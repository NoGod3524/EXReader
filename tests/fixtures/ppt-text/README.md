# Binary PowerPoint text fixtures

`generate.py` creates these files with PowerPoint 16.0 COM, saves format 1
(`.ppt`), closes them, then reopens them to record `manifest.json` and export
the `*-powerpoint.png` reference images. Office and pywin32 are generation
tools only. The committed tests use Python's standard library and the native
`exreader-ppt-shape-probe` raster output.

Run `python tests/fixtures/ppt-text/generate.py` on Windows with PowerPoint and
pywin32 to regenerate. Each manifest entry records the saved file SHA-256 and
the reopened COM text, font, size, alignment, shape bounds and margins.

Cases cover centered black 18pt Hello; 12/24/48pt Hello; regular/bold 48pt
vertical stems; four Chinese characters with SimHei; left/center/right 24pt
alignment; three real paragraph bullet dots plus an independent literal dot;
wrapping; 40pt exact line spacing with 12pt paragraph spacing; mixed character
runs; and a theme text color saved by PowerPoint as an explicit COLORINDEX.

The ASCII fixtures contain `TextBytesAtom`; PowerPoint writes the Chinese and
literal bullet characters as `TextCharsAtom`. Binary negative tests construct
independent CFB/record data at runtime for Unicode decoding, Latin-1 fallback,
invalid indices, all eight scheme slots, truncated styles, and inconsistent
paragraph/character run counts. A separate synthetic master test verifies
Environment `TextMasterStyleAtom` sizes and `MasterTextPropAtom` level selection
against explicitly styled text. The outline test resolves `OutlineTextRefAtom`
through `SlideListWithText` and compares its Latin/CJK output with inline text.

The font array in these saved files is 0=Aptos, 1=Arial, 2=Aptos Display,
3=SimHei. Slide character properties reference 1 for Latin/ANSI and 3 for
East Asian text. `check_ppt_text.py indices` reads the saved binary font array
and color scheme, prints their mappings, and verifies every color index
against a direct-color raster reference.

`check_ppt_text.py cjk` uses the same `has_cjk_font` host-font detection as
PPTX M4: with CJK fonts it requires four different silhouettes; without them
it requires the fallback warning. It does not require a CJK font on CI.
