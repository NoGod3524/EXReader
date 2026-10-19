/* SPDX-License-Identifier: MIT */
#include "audio_internal.h"
#if defined(EXR_ENABLE_MP3) && EXR_ENABLE_MP3
#define MINIMP3_ONLY_MP3
#define MINIMP3_FLOAT_OUTPUT
/* The upstream x86 runtime SIMD probe has a writable process-global cache.
   Baseline 64-bit ISAs already guarantee SSE2/NEON; other targets use scalar
   code so independent decoder instances can run concurrently without it. */
#if defined(__x86_64__) || defined(_M_X64) || defined(__aarch64__) || defined(_M_ARM64)
#define MINIMP3_ONLY_SIMD
#else
#define MINIMP3_NO_SIMD
#endif
#define MINIMP3_IMPLEMENTATION
#include <minimp3.h>
#define MP3_POINTS 128u
#define MP3_WORK_SAMPLES UINT64_C(16777216)
#define MP3_WORK_BYTES UINT64_C(268435456)
typedef struct { uint64_t offset,frame; mp3dec_t decoder; } mp3_point;
struct exr_mp3 {
  exr_source source;
  exr_mp3_info info;
  uint64_t begin,end,encoded_frames;
  uint32_t delay,padding,block;
  mp3_point *points,cursor,frontier;
  size_t count,capacity;
  uint64_t stride;
  float pcm[MINIMP3_MAX_SAMPLES_PER_FRAME];
  int busy;
};
typedef struct { unsigned size,rate,channels,samples; } mp3_header;
static uint32_t mp3_be32(const unsigned char *p) { return (uint32_t)p[0]<<24|(uint32_t)p[1]<<16|(uint32_t)p[2]<<8|p[3]; }
static uint32_t mp3_le32(const unsigned char *p) { return (uint32_t)p[3]<<24|(uint32_t)p[2]<<16|(uint32_t)p[1]<<8|p[0]; }
static exr_status mp3_exact(const exr_source *s,uint64_t at,void *out,size_t n,const exr_control *control,exr_error *e) {
  size_t done=0;
  if(at>s->size || n>s->size-at) return exr_fail(e,EXR_FORMAT,"Truncated MP3 source");
  while(done<n) {
    size_t got;
    if(exr_control_cancel(control,e)!=EXR_OK) return EXR_CANCELLED;
    got=s->read_at(s->context,at+done,(unsigned char *)out+done,n-done);
    if(!got || got>n-done) return exr_fail(e,EXR_IO,"Invalid or short MP3 source read");
    done+=got;
  }
  return EXR_OK;
}
static int mp3_parse(const unsigned char *p,mp3_header *h) {
  static const unsigned rates[3]={44100,48000,32000};
  static const unsigned bitrates[2][16]={{0,8,16,24,32,40,48,56,64,80,96,112,128,144,160,0},{0,32,40,48,56,64,80,96,112,128,160,192,224,256,320,0}};
  unsigned version=(p[1]>>3)&3,rate=(p[2]>>2)&3,bitrate=p[2]>>4;
  if(p[0]!=255 || (p[1]&0xe0)!=0xe0 || version==1 || (p[1]&6)!=2 || rate==3 || !bitrate || bitrate==15 || (p[3]&3)==2) return 0;
  h->rate=rates[rate]>>(version==3 ? 0 : version==2 ? 1 : 2);
  h->channels=(p[3]>>6)==3 ? 1 : 2; h->samples=version==3 ? 1152 : 576;
  h->size=(version==3 ? 144000u : 72000u)*bitrates[version==3][bitrate]/h->rate+((p[2]>>1)&1);
  return h->size>=4 && h->size<=1441;
}
static exr_status mp3_tags(const exr_source *s,uint64_t *begin,uint64_t *end,exr_error *e) {
  unsigned char b[32]; unsigned tags=0; exr_status status;
  *begin=0; *end=s->size;
  while(*end-*begin>=10) {
    uint64_t n; unsigned i,footer,mask;
    status=mp3_exact(s,*begin,b,10,&s->control,e); if(status!=EXR_OK) return status;
    if(memcmp(b,"ID3",3)) break;
    if(++tags>64) return exr_fail(e,EXR_LIMIT,"MP3 ID3 tag count exceeds 64");
    if(b[3]<2 || b[3]>4 || b[4]==255) return exr_fail(e,EXR_FORMAT,"Unsupported/invalid ID3 version");
    mask=b[3]==2 ? 63u : b[3]==3 ? 31u : 15u;
    if(b[5]&mask) return exr_fail(e,EXR_FORMAT,"Reserved ID3 flags are set");
    n=0; for(i=6;i<10;i++) { if(b[i]&128) return exr_fail(e,EXR_FORMAT,"Invalid ID3 synchsafe size"); n=(n<<7)|b[i]; }
    footer=b[3]==4 && (b[5]&16); n+=10+(footer ? 10u : 0u);
    if(n>*end-*begin) return exr_fail(e,EXR_FORMAT,"ID3 tag exceeds MP3 source");
    if(n>UINT64_C(67108864) || *begin+n>UINT64_C(67108864)) return exr_fail(e,EXR_LIMIT,"MP3 leading metadata exceeds 64 MiB");
    if(footer) {
      unsigned char f[10]; status=mp3_exact(s,*begin+n-10,f,10,&s->control,e); if(status!=EXR_OK) return status;
      if(memcmp(f,"3DI",3) || memcmp(f+3,b+3,7)) return exr_fail(e,EXR_FORMAT,"Invalid ID3v2.4 footer");
    }
    *begin+=n;
  }
  if(*end-*begin>=128) {
    status=mp3_exact(s,*end-128,b,3,&s->control,e); if(status!=EXR_OK) return status;
    if(!memcmp(b,"TAG",3)) {
      *end-=128;
      if(*end-*begin>=227) { status=mp3_exact(s,*end-227,b,4,&s->control,e); if(status!=EXR_OK) return status; if(!memcmp(b,"TAG+",4)) *end-=227; }
    }
  }
  if(*end-*begin>=32) {
    status=mp3_exact(s,*end-32,b,32,&s->control,e); if(status!=EXR_OK) return status;
    if(!memcmp(b,"APETAGEX",8)) {
      uint32_t n=mp3_le32(b+12),flags=mp3_le32(b+20);
      if(mp3_le32(b+8)!=2000 || n<32 || n>*end-*begin || n>67108864u) return exr_fail(e,EXR_FORMAT,"Invalid/oversized APEv2 tag");
      *end-=n;
      if(flags&UINT32_C(0x80000000)) {
        if(*end-*begin<32) return exr_fail(e,EXR_FORMAT,"Missing APEv2 header");
        status=mp3_exact(s,*end-32,b,32,&s->control,e); if(status!=EXR_OK) return status;
        if(memcmp(b,"APETAGEX",8)) return exr_fail(e,EXR_FORMAT,"Missing APEv2 header");
        *end-=32;
      }
    }
  }
  return EXR_OK;
}
static exr_status mp3_first(const exr_source *s,uint64_t *begin,uint64_t end,mp3_header *header,exr_error *e) {
  unsigned char buffer[4096+1445]; uint64_t initial=*begin;
  while(*begin<end && *begin-initial<65536) {
    size_t n=end-*begin<sizeof(buffer) ? (size_t)(end-*begin) : sizeof(buffer),i,limit=n<4096 ? n : 4096;
    size_t remaining=(size_t)(65536-(*begin-initial));
    if(limit>remaining+3) limit=remaining+3;
    exr_status status=mp3_exact(s,*begin,buffer,n,&s->control,e); if(status!=EXR_OK) return status;
    for(i=0;i+4<=limit;i++) {
      mp3_header next; size_t after;
      if(!mp3_parse(buffer+i,header)) continue;
      after=i+header->size;
      if(header->size>end-(*begin+i)) continue;
      if(*begin+after==end || (after+4<=n && mp3_parse(buffer+after,&next) && next.rate==header->rate && next.channels==header->channels)) { *begin+=i; return EXR_OK; }
    }
    *begin+=limit>=4 ? limit-3 : limit;
  }
  return exr_fail(e,EXR_FORMAT,"No valid MPEG Layer III stream within 64 KiB");
}
static exr_status mp3_xing(exr_mp3 *m,const unsigned char *frame,const mp3_header *h,int *skip,exr_error *e) {
  unsigned side=h->samples==1152 ? (h->channels==1 ? 17u : 32u) : (h->channels==1 ? 9u : 17u);
  size_t at=4+side+((frame[1]&1) ? 0 : 2); uint32_t flags; uint64_t raw;
  *skip=0;
  if(at+8>h->size || (memcmp(frame+at,"Xing",4) && memcmp(frame+at,"Info",4))) return EXR_OK;
  *skip=1; flags=mp3_be32(frame+at+4); at+=8;
  if(flags&~15u) return exr_fail(e,EXR_FORMAT,"Unsupported Xing flags");
  if(flags&1) { if(at+4>h->size) goto truncated; m->encoded_frames=mp3_be32(frame+at); at+=4; if(!m->encoded_frames) return exr_fail(e,EXR_FORMAT,"Zero Xing frame count"); }
  if(flags&2) { if(at+4>h->size) goto truncated; at+=4; }
  if(flags&4) { if(at+100>h->size) goto truncated; at+=100; }
  if(flags&8) { if(at+4>h->size) goto truncated; at+=4; }
  if(at+36<=h->size && (!memcmp(frame+at,"LAME",4) || !memcmp(frame+at,"Lavc",4) || !memcmp(frame+at,"Lavf",4))) {
    unsigned delay=(unsigned)frame[at+21]*16+(frame[at+22]>>4),padding=(unsigned)(frame[at+22]&15)*256+frame[at+23];
    if(padding<529) return exr_fail(e,EXR_FORMAT,"Unsupported LAME padding shorter than decoder delay");
    m->delay=delay+529; m->padding=padding-529;
  }
  if(m->encoded_frames) {
    raw=m->encoded_frames*h->samples;
    if(raw<(uint64_t)m->delay+m->padding) return exr_fail(e,EXR_FORMAT,"LAME trimming exceeds Xing sample count");
    m->info.frames=raw-m->delay-m->padding;
  }
  return EXR_OK;
truncated:
  return exr_fail(e,EXR_FORMAT,"Truncated Xing seek/duration tag");
}
static exr_status mp3_point_save(exr_mp3 *m,const mp3_point *p,exr_error *e) {
  size_t i;
  if(p->offset<=m->points[m->count-1].offset || p->frame%m->stride) return EXR_OK;
  if(m->count==MP3_POINTS) {
    for(i=1;i<MP3_POINTS/2;i++) m->points[i]=m->points[i*2];
    m->count=MP3_POINTS/2; m->stride*=2;
    if(p->frame%m->stride) return EXR_OK;
  }
  if(!exr_grow((void **)&m->points,&m->capacity,m->count+1,sizeof(*m->points))) return exr_fail(e,EXR_MEMORY,"MP3 checkpoint allocation failed");
  m->points[m->count++]=*p; return EXR_OK;
}
int exr_mp3_available(void) { return 1; }
void exr_mp3_free(exr_mp3 *m) { if(m) { if(m->source.release) m->source.release(m->source.context); free(m->points); free(m); } }
const exr_mp3_info *exr_mp3_format(const exr_mp3 *m) { return m ? &m->info : NULL; }
exr_status exr_mp3_open_source(const exr_source *source,exr_mp3 **out,exr_error *e) {
  exr_mp3 *m; unsigned char frame[1441],next[4]; mp3_header h={0},n={0}; exr_status status; int skip;
  if(out) *out=NULL;
  if(!source || !out || !source->read_at || source->size<4) return exr_fail(e,EXR_ARGUMENT,"Invalid MP3 source");
  m=calloc(1,sizeof(*m)); if(!m) return exr_fail(e,EXR_MEMORY,"MP3 reader allocation failed");
  m->info.frames=UINT64_MAX; m->stride=32;
  status=mp3_tags(source,&m->begin,&m->end,e); if(status!=EXR_OK) goto fail;
  status=mp3_first(source,&m->begin,m->end,&h,e); if(status!=EXR_OK) goto fail;
  m->info.sample_rate=h.rate; m->info.channels=h.channels; m->block=h.samples;
  status=mp3_exact(source,m->begin,frame,h.size,&source->control,e); if(status!=EXR_OK) goto fail;
  status=mp3_xing(m,frame,&h,&skip,e); if(status!=EXR_OK) goto fail;
  if(skip) {
    m->begin+=h.size;
    if(m->end-m->begin<4) { status=exr_fail(e,EXR_FORMAT,"MP3 Xing header has no audio frames"); goto fail; }
    status=mp3_exact(source,m->begin,next,4,&source->control,e); if(status!=EXR_OK) goto fail;
    if(!mp3_parse(next,&n) || n.rate!=h.rate || n.channels!=h.channels || n.samples!=h.samples || n.size>m->end-m->begin) { status=exr_fail(e,EXR_FORMAT,"MP3 audio disagrees with Xing header"); goto fail; }
  }
  m->points=malloc(sizeof(*m->points)); m->capacity=1;
  if(!m->points) { status=exr_fail(e,EXR_MEMORY,"MP3 checkpoint allocation failed"); goto fail; }
  memset(m->points,0,sizeof(*m->points)); m->points[0].offset=m->begin; mp3dec_init(&m->points[0].decoder); m->count=1;
  m->cursor=m->frontier=m->points[0];
  status=exr_control_poll(&source->control,EXR_STAGE_READ,m->begin,source->size,e); if(status!=EXR_OK) goto fail;
  m->source=*source; memset(&m->source.control,0,sizeof(m->source.control)); *out=m; return exr_fail(e,EXR_OK,"");
fail:
  free(m->points); free(m); return status;
}
exr_status exr_mp3_open(const char *path,const exr_control *control,exr_mp3 **out,exr_error *e) {
  exr_source source; exr_status status;
  if(out) *out=NULL;
  if(!path || !out) return exr_fail(e,EXR_ARGUMENT,"Invalid MP3 file input");
  status=exr_file_source_limit(path,INT64_MAX,&source,e); if(status!=EXR_OK) return status;
  if(control) source.control=*control;
  status=exr_mp3_open_source(&source,out,e); if(status!=EXR_OK) source.release(source.context); return status;
}
exr_status exr_mp3_read(exr_mp3 *m,uint64_t first,size_t requested,float *output,size_t *read,const exr_control *control,exr_error *e) {
  mp3_point state; uint64_t target,work_offset,work_frames=0; size_t i,done=0; exr_status status;
  if(read) *read=0;
  if(!m || !read || (requested && !output) || m->busy || first>m->info.frames || first>UINT64_MAX-m->delay-65536)
    return exr_fail(e,EXR_ARGUMENT,"Invalid or reentrant MP3 read");
  if(requested>65536) return exr_fail(e,EXR_LIMIT,"MP3 read exceeds 65536 sample frames");
  if(requested) memset(output,0,requested*m->info.channels*sizeof(*output));
  m->busy=1; status=exr_control_cancel(control,e); if(status!=EXR_OK) goto finish;
  if(!requested || first==m->info.frames) goto complete;
  target=first+m->delay;
  for(i=1;i<m->count && m->points[i].frame<=target/m->block;i++) {}
  state=m->points[i-1];
  if(m->cursor.frame<=target/m->block && m->cursor.frame>state.frame) state=m->cursor;
  if(m->frontier.frame<=target/m->block && m->frontier.frame>state.frame) state=m->frontier;
  work_offset=state.offset;
  while(done<requested) {
    unsigned char bytes[1441]; mp3_header h; mp3dec_frame_info_t frame_info={0}; mp3_point before; uint64_t raw,end; int n; size_t begin,count,c;
    if(state.offset==m->end) {
      raw=state.frame*m->block;
      if(m->encoded_frames && state.frame!=m->encoded_frames) { status=exr_fail(e,EXR_FORMAT,"MP3 EOF disagrees with Xing frame count"); goto finish; }
      if(raw<(uint64_t)m->delay+m->padding) { status=exr_fail(e,EXR_FORMAT,"MP3 EOF precedes gapless trimming"); goto finish; }
      m->info.frames=raw-m->delay-m->padding; break;
    }
    if(work_frames>=MP3_WORK_SAMPLES || state.offset-work_offset>=MP3_WORK_BYTES) { status=exr_fail(e,EXR_LIMIT,"MP3 seek scan budget exhausted; retry retains verified checkpoints"); goto finish; }
    status=exr_control_poll(control,EXR_STAGE_READ,done,requested,e); if(status!=EXR_OK) goto finish;
    if(m->end-state.offset<4) { status=exr_fail(e,EXR_FORMAT,"Trailing/truncated MP3 frame header"); goto finish; }
    status=mp3_exact(&m->source,state.offset,bytes,4,control,e); if(status!=EXR_OK) goto finish;
    if(!mp3_parse(bytes,&h) || h.rate!=m->info.sample_rate || h.channels!=m->info.channels || h.samples!=m->block || h.size>m->end-state.offset) { status=exr_fail(e,EXR_FORMAT,"Invalid/truncated or changing MP3 stream format"); goto finish; }
    status=mp3_exact(&m->source,state.offset+4,bytes+4,h.size-4,control,e); if(status!=EXR_OK) goto finish;
    before=state; n=mp3dec_decode_frame(&state.decoder,bytes,(int)h.size,m->pcm,&frame_info);
    if(n!=(int)m->block || frame_info.frame_offset || frame_info.frame_bytes!=(int)h.size || frame_info.layer!=3 || frame_info.channels!=(int)m->info.channels || frame_info.hz!=(int)m->info.sample_rate) { status=exr_fail(e,EXR_FORMAT,"MP3 decoder rejected frame or missing bit reservoir"); goto finish; }
    for(c=0;c<(size_t)n*m->info.channels;c++) if(!isfinite(m->pcm[c])) { status=exr_fail(e,EXR_FORMAT,"MP3 decoder produced nonfinite audio"); goto finish; }
    if(state.frame>UINT64_MAX/m->block-1) { status=exr_fail(e,EXR_LIMIT,"MP3 sample count exceeds 64 bits"); goto finish; }
    raw=state.frame*m->block; end=raw+m->block;
    state.frame++; state.offset+=h.size; work_frames+=m->block;
    if(m->encoded_frames && (state.frame>m->encoded_frames || (state.offset==m->end && state.frame!=m->encoded_frames) || (state.frame==m->encoded_frames && state.offset!=m->end))) { status=exr_fail(e,EXR_FORMAT,"MP3 data disagrees with Xing frame count"); goto finish; }
    status=mp3_point_save(m,&before,e); if(status!=EXR_OK) goto finish;
    m->cursor=before; if(state.frame>m->frontier.frame) m->frontier=state;
    if(state.offset==m->end && !m->encoded_frames) {
      if(end<(uint64_t)m->delay+m->padding) { status=exr_fail(e,EXR_FORMAT,"MP3 EOF precedes gapless trimming"); goto finish; }
      m->info.frames=end-m->delay-m->padding;
    }
    if(m->info.frames!=UINT64_MAX && end>m->info.frames+m->delay) end=m->info.frames+m->delay;
    if(target+done<end) {
      begin=(size_t)(target+done-raw); count=(size_t)(end-(target+done)); if(count>requested-done) count=requested-done;
      memcpy(output+done*m->info.channels,m->pcm+begin*m->info.channels,count*m->info.channels*sizeof(*output)); done+=count;
    }
    if(m->info.frames!=UINT64_MAX && first+done>=m->info.frames) break;
  }
complete:
  status=exr_control_poll(control,EXR_STAGE_READ,done,done,e);
finish:
  m->busy=0;
  if(status!=EXR_OK) { if(requested) memset(output,0,requested*m->info.channels*sizeof(*output)); return status; }
  *read=done; return exr_fail(e,EXR_OK,"");
}
#else
struct exr_mp3 { int unused; };
int exr_mp3_available(void) { return 0; }
void exr_mp3_free(exr_mp3 *m) { free(m); }
const exr_mp3_info *exr_mp3_format(const exr_mp3 *m) { (void)m; return NULL; }
exr_status exr_mp3_open_source(const exr_source *source,exr_mp3 **out,exr_error *e) {
  if(out) *out=NULL;
  if(!source || !out || !source->read_at) return exr_fail(e,EXR_ARGUMENT,"Invalid MP3 source");
  return exr_fail(e,EXR_FORMAT,"MP3 codec was disabled at build time");
}
exr_status exr_mp3_open(const char *path,const exr_control *control,exr_mp3 **out,exr_error *e) {
  (void)control; if(out) *out=NULL;
  return exr_fail(e,path && out ? EXR_FORMAT : EXR_ARGUMENT,"MP3 codec was disabled or input is invalid");
}
exr_status exr_mp3_read(exr_mp3 *m,uint64_t first,size_t frames,float *output,size_t *read,const exr_control *control,exr_error *e) {
  (void)m; (void)first; (void)frames; (void)output; (void)control; if(read) *read=0;
  return exr_fail(e,EXR_ARGUMENT,"No MP3 decoder handle");
}
#endif
