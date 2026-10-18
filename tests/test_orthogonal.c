/* SPDX-License-Identifier: GPL-3.0-only */
#include "exreader.h"
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static exr_error error;
static unsigned checks;
#define CHECK(x) do { checks++; if (!(x)) { fprintf(stderr,"line %d: %s (%d %s)\n",__LINE__,#x,error.code,error.message); exit(1); } } while(0)
#define OK(x) CHECK((x)==EXR_OK)
static int near(float a,float b) { return fabsf(a-b)<.02f; }
static const char *modes[]={"horizontal-tb","vertical-rl","vertical-lr"};
static exr_layout_config config(void) {
  exr_layout_config c=exr_layout_config_defaults();
  c.page.width=160; c.page.height=180; c.page.margin=10;
  c.page.font_size=20; c.page.line_height=1.2f; c.page.paragraph_spacing=0;
  return c;
}
static exr_document *document_ex(unsigned outer,unsigned inner,size_t repeat,const char *extra) {
  exr_document *doc=NULL; char a[80],b[512],*text=malloc(repeat*4+1); size_t i;
  exr_attribute root={"style",a},local={"style",b};
  exr_node_input nodes[]={{EXR_NODE_DOCUMENT,SIZE_MAX,NULL,NULL,NULL,0},
    {EXR_NODE_CHAPTER,0,NULL,NULL,&root,1},{EXR_NODE_PARAGRAPH,1,"p",NULL,NULL,0},
    {EXR_NODE_TEXT,2,NULL,"A\xe7\x94\xb2",NULL,0},
    {EXR_NODE_SECTION,1,"section",NULL,&local,1},{EXR_NODE_PARAGRAPH,4,"p",NULL,NULL,0},
    {EXR_NODE_TEXT,5,NULL,NULL,NULL,0},{EXR_NODE_PARAGRAPH,1,"p",NULL,NULL,0},
    {EXR_NODE_TEXT,7,NULL,"\xe7\x94\xb2" "A",NULL,0}};
  exr_chapter_input chapter={"mixed","mixed.xhtml",1,1};
  exr_document_input input={"mixed",nodes,9,&chapter,1,NULL,0};
  CHECK(text); for(i=0;i<repeat;i++) memcpy(text+4*i,"\xe7\x94\xb2" "A",4); text[4*repeat]=0;
  snprintf(a,sizeof(a),"writing-mode:%s",modes[outer]);
  snprintf(b,sizeof(b),"writing-mode:%s;%s:80px;%s",modes[inner],inner ? "height" : "width",extra ? extra : "");
  nodes[6].text=text; OK(exr_document_create(&input,&doc,&error)); free(text); return doc;
}
static exr_document *document(unsigned outer,unsigned inner,size_t repeat) {
  return document_ex(outer,inner,repeat,NULL);
}
static void equal_page(const exr_layout *all,size_t page,const exr_layout *one) {
  const exr_page *a=exr_layout_pages(all,NULL)+page,*b=exr_layout_pages(one,NULL);
  const exr_line *la=exr_layout_lines(all,NULL),*lb=exr_layout_lines(one,NULL);
  const exr_glyph *ga=exr_layout_glyphs(all,NULL),*gb=exr_layout_glyphs(one,NULL);
  const exr_box *ba=exr_layout_boxes(all,NULL),*bb=exr_layout_boxes(one,NULL);
  size_t n,i,j; exr_layout_pages(one,&n);
  CHECK(n==1 && a->start==b->start && a->end==b->end && a->line_count==b->line_count && a->box_count==b->box_count);
  for(i=0;i<b->line_count;i++) {
    const exr_line *x=&la[a->line_start+i],*y=&lb[b->line_start+i];
    CHECK(x->start==y->start && x->end==y->end && x->glyph_count==y->glyph_count &&
          near(x->x,y->x) && near(x->y,y->y) && near(x->width,y->width) && near(x->height,y->height));
    for(j=0;j<x->glyph_count;j++) {
      const exr_glyph *u=&ga[x->glyph_start+j],*v=&gb[y->glyph_start+j];
      CHECK(u->start==v->start && u->end==v->end && u->glyph==v->glyph && u->flags==v->flags &&
            near(u->x,v->x) && near(u->baseline,v->baseline) && near(u->advance,v->advance) &&
            near(u->clip_left,v->clip_left) && near(u->clip_right,v->clip_right) &&
            near(u->offset_x,v->offset_x) && near(u->offset_y,v->offset_y));
    }
  }
  for(i=0;i<b->box_count;i++) {
    const exr_box *x=&ba[a->box_start+i],*y=&bb[b->box_start+i];
    CHECK(x->kind==y->kind && x->node==y->node && x->start==y->start && x->end==y->end &&
          x->resource==y->resource && x->flags==y->flags && near(x->x,y->x) && near(x->y,y->y) &&
          near(x->width,y->width) && near(x->height,y->height) && near(x->border_width,y->border_width) &&
          x->background==y->background && x->border_color==y->border_color);
  }
}
static void positioned(exr_document *doc,exr_font *font,const exr_layout *layout) {
  size_t np,nl,ng,nb,i,j,at=0; const exr_page *p=exr_layout_pages(layout,&np);
  const exr_line *lines=exr_layout_lines(layout,&nl); const exr_glyph *g=exr_layout_glyphs(layout,&ng);
  const exr_box *boxes=exr_layout_boxes(layout,&nb);
  exr_positioned_page *pages=calloc(np,sizeof(*pages)); exr_paint *paints=calloc(ng+nb,sizeof(*paints));
  exr_positioned_input input={0}; exr_layout_config c=config(); exr_layout *copy=NULL;
  CHECK(pages && paints);
  for(i=0;i<np;i++) {
    pages[i].width=160; pages[i].height=180; pages[i].content=p[i]; pages[i].paint_start=at;
    for(j=p[i].box_start;j<p[i].box_start+p[i].box_count;j++)
      paints[at++]=(exr_paint){EXR_PAINT_BOX,0,j};
    for(j=p[i].line_start;j<p[i].line_start+p[i].line_count;j++) {
      size_t k; for(k=lines[j].glyph_start;k<lines[j].glyph_start+lines[j].glyph_count;k++)
        paints[at++]=(exr_paint){EXR_PAINT_GLYPH,0,k};
    }
    pages[i].paint_count=at-pages[i].paint_start;
  }
  CHECK(at==ng+nb); input.struct_size=sizeof(input); input.pages=pages; input.page_count=np;
  input.glyphs=g; input.glyph_count=ng; input.lines=lines; input.line_count=nl;
  input.boxes=boxes; input.box_count=nb;
  input.paints=paints; input.paint_count=ng+nb; c.page.margin=0;
  OK(exr_layout_create_positioned(doc,font,&input,&c,&copy,&error));
  for(i=0;i<np;i++) {
    exr_bitmap a={0},b={0};
    OK(exr_render_page(layout,font,i,&a,&error)); OK(exr_render_page(copy,font,i,&b,&error));
    CHECK(a.width==b.width && a.height==b.height && a.stride==b.stride &&
          !memcmp(a.pixels,b.pixels,(size_t)a.stride*a.height));
    exr_bitmap_free(&a); exr_bitmap_free(&b);
  }
  exr_layout_free(copy); free(pages); free(paints);
}
static void mixed(exr_font *font,unsigned outer,unsigned inner) {
  exr_document *doc=document(outer,inner,240); exr_layout_config c=config();
  exr_layout *all=NULL,*one=NULL; exr_pager *pager=NULL; const exr_layout *cached=NULL;
  const exr_line *lines; const exr_glyph *g; size_t np,nl,ng,i,j,local=0,normal=0;
  exr_pager_stats stats; const size_t budget=512*1024;
  OK(exr_layout_create_ex(doc,font,&c,&all,&error)); exr_layout_pages(all,&np);
  lines=exr_layout_lines(all,&nl); g=exr_layout_glyphs(all,&ng);
  CHECK(np>3 && nl && ng==484 && exr_layout_writing_mode(all)==(exr_writing_mode)outer);
  for(i=0;i<ng;i++) {
    CHECK(!!(g[i].flags&EXR_GLYPH_VERTICAL)==!!(g[i].node==6 ? inner : outer));
    if(g[i].node==6) local++; else normal++;
  }
  CHECK(local==480 && normal==4);
  for(i=0;i<nl;i++) {
    const exr_line *line=&lines[i]; const exr_glyph *first=&g[line->glyph_start];
    CHECK(line->x>=9.98f && line->y>=9.98f && line->x+line->width<=150.02f && line->y+line->height<=170.02f);
    for(j=line->glyph_start;j<line->glyph_start+line->glyph_count;j++) {
      float x=(first->flags&EXR_GLYPH_VERTICAL) ? line->x+line->width/2 : g[j].x+g[j].advance/4;
      float y=(first->flags&EXR_GLYPH_VERTICAL) ? g[j].baseline+g[j].advance/4 : line->y+line->height/2;
      CHECK(exr_layout_hit_test(all,line->page,x,y)==g[j].cluster_start);
    }
  }
  positioned(doc,font,all);
  OK(exr_pager_create(doc,font,&c,&pager,&error));
  for(i=0;i<np;i++) {
    OK(exr_pager_next(pager,&one,&error)); CHECK(one); equal_page(all,i,one); exr_layout_free(one); one=NULL;
  }
  OK(exr_pager_next(pager,&one,&error)); CHECK(!one); exr_pager_free(pager); pager=NULL;
  OK(exr_pager_create(doc,font,&c,&pager,&error)); OK(exr_pager_set_cache(pager,1,128*1024,&error));
  OK(exr_pager_set_checkpoints(pager,8,budget,1,&error));
  { size_t indices[]={np-1,1,np-2,0,np/2};
    for(i=0;i<sizeof(indices)/sizeof(*indices);i++) {
      OK(exr_pager_get(pager,indices[i],&cached,&error)); equal_page(all,indices[i],cached);
    }
  }
  stats=exr_pager_statistics(pager);
  CHECK(stats.restored_checkpoints>0 && stats.checkpoint_count && stats.checkpoint_bytes<=budget);
  exr_pager_free(pager); pager=NULL;
  OK(exr_pager_create(doc,font,&c,&pager,&error)); OK(exr_pager_set_cache(pager,1,128*1024,&error));
  OK(exr_pager_set_checkpoints(pager,8,1024,1,&error)); OK(exr_pager_get(pager,np/2,&cached,&error));
  stats=exr_pager_statistics(pager); CHECK(!stats.checkpoint_count && !stats.checkpoint_bytes);
  equal_page(all,np/2,cached);
  exr_pager_free(pager); exr_layout_free(all); exr_document_free(doc);
}
static void bounded(exr_font *font) {
  exr_document *doc=document(0,1,10000); exr_layout_config c=config(); exr_pager *pager=NULL;
  exr_layout *page=NULL; size_t size,first; const exr_page *pages;
  exr_document_text(doc,&size); OK(exr_pager_create(doc,font,&c,&pager,&error));
  OK(exr_pager_next(pager,&page,&error)); CHECK(page); pages=exr_layout_pages(page,NULL); first=pages[0].end;
  CHECK(first<size/20 && exr_pager_position(pager)<size/20 && exr_layout_memory_size(page)<128*1024);
  exr_layout_free(page); exr_pager_free(pager); exr_document_free(doc);
}
static void outer_geometry(exr_font *font) {
  const char *styles[]={"", "padding-top:5px;padding-bottom:7px", "margin-top:3px;margin-bottom:4px"};
  const float heights[]={80,92,87}; size_t k;
  for(k=0;k<sizeof(styles)/sizeof(*styles);k++) {
    exr_document *doc=document_ex(0,1,1,styles[k]); exr_layout_config c=config(); exr_layout *layout=NULL;
    const exr_line *lines; const exr_glyph *g; size_t n,i; float top=-1,bottom=-1;
    OK(exr_layout_create_ex(doc,font,&c,&layout,&error)); lines=exr_layout_lines(layout,&n); g=exr_layout_glyphs(layout,NULL);
    for(i=0;i<n;i++) {
      if(g[lines[i].glyph_start].node==3) top=lines[i].y+lines[i].height;
      if(g[lines[i].glyph_start].node==8) bottom=lines[i].y;
    }
    CHECK(top>0 && near(bottom-top,heights[k]));
    exr_layout_free(layout); exr_document_free(doc);
  }
  {
    exr_document *doc=document_ex(0,1,1,"break-before:page;break-after:page");
    exr_layout_config c=config(); exr_layout *layout=NULL; const exr_glyph *g; size_t n,i;
    OK(exr_layout_create_ex(doc,font,&c,&layout,&error)); g=exr_layout_glyphs(layout,&n);
    for(i=0;i<n;i++) CHECK(g[i].page==(g[i].node==3 ? 0u : g[i].node==6 ? 1u : 2u));
    exr_layout_pages(layout,&n); CHECK(n==3); exr_layout_free(layout); exr_document_free(doc);
  }
  {
    exr_document *doc=document_ex(0,1,240,"padding:2px;border:1px solid black;background:#dceeff");
    exr_layout_config c=config(); exr_layout *layout=NULL;
    OK(exr_layout_create_ex(doc,font,&c,&layout,&error)); positioned(doc,font,layout);
    exr_layout_free(layout); exr_document_free(doc);
  }
}
static void nested(exr_font *font) {
  exr_attribute root={"style","writing-mode:horizontal-tb"};
  exr_attribute outer={"style","writing-mode:vertical-rl;height:120px;padding:2px;border:1px solid black;background:#eef"};
  exr_attribute horizontal[]={ {"style","writing-mode:horizontal-tb;width:24px;padding:1px;border:1px solid black;background:#abc"}, {"rowspan","2"} };
  exr_attribute vertical={"style","padding:1px;border:1px solid black"};
  exr_attribute image={"style","width:18px;height:24px"};
  exr_attribute inner={"style","writing-mode:horizontal-tb;width:60px"};
  char text[385]; size_t i,n,np,nb; exr_document *doc=NULL; exr_layout *all=NULL;
  exr_layout_config c=config(); exr_pager *pager=NULL; const exr_layout *cached=NULL;
  const exr_box *boxes; const exr_glyph *g; unsigned images=0,span=0;
  exr_node_input nodes[]={{EXR_NODE_DOCUMENT,SIZE_MAX,NULL,NULL,NULL,0},
    {EXR_NODE_CHAPTER,0,NULL,NULL,&root,1},{EXR_NODE_SECTION,1,"section",NULL,&outer,1},
    {EXR_NODE_TABLE,2,"table",NULL,NULL,0},{EXR_NODE_ROW,3,"tr",NULL,NULL,0},
    {EXR_NODE_CELL,4,"td",NULL,horizontal,2},{EXR_NODE_TEXT,5,NULL,"A\xe7\x94\xb2",NULL,0},
    {EXR_NODE_CELL,4,"td",NULL,&vertical,1},{EXR_NODE_TEXT,7,NULL,"\xe7\x94\xb2" "A",NULL,0},
    {EXR_NODE_ROW,3,"tr",NULL,NULL,0},{EXR_NODE_CELL,9,"td",NULL,&vertical,1},
    {EXR_NODE_TEXT,10,NULL,"\xe7\x94\xb2",NULL,0},{EXR_NODE_IMAGE,2,"img",NULL,&image,1},
    {EXR_NODE_SECTION,2,"section",NULL,&inner,1},{EXR_NODE_PARAGRAPH,13,"p",NULL,NULL,0},
    {EXR_NODE_TEXT,14,NULL,"A\xe7\x94\xb2",NULL,0},{EXR_NODE_PARAGRAPH,2,"p",NULL,NULL,0},
    {EXR_NODE_TEXT,16,NULL,text,NULL,0},{EXR_NODE_PARAGRAPH,1,"p",NULL,NULL,0},
    {EXR_NODE_TEXT,18,NULL,"A",NULL,0}};
  exr_chapter_input chapter={"nested","nested.xhtml",1,1};
  exr_document_input input={"nested",nodes,20,&chapter,1,NULL,0};
  for(i=0;i<128;i++) memcpy(text+3*i,"\xe7\x94\xb2",3);
  text[384]=0;
  OK(exr_document_create(&input,&doc,&error)); OK(exr_layout_create_ex(doc,font,&c,&all,&error));
  exr_layout_pages(all,&np); CHECK(np>=3); g=exr_layout_glyphs(all,&n); CHECK(n==136);
  for(i=0;i<n;i++) CHECK(!!(g[i].flags&EXR_GLYPH_VERTICAL)==!!(g[i].node==8 || g[i].node==11 || g[i].node==17));
  boxes=exr_layout_boxes(all,&nb); CHECK(nb>5);
  for(i=0;i<nb;i++) {
    if(boxes[i].x<9.98f || boxes[i].y<9.98f || boxes[i].x+boxes[i].width>150.02f || boxes[i].y+boxes[i].height>170.02f)
      fprintf(stderr,"box %zu node %zu page %zu kind %u rect %.2f %.2f %.2f %.2f\n",i,boxes[i].node,boxes[i].page,(unsigned)boxes[i].kind,boxes[i].x,boxes[i].y,boxes[i].width,boxes[i].height);
    CHECK(boxes[i].x>=9.98f && boxes[i].y>=9.98f && boxes[i].x+boxes[i].width<=150.02f &&
          boxes[i].y+boxes[i].height<=170.02f);
    if(boxes[i].kind==EXR_BOX_IMAGE) { CHECK(boxes[i].flags==1); images++; }
    if(boxes[i].kind==EXR_BOX_CELL && boxes[i].node==5) {
      size_t j; float rows=0;
      for(j=0;j<nb;j++) if(boxes[j].kind==EXR_BOX_CELL && (boxes[j].node==7 || boxes[j].node==10)) {
        CHECK(boxes[j].page==boxes[i].page); rows+=boxes[j].width;
      }
      CHECK(boxes[i].width>=55.98f && near(boxes[i].width,rows)); span++;
    }
  }
  CHECK(images==1 && span==1); positioned(doc,font,all);
  OK(exr_pager_create(doc,font,&c,&pager,&error)); OK(exr_pager_set_cache(pager,1,128*1024,&error));
  OK(exr_pager_set_checkpoints(pager,8,1024*1024,1,&error));
  for(i=np;i;i--) { OK(exr_pager_get(pager,i-1,&cached,&error)); equal_page(all,i-1,cached); }
  CHECK(exr_pager_statistics(pager).restored_checkpoints>0);
  exr_pager_free(pager); exr_layout_free(all); exr_document_free(doc);
}
static void inline_mode(exr_font *font) {
  unsigned outer;
  for(outer=0;outer<2;outer++) {
    char a[80],b[80]; exr_attribute root={"style",a},span={"style",b};
    exr_document *doc=NULL; exr_layout *layout=NULL; exr_layout_config c=config();
    const exr_glyph *g; size_t n,i;
    exr_node_input nodes[]={{EXR_NODE_DOCUMENT,SIZE_MAX,NULL,NULL,NULL,0},
      {EXR_NODE_CHAPTER,0,NULL,NULL,&root,1},{EXR_NODE_PARAGRAPH,1,"p",NULL,NULL,0},
      {EXR_NODE_TEXT,2,NULL,"A",NULL,0},{EXR_NODE_ELEMENT,2,"span",NULL,&span,1},
      {EXR_NODE_TEXT,4,NULL,"\xe7\x94\xb2",NULL,0},{EXR_NODE_SECTION,4,"section",NULL,NULL,0},
      {EXR_NODE_TEXT,6,NULL,"A",NULL,0},{EXR_NODE_TEXT,2,NULL,"A",NULL,0}};
    exr_chapter_input chapter={"inline","inline.xhtml",1,1};
    exr_document_input input={"inline",nodes,9,&chapter,1,NULL,0};
    snprintf(a,sizeof(a),"writing-mode:%s",modes[outer]);
    snprintf(b,sizeof(b),"writing-mode:%s",modes[!outer]);
    OK(exr_document_create(&input,&doc,&error)); OK(exr_layout_create_ex(doc,font,&c,&layout,&error));
    g=exr_layout_glyphs(layout,&n); CHECK(n==4);
    for(i=0;i<n;i++) CHECK(!!(g[i].flags&EXR_GLYPH_VERTICAL)==(g[i].node==7 ? !outer : !!outer));
    positioned(doc,font,layout); exr_layout_free(layout); exr_document_free(doc);
  }
}
static void visible_viewport(exr_font *font) {
  const char *styles[]={"display:none;writing-mode:vertical-rl", "writing-mode:vertical-rl",
                        "writing-mode:vertical-rl", "writing-mode:vertical-rl"};
  const char *texts[]={"A", " \t\n", "", "A"}; size_t k;
  for(k=0;k<4;k++) {
    exr_document *doc=NULL; exr_layout *layout=NULL; exr_layout_config c=config();
    exr_attribute a={"style",styles[k]},b={"style","writing-mode:horizontal-tb"},hide={"style","display:none"};
    exr_node_input nodes[]={{EXR_NODE_DOCUMENT,SIZE_MAX,NULL,NULL,NULL,0},
      {EXR_NODE_CHAPTER,0,NULL,NULL,&a,1},{EXR_NODE_PARAGRAPH,1,"p",NULL,k==3 ? &hide : NULL,k==3 ? 1u : 0u},
      {EXR_NODE_TEXT,2,NULL,texts[k],NULL,0},{EXR_NODE_CHAPTER,0,NULL,NULL,&b,1},
      {EXR_NODE_PARAGRAPH,4,"p",NULL,NULL,0},{EXR_NODE_TEXT,5,NULL,"A",NULL,0}};
    exr_chapter_input chapters[]={{"ignored","ignored.xhtml",1,1},{"visible","visible.xhtml",4,1}};
    exr_document_input input={"visibility",nodes,7,chapters,2,NULL,0}; const exr_glyph *g; size_t n,i;
    OK(exr_document_create(&input,&doc,&error)); OK(exr_layout_create_ex(doc,font,&c,&layout,&error));
    CHECK(exr_layout_writing_mode(layout)==EXR_WRITING_HORIZONTAL_TB); g=exr_layout_glyphs(layout,&n);
    for(i=0;i<n;i++) if(g[i].node==6) CHECK(!(g[i].flags&EXR_GLYPH_VERTICAL));
    exr_layout_free(layout); exr_document_free(doc);
  }
  {
    exr_document *doc=NULL; exr_layout *layout=NULL; exr_layout_config c=config();
    exr_attribute hidden={"style","display:none;writing-mode:horizontal-tb"};
    exr_attribute visible={"style","writing-mode:vertical-lr"};
    exr_node_input nodes[]={{EXR_NODE_DOCUMENT,SIZE_MAX,NULL,NULL,NULL,0},
      {EXR_NODE_CHAPTER,0,NULL,NULL,NULL,0},{EXR_NODE_SECTION,1,"section",NULL,&hidden,1},
      {EXR_NODE_TEXT,2,NULL,"A",NULL,0},{EXR_NODE_SECTION,1,"section",NULL,NULL,0},
      {EXR_NODE_PARAGRAPH,1,"p",NULL,&visible,1},{EXR_NODE_TEXT,5,NULL,"A",NULL,0}};
    exr_chapter_input chapter={"visible","visible.xhtml",1,1};
    exr_document_input input={"visibility",nodes,7,&chapter,1,NULL,0};
    OK(exr_document_create(&input,&doc,&error)); OK(exr_layout_create_ex(doc,font,&c,&layout,&error));
    CHECK(exr_layout_writing_mode(layout)==EXR_WRITING_VERTICAL_LR);
    exr_layout_free(layout); exr_document_free(doc);
  }
}
int main(int argc,char **argv) {
  char path[4096]; exr_font *font=NULL; unsigned a,b;
  CHECK(argc==2); snprintf(path,sizeof(path),"%s/vertical-vrt2.ttf",argv[1]);
  OK(exr_font_open(path,&font,&error));
  for(a=0;a<3;a++) for(b=0;b<3;b++) if(a!=b) mixed(font,a,b);
  bounded(font); outer_geometry(font); nested(font); inline_mode(font); visible_viewport(font); exr_font_free(font);
  printf("%u orthogonal geometry, pagination, checkpoint and positioned checks passed\n",checks); return 0;
}
