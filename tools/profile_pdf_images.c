/* SPDX-License-Identifier: MIT */
#if !defined(_WIN32) && !defined(_POSIX_C_SOURCE)
#define _POSIX_C_SOURCE 200809L
#endif
/* Same canvas/viewport/page painter as fixed_render, with internal counters.
   Usage: exreader-pdf-image-profile file.pdf width rounds */
#include "../src/pdf_raster_internal.h"
#include "../src/canvas_internal.h"
#include <time.h>
#ifdef _WIN32
#include <windows.h>
#endif

static double now_ms(void) {
#ifdef _WIN32
  LARGE_INTEGER t,frequency;QueryPerformanceCounter(&t);QueryPerformanceFrequency(&frequency);
  return (double)t.QuadPart*1000/(double)frequency.QuadPart;
#else
  struct timespec t;clock_gettime(CLOCK_MONOTONIC,&t);return (double)t.tv_sec*1000+t.tv_nsec/1e6;
#endif
}
/* This command renders serially; leave the canvas context unchanged so every
   other sink callback still reaches the original canvas. */
static exr_draw_image_fn original_image;
static double paint_image_ms;
static size_t paint_image_calls;
static exr_draw_clip_fn original_clip;
static double clip_ms;
static size_t clip_calls;
static exr_status timed_image(void *context,const exr_image_layer *image,const double matrix[6],double alpha,exr_error *error) {
  double started=now_ms();exr_status status=original_image(context,image,matrix,alpha,error);
  paint_image_ms+=now_ms()-started;paint_image_calls++;return status;
}
static exr_status timed_clip(void *context,const exr_path_segment *segments,size_t count,const double matrix[6],exr_fill_rule rule,unsigned text,exr_error *error) {
  double started=now_ms();exr_status status=original_clip(context,segments,count,matrix,rule,text,error);
  clip_ms+=now_ms()-started;clip_calls++;return status;
}
static void check(exr_status status,const exr_error *error) {
  if(status!=EXR_OK) { fprintf(stderr,"%d: %s\n",status,error->message);exit(1); }
}
int main(int argc,char **argv) {
  FILE *input;long length;unsigned char *data;unsigned width,rounds,round;size_t count,page;
  exr_pdf_file *file=NULL;exr_pdf_page_info *pages=NULL;exr_error error={0};
  if(argc!=4 || !(width=(unsigned)atoi(argv[2])) || !(rounds=(unsigned)atoi(argv[3]))) return 2;
  input=fopen(argv[1],"rb");if(!input || fseek(input,0,SEEK_END) || (length=ftell(input))<=0) return 2;
  rewind(input);data=malloc((size_t)length);if(!data || fread(data,1,(size_t)length,input)!=(size_t)length) return 2;fclose(input);
  check(exr_pdf_open(data,(size_t)length,&file,&error),&error);
  check(exr_pdf_pages(file,&pages,&count,&error),&error);exr_pdf_operation_end(file);
  for(round=0;round<rounds;round++) for(page=0;page<count;page++) {
    exr_canvas_config config={0};exr_canvas *canvas=NULL;exr_viewport view;
    exr_draw_sink_ex sink={0};exr_path_segment clip[5]={0};exr_pdf_image_cache_stats before,after;
    exr_bitmap out={0};double native_width,scale,started,elapsed;size_t allocations,reuses;
    const exr_pdf_page_info *p=pages+page;
    native_width=p->rotation%180 ? fmin(p->crop[3],p->media[3])-fmax(p->crop[1],p->media[1]) :
      fmin(p->crop[2],p->media[2])-fmax(p->crop[0],p->media[0]);
    scale=width/(native_width*p->user_unit);
    check(exr_pdf_page_viewport(p,scale,&view,&error),&error);
    config.width=(uint32_t)ceil(view.width);config.height=(uint32_t)ceil(view.height);
    config.channels=4;config.background=0xffffffff;
    exr_pdf_image_cache_report(file,&before);started=now_ms();
    check(exr_canvas_create(&config,&canvas,&error),&error);
    clip[0].verb=EXR_PATH_MOVE;clip[1].verb=EXR_PATH_LINE;clip[1].points[0]=(exr_path_point){view.width,0};
    clip[2].verb=EXR_PATH_LINE;clip[2].points[0]=(exr_path_point){view.width,view.height};
    clip[3].verb=EXR_PATH_LINE;clip[3].points[0]=(exr_path_point){0,view.height};clip[4].verb=EXR_PATH_CLOSE;
    check(exr_canvas_clip(canvas,clip,5,NULL,EXR_FILL_NONZERO,&error),&error);
    sink.struct_size=sizeof(sink);check(exr_canvas_get_sink_ex(canvas,&sink,&error),&error);
    original_image=sink.base.image;sink.base.image=timed_image;paint_image_ms=0;paint_image_calls=0;
    original_clip=sink.base.clip;sink.base.clip=timed_clip;clip_ms=0;clip_calls=0;
    { exr_buffer content={0};
      check(exr_pdf_content(file,p->contents,&content,&error),&error);
      check(exr_pdf_paint_page_ex(file,p,content.data,content.size,view.matrix,&sink,NULL,NULL,NULL,NULL,&error),&error);
      free(content.data);
    }
    check(exr_canvas_take(canvas,&out,&error),&error);
    allocations=canvas->local_pool.allocations+exr_pdf_buffer_pool(file)->allocations;
    reuses=canvas->local_pool.reuses+exr_pdf_buffer_pool(file)->reuses;
    exr_pdf_image_cache_report(file,&after);
    exr_pdf_operation_end(file);exr_canvas_free(canvas);elapsed=now_ms()-started;
    printf("{\"round\":%u,\"page\":%zu,\"width\":%u,\"ms\":%.6f,\"decode_ms\":%.6f,\"paint_image_ms\":%.6f,\"paint_image_calls\":%zu,\"clip_ms\":%.6f,\"clip_calls\":%zu,\"hits\":%zu,\"misses\":%zu,\"matte_bypasses\":%zu,\"wide_bypasses\":%zu,\"resident_bytes\":%zu,\"entries\":%zu,\"buffer_allocations\":%zu,\"buffer_reuses\":%zu}\n",
      round,page+1,width,elapsed,after.decode_ms-before.decode_ms,paint_image_ms,paint_image_calls,clip_ms,clip_calls,after.hits-before.hits,after.misses-before.misses,
      after.matte_bypasses-before.matte_bypasses,after.wide_bypasses-before.wide_bypasses,after.bytes,after.entries,allocations,reuses);
    free(out.pixels);
  }
  free(pages);exr_pdf_close(file);free(data);return 0;
}
