# D03 — GTK scaling and accessibility: authenticated evidence, acceptance withheld

## Outcome

`evidence_authenticated=true`; `audit_completed=false`; `keyboard_accepted=false`; `contrast_accepted=false`; `screen_reader_accepted=false`; `accepted=false`.

The final real-host run exercised eight OFF/ON configurations. The raw checker reported 27/27 passes for each compact ON configuration and 24/25 for each default OFF configuration. **These are raw execution counts, not accessibility acceptance.** Review revoked `records-dialog-focus` in all eight configurations: its presence-only predicate accepted focus on the insensitive main window, outside the modal. Default OFF also failed to close Reading records after bookmark save and Escape, in all four configurations. The final completeness gate remained red. Three failed rounds have been retained; no fourth retry or production edit was made.

The machine-readable [validation.json](validation.json) explicitly records this adjudication, the invalid assertion, and indeterminate 2× geometry/contrast. The original report is preserved unchanged in the authenticated artifact.

## Immutable identities

| Identity | Value |
|---|---|
| Branch | `codex/reader-final-d03` |
| Fixed implementation base | `0889f7d1e9a537c6c1b05456547e016b26e1cd85` |
| Tested harness | `81a67f582ddfe8906b64e6eef4e7969127415ba8` |
| Isolated compact target | `9fc407a5cce5a0bfe644a60bd8dc29f84dea6d0e` |
| SDK source | `edddc463c06ed5731195cdb8f06b2df6dff7699e` |
| Actual packager identity | SDK 3.41.0 / ABI 1; installed header declares core 3.40.0 |
| OFF executable SHA-256 | `13db7c15064481a2bf1bab4cb5f2c054f2845ba599c7f91ee8b5dfa9ca593ea9` |
| ON executable SHA-256 | `409eb3e8d74717730323e4d8dd81ed5eb8da9c4696401840877d929c5fc257eb` |
| SDK base archive SHA-256 | `3537fc62d27671b40f004786323f24c35f2c9d9d36e6ae701c254927f6aa1354` |
| SDK library archive SHA-256 | `8e0a35b5978046372b866c7af7e66e079cfa0c01c835b4c7acab7366970781e6` |

The actual executable bytes, packager manifests and CMake caches were authenticated together. OFF omitted the compact option and read back `EXR_READER_GTK_COMPACT:BOOL=OFF`; ON read back `ON`. SDK archive identities from the same producer log are in [SDK-IDENTITIES.json](SDK-IDENTITIES.json). This is not a claim that the two binaries are the root's future integrated implementation.

## Actions and artifacts

[Run 40218375669, attempt 1](https://github.com/NoGod3524/EXReader/actions/runs/40218375669):

- Producer job `121244359634`, **GTK native scale audit**: success. Source/whitelist guard, syntax, real SDK/module/OFF/ON builds, all eight sessions and artifact upload executed.
- Verifier job `121247583314`, **Authenticate ZIP and same-source coverage**: failure **only at final audit-completeness assertion**, after successful ZIP authentication, file/program identity checks, credential-pattern scan and 13 negative mutations per configuration (104 total). No assertion was removed to make the gate green.
- Primary artifact `12609036554`, `reader-final-d03-40218375669-1`: **35,146,853 bytes**, SHA-256 **`a60100c94b4033f236536efb2274cfd4fd38727e51e9fc63e31bd970187d4496`**, expires **2026-11-08 18:03:36 UTC**. Original ZIP bytes downloaded and size/hash/expiry verified inside Actions.
- Summary artifact `12609126714`, `reader-final-d03-verification-40218375669-1`: **74,463 bytes**, upload/API digest **`454cc592f81888a441acd4c08682e94f4680138164fa59fc2be4ace1b887d609`**, expires **2026-11-08 18:03:57 UTC**. Its upload digest and API metadata are recorded; it was not independently re-downloaded by its own producing job. Use the independently authenticated primary artifact as the evidence source.

## Actual coverage and settings

Ubuntu 22.04.5 Actions desktop, Xvfb 2560×1920 at requested 96 DPI, Openbox, real DBus/AT-SPI and GTK **3.24.33**. `gtk-xft-dpi=98304` read back in every configuration. GDK scale/font/theme readback used a separate same-environment native GTK probe window; actual host focus/roles/extents came through AT-SPI, and actual window geometry through X11.

| Configuration, for both OFF and ON | Readback | OFF initial → requested-small actual pixels | ON initial → requested-small actual pixels |
|---|---|---|---|
| normal | Adwaita, Sans 11, scale 1 | 1072×820 → 1072×600 | 1040×820 → 800×600 |
| scale2 | Adwaita, Sans 11, scale 2 | 2144×1640 → 2144×600 | 2080×1640 → 800×600 |
| dark | Adwaita-dark, Sans 16, scale 1 | 1376×820 → 1376×600 | 1040×820 → 800×600 |
| large | HighContrast, Sans 20, scale 1 | 1590×820 → 1590×600 | 1040×820 → 800×600 |

These values show real scale/font inputs, not just resized windows. OFF did not honor the requested 800-pixel width. Bounds do not establish text fit or absence of clipping. Theme-name readback does not prove that custom owner CSS follows the theme.

Real keys exercised import cancel and actual TXT import/open, next/previous page, directory/search/settings, records/bookmark save, text-note selection/save, Collections type changes (Shelves/Tags/Series), account dialog, metadata, shelf return, forward/reverse Tab and Escape. Compact ON also imported a real PDF and traversed the four parent menus with exact `menu` roles; the union of actual TXT and PDF leaf names covered all 22 menu items. Traversal/name-state coverage is not execution of every leaf action or repetition of the earlier 45 functional checks. Reused original AT-SPI and driver modules were not forked.

## Findings and reproducible evidence

All findings below bind to target `9fc407a5cce5a0bfe644a60bd8dc29f84dea6d0e`, harness/run/attempt above. Paths are inside primary artifact `12609036554`.

### F01 — Reading records initial focus is outside the modal (OFF and ON, all settings)

1. Import/open TXT with F1 and the real chooser.
2. Exercise directory then close it; press Ctrl+Shift+R.
3. Read the actual focused element before moving focus with Tab.

Expected: a visible, sensitive focused descendant of `dialog[Reading records]`, preferably stable Close while the list request runs.

Actual OFF: `application[exreader-linux]#0/frame[EXReader Linux]#0/filler[]#0/filler[]#0/push button[Import F1]#0`.

Actual ON: same main-frame prefix, `toggle button[More reader actions]#2`.

Both report `focused=true` but omit `enabled` and `sensitive`. They are not descendants of the modal. Evidence: `{OFF,ON}-{normal,scale2,dark,large}/records-dialog.{png,json}`, `keys.log`, and `result.json` check `records-dialog-focus`. The raw predicate was `bool(focused())`; **that pass is revoked in the final machine-readable adjudication**.

Source evidence: `examples/linux/reading_records_ui.inc:192–218` disables main content, queues the initial list request, then tries to focus the list; `records_controls():46` disables it while running. `examples/linux/reader.c:814–817` adds stable Close focus only in `compact_records_open`, whereas the Ctrl+Shift+R path at line 939 invokes `reading_records_open` directly. This supports the missing stable-focus initialization diagnosis; the exact event timing was not separately instrumented.

Minimal owner recommendation: establish initial focus on the stable Close response in the shared opener, covering both menu and shortcut routes and both configurations; preserve focus correctly when asynchronous list state changes. Harness follow-up: require `is_ancestor(dialog, focused)` plus showing/sensitive state, not just presence of any focused node.

### F02 — Default OFF Escape does not close Reading records after bookmark save (4/4)

1. Continue F01 via real Tab to Add bookmark and Return.
2. Enter `D03 bookmark` in Reading record text; press Alt+S.
3. Confirm the real accessible bookmark row contains `D03 bookmark`.
4. Press Escape once and wait 15 seconds for Reading records to disappear.

Actual: the row was saved, but the dialog remained; all OFF configurations recorded `records-completed=false` and a close timeout. ON closed successfully on this route, which does not cure its initial-focus issue. Evidence: `OFF-*/records-saved.{png,json}`, `records-failed.{png,json}`, `keys.log`, `application.log`, `result.json`. Subsequent recovery keys were retained; the failed first Escape was not rewritten as a pass.

Root cause remains unconfirmed. The insensitive main-focus state and nested editor focus restoration are candidates. Inspect `reading_records_ui.inc:144–158, 191–218`, response/close handling at `68–74`, and the actual event target after editor dismissal. Minimal recommendation: fix native focus/response routing after editor close and verify one Escape returns to the invoking control without a trap; do not bypass the owner lifecycle or simply add blind repeated Escapes to the test.

### F03 — Directory's initial focused scroll container is unnamed (8/8)

After Ctrl+Shift+T, focus is inside the correct dialog but on:
`application[exreader-linux]#0/dialog[Directory and page entries]#1/filler[]#0/scroll pane[]#1`.

Role is `scroll pane`; name is empty; focused/showing/sensitive are true. Evidence: every configuration's `directory-dialog.{png,json}` and `directory-dialog-focus.actual`. The presence-only focus check did not validate a meaningful accessible name. Minimal owner recommendation: give the focusable scroll container an appropriate accessible name and confirm traversal targets the intended native content. No Orca announcement was measured.

### H01 — 2× geometry/contrast attribution is indeterminate

At scale 2, AT-SPI extents are logical, while root PNG and X11 geometry are physical. Example ON: window X=241 and width=2080, but sampled search-region X=120 and width=400 after small-window resize. The harness did not calibrate/apply the coordinate transform before cropping/comparing bounds. Therefore 2× crop ratios (21 and 19.11698) and zero offscreen-candidate counts **do not describe the intended control reliably**. They are retained raw and excluded from scope grants. Future harness work must calibrate logical→physical mapping, including offsets, against the actual host before any geometry/contrast judgment.

At scale 1 the stored dominant-color pairs produce ratios 3.768729 (normal/dark) or 5.288906 (HighContrast), using relative sRGB luminance `(Lmax+0.05)/(Lmin+0.05)`. These are measured pixel pairs, not verified text/background pairs; they may be selection/focus colors. No WCAG pass or failure follows from them.

## Retained failures and stopping condition

- Round 1: `40215023319` / harness `834e9c57be3b9dc4c9da26be0175747250e64d19`. Both builds passed; missing `xrdb` aborted the environment probe before host audit. Artifact `12607068775`, 16,884 bytes, SHA-256 `fd8cadb416022865ea96f4cd9f5766183a7c9366ed0acb5fb40311e679ff38b1`, expiry `2026-11-08T17:11:48Z`.
- Round 2: `40215548145` / harness `12bd1f1e0caf939b847804c62369963a46df9563`. Eight captures but initial TXT chooser did not complete; downstream reader failures were not product diagnoses. Missing explicit chooser activation/select-all was repaired using the original keyboard route, with observed-state-only second Return. Verifier separately hit HTTP 401 from forwarding API Authorization to signed artifact storage. Artifact `12607494079`, 8,973,262 bytes, SHA-256 `2b05d86f1c05527ad9fe1c8fcac6c9eada70c51e6d5f833f6bb475384cace6c4`, expiry `2026-11-08T17:44:47Z`.
- Both old original ZIPs were independently rehashed/authenticated in final verifier job `121247583314`. Their success fragments were not combined with the final run to grant a scope.
- Round 3: exact findings above; the red completeness gate and newly identified assertion/coordinate limitations remain. Retry cap reached. Root owns any production repair and subsequent authorized acceptance run.

## Not verified

Orca or human screen-reader speech, braille, physical desktop/Wayland/multi-monitor DPI, focus-ring visibility, visual clipping/overlap, whole-UI text/non-text contrast, full semantic announcements/live regions, all 22 menu-action executions at every scale, and full prior OFF functional regressions. Captured role/state trees and screenshots do not establish these scopes. No WebView, server dependency, production changes, SDK changes, schema/wire/anchor changes, release, PR or default-branch push occurred.
