/* SPDX-License-Identifier: MIT */
#include "lm_recovery_win32_record.h"
#include <stdlib.h>
#include <string.h>
static int hex(const char *s,size_t capacity,size_t n) {
  size_t i;if(!s||n>=capacity)return 0;
  for(i=0;i<n;i++)if(!((s[i]>='0'&&s[i]<='9')||(s[i]>='a'&&s[i]<='f')))return 0;
  return s[n]==0;
}
static int valid(const lm_wr_record *r) {
  return r&&r->ordinal<32&&r->phase<9&&hex(r->source,sizeof(r->source),40)&&
    hex(r->run,sizeof(r->run),32)&&hex(r->root,sizeof(r->root),48)&&
    hex(r->parent,sizeof(r->parent),48)&&hex(r->target,sizeof(r->target),48)&&
    hex(r->payload_sha,sizeof(r->payload_sha),64)&&
    (r->ordinal?(hex(r->previous_id,sizeof(r->previous_id),48)&&hex(r->previous_sha,sizeof(r->previous_sha),64)):
                (!r->previous_id[0]&&!r->previous_sha[0]));
}
static void body(const lm_wr_record *r,lm_sb *b) {
  lm_sb_fmt(b,"{\"magic\":\"EXRWINRECOVERY1\",\"version\":1,\"ordinal\":%u,\"phase\":%u,\"source\":\"%s\",\"run\":\"%s\",\"root\":\"%s\",\"parent\":\"%s\",\"target\":\"%s\",\"previous_id\":\"%s\",\"previous_sha\":\"%s\",\"payload_sha\":\"%s\"}\n",
    r->ordinal,r->phase,r->source,r->run,r->root,r->parent,r->target,r->previous_id,r->previous_sha,r->payload_sha);
}
int lm_wr_record_encode(const lm_wr_record *r,lm_sb *b) {
  char seal[65];if(!b||b->n||b->oom||!valid(r))return 0;
  body(r,b);if(b->oom||b->n<2||b->n>LM_WR_RECORD_MAX)return 0;
  lm_sha_bytes(b->p,b->n,seal);b->n-=2;b->p[b->n]=0;
  lm_sb_fmt(b,",\"seal\":\"%s\"}\n",seal);return !b->oom&&b->n<=LM_WR_RECORD_MAX;
}
static int field(const jv *j,const char *key,char *out,size_t capacity) {
  const jv *v=lm_get(j,key);if(!v||v->t!=J_STR||v->n>=capacity||strlen(v->s)!=v->n)return 0;
  memcpy(out,v->s,v->n+1);return 1;
}
int lm_wr_record_decode(const void *bytes,size_t size,lm_wr_record *out) {
  jv *j=NULL;lm_wr_record r={0};lm_sb canonical;char error[128],magic[32];uint64_t n;int ok=0;
  if(!out)return 0;memset(out,0,sizeof(*out));lm_sb_init(&canonical);
  if(!bytes||!size||size>LM_WR_RECORD_MAX||memchr(bytes,0,size))goto done;
  j=lm_json_parse(bytes,size,error,sizeof(error));
  if(!j||j->t!=J_OBJ||j->n!=13||!field(j,"magic",magic,sizeof(magic))||strcmp(magic,"EXRWINRECOVERY1")||
     !lm_json_uint(lm_get(j,"version"),&n)||n!=1||!lm_json_uint(lm_get(j,"ordinal"),&n)||n>=32)goto done;
  r.ordinal=(unsigned)n;if(!lm_json_uint(lm_get(j,"phase"),&n)||n>=9)goto done;r.phase=(unsigned)n;
  if(!field(j,"source",r.source,sizeof(r.source))||!field(j,"run",r.run,sizeof(r.run))||
     !field(j,"root",r.root,sizeof(r.root))||!field(j,"parent",r.parent,sizeof(r.parent))||
     !field(j,"target",r.target,sizeof(r.target))||!field(j,"previous_id",r.previous_id,sizeof(r.previous_id))||
     !field(j,"previous_sha",r.previous_sha,sizeof(r.previous_sha))||!field(j,"payload_sha",r.payload_sha,sizeof(r.payload_sha))||
     !lm_wr_record_encode(&r,&canonical)||canonical.n!=size||memcmp(canonical.p,bytes,size))goto done;
  *out=r;ok=1;
done:lm_json_free(j);lm_sb_free(&canonical);return ok;
}
int lm_wr_record_links(const lm_wr_record *next,const lm_wr_record *previous,
                      const wr_identity *id) {
  char identity[49],sha[65];lm_sb b;int ok;
  if(!valid(next)||!valid(previous)||!id)return 0;lm_sb_init(&b);
  if(!lm_wr_record_encode(previous,&b)){lm_sb_free(&b);return 0;}
  lm_sha_bytes(b.p,b.n,sha);lm_sb_free(&b);
  wr_identity_text(id,identity);
  ok=next->ordinal==previous->ordinal+1&&!strcmp(next->previous_id,identity)&&!strcmp(next->previous_sha,sha)&&
    !strcmp(next->source,previous->source)&&!strcmp(next->run,previous->run)&&
    !strcmp(next->root,previous->root)&&!strcmp(next->parent,previous->parent)&&!strcmp(next->target,previous->target);
  return ok;
}
static int refuse(wr_error *e,const char *reason) {
  SetLastError(ERROR_INVALID_DATA);if(e){e->native=ERROR_INVALID_DATA;e->reason=reason;}return 0;
}
static int bound(wr_context *c,HANDLE target,const lm_wr_record *r,wr_error *e) {
  wr_identity actual;char id[49];if(!valid(r)||!c||c->count<2||!wr_recheck(c,e))return refuse(e,"windows-record-context");
  wr_identity_text(&c->root,id);if(strcmp(id,r->root))return refuse(e,"windows-record-root");
  wr_identity_text(&c->identities[c->count-2],id);if(strcmp(id,r->parent))return refuse(e,"windows-record-parent");
  if(!wr_identity_get(target,0,&actual,e))return 0;wr_identity_text(&actual,id);
  return !strcmp(id,r->target)?1:refuse(e,"windows-record-target");
}
int lm_wr_record_write(wr_context *c,const WCHAR *leaf,HANDLE target,const lm_wr_record *r,
                       HANDLE *retained,wr_identity *observed,wr_error *e) {
  lm_sb b;HANDLE h=INVALID_HANDLE_VALUE;int ok=0;
  if(!retained||!observed)return refuse(e,"windows-record-output");*retained=INVALID_HANDLE_VALUE;memset(observed,0,sizeof(*observed));lm_sb_init(&b);
  if(!bound(c,target,r,e)||!lm_wr_record_encode(r,&b))goto done;
  if(!wr_write_new(c,leaf,b.p,b.n,1,&h,e)||!wr_identity_get(h,0,observed,e)||!bound(c,target,r,e))goto done;
  *retained=h;h=INVALID_HANDLE_VALUE;ok=1;
done:if(h!=INVALID_HANDLE_VALUE)CloseHandle(h);if(!ok)memset(observed,0,sizeof(*observed));lm_sb_free(&b);return ok;
}
int lm_wr_record_read(wr_context *c,const WCHAR *leaf,HANDLE target,lm_wr_record *r,
                      HANDLE *retained,wr_identity *observed,wr_error *e) {
  HANDLE h=INVALID_HANDLE_VALUE;void *bytes=NULL;size_t size=0;int ok=0;
  if(!r||!retained||!observed)return refuse(e,"windows-record-output");memset(r,0,sizeof(*r));*retained=INVALID_HANDLE_VALUE;memset(observed,0,sizeof(*observed));
  h=wr_open(c,leaf,GENERIC_READ,FILE_SHARE_READ|FILE_SHARE_WRITE|FILE_SHARE_DELETE,0,e);if(h==INVALID_HANDLE_VALUE)goto done;
  if(!wr_read(h,&bytes,&size,LM_WR_RECORD_MAX,e))goto done;
  if(!lm_wr_record_decode(bytes,size,r)){refuse(e,"windows-record-format");goto done;}
  if(!wr_identity_get(h,0,observed,e)||!bound(c,target,r,e))goto done;
  *retained=h;h=INVALID_HANDLE_VALUE;ok=1;
done:if(h!=INVALID_HANDLE_VALUE)CloseHandle(h);if(!ok){memset(r,0,sizeof(*r));memset(observed,0,sizeof(*observed));}free(bytes);return ok;
}
