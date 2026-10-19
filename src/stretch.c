/* SPDX-License-Identifier: MIT */
#include "internal.h"
#define STRETCH_Q UINT64_C(4294967296)
struct exr_stretch {
  uint32_t sample_rate,channels;
  uint64_t rate,input_frames,output_frames,generated,goal,base;
  size_t hop,search,capacity,head,count,pending_at,pending_count;
  float *storage,*input,*tail,*pending,*window;
  int initialized,finished,busy;
};
static exr_status stretch_rate(double rate,uint64_t *out,exr_error *e) {
  if(!isfinite(rate) || rate<0.5 || rate>2) return exr_fail(e,EXR_ARGUMENT,"Time-stretch rate must be between 0.5 and 2");
  *out=(uint64_t)floor(rate*(double)STRETCH_Q+0.5); return EXR_OK;
}
/* Exact round(n * 2^32 / denominator), without a nonstandard 128-bit integer. */
static int stretch_duration(uint64_t n,uint64_t denominator,uint64_t *out) {
  uint64_t whole=n/denominator,remainder=n%denominator,fraction=0,value; unsigned i;
  if(whole>UINT64_MAX/STRETCH_Q) return 0;
  for(i=0;i<32;i++) { remainder*=2; fraction<<=1; if(remainder>=denominator) { remainder-=denominator; fraction|=1; } }
  value=whole*STRETCH_Q+fraction;
  if(remainder>=(denominator+1)/2) { if(value==UINT64_MAX) return 0; value++; }
  *out=value; return 1;
}
/* Exact round(position * rate / 2^32), also on 32-bit C targets. */
static int stretch_position(uint64_t position,uint64_t rate,uint64_t *out) {
  uint64_t integer=rate>>32,fraction=rate&(STRETCH_Q-1),high=position>>32,low=position&(STRETCH_Q-1),small,whole;
  if(integer && position>UINT64_MAX/integer) return 0;
  whole=position*integer;
  small=high*fraction+((low*fraction+STRETCH_Q/2)>>32);
  if(small>UINT64_MAX-whole) return 0;
  *out=whole+small; return 1;
}
static float stretch_sample(const exr_stretch *s,uint64_t frame,uint32_t channel) {
  size_t offset;
  if(frame<s->base || frame>=s->input_frames) return 0;
  offset=(s->head+(size_t)(frame-s->base))%s->capacity;
  return s->input[offset*s->channels+channel];
}
static void stretch_discard(exr_stretch *s,uint64_t before) {
  size_t n;
  if(before<=s->base) return;
  n=before-s->base<s->count ? (size_t)(before-s->base) : s->count;
  s->base+=n; s->head=(s->head+n)%s->capacity; s->count-=n;
}
static double stretch_score(const exr_stretch *s,uint64_t candidate,uint32_t channel,size_t stride) {
  size_t i; double dot=0,reference=0,energy=0;
  for(i=0;i<s->hop;i+=stride) {
    double a=s->tail[i*s->channels+channel],b=stretch_sample(s,candidate+i,channel);
    dot+=a*b; reference+=a*a; energy+=b*b;
  }
  if(reference<1e-30 || energy<1e-30) return -2;
  return dot/sqrt(reference*energy);
}
static uint64_t stretch_distance(uint64_t a,uint64_t b) { return a>b ? a-b : b-a; }
static int stretch_better(double score,uint64_t candidate,double best_score,uint64_t best,uint64_t desired) {
  if(score>best_score+1e-12) return 1;
  return fabs(score-best_score)<=1e-12 && (stretch_distance(candidate,desired)<stretch_distance(best,desired) ||
    (stretch_distance(candidate,desired)==stretch_distance(best,desired) && candidate<best));
}
static exr_status stretch_generate(exr_stretch *s,const exr_control *control,exr_error *e) {
  uint64_t desired=0,low=0,high=0,chosen=0,next; size_t i,n=s->hop; uint32_t c;
  exr_status status;
  if(s->finished && s->generated>=s->goal) return EXR_OK;
  if(!s->initialized) { if(!s->finished && s->input_frames<s->hop*2) return EXR_OK; }
  else {
    double energy=0,best_score; uint32_t channel=0; size_t step=s->sample_rate/4000,coarse=s->hop/128,fine=s->hop/256,j=0;
    uint64_t candidate,stop;
    if(!stretch_position(s->generated,s->rate,&desired) || desired>UINT64_MAX-s->search-s->hop*2) return exr_fail(e,EXR_LIMIT,"Time-stretch analysis timeline overflows");
    low=desired>s->search ? desired-s->search : 0; high=desired+s->search;
    if(!s->finished && high+s->hop*2>s->input_frames) return EXR_OK;
    if(s->finished && high>=s->input_frames) high=s->input_frames ? s->input_frames-1 : 0;
    if(low>high) low=high;
    if(low<s->base) return exr_fail(e,EXR_FORMAT,"Time-stretch input history is unavailable");
    chosen=desired<low ? low : desired>high ? high : desired;
    for(c=0;c<s->channels;c++) {
      double total=0; for(i=0;i<s->hop;i++) { double sample=s->tail[i*s->channels+c]; total+=sample*sample; }
      if(total>energy) { energy=total; channel=c; }
    }
    if(energy>1e-30) {
      if(!step) step=1;
      if(!coarse) coarse=1;
      if(!fine) fine=1;
      best_score=stretch_score(s,chosen,channel,coarse);
      for(candidate=low;;) {
        double score=stretch_score(s,candidate,channel,coarse);
        if(stretch_better(score,candidate,best_score,chosen,desired)) { chosen=candidate; best_score=score; }
        if(!(j++&15)) { status=exr_control_poll(control,EXR_STAGE_READ,j,0,e); if(status!=EXR_OK) return status; }
        if(high-candidate<step) break;
        candidate+=step;
      }
      { double score=stretch_score(s,high,channel,coarse); if(stretch_better(score,high,best_score,chosen,desired)) chosen=high; }
      candidate=chosen>step ? chosen-step : 0; if(candidate<low) candidate=low;
      stop=chosen+step; if(stop>high) stop=high;
      best_score=stretch_score(s,chosen,channel,fine);
      for(;;) {
        double score=stretch_score(s,candidate,channel,fine);
        if(stretch_better(score,candidate,best_score,chosen,desired)) { chosen=candidate; best_score=score; }
        if(!(j++&15)) { status=exr_control_poll(control,EXR_STAGE_READ,j,0,e); if(status!=EXR_OK) return status; }
        if(candidate==stop) break;
        candidate++;
      }
    }
  }
  status=exr_control_cancel(control,e); if(status!=EXR_OK) return status;
  if(s->finished && s->goal-s->generated<n) n=(size_t)(s->goal-s->generated);
  if(s->generated>UINT64_MAX-n) return exr_fail(e,EXR_LIMIT,"Time-stretch output timeline overflows");
  for(i=0;i<s->hop;i++) for(c=0;c<s->channels;c++) {
    size_t at=i*s->channels+c; double current=stretch_sample(s,chosen+i,c);
    s->pending[at]=s->initialized ? (float)((double)s->tail[at]+(current-s->tail[at])*s->window[i]) : (float)current;
    s->tail[at]=stretch_sample(s,chosen+s->hop+i,c);
  }
  s->initialized=1; s->pending_at=0; s->pending_count=n; s->generated+=n;
  if(s->finished && s->generated==s->goal) stretch_discard(s,s->input_frames);
  else if(stretch_position(s->generated,s->rate,&next)) stretch_discard(s,next>s->search ? next-s->search : 0);
  return EXR_OK;
}
void exr_stretch_free(exr_stretch *s) { if(s) { free(s->storage); free(s); } }
exr_status exr_stretch_create(uint32_t sample_rate,uint32_t channels,double rate,exr_stretch **out,exr_error *e) {
  exr_stretch *s; uint64_t fixed=0; size_t samples,i; exr_status status;
  if(out) *out=NULL;
  if(!out || sample_rate<7350 || sample_rate>192000 || !channels || channels>8) return exr_fail(e,EXR_ARGUMENT,"Time-stretch requires 7350-192000 Hz and one to eight channels");
  status=stretch_rate(rate,&fixed,e); if(status!=EXR_OK) return status;
  s=calloc(1,sizeof(*s)); if(!s) return exr_fail(e,EXR_MEMORY,"Time-stretch allocation failed");
  s->sample_rate=sample_rate; s->channels=channels; s->rate=fixed; s->hop=(sample_rate+50)/100; s->search=(sample_rate+100)/200; s->capacity=s->hop*8+s->search*4;
  samples=(s->capacity+s->hop*2)*channels+s->hop; s->storage=calloc(samples,sizeof(*s->storage));
  if(!s->storage) { free(s); return exr_fail(e,EXR_MEMORY,"Time-stretch buffer allocation failed"); }
  s->input=s->storage; s->tail=s->input+s->capacity*channels; s->pending=s->tail+s->hop*channels; s->window=s->pending+s->hop*channels;
  for(i=0;i<s->hop;i++) s->window[i]=(float)(0.5-0.5*cos(3.14159265358979323846*((double)i+0.5)/s->hop));
  *out=s; return exr_fail(e,EXR_OK,"");
}
exr_status exr_stretch_push(exr_stretch *s,const float *input,size_t frames,size_t *accepted,const exr_control *control,exr_error *e) {
  size_t i,n; exr_status status;
  if(accepted) *accepted=0;
  if(!s || !accepted || (frames && !input) || s->finished || s->busy) return exr_fail(e,EXR_ARGUMENT,"Invalid, finished, or reentrant time-stretch input");
  if(frames>65536) return exr_fail(e,EXR_LIMIT,"Time-stretch input exceeds 65536 frames");
  for(i=0;i<frames*s->channels;i++) if(!isfinite(input[i])) return exr_fail(e,EXR_ARGUMENT,"Time-stretch input must be finite");
  n=s->capacity-s->count; if(n>frames) n=frames;
  if(n>UINT64_MAX-s->input_frames) return exr_fail(e,EXR_LIMIT,"Time-stretch input timeline overflows");
  s->busy=1; status=exr_control_poll(control,EXR_STAGE_READ,0,n,e);
  if(status==EXR_OK) {
    for(i=0;i<n;i++) { size_t frame=(s->head+s->count+i)%s->capacity; memcpy(s->input+frame*s->channels,input+i*s->channels,s->channels*sizeof(*input)); }
    s->count+=n; s->input_frames+=n; *accepted=n;
  }
  s->busy=0; return status==EXR_OK ? exr_fail(e,EXR_OK,"") : status;
}
exr_status exr_stretch_pull(exr_stretch *s,float *output,size_t frames,size_t *read,const exr_control *control,exr_error *e) {
  size_t n=0,i; exr_status status;
  if(read) *read=0;
  if(!s || !read || (frames && !output) || s->busy) return exr_fail(e,EXR_ARGUMENT,"Invalid or reentrant time-stretch output");
  if(frames>65536) return exr_fail(e,EXR_LIMIT,"Time-stretch output exceeds 65536 frames");
  if(frames) memset(output,0,frames*s->channels*sizeof(*output));
  s->busy=1; status=exr_control_cancel(control,e); if(status!=EXR_OK || !frames) goto finish;
  if(s->rate==STRETCH_Q) {
    n=s->count<frames ? s->count : frames;
    status=exr_control_poll(control,EXR_STAGE_READ,0,n,e); if(status!=EXR_OK) goto finish;
    for(i=0;i<n;i++) { size_t frame=(s->head+i)%s->capacity; memcpy(output+i*s->channels,s->input+frame*s->channels,s->channels*sizeof(*output)); }
    stretch_discard(s,s->base+n); s->generated+=n;
  } else {
    if(!s->pending_count) { status=stretch_generate(s,control,e); if(status!=EXR_OK) goto finish; }
    n=s->pending_count<frames ? s->pending_count : frames;
    status=exr_control_poll(control,EXR_STAGE_READ,n,n,e); if(status!=EXR_OK) goto finish;
    if(n) memcpy(output,s->pending+s->pending_at*s->channels,n*s->channels*sizeof(*output));
    s->pending_at+=n; s->pending_count-=n;
  }
  s->output_frames+=n; *read=n;
finish:
  s->busy=0;
  if(status!=EXR_OK) return status;
  return exr_fail(e,EXR_OK,"");
}
exr_status exr_stretch_finish(exr_stretch *s,exr_error *e) {
  uint64_t goal;
  if(!s || s->busy) return exr_fail(e,EXR_ARGUMENT,"Missing or reentrant time-stretch finish");
  if(s->finished) return exr_fail(e,EXR_OK,"");
  if(!stretch_duration(s->input_frames,s->rate,&goal)) return exr_fail(e,EXR_LIMIT,"Time-stretch final duration overflows");
  if(goal<s->generated) return exr_fail(e,EXR_FORMAT,"Time-stretch generated past final duration");
  s->goal=goal; s->finished=1; return exr_fail(e,EXR_OK,"");
}
exr_status exr_stretch_reset(exr_stretch *s,double rate,exr_error *e) {
  uint64_t fixed=0; exr_status status;
  if(!s || s->busy) return exr_fail(e,EXR_ARGUMENT,"Missing or reentrant time-stretch reset");
  status=stretch_rate(rate,&fixed,e); if(status!=EXR_OK) return status;
  s->rate=fixed; s->input_frames=s->output_frames=s->generated=s->goal=s->base=0;
  s->head=s->count=s->pending_at=s->pending_count=0; s->initialized=s->finished=0;
  memset(s->tail,0,s->hop*s->channels*sizeof(*s->tail)); return exr_fail(e,EXR_OK,"");
}
exr_status exr_stretch_get(const exr_stretch *s,exr_stretch_state *out,exr_error *e) {
  if(out) memset(out,0,sizeof(*out));
  if(!s || !out || s->busy) return exr_fail(e,EXR_ARGUMENT,"Missing or reentrant time-stretch snapshot");
  *out=(exr_stretch_state){s->sample_rate,s->channels,(double)s->rate/STRETCH_Q,s->input_frames,s->output_frames,s->count,s->pending_count,
    s->rate==STRETCH_Q ? 0 : s->hop*2+s->search,s->finished,s->finished && s->output_frames==s->goal};
  return exr_fail(e,EXR_OK,"");
}
