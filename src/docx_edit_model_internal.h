/* SPDX-License-Identifier: MIT */
#ifndef EXR_EDIT_INTERNAL_H
#define EXR_EDIT_INTERNAL_H
#include <exr/edit.h>
/* Copy before committing so borrowed input views may alias the model. */
exr_status exr_edit_ready(exr_edit_doc *d);
exr_status exr_edit_failure(exr_edit_doc *d,exr_status status);
exr_status exr_edit_replace(exr_edit_doc *d,exr_edit_id id,const exr_edit_block *view);
exr_status exr_edit_insert_block(exr_edit_doc *d,exr_edit_id after,const exr_edit_block *view,exr_edit_id *id);
#endif
