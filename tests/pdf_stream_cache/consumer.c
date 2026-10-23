/* SPDX-License-Identifier: MIT */
#include "exreader.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static exr_error error;
static unsigned checks;
#define CHECK(x) do { checks++; if(!(x)) { fprintf(stderr,"line %d: %s (%d: %s)\n",__LINE__,#x,error.code,error.message); exit(1); } } while(0)
#define OK(x) CHECK((x)==EXR_OK)
static int cancel(void *unused) { (void)unused; return 1; }
static void pixels(const exr_bitmap *b,size_t page) {
  const unsigned char *left,*right;
  CHECK(b->width==8 && b->height==8 && b->channels==4 && b->stride>=32);
  left=b->pixels+b->stride*4+4; right=b->pixels+b->stride*4+24;
  CHECK(left[0]==(page%2 ? 255 : 0) && right[0]==(page%2 ? 0 : 255));
  CHECK(left[3]==255 && right[3]==255);
}
int main(int argc,char **argv) {
  exr_fixed_document *d=NULL; exr_bitmap b={0},retained={0};
  exr_fixed_text *retained_text=NULL,*text=NULL; exr_control control={0};
  char path[4096]; size_t count,n; unsigned i; exr_status status;
  CHECK(argc==3 && (!strcmp(argv[2],"baseline") || !strcmp(argv[2],"candidate")));
  snprintf(path,sizeof(path),"%s/many-pages.pdf",argv[1]);
  OK(exr_fixed_open(path,NULL,&d,&error)); CHECK(exr_fixed_pages(d,&count) && count==24);
  for(i=0;i<count;i++) {
    status=exr_fixed_render(d,i,1,NULL,&b,&error);
    if(status!=EXR_OK) break;
    pixels(&b,i);
    if(!i) retained=b; else exr_bitmap_free(&b);
    memset(&b,0,sizeof(b));
    status=exr_fixed_load_text(d,i,NULL,&text,&error); if(status!=EXR_OK) break;
    CHECK(exr_fixed_text_string(text,&n) && n==0);
    if(!i) retained_text=text; else exr_fixed_text_free(text);
    text=NULL;
  }
  if(!strcmp(argv[2],"baseline")) {
    CHECK(i<count && status==EXR_LIMIT);
    printf("{\"baseline_reproduced\":true,\"completed_pages\":%u,\"status\":%d}\n",i,status);
    exr_fixed_text_free(retained_text); exr_fixed_text_free(text);
    exr_bitmap_free(&retained); exr_bitmap_free(&b); exr_fixed_free(d); return 0;
  }
  CHECK(i==count && status==EXR_OK);
  pixels(&retained,0); CHECK(exr_fixed_text_string(retained_text,&n) && n==0);
  for(i=0;i<48;i++) {
    size_t page=(i*17)%count;
    OK(exr_fixed_render(d,page,1,NULL,&b,&error)); pixels(&b,page); exr_bitmap_free(&b);
    OK(exr_fixed_load_text(d,page,NULL,&text,&error)); exr_fixed_text_free(text); text=NULL;
  }
  control.cancelled=cancel;
  CHECK(exr_fixed_render(d,0,1,&control,&b,&error)==EXR_CANCELLED && !b.pixels);
  OK(exr_fixed_render(d,0,1,NULL,&b,&error)); pixels(&b,0); exr_bitmap_free(&b);
  exr_fixed_text_free(retained_text); exr_bitmap_free(&retained); exr_fixed_free(d); d=NULL;
  snprintf(path,sizeof(path),"%s/oversized-page.pdf",argv[1]);
  OK(exr_fixed_open(path,NULL,&d,&error));
  CHECK(exr_fixed_render(d,0,1,NULL,&b,&error)==EXR_LIMIT && !b.pixels);
  CHECK(exr_fixed_load_text(d,0,NULL,&text,&error)==EXR_LIMIT && !text);
  exr_fixed_free(d);
  printf("{\"accepted\":true,\"checks\":%u,\"complete_pages\":24,\"random_operations\":96,\"single_page_limit_preserved\":true}\n",checks);
  return 0;
}
