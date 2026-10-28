# Windows ↔ GTK offline conflicts and recovery

Status: in progress, not accepted.

## Provenance and scope

- Common source: `36fb8db3c088d665f87aac407f8e3739fa73e0f0`.
- Windows account source: `42445abd6dfeb312c8803d0a000a32f2a0459a15`, composed only the account owner/UI and Wave3 recovery differences from common ancestor `f34a4f27161061d08ecc40f5cebfb6f5018aa77f`.
- Reference D23 run: <https://github.com/NoGod3524/EXReader/actions/runs/40429896444>, historical source `b723a9a3a20af7b31729fa1a47b695b20a0c4b8f`.
- Feature branch: `codex/dot-win-gtk-conflict-recovery`.
- No changes to SDK `src/` or `include/`, default branch, tags, or Releases.

## Product gap

Both desktop metadata editors reported conflicts but blocked all edits. The metadata adapter deliberately rejects ordinary conflicting snapshots. An additive `reader_metadata_stage_book_resolution` entry point now stages an explicitly requested merge of complete concurrent book heads through the existing durable metadata intent and typed commands. Original ordinary staging remains unchanged. Missing/foreign parents, identity mismatch, and a head set changed before commit remain failures; old revisions are retained. Native UI requires a separate confirmation before enabling merged fields and still requires Save.

## Acceptance plan

The unchanged D23 Windows→GTK→Windows→GTK workflow checks and its original verifier are prerequisites in the same run. New stages restore only actual earlier host profiles, operate native UI offline on the same book/parent, reconnect through authenticated HTTPS, display concurrent versions, explicitly resolve on Windows, and verify reception/reopen on GTK. A native GTK tag deletion/restore roundtrip is checked separately and is not called book deletion. Original bytes, immutable revisions, executable identity and artifact state-chain identity are retained. The relay consists of sequential HTTPS snapshots, not a continuously running public service.

Separate native API tests use private copies of the actual GTK conflict database. They do not seed or replace the real hosts' state. They cover ordinary-edit rejection, incorrect original identity, abandoning an uncommitted resolution, exact committed retry, and stale-head refusal with retained intent.

## Runs and evidence

- First source `e46fed0d6f1c3f42a14fd44663aade4ea6f1266d`, auto-run <https://github.com/NoGod3524/EXReader/actions/runs/40650050430>. Windows build/retained checks and initial native upload passed; GTK build/current and original receive regressions and native receipt passed as of 07:40 UTC. Remaining result pending. This first round does not include all later safety/delete/restore coverage.
- No local build, test, syntax check, fixture generation, performance execution or artifact parsing was performed. All such execution is restricted to Actions.

First round terminal result: original four native relay stages and original verifier all passed. New Windows offline phase failed before editing because `SearchApp.dialog` searched for search controls instead of the already-visible metadata dialog. Failure job `122693678508`; original diagnostic artifact `12800665302`, digest `sha256:8fe8fdb3a66436790a92d37cc21e5850bbab972a9a3d61e8fc693709a483655c`. The new driver now explicitly reuses `MetadataApp.dialog`. No old assertion was altered. Same-source full rerun required.

Second round `3cfcacf6d6f71d6678df367903aaeefa1afd6b7a`, run `40656616824`: all original relay checks and Windows offline edit passed. GTK authored the second real offline revision with the same parent, then safely refused the downloaded profile account configuration because Actions artifact extraction flattened its private POSIX file mode. Failure job `122715707199` retains the original account state/requests. The driver now restores 0700 directories/0600 regular files only inside the copied runner-owned profile, verifying exact bytes before/after; production privacy checks are unchanged. This is not a database or path substitution experiment.
