# D02 observations and owner follow-ups

Results below must be read with the exact final run and its evidence index, not as a product grant.

## Confirmed source observations (immutable f355525b)

* `apps/reader/desktop/windows_compact_ui.inc`, `compact_layout`: uses unscaled pixel sizes (12 px margins, 28 px button heights, 80 px button widths). `compact_expand` grows the window to at least 1060×660 without constraining it to monitor work area. Owner should adopt DPI-derived units and work-area-aware minimums, then rerun at real 100/150/200% scales. This is a source diagnosis, not proof of actual clipping at an unavailable scale.
* No `SetProcessDpi*`, `SetProcessDPI*`, `DPIAware` or `WM_DPICHANGED` reference was found in candidate examples, desktop host or windows-account source. Actual awareness must come from the runtime query; source absence alone does not rule out a manifest.
* `examples/reader.c:paint_page_view` fills white and paints the empty-state hint at RGB(90,90,90), then paints rendered SDK bitmap content. `DrawFocusRect` provides a page focus rectangle. These are actual color sources, but neither source nor a theme label proves high-contrast compliance for all states. Owner should review system high contrast behavior separately from ordinary light/dark preferences.

## Harness boundaries

D02 never calls product handlers or `WM_COMMAND`/`BM_CLICK` for state transitions. It observes list counts and controls read-only, injects genuine keyboard input, and uses ordinary window resize for geometric observations. Each failed keyboard route is retained; Escape-only recovery is logged and never reclassified as a clean journey.

Forward/reverse cycle checks only cover the measured initial page and UIA/native focus agreement. They do not certify every state. Text clipping and localized focus visibility remain pending where the automated evidence is not discriminating. UIA trees expose native names, roles and states, not actual screen-reader speech.

The original four-format fixture files and fixed producer programs are authenticated, not rebuilt. No combined-current-source, physical display, NVDA, Narrator, human screen-reader or overall contrast acceptance is granted.

## Actual final run: 40215441500 / attempt 1

Harness `e8b5b1bd200202c06a7a22e5a4ed1f801eb47706`. Native job121235461850 and strict consumer121236012444 success. Audit completed for both configurations; **all acceptance fields remain false**. OFF29 observations:20pass/3fail/6pending; ON30:22pass/3fail/5pending. 34+44 raw BMPs and per-step UIA snapshots authenticated.

### D02-GEOMETRY: window exceeds available work area

Work area `[0,0,1024,728]`. OFF requested1100×720 became1060×720; requested700×480 became1060×660. ON baseline1044×720; compact700×480 fits, but More expansion1060×660 overflows. These are window-bound overflows, **not** proof every control is clipped. Evidence: `OFF/003-baseline-layout.{json,bmp}`, `OFF/004-small-layout.{json,bmp}`, `ON/003-baseline-layout.{json,bmp}`, `ON/034-expanded-small-layout.{json,bmp}`. Reproduce native launch→resize, Alt+V→M for More; compare GetWindowRect with SPI_GETWORKAREA. Fixed full-panel minimum is the source-confirmed cause of its overflow. Owner: work-area-aware minimum, reflow/scrolling and DPI-derived sizing.

### D02-FOCUS: compact shelf search closes onto reading region

After read→Alt+Left shelf return, Ctrl+F→Tab→Shift+Tab→Escape closes search but focus changes from HWND655800 to HWND459364, not its invoker. `ON/020-search.json`, `021-search-closed.json`, `022-search-failed.json` and key trace preserve evidence. Source-confirmed cause: `apps/reader/desktop/windows_search.inc:180-187`, `winsearch_close`, unconditionally `SetFocus(g.page)`. Owner: remember invoking control and restore a visible/enabled target appropriate to shelf/reading state. Reading-state search in the journey returned correctly; do not generalize shelf failure to every invocation.

### D02-ACCOUNT: OFF account Escape timeout; cause unconfirmed

Tab to control137→Space opened account; Tab→Shift+Tab→Escape timed out waiting8seconds for disappearance. Evidence `OFF/025-account.json`, `026-account-failed.json`, key trace. ON entry via Alt+B menu completed with focus return. Source contains IDCANCEL/WM_CLOSE handlers and IsDialogMessage dispatch; **not a proven missing Escape handler**. Timing or foreground/input routing remains a hypothesis. Owner: inspect captured dialog/focus state and replay exact OFF sequence, comparing Close and Escape without real credentials. Only empty account UI opened; no settings submitted.

### Supported observations, narrow scope

- Genuine keyboard import/open succeeded for original TXT/EPUB/PDF/CBZ fixtures, both modes. TXT keyboard page-turn→search→records→return sequence completed. OFF retains dual-pane shelf, so its return assertion is shelf visibility, not a distinct compact Back transition.
- Initial forward/reverse Tab:10unique OFF stops/3unique ON stops, native/UIA focus agree; not all-state coverage. Five reused G12 launch assertions passed unchanged, including shelf search name `搜索(S)`. Historical unnamed-search failure was not carried forward.
- ON Ctrl+O picker cancel restored focus. More/directory/records/settings/account completed. Actual Ctrl+G/Ctrl+L/Ctrl+comma shortcuts, no business callbacks.
- Both programs DPI-unaware0, effective window/system96DPI, monitor100%. Relative150/200 requests returned API success but monitor/window stayed100%/96: **150/200 pending**, not high-DPI passed.
- System high contrast enabled(flags127), changing palette white/black→black/white and highlight cyan/black; initial-page BMPs retained. WCAG ratios are system palette samples, not actual whole-UI paint compliance. Full reading/dialog/focus/disabled-state contrast, glyph clipping and localized focus visibility unverified. Whole-window repaint is not focus visibility proof.

## Evidence integrity and security

Current raw ZIP12607496289:2758064B, SHA256 `db75580f89715d5d3176de758823c2b9585314efdfa5d8f3e7cf814668a25c61`, expires2026-11-24T17:15:54Z. Strict Actions downloaded/verified ZIP bytes, source/run/attempt/upstream job and every indexed observation file. 168extracted files/log inputs passed token/private-key/signed-query pattern scan; no real credentials used. Summary ZIP12607486296:16197B, SHA256 `12dc461f15be0b4338971eee6d2b65e494b1572d742a70b659e6cedcb3abf188`, expires2026-11-24T17:16:11Z: upload digest/API metadata, not recursively downloaded ZIP proof.

## Remaining scope

No real150/200% display, human image review for truncation, localized focus-ring certification, full painted contrast audit, NVDA/Narrator/human speech, physical keyboard or unified-source acceptance. Broad high-DPI/contrast/screen-reader goals remain open despite completed automated evidence collection. Integration must retain pending scopes and measured failures.
