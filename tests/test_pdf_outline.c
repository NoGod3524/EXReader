/* SPDX-License-Identifier: GPL-3.0-only */
#include "../src/pdf_face_internal.h"
static exr_error error; static unsigned checks;
#define CHECK(x) do { checks++; if(!(x)) { fprintf(stderr,"line %d: %s (%d: %s)\n",__LINE__,#x,error.code,error.message); exit(1); } } while(0)
#define OK(x) CHECK((x)==EXR_OK)
static unsigned char *read_fixture(const char *dir,const char *name,size_t *size) {
  char path[4096]; FILE *file; long n; unsigned char *data;
  snprintf(path,sizeof(path),"%s/%s",dir,name); file=fopen(path,"rb"); CHECK(file && !fseek(file,0,SEEK_END)); n=ftell(file); CHECK(n>0); rewind(file);
  *size=(size_t)n; data=malloc(*size); CHECK(data && fread(data,1,*size,file)==*size); fclose(file); return data;
}
static uint32_t resources(exr_pdf_file *file) { uint32_t id; OK(exr_pdf_resolve(file,exr_pdf_get(file,exr_pdf_root(file),"Resources"),&id,&error)); return id; }
static exr_pdf_font *font_open(exr_pdf_file *file,const char *name) {
  uint32_t fonts; exr_pdf_font *font=NULL; OK(exr_pdf_resolve(file,exr_pdf_get(file,resources(file),"Font"),&fonts,&error));
  OK(exr_pdf_font_open(file,exr_pdf_get(file,fonts,name),NULL,&font,&error)); return font;
}
static exr_pdf_character character(exr_pdf_font *font,const char *s,size_t n) {
  exr_pdf_character ch; size_t at=0; OK(exr_pdf_font_next(font,(const unsigned char *)s,n,&at,&ch,&error)); CHECK(at==n); return ch;
}
static int cancelled(void *context) { (void)context; return 1; }
static void glyph_selection(exr_pdf_file *file,FT_Library library) {
  const char *names[]={"Names","Unicode","Symbol","Cubic","CID","GlyphOnly"}; size_t i,j,work=0,count; uint32_t glyph;
  for(i=0;i<sizeof(names)/sizeof(*names);i++) {
    exr_pdf_font *font=font_open(file,names[i]); exr_pdf_face *face=NULL; exr_pdf_character ch; exr_vector_segment *segments=NULL;
    OK(exr_pdf_face_open(library,font,NULL,&face,NULL,&error)); CHECK(exr_pdf_face_memory(face)>0);
    ch=character(font,i==4 ? "\0\x2a" : i==5 ? "\0\2" : "A",i>=4 ? 2 : 1);
    if(i<4) CHECK(ch.text.size==1 && ch.text.utf8[0]=='A'); /* Semantic A still paints fi. */
    OK(exr_pdf_face_glyph(face,&ch,&glyph,&error)); CHECK(glyph==2);
    OK(exr_pdf_face_outline(face,&ch,&segments,&count,&work,NULL,&error)); CHECK(count>=5);
    if(i<5) CHECK(segments[0].verb==EXR_VECTOR_MOVE && segments[0].points[0].x==500 && segments[0].points[0].y==0);
    free(segments);
    if(i==0) {
      exr_pdf_face *shared=NULL; exr_pdf_font *other=font_open(file,"CID");
      CHECK(exr_pdf_face_matches(face,font,NULL) && !exr_pdf_face_matches(face,other,NULL));
      CHECK(exr_pdf_face_open_shared(library,other,NULL,face,&shared,NULL,&error)==EXR_ARGUMENT && !shared); exr_pdf_font_close(other);
      OK(exr_pdf_face_open_shared(library,font,NULL,face,&shared,NULL,&error)); exr_pdf_face_close(face); face=shared;
      OK(exr_pdf_face_outline(face,&ch,&segments,&count,&work,NULL,&error)); CHECK(count>=5 && segments[0].points[0].x==500); free(segments);
    }
    if(i<4) {
      ch=character(font,"Q",1); OK(exr_pdf_face_outline(face,&ch,&segments,&count,&work,NULL,&error));
      for(j=0;j<count;j++) if(segments[j].verb==(i==3 ? EXR_VECTOR_CUBIC : EXR_VECTOR_QUAD)) break;
      if(i!=2) CHECK(j<count);
      free(segments);
      ch=character(font," ",1); OK(exr_pdf_face_outline(face,&ch,&segments,&count,&work,NULL,&error)); CHECK(!count); free(segments);
    }
    { exr_control control={0}; control.cancelled=cancelled; segments=(void *)(uintptr_t)1; count=1;
      CHECK(exr_pdf_face_outline(face,&ch,&segments,&count,&work,&control,&error)==EXR_CANCELLED && !segments && !count);
    }
    if(i==4) {
      ch=character(font,"\0\1",2); OK(exr_pdf_face_glyph(face,&ch,&glyph,&error)); CHECK(glyph==1);
      ch=character(font,"\0\2",2); OK(exr_pdf_face_glyph(face,&ch,&glyph,&error)); CHECK(!glyph);
    }
    exr_pdf_face_close(face); exr_pdf_font_close(font);
  }
  CHECK(!exr_pdf_face_memory(NULL)); exr_pdf_face_close(NULL);
}
typedef struct { FT_Library library; exr_bitmap bitmap; size_t work,glyphs; } raster;
static exr_status draw_glyph(void *context,const exr_pdf_text_glyph *g,exr_error *e) {
  raster *r=context; exr_pdf_face *face=NULL; exr_vector_segment *segments=NULL; exr_vector_polyline path={0}; exr_vector_edge *edges=NULL; size_t count=0,edge_count=0;
  exr_status status=exr_pdf_face_open(r->library,g->font,NULL,&face,NULL,e);
  if(status==EXR_OK) status=exr_pdf_face_outline(face,&g->character,&segments,&count,&r->work,NULL,e);
  exr_pdf_face_close(face); /* The outline is independent of the FT slot/face. */
  if(status==EXR_OK) status=exr_vector_flatten(segments,count,g->transform,.01,&path,&r->work,NULL,e);
  if(status==EXR_OK) status=exr_vector_edges(&path,1,&edges,&edge_count,&r->work,NULL,e);
  if(status==EXR_OK) status=exr_vector_fill(&r->bitmap,edges,edge_count,EXR_VECTOR_NONZERO,0x000000ff,NULL,&r->work,NULL,e);
  r->glyphs++; free(segments); free(edges); exr_vector_polyline_free(&path); return status;
}
static void rasterized(exr_pdf_file *file,FT_Library library) {
  raster r={0}; exr_pdf_draw_callbacks cb={0}; const double flip[6]={1,0,0,-1,0,12}; const char content[]="BT /Names 10 Tf (A) Tj ET";
  r.library=library; r.bitmap.width=r.bitmap.height=12; r.bitmap.channels=1; r.bitmap.stride=12; r.bitmap.pixels=malloc(144); CHECK(r.bitmap.pixels); cb.glyph=draw_glyph;
  memset(r.bitmap.pixels,255,144); OK(exr_pdf_draw_ops(file,resources(file),content,sizeof(content)-1,NULL,&cb,&r,NULL,&error));
  CHECK(r.glyphs==1 && r.bitmap.pixels[12+6]==0 && r.bitmap.pixels[12+1]==255 && r.bitmap.pixels[12*8+6]==255);
  memset(r.bitmap.pixels,255,144); OK(exr_pdf_draw_ops(file,resources(file),content,sizeof(content)-1,flip,&cb,&r,NULL,&error));
  CHECK(r.bitmap.pixels[12*10+6]==0 && r.bitmap.pixels[12+6]==255); free(r.bitmap.pixels);
}
static void generic_and_fallback(const char *dir,FT_Library library) {
  size_t size,count=1,work=0; unsigned char *data=read_fixture(dir,"fonts/pdf-names.ttf",&size); FT_Face ft=NULL; exr_vector_segment *segments=NULL;
  OK(FT_New_Memory_Face(library,data,(FT_Long)size,0,&ft));
  OK(exr_font_outline(ft,1,&segments,&count,&work,NULL,&error)); CHECK(count>=5 && segments[1].points[0].x==400); free(segments);
  CHECK(exr_font_outline(ft,9999,&segments,&count,NULL,NULL,&error)==EXR_ARGUMENT && !segments && !count);
  work=(size_t)256*1024*1024; CHECK(exr_font_outline(ft,1,&segments,&count,&work,NULL,&error)==EXR_LIMIT && !segments && !count);
  FT_Done_Face(ft);
  { exr_pdf_file *file=NULL; exr_pdf_font *font=NULL; exr_pdf_face *face=NULL; exr_pdf_character ch; uint32_t fonts,id,glyph; size_t pdf_size; unsigned char *pdf=read_fixture(dir,"pdf-font-fallback.pdf",&pdf_size);
    OK(exr_pdf_open(pdf,pdf_size,&file,&error)); OK(exr_pdf_resolve(file,exr_pdf_get(file,exr_pdf_root(file),"Fonts"),&fonts,&error)); id=exr_pdf_get(file,fonts,"Helvetica"); OK(exr_pdf_font_open(file,id,NULL,&font,&error));
    CHECK(exr_pdf_face_open(library,font,NULL,&face,NULL,&error)==EXR_FORMAT && !face);
    { exr_font_input source={data,size,0}; OK(exr_pdf_face_open(library,font,&source,&face,NULL,&error)); } ch=character(font,"A",1);
    OK(exr_pdf_face_glyph(face,&ch,&glyph,&error)); CHECK(glyph==1); exr_pdf_face_close(face); exr_pdf_font_close(font); exr_pdf_close(file); free(pdf);
  }
  free(data);
}
int main(int argc,char **argv) {
  FT_Library library=NULL; exr_pdf_file *file=NULL; unsigned char *data; size_t size;
  CHECK(argc==2); CHECK(!FT_Init_FreeType(&library)); data=read_fixture(argv[1],"pdf-outlines.pdf",&size); OK(exr_pdf_open(data,size,&file,&error));
  glyph_selection(file,library); rasterized(file,library); generic_and_fallback(argv[1],library);
  exr_pdf_close(file); free(data); FT_Done_FreeType(library); printf("%u native PDF outline checks passed\n",checks); return 0;
}
