/* SPDX-License-Identifier: GPL-3.0-only */
#ifndef EXR_INTERNAL_H
#define EXR_INTERNAL_H
#include "exreader.h"
#include <limits.h>
#include <math.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define EXR_DECORATIONS (EXR_GLYPH_UNDERLINE | EXR_GLYPH_STRIKE)
/* Internal hint: this group's caller relies on whole-canvas buffer semantics. */
#define EXR_GROUP_WHOLE_BUFFER 0x80u
/* Internal flag: the group blends in DeviceGray, so painted colours are reduced
   to luminance before they reach the raster. */
#define EXR_GROUP_GRAY 0x100u
#define EXR_MAX_INPUT ((size_t)128 * 1024 * 1024)
#define EXR_MAX_TEXT ((size_t)64 * 1024 * 1024)
#define EXR_MAX_ITEMS ((size_t)4 * 1024 * 1024)
#define EXR_MAX_NODES ((size_t)262144)
typedef struct {
  unsigned char *bytes;
  size_t size;
} exr_resource_data;
typedef struct {
  unsigned char *bytes;
  size_t size, refs;
  exr_source source;
} exr_archive_store;
struct exr_document {
  char *text, *title,*language; /* Optional publication-level fallback; element lang wins. */
  size_t size, text_capacity;
  exr_block *blocks;
  size_t count, capacity;
  exr_format format;
  exr_node *nodes;
  size_t node_count, node_capacity, model_bytes;
  size_t *last_children;
  size_t last_capacity;
  exr_chapter *chapters;
  size_t chapter_count, chapter_capacity;
  exr_resource *resources;
  size_t resource_count, resource_capacity;
  exr_resource_data *resource_data; /* Copied resources from public construction inputs. */
  int owns_chapter_strings;
  unsigned char *archive;
  size_t archive_size;
  exr_archive_store *shared_archive;
  size_t ncx_resource;
  int has_ncx;
};
typedef struct {
  char *data;
  size_t size, capacity;
} exr_buffer;
exr_status exr_fail(exr_error *error, exr_status status, const char *fmt, ...);
exr_status exr_control_cancel(const exr_control *control, exr_error *error);
exr_status exr_control_poll(const exr_control *control, exr_stage stage,
                             uint64_t completed, uint64_t total, exr_error *error);
exr_status exr_kmp_prefix(const char *query,size_t size,const exr_control *control,uint32_t **out,exr_error *error);
exr_status exr_find_bytes(const char *text,size_t size,const char *query,size_t query_size,size_t from,
                            const exr_control *control,size_t *start,size_t *end,exr_error *error);
int exr_grow(void **data, size_t *capacity, size_t count, size_t element);
char *exr_copy(const char *text, size_t size);
exr_status exr_export_time(char modified[32], exr_error *error);
exr_status exr_xml_text(const char *text, size_t size, const char *field, exr_error *error);
int exr_append(exr_buffer *buf, const void *data, size_t size);
exr_status exr_number_text(exr_buffer *out,int value,const char *format,exr_error *error);
int exr_codepoint(exr_buffer *buf, uint32_t cp);
int exr_next(const char *text, size_t size, size_t *offset, uint32_t *cp);
FILE *exr_fopen(const char *path, const char *mode);
exr_status exr_read(const char *path, unsigned char **data, size_t *size, exr_error *error);
exr_status exr_decode(const void *data, size_t size, exr_buffer *buf, exr_error *error);
/* Private four-component JPEG samples, before PDF Decode and color conversion.
   channels==4 stores C/M/Y/K, not RGBA. */
exr_status exr_jpeg_cmyk_decode(const void *data,size_t size,const exr_control *control,
                               exr_bitmap *out,exr_error *error);
exr_status exr_audio_ref(exr_audio *audio,exr_error *error);
exr_status exr_fixed_anchor_validate(const exr_fixed_anchor *anchor,exr_error *error);
exr_status exr_anchor_validate(const exr_anchor *anchor, exr_error *error);
exr_status exr_parse(exr_document *doc, const void *data, size_t size, exr_error *error);
exr_status exr_epub_index(const void *data, size_t size, exr_document **out, exr_error *error);
exr_status exr_epub_index_source(const exr_source *source, exr_document **out, exr_error *error);
exr_status exr_file_source_limit(const char *path,uint64_t maximum,exr_source *source,exr_error *error);
exr_status exr_file_source(const char *path, exr_source *source, exr_error *error);
exr_status exr_xml_resource(const exr_document *doc, size_t resource, const char *root_name,
                             exr_document **out, exr_error *error);
exr_status exr_epub_navigation(const exr_document *index, size_t metadata_bytes,
                                exr_navigation **entries, size_t *count, exr_error *error);
exr_status exr_cfi_context(const exr_document *doc,size_t chapter,const exr_cfi_point *point,size_t context,const exr_control *control,char **before,char **after,exr_error *error);
exr_status exr_cfi_assertion_resolve(const exr_document *doc,size_t chapter,const char *before,const char *after,const exr_control *control,exr_cfi_point *point,exr_error *error);
exr_status exr_cfi_create_for_part(const exr_document *index,size_t part,const exr_document *doc,size_t chapter,const exr_cfi_point *point,size_t context,const exr_control *control,char **out,exr_error *error);
exr_status exr_cfi_route(const exr_document *index,const char *cfi,const exr_control *control,size_t *part,char **local,exr_error *error);
exr_status exr_epub_package_tree(const exr_document *doc,const exr_control *control,exr_document **out,exr_error *error);
exr_status exr_epub_export_check(const exr_document *doc, exr_error *error);
exr_status exr_epub_load(const exr_document *index, size_t part, exr_document **out,
                        exr_error *error);
int exr_add_block(exr_document *doc, const char *text, size_t size, unsigned heading);
char *exr_model_copy(exr_document *doc, const char *text, size_t size);
const char *exr_html_tag(const exr_document *doc, const exr_node *node);
size_t exr_model_node(exr_document *doc, size_t parent, size_t chapter, exr_node_kind kind,
                      const char *name, const char *text, size_t length);
exr_status exr_xhtml(exr_document *doc, const void *data, size_t size, size_t resource,
                     int in_spine, int linear, exr_error *error);
typedef exr_status (*exr_xml_position_fn)(void *context, size_t offset, size_t node);
exr_status exr_xhtml_positions(exr_document *doc, const void *data, size_t size, size_t resource,
                                 exr_xml_position_fn position, void *context, exr_error *error);
exr_status exr_xml_tree(exr_document *doc, const void *data, size_t size, size_t resource,
                         int in_spine, int linear, const char *root_name, exr_error *error);
size_t exr_model_html(exr_document *doc, size_t parent, size_t chapter, exr_node_kind kind,
                       const char *tag, const char *text);
int exr_model_attribute(exr_document *doc, size_t node, const char *name, const char *value);
exr_status exr_xml_memory_tree(const void *data, size_t size, const char *root,
                                exr_document **out, exr_error *error);
exr_status exr_xml_serialize(const exr_document *doc, size_t root,
                               exr_buffer *out, exr_error *error);
typedef exr_status (*exr_member_read_fn)(void *context, const char *path, int optional,
                                          void **data, size_t *size, exr_error *error);
exr_status exr_docx(exr_document *doc, exr_member_read_fn read, void *context, exr_error *error);
exr_status exr_model_finish(exr_document *doc, exr_error *error);
void exr_model_free(exr_document *doc);
int exr_canonical_path(const char *path);
typedef struct { const unsigned char *data; size_t size; } exr_mobi_record;
exr_status exr_kf8(exr_document *doc, const exr_mobi_record *records, size_t count,
                    const exr_mobi_record *shared, size_t shared_count,
                    const char *text, size_t size, exr_error *error);
exr_status exr_mobi_cover(exr_document *doc, const exr_mobi_record *records, size_t count,
                           const exr_mobi_record *shared, size_t shared_count,
                           uint32_t cover, exr_error *error);
typedef struct exr_mobi_huff exr_mobi_huff;
exr_status exr_mobi_huff_open(const exr_mobi_record *records, size_t count,
                               exr_mobi_huff **out, exr_error *error);
/* Append to one initially empty output buffer across text records. */
exr_status exr_mobi_huff_decode(exr_mobi_huff *huff, const void *data, size_t size,
                                 exr_buffer *out, exr_error *error);
void exr_mobi_huff_free(exr_mobi_huff *huff);
uint32_t exr_windows1252(unsigned char byte);
exr_status exr_rtf(exr_document *doc, const void *data, size_t size, exr_error *error);
exr_status exr_fb2(exr_document *doc, const void *data, size_t size, exr_error *error);
int exr_uri_path(exr_buffer *buffer, const char *path);
int exr_uri_decode(const char *text, size_t size, char out[2048]);
int exr_resolve_path(const char *base, const char *href, char out[2048]);
typedef struct {
  float value;
  int percent;
} exr_length; /* value < 0 means auto */
enum { EXR_CSS_NONE, EXR_CSS_INLINE, EXR_CSS_BLOCK, EXR_CSS_TABLE, EXR_CSS_ROW, EXR_CSS_CELL };
enum { EXR_CELL_BASELINE,EXR_CELL_TOP,EXR_CELL_MIDDLE,EXR_CELL_BOTTOM };
enum { EXR_HYPHENS_MANUAL,EXR_HYPHENS_AUTO,EXR_HYPHENS_NONE };
typedef struct {
  char family[128], source[2048], base[2048];
  size_t chapter;
  unsigned flags;
} exr_font_rule;
/* Border sides use CSS physical order: 0 top, 1 right, 2 bottom, 3 left. */
typedef struct {
  float font_size, leading, indent, border_width[4];
  const char *family;
  int family_owned;
  int leading_relative, align, display, before, after, border_style[4], writing_declared;
  int ruby_position, ruby_align;
  int table_fixed;
  int border_collapse;
  int vertical_align;
  int float_side,clear_side; /* CSS line-left=1, line-right=2, both=3. */
  int hyphens;
  unsigned flags;
  exr_direction direction;
  exr_writing_mode writing_mode;
  exr_text_orientation orientation;
  uint32_t color, background, border_color[4];
  exr_length width, height, max_width, max_height, margin[4], padding[4];
} exr_style;
/* A visible border occupies its width; CSS "hidden" reserves no space outside
   the collapsing model. */
static inline float exr_border_extent(const exr_style *s, int side) {
  int style = s->border_style[side];
  return style != 0 && style != 2 ? s->border_width[side] : 0;
}
static inline int exr_border_any(const exr_style *s) {
  int side;
  for (side = 0; side < 4; side++)
    if (exr_border_extent(s, side) > 0)
      return 1;
  return 0;
}
/* All four sides share one width, colour and style; the single-border box path
   can then keep the compact representation. */
static inline int exr_border_uniform(const exr_style *s) {
  int side;
  for (side = 1; side < 4; side++) {
    if (s->border_style[side] != s->border_style[0])
      return 0;
    if (s->border_style[side] &&
        (s->border_width[side] != s->border_width[0] ||
         s->border_color[side] != s->border_color[0]))
      return 0;
  }
  return 1;
}
exr_status exr_compute_styles(const exr_document *doc, const exr_layout_config *config,
                              exr_style **styles, exr_font_rule **fonts, size_t *font_count,
                              exr_error *error);
void exr_styles_free(exr_style *styles, size_t count);
int exr_family_next(const char *value, size_t *offset, char out[128]);
int exr_family_equal(const char *a, const char *b);
int exr_parse_font_rule(const char *body, size_t size, const char *base,
                         size_t chapter, exr_font_rule *rule);
size_t exr_css_delimiter(const char *text, size_t size, char delimiter);
exr_status exr_image_dimensions(const void *data,size_t size,uint32_t *width,uint32_t *height,exr_error *error);
static inline int exr_format_is_fixed(exr_format format) { return format==EXR_PDF || format==EXR_CBZ; }
/* CBZ memory takes ownership of bytes on every path. File keeps a lazy source. */
exr_status exr_cbz_open_owned(unsigned char *data,size_t size,const char *title,
  const exr_fixed_open_options *options,exr_fixed_document **out,exr_error *error);
exr_status exr_cbz_open_file(const char *path,const char *title,
  const exr_fixed_open_options *options,exr_fixed_document **out,exr_error *error);
exr_status exr_draw_sink_snapshot(const exr_draw_sink_ex *input,exr_draw_sink_ex *out,exr_error *error);
/* Non-isolated working pixels: premultiplied RGB, complete alpha, group-only
   alpha. A NULL buffer keeps the original compact 8-bit drawing path. */
typedef struct exr_composite_state {
  float *pixels;float *cmyk_pixels;exr_bitmap backdrop;const struct exr_composite_state *backdrop_state;
  uint32_t left,top,right,bottom;unsigned depth;unsigned knockout,isolated;
  /* Working buffers may cover only a sub-rectangle of the canvas. */
  int origin_x,origin_y;
  /* Graphics-state soft mask: one byte per page pixel, 255 = fully visible. */
  const unsigned char *soft_mask;size_t soft_mask_width,soft_mask_height;
} exr_composite_state;
exr_status exr_sink_begin_group(const exr_draw_sink_ex *sink,double opacity,exr_blend_mode mode,unsigned flags,exr_error *error);
exr_status exr_sink_soft_mask(const exr_draw_sink_ex *sink,const unsigned char *mask,size_t width,size_t height,exr_error *error);
exr_status exr_sink_extent(const exr_draw_sink_ex *sink,unsigned *width,unsigned *height,exr_error *error);
exr_status exr_composite_initialize(exr_bitmap *child,exr_composite_state *state,const exr_bitmap *parent,
  const exr_composite_state *parent_state,int origin_x,int origin_y,size_t *work,const exr_control *control,exr_error *error);
exr_status exr_composite_compound(exr_bitmap *target,const exr_bitmap *fill,const exr_bitmap *stroke,
  uint32_t fill_color,uint32_t stroke_color,exr_blend_mode mode,const exr_bitmap *clip,exr_composite_state *state,
  size_t *work,const exr_control *control,exr_error *error);
exr_status exr_bitmap_to_gray(exr_bitmap *bitmap,const exr_control *control,exr_error *error);
exr_status exr_composite_frame(exr_bitmap *target,const exr_bitmap *source,double opacity,exr_blend_mode mode,
  const exr_bitmap *clip,exr_composite_state *target_state,const exr_composite_state *source_state,
  int origin_x,int origin_y,size_t *work,const exr_control *control,exr_error *error);
#endif
