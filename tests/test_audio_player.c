/* SPDX-License-Identifier: MIT */
#include "exreader.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
static exr_error error; static unsigned checks;
#define CHECK(x) do { checks++; if(!(x)) { fprintf(stderr,"line %d: %s (%d: %s)\n",__LINE__,#x,error.code,error.message); exit(1); } } while(0)
#define OK(x) CHECK((x)==EXR_OK)
typedef struct { exr_audio_player *player; exr_audio_command events[64]; size_t count,releases; int fail; } probe;
static exr_status command(void *context,const exr_audio_command *c,exr_error *e) {
  probe *p=context; exr_audio_playback state; (void)e;
  CHECK(p->count<64 && c->source && c->source->duration_ms && c->rate>0 && c->rate<=16); p->events[p->count++]=*c;
  if(p->player) { OK(exr_audio_player_get(p->player,&state,&error)); CHECK(exr_audio_player_seek(p->player,0,&error)==EXR_ARGUMENT); }
  if(p->fail && c->kind==EXR_AUDIO_RATE) { p->fail=0; return EXR_IO; }
  return EXR_OK;
}
static void release(void *context) { ((probe *)context)->releases++; }
static exr_audio *audio(int inserted) {
  exr_audio_track tracks[3]={{"intro","host:0","audio/custom",100},{"one","host:1","audio/custom",1000},{"two","host:2","audio/custom",2000}};
  exr_audio_input input={0}; exr_audio *a=NULL; input.struct_size=sizeof(input); input.tracks=tracks+(inserted ? 0 : 1); input.track_count=inserted ? 3 : 2;
  OK(exr_audio_create(&input,NULL,&a,&error)); return a;
}
int main(void) {
  probe p={0}; exr_audio *a=audio(0); exr_audio_player *player=NULL; exr_audio_backend backend={0}; exr_audio_playback state; size_t n; uint64_t old,time;
  backend.struct_size=sizeof(backend); backend.command=command; backend.context=&p; backend.release=release;
  backend.struct_size--; CHECK(exr_audio_player_create(a,&backend,&player,&error)==EXR_ARGUMENT && !player && !p.releases); backend.struct_size++;
  OK(exr_audio_time(a,1,100,&time,&error)); CHECK(time==1100);
  CHECK(exr_audio_time(a,2,0,&time,&error)==EXR_ARGUMENT && !time);
  OK(exr_audio_player_create(a,&backend,&player,&error)); p.player=player; exr_audio_free(a); CHECK(!p.count);
  OK(exr_audio_player_restore(player,"two",250,1.5,&error)); CHECK(!p.count);
  OK(exr_audio_player_get(player,&state,&error)); CHECK(state.time_ms==1250 && state.position.track==1 && state.rate==1.5 && !state.playing && !state.needs_reload);
  CHECK(exr_audio_player_restore(player,"missing",0,1,&error)==EXR_ARGUMENT);
  CHECK(exr_audio_player_restore(player,"two",2001,1,&error)==EXR_ARGUMENT);
  CHECK(exr_audio_player_rate(player,NAN,&error)==EXR_ARGUMENT); CHECK(exr_audio_player_rate(player,0,&error)==EXR_ARGUMENT);
  OK(exr_audio_player_play(player,&error)); CHECK(p.count==2 && p.events[0].kind==EXR_AUDIO_LOAD && p.events[0].track==1 && p.events[0].offset_ms==250 && p.events[0].rate==1.5 && p.events[1].kind==EXR_AUDIO_PLAY);
  OK(exr_audio_player_get(player,&state,&error)); old=state.generation; n=p.count;
  OK(exr_audio_player_play(player,&error)); CHECK(n==p.count); OK(exr_audio_player_get(player,&state,&error)); CHECK(state.generation==old);
  OK(exr_audio_player_report(player,state.generation,1,500,0,&error));
  CHECK(exr_audio_player_report(player,state.generation,1,499,0,&error)==EXR_ARGUMENT);
  OK(exr_audio_player_rate(player,1.25,&error)); CHECK(p.events[p.count-1].kind==EXR_AUDIO_RATE);
  CHECK(exr_audio_player_report(player,old,1,600,0,&error)==EXR_ARGUMENT); /* Old command generation. */
  OK(exr_audio_player_get(player,&state,&error)); CHECK(state.position.offset_ms==500 && state.rate==1.25 && state.playing);
  OK(exr_audio_player_pause(player,&error)); CHECK(p.events[p.count-1].kind==EXR_AUDIO_PAUSE);
  OK(exr_audio_player_seek(player,1100,&error)); CHECK(p.events[p.count-1].kind==EXR_AUDIO_SEEK);
  OK(exr_audio_player_get(player,&state,&error)); CHECK(!state.playing && state.time_ms==1100);
  OK(exr_audio_player_play(player,&error)); p.fail=1; CHECK(exr_audio_player_rate(player,2,&error)==EXR_IO && error.message[0]);
  CHECK(p.events[p.count-1].kind==EXR_AUDIO_PAUSE); OK(exr_audio_player_get(player,&state,&error)); CHECK(!state.playing && state.needs_reload && state.rate==1.25);
  CHECK(exr_audio_player_report(player,state.generation,1,1000,0,&error)==EXR_ARGUMENT);
  OK(exr_audio_player_play(player,&error)); CHECK(p.events[p.count-2].kind==EXR_AUDIO_LOAD && p.events[p.count-1].kind==EXR_AUDIO_PLAY);
  OK(exr_audio_player_get(player,&state,&error)); OK(exr_audio_player_report(player,state.generation,1,2000,1,&error));
  OK(exr_audio_player_get(player,&state,&error)); CHECK(state.time_ms==3000 && !state.playing);
  OK(exr_audio_player_play(player,&error)); CHECK(p.events[p.count-2].track==0);
  OK(exr_audio_player_get(player,&state,&error)); old=state.generation;
  CHECK(exr_audio_player_report(player,old,0,999,1,&error)==EXR_ARGUMENT);
  OK(exr_audio_player_report(player,old,0,1000,1,&error)); CHECK(p.events[p.count-2].kind==EXR_AUDIO_LOAD && p.events[p.count-2].track==1 && p.events[p.count-1].kind==EXR_AUDIO_PLAY);
  CHECK(exr_audio_player_report(player,old,0,1000,1,&error)==EXR_ARGUMENT);
  OK(exr_audio_player_seek(player,3000,&error)); OK(exr_audio_player_get(player,&state,&error)); CHECK(!state.playing && state.time_ms==3000);
  CHECK(exr_audio_player_seek(player,3001,&error)==EXR_ARGUMENT);
  exr_audio_player_free(player); p.player=NULL; CHECK(p.releases==1 && p.events[p.count-1].kind==EXR_AUDIO_CLOSE);
  /* Resume by ID after a new track is inserted before the original tracks. */
  a=audio(1); memset(&p,0,sizeof(p)); OK(exr_audio_player_create(a,&backend,&player,&error)); p.player=player;
  OK(exr_audio_player_restore(player,"two",500,2,&error)); OK(exr_audio_player_get(player,&state,&error)); CHECK(state.position.track==2 && state.time_ms==1600 && !p.count);
  exr_audio_free(a); exr_audio_player_free(player); CHECK(p.releases==1 && !p.count); exr_audio_player_free(NULL);
  printf("%u audio backend control checks passed\n",checks); return 0;
}
