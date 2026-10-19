/* SPDX-License-Identifier: MIT */
/* DeviceCMYK transparency groups blend four device components and convert the
   result back with the page model. Two half-transparent fills of rich black and
   white are the smallest case where that differs from RGB compositing. */
#include "exreader.h"
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "cmyk_reference.h"
#include <math.h>
static unsigned checks; static exr_error error;
#define CHECK(x) do { checks++; if(!(x)) { fprintf(stderr,"line %d: %s (%d: %s)\n",__LINE__,#x,error.code,error.message); exit(1); } } while(0)
#define OK(x) CHECK((x)==EXR_OK)
static exr_path_segment square[5];
static void rectangle(double x,double y,double w,double h) {
  memset(square,0,sizeof(square));
  square[0].verb=EXR_PATH_MOVE;square[0].points[0]=(exr_path_point){x,y};
  square[1].verb=EXR_PATH_LINE;square[1].points[0]=(exr_path_point){x+w,y};
  square[2].verb=EXR_PATH_LINE;square[2].points[0]=(exr_path_point){x+w,y+h};
  square[3].verb=EXR_PATH_LINE;square[3].points[0]=(exr_path_point){x,y+h};
  square[4].verb=EXR_PATH_CLOSE;
}
static exr_draw_style square_style(unsigned flags,uint32_t color) {
  exr_draw_style style=exr_draw_style_defaults();
  style.flags=flags;style.fill=color;style.stroke=color;style.rule=EXR_FILL_NONZERO;
  return style;
}
static exr_canvas *canvas(void) {
  exr_canvas_config config={0};exr_canvas *c=NULL;
  config.width=8;config.height=8;config.channels=4;config.background=0xffffffff;
  OK(exr_canvas_create(&config,&c,&error));
  return c;
}
static void fill_cmyk(exr_canvas *c,const double fill[4],uint32_t rgba) {
  exr_draw_style style=square_style(EXR_DRAW_FILL,rgba);
  OK(exr_canvas_path_cmyk(c,square,sizeof(square)/sizeof(*square),NULL,&style,fill,fill,&error));
}
static void knockout_edges(void) {
  unsigned space,image,nested,opaque,corner,k;
  for(space=0;space<2;space++) for(image=0;image<2;image++) for(nested=0;nested<3;nested++) for(opaque=0;opaque<2;opaque++) for(corner=0;corner<2;corner++) {
    exr_canvas *c=canvas();exr_bitmap b={0};exr_draw_style style=square_style(EXR_DRAW_FILL,0xff0000ff);
    const double red[4]={0,1,1,0},blue[4]={1,1,0,0};double alpha=opaque ? 1 : 128/255.,shape=corner ? .25 : .5,total=1-shape+shape*alpha;
    unsigned expected[3];const unsigned char *p;
    OK(exr_canvas_begin_group(c,1,EXR_BLEND_NORMAL,EXR_GROUP_ISOLATED|EXR_GROUP_KNOCKOUT|(space ? EXR_GROUP_CMYK : EXR_GROUP_RGB),&error));
    rectangle(0,0,8,8);
    if(space) fill_cmyk(c,red,style.fill);else OK(exr_canvas_path(c,square,5,NULL,&style,&error));
    if(nested) OK(exr_canvas_begin_group(c,1,EXR_BLEND_NORMAL,nested==1 ? EXR_GROUP_ISOLATED : 0,&error));
    if(image) {
      unsigned char rgba[4]={0,0,255,255},ink_bytes[4]={255,255,0,0};
      exr_image_layer layer={0};exr_bitmap inks={1,1,4,ink_bytes,4};double matrix[6]={4.5,0,0,corner ? 4.5 : 8,0,0};
      layer.bitmap=(exr_bitmap){1,1,4,rgba,4};
      if(space) OK(exr_canvas_image_cmyk(c,&layer,&inks,matrix,alpha,&error));
      else OK(exr_canvas_image(c,&layer,matrix,alpha,&error));
    } else {
      rectangle(0,0,4.5,corner ? 4.5 : 8);style.fill=0x0000ff00|(opaque ? 255 : 128);
      if(space) fill_cmyk(c,blue,style.fill);else OK(exr_canvas_path(c,square,5,NULL,&style,&error));
    }
    if(nested) OK(exr_canvas_end_layer(c,1,&error));
    OK(exr_canvas_end_layer(c,1,&error));OK(exr_canvas_take(c,&b,&error));exr_canvas_free(c);
    if(space) {
      double ink[4];for(k=0;k<4;k++) ink[k]=((1-shape)*red[k]+shape*alpha*blue[k])/total;
      cmyk_reference(ink,expected);
      for(k=0;k<3;k++) expected[k]=(unsigned)floor(total*expected[k]+(1-total)*255+.5);
    } else {
      expected[0]=(unsigned)floor((1-shape*alpha)*255+.5);
      expected[1]=(unsigned)floor((1-total)*255+.5);expected[2]=(unsigned)floor(shape*255+.5);
    }
    p=b.pixels+4*b.stride+4*4;
    for(k=0;k<3;k++) { if(abs((int)p[k]-(int)expected[k])>2) fprintf(stderr,"space %u image %u nested %u opaque %u corner %u channel %u got %u want %u\n",space,image,nested,opaque,corner,k,p[k],expected[k]);CHECK(abs((int)p[k]-(int)expected[k])<=2); }
    CHECK(p[3]==255);exr_bitmap_free(&b);
  }
  rectangle(0,0,8,8);
}
int main(void) {
  exr_bitmap out={0};const unsigned char *p;exr_canvas *c;
  knockout_edges();rectangle(0,0,8,8);
  /* Rich black (C=M=Y=1, K=1) blends with white differently in CMYK space:
     the CMYK result is (0.333,0.333,0,0.333) over 0.75 alpha, i.e. (128,128,191)
     over white, where RGB compositing would give (191,191,191). */
  c=canvas();
  OK(exr_canvas_begin_group(c,1.0,EXR_BLEND_NORMAL,EXR_GROUP_ISOLATED|EXR_GROUP_CMYK,&error));
  { const double rich[4]={1,1,0,1},white[4]={0,0,0,0};
    fill_cmyk(c,rich,0x00000080);
    fill_cmyk(c,white,0xffffff80); }
  OK(exr_canvas_end_layer(c,1,&error));
  OK(exr_canvas_take(c,&out,&error));exr_canvas_free(c);
  CHECK(out.width==8 && out.height==8 && out.channels==4);
  p=out.pixels+4*out.stride+4*4;
  { unsigned expected[3],k;double a=128/255.,total=a+a-a*a,v=(a*(1-a))/total;
    cmyk_reference((const double[4]){v,v,0,v},expected);
    for(k=0;k<3;k++) CHECK(abs((int)p[k]-(int)floor(total*expected[k]+(1-total)*255+.5))<=2); }
  CHECK(p[2]>p[0]+10);   /* visibly not the RGB-composited grey */
  exr_bitmap_free(&out);

  /* Outside a CMYK group the same paint converts to device RGB (rich black). */
  c=canvas();
  { const double rich[4]={1,1,0,1};fill_cmyk(c,rich,0x000000ff); }
  OK(exr_canvas_take(c,&out,&error));exr_canvas_free(c);
  p=out.pixels+4*out.stride+4*4;
  { unsigned expected[3],k;cmyk_reference((const double[4]){1,1,0,1},expected);for(k=0;k<3;k++) CHECK(abs((int)p[k]-(int)expected[k])<=1);CHECK(p[3]==255); }
  exr_bitmap_free(&out);

  /* Nested CMYK groups inherit the blend space; mixed-device and
     non-separable paints are refused. */
  c=canvas();
  OK(exr_canvas_begin_group(c,1.0,EXR_BLEND_NORMAL,EXR_GROUP_CMYK,&error));
  OK(exr_canvas_begin_group(c,1.0,EXR_BLEND_NORMAL,EXR_GROUP_CMYK,&error));
  { const double rich[4]={1,1,0,1};fill_cmyk(c,rich,0x000000ff); }
  OK(exr_canvas_end_layer(c,1,&error));
  OK(exr_canvas_end_layer(c,1,&error));
  OK(exr_canvas_take(c,&out,&error));exr_canvas_free(c);
  p=out.pixels+4*out.stride+4*4;
  { unsigned expected[3],k;cmyk_reference((const double[4]){1,1,0,1},expected);for(k=0;k<3;k++) CHECK(abs((int)p[k]-(int)expected[k])<=1);CHECK(p[3]==255); }
  exr_bitmap_free(&out);
  c=canvas();
  OK(exr_canvas_begin_group(c,1.0,EXR_BLEND_NORMAL,EXR_GROUP_CMYK,&error));
  OK(exr_canvas_blend(c,EXR_BLEND_HUE,&error));
  exr_canvas_free(c);
  /* Compound fill+stroke is one CMYK element and still paints. */
  c=canvas();
  OK(exr_canvas_begin_group(c,1.0,EXR_BLEND_NORMAL,EXR_GROUP_CMYK,&error));
  { exr_draw_style style=square_style(EXR_DRAW_FILL|EXR_DRAW_STROKE,0x000000ff);
    const double rich[4]={1,1,0,1};
    OK(exr_canvas_path_cmyk(c,square,sizeof(square)/sizeof(*square),NULL,&style,rich,rich,&error)); }
  OK(exr_canvas_end_layer(c,1,&error));
  OK(exr_canvas_take(c,&out,&error));exr_canvas_free(c);
  p=out.pixels+4*out.stride+4*4;
  { unsigned expected[3],k;cmyk_reference((const double[4]){1,1,0,1},expected);for(k=0;k<3;k++) CHECK(abs((int)p[k]-(int)expected[k])<=1); }
  exr_bitmap_free(&out);
  printf("%u native canvas CMYK group checks passed\n",checks);
  return 0;
}
