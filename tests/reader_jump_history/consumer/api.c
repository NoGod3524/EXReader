/* SPDX-License-Identifier: MIT */
/* C consumer: the public header compiles as C, the C ABI links, and every
   refusal keeps the history untouched. No SDK object is used here. */
#include <reader_jump_history.h>
#include <reader_revisions.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static int failures;
static void check(const char *name,int ok,const char *detail){
  if(!ok){failures++;fprintf(stderr,"FAIL %s %s\n",name,detail?detail:"");}
  printf("%s %s\n",ok?"PASS":"FAIL",name);
}
int main(int argc,char **argv){
  if(argc<2){fprintf(stderr,"usage: jump-history-c-consumer WORKDIR\n");return 2;}
  char product[4096];
  snprintf(product,sizeof(product),"%s/c-consumer.sqlite",argv[1]);
  reader_jh_error err;
  memset(&err,0,sizeof(err));
  check("the version macro is usable from C",strcmp(READER_JH_VERSION,"0.1.0")==0,READER_JH_VERSION);
  reader_jh *h=NULL;
  check("open without limits",reader_jh_open(NULL,&h,&err)==READER_JH_OK,err.message);
  reader_jh_state st;
  memset(&st,0,sizeof(st));st.struct_version=READER_JH_STRUCT_VERSION;
  check("the default limits are reported",
    reader_jh_state_get(h,&st,&err)==READER_JH_OK&&st.max_entries==READER_JH_DEFAULT_ENTRIES
    &&st.max_bytes==READER_JH_DEFAULT_BYTES&&st.count==0,err.message);
  reader_jh_item item;
  memset(&item,0,sizeof(item));
  check("peek on an empty history is EMPTY",reader_jh_peek(h,READER_JH_BACK,&item,&err)==READER_JH_EMPTY,err.message);
  check("a refused peek leaves a zeroed item",item.wire==NULL&&item.wire_bytes==0&&item.entry_id==0,"");
  reader_jh_result result;
  memset(&result,0,sizeof(result));
  check("commit_wire without a wire is ARGUMENT",
    reader_jh_commit_wire(h,NULL,READER_JH_PAGE,NULL,0,&result,&err)==READER_JH_ARGUMENT,err.message);
  reader_revisions *store=NULL;
  reader_revision_error revision_error;
  memset(&revision_error,0,sizeof(revision_error));
  check("the product revision store opens",
    reader_revisions_open(product,&store,&revision_error)==READER_REV_OK,revision_error.message);
  check("commit_wire with a non-wire payload is refused",
    reader_jh_commit_wire(h,store,READER_JH_PAGE,"not a wire",10,&result,&err)!=READER_JH_OK,err.message);
  memset(&st,0,sizeof(st));st.struct_version=READER_JH_STRUCT_VERSION;
  check("a refused wire changed nothing",
    reader_jh_state_get(h,&st,&err)==READER_JH_OK&&st.count==0&&st.generation==0,err.message);
  check("item_at outside the history is ARGUMENT",reader_jh_item_at(h,0,&item,&err)==READER_JH_ARGUMENT,err.message);
  memset(&item,0,sizeof(item));
  check("complete with a zeroed item is ARGUMENT",reader_jh_complete(h,&item,&err)==READER_JH_ARGUMENT,err.message);
  reader_jh_item_release(&item);
  reader_jh_item_release(NULL);
  reader_jh_limits limits;
  memset(&limits,0,sizeof(limits));limits.struct_version=READER_JH_STRUCT_VERSION+1;
  reader_jh *rejected=NULL;
  check("an unknown limits version is refused",
    reader_jh_open(&limits,&rejected,&err)==READER_JH_VERSION_UNSUPPORTED&&rejected==NULL,err.message);
  memset(&limits,0,sizeof(limits));limits.struct_version=READER_JH_STRUCT_VERSION;
  limits.max_entries=READER_JH_MAX_ENTRIES+1;
  check("the entry hard cap is enforced",reader_jh_open(&limits,&rejected,&err)==READER_JH_LIMIT,err.message);
  memset(&limits,0,sizeof(limits));limits.struct_version=READER_JH_STRUCT_VERSION;
  limits.max_bytes=READER_JH_MIN_BYTES-1;
  check("the byte floor is enforced",reader_jh_open(&limits,&rejected,&err)==READER_JH_LIMIT,err.message);
  check("close frees the handle",reader_jh_close(&h,&err)==READER_JH_OK&&h==NULL,err.message);
  check("closing twice is a no-op",reader_jh_close(&h,&err)==READER_JH_OK,err.message);
  if(reader_revisions_close(&store,&revision_error)!=READER_REV_OK){failures++;fprintf(stderr,"FAIL revisions close\n");}
  printf("jump-history C consumer: %s\n",failures?"FAILED":"OK");
  return failures?1:0;
}
