/* SPDX-License-Identifier: MIT */
/* Actions-only owner-level probe of the five Wave 3 GTK tools. It drives the real
   linux_reader_execute worker entry point, exactly as the GTK worker does, with
   real SDK books, the real product revision store and the real installed modules. */
#define _POSIX_C_SOURCE 200809L
#include "../../examples/linux/reading.h"
#include <reader_annotation_export.h>
#include <reader_search.h>
#include <glib.h>
#include <glib/gstdio.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>

static unsigned checks;
#define REQUIRE(test) do { checks++;if(!(test)) { fprintf(stderr,"check %u failed at %d: %s\n",checks,__LINE__,#test);exit(1); } } while(0)
#define PASS(name) printf("{\"check\":\"%s\",\"pass\":true}\n",name)
static int never(void *unused) { (void)unused;return 0; }
static reader_command command(reader_action action,int64_t book) {
  reader_command value={0};value.action=action;value.book=book;value.font=24;value.zoom=100;value.records_token=1;return value;
}
static reader_result run(linux_reader *reader,reader_command value) {
  reader_result result={0};linux_reader_execute(reader,&value,&result);return result;
}
static reader_result commit(linux_reader *reader,const reader_result *frame) {
  reader_command value=command(READER_COMMIT,frame->book);value.part=frame->part;value.page=frame->page;value.start=frame->start;
  reader_result result=run(reader,value);REQUIRE(result.status==EXR_OK);return result;
}
static int64_t open_book(linux_reader *reader,reader_action action,const char *path,int64_t book,reader_result *landed) {
  reader_command value=command(action,book);value.path=path;reader_result frame=run(reader,value);
  REQUIRE(frame.status==EXR_OK && frame.has_frame);int64_t id=frame.book;
  *landed=commit(reader,&frame);reader_result_free(&frame);return id;
}
static reader_result scan_choose(linux_reader *reader,int64_t book,uint64_t token,const char *query,reader_search_control *control) {
  reader_command value=command(READER_SEARCH_BEGIN,book);value.search_token=token;value.search_query=query;value.search_control=control;
  g_atomic_int_inc(&control->request);g_atomic_int_set(&control->phase,0);g_atomic_int_set(&control->polls,0);
  value.search_request=g_atomic_int_get(&control->request);
  reader_result found=run(reader,value);REQUIRE(found.status==EXR_OK && found.search_count>=1);reader_result_free(&found);
  value=command(READER_SEARCH_CHOOSE,book);value.search_token=token;value.search_index=0;
  reader_result frame=run(reader,value);
  REQUIRE(frame.status==EXR_OK && frame.has_frame && frame.search_match==EXR_ANCHOR_FOUND && frame.select_range);return frame;
}
static void write_text(const char *path,const char *title) {
  GString *text=g_string_new(NULL);
  for(int i=0;i<900;i++) {
    g_string_append_printf(text,"%s line %d keeps ordinary reading words moving through the page so that several pages exist.\n",title,i);
    if(i==120) g_string_append(text,"NEEDLEONE appears only here.\n");
    if(i==520) g_string_append(text,"NEEDLETWO appears only here.\n");
  }
  REQUIRE(g_file_set_contents(path,text->str,(gssize)text->len,NULL));g_string_free(text,TRUE);
}
static void expect_history(linux_reader *reader,int64_t book,int direction,size_t selected,reader_result *out,int commit_it,int count,int cursor,int back,int forward) {
  reader_command value=command(READER_W3_HISTORY,book);value.direction=direction;
  reader_result frame=run(reader,value);
  REQUIRE(frame.status==EXR_OK && frame.has_frame && frame.select_range && frame.selected_start==selected);
  if(commit_it) {
    reader_result landed=commit(reader,&frame);
    REQUIRE(landed.has_w3 && landed.w3_history_count==count && landed.w3_history_cursor==cursor);
    REQUIRE(landed.w3_can_back==back && landed.w3_can_forward==forward);reader_result_free(&landed);
  }
  if(out) *out=frame;else reader_result_free(&frame);
}
static int font_count(linux_reader *reader,int64_t book,char *active) {
  reader_result list=run(reader,command(READER_W3_FONT_LIST,book));REQUIRE(list.status==EXR_OK && list.has_w3);
  int count=list.w3_font_count;if(active) g_strlcpy(active,list.w3_font_active,RFL_HASH_BYTES);reader_result_free(&list);return count;
}
int main(int argc,char **argv) {
  REQUIRE(argc==6);
  const char *library_a=argv[1],*library_b=argv[2],*font=argv[3],*fonts=argv[4],*work=argv[5];
  exr_control control={never,NULL,NULL};linux_reader *reader=NULL;exr_error error={0};reader_search_control search={0};
  char *text_path=g_build_filename(work,"history.txt",NULL),*other_path=g_build_filename(work,"other.txt",NULL);
  write_text(text_path,"History");write_text(other_path,"Other");
  REQUIRE(linux_reader_open(library_a,font,&control,&reader,&error)==EXR_OK);

  /* 1. Landing history: page, search, search; back/forward move only after the frame is accepted. */
  reader_result landed={0};int64_t book=open_book(reader,READER_IMPORT,text_path,0,&landed);
  REQUIRE(landed.has_w3 && landed.w3_history_count==1 && !landed.w3_can_back && !landed.w3_can_forward);
  const size_t first_start=0;
  char key[73];
  {
    reader_command save=command(READER_RECORDS_SAVE,book);save.records_kind=READER_RC_HIGHLIGHT;save.records_operation=READER_RC_PUT;
    save.records_text="History highlight";save.start=0;save.end=6;
    reader_result saved=run(reader,save);REQUIRE(saved.status==EXR_OK && saved.records_created);g_strlcpy(key,saved.records_key,sizeof(key));reader_result_free(&saved);
    save.records_kind=READER_RC_BOOKMARK;save.records_text="History bookmark";save.start=0;save.end=0;
    saved=run(reader,save);REQUIRE(saved.status==EXR_OK && saved.records_created);reader_result_free(&saved);
  }
  reader_result_free(&landed);PASS("annotations_exist_before_history");
  reader_result one=scan_choose(reader,book,1,"NEEDLEONE",&search);size_t one_start=one.selected_start;
  landed=commit(reader,&one);REQUIRE(landed.w3_history_count==2 && landed.w3_history_cursor==1 && landed.w3_can_back && !landed.w3_can_forward);
  reader_result_free(&landed);reader_result_free(&one);
  reader_result two=scan_choose(reader,book,2,"NEEDLETWO",&search);size_t two_start=two.selected_start;
  REQUIRE(two_start>one_start);landed=commit(reader,&two);
  REQUIRE(landed.w3_history_count==3 && landed.w3_history_cursor==2 && landed.w3_can_back && !landed.w3_can_forward);
  reader_result_free(&landed);reader_result_free(&two);PASS("history_records_page_and_search_landings");
  expect_history(reader,book,-1,one_start,NULL,1,3,1,1,1);PASS("history_back_to_first_search_after_accept");
  reader_result origin={0};
  {
    reader_command value=command(READER_W3_HISTORY,book);value.direction=-1;origin=run(reader,value);
    REQUIRE(origin.status==EXR_OK && origin.has_frame && origin.start==first_start);
    reader_result moved=commit(reader,&origin);
    REQUIRE(moved.w3_history_cursor==0 && !moved.w3_can_back && moved.w3_can_forward);reader_result_free(&moved);reader_result_free(&origin);
  }
  {
    reader_command value=command(READER_W3_HISTORY,book);value.direction=-1;reader_result none=run(reader,value);
    REQUIRE(none.status!=EXR_OK && !none.has_frame && strstr(none.message,"No earlier"));reader_result_free(&none);
  }
  PASS("history_back_to_origin_then_empty_refused");
  expect_history(reader,book,1,one_start,NULL,1,3,1,1,1);
  /* Forward is proved but not accepted: discarding the pending frame must leave the cursor. */
  {
    reader_command value=command(READER_W3_HISTORY,book);value.direction=1;reader_result pending=run(reader,value);
    REQUIRE(pending.status==EXR_OK && pending.has_frame && pending.selected_start==two_start);reader_result_free(&pending);
    reader_result shelf=run(reader,command(READER_SHELF,book));REQUIRE(shelf.status==EXR_OK);reader_result_free(&shelf);
    reader_result again=run(reader,value);REQUIRE(again.status==EXR_OK && again.has_frame && again.selected_start==two_start);
    reader_result moved=commit(reader,&again);REQUIRE(moved.w3_history_cursor==2 && moved.w3_can_back && !moved.w3_can_forward);
    reader_result_free(&moved);reader_result_free(&again);
  }
  PASS("history_unaccepted_target_leaves_cursor");
  {
    reader_command value=command(READER_W3_HISTORY,book);value.direction=1;reader_result none=run(reader,value);
    REQUIRE(none.status!=EXR_OK && !none.has_frame && strstr(none.message,"No later"));reader_result_free(&none);
  }
  PASS("history_forward_empty_refused");

  /* 2. Local font library: import, duplicate, lease, rollback, corruption, removal, reopen. */
  REQUIRE(font_count(reader,book,NULL)==0);
  char *primary=g_build_filename(fonts,"primary.ttf",NULL),*fallback=g_build_filename(fonts,"fallback.ttf",NULL);
  reader_command importing=command(READER_W3_FONT_IMPORT,book);importing.w3_path=primary;
  reader_result added=run(reader,importing);REQUIRE(added.status==EXR_OK && added.w3_font_count==1 && strstr(added.message,"added"));
  char primary_hash[RFL_HASH_BYTES];g_strlcpy(primary_hash,added.w3_font_hashes[0],sizeof(primary_hash));reader_result_free(&added);
  added=run(reader,importing);REQUIRE(added.status==EXR_OK && added.w3_font_count==1 && strstr(added.message,"already"));reader_result_free(&added);
  importing.w3_path=fallback;added=run(reader,importing);REQUIRE(added.status==EXR_OK && added.w3_font_count==2);
  char fallback_hash[RFL_HASH_BYTES]="";
  for(int i=0;i<added.w3_font_count;i++) if(strcmp(added.w3_font_hashes[i],primary_hash)) g_strlcpy(fallback_hash,added.w3_font_hashes[i],sizeof(fallback_hash));
  reader_result_free(&added);REQUIRE(fallback_hash[0]);
  {
    reader_command bad=command(READER_W3_FONT_IMPORT,book);bad.w3_path=text_path;reader_result refused=run(reader,bad);
    REQUIRE(refused.status!=EXR_OK && refused.w3_font_count==2);reader_result_free(&refused);
  }
  PASS("font_import_duplicate_and_invalid_keep_library");
  reader_result before=run(reader,command(READER_NEXT,book));REQUIRE(before.status==EXR_OK && before.has_frame);
  reader_result moved=commit(reader,&before);reader_result_free(&moved);reader_result_free(&before);
  reader_command use=command(READER_W3_FONT_USE,book);use.w3_hash=primary_hash;use.font=24;
  /* A candidate pager is borrowed from the lease until the frame is accepted; discarding releases it. */
  reader_result candidate=run(reader,use);REQUIRE(candidate.status==EXR_OK && candidate.has_frame);reader_result_free(&candidate);
  reader_command removal=command(READER_W3_FONT_REMOVE,book);removal.w3_hash=primary_hash;
  reader_result discarded=run(reader,command(READER_SHELF,book));REQUIRE(discarded.status==EXR_OK);reader_result_free(&discarded);
  char active[RFL_HASH_BYTES];REQUIRE(font_count(reader,book,active)==2 && !active[0]);
  candidate=run(reader,use);REQUIRE(candidate.status==EXR_OK && candidate.has_frame);
  landed=commit(reader,&candidate);REQUIRE(!strcmp(landed.w3_font_active,primary_hash));reader_result_free(&landed);
  REQUIRE(candidate.end>candidate.start && candidate.font==24);reader_result_free(&candidate);
  reader_result next=run(reader,command(READER_NEXT,book));REQUIRE(next.status==EXR_OK && next.has_frame);
  landed=commit(reader,&next);reader_result_free(&landed);reader_result_free(&next);
  PASS("font_lease_applies_after_accept_and_discard_releases");
  {
    reader_result blocked=run(reader,removal);REQUIRE(blocked.status!=EXR_OK && strstr(blocked.message,"in use"));reader_result_free(&blocked);
    removal.w3_hash=fallback_hash;reader_result gone=run(reader,removal);REQUIRE(gone.status==EXR_OK && gone.w3_font_count==1);reader_result_free(&gone);
    importing.w3_path=fallback;added=run(reader,importing);REQUIRE(added.status==EXR_OK && added.w3_font_count==2);reader_result_free(&added);
  }
  PASS("font_in_use_removal_refused_and_unused_removed");
  /* A stored font changed on disk is an anomaly: the previous font and page stay usable. */
  {
    char *directory=g_path_get_dirname(library_a),*stored=g_strconcat(directory,"/fonts/",fallback_hash,".font",NULL);
    gchar *bytes=NULL;gsize size=0;REQUIRE(g_file_get_contents(stored,&bytes,&size,NULL) && size>16);bytes[size/2]^=0x55;
    REQUIRE(g_file_set_contents(stored,bytes,(gssize)size,NULL));g_free(bytes);g_free(stored);g_free(directory);
    use.w3_hash=fallback_hash;reader_result broken=run(reader,use);
    REQUIRE(broken.status!=EXR_OK && !broken.has_frame && strstr(broken.message,"previous"));reader_result_free(&broken);
    reader_result still=run(reader,command(READER_PREVIOUS,book));REQUIRE(still.status==EXR_OK && still.has_frame);
    landed=commit(reader,&still);REQUIRE(!strcmp(landed.w3_font_active,primary_hash));reader_result_free(&landed);reader_result_free(&still);
  }
  PASS("font_corrupt_stored_font_keeps_previous_font_and_reading");
  linux_reader_close(reader);reader=NULL;
  REQUIRE(linux_reader_open(library_a,font,&control,&reader,&error)==EXR_OK);
  {
    reader_command reopen=command(READER_OPEN,book);reopen.font=24;reader_result frame=run(reader,reopen);REQUIRE(frame.status==EXR_OK && frame.has_frame);
    landed=commit(reader,&frame);REQUIRE(landed.has_w3 && !strcmp(landed.w3_font_active,primary_hash));reader_result_free(&landed);reader_result_free(&frame);
  }
  PASS("font_selection_survives_process_reopen");

  /* 3. Original export: byte-identical, duplicate-safe, refuses an unusable folder. */
  {
    char *out=g_build_filename(work,"exported",NULL);REQUIRE(g_mkdir_with_parents(out,0700)==0);
    reader_command exporting=command(READER_W3_EXPORT,book);exporting.w3_path=out;
    reader_result done=run(reader,exporting);REQUIRE(done.status==EXR_OK && done.w3_export_created && done.w3_export_durable && done.w3_export_path[0]);
    gchar *original=NULL,*copy=NULL;gsize original_size=0,copy_size=0;
    REQUIRE(g_file_get_contents(text_path,&original,&original_size,NULL) && g_file_get_contents(done.w3_export_path,&copy,&copy_size,NULL));
    REQUIRE(original_size==copy_size && !memcmp(original,copy,original_size) && done.w3_export_bytes==original_size);g_free(original);g_free(copy);
    reader_result_free(&done);done=run(reader,exporting);REQUIRE(done.status==EXR_OK && !done.w3_export_created && strstr(done.message,"already"));reader_result_free(&done);
    exporting.w3_path="/nonexistent/exreader-wave3";done=run(reader,exporting);REQUIRE(done.status!=EXR_OK && !done.has_frame);reader_result_free(&done);
    reader_result still=run(reader,command(READER_NEXT,book));REQUIRE(still.status==EXR_OK && still.has_frame);landed=commit(reader,&still);reader_result_free(&landed);reader_result_free(&still);
    g_free(out);
  }
  PASS("original_export_byte_identity_duplicate_and_failure");

  /* 4. Sync status with no session is explicit text, never an invented state. */
  {
    reader_result status=run(reader,command(READER_W3_SYNC_STATUS,book));REQUIRE(status.status==EXR_OK && status.w3_sync_text && strstr(status.w3_sync_text,"No sync session"));
    reader_result_free(&status);
  }
  PASS("sync_status_without_session_is_explicit");
  linux_reader_close(reader);reader=NULL;

  /* 5. Annotation export from library A, preview then confirmed import into library B. */
  {
    char *directory=g_path_get_dirname(library_a),*product=g_strconcat(library_a,".product.sqlite",NULL),*jsonl=g_build_filename(work,"annotations.jsonl",NULL);
    g_free(directory);reader_revisions *store=NULL;REQUIRE(reader_revisions_open(product,&store,NULL)==READER_REV_OK);
    reader_annotation_export_options options={0};options.struct_size=sizeof(options);options.revisions=store;options.book_key=key;options.jsonl_path=jsonl;
    reader_annotation_export_stats stats={0};reader_annotation_export_error problem={0};
    REQUIRE(reader_annotation_export_run(&options,&stats,&problem)==READER_ANNOTATION_EXPORT_OK && stats.annotations==2 && stats.jsonl_published);
    REQUIRE(reader_revisions_close(&store,NULL)==READER_REV_OK);g_free(product);
    REQUIRE(linux_reader_open(library_b,font,&control,&reader,&error)==EXR_OK);
    int64_t imported=open_book(reader,READER_IMPORT,text_path,0,&landed);reader_result_free(&landed);
    reader_command listing=command(READER_RECORDS_LIST,imported);reader_result empty=run(reader,listing);
    REQUIRE(empty.status==EXR_OK && empty.records_page.count==0 && !strcmp(empty.records_key,key));reader_result_free(&empty);
    reader_command preview=command(READER_W3_ANNOTATION_PREVIEW,imported);preview.w3_path=jsonl;
    reader_result checked=run(reader,preview);
    REQUIRE(checked.status==EXR_OK && checked.w3_ann_validated && checked.w3_ann_annotations==2 && checked.w3_ann_heads==2 && !checked.w3_ann_committed);
    reader_result_free(&checked);empty=run(reader,listing);REQUIRE(empty.status==EXR_OK && empty.records_page.count==0);reader_result_free(&empty);
    PASS("annotation_preview_validates_without_writing");
    reader_command confirm=command(READER_W3_ANNOTATION_IMPORT,imported);confirm.w3_path=jsonl;
    reader_result done=run(reader,confirm);
    REQUIRE(done.status==EXR_OK && done.w3_ann_committed==2 && done.w3_ann_created==2 && done.w3_ann_duplicates==0);reader_result_free(&done);
    reader_result listed=run(reader,listing);REQUIRE(listed.status==EXR_OK && listed.records_page.count==2);reader_result_free(&listed);
    done=run(reader,confirm);REQUIRE(done.status==EXR_OK && done.w3_ann_created==0 && done.w3_ann_duplicates==2);reader_result_free(&done);
    PASS("annotation_confirmed_import_and_exact_retry");
    int64_t other=open_book(reader,READER_IMPORT,other_path,0,&landed);reader_result_free(&landed);
    reader_command mismatch=command(READER_W3_ANNOTATION_PREVIEW,other);mismatch.w3_path=jsonl;
    reader_result refused=run(reader,mismatch);REQUIRE(refused.status!=EXR_OK && !refused.w3_ann_validated && strstr(refused.message,"refused"));reader_result_free(&refused);
    gchar *content=NULL;gsize size=0;REQUIRE(g_file_get_contents(jsonl,&content,&size,NULL));
    char *broken=g_build_filename(work,"broken.jsonl",NULL);REQUIRE(g_file_set_contents(broken,content,(gssize)(size-12),NULL));g_free(content);
    mismatch.book=imported;mismatch.w3_path=broken;
    {
      reader_command back=command(READER_OPEN,imported);back.font=24;reader_result frame=run(reader,back);REQUIRE(frame.status==EXR_OK);reader_result opened=commit(reader,&frame);reader_result_free(&opened);reader_result_free(&frame);
    }
    refused=run(reader,mismatch);REQUIRE(refused.status!=EXR_OK && !refused.w3_ann_validated);reader_result_free(&refused);
    listed=run(reader,listing);REQUIRE(listed.status==EXR_OK && listed.records_page.count==2);reader_result_free(&listed);
    PASS("annotation_wrong_book_and_truncated_file_refused_without_commit");
    g_free(broken);g_free(jsonl);linux_reader_close(reader);
  }
  g_free(primary);g_free(fallback);g_free(text_path);g_free(other_path);
  printf("{\"backend_checks\":%u}\n",checks);return 0;
}
