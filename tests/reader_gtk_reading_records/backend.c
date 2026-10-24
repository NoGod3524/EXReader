/* SPDX-License-Identifier: MIT */
#define _POSIX_C_SOURCE 200809L
#include "../../examples/linux/reading.h"
#include <sqlite3.h>
#include <glib.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
static unsigned checks;
#define REQUIRE(test) do { checks++;if(!(test)) { fprintf(stderr,"check %u line %d: %s\n",checks,__LINE__,#test);exit(1); } } while(0)
static int cancelled(void *opaque) { return *(int *)opaque; }
static reader_command command(reader_action action,int64_t book) { reader_command value={0};value.action=action;value.book=book;value.font=24;value.zoom=100;value.records_token=1;return value; }
static void commit(linux_reader *reader,reader_result *frame) {
  reader_command value=command(READER_COMMIT,frame->book);value.part=frame->part;value.page=frame->page;value.start=frame->start;
  reader_result result={0};linux_reader_execute(reader,&value,&result);REQUIRE(result.status==EXR_OK);reader_result_free(&result);
}
static void list(linux_reader *reader,int64_t book,reader_result *result) {
  reader_command value=command(READER_RECORDS_LIST,book);linux_reader_execute(reader,&value,result);REQUIRE(result->status==EXR_OK);REQUIRE(!result->has_frame);REQUIRE(result->records_page.output_bytes<=2097152);
}
static void save(linux_reader *reader,int64_t book,int kind,const char *text,reader_result *result) {
  reader_command value=command(READER_RECORDS_SAVE,book);value.records_kind=kind;value.records_operation=READER_RC_PUT;value.records_text=text;value.start=0;value.end=6;
  linux_reader_execute(reader,&value,result);
  if(result->status!=EXR_OK) fprintf(stderr,"save kind=%d status=%d g03=%d pending=%d pending_error=%d message=%s\n",kind,result->status,result->records_code,result->records_pending,result->records_pending_error,result->message);
}
static void mutate(linux_reader *reader,int64_t book,const reader_av_item *item,int kind,int operation,const char *body,const char *version,reader_result *result) {
  reader_command value=command(READER_RECORDS_SAVE,book);value.records_kind=kind;value.records_operation=operation;value.records_id=item->annotation_id;
  value.records_head=item->revision_id;value.records_sha=item->sha256;value.records_text=body;value.records_version=version;linux_reader_execute(reader,&value,result);
}
static void receive(reader_revisions *store,const char *key,const char *annotation,const char *revision,const char *operation,
    const char *const *parents,size_t parent_count,const char *body,const exr_anchor *anchor) {
  reader_rs_envelope envelope={revision,operation,"annotation",key,annotation,parents,parent_count,body,exr_version()};
  reader_rs_capture captured={0};captured.mode=READER_RS_REFLOW_GLOBAL;captured.anchor=!strcmp(operation,"delete") ? NULL:anchor;
  char *wire=NULL;size_t size=0;reader_rs_error error={0};REQUIRE(reader_rs_encode_v2(store,&envelope,&captured,0,&wire,&size,&error)==READER_RS_OK);
  char *sha=g_compute_checksum_for_data(G_CHECKSUM_SHA256,(const guchar *)wire,size);reader_revision_info info={0};int created=0;
  REQUIRE(reader_revision_receive(store,wire,size,sha,&info,&created,NULL)==READER_REV_OK && created);g_free(sha);reader_rs_free(wire);
}
int main(int argc,char **argv) {
  REQUIRE(argc==5);int cancel=0;exr_control control={cancelled,NULL,&cancel};linux_reader *reader=NULL;exr_error error={0};reader_result result={0};
  REQUIRE(linux_reader_open(argv[1],argv[2],&control,&reader,&error)==EXR_OK);
  int routes=!strcmp(argv[4],"routes"),graphs=!strcmp(argv[4],"graphs");
  reader_command value=command(!strcmp(argv[4],"first") || routes || graphs ? READER_IMPORT:READER_OPEN,1);value.path=argv[3];linux_reader_execute(reader,&value,&result);
  REQUIRE(result.status==EXR_OK && result.has_frame);int64_t book=result.book;commit(reader,&result);reader_result_free(&result);
  if(graphs) {
    save(reader,book,READER_RC_PROGRESS,"",&result);REQUIRE(result.status==EXR_OK && result.records_created);reader_result_free(&result);
    list(reader,book,&result);char key[73];g_strlcpy(key,result.records_key,sizeof(key));reader_result_free(&result);
    char *product=g_strconcat(argv[1],".product.sqlite",NULL);reader_revisions *store=NULL;REQUIRE(reader_revisions_open(product,&store,NULL)==READER_REV_OK);g_free(product);
    exr_library *library=NULL;exr_document *document=NULL;exr_anchor anchor={0};REQUIRE(exr_library_open(argv[1],&library,&error)==EXR_OK);
    REQUIRE(exr_library_document(library,book,&document,&error)==EXR_OK);REQUIRE(exr_anchor_create(document,0,0,&anchor,&error)==EXR_OK);
    char ids[8][33];for(size_t i=0;i<8;i++) REQUIRE(reader_revision_new_id(ids[i],NULL)==READER_REV_OK);
    const char *parent[]={ids[0]};const char *conflict="f0000000000000000000000000000001",*pending="f0000000000000000000000000000002",*blocked="f0000000000000000000000000000003";
    receive(store,key,conflict,ids[0],"put",NULL,0,"private root",&anchor);
    receive(store,key,conflict,ids[1],"put",parent,1,"PRIVATE CONCURRENT QUOTE",&anchor);receive(store,key,conflict,ids[2],"put",parent,1,"PRIVATE OTHER QUOTE",&anchor);
    parent[0]=ids[3];receive(store,key,pending,ids[4],"put",parent,1,"PRIVATE PENDING QUOTE",&anchor);
    receive(store,key,blocked,ids[5],"delete",NULL,0,NULL,&anchor);parent[0]=ids[5];receive(store,key,blocked,ids[6],"put",parent,1,"PRIVATE BLOCKED QUOTE",&anchor);
    char *large=g_malloc0(65537);memset(large,'x',65536);
    for(unsigned i=0;i<32;i++) { char annotation[33],revision[33];snprintf(annotation,sizeof(annotation),"%032x",0x200+i);REQUIRE(reader_revision_new_id(revision,NULL)==READER_REV_OK);receive(store,key,annotation,revision,"put",NULL,0,large,&anchor); }
    g_free(large);exr_anchor_free(&anchor);exr_document_free(document);exr_library_close(library);REQUIRE(reader_revisions_close(&store,NULL)==READER_REV_OK);
    list(reader,book,&result);REQUIRE(result.records_page.count==31 && result.records_page.budget_stopped && !result.records_page.complete && result.records_page.output_bytes<=2097152);
    char after[33];g_strlcpy(after,result.records_page.next.after_id,33);reader_result_free(&result);
    value=command(READER_RECORDS_LIST,book);value.records_after=after;value.direction=1;linux_reader_execute(reader,&value,&result);REQUIRE(result.status==EXR_OK && result.records_page.count==4 && result.records_page.complete);
    size_t concurrent_count=0,pending_count=0,blocked_count=0;
    for(size_t i=0;i<result.records_page.count;i++) {
      reader_av_item *item=&result.records_page.items[i];if(item->state==READER_AV_STATE_SAFE) continue;
      REQUIRE(!item->content_available && !item->exact && !item->note_text && !item->part_path && !item->page_id && !item->revision_id[0] && !item->sha256[0] && item->resolution==READER_AV_RESOLUTION_NOT_ATTEMPTED);
      if(item->state==READER_AV_STATE_CONCURRENT) { concurrent_count++;REQUIRE(item->revisions==3 && item->heads==2); }
      if(item->state==READER_AV_STATE_PENDING_PARENTS) { pending_count++;REQUIRE(item->missing_parents==1); }
      if(item->state==READER_AV_STATE_BLOCKED_RESTORE) { blocked_count++;REQUIRE(item->requires_restore); }
    }
    REQUIRE(concurrent_count==1 && pending_count==1 && blocked_count==1);reader_result_free(&result);
  } else if(routes) {
    save(reader,book,READER_RC_BOOKMARK,"EPUB point",&result);REQUIRE(result.status==EXR_OK && result.records_created);reader_result_free(&result);
    list(reader,book,&result);REQUIRE(result.records_page.count==1 && result.records_page.items[0].mode==READER_AV_MODE_EPUB && result.records_page.items[0].has_part && result.records_page.items[0].part==0);
    reader_av_item *item=&result.records_page.items[0];value=command(READER_RECORDS_JUMP,book);value.records_id=item->annotation_id;value.records_head=item->revision_id;value.records_sha=item->sha256;
    reader_result jumped={0};linux_reader_execute(reader,&value,&jumped);REQUIRE(jumped.status==EXR_OK && jumped.has_frame && jumped.bounded && jumped.part==0 && jumped.records_match==EXR_ANCHOR_FOUND);commit(reader,&jumped);reader_result_free(&jumped);reader_result_free(&result);
    char *folder=g_path_get_dirname(argv[3]),*path=g_build_filename(folder,"pages.pdf",NULL);value=command(READER_IMPORT,0);value.path=path;linux_reader_execute(reader,&value,&result);g_free(path);
    REQUIRE(result.status==EXR_OK && result.has_frame && result.fixed);book=result.book;commit(reader,&result);reader_result_free(&result);
    save(reader,book,READER_RC_BOOKMARK,"PDF point",&result);REQUIRE(result.status==EXR_OK && result.records_created);reader_result_free(&result);
    list(reader,book,&result);REQUIRE(result.records_page.count==1 && result.records_page.items[0].mode==READER_AV_MODE_FIXED && result.records_page.items[0].has_page);
    item=&result.records_page.items[0];value=command(READER_RECORDS_JUMP,book);value.records_id=item->annotation_id;value.records_head=item->revision_id;value.records_sha=item->sha256;
    linux_reader_execute(reader,&value,&jumped);REQUIRE(jumped.status==EXR_OK && jumped.has_frame && jumped.fixed && jumped.page==0 && jumped.records_match==EXR_ANCHOR_FOUND);commit(reader,&jumped);reader_result_free(&jumped);reader_result_free(&result);
    path=g_build_filename(folder,"pages.cbz",NULL);g_free(folder);value=command(READER_IMPORT,0);value.path=path;linux_reader_execute(reader,&value,&result);g_free(path);
    REQUIRE(result.status==EXR_OK && result.has_frame && result.fixed);book=result.book;commit(reader,&result);reader_result_free(&result);
    save(reader,book,READER_RC_BOOKMARK,"CBZ public empty snapshot point",&result);REQUIRE(result.status==EXR_OK && result.records_created && !result.records_pending && !result.has_frame);reader_result_free(&result);
    list(reader,book,&result);REQUIRE(result.records_page.count==1 && result.records_page.complete && result.records_page.items[0].mode==READER_AV_MODE_FIXED && result.records_page.items[0].exact_size==0);
    item=&result.records_page.items[0];value=command(READER_RECORDS_JUMP,book);value.records_id=item->annotation_id;value.records_head=item->revision_id;value.records_sha=item->sha256;
    linux_reader_execute(reader,&value,&jumped);REQUIRE(jumped.status==EXR_OK && jumped.has_frame && jumped.fixed && jumped.page==0 && jumped.records_match==EXR_ANCHOR_FOUND);commit(reader,&jumped);reader_result_free(&jumped);reader_result_free(&result);
    save(reader,book,READER_RC_PROGRESS,"",&result);REQUIRE(result.status==EXR_OK && result.records_created && !result.has_frame);reader_result_free(&result);
    list(reader,book,&result);REQUIRE(result.records_progress_state==READER_SELECTION_SAFE && !result.records_progress_deleted);reader_result_free(&result);
  } else if(!strcmp(argv[4],"first")) {
    list(reader,book,&result);REQUIRE(result.records_page.count==0 && result.records_page.complete);REQUIRE(result.records_progress_state==READER_SELECTION_MISSING);reader_result_free(&result);
    save(reader,book,READER_RC_PROGRESS,"",&result);REQUIRE(result.status==EXR_OK && result.records_created && !result.records_pending && !result.has_frame);reader_result_free(&result);
    for(unsigned i=0;i<35;i++) { char text[64];snprintf(text,sizeof(text),"Bookmark %u 书签 🙂",i);save(reader,book,READER_RC_BOOKMARK,text,&result);REQUIRE(result.status==EXR_OK && result.records_created && !result.has_frame && !result.records_pending);reader_result_free(&result); }
    list(reader,book,&result);REQUIRE(result.records_page.count==32 && !result.records_page.complete && !result.records_page.budget_stopped);
    char after[33];g_strlcpy(after,result.records_page.next.after_id,33);reader_result_free(&result);
    value=command(READER_RECORDS_LIST,book);value.direction=1;value.records_after=after;linux_reader_execute(reader,&value,&result);REQUIRE(result.status==EXR_OK && result.records_page.count==3 && result.records_page.complete);reader_result_free(&result);
    save(reader,book,READER_RC_HIGHLIGHT,"original note",&result);REQUIRE(result.status==EXR_OK && result.records_created);char annotation[33];g_strlcpy(annotation,result.records_annotation,33);reader_result_free(&result);
    value=command(READER_RECORDS_LIST,book);linux_reader_execute(reader,&value,&result);REQUIRE(result.status==EXR_OK);
    reader_av_page page=result.records_page;memset(&result.records_page,0,sizeof(result.records_page));reader_result_free(&result);
    reader_av_item *target=NULL;for(size_t i=0;i<page.count;i++) if(!strcmp(page.items[i].annotation_id,annotation)) target=&page.items[i];
    if(!target) { reader_av_cursor cursor=page.next;reader_av_page_free(&page);value.records_after=cursor.after_id;linux_reader_execute(reader,&value,&result);REQUIRE(result.status==EXR_OK);page=result.records_page;memset(&result.records_page,0,sizeof(result.records_page));reader_result_free(&result);for(size_t i=0;i<page.count;i++) if(!strcmp(page.items[i].annotation_id,annotation)) target=&page.items[i]; }
    REQUIRE(target && target->state==READER_AV_STATE_SAFE && target->content_available && target->resolution==READER_AV_RESOLUTION_NOT_ATTEMPTED);
    char original[33];g_strlcpy(original,target->revision_id,33);
    value=command(READER_RECORDS_JUMP,book);value.records_id=target->annotation_id;value.records_head=target->revision_id;value.records_sha=target->sha256;
    linux_reader_execute(reader,&value,&result);REQUIRE(result.status==EXR_OK && result.has_frame && result.records_match==EXR_ANCHOR_FOUND);commit(reader,&result);reader_result_free(&result);
    mutate(reader,book,target,READER_RC_NOTE_TEXT,READER_RC_PUT,"edited text",NULL,&result);REQUIRE(result.status==EXR_OK && result.records_created && !result.has_frame);reader_result_free(&result);
    mutate(reader,book,target,READER_RC_NOTE_TEXT,READER_RC_PUT,"stale edit",NULL,&result);REQUIRE(result.status!=EXR_OK && !result.records_created && !result.records_pending);reader_result_free(&result);reader_av_page_free(&page);
    /* Force a real failed product commit after the private request is durable. */
    char *product=g_strconcat(argv[1],".product.sqlite",NULL);sqlite3 *lock=NULL;REQUIRE(sqlite3_open(product,&lock)==SQLITE_OK);g_free(product);
    REQUIRE(sqlite3_exec(lock,"BEGIN IMMEDIATE",NULL,NULL,NULL)==SQLITE_OK);
    save(reader,book,READER_RC_BOOKMARK,"durable original capture",&result);REQUIRE(result.status!=EXR_OK && result.records_pending && !result.records_created && !result.has_frame);reader_result_free(&result);
    REQUIRE(sqlite3_exec(lock,"ROLLBACK",NULL,NULL,NULL)==SQLITE_OK);REQUIRE(sqlite3_close(lock)==SQLITE_OK);
    char *pending=g_strconcat(argv[1],".product.sqlite.reading.pending",NULL);struct stat info;REQUIRE(!stat(pending,&info) && (info.st_mode&077)==0);g_free(pending);
    cancel=1;
    value=command(READER_RECORDS_LIST,book);linux_reader_execute(reader,&value,&result);REQUIRE(result.status==EXR_CANCELLED && result.records_page.count==0 && !result.has_frame);reader_result_free(&result);cancel=0;
    (void)original;
  } else {
    list(reader,book,&result);REQUIRE(result.records_pending && !result.records_pending_error);char revision[33];g_strlcpy(revision,result.records_revision,33);reader_result_free(&result);
    char *pending=g_strconcat(argv[1],".product.sqlite.reading.pending",NULL),*retained=NULL;gsize retained_size=0;REQUIRE(g_file_get_contents(pending,&retained,&retained_size,NULL));
    value=command(READER_RECORDS_RETRY,book);linux_reader_execute(reader,&value,&result);REQUIRE(result.status==EXR_OK && result.records_created && !result.records_pending && !strcmp(result.records_revision,revision));reader_result_free(&result);
    REQUIRE(g_file_set_contents(pending,retained,(gssize)retained_size,NULL));REQUIRE(chmod(pending,0600)==0);
    linux_reader_execute(reader,&value,&result);REQUIRE(result.status==EXR_OK && !result.records_created && !result.records_pending && !strcmp(result.records_revision,revision));reader_result_free(&result);g_free(pending);g_free(retained);
    /* Move to the last keyset batch; edit/delete/restore one current SAFE row. */
    value=command(READER_RECORDS_LIST,book);value.direction=-1;linux_reader_execute(reader,&value,&result);REQUIRE(result.status==EXR_OK && result.records_page.count==32);
    reader_av_page page=result.records_page;memset(&result.records_page,0,sizeof(result.records_page));reader_result_free(&result);reader_av_item *item=&page.items[0];char version[33];g_strlcpy(version,item->revision_id,33);
    mutate(reader,book,item,READER_RC_BOOKMARK,READER_RC_DELETE,NULL,NULL,&result);REQUIRE(result.status==EXR_OK && result.records_created && !result.has_frame);reader_result_free(&result);
    value=command(READER_RECORDS_LIST,book);value.direction=-1;linux_reader_execute(reader,&value,&result);REQUIRE(result.status==EXR_OK);reader_av_page_free(&page);page=result.records_page;memset(&result.records_page,0,sizeof(result.records_page));reader_result_free(&result);item=&page.items[0];
    REQUIRE(item->state==READER_AV_STATE_SAFE && item->deleted && !item->content_available && !item->note_text);
    value=command(READER_RECORDS_HISTORY,book);value.records_id=item->annotation_id;value.records_head=item->revision_id;value.records_sha=item->sha256;
    linux_reader_execute(reader,&value,&result);REQUIRE(result.status==EXR_OK && result.records_version_count>=1 && result.records_history_complete);reader_result_free(&result);
    mutate(reader,book,item,READER_RC_BOOKMARK,READER_RC_RESTORE,NULL,version,&result);REQUIRE(result.status==EXR_OK && result.records_created && !result.has_frame);reader_result_free(&result);reader_av_page_free(&page);
  }
  linux_reader_close(reader);printf("reading-records backend checks=%u process=%s passed\n",checks,argv[4]);return 0;
}
