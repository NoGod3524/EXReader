/* SPDX-License-Identifier: MIT */
#include "ppt_internal.h"

static int cancel(void *context) { (void)context;return 1; }
int main(int argc,char **argv) {
  unsigned char *bytes=NULL;FILE *file;long length;exr_error error={0};exr_status status;
  exr_fixed_document *doc=NULL;exr_fixed_open_options options={0};
  exr_ppt_streams streams={0};exr_ppt_info info={0};size_t count=0,i;double width=0,height=0;
  const exr_fixed_page *pages;int white=1;
  if(argc!=3) return 2;
  file=fopen(argv[2],"rb");if(!file) return 2;
  if(fseek(file,0,SEEK_END) || (length=ftell(file))<0 || fseek(file,0,SEEK_SET)) { fclose(file);return 2; }
  bytes=malloc(length ? (size_t)length : 1);
  if(!bytes || fread(bytes,1,(size_t)length,file)!=(size_t)length) { fclose(file);free(bytes);return 2; }
  fclose(file);options.struct_size=sizeof(options);
  if(!strcmp(argv[1],"cfb")) {
    status=exr_ppt_cfb(bytes,(size_t)length,NULL,&streams,&error);
    count=streams.document_size;exr_ppt_streams_free(&streams);
  } else if(!strcmp(argv[1],"records")) {
    status=exr_ppt_records(bytes,(size_t)length,NULL,&info,&error);
    count=info.pages;width=info.width;height=info.height;
    if(status==EXR_OK && info.mismatch) snprintf(error.message,sizeof(error.message),"warning: count mismatch");
  } else {
    if(!strcmp(argv[1],"memory")) status=exr_fixed_open_memory(EXR_PPT,bytes,(size_t)length,&options,&doc,&error);
    else {
      if(!strcmp(argv[1],"cancel")) options.control.cancelled=cancel;
      status=exr_fixed_open(argv[2],&options,&doc,&error);
    }
    if(status==EXR_OK) {
      pages=exr_fixed_pages(doc,&count);
      if(count) { width=pages[0].geometry.bounds[2];height=pages[0].geometry.bounds[3]; }
      for(i=0;i<count;i++) {
        exr_bitmap bitmap={0};size_t x,y;exr_error render_error={0};
        if(exr_fixed_render(doc,i,1,NULL,&bitmap,&render_error)!=EXR_OK) { white=0;break; }
        if(bitmap.width!=(uint32_t)width || bitmap.height!=(uint32_t)height) white=0;
        for(y=0;y<bitmap.height;y++) for(x=0;x<(size_t)bitmap.width*bitmap.channels;x++)
          if(bitmap.pixels[y*bitmap.stride+x]!=255) white=0;
        exr_bitmap_free(&bitmap);
      }
    }
  }
  printf("status=%d\nmessage=%s\npages=%zu\nwidth=%.8g\nheight=%.8g\nwhite=%d\ntitle=%s\n",
    status,error.message,count,width,height,white,doc ? exr_fixed_title(doc) : "");
  exr_fixed_free(doc);free(bytes);return white ? 0 : 1;
}
