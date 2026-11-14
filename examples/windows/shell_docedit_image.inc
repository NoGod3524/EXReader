/* SPDX-License-Identifier: MIT */
/* Include after shell_docedit.inc. The host owns de.selected_block and resets
   it to SIZE_MAX on open, caret navigation, undo/redo and document close. */
#include <exr/graphics.h>

static int de_image_at_caret(void) {
  const exr_edit_block *b=de.doc ? exr_edit_block_at(de.doc,de.caret_block):NULL;
  return b && b->kind==EXR_EDIT_IMAGE;
}

static int de_image_insert(const char *path) {
  if(!de.doc || !path || !*path)return 0;
  const exr_edit_block *b=exr_edit_block_at(de.doc,de.caret_block);
  if(!b || b->kind!=EXR_EDIT_PARAGRAPH) {
    set_status(L"请将光标放在要插入图片的段落中。");return 0;
  }
  exr_edit_id after=b->id,id=0;
  wchar_t *wide=host_wide(path,strlen(path));
  FILE *file=wide ? _wfopen(wide,L"rb"):NULL;free(wide);
  if(!file) {set_status(L"无法打开图片文件。");return 0;}
  void *bytes=NULL;long length=0;uint32_t width=0,height=0;
  exr_status status=EXR_IO;
  if(!fseek(file,0,SEEK_END) && (length=ftell(file))>0 && !fseek(file,0,SEEK_SET)) {
    /* Bound the UI's file buffer to 64 MiB before allocating it. */
    if((unsigned long)length>64u*1024u*1024u)status=EXR_LIMIT;
    else {
      bytes=malloc((size_t)length);status=bytes ? EXR_IO:EXR_MEMORY;
      if(bytes && fread(bytes,1,(size_t)length,file)==(size_t)length)
        status=exr_image_page_dimensions(bytes,(size_t)length,0,&width,&height,NULL);
    }
  }
  fclose(file);
  if(status==EXR_OK) {
    exr_edit_tx *tx=exr_edit_begin(de.doc);status=tx ? EXR_OK:EXR_MEMORY;
    if(tx) {
      /* The UI uses 96 DPI; the image API takes points (72 per inch). */
      status=exr_edit_insert_image(de.doc,after,bytes,(size_t)length,width*.75,height*.75,&id);
      if(status==EXR_OK)status=exr_edit_commit(tx);else exr_edit_rollback(tx);
    }
  }
  free(bytes);
  if(status!=EXR_OK) {de_error(L"无法插入图片",status,NULL);return 0;}
  size_t index=0;
  while(index<exr_edit_block_count(de.doc) && exr_edit_block_at(de.doc,index)->id!=id)index++;
  de_set_caret(de_start(index));de_set_anchor(de_caret());de.selected_block=index;
  memset(&de.pending_props,0,sizeof(de.pending_props));
  de.dirty=1;de.layout_dirty=1;de_refresh(1);return 1;
}

static int de_image_delete_selected(void) {
  if(!de.doc || de.selected_block==SIZE_MAX)return 0;
  size_t index=de.selected_block;
  const exr_edit_block *b=exr_edit_block_at(de.doc,index);
  if(!b || b->kind!=EXR_EDIT_IMAGE)return 0;
  exr_edit_id id=b->id;
  exr_edit_tx *tx=exr_edit_begin(de.doc);exr_status status=tx ? EXR_OK:EXR_MEMORY;
  if(tx) {
    status=exr_edit_delete_image(de.doc,id);
    if(status==EXR_OK)status=exr_edit_commit(tx);else exr_edit_rollback(tx);
  }
  if(status!=EXR_OK) {de_error(L"无法删除图片",status,NULL);return 0;}
  de.selected_block=SIZE_MAX;
  de_set_caret(de_normalize(de_start(index)));de_set_anchor(de_caret());
  memset(&de.pending_props,0,sizeof(de.pending_props));
  de.dirty=1;de.layout_dirty=1;de_refresh(1);return 1;
}
