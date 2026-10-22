/* SPDX-License-Identifier: MIT */
#include "exreader.h"
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static exr_error error; static unsigned checks; static exr_font *font;
#define CHECK(x) do { checks++; if(!(x)) { fprintf(stderr,"line %d: %s (%d: %s)\n",__LINE__,#x,error.code,error.message); exit(1); } } while(0)
#define OK(x) CHECK((x)==EXR_OK)
static int near(float a,float b) { return fabsf(a-b)<.002f; }
static exr_layout_config config(void) {
  exr_layout_config c=exr_layout_config_defaults(); c.page=(exr_layout_options){420,180,10,14,1.2f,0};
  c.user_css="table {width:200px;table-layout:fixed;background:white} td {padding:0;margin:0;vertical-align:top;background:#c0d0e0} tr,table {padding:0;margin:0}";
  return c;
}
/* Host construction exercises the same CSS cascade and pager as EPUB without
   adding generated binary fixtures to the repository. */
static exr_document *document(const char *css,const char *parent,int rows,int spans,int header,int tall) {
  exr_node_input nodes[2048]={{0}}; exr_attribute attrs[2048][3];
  exr_chapter_input chapter={"spacing","spacing.unit",1,1};
  exr_document_input input={"Border spacing",nodes,0,&chapter,1,NULL,0};
  exr_document *d=NULL; size_t used=3,group=2; int r,c;
  attrs[1][0]=(exr_attribute){"style",parent};
  nodes[0]=(exr_node_input){EXR_NODE_DOCUMENT,SIZE_MAX,NULL,NULL,NULL,0};
  nodes[1]=(exr_node_input){EXR_NODE_CHAPTER,0,"body",NULL,attrs[1],parent ? 1u : 0u};
  attrs[2][0]=(exr_attribute){"style",css};
  nodes[2]=(exr_node_input){EXR_NODE_TABLE,1,"table",NULL,attrs[2],1};
  for(r=0;r<rows;r++) {
    size_t row;
    if(header && r<2) { group=used++; nodes[group]=(exr_node_input){EXR_NODE_ELEMENT,2,r ? "tbody" : "thead",NULL,NULL,0}; }
    row=used++; nodes[row]=(exr_node_input){EXR_NODE_ROW,group,"tr",NULL,NULL,0};
    for(c=0;c<(spans ? 3 : 2);c++) {
      size_t cell,text; unsigned count=1; const char *ids[]={"a","b","c","d"};
      if(spans && r==1 && c!=1) continue;
      cell=used++; text=used++;
      attrs[cell][0]=(exr_attribute){"id",r==0 ? ids[c] : r==1 ? (spans ? "d" : c ? "d" : "c") : "later"};
      if(spans && r==0 && !c) attrs[cell][count++]=(exr_attribute){"rowspan","2"};
      if(spans && r==1) attrs[cell][count++]=(exr_attribute){"colspan","2"};
      attrs[cell][count++]=(exr_attribute){"style",tall && !r ? "height:400px;border:2px solid red" : "height:30px"};
      nodes[cell]=(exr_node_input){EXR_NODE_CELL,row,"td",NULL,attrs[cell],count};
      nodes[text]=(exr_node_input){EXR_NODE_TEXT,cell,NULL,tall && !r ? "A A A A A A A A A A A A A A A A A A A A" : "A",NULL,0};
    }
  }
  input.node_count=used; OK(exr_document_create(&input,&d,&error)); return d;
}
static size_t id(exr_document *d,const char *name) {
  size_t n,i; const exr_node *nodes=exr_document_nodes(d,&n);
  for(i=0;i<n;i++) { const char *v=exr_node_attribute(nodes+i,"id"); if(v && !strcmp(v,name)) return i; }
  CHECK(0); return SIZE_MAX;
}
static const exr_box *box(exr_document *d,const exr_layout *l,const char *name) {
  size_t node=id(d,name),n,i; const exr_box *b=exr_layout_boxes(l,&n);
  for(i=0;i<n;i++) if(b[i].node==node && b[i].kind==EXR_BOX_CELL) return b+i;
  CHECK(0); return NULL;
}
static void grid(const char *css,const char *parent,float horizontal,float vertical) {
  exr_document *d=document(css,parent,2,0,0,0); exr_layout_config cfg=config(); exr_layout *l=NULL;
  const exr_box *a,*b,*c,*e; size_t n,i; const exr_box *all;
  OK(exr_layout_create_ex(d,font,&cfg,&l,&error)); a=box(d,l,"a"); b=box(d,l,"b"); c=box(d,l,"c"); e=box(d,l,"d");
  CHECK(near(a->x,10+horizontal) && near(a->y,10+vertical));
  CHECK(near(a->width,(200-3*horizontal)/2) && near(a->height,30));
  CHECK(near(b->x-a->x-a->width,horizontal)); CHECK(near(c->y-a->y-a->height,vertical));
  CHECK(near(b->x+b->width,210-horizontal) && near(e->y+e->height,70+2*vertical));
  all=exr_layout_boxes(l,&n); for(i=0;i<n;i++) if(all[i].node==2 && all[i].kind==EXR_BOX_BLOCK) {
    CHECK(near(all[i].width,200) && near(all[i].height,60+3*vertical)); break;
  }
  CHECK(i<n); exr_layout_free(l); exr_document_free(d);
}
static void spans(void) {
  exr_document *d=document("border-spacing:7px 11px",NULL,2,1,0,0); exr_layout_config cfg=config(); exr_layout *l=NULL;
  const exr_box *a,*b,*c,*e;
  OK(exr_layout_create_ex(d,font,&cfg,&l,&error)); a=box(d,l,"a"); b=box(d,l,"b"); c=box(d,l,"c"); e=box(d,l,"d");
  CHECK(near(b->x-a->x-a->width,7) && near(c->x-b->x-b->width,7));
  CHECK(near(e->width,b->width+c->width+7) && near(e->x,b->x));
  CHECK(near(a->height,b->height+e->height+11) && near(e->y,b->y+b->height+11));
  exr_layout_free(l); exr_document_free(d);
}
static void vertical(int lr) {
  exr_document *d=document("border-spacing:7px 11px;height:200px;width:auto",lr ? "writing-mode:vertical-lr" : "writing-mode:vertical-rl",2,0,0,0);
  exr_layout_config cfg=config(); exr_layout *l=NULL; const exr_box *a,*b,*c;
  cfg.user_css="table {table-layout:fixed} td {padding:0;margin:0;width:30px;vertical-align:top;text-orientation:upright;background:#c0d0e0}";
  OK(exr_layout_create_ex(d,font,&cfg,&l,&error)); a=box(d,l,"a"); b=box(d,l,"b"); c=box(d,l,"c");
  CHECK(near(a->y,21) && near(a->height,(200-33)/2.0f));
  CHECK(near(b->y-a->y-a->height,11));
  CHECK(lr ? near(c->x-a->x-a->width,7) : near(a->x-c->x-c->width,7));
  exr_layout_free(l); exr_document_free(d);
}
static void same_page(const exr_layout *whole,size_t page,const exr_layout *one) {
  size_t n,m,i,j=0; const exr_glyph *a=exr_layout_glyphs(whole,&n),*b=exr_layout_glyphs(one,&m);
  exr_bitmap x={0},y={0};
  for(i=0;i<n;i++) if(a[i].page==page) {
    CHECK(j<m && a[i].node==b[j].node && a[i].start==b[j].start && a[i].end==b[j].end && a[i].glyph==b[j].glyph && near(a[i].x,b[j].x) && near(a[i].baseline,b[j].baseline));
    CHECK(exr_layout_hit_test(whole,page,a[i].x+.1f,a[i].baseline-2)==exr_layout_hit_test(one,0,b[j].x+.1f,b[j].baseline-2)); j++;
  }
  CHECK(j==m); OK(exr_render_page_color(whole,NULL,page,&x,&error)); OK(exr_render_page_color(one,NULL,0,&y,&error));
  CHECK(x.width==y.width && x.height==y.height && x.stride==y.stride && !memcmp(x.pixels,y.pixels,(size_t)x.stride*x.height));
  exr_bitmap_free(&x); exr_bitmap_free(&y);
}
static void pages(int header,int tall,int vertical_mode) {
  exr_document *d=document("border-spacing:7px 11px",vertical_mode ? "writing-mode:vertical-rl" : NULL,60,0,header,tall);
  exr_layout_config cfg=config(); exr_layout *whole=NULL; exr_pager *fast=NULL,*slow=NULL; size_t np,i,targets[7];
  if(vertical_mode) { cfg.page.width=180; cfg.page.height=420; cfg.user_css="table {height:200px;table-layout:fixed} td {width:30px;vertical-align:top;text-orientation:upright;background:#c0d0e0}"; }
  OK(exr_layout_create_ex(d,font,&cfg,&whole,&error)); exr_layout_pages(whole,&np); CHECK(np>5);
  OK(exr_pager_create(d,font,&cfg,&fast,&error)); OK(exr_pager_create(d,font,&cfg,&slow,&error));
  OK(exr_pager_set_cache(fast,1,262144,&error)); OK(exr_pager_set_checkpoints(fast,32,8*1024*1024,1,&error));
  OK(exr_pager_set_checkpoints(slow,0,0,0,&error));
  targets[0]=np-1; targets[1]=np/2; targets[2]=0; targets[3]=np-2; targets[4]=1; targets[5]=np/3; targets[6]=np-1;
  for(i=0;i<7;i++) { const exr_layout *a=NULL,*b=NULL; OK(exr_pager_get(fast,targets[i],&a,&error)); OK(exr_pager_get(slow,targets[i],&b,&error)); CHECK(a && b); same_page(whole,targets[i],a); same_page(a,0,b); }
  CHECK(exr_pager_statistics(fast).restored_checkpoints>0);
  exr_pager_free(fast); exr_pager_free(slow); exr_layout_free(whole); exr_document_free(d);
}
int main(int argc,char **argv) {
  char path[4096]; CHECK(argc==2); snprintf(path,sizeof(path),"%s/fonts/primary.ttf",argv[1]); OK(exr_font_open(path,&font,&error));
  grid("",NULL,0,0); grid("border-spacing:7px",NULL,7,7); grid("border-spacing:7px 11px",NULL,7,11);
  grid("border-spacing:0",NULL,0,0); grid("border-spacing:7px 11px;border-spacing:-1px",NULL,7,11);
  grid("border-spacing:7px 11px;border-spacing:3px 4px 5px",NULL,7,11);
  grid("border-spacing:7px 11px;border-spacing:10%",NULL,7,11);
  grid("border-spacing:7px 11px;border-spacing:auto",NULL,7,11);
  grid("border-spacing:7px 11px;border-collapse:collapse",NULL,0,0);
  grid("", "border-spacing:7px 11px",7,11); grid("border-spacing:inherit","border-spacing:7px 11px",7,11);
  grid("border-spacing:initial","border-spacing:7px 11px",0,0); grid("border-spacing:unset","border-spacing:7px 11px",7,11);
  grid("font-size:14px;border-spacing:.5em",NULL,7,7);
  spans(); vertical(0); vertical(1); pages(0,0,0); pages(1,0,0); pages(0,1,0); pages(0,0,1);
  exr_font_free(font); printf("%u table spacing checks passed\n",checks); return 0;
}
