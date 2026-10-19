/* SPDX-License-Identifier: MIT */
/* WP5: <thead> rows repeat at the top of every table continuation page. */
#include "exreader.h"
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static exr_error error;
static unsigned checks;
static exr_font *font;

#define CHECK(x) do { checks++; if(!(x)) { fprintf(stderr,"line %d: %s (%d: %s)\n",__LINE__,#x,error.code,error.message); exit(1); } } while(0)
#define OK(x) CHECK((x)==EXR_OK)

static exr_layout_config config(float height) {
  exr_layout_config c=exr_layout_config_defaults();
  c.page=(exr_layout_options){200,height,5,14,1.2f,0};
  return c;
}
typedef struct {
  exr_node_input nodes[128];
  exr_attribute attrs[128][3];
  char styles[128][192], texts[128][128], spans[128][8];
  size_t count;
} builder;
static size_t add(builder *b,exr_node_kind kind,size_t parent,const char *name,
                  const char *style,const char *text) {
  size_t i=b->count++; size_t n=0;
  if(text) snprintf(b->texts[i],sizeof(b->texts[i]),"%s",text);
  b->nodes[i]=(exr_node_input){kind,parent,name,text?b->texts[i]:NULL,NULL,0};
  if(style) { snprintf(b->styles[i],sizeof(b->styles[i]),"%s",style); b->attrs[i][n++]=(exr_attribute){"style",b->styles[i]}; }
  b->nodes[i].attributes=b->attrs[i]; b->nodes[i].attribute_count=n;
  return i;
}
static size_t spanning(builder *b,exr_node_kind kind,size_t parent,const char *name,
                       const char *style,const char *text,unsigned colspan) {
  size_t i=add(b,kind,parent,name,style,text);
  snprintf(b->spans[i],sizeof(b->spans[i]),"%u",colspan);
  b->attrs[i][b->nodes[i].attribute_count++]=(exr_attribute){"colspan",b->spans[i]};
  b->nodes[i].attributes=b->attrs[i];
  return i;
}
static exr_document *open(builder *b) {
  exr_chapter_input chapter={"t","t.xhtml",1,1};
  exr_document_input input={"t",b->nodes,b->count,&chapter,1,NULL,0};
  exr_document *d=NULL;
  OK(exr_document_create(&input,&d,&error));
  return d;
}
static size_t text_range(const exr_document *d,const char *needle,size_t *start,size_t *end) {
  size_t i,n; const exr_node *nodes=exr_document_nodes(d,&n);
  for(i=0;i<n;i++) if(nodes[i].text && !strcmp(nodes[i].text,needle)) { *start=nodes[i].start; *end=nodes[i].end; return i; }
  CHECK(0); return SIZE_MAX;
}
static size_t page_glyphs(const exr_layout *l,size_t page,size_t start,size_t end) {
  size_t i,n,count=0; const exr_glyph *g=exr_layout_glyphs(l,&n);
  for(i=0;i<n;i++) if(g[i].page==page && g[i].start>=start && g[i].start<end) count++;
  return count;
}
static uint32_t pixel(const exr_bitmap *b,float x,float y) {
  const unsigned char *p; CHECK(x>=0 && y>=0 && x<b->width && y<b->height);
  p=b->pixels+(size_t)y*b->stride+(size_t)x*4;
  return ((uint32_t)p[0]<<24)|((uint32_t)p[1]<<16)|((uint32_t)p[2]<<8)|p[3];
}
static int has_color(const exr_bitmap *b,uint32_t color,float x0,float y0,float x1,float y1) {
  float x,y;
  for(y=y0;y<y1;y+=1) for(x=x0;x<x1;x+=1) {
    const unsigned char *p=b->pixels+(size_t)y*b->stride+(size_t)x*4;
    uint32_t v=((uint32_t)p[0]<<24)|((uint32_t)p[1]<<16)|((uint32_t)p[2]<<8)|p[3];
    if(v==color) return 1;
  }
  return 0;
}
/* A table with a one-row thead containing `header`, then `rows` body rows. */
static size_t table(builder *b,unsigned rows,const char *table_style,const char *th_style,
                    const char *header,int thead) {
  size_t t=add(b,EXR_NODE_TABLE,1,"table",table_style,NULL),parent=t,tr,cell;
  if(thead) parent=add(b,EXR_NODE_SECTION,t,"http://www.w3.org/1999/xhtml|thead",NULL,NULL);
  tr=add(b,EXR_NODE_ROW,parent,"tr",NULL,NULL);
  cell=add(b,EXR_NODE_CELL,tr,"th",th_style,NULL);
  add(b,EXR_NODE_TEXT,cell,NULL,NULL,header);
  { unsigned row; for(row=0;row<rows;row++) {
      char text[16]; size_t body=add(b,EXR_NODE_ROW,t,"tr",NULL,NULL);
      snprintf(text,sizeof(text),"b%u",row);
      cell=add(b,EXR_NODE_CELL,body,"td",NULL,NULL);
      add(b,EXR_NODE_TEXT,cell,NULL,NULL,text);
  } }
  return t;
}
static void begin(builder *b) {
  add(b,EXR_NODE_DOCUMENT,SIZE_MAX,NULL,NULL,NULL);
  add(b,EXR_NODE_CHAPTER,0,NULL,NULL,NULL);
}

/* 1. A paginated table repeats the single header row on every page. */
static void repeats(void) {
  builder b={0}; exr_layout_config c=config(64); exr_document *d; exr_layout *l;
  size_t np,i,hs,he,header_count; const exr_page *pages;
  begin(&b); table(&b,6,NULL,NULL,"HEAD",1);
  d=open(&b); text_range(d,"HEAD",&hs,&he);
  OK(exr_layout_create_ex(d,font,&c,&l,&error));
  pages=exr_layout_pages(l,&np); CHECK(np>=3);
  header_count=page_glyphs(l,0,hs,he); CHECK(header_count==4);
  for(i=0;i<np;i++) CHECK(page_glyphs(l,i,hs,he)==header_count);
  (void)pages;
  exr_layout_free(l); exr_document_free(d);
}

/* 2. Without thead nothing repeats. */
static void no_thead(void) {
  builder b={0}; exr_layout_config c=config(64); exr_document *d; exr_layout *l;
  size_t np,i,hs,he;
  begin(&b); table(&b,6,NULL,NULL,"HEAD",0);
  d=open(&b); text_range(d,"HEAD",&hs,&he);
  OK(exr_layout_create_ex(d,font,&c,&l,&error));
  exr_layout_pages(l,&np); CHECK(np>=3);
  CHECK(page_glyphs(l,0,hs,he)==4);
  for(i=1;i<np;i++) CHECK(page_glyphs(l,i,hs,he)==0);
  exr_layout_free(l); exr_document_free(d);
}

/* 3. The repeated header consumes page height, so the table needs more pages
      than the same rows without a repeating header. */
static void budget(void) {
  builder with={0},without={0}; exr_layout_config c=config(60); exr_document *d;
  exr_layout *a=NULL,*b=NULL; size_t na,nb;
  begin(&with); table(&with,6,NULL,NULL,"HEAD",1);
  begin(&without); table(&without,6,NULL,NULL,"HEAD",0);
  d=open(&with); OK(exr_layout_create_ex(d,font,&c,&a,&error)); exr_document_free(d);
  d=open(&without); OK(exr_layout_create_ex(d,font,&c,&b,&error)); exr_document_free(d);
  exr_layout_pages(a,&na); exr_layout_pages(b,&nb);
  CHECK(na>nb);
  exr_layout_free(a); exr_layout_free(b);
}

/* 4. Two header rows and a spanning header cell repeat together. */
static void two_rows(void) {
  builder b={0}; exr_layout_config c=config(64); exr_document *d; exr_layout *l;
  size_t np,i,hs,he,ls,le,t;
  begin(&b);
  t=add(&b,EXR_NODE_TABLE,1,"table",NULL,NULL);
  { size_t th=add(&b,EXR_NODE_SECTION,t,"http://www.w3.org/1999/xhtml|thead",NULL,NULL);
    size_t r1=add(&b,EXR_NODE_ROW,th,"tr",NULL,NULL),r2;
    size_t wide=spanning(&b,EXR_NODE_CELL,r1,"th",NULL,NULL,2);
    add(&b,EXR_NODE_TEXT,wide,NULL,NULL,"TOP");
    r2=add(&b,EXR_NODE_ROW,th,"tr",NULL,NULL);
    add(&b,EXR_NODE_TEXT,add(&b,EXR_NODE_CELL,r2,"th",NULL,NULL),NULL,NULL,"L");
    add(&b,EXR_NODE_TEXT,add(&b,EXR_NODE_CELL,r2,"th",NULL,NULL),NULL,NULL,"R");
  }
  { unsigned row; for(row=0;row<6;row++) {
      char text[16]; size_t tr=add(&b,EXR_NODE_ROW,t,"tr",NULL,NULL);
      snprintf(text,sizeof(text),"b%u",row);
      add(&b,EXR_NODE_TEXT,add(&b,EXR_NODE_CELL,tr,"td",NULL,NULL),NULL,NULL,text);
  } }
  d=open(&b); text_range(d,"TOP",&hs,&he); text_range(d,"L",&ls,&le);
  OK(exr_layout_create_ex(d,font,&c,&l,&error));
  exr_layout_pages(l,&np); CHECK(np>=3);
  for(i=0;i<np;i++) {
    CHECK(page_glyphs(l,i,hs,he)==3);
    CHECK(page_glyphs(l,i,ls,le)>=1);
  }
  exr_layout_free(l); exr_document_free(d);
}

/* 5. Collapsed grid lines surround the repeated header. */
static void collapsed_header(void) {
  builder b={0}; exr_layout_config c=config(64); exr_document *d; exr_layout *l;
  size_t np,page;
  begin(&b);
  table(&b,6,"border-collapse:collapse",
        "border-top:4px solid red;border-bottom:2px solid blue;background-color:#ffffff","HEAD",1);
  d=open(&b); OK(exr_layout_create_ex(d,font,&c,&l,&error));
  exr_layout_pages(l,&np); CHECK(np>=3);
  for(page=1;page<np;page++) {
    exr_bitmap image={0};
    OK(exr_render_page_color(l,NULL,page,&image,&error));
    /* The table top line and the header's own bottom line repeat. */
    CHECK(pixel(&image,20,5.5f)==0xff0000ff);
    CHECK(has_color(&image,0x0000ffff,0,10,200,30));
    exr_bitmap_free(&image);
  }
  exr_layout_free(l); exr_document_free(d);
}

/* 6. Separate-cell borders on the header repeat as well. */
static void separate_header(void) {
  builder b={0}; exr_layout_config c=config(64); exr_document *d; exr_layout *l;
  size_t np,page;
  begin(&b);
  table(&b,6,"border-collapse:separate;border-spacing:0",
        "border-top:4px solid red;border-left:6px solid green;background-color:#ffffff","HEAD",1);
  d=open(&b); OK(exr_layout_create_ex(d,font,&c,&l,&error));
  exr_layout_pages(l,&np); CHECK(np>=3);
  for(page=1;page<np;page++) {
    exr_bitmap image={0};
    OK(exr_render_page_color(l,NULL,page,&image,&error));
    CHECK(pixel(&image,20,5.5f)==0xff0000ff);
    CHECK(pixel(&image,5.5f,10)==0x008000ff);
    exr_bitmap_free(&image);
  }
  exr_layout_free(l); exr_document_free(d);
}

/* 7. Paged and whole layouts agree, including the repeated header boxes. */
static void pager_equals_whole(void) {
  builder b={0}; exr_layout_config c=config(64); exr_document *d; exr_layout *whole; exr_pager *pager=NULL;
  size_t np,i;
  begin(&b);
  table(&b,6,"border-collapse:collapse","border-bottom:2px solid blue;background-color:#ffffff","HEAD",1);
  d=open(&b); OK(exr_layout_create_ex(d,font,&c,&whole,&error));
  exr_layout_pages(whole,&np); CHECK(np>=3);
  OK(exr_pager_create(d,font,&c,&pager,&error));
  OK(exr_pager_set_checkpoints(pager,8,1024*1024,1,&error));
  for(i=0;i<np;i++) {
    const exr_layout *page=NULL; exr_bitmap a={0},bb={0};
    OK(exr_pager_get(pager,i,&page,&error));
    OK(exr_render_page_color(page,NULL,0,&a,&error));
    OK(exr_render_page_color(whole,NULL,i,&bb,&error));
    CHECK(a.stride==bb.stride && a.height==bb.height && !memcmp(a.pixels,bb.pixels,(size_t)a.stride*bb.height));
    exr_bitmap_free(&a); exr_bitmap_free(&bb);
  }
  exr_pager_free(pager); exr_layout_free(whole); exr_document_free(d);
}

/* 8. A tall header cell still repeats on every continuation page. */
static void tall_header(void) {
  builder b={0}; exr_layout_config c=config(110); exr_document *d; exr_layout *l;
  size_t np,i,hs,he;
  begin(&b);
  table(&b,6,NULL,"font-size:20px;line-height:1.4","TALL",1);
  d=open(&b); text_range(d,"TALL",&hs,&he);
  OK(exr_layout_create_ex(d,font,&c,&l,&error));
  exr_layout_pages(l,&np); CHECK(np>=3);
  for(i=0;i<np;i++) CHECK(page_glyphs(l,i,hs,he)==4);
  exr_layout_free(l); exr_document_free(d);
}

int main(int argc,char **argv) {
  char path[4096];
  CHECK(argc==2);
  snprintf(path,sizeof(path),"%s/fonts/primary.ttf",argv[1]);
  OK(exr_font_open(path,&font,&error));
  repeats(); no_thead(); budget(); two_rows(); collapsed_header(); separate_header();
  pager_equals_whole(); tall_header();
  exr_font_free(font);
  printf("%u repeated header checks passed\n",checks);
  return 0;
}
