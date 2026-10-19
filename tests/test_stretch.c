/* SPDX-License-Identifier: MIT */
#include "exreader.h"
#include <float.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static exr_error error; static unsigned checks;
#define CHECK(x) do { checks++; if(!(x)) { fprintf(stderr,"line %d: %s (%d: %s)\n",__LINE__,#x,error.code,error.message); exit(1); } } while(0)
#define OK(x) CHECK((x)==EXR_OK)
static uint32_t random_state=14517;
static uint32_t random_number(void) { random_state=random_state*1664525u+1013904223u; return random_state; }
typedef struct { float *data; size_t count; } rendered;
static rendered render(const float *input,size_t frames,uint32_t rate,uint32_t channels,double speed,unsigned split,size_t pull_size) {
  exr_stretch *s=NULL; exr_stretch_state state; rendered result={0}; float *out; size_t at=0,expected,iterations=0;
  OK(exr_stretch_create(rate,channels,speed,&s,&error)); OK(exr_stretch_get(s,&state,&error));
  expected=(size_t)floor((double)frames/state.rate+0.5); result.data=malloc((expected+1)*channels*sizeof(*result.data)); out=malloc(pull_size*channels*sizeof(*out)); CHECK(result.data && out);
  while(at<frames) {
    size_t accepted=0,n=split==1 ? 1 : split==2 ? 137 : split==3 ? random_number()%2048+1 : 65536,pulled=0;
    if(n>frames-at) n=frames-at;
    OK(exr_stretch_push(s,input+at*channels,n,&accepted,NULL,&error)); CHECK(accepted<=n); at+=accepted;
    for(;;) {
      size_t got; OK(exr_stretch_pull(s,out,pull_size,&got,NULL,&error)); CHECK(got<=pull_size && got<=expected-result.count);
      if(!got) break;
      memcpy(result.data+result.count*channels,out,got*channels*sizeof(*out)); result.count+=got; pulled+=got;
    }
    CHECK(accepted || pulled); CHECK(++iterations<=frames+1000);
  }
  OK(exr_stretch_finish(s,&error)); OK(exr_stretch_finish(s,&error));
  for(;;) {
    size_t got; OK(exr_stretch_pull(s,out,pull_size,&got,NULL,&error)); CHECK(got<=pull_size && got<=expected-result.count);
    if(!got) break;
    memcpy(result.data+result.count*channels,out,got*channels*sizeof(*out)); result.count+=got;
  }
  CHECK(result.count==expected); OK(exr_stretch_get(s,&state,&error)); CHECK(state.finished && state.drained && state.input_frames==frames && state.output_frames==expected && !state.output_buffered);
  exr_stretch_free(s); free(out); return result;
}
static double frequency(const float *data,size_t count,unsigned channels,unsigned sample_rate) {
  size_t i,begin=sample_rate/10,end=count-sample_rate/10; double first=0,last=0; unsigned crossings=0;
  CHECK(count>sample_rate/3);
  for(i=begin+1;i<end;i++) {
    double a=data[(i-1)*channels],b=data[i*channels];
    if(a<=0 && b>0) { double t=(double)(i-1)+a/(a-b); if(!crossings) first=t; last=t; crossings++; }
  }
  CHECK(crossings>20); return (crossings-1)*sample_rate/(last-first);
}
typedef struct { int stop,reenter; unsigned polls; exr_stretch *stretch; } cancellation;
static int cancelled(void *context) { return ((cancellation *)context)->stop; }
static void progress(void *context,exr_stage stage,uint64_t completed,uint64_t total) {
  cancellation *c=context; (void)stage; (void)total; c->polls++;
  if(c->reenter) {
    float out[8]={0}; size_t n; exr_stretch_state state;
    CHECK(exr_stretch_push(c->stretch,out,1,&n,NULL,&error)==EXR_ARGUMENT && !n);
    CHECK(exr_stretch_pull(c->stretch,out,1,&n,NULL,&error)==EXR_ARGUMENT && !n);
    CHECK(exr_stretch_get(c->stretch,&state,&error)==EXR_ARGUMENT && !state.input_frames);
    CHECK(exr_stretch_finish(c->stretch,&error)==EXR_ARGUMENT); CHECK(exr_stretch_reset(c->stretch,1,&error)==EXR_ARGUMENT);
  }
  if(completed) c->stop=1;
}
int main(void) {
  const unsigned sample_rate=48000,channels=2; const size_t frames=96017; float *input=malloc(frames*channels*sizeof(*input)); size_t i,j; unsigned k;
  static const double speeds[5]={0.5,0.75,1,1.5,2};
  CHECK(input);
  for(i=0;i<frames;i++) { input[i*2]=(float)(0.5*sin(2*3.14159265358979323846*440*i/sample_rate)); input[i*2+1]=-input[i*2]; }
  for(k=0;k<5;k++) {
    rendered base=render(input,frames,sample_rate,channels,speeds[k],0,4096); double hz=frequency(base.data,base.count,channels,sample_rate);
    CHECK(fabs(hz-440)<4.4);
    for(i=0;i<base.count;i++) { CHECK(isfinite(base.data[i*2]) && fabs((double)base.data[i*2]+base.data[i*2+1])<1e-7); }
    if(speeds[k]==1) CHECK(base.count==frames && !memcmp(base.data,input,frames*channels*sizeof(*input)));
    for(j=1;j<4;j++) {
      rendered split=render(input,frames,sample_rate,channels,speeds[k],(unsigned)j,j==1 ? 97 : j==2 ? 1 : 777);
      CHECK(split.count==base.count && !memcmp(split.data,base.data,base.count*channels*sizeof(*input))); free(split.data);
    }
    printf("rate=%.2f frames=%zu pitch=%.3fHz\n",speeds[k],base.count,hz); free(base.data);
  }
  { rendered a,b; double hz;
    for(i=0;i<frames;i++) { input[i*2]=(float)(0.5*sin(2*3.14159265358979323846*220*i/sample_rate)); input[i*2+1]=-input[i*2]; }
    a=render(input,frames,sample_rate,channels,1.333333333,0,4096); b=render(input,frames,sample_rate,channels,1.333333333,3,97);
    hz=frequency(a.data,a.count,channels,sample_rate); CHECK(fabs(hz-220)<2.2); CHECK(a.count==b.count && !memcmp(a.data,b.data,a.count*channels*sizeof(*a.data)));
    printf("rate=1.333333333 frames=%zu pitch=%.3fHz\n",a.count,hz); free(a.data); free(b.data);
    for(k=0;k<2;k++) { double speed=k ? 1.99999999 : 0.50000001; a=render(input,10017,sample_rate,channels,speed,0,4096); b=render(input,10017,sample_rate,channels,speed,3,97); CHECK(a.count==b.count && !memcmp(a.data,b.data,a.count*channels*sizeof(*a.data))); free(a.data); free(b.data); }
  }
  /* Short boundaries and all supported channel counts preserve duration and
     deterministic output under one-frame pushes and differently sized pulls. */
  { static const size_t counts[8]={0,1,37,479,480,481,959,1017}; unsigned ch;
    for(ch=1;ch<=8;ch++) for(k=0;k<8;k++) {
      float short_input[1017*8]; rendered a,b; double speed=k&1 ? 0.5 : 2;
      for(i=0;i<counts[k]*ch;i++) short_input[i]=(float)sin((double)i/7)*0.1f;
      a=render(short_input,counts[k],7350,ch,speed,0,311); b=render(short_input,counts[k],7350,ch,speed,1,1);
      CHECK(a.count==b.count && !memcmp(a.data,b.data,a.count*ch*sizeof(*a.data))); free(a.data); free(b.data);
    }
  }
  { exr_stretch *s=NULL; exr_stretch_state state; cancellation c={0}; exr_control control={0}; float out[2000]; size_t n,accepted;
    OK(exr_stretch_create(sample_rate,channels,1.25,&s,&error)); c.stretch=s; c.reenter=1; control.context=&c; control.cancelled=cancelled; control.progress=progress;
    c.stop=1; CHECK(exr_stretch_push(s,input,100,&accepted,&control,&error)==EXR_CANCELLED && !accepted); c.stop=0;
    OK(exr_stretch_push(s,input,65536,&accepted,&control,&error)); CHECK(accepted>0 && accepted<65536); OK(exr_stretch_get(s,&state,&error)); CHECK(state.input_frames==accepted);
    OK(exr_stretch_push(s,input+accepted*2,1,&n,NULL,&error)); CHECK(!n);
    CHECK(exr_stretch_pull(s,out,1000,&n,&control,&error)==EXR_CANCELLED && !n); for(i=0;i<2000;i++) CHECK(!out[i]);
    OK(exr_stretch_get(s,&state,&error)); CHECK(!state.output_frames && state.output_buffered>0);
    c.stop=0; c.reenter=0; OK(exr_stretch_pull(s,out,480,&n,NULL,&error)); CHECK(n==480 && !memcmp(out,input,480*2*sizeof(*out)));
    c.polls=0; CHECK(exr_stretch_pull(s,out,480,&n,&control,&error)==EXR_CANCELLED && !n); c.stop=0;
    OK(exr_stretch_pull(s,out,480,&n,NULL,&error)); CHECK(n==480);
    OK(exr_stretch_reset(s,1,&error)); OK(exr_stretch_get(s,&state,&error)); CHECK(!state.input_frames && !state.output_frames && !state.finished && state.rate==1 && !state.latency_frames);
    { float invalid[2]={0,NAN}; CHECK(exr_stretch_push(s,invalid,1,&n,NULL,&error)==EXR_ARGUMENT && !n); }
    CHECK(exr_stretch_push(s,input,65537,&n,NULL,&error)==EXR_LIMIT && !n); CHECK(exr_stretch_pull(s,out,65537,&n,NULL,&error)==EXR_LIMIT && !n);
    CHECK(exr_stretch_reset(s,NAN,&error)==EXR_ARGUMENT); OK(exr_stretch_finish(s,&error)); CHECK(exr_stretch_push(s,input,1,&n,NULL,&error)==EXR_ARGUMENT && !n);
    exr_stretch_free(s);
  }
  { exr_stretch *s=NULL; CHECK(exr_stretch_create(7349,2,1,&s,&error)==EXR_ARGUMENT && !s); CHECK(exr_stretch_create(192001,2,1,&s,&error)==EXR_ARGUMENT && !s);
    CHECK(exr_stretch_create(48000,0,1,&s,&error)==EXR_ARGUMENT && !s); CHECK(exr_stretch_create(48000,9,1,&s,&error)==EXR_ARGUMENT && !s);
    CHECK(exr_stretch_create(48000,2,0.49,&s,&error)==EXR_ARGUMENT && !s); CHECK(exr_stretch_create(48000,2,2.01,&s,&error)==EXR_ARGUMENT && !s); CHECK(exr_stretch_create(48000,2,INFINITY,&s,&error)==EXR_ARGUMENT && !s);
    OK(exr_stretch_create(192000,8,1,&s,&error)); OK(exr_stretch_finish(s,&error)); exr_stretch_free(s);
  }
  { float extreme[4096]; rendered r; for(i=0;i<4096;i++) extreme[i]=(i&1) ? FLT_MAX : -FLT_MAX;
    r=render(extreme,2048,48000,2,0.75,3,97); for(i=0;i<r.count*2;i++) CHECK(isfinite(r.data[i])); free(r.data);
  }
  exr_stretch_free(NULL); free(input); printf("%u pitch-preserving time-stretch checks passed\n",checks); return 0;
}
