/* SPDX-License-Identifier: MIT */
#include "../../examples/linux/reading.h"
#include <sqlite3.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define CHECK(x) do { if(!(x)) { fprintf(stderr,"FAIL %d: %s\n",__LINE__,#x);exit(1); } } while(0)
static unsigned groups;
static void passed(const char *name) { groups++;printf("PASS %s\n",name); }
static void run(linux_reader *reader,reader_command *command,reader_result *result) {
  reader_result_free(result);linux_reader_execute(reader,command,result);
  CHECK(result->status==EXR_OK);CHECK(result->book_count<=50);
}
static void sql(sqlite3 *db,const char *text) { CHECK(sqlite3_exec(db,text,NULL,NULL,NULL)==SQLITE_OK); }
int main(int argc,char **argv) {
  if(argc!=3) return 2;
  exr_library *library=NULL;exr_error error={0};
  CHECK(exr_library_open(argv[1],&library,&error)==EXR_OK);
  for(unsigned i=0;i<2202;i++) {
    char title[64],body[160];int64_t id=0;int created=0;
    snprintf(title,sizeof(title),"Shelf %04u",i);
    snprintf(body,sizeof(body),"Shelf original %04u. Read this book and return to the same shelf position.\n",i);
    CHECK(exr_library_import_unique(library,EXR_TXT,body,strlen(body),title,&id,&created,&error)==EXR_OK && created);
    exr_book book={0};book.id=id;book.title=title;book.author=i%17==0 ? "Author %_!":"Reader";
    book.tags="";CHECK(exr_library_update(library,&book,&error)==EXR_OK);
  }
  exr_library_close(library);passed("2202_distinct_public_sdk_originals");
  linux_reader *reader=NULL;reader_command command={0};reader_result result={0};
  CHECK(linux_reader_open(argv[1],argv[2],NULL,&reader,&error)==EXR_OK);
  command.action=READER_SHELF;command.font=24;command.zoom=100;run(reader,&command,&result);
  CHECK(result.has_shelf && result.cursors && result.book_count==50 && !result.shelf_before && result.shelf_after);
  CHECK(!strcmp(result.books[0].title,"Shelf 0000"));passed("startup_transfers_only_50_product_rows");
  size_t total=result.book_count;char title[128],key[80];
  command.action=READER_SHELF_QUERY;command.direction=1;
  while(result.shelf_after) {
    size_t last=result.book_count-1;snprintf(title,sizeof(title),"%s",result.cursors[last].sort_title);
    snprintf(key,sizeof(key),"%s",result.cursors[last].key);command.cursor_title=title;command.cursor_key=key;
    run(reader,&command,&result);CHECK(result.book_count>0 && result.shelf_before);total+=result.book_count;
  }
  CHECK(total==2202 && !strcmp(result.books[result.book_count-1].title,"Shelf 2201"));
  passed("forward_complete_2202_without_full_ui_array");
  total=result.book_count;command.direction=-1;
  while(result.shelf_before) {
    snprintf(title,sizeof(title),"%s",result.cursors[0].sort_title);snprintf(key,sizeof(key),"%s",result.cursors[0].key);
    run(reader,&command,&result);CHECK(result.book_count>0 && result.shelf_after);total+=result.book_count;
  }
  CHECK(total==2202 && !strcmp(result.books[0].title,"Shelf 0000"));passed("reverse_complete_2202_ascending_pages");
  snprintf(key,sizeof(key),"%s",result.cursors[27].key);command=(reader_command){0};
  command.action=READER_SHELF_QUERY;command.anchor_key=key;run(reader,&command,&result);
  CHECK(!strcmp(result.books[0].title,"Shelf 0027") && result.book_count==50);passed("stable_key_restore_includes_anchor");
  command.anchor_key=NULL;command.query="%_!";run(reader,&command,&result);
  CHECK(result.book_count==50 && !strcmp(result.books[0].author,"Author %_!"));passed("literal_author_filter");
  command.query="No such book";run(reader,&command,&result);CHECK(!result.book_count && result.has_shelf);
  passed("empty_filter_keeps_valid_empty_result");
  command.query="Shelf 2050";run(reader,&command,&result);CHECK(result.book_count==1);
  int64_t selected=result.books[0].id;
  command=(reader_command){0};command.action=READER_OPEN;command.book=selected;command.font=24;command.zoom=100;
  run(reader,&command,&result);CHECK(result.has_frame && result.book==selected);
  reader_command accepted={0};accepted.action=READER_COMMIT;accepted.book=result.book;accepted.start=result.start;
  accepted.part=result.part;accepted.page=result.page;
  command.action=READER_SHELF_QUERY;command.query="Shelf 2050";run(reader,&command,&result);
  run(reader,&accepted,&result);passed("shelf_query_preserves_uncommitted_reading_frame");
  reader_result_free(&result);linux_reader_close(reader);
  char catalog[4096];snprintf(catalog,sizeof(catalog),"%s.product.sqlite",argv[1]);sqlite3 *db=NULL;
  CHECK(sqlite3_open(catalog,&db)==SQLITE_OK);
  sql(db,"DELETE FROM reader_local_books WHERE sdk_book_id=1; CREATE TRIGGER fail_shelf_mapping BEFORE INSERT ON reader_local_books BEGIN SELECT RAISE(ABORT,'injected mapping failure'); END;");
  CHECK(sqlite3_close(db)==SQLITE_OK);
  CHECK(linux_reader_open(argv[1],argv[2],NULL,&reader,&error)==EXR_OK);
  command=(reader_command){0};command.action=READER_SHELF;run(reader,&command,&result);
  CHECK(result.shelf_pending && result.has_shelf && !result.cursors && result.book_count==50);
  passed("catalog_failure_keeps_bounded_local_readable_fallback");
  reader_result_free(&result);linux_reader_close(reader);
  CHECK(sqlite3_open(catalog,&db)==SQLITE_OK);sql(db,"DROP TRIGGER fail_shelf_mapping");CHECK(sqlite3_close(db)==SQLITE_OK);
  CHECK(linux_reader_open(argv[1],argv[2],NULL,&reader,&error)==EXR_OK);run(reader,&command,&result);
  CHECK(!result.shelf_pending && result.cursors && result.book_count==50);
  passed("reopen_repairs_pending_catalog_without_losing_originals");
  reader_result_free(&result);linux_reader_close(reader);CHECK(groups==10);printf("SHELF_BACKEND groups=%u passed=true\n",groups);
  return 0;
}
