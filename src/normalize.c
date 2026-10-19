/* SPDX-License-Identifier: MIT */
#include "normalize_internal.h"
#include "normalize_data.h"

static unsigned combining(uint32_t cp) {
  size_t lo=0,hi=sizeof(exr_canonical_classes)/sizeof(*exr_canonical_classes);
  while(lo<hi) {
    size_t m=lo+(hi-lo)/2;
    if(cp<exr_canonical_classes[m].first) hi=m;
    else if(cp>exr_canonical_classes[m].last) lo=m+1;
    else return exr_canonical_classes[m].value;
  }
  return 0;
}
static uint32_t compose(uint32_t a,uint32_t b) {
  size_t lo=0,hi=sizeof(exr_canonical_compositions)/sizeof(*exr_canonical_compositions);
  if(a>=0x1100 && a<0x1113 && b>=0x1161 && b<0x1176) return 0xac00+(a-0x1100)*588+(b-0x1161)*28;
  if(a>=0xac00 && a<=0xd7a3 && (a-0xac00)%28==0 && b>0x11a7 && b<0x11c3) return a+b-0x11a7;
  while(lo<hi) {
    size_t m=lo+(hi-lo)/2;
    if(a<exr_canonical_compositions[m].first || (a==exr_canonical_compositions[m].first && b<exr_canonical_compositions[m].second)) hi=m;
    else if(a>exr_canonical_compositions[m].first || b>exr_canonical_compositions[m].second) lo=m+1;
    else return exr_canonical_compositions[m].result;
  }
  return 0;
}
static exr_status work(size_t *done,const exr_control *control,exr_error *e) {
  if(*done>=64u*1024u*1024u) return exr_fail(e,EXR_LIMIT,"Canonical normalization work limit exceeded");
  (*done)++;
  return !(*done&1023) ? exr_control_cancel(control,e) : EXR_OK;
}
exr_status exr_normalize_nfc(const exr_normal_scalar *in,size_t count,
  exr_normal_scalar *out,size_t capacity,size_t *written,const exr_control *control,size_t *operations,exr_error *e) {
  size_t i,j,k,n=0,used=0,starter=SIZE_MAX,local_work=0; size_t *done=operations ? operations : &local_work; unsigned last=0; exr_status status;
  if(!written) return exr_fail(e,EXR_ARGUMENT,"Missing normalized scalar count");
  *written=0;
  if((!in && count) || (!out && capacity) || (count && in==out)) return exr_fail(e,EXR_ARGUMENT,"Invalid normalization buffers");
  if(count>4096 || capacity>16384) return exr_fail(e,EXR_LIMIT,"Canonical normalization scalar limit exceeded");
  status=exr_control_cancel(control,e); if(status!=EXR_OK) return status;
  for(i=0;i<count;i++) {
    uint32_t cp=in[i].cp,hangul[3]; const uint32_t *parts=&cp;size_t length=1,lo=0,hi=sizeof(exr_canonical_decompositions)/sizeof(*exr_canonical_decompositions);
    if(cp>0x10ffff || (cp>=0xd800 && cp<=0xdfff) || in[i].first>in[i].last)
      return exr_fail(e,EXR_ENCODING,"Invalid normalization scalar or source interval");
    if(cp>=0xac00 && cp<=0xd7a3) {
      uint32_t s=cp-0xac00;hangul[0]=0x1100+s/588;hangul[1]=0x1161+(s%588)/28;hangul[2]=0x11a7+s%28;
      parts=hangul;length=s%28 ? 3 : 2;
    } else while(lo<hi) {
      size_t m=lo+(hi-lo)/2;
      if(cp<exr_canonical_decompositions[m].cp) hi=m;
      else if(cp>exr_canonical_decompositions[m].cp) lo=m+1;
      else { parts=exr_canonical_decompositions[m].parts;length=exr_canonical_decompositions[m].length;break; }
    }
    if(length>capacity-used) return exr_fail(e,EXR_LIMIT,"Canonical normalization output buffer exceeded");
    for(j=0;j<length;j++) {
      exr_normal_scalar value={parts[j],in[i].first,in[i].last}; unsigned cc=combining(parts[j]);k=used++;
      while(k && cc && combining(out[k-1].cp)>cc) {
        status=work(done,control,e); if(status!=EXR_OK) return status;
        out[k]=out[k-1];k--;
      }
      out[k]=value;status=work(done,control,e);if(status!=EXR_OK) return status;
    }
  }
  for(i=0;i<used;i++) {
    unsigned cc=combining(out[i].cp);
    uint32_t composed=starter!=SIZE_MAX && (!last || last<cc) ? compose(out[starter].cp,out[i].cp) : 0;
    if(composed) {
      out[starter].cp=composed;
      if(out[i].first<out[starter].first) out[starter].first=out[i].first;
      if(out[i].last>out[starter].last) out[starter].last=out[i].last;
    } else { if(!cc) starter=n;out[n++]=out[i];last=cc; }
    status=work(done,control,e);if(status!=EXR_OK) return status;
  }
  status=exr_control_cancel(control,e);if(status!=EXR_OK) return status;
  *written=n;return exr_fail(e,EXR_OK,"");
}
