/* SPDX-License-Identifier: GPL-3.0-only */
#ifndef EXR_FLOW_INTERNAL_H
#define EXR_FLOW_INTERNAL_H
#include "layout_internal.h"
#include "text_internal.h"
#include "hyphen_internal.h"
#define EXR_PAUSE ((exr_status)100)
#define EXR_REFLOW ((exr_status)101)
#define EXR_FRAGMENT_SMALL ((exr_status)102)
#define EXR_MAX_FLOATS 128
typedef struct { float x,y,width,height; unsigned side; } exr_float;
typedef struct { exr_float items[EXR_MAX_FLOATS]; size_t count; } exr_float_state;
#define EXR_GLYPH_TRY_VERTICAL 512u /* Internal UAX #50 Tr probe, cleared before output. */
#define EXR_GLYPH_RUBY_ITEM 1024u /* Internal atomic inline item, expanded before output. */
#define EXR_BOUNDARY_AUTO_HYPHEN 16u /* Private raw-source opportunity, not a shaping boundary. */
typedef struct {
  size_t point,start,end,word_start,until,before,after;
  size_t raw_start,raw_point,raw_end;
  unsigned mapped;
  char text[514];
} exr_hyphen_edit;
typedef struct {
  size_t start,until,count,points[256];
  char language[256];
  exr_hyphen_edit *edits;size_t edit_count,edit_capacity;
} exr_hyphen_word;
typedef struct {
  exr_bidi *analysis;
  size_t *offsets, count;
  size_t first_node;
} exr_inline_bidi;
typedef struct {
  exr_layout *layout, *assets;
  const exr_document *doc;
  const exr_style *styles, *paragraph;
  const exr_layout_config *config;
  exr_font *font;
  exr_hyphenator *hyphenator; /* Borrowed from the owning root pager. */
  exr_error *error;
  float x, width, y, bottom_inset, origin_x, used_inline, inline_end_inset;
  size_t pending;
  int first_line, paginate, force_break, unit_depth, page_limit, context_depth;
  int intrinsic; /* 1: every legal line break, 2: unwrapped streaming measure. */
  double intrinsic_extent;
  size_t border_node;
  float border_insets[4]; /* Logical top/right/bottom/left of a collapsed cell. */
  int border_override;
  exr_float_state *floats;
  size_t unit_node;
  float unit_reference;
  float unit_block_reference;
  int unit_assigned;
  int fragment_probe;
  exr_inline_bidi *bidi;
  exr_writing_mode writing_mode;
} flow;
typedef struct {
  exr_layout run, raw, line;
  exr_text_state text;
  uint32_t before, after;
  size_t cluster_start, ready, scan, soft, emergency, line_end, raw_end;
  float scan_width;
  float scan_ascent,scan_descent,scan_leading,line_x,line_width;
  int initialized, finishing, forced, final, line_ready;
  unsigned vertical_flags;
  double measure_width, measure_trailing;
  exr_glyph measure_last;
  int measure_has_last;
  exr_hyphen_word *word;
  size_t word_node,word_start,previous_node;
  uint32_t previous_scalar;
  int in_word;
  exr_hyphen_edit *edits;size_t edit_count,edit_capacity,rewrite,blocked_until;
} exr_line_buffer;
void exr_inline_clear(exr_inline_bidi *bidi);
unsigned exr_vertical_flags(uint32_t codepoint, exr_text_orientation orientation);
exr_status exr_inline_prepare(flow *f, size_t first_node, exr_inline_bidi *bidi);
unsigned exr_inline_level(const exr_inline_bidi *bidi, size_t offset);
unsigned exr_inline_base(const exr_inline_bidi *bidi, size_t offset);
exr_status exr_inline_reorder(flow *f, exr_glyph *glyphs, size_t count);
exr_status exr_inline_shape(flow *f, size_t start, uint32_t before, uint32_t after);
exr_status exr_inline_feed(flow *f, exr_line_buffer *buffer, exr_glyph glyph);
exr_status exr_inline_drain(flow *f, exr_line_buffer *buffer);
exr_status exr_inline_finish(flow *f, exr_line_buffer *buffer);
void exr_inline_buffer_clear(exr_line_buffer *buffer);
size_t exr_inline_extra_size(const exr_line_buffer *buffer,int compact);
void exr_inline_rescan(exr_line_buffer *buffer);
exr_status exr_inline_pending(flow *f,exr_line_buffer *buffer,float *width);
exr_status exr_inline_break(flow *f,exr_line_buffer *buffer);
void exr_flow_clear(flow *f,unsigned side);
void exr_flow_area(const flow *f,float y,float height,float *x,float *width,float *next);
exr_status exr_flow_line_slot(flow *f,float height,float minimum,size_t offset,float *x,float *width);
exr_status exr_flow_float_slot(flow *f,float width,float height,unsigned clear,size_t offset,float *x,float *y);
exr_status exr_flow_float_add(flow *f,exr_float item);
float exr_flow_top(const flow *f);
float exr_flow_bottom(const flow *f);
float exr_flow_room(const flow *f);
exr_style exr_flow_style(const exr_style *style, exr_writing_mode mode);
exr_status exr_flow_page(flow *f, float height, size_t offset);
exr_box *exr_flow_box(flow *f, size_t node, size_t page, float x, float y,
                       float width, float height, exr_box_kind kind);
exr_status exr_flow_cluster(flow *f, size_t start, size_t end);
exr_status exr_flow_image(flow *f, size_t node, float x, float width);
exr_status exr_flow_emit_line(flow *f, exr_glyph *glyphs, size_t count,
                               int forced, int final);
exr_status exr_flow_unit(flow *parent, size_t node, float width,
                          exr_layout **out, float *height);
exr_status exr_flow_intrinsic(flow *parent,size_t node,float width,int mode,float *out);
exr_status exr_flow_copy(flow *f, const exr_layout *from, size_t node,
                          float x, float y, float height,float inset);
typedef struct exr_table_cursor exr_table_cursor;
exr_status exr_table_create(flow *f, size_t node, float x, float width, exr_table_cursor **out);
exr_status exr_table_step(flow *f, exr_table_cursor *cursor, int *done);
void exr_table_free(exr_table_cursor *cursor);
size_t exr_table_memory_size(const exr_table_cursor *cursor);
exr_table_cursor *exr_table_clone(const exr_table_cursor *cursor);
size_t exr_table_position(const exr_table_cursor *cursor);
void exr_table_geometry(const exr_table_cursor *cursor,float *x,float *width);
#endif
