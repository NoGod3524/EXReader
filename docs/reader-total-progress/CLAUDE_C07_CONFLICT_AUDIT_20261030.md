# C07 independent conflict audit — 2026-10-30

Base 343bb94eb6513beaf5b344e7828342f6602a3b7b; branch claude/dot-c07-conflict-audit-20261030.
Owned paths only: this document, `scripts/audit/claude_c07_conflict_audit_20261030.py`,
`.github/workflows/claude_c07_conflict_audit_20261030.yml`, `tests/reader_f05_independent_audit_20261030/**`.
No GTK product, native driver, SDK or old assertion is edited. The C03 author validator is not used as an oracle.

## Target
Native producer 99c329b3839d00b986673c87fcaebf13b04bfee7, run 41084852566 (`f05-remaining-<run>-<attempt>`).
At the time of writing the run was reported in progress; nothing here claims it passed.
Old C03 c0ec6edf run 41032783657 is background only.

## What the verifier does
1. Authenticates the original Actions ZIP through the API: run completed/success, attempt, head SHA, artifact id/name,
   not expired, size, SHA-256 digest, host job and the Receive step success, safe archive members.
2. Re-derives verdicts from raw files (`result.json`, `requests.json`, `wire.json`, `build.json`, logs); rehashes
   `build.json` and the revision consumer; scans every file for key material and Basic credentials.
3. Per scenario: Receive absent-then-present with a real `receive_seen` counter; distinct delete and update siblings of
   one common head; two identical unsafe heads with no automatic winner; each sibling PUT by its author and GET by the
   other peer, with matching wire digests.
4. Runs an identity control and named negative controls (wrong SHA/run/attempt, planting, non-GTK host, stale hashes,
   never-clicked Receive, single head, safe projection, missing peer fetch, leaked secrets, in-progress run, bad digest,
   traversal members). Controls use synthetic data and validate the verifier only, not the product.

## Boundaries
- Scope is Linux GTK, group delete versus rename. The earlier 11-case conflict-recovery suite is not covered by this
  artifact and stays unverified here. Book delete/restore, six platforms and physical devices are not claimed.
- The packaged binary is not shipped in the artifact, so its digest is only compared to `build.json` as a non-gating
  observation. Parent equality for the siblings is taken from the producer's recorded observation.
- Every syntax check, build and test, including the ZIP download and parsing, runs only in GitHub Actions.

## Status
Verifier written; first Actions result pending. Producer audit awaits coordinator-supplied successful run id, attempt
and artifact id (dispatch inputs `producer_run_id`, `producer_attempt`, `producer_artifact_id`).
