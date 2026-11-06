/* SPDX-License-Identifier: MIT */
#ifndef EXR_SHELL_GEOMETRY_H
#define EXR_SHELL_GEOMETRY_H
#include "shell_tokens.h"
#include <math.h>
typedef struct {
  int enabled, width, height, vertical;
  unsigned dpi;
  float font;
} shell_geometry;
static inline int shell_px(float dip, unsigned dpi) { return (int)floorf(dip * dpi / 96.0f + 0.5f); }
/* Positions are derived from rounded boundaries, never a sum of rounded gaps. */
static inline shell_geometry shell_geometry_for(int w, int h, unsigned dpi, float font, int vertical) {
  shell_geometry out = {0};
  int top = shell_px(SHELL_TOPBAR_H + SHELL_BODY_TOP, dpi);
  int bottom = h - shell_px(SHELL_BODY_BOTTOM + SHELL_PAGE_NUMBER_H + SHELL_BODY_GAP, dpi);
  int available = w - 2 * shell_px(SHELL_SPACE_5, dpi);
  out.enabled = w > 0 && bottom > top && available > 0;
  out.dpi = dpi; out.font = font; out.vertical = vertical;
  out.width = (int)fminf((float)available, (float)shell_px(SHELL_BODY_MAX_EM * font, dpi));
  out.height = bottom - top;
  if (vertical) out.height = (int)fminf((float)(h - shell_px(SHELL_TOPBAR_H + 2 * SHELL_SPACE_5 + SHELL_PAGE_NUMBER_H + SHELL_BODY_BOTTOM, dpi)),
                                      (float)shell_px(SHELL_BODY_MAX_EM * font, dpi));
  if (out.height <= 0) out.enabled = 0;
  return out;
}
/* Origin changes at the 34em cap do not require a new pager. DPI and mode do. */
static inline int shell_geometry_equal(shell_geometry a, shell_geometry b) {
  return a.enabled == b.enabled && (!a.enabled || (a.width == b.width && a.height == b.height &&
    a.font == b.font && a.dpi == b.dpi && a.vertical == b.vertical));
}
#endif
