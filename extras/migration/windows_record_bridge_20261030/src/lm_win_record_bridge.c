/* SPDX-License-Identifier: MIT */
#include "lm_win_record_bridge.h"
#include <stdlib.h>
#include <string.h>
#include <wchar.h>
struct lm_rb {
 HANDLE target,slots[32];wr_identity target_id,root,parent,ids[32];
 unsigned count,next;int attempted[32];lm_wr_record session,records[32];
 lm_wp_custody *custody;wr_context acl;
};
static int refuse(wr_error *e,const char *s){
 SetLastError(ERROR_INVALID_DATA);if(e){e->native=ERROR_INVALID_DATA;e->reason=s;}return 0;
}
static int native(wr_error *e,const char *s){
 if(e){e->native=GetLastError();e->reason=s;}return 0;
}
static int identity_text(const wr_identity *id,const char *s){
 char text[49];wr_identity_text(id,text);return !strcmp(text,s);
}
static int target_check(lm_rb *b,wr_error *e){
 wr_identity id;void *bytes=NULL;size_t size=0;char sha[65];int ok;
 if(!wr_identity_get(b->target,0,&id,e)||!wr_identity_equal(&id,&b->target_id)||
    id.size!=b->target_id.size||!wr_private_acl(b->target,0,&b->acl,e))
  return refuse(e,"bridge-target-identity");
 if(!wr_read(b->target,&bytes,&size,WR_RECORD_MAX,e))return 0;
 lm_sha_bytes(bytes,size,sha);free(bytes);ok=!strcmp(sha,b->session.payload_sha);
 return ok?1:refuse(e,"bridge-target-hash");
}
static int custody_check(lm_rb *b,wr_error *e){
 wr_identity root,parent;
 if(!b->custody||!lm_wp_custody_identity(b->custody,&root,&parent,e)||
    !wr_identity_equal(&root,&b->root)||!wr_identity_equal(&parent,&b->parent))
  return refuse(e,"bridge-custody-binding");
 return target_check(b,e);
}
void lm_rb_close(lm_rb *b){
 unsigned i;if(!b)return;
 for(i=0;i<b->count;i++)CloseHandle(b->slots[i]);
 free(b);
}
int lm_rb_prepare(wr_context *c,HANDLE target,const lm_wr_record *s,
 unsigned slots,lm_rb **out,wr_error *e){
 lm_rb *b=NULL;lm_sb encoded;unsigned i;WCHAR leaf[40];
 unsigned char reservation[LM_WR_RECORD_MAX]={0};int ok=0;
 if(!out)return refuse(e,"bridge-output");*out=NULL;lm_sb_init(&encoded);
 if(!c||c->count<2||!s||s->ordinal||!slots||slots>32||
    !wr_recheck(c,e)||!lm_wr_record_encode(s,&encoded)){
  refuse(e,"bridge-prepare-arguments");goto done;
 }
 if(!identity_text(&c->root,s->root)||
    !identity_text(&c->identities[c->count-2],s->parent)){
  refuse(e,"bridge-original-binding");goto done;
 }
 b=calloc(1,sizeof(*b));if(!b){refuse(e,"bridge-allocation");goto done;}
 b->target=target;b->root=c->root;b->parent=c->identities[c->count-2];b->session=*s;
 memcpy(b->acl.user,c->user,sizeof(c->user));memcpy(b->acl.system,c->system,sizeof(c->system));
 if(!wr_identity_get(target,0,&b->target_id,e)||
    !identity_text(&b->target_id,s->target)||!target_check(b,e)){
  refuse(e,"bridge-target-binding");goto done;
 }
 for(i=0;i<slots;i++){
  HANDLE h=INVALID_HANDLE_VALUE;
  swprintf(leaf,40,L"bridge-slot-%02u.rec",i);
  if(!wr_write_new(c,leaf,reservation,sizeof(reservation),1,&h,e))goto done;
  b->slots[b->count++]=h;
  if(!wr_identity_get(h,0,&b->ids[i],e)||!wr_private_acl(h,0,c,e))goto done;
 }
 if(!wr_recheck(c,e)||!target_check(b,e))goto done;
 *out=b;b=NULL;ok=1;
done:lm_rb_close(b);lm_sb_free(&encoded);return ok;
}
int lm_rb_attach(lm_rb *b,lm_wp_custody *custody,wr_error *e){
 if(!b||b->custody||!custody)return refuse(e,"bridge-attach-arguments");
 b->custody=custody;
 if(!custody_check(b,e)){b->custody=NULL;return 0;}
 return 1;
}
static int same_session(const lm_wr_record *a,const lm_wr_record *b){
 return !strcmp(a->source,b->source)&&!strcmp(a->run,b->run)&&
 !strcmp(a->root,b->root)&&!strcmp(a->parent,b->parent)&&
 !strcmp(a->target,b->target)&&!strcmp(a->payload_sha,b->payload_sha);
}
static int slot_read(lm_rb *b,unsigned i,const lm_sb *expected,wr_error *e){
 void *bytes=NULL;size_t size=0;wr_identity id;lm_wr_record decoded;int ok=0;
 if(!wr_identity_get(b->slots[i],0,&id,e)||!wr_identity_equal(&id,&b->ids[i])||
    !wr_private_acl(b->slots[i],0,&b->acl,e))return refuse(e,"bridge-slot-identity");
 if(!wr_read(b->slots[i],&bytes,&size,LM_WR_RECORD_MAX,e))return 0;
 ok=size==expected->n&&!memcmp(bytes,expected->p,size)&&lm_wr_record_decode(bytes,size,&decoded);
 free(bytes);return ok?1:refuse(e,"bridge-slot-bytes");
}
int lm_rb_write_once(lm_rb *b,unsigned slot,const lm_wr_record *r,
 lm_rb_result *result,wr_error *e){
 lm_sb bytes,previous;LARGE_INTEGER at;size_t off=0;DWORD written;wr_identity id;int ok=0;
 if(!result)return refuse(e,"bridge-result");memset(result,0,sizeof(*result));
 lm_sb_init(&bytes);lm_sb_init(&previous);
 if(!b||!r||slot>=b->count||slot!=b->next||b->attempted[slot]||
    r->ordinal!=slot||!lm_wr_record_encode(r,&bytes)||!same_session(r,&b->session)){
  refuse(e,"bridge-write-arguments");goto done;
 }
 if(!custody_check(b,e))goto done;
 if(slot&&(!lm_wr_record_encode(&b->records[slot-1],&previous)||
    !slot_read(b,slot-1,&previous,e)||
    !lm_wr_record_links(r,&b->records[slot-1],&b->ids[slot-1]))){
  refuse(e,"bridge-predecessor");goto done;
 }
 if(!wr_identity_get(b->slots[slot],0,&id,e)||!wr_identity_equal(&id,&b->ids[slot])||
    id.size!=LM_WR_RECORD_MAX||!wr_private_acl(b->slots[slot],0,&b->acl,e)){
  refuse(e,"bridge-reservation");goto done;
 }
 /* From here on failure is uncertain and the slot can never be retried. */
 b->attempted[slot]=1;result->write_attempted=1;at.QuadPart=0;
 if(!SetFilePointerEx(b->slots[slot],at,NULL,FILE_BEGIN)){native(e,"bridge-seek");goto done;}
 while(off<bytes.n){
  if(!WriteFile(b->slots[slot],bytes.p+off,(DWORD)(bytes.n-off),&written,NULL)||!written){
   native(e,"bridge-write");goto done;
  }
  off+=written;
 }
 if(!SetEndOfFile(b->slots[slot])){native(e,"bridge-truncate");goto done;}
 if(!wr_flush(b->slots[slot],e))goto done;result->flushed=1;
 if(!slot_read(b,slot,&bytes,e)||!custody_check(b,e)||
    !wr_identity_get(b->slots[slot],0,&result->identity,e))goto done;
 lm_sha_bytes(bytes.p,bytes.n,result->sha);result->verified=1;
 b->records[slot]=*r;b->next++;ok=1;
done:lm_sb_free(&previous);lm_sb_free(&bytes);return ok;
}
