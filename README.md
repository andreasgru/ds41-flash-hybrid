# ds41-flash-hybrid

B10-v6 source release candidate, tag `v3.2.0-b10-v6`, for DeepSeek-V4.1-Flash with pinned SGLang and KTransformers. B10 adds CPU kernel 3 on the DK/Arena source base, retaining the K22b GPU-resident expert B12X W4A16 decode and streamed CUTLASS prefill. Weights, Engram data, runtime environments and native binaries are supplied separately.

**Status: source reconstruction and 18 offline real-input tests passed.** Static interface and actual print-path workspace counterchecks passed. Native rebuilding, GPU execution, server startup and full workload acceptance remain untested. Historical measurements describe recorded implementations, not a newly built public artifact.

The intended workload remains 1–2 main sessions approaching 500k tokens plus 4–6 subordinate sessions. The historical full-load run used one main and four subordinate sessions and failed five performance gates.

## B10-v6 profile

Recorded hardware: RTX PRO 6000 Blackwell Max-Q, 96 GB; two EPYC 7302 CPUs; approximately 499 GiB host RAM visible to the operating system.

The portable profile retains placement and server options: context 524,288, token pool 1,800,000, prefill chunk 16,384, streaming threshold 1,024, SWA/full ratio 0.0625, GPU memory fraction 0.90, 90 GPU experts, 28 CPU inference threads, at most 12 requests and graph batches 1–12. HiCache and speculation stay disabled; NUMA nodes are 0/1.

`KT_DS41_MU_MXFP4_KERNEL=3` selects B10 E4M3 activation quantization (W4A8) with `KT_DS41_MU_MXFP4_E8M0=1`. This path is not bit-identical to the preceding decode path; numerical and quality gates remain required. `DS41_CBPKG=multi-user-dk` remains the package selector. The inherited DECODE_KERNEL=1 and DECODE_PREFETCH=2048 settings have source readers, but their DK decode dispatch requires kernel 1 and does not select B10 kernel 3. K2EPLUS=1 retains the expert pipeline. Dense FP8 operations separately use `SGLANG_DS41_MU_MXFP8_B12X=1`.

A1 keeps CACHE=1, SWAP=1, BUDGET=2, STAT_S=1, RING=32 and STAGER=1 under `SGLANG_DS41_MU_A1_`. GPU-resident expert slots use B12X W4A16 and streamed prefill stays on CUTLASS. All 14 selected extension switches have static readers; this does not imply that retained DK switches affect kernel 3. K22 lacked the GPU-expert B12X readers; its dense MXFP8 path was separately active.

Shared expert storage and zero-copy remain off; A1 reads checkpoint experts. `A1_SOURCE=ckpt` is an additional visible marker for the hardcoded checkpoint reader, not a selectable reader implementation. Exact historical environment-byte equality is not claimed. `SGLANG_DS41_MU_A1_B12X_WORKSPACE_TOKENS` stays unset or zero; capacity follows the prefill chunk with fallback 16384. Nonzero overrides are rejected.

The service limit remains 480 GiB with no swap; preflight requires 465 GiB available. Stop thresholds remain 60 GiB global available memory, 2 GiB on either NUMA node, 1 GiB swap growth and 460 GiB anonymous/shared memory. Ownership and control-group cleanup remain in place. See [CONFIGURATION](CONFIGURATION.md).

## Historical B10-v6 measurements — 18 October 2026

The fixed cohort contains all ten complete archived starts selected for this comparison: seven with model revision 1016 and three with revision 1017. Earlier auxiliary starts and the following start are excluded. Values were computed on Linux from internal archives by the reviewed `b10-band-v2` tool (source SHA256 `3863fb38c7ffd5e7a87feee9489ae6f5f440416c5f3554d46b7864407aa0464b`; tool archive SHA256 `b68846e18460896eba643fcd3d8d236f843b30463f8d6bea7f910abb9515ac2e`). Raw measurement data are internal and are not published. Each cell is min / median / max across starts, in tokens/s.

| Metric | Model 1016, n=7 starts | Model 1017, n=3 starts |
|---|---:|---:|
| bs1x20, 20 measured + 1 excluded warmup | 63.470 / 63.741 / 64.432 | 64.503 / 64.523 / 64.657 |
| Decode bs1, all 6 including warmup | 64.523 / 64.623 / 64.734 | 65.128 / 65.233 / 65.492 |
| Decode bs4, all 6 including warmup | 103.687 / 106.003 / 108.317 | 110.514 / 110.659 / 110.713 |
| Decode bs8, all 6 including warmup | 193.413 / 200.878 / 205.069 | 204.968 / 210.257 / 214.920 |
| m8_median_22, aligned, includes 2 warmups | 140.462 / 141.504 / 142.275 | 142.294 / 143.110 / 143.140 |
| Aligned m8, 20 measured | 140.591 / 142.018 / 142.488 | 142.549 / 143.414 / 143.541 |
| qprobe2 partial correct count / 88 | 75 / 76 / 76 | 76 / 76 / 76 |
| Separate JSON validity / 10 | 10 / 10 / 10 | 10 / 10 / 10 |
| Arithmetic first attempt / 36 | 36 / 36 / 36 | 35 / 35 / 36 |

bs1x20 uses the same synthetic prompt, output length 256 and thinking disabled. Decode has five measured repetitions and one warmup; the legacy extractor includes all six. m8 uses eight distinct synthetic prompts and aligned-stream rates; its 22-record median includes two warmups while the independently recomputed 20-record metric excludes them. The unaligned reading is invalid for staggered starts. These short repeated synthetic-load starts are not full workload acceptance or a controlled statistical trial.

The qprobe2 correct count excludes the separately counted JSON tasks; it is a partial count, not a complete quality score. Two model-1017 starts scored 35/36 arithmetic initially and passed an allowed one-item retry (1/1), reported separately; the third scored 36/36 without retry. Model-1017 numerical-reference data were captured without a G2 verdict against the model-1016 reference. No 1017 numerical-gate pass or standard change is implied. No ranges from other cohorts are included in this table.

## Historical K22b measurements

Historical values are transcribed from internal run logs; the raw measurement data are not published.

Two short repeat runs on 16 October 2026 used the recorded K22b implementation. Values include the initial ramp-up; they do not describe a newly built public artifact or guarantee the first-request rate.

| Metric | K22b repeat A | K22b repeat B | Conditions per run |
|---|---:|---:|---|
| Single-request median, tok/s | 64.08 | 62.48 | 20 measured repeats + 1 warm-up; same prompt, output length 256, thinking off |
| 88-item quality set, correct | 77/88 | 77/88 | One complete set |
| 36-item arithmetic set, correct | 36/36 | 35/36 + allowed retry correct | First attempt and retry reported separately |

Separate longer multi-prompt runs produced aligned batch-8 plateau values of **132.96 and 132.99 tok/s in two K22b starts**, versus **121.31 tok/s in one K22 reference start**. Each start had 20 measured batch-8 repetitions; these plateau values use repetitions 8–10, the first qualifying three-repeat window from repetition 8 with `(max-min)/median <= 4%`. They are not full-run medians or the identical-prompt decode benchmark. Unaligned m8 values were invalid because stream starts were staggered. Ramp-up after a workload change remains visible, especially at batch 4. Longer performance-only runs did not add quality or numerical-check coverage.

Decode measurements with known overlapping external reads, including the standard-switch decode interval, are not presented as clean benchmarks here. The standard-switch numerical confirmation initially used reference v4. Reference v5 was installed later, selecting a central single run from four candidates with the numerical gate unchanged. Earlier results are not relabeled as v5 results; a numerical-gate pass does not mean bitwise identity.

## Historical K22 measurements

Historical values are transcribed from internal run logs; the raw measurement data are not published.

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

Stability passed in that historical run. Quality stages were **not run after HALT** at the load gates, including planned prompt-correctness and arithmetic checks. The separate K22 and K22b checks above do not complete those stages or turn these five gates green.

Future acceptance uses `sum(min(C,U))/sum(U)`, where C is server-reported cached input tokens and U is the token longest common prefix with the preceding prompt plus generated output for the same agent and session. Measure main and subordinate roles separately from round 2; each role must reach 98%. The historical raw ratio has not been relabeled or recomputed. See [METHODS](METHODS.md).

## Sources, preparation and build

Archive revisions, SHA256 and exact download URLs are in `pins/upstream.json`. The eight-patch series contains four r3 patches, two K22 patches, the K22b SGLang overlay and the B10 native patch. Fresh application reproduced 10,410 regular files and five symlink targets against the derived cleaned B10 target. Both B10 native files were freshly reversed to pinned raw originals; the earlier K22b four-file and K22 56-file reversal journals are pinned and inherited, not rerun in this stage. The Arena-qualified base equals K22b before the B10 patch. Three fail-closed controls passed. Runtime coverage is 63 source files and 81 total pins. FlashInfer entries record external runtime provenance and are not extracted by this series.

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

The preparation tools verify archive and patch pins, reject existing destinations and publish only after successful preparation. The native build verifies source pins, builds the KT extension and CPU adapter with one job, then creates the actual ABI/artifact receipt. Its native recipe explicitly disables AVX512, VNNI, BF16 and VBMI, the llama.cpp CUDA backend and optional llama.cpp test/example/server builds while retaining AVX2/FMA/F16C and the KTransformers CUDA extension. The historical B10 tempo module used CUDA 13.2.86 and GCC 15.2; serving paths retain CUDA 13.3. The portable renamed native build remains untested; byte-identical rebuilding is not claimed. The tempo recipe omits the compile macro `K2P_TRACE`; this is not a runtime environment knob.

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

Runtime readiness verifies the build receipt and discovers required packages without importing them. Discovery is not a functional server check. The resolver checks source, placement, native ELF, Python ABI and receipts; the starter reserves the configured lock, waits for health and parser readiness, then requests exact 32k and 8k synthetic warmups. All positive deployment paths remain untested for this B10 candidate. Do not create readiness receipts manually.

The endpoint defaults to numeric IPv4 loopback, port 18081 and device ordinal 0; ::1 is supported with bracketed URLs. Startup and readiness use the same endpoint. Stop only the exact unit recorded in the selected run's `unit.txt`; StopPost releases its reservation. Handoff requires a retained reservation and a stopped prior unit.

## Checks and limits

The first B10 WSL run passed 18 real-input tests in 28.133 s: 12 archive/source and six runtime-configuration methods against eight patches and 81 pins. It compared 93 independent oracle environment entries plus the port setting and 74 command arguments. Genuine CPython 3.12.11, historical B10 native ELF `87b1314b` and a genuine row-store library support offline ABI/configuration checks only. Static interface and actual print-path workspace counterchecks passed. See [VALIDATION](VALIDATION.md).

## Credits and licenses

Own tooling and patches use Apache-2.0; upstream notices are preserved. Thanks to SGLang, KTransformers, FlashInfer and the 05yuki compatibility recipe. The Engram adapter retains 0xSero's MIT copyright/header/text. llama.cpp is MIT and pybind11 BSD. Full texts and provenance are in `licenses/` and [NOTICE](NOTICE).

Weights are not redistributed; the tooling license grants no model/data rights. Original synthetic warmup text is included; no external literary corpus is copied.

## Versions

- `v3.2.0-b10-v6`: B10 CPU kernel 3, K22b GPU expert path and fixed ten-start historical measurement cohort.

- `v3.1.1-k22b`: documentation consistency update; product code and tests unchanged.
- `v3.1.0-k22b`: internal, not published; superseded by v3.1.1-k22b (documentation consistency).
- `v3.0.0-k22`: K22 source candidate; source reconstruction and 18 offline real-input tests passed. Native rebuilding and deployment remain untested.
- `v2.1.1` (8 October 2026): public r3 release; documentation/checksum update, with code and patches unchanged from v2.1.
- `v2.1` (3 October 2026): r3 source release candidate.

Historical K22b source byte equality is against its derived cleaned target. The four K22b overlay reversals were executed for that earlier stage; the earlier 56-file K22 reversal journal is pinned and inherited, rather than rerun as part of the K22b build. Supplied standard inputs match both their pinned raw K22 counterparts and, after cleanup, the derived K22 files.

Historical K22b verification record (product code at v3.1.1-k22b): the final archive passed 18 tests in 27.895 s (k22b-final-real-tests-v2-tests.log:509,511). The static interface check found 12 selected readers and detected the removed-reader and state-key regression controls (k22b-final-check_k22b_interfaces_v1.py.log:1). The actual print path accepted the default and zero workspace settings and rejected half-chunk, double-chunk and invalid overrides (k22b-final-check_k22b_workspace_v1.py.log:1). These additional verification scripts and evidence logs are internal and are not published. Native rebuilding, GPU inference and live-service operation remain untested; no pass for those paths is implied.

B10-v6 current-stage evidence: the first 18 offline tests passed in 28.133 s against eight patches and 81 runtime pins (63 source files). The independent B10 oracle retains 93 environment entries plus the permitted port and 74 command arguments; only the selected kernel value changes from 1 to 3 relative to K22b. Static interface checks found 14 readers and detected the removed-reader/state-key controls. The actual print path accepted default/zero workspace settings and rejected half-chunk/double-chunk/invalid overrides. These additional verification scripts and logs are internal and are not published. Native rebuilding, GPU inference and live service remain untested; no pass is implied.
