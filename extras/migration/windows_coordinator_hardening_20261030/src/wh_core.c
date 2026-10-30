/* SPDX-License-Identifier: MIT */
#include "exr_wh.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
enum {H_START=0,H_ADMIT_BEGIN,H_ADMIT_OK,H_SNAP_BEGIN,H_SNAP_OK,H_IMPORT_BEGIN,
 H_IMPORT_OK,H_VERIFY_BEGIN,H_VERIFY_OK,H_PUBLISH_BEGIN,H_PUBLISH_OK,H_COMMIT,
 H_RELEASE_BEGIN,H_ABORT_BEGIN,H_ABORT_OK,H_REACQUIRE,H_RECOVER_YES,H_RECOVER_NO};
typedef struct {unsigned event,seq;int publish_intent,published,committed,aborted;
 char lease[49],stage[49],snap[65],content[65],prev[65],bind[65];} history;
struct wh_session {wh_binding b;wh_gates g;wh_provider p;wh_append_verify sink;void *sink_context,*cap;
 history h;char live_lease[49],live_stage[49];int used,poisoned;char manifest[EXR_WH_LINE_MAX];};
static int hx(const char *s,size_t n){size_t i;for(i=0;i<n;i++)if(!((s[i]>='0'&&s[i]<='9')||(s[i]>='a'&&s[i]<='f')))return 0;
 return !s[n];}
static int gates(const wh_gates *g){return g&&hx(g->admission,64)&&hx(g->publisher,64)&&hx(g->recovery,64)&&hx(g->observer,64)&&hx(g->fault,64);}
int wh_manifest(const wh_binding *b,const wh_gates *g,char out[EXR_WH_LINE_MAX]){
 int n;
 if(!b||!out||!wh_binding_valid(b)||!gates(g))return 0;
 n=snprintf(out,EXR_WH_LINE_MAX,"EXRWH2|source=%s|run=%s|attempt=%s|artifact=%s|platform=%s|sdk=%s|provider=%s|admission=%s|publisher=%s|recovery=%s|observer=%s|fault=%s",
 b->source,b->run,b->attempt,b->artifact,b->platform,b->sdk,b->provider,g->admission,g->publisher,g->recovery,g->observer,g->fault);
 return n>0&&(size_t)n<EXR_WH_LINE_MAX;
}
static int ready(const wh_session *s){
 const wh_provider *p=&s->p;
 return p->abi==EXR_WH_ABI&&p->identity_sha&&!strcmp(p->identity_sha,s->b.provider)&&
 p->acquire&&p->reacquire&&p->check&&p->snapshot&&p->import_rows&&p->verify&&p->publish&&p->inspect&&p->discard&&p->release&&s->sink;
}
static wh_status report(wh_session *s,wh_report *r,wh_status status,const char *why){
 if(!r)return WH_INTERNAL;
 memset(r,0,sizeof(*r));r->status=status;
 if(s){r->seq=s->h.seq;r->live_lease=s->cap!=NULL;r->poisoned=s->poisoned;
 memcpy(r->lease,s->live_lease[0]?s->live_lease:s->h.lease,49);memcpy(r->staged,s->live_stage[0]?s->live_stage:s->h.stage,49);
 memcpy(r->snapshot,s->h.snap,65);memcpy(r->content,s->h.content,65);}
 snprintf(r->detail,sizeof(r->detail),"%s",why);
 return status;
}
static int same(const char *a,const char *b){return !strcmp(a,b);}
static int transition(history *h,unsigned e,const char *lease,const char *stage,const char *snap,const char *content){
 unsigned old=h->event;int allow=0;
 if(e<H_ADMIT_BEGIN||e>H_RECOVER_NO)return 0;
 if(e==H_REACQUIRE)allow=1;
 else if(e==H_RECOVER_YES)allow=old==H_REACQUIRE&&h->publish_intent&&!h->aborted;
 else if(e==H_RECOVER_NO)allow=old==H_REACQUIRE&&!h->published&&!h->committed;
 else if(e==H_COMMIT)allow=old==H_PUBLISH_OK||old==H_RECOVER_YES;
 else if(e==H_RELEASE_BEGIN)allow=old==H_COMMIT||old==H_ABORT_OK;
 else if(e==H_ABORT_BEGIN)allow=old==H_ADMIT_OK||old==H_SNAP_BEGIN||old==H_SNAP_OK||old==H_IMPORT_BEGIN||old==H_IMPORT_OK||old==H_VERIFY_BEGIN||old==H_VERIFY_OK||old==H_PUBLISH_BEGIN||old==H_RECOVER_NO;
 else if(e==H_ABORT_OK)allow=old==H_ABORT_BEGIN;
 else if(e<=H_PUBLISH_OK)allow=e==old+1;
 if(!allow)return 0;
 if(e==H_ADMIT_OK||e==H_REACQUIRE){
  if(!hx(lease,48)||(h->lease[0]&&!same(h->lease,lease)))return 0;
 }else if(!same(lease,h->lease))return 0;
 if(e==H_IMPORT_OK){if(!hx(stage,48)||h->stage[0])return 0;}
 else if(!same(stage,h->stage))return 0;
 if(e==H_SNAP_OK){if(!hx(snap,64)||h->snap[0])return 0;}
 else if(!same(snap,h->snap))return 0;
 if(e==H_IMPORT_BEGIN){if(!hx(content,64)||h->content[0])return 0;}
 else if(!same(content,h->content))return 0;
 if(e==H_RECOVER_YES&&(!hx(stage,48)||!hx(content,64)))return 0;
 memcpy(h->lease,lease,49);memcpy(h->stage,stage,49);memcpy(h->snap,snap,65);memcpy(h->content,content,65);
 h->event=e;
 if(e==H_PUBLISH_BEGIN)h->publish_intent=1;
 if(e==H_PUBLISH_OK||e==H_RECOVER_YES)h->published=1;
 if(e==H_COMMIT)h->committed=1;
 if(e==H_ABORT_OK)h->aborted=1;
 return 1;
}
static const char *value(const char *s){return *s?s:"-";}
static int make_line(const history *h,unsigned event,const char *lease,const char *stage,const char *snap,const char *content,char out[EXR_WH_LINE_MAX]){
 char seal[65];int n=snprintf(out,EXR_WH_LINE_MAX,"EXRWH2 %u %u %s %s %s %s %s %s",h->seq,event,value(lease),value(stage),value(snap),value(content),h->prev,h->bind);
 if(n<=0||(size_t)n>=EXR_WH_LINE_MAX-66)return 0;
 wh_sha256_hex(out,(size_t)n,seal);strcat(out," ");strcat(out,seal);
 return 1;
}
static int append_event(wh_session *s,unsigned event,const char *lease,const char *stage,const char *snap,const char *content){
 history next=s->h;char line[EXR_WH_LINE_MAX];
 if(s->poisoned)return 0;
 if(s->h.seq>=EXR_WH_MAX_JOURNAL||!transition(&next,event,lease,stage,snap,content)||!make_line(&s->h,event,lease,stage,snap,content,line)){s->poisoned=1;
 return 0;}
 if(s->sink(s->sink_context,line)){s->poisoned=1;
 return 0;}
 memcpy(next.prev,line+strlen(line)-64,65);next.seq++;s->h=next;
 return 1;
}
#define EVENT(s,e) append_event((s),(e),(s)->h.lease,(s)->h.stage,(s)->h.snap,(s)->h.content)
static int parse(history *h,const char *line){
 unsigned seq,event;char lease[49]={0},stage[49]={0},snap[65]={0},content[65]={0},prev[65]={0},bind[65]={0},seal[65]={0},tail,canonical[EXR_WH_LINE_MAX];
 history next=*h;int n;
 if(!line)return 0;
 n=sscanf(line,"EXRWH2 %u %u %48s %48s %64s %64s %64s %64s %64s %c",&seq,&event,lease,stage,snap,content,prev,bind,seal,&tail);
 if(n!=9||seq!=h->seq||!same(prev,h->prev)||!same(bind,h->bind)||!hx(seal,64))return 0;
 if(same(lease,"-"))lease[0]=0;
 if(same(stage,"-"))stage[0]=0;
 if(same(snap,"-"))snap[0]=0;
 if(same(content,"-"))content[0]=0;
 if(!transition(&next,event,lease,stage,snap,content)||!make_line(h,event,lease,stage,snap,content,canonical)||strcmp(canonical,line))return 0;
 memcpy(next.prev,seal,65);next.seq++;*h=next;
 return 1;
}
static int load_history(const wh_binding *b,const wh_gates *g,const char *const *lines,size_t n,history *h){
 char manifest[EXR_WH_LINE_MAX];size_t i;
 memset(h,0,sizeof(*h));
 if(!lines||!n||n>EXR_WH_MAX_JOURNAL||!wh_manifest(b,g,manifest)||!lines[0]||strcmp(lines[0],manifest))return 0;
 wh_sha256_hex(manifest,strlen(manifest),h->bind);memcpy(h->prev,h->bind,65);h->seq=1;
 for(i=1;i<n;i++){if(!parse(h,lines[i]))return 0;}
 return 1;
}
int wh_journal_check(const wh_binding *b,const wh_gates *g,const char *const *lines,size_t n){history h;
 return load_history(b,g,lines,n,&h);}
wh_session *wh_create(const wh_binding *b,const wh_gates *g,const wh_provider *p,wh_append_verify sink,void *ctx){
 wh_session *s;
 if(!b||!g||!p)return NULL;
 s=calloc(1,sizeof(*s));
 if(!s)return NULL;
 if(!wh_manifest(b,g,s->manifest)){free(s);
 return NULL;}
 s->b=*b;s->g=*g;s->p=*p;s->sink=sink;s->sink_context=ctx;
 return s;
}
int wh_dispose(wh_session *s){if(!s)return 1;
 if(s->cap||s->poisoned)return 0;
 free(s);
 return 1;}
static wh_status uncertain(wh_session *s,wh_report *r,const char *why){return report(s,r,WH_UNCERTAIN,why);}
static int checked(wh_session *s){return s->cap&&s->p.check(s->p.context,s->cap)==WH_STEP_OK;}
static wh_status release_terminal(wh_session *s,wh_report *r,int committed){
 if(!checked(s))return uncertain(s,r,"lease-check-before-release-intent-failed");
 if(!EVENT(s,H_RELEASE_BEGIN))return uncertain(s,r,"journal-release-intent-failed");
 if(!checked(s))return uncertain(s,r,"lease-check-before-release-failed");
 if(s->p.release(s->p.context,s->cap)!=WH_STEP_OK)return report(s,r,WH_LEASE_RETAINED,"release-unconfirmed-capability-retained");
 s->cap=NULL;
 return report(s,r,committed?WH_COMPLETED:WH_ROLLED_BACK,committed?"durable-commit-then-release":"durable-abort-then-release");
}
static wh_status abort_known(wh_session *s,wh_report *r){
 if(!EVENT(s,H_ABORT_BEGIN))return uncertain(s,r,"journal-abort-intent-failed");
 if(!checked(s))return uncertain(s,r,"lease-check-before-discard-failed");
 if(s->h.stage[0]&&s->p.discard(s->p.context,s->cap,s->h.stage)!=WH_STEP_OK)return uncertain(s,r,"discard-unconfirmed");
 if(!checked(s))return uncertain(s,r,"lease-check-before-abort-terminal-failed");
 if(!EVENT(s,H_ABORT_OK))return uncertain(s,r,"journal-abort-failed");
 return release_terminal(s,r,0);
}
static wh_status commit_known(wh_session *s,wh_report *r){
 if(!checked(s))return uncertain(s,r,"lease-check-before-commit-failed");
 if(!EVENT(s,H_COMMIT))return uncertain(s,r,"journal-commit-failed");
 return release_terminal(s,r,1);
}
static int acquire(wh_session *s,int recovery,char actual[49]){
 wh_step step;
 if(recovery)step=s->p.reacquire(s->p.context,&s->b,&s->g,s->h.lease,&s->cap,actual);
 else step=s->p.acquire(s->p.context,&s->b,&s->g,&s->cap,actual);
 if(hx(actual,48))memcpy(s->live_lease,actual,49);
 if(step!=WH_STEP_OK)return step==WH_STEP_FAILED&&!s->cap?0:-1;
 if(!s->cap||!hx(actual,48)||(s->h.lease[0]&&!same(actual,s->h.lease))||!checked(s))return -1;
 return 1;
}
wh_status wh_run(wh_session *s,wh_report *r){
 wh_record *rows;size_t n=0;char actual[49]={0},stage[49]={0},snap[65]={0},content[65]={0};
 wh_step step;wh_pub pub=WH_PUB_UNKNOWN;wh_status result;int ac;
 if(!s||!r)return WH_INTERNAL;
 if(s->used||s->poisoned)return uncertain(s,r,"session-already-used");
 if(!ready(s))return report(s,r,WH_PENDING,"provider-contract-incomplete");
 s->used=1;
 ac=acquire(s,0,actual);
 if(ac<=0)return report(s,r,ac?WH_UNCERTAIN:WH_REFUSED,"admission-not-proven");
 if(s->sink(s->sink_context,s->manifest)){s->poisoned=1;
 return uncertain(s,r,"manifest-write-failed");}
 wh_sha256_hex(s->manifest,strlen(s->manifest),s->h.bind);memcpy(s->h.prev,s->h.bind,65);s->h.seq=1;
 if(!EVENT(s,H_ADMIT_BEGIN))return uncertain(s,r,"journal-admit-intent-failed");
 if(!append_event(s,H_ADMIT_OK,actual,s->h.stage,s->h.snap,s->h.content))return uncertain(s,r,"journal-admission-failed-capability-retained");
 rows=calloc(EXR_WH_MAX_RECORDS,sizeof(*rows));
 if(!rows)return uncertain(s,r,"allocation-failed-capability-retained");
#define STOP(why) do{free(rows);return uncertain(s,r,why);}while(0)
 if(!EVENT(s,H_SNAP_BEGIN)||!checked(s))STOP("snapshot-intent-or-lease-failed");
 step=s->p.snapshot(s->p.context,s->cap,rows,EXR_WH_MAX_RECORDS,&n);
 if(step==WH_STEP_FAILED){free(rows);
 return abort_known(s,r);}
 if(step!=WH_STEP_OK||!wh_snapshot_digest(&s->b,rows,n,snap)||!wh_content_digest(rows,n,content))STOP("snapshot-uncertain-or-invalid");
 if(!append_event(s,H_SNAP_OK,s->h.lease,s->h.stage,snap,s->h.content))STOP("snapshot-journal-failed");
 if(!append_event(s,H_IMPORT_BEGIN,s->h.lease,s->h.stage,s->h.snap,content)||!checked(s))STOP("import-intent-or-lease-failed");
 step=s->p.import_rows(s->p.context,s->cap,rows,n,stage);
 if(hx(stage,48))memcpy(s->live_stage,stage,49);
 if(step==WH_STEP_FAILED&&!stage[0]){free(rows);
 return abort_known(s,r);}
 if(step!=WH_STEP_OK||!hx(stage,48))STOP("import-uncertain-or-contradictory");
 if(!append_event(s,H_IMPORT_OK,s->h.lease,stage,s->h.snap,s->h.content))STOP("import-journal-failed");
 if(!EVENT(s,H_VERIFY_BEGIN)||!checked(s))STOP("verify-intent-or-lease-failed");
 step=s->p.verify(s->p.context,s->cap,s->h.stage,rows,n);
 if(step==WH_STEP_FAILED){free(rows);
 return abort_known(s,r);}
 if(step!=WH_STEP_OK)STOP("verify-uncertain");
 if(!EVENT(s,H_VERIFY_OK))STOP("verify-journal-failed");
 free(rows);
#undef STOP
 if(!EVENT(s,H_PUBLISH_BEGIN)||!checked(s))return uncertain(s,r,"publish-intent-or-lease-failed");
 step=s->p.publish(s->p.context,s->cap,s->h.stage,&pub);
 if(step==WH_STEP_OK&&pub==WH_PUB_YES){
  if(!EVENT(s,H_PUBLISH_OK))return uncertain(s,r,"published-journal-failed");
  return commit_known(s,r);
 }
 if((step==WH_STEP_OK||step==WH_STEP_FAILED)&&pub==WH_PUB_NO)result=abort_known(s,r);
 else result=uncertain(s,r,"publish-uncertain-or-contradictory");
 return result;
}
wh_status wh_recover(wh_session *s,const char *const *lines,size_t n,wh_report *r){
 char actual[49]={0};wh_pub pub=WH_PUB_UNKNOWN;wh_step step;int ac;
 if(!s||!r)return WH_INTERNAL;
 if(s->used||s->poisoned)return uncertain(s,r,"session-already-used");
 if(!ready(s))return report(s,r,WH_PENDING,"provider-contract-incomplete");
 if(!load_history(&s->b,&s->g,lines,n,&s->h))return report(s,r,WH_REFUSED,"journal-fsm-or-binding-invalid");
 s->used=1;ac=acquire(s,1,actual);
 if(ac<=0)return report(s,r,ac?WH_UNCERTAIN:WH_REFUSED,"fresh-exclusive-reacquire-not-proven");
 if(!append_event(s,H_REACQUIRE,actual,s->h.stage,s->h.snap,s->h.content))return uncertain(s,r,"reacquire-journal-failed-capability-retained");
 if(!checked(s))return uncertain(s,r,"fresh-lease-lost-before-inspect");
 step=s->p.inspect(s->p.context,s->cap,s->h.stage,s->h.content,&pub);
 if(step!=WH_STEP_OK)return uncertain(s,r,"restart-inspection-uncertain");
 if(pub==WH_PUB_YES&&s->h.publish_intent&&!s->h.aborted&&hx(s->h.stage,48)&&hx(s->h.content,64)){
  if(!EVENT(s,H_RECOVER_YES))return uncertain(s,r,"restart-confirmation-journal-failed");
  return commit_known(s,r);
 }
 if(pub==WH_PUB_NO&&!s->h.published&&!s->h.committed){
  if(!EVENT(s,H_RECOVER_NO))return uncertain(s,r,"restart-abort-confirmation-journal-failed");
  return abort_known(s,r);
 }
 return uncertain(s,r,"restart-contradiction-or-unknown");
}
