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
  CHECK(argc==2 && exr_abi_version()==1 && !strcmp(exr_version(),EXR_VERSION));
  CHECK(exr_text_analyze("abc",3,&boundaries,&e)==EXR_OK && (boundaries[3]&EXR_BOUNDARY_MANDATORY));exr_free(boundaries);
  CHECK(exr_bidi_analyze("abc",3,EXR_DIRECTION_AUTO,&bidi,&e)==EXR_OK);exr_bidi_free(bidi);
  CHECK(exr_document_open_memory(EXR_TXT,"abc",3,&doc,&e)==EXR_OK);
  CHECK(exr_font_open(argv[1],&font,&e)==EXR_OK);
  CHECK(exr_layout_create(doc,font,&options,&layout,&e)==EXR_OK);
  CHECK(exr_layout_pages(layout,&count)!=NULL && count==1);
  CHECK(exr_layout_hit_test(layout,0,options.margin,options.margin)<3);
  CHECK(exr_render_page_color(layout,font,0,&bitmap,&e)==EXR_OK && bitmap.pixels);
  exr_bitmap_free(&bitmap);exr_layout_free(layout);exr_font_free(font);exr_document_free(doc);
  puts("Independent core component passed");return 0;
}
