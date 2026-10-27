/* SPDX-License-Identifier: MIT */
#include "catalog.h"
#include <sqlite3.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define CHECK(x) do { if(!(x)) { fprintf(stderr,"FAIL %d: %s\n",__LINE__,#x); exit(1); } } while(0)
static void sql(sqlite3 *db,const char *q) { char *error=NULL; int rc=sqlite3_exec(db,q,NULL,NULL,&error); if(rc!=SQLITE_OK) fprintf(stderr,"%s\n",error); CHECK(rc==SQLITE_OK); sqlite3_free(error); }
static int seen(void *ctx,const reader_catalog_original_row *r) { int *count=ctx; CHECK(r->book_key && r->storage_ref && r->state); ++*count; return 0; }
static int book_seen(void *ctx,const reader_catalog_row *r) { int *count=ctx; CHECK(r->book_key); ++*count; return 0; }
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
  /* A new original must not appear before its file is published. Existing
     SDK mappings must remain visible throughout staging. */
  { int books=0, visible=0;
    CHECK(reader_catalog_find(c,key,NULL,book_seen,&books,&visible,&e)==SQLITE_OK);
    CHECK(!visible && books==0);
    CHECK(reader_catalog_find(c,"epub:0000000000000000000000000000000000000000000000000000000000000002",NULL,book_seen,&books,&visible,&e)==SQLITE_OK);
    CHECK(visible && books==1);
  }
  { int books=0, visible=0;
    CHECK(reader_catalog_page(c,NULL,NULL,1,book_seen,&books,&e)==SQLITE_OK && books==1);
    books=0; CHECK(reader_catalog_query_page(c,NULL,NULL,"Title",1,1,book_seen,&books,&e)==SQLITE_OK && books==0);
    CHECK(reader_catalog_metadata(c,key,book_seen,&books,&visible,&e)==SQLITE_OK && !visible && books==0);
  }
  CHECK(reader_catalog_original_stage(c,&b,"originals/book.txt",&e)!=SQLITE_OK);
  { reader_catalog_book conflict={"txt","0000000000000000000000000000000000000000000000000000000000000004","Conflict","Author","Conflict",NULL,10,0,0};
    int books=0, visible=0;
    CHECK(reader_catalog_original_stage(c,&conflict,"originals/book.txt",&e)!=SQLITE_OK);
    CHECK(reader_catalog_find(c,"txt:0000000000000000000000000000000000000000000000000000000000000004",NULL,book_seen,&books,&visible,&e)==SQLITE_OK && !visible && books==0);
  }
  { reader_catalog_book old={"epub","0000000000000000000000000000000000000000000000000000000000000002","Ignored","Author","Ignored",NULL,100,0,0};
    int books=0, visible=0;
    CHECK(reader_catalog_original_stage(c,&old,"originals/old.epub",&e)==SQLITE_OK);
    CHECK(reader_catalog_find(c,"epub:0000000000000000000000000000000000000000000000000000000000000002",NULL,book_seen,&books,&visible,&e)==SQLITE_OK && visible && books==1);
    CHECK(reader_catalog_original_transition(c,"epub:0000000000000000000000000000000000000000000000000000000000000002","staged","deleting",&e)==SQLITE_OK);
    CHECK(reader_catalog_original_forget(c,"epub:0000000000000000000000000000000000000000000000000000000000000002",&e)==SQLITE_OK);
    CHECK(reader_catalog_has_local(c,42,&present,&e)==SQLITE_OK && present);
  }
  CHECK(reader_catalog_close(&c,&e)==SQLITE_OK);
  CHECK(reader_catalog_open(argv[1],&c,&e)==SQLITE_OK);
  CHECK(reader_catalog_original_find(c,key,seen,&count,&found,&e)==SQLITE_OK && found && count==1);
  CHECK(reader_catalog_original_page(c,NULL,1,seen,&count,&e)==SQLITE_OK && count==2);
  CHECK(reader_catalog_original_forget(c,key,&e)==SQLITE_NOTFOUND);
  CHECK(reader_catalog_original_transition(c,key,"ready","deleting",&e)==SQLITE_NOTFOUND);
  /* A failed publication rolls back both the state and book insertion. */
  CHECK(sqlite3_open(argv[1],&db)==SQLITE_OK);
  sql(db,"CREATE TRIGGER reject_publish BEFORE INSERT ON reader_books BEGIN SELECT RAISE(ABORT,'publication fault'); END");
  CHECK(sqlite3_close(db)==SQLITE_OK);
  CHECK(reader_catalog_original_transition(c,key,"staged","ready",&e)!=SQLITE_OK);
  { int books=0, visible=0; CHECK(reader_catalog_find(c,key,NULL,book_seen,&books,&visible,&e)==SQLITE_OK && !visible && books==0); }
  CHECK(sqlite3_open(argv[1],&db)==SQLITE_OK); sql(db,"DROP TRIGGER reject_publish"); CHECK(sqlite3_close(db)==SQLITE_OK);
  CHECK(reader_catalog_original_transition(c,key,"staged","ready",&e)==SQLITE_OK);
  { int books=0, visible=0; CHECK(reader_catalog_find(c,key,"Title",book_seen,&books,&visible,&e)==SQLITE_OK && visible && books==1);
    books=0; CHECK(reader_catalog_page(c,NULL,NULL,10,book_seen,&books,&e)==SQLITE_OK && books==2); }
  CHECK(reader_catalog_original_transition(c,key,"ready","deleting",&e)==SQLITE_OK);
  CHECK(reader_catalog_close(&c,&e)==SQLITE_OK);
  CHECK(reader_catalog_open(argv[1],&c,&e)==SQLITE_OK);
  CHECK(reader_catalog_original_find(c,key,seen,&count,&found,&e)==SQLITE_OK && found);
  CHECK(reader_catalog_original_forget(c,key,&e)==SQLITE_OK);
  CHECK(reader_catalog_has_local(c,42,&present,&e)==SQLITE_OK && present);
  { int books=0, visible=0; CHECK(reader_catalog_find(c,key,NULL,book_seen,&books,&visible,&e)==SQLITE_OK && visible && books==1); }
  { reader_catalog_book cancelled={"txt","0000000000000000000000000000000000000000000000000000000000000003","Cancelled","Author","Cancelled",NULL,12,0,0};
    const char *cancel_key="txt:0000000000000000000000000000000000000000000000000000000000000003";
    int books=0, visible=0;
    CHECK(reader_catalog_original_stage(c,&cancelled,"originals/cancel.txt",&e)==SQLITE_OK);
    CHECK(reader_catalog_original_transition(c,cancel_key,"staged","deleting",&e)==SQLITE_OK);
    CHECK(reader_catalog_original_forget(c,cancel_key,&e)==SQLITE_OK);
    CHECK(reader_catalog_find(c,cancel_key,NULL,book_seen,&books,&visible,&e)==SQLITE_OK && !visible && books==0);
    CHECK(reader_catalog_original_stage(c,&cancelled,"originals/cancel.txt",&e)==SQLITE_OK);
  }
  CHECK(reader_catalog_close(&c,&e)==SQLITE_OK);
  puts("v1 migration, mapping preservation, staging, restart, transitions and deletion passed"); return 0;
}
