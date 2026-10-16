/* SPDX-License-Identifier: GPL-3.0-only */
#ifndef EXR_BIDI_INTERNAL_H
#define EXR_BIDI_INTERNAL_H
#include "internal.h"
/* Unicode Bidi_Mirroring_Glyph; unchanged when no mirrored glyph is defined. */
EXR_API uint32_t exr_bidi_mirror(uint32_t codepoint);
EXR_API unsigned exr_bidi_base_level(const exr_bidi *bidi, size_t scalar_index);
int exr_bidi_complex(uint32_t codepoint);
exr_status exr_bidi_line_levels(const exr_bidi *bidi, size_t first, size_t count,
                                 unsigned *out);
#endif
