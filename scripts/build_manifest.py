#!/usr/bin/env python3
"""Bind installed sources and native build artifacts to a Python ABI.

Origin: own implementation. License: Apache-2.0.
No GPU or model imports. The build creates this receipt; launch verifies it.
"""
import argparse
import hashlib
import json
import subprocess
from pathlib import Path

def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream,'sha256').hexdigest()

def relative(root, name):
    path=Path(name)
    if path.is_absolute() or '..' in path.parts or not path.parts:
        raise ValueError('MANIFEST_PATH_INVALID')
    target=root/path
    if target.is_symlink() or not target.is_file() or not target.resolve().is_relative_to(root.resolve()):
        raise ValueError('MANIFEST_FILE_MISSING_OR_SYMLINK:'+name)
    return target

def python_abi(python):
    code='import sys,sysconfig,json,platform; print(json.dumps({"cache_tag":sys.implementation.cache_tag,"extension_suffix":sysconfig.get_config_var("EXT_SUFFIX"),"machine":platform.machine(),"version":list(sys.version_info[:3])}))'
    result=subprocess.run([str(python),'-I','-c',code],check=True,capture_output=True,text=True,timeout=15)
    value=json.loads(result.stdout)
    if not value.get('extension_suffix') or value['machine']!='x86_64':
        raise ValueError('NATIVE_ABI_UNSUPPORTED')
    return value

def elf(path):
    with path.open('rb') as stream: header=stream.read(64)
    if len(header)<64 or header[:6]!=b'\x7fELF\x02\x01' or int.from_bytes(header[16:18],'little')!=3 or int.from_bytes(header[18:20],'little')!=62:
        raise ValueError('NATIVE_ELF_INVALID:'+path.name)

def source_check(root):
    pins_path=relative(root,'pins/runtime-files.json')
    pins=json.loads(pins_path.read_text())
    if pins.get('schema')!=1 or not isinstance(pins.get('files'),dict):
        raise ValueError('SOURCE_PINS_INVALID')
    files=pins['files']
    source=[p for p in files if p.startswith('sources/')]
    fp8=[p for p in files if p.startswith('config/fp8/')]
    adapter=[p for p in files if p.startswith('tools/engram-adapter/')]
    helpers={'scripts/endpoint.py','scripts/verify_model_shards.py','scripts/verify_runtime.py','scripts/supervisor.py','scripts/resolve_launcher.py','scripts/gpu_lock.py','scripts/standard-env.sh'}
    if len(source)!=43 or len(fp8)!=7 or len(adapter)!=3 or 'config/expert-placement.json' not in files or not helpers <= set(files) or len(files)!=61:
        raise ValueError('SOURCE_PIN_COVERAGE_INVALID')
    actual_fp8={str(p.relative_to(root)) for p in (root/'config/fp8').glob('N=*.json')}
    if actual_fp8!=set(fp8):
        raise ValueError('FP8_CONFIGURATION_SET_INVALID')
    for name, expected in files.items():
        if digest(relative(root,name))!=expected:
            raise ValueError('SOURCE_SHA_MISMATCH:'+name)
    return digest(pins_path)

def receipt(root, python):
    pins=source_check(root)
    abi=python_abi(python)
    names=['package/kt_kernel/kt_kernel_ext'+abi['extension_suffix'],'tools/engram-adapter/librow_store.so']
    artifacts={}
    for name in names:
        path=relative(root,name); elf(path); artifacts[name]=digest(path)
    return {'schema':1,'source_pin_sha256':pins,'python_abi':abi,
            'python_sha256':digest(Path(python).resolve()),'native_artifacts':artifacts}

def main():
    parser=argparse.ArgumentParser(); parser.add_argument('mode',choices=['create','verify'])
    parser.add_argument('--root',type=Path,required=True); parser.add_argument('--python',type=Path,required=True)
    args=parser.parse_args(); root=args.root.resolve(); result=receipt(root,args.python)
    path=root/'build-manifest.json'
    if args.mode=='create':
        with path.open('x') as stream: json.dump(result,stream,indent=2); stream.write('\n')
        print('BUILD_MANIFEST_CREATED')
    else:
        if json.loads(path.read_text())!=result: raise ValueError('BUILD_MANIFEST_MISMATCH')
        print('BUILD_MANIFEST_VERIFIED')

if __name__=='__main__': main()
