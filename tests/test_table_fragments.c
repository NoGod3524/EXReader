/* SPDX-License-Identifier: GPL-3.0-only */
#include "exreader.h"
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static unsigned checks;
static exr_error error;
static exr_font *font;
#define CHECK(x) do { checks++;if(!(x)) { fprintf(stderr,"line %d: %s (%d: %s)\n",__LINE__,#x,error.code,error.message);exit(1); } } while(0)
#define OK(x) CHECK((x)==EXR_OK)
static int near(float a,float b) { return fabsf(a-b)<.04f; }
static exr_layout_config config(void) {
  exr_layout_config c=exr_layout_config_defaults();c.page=(exr_layout_options){180,100,10,14,20.f/14,0};
  c.user_css="html,body,p,table,tr,td {margin:0;padding:0;font-size:14px;line-height:20px}";return c;
}
static void positioned(exr_document *d,const exr_layout *l,const exr_layout_config *config) {
  size_t np,nl,ng,nb,i,at=0;const exr_page *p=exr_layout_pages(l,&np);const exr_line *lines=exr_layout_lines(l,&nl);
  const exr_glyph *glyphs=exr_layout_glyphs(l,&ng);const exr_box *boxes=exr_layout_boxes(l,&nb);
  exr_positioned_page *pages=calloc(np,sizeof(*pages));exr_paint *paints=calloc(ng+nb+1,sizeof(*paints));exr_layout *copy=NULL;
  exr_positioned_input input={0};exr_layout_config c=*config;CHECK(pages && paints);
  for(i=0;i<np;i++) {
    size_t j;pages[i].width=config->page.width;pages[i].height=config->page.height;pages[i].content=p[i];pages[i].paint_start=at;
    for(j=p[i].box_start;j<p[i].box_start+p[i].box_count;j++) paints[at++]=(exr_paint){EXR_PAINT_BOX,0,j};
    for(j=p[i].line_start;j<p[i].line_start+p[i].line_count;j++) {
      size_t k;for(k=lines[j].glyph_start;k<lines[j].glyph_start+lines[j].glyph_count;k++) paints[at++]=(exr_paint){EXR_PAINT_GLYPH,0,k};
    }
    pages[i].paint_count=at-pages[i].paint_start;
  }
  input.struct_size=sizeof(input);input.pages=pages;input.page_count=np;input.lines=lines;input.line_count=nl;
  input.glyphs=glyphs;input.glyph_count=ng;input.boxes=boxes;input.box_count=nb;input.paints=paints;input.paint_count=at;
  c.page.margin=0;OK(exr_layout_create_positioned(d,font,&input,&c,&copy,&error));
  for(i=0;i<np;i++) {
    exr_bitmap a={0},b={0};OK(exr_render_page_color(l,NULL,i,&a,&error));OK(exr_render_page_color(copy,NULL,i,&b,&error));
    CHECK(a.stride==b.stride && a.height==b.height && !memcmp(a.pixels,b.pixels,(size_t)a.stride*a.height));
    exr_bitmap_free(&a);exr_bitmap_free(&b);
  }
  free(pages);free(paints);exr_layout_free(copy);
}
static void compare(exr_document *d,const exr_layout *whole,const exr_layout_config *c,int vertical) {
  size_t np,i,n,nn,nodes_count,targets[5];const exr_page *pages=exr_layout_pages(whole,&np);
  const exr_line *lines=exr_layout_lines(whole,&n);const exr_glyph *glyphs=exr_layout_glyphs(whole,&nn);
  exr_layout_config large=*c;exr_layout *reference=NULL;exr_pager *fast=NULL,*slow=NULL;
  const exr_glyph *original;size_t original_count,*at;
  CHECK(np>2);exr_document_nodes(d,&nodes_count);at=calloc(nodes_count,sizeof(*at));CHECK(at);
  if(vertical) large.page.width=16384;else large.page.height=16384;
  OK(exr_layout_create_ex(d,font,&large,&reference,&error));original=exr_layout_glyphs(reference,&original_count);
  CHECK(nn==original_count);
  for(i=0;i<nn;i++) {
    const exr_glyph *g=glyphs+i,*r;size_t j=at[g->node];
    while(j<original_count && original[j].node!=g->node) j++;
    CHECK(j<original_count);r=original+j;at[g->node]=j+1;
    CHECK(g->start==r->start && g->end==r->end && g->codepoint==r->codepoint && g->glyph==r->glyph && g->color==r->color);
    CHECK(g->flags==r->flags && near(g->advance,r->advance));
    CHECK(g->start>=pages[g->page].start && g->end<=pages[g->page].end);
  }
  for(i=0;i<n;i++) {
    float begin=vertical ? lines[i].x : lines[i].y,extent=vertical ? lines[i].width : lines[i].height;
    float end=vertical ? c->page.width : c->page.height;
    CHECK(begin>=c->page.margin-.04f && begin+extent<=end-c->page.margin+.04f);
  }
  if(!vertical && c->page.width<=180) {
    exr_bitmap a={0},b={0};size_t bytes;
    OK(exr_render_page_color(whole,NULL,0,&a,&error));OK(exr_render_page_color(reference,NULL,0,&b,&error));
    bytes=(size_t)a.stride*(size_t)(c->page.margin+20);if(a.stride==b.stride && memcmp(a.pixels,b.pixels,bytes)) { size_t k;for(k=0;k<bytes;k++) if(a.pixels[k]!=b.pixels[k]) { fprintf(stderr,"pixel mismatch %zu,%zu channel%zu actual%u ref%u\n",(k%(size_t)a.stride)/4,k/(size_t)a.stride,k%4,a.pixels[k],b.pixels[k]);break; } }
    CHECK(a.stride==b.stride && !memcmp(a.pixels,b.pixels,bytes));
    exr_bitmap_free(&a);exr_bitmap_free(&b);
  }
  { size_t count,k;const exr_box *boxes=exr_layout_boxes(whole,&count);
    for(k=0;k<count;k++) CHECK(boxes[k].x>=c->page.margin-.04f && boxes[k].y>=c->page.margin-.04f &&
      boxes[k].x+boxes[k].width<=c->page.width-c->page.margin+.04f && boxes[k].y+boxes[k].height<=c->page.height-c->page.margin+.04f);
  }
  free(at);exr_layout_free(reference);positioned(d,whole,c);
  OK(exr_pager_create(d,font,c,&fast,&error));OK(exr_pager_create(d,font,c,&slow,&error));
  OK(exr_pager_set_cache(fast,1,262144,&error));OK(exr_pager_set_checkpoints(fast,32,8*1024*1024,1,&error));
  OK(exr_pager_set_checkpoints(slow,0,0,0,&error));targets[0]=np-1;targets[1]=np/2;targets[2]=0;targets[3]=np-1;targets[4]=1;
  for(i=0;i<5;i++) {
    const exr_layout *a=NULL,*b=NULL;const exr_glyph *ga,*gb;size_t na,nb,j;exr_bitmap x={0},y={0},z={0};
    OK(exr_pager_get(fast,targets[i],&a,&error));OK(exr_pager_get(slow,targets[i],&b,&error));CHECK(a && b);
    ga=exr_layout_glyphs(a,&na);gb=exr_layout_glyphs(b,&nb);CHECK(na==nb);
    for(j=0;j<na;j++) {
      CHECK(ga[j].start==gb[j].start && ga[j].end==gb[j].end && ga[j].flags==gb[j].flags && near(ga[j].x,gb[j].x) && near(ga[j].baseline,gb[j].baseline));
      CHECK(exr_layout_hit_test(a,0,ga[j].x+.1f,ga[j].baseline-2)==exr_layout_hit_test(whole,targets[i],ga[j].x+.1f,ga[j].baseline-2));
    }
    OK(exr_render_page_color(a,NULL,0,&x,&error));OK(exr_render_page_color(b,NULL,0,&y,&error));OK(exr_render_page_color(whole,NULL,targets[i],&z,&error));
    CHECK(x.stride==y.stride && x.stride==z.stride && x.height==y.height && x.height==z.height && !memcmp(x.pixels,y.pixels,(size_t)x.stride*x.height) && !memcmp(x.pixels,z.pixels,(size_t)x.stride*x.height));
    exr_bitmap_free(&x);exr_bitmap_free(&y);exr_bitmap_free(&z);
  }
  CHECK(exr_pager_statistics(fast).restored_checkpoints>0 && exr_pager_statistics(fast).checkpoint_bytes<=8*1024*1024);
  exr_pager_free(fast);exr_pager_free(slow);
}
/* Same-build comparison against a preceding DLL, including every page pixel.
   The fixture font is fixed; output is evidence rather than a platform hash. */
static void signature(const exr_layout *l,unsigned test) {
  size_t i,n;uint64_t hash=UINT64_C(14695981039346656037);exr_layout_pages(l,&n);
  for(i=0;i<n;i++) {
    exr_bitmap b={0};size_t k;OK(exr_render_page_color(l,NULL,i,&b,&error));
    for(k=0;k<(size_t)b.stride*b.height;k++) { hash^=b.pixels[k];hash*=UINT64_C(1099511628211); }
    exr_bitmap_free(&b);
  }
  printf("case %u pages %zu pixels %016llx\n",test,n,(unsigned long long)hash);
}
static void cases(const char *directory) {
  unsigned test;char path[4096];
  for(test=0;test<24;test++) {
    exr_document *d=NULL;exr_layout *l=NULL;exr_layout_config c=config();size_t count,i,tables=0,cells=0;const exr_node *nodes;
    snprintf(path,sizeof(path),"%s/table-fragments-%u.epub",directory,test);OK(exr_document_open(path,&d,&error));
    nodes=exr_document_nodes(d,&count);for(i=0;i<count;i++) { tables+=nodes[i].kind==EXR_NODE_TABLE;cells+=nodes[i].kind==EXR_NODE_CELL; }
    CHECK(tables>0 && cells>=2 && count>8);
    if(test==6 || test==7 || test==23) { c.page.width=100;c.page.height=180; }
    { exr_status status=exr_layout_create_ex(d,font,&c,&l,&error);if(status!=EXR_OK) fprintf(stderr,"fragment case %u\n",test);OK(status); }
    fprintf(stderr,"fragment case %u\n",test);
    if(test!=16) { size_t np;const exr_page *pages=exr_layout_pages(l,&np);CHECK(np && pages[np-1].line_count>0); }
    signature(l,test);compare(d,l,&c,test==6 || test==7 || test==23);exr_layout_free(l);exr_document_free(d);
  }
}
static int within(int x,int y,float left,float top,float width,float height) {
  return width>0 && height>0 && x>=(int)floorf(left) && x<(int)ceilf(left+width) && y>=(int)floorf(top) && y<(int)ceilf(top+height);
}
static void alpha_borders(void) {
  const float widths[]={0,.1f,.5f,1.4f,3.8f,20};size_t i;exr_document *d=NULL;exr_layout_config c=config();
  OK(exr_document_open_memory(EXR_TXT,"border",6,&d,&error));c.page.width=c.page.height=16;c.page.margin=0;
  for(i=0;i<sizeof(widths)/sizeof(*widths);i++) {
    exr_positioned_page page={0};exr_box box={0};exr_paint paint={EXR_PAINT_BOX,0,0};exr_positioned_input input={0};
    exr_layout *l=NULL;exr_bitmap rgba={0},gray={0};int x,y;float bw;
    page.width=page.height=16;page.content.end=6;page.content.box_count=1;page.paint_count=1;
    box.kind=EXR_BOX_BLOCK;box.node=SIZE_MAX;box.resource=SIZE_MAX;box.end=6;box.x=2.3f;box.y=1.7f;box.width=7.1f;box.height=8.6f;
    box.background=0xffffffff;box.border_color=0x00000080;box.border_width=widths[i];
    input.struct_size=sizeof(input);input.pages=&page;input.page_count=1;input.boxes=&box;input.box_count=1;input.paints=&paint;input.paint_count=1;
    OK(exr_layout_create_positioned(d,font,&input,&c,&l,&error));OK(exr_render_page_color(l,NULL,0,&rgba,&error));OK(exr_render_page(l,NULL,0,&gray,&error));
    bw=fminf(box.border_width,fminf(box.width,box.height)/2);
    for(y=0;y<16;y++) for(x=0;x<16;x++) {
      int painted=bw>0 && (within(x,y,box.x,box.y,box.width,bw) || within(x,y,box.x,box.y+box.height-bw,box.width,bw) ||
        within(x,y,box.x,box.y,bw,box.height) || within(x,y,box.x+box.width-bw,box.y,bw,box.height));
      unsigned char expected=painted ? 127 : 255;const unsigned char *p=rgba.pixels+y*(size_t)rgba.stride+x*4;
      CHECK(p[0]==expected && p[1]==expected && p[2]==expected && p[3]==255 && gray.pixels[y*(size_t)gray.stride+x]==expected);
    }
    exr_bitmap_free(&rgba);exr_bitmap_free(&gray);exr_layout_free(l);
  }
  exr_document_free(d);
}
typedef struct { unsigned calls,at; } cancel_state;
static int cancel_after(void *context) { cancel_state *s=context;return ++s->calls>=s->at; }
static void recovery(const char *directory) {
  char path[4096];exr_document *d=NULL;exr_layout_config c=config();exr_pager *p=NULL;const exr_layout *page=NULL;unsigned threshold,test;const unsigned ids[]={12,21,22,23};
  for(test=0;test<sizeof(ids)/sizeof(*ids);test++) {
  snprintf(path,sizeof(path),"%s/table-fragments-%u.epub",directory,ids[test]);OK(exr_document_open(path,&d,&error));
  for(threshold=1;threshold<=32;threshold*=2) {
    cancel_state state={0,threshold};exr_control control={cancel_after,NULL,&state};
    OK(exr_pager_create(d,font,&c,&p,&error));OK(exr_pager_set_control(p,&control,&error));
    CHECK(exr_pager_get(p,0,&page,&error)==EXR_CANCELLED && !page && !exr_pager_cached_count(p));
    CHECK(state.calls>=threshold);OK(exr_pager_set_control(p,NULL,&error));OK(exr_pager_get(p,0,&page,&error));CHECK(page);
    exr_pager_free(p);p=NULL;
  }
  OK(exr_pager_create(d,font,&c,&p,&error));OK(exr_pager_set_cache(p,1,1,&error));
  CHECK(exr_pager_get(p,0,&page,&error)==EXR_LIMIT && !page && !exr_pager_cached_count(p));
  OK(exr_pager_set_cache(p,1,262144,&error));OK(exr_pager_get(p,0,&page,&error));CHECK(page);
  exr_pager_free(p);exr_document_free(d);p=NULL;d=NULL;
  }
}
static void large_fixed(const char *directory) {
  char path[4096];exr_document *d=NULL;exr_pager *p=NULL;const exr_layout *page=NULL;exr_layout_config c=config();
  cancel_state state={0,4096};exr_control control={cancel_after,NULL,&state};size_t count;
  c.page.width=720;c.page.height=960;snprintf(path,sizeof(path),"%s/table-fragments-large-fixed.epub",directory);
  OK(exr_document_open(path,&d,&error));OK(exr_pager_create(d,font,&c,&p,&error));OK(exr_pager_set_control(p,&control,&error));
  OK(exr_pager_get(p,0,&page,&error));CHECK(page && state.calls<4096 && exr_layout_memory_size(page)<512*1024);
  exr_layout_glyphs(page,&count);CHECK(count>0 && count<10000);
  fprintf(stderr,"large fixed first-page polls %u\n",state.calls);exr_pager_free(p);exr_document_free(d);
}
static void float_budgets(const char *directory) {
  const char *names[]={"float-128","float-129","float-tree-129"};size_t i;char path[4096];
  for(i=0;i<3;i++) {
    exr_document *d=NULL;exr_pager *p=NULL;const exr_layout *page=NULL;exr_layout_config c=config();
    c.page.width=i==1 ? 520 : 360;snprintf(path,sizeof(path),"%s/table-fragments-%s.epub",directory,names[i]);
    OK(exr_document_open(path,&d,&error));OK(exr_pager_create(d,font,&c,&p,&error));
    if(!i) { OK(exr_pager_get(p,0,&page,&error));CHECK(page); }
    else { CHECK(exr_pager_get(p,0,&page,&error)==EXR_LIMIT && !page && !exr_pager_cached_count(p));CHECK(strstr(error.message,"128 floating cursors")); }
    exr_pager_free(p);exr_document_free(d);
  }
}
int main(int argc,char **argv) {
  char path[4096];CHECK(argc==2 || argc==3);snprintf(path,sizeof(path),"%s/fonts/primary.ttf",argv[1]);OK(exr_font_open(path,&font,&error));
  if(argc==3) large_fixed(argv[1]);else { alpha_borders();cases(argv[1]);float_budgets(argv[1]);recovery(argv[1]);large_fixed(argv[1]); }exr_font_free(font);printf("%u table fragment checks passed\n",checks);return 0;
}
