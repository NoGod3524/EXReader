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
