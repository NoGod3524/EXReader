/* SPDX-License-Identifier: GPL-3.0-only */
#include "exreader.h"
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static unsigned generated_case; static exr_error error; static unsigned checks; static const char *directory; static exr_font *font;
#define CHECK(x) do { checks++; if(!(x)) { fprintf(stderr,"line %d: %s (%d: %s)\n",__LINE__,#x,error.code,error.message); exit(1); } } while(0)
#define OK(x) CHECK((x)==EXR_OK)
static int near(float a,float b) { return fabsf(a-b)<.03f; }
static exr_layout_config config(void) { exr_layout_config c=exr_layout_config_defaults(); c.page=(exr_layout_options){240,240,20,14,20.0f/14,0}; return c; }
static exr_document *book(const char *name) { char path[4096]; exr_document *d=NULL; snprintf(path,sizeof(path),"%s/float-%s.epub",directory,name); OK(exr_document_open(path,&d,&error)); return d; }
static exr_layout *layout(exr_document *d) { exr_layout_config c=config(); exr_layout *l=NULL; OK(exr_layout_create_ex(d,font,&c,&l,&error)); return l; }
static size_t node(const exr_document *d,const char *name) {
  size_t i,n; const exr_node *nodes=exr_document_nodes(d,&n);
  for(i=0;i<n;i++) { const char *id=exr_node_attribute(nodes+i,"id"); if(id && !strcmp(id,name)) return i; }
  CHECK(0); return SIZE_MAX;
}
static const exr_box *box(const exr_document *d,const exr_layout *l,const char *name) {
  size_t id=node(d,name),i,n; const exr_box *b=exr_layout_boxes(l,&n);
  for(i=0;i<n;i++) if(b[i].node==id && !(b[i].flags&EXR_BOX_BORDER)) return b+i;
  CHECK(0); return NULL;
}
static uint32_t pixel(const exr_bitmap *b,float x,float y) {
  const unsigned char *p; CHECK(x>=0 && y>=0 && x<b->width && y<b->height);
  p=b->pixels+(size_t)y*b->stride+(size_t)x*4;
  return ((uint32_t)p[0]<<24)|((uint32_t)p[1]<<16)|((uint32_t)p[2]<<8)|p[3];
}
static void positioned(exr_document *doc,const exr_layout *l) {
  size_t np,nl,ng,nb,i,j,at=0; const exr_page *p=exr_layout_pages(l,&np);
  const exr_line *lines=exr_layout_lines(l,&nl); const exr_glyph *g=exr_layout_glyphs(l,&ng); const exr_box *boxes=exr_layout_boxes(l,&nb);
  exr_positioned_page *pages=calloc(np,sizeof(*pages)); exr_paint *paints=calloc(ng+nb,sizeof(*paints));
  exr_positioned_input input={0}; exr_layout_config c=config(); exr_layout *copy=NULL; CHECK(pages && paints);
  for(i=0;i<np;i++) {
    pages[i].width=c.page.width; pages[i].height=c.page.height; pages[i].content=p[i]; pages[i].paint_start=at;
    for(j=p[i].box_start;j<p[i].box_start+p[i].box_count;j++) paints[at++]=(exr_paint){EXR_PAINT_BOX,0,j};
    for(j=p[i].line_start;j<p[i].line_start+p[i].line_count;j++) { size_t k; for(k=lines[j].glyph_start;k<lines[j].glyph_start+lines[j].glyph_count;k++) paints[at++]=(exr_paint){EXR_PAINT_GLYPH,0,k}; }
    pages[i].paint_count=at-pages[i].paint_start;
  }
  CHECK(at==ng+nb); input.struct_size=sizeof(input); input.pages=pages; input.page_count=np;
  input.glyphs=g; input.glyph_count=ng; input.lines=lines; input.line_count=nl; input.boxes=boxes; input.box_count=nb; input.paints=paints; input.paint_count=at;
  c.page.margin=0; OK(exr_layout_create_positioned(doc,exr_layout_font(l),&input,&c,&copy,&error));
  for(i=1;i<np;i++) if(p[i].start<p[i-1].end) {
    for(j=0;j<ng;j++) CHECK(exr_layout_page_at(copy,g[j].start)==g[j].page);
    break;
  }
  for(i=0;i<np;i++) { exr_bitmap a={0},b={0}; OK(exr_render_page_color(l,NULL,i,&a,&error)); OK(exr_render_page_color(copy,NULL,i,&b,&error)); CHECK(a.stride==b.stride && a.height==b.height && !memcmp(a.pixels,b.pixels,(size_t)a.stride*a.height)); exr_bitmap_free(&a); exr_bitmap_free(&b); }
  exr_layout_free(copy); free(pages); free(paints);
}
static int descendant(const exr_node *nodes,size_t parent,size_t child) {
  for(;child!=SIZE_MAX;child=nodes[child].parent) if(child==parent) return 1; return 0;
}
static int floated(const exr_node *nodes,size_t leaf) {
  for(;leaf!=SIZE_MAX;leaf=nodes[leaf].parent) { const char *style=exr_node_attribute(nodes+leaf,"style"); if(style && strstr(style,"float:")) return 1; } return 0;
}
static const exr_line *first_line(const exr_document *d,const exr_layout *l,const char *id) {
  size_t i,n,index=node(d,id); const exr_node *nodes=exr_document_nodes(d,NULL); const exr_line *lines=exr_layout_lines(l,&n); const exr_glyph *g=exr_layout_glyphs(l,NULL);
  for(i=0;i<n;i++) if(lines[i].glyph_count && descendant(nodes,index,g[lines[i].glyph_start].node)) return lines+i;
  CHECK(0); return NULL;
}
static void validate(exr_document *d,const exr_layout *l) {
  size_t ng,nb,nl,np,i,j,expected=0,actual=0,size; const char *source=exr_document_text(d,&size); const exr_node *nodes=exr_document_nodes(d,NULL);
  const exr_glyph *g=exr_layout_glyphs(l,&ng); const exr_box *b=exr_layout_boxes(l,&nb); const exr_line *lines=exr_layout_lines(l,&nl); const exr_page *pages=exr_layout_pages(l,&np);
  for(i=0;i<size;i++) expected+=source[i]=='A';
  for(i=0;i<ng;i++) { actual+=g[i].codepoint=='A'; CHECK(g[i].page<np && g[i].start>=pages[g[i].page].start && g[i].end<=pages[g[i].page].end); }
  CHECK(expected==actual);
  for(i=0;i<nb;i++) CHECK(isfinite(b[i].x) && isfinite(b[i].y) && b[i].x>=19.99f && b[i].y>=19.99f && b[i].x+b[i].width<=220.01f && b[i].y+b[i].height<=220.01f);
  for(i=0;i<nl;i++) if(lines[i].glyph_count && !floated(nodes,g[lines[i].glyph_start].node)) {
    for(j=0;j<nb;j++) if(b[j].page==lines[i].page && !(b[j].flags&EXR_BOX_BORDER) && floated(nodes,b[j].node)) {
      /* Advances retain source spaces/indivisible clusters; the public inline
         clip is the visible rectangle used by the native rasterizer. */
      float left=lines[i].x,right=left+lines[i].width,top=lines[i].y,bottom=top+lines[i].height;
      const exr_glyph *first=g+lines[i].glyph_start;
      if(first->flags&EXR_GLYPH_VERTICAL) { top=fmaxf(top,first->clip_left); bottom=fminf(bottom,first->clip_right); }
      else { left=fmaxf(left,first->clip_left); right=fminf(right,first->clip_right); }
      if(!(right<=b[j].x+.03f || left>=b[j].x+b[j].width-.03f || bottom<=b[j].y+.03f || top>=b[j].y+b[j].height-.03f)) {
        size_t k,total; exr_document_nodes(d,&total);
        fprintf(stderr,"generated %u line %zu page %zu xywh %.3f %.3f %.3f %.3f box node %zu xywh %.3f %.3f %.3f %.3f\n",generated_case,i,lines[i].page,lines[i].x,lines[i].y,lines[i].width,lines[i].height,b[j].node,b[j].x,b[j].y,b[j].width,b[j].height);
        fprintf(stderr,"line glyph node %zu clip %.3f %.3f baseline %.3f\n",g[lines[i].glyph_start].node,g[lines[i].glyph_start].clip_left,g[lines[i].glyph_start].clip_right,g[lines[i].glyph_start].baseline);
        for(k=0;k<total;k++) { const char *style=exr_node_attribute(nodes+k,"style"); if(style) fprintf(stderr,"node %zu %s\n",k,style); }
        CHECK(0);
      }
    }
  }
}
static void pictures(void) {
  const char *names[]={"left","right","both","same","stack","order","clear-left","clear-right","clear-both","midline","late","block","auto","table","cell","nested","vertical-rl","vertical-lr","bidi","soft","ruby","next-page","full","clear-br","margins","normal-image","normal-table","mixed-size","ordinary-block","nested-clear","percent","empty","auto-percent","max-percent","auto-corridor"}; size_t i;
  for(i=0;i<sizeof(names)/sizeof(*names);i++) {
    exr_document *d=book(names[i]); exr_layout *l=NULL; exr_layout_config c=config(); exr_status status=exr_layout_create_ex(d,font,&c,&l,&error); const exr_line *line;
    if(status!=EXR_OK) fprintf(stderr,"fixture %s\n",names[i]); OK(status); validate(d,l);
    line=first_line(d,l,"text");
    if(i==15) { const exr_line *lines=exr_layout_lines(l,NULL); const exr_glyph *g=exr_layout_glyphs(l,NULL); const exr_node *nodes=exr_document_nodes(d,NULL); size_t j=0;
      while(floated(nodes,g[lines[j].glyph_start].node)) j++; line=lines+j;
    }
    if(i<2) { const exr_box *p=box(d,l,"picture"); size_t j,n; const exr_glyph *g=exr_layout_glyphs(l,&n);
      CHECK(near(p->x,i ? 140 : 20) && near(p->y,20) && near(p->width,80) && near(p->height,60));
      CHECK(near(line->x,i ? 20 : 100) && near(line->y,20));
      for(j=0;j<n;j++) if(!(g[j].flags&EXR_GLYPH_VERTICAL) && g[j].baseline<80) CHECK(near(g[j].clip_left,i ? 20 : 100) && near(g[j].clip_right,i ? 140 : 220));
    }
    if(i==2 || i==3) { CHECK(near(box(d,l,"left")->x,20) && near(box(d,l,"right")->x,i==2 ? 160 : 80)); CHECK(near(line->x,i==2 ? 80 : 140)); }
    if(i==4) CHECK(near(box(d,l,"right")->y,110) && near(line->x,140));
    if(i==5) CHECK(box(d,l,"third")->y>=box(d,l,"second")->y);
    if(i>=6 && i<=8) CHECK(near(line->y,i==7 ? 50 : 80) && near(line->x,i==7 ? 100 : 20));
    if(i==9) CHECK(near(first_line(d,l,"before")->x,80) && near(box(d,l,"picture")->y,20));
    if(i==10) CHECK(near(first_line(d,l,"before")->y,20) && near(box(d,l,"picture")->y,40));
    if(i==11) CHECK(near(box(d,l,"floating")->width,60) && near(box(d,l,"floating")->height,80) && near(line->x,80));
    if(i==12) CHECK(near(box(d,l,"floating")->width,21) && near(line->x,41));
    if(i==15) CHECK(box(d,l,"floating")->height>=box(d,l,"picture")->height && near(line->x,120));
    if(i==21) CHECK(box(d,l,"picture")->page==1 && near(box(d,l,"picture")->y,20));
    if(i==22) CHECK(near(line->y,170) && near(line->x,20) && line->width>7);
    if(i==23) CHECK(near(line->y,80));
    if(i==24) { const exr_box *p=exr_layout_boxes(l,NULL); size_t n,j; exr_bitmap image={0}; exr_layout_boxes(l,&n); for(j=0;j<n;j++) if(p[j].kind==EXR_BOX_IMAGE) break; CHECK(j<n); p+=j; CHECK(near(p->x,36) && near(p->y,30) && near(line->x,128)); OK(exr_render_page_color(l,NULL,0,&image,&error)); CHECK(pixel(&image,40,35)==0x0080ffff && pixel(&image,31,26)==0xff0000ff); exr_bitmap_free(&image); }
    if(i==25) CHECK(near(box(d,l,"normal")->x,100));
    if(i==26) CHECK(line->y>=100);
    if(i==30) { const exr_box *b=exr_layout_boxes(l,NULL); size_t j=0; while(b[j].kind!=EXR_BOX_IMAGE) j++; CHECK(near(b[j].x,32) && near(b[j].width,40) && near(line->x,84)); }
    if(i==31) CHECK(near(box(d,l,"floating")->height,80) && near(line->x,80));
    if(i==32) CHECK(near(box(d,l,"floating")->width,41) && near(line->x,61));
    if(i==33) CHECK(near(box(d,l,"floating")->width,60) && near(line->x,80));
    if(i==34) CHECK(near(box(d,l,"floating")->width,60) && near(box(d,l,"floating")->x,160) && near(box(d,l,"floating")->y,20));
    positioned(d,l); exr_layout_free(l); exr_document_free(d);
  }
}
static void pages(const char *name) {
  exr_document *d=book(name); exr_layout_config c=config(); exr_layout *whole=layout(d); exr_pager *fast=NULL,*slow=NULL; const exr_layout *a,*b; size_t np,i,targets[]={20,15,2,11,0,20,4};
  exr_layout_pages(whole,&np); CHECK(np>20); validate(d,whole); OK(exr_pager_create(d,font,&c,&fast,&error)); OK(exr_pager_create(d,font,&c,&slow,&error));
  OK(exr_pager_set_cache(fast,1,262144,&error)); OK(exr_pager_set_checkpoints(fast,32,1024*1024,1,&error)); OK(exr_pager_set_checkpoints(slow,0,0,0,&error));
  for(i=0;i<sizeof(targets)/sizeof(*targets);i++) {
    size_t j,n,m; const exr_glyph *g,*h; exr_bitmap x={0},y={0},z={0}; OK(exr_pager_get(fast,targets[i],&a,&error)); OK(exr_pager_get(slow,targets[i],&b,&error)); CHECK(a && b);
    g=exr_layout_glyphs(a,&n); h=exr_layout_glyphs(b,&m); CHECK(n==m);
    for(j=0;j<n;j++) CHECK(g[j].start==h[j].start && g[j].end==h[j].end && near(g[j].x,h[j].x) && near(g[j].baseline,h[j].baseline) && exr_layout_hit_test(a,0,g[j].x+.1f,g[j].baseline-2)==exr_layout_hit_test(whole,targets[i],g[j].x+.1f,g[j].baseline-2));
    OK(exr_render_page_color(a,NULL,0,&x,&error)); OK(exr_render_page_color(b,NULL,0,&y,&error)); OK(exr_render_page_color(whole,NULL,targets[i],&z,&error));
    CHECK(x.stride==y.stride && x.stride==z.stride && x.height==y.height && x.height==z.height && !memcmp(x.pixels,y.pixels,(size_t)x.stride*x.height) && !memcmp(x.pixels,z.pixels,(size_t)x.stride*x.height)); exr_bitmap_free(&x); exr_bitmap_free(&y); exr_bitmap_free(&z);
  }
  CHECK(exr_pager_statistics(fast).restored_checkpoints>0); exr_pager_free(fast); exr_pager_free(slow); exr_layout_free(whole); exr_document_free(d);
}
static void limits(void) {
  exr_document *d=book("oversized"); exr_layout_config c=config(); exr_layout *l=NULL; CHECK(exr_layout_create_ex(d,font,&c,&l,&error)==EXR_LIMIT && !l); exr_document_free(d);
  d=book("limit"); c.page.width=2048; CHECK(exr_layout_create_ex(d,font,&c,&l,&error)==EXR_LIMIT && !l); exr_document_free(d);
}
typedef struct { unsigned calls; int stop; } cancellation;
static int cancelled(void *context) { return ((cancellation *)context)->stop; }
static void progress(void *context,exr_stage stage,uint64_t completed,uint64_t total) {
  cancellation *c=context; (void)completed; (void)total; if(stage==EXR_STAGE_LAYOUT && ++c->calls==8) c->stop=1;
}
static void recovery(void) {
  exr_document *d=book("pages"); exr_layout_config c=config(); exr_layout *l=(exr_layout *)(uintptr_t)1; exr_pager *p=NULL; const exr_layout *page=(const exr_layout *)(uintptr_t)1; cancellation state={0};
  c.control=(exr_control){cancelled,progress,&state}; CHECK(exr_layout_create_ex(d,font,&c,&l,&error)==EXR_CANCELLED && !l && state.stop);
  memset(&c.control,0,sizeof(c.control)); OK(exr_layout_create_ex(d,font,&c,&l,&error)); validate(d,l); exr_layout_free(l);
  OK(exr_pager_create(d,font,&c,&p,&error)); OK(exr_pager_set_cache(p,1,1,&error)); CHECK(exr_pager_get(p,0,&page,&error)==EXR_LIMIT && !page); exr_pager_free(p); exr_document_free(d);
}
static uint32_t random_value(uint32_t *s) { *s=*s*1664525u+1013904223u; return *s; }
static void generated(void) {
  uint32_t seed=180319; unsigned iteration;
  for(iteration=0;iteration<500;iteration++) {
    generated_case=iteration;
    exr_node_input nodes[96]={{0}}; exr_attribute attrs[96]; char styles[96][160],texts[96][96];
    exr_chapter_input chapter={"generated","generated.unit",1,1}; exr_document_input input={"Floats",nodes,0,&chapter,1,NULL,0};
    exr_document *d=NULL; exr_layout *l=NULL; exr_layout_config c=config(); size_t used=2,i;
    nodes[0]=(exr_node_input){EXR_NODE_DOCUMENT,SIZE_MAX,NULL,NULL,NULL,0}; nodes[1]=(exr_node_input){EXR_NODE_CHAPTER,0,NULL,NULL,NULL,0};
    for(i=0;i<12;i++) {
      size_t block=used++,text_node=used++,j,length=0; unsigned floated_item=i%3!=2,count=1+random_value(&seed)%(floated_item ? 3 : 30);
      const char *clear[]={"none","left","right","both"};
      if(floated_item) snprintf(styles[block],sizeof(styles[block]),"float:%s;width:%upx;height:%upx;margin:%upx;padding:%upx;clear:%s;background:#ffe080;font-size:%upx",random_value(&seed)%2 ? "left" : "right",20+random_value(&seed)%61,20+random_value(&seed)%51,random_value(&seed)%4,random_value(&seed)%3,clear[random_value(&seed)%4],10+random_value(&seed)%12);
      else snprintf(styles[block],sizeof(styles[block]),"text-align:%s;direction:%s",iteration%2 ? "justify" : "right",iteration%3 ? "ltr" : "rtl");
      if(floated_item && iteration%4==0) { char *width=strstr(styles[block],"width:"),*end=strchr(width,';'); memmove(width+10,end,strlen(end)+1); memcpy(width,"width:auto",10); }
      attrs[block]=(exr_attribute){"style",styles[block]}; nodes[block]=(exr_node_input){EXR_NODE_PARAGRAPH,1,"p",NULL,attrs+block,1};
      for(j=0;j<count;j++) { texts[text_node][length++]='A'; if(j+1<count) texts[text_node][length++]=' '; } texts[text_node][length]=0;
      nodes[text_node]=(exr_node_input){EXR_NODE_TEXT,block,NULL,texts[text_node],NULL,0};
    }
    input.node_count=used; OK(exr_document_create(&input,&d,&error));
    { exr_status status=exr_layout_create_ex(d,font,&c,&l,&error); if(status!=EXR_OK) fprintf(stderr,"generated %u (%s)\n",iteration,error.message); CHECK(status==EXR_OK); }
    validate(d,l);
    if(iteration%50==0) { exr_bitmap bitmap={0}; OK(exr_render_page_color(l,NULL,0,&bitmap,&error)); exr_bitmap_free(&bitmap); }
    exr_layout_free(l); exr_document_free(d);
  }
}
static void joining(void) {
  char path[4096]; exr_font *shaping=NULL; exr_document *a=book("joining"),*b=book("joining-control"); exr_layout *x=NULL,*y=NULL; exr_layout_config c=config(); const exr_glyph *g,*h; size_t n,m;
  snprintf(path,sizeof(path),"%s/shaping/shaping.ttf",directory); OK(exr_font_open(path,&shaping,&error));
  OK(exr_layout_create_ex(a,shaping,&c,&x,&error)); OK(exr_layout_create_ex(b,shaping,&c,&y,&error));
  g=exr_layout_glyphs(x,&n); h=exr_layout_glyphs(y,&m); CHECK(n==1 && m==1 && g[0].glyph==h[0].glyph && near(g[0].advance,h[0].advance) && g[0].cluster_end==h[0].cluster_end);
  CHECK(g[0].flags&EXR_GLYPH_SHAPED); CHECK(near(g[0].clip_left,60)); positioned(a,x);
  exr_layout_free(x); exr_layout_free(y); exr_document_free(a); exr_document_free(b); exr_font_free(shaping);
}
static void cell_baseline(void) {
  exr_document *d=book("cell-baseline"); exr_layout *l=layout(d); const exr_line *peer=first_line(d,l,"peer"),*floating_line=first_line(d,l,"floating"); const exr_glyph *g=exr_layout_glyphs(l,NULL);
  CHECK(near(g[peer->glyph_start].baseline,box(d,l,"cell")->y+60));
  CHECK(g[floating_line->glyph_start].baseline<g[peer->glyph_start].baseline); positioned(d,l); exr_layout_free(l); exr_document_free(d);
}
static void source_overlap(void) {
  exr_document *d=book("source-overlap"); exr_layout *l=layout(d); size_t np,n,i; const exr_glyph *g=exr_layout_glyphs(l,&n); const exr_page *p=exr_layout_pages(l,&np);
  CHECK(np==2 && p[0].end>p[1].start);
  for(i=0;i<n;i++) { size_t page=exr_layout_page_at(l,g[i].start); if(page!=g[i].page) fprintf(stderr,"source lookup offset %zu expected %zu got %zu\n",g[i].start,g[i].page,page); CHECK(page==g[i].page); }
  positioned(d,l); exr_layout_free(l); exr_document_free(d);
}
int main(int argc,char **argv) {
  char path[4096]; CHECK(argc==2); directory=argv[1]; snprintf(path,sizeof(path),"%s/fonts/primary.ttf",directory); OK(exr_font_open(path,&font,&error)); pictures(); pages("pages"); pages("orthogonal-pages"); limits(); recovery(); generated(); joining(); cell_baseline(); source_overlap(); exr_font_free(font); printf("%u float checks passed\n",checks); return 0;
}


