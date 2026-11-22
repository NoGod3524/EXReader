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
static void rejected_probe(const char *fixtures) {
  mz_zip_archive zip;void *data=NULL;size_t size=0,i;
  memset(&zip,0,sizeof(zip));CHECK(mz_zip_writer_init_heap(&zip,0,0));
  put_file(&zip,"page.png",fixtures,"images/png/huge.png");
  CHECK(mz_zip_writer_finalize_heap_archive(&zip,&data,&size));CHECK(mz_zip_writer_end(&zip));
  for(i=0;i<3;i++) {
    exr_fixed_document *doc=(void *)1;
    CHECK(exr_fixed_open_memory(EXR_CBZ,data,size,NULL,&doc,&error)==EXR_LIMIT);
    CHECK(!doc);
  }
  mz_free(data);
}
static void natural_frame_order(const char *fixtures) {
  mz_zip_archive zip;void *data=NULL;size_t size=0,count,i;exr_fixed_document *doc=NULL;const exr_fixed_page *pages;
  const char *names[]={"page01.gif","page01.gif#1","page01.gif#2","page01.gif#3",
                       "page1.gif","page1.gif#1","page1.gif#2","page1.gif#3"};
  memset(&zip,0,sizeof(zip));CHECK(mz_zip_writer_init_heap(&zip,0,0));
  put_file(&zip,"page1.gif",fixtures,"images/gif/animation.gif");
  put_file(&zip,"page01.gif",fixtures,"images/gif/animation.gif");
  CHECK(mz_zip_writer_finalize_heap_archive(&zip,&data,&size));CHECK(mz_zip_writer_end(&zip));
  OK(exr_fixed_open_memory(EXR_CBZ,data,size,NULL,&doc,&error));
  pages=exr_fixed_pages(doc,&count);CHECK(count==8);
  for(i=0;i<count;i++) CHECK(!strcmp(pages[i].id,names[i]));
  exr_fixed_free(doc);mz_free(data);
}
typedef struct { unsigned char *p;size_t n,cap; } bytes_out;
static void out(bytes_out *b,const void *d,size_t n) {
  if(b->n+n>b->cap) { b->cap=(b->n+n)*2;b->p=realloc(b->p,b->cap);CHECK(b->p); }
  memcpy(b->p+b->n,d,n);b->n+=n;
}
static void out16(bytes_out *b,unsigned v) { unsigned char c[2]={(unsigned char)v,(unsigned char)(v>>8)};out(b,c,2); }
static void out32(bytes_out *b,uint32_t v) { out16(b,v&65535);out16(b,v>>16); }
static void out32be(bytes_out *b,uint32_t v) { unsigned char c[4]={(unsigned char)(v>>24),(unsigned char)(v>>16),(unsigned char)(v>>8),(unsigned char)v};out(b,c,4); }
/* One stored member listed by several central-directory entries: every alias
   would re-read the same bytes while the page list is built. */
static void aliased_members(const char *fixtures) {
  char path[4096];size_t size,i,cd;void *gif;bytes_out z={0};exr_fixed_document *doc=(void *)1;
  snprintf(path,sizeof(path),"%s/images/gif/expansion.gif",fixtures);gif=read_file(path,&size);
  out32(&z,0x04034b50);out16(&z,20);out16(&z,0);out16(&z,0);out16(&z,0);out16(&z,0);
  out32(&z,(uint32_t)mz_crc32(0,gif,size));out32(&z,(uint32_t)size);out32(&z,(uint32_t)size);out16(&z,5);out16(&z,0);out(&z,"a.gif",5);
  out(&z,gif,size);cd=z.n;
  for(i=0;i<2;i++) {
    char name[16];snprintf(name,sizeof(name),"p%zu.gif",i);
    out32(&z,0x02014b50);out16(&z,20);out16(&z,20);out16(&z,0);out16(&z,0);out16(&z,0);out16(&z,0);
    out32(&z,(uint32_t)mz_crc32(0,gif,size));out32(&z,(uint32_t)size);out32(&z,(uint32_t)size);
    out16(&z,6);out16(&z,0);out16(&z,0);out16(&z,0);out16(&z,0);out32(&z,0);out32(&z,0);out(&z,name,6);
  }
  { size_t end=z.n;out32(&z,0x06054b50);out16(&z,0);out16(&z,0);out16(&z,2);out16(&z,2);out32(&z,(uint32_t)(end-cd));out32(&z,(uint32_t)cd);out16(&z,0); }
  CHECK(exr_fixed_open_memory(EXR_CBZ,z.p,z.n,NULL,&doc,&error)==EXR_LIMIT && !doc);
  free(z.p);free(gif);
}
/* Many ordinary stored pages still open: their header reads never exceed the archive. */
static void stored_pages(const char *fixtures) {
  mz_zip_archive zip;void *data=NULL;size_t size=0,count,i;exr_fixed_document *doc=NULL;
  memset(&zip,0,sizeof(zip));CHECK(mz_zip_writer_init_heap(&zip,0,0));
  for(i=0;i<120;i++) { char name[32];snprintf(name,sizeof(name),"%03zu.gif",i);put_file(&zip,name,fixtures,"images/gif/expansion.gif"); }
  CHECK(mz_zip_writer_finalize_heap_archive(&zip,&data,&size));CHECK(mz_zip_writer_end(&zip));
  OK(exr_fixed_open_memory(EXR_CBZ,data,size,NULL,&doc,&error));exr_fixed_pages(doc,&count);CHECK(count==480);
  exr_fixed_free(doc);mz_free(data);
}
/* 4096 TIFF directories of different widths: one ordered pass sizes every page. */
static void tiff_directories(void) {
  bytes_out t={0};mz_zip_archive zip;void *data=NULL;size_t size=0,count,i,link;exr_fixed_document *doc=NULL;const exr_fixed_page *pages;exr_status status;
  out(&t,"II*\0",4);link=t.n;out32(&t,0);
  for(i=0;i<4096;i++) {
    unsigned width=1+(unsigned)(i%5),k;size_t pixels=t.n;
    for(k=0;k<width;k++) { unsigned char gray=128;out(&t,&gray,1); }
    if(t.n&1) out(&t,"",1);
    t.p[link]=(unsigned char)t.n;t.p[link+1]=(unsigned char)(t.n>>8);t.p[link+2]=(unsigned char)(t.n>>16);t.p[link+3]=(unsigned char)(t.n>>24);
    out16(&t,8);
    out16(&t,256);out16(&t,3);out32(&t,1);out32(&t,width);
    out16(&t,257);out16(&t,3);out32(&t,1);out32(&t,1);
    out16(&t,258);out16(&t,3);out32(&t,1);out32(&t,8);
    out16(&t,259);out16(&t,3);out32(&t,1);out32(&t,1);
    out16(&t,262);out16(&t,3);out32(&t,1);out32(&t,1);
    out16(&t,273);out16(&t,4);out32(&t,1);out32(&t,(uint32_t)pixels);
    out16(&t,278);out16(&t,3);out32(&t,1);out32(&t,1);
    out16(&t,279);out16(&t,4);out32(&t,1);out32(&t,width);
    link=t.n;out32(&t,0);
  }
  memset(&zip,0,sizeof(zip));CHECK(mz_zip_writer_init_heap(&zip,0,0));
  CHECK(mz_zip_writer_add_mem(&zip,"pages.tif",t.p,t.n,MZ_NO_COMPRESSION));
  CHECK(mz_zip_writer_finalize_heap_archive(&zip,&data,&size));CHECK(mz_zip_writer_end(&zip));
  status=exr_fixed_open_memory(EXR_CBZ,data,size,NULL,&doc,&error);
  if(status!=EXR_UNSUPPORTED) {
    CHECK(status==EXR_OK);pages=exr_fixed_pages(doc,&count);CHECK(count==4096);
    for(i=0;i<count;i++) {
      /* "pages.tif" is directory 0 and "pages.tif#n" is directory n. */
      const char *mark=strchr(pages[i].id,'#');size_t frame=mark ? (size_t)strtoul(mark+1,NULL,10) : 0;
      CHECK(frame<4096 && pages[i].geometry.bounds[2]==1+frame%5 && pages[i].geometry.bounds[3]==1);
    }
    exr_fixed_free(doc);
  }
  mz_free(data);free(t.p);
}
/* An 8192x2048 RGBA PNG passes the dimension limits but exhausts the 128 MiB
   stb working budget; every decode entry reports that as EXR_LIMIT. */
static void stb_budget(void) {
  size_t row=8192*4+1,raw_size=row*2048;unsigned char *raw=calloc(1,raw_size),*packed;mz_ulong packed_size;
  bytes_out png={0};exr_bitmap image={0};uint32_t w=0,h=0;
  static const unsigned char header[]={137,80,78,71,13,10,26,10};
  unsigned char ihdr[17]={'I','H','D','R',0,0,32,0,0,0,8,0,8,6,0,0,0};
  CHECK(raw);packed_size=mz_compressBound((mz_ulong)raw_size);packed=malloc(packed_size);CHECK(packed);
  CHECK(mz_compress2(packed,&packed_size,raw,(mz_ulong)raw_size,1)==MZ_OK);
  out(&png,header,8);
  out32be(&png,13);out(&png,ihdr,17);out32be(&png,(uint32_t)mz_crc32(0,ihdr,17));
  out32be(&png,(uint32_t)packed_size);
  { mz_ulong crc=mz_crc32(0,(const unsigned char *)"IDAT",4);out(&png,"IDAT",4);out(&png,packed,packed_size);out32be(&png,(uint32_t)mz_crc32(crc,packed,packed_size)); }
  out32be(&png,0);out(&png,"IEND",4);out32be(&png,(uint32_t)mz_crc32(0,(const unsigned char *)"IEND",4));
  OK(exr_image_page_dimensions(png.p,png.n,0,&w,&h,&error));CHECK(w==8192 && h==2048);
  CHECK(exr_image_decode(png.p,png.n,&image,&error)==EXR_LIMIT && !image.pixels);
  CHECK(exr_image_decode_page(png.p,png.n,0,&image,&error)==EXR_LIMIT && !image.pixels);
  CHECK(exr_image_decode_page(png.p,png.n,0,&image,&error)==EXR_LIMIT && !image.pixels);
  free(raw);free(packed);free(png.p);
}
int main(int argc,char **argv) {
  mz_zip_archive zip;void *archive=NULL;size_t size=0,count,i;exr_fixed_document *d=NULL;const exr_fixed_page *pages;
  const char *info="<ComicInfo><Title>Formats</Title><Writer>WP12a</Writer></ComicInfo>";
  CHECK(argc==2 || argc==3);
  if(argc==3 && !strcmp(argv[2],"order")) {
    natural_frame_order(argv[1]);printf("%u CBZ order checks passed\n",checks);return 0;
  }
  rejected_probe(argv[1]);
  natural_frame_order(argv[1]);
  aliased_members(argv[1]);
  stored_pages(argv[1]);
  tiff_directories();
  stb_budget();
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
