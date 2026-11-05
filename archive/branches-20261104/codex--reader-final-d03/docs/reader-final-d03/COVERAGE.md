# D03 coverage delta and evidence contract

Target `9fc407a5cce5a0bfe644a60bd8dc29f84dea6d0e`, SDK `edddc463c06ed5731195cdb8f06b2df6dff7699e`; harness starts at `0889f7d1e9a537c6c1b05456547e016b26e1cd85`.

Reuse the existing `reader_a11y_gtk` AT-SPI client and keyboard driver, not a fork. Read `tests/linux_host` and the original compact workflow/checker. Its 45 ON checks, 22 leaves, OFF regression and refusal suite are historical functional results, not new scaling/accessibility acceptance. New build enables identical optional integrations but defaults compact OFF in its OFF build. It installs the pinned target SDK and modules, without moving production files into the harness branch.

New matrix: OFF and ON, each Adwaita at GDK_SCALE=1/font 11, Adwaita scale 2/font 11, Adwaita-dark scale 1/font 16 and HighContrast scale 1/font 20. Each independent process/profile records GTK settings, Xft DPI, GDK scale, desktop and window extents. Keyboard routes use X11 keys only: import cancellation/import, reading page turns, More hierarchy traversal, dialog entry/exit, text/note actions, reading records, forward/reverse Tab, shelf return. Snapshots preserve paths/roles/states and raw PNGs. No owner callbacks or AT-SPI actions count as keys.

Bounding boxes outside the actual window are measured candidates, not automatic text-clipping diagnoses. Pixel contrast measures only identified sampled regions and is explicitly not whole-UI WCAG acceptance. Theme setting readback does not prove every custom widget obeys it. Visible focus, complex overlapping text and speech need human review; Orca/human reader acceptance remains false. Any incomplete phase retains its exception and unevaluated scope; audit completion never means product acceptance.

## Retained first failure

Run `40215023319`, attempt 1, harness `834e9c57be3b9dc4c9da26be0175747250e64d19`: guard, syntax and both pinned real native builds passed; runtime environment probe raised `FileNotFoundError: xrdb` before host launch. This is a harness dependency failure, not a host accessibility verdict. Round 2 adds Ubuntu `x11-xserver-utils`; no production changes or relaxed assertions.

The target dynamically replaces Larger/Smaller text labels with Zoom in/out for fixed-layout books. The 22-leaf union therefore needs both text and actual PDF entry, not an assertion that all 22 coexist on TXT. The revised audit imports a generated PDF through the real chooser before checking that complete union. Shelves, Tags and Series are selected through the real Collection type combo. Actual product binary/packager manifests and CMake defaults are retained independently of the report, and thirteen negative report/byte mutations per configuration test refusal behavior.

GDK scale, GTK font and Xft DPI settings come from a same-environment native GTK probe; host screen extents and focus are actual AT-SPI observations. This is not an instrumented in-process host DPI query. Keyboard route success is separated from keyboard acceptance, which remains false pending visual focus review. Bounds outside the screenshot are explicit candidates, not a claim of confirmed text clipping.

## Retained second failure

Run `40215548145`, attempt 1, harness `12bd1f1e0caf939b847804c62369963a46df9563` completed eight sessions and retained PNG/tree/keys. Environment readback matched all four requested settings. Initial TXT import did not complete in any configuration; downstream reading failures therefore do not establish product defects. The original a11y chooser routine explicitly activates the mapped chooser, clears its prefilled location, and conditionally sends a second Return only while the real chooser remains visible. The final harness restores that route and additionally requires matching actual selected-path digest/accept state, retaining intermediate evidence. It marks reader phases blocked if import is unmet. Round 2's separate verifier failed HTTP 401 on signed artifact redirect; the final verifier uses the existing GTK aggregate's no-Authorization-on-redirect pattern, authenticating both old ZIPs rather than dropping their failures.
