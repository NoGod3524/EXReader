/* SPDX-License-Identifier: MIT */
#include "exreader.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static exr_error error; static unsigned checks;
#define CHECK(x) do { checks++; if(!(x)) { fprintf(stderr,"line %d: %s (%d: %s)\n",__LINE__,#x,error.code,error.message); exit(1); } } while(0)
#define OK(x) CHECK((x)==EXR_OK)
static int cancel(void *context) { return *(int *)context; }
static void progress(void *context,exr_stage stage,uint64_t completed,uint64_t total) { (void)stage; (void)total; if(completed) *(int *)context=1; }
int main(void) {
  char title[]="Audio",uri[]="opaque:source"; size_t count,index; exr_audio *a=NULL; exr_audio_position position;
  exr_audio_track tracks[2]={{"first",uri,"audio/custom",1000},{NULL,"https://host/chapter","audio/mpeg",2000}};
  exr_audio_chapter chapters[3]={{"whole","Book",SIZE_MAX,0,3000},{NULL,"Opening",0,0,1000},{NULL,"Second",0,1000,3000}};
  exr_audio_sync sync[3]={{"part-a",0,3,0,500},{"part-b",7,12,250,1500},{"part-a",3,6,1000,3000}};
  exr_audio_input in={0}; exr_control control={0}; int stopped=1;
  in.struct_size=sizeof(in); in.title=title; in.tracks=tracks; in.track_count=2; in.chapters=chapters; in.chapter_count=3; in.sync=sync; in.sync_count=3;
  OK(exr_audio_create(&in,NULL,&a,&error)); memset(title,'x',5); memset(uri,'x',sizeof(uri)-1);
  CHECK(!strcmp(exr_audio_title(a),"Audio") && exr_audio_duration(a)==3000 && exr_audio_memory_size(a)>sizeof(in));
  CHECK(exr_audio_tracks(a,&count) && count==2 && !strcmp(exr_audio_tracks(a,NULL)[0].uri,"opaque:source") && !strcmp(exr_audio_tracks(a,NULL)[1].id,"track-2"));
  CHECK(exr_audio_chapters(a,&count) && count==3 && !strcmp(exr_audio_chapters(a,NULL)[1].id,"chapter-2") && exr_audio_chapters(a,NULL)[2].parent==0);
  CHECK(exr_audio_syncs(a,&count) && count==3 && !strcmp(exr_audio_syncs(a,NULL)[1].part_id,"part-b"));
  OK(exr_audio_locate(a,0,&position,&error)); CHECK(position.track==0 && !position.offset_ms);
  OK(exr_audio_locate(a,999,&position,&error)); CHECK(position.track==0 && position.offset_ms==999);
  OK(exr_audio_locate(a,1000,&position,&error)); CHECK(position.track==1 && !position.offset_ms);
  OK(exr_audio_locate(a,3000,&position,&error)); CHECK(position.track==1 && position.offset_ms==2000);
  CHECK(exr_audio_locate(a,3001,&position,&error)==EXR_ARGUMENT && position.track==SIZE_MAX);
  OK(exr_audio_sync_at(a,300,0,NULL,&index,&error)); CHECK(index==0);
  OK(exr_audio_sync_at(a,300,1,NULL,&index,&error)); CHECK(index==1);
  OK(exr_audio_sync_at(a,300,2,NULL,&index,&error)); CHECK(index==SIZE_MAX);
  OK(exr_audio_sync_at(a,500,0,NULL,&index,&error)); CHECK(index==1);
  OK(exr_audio_sync_at(a,3000,0,NULL,&index,&error)); CHECK(index==SIZE_MAX);
  OK(exr_audio_sync_text(a,"part-a",2,4,0,NULL,&index,&error)); CHECK(index==0);
  OK(exr_audio_sync_text(a,"part-a",2,4,1,NULL,&index,&error)); CHECK(index==2);
  OK(exr_audio_sync_text(a,"part-a",3,3,0,NULL,&index,&error)); CHECK(index==2);
  OK(exr_audio_sync_text(a,"part-a",6,6,0,NULL,&index,&error)); CHECK(index==SIZE_MAX);
  CHECK(exr_audio_sync_text(a,"\xc0",0,1,0,NULL,&index,&error)==EXR_ENCODING && index==SIZE_MAX);
  CHECK(exr_audio_sync_at(a,0,4,NULL,&index,&error)==EXR_ARGUMENT && index==SIZE_MAX);
  control.cancelled=cancel; control.context=&stopped;
  CHECK(exr_audio_sync_at(a,300,0,&control,&index,&error)==EXR_CANCELLED && index==SIZE_MAX);
  CHECK(exr_audio_sync_text(a,"part-a",0,1,0,&control,&index,&error)==EXR_CANCELLED && index==SIZE_MAX);
  exr_audio_free(a); a=NULL;
  CHECK(exr_audio_create(&in,&control,&a,&error)==EXR_CANCELLED && !a);
  stopped=0; control.progress=progress; CHECK(exr_audio_create(&in,&control,&a,&error)==EXR_CANCELLED && !a);
  tracks[1].id="first"; CHECK(exr_audio_create(&in,NULL,&a,&error)==EXR_ARGUMENT && !a); tracks[1].id=NULL;
  tracks[0].duration_ms=UINT64_MAX; CHECK(exr_audio_create(&in,NULL,&a,&error)==EXR_ARGUMENT && !a); tracks[0].duration_ms=1000;
  tracks[0].duration_ms=0; CHECK(exr_audio_create(&in,NULL,&a,&error)==EXR_ARGUMENT && !a); tracks[0].duration_ms=1000;
  chapters[2].parent=2; CHECK(exr_audio_create(&in,NULL,&a,&error)==EXR_ARGUMENT && !a); chapters[2].parent=1;
  CHECK(exr_audio_create(&in,NULL,&a,&error)==EXR_ARGUMENT && !a); chapters[2].parent=0;
  chapters[2].id="whole"; CHECK(exr_audio_create(&in,NULL,&a,&error)==EXR_ARGUMENT && !a); chapters[2].id=NULL;
  sync[2].end_ms=3001; CHECK(exr_audio_create(&in,NULL,&a,&error)==EXR_ARGUMENT && !a); sync[2].end_ms=3000;
  sync[2].part_id="\xff"; CHECK(exr_audio_create(&in,NULL,&a,&error)==EXR_ENCODING && !a); sync[2].part_id="part-a";
  sync[2].end=3; CHECK(exr_audio_create(&in,NULL,&a,&error)==EXR_ARGUMENT && !a); sync[2].end=6;
  in.track_count=10001; CHECK(exr_audio_create(&in,NULL,&a,&error)==EXR_LIMIT && !a); in.track_count=2;
  in.chapter_count=100001; CHECK(exr_audio_create(&in,NULL,&a,&error)==EXR_LIMIT && !a); in.chapter_count=3;
  in.sync_count=1000001; CHECK(exr_audio_create(&in,NULL,&a,&error)==EXR_LIMIT && !a); in.sync_count=3;
  in.struct_size--; CHECK(exr_audio_create(&in,NULL,&a,&error)==EXR_ARGUMENT && !a); in.struct_size++;
  { struct { exr_audio_input input; unsigned char tail[8]; } extra={0}; extra.input=in; extra.input.struct_size=sizeof(extra); extra.tail[0]=1;
    CHECK(exr_audio_create(&extra.input,NULL,&a,&error)==EXR_ARGUMENT && !a); extra.tail[0]=0; OK(exr_audio_create(&extra.input,NULL,&a,&error)); exr_audio_free(a); a=NULL;
  }
  in.chapter_count=in.sync_count=0; in.track_count=1; tracks[0].duration_ms=UINT64_MAX;
  OK(exr_audio_create(&in,NULL,&a,&error)); OK(exr_audio_locate(a,UINT64_MAX,&position,&error)); CHECK(position.track==0 && position.offset_ms==UINT64_MAX); exr_audio_free(a);
  CHECK(!exr_audio_tracks(NULL,&count) && !count && !exr_audio_chapters(NULL,&count) && !count && !exr_audio_syncs(NULL,&count) && !count);
  CHECK(!exr_audio_duration(NULL) && !exr_audio_memory_size(NULL) && !strcmp(exr_audio_title(NULL),"")); exr_audio_free(NULL);
  printf("%u audio timeline checks passed\n",checks); return 0;
}
