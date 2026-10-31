/* SPDX-License-Identifier: MIT */
#define _POSIX_C_SOURCE 200809L
#include "exreader.h"
#include <inttypes.h>
#include <stdio.h>
#include <string.h>
#include <sys/resource.h>
#include <time.h>

/* Linux probe, installed public SDK only. Same monotonic/RSS units as benchmark.c. */
#define RANDOM_TURNS 16
#define MAX_PAGES 256
typedef struct {
  const char *phase;
  size_t page;
  double render_ms;
  uint32_t width,height,channels;
  uint64_t pixel_bytes,pixel_hash;
  uint32_t first_rgba;
  int status,uniform_rgba;
} sample;

static double now_ms(void) {
  struct timespec value;
  if(clock_gettime(CLOCK_MONOTONIC,&value)) return -1;
  return (double)value.tv_sec*1000.0+(double)value.tv_nsec/1000000.0;
}
static int peak_rss(uint64_t *bytes) {
  struct rusage usage;
  if(getrusage(RUSAGE_SELF,&usage) || usage.ru_maxrss<0) return 0;
  *bytes=(uint64_t)usage.ru_maxrss*1024;
  return 1;
}
static void json_string(const char *text) {
  const unsigned char *p=(const unsigned char *)text;
  putchar('"');
  for(;*p;p++) {
    if(*p=='"' || *p=='\\') printf("\\%c",*p);
    else if(*p<32) printf("\\u%04x",*p);
    else putchar(*p);
  }
  putchar('"');
}
static int paint(exr_fixed_document *document,size_t page,const char *phase,
                 sample *item,exr_error *error) {
  exr_fixed_render_options options={0};
  exr_bitmap bitmap={0};
  double started=now_ms();
  size_t y,x,row;
  uint64_t hash=UINT64_C(14695981039346656037);
  options.channels=4;options.background=0xffffffffu;
  item->phase=phase;item->page=page;
  item->status=(int)exr_fixed_render(document,page,1.0,&options,&bitmap,error);
  item->render_ms=now_ms()-started;
  if(item->status!=EXR_OK) { exr_bitmap_free(&bitmap);return 0; }
  item->width=bitmap.width;item->height=bitmap.height;item->channels=bitmap.channels;
  row=(size_t)bitmap.width*bitmap.channels;
  if(!bitmap.pixels || !bitmap.width || !bitmap.height || bitmap.channels!=4 ||
     bitmap.width>4096 || bitmap.height>4096 || row>bitmap.stride) {
    item->status=EXR_LIMIT;exr_bitmap_free(&bitmap);return 0;
  }
  item->pixel_bytes=(uint64_t)row*bitmap.height;
  item->uniform_rgba=1;
  item->first_rgba=((uint32_t)bitmap.pixels[0]<<24)|((uint32_t)bitmap.pixels[1]<<16)|
                   ((uint32_t)bitmap.pixels[2]<<8)|bitmap.pixels[3];
  /* Hash only active RGBA bytes, excluding allocator stride padding. */
  for(y=0;y<bitmap.height;y++) for(x=0;x<row;x++) {
    if(bitmap.pixels[y*bitmap.stride+x]!=bitmap.pixels[x%4]) item->uniform_rgba=0;
    hash^=bitmap.pixels[y*bitmap.stride+x];hash*=UINT64_C(1099511628211);
  }
  item->pixel_hash=hash;
  exr_bitmap_free(&bitmap);
  return item->render_ms>=0;
}
int main(int argc,char **argv) {
  exr_font *font=NULL;
  exr_fixed_document *document=NULL;
  exr_fixed_open_options options={0};
  exr_error error={0};
  const exr_fixed_page *pages=NULL;
  sample samples[MAX_PAGES+RANDOM_TURNS+1]={{0}};
  size_t page_count=0,count=0,i;
  uint32_t random=20261022u;
  uint64_t baseline=0,peak=0,directory_bytes=0;
  double started,at,font_ms=0,open_ms=0,directory_ms=0,first_visible_ms=0;
  const char *stage="initialization";
  int status=EXR_OK,success=0;
  if(argc!=3) { fprintf(stderr,"Usage: reading-pdf-benchmark input.pdf|input.cbz font.ttf\n");return 2; }
  started=now_ms();
  if(started<0 || !peak_rss(&baseline)) { fprintf(stderr,"Monotonic clock/RSS unavailable\n");return 2; }
  stage="font_open";at=now_ms();
  status=(int)exr_font_open(argv[2],&font,&error);font_ms=now_ms()-at;
  if(status!=EXR_OK) goto done;
  options.struct_size=sizeof(options);options.fallback_font=font;
  stage="fixed_open";at=now_ms();
  status=(int)exr_fixed_open(argv[1],&options,&document,&error);open_ms=now_ms()-at;
  if(status!=EXR_OK) goto done;
  stage="directory";at=now_ms();
  pages=exr_fixed_pages(document,&page_count);
  directory_bytes=exr_fixed_memory_size(document);directory_ms=now_ms()-at;
  if(!pages || !page_count || page_count>MAX_PAGES) { status=EXR_LIMIT;goto done; }
  stage="first_render";
  if(!paint(document,0,"first",&samples[count++],&error)) { status=samples[count-1].status;goto done; }
  first_visible_ms=now_ms()-started;
  /* Visit every declared page before the deterministic repeat plan. */
  stage="sequential_render";
  for(i=0;i<page_count;i++) {
    if(!paint(document,i,"sequential",&samples[count++],&error)) { status=samples[count-1].status;goto done; }
  }
  stage="random_render";
  for(i=0;i<RANDOM_TURNS;i++) {
    random=random*1664525u+1013904223u;
    if(!paint(document,(size_t)(random%page_count),"random",&samples[count++],&error)) {
      status=samples[count-1].status;goto done;
    }
  }
  success=1;stage="complete";
done:
  if(!peak_rss(&peak)) { success=0;stage="rss";status=EXR_IO; }
  printf("{\"schema_version\":1,\"engine_version\":");json_string(exr_version());
  printf(",\"input\":");json_string(argv[1]);printf(",\"font\":");json_string(argv[2]);
  printf(",\"success\":%s,\"error_stage\":",success?"true":"false");json_string(stage);
  printf(",\"status\":%d,\"clock\":\"monotonic\",\"disk_cache\":\"uncontrolled\","
         "\"rss_metric\":\"process_high_water_mark\",\"scale\":1,\"channels\":4,"
         "\"background\":\"ffffffff\",\"pixel_hash_algorithm\":\"fnv1a64-active-rgba\","
         "\"seed\":20261022,\"random_turns\":16,\"page_count\":%zu,\"sample_count\":%zu,"
         "\"directory_owned_bytes\":%" PRIu64 ",\"font_open_ms\":%.6f,\"fixed_open_ms\":%.6f,"
         "\"directory_ms\":%.6f,\"first_visible_total_ms\":%.6f,"
         "\"baseline_peak_rss_bytes\":%" PRIu64 ",\"peak_rss_bytes\":%" PRIu64 ","
         "\"incremental_peak_rss_bytes\":%" PRIu64 ",\"samples\":[",
         status,page_count,count,directory_bytes,font_ms,open_ms,directory_ms,first_visible_ms,
         baseline,peak,peak>=baseline?peak-baseline:0);
  for(i=0;i<count;i++) {
    sample *s=&samples[i];
    printf("%s{\"phase\":",i?",":"");json_string(s->phase);
    printf(",\"page\":%zu,\"status\":%d,\"render_ms\":%.6f,\"width\":%u,\"height\":%u,"
           "\"channels\":%u,\"pixel_bytes\":%" PRIu64 ",\"pixel_hash\":\"%016" PRIx64 "\","
           "\"first_rgba\":\"%08" PRIx32 "\",\"uniform_rgba\":%s}",
           s->page,s->status,s->render_ms,s->width,s->height,s->channels,s->pixel_bytes,s->pixel_hash,
           s->first_rgba,s->uniform_rgba?"true":"false");
  }
  printf("]}\n");
  if(!success) fprintf(stderr,"Probe failed at %s (status %d)\n",stage,status);
  exr_fixed_free(document);exr_font_free(font);
  return success?0:1;
}
