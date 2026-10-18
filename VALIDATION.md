# Validation and explicit limits

**K22 candidate `v3.0.0-k22`: source reconstruction and 18 offline real-input tests passed.** The WSL run passed 12 archive/source tests and six runtime-configuration tests. Native rebuilding, GPU execution, server startup and full workload acceptance remain untested. Historical inference measurements and current offline checks are separate evidence.

## Required real inputs and existing suites

Both source tools consume `pins/upstream.json`. Archive checks require the four real pinned SGLang, KTransformers, llama.cpp and pybind11 archives. Use a temporary directory owned by the test outside release/download paths:

```bash
mkdir -p /absolute/path/to/owned-test-work
export TMPDIR=/absolute/path/to/owned-test-work
export DS41_TEST_DOWNLOADS=/absolute/path/to/downloads
/usr/bin/python3 -B -m unittest discover -s tests -p test_real_inputs.py -v
```

The existing archive suite has 12 methods covering actual apply/prepare/source pins and lock reservation, with real-file mutants for patch SHA/context, empty or duplicate series, traversal, missing or corrupt archives, missing or duplicate central pins, existing outputs and failure after dependency extraction. Failed transactions must leave neither output nor their own staging directory. Missing inputs are errors, not a passing empty suite. All 12 methods passed in the recorded WSL run against the six-patch K22 series.

Runtime checks additionally require genuine files:

```bash
export DS41_TEST_PYTHON=/absolute/path/to/actual/python
export DS41_TEST_KT_EXTENSION=/absolute/path/to/actual/kt_kernel_ext.so
export DS41_TEST_ROW_STORE=/absolute/path/to/actual/librow_store.so
/usr/bin/python3 -B -m unittest discover -s tests -p test_runtime_inputs.py -v
```

The six runtime-configuration tests passed using genuine CPython 3.12.11, the original recorded K22 native ELF (SHA256 prefix `729974e6`) and a genuine row-store library. The suite prepares real sources, copies those artifacts, creates the actual build receipt and exercises `start-standard.sh --print-command`. The native artifact is used for ABI and command resolution only: this is neither a rebuild nor an inference test.

The independent K22 oracle derives its expectations from the preserved recorded r3 comparator plus the original K22 environment and launcher settings, with explicit neutral-name/path substitutions and the additional `A1_SOURCE=ckpt` marker. It does not copy current producer output. Comparison covers 93 oracle environment entries plus the permitted public port setting and all 74 command arguments. The historical r3 oracle file remains unchanged. The real-file negative controls include removal of the Engram-directory export, changed source/native bytes, a foreign lock record and failed dependency preparation; endpoint checks exercise the actual validator without starting a service.

These suites reject changed source/native bytes and exercise actual endpoint validation. They use neither native stubs, fake packages, fabricated server responses nor monkeypatched functions. Tokenizer, live resource/parser and service behavior require their real operating environments; no replacement response certifies them.

## Source reconstruction and pin coverage

The series contains four r3 patches and two K22 patches, one each for SGLang and KTransformers. Fresh application to the pinned archives reproduced all 10,408 regular files and five symlink targets in the derived cleaned target. The reverse-edit proof covers 56 files; three fail-closed controls reject missing inputs, a corrupt patch and an existing output. The runtime file list contains 78 pins: 60 source files, seven FP8 configuration files, three adapter files, placement and seven runtime helpers. Source identity, neutral renaming, English text and portable path/configuration changes remain separate claims; the recorded checks, rather than this prose, establish their stated scope.

The K22 resolver selects the fixed DK/A1 profile and preserves the existing server options and placement. The native build must use the K22 source pins and create a new actual ABI/artifact receipt. The historical native libraries support the passed offline K22 configuration comparison; they do not prove that the renamed sources rebuild or execute correctly.

`A1_SOURCE=ckpt` is additionally exposed in the resolved environment. The source reader remains hardcoded to checkpoint experts, shared expert storage stays off, and the marker does not enable an arena/writer source. Exact historical environment-byte equality is not claimed.

## Historical K22 measurements

The two 14 October repeat runs and their per-run counts are listed in [README](README.md). Single-request tests used 20 measured repetitions plus one warm-up; batch-decode tests used five plus one per batch, with output length 256. The eight-stream figures use the aligned aggregate over ten repetitions at batch 8. The unaligned metric was invalid because stream starts were offset by 5.81–6.29 seconds. The two aligned run results differ by approximately 0.7%; this is not a statistical confidence bound.

The fixed A1_B12X_DECODE and A1_B12X_STREAM_CUTLASS flags had no readers in the K22 tree. GPU expert B12X decode was absent; dense MXFP8 B12X was active. Results around 63.4 tokens/s from a different experimental source/native combination must not be labeled K22 production measurements. Historical numerical, state and short quality checks do not validate a newly built public artifact.

## Untested positive deployment paths

- Native KT/CUDA compilation of the renamed K22 sources and environment interfaces.
- GPU execution, model loading, live health/parser readiness and inference.
- Actual tokenizer and complete standard warmup against a real service.
- Full 52-shard hashing and positive model-readiness receipt creation.
- Positive Engram-header/offset manifest generation with actual weights.
- Positive full dependency-readiness receipt creation in a serving environment.
- Real systemd start, rollback, handoff, signals and StopPost.
- New benchmarks and complete intended-workload acceptance for the public K22 candidate.

The historical v2/r3 load acceptance remains **RED on all five performance gates**, with sample counts retained in README. Quality stages after its HALT were not run. The separate K22 short quality sets do not complete those missing stages or replace full acceptance.
