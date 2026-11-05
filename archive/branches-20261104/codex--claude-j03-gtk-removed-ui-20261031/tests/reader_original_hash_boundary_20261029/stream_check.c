/* Actions-only controls; never compiled into an installed owner. */
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <string.h>
#include <opds_sha256_stream.h>
static void require(int ok, const char *message) {
  if (!ok) { fprintf(stderr, "FAIL %s\n", message); exit(1); }
}
#ifdef STREAM_INTERNAL_TEST
static int fail_allocation;
static size_t allocations, releases, largest;
static void *checked_calloc(size_t n, size_t size) {
  void *p;
  if (fail_allocation) return NULL;
  require(!n || size <= SIZE_MAX/n, "allocation multiplication");
  if (n*size > largest) largest=n*size;
  p=calloc(n,size); if(p) ++allocations; return p;
}
static void checked_free(void *p) { if(p) ++releases; free(p); }
#define calloc checked_calloc
#define free checked_free
#include STREAM_PROVIDER_SOURCE
#undef calloc
#undef free
#else
/* Public one-shot oracle, linked from either normal OPDS or the unchanged
 * actual reader_revision_hash target. Never granted to production consumer. */
#include <opds.h>
#endif
static void vector(size_t n, size_t fragment) {
  unsigned char *bytes=(unsigned char *)malloc(n ? n : 1);
  opds_sha256_stream *c=NULL;
  char digest[65]; size_t i;
  require(bytes!=NULL,"fixture memory");
  for(i=0;i<n;i++) bytes[i]=(unsigned char)((i*29u+7u)&255u);
  require(opds_sha256_stream_create(&c)==OPDS_SHA256_STREAM_OK && c,"create");
  require(opds_sha256_stream_update(c,NULL,0)==OPDS_SHA256_STREAM_OK,"zero");
  for(i=0;i<n;) {size_t take=n-i; if(take>fragment)take=fragment;
    require(opds_sha256_stream_update(c,bytes+i,take)==OPDS_SHA256_STREAM_OK,"update");i+=take;}
  require(opds_sha256_stream_finish_hex(c,digest)==OPDS_SHA256_STREAM_OK,"finish");
#ifndef STREAM_INTERNAL_TEST
  { char oracle[65]; opds_sha256_hex(bytes,n,oracle); require(!strcmp(digest,oracle),"normal owner oracle equality"); }
#endif
  printf("VECTOR %zu %zu %s\n",n,fragment,digest);
  require(opds_sha256_stream_update(c,bytes,0)==OPDS_SHA256_STREAM_STATE,"update after final");
  require(opds_sha256_stream_finish_hex(c,digest)==OPDS_SHA256_STREAM_STATE && !digest[0],"double final clears");
  opds_sha256_stream_destroy(&c); require(c==NULL,"destroy clears");
  opds_sha256_stream_destroy(&c); free(bytes);
}
int main(void) {
  static const size_t lengths[]={0,1,3,55,56,63,64,65,65535,65536,65537};
  static const size_t fragments[]={1,7,64,65536};
  opds_sha256_stream *c=NULL; char out[65]; size_t i,j;
  require(opds_sha256_stream_create(NULL)==OPDS_SHA256_STREAM_ARGUMENT,"null owner");
  require(opds_sha256_stream_update(NULL,NULL,0)==OPDS_SHA256_STREAM_ARGUMENT,"null context");
  memset(out,'x',sizeof out);
  require(opds_sha256_stream_finish_hex(NULL,out)==OPDS_SHA256_STREAM_ARGUMENT && !out[0],"null final clears");
  opds_sha256_stream_destroy(NULL);
  require(opds_sha256_stream_create(&c)==OPDS_SHA256_STREAM_OK,"argument create");
  require(opds_sha256_stream_update(c,NULL,1)==OPDS_SHA256_STREAM_ARGUMENT,"nonzero null");
  require(opds_sha256_stream_finish_hex(c,NULL)==OPDS_SHA256_STREAM_ARGUMENT,"null output");
  require(opds_sha256_stream_update(c,"abc",3)==OPDS_SHA256_STREAM_OK,"abc update");
  require(opds_sha256_stream_finish_hex(c,out)==OPDS_SHA256_STREAM_OK &&
    !strcmp(out,"ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"),"abc exact");
  opds_sha256_stream_destroy(&c);
  for(i=0;i<sizeof lengths/sizeof *lengths;i++)
    for(j=0;j<sizeof fragments/sizeof *fragments;j++) vector(lengths[i],fragments[j]);
#ifdef STREAM_INTERNAL_TEST
  fail_allocation=1; c=(opds_sha256_stream *)(uintptr_t)1;
  require(opds_sha256_stream_create(&c)==OPDS_SHA256_STREAM_MEMORY && !c,"allocation failure clears");
  fail_allocation=0;
  require(opds_sha256_stream_create(&c)==OPDS_SHA256_STREAM_OK,"overflow create");
  c->state.len=UINT64_MAX-1;
  { unsigned char before[sizeof *c]; memcpy(before,c,sizeof before);
    require(opds_sha256_stream_update(c,"ab",2)==OPDS_SHA256_STREAM_ARGUMENT,"overflow rejected");
    require(!memcmp(c,before,sizeof before),"overflow preserves complete state"); }
  require(opds_sha256_stream_update(c,"a",1)==OPDS_SHA256_STREAM_OK && c->state.len==UINT64_MAX,"last representable byte");
  opds_sha256_stream_destroy(&c);
  require(allocations==releases && largest<=256,"bounded contexts and lifetime");
  printf("INTERNAL allocations=%zu releases=%zu max=%zu\n",allocations,releases,largest);
#endif
  puts("STREAM_OK"); return 0;
}
