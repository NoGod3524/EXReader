/* SPDX-License-Identifier: MIT */
#include "layout_internal.h"
#include FT_TRUETYPE_TABLES_H
#include "vector_internal.h"
exr_status exr_font_color_palettes(const exr_font *font,size_t index,size_t *palettes,size_t *entries,exr_error *error) {
  FT_Palette_Data data; FT_ULong size=0; FT_Error code;
  if(palettes) *palettes=0;
  if(entries) *entries=0;
  if(!font || index>=font->count || !palettes || !entries) return exr_fail(error,EXR_ARGUMENT,"Invalid font palette query");
  code=FT_Load_Sfnt_Table(font->faces[index].face,FT_MAKE_TAG('C','P','A','L'),0,NULL,&size);
  if(code==FT_Err_Table_Missing || code==FT_Err_Invalid_Face_Handle || code==FT_Err_Invalid_Argument) return exr_fail(error,EXR_OK,"");
  if(code || FT_Palette_Data_Get(font->faces[index].face,&data)) return exr_fail(error,EXR_FONT,"Cannot read font color palettes");
  *palettes=data.num_palettes; *entries=data.num_palette_entries; return exr_fail(error,EXR_OK,"");
}
exr_status exr_font_colr(exr_face *face,uint32_t glyph,size_t palette_index,uint32_t foreground,exr_font_color_layer layers[256],size_t *count,size_t *work) {
  FT_LayerIterator iterator={0}; FT_UInt layer,color; FT_Palette_Data data; FT_Color *palette=NULL;
  *count=0;
  if(!FT_Get_Color_Glyph_Layer(face->face,glyph,&layer,&color,&iterator)) return EXR_OK;
  if(iterator.num_layers>256) return EXR_LIMIT;
  if(work && !exr_vector_work(work,iterator.num_layers)) return EXR_LIMIT;
  if(FT_Palette_Data_Get(face->face,&data) || palette_index>=data.num_palettes) return EXR_FONT;
  if(!face->palette_ready || face->palette_index!=palette_index) {
    if(work && !exr_vector_work(work,data.num_palette_entries)) return EXR_LIMIT;
    face->palette_ready=0;
    if(FT_Palette_Select(face->face,(FT_UShort)palette_index,&face->color_palette) || !face->color_palette) return EXR_FONT;
    face->palette_index=(unsigned)palette_index; face->palette_ready=1;
  }
  palette=face->color_palette;
  do {
    uint32_t rgba=foreground;
    if(*count==256) return EXR_LIMIT;
    if(color!=0xffff) {
      const FT_Color *c;
      if(color>=data.num_palette_entries) return EXR_FONT;
      c=palette+color;
      rgba=(uint32_t)c->red<<24|(uint32_t)c->green<<16|(uint32_t)c->blue<<8|((c->alpha*(foreground&255)+127)/255);
    }
    layers[(*count)++]=(exr_font_color_layer){layer,rgba};
  } while(FT_Get_Color_Glyph_Layer(face->face,glyph,&layer,&color,&iterator));
  return *count==iterator.num_layers ? EXR_OK : EXR_FONT;
}
exr_status exr_font_color_layers(exr_font *font,size_t index,uint32_t glyph,size_t palette,uint32_t foreground,
                                 exr_font_color_layer **out,size_t *count,const exr_control *control,exr_error *error) {
  exr_font_color_layer layers[256],*copy=NULL; size_t n=0,palettes=0,entries=0; exr_status status;
  if(out) *out=NULL;
  if(count) *count=0;
  if(!font || index>=font->count || !out || !count || glyph>=(uint32_t)font->faces[index].face->num_glyphs) return exr_fail(error,EXR_ARGUMENT,"Invalid font color-layer query");
  if(exr_control_cancel(control,error)!=EXR_OK) return EXR_CANCELLED;
  status=exr_font_color_palettes(font,index,&palettes,&entries,error); if(status!=EXR_OK) return status;
  if(palette>=(palettes ? palettes : 1)) return exr_fail(error,EXR_ARGUMENT,"Font palette index is outside the palette list");
  status=exr_font_colr(font->faces+index,glyph,palette,foreground,layers,&n,NULL);
  if(status!=EXR_OK) return exr_fail(error,status,status==EXR_LIMIT ? "Color glyph exceeds 256 layers" : "Invalid font color layers");
  if(n) {
    copy=malloc(n*sizeof(*copy)); if(!copy) return exr_fail(error,EXR_MEMORY,"Font color-layer allocation failed");
    memcpy(copy,layers,n*sizeof(*copy));
  }
  if(exr_control_cancel(control,error)!=EXR_OK) { free(copy); return EXR_CANCELLED; }
  *out=copy; *count=n; return exr_fail(error,EXR_OK,"");
}
