# J01 Android license material findings and candidate

Scope: development-package materials only; not a legal opinion, release, signing or production-packaging change. Formal ledger 95/108 is unchanged.

## Inputs (verified in Actions before use)
- F12 artifact 13022451126 (run 41149079819/1, commit c03b1d9a3b30b745a903eeab9be2871f18360e33): size 138556827, SHA-256 941fa87a...3fc34 matched.
- Original Android outer artifact 12812325830 (run 40678657371/1, source 8f8acf32): SHA-256 e120fb8a...760e; inner ZIP 4533e63c...0a6a0e53; APK b6adf2d4...f9519.
- Re-deriving the Android matrix with the F12 auditor logic reproduced the F12 states exactly (`rederive-consistency.json`: true).

## Findings (original package)
13 rows were present_verified (3) or not_applicable (10, per recipe: Android disables WEBP/TIFF/AVIF/PDF_CRYPTO). 15 registered obligations were **missing_required** — material missing from the delivery ZIP (neither at the package level nor inside the APK assets), not an auditor misread: freetype FTL.TXT and LICENSE.TXT, expat COPYING (two), miniz, stb, openjpeg, lcms, sqlite public-domain text, minimp3, unicode, default CMYK profile text, adobe-glyph-list, pdfjs data, wp7 Noto test-font notice. Android's recipe enables PDF/library/ICC/JPX and AUDIO/MP3, so openjpeg, lcms, sqlite and minimp3 are applicable. No row was a content mismatch.

## Candidate
Run 41151842961/1 (commit 5bcff0b0): all 15 texts added to the inner package under `licenses/...` (bytes equal the registered hash: repository originals from source 8f8acf32, upstream texts from the pinned, hash-checked codeload archives). Inner manifest.json/SHA256SUMS and outer manifest were resealed; a `candidate` block lists every added file. APK bytes and all other entries are byte-identical (checked); no duplicate ZIP entries.
- Candidate outer: `exreader-android-j01-candidate.zip`, 19721199 bytes, SHA-256 `944ead0934115f7a92a03e500417b1a0398cf05f29675a7096970f1a0a267f55`; inner 19723399 bytes `5be6e7789266eb8c7929e90013c979d90c7f498019eb08bb6cc48439b6eb6922`.
- Artifacts: candidate 13023043154 (sha256:372ee0ae...e6e1), evidence 13023028193.
- After: present_verified 17, not_applicable 10, **unresolved 1**: minimp3 `licenses/minimp3/LICENSE`. The registry pins only the upstream archive for this file (no per-file hash), so it was added from the pinned archive member but the auditor cannot call it verified. Registry gap, not proven absence.
- `materials_complete` stays false (F12: linked/system dependency closure unresolved). Production Android packaging is NOT changed; this is a standalone candidate. Wiring it into the producer needs a separate approval for the existing packaging files.

## Runs
Run 1 41151730583 (discovery+candidate, success; superseded by the minimp3 handling), run 2 41151842961 (success). 2 of 3 budgeted runs used.
