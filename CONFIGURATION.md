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

The single build-manifest.json stores the SHA256 of pins/runtime-files.json after verifying its 81 entries: 63 source files, seven FP8 files, three adapter files, placement and seven runtime helpers. It also binds the actual interpreter hash/ABI and both native ELF hashes. Receipt regeneration cannot authorize changed source pins.

The historical K22b WSL run passed 18 offline archive/runtime-configuration tests against the seven-patch series and 80-pin set. With genuine CPython 3.12.11 and recorded native artifacts, it compared 93 oracle environment entries, including the additional checkpoint-source marker, plus the permitted port setting and 74 command arguments. This establishes the tested offline resolution, not a new native build or running service. Static interface and actual print-path workspace counterchecks passed.

Fixed properties of the recorded profile are `SGLANG_NUMA_BIND_V2=0`, `KT_NUMA_NODES=0,1`, AVX2 KT backend/kernel variant, Engram nvme mode/cache 8 GiB, CUDA architectures 12.0/12.0a, service MemoryMax 480G/Swap 0 and NUMA nodes 0/1. Preflight requires 465 GiB available host memory; stop conditions are 60 GiB global, 2 GiB per node, 1 GiB swap growth and 460 GiB anonymous/shared memory. A host lacking either NUMA node is unsupported.

`runtime.ready` is strict JSON produced only by `scripts/verify_runtime.py create`; it binds actual dependency discovery to the current build receipt. `checksums.ok` is produced by `scripts/verify_model_shards.py`; it binds the 52 real shards to the trusted current checksum list. Both procedures and their untested positive deployment limits are documented in README.

Handoff uses `DS41_HANDOFF_LOCK=1` and `DS41_HANDOFF_FROM` pointing to a retained run under the run root. DS41_UNIT/DS41_RUN_DIR are set internally; the supervisor derives and verifies its own cgroup. Diagnostic selectors are rejected. No old configuration aliases are supplied.

The historical K22b profile selected the DK CPU package, dense MXFP8 B12X and A1 checkpoint-expert swapping (budget 2, ring 32, one stager). Shared storage and zero-copy remain off. The two A1 GPU-expert B12X flags had readers and selected resident-expert W4A16 decode while keeping streamed prefill on CUTLASS. All 12 selected extension switches had readers in that historical stage. `SGLANG_DS41_MU_A1_B12X_WORKSPACE_TOKENS` must be unset or zero; capacity follows the actual prefill chunk, falling back to 16384. Nonzero overrides are rejected. The preceding K22 stage lacked these GPU-expert readers. `A1_SOURCE=ckpt` is an additional visible marker for the hardcoded checkpoint reader. See README for the complete profile and limits.

Historical K22b verification record (product code at v3.1.1-k22b): the final archive passed 18 tests in 27.895 s (k22b-final-real-tests-v2-tests.log:509,511). The static interface check found 12 selected readers and detected the removed-reader and state-key regression controls (k22b-final-check_k22b_interfaces_v1.py.log:1). The actual print path accepted the default and zero workspace settings and rejected half-chunk, double-chunk and invalid overrides (k22b-final-check_k22b_workspace_v1.py.log:1). These additional verification scripts and evidence logs are internal and are not published. Native rebuilding, GPU inference and live-service operation remain untested; no pass for those paths is implied.

B10-v6 current-stage evidence: the first 18 offline tests passed in 28.133 s against eight patches and 81 runtime pins (63 source files). The independent B10 oracle retains 93 environment entries plus the permitted port and 74 command arguments; only the selected kernel value changes from 1 to 3 relative to K22b. Static interface checks found 14 readers and detected the removed-reader/state-key controls. The actual print path accepted default/zero workspace settings and rejected half-chunk/double-chunk/invalid overrides. These additional verification scripts and logs are internal and are not published. Native rebuilding, GPU inference and live service remain untested; no pass is implied.

B10 selects `KT_DS41_MU_MXFP4_KERNEL=3` with E8M0=1, retaining the K22b GPU expert and workspace settings. Its 14 selected extension switches have static source readers. Inherited DK selectors retain readers but their dispatch requires kernel1; they do not select kernel3. The tempo build omits compile macro `K2P_TRACE`. No memory, placement or command-argument change is selected.
