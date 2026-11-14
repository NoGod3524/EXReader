/* SPDX-License-Identifier: MIT */
#ifndef EXR_EDIT_INTERNAL_H
#define EXR_EDIT_INTERNAL_H
#include <exr/edit.h>
/* Cell edits are separate from imported vertical-merge markers. */
enum { CELL_REPLACED=1u,CELL_VMERGE_START=2u,CELL_VMERGE_CONTINUE=4u,CELL_PATCHED=8u };
int exr_edit_cell_can_split(const exr_edit_cell *cell);
exr_status exr_edit_tx_ready(exr_edit_doc *d,exr_edit_tx *tx);
/* Copy before committing so borrowed input views may alias the model. */
exr_status exr_edit_ready(exr_edit_doc *d);
exr_status exr_edit_failure(exr_edit_doc *d,exr_status status);
exr_status exr_edit_replace(exr_edit_doc *d,exr_edit_id id,const exr_edit_block *view);
exr_status exr_edit_insert_block(exr_edit_doc *d,exr_edit_id after,const exr_edit_block *view,exr_edit_id *id);
/* Atomic metadata journal; buffers may alias borrowed views. first=-1 retains. */
exr_status exr_edit_package_update(exr_edit_doc *d,size_t section,
  const exr_edit_section *value,const exr_edit_part *parts,size_t count,int first);
int exr_edit_first_override(const exr_edit_doc *d,size_t section);
int exr_edit_text_valid(const char *text,size_t size);
int exr_edit_transaction_active(const exr_edit_doc *d);
#endif
