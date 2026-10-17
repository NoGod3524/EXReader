# Original Devanagari shaping fixtures

These two geometric fonts are EXReader original code/assets, GPL-3.0-only,
copyright 2026 EXReader contributors. They use rectangles instead of artwork
from a reading font. `dev2.ttf` and `deva-legacy.ttf` distinguish modern and legacy
basic-form feature order, nukta, reph, half/conjunct forms, ZWJ/ZWNJ, pre-base
matras, broken-syllable circles, contextual substitutions and mark attachment.

`tools/generate_indic_test_font.py` uses fontTools to regenerate both fonts.
`tools/generate_indic_reference.py` uses development-only uharfbuzz to regenerate
64 independently shaped expectations in `reference.h`. The generated file records
the HarfBuzz version and each font hash. Native builds/tests need neither Python,
HarfBuzz nor fontTools. The C test separately validates source ranges,
cancellation/failure cleanup and paginated layout/rendering.
