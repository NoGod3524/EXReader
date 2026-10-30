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

(filled in after the run — see handoff; failures are retained)

## Proposed smallest product testing interface (only if refusal stays unproven)

A compile-time-off, test-only seam in `extras/credentials/src/windows.c`: an environment-selected persistence level
(for example `EXR_CREDENTIALS_TEST_PERSIST=session|enterprise` honoured only when built with
`-DEXR_CREDENTIALS_TESTING=ON`) so a real `CredWriteW` can be asked for a persistence a network logon is known to refuse.
This keeps the failing call real (the OS refuses) and only chooses what to ask for. A pure error-injection hook would
exercise the mapping, not the real store, and must not be cited as refusal proof.
