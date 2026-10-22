/* SPDX-License-Identifier: MIT */
#define _POSIX_C_SOURCE 200809L
#include <gtk/gtk.h>
#include <exreader.h>
#include <stdio.h>
#include <stdlib.h>
static int fail_reads;
static int fail_write;
static exr_status write_progress(exr_library *library,int64_t id,const exr_anchor *anchor,exr_error *error) {
  if(fail_write) { error->code=EXR_DATABASE;return EXR_DATABASE; }
  return exr_library_progress(library,id,anchor,error);
}
static exr_status query_notes(exr_library *library,int64_t id,exr_note **out,size_t *count,exr_error *error) {
  if(fail_reads) { *out=NULL;*count=0;error->code=EXR_DATABASE;return EXR_DATABASE; }
  return exr_library_notes(library,id,out,count,error);
}
#define exr_library_notes query_notes
#define exr_library_progress write_progress
#include "../../examples/linux/reading.c"
#undef exr_library_notes
#undef exr_library_progress
#define main exreader_host_main
#include "../../examples/linux/reader.c"
#undef main
static unsigned checks;
static unsigned publication_events;
static void require(int condition,const char *name) {
  if(!condition) { fprintf(stderr,"FAIL %s\n",name);exit(1); } checks++;
}
static unsigned rows(void) {
  GList *children=gtk_container_get_children(GTK_CONTAINER(notes));unsigned n=g_list_length(children);g_list_free(children);return n;
}
static void publication_changed(GtkTextBuffer *buffer,gpointer unused) {
  (void)buffer;(void)unused;
  require(busy,"frame publication cannot advertise idle before SAVE");publication_events++;
}
static void apply(linux_reader *reader,reader_command command) {
  host_result *result=g_new0(host_result,1);result->action=command.action;result->generation=g_atomic_int_get(&generation);
  busy=TRUE;
  linux_reader_execute(reader,&command,&result->value);apply_result(result);
  if(saving) {
    host_job *job=g_async_queue_pop(queue);host_result *saved=g_new0(host_result,1);
    saved->action=READER_COMMIT;saved->generation=job->generation;
    linux_reader_execute(reader,&job->command,&saved->value);job_free(job);apply_result(saved);
  }
}
int main(int argc,char **argv) {
  linux_reader *reader=NULL;exr_error error={0};reader_command command={0};
  if(argc!=3) return 2;
  gtk_init(NULL,NULL);home=g_strdup(argv[2]);g_mkdir_with_parents(home,0700);
  settings_path=g_build_filename(home,"reader.ini",NULL);settings=g_key_file_new();
  char *database=g_build_filename(home,"library.sqlite",NULL);
  require(linux_reader_open(database,argv[1],NULL,&reader,&error)==EXR_OK,"open installed SDK reader");g_free(database);
  queue=g_async_queue_new();window=gtk_window_new(GTK_WINDOW_TOPLEVEL);label=gtk_label_new("");image=gtk_image_new();
  text=gtk_text_view_new();comment=gtk_entry_new();notes=gtk_list_box_new();shelf=gtk_list_box_new();stack=gtk_stack_new();
  g_signal_connect(gtk_text_view_get_buffer(GTK_TEXT_VIEW(text)),"changed",G_CALLBACK(publication_changed),NULL);
  gtk_stack_add_named(GTK_STACK(stack),gtk_label_new("reader"),"reader");
  const char *body="Reader note body with stable original bytes.";int64_t first=0,second=0,note_id=0;
  require(exr_library_import(reader->library,EXR_TXT,body,strlen(body),"Original",&first,&error)==EXR_OK,"import original");
  require(exr_library_import(reader->library,EXR_TXT,body,strlen(body),"Candidate",&second,&error)==EXR_OK,"import candidate");
  exr_note note={0};note.book_id=first;note.start=0;note.end=6;note.text="existing";
  require(exr_library_note(reader->library,&note,&note_id,&error)==EXR_OK,"persist existing note");
  command.action=READER_OPEN;command.book=first;command.font=24;apply(reader,command);
  require(book_id==first && note_count==1 && rows()==1 && last_error==0,"show original page and note");
  exr_document *old_document=reader->current.document;exr_pager *old_pager=reader->current.pager;
  size_t old_start=page_start,old_end=page_end;GdkPixbuf *old_pixels=gtk_image_get_pixbuf(GTK_IMAGE(image));
  /* A rendered but unaccepted candidate must not move the worker cursor. */
  reader_result candidate={0};command.action=READER_FONT;command.font=26;
  linux_reader_execute(reader,&command,&candidate);
  require(candidate.status==EXR_OK && candidate.has_frame && reader->current.pager==old_pager && reader->current.font==24,
          "unaccepted font candidate retains accepted session");
  reader_result_free(&candidate);command.action=READER_SHELF;linux_reader_execute(reader,&command,&candidate);
  require(!reader->has_pending && reader->current.pager==old_pager,"discard stale candidate without changing cursor");reader_result_free(&candidate);
  fail_reads=1;command.action=READER_OPEN;command.book=first;command.font=24;apply(reader,command);
  require(last_error==EXR_DATABASE && note_count==1 && rows()==1,"failed query retains notes and visible error");
  command.book=second;apply(reader,command);
  require(book_id==first && reader->current.document==old_document && reader->current.pager==old_pager &&
    page_start==old_start && page_end==old_end && gtk_image_get_pixbuf(GTK_IMAGE(image))==old_pixels &&
    last_error==EXR_DATABASE && note_count==1 && rows()==1,"candidate note failure retains accepted page and notes");
  command.book=first;command.action=READER_NOTE_ADD;command.start=0;command.end=6;command.comment="added during refresh failure";
  apply(reader,command);require(last_error==EXR_DATABASE && rows()==1,"add does not mask query failure");
  exr_note *actual=NULL;size_t count=0;
  require(exr_library_notes(reader->library,first,&actual,&count,&error)==EXR_OK && count==2,"both notes remain persisted");
  exr_notes_free(actual,count);command.action=READER_NOTE_REMOVE;command.note=note_id;apply(reader,command);
  require(last_error==EXR_DATABASE && rows()==1,"delete refuses unverified ownership during query failure");
  require(exr_library_notes(reader->library,first,&actual,&count,&error)==EXR_OK && count==2,"failed ownership query deletes no row");
  exr_notes_free(actual,count);fail_reads=0;command.action=READER_OPEN;apply(reader,command);
  require(note_count==2 && rows()==2 && last_error==0,"recover notes after query succeeds");
  command.action=READER_NOTE_REMOVE;apply(reader,command);
  require(note_count==1 && rows()==1 && last_error==0,"verified deletion succeeds");
  fail_write=1;command.action=READER_FONT;command.font=28;apply(reader,command);
  require(save_failed && reader->has_pending && reader->current.font==24 && font_size==28,
          "failed accepted-frame save retains pending and previous committed cursor");
  int before=g_atomic_int_get(&generation);open_id(second);action(NULL,"cancel");
  require(save_failed && book_id==first && g_atomic_int_get(&generation)==before && reader->has_pending,
          "failed save blocks switching and cancellation cannot discard pending");
  fail_write=0;action(NULL,"save");
  require(saving && busy,"F12 queues serialized save retry");
  action(NULL,"cancel");require(saving && busy && g_atomic_int_get(&generation)==before,"escape cannot cancel save barrier");
  host_job *retry=g_async_queue_pop(queue);host_result *saved=g_new0(host_result,1);
  saved->action=READER_COMMIT;saved->generation=retry->generation;
  linux_reader_execute(reader,&retry->command,&saved->value);job_free(retry);apply_result(saved);
  require(!save_failed && !saving && !busy && !reader->has_pending && reader->current.font==28 && last_error==EXR_OK,
          "successful retry promotes exact accepted pending cursor");
  require(publication_events>=3,"real GTK frame publication ordering observed");
  linux_reader_close(reader);g_async_queue_unref(queue);g_key_file_free(settings);g_free(settings_path);g_free(home);g_free(page_text);
  printf("{\"passed\":true,\"checks\":%u,\"kind\":\"GTK note query fault regression\"}\n",checks);return 0;
}
