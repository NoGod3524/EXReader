/* SPDX-License-Identifier: MIT */
#include "layout_internal.h"
#include "font_outline_internal.h"
exr_status exr_font_glyph_outline(exr_font *font,size_t index,uint32_t glyph,
                                   exr_path_segment **out,size_t *count,const exr_control *control,exr_error *e) {
  if(out) *out=NULL;
  if(count) *count=0;
  if(!out || !count || !font || index>=font->count || glyph>=(uint64_t)font->faces[index].face->num_glyphs) return exr_fail(e,EXR_ARGUMENT,"Invalid font glyph outline input/output");
  if(font->faces[index].bitmap_only) {
    if(exr_control_cancel(control,e)!=EXR_OK) return EXR_CANCELLED;
    return exr_fail(e,EXR_OK,"");
  }
  return exr_font_outline(font->faces[index].face,glyph,out,count,NULL,control,e);
}
