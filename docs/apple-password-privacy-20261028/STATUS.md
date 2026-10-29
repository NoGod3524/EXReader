# Apple password privacy — bounded F10 source candidate

Base: `8f8acf3234cba747165f001c0c96efe1b911e6ad`; installed SDK **3.42.0**.
Proposed branch: `codex/apple-password-privacy-20261028`.
Owned additions: `tests/apple_password_privacy_20261028/**`, this document,
`.github/workflows/apple-password-privacy-20261028.yml` only.

**Native acceptance remains ungranted.** The first published source
`7dc199ce383877aee1f45a44be8453b7d4268219` ran in Actions
[40773724953](https://github.com/NoGod3524/EXReader/actions/runs/40773724953):
all 18 scanner/archive controls and both SDK builds passed, while all three
native jobs failed during setup and authentication correctly refused.
The original failure artifacts are retained unchanged.

A diagnostic-only publication was denied at 21:52 UTC, then the exact reviewed
two-file payload was retried once after the user's named-package authorization
at 21:59:11 UTC. Source `8845cf2886f50a69d56c577e34f317d449f2f103`, Actions
[40776849750](https://github.com/NoGod3524/EXReader/actions/runs/40776849750),
authenticated the pinned prior macOS ZIP and printed its sanitized project log:
`make_project.rb:31` raised `TypeError: no implicit conversion of Array into String`.
This diagnostic skipped SDK/native/authentication rather than repeating
successful builds solely to retrieve a log; it is not privacy acceptance.

The new adapter repair normalizes xcodeproj's String/Array flag representation,
preserves every existing token, and adds only the required raw metadata flags.
New Actions-only controls cover both forms, quoted paths, malformed/invalid
values, and actual xcodeproj save/reopen. Repaired full run
[40777254345](https://github.com/NoGod3524/EXReader/actions/runs/40777254345),
source `b45971a955446310d2e4fc85a94690aa5a6703dd`, passed these controls and both
SDKs but all three native jobs refused the first post-termination observation.
Safe retained-artifact diagnostics
[40780733484](https://github.com/NoGod3524/EXReader/actions/runs/40780733484) and
[40781522760](https://github.com/NoGod3524/EXReader/actions/runs/40781522760)
authenticated every retained member without rebuilding SDK/native products.
Profile/container files were clean; each process unified log matched only
`user:raw`, `user:json`, `user:url`, `user:url-lower-escape`. For the synthetic
ASCII username those four labels represent identical bytes, not four distinct
leaks. No password, user:password or Authorization variant was detected in that
first-checkpoint scan. This is not owner-callsite attribution or full-F10 proof.

The failed scan manifest retained its digest/size/hits, but the original harness
refused before archiving the raw unified log. The evidence-retention repair now
writes complete captured stdout/stderr with private runner file modes and a
safe hash manifest before the unchanged privacy verdict. Synthetic-sensitive
raw bytes stay in retained Actions artifacts, never console/chat; access follows
repository/Actions artifact access controls, not an independently configured
private store. Original failed runs remain unchanged. New fixed-enum event
attribution reports only sender-image category, credential role and counts;
JSON decoding may normalize encodings, so the original streaming byte scan
remains authoritative. An image category is not a proven production callsite.
All existing privacy predicates and budgets are unchanged. Purposeful native
reproduction now retains complete failed evidence; its result is recorded below.

## Additive diagnostic continuation — never a replacement green

Reproduction [40782857602](https://github.com/NoGod3524/EXReader/actions/runs/40782857602),
source `af51c760bec76454b0db6547cf592ddb7338de0b`, passed all 28 controls and both
SDK builds, but all three strict native jobs still failed at the first scan.
Complete raw synthetic logs are now retained. Safe event analysis found only
username matching roles, all in the `test-framework-image` category: macOS 28,
iPhone 50, iPad 50 events. This supports instrumentation noise, not a proven
production password leak; sender-image categories are not source callsites.
Original strict failure artifacts and verdicts remain unchanged.

An additive, explicitly marked `[privacy-continuation]` probe uses a distinct
test class/case, generated test-file reference, native job/artifact names and
independent diagnostic verifier. It performs the same actual account controls,
termination/restart, authenticated sweeps and missing-credential check. A 204
callback means all observation evidence and its strict verdict were recorded,
**not** that privacy passed. Every strict scan result is retained, independently
rescanned and reported per stage. Recording a failed privacy observation allows
this new diagnostic case to attempt later operations; it does not alter or
rerun the original strict case with filtered logs or relaxed assertions.

The probe always reports `accepted: false`, `diagnostic_only: true` and
`full_f10_accepted: false`, even if every scan were clean. Its only possible
success is `sequence_complete`/`probe_integrity_verified`; privacy failures
remain explicit in `failed_strict_checkpoints` and per-root encoded match
labels. Safe image-category attribution and any password findings remain
narrow observations, not unrestricted absence or production-callsite proof.
The ordinary strict run remains the only route to strict slice acceptance.
Existing hard stops are retained: for example, a direct macOS preferences hit
still refuses before checkpoint completion, as do incomplete capture,
unreadable/linked/special entries, mutations and failed structural/network/UI
checks. Thus this probe can advance after a completely captured whole-root
privacy failure, not every conceivable privacy or evidence failure.

The marker selects separate jobs within the one owned workflow; unmarked runs
retain original strict native/authentication behavior. No old test file,
production owner, SDK, timeout or budget changes. Five Actions-only controls
reject incomplete/nonboolean stage reports and strict-case replay, and prove
that continuation cannot award strict acceptance. The independent verifier
also checks generated project structures differ only in the new test reference,
all original bytes, current-run SDK/program identity, actual case/screenshots,
network roles, originals, snapshots and raw-log manifests. Summary upload is
safe JSON only; original synthetic-sensitive artifacts stay on their producers.
Continuation source review and Actions execution remain pending.
No local build, syntax check, fixture generation, test or artifact parsing
was performed. Source reading/writing and source-file hashing are not execution
evidence. No Codex task, user computer, main push, PR, tag or release is used.

## Real credential route, with an explicit missing feature

The unchanged `HostAccountViews.swift` presents Remember / Update, but no
dedicated Forget control. The unchanged `HostAccounts.updateCredentials` deletes
the profile's stored credential when Remember is off, while keeping the supplied
authorization transiently in that process. This package exercises that actual
UI route; it does not add a Forget button, call the owner directly, replace the
credential backend, or label uncheck-and-update as a dedicated Forget action.

| Stage | Actual native operation | Required independent observation |
|---|---|---|
| `remember_closed` | Connect with Remember on; import one fixture EPUB; terminate | Account/original intact, no unexpected sync, clean captured private files/logs |
| `remember_reopened` | Launch a new process and manually sync | Full 256-shard sweep authenticated with the remembered synthetic credential |
| `session_closed` | New process; Update with a different synthetic credential and Remember off; sync; terminate | Full sweep uses only the new session credential; original unchanged |
| `session_reopened_missing` | New process; manually sync again | Native missing-credential failure and no new server request |

The new test runs separately on macOS, iPhone Simulator and iPad Simulator.
Actual loopback TLS uses a one-run certificate trusted only on the disposable
Actions runner/simulator; no public account/server is contacted. Credentials are
cryptographically random synthetic canaries generated only in Actions. The
fixture records credential *roles*, not Authorization bytes. Synthetic oracle
inputs are deliberately retained, labeled as test inputs, separately from
product snapshots so authentication can reconstruct every search variant.

Opening Update also observes the displayed username and SecureField values.
**An empty or masked SecureField is not evidence that a secret is absent.**
Restart behavior, authenticated network identity, and the retained byte scans
are separate evidence. Compact sync controls put state in their label and
failure detail in accessibility value; the test handles both layouts without
changing the product UI.

## Streaming privacy scope

At each checkpoint the app is terminated before inspection. Every regular file
under the actual product roots is streamed, including hidden files, SQLite/WAL,
cache, downloads and files larger than 64 MiB. macOS roots are the EXReader
Application Support profile and this package's preferences, cache and saved
state; absent optional roots are reported. Simulator scope is the **entire app
data container**. Captured EXReaderHost unified logs include info/debug events.
No extension whitelist, file-count cap, unreadable-file exemption, symlink
following or large-file skip can produce acceptance. Special/linked entries
and unreadable files refuse. Empty primary roots refuse.

Search variants include raw username/password, user:password, Basic header,
hex in both cases, padded/unpadded standard and URL-safe base64, ordinary and
fully percent-escaped URL forms, UTF-16/UTF-32 endian forms, and JSON escaping.
Overlap is the longest needle minus one, so a match spanning a chunk boundary
is not lost. These are enumerated variants, **not a claim about every possible
encoding, encryption, fragmentation or transformed secret**.

File identity, size, mtime and ctime are checked before/after streaming; a final
directory/file inventory detects mutations of earlier files and already-scanned
directory prefixes while later files or roots are read. Actual archive members
are then streamed and compared with scan digests; all roots are rescanned before
the checkpoint is published. Copied macOS preferences are checked against the
actual source again. This requires quiescent product output, not an adversarial
filesystem that can perfectly forge/change metadata between observations.
The complete optional macOS-root namespace is inventoried with `lstat` before
classification and rechecked at publication: a previously absent preference,
cache or saved-state root appearing late refuses, as does a dangling symlink.

Actions-only rejection fixtures cover every configured encoded variant across
chunk boundaries, clean and leaking files over 64 MiB, symlinks, unreadable and
empty roots, in-place overwrite of an already-read prefix, earlier-file and
earlier-root mutation, additions in an earlier directory, late creation of an
absent optional root, dangling optional roots, and canaries in file or empty
directory names. Reports contain variant labels, not matching secret bytes. These
scanner tests never count as product privacy acceptance.

## Retained identity and independent authentication

The scope guard requires the exact base as ancestor, exact checked-out source,
and **additions only** in the owned paths. Frozen SDK, production owners, old
tests/assertions and existing budgets remain unchanged. The existing SDK342
builder supplies raw selector/wave3/page-theme products. A new adapter changes
only generated SDK-version guards, generated bundle/configuration, and selects
the new test target. All production Swift source bytes are recorded unchanged.
The existing review fixture import control supplies the EPUB; this does not
award production-import UI coverage or replace the credential controls.

Actions retains the original xcresult, stage screenshots, typed-input oracle,
request-role log, all private snapshots, source EPUB, actual program ZIP,
packaged SDK runtime, link map, SDK identity and original/derived generators.
The aggregate job authenticates same-source/run/attempt producer jobs and API
artifact ID/digest/size/expiry, checks every member's digest, rereads the original
native case and attachments, rescans every snapshot byte independently, verifies
the actual account and original EPUB BLOB, and repeats actual program/provider
inspection. Older greens or synthetic scanner fixtures cannot satisfy it.
Before extraction, the entire ZIP namespace rejects normalized NFC/case-folded
parent aliases, duplicate names and file/directory collisions, along with links,
special entries and traversal. Archive resource limits are 8 GiB per member and
32 GiB total uncompressed bytes: exceeding a limit fails the whole evidence
gate, never truncates or skips a file. These extraction safeguards are distinct
from the streaming scanner, which has no per-file size exclusion. Actions-only
controls cover case/Unicode aliases, parent aliases, file/directory collisions,
ordinary implicit/explicit directories and both resource-limit refusals.

The workflow has one proposed feature-branch push trigger, no dispatch and no
built-in retry. New job limits: contract 10, SDK 90, native 90, authentication 30
minutes; the new native case uses default/max 240/360 seconds. Existing suite
limits are untouched. All builds/tests/fixtures/artifact work is Actions-only.

## Remaining gaps and stopping boundary

* **Dedicated Forget UI is absent and untested; full F10 stays false.** A future
  owner/UI change needs separate scope/authorization.
* Physical-device Keychain/access-group behavior is not established by a macOS
  host and simulators. Keychain bytes are not dumped/scanned: remembered storage
  there is expected, and deletion is inferred from the real restart/network
  behavior, not direct database inspection or forensic erasure.
* Logs means the retained readable unified-log export and logs inside the named
  product roots. Private/redacted OS logging payloads, arbitrary system logs,
  process memory, crash/core dumps outside those roots, and separately isolated
  product stdout/stderr are not proven secret-free. XCTest activity logs and the
  synthetic input file intentionally contain test inputs and are not mislabeled
  as product-output absence evidence.
* Simulator TLS trust, macOS Keychain prompts, native field values, real sweep
  completion and emitted log coverage remain runtime questions. A failure must
  stay failed/blocked; do not loosen assertions, skip bytes or change an owner.
* Scanner/archive controls and the diagnostic-only pinned setup-artifact check
  passed in Actions. No real credential UI case or full original-native-artifact
  authentication has passed; there is no product acceptance to grant.

## 2026-10-29: retained failure diagnosis and finite UI-state reproduction

The additive continuation at `0533fadf8d5cc41959a7ae81ef1dbd294c7d096e`,
run `40794326091`, failed all three native sequences after the first checkpoint.
Its 33 controls, both current-source SDK builds and flags regressions passed.
Original strict failures and complete synthetic evidence remain preserved.

Four bounded Actions-only diagnostic runs inspected the same pinned original
uploads without rebuilding SDK/native jobs: `40801553322` (37 controls),
`40802297629` (39), `40803228570` (41), `40804595108` (43), all successful.
The first checkpoint completed on all three and callbacks did not fail. macOS
then performed 272 remembered-role authenticated requests after actual restart,
including all 256 revision shards. iPhone/iPad recorded no later requests; that
alone does not prove credential failure. All three native xcresults contain
execution-time-allowance-exceeded signatures. Subsequent sync-state polling
lasted macOS 73.41–253.42s, iPhone 155.28–309.62s, iPad 134.49–289.39s.

Each exported result has one first-stage PNG, one text attachment and 15 opaque
extension attachments. The text contains no literal UTF8 status tokens, but
UTF16/escaped/opaque data and image interpretation were not covered; missing
actual displayed-state evidence is not a claim that no error was displayed.
No production/password defect or scanner bottleneck has been inferred.

The next purposeful continuation reproduction adds finite codes for the actual
already-queried accessibility snapshot label/value, value type, credential-missing
indicator, phase and monotonic elapsed time. Unknown text becomes `other`; no raw
label/value, username, password, framework error or root URL is printed. Changes
and five-second heartbeats are emitted, without extra snapshot requests. The
original label-return predicate, controls, case sequence, 180-second sync wait,
90-second checkpoint wait, native/global job budgets and full all-file privacy
scans remain unchanged. An Actions-only source contract removes only the
observation wrapper and checks byte equality with the original continuation UI.
The independent authenticator recomputes these finite records from the retained
native log. Four new controls precede any current-source SDK/native work.

This instrumentation is diagnostic only. It cannot convert username log noise
into strict acceptance, prove secret absence from a masked field, validate a
production owner callsite, or grant full F10. No dedicated Forget UI exists.

## Actual UI-state reproduction and bounded next repair (2026-10-29)

Run [40810434512](https://github.com/NoGod3524/EXReader/actions/runs/40810434512),
attempt1, source `a703af3e7b7394d337b522fbbf2fc0aafe1de0e5`: all47 controls and
both SDK builds passed. All three native continuations and independent aggregate
failed; strict remember_closed remained false, sequence/full-F10 remained false.
Original username/test-framework-image observations remained28/50/50 groups.

The same-snapshot finite observation now establishes a macOS harness mismatch:
label was empty, value running57.637s then finished59.139s and through237.164s;
the original label-only predicate missed the completed state. iPhone instead
reported label failed121.596–300.770s; iPad failed143.179–287.595s, both with absent
value. Their separate expanded-view detail text was not part of that snapshot.
False missing-credential flags therefore do not classify the simulator failures.

Retained native uploads, all tied to this exact source/run/attempt:

| Platform | Artifact ID | ZIP bytes | SHA256 |
|---|---:|---:|---|
| macOS |12870153932|114145694|9e6a8f7150662bb1da325b32bf49dbbeaf7157b60a94555e5cfee72a67ff9eac|
| iPhone |12870921660|94991384|64a8b9a791ba19c8f0804b9469bdbe43c98bd9120bfc922177aa4ebabea5db88|
| iPad |12871070896|93351932|353b8cc257a5b40755d06f831a2d911cd952df990d80d39ae544035d5013efc5|

Proposed source-only four-file repair changes the continuation accessor on macOS
only: a nonempty label remains authoritative even against a contradictory value;
an empty label permits only an exact whitelisted state string in value. iOS keeps
label-only interpretation. Eight native control assertions cover exact states,
contradictory label/value, message/unknown/nonstring refusals and unchanged iOS.
The original strict UI source stays untouched. The byte-equivalence control
allows exactly this accessor and two diagnostic calls; every original assertion,
expected state, UI action/key, restart, wait and global budget remains identical.

Finite additional observations query six fixed save-status strings only while
the existing initial Update sheet is open, and query the fixed re-enter-credentials
phrase once per failed sync phase. Output contains only status enums, booleans,
phase and bounded elapsed time. These are accessibility existence observations,
not raw strings, visible-pixel proof, secret absence, native OSStatus or acceptance.
Missing observations remain distinct from an observed false/absent result. Two
new Actions controls cover finite metadata, encoded/truncated operands, duplicate,
misordered and unbound detail records (proposed total49 controls).

Simulator signing/entitlement mismatch is only a source-derived hypothesis:
the base host generator disables iOS signing, whereas the standalone credentials
probe declares keychain entitlements. No signing, product owner or SDK change is
made in this repair; no claim that missing entitlement is the observed cause.
This source proposal does not authorize publication or a further native run.
