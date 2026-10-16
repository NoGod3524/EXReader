# Third-party notices

EXReader's own code is MIT licensed. Full bundled dependency notices are in `licenses/` in the portable release and `public/licenses/` in source distributions. `Cargo.lock` and `package-lock.json` pin dependency versions.

| Component | Source | License | Role |
| --- | --- | --- | --- |
| Foliate JS | https://github.com/johnfactotum/foliate-js/tree/78914aef4466eb960965702401634c2cb348e9b1 | MIT, John Factotum | EPUB, MOBI/KF8, FB2, pagination and CFI |
| Foliate's vendored zip.js | https://github.com/gildas-lormeau/zip.js | BSD-3-Clause, Gildas Lormeau | ZIP reader |
| fflate (including Foliate's vendored decompressor) | https://github.com/101arrowz/fflate | MIT, Arjun Barrett | Decompression and exports |
| PDF.js and text-layer stylesheet | https://github.com/mozilla/pdf.js | Apache-2.0, Mozilla Foundation | PDF rendering and selection |
| PDF CMaps and standard fonts | `public/pdf-assets/*/LICENSE*` | BSD and font-specific licenses in those directories | CJK and standard font rendering |
| Mammoth | https://github.com/mwilliamson/mammoth.js | BSD-2-Clause, Michael Williamson | DOCX conversion to sanitized HTML |
| DOMPurify | https://github.com/cure53/DOMPurify | Apache-2.0 OR MPL-2.0; distributed under Apache-2.0 here | Book HTML sanitization |
| rtf.js | https://github.com/tbluemel/rtf.js | MIT, Thomas Bluemel and contributors | RTF rendering |
| js-codepage | https://github.com/SheetJS/js-codepage | Apache-2.0 | RTF text encodings |
| Tauri / Wry / Tao | https://github.com/tauri-apps | MIT OR Apache-2.0 | Native shell and system WebView |
| Tauri dialog / filesystem plugins | https://github.com/tauri-apps/plugins-workspace | MIT OR Apache-2.0 | Native save dialogs and writing user-selected files |
| Linux AppImage runtime libraries | Upstream links in `usr/share/doc/*/copyright` inside the extracted AppImage | Component-specific, including LGPL, BSD and MIT | WebKitGTK, JavaScriptCore, GTK, GLib and supporting libraries |

The PDF text-layer stylesheet is extracted without changing its rules. Foliate's local patches route PDF files to EXReader's own adapter and guard paginator layout / deferred font callbacks while an iframe loads or after it is destroyed. Reproduce using `python scripts/vendor.py`. The upstream revision and MIT license remain in `vendor/foliate/`.

Thorium Reader (BSD-3-Clause), SumatraPDF ((A)GPLv3 and BSD components), and calibre (GPLv3) were studied as references. Their application source code and binaries are not bundled. The optional desktop conversion command invokes a separately obtained calibre `ebook-convert` executable. Any redistribution of calibre must comply with its own license.
