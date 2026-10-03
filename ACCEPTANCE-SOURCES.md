# Acceptance sources and measured load results

## Source and scope

The results below are aggregate values from the evaluator for one system load run on 28–29 September 2026. Its load stage completed; the overall process halted after the red load gates. The run exercised a 1+4-agent profile with synthetically generated prompts. The prompts were synthetic; the run itself and the reported request counts and timings were actual recorded observations, not outputs from an offline synthetic benchmark fixture.

The source report describes the evaluator outputs and an independent estimate from the request stream. For this run, the public archive includes aggregate values only. It does not include raw measurement data, request bodies, request traces, or host-specific paths and identifiers.

## Five red load gates

| Metric | Acceptance gate | Observed | Sample count | Result | Public method reference |
|---|---:|---:|---:|---|---|
| Generation throughput in the measurement band, all completion tokens | ≥ 40 tok/s | **35.11 tok/s** | 649 requests | **RED** | `METHODS.md`: recorded workload and measurement window; evaluator aggregate transcribed above |
| Main-agent first-token latency, p95 of follow-up turns in the band | ≤ 30 s | **57.88 s** | 58 | **RED** | `METHODS.md`: recorded workload and role-specific populations; evaluator percentile transcribed above |
| Main-agent first-token latency, p50 | ≤ 15 s | **15.745 s** | 58 | **RED** | `METHODS.md`: recorded workload and role-specific populations; evaluator percentile transcribed above |
| Sub-agent first-token latency, p95 | ≤ 30 s | **50.21 s** | 244 | **RED** | `METHODS.md`: recorded workload and role-specific populations; evaluator percentile transcribed above |
| Sub-agent cache-hit rate | ≥ 98% | **96.42%** | 243 | **RED** | `METHODS.md`: historical raw cache result and its population, separated from the future criterion |

The sample count is the number of requests or observations used for that metric. In particular, the sub-agent TTFT and cache metrics use different populations and therefore have different counts.

## Separate cache definitions

The recorded 96.42% gate is the historical subordinate raw cache ratio, not the later useful-prefix metric. It has not been relabeled or recomputed.

For a future acceptance run, calculate sum(min(C,U))/sum(U), with U the token longest common prefix with the preceding prompt plus generated output for the same agent and session. Compute main and subordinate roles separately from round 2 onward; each must reach 98%. The complete historical U values are unavailable. See METHODS.md.

## Halt and interpretation

The load stage ended with five red gates, so the process halted before the model and system quality stage. Those quality checks were not run; this report makes no quality-stage pass or fail claim. The red values describe the recorded load run under its stated workload and thresholds.
