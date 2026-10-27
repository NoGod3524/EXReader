/* SPDX-License-Identifier: MIT */
#include "catalog.h"
#include <sqlite3.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define CHECK(x) do { if(!(x)) { fprintf(stderr,"FAIL %d: %s\n",__LINE__,#x); exit(1); } } while(0)
static void sql(sqlite3 *db,const char *q) { char *error=NULL; int rc=sqlite3_exec(db,q,NULL,NULL,&error); if(rc!=SQLITE_OK) fprintf(stderr,"%s\n",error); CHECK(rc==SQLITE_OK); sqlite3_free(error); }
static int seen(void *ctx,const reader_catalog_original_row *r) { int *count=ctx; CHECK(r->book_key && r->storage_ref && r->state); ++*count; return 0; }
int main(int argc,char **argv) {
  sqlite3 *db=NULL; reader_catalog *c=NULL; reader_catalog_error e; size_t n; int found=0,count=0,present=0;
  const char *hash="0000000000000000000000000000000000000000000000000000000000000001";
  const char *key="txt:0000000000000000000000000000000000000000000000000000000000000001";
  reader_catalog_book b={"txt",hash,"Title","Author","Title",NULL,123,0,0};
  CHECK(argc==2 && getenv("GITHUB_ACTIONS"));
  CHECK(sqlite3_open(argv[1],&db)==SQLITE_OK); sql(db,reader_catalog_migration(&n));
  sql(db,"INSERT INTO reader_books VALUES('epub:0000000000000000000000000000000000000000000000000000000000000002','epub','0000000000000000000000000000000000000000000000000000000000000002',100,'Old','Author','Old',0,0); INSERT INTO reader_local_books VALUES('epub:0000000000000000000000000000000000000000000000000000000000000002',42,'epub_chapter');");
  CHECK(sqlite3_close(db)==SQLITE_OK);
  CHECK(reader_catalog_open(argv[1],&c,&e)==SQLITE_OK);
  CHECK(reader_catalog_has_local(c,42,&present,&e)==SQLITE_OK && present);
  CHECK(reader_catalog_original_stage(c,&b,"../escape",&e)==SQLITE_MISUSE);
  CHECK(reader_catalog_original_stage(c,&b,"originals/book.txt",&e)==SQLITE_OK);
  CHECK(reader_catalog_original_stage(c,&b,"originals/book.txt",&e)!=SQLITE_OK);
  CHECK(reader_catalog_close(&c,&e)==SQLITE_OK);
  CHECK(reader_catalog_open(argv[1],&c,&e)==SQLITE_OK);
  CHECK(reader_catalog_original_find(c,key,seen,&count,&found,&e)==SQLITE_OK && found && count==1);
  CHECK(reader_catalog_original_page(c,NULL,1,seen,&count,&e)==SQLITE_OK && count==2);
  CHECK(reader_catalog_original_forget(c,key,&e)==SQLITE_NOTFOUND);
  CHECK(reader_catalog_original_transition(c,key,"ready","deleting",&e)==SQLITE_NOTFOUND);
  CHECK(reader_catalog_original_transition(c,key,"staged","ready",&e)==SQLITE_OK);
  CHECK(reader_catalog_original_transition(c,key,"ready","deleting",&e)==SQLITE_OK);
  CHECK(reader_catalog_close(&c,&e)==SQLITE_OK);
  CHECK(reader_catalog_open(argv[1],&c,&e)==SQLITE_OK);
  CHECK(reader_catalog_original_find(c,key,seen,&count,&found,&e)==SQLITE_OK && found);
  CHECK(reader_catalog_original_forget(c,key,&e)==SQLITE_OK);
  CHECK(reader_catalog_has_local(c,42,&present,&e)==SQLITE_OK && present);
  CHECK(reader_catalog_close(&c,&e)==SQLITE_OK);
  puts("v1 migration, mapping preservation, staging, restart, transitions and deletion passed"); return 0;
}
