/* SPDX-License-Identifier: MIT */
/* gcc -std=c11 -Wall -Wextra -Werror -DEXR_STATIC -Iinclude
   examples/windows/check_shell_docedit_clipboard.c src/docx_edit.c -o clipboard-check.exe */
#include <exr/edit.h>
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#ifndef DE_CLIPBOARD_TRANSPORT_ONLY
#define DE_CLIPBOARD_MODEL_ONLY
#endif
#include "shell_docedit_clipboard.inc"

static exr_edit_block paragraph(const char *s,exr_edit_run *r) {
  memset(r,0,sizeof(*r));r->text=s;r->text_size=strlen(s);
  exr_edit_block b={0};b.runs=r;b.run_count=1;return b;
}
static de_clip_pos position(exr_edit_id id,size_t byte) {
  de_clip_pos p={id,0,byte};return p;
}
static void equals(exr_edit_doc *doc,exr_edit_id id,const char *s) {
  const exr_edit_block *b=exr_edit_find_block(doc,id);
  assert(b && b->run_count==1 && !strcmp(b->runs[0].text,s));
}
int main(void) {
  exr_edit_run runs[6];exr_edit_block top[3],cells[4];
  const char *five="\xe7\x94\xb2\xe4\xb9\x99\xe4\xb8\x99\xe4\xb8\x81\xe6\x88\x8a";
  top[0]=paragraph(five,&runs[0]);top[2]=paragraph("tail",&runs[1]);
  cells[0]=paragraph("left",&runs[2]);cells[1]=paragraph("keep-left",&runs[3]);
  cells[2]=paragraph("right",&runs[4]);cells[3]=paragraph("keep-right",&runs[5]);
  runs[4].props.present=EXR_EDIT_BOLD;runs[4].props.bold=1;
  exr_edit_cell cell[2]={{0}};
  cell[0].blocks=cells;cell[0].block_count=2;cell[1].blocks=cells+2;cell[1].block_count=2;
  exr_edit_row row={0};row.cells=cell;row.cell_count=2;
  exr_edit_table table={0};table.rows=&row;table.row_count=1;table.column_count=2;
  memset(&top[1],0,sizeof(top[1]));top[1].kind=EXR_EDIT_TABLE;top[1].table=&table;
  exr_edit_doc *doc=NULL;assert(exr_edit_doc_create(NULL,0,top,3,NULL,0,NULL,&doc)==EXR_OK);
  exr_edit_id source=exr_edit_block_at(doc,0)->id,tail=exr_edit_block_at(doc,2)->id;
  const exr_edit_table *t=exr_edit_block_at(doc,1)->table;
  exr_edit_id left=t->rows[0].cells[0].blocks[0].id,keep_left=t->rows[0].cells[0].blocks[1].id;
  exr_edit_id right=t->rows[0].cells[1].blocks[0].id,keep_right=t->rows[0].cells[1].blocks[1].id;
  assert(de_clipboard_copy(doc,position(source,0),position(source,15),0));
  assert(de_clip_size==15 && !strcmp(de_clip_text,five));
  de_clip_pos p=position(tail,4);
  assert(de_clipboard_insert(doc,&p,de_clip_text,de_clip_size)==EXR_OK);
  assert(p.byte==19);equals(doc,source,five);
  puts("PASS copy five UTF-8 characters -> paste elsewhere; source retained");
  assert(de_clipboard_copy(doc,position(source,15),position(source,0),1));equals(doc,source,"");
  assert(exr_edit_undo(doc)==EXR_OK);equals(doc,source,five);
  assert(exr_edit_redo(doc)==EXR_OK);equals(doc,source,"");
  puts("PASS reversed selection cut removes source; one-step undo/redo");
  assert(de_clipboard_copy(doc,position(left,0),position(left,4),0));p=position(right,2);
  assert(de_clipboard_insert(doc,&p,de_clip_text,de_clip_size)==EXR_OK);equals(doc,right,"rileftght");
  equals(doc,keep_left,"keep-left");equals(doc,keep_right,"keep-right");
  assert(exr_edit_find_block(doc,right)->runs[0].props.bold);
  assert(exr_edit_find_block(doc,right)->runs[0].props.present&EXR_EDIT_BOLD);
  puts("PASS cell-to-cell paste retains destination bold and both sibling paragraphs");
  assert(de_clipboard_copy(doc,position(left,2),position(right,2),0));
  assert(!strcmp(de_clip_text,"ft\nkeep-left\nri"));
  assert(de_clipboard_copy(doc,position(left,2),position(right,2),1));
  equals(doc,left,"le");equals(doc,keep_left,"");equals(doc,right,"leftght");equals(doc,keep_right,"keep-right");
  assert(exr_edit_undo(doc)==EXR_OK);equals(doc,left,"left");equals(doc,keep_left,"keep-left");equals(doc,right,"rileftght");
  assert(exr_edit_block_at(doc,1)->table->rows[0].cells[0].block_count==2);
  puts("PASS cross-cell selection uses LF; cut preserves grid/paragraph IDs; atomic undo");
  /* Invalid scalar offsets and invalid external UTF-8 must leave text intact. */
  assert(exr_edit_undo(doc)==EXR_OK);assert(exr_edit_undo(doc)==EXR_OK);equals(doc,source,five);
  assert(!de_clipboard_copy(doc,position(source,1),position(source,15),1));equals(doc,source,five);
  p=position(left,1);assert(de_clipboard_insert(doc,&p,"\xff",1)==EXR_ARGUMENT);equals(doc,left,"left");
  puts("PASS invalid UTF-8 offsets/payload rejected without mutation");
  exr_edit_doc_free(doc);free(de_clip_text);puts("L04 clipboard model acceptance PASS (no GUI / no SendInput)");return 0;
}
