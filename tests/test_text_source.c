/* SPDX-License-Identifier: GPL-3.0-only */
#include "exreader.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static exr_error error; static unsigned checks;
#define CHECK(x) do { checks++; if(!(x)) { fprintf(stderr,"line %d: %s (%d: %s)\n",__LINE__,#x,error.code,error.message); exit(1); } } while(0)
#define OK(x) CHECK((x)==EXR_OK)
static size_t count(exr_text_index *index,const char *source,const char *word) {
  exr_text_query *q=NULL; exr_text_hit hit; int found; size_t n=0;
  OK(exr_text_index_query(index,source,word,strlen(word),NULL,&q,&error));
  for(;;) { OK(exr_text_query_next(q,&hit,&found,&error)); if(!found) break; n++; }
  exr_text_query_free(q); return n;
}
typedef struct { exr_text_index *index; const char *path; size_t count,calls; int mode,observe; char id[48],*text; size_t size; } provider;
static void clear(provider *p) { if(p->text) memset(p->text,0xdd,p->size); free(p->text); p->text=NULL; p->size=0; }
static exr_status next(void *context,size_t at,exr_text_part *out,int *found,exr_error *e) {
  provider *p=context; clear(p); p->calls++;
  if(p->observe) {
    exr_text_index *reader=NULL; exr_text_query *q=(exr_text_query *)(uintptr_t)1; exr_error local;
    OK(exr_text_index_open(p->path,&reader,&error)); CHECK(count(reader,"book","old")==1); exr_text_index_close(reader);
    CHECK(exr_text_index_query(p->index,NULL,"old",3,NULL,&q,&local)==EXR_ARGUMENT && !q);
  }
  if(at>=p->count) { *found=0; return EXR_OK; }
  *found=1;
  if(at==1) {
    if(p->mode==2) { e->code=EXR_IO; strcpy(e->message,"Provider IO failure"); return EXR_IO; }
    if(p->mode==3) { e->code=EXR_FORMAT; strcpy(e->message,"Provider local error"); return EXR_OK; }
    if(p->mode==4) { *found=2; return EXR_OK; }
    if(p->mode==5) { *out=(exr_text_part){"too-big","x",(size_t)64*1024*1024}; return EXR_OK; }
    if(p->mode==6) { *out=(exr_text_part){"bad-utf8","\xff",1}; return EXR_OK; }
    if(p->mode==7) { *out=(exr_text_part){"missing",NULL,1}; return EXR_OK; }
  }
  snprintf(p->id,sizeof(p->id),"part-%zu",p->mode==1 ? (size_t)0 : at);
  p->size=64; p->text=malloc(p->size); CHECK(p->text); memset(p->text,' ',p->size); memcpy(p->text,"new streamed part",17);
  *out=(exr_text_part){p->id,p->text,p->size}; return EXR_OK;
}
static void reset(exr_text_index *i) { OK(exr_text_index_remove(i,"book",NULL,NULL,&error)); OK(exr_text_index_put(i,"book","baseline","old baseline",12,NULL,&error)); }
static int cancel(void *context) { return *(int *)context; }
static void final_cancel(void *context,exr_stage stage,uint64_t completed,uint64_t total) { (void)stage; if(total && completed==total) *(int *)context=1; }
int main(int argc,char **argv) {
  char path[4096]; exr_text_index *i=NULL; provider p={0}; exr_text_query *q=NULL; size_t k; int stopped=0; exr_control control={cancel,final_cancel,&stopped};
  const exr_status errors[]={EXR_ARGUMENT,EXR_IO,EXR_FORMAT,EXR_ARGUMENT,EXR_LIMIT,EXR_ENCODING,EXR_ARGUMENT};
  CHECK(argc==2); if(!exr_text_index_available()) { printf("text source provider disabled\n"); return 0; }
  snprintf(path,sizeof(path),"%s/text-source.sqlite",argv[1]); remove(path); OK(exr_text_index_open(path,&i,&error)); OK(exr_text_index_put(i,"other","keep","keep",4,NULL,&error)); reset(i);
  p.index=i; p.path=path; p.count=3; p.observe=1;
  OK(exr_text_index_replace(i,"book",next,&p,NULL,&error)); CHECK(p.calls==4); clear(&p); CHECK(count(i,"book","new")==3 && !count(i,"book","old") && count(i,"other","keep")==1);
  p.observe=0;
  for(k=1;k<=7;k++) {
    reset(i); p.calls=0; p.mode=(int)k; CHECK(exr_text_index_replace(i,"book",next,&p,NULL,&error)==errors[k-1]); clear(&p);
    CHECK(p.calls==2 && count(i,"book","old")==1 && !count(i,"book","new"));
  }
  p.mode=0; p.count=2; p.calls=0; reset(i);
  CHECK(exr_text_index_replace(i,"book",next,&p,&control,&error)==EXR_CANCELLED); clear(&p); CHECK(p.calls==3 && count(i,"book","old")==1 && !count(i,"book","new"));
  p.calls=0; CHECK(exr_text_index_replace(i,"book",next,&p,&control,&error)==EXR_CANCELLED && !p.calls);
  OK(exr_text_index_query(i,"book","old",3,NULL,&q,&error)); CHECK(exr_text_index_replace(i,"book",next,&p,NULL,&error)==EXR_ARGUMENT && !p.calls); exr_text_query_free(q);
  p.count=0; p.calls=0; OK(exr_text_index_replace(i,"book",next,&p,NULL,&error)); CHECK(p.calls==1 && !count(i,"book","old") && count(i,"other","keep")==1);
  CHECK(exr_text_index_replace(i,"book",NULL,&p,NULL,&error)==EXR_ARGUMENT); CHECK(exr_text_index_replace(i,NULL,next,&p,NULL,&error)==EXR_ARGUMENT);
  exr_text_index_close(i); remove(path); printf("%u streaming text source checks passed\n",checks); return 0;
}
