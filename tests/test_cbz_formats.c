/* SPDX-License-Identifier: MIT */
#include "exreader.h"
#include <miniz.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static exr_error error;static unsigned checks;
#define CHECK(x) do { checks++;if(!(x)) { fprintf(stderr,"line %d: %s (%d: %s)\n",__LINE__,#x,error.code,error.message);exit(1); } } while(0)
#define OK(x) CHECK((x)==EXR_OK)
static void *read_file(const char *path,size_t *size) {
  FILE *f=fopen(path,"rb");long n;void *data;CHECK(f && !fseek(f,0,SEEK_END));n=ftell(f);CHECK(n>=0);rewind(f);
  *size=(size_t)n;data=malloc(*size ? *size : 1);CHECK(data && fread(data,1,*size,f)==*size && !fclose(f));return data;
}
static void put_file(mz_zip_archive *zip,const char *name,const char *root,const char *relative) {
  char path[4096];size_t size;void *data;snprintf(path,sizeof(path),"%s/%s",root,relative);data=read_file(path,&size);
  CHECK(mz_zip_writer_add_mem(zip,name,data,size,MZ_NO_COMPRESSION));free(data);
}
static void expect_page(exr_fixed_document *d,size_t page,const char *id,unsigned w,unsigned h) {
  const exr_fixed_page *pages;size_t count;exr_bitmap bitmap={0};unsigned x,y,k;
  pages=exr_fixed_pages(d,&count);CHECK(page<count);CHECK(!strcmp(pages[page].id,id));
  CHECK(pages[page].geometry.bounds[2]==w && pages[page].geometry.bounds[3]==h);
  OK(exr_fixed_render(d,page,1,NULL,&bitmap,&error));CHECK(bitmap.width==w && bitmap.height==h && bitmap.channels==4);
  for(y=0;y<bitmap.height;y++) for(x=0;x<bitmap.width;x++) for(k=0;k<4;k++) CHECK(bitmap.pixels[(size_t)y*bitmap.stride+x*4+k]<=255);
  exr_bitmap_free(&bitmap);
}
int main(int argc,char **argv) {
  mz_zip_archive zip;void *archive=NULL;size_t size=0,count,i;exr_fixed_document *d=NULL;const exr_fixed_page *pages;
  const char *info="<ComicInfo><Title>Formats</Title><Writer>WP12a</Writer></ComicInfo>";
  CHECK(argc==2);
  memset(&zip,0,sizeof(zip));CHECK(mz_zip_writer_init_heap(&zip,0,0));
  put_file(&zip,"Chapter/1.png",argv[1],"images/png/solid.png");
  put_file(&zip,"Chapter/2.gif",argv[1],"images/gif/animation.gif");
  put_file(&zip,"Chapter/3.webp",argv[1],"images/webp/solid.webp");
  put_file(&zip,"Chapter/4.bmp",argv[1],"images/bmp/solid.bmp");
  put_file(&zip,"Chapter/5.tif",argv[1],"images/tiff/animation.tif");
  put_file(&zip,"Chapter/6.avif",argv[1],"images/avif/solid.avif");
  put_file(&zip,"Chapter/10.png",argv[1],"images/png/checker.png");
  put_file(&zip,"cover.JPEG",argv[1],"pdf-images/baseline.jpg");
  CHECK(mz_zip_writer_add_mem(&zip,"ComicInfo.xml",info,strlen(info),MZ_NO_COMPRESSION));
  CHECK(mz_zip_writer_finalize_heap_archive(&zip,&archive,&size));CHECK(mz_zip_writer_end(&zip));
  { exr_status opened=exr_fixed_open_memory(EXR_CBZ,archive,size,NULL,&d,&error);
    if(opened==EXR_UNSUPPORTED) { printf("skip CBZ format matrix: %s\n",error.message);mz_free(archive);return 0; }
    CHECK(opened==EXR_OK); }
  CHECK(!strcmp(exr_fixed_title(d),"Formats"));
  pages=exr_fixed_pages(d,&count);
  CHECK(count==14);
  expect_page(d,0,"Chapter/1.png",4,4);
  expect_page(d,1,"Chapter/2.gif",8,8);
  expect_page(d,2,"Chapter/2.gif#1",8,8);
  expect_page(d,3,"Chapter/2.gif#2",8,8);
  expect_page(d,4,"Chapter/2.gif#3",8,8);
  expect_page(d,5,"Chapter/3.webp",4,4);
  expect_page(d,6,"Chapter/4.bmp",4,4);
  expect_page(d,7,"Chapter/5.tif",8,8);
  expect_page(d,8,"Chapter/5.tif#1",8,8);
  expect_page(d,9,"Chapter/5.tif#2",8,8);
  expect_page(d,10,"Chapter/5.tif#3",8,8);
  expect_page(d,11,"Chapter/6.avif",4,4);
  expect_page(d,12,"Chapter/10.png",16,16);
  expect_page(d,13,"cover.JPEG",(unsigned)pages[13].geometry.bounds[2],(unsigned)pages[13].geometry.bounds[3]);
  { exr_bitmap a={0},b={0};OK(exr_fixed_render(d,1,1,NULL,&a,&error));OK(exr_fixed_render(d,2,1,NULL,&b,&error));
    CHECK(a.width==b.width && a.height==b.height);CHECK(memcmp(a.pixels,b.pixels,(size_t)a.stride*a.height)!=0);
    exr_bitmap_free(&a);exr_bitmap_free(&b); }
  { exr_bitmap missing={0};CHECK(exr_fixed_render(d,count,1,NULL,&missing,&error)==EXR_ARGUMENT && !missing.pixels); }
  exr_fixed_free(d);d=NULL;
  /* A supported extension with damaged content is an error, not a dropped page. */
  { mz_zip_archive bad;void *bytes=NULL;size_t n=0;exr_fixed_document *x=(void *)1;
    memset(&bad,0,sizeof(bad));CHECK(mz_zip_writer_init_heap(&bad,0,0));
    CHECK(mz_zip_writer_add_mem(&bad,"page.avif","bad",3,MZ_NO_COMPRESSION));
    CHECK(mz_zip_writer_finalize_heap_archive(&bad,&bytes,&n));CHECK(mz_zip_writer_end(&bad));
    CHECK(exr_fixed_open_memory(EXR_CBZ,bytes,n,NULL,&x,&error)==EXR_FORMAT && !x);mz_free(bytes); }
  mz_free(archive);printf("%u CBZ format checks passed\n",checks);return 0;
}
