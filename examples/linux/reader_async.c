/* SPDX-License-Identifier: MIT */
#include <gtk/gtk.h>
#include "reading.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static GtkWidget *window,*image,*label,*shelf,*notes,*text,*comment,*stack;
static size_t book_count,page_number,page_start,page_end,note_count,selection_start,selection_end,part;
static int64_t book_id;
static int font_size=24,last_error,bounded;
static guint sequence;
static char *home,*settings_path,*state_path,*page_text;
static GKeyFile *settings;
static GAsyncQueue *queue;
static GThread *thread;
static gint generation=1;
static int worker_generation;
static gboolean busy,saving,save_failed,closing,close_after_save;
static gboolean choosing_file;
typedef struct { reader_command command;char *path,*comment;int generation,stop; } host_job;
typedef struct { reader_result value;reader_action action;int generation; } host_result;
static void stop_worker(void);

static void state(void) {
  if(!state_path) return;
  GtkTextIter a,b;size_t selected=0;
  if(gtk_text_buffer_get_selection_bounds(gtk_text_view_get_buffer(GTK_TEXT_VIEW(text)),&a,&b))
    selected=(size_t)(gtk_text_iter_get_offset(&b)-gtk_text_iter_get_offset(&a));
  char *data=g_strdup_printf("[host]\nsequence=%u\nerror=%d\nbook=%"G_GINT64_FORMAT"\nbooks=%zu\npage=%zu\nstart=%zu\nend=%zu\nfont=%d\nnotes=%zu\nselected=%zu\nselection_start=%zu\nselection_end=%zu\nvisible=%d\nfocused=%d\nbounded=%d\npart=%zu\nbusy=%d\nsaving=%d\ngeneration=%d\nsave_failed=%d\n",
    ++sequence,last_error,book_id,book_count,page_number,page_start,page_end,font_size,note_count,selected,
    selection_start,selection_end,gtk_widget_get_visible(window),gtk_window_is_active(GTK_WINDOW(window)),
    bounded,part,busy,saving,g_atomic_int_get(&generation),save_failed);
  g_file_set_contents(state_path,data,-1,NULL);g_free(data);
}
static void status(exr_status code,const char *message) {
  last_error=(int)code;gtk_label_set_text(GTK_LABEL(label),message);state();
}
static gboolean save_settings(void) {
  GError *error=NULL;
  g_key_file_set_int64(settings,"reader","book",book_id);g_key_file_set_integer(settings,"reader","font",font_size);
  if(!g_key_file_save_to_file(settings,settings_path,&error)) {
    status(EXR_IO,"Could not save reading settings");g_clear_error(&error);return FALSE;
  }
  return TRUE;
}
static void rows_clear(GtkWidget *box) {
  GList *children=gtk_container_get_children(GTK_CONTAINER(box));
  for(GList *p=children;p;p=p->next) gtk_widget_destroy(GTK_WIDGET(p->data));
  g_list_free(children);
}
static void shelf_present(reader_result *result) {
  rows_clear(shelf);book_count=result->book_count;
  for(size_t i=0;i<result->book_count;i++) {
    GtkWidget *row=gtk_list_box_row_new(),*title=gtk_label_new(result->books[i].title);
    int64_t *id=g_new(int64_t,1);*id=result->books[i].id;g_object_set_data_full(G_OBJECT(row),"book-id",id,g_free);
    gtk_container_add(GTK_CONTAINER(row),title);gtk_container_add(GTK_CONTAINER(shelf),row);
  }
  gtk_widget_show_all(shelf);
}
static void notes_present(reader_result *result) {
  rows_clear(notes);note_count=result->note_count;
  for(size_t i=0;i<result->note_count;i++) {
    GtkWidget *row=gtk_list_box_row_new(),*title=gtk_label_new(result->notes[i].text);
    int64_t *id=g_new(int64_t,1);*id=result->notes[i].id;g_object_set_data_full(G_OBJECT(row),"note-id",id,g_free);
    gtk_label_set_ellipsize(GTK_LABEL(title),PANGO_ELLIPSIZE_END);
    gtk_container_add(GTK_CONTAINER(row),title);gtk_container_add(GTK_CONTAINER(notes),row);
  }
  gtk_widget_show_all(notes);
}
static void job_free(host_job *job) { g_free(job->path);g_free(job->comment);g_free(job); }
static void queue_commit(void) {
  host_job *job=g_new0(host_job,1);job->generation=g_atomic_int_get(&generation);
  job->command.action=READER_COMMIT;job->command.book=book_id;job->command.part=part;job->command.start=page_start;
  busy=saving=TRUE;g_async_queue_push(queue,job);state();
}
static void pixels_free(guchar *pixels,gpointer unused) { (void)unused;free(pixels); }
static gboolean apply_result(gpointer data) {
  host_result *done=data;reader_result *result=&done->value;
  if(done->generation!=g_atomic_int_get(&generation)) goto free_result;
  busy=FALSE;
  if(result->has_shelf) shelf_present(result);
  if(done->action==READER_COMMIT) {
    saving=FALSE;save_failed=result->status!=EXR_OK;
    if(save_failed) { close_after_save=FALSE;status(result->status,"Position save failed; F12 retries, book switch and close are blocked"); }
    else { state();if(close_after_save) stop_worker(); }
    goto free_result;
  }
  if(result->status!=EXR_OK) { status(result->status,result->message);goto free_result; }
  if(result->has_frame) {
    GdkPixbuf *pixels=gdk_pixbuf_new_from_data(result->pixels,GDK_COLORSPACE_RGB,TRUE,8,
      (int)result->width,(int)result->height,(int)result->stride,pixels_free,NULL);
    if(!pixels) { status(EXR_MEMORY,"Page presentation failed; accepted page retained");goto free_result; }
    notes_present(result);
    result->pixels=NULL;gtk_image_set_from_pixbuf(GTK_IMAGE(image),pixels);g_object_unref(pixels);
    book_id=result->book;part=result->part;bounded=result->bounded;font_size=result->font;
    page_number=result->page;page_start=result->start;page_end=result->end;selection_start=selection_end=0;
    g_free(page_text);page_text=result->text;result->text=NULL;
    gtk_text_buffer_set_text(gtk_text_view_get_buffer(GTK_TEXT_VIEW(text)),page_text,(int)result->text_size);
    gtk_stack_set_visible_child_name(GTK_STACK(stack),"reader");
    if(result->select_range) {
      GtkTextBuffer *buffer=gtk_text_view_get_buffer(GTK_TEXT_VIEW(text));GtkTextIter a,b;size_t end=MIN(result->selected_end,page_end);
      if(result->selected_start>=page_start && result->selected_start<=end) {
        gtk_text_buffer_get_iter_at_offset(buffer,&a,(int)g_utf8_pointer_to_offset(page_text,page_text+result->selected_start-page_start));
        gtk_text_buffer_get_iter_at_offset(buffer,&b,(int)g_utf8_pointer_to_offset(page_text,page_text+end-page_start));
        gtk_text_buffer_select_range(buffer,&a,&b);selection_start=result->selected_start;selection_end=end;
      }
    }
    g_print("FRAME book=%"G_GINT64_FORMAT" bounded=%d part=%zu page=%zu start=%zu end=%zu text=%zu bitmap=%zu index=%zu workspace=%zu evicted=%zu generation=%d\n",
      book_id,bounded,part,page_number,page_start,page_end,result->text_size,result->stride*result->height,
      result->chapter.index_bytes,result->chapter.peak_parse_workspace_bytes,result->chapter.windows_evicted,done->generation);
    status(EXR_OK,result->message);save_settings();queue_commit();
  } else {
    notes_present(result);
    selection_start=result->selected_start;selection_end=result->selected_end;status(EXR_OK,result->message);
  }
free_result:
  reader_result_free(result);g_free(done);return G_SOURCE_REMOVE;
}
static gboolean worker_stopped(gpointer unused) { (void)unused;gtk_widget_destroy(window);return G_SOURCE_REMOVE; }
static int worker_cancelled(void *unused) { (void)unused;return worker_generation!=g_atomic_int_get(&generation); }
static gpointer work(gpointer font_path) {
  linux_reader *reader=NULL;exr_error error={0};char *database=g_build_filename(home,"library.sqlite",NULL);
  exr_control control={worker_cancelled,NULL,NULL};exr_status opened=linux_reader_open(database,font_path,&control,&reader,&error);
  g_free(database);g_free(font_path);
  for(;;) {
    host_job *job=g_async_queue_pop(queue);if(job->stop) { job_free(job);break; }
    if(job->command.action!=READER_COMMIT && job->generation!=g_atomic_int_get(&generation)) { job_free(job);continue; }
    worker_generation=job->command.action==READER_COMMIT ? g_atomic_int_get(&generation):job->generation;
    host_result *result=g_new0(host_result,1);result->generation=job->generation;result->action=job->command.action;
    if(opened==EXR_OK) linux_reader_execute(reader,&job->command,&result->value);
    else { result->value.status=opened;strcpy(result->value.message,"Could not open library or font"); }
    g_idle_add(apply_result,result);job_free(job);
  }
  linux_reader_close(reader);g_idle_add(worker_stopped,NULL);return NULL;
}
static void submit(reader_action action,int64_t id,const char *path,int size) {
  if(closing) return;
  if(save_failed) { status(EXR_DATABASE,"Position was not saved; F12 retries before leaving");return; }
  if(busy) { status(EXR_OK,"Reading operation in progress; current page retained");return; }
  host_job *job=g_new0(host_job,1);job->generation=g_atomic_int_add(&generation,1)+1;
  job->command.action=action;job->command.book=id;job->command.part=part;job->command.font=size;
  if(path) { job->path=g_strdup(path);job->command.path=job->path; }
  if(action==READER_NOTE_ADD) {
    GtkTextIter a,b;GtkTextBuffer *buffer=gtk_text_view_get_buffer(GTK_TEXT_VIEW(text));
    if(!page_text || !gtk_text_buffer_get_selection_bounds(buffer,&a,&b)) { job_free(job);status(EXR_ARGUMENT,"Select page text first");return; }
    job->command.start=page_start+(size_t)(g_utf8_offset_to_pointer(page_text,gtk_text_iter_get_offset(&a))-page_text);
    job->command.end=page_start+(size_t)(g_utf8_offset_to_pointer(page_text,gtk_text_iter_get_offset(&b))-page_text);
    job->comment=g_strdup(gtk_entry_get_text(GTK_ENTRY(comment)));job->command.comment=job->comment;
  }
  if(action==READER_NOTE_REMOVE || action==READER_NOTE_JUMP) {
    GtkListBoxRow *row=gtk_list_box_get_selected_row(GTK_LIST_BOX(notes));
    if(!row) { job_free(job);status(EXR_ARGUMENT,"Select a note first");return; }
    int64_t *note=g_object_get_data(G_OBJECT(row),"note-id");job->command.note=*note;
  }
  busy=TRUE;status(EXR_OK,"Reading in worker");g_async_queue_push(queue,job);
}
static void open_id(int64_t id) { submit(READER_OPEN,id,NULL,font_size); }
static void import_dialog(void) {
  if(busy || closing || save_failed) { state();return; }
  GtkWidget *dialog=gtk_file_chooser_dialog_new("Import book",GTK_WINDOW(window),GTK_FILE_CHOOSER_ACTION_OPEN,
    "Cancel",GTK_RESPONSE_CANCEL,"Import",GTK_RESPONSE_ACCEPT,NULL);
  choosing_file=TRUE;
  int response=gtk_dialog_run(GTK_DIALOG(dialog));choosing_file=FALSE;
  if(response==GTK_RESPONSE_ACCEPT) {
    char *path=gtk_file_chooser_get_filename(GTK_FILE_CHOOSER(dialog));gtk_widget_destroy(dialog);
    submit(READER_IMPORT,0,path,font_size);g_free(path);
  } else { gtk_widget_destroy(dialog);state(); }
}
static void focus_list(GtkWidget *box) {
  GtkListBoxRow *row=gtk_list_box_get_selected_row(GTK_LIST_BOX(box));if(!row) row=gtk_list_box_get_row_at_index(GTK_LIST_BOX(box),0);
  if(row) { gtk_list_box_select_row(GTK_LIST_BOX(box),row);gtk_widget_grab_focus(GTK_WIDGET(row)); } else gtk_widget_grab_focus(box);
}
static void action(GtkWidget *widget,gpointer name) {
  (void)widget;const char *a=name;
  if(!strcmp(a,"import")) import_dialog();
  else if(!strcmp(a,"shelf")) { gtk_stack_set_visible_child_name(GTK_STACK(stack),"shelf");focus_list(shelf);state(); }
  else if(!strcmp(a,"previous")) submit(READER_PREVIOUS,book_id,NULL,font_size);
  else if(!strcmp(a,"next")) submit(READER_NEXT,book_id,NULL,font_size);
  else if(!strcmp(a,"bigger")) submit(READER_FONT,book_id,NULL,font_size+2);
  else if(!strcmp(a,"smaller")) submit(READER_FONT,book_id,NULL,font_size-2);
  else if(!strcmp(a,"text")) { gtk_widget_grab_focus(text);state(); }
  else if(!strcmp(a,"note")) submit(READER_NOTE_ADD,book_id,NULL,font_size);
  else if(!strcmp(a,"notes")) { focus_list(notes);state(); }
  else if(!strcmp(a,"delete")) submit(READER_NOTE_REMOVE,book_id,NULL,font_size);
  else if(!strcmp(a,"comment")) { gtk_widget_grab_focus(comment);state(); }
  else if(!strcmp(a,"save")) { if(!busy && save_failed && book_id) queue_commit(); }
  else if(!strcmp(a,"cancel") && busy && !saving) {
    g_atomic_int_inc(&generation);busy=FALSE;status(EXR_CANCELLED,"Cancellation requested; accepted position retained");
  }
}
static gboolean key(GtkWidget *w,GdkEventKey *event,gpointer unused) {
  (void)w;(void)unused;
  if(choosing_file) return FALSE;
  static const char *names[]={"import","shelf","previous","next","bigger","smaller","text","note","notes","delete","comment","save"};
  if(event->state & (GDK_CONTROL_MASK|GDK_MOD1_MASK|GDK_SUPER_MASK)) return FALSE;
  if(event->keyval==GDK_KEY_Escape) { action(NULL,"cancel");return TRUE; }
  if(event->keyval>=GDK_KEY_F1 && event->keyval<=GDK_KEY_F12) { action(NULL,(gpointer)names[event->keyval-GDK_KEY_F1]);return TRUE; }
  return FALSE;
}
static void shelf_activated(GtkListBox *box,GtkListBoxRow *row,gpointer unused) {
  (void)box;(void)unused;int64_t *id=g_object_get_data(G_OBJECT(row),"book-id");open_id(*id);
}
static void note_activated(GtkListBox *box,GtkListBoxRow *row,gpointer unused) {
  (void)box;(void)row;(void)unused;submit(READER_NOTE_JUMP,book_id,NULL,font_size);
}
static gboolean focus_changed(GtkWidget *w,GdkEventFocus *event,gpointer unused) {
  (void)w;(void)event;(void)unused;state();return FALSE;
}
static void stop_worker(void) {
  if(closing) return;
  closing=TRUE;g_atomic_int_inc(&generation);host_job *stop=g_new0(host_job,1);stop->stop=1;g_async_queue_push(queue,stop);state();
}
static gboolean close_window(GtkWidget *w,GdkEvent *event,gpointer unused) {
  (void)w;(void)event;(void)unused;
  if(save_failed) { if(!busy) queue_commit();status(EXR_DATABASE,"Retrying position; close again after success");return TRUE; }
  if(!save_settings()) return TRUE;
  if(saving) close_after_save=TRUE;else stop_worker();return TRUE;
}
static void destroyed(GtkWidget *w,gpointer unused) { (void)w;(void)unused;gtk_main_quit(); }
static void selection_changed(GtkTextBuffer *buffer,GtkTextIter *iter,GtkTextMark *mark,gpointer unused) {
  (void)buffer;(void)iter;(void)mark;(void)unused;state();
}
static GtkWidget *scroll(GtkWidget *child) {
  GtkWidget *s=gtk_scrolled_window_new(NULL,NULL);gtk_container_add(GTK_CONTAINER(s),child);return s;
}

int main(int argc,char **argv) {
  if(argc==2 && !strcmp(argv[1],"--version")) { printf("%s %u\n",exr_version(),exr_abi_version());return 0; }
  if(argc!=1 && argc!=3 && argc!=4) { fprintf(stderr,"Usage: exreader-linux [FONT STATE_DIRECTORY [OBSERVATION_FILE]]\n");return 2; }
  char *font_path=NULL;
  if(argc==1) {
    char *executable=g_file_read_link("/proc/self/exe",NULL);if(!executable) return 2;
    char *bin=g_path_get_dirname(executable),*package=g_path_get_dirname(bin);
    font_path=g_build_filename(package,"Reader.otf",NULL);g_free(executable);g_free(bin);g_free(package);
    home=g_build_filename(g_get_user_data_dir(),"exreader",NULL);
  } else { home=g_strdup(argv[2]);font_path=g_strdup(argv[1]); }
  state_path=argc==4 ? g_strdup(argv[3]):NULL;if(g_mkdir_with_parents(home,0700)) return 2;
  settings_path=g_build_filename(home,"reader.ini",NULL);settings=g_key_file_new();
  g_key_file_load_from_file(settings,settings_path,G_KEY_FILE_NONE,NULL);
  int size=g_key_file_get_integer(settings,"reader","font",NULL);if(size>=12 && size<=48) font_size=size;
  int64_t last=g_key_file_get_int64(settings,"reader","book",NULL);
  gtk_init(NULL,NULL);window=gtk_window_new(GTK_WINDOW_TOPLEVEL);
  gtk_window_set_title(GTK_WINDOW(window),"EXReader Linux");gtk_window_set_default_size(GTK_WINDOW(window),1040,820);
  GtkWidget *root=gtk_box_new(GTK_ORIENTATION_VERTICAL,6),*toolbar=gtk_box_new(GTK_ORIENTATION_HORIZONTAL,4);
  gtk_container_add(GTK_CONTAINER(window),root);gtk_box_pack_start(GTK_BOX(root),toolbar,FALSE,FALSE,0);
  const char *names[]={"import","shelf","previous","next","bigger","smaller","text","note","notes","delete"};
  const char *titles[]={"Import F1","Shelf F2","Previous F3","Next F4","A+ F5","A− F6","Text F7","Add note F8","Notes F9","Delete F10"};
  for(size_t i=0;i<G_N_ELEMENTS(names);i++) {
    GtkWidget *button=gtk_button_new_with_label(titles[i]);gtk_box_pack_start(GTK_BOX(toolbar),button,FALSE,FALSE,0);
    g_signal_connect(button,"clicked",G_CALLBACK(action),(gpointer)names[i]);
  }
  label=gtk_label_new("Import a book to start reading");gtk_box_pack_start(GTK_BOX(root),label,FALSE,FALSE,0);
  stack=gtk_stack_new();gtk_box_pack_start(GTK_BOX(root),stack,TRUE,TRUE,0);
  shelf=gtk_list_box_new();gtk_list_box_set_activate_on_single_click(GTK_LIST_BOX(shelf),TRUE);
  atk_object_set_name(gtk_widget_get_accessible(shelf),"Bookshelf");
  gtk_stack_add_named(GTK_STACK(stack),scroll(shelf),"shelf");
  GtkWidget *reader=gtk_box_new(GTK_ORIENTATION_HORIZONTAL,8),*right=gtk_box_new(GTK_ORIENTATION_VERTICAL,6);
  image=gtk_image_new();gtk_box_pack_start(GTK_BOX(reader),scroll(image),TRUE,TRUE,0);
  atk_object_set_name(gtk_widget_get_accessible(image),"Rendered page; selectable text is in the adjacent panel");
  text=gtk_text_view_new();gtk_text_view_set_editable(GTK_TEXT_VIEW(text),FALSE);
  atk_object_set_name(gtk_widget_get_accessible(text),"Selectable page text");
  gtk_text_view_set_wrap_mode(GTK_TEXT_VIEW(text),GTK_WRAP_WORD_CHAR);gtk_widget_set_size_request(text,320,250);
  gtk_box_pack_start(GTK_BOX(right),scroll(text),TRUE,TRUE,0);
  comment=gtk_entry_new();gtk_entry_set_placeholder_text(GTK_ENTRY(comment),"Comment (F11); select text, then Add note");
  atk_object_set_name(gtk_widget_get_accessible(comment),"Annotation comment");
  gtk_box_pack_start(GTK_BOX(right),comment,FALSE,FALSE,0);
  notes=gtk_list_box_new();gtk_widget_set_size_request(notes,320,120);
  atk_object_set_name(gtk_widget_get_accessible(notes),"Saved notes; activate to return to selected text");
  gtk_box_pack_start(GTK_BOX(right),scroll(notes),TRUE,TRUE,0);gtk_box_pack_start(GTK_BOX(reader),right,FALSE,FALSE,0);
  gtk_stack_add_named(GTK_STACK(stack),reader,"reader");
  g_signal_connect(window,"key-press-event",G_CALLBACK(key),NULL);
  g_signal_connect(window,"focus-in-event",G_CALLBACK(focus_changed),NULL);
  g_signal_connect(window,"focus-out-event",G_CALLBACK(focus_changed),NULL);
  g_signal_connect(window,"delete-event",G_CALLBACK(close_window),NULL);
  g_signal_connect(window,"destroy",G_CALLBACK(destroyed),NULL);
  g_signal_connect(shelf,"row-activated",G_CALLBACK(shelf_activated),NULL);
  g_signal_connect(notes,"row-activated",G_CALLBACK(note_activated),NULL);
  g_signal_connect(gtk_text_view_get_buffer(GTK_TEXT_VIEW(text)),"mark-set",G_CALLBACK(selection_changed),NULL);
  gtk_widget_show_all(window);gtk_window_present(GTK_WINDOW(window));queue=g_async_queue_new();
  thread=g_thread_new("reading",work,font_path);submit(last ? READER_OPEN:READER_SHELF,last,NULL,font_size);
  state();gtk_main();g_thread_join(thread);g_async_queue_unref(queue);
  g_key_file_free(settings);g_free(home);g_free(settings_path);g_free(state_path);g_free(page_text);return 0;
}
