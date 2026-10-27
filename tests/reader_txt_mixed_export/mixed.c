/* SPDX-License-Identifier: MIT */
#include <reader_original_export.h>
#include <stdio.h>
#include <string.h>
#include <stdint.h>

static int held=0,releases=0;
static int enter(void *p){(void)p;if(held)return 1;held=1;return 0;}
static void leave(void *p){(void)p;held=0;}
static size_t read_short(void *p,uint64_t off,void *out,size_t size){
  const char *text=(const char *)p;
  if(off>=3||!size)return 0;
  *(char *)out=text[(size_t)off];return 1;
}
static void release_borrowed(void *p){(void)p;releases++;}
static int cancelled(void *p){(void)p;return 1;}
int main(int argc,char **argv){
  const char *good="ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad";
  const char *bad="0000000000000000000000000000000000000000000000000000000000000000";
  exr_library *lib=NULL;exr_error error={0};roe_exporter *e=NULL;roe_owner owner={enter,leave,NULL};
  exr_source source={0};roe_mixed_selection selected[2]={0};roe_options options={0};
  roe_result *r=NULL;roe_status st;int64_t id=0;FILE *f;char bytes[4]={0};
  if(argc!=2)return 1;
  if(exr_library_open(":memory:",&lib,&error)!=EXR_OK)return 2;
  if(exr_library_import(lib,EXR_TXT,"SDK original",12,"SDK",&id,&error)!=EXR_OK)return 3;
  if(roe_create(lib,&owner,&e)!=ROE_OK)return 4;
  source.size=3;source.context=(void *)"abc";source.read_at=read_short;source.release=release_borrowed;
  selected[0].source=&source;selected[0].format=EXR_TXT;selected[0].expected_sha256=bad;
  selected[1].book_id=id;options.directory=argv[1];options.naming=ROE_HASH_NAME;
  st=roe_run_mixed(e,selected,2,&options,&r);
  if(st!=ROE_SOURCE||!r||r->items[0].committed||r->items[0].cleanup_pending||r->items[1].status!=ROE_PENDING)return 5;
  roe_result_free(r);r=NULL;selected[0].expected_sha256=good;
  st=roe_run_mixed(e,selected,2,&options,&r);
  if(st!=ROE_OK||!r||r->count!=2||!r->items[0].created||!r->items[1].created||
     strcmp(r->items[0].original_sha256,good)||r->items[1].book_id!=id)return 6;
  f=fopen(r->items[0].output_path,"rb");if(!f)return 7;
  if(fread(bytes,1,3,f)!=3||memcmp(bytes,"abc",3)||fgetc(f)!=EOF)return 8;
  fclose(f);roe_result_free(r);r=NULL;
  st=roe_run_mixed(e,selected,2,&options,&r);
  if(st!=ROE_OK||!r||r->items[0].created||r->items[1].created||!r->items[0].committed||!r->items[1].committed)return 9;
  roe_result_free(r);r=NULL;options.callbacks.cancelled=cancelled;
  st=roe_run_mixed(e,selected,2,&options,&r);
  if(st!=ROE_CANCELLED||!r||r->items[0].committed||r->items[1].committed)return 10;
  roe_result_free(r);
  if(held||releases||roe_destroy(&e)!=ROE_OK)return 11;
  exr_library_close(lib);
  puts("mixed export: identity mismatch, short reads, SDK coexistence, exact bytes, duplicates and cancellation passed");
  return 0;
}
