/* SPDX-License-Identifier: MIT */
/* EPUB 3 Fixed Layout: rendition metadata, spreads, native viewport mapping,
   CSS absolute positioning on fixed pages, and mixed fixed/reflowable parts. */
#include "exreader.h"
#include <math.h>
#include <miniz.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static exr_error error; static unsigned checks; static exr_font *font;
#define CHECK(x) do { checks++; if(!(x)) { fprintf(stderr,"line %d: %s (%d: %s)\n",__LINE__,#x,error.code,error.message); exit(1); } } while(0)
#define OK(x) CHECK((x)==EXR_OK)
static int near(float a,float b) { return fabsf(a-b)<.05f; }
typedef struct { const char *name; const void *data; size_t size; } member;

static unsigned char *png(int w,int h,unsigned char r,unsigned char g,unsigned char b,size_t *size) {
  unsigned char *rgb=malloc((size_t)w*h*3),*out; int i; CHECK(rgb);
  for(i=0;i<w*h;i++) { rgb[i*3]=r; rgb[i*3+1]=g; rgb[i*3+2]=b; }
  out=tdefl_write_image_to_png_file_in_memory(rgb,w,h,3,size); free(rgb); CHECK(out); return out;
}
/* One EPUB in memory: mimetype, container, OEBPS/package.opf, then members. */
static exr_publication *book(const char *opf,const member *m,size_t count) {
  static const char container[]="<?xml version=\"1.0\"?><container version=\"1.0\" xmlns=\"urn:oasis:names:tc:opendocument:xmlns:container\">"
    "<rootfiles><rootfile full-path=\"OEBPS/package.opf\" media-type=\"application/oebps-package+xml\"/></rootfiles></container>";
  mz_zip_archive zip; void *bytes=NULL; size_t n=0,i; exr_publication *p=NULL;
  memset(&zip,0,sizeof(zip)); CHECK(mz_zip_writer_init_heap(&zip,0,0));
  CHECK(mz_zip_writer_add_mem(&zip,"mimetype","application/epub+zip",20,0));
  CHECK(mz_zip_writer_add_mem(&zip,"META-INF/container.xml",container,strlen(container),MZ_BEST_SPEED));
  CHECK(mz_zip_writer_add_mem(&zip,"OEBPS/package.opf",opf,strlen(opf),MZ_BEST_SPEED));
  for(i=0;i<count;i++) { char name[256]; snprintf(name,sizeof(name),"OEBPS/%s",m[i].name);
    CHECK(mz_zip_writer_add_mem(&zip,name,m[i].data,m[i].size ? m[i].size : strlen(m[i].data),MZ_BEST_SPEED)); }
  CHECK(mz_zip_writer_finalize_heap_archive(&zip,&bytes,&n)); CHECK(mz_zip_writer_end(&zip));
  OK(exr_publication_open_memory(EXR_EPUB,bytes,n,&p,&error)); mz_free(bytes); return p;
}
static char *page(const char *viewport,const char *css,const char *body) {
  size_t n=strlen(body)+strlen(css)+1024; char *s=malloc(n); CHECK(s);
  snprintf(s,n,"<?xml version=\"1.0\" encoding=\"UTF-8\"?><html xmlns=\"http://www.w3.org/1999/xhtml\"><head><title>t</title>"
    "%s%s%s<style>body{margin:0}%s</style></head><body>%s</body></html>",
    viewport ? "<meta name=\"viewport\" content=\"" : "",viewport ? viewport : "",viewport ? "\"/>" : "",css,body);
  return s;
}
/* package.opf from metadata lines, manifest items and spine itemrefs. */
static char *package(const char *metadata,const char *spine_attr,const char *items,const char *refs) {
  size_t n=strlen(metadata)+strlen(items)+strlen(refs)+1024; char *s=malloc(n); CHECK(s);
  snprintf(s,n,"<?xml version=\"1.0\"?><package xmlns=\"http://www.idpf.org/2007/opf\" version=\"3.0\" unique-identifier=\"u\" "
    "prefix=\"rendition: http://www.idpf.org/vocab/rendition/#\"><metadata xmlns:dc=\"http://purl.org/dc/elements/1.1/\">"
    "<dc:identifier id=\"u\">x</dc:identifier><dc:title>Fixed</dc:title><dc:language>en</dc:language>%s</metadata>"
    "<manifest>%s</manifest><spine%s>%s</spine></package>",metadata,items,spine_attr,refs);
  return s;
}
static exr_layout_config config(float w,float h) {
  exr_layout_config c=exr_layout_config_defaults(); c.page=(exr_layout_options){w,h,20,14,1.4f,0}; c.document_css=1; return c;
}
/* All pages of one part at w x h; *count receives the number of pages. */
static exr_layout *first_page(exr_publication *p,size_t part,float w,float h,size_t *count,exr_document **doc) {
  exr_layout_config c=config(w,h); exr_pager *pager=NULL; exr_layout *first=NULL,*next=NULL;
  OK(exr_publication_load(p,part,doc,&error)); OK(exr_pager_create(*doc,font,&c,&pager,&error));
  *count=0;
  for(;;) { OK(exr_pager_next(pager,&next,&error)); if(!next) break; if(!*count) first=next; else exr_layout_free(next); ++*count; }
  exr_pager_free(pager); return first;
}
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
static uint32_t pixel(const exr_bitmap *b,int x,int y) {
  const unsigned char *p=b->pixels+(size_t)y*b->stride+(size_t)x*4;
  return ((uint32_t)p[0]<<16)|((uint32_t)p[1]<<8)|p[2];
}
static void spreads_equal(exr_publication *p,const size_t (*want)[3],size_t count) {
  exr_spread *s=NULL; size_t n=0,i; OK(exr_publication_spreads(p,&s,&n,&error)); CHECK(n==count);
  for(i=0;i<n;i++) CHECK(s[i].left==want[i][0] && s[i].right==want[i][1] && (s[i].flags&EXR_SPREAD_SINGLE)==want[i][2]);
  exr_free(s);
}
#define NO SIZE_MAX
static void rendition(void) {
  static const char items[]="<item id=\"a\" href=\"a.xhtml\" media-type=\"application/xhtml+xml\"/><item id=\"b\" href=\"b.xhtml\" media-type=\"application/xhtml+xml\"/>"
    "<item id=\"c\" href=\"c.xhtml\" media-type=\"application/xhtml+xml\"/><item id=\"d\" href=\"d.xhtml\" media-type=\"application/xhtml+xml\"/>"
    "<item id=\"e\" href=\"e.xhtml\" media-type=\"application/xhtml+xml\"/><item id=\"f\" href=\"f.xhtml\" media-type=\"application/xhtml+xml\"/>"
    "<item id=\"g\" href=\"g.xhtml\" media-type=\"application/xhtml+xml\"/>";
  char *text=page("width=300, height=400","","<p>x</p>"); exr_part_rendition r; exr_publication *p; char *opf;
  member m[7]={{"a.xhtml",text,0},{"b.xhtml",text,0},{"c.xhtml",text,0},{"d.xhtml",text,0},{"e.xhtml",text,0},{"f.xhtml",text,0},{"g.xhtml",text,0}};
  /* ltr, explicit sides, an item-level reflowable override, an auto side, a center page, a nonlinear page. */
  opf=package("<meta property=\"rendition:layout\">pre-paginated</meta><meta property=\"rendition:spread\">auto</meta>"
              "<meta property=\"rendition:viewport\">width=640, height=480</meta>"," page-progression-direction=\"ltr\"",items,
              "<itemref idref=\"a\" properties=\"page-spread-left\"/><itemref idref=\"b\" properties=\"page-spread-right\"/>"
              "<itemref idref=\"c\" properties=\"rendition:layout-reflowable\"/><itemref idref=\"d\"/>"
              "<itemref idref=\"e\" properties=\"rendition:page-spread-center\"/><itemref idref=\"f\" properties=\"rendition:page-spread-right\"/>"
              "<itemref idref=\"g\" linear=\"no\"/>");
  p=book(opf,m,7);
  CHECK(exr_publication_page_progression(p)==1);
  OK(exr_publication_rendition(p,0,&r,&error)); CHECK(r.layout==EXR_RENDITION_PRE_PAGINATED && r.spread==EXR_SPREAD_LEFT && r.viewport_width==640 && r.viewport_height==480);
  OK(exr_publication_rendition(p,1,&r,&error)); CHECK(r.layout==EXR_RENDITION_PRE_PAGINATED && r.spread==EXR_SPREAD_RIGHT);
  OK(exr_publication_rendition(p,2,&r,&error)); CHECK(r.layout==EXR_RENDITION_REFLOWABLE);
  OK(exr_publication_rendition(p,3,&r,&error)); CHECK(r.layout==EXR_RENDITION_PRE_PAGINATED && r.spread==EXR_SPREAD_AUTO);
  OK(exr_publication_rendition(p,4,&r,&error)); CHECK(r.spread==EXR_SPREAD_CENTER);
  OK(exr_publication_rendition(p,5,&r,&error)); CHECK(r.spread==EXR_SPREAD_RIGHT);
  CHECK(exr_publication_rendition(p,99,&r,&error)==EXR_ARGUMENT);
  { static const size_t want[][3]={{0,1,0},{2,NO,1},{NO,3,0},{4,NO,1},{NO,5,0}}; spreads_equal(p,want,5); }
  exr_publication_free(p); free(opf);
  /* rtl with unspecified sides: first page recto on the left, then right/left pairs. */
  opf=package("<meta property=\"rendition:layout\">pre-paginated</meta>"," page-progression-direction=\"rtl\"",items,
              "<itemref idref=\"a\"/><itemref idref=\"b\"/><itemref idref=\"c\"/><itemref idref=\"d\"/>");
  p=book(opf,m,7); CHECK(exr_publication_page_progression(p)==2);
  { static const size_t want[][3]={{0,NO,0},{2,1,0},{NO,3,0}}; spreads_equal(p,want,3); }
  exr_publication_free(p); free(opf);
  /* rendition:spread none: every page is its own screen. */
  opf=package("<meta property=\"rendition:layout\">pre-paginated</meta><meta property=\"rendition:spread\">none</meta>","",items,
              "<itemref idref=\"a\" properties=\"page-spread-left\"/><itemref idref=\"b\" properties=\"page-spread-right\"/>");
  p=book(opf,m,7);
  { static const size_t want[][3]={{0,NO,1},{1,NO,1}}; spreads_equal(p,want,2); }
  exr_publication_free(p); free(opf);
  /* No rendition data: reflowable, single screens, reflow pages carry no fixed record. */
  opf=package("","",items,"<itemref idref=\"a\"/><itemref idref=\"b\"/>");
  p=book(opf,m,7); CHECK(exr_publication_page_progression(p)==EXR_DIRECTION_LTR);
  OK(exr_publication_rendition(p,0,&r,&error)); CHECK(r.layout==EXR_RENDITION_REFLOWABLE && r.spread==EXR_SPREAD_AUTO && r.viewport_width==0);
  { static const size_t want[][3]={{0,NO,1},{1,NO,1}}; spreads_equal(p,want,2); }
  { size_t count; exr_document *d=NULL; exr_layout *l=first_page(p,0,300,400,&count,&d); CHECK(l && !exr_layout_fixed_viewport(l).fixed);
    exr_layout_free(l); exr_document_free(d); }
  exr_publication_free(p); free(opf); free(text);
}
static void viewport(void) {
  static const char items[]="<item id=\"a\" href=\"a.xhtml\" media-type=\"application/xhtml+xml\"/><item id=\"b\" href=\"b.xhtml\" media-type=\"application/xhtml+xml\"/>"
    "<item id=\"c\" href=\"c.xhtml\" media-type=\"application/xhtml+xml\"/><item id=\"d\" href=\"d.xhtml\" media-type=\"application/xhtml+xml\"/>"
    "<item id=\"e\" href=\"e.xhtml\" media-type=\"application/xhtml+xml\"/><item id=\"i\" href=\"i.png\" media-type=\"image/png\"/>"
    "<item id=\"s\" href=\"s.png\" media-type=\"image/png\"/>";
  size_t isize,ssize,count,i; unsigned char *image=png(600,800,0,200,0,&isize),*small=png(120,90,0,0,220,&ssize);
  char *a=page("width=600, height=800","","<img id=\"full\" src=\"i.png\" alt=\"\" style=\"position:absolute;left:0;top:0;width:600px;height:800px\"/>");
  char *b=page(NULL,"","<p>package viewport</p>");
  char *c=page("width=device-width","","<img id=\"own\" src=\"s.png\" alt=\"\"/>");
  char *d=page(NULL,"","<p>no viewport at all</p>");
  char *long_text=malloc(200000),*e; CHECK(long_text); strcpy(long_text,"");
  for(i=0;i<400;i++) strcat(long_text,"<p>overflowing static text stays on its single fixed page</p>");
  e=page("width=200, height=100","",long_text);
  member m[7]={{"a.xhtml",a,0},{"b.xhtml",b,0},{"c.xhtml",c,0},{"d.xhtml",d,0},{"e.xhtml",e,0},{"i.png",image,isize},{"s.png",small,ssize}};
  char *opf=package("<meta property=\"rendition:layout\">pre-paginated</meta>","",items,
    "<itemref idref=\"a\"/><itemref idref=\"b\" properties=\"x\"/><itemref idref=\"c\"/><itemref idref=\"d\"/><itemref idref=\"e\"/>");
  char *with_package=package("<meta property=\"rendition:layout\">pre-paginated</meta><meta property=\"rendition:viewport\">width=400, height=200</meta>","",items,
    "<itemref idref=\"a\"/><itemref idref=\"b\"/>");
  exr_publication *p=book(opf,m,7),*q=book(with_package,m,7); exr_document *doc=NULL; exr_layout *l; exr_fixed_viewport v; exr_bitmap bmp={0};
  const exr_box *full;
  /* Content meta viewport, portrait target: uniform 0.75, centred horizontally, no crop. */
  l=first_page(p,0,600,600,&count,&doc); v=exr_layout_fixed_viewport(l);
  CHECK(count==1 && v.fixed && v.source==EXR_VIEWPORT_CONTENT && v.width==600 && v.height==800);
  CHECK(near(v.scale,.75f) && near(v.x,75) && near(v.y,0));
  full=box(doc,l,"full"); CHECK(near(full->x,75) && near(full->y,0) && near(full->width,450) && near(full->height,600));
  OK(exr_render_page_color(l,exr_layout_font(l),0,&bmp,&error)); CHECK(bmp.width==600 && bmp.height==600);
  CHECK(pixel(&bmp,76,1)==0x00c800 && pixel(&bmp,523,598)==0x00c800 && pixel(&bmp,300,300)==0x00c800);
  CHECK(pixel(&bmp,10,300)==0xffffff && pixel(&bmp,590,300)==0xffffff); /* letterbox, not stretched */
  exr_bitmap_free(&bmp); exr_layout_free(l); exr_document_free(doc);
  /* Landscape target: same native page, scale 0.5, centred. */
  l=first_page(p,0,800,400,&count,&doc); v=exr_layout_fixed_viewport(l);
  CHECK(count==1 && near(v.scale,.5f) && near(v.x,250) && near(v.y,0));
  full=box(doc,l,"full"); CHECK(near(full->width,300) && near(full->height,400) && near(full->width/full->height,600.0f/800));
  exr_layout_free(l); exr_document_free(doc);
  /* No content meta: package rendition:viewport, else image intrinsic, else the requested page. */
  l=first_page(q,1,800,800,&count,&doc); v=exr_layout_fixed_viewport(l);
  CHECK(count==1 && v.source==EXR_VIEWPORT_PACKAGE && v.width==400 && v.height==200 && near(v.scale,2) && near(v.y,200));
  exr_layout_free(l); exr_document_free(doc);
  l=first_page(p,2,240,360,&count,&doc); v=exr_layout_fixed_viewport(l);
  CHECK(count==1 && v.source==EXR_VIEWPORT_IMAGE && v.width==120 && v.height==90 && near(v.scale,2) && near(v.y,90));
  full=box(doc,l,"own"); CHECK(near(full->x,0) && near(full->y,90) && near(full->width,240) && near(full->height,180));
  exr_layout_free(l); exr_document_free(doc);
  l=first_page(p,3,320,480,&count,&doc); v=exr_layout_fixed_viewport(l);
  CHECK(count==1 && v.source==EXR_VIEWPORT_PAGE && v.width==320 && v.height==480 && near(v.scale,1) && near(v.x,0));
  exr_layout_free(l); exr_document_free(doc);
  /* Overflowing content is still exactly one page; glyphs scale with the page. */
  l=first_page(p,4,400,200,&count,&doc); v=exr_layout_fixed_viewport(l);
  CHECK(count==1 && near(v.scale,2));
  { size_t n; const exr_glyph *g=exr_layout_glyphs(l,&n); CHECK(n>0 && near(g[0].size,32)); }
  exr_layout_free(l); exr_document_free(doc);
  exr_publication_free(p); exr_publication_free(q); free(opf); free(with_package);
  free(a); free(b); free(c); free(d); free(e); free(long_text); mz_free(image); mz_free(small);
}
static void absolute(void) {
  static const char items[]="<item id=\"a\" href=\"a.xhtml\" media-type=\"application/xhtml+xml\"/><item id=\"b\" href=\"b.xhtml\" media-type=\"application/xhtml+xml\"/>";
  const char *css="div,p{margin:0} .x{position:absolute}";
  char *a=page("width=1000, height=1000",css,
    "<p id=\"p1\">static first</p>"
    "<div id=\"a\" class=\"x\" style=\"left:100px;top:50px;width:200px;background-color:#ff0000\">a</div>"
    "<div id=\"b\" class=\"x\" style=\"right:30px;bottom:40px;width:300px;height:100px;background-color:#0000ff\">b</div>"
    "<div id=\"c\" class=\"x\" style=\"left:10%;top:25%;width:20%;background-color:#00ff00\">c</div>"
    "<div id=\"d\" class=\"x\" style=\"width:50px;background-color:#ffff00\">d</div>"
    "<p id=\"p2\">static second</p>"
    "<div id=\"e\" class=\"x\" style=\"left:500px;top:500px;width:400px;height:300px;background-color:#00ffff\">"
    "<div id=\"f\" class=\"x\" style=\"left:20px;top:30px;width:50px;background-color:#ff00ff\">f</div></div>");
  char *b=page("width=1000, height=1000",css,"<p id=\"p1\">static first</p><p id=\"p2\">static second</p>");
  member m[2]={{"a.xhtml",a,0},{"b.xhtml",b,0}};
  char *opf=package("<meta property=\"rendition:layout\">pre-paginated</meta>","",items,"<itemref idref=\"a\"/><itemref idref=\"b\"/>");
  exr_publication *p=book(opf,m,2); exr_document *doc=NULL,*plain=NULL; exr_layout *l,*k; size_t count; const exr_box *x; exr_bitmap bmp={0};
  l=first_page(p,0,1000,1000,&count,&doc); CHECK(count==1 && near(exr_layout_fixed_viewport(l).scale,1));
  x=box(doc,l,"a"); CHECK(near(x->x,100) && near(x->y,50) && near(x->width,200));
  x=box(doc,l,"b"); CHECK(near(x->x+x->width,970) && near(x->y+x->height,960) && near(x->height,100) && near(x->width,300));
  x=box(doc,l,"c"); CHECK(near(x->x,100) && near(x->y,250) && near(x->width,200));
  x=box(doc,l,"e"); CHECK(near(x->x,500) && near(x->y,500) && near(x->height,300));
  x=box(doc,l,"f"); CHECK(near(x->x,520) && near(x->y,530)); /* containing block is the positioned ancestor */
  /* Auto insets keep the static position; out-of-flow boxes do not displace static text. */
  k=first_page(p,1,1000,1000,&count,&plain);
  { size_t n,nk,i,j; const exr_glyph *g=exr_layout_glyphs(l,&n),*h=exr_layout_glyphs(k,&nk); const exr_node *nodes=exr_document_nodes(doc,NULL);
    size_t p2=node(doc,"p2"); float y=-1,yk=-1,static_y=-1;
    for(i=0;i<n;i++) if(nodes[g[i].node].parent==p2) { y=g[i].baseline; break; }
    for(j=0;j<nk;j++) if(exr_document_nodes(plain,NULL)[h[j].node].parent==node(plain,"p2")) { yk=h[j].baseline; break; }
    CHECK(y>0 && near(y,yk));
    for(i=0;i<n;i++) if(nodes[g[i].node].parent==node(doc,"p1")) static_y=g[i].baseline;
    x=box(doc,l,"d"); CHECK(near(x->x,0) && x->y>static_y-1 && x->y<y); }
  OK(exr_render_page_color(l,exr_layout_font(l),0,&bmp,&error));
  CHECK(pixel(&bmp,295,52)==0xff0000 && pixel(&bmp,968,958)==0x0000ff && pixel(&bmp,522,532)==0xff00ff && pixel(&bmp,890,790)==0x00ffff);
  exr_bitmap_free(&bmp); exr_layout_free(l); exr_layout_free(k); exr_document_free(doc); exr_document_free(plain);
  exr_publication_free(p); free(opf); free(a); free(b);
}
static int same_glyphs(const exr_layout *a,const exr_layout *b) {
  size_t n,m,i; const exr_glyph *g=exr_layout_glyphs(a,&n),*h=exr_layout_glyphs(b,&m);
  if(n!=m || !n) return 0;
  for(i=0;i<n;i++) if(g[i].glyph!=h[i].glyph || g[i].x!=h[i].x || g[i].baseline!=h[i].baseline || g[i].size!=h[i].size) return 0;
  return 1;
}
static void mixed(void) {
  static const char items[]="<item id=\"f\" href=\"f.xhtml\" media-type=\"application/xhtml+xml\"/><item id=\"r\" href=\"r.xhtml\" media-type=\"application/xhtml+xml\"/>"
    "<item id=\"q\" href=\"q.xhtml\" media-type=\"application/xhtml+xml\"/>";
  char text[8192]="",*fixed,*reflow,*plain; size_t i,count,count2; int pages_a,pages_b;
  for(i=0;i<30;i++) strcat(text,"<p>Reflowable chapter text wraps to the requested page and repaginates.</p>");
  fixed=page("width=500, height=700","","<div style=\"position:absolute;left:40px;top:60px;width:100px;background-color:#123456\">fixed</div>");
  { char body[9000]; snprintf(body,sizeof(body),"<div id=\"o\" style=\"position:absolute;left:300px;top:5px\">ignored offsets</div>%s",text);
    reflow=page(NULL,"",body);
    snprintf(body,sizeof(body),"<div id=\"o\">ignored offsets</div>%s",text); plain=page(NULL,"",body); }
  member m[3]={{"f.xhtml",fixed,0},{"r.xhtml",reflow,0},{"q.xhtml",plain,0}};
  char *opf=package("<meta property=\"rendition:layout\">reflowable</meta>","",items,
    "<itemref idref=\"f\" properties=\"rendition:layout-pre-paginated\"/><itemref idref=\"r\"/><itemref idref=\"q\" properties=\"rendition:layout-reflowable\"/>");
  char *bare=package("","",items,"<itemref idref=\"f\"/><itemref idref=\"r\"/><itemref idref=\"q\"/>");
  exr_publication *p=book(opf,m,3),*b=book(bare,m,3); exr_part_rendition r; exr_document *d1=NULL,*d2=NULL; exr_layout *l1,*l2;
  OK(exr_publication_rendition(p,0,&r,&error)); CHECK(r.layout==EXR_RENDITION_PRE_PAGINATED);
  OK(exr_publication_rendition(p,1,&r,&error)); CHECK(r.layout==EXR_RENDITION_REFLOWABLE);
  OK(exr_publication_rendition(p,2,&r,&error)); CHECK(r.layout==EXR_RENDITION_REFLOWABLE);
  /* The fixed part: one page at every size. */
  l1=first_page(p,0,600,800,&count,&d1); CHECK(count==1 && exr_layout_fixed_viewport(l1).fixed); exr_layout_free(l1); exr_document_free(d1);
  l1=first_page(p,0,300,400,&count,&d1); CHECK(count==1 && near(exr_layout_fixed_viewport(l1).scale,400.0f/700)); exr_layout_free(l1); exr_document_free(d1);
  /* The reflowable part repaginates and matches the same chapter in a book without rendition data. */
  l1=first_page(p,1,600,800,&count,&d1); l2=first_page(b,1,600,800,&count2,&d2);
  CHECK(!exr_layout_fixed_viewport(l1).fixed && count==count2 && same_glyphs(l1,l2)); pages_a=(int)count;
  exr_layout_free(l1); exr_layout_free(l2); exr_document_free(d1); exr_document_free(d2);
  l1=first_page(p,1,300,400,&count,&d1); CHECK((int)count>pages_a && !exr_layout_fixed_viewport(l1).fixed); pages_b=(int)count;
  exr_layout_free(l1); exr_document_free(d1);
  /* position:absolute is not applied on reflowable pages: identical to the same text without it. */
  l1=first_page(p,1,600,800,&count,&d1); l2=first_page(p,2,600,800,&count2,&d2);
  CHECK(count==count2 && same_glyphs(l1,l2));
  exr_layout_free(l1); exr_layout_free(l2); exr_document_free(d1); exr_document_free(d2);
  CHECK(pages_b>pages_a);
  exr_publication_free(p); exr_publication_free(b); free(opf); free(bare); free(fixed); free(reflow); free(plain);
}
int main(int argc,char **argv) {
  char path[4096];
  if(argc!=3) { fprintf(stderr,"usage: %s fixtures rendition|viewport|absolute|mixed\n",argv[0]); return 2; }
  snprintf(path,sizeof(path),"%s/fonts/primary.ttf",argv[1]); OK(exr_font_open(path,&font,&error));
  if(!strcmp(argv[2],"rendition")) rendition();
  else if(!strcmp(argv[2],"viewport")) viewport();
  else if(!strcmp(argv[2],"absolute")) absolute();
  else if(!strcmp(argv[2],"mixed")) mixed();
  else return 2;
  exr_font_free(font); printf("%u fixed-layout %s checks passed\n",checks,argv[2]); return 0;
}
