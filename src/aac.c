/* SPDX-License-Identifier: MIT */
#include "internal.h"
#if defined(EXR_ENABLE_AAC) && EXR_ENABLE_AAC
#include <neaacdec.h>
#define AAC_WORK_SAMPLES UINT64_C(16777216)
#define AAC_WORK_BYTES UINT64_C(268435456)
typedef struct { unsigned size,header,rate,channels,profile; } aac_header;
struct exr_aac {
  exr_source source;
  exr_aac_info info;
  NeAACDecHandle decoder;
  uint64_t begin,end,offset,position,cache_first;
  float *cache;
  size_t cache_frames,capacity;
  aac_header initial;
  int busy,dirty;
};
static exr_status aac_exact(const exr_source *s,uint64_t at,void *out,size_t n,const exr_control *control,exr_error *e) {
  size_t done=0;
  if(at>s->size || n>s->size-at) return exr_fail(e,EXR_FORMAT,"Truncated ADTS AAC source");
  while(done<n) {
    size_t got;
    if(exr_control_cancel(control,e)!=EXR_OK) return EXR_CANCELLED;
    got=s->read_at(s->context,at+done,(unsigned char *)out+done,n-done);
    if(!got || got>n-done) return exr_fail(e,EXR_IO,"Invalid or short AAC source read");
    done+=got;
  }
  return EXR_OK;
}
static int aac_parse(const unsigned char *p,aac_header *h) {
  static const unsigned rates[13]={96000,88200,64000,48000,44100,32000,24000,22050,16000,12000,11025,8000,7350};
  unsigned index=(p[2]>>2)&15,channels=((p[2]&1)<<2)|(p[3]>>6);
  if(p[0]!=255 || (p[1]&0xf6)!=0xf0 || index>=13 || !channels || (p[6]&3)) return 0;
  h->header=(p[1]&1) ? 7u : 9u; h->size=((p[3]&3)<<11)|((unsigned)p[4]<<3)|(p[5]>>5);
  h->rate=rates[index]; h->channels=channels==7 ? 8 : channels; h->profile=(p[2]>>6)+1;
  return h->size>h->header;
}
static exr_status aac_range(const exr_source *s,uint64_t *begin,uint64_t *end,const exr_control *control,exr_error *e) {
  unsigned char h[10]; unsigned count=0; exr_status status;
  *begin=0; *end=s->size;
  while(*end-*begin>=10) {
    uint64_t size=0; unsigned i,mask,footer;
    status=aac_exact(s,*begin,h,10,control,e); if(status!=EXR_OK) return status;
    if(memcmp(h,"ID3",3)) break;
    if(++count>64) return exr_fail(e,EXR_LIMIT,"AAC ID3 count exceeds 64");
    if(h[3]<2 || h[3]>4 || h[4]==255) return exr_fail(e,EXR_FORMAT,"Invalid AAC ID3 version");
    mask=h[3]==2 ? 63u : h[3]==3 ? 31u : 15u;
    if(h[5]&mask) return exr_fail(e,EXR_FORMAT,"Reserved AAC ID3 flags");
    for(i=6;i<10;i++) { if(h[i]&128) return exr_fail(e,EXR_FORMAT,"Invalid AAC ID3 synchsafe size"); size=(size<<7)|h[i]; }
    footer=h[3]==4 && (h[5]&16); size+=10+(footer ? 10u : 0u);
    if(size>*end-*begin) return exr_fail(e,EXR_FORMAT,"AAC ID3 exceeds source");
    if(*begin+size>UINT64_C(67108864)) return exr_fail(e,EXR_LIMIT,"AAC leading metadata exceeds 64 MiB");
    if(footer) { unsigned char f[10]; status=aac_exact(s,*begin+size-10,f,10,control,e); if(status!=EXR_OK) return status; if(memcmp(f,"3DI",3) || memcmp(f+3,h+3,7)) return exr_fail(e,EXR_FORMAT,"Invalid AAC ID3 footer"); }
    *begin+=size;
  }
  if(*end-*begin>=128) {
    status=aac_exact(s,*end-128,h,3,control,e); if(status!=EXR_OK) return status;
    if(!memcmp(h,"TAG",3)) *end-=128;
  }
  return EXR_OK;
}
static exr_status aac_first(const exr_source *s,uint64_t *begin,uint64_t end,aac_header *h,const exr_control *control,exr_error *e) {
  unsigned char buffer[4096+8198]; uint64_t initial=*begin;
  while(*begin<end && *begin-initial<65536) {
    size_t n=end-*begin<sizeof(buffer) ? (size_t)(end-*begin) : sizeof(buffer),i,limit=n<4096 ? n : 4096;
    size_t remaining=(size_t)(65536-(*begin-initial)); exr_status status;
    if(limit>remaining+6) limit=remaining+6;
    status=aac_exact(s,*begin,buffer,n,control,e); if(status!=EXR_OK) return status;
    for(i=0;i+7<=limit;i++) {
      aac_header next; size_t after;
      if(!aac_parse(buffer+i,h) || h->size>end-(*begin+i)) continue;
      after=i+h->size;
      if(*begin+after==end || (after+7<=n && aac_parse(buffer+after,&next) && next.rate==h->rate && next.channels==h->channels && next.profile==h->profile)) { *begin+=i; return EXR_OK; }
    }
    *begin+=limit>=7 ? limit-6 : limit;
  }
  return exr_fail(e,EXR_FORMAT,"No supported ADTS AAC stream within 64 KiB");
}
static exr_status aac_decode(exr_aac *a,NeAACDecHandle decoder,const unsigned char *bytes,unsigned size,NeAACDecFrameInfo *info,const float **pcm,exr_error *e) {
  void *samples=NeAACDecDecode(decoder,info,(unsigned char *)bytes,size); size_t i;
  if(info->error) return exr_fail(e,EXR_FORMAT,"AAC decoder: %s",NeAACDecGetErrorMessage(info->error));
  if(!samples || !info->bytesconsumed || info->bytesconsumed>size || !info->channels || info->channels>8 ||
     !info->samples || info->samples%info->channels || info->samples/info->channels>2048 || !info->samplerate || info->samplerate>192000)
    return exr_fail(e,EXR_FORMAT,"Invalid/unsupported decoded AAC frame");
  if(a->info.sample_rate && (info->samplerate!=a->info.sample_rate || info->channels!=a->info.channels)) return exr_fail(e,EXR_FORMAT,"AAC output format changes within stream");
  *pcm=samples;
  for(i=0;i<info->samples;i++) if(!isfinite((*pcm)[i])) return exr_fail(e,EXR_FORMAT,"AAC decoder produced nonfinite audio");
  return EXR_OK;
}
static exr_status aac_restart(exr_aac *a,const exr_source *source,const exr_control *control,exr_error *e) {
  unsigned char bytes[8191]; NeAACDecHandle decoder=NULL; NeAACDecConfigurationPtr config; NeAACDecFrameInfo frame={0};
  unsigned long rate=0; unsigned char channels=0; const float *pcm; exr_status status; long consumed;
  status=aac_exact(source,a->begin,bytes,a->initial.size,control,e); if(status!=EXR_OK) return status;
  decoder=NeAACDecOpen(); if(!decoder) return exr_fail(e,EXR_MEMORY,"AAC decoder allocation failed");
  config=NeAACDecGetCurrentConfiguration(decoder);
  if(!config) { status=exr_fail(e,EXR_FORMAT,"AAC decoder configuration unavailable"); goto fail; }
  config->outputFormat=FAAD_FMT_FLOAT; config->downMatrix=0; config->dontUpSampleImplicitSBR=1;
  if(!NeAACDecSetConfiguration(decoder,config)) { status=exr_fail(e,EXR_FORMAT,"AAC float output configuration rejected"); goto fail; }
  consumed=NeAACDecInit(decoder,bytes,a->initial.size,&rate,&channels);
  if(consumed!=0) { status=exr_fail(e,EXR_FORMAT,"AAC decoder could not initialize ADTS"); goto fail; }
  /* ADTS has no encoder trim metadata. Keep its complete PCM timeline; FAAD2
     otherwise hides the first normal AAC frame as an implicit MP4 priming trim. */
  NeAACDecPostSeekReset(decoder,1);
  status=aac_decode(a,decoder,bytes,a->initial.size,&frame,&pcm,e); if(status!=EXR_OK) goto fail;
  if(!exr_grow((void **)&a->cache,&a->capacity,frame.samples,sizeof(*a->cache))) { status=exr_fail(e,EXR_MEMORY,"AAC frame cache allocation failed"); goto fail; }
  status=exr_control_cancel(control,e); if(status!=EXR_OK) goto fail;
  memcpy(a->cache,pcm,frame.samples*sizeof(*pcm));
  if(a->decoder) NeAACDecClose(a->decoder);
  a->decoder=decoder; a->info.sample_rate=(uint32_t)frame.samplerate; a->info.channels=frame.channels;
  a->cache_first=0; a->cache_frames=frame.samples/frame.channels; a->position=a->cache_frames; a->offset=a->begin+a->initial.size; a->dirty=0;
  if(a->offset==a->end) a->info.frames=a->position;
  return EXR_OK;
fail:
  NeAACDecClose(decoder); return status;
}
int exr_aac_available(void) { return 1; }
void exr_aac_free(exr_aac *a) { if(a) { if(a->decoder) NeAACDecClose(a->decoder); if(a->source.release) a->source.release(a->source.context); free(a->cache); free(a); } }
const exr_aac_info *exr_aac_format(const exr_aac *a) { return a ? &a->info : NULL; }
exr_status exr_aac_open_source(const exr_source *source,exr_aac **out,exr_error *e) {
  exr_aac *a; exr_status status;
  if(out) *out=NULL;
  if(!source || !out || !source->read_at || source->size<7) return exr_fail(e,EXR_ARGUMENT,"Invalid ADTS AAC source");
  a=calloc(1,sizeof(*a)); if(!a) return exr_fail(e,EXR_MEMORY,"AAC reader allocation failed"); a->info.frames=UINT64_MAX;
  status=aac_range(source,&a->begin,&a->end,&source->control,e); if(status!=EXR_OK) goto fail;
  status=aac_first(source,&a->begin,a->end,&a->initial,&source->control,e); if(status!=EXR_OK) goto fail;
  status=aac_restart(a,source,&source->control,e); if(status!=EXR_OK) goto fail;
  status=exr_control_poll(&source->control,EXR_STAGE_READ,a->offset,source->size,e); if(status!=EXR_OK) goto fail;
  a->source=*source; memset(&a->source.control,0,sizeof(a->source.control)); *out=a; return exr_fail(e,EXR_OK,"");
fail:
  if(a->decoder) NeAACDecClose(a->decoder);
  free(a->cache); free(a); return status;
}
exr_status exr_aac_open(const char *path,const exr_control *control,exr_aac **out,exr_error *e) {
  exr_source source; exr_status status;
  if(out) *out=NULL;
  if(!path || !out) return exr_fail(e,EXR_ARGUMENT,"Invalid AAC file input");
  status=exr_file_source_limit(path,INT64_MAX,&source,e); if(status!=EXR_OK) return status;
  if(control) source.control=*control;
  status=exr_aac_open_source(&source,out,e); if(status!=EXR_OK) source.release(source.context); return status;
}
exr_status exr_aac_read(exr_aac *a,uint64_t first,size_t requested,float *out,size_t *read,const exr_control *control,exr_error *e) {
  size_t done=0; uint64_t work=0,start; exr_status status;
  if(read) *read=0;
  if(!a || !read || (requested && !out) || a->busy || first>a->info.frames || first>UINT64_MAX-65536) return exr_fail(e,EXR_ARGUMENT,"Invalid or reentrant AAC read");
  if(requested>65536) return exr_fail(e,EXR_LIMIT,"AAC read exceeds 65536 sample frames");
  if(requested) memset(out,0,requested*a->info.channels*sizeof(*out));
  a->busy=1; status=exr_control_cancel(control,e); if(status!=EXR_OK) goto finish;
  if(!requested || first==a->info.frames) goto complete;
  if(a->dirty || first<a->cache_first) { status=aac_restart(a,&a->source,control,e); if(status!=EXR_OK) goto finish; }
  start=a->offset;
  while(done<requested) {
    uint64_t target=first+done;
    if(target>=a->cache_first && target<a->position) {
      size_t begin=(size_t)(target-a->cache_first),n=(size_t)(a->position-target); if(n>requested-done) n=requested-done;
      memcpy(out+done*a->info.channels,a->cache+begin*a->info.channels,n*a->info.channels*sizeof(*out)); done+=n;
      if(done==requested) break;
    }
    if(a->offset==a->end) { a->info.frames=a->position; break; }
    if(work>=AAC_WORK_SAMPLES || a->offset-start>=AAC_WORK_BYTES) { status=exr_fail(e,EXR_LIMIT,"AAC accurate replay budget exhausted; retry retains decoder progress"); goto finish; }
    status=exr_control_poll(control,EXR_STAGE_READ,done,requested,e); if(status!=EXR_OK) goto finish;
    {
      unsigned char bytes[8191]; aac_header h; NeAACDecFrameInfo frame={0}; const float *pcm; size_t count;
      if(a->end-a->offset<7) { status=exr_fail(e,EXR_FORMAT,"Trailing or truncated ADTS AAC header"); goto finish; }
      status=aac_exact(&a->source,a->offset,bytes,7,control,e); if(status!=EXR_OK) goto finish;
      if(!aac_parse(bytes,&h) || h.rate!=a->initial.rate || h.channels!=a->initial.channels || h.profile!=a->initial.profile || h.size>a->end-a->offset) { status=exr_fail(e,EXR_FORMAT,"Invalid/truncated or changing ADTS AAC format"); goto finish; }
      status=aac_exact(&a->source,a->offset+7,bytes+7,h.size-7,control,e); if(status!=EXR_OK) goto finish;
      status=aac_decode(a,a->decoder,bytes,h.size,&frame,&pcm,e); if(status!=EXR_OK) { a->dirty=1; goto finish; }
      count=frame.samples/a->info.channels;
      if(a->position>UINT64_MAX-count) { a->dirty=1; status=exr_fail(e,EXR_LIMIT,"AAC PCM frame count exceeds 64 bits"); goto finish; }
      if(!exr_grow((void **)&a->cache,&a->capacity,frame.samples,sizeof(*a->cache))) { a->dirty=1; status=exr_fail(e,EXR_MEMORY,"AAC frame cache allocation failed"); goto finish; }
      memcpy(a->cache,pcm,frame.samples*sizeof(*pcm)); a->cache_first=a->position; a->cache_frames=count; a->position+=count; a->offset+=h.size; work+=count;
      if(a->offset==a->end) a->info.frames=a->position;
    }
  }
complete:
  status=exr_control_poll(control,EXR_STAGE_READ,done,done,e);
finish:
  a->busy=0;
  if(status!=EXR_OK) { if(requested) memset(out,0,requested*a->info.channels*sizeof(*out)); return status; }
  *read=done; return exr_fail(e,EXR_OK,"");
}
#else
struct exr_aac { int unused; };
int exr_aac_available(void) { return 0; }
void exr_aac_free(exr_aac *a) { free(a); }
const exr_aac_info *exr_aac_format(const exr_aac *a) { (void)a; return NULL; }
exr_status exr_aac_open_source(const exr_source *source,exr_aac **out,exr_error *e) {
  if(out) *out=NULL;
  if(!source || !out || !source->read_at) return exr_fail(e,EXR_ARGUMENT,"Invalid AAC source");
  return exr_fail(e,EXR_FORMAT,"AAC codec was disabled at build time");
}
exr_status exr_aac_open(const char *path,const exr_control *control,exr_aac **out,exr_error *e) {
  (void)control; if(out) *out=NULL;
  return exr_fail(e,path && out ? EXR_FORMAT : EXR_ARGUMENT,"AAC codec was disabled or input is invalid");
}
exr_status exr_aac_read(exr_aac *a,uint64_t first,size_t frames,float *output,size_t *read,const exr_control *control,exr_error *e) {
  (void)a; (void)first; (void)frames; (void)output; (void)control; if(read) *read=0;
  return exr_fail(e,EXR_ARGUMENT,"No AAC decoder handle");
}
#endif
