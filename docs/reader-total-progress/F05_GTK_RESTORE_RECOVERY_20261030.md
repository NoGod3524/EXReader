# F05 GTK interrupted Restore recovery candidate
Base 7f15fe49374cd9389e2106837351d4bbd5e56113.
Branch codex/dot-f05-gtk-restore-recovery-20261030.
Explicit user approval 2026-10-30T22:55:14Z: isolated new test/workflow/document, one Linux Actions run.
Only these three new paths are owned; product, SDK and old tests remain untouched.
The unchanged original 29 metadata + 8 GTK + 9 installed paging checks run in full.
The new ten checks are separate, not a replacement. Original job budget stays 80 minutes.

## Native recovery boundary
One actual GTK host imports a private synthetic text original through its native chooser.
Existing SDK-verified metadata preparation performs the normal bootstrap.
Real DELETE and RESTORE confirmation cancellation must leave catalog/history/outbox and pending state unchanged.
After real deletion, native Restore is held by a separate BEGIN IMMEDIATE on the private product DB.
The harness never writes SQL data or alters SDK files. It observes a durable pending file within
the existing three-second staging bound, then waits for the actual Recover book edit window
while the normal five-second database busy timeout refuses the transaction.
Only after that observable refusal does it kill the process. It releases its lock in finally,
reopens the same profile and verifies identical intent bytes and unchanged tombstone state.
First cycle explicitly Discards; second cycle explicitly Retries. Exactly one restore revision
and outbox row must result, bound to the delete parent and unchanged metadata/SDK mapping.
A further restart must not duplicate it and the native SDK original must still open.

The helper's Return waits for not-busy, so Restore confirmation uses native alt+o;
pending observation does not use Session.wait, which suppresses busy observations.
Window 35s, staging 3s, shelf/import 60s, process termination 15s retain existing bounds.
Evidence contains phase snapshots, raw private pending bytes, screenshot(s), binary/source/run/attempt
identity and file hashes; failure results are retained and no failure is converted to success.

## Limits
Not a test of original bytes changed or lost after staging. Retry original re-verification
is a separately identified source-level question, not proven safe by this scenario.
No GTK pagination, multi-head Restore, six-platform F05, formal acceptance promotion or P0 completion.
Formal acceptance remains 95/108. No result claimed before the one authorized run completes.
