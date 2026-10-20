/* SPDX-License-Identifier: MIT */
#include "exr/core.h"
#include <stdio.h>
#include <string.h>
#if defined(EXR_AUDIO_H) || defined(EXR_LIBRARY_H) || defined(EXR_PDF_H) || defined(EXR_TEXTINDEX_H)
#error Core headers must not include optional components
#endif
#define CHECK(x) do { if(!(x)) { fprintf(stderr,"line %d: %s (%s)\n",__LINE__,#x,e.message);return 1; } } while(0)
int main(int argc,char **argv) {
  exr_error e={0};exr_document *doc=NULL;exr_font *font=NULL;exr_layout *layout=NULL;
  exr_bitmap bitmap={0};exr_bidi *bidi=NULL;unsigned char *boundaries=NULL;size_t count=0;
  exr_layout_options options=exr_layout_defaults();
  CHECK((argc==2 || argc==3) && exr_abi_version()==1 && !strcmp(exr_version(),EXR_VERSION));
  CHECK(exr_text_analyze("abc",3,&boundaries,&e)==EXR_OK && (boundaries[3]&EXR_BOUNDARY_MANDATORY));exr_free(boundaries);
  CHECK(exr_bidi_analyze("abc",3,EXR_DIRECTION_AUTO,&bidi,&e)==EXR_OK);exr_bidi_free(bidi);
  CHECK(exr_document_open_memory(EXR_TXT,"abc",3,&doc,&e)==EXR_OK);
  { void *text=NULL;size_t size=0;
    CHECK(exr_document_export_control(doc,EXR_TXT,NULL,&text,&size,&e)==EXR_OK && size==3);
    exr_free(text);
  }
  CHECK(exr_font_open(argv[1],&font,&e)==EXR_OK);
  { exr_font_color_info info={0};info.struct_size=sizeof(info);
    CHECK(exr_font_color_info_get(font,0,0,&info,NULL,&e)==EXR_OK && info.kind==EXR_FONT_COLOR_NONE);
  }
  CHECK(exr_layout_create(doc,font,&options,&layout,&e)==EXR_OK);
  CHECK(exr_layout_pages(layout,&count)!=NULL && count==1);
  CHECK(exr_layout_hit_test(layout,0,options.margin,options.margin)<3);
  CHECK(exr_render_page_color(layout,font,0,&bitmap,&e)==EXR_OK && bitmap.pixels);
  exr_bitmap_free(&bitmap);exr_layout_free(layout);exr_font_free(font);exr_document_free(doc);
  if(argc==3 && argv[2][0]) {
    exr_font_color_info info={0};info.struct_size=sizeof(info);
    CHECK(exr_font_open(argv[2],&font,&e)==EXR_OK);
    CHECK(exr_font_color_info_get(font,0,7,&info,NULL,&e)==EXR_OK && info.kind==EXR_FONT_COLOR_COLR_V1);
    exr_font_free(font);
  }
  { exr_canvas_config config={0};exr_canvas *c=NULL;exr_draw_sink_ex sink={0};exr_image_layer image={0};
    unsigned char rgba[4]={17,34,51,255},raw[4]={0,0,0,0};
    const double matrix[6]={1,0,0,1,0,0};exr_bitmap inks={.width=1,.height=1,.stride=4,.pixels=raw,.channels=4};
    config.width=config.height=1;image.bitmap=inks;image.bitmap.pixels=rgba;
    CHECK(exr_canvas_create(&config,&c,&e)==EXR_OK);sink.struct_size=sizeof(sink);
    CHECK(exr_canvas_get_sink_ex(c,&sink,&e)==EXR_OK && sink.image_cmyk && sink.image_space);
    CHECK(sink.image_space(c)==EXR_GROUP_RGB);
    CHECK(exr_canvas_image_cmyk(c,&image,&inks,matrix,1,&e)==EXR_OK);
    CHECK(exr_canvas_take(c,&bitmap,&e)==EXR_OK && bitmap.pixels[0]==17 && bitmap.pixels[3]==255);
    exr_bitmap_free(&bitmap);exr_canvas_free(c);
  }
  puts("Independent core component passed");return 0;
}
