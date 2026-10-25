/* SPDX-License-Identifier: MIT */
#define _POSIX_C_SOURCE 200809L
#include "../../examples/linux/reading.h"
#include "../../apps/reader/desktop/catalog_sdk.h"
#include <reader_batch_import.h>
#include <exr_desktop_drop.h>
#include <glib.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static void check(int ok,const char *name) { if(!ok) { fprintf(stderr,"DROP_BACKEND_FAIL %s\n",name);exit(1); } }
typedef struct { int64_t id;uint64_t bytes; } mapped_book;
static int mapped(void *context,const reader_catalog_row *row) { mapped_book *book=context;book->id=row->sdk_book_id;book->bytes=row->source_bytes;return 0; }
static void inspect(const char *database,const char *output) {
  exr_library *library=NULL;exr_error error={0};exr_book *books=NULL;size_t count=0;
  check(exr_library_open(database,&library,&error)==EXR_OK,"SDK open");
  check(exr_library_books(library,"",&books,&count,&error)==EXR_OK,"SDK books");
  char *product=g_strconcat(database,".product.sqlite",NULL);reader_catalog *catalog=NULL;
  check(reader_catalog_open(product,&catalog,NULL)==0,"product open");g_free(product);
  FILE *out=fopen(output,"w");check(out!=NULL,"output open");
  for(size_t i=0;i<count;i++) {
    char sha[65],key[80];uint64_t bytes=0;int found=0;mapped_book book={0};
    check(reader_catalog_sdk_original_identity(library,books[i].id,NULL,sha,&bytes,&error)==EXR_OK,"public original identity");
    char *format=g_ascii_strdown(reader_batch_format_name(books[i].format),-1);
    snprintf(key,sizeof(key),"%s:%s",format,sha);g_free(format);
    check(reader_catalog_find(catalog,key,NULL,mapped,&book,&found,NULL)==0 && found && book.id==books[i].id && book.bytes==bytes,
          "canonical existing SDK/product mapping");
    fprintf(out,"%lld\t%s\t%s\t%llu\t%zu\n",(long long)books[i].id,reader_batch_format_name(books[i].format),sha,(unsigned long long)bytes,books[i].position);
  }
  check(fclose(out)==0,"output close");reader_catalog_close(&catalog,NULL);exr_books_free(books,count);exr_library_close(library);
}
int main(int argc,char **argv) {
  if(argc!=6) return 2;
  if(!strcmp(argv[5],"inspect")) { inspect(argv[1],argv[3]);return 0; }
  check(getenv("GITHUB_ACTIONS") && !strcmp(getenv("GITHUB_ACTIONS"),"true"),"Actions only");
  gchar *payload=NULL;gsize bytes=0;check(g_file_get_contents(argv[3],&payload,&bytes,NULL),"native payload fixture");
  linux_reader *reader=NULL;exr_error error={0};check(linux_reader_open(argv[1],argv[2],NULL,&reader,&error)==EXR_OK,"reader open");
  reader_batch_control observe={.request=1};reader_command command={0};reader_result result={0};
  command.action=READER_BATCH_BEGIN;command.batch_token=1;command.batch_control=&observe;command.batch_request=1;
  command.batch_input=strstr(argv[5],"gnome") ? 2:1;command.batch_origin=EXR_DROP_ORIGIN_DROP;
  command.batch_payload=payload;command.batch_payload_bytes=bytes;
  linux_reader_execute(reader,&command,&result);g_free(payload);command.batch_payload=NULL;command.batch_payload_bytes=0;
  if(result.status!=EXR_OK) {
    fprintf(stderr,"INPUT_REFUSED status=%d owned=%d: %s\n",result.status,result.batch_owned,result.message);
    check(!result.batch_owned,"failed initial parse leaves no owner");reader_result_free(&result);linux_reader_close(reader);return 3;
  }
  if(strstr(argv[5],"cancel") && result.batch_imported) g_atomic_int_set(&observe.cancelled,1);
  for(unsigned step=0;!result.batch_done && step<1000;step++) {
    command.action=result.batch_map ? READER_BATCH_MAP:READER_BATCH_NEXT;reader_result_free(&result);
    linux_reader_execute(reader,&command,&result);check(result.status==EXR_OK,"serial explicit-file owner operation");
    check(result.batch_count<=32 && !result.has_frame,"bounded receipts and no implicit navigation");
  }
  check(result.batch_done && !result.batch_pending,"complete/reconciled request");
  FILE *out=fopen(argv[4],"w");check(out!=NULL,"summary open");
  fprintf(out,"%d\t%d\t%d\t%llu\t%llu\t%llu\t%llu\t%zu\t%zu\t%zu\n",
    result.batch_complete,result.batch_truncated,result.batch_cancelled,(unsigned long long)result.batch_attempted,
    (unsigned long long)result.batch_imported,(unsigned long long)result.batch_duplicates,(unsigned long long)result.batch_failed,
    result.batch_source_items,result.batch_source_duplicates,result.batch_source_overflow);check(fclose(out)==0,"summary close");
  reader_result_free(&result);command.action=READER_BATCH_CLOSE;linux_reader_execute(reader,&command,&result);
  check(result.status==EXR_OK && !result.batch_owned,"CLOSE releases explicit source and reconciles");reader_result_free(&result);linux_reader_close(reader);
  return 0;
}
