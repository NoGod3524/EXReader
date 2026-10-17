/* SPDX-License-Identifier: GPL-3.0-only */
#include "../src/pdf_internal.h"
static exr_error error; static unsigned checks;
#define CHECK(x) do { checks++; if(!(x)) { fprintf(stderr,"line %d: %s (%d: %s)\n",__LINE__,#x,error.code,error.message); exit(1); } } while(0)
#define OK(x) CHECK((x)==EXR_OK)
static unsigned char *read_fixture(const char *dir,const char *name,size_t *size) {
  char path[4096]; FILE *file; long length; unsigned char *data;
  snprintf(path,sizeof(path),"%s/%s",dir,name); file=fopen(path,"rb"); CHECK(file);
  CHECK(!fseek(file,0,SEEK_END)); length=ftell(file); CHECK(length>0); rewind(file);
  *size=(size_t)length; data=malloc(*size); CHECK(data && fread(data,1,*size,file)==*size); fclose(file); return data;
}
static void tree(const char *dir) {
  unsigned char *data; size_t size,count; exr_pdf_file *file=NULL; exr_pdf_page_info *pages=NULL; exr_buffer content={0};
  data=read_fixture(dir,"pdf-pages.pdf",&size); OK(exr_pdf_open(data,size,&file,&error));
  OK(exr_pdf_pages(file,&pages,&count,&error)); CHECK(count==3 && pages);
  CHECK(pages[0].media[0]==-10 && pages[0].media[1]==-20 && pages[0].media[2]==200 && pages[0].media[3]==300);
  CHECK(!memcmp(pages[0].media,pages[0].crop,sizeof(pages[0].media)) && pages[0].rotation==270 && pages[0].user_unit==1);
  CHECK(exr_pdf_get(file,pages[0].resources,"Inherited")!=EXR_PDF_NONE && pages[0].annotations!=EXR_PDF_NONE);
  CHECK(pages[1].media[0]==0 && pages[1].media[1]==0 && pages[1].media[2]==400 && pages[1].media[3]==500);
  CHECK(pages[1].crop[0]==10 && pages[1].crop[1]==20 && pages[1].crop[2]==300 && pages[1].crop[3]==450);
  CHECK(pages[1].rotation==90 && pages[1].user_unit==2.5 && pages[1].resources!=pages[0].resources);
  CHECK(exr_pdf_get(file,pages[1].resources,"Local")!=EXR_PDF_NONE && pages[1].annotations==EXR_PDF_NONE);
  CHECK(pages[2].rotation==0 && pages[2].user_unit==1 && pages[2].resources==pages[1].resources);
  CHECK(pages[2].media[2]==100 && pages[2].media[3]==150 && !memcmp(pages[2].crop,pages[1].crop,sizeof(pages[2].crop)));
  OK(exr_pdf_content(file,pages[0].contents,&content,&error));
  CHECK(content.size==10 && !memcmp(content.data,"(hello) Tj",10) && content.data[content.size]==0); free(content.data);
  OK(exr_pdf_content(file,pages[1].contents,&content,&error)); CHECK(content.size==4 && !memcmp(content.data,"(hel",4)); free(content.data);
  OK(exr_pdf_content(file,pages[2].contents,&content,&error)); CHECK(!content.size && content.data && !content.data[0]); free(content.data);
  exr_pdf_close(file); free(data); CHECK(pages[1].user_unit==2.5); free(pages);
}
static void simple(const char *dir,const char *name,size_t expected) {
  unsigned char *data; size_t size,count; exr_pdf_file *file=NULL; exr_pdf_page_info *pages=NULL;
  data=read_fixture(dir,name,&size); OK(exr_pdf_open(data,size,&file,&error));
  OK(exr_pdf_pages(file,&pages,&count,&error)); CHECK(count==expected);
  if(count) CHECK(pages[0].media[2]==200 && pages[0].media[3]==300 && pages[0].resources==EXR_PDF_NONE);
  free(pages); exr_pdf_close(file); free(data);
}
static void bad(const char *dir,const char *name,exr_status expected,int content_error) {
  char path[256]; unsigned char *data; size_t size,count=99; exr_pdf_file *file=NULL; exr_pdf_page_info *pages=(exr_pdf_page_info *)(uintptr_t)1;
  snprintf(path,sizeof(path),"pdf-pages-bad-%s.pdf",name); data=read_fixture(dir,path,&size);
  OK(exr_pdf_open(data,size,&file,&error));
  if(content_error) {
    exr_buffer content={0}; OK(exr_pdf_pages(file,&pages,&count,&error)); CHECK(count==3);
    CHECK(exr_pdf_content(file,pages[0].contents,&content,&error)==expected && !content.data && !content.size && !content.capacity); free(pages);
  } else {
    exr_status status=exr_pdf_pages(file,&pages,&count,&error);
    if(status!=expected) fprintf(stderr,"fixture %s returned %d\n",name,status);
    CHECK(status==expected && !pages && !count && error.code==expected && error.message[0]);
  }
  exr_pdf_close(file); free(data);
}
int main(int argc,char **argv) {
  const char *invalid[]={"count","cycle","repeated","parent","root-parent","root-type","missing-media","media-size","media-arity","media-number","media-range","rotate","rotate-real","resources","kids","unit","unit-limit"}; size_t i;
  CHECK(argc==2); tree(argv[1]); simple(argv[1],"pdf-pages-empty.pdf",0);
  simple(argv[1],"pdf-objects.pdf",1); simple(argv[1],"pdf-object-stream.pdf",1); simple(argv[1],"pdf-hybrid-predictor.pdf",1);
  for(i=0;i<sizeof(invalid)/sizeof(*invalid);i++) bad(argv[1],invalid[i],EXR_FORMAT,0);
  bad(argv[1],"depth",EXR_LIMIT,0); bad(argv[1],"content-type",EXR_FORMAT,1); bad(argv[1],"content-stream",EXR_FORMAT,1);
  { exr_pdf_page_info *pages=(exr_pdf_page_info *)(uintptr_t)1; size_t count=1; exr_buffer content={0};
    CHECK(exr_pdf_pages(NULL,&pages,&count,&error)==EXR_ARGUMENT && !pages && !count);
    CHECK(exr_pdf_content(NULL,EXR_PDF_NONE,&content,&error)==EXR_ARGUMENT && !content.data);
  }
  printf("%u native PDF page tree checks passed\n",checks); return 0;
}
