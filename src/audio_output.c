/* SPDX-License-Identifier: GPL-3.0-only */
#include "internal.h"
#include <errno.h>
#if defined(_WIN32)
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <mmsystem.h>
#elif defined(__APPLE__)
#include <stdatomic.h>
#include <AudioToolbox/AudioToolbox.h>
#elif defined(__ANDROID__)
#include <SLES/OpenSLES.h>
#include <SLES/OpenSLES_Android.h>
#elif defined(__linux__)
#include <dlfcn.h>
#endif

#define OUTPUT_BLOCK 4096u
#define OUTPUT_SLOTS 4u
typedef struct {
  size_t frames;
#if defined(_WIN32)
  WAVEHDR header; int prepared; int16_t samples[OUTPUT_BLOCK*2];
#elif defined(__APPLE__)
  AudioQueueBufferRef buffer; atomic_uint queued;
#elif defined(__ANDROID__)
  int16_t samples[OUTPUT_BLOCK*2];
#endif
} output_slot;
#if defined(__linux__) && !defined(__ANDROID__)
typedef struct _snd_pcm snd_pcm_t;
typedef long pcm_sframes;
typedef unsigned long pcm_uframes;
#endif
struct exr_audio_output {
  uint32_t rate,channels; int paused;
#if defined(_WIN32)
  HWAVEOUT device; output_slot slots[OUTPUT_SLOTS];
#elif defined(__APPLE__)
  AudioQueueRef device; output_slot slots[OUTPUT_SLOTS]; int started;
#elif defined(__ANDROID__)
  SLObjectItf engine,mix,player; SLEngineItf engine_api; SLPlayItf play;
  SLAndroidSimpleBufferQueueItf queue; output_slot slots[OUTPUT_SLOTS]; size_t head,tail,count;
#elif defined(__linux__)
  void *library; snd_pcm_t *device; int native_paused; int16_t samples[OUTPUT_BLOCK*2];
  int (*open)(snd_pcm_t **,const char *,int,int);
  int (*close)(snd_pcm_t *);
  int (*set_params)(snd_pcm_t *,int,int,unsigned,unsigned,int,unsigned);
  pcm_sframes (*writei)(snd_pcm_t *,const void *,pcm_uframes);
  int (*delay)(snd_pcm_t *,pcm_sframes *);
  int (*pause)(snd_pcm_t *,int);
  int (*drop)(snd_pcm_t *);
  int (*prepare)(snd_pcm_t *);
  int (*state)(snd_pcm_t *);
  int (*start)(snd_pcm_t *);
#endif
};
const char *exr_audio_output_backend(void) {
#if defined(_WIN32)
  return "waveOut";
#elif defined(__APPLE__)
  return "AudioQueue";
#elif defined(__ANDROID__)
  return "OpenSL ES";
#elif defined(__linux__)
  return "ALSA";
#else
  return NULL;
#endif
}
static exr_status output_error(exr_error *e,const char *operation,long code) {
  return exr_fail(e,EXR_IO,"Native audio %s failed (%ld)",operation,code);
}
static void pcm16(int16_t *out,const float *input,size_t count) {
  size_t i; for(i=0;i<count;i++) {
    double value=input[i];
    out[i]=value<=-1 ? INT16_MIN : value>=1 ? INT16_MAX : (int16_t)lrint(value*(value<0 ? 32768 : 32767));
  }
}
#if defined(__APPLE__)
static void returned_buffer(void *context,AudioQueueRef queue,AudioQueueBufferRef buffer) {
  output_slot *slot=buffer->mUserData; (void)context; (void)queue;
  atomic_store_explicit(&slot->queued,0,memory_order_release);
}
#elif defined(__linux__) && !defined(__ANDROID__)
static int alsa_symbols(exr_audio_output *a) {
#define PCM_SYMBOL(member,name) do { void *symbol=dlsym(a->library,name); if(!symbol || sizeof(symbol)!=sizeof(a->member)) return 0; memcpy(&a->member,&symbol,sizeof(symbol)); } while(0)
  PCM_SYMBOL(open,"snd_pcm_open"); PCM_SYMBOL(close,"snd_pcm_close"); PCM_SYMBOL(set_params,"snd_pcm_set_params");
  PCM_SYMBOL(writei,"snd_pcm_writei"); PCM_SYMBOL(delay,"snd_pcm_delay"); PCM_SYMBOL(pause,"snd_pcm_pause");
  PCM_SYMBOL(drop,"snd_pcm_drop"); PCM_SYMBOL(prepare,"snd_pcm_prepare");
  PCM_SYMBOL(state,"snd_pcm_state"); PCM_SYMBOL(start,"snd_pcm_start");
#undef PCM_SYMBOL
  return 1;
}
#endif
void exr_audio_output_free(exr_audio_output *a) {
  if(!a) return;
#if defined(_WIN32)
  if(a->device) {
    unsigned i;
    /* A broken driver must not retain pointers into freed sample storage. */
    if(waveOutReset(a->device)!=MMSYSERR_NOERROR) return;
    for(i=0;i<OUTPUT_SLOTS;i++) if(a->slots[i].prepared && waveOutUnprepareHeader(a->device,&a->slots[i].header,sizeof(WAVEHDR))!=MMSYSERR_NOERROR) return;
    if(waveOutClose(a->device)!=MMSYSERR_NOERROR) return;
  }
#elif defined(__APPLE__)
  /* Immediate disposal synchronizes the native callbacks before their slots
     and mUserData storage are released. No user worker thread is created. */
  if(a->device && AudioQueueDispose(a->device,1)!=noErr) return;
#elif defined(__ANDROID__)
  /* Polling GetState avoids callback ownership and teardown races. */
  if(a->player) (*a->player)->Destroy(a->player);
  if(a->mix) (*a->mix)->Destroy(a->mix);
  if(a->engine) (*a->engine)->Destroy(a->engine);
#elif defined(__linux__)
  if(a->device && a->close) { a->drop(a->device); a->close(a->device); }
  if(a->library) dlclose(a->library);
#endif
  free(a);
}
exr_status exr_audio_output_open(uint32_t rate,uint32_t channels,exr_audio_output **out,exr_error *e) {
  exr_audio_output *a; long code=0; exr_status status=EXR_OK;
  if(out) *out=NULL;
  if(!out || rate<8000 || rate>192000 || (channels!=1 && channels!=2))
    return exr_fail(e,EXR_ARGUMENT,"Native audio requires 8000-192000 Hz and one or two channels");
  if(!exr_audio_output_backend()) return exr_fail(e,EXR_FORMAT,"No native audio output backend for this target");
  a=calloc(1,sizeof(*a)); if(!a) return exr_fail(e,EXR_MEMORY,"Native audio output allocation failed");
  a->rate=rate; a->channels=channels;
#if defined(_WIN32)
  {
    WAVEFORMATEX format={0}; unsigned i;
    format.wFormatTag=WAVE_FORMAT_PCM; format.nChannels=(WORD)channels; format.nSamplesPerSec=rate; format.wBitsPerSample=16;
    format.nBlockAlign=(WORD)(channels*2); format.nAvgBytesPerSec=rate*channels*2;
    code=waveOutOpen(&a->device,WAVE_MAPPER,&format,0,0,CALLBACK_NULL);
    for(i=0;!code && i<OUTPUT_SLOTS;i++) {
      WAVEHDR *header=&a->slots[i].header; header->lpData=(LPSTR)a->slots[i].samples; header->dwBufferLength=OUTPUT_BLOCK*channels*2;
      code=waveOutPrepareHeader(a->device,header,sizeof(*header)); if(!code) a->slots[i].prepared=1;
    }
  }
#elif defined(__APPLE__)
  {
    AudioStreamBasicDescription format={0}; unsigned i;
    format.mSampleRate=rate; format.mFormatID=kAudioFormatLinearPCM;
    format.mFormatFlags=kLinearPCMFormatFlagIsSignedInteger|kAudioFormatFlagsNativeEndian|kAudioFormatFlagIsPacked;
    format.mFramesPerPacket=1; format.mChannelsPerFrame=channels; format.mBitsPerChannel=16;
    format.mBytesPerFrame=format.mBytesPerPacket=channels*2;
    code=AudioQueueNewOutput(&format,returned_buffer,a,NULL,NULL,0,&a->device);
    for(i=0;!code && i<OUTPUT_SLOTS;i++) {
      atomic_init(&a->slots[i].queued,0);
      code=AudioQueueAllocateBuffer(a->device,OUTPUT_BLOCK*channels*2,&a->slots[i].buffer);
      if(!code) a->slots[i].buffer->mUserData=&a->slots[i];
    }
  }
#elif defined(__ANDROID__)
  {
    SLDataLocator_AndroidSimpleBufferQueue locator={SL_DATALOCATOR_ANDROIDSIMPLEBUFFERQUEUE,OUTPUT_SLOTS};
    SLDataFormat_PCM format={SL_DATAFORMAT_PCM,channels,rate*1000,SL_PCMSAMPLEFORMAT_FIXED_16,SL_PCMSAMPLEFORMAT_FIXED_16,
      channels==1 ? SL_SPEAKER_FRONT_CENTER : SL_SPEAKER_FRONT_LEFT|SL_SPEAKER_FRONT_RIGHT,SL_BYTEORDER_LITTLEENDIAN};
    SLDataSource source={&locator,&format}; SLDataLocator_OutputMix mix={SL_DATALOCATOR_OUTPUTMIX,NULL}; SLDataSink sink={&mix,NULL};
    const SLInterfaceID interfaces[]={SL_IID_ANDROIDSIMPLEBUFFERQUEUE}; const SLboolean required[]={SL_BOOLEAN_TRUE};
    code=slCreateEngine(&a->engine,0,NULL,0,NULL,NULL);
    if(!code) code=(*a->engine)->Realize(a->engine,SL_BOOLEAN_FALSE);
    if(!code) code=(*a->engine)->GetInterface(a->engine,SL_IID_ENGINE,&a->engine_api);
    if(!code) code=(*a->engine_api)->CreateOutputMix(a->engine_api,&a->mix,0,NULL,NULL);
    if(!code) code=(*a->mix)->Realize(a->mix,SL_BOOLEAN_FALSE);
    mix.outputMix=a->mix;
    if(!code) code=(*a->engine_api)->CreateAudioPlayer(a->engine_api,&a->player,&source,&sink,1,interfaces,required);
    if(!code) code=(*a->player)->Realize(a->player,SL_BOOLEAN_FALSE);
    if(!code) code=(*a->player)->GetInterface(a->player,SL_IID_PLAY,&a->play);
    if(!code) code=(*a->player)->GetInterface(a->player,SL_IID_ANDROIDSIMPLEBUFFERQUEUE,&a->queue);
    if(!code) code=(*a->play)->SetPlayState(a->play,SL_PLAYSTATE_PLAYING);
  }
#elif defined(__linux__)
  a->library=dlopen("libasound.so.2",RTLD_LOCAL|RTLD_NOW);
  if(!a->library || !alsa_symbols(a)) status=exr_fail(e,EXR_IO,"ALSA runtime is unavailable");
  if(status==EXR_OK) {
    unsigned latency=(unsigned)((uint64_t)OUTPUT_BLOCK*OUTPUT_SLOTS*1000000/rate); int format=2;
#if defined(__BYTE_ORDER__) && __BYTE_ORDER__==__ORDER_BIG_ENDIAN__
    format=3;
#endif
    code=a->open(&a->device,"default",0,1);
    if(!code) code=a->set_params(a->device,format,3,channels,rate,1,latency);
  }
#endif
  if(code && status==EXR_OK) status=output_error(e,"open",code);
  if(status!=EXR_OK) { exr_audio_output_free(a); return status; }
  *out=a; return exr_fail(e,EXR_OK,"");
}
#if defined(__ANDROID__)
static exr_status reap(exr_audio_output *a,exr_error *e) {
  SLAndroidSimpleBufferQueueState state; SLresult code=(*a->queue)->GetState(a->queue,&state);
  if(code) return output_error(e,"queue state",code);
  if(state.count>a->count) return exr_fail(e,EXR_IO,"Native audio queue ownership is inconsistent");
  while(a->count>state.count) { a->slots[a->head].frames=0; a->head=(a->head+1)%OUTPUT_SLOTS; a->count--; }
  return EXR_OK;
}
#endif
exr_status exr_audio_output_pending(exr_audio_output *a,size_t *frames,exr_error *e) {
  if(frames) *frames=0;
  if(!a || !frames) return exr_fail(e,EXR_ARGUMENT,"Missing native audio output or pending frames");
#if defined(_WIN32)
  {
    unsigned i; for(i=0;i<OUTPUT_SLOTS;i++) {
      if(a->slots[i].frames && (a->slots[i].header.dwFlags&WHDR_DONE)) a->slots[i].frames=0;
      *frames+=a->slots[i].frames;
    }
  }
#elif defined(__APPLE__)
  { unsigned i; for(i=0;i<OUTPUT_SLOTS;i++) if(atomic_load_explicit(&a->slots[i].queued,memory_order_acquire)) *frames+=a->slots[i].frames; }
#elif defined(__ANDROID__)
  { unsigned i; exr_status status=reap(a,e); if(status!=EXR_OK) return status; for(i=0;i<OUTPUT_SLOTS;i++) *frames+=a->slots[i].frames; }
#elif defined(__linux__)
  { pcm_sframes delay=0; int code=a->delay(a->device,&delay); if(code==-EPIPE) return exr_fail(e,EXR_OK,""); if(code<0) return output_error(e,"delay",code); if(delay>0) *frames=(size_t)delay; }
#endif
  return exr_fail(e,EXR_OK,"");
}
exr_status exr_audio_output_write(exr_audio_output *a,const float *input,size_t frames,size_t *written,exr_error *e) {
  size_t i,accepted=0; long code=0;
  if(written) *written=0;
  if(!a || !written || (!input && frames)) return exr_fail(e,EXR_ARGUMENT,"Missing native audio input or written frames");
  if(frames>65536) return exr_fail(e,EXR_LIMIT,"Native audio write exceeds 65536 frames");
  for(i=0;i<frames*a->channels;i++) if(!isfinite(input[i])) return exr_fail(e,EXR_ARGUMENT,"Native audio samples must be finite");
  if(a->paused || !frames) return exr_fail(e,EXR_OK,"");
#if defined(_WIN32) || defined(__APPLE__) || defined(__ANDROID__)
  {
    size_t pending=0; exr_status status=exr_audio_output_pending(a,&pending,e); if(status!=EXR_OK) return status;
    for(i=0;i<OUTPUT_SLOTS && accepted<frames;i++) {
      output_slot *slot; size_t count=frames-accepted; int16_t *samples;
      if(count>OUTPUT_BLOCK) count=OUTPUT_BLOCK;
#if defined(__ANDROID__)
      if(a->count==OUTPUT_SLOTS) break;
      slot=&a->slots[a->tail]; samples=slot->samples;
#else
      slot=&a->slots[i];
#if defined(_WIN32)
      if(slot->frames) continue;
      samples=slot->samples;
#else
      if(atomic_load_explicit(&slot->queued,memory_order_acquire)) continue;
      samples=slot->buffer->mAudioData;
#endif
#endif
      pcm16(samples,input+accepted*a->channels,count*a->channels); slot->frames=count;
#if defined(_WIN32)
      slot->header.dwBufferLength=(DWORD)(count*a->channels*2); code=waveOutWrite(a->device,&slot->header,sizeof(slot->header));
#elif defined(__APPLE__)
      slot->buffer->mAudioDataByteSize=(UInt32)(count*a->channels*2);
      atomic_store_explicit(&slot->queued,1,memory_order_release);
      code=AudioQueueEnqueueBuffer(a->device,slot->buffer,0,NULL);
#elif defined(__ANDROID__)
      code=(*a->queue)->Enqueue(a->queue,samples,(SLuint32)(count*a->channels*2));
#endif
      if(code) {
        slot->frames=0;
#if defined(__APPLE__)
        atomic_store_explicit(&slot->queued,0,memory_order_release);
#endif
        break;
      }
      accepted+=count;
#if defined(__ANDROID__)
      a->tail=(a->tail+1)%OUTPUT_SLOTS; a->count++;
#endif
    }
#if defined(__APPLE__)
    if(accepted && !code && !a->started) { code=AudioQueueStart(a->device,NULL); if(!code) a->started=1; }
#endif
  }
#elif defined(__linux__)
  while(accepted<frames) {
    size_t count=frames-accepted; pcm_sframes result;
    if(count>OUTPUT_BLOCK) count=OUTPUT_BLOCK;
    pcm16(a->samples,input+accepted*a->channels,count*a->channels); result=a->writei(a->device,a->samples,(pcm_uframes)count);
    if(result==-EPIPE) { code=a->prepare(a->device); if(code<0) break; result=a->writei(a->device,a->samples,(pcm_uframes)count); }
    if(result==-EAGAIN || result==0) break;
    if(result<0) { code=result; break; }
    if((size_t)result>count) { code=-EIO; break; }
    accepted+=(size_t)result;
  }
  /* set_params may otherwise wait for an almost-full device buffer. A short
     final write must start too, including immediately after underrun recovery. */
  if(accepted && !code && a->state(a->device)==2) code=a->start(a->device);
#endif
  *written=accepted; return code ? output_error(e,"write",code) : exr_fail(e,EXR_OK,"");
}
exr_status exr_audio_output_pause(exr_audio_output *a,int paused,exr_error *e) {
  long code=0; paused=paused!=0;
  if(!a) return exr_fail(e,EXR_ARGUMENT,"Missing native audio output");
  if(a->paused==paused) return exr_fail(e,EXR_OK,"");
#if defined(_WIN32)
  code=paused ? waveOutPause(a->device) : waveOutRestart(a->device);
#elif defined(__APPLE__)
  if(a->started) code=paused ? AudioQueuePause(a->device) : AudioQueueStart(a->device,NULL);
#elif defined(__ANDROID__)
  code=(*a->play)->SetPlayState(a->play,paused ? SL_PLAYSTATE_PAUSED : SL_PLAYSTATE_PLAYING);
#elif defined(__linux__)
  if(paused) {
    size_t frames=0; exr_status status=exr_audio_output_pending(a,&frames,e); if(status!=EXR_OK) return status;
    if(frames) {
      code=a->pause(a->device,1);
      if(code<0) return exr_fail(e,EXR_FORMAT,"ALSA device does not support preserving the queued audio on pause (%ld)",code);
      a->native_paused=1;
    }
  } else if(a->native_paused) { code=a->pause(a->device,0); if(!code) a->native_paused=0; }
#endif
  if(code) return output_error(e,"pause",code);
  a->paused=paused; return exr_fail(e,EXR_OK,"");
}
exr_status exr_audio_output_flush(exr_audio_output *a,exr_error *e) {
  long code=0;
  if(!a) return exr_fail(e,EXR_ARGUMENT,"Missing native audio output");
#if defined(_WIN32)
  code=waveOutReset(a->device);
  if(!code) { unsigned i; for(i=0;i<OUTPUT_SLOTS;i++) a->slots[i].frames=0; if(a->paused) code=waveOutPause(a->device); }
#elif defined(__APPLE__)
  code=AudioQueueStop(a->device,1);
  if(!code) code=AudioQueueReset(a->device);
  if(!code) { unsigned i; a->started=0; for(i=0;i<OUTPUT_SLOTS;i++) atomic_store_explicit(&a->slots[i].queued,0,memory_order_release); }
#elif defined(__ANDROID__)
  code=(*a->play)->SetPlayState(a->play,SL_PLAYSTATE_STOPPED);
  if(!code) code=(*a->queue)->Clear(a->queue);
  if(!code) {
    unsigned i; a->head=a->tail=a->count=0; for(i=0;i<OUTPUT_SLOTS;i++) a->slots[i].frames=0;
    code=(*a->play)->SetPlayState(a->play,a->paused ? SL_PLAYSTATE_PAUSED : SL_PLAYSTATE_PLAYING);
  }
#elif defined(__linux__)
  code=a->drop(a->device); if(!code) { code=a->prepare(a->device); a->native_paused=0; }
#endif
  return code ? output_error(e,"flush",code) : exr_fail(e,EXR_OK,"");
}
