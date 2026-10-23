/* SPDX-License-Identifier: MIT */
#define _POSIX_C_SOURCE 200809L
#include "exreader.h"
#include <inttypes.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/resource.h>
#include <time.h>

static double now_ms(void) {
  struct timespec t;
  if(clock_gettime(CLOCK_MONOTONIC,&t)) abort();
  return t.tv_sec*1000.0+t.tv_nsec/1000000.0;
}
static int expired(void *context) { return now_ms()>=*(double *)context; }
static uint64_t hash_bytes(uint64_t h,const void *bytes,size_t size) {
  const unsigned char *p=bytes;size_t i;
  for(i=0;i<size;i++) { h^=p[i];h*=UINT64_C(1099511628211); }
  return h;
}
static exr_status page_hash(exr_layout *page,uint64_t *out,exr_error *error) {
  exr_bitmap bitmap={0};size_t count,i;const exr_page *pages;
  uint64_t h=UINT64_C(14695981039346656037);exr_status status;
  pages=exr_layout_pages(page,&count);
  if(!pages || count!=1) return EXR_FORMAT;
  h=hash_bytes(h,&pages[0].start,sizeof(pages[0].start));
  h=hash_bytes(h,&pages[0].end,sizeof(pages[0].end));
  status=exr_render_page_color(page,exr_layout_font(page),0,&bitmap,error);
  if(status!=EXR_OK) return status;
  h=hash_bytes(h,&bitmap.width,sizeof(bitmap.width));
  h=hash_bytes(h,&bitmap.height,sizeof(bitmap.height));
  for(i=0;i<bitmap.height;i++) h=hash_bytes(h,bitmap.pixels+i*bitmap.stride,(size_t)bitmap.width*4);
  exr_bitmap_free(&bitmap);*out=h;return EXR_OK;
}

int main(int argc,char **argv) {
  exr_publication *book=NULL;exr_document *snapshot=NULL;exr_font *font=NULL;
  exr_pager *pager=NULL,*reference=NULL;exr_layout *page=NULL;
  exr_error error={0};exr_anchor anchor={0},reference_anchor={0};
  exr_anchor_match match={0},expected={0};
  exr_layout_config config=exr_layout_config_defaults();
  exr_chapter_options options=exr_chapter_options_defaults();
  exr_chapter_stats before={0},after={0};
  exr_status status=EXR_ARGUMENT;const char *stage="arguments";
  double began=0,create_ms=0,resolve_ms=0,snapshot_ms=0,deadline;
  uint64_t actual[2]={0},wanted[2]={0};size_t quote_bytes=0,i;struct rusage usage={0};
  int same_match=0,same_pages=0;
  if(argc!=5) { fprintf(stderr,"usage: r4-anchor-probe book font window-bytes quote-bytes\n");return 2; }
  options.window_bytes=(size_t)strtoull(argv[3],NULL,10);
  quote_bytes=(size_t)strtoull(argv[4],NULL,10);
  if((options.window_bytes!=16384 && options.window_bytes!=4194304) || (quote_bytes!=0 && quote_bytes!=64)) return 2;
#define RUN(label,call) do { stage=label;status=(call);if(status!=EXR_OK) goto done; } while(0)
  RUN("font",exr_font_open(argv[2],&font,&error));
  RUN("open",exr_publication_open(argv[1],&book,&error));
  began=now_ms();
  RUN("create",exr_publication_pager_create(book,0,font,&config,&options,&pager,&error));
  create_ms=now_ms()-began;
  RUN("first_page",exr_pager_next(pager,&page,&error));
  if(!page) { status=EXR_FORMAT;goto done; }
  RUN("first_pixels",page_hash(page,&actual[0],&error));exr_layout_free(page);page=NULL;
  RUN("anchor_create",exr_pager_anchor_create(pager,1024,1024+quote_bytes,NULL,&anchor,&error));
  before=exr_pager_chapter_statistics(pager);
  deadline=now_ms()+30000;
  { exr_control control={expired,NULL,&deadline};began=now_ms();stage="resolve";
    status=exr_pager_anchor_resolve(pager,&anchor,&control,&match,&error);
    resolve_ms=now_ms()-began;after=exr_pager_chapter_statistics(pager);getrusage(RUSAGE_SELF,&usage);
    if(status!=EXR_OK) goto done;
  }
  RUN("continuation",exr_pager_next(pager,&page,&error));
  if(!page) { status=EXR_FORMAT;goto done; }
  RUN("continuation_pixels",page_hash(page,&actual[1],&error));exr_layout_free(page);page=NULL;
  RUN("snapshot",exr_publication_load(book,0,&snapshot,&error));
  RUN("snapshot_anchor",exr_anchor_create(snapshot,1024,1024+quote_bytes,&reference_anchor,&error));
  if(strcmp(anchor.exact,reference_anchor.exact) || strcmp(anchor.prefix,reference_anchor.prefix) ||
     strcmp(anchor.suffix,reference_anchor.suffix) || strcmp(anchor.chapter,reference_anchor.chapter)) {
    stage="selector_equivalence";status=EXR_FORMAT;goto done;
  }
  began=now_ms();RUN("snapshot_resolve",exr_anchor_resolve(snapshot,&anchor,&expected,&error));
  snapshot_ms=now_ms()-began;
  same_match=match.state==expected.state && match.start==expected.start && match.end==expected.end;
  RUN("snapshot_pager",exr_pager_create(snapshot,font,&config,&reference,&error));
  for(i=0;i<2;i++) {
    RUN("snapshot_page",exr_pager_next(reference,&page,&error));
    if(!page) { status=EXR_FORMAT;goto done; }
    RUN("snapshot_pixels",page_hash(page,&wanted[i],&error));exr_layout_free(page);page=NULL;
  }
  same_pages=actual[0]==wanted[0] && actual[1]==wanted[1];
  if(!same_match || !same_pages) { stage="equivalence";status=EXR_FORMAT; }
done:
  printf("{\"schema\":1,\"sdk\":\"%s\",\"abi\":%u,\"status\":%d,\"stage\":\"%s\",\"window_bytes\":%zu,\"quote_bytes\":%zu,"
         "\"create_ms\":%.6f,\"resolve_ms\":%.6f,\"snapshot_resolve_ms\":%.6f,"
         "\"match_state\":%d,\"expected_state\":%d,\"same_match\":%s,\"same_pages\":%s,"
         "\"page_hashes\":[\"%016" PRIx64 "\",\"%016" PRIx64 "\"],"
         "\"projection_bytes\":%zu,\"resolve_windows_loaded\":%zu,\"resolve_windows_evicted\":%zu,"
         "\"index_bytes\":%zu,\"peak_workspace_bytes\":%zu,\"snapshot_bytes\":%zu,\"bounded_peak_rss_bytes\":%zu}\n",
         exr_version(),exr_abi_version(),status,stage,options.window_bytes,quote_bytes,create_ms,resolve_ms,snapshot_ms,match.state,expected.state,
         same_match?"true":"false",same_pages?"true":"false",actual[0],actual[1],after.projection_bytes,
         after.windows_loaded-before.windows_loaded,after.windows_evicted-before.windows_evicted,
         after.index_bytes,after.peak_parse_workspace_bytes,after.explicit_snapshot_bytes,(size_t)usage.ru_maxrss*1024);
  if(status!=EXR_OK) fprintf(stderr,"stage=%s status=%d\n",stage,status);
  exr_layout_free(page);exr_pager_free(reference);exr_document_free(snapshot);
  exr_anchor_free(&reference_anchor);exr_anchor_free(&anchor);exr_pager_free(pager);exr_publication_free(book);exr_font_free(font);
  return status==EXR_OK ? 0 : 1;
}
