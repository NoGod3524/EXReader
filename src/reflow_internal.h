/* SPDX-License-Identifier: MIT */
#ifndef EXR_REFLOW_INTERNAL_H
#define EXR_REFLOW_INTERNAL_H
#include "layout_internal.h"
#include "exr/reflow.h"
/* Uses the existing pager LRU; edit state owns only snapshots and page tokens. */
typedef exr_status (*exr_edit_page_fn)(void *,size_t,exr_layout **,exr_error *);
exr_status exr_pager_edit_create(exr_font *,const exr_layout_config *,void *,
  exr_edit_page_fn,void (*)(void *),exr_pager **,exr_error *);
void *exr_pager_edit_state(const exr_pager *);
void exr_pager_edit_busy(exr_pager *,int);
const exr_layout_config *exr_pager_edit_config(const exr_pager *);
size_t exr_pager_edit_commit(exr_pager *,size_t,size_t,size_t,size_t,size_t,size_t);
exr_status exr_edit_shape(const exr_document *,exr_font *,const exr_layout_config *,exr_style *,
  exr_layout **,exr_error *);
#endif
