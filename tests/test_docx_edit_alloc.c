/* SPDX-License-Identifier: MIT */
/* Compile the engine once with a deterministic allocator to exercise every
   allocation failure without adding a fault-injection API to the public ABI. */
#include <exr/edit.h>
#include <stdlib.h>
#include <stdio.h>
#include <string.h>
static size_t remaining=SIZE_MAX,live=0;
static void *edit_calloc(size_t count,size_t size) {
  void *p;
  if (remaining!=SIZE_MAX) { if (!remaining) return NULL; remaining--; }
  p=calloc(count,size); if (p) live++; return p;
}
static void edit_free(void *p) { if (p) { live--; free(p); } }
#define calloc edit_calloc
#define free edit_free
#include "../src/docx_edit.c"
#undef calloc
#undef free
#define CHECK(x) do { if (!(x)) { fprintf(stderr,"allocation test line %d: %s\n",__LINE__,#x); exit(1); } } while (0)
static exr_status make(exr_edit_doc **out) {
  exr_edit_block b[2]={{0}}; exr_edit_run r[2]={{0}}; exr_edit_part p={0};
  r[0].text="abcdef"; r[0].text_size=6; r[0].id=10;
  r[1].kind=EXR_EDIT_OPAQUE_RUN; r[1].opaque_xml="<w:drawing/>"; r[1].opaque_size=12; r[1].id=11;
  b[0].id=20; b[0].runs=r; b[0].run_count=2;
  b[1].id=21; b[1].kind=EXR_EDIT_TABLE; b[1].opaque_xml="<w:tbl/>"; b[1].opaque_size=8;
  p.name="word/media/image.png"; p.data="\x89PNG\0"; p.size=5;
  return exr_edit_doc_create(NULL,0,b,2,&p,1,NULL,out);
}
static void unchanged(exr_edit_doc *d) {
  const exr_edit_block *b=exr_edit_block_at(d,0); size_t n;
  CHECK(exr_edit_block_count(d)==2 && b->id==20 && b->run_count==2 && b->runs[0].id==10);
  CHECK(!strcmp(b->runs[0].text,"abcdef") && !b->props.present && !b->runs[0].props.present);
  CHECK(b->runs[1].id==11 && !memcmp(b->runs[1].opaque_xml,"<w:drawing/>",12));
  CHECK(exr_edit_block_at(d,1)->id==21 && !memcmp(exr_edit_block_at(d,1)->opaque_xml,"<w:tbl/>",8));
  CHECK(exr_edit_sections(d,&n) && n==1);
  CHECK(exr_edit_parts(d,&n) && n==1 && !memcmp(exr_edit_parts(d,NULL)[0].data,"\x89PNG\0",5));
}
static exr_status command(exr_edit_doc *d,unsigned op) {
  exr_edit_id id; exr_edit_run r={0}; exr_edit_para_props p={0}; exr_edit_run_props rp={0};
  r.text="new"; r.text_size=3; p.present=EXR_EDIT_KEEP_NEXT; p.keep_next=1;
  rp.present=EXR_EDIT_BOLD; rp.bold=1;
  switch (op) {
    case 0: return exr_edit_insert_paragraph(d,20,&r,1,NULL,&id);
    case 1: return exr_edit_split_paragraph(d,20,0,3);
    case 2: return exr_edit_set_paragraph_props(d,20,&p);
    case 3: return exr_edit_set_run_props(d,20,0,&rp);
    default: return exr_edit_delete_block(d,20);
  }
}
static exr_status make_table_image(exr_edit_doc **out) {
  exr_edit_run run={0}; exr_edit_block p={0},blocks[2]={{0}};
  exr_edit_cell cell={0}; exr_edit_row row={0}; exr_edit_table table={0}; exr_edit_image image={0};
  int32_t width=2400;
  run.text="cell"; run.text_size=4; p.runs=&run; p.run_count=1;
  cell.blocks=&p; cell.block_count=1; cell.opaque_xml="<w:tc/>"; cell.opaque_size=7;
  row.cells=&cell; row.cell_count=1; row.opaque_xml="<w:tr/>"; row.opaque_size=7;
  table.rows=&row; table.row_count=table.column_count=1;
  table.width_twips=width; table.column_widths=&width;
  blocks[0].kind=EXR_EDIT_TABLE; blocks[0].table=&table;
  image.data="payload"; image.size=7; image.width_emu=image.height_emu=12700;
  blocks[1].kind=EXR_EDIT_IMAGE; blocks[1].image=&image;
  return exr_edit_doc_create(NULL,0,blocks,2,NULL,0,NULL,out);
}
int main(void) {
  size_t fail_at,covered=0; unsigned op,transaction;
  for (fail_at=0;fail_at<64;fail_at++) {
    exr_edit_doc *d=(exr_edit_doc *)(uintptr_t)1; exr_status s;
    remaining=fail_at; s=make(&d); remaining=SIZE_MAX;
    if (!s) { unchanged(d); exr_edit_doc_free(d); CHECK(!live); break; }
    CHECK(s==EXR_MEMORY && !d && !live); covered++;
  }
  CHECK(fail_at<64);
  /* Failed nested model copies must release partially copied rows, cells,
     paragraphs, runs and payloads, without publishing a partial document. */
  for (fail_at=0;fail_at<128;fail_at++) {
    exr_edit_doc *d=(exr_edit_doc *)(uintptr_t)1; exr_status s;
    remaining=fail_at; s=make_table_image(&d); remaining=SIZE_MAX;
    if (!s) {
      CHECK(exr_edit_block_at(d,0)->table->rows[0].cells[0].blocks[0].runs[0].text_size==4);
      CHECK(exr_edit_block_at(d,1)->image->size==7);
      exr_edit_doc_free(d); CHECK(!live); break;
    }
    CHECK(s==EXR_MEMORY && !d && !live); covered++;
  }
  CHECK(fail_at<128);
  for (transaction=0;transaction<2;transaction++) for (op=0;op<5;op++) {
    for (fail_at=0;fail_at<64;fail_at++) {
      exr_edit_doc *d=NULL; exr_edit_tx *t=NULL; exr_status s;
      CHECK(make(&d)==EXR_OK);
      if (transaction) { t=exr_edit_begin(d); CHECK(t && command(d,0)==EXR_OK); }
      remaining=fail_at; s=command(d,op); remaining=SIZE_MAX;
      if (!s) {
        if (t) CHECK(exr_edit_commit(t)==EXR_OK);
        CHECK(exr_edit_undo(d)==EXR_OK); unchanged(d);
        exr_edit_doc_free(d); CHECK(!live); break;
      }
      CHECK(s==EXR_MEMORY);
      if (t) CHECK(exr_edit_commit(t)==EXR_MEMORY);
      unchanged(d); CHECK(exr_edit_undo(d)==EXR_ARGUMENT);
      exr_edit_doc_free(d); CHECK(!live); covered++;
    }
    CHECK(fail_at<64);
  }
  for (transaction=0;transaction<2;transaction++) for (fail_at=0;fail_at<128;fail_at++) {
    exr_edit_doc *d=NULL; exr_edit_tx *t=NULL; exr_edit_id id; exr_status s;
    CHECK(make_table_image(&d)==EXR_OK);
    id=exr_edit_block_at(d,0)->table->rows[0].cells[0].blocks[0].id;
    if (transaction) { t=exr_edit_begin(d); CHECK(t); }
    remaining=fail_at; s=exr_edit_split_paragraph(d,id,0,2); remaining=SIZE_MAX;
    if (!s) {
      if (t) CHECK(exr_edit_commit(t)==EXR_OK);
      CHECK(exr_edit_block_at(d,0)->table->rows[0].cells[0].block_count==2);
      CHECK(exr_edit_undo(d)==EXR_OK);
    } else {
      CHECK(s==EXR_MEMORY);
      if (t) CHECK(exr_edit_commit(t)==EXR_MEMORY);
      covered++;
    }
    CHECK(exr_edit_block_at(d,0)->table->rows[0].cells[0].block_count==1);
    CHECK(!strcmp(exr_edit_block_at(d,0)->table->rows[0].cells[0].blocks[0].runs[0].text,"cell"));
    CHECK(exr_edit_block_at(d,0)->table->column_widths[0]==2400);
    exr_edit_doc_free(d); CHECK(!live);
    if (!s) break;
  }
  CHECK(fail_at<128);
  /* Every allocation in a cell run edit must leave both split paragraphs intact
     on failure, in automatic and explicit transactions. */
  for (transaction=0;transaction<2;transaction++) for (fail_at=0;fail_at<128;fail_at++) {
    exr_edit_doc *d=NULL; exr_edit_tx *t=NULL; exr_edit_id id,left; exr_status s;
    CHECK(make_table_image(&d)==EXR_OK);
    left=exr_edit_block_at(d,0)->table->rows[0].cells[0].blocks[0].id;
    CHECK(exr_edit_split_paragraph(d,left,0,2)==EXR_OK);
    id=exr_edit_block_at(d,0)->table->rows[0].cells[0].blocks[1].id;
    if (transaction) { t=exr_edit_begin(d); CHECK(t); }
    remaining=fail_at; s=exr_edit_set_run_text(d,id,0,"B2",2); remaining=SIZE_MAX;
    if (t) CHECK(exr_edit_commit(t)==s);
    CHECK(exr_edit_block_at(d,0)->table->rows[0].cells[0].block_count==2);
    CHECK(!strcmp(exr_edit_find_block(d,left)->runs[0].text,"ce"));
    if (!s) {
      CHECK(!strcmp(exr_edit_find_block(d,id)->runs[0].text,"B2"));
      CHECK(exr_edit_undo(d)==EXR_OK);
    } else { CHECK(s==EXR_MEMORY); covered++; }
    CHECK(!strcmp(exr_edit_find_block(d,id)->runs[0].text,"ll"));
    CHECK(exr_edit_undo(d)==EXR_OK);
    CHECK(exr_edit_block_at(d,0)->table->rows[0].cells[0].block_count==1);
    CHECK(!strcmp(exr_edit_find_block(d,left)->runs[0].text,"cell"));
    exr_edit_doc_free(d); CHECK(!live);
    if (!s) break;
  }
  CHECK(fail_at<128);
  printf("docx-edit-allocation: %zu injected failures, all atomic/rolled back, zero live allocations\n",covered);
  return 0;
}
