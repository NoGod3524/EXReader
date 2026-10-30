# Claude C06 engine audit 20261030

Preliminary, independent audit of the original Windows observer producer. Not a P0 acceptance.

## Subject (bound identities)

| Item | Value |
| --- | --- |
| Producer source SHA | `b3f346570df7ca972c67232bb5ec3cfb2f6510d8` |
| Producer run | `41024553069` |
| Producer job | `engine` |
| Producer artifact | `12962888396` (`windows-engine-<sha>`) |
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

## What is NOT claimed

- `producer-asserted`: the consumer's `checks == 29`, `failed == 0` and timeout behaviour come from the producer's own `stdout.txt`/`receipt.json`. They are cross-checked for consistency only and are not independent proof of behaviour. `behavior_independently_verified` stays `false`.
- Native owner fix `7b26bf30` is unverified. No exact successful run has been supplied. The coordinator must provide that run; this auditor never reruns the producer and never modifies the engine.
- Old risks are preserved and nothing here is full P0 acceptance (`full_p0_acceptance: false`).

## Result

Pending the first GitHub Actions run on branch `claude/dot-c06-engine-audit-20261030`. Results and any retained failures are appended below.
