# PPT-M4 binary text

The binary reader projects UTF-16 text and its PF/CF runs into the existing
`exr_flow_unit` layout path and draws the engine's font outlines. It shares
the font manager, shaping, wrapping and glyph path APIs used by PPTX M4.
No changes are required in `docx.c` or `pptx.c`.

`TextHeaderAtom` stores its text type in the payload. `TextCharsAtom` is
0x0FA0 and `StyleTextPropAtom` is 0x0FA1. The latter contains paragraph runs
followed by character runs, with no total-length or per-property-block length.
Each run array counts UTF-16 units plus the implicit final CR. See Microsoft's
[TextHeaderAtom](https://learn.microsoft.com/en-us/openspecs/office_file_formats/ms-ppt/08d31a66-0750-4009-b416-49f2871cd178)
and [StyleTextPropAtom](https://learn.microsoft.com/en-us/openspecs/office_file_formats/ms-ppt/a9a5fa71-238d-491e-acc7-fa1fffd5f100).

The parser reads the Environment font array, Environment/master text styles,
paragraph levels, TextRuler margins and shape text insets. Independent textboxes
use Environment defaults; placeholders may inherit their master's styles.
`OutlineTextRefAtom` resolves text stored after the slide's persist reference in
`SlideListWithText`. TextChars wins when both TextChars and TextBytes are present.
TextBytes uses Latin-1 with a warning. Isolated UTF-16 surrogates become U+FFFD.

The supported text subset includes Latin/EA font references, point sizes,
bold/italic/underline, RGB/scheme colors, horizontal alignment, wrapping, soft
breaks, paragraph spacing, absolute/percentage line spacing, vertical anchors,
and Unicode bullet characters with their font/color/size overrides. Font and
glyph fallback diagnostics use the same font-manager selection as PPTX M4.

The committed 16 PowerPoint COM fixtures and runtime binary corruption cases
are exercised by 15 `native-ppt-text-*` groups. Tests use only the Python
standard library and the existing native raster probe. CJK assertions follow
PPTX M4's `has_cjk_font` host split. The generation script records SHA-256 and
reopens saved `.ppt` files through COM for the text oracle. Measurements and
the actual font/color index mappings are in `evidence/ppt-m4/text-tests.txt` and
`text-summary.json`; the complete acceptance report is `OUT-PPTM4.txt`.

Current limits and boundaries:

- Five legacy text levels, up to 65,536 paragraphs/runs per textbox, 1,024 font
  slots, 32 distinct faces per laid-out paragraph; parsed text/structures have
  a cumulative 64 MiB budget, glyph storage 128 MiB, loaded font data 256 MiB.
- Unicode character bullets are supported. Automatic numbered-list extension
  records, Wingdings/Symbol character remapping, advanced tab stops, vertical
  text, rotation, autofit, and PP9/PP10 text extension properties are outside
  this subset. Group anchors transform bounds; group font scaling is not added.
- Standalone Environment CF/PF default atoms and DefaultRuler are not overlaid;
  Environment TextMasterStyleAtom and per-text TextRuler are consumed.
- If a corrupt PF list makes the PF/CF boundary unreadable, visible text falls
  back to the inherited style. A short final CF run inherits its last usable
  style; excess counts are clipped. Both cases report warnings with status=0.
- Text is drawn as glyph paths. Search/selection text indexing is not added.
  Diagnostics fit the existing 256-byte `exr_error.message` and can be truncated.

Build and verify from a configured full-test build:

```powershell
cmake --build ../exr-build-pptm4 -j 8
ctest --test-dir ../exr-build-pptm4 -V -R '^native-ppt-text-'
ctest --test-dir ../exr-build-pptm4 -R '^native-ppt-(shape|fill)-' --output-on-failure
cmake -E env PYTHONUTF8=1 ctest --test-dir ../exr-build-pptm4 -E '^(sdk-release|sdk-doc-coverage)$' --output-on-failure -j 8
pwsh -NoProfile -File C:/Users/Oscar/OneDrive/Desktop/deepseekHarness/ops/prepush-check.ps1 -Worktree C:/Users/Oscar/Documents/Codex/EXReader-ppt-m4
```
