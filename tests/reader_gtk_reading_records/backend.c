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
int main(int argc,char **argv) {
  REQUIRE(argc==5);int cancel=0;exr_control control={cancelled,NULL,&cancel};linux_reader *reader=NULL;exr_error error={0};reader_result result={0};
  REQUIRE(linux_reader_open(argv[1],argv[2],&control,&reader,&error)==EXR_OK);
  int routes=!strcmp(argv[4],"routes");
  reader_command value=command(!strcmp(argv[4],"first") || routes ? READER_IMPORT:READER_OPEN,1);value.path=argv[3];linux_reader_execute(reader,&value,&result);
  REQUIRE(result.status==EXR_OK && result.has_frame);int64_t book=result.book;commit(reader,&result);reader_result_free(&result);
  if(routes) {
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
    save(reader,book,READER_RC_BOOKMARK,"CBZ must not invent text",&result);REQUIRE(result.status==EXR_UNSUPPORTED && !result.records_created && !result.records_pending && !result.has_frame);reader_result_free(&result);
    list(reader,book,&result);REQUIRE(result.records_page.count==0 && result.records_page.complete);reader_result_free(&result);
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
