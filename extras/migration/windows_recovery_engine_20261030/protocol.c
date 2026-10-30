/* SPDX-License-Identifier: MIT */
#include "protocol.h"
#include <string.h>
#include <stdlib.h>
static int hx(const char *s,size_t cap,size_t n){
 return memchr(s,0,cap)==s+n&&strspn(s,"0123456789abcdef")==n;
}
int lm_we_request_valid(const lm_we_request *r){
 return !memcmp(r->magic,"EXRWINOBSERVE1",14)&&r->magic[14]==0&&r->magic[15]==0&&
 hx(r->source,sizeof(r->source),40)&&!strcmp(r->source,LM_WE_SOURCE)&&
 hx(r->nonce,sizeof(r->nonce),32)&&hx(r->root,sizeof(r->root),48)&&
 hx(r->parent,sizeof(r->parent),48)&&hx(r->target,sizeof(r->target),48)&&
 hx(r->worker_sha,sizeof(r->worker_sha),64);
}
int lm_we_hash(HANDLE h,char sha[65],wr_identity *identity,wr_error *e){
 wr_identity before,after;void *bytes=NULL;size_t size=0;
 if(!wr_identity_get(h,0,&before,e)||!wr_read(h,&bytes,&size,LM_WE_LIMIT,e))return 0;
 lm_sha_bytes(bytes,size,sha);free(bytes);
 if(!wr_identity_get(h,0,&after,e)||!wr_identity_equal(&before,&after)||
 before.size!=after.size||after.size!=size){if(e)e->reason="observer-identity-change";return 0;}
 *identity=after;return 1;
}
