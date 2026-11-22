/* SPDX-License-Identifier: MIT */
/* Work package 4: the rendering intent must reach the ICC transform instead of
   silently falling back to relative colorimetric. Expected pixels come from
   MuPDF 1.28.2 on the same file (within one level). */
#include "exreader.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static unsigned checks; static exr_error error;
#define CHECK(x) do { checks++; if(!(x)) { fprintf(stderr,"line %d: %s (%d: %s)\n",__LINE__,#x,error.code,error.message); exit(1); } } while(0)
#define OK(x) CHECK((x)==EXR_OK)
static const char *directory;

static exr_bitmap render(const char *name) {
  char path[4096]; exr_fixed_document *d=NULL; exr_bitmap out={0};
  exr_fixed_render_options options={0};
  snprintf(path,sizeof(path),"%s/pdf-color/%s",directory,name);
  OK(exr_fixed_open(path,NULL,&d,&error)); CHECK(d);
  options.channels=4; options.background=0xffffffff;
  OK(exr_fixed_render(d,0,1,&options,&out,&error));
  exr_fixed_free(d);
  return out;
}
static void pixel(const exr_bitmap *b,size_t x,size_t y,unsigned char rgb[3]) {
  const unsigned char *p=b->pixels+y*b->stride+x*4;
  rgb[0]=p[0];rgb[1]=p[1];rgb[2]=p[2];
}
static void near(const exr_bitmap *b,size_t x,size_t y,unsigned char r,unsigned char g,unsigned char bl,const char *what) {
  unsigned char got[3]; unsigned k;
  pixel(b,x,y,got);
  for(k=0;k<3;k++) {
    int want=(int)(k==0?r:k==1?g:bl), diff=(int)got[k]-want;
    if(diff<0) diff=-diff;
    if(diff>3) fprintf(stderr,"%s channel %u got %u want %d\n",what,k,got[k],want);
    CHECK(diff<=3);
  }
}
/* The dictionary is only read when the content applies it, so the rejection
   happens during rendering rather than at open. */
static void rejected(const char *name) {
  char path[4096]; exr_fixed_document *d=NULL; exr_bitmap out={0}; exr_fixed_render_options options={0};
  snprintf(path,sizeof(path),"%s/pdf-color/%s",directory,name);
  OK(exr_fixed_open(path,NULL,&d,&error)); CHECK(d);
  options.channels=4; options.background=0xffffffff;
  CHECK(exr_fixed_render(d,0,1,&options,&out,&error)==EXR_FORMAT);
  CHECK(!out.pixels);
  exr_fixed_free(d);
}
static exr_bitmap render_ri_update(const unsigned char *base,size_t base_size,size_t prev_xref,
                                   const char *stream,exr_status expected) {
  unsigned char *buf=malloc(base_size+2048); size_t at=base_size,obj_off,xref_off;
  exr_fixed_document *d=NULL; exr_bitmap out={0}; exr_fixed_render_options options={0};
  CHECK(buf); memcpy(buf,base,base_size);
  obj_off=at;
  at+=(size_t)snprintf((char *)buf+at,2048-(at-base_size),
    "\n4 0 obj\n<< /Length %zu >>\nstream\n%s\nendstream\nendobj\n",strlen(stream),stream);
  xref_off=at;
  at+=(size_t)snprintf((char *)buf+at,2048-(at-base_size),
    "xref\n4 1\n%010zu 00000 n \ntrailer\n<< /Size 10 /Root 1 0 R /Prev %zu >>\nstartxref\n%zu\n%%%%EOF\n",
    obj_off+1,prev_xref,xref_off);
  OK(exr_fixed_open_memory(EXR_PDF,buf,at,NULL,&d,&error)); CHECK(d);
  options.channels=4; options.background=0xffffffff;
  CHECK(exr_fixed_render(d,0,1,&options,&out,&error)==expected);
  if(expected!=EXR_OK) CHECK(!out.pixels);
  exr_fixed_free(d); free(buf); return out;
}
static void test_ri_operator(void) {
  char path[4096]; FILE *f; long n; unsigned char *base; const char *sx; size_t prev_xref;
  exr_bitmap page;
  const char *stream=
    "q /RelativeColorimetric ri /CS1 cs 0.2 0.8 0.8 0.1 scn 0 0 32 16 re f Q "
    "q /Perceptual ri /CS1 cs 0.2 0.8 0.8 0.1 scn 32 0 32 16 re f Q "
    "q /Saturation ri /CS1 cs 0.2 0.8 0.8 0.1 scn 64 0 32 16 re f Q "
    "q /AbsoluteColorimetric ri /CS1 cs 0.2 0.8 0.8 0.1 scn 96 0 32 16 re f Q";
  const char *fallback_stream=
    "q /AbsoluteColorimetric ri /CustomVendorIntent ri /CS1 cs 0.2 0.8 0.8 0.1 scn 0 0 32 16 re f Q";
  snprintf(path,sizeof(path),"%s/pdf-color/intent-intents.pdf",directory);
  f=fopen(path,"rb"); CHECK(f && !fseek(f,0,SEEK_END)); n=ftell(f); CHECK(n>64); rewind(f);
  base=malloc((size_t)n+1); CHECK(base && fread(base,1,(size_t)n,f)==(size_t)n && !fclose(f));
  base[n]=0;
  sx=strstr((const char *)base+n-64,"startxref"); CHECK(sx);
  prev_xref=(size_t)strtoull(sx+9,NULL,10); CHECK(prev_xref>0);
  page=render_ri_update(base,(size_t)n,prev_xref,stream,EXR_OK);
#ifdef EXR_ENABLE_ICC
  near(&page,16,8,174,74,53,"ri relative");
  near(&page,48,8,175,80,63,"ri perceptual");
  near(&page,80,8,175,80,63,"ri saturation");
  near(&page,112,8,167,76,60,"ri absolute");
#else
  near(&page,16,8,179,26,26,"ri relative alternate");
  near(&page,112,8,179,26,26,"ri absolute alternate");
#endif
  exr_bitmap_free(&page);
  /* ISO 32000-1 8.6.5.8: unrecognized ri name falls back to RelativeColorimetric. */
  page=render_ri_update(base,(size_t)n,prev_xref,fallback_stream,EXR_OK);
#ifdef EXR_ENABLE_ICC
  near(&page,16,8,174,74,53,"ri unknown fallback");
#endif
  exr_bitmap_free(&page);
  /* Non-name operand for ri must fail. */
  (void)render_ri_update(base,(size_t)n,prev_xref,"1 ri",EXR_FORMAT);
  free(base);
}
int main(int argc,char **argv) {
  exr_bitmap page; unsigned char rel[3],per[3];
  CHECK(argc==2); directory=argv[1];
  page=render("intent-intents.pdf");
  CHECK(page.width==128 && page.height==16);
  /* MuPDF: relative (174,74,53), perceptual (175,80,63), saturation (175,80,63), absolute (167,76,60). */
#ifdef EXR_ENABLE_ICC
  near(&page,16,8,174,74,53,"relative");
  near(&page,48,8,175,80,63,"perceptual");
  near(&page,80,8,175,80,63,"saturation");
  near(&page,112,8,167,76,60,"absolute");
  pixel(&page,16,8,rel); pixel(&page,48,8,per);
  CHECK(memcmp(rel,per,3)!=0); /* the intent must change the result */
#else
  near(&page,16,8,179,26,26,"relative alternate");
  near(&page,48,8,179,26,26,"perceptual alternate");
  near(&page,80,8,179,26,26,"saturation alternate");
  near(&page,112,8,179,26,26,"absolute alternate");
  pixel(&page,16,8,rel);pixel(&page,48,8,per);CHECK(!memcmp(rel,per,3));
#endif
  exr_bitmap_free(&page);
  rejected("intent-bad-name.pdf");
  rejected("intent-bad-type.pdf");
  /* ISO 32000-1 8.6.5.8: an image's /Intent overrides the graphics-state intent.
     MuPDF 1.28.2 renders the same file as (175,74,53), (175,81,63), (175,81,63). */
  page=render("image-intent-default.pdf");
#ifdef EXR_ENABLE_ICC
  near(&page,8,8,175,74,53,"image default");
#else
  near(&page,8,8,178,25,25,"image default alternate");
#endif
  exr_bitmap_free(&page);
  page=render("image-intent-perceptual.pdf");
#ifdef EXR_ENABLE_ICC
  near(&page,8,8,175,81,63,"image perceptual");
#else
  near(&page,8,8,178,25,25,"image perceptual alternate");
#endif
  exr_bitmap_free(&page);
  page=render("image-intent-saturation.pdf");
#ifdef EXR_ENABLE_ICC
  near(&page,8,8,175,81,63,"image saturation");
#else
  near(&page,8,8,178,25,25,"image saturation alternate");
#endif
  exr_bitmap_free(&page);
  rejected("image-intent-bad.pdf");
  rejected("image-intent-bad-type.pdf");
  test_ri_operator();
  printf("%u native PDF rendering-intent checks passed\n",checks);
  return 0;
}
