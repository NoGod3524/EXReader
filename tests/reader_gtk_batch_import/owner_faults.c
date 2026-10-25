/* SPDX-License-Identifier: MIT */
#define _POSIX_C_SOURCE 200809L
#include <gtk/gtk.h>
#include <glib/gstdio.h>
#include <reader_batch_import.h>
#include "../../examples/linux/reading.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

/* The existing notes_failure probe uses the same real-source inclusion seam.
   Only this test translation unit replaces malloc calls in reading.c. SDK,
   importer and GLib allocations remain real; the installed host is unchanged. */
static int fail_receipt_once;
static unsigned receipt_allocation_failures;
static int fail_candidate_once;
static unsigned candidate_allocation_failures;
void *__real_calloc(size_t count,size_t bytes);
void *__wrap_calloc(size_t count,size_t bytes) {
  if(fail_candidate_once && count==READER_BATCH_DEFAULT_BATCH && bytes==sizeof(reader_batch_candidate)) {
    fail_candidate_once=0;candidate_allocation_failures++;return NULL;
  }
  return __real_calloc(count,bytes);
}
static void *receipt_malloc(size_t bytes) {
  if(fail_receipt_once && bytes==sizeof(reader_batch_receipt)) {
    fail_receipt_once=0;receipt_allocation_failures++;return NULL;
  }
  return malloc(bytes);
}
#define malloc receipt_malloc
#include "../../examples/linux/reading.c"
#undef malloc
#define main exreader_owner_fault_host_main
#include "../../examples/linux/reader.c"
#undef main

static void require(int condition,const char *name) {
  if(!condition) { fprintf(stderr,"GTK_BATCH_OWNER_FAULT FAIL %s\n",name);exit(1); }
}
static host_result *execute_next(linux_reader *reader,reader_action expected) {
  host_job *job=g_async_queue_try_pop(queue);
  require(job && job->command.action==expected,"real owner queue action");
  host_result *done=g_new0(host_result,1);done->action=job->command.action;
  done->generation=job->generation;done->shelf_generation=job->shelf_generation;
  linux_reader_execute(reader,&job->command,&done->value);job_free(job);return done;
}
static void verify_original(linux_reader *reader,const char *body) {
  exr_book *books=NULL;size_t count=0;exr_error error={0};
  require(exr_library_books(reader->library,"",&books,&count,&error)==EXR_OK,"public SDK listing");
  require(count==(body ? 1u:0u),"exact SDK commit count");
  if(body) {
    char sha[65];uint64_t bytes=0;int present=0;
    char *expected=g_compute_checksum_for_string(G_CHECKSUM_SHA256,body,-1);
    require(reader_catalog_sdk_original_identity(reader->library,books[0].id,NULL,sha,&bytes,&error)==EXR_OK,
            "public SDK original readback");
    require(bytes==strlen(body) && !strcmp(sha,expected),"byte-exact committed original");g_free(expected);
    require(reader->catalog && reader_catalog_has_local(reader->catalog,books[0].id,&present,NULL)==0 && present,
            "actual product mapping completed before reopen");
  }
  exr_books_free(books,count);
}
static void close_owner(linux_reader *reader,int shutdown) {
  if(shutdown) {
    /* A close arriving after the MAP result uses the actual shutdown barrier. */
    require(closing,"shutdown state retained");folder_exit();
  } else {
    folder_close(NULL,NULL);folder_tick(NULL);
  }
  host_result *done=execute_next(reader,READER_BATCH_CLOSE);
  require(done->value.status==EXR_OK && done->value.batch_done && !done->value.batch_pending,
          "CLOSE reconciles committed SDK items");
  if(done->value.batch_count)
    require(done->value.batch_rows[0].committed && done->value.batch_rows[0].mapped,
            "CLOSE retains mapped committed receipt");
  apply_result(done);
  require(!folder.has_owner && !reader->batch_data,"CLOSE releases both real owners");
  require(g_async_queue_length(queue)==0,"no orphaned owner jobs");closing=FALSE;
}
static void scenario(const char *font,const char *output,const char *name,int fault,int map_first) {
  char *base=g_build_filename(output,name,NULL),*root=g_build_filename(base,"input",NULL);
  char *database=g_build_filename(base,"library.sqlite",NULL),*path=g_build_filename(root,"original.txt",NULL);
  const char *body=fault ? "Committed before receipt allocation fails.\n":NULL;
  require(g_mkdir_with_parents(root,0700)==0,"private real input directory");
  if(body) require(g_file_set_contents(path,body,-1,NULL),"real TXT original fixture");
  linux_reader *reader=NULL;exr_error error={0};
  require(linux_reader_open(database,font,NULL,&reader,&error)==EXR_OK,"open real installed SDK");
  memset(&folder,0,sizeof(folder));folder.token=1;folder.has_owner=1;folder.control.request=1;
  closing=busy=saving=save_failed=choosing_file=shelf_loading=FALSE;
  folder_queue(READER_BATCH_BEGIN,root,0);fail_receipt_once=fault;
  unsigned before=receipt_allocation_failures;host_result *done=execute_next(reader,READER_BATCH_BEGIN);
  if(fault) {
    require(!fail_receipt_once && receipt_allocation_failures==before+1,"actual receipt malloc returned NULL once");
    require(done->value.status==EXR_MEMORY && done->value.batch_map && done->value.batch_imported==1 &&
            done->value.batch_attempted==1 && !done->value.batch_count,"failed output allocation after real SDK commit");
  } else {
    require(done->value.status==EXR_OK && done->value.batch_map && done->value.batch_complete &&
            !done->value.batch_truncated && !done->value.batch_seen && !done->value.batch_count,
            "empty directory reaches normal end without an import");
  }
  apply_result(done);
  require(folder.has_owner && reader->batch_data && folder.map,"BEGIN retains owner requiring reconciliation");
  if(map_first) {
    folder_tick(NULL);done=execute_next(reader,READER_BATCH_MAP);
    require(done->value.status==EXR_OK && done->value.batch_done && !done->value.batch_pending,
            "MAP completes real catalog reconciliation");
    if(fault) require(done->value.batch_count==1 && done->value.batch_rows[0].committed &&
                      done->value.batch_rows[0].mapped,"MAP returns original committed receipt");
    /* Exercise the real case where app close arrives before UI accepts MAP;
       its closing guard must avoid starting an unrelated shelf repaint. */
    closing=TRUE;apply_result(done);
    require(folder.has_owner && reader->batch_data,"MAP preserves owner until CLOSE");
  }
  close_owner(reader,map_first);verify_original(reader,body);linux_reader_close(reader);
  require(linux_reader_open(database,font,NULL,&reader,&error)==EXR_OK,"reopen after fault recovery");
  reader_command shelf_command={0};reader_result shelf_result={0};shelf_command.action=READER_SHELF;
  linux_reader_execute(reader,&shelf_command,&shelf_result);
  require(shelf_result.status==EXR_OK,"normal host reopen reconciliation");reader_result_free(&shelf_result);
  verify_original(reader,body);linux_reader_close(reader);
  g_free(base);g_free(root);g_free(database);g_free(path);
  printf("GTK_BATCH_OWNER_FAULT_CASE %s passed\n",name);
}
static void candidate_failure(const char *font,const char *output) {
  char *base=g_build_filename(output,"candidate-allocation-failure",NULL),*root=g_build_filename(base,"input",NULL);
  char *database=g_build_filename(base,"library.sqlite",NULL),*path=g_build_filename(root,"original.txt",NULL);
  const char *body="Explicit retry after a real candidate allocation failure.\n";
  require(g_mkdir_with_parents(root,0700)==0 && g_file_set_contents(path,body,-1,NULL),"candidate failure fixture");
  linux_reader *reader=NULL;exr_error error={0};
  require(linux_reader_open(database,font,NULL,&reader,&error)==EXR_OK,"candidate failure SDK open");
  memset(&folder,0,sizeof(folder));folder.token=1;folder.has_owner=1;folder.control.request=1;
  closing=busy=saving=save_failed=choosing_file=shelf_loading=FALSE;
  folder_queue(READER_BATCH_BEGIN,root,0);fail_candidate_once=1;
  host_result *done=execute_next(reader,READER_BATCH_BEGIN);
  require(!fail_candidate_once && candidate_allocation_failures==1,"real frozen enumerator calloc returned NULL");
  require(done->value.status==EXR_MEMORY && done->value.batch_done && done->value.batch_owned &&
          !done->value.batch_map && !done->value.batch_attempted &&
          !strcmp(done->value.message,"Cannot allocate candidate batch"),"BEGIN error has a live owner without MAP");
  apply_result(done);
  require(folder.has_owner && reader->batch_data && !folder.map,"UI retains terminal failed enumerator until CLOSE");
  close_owner(reader,0);verify_original(reader,NULL);
  folder.token++;folder.has_owner=1;folder.want_close=folder.release_queued=0;
  g_atomic_int_inc(&folder.control.request);g_atomic_int_set(&folder.control.cancelled,0);
  folder_queue(READER_BATCH_BEGIN,root,0);done=execute_next(reader,READER_BATCH_BEGIN);
  require(done->value.status==EXR_OK && done->value.batch_imported==1 && done->value.batch_map,
          "fresh explicit BEGIN succeeds after failed owner closes");apply_result(done);
  close_owner(reader,0);verify_original(reader,body);linux_reader_close(reader);
  g_free(base);g_free(root);g_free(database);g_free(path);
  puts("GTK_BATCH_OWNER_FAULT_CASE candidate-allocation-failure passed");
}
int main(int argc,char **argv) {
  if(argc!=3) return 2;
  require(getenv("GITHUB_ACTIONS") && !strcmp(getenv("GITHUB_ACTIONS"),"true"),"Actions-only fault regression");
  require(g_mkdir_with_parents(argv[2],0700)==0,"private output directory");queue=g_async_queue_new();
  scenario(argv[1],argv[2],"allocation-failure-map-close",1,1);
  scenario(argv[1],argv[2],"allocation-failure-direct-close",1,0);
  scenario(argv[1],argv[2],"empty-directory-map-close",0,1);
  candidate_failure(argv[1],argv[2]);
  require(receipt_allocation_failures==2,"exactly two real allocation failures");
  char *path=g_build_filename(argv[2],"report.json",NULL);FILE *out=fopen(path,"w");require(out!=NULL,"open fault report");
  fprintf(out,"{\"source_sha\":\"%s\",\"run_id\":\"%s\",\"attempt\":\"%s\",\"ok\":true,\"allocation_failures\":3,\"receipt_allocation_failures\":2,\"candidate_allocation_failures\":1,\"checks\":["
    "{\"name\":\"allocation-failure-map-close\",\"passed\":true},"
    "{\"name\":\"allocation-failure-direct-close\",\"passed\":true},"
    "{\"name\":\"empty-directory-map-close\",\"passed\":true},"
    "{\"name\":\"candidate-allocation-failure\",\"passed\":true}]}\n",
    getenv("GITHUB_SHA"),getenv("GITHUB_RUN_ID"),getenv("GITHUB_RUN_ATTEMPT"));
  require(fclose(out)==0,"flush fault report");g_free(path);g_async_queue_unref(queue);
  puts("GTK_BATCH_OWNER_FAULTS scenarios=4 allocation_failures=3 all passed");return 0;
}
