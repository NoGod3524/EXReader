#include <reader_commands.h>
static void metadata_submit(reader_action);
static GtkWidget *metadata_removed_dialog,*metadata_removed_list;
static char *metadata_removed_cursor;
static int metadata_operation;
static void metadata_removed_request(void) {
  if(closing || metadata_running || busy || saving || save_failed) return;
  host_job *job=g_new0(host_job,1);job->generation=g_atomic_int_get(&generation);
  job->shelf_generation=g_atomic_int_get(&shelf_generation);
  job->command.action=READER_METADATA_REMOVED_LIST;
  job->command.cursor_key=g_strdup(metadata_removed_cursor);
  busy=metadata_running=TRUE;g_async_queue_push(queue,job);
}
static void metadata_removed_destroy(GtkWidget *widget,gpointer unused) {
  (void)widget;(void)unused;metadata_removed_dialog=metadata_removed_list=NULL;
  g_clear_pointer(&metadata_removed_cursor,g_free);
}
static gboolean metadata_removed_delete(GtkWidget *widget,GdkEvent *event,gpointer unused) {
  (void)widget;(void)event;(void)unused;return metadata_running;
}
static void metadata_removed_response(GtkDialog *dialog,int response,gpointer unused) {
  (void)unused;
  if(metadata_running) return;
  if(response==1) metadata_removed_request();
  else if(response==2) { g_clear_pointer(&metadata_removed_cursor,g_free);metadata_removed_request(); }
  else gtk_widget_destroy(GTK_WIDGET(dialog));
}
static void metadata_removed_activate(GtkListBox *list,GtkListBoxRow *row,gpointer unused) {
  (void)list;(void)unused;
  if(busy || metadata_running || !row) return;
  const char *key=g_object_get_data(G_OBJECT(row),"book-key");
  int64_t *id=g_object_get_data(G_OBJECT(row),"book-id");
  if(!key) return;
  g_free(metadata_key);metadata_key=g_strdup(key);metadata_book=id ? *id:0;metadata_token=0;
  gtk_widget_destroy(metadata_removed_dialog);
  metadata_submit(READER_METADATA_PREPARE);
}
static void metadata_removed_present(const reader_result *result) {
  if(!metadata_removed_dialog) {
    metadata_removed_dialog=gtk_dialog_new_with_buttons("Removed books",GTK_WINDOW(window),
      GTK_DIALOG_MODAL|GTK_DIALOG_DESTROY_WITH_PARENT,"_Close",GTK_RESPONSE_CANCEL,
      "_First page",2,"_Next page",1,NULL);
    gtk_window_set_default_size(GTK_WINDOW(metadata_removed_dialog),600,400);
    GtkWidget *scroll=gtk_scrolled_window_new(NULL,NULL);
    gtk_widget_set_vexpand(scroll,TRUE);
    metadata_removed_list=gtk_list_box_new();
    gtk_container_add(GTK_CONTAINER(scroll),metadata_removed_list);
    gtk_box_pack_start(GTK_BOX(gtk_dialog_get_content_area(GTK_DIALOG(metadata_removed_dialog))),scroll,TRUE,TRUE,8);
    g_signal_connect(metadata_removed_dialog,"destroy",G_CALLBACK(metadata_removed_destroy),NULL);
    g_signal_connect(metadata_removed_dialog,"delete-event",G_CALLBACK(metadata_removed_delete),NULL);
    g_signal_connect(metadata_removed_dialog,"response",G_CALLBACK(metadata_removed_response),NULL);
    g_signal_connect(metadata_removed_list,"row-activated",G_CALLBACK(metadata_removed_activate),NULL);
  }
  GList *children=gtk_container_get_children(GTK_CONTAINER(metadata_removed_list));
  for(GList *item=children;item;item=item->next) gtk_widget_destroy(GTK_WIDGET(item->data));
  g_list_free(children);
  for(size_t i=0;i<result->book_count;i++) {
    GtkWidget *row=gtk_list_box_row_new();
    char *caption=g_strdup_printf("%s\n%s",result->books[i].title,result->cursors[i].key);
    GtkWidget *label=gtk_label_new(caption);gtk_label_set_xalign(GTK_LABEL(label),0);
    atk_object_set_name(gtk_widget_get_accessible(row),caption);g_free(caption);
    gtk_container_add(GTK_CONTAINER(row),label);
    g_object_set_data_full(G_OBJECT(row),"book-key",g_strdup(result->cursors[i].key),g_free);
    int64_t *id=g_new(int64_t,1);*id=result->books[i].id;
    g_object_set_data_full(G_OBJECT(row),"book-id",id,g_free);
    gtk_container_add(GTK_CONTAINER(metadata_removed_list),row);
  }
  if(result->book_count) {
    g_free(metadata_removed_cursor);metadata_removed_cursor=g_strdup(result->cursors[result->book_count-1].key);
  }
  gtk_dialog_set_response_sensitive(GTK_DIALOG(metadata_removed_dialog),1,result->book_count==50);
  gtk_widget_show_all(metadata_removed_dialog);gtk_widget_grab_focus(metadata_removed_list);
}
static void metadata_removed_open(GtkWidget *unused,gpointer context) {
  (void)unused;(void)context;
  if(closing || busy || saving || save_failed || metadata_running || metadata_dialog || metadata_removed_dialog) return;
  g_clear_pointer(&metadata_removed_cursor,g_free);metadata_removed_request();
}

/* SPDX-License-Identifier: MIT */
/* Native GTK widgets; all catalog/revision work is dispatched to the owner. */
static void metadata_dialog_close(void) {
  if(metadata_dialog) gtk_widget_destroy(metadata_dialog);
  metadata_dialog=metadata_title=metadata_author=metadata_favorite=metadata_message=NULL;
}
static void metadata_dialog_destroyed(GtkWidget *widget,gpointer unused) {
  (void)unused;
  if(widget==metadata_dialog) metadata_dialog=metadata_title=metadata_author=metadata_favorite=metadata_message=NULL;
}
static gboolean metadata_dialog_delete(GtkWidget *widget,GdkEvent *event,gpointer unused) {
  (void)widget;(void)event;(void)unused;
  if(!metadata_running) metadata_dialog_close();
  return TRUE;
}
static void metadata_dialog_lifecycle(void) {
  g_signal_connect(metadata_dialog,"delete-event",G_CALLBACK(metadata_dialog_delete),NULL);
  g_signal_connect(metadata_dialog,"destroy",G_CALLBACK(metadata_dialog_destroyed),NULL);
}
static void metadata_submit(reader_action action) {
  if(closing || metadata_running || busy || saving || save_failed) return;
  host_job *job=g_new0(host_job,1);job->generation=g_atomic_int_get(&generation);
  job->shelf_generation=g_atomic_int_add(&shelf_generation,1)+1;
  job->command.action=action;job->command.book=metadata_book;job->command.metadata_token=metadata_token;
  job->command.metadata_key=g_strdup(metadata_key);
  job->command.query=g_strdup(shelf_query ? shelf_query:"");
  shelf_remember();job->command.anchor_key=g_strdup(shelf_top_key);
  if(action==READER_METADATA_SAVE) {
    job->command.metadata_title=g_strdup(gtk_entry_get_text(GTK_ENTRY(metadata_title)));
    job->command.metadata_author=g_strdup(gtk_entry_get_text(GTK_ENTRY(metadata_author)));
    job->command.metadata_operation=metadata_operation;
    job->command.metadata_favorite=gtk_toggle_button_get_active(GTK_TOGGLE_BUTTON(metadata_favorite));
  }
  busy=metadata_running=TRUE;shelf_loading=FALSE;
  if(metadata_dialog) gtk_widget_set_sensitive(metadata_dialog,FALSE);
  status(EXR_OK,"Saving book details on the library worker");g_async_queue_push(queue,job);
}
static void metadata_response(GtkDialog *dialog,int response,gpointer recovery) {
  (void)dialog;
  if(metadata_running) return;
  if(response==GTK_RESPONSE_ACCEPT) { metadata_operation=READER_COMMAND_PUT;metadata_submit(recovery ? READER_METADATA_RETRY:READER_METADATA_SAVE); }
  else if(!recovery && (response==3 || response==4)) {
    GtkWidget *confirm=gtk_message_dialog_new(GTK_WINDOW(metadata_dialog),GTK_DIALOG_MODAL,GTK_MESSAGE_QUESTION,GTK_BUTTONS_OK_CANCEL,
      "%s",response==3 ? "Restore this removed book? Its retained original will be verified before saving.":"Remove this book from the shelf? Original bytes and revision history will be retained.");
    gtk_window_set_title(GTK_WINDOW(confirm),"Confirm book operation");
    int answer=gtk_dialog_run(GTK_DIALOG(confirm));gtk_widget_destroy(confirm);
    if(answer==GTK_RESPONSE_OK) { metadata_operation=response==3 ? READER_COMMAND_RESTORE:READER_COMMAND_DELETE;metadata_submit(READER_METADATA_SAVE); }
  }
  else if(recovery && response==2) metadata_submit(READER_METADATA_DISCARD);
  else metadata_dialog_close();
}
static void metadata_recovery(const char *message) {
  metadata_dialog_close();
  metadata_dialog=gtk_dialog_new_with_buttons("Recover book edit",GTK_WINDOW(window),
    GTK_DIALOG_MODAL|GTK_DIALOG_DESTROY_WITH_PARENT,"Close",GTK_RESPONSE_CANCEL,
    "_Discard uncommitted",2,"_Retry",GTK_RESPONSE_ACCEPT,NULL);
  metadata_dialog_lifecycle();
  gtk_dialog_set_default_response(GTK_DIALOG(metadata_dialog),GTK_RESPONSE_ACCEPT);
  metadata_message=gtk_label_new(message);gtk_label_set_line_wrap(GTK_LABEL(metadata_message),TRUE);
  gtk_container_set_border_width(GTK_CONTAINER(gtk_dialog_get_content_area(GTK_DIALOG(metadata_dialog))),16);
  gtk_box_pack_start(GTK_BOX(gtk_dialog_get_content_area(GTK_DIALOG(metadata_dialog))),metadata_message,FALSE,FALSE,6);
  g_signal_connect(metadata_dialog,"response",G_CALLBACK(metadata_response),GINT_TO_POINTER(1));
  gtk_widget_show_all(metadata_dialog);
}
static void metadata_present(const reader_result *result) {
  metadata_dialog_close();metadata_token=result->metadata_token;
  metadata_dialog=gtk_dialog_new_with_buttons("Book details",GTK_WINDOW(window),
    GTK_DIALOG_MODAL|GTK_DIALOG_DESTROY_WITH_PARENT,"Cancel",GTK_RESPONSE_CANCEL,"Save",GTK_RESPONSE_ACCEPT,NULL);
  metadata_dialog_lifecycle();
  gtk_dialog_add_button(GTK_DIALOG(metadata_dialog),result->metadata_deleted ? "_Restore book":"_Delete book",result->metadata_deleted ? 3:4);
  gtk_dialog_set_response_sensitive(GTK_DIALOG(metadata_dialog),result->metadata_deleted ? 3:4,!result->metadata_conflict);
  gtk_dialog_set_default_response(GTK_DIALOG(metadata_dialog),GTK_RESPONSE_ACCEPT);
  GtkWidget *grid=gtk_grid_new();gtk_grid_set_row_spacing(GTK_GRID(grid),8);
  gtk_grid_set_column_spacing(GTK_GRID(grid),12);gtk_container_set_border_width(GTK_CONTAINER(grid),16);
  gtk_container_add(GTK_CONTAINER(gtk_dialog_get_content_area(GTK_DIALOG(metadata_dialog))),grid);
  metadata_title=gtk_entry_new();metadata_author=gtk_entry_new();metadata_favorite=gtk_check_button_new_with_mnemonic("_Favorite");
  gtk_entry_set_max_length(GTK_ENTRY(metadata_title),4096);gtk_entry_set_max_length(GTK_ENTRY(metadata_author),4096);
  gtk_entry_set_width_chars(GTK_ENTRY(metadata_title),42);
  gtk_entry_set_activates_default(GTK_ENTRY(metadata_title),TRUE);
  gtk_entry_set_activates_default(GTK_ENTRY(metadata_author),TRUE);
  gtk_entry_set_text(GTK_ENTRY(metadata_title),result->metadata_title);
  gtk_entry_set_text(GTK_ENTRY(metadata_author),result->metadata_author);
  gtk_toggle_button_set_active(GTK_TOGGLE_BUTTON(metadata_favorite),result->metadata_favorite);
  GtkWidget *title=gtk_label_new_with_mnemonic("_Title"),*author=gtk_label_new_with_mnemonic("_Author");
  gtk_label_set_mnemonic_widget(GTK_LABEL(title),metadata_title);gtk_label_set_mnemonic_widget(GTK_LABEL(author),metadata_author);
  atk_object_set_name(gtk_widget_get_accessible(metadata_title),"Book title");
  atk_object_set_name(gtk_widget_get_accessible(metadata_author),"Book author");
  atk_object_set_name(gtk_widget_get_accessible(metadata_favorite),"Favorite book");
  gtk_grid_attach(GTK_GRID(grid),title,0,0,1,1);gtk_grid_attach(GTK_GRID(grid),metadata_title,1,0,1,1);
  gtk_grid_attach(GTK_GRID(grid),author,0,1,1,1);gtk_grid_attach(GTK_GRID(grid),metadata_author,1,1,1,1);
  gtk_grid_attach(GTK_GRID(grid),metadata_favorite,1,2,1,1);
  metadata_message=gtk_label_new(result->metadata_conflict ? result->message:"");
  gtk_label_set_line_wrap(GTK_LABEL(metadata_message),TRUE);gtk_grid_attach(GTK_GRID(grid),metadata_message,0,3,2,1);
  if(result->metadata_conflict || result->metadata_deleted) {
    gtk_widget_set_sensitive(metadata_title,FALSE);gtk_widget_set_sensitive(metadata_author,FALSE);
    gtk_widget_set_sensitive(metadata_favorite,FALSE);
    gtk_dialog_set_response_sensitive(GTK_DIALOG(metadata_dialog),GTK_RESPONSE_ACCEPT,FALSE);
  }
  g_signal_connect(metadata_dialog,"response",G_CALLBACK(metadata_response),NULL);
  gtk_widget_show_all(metadata_dialog);gtk_widget_grab_focus(metadata_title);
}
static void metadata_edit(GtkWidget *unused,gpointer context) {
  (void)unused;(void)context;
  if(closing || busy || saving || save_failed || metadata_running || metadata_dialog) return;
  if(strcmp(gtk_stack_get_visible_child_name(GTK_STACK(stack)),"shelf")) {
    status(EXR_ARGUMENT,"Open the shelf and select a book first");return;
  }
  GtkListBoxRow *row=gtk_list_box_get_selected_row(GTK_LIST_BOX(shelf));
  const char *key=row ? g_object_get_data(G_OBJECT(row),"book-key"):NULL;
  int64_t *id=row ? g_object_get_data(G_OBJECT(row),"book-id"):NULL;
  if(!key) { status(EXR_ARGUMENT,"Select a book first");return; }
  g_free(metadata_key);metadata_key=g_strdup(key);metadata_book=id ? *id:0;metadata_token=0;
  metadata_submit(READER_METADATA_PREPARE);
}
static void metadata_apply(host_result *done) {
  reader_result *result=&done->value;busy=metadata_running=FALSE;
  if(closing) return;
  if(metadata_dialog) gtk_widget_set_sensitive(metadata_dialog,TRUE);
  if(result->has_shelf) { shelf_filter_pending=FALSE;shelf_present(result); }
  if(result->has_removed_books) metadata_removed_present(result);
  if(result->has_metadata) metadata_present(result);
  else if(result->status==EXR_OK || result->metadata_committed) metadata_dialog_close();
  if(result->metadata_pending) metadata_recovery(result->message);
  else if(result->status!=EXR_OK && metadata_message) gtk_label_set_text(GTK_LABEL(metadata_message),result->message);
  status(result->status,result->message);
  if(close_after_save) { close_after_save=FALSE;metadata_dialog_close();stop_worker(); }
}
