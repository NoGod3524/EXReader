/* SPDX-License-Identifier: GPL-3.0-only */
#ifndef EXR_FLOW_INTERNAL_H
#define EXR_FLOW_INTERNAL_H
#include "layout_internal.h"
#include "text_internal.h"
#define EXR_PAUSE ((exr_status)100)
typedef struct {
  exr_bidi *analysis;
  size_t *offsets, count;
} exr_inline_bidi;
typedef struct {
  exr_layout *layout, *assets;
  const exr_document *doc;
  const exr_style *styles, *paragraph;
  const exr_layout_config *config;
  exr_font *font;
  exr_error *error;
  float x, width, y, bottom_inset;
  size_t pending;
  int first_line, paginate, force_break, table_depth, page_limit;
  exr_inline_bidi *bidi;
} flow;
typedef struct {
  exr_layout run, raw, line;
  exr_text_state text;
  uint32_t before, after;
  size_t cluster_start, ready, scan, soft, emergency, line_end, raw_end;
  float scan_width;
  int initialized, finishing, forced, final, line_ready;
} exr_line_buffer;
void exr_inline_clear(exr_inline_bidi *bidi);
exr_status exr_inline_prepare(flow *f, size_t first_node, exr_inline_bidi *bidi);
unsigned exr_inline_level(const exr_inline_bidi *bidi, size_t offset);
unsigned exr_inline_base(const exr_inline_bidi *bidi, size_t offset);
exr_status exr_inline_reorder(flow *f, exr_glyph *glyphs, size_t count);
exr_status exr_inline_shape(flow *f, size_t start, uint32_t before, uint32_t after);
exr_status exr_inline_feed(flow *f, exr_line_buffer *buffer, exr_glyph glyph);
exr_status exr_inline_drain(flow *f, exr_line_buffer *buffer);
exr_status exr_inline_finish(flow *f, exr_line_buffer *buffer);
void exr_inline_buffer_clear(exr_line_buffer *buffer);
float exr_flow_top(const flow *f);
float exr_flow_bottom(const flow *f);
float exr_flow_room(const flow *f);
exr_status exr_flow_page(flow *f, float height, size_t offset);
exr_box *exr_flow_box(flow *f, size_t node, size_t page, float x, float y,
                       float width, float height, exr_box_kind kind);
exr_status exr_flow_cluster(flow *f, size_t start, size_t end);
exr_status exr_flow_image(flow *f, size_t node, float x, float width);
exr_status exr_flow_emit_line(flow *f, exr_glyph *glyphs, size_t count,
                               size_t destination, int forced, int final);
exr_status exr_flow_unit(flow *parent, size_t node, float width,
                          exr_layout **out, float *height);
exr_status exr_flow_copy(flow *f, const exr_layout *from, size_t node,
                          float x, float y, float height);
typedef struct exr_table_cursor exr_table_cursor;
exr_status exr_table_create(flow *f, size_t node, float x, float width, exr_table_cursor **out);
exr_status exr_table_step(flow *f, exr_table_cursor *cursor, int *done);
void exr_table_free(exr_table_cursor *cursor);
size_t exr_table_position(const exr_table_cursor *cursor);
#endif
