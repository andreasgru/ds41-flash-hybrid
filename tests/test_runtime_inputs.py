"""Public CPU regressions using the real pinned release inputs.

The suite creates private copies of actual supplied inputs and exercises the
normal command-resolution path without starting a model or service.
"""
import getpass
import hashlib
import errno
import importlib.util
import json
import os
import re
import shutil
import stat
import subprocess
import tempfile
import unittest
import uuid
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ORACLE = ROOT / "tests" / "data" / "recorded-r3.json"
TEMP_PREFIX = "ds41-real-runtime-"
PUBLIC_ENV_FILTER = re.compile(
    r"^(KT_|DSV41_|SGLANG_|CUDA_|FLASHINFER_|TORCH_|TORCHINDUCTOR_|TRITON_|"
    r"OMP_|HOME$|XDG_|HF_HOME$|HF_HUB_OFFLINE$|TMPDIR$|"
    r"PYTHONPYCACHEPREFIX$|PYTHONPATH$|LD_LIBRARY_PATH$)"
)
REQUIRED_ARCHIVE_COMPONENTS = {"sglang", "ktransformers", "llama", "pybind11"}


def _load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"MODULE_UNAVAILABLE:{path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _required_path(name, *, executable=False, regular=False):
    raw = os.environ.get(name)
    if not raw:
        raise RuntimeError(f"REQUIRED_REAL_INPUT_MISSING:{name}")
    candidate = Path(raw).expanduser()
    if regular and candidate.is_symlink():
        raise RuntimeError(f"REQUIRED_REAL_FILE_INVALID:{name}")
    path = candidate.resolve(strict=True)
    if not path.is_file():
        raise RuntimeError(f"REQUIRED_REAL_FILE_INVALID:{name}")
    if executable and not os.access(path, os.X_OK):
        raise RuntimeError(f"REQUIRED_REAL_EXECUTABLE_INVALID:{name}")
    return path


def _paths_overlap(left, right):
    return left == right or left in right.parents or right in left.parents


def _expand(value, substitutions):
    if isinstance(value, str):
        result = value
        for name, replacement in substitutions.items():
            result = result.replace("${" + name + "}", replacement)
        if "${" in result:
            raise AssertionError(f"UNKNOWN_ORACLE_SUBSTITUTION:{result}")
        return result
    if isinstance(value, list):
        return [_expand(item, substitutions) for item in value]
    if isinstance(value, dict):
        return {key: _expand(item, substitutions) for key, item in value.items()}
    return value


def _replace_private_file(path, replacement):
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise AssertionError(f"MUTATION_TARGET_INVALID:{path}")
    temporary = path.with_name(path.name + ".private-" + uuid.uuid4().hex)
    mode = stat.S_IMODE(path.stat().st_mode)
    with temporary.open("xb") as stream:
        stream.write(replacement)
    temporary.chmod(mode)
    os.replace(temporary, path)


def _linked_copy(source, destination):
    shutil.copytree(source, destination, symlinks=True, copy_function=os.link)


def _link_or_copy(source, destination):
    try:
        os.link(source, destination)
    except OSError as exc:
        if exc.errno != errno.EXDEV:
            raise
        shutil.copy2(source, destination)


class RealRuntimeInputTests(unittest.TestCase):
    """Run real release CLIs against caller-supplied pinned inputs."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.release = ROOT.resolve(strict=True)
        if not (cls.release / "scripts" / "prepare_sources.py").is_file():
            raise RuntimeError("RELEASE_TEST_FILE_MUST_BE_INSTALLED_UNDER_RELEASE_TESTS")
        cls.python = _required_path("DS41_TEST_PYTHON", executable=True)
        cls.kt_extension = _required_path("DS41_TEST_KT_EXTENSION", regular=True)
        cls.row_store = _required_path("DS41_TEST_ROW_STORE", regular=True)
        raw_downloads = os.environ.get("DS41_TEST_DOWNLOADS")
        if not raw_downloads:
            raise RuntimeError("REQUIRED_REAL_INPUT_MISSING:DS41_TEST_DOWNLOADS")
        downloads_candidate = Path(raw_downloads).expanduser()
        if downloads_candidate.is_symlink() or not downloads_candidate.is_dir():
            raise RuntimeError("REQUIRED_PINNED_DOWNLOAD_DIRECTORY_INVALID:DS41_TEST_DOWNLOADS")
        cls.downloads = downloads_candidate.resolve(strict=True)
        if not ORACLE.is_file() or ORACLE.is_symlink():
            raise RuntimeError(f"INDEPENDENT_RECORDED_ORACLE_MISSING:{ORACLE}")

        cls.oracle = json.loads(ORACLE.read_text(encoding="utf-8"))
        if cls.oracle.get("schema") != 1:
            raise RuntimeError("RECORDED_ORACLE_SCHEMA_INVALID")
        if cls.oracle.get("substitutions") != ["ROOT", "MODEL", "PYTHON"]:
            raise RuntimeError("RECORDED_ORACLE_SUBSTITUTIONS_INVALID")
        if len(cls.oracle.get("environment", {})) != 80:
            raise RuntimeError("RECORDED_ORACLE_ENVIRONMENT_COUNT_INVALID")
        if len(cls.oracle.get("command", [])) != 74:
            raise RuntimeError("RECORDED_ORACLE_COMMAND_COUNT_INVALID")
        if cls.oracle.get("allowed_extra_environment") != {"SGLANG_PORT": "18081"}:
            raise RuntimeError("RECORDED_ORACLE_ALLOWED_EXTRA_INVALID")

        cls.temp_parent = Path(tempfile.gettempdir()).resolve(strict=True)
        if (
            cls.temp_parent == cls.release
            or cls.release in cls.temp_parent.parents
            or cls.temp_parent == cls.downloads
            or cls.downloads in cls.temp_parent.parents
        ):
            raise RuntimeError("TEMPORARY_PARENT_OVERLAPS_RELEASE_OR_DOWNLOADS")
        cls.temp_context = tempfile.TemporaryDirectory(
            prefix=TEMP_PREFIX, dir=cls.temp_parent
        )
        cls.work = Path(cls.temp_context.name).resolve(strict=True)
        cls.addClassCleanup(cls.temp_context.cleanup)
        if _paths_overlap(cls.work, cls.release) or _paths_overlap(
            cls.work, cls.downloads
        ):
            raise RuntimeError("TEMPORARY_WORK_OVERLAPS_RELEASE_OR_DOWNLOADS")

        cls.install = cls.work / "prepared-install"
        shutil.copytree(cls.release, cls.install, symlinks=True)
        if os.path.lexists(cls.install / "sources"):
            raise RuntimeError("RELEASE_COPY_ALREADY_HAS_SOURCES")
        if os.path.lexists(cls.install / "build-manifest.json"):
            raise RuntimeError("RELEASE_COPY_ALREADY_HAS_BUILD_MANIFEST")

        cls.apply_series = _load_module(
            cls.install / "patches" / "apply-series.py", "runtime_apply_series"
        )
        cls.upstream_pins = cls.apply_series.load_pins(
            cls.install / "pins" / "upstream.json"
        )
        cls.required_components = tuple(
            cls.upstream_pins["source_sets"]["patch_sources"]
        ) + tuple(
            item["component"]
            for item in cls.upstream_pins["source_sets"]["dependencies"]
        )
        if (
            len(cls.required_components) != 4
            or set(cls.required_components) != REQUIRED_ARCHIVE_COMPONENTS
        ):
            raise RuntimeError("FOUR_REQUIRED_PINNED_ARCHIVES_INVALID")
        for component in cls.required_components:
            archive = cls.downloads / cls.upstream_pins["archives"][component]["archive"]
            if archive.is_symlink() or not archive.is_file():
                raise RuntimeError(f"REQUIRED_PINNED_ARCHIVE_MISSING:{component}")

        cls._run(
            [
                str(cls.python),
                str(cls.install / "scripts" / "prepare_sources.py"),
                "--root",
                str(cls.install),
                "--downloads",
                str(cls.downloads),
            ],
            cwd=cls.install,
            timeout=900,
            check=True,
        )

        suffix_result = cls._run(
            [
                str(cls.python),
                "-I",
                "-c",
                "import sysconfig; print(sysconfig.get_config_var('EXT_SUFFIX') or '')",
            ],
            cwd=cls.install,
            timeout=15,
            check=True,
        )
        cls.extension_suffix = suffix_result.stdout.strip()
        if not cls.extension_suffix or "/" in cls.extension_suffix:
            raise RuntimeError("TARGET_PYTHON_ABI_SUFFIX_INVALID")

        extension_target = (
            cls.install / "package" / "kt_kernel" / ("kt_kernel_ext" + cls.extension_suffix)
        )
        row_store_target = cls.install / "tools" / "engram-adapter" / "librow_store.so"
        if os.path.lexists(extension_target) or os.path.lexists(row_store_target):
            raise RuntimeError("NATIVE_ARTIFACT_TARGET_ALREADY_EXISTS")
        extension_target.parent.mkdir(parents=True, exist_ok=True)
        row_store_target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(cls.kt_extension, extension_target)
        shutil.copy2(cls.row_store, row_store_target)

        cls._run(
            [
                str(cls.python),
                str(cls.install / "scripts" / "build_manifest.py"),
                "create",
                "--root",
                str(cls.install),
                "--python",
                str(cls.python),
            ],
            cwd=cls.install,
            timeout=60,
            check=True,
        )

    @classmethod
    def _run(cls, command, *, cwd, timeout, check=False, env=None):
        result = subprocess.run(
            command,
            cwd=cwd,
            env=env if env is not None else {"PATH": os.defpath, "LC_ALL": "C", "TMPDIR": str(cls.work), "PYTHONDONTWRITEBYTECODE": "1"},
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        if check and result.returncode != 0:
            raise AssertionError(
                f"REAL_CLI_FAILED:{command[0]}:{result.returncode}\n"
                f"stdout={result.stdout}\nstderr={result.stderr}"
            )
        return result

    @classmethod
    def _launch_environment(cls, root):
        root = Path(root).resolve(strict=True)
        return {
            "PATH": os.defpath,
            "LC_ALL": "C",
            "DS41_ROOT": str(root),
            "DS41_MODEL_DIR": str(root / "model"),
            "DS41_RUN_ROOT": str(root / "runs"),
            "DS41_PYTHON": str(cls.python),
            "DS41_CACHE_ROOT": str(root / "cache"),
            "DS41_TMP_ROOT": str(root / "tmp"),
            "DS41_CUDA_HOME": "/usr/local/cuda-13.3",
            "DS41_GPU_DEVICE": "0",
            "DS41_SERVICE_USER": getpass.getuser(),
            "DS41_LOCK_FILE": str(root / "state" / "GPU.lock"),
            "DS41_LOCK_OWNER": "runtime-test-owner",
            "DS41_PLACEMENT": str(root / "config" / "expert-placement.json"),
            "DS41_BIND_HOST": "127.0.0.1",
            "SGLANG_PORT": "18081",
        }

    @classmethod
    def _print_command(cls, root):
        root = Path(root).resolve(strict=True)
        return cls._run(
            ["/bin/bash", str(root / "scripts" / "start-standard.sh"), "--print-command"],
            cwd=root,
            env=cls._launch_environment(root),
            timeout=30,
        )

    @classmethod
    def _expected_record(cls, root):
        root = str(Path(root).resolve(strict=True))
        model = str(Path(root) / "model")
        python = str(cls.python)
        substitutions = {"ROOT": root, "MODEL": model, "PYTHON": python}
        expected_environment = _expand(cls.oracle["environment"], substitutions)
        expected_environment.update(cls.oracle["allowed_extra_environment"])
        expected_command = _expand(cls.oracle["command"], substitutions)
        return expected_environment, expected_command

    @classmethod
    def _public_record_matches(cls, result, root):
        if not isinstance(result, dict):
            return False
        expected_environment, expected_command = cls._expected_record(root)
        environment = result.get("environment")
        if not isinstance(environment, dict):
            return False
        filtered_environment = {
            key: value
            for key, value in environment.items()
            if PUBLIC_ENV_FILTER.match(key)
        }
        return (
            filtered_environment == expected_environment
            and result.get("command") == expected_command
        )

    def test_recorded_r3_environment_and_command_match(self):
        result = self._print_command(self.install)
        self.assertEqual(result.returncode, 0, result.stderr)
        actual = json.loads(result.stdout)
        expected_environment, expected_command = self._expected_record(self.install)
        filtered_environment = {
            key: value
            for key, value in actual["environment"].items()
            if PUBLIC_ENV_FILTER.match(key)
        }
        self.assertEqual(filtered_environment, expected_environment, {k:(filtered_environment.get(k),expected_environment.get(k)) for k in set(filtered_environment)|set(expected_environment) if filtered_environment.get(k)!=expected_environment.get(k)})
        self.assertEqual(actual["command"], expected_command)

    def test_dir_export_mutant_is_detected_against_independent_oracle(self):
        baseline = self._print_command(self.install)
        self.assertEqual(baseline.returncode, 0, baseline.stderr)
        self.assertTrue(self._public_record_matches(json.loads(baseline.stdout), self.install))

        with tempfile.TemporaryDirectory(
            prefix=TEMP_PREFIX + "dir-mutant-", dir=self.temp_parent
        ) as folder:
            mutant_root = Path(folder) / "release"
            _linked_copy(self.install, mutant_root)
            key = "DSV41_ENGRAM_DIR"
            self.assertIn(key, self.oracle["environment"])
            python_pattern = re.compile(
                rf"(?P<quote>['\"])(?P<key>{re.escape(key)})(?P=quote)(?P<separator>\s*:)"
            )
            shell_pattern = re.compile(
                rf"(?<![A-Za-z0-9_])(?P<key>{re.escape(key)})(?=\s*=)"
            )
            producer_matches = []
            for candidate in (mutant_root / "scripts").rglob("*"):
                if candidate.suffix not in (".py", ".sh") or candidate.is_symlink():
                    continue
                text = candidate.read_text(encoding="utf-8")
                for producer_pattern in (python_pattern, shell_pattern):
                    for match in producer_pattern.finditer(text):
                        producer_matches.append((candidate, text, match))
            self.assertEqual(
                len(producer_matches),
                1,
                "expected one direct producer mapping for the oracle DIR key",
            )
            producer, text, match = producer_matches[0]
            target = "'DSV41_ENGRAM_DIR':env['DS41_ENGRAM_DIR'],"
            self.assertEqual(text.count(target), 1)
            mutated_text = text.replace(target, '', 1)
            _replace_private_file(producer, mutated_text.encode("utf-8"))
            pin_path = mutant_root / "pins" / "runtime-files.json"
            pins = json.loads(pin_path.read_text())
            producer_key = producer.relative_to(mutant_root).as_posix()
            self.assertIn(producer_key, pins["files"])
            pins["files"][producer_key] = hashlib.sha256(producer.read_bytes()).hexdigest()
            _replace_private_file(pin_path, (json.dumps(pins, indent=2) + "\n").encode())
            (mutant_root / "build-manifest.json").unlink()
            receipt = self._run([str(self.python), "-B", str(mutant_root / "scripts" / "build_manifest.py"), "create", "--root", str(mutant_root), "--python", str(self.python)], cwd=mutant_root, timeout=30)
            self.assertEqual(receipt.returncode, 0, receipt.stderr)

            result = self._print_command(mutant_root)
            # A syntax failure or unrelated CLI error does not count as detecting
            # the missing export: the real producer must still resolve normally.
            self.assertEqual(result.returncode, 0, result.stderr)
            actual = json.loads(result.stdout)
            self.assertNotIn(key, actual['environment'])
            self.assertFalse(self._public_record_matches(actual, mutant_root))

    def test_real_source_and_native_byte_mutants_are_rejected(self):
        manifest = _load_module(
            self.install / "scripts" / "build_manifest.py", "runtime_build_manifest"
        )
        with self.assertRaisesRegex(ValueError, "MANIFEST_PATH_INVALID"):
            manifest.relative(self.install, "../outside")

        native_name = (
            "package/kt_kernel/kt_kernel_ext" + self.extension_suffix
        )
        native_path = self.install / native_name
        symlink_path = self.install / "manifest-real-artifact-link"
        symlink_path.symlink_to(native_path)
        with self.assertRaisesRegex(ValueError, "MANIFEST_FILE_MISSING_OR_SYMLINK"):
            manifest.relative(self.install, symlink_path.name)
        symlink_path.unlink()

        runtime_pins = json.loads(
            (self.install / "pins" / "runtime-files.json").read_text(encoding="utf-8")
        )["files"]
        source_name = next(name for name in sorted(runtime_pins) if name.startswith("sources/"))

        for mutant_kind, relative_name, marker in (
            ("source", source_name, "SOURCE_SHA_MISMATCH"),
            ("native", native_name, "BUILD_MANIFEST_MISMATCH"),
        ):
            with self.subTest(mutant=mutant_kind), tempfile.TemporaryDirectory(
                prefix=TEMP_PREFIX + mutant_kind + "-mutant-", dir=self.temp_parent
            ) as folder:
                mutant_root = Path(folder) / "release"
                _linked_copy(self.install, mutant_root)
                target = mutant_root / relative_name
                original = target.read_bytes()
                self.assertTrue(original, f"real {mutant_kind} input is empty")
                changed = bytearray(original)
                changed[-1] ^= 1
                _replace_private_file(target, bytes(changed))
                result = self._print_command(mutant_root)
                self.assertNotEqual(result.returncode, 0, result.stdout)
                self.assertIn(marker, result.stderr)

    def test_warmup_helper_accepts_loopback_and_rejects_invalid_urls(self):
        warmup = _load_module(self.install / "scripts" / "warmup.py", "runtime_warmup")
        self.assertEqual(warmup.local_base("http://127.0.0.1:18081"), "http://127.0.0.1:18081")
        self.assertEqual(warmup.local_base("http://[::1]:18081/"), "http://[::1]:18081")
        for url in (
            "https://127.0.0.1:18081",
            "http://example.invalid:18081",
            "http://127.0.0.1",
            "http://127.0.0.1:65536",
            "http://user@127.0.0.1:18081",
            "http://127.0.0.1:18081/tokenize",
        ):
            with self.subTest(url=url), self.assertRaises(ValueError):
                warmup.local_base(url)

    def test_lock_producer_preserves_foreign_record_without_service(self):
        lock = _load_module(self.install / "scripts" / "gpu_lock.py", "runtime_gpu_lock")
        with tempfile.TemporaryDirectory(
            prefix=TEMP_PREFIX + "lock-", dir=self.temp_parent
        ) as folder:
            lock_path = Path(folder) / "state" / "GPU.lock"
            env = {
                "DS41_LOCK_FILE": str(lock_path),
                "DS41_LOCK_OWNER": "runtime-test-owner",
            }
            own = {
                "unit": "ds41-serving-" + uuid.uuid4().hex + ".service",
                "run": str(Path(folder) / "runs" / uuid.uuid4().hex),
                "token": uuid.uuid4().hex,
            }
            reservation = lock.Reservation(env)
            reservation.update("reserve", own)
            with self.assertRaisesRegex(ValueError, "GPU_LOCK_BUSY"):
                reservation.update("reserve", own)
            with self.assertRaisesRegex(ValueError, "LOCK_RELEASE_OWNERSHIP_MISMATCH"):
                reservation.update("release", dict(own, token=uuid.uuid4().hex))

            # Obtain the foreign record bytes from the same genuine producer,
            # rather than fabricating a shared-lock line or replacing a service.
            foreign_path = Path(folder) / "other-state" / "GPU.lock"
            foreign_env = dict(env, DS41_LOCK_FILE=str(foreign_path), DS41_LOCK_OWNER='other-owner')
            foreign = dict(own, unit='ds41-serving-'+uuid.uuid4().hex+'.service', token=uuid.uuid4().hex)
            lock.Reservation(foreign_env).update('reserve', foreign)
            foreign_bytes = foreign_path.read_bytes()
            with lock_path.open('ab') as stream:
                stream.write(foreign_bytes)
            reservation.update('release', own)
            self.assertEqual(lock_path.read_bytes(), foreign_bytes)

    def test_missing_real_dependency_archive_cleans_private_transaction(self):
        with (
            tempfile.TemporaryDirectory(
                prefix=TEMP_PREFIX + "missing-archive-", dir=self.temp_parent
            ) as download_folder,
            tempfile.TemporaryDirectory(
                prefix=TEMP_PREFIX + "archive-failure-", dir=self.temp_parent
            ) as release_folder,
        ):
            partial_downloads = Path(download_folder)
            fresh_root = Path(release_folder) / "release"
            shutil.copytree(self.release, fresh_root, symlinks=True)
            for component in self.required_components:
                if component == "pybind11":
                    continue
                archive = self.downloads / self.upstream_pins["archives"][component]["archive"]
                _link_or_copy(archive, partial_downloads / archive.name)

            result = self._run(
                [
                    str(self.python),
                    str(fresh_root / "scripts" / "prepare_sources.py"),
                    "--root",
                    str(fresh_root),
                    "--downloads",
                    str(partial_downloads),
                ],
                cwd=fresh_root,
                timeout=900,
            )
            self.assertNotEqual(result.returncode, 0, result.stdout)
            self.assertIn("MISSING_UPSTREAM_ARCHIVE", result.stderr)
            self.assertFalse(os.path.lexists(fresh_root / "sources"))
            self.assertEqual(list(fresh_root.glob(".sources.staging-*")), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
