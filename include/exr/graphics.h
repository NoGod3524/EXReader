/* SPDX-License-Identifier: MIT */
#ifndef EXR_GRAPHICS_H
#define EXR_GRAPHICS_H
#include "base.h"
#ifdef __cplusplus
extern "C" {
#endif
typedef struct { double x,y; } exr_path_point;
typedef enum { EXR_PATH_MOVE,EXR_PATH_LINE,EXR_PATH_QUAD,EXR_PATH_CUBIC,EXR_PATH_CLOSE } exr_path_verb;
typedef struct { exr_path_verb verb; exr_path_point points[3]; } exr_path_segment;
typedef enum { EXR_FILL_NONZERO,EXR_FILL_EVENODD } exr_fill_rule;
typedef enum { EXR_CAP_BUTT,EXR_CAP_ROUND,EXR_CAP_SQUARE } exr_line_cap;
typedef enum { EXR_JOIN_MITER,EXR_JOIN_ROUND,EXR_JOIN_BEVEL } exr_line_join;
typedef struct { double width,miter_limit; exr_line_cap cap; exr_line_join join; } exr_path_stroke;
enum { EXR_MASK_GRAY=1,EXR_MASK_ALPHA=2 };
typedef struct exr_image_layer {
  exr_bitmap bitmap;
  struct exr_image_layer *mask;
  unsigned interpolate,mask_mode,has_matte; /* mask_mode: 1 gray*alpha, 2 alpha */
  double matte[3]; /* Optional normalized RGB preblend color to remove. */
} exr_image_layer;
enum { EXR_DRAW_FILL=1,EXR_DRAW_STROKE=2 };
typedef struct {
  uint32_t fill,stroke; /* 0xRRGGBBAA */
  unsigned flags;
  exr_fill_rule rule;
  exr_path_stroke line;
  const double *dashes; size_t dash_count; double dash_phase;
  /* Coordinates defining stroke widths/dashes. NULL uses the path matrix.
     Identity here gives a non-scaling stroke for a transformed path. */
  const double *stroke_matrix;
} exr_draw_style;
/* RGB component blend functions from ISO 32000. Normal uses source-over. */
typedef enum {
  EXR_BLEND_NORMAL,EXR_BLEND_MULTIPLY,EXR_BLEND_SCREEN,EXR_BLEND_OVERLAY,
  EXR_BLEND_DARKEN,EXR_BLEND_LIGHTEN,EXR_BLEND_COLOR_DODGE,EXR_BLEND_COLOR_BURN,
  EXR_BLEND_HARD_LIGHT,EXR_BLEND_SOFT_LIGHT,EXR_BLEND_DIFFERENCE,EXR_BLEND_EXCLUSION,
  EXR_BLEND_HUE,EXR_BLEND_SATURATION,EXR_BLEND_COLOR,EXR_BLEND_LUMINOSITY
} exr_blend_mode;
typedef struct exr_canvas exr_canvas;
typedef struct {
  uint32_t width,height,channels,background; /* channels 0 -> RGBA */
  size_t mask_budget; /* zero -> 64 MiB */
  exr_control control; /* Context must remain valid until canvas_free. */
} exr_canvas_config;
EXR_API exr_draw_style exr_draw_style_defaults(void);
/* Immediate drawing, independent of document format, fonts and UI. Path/image
   inputs are borrowed only for a call. A failed draw poisons the canvas; take
   then returns that failure instead of exposing partial output. */
EXR_API exr_status exr_canvas_create(const exr_canvas_config *config,exr_canvas **out,exr_error *error);
EXR_API void exr_canvas_free(exr_canvas *canvas);
EXR_API size_t exr_canvas_memory_size(const exr_canvas *canvas);
EXR_API const exr_bitmap *exr_canvas_bitmap(const exr_canvas *canvas);
EXR_API exr_status exr_canvas_take(exr_canvas *canvas,exr_bitmap *out,exr_error *error);
/* Save/restore the clipping region; paint styles are supplied per draw. */
/* Blend state is saved/restored with the canvas graphics state. RGB working
   components use the current RGB backdrop (neutral RGB on a gray canvas);
   gray canvases convert after each draw. Fixed extended rendering retains RGB
   throughout the page before converting requested gray output. */
EXR_API exr_status exr_canvas_blend(exr_canvas *canvas,exr_blend_mode mode,exr_error *error);
/* Isolated RGB layer, initially transparent with Normal blend state. The
   inherited clip is applied once when committing. Valid end calls consume the
   layer even on failure; commit=0 discards it and unwinds its inner scopes.
   The current soft mask belongs to the group commit, starts cleared inside the
   group, and is restored when leaving; inner masks do not replace the parent. */
#define EXR_GROUP_ISOLATED 1u
/* Knockout: each element composites with the group's initial backdrop instead of
   the accumulated result, so a later element replaces an earlier one inside its
   coverage. Combine with ISOLATED; end_layer closes either kind. */
#define EXR_GROUP_KNOCKOUT 2u
/* DeviceCMYK blend space. The group keeps four device components and composites
   them with the same CMYK model as page painting; end_layer converts the result
   back to device RGB. Use exr_canvas_path_cmyk to supply CMYK source colours;
   RGB paints and images are converted before blending. Compound fill+stroke
   paths and nested groups inherit the CMYK working space. */
#define EXR_GROUP_CMYK 0x200u
/* Explicit DeviceRGB blend space, overriding an inherited Gray/CMYK space.
   A change from Gray/CMYK requires ISOLATED. Mutually exclusive with CMYK. */
#define EXR_GROUP_RGB 0x400u
/* flags=0 inherits the backdrop; ISOLATED starts transparent. end_layer closes
   either kind. Non-isolated and knockout groups maintain an independent
   source-alpha buffer. */
EXR_API exr_status exr_canvas_begin_group(exr_canvas *canvas,double opacity,exr_blend_mode mode,unsigned flags,exr_error *error);
EXR_API exr_status exr_canvas_begin_layer(exr_canvas *canvas,double opacity,exr_blend_mode mode,exr_error *error);
EXR_API exr_status exr_canvas_end_layer(exr_canvas *canvas,unsigned commit,exr_error *error);
/* Set before entering layers; zero restores the 64 MiB aggregate default. */
EXR_API exr_status exr_canvas_set_layer_budget(exr_canvas *canvas,size_t bytes,exr_error *error);
EXR_API exr_status exr_canvas_save(exr_canvas *canvas,exr_error *error);
EXR_API exr_status exr_canvas_restore(exr_canvas *canvas,exr_error *error);
/* Combined fill/stroke is one knockout element; stroke shape replaces fill. */
EXR_API exr_status exr_canvas_path(exr_canvas *canvas,const exr_path_segment *segments,size_t count,
                                    const double matrix[6],const exr_draw_style *style,exr_error *error);
/* Explicit DeviceCMYK fill/stroke colours (each component 0..1). The style's
   flags, alpha byte, dash and line settings apply; its RGB colour fields are
   ignored. Outside a CMYK group the colours are converted to device RGB first.
   Compound fill and stroke remain a single transparency element. */
EXR_API exr_status exr_canvas_path_cmyk(exr_canvas *canvas,const exr_path_segment *segments,size_t count,
                                         const double matrix[6],const exr_draw_style *style,
                                         const double fill[4],const double stroke[4],exr_error *error);
EXR_API exr_status exr_canvas_clip(exr_canvas *canvas,const exr_path_segment *segments,size_t count,
                                    const double matrix[6],exr_fill_rule rule,exr_error *error);
EXR_API exr_status exr_canvas_image(exr_canvas *canvas,const exr_image_layer *image,const double matrix[6],
                                     double alpha,exr_error *error);
/* Native DeviceCMYK samples, four unsigned bytes C/M/Y/K per pixel, same size
   as image->bitmap. image supplies RGB fallback, alpha, interpolation and masks;
   its matte must already be removed. Samples are borrowed for this call. In a
   CMYK group inks are sampled before blending; elsewhere the RGB image is used. */
EXR_API exr_status exr_canvas_image_cmyk(exr_canvas *canvas,const exr_image_layer *image,const exr_bitmap *inks,
                                      const double matrix[6],double alpha,exr_error *error);
typedef enum { EXR_DRAW_SAVE,EXR_DRAW_RESTORE,EXR_DRAW_BEGIN_CLIP,EXR_DRAW_END_CLIP } exr_draw_state;
typedef exr_status (*exr_draw_path_fn)(void *context,const exr_path_segment *segments,size_t count,
                                        const double matrix[6],const exr_draw_style *style,exr_error *error);
typedef exr_status (*exr_draw_image_fn)(void *context,const exr_image_layer *image,const double matrix[6],
                                         double alpha,exr_error *error);
typedef exr_status (*exr_draw_clip_fn)(void *context,const exr_path_segment *segments,size_t count,
                                        const double matrix[6],exr_fill_rule rule,unsigned accumulate,exr_error *error);
typedef exr_status (*exr_draw_state_fn)(void *context,exr_draw_state state,exr_error *error);
/* A streaming drawing consumer. All callback inputs are borrowed for that
   callback. Absent callbacks are skipped for inspection-only consumers.
   Clip accumulate=0 intersects now; accumulate=1 adds to the union applied at
   END_CLIP. BEGIN_CLIP discards an unfinished union; an empty union is a no-op. */
typedef struct {
  exr_draw_path_fn path;
  exr_draw_image_fn image;
  exr_draw_clip_fn clip;
  exr_draw_state_fn state;
  void *context;
} exr_draw_sink;
typedef exr_status (*exr_draw_blend_fn)(void *context,exr_blend_mode mode,exr_error *error);
/* Versioned consumer. Initialize struct_size; base.context also serves blend.
   Missing blend permits Normal only when a primitive is painted. Layer callbacks
   form a pair; PDF page drawing with blend support also needs that pair. */
typedef exr_status (*exr_draw_layer_begin_fn)(void *context,double opacity,exr_blend_mode mode,exr_error *error);
typedef exr_status (*exr_draw_layer_end_fn)(void *context,unsigned commit,exr_error *error);
typedef exr_status (*exr_draw_group_begin_fn)(void *context,double opacity,exr_blend_mode mode,unsigned flags,exr_error *error);
/* Graphics-state soft mask: one byte per page pixel, 255 = fully visible, NULL
   clears it. Group begin saves it for group commit and clears it internally;
   group end restores it. A consumer without this callback refuses PDF soft masks. */
typedef exr_status (*exr_draw_soft_mask_fn)(void *context,const unsigned char *mask,size_t width,size_t height,exr_error *error);
/* Consumer extent in device pixels; required to build page-space soft masks. */
typedef exr_status (*exr_draw_extent_fn)(void *context,unsigned *width,unsigned *height,exr_error *error);
/* Shading: an RGBA bitmap painted through matrix (shading space to device) with
   the current clip, alpha and blend. Consumers without this callback reject the
   PDF sh operator instead of silently dropping the gradient. */
typedef exr_status (*exr_draw_shading_fn)(void *context,const exr_bitmap *bitmap,const double matrix[6],exr_error *error);
/* DeviceCMYK paint source: fill and stroke components (each 0..1) for a path
   whose style still carries alpha, dashes, line settings and rule. A consumer
   may use the components when it blends in a CMYK group and fall back to the
   style's RGB fields otherwise; the canvas sink accepts both. */
typedef exr_status (*exr_draw_path_cmyk_fn)(void *context,const exr_path_segment *segments,size_t count,
  const double matrix[6],const exr_draw_style *style,const double fill[4],const double stroke[4],exr_error *error);
typedef exr_status (*exr_draw_image_cmyk_fn)(void *context,const exr_image_layer *image,const exr_bitmap *inks,
  const double matrix[6],double alpha,exr_error *error);
/* Return EXR_GROUP_CMYK to request native ink images/gradients in the current
   blend space; other values request RGB. Called before decoding, without
   changing drawing state. Absent query requests inks whenever image_cmyk exists. */
typedef unsigned (*exr_draw_image_space_fn)(void *context);
/* Alpha sources default to opacity. CONSTANT_SHAPE also interprets the current
   graphics-state soft mask as shape. IMAGE_SHAPE treats bitmap alpha as intrinsic
   image shape; explicit image masks are always shape. Save/restore and groups
   preserve this state. Unrecognised bits must be refused. Older consumers without
   this callback retain their image interpretation; CONSTANT_SHAPE is refused. */
enum { EXR_ALPHA_CONSTANT_SHAPE=1u,EXR_ALPHA_IMAGE_SHAPE=2u };
typedef exr_status (*exr_draw_alpha_source_fn)(void *context,unsigned flags,exr_error *error);

typedef struct {
  size_t struct_size;
  exr_draw_sink base;
  exr_draw_blend_fn blend;
  exr_draw_layer_begin_fn begin_layer;
  exr_draw_layer_end_fn end_layer;
  exr_draw_group_begin_fn begin_group; /* Optional general group begin; shares end_layer. */
  exr_draw_soft_mask_fn soft_mask; /* Optional page-space soft mask. */
  exr_draw_extent_fn extent; /* Optional device extent; needed for soft masks. */
  exr_draw_shading_fn shading; /* Optional; PDF sh operator. */
  exr_draw_path_cmyk_fn path_cmyk; /* Optional; PDF CMYK source components for paths. */
  exr_draw_image_cmyk_fn image_cmyk; /* Optional native inks; also receives CMYK gradients. */
  exr_draw_image_space_fn image_space; /* Optional allocation hint for image_cmyk. */
  exr_draw_alpha_source_fn alpha_source; /* Optional shape/opacity interpretation. */
} exr_draw_sink_ex;
/* Initialize out->struct_size to the available storage size. */
EXR_API exr_status exr_canvas_get_sink_ex(exr_canvas *canvas,exr_draw_sink_ex *out,exr_error *error);
/* The returned sink borrows the canvas until canvas_free. */
EXR_API exr_status exr_canvas_get_sink(exr_canvas *canvas,exr_draw_sink *out,exr_error *error);
/* Built-in PNG/JPEG decoder; owns its output pixels, freed with exr_bitmap_free(). */
EXR_API exr_status exr_image_decode(const void *data, size_t size, exr_bitmap *rgba,
                                    exr_error *error);
#ifdef __cplusplus
}
#endif
#endif
