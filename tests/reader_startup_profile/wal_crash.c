/* Actions-only: kill after a committed mapping while the WAL is still open. */
#define _CRT_SECURE_NO_WARNINGS
#include "catalog_sdk.h"
#include <sqlite3.h>
#include <windows.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define CHECK(x) do { if (!(x)) { fprintf(stderr,"FAIL %d: %s\n",__LINE__,#x); exit(1); } } while (0)
int main(int argc,char **argv) {
  char sdk_path[4096],product_path[4096],wal_path[4100];
  exr_library *library=NULL;reader_catalog *catalog=NULL;exr_error error={0};
  sqlite3 *db=NULL;sqlite3_stmt *stmt=NULL;int present=0;
  CHECK(argc==3);
  snprintf(sdk_path,sizeof(sdk_path),"%s/sdk.sqlite",argv[1]);
  snprintf(product_path,sizeof(product_path),"%s/product.sqlite",argv[1]);
  snprintf(wal_path,sizeof(wal_path),"%s-wal",product_path);
  CHECK(exr_library_open(sdk_path,&library,&error)==EXR_OK);
  CHECK(reader_catalog_open(product_path,&catalog,NULL)==SQLITE_OK);
  if(!strcmp(argv[2],"seed")) {
    int64_t id=0;exr_book *books=NULL;size_t count=0,failed=0;
    CHECK(exr_library_import(library,EXR_TXT,"crash original",14,"Committed book",&id,&error)==EXR_OK && id==1);
    CHECK(exr_library_books(library,"",&books,&count,&error)==EXR_OK && count==1);
    CHECK(reader_catalog_sdk_repair(catalog,library,books,count,NULL,&failed,&error)==EXR_OK && failed==0);
    exr_books_free(books,count);
    CHECK(reader_catalog_has_local(catalog,id,&present,NULL)==SQLITE_OK && present);
    CHECK(sqlite3_open_v2(product_path,&db,SQLITE_OPEN_READONLY,NULL)==SQLITE_OK);
    CHECK(sqlite3_prepare_v2(db,"PRAGMA journal_mode",-1,&stmt,NULL)==SQLITE_OK);
    CHECK(sqlite3_step(stmt)==SQLITE_ROW && !strcmp((const char *)sqlite3_column_text(stmt,0),"wal"));
    CHECK(sqlite3_finalize(stmt)==SQLITE_OK && sqlite3_close(db)==SQLITE_OK);
    WIN32_FILE_ATTRIBUTE_DATA info;
    CHECK(GetFileAttributesExA(wal_path,GetFileExInfoStandard,&info) && (info.nFileSizeHigh || info.nFileSizeLow));
    puts("READY_TO_KILL_COMMITTED_WAL");fflush(stdout);
    for(;;) Sleep(1000);
  }
  CHECK(!strcmp(argv[2],"recover"));
  CHECK(reader_catalog_has_local(catalog,1,&present,NULL)==SQLITE_OK && present);
  exr_source source={0};char bytes[14];
  CHECK(exr_library_source(library,1,&source,&error)==EXR_OK && source.size==14);
  CHECK(source.read_at(source.context,0,bytes,sizeof(bytes))==sizeof(bytes) && !memcmp(bytes,"crash original",14));
  source.release(source.context);
  CHECK(sqlite3_open_v2(product_path,&db,SQLITE_OPEN_READONLY,NULL)==SQLITE_OK);
  CHECK(sqlite3_prepare_v2(db,"PRAGMA integrity_check",-1,&stmt,NULL)==SQLITE_OK);
  CHECK(sqlite3_step(stmt)==SQLITE_ROW && !strcmp((const char *)sqlite3_column_text(stmt,0),"ok"));
  CHECK(sqlite3_finalize(stmt)==SQLITE_OK && sqlite3_close(db)==SQLITE_OK);
  CHECK(reader_catalog_close(&catalog,NULL)==SQLITE_OK);exr_library_close(library);
  puts("RECOVERED_COMMITTED_WAL");return 0;
}
