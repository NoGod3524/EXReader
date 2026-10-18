/* SPDX-License-Identifier: GPL-3.0-only */
#ifndef EXR_DISPLAY_BIDI_INTERNAL_H
#define EXR_DISPLAY_BIDI_INTERNAL_H
#include "layout_internal.h"
#include "bidi_internal.h"

#define EXR_DISPLAY_GENERATED 32u
typedef struct {
  exr_bidi *bidi;
  size_t *sources,count,capacity;
  unsigned char *boundaries;
} exr_display_view;
typedef struct {
  exr_buffer text;
  size_t *sources,count,capacity;
  unsigned char *flags;
  const exr_control *control;
} exr_display_builder;
typedef struct {
  size_t start,end,offset,size;
  unsigned kind; /* 0: borrowed original bytes, 1: generated, 2: fixed source. */
} exr_display_piece;
typedef struct exr_display_patch {
  size_t refs,start,end,count,bytes,total,depth;
  struct exr_display_patch *previous;
  exr_display_piece *pieces;
  char *text;
} exr_display_patch;
typedef struct {
  exr_display_patch *history,*pending;
  exr_display_patch *context,*pending_context;
  exr_display_view *active,*trial;
  size_t first_node,line_first,line_count,tail_first;
  int record_pending;
  int window_safe,pending_unsafe;
} exr_display_state;

void exr_display_builder_clear(exr_display_builder *builder);
exr_status exr_display_append(exr_display_builder *builder,const char *text,size_t size,
                               size_t source,int fixed,int generated,exr_error *error);
exr_status exr_display_finish(exr_display_builder *builder,exr_direction direction,const exr_bidi_override *overrides,
                               exr_display_view **out,exr_error *error);
void exr_display_view_free(exr_display_view *view);
exr_status exr_display_apply(const exr_display_view *view,exr_glyph *glyphs,size_t count,
                              size_t first,exr_error *error);
exr_status exr_display_apply_line(const exr_display_view *view,exr_glyph *glyphs,size_t count,
                                   size_t first,size_t scalars,exr_error *error);
size_t exr_display_original(const exr_display_view *view,size_t source);
exr_status exr_display_patch_create(const exr_document *document,const exr_glyph *glyphs,
                                     size_t count,exr_display_patch *previous,
                                     exr_display_patch **out,exr_error *error);
exr_status exr_display_patch_append(exr_display_builder *builder,const exr_document *document,
                                     const exr_display_patch *patch,exr_error *error);
void exr_display_patch_free(exr_display_patch *patch);
void exr_display_state_free(exr_display_state *state);
exr_display_state *exr_display_state_clone(const exr_display_state *state);
size_t exr_display_state_size(const exr_display_state *state);
#endif
