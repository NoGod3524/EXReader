/* SPDX-License-Identifier: MIT */
#include "exreader.h"
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static exr_error error; static unsigned checks; static const char *directory; static exr_font *font;
#define CHECK(x) do { checks++; if(!(x)) { fprintf(stderr,"line %d: %s (%d: %s)\n",__LINE__,#x,error.code,error.message); exit(1); } } while(0)
#define OK(x) CHECK((x)==EXR_OK)
static int near(float a,float b) { return fabsf(a-b)<.03f; }
static exr_layout_config config(void) { exr_layout_config c=exr_layout_config_defaults(); c.page=(exr_layout_options){420,160,10,14,1.2f,0}; return c; }
static exr_document *book(const char *name) { char path[4096]; exr_document *d=NULL; snprintf(path,sizeof(path),"%s/table-align-%s.epub",directory,name); OK(exr_document_open(path,&d,&error)); return d; }
static exr_layout *layout(exr_document *d) { exr_layout_config c=config(); exr_layout *l=NULL; OK(exr_layout_create_ex(d,font,&c,&l,&error)); return l; }
static size_t node(const exr_document *d,const char *name) {
  size_t i,n; const exr_node *nodes=exr_document_nodes(d,&n);
  for(i=0;i<n;i++) { const char *id=exr_node_attribute(nodes+i,"id"); if(id && !strcmp(id,name)) return i; }
  CHECK(0); return SIZE_MAX;
}
static const exr_box *box(const exr_document *d,const exr_layout *l,const char *name) {
  size_t id=node(d,name),i,n; const exr_box *b=exr_layout_boxes(l,&n);
  for(i=0;i<n;i++) if(b[i].node==id) return b+i;
  CHECK(0); return NULL;
}
static int inside(const exr_document *d,size_t id,size_t leaf) {
  const exr_node *nodes=exr_document_nodes(d,NULL);
  while(leaf!=SIZE_MAX) { if(id==leaf) return 1; leaf=nodes[leaf].parent; } return 0;
}
static const exr_glyph *glyph(const exr_document *d,const exr_layout *l,const char *name) {
  size_t id=node(d,name),i,n; const exr_glyph *g=exr_layout_glyphs(l,&n);
  for(i=0;i<n;i++) if(inside(d,id,g[i].node)) return g+i;
  CHECK(0); return NULL;
}
static const exr_line *line(const exr_document *d,const exr_layout *l,const char *name) {
  size_t id=node(d,name),i,n; const exr_line *lines=exr_layout_lines(l,&n); const exr_glyph *g=exr_layout_glyphs(l,NULL);
  for(i=0;i<n;i++) if(lines[i].glyph_count && inside(d,id,g[lines[i].glyph_start].node)) return lines+i;
  CHECK(0); return NULL;
}
static void modes(void) {
  exr_document *d=book("modes"),*control=book("control"); exr_layout *l=layout(d),*before=layout(control); exr_bitmap bitmap={0};
  const exr_box *middle=box(d,l,"middle"),*panel=box(d,l,"panel"),*image=box(d,l,"image"),*bottom=box(d,l,"bottom");
  float mid=(middle->height-(box(control,before,"panel")->height+8))/2;
  float low=bottom->height-(line(control,before,"bottom")->height+8);
  CHECK(near(middle->height,108) && near(bottom->height,108) && near(box(d,l,"top")->height,108));
  CHECK(near(glyph(d,l,"top")->baseline,glyph(control,before,"top")->baseline));
  CHECK(near(glyph(d,l,"middle")->baseline,glyph(control,before,"middle")->baseline+mid));
  CHECK(near(panel->y,box(control,before,"panel")->y+mid) && near(image->y,box(control,before,"image")->y+mid));
  CHECK(near(glyph(d,l,"bottom")->baseline,glyph(control,before,"bottom")->baseline+low));
  CHECK(near(middle->y,box(control,before,"middle")->y));
  CHECK(exr_layout_hit_test(l,0,glyph(d,l,"middle")->x+.1f,glyph(d,l,"middle")->baseline-2)==glyph(d,l,"middle")->start);
  OK(exr_render_page_color(l,NULL,0,&bitmap,&error));
  { size_t x=(size_t)(middle->x+middle->width-2),y=(size_t)(middle->y+10); const unsigned char *p=bitmap.pixels+y*(size_t)bitmap.stride+x*4;
    CHECK(p[0]==224 && p[1]==224 && p[2]==224); /* Background stays at the full cell, not at the shifted content. */
    x=(size_t)(image->x+image->width/2); y=(size_t)(image->y+image->height/2); p=bitmap.pixels+y*(size_t)bitmap.stride+x*4;
    CHECK(p[0]==0 && p[1]==128 && p[2]==255);
  }
  exr_bitmap_free(&bitmap); exr_layout_free(l); exr_layout_free(before); exr_document_free(d); exr_document_free(control);
}
static void baseline(void) {
  exr_document *d=book("baseline"); exr_layout *l=layout(d); const exr_box *image=box(d,l,"image");
  CHECK(near(glyph(d,l,"small")->baseline,glyph(d,l,"big")->baseline));
  CHECK(near(image->y+image->height,glyph(d,l,"big")->baseline));
  CHECK(near(box(d,l,"small")->height,box(d,l,"big")->height));
  exr_layout_free(l); exr_document_free(d);
  d=book("rowspan"); l=layout(d);
  CHECK(near(glyph(d,l,"span")->baseline,glyph(d,l,"big")->baseline));
  CHECK(near(box(d,l,"span")->height,box(d,l,"big")->height+box(d,l,"lower")->height));
  exr_layout_free(l); exr_document_free(d);
  d=book("nested"); l=layout(d); CHECK(near(glyph(d,l,"nested")->baseline,glyph(d,l,"peer")->baseline)); exr_layout_free(l); exr_document_free(d);
  d=book("ruby"); l=layout(d); CHECK(near(glyph(d,l,"base")->baseline,glyph(d,l,"peer")->baseline));
  CHECK(glyph(d,l,"annotation")->baseline<glyph(d,l,"base")->baseline); exr_layout_free(l); exr_document_free(d);
  d=book("empty"); l=layout(d); CHECK(near(box(d,l,"empty")->height,100) && glyph(d,l,"text")->baseline-box(d,l,"text")->y<30); exr_layout_free(l); exr_document_free(d);
  d=book("nested-fallback"); l=layout(d);
  CHECK(near(glyph(d,l,"peer")->baseline,box(d,l,"inner")->y+box(d,l,"inner")->height-2));
  CHECK(glyph(d,l,"peer")->baseline>glyph(d,l,"inner")->baseline); exr_layout_free(l); exr_document_free(d);
  d=book("baseline-values"); l=layout(d);
  CHECK(near(glyph(d,l,"small")->baseline,glyph(d,l,"big")->baseline) && near(glyph(d,l,"length")->baseline,glyph(d,l,"big")->baseline));
  exr_layout_free(l); exr_document_free(d);
}
static void inheritance(void) {
  exr_document *d=book("inherit"); exr_layout *l=layout(d); const exr_line *small=line(d,l,"small"),*big=line(d,l,"big");
  CHECK(near(small->y+small->height,big->y+big->height)); exr_layout_free(l); exr_document_free(d);
  d=book("override"); l=layout(d); CHECK(near(line(d,l,"small")->y,box(d,l,"small")->y+2)); exr_layout_free(l); exr_document_free(d);
}
static void vertical(void) {
  exr_document *d=book("vertical"); exr_layout *l=layout(d); const exr_box *cell; const exr_line *content;
  cell=box(d,l,"top"); content=line(d,l,"top"); CHECK(near(content->x+content->width,cell->x+cell->width));
  cell=box(d,l,"middle"); content=line(d,l,"middle"); CHECK(near(content->x+content->width/2,cell->x+cell->width/2));
  cell=box(d,l,"bottom"); content=line(d,l,"bottom"); CHECK(near(content->x,cell->x));
  exr_layout_free(l); exr_document_free(d);
  d=book("vertical-baseline"); l=layout(d);
  CHECK(near(line(d,l,"small")->x+line(d,l,"small")->width/2,line(d,l,"big")->x+line(d,l,"big")->width/2));
  exr_layout_free(l); exr_document_free(d);
  d=book("vertical-lr"); l=layout(d);
  cell=box(d,l,"top"); content=line(d,l,"top"); CHECK(near(content->x,cell->x));
  cell=box(d,l,"middle"); content=line(d,l,"middle"); CHECK(near(content->x+content->width/2,cell->x+cell->width/2));
  cell=box(d,l,"bottom"); content=line(d,l,"bottom"); CHECK(near(content->x+content->width,cell->x+cell->width));
  exr_layout_free(l); exr_document_free(d);
  d=book("opposite-directions"); l=layout(d);
  CHECK(near(glyph(d,l,"small")->x,glyph(d,l,"big")->x)); exr_layout_free(l); exr_document_free(d);
}
static void pages(void) {
  exr_document *d=book("pages"); exr_layout_config c=config(); exr_layout *whole=layout(d); exr_pager *fast=NULL,*slow=NULL;
  const exr_layout *a,*b; size_t count,i,targets[]={20,15,2,11,0,20,4}; exr_layout_pages(whole,&count); CHECK(count>20);
  OK(exr_pager_create(d,font,&c,&fast,&error)); OK(exr_pager_create(d,font,&c,&slow,&error));
  OK(exr_pager_set_cache(fast,1,65536,&error)); OK(exr_pager_set_checkpoints(fast,32,1024*1024,1,&error)); OK(exr_pager_set_checkpoints(slow,0,0,0,&error));
  for(i=0;i<sizeof(targets)/sizeof(*targets);i++) {
    size_t j,n,m; const exr_glyph *g,*h; exr_bitmap x={0},y={0},z={0};
    OK(exr_pager_get(fast,targets[i],&a,&error)); OK(exr_pager_get(slow,targets[i],&b,&error)); CHECK(a && b);
    g=exr_layout_glyphs(a,&n); h=exr_layout_glyphs(b,&m); CHECK(n==m);
    for(j=0;j<n;j++) { CHECK(g[j].start==h[j].start && g[j].end==h[j].end && near(g[j].x,h[j].x) && near(g[j].baseline,h[j].baseline));
      CHECK(exr_layout_hit_test(a,0,g[j].x+.1f,g[j].baseline-2)==exr_layout_hit_test(whole,targets[i],g[j].x+.1f,g[j].baseline-2));
    }
    OK(exr_render_page_color(a,NULL,0,&x,&error)); OK(exr_render_page_color(b,NULL,0,&y,&error)); OK(exr_render_page_color(whole,NULL,targets[i],&z,&error));
    CHECK(x.stride==y.stride && x.stride==z.stride && x.height==y.height && x.height==z.height);
    CHECK(!memcmp(x.pixels,y.pixels,(size_t)x.stride*x.height) && !memcmp(x.pixels,z.pixels,(size_t)x.stride*x.height));
    exr_bitmap_free(&x); exr_bitmap_free(&y); exr_bitmap_free(&z);
  }
  CHECK(exr_pager_statistics(fast).restored_checkpoints>0); exr_pager_free(fast); exr_pager_free(slow); exr_layout_free(whole); exr_document_free(d);
  d=book("height"); whole=layout(d); exr_layout_pages(whole,&count); CHECK(count==2);
  for(i=0;i<4;i++) { char name[8]; const exr_box *cell; const exr_line *content; snprintf(name,sizeof(name),"r%zu",i); cell=box(d,whole,name); content=line(d,whole,name);
    CHECK(near(cell->height,50) && near(content->y+content->height/2,cell->y+cell->height/2));
  }
  exr_layout_free(whole); exr_document_free(d);
}
int main(int argc,char **argv) {
  char path[4096]; CHECK(argc==2); directory=argv[1]; snprintf(path,sizeof(path),"%s/fonts/primary.ttf",directory); OK(exr_font_open(path,&font,&error));
  modes(); baseline(); inheritance(); vertical(); pages(); exr_font_free(font); printf("%u table alignment checks passed\n",checks); return 0;
}
