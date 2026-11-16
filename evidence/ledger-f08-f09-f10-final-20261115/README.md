# F08 / F09 / F10 final round (2026-11-15)

Branch `codex/ledger-f08-f09-f10-final` (base main `85bfffef`). Scope: `SCOPE-windows-only.md` (2026-11-15). Windows + Linux runnable hosts must both be complete for `verified`; the other four targets only record build-only facts; screen-reader recordings are excluded by scope.

**Result: F08 / F09 / F10 = partial.** The Windows work below is backed by real Actions runs. The Linux GTK equivalents (and a few Windows items) are still missing, so none of the three is marked verified.

## Runs (all windows-2022, workflow `.github/workflows/ledger-f08-f09-f10-final.yml`)

| run | source | result | artifacts (id, bytes, digest) |
|---|---|---|---|
| [43782890323](https://github.com/NoGod3524/EXReader/actions/runs/43782890323) | `30fd04ad` | failure, then cancelled: corpus fetch refused pg11 (gutenberg.org now serves a regenerated `pg11-images-3.epub`, sha256 `42de49e8…`, 189255 bytes, not the pinned `4f81245d…`) | — |
| [43783330321](https://github.com/NoGod3524/EXReader/actions/runs/43783330321) | `125e3e05` | success / success | checks 14189980049, 106190 B, `sha256:2a09b047…4222`; keyboard 14189905770, 525938 B, `sha256:12994acd…4072` |
| [43784359983](https://github.com/NoGod3524/EXReader/actions/runs/43784359983) | `abecdad0` | success / success (**final source**) | checks 14189712567, 106227 B, `sha256:97848202…7310`; keyboard 14189573783, 526195 B, `sha256:a0b4ed87…82f0` |

From 43783330321 on, the workflow seeds `build/f08-books` from the tracked `evidence/dfinal-b-budget-security-20261114/frozen-books/`. `render_budget.py --fetch-corpus` still verifies every SHA-256 (`verified cached original` ×3 in `f08-fetch.txt`).

Archived (excluding `host-data/`): `run-43783330321/`, `run-43784359983/` (`checks/` = identity, ctest.txt, ctest.xml (final run only), new-checks.txt, f08-*; `keyboard/` = identity, binary, fetch, f09-keyboard.txt, f09-keyboard/*.json*).

Full CTest on both successful runs: **601/601** (`ctest.txt`).

## Real product defects fixed

1. **Build break**: `examples/windows/shell_d2d.cpp:206` `LARGE_INTEGER x = {0}` → `{}` (MinGW `-Werror=missing-field-initializers`). `cmake --build build/handoff-win` is 0 errors.
2. **F09 dictionary Tab trap**: read-only multiline EDITs answered `WM_GETDLGCODE` with `DLGC_WANTALLKEYS`. `shell_readonly_edit_release_tab()` (`shell_footnotes.inc`) is applied in `dict_control()` (dictionary/vocabulary/sync status bodies) and to the footnote body. Regression: `check_shell_dictionary.inc` `dictionary_expect_tab_release()` uses a stock-EDIT negative control.
3. **F09 shelf view was mouse-only**: `系列、标签与阅读统计` (`shell_shelfmeta.inc`) was one Tab stop with no keyboard activation. Every painted target is now a stop (Tab/Shift+Tab/arrows, Enter/Space, Apps/Shift+F10), with a focus ring, scroll-into-view, and the accessible name following focus. Regression: `check_shell_shelfmeta.inc` `shelfmeta_keyboard()`, 17 stops (`ctest.xml` of run 43784359983: `SHELFMETA keyboard: 17 stops … PASS`).
4. **F10 startup scavenger was missing**: `sy_startup_scavenge()` (`shell_sync.inc`) is called from `reader.c` before `settings_load()`. It removes interrupted `*.tmp` stages in data_dir, annotations and sync, plus `opds-downloads/*.part`, without recursing. It never touches a live writer, reparse point, directory, hard link or `sync.cred.tmp`, and it deletes through the validated handle.

## F08 — partial

Recomputed from raw samples by `F08-summary.py` (`F08-summary-4378*.txt`, `recompute_agrees_with_exporter=True`). Final run 43784359983, candidate side, 3 fresh processes × 64 samples per book:

```text
pg1.epub  render p50/p95 0.400400/0.497500 ms  present p50/p95 0.142800/0.193800 ms  first_interactive 24.552 ms  peak_ws 24670208
pg10.epub render p50/p95 0.376100/0.381100 ms  present p50/p95 0.140400/0.150000 ms  first_interactive 157.965 ms peak_ws 30806016
pg11.epub render p50/p95 0.475250/0.576800 ms  present p50/p95 0.146800/0.196000 ms  first_interactive 19.163 ms  peak_ws 21815296
budgets (render-corpus.json): first_interactive 2500 ms, render/present p50 50 ms, p95 100 ms, peak 256 MiB → all within; passed=accepted=True
```

What is measured: `present` = `compose_page_view + paint_page_view + shell_paint (D2D EndDraw, QPC-timed in shell_d2d_end, present_count asserted) + GdiFlush` on the test process's off-screen popup HWND. This is the real D2D present path, but **not** vsync/DWM presentation on a visible display (locally the same code read ≈31/45 ms under DWM pacing; on the runner ≈0.14 ms). `first_interactive` = cold bounded-EPUB open → first present → keyboard selection round trip → present. It is measured inside the process, not from process launch.

Gaps: ① Linux GTK frame-time percentiles (`docs/validation/reader-perf-gtk.json` `not_granted.frame_time_percentiles=false`). GTK first-interaction and RSS already exist in run 40086971620 (`startup_key_response` p50 197.924 ms, VmHWM median 69008 kB) but have no hard budget. ② The Windows workload is a fixed spine part of 3 books, not a populated large shelf. ③ No display-vsync timestamps.

## F09 — partial

Real SendInput, `set_foreground_calls=1`, 507 keyboard observations, all 8 surfaces collected, `audit_completed=True` (`F09-summary-43784359983.txt`; r2 run 43769173285 had exit 1 at the dictionary trap with 3 surfaces missing).

- dictionary-settings: `添加目录 → 移除目录 → 选中即查 → 词典加载状态 → 生词本 → 关闭 → 词典目录` (生词本 now reachable).
- vocabulary: 5 reached, webdav-account: 12 reached.
- shelf (`F09-shelf-cycle-*.txt`): before (43783330321) 61 consecutive presses on `系列、标签与阅读统计`. After (43784359983): 10 distinct stops, longest same-element run 1: `网格视图 → 列表视图 → 阅读统计 → 返回阅读 → 书源 → 打开书籍 → 标签筛选：全部 → 未分类 → 书籍：Alice's Adventures in Wonderland`, then back to 网格视图.

Remaining gaps: ① `name_role_passed=False` from a single element: vocabulary `按书筛选` ComboBox's inner UIA TextControl (system combobox proxy, offscreen, name empty; not a separate Tab stop; not patched). ② Not in the measured Tab sequence: toc `目录列表` and chapter items, search `上一处/下一处`, settings `阅读设置/▾`. ③ The shelf view exposes its focused item as the view's name, not as separate UIA child elements. ④ Linux GTK: AT-SPI audit run 40082300842 (`docs/validation/reader-a11y-gtk.json`) audit_completed=true but six blocking findings, accessibility_accepted=false. Screen-reader recordings are excluded by scope.

## F10 — partial

Final run 43784359983 `new-checks.txt` / `windows-privacy-cleanup`:

```text
PRIVACY startup scavenger removed=2 kept=3: abrupt-exit state.json.tmp and opds-downloads/book.epub.part removed, original preserved; live writer, hard link, directory, non-suffix, nested and unowned sync.cred.tmp kept
PRIVACY startup scavenger: stage released by its writer is removed on the next startup
```

Both stages come from a real child process that writes, flushes and `ExitProcess(77)`s. The test points `EXREADER_ANNOTATIONS_DIR` at its own temp root, so it never touches a real profile. Existing checks still pass in the same suite: TokenUser owner/protected DACL on `sync.cred`, forced-termination credential stage recovery, DPAPI round trip and tamper rejection (`windows-selection-sync`).

Remaining gaps: ① Credential Manager `UNAVAILABLE` fallback still not induced for real (`tests/reader_credentials/strict_contract.py` PENDING; not retried here). ② `apps/reader/desktop/windows_accounts.inc` has not been re-run on main source since run 40118190108. ③ The `examples/windows` shell still stores WebDAV secrets with DPAPI (`sync.cred`, current-user, private DACL), not Credential Manager. ④ Cross-user (second identity) not tested. ⑤ TLS only uses the loopback test CA. ⑥ Linux GTK Secret Service fallback / temp-file recovery / TLS. The other four targets are same-source builds without device acceptance, not counted under scope.

## Reproduce

```text
python evidence/ledger-f08-f09-f10-final-20261115/F08-summary.py evidence/ledger-f08-f09-f10-final-20261115/run-43784359983/checks/f08-realbooks.json
python evidence/ledger-f08-f09-f10-r2-20261115/F09-runner-summary.py evidence/ledger-f08-f09-f10-final-20261115/run-43784359983/keyboard/f09-keyboard
python evidence/ledger-f08-f09-f10-final-20261115/F09-shelf-cycle.py evidence/ledger-f08-f09-f10-final-20261115/run-43784359983/keyboard/f09-keyboard
```

Standard library only.
