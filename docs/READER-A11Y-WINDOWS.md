# READER-A11Y-WINDOWS: Windows keyboard and accessibility audit

Audit package. Tests, workflow and documentation only; the product host, the SDK and
the product database are unchanged. Nothing in this branch is a production fix.

- Implementation start: `f43baf9182d75907c0cb5d6f77048f27bca8c950`
- Result of record: `da2bcde7d684c1db8a9a51de9a7d478d870d5149` (run 40084309431, attempt 1)
- SDK identity: `9854061be331fe603a1822d9b2b36ee357154927`; product schema
  `f32bb8aa18ed3de286900f19ce4230fd93435dd0`. The workflow fails if either tree moves.
- Audited binary: the packaged product host `EXReaderProduct.exe` (product catalog +
  desktop metadata), sha256 `df70f4716ce82539f595f3fc3204f3de1c0479c9315628412f3689e5b5b03fc8`.

## Verdict of record

| field | value |
| --- | --- |
| audit_completed | **true** (49 named checks, 0 harness errors) |
| accessibility_accepted | **false** (8 blocking findings) |
| screen_reader_verified | **false** (no NVDA/Narrator/human pass was run) |
| evidence verified | **true** (strict verifier accepted the raw records) |

49 checks: 34 pass, 9 fail, 5 gap, 1 not_verified, 0 error.
Blocking: SH-04, KB-06, RD-02, KB-07, KB-01, AN-02, OR-09, KB-05.

| flow | checks | pass | fail | gap | not_verified |
| --- | --- | --- | --- | --- | --- |
| shelf 书架 | 7 | 6 | 1 | 0 | 0 |
| import 导入 | 6 | 4 | 1 | 1 | 0 |
| organize 整理 | 11 | 8 | 2 | 1 | 0 |
| reading 阅读 | 7 | 6 | 1 | 0 | 0 |
| annotation 标注 | 6 | 5 | 1 | 0 | 0 |
| settings 设置 | 5 | 3 | 0 | 2 | 0 |
| keyboard 键盘 | 7 | 2 | 3 | 1 | 1 |

## Blocking findings

Each item lists the element, how to reproduce it, expected versus actual, and the
smallest change that would clear it. Full records (steps, evidence references,
raw values) are in the report artifact.

### SH-04 shelf search field has no accessible name

- Element: `IDC_SHELF_SEARCH` (control id 126), class `Edit`, direct child of `EXReaderHost`.
- Steps: launch the host, read the UIA element of control 126.
- Expected: a name such as 书架搜索, independent of the role.
- Actual: `name='' , control_type='EditControl', help='' , access_key=''`.
- Fix: give the box its own window text or a provider name (`SetWindowTextW(g.shelf_search, L"书架搜索")`),
  the same way the import field inherits 导入路径 from its static label.

### AN-02 annotation comment field has no accessible name

- Element: `IDC_NOTE_EDIT` (control id 122), multiline `Edit`.
- Steps: read the UIA element of control 122.
- Expected: a name such as 标注内容.
- Actual: `name='' , control_type='EditControl'`. The adjacent static is 标注（双击跳转）,
  which names the list, not the editor.
- Fix: set an accessible name on the multiline edit.

### RD-02 page content is not readable through UI Automation

- Element: `IDC_PAGE` (control id 123), custom class `EXReaderPage`.
- Steps: read the element's patterns and walk its children.
- Expected: the page text readable through a Text or Value pattern, or as child text.
- Actual: `patterns=['LegacyIAccessiblePattern'], child_count=0`; a screen reader gets the
  name 阅读区域 and nothing of the page.
- Fix: implement a UI Automation text provider over the painted page text, with the
  selection as the text selection range.

### KB-05 the host implements no accessibility provider (root cause of RD-02)

- Element: `EXReaderPage` served by the default proxy.
- Steps: `git grep` the host sources for provider entry points.
- Expected: a provider for the custom widget.
- Actual: `WM_GETOBJECT=0, UiaReturnRawElementProvider=0, IAccessible=0` in
  `examples/reader.c` and `apps/reader/desktop`; only standard Win32 controls answer.
- Fix: implement `WM_GETOBJECT` on `EXReaderPage` (UiaReturnRawElementProvider or the
  MSAA bridge) so the page and its selection are exposed.

### KB-06 an activated command drops keyboard focus to nothing

- Element: `IDC_IMPORT_BUTTON` (control id 102).
- Steps: Tab to 导入, press Space, read `GetGUIThreadInfo(hwndFocus)`, then press Tab twice.
- Expected: focus stays on 导入, or moves to a defined stop.
- Actual: focus becomes `NULL` immediately (`focus='none'`), and two Tabs keep it at
  `none`. The command disables itself through `host_update_controls()` while it holds focus.
  The same happens for the 刷新 command (control id 127).
- Fix: in `host_update_controls()`, when the command that currently holds focus is about to be
  disabled, move focus to the next enabled control (or keep it enabled until the job
  finishes and disable only the actions that would re-enter).

### KB-07 the annotation comment field traps Tab and Shift+Tab

- Element: `IDC_NOTE_EDIT` (control id 122), `ES_MULTILINE | ES_AUTOVSCROLL | WS_VSCROLL`.
- Steps: Tab to the comment field, press Tab twice, then Shift+Tab twice.
- Expected: focus leaves the field in both directions.
- Actual: `after two Tabs=['note_edit','note_edit']` and the same for Shift+Tab; the keys are
  inserted as tab characters instead of moving focus. A keyboard-only user who enters
  the field cannot leave it without a mouse.
- Fix: do not answer `WM_GETDLGCODE` with `DLGC_WANTALLKEYS` for Tab, or forward Tab to
  `IsDialogMessage` from the edit so the dialog manager performs the traversal.

### KB-01 no clean Tab cycle (consequence of KB-07)

- Steps: press Tab from the first stop until a stop repeats.
- Expected: each enabled stop once, then back to the first.
- Actual: 20 stops, cycle closed, but 7 stops had to be resumed by the audit after the
  trap; a user has no such resume. Covered by KB-07; re-measure after the fix.

### OR-09 focus does not return to the command that opened the details dialog

- Element: `IDC_METADATA_BUTTON` (control id 128) / dialog `#32770` 书籍详情.
- Steps: Tab to 详情, press Space, put the focus on 书名, press Escape, read the focused control.
- Expected: focus back on 详情.
- Actual: `focused control after close='EXReaderHost:EXReader'` — the owner window, not the
  invoking command.
- Fix: in the dialog's `WM_DESTROY` call `SetFocus` on the invoking button;
  `SetActiveWindow(g.window)` alone does not restore keyboard focus.

## Serious findings and recorded gaps

| id | status | finding |
| --- | --- | --- |
| IM-06 | fail | focus is not kept on 导入 after the import (same cause as KB-06) |
| OR-10 | fail | the owner window is disabled, but its children still report `IsEnabled=true` to UIA |
| IM-05 | gap | status changes raise no accessibility event (`NotifyWinEvent=0`) |
| OR-06 | gap | 保存 carries `Alt+s`, 取消 carries no access key |
| ST-04 | gap | the Windows host has no settings surface; inline 字号/缩放 plus `host.ini` are the whole flow |
| ST-05 | gap | 0 of 18 main-window buttons expose an AccessKey |
| KB-02 | not_verified | the trap makes a reverse-order measurement meaningless; recorded, not claimed |

## What the keyboard audit confirms works

Bookshelf list with names and real item strings; keyboard import of a book; reading
region reachable with Tab after 17 stops and **with a visible focus rectangle**
(1390 changed pixels, 3 of 3 samples); page turning with arrows; position text
exposed (章 1 · 本章第 1 页 · EPUB · 字号 150%); Ctrl+A and Ctrl+C (432 bytes on the
clipboard); annotation add, jump and delete from the keyboard; 字号 change and its
persistence (`host.ini FontPercent=160`); fixed-page zoom with the right per-book
state (字号 disabled, 缩放 100→125); details dialog opens, is named 书籍详情, its
title/author edits report 书名(T)/作者(A), the 收藏 checkbox exposes `Alt+f` and a
toggle pattern, its Tab cycle is 书名→作者→收藏→保存→取消→书名, Escape closes it, and Enter
runs the default 保存 (status 书籍信息已保存。); the search box filters the shelf to
《Pages》 — 未知作者 · PDF; UIA focus agrees with `GetGUIThreadInfo` at every sampled stop.

## Method

1. Build the unchanged reading SDK, the product catalog provider, the native metadata
   commands and the product host; package the payload with its preserved 26-check
   self-test.
2. Launch `EXReader.exe --data <private directory>` with no driver script; every state change
   after that comes from a key event, not from `WM_COMMAND` or `BM_CLICK`.
3. Transport is `SendInput` (hardware-level input to the focused window, so the host's own
   message loop and `IsDialogMessage` do the work). The runner probe recorded
   `transport=sendinput`, `host_foreground=true`, `interactive_desktop=true`.
4. Controls are identified by `IDC_*` id plus window class; the run aborts if the binary does
   not create the expected control set.
5. Each claim is one named check with element locator, steps, expected and actual
   value, severity, evidence reference and a minimal fix.
6. Visible focus is measured: the window is captured with
   `PrintWindow(PW_RENDERFULLCONTENT)` while a control has focus and again after focus moves,
   and the pixels inside that control's rectangle are compared (3 samples, best kept).
7. Two blocking defects take the audit off the keyboard path (KB-06, KB-07). Each is
   recorded first, then the audit resumes focus through its own thread attach — never a
   mouse — so the later flows stay measurable. Those resumptions are `focus_recovery`
   (6) and `focus_trap_escape` (20) events in the key trace, and the report lists them.

## Evidence identity

| field | value |
| --- | --- |
| workflow | `.github/workflows/reader-a11y-windows.yml` |
| run / attempt | 40084309431 / 1 |
| job | 120843987235 (windows-2022, success) |
| artifact | reader-a11y-windows-40084309431-1 |
| artifact id / bytes | 12556064712 / 1097329 |
| artifact digest | sha256:6fc353809c5dfa865788a6c141781e060b14f6c7e63274eee1c26b8c1e0f1aaf |
| artifact expires | 2027-01-22T10:02:15Z |

The artifact holds `report.json`, `verification.json`, `key-trace.jsonl` (one line per input
event with its transport), five raw UIA trees, four screenshots and the focus crops.

## What is not verified

- **Screen-reader acceptance.** No NVDA, Narrator or human reading pass was run.
  `screen_reader_verified` stays `false`; the report lists the human review still owed.
- Speech quality, verbosity and reading order inside a page cannot be judged by UIA.
- iOS, Android, GTK, sync, OPDS and network features are out of scope for this audit.
- Findings are measurements on this source; the minimal fixes are suggestions for the
  owners of those files (G01/root). No production file was edited here.
- The 26-check self-test of the host is unchanged and still passes at packaging time;
  it is not a substitute for this audit and neither is this audit a substitute for it.

## Reproduce

    cmake --preset reading-library
    cmake --build --preset reading-library
    cmake --install build/reading-library
    cmake -S apps/reader/desktop -B build/desktop-sdk -DEXR_SDK=build/reading-library/stage \
      -DREADER_METADATA_PREFIX=build/product-stage -DCMAKE_BUILD_TYPE=Release
    cmake --build build/desktop-sdk --config Release
    python tools/build_windows_host.py --sdk build/reading-library/stage \
      --binary build/desktop-sdk/EXReaderProduct.exe --output build/a11y-package --static-reading
    python tests/windows_host/make_fixtures.py --output build/a11y-fixtures
    python -m pip install "uiautomation==2.0.29"
    python tests/reader_a11y_windows/run_audit.py --payload build/a11y-package/EXReader \
      --fixtures build/a11y-fixtures --output build/a11y-evidence --verbose
    python tests/reader_a11y_windows/verify_report.py --report build/a11y-evidence/report.json \
      --output build/a11y-evidence/verification.json
