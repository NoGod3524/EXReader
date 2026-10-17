/* SPDX-License-Identifier: GPL-3.0-only */
#include "internal.h"
struct exr_audio_player {
  exr_audio *audio; exr_audio_backend backend; const exr_audio_track *tracks; size_t count,track;
  uint64_t offset,generation; double rate; int playing,loaded,dirty,touched,busy;
};
static exr_status available(exr_audio_player *p,exr_error *e) {
  return p && !p->busy ? EXR_OK : exr_fail(e,EXR_ARGUMENT,"Missing or reentrant audio player");
}
static exr_status send(exr_audio_player *p,exr_audio_command_kind kind,size_t track,uint64_t offset,double rate,uint64_t generation,exr_error *e) {
  exr_audio_command c={kind,track,&p->tracks[track],offset,generation,rate}; exr_error local={0}; exr_status status;
  p->touched=1; status=p->backend.command(p->backend.context,&c,&local);
  if(status==EXR_OK && local.code!=EXR_OK) status=local.code;
  if(status!=EXR_OK) {
    if(!local.message[0]) exr_fail(&local,status,"Audio backend command failed"); else local.code=status;
    p->playing=0; p->loaded=0; p->dirty=1; p->generation=generation;
    if(kind!=EXR_AUDIO_PAUSE) { exr_error ignored={0}; c.kind=EXR_AUDIO_PAUSE; p->backend.command(p->backend.context,&c,&ignored); }
    if(e) *e=local;
  }
  return status;
}
/* LOAD replaces the host source and leaves it paused. Repositioning
   before first playback only changes metadata; no decoder/device is opened. */
static exr_status target(exr_audio_player *p,size_t track,uint64_t offset,double rate,int playing,exr_error *e) {
  exr_status status=EXR_OK; uint64_t generation; int load;
  if(p->generation==UINT64_MAX) return exr_fail(e,EXR_LIMIT,"Audio command generation exhausted");
  if(!p->dirty && track==p->track && offset==p->offset && rate==p->rate && playing==p->playing) return exr_fail(e,EXR_OK,"");
  generation=p->generation+1; p->busy=1;
  if(!p->touched && !playing) goto commit;
  load=!p->loaded || p->dirty || track!=p->track;
  if(load) status=send(p,EXR_AUDIO_LOAD,track,offset,rate,generation,e);
  else {
    if(p->playing && !playing) status=send(p,EXR_AUDIO_PAUSE,track,offset,rate,generation,e);
    if(status==EXR_OK && offset!=p->offset) status=send(p,EXR_AUDIO_SEEK,track,offset,rate,generation,e);
    if(status==EXR_OK && rate!=p->rate) status=send(p,EXR_AUDIO_RATE,track,offset,rate,generation,e);
  }
  if(status==EXR_OK && playing && (load || !p->playing)) status=send(p,EXR_AUDIO_PLAY,track,offset,rate,generation,e);
  if(status!=EXR_OK) { p->busy=0; return status; }
  p->loaded=1;
commit:
  p->track=track; p->offset=offset; p->rate=rate; p->playing=playing; p->generation=generation; p->dirty=0; p->busy=0;
  return exr_fail(e,EXR_OK,"");
}
exr_status exr_audio_player_create(exr_audio *audio,const exr_audio_backend *input,exr_audio_player **out,exr_error *e) {
  exr_audio_player *p; exr_status status; size_t i;
  if(out) *out=NULL;
  if(!audio || !input || !out || input->struct_size<sizeof(*input) || input->struct_size>4096 || !input->command) return exr_fail(e,EXR_ARGUMENT,"Invalid audio player backend");
  for(i=sizeof(*input);i<input->struct_size;i++) if(((const unsigned char *)input)[i]) return exr_fail(e,EXR_ARGUMENT,"Unsupported audio backend extension");
  p=calloc(1,sizeof(*p)); if(!p) return exr_fail(e,EXR_MEMORY,"Audio player allocation failed");
  status=exr_audio_ref(audio,e); if(status!=EXR_OK) { free(p); return status; }
  p->audio=audio; p->backend=*input; p->tracks=exr_audio_tracks(audio,&p->count); p->rate=1; *out=p; return exr_fail(e,EXR_OK,"");
}
void exr_audio_player_free(exr_audio_player *p) {
  if(!p) return;
  p->busy=1;
  if(p->touched) { exr_error ignored={0}; exr_audio_command c={EXR_AUDIO_CLOSE,p->track,&p->tracks[p->track],p->offset,p->generation,p->rate}; p->backend.command(p->backend.context,&c,&ignored); }
  if(p->backend.release) p->backend.release(p->backend.context);
  exr_audio_free(p->audio); free(p);
}
exr_status exr_audio_player_get(const exr_audio_player *p,exr_audio_playback *out,exr_error *e) {
  if(out) memset(out,0,sizeof(*out));
  if(!p || !out) return exr_fail(e,EXR_ARGUMENT,"Missing audio playback snapshot");
  out->position=(exr_audio_position){p->track,p->offset}; out->track_id=p->tracks[p->track].id; out->generation=p->generation;
  out->rate=p->rate; out->playing=p->playing; out->needs_reload=p->dirty;
  return exr_audio_time(p->audio,p->track,p->offset,&out->time_ms,e);
}
exr_status exr_audio_player_play(exr_audio_player *p,exr_error *e) {
  exr_status status=available(p,e); if(status!=EXR_OK) return status;
  if(p->offset==p->tracks[p->track].duration_ms) return target(p,p->track+1<p->count ? p->track+1 : 0,0,p->rate,1,e);
  return target(p,p->track,p->offset,p->rate,1,e);
}
exr_status exr_audio_player_pause(exr_audio_player *p,exr_error *e) {
  exr_status status=available(p,e); if(status!=EXR_OK) return status;
  if(!p->playing) return exr_fail(e,EXR_OK,"");
  return target(p,p->track,p->offset,p->rate,0,e);
}
exr_status exr_audio_player_seek(exr_audio_player *p,uint64_t time,exr_error *e) {
  exr_audio_position pos; exr_status status=available(p,e); if(status!=EXR_OK) return status;
  status=exr_audio_locate(p->audio,time,&pos,e); if(status!=EXR_OK) return status;
  return target(p,pos.track,pos.offset_ms,p->rate,p->playing && time<exr_audio_duration(p->audio),e);
}
exr_status exr_audio_player_rate(exr_audio_player *p,double rate,exr_error *e) {
  exr_status status=available(p,e); if(status!=EXR_OK) return status;
  if(!isfinite(rate) || rate<=0 || rate>16) return exr_fail(e,EXR_ARGUMENT,"Invalid audio playback rate");
  return target(p,p->track,p->offset,rate,p->playing,e);
}
exr_status exr_audio_player_restore(exr_audio_player *p,const char *id,uint64_t offset,double rate,exr_error *e) {
  size_t i,n=0; exr_status status=available(p,e); if(status!=EXR_OK) return status;
  if(!id || !isfinite(rate) || rate<=0 || rate>16) return exr_fail(e,EXR_ARGUMENT,"Invalid audio resume point");
  while(n<=65536 && id[n]) n++;
  if(!n || n>65536) return exr_fail(e,EXR_ARGUMENT,"Invalid audio resume track ID");
  for(i=0;i<p->count;i++) if(!strcmp(id,p->tracks[i].id)) {
    if(offset>p->tracks[i].duration_ms) return exr_fail(e,EXR_ARGUMENT,"Audio resume point is past track end");
    return target(p,i,offset,rate,0,e);
  }
  return exr_fail(e,EXR_ARGUMENT,"Audio resume track is missing");
}
exr_status exr_audio_player_report(exr_audio_player *p,uint64_t generation,size_t track,uint64_t offset,int ended,exr_error *e) {
  exr_status status=available(p,e); if(status!=EXR_OK) return status;
  if(!p->loaded || p->dirty || generation!=p->generation || track!=p->track || offset<p->offset || offset>p->tracks[track].duration_ms ||
     (ended!=0 && ended!=1) || (ended && offset!=p->tracks[track].duration_ms)) return exr_fail(e,EXR_ARGUMENT,"Stale or invalid audio backend report");
  if(ended) {
    if(track+1<p->count) return target(p,track+1,0,p->rate,p->playing,e);
    if(p->generation==UINT64_MAX) return exr_fail(e,EXR_LIMIT,"Audio command generation exhausted");
    p->generation++; p->playing=0;
  }
  p->offset=offset; return exr_fail(e,EXR_OK,"");
}
