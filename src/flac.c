/* SPDX-License-Identifier: MIT */
#include "audio_internal.h"

/* Native FLAC bitstream decoder. The Ogg container and MD5 verification are
   separate from decoding; frame/header CRCs are always checked here. */
#define FLAC_INDEX 4096u
#define FLAC_WORK_FRAMES UINT64_C(16777216)
#define FLAC_WORK_BYTES UINT64_C(268435456)
typedef struct { uint64_t sample,offset,number; } flac_point;
struct exr_flac {
  exr_source source;
  exr_flac_info info;
  uint64_t data;
  unsigned minimum_block,maximum_block,maximum_frame;
  flac_point index[FLAC_INDEX];
  flac_point *seek;
  size_t seek_count;
  flac_point frontier;
  uint64_t seek_last_offset;
  size_t count;
  uint64_t stride;
  int64_t *samples;
  size_t capacity;
  int busy,unknown,strategy;
};
typedef struct {
  exr_flac *flac;
  const exr_control *control;
  exr_error *error;
  exr_status status;
  uint64_t at,start,work_start;
  unsigned char bytes[4096];
  size_t position,size;
  unsigned byte,left,crc8,crc16;
} flac_bits;
typedef struct { uint64_t first,number,next; unsigned count,assignment; int variable; } flac_frame;

static uint32_t be16(const unsigned char *p) { return (uint32_t)p[0]<<8|p[1]; }
static uint32_t be24(const unsigned char *p) { return (uint32_t)p[0]<<16|be16(p+1); }
static uint64_t be64(const unsigned char *p) { unsigned i; uint64_t n=0; for(i=0;i<8;i++) n=(n<<8)|p[i]; return n; }
static exr_status exact(const exr_source *s,uint64_t at,void *out,size_t n,const exr_control *c,exr_error *e) {
  size_t done=0;
  if(at>s->size || n>s->size-at) return exr_fail(e,EXR_FORMAT,"Truncated FLAC input");
  while(done<n) {
    size_t got;
    if(exr_control_cancel(c,e)!=EXR_OK) return EXR_CANCELLED;
    got=s->read_at(s->context,at+done,(unsigned char *)out+done,n-done);
    if(!got || got>n-done) return exr_fail(e,EXR_IO,"Invalid or short FLAC source read");
    done+=got;
  }
  return EXR_OK;
}
static int bad(flac_bits *b,const char *s) { if(b->status==EXR_OK) b->status=exr_fail(b->error,EXR_FORMAT,"%s",s); return 0; }
static int byte(flac_bits *b,unsigned *out) {
  unsigned v,k;
  if(b->status!=EXR_OK) return 0;
  if(b->at-b->start>=UINT64_C(33554432)) { b->status=exr_fail(b->error,EXR_LIMIT,"FLAC frame exceeds 32 MiB"); return 0; }
  if(b->at-b->work_start>=FLAC_WORK_BYTES) { b->status=exr_fail(b->error,EXR_LIMIT,"FLAC read exceeds 256 MiB scan budget; retry continues from verified index"); return 0; }
  if(b->position==b->size) {
    uint64_t remaining=b->flac->source.size-b->at;
    if(!remaining) return bad(b,"Truncated FLAC frame");
    b->size=remaining<sizeof(b->bytes) ? (size_t)remaining : sizeof(b->bytes); b->position=0;
    b->status=exact(&b->flac->source,b->at,b->bytes,b->size,b->control,b->error);
    if(b->status!=EXR_OK) return 0;
  }
  v=b->bytes[b->position++]; b->at++;
  b->crc8^=v; b->crc16^=v<<8;
  for(k=0;k<8;k++) {
    b->crc8=((b->crc8<<1)^((b->crc8&128) ? 7u : 0u))&255u;
    b->crc16=((b->crc16<<1)^((b->crc16&32768) ? 0x8005u : 0u))&65535u;
  }
  *out=v; return 1;
}
static int bits(flac_bits *b,unsigned n,uint64_t *out) {
  uint64_t result=0;
  while(n) {
    unsigned take,part;
    if(!b->left) { if(!byte(b,&b->byte)) return 0; b->left=8; }
    take=n<b->left ? n : b->left; b->left-=take;
    part=(b->byte>>b->left)&((1u<<take)-1u);
    result=(result<<take)|part; n-=take;
  }
  *out=result; return 1;
}
static int signed_bits(flac_bits *b,unsigned n,int64_t *out) {
  uint64_t v;
  if(!n || n>33) return bad(b,"Invalid FLAC signed sample width");
  if(!bits(b,n,&v)) return 0;
  *out=(v&(UINT64_C(1)<<(n-1))) ? (int64_t)v-(int64_t)(UINT64_C(1)<<n) : (int64_t)v;
  return 1;
}
static int unary(flac_bits *b,uint64_t maximum,uint64_t *out) {
  uint64_t n=0,v;
  for(;;) {
    if(!bits(b,1,&v)) return 0;
    if(v) { *out=n; return 1; }
    if(++n>maximum) return bad(b,"FLAC unary value exceeds sample range");
    if(!(n&4095) && exr_control_cancel(b->control,b->error)!=EXR_OK) { b->status=EXR_CANCELLED; return 0; }
  }
}
static int coded_number(flac_bits *b,uint64_t *out) {
  unsigned first,n,k; uint64_t value,v;
  if(!byte(b,&first)) return 0;
  if(first<128) { *out=first; return 1; }
  if(first<0xc0 || first==0xff) return bad(b,"Invalid FLAC coded frame number");
  for(n=0; n<8 && (first&(128u>>n));n++) {}
  if(n<2 || n>7) return bad(b,"Invalid FLAC coded frame number");
  value=first&((1u<<(7-n))-1u);
  for(k=1;k<n;k++) {
    unsigned c;
    if(!byte(b,&c)) return 0;
    if((c&0xc0)!=0x80) return bad(b,"Invalid FLAC frame-number continuation");
    value=(value<<6)|(c&63);
  }
  v= n==2 ? UINT64_C(128) : UINT64_C(1)<<(5*n-4);
  if(value<v || value>UINT64_C(0xfffffffff)) return bad(b,"Noncanonical FLAC coded frame number");
  *out=value; return 1;
}
static int header(flac_bits *b,flac_frame *f) {
  static const unsigned rates[12]={0,88200,176400,192000,8000,16000,22050,24000,32000,44100,48000,96000};
  static const unsigned widths[8]={0,8,12,0,16,20,24,32};
  unsigned a,c,d,block,rate,width,crc; uint64_t n,v;
  if(!byte(b,&a) || !byte(b,&c) || !byte(b,&d) || !byte(b,&width)) return 0;
  if(a!=255 || (c&0xfe)!=0xf8 || (width&1)) return bad(b,"Invalid FLAC frame sync/reserved bits");
  f->variable=(int)(c&1); block=d>>4; rate=d&15; f->assignment=width>>4; width=(width>>1)&7;
  if(!block || rate==15 || width==3 || f->assignment>10) return bad(b,"Reserved FLAC frame header code");
  if(!coded_number(b,&n)) return 0;
  if(!f->variable && n>UINT64_C(0x7fffffff)) return bad(b,"FLAC fixed frame number exceeds 31 bits");
  if(block==1) f->count=192;
  else if(block<=5) f->count=576u<<(block-2);
  else if(block==6 || block==7) { if(!bits(b,block==6 ? 8 : 16,&v)) return 0; f->count=(unsigned)v+1; }
  else f->count=256u<<(block-8);
  if(rate<=11) rate=rates[rate];
  else { unsigned code=rate; if(!bits(b,code==12 ? 8 : 16,&v)) return 0; rate=(unsigned)v*(code==12 ? 1000u : code==14 ? 10u : 1u); if(!rate) return bad(b,"Zero explicit FLAC audio sample rate"); }
  if(!byte(b,&crc)) return 0;
  (void)crc;
  if(b->crc8) return bad(b,"FLAC header CRC mismatch");
  if((rate && rate!=b->flac->info.sample_rate) || (width && widths[width]!=b->flac->info.bits_per_sample) ||
     (f->assignment<=7 ? f->assignment+1 : 2)!=b->flac->info.channels || f->count>b->flac->maximum_block)
    return bad(b,"FLAC frame disagrees with STREAMINFO");
  f->number=n; f->first=f->variable ? n : n*b->flac->maximum_block;
  return 1;
}
static int residual(flac_bits *b,int64_t *s,unsigned count,unsigned order) {
  uint64_t method,power,v; unsigned partition,partitions,each,at=order;
  if(!bits(b,2,&method) || !bits(b,4,&power)) return 0;
  if(method>1) return bad(b,"Reserved FLAC residual coding method");
  partitions=1u<<(unsigned)power;
  if(count%partitions || count/partitions<=order) return bad(b,"Invalid FLAC residual partition order");
  each=count/partitions;
  for(partition=0;partition<partitions;partition++) {
    unsigned n=each-(partition ? 0 : order),k,parameter,raw=0;
    if(!bits(b,method ? 5 : 4,&v)) return 0;
    parameter=(unsigned)v;
    if(parameter==(method ? 31u : 15u)) { if(!bits(b,5,&v)) return 0; raw=(unsigned)v; }
    for(k=0;k<n;k++) {
      if(parameter==(method ? 31u : 15u)) {
        if(!raw) s[at++]=0;
        else { if(!signed_bits(b,raw,s+at)) return 0; at++; }
      } else {
        uint64_t q,remainder;
        if(!unary(b,UINT32_MAX>>parameter,&q) || !bits(b,parameter,&remainder)) return 0;
        v=(q<<parameter)|remainder;
        if(v>=UINT32_MAX) return bad(b,"FLAC residual exceeds signed 32-bit range");
        s[at++]=(v&1) ? -(int64_t)(v>>1)-1 : (int64_t)(v>>1);
      }
    }
    if(exr_control_cancel(b->control,b->error)!=EXR_OK) { b->status=EXR_CANCELLED; return 0; }
  }
  return 1;
}
static int range(int64_t v,unsigned width) {
  int64_t limit=INT64_C(1)<<(width-1);
  return v>=-limit && v<limit;
}
static int subframe(flac_bits *b,int64_t *s,unsigned count,unsigned width) {
  uint64_t h,v; unsigned type,wasted=0,order=0,i; int64_t coeff[32],shift=0;
  if(!bits(b,8,&h)) return 0;
  if(h&128) return bad(b,"Reserved FLAC subframe bit is set");
  type=((unsigned)h>>1)&63;
  if(h&1) { if(!unary(b,width-1,&v)) return 0; wasted=(unsigned)v+1; }
  if(wasted>=width) return bad(b,"FLAC wasted bits exceed sample width");
  width-=wasted;
  if(!type) {
    if(!signed_bits(b,width,s)) return 0;
    for(i=1;i<count;i++) s[i]=s[0];
  } else if(type==1) {
    for(i=0;i<count;i++) if(!signed_bits(b,width,s+i)) return 0;
  } else if((type>=8 && type<=12) || type>=32) {
    order=type>=32 ? type-31 : type-8;
    if(order>count) return bad(b,"FLAC predictor order exceeds block");
    for(i=0;i<order;i++) if(!signed_bits(b,width,s+i)) return 0;
    if(type>=32) {
      unsigned precision;
      if(!bits(b,4,&v)) return 0;
      if(v==15) return bad(b,"Reserved FLAC LPC precision");
      precision=(unsigned)v+1;
      if(!signed_bits(b,5,&shift)) return 0;
      if(shift<0) return bad(b,"Negative FLAC LPC shift is forbidden");
      for(i=0;i<order;i++) if(!signed_bits(b,precision,coeff+i)) return 0;
    } else {
      static const int fixed[5][4]={{0,0,0,0},{1,0,0,0},{2,-1,0,0},{3,-3,1,0},{4,-6,4,-1}};
      for(i=0;i<order;i++) coeff[i]=fixed[order][i];
    }
    if(!residual(b,s,count,order)) return 0;
    for(i=order;i<count;i++) {
      int64_t prediction=0; unsigned k;
      /* Samples are at most 33 bits; 32 signed 15-bit coefficients fit in 64. */
      for(k=0;k<order;k++) prediction+=coeff[k]*s[i-k-1];
      if(shift>=0) {
        int64_t divisor=INT64_C(1)<<(unsigned)shift;
        prediction=prediction/divisor-((prediction<0 && prediction%divisor) ? 1 : 0);
      }
      if((s[i]>0 && prediction>INT64_MAX-s[i]) || (s[i]<0 && prediction<INT64_MIN-s[i])) return bad(b,"FLAC reconstructed sample overflows");
      s[i]+=prediction;
      if(!range(s[i],width)) return bad(b,"FLAC reconstructed sample exceeds bit depth");
      if(!(i&1023) && exr_control_cancel(b->control,b->error)!=EXR_OK) { b->status=EXR_CANCELLED; return 0; }
    }
  } else return bad(b,"Reserved FLAC subframe type");
  if(wasted) for(i=0;i<count;i++) s[i]*=INT64_C(1)<<wasted;
  return 1;
}
static exr_status decode(exr_flac *f,uint64_t offset,uint64_t work_start,const exr_control *control,flac_frame *frame,exr_error *e) {
  flac_bits b; unsigned c,i,footer; uint64_t padding;
  memset(&b,0,sizeof(b)); memset(frame,0,sizeof(*frame));
  b.flac=f; b.control=control; b.error=e; b.at=b.start=offset; b.work_start=work_start;
  if(!header(&b,frame)) return b.status;
  if(!exr_grow((void **)&f->samples,&f->capacity,(size_t)frame->count*f->info.channels,sizeof(*f->samples))) return exr_fail(e,EXR_MEMORY,"FLAC sample buffer allocation failed");
  for(c=0;c<f->info.channels;c++) {
    unsigned width=f->info.bits_per_sample;
    if((frame->assignment==8 && c==1) || (frame->assignment==9 && c==0) || (frame->assignment==10 && c==1)) width++;
    if(!subframe(&b,f->samples+(size_t)c*frame->count,frame->count,width)) return b.status;
  }
  if(b.left && (!bits(&b,b.left,&padding) || padding)) { if(b.status==EXR_OK) bad(&b,"Nonzero FLAC frame padding"); return b.status; }
  if(!byte(&b,&footer) || !byte(&b,&footer)) return b.status;
  if(b.crc16) return exr_fail(e,EXR_FORMAT,"FLAC frame CRC mismatch");
  if(f->maximum_frame && b.at-offset>f->maximum_frame) return exr_fail(e,EXR_FORMAT,"FLAC frame exceeds declared maximum size");
  frame->next=b.at;
  if(frame->assignment>=8) {
    int64_t *left=f->samples,*right=left+frame->count;
    for(i=0;i<frame->count;i++) {
      int64_t a=left[i],d=right[i];
      if(frame->assignment==8) right[i]=a-d;
      else if(frame->assignment==9) left[i]=a+d;
      else { int64_t twice=a*2+(d&1); left[i]=(twice+d)/2; right[i]=(twice-d)/2; }
      if(!range(left[i],f->info.bits_per_sample) || !range(right[i],f->info.bits_per_sample)) return exr_fail(e,EXR_FORMAT,"Invalid FLAC stereo reconstruction");
    }
  }
  return exr_control_cancel(control,e);
}
static void point(exr_flac *f,uint64_t sample,uint64_t offset,uint64_t number) {
  if(offset<=f->index[f->count-1].offset || number%f->stride) return;
  if(f->count==FLAC_INDEX) {
    size_t i;
    for(i=1;i<FLAC_INDEX/2;i++) f->index[i]=f->index[i*2];
    f->count=FLAC_INDEX/2; f->stride*=2;
    if(number%f->stride) return;
  }
  f->index[f->count++]=(flac_point){sample,offset,number};
}
void exr_flac_free(exr_flac *f) { if(f) { if(f->source.release) f->source.release(f->source.context); free(f->samples); free(f->seek); free(f); } }
const exr_flac_info *exr_flac_format(const exr_flac *f) { return f ? &f->info : NULL; }
exr_status exr_flac_open_source(const exr_source *source,exr_flac **out,exr_error *e) {
  exr_flac *f; unsigned char h[4],stream[34]; uint64_t at=4,packed; unsigned blocks=0,last=0,i; int have_seek=0; exr_status status;
  if(out) *out=NULL;
  if(!source || !out || !source->read_at || source->size<42) return exr_fail(e,EXR_ARGUMENT,"Invalid FLAC source");
  status=exact(source,0,h,4,&source->control,e); if(status!=EXR_OK) return status;
  if(memcmp(h,"fLaC",4)) return exr_fail(e,EXR_FORMAT,"Source is not native FLAC");
  f=calloc(1,sizeof(*f)); if(!f) return exr_fail(e,EXR_MEMORY,"FLAC reader allocation failed"); f->strategy=-1;
  while(!last) {
    unsigned type,n;
    if(++blocks>65536) { status=exr_fail(e,EXR_LIMIT,"FLAC metadata block count exceeds budget"); goto fail; }
    status=exact(source,at,h,4,&source->control,e); if(status!=EXR_OK) goto fail;
    at+=4; last=h[0]>>7; type=h[0]&127; n=be24(h+1);
    if(n>source->size-at || at+n>UINT64_C(67108864)) { status=exr_fail(e,n>source->size-at ? EXR_FORMAT : EXR_LIMIT,"FLAC metadata length exceeds source or 64 MiB budget"); goto fail; }
    if(type==127 || (!type && (blocks!=1 || n!=34)) || (blocks==1 && type!=0)) { status=exr_fail(e,EXR_FORMAT,"Invalid FLAC STREAMINFO/metadata order"); goto fail; }
    if(!type) {
      status=exact(source,at,stream,34,&source->control,e); if(status!=EXR_OK) goto fail;
      f->minimum_block=be16(stream); f->maximum_block=be16(stream+2); f->maximum_frame=be24(stream+7);
      packed=0; for(i=10;i<18;i++) packed=(packed<<8)|stream[i];
      f->info.sample_rate=(uint32_t)(packed>>44); f->info.channels=(uint32_t)((packed>>41)&7)+1;
      f->info.bits_per_sample=(uint32_t)((packed>>36)&31)+1; f->info.frames=packed&UINT64_C(0xfffffffff);
      if(f->minimum_block<16 || f->maximum_block<f->minimum_block || !f->info.sample_rate || f->info.bits_per_sample<4 ||
         (be24(stream+4) && f->maximum_frame && be24(stream+4)>f->maximum_frame)) { status=exr_fail(e,EXR_FORMAT,"Invalid FLAC STREAMINFO fields"); goto fail; }
      f->unknown=!f->info.frames;
      if(f->unknown) f->info.frames=UINT64_MAX;
    } else if(type==3) {
      uint64_t previous_sample=0,previous_offset=0; size_t j,total=n/18,step=(total+FLAC_INDEX-1)/FLAC_INDEX; int placeholder=0,have=0;
      if(have_seek++ || n%18) { status=exr_fail(e,EXR_FORMAT,"Invalid/duplicate FLAC SEEKTABLE"); goto fail; }
      if(total>65536) { status=exr_fail(e,EXR_LIMIT,"FLAC SEEKTABLE exceeds 65536 point budget"); goto fail; }
      if(total) { f->seek=calloc(total<FLAC_INDEX ? total : FLAC_INDEX,sizeof(*f->seek)); if(!f->seek) { status=exr_fail(e,EXR_MEMORY,"FLAC seek table allocation failed"); goto fail; } }
      for(j=0;j<total;j++) {
        unsigned char entry[18]; uint64_t sample,offset;
        status=exact(source,at+j*18,entry,18,&source->control,e); if(status!=EXR_OK) goto fail;
        sample=be64(entry); offset=be64(entry+8);
        if(sample==UINT64_MAX) { placeholder=1; continue; }
        if(placeholder || (have && (sample<=previous_sample || offset<=previous_offset)) || !be16(entry+16) || be16(entry+16)>f->maximum_block ||
           (!f->unknown && sample>=f->info.frames)) { status=exr_fail(e,EXR_FORMAT,"Invalid FLAC seek point order/sample"); goto fail; }
        if(!(j%step)) f->seek[f->seek_count++]=(flac_point){sample,offset,be16(entry+16)};
        f->seek_last_offset=offset;
        have=1; previous_sample=sample; previous_offset=offset;
      }
    }
    at+=n;
    status=exr_control_poll(&source->control,EXR_STAGE_READ,at,source->size,e); if(status!=EXR_OK) goto fail;
  }
  if(at==source->size) { if(!f->unknown) { status=exr_fail(e,EXR_FORMAT,"Missing FLAC audio frames"); goto fail; } f->info.frames=0; f->unknown=0; }
  if(f->seek_count && f->seek_last_offset>=source->size-at) { status=exr_fail(e,EXR_FORMAT,"FLAC seek offset exceeds audio payload"); goto fail; }
  for(i=0;i<f->seek_count;i++) {
    if(f->seek[i].offset>=source->size-at) { status=exr_fail(e,EXR_FORMAT,"FLAC seek offset exceeds audio payload"); goto fail; }
    f->seek[i].offset+=at;
  }
  f->data=at; f->source=*source; memset(&f->source.control,0,sizeof(f->source.control));
  f->count=1; f->stride=1; f->index[0]=(flac_point){0,at,0}; *out=f; return exr_fail(e,EXR_OK,"");
fail:
  free(f->seek); free(f); return status;
}
exr_status exr_flac_open(const char *path,const exr_control *control,exr_flac **out,exr_error *e) {
  exr_source source; exr_status status;
  if(out) *out=NULL;
  if(!path || !out) return exr_fail(e,EXR_ARGUMENT,"Invalid FLAC file input");
  status=exr_file_source_limit(path,INT64_MAX,&source,e); if(status!=EXR_OK) return status;
  if(control) source.control=*control;
  status=exr_flac_open_source(&source,out,e); if(status!=EXR_OK) source.release(source.context); return status;
}
exr_status exr_flac_read(exr_flac *f,uint64_t first,size_t requested,float *out,size_t *read,const exr_control *control,exr_error *e) {
  exr_status status; size_t i,done=0; uint64_t offset,sample,number,work_start,work=0; unsigned prior=0,seek_block=0;
  if(read) *read=0;
  if(!f || !read || (requested && !out) || first>f->info.frames || first>UINT64_C(0xfffffffff) || f->busy) return exr_fail(e,EXR_ARGUMENT,"Invalid or reentrant FLAC read");
  if(requested>65536) return exr_fail(e,EXR_LIMIT,"FLAC read exceeds 65536 frames");
  if(requested) memset(out,0,requested*f->info.channels*sizeof(*out));
  f->busy=1; status=exr_control_cancel(control,e); if(status!=EXR_OK) goto finish;
  if(!requested || first==f->info.frames) goto complete;
  for(i=1;i<f->count && f->index[i].sample<=first;i++) {}
  sample=f->index[i-1].sample; offset=work_start=f->index[i-1].offset; number=f->index[i-1].number;
  if(f->frontier.sample<=first && f->frontier.sample>sample) { sample=f->frontier.sample; offset=work_start=f->frontier.offset; number=f->frontier.number; }
  for(i=0;i<f->seek_count && f->seek[i].sample<=first;i++) {
    if(f->seek[i].sample>sample) { sample=f->seek[i].sample; offset=work_start=f->seek[i].offset; number=UINT64_MAX; seek_block=(unsigned)f->seek[i].number; }
  }
  while(done<requested) {
    flac_frame frame; uint64_t end; size_t begin,n,c,k;
    if(offset==f->source.size) {
      if(!f->unknown && sample!=f->info.frames) { status=exr_fail(e,EXR_FORMAT,"FLAC ends before declared sample count"); goto finish; }
      f->unknown=0; f->info.frames=sample; break;
    }
    if(work>=FLAC_WORK_FRAMES) { status=exr_fail(e,EXR_LIMIT,"FLAC seek exceeds 16M sample scan budget; retry continues from verified index"); goto finish; }
    status=exr_control_poll(control,EXR_STAGE_READ,done,requested,e); if(status!=EXR_OK) goto finish;
    status=decode(f,offset,work_start,control,&frame,e); if(status!=EXR_OK) goto finish;
    if(number==UINT64_MAX) number=frame.variable ? sample/f->maximum_block : frame.number;
    if(frame.first!=sample || (!frame.variable && frame.number!=number) || (f->strategy!=-1 && f->strategy!=frame.variable) ||
       (seek_block && frame.count!=seek_block) ||
       (prior && prior!=f->maximum_block && !frame.variable)) { status=exr_fail(e,EXR_FORMAT,"Noncontiguous FLAC frame sequence"); goto finish; }
    f->strategy=frame.variable; seek_block=0; prior=frame.count; end=sample+frame.count;
    if(end>UINT64_C(0xfffffffff) || (!f->unknown && end>f->info.frames) ||
       (frame.count<f->minimum_block && frame.next!=f->source.size)) { status=exr_fail(e,EXR_FORMAT,"FLAC frame exceeds declared sample/block count"); goto finish; }
    if(!f->unknown && end==f->info.frames && frame.next!=f->source.size) { status=exr_fail(e,EXR_FORMAT,"Trailing FLAC frames or bytes after declared samples"); goto finish; }
    if(!f->unknown && frame.next==f->source.size && end!=f->info.frames) { status=exr_fail(e,EXR_FORMAT,"FLAC EOF disagrees with declared sample count"); goto finish; }
    point(f,sample,offset,number);
    if(end>f->frontier.sample) f->frontier=(flac_point){end,frame.next,number+1};
    work+=frame.count;
    if(first+done<end) {
      begin=(size_t)(first+done-sample); n=frame.count-begin; if(n>requested-done) n=requested-done;
      for(k=0;k<n;k++) for(c=0;c<f->info.channels;c++) out[(done+k)*f->info.channels+c]=(float)ldexp((double)f->samples[c*frame.count+begin+k],1-(int)f->info.bits_per_sample);
      done+=n;
    }
    sample=end; offset=frame.next; number++;
    if(offset==f->source.size && f->unknown) { f->unknown=0; f->info.frames=sample; }
    if(sample==f->info.frames) break;
  }
complete:
  status=exr_control_poll(control,EXR_STAGE_READ,done,done,e);
finish:
  f->busy=0;
  if(status!=EXR_OK) { if(requested) memset(out,0,requested*f->info.channels*sizeof(*out)); return status; }
  *read=done; return exr_fail(e,EXR_OK,"");
}
