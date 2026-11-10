/* SPDX-License-Identifier: MIT */
#ifndef EXR_SHELL_HIGHLIGHT_H
#define EXR_SHELL_HIGHLIGHT_H
/* Union first: overlapping glyphs/ligatures receive the highlight once. Shared
   by the reader's glyph selection and the editor's DirectWrite hit rectangles. */
static inline void shell_highlight_rect(HRGN region, float x, float y, float w, float h) {
  if (w < 0) { x += w; w = -w; }
  if (h < 0) { y += h; h = -h; }
  HRGN box = CreateRectRgn((int)floorf(x), (int)floorf(y), (int)ceilf(x+w), (int)ceilf(y+h));
  CombineRgn(region, region, box, RGN_OR);
  DeleteObject(box);
}
#endif
