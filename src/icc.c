/* SPDX-License-Identifier: MIT */
#include "icc_internal.h"
#ifdef EXR_ENABLE_ICC
#include <lcms2.h>
#include <lcms2_plugin.h>
#include "miniz.h"
#include "default_cmyk_profile.h"
#define ICC_BUDGET ((size_t)16*1024*1024)
struct exr_icc {
  cmsContext context;cmsHTRANSFORM transform;cmsHTRANSFORM intents[4];cmsColorSpaceSignature space;
  size_t bytes,cost;unsigned channels;int limited,failed,invalid,cancelled;
  exr_control control;cmsHTRANSFORM reverse;exr_error deferred;
};
typedef union {
  struct { size_t size;exr_icc *owner; } value;
#ifdef _MSC_VER
  __declspec(align(16)) unsigned char alignment[16];
#else
  max_align_t alignment;
#endif
} icc_allocation;
#ifdef _MSC_VER
static __declspec(thread) exr_icc *creating;
#else
static _Thread_local exr_icc *creating;
#endif
static void *allocate(cmsContext context,cmsUInt32Number size) {
  exr_icc *p=context ? cmsGetContextUserData(context) : NULL;icc_allocation *a;size_t bytes=(size_t)size+sizeof(*a);
  if(!p) p=creating;
  if(!p) return NULL;
  if(exr_control_cancel(&p->control,NULL)!=EXR_OK) { p->cancelled=1;return NULL; }
  if(bytes>ICC_BUDGET-p->bytes) { p->limited=1;return NULL; }
  a=malloc(bytes);if(!a) { p->failed=1;return NULL; }
  a->value.size=bytes;a->value.owner=p;p->bytes+=bytes;return a+1;
}
static void deallocate(cmsContext context,void *memory) {
  icc_allocation *a;(void)context;if(!memory) return;a=(icc_allocation *)memory-1;a->value.owner->bytes-=a->value.size;free(a);
}
static void *resize(cmsContext context,void *memory,cmsUInt32Number size) {
  icc_allocation *a,*next;exr_icc *p;size_t bytes=(size_t)size+sizeof(*a),old;
  if(!memory) return allocate(context,size);
  a=(icc_allocation *)memory-1;p=a->value.owner;old=a->value.size;
  if(exr_control_cancel(&p->control,NULL)!=EXR_OK) { p->cancelled=1;return NULL; }
  if(bytes>ICC_BUDGET-(p->bytes-old)) { p->limited=1;return NULL; }
  next=realloc(a,bytes);if(!next) { p->failed=1;return NULL; }
  next->value.size=bytes;p->bytes=p->bytes-old+bytes;return next+1;
}
static void report(cmsContext context,cmsUInt32Number code,const char *message) {
  exr_icc *p=cmsGetContextUserData(context);(void)code;(void)message;if(p) p->invalid=1;
}
void exr_icc_free(exr_icc *p) {
  unsigned i;
  if(!p) return;
  for(i=0;i<4;i++) if(p->intents[i]) cmsDeleteTransform(p->intents[i]);
  if(p->reverse) cmsDeleteTransform(p->reverse);
  if(p->context) cmsDeleteContext(p->context);
  free(p);
}
static exr_status open_profile(const void *data,size_t size,unsigned channels,const exr_control *control,unsigned reverse,exr_icc **out,exr_error *e) {
  cmsPluginMemHandler memory={{cmsPluginMagicNumber,LCMS_VERSION,cmsPluginMemHandlerSig,NULL},allocate,deallocate,resize,NULL,NULL,NULL};
  exr_icc *p,*previous;cmsHPROFILE input=NULL,output=NULL;cmsUInt32Number format=0;exr_status status=EXR_OK;
  *out=NULL;if(!size) return EXR_OK;
  if(size>4*1024*1024) return exr_fail(e,EXR_LIMIT,"ICC profile exceeds 4 MiB");
  if(exr_control_cancel(control,e)!=EXR_OK) return EXR_CANCELLED;
  p=calloc(1,sizeof(*p));if(!p) return exr_fail(e,EXR_MEMORY,"ICC context allocation failed");
  if(control) p->control=*control;
  previous=creating;creating=p;p->context=cmsCreateContext(&memory,p);creating=previous;
  if(!p->context) goto done;
  cmsSetLogErrorHandlerTHR(p->context,report);
  input=cmsOpenProfileFromMemTHR(p->context,data,(cmsUInt32Number)size);if(!input) goto done;
  p->space=cmsGetColorSpace(input);p->channels=channels;
  if(cmsChannelsOfColorSpace(p->space)!=(cmsInt32Number)channels) goto done;
  if(p->space==cmsSigRgbData) format=TYPE_RGB_DBL;
  else if(p->space==cmsSigGrayData) format=TYPE_GRAY_DBL;
  else if(p->space==cmsSigCmykData) format=TYPE_CMYK_DBL;
  else if(p->space==cmsSigLabData) format=TYPE_Lab_DBL;
  else goto done;
  if(cmsGetDeviceClass(input)!=cmsSigInputClass && cmsGetDeviceClass(input)!=cmsSigDisplayClass && cmsGetDeviceClass(input)!=cmsSigOutputClass && cmsGetDeviceClass(input)!=cmsSigColorSpaceClass) goto done;
  { static const cmsTagSignature tags[]={cmsSigAToB0Tag,cmsSigAToB1Tag,cmsSigAToB2Tag,cmsSigDToB0Tag,cmsSigDToB1Tag,cmsSigDToB2Tag,cmsSigDToB3Tag};
    size_t i;unsigned stages=0;
    if(cmsGetTagCount(input)>512) { status=exr_fail(e,EXR_LIMIT,"ICC profile exceeds 512 tags");goto done; }
    for(i=0;i<sizeof(tags)/sizeof(*tags);i++) if(cmsIsTag(input,tags[i])) {
      const cmsPipeline *pipeline=cmsReadTag(input,tags[i]);unsigned count=pipeline ? cmsPipelineStageCount(pipeline) : 0;
      if(count>64) { status=exr_fail(e,EXR_LIMIT,"ICC pipeline exceeds 64 stages");goto done; }
      if(count>stages) stages=count;
    }
    p->cost=32+8*stages;
  }
  output=cmsCreate_sRGBProfileTHR(p->context);if(!output) goto done;
  p->invalid=0;
  /* ISO 32000-1 8.6.5.8: the rendering intent selects an ICC intent. Keep one
     transform per intent so /RI does not silently fall back to relative. */
  { static const cmsUInt32Number table[4]={INTENT_PERCEPTUAL,INTENT_RELATIVE_COLORIMETRIC,INTENT_SATURATION,INTENT_ABSOLUTE_COLORIMETRIC};
    unsigned i;
    for(i=0;i<4;i++)
      /* MuPDF compensates the black point for relative colorimetric; matching it
         keeps CMYK output within a few levels of the reference. */
      p->intents[i]=cmsCreateTransformTHR(p->context,input,format,output,TYPE_RGB_DBL,table[i],
        cmsFLAGS_NOOPTIMIZE|cmsFLAGS_NOCACHE|(table[i]==INTENT_RELATIVE_COLORIMETRIC ? cmsFLAGS_BLACKPOINTCOMPENSATION : 0));
    p->transform=p->intents[1];
    if(reverse) p->reverse=cmsCreateTransformTHR(p->context,output,TYPE_RGB_DBL,input,TYPE_CMYK_DBL,
      INTENT_RELATIVE_COLORIMETRIC,cmsFLAGS_NOOPTIMIZE|cmsFLAGS_NOCACHE|cmsFLAGS_BLACKPOINTCOMPENSATION);
  }
done:
  if(input) cmsCloseProfile(input);
  if(output) cmsCloseProfile(output);
  if(p->cancelled) status=exr_fail(e,EXR_CANCELLED,"ICC processing cancelled");
  else if(p->limited) status=exr_fail(e,EXR_LIMIT,"ICC profile processing exceeds 16 MiB");
  else if(p->failed || !p->context) status=exr_fail(e,EXR_MEMORY,"ICC processing allocation failed");
  else if(status==EXR_OK) status=exr_control_cancel(control,e);
  if(status==EXR_OK && p->transform && (!reverse || p->reverse) && !p->invalid) { *out=p;return EXR_OK; }
  exr_icc_free(p);return status;
}
exr_status exr_icc_open(const void *data,size_t size,unsigned channels,const exr_control *control,exr_icc **out,exr_error *e) {
  return open_profile(data,size,channels,control,0,out,e);
}
exr_status exr_icc_default_cmyk(const exr_control *control,exr_icc **out,exr_error *e) {
  unsigned char *raw; mz_ulong size=961644;exr_status status;*out=NULL;
  if(exr_control_cancel(control,e)!=EXR_OK) return EXR_CANCELLED;
  raw=malloc((size_t)size);if(!raw) return exr_fail(e,EXR_MEMORY,"Default CMYK profile allocation failed");
  if(mz_uncompress(raw,&size,default_cmyk_data,sizeof(default_cmyk_data))!=MZ_OK || size!=961644) {
    free(raw);return exr_fail(e,EXR_FORMAT,"Invalid bundled CMYK profile");
  }
  status=open_profile(raw,(size_t)size,4,control,1,out,e);free(raw);
  if(status==EXR_OK && !*out) return exr_fail(e,EXR_FORMAT,"Bundled CMYK profile could not be opened");
  /* Raster loops already poll their active control, without retaining a callback
     to a completed PDF operation in the cached transform. */
  if(*out) memset(&(*out)->control,0,sizeof((*out)->control));
  return status;
}
void exr_device_cmyk_rgb(exr_icc *p,const double values[4],double rgb[3],unsigned intent) {
  unsigned k;
  if(!p) { for(k=0;k<3;k++) rgb[k]=1-fmin(1,values[k]+values[3]);return; }
  if(p->deferred.code!=EXR_OK) { memset(rgb,0,3*sizeof(*rgb));return; }
  (void)exr_icc_rgb_intent(p,values,rgb,intent,&p->deferred);
}
void exr_device_cmyk_from_rgb(exr_icc *p,const double rgb[3],double out[4]) {
  unsigned k;
  if(!p) {
    out[3]=fmax(0,fmin(1,1-fmax(rgb[0],fmax(rgb[1],rgb[2]))));
    for(k=0;k<3;k++) out[k]=fmax(0,fmin(1,1-rgb[k]-out[3]));
    return;
  }
  p->invalid=0;cmsDoTransform(p->reverse,rgb,out,1);
  if(p->invalid) (void)exr_fail(&p->deferred,EXR_FORMAT,"Default CMYK inverse conversion failed");
  for(k=0;k<4;k++) { if(!isfinite(out[k])) { out[k]=0;(void)exr_fail(&p->deferred,EXR_FORMAT,"Nonfinite CMYK conversion result"); }out[k]=fmax(0,fmin(1,out[k]/100)); }
}
exr_status exr_icc_deferred_status(const exr_icc *p,exr_error *e) {
  if(p && p->deferred.code!=EXR_OK) { if(e) *e=p->deferred;return p->deferred.code; }return EXR_OK;
}
exr_status exr_icc_rgb_intent(exr_icc *p,const double *values,double rgb[3],unsigned intent,exr_error *e) {
  double input[4];unsigned i;
  if(!p) return exr_fail(e,EXR_ARGUMENT,"Missing ICC profile");
  if(intent>3) return exr_fail(e,EXR_ARGUMENT,"Invalid rendering intent");
  if(!p->intents[intent]) return exr_fail(e,EXR_FORMAT,"ICC rendering intent is unavailable");
  if(exr_control_cancel(&p->control,e)!=EXR_OK) return EXR_CANCELLED;
  for(i=0;i<p->channels;i++) input[i]=values[i];
  if(p->space==cmsSigCmykData) for(i=0;i<4;i++) input[i]=fmax(0,fmin(1,input[i]))*100;
  else if(p->space==cmsSigLabData) {
    input[0]=fmax(0,fmin(100,input[0]));for(i=1;i<3;i++) input[i]=fmax(-128,fmin(127,input[i]));
  } else for(i=0;i<p->channels;i++) input[i]=fmax(0,fmin(1,input[i]));
  p->invalid=0;cmsDoTransform(p->intents[intent],input,rgb,1);
  if(p->invalid) return exr_fail(e,EXR_FORMAT,"ICC color conversion failed");
  for(i=0;i<3;i++) { if(!isfinite(rgb[i])) return exr_fail(e,EXR_FORMAT,"Nonfinite ICC result");rgb[i]=fmax(0,fmin(1,rgb[i])); }
  return EXR_OK;
}
exr_status exr_icc_rgb(exr_icc *p,const double *values,double rgb[3],exr_error *e) {
  return exr_icc_rgb_intent(p,values,rgb,1,e);
}
size_t exr_icc_memory(const exr_icc *p) { return p ? sizeof(*p)+p->bytes : 0; }
size_t exr_icc_cost(const exr_icc *p) { return p ? p->cost : 0; }
#else
struct exr_icc { unsigned unused; };
exr_status exr_icc_default_cmyk(const exr_control *control,exr_icc **out,exr_error *e) { *out=NULL;return exr_control_cancel(control,e); }
void exr_device_cmyk_rgb(exr_icc *p,const double values[4],double rgb[3],unsigned intent) { unsigned k;(void)p;(void)intent;for(k=0;k<3;k++) rgb[k]=1-fmin(1,values[k]+values[3]); }
void exr_device_cmyk_from_rgb(exr_icc *p,const double rgb[3],double out[4]) {
  unsigned k;(void)p;out[3]=fmax(0,fmin(1,1-fmax(rgb[0],fmax(rgb[1],rgb[2]))));
  for(k=0;k<3;k++) out[k]=fmax(0,fmin(1,1-rgb[k]-out[3]));
}
exr_status exr_icc_deferred_status(const exr_icc *p,exr_error *e) { (void)p;(void)e;return EXR_OK; }
exr_status exr_icc_open(const void *data,size_t size,unsigned channels,const exr_control *control,exr_icc **out,exr_error *e) {
  (void)data;(void)size;(void)channels;(void)control;(void)e;*out=NULL;return EXR_OK;
}
void exr_icc_free(exr_icc *p) { (void)p; }
exr_status exr_icc_rgb(exr_icc *p,const double *values,double rgb[3],exr_error *e) { (void)p;(void)values;(void)rgb;return exr_fail(e,EXR_FORMAT,"ICC conversion is disabled"); }
exr_status exr_icc_rgb_intent(exr_icc *p,const double *values,double rgb[3],unsigned intent,exr_error *e) { (void)p;(void)values;(void)rgb;(void)intent;return exr_fail(e,EXR_FORMAT,"ICC conversion is disabled"); }
size_t exr_icc_memory(const exr_icc *p) { (void)p;return 0; }
size_t exr_icc_cost(const exr_icc *p) { (void)p;return 0; }
#endif
