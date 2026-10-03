#!/usr/bin/env python3
"""Apply the public patch series and unpack pinned CMake dependencies atomically."""
import argparse
import importlib.util
from pathlib import Path


def _load_apply_series(path):
    spec = importlib.util.spec_from_file_location("apply_series", path)
    if spec is None or spec.loader is None:
        raise ValueError("APPLY_SERIES_MODULE_UNAVAILABLE")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def prepare(root, downloads):
    root = Path(root).resolve()
    downloads = Path(downloads).resolve()
    module = _load_apply_series(root / "patches" / "apply-series.py")
    output = module.ensure_output_available(root / "sources")
    pins = module.load_pins(root / "pins" / "upstream.json")
    staging = module.create_staging(output)
    try:
        module.apply_into_staging(
            downloads,
            staging,
            root / "patches",
            pins,
        )
        for dependency in pins["source_sets"]["dependencies"]:
            pin = pins["archives"][dependency["component"]]
            module.extract_pinned_archive(
                downloads,
                staging,
                pin,
                dependency["destination"],
            )
        module.publish_staging(staging, output)
        staging = None
    except BaseException:
        module.cleanup_staging(staging)
        raise
    print("SOURCE_AND_CMAKE_DEPENDENCIES_READY")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--downloads", type=Path, required=True)
    args = parser.parse_args()
    prepare(args.root, args.downloads)
