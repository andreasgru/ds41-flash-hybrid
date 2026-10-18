# Changelog

## v3.2.0-b10-v6 — source reconstruction candidate

- Add the B10 CPU kernel3 on the pinned DK/Arena base; retain K22b GPU expert decode, command arguments and memory limits. DK selectors remain exported but do not select kernel3.
- Reconstruct the eight-patch tree and add the independent B10 environment comparator. Preserve prior stage commits and tags.
- Report the fixed 18 October ten-start historical cohort separately for models1016 (n7) and1017 (n3), including both m8 readings, partial quality counts and separate arithmetic retries. Raw data remain internal.
- Native rebuilding and positive deployment remain untested; five historical full-load gates stay red.

## v3.1.1-k22b — documentation consistency

- Resolve conflicting validation wording across the six documents. Product code, tests, source patches and runtime pins remain unchanged.
- Cite the final 27.895-second test run and the actual interface/workspace evidence scope. Additional verification scripts and evidence logs are internal and are not published.
- v3.1.0-k22b internal only, superseded by v3.1.1-k22b (documentation consistency).

## v3.1.0-k22b — source reconstruction candidate

Status: **K22b source reconstruction and 18 offline real-input tests passed**. Static interface and actual print-path workspace counterchecks passed.

- Add the four-file SGLang overlay that activates GPU-resident expert B12X W4A16 decode; streamed prefill stays on CUTLASS and dense MXFP8 B12X remains active.
- Preserve K22 native-module selection, placement, server arguments, memory limits and selected environment values. All 12 selected extension switches now have readers. Workspace allocation remains chunk-sized with an unset/zero override; nonzero overrides are rejected.
- Reconstruct the seven-patch tree: 10,409 regular files, five symlink targets, four new overlay reversals, three originals matching K22, and the prior 56-file reversal. Three fail-closed controls passed. Runtime pins cover 62 sources and 80 files overall.
- Retain the portable 93-entry plus port / 74-argument profile and explicit checkpoint marker. The K22b WSL run passed 18 tests against the seven-patch series and 80 pins; the earlier K22 pass remains separate. Static interface and actual print-path workspace counterchecks passed.
- Record short-repeat quality/arithmetic results with the allowed arithmetic retry explicit, and distinguish longer aligned-stream plateau measurements from full-run or decode medians.
- Preserve reference chronology: numerical reference v4 at standard switch, v5 later under the unchanged gate. Keep historical K22 limitations and all five red full-load gates.

Native rebuilding, GPU inference, live service operation and full acceptance remain untested. A later B10 stage is separate and is not claimed by this tag.

The K22b documentation also clarifies retrospectively that historical K22 measurement values come from internal run logs and their raw data are not published. The existing K22 commit and tag remain unchanged.

## v3.0.0-k22 — source reconstruction candidate

Status: **source reconstruction and 18 offline real-input tests passed**. This entry describes the K22 source stage; it does not announce a validated native build or deployment.

- Extend the four r3 patches with K22 SGLang and KTransformers patches. Fresh application reproduces 10,408 regular files and five symlink targets; 56 cleaned files reverse to their pinned originals, with three fail-closed controls.
- Pass 12 archive/source and six runtime-configuration tests on WSL. The latter use genuine CPython 3.12.11, the original K22 native ELF and a genuine row-store library for offline ABI/configuration checks only.
- Compare 93 oracle environment entries plus the permitted port setting and 74 command arguments against independent K22 expectations; retain the historical r3 oracle unchanged. Runtime pin coverage is 60 source files and 78 files overall.
- Add DK CPU decode/K2EPLUS, V2b dense MXFP8 B12X and A1 checkpoint-expert swapping with budget 2, ring 32 and one stager.
- Keep existing placement, server options, token pools, NUMA assignment and portable source/package layout.
- Set the service memory limit to 480 GiB and startup available-memory requirement to 465 GiB; retain the existing reserve checks and 20 GiB anonymous/shared-memory margin, giving a 460 GiB stop boundary.
- Preserve historical inactive A1 GPU-expert B12X flags explicitly. Dense MXFP8 B12X is active; GPU expert B12X decode is absent from this stage.
- Expose the additional checkpoint-source marker `A1_SOURCE=ckpt`; no exact historical environment-byte equivalence is claimed.
- Separate historical K22 short-run measurements from the still-failed historical v2/r3 full-load gates. Native rebuild, deployment and new full acceptance remain untested.

This historical K22 tag did not include the later K22b or B10 stages.

## v2.1.1 — 8 October 2026

Public r3 release. README wording and checksum updates only; code, patches, configuration and tests remained byte-identical to v2.1.

## v2.1 — 3 October 2026

Initial r3 source release candidate with the compatibility baseline, neutral multi-user layer, portable build/launch tools and real-input regression suites. Historical full-load performance gates remained red.

Historical K22b verification record (product code at v3.1.1-k22b): the final archive passed 18 tests in 27.895 s (k22b-final-real-tests-v2-tests.log:509,511). The static interface check found 12 selected readers and detected the removed-reader and state-key regression controls (k22b-final-check_k22b_interfaces_v1.py.log:1). The actual print path accepted the default and zero workspace settings and rejected half-chunk, double-chunk and invalid overrides (k22b-final-check_k22b_workspace_v1.py.log:1). These additional verification scripts and evidence logs are internal and are not published. Native rebuilding, GPU inference and live-service operation remain untested; no pass for those paths is implied.

B10-v6 current-stage evidence: the first 18 offline tests passed in 28.133 s against eight patches and 81 runtime pins (63 source files). The independent B10 oracle retains 93 environment entries plus the permitted port and 74 command arguments; only the selected kernel value changes from 1 to 3 relative to K22b. Static interface checks found 14 readers and detected the removed-reader/state-key controls. The actual print path accepted default/zero workspace settings and rejected half-chunk/double-chunk/invalid overrides. These additional verification scripts and logs are internal and are not published. Native rebuilding, GPU inference and live service remain untested; no pass is implied.
