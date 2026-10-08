# ds41-flash-hybrid

Source release candidate v2.1.1 for DeepSeek-V4.1-Flash with pinned SGLang and KTransformers. The project name is `ds41-flash-hybrid`. This package contains a compatibility patch series, an English multi-user layer, portable build and launch tools, and real-input regression tests. Weights, Engram data, runtime environments and native binaries are supplied separately.

The intended workload is 1–2 main sessions approaching 500k tokens plus 4–6 subordinate sessions. The historical run used one main and four subordinate sessions; it does not establish that the full workload meets its targets.

## Recorded results

Hardware: RTX PRO 6000 Blackwell Max-Q, 96 GB; two EPYC 7302 CPUs; about 499 GiB host RAM visible to the operating system. The recorded profile used a 524,288-token context limit, a 1,800,000-token pool, 16,384-token prefill chunks, a 1,024-token streaming threshold, SWA/full ratio 0.0625, static GPU memory fraction 0.90, 90 GPU experts, 28 CPU inference threads and at most 12 requests. HiCache and speculation were disabled.

The historical load ran on 28–29 September 2026: 649 requests, no reported request errors, about 8 h 12 min. Throughput refers to the long-context band window.

| Gate | Recorded result | Target | Sample count | Status |
|---|---:|---:|---:|---|
| Aggregate throughput in the band window | 35.11 tokens/s | ≥40 tokens/s | 649 requests | **RED** |
| Main-session TTFT p95 | 57.88 s | ≤30 s | 58 | **RED** |
| Main-session TTFT p50 | 15.745 s | ≤15 s | 58 | **RED** |
| Subordinate-session TTFT p95 | 50.21 s | ≤30 s | 244 | **RED** |
| Subordinate raw cache ratio | 96.42% | ≥98% | 243 | **RED** |

Stability passed. Quality stages were **not run after HALT** at the load gates, including the planned prompt-correctness and arithmetic checks. No new GPU benchmark or quality pass is claimed here.

Future acceptance uses `sum(min(C,U))/sum(U)`, where C is server-reported cached input tokens and U is the token longest common prefix with the preceding prompt plus generated output **for the same agent and session**. Measure main and subordinate roles separately, starting at round 2; each role must reach 98%. The historical raw ratio has not been relabeled or recomputed. See [METHODS](METHODS.md).

## Pins and names

Archive revisions, SHA256 and exact codeload URLs are maintained once in `pins/upstream.json`; both source tools consume it. The four patches in `patches/series` separate the 05yuki recipe baseline from the own multi-user layer. Applying them to fresh pinned sources reproduces the complete cleaned source tree. Download the archives from the listed URLs into an external downloads directory; FlashInfer entries record external runtime provenance and are not extracted by this series.

Own SGLang options use `SGLANG_DS41_MU_*`; own KT additions use `KT_DS41_MU_*`. Internal identifiers use `ds41_mu_*`/`_ds41_mu*` and the approved DS41MU class names. Genuine upstream and recipe interfaces keep their existing names; the `KT_` prefix alone does not imply upstream origin.

## Prepare and build

Requirements: Linux x86_64, Bash, GNU patch/diff, CMake, Ninja, a C++ compiler, CUDA 13.3, development/sysroot libraries and a compatible Python environment with PyTorch, SGLang, FlashInfer and Triton dependencies. Recorded serving Python was 3.12.11. Source checks also ran with Python 3.14. No prebuilt environment or native binary is distributed.

```bash
export DS41_ROOT="$PWD"
export DS41_MODEL_DIR="/absolute/path/to/model"
export DS41_PYTHON="$DS41_ROOT/venv/bin/python"
export DS41_ENGRAM_DIR="$DS41_ROOT/engram"
/usr/bin/python3 scripts/prepare_sources.py --root "$DS41_ROOT" --downloads "/absolute/path/to/downloads"
bash scripts/build-native.sh --print-plan
bash scripts/build-native.sh --build
```

Preparation verifies archives and uses patch dry runs followed by real applications. Source extraction and dependency preparation publish atomically only after success; failure removes their own partial staging tree. Existing output destinations, including dangling symlinks, are rejected. The native build uses one job, verifies source pins, builds the KT extension and CPU adapter and creates its actual ABI/artifact receipt. A native KT/CUDA rebuild for this source release remains **untested**.

## Readiness inputs

Obtain a trusted `SHA256SUMS` covering all 52 real model shards. Files must be regular, non-symlink safetensors shards directly in the model directory. The actual verifier hashes them and exclusively creates the filename-free `checksums.ok` receipt:

```bash
"$DS41_PYTHON" scripts/verify_model_shards.py --model-dir "$DS41_MODEL_DIR"
"$DS41_PYTHON" tools/make-engram-manifest.py --model-dir "$DS41_MODEL_DIR" --output "$DS41_ENGRAM_DIR/engram-manifest.json"
```

The receipt binds schema/status/shard count to the exact checksum-list SHA256. It does not authenticate the list's publisher. The launch check validates receipt types, list digest and exact current shard set. The expensive complete hashing happens at receipt creation; keep verified weights immutable afterwards.

The shipped Engram producer reads the real model index and safetensors headers for layers 1 and 14, with exact weight/scale offsets. It writes the adapter's existing manifest format without reading/extracting tensor payloads. The index must come from the same trusted model distribution. It is not covered by the 52-shard receipt. Runtime manifests contain local paths and shard names and are not distributed in this repository. Positive model verification and Engram generation remain **untested** in this release preparation; no fabricated weights or headers replace them.

Create `runtime.ready` through its actual producer after preparing real runtime dependencies:

```bash
source scripts/runtime-config.sh
ds41_configure
source scripts/standard-env.sh
ds41_standard_env
"$DS41_PYTHON" scripts/verify_runtime.py create --root "$DS41_ROOT"
```

This resolves the actual launch, verifies the build receipt, discovers the seven required top-level packages without importing them and binds the runtime receipt to the actual build-manifest hash. Discovery is not a functional GPU/server check. Full runtime-readiness success remains **untested**; missing real packages are rejected, not supplied by substitutes. Do not create these receipts manually.

## Resolve and start

```bash
bash scripts/start-standard.sh --print-command
bash scripts/start-standard.sh --start-standard
```

The first command performs actual source/placement/native/ELF/ABI/receipt checks and prints the resolved command and environment. It starts no server. It was checked in a private release copy using the supplied genuine Python interpreter and copies of genuine native artifacts against the recorded r3 configuration, with only documented names/paths/device/diagnostic exceptions. This does not certify a new native build or inference.

The second reserves the configured lock, starts the service, waits for health and parser readiness and requests exact 32k then 8k synthetic warmups with 16 output tokens each. GPU/server startup, real tokenizer/inference and the full warmup remain **untested** for v2.

The bind host defaults to 127.0.0.1 and accepts only numeric IPv4 loopback or ::1; IPv6 URLs are bracketed. Port defaults to 18081, device to ordinal 0. Startup, health, server-info and warmup use the same endpoint. Parser validation remains fail-closed.

The service uses a 360 GiB memory limit, no swap and control-group cleanup. Preflight requires 420 GiB available host memory. Stop thresholds are available memory below 60 GiB, either NUMA node below 2 GiB, swap growth above 1 GiB or anonymous/shared memory above 340 GiB. NUMA nodes 0/1 and AVX2 are fixed recorded-profile properties. See [CONFIGURATION](CONFIGURATION.md).

Stop only the exact unit written in the chosen run's `unit.txt`. StopPost releases that reservation; shared lock contents must not be edited by hand. Handoff requires a retained reservation and a stopped prior unit.

## Real-input checks

The public archive suite requires the four real pinned SGLang/KT/llama.cpp/pybind11 archives. Runtime regression additionally requires a genuine interpreter, KT extension and row-store library. Missing inputs fail closed; there are no fake packages, native stubs or patched-out functions. See [VALIDATION](VALIDATION.md) for commands, mutants and explicitly untested paths. Ordinary API inputs and mutations of real file copies do not replace producers.

The five performance gates remain red. Offline source/configuration checks do not turn them green.

## Credits and licenses

Own tooling and patches use Apache-2.0; upstream notices are preserved. Thanks to SGLang, KTransformers, FlashInfer and the 05yuki compatibility recipe. The Engram adapter retains 0xSero's MIT copyright/header/text. llama.cpp is MIT, pybind11 BSD. Full texts and pinned provenance are in `licenses/` and [NOTICE](NOTICE).

Weights are not redistributed; the tooling license grants no model/data rights. Original synthetic warmup text is included; no Wikipedia or Gutenberg corpus is copied.

## Versions

- v2.1.1 (8 October 2026): public release. README wording and checksum files only; code, patches, configuration and tests are byte-identical to v2.1.
- v2.1 (3 October 2026): source release candidate, first distributed privately (package ds41-flash-hybrid-v2.1-60abc3c5f971, tag `v2.1`).
