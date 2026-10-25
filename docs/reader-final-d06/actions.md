# Semantic action / routing ledger

Source references below are at baseline 0889 unless mode says candidate. `observed`
results are only in Actions execution reports; this table is source mapping, not
runtime success. All unmentioned native focus restoration is **pending**, not inferred
from a handler name. For every row enter/exit focus means the native platform focus,
not the existence of a view. Common idle requirement means no active saving/operation;
compile-time optional surfaces must actually be present in the tested binary.

## Windows (default / compact separately)

| Action | Entry / label and input | Context, enablement / handler | Entry → exit focus; expected result |
|---|---|---|---|
| Import | default path + 导入 / Ctrl+I on page; compact 导入书籍 / Ctrl+O | idle host; `host_command(IDC_IMPORT_BUTTON)` / `compact_import` | file chooser → caller pending; library count increases, cancel preserves it |
| Open | 打开所选书籍 / default Ctrl+O; compact menu | selected shelf book, idle; `host_command(IDC_OPEN_BUTTON)` | shelf → page; actual book frame |
| Continue | compact 继续阅读 | saved current/last book; `compact_switch` | page; default dedicated entry missing |
| Return shelf | compact 书架 / Alt+Left | host descendant, enabled; `compact_translate`, `compact_switch(0)` | shelf focus runtime; default dedicated compact return missing |
| Previous / next | 上一页 / 下一页, page Left/Right/PgUp/PgDn | page owner, not busy; `page_procedure`, `page_step`, preferences direction | page stays; actual label/frame changes |
| Directory | 目录 / Ctrl+G | navigation option, current book; `winnav_translate`, `winnav_show` | rows → restored page; Escape closes, Return activates rows |
| Search | 书内查找 / Ctrl+F (not Shift) | main window enabled; `winsearch_translate`, `winsearch_show` | query → page on close; Enter submits query or row |
| Reading records | 书签与阅读记录 / Ctrl+L | records option; `winrecords_translate`, `winrecords_show` | record rows → page pending; Return row activates only outside history |
| Bookmark / annotation | records commands; 标注编辑 / selected text | current book and valid selection; records owner / legacy note commands | editor/record rows; save must be observed, not inferred |
| Settings | native menu / Ctrl+, | prefs option + enabled host; `prefs_translate`, `prefs_show` | dialog field → page pending; Apply explicit |
| Cloud account | 同步账号 / Ctrl+Shift+A | no existing account dialog, enabled host; `acct_open_dialog` | credential field → caller pending |
| Cancel | task cancel / Escape in search and records | running dialog cancels rather than closes; `winsearch_cancel`, `job_cancel_button` | dialog remains; second Escape closes after cancellation |
| Confirm | native buttons / Enter | focused query vs result row; dialog-specific handlers | query/results context; repeated submit pending |
| Close popup | 关闭 / Escape / window close | search/nav/records-specific close | actual focus restoration in native reports only |

Dispatch order in `examples/reader.c:message_loop`: search → navigation → records →
metadata dialog → account dialog/shortcut → import-organize dialog/shortcut → preferences
IsDialogMessage/translator → compact translator → main IsDialogMessage → native dispatch.
This order, not J08, decides whether text, modal or menu owns keys. Search Enter is
query/row-specific; Escape cancels while running. Page arrows are handled by the page
window, so editable controls should retain their own arrows. Modal Tab/Shift+Tab are
native IsDialogMessage behavior; actual search cycle is re-executed, other dialogs pending.

## GTK (default / compact separately)

| Action | Entry / key or gesture | Context / handler | Focus and expected result |
|---|---|---|---|
| Import | Import / F1; compact Import menu | not choosing file; `action("import")` | chooser, Escape restore pending new trace; import yields book |
| Open | shelf row Return/activation | selected book; `shelf_activated` | reader page, rendered current book |
| Continue | compact Continue reading | last book known; compact action | reader page; default dedicated entry missing |
| Return | F2 / compact Library | `action("shelf")`, restore scheduling | shelf list; book retained |
| Previous/next | F3/F4; preferences Left/Right/PgUp/PgDn | `key`, `preferences_turn_key`; idle reader, hardware mode; excludes Entry/TextView | page/result label changes, focus stays owning widget |
| Directory | Ctrl+Shift+T / Directory | `directory_open` | dialog rows; close restore observed by compact driver |
| Search | Ctrl+Shift+F / Search within book | `inbook_open` | query; **Ctrl+F is bookshelf search** |
| Records | Ctrl+Shift+R / Reading records | `reading_records_open` | rows/close; new compact driver records native AT-SPI focus |
| Bookmark / annotation | records save; F7 text, F11 comment, F8 note, F9 notes | real selected text; `action` / records owner | selectable text/comment/notes; source token is not pass |
| Settings | Ctrl+, / Reading settings | `preferences_open`; optional | dialog → prior control pending source; actual compact traces |
| Cloud | Ctrl+Shift+A / Account and Sync | `accounts_open`, optional account owner | root/username/password → prior owner pending |
| Cancel | Escape / Cancel current operation | `action("cancel")`: busy and not saving | cancellation retains accepted position |
| Confirm | dialog-specific buttons / Return | native focused control and owner callbacks | must observe side effect, not just clicked handler |
| Close | Close / Escape | individual dialog callback | compact records actual focus snapshots |

`examples/linux/reader.c:key` returns early while record/navigation/search/preferences/
account dialogs are open. File chooser returns FALSE, giving native chooser ownership.
Hardware page-turn excludes text Entry/TextView, but F3/F4 use a separate action path:
**text-focus F3/F4 needs explicit runtime investigation**, not treated as an arrow-key bug.
The compact candidate changes presentation; each executed mode is separately named.

## Apple: separate macOS, iPhone, iPad records

All three use the shared SwiftUI symbols below; three source mappings do not constitute
three executed results. macOS native key-equivalents/focus testing pending. iPhone and
iPad touch-only mapping does not imply external-keyboard support. No explicit
`.keyboardShortcut` mappings were located in the inspected Host* view surfaces.

| Action | Entry / handler | Context/enabled; entering → exiting focus |
|---|---|---|
| Import | 打开文件… → `importing=true`, fileImporter | native picker; focus pending separately for all three |
| Open | shelf book title → `model.openBook` | available shelf row; library → reader, native focus pending |
| Continue | no distinct dedicated entry identified | missing/pending rather than inventing shortcut |
| Return | 书架, `reader.back` → `model.backToLibrary` | reader; shelf focus pending |
| Previous/next | `reader.previous`, `reader.next` → model page turn | `.disabled(model.busy)`; frame must change |
| Directory | 目录, `reader.navigation` → prepareNavigation/showNavigation | idle reader; sheet native focus pending |
| Search | 查找, `reader.search` → prepareSearch/showSearch; 查找 → findInBook | idle reader; search query focus pending |
| Records | 更多阅读操作 → 阅读记录 → prepareReadingRecords | idle reader; sheet row focus pending |
| Bookmark/annotation | 添加书签 → saveReadingRecord(bookmark:true); 选文/标注 | current document/selection; save native side effect pending |
| Settings | 阅读主题 via more menu (compile option) | page theme sheet; no claim of full settings parity |
| Cloud | HostAccountViews account controls | `.focused($focused)` on root/user/password; submit clears focus, disappear clears fields |
| Cancel | `reader.cancel` → cancelWork; sheet-specific cancel | busy reader or relevant sheet; not assumed global Escape |
| Confirm | 保存/确认打开本章开头/删除 role | sheet-specific; destructive confirmation must be explicit |
| Close | 关闭 → presentation.dismiss; account 完成 → dismiss | previous focus pending on each platform |

## Android

`MainActivity` plus SearchPanel/NavigationPanel/ReadingPanel/PreferencesPanel are actual
native surfaces. Touch targets are legitimate entry points; desktop shortcuts are not
required. Static source does not establish DPAD execution or TalkBack speech.

| Action | Native entry / routing | Context / focus and result |
|---|---|---|
| Import/open | shelf import/system document picker; shelf item click | actual picker callback / selected book; focus pending |
| Continue | selected stored book reopen; distinct dedicated entry not established | missing dedicated mapping, no internal API substitute |
| Return | Android Back → `leaveReader` | reader visible, after higher-priority panels; shelf focus pending |
| Previous/next | reader controls/gestures; `dispatchKeyEvent` DPAD/PgUp/PgDn | hardware input 4, current book, not select mode, operation 0, reader visible |
| Directory | navigation panel entry | panel selection; pending native focus/action replay |
| Search | search panel entry | edit field; input ownership pending |
| Records | reading records panel | records controls; pending new execution |
| Bookmark/annotation | record bookmark and selection annotation entries | valid current book/selection; pending |
| Settings | preferences panel | dismiss posts reader.requestFocus; actual focus still pending |
| Cloud | native account entry | credential input; no real account used |
| Cancel/confirm/close | panel buttons, Android Back | panel-specific callbacks; all pending new runtime evidence |

Back precedence from `MainActivity:onBackPressed`: preferences → reading records →
navigation → search → organization → notes → reader → superclass. Organization restores
previousFocus if still shown. Hardware dispatcher suppresses repeat-down turns but consumes
matched key-up; **it has no explicit current-focus/EditText test or modifier filter** in
this branch, unlike GTK. Whether a dialog intercepts before Activity is an unresolved
runtime hypothesis, not a confirmed text-input defect. This is a high-priority native
external-keyboard regression to reproduce with source/current binary held fixed.

## Differences, conflicts and unique owners

| ID / priority | Finding / reproduce | Expected / actual source | Unique owner |
|---|---|---|---|
| D06-01 / P1 | default page Ctrl+O versus compact Ctrl+O | same semantic action desirable; default open selected vs compact native import picker | Windows compact/root integration owner |
| D06-02 / P1 | Ctrl+F on GTK vs Windows, both in reader | GTK bookshelf search vs Win in-book; GTK in-book Ctrl+Shift+F. Intentional current mapping but labels/docs must make it predictable | GTK host owner |
| D06-03 / P1 hypothesis | Android hardware-mode input, focus edit then DPAD with modifiers | text should retain editing; Activity dispatch lacks explicit EditText/modifier guard. Must reproduce before product defect verdict | Android preferences owner |
| D06-04 / P2 | macOS shortcuts/exit focus | inspected shared views lack explicit key equivalents; do not borrow J08 claims | Apple host owner |
| D06-05 / P2 | repeated submit while job pending, each host | one committed action; repeated-open test is not repeated-submit coverage | root action-integration owner |

Allowed conventions: Cmd on macOS vs Ctrl elsewhere; Android system Back vs desktop
Escape/Alt+Left; touchscreen actions need not expose desktop shortcut keys. No production
patch is proposed here; owners receive precise route/context and retained failures.
