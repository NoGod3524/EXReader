/* SPDX-License-Identifier: GPL-3.0-only */
#include "internal.h"
struct exr_audio {
  char *title; exr_audio_track *tracks; exr_audio_chapter *chapters; exr_audio_sync *sync;
  uint64_t *starts,duration; size_t track_count,chapter_count,sync_count,bytes,references;
};
void exr_audio_free(exr_audio *a) {
  size_t i; if(!a || --a->references) return;
  for(i=0;i<a->track_count;i++) { free((void *)a->tracks[i].id); free((void *)a->tracks[i].uri); free((void *)a->tracks[i].media_type); }
  for(i=0;i<a->chapter_count;i++) { free((void *)a->chapters[i].id); free((void *)a->chapters[i].title); }
  for(i=0;i<a->sync_count;i++) free((void *)a->sync[i].part_id);
  free(a->title); free(a->tracks); free(a->chapters); free(a->sync); free(a->starts); free(a);
}
const char *exr_audio_title(const exr_audio *a) { return a ? a->title : ""; }
uint64_t exr_audio_duration(const exr_audio *a) { return a ? a->duration : 0; }
const exr_audio_track *exr_audio_tracks(const exr_audio *a,size_t *n) { if(n) *n=a ? a->track_count : 0; return a ? a->tracks : NULL; }
const exr_audio_chapter *exr_audio_chapters(const exr_audio *a,size_t *n) { if(n) *n=a ? a->chapter_count : 0; return a ? a->chapters : NULL; }
const exr_audio_sync *exr_audio_syncs(const exr_audio *a,size_t *n) { if(n) *n=a ? a->sync_count : 0; return a ? a->sync : NULL; }
size_t exr_audio_memory_size(const exr_audio *a) { return a ? a->bytes : 0; }
static exr_status copy_string(const char *input,size_t *bytes,const char **out,exr_error *e) {
  size_t n=0,at=0; uint32_t cp; char *copy;
  if(!input) input="";
  while(n<=65536 && input[n]) n++;
  if(n>65536 || n+1>(size_t)16*1024*1024-*bytes) return exr_fail(e,EXR_LIMIT,"Audio metadata exceeds string budget");
  while(at<n) if(!exr_next(input,n,&at,&cp)) return exr_fail(e,EXR_ENCODING,"Audio metadata is not UTF-8");
  copy=exr_copy(input,n); if(!copy) return exr_fail(e,EXR_MEMORY,"Audio metadata allocation failed");
  *out=copy; *bytes+=n+1; return EXR_OK;
}
static int compare_id(const void *a,const void *b) { return strcmp(*(const char *const *)a,*(const char *const *)b); }
static exr_status unique_ids(const char **ids,size_t n,exr_error *e) {
  size_t i; qsort(ids,n,sizeof(*ids),compare_id);
  for(i=1;i<n;i++) if(!strcmp(ids[i-1],ids[i])) return exr_fail(e,EXR_ARGUMENT,"Duplicate audio track/chapter ID");
  return EXR_OK;
}
exr_status exr_audio_create(const exr_audio_input *input,const exr_control *control,exr_audio **out,exr_error *e) {
  exr_audio *a; exr_audio_input in; exr_status status; size_t i,strings=0,bytes,ids_count; const char **ids=NULL,*title=NULL;
  if(!out) return exr_fail(e,EXR_ARGUMENT,"Missing audio output");
  *out=NULL;
  if(!input || input->struct_size<sizeof(in) || input->struct_size>4096) return exr_fail(e,EXR_ARGUMENT,"Invalid audio input size");
  for(i=sizeof(in);i<input->struct_size;i++) if(((const unsigned char *)input)[i]) return exr_fail(e,EXR_ARGUMENT,"Unsupported audio input extension");
  in=*input;
  if(!in.tracks || !in.track_count || (!in.chapters && in.chapter_count) || (!in.sync && in.sync_count)) return exr_fail(e,EXR_ARGUMENT,"Missing audio input tables");
  if(in.track_count>10000 || in.chapter_count>100000 || in.sync_count>1000000) return exr_fail(e,EXR_LIMIT,"Audio table count exceeds budget");
  bytes=sizeof(*a)+in.track_count*(sizeof(*a->tracks)+sizeof(*a->starts))+in.chapter_count*sizeof(*a->chapters)+in.sync_count*sizeof(*a->sync);
  if(bytes>(size_t)128*1024*1024) return exr_fail(e,EXR_LIMIT,"Audio table payload exceeds budget");
  status=exr_control_cancel(control,e); if(status!=EXR_OK) return status;
  a=calloc(1,sizeof(*a)); if(!a) return exr_fail(e,EXR_MEMORY,"Audio allocation failed");
  a->references=1;
  a->tracks=calloc(in.track_count,sizeof(*a->tracks)); a->starts=calloc(in.track_count,sizeof(*a->starts));
  if(in.chapter_count) a->chapters=calloc(in.chapter_count,sizeof(*a->chapters));
  if(in.sync_count) a->sync=calloc(in.sync_count,sizeof(*a->sync));
  ids_count=in.track_count>in.chapter_count ? in.track_count : in.chapter_count; ids=malloc(ids_count*sizeof(*ids));
  if(!a->tracks || !a->starts || (in.chapter_count && !a->chapters) || (in.sync_count && !a->sync) || !ids) { status=exr_fail(e,EXR_MEMORY,"Audio tables allocation failed"); goto finish; }
  status=copy_string(in.title,&strings,&title,e); a->title=(char *)title;
  for(i=0;status==EXR_OK && i<in.track_count;i++) {
    char generated[32]; const exr_audio_track *t=&in.tracks[i]; exr_audio_track *v=&a->tracks[i]; const char *id=t->id;
    status=exr_control_poll(control,EXR_STAGE_READ,i,in.track_count,e); if(status!=EXR_OK) break;
    if(!t->duration_ms || t->duration_ms>UINT64_MAX-a->duration) { status=exr_fail(e,EXR_ARGUMENT,"Invalid/overflowing audio duration"); break; }
    a->track_count=i+1; a->starts[i]=a->duration; a->duration+=t->duration_ms; v->duration_ms=t->duration_ms;
    if(!id || !*id) { snprintf(generated,sizeof(generated),"track-%zu",i+1); id=generated; }
    status=copy_string(id,&strings,&v->id,e);
    if(status==EXR_OK) status=copy_string(t->uri,&strings,&v->uri,e);
    if(status==EXR_OK) status=copy_string(t->media_type,&strings,&v->media_type,e);
    ids[i]=v->id;
  }
  if(status==EXR_OK) status=unique_ids(ids,in.track_count,e);
  for(i=0;status==EXR_OK && i<in.chapter_count;i++) {
    char generated[32]; const exr_audio_chapter *c=&in.chapters[i]; exr_audio_chapter *v=&a->chapters[i]; const char *id=c->id;
    if(!(i&255)) status=exr_control_cancel(control,e);
    if(status!=EXR_OK) break;
    if(c->start_ms>=c->end_ms || c->end_ms>a->duration || (c->parent!=SIZE_MAX &&
       (c->parent>=i || c->start_ms<a->chapters[c->parent].start_ms || c->end_ms>a->chapters[c->parent].end_ms))) { status=exr_fail(e,EXR_ARGUMENT,"Invalid audio chapter range/parent"); break; }
    a->chapter_count=i+1; v->parent=c->parent; v->start_ms=c->start_ms; v->end_ms=c->end_ms;
    if(!id || !*id) { snprintf(generated,sizeof(generated),"chapter-%zu",i+1); id=generated; }
    status=copy_string(id,&strings,&v->id,e); if(status==EXR_OK) status=copy_string(c->title,&strings,&v->title,e); ids[i]=v->id;
  }
  if(status==EXR_OK) status=unique_ids(ids,in.chapter_count,e);
  for(i=0;status==EXR_OK && i<in.sync_count;i++) {
    const exr_audio_sync *s=&in.sync[i]; exr_audio_sync *v=&a->sync[i];
    if(!(i&255)) status=exr_control_cancel(control,e);
    if(status!=EXR_OK) break;
    if(!s->part_id || !*s->part_id || s->start>=s->end || s->start_ms>=s->end_ms || s->end_ms>a->duration) { status=exr_fail(e,EXR_ARGUMENT,"Invalid audio/text synchronization range"); break; }
    a->sync_count=i+1; v->start=s->start; v->end=s->end; v->start_ms=s->start_ms; v->end_ms=s->end_ms;
    status=copy_string(s->part_id,&strings,&v->part_id,e);
  }
  if(status==EXR_OK) status=exr_control_cancel(control,e);
finish:
  free(ids);
  if(status!=EXR_OK) { exr_audio_free(a); return status; }
  a->bytes=bytes+strings; *out=a; return exr_fail(e,EXR_OK,"");
}
exr_status exr_audio_locate(const exr_audio *a,uint64_t time,exr_audio_position *out,exr_error *e) {
  size_t low=0,high;
  if(out) { out->track=SIZE_MAX; out->offset_ms=0; }
  if(!a || !out || time>a->duration) return exr_fail(e,EXR_ARGUMENT,"Invalid audio timeline position");
  high=a->track_count;
  while(low<high) { size_t mid=low+(high-low)/2; if(a->starts[mid]<=time) low=mid+1; else high=mid; }
  out->track=low-1; out->offset_ms=time-a->starts[low-1]; return exr_fail(e,EXR_OK,"");
}
exr_status exr_audio_sync_at(const exr_audio *a,uint64_t time,size_t from,const exr_control *control,size_t *index,exr_error *e) {
  size_t i; exr_status status;
  if(index) *index=SIZE_MAX;
  if(!a || !index || time>a->duration || from>a->sync_count) return exr_fail(e,EXR_ARGUMENT,"Invalid audio sync query");
  status=exr_control_cancel(control,e); if(status!=EXR_OK) return status;
  for(i=from;i<a->sync_count;i++) {
    if(!((i-from)&255) && exr_control_cancel(control,e)!=EXR_OK) return EXR_CANCELLED;
    if(time>=a->sync[i].start_ms && time<a->sync[i].end_ms) { *index=i; break; }
  }
  return exr_fail(e,EXR_OK,"");
}
exr_status exr_audio_sync_text(const exr_audio *a,const char *part,size_t start,size_t end,size_t from,
                                const exr_control *control,size_t *index,exr_error *e) {
  size_t i,n=0,at=0; uint32_t cp; exr_status status;
  if(index) *index=SIZE_MAX;
  if(!a || !index || !part || !*part || start>end || from>a->sync_count) return exr_fail(e,EXR_ARGUMENT,"Invalid text/audio sync query");
  while(n<=65536 && part[n]) n++;
  if(n>65536) return exr_fail(e,EXR_LIMIT,"Audio text part ID exceeds budget");
  while(at<n) if(!exr_next(part,n,&at,&cp)) return exr_fail(e,EXR_ENCODING,"Invalid audio text part UTF-8");
  status=exr_control_cancel(control,e); if(status!=EXR_OK) return status;
  for(i=from;i<a->sync_count;i++) {
    const exr_audio_sync *s=&a->sync[i];
    if(!((i-from)&255) && exr_control_cancel(control,e)!=EXR_OK) return EXR_CANCELLED;
    if(!strcmp(part,s->part_id) && (start==end ? s->start<=start && start<s->end : s->start<end && start<s->end)) { *index=i; break; }
  }
  return exr_fail(e,EXR_OK,"");
}

exr_status exr_audio_ref(exr_audio *a,exr_error *e) {
  if(!a) return exr_fail(e,EXR_ARGUMENT,"Missing audio timeline");
  if(a->references==SIZE_MAX) return exr_fail(e,EXR_LIMIT,"Audio reference count exhausted");
  a->references++; return EXR_OK;
}
exr_status exr_audio_time(const exr_audio *a,size_t track,uint64_t offset,uint64_t *out,exr_error *e) {
  if(out) *out=0;
  if(!a || !out || track>=a->track_count || offset>a->tracks[track].duration_ms) return exr_fail(e,EXR_ARGUMENT,"Invalid track-local audio position");
  *out=a->starts[track]+offset; return exr_fail(e,EXR_OK,"");
}
