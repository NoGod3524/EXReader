/* SPDX-License-Identifier: MIT */
/* Shared by the native table editor and its console acceptance. */
static exr_status de_table_text(exr_edit_doc *doc,exr_edit_id table,size_t row,size_t col,
    const char *text,size_t size) {
  exr_edit_tx *tx=exr_edit_begin(doc);
  exr_edit_run run={0};exr_status status;
  if(!tx)return EXR_MEMORY;
  const exr_edit_block *old=exr_edit_table_cell_paragraph(doc,table,row,col,0);
  if(!old) {exr_edit_rollback(tx);return EXR_UNSUPPORTED;}
  exr_edit_id first=old->id;
  if(old->run_count)run.props=old->runs[0].props;
  run.text=text;run.text_size=size;
  if(!old->run_count) {
    exr_edit_para_props props=old->props;
    status=exr_edit_insert_paragraph(doc,first,&run,1,&props,&first);
    if(status==EXR_OK) {
      old=exr_edit_table_cell_paragraph(doc,table,row,col,0);
      status=exr_edit_delete_block(doc,old->id);
    }
  } else {
    size_t count=old->run_count;
    status=exr_edit_set_run_text(doc,first,0,text,size);
    for(size_t i=1;status==EXR_OK && i<count;i++)status=exr_edit_set_run_text(doc,first,i,NULL,0);
  }
  size_t count=exr_edit_table_cell_block_count(doc,table,row,col);
  while(status==EXR_OK && count>1) {
    old=exr_edit_table_cell_block_at(doc,table,row,col,--count);
    status=exr_edit_delete_block(doc,old->id);
  }
  /* Split from the end so every offset still refers to the original prefix.
     Enter plus the following typing is one committed model transaction. */
  for(size_t i=size;status==EXR_OK && i;i--)if(text[i-1]=='\n') {
    const exr_edit_block *p=exr_edit_table_cell_paragraph(doc,table,row,col,0);
    if(!p) {status=EXR_UNSUPPORTED;break;}
    exr_edit_id id=p->id;
    status=exr_edit_split_paragraph(doc,id,0,i);
    if(status==EXR_OK)status=exr_edit_set_run_text(doc,id,0,text,i-1);
  }
  if(status==EXR_OK)return exr_edit_commit(tx);
  exr_edit_rollback(tx);return status;
}
static exr_status de_table_width(exr_edit_doc *doc,exr_edit_id table,size_t col,int delta) {
  const exr_edit_block *b=exr_edit_find_block(doc,table);
  if(!b || !b->table || col>=b->table->column_count)return EXR_ARGUMENT;
  int64_t width=b->table->column_widths ? b->table->column_widths[col]:
    b->table->width_twips/(int32_t)b->table->column_count;
  width+=delta;
  if(width<=0 || width>INT32_MAX)return EXR_ARGUMENT;
  exr_edit_tx *tx=exr_edit_begin(doc);if(!tx)return EXR_MEMORY;
  exr_status status=exr_edit_table_set_column_width(doc,tx,table,col,(int32_t)width);
  if(status==EXR_OK)return exr_edit_commit(tx);
  exr_edit_rollback(tx);return status;
}
