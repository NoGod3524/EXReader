/* SPDX-License-Identifier: MIT */
#include <exreader.h>
#include <sqlite3.h>
#include <stdio.h>
int main(int argc,char **argv) {
  exr_library *owner=NULL;exr_error error={0};exr_source source={0};sqlite3 *other=NULL;
  static const char ledger[]="temporary uncommitted ledger";
  if(argc!=2) return 2;
  if(exr_library_migration_open(argv[1],&owner,&error)!=EXR_OK) { fprintf(stderr,"open: %s\n",error.message);return 1; }
  if(exr_library_source(owner,1,&source,&error)!=EXR_OK ||
     exr_library_migration_ledger_set(owner,ledger,sizeof(ledger)-1,&error)!=EXR_OK) {
    fprintf(stderr,"source/ledger: %s\n",error.message);exr_library_close(owner);return 1;
  }
  exr_library_close(owner);
  if(sqlite3_open_v2(argv[1],&other,SQLITE_OPEN_READWRITE,NULL)!=SQLITE_OK ||
     sqlite3_exec(other,"BEGIN IMMEDIATE;ROLLBACK",NULL,NULL,NULL)!=SQLITE_OK) {
    fprintf(stderr,"owner close did not release transaction\n");if(other) sqlite3_close(other);source.release(source.context);return 1;
  }
  sqlite3_close(other);
  {
    char prefix[5];
    if(source.read_at(source.context,0,prefix,sizeof(prefix))!=sizeof(prefix)) {
      fprintf(stderr,"retained source unreadable after owner close\n");source.release(source.context);return 1;
    }
  }
  source.release(source.context);
  puts("owner close rolled back while source remained live");return 0;
}
