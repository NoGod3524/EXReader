# F10 credential, privacy, recovery and TLS acceptance

Branch: `codex/ledger-f10-fable`; PR: https://github.com/NoGod3524/EXReader/pull/227 (unmerged).

## Windows identity and TLS

[Actions 43831439309](https://github.com/NoGod3524/EXReader/actions/runs/43831439309), source `02c5cd578d2a585ffa39a196a7e48d15114c9a98`, passed. The retained ZIP was downloaded through the authenticated GitHub API and its SHA-256 and byte length recomputed against the artifact metadata. `_audit/43831439309.json` records the retained files and hashes.

- Cross-user isolation: a disposable non-admin local account, `LogonUserW`, profile loading and impersonation. Shell checks prove the other SID cannot read the runner's Credential Manager record, open `sync.cred` (error 5), or decrypt its DPAPI blob. The installed credentials module independently proves both vaults are isolated and each account can round-trip its own record.
- Credential Manager UNAVAILABLE: a real `LOGON32_LOGON_NETWORK` token is impersonated in each probe. Both observe platform error 1312. The module returns UNAVAILABLE for put/get/delete. In that token DPAPI also refuses access, so the shell safely refuses the save and leaves no credential file or Credential Manager record. Separately, `check_sync --privacy` forces `EXR_SYNC_CREDENTIAL_BACKEND=dpapi` and proves successful file save/load, then restores the default backend and proves Credential Manager save/load.
- Recovery: the same privacy run verifies protected owner/DACL, a real interrupted credential write, original preservation, atomic-publish refusal, and startup cleanup after abrupt process exits while retaining live writers and unsafe/unrelated files.
- TLS: both the shell WinHTTP path and installed WebDAV client pass the seven public-PKI cases. A generated CA signs a DNS-SAN-only server certificate. `exr-f10.test` and a wrong-name alias resolve to the runner's non-loopback address. Both clients reject the untrusted CA, accept after installation in system trust, and reject the wrong host. Origin-side observations prove the trusted request arrives from the non-loopback peer, rejected cases send no HTTP request, and no Authorization header is sent. Public certificates are retained; private keys stay outside uploaded output. The harness removes its hosts entries, CA trust and firewall rule.

## Windows account host

The host now declares `EXR_READER_TEST_DRIVERS` default OFF and forwards it to the native targets; this workflow explicitly enables it. The driver waits for `shelf_need_refresh` as well as the worker, so a completed import/delete is observed after its queued product shelf refresh. No acceptance action or assertion was removed.

Run 43830316729 first exposed the queued refresh race. Run 43831145057 then passed all 158 actions and eight screenshots, and exposed obsolete retained-product assertions: catalog schema 1 instead of current schema 3, and SDK 3.40.0 instead of the sealed original report's SDK version. Those expectations are corrected for the next run.

[Actions 43831953731](https://github.com/NoGod3524/EXReader/actions/runs/43831953731), source `dcff99640aa59f490c4506482265400a91410c77`, passed all 158 actions and eight screenshots. The ten-product regression then passed its repair/refusal/retry driver phases but failed at `check_windows_product.py:166`: `Owner did not become idle`. That observer requires the removed cancel control 117. Current `create_controls()` creates shelf/search/refresh, account/metadata, notes and page controls; it no longer creates the old path/import/cancel controls 101/102/117. The worker, shelf, metadata and account test helpers also still refer to those removed controls. The workflow stopped before its 32-check real Windows account suite and its strict summary rejected the failed account job. The UI158 report is retained as a passed sub-result of a failed run; it is not recorded as a successful workflow.

Remaining F10 gap: migrate the Windows account/retained test drivers to the current real native UI, then obtain a successful account suite and strict summary. The current account suite has not been rerun successfully against `windows_accounts.inc`; F10 stays partial. No checks were removed, bypassed or marked successful.

## Linux GTK

The original shared run 43828822348 failed in F09's accessibility collection because `build/a11y-evidence/result.json` was missing; its F10 account suite still passed 48 checks. The dedicated F10 workflow retains the original installed consumers, GTK startup-scavenger regression, and unchanged 48-check real account suite, and adds public-PKI/private-CA TLS. The original F09 workflow remains unchanged.

[Actions 43831439414](https://github.com/NoGod3524/EXReader/actions/runs/43831439414), source `02c5cd578d2a585ffa39a196a7e48d15114c9a98`, passed. Retained reports prove all 48 account checks (real unlocked/locked GNOME Secret Service, explicit session-only behavior, restart, leak checks and native HTTPS), the real abrupt-exit startup cleanup, seven public-PKI cases and all private-CA non-loopback cases. `_audit/43831439414.json` records verified ZIP provenance and retained-file hashes. The earlier run 43830316796 also passed.

## Local checks and scope

- `cmake --build build/shell --target check_sync --parallel 4`: exit 0.
- `cmake --build build/credential-probe --clean-first --parallel 4`: exit 0.
- Standalone standard-library TLS fixture check: trusted SAN succeeds; wrong SAN and unknown issuer are rejected.
- Required prepush script: all code/docs checks pass. CI hygiene: violations=0.
- Catalog denominator and groups remain 108 = foundation 12 + host 84 + final 12. Only F10 is updated; F08/F09 and every other requirement are retained.

A full local MinGW all-target build also encounters the pre-existing F09 `AccessibleObjectFromWindow` function-pointer-cast warning promoted to error. F10 targets compile successfully; UI acceptance comes from CI artifacts. No local UI result is claimed.

Final F10 state: **partial**. Credential isolation, forced fallback, real UNAVAILABLE, Windows/Linux TLS and GTK recovery/Secret Service are verified in the successful runs above. The remaining Windows account acceptance gap is explicit.
