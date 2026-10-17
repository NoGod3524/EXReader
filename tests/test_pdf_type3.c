/* SPDX-License-Identifier: GPL-3.0-only */
#include "exreader.h"
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static exr_error error; static unsigned checks;
#define CHECK(x) do { checks++; if(!(x)) { fprintf(stderr,"line %d: %s (%d: %s)\n",__LINE__,#x,error.code,error.message); exit(1); } } while(0)
#define OK(x) CHECK((x)==EXR_OK)
#define NEAR(a,b) CHECK(fabs((a)-(b))<1e-7)
#define LOCAL "<< /Font << /F1 5 0 R /F2 6 0 R >> /XObject << /Fm 11 0 R /Im 12 0 R >> >>"
#define DEFAULT_TEXT "0 0 1 rg 0 1 0 RG BT /F1 24 Tf 1 0 0 1 20 20 Tm (AB) Tj ET"
#define SQUARE "500 0 d0 1 0 0 rg 0 0 500 500 re f"
static char pdf[65536]; static size_t size,offset[15]; static int mask_image=1;
static void add(const char *text) { size_t n=strlen(text); CHECK(n<sizeof(pdf)-size); memcpy(pdf+size,text,n); size+=n; pdf[size]=0; }
static void object(unsigned id,const char *body) {
  char row[64]; offset[id]=size; snprintf(row,sizeof(row),"%u 0 obj\n",id); add(row); add(body); add("\nendobj\n");
}
static void stream(unsigned id,const char *dictionary,const char *content) {
  char row[2048]; offset[id]=size; snprintf(row,sizeof(row),"%u 0 obj\n<< %s /Length %zu >>\nstream\n",id,dictionary,strlen(content));
  add(row); add(content); add("\nendstream\nendobj\n");
}
static void build(const char *program,const char *content,const char *matrix,const char *resources,const char *font_override) {
  char row[2048]; size_t xref; unsigned i; size=0; memset(offset,0,sizeof(offset)); add("%PDF-1.7\n");
  object(1,"<< /Type /Catalog /Pages 2 0 R >>"); object(2,"<< /Type /Pages /Count 2 /Kids [3 0 R 4 0 R] >>");
  object(3,"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 64 64] /Resources " LOCAL " /Contents 7 0 R >>");
  object(4,"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 64 64] /Contents 8 0 R >>");
  snprintf(row,sizeof(row),"<< /Type /Font /Subtype /Type3 /FontBBox [0 0 600 500] /FontMatrix [%s] /FirstChar 65 /LastChar 66 /Widths [500 600] /Encoding << /Differences [65 /A /B] >> /CharProcs << /A 9 0 R /B 10 0 R >> /ToUnicode 13 0 R %s %s >>",
    matrix ? matrix : ".001 0 0 .001 0 0",resources ? "/Resources" : "",resources ? resources : ""); object(5,font_override ? font_override : row);
  object(6,"<< /Type /Font /Subtype /Type3 /FontBBox [0 0 1000 1000] /FontMatrix [.001 0 0 .001 0 0] /FirstChar 65 /LastChar 65 /Widths [1000] /Encoding << /Differences [65 /C] >> /CharProcs << /C 14 0 R >> >>");
  stream(7,"",content ? content : DEFAULT_TEXT); stream(8,"","0 0 1 rg 0 0 64 64 re f");
  stream(9,"",program ? program : SQUARE); stream(10,"","600 0 d0 0 0 300 500 re f");
  stream(11,"/Type /XObject /Subtype /Form /BBox [0 0 500 500]","0 0 500 500 re f");
  stream(12,mask_image ? "/Type /XObject /Subtype /Image /Width 1 /Height 1 /ImageMask true /BitsPerComponent 1 /Decode [1 0] /Filter /ASCIIHexDecode" :
    "/Type /XObject /Subtype /Image /Width 1 /Height 1 /BitsPerComponent 8 /ColorSpace /DeviceRGB /Filter /ASCIIHexDecode",mask_image ? "80>" : "FF0000>");
  stream(13,"","/CIDInit /ProcSet findresource begin 12 dict begin begincmap /CMapType 2 def 1 begincodespacerange <00> <FF> endcodespacerange 2 beginbfchar <41> <4E2D> <42> <00660069> endbfchar endcmap end end");
  stream(14,"","1000 0 d0 0 0 1000 1000 re f");
  xref=size; add("xref\n0 15\n0000000000 65535 f \n");
  for(i=1;i<15;i++) { snprintf(row,sizeof(row),"%010zu 00000 n \n",offset[i]); add(row); }
  snprintf(row,sizeof(row),"trailer\n<< /Size 15 /Root 1 0 R >>\nstartxref\n%zu\n%%%%EOF\n",xref); add(row);
}
static exr_fixed_document *open_pdf(void) { exr_fixed_document *document=NULL; OK(exr_fixed_open_memory(EXR_PDF,pdf,size,NULL,&document,&error)); return document; }
static exr_bitmap rendered(exr_fixed_document *document,size_t page) {
  exr_bitmap image={0}; OK(exr_fixed_render(document,page,1,NULL,&image,&error)); CHECK(image.width==64 && image.height==64 && image.channels==4); return image;
}
static uint32_t color(const exr_bitmap *image,unsigned x,unsigned y) {
  const unsigned char *p=image->pixels+(image->height-y-1)*image->stride+x*4;
  return ((uint32_t)p[0]<<16)|((uint32_t)p[1]<<8)|p[2];
}
static void save(const char *directory,const char *name) {
  FILE *f; char path[4096]; if(!directory) return;
  snprintf(path,sizeof(path),"%s/%s",directory,name); f=fopen(path,"wb"); CHECK(f); CHECK(fwrite(pdf,1,size,f)==size); CHECK(!fclose(f));
}
static void text(exr_fixed_document *document,const char *expected,size_t expected_count,double second_x) {
  exr_fixed_text *snapshot=NULL; const exr_text_region *regions; size_t n,size_bytes;
  OK(exr_fixed_load_text(document,0,NULL,&snapshot,&error)); CHECK(!strcmp(exr_fixed_text_string(snapshot,&size_bytes),expected) && size_bytes==strlen(expected));
  regions=exr_fixed_text_regions(snapshot,&n); CHECK(n==expected_count);
  if(n>1) NEAR(regions[1].quad[0],second_x);
  exr_fixed_text_free(snapshot);
}
static void painting(const char *directory) {
  exr_fixed_document *d; exr_bitmap b;
  build(NULL,NULL,NULL,LOCAL,NULL); d=open_pdf(); b=rendered(d,0);
  CHECK(color(&b,22,22)==0xff0000 && color(&b,34,22)==0x0000ff && color(&b,47,22)==0xffffff);
  text(d,"\xe4\xb8\xad" "fi",2,32); save(directory,"pdf-type3-basic.pdf"); exr_bitmap_free(&b); exr_fixed_free(d);
  build("500 0 0 0 500 500 d1 0 0 500 500 re f",NULL,NULL,LOCAL,NULL); d=open_pdf(); b=rendered(d,0);
  CHECK(color(&b,22,22)==0x0000ff && color(&b,34,22)==0x0000ff); save(directory,"pdf-type3-uncolored.pdf"); exr_bitmap_free(&b); exr_fixed_free(d);
  build(NULL,NULL,".002 0 0 .001 0 0",LOCAL,NULL); d=open_pdf(); b=rendered(d,0);
  CHECK(color(&b,43,22)==0xff0000 && color(&b,46,22)==0x0000ff); text(d,"\xe4\xb8\xad" "fi",2,44); exr_bitmap_free(&b); exr_fixed_free(d);
  build(NULL,NULL,".001 .0005 0 .001 0 0",LOCAL,NULL); d=open_pdf(); b=rendered(d,0);
  CHECK(color(&b,28,25)==0xff0000 && color(&b,34,22)==0x0000ff); text(d,"\xe4\xb8\xad" "fi",2,32);
  save(directory,"pdf-type3-shear.pdf"); exr_bitmap_free(&b); exr_fixed_free(d);
  build(NULL,NULL,".001 .0005 .00025 .001 .1 .05",LOCAL,NULL); d=open_pdf(); b=rendered(d,0);
  CHECK(color(&b,26,26)==0xff0000 && color(&b,20,20)==0xffffff); text(d,"\xe4\xb8\xad" "fi",2,34.4);
  { exr_fixed_text *t=NULL; const exr_text_region *r; size_t n; OK(exr_fixed_load_text(d,0,NULL,&t,&error)); r=exr_fixed_text_regions(t,&n);
    CHECK(n==2); NEAR(r[0].quad[0],22.4); NEAR(r[0].quad[1],21.2); NEAR(r[0].quad[4],39.8); NEAR(r[0].quad[5],40.4); exr_fixed_text_free(t);
  }
  save(directory,"pdf-type3-affine.pdf"); exr_bitmap_free(&b); exr_fixed_free(d);
  build(NULL,"BT /F1 24 Tf 20 20 Td (AA) Tj ET","0 .001 -.001 0 0 0",LOCAL,NULL); d=open_pdf(); b=rendered(d,0);
  CHECK(color(&b,10,22)==0xff0000 && color(&b,21,22)==0xffffff);
  text(d,"\xe4\xb8\xad\xe4\xb8\xad",2,20);
  { exr_fixed_text *t=NULL; const exr_text_region *r; size_t n; OK(exr_fixed_load_text(d,0,NULL,&t,&error)); r=exr_fixed_text_regions(t,&n);
    CHECK(n==2); NEAR(r[0].quad[0],20); NEAR(r[0].quad[2],20); NEAR(r[0].quad[4],8); NEAR(r[0].quad[6],8);
    exr_fixed_text_free(t);
  }
  save(directory,"pdf-type3-rotate.pdf"); exr_bitmap_free(&b); exr_fixed_free(d);
  build("1 0 d0 1 0 0 rg 0 0 1 1 re f","BT /F1 24 Tf 20 20 Td (AA) Tj ET",NULL,NULL,
    "<< /Subtype /Type3 /FontBBox [0 0 1 1] /FontMatrix [1 0 0 1 0 0] /FirstChar 65 /LastChar 65 /Widths [1] /Encoding << /Differences [65 /A] >> /CharProcs << /A 9 0 R >> >>");
  d=open_pdf(); b=rendered(d,0); CHECK(color(&b,22,22)==0xff0000 && color(&b,60,22)==0xff0000); text(d,"AA",2,44); exr_bitmap_free(&b); exr_fixed_free(d);
}
static void modes_and_resources(const char *directory) {
  unsigned mode; exr_fixed_document *d; exr_bitmap b; char content[512];
  for(mode=0;mode<8;mode++) {
    snprintf(content,sizeof(content),"BT /F1 24 Tf %u Tr 20 20 Td (A) Tj ET",mode); build(NULL,content,NULL,NULL,NULL);
    d=open_pdf(); b=rendered(d,0); CHECK(color(&b,22,22)==((mode==3 || mode==7) ? 0xffffff : 0xff0000));
    exr_bitmap_free(&b); exr_fixed_free(d);
    snprintf(content,sizeof(content),"BT /F1 24 Tf %u Tr 20 20 Td (A) Tj ET 0 1 0 rg 0 0 64 64 re f",mode);
    build(NULL,content,NULL,NULL,NULL); d=open_pdf(); b=rendered(d,0); CHECK(color(&b,1,1)==0x00ff00 && color(&b,22,22)==0x00ff00); exr_bitmap_free(&b); exr_fixed_free(d);
  }
  build("500 0 0 0 500 500 d1 /Fm Do",NULL,NULL,NULL,NULL); d=open_pdf(); b=rendered(d,0);
  CHECK(color(&b,22,22)==0x0000ff); exr_bitmap_free(&b); exr_fixed_free(d); /* Absent font Resources inherits page scope. */
  build("500 0 0 0 500 500 d1 q 500 0 0 500 0 0 cm /Im Do Q",NULL,NULL,LOCAL,NULL); d=open_pdf(); b=rendered(d,0);
  CHECK(color(&b,22,22)==0x0000ff); save(directory,"pdf-type3-stencil.pdf"); exr_bitmap_free(&b); exr_fixed_free(d);
  build("500 0 d0 BT /F2 500 Tf 0 Tr (A) Tj ET",NULL,NULL,LOCAL,NULL); d=open_pdf(); b=rendered(d,0);
  CHECK(color(&b,22,22)==0x0000ff && color(&b,34,22)==0x0000ff); text(d,"\xe4\xb8\xad" "fi",2,32);
  save(directory,"pdf-type3-nested-text.pdf"); exr_bitmap_free(&b); exr_fixed_free(d);
  /* Changes inside a glyph never leak CTM, color, local clipping or text state. */
  build("500 0 d0 1 0 0 rg 0 0 250 500 re W n 0 0 500 500 re f 1 0 0 1 300 0 cm",NULL,NULL,LOCAL,NULL); d=open_pdf(); b=rendered(d,0);
  CHECK(color(&b,22,22)==0xff0000 && color(&b,29,22)==0xffffff && color(&b,34,22)==0x0000ff); exr_bitmap_free(&b); exr_fixed_free(d);
  { const char *const entries[]={"/.notdef 9 0 R","/A 99 0 R /.notdef 9 0 R","/A null /.notdef 9 0 R"}; size_t i; char font[1024];
    for(i=0;i<sizeof(entries)/sizeof(*entries);i++) {
      snprintf(font,sizeof(font),"<< /Subtype /Type3 /FontBBox [0 0 500 500] /FontMatrix [.001 0 0 .001 0 0] /FirstChar 65 /LastChar 65 /Widths [500] /Encoding << /Differences [65 /A] >> /CharProcs << %s >> /ToUnicode 13 0 R >>",entries[i]);
      build(NULL,"BT /F1 24 Tf 20 20 Td (A) Tj ET",NULL,NULL,font); d=open_pdf(); b=rendered(d,0); CHECK(color(&b,22,22)==0xff0000);
      text(d,"\xe4\xb8\xad",1,0); exr_bitmap_free(&b); exr_fixed_free(d);
    }
  }
}
static void rect(exr_path_segment p[5],double size_value) {
  memset(p,0,5*sizeof(*p)); p[0].verb=EXR_PATH_MOVE; p[1].verb=p[2].verb=p[3].verb=EXR_PATH_LINE; p[4].verb=EXR_PATH_CLOSE;
  p[1].points[0].x=p[2].points[0].x=size_value; p[2].points[0].y=p[3].points[0].y=size_value;
}
static void nested_clip_union(void) {
  exr_fixed_document *d; exr_canvas *canvas=NULL; exr_canvas_config config={0}; exr_draw_sink sink={0}; exr_path_segment p[5];
  exr_draw_style style=exr_draw_style_defaults(); const exr_bitmap *bitmap; const double identity[6]={1,0,0,1,0,0};
  build("500 0 d0 BT /F2 500 Tf 0 Tr (A) Tj ET",NULL,NULL,LOCAL,NULL); d=open_pdf(); config.width=config.height=64; config.background=0xffffffff;
  OK(exr_canvas_create(&config,&canvas,&error)); OK(exr_canvas_get_sink(canvas,&sink,&error));
  OK(sink.state(sink.context,EXR_DRAW_BEGIN_CLIP,&error)); rect(p,8); OK(sink.clip(sink.context,p,5,NULL,EXR_FILL_NONZERO,1,&error));
  OK(exr_fixed_draw(d,0,identity,&sink,NULL,&error)); OK(sink.state(sink.context,EXR_DRAW_END_CLIP,&error));
  rect(p,64); style.fill=0xff0000ff; OK(sink.path(sink.context,p,5,NULL,&style,&error)); bitmap=exr_canvas_bitmap(canvas); CHECK(bitmap);
  /* Here canvas uses the caller's unchanged y-up identity rather than the
     PDF raster helper's y-flip; the pending outer union must survive both BTs. */
  CHECK(color(bitmap,2,61)==0xff0000 && color(bitmap,10,53)==0xffffff && color(bitmap,22,41)==0x0000ff);
  exr_canvas_free(canvas); exr_fixed_free(d);
}
static int cancelled(void *context) { return *(int *)context; }
typedef struct { unsigned depth,text,paths; int cancel; } observer;
static exr_status observed_state(void *context,exr_draw_state state,exr_error *e) {
  observer *o=context; (void)e;
  if(state==EXR_DRAW_SAVE) o->depth++;
  else if(state==EXR_DRAW_RESTORE) { CHECK(o->depth); o->depth--; }
  else if(state==EXR_DRAW_BEGIN_CLIP) o->text++;
  else if(state==EXR_DRAW_END_CLIP) { CHECK(o->text); o->text--; }
  return EXR_OK;
}
static exr_status observed_path(void *context,const exr_path_segment *p,size_t count,const double matrix[6],const exr_draw_style *style,exr_error *e) {
  observer *o=context; (void)p; (void)count; (void)matrix; (void)style; (void)e; o->paths++; return o->cancel ? EXR_CANCELLED : EXR_OK;
}
static void fail_render(const char *program,const char *resources,exr_status expected) {
  exr_fixed_document *d; exr_bitmap b={0}; build(program,NULL,NULL,resources,NULL); d=open_pdf();
  CHECK(exr_fixed_render(d,0,1,NULL,&b,&error)==expected && !b.pixels && !b.width);
  b=rendered(d,1); CHECK(color(&b,20,20)==0x0000ff); exr_bitmap_free(&b); exr_fixed_free(d);
}
static void failures(void) {
  static const char *const bad[]={"0 0 1 1 re f","q 500 0 d0 Q","500 0 d0 500 0 d0","500 1 d0","500 0 1 1 0 0 d1",
    "500 0 0 0 500 500 d1 1 0 0 rg","500 0 d0 q","500 0 d0 BT","500 0 d0 0 0 m"};
  size_t i; exr_fixed_document *d; exr_bitmap b={0}; exr_fixed_render_options options={0}; int stop=1;
  for(i=0;i<sizeof(bad)/sizeof(*bad);i++) fail_render(bad[i],LOCAL,EXR_FORMAT);
  fail_render("500 0 d0 /Fm Do","<< >>",EXR_FORMAT);
  fail_render("500 0 d0 BT /F1 500 Tf (A) Tj ET",LOCAL,EXR_FORMAT); /* Recursive CharProc, not a fresh page budget. */
  mask_image=0; fail_render("500 0 0 0 500 500 d1 q 500 0 0 500 0 0 cm /Im Do Q",LOCAL,EXR_FORMAT); mask_image=1;
  build(NULL,NULL,NULL,LOCAL,NULL); d=open_pdf(); options.control=(exr_control){cancelled,NULL,&stop};
  CHECK(exr_fixed_render(d,0,1,&options,&b,&error)==EXR_CANCELLED && !b.pixels); stop=0;
  OK(exr_fixed_render(d,0,1,&options,&b,&error)); exr_bitmap_free(&b); exr_fixed_free(d);
  { observer o={0}; exr_draw_sink sink={0}; const double identity[6]={1,0,0,1,0,0};
    build("500 0 d0 BT /F2 500 Tf 0 Tr (A) Tj ET",NULL,NULL,LOCAL,NULL); d=open_pdf(); sink.context=&o; sink.state=observed_state; sink.path=observed_path;
    o.cancel=1; CHECK(exr_fixed_draw(d,0,identity,&sink,NULL,&error)==EXR_CANCELLED); CHECK(o.paths==1 && !o.depth && !o.text);
    o.cancel=0; OK(exr_fixed_draw(d,0,identity,&sink,NULL,&error)); CHECK(o.paths>1 && !o.depth && !o.text); exr_fixed_free(d);
  }
}
int main(int argc,char **argv) {
  const char *directory=argc==2 ? argv[1] : NULL; CHECK(argc<=2); painting(directory); modes_and_resources(directory); nested_clip_union(); failures();
  printf("PDF Type3 painting passed (%u checks)\n",checks); return 0;
}
