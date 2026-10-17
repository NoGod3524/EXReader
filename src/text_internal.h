/* SPDX-License-Identifier: GPL-3.0-only */
#ifndef EXR_TEXT_INTERNAL_H
#define EXR_TEXT_INTERNAL_H
#include "internal.h"
#include "text_line_internal.h"
typedef struct {
  int started, previous_gcb;
  exr_line_state line;
  int ri_odd, ep_chain, zwj_after_ep, indic_chain;
} exr_text_state;
unsigned exr_text_step(exr_text_state *state, uint32_t codepoint,
                       exr_text_next next, void *context);
int exr_text_hidden(uint32_t codepoint);
#endif
