/* SPDX-License-Identifier: MIT */
#include "exreader.h"
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static exr_error error; static unsigned checks;
#define CHECK(x) do { checks++; if(!(x)) { fprintf(stderr,"line %d: %s (%d: %s)\n",__LINE__,#x,error.code,error.message); exit(1); } } while(0)
#define OK(x) CHECK((x)==EXR_OK)
#define NEAR(a,b) CHECK(fabs((double)(a)-(b))<1e-6)
typedef struct { unsigned char bytes[65536]; size_t size,reads,released,fail_at,max_read; int fail,over; exr_flac *flac; } memory;
typedef struct { memory *m; unsigned left; } writer;
static void put16(unsigned char *p,unsigned n) { p[0]=(unsigned char)(n>>8); p[1]=(unsigned char)n; }
static void put64(unsigned char *p,uint64_t n) { unsigned i; for(i=0;i<8;i++) p[7-i]=(unsigned char)(n>>(i*8)); }
static unsigned crc(const unsigned char *p,size_t n,unsigned width,unsigned polynomial) {
  unsigned value=0,i; size_t k;
  for(k=0;k<n;k++) { value^=(unsigned)p[k]<<(width-8); for(i=0;i<8;i++) value=((value<<1)^((value&(1u<<(width-1))) ? polynomial : 0))&((1u<<width)-1); }
  return value;
}
static void putbits(writer *w,unsigned count,uint64_t value) {
  unsigned i;
  for(i=count;i>0;i--) {
    if(!w->left) { CHECK(w->m->size<sizeof(w->m->bytes)); w->m->bytes[w->m->size++]=0; w->left=8; }
    w->left--; w->m->bytes[w->m->size-1]|=(unsigned char)(((value>>(i-1))&1)<<w->left);
  }
}
static void code(writer *w,uint64_t value) {
  unsigned n,i;
  if(value<128) { putbits(w,8,value); return; }
  for(n=2;n<7 && value>=(UINT64_C(1)<<(5*n+1));n++) {}
  putbits(w,8,((255u<<(8-n))&255u)|(unsigned)(value>>(6*(n-1))));
  for(i=n-1;i>0;i--) putbits(w,8,128|((value>>(6*(i-1)))&63));
}
static size_t read_at(void *context,uint64_t at,void *out,size_t n) {
  memory *m=context; m->reads++;
  if(m->flac) { float output; size_t got; CHECK(exr_flac_read(m->flac,0,1,&output,&got,NULL,&error)==EXR_ARGUMENT && !got); }
  if(m->over) return n+1;
  if(m->fail || (m->fail_at && at>=m->fail_at)) return 0;
  if(at>=m->size) return 0;
  if(n>m->size-(size_t)at) n=m->size-(size_t)at;
  if(m->max_read && n>m->max_read) n=m->max_read;
  memcpy(out,m->bytes+(size_t)at,n); return n;
}
static void release(void *context) { ((memory *)context)->released++; }
static exr_source source(memory *m) { exr_source s={0}; s.size=m->size; s.read_at=read_at; s.release=release; s.context=m; return s; }
static void stream(memory *m,unsigned channels,unsigned width,uint64_t samples,unsigned block,int seek) {
  uint64_t packed=(UINT64_C(48000)<<44)|((uint64_t)(channels-1)<<41)|((uint64_t)(width-1)<<36)|samples;
  memset(m,0,sizeof(*m)); memcpy(m->bytes,"fLaC",4); m->bytes[4]=(unsigned char)(seek ? 0 : 128); m->bytes[7]=34;
  put16(m->bytes+8,block); put16(m->bytes+10,block); put64(m->bytes+18,packed); m->size=42;
  if(seek) { m->bytes[42]=131; m->bytes[45]=36; m->size=82; }
}
static void sub(writer *w,const int64_t *s,unsigned count,unsigned width,unsigned type,unsigned wasted,unsigned method,int parameter,int shift) {
  unsigned order=type>=32 ? type-31 : type>=8 ? type-8 : 0,i,j;
  int64_t coeff[32]={0};
  putbits(w,8,(type<<1)|(wasted ? 1 : 0));
  for(i=0;i<wasted;i++) putbits(w,1,i+1==wasted);
  width-=wasted;
  if(type<2) { for(i=0;i<(type ? count : 1);i++) putbits(w,width,(uint64_t)(s[i]/(INT64_C(1)<<wasted))); return; }
  for(i=0;i<order;i++) putbits(w,width,(uint64_t)(s[i]/(INT64_C(1)<<wasted)));
  if(type>=32) {
    putbits(w,4,3); putbits(w,5,(uint64_t)shift);
    for(i=0;i<order;i++) { coeff[i]= i==0 ? 2 : i==1 ? -1 : 0; putbits(w,4,(uint64_t)coeff[i]); }
  } else {
    static const int fixed[5][4]={{0,0,0,0},{1,0,0,0},{2,-1,0,0},{3,-3,1,0},{4,-6,4,-1}};
    for(i=0;i<order;i++) coeff[i]=fixed[order][i];
  }
  putbits(w,2,method); putbits(w,4,0);
  putbits(w,method ? 5 : 4,parameter<0 ? (method ? 31 : 15) : (unsigned)parameter);
  if(parameter<0) putbits(w,5,(unsigned)(-parameter));
  for(i=order;i<count;i++) {
    int64_t prediction=0,residue; uint64_t folded,q;
    for(j=0;j<order;j++) prediction+=coeff[j]*(s[i-j-1]/(INT64_C(1)<<wasted));
    if(shift>0) { int64_t d=INT64_C(1)<<(unsigned)shift; prediction=prediction/d-((prediction<0 && prediction%d) ? 1 : 0); }
    else if(shift<0) prediction*=INT64_C(1)<<(unsigned)(-shift);
    residue=s[i]/(INT64_C(1)<<wasted)-prediction;
    if(parameter<0) { putbits(w,(unsigned)-parameter,(uint64_t)residue); continue; }
    folded=residue<0 ? (uint64_t)(-residue)*2-1 : (uint64_t)residue*2;
    q=folded>>(unsigned)parameter; CHECK(q<100000);
    while(q--) putbits(w,1,0);
    putbits(w,1,1); putbits(w,(unsigned)parameter,folded);
  }
}
static size_t frame(memory *m,unsigned channels,unsigned width,unsigned count,unsigned assignment,uint64_t number,int variable,
                    int64_t data[8][64],unsigned type,unsigned wasted,unsigned method,int parameter,int shift) {
  writer w={m,0}; size_t start=m->size; unsigned c,i,check; int64_t transformed[64];
  putbits(&w,16,variable ? 0xfff9 : 0xfff8); putbits(&w,8,0x60); putbits(&w,8,assignment<<4); code(&w,number); putbits(&w,8,count-1);
  check=crc(m->bytes+start,m->size-start,8,7); putbits(&w,8,check);
  for(c=0;c<channels;c++) {
    unsigned bits=width;
    for(i=0;i<count;i++) {
      if(assignment==8) transformed[i]=c ? data[0][i]-data[1][i] : data[0][i];
      else if(assignment==9) transformed[i]=c ? data[1][i] : data[0][i]-data[1][i];
      else if(assignment==10) { int64_t total=data[0][i]+data[1][i]; transformed[i]=c ? data[0][i]-data[1][i] : total/2-((total<0 && total%2) ? 1 : 0); }
      else transformed[i]=data[c][i];
    }
    if((assignment==8 && c==1) || (assignment==9 && c==0) || (assignment==10 && c==1)) bits++;
    sub(&w,transformed,count,bits,type,wasted,method,parameter,shift);
  }
  w.left=0; check=crc(m->bytes+start,m->size-start,16,0x8005); putbits(&w,16,check);
  return start;
}
static void verify(memory *m,unsigned channels,unsigned width,unsigned count,int64_t data[8][64]) {
  exr_source s=source(m); exr_flac *f=NULL; const exr_flac_info *info; float out[8*64]; size_t got; unsigned i,c;
  OK(exr_flac_open_source(&s,&f,&error)); info=exr_flac_format(f); CHECK(info->frames==count && info->channels==channels && info->bits_per_sample==width && info->sample_rate==48000);
  OK(exr_flac_read(f,0,count,out,&got,NULL,&error)); CHECK(got==count);
  for(i=0;i<count;i++) for(c=0;c<channels;c++) NEAR(out[i*channels+c],ldexp((double)data[c][i],1-(int)width));
  OK(exr_flac_read(f,count-1,3,out,&got,NULL,&error)); CHECK(got==1); for(c=channels;c<3*channels;c++) CHECK(!out[c]);
  exr_flac_free(f); CHECK(m->released==1);
}
static int cancelled(void *context) { return *(int *)context; }
static void cancel_progress(void *context,exr_stage stage,uint64_t completed,uint64_t total) { (void)stage; if(completed==total && completed) *(int *)context=1; }
int main(int argc,char **argv) {
  memory m; int64_t data[8][64]={{0}}; unsigned i,c,type,assignment; exr_source s; exr_flac *f=NULL; float out[8*64]; size_t got,start,second; exr_control control={0}; int stop=1;
  CHECK(argc==2);
  for(i=0;i<32;i++) for(c=0;c<8;c++) data[c][i]=(int64_t)i*4+(int64_t)c*10-80;
  /* Every subframe family, both residual methods, and escaped/wasted values. */
  for(type=0;type<10;type++) {
    unsigned actual=type==0 ? 0 : type==1 ? 1 : type<7 ? type+6 : type==7 ? 32 : type==8 ? 33 : 35;
    if(!actual) for(i=0;i<32;i++) data[0][i]=-12;
    else for(i=0;i<32;i++) data[0][i]=(int64_t)i*4-80;
    stream(&m,1,16,32,32,0); frame(&m,1,16,32,0,0,0,data,actual,actual==1 ? 2 : 0,type&1,type==8 ? -16 : 3,type==9 ? 1 : 0); verify(&m,1,16,32,data);
  }
  /* RFC 9639 forbids a negative LPC shift and empty first partitions. */
  stream(&m,1,16,32,32,0); frame(&m,1,16,32,0,0,0,data,33,0,0,3,-1); s=source(&m);
  OK(exr_flac_open_source(&s,&f,&error)); CHECK(exr_flac_read(f,0,32,out,&got,NULL,&error)==EXR_FORMAT && !got); exr_flac_free(f);
  stream(&m,1,16,32,32,0); frame(&m,1,16,32,0,0,0,data,63,0,0,3,0); s=source(&m);
  OK(exr_flac_open_source(&s,&f,&error)); CHECK(exr_flac_read(f,0,32,out,&got,NULL,&error)==EXR_FORMAT && !got); exr_flac_free(f);
  for(assignment=8;assignment<=10;assignment++) {
    for(i=0;i<32;i++) { data[0][i]=(int64_t)i*17-230; data[1][i]=200-(int64_t)i*11; }
    stream(&m,2,16,32,32,0); frame(&m,2,16,32,assignment,0,0,data,1,0,0,0,0); verify(&m,2,16,32,data);
    for(i=0;i<32;i++) { data[0][i]=(i&1) ? INT32_MAX : INT32_MIN; data[1][i]=(i&1) ? INT32_MIN : INT32_MAX; }
    stream(&m,2,32,32,32,0); frame(&m,2,32,32,assignment,0,0,data,1,0,0,0,0); verify(&m,2,32,32,data);
  }
  for(c=1;c<=8;c++) {
    for(i=0;i<32;i++) { unsigned k; for(k=0;k<c;k++) data[k][i]=(int64_t)(i%8)-4; }
    stream(&m,c,4,32,32,0); frame(&m,c,4,32,c-1,0,0,data,1,0,0,0,0); verify(&m,c,4,32,data);
  }
  /* Variable blocks, extended coded sample number, final short block, seek. */
  stream(&m,1,16,173,32,1); start=m.size;
  for(i=0;i<5;i++) frame(&m,1,16,32,0,(uint64_t)i*32,1,data,1,0,0,0,0);
  second=m.size; frame(&m,1,16,13,0,160,1,data,1,0,0,0,0);
  put64(m.bytes+46,0); put64(m.bytes+54,0); put16(m.bytes+62,32);
  put64(m.bytes+64,160); put64(m.bytes+72,second-start); put16(m.bytes+80,13);
  s=source(&m); OK(exr_flac_open_source(&s,&f,&error)); m.reads=0; OK(exr_flac_read(f,165,4,out,&got,NULL,&error)); CHECK(got==4 && m.reads<=2); NEAR(out[0],ldexp((double)data[0][5],-15));
  OK(exr_flac_read(f,31,3,out,&got,NULL,&error)); CHECK(got==3); NEAR(out[0],ldexp((double)data[0][31],-15)); NEAR(out[1],ldexp((double)data[0][0],-15));
  exr_flac_free(f);
  /* Corrupted seek locations are not trusted as audio frames. */
  put64(m.bytes+72,second-start+1); s=source(&m); OK(exr_flac_open_source(&s,&f,&error)); CHECK(exr_flac_read(f,165,1,out,&got,NULL,&error)==EXR_FORMAT && !got && !out[0]); exr_flac_free(f);
  put64(m.bytes+72,UINT64_MAX); s=source(&m); CHECK(exr_flac_open_source(&s,&f,&error)==EXR_FORMAT && !f);
  /* Unknown total length becomes exact only after a verified audio EOF. */
  stream(&m,1,16,0,32,0); frame(&m,1,16,32,0,0,0,data,1,0,0,0,0); frame(&m,1,16,13,0,1,0,data,1,0,0,0,0);
  s=source(&m); OK(exr_flac_open_source(&s,&f,&error)); CHECK(exr_flac_format(f)->frames==UINT64_MAX); OK(exr_flac_read(f,40,20,out,&got,NULL,&error)); CHECK(got==5 && exr_flac_format(f)->frames==45); exr_flac_free(f);
  { memory other; exr_pcm *pcm=NULL; float direct[64]; size_t native_count;
    m.released=0; other=m; s=source(&m); OK(exr_flac_open_source(&s,&f,&error)); s=source(&other); OK(exr_pcm_open_source(&s,&pcm,&error));
    CHECK(exr_pcm_format(pcm)->frames==UINT64_MAX && exr_pcm_format(pcm)->channels==1);
    OK(exr_flac_read(f,40,20,direct,&native_count,NULL,&error)); OK(exr_pcm_read(pcm,40,20,out,&got,NULL,&error));
    CHECK(got==native_count && got==5 && exr_pcm_format(pcm)->frames==45); CHECK(!memcmp(out,direct,20*sizeof(*out)));
    exr_pcm_free(pcm); exr_flac_free(f); CHECK(m.released==1 && other.released==1);
  }
  /* Callback ownership, short reads, reentry, cancellation, and retry. */
  stream(&m,1,16,32,32,0); start=frame(&m,1,16,32,0,0,0,data,1,0,0,0,0); m.max_read=3; s=source(&m);
  OK(exr_flac_open_source(&s,&f,&error)); CHECK(!m.released); m.flac=f; OK(exr_flac_read(f,0,32,out,&got,NULL,&error)); m.flac=NULL;
  control.cancelled=cancelled; control.context=&stop; CHECK(exr_flac_read(f,0,32,out,&got,&control,&error)==EXR_CANCELLED && !got); for(i=0;i<32;i++) CHECK(!out[i]);
  stop=0; control.progress=cancel_progress; CHECK(exr_flac_read(f,0,32,out,&got,&control,&error)==EXR_CANCELLED && !got && !out[0]);
  m.fail=1; CHECK(exr_flac_read(f,0,32,out,&got,NULL,&error)==EXR_IO && !got && !out[0]); m.fail=0;
  m.over=1; CHECK(exr_flac_read(f,0,32,out,&got,NULL,&error)==EXR_IO && !got); m.over=0;
  OK(exr_flac_read(f,0,32,out,&got,NULL,&error)); CHECK(got==32);
  CHECK(exr_flac_read(f,33,1,out,&got,NULL,&error)==EXR_ARGUMENT && !got);
  CHECK(exr_flac_read(f,0,65537,out,&got,NULL,&error)==EXR_LIMIT && !got);
  OK(exr_flac_read(f,32,1,out,&got,NULL,&error)); CHECK(!got && !out[0]);
  exr_flac_free(f); CHECK(m.released==1); s=source(&m); stop=1; s.control=control; CHECK(exr_flac_open_source(&s,&f,&error)==EXR_CANCELLED && !f && m.released==1);
  /* CRC header and frame footer failures reset every output sample. */
  m.bytes[start+6]^=1; s=source(&m); OK(exr_flac_open_source(&s,&f,&error)); CHECK(exr_flac_read(f,0,32,out,&got,NULL,&error)==EXR_FORMAT && !got); exr_flac_free(f); m.bytes[start+6]^=1;
  m.bytes[m.size-1]^=1; s=source(&m); OK(exr_flac_open_source(&s,&f,&error)); CHECK(exr_flac_read(f,0,32,out,&got,NULL,&error)==EXR_FORMAT && !got); for(i=0;i<32;i++) CHECK(!out[i]); exr_flac_free(f); m.bytes[m.size-1]^=1;
  s=source(&m); s.size--; OK(exr_flac_open_source(&s,&f,&error)); CHECK(exr_flac_read(f,0,32,out,&got,NULL,&error)==EXR_FORMAT && !got); exr_flac_free(f);
  { char path[4096]; FILE *file; snprintf(path,sizeof(path),"%s/flac-native-test.flac",argv[1]); file=fopen(path,"wb"); CHECK(file && fwrite(m.bytes,1,m.size,file)==m.size && !fclose(file)); OK(exr_flac_open(path,NULL,&f,&error)); OK(exr_flac_read(f,17,3,out,&got,NULL,&error)); CHECK(got==3); exr_flac_free(f); remove(path); }
  /* Strict STREAMINFO and metadata rejection; failure keeps source ownership. */
  stream(&m,1,16,32,32,0); m.bytes[4]=0; s=source(&m); CHECK(exr_flac_open_source(&s,&f,&error)==EXR_FORMAT && !f && !m.released);
  stream(&m,1,16,32,32,0); m.bytes[8]=0; m.bytes[9]=15; s=source(&m); CHECK(exr_flac_open_source(&s,&f,&error)==EXR_FORMAT && !f);
  stream(&m,1,16,0,32,0); s=source(&m); OK(exr_flac_open_source(&s,&f,&error)); CHECK(!exr_flac_format(f)->frames); OK(exr_flac_read(f,0,1,out,&got,NULL,&error)); CHECK(!got && !out[0]); exr_flac_free(f);
  CHECK(!exr_flac_format(NULL)); exr_flac_free(NULL); printf("%u native FLAC checks passed\n",checks); return 0;
}
