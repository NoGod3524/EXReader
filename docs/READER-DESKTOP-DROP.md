# READER-DESKTOP-DROP: desktop file drop and paste adapter

## Root共存修补：云端已验收

独立分支 `codex/reader-drop-coexistence`，受测完整源码 `335f188352575c8d598a60692104946dfe3f21c3`，[run 40139548335](https://github.com/NoGod3524/EXReader/actions/runs/40139548335) / attempt1，guard、Windows、Linux、macOS与严格同轮汇总5/5success。Windows真实窗口53项（含新增四项共存/回滚）、三平台各便携52项、GTK28与AppKit28全部通过；Windows原hook及ASan变体保留并通过，严格汇总13项拒绝回归通过，认证三平台ZIP及绑定文件。

生产实现使用Windows原生链式子类，只卸载自身；下一层宿主回调内detach由临时COM引用保护；安装失败撤销真实OLE注册，宿主消息和重新attach保持可用。SDK/schema不变，未接生产宿主、未授手势级拖拽或产品性能。新工件ID/完整摘要/大小/有效期及全部旧交回证据在验证JSON内，旧记录完整保留在 `previous_delivery`。

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
`IDropTarget` with `RegisterDragDrop`, then installs one transparent window
procedure so the registration can be released while the window is still valid:
`WM_DESTROY` calls `RevokeDragDrop` (which drops OLE's reference) and
`WM_NCDESTROY` restores the original procedure. Every other message goes to the
original procedure unchanged, detach restores it, and the probe asserts both
directions. A window destroyed before detach therefore leaves no COM object
behind: OLE's reference is gone, detach frees the last one, and the hook build
counts live targets to prove it.

Accepted formats, in order: `CF_HDROP`, `CF_UNICODETEXT`,
`FileGroupDescriptorW` (a promised file, reported as `EXR_DROP_ITEM_VIRTUAL`
and never materialised); anything else answers `DROPEFFECT_NONE`.

Every HGLOBAL is bounded by its real allocation before a single element is
read — the 1 MiB payload budget is a product limit, never a buffer size:

- `CF_UNICODETEXT`: `GlobalSize() / sizeof(wchar_t)` units are scanned; a
  buffer without a NUL inside that extent (including an odd trailing byte that
  cannot form a unit) is refused, never `wcsnlen`-ed past the end. The
  clipboard itself hands back a terminated copy of text, so the clipboard
  negative is the structural HDROP one below, which Windows stores verbatim.
- `FileGroupDescriptorW`: the allocation must hold the whole header, and
  `cItems` must be covered by
  `(GlobalSize() - offsetof(fgd)) / sizeof(FILEDESCRIPTORW)`; a lying or
  extreme count is refused before `fgd[]` is indexed. Zero descriptors is
  `EXR_DROP_UNSUPPORTED`.
- `CF_HDROP`: the header must fit, `pFiles` must lie inside the allocation
  and be at least `sizeof(DROPFILES)`, and the wide or ANSI list must be
  terminated by an empty entry inside the allocation. Wide units are read
  bytewise so a truncated code unit can never be read at all. Only then does
  `DragQueryFileW` see the buffer.

A malformed buffer is refused with `EXR_DROP_PLATFORM` (one callback, no
request, `DROPEFFECT_NONE`). `exr_drop_windows_clipboard_request` reads the
clipboard with bounded retries (80 ms) and copies everything it needs, so the
request survives `CloseClipboard` and the owning process.
`exr_drop_windows_deliver_drop` delivers a completed drop through the same entry
OLE calls for `IDropTarget::Drop` with identical effect negotiation and callback
ownership; hosts use it to forward a drop another window received, acceptance
uses it where no pointer device can start a drag.

Acceptance compiles the module a second time with
`EXR_DESKTOP_DROP_TEST_HOOKS` (a live-target counter that must return to its
previous value around attach/ destroy/ detach) and a third time under
`/fsanitize=address`; both variants run the same probe. The hook counter is
compiled out of the installed binary.

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

## Acceptance result (root-review repair)

Run [40136297928](https://github.com/NoGod3524/EXReader/actions/runs/40136297928), attempt 1,
on tested source `5a0cd498ce4ec570f6cd52c6eca4d611431c1cc0`: guard, the three
platform jobs and the same-run report all succeeded.

| Job | Result |
| --- | --- |
| guard | fixed start is an ancestor, frozen SDK trees and every shared path byte-identical, whitelist-only diff, module SDK-free and out of the default build |
| drop (linux-gtk3) | installed package, host examples and acceptance project built from the installed prefix; 28 GTK cases and 52 portable cases, 0 problems |
| drop (windows-hdrop) | three builds of the same package (release, `EXR_DESKTOP_DROP_TEST_HOOKS` Debug, `/fsanitize=address`) and three probe runs merged by case: 49 native cases and 52 portable cases, 0 problems; 5 sanitizer scan streams clean; the live-target hook shows one target allocated and reclaimed across attach → destroy → detach |
| drop (macos-pasteboard) | 28 native cases and 52 portable cases, 0 problems |
| same-run report | 13/13 rejection regressions rejected, three artifacts re-downloaded and re-hashed against the API digest, reports re-read and every bound file re-hashed, `accepted=True` |

The Windows report binds the release probe, the hook probe, the AddressSanitizer
probe and portable run, and the five stderr scan files, so the memory-safety and
lifecycle claims are part of the attested artifact rather than prose.

Artifacts (all expire 2027-01-22T21:54:59Z):

| Artifact | id | bytes | SHA-256 |
| --- | --- | --- | --- |
| reader-desktop-drop-windows-40136297928-1 | 12577100299 | 12397988 | `7083e89f487d036a41567bad1f5aca808d165c8e878a53853a3658761782ed91` |
| reader-desktop-drop-linux-40136297928-1 | 12576449766 | 306129 | `ecaa015a7747082c778c0adb541564099c407e6fdd00fe4f27e3477ff560ed74` |
| reader-desktop-drop-macos-40136297928-1 | 12576884782 | 396149 | `721670a77465aff845dfa754f008bf9948c8c1e6a627c7ca2fd72c833b5023fd` |
| reader-desktop-drop-report-40136297928-1 | 12577700308 | 834 | `d46a50b416e358643e602833682b7241fdf05b8ae4a82323ebcf6e51631e3018` |

## Previous acceptance (kept)

Run [40123821461](https://github.com/NoGod3524/EXReader/actions/runs/40123821461), attempt 1,
on tested source `f2c95f9a4cc013f294edc55fefe12b8da3d5a5a5` (branch
`codex/reader-desktop-drop`): guard, the three platform jobs and the same-run
report all succeeded.

| Job | Result |
| --- | --- |
| guard | fixed start is an ancestor, frozen SDK trees and every shared path byte-identical, whitelist-only diff, module SDK-free and out of the default build |
| drop (linux-gtk3) | installed package, host examples and acceptance project built from the installed prefix; 28 GTK cases and 52 portable cases, 0 problems |
| drop (windows-hdrop) | 31 native cases (OLE registration, real shell data object, HDROP, Unicode text, virtual descriptor, clipboard, lifetimes, wrong thread, self-destroy) and 52 portable cases, 0 problems |
| drop (macos-pasteboard) | 28 native cases (drag destination, private NSPasteboard, drag double, lifetimes, wrong thread) and 52 portable cases, 0 problems |
| same-run report | 13/13 rejection regressions rejected, three artifacts re-downloaded and re-hashed against the API digest, reports re-read and every bound file re-hashed, `accepted=True` |

Artifacts (all expire 2027-01-22T19:07:07Z):

| Artifact | id | bytes | SHA-256 |
| --- | --- | --- | --- |
| reader-desktop-drop-windows-40123821461-1 | 12572242559 | 1400329 | `28f9f841fdc9a50e3066ddfbd94f4cf29cc5372d6a3e5f9450cb4385b908b15b` |
| reader-desktop-drop-linux-40123821461-1 | 12571374475 | 305884 | `1562100a58a490999eedaa3191fb317a6c835b6bf7c2ba6a0d00dc47bb0496b2` |
| reader-desktop-drop-macos-40123821461-1 | 12571909968 | 395928 | `5e55051f4e93d1e8458329ab8331b05fda00e3eb50120f9534e202dc3f154b0c` |
| reader-desktop-drop-report-40123821461-1 | 12572214740 | 828 | `874ae7b021161f9bc39f325eafe85abd7fd8a5ca3f9a1ce1bbd26c816825599b` |

That run is kept as the first acceptance of this package. It is superseded for
the repaired source by run 40136297928: it could not see the Win32 allocation
bounds, the narrow `CFSTR_FILEDESCRIPTORW` atom or the COM reference that
survived a window destroyed before detach, all of which the repair and the new
run address.

The evidence commit after each run carries `[skip ci]` and changes only this
file and `docs/validation/reader-desktop-drop.json`; the tested source revision
above is what the acceptance actually ran, and the final HEAD differs from it by
those two documentation files only.

## Rejected intermediate results

Every rejection below was observed on GitHub Actions against this package and is
kept in the record; nothing was loosened to turn it green.

| Run | Revision | Rejection | Correction |
| --- | --- | --- | --- |
| 40122278887 | 7a477bdf | Guard failed: the print/log rule also scanned `extras/desktop-drop/examples`, which is a normal host program that prints its result. | The rule now covers the installed module (`src/`, `include/`) only. |
| 40122803440 | 2a813e59 | Linux link failure: `gtk_clipboard_wait_is_available` does not exist in GTK3 (implicit declaration, then an undefined reference). Windows portable matrix rejected six fixtures: percent-encoded URI built without the drive prefix, a localhost fixture that reused the previous expectation, gnome cases parsed through the text/uri-list entry, an over-long "path" that was not absolute on Windows, and a reentrancy poll that never cancelled. | The clipboard reader tries each flavour and treats an unserved target as absent. The fixtures now build platform-correct absolute paths, drive the gnome parser for gnome payloads and assert cancellation *and* a successful nested parse. |
| 40123129432 | 745f152a | Linux: the drop target refused to attach because `g_main_context_is_owner()` is false whenever no loop is running; the clipboard cancellation fixture had a single entry; an AT-SPI warning shared the case stream. | Attachment now also succeeds when no other thread owns the default context and is refused while another thread holds it (asserted by a holder thread). Cancellation uses a two-entry payload; toolkit chatter moved to a separate log and is tolerated by the checker. |
| 40123504735 | cce4c045 | Linux: two detach cases failed because the negative "attach with a NULL widget" case overwrote the live target handle. | Negative attach cases use a scratch handle on GTK and AppKit. |
| 40135689234 | 03babdbe | Windows: MSYS rewrote `/fsanitize=address` into `C:/Program Files/Git/fsanitize=address`, so the AddressSanitizer configure and link failed. The same build surfaced two defects: `CFSTR_FILEDESCRIPTORW` is a narrow literal in this SDK, so `RegisterClipboardFormatW()` received a `char *` (module and probe agreed on the wrong atom, which is why the earlier run passed), and the C form of `IDropTarget::lpVtbl` is a plain pointer, so the table cannot be `const`. | The variant step exports `MSYS2_ARG_CONV_EXCL`, the atom is registered from an explicit wide literal, and the vtable is non-const. |
| 40136007055 | 14b91fbc | Windows: 48/49 native cases passed; the "clipboard text without terminator" negative returned OK because the clipboard normalises `CF_UNICODETEXT` and hands back a terminated copy. | The clipboard negative is now a structural HDROP whose `pFiles` leaves the allocation; the unterminated and odd-length text negatives stay on the `IDataObject` route, where a hostile producer really can hand one over. |

## Not covered

- No physical-device or interactive drag gesture: the drop path is exercised
  through the same native entry the OS calls, with real data objects and real
  pasteboards, but no pointer motion is synthesised.
- No host wiring: attaching the adapter to a production host window is left to
  the host owners; this package ships the module, the example and the probes.
- Windows memory safety is asserted on an AddressSanitizer build of the same
  probe with deliberately tiny, unterminated, odd-length, lying-count and
  out-of-range HGLOBALs; the release build asserts the same named rejections,
  and the hook build proves the COM target is reclaimed when the window dies
  before detach.
- No filesystem, network or archive access is performed, so drag-and-drop of
  remote or virtual entries stops at the reported status.
# Root接续：窗口子类共存候选

分支 `codex/reader-drop-coexistence` 从原交回HEAD `986f2f0132ecdf753d6d428ba821a58175cd0d0c` 独立接续，原分支不改。候选初写时 `accepted=false`；现在按页首新源码实测授予本包范围。原交回绿仍只属于原受测源码 `5a0cd498` / run `40136297928`。

用Windows已有 `SetWindowSubclass/RemoveWindowSubclass/DefSubclassProc` 取代直接覆盖和还原 `GWLP_WNDPROC`，detach仅移除本模块。原生子类调用栈持有临时COM引用，允许下一层宿主回调重入detach。安装失败回滚真实OLE注册，不再依赖未检查成功的SetProp。静态包显式导出系统comctl32链接依赖。

新增四项实际窗口检查：模块先卸载、宿主先卸载、下层宿主在消息栈内卸载模块、注入子类安装失败后宿主消息/COM计数/OLE重新attach均恢复；所有既有HGLOBAL负例、ASan、生命周期、三平台安装消费者及同轮ZIP认证保留。本地仅源码文档Git，未执行构建、语法或测试。原始证据继续保留如下。

