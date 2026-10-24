/* SPDX-License-Identifier: MIT */
#define _POSIX_C_SOURCE 200809L
#include "../../examples/linux/reading.h"
#include <reader_search.h>
#include <glib.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static unsigned checks;
#define REQUIRE(test) do { checks++;if(!(test)) { fprintf(stderr,"check %u failed at %d: %s\n",checks,__LINE__,#test);exit(1); } } while(0)
typedef struct { int cancel,cancel_scan;reader_search_control *observe; } context;
static int cancelled(void *value) { return ((context *)value)->cancel; }
static void phase(void *value) {
  context *control=value;
  if(control->cancel_scan && g_atomic_int_get(&control->observe->phase)==2) control->cancel=1;
}
static reader_command command(reader_action action,int64_t book,size_t part,size_t page) {
  reader_command value={0};value.action=action;value.book=book;value.part=part;value.page=page;value.font=24;value.zoom=100;return value;
}
static void commit(linux_reader *reader,const reader_result *frame) {
  reader_command value=command(READER_COMMIT,frame->book,frame->part,frame->page);value.start=frame->start;
  reader_result result={0};linux_reader_execute(reader,&value,&result);REQUIRE(result.status==EXR_OK);reader_result_free(&result);
}
static int64_t import(linux_reader *reader,const char *folder,const char *name) {
  char path[4096];snprintf(path,sizeof(path),"%s/%s",folder,name);
  reader_command value=command(READER_IMPORT,0,0,0);value.path=path;reader_result result={0};linux_reader_execute(reader,&value,&result);
  REQUIRE(result.status==EXR_OK && result.has_frame);int64_t book=result.book;commit(reader,&result);reader_result_free(&result);return book;
}
static reader_result scan(linux_reader *reader,reader_action action,int64_t book,uint64_t token,const char *query,reader_search_control *control) {
  reader_command value=command(action,book,0,0);value.search_token=token;value.search_query=query;value.search_control=control;
  if(control) { g_atomic_int_inc(&control->request);g_atomic_int_set(&control->phase,0);g_atomic_int_set(&control->polls,0); }
  value.search_request=control ? g_atomic_int_get(&control->request):0;
  reader_result result={0};linux_reader_execute(reader,&value,&result);return result;
}
static reader_result choose(linux_reader *reader,int64_t book,size_t part,size_t page,uint64_t token,size_t index) {
  reader_command value=command(READER_SEARCH_CHOOSE,book,part,page);value.search_token=token;value.search_index=index;
  reader_result result={0};linux_reader_execute(reader,&value,&result);return result;
}
int main(int argc,char **argv) {
  REQUIRE(argc==5);linux_reader *reader=NULL;exr_error error={0};context ctx={0};reader_search_control control={0};
  ctx.observe=&control;control.changed=phase;control.context=&ctx;exr_control sdk={cancelled,NULL,&ctx};
  REQUIRE(linux_reader_open(argv[1],argv[2],&sdk,&reader,&error)==EXR_OK);
  int64_t txt=import(reader,argv[3],"book.txt");reader_result result=scan(reader,READER_SEARCH_BEGIN,txt,1,"",&control);
  REQUIRE(result.search_code==READER_SEARCH_QUERY && !result.search_count && !result.has_frame && !control.phase);reader_result_free(&result);
  result=scan(reader,READER_SEARCH_BEGIN,txt,2,"\xc0\xaf",&control);
  REQUIRE(result.search_code==READER_SEARCH_QUERY && !result.search_count && !control.phase);reader_result_free(&result);
  result=scan(reader,READER_SEARCH_BEGIN,txt,3,"Z-hit",&control);size_t total=0,last=0,batches=0;
  for(;;) {
    REQUIRE(result.status==EXR_OK && result.has_search && !result.has_frame && result.search_count<=32);
    for(size_t i=0;i<result.search_count;i++) { REQUIRE(result.search_rows[i].start>=last);last=result.search_rows[i].end;total++; }
    int complete=result.search_complete;batches++;reader_result_free(&result);if(complete) break;
    result=scan(reader,READER_SEARCH_NEXT,txt,3,NULL,&control);
  }
  REQUIRE(total==250 && batches==8);
  result=scan(reader,READER_SEARCH_BEGIN,txt,4,"Z-hit",&control);REQUIRE(result.search_count==32);last=result.search_rows[31].end;reader_result_free(&result);
  ctx.cancel_scan=1;result=scan(reader,READER_SEARCH_NEXT,txt,4,NULL,&control);
  REQUIRE(result.search_code==READER_SEARCH_CANCELLED && !result.search_count && control.polls>0);reader_result_free(&result);
  ctx.cancel=ctx.cancel_scan=0;result=scan(reader,READER_SEARCH_NEXT,txt,4,NULL,&control);
  REQUIRE(result.status==EXR_OK && result.search_count==32 && result.search_rows[0].start>=last);reader_result_free(&result);
  result=scan(reader,READER_SEARCH_BEGIN,txt,5,"AMBIGUOUS TARGET",&control);REQUIRE(result.status==EXR_OK && result.search_count==2);reader_result_free(&result);
  result=choose(reader,txt,0,0,5,0);REQUIRE(result.status!=EXR_OK && !result.has_frame && result.search_match==EXR_ANCHOR_AMBIGUOUS);reader_result_free(&result);
  result=scan(reader,READER_SEARCH_BEGIN,txt,6,"书内搜索",&control);REQUIRE(result.search_count==1);reader_result_free(&result);
  result=choose(reader,txt,0,0,5,0);REQUIRE(result.status!=EXR_OK && !result.has_frame);reader_result_free(&result);
  result=choose(reader,txt,0,0,6,0);REQUIRE(result.status==EXR_OK && result.has_frame && result.search_match==EXR_ANCHOR_FOUND && result.select_range);
  REQUIRE(result.selected_end>result.selected_start);commit(reader,&result);reader_result_free(&result);
  int64_t epub=import(reader,argv[3],"book.epub");result=scan(reader,READER_SEARCH_BEGIN,epub,7,"SEARCHTOKEN",&control);
  REQUIRE(result.status==EXR_OK && result.search_count==4 && result.search_rows[3].unit==2);reader_result_free(&result);
  result=choose(reader,epub,0,0,7,3);REQUIRE(result.status==EXR_OK && result.has_frame && result.part==2 && result.search_match==EXR_ANCHOR_FOUND);commit(reader,&result);reader_result_free(&result);
  result=scan(reader,READER_SEARCH_BEGIN,epub,8,"unique-b-only",&control);REQUIRE(result.search_count==1 && result.search_rows[0].unit==1);reader_result_free(&result);
  result=choose(reader,epub,2,0,8,0);REQUIRE(result.status==EXR_OK && result.part==1 && result.search_match==EXR_ANCHOR_FOUND);commit(reader,&result);reader_result_free(&result);
  int64_t pdf=import(reader,argv[3],"pages.pdf");result=scan(reader,READER_SEARCH_BEGIN,pdf,9,"Shared quote",&control);
  REQUIRE(result.status==EXR_OK && result.search_count==2 && result.search_rows[1].unit==3);reader_result_free(&result);
  result=choose(reader,pdf,0,0,9,1);REQUIRE(result.status==EXR_OK && result.has_frame && result.fixed && result.page==3 && result.search_match==EXR_ANCHOR_FOUND);commit(reader,&result);reader_result_free(&result);
  result=scan(reader,READER_SEARCH_BEGIN,pdf,10,"selection target",&control);REQUIRE(result.status==EXR_OK && result.search_count==3);reader_result_free(&result);
  result=choose(reader,pdf,0,3,10,0);REQUIRE(result.status!=EXR_OK && !result.has_frame && result.search_match==EXR_ANCHOR_AMBIGUOUS);reader_result_free(&result);
  result=scan(reader,READER_SEARCH_BEGIN,pdf,11,"not present",&control);REQUIRE(result.status==EXR_OK && result.search_complete && !result.search_count);reader_result_free(&result);
  int64_t cbz=import(reader,argv[4],"Pages.cbz");result=scan(reader,READER_SEARCH_BEGIN,cbz,12,"word",&control);
  REQUIRE(result.search_code==READER_SEARCH_SDK && !result.has_frame);reader_result_free(&result);
  result=choose(reader,cbz,0,0,11,0);REQUIRE(result.status!=EXR_OK && !result.has_frame);reader_result_free(&result);
  result=scan(reader,READER_SEARCH_CLOSE,cbz,0,NULL,&control);REQUIRE(result.status==EXR_OK);reader_result_free(&result);
  linux_reader_close(reader);printf("{\"accepted\":true,\"scope\":\"GTK private search backend only\",\"checks\":%u}\n",checks);return 0;
}
