# Reader 0.2.0 integration validation

2026-10-15. This branch restores the full reader UI on the GPLv3 framework API. Original 0.1.1 installers remain unchanged.

- Production build and offline reading: passed. The production check imports the sample, caches the application and engines, switches offline, reloads, and opens the book. `docs/screenshots/library.png` shows the preserved UI with version 0.2.0.
- UI regression matrix: all 31 applicable cases passed across the full run and targeted reruns. Covers import, reflow formats, PDF highlights/navigation, notes, metadata/cover editing, backup/restore, conversions, audio position and responsive layout. Two Windows WebKit audio cases are skipped as in 0.1.1.
- Targeted reruns: Chromium audio and RTF, mobile RTF passed; mobile audio skipped. Fixed the audio wrapper width after separating framework media from application controls.
- Framework matrix on the app branch: 45 passed, 2 skipped; the remaining mobile bookshelf case passed on rerun after test artifacts were separated from the simultaneously running UI suite. Independent framework-branch full run: 46 passed, 2 skipped.
- `cargo check --manifest-path src-tauri/Cargo.toml --offline`: passed on Windows. Native conversion now delegates to `exreader-calibre`; the prior lockfile versions are retained with only the new path dependency added.

These checks validate source integration. No new 0.2.0 native installers have been published or checked on the other five target platforms. Prior native-package validation is recorded separately in VALIDATION.md.
