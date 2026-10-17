/* SPDX-License-Identifier: GPL-3.0-only */
#include "pdf_internal.h"
typedef struct { uint32_t first,last; size_t offset; unsigned constant; } width_range;
typedef struct { width_range *ranges; size_t count,capacity; double *values; size_t value_count,value_capacity; unsigned dimension; } width_table;
struct exr_pdf_font {
  exr_pdf_font_info info; exr_pdf_cmap *unicode;
  char *names[256]; double simple[256],default_width,default_vertical[2];
  width_table widths,vertical;
  const unsigned char *cid_glyphs; size_t cid_glyph_size;
};
typedef struct { exr_pdf_file *file; const exr_control *control; exr_error error; } font_reader;
static int bad(font_reader *r,const char *message) { if(r->error.code==EXR_OK) exr_fail(&r->error,EXR_FORMAT,"%s",message); return 0; }
static uint32_t resolve(font_reader *r,uint32_t id) {
  uint32_t out=EXR_PDF_NONE;
  if(r->error.code==EXR_OK) exr_pdf_resolve(r->file,id,&out,&r->error);
  if(out!=EXR_PDF_NONE && exr_pdf_value_at(r->file,out)->kind==EXR_PDF_NULL) out=EXR_PDF_NONE;
  return out;
}
static uint32_t get(font_reader *r,uint32_t id,const char *key) { return resolve(r,exr_pdf_get(r->file,id,key)); }
static int name_is(font_reader *r,uint32_t id,const char *name) {
  size_t n; const unsigned char *data=exr_pdf_bytes(r->file,id,&n);
  return data && exr_pdf_value_at(r->file,id)->kind==EXR_PDF_NAME && n==strlen(name) && !memcmp(data,name,n);
}
static int integer(font_reader *r,uint32_t id,uint32_t maximum,uint32_t *out) {
  const exr_pdf_value *v;
  id=resolve(r,id); v=exr_pdf_value_at(r->file,id);
  if(!v || v->kind!=EXR_PDF_INT || v->u.integer<0 || (uint64_t)v->u.integer>maximum) return 0;
  *out=(uint32_t)v->u.integer; return 1;
}
static int number(font_reader *r,uint32_t id,double *out) {
  const exr_pdf_value *v;
  id=resolve(r,id); v=exr_pdf_value_at(r->file,id);
  if(!v || (v->kind!=EXR_PDF_INT && v->kind!=EXR_PDF_REAL)) return 0;
  *out=v->kind==EXR_PDF_INT ? (double)v->u.integer : v->u.number;
  return isfinite(*out) && fabs(*out)<=1e7;
}
static char *copy_name(font_reader *r,uint32_t id) {
  size_t n; const unsigned char *data=exr_pdf_bytes(r->file,id,&n); char *copy;
  if(!data || exr_pdf_value_at(r->file,id)->kind!=EXR_PDF_NAME || !n || n>127 || memchr(data,0,n)) { bad(r,"Invalid PDF font name"); return NULL; }
  copy=exr_copy((const char *)data,n); if(!copy) exr_fail(&r->error,EXR_MEMORY,"PDF font name allocation failed"); return copy;
}
static uint32_t next(exr_pdf_file *file,uint32_t id) { return id==EXR_PDF_NONE ? id : exr_pdf_value_at(file,id)->next; }
static int compare_width(const void *a,const void *b) {
  const width_range *x=a,*y=b; return x->first<y->first ? -1 : x->first>y->first;
}
static int add_width(font_reader *r,width_table *table,double value) {
  if(!(table->value_count&1023) && exr_control_cancel(r->control,&r->error)!=EXR_OK) return 0;
  if(table->value_count>=(size_t)65536*table->dimension) { exr_fail(&r->error,EXR_LIMIT,"PDF font metric budget exceeded"); return 0; }
  if(!exr_grow((void **)&table->values,&table->value_capacity,table->value_count+1,sizeof(*table->values))) {
    exr_fail(&r->error,EXR_MEMORY,"PDF font metric allocation failed"); return 0;
  }
  table->values[table->value_count++]=value; return 1;
}
static int widths(font_reader *r,uint32_t id,width_table *table,unsigned dimension) {
  const exr_pdf_value *v; uint32_t at; size_t i;
  table->dimension=dimension;
  if(id==EXR_PDF_NONE) return 1;
  v=exr_pdf_value_at(r->file,id); if(v->kind!=EXR_PDF_ARRAY) return bad(r,"PDF CID widths are not an array");
  at=v->first;
  while(at!=EXR_PDF_NONE && r->error.code==EXR_OK) {
    width_range range={0}; uint32_t value; double metric; size_t entries;
    if(!integer(r,at,65535,&range.first)) goto invalid;
    at=next(r->file,at); if(at==EXR_PDF_NONE) goto invalid;
    value=resolve(r,at); v=exr_pdf_value_at(r->file,value); if(!v) goto invalid;
    range.offset=table->value_count;
    if(v->kind==EXR_PDF_ARRAY) {
      uint32_t member=v->first;
      while(member!=EXR_PDF_NONE) {
        uint32_t following=next(r->file,member);
        if(!number(r,member,&metric) || !add_width(r,table,metric)) goto invalid;
        member=following;
      }
      entries=table->value_count-range.offset;
      if(!entries || entries%dimension || entries/dimension>65536-range.first) goto invalid;
      range.last=range.first+(uint32_t)(entries/dimension)-1; at=next(r->file,at);
    } else {
      unsigned k;
      if(!integer(r,value,65535,&range.last) || range.last<range.first) goto invalid;
      range.constant=1; at=next(r->file,at);
      for(k=0;k<dimension;k++) {
        uint32_t following=next(r->file,at);
        if(!number(r,at,&metric) || !add_width(r,table,metric)) goto invalid;
        at=following;
      }
    }
    if(table->count==65536) { exr_fail(&r->error,EXR_LIMIT,"PDF font metric range budget exceeded"); return 0; }
    if(!exr_grow((void **)&table->ranges,&table->capacity,table->count+1,sizeof(*table->ranges))) { exr_fail(&r->error,EXR_MEMORY,"PDF metric range allocation failed"); return 0; }
    table->ranges[table->count++]=range;
  }
  if(table->count) qsort(table->ranges,table->count,sizeof(*table->ranges),compare_width);
  for(i=1;i<table->count;i++) if(table->ranges[i].first<=table->ranges[i-1].last) goto invalid;
  return r->error.code==EXR_OK;
invalid:
  return bad(r,"Invalid, overlapping or incomplete PDF CID width ranges");
}
static const double *lookup_width(const width_table *table,uint32_t code) {
  size_t low=0,high=table->count;
  while(low<high) { size_t mid=low+(high-low)/2; if(table->ranges[mid].first<=code) low=mid+1; else high=mid; }
  if(low && code<=table->ranges[low-1].last) {
    const width_range *range=&table->ranges[low-1];
    return table->values+range->offset+(range->constant ? 0 : (size_t)(code-range->first)*table->dimension);
  }
  return NULL;
}
static int simple_encoding(font_reader *r,uint32_t id,exr_pdf_font *font) {
  uint32_t differences=EXR_PDF_NONE; const exr_pdf_value *v=exr_pdf_value_at(r->file,id);
  if(v && v->kind==EXR_PDF_DICT) { differences=get(r,id,"Differences"); id=get(r,id,"BaseEncoding"); }
  else if(v && v->kind!=EXR_PDF_NAME) return bad(r,"Invalid PDF simple font Encoding");
  if(id!=EXR_PDF_NONE) { font->info.encoding_name=copy_name(r,id); if(!font->info.encoding_name) return 0; }
  if(differences!=EXR_PDF_NONE) {
    uint32_t at; unsigned code=256;
    v=exr_pdf_value_at(r->file,differences); if(v->kind!=EXR_PDF_ARRAY) return bad(r,"PDF font Differences are not an array");
    at=v->first;
    while(at!=EXR_PDF_NONE) {
      uint32_t following=next(r->file,at),value=resolve(r,at); v=exr_pdf_value_at(r->file,value);
      if(v && v->kind==EXR_PDF_INT) { uint32_t start; if(!integer(r,value,255,&start)) return bad(r,"Invalid PDF Differences code"); code=start; }
      else {
        char *name;
        if(code>255 || !(name=copy_name(r,value))) return bad(r,"Invalid PDF Differences glyph name");
        free(font->names[code]); font->names[code++]=name;
      }
      at=following;
    }
  }
  return r->error.code==EXR_OK;
}
void exr_pdf_font_close(exr_pdf_font *font) {
  size_t i; if(!font) return;
  free((void *)font->info.base_name); free((void *)font->info.encoding_name); free((void *)font->info.program_type);
  for(i=0;i<256;i++) free(font->names[i]);
  exr_pdf_cmap_free(font->unicode); free(font->widths.ranges); free(font->widths.values); free(font->vertical.ranges); free(font->vertical.values); free(font);
}
const exr_pdf_font_info *exr_pdf_font_description(const exr_pdf_font *font) { return font ? &font->info : NULL; }
size_t exr_pdf_font_memory(const exr_pdf_font *font) {
  size_t bytes=0,i; const char *names[3];
  if(!font) return 0;
  bytes=sizeof(*font)+exr_pdf_cmap_memory(font->unicode)+(font->widths.capacity+font->vertical.capacity)*sizeof(width_range)+
    (font->widths.value_capacity+font->vertical.value_capacity)*sizeof(double);
  names[0]=font->info.base_name; names[1]=font->info.encoding_name; names[2]=font->info.program_type;
  for(i=0;i<3;i++) if(names[i]) bytes+=strlen(names[i])+1;
  for(i=0;i<256;i++) if(font->names[i]) bytes+=strlen(font->names[i])+1;
  return bytes;
}
exr_status exr_pdf_font_open(exr_pdf_file *file,uint32_t dict,const exr_control *control,exr_pdf_font **out,exr_error *error) {
  font_reader r={0}; exr_pdf_font *font; uint32_t subtype,metrics,descriptor,encoding,id,to_unicode; const exr_pdf_value *v; size_t i;
  if(!out) return exr_fail(error,EXR_ARGUMENT,"Missing PDF font output");
  *out=NULL; if(!file) return exr_fail(error,EXR_ARGUMENT,"Missing PDF font file");
  r.file=file; r.control=control; font=calloc(1,sizeof(*font)); if(!font) return exr_fail(error,EXR_MEMORY,"PDF font allocation failed");
  if(exr_control_cancel(control,&r.error)!=EXR_OK) goto done;
  dict=resolve(&r,dict); v=exr_pdf_value_at(file,dict); if(!v || v->kind!=EXR_PDF_DICT) goto invalid;
  subtype=get(&r,dict,"Subtype"); encoding=get(&r,dict,"Encoding"); metrics=dict; to_unicode=get(&r,dict,"ToUnicode");
  if(name_is(&r,subtype,"Type0")) {
    uint32_t descendants=get(&r,dict,"DescendantFonts"),first;
    font->info.composite=1;
    if(!name_is(&r,encoding,"Identity-H") && !name_is(&r,encoding,"Identity-V")) { bad(&r,"Custom PDF composite Encoding CMaps are not implemented yet"); goto done; }
    font->info.vertical=name_is(&r,encoding,"Identity-V"); font->info.encoding_name=copy_name(&r,encoding);
    v=exr_pdf_value_at(file,descendants);
    if(!v || v->kind!=EXR_PDF_ARRAY || (first=v->first)==EXR_PDF_NONE || next(file,first)!=EXR_PDF_NONE) goto invalid;
    metrics=resolve(&r,first); v=exr_pdf_value_at(file,metrics); if(!v || v->kind!=EXR_PDF_DICT) goto invalid;
    subtype=get(&r,metrics,"Subtype");
    if(name_is(&r,subtype,"CIDFontType2")) font->info.kind=EXR_PDF_CID_TYPE2;
    else if(name_is(&r,subtype,"CIDFontType0")) font->info.kind=EXR_PDF_CID_TYPE0;
    else goto invalid;
  } else if(name_is(&r,subtype,"TrueType")) font->info.kind=EXR_PDF_TRUETYPE;
  else if(name_is(&r,subtype,"Type1") || name_is(&r,subtype,"MMType1")) font->info.kind=EXR_PDF_TYPE1;
  else { bad(&r,"PDF font Subtype is not implemented yet"); goto done; }
  id=get(&r,dict,"BaseFont"); if(id==EXR_PDF_NONE) id=get(&r,metrics,"BaseFont");
  if(id!=EXR_PDF_NONE) { font->info.base_name=copy_name(&r,id); if(!font->info.base_name) goto done; }
  descriptor=get(&r,metrics,"FontDescriptor"); v=exr_pdf_value_at(file,descriptor);
  if(v && v->kind!=EXR_PDF_DICT) goto invalid;
  if(font->info.composite) {
    font->default_width=1000; font->default_vertical[0]=880; font->default_vertical[1]=-1000;
    id=get(&r,metrics,"DW"); if(id!=EXR_PDF_NONE && !number(&r,id,&font->default_width)) goto invalid;
    id=get(&r,metrics,"DW2"); if(id!=EXR_PDF_NONE) {
      uint32_t at; v=exr_pdf_value_at(file,id); if(v->kind!=EXR_PDF_ARRAY) goto invalid; at=v->first;
      for(i=0;i<2;i++) { if(!number(&r,at,&font->default_vertical[i])) goto invalid; at=next(file,at); }
      if(at!=EXR_PDF_NONE) goto invalid;
    }
    if(!widths(&r,get(&r,metrics,"W"),&font->widths,1) || !widths(&r,get(&r,metrics,"W2"),&font->vertical,3)) goto done;
    id=get(&r,metrics,"CIDToGIDMap");
    if(id!=EXR_PDF_NONE && !name_is(&r,id,"Identity")) {
      if(font->info.kind!=EXR_PDF_CID_TYPE2 || exr_pdf_stream_data(file,id,&font->cid_glyphs,&font->cid_glyph_size,&r.error)!=EXR_OK) goto invalid;
      if(font->cid_glyph_size%2 || font->cid_glyph_size>131072) goto invalid;
    }
  } else {
    uint32_t first,last,at;
    id=get(&r,descriptor,"MissingWidth"); if(id!=EXR_PDF_NONE && !number(&r,id,&font->default_width)) goto invalid;
    for(i=0;i<256;i++) font->simple[i]=font->default_width;
    id=get(&r,metrics,"Widths"); v=exr_pdf_value_at(file,id);
    if(!v || v->kind!=EXR_PDF_ARRAY) { bad(&r,"PDF standard-font fallback widths are not implemented yet"); goto done; }
    at=v->first;
    if(!integer(&r,get(&r,metrics,"FirstChar"),255,&first) || !integer(&r,get(&r,metrics,"LastChar"),255,&last) || first>last) goto invalid;
    for(i=first;i<=last;i++) { if(!number(&r,at,&font->simple[i])) goto invalid; at=next(file,at); }
    if(at!=EXR_PDF_NONE || !simple_encoding(&r,encoding,font)) goto invalid;
  }
  { const char *keys[]={"FontFile","FontFile2","FontFile3"}; unsigned found=0;
    for(i=0;i<3;i++) {
      id=get(&r,descriptor,keys[i]); if(id==EXR_PDF_NONE) continue;
      if((i==0 && font->info.kind!=EXR_PDF_TYPE1) ||
         (i==1 && font->info.kind!=EXR_PDF_TRUETYPE && font->info.kind!=EXR_PDF_CID_TYPE2)) goto invalid;
      if(found++ || exr_pdf_stream_data(file,id,&font->info.program,&font->info.program_size,&r.error)!=EXR_OK) goto invalid;
      if(!font->info.program_size) goto invalid;
      if(font->info.program_size>EXR_MAX_TEXT) { exr_fail(&r.error,EXR_LIMIT,"PDF embedded font exceeds 64 MiB"); goto done; }
      if(i==2) {
        uint32_t program_type=get(&r,id,"Subtype");
        if(!name_is(&r,program_type,"OpenType") &&
           !(font->info.kind==EXR_PDF_TYPE1 && name_is(&r,program_type,"Type1C")) &&
           !(font->info.kind==EXR_PDF_CID_TYPE0 && name_is(&r,program_type,"CIDFontType0C"))) goto invalid;
        font->info.program_type=copy_name(&r,program_type); if(!font->info.program_type) goto done;
      }
    }
  }
  if(to_unicode!=EXR_PDF_NONE) {
    const unsigned char *data; size_t size;
    if(exr_pdf_stream_data(file,to_unicode,&data,&size,&r.error)!=EXR_OK || exr_pdf_cmap_parse(data,size,control,&font->unicode,&r.error)!=EXR_OK) goto done;
  }
  if(r.error.code==EXR_OK && exr_control_cancel(control,&r.error)==EXR_OK) { *out=font; font=NULL; } goto done;
invalid:
  bad(&r,"Invalid PDF font dictionary, widths or program");
done:
  exr_pdf_font_close(font); if(error) *error=r.error; return r.error.code;
}
exr_status exr_pdf_font_next(const exr_pdf_font *font,const unsigned char *data,size_t size,size_t *at,exr_pdf_character *out,exr_error *error) {
  size_t bytes,used=0; uint32_t code; const double *metric;
  if(out) memset(out,0,sizeof(*out));
  if(!font || !data || !at || !out || *at>=size) return exr_fail(error,EXR_ARGUMENT,"Missing PDF font character input/output");
  bytes=font->info.composite ? 2 : 1;
  if(bytes>size-*at) return exr_fail(error,EXR_FORMAT,"Truncated PDF composite character code");
  code=bytes==2 ? ((uint32_t)data[*at]<<8)|data[*at+1] : data[*at];
  if(font->unicode) {
    exr_status status=exr_pdf_cmap_next(font->unicode,data+*at,bytes,&used,&out->text,error);
    if(status!=EXR_OK) return status;
    if(used!=bytes) { memset(out,0,sizeof(*out)); return exr_fail(error,EXR_FORMAT,"PDF ToUnicode and font code widths disagree"); }
  } else { out->text.code=code; out->text.code_bytes=(unsigned)bytes; memcpy(out->text.utf8,"\xef\xbf\xbd",4); out->text.size=3; }
  out->cid=code; out->width=font->default_width;
  if(font->info.composite) {
    metric=lookup_width(&font->widths,code); if(metric) out->width=metric[0];
    if(font->info.kind==EXR_PDF_CID_TYPE2) {
      out->glyph_known=1; out->glyph=font->cid_glyphs ? (code<font->cid_glyph_size/2 ? ((uint32_t)font->cid_glyphs[2*code]<<8)|font->cid_glyphs[2*code+1] : 0) : code;
    }
  } else { out->width=font->simple[code]; out->glyph_name=font->names[code]; }
  out->vertical_advance=font->default_vertical[1]; out->vertical_x=out->width/2; out->vertical_y=font->default_vertical[0];
  metric=lookup_width(&font->vertical,code);
  if(metric) { out->vertical_advance=metric[0]; out->vertical_x=metric[1]; out->vertical_y=metric[2]; }
  *at+=bytes;
  if(error) memset(error,0,sizeof(*error));
  return EXR_OK;
}
