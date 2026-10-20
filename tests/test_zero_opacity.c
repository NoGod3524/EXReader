/* SPDX-License-Identifier: MIT */
#include "exreader.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static exr_error error;static unsigned checks;
#define CHECK(x) do { checks++;if(!(x)) { fprintf(stderr,"line %d: %s (%d: %s)\n",__LINE__,#x,error.code,error.message);exit(1); } } while(0)
#define OK(x) CHECK((x)==EXR_OK)
static void pdfs(const char *directory) {
  const char *names[]={"path","text","group","shading","soft","explicit","key","compound"};
  unsigned char expected[64][4];char path[4096];FILE *f;unsigned row=0;
  snprintf(path,sizeof(path),"%s/pdf-blend/zero-opacity-oracle.bin",directory);f=fopen(path,"rb");CHECK(f);
  CHECK(fread(expected,1,sizeof(expected),f)==sizeof(expected));CHECK(fgetc(f)==EOF);fclose(f);
  for(unsigned mask_zero=0;mask_zero<2;mask_zero++) for(unsigned isolated=0;isolated<2;isolated++) for(unsigned shape=0;shape<2;shape++) for(unsigned p=0;p<8;p++) {
    exr_fixed_document *doc=NULL;exr_bitmap b={0};exr_fixed_render_options options={0};options.channels=4;
    snprintf(path,sizeof(path),"%s/pdf-blend/zero-%s-%s-%s-%s.pdf",directory,mask_zero ? "mask" : "opacity",isolated ? "iso" : "noniso",shape ? "shape" : "opacity",names[p]);
    OK(exr_fixed_open(path,NULL,&doc,&error));OK(exr_fixed_render(doc,0,1,&options,&b,&error));
    for(unsigned k=0;k<4;k++) {
      unsigned got=b.pixels[8*b.stride+8*4+k];
      if(abs((int)got-expected[row][k])>2) fprintf(stderr,"%s channel %u: %u != %u\n",path,k,got,expected[row][k]);
      CHECK(abs((int)got-expected[row][k])<=2);
    }
    row++;exr_bitmap_free(&b);exr_fixed_free(doc);
  }
}
static void canvas(void) {
  unsigned char pixel[4]={0,0,255,255},zero_mask[4]={0,0,0,0};
  exr_image_layer image={0},mask={0};exr_path_segment path[5]={0};const double matrix[6]={1,0,0,1,0,0};
  for(unsigned i=0;i<4;i++) { path[i].verb=i ? EXR_PATH_LINE : EXR_PATH_MOVE;path[i].points[0]=(exr_path_point){i==1 || i==2 ? 1 : 0,i>=2 ? 1 : 0}; }path[4].verb=EXR_PATH_CLOSE;
  image.bitmap=(exr_bitmap){1,1,4,pixel,4};mask.bitmap=(exr_bitmap){1,1,4,zero_mask,4};
  for(unsigned cmyk=0;cmyk<2;cmyk++) for(unsigned isolated=0;isolated<2;isolated++) for(unsigned nested=0;nested<4;nested++) for(unsigned shape=0;shape<2;shape++) for(unsigned kind=0;kind<6;kind++) {
    exr_canvas *c=NULL;exr_canvas_config config={0};exr_draw_sink_ex sink={0};exr_draw_style style=exr_draw_style_defaults();exr_bitmap b={0};
    config.width=config.height=1;OK(exr_canvas_create(&config,&c,&error));sink.struct_size=sizeof(sink);OK(exr_canvas_get_sink_ex(c,&sink,&error));
    OK(exr_canvas_begin_group(c,1,EXR_BLEND_NORMAL,(isolated ? EXR_GROUP_ISOLATED : 0)|EXR_GROUP_KNOCKOUT|(cmyk ? EXR_GROUP_CMYK : EXR_GROUP_RGB),&error));
    style.fill=0xff0000ff;OK(exr_canvas_path(c,path,5,NULL,&style,&error));
    OK(sink.alpha_source(c,shape ? EXR_ALPHA_CONSTANT_SHAPE : 0,&error));
    if(kind==4) OK(sink.soft_mask(c,zero_mask,1,1,&error));
    if(nested) OK(exr_canvas_begin_group(c,nested==1 ? 0 : 1,EXR_BLEND_NORMAL,(nested==3 ? EXR_GROUP_RGB : (cmyk ? EXR_GROUP_CMYK : EXR_GROUP_RGB))|(nested==2 ? 0 : EXR_GROUP_ISOLATED),&error));
    if(kind==0) { style.fill=nested==1 ? 0x0000ffff : 0x0000ff00;OK(exr_canvas_path(c,path,5,NULL,&style,&error)); }
    else if(kind==1) OK(exr_canvas_image(c,&image,matrix,nested==1 ? 1 : 0,&error));
    else if(kind==2) {
      image.mask=&mask;image.mask_mode=1;OK(sink.alpha_source(c,shape && !nested ? EXR_ALPHA_CONSTANT_SHAPE : 0,&error));
      OK(exr_canvas_image(c,&image,matrix,1,&error));image.mask=NULL;
    } else if(kind==3) { style.flags=EXR_DRAW_FILL|EXR_DRAW_STROKE;style.fill=style.stroke=0;OK(exr_canvas_path(c,path,5,NULL,&style,&error)); }
    else if(kind==4) { style.fill=0x0000ffff;OK(exr_canvas_path(c,path,5,NULL,&style,&error)); }
    else { OK(sink.alpha_source(c,EXR_ALPHA_IMAGE_SHAPE,&error));OK(exr_canvas_image(c,&mask,matrix,1,&error)); }
    if(nested) OK(exr_canvas_end_layer(c,1,&error));
    OK(exr_canvas_end_layer(c,1,&error));OK(exr_canvas_take(c,&b,&error));
    if(kind==5 || (shape && (nested<2 || kind==4))) CHECK(b.pixels[3]==255 && b.pixels[0]>b.pixels[1] && b.pixels[0]>b.pixels[2]);
    else CHECK(!b.pixels[3]);
    exr_bitmap_free(&b);exr_canvas_free(c);
  }
}
int main(int argc,char **argv) { CHECK(argc==2);pdfs(argv[1]);canvas();printf("%u zero-opacity checks passed\n",checks);return 0; }
