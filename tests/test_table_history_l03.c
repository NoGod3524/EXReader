/* SPDX-License-Identifier: MIT */
#include <exr/edit.h>
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "../examples/windows/shell_docedit_table_history.h"

static exr_edit_doc *snapshot(exr_edit_doc *doc) {
  exr_edit_doc *copy=NULL;
  const exr_edit_block *b=exr_edit_block_at(doc,0);
  size_t count;const exr_edit_section *sections=exr_edit_sections(doc,&count);
  assert(exr_edit_doc_create(sections,count,b,1,NULL,0,NULL,&copy)==EXR_OK);return copy;
}
static void same_block(const exr_edit_block *a,const exr_edit_block *b) {
  assert(a->id==b->id && a->section_id==b->section_id && a->kind==b->kind);
  assert(!memcmp(&a->props,&b->props,sizeof(a->props)));
  assert(a->opaque_size==b->opaque_size);
  if(a->opaque_size)assert(!memcmp(a->opaque_xml,b->opaque_xml,a->opaque_size));
  assert(a->run_count==b->run_count);
  for(size_t i=0;i<a->run_count;i++) {
    const exr_edit_run *x=&a->runs[i],*y=&b->runs[i];
    assert(x->id==y->id && x->kind==y->kind && x->text_size==y->text_size);
    assert(!memcmp(&x->props,&y->props,sizeof(x->props)));
    if(x->text_size)assert(!memcmp(x->text,y->text,x->text_size));
    assert(x->opaque_size==y->opaque_size);
    if(x->opaque_size)assert(!memcmp(x->opaque_xml,y->opaque_xml,x->opaque_size));
  }
}
static void same(exr_edit_doc *a,exr_edit_doc *b) {
  const exr_edit_block *x=exr_edit_block_at(a,0),*y=exr_edit_block_at(b,0);
  same_block(x,y);
  const exr_edit_table *s=x->table,*t=y->table;
  assert(s->row_count==t->row_count && s->column_count==t->column_count);
  assert(s->width_twips==t->width_twips && s->changed==t->changed && s->borders==t->borders);
  assert(!!s->column_widths==!!t->column_widths);
  if(s->column_widths)assert(!memcmp(s->column_widths,t->column_widths,s->column_count*sizeof(int32_t)));
  for(size_t i=0;i<s->row_count;i++) {
    const exr_edit_row *r=&s->rows[i],*q=&t->rows[i];
    assert(r->id==q->id && r->cell_count==q->cell_count && r->source_index==q->source_index);
    assert(r->opaque_size==q->opaque_size);
    if(r->opaque_size)assert(!memcmp(r->opaque_xml,q->opaque_xml,r->opaque_size));
    for(size_t j=0;j<r->cell_count;j++) {
      const exr_edit_cell *c=&r->cells[j],*d=&q->cells[j];
      assert(c->id==d->id && c->block_count==d->block_count && c->changed==d->changed && c->unsupported==d->unsupported);
      assert(c->opaque_size==d->opaque_size);
      if(c->opaque_size)assert(!memcmp(c->opaque_xml,d->opaque_xml,c->opaque_size));
      for(size_t k=0;k<c->block_count;k++)same_block(&c->blocks[k],&d->blocks[k]);
    }
  }
}
int main(void) {
  exr_edit_run run={0};run.text="seed";run.text_size=4;
  run.props.present=EXR_EDIT_BOLD;run.props.bold=1;
  exr_edit_block para={0};para.runs=&run;para.run_count=1;
  exr_edit_cell cells[2]={{0}};
  cells[0].blocks=cells[1].blocks=&para;cells[0].block_count=cells[1].block_count=1;
  exr_edit_row row={0};row.cells=cells;row.cell_count=2;
  int32_t widths[]={2000,2000};
  exr_edit_table table={0};table.rows=&row;table.row_count=1;table.column_count=2;
  table.width_twips=4000;table.column_widths=widths;
  exr_edit_block block={0};block.kind=EXR_EDIT_TABLE;block.table=&table;
  exr_edit_doc *doc=NULL,*states[4];
  assert(exr_edit_doc_create(NULL,0,&block,1,NULL,0,NULL,&doc)==EXR_OK);
  exr_edit_id id=exr_edit_block_at(doc,0)->id;states[0]=snapshot(doc);
  assert(exr_edit_table_insert_row(doc,id,0)==EXR_OK);states[1]=snapshot(doc);
  assert(de_table_text(doc,id,1,0,"A\xe4\xb8\xad\nB\xf0\x9f\x99\x82",10)==EXR_OK);
  assert(exr_edit_table_cell_block_count(doc,id,1,0)==2);states[2]=snapshot(doc);
  assert(de_table_width(doc,id,0,120)==EXR_OK);states[3]=snapshot(doc);
  for(int i=2;i>=0;i--) {assert(exr_edit_undo(doc)==EXR_OK);same(doc,states[i]);printf("undo %d: text/structure/IDs/templates equal PASS\n",3-i);}
  assert(exr_edit_undo(doc)==EXR_ARGUMENT);
  for(int i=1;i<=3;i++) {assert(exr_edit_redo(doc)==EXR_OK);same(doc,states[i]);printf("redo %d: text/structure/IDs/templates equal PASS\n",i);}
  assert(exr_edit_redo(doc)==EXR_ARGUMENT);
  assert(exr_edit_table_delete_row(doc,id,1)==EXR_OK);
  exr_edit_doc *deleted=snapshot(doc);
  assert(exr_edit_undo(doc)==EXR_OK);same(doc,states[3]);
  assert(exr_edit_redo(doc)==EXR_OK);same(doc,deleted);
  assert(exr_edit_undo(doc)==EXR_OK);
  assert(de_table_width(doc,id,0,-100000)==EXR_ARGUMENT);same(doc,states[3]);
  assert(exr_edit_redo(doc)==EXR_OK); /* rejected operation preserves redo */
  puts("delete-row undo/redo; rejected width preserves redo PASS");
  assert(exr_edit_undo(doc)==EXR_OK);
  assert(de_table_text(doc,id,1,0,"branch",6)==EXR_OK);
  assert(exr_edit_redo(doc)==EXR_ARGUMENT);
  for(int i=0;i<4;i++)exr_edit_doc_free(states[i]);
  exr_edit_doc_free(deleted);exr_edit_doc_free(doc);
  puts("L03 table history acceptance PASS (no HWND / no SendInput)");return 0;
}
