/* SPDX-License-Identifier: GPL-3.0-only */
#include "internal.h"
struct exr_wave { exr_source source; exr_wave_info info; uint64_t data; uint32_t alignment; int busy; };
static uint32_t le16(const unsigned char *p) { return (uint32_t)p[0]|(uint32_t)p[1]<<8; }
static uint32_t le32(const unsigned char *p) { return le16(p)|le16(p+2)<<16; }
static exr_status read_exact(const exr_source *s,uint64_t offset,void *output,size_t size,const exr_control *control,exr_error *e) {
  size_t done=0;
  if(offset>s->size || size>s->size-offset) return exr_fail(e,EXR_FORMAT,"WAVE chunk exceeds source");
  while(done<size) {
    size_t got;
    if(exr_control_cancel(control,e)!=EXR_OK) return EXR_CANCELLED;
    got=s->read_at(s->context,offset+done,(unsigned char *)output+done,size-done);
    if(!got || got>size-done) return exr_fail(e,EXR_IO,"WAVE source returned an invalid/short read");
    done+=got;
  }
  return EXR_OK;
}
void exr_wave_free(exr_wave *w) { if(w) { if(w->source.release) w->source.release(w->source.context); free(w); } }
const exr_wave_info *exr_wave_format(const exr_wave *w) { return w ? &w->info : NULL; }
static exr_status format(exr_wave *w,const unsigned char *b,size_t size,exr_error *e) {
  uint32_t tag=le16(b),channels=le16(b+2),rate=le32(b+4),bits=le16(b+14),valid=bits,mask=0,align=le16(b+12);
  if(tag==65534) {
    static const unsigned char guid_tail[12]={0,0,16,0,128,0,0,170,0,56,155,113};
    uint32_t flags,k=0;
    if(size<40 || le16(b+16)<22 || (uint32_t)18+le16(b+16)>size || memcmp(b+28,guid_tail,12)) return exr_fail(e,EXR_FORMAT,"Unsupported/invalid extensible WAVE format");
    tag=le32(b+24); valid=le16(b+18); mask=le32(b+20);
    for(flags=mask;flags;flags>>=1) k+=flags&1;
    if(mask && k!=channels) return exr_fail(e,EXR_FORMAT,"WAVE channel mask/count disagree");
  }
  if((tag!=1 && tag!=3) || !channels || channels>32 || !rate || rate>768000 || !valid || valid>bits ||
     (tag==1 ? (bits!=8 && bits!=16 && bits!=24 && bits!=32) : ((bits!=32 && bits!=64) || valid!=bits)) ||
     align!=channels*(bits/8) || (uint64_t)rate*align!=le32(b+8)) return exr_fail(e,EXR_FORMAT,"Unsupported/invalid WAVE PCM format");
  w->info=(exr_wave_info){rate,channels,bits,valid,mask,0,tag==3}; w->alignment=align; return EXR_OK;
}
exr_status exr_wave_open_source(const exr_source *source,exr_wave **out,exr_error *e) {
  exr_wave *w; unsigned char header[12],chunk[8],fmt[40]; uint64_t at=12,end,data_size=0; size_t chunks=0; int have_format=0,have_data=0; exr_status status;
  if(out) *out=NULL;
  if(!source || !out || !source->read_at || source->size<12) return exr_fail(e,EXR_ARGUMENT,"Invalid WAVE source");
  status=read_exact(source,0,header,12,&source->control,e); if(status!=EXR_OK) return status;
  if(memcmp(header,"RIFF",4) || memcmp(header+8,"WAVE",4)) return exr_fail(e,EXR_FORMAT,"Source is not little-endian RIFF/WAVE");
  end=(uint64_t)le32(header+4)+8;
  if(end<12 || end>source->size) return exr_fail(e,EXR_FORMAT,"Invalid WAVE RIFF length");
  w=calloc(1,sizeof(*w)); if(!w) return exr_fail(e,EXR_MEMORY,"WAVE reader allocation failed");
  while(at<end) {
    uint32_t n; uint64_t next;
    if(++chunks>1000000) { status=exr_fail(e,EXR_LIMIT,"WAVE chunk count exceeds budget"); goto finish; }
    if(end-at<8) { status=exr_fail(e,EXR_FORMAT,"Truncated WAVE chunk header"); goto finish; }
    status=read_exact(source,at,chunk,8,&source->control,e); if(status!=EXR_OK) goto finish;
    n=le32(chunk+4); at+=8;
    if(n>end-at) { status=exr_fail(e,EXR_FORMAT,"WAVE chunk exceeds RIFF length"); goto finish; }
    next=at+n+(n&1u); if(next>end) { status=exr_fail(e,EXR_FORMAT,"Missing WAVE chunk padding"); goto finish; }
    if(!memcmp(chunk,"fmt ",4)) {
      if(have_format || n<16) { status=exr_fail(e,EXR_FORMAT,"Invalid/duplicate WAVE format chunk"); goto finish; }
      status=read_exact(source,at,fmt,n<sizeof(fmt) ? n : sizeof(fmt),&source->control,e); if(status!=EXR_OK) goto finish;
      status=format(w,fmt,n,e); if(status!=EXR_OK) goto finish; have_format=1;
    } else if(!memcmp(chunk,"data",4)) {
      if(have_data) { status=exr_fail(e,EXR_FORMAT,"Multiple WAVE data chunks are not supported"); goto finish; }
      have_data=1; w->data=at; data_size=n;
    }
    at=next;
  }
  if(!have_format || !have_data || data_size%w->alignment) { status=exr_fail(e,EXR_FORMAT,"Missing/misaligned WAVE PCM payload"); goto finish; }
  status=exr_control_cancel(&source->control,e); if(status!=EXR_OK) goto finish;
  w->info.frames=data_size/w->alignment; w->source=*source; memset(&w->source.control,0,sizeof(w->source.control)); *out=w; return exr_fail(e,EXR_OK,"");
finish:
  free(w); return status;
}
exr_status exr_wave_open(const char *path,const exr_control *control,exr_wave **out,exr_error *e) {
  exr_source source; exr_status status;
  if(out) *out=NULL;
  if(!path || !out) return exr_fail(e,EXR_ARGUMENT,"Invalid WAVE file input");
  status=exr_file_source_limit(path,(uint64_t)UINT32_MAX+8,&source,e); if(status!=EXR_OK) return status;
  if(control) source.control=*control;
  status=exr_wave_open_source(&source,out,e); if(status!=EXR_OK) source.release(source.context); return status;
}
static exr_status sample(const unsigned char *p,const exr_wave_info *info,float *out,exr_error *e) {
  unsigned bytes=info->bits_per_sample/8,k; uint64_t bits=0; double value;
  for(k=0;k<bytes;k++) bits|=(uint64_t)p[k]<<(8*k);
  if(info->floating) {
    if(bytes==4) { uint32_t raw=(uint32_t)bits; float f; memcpy(&f,&raw,4); value=f; } else memcpy(&value,&bits,8);
    if(!isfinite(value)) return exr_fail(e,EXR_FORMAT,"Non-finite WAVE floating sample");
    if(value>1) value=1; else if(value< -1) value=-1;
  } else if(bytes==1) value=((double)(bits>>(8-info->valid_bits))-ldexp(1,info->valid_bits-1))/ldexp(1,info->valid_bits-1);
  else {
    int64_t integer=(int64_t)bits;
    if(bits&((uint64_t)1<<(info->bits_per_sample-1))) integer-=(int64_t)((uint64_t)1<<info->bits_per_sample);
    value=floor(ldexp((double)integer,-(int)(info->bits_per_sample-info->valid_bits)))/ldexp(1,info->valid_bits-1);
  }
  *out=(float)value; return EXR_OK;
}
exr_status exr_wave_read(exr_wave *w,uint64_t first,size_t requested,float *out,size_t *read,const exr_control *control,exr_error *e) {
  unsigned char buffer[4096]; size_t count,done=0; exr_status status=EXR_OK;
  if(read) *read=0;
  if(!w || !read || (requested && !out) || first>w->info.frames || w->busy) return exr_fail(e,EXR_ARGUMENT,"Invalid or reentrant WAVE read");
  if(requested>65536) return exr_fail(e,EXR_LIMIT,"WAVE read exceeds 65536 frames");
  if(requested) memset(out,0,requested*w->info.channels*sizeof(*out));
  count=w->info.frames-first<requested ? (size_t)(w->info.frames-first) : requested; w->busy=1;
  status=exr_control_cancel(control,e);
  while(status==EXR_OK && done<count) {
    size_t n=sizeof(buffer)/w->alignment,i; if(n>count-done) n=count-done;
    status=exr_control_poll(control,EXR_STAGE_READ,done,count,e); if(status!=EXR_OK) break;
    status=read_exact(&w->source,w->data+(first+done)*w->alignment,buffer,n*w->alignment,control,e); if(status!=EXR_OK) break;
    for(i=0;i<n*w->info.channels;i++) {
      status=sample(buffer+i*(w->info.bits_per_sample/8),&w->info,out+done*w->info.channels+i,e); if(status!=EXR_OK) break;
    }
    if(status==EXR_OK) done+=n;
  }
  if(status==EXR_OK) status=exr_control_poll(control,EXR_STAGE_READ,count,count,e);
  w->busy=0;
  if(status!=EXR_OK) { if(requested) memset(out,0,requested*w->info.channels*sizeof(*out)); return status; }
  *read=count; return exr_fail(e,EXR_OK,"");
}
