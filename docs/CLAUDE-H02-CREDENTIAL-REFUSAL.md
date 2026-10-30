# H02 Windows credential worker refusal (candidate evidence, no score)

Branch `codex/claude-h02-credential-refusal-20261030`, base `bd28d49`. Adds only `tests/claude_h02_credential_refusal/`,
`.github/workflows/claude-h02-credential-refusal.yml` and this file. No product, SDK, frozen provider or old test is changed.

## Read-only findings (source `bd28d49`)
- `extras/credentials/src/windows.c` maps `ERROR_NO_SUCH_LOGON_SESSION` (1312) to `EXR_CRED_UNAVAILABLE`.
- The host never impersonates: no `ImpersonateLoggedOnUser`/`SetThreadToken` anywhere in the tree. Each job runs on a
  `_beginthreadex` thread (`examples/reader.c`), so the credential worker uses the **process primary token**.
  A UI-thread impersonation test therefore proves nothing about the worker; the only faithful way to give the worker a
  logon session without Credential Manager is to start the real `EXReader.exe` with such a primary token.
- `acct_set_job` binds the root first, then `exr_credentials_put` (only when remember is on), then adopts the new secret
  only on success. On failure the previous in-memory secret is **not cleared**, so scenario S3 can fail (stale A secret
  stays usable). That is an expectation under test, not a prediction.
- `docs/READER-CREDENTIALS.md` records that S4U/low-integrity/VaultSvc-stop did not reproduce 1312, so this package uses
  a NETWORK logon token instead.

## Method
`token_host.py` creates a synthetic local user, `LogonUser(NETWORK)`, duplicates to a primary token and launches the real
packaged host with it (`CreateProcessAsUserW`, falling back to `CreateProcessWithTokenW`); every outcome is recorded.
It reports host process token type/logon type (via LSA), and samples new host threads during each Apply, recording
`OpenThreadToken` (1008 = no thread token = primary token in use). `probe_cred.py` is a **same-token API probe**, labelled
as such, showing the raw Credential Manager return codes; it is not host evidence.

## Known limit (not claimed)
The host does not expose the raw credential return code, so the raw `1312` inside the worker is not directly observed.
Evidence chain = host process token is Network logon + no worker impersonation + same-token probe returns 1312 + host UI
reports UNAVAILABLE. Seam proposal if a direct observation is required (needs separate authorization): an opt-in
diagnostic hook in `acct_set_job`/`acct_load_job` that logs `GetLastError()` of the first failing credential call.

## Scenarios
S1 no old secret + remember on -> refused, Sync disabled, zero server requests, book/revision/outbox unchanged.
S2 remember off -> session-only secret, Sync works. S3 A live, B (remember on) fails -> A must not silently sync as B;
book rows unchanged. S4 cancel/retry keeps books/heads. S5 restart -> secret gone, Sync disabled, no requests.
Markers scan covers only this package's temp files; no user credential store is enumerated.
Failures are kept as red evidence; no assertion is weakened.

## Status
Rounds used: see the delivery note in the session; all execution is GitHub Actions only. Consumes no formal acceptance item.
