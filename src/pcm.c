/* SPDX-License-Identifier: MIT */
#include "audio_internal.h"
struct exr_pcm { exr_pcm_info info; exr_pcm_read_fn read; exr_context_release_fn release; void *context; unsigned kind,busy; };
static int valid(const exr_pcm_info *info) {
  uint32_t mask=info->channel_mask; unsigned n=0;
  while(mask) { n+=mask&1; mask>>=1; }
  return info->sample_rate && info->sample_rate<=1048575 && info->channels && info->channels<=32 && (!info->channel_mask || n==info->channels);
}
exr_status exr_pcm_create(const exr_pcm_input *input,exr_pcm **out,exr_error *e) {
  exr_pcm *pcm; size_t i;
  if(out) *out=NULL;
  if(!out || !input || input->struct_size<sizeof(*input) || input->struct_size>4096 || !input->read || !valid(&input->info))
    return exr_fail(e,EXR_ARGUMENT,"Invalid PCM provider input");
  for(i=sizeof(*input);i<input->struct_size;i++) if(((const unsigned char *)input)[i]) return exr_fail(e,EXR_ARGUMENT,"Unsupported PCM provider extension");
  pcm=calloc(1,sizeof(*pcm)); if(!pcm) return exr_fail(e,EXR_MEMORY,"PCM provider allocation failed");
  pcm->info=input->info; pcm->read=input->read; pcm->release=input->release; pcm->context=input->context; *out=pcm; return exr_fail(e,EXR_OK,"");
}
static exr_status wave_read(void *context,uint64_t first,size_t frames,float *output,size_t *read,const exr_control *control,exr_error *e) {
  return exr_wave_read(context,first,frames,output,read,control,e);
}
static exr_status flac_read(void *context,uint64_t first,size_t frames,float *output,size_t *read,const exr_control *control,exr_error *e) {
  return exr_flac_read(context,first,frames,output,read,control,e);
}
static void wave_free(void *context) { exr_wave_free(context); }
static void flac_free(void *context) { exr_flac_free(context); }
static exr_status mp3_read(void *context,uint64_t first,size_t frames,float *output,size_t *read,const exr_control *control,exr_error *e) {
  return exr_mp3_read(context,first,frames,output,read,control,e);
}
static void mp3_free(void *context) { exr_mp3_free(context); }
static exr_status aac_read(void *context,uint64_t first,size_t frames,float *output,size_t *read,const exr_control *control,exr_error *e) {
  return exr_aac_read(context,first,frames,output,read,control,e);
}
static void aac_free(void *context) { exr_aac_free(context); }
static exr_status m4b_read(void *context,uint64_t first,size_t frames,float *output,size_t *read,const exr_control *control,exr_error *e) {
  return exr_m4b_read(context,first,frames,output,read,control,e);
}
static void m4b_free(void *context) { exr_m4b_free(context); }
exr_status exr_pcm_open_source(const exr_source *source,exr_pcm **out,exr_error *e) {
  exr_pcm *pcm; unsigned char signature[8]={0}; size_t done=0,signature_size; exr_status status; int bmff;
  if(out) *out=NULL;
  if(!source || !out || !source->read_at || source->size<4) return exr_fail(e,EXR_ARGUMENT,"Invalid PCM byte source");
  signature_size=source->size<sizeof(signature) ? (size_t)source->size : sizeof(signature);
  while(done<signature_size) {
    size_t got; status=exr_control_cancel(&source->control,e); if(status!=EXR_OK) return status;
    got=source->read_at(source->context,done,signature+done,signature_size-done);
    if(!got || got>signature_size-done) return exr_fail(e,EXR_IO,"PCM source returned an invalid/short read");
    done+=got;
  }
  bmff=signature_size==8 && (!memcmp(signature+4,"ftyp",4) || !memcmp(signature+4,"free",4) ||
    !memcmp(signature+4,"skip",4) || !memcmp(signature+4,"wide",4) || !memcmp(signature+4,"mdat",4) || !memcmp(signature+4,"moov",4));
  if(!bmff && memcmp(signature,"RIFF",4) && memcmp(signature,"fLaC",4) && memcmp(signature,"ID3",3) &&
     !(signature[0]==255 && (signature[1]&0xe0)==0xe0)) return exr_fail(e,EXR_FORMAT,"Unknown PCM source codec");
  pcm=calloc(1,sizeof(*pcm)); if(!pcm) return exr_fail(e,EXR_MEMORY,"PCM decoder allocation failed");
  if(!memcmp(signature,"RIFF",4)) {
    exr_wave *wave=NULL; const exr_wave_info *info;
    status=exr_wave_open_source(source,&wave,e);
    if(status==EXR_OK) {
      info=exr_wave_format(wave); pcm->info=(exr_pcm_info){info->sample_rate,info->channels,info->channel_mask,info->frames};
      pcm->context=wave; pcm->read=wave_read; pcm->release=wave_free; pcm->kind=1;
    }
  } else if(!memcmp(signature,"fLaC",4)) {
    exr_flac *flac=NULL; const exr_flac_info *info;
    status=exr_flac_open_source(source,&flac,e);
    if(status==EXR_OK) {
      info=exr_flac_format(flac); pcm->info=(exr_pcm_info){info->sample_rate,info->channels,0,info->frames};
      pcm->context=flac; pcm->read=flac_read; pcm->release=flac_free; pcm->kind=2;
    }
  } else if(bmff) {
    exr_m4b *m4b=NULL; const exr_m4b_info *info;
    status=exr_m4b_open_source(source,&m4b,e);
    if(status==EXR_OK) {
      info=exr_m4b_format(m4b); pcm->info=(exr_pcm_info){info->sample_rate,info->channels,0,info->frames};
      pcm->context=m4b; pcm->read=m4b_read; pcm->release=m4b_free; pcm->kind=5;
    }
  } else {
    exr_mp3 *mp3=NULL; const exr_mp3_info *info;
    int adts=signature[0]==255 && !(signature[1]&6);
    status=adts ? EXR_FORMAT : exr_mp3_open_source(source,&mp3,e);
    if(status==EXR_OK) {
      info=exr_mp3_format(mp3); pcm->info=(exr_pcm_info){info->sample_rate,info->channels,0,info->frames};
      pcm->context=mp3; pcm->read=mp3_read; pcm->release=mp3_free; pcm->kind=3;
    } else if(status==EXR_FORMAT) {
      /* ID3 is shared by MP3 and ADTS. Failed opens retain source ownership. */
      exr_aac *aac=NULL; const exr_aac_info *aac_info;
      status=exr_aac_open_source(source,&aac,e);
      if(status==EXR_OK) {
        aac_info=exr_aac_format(aac); pcm->info=(exr_pcm_info){aac_info->sample_rate,aac_info->channels,0,aac_info->frames};
        pcm->context=aac; pcm->read=aac_read; pcm->release=aac_free; pcm->kind=4;
      }
    }
  }
  if(status!=EXR_OK) { free(pcm); return status; }
  *out=pcm; return exr_fail(e,EXR_OK,"");
}
exr_status exr_pcm_open(const char *path,const exr_control *control,exr_pcm **out,exr_error *e) {
  exr_source source; exr_status status;
  if(out) *out=NULL;
  if(!path || !out) return exr_fail(e,EXR_ARGUMENT,"Invalid PCM file input");
  status=exr_file_source_limit(path,INT64_MAX,&source,e); if(status!=EXR_OK) return status;
  if(control) source.control=*control;
  status=exr_pcm_open_source(&source,out,e); if(status!=EXR_OK) source.release(source.context); return status;
}
void exr_pcm_free(exr_pcm *pcm) { if(pcm) { if(pcm->release) pcm->release(pcm->context); free(pcm); } }
const exr_pcm_info *exr_pcm_format(const exr_pcm *pcm) { return pcm ? &pcm->info : NULL; }
exr_status exr_pcm_read(exr_pcm *pcm,uint64_t first,size_t frames,float *output,size_t *read,const exr_control *control,exr_error *e) {
  exr_error local={0}; exr_status status; size_t got=0,i; uint64_t remaining;
  if(read) *read=0;
  if(!pcm || !read || (frames && !output) || pcm->busy || first>pcm->info.frames || first==UINT64_MAX)
    return exr_fail(e,EXR_ARGUMENT,"Invalid or reentrant PCM read");
  if(frames>65536) return exr_fail(e,EXR_LIMIT,"PCM read exceeds 65536 frames");
  if(frames) memset(output,0,frames*pcm->info.channels*sizeof(*output));
  remaining=pcm->info.frames==UINT64_MAX ? UINT64_MAX-first : pcm->info.frames-first;
  if(frames>remaining) frames=(size_t)remaining;
  pcm->busy=1; status=exr_control_poll(control,EXR_STAGE_READ,0,frames,&local);
  if(status==EXR_OK && frames) status=pcm->read(pcm->context,first,frames,output,&got,control,&local);
  if(status==EXR_OK && local.code!=EXR_OK) status=local.code;
  if(status==EXR_OK && got>frames) status=exr_fail(&local,EXR_FORMAT,"PCM provider returned too many frames");
  for(i=0;status==EXR_OK && i<got*pcm->info.channels;i++) if(!isfinite(output[i])) status=exr_fail(&local,EXR_FORMAT,"PCM provider returned nonfinite audio");
  if(status==EXR_OK && pcm->info.frames!=UINT64_MAX && got<frames) status=exr_fail(&local,EXR_FORMAT,"PCM provider ended before its declared frame count");
  if(status==EXR_OK) status=exr_control_poll(control,EXR_STAGE_READ,got,got,&local);
  pcm->busy=0;
  if(status!=EXR_OK) {
    if(frames) memset(output,0,frames*pcm->info.channels*sizeof(*output));
    if(!local.message[0]) exr_fail(&local,status,"PCM provider read failed"); else local.code=status;
    if(e) *e=local;
    return status;
  }
  if(pcm->kind==2) pcm->info.frames=exr_flac_format(pcm->context)->frames;
  else if(pcm->kind==3) pcm->info.frames=exr_mp3_format(pcm->context)->frames;
  else if(pcm->kind==4) pcm->info.frames=exr_aac_format(pcm->context)->frames;
  *read=got; return exr_fail(e,EXR_OK,"");
}
