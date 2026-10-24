# READER-DESKTOP-DROP: desktop file drop and paste adapter

Package J03. Independent, SDK-free C module that turns a native desktop drop or
paste into a bounded, immutable request that outlives the platform data object,
the widget and the drop target. The host then decides what to import: only
`EXR_DROP_ITEM_FILE` entries are fit for `exr_sideload_import_file()` (UTF-8
path, immutable until that call returns).

- Sources: `extras/desktop-drop/`
- Acceptance: `tests/reader_desktop_drop/`
- Workflow: `.github/workflows/reader-desktop-drop.yml`
- Evidence: `docs/validation/reader-desktop-drop.json`
- Fixed start: `f43baf9182d75907c0cb5d6f77048f27bca8c950`; frozen SDK
  `9854061be331fe603a1822d9b2b36ee357154927` (3.40.0, ABI 1) unchanged.
- Whitelist: `extras/desktop-drop/**`, `tests/reader_desktop_drop/**`,
  `.github/workflows/reader-desktop-drop.yml`, this file, and the validation
  JSON. Nothing else changes; the default build does not include the module.

## What it does not do

No file is opened, read, copied, watched or recursed into. The only filesystem
access is one `stat`/`GetFileAttributes` per local path to classify it. There is
no WebView, no resident server, no plugin framework and no second parser: the
module is a fixed set of pure entry points plus one native drop-target object
per window/view, and it depends on no part of the EXReader SDK.

## Shared contract

`exr_desktop_drop.h` is the whole portable surface:

| Function | Purpose |
| --- | --- |
| `exr_drop_request_from_uri_list` | `text/uri-list` bytes (RFC 2483 framing) |
| `exr_drop_request_from_gnome_files` | `x-special/gnome-copied-files` bytes |
| `exr_drop_request_from_utf16` | `CF_HDROP` NUL list or `CF_UNICODETEXT` lines |
| `exr_drop_request_from_utf8_list` | arrays of native UTF-8 paths or URIs |
| `exr_drop_request_get_info`/`_get_item` | read-only accessors |
| `exr_drop_request_release` | free one request (NULL accepted) |
| `exr_drop_status_name`/`_item_status_name` | stable diagnostic names |
| `exr_drop_target_destroy` | platform-neutral destroy of a target |

Item statuses distinguish a real file, a directory (never recursed), a remote
URL, a `file://` URI naming another host, a virtual/promise entry, a malformed
URI, invalid encoding, an over-long path, a missing path, an unreadable path and
a non-regular file. Directories are explicit items; nothing is followed.

### Memory, threads, reentrancy

A request is one heap block, immutable after the call returns `EXR_DROP_OK`.
Any thread may read it; the last owner calls `exr_drop_request_release` once
(NULL is accepted). Parsers are reentrant and thread-safe and keep no global
state (verified by a reentrant parse from inside the cancellation poll and 200
parses on a worker thread). A target belongs to the thread of its native
control: Windows STA with `OleInitialize` performed, GTK/AppKit main thread.
Destroying a target from any other thread returns `EXR_DROP_WRONG_THREAD` and
changes nothing. A target may destroy itself from its own callback; the COM
object on Windows then survives until OLE releases it after `Drop` returns.

### Limits and cancellation

| Limit | Value |
| --- | --- |
| Items per request | 256 (rejected entries included) |
| UTF-8 bytes per local path | 4096 |
| Sanitized diagnostic text per item | 256 |
| Platform payload per call | 1 MiB (UTF-16 payload: 512 Ki units) |

Exceeding the item cap keeps the first 256 entries and records
`overflow_count`/`truncated`; an over-long path becomes one
`EXR_DROP_ITEM_TOO_LONG` item; a payload above the byte budget fails as a whole
with `EXR_DROP_TOO_LARGE`. `control->cancelled` is polled before each entry; a
nonzero answer frees everything and returns `EXR_DROP_CANCELLED`. A request is
all-or-nothing: the commit boundary is the return of `EXR_DROP_OK`.

## Platform heads

### Windows — `exr_desktop_drop_windows.h`

`exr_drop_windows_attach(HWND, options, &target)` registers this module's
`IDropTarget` with `RegisterDragDrop`. Accepted formats, in order: `CF_HDROP`,
`CF_UNICODETEXT`, `FileGroupDescriptorW` (a promised file, reported as
`EXR_DROP_ITEM_VIRTUAL` and never materialised); anything else answers
`DROPEFFECT_NONE`. `exr_drop_windows_clipboard_request` reads the clipboard
with bounded retries (80 ms) and copies everything it needs, so the request
survives `CloseClipboard` and the owning process. `exr_drop_windows_deliver_drop`
delivers a completed drop through the same entry OLE calls for
`IDropTarget::Drop` with identical effect negotiation and callback ownership;
hosts use it to forward a drop another window received, acceptance uses it where
no pointer device can start a drag.

### GTK3 — `exr_desktop_drop_gtk.h`

`exr_drop_gtk_attach(GtkWidget*, options, &target)` installs a real drop
destination (`gtk_drag_dest_set` with `GTK_DEST_DEFAULT_MOTION |
GTK_DEST_DEFAULT_DROP`, targets `text/uri-list` and
`x-special/gnome-copied-files`) and connects `drag-data-received`,
`drag-leave` and `destroy`. `exr_drop_gtk_request_from_selection` reads the
selection target name and the exact bytes GTK delivered;
`exr_drop_gtk_clipboard_request` asks the clipboard for `text/uri-list` then
for `x-special/gnome-copied-files` and returns `EXR_DROP_EMPTY` when nothing is
available. Neither writes to, clears or takes the clipboard. If the widget dies
first the target becomes inert and destroy only frees memory.

### AppKit — `exr_desktop_drop_apple.h`

`exr_drop_apple_attach(NSView*, options, &target)` inserts one transparent
child `NSView` pinned to the host's bounds and registers
`NSPasteboardTypeFileURL`, `NSPasteboardTypeURL` and `NSPasteboardTypeString`
on it. The host view is not subclassed, replaced or otherwise modified; detach
removes the child. Reads, in order: pasteboard URLs (file URL without a host →
native path, file URL with a host → `REMOTE_HOST`, other URL → `REMOTE_URL`),
the legacy `NSFilenamesPboardType` array, then plain string text split into
entries. A pasteboard with content but no file-like representation is
`EXR_DROP_UNSUPPORTED`; an empty one is `EXR_DROP_EMPTY`.

## Host integration example

`extras/desktop-drop/examples/` builds a C and a C++ host against the installed
package only (`find_package(EXReaderDesktopDrop 0.1 CONFIG REQUIRED)`), iterates
the request, passes only `FILE` entries to an import stub and releases the
request. It demonstrates the ownership rule the SDK contract requires: the path
stays immutable until `exr_sideload_import_file()` returns.

## Acceptance

```
bash tests/reader_desktop_drop/check_scope.sh
cmake -S extras/desktop-drop -B build/module -DCMAKE_INSTALL_PREFIX=$PWD/build/stage
cmake --build build/module && cmake --install build/module
cmake -S extras/desktop-drop/examples -B build/examples -DCMAKE_PREFIX_PATH=$PWD/build/stage
cmake -S tests/reader_desktop_drop -B build/accept -DCMAKE_PREFIX_PATH=$PWD/build/stage
cmake --build build/accept
build/accept/drop-check                                    # portable matrix
build/accept/drop-probe                                    # native matrix
python3 tests/reader_desktop_drop/check_results.py --platform <platform> ...
python3 tests/reader_desktop_drop/check_aggregate.py       # rejection regressions
python3 tests/reader_desktop_drop/aggregate.py --output build/report
```

All builds, tests, fixtures and artifacts run on GitHub Actions only. The guard
proves `HEAD == GITHUB_SHA`, that the fixed start is an ancestor, that the
frozen SDK and every shared path are byte-identical to it, and that only this
package's whitelist changed. Per platform the acceptance project is configured
from the installed prefix, and `check_results.py` requires every named case,
recomputes the binary and log digests it binds, and refuses unplanned skips. The
report job re-downloads each artifact of the same run, checks name, id, byte
size, API digest and expiry, recomputes the ZIP SHA-256, re-reads the platform
report and re-hashes every file that report binds.

## Not covered

- No physical-device or interactive drag gesture: the drop path is exercised
  through the same native entry the OS calls, with real data objects and real
  pasteboards, but no pointer motion is synthesised.
- No host wiring: attaching the adapter to a production host window is left to
  the host owners; this package ships the module, the example and the probes.
- Windows COM reclamation when the window is destroyed before detach: OLE keeps
  its own reference, the target frees only its own and the registration dies
  with the window, so that corner leaks one small object.
- No filesystem, network or archive access is performed, so drag-and-drop of
  remote or virtual entries stops at the reported status.
