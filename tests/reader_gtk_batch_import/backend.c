/* SPDX-License-Identifier: MIT */
#define _POSIX_C_SOURCE 200809L
#include "../../examples/linux/reading.h"
#include "../../apps/reader/desktop/catalog_sdk.h"
#include <reader_batch_import.h>
#include <glib.h>
#include <glib/gstdio.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
static unsigned checks;
#define REQUIRE(test) do { checks++;if(!(test)) { fprintf(stderr,"check %u line %d: %s\n",checks,__LINE__,#test);exit(1); } } while(0)
static int cancelled(void *value) { return *(int *)value; }
static reader_command command(reader_action action) { reader_command value={0};value.action=action;value.font=24;value.zoom=100;return value; }
static void commit(linux_reader *reader,const reader_result *frame) {
  reader_command value=command(READER_COMMIT);value.book=frame->book;value.part=frame->part;value.page=frame->page;value.start=frame->start;
  reader_result result={0};linux_reader_execute(reader,&value,&result);REQUIRE(result.status==EXR_OK);reader_result_free(&result);
}
typedef struct { int64_t id;char key[73];uint64_t bytes; } mapping;
static int mapped(void *context,const reader_catalog_row *row) {
  mapping *value=context;value->id=row->sdk_book_id;value->bytes=row->source_bytes;g_strlcpy(value->key,row->book_key,sizeof(value->key));return 0;
}
static void inspect(const char *database,const char *output) {
  exr_library *library=NULL;exr_error error={0};exr_book *books=NULL;size_t count=0;reader_catalog *catalog=NULL;
  REQUIRE(exr_library_open(database,&library,&error)==EXR_OK);REQUIRE(exr_library_books(library,"",&books,&count,&error)==EXR_OK);
  char *product=g_strconcat(database,".product.sqlite",NULL);REQUIRE(reader_catalog_open(product,&catalog,NULL)==0);g_free(product);
  FILE *file=fopen(output,"w");REQUIRE(file!=NULL);
  fprintf(file,"# public original identity and stable product mapping\n");
  for(size_t i=0;i<count;i++) {
    char sha[65],key[73];uint64_t bytes=0;
    REQUIRE(reader_catalog_sdk_original_identity(library,books[i].id,NULL,sha,&bytes,&error)==EXR_OK);
    /* All own host fixtures are TXT; original installed-module suites cover nine formats. */
    REQUIRE(books[i].format==EXR_TXT);snprintf(key,sizeof(key),"txt:%s",sha);
    mapping value={0};int found=0;REQUIRE(reader_catalog_find(catalog,key,NULL,mapped,&value,&found,NULL)==0);
    REQUIRE(found && value.id==books[i].id && value.bytes==bytes && !strcmp(value.key,key));
    fprintf(file,"%lld\t%s\t%llu\t%zu\n",(long long)books[i].id,sha,(unsigned long long)bytes,books[i].position);
  }
  REQUIRE(!fclose(file));reader_catalog_close(&catalog,NULL);exr_books_free(books,count);exr_library_close(library);
}
static void run(linux_reader *reader,reader_command *value,reader_result *result) {
  linux_reader_execute(reader,value,result);
  if(result->status!=EXR_OK) fprintf(stderr,"batch action=%d status=%d: %s\n",value->action,result->status,result->message);
  REQUIRE(result->status==EXR_OK);REQUIRE(result->has_batch);REQUIRE(result->batch_count<=32);REQUIRE(!result->has_frame);
}
static void finish(linux_reader *reader,reader_command *value,reader_result *result) {
  for(unsigned step=0;!result->batch_done && step<1000;step++) {
    value->action=result->batch_map ? READER_BATCH_MAP:READER_BATCH_NEXT;reader_result_free(result);run(reader,value,result);
    if(value->action==READER_BATCH_MAP) for(size_t i=0;i<result->batch_count;i++)
      REQUIRE(!result->batch_rows[i].committed || result->batch_rows[i].mapped);
  }
  REQUIRE(result->batch_done);REQUIRE(result->batch_pending==0);
}
static void close_batch(linux_reader *reader,reader_command *value,reader_result *result) {
  reader_result_free(result);value->action=READER_BATCH_CLOSE;run(reader,value,result);REQUIRE(result->batch_done);reader_result_free(result);
}
int main(int argc,char **argv) {
  REQUIRE(argc==6);
  if(!strcmp(argv[5],"inspect")) { inspect(argv[1],argv[3]);printf("BATCH_INSPECT checks=%u\n",checks);return 0; }
  linux_reader *reader=NULL;int stale_reading=0;exr_control control={cancelled,NULL,&stale_reading};exr_error error={0};reader_result result={0};
  REQUIRE(linux_reader_open(argv[1],argv[2],&control,&reader,&error)==EXR_OK);
  char *root=g_build_filename(argv[3],"folder 书籍",NULL),*book=g_build_filename(root,"Book 00 文字.txt",NULL);
  reader_command initial=command(READER_IMPORT);initial.path=book;linux_reader_execute(reader,&initial,&result);
  REQUIRE(result.status==EXR_OK && result.has_frame);reader_result frame=result;memset(&result,0,sizeof(result));int64_t accepted=frame.book;
  reader_batch_control observe={.request=1};reader_command value=command(READER_BATCH_BEGIN);
  value.batch_root=root;value.batch_token=1;value.batch_control=&observe;value.batch_request=1;
  /* A rendered but uncommitted frame is a real import barrier. */
  run(reader,&value,&result);REQUIRE(result.batch_deferred && result.batch_attempted==0);reader_result_free(&result);commit(reader,&frame);reader_result_free(&frame);
  stale_reading=1;value.action=READER_BATCH_NEXT;run(reader,&value,&result);REQUIRE(result.batch_attempted==1);stale_reading=0;
  finish(reader,&value,&result);
  REQUIRE(result.batch_complete && !result.batch_truncated && !result.batch_cancelled);
  REQUIRE(result.batch_seen==37 && result.batch_attempted==37 && result.batch_imported==34 && result.batch_duplicates==2 && result.batch_failed==1);
  close_batch(reader,&value,&result);
  /* Reading still uses the accepted old source after repeated SQLite mutations. */
  reader_command reading=command(READER_FONT);reading.book=accepted;reading.font=26;linux_reader_execute(reader,&reading,&result);
  REQUIRE(result.status==EXR_OK && result.has_frame && result.book==accepted);commit(reader,&result);reader_result_free(&result);
  value.action=READER_BATCH_BEGIN;value.batch_token++;run(reader,&value,&result);finish(reader,&value,&result);
  REQUIRE(result.batch_imported==0 && result.batch_duplicates==36 && result.batch_failed==1);close_batch(reader,&value,&result);
  value.action=READER_BATCH_BEGIN;value.batch_token++;value.batch_candidate_limit=3;run(reader,&value,&result);finish(reader,&value,&result);
  REQUIRE(!result.batch_complete && result.batch_truncated && result.batch_attempted==3);close_batch(reader,&value,&result);value.batch_candidate_limit=0;
  char *cancel_root=g_build_filename(argv[3],"cancel",NULL);value.batch_root=cancel_root;value.action=READER_BATCH_BEGIN;value.batch_token++;
  run(reader,&value,&result);REQUIRE(result.batch_imported==1);g_atomic_int_set(&observe.cancelled,1);uint64_t before=result.batch_attempted;
  value.action=READER_BATCH_NEXT;reader_result_free(&result);run(reader,&value,&result);finish(reader,&value,&result);
  REQUIRE(result.batch_cancelled && result.batch_attempted==before && result.batch_imported==1);close_batch(reader,&value,&result);g_atomic_int_set(&observe.cancelled,0);
  char *changed=g_build_filename(argv[3],"changed",NULL);value.batch_root=changed;value.action=READER_BATCH_BEGIN;value.batch_token++;
  run(reader,&value,&result);REQUIRE(result.batch_count==1 && result.batch_imported==1);
  const char *next=!strcmp(result.batch_rows[0].path,"one.txt") ? "two.txt":"one.txt";
  char *replaced=g_build_filename(changed,next,NULL),*outside=g_build_filename(argv[3],"outside.txt",NULL);
  REQUIRE(g_unlink(replaced)==0 && symlink(outside,replaced)==0);finish(reader,&value,&result);
  REQUIRE(result.batch_imported==1 && result.batch_failed==1 && result.batch_attempted==2);close_batch(reader,&value,&result);g_free(replaced);g_free(outside);
  char *linked=g_build_filename(argv[3],"linked-root",NULL);value.batch_root=linked;value.action=READER_BATCH_BEGIN;value.batch_token++;
  linux_reader_execute(reader,&value,&result);REQUIRE(result.status!=EXR_OK && result.batch_done);reader_result_free(&result);
  /* Closing an active owner reconciles the already committed item. */
  g_free(cancel_root);cancel_root=g_build_filename(argv[3],"closing",NULL);value.batch_root=cancel_root;value.action=READER_BATCH_BEGIN;value.batch_token++;
  run(reader,&value,&result);REQUIRE(result.batch_imported==1);close_batch(reader,&value,&result);
  reading=command(READER_SHELF);linux_reader_execute(reader,&reading,&result);REQUIRE(result.status==EXR_OK && result.has_shelf && result.book_count==38);reader_result_free(&result);
  linux_reader_close(reader);inspect(argv[1],argv[4]);
  /* Reopen does not restart enumeration and original mappings remain stable. */
  REQUIRE(linux_reader_open(argv[1],argv[2],&control,&reader,&error)==EXR_OK);linux_reader_execute(reader,&reading,&result);
  REQUIRE(result.status==EXR_OK && result.has_shelf && result.book_count==38);reader_result_free(&result);linux_reader_close(reader);
  g_free(root);g_free(book);g_free(cancel_root);g_free(changed);g_free(linked);
  printf("GTK_BATCH_BACKEND checks=%u all passed\n",checks);return 0;
}
