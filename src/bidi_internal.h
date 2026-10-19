/* SPDX-License-Identifier: MIT */
#ifndef EXR_BIDI_INTERNAL_H
#define EXR_BIDI_INTERNAL_H
#include "internal.h"
typedef struct exr_bidi_override {
  size_t refs,start,end,depth;
  exr_direction direction;
  struct exr_bidi_override *previous;
} exr_bidi_override;
void exr_bidi_override_free(exr_bidi_override *item);
exr_direction exr_bidi_override_at(const exr_bidi_override *item,size_t source);
exr_status exr_bidi_analyze_mapped(const char *text,size_t size,exr_direction requested,
  const size_t *sources,const exr_bidi_override *overrides,exr_bidi **out,exr_error *error);
exr_status exr_bidi_analyze_first(const char *text,size_t size,exr_direction requested,
  exr_direction first,exr_bidi **out,exr_error *error);
unsigned exr_bidi_tail_type(uint32_t codepoint);
int exr_bidi_paragraph_end(uint32_t codepoint);
/* Advance UAX #9 P2, ignoring the contents of nested isolates. */
unsigned exr_bidi_p2(uint32_t codepoint,size_t *isolate_depth);
/* Unicode Bidi_Mirroring_Glyph; unchanged when no mirrored glyph is defined. */
/* exr_bidi_mirror() and exr_bidi_base_level() are public API; see exreader.h. */
int exr_bidi_complex(uint32_t codepoint);
int exr_bidi_ltr_letter(uint32_t codepoint);
unsigned exr_bidi_strong_type(uint32_t codepoint); /* 0: other, 1: L, 2: R, 3: AL. */
int exr_bidi_window_safe(uint32_t codepoint);
exr_status exr_bidi_line_levels(const exr_bidi *bidi, size_t first, size_t count,
                                 unsigned *out);
#endif
