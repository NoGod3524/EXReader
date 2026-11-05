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
Verifier written; controls and producer audit complete, see Result.
and artifact id (dispatch inputs `producer_run_id`, `producer_attempt`, `producer_artifact_id`).

## Result (2026-10-30)
Old producer 99c329b3 run 41084852566 attempt 1 completed with failure (native import dialog closure); retained, not audited.
Corrected producer ed24fec29f77f17ded6be843f1dfafb4e9e0456e, run 41086747699, attempt 1, completed success, artifact
f05-remaining-41086747699-1 id 12992621946, 953796 bytes, digest sha256:6bef126ec9b51a034a0397725dfc3261407594b48162069b38dc4ac58213c740
(official API metadata; head SHA and branch match). The producer diff from 99c329b3 only adds failure diagnostics; schema unchanged.
Audit: workflow_dispatch run 41088276333 attempt 1 at verifier source c7224e56, success. Verdict ACCEPTED (Linux GTK scope only),
39 controls all ok. Audit record artifact c07-conflict-audit-41088276333-1 id 12992965833. The ZIP was downloaded, unpacked and parsed
only inside Actions.
Not claimed: full F05, the 11-case recovery suite, book delete/restore, six platforms, physical devices.
## Result for source 73ac5ca9 (2026-10-30)
Producer 73ac5ca9f9a4aec0b5477122d05f7a0da1198543, run 41091287293, attempt 1, completed success, job and every step success.
Artifact f05-remaining-41091287293-1 id 12994257426, 982682 bytes, digest sha256:d27ed7509f64bdcc96b2241c4759f1cfade1b58e27ac22147b6a357049affec0
(official API metadata; head SHA matches; not expired). Audited separately from ed24fec2 with profile restore8 (eight checks plus the unchanged
29-check metadata regression record). Verifier source 31b43a5a; audit run 41093198048 attempt 1 success, ACCEPTED, 97 controls all ok
(controls-only push run 41092994575). Audit record artifact c07-conflict-audit-41093198048-1 id 12995390360. ZIP handled only in Actions.
Independently re-derived from raw files: Receive/group/delete-versus-update/two-unsafe-heads as before; book delete and restart-restore revision
linkage (distinct, same ids in result and observations); 5000-character refusal; 4096-multibyte byte counts and no-SQL setup; metadata regression
accepted for the same source/run/attempt with 29 unique checks and no UI claim. Missing metadata or host evidence is refused (negative controls).
Limits: the artifact holds no process or SQL record, so actual restart, sort-title equality and tombstone state rest on the producer's own
assertions and consistent observations (recorded as a non-gating row). Not full F05, not six platforms; ed24fec2 findings and its controls are preserved.