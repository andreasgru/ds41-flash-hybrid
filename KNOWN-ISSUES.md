# Known issues before public release

Initial repository distribution is private. These review observations remain open:

- The recorded live configuration omits NCCL_*, PYTORCH_CUDA_ALLOC_CONF, TRANSFORMERS_OFFLINE, PATH and DS41_* settings from its filter. They cannot be compared with that live record; the oracle suite does not establish their presence.
- DSV41_ENGRAM_MANIFEST can select another manifest while preflight checks the standard manifest location. The override is not yet aligned with that check.
- Concurrent flock acquisition fails immediately; first-start.at is set when the service command returns; terminate is not followed by wait; Engram-manifest creation makes its destination before validation; an adapter extraction comment and a model-verifier line reference need correction.
- standard_start.py, warmup.py and build_manifest.py remain outside the current runtime pin set. The four additional runtime consumers requested for this revision are pinned.

Positive model/Engram/runtime readiness, native rebuild, GPU/server operation, HTTP warmup and supervisor signal/service paths remain untested. No substitute states are used to claim those paths.
