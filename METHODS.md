# Measurement methods

This document separates historical live measurements from the cache criterion intended for a future acceptance run. The historical results describe the selected live configuration, not a new run of this source package.

## Historical load

The producer ran for about 8 h 12 min on 28–29 September 2026 and recorded 649 requests. It used one main session and four subordinate sessions. The main session compacted near 500k tokens. The long-context band was 450k–500k tokens; throughput is the aggregate over the band window. The values and original sample counts are reproduced in [README](README.md). No raw request records are included.

The cache result in the README is the original subordinate raw ratio, 96.42% over 243 samples. It has not been relabeled or recomputed using the later criterion.

## Future cache criterion

Compute the ratio independently for main sessions and subordinate sessions. A combined result across the two roles does not establish either result.

For each request from round 2 onward, and for the same agent in the same session:

- `U` is the token length of the longest common prefix between the current prompt and the previous prompt concatenated with the previous generated output.
- `C` is the cached input-token count reported by the server.

For each role, calculate:

~~~text
R = sum(min(C, U)) / sum(U)
~~~

Each role must reach at least 0.98. Round 1 is excluded because there is no preceding turn. A request with `U = 0` contributes zero to both sums. If a role’s total denominator is zero, that role has no passing result. The available historical data does not contain the complete `U` measurements, so no retrospective result is claimed.

## Warmup path

The launch workflow requests tokenization from the running service, shapes the returned IDs to 32,768 and 8,192 tokens, then sends completion requests with a 16-token output limit. The public suites check warmup URL validation through the actual shared endpoint helper. They do not exercise token-count shaping or response validation and do not call a live tokenizer or completion endpoint. Warmup duration is request duration, not TTFT, and is not a performance result.

The historical warmup used the same 32,768-token and 8,192-token input lengths and 16-token output limit. This package uses its own synthetic seed text; original background corpus passages are not distributed. These text and installation changes have not been performance-tested.

## Quality and stability

Stability passed in the historical run. Quality stages were not run after HALT at the failed load gates. No quality outcome is inferred from the stability result or from the offline source-package checks.
