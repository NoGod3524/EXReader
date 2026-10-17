/* SPDX-License-Identifier: GPL-3.0-only */
#include "pdf_internal.h"
typedef struct {
  exr_pdf_file *file; exr_error error;
  exr_pdf_page_info *pages; size_t count,capacity,nodes;
  unsigned char *seen;
} page_reader;
typedef struct { double media[4],crop[4]; uint32_t resources; unsigned rotation,have_media,have_crop; } inherited;
static int invalid(page_reader *r,const char *message) {
  if(r->error.code==EXR_OK) exr_fail(&r->error,EXR_FORMAT,"%s",message);
  return 0;
}
static uint32_t resolved(page_reader *r,uint32_t id) {
  uint32_t value=EXR_PDF_NONE;
  if(r->error.code==EXR_OK) exr_pdf_resolve(r->file,id,&value,&r->error);
  if(value!=EXR_PDF_NONE && exr_pdf_value_at(r->file,value)->kind==EXR_PDF_NULL) value=EXR_PDF_NONE;
  return value;
}
static uint32_t property(page_reader *r,uint32_t dict,const char *name) {
  return resolved(r,exr_pdf_get(r->file,dict,name));
}
static int name_is(page_reader *r,uint32_t id,const char *name) {
  size_t n; const unsigned char *data=exr_pdf_bytes(r->file,id,&n);
  return data && exr_pdf_value_at(r->file,id)->kind==EXR_PDF_NAME && n==strlen(name) && !memcmp(data,name,n);
}
static int number(page_reader *r,uint32_t id,double *out) {
  const exr_pdf_value *v;
  id=resolved(r,id); v=exr_pdf_value_at(r->file,id);
  if(!v || (v->kind!=EXR_PDF_INT && v->kind!=EXR_PDF_REAL)) return 0;
  *out=v->kind==EXR_PDF_INT ? (double)v->u.integer : v->u.number;
  return isfinite(*out);
}
static int rectangle(page_reader *r,uint32_t id,double box[4]) {
  const exr_pdf_value *v=exr_pdf_value_at(r->file,id); uint32_t at; size_t count=0;
  if(!v || v->kind!=EXR_PDF_ARRAY) return invalid(r,"PDF page rectangle is not an array");
  at=v->first;
  while(at!=EXR_PDF_NONE) {
    uint32_t next=exr_pdf_value_at(r->file,at)->next;
    if(count==4 || !number(r,at,&box[count]) || fabs(box[count])>1e7) return invalid(r,"Invalid PDF page rectangle coordinates");
    count++; at=next;
  }
  if(count!=4) return invalid(r,"PDF page rectangle requires four coordinates");
  if(box[0]>box[2]) { double swap=box[0]; box[0]=box[2]; box[2]=swap; }
  if(box[1]>box[3]) { double swap=box[1]; box[1]=box[3]; box[3]=swap; }
  return (box[0]<box[2] && box[1]<box[3]) || invalid(r,"PDF page rectangle has zero area");
}
static int visit(page_reader *r,uint32_t id,uint32_t parent,inherited state,unsigned depth) {
  uint32_t value,type,at; const exr_pdf_value *v; size_t before;
  if(depth>=128 || ++r->nodes>20000) { exr_fail(&r->error,EXR_LIMIT,"PDF page tree depth or node budget exceeded"); return 0; }
  id=resolved(r,id); v=exr_pdf_value_at(r->file,id);
  if(!v || v->kind!=EXR_PDF_DICT) return invalid(r,"PDF page tree child is not a dictionary");
  if(id>=EXR_PDF_MAX_VALUES) { exr_fail(&r->error,EXR_LIMIT,"PDF page tree object index exceeds budget"); return 0; }
  if(r->seen[id/8]&(1u<<(id%8))) return invalid(r,"Repeated or cyclic PDF page tree node");
  r->seen[id/8]|=(unsigned char)(1u<<(id%8));
  if(property(r,id,"Parent")!=parent) return invalid(r,"Invalid PDF page tree parent");
  type=property(r,id,"Type");
  value=property(r,id,"MediaBox");
  if(value!=EXR_PDF_NONE) { if(!rectangle(r,value,state.media)) return 0; state.have_media=1; }
  value=property(r,id,"CropBox");
  if(value!=EXR_PDF_NONE) { if(!rectangle(r,value,state.crop)) return 0; state.have_crop=1; }
  value=property(r,id,"Resources");
  if(value!=EXR_PDF_NONE) {
    if(exr_pdf_value_at(r->file,value)->kind!=EXR_PDF_DICT) return invalid(r,"PDF page resources are not a dictionary");
    state.resources=value;
  }
  value=property(r,id,"Rotate");
  if(value!=EXR_PDF_NONE) {
    int64_t angle; v=exr_pdf_value_at(r->file,value);
    if(v->kind!=EXR_PDF_INT || v->u.integer%90) return invalid(r,"PDF page rotation is not an integer multiple of 90");
    angle=v->u.integer%360; state.rotation=(unsigned)(angle<0 ? angle+360 : angle);
  }
  if(name_is(r,type,"Page")) {
    exr_pdf_page_info page={0};
    if(!state.have_media) return invalid(r,"PDF page is missing an inherited MediaBox");
    if(r->count==10000) { exr_fail(&r->error,EXR_LIMIT,"PDF page count exceeds 10000"); return 0; }
    memcpy(page.media,state.media,sizeof(page.media)); memcpy(page.crop,state.have_crop ? state.crop : state.media,sizeof(page.crop));
    page.object=id; page.resources=state.resources; page.rotation=state.rotation; page.user_unit=1;
    page.contents=property(r,id,"Contents"); page.annotations=property(r,id,"Annots");
    value=property(r,id,"UserUnit");
    if(value!=EXR_PDF_NONE && (!number(r,value,&page.user_unit) || page.user_unit<=0 || page.user_unit>75000)) return invalid(r,"Invalid PDF page UserUnit");
    if(r->error.code!=EXR_OK) return 0;
    if(!exr_grow((void **)&r->pages,&r->capacity,r->count+1,sizeof(*r->pages))) { exr_fail(&r->error,EXR_MEMORY,"PDF page array allocation failed"); return 0; }
    r->pages[r->count++]=page; return 1;
  }
  if(!name_is(r,type,"Pages")) return invalid(r,"Invalid PDF page tree node Type");
  value=property(r,id,"Count"); v=exr_pdf_value_at(r->file,value);
  if(!v || v->kind!=EXR_PDF_INT || v->u.integer<0 || v->u.integer>10000) return invalid(r,"Invalid PDF page subtree Count");
  { size_t declared=(size_t)v->u.integer;
    value=property(r,id,"Kids"); v=exr_pdf_value_at(r->file,value);
    if(!v || v->kind!=EXR_PDF_ARRAY) return invalid(r,"PDF page tree Kids is not an array");
    at=v->first; before=r->count;
    while(at!=EXR_PDF_NONE) {
      uint32_t next; v=exr_pdf_value_at(r->file,at); next=v->next;
      if(v->kind!=EXR_PDF_REF) return invalid(r,"PDF page tree Kids entry is not an indirect reference");
      if(!visit(r,at,id,state,depth+1)) return 0;
      at=next;
    }
    if(r->count-before!=declared) return invalid(r,"PDF page subtree Count does not match its leaves");
  }
  return r->error.code==EXR_OK;
}
exr_status exr_pdf_pages(exr_pdf_file *file,exr_pdf_page_info **pages,size_t *count,exr_error *error) {
  page_reader r={0}; inherited state={0}; uint32_t root; int ok;
  if(pages) *pages=NULL;
  if(count) *count=0;
  if(!file || !pages || !count) return exr_fail(error,EXR_ARGUMENT,"Missing PDF page tree input/output");
  r.file=file; state.resources=EXR_PDF_NONE; r.seen=calloc(EXR_PDF_MAX_VALUES/8,1);
  if(!r.seen) return exr_fail(error,EXR_MEMORY,"PDF page tree validation allocation failed");
  root=property(&r,exr_pdf_root(file),"Pages");
  if(root!=EXR_PDF_NONE && name_is(&r,property(&r,root,"Type"),"Pages")) ok=visit(&r,root,EXR_PDF_NONE,state,0);
  else ok=invalid(&r,"PDF catalog Pages is missing or has invalid Type");
  free(r.seen);
  if(ok) { *pages=r.pages; *count=r.count; } else free(r.pages);
  if(error) *error=r.error;
  return r.error.code;
}
exr_status exr_pdf_content(exr_pdf_file *file,uint32_t contents,exr_buffer *out,exr_error *error) {
  page_reader r={0}; uint32_t at; const exr_pdf_value *v; size_t total=0,pass;
  if(out) memset(out,0,sizeof(*out));
  if(!file || !out) return exr_fail(error,EXR_ARGUMENT,"Missing PDF content input/output");
  r.file=file; contents=resolved(&r,contents);
  for(pass=0;pass<2 && r.error.code==EXR_OK;pass++) {
    v=exr_pdf_value_at(file,contents); at=v && v->kind==EXR_PDF_ARRAY ? v->first : contents;
    while(at!=EXR_PDF_NONE) {
      uint32_t next=EXR_PDF_NONE,id; const unsigned char *data; size_t size;
      v=exr_pdf_value_at(file,contents); if(v && v->kind==EXR_PDF_ARRAY) next=exr_pdf_value_at(file,at)->next;
      id=resolved(&r,at);
      if(r.error.code!=EXR_OK || exr_pdf_stream_data(file,id,&data,&size,&r.error)!=EXR_OK) break;
      if(!pass) {
        if(size>EXR_MAX_TEXT-total) { exr_fail(&r.error,EXR_LIMIT,"PDF page content exceeds 64 MiB"); break; }
        total+=size;
      } else { if(size) memcpy(out->data+out->size,data,size); out->size+=size; }
      at=next;
    }
    if(!pass && r.error.code==EXR_OK) {
      out->data=malloc(total+1); out->capacity=total+1;
      if(!out->data) exr_fail(&r.error,EXR_MEMORY,"PDF page content allocation failed");
    }
  }
  if(r.error.code!=EXR_OK) { free(out->data); memset(out,0,sizeof(*out)); }
  else out->data[out->size]=0;
  if(error) *error=r.error;
  return r.error.code;
}
