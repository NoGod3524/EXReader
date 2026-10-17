/* SPDX-License-Identifier: GPL-3.0-only */
#include "pdf_internal.h"
typedef struct {
  double ctm[6],size,char_space,word_space,scale,leading,rise;
  exr_pdf_font *font; unsigned mode;
} text_state;
typedef struct { uint32_t id; exr_pdf_font *font; } cached_font;
typedef struct {
  exr_pdf_file *file; uint32_t resources; const exr_control *control;
  exr_pdf_text_fn glyph; void *context;
  text_state state,stack[128]; size_t depth,sequence,font_count,font_bytes;
  double matrix[6],line[6]; unsigned inside,compatibility;
  cached_font fonts[128];
} text_reader;
static void identity(double matrix[6]) { memset(matrix,0,6*sizeof(double)); matrix[0]=matrix[3]=1; }
static int multiply(double out[6],const double left[6],const double right[6]) {
  double m[6]; size_t i;
  m[0]=left[0]*right[0]+left[2]*right[1]; m[1]=left[1]*right[0]+left[3]*right[1];
  m[2]=left[0]*right[2]+left[2]*right[3]; m[3]=left[1]*right[2]+left[3]*right[3];
  m[4]=left[0]*right[4]+left[2]*right[5]+left[4]; m[5]=left[1]*right[4]+left[3]*right[5]+left[5];
  for(i=0;i<6;i++) if(!isfinite(m[i]) || fabs(m[i])>1e12) return 0;
  memcpy(out,m,sizeof(m)); return 1;
}
static int translate(double matrix[6],double x,double y) { const double move[6]={1,0,0,1,x,y}; return multiply(matrix,matrix,move); }
static int numeric(exr_pdf_file *arena,uint32_t id,double *out) {
  const exr_pdf_value *v=exr_pdf_value_at(arena,id);
  if(!v || (v->kind!=EXR_PDF_INT && v->kind!=EXR_PDF_REAL)) return 0;
  *out=v->kind==EXR_PDF_INT ? (double)v->u.integer : v->u.number;
  return isfinite(*out) && fabs(*out)<=1e7;
}
static exr_status resolved(exr_pdf_file *file,uint32_t id,uint32_t *out,exr_error *error) { return exr_pdf_resolve(file,id,out,error); }
static exr_status resource(text_reader *r,exr_pdf_file *arena,uint32_t name,const char *kind,uint32_t *out,exr_error *error) {
  const unsigned char *data; size_t n; char key[128]; uint32_t dictionary;
  data=exr_pdf_bytes(arena,name,&n);
  if(!data || exr_pdf_value_at(arena,name)->kind!=EXR_PDF_NAME || !n || n>127 || memchr(data,0,n)) return exr_fail(error,EXR_FORMAT,"Invalid PDF text resource name");
  memcpy(key,data,n); key[n]=0;
  if(resolved(r->file,exr_pdf_get(r->file,r->resources,kind),&dictionary,error)!=EXR_OK) return error->code;
  if(resolved(r->file,exr_pdf_get(r->file,dictionary,key),out,error)!=EXR_OK) return error->code;
  if(*out==EXR_PDF_NONE) return exr_fail(error,EXR_FORMAT,"Missing PDF text resource");
  return EXR_OK;
}
static exr_status select_font(text_reader *r,uint32_t id,double size,exr_error *error) {
  size_t i,bytes; exr_pdf_font *font=NULL;
  for(i=0;i<r->font_count;i++) if(r->fonts[i].id==id) { r->state.font=r->fonts[i].font; r->state.size=size; return EXR_OK; }
  if(r->font_count==128) return exr_fail(error,EXR_LIMIT,"PDF page font cache exceeds 128 fonts");
  if(exr_pdf_font_open(r->file,id,r->control,&font,error)!=EXR_OK) return error->code;
  bytes=exr_pdf_font_memory(font);
  if(bytes>EXR_MAX_INPUT-r->font_bytes) { exr_pdf_font_close(font); return exr_fail(error,EXR_LIMIT,"PDF page font cache exceeds 128 MiB"); }
  r->fonts[r->font_count++]=(cached_font){id,font}; r->font_bytes+=bytes; r->state.font=font; r->state.size=size; return EXR_OK;
}
static exr_status show(text_reader *r,exr_pdf_file *arena,uint32_t string,exr_error *error) {
  size_t n,at=0; const unsigned char *data=exr_pdf_bytes(arena,string,&n); const exr_pdf_font_info *font;
  if(!data || exr_pdf_value_at(arena,string)->kind!=EXR_PDF_STRING || !r->state.font) return exr_fail(error,EXR_FORMAT,"PDF text needs a string and selected font");
  font=exr_pdf_font_description(r->state.font);
  while(at<n) {
    exr_pdf_text_glyph glyph={0}; double scale[6]={0},matrix[6],advance,spacing;
    if(r->sequence==EXR_MAX_ITEMS) return exr_fail(error,EXR_LIMIT,"PDF page glyph budget exceeded");
    if(!(r->sequence&255) && exr_control_cancel(r->control,error)!=EXR_OK) return error->code;
    if(exr_pdf_font_next(r->state.font,data,n,&at,&glyph.character,error)!=EXR_OK) return error->code;
    scale[0]=r->state.size*r->state.scale/1000; scale[3]=r->state.size/1000; scale[5]=r->state.rise;
    if(font->vertical) { scale[4]=-glyph.character.vertical_x*scale[0]; scale[5]-=glyph.character.vertical_y*scale[3]; }
    if(!multiply(matrix,r->matrix,scale) || !multiply(glyph.transform,r->state.ctm,matrix)) return exr_fail(error,EXR_LIMIT,"PDF glyph transform exceeds coordinate budget");
    glyph.font=r->state.font; glyph.sequence=r->sequence++; glyph.rendering_mode=r->state.mode;
    { exr_status status=r->glyph(r->context,&glyph,error); if(status!=EXR_OK) return status; if(error->code!=EXR_OK) return error->code; }
    spacing=r->state.char_space+(glyph.character.text.code_bytes==1 && glyph.character.text.code==32 ? r->state.word_space : 0);
    advance=(font->vertical ? glyph.character.vertical_advance : glyph.character.width)*r->state.size/1000+spacing;
    if(!translate(r->matrix,font->vertical ? 0 : advance*r->state.scale,font->vertical ? advance : 0)) return exr_fail(error,EXR_LIMIT,"PDF text position exceeds coordinate budget");
  }
  return EXR_OK;
}
static int new_line(text_reader *r,double x,double y) {
  if(!translate(r->line,x,y)) return 0;
  memcpy(r->matrix,r->line,sizeof(r->matrix)); return 1;
}
static exr_status text_operation(void *context,exr_pdf_file *arena,const char *name,const uint32_t *values,size_t count,exr_error *error) {
  text_reader *r=context; double numbers[6]; size_t i; uint32_t id;
  if(!strcmp(name,"q")) { if(count) goto invalid; if(r->depth==128) goto limit; r->stack[r->depth++]=r->state; return EXR_OK; }
  if(!strcmp(name,"Q")) { if(count || !r->depth) goto invalid; r->state=r->stack[--r->depth]; return EXR_OK; }
  if(!strcmp(name,"BT")) { if(count || r->inside) goto invalid; r->inside=1; identity(r->matrix); identity(r->line); return EXR_OK; }
  if(!strcmp(name,"ET")) { if(count || !r->inside) goto invalid; r->inside=0; return EXR_OK; }
  if(!strcmp(name,"BX")) { if(count) goto invalid; if(r->compatibility==128) goto limit; r->compatibility++; return EXR_OK; }
  if(!strcmp(name,"EX")) { if(count || !r->compatibility) goto invalid; r->compatibility--; return EXR_OK; }
  if(!strcmp(name,"cm")) {
    if(count!=6) goto invalid;
    for(i=0;i<6;i++) if(!numeric(arena,values[i],&numbers[i])) goto invalid;
    if(!multiply(r->state.ctm,r->state.ctm,numbers)) goto limit;
    return EXR_OK;
  }
  if(!strcmp(name,"gs")) {
    uint32_t font,at,size_id; const exr_pdf_value *v; double size;
    if(count!=1 || resource(r,arena,values[0],"ExtGState",&id,error)!=EXR_OK) goto invalid;
    v=exr_pdf_value_at(r->file,id); if(!v || v->kind!=EXR_PDF_DICT) goto invalid;
    if(resolved(r->file,exr_pdf_get(r->file,id,"Font"),&font,error)!=EXR_OK) return error->code;
    if(font==EXR_PDF_NONE) return EXR_OK;
    v=exr_pdf_value_at(r->file,font); if(v->kind!=EXR_PDF_ARRAY || (at=v->first)==EXR_PDF_NONE) goto invalid;
    size_id=exr_pdf_value_at(r->file,at)->next;
    if(size_id==EXR_PDF_NONE || exr_pdf_value_at(r->file,size_id)->next!=EXR_PDF_NONE ||
       resolved(r->file,at,&id,error)!=EXR_OK || resolved(r->file,size_id,&size_id,error)!=EXR_OK || !numeric(r->file,size_id,&size)) goto invalid;
    return select_font(r,id,size,error);
  }
  if(!strcmp(name,"Do")) {
    uint32_t subtype; size_t n; const unsigned char *type;
    if(count!=1 || resource(r,arena,values[0],"XObject",&id,error)!=EXR_OK) goto invalid;
    if(resolved(r->file,exr_pdf_get(r->file,id,"Subtype"),&subtype,error)!=EXR_OK) return error->code;
    type=exr_pdf_bytes(r->file,subtype,&n);
    if(type && exr_pdf_value_at(r->file,subtype)->kind==EXR_PDF_NAME && n==5 && !memcmp(type,"Image",5)) return EXR_OK;
    return exr_fail(error,EXR_FORMAT,"PDF Form text execution is not implemented yet");
  }
  if(!strcmp(name,"Tf")) {
    if(!r->inside || count!=2 || !numeric(arena,values[1],&numbers[0])) goto invalid;
    if(resource(r,arena,values[0],"Font",&id,error)!=EXR_OK) return error->code;
    return select_font(r,id,numbers[0],error);
  }
  if(!strcmp(name,"Tj") || !strcmp(name,"'") || !strcmp(name,"\"")) {
    size_t expected=!strcmp(name,"\"") ? 3 : 1;
    if(!r->inside || count!=expected) goto invalid;
    if(expected==3) {
      if(!numeric(arena,values[0],&r->state.word_space) || !numeric(arena,values[1],&r->state.char_space)) goto invalid;
    }
    if(strcmp(name,"Tj") && !new_line(r,0,-r->state.leading)) goto limit;
    return show(r,arena,values[count-1],error);
  }
  if(!strcmp(name,"TJ")) {
    const exr_pdf_value *v; uint32_t at;
    if(!r->inside || count!=1 || !(v=exr_pdf_value_at(arena,values[0])) || v->kind!=EXR_PDF_ARRAY || !r->state.font) goto invalid;
    for(at=v->first;at!=EXR_PDF_NONE;at=exr_pdf_value_at(arena,at)->next) {
      if(numeric(arena,at,&numbers[0])) {
        int vertical=exr_pdf_font_description(r->state.font)->vertical;
        double move=-numbers[0]*r->state.size/1000;
        if(!translate(r->matrix,vertical ? 0 : move*r->state.scale,vertical ? move : 0)) goto limit;
      } else { exr_status status=show(r,arena,at,error); if(status!=EXR_OK) return status; }
    }
    return EXR_OK;
  }
  if(!strcmp(name,"Tm") || !strcmp(name,"Td") || !strcmp(name,"TD") || !strcmp(name,"T*")) {
    size_t expected=!strcmp(name,"Tm") ? 6 : !strcmp(name,"T*") ? 0 : 2;
    if(!r->inside || count!=expected) goto invalid;
    for(i=0;i<count;i++) if(!numeric(arena,values[i],&numbers[i])) goto invalid;
    if(expected==6) { memcpy(r->matrix,numbers,sizeof(numbers)); memcpy(r->line,numbers,sizeof(numbers)); }
    else {
      if(!strcmp(name,"TD")) r->state.leading=-numbers[1];
      if(!new_line(r,expected ? numbers[0] : 0,expected ? numbers[1] : -r->state.leading)) goto limit;
    }
    return EXR_OK;
  }
  if(!strcmp(name,"Tc") || !strcmp(name,"Tw") || !strcmp(name,"Tz") || !strcmp(name,"TL") || !strcmp(name,"Ts") || !strcmp(name,"Tr")) {
    if(!r->inside || count!=1 || !numeric(arena,values[0],&numbers[0])) goto invalid;
    if(!strcmp(name,"Tc")) r->state.char_space=numbers[0];
    else if(!strcmp(name,"Tw")) r->state.word_space=numbers[0];
    else if(!strcmp(name,"Tz")) r->state.scale=numbers[0]/100;
    else if(!strcmp(name,"TL")) r->state.leading=numbers[0];
    else if(!strcmp(name,"Ts")) r->state.rise=numbers[0];
    else { if(numbers[0]<0 || numbers[0]>7 || floor(numbers[0])!=numbers[0]) goto invalid; r->state.mode=(unsigned)numbers[0]; }
    return EXR_OK;
  }
  { const char *ignored[]={"m","l","c","v","y","h","re","S","s","f","F","f*","B","B*","b","b*","n","W","W*","w","J","j","M","d","ri","i","G","g","RG","rg","K","k","CS","cs","SC","sc","SCN","scn","sh","d0","d1","BMC","BDC","EMC","MP","DP"};
    for(i=0;i<sizeof(ignored)/sizeof(*ignored);i++) if(!strcmp(name,ignored[i])) return EXR_OK;
  }
  if(r->compatibility) return EXR_OK;
invalid:
  if(error->code!=EXR_OK) return error->code;
  return exr_fail(error,EXR_FORMAT,"Invalid or unsupported PDF text operator/operands");
limit:
  return exr_fail(error,EXR_LIMIT,"PDF text state or coordinate budget exceeded");
}
exr_status exr_pdf_text_ops(exr_pdf_file *file,uint32_t resources,const void *data,size_t size,
                            exr_pdf_text_fn glyph,void *context,const exr_control *control,exr_error *error) {
  text_reader *r; exr_error local={0}; exr_status status; size_t i;
  if(!file || !glyph || (!data && size)) return exr_fail(error,EXR_ARGUMENT,"Missing PDF text input or glyph callback");
  r=calloc(1,sizeof(*r)); if(!r) return exr_fail(error,EXR_MEMORY,"PDF text state allocation failed");
  r->file=file; r->resources=resources; r->control=control; r->glyph=glyph; r->context=context; r->state.scale=1;
  identity(r->state.ctm); identity(r->matrix); identity(r->line);
  status=exr_pdf_content_ops(data,size,text_operation,r,control,&local);
  if(status==EXR_OK && (r->inside || r->depth || r->compatibility)) status=exr_fail(&local,EXR_FORMAT,"Unbalanced PDF text/graphics/compatibility state");
  for(i=0;i<r->font_count;i++) exr_pdf_font_close(r->fonts[i].font);
  free(r); if(error) *error=local; return status;
}
