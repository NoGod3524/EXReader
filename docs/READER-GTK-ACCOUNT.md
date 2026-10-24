# GTK account controls and local original staging

The optional GTK host exposes **More → Account / Sync…** and **Ctrl+Shift+A**.
It uses the installed credentials, native account-session, desktop-metadata and
public sideload modules. `EXR_READER_GTK_ACCOUNT` defaults to `OFF`; enabling it
requires installed `READER_METADATA_PREFIX` and `READER_ACCOUNT_PREFIX` plus the
installed reading-library SDK. The frozen SDK, shared module APIs and product
schema are unchanged.

## Credentials and binding

The dialog accepts an HTTPS WebDAV collection root ending in `/`, username and
masked password. The user explicitly chooses system secure storage or the
current app session. The credentials module stores one opaque username/password
record under namespace `org.exreader.reader.webdav` and the library's canonical
UUID. `account.ini` contains only `[account]` keys `id` and `root`; the root is
the exact validated URL. The native session independently binds the same product
database to that UUID and exact root. A different binding is refused before HTTP.

`UNAVAILABLE` reports that credentials were not saved. Scanning stops until the
user explicitly chooses session-only credentials or restores secure storage.
Forget clears app-session memory and requests deletion of the system record;
unconfirmed system deletion is shown as a failure. The nonsecret binding remains.
Session-only changes do not delete an older saved record; use Forget to remove it.
Username, password and Authorization do not enter the product catalog, account
configuration, scan observations, wire payloads or logs. Temporary auth buffers
and owner copies are wiped after use. GTK keeps its password entry masked.

## Owners, preparation and network lifecycle

The existing SDK owner prepares all locally attached books, independently of
selection. It reads at most 50 product rows per page and processes one book per
queued owner operation, yielding between replies. Durable pending metadata
blocks preparation until the user resolves the earlier edit. Bootstrap uses a
local metadata snapshot and public original-identity proof; it never replaces the
book editor's retained snapshot or token and preserves existing edited fields.
An already retained book history with multiple heads does not require bootstrap:
after independent SDK original-identity proof, preparation stages only its bytes
and continues. It does not select a head, project a revision or modify product
metadata. A real durable pending edit still refuses the entire preparation.

Before network start, the owner releases every SDK source and stages private
immutable `<sha256>.<format>` files. Both identity and public export enforce a
128 MiB ceiling; export/verification copies use at most 64 KiB chunks. Export
publishes without replacing an existing file. Existing originals are checked for
private regular-file ownership, exact length and SHA-256; mismatches stop the
scan and remain untouched. The native sync module rechecks originals before
publication. Missing or oversized sources remain pending.

The GTK thread controls and observes the existing asynchronous native session;
it owns no network thread and performs no synchronous DAV I/O. Preparation and
network scanning expose progress, Cancel and errors. Retry is explicit and
resumes the failed/cancelled handle's cursor; a new connection stages the local
library again and starts a fresh native scan. Counters describe operations or
observations, and current transfer bytes describe the current callback.

Back, Disconnect and app close request cancellation/closure, keep polling until
`CLOSED`, then destroy the session. SDK-owner shutdown follows this barrier.
The transient dialog disables the main content while allowing the main window's
close event. Shutdown retires shelf timers and scroll/layout callbacks before
destroying widgets; observations ignore a window being destroyed.
Controls remain responsive while native calls reach their cancellation boundary.
The transport's default network timeout is 30 seconds.

`FINISHED` means that one record scan ended. Received records remain history;
this package does not project remote metadata, import remote originals into the
SDK, or claim that received books are readable. That application orchestration
is a separate integration step.

## Cloud verification

`.github/workflows/reader-account-linux.yml` builds the installed optional modules
and actual GTK host on Ubuntu 22.04. It retains the previous GTK twenty checks,
product five, fixed-page twenty-four, shelf fourteen, metadata fifteen,
collections twenty-seven and original fault regressions in the same run.

`tests/linux_host/check_account_ui.py` exercises real windows, 52 chooser-imported
SDK originals across the 50-row boundary, temporary unlocked/locked Secret
Service, native HTTPS DAV, save/restart/load/delete, explicit unavailable
session-only mode, preparation/network cancellation and close barriers, failure
and explicit retry, root/UUID isolation, immutable-file refusal, retained pending
metadata and credential-leak checks. All execution, fixture creation and artifact
collection belong in Actions. Source edits and Git operations are the only local
work.

The 23 account checks include an actual pair of locally retained book branches:
all heads and metadata must stay unchanged, the staged original must match its
global key, both outbox entries must publish, and a new remote record must still
arrive while the book remains unresolved.

## Retained failures and diagnostics

| Run | Source | Result |
| --- | --- | --- |
| 40063941677 | 5cad2112 | Existing installed-consumer verifier required a fixed build-log path. |
| 40064010888 | 20cc0314 | Same missing legacy verifier log path. No account acceptance. |
| 40064197851 | 3e690526 | Modal dialog prevented main-window close during preparation. |
| 40065023405 attempt 1 | 9e24b28f | Font mutant stopped before its restart assertion: two page-forward inputs reached only page 1. |
| 40065023405 attempt 2 | 9e24b28f | Preparation cancelled before network, but stale shelf callbacks accessed widgets during app destruction. |
| 40066728040 | 4d9fc618 | Cancel keyboard input was checked before its acknowledgement; actual window focus and a bounded acknowledgement wait were added. |
| 40067554989 | e74d3193 | Retry could observe the preceding FAILED terminal state; the test now requires a newer native attempt before accepting its result. |
| 40068286398 | c374e2de | Network Back used an unfenced transient closing assertion; the test now targets the dialog and verifies closing or completed CLOSED, then matched generation. |

The font precondition now explicitly waits for page 1 before forwarding to page
2. Its twenty checks and the negative restore assertion remain. The two original
attempts of run 40065023405 and their artifacts remain separate. Cloud inspection
runs 40066307947 and 40066418937 verified the original ZIP digests and read the
retained observations; both are diagnostic only with `accepted=false`.
The first inspection run 40066177416 failed its archive-root path lookup and
remains retained as a failed diagnostic.

## Accepted cloud source

Tested source: `d88ed89d65ddbdad4eed0ba71e52dbba3c0611fe`.
[Run 40068924227](https://github.com/NoGod3524/EXReader/actions/runs/40068924227),
attempt 1, job `120797949398`: the single job and every step succeeded. Completed
job logs confirm the following results on that same source and attempt:

| Checks | Passed |
| --- | ---: |
| Native account / Secret Service / HTTPS / lifecycle / conflicts | 23/23 |
| Original GTK | 20/20 |
| Product UI | 5/5 |
| Original fault regressions, including font mutant rejection | 4/4 |
| Fixed-page UI | 24/24 |
| Bounded shelf UI | 14/14 |
| Metadata UI | 15/15 |
| Collections UI | 27/27 |
| Desktop installed-consumer ctest | 4/4 |
| Product provider ctest | 1/1 |

The account fixture imported 52 actual TXT originals through the native chooser.
It crossed the 50-row owner-page boundary and verified exact staged/uploaded
bytes, preserved edited product fields, real secure-storage persistence and
deletion, explicit session-only behavior with locked secure storage, both close
paths, a retained two-head book and continued remote reception. Credential scans
over generated profile/product/wire/evidence files found zero raw, hex or base64
hits.

The single required artifact `reader-gtk-account-40068924227-1`, ID
`12550344355`, contains 39,689,678 bytes; it is nonempty, unexpired and bound to
that exact run/source. Digest:
`sha256:d98210dcc8cb2023cea49ec40f307f47b62ec602e41192295cd291458f952cab`.
Packaged program SHA-256:
`60dce4c781eb0b95176f9798a53688c6bc49e344f17f80c78ac13262a65daeb1`.
SDK identity remains 3.40.0 / ABI 1. Machine-readable identities and every retained
failure artifact are recorded in
[reader-gtk-account.json](validation/reader-gtk-account.json).

Acceptance covers the Linux GTK reference account and staging flow. Remote
metadata projection, remote SDK import, performance budgets and the complete
product remain separate work.
