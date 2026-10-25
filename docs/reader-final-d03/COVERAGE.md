# D03 coverage delta and evidence contract

Target `9fc407a5cce5a0bfe644a60bd8dc29f84dea6d0e`, SDK `edddc463c06ed5731195cdb8f06b2df6dff7699e`; harness starts at `0889f7d1e9a537c6c1b05456547e016b26e1cd85`.

Reuse the existing `reader_a11y_gtk` AT-SPI client and keyboard driver, not a fork. Read `tests/linux_host` and the original compact workflow/checker. Its 45 ON checks, 22 leaves, OFF regression and refusal suite are historical functional results, not new scaling/accessibility acceptance. New build enables identical optional integrations but defaults compact OFF in its OFF build. It installs the pinned target SDK and modules, without moving production files into the harness branch.

New matrix: OFF and ON, each Adwaita at GDK_SCALE=1/font 11, Adwaita scale 2/font 11, Adwaita-dark scale 1/font 16 and HighContrast scale 1/font 20. Each independent process/profile records GTK settings, Xft DPI, GDK scale, desktop and window extents. Keyboard routes use X11 keys only: import cancellation/import, reading page turns, More hierarchy traversal, dialog entry/exit, text/note actions, reading records, forward/reverse Tab, shelf return. Snapshots preserve paths/roles/states and raw PNGs. No owner callbacks or AT-SPI actions count as keys.

Bounding boxes outside the actual window are measured candidates, not automatic text-clipping diagnoses. Pixel contrast measures only identified sampled regions and is explicitly not whole-UI WCAG acceptance. Theme setting readback does not prove every custom widget obeys it. Visible focus, complex overlapping text and speech need human review; Orca/human reader acceptance remains false. Any incomplete phase retains its exception and unevaluated scope; audit completion never means product acceptance.
