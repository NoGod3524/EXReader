/* SPDX-License-Identifier: MIT */
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
static exr_font *open_font(const char *directory,const char *kind) {
  char path[4096]; exr_font *font=NULL;
  snprintf(path,sizeof(path),"%s/vertical-%s.ttf",directory,kind);
  OK(exr_font_open(path,&font,&error)); return font;
}
static exr_document *document(const char *text) {
  exr_document *doc=NULL; exr_attribute id={"id","body"};
  exr_node_input nodes[]={{EXR_NODE_DOCUMENT,SIZE_MAX,NULL,NULL,NULL,0},
    {EXR_NODE_CHAPTER,0,NULL,NULL,NULL,0},{EXR_NODE_PARAGRAPH,1,"p",NULL,&id,1},
    {EXR_NODE_TEXT,2,NULL,text,NULL,0}};
  exr_chapter_input chapter={"vertical","vertical.xhtml",1,1};
  exr_document_input input={"vertical",nodes,4,&chapter,1,NULL,0};
  OK(exr_document_create(&input,&doc,&error)); return doc;
}
static exr_layout_config config(const char *css) {
  exr_layout_config c=exr_layout_config_defaults();
  c.page.width=100; c.page.height=140; c.page.margin=10;
  c.page.font_size=20; c.page.line_height=1.2f; c.page.paragraph_spacing=0;
  c.user_css=css; return c;
}
static void shaping(const char *directory) {
  static const char *kinds[]={"plain","vert","vrt2"}; size_t i;
  for(i=0;i<3;i++) {
    exr_font *font=open_font(directory,kinds[i]); exr_shape_options options=exr_shape_defaults();
    exr_shaped_glyph *g=NULL; size_t n=0;
    options.font_size=20;
    OK(exr_shape_vertical(font,0,"\xe3\x80\x88",3,&options,&g,&n,&error));
    CHECK(n==1 && g[0].glyph==(i==0 ? 5u : i==1 ? 8u : 10u));
    CHECK(near(g[0].advance_x,0) && near(g[0].advance_y,-20) && (g[0].flags&EXR_GLYPH_VERTICAL));
    exr_free(g);
    OK(exr_shape(font,0,"\xe3\x80\x88",3,&options,&g,&n,&error));
    CHECK(n==1 && g[0].glyph==5 && near(g[0].advance_x,12) && !g[0].advance_y);
    exr_free(g);
    OK(exr_shape_vertical(font,0,"\xe7\x94\xb2\xe7\x94\xb2",6,&options,&g,&n,&error));
    CHECK(n==2 && near(g[0].advance_y,i ? -18 : -20) && near(g[1].advance_y,-20));
    exr_free(g);
    {
      exr_document *doc=document("\xe7\x94\xb2\xe7\x94\xb2");
      exr_layout_config c=config("#body {writing-mode:vertical-rl}"); exr_layout *layout=NULL;
      const exr_glyph *glyphs;
      OK(exr_layout_create_ex(doc,font,&c,&layout,&error)); glyphs=exr_layout_glyphs(layout,&n);
      CHECK(n==2 && near(glyphs[0].advance,i ? 18 : 20) && near(glyphs[1].advance,20));
      CHECK(near(glyphs[1].baseline-glyphs[0].baseline,glyphs[0].advance));
      exr_layout_free(layout); exr_document_free(doc);
    }
    exr_font_free(font);
  }
}
static void page_equal(const exr_layout *all,size_t page,const exr_layout *one) {
  size_t n,i,j; const exr_page *a=exr_layout_pages(all,NULL)+page,*b=exr_layout_pages(one,&n);
  const exr_line *la=exr_layout_lines(all,NULL),*lb=exr_layout_lines(one,NULL);
  const exr_glyph *ga=exr_layout_glyphs(all,NULL),*gb=exr_layout_glyphs(one,NULL);
  if(n!=1 || a->start!=b->start || a->end!=b->end || a->line_count!=b->line_count)
    fprintf(stderr,"page %zu expected %zu..%zu %zu lines; actual count %zu %zu..%zu %zu lines\n",
            page,a->start,a->end,a->line_count,n,b->start,b->end,b->line_count);
  CHECK(n==1 && a->start==b->start && a->end==b->end && a->line_count==b->line_count);
  CHECK(exr_layout_writing_mode(all)==exr_layout_writing_mode(one));
  for(i=0;i<b->line_count;i++) {
    const exr_line *x=&la[a->line_start+i],*y=&lb[b->line_start+i];
    CHECK(x->glyph_count==y->glyph_count && x->start==y->start && x->end==y->end &&
          near(x->x,y->x) && near(x->y,y->y) && near(x->width,y->width) && near(x->height,y->height));
    for(j=0;j<x->glyph_count;j++) {
      const exr_glyph *u=&ga[x->glyph_start+j],*v=&gb[y->glyph_start+j];
      CHECK(u->start==v->start && u->end==v->end && u->glyph==v->glyph && u->flags==v->flags &&
            near(u->x,v->x) && near(u->baseline,v->baseline) && near(u->advance,v->advance) &&
            near(u->offset_x,v->offset_x) && near(u->offset_y,v->offset_y));
    }
  }
}
static void positioned_roundtrip(exr_document *doc,exr_font *font,const exr_layout *layout) {
  size_t np,nl,ng,i,j,paint=0;
  const exr_page *pages=exr_layout_pages(layout,&np);
  const exr_line *lines=exr_layout_lines(layout,&nl);
  const exr_glyph *glyphs=exr_layout_glyphs(layout,&ng);
  exr_positioned_page *positioned=calloc(np,sizeof(*positioned));
  exr_paint *paints=calloc(ng,sizeof(*paints));
  exr_positioned_input input={0}; exr_layout_config c=config(NULL); exr_layout *copy=NULL;
  exr_bitmap a={0},b={0};
  CHECK(positioned && paints);
  for(i=0;i<np;i++) {
    positioned[i].width=100; positioned[i].height=140; positioned[i].content=pages[i];
    positioned[i].paint_start=paint;
    for(j=pages[i].line_start;j<pages[i].line_start+pages[i].line_count;j++) {
      size_t k;
      for(k=lines[j].glyph_start;k<lines[j].glyph_start+lines[j].glyph_count;k++)
        paints[paint++]=(exr_paint){EXR_PAINT_GLYPH,0,k};
    }
    positioned[i].paint_count=paint-positioned[i].paint_start;
  }
  CHECK(paint==ng);
  input.struct_size=sizeof(input); input.pages=positioned; input.page_count=np;
  input.glyphs=glyphs; input.glyph_count=ng; input.lines=lines; input.line_count=nl;
  input.paints=paints; input.paint_count=ng;
  c.page.margin=0;
  OK(exr_layout_create_positioned(doc,font,&input,&c,&copy,&error));
  for(i=0;i<np;i++) {
    OK(exr_render_page(layout,font,i,&a,&error)); OK(exr_render_page(copy,font,i,&b,&error));
    CHECK(a.width==b.width && a.height==b.height && a.stride==b.stride &&
          !memcmp(a.pixels,b.pixels,(size_t)a.stride*a.height));
    exr_bitmap_free(&a); exr_bitmap_free(&b);
  }
  for(i=0;i<ng;i++) if(glyphs[i].advance && !(glyphs[i].flags&EXR_GLYPH_HIDDEN)) {
    float x=glyphs[i].x,y=glyphs[i].baseline+glyphs[i].advance/4;
    CHECK(exr_layout_hit_test(layout,glyphs[i].page,x,y)==exr_layout_hit_test(copy,glyphs[i].page,x,y));
  }
  exr_layout_free(copy); free(paints); free(positioned);
}
static void verify_geometry(const exr_document *doc,const exr_layout *lay,int lr,int plain) {
  size_t n,i,j,size,lines,pages; const exr_glyph *g=exr_layout_glyphs(lay,&n);
  const exr_line *line=exr_layout_lines(lay,&lines); const char *text=exr_document_text(doc,&size);
  unsigned char *map=NULL; exr_bitmap bitmap={0}; unsigned saw_cjk=0,saw_latin=0,saw_tr=0,saw_tu=0;
  OK(exr_text_analyze(text,size,&map,&error)); CHECK(n && lines);
  CHECK(exr_layout_writing_mode(lay)==(lr ? EXR_WRITING_VERTICAL_LR : EXR_WRITING_VERTICAL_RL));
  for(i=0;i<n;i++) {
    double matrix[6]; size_t a,b;
    CHECK(g[i].flags&EXR_GLYPH_VERTICAL); CHECK(!(g[i].flags&~511u));
    CHECK(map[g[i].cluster_start]&EXR_BOUNDARY_GRAPHEME);
    CHECK(map[g[i].cluster_end]&EXR_BOUNDARY_GRAPHEME);
    OK(exr_glyph_matrix(&g[i],matrix,&error));
    if(g[i].flags&EXR_GLYPH_SIDEWAYS) CHECK(matrix[0]==0 && matrix[3]==0 && matrix[1]>0 && matrix[2]>0);
    else CHECK(matrix[0]>0 && matrix[3]<0 && !matrix[1] && !matrix[2]);
    if(g[i].codepoint==0x7532) { CHECK(!(g[i].flags&EXR_GLYPH_SIDEWAYS)); saw_cjk++; }
    if(g[i].codepoint=='A') { CHECK(g[i].flags&EXR_GLYPH_SIDEWAYS); saw_latin++; }
    if(g[i].codepoint==0x3008) { CHECK(!!(g[i].flags&EXR_GLYPH_SIDEWAYS)==!!plain); saw_tr++; }
    if(g[i].codepoint==0x3001) { CHECK(!(g[i].flags&EXR_GLYPH_SIDEWAYS)); saw_tu++; }
    if(g[i].advance && !(g[i].flags&EXR_GLYPH_HIDDEN)) {
      a=exr_layout_hit_test(lay,g[i].page,g[i].x,g[i].baseline+g[i].advance/4);
      b=exr_layout_hit_test(lay,g[i].page,g[i].x,g[i].baseline+g[i].advance*3/4);
      CHECK(a<=size && b<=size && (map[a]&EXR_BOUNDARY_GRAPHEME) && (map[b]&EXR_BOUNDARY_GRAPHEME));
    }
  }
  CHECK(saw_cjk && saw_latin && saw_tr && saw_tu);
  for(i=0;i<lines;i++) {
    CHECK(line[i].x>=9.99f && line[i].x+line[i].width<=90.01f && line[i].y>=9.99f);
    CHECK(line[i].y+line[i].height<=130.01f);
    if(i && line[i].page==line[i-1].page) CHECK(lr ? line[i].x>line[i-1].x : line[i].x<line[i-1].x);
  }
  exr_layout_pages(lay,&pages);
  for(i=0;i<pages;i++) {
    size_t ink=0;
    OK(exr_render_page(lay,NULL,i,&bitmap,&error)); CHECK(bitmap.width==100 && bitmap.height==140);
    for(j=0;j<(size_t)bitmap.stride*bitmap.height;j++) ink+=bitmap.pixels[j]<255;
    CHECK(ink>0); exr_bitmap_free(&bitmap);
  }
  exr_free(map);
}
static void layouts(const char *directory) {
  static const char text[]="\xe7\x94\xb2" "A\xcc\x81" "\xe3\x80\x88\xe3\x80\x81\xe7\x94\xb2"
    "A\xe3\x80\x88\xe3\x80\x81\xe7\x94\xb2" "A\xe3\x80\x88\xe3\x80\x81\xe7\x94\xb2"
    "A\xe3\x80\x88\xe3\x80\x81\xe7\x94\xb2" "A\xe3\x80\x88\xe3\x80\x81\xe7\x94\xb2"
    "A\xe3\x80\x88\xe3\x80\x81\xe7\x94\xb2" "A\xe3\x80\x88\xe3\x80\x81\xe7\x94\xb2";
  unsigned lr,plain;
  for(lr=0;lr<2;lr++) for(plain=0;plain<2;plain++) {
    exr_font *font=open_font(directory,plain ? "plain" : "vrt2"); exr_document *doc=document(text);
    exr_layout_config c=config(lr ? "#body {writing-mode:vertical-lr}" : "#body {writing-mode:vertical-rl}");
    exr_layout *all=NULL,*page=NULL; exr_pager *pager=NULL; const exr_layout *cached=NULL; size_t n,i;
    OK(exr_layout_create_ex(doc,font,&c,&all,&error)); verify_geometry(doc,all,(int)lr,(int)plain);
    positioned_roundtrip(doc,font,all);
    exr_layout_pages(all,&n); CHECK(n>1);
    OK(exr_pager_create(doc,font,&c,&pager,&error));
    for(i=0;i<n;i++) { OK(exr_pager_next(pager,&page,&error)); CHECK(page); page_equal(all,i,page); exr_layout_free(page); }
    OK(exr_pager_next(pager,&page,&error)); CHECK(!page); exr_pager_free(pager);
    OK(exr_pager_create(doc,font,&c,&pager,&error));
    OK(exr_pager_set_cache(pager,1,1024*1024,&error)); OK(exr_pager_set_checkpoints(pager,16,1024*1024,1,&error));
    OK(exr_pager_get(pager,n-1,&cached,&error)); page_equal(all,n-1,cached);
    OK(exr_pager_get(pager,0,&cached,&error)); page_equal(all,0,cached);
    OK(exr_pager_get(pager,n-1,&cached,&error)); page_equal(all,n-1,cached);
    exr_pager_free(pager); exr_layout_free(all); exr_document_free(doc); exr_font_free(font);
  }
}
static void overrides(const char *directory) {
  exr_font *font=open_font(directory,"vrt2"); exr_document *doc=document("\xe7\x94\xb2" "A");
  const char *css[]={"#body {writing-mode:vertical-rl;text-orientation:upright}",
                     "#body {writing-mode:vertical-lr;text-orientation:sideways}"};
  size_t k;
  for(k=0;k<2;k++) {
    exr_layout_config c=config(css[k]); exr_layout *lay=NULL; const exr_glyph *g; size_t n,i;
    OK(exr_layout_create_ex(doc,font,&c,&lay,&error)); g=exr_layout_glyphs(lay,&n);
    for(i=0;i<n;i++) CHECK(!!(g[i].flags&EXR_GLYPH_SIDEWAYS)==!!k);
    exr_layout_free(lay);
  }
  exr_document_free(doc); exr_font_free(font);
}
static void logical_anchors(const char *directory) {
  exr_font *font=open_font(directory,"vrt2");
  exr_document *doc=document("A\xe2\x80\x8b" "A\xc2\xad" "A\xe7\x94\xb2");
  exr_anchor anchor={0}; exr_anchor_match match={0}; exr_layout *layout=NULL;
  exr_layout_config c=config("#body {writing-mode:vertical-rl}");
  OK(exr_anchor_create(doc,4,7,&anchor,&error));
  OK(exr_layout_create_ex(doc,font,&c,&layout,&error));
  OK(exr_anchor_resolve(doc,&anchor,&match,&error));
  CHECK(match.state==EXR_ANCHOR_FOUND && match.start==4 && match.end==7);
  positioned_roundtrip(doc,font,layout);
  exr_anchor_free(&anchor); exr_layout_free(layout); exr_document_free(doc); exr_font_free(font);
}
static void clusters_and_modes(const char *directory) {
  exr_font *font=open_font(directory,"vrt2"); exr_document *doc=NULL;
  exr_attribute id={"id","body"},orient={"style","text-orientation:upright;font-size:24px"};
  exr_attribute other={"style","writing-mode:horizontal-tb"};
  exr_node_input nodes[]={{EXR_NODE_DOCUMENT,SIZE_MAX,NULL,NULL,NULL,0},
    {EXR_NODE_CHAPTER,0,NULL,NULL,NULL,0},{EXR_NODE_PARAGRAPH,1,"p",NULL,&id,1},
    {EXR_NODE_ELEMENT,2,"span",NULL,NULL,0},{EXR_NODE_TEXT,3,NULL,"A",NULL,0},
    {EXR_NODE_ELEMENT,2,"span",NULL,&orient,1},{EXR_NODE_TEXT,5,NULL,"\xcc\x81",NULL,0},
    {EXR_NODE_TEXT,2,NULL,"\xe7\x94\xb2",NULL,0}};
  exr_chapter_input chapter={"vertical","vertical.xhtml",1,1};
  exr_document_input input={"vertical",nodes,8,&chapter,1,NULL,0};
  exr_layout_config c=config("#body {writing-mode:vertical-rl}"); exr_layout *lay=NULL;
  const exr_glyph *g; size_t n,i,cluster=0;
  OK(exr_document_create(&input,&doc,&error)); OK(exr_layout_create_ex(doc,font,&c,&lay,&error));
  g=exr_layout_glyphs(lay,&n);
  for(i=0;i<n;i++) if(g[i].cluster_start==0) {
    CHECK(g[i].cluster_end==3 && (g[i].flags&EXR_GLYPH_SIDEWAYS)); cluster++;
  }
  CHECK(cluster==2); exr_layout_free(lay); exr_document_free(doc); lay=NULL; doc=NULL;
  nodes[5].kind=EXR_NODE_PARAGRAPH; nodes[5].name="p";
  nodes[5].attributes=&other; nodes[5].attribute_count=1;
  OK(exr_document_create(&input,&doc,&error));
  OK(exr_layout_create_ex(doc,font,&c,&lay,&error));
  g=exr_layout_glyphs(lay,&n); CHECK(n==3);
  for(i=0;i<n;i++) CHECK(!!(g[i].flags&EXR_GLYPH_VERTICAL)==(g[i].node!=6));
  exr_layout_free(lay); exr_document_free(doc); exr_font_free(font);
  {
    char path[4096]; exr_shaped_glyph *shaped=NULL; exr_shape_options options=exr_shape_defaults();
    snprintf(path,sizeof(path),"%s/primary.ttf",directory); OK(exr_font_open(path,&font,&error));
    options.font_size=20;
    OK(exr_shape_vertical(font,0,"A",1,&options,&shaped,&n,&error));
    CHECK(n==1 && near(shaped[0].advance_y,-20)); /* No vmtx: one em. */
    exr_free(shaped); exr_font_free(font);
  }
}
static void outline_geometry(const char *directory) {
  exr_font *font=open_font(directory,"vrt2"); exr_document *doc=document("A");
  exr_layout_config c=config("#body {writing-mode:vertical-lr}");
  exr_layout *layout=NULL; const exr_glyph *glyph; exr_path_segment *path=NULL;
  exr_bitmap bitmap={0}; double matrix[6],minx=1e6,miny=1e6,maxx=-1e6,maxy=-1e6;
  size_t n,i,j; unsigned left=1000,top=1000,right=0,bottom=0;
  OK(exr_layout_create_ex(doc,font,&c,&layout,&error)); glyph=exr_layout_glyphs(layout,&n); CHECK(n==1);
  OK(exr_glyph_matrix(glyph,matrix,&error));
  OK(exr_font_glyph_outline(font,0,glyph->glyph,&path,&n,NULL,&error));
  for(i=0;i<n;i++) {
    size_t points=path[i].verb==EXR_PATH_CUBIC ? 3u : path[i].verb==EXR_PATH_QUAD ? 2u :
                  path[i].verb==EXR_PATH_CLOSE ? 0u : 1u;
    for(j=0;j<points;j++) {
      double x=matrix[0]*path[i].points[j].x+matrix[2]*path[i].points[j].y+matrix[4];
      double y=matrix[1]*path[i].points[j].x+matrix[3]*path[i].points[j].y+matrix[5];
      minx=fmin(minx,x); miny=fmin(miny,y); maxx=fmax(maxx,x); maxy=fmax(maxy,y);
    }
  }
  exr_free(path);
  OK(exr_render_page(layout,font,0,&bitmap,&error));
  for(i=0;i<bitmap.height;i++) for(j=0;j<bitmap.width;j++) if(bitmap.pixels[i*bitmap.stride+j]<255) {
    if(j<left) left=(unsigned)j;
    if(j>right) right=(unsigned)j;
    if(i<top) top=(unsigned)i;
    if(i>bottom) bottom=(unsigned)i;
  }
  CHECK(left<right && top<bottom && fabs((double)left-minx)<2 && fabs((double)top-miny)<2 &&
        fabs((double)right+1-maxx)<2 && fabs((double)bottom+1-maxy)<2);
  CHECK(right-left>bottom-top); /* Rotated triangle has the expected physical axes. */
  exr_bitmap_free(&bitmap); exr_layout_free(layout); exr_document_free(doc); exr_font_free(font);
}
int main(int argc,char **argv) {
  CHECK(argc==2); shaping(argv[1]); layouts(argv[1]); overrides(argv[1]); logical_anchors(argv[1]);
  clusters_and_modes(argv[1]); outline_geometry(argv[1]);
  CHECK(exr_layout_writing_mode(NULL)==EXR_WRITING_HORIZONTAL_TB);
  { double m[6]={1,1,1,1,1,1}; size_t i; CHECK(exr_glyph_matrix(NULL,m,&error)==EXR_ARGUMENT);
    for(i=0;i<6;i++) CHECK(!m[i]); }
  printf("%u vertical layout, orientation, shaping and pager checks passed\n",checks); return 0;
}
