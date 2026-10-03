# Test Input Inventory

## Scope

This inventory covers `tests/test_real_inputs.py` (12 test methods), `tests/test_runtime_inputs.py` (6 methods), `tests/data/recorded-r3.json`, and their product entry points.

Neither test file imports or calls `unittest.mock`, `patch`, `Mock`, or `monkeypatch`, and neither replaces a product function. Mutations edit product files inside temporary installation copies.

## Input Provenance

`test_real_inputs.py:43, 59–75` loads the package pins and requires four matching, SHA-checked archives in the supplied download directory. Lines `:85–105` copy the release patches, pins, runtime files, and two scripts into a temporary work directory. `scripts/prepare_sources.py:17–44` calls the product patch applier, extracts pinned dependencies into staging, and publishes the sources.

`test_runtime_inputs.py:100–123` requires the target interpreter, native artifacts, four archives, and the recorded oracle. Lines `:152–234` make a temporary release copy, prepare real source archives through the product CLI, copy the supplied native artifacts, and invoke the product CLI to create the build receipt. These are working copies of real inputs; they do not contain replacement servers or functions.

`tests/data/recorded-r3.json:3` identifies its configuration values as neutralized values from an independently recorded live invocation, captured before release generation and containing no request data. `test_runtime_inputs.py:122–132, 287–313` validates the oracle's structure and size, then compares the actual CLI result with it. The expected values are not read from the launcher result under test.

## Inventory of the 18 Methods

| Test location | Input, mutant, or copy | Provenance and classification |
|---|---|---|
| `test_real_inputs.py:226, 230, 235` | Positive patch application | Real pinned archives and release patches; product function `apply-series.py`, followed by the real runtime-pin check. |
| `test_real_inputs.py:237, 240, 248` | Positive source and dependency preparation | The same real archives; product CLI `prepare_sources.py` and its staging/publish path. |
| `test_real_inputs.py:250, 264–277` | Reserve, duplicate reserve, release with wrong token, correct release | UUIDs and paths are ordinary API inputs. The real `Reservation.update` in `scripts/gpu_lock.py:19–49` writes every lock byte. No service is represented. |
| `test_real_inputs.py:279, 285–295` | Wrong patch digest | A pin row in a copy of the real patch list is changed; the patch itself comes from the release. The product applier refuses it before publication. |
| `test_real_inputs.py:297, 302–315` | Wrong hunk context | A real patch file is changed in a temporary package copy; only its digest is then refreshed so the real patch command reaches the context failure. No mock is used. |
| `test_real_inputs.py:317, 321–325` | Empty series | The real `series` file in the working copy is emptied; the product function must fail closed. |
| `test_real_inputs.py:327, 331–338` | Duplicate series entry | The first real series entry is duplicated in the copied manifest; this corrupts the real manifest structure. |
| `test_real_inputs.py:340–374` | Traversal in series and diff paths | A real series entry and a real patch file in working copies are changed to contain `..` paths. The diff file's digest is refreshed so the path check itself is exercised. |
| `test_real_inputs.py:376–400` | Missing and corrupted archive | The missing-archive case uses an empty temporary download directory. The SHA failure flips one byte in a copy of the real pinned archive (`:192–209, 392–400`). |
| `test_real_inputs.py:402–411` | Missing central pin | The real `upstream.json` is removed only from the package copy. |
| `test_real_inputs.py:413–427` | Duplicate central pin | A real pin row is duplicated in the package copy; the real product applier checks it. |
| `test_real_inputs.py:429–455` | Existing output and missing dependency after patching | The output sentinel at `:434–441` is handwritten test content in a temporary target directory, used only to check preservation of existing output; it replaces no product function and is not an operational format. The second case copies real archives but omits one real pinned dependency (`:444–455`). |
| `test_runtime_inputs.py:315–326` | Resolved environment and launch command | Ordinary invocation of the real `start-standard.sh --print-command` path, compared with independently stored live values. The shell passes through to the real resolver (`scripts/start-standard.sh:5–8`, `scripts/start-tp1.sh:5–12`, `scripts/resolve_launcher.py:13–19, 67–89`). |
| `test_runtime_inputs.py:328–370` | Missing directory export | In a copy, the real resolver mapping is removed (`:336–363`); the same product CLI invocation must still resolve with rc 0 (`:364–368`). The independent oracle then detects the missing output (`:369–370`). This is a producer mutant in a copy, not an injected replacement result. |
| `test_runtime_inputs.py:372–412` | Traversal, symlink, source-byte, and native-byte mutants | `../outside` is an ordinary path parameter to the product API (`:373–378`). The symlink points to a real copied native artifact (`:379–387`). Source and native bytes are changed in release copies (`:389–412`); the unchanged resolver CLI checks the real pins and receipt. |
| `test_runtime_inputs.py:413–426` | Loopback and invalid URL values | Ordinary function inputs to the real `warmup.local_base` URL check; no HTTP response, server, tokenizer, or model is replaced. This method checks URL resolution, not the warmup operating path. |
| `test_runtime_inputs.py:428–460` | Foreign lock record | Owner, UUID, run, and token values are ordinary API inputs. The real `Reservation.update` writes both records; the foreign bytes are taken from its output and appended (`:450–460`). There is no handwritten lock row or replacement service. |
| `test_runtime_inputs.py:462–495` | Missing dependency archive and transaction cleanup | Real archives are linked or copied to a fresh temporary directory, with one archive omitted (`:471–479`). The real `prepare_sources.py` CLI must fail and clean staging (`:480–495`). |

## Uncovered Operating Paths

These methods check launch configuration, the build receipt, and source pins. They do not start a real model server. Product preflight calls runtime and model readiness checks plus GPU, systemd, and port checks (`scripts/supervisor.py:65–80`); service start and supervision begin at `:82` and `:116`. Positive model-shard readiness (`scripts/verify_model_shards.py:296–330`), real tokenizer/warmup HTTP requests (`scripts/warmup.py:53–84`), and the native build entry point (`scripts/build-native.sh:1–39`) are not exercised here. Real model, server, tokenizer, positive readiness, and native build remain untested.

## Revision 2.1 additions

The existing lock lifecycle method also uses real owned run directories and actual valid/dangling symlinks; run_path must reject both before resolution. The DIR producer mutant now updates the copied resolver pin and invokes the genuine build receipt producer after removing its copied receipt. This deliberate mutant rebinding reaches the independent configuration oracle without replacing a function or hand-writing a receipt. The suite still has 18 methods. Earlier line references are from revision 2; the added bodies shift later test lines.
