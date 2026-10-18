# Changelog

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

Later K22b and B10 stages are planned separately; no implementation or result for them is claimed by this tag.

## v2.1.1 — 8 October 2026

Public r3 release. README wording and checksum updates only; code, patches, configuration and tests remained byte-identical to v2.1.

## v2.1 — 3 October 2026

Initial r3 source release candidate with the compatibility baseline, neutral multi-user layer, portable build/launch tools and real-input regression suites. Historical full-load performance gates remained red.
