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
static exr_layout_config config(void) { exr_layout_config c=exr_layout_config_defaults(); c.page=(exr_layout_options){420,180,10,14,1.2f,0}; return c; }
static exr_document *book(const char *name) { char path[4096]; exr_document *d=NULL; snprintf(path,sizeof(path),"%s/table-border-%s.epub",directory,name); OK(exr_document_open(path,&d,&error)); return d; }
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
static size_t borders(const exr_layout *l,size_t node_id) {
  size_t i,n,count=0; const exr_box *b=exr_layout_boxes(l,&n);
  for(i=0;i<n;i++) if((b[i].flags&EXR_BOX_BORDER) && (node_id==SIZE_MAX || b[i].node==node_id)) count++;
  return count;
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
  for(i=0;i<np;i++) { exr_bitmap a={0},b={0}; OK(exr_render_page_color(l,NULL,i,&a,&error)); OK(exr_render_page_color(copy,NULL,i,&b,&error)); CHECK(a.stride==b.stride && a.height==b.height && !memcmp(a.pixels,b.pixels,(size_t)a.stride*a.height)); exr_bitmap_free(&a); exr_bitmap_free(&b); }
  exr_layout_free(copy); free(pages); free(paints);
}
static void basic(void) {
  exr_document *d=book("basic"); exr_layout *l=layout(d); exr_bitmap image={0}; const exr_box *a=box(d,l,"a"),*b=box(d,l,"b"),*c=box(d,l,"c");
  CHECK(near(a->x,11) && near(a->y,11) && near(a->width,99) && near(a->height,42));
  CHECK(near(b->x,110) && near(c->y,53) && a->border_width==0 && b->border_width==0);
  CHECK(borders(l,SIZE_MAX)==12); OK(exr_render_page_color(l,NULL,0,&image,&error));
  CHECK(pixel(&image,108,30)==0xffffffff && pixel(&image,109,30)==0x0000ffff && pixel(&image,110,30)==0x0000ffff && pixel(&image,111,30)==0xffffffff);
  CHECK(pixel(&image,10,10)==0x0000ffff && pixel(&image,209,95)==0x0000ffff);
  exr_bitmap_free(&image); positioned(d,l); exr_layout_free(l); exr_document_free(d);
  d=book("separate"); l=layout(d); CHECK(!borders(l,SIZE_MAX) && near(box(d,l,"a")->border_width,2) && near(box(d,l,"a")->height,44)); exr_layout_free(l); exr_document_free(d);
  d=book("inapplicable"); l=layout(d); CHECK(near(box(d,l,"a")->x,11) && near(box(d,l,"a")->y,11) && near(box(d,l,"a")->width,99) && near(box(d,l,"a")->height,42)); exr_layout_free(l); exr_document_free(d);
  d=book("inherit"); l=layout(d); CHECK(borders(l,SIZE_MAX)==12 && near(box(d,l,"a")->height,42)); exr_layout_free(l); exr_document_free(d);
  d=book("mixed"); l=layout(d); a=box(d,l,"a"); b=box(d,l,"b"); CHECK(near(a->x,12) && near(a->height,44) && near(b->height,44)); OK(exr_render_page_color(l,NULL,0,&image,&error)); CHECK(pixel(&image,b->x,30)==0xff0000ff && pixel(&image,209,30)==0x0000ffff); exr_bitmap_free(&image); exr_layout_free(l); exr_document_free(d);
}
static void conflicts(void) {
  const char *names[]={"tie","rtl","hidden","none","groups","origin","wide-table"}; size_t i;
  for(i=0;i<sizeof(names)/sizeof(*names);i++) {
    exr_document *d=book(names[i]); exr_layout *l=layout(d); exr_bitmap image={0}; const exr_box *a=box(d,l,"a"),*b=box(d,l,"b"),*c=box(d,l,"c");
    OK(exr_render_page_color(l,NULL,0,&image,&error));
    if(i<2) { CHECK(pixel(&image,b->x,30)==(i ? 0x008000ff : 0xff0000ff)); CHECK(pixel(&image,50,c->y)==0xff0000ff); }
    if(i==2) { CHECK(pixel(&image,b->x,30)==0xffffffff && pixel(&image,50,c->y)==0xffffffff); CHECK(near(a->x,11) && near(a->height,42)); }
    if(i==3) CHECK(pixel(&image,b->x,30)==0x0000ffff && pixel(&image,50,c->y)==0x0000ffff);
    if(i==4) { CHECK(pixel(&image,11,30)==0x000000ff); CHECK(pixel(&image,b->x,30)==0x008000ff); CHECK(pixel(&image,11,c->y+15)==0x0000ffff); }
    if(i==5) CHECK(pixel(&image,b->x,30)==0xff00ffff && pixel(&image,11,30)==0xff00ffff);
    if(i==6) CHECK(pixel(&image,11,30)==0x808000ff);
    exr_bitmap_free(&image); exr_layout_free(l); exr_document_free(d);
  }
}
static void alpha(void) {
  exr_document *d=book("alpha"); exr_layout *l=layout(d); exr_bitmap image={0}; const exr_box *b=box(d,l,"b"),*c=box(d,l,"c");
  OK(exr_render_page_color(l,NULL,0,&image,&error));
  CHECK(pixel(&image,b->x,30)==0x7f7f7fff && pixel(&image,b->x,c->y)==0x7f7f7fff && pixel(&image,10,10)==0x7f7f7fff);
  exr_bitmap_free(&image); positioned(d,l); exr_layout_free(l); exr_document_free(d);
}
static void spans(void) {
  exr_document *d=book("spans"); exr_layout *l=layout(d); exr_bitmap image={0}; const exr_box *a=box(d,l,"a"),*b=box(d,l,"b"),*c=box(d,l,"c"),*e=box(d,l,"e");
  CHECK(near(a->height,b->height+c->height) && near(e->width,198)); OK(exr_render_page_color(l,NULL,0,&image,&error));
  CHECK(pixel(&image,a->x+20,c->y)==0xffffffff); CHECK(pixel(&image,c->x+c->width,30)==0xffffffff);
  CHECK(pixel(&image,c->x+c->width,c->y+20)==0x0000ffff);
  exr_bitmap_free(&image); positioned(d,l); exr_layout_free(l); exr_document_free(d);
}
static void nested(void) {
  const char *names[]={"nested","nested-separate","columns","vertical","vertical-lr","opposite"}; size_t i;
  for(i=0;i<sizeof(names)/sizeof(*names);i++) {
    exr_document *d=book(names[i]); exr_layout *l=layout(d); const exr_box *b=exr_layout_boxes(l,NULL); size_t n,j; exr_layout_boxes(l,&n);
    CHECK(borders(l,SIZE_MAX)>0);
    if(i<2) { CHECK(borders(l,node(d,"inner"))==(i ? 0u : 4u)); CHECK(near(box(d,l,"innercell")->border_width,i ? 2 : 0)); }
    for(j=0;j<n;j++) CHECK(b[j].x>=9.99f && b[j].y>=9.99f && b[j].x+b[j].width<=410.01f && b[j].y+b[j].height<=170.01f);
    if(i==3 || i==4) CHECK(near(box(d,l,"a")->height,79) && near(box(d,l,"a")->width,42));
    if(i==5) { const exr_line *ln=exr_layout_lines(l,NULL); const exr_box *a=box(d,l,"a");
      /* A physical right edge of 2px still reserves 1px when the inner block
         direction reverses; it must not inherit the left edge's 3px inset. */
      CHECK(near(ln[0].x+ln[0].width,a->x+a->width-1) && near(ln[0].y,a->y+1));
    }
    positioned(d,l); exr_layout_free(l); exr_document_free(d);
  }
}
static void pages(void) {
  exr_document *d=book("pages"); exr_layout_config cfg=config(); exr_layout *whole=layout(d); exr_pager *fast=NULL,*slow=NULL; const exr_layout *a,*b;
  size_t count,i,targets[]={11,9,2,7,0,11,4}; exr_layout_pages(whole,&count); CHECK(count>11);
  OK(exr_pager_create(d,font,&cfg,&fast,&error)); OK(exr_pager_create(d,font,&cfg,&slow,&error));
  OK(exr_pager_set_cache(fast,1,65536,&error)); OK(exr_pager_set_checkpoints(fast,32,1024*1024,1,&error)); OK(exr_pager_set_checkpoints(slow,0,0,0,&error));
  for(i=0;i<sizeof(targets)/sizeof(*targets);i++) {
    size_t j,n,m; const exr_glyph *g,*h; const exr_box *boxes; exr_bitmap x={0},y={0},z={0};
    OK(exr_pager_get(fast,targets[i],&a,&error)); OK(exr_pager_get(slow,targets[i],&b,&error)); CHECK(a && b);
    g=exr_layout_glyphs(a,&n); h=exr_layout_glyphs(b,&m); CHECK(n==m);
    for(j=0;j<n;j++) CHECK(g[j].start==h[j].start && near(g[j].x,h[j].x) && near(g[j].baseline,h[j].baseline) && exr_layout_hit_test(a,0,g[j].x+.1f,g[j].baseline-2)==exr_layout_hit_test(whole,targets[i],g[j].x+.1f,g[j].baseline-2));
    boxes=exr_layout_boxes(a,&n); for(j=0;j<n;j++) CHECK(boxes[j].x>=9.99f && boxes[j].y>=9.99f && boxes[j].x+boxes[j].width<=410.01f && boxes[j].y+boxes[j].height<=170.01f);
    OK(exr_render_page_color(a,NULL,0,&x,&error)); OK(exr_render_page_color(b,NULL,0,&y,&error)); OK(exr_render_page_color(whole,NULL,targets[i],&z,&error));
    CHECK(x.stride==y.stride && x.stride==z.stride && x.height==y.height && x.height==z.height && !memcmp(x.pixels,y.pixels,(size_t)x.stride*x.height) && !memcmp(x.pixels,z.pixels,(size_t)x.stride*x.height));
    exr_bitmap_free(&x); exr_bitmap_free(&y); exr_bitmap_free(&z);
  }
  CHECK(exr_pager_statistics(fast).restored_checkpoints>0); positioned(d,whole); exr_pager_free(fast); exr_pager_free(slow); exr_layout_free(whole); exr_document_free(d);
}
static uint32_t random_value(uint32_t *state) { *state=*state*1664525u+1013904223u; return *state; }
static void generated(void) {
  uint32_t seed=180318; unsigned iteration;
  for(iteration=0;iteration<500;iteration++) {
    exr_node_input nodes[128]={{0}}; exr_attribute attrs[128][2]; char styles[128][128],texts[128][32];
    exr_chapter_input chapter={"generated","generated.unit",1,1}; exr_document_input input={"Collapsed tables",nodes,0,&chapter,1,NULL,0};
    exr_document *d=NULL; exr_layout *l=NULL; exr_layout_config cfg=config(); size_t used=3,row,columns=2+random_value(&seed)%5,i,n,expected=0,actual=0;
    const exr_box *boxes; const exr_glyph *g; const char *source;
    cfg.page.height=2048;
    nodes[0]=(exr_node_input){EXR_NODE_DOCUMENT,SIZE_MAX,NULL,NULL,NULL,0}; nodes[1]=(exr_node_input){EXR_NODE_CHAPTER,0,NULL,NULL,NULL,0};
    snprintf(styles[2],sizeof(styles[2]),"border-collapse:collapse;%s%s;direction:%s",iteration%3==0 ? "table-layout:fixed;" : "",iteration%4 ? "width:300px" : "width:auto",iteration%2 ? "rtl" : "ltr");
    attrs[2][0]=(exr_attribute){"style",styles[2]}; nodes[2]=(exr_node_input){EXR_NODE_TABLE,1,"table",NULL,attrs[2],1};
    for(row=0;row<3;row++) {
      size_t parent=used++,column=0; nodes[parent]=(exr_node_input){EXR_NODE_ROW,2,"tr",NULL,NULL,0};
      while(column<columns) {
        const char *align[]={"baseline","top","middle","bottom"},*border[]={"solid","hidden","none"};
        size_t cell=used++,text=used++,span=(row==0 && column+1<columns && random_value(&seed)%3==0) ? 2 : 1;
        unsigned letters=1+random_value(&seed)%9,k; size_t length=0;
        snprintf(styles[cell],sizeof(styles[cell]),"vertical-align:%s;font-size:%upx;height:%upx;border:%upx %s #00000080",align[random_value(&seed)%4],14+7*(random_value(&seed)%3),10+random_value(&seed)%51,random_value(&seed)%11,border[random_value(&seed)%3]);
        attrs[cell][0]=(exr_attribute){"style",styles[cell]}; attrs[cell][1]=(exr_attribute){"colspan","2"};
        nodes[cell]=(exr_node_input){EXR_NODE_CELL,parent,"td",NULL,attrs[cell],span==2 ? 2u : 1u};
        for(k=0;k<letters;k++) { texts[text][length++]='A'; if(k+1<letters && iteration%2) texts[text][length++]=' '; } texts[text][length]=0;
        nodes[text]=(exr_node_input){EXR_NODE_TEXT,cell,NULL,texts[text],NULL,0}; column+=span;
      }
    }
    input.node_count=used; OK(exr_document_create(&input,&d,&error)); OK(exr_layout_create_ex(d,font,&cfg,&l,&error));
    source=exr_document_text(d,&n); for(i=0;i<n;i++) expected+=source[i]=='A';
    g=exr_layout_glyphs(l,&n); for(i=0;i<n;i++) actual+=g[i].codepoint=='A'; CHECK(actual==expected);
    boxes=exr_layout_boxes(l,&n); for(i=0;i<n;i++) CHECK(isfinite(boxes[i].x) && isfinite(boxes[i].width) && isfinite(boxes[i].y) && isfinite(boxes[i].height) && boxes[i].x>=9.99f && boxes[i].y>=9.99f && boxes[i].width>0 && boxes[i].x+boxes[i].width<=cfg.page.width-9.99f && boxes[i].y+boxes[i].height<=cfg.page.height-9.99f);
    exr_layout_free(l); exr_document_free(d);
  }
}
static void limits(void) {
  exr_document *d=book("basic"); exr_positioned_input input={0}; exr_positioned_page page={0}; exr_layout_config cfg=config(); exr_layout *l=NULL; exr_bitmap image={0};
  exr_box b={0}; exr_paint paint={EXR_PAINT_BOX,0,0}; size_t n; exr_document_text(d,&n);
  cfg.page.width=page.width=5000; cfg.page.height=page.height=4000; page.content.end=n; page.content.box_count=1; page.paint_count=1;
  b=(exr_box){EXR_BOX_BLOCK,node(d,"table"),0,SIZE_MAX,0,n,0,0,5000,4000,0,0x00000080,0,EXR_BOX_BORDER};
  input.struct_size=sizeof(input); input.pages=&page; input.page_count=1; input.boxes=&b; input.box_count=1; input.paints=&paint; input.paint_count=1;
  OK(exr_layout_create_positioned(d,font,&input,&cfg,&l,&error));
  CHECK(exr_render_page(l,NULL,0,&image,&error)==EXR_LIMIT && !image.pixels && error.code==EXR_LIMIT); exr_layout_free(l); l=NULL;
  b.border_width=1; CHECK(exr_layout_create_positioned(d,font,&input,&cfg,&l,&error)==EXR_ARGUMENT && !l); b.border_width=0;
  b.kind=EXR_BOX_CELL; CHECK(exr_layout_create_positioned(d,font,&input,&cfg,&l,&error)==EXR_ARGUMENT && !l);
  b.kind=EXR_BOX_IMAGE; CHECK(exr_layout_create_positioned(d,font,&input,&cfg,&l,&error)==EXR_ARGUMENT && !l);
  b.kind=EXR_BOX_BLOCK; b.flags=3; CHECK(exr_layout_create_positioned(d,font,&input,&cfg,&l,&error)==EXR_ARGUMENT && !l);
  exr_document_free(d);
}
int main(int argc,char **argv) {
  char path[4096]; CHECK(argc==2); directory=argv[1]; snprintf(path,sizeof(path),"%s/fonts/primary.ttf",directory); OK(exr_font_open(path,&font,&error));
  basic(); conflicts(); alpha(); spans(); nested(); pages(); generated(); limits(); exr_font_free(font); printf("%u table border checks passed\n",checks); return 0;
}


