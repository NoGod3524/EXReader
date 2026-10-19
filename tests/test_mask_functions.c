/* SPDX-License-Identifier: MIT */
#include "exreader.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static exr_error error;static unsigned checks,maximum;
#define CHECK(x) do { checks++;if(!(x)) { fprintf(stderr,"line %d: %s (%d: %s)\n",__LINE__,#x,error.code,error.message);exit(1); } } while(0)
#define OK(x) CHECK((x)==EXR_OK)
static const char *directory;
static void scene(const char *name,const unsigned char expected[8]) {
  exr_fixed_document *d=NULL;char path[4096];unsigned w,k;
  snprintf(path,sizeof(path),"%s/pdf-blend/%s",directory,name);OK(exr_fixed_open(path,NULL,&d,&error));
  for(w=0;w<2;w++) {
    exr_bitmap b={0};exr_fixed_render_options options={0};options.channels=4;options.background=w ? 0xffffffff : 0;
    exr_status status=exr_fixed_render(d,0,1,&options,&b,&error);
    if(expected) {
      if(status!=EXR_OK) fprintf(stderr,"%s: %s\n",name,error.message);
      CHECK(status==EXR_OK);
      for(k=0;k<4;k++) {
        const unsigned char *p=b.pixels+8*b.stride+8*4;unsigned value=w || k==3 ? p[k] : (p[k]*p[3]+127)/255;
        unsigned difference=(unsigned)abs((int)value-(int)expected[4*w+k]);
        if(difference>maximum) maximum=difference;
        if(difference>2) fprintf(stderr,"%s white %u channel %u: %u != %u\n",name,w,k,value,expected[4*w+k]);
        CHECK(difference<=2);
      }
    } else { if(status!=EXR_FORMAT) fprintf(stderr,"%s: expected format error, got %d %s\n",name,status,error.message);CHECK(status==EXR_FORMAT && !b.pixels); }
    exr_bitmap_free(&b);
  }
  exr_fixed_free(d);
}
int main(int argc,char **argv) {
  const char *kinds[]={"alpha","luminosity"};const char *functions[]={"sampled","exponential","stitching","calculator","identity","domain","square"};
  const char *images[]={"none","soft","explicit","key-visible","key-hidden","both"};
  const char *geometry[]={"rotated-inside","rotated-outside","outside-zero","outside-inverse","knockout","nonisolated"};
  const char *bad[]={"name","scalar","outputs","domain","cycle","calculator","samples","missing-type"};
  unsigned i,j,k;unsigned char expected[72][8];char path[4096];FILE *f;size_t row=0;
  CHECK(argc==2);directory=argv[1];snprintf(path,sizeof(path),"%s/pdf-blend/mask-function-oracle.bin",directory);
  f=fopen(path,"rb");CHECK(f);CHECK(fread(expected,1,sizeof(expected),f)==sizeof(expected));CHECK(fgetc(f)==EOF);fclose(f);
  for(i=0;i<2;i++) for(j=0;j<7;j++) for(k=64;k<=192;k+=64) {
    snprintf(path,sizeof(path),"mask-function-%s-%s-%u.pdf",kinds[i],functions[j],k);scene(path,expected[row++]);
  }
  for(i=0;i<6;i++) for(k=64;k<=192;k+=64) { snprintf(path,sizeof(path),"mask-function-image-%s-%u.pdf",images[i],k);scene(path,expected[row++]); }
  for(i=0;i<2;i++) for(j=0;j<6;j++) { snprintf(path,sizeof(path),"mask-function-%s-%s.pdf",kinds[i],geometry[j]);scene(path,expected[row++]); }
  CHECK(row==72);
  for(i=0;i<8;i++) { snprintf(path,sizeof(path),"mask-function-bad-%s.pdf",bad[i]);scene(path,NULL); }
  printf("%u mask function checks; maximum analytic difference %u/255\n",checks,maximum);return 0;
}
