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
/* Initial canvas in straight 0xRRGGBBAA; book paints/images retain their original
   order, colors and alpha. channels is 1 or 4. Gray uses (77R+150G+29B+128)>>8,
   ignoring background alpha, as exr_canvas_create does for one-channel output.
   The caller must release a previous bitmap before reusing out. Every failure
   leaves out empty. Layout/font and their borrowed views remain unchanged.
   The three older render entry points always retain an opaque white canvas. */
EXR_API exr_status exr_render_page_background(const exr_layout *layout, exr_font *font, size_t page,
  unsigned channels, uint32_t background_rgba, const exr_control *control,
  exr_bitmap *out, exr_error *error);
EXR_API exr_status exr_render_page_color(const exr_layout *layout, exr_font *font, size_t page,
                                         exr_bitmap *bitmap, exr_error *error);
#ifdef __cplusplus
}
#endif
#endif
