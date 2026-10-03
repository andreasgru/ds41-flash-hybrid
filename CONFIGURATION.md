# Configuration

All path inputs require absolute paths. The repository name is `ds41-flash-hybrid`.

| Key | Default / requirement |
|---|---|
| DS41_ROOT | Parent of scripts directory |
| DS41_MODEL_DIR | Required external model directory with trusted SHA256SUMS |
| DS41_PYTHON | Root/venv/bin/python; an external compatible interpreter may be configured |
| DS41_ENGRAM_DIR | Root/engram |
| DS41_RUN_ROOT | Root/runs |
| DS41_CACHE_ROOT | Root/cache |
| DS41_TMP_ROOT | Root/tmp |
| DS41_CUDA_HOME | /usr/local/cuda-13.3 |
| DS41_GPU_DEVICE | Ordinal 0 |
| DS41_SERVICE_USER | Current user |
| DS41_LOCK_FILE | Root/state/GPU.lock |
| DS41_LOCK_OWNER | ds41-serving |
| DS41_PLACEMENT | Root/config/expert-placement.json; full content pin required |
| DS41_BIND_HOST | 127.0.0.1; numeric 127/8 or ::1 only |
| SGLANG_PORT | 18081; integer 1..65535 |

`DSV41_ENGRAM_DIR` resolves from `DS41_ENGRAM_DIR`; `DSV41_ENGRAM_BASE` is the external model directory. The adapter reads `engram-manifest.json` in the Engram directory. The shipped header/offset producer is documented in README. HiCache remains disabled; optional RAM/NUMA adapter modes are outside this standard profile.

The single build-manifest.json stores the SHA256 of pins/runtime-files.json after verifying its 61 entries: 43 source files, seven FP8 files, three adapter files, placement and seven runtime helpers. It also binds the actual interpreter hash/ABI and both native ELF hashes. Receipt regeneration cannot authorize changed source pins.

Fixed properties of the recorded profile are `SGLANG_NUMA_BIND_V2=0`, `KT_NUMA_NODES=0,1`, AVX2 KT backend/kernel variant, Engram nvme mode/cache 8 GiB, CUDA architectures 12.0/12.0a, service MemoryMax 360G/Swap 0 and NUMA nodes 0/1. Preflight requires 420 GiB available host memory; stop conditions are 60 GiB global, 2 GiB per node, 1 GiB swap growth and 340 GiB anonymous/shared memory. A host lacking either NUMA node is unsupported.

`runtime.ready` is strict JSON produced only by `scripts/verify_runtime.py create`; it binds actual dependency discovery to the current build receipt. `checksums.ok` is produced by `scripts/verify_model_shards.py`; it binds the 52 real shards to the trusted current checksum list. Both procedures and their untested positive deployment limits are documented in README.

Handoff uses `DS41_HANDOFF_LOCK=1` and `DS41_HANDOFF_FROM` pointing to a retained run under the run root. DS41_UNIT/DS41_RUN_DIR are set internally; the supervisor derives and verifies its own cgroup. Diagnostic selectors are rejected. No old configuration aliases are supplied.
