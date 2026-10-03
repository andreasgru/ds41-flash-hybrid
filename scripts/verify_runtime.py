#!/usr/bin/env python3
"""Create and validate the runtime dependency receipt without importing packages."""
import argparse
import hashlib
import importlib.util
import json
import os
import re
import stat
import subprocess
import sys
from pathlib import Path

SCHEMA = 1
STATUS = 'RUNTIME_READY'
MODULES = ('torch', 'triton', 'flashinfer', 'safetensors', 'transformers', 'sglang', 'kt_kernel')
_SHA256 = re.compile(r'[0-9a-f]{64}')
_DISCOVERY = '''
import importlib.machinery, json, sys
names = ('torch', 'triton', 'flashinfer', 'safetensors', 'transformers', 'sglang', 'kt_kernel')
inventory = {}
for name in names:
    spec = importlib.machinery.PathFinder.find_spec(name, sys.path)
    if spec is None:
        inventory[name] = {'found': False, 'origin': None, 'locations': []}
    else:
        locations = list(spec.submodule_search_locations or ())
        inventory[name] = {
            'found': True,
            'origin': spec.origin if isinstance(spec.origin, str) else None,
            'locations': [str(location) for location in locations],
        }
print(json.dumps(inventory, separators=(',', ':')))
'''


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('JSON_DUPLICATE_KEY')
        result[key] = value
    return result


def _reject_constant(value):
    raise ValueError('JSON_CONSTANT_INVALID')


def _json_bytes(raw, error):
    try:
        return json.loads(raw.decode('utf-8'), object_pairs_hook=_unique_object,
                          parse_constant=_reject_constant)
    except (UnicodeDecodeError, ValueError) as exc:
        raise ValueError(error) from exc


def _root_path(root):
    try:
        path = Path(root).resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise ValueError('RUNTIME_ROOT_INVALID') from exc
    if not path.is_dir():
        raise ValueError('RUNTIME_ROOT_INVALID')
    return path


def _read_regular(path, error):
    try:
        fd = os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0))
    except OSError as exc:
        raise ValueError(error) from exc
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise ValueError(error)
        with os.fdopen(fd, 'rb') as stream:
            fd = -1
            return stream.read()
    finally:
        if fd >= 0:
            os.close(fd)


def _load_script(root, name):
    path = root / 'scripts' / (name + '.py')
    try:
        info = path.lstat()
    except OSError as exc:
        raise ValueError('RUNTIME_SCRIPT_UNAVAILABLE') from exc
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
        raise ValueError('RUNTIME_SCRIPT_UNAVAILABLE')
    spec = importlib.util.spec_from_file_location('_runtime_' + name, path)
    if spec is None or spec.loader is None:
        raise ValueError('RUNTIME_SCRIPT_UNAVAILABLE')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _ensure_absent(path):
    try:
        info = path.lstat()
    except FileNotFoundError:
        return
    except OSError as exc:
        raise ValueError('RUNTIME_READY_PATH_UNAVAILABLE') from exc
    if stat.S_ISLNK(info.st_mode):
        raise ValueError('RUNTIME_READY_SYMLINK')
    raise ValueError('RUNTIME_READY_ALREADY_EXISTS')


def _validate_modules(modules):
    if type(modules) is not dict or set(modules) != set(MODULES):
        raise ValueError('RUNTIME_MODULE_INVENTORY_INVALID')
    for name in MODULES:
        item = modules[name]
        if type(item) is not dict or set(item) != {'found', 'origin', 'locations'}:
            raise ValueError('RUNTIME_MODULE_INVENTORY_INVALID')
        if item['found'] is not True:
            raise ValueError('RUNTIME_MODULES_MISSING:' + name)
        origin, locations = item['origin'], item['locations']
        if origin is not None and (not isinstance(origin, str) or not origin or '\x00' in origin):
            raise ValueError('RUNTIME_MODULE_INVENTORY_INVALID')
        if type(locations) is not list or any(not isinstance(p, str) or not p or '\x00' in p for p in locations):
            raise ValueError('RUNTIME_MODULE_INVENTORY_INVALID')
        if len(locations) != len(set(locations)) or (origin is None and not locations):
            raise ValueError('RUNTIME_MODULE_INVENTORY_INVALID')


def _validate_receipt(value, manifest_sha256):
    if type(value) is not dict or set(value) != {'schema', 'status', 'build_manifest_sha256', 'modules'}:
        raise ValueError('RUNTIME_READY_SCHEMA_INVALID')
    if type(value['schema']) is not int or value['schema'] != SCHEMA or value['status'] != STATUS:
        raise ValueError('RUNTIME_READY_SCHEMA_INVALID')
    digest = value['build_manifest_sha256']
    if not isinstance(digest, str) or not _SHA256.fullmatch(digest):
        raise ValueError('RUNTIME_READY_SHA_INVALID')
    if digest != manifest_sha256:
        raise ValueError('RUNTIME_READY_STALE')
    _validate_modules(value['modules'])
    return value


def validate_runtime(root):
    """Return the validated receipt or raise ValueError; never follows receipt symlinks."""
    root = _root_path(root)
    ready = _read_regular(root / 'runtime.ready', 'RUNTIME_READY_INVALID')
    value = _json_bytes(ready, 'RUNTIME_READY_INVALID')
    manifest = _read_regular(root / 'build-manifest.json', 'BUILD_MANIFEST_INVALID')
    return _validate_receipt(value, hashlib.sha256(manifest).hexdigest())


def _discover_modules(python, environment, root):
    if not isinstance(environment.get('PYTHONPATH'), str):
        raise ValueError('RUNTIME_PYTHONPATH_MISSING')
    try:
        result = subprocess.run([python, '-B', '-c', _DISCOVERY], cwd=root, env=environment,
                                check=True, capture_output=True, text=True,
                                encoding='utf-8', timeout=60)
    except (OSError, subprocess.SubprocessError) as exc:
        raise ValueError('RUNTIME_MODULE_DISCOVERY_FAILED') from exc
    inventory = _json_bytes(result.stdout.encode('utf-8'), 'RUNTIME_MODULE_DISCOVERY_INVALID')
    if type(inventory) is not dict or set(inventory) != set(MODULES):
        raise ValueError('RUNTIME_MODULE_DISCOVERY_INVALID')
    missing = [name for name in MODULES if type(inventory[name]) is not dict or inventory[name].get('found') is not True]
    if missing:
        raise ValueError('RUNTIME_MODULES_MISSING:' + ','.join(missing))
    _validate_modules(inventory)
    return inventory


def produce_runtime_ready(root, env=None):
    """Resolve the actual launch, verify its receipt, discover modules, then create once."""
    root = _root_path(root)
    marker = root / 'runtime.ready'
    _ensure_absent(marker)
    env = dict(os.environ if env is None else env)
    configured_root = env.get('DS41_ROOT')
    python = env.get('DS41_PYTHON')
    if not isinstance(configured_root, str) or Path(configured_root).resolve() != root:
        raise ValueError('RUNTIME_ROOT_MISMATCH')
    if not isinstance(python, str) or not python:
        raise ValueError('RUNTIME_PYTHON_MISSING')

    resolved = _load_script(root, 'resolve_launcher').resolve(env)
    if type(resolved) is not dict or type(resolved.get('environment')) is not dict:
        raise ValueError('RUNTIME_RESOLUTION_INVALID')
    runtime_env = resolved['environment']
    if runtime_env.get('DS41_PYTHON') != python:
        raise ValueError('RUNTIME_PYTHON_MISMATCH')
    actual_manifest = resolved.get('build_manifest')
    raw_manifest = _read_regular(root / 'build-manifest.json', 'BUILD_MANIFEST_INVALID')
    if _json_bytes(raw_manifest, 'BUILD_MANIFEST_INVALID') != actual_manifest:
        raise ValueError('BUILD_MANIFEST_MISMATCH')
    manifest_sha256 = hashlib.sha256(raw_manifest).hexdigest()
    inventory = _discover_modules(python, runtime_env, root)
    if hashlib.sha256(_read_regular(root / 'build-manifest.json', 'BUILD_MANIFEST_INVALID')).hexdigest() != manifest_sha256:
        raise ValueError('BUILD_MANIFEST_CHANGED_DURING_DISCOVERY')

    value = {'schema': SCHEMA, 'status': STATUS,
             'build_manifest_sha256': manifest_sha256, 'modules': inventory}
    _validate_receipt(value, manifest_sha256)
    _ensure_absent(marker)
    try:
        fd = os.open(marker, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_NOFOLLOW', 0), 0o644)
    except FileExistsError as exc:
        raise ValueError('RUNTIME_READY_ALREADY_EXISTS') from exc
    except OSError as exc:
        raise ValueError('RUNTIME_READY_CREATE_FAILED') from exc
    with os.fdopen(fd, 'w', encoding='utf-8', newline='\n') as stream:
        json.dump(value, stream, indent=2, sort_keys=True)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())
    return value


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=('create', 'verify'))
    parser.add_argument('--root', type=Path, required=True)
    args = parser.parse_args(argv)
    if args.mode == 'create':
        produce_runtime_ready(args.root)
        print('RUNTIME_READY_CREATED')
    else:
        validate_runtime(args.root)
        print('RUNTIME_READY_VALID')


if __name__ == '__main__':
    main()
