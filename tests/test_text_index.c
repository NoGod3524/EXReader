/* SPDX-License-Identifier: GPL-3.0-only */
#include "exreader.h"
#include <sqlite3.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static exr_error error; static unsigned checks;
#define CHECK(x) do { checks++; if(!(x)) { fprintf(stderr,"line %d: %s (%d: %s)\n",__LINE__,#x,error.code,error.message); exit(1); } } while(0)
#define OK(x) CHECK((x)==EXR_OK)
static void sql(const char *path,const char *text) { sqlite3 *db=NULL; CHECK(sqlite3_open(path,&db)==SQLITE_OK); CHECK(sqlite3_exec(db,text,NULL,NULL,NULL)==SQLITE_OK); CHECK(sqlite3_close(db)==SQLITE_OK); }
static size_t matches(exr_text_index *index,const char *source,const void *pattern,size_t size) {
  exr_text_query *q=NULL; exr_text_hit hit; size_t count=0; int found;
  OK(exr_text_index_query(index,source,pattern,size,NULL,&q,&error));
  while(1) { OK(exr_text_query_next(q,&hit,&found,&error)); if(!found) break; CHECK(hit.start<hit.end && hit.end<=hit.text_size && hit.end-hit.start==size && !memcmp(hit.text+hit.start,pattern,size)); count++; }
  CHECK(!hit.source && !hit.part && !hit.text && !hit.text_size && hit.start==SIZE_MAX); OK(exr_text_query_next(q,&hit,&found,&error)); CHECK(!found); exr_text_query_free(q); return count;
}
static int cancel(void *context) { return *(int *)context; }
static void stop(void *context,exr_stage stage,uint64_t done,uint64_t total) { (void)stage; (void)done; (void)total; *(int *)context=1; }
int main(int argc,char **argv) {
  char path[4096],wrong[4096]; exr_text_index *i=NULL,*other=NULL; exr_text_query *q=NULL,*extra=NULL; exr_text_hit hit; int found,stopped=0; exr_control control={cancel,stop,&stopped};
  const char *chinese="中文阅读 中文阅读",*special="one \"A+B\" AND OR NEAR * ; ' two",*accent="café CAFE cafe",*emoji="😀中A 😀中A"; const char binary[]={'A',0,'B','C','D','E','F',0,'A'},nul[]={0},null_query[]={0,'B','C'};
  CHECK(argc==2); snprintf(path,sizeof(path),"%s/text-index.sqlite",argv[1]); snprintf(wrong,sizeof(wrong),"%s/wrong-index.sqlite",argv[1]); remove(path); remove(wrong);
  if(!exr_text_index_available()) { exr_document *doc=NULL; CHECK(exr_text_index_open(path,&i,&error)==EXR_FORMAT && !i); OK(exr_document_open_memory(EXR_TXT,"text",4,&doc,&error)); exr_document_free(doc); printf("disabled text index check passed\n"); return 0; }
  OK(exr_text_index_open(path,&i,&error)); CHECK(matches(i,NULL,"ana",3)==0);
  OK(exr_text_index_put(i,"book1","a","banana",6,NULL,&error)); OK(exr_text_index_put(i,"book1","b",chinese,strlen(chinese),NULL,&error));
  OK(exr_text_index_put(i,"book2","x","Banana banana",13,NULL,&error)); OK(exr_text_index_put(i,"special","",special,strlen(special),NULL,&error));
  OK(exr_text_index_put(i,"binary","",binary,sizeof(binary),NULL,&error)); OK(exr_text_index_put(i,"spaces","","a   b",5,NULL,&error));
  OK(exr_text_index_put(i,"accent","",accent,strlen(accent),NULL,&error)); OK(exr_text_index_put(i,"emoji","",emoji,strlen(emoji),NULL,&error)); OK(exr_text_index_put(i,"empty","",NULL,0,NULL,&error));
  CHECK(matches(i,NULL,"ana",3)==6); CHECK(matches(i,NULL,"banana",6)==2); CHECK(matches(i,"book1","ana",3)==2);
  CHECK(matches(i,NULL,"中文",strlen("中文"))==2); CHECK(matches(i,NULL,"文阅读",strlen("文阅读"))==2); CHECK(matches(i,NULL,"中",strlen("中"))==4);
  CHECK(matches(i,NULL,"\"A+B\"",5)==1); CHECK(matches(i,NULL,"   ",3)==1); CHECK(matches(i,NULL,"café",strlen("café"))==1); CHECK(matches(i,NULL,"😀中A",strlen("😀中A"))==2);
  CHECK(matches(i,"binary","BCD",3)==1); CHECK(matches(i,NULL,nul,sizeof(nul))==2); CHECK(matches(i,NULL,null_query,sizeof(null_query))==1);
  OK(exr_text_index_query(i,"book1","ana",3,NULL,&q,&error)); OK(exr_text_query_next(q,&hit,&found,&error)); CHECK(found && hit.start==1 && hit.end==4 && !strcmp(hit.source,"book1") && !strcmp(hit.part,"a"));
  CHECK(exr_text_index_put(i,"book1","a","replacement",11,NULL,&error)==EXR_ARGUMENT); CHECK(exr_text_index_query(i,NULL,"ana",3,NULL,&extra,&error)==EXR_ARGUMENT && !extra);
  OK(exr_text_index_open(path,&other,&error)); OK(exr_text_index_put(other,"new","part","ana",3,NULL,&error));
  OK(exr_text_query_next(q,&hit,&found,&error)); CHECK(found && hit.start==3); OK(exr_text_query_next(q,&hit,&found,&error)); CHECK(!found); exr_text_query_free(q); q=NULL;
  CHECK(matches(i,NULL,"ana",3)==7); exr_text_index_close(other); other=NULL;
  sql(path,"CREATE TRIGGER fail_write BEFORE INSERT ON text_items BEGIN SELECT RAISE(ABORT,'forced write failure');END;");
  CHECK(exr_text_index_put(i,"book1","a","changed",7,NULL,&error)==EXR_DATABASE); CHECK(matches(i,"book1","banana",6)==1); sql(path,"DROP TRIGGER fail_write;");
  sql(path,"CREATE TABLE fail_commit(parent INTEGER REFERENCES text_items(id) DEFERRABLE INITIALLY DEFERRED);CREATE TRIGGER defer_write AFTER INSERT ON text_items BEGIN INSERT INTO fail_commit VALUES(999999);END;");
  CHECK(exr_text_index_put(i,"rollback","","ana",3,NULL,&error)==EXR_DATABASE); CHECK(matches(i,"rollback","ana",3)==0); sql(path,"DROP TRIGGER defer_write;DROP TABLE fail_commit;");
  OK(exr_text_index_put(i,"book1","a","new text",8,NULL,&error)); CHECK(matches(i,"book1","banana",6)==0); CHECK(matches(i,"book1","new",3)==1);
  OK(exr_text_index_remove(i,"book1","b",NULL,&error)); CHECK(matches(i,NULL,"中文",strlen("中文"))==0); OK(exr_text_index_remove(i,"book1",NULL,NULL,&error)); CHECK(matches(i,"book1","new",3)==0);
  CHECK(exr_text_index_query(i,NULL,"\xff",1,NULL,&q,&error)==EXR_ENCODING && !q); CHECK(exr_text_index_query(i,NULL,"x",4097,NULL,&q,&error)==EXR_LIMIT && !q);
  CHECK(exr_text_index_put(i,"bad","","\xff",1,NULL,&error)==EXR_ENCODING); CHECK(exr_text_index_put(i,"bad","","x",(size_t)64*1024*1024,NULL,&error)==EXR_LIMIT);
  OK(exr_text_index_query(i,NULL,"banana",6,&control,&q,&error)); CHECK(exr_text_query_next(q,&hit,&found,&error)==EXR_CANCELLED && !found && !hit.text && hit.start==SIZE_MAX); CHECK(exr_text_query_next(q,&hit,&found,&error)==EXR_ARGUMENT); exr_text_query_free(q); q=NULL;
  CHECK(matches(i,NULL,"banana",6)==1);
  stopped=1; CHECK(exr_text_index_put(i,"bad","","text",4,&control,&error)==EXR_CANCELLED); CHECK(matches(i,"bad","text",4)==0);
  { size_t length=131072; char *large=malloc(length); CHECK(large); memset(large,'a',length); large[length-1]='b';
    OK(exr_text_index_put(i,"long","part",large,length,NULL,&error)); CHECK(matches(i,"long","aaaaab",6)==1);
    OK(exr_text_index_query(i,"long","aaaa",4,NULL,&q,&error)); OK(exr_text_query_next(q,&hit,&found,&error)); CHECK(found && hit.start==0); OK(exr_text_query_next(q,&hit,&found,&error)); CHECK(found && hit.start==1); exr_text_query_free(q); q=NULL; free(large);
    OK(exr_text_index_remove(i,"long",NULL,NULL,&error));
  }
  exr_text_index_close(i); i=NULL; OK(exr_text_index_open(path,&i,&error)); CHECK(matches(i,NULL,"banana",6)==1);
  OK(exr_text_index_query(i,NULL,"banana",6,NULL,&q,&error)); exr_text_index_close(i); i=NULL; OK(exr_text_query_next(q,&hit,&found,&error)); CHECK(found && !strcmp(hit.source,"book2")); exr_text_query_free(q); q=NULL;
  { exr_library *library=NULL; OK(exr_library_open(wrong,&library,&error)); exr_library_close(library); CHECK(exr_text_index_open(wrong,&i,&error)==EXR_DATABASE && !i); }
  OK(exr_text_index_open(path,&i,&error)); sql(path,"UPDATE text_items SET body=CAST(x'FF' AS TEXT) WHERE source='book2';");
  OK(exr_text_index_query(i,"book2","banana",6,NULL,&q,&error)); CHECK(exr_text_query_next(q,&hit,&found,&error)==EXR_DATABASE && !found && !hit.text); exr_text_query_free(q); exr_text_index_close(i);
  remove(path); remove(wrong); printf("%u text index checks passed\n",checks); return 0;
}
