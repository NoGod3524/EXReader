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
book rows unchanged. S4 a real cancel (a PROPFIND is held open, Cancel pressed, note `同步已取消`, Retry enabled), then
Retry completes and keeps books, revision heads (computed from the retained wire `parents`, non-empty) and every revision
row. S5 restart -> secret gone, Sync disabled, no requests. S6a/S6b: A's network session is really cancelled / failed
(HTTP 500, note `同步失败`), saving B with remember on is refused, Retry is pressed -> zero new server requests and
books, heads, revisions and outbox unchanged.
Markers scan covers only this package's temp files; no user credential store is enumerated.
Failures are kept as red evidence; no assertion is weakened.

## Status
All execution is GitHub Actions only. Consumes no formal acceptance item. Extra correction rounds were authorized by the user.

| run | source | result |
|---|---|---|
| 41142853013 | b1fe263f | probe red: missing 64-bit ctypes signatures (harness bug) |
| 41142963420 | 6f3641f4 | probe green; host configure red: stale recipe needs OPDSHash prefix |
| 41143217136 | 2187d102 | probe green; `product-configure` still needs OPDSHash prefix |
| 41144628910 | 25c126db | cancelled (superseded by known harness bugs) |
| 41144831499 | 9bf2687d | host ran: 12/14, S3 red, thread sampler n=0 (harness timing) |
| 41145383847 | 0303bde3 | host ran: **13/14**, only S3 red |

Corrections 3-5 touch only this package: hash-only OPDSHash install before `tests/windows_sdk342/build.py`; pass a `Path`
to the compact picker; read the host token from the shim launch; keep the thread sampler running until each Apply
result / session sync finishes (more samples, same assertion).

Latest run 41145383847 attempt 1: probe job 124369135530 green, host job 124369276105 red.
Artifacts: probe 13020344922 (832 B, zip sha256 4a259f4c10899091fa7b8b8efd56cf2c2fc11446bd65999128f277cc537419cd);
host 13020472255 (1556 B, zip sha256 c496cf2d4247448c88090db8bb7bd7050efbd54ecdc305ea1e50889fae17d6df).

Green: host primary token is Network logon (session 2); S1 refused as UNAVAILABLE with Sync disabled and zero requests,
book/revision/outbox unchanged; S2 session-only secret syncs authenticated (272 requests); S3 failure reported
UNAVAILABLE and book heads unchanged; S4 cancel/retry keeps books and heads; S5 restart has no secret, Sync disabled,
no requests; no synthetic marker in package temp files; 3 worker threads sampled, all without a thread token (1008).

**Kept RED (product defect):** `s3_failed_B_save_does_not_let_stale_A_secret_sync_as_B` - after saving B fails, Sync
stays enabled and 257 requests go out with the stale A secret. Matches the read-only finding in `acct_set_job` (old
in-memory secret not cleared when `exr_credentials_put` fails). Not fixed here: product change is outside this package.

### Run 41157434078 (source 36e997f8, S4 tightened + S6 added, pre-fix product): 22/26
Probe job 124407214233 green; host job 124407323865 red. Artifacts: probe 13025542441 (831 B, zip sha256
1b1fa895b3ec31d6d0fd6d6a8e06b748d771c4ec217dae00ed85bbc2fa064a93); host 13025203757 (2108 B, zip sha256
1b0e826ff7fe19bb2a21251c0b03cff253c68c276d13c035570ed6ddf5cc4dc2).
S4 green: the cancel provably landed (PROPFIND held, note `同步已取消`, Retry enabled), Retry completed, books, the
single non-empty head and every revision row unchanged. S6a/S6b: A's session really cancelled / failed, B refused as
UNAVAILABLE, but **Retry stayed enabled and sent 256 / 257 requests (GET, PROPFIND) with A** - kept RED, as is S3.
Also red in this run only: `worker_threads_observed_without_impersonation_token` (n=6); the job log prints no per-sample
detail, so the cause is not established (it was green with n=3/6 in runs 41145383847, 41146619827, 41157486595).
