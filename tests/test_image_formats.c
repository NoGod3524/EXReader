/* SPDX-License-identifier: MIT */
#include "exreader.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static exr_error error;static unsigned checks;
#define CHECK(x) do { checks++;if(!(x)) { fprintf(stderr,"line %d: %s (%d: %s)\n",__LINE__,#x,error.code,error.message);exit(1); } } while(0)
#define OK(x) CHECK((x)==EXR_OK)
static void *read_file(const char *path,size_t *size) {
  FILE *f=fopen(path,"rb");long n;void *data;
  if(!f) { fprintf(stderr,"cannot open %s\n",path); exit(1); }
  CHECK(!fseek(f,0,SEEK_END));n=ftell(f);CHECK(n>=0);rewind(f);
  *size=(size_t)n;data=malloc(*size ? *size : 1);CHECK(data && fread(data,1,*size,f)==*size && !fclose(f));return data;
}
typedef struct { const char *name; unsigned w,h; int exact; } variant;
static const variant variants[] = {
  {"solid",4,4,1},{"alpha",8,6,1},{"checker",16,16,1},{"odd",17,9,1},{"one",1,1,1},
  {"wide",255,1,1},{"tall",1,255,1},{"gray",32,8,1},{"palette",12,12,0},{"transparent",5,5,1},
  {"gradient",100,100,0}
};
static void read_rgba(const char *root,const char *format,const char *name,exr_bitmap *bitmap) {
  char path[4096];size_t size;void *data;
  snprintf(path,sizeof(path),"%s/%s/%s",root,format,name);
  data=read_file(path,&size);OK(exr_image_decode(data,size,bitmap,&error));free(data);
}
static void close_rgba(const exr_bitmap *bitmap,int r,int g,int b,int a) {
  CHECK(bitmap->pixels && bitmap->channels==4);
  CHECK(abs((int)bitmap->pixels[0]-r)<=16 && abs((int)bitmap->pixels[1]-g)<=16 &&
        abs((int)bitmap->pixels[2]-b)<=16 && abs((int)bitmap->pixels[3]-a)<=16);
}
static void tiff_alpha(const char *root) {
  char path[4096];size_t size,x,y,k;void *data;exr_bitmap tiff={0},png={0};exr_status status;
  snprintf(path,sizeof(path),"%s/tiff/alpha.tif",root);data=read_file(path,&size);
  status=exr_image_decode(data,size,&tiff,&error);free(data);
  if(status==EXR_UNSUPPORTED) return;
  CHECK(status==EXR_OK);read_rgba(root,"png","alpha.png",&png);
  CHECK(tiff.width==png.width && tiff.height==png.height);
  for(y=0;y<png.height;y++) for(x=0;x<png.width;x++) {
    const unsigned char *a=png.pixels+y*png.stride+x*4,*b=tiff.pixels+y*tiff.stride+x*4;
    CHECK(a[3]==b[3]);
    /* libtiff's 8-bit associated-alpha raster has one quantization step.
       Compare premultiplied contributions rather than undefined alpha-zero RGB. */
    for(k=0;k<3;k++) CHECK(abs((int)((a[k]*a[3]+127)/255)-(int)((b[k]*b[3]+127)/255))<=1);
  }
  { unsigned backgrounds[]={0xffffffffu,0x203040ffu};size_t i;
    for(i=0;i<2;i++) {
      exr_canvas_config config={0};exr_canvas *a=NULL,*b=NULL;exr_bitmap pa={0},pb={0};exr_image_layer layer={0};
      double matrix[6]={png.width,0,0,png.height,0,0};
      config.width=png.width;config.height=png.height;config.channels=4;config.background=backgrounds[i];
      OK(exr_canvas_create(&config,&a,&error));OK(exr_canvas_create(&config,&b,&error));
      layer.bitmap=png;OK(exr_canvas_image(a,&layer,matrix,1,&error));
      layer.bitmap=tiff;OK(exr_canvas_image(b,&layer,matrix,1,&error));
      OK(exr_canvas_take(a,&pa,&error));OK(exr_canvas_take(b,&pb,&error));
      for(y=0;y<pa.height;y++) for(x=0;x<pa.width*4;x++) CHECK(abs((int)pa.pixels[y*pa.stride+x]-(int)pb.pixels[y*pb.stride+x])<=1);
      exr_bitmap_free(&pa);exr_bitmap_free(&pb);exr_canvas_free(a);exr_canvas_free(b);
    }
  }
  exr_bitmap_free(&png);exr_bitmap_free(&tiff);
}
static void matrix(const char *root,const char *format,const char *extension,unsigned tolerance) {
  size_t i;
  { char path[4096];size_t size,pages=0;void *data;snprintf(path,sizeof(path),"%s/%s/solid.%s",root,format,extension);
    data=read_file(path,&size);{ exr_status status=exr_image_page_count(data,size,&pages,&error);free(data);
      if(status==EXR_UNSUPPORTED) { printf("skip %s: %s\n",format,error.message);return; }CHECK(status==EXR_OK); } }
  for(i=0;i<sizeof(variants)/sizeof(*variants);i++) {
    const variant *v=&variants[i];char path[4096];size_t size,pages=0;void *data;exr_bitmap bitmap={0};
    if(!strcmp(format,"bmp") && !strcmp(v->name,"transparent")) continue;
    snprintf(path,sizeof(path),"%s/%s/%s.%s",root,format,v->name,extension);
    data=read_file(path,&size);
    OK(exr_image_page_count(data,size,&pages,&error));CHECK(pages==1);
    { uint32_t w=0,h=0;OK(exr_image_page_dimensions(data,size,0,&w,&h,&error));CHECK(w==v->w && h==v->h); }
    OK(exr_image_decode_page(data,size,0,&bitmap,&error));
    CHECK(bitmap.width==v->w && bitmap.height==v->h && bitmap.channels==4 && bitmap.stride==v->w*4);
    if(!strcmp(v->name,"solid")) close_rgba(&bitmap,220,30,40,255);
    if(!strcmp(v->name,"one")) close_rgba(&bitmap,255,0,255,255);
    if(!strcmp(v->name,"transparent") && strcmp(format,"bmp")) CHECK(bitmap.pixels[3]==0);
    if(!strcmp(v->name,"alpha") && strcmp(format,"gif") && strcmp(format,"bmp")) {
      CHECK(bitmap.pixels[3]<=tolerance);
      CHECK(abs((int)bitmap.pixels[(v->w-1)*4+3]-255)<=tolerance);
    }
    if(!strcmp(v->name,"checker")) {
      CHECK(bitmap.pixels[0]<=tolerance || bitmap.pixels[0]>=255-tolerance);
      CHECK(bitmap.pixels[4]<=tolerance || bitmap.pixels[4]>=255-tolerance);
      CHECK(bitmap.pixels[0]!=bitmap.pixels[4]);
    }
    exr_bitmap_free(&bitmap);
    CHECK(exr_image_decode_page(data,size,pages,&bitmap,&error)==EXR_LIMIT);
    CHECK(!bitmap.pixels);
    free(data);
  }
  if(strcmp(format,"png") && strcmp(format,"bmp")) { char path[4096];size_t size,pages=0;void *data;exr_bitmap bitmap={0};
    snprintf(path,sizeof(path),"%s/%s/animation.%s",root,format,extension);
    data=read_file(path,&size);OK(exr_image_page_count(data,size,&pages,&error));
    if(strcmp(format,"bmp")) CHECK(pages==4);
    else CHECK(pages==1);
    if(pages==4) {
      size_t page;unsigned char *first=NULL;
      for(page=0;page<pages;page++) {
        uint32_t w=0,h=0;exr_bitmap frame={0};
        OK(exr_image_page_dimensions(data,size,page,&w,&h,&error));CHECK(w==8 && h==8);
        OK(exr_image_decode_page(data,size,page,&frame,&error));CHECK(frame.width==8 && frame.height==8);
        if(page==0) first=malloc(frame.stride*frame.height);
        if(page==0) memcpy(first,frame.pixels,frame.stride*frame.height);
        exr_bitmap_free(&frame);
      }
      { exr_bitmap last={0};size_t bytes;OK(exr_image_decode_page(data,size,pages-1,&last,&error));bytes=last.stride*last.height;
        CHECK(memcmp(first,last.pixels,bytes)!=0);exr_bitmap_free(&last); }
      free(first);
    }
    free(data);
  }
  { char path[4096];size_t size,pages=0;void *data;exr_bitmap bitmap={0};uint32_t w=0,h=0;
    snprintf(path,sizeof(path),"%s/%s/truncated.%s",root,format,extension);
    data=read_file(path,&size);{ exr_status s=exr_image_page_count(data,size,&pages,&error);
      if(s==EXR_OK) { exr_bitmap broken={0};s=exr_image_decode_page(data,size,0,&broken,&error);
        if(!strcmp(format,"bmp")) { exr_bitmap_free(&broken); }
        else CHECK(s!=EXR_OK && !broken.pixels); }
      else CHECK(s==EXR_FORMAT || s==EXR_LIMIT); }free(data);
    snprintf(path,sizeof(path),"%s/%s/badmagic.%s",root,format,extension);
    data=read_file(path,&size);{ exr_status s=exr_image_page_count(data,size,&pages,&error);
      if(s!=EXR_FORMAT) fprintf(stderr,"badmagic %s status=%d %s\n",format,(int)s,error.message);CHECK(s==EXR_FORMAT); }free(data);
    (void)w;(void)h;(void)bitmap;
  }
}
int main(int argc,char **argv) {
  size_t size;void *data;exr_bitmap bitmap={0};size_t pages=0;
  CHECK(argc==2 || argc==3);
  tiff_alpha(argv[1]);
  if(argc==2 || !strcmp(argv[2],"png")) matrix(argv[1],"png","png",0);
  if(argc==2 || !strcmp(argv[2],"bmp")) matrix(argv[1],"bmp","bmp",0);
  if(argc==2 || !strcmp(argv[2],"gif")) matrix(argv[1],"gif","gif",16);
  if(argc==2 || !strcmp(argv[2],"webp")) matrix(argv[1],"webp","webp",0);
  if(argc==2 || !strcmp(argv[2],"tiff")) matrix(argv[1],"tiff","tif",0);
  if(argc==2 || !strcmp(argv[2],"avif")) matrix(argv[1],"avif","avif",16);
  { char path[4096];uint32_t w=0,h=0;snprintf(path,sizeof(path),"%s/png/huge.png",argv[1]);data=read_file(path,&size);
    CHECK(exr_image_page_count(data,size,&pages,&error)==EXR_LIMIT);free(data);(void)w;(void)h; }
  { char path[4096];void *large=calloc(1,33*1024*1024);snprintf(path,sizeof(path),"%s/gif/expansion.gif",argv[1]);data=read_file(path,&size);
    CHECK(exr_image_page_count(data,size,&pages,&error)==EXR_OK && pages==4);
    { exr_bitmap capped={0};CHECK(exr_image_decode_page(data,size,0,&capped,&error)==EXR_LIMIT && !capped.pixels); }
    free(data);CHECK(large);CHECK(exr_image_decode(large,33*1024*1024,&bitmap,&error)==EXR_LIMIT && !bitmap.pixels);free(large); }
  { char path[4096];exr_status status;snprintf(path,sizeof(path),"%s/tiff/animation.tif",argv[1]);data=read_file(path,&size);
    status=exr_image_page_count(data,size,&pages,&error);
    if(status==EXR_OK) { CHECK(pages==4);OK(exr_image_page_dimensions(data,size,3,&bitmap.width,&bitmap.height,&error));
      CHECK(bitmap.width==8 && bitmap.height==8); }
    else CHECK(status==EXR_UNSUPPORTED);
    free(data);(void)bitmap; }
  { char path[4096];exr_bitmap alpha={0};snprintf(path,sizeof(path),"%s/bmp/alpha32.bmp",argv[1]);data=read_file(path,&size);
    OK(exr_image_decode(data,size,&alpha,&error));CHECK(alpha.width==5 && alpha.height==5 && alpha.pixels[3]==0 && alpha.pixels[4*4+3]==255);
    exr_bitmap_free(&alpha);free(data); }
  printf("%u image-format checks passed\n",checks);return 0;
}
