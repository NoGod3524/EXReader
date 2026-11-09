/* SPDX-License-Identifier: MIT */
/* Scalar, bounded decoder written from the LZMA format specification.
   The output doubles as the dictionary; no allocation follows a dictionary
   size supplied by the archive. LZMA2 resets restrict access to prior bytes. */
#include "lzma_internal.h"

typedef struct {
  const unsigned char *data;
  size_t size, at;
  uint32_t range, code;
  int bad;
} range_reader;
typedef struct { uint16_t choice[2],low[16][8],mid[16][8],high[256]; } length_model;
typedef struct {
  uint16_t match[12][16],rep[12],g0[12],g1[12],g2[12],short_rep[12][16];
  uint16_t slot[4][64],distance[114],align[16];
  length_model length,rep_length;
} fixed_model;
typedef struct {
  fixed_model model;
  uint16_t *literal;
  size_t literal_count, dictionary_start;
  uint32_t dictionary, reps[4];
  unsigned state,lc,lp,pb;
} lz_state;

static unsigned byte(range_reader *r) {
  if(r->at==r->size) { r->bad=1; return 0; }
  return r->data[r->at++];
}
static void normalize(range_reader *r) {
  if(r->range < (UINT32_C(1)<<24)) { r->range<<=8; r->code=(r->code<<8)|byte(r); }
}
static unsigned bit(range_reader *r,uint16_t *p) {
  uint32_t bound=(r->range>>11)* *p;
  unsigned value=r->code>=bound;
  if(value) { r->range-=bound; r->code-=bound; *p-=(uint16_t)(*p>>5); }
  else { r->range=bound; *p+=(uint16_t)((2048-*p)>>5); }
  normalize(r); return value;
}
static uint32_t tree(range_reader *r,uint16_t *p,unsigned bits) {
  uint32_t node=1; unsigned i;
  for(i=0;i<bits;i++) node=(node<<1)|bit(r,p+node);
  return node-(UINT32_C(1)<<bits);
}
static uint32_t reverse_tree(range_reader *r,uint16_t *p,int base,unsigned bits) {
  uint32_t node=1,value=0; unsigned i,b;
  for(i=0;i<bits;i++) { b=bit(r,p+(base+(int)node)); node=(node<<1)|b; value|=(uint32_t)b<<i; }
  return value;
}
static uint32_t direct(range_reader *r,unsigned bits) {
  uint32_t value=0; unsigned i,b;
  for(i=0;i<bits;i++) {
    r->range>>=1; b=r->code>=r->range;
    if(b) r->code-=r->range;
    value=(value<<1)|b; normalize(r);
  }
  return value;
}
static unsigned length(range_reader *r,length_model *m,unsigned pos) {
  if(!bit(r,&m->choice[0])) return 2+tree(r,m->low[pos],3);
  if(!bit(r,&m->choice[1])) return 10+tree(r,m->mid[pos],3);
  return 18+tree(r,m->high,8);
}
static void reset(lz_state *s) {
  size_t i;
  /* All fields in fixed_model are uint16_t probability arrays. */
  uint16_t initial=1024;
  for(i=0;i<sizeof(s->model);i+=sizeof(initial))
    memcpy((unsigned char *)&s->model+i,&initial,sizeof(initial));
  for(i=0;i<s->literal_count;i++) s->literal[i]=1024;
  s->state=0; memset(s->reps,0,sizeof(s->reps));
}
static exr_status properties(lz_state *s,unsigned prop,int lzma2,exr_error *e) {
  size_t count; uint16_t *p;
  if(prop>=225) return exr_fail(e,EXR_FORMAT,"Invalid LZMA properties");
  s->lc=prop%9; prop/=9; s->lp=prop%5; s->pb=prop/5;
  if(lzma2 && s->lc+s->lp>4) return exr_fail(e,EXR_FORMAT,"Invalid LZMA2 literal context");
  count=(size_t)768<<(s->lc+s->lp);
  p=realloc(s->literal,count*sizeof(*p));
  if(!p) return exr_fail(e,EXR_MEMORY,"LZMA probability allocation failed");
  s->literal=p; s->literal_count=count; return EXR_OK;
}
static int distance_valid(const lz_state *s,size_t at,uint32_t dist) {
  return (uint64_t)dist < at-s->dictionary_start && dist<s->dictionary;
}
static exr_status chunk(lz_state *s,const unsigned char *in,size_t n,
  unsigned char *out,size_t *position,size_t end,int allow_marker,
  const exr_control *control,exr_error *e) {
  range_reader r={in,n,0,UINT32_MAX,0,0};
  size_t at=*position,poll=at;
  unsigned i;
  if(byte(&r)!=0) r.bad=1;
  for(i=0;i<4;i++) r.code=(r.code<<8)|byte(&r);
  if(r.code==UINT32_MAX) r.bad=1;
  while(!r.bad && (at<end || (allow_marker && r.code))) {
    unsigned state=s->state,pos=(unsigned)((at-s->dictionary_start)&((1u<<s->pb)-1));
    unsigned len; uint32_t dist;
    if(at-poll>=65536) {
      exr_status status=exr_control_cancel(control,e);
      if(status!=EXR_OK) return status;
      poll=at;
    }
    if(!bit(&r,&s->model.match[state][pos])) {
      unsigned prev=at>s->dictionary_start ? out[at-1] : 0;
      unsigned ctx=(unsigned)((at-s->dictionary_start)&((1u<<s->lp)-1));
      unsigned node=1;
      uint16_t *probs=s->literal+768*((ctx<<s->lc)+(prev>>(8-s->lc)));
      if(at==end) { r.bad=1; break; }
      if(state>=7) {
        unsigned match;
        if(!distance_valid(s,at,s->reps[0])) { r.bad=1; break; }
        match=out[at-(size_t)s->reps[0]-1];
        do {
          unsigned expected=(match>>7)&1,b;
          match<<=1; b=bit(&r,probs+256+(expected<<8)+node); node=(node<<1)|b;
          if(b!=expected) break;
        } while(node<256);
      }
      while(node<256) node=(node<<1)|bit(&r,probs+node);
      out[at++]=(unsigned char)node;
      s->state=state<4 ? 0 : (state<10 ? state-3 : state-6);
      continue;
    }
    if(bit(&r,&s->model.rep[state])) {
      if(!bit(&r,&s->model.g0[state])) {
        if(!bit(&r,&s->model.short_rep[state][pos])) {
          len=1; s->state=state<7 ? 9 : 11;
          goto copy_match;
        }
      } else {
        unsigned which;
        if(!bit(&r,&s->model.g1[state])) which=1;
        else which=bit(&r,&s->model.g2[state]) ? 3 : 2;
        dist=s->reps[which];
        for(i=which;i>0;i--) s->reps[i]=s->reps[i-1];
        s->reps[0]=dist;
      }
      len=length(&r,&s->model.rep_length,pos); s->state=state<7 ? 8 : 11;
    } else {
      unsigned slot,bits;
      len=length(&r,&s->model.length,pos); s->state=state<7 ? 7 : 10;
      slot=tree(&r,s->model.slot[len<6 ? len-2 : 3],6);
      dist=slot;
      if(slot>=4) {
        bits=(slot>>1)-1; dist=(2u+(slot&1))<<bits;
        if(slot<14) dist+=reverse_tree(&r,s->model.distance,(int)dist-(int)slot-1,bits);
        else { dist+=direct(&r,bits-4)<<4; dist+=reverse_tree(&r,s->model.align,0,4); }
      }
      if(dist==UINT32_MAX) {
        if(!allow_marker || at!=end || len!=2) r.bad=1;
        break;
      }
      for(i=3;i>0;i--) s->reps[i]=s->reps[i-1];
      s->reps[0]=dist;
    }
copy_match:
    if(!distance_valid(s,at,s->reps[0]) || len>end-at) { r.bad=1; break; }
    for(i=0;i<len;i++,at++) out[at]=out[at-(size_t)s->reps[0]-1];
  }
  if(r.bad || at!=end || r.at!=n || r.code)
    return exr_fail(e,EXR_FORMAT,"Corrupt or truncated LZMA stream");
  *position=at; return EXR_OK;
}
exr_status exr_lzma_decode(int lzma2,const unsigned char *props,size_t props_size,
  const unsigned char *in,size_t n,unsigned char *out,size_t size,
  const exr_control *control,exr_error *e) {
  lz_state s={0}; exr_status status=EXR_OK; size_t at=0,pos=0;
  int need_dictionary=1,need_state=1;
  if(!lzma2) {
    if(props_size!=5) return exr_fail(e,EXR_FORMAT,"Invalid LZMA property length");
    s.dictionary=(uint32_t)props[1]|((uint32_t)props[2]<<8)|((uint32_t)props[3]<<16)|((uint32_t)props[4]<<24);
    if(s.dictionary<4096) s.dictionary=4096;
    status=properties(&s,props[0],0,e);
    if(status==EXR_OK) { reset(&s); status=chunk(&s,in,n,out,&pos,size,1,control,e); }
    free(s.literal); return status;
  }
  if(props_size!=1 || props[0]>40) return exr_fail(e,EXR_FORMAT,"Invalid LZMA2 properties");
  s.dictionary=props[0]==40 ? UINT32_MAX : (2u+(props[0]&1))<<(props[0]/2+11);
  while(at<n) {
    unsigned c=in[at++]; size_t unpack,packed;
    status=exr_control_cancel(control,e);
    if(status!=EXR_OK) break;
    if(c==0) {
      if(at==n && pos==size) { free(s.literal); return EXR_OK; }
      break;
    }
    if(c!=1 && c!=2 && c<128) break;
    if(c==1 || c>=224) { s.dictionary_start=pos; need_dictionary=0; }
    if(need_dictionary || n-at<2) break;
    unpack=((size_t)in[at]<<8)+in[at+1]+1; at+=2;
    if(c<128) {
      if(unpack>n-at || unpack>size-pos) break;
      memcpy(out+pos,in+at,unpack); pos+=unpack; at+=unpack; need_state=1;
      continue;
    }
    unpack+=(size_t)(c&31)<<16;
    if(n-at<2) break;
    packed=((size_t)in[at]<<8)+in[at+1]+1; at+=2;
    if(c>=192) {
      if(at==n) break;
      status=properties(&s,in[at++],1,e);
      if(status!=EXR_OK) break;
    }
    if(!s.literal || (need_state && c<160)) break;
    if(c>=160) { reset(&s); need_state=0; }
    if(packed>n-at || unpack>size-pos) break;
    status=chunk(&s,in+at,packed,out,&pos,pos+unpack,0,control,e);
    if(status!=EXR_OK) break;
    at+=packed;
  }
  free(s.literal);
  return status==EXR_OK ? exr_fail(e,EXR_FORMAT,"Corrupt or truncated LZMA2 stream") : status;
}
