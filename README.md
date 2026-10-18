# ds41-flash-hybrid

K22 source release candidate, tag `v3.0.0-k22`, for DeepSeek-V4.1-Flash with pinned SGLang and KTransformers. It extends the r3 source release with DK CPU decode, V2b dense MXFP8 decode and A1 expert-cache swapping. Weights, Engram data, runtime environments and native binaries are supplied separately.

**Status: source reconstruction and 18 offline real-input tests passed.** Native rebuilding, GPU execution, server startup and full workload acceptance have not been validated for this candidate. Historical measurements describe the recorded implementation, not a newly built public release.

The intended workload remains 1–2 main sessions approaching 500k tokens plus 4–6 subordinate sessions. The historical full-load run used one main and four subordinate sessions and failed five performance gates.

## K22 profile

Recorded hardware: RTX PRO 6000 Blackwell Max-Q, 96 GB; two EPYC 7302 CPUs; approximately 499 GiB host RAM visible to the operating system.

The portable profile keeps the existing placement, server options, 524,288-token context limit, 1,800,000-token pool, 16,384-token prefill chunks, 1,024-token streaming threshold, SWA/full ratio 0.0625, GPU memory fraction 0.90, 90 GPU experts, 28 CPU inference threads and at most 12 requests. Decode graph batches remain 1–12. HiCache and speculation remain disabled; NUMA nodes are 0/1.

K22 selects `DS41_CBPKG=multi-user-dk` with `KT_DS41_MU_DECODE_KERNEL=1`, `KT_DS41_MU_DECODE_PREFETCH=2048` and `KT_DS41_MU_K2EPLUS=1`. Dense FP8 operations use `SGLANG_DS41_MU_MXFP8_B12X=1`. A1 uses CACHE=1, SWAP=1, BUDGET=2, STAT_S=1, RING=32 and STAGER=1 under the `SGLANG_DS41_MU_A1_` prefix. Sources remain under `sources/` and the native package under `package/`.

The native module supports shared storage, but this profile fixes shared expert storage and zero-copy off. A1 reads checkpoint experts. `A1_SOURCE=ckpt` is exposed as an additional configuration marker; the implementation constructs the checkpoint reader directly. This marker is an explicit difference from the historical environment export. Exact environment-byte equivalence is not claimed.

**Historical limitation:** `SGLANG_DS41_MU_A1_B12X_DECODE=1` and `SGLANG_DS41_MU_A1_B12X_STREAM_CUTLASS=1` are retained but have no readers in the K22 source tree. GPU expert B12X decode is absent. This does not disable the separate, active dense MXFP8 B12X path.

The service limit is 480 GiB with no swap. Preflight requires 465 GiB available host memory. Existing stop thresholds are available memory below 60 GiB, either NUMA node below 2 GiB, swap growth above 1 GiB, or anonymous/shared memory above 460 GiB. Ownership checks and control-group cleanup remain in place. See [CONFIGURATION](CONFIGURATION.md).

## Historical K22 measurements

Two repeat runs on 14 October 2026 used the recorded K22 A1 source tree and native module. These are separate short decode and multi-prompt workloads, not full workload acceptance. Values are medians in tokens/s unless stated otherwise.

| Metric | Historical run A | Historical run B | Samples and conditions per run |
|---|---:|---:|---|
| Single-request ×20 | 52.54 | 52.78 | 20 measured repetitions + 1 warm-up; batch 1, output length 256, thinking disabled |
| Decode batch 1 | 52.91 | 53.22 | 5 measured repetitions + 1 warm-up; output length 256 |
| Decode batch 4 | 82.64 | 84.07 | Same decode protocol |
| Decode batch 8 | 166.00 | 165.17 | Same decode protocol |
| Eight-stream aligned aggregate | 119.43 | 120.27 | 10 repetitions; eight-prompt workload at batch 8 |
| 88-item quality set, correct | 76/88 | 77/88 | One complete set |
| 36-item arithmetic set, correct | 36/36 | 36/36 | One complete set |
| Recorded numerical / state checks | passed / identical | passed / identical | Run-specific checks |

The unaligned eight-stream metric was invalid because starts were offset by 5.81–6.29 seconds. The table uses the separately defined aligned aggregate. The difference between the two aligned run results was 0.84 tokens/s, approximately 0.7%; this is observed repeat-run variation, not a confidence interval. Single-request, batch-decode and aligned-stream numbers must not be interchanged. The approximately 63.4 tokens/s result from a separate experimental GPU-expert path is not a K22 production result.

## Historical v2/r3 full-load acceptance

The 28–29 September 2026 run comprised 649 requests over approximately 8 h 12 min with no reported request errors. Throughput refers to the long-context band window.

| Gate | Recorded result | Target | Sample count | Status |
|---|---:|---:|---:|---|
| Aggregate throughput in the band window | 35.11 tokens/s | ≥40 tokens/s | 649 requests | **RED** |
| Main-session TTFT p95 | 57.88 s | ≤30 s | 58 | **RED** |
| Main-session TTFT p50 | 15.745 s | ≤15 s | 58 | **RED** |
| Subordinate-session TTFT p95 | 50.21 s | ≤30 s | 244 | **RED** |
| Subordinate raw cache ratio | 96.42% | ≥98% | 243 | **RED** |

Stability passed in that historical run. Quality stages were **not run after HALT** at the load gates, including planned prompt-correctness and arithmetic checks. The separate K22 checks above do not complete those stages or turn these five gates green.

Future acceptance uses `sum(min(C,U))/sum(U)`, where C is server-reported cached input tokens and U is the token longest common prefix with the preceding prompt plus generated output for the same agent and session. Measure main and subordinate roles separately from round 2; each role must reach 98%. The historical raw ratio has not been relabeled or recomputed. See [METHODS](METHODS.md).

## Sources, preparation and build

Archive revisions, SHA256 and exact download URLs are maintained in `pins/upstream.json`. The six-patch series comprises the four r3 baseline/multi-user patches plus one K22 SGLang patch and one K22 KTransformers patch. Fresh application of all six patches reproduced 10,408 regular files and five symlink targets byte-for-byte against the derived cleaned stage. The separate edit journal reversed 56 cleaned files to their pinned original sources; three fail-closed controls passed. The runtime pin list covers 60 source files and 78 files in total. These checks establish source reconstruction and pin coverage, not native execution. FlashInfer entries record external runtime provenance and are not extracted by this series.

Own options use `SGLANG_DS41_MU_*` and `KT_DS41_MU_*`; internal identifiers use the existing neutral DS41MU naming convention. Genuine upstream and recipe interfaces retain their names.

Requirements include Linux x86_64, Bash, GNU patch/diff, CMake, Ninja, a C++ compiler, CUDA 13.3, development/sysroot libraries and a compatible Python environment with PyTorch, SGLang, FlashInfer and Triton dependencies. Recorded serving Python was 3.12.11. No prebuilt environment or native binary is distributed.

```bash
export DS41_ROOT="$PWD"
export DS41_MODEL_DIR="/absolute/path/to/model"
export DS41_PYTHON="$DS41_ROOT/venv/bin/python"
export DS41_ENGRAM_DIR="$DS41_ROOT/engram"
/usr/bin/python3 scripts/prepare_sources.py --root "$DS41_ROOT" --downloads "/absolute/path/to/downloads"
bash scripts/build-native.sh --print-plan
bash scripts/build-native.sh --build
```

The preparation tools verify archive and patch pins, reject existing destinations and publish only after successful preparation. The native build verifies source pins, builds the KT extension and CPU adapter with one job, then creates the actual ABI/artifact receipt. Its DK recipe explicitly disables AVX512, the llama.cpp CUDA backend and optional llama.cpp test/example/server builds while retaining AVX2/FMA/F16C and the KTransformers CUDA extension. The renamed K22 native build remains untested.

## Readiness and launch

Obtain a trusted `SHA256SUMS` covering all 52 real model shards. The verifier hashes regular, non-symlink shards directly in the model directory and exclusively creates `checksums.ok`:

```bash
"$DS41_PYTHON" scripts/verify_model_shards.py --model-dir "$DS41_MODEL_DIR"
"$DS41_PYTHON" tools/make-engram-manifest.py --model-dir "$DS41_MODEL_DIR" --output "$DS41_ENGRAM_DIR/engram-manifest.json"
source scripts/runtime-config.sh
ds41_configure
source scripts/standard-env.sh
ds41_standard_env
"$DS41_PYTHON" scripts/verify_runtime.py create --root "$DS41_ROOT"
bash scripts/start-standard.sh --print-command
bash scripts/start-standard.sh --start-standard
```

The shard receipt binds the exact checksum-list digest and shard set, not the publisher's identity. Keep verified weights immutable. The Engram producer reads the real model index and safetensors headers for exact weight/scale offsets without extracting tensor payloads. Its index must come from the same trusted distribution; the shard receipt does not cover that index. Runtime manifests remain local.

Runtime readiness verifies the build receipt and discovers required packages without importing them. Discovery is not a functional server check. The resolver checks source, placement, native ELF, Python ABI and receipts; the starter reserves the configured lock, waits for health and parser readiness, then requests exact 32k and 8k synthetic warmups. All positive deployment paths remain untested for this K22 candidate. Do not create readiness receipts manually.

The endpoint defaults to numeric IPv4 loopback, port 18081 and device ordinal 0; ::1 is supported with bracketed URLs. Startup and readiness use the same endpoint. Stop only the exact unit recorded in the selected run's `unit.txt`; StopPost releases its reservation. Handoff requires a retained reservation and a stopped prior unit.

## Checks and limits

The WSL run passed 18 real-input tests: 12 archive/source tests and six runtime-configuration tests. The latter used genuine CPython 3.12.11, the original recorded K22 native ELF and a genuine row-store library. The independent K22 oracle compared 93 recorded environment entries, including the additional checkpoint-source marker, plus the permitted public port setting, and all 74 command arguments. It was derived from the historical configuration and original K22 settings, not from current resolver output; the historical r3 oracle remains unchanged. These are offline source, ABI and configuration checks, not a native rebuild, kernel-execution or live-service test. See [VALIDATION](VALIDATION.md) for commands and remaining limits.

## Credits and licenses

Own tooling and patches use Apache-2.0; upstream notices are preserved. Thanks to SGLang, KTransformers, FlashInfer and the 05yuki compatibility recipe. The Engram adapter retains 0xSero's MIT copyright/header/text. llama.cpp is MIT and pybind11 BSD. Full texts and provenance are in `licenses/` and [NOTICE](NOTICE).

Weights are not redistributed; the tooling license grants no model/data rights. Original synthetic warmup text is included; no external literary corpus is copied.

## Versions

- `v3.0.0-k22`: K22 source candidate; source reconstruction and 18 offline real-input tests passed. Native rebuilding and deployment remain untested.
- `v2.1.1` (8 October 2026): public r3 release; documentation/checksum update, with code and patches unchanged from v2.1.
- `v2.1` (3 October 2026): r3 source release candidate.
