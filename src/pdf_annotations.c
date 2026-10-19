/* SPDX-License-Identifier: MIT */
#include "pdf_internal.h"
#define BUDGET ((size_t)8*1024*1024)
static exr_status charge(size_t *bytes,size_t n,exr_error *e) {
  if(n>BUDGET-*bytes) return exr_fail(e,EXR_LIMIT,"PDF page annotations exceed 8 MiB");
  *bytes+=n; return EXR_OK;
}
static exr_status array(exr_pdf_file *file,uint32_t id,double **out,size_t *count,size_t *bytes,exr_error *e) {
  const exr_pdf_value *v; uint32_t at,first; size_t n=0,i; double *values=NULL; exr_status status;
  *out=NULL; *count=0; status=exr_pdf_resolve(file,id,&id,e); if(status!=EXR_OK) return status;
  v=exr_pdf_value_at(file,id); if(!v || v->kind==EXR_PDF_NULL) return EXR_OK;
  if(v->kind!=EXR_PDF_ARRAY) return exr_fail(e,EXR_FORMAT,"Annotation geometry is not an array");
  first=v->first;
  for(at=first;at!=EXR_PDF_NONE;at=exr_pdf_value_at(file,at)->next) n++;
  if(n>BUDGET/sizeof(double)) return exr_fail(e,EXR_LIMIT,"Annotation geometry array is too large");
  status=charge(bytes,n*sizeof(double),e); if(status!=EXR_OK || !n) return status;
  values=malloc(n*sizeof(*values)); if(!values) return exr_fail(e,EXR_MEMORY,"Annotation geometry allocation failed");
  for(at=first,i=0;at!=EXR_PDF_NONE;i++) {
    uint32_t next=exr_pdf_value_at(file,at)->next,resolved;
    status=exr_pdf_resolve(file,at,&resolved,e); if(status!=EXR_OK) goto failure;
    v=exr_pdf_value_at(file,resolved);
    if(!v || (v->kind!=EXR_PDF_INT && v->kind!=EXR_PDF_REAL)) { status=exr_fail(e,EXR_FORMAT,"Annotation geometry is not numeric"); goto failure; }
    values[i]=v->kind==EXR_PDF_INT ? (double)v->u.integer : v->u.number;
    if(!isfinite(values[i]) || fabs(values[i])>1e7) { status=exr_fail(e,EXR_FORMAT,"Annotation coordinate exceeds source bounds"); goto failure; }
    at=next;
  }
  *out=values; *count=n; return EXR_OK;
failure:
  free(values); return status;
}
static exr_status annotation(exr_pdf_file *file,uint32_t id,size_t *bytes,exr_page_annotation *out,exr_error *e) {
  static const char *names[]={"Contents","T","Subj","CreationDate","M"};
  static const char *keys[]={"http://purl.org/dc/terms/description","http://purl.org/dc/terms/creator","http://purl.org/dc/terms/subject","http://ns.adobe.com/xap/1.0/CreateDate","http://ns.adobe.com/xap/1.0/ModifyDate"};
  uint32_t subtype; const exr_pdf_value *v; const unsigned char *name; size_t n,i,at; char *copy; double *values=NULL; exr_status status;
  exr_metadata_entry *properties; uint32_t cp;
  status=exr_pdf_resolve(file,exr_pdf_get(file,id,"Subtype"),&subtype,e); if(status!=EXR_OK) return status;
  v=exr_pdf_value_at(file,subtype); name=exr_pdf_bytes(file,subtype,&n);
  if(!v || v->kind!=EXR_PDF_NAME || !n || !name || memchr(name,0,n)) return exr_fail(e,EXR_FORMAT,"Missing PDF annotation subtype");
  if(n>65536) return exr_fail(e,EXR_LIMIT,"Annotation subtype exceeds 64 KiB");
  for(at=0;at<n;) if(!exr_next((const char *)name,n,&at,&cp)) return exr_fail(e,EXR_FORMAT,"Annotation subtype is not UTF-8");
  status=charge(bytes,n+1,e); if(status!=EXR_OK) return status;
  out->kind=exr_copy((const char *)name,n); if(!out->kind) return exr_fail(e,EXR_MEMORY,"Annotation subtype allocation failed");
  status=exr_pdf_metadata_string(file,exr_pdf_get(file,id,"NM"),&copy,e); if(status!=EXR_OK) return status;
  out->id=copy; if(copy && (status=charge(bytes,strlen(copy)+1,e))!=EXR_OK) return status;
  status=array(file,exr_pdf_get(file,id,"Rect"),&values,&n,bytes,e); if(status!=EXR_OK) return status;
  if(n!=4) { free(values); return exr_fail(e,EXR_FORMAT,"Annotation Rect must have four coordinates"); }
  for(i=0;i<2;i++) { out->bounds[i]=fmin(values[i],values[i+2]); out->bounds[i+2]=fmax(values[i],values[i+2]); } free(values);
  status=array(file,exr_pdf_get(file,id,"QuadPoints"),&values,&n,bytes,e); if(status!=EXR_OK) return status;
  if(n%8) { free(values); return exr_fail(e,EXR_FORMAT,"Annotation QuadPoints must contain groups of eight"); }
  out->quads=values; out->quad_count=n/8;
  status=charge(bytes,5*sizeof(*properties),e); if(status!=EXR_OK) return status;
  properties=calloc(5,sizeof(*properties)); if(!properties) return exr_fail(e,EXR_MEMORY,"Annotation properties allocation failed"); out->properties=properties;
  for(i=0;i<5;i++) {
    char *key; status=exr_pdf_metadata_string(file,exr_pdf_get(file,id,names[i]),&copy,e); if(status!=EXR_OK) return status;
    if(!copy) continue;
    status=charge(bytes,strlen(keys[i])+strlen(copy)+2,e); if(status!=EXR_OK) { free(copy); return status; }
    key=exr_copy(keys[i],strlen(keys[i])); if(!key) { free(copy); return exr_fail(e,EXR_MEMORY,"Annotation key allocation failed"); }
    properties[out->property_count++]=(exr_metadata_entry){key,copy};
  }
  return EXR_OK;
}
exr_status exr_pdf_page_annotations(exr_pdf_file *file,uint32_t id,const exr_control *control,exr_page_annotation **out,size_t *count,exr_error *e) {
  const exr_pdf_value *v; exr_page_annotation *entries=NULL; size_t n=0,used=0,bytes=0; uint32_t at,first; exr_status status;
  *out=NULL; *count=0; status=exr_pdf_resolve(file,id,&id,e); if(status!=EXR_OK) return status;
  v=exr_pdf_value_at(file,id); if(!v || v->kind==EXR_PDF_NULL) return exr_fail(e,EXR_OK,"");
  if(v->kind!=EXR_PDF_ARRAY) return exr_fail(e,EXR_FORMAT,"PDF Annots is not an array");
  first=v->first;
  for(at=first;at!=EXR_PDF_NONE;at=exr_pdf_value_at(file,at)->next) { if(n++==4096) return exr_fail(e,EXR_LIMIT,"PDF page exceeds 4096 annotations"); }
  if(n) { entries=calloc(n,sizeof(*entries)); if(!entries) return exr_fail(e,EXR_MEMORY,"PDF annotations allocation failed"); bytes=n*sizeof(*entries); }
  for(at=first;at!=EXR_PDF_NONE;) {
    uint32_t next=exr_pdf_value_at(file,at)->next,resolved;
    status=exr_control_poll(control,EXR_STAGE_READ,used,n,e); if(status!=EXR_OK) goto failure;
    status=exr_pdf_resolve(file,at,&resolved,e); if(status!=EXR_OK) goto failure;
    v=exr_pdf_value_at(file,resolved);
    if(v && v->kind!=EXR_PDF_NULL) {
      if(v->kind!=EXR_PDF_DICT) { status=exr_fail(e,EXR_FORMAT,"PDF annotation is not a dictionary"); goto failure; }
      status=annotation(file,resolved,&bytes,&entries[used++],e); if(status!=EXR_OK) goto failure;
    }
    at=next;
  }
  if(!used) { free(entries); entries=NULL; }
  *out=entries; *count=used; return exr_fail(e,EXR_OK,"");
failure:
  exr_page_annotations_free(entries,used); return status;
}
