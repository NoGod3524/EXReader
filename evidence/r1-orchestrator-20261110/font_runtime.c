#include "font_internal.h"
#include <exr/render.h>
#include <exr/formats.h>
#include <stdio.h>
#define CHECK(x) do { if (!(x)) { fprintf(stderr,"line %d: %s (%s)\n",__LINE__,#x,error.message); return 1; } } while (0)
int main(int argc,char **argv) {
  exr_font *font=NULL; exr_document *doc=NULL; exr_layout *layout=NULL;
  exr_error error={0}; exr_bitmap bitmap={0};
  exr_layout_config config=exr_layout_config_defaults();
  struct exr_glyph_cache *cache;
  CHECK(argc==2 && exr_font_open(argv[1],&font,&error)==EXR_OK);
  CHECK(!font->raster_cache);
  CHECK(exr_document_open_memory(EXR_TXT,"ABC ABC",7,&doc,&error)==EXR_OK);
  CHECK(exr_layout_create_ex(doc,font,&config,&layout,&error)==EXR_OK);
  CHECK(exr_render_page_color(layout,font,0,&bitmap,&error)==EXR_OK);
  exr_bitmap_free(&bitmap);cache=font->raster_cache;CHECK(cache);
  CHECK(exr_render_page_color(layout,font,0,&bitmap,&error)==EXR_OK);
  CHECK(font->raster_cache==cache);
  puts("PASS: raster_cache initialized by raster.c, retained on second render");
  exr_bitmap_free(&bitmap);exr_layout_free(layout);exr_document_free(doc);exr_font_free(font);
  return 0;
}
