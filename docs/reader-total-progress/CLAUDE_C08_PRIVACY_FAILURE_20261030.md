# Claude C08 — Windows Credential Manager refusal / plaintext persistence (2026-10-30)

Base `5963488997a7169f2ae40a8d6d33abae15eb3f36`, branch `claude/dot-c08-privacy-failure-20261030`.
Owned new paths only: `tests/reader_privacy_failure_20261030/**`,
`.github/workflows/claude_c08_privacy_failure_20261030.yml`,
`scripts/audit/claude_c08_privacy_failure_20261030.py`, this file. No production, SDK, Apple or old-test change.
`AGENTS.md` does not exist at the base; `DOT_APPLE_TASK_20261029.md` is not in the base tree (read from another worktree, unrelated to this package).

Not F10 acceptance, not full P0. Results bind only to the run/attempt named below.

## Gap being attacked

C04 (`CLAUDE_DOT_C04_20261030.md`) showed the Windows Credential Manager round-trip works, but its four
refusal mechanisms (low integrity, S4U task, VaultSvc stopped, WinRM network logon) never made the store
refuse, so "refuse without plaintext fallback" on Windows stayed undemonstrated.

## Design

One `windows-2022` job. A disposable local user is created with a run-time random password. `c08-probe.exe`
(links only the installed, unchanged `extras/credentials` package) calls `LogonUserW` for that user with each of
`network`, `network-cleartext`, `batch`, `service`, `interactive`, impersonates the resulting logon in its own thread and
runs the real module `put` / `get`; it also reports the raw Win32 error of a direct `CredWriteW` with the module's
persistence (diagnostic). The module maps `ERROR_NO_SUCH_LOGON_SESSION` / `ACCESS_DENIED` / `NOT_SUPPORTED` to
`UNAVAILABLE`; a network-type logon has no credential-capable session, which is the natural real trigger.

* `refusal_proven` is true only if the real module returned `UNAVAILABLE`/`IO` for put and a failing get, under a
  real logon of the throw-away user, and every sweep is clean.
* After each attempt the sandbox (contents and names), probe streams, TEMP (must stay empty), the runner user's
  `cmdkey /list` (our target must be absent) and credential-store files that changed during the run are searched for
  the secret and the password in raw, hex, base64 (3 alignments, std/url), percent and UTF-16LE form (matching only).
* If a logon type unexpectedly stores the secret, the probe deletes it in the same impersonation and the sweep checks it.
* The synthetic user and its profile are removed and checked at the end.
* Scanner self-test plants each encoding and a file name and requires detection; a clean tree must pass.
* No mock or fault injection is used as proof. Nothing real is read; no system security setting is changed.

## Evidence

| source SHA | run / attempt | result |
|---|---|---|
| `2485c26f18499ffed27ce0a0a82462c57c35603d` | 41086810708 / 1 | failure (retained): build ok; harness failed before any attempt — `net user` prompts for passwords over 14 characters, user never created, no refusal attempted |
| `40982f689062a9c713045668603cfe8e2fea28ce` | 41087173303 / 1 | success; `refusal_proven: true`, all harness gates true (windows-2022, image 20261026.347.1), artifact `claude-c08-privacy-failure-41087173303-1` |

Run 41087173303 (fix cycle 1 of 2; the fix only shortened the synthetic password and answered the prompt):

| logon type (throw-away user, impersonated) | real module put / get | direct `CredWriteW` | sweep |
|---|---|---|---|
| network | `UNAVAILABLE` / `UNAVAILABLE` | error 1312 (`ERROR_NO_SUCH_LOGON_SESSION`) | clean |
| network-cleartext | `UNAVAILABLE` / `UNAVAILABLE` | error 1312 | clean |
| batch | LogonUser error 1385 (right not granted) — no attempt | – | clean |
| service | LogonUser error 1385 — no attempt | – | clean |
| interactive (no profile loaded) | `UNAVAILABLE` / `NOT_FOUND` | error 1312 | clean |

* Proven (this run, this platform only): the real Windows Credential Manager refuses to store for a logon session
  that has no credential-capable session, the installed unchanged module reports `UNAVAILABLE` for put and does not
  return a secret for get, and no copy of the synthetic secret or password appeared in the sandbox (names and
  contents, all encodings), probe streams, TEMP (stayed empty), the runner user's `cmdkey /list`, or any
  credential-store file that changed during the run. The synthetic user was removed and verified gone.
* The refusal is a real OS error from the real store, caused by impersonating a real logon of a throw-away local user;
  no mock, fault injection, service stop or security-setting change was used.
* Not proven: the application-level flows (WebDAV/OPDS account save, sync, export) refusing without plaintext fallback —
  only the credential module's own put/get and the sandbox are observed; the module itself writes no file. A normal
  interactive desktop logon with a loaded profile (positive control) was not exercised, so the success path of this
  user is not shown here (C04 shows it for the runner user). Batch/service logons need rights this runner does not
  grant, so they remain untried.
* Gate semantics: the workflow is green when the harness is clean; read `refusal_proven` in
  `summary.json`/`dynamic.json`, not the job colour, for the verdict.

## Proposed smallest product testing interface (not needed for the credential module's refusal; kept for app-level flows)

For application flows, the smallest useful interface is a way to start the host with a credential store known to refuse
without a mock, for example the host accepting a test-only launch option that runs the credential calls under the same
impersonated network logon this probe uses. The module-level proposal below is no longer required:

A compile-time-off, test-only seam in `extras/credentials/src/windows.c`: an environment-selected persistence level
(for example `EXR_CREDENTIALS_TEST_PERSIST=session|enterprise` honoured only when built with
`-DEXR_CREDENTIALS_TESTING=ON`) so a real `CredWriteW` can be asked for a persistence a network logon is known to refuse.
This keeps the failing call real (the OS refuses) and only chooses what to ask for. A pure error-injection hook would
exercise the mapping, not the real store, and must not be cited as refusal proof.
