# D09 — evidence authenticated; actual modal-focus defect retained

**Audit completed; product acceptance withheld.** Four configurations each completed all 20 named checks: **19 passed, `records-dialog-focus` failed**. The final verifier remains red deliberately. Original ZIP/program identity and 67 negative controls passed. Two complete CI iterations were used; another identical run cannot repair the product defect.

## Exact identities

| Item | Identity |
|---|---|
| Branch | `codex/reader-dot-d09` |
| Harness base | `0889f7d1e9a537c6c1b05456547e016b26e1cd85` |
| Final tested harness | `2ccceba85cb12a9cab5c00e5cb62a7c5a4a4ece5` |
| Actual target checkout | `803098e9df1a365a9b8e206805c2d179aca8501f` |
| Approved SDK source | `edddc463c06ed5731195cdb8f06b2df6dff7699e` |
| SDK package / ABI / core header | 3.41.0 / 1 / core 3.40.0 |
| Actual program SHA-256 | `4bb3597d43f6d818a5f8a8b78a1f0fb330e31d839065a4dff298febf63559742` |
| Program bytes / original mode | 10,279,568 / 0755, regular non-symlink |
| Font SHA-256 | `2c76254f6fc379fddfce0a7e84fb5385bb135d3e399294f6eeb6680d0365b74b` |

Program is explicit **RAW3 ON / COMPACT ON**, with original product, account, records, navigation, search, preferences, batch/drop and page-background integrations. Actual compile commands, cache and package manifest were checked; no review macros or production edits. This is not a default OFF rerun. Old OFF results remain separate. Original target probe 40218764233 does not make full original chain 40219591315 green.

SDK archive hashes and exact CMake-cache hashes are in [SDK-IDENTITIES.json](SDK-IDENTITIES.json), transcribed from producer identity output; those archives were not individually archived as binaries. Source guard compared approved SDK trees. `libexr_base.a`: `3537fc62d27671b40f004786323f24c35f2c9d9d36e6ae701c254927f6aa1354`; `libexr_library.a`: `8e0a35b5978046372b866c7af7e66e079cfa0c01c835b4c7acab7366970781e6`.

## Final run and original bytes

[Run 40226140199, attempt 1](https://github.com/NoGod3524/EXReader/actions/runs/40226140199):

- Producer `121267803662`, **GTK native scale audit**: success, including source/syntax guard, actual build, four sessions and upload.
- Consumer `121269533233`, **Authenticate ZIP and same-source coverage**: failure only at final acceptance assertion, after all identity, raw evidence and negative checks.
- Original primary artifact **12611531256**, `reader-dot-d09-40226140199-1`: **16,389,760 bytes**, SHA-256 **`a7c6bda5d397ba36ac51d2bab4ea8559470b0f2a8465dd1349377a8410cc7bce`**, expiry **2026-11-08T19:34:58Z**. Original ZIP independently downloaded, hashed and size/expiry/source/run/attempt/unique-name checked **inside Actions**, stripping API authorization before signed-storage redirect.
- Summary artifact **12611468052**, `reader-dot-d09-verification-40226140199-1`: **40,473 bytes**, upload/API digest **`0d57225e5b9079e9aecadd7a58f25cbffedc37601dacbee6d5f1597ffe5ebf98`**, expiry **2026-11-08T19:35:14Z**. This summary's ZIP was not independently re-downloaded; rely on the authenticated primary for evidence.

Primary `programs/ON/{exreader-linux,program-attributes.json,build.json,CMakeCache.txt,compile_commands.json,runtime-dependencies.txt}` authenticates the binary and original pre-ZIP filesystem mode. ZIP extraction permissions are not asserted or repaired. The font is bound by manifest/session hash but not included as raw font bytes; this evidence bundle is not represented as a complete redistributable payload.

## Four real configurations and calibrated geometry

GTK 3.24.33, Ubuntu 22.04 Actions, Xvfb root screenshots **2560×1920 physical pixels**, 96 DPI, independent D-Bus accessibility probe and Openbox readiness. `gtk-xft-dpi=98304` in all cases.

| Configuration | Native probe readback | Initial client physical size | WM frame physical bounds | AT-SPI logical frame |
|---|---|---|---|---|
| normal | Adwaita, Sans 11, scale 1 | 1040×820 | (759,537), 1042×845 | (759,537), 1042×845 |
| scale2 | Adwaita, Sans 11, scale 2 | 2080×1640 | (239,127), 2082×1665 | (119,63), 1042×833 |
| dark | Adwaita-dark, Sans 11, scale 1 | 1040×820 | (759,537), 1042×845 | (759,537), 1042×845 |
| large | HighContrast, Sans 20, scale 1 | 1040×820 | (759,537), 1042×845 | (759,537), 1042×845 |

Read-only `XQueryTree` selects the actual WM frame; `XTranslateCoordinates` provides its root-space origin. A measured move of (40,40) physical pixels produces (40,40) logical at 1× and (20,20) at 2×, then returns to the original position. Dimension/origin residual tolerance is at most 4 physical pixels, accounting for integer rounding/decorations. All four initial calibrations pass; raw samples and independent client/frame/root identities are retained. Per-control physical coordinates are recorded only when calibration passes. The driver also recalibrates at the requested small size before any pixel crop.

**Contrast is not accepted.** Recorded crops use calibrated coordinates, but two most frequent colors are not proven text/background semantics. Original small-window pixel pairs, ratios, control regions and raw PNGs remain in each `ON-*/result.json` and `small-window.png`; no WCAG or clipping/overlap verdict follows. GTK font/theme readback is from a same-environment probe; actual host geometry and focus come from its own X11/AT-SPI objects, not inferred from the probe.

## Actual defect: Reading records shortcut focus remains outside its modal

Reproduction: real F1 chooser import/open of temporary TXT, keyboard page turns and directory open/close, then **Ctrl+Shift+R**. Read focus before moving it with Tab.

Expected: active modal `dialog[Reading records]` has a focused **enabled, sensitive, visible, showing descendant**. Actual in **all four configurations**:

```text
application[exreader-linux]#0/frame[EXReader Linux]#0/filler[]#0/filler[]#0/toggle button[More reader actions]#2
```

Actual main button states: visible/showing/focused/focusable true; **enabled and sensitive absent; native modal ancestry false**. The dialog itself is enabled/visible/showing/sensitive/**active/modal**. Main-window focus is not accepted as dialog focus. Real Tab then reaches Add bookmark, save succeeds, one Escape closes the records dialog and restores operable main focus; this later success does not cure the initial failure.

Evidence in authenticated primary: `ON-{normal,scale2,dark,large}/records-{before-open,dialog,before-close,after-close}.{json,png}`, `records-saved.{json,png}`, `keys.log`, `application.log`, and complete `result.json` named-check values. Every required modal has before/open/before-close/after-close trees and original root screenshots.

Source corroboration, not a substitute for the runtime finding: target `examples/linux/reader.c:939` calls shared `reading_records_open` directly; stable Close focus exists only in `compact_records_open` at 814–817. Shared `reading_records_ui.inc:191–218` disables main content, queues the list (which may be insensitive), then focuses that list. Root should establish stable initial modal focus in the shared opener for both keyboard and menu routes, and independently verify async transitions. D09 does not edit the owner to pass its audit.

## Complete named result set

The same 20 names were evaluated independently in all four configurations. **Only the bold item fails**:

1. bridge
2. scale-readback
3. compact-mode
4. coordinate-calibration
5. tab-forward-reverse
6. tab-focus-names
7. import-cancel
8. keyboard-import-open
9. next-page
10. more-text-leaves
11. search-dialog-focus
12. search-escape
13. directory-dialog-focus
14. directory-escape
15. **records-dialog-focus**
16. record-save
17. records-escape
18. settings-dialog-focus
19. settings-escape
20. return-shelf-search

This covers shelf, reading, search, directory, records, settings and real forward/reverse Tab. Menu leaf names are not claims that every menu action executed. Search/directory/settings were opened/closed by keyboard; no complete search-result, every-directory-item or settings-save suite is claimed. [validation.json](validation.json) records exact per-configuration verdicts and actual failed focus/calibration data; complete raw actual/expected values remain in original per-configuration reports.

Fifteen independent semantic controls reject main-frame focus, each missing enabled/sensitive/visible/showing/focused state, unconverted 2× coordinates, unmeasured coordinate claims, each individually missing configuration, missing program, missing screenshots and a false required check. A labeled synthetic positive tests the contract only; it never grants product scope. Thirteen evidence mutations per configuration (52 total) reject wrong source/target/SDK/run/attempt/mode/program, empty evidence/snapshots/checks, duplicate snapshots/checks and tampered bytes. **67/67 refusals pass.**

## Retained failures and narrow acceptance

- D03 read-only source `c484ce52540851a4f35056bc8ca41afcfcab889e`: original run **40218375669**, harness **81a67f582ddfe8906b64e6eef4e7969127415ba8**, ZIP **12609036554**, **35,146,853 bytes**, SHA-256 **`a60100c94b4033f236536efb2274cfd4fd38727e51e9fc63e31bd970187d4496`**, expiry **2026-11-08T18:03:36Z** reauthenticated in final Actions. All eight old records-focus raw passes are explicitly revoked after checking actual main-frame paths. Earlier **40215023319** (missing xrdb) and **40215548145** (chooser plus redirect failure), default-OFF records Escape failures, unnamed directory focus, and old 2× indeterminate crops remain historical failures/gaps, not replaced by D09.
- D09 round 1 **40224943448**, harness **b28ce904ca65e7d5e7a37a269522e8e039889901**, jobs **121264215576** success / **121265426657** failure. Every configuration 18/20: records focus failed and coordinate calibration rejected the incorrect xdotool-client-versus-AT-SPI-frame comparison. ZIP **12610553310**, **16,196,056 bytes**, SHA-256 **`105e6fab0ee44dcc225669ec9f0a3a7de28b406e7ce0c90c5dfca3d973ee5429`**, expiry **2026-11-08T19:17:42Z**, reauthenticated with all failures in round 2. No round-1 coordinate/contrast acceptance.
- Round 2 fixes only owned measurement: raw xdotool data remain, Xlib WM-frame calibration now passes. It still fails the actual product modal-focus assertion. **No third run spent; no production fix or assertion weakening.**

Granted: source/run/program-bound audit evidence and listed narrow observed successes. Not granted: whole product, modal focus, full keyboard accessibility, Orca/human speech/braille, physical devices/Wayland/multi-monitor, performance, visual clipping/overlap, focus-ring visibility or semantic text/non-text contrast. No PR, merge, default-branch push, tag, release, Codex task, child agent, real user profile or credential access.

The final documentation-only `[skip ci]` seal changes only D09 documents. Tested code SHA above remains distinct from the seal SHA returned to root.
