/* SPDX-License-Identifier: MIT */
#include <reader_batch_import.h>
static struct {
  GtkWidget *dialog,*list,*message,*progress,*cancel,*close,*chooser;
  reader_batch_control control;
  uint64_t token,seen,attempted,imported,duplicates,failed,pending;
  size_t rows,max_rows;
  guint timer;
  int running,done,complete,truncated,cancelled,map,want_close,release_queued,has_owner;
  unsigned actions;
} folder;
static void folder_queue(reader_action action,const char *root,int recursive) {
  host_job *job=g_new0(host_job,1);job->generation=g_atomic_int_get(&generation);
  job->command.action=action;job->command.batch_token=folder.token;
  job->command.batch_control=&folder.control;job->command.batch_request=g_atomic_int_get(&folder.control.request);
  job->command.batch_root=g_strdup(root);job->command.batch_recursive=recursive;
  folder.running=1;g_async_queue_push(queue,job);state();
}
static void folder_message(void) {
  if(!folder.dialog) return;
  char *message=g_strdup_printf("%"G_GUINT64_FORMAT" checked · %"G_GUINT64_FORMAT" added · %"G_GUINT64_FORMAT" exact duplicates · %"G_GUINT64_FORMAT" failed\n%s%s",
    folder.attempted,folder.imported,folder.duplicates,folder.failed,
    folder.pending ? "Books saved; bookshelf update pending. Reopen the library to retry.":
    folder.done ? (folder.cancelled ? "Cancelled; committed books kept.":folder.truncated ? "Scan stopped at a limit or unreadable folder; some files omitted.":folder.complete ? "Scan completed.":"Import stopped; scan did not complete."):
    g_atomic_int_get(&folder.control.cancelled) ? "Cancelling; committed books are kept…":"Importing; total unknown until scan ends…",
    "\nOnly the latest 32 results are shown. Links and unsupported files are omitted.");
  gtk_label_set_text(GTK_LABEL(folder.message),message);g_free(message);
  gtk_widget_set_sensitive(folder.cancel,!folder.done && !g_atomic_int_get(&folder.control.cancelled));
  gtk_button_set_label(GTK_BUTTON(folder.close),folder.done ? "Close":"Stop and close");
}
static int folder_paused(void) {
  if(busy || saving || save_failed || choosing_file || shelf_loading) return 1;
#ifdef EXR_READER_READING_RECORDS_UI
  if(reading_records_opened()) return 1;
#endif
#ifdef EXR_READER_NAVIGATION_UI
  if(directory_opened()) return 1;
#endif
#ifdef EXR_READER_SEARCH_UI
  if(inbook_opened()) return 1;
#endif
#ifdef EXR_READER_PREFERENCES_UI
  if(preferences_opened() || preferences_busy()) return 1;
#endif
#ifdef EXR_READER_DESKTOP_METADATA
  if(metadata_running || collections_opened()) return 1;
#endif
#ifdef EXR_READER_ACCOUNT
  if(accounts_opened()) return 1;
#endif
  return 0;
}
static gboolean folder_tick(gpointer unused) {
  (void)unused;
  if(closing || !folder.has_owner) { folder.timer=0;return G_SOURCE_REMOVE; }
  if(folder.progress) {
    int current=g_atomic_int_get(&folder.control.current_bytes),total=g_atomic_int_get(&folder.control.total_bytes);
    if(total>0) gtk_progress_bar_set_fraction(GTK_PROGRESS_BAR(folder.progress),MIN(1.,(double)current/total));
    else if(!folder.done) gtk_progress_bar_pulse(GTK_PROGRESS_BAR(folder.progress));
  }
  if(!folder.running && !folder_paused()) {
    if(folder.want_close && !folder.release_queued) { folder.release_queued=1;folder_queue(READER_BATCH_CLOSE,NULL,0); }
    else if(!folder.done && !folder.release_queued) folder_queue(folder.map ? READER_BATCH_MAP:READER_BATCH_NEXT,NULL,0);
  }
  if(folder.done && !folder.running && !folder.want_close) { folder.timer=0;return G_SOURCE_REMOVE; }
  state();
  return G_SOURCE_CONTINUE;
}
static void folder_cancel(GtkWidget *widget,gpointer unused) {
  (void)widget;(void)unused;g_atomic_int_set(&folder.control.cancelled,1);folder_message();state();
}
static void folder_close(GtkWidget *widget,gpointer unused) {
  folder_cancel(widget,unused);folder.want_close=1;
  if(!folder.has_owner && folder.dialog) {
    gtk_widget_destroy(folder.dialog);folder.dialog=folder.list=folder.message=folder.progress=folder.cancel=folder.close=NULL;state();
  }
  if(folder.has_owner && !folder.timer) folder.timer=g_timeout_add(80,folder_tick,NULL);
}
static gboolean folder_key(GtkWidget *widget,GdkEventKey *event,gpointer unused) {
  if(event->keyval==GDK_KEY_Escape) { folder_close(widget,unused);return TRUE; }
  return FALSE;
}
static gboolean folder_delete(GtkWidget *widget,GdkEvent *event,gpointer unused) {
  (void)event;folder_close(widget,unused);return TRUE;
}
static gboolean folder_apply(host_result *done) {
  reader_result *result=&done->value;
  if(result->batch_token!=folder.token || !folder.has_owner) return TRUE;
  folder.running=0;folder.actions++;
  folder.seen=result->batch_seen;folder.attempted=result->batch_attempted;folder.imported=result->batch_imported;
  folder.duplicates=result->batch_duplicates;folder.failed=result->batch_failed;folder.pending=result->batch_pending;
  folder.done=result->batch_done;folder.complete=result->batch_complete;folder.truncated=result->batch_truncated;
  folder.cancelled=result->batch_cancelled;folder.map=result->batch_map;
  if(result->receive_restore_failed) status(EXR_IO,"Import saved; reopen your original book from its saved position");
  if(folder.list) {
    rows_clear(folder.list);folder.rows=result->batch_count;folder.max_rows=MAX(folder.max_rows,folder.rows);
    for(size_t i=0;i<result->batch_count;i++) {
      const reader_batch_receipt *row=&result->batch_rows[i];
      const char *outcome=row->committed ? (row->created ? "Added":"Exact duplicate"):
        row->status==READER_BATCH_ITEM_CANCELLED ? "Cancelled":"Failed";
      char *title=g_strdup_printf("%s · %s%s%s%s",row->path,outcome,row->committed ? row->mapped ? "":" · Bookshelf update pending":"",
        row->message[0] ? " · ":"",row->message);
      GtkWidget *label_row=gtk_label_new(title);gtk_label_set_xalign(GTK_LABEL(label_row),0);
      gtk_label_set_line_wrap(GTK_LABEL(label_row),TRUE);gtk_list_box_insert(GTK_LIST_BOX(folder.list),label_row,-1);g_free(title);
    }
    gtk_widget_show_all(folder.list);
  }
  if(result->status!=EXR_OK && result->status!=EXR_CANCELLED && !folder.map) {
    folder.done=1;folder_message();
    if(folder.message) gtk_label_set_text(GTK_LABEL(folder.message),result->message[0] ? result->message:"Import stopped; committed books retained");
  } else folder_message();
  if(done->action==READER_BATCH_MAP && !closing && !folder_paused()) shelf_request(0,TRUE);
  if(done->action==READER_BATCH_CLOSE || (done->action==READER_BATCH_BEGIN && result->status!=EXR_OK)) {
    folder.has_owner=0;
    if(folder.timer) { g_source_remove(folder.timer);folder.timer=0; }
    if(done->action==READER_BATCH_CLOSE && folder.dialog) {
      gtk_widget_destroy(folder.dialog);folder.dialog=folder.list=folder.message=folder.progress=folder.cancel=folder.close=NULL;
    }
  }
  state();return TRUE;
}
static void folder_exit(void) {
  g_atomic_int_set(&folder.control.cancelled,1);
  if(folder.timer) { g_source_remove(folder.timer);folder.timer=0; }
  if(folder.has_owner && !folder.release_queued) { folder.release_queued=1;folder_queue(READER_BATCH_CLOSE,NULL,0); }
}
static void folder_chooser_changed(GtkFileChooser *chooser,gpointer unused) { (void)chooser;(void)unused;state(); }
static void folder_open(GtkWidget *widget,gpointer unused) {
  (void)widget;(void)unused;
  if(folder.dialog) { gtk_window_present(GTK_WINDOW(folder.dialog));return; }
  if(!profile_writable) { status(EXR_IO,"Library unavailable; reopen before importing a folder");return; }
  if(closing || folder_paused()) { status(EXR_OK,"Finish the current reading operation first");return; }
  GtkWidget *chooser=gtk_file_chooser_dialog_new("Import folder",GTK_WINDOW(window),GTK_FILE_CHOOSER_ACTION_SELECT_FOLDER,
    "Cancel",GTK_RESPONSE_CANCEL,"Choose folder",GTK_RESPONSE_ACCEPT,NULL);
  GtkWidget *recursive=gtk_check_button_new_with_label("Include subfolders");
  gtk_toggle_button_set_active(GTK_TOGGLE_BUTTON(recursive),FALSE);
  gtk_file_chooser_set_extra_widget(GTK_FILE_CHOOSER(chooser),recursive);gtk_widget_show(recursive);
#ifdef EXR_READER_PREFERENCES_UI
  preferences_import_dialog=chooser;
  g_signal_connect(chooser,"selection-changed",G_CALLBACK(preferences_import_changed),NULL);
  g_signal_connect(chooser,"current-folder-changed",G_CALLBACK(preferences_import_changed),NULL);
  g_signal_connect(chooser,"map-event",G_CALLBACK(preferences_import_mapped),NULL);
  g_signal_connect_after(chooser,"set-focus",G_CALLBACK(preferences_import_focus),NULL);
  g_signal_connect(chooser,"notify::is-active",G_CALLBACK(preferences_import_activity),NULL);
#endif
  g_signal_connect(chooser,"selection-changed",G_CALLBACK(folder_chooser_changed),NULL);
  g_signal_connect(chooser,"current-folder-changed",G_CALLBACK(folder_chooser_changed),NULL);
  folder.chooser=chooser;choosing_file=TRUE;state();int response=gtk_dialog_run(GTK_DIALOG(chooser));choosing_file=FALSE;
#ifdef EXR_READER_PREFERENCES_UI
  preferences_import_dialog=NULL;preferences_import_schedule();
#endif
  char *root=response==GTK_RESPONSE_ACCEPT ? gtk_file_chooser_get_filename(GTK_FILE_CHOOSER(chooser)):NULL;
  int include=gtk_toggle_button_get_active(GTK_TOGGLE_BUTTON(recursive));folder.chooser=NULL;gtk_widget_destroy(chooser);
  if(!root) { state();return; }
  folder.token++;g_atomic_int_inc(&folder.control.request);g_atomic_int_set(&folder.control.cancelled,0);
  g_atomic_int_set(&folder.control.current_bytes,0);g_atomic_int_set(&folder.control.total_bytes,0);
  folder.seen=folder.attempted=folder.imported=folder.duplicates=folder.failed=folder.pending=0;
  folder.rows=folder.max_rows=0;folder.done=folder.complete=folder.truncated=folder.cancelled=folder.map=folder.want_close=folder.release_queued=0;
  folder.has_owner=1;
  folder.dialog=gtk_dialog_new_with_buttons("Folder import",GTK_WINDOW(window),GTK_DIALOG_DESTROY_WITH_PARENT,NULL,NULL);
  gtk_window_set_default_size(GTK_WINDOW(folder.dialog),620,420);
  GtkWidget *content=gtk_dialog_get_content_area(GTK_DIALOG(folder.dialog));
  folder.message=gtk_label_new(NULL);gtk_label_set_line_wrap(GTK_LABEL(folder.message),TRUE);gtk_label_set_xalign(GTK_LABEL(folder.message),0);
  folder.progress=gtk_progress_bar_new();folder.list=gtk_list_box_new();
  atk_object_set_name(gtk_widget_get_accessible(folder.list),"Latest folder import results");
  GtkWidget *scroll=gtk_scrolled_window_new(NULL,NULL);gtk_container_add(GTK_CONTAINER(scroll),folder.list);
  gtk_box_pack_start(GTK_BOX(content),folder.message,FALSE,FALSE,5);gtk_box_pack_start(GTK_BOX(content),folder.progress,FALSE,FALSE,5);
  gtk_box_pack_start(GTK_BOX(content),scroll,TRUE,TRUE,5);
  folder.cancel=gtk_dialog_add_button(GTK_DIALOG(folder.dialog),"Cancel import",1);
  folder.close=gtk_dialog_add_button(GTK_DIALOG(folder.dialog),"Stop and close",2);
  g_signal_connect(folder.cancel,"clicked",G_CALLBACK(folder_cancel),NULL);g_signal_connect(folder.close,"clicked",G_CALLBACK(folder_close),NULL);
  g_signal_connect(folder.dialog,"delete-event",G_CALLBACK(folder_delete),NULL);
  g_signal_connect(folder.dialog,"key-press-event",G_CALLBACK(folder_key),NULL);
  folder_message();gtk_widget_show_all(folder.dialog);folder_queue(READER_BATCH_BEGIN,root,include);g_free(root);
  folder.timer=g_timeout_add(80,folder_tick,NULL);
}
static char *folder_observation(void) {
  return g_strdup_printf("[folder_import]\nvisible=%d\nchooser=%d\nrunning=%d\nowner=%d\ntoken=%"G_GUINT64_FORMAT"\nactions=%u\ndone=%d\ncomplete=%d\ntruncated=%d\ncancelled=%d\ncancel_requested=%d\nseen=%"G_GUINT64_FORMAT"\nattempted=%"G_GUINT64_FORMAT"\nimported=%"G_GUINT64_FORMAT"\nduplicates=%"G_GUINT64_FORMAT"\nfailed=%"G_GUINT64_FORMAT"\npending=%"G_GUINT64_FORMAT"\nrows=%zu\nmax_rows=%zu\nphase=%d\ncurrent_bytes=%d\ntotal_bytes=%d\n",
    folder.dialog!=NULL,folder.chooser!=NULL,folder.running,folder.has_owner,folder.token,folder.actions,folder.done,folder.complete,folder.truncated,folder.cancelled,
    g_atomic_int_get(&folder.control.cancelled),folder.seen,folder.attempted,folder.imported,folder.duplicates,folder.failed,folder.pending,folder.rows,folder.max_rows,
    g_atomic_int_get(&folder.control.phase),g_atomic_int_get(&folder.control.current_bytes),g_atomic_int_get(&folder.control.total_bytes));
}
