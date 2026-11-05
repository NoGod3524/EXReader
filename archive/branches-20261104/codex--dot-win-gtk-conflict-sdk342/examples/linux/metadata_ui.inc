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
    job->command.metadata_favorite=gtk_toggle_button_get_active(GTK_TOGGLE_BUTTON(metadata_favorite));
    job->command.metadata_resolution=GPOINTER_TO_INT(g_object_get_data(G_OBJECT(metadata_dialog),"explicit-resolution"));
  }
  busy=metadata_running=TRUE;shelf_loading=FALSE;
  if(metadata_dialog) gtk_widget_set_sensitive(metadata_dialog,FALSE);
  status(EXR_OK,"Saving book details on the library worker");g_async_queue_push(queue,job);
}
static void metadata_response(GtkDialog *dialog,int response,gpointer recovery) {
  (void)dialog;
  if(metadata_running) return;
  if(response==3 && !recovery) {
    GtkWidget *confirm=gtk_message_dialog_new(GTK_WINDOW(dialog),GTK_DIALOG_MODAL,GTK_MESSAGE_QUESTION,GTK_BUTTONS_YES_NO,
      "%s","Merge every observed version using the details you enter next? Old revisions and original bytes will be retained. Save is still required.");
    int answer=gtk_dialog_run(GTK_DIALOG(confirm));gtk_widget_destroy(confirm);
    if(answer==GTK_RESPONSE_YES) {
      g_object_set_data(G_OBJECT(dialog),"explicit-resolution",GINT_TO_POINTER(1));
      gtk_widget_set_sensitive(metadata_title,TRUE);gtk_widget_set_sensitive(metadata_author,TRUE);gtk_widget_set_sensitive(metadata_favorite,TRUE);
      gtk_dialog_set_response_sensitive(dialog,GTK_RESPONSE_ACCEPT,TRUE);gtk_dialog_set_response_sensitive(dialog,3,FALSE);
      gtk_label_set_text(GTK_LABEL(metadata_message),"Enter merged details and Save. A changed head set will be rejected; old revisions remain retained.");
    }
  } else if(response==GTK_RESPONSE_ACCEPT) metadata_submit(recovery ? READER_METADATA_RETRY:READER_METADATA_SAVE);
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
  if(result->metadata_conflict) {
    gtk_widget_set_sensitive(metadata_title,FALSE);gtk_widget_set_sensitive(metadata_author,FALSE);
    gtk_widget_set_sensitive(metadata_favorite,FALSE);
    gtk_dialog_set_response_sensitive(GTK_DIALOG(metadata_dialog),GTK_RESPONSE_ACCEPT,FALSE);
    gtk_dialog_add_button(GTK_DIALOG(metadata_dialog),"_Resolve versions",3);
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
  if(result->has_metadata) metadata_present(result);
  else if(result->status==EXR_OK || result->metadata_committed) metadata_dialog_close();
  if(result->metadata_pending) metadata_recovery(result->message);
  else if(result->status!=EXR_OK && metadata_message) gtk_label_set_text(GTK_LABEL(metadata_message),result->message);
  status(result->status,result->message);
  if(close_after_save) { close_after_save=FALSE;metadata_dialog_close();stop_worker(); }
}
