/* SPDX-License-Identifier: MIT */
/* Native low-frequency controls; SDK and product handles stay on their owner. */
static struct {
  GtkWidget *dialog,*content,*list,*status,*progress,*save,*bookmark,*highlight,*more,*previous,*refresh;
  GtkWidget *jump,*edit,*remove,*restore,*retry,*discard,*cancel,*choice,*return_focus;
  reader_av_page page;
  gboolean running,pending,pending_error,progress_selected,has_range,suppress_focus;
  uint64_t token;size_t selected,start,end;
  int progress_state,progress_deleted,code,match;
  char progress_head[33],progress_sha[65],pending_revision[33],selected_id[33],selected_head[33],selected_sha[65];
  unsigned actions,closed;
} records;
static gboolean reading_records_opened(void) { return records.dialog!=NULL; }
static const char *records_state_name(int state,int progress) {
  if(progress) {
    switch(state) {
      case READER_SELECTION_SAFE:return "Saved";
      case READER_SELECTION_CONCURRENT:return "Versions need review";
      case READER_SELECTION_PENDING_PARENTS:return "Waiting for earlier versions";
      case READER_SELECTION_BLOCKED_RESTORE:return "Restore needs review";
      default:return "Not saved";
    }
  }
  switch(state) {
    case READER_AV_STATE_SAFE:return "Saved";
    case READER_AV_STATE_CONCURRENT:return "Versions need review";
    case READER_AV_STATE_PENDING_PARENTS:return "Waiting for earlier versions";
    case READER_AV_STATE_BLOCKED_RESTORE:return "Restore needs review";
    default:return "Not available";
  }
}
static void records_message(const char *message) {
  if(records.status) { gtk_label_set_text(GTK_LABEL(records.status),message);atk_object_set_name(gtk_widget_get_accessible(records.status),message); }
}
static reader_av_item *records_selected_item(void) { return !records.progress_selected && records.selected<records.page.count ? &records.page.items[records.selected]:NULL; }
static void records_controls(void) {
  if(!records.dialog) return;
  reader_av_item *item=records_selected_item();
  gboolean safe=records.progress_selected ? records.progress_state==READER_SELECTION_SAFE:item && item->state==READER_AV_STATE_SAFE;
  gboolean deleted=records.progress_selected ? records.progress_deleted:item && item->deleted;
#ifdef EXR_READER_GTK_RAW3
  gboolean location_safe=safe;
  if(item && item->mode==READER_AV_MODE_FIXED && item->anchor_version==3 && !item->exact) location_safe=FALSE;
#endif
  gboolean write=!records.running && !records.pending;
  gtk_widget_set_sensitive(records.save,write && !records.progress_deleted && (records.progress_state==READER_SELECTION_SAFE || records.progress_state==READER_SELECTION_MISSING));
  gtk_widget_set_sensitive(records.bookmark,write);gtk_widget_set_sensitive(records.highlight,write && records.has_range);
  gtk_widget_set_sensitive(records.more,!records.running && records.page.count>0 && !(records.page.next.direction>0 && records.page.complete));
  gtk_widget_set_sensitive(records.previous,!records.running && records.page.count>0 && !(records.page.next.direction<0 && records.page.complete));
  gtk_widget_set_sensitive(records.refresh,!records.running);gtk_widget_set_sensitive(records.list,!records.running);gtk_widget_set_sensitive(records.progress,!records.running);
#ifdef EXR_READER_GTK_RAW3
  gtk_widget_set_sensitive(records.jump,!records.running && location_safe && !deleted);gtk_widget_set_sensitive(records.edit,write && location_safe && !deleted && !records.progress_selected);
#else
  gtk_widget_set_sensitive(records.jump,!records.running && safe && !deleted);gtk_widget_set_sensitive(records.edit,write && safe && !deleted && !records.progress_selected);
#endif
  gtk_widget_set_sensitive(records.remove,write && safe && !deleted);gtk_widget_set_sensitive(records.restore,write && safe && deleted);
  gtk_widget_set_sensitive(records.retry,!records.running && records.pending && !records.pending_error);
  gtk_widget_set_sensitive(records.discard,!records.running && records.pending && !records.pending_error);
  gtk_widget_set_sensitive(records.cancel,records.running);
}
static void records_rows_clear(void) {
  if(records.list) { GList *rows=gtk_container_get_children(GTK_CONTAINER(records.list));for(GList *row=rows;row;row=row->next) gtk_widget_destroy(row->data);g_list_free(rows); }
  reader_av_page_free(&records.page);records.page.complete=1;records.selected=SIZE_MAX;records.progress_selected=FALSE;
}
static void records_destroyed(GtkWidget *widget,gpointer unused) {
  (void)widget;(void)unused;records.dialog=NULL;records.list=records.status=NULL;
  if(records.content) gtk_widget_set_sensitive(records.content,TRUE);
  records.content=NULL;
  if(!closing && !records.suppress_focus) {
    gtk_window_present(GTK_WINDOW(window));
    if(records.return_focus && gtk_widget_get_visible(records.return_focus) && gtk_widget_is_sensitive(records.return_focus)) gtk_widget_grab_focus(records.return_focus);
    else gtk_widget_grab_focus(text);
  }
  g_clear_object(&records.return_focus);state();
}
static void reading_records_close(void) {
  g_atomic_int_inc(&generation);records.token++;records.running=FALSE;busy=FALSE;records.closed++;
  if(records.choice) { gtk_widget_destroy(records.choice);records.choice=NULL; }
  records_rows_clear();if(records.dialog) gtk_widget_destroy(records.dialog);state();
}
static gboolean records_delete(GtkWidget *widget,GdkEvent *event,gpointer unused) { (void)widget;(void)event;(void)unused;reading_records_close();return TRUE; }
static void records_response(GtkDialog *dialog,int response,gpointer unused) { (void)dialog;(void)response;(void)unused;reading_records_close(); }
static gboolean records_background(GtkWidget *widget,GdkEventWindowState *event,gpointer unused) {
  (void)widget;(void)unused;
  if(records.dialog && (event->new_window_state&(GDK_WINDOW_STATE_ICONIFIED|GDK_WINDOW_STATE_WITHDRAWN))) { records.suppress_focus=TRUE;reading_records_close();records.suppress_focus=FALSE; }
  return FALSE;
}
static int records_target_kind(void) {
  if(records.progress_selected) return READER_RC_PROGRESS;
  reader_av_item *item=records_selected_item();return item && item->start==item->end ? READER_RC_BOOKMARK:READER_RC_HIGHLIGHT;
}
static void records_queue(reader_action action,int kind,int operation,const char *body,const char *version,int direction) {
  if(!records.dialog || records.running || busy || saving || save_failed || !book_id) return;
  host_job *job=g_new0(host_job,1);job->generation=g_atomic_int_add(&generation,1)+1;
  job->command.action=action;job->command.book=book_id;job->command.part=part;job->command.page=page_number;job->command.direction=direction;
  job->command.records_token=records.token;job->command.records_kind=kind;job->command.records_operation=operation;
  job->command.records_text=g_strdup(body ? body:"");job->command.records_version=g_strdup(version ? version:"");
  job->command.start=records.start;job->command.end=records.end;
  if(action==READER_RECORDS_LIST && direction) {
    const reader_av_cursor *cursor=records.page.next.direction==direction ? &records.page.next:&records.page.reverse;
    job->command.records_after=g_strdup(cursor->has_after ? cursor->after_id:"");
  }
  if(action==READER_RECORDS_DISCARD) job->command.records_head=g_strdup(records.pending_revision);
  else if(action==READER_RECORDS_JUMP || action==READER_RECORDS_HISTORY || (action==READER_RECORDS_SAVE &&
      (kind==READER_RC_PROGRESS || kind==READER_RC_NOTE_TEXT || operation!=READER_RC_PUT))) {
    job->command.records_progress=records.progress_selected || kind==READER_RC_PROGRESS;
    reader_av_item *item=job->command.records_progress ? NULL:records_selected_item();
    job->command.records_id=g_strdup(item ? item->annotation_id:"");
    job->command.records_head=g_strdup(item ? item->revision_id:records.progress_head);
    job->command.records_sha=g_strdup(item ? item->sha256:records.progress_sha);
    if(item) { g_strlcpy(records.selected_id,item->annotation_id,33);g_strlcpy(records.selected_head,item->revision_id,33);g_strlcpy(records.selected_sha,item->sha256,65); }
  }
  records.running=TRUE;records.actions++;busy=TRUE;records_controls();records_message(action==READER_RECORDS_LIST ? "Reading records…":action==READER_RECORDS_JUMP ? "Independently verifying this location…":"Saving or confirming the original request…");
  g_async_queue_push(queue,job);state();
}
static void records_refresh(GtkWidget *button,gpointer unused) { (void)button;(void)unused;records_queue(READER_RECORDS_LIST,0,0,NULL,NULL,0); }
static void records_more(GtkWidget *button,gpointer unused) { (void)button;(void)unused;records_queue(READER_RECORDS_LIST,0,0,NULL,NULL,1); }
static void records_previous(GtkWidget *button,gpointer unused) { (void)button;(void)unused;records_queue(READER_RECORDS_LIST,0,0,NULL,NULL,-1); }
static void records_save_progress(GtkWidget *button,gpointer unused) { (void)button;(void)unused;records_queue(READER_RECORDS_SAVE,READER_RC_PROGRESS,READER_RC_PUT,NULL,NULL,0); }
static void records_retry_button(GtkWidget *button,gpointer unused) { (void)button;(void)unused;records_queue(READER_RECORDS_RETRY,0,0,NULL,NULL,0); }
static void records_cancel(GtkWidget *button,gpointer unused) {
  (void)button;(void)unused;if(!records.running) return;
  g_atomic_int_inc(&generation);records.token++;records.running=FALSE;busy=FALSE;records_controls();
  records_message("Operation cancelled. A committed save is retained; refresh to check confirmation");state();
}
static gboolean records_confirm(const char *title,const char *message,const char *accept) {
  if(records.running || !records.dialog) return FALSE;
  uint64_t token=records.token;
  GtkWidget *dialog=gtk_message_dialog_new(GTK_WINDOW(records.dialog),GTK_DIALOG_MODAL|GTK_DIALOG_DESTROY_WITH_PARENT,GTK_MESSAGE_QUESTION,GTK_BUTTONS_NONE,"%s",title);
  g_object_ref_sink(dialog);records.choice=dialog;gtk_message_dialog_format_secondary_text(GTK_MESSAGE_DIALOG(dialog),"%s",message);
  gtk_dialog_add_buttons(GTK_DIALOG(dialog),"_Back",GTK_RESPONSE_CANCEL,accept,GTK_RESPONSE_ACCEPT,NULL);
  int response=gtk_dialog_run(GTK_DIALOG(dialog));gboolean current=records.dialog && records.token==token;
  if(records.choice==dialog) records.choice=NULL;
  gtk_widget_destroy(dialog);g_object_unref(dialog);return current && response==GTK_RESPONSE_ACCEPT;
}
static void records_discard(GtkWidget *button,gpointer unused) {
  (void)button;(void)unused;
  if(records_confirm("End the previous save confirmation?","Saved revisions remain. An uncommitted request will no longer be retried. Refresh before saving another record.","_End confirmation"))
    records_queue(READER_RECORDS_DISCARD,0,0,NULL,NULL,0);
}
static void records_remove(GtkWidget *button,gpointer unused) {
  (void)button;(void)unused;
  if(records_confirm("Delete this reading record?","Its retained versions remain available for explicit restoration.","_Delete"))
    records_queue(READER_RECORDS_SAVE,records_target_kind(),READER_RC_DELETE,NULL,NULL,0);
}
static void records_body_insert(GtkTextBuffer *buffer,GtkTextIter *where,gchar *inserted,gint length,gpointer unused) {
  (void)where;(void)unused;GtkTextIter start,end;gtk_text_buffer_get_bounds(buffer,&start,&end);
  char *current=gtk_text_buffer_get_text(buffer,&start,&end,FALSE);size_t size=strlen(current);g_free(current);
  if(length<0 || size>65536 || (size_t)length>65536-size || memchr(inserted,0,(size_t)length) || !g_utf8_validate(inserted,length,NULL))
    g_signal_stop_emission_by_name(buffer,"insert-text");
}
static void records_edit_text(GtkWidget *button,gpointer kind_value) {
  (void)button;int kind=GPOINTER_TO_INT(kind_value);reader_av_item *item=kind==READER_RC_NOTE_TEXT ? records_selected_item():NULL;
  if(records.running || records.pending || !records.dialog) return;
  uint64_t token=records.token;
  GtkWidget *dialog=gtk_dialog_new_with_buttons(kind==READER_RC_BOOKMARK ? "Add bookmark":kind==READER_RC_NOTE_TEXT ? "Edit record text":"Highlight selected text",
    GTK_WINDOW(records.dialog),GTK_DIALOG_MODAL|GTK_DIALOG_DESTROY_WITH_PARENT,"_Back",GTK_RESPONSE_CANCEL,"_Save",GTK_RESPONSE_ACCEPT,NULL);
  g_object_ref_sink(dialog);records.choice=dialog;GtkWidget *entry=gtk_text_view_new();gtk_widget_set_size_request(entry,420,140);
  gtk_text_view_set_wrap_mode(GTK_TEXT_VIEW(entry),GTK_WRAP_WORD_CHAR);atk_object_set_name(gtk_widget_get_accessible(entry),"Reading record text");
  gtk_text_buffer_set_text(gtk_text_view_get_buffer(GTK_TEXT_VIEW(entry)),item && item->note_text ? item->note_text:"",-1);
  g_signal_connect(gtk_text_view_get_buffer(GTK_TEXT_VIEW(entry)),"insert-text",G_CALLBACK(records_body_insert),NULL);
  gtk_box_pack_start(GTK_BOX(gtk_dialog_get_content_area(GTK_DIALOG(dialog))),entry,TRUE,TRUE,12);gtk_widget_show_all(dialog);
  int response=gtk_dialog_run(GTK_DIALOG(dialog));char *body=NULL;gboolean current=records.dialog && records.token==token && !gtk_widget_in_destruction(entry);
  if(current && response==GTK_RESPONSE_ACCEPT) { GtkTextIter start,end;GtkTextBuffer *buffer=gtk_text_view_get_buffer(GTK_TEXT_VIEW(entry));gtk_text_buffer_get_bounds(buffer,&start,&end);body=gtk_text_buffer_get_text(buffer,&start,&end,FALSE); }
  if(records.choice==dialog) records.choice=NULL;
  gtk_widget_destroy(dialog);g_object_unref(dialog);
  if(body) { if(strlen(body)<=65536 && g_utf8_validate(body,-1,NULL)) records_queue(READER_RECORDS_SAVE,kind,READER_RC_PUT,body,NULL,0);else records_message("Record text exceeds 65536 UTF-8 bytes");g_free(body); }
}
static void records_jump_button(GtkWidget *button,gpointer unused) { (void)button;(void)unused;records_queue(READER_RECORDS_JUMP,0,0,NULL,NULL,0); }
static void records_restore_button(GtkWidget *button,gpointer unused) { (void)button;(void)unused;records_queue(READER_RECORDS_HISTORY,0,0,NULL,NULL,0); }
static void records_selected(GtkListBox *list,GtkListBoxRow *row,gpointer unused) {
  (void)list;(void)unused;records.progress_selected=FALSE;records.selected=row ? GPOINTER_TO_SIZE(g_object_get_data(G_OBJECT(row),"record-index")):SIZE_MAX;records_controls();state();
}
static void records_select_progress(GtkWidget *button,gpointer unused) {
  (void)button;(void)unused;gtk_list_box_unselect_all(GTK_LIST_BOX(records.list));records.progress_selected=TRUE;records.selected=SIZE_MAX;records_controls();state();
}
static GtkWidget *records_button(GtkWidget *row,const char *title,GCallback callback,gpointer data) {
  GtkWidget *button=gtk_button_new_with_mnemonic(title);gtk_box_pack_start(GTK_BOX(row),button,FALSE,FALSE,0);g_signal_connect(button,"clicked",callback,data);return button;
}
static GtkWidget *records_button_row(GtkWidget *area) { GtkWidget *row=gtk_box_new(GTK_ORIENTATION_HORIZONTAL,6);gtk_box_pack_start(GTK_BOX(area),row,FALSE,FALSE,4);return row; }
static void reading_records_open(GtkWidget *button,gpointer unused) {
  (void)button;(void)unused;
  if(closing || busy || saving || save_failed || records.dialog || !book_id) return;
#ifdef EXR_READER_SEARCH_UI
  if(inbook_opened()) return;
#endif
#ifdef EXR_READER_NAVIGATION_UI
  if(directory_opened()) return;
#endif
#ifdef EXR_READER_PREFERENCES_UI
  if(preferences_opened()) return;
#endif
  if(accounts_opened() || metadata_dialog || metadata_running || collections_opened()) return;
  /* Snapshot the real visible selection before changing native focus or
     sensitivity; GTK can retire its selection when the main tree is disabled. */
  GtkTextIter start,end;records.has_range=page_text && gtk_text_buffer_get_selection_bounds(gtk_text_view_get_buffer(GTK_TEXT_VIEW(text)),&start,&end);
  records.start=records.end=0;
  if(records.has_range) { records.start=page_start+(size_t)(g_utf8_offset_to_pointer(page_text,gtk_text_iter_get_offset(&start))-page_text);records.end=page_start+(size_t)(g_utf8_offset_to_pointer(page_text,gtk_text_iter_get_offset(&end))-page_text); }
  GtkWidget *focus=gtk_window_get_focus(GTK_WINDOW(window));if(focus) records.return_focus=g_object_ref(focus);
  records.content=gtk_bin_get_child(GTK_BIN(window));gtk_widget_set_sensitive(records.content,FALSE);
  records.dialog=gtk_dialog_new_with_buttons("Reading records",GTK_WINDOW(window),GTK_DIALOG_MODAL|GTK_DIALOG_DESTROY_WITH_PARENT,"_Close",GTK_RESPONSE_CLOSE,NULL);
#ifdef EXR_READER_PREFERENCES_UI
  gtk_style_context_add_class(gtk_widget_get_style_context(records.dialog),"exreader-appearance");
#endif
  GtkWindowGroup *group=gtk_window_group_new();gtk_window_group_add_window(group,GTK_WINDOW(records.dialog));g_object_unref(group);
  GtkWidget *area=gtk_dialog_get_content_area(GTK_DIALOG(records.dialog));gtk_container_set_border_width(GTK_CONTAINER(area),12);
  records.status=gtk_label_new("");gtk_label_set_line_wrap(GTK_LABEL(records.status),TRUE);gtk_box_pack_start(GTK_BOX(area),records.status,FALSE,FALSE,4);
  GtkWidget *row=records_button_row(area);
  records.save=records_button(row,"_Save progress",G_CALLBACK(records_save_progress),NULL);
  records.bookmark=records_button(row,"_Add bookmark",G_CALLBACK(records_edit_text),GINT_TO_POINTER(READER_RC_BOOKMARK));
  records.highlight=records_button(row,"_Highlight selection",G_CALLBACK(records_edit_text),GINT_TO_POINTER(READER_RC_HIGHLIGHT));
  records.progress=gtk_button_new_with_label("Saved progress");atk_object_set_name(gtk_widget_get_accessible(records.progress),"Saved product progress");
  gtk_box_pack_start(GTK_BOX(area),records.progress,FALSE,FALSE,4);g_signal_connect(records.progress,"clicked",G_CALLBACK(records_select_progress),NULL);
  records.list=gtk_list_box_new();gtk_list_box_set_selection_mode(GTK_LIST_BOX(records.list),GTK_SELECTION_SINGLE);gtk_list_box_set_activate_on_single_click(GTK_LIST_BOX(records.list),FALSE);
  atk_object_set_name(gtk_widget_get_accessible(records.list),"Bookmarks and annotations");g_signal_connect(records.list,"row-selected",G_CALLBACK(records_selected),NULL);
  GtkWidget *view=gtk_scrolled_window_new(NULL,NULL);gtk_widget_set_size_request(view,560,240);gtk_container_add(GTK_CONTAINER(view),records.list);gtk_box_pack_start(GTK_BOX(area),view,TRUE,TRUE,4);
  row=records_button_row(area);records.jump=records_button(row,"_Open location",G_CALLBACK(records_jump_button),NULL);
  records.edit=records_button(row,"_Edit text",G_CALLBACK(records_edit_text),GINT_TO_POINTER(READER_RC_NOTE_TEXT));
  records.remove=records_button(row,"_Delete record",G_CALLBACK(records_remove),NULL);records.restore=records_button(row,"Choose restore _version",G_CALLBACK(records_restore_button),NULL);
  row=records_button_row(area);records.previous=records_button(row,"_Previous batch",G_CALLBACK(records_previous),NULL);records.more=records_button(row,"_Next batch",G_CALLBACK(records_more),NULL);
  records.refresh=records_button(row,"_Refresh records",G_CALLBACK(records_refresh),NULL);records.cancel=records_button(row,"Cancel operation",G_CALLBACK(records_cancel),NULL);
  row=records_button_row(area);records.retry=records_button(row,"Confirm original save",G_CALLBACK(records_retry_button),NULL);records.discard=records_button(row,"End save confirmation",G_CALLBACK(records_discard),NULL);
  records.token++;records.selected=SIZE_MAX;records.page.complete=1;records.pending=records.pending_error=FALSE;records.code=records.match=0;
  g_signal_connect(records.dialog,"destroy",G_CALLBACK(records_destroyed),NULL);g_signal_connect(records.dialog,"delete-event",G_CALLBACK(records_delete),NULL);
  g_signal_connect(records.dialog,"response",G_CALLBACK(records_response),NULL);g_signal_connect(records.dialog,"window-state-event",G_CALLBACK(records_background),NULL);
  gtk_widget_show_all(records.dialog);records_queue(READER_RECORDS_LIST,0,0,NULL,NULL,0);gtk_widget_grab_focus(records.list);state();
}
static void records_choose_history(reader_result *result) {
  if(!records.dialog || !result->records_version_count) return;
  uint64_t token=records.token;GtkWidget *dialog=gtk_dialog_new_with_buttons("Explicitly choose a retained version",GTK_WINDOW(records.dialog),GTK_DIALOG_MODAL|GTK_DIALOG_DESTROY_WITH_PARENT,
    "_Back",GTK_RESPONSE_CANCEL,"_Restore selected version",GTK_RESPONSE_ACCEPT,NULL);g_object_ref_sink(dialog);records.choice=dialog;
  GtkWidget *area=gtk_dialog_get_content_area(GTK_DIALOG(dialog)),*message=gtk_label_new(result->message);gtk_label_set_line_wrap(GTK_LABEL(message),TRUE);gtk_box_pack_start(GTK_BOX(area),message,FALSE,FALSE,6);
  GtkWidget *list=gtk_list_box_new();gtk_list_box_set_selection_mode(GTK_LIST_BOX(list),GTK_SELECTION_SINGLE);gtk_list_box_set_activate_on_single_click(GTK_LIST_BOX(list),FALSE);atk_object_set_name(gtk_widget_get_accessible(list),"Retained reading versions");
  for(size_t i=0;i<result->records_version_count;i++) { GtkWidget *row=gtk_list_box_row_new(),*label=gtk_label_new(result->records_version_labels[i]);gtk_label_set_line_wrap(GTK_LABEL(label),TRUE);gtk_label_set_xalign(GTK_LABEL(label),0);gtk_container_add(GTK_CONTAINER(row),label);g_object_set_data(G_OBJECT(row),"version-index",GSIZE_TO_POINTER(i));gtk_container_add(GTK_CONTAINER(list),row); }
  GtkWidget *view=gtk_scrolled_window_new(NULL,NULL);gtk_widget_set_size_request(view,480,260);gtk_container_add(GTK_CONTAINER(view),list);gtk_box_pack_start(GTK_BOX(area),view,TRUE,TRUE,6);
  gtk_widget_show_all(dialog);gtk_list_box_unselect_all(GTK_LIST_BOX(list));int response=gtk_dialog_run(GTK_DIALOG(dialog));char *version=NULL;
  if(records.dialog && records.token==token && response==GTK_RESPONSE_ACCEPT && !gtk_widget_in_destruction(list)) { GtkListBoxRow *row=gtk_list_box_get_selected_row(GTK_LIST_BOX(list));if(row) { size_t index=GPOINTER_TO_SIZE(g_object_get_data(G_OBJECT(row),"version-index"));if(index<result->records_version_count) version=g_strdup(result->records_versions[index]); } }
  if(records.choice==dialog) records.choice=NULL;
  gtk_widget_destroy(dialog);g_object_unref(dialog);
  if(version) { if(records_confirm("Restore this retained version?","The original file must independently resolve the selected location before a new restore revision is saved.","_Restore")) records_queue(READER_RECORDS_SAVE,records_target_kind(),READER_RC_RESTORE,NULL,version,0);g_free(version); }
}
static gboolean reading_records_apply(host_result *done) {
  reader_result *result=&done->value;
  if(done->generation!=g_atomic_int_get(&generation) || !records.dialog || result->records_token!=records.token) return TRUE;
  records.running=FALSE;records.code=result->records_code;records.match=result->records_match;
  if(done->action==READER_RECORDS_JUMP && result->status==EXR_OK && result->has_frame && result->records_match==EXR_ANCHOR_FOUND) {
    records_rows_clear();gtk_widget_destroy(records.dialog);return FALSE;
  }
  busy=FALSE;
  if(result->status==EXR_OK && done->action==READER_RECORDS_LIST) {
    records_rows_clear();records.page=result->records_page;memset(&result->records_page,0,sizeof(result->records_page));
    records.progress_state=result->records_progress_state;records.progress_deleted=result->records_progress_deleted;
    g_strlcpy(records.progress_head,result->records_progress_head,33);g_strlcpy(records.progress_sha,result->records_progress_sha,65);
    records.pending=result->records_pending;records.pending_error=result->records_pending_error;g_strlcpy(records.pending_revision,result->records_revision,33);
    char *progress_label=g_strdup_printf("Saved progress · %s · %zu versions / %zu current / %zu missing / %zu unrelated%s",records_state_name(records.progress_state,1),
      result->records_progress_revisions,result->records_progress_heads,result->records_progress_missing,result->records_progress_foreign,records.progress_deleted ? " · deleted":"");
    gtk_button_set_label(GTK_BUTTON(records.progress),progress_label);g_free(progress_label);
    for(size_t i=0;i<records.page.count;i++) {
      reader_av_item *item=&records.page.items[i];char *name;
      if(item->state!=READER_AV_STATE_SAFE) name=g_strdup_printf("%s · %zu versions / %zu current / %zu missing / %zu unrelated",records_state_name(item->state,0),item->revisions,item->heads,item->missing_parents,item->foreign_parents);
      else if(item->deleted) name=g_strdup_printf("Record %.8s · deleted · retained versions available",item->annotation_id);
      else {
        char *body=g_utf8_substring(item->note_text ? item->note_text:"",0,120);
        name=g_strdup_printf("%s %.8s · %s · location not checked",item->kind==READER_AV_KIND_BOOKMARK ? "Bookmark":"Annotation",item->annotation_id,body);g_free(body);
      }
      GtkWidget *row=gtk_list_box_row_new(),*label=gtk_label_new(name);gtk_label_set_line_wrap(GTK_LABEL(label),TRUE);gtk_label_set_xalign(GTK_LABEL(label),0);
      gtk_container_add(GTK_CONTAINER(row),label);atk_object_set_name(gtk_widget_get_accessible(row),name);g_free(name);g_object_set_data(G_OBJECT(row),"record-index",GSIZE_TO_POINTER(i));gtk_container_add(GTK_CONTAINER(records.list),row);
    }
    gtk_widget_show_all(records.list);gtk_list_box_unselect_all(GTK_LIST_BOX(records.list));
  } else if(done->action==READER_RECORDS_SAVE || done->action==READER_RECORDS_RETRY || done->action==READER_RECORDS_DISCARD) {
    records.pending=result->records_pending;records.pending_error=result->records_pending_error;g_strlcpy(records.pending_revision,result->records_revision,33);
    if(result->status==EXR_OK) { records_controls();records_queue(READER_RECORDS_LIST,0,0,NULL,NULL,0);return TRUE; }
  }
  records_controls();records_message(result->message);state();
  if(result->status==EXR_OK && done->action==READER_RECORDS_HISTORY) records_choose_history(result);
  return TRUE;
}
static char *reading_records_observation(void) {
  return g_strdup_printf("[reading_records]\nvisible=%d\nrunning=%d\ncount=%zu\ncomplete=%d\nbudget_stopped=%d\noutput_bytes=%zu\nwire_bytes=%zu\npending=%d\npending_error=%d\nprogress_state=%d\nprogress_deleted=%d\nselected=%zu\nprogress_selected=%d\ncode=%d\nmatch=%d\ntoken=%"G_GUINT64_FORMAT"\nactions=%u\nclosed=%u\nhas_range=%d\nrange_start=%zu\nrange_end=%zu\n",
    records.dialog!=NULL,records.running,records.page.count,records.page.complete,records.page.budget_stopped,records.page.output_bytes,records.page.wire_bytes,
    records.pending,records.pending_error,records.progress_state,records.progress_deleted,records.selected,records.progress_selected,records.code,records.match,records.token,records.actions,records.closed,records.has_range,records.start,records.end);
}
