/* SPDX-License-Identifier: MIT */
#include "pdf_function_internal.h"
#include "pdf_calculator_internal.h"
struct exr_pdf_function {
  unsigned type,inputs,outputs,count,has_range,bits,order;
  double domain[2*EXR_PDF_MAX_COLORANTS],range[8],exponent,first[4],last[4];
  double *bounds,*encode;
  struct exr_pdf_function **children;
  unsigned char *samples; size_t sample_count;
  size_t sizes[EXR_PDF_MAX_COLORANTS],strides[EXR_PDF_MAX_COLORANTS];
  double decode[8];
  exr_pdf_calculator *calculator;
  exr_control control;
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
  free(f->children); free(f->bounds); free(f->encode); free(f->samples); exr_pdf_calculator_free(f->calculator); free(f);
}
static exr_status open_function(function_reader *r,uint32_t id,unsigned inputs,unsigned outputs,unsigned depth,exr_pdf_function **out) {
  exr_pdf_function *f=NULL; const exr_pdf_value *value; uint32_t ids[64],field; size_t i,count; int stream; exr_status status=EXR_FORMAT;
  *out=NULL;
  if(depth==16 || ++r->nodes>1024) return exr_fail(r->error,EXR_LIMIT,"PDF function exceeds 16 levels or 1024 nodes");
  if(exr_control_cancel(r->control,r->error)!=EXR_OK) return EXR_CANCELLED;
  if(exr_pdf_resolve(r->file,id,&id,r->error)!=EXR_OK) return r->error->code;
  for(i=0;i<depth;i++) if(r->active[i]==id) return exr_fail(r->error,EXR_FORMAT,"Cyclic PDF function");
  r->active[depth]=id;
  value=exr_pdf_value_at(r->file,id); if(!value || (value->kind!=EXR_PDF_DICT && value->kind!=EXR_PDF_STREAM)) goto bad;
  stream=value->kind==EXR_PDF_STREAM;
  field=get(r,id,"FunctionType"); value=exr_pdf_value_at(r->file,field);
  if(!value || value->kind!=EXR_PDF_INT || (value->u.integer!=0 && value->u.integer!=2 && value->u.integer!=3 && value->u.integer!=4)) goto bad;
  if(sizeof(*f)>(size_t)1024*1024-r->bytes) return exr_fail(r->error,EXR_LIMIT,"PDF function payload exceeds 1 MiB");
  f=calloc(1,sizeof(*f)); if(!f) goto memory;
  f->type=(unsigned)value->u.integer; f->inputs=inputs; f->outputs=outputs; f->bytes=sizeof(*f); r->bytes+=sizeof(*f);
  if(r->control) f->control=*r->control;
  if(!numbers(r,get(r,id,"Domain"),f->domain,2*inputs)) goto bad;
  for(i=0;i<inputs;i++) if(f->domain[2*i]>f->domain[2*i+1]) goto bad;
  if(inputs!=1 && f->type!=0 && f->type!=4) { status=exr_fail(r->error,EXR_FORMAT,"PDF Type 2/3 functions require one input"); goto done; }
  field=get(r,id,"Range");
  if(field!=EXR_PDF_NONE) {
    f->has_range=1; if(!numbers(r,field,f->range,2*outputs)) goto bad;
    for(i=0;i<outputs;i++) if(f->range[2*i]>f->range[2*i+1]) goto bad;
  }
  if(f->type==4) {
    const unsigned char *source; size_t size,extra;
    if(!stream || !f->has_range) goto bad;
    status=exr_pdf_stream_data(r->file,id,&source,&size,r->error); if(status!=EXR_OK) goto done;
    status=exr_pdf_calculator_open(source,size,r->control,&f->calculator,r->error); if(status!=EXR_OK) goto done;
    extra=exr_pdf_calculator_memory(f->calculator);
    if(extra>(size_t)1024*1024-r->bytes) { status=exr_fail(r->error,EXR_LIMIT,"PDF function payload exceeds 1 MiB"); goto done; }
    f->bytes+=extra; r->bytes+=extra; f->cost=exr_pdf_calculator_cost(f->calculator)+2*outputs+2*inputs;
  } else if(f->type==0) {
    const unsigned char *samples; size_t size,needed,extra=2*inputs*sizeof(double),corners=1; uint64_t packed;
    if(!stream || !f->has_range || !array(r,get(r,id,"Size"),ids,64,&count) || count!=inputs) goto bad;
    f->sample_count=1;
    for(i=0;i<inputs;i++) {
      value=exr_pdf_value_at(r->file,ids[i]);
      if(!value || value->kind!=EXR_PDF_INT || value->u.integer<=0) goto bad;
      /* Even a one-bit table cannot exceed the function graph payload budget. */
      if((uint64_t)value->u.integer>UINT32_MAX || (uint64_t)value->u.integer>8388608/f->sample_count) {
        status=exr_fail(r->error,EXR_LIMIT,"PDF sample table exceeds size limit"); goto done;
      }
      f->sizes[i]=(size_t)value->u.integer; f->strides[i]=f->sample_count*outputs; f->sample_count*=f->sizes[i];
    }
    field=get(r,id,"BitsPerSample"); value=exr_pdf_value_at(r->file,field);
    if(!value || value->kind!=EXR_PDF_INT ||
       (value->u.integer!=1 && value->u.integer!=2 && value->u.integer!=4 && value->u.integer!=8 &&
        value->u.integer!=12 && value->u.integer!=16 && value->u.integer!=24 && value->u.integer!=32)) goto bad;
    f->bits=(unsigned)value->u.integer; packed=(uint64_t)f->sample_count*outputs*f->bits;
    if(extra>(size_t)1024*1024-r->bytes || (packed+7)/8>(size_t)1024*1024-r->bytes-extra) { status=exr_fail(r->error,EXR_LIMIT,"PDF function payload exceeds 1 MiB"); goto done; }
    needed=(size_t)((packed+7)/8);
    field=get(r,id,"Order"); value=exr_pdf_value_at(r->file,field);
    if(field!=EXR_PDF_NONE && (!value || value->kind!=EXR_PDF_INT || (value->u.integer!=1 && value->u.integer!=3))) goto bad;
    f->order=field==EXR_PDF_NONE ? 1 : (unsigned)value->u.integer;
    for(i=0;i<inputs;i++) {
      size_t width=f->order==3 ? 4 : 2; if(width>f->sizes[i]) width=f->sizes[i];
      if(corners>65536/width) { status=exr_fail(r->error,EXR_LIMIT,"PDF sample interpolation exceeds 65536 corners"); goto done; }
      corners*=width;
    }
    f->encode=calloc(2*inputs,sizeof(double)); if(!f->encode) goto memory;
    for(i=0;i<inputs;i++) f->encode[2*i+1]=(double)(f->sizes[i]-1);
    field=get(r,id,"Encode"); if(field!=EXR_PDF_NONE && !numbers(r,field,f->encode,2*inputs)) goto bad;
    memcpy(f->decode,f->range,2*outputs*sizeof(double));
    field=get(r,id,"Decode"); if(field!=EXR_PDF_NONE && !numbers(r,field,f->decode,2*outputs)) goto bad;
    status=exr_pdf_stream_data(r->file,id,&samples,&size,r->error); if(status!=EXR_OK) goto done;
    if(size!=needed) goto bad;
    f->samples=malloc(needed); if(!f->samples) goto memory;
    memcpy(f->samples,samples,needed); f->bytes+=needed+extra; r->bytes+=needed+extra;
    f->cost=32*inputs+corners*(4*inputs+8*outputs)+4*outputs;
  } else if(f->type==2) {
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
      status=open_function(r,ids[i],1,outputs,depth+1,&f->children[i]); if(status!=EXR_OK) goto done;
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
  if(r->error->code==EXR_OK) exr_fail(r->error,EXR_FORMAT,"Unsupported or invalid PDF function");
  status=r->error->code;
done:
  exr_pdf_function_free(f); return status;
}
exr_status exr_pdf_function_open_inputs(exr_pdf_file *file,uint32_t value,unsigned inputs,unsigned outputs,const exr_control *control,exr_pdf_function **out,exr_error *error) {
  exr_error local={0}; function_reader r={0};
  if(out) *out=NULL;
  if(!file || !out || !inputs || inputs>EXR_PDF_MAX_COLORANTS || !outputs || outputs>4) return exr_fail(error,EXR_ARGUMENT,"Invalid PDF function input/output");
  r.file=file; r.control=control; r.error=error ? error : &local; memset(r.error,0,sizeof(*r.error));
  return open_function(&r,value,inputs,outputs,0,out);
}
exr_status exr_pdf_function_open(exr_pdf_file *file,uint32_t value,unsigned outputs,const exr_control *control,exr_pdf_function **out,exr_error *error) {
  return exr_pdf_function_open_inputs(file,value,1,outputs,control,out,error);
}
static double sample_value(const exr_pdf_function *f,size_t index) {
  uint64_t bit=(uint64_t)index*f->bits,value=0,mask=(UINT64_C(1)<<f->bits)-1;
  unsigned skip=(unsigned)(bit&7),count=(skip+f->bits+7)/8,i;
  for(i=0;i<count;i++) value=(value<<8)|f->samples[(size_t)(bit>>3)+i];
  value=(value>>(count*8-skip-f->bits))&mask; return (double)value/(double)mask;
}
static exr_status sampled_value(const exr_pdf_function *f,const double *input,double out[4],exr_error *error) {
  size_t offsets[EXR_PDF_MAX_COLORANTS][4],base=0,corners=1,corner,i; unsigned active=0,widths[EXR_PDF_MAX_COLORANTS];
  double weights[EXR_PDF_MAX_COLORANTS][4];
  for(i=0;i<f->inputs;i++) {
    double encoded=f->encode[2*i],fraction; size_t first;
    if(f->domain[2*i+1]!=f->domain[2*i]) encoded+=(input[i]-f->domain[2*i])/(f->domain[2*i+1]-f->domain[2*i])*(f->encode[2*i+1]-encoded);
    encoded=fmax(0,fmin((double)(f->sizes[i]-1),encoded)); first=(size_t)floor(encoded); fraction=encoded-(double)first;
    if(fraction==0) base+=first*f->strides[i];
    else {
      unsigned j,width=2;
      if(f->order==3 && f->sizes[i]>2) {
        double t=fraction,t2=t*t,t3=t2*t;
        double w[4]={-.5*t+t2-.5*t3,1-2.5*t2+1.5*t3,.5*t+2*t2-1.5*t3,-.5*t2+.5*t3};
        size_t points[4]={first ? first-1 : 0,first,first+1,first+2<f->sizes[i] ? first+2 : first+1};
        /* Cardinal cubic convolution (a=-1/2); replicate endpoint samples. */
        width=0;
        for(j=0;j<4;j++) {
          size_t offset=points[j]*f->strides[i];
          if(width && offsets[active][width-1]==offset) weights[active][width-1]+=w[j];
          else { offsets[active][width]=offset; weights[active][width++]=w[j]; }
        }
      } else {
        offsets[active][0]=first*f->strides[i]; offsets[active][1]=(first+1)*f->strides[i];
        weights[active][0]=1-fraction; weights[active][1]=fraction;
      }
      widths[active++]=width; corners*=width;
    }
  }
  for(i=0;i<f->outputs;i++) out[i]=0;
  for(corner=0;corner<corners;corner++) {
    size_t index=base,ordinal=corner; double weight=1; unsigned axis;
    if(!(corner&255) && exr_control_cancel(&f->control,error)!=EXR_OK) return EXR_CANCELLED;
    for(axis=0;axis<active;axis++) {
      unsigned at=(unsigned)(ordinal%widths[axis]); ordinal/=widths[axis];
      index+=offsets[axis][at]; weight*=weights[axis][at];
    }
    for(i=0;i<f->outputs;i++) out[i]+=weight*sample_value(f,index+i);
  }
  for(i=0;i<f->outputs;i++) out[i]=f->decode[2*i]+out[i]*(f->decode[2*i+1]-f->decode[2*i]);
  return EXR_OK;
}
exr_status exr_pdf_function_eval_inputs(const exr_pdf_function *f,const double *input,double out[4],exr_error *error) {
  double values[EXR_PDF_MAX_COLORANTS],x; size_t i;
  if(!f || !f->inputs || !input || !out) return exr_fail(error,EXR_ARGUMENT,"Invalid PDF function evaluation");
  for(i=0;i<f->inputs;i++) { if(!isfinite(input[i])) return exr_fail(error,EXR_FORMAT,"Nonfinite PDF function input"); values[i]=fmax(f->domain[2*i],fmin(f->domain[2*i+1],input[i])); }
  x=values[0];
  if(f->type==4) {
    exr_status status=exr_pdf_calculator_eval_inputs(f->calculator,values,f->inputs,f->outputs,out,error); if(status!=EXR_OK) return status;
  } else if(f->type==0) {
    exr_status status=sampled_value(f,values,out,error); if(status!=EXR_OK) return status;
  } else if(f->type==2) {
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
exr_status exr_pdf_function_eval(const exr_pdf_function *f,double input,double out[4],exr_error *error) {
  if(!f || f->inputs!=1) return exr_fail(error,EXR_ARGUMENT,"PDF scalar evaluation requires one input");
  return exr_pdf_function_eval_inputs(f,&input,out,error);
}
size_t exr_pdf_function_memory(const exr_pdf_function *f) { return f ? f->bytes : 0; }
size_t exr_pdf_function_cost(const exr_pdf_function *f) { return f ? f->cost : 0; }
