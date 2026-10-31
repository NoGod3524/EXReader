# F02 Windows to GTK original-transfer candidate

Base cfdaf6a4531548be63b4dd0c2bccd6b050a93124.
Exclusive branch codex/dot-f02-win-gtk-transfer-20261031; seven new files only.
One explicitly approved Actions run: Windows240min -> GTK150min -> authentication20min.
No automatic repair run. No production/SDK/old suite changes or local execution.

The original Windows-host and GTK SDK342 workflow build/regression steps are retained in the new workflow.
Windows original SDK identity check remains; GTK's historical branch-limited source guard is not falsely reported passed.
Instead this additive package binds the current exact base and unchanged product/SDK/original test trees with source_lock.json.
The public OPDSHash owner is installed explicitly before either existing producer. Existing installed SDK inspector source is reused.
The old GTK standalone artifact-authentication job is not run here; the approved new 20-minute cross-host audit replaces it. No claim is made that the old full workflow or its artifact-authentication gate passed.

Sender: fresh native Windows profile, actual compact file picker, visible reader, actual account UI and HTTPS Sync.
Only immutable bytes actually received in authenticated server PUT requests populate the exported server store.
The book revision and original path/hash/size are joined to sender product book_key and local SDK mapping.
The closed sender's installed public SDK source is independently read back.
Six sender checks; no direct database writes or fake remote fixture revisions.

Receiver: restore the byte-identical server storage from the authenticated same-run/attempt sender artifact.
Fresh GTK profile uses native account scan, explicit Receive, shelf activation, actual GET/download/import/open.
The retained SDK original is read back with the host closed. A new process must reopen offline after this private
test profile's download cache is removed and the test server is stopped. Seven receiver checks.
Local SDK row numbers are independent: only format+original SHA256 is cross-device identity.

Authentication binds both original job conclusions, exact artifact IDs/names/source/attempt/size/digest, ZIP
bytes and strict member inventories. ZIP limits:5000 entries,64MiB per member/archive,128MiB expanded total;
reject unsafe paths, normalized/casefold collisions, symlink/special/encrypted entries before extraction.
Both actual host binaries and inspector binaries remain with their receipts; no artifact executable is run in the audit.
One positive real-evidence chain and eight semantic mutations retain failure reasons.
No mutation changes production data or bypasses the original producer's failure.

All credentials are random synthetic, session-only, never printed. Fresh per-job test CA trust is removed after the
host closes; CA private keys and host profiles are outside uploaded evidence and removed. Server receipts contain
only auth-match booleans, method/path/status/body hashes and lengths. The exported synthetic evidence is scanned
against the in-memory credentials and TLS key in finally on success and failure. Only a successful scan sets
safe_upload=true; the workflow refuses to upload this payload otherwise. Reports expose only fixed stage/error type,
not arbitrary exception or command text. Nested cleanup always removes test trust/private profiles even when host close fails.

The two hosts use HTTPS against the same logical DAV store relocated between jobs through original artifact bytes.
This is NOT a simultaneous continuously-online public server or a production deployment test. No public service rented.
No credentials/system-account/owner policy changes. No H02/H03/H04/J03/C02 scope takeover.
Status pending: this package does not presume a product bug, does not promote F02, and leaves95/108 unchanged.

## Sole approved run: failed before native transfer (2026-10-31 03:35:55Z observation)

Tested source: e50c97f7acfa09afb8a9eae8a4f138586248fb1c.
Run [41164667579](https://github.com/NoGod3524/EXReader/actions/runs/41164667579), attempt 1, started 03:30:35Z.
Windows job 124429548817 failed at 03:33:29Z; GTK job 124430200817 skipped;
authentication job 124430199903 failed its upstream-result guard at 03:33:38Z.

Observed successful steps: exact-seven-file/frozen-source admission, public OPDSHash build/install,
original Windows SDK identity8357 guard, display preparation, automation installation.
Inside the original build step the log explicitly reports "sdk-install success".
The following product configure fails at apps/reader/store/native/CMakeLists.txt:95:
"Original hash prefix must be canonical", followed by "RuntimeError: product-configure exit=1".

This is a test-workflow dependency-prefix orchestration defect, not evidence that cross-host transfer failed.
The package supplied EXREADER_ORIGINAL_HASH_PREFIX using the raw Windows github.workspace plus a slash suffix;
the unchanged product guard requires exact equality with CMake file(REAL_PATH). A separately authorized correction
would obtain the canonical prefix through CMake and publish that exact value before invoking the unchanged builders.
Do not weaken the product guard or change the frozen SDK/builders to accommodate this workflow.

All original native UI regression steps after host build, the six sender checks, seven receiver checks,
and one-positive/eight-negative independent transfer controls were NOT EXECUTED. No sender/receiver proof artifact
was uploaded; safety-upload conditions stayed false because the new drivers never ran. The auth always-upload
step had no proof files, so it created no artifact. No success or rejection-control count is credited.

Retained original build-evidence artifact (metadata checked through GitHub API, not downloaded or parsed here):
- ID 13028452194, name windows-host-sdk342-41164667579-1
- size 14929 bytes
- SHA256 5c371554d7810a4cc15637f714992903f74c72e5de057deea259d3756e833b36
- source e50c97f7acfa09afb8a9eae8a4f138586248fb1c, same run/attempt; not expired at observation.
This is build evidence only, not a transfer receipt or original-book proof.

Round budget: 1/1 consumed. No automatic rerun or correction is authorized by the original single-run grant.
Result-document sealing is doc-only with [skip ci], not a second verification.
F02 remains unverified; fixed formal total remains 95/108 (87.96%).
This snapshot preserves the failed run and next prerequisite; it does not mean the overall EXReader task stopped or completed.

## Separately authorized canonical-prefix correction

After preserving the first failure, the user explicitly approved one additional run solely for the workflow's
Windows path normalization (Sentinel_ccf1f53a53dc81919073ef94dbc5083e). The workflow now asks CMake itself to
compute file(REAL_PATH) for the installed build/f02-hash directory and exports that exact value through GITHUB_ENV
before the unchanged builders. No product guard, SDK, old builder, test assertion or timeout changes.
This correction has one additional 240/150/20-minute run; no further automatic correction is authorized.

## Authorized correction run: terminal failure (sealed 2026-10-31 04:25Z)

Source 915132b5060e01524fda1a9e6004e335ce617f96; run
[41165250954](https://github.com/NoGod3524/EXReader/actions/runs/41165250954), attempt 1.
Windows job 124431307896 ended failure at 03:57:26Z. GTK job 124435216932 was skipped.
Authentication job 124435216282 ended failure at 03:57:36Z because the upstream jobs were not both successful.

The canonical-prefix blocker was cleared. The Windows host build and original compact, wave3, TXT,
account/sync, forward-scan comparison and installed-SDK scan steps succeeded. The retained original
"Build native organization consumers" step failed. This failure was not suppressed or counted as a pass.

Root's ordinary job-log inspection located the organization consumer configure error at
tests/windows_organization_projection/cloud/CMakeLists.txt:8: find_package requested EXReader EXACT
version "3", while the installed candidate was 3.42.0. The logged invocation used the unquoted
-DEXR_SDK_VERSION=3.42.0; a later reference build used the quoted equivalent and succeeded.
PowerShell argument handling is therefore a candidate cause, not yet proven by source/cache inspection.
No old test, product source, SDK guard or assertion was changed to hide this failure.

The new "Native Windows import and actual HTTPS PUT" step was skipped. Consequently the six new sender
checks, seven receiver checks, and one-positive/eight-negative cross-host authentication controls remain
NOT EXECUTED. No cross-host transfer success is claimed. GTK was not built/run in this attempt.
The old regression successes do not satisfy F02 or substitute for an unexecuted receiver.

Independent API recheck at 04:24:59Z confirmed the three job outcomes, source SHA and retained artifact metadata:
- artifact 13029208976, windows-host-sdk342-41165250954-1
- 10696355 bytes
- SHA256 f6738da14ad96796d9e1b243487f7ee81d2e1a76f6be19cdd177ada5cc19c578
- same run/source/attempt; not expired at inspection.
The archive was not downloaded or parsed on the cloud computer. It contains the original build/regression
evidence, not a completed transfer proof. First-run failure 41164667579 and its artifact remain preserved above.

Both separately authorized runs are consumed: original 1/1 and canonical-correction 1/1.
There is no third-run authorization. The next permitted action is read-only diagnosis of the exact
organization CMake argument/cache discrepancy; a code/workflow correction or another run needs its own grant.
This document-only seal uses [skip ci]. Formal acceptance stays 95/108 (87.96%), F02 not promoted.
