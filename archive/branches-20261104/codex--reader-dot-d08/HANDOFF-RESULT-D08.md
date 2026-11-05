# D08 final — authenticated Windows automation, substantive failures retained

**Overall acceptance: false.** Two complete CI iterations; final native and authentication jobs succeeded. This is an evidence delivery, not a high-DPI, contrast or screen-reader acceptance grant.

## Exact source and program identities

- Branch: `NoGod3524/EXReader:codex/reader-dot-d08`.
- Implementation base: `0889f7d1e9a537c6c1b05456547e016b26e1cd85`.
- Separately checked-out target: `9321de84eb9c8d3d57cafbeaa8b0a28fe2a26a08`.
- Approved SDK: `edddc463c06ed5731195cdb8f06b2df6dff7699e`; Actions source comparison included src/include/cmake/CMakeLists/CMakePresets/bindings/fixtures.
- Final tested harness: `d885475a6eb93677055b27d168a7f50e601bf6b4`, tree `eb6c432b4ddda3fc5d030ef87909ab8475ab155b`.
- Final documentation seal: containing docs-only `[skip ci]` commit; its full SHA is reported in the external D08-status.md and handoff message, avoiding a self-referential commit hash.
- Actual EXReaderProduct.exe SHA256: `77eb216cae2f48556811c507a9505de5bb6cee57b40c52714ce13c82bfa105b5`.

Fresh SDK/product/modules were built and installed, then actual compact host compiled. Configuration: compact/search/navigation/records/import-organize/preferences ON; raw3 OFF; preference-review OFF. Actual EXReaderProduct compile command contains the expected feature macros, `/O2 /Ob2 /DNDEBUG -std:c11 -MT /utf-8`, and no review macros. All commands/caches/Ninja files/link map retained, not inferred from a static-library filename.49 installed `.lib` identities retained. Each actual process's loaded program/DLL paths, bytes and hashes are in its configuration record:38 modules first launch,37 in each subsequent launch; no inventory errors. These are initial-process inventories, not every later delay-loaded module or module-behavior certification.

## Final CI and original ZIP authentication

[Run40226179285](https://github.com/NoGod3524/EXReader/actions/runs/40226179285), attempt1. Native job121267922718 and strict job121270374447 both success.

| Original ZIP | ID | bytes | SHA256 | expiry UTC | authentication |
|---|---:|---:|---|---|---|
| raw |12610794664|24944030|c3e48e80c3678aa1a68fe04bdc043d32d8ccb37783ac584fc3158386da3ead5f|2026-11-24T19:38:27Z|Original ZIP downloaded inside same-run strict Actions; unique name, ID, source/run/attempt, size/digest/expiry, upstream job, every indexed file/program/screenshot checked|
| summary |12611760570|249824|b55b28cc9391db42a3c666e17b62eb1752ddf9fd5e733f92e1e3d1640336e3c3|2026-11-24T19:38:50Z|Upload digest and GitHub metadata; NOT recursively ZIP-downloaded|

Raw contains1563 files, including1152 BMP screenshots, per-step UIA/native geometry/focus, full per-control pixel coordinates/counts, build identity, keyboard trace, actual executable/font and the complete report. Credential-shaped/ephemeral-token scan covered1564 files/log inputs and passed. Local work was source/docs/Git only; no local build, syntax check, fixture, screenshot, test, artifact download/unpack or artifact parsing. Completed Actions logs were read through connector.

## Complete named result set

Every configuration has mandatory `dpi`, `layout`, `contrast`, `import-open`, `search`, `directory`, `records`, `settings`, `return-focus`, plus retained independent `shelf_search`. Four negative controls reject wrong DPI, main-window-only modal focus, missing screenshot and incomplete configuration. These are harness refusal tests, not product checks.

| Requested configuration | DPI | layout | contrast | import/open + four reading dialogs + return | shelf search |
|---|---|---|---|---|---|
|100-normal-default|pass|fail|pending|six pass|fail|
|100-normal-small|pass|pass|pending|six pass|fail|
|100-high-default|pass|fail|pending|six pass|fail|
|100-high-small|pass|pass|pending|six pass|fail|
|150-normal-default|fail|fail|pending|six pass|fail|
|150-normal-small|fail|pass|pending|six pass|fail|
|150-high-default|fail|fail|pending|six pass|fail|
|150-high-small|fail|pass|pending|six pass|fail|
|200-normal-default|fail|fail|pending|six pass|fail|
|200-normal-small|fail|pass|pending|six pass|fail|
|200-high-default|fail|fail|pending|six pass|fail|
|200-high-small|fail|pass|pending|six pass|fail|

These are **requested**, not achieved DPI configurations. All12 observations had window/system96DPI, monitor100%, awareness0. Eight higher-scale requests therefore fail required coverage; their subsequent observations are repeated actual100% observations, not150/200 passes. Only four distinct requested scale/theme/window combinations achieved the requested scale. Native high-contrast readback really changed: normal flags126, high flags127, setter true.

### Confirmed product failures

1. All12 shelf-search cases: after read→Alt+Left shelf→Ctrl+F→Tab→Shift+Tab→Escape, native focus returns to hidden reading page (`descendant=true`, `enabled=true`, **`visible=false`**), although UIA incorrectly says `offscreen=false`. Example final100-normal-default returned HWND66120, owner327866. The exact target `windows_search.inc:winsearch_close` unconditionally calls `SetFocus(g.page)`. Do not replace native visibility with UIA or nonzero focus.
2. Six default-window observations: actual `[0,0,1044,788]` exceeds work area `[0,0,1024,728]`. Requested700×480 fits. Native exposed bounds are measured; that does not prove every glyph or control state is unclipped.

### Narrow successful observations

Actual native SendInput imported/opened temporary TXT; reading-state search, directory, records and settings entries each had three visible/enabled native modal-descendant focus samples and returned to an operable main-window control; Alt+Left initially returned to usable shelf focus. These observations cover entry/tab/reverse-tab/dismissal, not successful search-result selection, saved records, applied preferences, or complete functional regressions. No handlers, WM_COMMAND or BM_CLICK were used for tested transitions. Native-input automation is not a physical-keyboard claim.

### Painted-pixel findings and remaining uncertainty

Each of12 attempts captured75 text-bearing native controls over initial shelf, reading dialogs, populated shelf and shelf-search:900 control samples total.49 per attempt had both distinct candidate foreground/background colors in actual control-client pixels (588 measured pairs);26 per attempt remained null/unresolved (312). Normal measured-pair ratios were18.427342383975944 or21; high contrast ratios21. These are GDI device-RGB pairs under an sRGB assumption, not calibrated or semantically proven text-glyph contrast. Full raw pixel coordinates and counts are retained. No low-contrast enabled sampled pair was observed; **all12 full-contrast scopes remain pending** because26/75 unresolved samples, color-space/foreground semantic uncertainty and untested glyph/focus/selection paint cannot be converted into passes. Controls' own client screenshots avoid screen/client offset guessing.

## History retained

CI1 harness `5c9f4dd84b7c7faf8855e83860c53fa719ced635`, run40225000270/1, native121264384514/strict121266188998 success. Actual EXE `544ede515af646024c602609343a6d868d9e17f070bfac173430553daf2e37fc`. Raw12611256853,24207143bytes,SHA256 `f4d12a8edad519fcb2e91902a9fe0685febd2c2a41c40af51d4e33014cb0a86a`, expiry2026-11-24T19:20:49Z. Summary12611187057,69128bytes,SHA256 `f59b740c5d357913a29d4fc1d513aad6809398376ec3f3b5094adfcde70ff1b5`, expiry2026-11-24T19:21:14Z (metadata-only). First-run disabled-button foreground count was0; its palette ratios were never accepted as painted contrast. CI2 repaired measurement, rather than relabeling that evidence. Both runs retain the same actual product/DPI failures.

D02 read-only source `c51bdb533d2f86e710c5c14a9faab462334b2a81`, tested `e8b5b1bd200202c06a7a22e5a4ed1f801eb47706`, run40215441500/1, target `f355525b74ae261db536c56200e46643919ef323`. Original signed-storage401 and cp1252 failures, work-area overflow, shelf-focus defect, unresolved OFF-account Escape timeout, unverified high-DPI/contrast/reader scopes remain. D08 does not rerun OFF account or rewrite old acceptance. See README/ITERATION-1 for preserved identities.

## Completion boundary and root integration

- Evidence authentication/build identity: verified in Actions for exact final harness/target/program.
- Overall product, whole keyboard journey (shelf-search failure), DPI150/200 and full contrast: **not accepted**.
- Narrator, actual screen-reader speech, physical display/keyboard, glyph clipping, localized focus-ring visibility, full search/directory/records/settings functionality, and later-loaded DLLs: pending/unverified.
- No module functional-regression grant from building installed libraries.
- No owner/SDK/old tests/default branch/PR/tag/release edits. All changes confined to D08-owned paths.

Root should consume authenticated raw `report.json`, `build-identity.json`, `negative-controls.json`, `observations/*` and summary `validation.json`; preserve requested-vs-actual scales and every failure/null observation. Source fixes belong to Windows owner; actual150/200 requires an Actions runner/session whose monitor readback genuinely changes. A third identical hosted run would not close those known environment/product gaps, so no blind third iteration was used.

Publication briefly paused after CI1: first CI2 blob and one evidence-backed identical retry were denied by auto-review. No workaround occurred. Fresh explicit owner approval Sentinel_3fc8195067848191984aeea41256b99b19:26:24 answered root's exact D08/D09/D10/D14 GitHub-write/remaining-CI/docs request Sentinel_38496d4b9f6881918e3a697844de0d02. Normal reviewed publication then succeeded with lease and force=false. No permission blocker remains.
