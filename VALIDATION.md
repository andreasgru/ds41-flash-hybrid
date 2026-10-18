# Validation and explicit limits

**B10-v6 candidate `v3.2.0-b10-v6`: eight-patch source reconstruction and 18 offline real-input tests passed.** See the current-stage evidence below. All following K22b-specific results remain historical evidence for that earlier stage.

## Required real inputs and existing suites

Both source tools consume `pins/upstream.json`. Archive checks require the four real pinned SGLang, KTransformers, llama.cpp and pybind11 archives. Use a temporary directory owned by the test outside release/download paths:

```bash
mkdir -p /absolute/path/to/owned-test-work
export TMPDIR=/absolute/path/to/owned-test-work
export DS41_TEST_DOWNLOADS=/absolute/path/to/downloads
/usr/bin/python3 -B -m unittest discover -s tests -p test_real_inputs.py -v
```

The existing archive suite has 12 methods covering actual apply/prepare/source pins and lock reservation, with real-file mutants for patch SHA/context, empty or duplicate series, traversal, missing or corrupt archives, missing or duplicate central pins, existing outputs and failure after dependency extraction. Failed transactions must leave neither output nor their own staging directory. Missing inputs are errors, not a passing empty suite. All 12 methods passed in the K22b WSL run against the seven-patch series. The preceding K22 result remains historical.

Runtime checks additionally require genuine files:

```bash
export DS41_TEST_PYTHON=/absolute/path/to/actual/python
export DS41_TEST_KT_EXTENSION=/absolute/path/to/actual/kt_kernel_ext.so
export DS41_TEST_ROW_STORE=/absolute/path/to/actual/librow_store.so
/usr/bin/python3 -B -m unittest discover -s tests -p test_runtime_inputs.py -v
```

The final K22b product run passed six runtime-configuration tests using genuine CPython 3.12.11, the original recorded K22 native ELF (SHA256 prefix `729974e6`) and a genuine row-store library. The suite prepares real sources, copies those artifacts, creates the actual build receipt and exercises `start-standard.sh --print-command`. The native artifact is used for ABI and command resolution only: this is neither a rebuild nor an inference test.

The preserved independent K22 oracle derives its expectations from the preserved recorded r3 comparator plus the original K22 environment and launcher settings, with explicit neutral-name/path substitutions and the additional `A1_SOURCE=ckpt` marker. It does not copy current producer output. The first K22b run compared 93 oracle environment entries plus the permitted public port setting and all 74 command arguments. Static interface and actual print-path workspace counterchecks passed. The historical r3 oracle file remains unchanged. The real-file negative controls include removal of the Engram-directory export, changed source/native bytes, a foreign lock record and failed dependency preparation; endpoint checks exercise the actual validator without starting a service.

These suites reject changed source/native bytes and exercise actual endpoint validation. They use neither native stubs, fake packages, fabricated server responses nor monkeypatched functions. Tokenizer, live resource/parser and service behavior require their real operating environments; no replacement response certifies them.

## Historical K22b source reconstruction and pin coverage

The seven-patch series contains four r3 patches, two K22 patches and one K22b SGLang patch. Fresh application reproduced 10,409 regular files and five symlink targets. Four new overlay files reverse to their pinned originals; three accompanying standard originals match K22. The result binds the preceding 56-file reversal. Three fail-closed controls reject missing inputs, a corrupt patch and an existing output. Runtime coverage is 80 pins: 62 source files, seven FP8 configurations, three adapter files, placement and seven runtime helpers. The final 18-test K22b archive/runtime pass is separate evidence; neither result establishes native execution. Static interface and actual print-path workspace counterchecks passed.

The K22b source change activates all 12 selected extension switches, including the two GPU-expert B12X switches that had no readers in K22. Streamed prefill remains CUTLASS. The workspace-token override stays unset/zero; the fixed profile rejects nonzero inherited overrides. Native-module selection, placement, argv and RAM limits remain the K22 profile. A historical native ELF is useful for ABI/command resolution, not evidence that renamed sources compile or execute correctly.

`A1_SOURCE=ckpt` is additionally exposed in the resolved environment. The source reader remains hardcoded to checkpoint experts, shared expert storage stays off, and the marker does not enable an arena/writer source. Exact historical environment-byte equality is not claimed.

## Historical K22b measurements and numerical references

Historical values are transcribed from internal run logs; the raw measurement data are not published.

README records two short starts with 20 measured single-request repetitions plus one warm-up, the same prompt, output length 256 and thinking disabled. The arithmetic result 35/36 followed by a successful permitted retry is kept separate from a first-attempt 36/36 result.

Separate longer performance-only starts each measured 20 batch-8 repetitions. Two K22b plateau results 132.96/132.99 tok/s compare with one K22 result 121.31; the first qualifying three-repeat window is repetitions 8–10, not the entire-run median. The metric is aligned after staggered starts; unaligned results were invalid. Warm-up after a changed workload, particularly at batch 4, limits extrapolation. Known disturbed decode results are not offered as clean benchmarks.

Reference v4 was used at the historical standard switch. Reference v5 was installed later, selecting one central run from four candidates, with the numerical gate unchanged. It is not an averaged four-run reference or four out-of-sample passes. Earlier numerical results retain their original reference identity; permitted token flips mean a numerical-gate pass is not bitwise identity. No request/response reference data is distributed here.

## Historical K22 measurements

Historical values are transcribed from internal run logs; the raw measurement data are not published.

The two 14 October repeat runs and their per-run counts are listed in [README](README.md). Single-request tests used 20 measured repetitions plus one warm-up; batch-decode tests used five plus one per batch, with output length 256. The eight-stream figures use the aligned aggregate over ten repetitions at batch 8. The unaligned metric was invalid because stream starts were offset by 5.81–6.29 seconds. The two aligned run results differ by approximately 0.7%; this is not a statistical confidence bound.

The fixed A1_B12X_DECODE and A1_B12X_STREAM_CUTLASS flags had no readers in the K22 tree. GPU expert B12X decode was absent; dense MXFP8 B12X was active. Results around 63.4 tokens/s from a different experimental source/native combination must not be labeled K22 production measurements. Historical numerical, state and short quality checks do not validate a newly built public artifact.

## Untested positive deployment paths

- Native KT/CUDA compilation of the renamed B10 sources and environment interfaces.
- GPU execution, model loading, live health/parser readiness and inference.
- Actual tokenizer and complete standard warmup against a real service.
- Full 52-shard hashing and positive model-readiness receipt creation.
- Positive Engram-header/offset manifest generation with actual weights.
- Positive full dependency-readiness receipt creation in a serving environment.
- Real systemd start, rollback, handoff, signals and StopPost.
- New benchmarks and complete intended-workload acceptance for the public B10 candidate.

The historical v2/r3 load acceptance remains **RED on all five performance gates**, with sample counts retained in README. Quality stages after its HALT were not run. The separate K22/K22b short quality sets do not complete those missing stages or replace full acceptance.

Historical K22b source byte equality is against its derived cleaned target. The four K22b overlay reversals were executed for this stage; the earlier 56-file K22 reversal journal is pinned and inherited, rather than rerun as part of the K22b build. Supplied standard inputs match both their pinned raw K22 counterparts and, after cleanup, the derived K22 files.

Historical K22b verification record (product code at v3.1.1-k22b): the final archive passed 18 tests in 27.895 s (k22b-final-real-tests-v2-tests.log:509,511). The static interface check found 12 selected readers and detected the removed-reader and state-key regression controls (k22b-final-check_k22b_interfaces_v1.py.log:1). The actual print path accepted the default and zero workspace settings and rejected half-chunk, double-chunk and invalid overrides (k22b-final-check_k22b_workspace_v1.py.log:1). These additional verification scripts and evidence logs are internal and are not published. Native rebuilding, GPU inference and live-service operation remain untested; no pass for those paths is implied.

B10-v6 current-stage evidence: the first 18 offline tests passed in 28.133 s against eight patches and 81 runtime pins (63 source files). The independent B10 oracle retains 93 environment entries plus the permitted port and 74 command arguments; only the selected kernel value changes from 1 to 3 relative to K22b. Static interface checks found 14 readers and detected the removed-reader/state-key controls. The actual print path accepted default/zero workspace settings and rejected half-chunk/double-chunk/invalid overrides. These additional verification scripts and logs are internal and are not published. Native rebuilding, GPU inference and live service remain untested; no pass is implied.

B10 source equality is against the derived cleaned target: 10,410 files and five links, with two newly reversed B10 native files. Four K22b and 56 K22 raw reversals are inherited by pinned journals. Three fail-closed source controls passed. Historical B10 measurement definitions, fixed cohort date, tool hashes, separate model populations and both m8 readings are in README. Numerical-reference capture for model1017 is not a G2 verdict. All five historical full-load gates remain red.
