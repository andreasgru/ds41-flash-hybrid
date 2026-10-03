# Validation and explicit limits

## Required real inputs

Archive checks use the four real pinned archives; both source tools read `pins/upstream.json`. Set a test-owned temporary directory outside the release/downloads paths:

```bash
mkdir -p /absolute/path/to/owned-test-work
export TMPDIR=/absolute/path/to/owned-test-work
export DS41_TEST_DOWNLOADS=/absolute/path/to/downloads
/usr/bin/python3 -B -m unittest discover -s tests -p test_real_inputs.py -v
```

The archive suite has 12 methods covering actual apply/prepare/source pins and lock reservation plus real-file mutants: patch SHA, context, empty/duplicate series, traversal, missing/corrupt archives, missing/duplicate central pins, existing output and failure after dependency extraction. Failed transactions must leave neither output nor their own staging directory. Missing required inputs are errors, not a passing empty suite.

Runtime checks additionally require genuine files:

```bash
export DS41_TEST_PYTHON=/absolute/path/to/actual/python
export DS41_TEST_KT_EXTENSION=/absolute/path/to/actual/kt_kernel_ext.so
export DS41_TEST_ROW_STORE=/absolute/path/to/actual/librow_store.so
/usr/bin/python3 -B -m unittest discover -s tests -p test_runtime_inputs.py -v
```

This suite prepares sources from real archives, copies genuine native files, creates the actual build receipt and exercises `start-standard.sh --print-command`. The expected configuration is independently derived from the actual recorded r3 command, with neutral keys and installation-path substitutions; it is never copied from the current producer. Removing the real Engram DIR export must make the configuration comparison red. Native/source byte changes must make the operational resolver fail. Endpoint checks call the actual shared local-address validator; they do not replace an HTTP service.

No test uses a native stub, fake package, fabricated server response or monkeypatched function. Test inputs and mutant copies remain private. The original synthetic resource/parser/tokenizer tests are not carried forward under the no-replacement rule; their real operating paths remain untested.

## Separate evidence

Source reconstruction, approved name-only transformation, English comments/literals and path/configuration changes are distinct proofs. Name/text stages use positional reverse checks; Python structure and C++ tokens are checked separately. English text changes are listed as translations, not represented as byte-identical original messages. The public patch series is freshly reapplied and compared to the cleaned generator tree.

The independently captured configuration uses 80 recorded environment entries after removing one diagnostic setting, plus the allowed public port; the recorded command has 74 argv entries. Private UUIDs, locations and run data are excluded. The unchanged independent review comparator also checks the final genuine operational resolve. Performance numbers are recorded historical results, not measured by these suites.

## Untested positive deployment paths

- Native KT/CUDA compilation of the renamed source and environment interfaces.
- GPU execution, model loading, live server health/parser readiness and inference.
- Real tokenizer and standard warmup against an actual service.
- Full 52-shard model hashing and positive model-readiness receipt creation.
- Positive Engram-header/offset manifest generation with actual model weights.
- Positive full runtime-dependency receipt creation in a complete serving environment.
- Real systemd start rollback, handoff, signals and StopPost.
- New performance/quality measurements after the historical HALT.

The archive/configuration/file tests prove their named paths only. Actual historical native artifacts used for resolution are not distributed or described as a rebuilt v2 kernel. All five README performance gates remain red.
