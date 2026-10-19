/* SPDX-License-Identifier: MIT */
/* WP5: independent border sides on blocks, separate cells and collapsed grids.
   Side order is CSS physical top, right, bottom, left. */
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
static int near(float a,float b) { return fabsf(a-b)<.05f; }

static exr_layout_config config(void) {
  exr_layout_config c=exr_layout_config_defaults();
  c.page=(exr_layout_options){420,240,10,14,1.2f,0};
  return c;
}
typedef struct {
  exr_node_input nodes[96];
  exr_attribute attrs[96][3];
  char ids[96][32], styles[96][192], texts[96][256], spans[96][8];
  size_t count;
} builder;
static size_t add(builder *b,exr_node_kind kind,size_t parent,const char *name,
                  const char *id,const char *style,const char *text) {
  size_t i=b->count++; size_t n=0;
  if(text) snprintf(b->texts[i],sizeof(b->texts[i]),"%s",text);
  b->nodes[i]=(exr_node_input){kind,parent,name,text?b->texts[i]:NULL,NULL,0};
  if(id) { snprintf(b->ids[i],sizeof(b->ids[i]),"%s",id); b->attrs[i][n++]=(exr_attribute){"id",b->ids[i]}; }
  if(style) { snprintf(b->styles[i],sizeof(b->styles[i]),"%s",style); b->attrs[i][n++]=(exr_attribute){"style",b->styles[i]}; }
  b->nodes[i].attributes=b->attrs[i]; b->nodes[i].attribute_count=n;
  return i;
}
static size_t rowspan(builder *b,exr_node_kind kind,size_t parent,const char *name,
                      const char *id,const char *style,unsigned span) {
  size_t i=add(b,kind,parent,name,id,style,NULL);
  snprintf(b->spans[i],sizeof(b->spans[i]),"%u",span);
  b->attrs[i][b->nodes[i].attribute_count++]=(exr_attribute){"rowspan",b->spans[i]};
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
static exr_layout *layout(exr_document *d,exr_layout_config *c) {
  exr_layout *l=NULL;
  OK(exr_layout_create_ex(d,font,c,&l,&error));
  return l;
}
static const exr_box *box(const exr_layout *l,size_t node_id) {
  size_t i,n; const exr_box *b=exr_layout_boxes(l,&n);
  for(i=0;i<n;i++) if(b[i].node==node_id && !(b[i].flags&EXR_BOX_BORDER)) return b+i;
  CHECK(0); return NULL;
}
static size_t border_boxes(const exr_layout *l,size_t node_id) {
  size_t i,n,count=0; const exr_box *b=exr_layout_boxes(l,&n);
  for(i=0;i<n;i++) if((b[i].flags&EXR_BOX_BORDER) && b[i].node==node_id) count++;
  return count;
}
static uint32_t pixel(const exr_bitmap *b,float x,float y) {
  const unsigned char *p; CHECK(x>=0 && y>=0 && x<b->width && y<b->height);
  p=b->pixels+(size_t)y*b->stride+(size_t)x*4;
  return ((uint32_t)p[0]<<24)|((uint32_t)p[1]<<16)|((uint32_t)p[2]<<8)|p[3];
}
static unsigned column_run(const exr_bitmap *b,float x,float y0,float y1,uint32_t color) {
  unsigned count=0; float y;
  for(y=y0;y<y1;y+=1) if(pixel(b,x,y)==color) count++;
  return count;
}
/* The positioned layout must rebuild every independent side from its boxes. */
static void positioned(const exr_document *doc,const exr_layout *l) {
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

static void four_sides(void) {
  builder b={0}; exr_layout_config c=config(); exr_document *d; exr_layout *l; exr_bitmap image={0};
  size_t a,bb;
  add(&b,EXR_NODE_DOCUMENT,SIZE_MAX,NULL,NULL,NULL,NULL);
  add(&b,EXR_NODE_CHAPTER,0,NULL,NULL,NULL,NULL);
  a=add(&b,EXR_NODE_PARAGRAPH,1,"div","a","width:120px;border-top:2px solid red;border-right:4px solid blue;"
        "border-bottom:6px solid green;border-left:8px solid black",NULL);
  bb=add(&b,EXR_NODE_PARAGRAPH,a,"div","b","height:10px;background-color:#ffffff",NULL);
  add(&b,EXR_NODE_TEXT,a,NULL,NULL,NULL,"AAAA");
  d=open(&b); l=layout(d,&c);
  {
    const exr_box *ab=box(l,a),*bob=box(l,bb);
    CHECK(ab && bob);
    CHECK(ab->border_width==0);            /* independent sides leave the compact field empty */
    CHECK(border_boxes(l,a)==4);
    CHECK(near(bob->x,ab->x+8) && near(bob->y,ab->y+2));
    OK(exr_render_page_color(l,NULL,0,&image,&error));
    CHECK(pixel(&image,ab->x+30,ab->y+.5f)==0xff0000ff);
    CHECK(pixel(&image,ab->x+ab->width-1,ab->y+ab->height/2)==0x0000ffff);
    CHECK(pixel(&image,ab->x+30,ab->y+ab->height-1)==0x008000ff);
    CHECK(pixel(&image,ab->x+.5f,ab->y+ab->height/2)==0x000000ff);
  }
  exr_bitmap_free(&image);
  positioned(d,l);
  exr_layout_free(l); exr_document_free(d);
}

static void shorthand(void) {
  builder b={0}; exr_layout_config c=config(); exr_document *d; exr_layout *l; exr_bitmap image={0};
  size_t a;
  add(&b,EXR_NODE_DOCUMENT,SIZE_MAX,NULL,NULL,NULL,NULL);
  add(&b,EXR_NODE_CHAPTER,0,NULL,NULL,NULL,NULL);
  a=add(&b,EXR_NODE_PARAGRAPH,1,"div","a",
        "background-color:#ffffff;border:2px solid red;border-top-color:blue;border-left:4px dashed green",NULL);
  add(&b,EXR_NODE_TEXT,a,NULL,NULL,NULL,"AAAA");
  d=open(&b); l=layout(d,&c);
  {
    const exr_box *ab=box(l,a); unsigned run;
    CHECK(ab);
    OK(exr_render_page_color(l,NULL,0,&image,&error));
    CHECK(pixel(&image,ab->x+10,ab->y+.5f)==0x0000ffff);
    CHECK(pixel(&image,ab->x+ab->width-1,ab->y+3)==0xff0000ff);
    CHECK(pixel(&image,ab->x+10,ab->y+ab->height-1)==0xff0000ff);
    run=column_run(&image,ab->x+1,ab->y+2,ab->y+ab->height-2,0x008000ff);
    CHECK(run>0 && run<(unsigned)(ab->height-4));
  }
  exr_bitmap_free(&image);
  exr_layout_free(l); exr_document_free(d);
}

static void width_expansion(void) {
  builder b={0}; exr_layout_config c=config(); exr_document *d; exr_layout *l; exr_bitmap image={0};
  size_t a;
  add(&b,EXR_NODE_DOCUMENT,SIZE_MAX,NULL,NULL,NULL,NULL);
  add(&b,EXR_NODE_CHAPTER,0,NULL,NULL,NULL,NULL);
  a=add(&b,EXR_NODE_PARAGRAPH,1,"div","a",
        "background-color:#ffffff;border-style:solid;border-width:1px 2px 3px 4px;border-color:red green blue black",NULL);
  add(&b,EXR_NODE_TEXT,a,NULL,NULL,NULL,"AAAA");
  d=open(&b); l=layout(d,&c);
  {
    const exr_box *ab=box(l,a);
    CHECK(ab && ab->border_width==0);
    OK(exr_render_page_color(l,NULL,0,&image,&error));
    CHECK(pixel(&image,ab->x+20,ab->y+.5f)==0xff0000ff);               /* top 1px red */
    CHECK(pixel(&image,ab->x+20,ab->y+1.5f)!=0xff0000ff);
    CHECK(pixel(&image,ab->x+ab->width-1,ab->y+ab->height/2)==0x008000ff); /* right 2px green */
    CHECK(pixel(&image,ab->x+20,ab->y+ab->height-1)==0x0000ffff);      /* bottom 3px blue */
    CHECK(pixel(&image,ab->x+2,ab->y+ab->height/2)==0x000000ff);       /* left 4px black */
    CHECK(pixel(&image,ab->x+3.5f,ab->y+ab->height/2)==0x000000ff);
  }
  exr_bitmap_free(&image);
  exr_layout_free(l); exr_document_free(d);
}

static void separate_cells(void) {
  builder b={0}; exr_layout_config c=config(); exr_document *d; exr_layout *l; exr_bitmap image={0};
  size_t t,r,a,bb;
  add(&b,EXR_NODE_DOCUMENT,SIZE_MAX,NULL,NULL,NULL,NULL);
  add(&b,EXR_NODE_CHAPTER,0,NULL,NULL,NULL,NULL);
  t=add(&b,EXR_NODE_TABLE,1,"table",NULL,"border-collapse:separate;border-spacing:0",NULL);
  r=add(&b,EXR_NODE_ROW,t,"tr",NULL,NULL,NULL);
  a=add(&b,EXR_NODE_CELL,r,"td","a","border-top:3px solid red;border-right:5px solid green;border-bottom:1px solid blue;"
        "border-left:2px solid black;background-color:#ffffff",NULL);
  add(&b,EXR_NODE_TEXT,a,NULL,NULL,NULL,"A");
  bb=add(&b,EXR_NODE_CELL,r,"td","b","border-top:1px solid blue;border-right:2px solid black;border-bottom:3px solid red;"
        "border-left:5px solid green;background-color:#ffffff",NULL);
  add(&b,EXR_NODE_TEXT,bb,NULL,NULL,NULL,"B");
  d=open(&b); l=layout(d,&c);
  {
    const exr_box *ab=box(l,a),*bob=box(l,bb);
    CHECK(ab && bob);
    CHECK(ab->border_width==0 && bob->border_width==0);
    CHECK(border_boxes(l,a)==4 && border_boxes(l,bb)==4);
    OK(exr_render_page_color(l,NULL,0,&image,&error));
    CHECK(pixel(&image,ab->x+10,ab->y+.5f)==0xff0000ff);
    CHECK(pixel(&image,ab->x+ab->width-1,ab->y+10)==0x008000ff);
    CHECK(pixel(&image,ab->x+ab->width/2,ab->y+ab->height-1)==0x0000ffff);
    CHECK(pixel(&image,ab->x+.5f,ab->y+10)==0x000000ff);
    CHECK(pixel(&image,bob->x+10,bob->y+.5f)==0x0000ffff);
    CHECK(pixel(&image,bob->x+bob->width-1,bob->y+10)==0x000000ff);
  }
  exr_bitmap_free(&image);
  exr_layout_free(l); exr_document_free(d);
}

static void collapsed_sides(void) {
  builder b={0}; exr_layout_config c=config(); exr_document *d; exr_layout *l; exr_bitmap image={0};
  size_t t,r,a,bb;
  add(&b,EXR_NODE_DOCUMENT,SIZE_MAX,NULL,NULL,NULL,NULL);
  add(&b,EXR_NODE_CHAPTER,0,NULL,NULL,NULL,NULL);
  t=add(&b,EXR_NODE_TABLE,1,"table",NULL,"border-collapse:collapse",NULL);
  r=add(&b,EXR_NODE_ROW,t,"tr",NULL,NULL,NULL);
  a=add(&b,EXR_NODE_CELL,r,"td","a","border-right:6px solid red;border-bottom:2px solid blue;background-color:#ffffff",NULL);
  add(&b,EXR_NODE_TEXT,a,NULL,NULL,NULL,"A");
  bb=add(&b,EXR_NODE_CELL,r,"td","b","border-left:2px solid blue;border-bottom:6px solid green;background-color:#ffffff",NULL);
  add(&b,EXR_NODE_TEXT,bb,NULL,NULL,NULL,"B");
  d=open(&b); l=layout(d,&c);
  {
    const exr_box *ab=box(l,a),*bob=box(l,bb);
    CHECK(ab && bob);
    OK(exr_render_page_color(l,NULL,0,&image,&error));
    /* The 6px red right side wins the 2px blue left side on the shared grid line. */
    CHECK(pixel(&image,bob->x-1,bob->y+8)==0xff0000ff);
    CHECK(pixel(&image,bob->x-2,bob->y+8)==0xff0000ff);
    CHECK(pixel(&image,bob->x-4,bob->y+8)!=0xff0000ff);
    /* The bottom conflict keeps the wider green line. */
    CHECK(pixel(&image,bob->x+8,ab->y+ab->height-1)==0x008000ff);
  }
  exr_bitmap_free(&image);
  exr_layout_free(l); exr_document_free(d);
}

static void vertical(const char *mode,int rl) {
  builder b={0}; exr_layout_config c=config(); exr_document *d; exr_layout *l; exr_bitmap image={0};
  size_t body,a;
  add(&b,EXR_NODE_DOCUMENT,SIZE_MAX,NULL,NULL,NULL,NULL);
  add(&b,EXR_NODE_CHAPTER,0,NULL,NULL,NULL,NULL);
  body=add(&b,EXR_NODE_PARAGRAPH,1,"div","body",mode,NULL);
  a=add(&b,EXR_NODE_PARAGRAPH,body,"div","a","width:100px;border-top:2px solid red;border-right:4px solid blue;"
        "border-bottom:6px solid green;border-left:8px solid black;background-color:#ffffff",NULL);
  add(&b,EXR_NODE_TEXT,a,NULL,NULL,NULL,"AAA");
  d=open(&b); l=layout(d,&c);
  {
    const exr_box *ab=box(l,a);
    CHECK(ab);
    OK(exr_render_page_color(l,NULL,0,&image,&error));
    /* CSS border sides stay physical in vertical writing: the logical-side map
       and the block rotation cancel, so neither mode may swap them. */
    CHECK(pixel(&image,ab->x+10,ab->y+.5f)==0xff0000ff);
    CHECK(pixel(&image,ab->x+ab->width-1,ab->y+10)==0x0000ffff);
    CHECK(pixel(&image,ab->x+10,ab->y+ab->height-1)==0x008000ff);
    CHECK(pixel(&image,ab->x+.5f,ab->y+10)==0x000000ff);
    (void)rl;
  }
  exr_bitmap_free(&image);
  exr_layout_free(l); exr_document_free(d);
}

static void split_pages(void) {
  builder b={0}; exr_layout_config c=config(); exr_document *d; exr_layout *l;
  size_t np,i,a;
  const exr_page *pages;
  add(&b,EXR_NODE_DOCUMENT,SIZE_MAX,NULL,NULL,NULL,NULL);
  add(&b,EXR_NODE_CHAPTER,0,NULL,NULL,NULL,NULL);
  a=add(&b,EXR_NODE_PARAGRAPH,1,"div","a","border-top:4px solid red;border-right:2px solid blue;"
        "border-bottom:4px solid green;border-left:2px solid black;background-color:#ffffff",NULL);
  add(&b,EXR_NODE_TEXT,a,NULL,NULL,NULL,
      "one two three four five six seven eight nine ten eleven twelve thirteen fourteen "
      "fifteen sixteen seventeen eighteen nineteen twenty twenty-one twenty-two");
  c.page.height=70;
  d=open(&b); l=layout(d,&c);
  pages=exr_layout_pages(l,&np); CHECK(np>=2);
  for(i=0;i<np;i++) {
    exr_bitmap image={0}; const exr_box *found=NULL; size_t j,n,count=0; const exr_box *boxes=exr_layout_boxes(l,&n);
    for(j=pages[i].box_start;j<pages[i].box_start+pages[i].box_count;j++)
      if(boxes[j].node==a && !(boxes[j].flags&EXR_BOX_BORDER)) { found=boxes+j; count++; }
    CHECK(found && count==1);
    OK(exr_render_page_color(l,NULL,i,&image,&error));
    CHECK(pixel(&image,found->x+.5f,found->y+8)==0x000000ff);
    CHECK(pixel(&image,found->x+found->width-1,found->y+8)==0x0000ffff);
    if(i==0) CHECK(pixel(&image,found->x+20,found->y+.5f)==0xff0000ff);
    if(i==np-1) CHECK(pixel(&image,found->x+20,found->y+found->height-1)==0x008000ff);
    exr_bitmap_free(&image);
  }
  { /* Paged output, including checkpoint restores, matches the whole layout. */
    exr_pager *pager=NULL; size_t page;
    OK(exr_pager_create(d,font,&c,&pager,&error));
    OK(exr_pager_set_checkpoints(pager,8,1024*1024,1,&error));
    for(page=0;page<np;page++) {
      const exr_layout *pg=NULL; exr_bitmap x={0},y={0};
      OK(exr_pager_get(pager,page,&pg,&error));
      OK(exr_render_page_color(pg,NULL,0,&x,&error));
      OK(exr_render_page_color(l,NULL,page,&y,&error));
      CHECK(x.stride==y.stride && x.height==y.height && !memcmp(x.pixels,y.pixels,(size_t)x.stride*x.height));
      exr_bitmap_free(&x); exr_bitmap_free(&y);
    }
    exr_pager_free(pager);
  }
  exr_layout_free(l); exr_document_free(d);
}

static void nested_cell(void) {
  builder b={0}; exr_layout_config c=config(); exr_document *d; exr_layout *l; exr_bitmap image={0};
  size_t t,r,cell,a;
  add(&b,EXR_NODE_DOCUMENT,SIZE_MAX,NULL,NULL,NULL,NULL);
  add(&b,EXR_NODE_CHAPTER,0,NULL,NULL,NULL,NULL);
  t=add(&b,EXR_NODE_TABLE,1,"table",NULL,NULL,NULL);
  r=add(&b,EXR_NODE_ROW,t,"tr",NULL,NULL,NULL);
  cell=add(&b,EXR_NODE_CELL,r,"td",NULL,"padding:4px",NULL);
  a=add(&b,EXR_NODE_PARAGRAPH,cell,"div","a","background-color:#ffffff;border-top:2px solid red;"
        "border-right:6px solid green;border-bottom:2px solid red;border-left:6px solid green",NULL);
  add(&b,EXR_NODE_TEXT,a,NULL,NULL,NULL,"AAAA");
  d=open(&b); l=layout(d,&c);
  {
    const exr_box *ab=box(l,a);
    CHECK(ab && ab->border_width==0);
    OK(exr_render_page_color(l,NULL,0,&image,&error));
    CHECK(pixel(&image,ab->x+.5f,ab->y+8)==0x008000ff);
    CHECK(pixel(&image,ab->x+ab->width-1,ab->y+8)==0x008000ff);
    CHECK(pixel(&image,ab->x+10,ab->y+.5f)==0xff0000ff);
    CHECK(pixel(&image,ab->x+10,ab->y+ab->height-1)==0xff0000ff);
  }
  exr_bitmap_free(&image);
  exr_layout_free(l); exr_document_free(d);
}

static void merged_cell(void) {
  builder b={0}; exr_layout_config c=config(); exr_document *d; exr_layout *l; exr_bitmap image={0};
  size_t t,r0,r1,a,bb,cc;
  add(&b,EXR_NODE_DOCUMENT,SIZE_MAX,NULL,NULL,NULL,NULL);
  add(&b,EXR_NODE_CHAPTER,0,NULL,NULL,NULL,NULL);
  t=add(&b,EXR_NODE_TABLE,1,"table",NULL,"border-collapse:collapse",NULL);
  r0=add(&b,EXR_NODE_ROW,t,"tr",NULL,NULL,NULL);
  a=rowspan(&b,EXR_NODE_CELL,r0,"td","a","border-top:4px solid red;border-right:4px solid green;"
        "border-bottom:4px solid blue;border-left:4px solid black;background-color:#ffffff",2);
  add(&b,EXR_NODE_TEXT,a,NULL,NULL,NULL,"M");
  bb=add(&b,EXR_NODE_CELL,r0,"td",NULL,"background-color:#ffffff",NULL);
  add(&b,EXR_NODE_TEXT,bb,NULL,NULL,NULL,"B");
  r1=add(&b,EXR_NODE_ROW,t,"tr",NULL,NULL,NULL);
  cc=add(&b,EXR_NODE_CELL,r1,"td",NULL,"border-bottom:6px solid green;background-color:#ffffff",NULL);
  add(&b,EXR_NODE_TEXT,cc,NULL,NULL,NULL,"C");
  d=open(&b); l=layout(d,&c);
  {
    const exr_box *ab=box(l,a),*bob=box(l,bb),*cob=box(l,cc);
    CHECK(ab && bob && cob);
    CHECK(near(ab->height,bob->height+cob->height));   /* rowspan reaches both rows */
    OK(exr_render_page_color(l,NULL,0,&image,&error));
    CHECK(pixel(&image,ab->x+5,ab->y+.5f)==0xff0000ff);
    CHECK(pixel(&image,ab->x+.5f,ab->y+ab->height/2)==0x000000ff);
    CHECK(pixel(&image,ab->x+ab->width-1,ab->y+ab->height/2)==0x008000ff);
    /* The spanning bottom line is blue under this column; the neighbour's
       wider green line stays in its own column. */
    CHECK(pixel(&image,ab->x+ab->width/2,ab->y+ab->height-1)==0x0000ffff);
    CHECK(pixel(&image,cob->x+cob->width/2,cob->y+cob->height-1)==0x008000ff);
  }
  exr_bitmap_free(&image);
  exr_layout_free(l); exr_document_free(d);
}

static void translucent(void) {
  builder b={0}; exr_layout_config c=config(); exr_document *d; exr_layout *l; exr_bitmap image={0};
  size_t a;
  add(&b,EXR_NODE_DOCUMENT,SIZE_MAX,NULL,NULL,NULL,NULL);
  add(&b,EXR_NODE_CHAPTER,0,NULL,NULL,NULL,NULL);
  a=add(&b,EXR_NODE_PARAGRAPH,1,"div","a","background-color:#ffffff;border-top:3px solid #ff000080;"
        "border-left:3px solid #0000ff80",NULL);
  add(&b,EXR_NODE_TEXT,a,NULL,NULL,NULL,"AAAA");
  d=open(&b); l=layout(d,&c);
  {
    const exr_box *ab=box(l,a); uint32_t corner;
    CHECK(ab);
    OK(exr_render_page_color(l,NULL,0,&image,&error));
    corner=pixel(&image,ab->x+.5f,ab->y+.5f);
    /* A 50% border paints once over the white page: double painting at the
       corner would leave a visibly darker result (~0x40 green). */
    CHECK((corner>>24)==0xff);
    CHECK(((corner>>16)&255)>=0x60 && ((corner>>16)&255)<=0xa0);
  }
  exr_bitmap_free(&image);
  exr_layout_free(l); exr_document_free(d);
}

static void double_growth(void) {
  builder b={0};exr_layout_config c=config();exr_document *d;exr_layout *l;size_t i,n;const exr_box *boxes;
  add(&b,EXR_NODE_DOCUMENT,SIZE_MAX,NULL,NULL,NULL,NULL);add(&b,EXR_NODE_CHAPTER,0,NULL,NULL,NULL,NULL);
  for(i=0;i<80;i++) add(&b,EXR_NODE_PARAGRAPH,1,"div",NULL,"height:1px;width:80px;border-top:3px double red",NULL);
  d=open(&b);l=layout(d,&c);boxes=exr_layout_boxes(l,&n);
  for(i=0;i<n;i++) if(boxes[i].flags&EXR_BOX_BORDER) CHECK(boxes[i].background==0xff0000ff);
  CHECK(n>=160);positioned(d,l);exr_layout_free(l);exr_document_free(d);
}

int main(int argc,char **argv) {
  char path[4096];
  CHECK(argc==2);
  snprintf(path,sizeof(path),"%s/fonts/primary.ttf",argv[1]);
  OK(exr_font_open(path,&font,&error));
  double_growth();four_sides(); shorthand(); width_expansion(); separate_cells(); collapsed_sides();
  vertical("writing-mode:vertical-rl",1);
  vertical("writing-mode:vertical-lr",0);
  split_pages(); nested_cell(); merged_cell(); translucent();
  exr_font_free(font);
  printf("%u independent border checks passed\n",checks);
  return 0;
}
