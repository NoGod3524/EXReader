/* SPDX-License-Identifier: MIT */
#ifndef EXR_FLOW_INTERNAL_H
#define EXR_FLOW_INTERNAL_H
#include "layout_internal.h"
#include "text_internal.h"
#include "hyphen_internal.h"
#include "display_bidi_internal.h"
#define EXR_PAUSE ((exr_status)100)
#define EXR_REFLOW ((exr_status)101)
#define EXR_FRAGMENT_SMALL ((exr_status)102)
#define EXR_BIDI_RESOLVED ((exr_status)103)
#define EXR_BIDI_CUT ((exr_status)104)
#define EXR_MAX_FLOATS 128
typedef struct { float x,y,width,height; unsigned side; } exr_float;
typedef struct { exr_float items[EXR_MAX_FLOATS]; size_t count; } exr_float_state;
#define EXR_GLYPH_TRY_VERTICAL 512u /* Internal UAX #50 Tr probe, cleared before output. */
#define EXR_GLYPH_DELETED 4096u /* Private empty replacement source marker. */
#define EXR_GLYPH_DISPLAY_BIDI 8192u /* Private page field holds a display scalar index. */
#define EXR_GLYPH_RUBY_ITEM 1024u /* Internal atomic inline item, expanded before output. */
#define EXR_BOUNDARY_AUTO_HYPHEN 16u /* Private raw-source opportunity, not a shaping boundary. */
/* Transient display-grapheme identity; output retains only public low bits. */
#define EXR_DISPLAY_ID_SHIFT 5u
#define EXR_DISPLAY_ID_MASK (~31u)
static inline unsigned exr_inline_id(const exr_glyph *g) { return g->boundaries>>EXR_DISPLAY_ID_SHIFT; }
static inline int exr_inline_same(const exr_glyph *a,const exr_glyph *b) {
  unsigned x=exr_inline_id(a),y=exr_inline_id(b);
  return x || y ? x==y : a->cluster_start==b->cluster_start;
}
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
  int plan_risky,prepared,window_safe; /* -1 unknown; safety cache belongs to this cursor. */
  size_t *refs;
} exr_inline_bidi;
typedef struct {
  size_t start,end,isolate_depth;
  unsigned strong;
} exr_bidi_probe;
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
  int measure_height; /* Exact wrapped geometry; discard emitted glyph/line snapshots. */
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
  int defer_tall_rows; /* Initial auto-table probe prefers its wider float-free corridor. */
  exr_inline_bidi *bidi;
  const exr_bidi_override *auto_bases; /* Borrowed from this pager line buffer. */
  void *plan_cursor;
  exr_status (*plan_resolve)(void *cursor);
  exr_plan_builder *plan_probe; /* Borrowed during a complete paragraph trial. */
  exr_bidi_probe *auto_probe; /* Borrowed only by a speculative paragraph cursor. */
  const exr_display_view *display_bidi; /* Borrowed only while emitting a line. */
  size_t display_first,display_count;
  exr_writing_mode writing_mode;
} flow;
typedef struct {
  exr_layout run, raw, line;
  exr_text_state text, display_origin, display_line;
  uint32_t display_previous, line_previous;
  unsigned display_origin_id,display_feed_id,display_line_id;
  size_t display_node, line_node;
  int track_display, display_changed;
  exr_display_state *display;
  exr_bidi_override *auto_bases;
  exr_display_plan *plan;
  exr_display_view *plan_view;
  exr_display_patch *plan_pending,*plan_prefix,*plan_suffix;
  exr_direction plan_base;
  size_t plan_at,plan_line,line_plan_count;
  int plan_valid,line_plan_match;
  unsigned first_strong,line_first_strong; /* Safe-window context; full path retains UAX9 P2. */
  int last_hyphen,line_last_hyphen,display_committed;
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
exr_status exr_inline_auto_stable(flow *f,exr_line_buffer *buffer,size_t node,size_t offset,int *stable);
size_t exr_inline_paragraph_end(flow *f,size_t node,size_t offset);
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
exr_status exr_flow_edge(flow *f, size_t node, int style, float width, uint32_t color,
                         float x, float y, float w, float h);
exr_status exr_flow_borders(flow *f, size_t node, const exr_style *s,
                            float x, float y, float width, float height);
exr_status exr_flow_cluster(flow *f, size_t start, size_t end);
exr_status exr_flow_image(flow *f, size_t node, float x, float width);
exr_status exr_flow_emit_line(flow *f, exr_glyph *glyphs, size_t count,
                               int forced, int final);
exr_status exr_flow_unit(flow *parent, size_t node, float width,
                          exr_layout **out, float *height);
exr_status exr_flow_intrinsic(flow *parent,size_t node,float width,int mode,float *out);
exr_status exr_flow_copy(flow *f, const exr_layout *from, size_t node,
                          float x, float y, float height,float inset);
/* Speculative paginated BFC: source stays immutable; returned cursor/layout are owned. */
exr_status exr_flow_fragment(flow *parent,const exr_pager *source,size_t node,float width,
                            float budget,float bottom,float fixed,exr_pager **out,exr_layout **part);
exr_pager *exr_flow_cursor_clone(const exr_pager *cursor);
size_t exr_flow_cursor_size(const exr_pager *cursor);
size_t exr_flow_cursor_position(const exr_pager *cursor);
int exr_flow_cursor_finished(const exr_pager *cursor);
size_t exr_flow_cursor_floats(const exr_pager *cursor);

typedef struct exr_table_cursor exr_table_cursor;
exr_status exr_table_create(flow *f, size_t node, float x, float width, exr_table_cursor **out);
exr_status exr_table_step(flow *f, exr_table_cursor *cursor, int *done);
void exr_table_free(exr_table_cursor *cursor);
size_t exr_table_memory_size(const exr_table_cursor *cursor);
size_t exr_table_float_cursors(const exr_table_cursor *cursor);
exr_table_cursor *exr_table_clone(const exr_table_cursor *cursor);
size_t exr_table_position(const exr_table_cursor *cursor);
void exr_table_geometry(const exr_table_cursor *cursor,float *x,float *width);
#endif
