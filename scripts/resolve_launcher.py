#!/usr/bin/env python3
"""Resolve the portable live r3 command and environment without launching it.

Origin: own implementation of the selected live configuration. Apache-2.0.
Historical diagnostic builds are rejected; their artifacts are not bundled.
"""
import argparse
import importlib.util
import json
import os
from pathlib import Path

def resolve(env):
    root=Path(env['DS41_ROOT']).resolve()
    spec=importlib.util.spec_from_file_location('build_manifest',root/'scripts/build_manifest.py')
    manifest=importlib.util.module_from_spec(spec); spec.loader.exec_module(manifest)
    actual=manifest.receipt(root,Path(env['DS41_PYTHON']))
    if json.loads((root/'build-manifest.json').read_text())!=actual:
        raise ValueError('BUILD_MANIFEST_MISMATCH')
    required={'DS41_MODE':'A','DS41_FIPRE':'FULL','DS41_CB':'1','DS41_CBPKG':'multi-user',
              'DS41_FP8TREE':'1','DS41_FP8TREEDIR':'sources','DS41_CHUNK':'16384',
              'DS41_RADIX':'1','DS41_HICACHE':'0','DS41_ENGRAM_PKG':'numa'}
    if any(env.get(k)!=v for k,v in required.items()):
        raise ValueError('LIVE_CONFIGURATION_REQUIRED')
    prohibited=['DS41_STREAMB','DS41_ZDIAG','DS41_HM3TREE','DS41_HM4TREE','DS41_HM4A',
                'DS41_ROUTING_DUMP','DS41_MOETIME','DS41_ENGRAM_RAM','KT_DS41_MU_STREAM_TBUCKET',
                'SGLANG_DS41_MU_P3','SGLANG_DS41_MU_P3_TILE','SGLANG_DS41_MU_P3_SHARE',
                'SGLANG_DS41_MU_MOE_WORKSPACE_MAX_TOKENS','SGLANG_DS41_MU_OOM_TEST']
    if any(env.get(k) not in (None,'','0') for k in prohibited):
        raise ValueError('DIAGNOSTIC_CONFIGURATION_UNSUPPORTED')
    if env.get('SGLANG_DS41_MU_RADIX_F2_VALUE','0')!='0':
        raise ValueError('RADIX_VALUE_NOT_ACCEPTED')
    placement=Path(env['DS41_PLACEMENT'])
    pins=json.loads((root/'pins/runtime-files.json').read_text())['files']
    if manifest.digest(placement)!=pins['config/expert-placement.json']:
        raise ValueError('PLACEMENT_SHA_MISMATCH')
    cache=Path(env['DS41_CACHE_ROOT']); tmp=env['DS41_TMP_ROOT']
    resolved=dict(env)
    resolved.update({'CUDA_VISIBLE_DEVICES':env['DS41_GPU_DEVICE'],'CUDA_DEVICE_ORDER':'PCI_BUS_ID',
        'KT_MXFP4_BACKEND':'avx2','KT_KERNEL_CPU_VARIANT':'avx2','KT_NUMA_NODES':'0,1',
        'KT_DEFERRED_EXPERTS':'0','SGLANG_SWA_BOUNDED_REPLAY':'0','SGLANG_ENABLE_DSPARK':'0',
        'KT_GPU_STREAM_GROUP':env.get('KT_GPU_STREAM_GROUP','8'),'KT_GPU_STREAM_ZEROCOPY':'0',
        'KT_EXPERT_SHM':'0','KT_DS41_MU_CB_JOIN':'1','KT_DS41_MU_CB_JOIN_CPU':env.get('KT_DS41_MU_CB_JOIN_CPU','15'),
        'SGLANG_SM120_FLASHMLA_BACKEND':'flashinfer','SGLANG_DS41_MU_FP8_SM120_TUNED':env['DS41_FP8'],
        'SGLANG_DS41_MU_FP8_BLOCK_CONFIG_DIR':str(root/'config/fp8'),'DSV41_CACHE_GIB':'8',
        'DSV41_ENGRAM_DIR':env['DS41_ENGRAM_DIR'],'DSV41_ENGRAM_BASE':env['DS41_MODEL_DIR'],
        'SGLANG_NUMA_BIND_V2':'0','DSV41_ENGRAM_MODE':'nvme','DSV41_ENGRAM_IO_THREADS':env['DS41_ENGRAM_IO'],
        'DSV41_ENGRAM_TIMING':'1','DSV41_ENGRAM_CACHE_THP':env['DS41_ENGRAM_CACHE_THP'],
        'NCCL_P2P_DISABLE':'1','NCCL_IB_DISABLE':'1','NCCL_SHM_DISABLE':'0','NCCL_DEBUG':'WARN',
        'TORCH_CUDA_ARCH_LIST':'12.0','FLASHINFER_CUDA_ARCH_LIST':'12.0a',
        'CUDA_HOME':env['DS41_CUDA_HOME'],'TMPDIR':tmp,'XDG_CACHE_HOME':str(cache),
        'HF_HUB_OFFLINE':'1','TRANSFORMERS_OFFLINE':'1','KT_DS41_MU_EXPERT_LOCATION':str(placement),
        'PYTHONPATH':str(root/'sources/sglang/python')+':'+str(root/'tools/engram-adapter')+':'+str(root/'package'),
        'LD_LIBRARY_PATH':str(root/'sysroot/usr/lib/x86_64-linux-gnu'),
        'OMP_NUM_THREADS':env.get('KT_CPU_THREADS','28'),
        'PYTORCH_CUDA_ALLOC_CONF':'expandable_segments:True'})
    cache_paths={'HOME':'home','HF_HOME':'hf','SGLANG_CACHE_DIR':'sglang',
        'TORCHINDUCTOR_CACHE_DIR':'torch-inductor','XDG_CONFIG_HOME':'config','XDG_DATA_HOME':'data',
        'XDG_STATE_HOME':'state','XDG_RUNTIME_DIR':'runtime','TORCH_HOME':'torch',
        'TORCH_EXTENSIONS_DIR':'torch-extensions','TRITON_CACHE_DIR':'triton',
        'FLASHINFER_WORKSPACE_BASE':'flashinfer','CUDA_CACHE_PATH':'cuda','PYTHONPYCACHEPREFIX':'pycache'}
    resolved.update({key:str(cache/value) for key,value in cache_paths.items()})
    resolved['PATH']=str(Path(env['DS41_PYTHON']).parent)+':'+env['DS41_CUDA_HOME']+'/bin:'+env.get('PATH','/usr/bin:/bin')
    for key in ['GLIBC_TUNABLES','PYTORCH_ALLOC_CONF','DSV41_ENGRAM_RAM_NUMA',
                'DSV41_ENGRAM_CACHE_PREFAULT','DSV41_ENGRAM_RAM_THREADS','SGLANG_DS41_MU_SM120_FLASHMLA_DECODE_BACKEND']:
        resolved.pop(key,None)
    command=[env['DS41_PYTHON'],'-m','sglang.launch_server','--host',env['DS41_BIND_HOST'],
        '--port',env['SGLANG_PORT'],'--model-path',env['DS41_MODEL_DIR'],'--load-format','safetensors',
        '--trust-remote-code','--served-model-name','deepseek-v41-flash-kt-tp1',
        '--tensor-parallel-size','1','--numa-node','0','--disable-custom-all-reduce',
        '--kt-weight-path',env['DS41_MODEL_DIR'],'--kt-method','MXFP4','--kt-num-gpu-experts',env.get('KT_GPU_EXPERTS','90'),
        '--init-expert-location',str(placement),'--kt-cpuinfer',env.get('KT_CPU_THREADS','28'),
        '--kt-threadpool-count','2','--kt-max-deferred-experts-per-token','0',
        '--context-length',env['SGLANG_CONTEXT_LENGTH'],'--max-total-tokens',env['SGLANG_MAX_TOTAL_TOKENS'],
        '--kv-cache-dtype','fp8_e4m3','--mem-fraction-static',env['DS41_MEMFRAC'],
        '--max-running-requests',env['SGLANG_DS41_MU_MAX_RUNNING_REQUESTS'],'--chunked-prefill-size',env['DS41_CHUNK'],
        '--max-prefill-tokens',env['DS41_CHUNK'],'--sampling-backend','pytorch',
        '--tool-call-parser','deepseekv41','--reasoning-parser','deepseek-v41',
        '--watchdog-timeout',env.get('DS41_WATCHDOG','1200'),'--swa-full-tokens-ratio',env['DS41_SWA_RATIO'],
        '--disable-shared-experts-fusion','--enable-metrics','--disable-flashinfer-autotune',
        '--cuda-graph-bs-decode',*env['DS41_GRAPH_BS'].split(),'--enable-cache-report']
    prefixes=('DS41_','KT_','DSV41_','SGLANG_','CUDA_','FLASHINFER_','TORCH_','TORCHINDUCTOR_','TRITON_','OMP_','XDG_','NCCL_','HF_','TRANSFORMERS_','PYTHON')
    public_env={k:v for k,v in resolved.items() if k.startswith(prefixes) or k in ('HOME','PATH','TMPDIR','LD_LIBRARY_PATH','PYTORCH_CUDA_ALLOC_CONF')}
    return {'command':command,'environment':public_env,'build_manifest':actual,
            'scope':'live r3 resolution; no server started'}

if __name__=='__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('--print-command',action='store_true',required=True)
    parser.parse_args(); print(json.dumps(resolve(dict(os.environ)),indent=2))
