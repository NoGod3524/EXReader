/* SPDX-License-Identifier: GPL-3.0-only */
#include "exreader.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
static exr_error error; static unsigned checks;
#define CHECK(x) do { checks++; if(!(x)) { fprintf(stderr,"line %d: %s (%d: %s)\n",__LINE__,#x,error.code,error.message); exit(1); } } while(0)
#define OK(x) CHECK((x)==EXR_OK)
#define NEAR(a,b) CHECK(fabs((double)(a)-(b))<1e-6)
typedef struct { unsigned char bytes[512]; size_t size,reads,released; int fail,over,sparse; exr_wave *wave; } memory;
static void put16(unsigned char *p,unsigned n) { p[0]=(unsigned char)n; p[1]=(unsigned char)(n>>8); }
static void put32(unsigned char *p,uint32_t n) { put16(p,n&65535); put16(p+2,n>>16); }
static size_t read_at(void *context,uint64_t at,void *out,size_t size) {
  memory *m=context; size_t n=size>3 ? 3 : size; m->reads++;
  if(m->wave) { float nested; size_t got; CHECK(exr_wave_read(m->wave,0,1,&nested,&got,NULL,&error)==EXR_ARGUMENT && !got); }
  if(m->fail) return 0;
  if(m->over) return size+1;
  if(m->sparse) { memset(out,0,n); if(at<44) { size_t head=44-(size_t)at; if(head>n) head=n; memcpy(out,m->bytes+(size_t)at,head); } return n; }
  if(at>=m->size) return 0;
  if(n>m->size-(size_t)at) n=m->size-(size_t)at;
  memcpy(out,m->bytes+(size_t)at,n); return n;
}
static void release(void *context) { ((memory *)context)->released++; }
static exr_source source(memory *m) { exr_source s={0}; s.size=m->size; s.read_at=read_at; s.release=release; s.context=m; return s; }
static void make(memory *m,unsigned tag,unsigned bits,unsigned valid,unsigned channels,const void *pcm,size_t n,int extensible) {
  size_t fmt=extensible ? 40 : 16,data=20+fmt; memset(m,0,sizeof(*m));
  memcpy(m->bytes,"RIFF",4); memcpy(m->bytes+8,"WAVEfmt ",8); put32(m->bytes+16,(uint32_t)fmt);
  put16(m->bytes+20,extensible ? 65534 : tag); put16(m->bytes+22,channels); put32(m->bytes+24,48000);
  put32(m->bytes+28,48000*channels*(bits/8)); put16(m->bytes+32,channels*(bits/8)); put16(m->bytes+34,bits);
  if(extensible) { static const unsigned char tail[12]={0,0,16,0,128,0,0,170,0,56,155,113}; put16(m->bytes+36,22); put16(m->bytes+38,valid); put32(m->bytes+40,channels==2 ? 3 : 0); put32(m->bytes+44,tag); memcpy(m->bytes+48,tail,12); }
  memcpy(m->bytes+data,"data",4); put32(m->bytes+data+4,(uint32_t)n); if(n) memcpy(m->bytes+data+8,pcm,n);
  m->size=data+8+n+(n&1); put32(m->bytes+4,(uint32_t)m->size-8);
}
static int cancel(void *context) { return *(int *)context; }
static void cancel_later(void *context,exr_stage stage,uint64_t completed,uint64_t total) { (void)stage; (void)total; if(completed) *(int *)context=1; }
int main(int argc,char **argv) {
  memory m; exr_source s; exr_wave *w=NULL; const exr_wave_info *info; float out[16]; size_t n; exr_control control={0}; int stopped=1;
  const unsigned char u8[3]={0,128,255},stereo[8]={0,128,255,127,0,0,0,192},s24[9]={0,0,128,0,0,0,255,255,127};
  const unsigned char floats[16]={0,0,0,192,0,0,0,63,0,0,0,64,0,0,192,127};
  CHECK(argc==2); make(&m,1,8,8,1,u8,3,0); s=source(&m); OK(exr_wave_open_source(&s,&w,&error)); info=exr_wave_format(w); CHECK(info->frames==3 && info->channels==1 && info->sample_rate==48000 && info->bits_per_sample==8 && !info->floating && !m.released);
  OK(exr_wave_read(w,0,5,out,&n,NULL,&error)); CHECK(n==3); NEAR(out[0],-1); NEAR(out[1],0); NEAR(out[2],127.0/128); CHECK(!out[3] && !out[4]);
  m.wave=w; OK(exr_wave_read(w,1,1,out,&n,NULL,&error)); CHECK(n==1); m.wave=NULL;
  control.cancelled=cancel; control.context=&stopped; out[0]=1; CHECK(exr_wave_read(w,0,3,out,&n,&control,&error)==EXR_CANCELLED && !n && !out[0]);
  m.fail=1; CHECK(exr_wave_read(w,0,3,out,&n,NULL,&error)==EXR_IO && !n && !out[0]); m.fail=0;
  m.over=1; CHECK(exr_wave_read(w,0,3,out,&n,NULL,&error)==EXR_IO && !n); m.over=0;
  OK(exr_wave_read(w,3,1,out,&n,NULL,&error)); CHECK(!n && !out[0]);
  CHECK(exr_wave_read(w,4,1,out,&n,NULL,&error)==EXR_ARGUMENT && !n); CHECK(exr_wave_read(w,0,65537,out,&n,NULL,&error)==EXR_LIMIT && !n);
  exr_wave_free(w); CHECK(m.released==1);
  make(&m,1,16,16,2,stereo,8,0); s=source(&m); OK(exr_wave_open_source(&s,&w,&error)); OK(exr_wave_read(w,0,2,out,&n,NULL,&error)); CHECK(n==2); NEAR(out[0],-1); NEAR(out[1],32767.0/32768); NEAR(out[2],0); NEAR(out[3],-.5); exr_wave_free(w);
  make(&m,1,24,24,1,s24,9,0); s=source(&m); OK(exr_wave_open_source(&s,&w,&error)); OK(exr_wave_read(w,0,3,out,&n,NULL,&error)); NEAR(out[0],-1); NEAR(out[1],0); NEAR(out[2],8388607.0/8388608); exr_wave_free(w);
  { const unsigned char pcm[6]={0,0,128,240,255,127}; make(&m,1,24,20,1,pcm,6,1); s=source(&m); OK(exr_wave_open_source(&s,&w,&error)); CHECK(exr_wave_format(w)->valid_bits==20); OK(exr_wave_read(w,0,2,out,&n,NULL,&error)); NEAR(out[0],-1); NEAR(out[1],524287.0/524288); exr_wave_free(w); }
  { const unsigned char pcm[8]={0,0,0,128,255,255,255,127}; make(&m,1,32,32,1,pcm,8,0); s=source(&m); OK(exr_wave_open_source(&s,&w,&error)); OK(exr_wave_read(w,0,2,out,&n,NULL,&error)); NEAR(out[0],-1); NEAR(out[1],1); exr_wave_free(w); }
  make(&m,3,32,32,1,floats,16,0); s=source(&m); OK(exr_wave_open_source(&s,&w,&error)); OK(exr_wave_read(w,0,3,out,&n,NULL,&error)); NEAR(out[0],-1); NEAR(out[1],.5); NEAR(out[2],1);
  CHECK(exr_wave_read(w,2,2,out,&n,NULL,&error)==EXR_FORMAT && !n && !out[0] && !out[1]); exr_wave_free(w);
  { const unsigned char pcm[16]={0,0,0,0,0,0,240,191,0,0,0,0,0,0,224,63}; make(&m,3,64,64,1,pcm,16,1); s=source(&m); OK(exr_wave_open_source(&s,&w,&error)); OK(exr_wave_read(w,0,2,out,&n,NULL,&error)); NEAR(out[0],-1); NEAR(out[1],.5); exr_wave_free(w); }
  make(&m,1,16,16,2,stereo,8,1); m.bytes[40]=1; s=source(&m); CHECK(exr_wave_open_source(&s,&w,&error)==EXR_FORMAT && !w && !m.released);
  make(&m,1,8,8,1,u8,3,0); m.bytes[4]--; s=source(&m); CHECK(exr_wave_open_source(&s,&w,&error)==EXR_FORMAT && !w && !m.released);
  make(&m,1,8,8,1,u8,3,0); m.bytes[32]=2; s=source(&m); CHECK(exr_wave_open_source(&s,&w,&error)==EXR_FORMAT && !w);
  make(&m,1,16,16,1,u8,3,0); s=source(&m); CHECK(exr_wave_open_source(&s,&w,&error)==EXR_FORMAT && !w);
  make(&m,1,8,8,1,u8,3,0); s=source(&m); s.control=control; CHECK(exr_wave_open_source(&s,&w,&error)==EXR_CANCELLED && !w && !m.released);
  /* Chunk order, unknown odd chunks, duplicate formats and GUID validation. */
  make(&m,1,8,8,1,u8,3,0); memmove(m.bytes+22,m.bytes+12,m.size-12); memcpy(m.bytes+12,"JUNK",4); put32(m.bytes+16,1); m.bytes[20]=7; m.bytes[21]=0; m.size+=10; put32(m.bytes+4,(uint32_t)m.size-8); s=source(&m);
  OK(exr_wave_open_source(&s,&w,&error)); OK(exr_wave_read(w,0,1,out,&n,NULL,&error)); NEAR(out[0],-1); exr_wave_free(w);
  make(&m,1,8,8,1,u8,3,0); { unsigned char fmt[24]; memcpy(fmt,m.bytes+12,24); memmove(m.bytes+12,m.bytes+36,12); memcpy(m.bytes+24,fmt,24); } s=source(&m);
  OK(exr_wave_open_source(&s,&w,&error)); OK(exr_wave_read(w,2,1,out,&n,NULL,&error)); NEAR(out[0],127.0/128); exr_wave_free(w);
  make(&m,1,8,8,1,u8,3,0); memcpy(m.bytes+m.size,m.bytes+12,24); m.size+=24; put32(m.bytes+4,(uint32_t)m.size-8); s=source(&m); CHECK(exr_wave_open_source(&s,&w,&error)==EXR_FORMAT && !w && !m.released);
  make(&m,1,16,16,2,stereo,8,1); m.bytes[59]^=1; s=source(&m); CHECK(exr_wave_open_source(&s,&w,&error)==EXR_FORMAT && !w);
  { float *large=malloc(8000*sizeof(*large)); size_t i; CHECK(large); make(&m,1,8,8,1,NULL,0,0); m.sparse=1; put32(m.bytes+4,8036); put32(m.bytes+40,8000); s=source(&m); s.size=8044;
    OK(exr_wave_open_source(&s,&w,&error)); stopped=0; control.progress=cancel_later;
    CHECK(exr_wave_read(w,0,8000,large,&n,&control,&error)==EXR_CANCELLED && !n);
    for(i=0;i<8000;i++) CHECK(!large[i]);
    exr_wave_free(w); free(large); control.progress=NULL;
  }
  /* A sparse >4 GiB RIFF source: only headers and the requested frame are read. */
  make(&m,1,8,8,1,NULL,0,0); m.sparse=1; put32(m.bytes+4,UINT32_MAX-1); put32(m.bytes+40,UINT32_MAX-37); s=source(&m); s.size=(uint64_t)UINT32_MAX+7;
  OK(exr_wave_open_source(&s,&w,&error)); CHECK(exr_wave_format(w)->frames==UINT32_MAX-37 && m.reads<32);
  OK(exr_wave_read(w,(uint64_t)UINT32_MAX-38,1,out,&n,NULL,&error)); CHECK(n==1 && out[0]==-1); exr_wave_free(w);
  { char path[4096]; FILE *file; make(&m,1,8,8,1,u8,3,0); snprintf(path,sizeof(path),"%s/wave-test.wav",argv[1]); file=fopen(path,"wb"); CHECK(file && fwrite(m.bytes,1,m.size,file)==m.size && !fclose(file)); OK(exr_wave_open(path,NULL,&w,&error)); OK(exr_wave_read(w,2,1,out,&n,NULL,&error)); NEAR(out[0],127.0/128); exr_wave_free(w); remove(path); }
  CHECK(!exr_wave_format(NULL)); exr_wave_free(NULL); printf("%u native WAVE checks passed\n",checks); return 0;
}
