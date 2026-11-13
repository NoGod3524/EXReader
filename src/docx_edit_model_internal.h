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
#endif
