/* SPDX-License-Identifier: GPL-3.0-only */
#ifndef EXR_FONT_OUTLINE_INTERNAL_H
#define EXR_FONT_OUTLINE_INTERNAL_H
#include "vector_internal.h"
#include <ft2build.h>
#include FT_FREETYPE_H
/* Scalable face -> owned path in 1000-em coordinates. No hinting/bitmap/font
   rasterization. The caller frees segments; no FT slot pointers escape. */
exr_status exr_font_outline(FT_Face face,uint32_t glyph,exr_vector_segment **segments,size_t *count,
                              size_t *work,const exr_control *control,exr_error *error);
#endif
