/* SPDX-License-Identifier: GPL-3.0-only */
#include "exreader.h"
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static exr_error error;
static unsigned checks;
#define CHECK(x) do { checks++; if(!(x)) { fprintf(stderr,"line %d: %s (%d: %s)\n",__LINE__,#x,error.code,error.message); exit(1); } } while(0)
#define OK(x) CHECK((x)==EXR_OK)
static char pdf[4096];
static size_t length;
static void source(void) {
  static const char *objects[]={
    "<< /Type /Catalog /Pages 2 0 R >>",
    "<< /Type /Pages /Count 1 /Kids [3 0 R] >>",
    "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 64 64] >>"
  };
  size_t offsets[4]={0},xref; unsigned i;
  length=(size_t)snprintf(pdf,sizeof(pdf),"%%PDF-1.7\n");
  for(i=1;i<4;i++) { offsets[i]=length; length+=(size_t)snprintf(pdf+length,sizeof(pdf)-length,"%u 0 obj\n%s\nendobj\n",i,objects[i-1]); }
  xref=length; length+=(size_t)snprintf(pdf+length,sizeof(pdf)-length,"xref\n0 4\n0000000000 65535 f \n");
  for(i=1;i<4;i++) length+=(size_t)snprintf(pdf+length,sizeof(pdf)-length,"%010zu 00000 n \n",offsets[i]);
  length+=(size_t)snprintf(pdf+length,sizeof(pdf)-length,"trailer\n<< /Size 4 /Root 1 0 R >>\nstartxref\n%zu\n%%%%EOF\n",xref);
  CHECK(length<sizeof(pdf));
}
static exr_page_annotation annotation(const char *kind,const double *quad) {
  exr_page_annotation a={0}; a.id="line-markup"; a.kind=kind; a.bounds[0]=8; a.bounds[1]=8; a.bounds[2]=56; a.bounds[3]=32;
  a.quads=quad; a.quad_count=1; return a;
}
static exr_bitmap render(const void *bytes,size_t size) {
  exr_fixed_document *document=NULL; exr_bitmap bitmap={0};
  OK(exr_fixed_open_memory(EXR_PDF,bytes,size,NULL,&document,&error));
  OK(exr_fixed_render(document,0,4,NULL,&bitmap,&error)); CHECK(bitmap.width==256 && bitmap.height==256 && bitmap.channels==4);
  exr_fixed_free(document); return bitmap;
}
static unsigned color_bounds(const exr_bitmap *bitmap,double bounds[4]) {
  size_t x,y; unsigned count=0,solid=0; bounds[0]=bounds[1]=64; bounds[2]=bounds[3]=0;
  for(y=0;y<bitmap->height;y++) for(x=0;x<bitmap->width;x++) {
    const unsigned char *pixel=bitmap->pixels+y*bitmap->stride+x*4;
    if(pixel[1]>=250) continue;
    CHECK(pixel[0]==255 && pixel[1]>=126 && pixel[2]==pixel[1]);
    if(pixel[1]<=129) solid++;
    { double px=((double)x+.5)/4,py=64-((double)y+.5)/4;
      if(px<bounds[0]) bounds[0]=px;
      if(py<bounds[1]) bounds[1]=py;
      if(px>bounds[2]) bounds[2]=px;
      if(py>bounds[3]) bounds[3]=py;
    }
    count++;
  }
  CHECK(!count || solid>10); return count;
}
static void roundtrip(const void *data,size_t size,const exr_page_annotation *expected) {
  exr_fixed_document *document=NULL; exr_page_annotation *loaded=NULL; size_t count=0;
  OK(exr_fixed_open_memory(EXR_PDF,data,size,NULL,&document,&error));
  OK(exr_fixed_load_annotations(document,0,NULL,&loaded,&count,&error));
  CHECK(count==1 && !strcmp(loaded[0].id,expected->id) && !strcmp(loaded[0].kind,expected->kind));
  CHECK(loaded[0].quad_count==expected->quad_count && !memcmp(loaded[0].quads,expected->quads,expected->quad_count*8*sizeof(double)));
  CHECK(!memcmp(loaded[0].bounds,expected->bounds,sizeof(expected->bounds)));
  exr_page_annotations_free(loaded,count); exr_fixed_free(document);
}
static void save(const char *directory,const char *kind,const void *bytes,size_t size) {
  char path[4096]; FILE *f; if(!directory) return;
  snprintf(path,sizeof(path),"%s/pdf-markup-%s.pdf",directory,kind); f=fopen(path,"wb"); CHECK(f);
  CHECK(fwrite(bytes,1,size,f)==size); CHECK(!fclose(f));
}
static void markup(const char *kind,const char *directory) {
  static const double z[]={8,32,56,32,8,8,56,8};
  static const double perimeter[]={8,32,56,32,56,8,8,8};
  static const double reverse[]={56,32,8,32,56,8,8,8};
  static const double vertical[]={20,8,20,56,44,8,44,56};
  double duplicate[16],bounds[4]; exr_page_annotation a=annotation(kind,z); exr_bitmap first={0},second={0};
  exr_pdf_annotation_write_options options=exr_pdf_annotation_write_defaults(); void *bytes=NULL,*other=NULL; size_t size=0,other_size=0;
  options.color=0xff0000; options.opacity=.5;
  OK(exr_pdf_annotation_write(pdf,length,0,&a,&options,&bytes,&size,&error));
  CHECK(size>length && !memcmp(bytes,pdf,length)); roundtrip(bytes,size,&a); first=render(bytes,size);
  CHECK(color_bounds(&first,bounds)>300);
  CHECK(bounds[0]>=8 && bounds[2]<=56);
  if(!strcmp(kind,"StrikeOut")) CHECK(bounds[1]>18 && bounds[3]<22);
  else CHECK(bounds[1]>=8 && bounds[3]<13);
  if(!strcmp(kind,"Squiggly")) CHECK(bounds[3]-bounds[1]>2);
  save(directory,kind,bytes,size);
  /* Both accepted corner orders produce the same appearance and retain their
     original bytes in QuadPoints when read back. */
  a.quads=perimeter;
  OK(exr_pdf_annotation_write(pdf,length,0,&a,&options,&other,&other_size,&error)); roundtrip(other,other_size,&a); second=render(other,other_size);
  CHECK(second.stride==first.stride && !memcmp(first.pixels,second.pixels,first.stride*first.height));
  exr_bitmap_free(&second); exr_free(other); other=NULL;
  a.quads=reverse;
  OK(exr_pdf_annotation_write(pdf,length,0,&a,&options,&other,&other_size,&error)); second=render(other,other_size);
  CHECK(!memcmp(first.pixels,second.pixels,first.stride*first.height));
  exr_bitmap_free(&second); exr_free(other); other=NULL;
  /* A second opposite-winding polygon must neither cancel nor darken alpha. */
  memcpy(duplicate,z,sizeof(z)); memcpy(duplicate+8,reverse,sizeof(reverse)); a.quads=duplicate; a.quad_count=2;
  OK(exr_pdf_annotation_write(pdf,length,0,&a,&options,&other,&other_size,&error)); second=render(other,other_size);
  CHECK(!memcmp(first.pixels,second.pixels,first.stride*first.height));
  exr_bitmap_free(&second); exr_free(other); other=NULL; exr_bitmap_free(&first);
  a.quads=vertical; a.quad_count=1; a.bounds[0]=20; a.bounds[1]=8; a.bounds[2]=44; a.bounds[3]=56;
  OK(exr_pdf_annotation_write(pdf,length,0,&a,&options,&other,&other_size,&error)); second=render(other,other_size);
  CHECK(color_bounds(&second,bounds)>300 && bounds[1]>=8 && bounds[3]<=56);
  if(!strcmp(kind,"StrikeOut")) CHECK(bounds[0]>30 && bounds[2]<34);
  else CHECK(bounds[0]>39 && bounds[2]<=44);
  exr_bitmap_free(&second); exr_free(other); other=NULL;
  /* Upsert to another markup subtype, then removal, survives a revision chain. */
  a=annotation(!strcmp(kind,"Underline") ? "StrikeOut" : "Underline",perimeter);
  OK(exr_pdf_annotation_write(bytes,size,0,&a,&options,&other,&other_size,&error)); roundtrip(other,other_size,&a); exr_free(bytes); bytes=NULL;
  OK(exr_pdf_annotation_remove(other,other_size,0,a.id,NULL,&bytes,&size,&error)); second=render(bytes,size);
  CHECK(!color_bounds(&second,bounds)); exr_bitmap_free(&second); exr_free(bytes); exr_free(other);
}
static int cancelled(void *context) { return *(unsigned *)context>=2; }
static void progress(void *context,exr_stage stage,uint64_t done,uint64_t total) { (void)stage; (void)done; (void)total; (*(unsigned *)context)++; }
static void invalid(void) {
  static const double diagonal[]={8,32,56,8,56,32,8,8};
  static const double valid[]={8,32,56,32,8,8,56,8};
  static const char *const kinds[]={"Underline","StrikeOut","Squiggly"};
  exr_pdf_annotation_write_options options=exr_pdf_annotation_write_defaults(); exr_page_annotation a;
  void *out; size_t size; unsigned i,stops=0;
  for(i=0;i<3;i++) {
    a=annotation(kinds[i],diagonal); out=(void *)(uintptr_t)1; size=123;
    CHECK(exr_pdf_annotation_write(pdf,length,0,&a,NULL,&out,&size,&error)==EXR_ARGUMENT && !out && !size);
    a.quads=NULL; a.quad_count=0; out=(void *)(uintptr_t)1; size=123;
    CHECK(exr_pdf_annotation_write(pdf,length,0,&a,NULL,&out,&size,&error)==EXR_ARGUMENT && !out && !size);
  }
  a=annotation("Squiggly",valid); options.control=(exr_control){cancelled,progress,&stops}; out=(void *)(uintptr_t)1; size=123;
  CHECK(exr_pdf_annotation_write(pdf,length,0,&a,&options,&out,&size,&error)==EXR_CANCELLED && !out && !size);
  { static const double tiny[]={8,8.00000001,56,8.00000001,8,8,56,8};
    a.quads=tiny; out=(void *)(uintptr_t)1; size=123;
    CHECK(exr_pdf_annotation_write(pdf,length,0,&a,NULL,&out,&size,&error)==EXR_LIMIT && !out && !size);
  }
}
int main(int argc,char **argv) {
  const char *directory=argc==2 ? argv[1] : NULL; CHECK(argc<=2); source();
  markup("Underline",directory); markup("StrikeOut",directory); markup("Squiggly",directory); invalid();
  printf("PDF line markup passed (%u checks)\n",checks); return 0;
}
