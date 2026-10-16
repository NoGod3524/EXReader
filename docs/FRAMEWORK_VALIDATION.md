# Framework 0.2.0 validation

2026-10-15. Tests run on Windows with Chromium (Edge), WebKit and mobile WebKit.

- `npm run test:node`: 1 passed. Public entry imports without DOM, IndexedDB initialization, or UI side effects.
- `npm run build`: passed. ESM output includes license notices, configurable PDF assets and rendering CSS.
- `npm test`: 46 passed, 2 skipped. Covers library isolation, duplicates, metadata/progress concurrency, annotations, deletion, ZIP restore, malicious HTML, EPUB/FB2/FBZ/FB2.ZIP/TXT/RTF/MOBI/DOCX/HTML parsing, EPUB/PDF rendering, PDF cleanup/text export, CBZ page parsing, text export round trips, media control and built ESM entry.
- The 2 skips are PCM audio decoding on Windows WebKit, including its mobile emulation; Chromium audio passed.
- `cargo test --manifest-path integrations/calibre/Cargo.toml --locked`: 1 passed. Verifies unsafe conversion formats and empty input are rejected before launching calibre. Full external calibre conversion still requires its installation.

This is browser/WebView API validation, not new native installation-package validation. The original 0.1.1 native-package records remain in VALIDATION.md. Complex publication compatibility, Apple real-device media decoding, large libraries and streaming backups remain outside this check.

Follow-up distribution check: 6 PDF lifecycle / built-renderer cases passed across Chromium, WebKit and mobile WebKit. PDF workers are shipped as a separate same-origin asset, and the built ESM renderer is exercised under a restrictive CSP without allowing data scripts.
