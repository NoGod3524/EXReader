/* SPDX-License-Identifier: GPL-3.0-only */
#include "pdf_function_internal.h"
struct exr_pdf_function {
  unsigned type,outputs,count,has_range;
  double domain[2],range[8],exponent,first[4],last[4];
  double *bounds,*encode;
  struct exr_pdf_function **children;
  size_t bytes,cost;
};
typedef struct {
  exr_pdf_file *file; const exr_control *control; exr_error *error;
  uint32_t active[16]; size_t nodes,bytes;
} function_reader;
static uint32_t get(function_reader *r,uint32_t dictionary,const char *key) {
  uint32_t value=EXR_PDF_NONE; const exr_pdf_value *v;
  if(r->error->code==EXR_OK) (void)exr_pdf_resolve(r->file,exr_pdf_get(r->file,dictionary,key),&value,r->error);
  v=exr_pdf_value_at(r->file,value); return v && v->kind==EXR_PDF_NULL ? EXR_PDF_NONE : value;
}
static int number(function_reader *r,uint32_t id,double *out) {
  const exr_pdf_value *v=exr_pdf_value_at(r->file,id);
  if(!v || (v->kind!=EXR_PDF_INT && v->kind!=EXR_PDF_REAL)) return 0;
  *out=v->kind==EXR_PDF_INT ? (double)v->u.integer : v->u.number;
  return isfinite(*out) && fabs(*out)<=1e7;
}
static int array(function_reader *r,uint32_t id,uint32_t *ids,size_t capacity,size_t *count) {
  const exr_pdf_value *v=exr_pdf_value_at(r->file,id); uint32_t at; *count=0;
  if(!v || v->kind!=EXR_PDF_ARRAY) return 0;
  for(at=v->first;at!=EXR_PDF_NONE;) {
    uint32_t next; v=exr_pdf_value_at(r->file,at);
    if(!v) return 0;
    if(*count==capacity) { exr_fail(r->error,EXR_LIMIT,"PDF function array exceeds work limit"); return 0; }
    next=v->next;
    if(exr_pdf_resolve(r->file,at,&ids[(*count)++],r->error)!=EXR_OK) return 0;
    at=next;
  }
  return 1;
}
static int numbers(function_reader *r,uint32_t id,double *out,size_t size) {
  uint32_t ids[128]; size_t n,i;
  if(size>128 || !array(r,id,ids,128,&n) || n!=size) return 0;
  for(i=0;i<n;i++) if(!number(r,ids[i],out+i)) return 0;
  return 1;
}
void exr_pdf_function_free(exr_pdf_function *f) {
  size_t i; if(!f) return;
  if(f->children) for(i=0;i<f->count;i++) exr_pdf_function_free(f->children[i]);
  free(f->children); free(f->bounds); free(f->encode); free(f);
}
static exr_status open_function(function_reader *r,uint32_t id,unsigned outputs,unsigned depth,exr_pdf_function **out) {
  exr_pdf_function *f=NULL; const exr_pdf_value *value; uint32_t ids[64],field; size_t i,count; exr_status status=EXR_FORMAT;
  *out=NULL;
  if(depth==16 || ++r->nodes>1024) return exr_fail(r->error,EXR_LIMIT,"PDF function exceeds 16 levels or 1024 nodes");
  if(exr_control_cancel(r->control,r->error)!=EXR_OK) return EXR_CANCELLED;
  if(exr_pdf_resolve(r->file,id,&id,r->error)!=EXR_OK) return r->error->code;
  for(i=0;i<depth;i++) if(r->active[i]==id) return exr_fail(r->error,EXR_FORMAT,"Cyclic PDF function");
  r->active[depth]=id;
  value=exr_pdf_value_at(r->file,id); if(!value || (value->kind!=EXR_PDF_DICT && value->kind!=EXR_PDF_STREAM)) goto bad;
  field=get(r,id,"FunctionType"); value=exr_pdf_value_at(r->file,field);
  if(!value || value->kind!=EXR_PDF_INT || (value->u.integer!=2 && value->u.integer!=3)) goto bad;
  f=calloc(1,sizeof(*f)); if(!f) goto memory;
  f->type=(unsigned)value->u.integer; f->outputs=outputs; f->bytes=sizeof(*f); r->bytes+=sizeof(*f);
  if(!numbers(r,get(r,id,"Domain"),f->domain,2) || f->domain[0]>f->domain[1]) goto bad;
  field=get(r,id,"Range");
  if(field!=EXR_PDF_NONE) {
    f->has_range=1; if(!numbers(r,field,f->range,2*outputs)) goto bad;
    for(i=0;i<outputs;i++) if(f->range[2*i]>f->range[2*i+1]) goto bad;
  }
  if(f->type==2) {
    double endpoint[2];
    field=get(r,id,"C0"); if(field==EXR_PDF_NONE) { if(outputs!=1) goto bad; } else if(!numbers(r,field,f->first,outputs)) goto bad;
    field=get(r,id,"C1");
    if(field==EXR_PDF_NONE) { if(outputs!=1) goto bad; f->last[0]=1; } else if(!numbers(r,field,f->last,outputs)) goto bad;
    if(!number(r,get(r,id,"N"),&f->exponent)) goto bad;
    if((f->exponent!=floor(f->exponent) && f->domain[0]<0) ||
       (f->exponent<0 && f->domain[0]<=0 && f->domain[1]>=0)) goto bad;
    endpoint[0]=pow(f->domain[0],f->exponent); endpoint[1]=pow(f->domain[1],f->exponent);
    for(i=0;i<outputs;i++) {
      if(!isfinite(endpoint[0]) || !isfinite(endpoint[1]) ||
         !isfinite(f->first[i]+endpoint[0]*(f->last[i]-f->first[i])) ||
         !isfinite(f->first[i]+endpoint[1]*(f->last[i]-f->first[i]))) goto bad;
    }
    f->cost=32+outputs;
  } else {
    size_t extra;
    if(!array(r,get(r,id,"Functions"),ids,64,&count) || !count || (count>1 && f->domain[0]==f->domain[1])) goto bad;
    f->count=(unsigned)count; extra=count*(sizeof(*f->children)+3*sizeof(double));
    if(extra>(size_t)1024*1024-r->bytes) { status=exr_fail(r->error,EXR_LIMIT,"PDF function payload exceeds 1 MiB"); goto done; }
    f->children=calloc(count,sizeof(*f->children)); f->bounds=calloc(count,sizeof(double)); f->encode=calloc(2*count,sizeof(double));
    if(!f->children || !f->bounds || !f->encode) goto memory;
    f->bytes+=extra; r->bytes+=extra;
    if(!numbers(r,get(r,id,"Bounds"),f->bounds,count-1) || !numbers(r,get(r,id,"Encode"),f->encode,2*count)) goto bad;
    for(i=0;i+1<count;i++) if(f->bounds[i]<f->domain[0] || f->bounds[i]>f->domain[1] || (i && f->bounds[i]<=f->bounds[i-1])) goto bad;
    for(i=0;i<count;i++) {
      status=open_function(r,ids[i],outputs,depth+1,&f->children[i]); if(status!=EXR_OK) goto done;
      f->bytes+=f->children[i]->bytes; if(f->children[i]->cost>f->cost) f->cost=f->children[i]->cost;
    }
    f->cost+=10;
  }
  if(r->bytes>1024*1024) { status=exr_fail(r->error,EXR_LIMIT,"PDF function payload exceeds 1 MiB"); goto done; }
  if(r->error->code!=EXR_OK) { status=r->error->code; goto done; }
  *out=f; return EXR_OK;
memory:
  status=exr_fail(r->error,EXR_MEMORY,"PDF function allocation failed"); goto done;
bad:
  if(r->error->code==EXR_OK) exr_fail(r->error,EXR_FORMAT,"Unsupported or invalid PDF scalar function");
  status=r->error->code;
done:
  exr_pdf_function_free(f); return status;
}
exr_status exr_pdf_function_open(exr_pdf_file *file,uint32_t value,unsigned outputs,const exr_control *control,exr_pdf_function **out,exr_error *error) {
  exr_error local={0}; function_reader r={0};
  if(out) *out=NULL;
  if(!file || !out || !outputs || outputs>4) return exr_fail(error,EXR_ARGUMENT,"Invalid PDF function input/output");
  r.file=file; r.control=control; r.error=error ? error : &local; memset(r.error,0,sizeof(*r.error));
  return open_function(&r,value,outputs,0,out);
}
exr_status exr_pdf_function_eval(const exr_pdf_function *f,double input,double out[4],exr_error *error) {
  double x=fmax(f->domain[0],fmin(f->domain[1],input)); size_t i;
  if(f->type==2) {
    double raised=pow(x,f->exponent);
    for(i=0;i<f->outputs;i++) out[i]=f->first[i]+raised*(f->last[i]-f->first[i]);
  } else {
    size_t lo=0,hi=f->count-1; double begin,end,encoded; exr_status status;
    while(lo<hi) { size_t mid=lo+(hi-lo)/2; if(x>=f->bounds[mid]) lo=mid+1; else hi=mid; }
    begin=lo ? f->bounds[lo-1] : f->domain[0]; end=lo+1<f->count ? f->bounds[lo] : f->domain[1];
    encoded=f->encode[2*lo]; if(end!=begin) encoded+=(x-begin)/(end-begin)*(f->encode[2*lo+1]-encoded);
    status=exr_pdf_function_eval(f->children[lo],encoded,out,error); if(status!=EXR_OK) return status;
  }
  for(i=0;i<f->outputs;i++) {
    if(!isfinite(out[i])) return exr_fail(error,EXR_FORMAT,"Nonfinite PDF function result");
    if(f->has_range) out[i]=fmax(f->range[2*i],fmin(f->range[2*i+1],out[i]));
  }
  return EXR_OK;
}
size_t exr_pdf_function_memory(const exr_pdf_function *f) { return f ? f->bytes : 0; }
size_t exr_pdf_function_cost(const exr_pdf_function *f) { return f ? f->cost : 0; }
