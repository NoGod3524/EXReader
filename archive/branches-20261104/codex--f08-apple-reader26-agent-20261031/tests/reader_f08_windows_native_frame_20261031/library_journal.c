/* SPDX-License-Identifier: MIT */
#include "exreader.h"
#include <sqlite3.h>
#include <stdio.h>
#include <string.h>
#include <stdlib.h>
static unsigned checks;
#define CHECK(x) do{checks++;if(!(x)){fprintf(stderr,"line %d: %s\n",__LINE__,#x);exit(1);}}while(0)
static void mode(sqlite3 *db,const char *expected) {
  sqlite3_stmt *s=NULL;
  CHECK(sqlite3_prepare_v2(db,"PRAGMA journal_mode",-1,&s,NULL)==SQLITE_OK);
  CHECK(sqlite3_step(s)==SQLITE_ROW && !strcmp((const char*)sqlite3_column_text(s,0),expected));
  CHECK(sqlite3_finalize(s)==SQLITE_OK);
}
int main(int argc,char **argv) {
  char path[4096];exr_library *library=NULL;exr_error error={0};sqlite3 *db=NULL;
  CHECK(argc==2);
  snprintf(path,sizeof(path),"%s/journal-local.sqlite",argv[1]);remove(path);
  CHECK(exr_library_open(path,&library,&error)==EXR_OK);exr_library_close(library);library=NULL;
  CHECK(sqlite3_open(path,&db)==SQLITE_OK);mode(db,"wal");
  CHECK(sqlite3_exec(db,"PRAGMA journal_mode=DELETE;BEGIN IMMEDIATE",NULL,NULL,NULL)==SQLITE_OK);
  CHECK(exr_library_open(path,&library,&error)==EXR_OK);mode(db,"delete");
  exr_library_close(library);library=NULL;
  CHECK(sqlite3_exec(db,"COMMIT",NULL,NULL,NULL)==SQLITE_OK);CHECK(sqlite3_close(db)==SQLITE_OK);db=NULL;
  CHECK(exr_library_open(path,&library,&error)==EXR_OK);exr_library_close(library);library=NULL;
  CHECK(sqlite3_open(path,&db)==SQLITE_OK);mode(db,"wal");CHECK(sqlite3_close(db)==SQLITE_OK);db=NULL;
  CHECK(exr_library_open(":memory:",&library,&error)==EXR_OK);exr_library_close(library);library=NULL;
  snprintf(path,sizeof(path),"%s/journal-migration.sqlite",argv[1]);remove(path);
  CHECK(exr_library_migration_open(path,&library,&error)==EXR_OK);
  CHECK(exr_library_migration_finish(library,1,&error)==EXR_OK);exr_library_close(library);library=NULL;
  CHECK(sqlite3_open(path,&db)==SQLITE_OK);mode(db,"delete");CHECK(sqlite3_close(db)==SQLITE_OK);db=NULL;
  snprintf(path,sizeof(path),"%s/journal-foreign.sqlite",argv[1]);remove(path);
  CHECK(sqlite3_open(path,&db)==SQLITE_OK);
  CHECK(sqlite3_exec(db,"PRAGMA application_id=123",NULL,NULL,NULL)==SQLITE_OK);CHECK(sqlite3_close(db)==SQLITE_OK);db=NULL;
  CHECK(exr_library_open(path,&library,&error)==EXR_DATABASE && !library);
  CHECK(sqlite3_open(path,&db)==SQLITE_OK);mode(db,"delete");CHECK(sqlite3_close(db)==SQLITE_OK);
  printf("%u local journal controls passed\n",checks);return 0;
}
