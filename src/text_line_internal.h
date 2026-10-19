/* SPDX-License-Identifier: MIT */
#ifndef EXR_TEXT_LINE_INTERNAL_H
#define EXR_TEXT_LINE_INTERNAL_H
#include <stdint.h>
typedef int (*exr_text_next)(void *context, uint32_t *codepoint);
typedef struct {
  int lb;
  unsigned gc, east, ep;
  uint32_t cp;
} exr_lb_char;
typedef struct {
  exr_lb_char previous, before_previous, space_base;
  int started, raw_previous, initial_quote, numeric, number_close, ri_odd;
} exr_line_state;
#endif
