/* SPDX-License-Identifier: GPL-3.0-only */
#include "exreader.h"
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static exr_error error; static unsigned checks;
#define CHECK(x) do { checks++; if(!(x)) { fprintf(stderr,"line %d: %s (%d: %s)\n",__LINE__,#x,error.code,error.message); exit(1); } } while(0)
#define OK(x) CHECK((x)==EXR_OK)
static int near(float a,float b) { return fabsf(a-b)<.002f; }
static exr_layout_config config(void) { exr_layout_config c=exr_layout_config_defaults(); c.page=(exr_layout_options){420,120,10,14,1.2f,0}; return c; }
static exr_document *open_book(const char *dir,const char *name) {
  char path[4096]; exr_document *d=NULL; snprintf(path,sizeof(path),"%s/%s.epub",dir,name); OK(exr_document_open(path,&d,&error)); return d;
}
static size_t id(const exr_document *d,const char *name) {
  size_t n,i; const exr_node *nodes=exr_document_nodes(d,&n);
  for(i=0;i<n;i++) { size_t j; for(j=0;j<nodes[i].attribute_count;j++) if(!strcmp(nodes[i].attributes[j].name,"id") && !strcmp(nodes[i].attributes[j].value,name)) return i; }
  CHECK(0); return SIZE_MAX;
}
static const exr_box *box(const exr_document *d,const exr_layout *l,const char *name) {
  size_t node=id(d,name),n,i; const exr_box *b=exr_layout_boxes(l,&n);
  for(i=0;i<n;i++) if(b[i].node==node && b[i].kind==EXR_BOX_CELL) return b+i;
  CHECK(0); return NULL;
}
static void dimensions(const char *dir,const char *name,exr_font *font,float a,float b,float c,int vertical) {
  exr_document *d=open_book(dir,name); exr_layout_config cfg=config(); exr_layout *l=NULL;
  const exr_box *x,*y,*z=NULL;
  if(vertical) cfg.page.height=340;
  { exr_status status=exr_layout_create_ex(d,font,&cfg,&l,&error); if(status!=EXR_OK) fprintf(stderr,"fixture %s\n",name); CHECK(status==EXR_OK); }
  x=box(d,l,"a"); y=box(d,l,"b"); if(c) z=box(d,l,"c");
  CHECK(near(vertical ? x->height : x->width,a)); CHECK(near(vertical ? y->height : y->width,b));
  CHECK(near(vertical ? y->y : y->x,(vertical ? x->y : x->x)+a));
  if(z) { CHECK(near(vertical ? z->height : z->width,c)); CHECK(near(vertical ? z->y : z->x,(vertical ? y->y : y->x)+b)); }
  if(!strcmp(name,"table-cell-widths")) {
    size_t n,i; const exr_line *lines=exr_layout_lines(l,&n); const exr_glyph *g=exr_layout_glyphs(l,NULL); float maximum=0;
    for(i=0;i<n;i++) if(lines[i].glyph_count && g[lines[i].glyph_start].node!=SIZE_MAX &&
        g[lines[i].glyph_start].start>=x->start && g[lines[i].glyph_start].end<=x->end) maximum=fmaxf(maximum,lines[i].width);
    CHECK(maximum>20 && maximum<=50); /* No second 25% width inside a 50px cell. */
  }
  exr_layout_free(l); exr_document_free(d);
}
static void same(const exr_layout *a,const exr_layout *b) {
  size_t n,m,i; const exr_box *ab=exr_layout_boxes(a,&n),*bb=exr_layout_boxes(b,&m); exr_bitmap x={0},y={0};
  CHECK(n==m); for(i=0;i<n;i++) CHECK(ab[i].node==bb[i].node && ab[i].kind==bb[i].kind && near(ab[i].x,bb[i].x) && near(ab[i].y,bb[i].y) && near(ab[i].width,bb[i].width) && near(ab[i].height,bb[i].height));
  { const exr_glyph *ag=exr_layout_glyphs(a,&n),*bg=exr_layout_glyphs(b,&m); CHECK(n==m);
    for(i=0;i<n;i++) CHECK(ag[i].start==bg[i].start && ag[i].end==bg[i].end && ag[i].glyph==bg[i].glyph && near(ag[i].x,bg[i].x) && near(ag[i].baseline,bg[i].baseline));
  }
  OK(exr_render_page_color(a,NULL,0,&x,&error)); OK(exr_render_page_color(b,NULL,0,&y,&error));
  CHECK(x.width==y.width && x.height==y.height && x.stride==y.stride && !memcmp(x.pixels,y.pixels,(size_t)x.stride*x.height));
  exr_bitmap_free(&x); exr_bitmap_free(&y);
}
static void whole_page(const exr_layout *whole,size_t page,const exr_layout *one) {
  size_t n,m,i,j=0; const exr_glyph *a=exr_layout_glyphs(whole,&n),*b=exr_layout_glyphs(one,&m); exr_bitmap x={0},y={0};
  for(i=0;i<n;i++) if(a[i].page==page) {
    CHECK(j<m && a[i].start==b[j].start && a[i].end==b[j].end && a[i].glyph==b[j].glyph &&
          near(a[i].x,b[j].x) && near(a[i].baseline,b[j].baseline));
    CHECK(exr_layout_hit_test(whole,page,a[i].x+.1f,a[i].baseline-2)==exr_layout_hit_test(one,0,b[j].x+.1f,b[j].baseline-2)); j++;
  }
  CHECK(j==m); OK(exr_render_page_color(whole,NULL,page,&x,&error)); OK(exr_render_page_color(one,NULL,0,&y,&error));
  CHECK(x.stride==y.stride && x.height==y.height && !memcmp(x.pixels,y.pixels,(size_t)x.stride*x.height));
  exr_bitmap_free(&x); exr_bitmap_free(&y);
}
static void checkpoints(const char *dir,exr_font *font) {
  exr_document *d=open_book(dir,"table-columns"); exr_layout_config cfg=config(); exr_pager *p=NULL,*baseline=NULL;
  const exr_layout *a,*b; size_t i,targets[]={15,12,2,8,0,15,4}; exr_layout *whole=NULL; const exr_box *x,*y,*z,*span;
  OK(exr_layout_create_ex(d,font,&cfg,&whole,&error)); x=box(d,whole,"a"); y=box(d,whole,"b"); z=box(d,whole,"c"); span=box(d,whole,"span");
  CHECK(near(x->width,80) && near(y->width,100) && near(z->width,220) && near(span->width,320));
  CHECK(near(x->height,y->height+span->height) && near(span->x,y->x));
  OK(exr_pager_create(d,font,&cfg,&p,&error)); OK(exr_pager_create(d,font,&cfg,&baseline,&error));
  OK(exr_pager_set_cache(p,1,1,&error)); CHECK(exr_pager_get(p,0,&a,&error)==EXR_LIMIT && !a);
  OK(exr_pager_set_cache(p,1,65536,&error)); OK(exr_pager_set_checkpoints(p,32,1024*1024,1,&error)); OK(exr_pager_set_checkpoints(baseline,0,0,0,&error));
  for(i=0;i<sizeof(targets)/sizeof(*targets);i++) { OK(exr_pager_get(p,targets[i],&a,&error)); OK(exr_pager_get(baseline,targets[i],&b,&error)); CHECK(a && b); same(a,b); whole_page(whole,targets[i],a); }
  CHECK(exr_pager_statistics(p).restored_checkpoints>0);
  exr_pager_free(p); exr_pager_free(baseline); exr_layout_free(whole); exr_document_free(d);
}
int main(int argc,char **argv) {
  char path[4096]; exr_font *font=NULL; exr_document *d; exr_layout *l=NULL; exr_layout_config cfg=config();
  CHECK(argc==2); snprintf(path,sizeof(path),"%s/fonts/primary.ttf",argv[1]); OK(exr_font_open(path,&font,&error));
  dimensions(argv[1],"table-cell-widths",font,50,150,0,0);
  dimensions(argv[1],"table-span-widths",font,90,90,120,0);
  dimensions(argv[1],"table-group-widths",font,60,60,180,0);
  dimensions(argv[1],"table-overconstrained",font,180,60,0,0);
  dimensions(argv[1],"table-vertical-columns",font,60,90,150,1);
  dimensions(argv[1],"table-tiny-column",font,1,99,0,0);
  dimensions(argv[1],"table-max-columns",font,63,1,0,0);
  dimensions(argv[1],"table-column-padding",font,26,174,0,0);
  checkpoints(argv[1],font);
  d=open_book(argv[1],"table-column-overflow"); CHECK(exr_layout_create_ex(d,font,&cfg,&l,&error)==EXR_LIMIT && !l); exr_document_free(d);
  exr_font_free(font); printf("%u table column checks passed\n",checks); return 0;
}
