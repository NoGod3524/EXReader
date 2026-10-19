/* SPDX-License-Identifier: MIT */
/* Transparency group color spaces: DeviceGray uses luminance, DeviceRGB
   preserves RGB, and DeviceCMYK blends native inks before ICC conversion. */
#include "exreader.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "cmyk_reference.h"
#include <math.h>
static unsigned checks; static exr_error error;
#define CHECK(x) do { checks++; if(!(x)) { fprintf(stderr,"line %d: %s (%d: %s)\n",__LINE__,#x,error.code,error.message); exit(1); } } while(0)
#define OK(x) CHECK((x)==EXR_OK)
static const char *directory;

static exr_bitmap render(const char *name) {
  char path[4096]; exr_fixed_document *d=NULL; exr_bitmap out={0}; exr_fixed_render_options options={0};
  snprintf(path,sizeof(path),"%s/pdf-color/%s",directory,name);
  OK(exr_fixed_open(path,NULL,&d,&error)); CHECK(d);
  options.channels=4; options.background=0xffffffff;
  OK(exr_fixed_render(d,0,1,&options,&out,&error));
  exr_fixed_free(d);
  return out;
}
static void group_flags(void) {
  static const char *names[]={"group-k-true.pdf","group-k-false.pdf","group-k-default.pdf","group-k-null.pdf"};
  static const unsigned expected[][3]={{127,127,255},{127,0,128},{127,0,128},{127,0,128}};
  unsigned i,k;
  for(i=0;i<4;i++) {
    exr_bitmap b=render(names[i]);const unsigned char *p=b.pixels+8*b.stride+8*4;
    for(k=0;k<3;k++) CHECK(abs((int)p[k]-(int)expected[i][k])<=1);
    CHECK(p[3]==255);exr_bitmap_free(&b);
  }
}
/* Separate inverse CMS transform: RGB groups convert once when committing into
   the CMYK parent, whereas inherited groups convert every painted source. */
static void inverse_reference(const double rgb[3],double out[4]) {
  unsigned k;
#ifdef EXR_ENABLE_ICC
  mz_ulong size=961644;unsigned char *raw=malloc((size_t)size);
  cmsHPROFILE cmyk,srgb;cmsHTRANSFORM transform;
  CHECK(raw && mz_uncompress(raw,&size,default_cmyk_data,sizeof(default_cmyk_data))==MZ_OK);
  cmyk=cmsOpenProfileFromMem(raw,(cmsUInt32Number)size);srgb=cmsCreate_sRGBProfile();
  transform=cmsCreateTransform(srgb,TYPE_RGB_DBL,cmyk,TYPE_CMYK_DBL,INTENT_RELATIVE_COLORIMETRIC,
    cmsFLAGS_NOOPTIMIZE|cmsFLAGS_NOCACHE|cmsFLAGS_BLACKPOINTCOMPENSATION);
  CHECK(transform);cmsDoTransform(transform,rgb,out,1);
  for(k=0;k<4;k++) out[k]=fmax(0,fmin(1,out[k]/100));
  cmsDeleteTransform(transform);cmsCloseProfile(cmyk);cmsCloseProfile(srgb);free(raw);
#else
  out[3]=1-fmax(rgb[0],fmax(rgb[1],rgb[2]));
  for(k=0;k<3;k++) out[k]=fmax(0,1-rgb[k]-out[3]);
#endif
}
static void mixed_groups(void) {
  static const char *names[]={"mixed-rgb-form.pdf","mixed-rgb-page.pdf","mixed-rgb-appearance.pdf","mixed-rgb-nested.pdf"};
  const double base[4]={.2,.4,.6,.1},gray[3]={170./255,170./255,170./255};
  double source[4],inks[4];unsigned rgb[3],i,k;
  inverse_reference(gray,source);
  for(k=0;k<4;k++) inks[k]=base[k]*(1-192./255)+source[k]*(192./255);
  cmyk_reference(inks,rgb);
  for(i=0;i<4;i++) {
    exr_bitmap b=render(names[i]);const unsigned char *p=b.pixels+8*b.stride+8*4;
    for(k=0;k<3;k++) CHECK(abs((int)p[k]-(int)rgb[k])<=2);
    CHECK(p[3]==255);exr_bitmap_free(&b);
  }
  /* An omitted /CS deliberately stays in CMYK. */
  { double black[4],white[4],a=128./255;exr_bitmap b;const unsigned char *p;
    inverse_reference((const double[3]){0,0,0},black);inverse_reference((const double[3]){1,1,1},white);
    for(k=0;k<4;k++) inks[k]=(base[k]*(1-a)+black[k]*a)*(1-a)+white[k]*a;
    cmyk_reference(inks,rgb);b=render("mixed-rgb-inherit.pdf");p=b.pixels+8*b.stride+8*4;
    for(k=0;k<3;k++) CHECK(abs((int)p[k]-(int)rgb[k])<=2);
    exr_bitmap_free(&b);
  }
  { exr_bitmap b=render("mixed-rgb-gray-parent.pdf");const unsigned char *p=b.pixels+8*b.stride+8*4;
    double linear=pow((170./255+.055)/1.055,2.4);
    double luminance=1.055*pow(.2126+(.7152+.0722)*linear,1/2.4)-.055;
    unsigned gray_byte=(unsigned)floor(luminance*255+.5);
    unsigned expected=(unsigned)floor(gray_byte*(192./255)+255*(1-192./255)+.5);
    for(k=0;k<3;k++) CHECK(abs((int)p[k]-(int)expected)<=1);
    exr_bitmap_free(&b);
  }
}
static void rejected_groups(void) {
  static const char *names[]={"group-k-bad.pdf","mixed-rgb-nonisolated.pdf","mixed-rgb-bad-space.pdf"};
  static const exr_status want[]={EXR_FORMAT,EXR_FORMAT,EXR_UNSUPPORTED};unsigned i;
  for(i=0;i<3;i++) {
    char path[4096];exr_fixed_document *d=NULL;exr_bitmap b={0};
    snprintf(path,sizeof(path),"%s/pdf-color/%s",directory,names[i]);
    OK(exr_fixed_open(path,NULL,&d,&error));
    CHECK(exr_fixed_render(d,0,1,NULL,&b,&error)==want[i]);CHECK(!b.pixels);exr_fixed_free(d);
  }
}
static void canvas_boundaries(void) {
  const double base[4]={.2,.4,.6,.1},black[4]={0,0,0,1};unsigned scenario,k;
  exr_path_segment rect[5]={ {.verb=EXR_PATH_MOVE,.points={{0,0}}},
    {.verb=EXR_PATH_LINE,.points={{16,0}}}, {.verb=EXR_PATH_LINE,.points={{16,16}}},
    {.verb=EXR_PATH_LINE,.points={{0,16}}}, {.verb=EXR_PATH_CLOSE} };
  for(scenario=0;scenario<6;scenario++) {
    exr_canvas_config cfg={0};exr_canvas *c=NULL;exr_bitmap b={0};exr_draw_style style=exr_draw_style_defaults();
    double source[4],inks[4],alpha=(scenario==3 ? 128./255 : 192./255)*.625;
    double gray=scenario==3 ? 1 : 170./255;unsigned rgb[3];const unsigned char *p;
    cfg.width=cfg.height=16;cfg.channels=4;cfg.background=0xffffffff;
    OK(exr_canvas_create(&cfg,&c,&error));
    OK(exr_canvas_begin_group(c,1,EXR_BLEND_NORMAL,EXR_GROUP_ISOLATED|EXR_GROUP_CMYK|
      (scenario==2 ? EXR_GROUP_KNOCKOUT : 0),&error));
    OK(exr_canvas_path_cmyk(c,rect,5,NULL,&style,base,base,&error));
    if(scenario==5) {
      char path[4096];exr_fixed_document *d=NULL;exr_draw_sink_ex sink={0};alpha=192./255;
      snprintf(path,sizeof(path),"%s/pdf-color/mixed-rgb-appearance-direct.pdf",directory);
      OK(exr_fixed_open(path,NULL,&d,&error));sink.struct_size=sizeof(sink);
      OK(exr_canvas_get_sink_ex(c,&sink,&error));OK(exr_fixed_draw_ex(d,0,NULL,&sink,NULL,&error));exr_fixed_free(d);
    } else {
      OK(exr_canvas_begin_group(c,.625,scenario==1 ? EXR_BLEND_MULTIPLY : EXR_BLEND_NORMAL,
      EXR_GROUP_ISOLATED|EXR_GROUP_RGB|(scenario==3 ? EXR_GROUP_KNOCKOUT : 0),&error));
      style.fill=0x00000080;OK(exr_canvas_path(c,rect,5,NULL,&style,&error));
      style.fill=0xffffff80;OK(exr_canvas_path(c,rect,5,NULL,&style,&error));
      OK(exr_canvas_end_layer(c,scenario!=4,&error));
    }
    /* Native ink painting after the child checks restoration of the parent. */
    rect[1].points[0].x=rect[2].points[0].x=8;style.fill=0x000000ff;
    OK(exr_canvas_path_cmyk(c,rect,5,NULL,&style,black,black,&error));
    rect[1].points[0].x=rect[2].points[0].x=16;
    OK(exr_canvas_end_layer(c,1,&error));OK(exr_canvas_take(c,&b,&error));exr_canvas_free(c);
    inverse_reference((const double[3]){gray,gray,gray},source);
    for(k=0;k<4;k++) {
      double blend=scenario==1 ? base[k]+source[k]-base[k]*source[k] : source[k];
      inks[k]=scenario==4 ? base[k] : scenario==2 ? source[k] : base[k]*(1-alpha)+blend*alpha;
    }
    cmyk_reference(inks,rgb);p=b.pixels+8*b.stride+12*4;
    for(k=0;k<3;k++) {
      double expected=scenario==2 ? rgb[k]*alpha+255*(1-alpha) : rgb[k];
      CHECK(abs((int)p[k]-(int)floor(expected+.5))<=2);
    }
    CHECK(p[3]==255);cmyk_reference(black,rgb);p=b.pixels+8*b.stride+4*4;
    for(k=0;k<3;k++) CHECK(abs((int)p[k]-(int)rgb[k])<=1);
    exr_bitmap_free(&b);
  }
  for(scenario=0;scenario<2;scenario++) {
    exr_canvas_config cfg={0};exr_canvas *c=NULL;cfg.width=cfg.height=1;
    OK(exr_canvas_create(&cfg,&c,&error));
    OK(exr_canvas_begin_group(c,1,EXR_BLEND_NORMAL,EXR_GROUP_ISOLATED|EXR_GROUP_CMYK,&error));
    CHECK(exr_canvas_begin_group(c,1,EXR_BLEND_NORMAL,EXR_GROUP_RGB|
      (scenario ? EXR_GROUP_CMYK : 0),&error)==(scenario ? EXR_ARGUMENT : EXR_UNSUPPORTED));
    /* Failure unwinds the existing group and does not publish partial pixels. */
    CHECK(exr_canvas_end_layer(c,0,&error)!=EXR_OK);CHECK(!exr_canvas_bitmap(c));exr_canvas_free(c);
  }
}
int main(int argc,char **argv) {
  exr_bitmap page; const unsigned char *p;
  CHECK(argc==2); directory=argv[1];
  group_flags();mixed_groups();rejected_groups();canvas_boundaries();
  page=render("groupgray.pdf");
  p=page.pixels+8*page.stride+8*4;
  CHECK(p[0]==p[1] && p[1]==p[2]);          /* grey, not red */
  CHECK(p[0]>=124 && p[0]<=134);            /* MuPDF renders 129 */
  exr_bitmap_free(&page);
  page=render("grouprgb.pdf");
  p=page.pixels+8*page.stride+8*4;
  CHECK(p[0]==255 && p[1]==0 && p[2]==0);   /* RGB group untouched */
  exr_bitmap_free(&page);
  /* Compare the same inks with an independently constructed ICC transform. */
  page=render("groupcmyk.pdf");
  p=page.pixels+8*page.stride+8*4;
  { unsigned rgb[3],k;cmyk_reference((const double[4]){0,1,1,0},rgb);for(k=0;k<3;k++) CHECK(abs((int)p[k]-(int)rgb[k])<=1); }
  exr_bitmap_free(&page);
  /* Translucent rich black then white, both 50%, blended in DeviceCMYK:
     (1/3,1/3,0,1/3) at alpha 0.75. The blue cast checks the ink-space path. */
  page=render("groupcmyk-blend.pdf");
  p=page.pixels+8*page.stride+8*4;
  { unsigned rgb[3],k;double a=.5,total=a+a-a*a,v=a*(1-a)/total;
    cmyk_reference((const double[4]){v,v,0,v},rgb);for(k=0;k<3;k++) CHECK(abs((int)p[k]-(int)floor(total*rgb[k]+(1-total)*255+.5))<=2); }
  CHECK(p[2]>p[0]+10);
  exr_bitmap_free(&page);
  printf("%u native PDF group colour-space checks passed\n",checks);
  return 0;
}
