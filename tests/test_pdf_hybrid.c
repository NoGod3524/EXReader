/* SPDX-License-Identifier: MIT */
#include "exreader.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
static exr_error error; static const char *scenario;
#define CHECK(x) do { if(!(x)) { fprintf(stderr,"%s line %d: %s (%d: %s)\n",scenario,__LINE__,#x,error.code,error.message); exit(1); } } while(0)
#define OK(x) CHECK((x)==EXR_OK)
static void deck(const char *dir) {
  char path[1024]; exr_fixed_document *d=NULL; size_t n=0,i,rendered=0,failures=0; double t0,first=0;
  scenario="deck"; snprintf(path,sizeof(path),"%s/pdf-ppt/deck.pdf",dir);
  t0=(double)clock()*1000/CLOCKS_PER_SEC;
  OK(exr_fixed_open(path,NULL,&d,&error)); exr_fixed_pages(d,&n); CHECK(n==15);
  for(i=0;i<n;i++) {
    exr_bitmap b={0};
    if(exr_fixed_render(d,i,1,NULL,&b,&error)==EXR_OK && b.pixels) { rendered++; if(!i) first=(double)clock()*1000/CLOCKS_PER_SEC-t0; } else failures++;
    exr_bitmap_free(&b);
  }
  printf("pages=%zu rendered=%zu failures=%zu first_paint_ms=%.1f\n",n,rendered,failures,first);
  CHECK(rendered==15 && !failures); exr_fixed_free(d);
}
int main(int argc,char **argv) {
  if(argc<2) return 2;
  deck(argv[1]);
  puts("ok"); return 0;
}
