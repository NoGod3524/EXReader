/* SPDX-License-Identifier: MIT */
#include "exreader.h"
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static exr_error error; static unsigned checks;
#define CHECK(x) do { checks++; if(!(x)) { fprintf(stderr,"line %d: %s (%d: %s)\n",__LINE__,#x,error.code,error.message); exit(1); } } while(0)
#define OK(x) CHECK((x)==EXR_OK)
typedef struct { exr_pcm *pcm; unsigned released,mode,calls; } provider;
static void released(void *context) { ((provider *)context)->released++; }
static exr_status read_pcm(void *context,uint64_t first,size_t frames,float *out,size_t *read,const exr_control *control,exr_error *e) {
  provider *p=context; size_t i,n=first<4 ? (size_t)(4-first) : 0; size_t nested=123; exr_error local={0}; (void)control;
  if(n>frames) n=frames;
  p->calls++;
  CHECK(exr_pcm_read(p->pcm,0,0,NULL,&nested,NULL,&local)==EXR_ARGUMENT && !nested);
  for(i=0;i<n*2;i++) out[i]=(float)(first+1)/10;
  *read=n;
  if(p->mode==1) out[0]=NAN;
  if(p->mode==2) *read=frames+1;
  if(p->mode==3) { e->code=EXR_IO; strcpy(e->message,"host decoder unavailable"); }
  if(p->mode==4) *read=n ? n-1 : 0;
  return EXR_OK;
}
static int cancel(void *context) { return *(int *)context; }
static void finish(void *context,exr_stage stage,uint64_t done,uint64_t total) { (void)stage; if(done && done==total) *(int *)context=1; }
static void zeros(const float *out,size_t n) { size_t i; for(i=0;i<n;i++) CHECK(out[i]==0); }
static void custom(void) {
  exr_pcm_input input={0}; provider p={0}; float out[16]; size_t got,i; int stopped=0; exr_control control={cancel,finish,&stopped};
  struct { exr_pcm_input base; unsigned char extension[8]; } larger;
  input.struct_size=sizeof(input); input.info=(exr_pcm_info){48000,2,3,4}; input.read=read_pcm; input.context=&p; input.release=released;
  OK(exr_pcm_create(&input,&p.pcm,&error)); CHECK(exr_pcm_format(p.pcm)->sample_rate==48000 && !p.released);
  OK(exr_pcm_read(p.pcm,0,4,out,&got,NULL,&error)); CHECK(got==4 && out[0]==.1f && out[7]==.1f);
  memset(out,1,sizeof(out)); OK(exr_pcm_read(p.pcm,3,8,out,&got,NULL,&error)); CHECK(got==1 && out[0]==.4f); zeros(out+2,14);
  memset(out,1,sizeof(out)); OK(exr_pcm_read(p.pcm,4,8,out,&got,NULL,&error)); CHECK(!got); zeros(out,16);
  for(i=1;i<=4;i++) {
    p.mode=(unsigned)i; memset(out,1,sizeof(out)); got=123;
    CHECK(exr_pcm_read(p.pcm,0,4,out,&got,NULL,&error)==(i==3 ? EXR_IO : EXR_FORMAT) && !got);
    if(i==3) CHECK(!strcmp(error.message,"host decoder unavailable"));
    zeros(out,8);
  }
  p.mode=0; memset(out,1,sizeof(out)); got=123;
  CHECK(exr_pcm_read(p.pcm,0,4,out,&got,&control,&error)==EXR_CANCELLED && !got); zeros(out,8);
  stopped=0; OK(exr_pcm_read(p.pcm,0,4,out,&got,NULL,&error)); CHECK(got==4);
  CHECK(exr_pcm_read(p.pcm,0,65537,out,&got,NULL,&error)==EXR_LIMIT && !got);
  CHECK(exr_pcm_read(p.pcm,5,1,out,&got,NULL,&error)==EXR_ARGUMENT && !got);
  CHECK(exr_pcm_read(p.pcm,UINT64_MAX,1,out,&got,NULL,&error)==EXR_ARGUMENT && !got);
  exr_pcm_free(p.pcm); CHECK(p.released==1); p.pcm=NULL;
  input.info.frames=UINT64_MAX; OK(exr_pcm_create(&input,&p.pcm,&error));
  OK(exr_pcm_read(p.pcm,2,4,out,&got,NULL,&error)); CHECK(got==2 && exr_pcm_format(p.pcm)->frames==UINT64_MAX);
  exr_pcm_free(p.pcm); CHECK(p.released==2); p.pcm=NULL;
  memset(&larger,0,sizeof(larger)); larger.base=input; larger.base.struct_size=sizeof(larger); larger.extension[7]=1;
  CHECK(exr_pcm_create(&larger.base,&p.pcm,&error)==EXR_ARGUMENT && !p.pcm); larger.extension[7]=0;
  OK(exr_pcm_create(&larger.base,&p.pcm,&error)); exr_pcm_free(p.pcm); CHECK(p.released==3); p.pcm=NULL;
  input.info.channels=33; CHECK(exr_pcm_create(&input,&p.pcm,&error)==EXR_ARGUMENT && !p.pcm); input.info.channels=2;
  input.info.channel_mask=1; CHECK(exr_pcm_create(&input,&p.pcm,&error)==EXR_ARGUMENT && !p.pcm);
  input.info.channel_mask=3; input.info.sample_rate=0; CHECK(exr_pcm_create(&input,&p.pcm,&error)==EXR_ARGUMENT && !p.pcm);
  CHECK(!exr_pcm_format(NULL)); exr_pcm_free(NULL);
}
typedef struct { const unsigned char *bytes; size_t size,reads,releases; int fail; } byte_source;
static size_t read_at(void *context,uint64_t at,void *out,size_t n) {
  byte_source *s=context; s->reads++; if(s->fail || at>s->size) return 0;
  if(n>s->size-(size_t)at) n=s->size-(size_t)at;
  if(n>3) n=3;
  memcpy(out,s->bytes+(size_t)at,n); return n;
}
static void close_source(void *context) { ((byte_source *)context)->releases++; }
static void native(const char *directory) {
  char path[4096]; unsigned char *bytes; FILE *file; long length; exr_pcm *pcm=NULL; exr_wave *wave=NULL;
  byte_source memory={0}; exr_source source={0}; float actual[128],expected[128]; size_t got,n; int stopped=0; exr_control control={cancel,NULL,&stopped};
  snprintf(path,sizeof(path),"%s/pcm.wav",directory); file=fopen(path,"rb"); CHECK(file); CHECK(!fseek(file,0,SEEK_END)); length=ftell(file); CHECK(length>12); rewind(file);
  bytes=malloc((size_t)length); CHECK(bytes && fread(bytes,1,(size_t)length,file)==(size_t)length); fclose(file);
  memory.bytes=bytes; memory.size=(size_t)length;
  source=(exr_source){(uint64_t)length,read_at,close_source,&memory,control};
  OK(exr_pcm_open_source(&source,&pcm,&error)); CHECK(!memory.releases && memory.reads>1 && exr_pcm_format(pcm)->channels==1);
  stopped=1; /* Open-time control must not be retained. */
  OK(exr_pcm_read(pcm,0,128,actual,&got,NULL,&error)); CHECK(got==128);
  OK(exr_wave_open(path,NULL,&wave,&error)); OK(exr_wave_read(wave,0,128,expected,&n,NULL,&error)); CHECK(n==got && !memcmp(actual,expected,n*sizeof(*actual)));
  exr_wave_free(wave); exr_pcm_free(pcm); CHECK(memory.releases==1); pcm=NULL;
  CHECK(exr_pcm_open_source(&source,&pcm,&error)==EXR_CANCELLED && !pcm && memory.releases==1); stopped=0;
  memory.fail=1; CHECK(exr_pcm_open_source(&source,&pcm,&error)==EXR_IO && !pcm && memory.releases==1); memory.fail=0;
  source.size=3; CHECK(exr_pcm_open_source(&source,&pcm,&error)==EXR_ARGUMENT && !pcm && memory.releases==1); source.size=memory.size;
  memory.bytes=(const unsigned char *)"no codec"; memory.size=8; source.size=8;
  CHECK(exr_pcm_open_source(&source,&pcm,&error)==EXR_FORMAT && !pcm && memory.releases==1);
  OK(exr_pcm_open(path,NULL,&pcm,&error)); CHECK(exr_pcm_format(pcm)->frames==3200); exr_pcm_free(pcm); free(bytes);
}
int main(int argc,char **argv) { CHECK(argc==2); custom(); native(argv[1]); printf("PCM providers passed (%u checks)\n",checks); return 0; }
