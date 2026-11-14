/* SPDX-License-Identifier: MIT */
#include "ppt_internal.h"

static exr_status audit_path(void *context,const exr_path_segment *segments,size_t count,
  const double matrix[6],const exr_draw_style *style,exr_error *error) {
  size_t *index=context;
  (void)segments;(void)count;(void)matrix;(void)error;
  printf("draw_%zu_flags=%u\ndraw_%zu_fill=%08x\ndraw_%zu_stroke=%08x\ndraw_%zu_width=%.8g\n",
    *index,style->flags,*index,(unsigned)style->fill,*index,(unsigned)style->stroke,*index,style->line.width);
  ++*index;return EXR_OK;
}

/* Write a dependency-free RGB artifact so the Python checks inspect the actual
   canvas, including color conversion, z-order, strokes and viewport scaling. */
int main(int argc,char **argv) {
  exr_fixed_document *doc=NULL;exr_fixed_open_options options={0};
  exr_error error={0},paint_error={0};exr_status status;exr_bitmap bitmap={0};
  const exr_fixed_page *pages=NULL;size_t count=0,x,y,paths=0;double scale=1;
  unsigned char *bytes=NULL;FILE *file=NULL;long length;int failed=0;
  if(argc!=5 && argc!=6) return 2;
  scale=strtod(argv[4],NULL);options.struct_size=sizeof(options);
  if(argc==6 && !strcmp(argv[5],"memory")) {
    file=fopen(argv[1],"rb");if(!file) return 2;
    if(fseek(file,0,SEEK_END) || (length=ftell(file))<0 || fseek(file,0,SEEK_SET)) { fclose(file);return 2; }
    bytes=malloc(length ? (size_t)length : 1);
    if(!bytes || fread(bytes,1,(size_t)length,file)!=(size_t)length) { fclose(file);free(bytes);return 2; }
    fclose(file);file=NULL;
    status=exr_fixed_open_memory(EXR_PPT,bytes,(size_t)length,&options,&doc,&error);
  } else status=exr_fixed_open(argv[1],&options,&doc,&error);
  if(status==EXR_OK) {
    size_t page=(size_t)strtoul(argv[3],NULL,10);
    pages=exr_fixed_pages(doc,&count);
    if(page<count) {
      exr_draw_sink sink={0};exr_status paint;
      sink.path=audit_path;sink.context=&paths;
      paint=exr_fixed_draw(doc,page,NULL,&sink,NULL,&paint_error);
      if(paint==EXR_OK) paint=exr_fixed_render(doc,page,scale,NULL,&bitmap,&paint_error);
      if(paint!=EXR_OK) { status=paint;error=paint_error; }
      else {
        file=fopen(argv[2],"wb");
        if(!file || fprintf(file,"P6\n%u %u\n255\n",bitmap.width,bitmap.height)<0) failed=1;
        if(file) {
          for(y=0;y<bitmap.height && !failed;y++) for(x=0;x<bitmap.width;x++) {
            const unsigned char *p=bitmap.pixels+y*bitmap.stride+x*bitmap.channels;
            if(bitmap.channels!=4 || fwrite(p,1,3,file)!=3) { failed=1;break; }
          }
          if(fclose(file)) failed=1;
        }
      }
    }
  }
  printf("status=%d\nmessage=%s\npages=%zu\nwidth=%.8g\nheight=%.8g\nbitmap_width=%u\nbitmap_height=%u\ndraw_count=%zu\n",
    status,error.message,count,count ? pages[0].geometry.bounds[2] : 0,
    count ? pages[0].geometry.bounds[3] : 0,bitmap.width,bitmap.height,paths);
  exr_bitmap_free(&bitmap);exr_fixed_free(doc);free(bytes);return failed ? 2 : 0;
}
