#!/usr/bin/env python3
"""Verify the 52 real model shards and create a filename-free readiness receipt.

The receipt can be written only after every shard named by SHA256SUMS has been
stream-hashed successfully. validate_readiness() is read-only and is intended
for the service preflight.

Origin: project-owned implementation. License: Apache-2.0.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import sys
import tempfile
from pathlib import Path, PureWindowsPath
from typing import Any

SHARD_COUNT = 52
SUMS_NAME = "SHA256SUMS"
RECEIPT_NAME = "checksums.ok"
CHUNK_SIZE = 1024 * 1024
MAX_SUMS_BYTES = 1024 * 1024
MAX_RECEIPT_BYTES = 4096
_HEX_256 = re.compile(r"[0-9a-f]{64}\Z")
_SUMS_LINE = re.compile(r"([0-9a-fA-F]{64}) ([ *])(.+)\Z")


class ReadinessError(ValueError):
    """A stable, filename-free model-readiness failure."""


def _model_root(model: str | os.PathLike[str]) -> Path:
    try:
        root = Path(model).expanduser().resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise ReadinessError("MODEL_DIRECTORY_INVALID") from exc
    if not root.is_dir():
        raise ReadinessError("MODEL_DIRECTORY_INVALID")
    return root


def _fixed_member(root: Path, value: str | os.PathLike[str], expected_name: str) -> Path:
    candidate = Path(value).expanduser()
    if candidate.name != expected_name or any(part in (".", "..") for part in candidate.parts):
        raise ReadinessError("MODEL_READINESS_PATH_INVALID")
    if candidate.is_absolute():
        try:
            parent = candidate.parent.resolve(strict=True)
        except (OSError, RuntimeError) as exc:
            raise ReadinessError("MODEL_READINESS_PATH_INVALID") from exc
        if parent != root:
            raise ReadinessError("MODEL_READINESS_PATH_INVALID")
    elif candidate.parts != (expected_name,):
        raise ReadinessError("MODEL_READINESS_PATH_INVALID")
    return root / expected_name


def _open_regular(path: Path, failure_code: str):
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        raise ReadinessError(failure_code) from exc
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode):
            raise ReadinessError(failure_code)
        return os.fdopen(fd, "rb"), before
    except BaseException:
        os.close(fd)
        raise


def _same_file_state(before: os.stat_result, after: os.stat_result) -> bool:
    return (
        before.st_dev == after.st_dev
        and before.st_ino == after.st_ino
        and before.st_size == after.st_size
        and before.st_mtime_ns == after.st_mtime_ns
    )


def _read_sums(root: Path) -> tuple[list[tuple[str, str]], str]:
    path = root / SUMS_NAME
    stream, before = _open_regular(path, "SHA256SUMS_INVALID")
    with stream:
        raw = stream.read(MAX_SUMS_BYTES + 1)
        after = os.fstat(stream.fileno())
    if len(raw) > MAX_SUMS_BYTES or not _same_file_state(before, after):
        raise ReadinessError("SHA256SUMS_INVALID")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ReadinessError("SHA256SUMS_INVALID") from exc
    lines = text.splitlines()
    if len(lines) != SHARD_COUNT:
        raise ReadinessError("SHA256SUMS_SHARD_COUNT_INVALID")

    entries: list[tuple[str, str]] = []
    seen: set[str] = set()
    for line in lines:
        match = _SUMS_LINE.fullmatch(line)
        if match is None:
            raise ReadinessError("SHA256SUMS_LINE_INVALID")
        expected_hash, _mode, name = match.groups()
        if (
            not name
            or name != name.strip()
            or name in (".", "..")
            or "/" in name
            or "\\" in name
            or "\x00" in name
            or Path(name).is_absolute()
            or Path(name).name != name
            or PureWindowsPath(name).is_absolute()
            or PureWindowsPath(name).drive
            or not name.endswith(".safetensors")
        ):
            raise ReadinessError("SHA256SUMS_PATH_INVALID")
        if name in seen:
            raise ReadinessError("SHA256SUMS_DUPLICATE_SHARD")
        seen.add(name)
        entries.append((name, expected_hash.lower()))

    return entries, hashlib.sha256(raw).hexdigest()


def _actual_shard_names(root: Path) -> set[str]:
    names: set[str] = set()
    pending = [root]
    while pending:
        directory = pending.pop()
        try:
            children = list(directory.iterdir())
        except OSError as exc:
            raise ReadinessError("MODEL_DIRECTORY_INVALID") from exc
        for child in children:
            if child.name.endswith(".safetensors"):
                if directory != root:
                    raise ReadinessError("MODEL_SHARD_SET_INVALID")
                try:
                    info = child.lstat()
                except OSError as exc:
                    raise ReadinessError("MODEL_SHARD_SET_INVALID") from exc
                if not stat.S_ISREG(info.st_mode):
                    raise ReadinessError("MODEL_SHARD_TYPE_INVALID")
                names.add(child.name)
                continue
            try:
                info = child.lstat()
            except OSError as exc:
                raise ReadinessError("MODEL_DIRECTORY_INVALID") from exc
            if stat.S_ISDIR(info.st_mode):
                pending.append(child)
    return names


def _check_shard_set(root: Path, entries: list[tuple[str, str]]) -> None:
    if len(entries) != SHARD_COUNT:
        raise ReadinessError("SHA256SUMS_SHARD_COUNT_INVALID")
    expected_names = {name for name, _digest in entries}
    if len(expected_names) != SHARD_COUNT or _actual_shard_names(root) != expected_names:
        raise ReadinessError("MODEL_SHARD_SET_INVALID")


def _stream_sha256(root: Path, name: str) -> str:
    path = root / name
    stream, before = _open_regular(path, "MODEL_SHARD_TYPE_INVALID")
    digest = hashlib.sha256()
    with stream:
        while True:
            block = stream.read(CHUNK_SIZE)
            if not block:
                break
            digest.update(block)
        after = os.fstat(stream.fileno())
    if not _same_file_state(before, after):
        raise ReadinessError("MODEL_SHARD_CHANGED_DURING_READ")
    return digest.hexdigest()


def _receipt_object(manifest_sha256: str) -> dict[str, Any]:
    return {
        "schema": 1,
        "status": "ok",
        "manifest_sha256": manifest_sha256,
        "verified_shards": SHARD_COUNT,
    }


def _create_receipt_exclusive(root: Path, receipt: dict[str, Any]) -> None:
    destination = root / RECEIPT_NAME
    if os.path.lexists(destination):
        raise ReadinessError("READINESS_RECEIPT_ALREADY_EXISTS")

    payload = (json.dumps(receipt, separators=(",", ":")) + "\n").encode("utf-8")
    fd = -1
    temporary: Path | None = None
    try:
        fd, raw_path = tempfile.mkstemp(prefix=".checksums.ok.tmp-", dir=root)
        temporary = Path(raw_path)
        with os.fdopen(fd, "wb") as stream:
            fd = -1
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        # A hard link publishes the complete receipt without replacing an
        # existing file. The staging file is in the same directory/filesystem.
        os.link(temporary, destination, follow_symlinks=False)
        temporary.unlink()
        temporary = None
        dir_fd = os.open(root, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)
    except FileExistsError as exc:
        raise ReadinessError("READINESS_RECEIPT_ALREADY_EXISTS") from exc
    except OSError as exc:
        raise ReadinessError("READINESS_RECEIPT_WRITE_FAILED") from exc
    finally:
        if fd >= 0:
            os.close(fd)
        if temporary is not None:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass
            except OSError as exc:
                raise ReadinessError("READINESS_TEMP_CLEANUP_FAILED") from exc


def verify_model_shards(
    model: str | os.PathLike[str],
    sha256sums: str | os.PathLike[str] = SUMS_NAME,
    receipt_path: str | os.PathLike[str] = RECEIPT_NAME,
) -> dict[str, Any]:
    """Verify actual shard bytes and exclusively create checksums.ok."""
    root = _model_root(model)
    sums_path = _fixed_member(root, sha256sums, SUMS_NAME)
    receipt_file = _fixed_member(root, receipt_path, RECEIPT_NAME)
    if os.path.lexists(receipt_file):
        raise ReadinessError("READINESS_RECEIPT_ALREADY_EXISTS")

    entries, manifest_sha256 = _read_sums(root)
    _check_shard_set(root, entries)
    for name, expected_hash in entries:
        if _stream_sha256(root, name) != expected_hash:
            raise ReadinessError("MODEL_SHARD_SHA256_MISMATCH")

    # Bind the result to the exact manifest bytes that still exist after the
    # shard reads; a changed list cannot receive a receipt for an old snapshot.
    final_entries, final_manifest_sha256 = _read_sums(root)
    if final_manifest_sha256 != manifest_sha256 or final_entries != entries:
        raise ReadinessError("SHA256SUMS_CHANGED_DURING_VERIFICATION")
    if _actual_shard_names(root) != {name for name, _digest in entries}:
        raise ReadinessError("MODEL_SHARD_SET_CHANGED_DURING_VERIFICATION")

    result = _receipt_object(manifest_sha256)
    _create_receipt_exclusive(root, result)
    return result


def _no_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ReadinessError("READINESS_RECEIPT_DUPLICATE_KEY")
        value[key] = item
    return value


def _read_receipt(root: Path) -> dict[str, Any]:
    path = root / RECEIPT_NAME
    stream, before = _open_regular(path, "READINESS_RECEIPT_INVALID")
    with stream:
        raw = stream.read(MAX_RECEIPT_BYTES + 1)
        after = os.fstat(stream.fileno())
    if len(raw) > MAX_RECEIPT_BYTES or not _same_file_state(before, after):
        raise ReadinessError("READINESS_RECEIPT_INVALID")
    try:
        decoded = raw.decode("utf-8")
        value = json.loads(decoded, object_pairs_hook=_no_duplicate_keys)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ReadinessError("READINESS_RECEIPT_INVALID") from exc
    if not isinstance(value, dict):
        raise ReadinessError("READINESS_RECEIPT_INVALID")
    return value


def validate_readiness(model: str | os.PathLike[str]) -> dict[str, Any]:
    """Validate the real current checksum list and its 52-shard receipt.

    This launch-time check confirms the current SHA256SUMS bytes, exact manifest
    entry set, existing non-symlink shard files and strict receipt schema. The
    expensive full-shard hashing is performed by verify_model_shards().
    """
    root = _model_root(model)
    entries, current_manifest_sha256 = _read_sums(root)
    _check_shard_set(root, entries)
    receipt = _read_receipt(root)
    if set(receipt) != {"schema", "status", "manifest_sha256", "verified_shards"}:
        raise ReadinessError("READINESS_RECEIPT_SCHEMA_INVALID")
    if type(receipt["schema"]) is not int or receipt["schema"] != 1:
        raise ReadinessError("READINESS_RECEIPT_SCHEMA_INVALID")
    if type(receipt["status"]) is not str or receipt["status"] != "ok":
        raise ReadinessError("READINESS_RECEIPT_STATUS_INVALID")
    manifest_sha256 = receipt["manifest_sha256"]
    if (
        type(manifest_sha256) is not str
        or _HEX_256.fullmatch(manifest_sha256) is None
        or manifest_sha256 != current_manifest_sha256
    ):
        raise ReadinessError("READINESS_RECEIPT_MANIFEST_MISMATCH")
    if type(receipt["verified_shards"]) is not int or receipt["verified_shards"] != SHARD_COUNT:
        raise ReadinessError("READINESS_RECEIPT_SHARD_COUNT_INVALID")
    final_entries, final_manifest_sha256 = _read_sums(root)
    if final_manifest_sha256 != current_manifest_sha256 or final_entries != entries:
        raise ReadinessError("SHA256SUMS_CHANGED_DURING_VALIDATION")
    if _actual_shard_names(root) != {name for name, _digest in entries}:
        raise ReadinessError("MODEL_SHARD_SET_CHANGED_DURING_VALIDATION")
    return receipt


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-dir", required=True, help="directory containing the model shards")
    parser.add_argument("--sha256sums", default=SUMS_NAME, help="fixed SHA256SUMS file in model-dir")
    parser.add_argument("--receipt", default=RECEIPT_NAME, help="fixed checksums.ok path in model-dir")
    args = parser.parse_args(argv)
    try:
        receipt = verify_model_shards(args.model_dir, args.sha256sums, args.receipt)
    except ReadinessError as exc:
        print(f"MODEL_READINESS_FAILED {exc}", file=sys.stderr)
        return 2
    print(
        "MODEL_READINESS_VERIFIED "
        f"shards={receipt['verified_shards']} "
        f"manifest_sha256={receipt['manifest_sha256']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
