/* SPDX-License-Identifier: MIT */
/* M-E2a: public-API-only reproducer for typing after Enter at a cell's end. */
#include <exr/edit.h>
#include <assert.h>
#include <stdio.h>
#include <string.h>

static const exr_edit_block *paragraph(exr_edit_doc *doc,exr_edit_id table,size_t at) {
  const exr_edit_block *p=exr_edit_table_cell_paragraph(doc,table,0,0,at);
  assert(p);return p;
}
static void rollback_unchanged(exr_edit_doc *doc,exr_edit_tx *tx,const void *before,size_t size) {
  void *after=NULL;size_t n=0;exr_error error={0};
  assert(exr_edit_rollback(tx)==EXR_OK);
  assert(exr_edit_docx_write(doc,&after,&n,&error)==EXR_OK);
  assert(n==size && !memcmp(before,after,n));exr_free(after);
}
int main(void) {
  exr_edit_run run={0};run.text="AB";run.text_size=2;
  exr_edit_block p={0};p.runs=&run;p.run_count=1;
  exr_edit_cell cell={0};cell.blocks=&p;cell.block_count=1;
  exr_edit_row row={0};row.cells=&cell;row.cell_count=1;
  exr_edit_table table={0};table.rows=&row;table.row_count=table.column_count=1;
  exr_edit_block block={0};block.kind=EXR_EDIT_TABLE;block.table=&table;
  exr_edit_doc *doc=NULL,*reopened=NULL;exr_error error={0};void *bytes=NULL;size_t size=0;
  assert(exr_edit_doc_create(NULL,0,&block,1,NULL,0,NULL,&doc)==EXR_OK);
  assert(exr_edit_docx_write(doc,&bytes,&size,&error)==EXR_OK);
  assert(exr_edit_docx_read(bytes,size,NULL,&reopened,&error)==EXR_OK);
  exr_free(bytes);exr_edit_doc_free(doc);doc=reopened;
  exr_edit_id tid=0;
  for(size_t i=0;i<exr_edit_block_count(doc);i++)
    if(exr_edit_block_at(doc,i)->kind==EXR_EDIT_TABLE)tid=exr_edit_block_at(doc,i)->id;
  assert(tid);
  puts("DOCX write/read: 1x1 table text=AB");
  assert(exr_edit_split_paragraph(doc,paragraph(doc,tid,0)->id,0,1)==EXR_OK);
  exr_edit_id second=paragraph(doc,tid,1)->id;
  assert(exr_edit_find_block(doc,second));
  assert(exr_edit_set_run_text(doc,second,0,"B2",2)==EXR_OK);
  assert(!strcmp(paragraph(doc,tid,0)->runs[0].text,"A"));
  assert(!strcmp(paragraph(doc,tid,1)->runs[0].text,"B2"));
  puts("E4 fixed: find_block(second)=found; set_run_text=B2; paragraphs=2 text=A|B2");
  assert(exr_edit_split_paragraph(doc,second,0,2)==EXR_OK);
  exr_edit_id empty=paragraph(doc,tid,2)->id;
  assert(paragraph(doc,tid,2)->run_count==0);
  puts("Enter at end: paragraphs=3 text=A|B2|empty; empty.run_count=0");
  assert(exr_edit_docx_write(doc,&bytes,&size,&error)==EXR_OK);
  exr_edit_tx *tx=exr_edit_begin(doc);assert(tx);
  exr_status status=exr_edit_set_run_text(doc,empty,0,"X",1);
  assert(status==EXR_ARGUMENT);
  printf("set_run_text(empty,0,X): EXR_ARGUMENT (%d)\n",status);
  rollback_unchanged(doc,tx,bytes,size);
  tx=exr_edit_begin(doc);assert(tx);exr_edit_id inserted=0;
  run.text="X";run.text_size=1;
  status=exr_edit_insert_paragraph(doc,empty,&run,1,NULL,&inserted);
  assert(status==EXR_ARGUMENT && !inserted);
  printf("insert_paragraph(after empty cell paragraph): EXR_ARGUMENT (%d)\n",status);
  rollback_unchanged(doc,tx,bytes,size);
  tx=exr_edit_begin(doc);assert(tx);
  assert(exr_edit_table_set_cell_text(doc,tid,0,0,&run,1)==EXR_OK);
  assert(exr_edit_table_cell_block_count(doc,tid,0,0)==1);
  assert(!strcmp(paragraph(doc,tid,0)->runs[0].text,"X"));
  puts("set_cell_text fallback: paragraphs=1 text=X; A and B2 lost");
  rollback_unchanged(doc,tx,bytes,size);exr_free(bytes);
  assert(exr_edit_table_cell_block_count(doc,tid,0,0)==3);
  assert(exr_edit_find_block(doc,empty)->run_count==0);
  puts("Rollback: all 3 paragraphs and IDs retained; DOCX bytes unchanged");
  puts("M-E2a BLOCKED: need insertion into a zero-run cell paragraph, preserving siblings/templates/history");
  exr_edit_doc_free(doc);return 0;
}
