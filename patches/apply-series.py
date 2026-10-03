#!/usr/bin/env python3
"""Apply the pinned patch series to fresh source trees as one transaction."""
import argparse
import ctypes
import errno
import hashlib
import json
import os
import re
import shutil
import subprocess
import tarfile
import tempfile
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit

PIN_FILE = Path(__file__).resolve().parent.parent / "pins" / "upstream.json"
PIN_COMPONENTS = {
    "sglang",
    "ktransformers",
    "llama",
    "pybind11",
    "flashinfer",
    "flashinfer-alternate",
}
EXPECTED_PATCH_SOURCES = ("sglang", "ktransformers")
EXPECTED_DEPENDENCIES = ("llama", "pybind11")
EXPECTED_RECORDED_ONLY = ("flashinfer", "flashinfer-alternate")
_COMPONENT_RE = re.compile(r"[a-z][a-z0-9-]*\Z")
_ARCHIVE_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*\.tar\.gz\Z")
_SHA1_RE = re.compile(r"[a-f0-9]{40}\Z")
_SHA256_RE = re.compile(r"[a-f0-9]{64}\Z")


def sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _repository_path(upstream):
    parsed = urlsplit(upstream)
    if (
        parsed.scheme != "https"
        or parsed.netloc != "github.com"
        or parsed.query
        or parsed.fragment
        or parsed.username
        or parsed.password
    ):
        raise ValueError("INVALID_UPSTREAM_URL")
    parts = parsed.path.split("/")
    if len(parts) != 3 or not parts[1] or not parts[2]:
        raise ValueError("INVALID_UPSTREAM_URL")
    return parts[1], parts[2]


def _validate_revision_source(upstream, revision, codeload_url):
    if not isinstance(revision, str) or not _SHA1_RE.fullmatch(revision):
        raise ValueError("INVALID_UPSTREAM_REVISION")
    owner, repository = _repository_path(upstream)
    expected = f"https://codeload.github.com/{owner}/{repository}/tar.gz/{revision}"
    if codeload_url != expected:
        raise ValueError("INVALID_CODELOAD_URL")


def load_pins(path=None):
    pin_path = Path(path) if path is not None else PIN_FILE
    if pin_path.is_symlink() or not pin_path.is_file():
        raise ValueError("MISSING_UPSTREAM_PINS")
    try:
        document = json.loads(pin_path.read_text(encoding="utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("MALFORMED_UPSTREAM_PINS") from exc
    if not isinstance(document, dict) or set(document) != {
        "schema",
        "source_sets",
        "archives",
        "recipe",
        "flashinfer_scope",
    }:
        raise ValueError("MALFORMED_UPSTREAM_PINS")
    if type(document["schema"]) is not int or document["schema"] != 2:
        raise ValueError("UNSUPPORTED_UPSTREAM_PIN_SCHEMA")

    raw_archives = document["archives"]
    if not isinstance(raw_archives, list) or not raw_archives:
        raise ValueError("MISSING_UPSTREAM_ARCHIVES")
    archives = {}
    archive_names = set()
    archive_digests = set()
    revisions = set()
    required_archive_fields = {
        "component",
        "archive",
        "sha256",
        "upstream",
        "revision",
        "codeload_url",
    }
    for record in raw_archives:
        if not isinstance(record, dict) or set(record) != required_archive_fields:
            raise ValueError("MALFORMED_UPSTREAM_PIN")
        component = record["component"]
        archive = record["archive"]
        digest = record["sha256"]
        upstream = record["upstream"]
        revision = record["revision"]
        codeload_url = record["codeload_url"]
        if not isinstance(component, str) or not _COMPONENT_RE.fullmatch(component):
            raise ValueError("INVALID_UPSTREAM_COMPONENT")
        if component not in PIN_COMPONENTS or component in archives:
            raise ValueError("DUPLICATE_OR_UNKNOWN_UPSTREAM_COMPONENT")
        if (
            not isinstance(archive, str)
            or not _ARCHIVE_RE.fullmatch(archive)
            or "/" in archive
            or "\\" in archive
            or archive in archive_names
        ):
            raise ValueError("DUPLICATE_OR_INVALID_ARCHIVE_NAME")
        if not isinstance(digest, str) or not _SHA256_RE.fullmatch(digest) or digest in archive_digests:
            raise ValueError("DUPLICATE_OR_INVALID_ARCHIVE_SHA256")
        if not isinstance(upstream, str):
            raise ValueError("INVALID_UPSTREAM_URL")
        _validate_revision_source(upstream, revision, codeload_url)
        revision_key = (upstream, revision)
        if revision_key in revisions:
            raise ValueError("DUPLICATE_UPSTREAM_REVISION")
        revisions.add(revision_key)
        archive_names.add(archive)
        archive_digests.add(digest)
        archives[component] = dict(record)
    if set(archives) != PIN_COMPONENTS:
        raise ValueError("MISSING_UPSTREAM_COMPONENT")

    source_sets = document["source_sets"]
    if not isinstance(source_sets, dict) or set(source_sets) != {
        "patch_sources",
        "dependencies",
        "recorded_only",
    }:
        raise ValueError("MALFORMED_UPSTREAM_SOURCE_SETS")
    patch_sources = source_sets["patch_sources"]
    recorded_only = source_sets["recorded_only"]
    dependencies = source_sets["dependencies"]
    if (
        not isinstance(patch_sources, list)
        or tuple(patch_sources) != EXPECTED_PATCH_SOURCES
        or not isinstance(recorded_only, list)
        or tuple(recorded_only) != EXPECTED_RECORDED_ONLY
    ):
        raise ValueError("MISSING_OR_DUPLICATE_UPSTREAM_SOURCE_SET_MEMBER")
    if not isinstance(dependencies, list):
        raise ValueError("MALFORMED_UPSTREAM_DEPENDENCIES")
    checked_dependencies = []
    dependency_components = []
    destinations = set()
    for dependency in dependencies:
        if not isinstance(dependency, dict) or set(dependency) != {"component", "destination"}:
            raise ValueError("MALFORMED_UPSTREAM_DEPENDENCY")
        component = dependency["component"]
        destination = dependency["destination"]
        if not isinstance(component, str) or component in dependency_components:
            raise ValueError("DUPLICATE_OR_INVALID_DEPENDENCY")
        if not isinstance(destination, str) or "\\" in destination:
            raise ValueError("INVALID_DEPENDENCY_DESTINATION")
        relative = PurePosixPath(destination)
        if (
            relative.is_absolute()
            or not relative.parts
            or ".." in relative.parts
            or relative.parts[:2] != ("ktransformers", "third_party")
            or not re.fullmatch(r"ktransformers/third_party/[A-Za-z0-9._/-]+", destination)
            or destination in destinations
        ):
            raise ValueError("INVALID_DEPENDENCY_DESTINATION")
        dependency_components.append(component)
        destinations.add(destination)
        checked_dependencies.append({"component": component, "destination": destination})
    if tuple(dependency_components) != EXPECTED_DEPENDENCIES:
        raise ValueError("MISSING_OR_DUPLICATE_DEPENDENCY")
    all_components = (
        list(patch_sources)
        + dependency_components
        + list(recorded_only)
    )
    if len(all_components) != len(set(all_components)) or set(all_components) != PIN_COMPONENTS:
        raise ValueError("UPSTREAM_SOURCE_SETS_DO_NOT_PARTITION_PINS")

    recipe = document["recipe"]
    if not isinstance(recipe, dict) or set(recipe) != {"upstream", "revision", "codeload_url"}:
        raise ValueError("MALFORMED_RECIPE_PIN")
    if not isinstance(recipe["upstream"], str):
        raise ValueError("INVALID_RECIPE_UPSTREAM")
    _validate_revision_source(recipe["upstream"], recipe["revision"], recipe["codeload_url"])
    if (recipe["upstream"], recipe["revision"]) in revisions:
        raise ValueError("DUPLICATE_UPSTREAM_REVISION")
    if not isinstance(document["flashinfer_scope"], str) or not document["flashinfer_scope"].strip():
        raise ValueError("MISSING_FLASHINFER_SCOPE")
    return {
        "archives": archives,
        "source_sets": {
            "patch_sources": tuple(patch_sources),
            "dependencies": tuple(checked_dependencies),
            "recorded_only": tuple(recorded_only),
        },
        "recipe": dict(recipe),
        "flashinfer_scope": document["flashinfer_scope"],
    }


def _verify_archive(downloads, pin):
    archive_path = Path(downloads) / pin["archive"]
    if archive_path.is_symlink():
        raise ValueError("UPSTREAM_ARCHIVE_SYMLINK")
    if not archive_path.is_file():
        raise ValueError("MISSING_UPSTREAM_ARCHIVE")
    if sha(archive_path) != pin["sha256"]:
        raise ValueError("UPSTREAM_SHA_MISMATCH")
    return archive_path


def _verify_archives(downloads, pins, components):
    verified = set()
    for component in components:
        if component not in pins["archives"] or component in verified:
            raise ValueError("MISSING_OR_DUPLICATE_UPSTREAM_COMPONENT")
        _verify_archive(downloads, pins["archives"][component])
        verified.add(component)
    return frozenset(verified)


def ensure_output_available(output):
    path = Path(os.path.abspath(os.fspath(output)))
    if os.path.lexists(path):
        raise ValueError("OUTPUT_ALREADY_EXISTS")
    if not path.parent.is_dir():
        raise ValueError("OUTPUT_PARENT_NOT_DIRECTORY")
    return path


def create_staging(output):
    path = ensure_output_available(output)
    try:
        return Path(tempfile.mkdtemp(prefix=f".{path.name}.staging-", dir=path.parent))
    except FileNotFoundError as exc:
        raise ValueError("OUTPUT_PARENT_NOT_DIRECTORY") from exc


def cleanup_staging(staging):
    if staging is None:
        return
    path = Path(staging)
    if not os.path.lexists(path):
        return
    if path.is_symlink() or not path.is_dir():
        path.unlink()
    else:
        shutil.rmtree(path)


def publish_staging(staging, output):
    stage = Path(os.path.abspath(os.fspath(staging)))
    destination = ensure_output_available(output)
    if stage.parent != destination.parent or stage.is_symlink() or not stage.is_dir():
        raise ValueError("INVALID_STAGING_DIRECTORY")
    try:
        libc = ctypes.CDLL(None, use_errno=True)
        renameat2 = libc.renameat2
    except (AttributeError, OSError) as exc:
        raise ValueError("ATOMIC_NO_REPLACE_PUBLISH_UNAVAILABLE") from exc
    renameat2.argtypes = (
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_uint,
    )
    renameat2.restype = ctypes.c_int
    result = renameat2(
        -100,
        os.fsencode(stage),
        -100,
        os.fsencode(destination),
        1,
    )
    if result != 0:
        error = ctypes.get_errno()
        if error == errno.EEXIST:
            raise ValueError("OUTPUT_ALREADY_EXISTS")
        raise OSError(error, os.strerror(error), os.fspath(destination))
    return destination


def extract_pinned_archive(downloads, staging, pin, destination):
    stage = Path(staging)
    if stage.is_symlink() or not stage.is_dir():
        raise ValueError("INVALID_STAGING_DIRECTORY")
    archive_path = _verify_archive(downloads, pin)
    if not isinstance(destination, str) or "\\" in destination:
        raise ValueError("INVALID_EXTRACTION_DESTINATION")
    relative = PurePosixPath(destination)
    if (
        relative.is_absolute()
        or not relative.parts
        or ".." in relative.parts
        or (
            destination != pin["component"]
            and not re.fullmatch(r"ktransformers/third_party/[A-Za-z0-9._/-]+", destination)
        )
    ):
        raise ValueError("INVALID_EXTRACTION_DESTINATION")
    component = pin["component"]
    temporary = stage / f".unpack-{component}"
    if os.path.lexists(temporary):
        raise ValueError("STAGING_PATH_COLLISION")
    temporary.mkdir()
    with tarfile.open(archive_path, "r:gz") as archive:
        archive.extractall(temporary, filter="data")
    members = list(temporary.iterdir())
    if len(members) != 1 or members[0].is_symlink() or not members[0].is_dir():
        raise ValueError("UNEXPECTED_ARCHIVE_ROOT")

    target = stage.joinpath(*relative.parts)
    parent = stage
    for part in relative.parts[:-1]:
        parent = parent / part
        if os.path.lexists(parent):
            if parent.is_symlink() or not parent.is_dir():
                raise ValueError("INVALID_EXTRACTION_PARENT")
        else:
            parent.mkdir()
    if os.path.lexists(target):
        if target.is_symlink() or not target.is_dir() or any(target.iterdir()):
            raise ValueError("DEPENDENCY_TARGET_NONEMPTY")
        target.rmdir()
    members[0].rename(target)
    temporary.rmdir()
    return target


def _validated_series(patches, allowed_projects):
    patch_root = Path(patches)
    if patch_root.is_symlink() or not patch_root.is_dir():
        raise ValueError("PATCH_ROOT_SYMLINK_OR_MISSING")
    pin_file = patch_root / "PATCHES.sha256"
    series_file = patch_root / "series"
    if (
        pin_file.is_symlink()
        or series_file.is_symlink()
        or not pin_file.is_file()
        or not series_file.is_file()
    ):
        raise ValueError("MISSING_SERIES_MANIFEST")

    manifest = {}
    for line in pin_file.read_text(encoding="utf-8").splitlines():
        fields = line.split()
        if len(fields) != 2:
            raise ValueError("INVALID_PATCH_MANIFEST")
        digest, name = fields
        if not _SHA256_RE.fullmatch(digest) or name in manifest:
            raise ValueError("INVALID_PATCH_MANIFEST")
        manifest[name] = digest
    series = series_file.read_text(encoding="utf-8").splitlines()
    if not series or any(not name for name in series):
        raise ValueError("EMPTY_SERIES")
    if len(set(series)) != len(series) or set(manifest) != set(series):
        raise ValueError("SERIES_MANIFEST_MISMATCH")

    for name in series:
        if not re.fullmatch(r"(sglang|ktransformers)/[A-Za-z0-9_.-]+\.patch", name):
            raise ValueError("INVALID_SERIES_PATH")
        project = name.split("/", 1)[0]
        if project not in allowed_projects:
            raise ValueError("PATCH_PROJECT_NOT_PINNED")
        patch_path = patch_root / name
        if patch_path.is_symlink() or patch_path.parent.is_symlink() or not patch_path.is_file():
            raise ValueError("PATCH_FILE_MISSING_OR_SYMLINK")
        if sha(patch_path) != manifest[name]:
            raise ValueError("PATCH_SHA_MISMATCH")
        text = patch_path.read_text(encoding="utf-8")
        lines = text.splitlines()
        if not text.strip() or not any(line.startswith("@@ ") for line in lines):
            raise ValueError("EMPTY_OR_INVALID_PATCH")
        for header in ("Origin:", "Purpose:", "License:"):
            if not any(line.startswith(header) and line[len(header):].strip() for line in lines):
                raise ValueError("MISSING_PATCH_HEADER")
        for line in lines:
            if not line.startswith(("--- ", "+++ ")):
                continue
            file_name = line[4:].split("\t", 1)[0]
            if file_name == "/dev/null":
                continue
            relative = PurePosixPath(file_name)
            if (
                "\\" in file_name
                or relative.is_absolute()
                or not relative.parts
                or ".." in relative.parts
                or relative.parts[0] not in ("a", "b")
            ):
                raise ValueError("INVALID_DIFF_PATH")
    return patch_root, series


def _apply_validated_series(staging, patch_root, series):
    for name in series:
        project = name.split("/", 1)[0]
        project_root = Path(staging) / project
        if project_root.is_symlink() or not project_root.is_dir():
            raise ValueError("PATCH_PROJECT_TREE_MISSING")
        command = [
            "patch",
            "--batch",
            "--fuzz=0",
            "-p1",
            "--input=" + str((patch_root / name).resolve()),
        ]
        subprocess.run(command + ["--dry-run"], cwd=project_root, check=True)
        subprocess.run(command, cwd=project_root, check=True)


def apply_into_staging(downloads, staging, patches, pins=None):
    pins = load_pins() if pins is None else pins
    stage = Path(staging)
    if stage.is_symlink() or not stage.is_dir() or any(stage.iterdir()):
        raise ValueError("STAGING_DIRECTORY_NOT_EMPTY")
    patch_sources = pins["source_sets"]["patch_sources"]
    patch_root, series = _validated_series(patches, set(patch_sources))
    _verify_archives(downloads, pins, patch_sources)
    for component in patch_sources:
        extract_pinned_archive(
            downloads,
            stage,
            pins["archives"][component],
            component,
        )
    _apply_validated_series(stage, patch_root, series)
    return len(series)


def unpack(downloads, output):
    destination = ensure_output_available(output)
    pins = load_pins()
    patch_sources = pins["source_sets"]["patch_sources"]
    _verify_archives(downloads, pins, patch_sources)
    staging = create_staging(destination)
    try:
        for component in patch_sources:
            extract_pinned_archive(
                downloads,
                staging,
                pins["archives"][component],
                component,
            )
        publish_staging(staging, destination)
        staging = None
    except BaseException:
        cleanup_staging(staging)
        raise


def apply(downloads, output, patches):
    destination = ensure_output_available(output)
    pins = load_pins()
    staging = create_staging(destination)
    try:
        patch_count = apply_into_staging(downloads, staging, patches, pins)
        publish_staging(staging, destination)
        staging = None
    except BaseException:
        cleanup_staging(staging)
        raise
    print("APPLY_OK patches=" + str(patch_count))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--downloads", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--patches", type=Path, required=True)
    args = parser.parse_args()
    apply(args.downloads, args.output, args.patches)


if __name__ == "__main__":
    main()
