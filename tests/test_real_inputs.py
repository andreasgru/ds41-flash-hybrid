"""Real archive/source checks; requires the four pinned input tarballs."""
import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import tempfile
import unittest
import uuid
from contextlib import contextmanager
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DOWNLOADS_ENV = "DS41_TEST_DOWNLOADS"
PATCH_COMPONENTS = ("sglang", "ktransformers")
DEPENDENCY_COMPONENTS = ("llama", "pybind11")

if not os.environ.get(DOWNLOADS_ENV):
    raise RuntimeError(
        "DS41_TEST_DOWNLOADS is required; real-input tests must not report zero selected cases as green."
    )


def _load_module(name, path):
    spec = importlib.util.spec_from_file_location(name + "_" + uuid.uuid4().hex, path)
    if spec is None or spec.loader is None:
        raise RuntimeError("PRODUCT_MODULE_UNAVAILABLE:" + str(path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


class RealInputTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        raw_downloads = os.environ.get(DOWNLOADS_ENV)
        if not raw_downloads:
            raise RuntimeError(
                "DS41_TEST_DOWNLOADS must name a directory containing all four "
                "pinned SGLang, KTransformers, llama.cpp and pybind11 archives."
            )
        cls.downloads = Path(raw_downloads).resolve()
        if not cls.downloads.is_dir():
            raise RuntimeError("DS41_TEST_DOWNLOADS is not a directory")
        temp_base = Path(tempfile.gettempdir()).resolve()
        if temp_base.is_relative_to(cls.downloads) or temp_base.is_relative_to(ROOT):
            raise RuntimeError("test temporary directory overlaps downloads or the release tree")

        apply_module = _load_module(
            "apply_series", ROOT / "patches" / "apply-series.py"
        )
        cls.pins = apply_module.load_pins(ROOT / "pins" / "upstream.json")
        cls.required_components = PATCH_COMPONENTS + DEPENDENCY_COMPONENTS
        missing = []
        for component in cls.required_components:
            pin = cls.pins["archives"][component]
            archive = cls.downloads / pin["archive"]
            if archive.is_symlink() or not archive.is_file():
                missing.append(pin["archive"])
            elif _sha(archive) != pin["sha256"]:
                missing.append(pin["archive"] + " (SHA256 mismatch)")
        if missing:
            raise RuntimeError(
                "DS41_TEST_DOWNLOADS is missing pinned archives: " + ", ".join(missing)
            )

    @contextmanager
    def _owned_temp(self, purpose):
        with tempfile.TemporaryDirectory(prefix="ds41-real-" + purpose + "-") as name:
            path = Path(name).resolve()
            if path.is_relative_to(self.downloads) or path.is_relative_to(ROOT):
                raise RuntimeError("owned test directory overlaps downloads or release tree")
            yield path

    def _copy_package_inputs(self, destination):
        destination = Path(destination)
        shutil.copytree(ROOT / "patches", destination / "patches")
        shutil.copytree(ROOT / "pins", destination / "pins")

        runtime_pins = json.loads((ROOT / "pins" / "runtime-files.json").read_text())["files"]
        for relative in runtime_pins:
            if relative.startswith("sources/"):
                continue
            source = ROOT / relative
            if source.is_symlink() or not source.is_file():
                raise RuntimeError("missing real public package input: " + relative)
            target = destination / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)

        scripts = destination / "scripts"
        scripts.mkdir(exist_ok=True)
        for filename in ("prepare_sources.py", "build_manifest.py"):
            shutil.copy2(ROOT / "scripts" / filename, scripts / filename)
        return destination

    def _apply_module(self, package_root):
        return _load_module(
            "apply_series", Path(package_root) / "patches" / "apply-series.py"
        )

    def _prepare_module(self, package_root):
        return _load_module(
            "prepare_sources", Path(package_root) / "scripts" / "prepare_sources.py"
        )

    def _manifest_module(self, package_root):
        return _load_module(
            "build_manifest", Path(package_root) / "scripts" / "build_manifest.py"
        )

    def _assert_no_output_or_staging(self, package_root, output):
        self.assertFalse(os.path.lexists(output), "failed transaction published output")
        stages = list(Path(package_root).glob("." + Path(output).name + ".staging-*"))
        self.assertEqual(stages, [], "failed transaction left its staging directory")

    def _series(self, patch_root):
        return (Path(patch_root) / "series").read_text().splitlines()

    def _manifest_rows(self, patch_root):
        path = Path(patch_root) / "PATCHES.sha256"
        rows = []
        for line in path.read_text().splitlines():
            fields = line.split(maxsplit=1)
            if len(fields) != 2:
                raise AssertionError("unexpected real PATCHES.sha256 row")
            rows.append((fields[0], fields[1]))
        return rows

    def _write_manifest_rows(self, patch_root, rows):
        path = Path(patch_root) / "PATCHES.sha256"
        path.write_text("".join(digest + "  " + name + "\n" for digest, name in rows))

    def _refresh_patch_digest(self, patch_root, name):
        patch = Path(patch_root) / name
        new_digest = _sha(patch)
        rows = self._manifest_rows(patch_root)
        changed = 0
        for index, (_, row_name) in enumerate(rows):
            if row_name == name:
                rows[index] = (new_digest, name)
                changed += 1
        if changed != 1:
            raise AssertionError("real patch must have exactly one pin row")
        self._write_manifest_rows(patch_root, rows)

    def _mutate_hunk_context(self, patch_root, name):
        patch = Path(patch_root) / name
        lines = patch.read_bytes().splitlines(keepends=True)
        in_hunk = False
        for index, line in enumerate(lines):
            if line.startswith(b"@@ "):
                in_hunk = True
                continue
            if line.startswith((b"diff ", b"--- ", b"+++ ")):
                in_hunk = False
            if in_hunk and line.startswith(b" "):
                ending = b"\r\n" if line.endswith(b"\r\n") else b"\n" if line.endswith(b"\n") else b""
                body = line[:-len(ending)] if ending else line
                lines[index] = body + b" __DS41_N2_CONTEXT_MISMATCH__" + ending
                patch.write_bytes(b"".join(lines))
                return
        raise AssertionError("selected real patch has no hunk context line")

    def _mutate_diff_path(self, patch_root, name):
        patch = Path(patch_root) / name
        lines = patch.read_bytes().splitlines(keepends=True)
        for index, line in enumerate(lines):
            if not line.startswith((b"--- ", b"+++ ")):
                continue
            ending = b"\r\n" if line.endswith(b"\r\n") else b"\n" if line.endswith(b"\n") else b""
            body = line[:-len(ending)] if ending else line
            old_path, separator, suffix = body[4:].partition(b"\t")
            if old_path == b"/dev/null":
                continue
            side = b"a" if line.startswith(b"--- ") else b"b"
            lines[index] = body[:4] + side + b"/../../escape" + separator + suffix + ending
            patch.write_bytes(b"".join(lines))
            return
        raise AssertionError("selected real patch has no file header")

    def _copy_download_view(self, destination, components, omit=None, corrupt=None):
        destination = Path(destination)
        destination.mkdir()
        for component in components:
            if component == omit:
                continue
            pin = self.pins["archives"][component]
            source = self.downloads / pin["archive"]
            target = destination / pin["archive"]
            shutil.copyfile(source, target)
            if component == corrupt:
                with target.open("r+b") as stream:
                    first = stream.read(1)
                    if not first:
                        raise AssertionError("pinned archive copy is empty")
                    stream.seek(0)
                    stream.write(bytes((first[0] ^ 1,)))
        return destination

    def _source_check(self, package_root):
        manifest = self._manifest_module(package_root)
        digest = manifest.source_check(package_root)
        self.assertEqual(digest, _sha(ROOT / "pins" / "runtime-files.json"))
        runtime_pins = json.loads(
            (Path(package_root) / "pins" / "runtime-files.json").read_text()
        )["files"]
        self.assertIn("config/expert-placement.json", runtime_pins)
        self.assertEqual(
            sum(name.startswith("config/fp8/") for name in runtime_pins), 7
        )
        self.assertEqual(
            sum(name.startswith("tools/engram-adapter/") for name in runtime_pins), 3
        )

    def test_apply_real_archives_positive_and_source_check(self):
        with self._owned_temp("apply-positive") as temp:
            package = self._copy_package_inputs(temp / "release")
            output = package / "sources"
            self._apply_module(package).apply(
                self.downloads, output, package / "patches"
            )
            self.assertTrue((output / "sglang").is_dir())
            self.assertTrue((output / "ktransformers").is_dir())
            self._source_check(package)

    def test_prepare_real_archives_and_source_check(self):
        with self._owned_temp("prepare-positive") as temp:
            package = self._copy_package_inputs(temp / "release")
            self._prepare_module(package).prepare(package, self.downloads)
            output = package / "sources"
            self.assertTrue(
                (output / "ktransformers/third_party/llama.cpp").is_dir()
            )
            self.assertTrue(
                (output / "ktransformers/third_party/pybind11").is_dir()
            )
            self._source_check(package)

    def test_public_lock_reservation_lifecycle(self):
        module = _load_module("gpu_lock", ROOT / "scripts" / "gpu_lock.py")
        with self._owned_temp("lock") as temp:
            lock_path = temp / "GPU.lock"
            token = uuid.uuid4().hex
            record = {
                "unit": "ds41-serving-" + uuid.uuid4().hex + ".service",
                "run": str(temp / ("ds41-serving-" + uuid.uuid4().hex)),
                "token": token,
            }
            env = {
                "DS41_LOCK_FILE": str(lock_path),
                "DS41_LOCK_OWNER": "ds41-serving-tests",
            }
            reservation = module.Reservation(env)
            reservation.update("reserve", record)
            original = lock_path.read_text()
            self.assertEqual(
                original,
                env["DS41_LOCK_OWNER"] + " " + json.dumps(record, separators=(",", ":")) + "\n",
            )
            with self.assertRaisesRegex(ValueError, "GPU_LOCK_BUSY"):
                reservation.update("reserve", record)
            with self.assertRaisesRegex(ValueError, "LOCK_RELEASE_OWNERSHIP_MISMATCH"):
                reservation.update("release", dict(record, token=uuid.uuid4().hex))
            self.assertEqual(lock_path.read_text(), original)
            reservation.update("release", record)
            self.assertEqual(lock_path.read_text(), "")
            run_root = temp / "runs"
            run_root.mkdir()
            run = run_root / ("ds41-serving-" + uuid.uuid4().hex)
            run.mkdir()
            path_env = dict(env, DS41_RUN_ROOT=str(run_root))
            self.assertEqual(module.run_path(path_env, run), run.resolve())
            for index, target in enumerate([run, run_root / "ds41-serving-absent"]):
                link = run_root / ("ds41-serving-link-" + str(index))
                link.symlink_to(target, target_is_directory=True)
                with self.subTest(target_exists=target.exists()):
                    with self.assertRaisesRegex(ValueError, "RUN_PATH_INVALID"):
                        module.run_path(path_env, link)
                    self.assertTrue(link.is_symlink())
                    self.assertEqual(link.resolve(), target.resolve())
            self.assertEqual(lock_path.read_text(), "")


    def test_n1_real_patch_sha_mismatch(self):
        with self._owned_temp("n1") as temp:
            package = self._copy_package_inputs(temp / "release")
            patch_root = package / "patches"
            name = self._series(patch_root)[0]
            rows = self._manifest_rows(patch_root)
            for index, (_, row_name) in enumerate(rows):
                if row_name == name:
                    actual = rows[index][0]
                    bad_digest = "0" * 64 if actual != "0" * 64 else "f" * 64
                    rows[index] = (bad_digest, name)
                    break
            self._write_manifest_rows(patch_root, rows)
            output = package / "sources"
            with self.assertRaisesRegex(ValueError, "PATCH_SHA_MISMATCH"):
                self._apply_module(package).apply(self.downloads, output, patch_root)
            self._assert_no_output_or_staging(package, output)

    def test_n2_real_context_mismatch_cleans_staging(self):
        with self._owned_temp("n2") as temp:
            package = self._copy_package_inputs(temp / "release")
            patch_root = package / "patches"
            name = None
            for candidate in self._series(patch_root):
                try:
                    self._mutate_hunk_context(patch_root, candidate)
                    name = candidate
                    break
                except AssertionError:
                    continue
            if name is None:
                self.fail("no real patch hunk has a context line")
            self._refresh_patch_digest(patch_root, name)
            output = package / "sources"
            with self.assertRaises(subprocess.CalledProcessError):
                self._apply_module(package).apply(self.downloads, output, patch_root)
            self._assert_no_output_or_staging(package, output)

    def test_n3_empty_real_series_fails_closed(self):
        with self._owned_temp("n3") as temp:
            package = self._copy_package_inputs(temp / "release")
            patch_root = package / "patches"
            (patch_root / "series").write_text("")
            output = package / "sources"
            with self.assertRaisesRegex(ValueError, "EMPTY_SERIES"):
                self._apply_module(package).apply(self.downloads, output, patch_root)
            self._assert_no_output_or_staging(package, output)

    def test_n4_duplicate_real_series_entry_fails_closed(self):
        with self._owned_temp("n4") as temp:
            package = self._copy_package_inputs(temp / "release")
            patch_root = package / "patches"
            first = self._series(patch_root)[0]
            digest = next(d for d, name in self._manifest_rows(patch_root) if name == first)
            (patch_root / "series").write_text(first + "\n" + first + "\n")
            self._write_manifest_rows(patch_root, [(digest, first)])
            output = package / "sources"
            with self.assertRaisesRegex(ValueError, "SERIES_MANIFEST_MISMATCH"):
                self._apply_module(package).apply(self.downloads, output, patch_root)
            self._assert_no_output_or_staging(package, output)

    def test_n5_real_traversal_inputs_fail_closed(self):
        with self.subTest(input="series path"):
            with self._owned_temp("n5-series") as temp:
                package = self._copy_package_inputs(temp / "release")
                patch_root = package / "patches"
                series = self._series(patch_root)
                old_name = series[0]
                new_name = "../escape.patch"
                series[0] = new_name
                (patch_root / "series").write_text("\n".join(series) + "\n")
                rows = self._manifest_rows(patch_root)
                self._write_manifest_rows(
                    patch_root,
                    [(digest, new_name if name == old_name else name) for digest, name in rows],
                )
                output = package / "sources"
                with self.assertRaisesRegex(ValueError, "INVALID_SERIES_PATH"):
                    self._apply_module(package).apply(
                        self.downloads, output, patch_root
                    )
                self._assert_no_output_or_staging(package, output)

        with self.subTest(input="diff path"):
            with self._owned_temp("n5-diff") as temp:
                package = self._copy_package_inputs(temp / "release")
                patch_root = package / "patches"
                name = self._series(patch_root)[0]
                self._mutate_diff_path(patch_root, name)
                self._refresh_patch_digest(patch_root, name)
                output = package / "sources"
                with self.assertRaisesRegex(ValueError, "INVALID_DIFF_PATH"):
                    self._apply_module(package).apply(
                        self.downloads, output, patch_root
                    )
                self._assert_no_output_or_staging(package, output)

    def test_n6_missing_and_corrupt_real_archives_fail_closed(self):
        with self.subTest(input="missing archive"):
            with self._owned_temp("n6-missing") as temp:
                package = self._copy_package_inputs(temp / "release")
                downloads = temp / "downloads"
                downloads.mkdir()
                output = package / "sources"
                with self.assertRaisesRegex(ValueError, "MISSING_UPSTREAM_ARCHIVE"):
                    self._apply_module(package).apply(
                        downloads, output, package / "patches"
                    )
                self._assert_no_output_or_staging(package, output)

        with self.subTest(input="archive SHA mismatch"):
            with self._owned_temp("n6-sha") as temp:
                package = self._copy_package_inputs(temp / "release")
                downloads = self._copy_download_view(
                    temp / "downloads", ("sglang",), corrupt="sglang"
                )
                output = package / "sources"
                with self.assertRaisesRegex(ValueError, "UPSTREAM_SHA_MISMATCH"):
                    self._apply_module(package).apply(
                        downloads, output, package / "patches"
                    )
                self._assert_no_output_or_staging(package, output)

    def test_n7_missing_central_pin_fails_closed(self):
        with self._owned_temp("n7") as temp:
            package = self._copy_package_inputs(temp / "release")
            (package / "pins" / "upstream.json").unlink()
            output = package / "sources"
            with self.assertRaisesRegex(ValueError, "MISSING_UPSTREAM_PINS"):
                self._apply_module(package).apply(
                    self.downloads, output, package / "patches"
                )
            self._assert_no_output_or_staging(package, output)

    def test_n8_duplicate_central_pin_fails_closed(self):
        with self._owned_temp("n8") as temp:
            package = self._copy_package_inputs(temp / "release")
            pin_path = package / "pins" / "upstream.json"
            pins = json.loads(pin_path.read_text())
            pins["archives"].append(dict(pins["archives"][0]))
            pin_path.write_text(json.dumps(pins, indent=2) + "\n")
            output = package / "sources"
            with self.assertRaisesRegex(
                ValueError, "DUPLICATE_OR_UNKNOWN_UPSTREAM_COMPONENT"
            ):
                self._apply_module(package).apply(
                    self.downloads, output, package / "patches"
                )
            self._assert_no_output_or_staging(package, output)

    def test_n9_existing_output_refusal_and_prepare_cleanup(self):
        with self.subTest(input="existing output"):
            with self._owned_temp("n9-existing") as temp:
                package = self._copy_package_inputs(temp / "release")
                output = package / "sources"
                output.mkdir()
                sentinel = output / "keep.txt"
                sentinel.write_text("pre-existing output\n")
                with self.assertRaisesRegex(ValueError, "OUTPUT_ALREADY_EXISTS"):
                    self._apply_module(package).apply(
                        self.downloads, output, package / "patches"
                    )
                self.assertEqual(sentinel.read_text(), "pre-existing output\n")
                self.assertEqual(list(package.glob(".sources.staging-*")), [])

        with self.subTest(input="dependency failure after patching"):
            with self._owned_temp("n9-cleanup") as temp:
                package = self._copy_package_inputs(temp / "release")
                downloads = self._copy_download_view(
                    temp / "downloads",
                    PATCH_COMPONENTS + ("llama",),
                    omit="pybind11",
                )
                output = package / "sources"
                with self.assertRaisesRegex(ValueError, "MISSING_UPSTREAM_ARCHIVE"):
                    self._prepare_module(package).prepare(package, downloads)
                self._assert_no_output_or_staging(package, output)


if __name__ == "__main__":
    unittest.main(verbosity=2)
