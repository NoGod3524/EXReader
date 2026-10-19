/* SPDX-License-Identifier: MIT */
#include "exreader.h"
#include "cmyk_reference.h"
#include <stdio.h>
#include <string.h>
static unsigned checks,max_error,legacy_difference;static exr_error error;static const char *directory;static char current[128];
#define CHECK(x) do { checks++;if(!(x)) { fprintf(stderr,"line %d: %s (%d: %s)\n",__LINE__,#x,error.code,error.message);exit(1); } } while(0)
#define OK(x) CHECK((x)==EXR_OK)
static const unsigned sources[3][4]={{180,120,80,90},{0,0,0,200},{128,128,128,0}};
static exr_fixed_document *open_scene(const char *name) {
  char path[4096];exr_fixed_document *d=NULL;snprintf(path,sizeof(path),"%s/pdf-color/%s",directory,name);
  OK(exr_fixed_open(path,NULL,&d,&error));return d;
}
static exr_bitmap render(const char *name,int legacy) {
  exr_fixed_document *d=open_scene(name);exr_canvas_config config={0};exr_canvas *c=NULL;exr_bitmap out={0};exr_draw_sink_ex sink={0};
  config.width=config.height=16;config.background=0xffffffff;
  OK(exr_canvas_create(&config,&c,&error));sink.struct_size=legacy ? offsetof(exr_draw_sink_ex,image_cmyk) : sizeof(sink);
  OK(exr_canvas_get_sink_ex(c,&sink,&error));OK(exr_fixed_draw_ex(d,0,NULL,&sink,NULL,&error));
  OK(exr_canvas_take(c,&out,&error));exr_canvas_free(c);exr_fixed_free(d);return out;
}
static void near(const exr_bitmap *b,const double ink[4]) {
  unsigned expected[3],k;cmyk_reference(ink,expected);
  for(k=0;k<3;k++) {
    const unsigned char *p=b->pixels+4*b->stride+4*4;unsigned diff=(unsigned)abs((int)p[k]-(int)expected[k]);
    if(diff>max_error) max_error=diff;
    if(diff>2) fprintf(stderr,"%s channel %u got %u want %u\n",current,k,p[k],expected[k]);
    CHECK(diff<=2);CHECK(p[3]==255);
  }
}
static void pdf_scenes(void) {
  static const char *kinds[]={"image","axial","radial","mesh4","mesh5","mesh6","mesh7"};
  static const char *modes[]={"normal","multiply","screen"};const double base[4]={.2,.4,.6,.1};unsigned i,j,m,k;
  for(i=0;i<7;i++) for(j=0;j<3;j++) for(m=0;m<3;m++) {
    char name[128];double expected[4];exr_bitmap b;
    snprintf(name,sizeof(name),"native-%s-%u-%s.pdf",kinds[i],j,modes[m]);b=render(name,0);
    for(k=0;k<4;k++) {
      double s=sources[j][k]/255.,mixed=m==0 ? s : m==1 ? base[k]+s-base[k]*s : base[k]*s;
      expected[k]=(base[k]+mixed)*.5;
    }
    snprintf(current,sizeof(current),"%s",name);near(&b,expected);
    if(i==0 && m==0) {
      exr_bitmap old=render(name,1);const unsigned char *a=b.pixels+4*b.stride+16,*p=old.pixels+4*old.stride+16;
      for(k=0;k<3;k++) { unsigned diff=(unsigned)abs((int)a[k]-(int)p[k]);if(diff>legacy_difference) legacy_difference=diff; }
      exr_bitmap_free(&old);
    }
    exr_bitmap_free(&b);
  }
  CHECK(legacy_difference>3);
  { static const char *variants[]={"decode","16","mask","matte","jpeg","key","page","appearance"};
    for(i=0;i<8;i++) {
      char name[128];double expected[4],alpha=(i==2 || i==3) ? .5*128/255. : i==5 ? 0 : .5;exr_bitmap b;
      snprintf(name,sizeof(name),"native-image-%s.pdf",variants[i]);b=render(name,0);
      for(k=0;k<4;k++) {
        double s=sources[0][k]/255.;
        if(i==3) { const double matte[4]={.2,.3,.4,.1};s=floor(fmax(0,fmin(1,matte[k]+(s-matte[k])/(128/255.)))*255+.5)/255.; }
        expected[k]=base[k]*(1-alpha)+s*alpha;
      }
      snprintf(current,sizeof(current),"%s",name);near(&b,expected);exr_bitmap_free(&b);
    }
  }
  { static const char *bad[]={"native-image-bad-decode.pdf","native-image-bad-mask.pdf","native-image-bad-intent.pdf"};
    for(i=0;i<3;i++) { exr_fixed_document *d=open_scene(bad[i]);exr_bitmap out={0};
      CHECK(exr_fixed_render(d,0,1,NULL,&out,&error)==EXR_FORMAT);CHECK(!out.pixels);exr_fixed_free(d); }
  }
  { exr_fixed_document *d=open_scene("native-image-budget.pdf");exr_bitmap out={0};
    CHECK(exr_fixed_render(d,0,1,NULL,&out,&error)==EXR_LIMIT);CHECK(!out.pixels);exr_fixed_free(d); }
}
static int cancelled(void *context) { return *(int *)context; }
static exr_canvas *canvas(int *stop) {
  exr_canvas_config config={0};exr_canvas *c=NULL;config.width=config.height=8;config.background=0xffffffff;
  if(stop) { config.control.cancelled=cancelled;config.control.context=stop; }
  OK(exr_canvas_create(&config,&c,&error));return c;
}
static void canvas_scenes(void) {
  unsigned char fallback[8]={128,128,128,255,128,128,128,255},raw[8]={0,0,0,128,128,128,128,0};
  exr_image_layer image={0};exr_bitmap inks={.width=2,.height=1,.stride=8,.pixels=raw,.channels=4};double matrix[6]={8,0,0,8,0,0};unsigned scenario,k;
  image.bitmap=(exr_bitmap){.width=2,.height=1,.stride=8,.pixels=fallback,.channels=4};
  /* Equal RGB fallbacks with different ink separations must remain distinct. */
  for(scenario=0;scenario<4;scenario++) {
    exr_canvas *c=canvas(NULL);exr_bitmap b={0};exr_draw_sink_ex sink={0};
    sink.struct_size=sizeof(sink);OK(exr_canvas_get_sink_ex(c,&sink,&error));CHECK(sink.image_space(c)==EXR_GROUP_RGB);
    if(scenario!=3) OK(exr_canvas_begin_group(c,1,EXR_BLEND_NORMAL,EXR_GROUP_CMYK|EXR_GROUP_ISOLATED,&error));
    if(scenario==1) image.interpolate=1;else image.interpolate=0;
    if(scenario==2) { fallback[3]=0;image.interpolate=1; }
    if(scenario!=3) CHECK(sink.image_space(c)==EXR_GROUP_CMYK);
    OK(exr_canvas_image_cmyk(c,&image,&inks,matrix,1,&error));
    if(scenario!=3) OK(exr_canvas_end_layer(c,1,&error));
    CHECK(sink.image_space(c)==EXR_GROUP_RGB);OK(exr_canvas_take(c,&b,&error));
    for(k=0;k<3;k++) {
      if(scenario==3) CHECK(b.pixels[4*b.stride+4*4+k]==128);
      else {
        /* Interior x=4 uses bilinear weights .375/.625 at its centre. */
        double mix=scenario==0 || scenario==2 ? 1 : .625,values[4]={128./255*mix,128./255*mix,128./255*mix,128./255*(1-mix)};
        unsigned expected[3];double a=scenario==2 ? .625 : 1;cmyk_reference(values,expected);
        CHECK(abs((int)b.pixels[4*b.stride+4*4+k]-(int)floor(expected[k]*a+255*(1-a)+.5))<=2);
      }
    }
    exr_bitmap_free(&b);exr_canvas_free(c);fallback[3]=255;
  }
  { exr_canvas *c=canvas(NULL);exr_bitmap b={0};exr_draw_style style=exr_draw_style_defaults();
    const double base[4]={.2,.4,.6,.1};unsigned first[3]={0};
    const exr_path_segment rect[5]={{.verb=EXR_PATH_MOVE,.points={{0,0}}},{.verb=EXR_PATH_LINE,.points={{8,0}}},
      {.verb=EXR_PATH_LINE,.points={{8,8}}},{.verb=EXR_PATH_LINE,.points={{0,8}}},{.verb=EXR_PATH_CLOSE}};
    image.interpolate=0;
    OK(exr_canvas_begin_group(c,1,EXR_BLEND_NORMAL,EXR_GROUP_ISOLATED|EXR_GROUP_CMYK,&error));
    OK(exr_canvas_path_cmyk(c,rect,5,NULL,&style,base,base,&error));
    OK(exr_canvas_blend(c,EXR_BLEND_MULTIPLY,&error));OK(exr_canvas_image_cmyk(c,&image,&inks,matrix,.5,&error));
    OK(exr_canvas_end_layer(c,1,&error));OK(exr_canvas_take(c,&b,&error));
    for(scenario=0;scenario<2;scenario++) {
      double values[4];unsigned expected[3];
      for(k=0;k<4;k++) { double s=raw[scenario*4+k]/255.;values[k]=base[k]+.5*s*(1-base[k]); }
      cmyk_reference(values,expected);
      for(k=0;k<3;k++) CHECK(abs((int)b.pixels[4*b.stride+(scenario ? 6 : 1)*4+k]-(int)expected[k])<=2);
      if(!scenario) memcpy(first,expected,sizeof(first));else CHECK(memcmp(first,expected,sizeof(first))!=0);
    }
    exr_bitmap_free(&b);exr_canvas_free(c);
  }
  for(scenario=0;scenario<5;scenario++) {
    exr_canvas *c=canvas(NULL);exr_bitmap bad=inks,b={0};exr_image_layer copy=image;
    if(scenario==0) bad.width=3;
    if(scenario==1) bad.stride=7;
    if(scenario==2) bad.channels=1;
    if(scenario==3) { copy.mask=&copy;copy.mask_mode=EXR_MASK_ALPHA; }
    if(scenario==4) copy.has_matte=1;
    CHECK(exr_canvas_image_cmyk(c,&copy,&bad,matrix,1,&error)==EXR_ARGUMENT);
    CHECK(exr_canvas_take(c,&b,&error)==EXR_ARGUMENT && !b.pixels);exr_canvas_free(c);
  }
  { int stop=0;exr_canvas *c=canvas(&stop);exr_bitmap b={0};stop=1;
    CHECK(exr_canvas_image_cmyk(c,&image,&inks,matrix,1,&error)==EXR_CANCELLED);
    CHECK(exr_canvas_take(c,&b,&error)==EXR_CANCELLED && !b.pixels);exr_canvas_free(c); }
  /* Old sink storage ends exactly where the optional extension begins. */
  { exr_canvas *c=canvas(NULL);size_t i;union { exr_draw_sink_ex aligned;unsigned char bytes[sizeof(exr_draw_sink_ex)+8]; } storage;
    exr_draw_sink_ex *sink=&storage.aligned;
    memset(&storage,0xa5,sizeof(storage));sink->struct_size=offsetof(exr_draw_sink_ex,image_cmyk);
    OK(exr_canvas_get_sink_ex(c,sink,&error));for(i=offsetof(exr_draw_sink_ex,image_cmyk);i<sizeof(storage);i++) CHECK(storage.bytes[i]==0xa5);
    exr_canvas_free(c); }
}
int main(int argc,char **argv) {
  CHECK(argc==2);directory=argv[1];pdf_scenes();canvas_scenes();
  printf("%u native ink checks; max reference difference %u; legacy round-trip difference %u\n",checks,max_error,legacy_difference);return 0;
}
