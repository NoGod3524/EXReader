/* SPDX-License-Identifier: MIT */
/* Native GTK controls for the Wave 3 reading tools: annotation import with a
   checked preview, the local font library, original export, jump history and a
   read-only sync status. GTK only commands the single SDK owner worker; it never
   touches an SDK, revision, font or session handle itself. Compact More menu and
   keyboard shortcuts reach every tool; the default reading screen is unchanged. */
enum { W3_IDLE=0, W3_CHECKING, W3_PREVIEW, W3_IMPORTING, W3_DONE, W3_REFUSED };
static struct {
  GtkWidget *back_item,*forward_item;
  int can_back,can_forward,history_count,history_cursor,history_code,history_moves,history_refused;
  GtkWidget *ann_dialog;char *ann_path;int ann_phase,ann_code,ann_validated;
  uint64_t ann_annotations,ann_heads,ann_omitted,ann_created,ann_duplicates,ann_committed,ann_bytes;
  GtkWidget *font_dialog,*font_list,*font_status,*font_use,*font_remove,*font_add;
  int font_busy,font_count,font_failed,font_applied;char *font_active,*font_notice;
  int export_phase,export_code,export_created,export_durable;uint64_t export_bytes;char *export_path;
  GtkWidget *sync_view,*sync_button;int sync_busy,sync_phase,sync_code,sync_refreshes;char *sync_text;
  const char *next_hash;int next_direction;
} w3;

static gboolean w3_opened(void) { return w3.ann_dialog!=NULL || w3.font_dialog!=NULL; }
static gboolean w3_sync_busy(void) { return w3.sync_busy; }
static void w3_restore_focus(void) {
#ifdef EXR_READER_GTK_COMPACT
  if(window && !closing) {
    gtk_window_present(GTK_WINDOW(window));
    if(compact_page_focus) gtk_widget_grab_focus(compact_page_focus);
  }
#endif
}
static gboolean w3_ready(void) {
  if(closing || book_id<=0 || !stack || strcmp(gtk_stack_get_visible_child_name(GTK_STACK(stack)),"reader")) {
    status(EXR_ARGUMENT,"Open a book to use the reading tools");return FALSE;
  }
  if(busy || saving || save_failed) { status(EXR_OK,"Reading operation in progress; try again when it finishes");return FALSE; }
  if(w3.ann_phase==W3_CHECKING || w3.ann_phase==W3_IMPORTING || w3.font_busy || w3.export_phase==W3_CHECKING) {
    status(EXR_OK,"Reading tool operation in progress; try again when it finishes");return FALSE;
  }
  if(w3_opened()) return FALSE;
  return TRUE;
}
static host_job *w3_job(reader_action action) {
  host_job *job=g_new0(host_job,1);job->command.action=action;job->command.book=book_id;
  job->command.part=part;job->command.page=page_number;return job;
}
static void w3_push(host_job *job) {
  job->generation=g_atomic_int_get(&generation);g_async_queue_push(queue,job);state();
}
static void w3_prepare(reader_command *command) {
  if(command->action==READER_W3_HISTORY) command->direction=w3.next_direction;
  if(command->action==READER_W3_FONT_USE) command->w3_hash=g_strdup(w3.next_hash ? w3.next_hash:"");
}

/* ---- jump history ---- */
static void w3_history_update(void) {
  gboolean reading=stack && book_id>0 && !strcmp(gtk_stack_get_visible_child_name(GTK_STACK(stack)),"reader");
  if(w3.back_item) gtk_widget_set_sensitive(w3.back_item,reading && w3.can_back);
  if(w3.forward_item) gtk_widget_set_sensitive(w3.forward_item,reading && w3.can_forward);
}
static void w3_history_move(int direction) {
  if(!w3_ready()) return;
  if(direction<0 ? !w3.can_back : !w3.can_forward) {
    w3.history_refused++;status(EXR_OK,direction<0 ? "No earlier reading position":"No later reading position");return;
  }
  w3.next_direction=direction;submit(READER_W3_HISTORY,book_id,NULL,font_size);
}
static void w3_history_menu(GtkWidget *item,gpointer value) { (void)item;w3_history_move(GPOINTER_TO_INT(value)); }

/* ---- annotation import: checked preview, then explicit confirmation ---- */
static void w3_annotation_stats(const reader_result *result) {
  w3.ann_code=result->w3_ann_code;w3.ann_validated=result->w3_ann_validated;w3.ann_annotations=result->w3_ann_annotations;
  w3.ann_heads=result->w3_ann_heads;w3.ann_omitted=result->w3_ann_omitted;w3.ann_created=result->w3_ann_created;
  w3.ann_duplicates=result->w3_ann_duplicates;w3.ann_committed=result->w3_ann_committed;w3.ann_bytes=result->w3_ann_bytes;
}
static void w3_annotation_response(GtkDialog *dialog,int response,gpointer unused) {
  (void)unused;
  if(response==GTK_RESPONSE_ACCEPT && w3.ann_path) {
    host_job *job=w3_job(READER_W3_ANNOTATION_IMPORT);job->command.w3_path=g_strdup(w3.ann_path);
    w3.ann_phase=W3_IMPORTING;status(EXR_OK,"Importing annotations");w3_push(job);
  } else {
    w3.ann_phase=W3_IDLE;w3_push(w3_job(READER_W3_ANNOTATION_DISCARD));
    status(EXR_OK,"Annotation import cancelled; nothing was imported");
  }
  gtk_widget_destroy(GTK_WIDGET(dialog));
}
static void w3_annotation_destroyed(GtkWidget *widget,gpointer unused) {
  (void)widget;(void)unused;w3.ann_dialog=NULL;w3_restore_focus();state();
}
static void w3_annotation_previewed(const reader_result *result) {
  w3_annotation_stats(result);
  if(result->status!=EXR_OK || !result->w3_ann_validated || closing) {
    w3.ann_phase=W3_REFUSED;status(result->status==EXR_OK ? EXR_FORMAT:result->status,result->message);return;
  }
  char *title=g_utf8_make_valid(result->w3_ann_title[0] ? result->w3_ann_title:"this book",-1);
  char *text=g_strdup_printf("The file for “%s” was checked completely.\n\n%llu annotation records · %llu current versions would be added · %llu older versions are not in the file\nFile size: %llu bytes\n\nNothing has been imported yet. Choose Import to add these records to this book, or Cancel to leave your library unchanged.",
    title,(unsigned long long)result->w3_ann_annotations,(unsigned long long)result->w3_ann_heads,
    (unsigned long long)result->w3_ann_omitted,(unsigned long long)result->w3_ann_bytes);
  w3.ann_dialog=gtk_dialog_new_with_buttons("Annotation import preview",GTK_WINDOW(window),GTK_DIALOG_MODAL|GTK_DIALOG_DESTROY_WITH_PARENT,
    "_Cancel",GTK_RESPONSE_CANCEL,"_Import annotations",GTK_RESPONSE_ACCEPT,NULL);
  gtk_window_set_default_size(GTK_WINDOW(w3.ann_dialog),560,260);
  GtkWidget *area=gtk_dialog_get_content_area(GTK_DIALOG(w3.ann_dialog)),*label=gtk_label_new(text);
  gtk_container_set_border_width(GTK_CONTAINER(area),16);
  gtk_label_set_line_wrap(GTK_LABEL(label),TRUE);gtk_label_set_xalign(GTK_LABEL(label),0);
  atk_object_set_name(gtk_widget_get_accessible(label),"Annotation import preview details");
  gtk_box_pack_start(GTK_BOX(area),label,TRUE,TRUE,6);
  gtk_dialog_set_default_response(GTK_DIALOG(w3.ann_dialog),GTK_RESPONSE_CANCEL);
  g_signal_connect(w3.ann_dialog,"response",G_CALLBACK(w3_annotation_response),NULL);
  g_signal_connect(w3.ann_dialog,"destroy",G_CALLBACK(w3_annotation_destroyed),NULL);
  gtk_widget_show_all(w3.ann_dialog);
  gtk_widget_grab_focus(gtk_dialog_get_widget_for_response(GTK_DIALOG(w3.ann_dialog),GTK_RESPONSE_CANCEL));
  w3.ann_phase=W3_PREVIEW;g_free(text);g_free(title);
  status(EXR_OK,result->message);
}
static void w3_annotation_imported(const reader_result *result) {
  w3_annotation_stats(result);
  w3.ann_phase=result->status==EXR_OK ? W3_DONE:W3_REFUSED;status(result->status,result->message);
}
static void w3_annotation_open(GtkWidget *item,gpointer unused) {
  (void)item;(void)unused;if(!w3_ready()) return;
  GtkWidget *dialog=gtk_file_chooser_dialog_new("Import annotations",GTK_WINDOW(window),GTK_FILE_CHOOSER_ACTION_OPEN,
    "Cancel",GTK_RESPONSE_CANCEL,"Check file",GTK_RESPONSE_ACCEPT,NULL);
  choosing_file=TRUE;
  int response=gtk_dialog_run(GTK_DIALOG(dialog));choosing_file=FALSE;
  char *path=response==GTK_RESPONSE_ACCEPT ? gtk_file_chooser_get_filename(GTK_FILE_CHOOSER(dialog)):NULL;
  gtk_widget_destroy(dialog);
  if(!path) { w3_restore_focus();state();return; }
  g_free(w3.ann_path);w3.ann_path=path;w3.ann_phase=W3_CHECKING;
  host_job *job=w3_job(READER_W3_ANNOTATION_PREVIEW);job->command.w3_path=g_strdup(path);
  status(EXR_OK,"Checking the annotation file");w3_push(job);
}

/* ---- reading font library ---- */
static void w3_font_notice(const char *text) {
  g_free(w3.font_notice);w3.font_notice=g_strdup(text ? text:"");
  if(w3.font_status) gtk_label_set_text(GTK_LABEL(w3.font_status),w3.font_notice);
}
static void w3_fonts_update(void) {
  if(!w3.font_dialog || !w3.font_list) return;
  GtkListBoxRow *row=gtk_list_box_get_selected_row(GTK_LIST_BOX(w3.font_list));
  const char *hash=row ? g_object_get_data(G_OBJECT(row),"font-hash"):NULL;
  gboolean different=hash && strcmp(hash,w3.font_active ? w3.font_active:"");
  gtk_widget_set_sensitive(w3.font_use,different && !w3.font_busy);
  gtk_widget_set_sensitive(w3.font_remove,hash && hash[0] && different && !w3.font_busy);
  gtk_widget_set_sensitive(w3.font_add,!w3.font_busy);
}
static void w3_fonts_fill(const reader_result *result) {
  if(!w3.font_dialog || !w3.font_list) return;
  g_free(w3.font_active);w3.font_active=g_strdup(result->w3_font_active);
  w3.font_count=result->w3_font_count;
  rows_clear(w3.font_list);
  GtkWidget *selected=NULL;
  for(int i=-1;i<result->w3_font_count;i++) {
    const char *hash=i<0 ? "":result->w3_font_hashes[i],*name=i<0 ? "Built-in font":result->w3_font_names[i];
    char *safe=g_utf8_make_valid(name,-1);
    char *caption=g_strdup_printf("%s%s",safe,!strcmp(hash,w3.font_active) ? " (in use)":"");
    GtkWidget *row=gtk_list_box_row_new(),*label=gtk_label_new(caption);
    gtk_label_set_xalign(GTK_LABEL(label),0);gtk_container_add(GTK_CONTAINER(row),label);
    atk_object_set_name(gtk_widget_get_accessible(row),caption);
    g_object_set_data_full(G_OBJECT(row),"font-hash",g_strdup(hash),g_free);
    gtk_container_add(GTK_CONTAINER(w3.font_list),row);
    if(!strcmp(hash,w3.font_active)) selected=row;
    g_free(caption);g_free(safe);
  }
  gtk_widget_show_all(w3.font_list);
  if(selected) gtk_list_box_select_row(GTK_LIST_BOX(w3.font_list),GTK_LIST_BOX_ROW(selected));
  w3_fonts_update();
}
static void w3_fonts_selected(GtkListBox *box,GtkListBoxRow *row,gpointer unused) {
  (void)box;(void)row;(void)unused;w3_fonts_update();
}
static void w3_fonts_list_request(void) {
  w3.font_busy=TRUE;w3_fonts_update();w3_push(w3_job(READER_W3_FONT_LIST));
}
static void w3_fonts_add(GtkWidget *button,gpointer unused) {
  (void)button;(void)unused;if(w3.font_busy || !w3.font_dialog) return;
  GtkWidget *dialog=gtk_file_chooser_dialog_new("Add font file",GTK_WINDOW(w3.font_dialog),GTK_FILE_CHOOSER_ACTION_OPEN,
    "Cancel",GTK_RESPONSE_CANCEL,"Add",GTK_RESPONSE_ACCEPT,NULL);
  choosing_file=TRUE;
  int response=gtk_dialog_run(GTK_DIALOG(dialog));choosing_file=FALSE;
  char *path=response==GTK_RESPONSE_ACCEPT ? gtk_file_chooser_get_filename(GTK_FILE_CHOOSER(dialog)):NULL;
  gtk_widget_destroy(dialog);
  if(!path) return;
  host_job *job=w3_job(READER_W3_FONT_IMPORT);job->command.w3_path=path;
  w3.font_busy=TRUE;w3_font_notice("Adding the font file…");w3_fonts_update();w3_push(job);
}
static void w3_fonts_remove(GtkWidget *button,gpointer unused) {
  (void)button;(void)unused;if(w3.font_busy || !w3.font_dialog) return;
  GtkListBoxRow *row=gtk_list_box_get_selected_row(GTK_LIST_BOX(w3.font_list));
  const char *hash=row ? g_object_get_data(G_OBJECT(row),"font-hash"):NULL;
  if(!hash || !hash[0]) return;
  host_job *job=w3_job(READER_W3_FONT_REMOVE);job->command.w3_hash=g_strdup(hash);
  w3.font_busy=TRUE;w3_font_notice("Removing the font…");w3_fonts_update();w3_push(job);
}
static void w3_fonts_use(GtkWidget *button,gpointer unused) {
  (void)button;(void)unused;if(w3.font_busy || !w3.font_dialog) return;
  GtkListBoxRow *row=gtk_list_box_get_selected_row(GTK_LIST_BOX(w3.font_list));
  if(!row) return;
  if(closing || busy || saving || save_failed) { w3_font_notice("Reading operation in progress; try again when it finishes");return; }
  w3.next_hash=g_object_get_data(G_OBJECT(row),"font-hash");
  submit(READER_W3_FONT_USE,book_id,NULL,font_size);
  w3.next_hash=NULL;w3.font_busy=busy;
  if(busy) w3_font_notice("Applying the font; the current page stays until it is ready");
  w3_fonts_update();
}
static void w3_fonts_response(GtkDialog *dialog,int response,gpointer unused) {
  (void)response;(void)unused;gtk_widget_destroy(GTK_WIDGET(dialog));
}
static void w3_fonts_destroyed(GtkWidget *widget,gpointer unused) {
  (void)widget;(void)unused;
  w3.font_dialog=w3.font_list=w3.font_status=w3.font_use=w3.font_remove=w3.font_add=NULL;
  w3_restore_focus();state();
}
static GtkWidget *w3_font_button(GtkWidget *box,const char *text,GCallback callback) {
  GtkWidget *button=gtk_button_new_with_mnemonic(text);gtk_box_pack_start(GTK_BOX(box),button,FALSE,FALSE,0);
  g_signal_connect(button,"clicked",callback,NULL);return button;
}
static void w3_fonts_open(GtkWidget *item,gpointer unused) {
  (void)item;(void)unused;if(!w3_ready()) return;
  w3.font_dialog=gtk_dialog_new_with_buttons("Reading font",GTK_WINDOW(window),GTK_DIALOG_MODAL|GTK_DIALOG_DESTROY_WITH_PARENT,
    "_Close",GTK_RESPONSE_CLOSE,NULL);
  gtk_window_set_default_size(GTK_WINDOW(w3.font_dialog),520,380);
  GtkWidget *area=gtk_dialog_get_content_area(GTK_DIALOG(w3.font_dialog));
  gtk_container_set_border_width(GTK_CONTAINER(area),12);
  w3.font_list=gtk_list_box_new();atk_object_set_name(gtk_widget_get_accessible(w3.font_list),"Font library");
  GtkWidget *frame=gtk_scrolled_window_new(NULL,NULL);
  atk_object_set_name(gtk_widget_get_accessible(frame),"Font library list");
  gtk_scrolled_window_set_min_content_height(GTK_SCROLLED_WINDOW(frame),180);
  gtk_container_add(GTK_CONTAINER(frame),w3.font_list);gtk_box_pack_start(GTK_BOX(area),frame,TRUE,TRUE,4);
  GtkWidget *buttons=gtk_box_new(GTK_ORIENTATION_HORIZONTAL,7);
  w3.font_add=w3_font_button(buttons,"_Add font file…",G_CALLBACK(w3_fonts_add));
  w3.font_use=w3_font_button(buttons,"_Use selected",G_CALLBACK(w3_fonts_use));
  w3.font_remove=w3_font_button(buttons,"_Remove",G_CALLBACK(w3_fonts_remove));
  gtk_box_pack_start(GTK_BOX(area),buttons,FALSE,FALSE,6);
  w3.font_status=gtk_label_new("");gtk_label_set_line_wrap(GTK_LABEL(w3.font_status),TRUE);gtk_label_set_xalign(GTK_LABEL(w3.font_status),0);
  atk_object_set_name(gtk_widget_get_accessible(w3.font_status),"Reading font status");
  gtk_box_pack_start(GTK_BOX(area),w3.font_status,FALSE,FALSE,4);
  g_signal_connect(w3.font_list,"row-selected",G_CALLBACK(w3_fonts_selected),NULL);
  g_signal_connect(w3.font_dialog,"response",G_CALLBACK(w3_fonts_response),NULL);
  g_signal_connect(w3.font_dialog,"destroy",G_CALLBACK(w3_fonts_destroyed),NULL);
  gtk_widget_show_all(w3.font_dialog);gtk_widget_grab_focus(w3.font_list);
  w3_font_notice("Loading the font library…");w3_fonts_list_request();
}
static void w3_fonts_applied(const reader_result *result,reader_action action) {
  w3.font_busy=FALSE;
  if(w3.font_dialog) {
    if(result->w3_font_hashes || result->w3_font_count==0) w3_fonts_fill(result);
    if(result->status!=EXR_OK) w3.font_failed++;
    w3_font_notice(result->message);
  }
  if(action==READER_W3_FONT_IMPORT || action==READER_W3_FONT_REMOVE) status(result->status,result->message);
}

/* ---- original export ---- */
static void w3_exported(const reader_result *result) {
  w3.export_code=result->w3_export_code;w3.export_created=result->w3_export_created;w3.export_durable=result->w3_export_durable;
  w3.export_bytes=result->w3_export_bytes;g_free(w3.export_path);w3.export_path=g_strdup(result->w3_export_path);
  w3.export_phase=result->status==EXR_OK ? W3_DONE:W3_REFUSED;
  if(result->status==EXR_OK) {
    char *name=g_path_get_basename(w3.export_path ? w3.export_path:"original");
    char *text=g_strdup_printf("%s: %s (%llu bytes)",result->message,name,(unsigned long long)result->w3_export_bytes);
    status(EXR_OK,text);g_free(text);g_free(name);
  } else status(result->status,result->message);
}
static void w3_export_open(GtkWidget *item,gpointer unused) {
  (void)item;(void)unused;if(!w3_ready()) return;
  GtkWidget *dialog=gtk_file_chooser_dialog_new("Export original",GTK_WINDOW(window),GTK_FILE_CHOOSER_ACTION_SELECT_FOLDER,
    "Cancel",GTK_RESPONSE_CANCEL,"Export here",GTK_RESPONSE_ACCEPT,NULL);
  choosing_file=TRUE;
  int response=gtk_dialog_run(GTK_DIALOG(dialog));choosing_file=FALSE;
  char *path=response==GTK_RESPONSE_ACCEPT ? gtk_file_chooser_get_filename(GTK_FILE_CHOOSER(dialog)):NULL;
  gtk_widget_destroy(dialog);
  if(!path) { w3_restore_focus();state();return; }
  host_job *job=w3_job(READER_W3_EXPORT);job->command.w3_path=path;
  w3.export_phase=W3_CHECKING;status(EXR_OK,"Exporting the original file");w3_push(job);
}

/* ---- read-only sync status, shown inside the Account and Sync window ---- */
static void w3_sync_set_text(const char *text) {
  /* Reopening the window passes the saved text back into this function. */
  char *copy=g_strdup(text ? text:"");g_free(w3.sync_text);w3.sync_text=copy;
  if(w3.sync_view) gtk_text_buffer_set_text(gtk_text_view_get_buffer(GTK_TEXT_VIEW(w3.sync_view)),w3.sync_text,-1);
}
static void w3_sync_refresh(GtkWidget *button,gpointer unused) {
  (void)button;(void)unused;if(w3.sync_busy || !accounts.dialog || closing) return;
  host_job *job=w3_job(READER_W3_SYNC_STATUS);job->command.w3_session=accounts.session;
  w3.sync_busy=TRUE;w3.sync_phase=W3_CHECKING;
  if(w3.sync_button) gtk_widget_set_sensitive(w3.sync_button,FALSE);
  w3_push(job);
}
static void w3_sync_attach(GtkWidget *area,GtkWidget *operations) {
  w3.sync_button=gtk_button_new_with_mnemonic("Sync _view");
  atk_object_set_name(gtk_widget_get_accessible(w3.sync_button),"Sync status");
  gtk_widget_set_tooltip_text(w3.sync_button,"Read the current sync status without changing anything");
  g_signal_connect(w3.sync_button,"clicked",G_CALLBACK(w3_sync_refresh),NULL);
  gtk_box_pack_start(GTK_BOX(operations),w3.sync_button,FALSE,FALSE,0);
  w3.sync_view=gtk_text_view_new();
  gtk_text_view_set_editable(GTK_TEXT_VIEW(w3.sync_view),FALSE);gtk_text_view_set_cursor_visible(GTK_TEXT_VIEW(w3.sync_view),FALSE);
  gtk_text_view_set_wrap_mode(GTK_TEXT_VIEW(w3.sync_view),GTK_WRAP_WORD_CHAR);
  atk_object_set_name(gtk_widget_get_accessible(w3.sync_view),"Sync status details");
  GtkWidget *frame=gtk_scrolled_window_new(NULL,NULL);
  atk_object_set_name(gtk_widget_get_accessible(frame),"Sync status area");
  gtk_scrolled_window_set_min_content_height(GTK_SCROLLED_WINDOW(frame),110);
  gtk_container_add(GTK_CONTAINER(frame),w3.sync_view);gtk_box_pack_start(GTK_BOX(area),frame,TRUE,TRUE,4);
  w3_sync_set_text(w3.sync_text && w3.sync_text[0] ? w3.sync_text:"Choose Sync view to read the current sync status. This view is read-only and never starts, cancels or retries a sync.");
  gtk_widget_set_sensitive(w3.sync_button,!w3.sync_busy);
}
static void w3_sync_detach(void) { w3.sync_view=w3.sync_button=NULL; }
static void w3_sync_open(GtkWidget *item,gpointer unused) {
  (void)item;(void)unused;accounts_open(NULL,NULL);
}
static void w3_synced(const reader_result *result) {
  w3.sync_busy=FALSE;w3.sync_code=result->w3_sync_code;w3.sync_phase=result->status==EXR_OK ? W3_DONE:W3_REFUSED;w3.sync_refreshes++;
  w3_sync_set_text(result->w3_sync_text ? result->w3_sync_text:result->message);
  if(w3.sync_button) gtk_widget_set_sensitive(w3.sync_button,TRUE);
}

/* Both desktop layouts expose the same low-frequency native actions. */
static void w3_tools_menu(GtkWidget *menu) {
  GtkWidget *heading=gtk_menu_item_new_with_label("Reading tools"),*tools=gtk_menu_new();
  gtk_menu_item_set_submenu(GTK_MENU_ITEM(heading),tools);
  gtk_menu_shell_append(GTK_MENU_SHELL(menu),heading);
  const char *titles[]={"Import annotations…","Reading font…","Export original…",
    "Back to previous position","Forward to next position","Sync status…"};
  GCallback callbacks[]={G_CALLBACK(w3_annotation_open),G_CALLBACK(w3_fonts_open),G_CALLBACK(w3_export_open),
    G_CALLBACK(w3_history_menu),G_CALLBACK(w3_history_menu),G_CALLBACK(w3_sync_open)};
  for(size_t i=0;i<G_N_ELEMENTS(titles);i++) {
    GtkWidget *item=gtk_menu_item_new_with_label(titles[i]);
    gtk_menu_shell_append(GTK_MENU_SHELL(tools),item);
    gpointer value=i==3 ? GINT_TO_POINTER(-1):i==4 ? GINT_TO_POINTER(1):NULL;
    g_signal_connect(item,"activate",callbacks[i],value);
    if(i==3) w3.back_item=item;
    if(i==4) w3.forward_item=item;
  }
  w3_history_update();
}

/* ---- dispatch ---- */
static gboolean w3_apply(host_result *done) {
  reader_result *result=&done->value;
  if(done->action<READER_W3_ANNOTATION_PREVIEW || done->action>READER_W3_SYNC_STATUS) return FALSE;
  /* A result from a superseded book switch must not open or update a tool view. */
  if(done->generation!=g_atomic_int_get(&generation)) {
    /* The worker has released the borrowed inputs even when its view is stale.
       In particular sync_busy must stop retaining the account session. */
    if(done->action==READER_W3_SYNC_STATUS) {
      w3.sync_busy=FALSE;w3.sync_phase=W3_IDLE;
      if(w3.sync_button) gtk_widget_set_sensitive(w3.sync_button,TRUE);
    } else if(done->action>=READER_W3_FONT_LIST && done->action<=READER_W3_FONT_REMOVE) {
      w3.font_busy=FALSE;w3_fonts_update();
    } else if(done->action==READER_W3_ANNOTATION_PREVIEW || done->action==READER_W3_ANNOTATION_IMPORT) {
      w3.ann_phase=W3_IDLE;
    } else if(done->action==READER_W3_EXPORT) w3.export_phase=W3_IDLE;
    state();return TRUE;
  }
  if(done->action==READER_W3_FONT_USE || done->action==READER_W3_HISTORY) return FALSE;
  switch(done->action) {
    case READER_W3_ANNOTATION_PREVIEW: w3_annotation_previewed(result);break;
    case READER_W3_ANNOTATION_DISCARD: break;
    case READER_W3_ANNOTATION_IMPORT: w3_annotation_imported(result);break;
    case READER_W3_FONT_LIST: case READER_W3_FONT_IMPORT: case READER_W3_FONT_REMOVE: w3_fonts_applied(result,done->action);break;
    case READER_W3_EXPORT: w3_exported(result);break;
    default: w3_synced(result);break;
  }
  state();return TRUE;
}
/* Frame jobs (font use, history) and every accepted frame commit pass through here. */
static void w3_result(const reader_result *result,reader_action action) {
  if(action==READER_W3_FONT_USE) {
    w3.font_busy=FALSE;
    if(result->status!=EXR_OK) { w3.font_failed++;w3_font_notice(result->message); }
    else w3_font_notice("Font ready; accepting the new page");
    w3_fonts_update();
  }
  if(action==READER_W3_HISTORY && result->status!=EXR_OK) w3.history_refused++;
  if(action==READER_COMMIT && result->has_w3) {
    int moved=result->w3_history_count==w3.history_count && result->w3_history_cursor!=w3.history_cursor;
    w3.can_back=result->w3_can_back;w3.can_forward=result->w3_can_forward;
    w3.history_count=result->w3_history_count;w3.history_cursor=result->w3_history_cursor;w3.history_code=result->w3_history_code;
    if(moved) w3.history_moves++;
    w3_history_update();
    /* NULL means this window never learned the active face yet; "" is the real
       built-in face, so a first lease from it must count as an applied change. */
    if(w3.font_active==NULL) w3.font_active=g_strdup(result->w3_font_active);
    else if(strcmp(w3.font_active,result->w3_font_active)) {
      g_free(w3.font_active);w3.font_active=g_strdup(result->w3_font_active);w3.font_applied++;
      if(w3.font_dialog) { w3_font_notice("Reading font applied");w3_fonts_list_request(); }
    }
  }
  /* The accepted frame and its history/lease bookkeeping are now complete, so the
     observation file must carry them before the next user operation. */
  state();
}
static gboolean w3_key(GdkEventKey *event) {
  if(w3_opened()) return TRUE;
  gboolean control=(event->state&GDK_CONTROL_MASK)!=0,shift=(event->state&GDK_SHIFT_MASK)!=0,alt=(event->state&GDK_MOD1_MASK)!=0;
  if(control && shift && (event->keyval==GDK_KEY_N || event->keyval==GDK_KEY_n)) { w3_annotation_open(NULL,NULL);return TRUE; }
  if(control && shift && (event->keyval==GDK_KEY_Y || event->keyval==GDK_KEY_y)) { w3_fonts_open(NULL,NULL);return TRUE; }
  if(control && shift && (event->keyval==GDK_KEY_E || event->keyval==GDK_KEY_e)) { w3_export_open(NULL,NULL);return TRUE; }
  if(control && shift && (event->keyval==GDK_KEY_S || event->keyval==GDK_KEY_s)) { w3_sync_open(NULL,NULL);return TRUE; }
  if(alt && !control && (event->keyval==GDK_KEY_Left || event->keyval==GDK_KEY_Right)) {
    w3_history_move(event->keyval==GDK_KEY_Left ? -1:1);return TRUE;
  }
  return FALSE;
}
static char *w3_observation(void) {
  GKeyFile *file=g_key_file_new();const char *group="wave3";
  g_key_file_set_integer(file,group,"history_can_back",w3.can_back);g_key_file_set_integer(file,group,"history_can_forward",w3.can_forward);
  g_key_file_set_integer(file,group,"history_count",w3.history_count);g_key_file_set_integer(file,group,"history_cursor",w3.history_cursor);
  g_key_file_set_integer(file,group,"history_code",w3.history_code);g_key_file_set_integer(file,group,"history_moves",w3.history_moves);
  g_key_file_set_integer(file,group,"history_refused",w3.history_refused);
  g_key_file_set_integer(file,group,"back_enabled",w3.back_item && gtk_widget_get_sensitive(w3.back_item));
  g_key_file_set_integer(file,group,"forward_enabled",w3.forward_item && gtk_widget_get_sensitive(w3.forward_item));
  g_key_file_set_integer(file,group,"ann_phase",w3.ann_phase);g_key_file_set_integer(file,group,"ann_dialog",w3.ann_dialog!=NULL);
  g_key_file_set_integer(file,group,"ann_code",w3.ann_code);g_key_file_set_integer(file,group,"ann_validated",w3.ann_validated);
  g_key_file_set_uint64(file,group,"ann_annotations",w3.ann_annotations);g_key_file_set_uint64(file,group,"ann_heads",w3.ann_heads);
  g_key_file_set_uint64(file,group,"ann_omitted",w3.ann_omitted);g_key_file_set_uint64(file,group,"ann_created",w3.ann_created);
  g_key_file_set_uint64(file,group,"ann_duplicates",w3.ann_duplicates);g_key_file_set_uint64(file,group,"ann_committed",w3.ann_committed);
  g_key_file_set_uint64(file,group,"ann_bytes",w3.ann_bytes);
  g_key_file_set_integer(file,group,"font_dialog",w3.font_dialog!=NULL);g_key_file_set_integer(file,group,"font_busy",w3.font_busy);
  g_key_file_set_integer(file,group,"font_count",w3.font_count);g_key_file_set_integer(file,group,"font_failed",w3.font_failed);
  g_key_file_set_integer(file,group,"font_applied",w3.font_applied);
  g_key_file_set_string(file,group,"font_active",w3.font_active ? w3.font_active:"");
  g_key_file_set_string(file,group,"font_notice",w3.font_notice ? w3.font_notice:"");
  g_key_file_set_integer(file,group,"export_phase",w3.export_phase);g_key_file_set_integer(file,group,"export_code",w3.export_code);
  g_key_file_set_integer(file,group,"export_created",w3.export_created);g_key_file_set_integer(file,group,"export_durable",w3.export_durable);
  g_key_file_set_uint64(file,group,"export_bytes",w3.export_bytes);
  g_key_file_set_string(file,group,"export_path",w3.export_path ? w3.export_path:"");
  g_key_file_set_integer(file,group,"sync_phase",w3.sync_phase);g_key_file_set_integer(file,group,"sync_busy",w3.sync_busy);
  g_key_file_set_integer(file,group,"sync_code",w3.sync_code);g_key_file_set_integer(file,group,"sync_refreshes",w3.sync_refreshes);
  g_key_file_set_integer(file,group,"sync_view_visible",w3.sync_view!=NULL);
  g_key_file_set_string(file,group,"sync_text",w3.sync_text ? w3.sync_text:"");
  char *data=g_key_file_to_data(file,NULL,NULL);g_key_file_free(file);return data;
}
