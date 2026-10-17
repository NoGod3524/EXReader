/* SPDX-License-Identifier: GPL-3.0-only */
#include "pdf_face_internal.h"
#include FT_CID_H
typedef struct { uint32_t cid,glyph; } cid_entry;
struct exr_pdf_face { FT_Face face; FT_Library library; const void *bytes; size_t size; unsigned index;
  exr_pdf_font_kind kind; unsigned flags,composite,dingbats,encoding,standard; cid_entry *cids; size_t count; };
static int compare_cid(const void *a,const void *b) {
  const cid_entry *x=a,*y=b; return x->cid<y->cid ? -1 : x->cid>y->cid ? 1 : x->glyph<y->glyph ? -1 : x->glyph>y->glyph;
}
void exr_pdf_face_close(exr_pdf_face *face) {
  if(face) { if(face->face) FT_Done_Face(face->face); free(face->cids); free(face); }
}
size_t exr_pdf_face_memory(const exr_pdf_face *face) { return face ? sizeof(*face)+face->count*sizeof(*face->cids) : 0; }
int exr_pdf_face_matches(const exr_pdf_face *face,const exr_pdf_font *font,const exr_font_input *fallback) {
  const exr_pdf_font_info *info=exr_pdf_font_description(font);
  if(!face || !info) return 0;
  if(info->program) return face->bytes==info->program && face->size==info->program_size && !face->index;
  return !info->composite && fallback && face->bytes==fallback->data && face->size==fallback->size && face->index==fallback->face_index;
}
static exr_status open_face(FT_Library library,const exr_pdf_font *font,const exr_font_input *fallback,const exr_pdf_face *shared,
                             exr_pdf_face **out,const exr_control *control,exr_error *error) {
  const exr_pdf_font_info *info=exr_pdf_font_description(font); const unsigned char *bytes; size_t size,i; unsigned index=0; exr_pdf_face *face; exr_status status=EXR_OK;
  if(!out) return exr_fail(error,EXR_ARGUMENT,"Missing PDF face output");
  *out=NULL;
  if(!library || !info) return exr_fail(error,EXR_ARGUMENT,"Invalid PDF face input");
  if(exr_control_cancel(control,error)!=EXR_OK) return EXR_CANCELLED;
  bytes=info->program; size=info->program_size;
  if(!bytes) {
    if(info->composite || !fallback || !fallback->data || !fallback->size) return exr_fail(error,EXR_FORMAT,"PDF font requires an embedded or host-provided program");
    if(fallback->face_index>INT_MAX) return exr_fail(error,EXR_ARGUMENT,"Invalid PDF fallback face index");
    bytes=fallback->data; size=fallback->size; index=fallback->face_index;
  }
  if(!size || size>(info->program ? EXR_MAX_TEXT : EXR_MAX_INPUT) || size>LONG_MAX) return exr_fail(error,EXR_LIMIT,"PDF font program exceeds budget");
  if(shared && (shared->library!=library || !exr_pdf_face_matches(shared,font,fallback))) return exr_fail(error,EXR_ARGUMENT,"PDF shared font program does not match");
  face=calloc(1,sizeof(*face)); if(!face) return exr_fail(error,EXR_MEMORY,"PDF face allocation failed"); face->kind=info->kind; face->flags=info->flags; face->composite=info->composite;
  face->library=library; face->bytes=bytes; face->size=size; face->index=index;
  face->dingbats=info->base_name && !strcmp(info->base_name,"ZapfDingbats"); face->encoding=info->encoding_name!=NULL; face->standard=exr_pdf_standard_font(info->base_name);
  if(shared) {
    if(FT_Reference_Face(shared->face)) { status=exr_fail(error,EXR_FORMAT,"Cannot retain shared PDF font program"); goto done; }
    face->face=shared->face;
  } else if(FT_New_Memory_Face(library,bytes,(FT_Long)size,(FT_Long)index,&face->face)) {
    status=exr_fail(error,EXR_FORMAT,"Invalid scalable PDF font program"); goto done;
  }
  if(!FT_IS_SCALABLE(face->face) || !face->face->units_per_EM || face->face->num_glyphs<=0 || face->face->num_glyphs>1048576 || (info->program && face->face->num_faces!=1)) {
    status=exr_fail(error,EXR_FORMAT,"Invalid scalable PDF font program"); goto done;
  }
  if(info->kind==EXR_PDF_CID_TYPE0) {
    FT_Bool keyed=0;
    if(FT_Get_CID_Is_Internally_CID_Keyed(face->face,&keyed) || !keyed) { status=exr_fail(error,EXR_FORMAT,"PDF CID CFF program is not CID-keyed"); goto done; }
    face->count=(size_t)face->face->num_glyphs; face->cids=calloc(face->count,sizeof(*face->cids));
    if(!face->cids) { status=exr_fail(error,EXR_MEMORY,"PDF CID glyph index allocation failed"); goto done; }
    for(i=0;i<face->count;i++) {
      FT_UInt cid;
      if(!(i&255) && (status=exr_control_cancel(control,error))!=EXR_OK) goto done;
      if(FT_Get_CID_From_Glyph_Index(face->face,(FT_UInt)i,&cid) || cid>65535) { status=exr_fail(error,EXR_FORMAT,"Invalid PDF font CID"); goto done; }
      face->cids[i]=(cid_entry){cid,(uint32_t)i};
    }
    qsort(face->cids,face->count,sizeof(*face->cids),compare_cid);
  }
  status=exr_control_cancel(control,error);
done:
  if(status==EXR_OK) { *out=face; if(error) memset(error,0,sizeof(*error)); } else exr_pdf_face_close(face);
  return status;
}
exr_status exr_pdf_face_open(FT_Library library,const exr_pdf_font *font,const exr_font_input *fallback,
                              exr_pdf_face **out,const exr_control *control,exr_error *error) {
  return open_face(library,font,fallback,NULL,out,control,error);
}
exr_status exr_pdf_face_open_shared(FT_Library library,const exr_pdf_font *font,const exr_font_input *fallback,const exr_pdf_face *shared,
                                     exr_pdf_face **out,const exr_control *control,exr_error *error) {
  return open_face(library,font,fallback,shared,out,control,error);
}
static int unicode_scalar(const char *s,size_t n,uint32_t *cp) {
  const unsigned char *p=(const unsigned char *)s; size_t i,bytes; uint32_t value;
  if(!n) return 0;
  bytes=p[0]<0x80 ? 1 : p[0]<0xe0 ? 2 : p[0]<0xf0 ? 3 : 4;
  if(bytes!=n) return 0;
  value=p[0]&(bytes==1 ? 0x7f : bytes==2 ? 31 : bytes==3 ? 15 : 7);
  for(i=1;i<n;i++) value=(value<<6)|(p[i]&63);
  *cp=value; return 1; /* Input is exclusively the validated glyph-name mapper. */
}
exr_status exr_pdf_face_glyph(exr_pdf_face *face,const exr_pdf_character *ch,uint32_t *out,exr_error *error) {
  FT_UInt glyph=0; FT_Face ft; size_t i;
  if(out) *out=0;
  if(!face || !ch || !out) return exr_fail(error,EXR_ARGUMENT,"Missing PDF glyph input/output");
  ft=face->face;
  if(!face->composite && ch->cid>255) return exr_fail(error,EXR_ARGUMENT,"Invalid PDF simple font character code");
  if(face->kind==EXR_PDF_CID_TYPE2) glyph=ch->glyph_known ? ch->glyph : 0;
  else if(face->kind==EXR_PDF_CID_TYPE0) {
    size_t low=0,high=face->count;
    while(low<high) { size_t mid=low+(high-low)/2; if(face->cids[mid].cid<ch->cid) low=mid+1; else high=mid; }
    if(low<face->count && face->cids[low].cid==ch->cid) glyph=face->cids[low].glyph;
  } else if(face->kind==EXR_PDF_TRUETYPE && (face->flags&4)) {
    if(!FT_Select_Charmap(ft,FT_ENCODING_MS_SYMBOL)) {
      glyph=FT_Get_Char_Index(ft,0xf000+ch->cid); if(!glyph) glyph=FT_Get_Char_Index(ft,ch->cid);
    } else {
      for(i=0;i<(size_t)ft->num_charmaps;i++) if(ft->charmaps[i]->platform_id==1 && ft->charmaps[i]->encoding_id==0) break;
      if(i==(size_t)ft->num_charmaps || FT_Set_Charmap(ft,ft->charmaps[i])) return exr_fail(error,EXR_FORMAT,"Unsupported symbolic PDF TrueType cmap");
      glyph=FT_Get_Char_Index(ft,ch->cid);
    }
  } else if(ch->glyph_name) {
    char text[256]; uint32_t cp;
    if(FT_HAS_GLYPH_NAMES(ft)) glyph=FT_Get_Name_Index(ft,(FT_String *)ch->glyph_name);
    if(!glyph && unicode_scalar(text,exr_pdf_glyph_unicode(ch->glyph_name,face->dingbats,text),&cp) &&
       !FT_Select_Charmap(ft,FT_ENCODING_UNICODE)) glyph=FT_Get_Char_Index(ft,cp);
  } else if(face->encoding || face->standard) glyph=0;
  else if(face->kind==EXR_PDF_TYPE1) {
    if(FT_Select_Charmap(ft,FT_ENCODING_ADOBE_CUSTOM) && FT_Select_Charmap(ft,FT_ENCODING_ADOBE_STANDARD))
      return exr_fail(error,EXR_FORMAT,"PDF Type1 builtin encoding is unavailable");
    glyph=FT_Get_Char_Index(ft,ch->cid);
  } else return exr_fail(error,EXR_FORMAT,"PDF simple font has no usable glyph encoding");
  *out=glyph<(uint64_t)ft->num_glyphs ? glyph : 0;
  if(error) memset(error,0,sizeof(*error));
  return EXR_OK;
}
exr_status exr_pdf_face_outline(exr_pdf_face *face,const exr_pdf_character *ch,exr_vector_segment **out,
                                 size_t *count,size_t *work,const exr_control *control,exr_error *error) {
  uint32_t glyph; exr_status status;
  if(out) *out=NULL;
  if(count) *count=0;
  if(!out || !count) return exr_fail(error,EXR_ARGUMENT,"Missing PDF outline output");
  status=exr_pdf_face_glyph(face,ch,&glyph,error);
  return status==EXR_OK ? exr_font_outline(face->face,glyph,out,count,work,control,error) : status;
}
