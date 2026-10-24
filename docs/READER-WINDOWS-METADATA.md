# Windows native metadata editor

Accepted Windows source: `1be8367f056026fe92a4a8f527b62b83155fad47`.
Base: `210403d121d6484a8fff4ea7ffd911efa3163535`.
Cloud run: [40050226847](https://github.com/NoGod3524/EXReader/actions/runs/40050226847),
attempt 1, job `120741039207`, completed successfully on Windows 2022.

| Checks on this source | Result |
| --- | --- |
| Existing package self-test threshold | At least the original 26, enforced by the packager |
| Existing forged-evidence refusals | 54 passed |
| Existing native UI | 158/158, eight screenshots |
| Existing product / worker / bounded shelf | 10 / 5 / 13 passed |
| Existing public SDK / native catalog / process interruption | 9 / 12 / two process kills passed |
| Installed-provider / desktop ctest | 1/1 and 3/3 passed |
| New actual metadata UI | 18/18 passed, six BMP captures |

The same-source unexpired artifact is
`reader-desktop-sdk-Windows-40050226847-1`, ID `12543013408`, 39,071,309 bytes,
API digest `sha256:edcb1bc323d8f09d717c954e27422e698911c3f67e1d58733dbde7995cf50196`.
The packaged product SHA-256 recorded by the existing bounded-shelf report is
`ddf2bc053f19fd76d062f579d67adbfc2e16c8a93fa7167bf85cb9a22b500d96`.
The artifact contains the new `desktop-windows-metadata/metadata-ui.json`, six
captures, host log, source fixture, product database, and independent native
writer log. The compact source/run/job/artifact and completed-log record is
[reader-windows-metadata.json](validation/reader-windows-metadata.json).

## Implementation

The new Details button uses ID 128. Existing IDs 100 through 127 and the original
158-action scripts are unchanged. The modeless standard Win32 dialog uses the
existing main message loop and native Edit, Button and CheckBox controls. It
edits the product title, author and favorite, retaining exact title/author
UTF-8 and deriving only the NFC sort title.

Each PREPARE/SAVE/RETRY/DISCARD job opens and closes an installed
`EXReaderDesktopMetadata::reader_desktop_metadata` 0.1.0 owner on that same
worker. Its catalog and revisions handles never cross threads. A snapshot is
an independent owned data object: preparation copies its strings, heads and
graph; it contains no borrowed store pointer or SQLite/SDK handle. The old
worker finishes and is joined before the UI takes exclusive ownership. The UI
uses separately copied view fields; Save moves the snapshot into the next job.
No two threads use or free it concurrently.

Before exposing a legacy book's editable fields, the worker verifies actual
format and exact retained source SHA-256/size with public SDK calls. It
bootstraps the unchanged current product fields, finishes that intent, then
prepares a fresh snapshot. A user Save therefore produces one complete typed
intent and one metadata/history/outbox transaction.

All metadata jobs have a commit barrier. Cancel, another reading operation,
dialog WM_CLOSE and main-window WM_CLOSE cannot cancel an accepted metadata
transaction. The main window waits for that job before normal shutdown; dialog
destruction clears every widget pointer. Staging failures probe the actual
pending file, including publication followed by a filesystem error. Retry uses
the persisted IDs, payload and original expected heads. Explicit Discard only
removes an uncommitted intent. A newer independent native commit makes an old
editor Save fail without overwriting it.

The new checks exercise actual controls, Unicode/favorite persistence, cancel,
transaction refusal, process termination and restart, exact retry, native
concurrent writes and stale-head refusal. They also hold a real external writer
lock while sending Cancel/dialog WM_CLOSE and main-window WM_CLOSE, and verify
that the accepted edit commits once. Original public-SDK reading and native
clipboard copy still work afterwards.

## Files and integration

- `apps/reader/desktop/windows_metadata.inc`: existing worker and public SDK proof.
- `apps/reader/desktop/windows_metadata_ui.inc`: native dialog and exclusive snapshot transfer.
- `examples/reader.c`: appended IDs, narrow worker/barrier and message-loop hooks.
- `apps/reader/desktop/CMakeLists.txt`: metadata target flags/link for the two Windows consumers.
- `tests/windows_host/check_metadata_ui.py`: 18 real native UI checks.

The desktop workflow selects only Windows for `codex/reader-windows-metadata`;
the integration branch still selects Linux and Windows. Both consumers use the
existing installed product provider. Frozen SDK trees, product SQL schema and
revision wire are unchanged. All execution ran in Actions; local work was
source/document and Git operations.

This delivery accepts the Windows editor scope. Group UI, network sync and
product-wide completion are separate. Root will merge it with the corrected
GTK delivery and run the full five-job same-source integration gate, including
Windows 18, GTK 15 and both 29-check adapter consumers.
