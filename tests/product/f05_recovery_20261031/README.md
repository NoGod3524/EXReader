# F05 current test design — 2026-11-01 01:00 UTC

Preparation only; **not 100% accepted**. One active implementation branch,
`dot/f05-client-recovery-20261031`, one independent validator. Nine approved files
exist; no workflow or CI run yet. Old sealed evidence is retained, never reclassified
as this candidate's result. All execution, syntax, fixtures and archive parsing is Actions-only.

## Contract → proof → counterexample
Original requirement: complete native client offline reconnect, concurrent
heads/tombstones, cancellation and crash recovery. Protocol
[129–130](https://github.com/NoGod3524/EXReader/blob/94fb236a4a2da87dfbaf4f1dd2a47885d615a230/docs/WEBDAV-PROTOCOL.md#L129-L130)
and [160](https://github.com/NoGod3524/EXReader/blob/94fb236a4a2da87dfbaf4f1dd2a47885d615a230/docs/WEBDAV-PROTOCOL.md#L160)
govern retained conflicts and native presentation. No universal single-head resolution
or identical cancel phase is invented.

| Proof target | Real positive path | Rejected counterexample / exact reason | Evidence |
|---|---|---|---|
| Offline reconnect | Native UI changes persist in outbox while DAV unavailable, then same native client syncs | Missing local revision, changed bytes, or uncleared acknowledged outbox → fail | UI action, before/after heads/outbox, raw authenticated PUT |
| Concurrent heads | Two native authors share parent and create causally independent revisions; receiver retains both | One head selected/discarded, artificial parent rewrite, receiver DB injection → fail | Raw original bytes/IDs/parents; native conflict display |
| Delete/put | GTK native Delete competes with native Rename; Android can author local offline change before same-run GTK deletion is exposed | Delete head missing or implicit restore; generic-only UI unable to identify deletion → partial/fail full acceptance | Typed operation/heads, native reachable detail, projection state |
| Cancel/retry | Windows/GTK cancel transport original GET; Android/Apple cancel explicit cache-miss Receive | Cancel before gate, wrong layer claimed, changed SDK original set, duplicate retry import → fail | Actual held request, native Cancel, original counts/hashes before/cancel/retry |
| Crash/unknown ack | Hold actual committed PUT reply, externally kill actual app, restart and retry | Wrong PID, no actual kill, lost original queued revision, changed committed bytes, lingering outbox → fail | PID/executable identity, committed request event, immutable inventory and restored process |
| Offline reopened original | Actual new process opens retained book without network | Network dependency, wrong original bytes, blank/nonmatching native page, changed heads → fail | Native reader frame/text/screenshot plus exact SDK original readback |
| Conditional restore | Only if actual user restore exists, every competing parent must be included | Missing parent or ordinary put treated as restore → fail | Actual native action and original wire revision |
| Independent provenance | All new producers and consumers use one final source/SDK/run/attempt | Foreign source/run/SDK, substituted artifact, changed archive bytes, missing old assertions → reject | Actions API metadata/digest, exact artifact bytes, unchanged old suite reports |

## Reviewed role gate and archive controls
`manifest.json` schema 2 separates native cases from coverage claims. Receivers
cannot disappear as N/A; author roles may come from another native host in this
same source/run/attempt. Applicable cancellation layer is recorded as transport,
receive or import; process recovery records its actual boundary rather than
inventing one mandatory kill point. Offline reopen and wholly local cancellation/recovery require no peer wire; an explicitly remote boundary still requires observed native wire.
Resolution/restore checks apply only when the actual user operation occurred.

`verify.py` uses the runner's normal `gh api` read-only authentication without
opening credential files. It retains each GitHub original ZIP and API metadata:
exact source/run/attempt; exact successful producer job from the attempt-jobs API;
artifact creation inside that job's start/end interval; unexpired exact artifact
name and ID; API SHA256 digest and byte size; actual packaged program hash.
It never re-zips evidence or extracts archive members to arbitrary filesystem paths.
Duplicate/path-traversal/symlink/encrypted members and archive limits fail closed.

The real positive role gate must pass before negative controls run. Each controlled
mutation has its own required refusal code: `wrong_source`, `missing_claim`,
`partial_case`, `wrong_suite_names`, `wrong_digest`, `duplicate_member`,
`unsafe_member`. A different pre-existing failure does not qualify as successful
rejection. Deliberately malformed tiny ZIPs are labeled negative controls only,
not source archives or native-client results. Any negative failure closes the gate.
Even a passed gate reports `F05_accepted=false`: final independent product
acceptance and complete applicable native coverage remain separate.

The original Android 16-check runner has a confirmed compatibility block:
its Java `HostSyncTest.java` still accepts only SDK3.40/3.41. The approved
Python CLI-choice adapter is not sufficient. The original Java remains untouched;
a separately approved, byte-guarded generated instrumentation copy is pending.
The retained entry deliberately fails preflight rather than wasting a CI attempt.
Do not describe this route as runnable yet.

Windows/GTK/Android now emit role receipts tied to raw case pointers and actual
native evidence. Android compares installed APK bytes to the retained program.
Apple binds actual native product identity, per-phase xcresult attachments and
exact killed/reopened executable paths/hashes. These are unexecuted preparations.

GTK's native old-parent put follows the actual native deletion in the authenticated
commit sequence, with typed operations and common parents verified. Its unmodified
checkpoint can then be delivered to Android through the native sync route, preserving
Android's own earlier local head as well. This tests the original old-put-not-restore
contract; repeated-ID replay is additional rather than a newly invented hard gate.
Deletion-specific native UI remains partial. F07's bounded source review found no
new blocker in this checkpoint isolation; it is not runtime verification.

No authentication, negative control, syntax check or host test has been executed
for this preparation. The pending shared-suite integration does not authorize
a new parallel permanent workflow or transfer the old run budget.

## Peer replay is not simultaneous online concurrency
Windows/GTK authors produce actual native PUT bytes. Same-run checkpoints retain
source/run/attempt/author, exact bytes/hash and commit sequence. Mobile receivers
first receive the common ancestor, perform applicable offline actions, then receive
unchanged remote branches. No ID/parent/time rewrite, no receiver DB writes, no
claims of simultaneous network races. Inherited wire records retain their original
author provenance, not falsely relabeled as new consumer PUTs.

## Cancellation fault is explicit
The native sync owner must be idle or actual application exited. Verify a single
cache file's exact hash/size, atomically rename that inode to a private test quarantine,
and retain its identity/bytes. SDK originals remain untouched. Do not restore that
cache before ordinary native retry. Fixture-only credentials enter through actual UI;
logs redact them. Transport cancellation is not mislabeled mid-SDK-import cancellation.

## Present coverage limits and hard readiness gate
- GTK/Android deletion preservation is implemented but native per-head deletion detail
  remains with the existing UI owner; affected result is **partial**, not accepted.
- F03's new Apple organization projection delta is not yet composed into this branch.
- Role-aware gate and original-archive authenticator are implemented as **unexecuted
  preparation**. Producer artifact names/job names/member paths and normalized runtime
  receipts are not wired; manifest stays `implementation-in-progress` and fails closed.
- Pinned retained suites: Windows native account 32; GTK account 23 plus explicit
  receive 25 (48 in the original interleaved order); Android original session UI
  6/5/1/4 (16), four PIDs and two blocked-request boundaries; each Apple host
  account 3 XCTest cases/14 named steps/6 attachments/256 shards plus original
  401→pending 1→retry 256→outbox 0. macOS additionally retains account-terminal.
  These original seeded cases are regression, not new native peer coverage.
- Original suite blobs and five SDK paths are checked before artifact processing.
  Runtime adapter connections and their exact report shapes remain required.
  No original assertion or negative case may be removed to fit the budget.
- Physical power loss, arbitrary third-party DAV implementations and hardware-specific
  devices are not inferred from runner process-kill/simulator coverage.
- F07 shared static linker inventory does not establish runtime provider use or F07 acceptance.

Approved cap: admission 5 + Windows 45 + GTK 20 + Android 60 + macOS 30 +
iPhone 45 + iPad 45 + audit 15 = **265 runner minutes**, one run, no automatic rerun.
Current usage **0**. Historical notes below are preserved; current design supersedes
obsolete blanket-resolution blockers or preparation file counts.

---

# Contract correction — 2026-10-31 23:19 UTC

The coordinator settled the original F05 interpretation: preserve every concurrent
head and present conflict; preserve delete/put and display delete conflict; stale
put must not restore. An existing explicit resolution/restore action must include
all observed competing parents. **No requirement to resolve every concurrent
scenario to one head.** Earlier text below that calls absent single-head resolution
a blanket production blocker is superseded; the safety refusal itself is not a bug.

Sources on preparation base: [protocol lines129–130](https://github.com/NoGod3524/EXReader/blob/94fb236a4a2da87dfbaf4f1dd2a47885d615a230/docs/WEBDAV-PROTOCOL.md#L129-L130)
and [native client line160](https://github.com/NoGod3524/EXReader/blob/94fb236a4a2da87dfbaf4f1dd2a47885d615a230/docs/WEBDAV-PROTOCOL.md#L160).
Actual host conflict presentation remains required, not just lower-layer refusal.

Preparation has progressed to a real HTTPS fault fixture and Win32 dual-host
driver: offline native edit/reconnect, committed PUT response withheld plus kill
and retry, two native edits producing genuine concurrent heads over HTTPS, and
offline host reopen/read. These are unexecuted, unvalidated source, not green tests.
The Win32 driver still lacks tombstone/delete-put and receive-cancel scenarios;
other platform drivers and the final workflow are not installed. It returns
coverage only, with F05_accepted=false. The contract checker remains distinct
from independent artifact authentication. CI usage remains0.

---

# F05 real-client recovery acceptance — preparation, not acceptance

Preparation base: `94fb236a4a2da87dfbaf4f1dd2a47885d615a230`.
Frozen SDK reference: `8357eafa28423a7ab93ba08b823af80f01ad1505`.
Branch: `dot/f05-client-recovery-20261031`.

## Required outcome
All six real clients must perform the six named scenarios in manifest.json on one
final composed source. Each scenario needs native host action evidence, real HTTPS
request/response identities, original revision bytes, complete head sets, and
reopened SDK original/readability evidence. Direct insertion into a receiving
database and a standalone public-API consumer are not client acceptance.

The catalog names offline reconnect, concurrent heads/tombstones, cancellation and
crash recovery. The product plan additionally requires explicit conflict UI;
WEBDAV-PROTOCOL section 4 requires a resolving revision whose parents cover all
competing heads, and explicit restoration covering tombstones. Preserve conflicts
without resolution is a valid safety result, not the complete requested loop.
The older protocol document's 16 shards must not override the implementation's
256-shard protocol.

## Blocking source evidence on the preparation base
* apps/reader/desktop-metadata/src/metadata.cpp:229 identifies multiple heads,
  missing/foreign parents and requires_restore as conflict; :260 rejects a
  conflicted snapshot before edit staging. prepare_group at :364 returns conflict.
* apps/reader/desktop/windows_metadata_ui.inc:158 disables editing unresolved
  version differences. examples/linux/metadata_ui.inc:84 presents the conflict path.
* examples/apple/HostOrganization.swift prepareGroup requires READER_METADATA_OK.
* examples/android/app/src/main/java/org/exreader/host/OrganizationPanel.java
  refuses a non-editable selection with an unresolved-revisions message.
* The lower reader_command_context.expected_heads API can name all heads.
  Calling it from the test instead of the host would bypass the missing UI and
  is forbidden as evidence of a complete client.

The original Windows 32-check account driver explicitly discloses direct receiver
planting of concurrent/tombstone records and no receive/import cancellation test.
The resilience suite's 21 added + 20 original checks explicitly excludes host UI
projection and other hosts. Preserve these original checks and limitations.

## Owner and budget boundary
Do not change SDK, original tests, shared worktrees, or production files here.
F10 is the proposed sole sync.cpp writer, pending its production authorization.
UI and Apple owner boundaries remain in force. A new owner-approved conflict
resolution route is required before spending a full-six-client validation run.
Do not automatically reuse C02/Linux-joint/Android passed runs as F05 acceptance.

Approved one run, at most 265 runner-minutes: Windows45/Linux20/Android60/
macOS30/iPhone45/iPad45/admission5/audit15. Zero runs used. No auto retry.
No workflow is installed or run while this capability blocker remains.

`verify.py` is a fail-closed receipt-contract checker. It is not a producer,
artifact authenticator, UI test, or completed acceptance. It must run only inside
Actions and downstream of original-artifact identity authentication. No script
has been executed locally, and no syntax/test pass is claimed.
