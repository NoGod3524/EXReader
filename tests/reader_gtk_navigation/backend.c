/* SPDX-License-Identifier: MIT */
#define _POSIX_C_SOURCE 200809L
#include "../../examples/linux/reading.h"
#include <reader_navigation.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static unsigned checks;
#define REQUIRE(test) do { checks++;if(!(test)) { fprintf(stderr,"check %u failed at %d: %s\n",checks,__LINE__,#test);exit(1); } } while(0)
typedef struct { int cancel,cancel_scan; } context;
static int cancelled(void *value) { return ((context *)value)->cancel; }
static reader_command command(reader_action action,int64_t book,size_t part,size_t page) {
  reader_command value={0};value.action=action;value.book=book;value.part=part;value.page=page;value.font=24;value.zoom=100;return value;
}
static void commit(linux_reader *reader,const reader_result *frame) {
  reader_command value=command(READER_COMMIT,frame->book,frame->part,frame->page);value.start=frame->start;
  reader_result result={0};linux_reader_execute(reader,&value,&result);REQUIRE(result.status==EXR_OK);reader_result_free(&result);
}
static int64_t import(linux_reader *reader,const char *folder,const char *name) {
  char path[4096];snprintf(path,sizeof(path),"%s/%s",folder,name);reader_command value=command(READER_IMPORT,0,0,0);value.path=path;
  reader_result result={0};linux_reader_execute(reader,&value,&result);REQUIRE(result.status==EXR_OK && result.has_frame);
  int64_t book=result.book;commit(reader,&result);reader_result_free(&result);return book;
}
typedef struct { context original;reader_navigation_control observe; } nav_context;
static void nav_phase(void *opaque) {
  nav_context *value=opaque;if(value->original.cancel_scan && value->observe.phase==2) value->original.cancel=1;
}
static reader_result nav(linux_reader *reader,reader_action action,int64_t book,size_t part,size_t page,
    uint64_t token,uint64_t parent,uint64_t row,uint64_t explicit_part,int accept,nav_context *context) {
  reader_command value=command(action,book,part,page);value.navigation_token=token;value.navigation_parent=parent;
  value.navigation_row=row;value.navigation_explicit_part=explicit_part;value.navigation_accept_part=accept;
  value.navigation_control=&context->observe;context->observe.request++;value.navigation_request=context->observe.request;
  context->observe.phase=context->observe.polls=0;reader_result result={0};linux_reader_execute(reader,&value,&result);return result;
}
static void cfi_input(const char *folder,const char *id,size_t offset,const char *output) {
  char path[4096];snprintf(path,sizeof(path),"%s/unicode.epub",folder);exr_publication *publication=NULL;exr_document *document=NULL;exr_error error={0};
  REQUIRE(exr_publication_open(path,&publication,&error)==EXR_OK);REQUIRE(exr_publication_load(publication,1,&document,&error)==EXR_OK);
  size_t count;const exr_node *nodes=exr_document_nodes(document,&count);exr_cfi_point point={SIZE_MAX,offset,0};
  for(size_t i=0;i<count;i++) { const char *found=exr_node_attribute(&nodes[i],"id");if(found && !strcmp(found,id)) { point.node=nodes[i].first_child;break; } }
  REQUIRE(point.node!=SIZE_MAX);char *cfi=NULL;REQUIRE(exr_publication_cfi_create(publication,1,document,&point,NULL,&cfi,&error)==EXR_OK);
  snprintf(path,sizeof(path),"%s/%s",folder,output);FILE *file=fopen(path,"wb");REQUIRE(file!=NULL);REQUIRE(fwrite(cfi,1,strlen(cfi),file)==strlen(cfi));REQUIRE(fclose(file)==0);
  exr_free(cfi);exr_document_free(document);exr_publication_free(publication);
}
int main(int argc,char **argv) {
  REQUIRE(argc==5);linux_reader *reader=NULL;exr_error error={0};nav_context context={0};context.observe.changed=nav_phase;context.observe.context=&context;
  exr_control sdk={cancelled,NULL,&context.original};REQUIRE(linux_reader_open(argv[1],argv[2],&sdk,&reader,&error)==EXR_OK);
  int64_t book=import(reader,argv[3],"nav3.epub");uint64_t none=READER_NAVIGATION_NONE;
  reader_result result=nav(reader,READER_NAVIGATION_BEGIN,book,0,0,1,none,0,none,0,&context);
  REQUIRE(result.status==EXR_OK && result.navigation_kind==READER_NAVIGATION_AUTHORED && result.navigation_author_outline && !result.has_frame);
  REQUIRE(result.navigation_count==10 && result.navigation_rows[0].index==0 && result.navigation_rows[0].children==1);reader_result_free(&result);
  result=nav(reader,READER_NAVIGATION_ROWS,book,0,0,1,0,0,none,0,&context);
  REQUIRE(result.status==EXR_OK && result.navigation_count==1 && result.navigation_rows[0].index==1);reader_result_free(&result);
  result=nav(reader,READER_NAVIGATION_CHOOSE,book,0,0,1,0,1,none,0,&context);
  REQUIRE(result.status==EXR_OK && result.navigation_verified && result.navigation_match==EXR_ANCHOR_FOUND && result.has_frame && result.part==1);commit(reader,&result);reader_result_free(&result);
  result=nav(reader,READER_NAVIGATION_BEGIN,book,1,0,2,none,0,none,0,&context);REQUIRE(result.status==EXR_OK);reader_result_free(&result);
  result=nav(reader,READER_NAVIGATION_CHOOSE,book,1,0,2,none,3,none,0,&context);REQUIRE(result.navigation_code==READER_NAVIGATION_NEEDS_HOST && !result.has_frame);reader_result_free(&result);
  result=nav(reader,READER_NAVIGATION_CHOOSE,book,1,0,2,none,8,none,0,&context);REQUIRE(result.navigation_code==READER_NAVIGATION_RANGE && !result.has_frame);reader_result_free(&result);
  result=nav(reader,READER_NAVIGATION_CHOOSE,book,1,0,2,none,5,none,0,&context);REQUIRE(result.navigation_code==READER_NAVIGATION_PART_ONLY && !result.has_frame);reader_result_free(&result);
  result=nav(reader,READER_NAVIGATION_CHOOSE,book,1,0,1,none,5,none,1,&context);REQUIRE(result.status!=EXR_OK && !result.has_frame);reader_result_free(&result);
  result=nav(reader,READER_NAVIGATION_CHOOSE,book,1,0,2,none,5,none,1,&context);REQUIRE(result.status==EXR_OK && result.navigation_verified && result.part==2 && result.navigation_match==EXR_ANCHOR_FOUND);commit(reader,&result);reader_result_free(&result);
  book=import(reader,argv[3],"repeated.epub");result=nav(reader,READER_NAVIGATION_BEGIN,book,0,0,3,none,0,none,0,&context);REQUIRE(result.status==EXR_OK);reader_result_free(&result);
  result=nav(reader,READER_NAVIGATION_CHOOSE,book,0,0,3,none,0,none,0,&context);REQUIRE(result.navigation_code==READER_NAVIGATION_AMBIGUOUS && result.navigation_candidate_count==2 && !result.has_frame);reader_result_free(&result);
  result=nav(reader,READER_NAVIGATION_CHOOSE,book,0,0,3,none,0,1,0,&context);REQUIRE(result.status==EXR_OK && result.navigation_verified && result.part==1);commit(reader,&result);reader_result_free(&result);
  book=import(reader,argv[3],"pages.pdf");result=nav(reader,READER_NAVIGATION_BEGIN,book,0,0,4,none,0,none,0,&context);
  REQUIRE(result.status==EXR_OK && result.navigation_kind==READER_NAVIGATION_PAGES && !result.navigation_author_outline && result.navigation_count==3);reader_result_free(&result);
  result=nav(reader,READER_NAVIGATION_CHOOSE,book,0,0,4,none,2,none,0,&context);REQUIRE(result.status==EXR_OK && result.navigation_verified && result.page==2);commit(reader,&result);reader_result_free(&result);
  book=import(reader,argv[4],"Pages.cbz");result=nav(reader,READER_NAVIGATION_BEGIN,book,0,0,5,none,0,none,0,&context);
  REQUIRE(result.status==EXR_OK && result.navigation_kind==READER_NAVIGATION_PAGES && !result.navigation_author_outline);reader_result_free(&result);
  result=nav(reader,READER_NAVIGATION_CHOOSE,book,0,0,5,none,1,none,0,&context);REQUIRE(result.status==EXR_OK && result.navigation_verified && result.page==1);commit(reader,&result);reader_result_free(&result);
  book=import(reader,argv[3],"empty.epub");result=nav(reader,READER_NAVIGATION_BEGIN,book,0,0,6,none,0,none,0,&context);REQUIRE(result.status==EXR_OK && !result.navigation_count);reader_result_free(&result);
  context.original.cancel_scan=1;result=nav(reader,READER_NAVIGATION_BEGIN,book,0,0,7,none,0,none,0,&context);REQUIRE(result.status==EXR_CANCELLED && !result.has_frame && context.observe.polls>0);reader_result_free(&result);
  context.original.cancel=context.original.cancel_scan=0;result=nav(reader,READER_NAVIGATION_CLOSE,book,0,0,0,none,0,none,0,&context);REQUIRE(result.status==EXR_OK);reader_result_free(&result);
  linux_reader_close(reader);cfi_input(argv[3],"intro",2,"normal.cfi");cfi_input(argv[3],"unicode",1,"surrogate.cfi");cfi_input(argv[3],"collapsed",3,"collapsed.cfi");
  printf("{\"accepted\":true,\"scope\":\"GTK private navigation backend\",\"checks\":%u}\n",checks);return 0;
}
