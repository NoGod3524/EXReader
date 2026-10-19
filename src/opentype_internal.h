/* SPDX-License-Identifier: MIT */
#ifndef EXR_OPENTYPE_INTERNAL_H
#define EXR_OPENTYPE_INTERNAL_H
#include "layout_internal.h"
void exr_ot_free(exr_face *face);
int exr_ot_present(exr_face *face);
int exr_ot_transparent(uint32_t codepoint);
/* Unicode script as an OpenType tag; Common/Inherited/unknown return zero.
   Selection of a font's legacy/new Indic script record happens in shape(). */
uint32_t exr_ot_script(uint32_t codepoint);
#endif
