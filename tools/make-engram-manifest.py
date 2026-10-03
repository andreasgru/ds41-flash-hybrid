#!/usr/bin/env python3
"""Create the adapter's Engram offset manifest from verified safetensors headers.

This is the parameterized form of the reference manifest helper
(SHA256 b3457e93a8eedceea99975493c804d27ad791dd3b1a4e99cc10c4867bded8c10).
It reads the model index and safetensors headers only; tensor payloads are
neither extracted nor loaded.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import stat
import sys
import tempfile
from pathlib import Path, PureWindowsPath
from typing import Any

_TOOL_ROOT = Path(__file__).resolve().parents[1]
_SCRIPTS = _TOOL_ROOT / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from verify_model_shards import ReadinessError, validate_readiness  # noqa: E402

INDEX_NAME = "model.safetensors.index.json"
MANIFEST_NAME = "engram-manifest.json"
MAX_INDEX_BYTES = 64 * 1024 * 1024
MAX_HEADER_BYTES = 32 * 1024 * 1024
_SHARD_NAME = re.compile(r"[^/\\\x00]+\.safetensors\Z")
_TENSOR_NAME = re.compile(r"^layers\.(\d+)\.engram\.embed\.(weight|scale)$")


class ManifestError(ValueError):
    """A stable, path-free manifest-generation failure."""


def _open_regular(path: Path, code: str):
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        raise ManifestError(code) from exc
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode):
            raise ManifestError(code)
        return os.fdopen(fd, "rb"), before
    except BaseException:
        os.close(fd)
        raise


def _unchanged(before: os.stat_result, after: os.stat_result) -> bool:
    return (
        before.st_dev == after.st_dev
        and before.st_ino == after.st_ino
        and before.st_size == after.st_size
        and before.st_mtime_ns == after.st_mtime_ns
    )


def _model_directory(value: str | os.PathLike[str]) -> Path:
    try:
        model = Path(value).expanduser().resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise ManifestError("MODEL_DIRECTORY_INVALID") from exc
    if not model.is_dir():
        raise ManifestError("MODEL_DIRECTORY_INVALID")
    return model


def _output_path(value: str | os.PathLike[str]) -> Path:
    requested = Path(value).expanduser()
    if requested.name != MANIFEST_NAME:
        raise ManifestError("MANIFEST_OUTPUT_INVALID")
    parent = requested.parent
    try:
        parent.mkdir(parents=True, exist_ok=True)
        parent = parent.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise ManifestError("MANIFEST_OUTPUT_INVALID") from exc
    if not parent.is_dir():
        raise ManifestError("MANIFEST_OUTPUT_INVALID")
    return parent / requested.name


def _read_index(model: Path) -> dict[str, str]:
    path = model / INDEX_NAME
    stream, before = _open_regular(path, "MODEL_INDEX_INVALID")
    with stream:
        raw = stream.read(MAX_INDEX_BYTES + 1)
        after = os.fstat(stream.fileno())
    if len(raw) > MAX_INDEX_BYTES or not _unchanged(before, after):
        raise ManifestError("MODEL_INDEX_INVALID")
    try:
        index = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ManifestError("MODEL_INDEX_INVALID") from exc
    if not isinstance(index, dict) or not isinstance(index.get("weight_map"), dict):
        raise ManifestError("MODEL_INDEX_INVALID")
    weight_map = index["weight_map"]
    if any(not isinstance(key, str) or not isinstance(value, str) for key, value in weight_map.items()):
        raise ManifestError("MODEL_INDEX_INVALID")
    return weight_map


def _selected_tensors(weight_map: dict[str, str]) -> dict[str, str]:
    selected = {
        key: filename
        for key, filename in weight_map.items()
        if _TENSOR_NAME.fullmatch(key) is not None
    }
    if len(selected) != 4:
        raise ManifestError("ENGRAM_TENSOR_SET_INVALID")
    for filename in selected.values():
        if (
            not filename
            or filename in (".", "..")
            or "/" in filename
            or "\\" in filename
            or "\x00" in filename
            or Path(filename).is_absolute()
            or PureWindowsPath(filename).is_absolute()
            or PureWindowsPath(filename).drive
            or Path(filename).name != filename
            or _SHARD_NAME.fullmatch(filename) is None
        ):
            raise ManifestError("ENGRAM_SHARD_PATH_INVALID")
    return selected


def _read_header(model: Path, filename: str) -> tuple[dict[str, Any], int, int]:
    path = model / filename
    stream, before = _open_regular(path, "ENGRAM_SHARD_INVALID")
    with stream:
        length_bytes = stream.read(8)
        if len(length_bytes) != 8:
            raise ManifestError("SAFETENSORS_HEADER_INVALID")
        header_length = int.from_bytes(length_bytes, "little", signed=False)
        if not 0 < header_length < MAX_HEADER_BYTES:
            raise ManifestError("SAFETENSORS_HEADER_INVALID")
        header_bytes = stream.read(header_length)
        after = os.fstat(stream.fileno())
    if len(header_bytes) != header_length or not _unchanged(before, after):
        raise ManifestError("SAFETENSORS_HEADER_INVALID")
    try:
        header = json.loads(header_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ManifestError("SAFETENSORS_HEADER_INVALID") from exc
    if not isinstance(header, dict):
        raise ManifestError("SAFETENSORS_HEADER_INVALID")
    return header, 8 + header_length, before.st_size


def _tensor_metadata(header: dict[str, Any], key: str, dtype: str, shape: list[int], payload_size: int):
    tensor = header.get(key)
    if not isinstance(tensor, dict) or tensor.get("dtype") != dtype or tensor.get("shape") != shape:
        raise ManifestError("ENGRAM_TENSOR_METADATA_INVALID")
    offsets = tensor.get("data_offsets")
    if (
        not isinstance(offsets, list)
        or len(offsets) != 2
        or any(type(value) is not int for value in offsets)
    ):
        raise ManifestError("ENGRAM_TENSOR_OFFSETS_INVALID")
    low, high = offsets
    if not 0 <= low < high <= payload_size or high - low != math.prod(shape):
        raise ManifestError("ENGRAM_TENSOR_OFFSETS_INVALID")
    return low, high


def _manifest(model: Path, selected: dict[str, str]) -> tuple[dict[str, Any], int]:
    headers: dict[str, tuple[dict[str, Any], int, int]] = {}
    header_bytes_read = 0
    for filename in sorted(set(selected.values())):
        header, payload_offset, file_size = _read_header(model, filename)
        headers[filename] = (header, payload_offset, file_size)
        header_bytes_read += payload_offset

    layers: dict[str, dict[str, Any]] = {}
    for key, filename in selected.items():
        match = _TENSOR_NAME.fullmatch(key)
        if match is None:
            continue
        layer_id, kind = match.groups()
        if kind != "weight":
            continue
        scale_key = f"layers.{layer_id}.engram.embed.scale"
        if selected.get(scale_key) != filename:
            raise ManifestError("ENGRAM_LAYER_SHARD_MISMATCH")

        header, payload_offset, file_size = headers[filename]
        weight_key = f"layers.{layer_id}.engram.embed.weight"
        payload_size = file_size - payload_offset
        weight = header.get(weight_key)
        if not isinstance(weight, dict):
            raise ManifestError("ENGRAM_TENSOR_METADATA_INVALID")
        shape = weight.get("shape")
        if (
            not isinstance(shape, list)
            or len(shape) != 2
            or any(type(value) is not int for value in shape)
        ):
            raise ManifestError("ENGRAM_TENSOR_SHAPE_INVALID")
        rows, dim = shape
        if rows <= 0 or dim != 256:
            raise ManifestError("ENGRAM_TENSOR_SHAPE_INVALID")

        weight_low, weight_high = _tensor_metadata(
            header, weight_key, "F8_E4M3", [rows, 256], payload_size
        )
        scale_low, scale_high = _tensor_metadata(
            header, scale_key, "F8_E8M0", [rows, 8], payload_size
        )
        if not (weight_high <= scale_low or scale_high <= weight_low):
            raise ManifestError("ENGRAM_TENSORS_OVERLAP")

        layers[layer_id] = {
            "file": filename,
            "rows": rows,
            "dim": dim,
            "block_size": 32,
            "weight_dtype": weight["dtype"],
            "scale_dtype": header[scale_key]["dtype"],
            "weight_offset": payload_offset + weight_low,
            "scale_offset": payload_offset + scale_low,
            "weight_bytes": weight_high - weight_low,
            "scale_bytes": scale_high - scale_low,
        }

    if set(layers) != {"1", "14"}:
        raise ManifestError("ENGRAM_LAYER_SET_INVALID")
    return {"base_dir": str(model), "layers": layers}, header_bytes_read


def _publish(path: Path, content: bytes) -> bool:
    """Create the manifest exclusively; return False for identical existing content."""
    if os.path.lexists(path):
        stream, _before = _open_regular(path, "MANIFEST_OUTPUT_INVALID")
        with stream:
            existing = stream.read(len(content) + 1)
        if existing == content:
            return False
        raise ManifestError("MANIFEST_OUTPUT_EXISTS_DIFFERENT")

    fd = -1
    temporary: Path | None = None
    try:
        fd, raw_path = tempfile.mkstemp(prefix=f".{path.name}.tmp-", dir=path.parent)
        temporary = Path(raw_path)
        with os.fdopen(fd, "wb") as stream:
            fd = -1
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, path, follow_symlinks=False)
        temporary.unlink()
        temporary = None
        return True
    except FileExistsError as exc:
        raise ManifestError("MANIFEST_OUTPUT_EXISTS_DIFFERENT") from exc
    except OSError as exc:
        raise ManifestError("MANIFEST_OUTPUT_WRITE_FAILED") from exc
    finally:
        if fd >= 0:
            os.close(fd)
        if temporary is not None:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass
            except OSError as exc:
                raise ManifestError("MANIFEST_TEMP_CLEANUP_FAILED") from exc


def create_manifest(
    model_dir: str | os.PathLike[str],
    output: str | os.PathLike[str],
) -> dict[str, Any]:
    model = _model_directory(model_dir)
    try:
        validate_readiness(model)
    except ReadinessError as exc:
        raise ManifestError(str(exc)) from exc

    weight_map = _read_index(model)
    selected = _selected_tensors(weight_map)
    manifest, header_bytes_read = _manifest(model, selected)
    content = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8")
    destination = _output_path(output)
    created = _publish(destination, content)
    return {
        "created": created,
        "table_count": len(manifest["layers"]),
        "tensor_count": len(selected),
        "header_bytes_read": header_bytes_read,
        "tensor_payload_bytes_read": 0,
        "manifest_bytes": len(content),
        "manifest_sha256": hashlib.sha256(content).hexdigest(),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-dir", required=True, help="directory with verified model shards")
    parser.add_argument("--output", required=True, help="destination for the adapter manifest")
    args = parser.parse_args(argv)
    try:
        result = create_manifest(args.model_dir, args.output)
    except (ManifestError, ReadinessError) as exc:
        print(f"ENGRAM_MANIFEST_FAILED {exc}", file=sys.stderr)
        return 2
    state = "ENGRAM_MANIFEST_CREATED" if result["created"] else "ENGRAM_MANIFEST_UNCHANGED"
    print(
        f"{state} tables={result['table_count']} tensors={result['tensor_count']} "
        f"header_bytes_read={result['header_bytes_read']} "
        f"tensor_payload_bytes_read={result['tensor_payload_bytes_read']} "
        f"manifest_bytes={result['manifest_bytes']} "
        f"manifest_sha256={result['manifest_sha256']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
