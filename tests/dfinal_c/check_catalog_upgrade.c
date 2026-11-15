/* SPDX-License-Identifier: MIT */
/* Installed product API opening actual v1/v2 layouts; no SDK private tables. */
#include <catalog.h>
#include <sqlite3.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static unsigned checks;
#define CHECK(x) do { ++checks; if(!(x)) { fprintf(stderr,"FAIL line %d: %s\n",__LINE__,#x); exit(1); } } while(0)
#define KEY "txt:0000000000000000000000000000000000000000000000000000000000000001"
#define ID "00000000000000000000000000000001"

static sqlite3 *database(const char *path) {
  sqlite3 *db=NULL; CHECK(sqlite3_open(path,&db)==SQLITE_OK); return db;
}
static void sql(sqlite3 *db,const char *text) {
  char *message=NULL; int rc=sqlite3_exec(db,text,NULL,NULL,&message);
  if(rc!=SQLITE_OK) fprintf(stderr,"SQL: %s\n",message?message:"");
  sqlite3_free(message); CHECK(rc==SQLITE_OK);
}
static int scalar(sqlite3 *db,const char *text) {
  sqlite3_stmt *s=NULL; int value;
  CHECK(sqlite3_prepare_v2(db,text,-1,&s,NULL)==SQLITE_OK);
  CHECK(sqlite3_step(s)==SQLITE_ROW); value=sqlite3_column_int(s,0);
  CHECK(sqlite3_finalize(s)==SQLITE_OK); return value;
}
static void sql_file(sqlite3 *db,const char *path) {
  FILE *file=fopen(path,"rb"); long size; char *text;
  CHECK(file && fseek(file,0,SEEK_END)==0); size=ftell(file);
  CHECK(size>0 && fseek(file,0,SEEK_SET)==0); text=malloc((size_t)size+1); CHECK(text);
  CHECK(fread(text,1,(size_t)size,file)==(size_t)size && fclose(file)==0);
  text[size]=0; sql(db,text); free(text);
}
static void retained(sqlite3 *db,int version) {
  CHECK(scalar(db,"PRAGMA application_id")==1163416144);
  CHECK(scalar(db,"PRAGMA user_version")==version);
  CHECK(scalar(db,"SELECT count(*) FROM reader_books WHERE book_key='" KEY "' AND title='Old title' AND author='Old author' AND sort_title='Old title' AND source_bytes=21 AND favorite=1 AND deleted=0")==1);
  CHECK(scalar(db,"SELECT count(*) FROM reader_local_books WHERE book_key='" KEY "' AND sdk_book_id=42 AND location_kind='reflow_global'")==1);
  CHECK(scalar(db,"SELECT count(*) FROM reader_shelves WHERE shelf_id='" ID "' AND name='Old shelf' AND ordinal=3 AND deleted=0")==1);
  CHECK(scalar(db,"SELECT count(*) FROM reader_book_shelves WHERE shelf_id='" ID "' AND book_key='" KEY "' AND ordinal=7")==1);
  CHECK(scalar(db,"SELECT count(*) FROM reader_tags WHERE tag_id='" ID "' AND name='Old tag' AND deleted=0")==1);
  CHECK(scalar(db,"SELECT count(*) FROM reader_book_tags WHERE tag_id='" ID "' AND book_key='" KEY "'")==1);
  CHECK(scalar(db,"SELECT count(*) FROM reader_series WHERE series_id='" ID "' AND name='Old series' AND deleted=0")==1);
  CHECK(scalar(db,"SELECT count(*) FROM reader_book_series WHERE series_id='" ID "' AND book_key='" KEY "' AND ordinal=9")==1);
  CHECK(scalar(db,"SELECT count(*) FROM reader_revisions WHERE revision_id='" ID "' AND entity_kind='annotation' AND entity_key='old-annotation' AND operation='delete' AND body_json='{}' AND body_sha256='44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a'")==1);
  CHECK(scalar(db,"SELECT count(*) FROM reader_outbox WHERE queue_id=13 AND revision_id='" ID "' AND attempts=4 AND last_error='offline'")==1);
  CHECK(scalar(db,"SELECT count(*) FROM reader_tombstones WHERE revision_id='" ID "'")==1);
  CHECK(scalar(db,"SELECT count(*) FROM pragma_foreign_key_check")==0);
}
static int book_seen(void *context,const reader_catalog_row *row) {
  CHECK(!strcmp(row->book_key,KEY) && !strcmp(row->title,"Old title") &&
        !strcmp(row->author,"Old author") && row->sdk_book_id==42 && row->favorite==1);
  ++*(int *)context; return 0;
}
static int original_seen(void *context,const reader_catalog_original_row *row) {
  CHECK(!strcmp(row->book_key,KEY) && !strcmp(row->storage_ref,"originals/old.txt") && !strcmp(row->state,"ready"));
  ++*(int *)context; return 0;
}
int main(int argc,char **argv) {
  CHECK(argc==4);
  for(int version=1;version<=2;++version) {
    char path[4096]; sqlite3 *db; reader_catalog *catalog=NULL; reader_catalog_error error;
    CHECK(snprintf(path,sizeof(path),"%s/product-upgrade-v%d.db",argv[3],version)>0);
    remove(path); db=database(path); sql_file(db,argv[1]);
    sql(db,"INSERT INTO reader_books VALUES('" KEY "','txt','0000000000000000000000000000000000000000000000000000000000000001',21,'Old title','Old author','Old title',1,0);"
      "INSERT INTO reader_local_books VALUES('" KEY "',42,'reflow_global');"
      "INSERT INTO reader_shelves VALUES('" ID "',NULL,'Old shelf',3,0);"
      "INSERT INTO reader_book_shelves VALUES('" ID "','" KEY "',7);"
      "INSERT INTO reader_tags VALUES('" ID "','Old tag',0);"
      "INSERT INTO reader_book_tags VALUES('" KEY "','" ID "');"
      "INSERT INTO reader_series VALUES('" ID "','Old series',0);"
      "INSERT INTO reader_book_series VALUES('" ID "','" KEY "',9);"
      "INSERT INTO reader_revisions VALUES('" ID "','annotation','old-annotation','delete','{}','44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a');"
      "INSERT INTO reader_outbox VALUES(13,'" ID "',4,'offline');");
    if(version==2) {
      sql_file(db,argv[2]);
      sql(db,"INSERT INTO reader_originals VALUES('" KEY "','originals/old.txt','ready')");
    }
    retained(db,version);
    /* v2 fails after ALTER/copy/drop, so rollback must restore its original table. */
    sql(db,version==1 ? "CREATE TABLE reader_originals(fault INTEGER)" : "CREATE TABLE reader_original_pending(fault INTEGER)");
    CHECK(sqlite3_close(db)==SQLITE_OK);
    CHECK(reader_catalog_open(path,&catalog,&error)!=SQLITE_OK && !catalog);
    db=database(path); retained(db,version);
    if(version==2) {
      CHECK(scalar(db,"SELECT count(*) FROM reader_originals WHERE book_key='" KEY "' AND storage_ref='originals/old.txt' AND state='ready'")==1);
      CHECK(scalar(db,"SELECT count(*) FROM sqlite_master WHERE name='reader_originals_v2'")==0);
    }
    sql(db,version==1 ? "DROP TABLE reader_originals" : "DROP TABLE reader_original_pending");
    CHECK(sqlite3_close(db)==SQLITE_OK);
    for(int reopen=0;reopen<2;++reopen) {
      int found=0,count=0;
      CHECK(reader_catalog_open(path,&catalog,&error)==SQLITE_OK);
      CHECK(reader_catalog_find(catalog,KEY,NULL,book_seen,&count,&found,&error)==SQLITE_OK && found && count==1);
      count=0;
      CHECK(reader_catalog_original_find(catalog,KEY,original_seen,&count,&found,&error)==SQLITE_OK);
      CHECK(found==(version==2) && count==(version==2));
      CHECK(reader_catalog_close(&catalog,&error)==SQLITE_OK && !catalog);
      db=database(path); retained(db,3);
      CHECK(scalar(db,"SELECT count(*) FROM reader_original_pending")==0);
      CHECK(sqlite3_close(db)==SQLITE_OK);
    }
    printf("product schema %d -> 3: failure rollback, metadata/mappings/organization/revisions/outbox%s, installed API and reopen passed\n",version,version==2 ? "/original reference" : "");
  }
  printf("%u product catalog upgrade checks passed\n",checks);
  return 0;
}
