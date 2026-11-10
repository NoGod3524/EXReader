/* SPDX-License-Identifier: MIT */
#ifndef EXR_REFLOW_H
#define EXR_REFLOW_H
#include "edit.h"
#include "layout.h"
#ifdef __cplusplus
extern "C" {
#endif
/* Snapshot-based editing pager. The model must outlive the pager. All successful
   commands, transactions, undo and redo are detected at layout_after, including
   disjoint changes; changed_block_id is an optional hint (0 = automatic).
   Paragraphs and explicit page breaks are supported. Opaque runs/tables and
   numbering, keep-next and user CSS return EXR_UNSUPPORTED.
   The host config supplies viewport geometry. Section paper sizes are not used.
   No borrowed page is valid across a successful layout_after call.
   layout_after also accepts a replacement model with preserved IDs (decoder
   snapshots); after success it replaces the model bound to this pager. */
EXR_API exr_status exr_edit_pager_create(exr_edit_doc *doc,exr_font *font,
  const exr_layout_config *config,exr_pager **out,exr_error *error);
EXR_API exr_status exr_edit_layout_after(exr_edit_doc *doc,exr_pager *pager,
  exr_edit_id changed_block_id,size_t *pages_repaginated,exr_error *error);
typedef struct {
  exr_edit_id first_block_id,last_block_id;
  size_t old_first,old_end,new_first,new_end; /* Half-open block order, NOT numeric ID order. */
  size_t first_page,end_page; /* Old half-open dirty page range, before propagation. */
} exr_edit_dirty_range;
typedef struct {
  size_t revision,page_count,pages_repaginated,pages_reused,cache_invalidated;
  exr_edit_dirty_range dirty;
} exr_edit_reflow_stats;
EXR_API exr_edit_reflow_stats exr_edit_reflow_statistics(const exr_pager *pager);
/* byte_offset is UTF-8 within the concatenated runs of block_id. page_offset is
   the corresponding page-local source-byte offset, suitable for the host's
   own scroll restoration. Reflow pages/glyphs use concatenated model bytes,
   with one separator byte per block; glyph.node is the stable block ID.
   Capture before editing; resolve after the next successful layout_after.
   Resolve accepts the current or immediately preceding revision only.
   Text inserted at the caret uses right affinity. Deleted text clamps to the
   replacement end; a deleted block falls forward, then backward at EOF.
   Hosts retain their pixel displacement from this text anchor themselves. */
typedef struct {
  size_t page_index,byte_offset,page_offset,revision;
  exr_edit_id block_id;
} exr_edit_view_anchor;
EXR_API exr_status exr_edit_anchor_capture(const exr_pager *pager,size_t page_index,
  exr_edit_id block_id,size_t byte_offset,exr_edit_view_anchor *out,exr_error *error);
EXR_API exr_status exr_edit_anchor_restore(const exr_pager *pager,
  const exr_edit_view_anchor *before,exr_edit_view_anchor *out,exr_error *error);
#ifdef __cplusplus
}
#endif
#endif
