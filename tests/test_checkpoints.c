/* SPDX-License-Identifier: GPL-3.0-only */
#include "exreader.h"
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static exr_error error;
static unsigned checks;
#define CHECK(x) do { checks++; if(!(x)) { fprintf(stderr,"line %d: %s (%d: %s)\n", \
 __LINE__,#x,(int)error.code,error.message); exit(1); } } while(0)
#define OK(x) CHECK((x)==EXR_OK)
static int near(float a,float b) { return fabsf(a-b)<0.001f; }
static exr_layout_config config(void) {
  exr_layout_config c=exr_layout_config_defaults();
  c.page=(exr_layout_options){120,96,8,20,1.2f,0}; return c;
}
static exr_document *text_document(const char *pattern) {
  size_t n=strlen(pattern), i; char *text=malloc(n*1024+1); exr_document *doc=NULL;
  exr_attribute style={"style","margin:0;width:72px"};
  exr_node_input nodes[]={
    {EXR_NODE_DOCUMENT,SIZE_MAX,NULL,NULL,NULL,0}, {EXR_NODE_CHAPTER,0,NULL,NULL,NULL,0},
    {EXR_NODE_PARAGRAPH,1,NULL,NULL,&style,1}, {EXR_NODE_TEXT,2,NULL,NULL,NULL,0}};
  exr_chapter_input chapter={"long","long.unit",1,1};
  exr_document_input input={"Checkpoint",nodes,4,&chapter,1,NULL,0};
  CHECK(text); for(i=0;i<1024;i++) memcpy(text+i*n,pattern,n); text[n*1024]=0;
  nodes[3].text=text; OK(exr_document_create(&input,&doc,&error)); free(text); return doc;
}
static exr_document *table_document(void) {
  exr_document *doc=NULL; size_t row, used=3;
  exr_node_input *nodes=calloc(3+160*3,sizeof(*nodes));
  exr_attribute span={"rowspan","2"};
  exr_chapter_input chapter={"table","table.unit",1,1};
  exr_document_input input={"Checkpoint table",nodes,0,&chapter,1,NULL,0};
  CHECK(nodes);
  nodes[0]=(exr_node_input){EXR_NODE_DOCUMENT,SIZE_MAX,NULL,NULL,NULL,0};
  nodes[1]=(exr_node_input){EXR_NODE_CHAPTER,0,NULL,NULL,NULL,0};
  nodes[2]=(exr_node_input){EXR_NODE_TABLE,1,NULL,NULL,NULL,0};
  for(row=0;row<160;row++) {
    nodes[used]=(exr_node_input){EXR_NODE_ROW,2,NULL,NULL,NULL,0};
    nodes[used+1]=(exr_node_input){EXR_NODE_CELL,used,NULL,NULL,row%4==0 ? &span:NULL,row%4==0 ? 1u:0u};
    nodes[used+2]=(exr_node_input){EXR_NODE_TEXT,used+1,NULL,"A",NULL,0}; used+=3;
  }
  input.node_count=used; OK(exr_document_create(&input,&doc,&error)); free(nodes); return doc;
}
static void same_page(const exr_layout *a,const exr_layout *b) {
  const exr_glyph *ag,*bg; const exr_line *al,*bl; const exr_page *ap,*bp;
  const exr_box *ab,*bb; exr_bitmap x={0},y={0}; size_t n,m,i;
  ap=exr_layout_pages(a,&n); bp=exr_layout_pages(b,&m); CHECK(n==1 && m==1);
  CHECK(ap->start==bp->start && ap->end==bp->end && ap->line_count==bp->line_count);
  ag=exr_layout_glyphs(a,&n); bg=exr_layout_glyphs(b,&m); CHECK(n==m);
  for(i=0;i<n;i++) {
    CHECK(ag[i].glyph==bg[i].glyph && ag[i].font_index==bg[i].font_index);
    CHECK(ag[i].start==bg[i].start && ag[i].end==bg[i].end && ag[i].node==bg[i].node);
    CHECK(ag[i].cluster_start==bg[i].cluster_start && ag[i].cluster_end==bg[i].cluster_end);
    CHECK(ag[i].flags==bg[i].flags && ag[i].bidi_level==bg[i].bidi_level);
    CHECK(near(ag[i].x,bg[i].x) && near(ag[i].baseline,bg[i].baseline));
    CHECK(near(ag[i].advance,bg[i].advance) && near(ag[i].offset_x,bg[i].offset_x) && near(ag[i].offset_y,bg[i].offset_y));
  }
  al=exr_layout_lines(a,&n); bl=exr_layout_lines(b,&m); CHECK(n==m);
  for(i=0;i<n;i++) {
    CHECK(al[i].start==bl[i].start && al[i].end==bl[i].end && al[i].glyph_count==bl[i].glyph_count);
    CHECK(near(al[i].x,bl[i].x) && near(al[i].y,bl[i].y) && near(al[i].width,bl[i].width) && near(al[i].height,bl[i].height));
  }
  ab=exr_layout_boxes(a,&n); bb=exr_layout_boxes(b,&m); CHECK(n==m);
  for(i=0;i<n;i++) {
    CHECK(ab[i].kind==bb[i].kind && ab[i].node==bb[i].node);
    CHECK(near(ab[i].x,bb[i].x) && near(ab[i].y,bb[i].y) && near(ab[i].width,bb[i].width) && near(ab[i].height,bb[i].height));
  }
  OK(exr_render_page_color(a,NULL,0,&x,&error)); OK(exr_render_page_color(b,NULL,0,&y,&error));
  CHECK(x.stride==y.stride && x.height==y.height);
  CHECK(!memcmp(x.pixels,y.pixels,(size_t)x.stride*x.height));
  exr_bitmap_free(&x); exr_bitmap_free(&y);
}
static void replay(exr_document *doc,exr_font *font,size_t far) {
  exr_layout_config c=config(); exr_pager *fast=NULL,*slow=NULL;
  const exr_layout *a=NULL,*b=NULL; exr_pager_stats before,after,baseline;
  size_t i, targets[]={0,1,17,3,31,7,15,23};
  OK(exr_pager_create(doc,font,&c,&fast,&error)); OK(exr_pager_create(doc,font,&c,&slow,&error));
  OK(exr_pager_set_checkpoints(fast,64,16*1024*1024,4,&error));
  OK(exr_pager_set_checkpoints(slow,0,0,0,&error));
  OK(exr_pager_get(fast,far,&a,&error)); OK(exr_pager_get(slow,far,&b,&error)); same_page(a,b);
  before=exr_pager_statistics(fast); CHECK(before.checkpoint_count>0);
  CHECK(before.checkpoint_bytes>0 && before.checkpoint_bytes<=16*1024*1024);
  baseline=exr_pager_statistics(slow);
  OK(exr_pager_get(fast,far-3,&a,&error)); OK(exr_pager_get(slow,far-3,&b,&error)); same_page(a,b);
  after=exr_pager_statistics(fast);
  CHECK(after.restored_checkpoints==before.restored_checkpoints+1);
  CHECK(after.generated_pages-before.generated_pages<=4);
  CHECK(exr_pager_statistics(slow).generated_pages-baseline.generated_pages==far-2);
  for(i=0;i<sizeof(targets)/sizeof(*targets);i++) {
    OK(exr_pager_get(fast,targets[i],&a,&error)); OK(exr_pager_get(slow,targets[i],&b,&error)); same_page(a,b);
  }
  OK(exr_pager_set_checkpoints(fast,1,1,1,&error));
  CHECK(!exr_pager_statistics(fast).checkpoint_count && !exr_pager_statistics(fast).checkpoint_bytes);
  OK(exr_pager_get(fast,far,&a,&error)); OK(exr_pager_get(slow,far,&b,&error)); same_page(a,b);
  CHECK(!exr_pager_statistics(fast).checkpoint_count);
  OK(exr_pager_set_checkpoints(fast,0,0,0,&error));
  CHECK(exr_pager_set_checkpoints(fast,65,1024,1,&error)==EXR_ARGUMENT);
  CHECK(exr_pager_set_checkpoints(fast,1,0,1,&error)==EXR_ARGUMENT);
  CHECK(exr_pager_set_checkpoints(fast,1,1024,0,&error)==EXR_ARGUMENT);
  CHECK(exr_pager_set_checkpoints(NULL,1,1024,1,&error)==EXR_ARGUMENT);
  CHECK(!exr_pager_statistics(NULL).generated_pages);
  exr_pager_free(fast); exr_pager_free(slow); exr_document_free(doc);
}
static void default_and_embedded(const char *directory,exr_font *font) {
  exr_document *doc=text_document("AV fi a "); exr_layout_config c=config();
  exr_pager *p=NULL,*slow=NULL; const exr_layout *a=NULL,*b=NULL;
  exr_pager_stats before,after; char path[4096]; exr_layout *whole=NULL; size_t pages;
  OK(exr_pager_create(doc,font,&c,&p,&error)); OK(exr_pager_get(p,40,&a,&error));
  before=exr_pager_statistics(p); CHECK(before.checkpoint_count>0 && before.checkpoint_count<=4);
  CHECK(before.checkpoint_bytes<=2*1024*1024);
  OK(exr_pager_get(p,37,&a,&error)); after=exr_pager_statistics(p);
  CHECK(after.restored_checkpoints==1 && after.generated_pages-before.generated_pages<=16);
  exr_pager_free(p); exr_document_free(doc);
  CHECK(snprintf(path,sizeof(path),"%s/font-book.epub",directory)>0);
  OK(exr_document_open(path,&doc,&error)); c.page.height=64;
  OK(exr_layout_create_ex(doc,font,&c,&whole,&error)); exr_layout_pages(whole,&pages);
  CHECK(pages>=3); exr_layout_free(whole);
  OK(exr_pager_create(doc,font,&c,&p,&error)); OK(exr_pager_create(doc,font,&c,&slow,&error));
  OK(exr_pager_set_checkpoints(p,16,1024*1024,1,&error));
  OK(exr_pager_set_checkpoints(slow,0,0,0,&error));
  OK(exr_pager_get(p,pages-1,&a,&error)); OK(exr_pager_get(slow,pages-1,&b,&error)); same_page(a,b);
  OK(exr_pager_get(p,0,&a,&error)); OK(exr_pager_get(slow,0,&b,&error)); same_page(a,b);
  OK(exr_pager_get(p,pages-1,&a,&error)); OK(exr_pager_get(slow,pages-1,&b,&error)); same_page(a,b);
  CHECK(exr_pager_statistics(p).restored_checkpoints>0);
  exr_pager_free(p); exr_pager_free(slow); exr_document_free(doc);
}
int main(int argc,char **argv) {
  char path[4096]; exr_font *font=NULL;
  CHECK(argc==2); CHECK(snprintf(path,sizeof(path),"%s/shaping/shaping.ttf",argv[1])>0);
  OK(exr_font_open(path,&font,&error));
  replay(text_document("AV fi a "),font,40);
  replay(text_document("A \xd8\xa8\xd8\xa8 \xd7\x90\xd7\x91 12 "),font,40);
  replay(table_document(),font,32);
  default_and_embedded(argv[1],font);
  exr_font_free(font); printf("Checkpoints: %u checks passed\n",checks); return 0;
}
