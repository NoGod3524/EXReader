/* SPDX-License-Identifier: MIT */
#ifndef EXR_RENDER_H
#define EXR_RENDER_H
#include "layout.h"
#ifdef __cplusplus
extern "C" {
#endif
EXR_API exr_status exr_render_page(const exr_layout *layout, exr_font *font, size_t page,
                                   exr_bitmap *bitmap, exr_error *error);
/* Controlled rendering; channels must be 1 or 4. Cancellation clears bitmap. */
EXR_API exr_status exr_render_page_ex(const exr_layout *layout, exr_font *font, size_t page,
                                       unsigned channels, const exr_control *control,
                                       exr_bitmap *out, exr_error *error);
EXR_API exr_status exr_render_page_color(const exr_layout *layout, exr_font *font, size_t page,
                                         exr_bitmap *bitmap, exr_error *error);
#ifdef __cplusplus
}
#endif
#endif
