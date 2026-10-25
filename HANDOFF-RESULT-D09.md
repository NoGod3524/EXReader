# D09 handoff — audit finished, actual GTK modal-focus defect retained

Full evidence: [docs/reader-dot-wave2/d09/REPORT.md](docs/reader-dot-wave2/d09/REPORT.md) and [validation.json](docs/reader-dot-wave2/d09/validation.json).

- Branch `codex/reader-dot-d09`; base `0889f7d1e9a537c6c1b05456547e016b26e1cd85`.
- Tested harness `2ccceba85cb12a9cab5c00e5cb62a7c5a4a4ece5`; actual target `803098e9df1a365a9b8e206805c2d179aca8501f`; SDK `edddc463c06ed5731195cdb8f06b2df6dff7699e`.
- Final run `40226140199`, attempt 1; producer `121267803662` success; verifier `121269533233` failure only final acceptance assertion.
- Primary ZIP `12611531256`, 16,389,760 bytes, SHA-256 `a7c6bda5d397ba36ac51d2bab4ea8559470b0f2a8465dd1349377a8410cc7bce`, expiry `2026-11-08T19:34:58Z`; original-byte auth passed in Actions.
- Program SHA-256 `4bb3597d43f6d818a5f8a8b78a1f0fb330e31d839065a4dff298febf63559742`, 10,279,568 bytes, original pre-ZIP mode 0755/non-symlink. RAW3/COMPACT ON, no review macros.
- All four normal/2×/dark/large sessions complete, **19/20 each**. Only `records-dialog-focus` fails: Ctrl+Shift+R leaves focus on insensitive main-frame More reader actions, outside active Reading records modal. Search/directory/settings actual focus and close pass. New Xlib WM-frame scale calibration passes all four; original PNGs/control coordinates preserved.
- All 67 negative controls pass. D03 revoked eight false focus passes and D09 failed round 1 are independently authenticated and retained. Two complete CI rounds, no third blind retry.
- `accepted=false`, modal/keyboard/contrast/screen-reader/physical/performance acceptance false. Scope granted only authenticated audit and named observed checks; no whole-product grant.
- Root integration point: shared `reading_records_open` versus menu-only `compact_records_open`; actual key route and raw files detailed in report. Product fix belongs to root, not this package.
- Documentation seal is this document's containing `[skip ci]` commit; exact final seal SHA returned via handoff message after remote verification. No code change after tested SHA.
