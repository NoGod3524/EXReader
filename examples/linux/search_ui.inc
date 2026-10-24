/* SPDX-License-Identifier: MIT */
/* Pure UI values cross the existing SDK-owner queue; no SDK handle lives here. */
#include <reader_search.h>
static void inbook_progress(void *unused);
static struct {
  GtkWidget *dialog,*content,*entry,*list,*status,*start,*more,*cancel,*return_focus;
  gboolean running,complete,has_owner,suppress_focus;
  uint64_t token;
  size_t count;
  unsigned actions,closed;
  int code,match;
  reader_search_control control;
} inbook={.control={.changed=inbook_progress}};
static gboolean inbook_progress_idle(gpointer unused) { (void)unused;state();return G_SOURCE_REMOVE; }
static void inbook_progress(void *unused) { (void)unused;g_idle_add(inbook_progress_idle,NULL); }
static gboolean inbook_opened(void) { return inbook.dialog!=NULL; }
static void inbook_message(const char *message) {
  if(inbook.status) { gtk_label_set_text(GTK_LABEL(inbook.status),message);atk_object_set_name(gtk_widget_get_accessible(inbook.status),message); }
}
static void inbook_controls(void) {
  if(!inbook.dialog) return;
  gtk_widget_set_sensitive(inbook.entry,!inbook.running);gtk_widget_set_sensitive(inbook.start,!inbook.running);
  gtk_widget_set_sensitive(inbook.more,!inbook.running && !inbook.complete);
  gtk_widget_set_sensitive(inbook.cancel,inbook.running);gtk_widget_set_sensitive(inbook.list,!inbook.running);
}
static void inbook_clear_rows(void) {
  if(inbook.list) {
    GList *rows=gtk_container_get_children(GTK_CONTAINER(inbook.list));
    for(GList *row=rows;row;row=row->next) gtk_widget_destroy(row->data);
    g_list_free(rows);
  }
  inbook.count=0;inbook.complete=TRUE;
}
static void inbook_release(void) {
  if(inbook.running) { g_atomic_int_inc(&generation);busy=FALSE;inbook.running=FALSE; }
  if(inbook.has_owner) {
    host_job *job=g_new0(host_job,1);job->generation=g_atomic_int_get(&generation);
    job->command.action=READER_SEARCH_CLOSE;job->command.search_token=inbook.token;g_async_queue_push(queue,job);
  }
  inbook.has_owner=FALSE;inbook.token++;
}
static void inbook_destroyed(GtkWidget *widget,gpointer unused) {
  (void)widget;(void)unused;inbook.dialog=inbook.entry=inbook.list=inbook.status=NULL;
  if(inbook.content) gtk_widget_set_sensitive(inbook.content,TRUE);
  inbook.content=NULL;
  if(!closing && !inbook.suppress_focus) {
    gtk_window_present(GTK_WINDOW(window));
    if(inbook.return_focus && gtk_widget_get_toplevel(inbook.return_focus)==window &&
       gtk_widget_get_visible(inbook.return_focus) && gtk_widget_is_sensitive(inbook.return_focus)) gtk_widget_grab_focus(inbook.return_focus);
    else gtk_widget_grab_focus(text);
  }
  g_clear_object(&inbook.return_focus);state();
}
static void inbook_close(void) {
  inbook_release();inbook_clear_rows();inbook.closed++;
  if(inbook.dialog) gtk_widget_destroy(inbook.dialog);
}
static gboolean inbook_delete(GtkWidget *widget,GdkEvent *event,gpointer unused) {
  (void)widget;(void)event;(void)unused;inbook_close();return TRUE;
}
static void inbook_response(GtkDialog *dialog,int response,gpointer unused) {
  (void)dialog;(void)response;(void)unused;inbook_close();
}
static gboolean inbook_background(GtkWidget *widget,GdkEventWindowState *event,gpointer unused) {
  (void)widget;(void)unused;
  if(inbook.dialog && (event->new_window_state&(GDK_WINDOW_STATE_ICONIFIED|GDK_WINDOW_STATE_WITHDRAWN))) {
    inbook.suppress_focus=TRUE;inbook_close();inbook.suppress_focus=FALSE;
  }
  return FALSE;
}
static void inbook_queue(reader_action action,size_t index) {
  if(inbook.running || !inbook.dialog || busy || saving || save_failed || !book_id) return;
  host_job *job=g_new0(host_job,1);job->generation=g_atomic_int_add(&generation,1)+1;
  job->command.action=action;job->command.book=book_id;job->command.part=part;job->command.page=page_number;
  if(action==READER_SEARCH_BEGIN) { inbook_release();inbook_clear_rows();inbook.token++; }
  job->command.search_token=inbook.token;job->command.search_index=index;
  g_atomic_int_set(&inbook.control.request,job->generation);g_atomic_int_set(&inbook.control.phase,0);g_atomic_int_set(&inbook.control.polls,0);
  job->command.search_control=&inbook.control;job->command.search_request=job->generation;
  if(action==READER_SEARCH_BEGIN) job->command.search_query=g_strdup(gtk_entry_get_text(GTK_ENTRY(inbook.entry)));
  inbook.has_owner=TRUE;inbook.running=TRUE;inbook.actions++;busy=TRUE;
  inbook_controls();inbook_message(action==READER_SEARCH_CHOOSE ? "Resolving selected result…":"Searching…");
  g_async_queue_push(queue,job);state();
}
static void inbook_start(GtkWidget *button,gpointer unused) { (void)button;(void)unused;inbook_queue(READER_SEARCH_BEGIN,0); }
static void inbook_more(GtkWidget *button,gpointer unused) { (void)button;(void)unused;inbook_queue(READER_SEARCH_NEXT,0); }
static void inbook_cancel(GtkWidget *button,gpointer unused) {
  (void)button;(void)unused;inbook_release();inbook_clear_rows();inbook.code=READER_SEARCH_CANCELLED;
  inbook_controls();inbook_message("Search cancelled. Search again to restart");state();
}
static void inbook_changed(GtkEditable *entry,gpointer unused) {
  (void)entry;(void)unused;if(inbook.running) return;
  inbook_release();inbook_clear_rows();inbook_controls();inbook_message("Literal, case-sensitive text. Search when ready");state();
}
static void inbook_choose(GtkListBox *list,GtkListBoxRow *row,gpointer unused) {
  (void)list;(void)unused;
  if(row && gtk_widget_get_parent(GTK_WIDGET(row))==inbook.list)
    inbook_queue(READER_SEARCH_CHOOSE,GPOINTER_TO_SIZE(g_object_get_data(G_OBJECT(row),"result-index")));
}
static void inbook_open(GtkWidget *button,gpointer unused) {
  (void)button;(void)unused;
  if(closing || busy || saving || save_failed || inbook.dialog || !book_id) return;
#ifdef EXR_READER_PREFERENCES_UI
  if(preferences_opened()) return;
#endif
#ifdef EXR_READER_ACCOUNT
  if(accounts_opened()) return;
#endif
#ifdef EXR_READER_DESKTOP_METADATA
  if(metadata_dialog || metadata_running || collections_opened()) return;
#endif
  GtkWidget *focus=gtk_window_get_focus(GTK_WINDOW(window));if(focus) inbook.return_focus=g_object_ref(focus);
  inbook.content=gtk_bin_get_child(GTK_BIN(window));gtk_widget_set_sensitive(inbook.content,FALSE);
  inbook.dialog=gtk_dialog_new_with_buttons("Search within book",GTK_WINDOW(window),GTK_DIALOG_MODAL|GTK_DIALOG_DESTROY_WITH_PARENT,"_Close",GTK_RESPONSE_CLOSE,NULL);
  GtkWindowGroup *group=gtk_window_group_new();gtk_window_group_add_window(group,GTK_WINDOW(inbook.dialog));g_object_unref(group);
  GtkWidget *area=gtk_dialog_get_content_area(GTK_DIALOG(inbook.dialog));gtk_container_set_border_width(GTK_CONTAINER(area),12);
  inbook.entry=gtk_entry_new();gtk_entry_set_max_length(GTK_ENTRY(inbook.entry),4096);
  gtk_entry_set_placeholder_text(GTK_ENTRY(inbook.entry),"Text to find · up to 4096 UTF-8 bytes");atk_object_set_name(gtk_widget_get_accessible(inbook.entry),"In-book query");
  gtk_box_pack_start(GTK_BOX(area),inbook.entry,FALSE,FALSE,4);
  GtkWidget *actions=gtk_box_new(GTK_ORIENTATION_HORIZONTAL,6);gtk_box_pack_start(GTK_BOX(area),actions,FALSE,FALSE,4);
  inbook.start=gtk_button_new_with_mnemonic("_Search");inbook.more=gtk_button_new_with_mnemonic("_More results");inbook.cancel=gtk_button_new_with_mnemonic("Ca_ncel search");
  GtkWidget *buttons[]={inbook.start,inbook.more,inbook.cancel};
  for(size_t i=0;i<G_N_ELEMENTS(buttons);i++) gtk_box_pack_start(GTK_BOX(actions),buttons[i],FALSE,FALSE,0);
  inbook.status=gtk_label_new("");gtk_label_set_line_wrap(GTK_LABEL(inbook.status),TRUE);gtk_box_pack_start(GTK_BOX(area),inbook.status,FALSE,FALSE,4);
  inbook.list=gtk_list_box_new();gtk_list_box_set_activate_on_single_click(GTK_LIST_BOX(inbook.list),TRUE);atk_object_set_name(gtk_widget_get_accessible(inbook.list),"In-book results");
  GtkWidget *view=gtk_scrolled_window_new(NULL,NULL);gtk_widget_set_size_request(view,480,300);gtk_container_add(GTK_CONTAINER(view),inbook.list);
  atk_object_set_name(gtk_widget_get_accessible(view),"In-book result page");gtk_box_pack_start(GTK_BOX(area),view,TRUE,TRUE,4);
  g_signal_connect(inbook.start,"clicked",G_CALLBACK(inbook_start),NULL);g_signal_connect(inbook.more,"clicked",G_CALLBACK(inbook_more),NULL);
  g_signal_connect(inbook.cancel,"clicked",G_CALLBACK(inbook_cancel),NULL);g_signal_connect(inbook.entry,"changed",G_CALLBACK(inbook_changed),NULL);
  g_signal_connect(inbook.entry,"activate",G_CALLBACK(inbook_start),NULL);g_signal_connect(inbook.list,"row-activated",G_CALLBACK(inbook_choose),NULL);
  g_signal_connect(inbook.dialog,"destroy",G_CALLBACK(inbook_destroyed),NULL);g_signal_connect(inbook.dialog,"delete-event",G_CALLBACK(inbook_delete),NULL);
  g_signal_connect(inbook.dialog,"response",G_CALLBACK(inbook_response),NULL);g_signal_connect(inbook.dialog,"window-state-event",G_CALLBACK(inbook_background),NULL);
  inbook.complete=TRUE;inbook.code=inbook.match=0;inbook_message("Literal, case-sensitive text. Search when ready");inbook_controls();
  gtk_widget_show_all(inbook.dialog);gtk_widget_grab_focus(inbook.entry);state();
}
/* TRUE means this read-only result is fully consumed; FOUND continues through
   the existing page-acceptance and position-COMMIT path with the current control. */
static gboolean inbook_apply(host_result *done) {
  reader_result *result=&done->value;
  if(done->action==READER_SEARCH_CLOSE) return TRUE;
  if(done->generation!=g_atomic_int_get(&generation) || !inbook.dialog || result->search_token!=inbook.token) return TRUE;
  inbook.running=FALSE;inbook.code=result->search_code;inbook.match=result->search_match;
  if(done->action==READER_SEARCH_CHOOSE && result->status==EXR_OK && result->has_frame && result->search_match==EXR_ANCHOR_FOUND) {
    inbook.has_owner=FALSE;gtk_widget_destroy(inbook.dialog);return FALSE;
  }
  busy=FALSE;
  if(done->action!=READER_SEARCH_CHOOSE) {
    inbook_clear_rows();inbook.complete=result->search_complete;
    if(result->status==EXR_OK) for(size_t i=0;i<result->search_count;i++) {
      GtkWidget *row=gtk_list_box_row_new();char *name=g_strdup_printf("Search result %zu: %s",i+1,result->search_rows[i].label);
      GtkWidget *label=gtk_label_new(name);gtk_label_set_xalign(GTK_LABEL(label),0);gtk_label_set_line_wrap(GTK_LABEL(label),TRUE);
      gtk_container_add(GTK_CONTAINER(row),label);atk_object_set_name(gtk_widget_get_accessible(row),name);g_free(name);
      g_object_set_data(G_OBJECT(row),"result-index",GSIZE_TO_POINTER(i));gtk_container_add(GTK_CONTAINER(inbook.list),row);inbook.count++;
    }
    gtk_widget_show_all(inbook.list);
  }
  inbook_controls();inbook_message(result->message);state();return TRUE;
}
static char *inbook_observation(void) {
  return g_strdup_printf("[inbook_search]\nvisible=%d\nrunning=%d\ncomplete=%d\ncount=%zu\ntoken=%"G_GUINT64_FORMAT"\ncode=%d\nmatch=%d\nactions=%u\nclosed=%u\nphase=%d\npolls=%d\n",
    inbook.dialog!=NULL,inbook.running,inbook.complete,inbook.count,inbook.token,inbook.code,inbook.match,inbook.actions,inbook.closed,
    g_atomic_int_get(&inbook.control.phase),g_atomic_int_get(&inbook.control.polls));
}
