/* SPDX-License-Identifier: GPL-3.0-only */
/* DeviceCMYK transparency groups blend four device components and convert the
   result back with the page model. Two half-transparent fills of rich black and
   white are the smallest case where that differs from RGB compositing. */
#include "exreader.h"
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
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
int main(void) {
  exr_bitmap out={0};const unsigned char *p;exr_canvas *c;
  rectangle(0,0,8,8);
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
  CHECK(abs((int)p[0]-128)<=2 && abs((int)p[1]-128)<=2 && abs((int)p[2]-191)<=2);
  CHECK(p[2]>p[0]+40);   /* visibly not the RGB-composited grey */
  exr_bitmap_free(&out);

  /* Outside a CMYK group the same paint converts to device RGB (rich black). */
  c=canvas();
  { const double rich[4]={1,1,0,1};fill_cmyk(c,rich,0x000000ff); }
  OK(exr_canvas_take(c,&out,&error));exr_canvas_free(c);
  p=out.pixels+4*out.stride+4*4;
  CHECK(p[0]==0 && p[1]==0 && p[2]==0 && p[3]==255);
  exr_bitmap_free(&out);

  /* Nested, mixed-device, compound and non-separable paints are refused. */
  c=canvas();
  OK(exr_canvas_begin_group(c,1.0,EXR_BLEND_NORMAL,EXR_GROUP_CMYK,&error));
  CHECK(exr_canvas_begin_group(c,1.0,EXR_BLEND_NORMAL,EXR_GROUP_CMYK,&error)==EXR_UNSUPPORTED);
  exr_canvas_free(c);
  c=canvas();
  OK(exr_canvas_begin_group(c,1.0,EXR_BLEND_NORMAL,EXR_GROUP_CMYK,&error));
  CHECK(exr_canvas_blend(c,EXR_BLEND_HUE,&error)==EXR_UNSUPPORTED);
  exr_canvas_free(c);
  c=canvas();
  OK(exr_canvas_begin_group(c,1.0,EXR_BLEND_NORMAL,EXR_GROUP_CMYK,&error));
  { exr_draw_style style=square_style(EXR_DRAW_FILL|EXR_DRAW_STROKE,0x00000080);
    const double rich[4]={1,1,0,1};
    CHECK(exr_canvas_path_cmyk(c,square,sizeof(square)/sizeof(*square),NULL,&style,rich,rich,&error)==EXR_UNSUPPORTED); }
  exr_canvas_free(c);
  printf("%u native canvas CMYK group checks passed\n",checks);
  return 0;
}
