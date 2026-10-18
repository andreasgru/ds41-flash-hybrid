# Known issues before public release

These review observations remain open in the K22b source candidate:

- The recorded live configuration omits NCCL_*, PYTORCH_CUDA_ALLOC_CONF, TRANSFORMERS_OFFLINE, PATH and DS41_* settings from its filter. They cannot be compared with that live record; the oracle suite does not establish their presence.
- DSV41_ENGRAM_MANIFEST can select another manifest while preflight checks the standard manifest location. The override is not yet aligned with that check.
- Concurrent flock acquisition fails immediately; first-start.at is set when the service command returns; terminate is not followed by wait; Engram-manifest creation makes its destination before validation; an adapter extraction comment and a model-verifier line reference need correction.
- standard_start.py, warmup.py and build_manifest.py remain outside the current runtime pin set. The four additional runtime consumers requested for this revision are pinned.

Positive model/Engram/runtime readiness, native rebuild, GPU/server operation, HTTP warmup and supervisor signal/service paths remain untested. No substitute states are used to claim those paths.

The preceding K22 stage set two A1 GPU-expert B12X flags without readers. K22b supplies those readers; dense MXFP8 B12X remains separately active and streamed prefill stays on CUTLASS. Nonzero workspace overrides are outside the fixed profile and rejected. The additional checkpoint-source marker remains visible; exact historical environment-byte equality is not claimed.

The final 18-test K22b offline run passed alongside the seven-patch source reconstruction. The final product archive and the separate interface/workspace counterchecks passed; see the verification record below. Historical short-repeat rates include ramp-up; aligned-stream plateaus are not full-run medians. Known disturbed decode measurements are excluded from clean performance claims. Numerical reference v4 at standard switch and the later v5 must not be conflated; a numerical-gate pass does not establish bitwise identity. The five historical full-load gates remain red.

Verification record for the unchanged product code: the final archive passed 18 tests in 27.895 s (k22b-final-real-tests-v2-tests.log:509,511). The static interface check found 12 selected readers and detected the removed-reader and state-key regression controls (k22b-final-check_k22b_interfaces_v1.py.log:1). The actual print path accepted the default and zero workspace settings and rejected half-chunk, double-chunk and invalid overrides (k22b-final-check_k22b_workspace_v1.py.log:1). These additional verification scripts and evidence logs are internal and are not published. Native rebuilding, GPU inference and live-service operation remain untested; no pass for those paths is implied.
