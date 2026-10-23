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
static int cancel_mask(void *context) { (void)context;return 1; }
static void cmyk_soft_masks(void) {
  /* Two translucent ink sources must blend in CMYK before conversion. The
     independent CMS reference makes RGB blending fail this check. */
  const double a=128./255,total=a+a-a*a;
  unsigned rgb[3],scenario,k;
  for(scenario=0;scenario<10;scenario++) {
    char pdf[8192],row[2048];size_t used=0,offset[9],xref;unsigned id;
    exr_fixed_document *document=NULL;exr_bitmap bitmap={0};exr_fixed_render_options options={0};
    const char *paint="/M gs 1 0 0 rg 0 0 16 16 re f";
    const char *mask="/Half gs 1 0 0 0 k 0 0 16 16 re f 0 1 0 0 k 0 0 16 16 re f";
    const char *group_paint=scenario>=6 ? "/Child Do" : mask;
    const char *bc=scenario==2 ? "/BC [0 0 0 0]" : scenario==3 ? "/BC [1 0 0 0]" : scenario==5 ? "/BC [0 0 0]" : "";
    const char *space=scenario==4 ? "[/CalRGB << /WhitePoint [.95047 1 1.08883] >>]" : "/DeviceCMYK";
    const char *box=scenario==9 ? "[0 16 16 0]" : "[0 0 16 16]";
    double coverage=scenario==8 ? 1 : total,expected=coverage;
#define APPEND(text) do { size_t length=strlen(text);CHECK(length<sizeof(pdf)-used);memcpy(pdf+used,text,length);used+=length; } while(0)
    APPEND("%PDF-1.7\n");
    for(id=1;id<=8;id++) {
      offset[id]=used;snprintf(row,sizeof(row),"%u 0 obj\n",id);APPEND(row);
      switch(id) {
        case 1: APPEND("<< /Type /Catalog /Pages 2 0 R >>");break;
        case 2: APPEND("<< /Type /Pages /Count 1 /Kids [3 0 R] >>");break;
        case 3: APPEND("<< /Type /Page /Parent 2 0 R /MediaBox [0 0 16 16] /Contents 4 0 R /Resources << /ExtGState << /M << /SMask 6 0 R >> >> >> >>");break;
        case 4: snprintf(row,sizeof(row),"<< /Length %zu >>\nstream\n%s\nendstream",strlen(paint),paint);APPEND(row);break;
        case 5:
          snprintf(row,sizeof(row),"<< /Type /XObject /Subtype /Form /BBox %s /Group << /S /Transparency /I true /CS %s >> /Resources << /ExtGState << /Half 7 0 R >> /XObject << /Child 8 0 R >> >> /Length %zu >>\nstream\n%s\nendstream",box,space,strlen(group_paint),group_paint);APPEND(row);break;
        case 6: snprintf(row,sizeof(row),"<< /S /%s /G 5 0 R %s >>",scenario ? "Luminosity" : "Alpha",bc);APPEND(row);break;
        case 7: APPEND(scenario==8 ? "<< /ca 1 >>" : "<< /ca .5 >>");break;
        case 8:
          snprintf(row,sizeof(row),"<< /Type /XObject /Subtype /Form /BBox [0 0 16 16] /Group << /S /Transparency /I false /CS /%s >> /Length %zu >>\nstream\n%s\nendstream",scenario==7 ? "DeviceRGB" : "DeviceCMYK",strlen(mask),mask);APPEND(row);break;
      }
      APPEND("\nendobj\n");
    }
    xref=used;APPEND("xref\n0 9\n0000000000 65535 f \n");
    for(id=1;id<=8;id++) { snprintf(row,sizeof(row),"%010zu 00000 n \n",offset[id]);APPEND(row); }
    snprintf(row,sizeof(row),"trailer\n<< /Size 9 /Root 1 0 R >>\nstartxref\n%zu\n%%%%EOF\n",xref);APPEND(row);
#undef APPEND
    OK(exr_fixed_open_memory(EXR_PDF,pdf,used,NULL,&document,&error));options.channels=4;
    if(scenario==4 || scenario==5 || scenario==7) CHECK(exr_fixed_render(document,0,1,&options,&bitmap,&error)==(scenario==4 ? EXR_UNSUPPORTED : EXR_FORMAT) && !bitmap.pixels);
    else {
      const unsigned char *p;
      OK(exr_fixed_render(document,0,1,&options,&bitmap,&error));p=bitmap.pixels+8*bitmap.stride+8*4;
      if(scenario) {
        const double source[4]={scenario==8 ? 0 : a*(1-a)/total,scenario==8 ? 1 : a/total,0,0};
        const double back[4]={scenario==3 ? 1 : 0,0,0,(scenario==1 || scenario>=6) ? 1 : 0};
        double inks[4];
        /* Composite in the declared ink space before the nonlinear CMS. */
        for(k=0;k<4;k++) inks[k]=source[k]*coverage+back[k]*(1-coverage);
        cmyk_reference(inks,rgb);
        expected=(.3*rgb[0]+.59*rgb[1]+.11*rgb[2])/255;
      }
      CHECK(p[0]==255 && p[1]==0 && p[2]==0);
      CHECK(abs((int)p[3]-(int)floor(expected*255+.5))<=2);
      for(k=0;k<4;k++) CHECK(bitmap.pixels[k]==p[k]);
    }
    exr_bitmap_free(&bitmap);
    if(scenario==1) {
      options.mask_budget=1;
      CHECK(exr_fixed_render(document,0,1,&options,&bitmap,&error)==EXR_LIMIT && !bitmap.pixels);
      options.mask_budget=0;options.control.cancelled=cancel_mask;
      CHECK(exr_fixed_render(document,0,1,&options,&bitmap,&error)==EXR_CANCELLED && !bitmap.pixels);
    }
    exr_fixed_free(document);
  }
}
int main(int argc,char **argv) {
  exr_bitmap page; const unsigned char *p;
  CHECK(argc==2); directory=argv[1];
  group_flags();mixed_groups();rejected_groups();canvas_boundaries();cmyk_soft_masks();
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
