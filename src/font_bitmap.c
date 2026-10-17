/* SPDX-License-Identifier: GPL-3.0-only */
#include "layout_internal.h"
#include "vector_internal.h"
#include FT_TRUETYPE_TABLES_H
#include FT_OUTLINE_H
#define SBIX FT_MAKE_TAG('s','b','i','x')
typedef struct { uint32_t at,end,order; unsigned ppem,ppi; } bitmap_strike;
struct exr_sbix { FT_ULong size; unsigned flags,count; bitmap_strike strikes[]; };
static unsigned be16(const unsigned char *p) { return (unsigned)p[0]<<8|p[1]; }
static uint32_t be32(const unsigned char *p) { return (uint32_t)be16(p)<<16|be16(p+2); }
static int signed16(const unsigned char *p) { unsigned n=be16(p); return n<32768 ? (int)n : (int)n-65536; }
static exr_status field(exr_face *face,FT_ULong size,FT_ULong offset,void *out,size_t n,size_t *work,const exr_control *control,exr_error *error) {
  FT_ULong length=(FT_ULong)n;
  if(offset>size || n>size-offset) return exr_fail(error,EXR_FONT,"sbix field exceeds table");
  if(!exr_vector_work(work,n)) return exr_fail(error,EXR_LIMIT,"Font bitmap read/work budget exceeded");
  if(exr_control_cancel(control,error)!=EXR_OK) return EXR_CANCELLED;
  if(!n) return EXR_OK;
  if(FT_Load_Sfnt_Table(face->face,SBIX,(FT_Long)offset,out,&length) || length!=n) return exr_fail(error,EXR_FONT,"Cannot read sbix field");
  return EXR_OK;
}
static int strike_order(const void *a,const void *b) {
  const bitmap_strike *x=a,*y=b; return x->at<y->at ? -1 : x->at>y->at ? 1 : x->order<y->order ? -1 : x->order>y->order;
}
void exr_font_sbix_free(exr_face *face) { free(face->sbix); face->sbix=NULL; face->sbix_checked=0; }
static exr_status directory(exr_face *face,size_t *work,const exr_control *control,exr_error *error) {
  FT_ULong size=0; FT_Error code; struct exr_sbix *table=NULL; unsigned char header[8],offsets[1024];
  unsigned count,i,j; uint64_t minimum; exr_status status;
  if(face->sbix_checked) return EXR_OK;
  code=FT_Load_Sfnt_Table(face->face,SBIX,0,NULL,&size);
  if(code==FT_Err_Table_Missing || code==FT_Err_Invalid_Face_Handle || code==FT_Err_Invalid_Argument) { face->sbix_checked=1; return EXR_OK; }
  if(code || size>UINT32_MAX) return exr_fail(error,EXR_FONT,"Cannot locate sbix table");
  status=field(face,size,0,header,8,work,control,error); if(status!=EXR_OK) return status;
  if(be16(header)!=1 || !(be16(header+2)&1) || (be16(header+2)&~3u)) return exr_fail(error,EXR_FONT,"Unsupported sbix version/flags");
  count=be32(header+4); if(count>256) return exr_fail(error,EXR_LIMIT,"sbix exceeds 256 strikes");
  status=field(face,size,8,offsets,4*count,work,control,error); if(status!=EXR_OK) return status;
  table=calloc(1,sizeof(*table)+count*sizeof(*table->strikes)); if(!table) return exr_fail(error,EXR_MEMORY,"sbix strike allocation failed");
  table->size=size; table->flags=be16(header+2); table->count=count;
  minimum=4+((uint64_t)face->face->num_glyphs+1)*4;
  for(i=0;i<count;i++) table->strikes[i]=(bitmap_strike){be32(offsets+4*i),(uint32_t)size,i,0,0};
  qsort(table->strikes,count,sizeof(*table->strikes),strike_order);
  for(i=0;i<count;i++) {
    bitmap_strike *strike=table->strikes+i;
    for(j=i+1;j<count;j++) if(table->strikes[j].at>strike->at) { strike->end=table->strikes[j].at; break; }
    if(strike->at<8+4*count || strike->at>strike->end || minimum>strike->end-strike->at) { status=exr_fail(error,EXR_FONT,"Invalid sbix strike boundaries"); goto done; }
    status=field(face,size,strike->at,header,4,work,control,error); if(status!=EXR_OK) goto done;
    strike->ppem=be16(header); strike->ppi=be16(header+2);
    if(!strike->ppem) { status=exr_fail(error,EXR_FONT,"Zero sbix strike size"); goto done; }
  }
  face->sbix=table; face->sbix_checked=1; return EXR_OK;
done:
  free(table); return status;
}
static exr_status span(exr_face *face,const bitmap_strike *strike,uint32_t glyph,uint32_t *begin,uint32_t *end,size_t *work,const exr_control *control,exr_error *error) {
  unsigned char bytes[8]; uint64_t minimum=4+((uint64_t)face->face->num_glyphs+1)*4;
  exr_status status=field(face,face->sbix->size,strike->at+4+(FT_ULong)glyph*4,bytes,8,work,control,error);
  if(status!=EXR_OK) return status;
  *begin=be32(bytes); *end=be32(bytes+4);
  if(*begin>*end || *end>strike->end-strike->at || (*begin!=*end && (*begin<minimum || *end-*begin<8))) return exr_fail(error,EXR_FONT,"Invalid sbix glyph boundaries");
  return EXR_OK;
}
exr_status exr_font_sbix_image(exr_face *face,uint32_t glyph,float pixels,exr_glyph_image *out,size_t *work,const exr_control *control,exr_error *error) {
  const bitmap_strike *selected=NULL; uint32_t begin=0,end=0,chosen_begin=0,chosen_end=0,active[16]; unsigned i,depth=0;
  unsigned char header[8],*encoded=NULL; int x,y; uint32_t original=glyph; exr_status status; double left=0,bottom=0,scale;
  memset(out,0,sizeof(*out));
  status=directory(face,work,control,error); if(status!=EXR_OK || !face->sbix) return status;
  for(i=0;i<face->sbix->count;i++) {
    const bitmap_strike *strike=face->sbix->strikes+i;
    status=span(face,strike,glyph,&begin,&end,work,control,error); if(status!=EXR_OK) return status;
    if(begin==end) continue;
    if(!selected || (strike->ppem>=pixels && (selected->ppem<pixels || strike->ppem<selected->ppem)) ||
       (strike->ppem<pixels && selected->ppem<pixels && strike->ppem>selected->ppem) ||
       (strike->ppem==selected->ppem && strike->order<selected->order)) { selected=strike; chosen_begin=begin; chosen_end=end; }
  }
  if(!selected) return EXR_OK;
  begin=chosen_begin; end=chosen_end;
  for(;;) {
    uint32_t type;
    if(depth==16) return exr_fail(error,EXR_LIMIT,"sbix duplicate depth exceeds 16");
    for(i=0;i<depth;i++) if(active[i]==glyph) return exr_fail(error,EXR_FONT,"Cyclic sbix duplicate glyph");
    active[depth++]=glyph;
    status=field(face,face->sbix->size,selected->at+begin,header,8,work,control,error); if(status!=EXR_OK) return status;
    x=signed16(header); y=signed16(header+2); type=be32(header+4);
    if(type!=FT_MAKE_TAG('d','u','p','e')) break;
    if(end-begin!=10) return exr_fail(error,EXR_FONT,"Invalid sbix duplicate record");
    status=field(face,face->sbix->size,selected->at+begin+8,header,2,work,control,error); if(status!=EXR_OK) return status;
    glyph=be16(header); if(glyph>=(uint64_t)face->face->num_glyphs) return exr_fail(error,EXR_FONT,"Invalid sbix duplicate glyph ID");
    status=span(face,selected,glyph,&begin,&end,work,control,error); if(status!=EXR_OK) return status;
    if(begin==end) return exr_fail(error,EXR_FONT,"sbix duplicate references an absent image");
  }
  if(be32(header+4)!=FT_MAKE_TAG('p','n','g',' ') && be32(header+4)!=FT_MAKE_TAG('j','p','g',' ')) return exr_fail(error,EXR_FORMAT,"Unsupported sbix image encoding");
  if(end-begin-8>32*1024*1024) return exr_fail(error,EXR_LIMIT,"sbix encoded image exceeds 32 MiB");
  encoded=malloc(end-begin-8 ? end-begin-8 : 1); if(!encoded) return exr_fail(error,EXR_MEMORY,"sbix image allocation failed");
  status=field(face,face->sbix->size,selected->at+begin+8,encoded,end-begin-8,work,control,error); if(status!=EXR_OK) goto done;
  if((be32(header+4)==FT_MAKE_TAG('p','n','g',' ') && (end-begin-8<8 || memcmp(encoded,"\x89PNG\r\n\x1a\n",8))) ||
     (be32(header+4)==FT_MAKE_TAG('j','p','g',' ') && (end-begin-8<3 || memcmp(encoded,"\xff\xd8\xff",3)))) { status=exr_fail(error,EXR_FORMAT,"sbix image signature differs from its encoding"); goto done; }
  status=exr_image_decode(encoded,end-begin-8,&out->bitmap,error); if(status!=EXR_OK) goto done;
  if(!exr_vector_work(work,(size_t)out->bitmap.width*out->bitmap.height)) { status=exr_fail(error,EXR_LIMIT,"Font bitmap decode work exceeds budget"); goto done; }
  if(FT_Load_Glyph(face->face,original,FT_LOAD_NO_SCALE|FT_LOAD_NO_HINTING|FT_LOAD_NO_BITMAP)) { status=exr_fail(error,EXR_FONT,"Cannot read bitmap glyph design origin"); goto done; }
  if(face->face->glyph->format==FT_GLYPH_FORMAT_OUTLINE && face->face->glyph->outline.n_contours>0) {
    FT_BBox bounds; FT_Outline_Get_CBox(&face->face->glyph->outline,&bounds);
    left=(double)bounds.xMin*pixels/face->face->units_per_EM; bottom=(double)bounds.yMin*pixels/face->face->units_per_EM;
  }
  scale=(double)pixels/selected->ppem;
  out->scale=(float)scale; out->left=(float)(left+x*scale); out->top=(float)(-bottom-(y+(double)out->bitmap.height)*scale);
  out->flags=(face->sbix->flags&2) ? EXR_GLYPH_IMAGE_OUTLINE_OVERLAY : 0;
  if(out->bitmap.width*scale>8192 || out->bitmap.height*scale>8192 || out->bitmap.width*scale*out->bitmap.height*scale>16*1024*1024 || fabs(out->left)>1e7 || fabs(out->top)>1e7) { status=exr_fail(error,EXR_LIMIT,"Scaled font bitmap exceeds raster limits"); goto done; }
  status=exr_control_cancel(control,error);
done:
  free(encoded); if(status!=EXR_OK) { exr_bitmap_free(&out->bitmap); memset(out,0,sizeof(*out)); } return status;
}
exr_status exr_font_glyph_image(exr_font *font,size_t index,uint32_t glyph,float pixels,exr_glyph_image *out,const exr_control *control,exr_error *error) {
  size_t work=0; exr_status status;
  if(out) memset(out,0,sizeof(*out));
  if(!font || index>=font->count || !out || glyph>=(uint64_t)font->faces[index].face->num_glyphs || !isfinite(pixels) || pixels<1.0f/64 || pixels>4096) return exr_fail(error,EXR_ARGUMENT,"Invalid font glyph-image query");
  if(exr_control_cancel(control,error)!=EXR_OK) return EXR_CANCELLED;
  status=exr_font_sbix_image(font->faces+index,glyph,pixels,out,&work,control,error);
  if(status==EXR_OK && exr_control_cancel(control,error)!=EXR_OK) { exr_bitmap_free(&out->bitmap); memset(out,0,sizeof(*out)); return EXR_CANCELLED; }
  return status==EXR_OK ? exr_fail(error,EXR_OK,"") : status;
}
