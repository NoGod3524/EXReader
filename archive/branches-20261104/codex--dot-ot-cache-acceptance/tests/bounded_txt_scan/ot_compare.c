/* Public-API comparison of warm/cold OpenType shaping and cancellation. */
#include "exreader.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
typedef struct { unsigned calls, stop; } cancel_state;
static int cancel_after(void *context) {
  cancel_state *s=(cancel_state *)context;
  return ++s->calls >= s->stop;
}
static void report(exr_font *font, const char *text, exr_shape_options *o) {
  exr_shaped_glyph *out=NULL; size_t count=0,i; exr_error error={0};
  exr_status status=exr_shape(font,0,text,strlen(text),o,&out,&count,&error);
  printf("status=%d count=%zu\n",(int)status,count);
  if(status!=EXR_OK) { exr_free(out); exit(1); }
  for(i=0;i<count;i++) {
    exr_shaped_glyph *g=&out[i];
    printf("%zu %zu %u %.9g %.9g %.9g %.9g %u\n",g->start,g->end,g->glyph,
      g->advance_x,g->advance_y,g->offset_x,g->offset_y,g->flags);
  }
  exr_free(out);
}
int main(int argc,char **argv) {
  static const char *samples[]={
    "Unique history line 00001234 with distinct content and a readable paragraph.",
    "office affine A\xcc\x81 a\xcc\x88 b\xcc\x81",
    "\xe4\xb8\xad\xe6\x96\x87\xe9\x98\x85\xe8\xaf\xbb",
    "\xd0\x91\xd1\x80\xd0\xb5\xd1\x82\xd1\x91\xd1\x80",
    "a 1 a 2 a 3 abc abc", "abc abc abc"
  };
  static const unsigned stops[]={1,2,3,5,10,50,100};
  exr_font *font=NULL; exr_error error={0}; exr_shape_options o=exr_shape_defaults();
  char text[2049]; size_t i,round;
  if(argc!=2 || exr_font_open(argv[1],&font,&error)!=EXR_OK) return 2;
  o.font_size=42;
  for(round=0;round<3;round++) for(i=0;i<sizeof(samples)/sizeof(samples[0]);i++) {
    printf("sample=%zu round=%zu\n",i,round); report(font,samples[i],&o);
  }
  memset(text,'a',sizeof(text)-1); text[sizeof(text)-1]=0;
  for(i=0;i<sizeof(stops)/sizeof(stops[0]);i++) {
    cancel_state state={0,stops[i]}; exr_shaped_glyph *out=NULL; size_t n=0;
    exr_status status;
    o.control.cancelled=cancel_after; o.control.context=&state;
    status=exr_shape(font,0,text,strlen(text),&o,&out,&n,&error);
    printf("cancel=%u status=%d polls=%u count=%zu\n",stops[i],(int)status,state.calls,n);
    exr_free(out);
  }
  exr_font_free(font); return 0;
}
