# Claude C06 engine audit 20261030

Preliminary, independent audit of the original Windows observer producer. Not a P0 acceptance.

## Subject (bound identities)

| Item | Value |
| --- | --- |
| Corrected producer SHA (primary) | `83b0bd1c1d2d697973ef43272d42b34cc58baa7f` |
| Run / attempt / job | `41087206035` / 1 / `engine` job id `124171372303` |
| Artifact | `12991588693`, 250290 bytes, zip SHA256 `daa5f7b6ab686de1340a73dd80d626e01fd8157487447da651c2cb7ed3c4e913` |
| Retained original producer (cross-check, not replaced) | SHA `b3f346570df7ca972c67232bb5ec3cfb2f6510d8`, run `41024553069`, artifact `12962888396` |
| Auditor | `scripts/audit/claude_c06_engine_audit_20261030.py`, run only by `.github/workflows/claude_c06_engine_audit_20261030.yml` |

## What is verified independently

The auditor downloads the original artifact in GitHub Actions and checks, from API metadata and raw bytes:

- run id, head SHA, event, workflow path, conclusion and run attempt;
- the `engine` job (head SHA, run id, attempt, required steps and upload step succeeded);
- artifact id, name, non-expiry, owning run, head SHA, creation inside the job window, and the zip digest when GitHub supplies one;
- observer is an x64 PE image, engine library is an `ar` archive, provider maps and private fixture bytes match;
- receipt SHA, run, attempt, worker/library/private file hashes recomputed from the bytes, not copied;
- admission file hashes recomputed against Git blobs at the producer SHA, and change list limited to owned paths;
- installed headers equal the Git blobs at the producer SHA.

Missing original evidence, an unavailable artifact or an unavailable Git blob fails the audit.

## Rejection controls

`tests/migration/claude_engine_audit_20261030/test_controls.py` builds a valid synthetic evidence set and requires each mutation to be rejected for its own reason: wrong SHA, run, attempt, job, artifact id/name, expired artifact, artifact outside job window, digest mismatch, each deleted required file, tampered binary/library/fixtures, forged receipt and admission, extra files, claimed full P0 or admission, forged Git-blob hash, unsafe zip members.

For the corrected producer it additionally pins job id, artifact size and zip SHA256, and binds the boundary suite evidence (`boundary-receipt.json`, `boundary-stdout.txt`, `wrong-launch.bin`) to the same SHA, run and attempt.

## Reconciliation with DOT_APPLE_TASK_20261029.md

That file is the Apple repair handoff; it binds this package only through its general rules, all of which prior work already met: every build, syntax check (`py_compile`, `ast.parse`), test and artifact download/unpack/parse ran only in GitHub Actions; no credentials; feature branch only, no default/common branch push, PR, tag or release; no edits to the shared SDK, engine, C1/C2/C3/Windows migration sources or the staged `exreader-resume-20261029` worktree; failures retained. No conflict found. Two notes: `AGENTS.md` does not exist at the task file's repo or on the VM, so it could not be read; and the file's Apple-specific scope (iPhone/iPad, 39+12 cases) is outside this package.

## What is NOT claimed

- `producer-asserted`: the consumer's `checks == 29`, `failed == 0` and timeout behaviour come from the producer's own `stdout.txt`/`receipt.json`. They are cross-checked for consistency only and are not independent proof of behaviour. `behavior_independently_verified` stays `false`.
- Native owner fix `7b26bf30` has no run of its own supplied. `83b0bd1c` descends from it and is audited separately, but that is provenance only. This auditor never reruns the producer and never modifies the engine.
- The boundary suite reports `test_only_fault_injection: true`; the receipt's `production_test_hooks: false` is a producer assertion. Neither is independent proof.
- No COMMIT or SDK admission is claimed.
- Old risks are preserved and nothing here is full P0 acceptance (`full_p0_acceptance: false`).

## Result

Retained record, first auditor version (original producer only): auditor commit c4d0acaa00e6046369ee8ba3b8481f8d981fa2b6, run 41086772004 attempt 1, artifact 12991438238; 8 controls OK; original run 41024553069 provenance verified (zip sha256 819b770ce3822145b1cbdcc15dd59772903c88a2e266f4d81bbef5a02e3ea364). Final doc commit e2e3cd35 run 41086923996 attempt 1 also success.

Corrected-producer audit: pending the Actions run of the extended auditor; results appended below.
