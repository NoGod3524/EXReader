/* SPDX-License-Identifier: MIT
 * Native installed-consumer checks; never compiled into the candidate library. */
#include "lm_recovery_win32_record.h"
#include <stdlib.h>
#include <string.h>
#include <stdio.h>
static wr_error error={0,"none"};
static unsigned checks;
#define CHECK(x) do { if(!(x)){fprintf(stderr,"check %u line %d: %s (%s, native=%lu)\n",checks+1,__LINE__,#x,error.reason?error.reason:"none",error.native);return 2;}checks++; } while(0)
int wmain(int argc,wchar_t **argv) {
  wr_context *c;wr_identity target_id,record_id,read_id,changed;lm_wr_record r={0},decoded,bad,next;
  HANDLE target=INVALID_HANDLE_VALUE,record=INVALID_HANDLE_VALUE,read=INVALID_HANDLE_VALUE,temp=INVALID_HANDLE_VALUE;
  lm_sb bytes,scratch;char *copy,*version;size_t n;
  const char posix_record[]="{\"magic\":\"EXRRECOVERY1\"}\n";
  const char mirror_record[]="{\"version\":3,\"format\":\"exreader-mirror-intent\"}\n";
  if(argc!=2)return 2;c=calloc(1,sizeof(*c));if(!c)return 2;lm_sb_init(&bytes);lm_sb_init(&scratch);
  CHECK(sizeof(r.target)==49&&sizeof(r.root)==49&&sizeof(r.previous_id)==49);
  CHECK(wr_prepare(c,argv[1],1,&error));
  CHECK(wr_write_new(c,L"target.fixture","disposable record-format fixture",32,1,&target,&error));
  CHECK(wr_identity_get(target,0,&target_id,&error));
  strcpy(r.source,CANDIDATE_SOURCE_SHA);strcpy(r.run,"11111111111111111111111111111111");
  wr_identity_text(&c->root,r.root);wr_identity_text(&c->identities[c->count-2],r.parent);wr_identity_text(&target_id,r.target);
  lm_sha_bytes("payload",7,r.payload_sha);
  CHECK(lm_wr_record_encode(&r,&bytes));
  CHECK(lm_wr_record_decode(bytes.p,bytes.n,&decoded)&&!strcmp(decoded.target,r.target)&&!strcmp(decoded.root,r.root));
  copy=malloc(bytes.n+2);if(!copy)return 2;memcpy(copy,bytes.p,bytes.n);n=bytes.n;
  copy[n-5]=copy[n-5]=='0'?'1':'0';CHECK(!lm_wr_record_decode(copy,n,&decoded)&&!decoded.source[0]);memcpy(copy,bytes.p,n);
  copy[n-1]=' ';copy[n]='\n';CHECK(!lm_wr_record_decode(copy,n+1,&decoded));
  CHECK(!lm_wr_record_decode(posix_record,sizeof(posix_record)-1,&decoded));
  bad=r;bad.target[32]=0;CHECK(!lm_wr_record_encode(&bad,&scratch));
  bad=r;bad.target[0]='A';CHECK(!lm_wr_record_encode(&bad,&scratch));
  bad=r;memset(bad.target,'1',sizeof(bad.target));CHECK(!lm_wr_record_encode(&bad,&scratch));
  CHECK(lm_wr_record_write(c,L"record-00.json",target,&r,&record,&record_id,&error));
  CHECK(!lm_wr_record_write(c,L"record-00.json",target,&r,&temp,&read_id,&error)&&temp==INVALID_HANDLE_VALUE);
  CHECK(lm_wr_record_read(c,L"record-00.json",target,&decoded,&read,&read_id,&error)&&wr_identity_equal(&record_id,&read_id)&&!strcmp(decoded.target,r.target));
  bad=r;bad.target[47]=bad.target[47]=='0'?'1':'0';CHECK(!lm_wr_record_write(c,L"foreign-record.json",target,&bad,&temp,&read_id,&error));
  next=r;next.ordinal=1;next.phase=1;wr_identity_text(&record_id,next.previous_id);lm_sha_bytes(bytes.p,bytes.n,next.previous_sha);
  CHECK(lm_wr_record_links(&next,&r,&record_id));
  changed=record_id;changed.file[15]^=1;CHECK(!lm_wr_record_links(&next,&r,&changed));
  bad=r;bad.payload_sha[0]=bad.payload_sha[0]=='0'?'1':'0';CHECK(!lm_wr_record_links(&next,&bad,&record_id));
  bad=next;bad.ordinal=2;CHECK(!lm_wr_record_links(&bad,&r,&record_id));
  bad=next;bad.source[39]=bad.source[39]=='0'?'1':'0';CHECK(!lm_wr_record_links(&bad,&r,&record_id));
  CHECK(!lm_wr_record_decode(mirror_record,sizeof(mirror_record)-1,&decoded));
  CHECK(!lm_wr_record_decode("",0,&decoded));
  memcpy(copy,bytes.p,n);copy[n]=0;version=strstr(copy,"\"version\":1");if(!version)return 2;version[10]='2';CHECK(!lm_wr_record_decode(copy,n,&decoded));
  CHECK(!lm_wr_record_decode(bytes.p,LM_WR_RECORD_MAX+1,&decoded));
  bad=r;bad.root[47]=bad.root[47]=='0'?'1':'0';CHECK(!lm_wr_record_write(c,L"foreign-root.json",target,&bad,&temp,&read_id,&error));
  CHECK(wr_identity_get(target,0,&changed,&error)&&wr_identity_equal(&changed,&target_id));
  printf("{\"source\":\"%s\",\"checks\":%u,\"expected\":27,\"passed\":%s,\"magic\":\"EXRWINRECOVERY1\",\"identity_bytes\":49,\"target\":\"%s\",\"record_bytes\":%zu,\"sdk_open_attempts\":0,\"recovery_admission\":false,\"directory_fsync_equivalent\":false}\n",CANDIDATE_SOURCE_SHA,checks,checks==27?"true":"false",r.target,bytes.n);
  free(copy);lm_sb_free(&bytes);lm_sb_free(&scratch);CloseHandle(read);CloseHandle(record);CloseHandle(target);wr_close(c);free(c);return checks==27?0:2;
}
