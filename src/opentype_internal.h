/* SPDX-License-Identifier: GPL-3.0-only */
#ifndef EXR_OPENTYPE_INTERNAL_H
#define EXR_OPENTYPE_INTERNAL_H
#include "layout_internal.h"
void exr_ot_free(exr_face *face);
int exr_ot_present(exr_face *face);
int exr_ot_transparent(uint32_t codepoint);
#endif
