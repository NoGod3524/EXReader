/* SPDX-License-Identifier: MIT */
/* Headless reproducer: Enter succeeds, but subsequent cell typing lacks an API. */
#include <exr/edit.h>
#include <assert.h>
#include <stdio.h>
#include <string.h>

int main(void) {
  exr_edit_run run={0};run.text="AB";run.text_size=2;
  exr_edit_block paragraph={0};paragraph.runs=&run;paragraph.run_count=1;
  exr_edit_cell cell={0};cell.blocks=&paragraph;cell.block_count=1;
  exr_edit_row row={0};row.cells=&cell;row.cell_count=1;
  exr_edit_table table={0};table.rows=&row;table.row_count=table.column_count=1;
  exr_edit_block block={0};block.kind=EXR_EDIT_TABLE;block.table=&table;
  exr_edit_doc *doc=NULL;
  assert(exr_edit_doc_create(NULL,0,&block,1,NULL,0,NULL,&doc)==EXR_OK);
  exr_edit_id id=exr_edit_block_at(doc,0)->id;
  const exr_edit_block *p=exr_edit_table_cell_paragraph(doc,id,0,0,0);assert(p);
  exr_edit_tx *tx=exr_edit_begin(doc);assert(tx);
  assert(exr_edit_split_paragraph(doc,p->id,0,1)==EXR_OK);
  assert(exr_edit_commit(tx)==EXR_OK);
  p=exr_edit_table_cell_paragraph(doc,id,0,0,1);assert(p);
  assert(!strcmp(p->runs[0].text,"B"));
  printf("Enter: paragraphs=%zu text=A|B\n",exr_edit_block_at(doc,0)->table->rows[0].cells[0].block_count);
  printf("find_block(cell_paragraph_id): %s\n",exr_edit_find_block(doc,p->id) ? "found":"NULL");
  tx=exr_edit_begin(doc);assert(tx);
  exr_status status=exr_edit_set_run_text(doc,p->id,0,"XB",2);
  assert(status==EXR_ARGUMENT);assert(exr_edit_rollback(tx)==EXR_OK);
  printf("set_run_text(cell_paragraph_id): EXR_ARGUMENT (%d)\n",status);
  run.text="XB";run.text_size=2;
  tx=exr_edit_begin(doc);assert(tx);
  assert(exr_edit_table_set_cell_text(doc,id,0,0,&run,1)==EXR_OK);
  assert(exr_edit_commit(tx)==EXR_OK);
  cell=exr_edit_block_at(doc,0)->table->rows[0].cells[0];
  assert(cell.block_count==1 && !strcmp(cell.blocks[0].runs[0].text,"XB"));
  printf("set_cell_text fallback: paragraphs=%zu text=XB (A paragraph lost)\n",cell.block_count);
  assert(exr_edit_undo(doc)==EXR_OK);
  assert(exr_edit_block_at(doc,0)->table->rows[0].cells[0].block_count==2);
  puts("M-E2a BLOCKED: need paragraph-scoped cell text editing, including empty paragraphs");
  exr_edit_doc_free(doc);return 0;
}
