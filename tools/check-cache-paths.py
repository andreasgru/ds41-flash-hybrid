#!/usr/bin/env python3
"""Validate resolved cache destinations against the isolated root before imports."""
import os
import subprocess
import sys
from pathlib import Path

root = Path(os.environ['DS41_ROOT']).resolve()
cache = Path(os.environ['DS41_CACHE_ROOT']).resolve()
keys = ('HOME', 'XDG_CACHE_HOME', 'XDG_CONFIG_HOME', 'XDG_DATA_HOME', 'XDG_STATE_HOME', 'XDG_RUNTIME_DIR',
        'SGLANG_CACHE_DIR', 'TORCHINDUCTOR_CACHE_DIR', 'TRITON_CACHE_DIR',
        'FLASHINFER_WORKSPACE_BASE', 'TORCH_HOME', 'TORCH_EXTENSIONS_DIR',
        'HF_HOME', 'CUDA_CACHE_PATH', 'PYTHONPYCACHEPREFIX', 'TMPDIR')

def check(name, value, base=cache):
    path = Path(value).expanduser().resolve()
    if not path.is_relative_to(base) or path == base.parent:
        raise RuntimeError(f'CACHE_PATH_REJECTED {name}={path}')
    path.mkdir(parents=True, exist_ok=True)
    print(f'{name}={path}', flush=True)

print(subprocess.check_output(['date', '+%F %H:%M:%S'], text=True).strip())
for key in keys:
    check(key, os.environ[key], Path(os.environ['DS41_TMP_ROOT']).resolve() if key == 'TMPDIR' else cache)
Path(os.environ['XDG_RUNTIME_DIR']).chmod(0o700)
if '--resolve' in sys.argv:
    from sglang.srt.environ import envs
    check('resolved.SGLANG_CACHE_DIR', envs.SGLANG_CACHE_DIR.get())
    from flashinfer.jit import env as fi
    for key in ('FLASHINFER_CACHE_DIR', 'FLASHINFER_WORKSPACE_DIR',
                'FLASHINFER_JIT_DIR', 'FLASHINFER_GEN_SRC_DIR', 'FLASHINFER_CUBIN_DIR'):
        check('resolved.' + key, getattr(fi, key))
    from torch._inductor.runtime.runtime_utils import cache_dir
    check('resolved.TORCHINDUCTOR_CACHE_DIR', cache_dir())
    from triton.runtime.cache import get_cache_manager
    check('resolved.TRITON_CACHE_DIR', get_cache_manager('00' * 32).cache_dir)
print(f'CACHE_PATHS_OK env_count={len(keys)} outside=0')
