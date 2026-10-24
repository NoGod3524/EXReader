/* SPDX-License-Identifier: MIT */
/* Low-frequency native organizer; the main bookshelf retains its own cache. */
static struct {
  GtkWidget *dialog,*editor,*recovery,*types,*removed,*groups,*members,*navigation,*selected_label,*target_label,*message;
  GtkWidget *previous_groups,*next_groups,*previous_members,*next_members,*enter,*up,*rename,*remove,*restore,*add,*detach,*position;
  GtkWidget *name,*ordinal,*editor_message;
  char *parent,*selected,*selected_name,*selected_parent,*navigation_parent,*target_key,*target_title,*editor_parent,*editor_book;
  char group_cursor[33],member_cursor[73];uint64_t group_ordinal,member_ordinal,token;
  int kind,trash,group_direction,member_direction,entity,operation,selected_deleted,dependency;
  gboolean applying,closing,editor_closing;
} collections;
static void collections_queue(reader_action action);
static void collections_refresh(void);
static gboolean collections_opened(void) { return collections.dialog!=NULL; }
static void collections_string(char **target,const char *value) { g_free(*target);*target=g_strdup(value ? value:""); }
static GtkWidget *collections_scroll(GtkWidget *child) {
  GtkWidget *widget=gtk_scrolled_window_new(NULL,NULL);gtk_container_add(GTK_CONTAINER(widget),child);
  gtk_widget_set_vexpand(widget,TRUE);return widget;
}
static void collections_access(GtkWidget *widget,const char *name) { atk_object_set_name(gtk_widget_get_accessible(widget),name); }
static GtkWidget *collections_button(GtkWidget *box,const char *caption,GCallback callback,gpointer value) {
  GtkWidget *button=gtk_button_new_with_mnemonic(caption);gtk_box_pack_start(GTK_BOX(box),button,FALSE,FALSE,0);
  g_signal_connect(button,"clicked",callback,value);return button;
}
static void collections_editor_destroyed(GtkWidget *widget,gpointer unused) {
  (void)unused;
  if(widget==collections.editor) {
    collections.editor=collections.name=collections.ordinal=collections.editor_message=NULL;collections.token=0;
    g_clear_pointer(&collections.editor_parent,g_free);g_clear_pointer(&collections.editor_book,g_free);
  }
  state();
}
static void collections_close_editor(void) {
  collections.editor_closing=TRUE;
  if(collections.editor) gtk_widget_destroy(collections.editor);
  g_clear_pointer(&collections.editor_parent,g_free);g_clear_pointer(&collections.editor_book,g_free);
  collections.editor_closing=FALSE;
}
static void collections_destroyed(GtkWidget *widget,gpointer unused) {
  (void)widget;(void)unused;collections.closing=TRUE;collections.applying=TRUE;
  collections.dialog=collections.editor=collections.recovery=collections.types=collections.removed=NULL;
  collections.groups=collections.members=collections.navigation=collections.selected_label=collections.target_label=collections.message=NULL;
  collections.previous_groups=collections.next_groups=collections.previous_members=collections.next_members=NULL;
  collections.enter=collections.up=collections.rename=collections.remove=collections.restore=collections.add=collections.detach=collections.position=NULL;
  collections.name=collections.ordinal=collections.editor_message=NULL;
  char **values[]={&collections.parent,&collections.selected,&collections.selected_name,&collections.selected_parent,&collections.navigation_parent,
    &collections.target_key,&collections.target_title,&collections.editor_parent,&collections.editor_book};
  for(size_t i=0;i<G_N_ELEMENTS(values);i++) g_clear_pointer(values[i],g_free);
  if(!closing && shelf_filter_pending) shelf_request(0,FALSE);
  state();
}
static void collections_close(void) {
  if(metadata_running) return;
  collections.closing=TRUE;
  if(collections.dialog) gtk_widget_destroy(collections.dialog);
}
static gboolean collections_delete(GtkWidget *widget,GdkEvent *event,gpointer unused) {
  (void)event;(void)unused;
  if(!metadata_running) {
    if(widget==collections.dialog) collections_close();else gtk_widget_destroy(widget);
  }
  return TRUE;
}
static void collections_recovery_destroyed(GtkWidget *widget,gpointer unused) {
  (void)unused;if(widget==collections.recovery) collections.recovery=NULL;state();
}
static void collections_recovery_response(GtkDialog *dialog,int response,gpointer unused) {
  (void)unused;if(metadata_running) return;
  if(response==GTK_RESPONSE_ACCEPT) collections_queue(READER_COLLECTIONS_RETRY);
  else if(response==2) collections_queue(READER_COLLECTIONS_DISCARD);
  else gtk_widget_destroy(GTK_WIDGET(dialog));
}
static void collections_show_recovery(const char *message) {
  collections_close_editor();
  if(collections.recovery) gtk_widget_destroy(collections.recovery);
  collections.recovery=gtk_dialog_new_with_buttons("Recover collection change",GTK_WINDOW(collections.dialog),GTK_DIALOG_MODAL|GTK_DIALOG_DESTROY_WITH_PARENT,
    "Close",GTK_RESPONSE_CANCEL,"_Discard uncommitted",2,"_Retry",GTK_RESPONSE_ACCEPT,NULL);
  GtkWidget *notice=gtk_label_new(message && message[0] ? message:"An earlier change is retained and needs recovery");
  gtk_label_set_line_wrap(GTK_LABEL(notice),TRUE);gtk_container_set_border_width(GTK_CONTAINER(gtk_dialog_get_content_area(GTK_DIALOG(collections.recovery))),16);
  gtk_box_pack_start(GTK_BOX(gtk_dialog_get_content_area(GTK_DIALOG(collections.recovery))),notice,FALSE,FALSE,4);
  g_signal_connect(collections.recovery,"response",G_CALLBACK(collections_recovery_response),NULL);
  g_signal_connect(collections.recovery,"delete-event",G_CALLBACK(collections_delete),NULL);
  g_signal_connect(collections.recovery,"destroy",G_CALLBACK(collections_recovery_destroyed),NULL);
  gtk_dialog_set_default_response(GTK_DIALOG(collections.recovery),GTK_RESPONSE_ACCEPT);gtk_widget_show_all(collections.recovery);state();
}
static void collections_queue(reader_action action) {
  if(!collections.dialog || collections.closing || closing || metadata_running || busy || saving || save_failed) return;
  host_job *job=g_new0(host_job,1);job->generation=g_atomic_int_get(&generation);job->shelf_generation=g_atomic_int_get(&shelf_generation);
  reader_command *command=&job->command;command->action=action;command->collection_kind=collections.kind;
  command->collection_removed=collections.trash;command->collection_operation=collections.operation;command->collection_token=collections.token;
  command->collection_parent=g_strdup(collections.parent ? collections.parent:"");
  command->collection_id=g_strdup(collections.selected ? collections.selected:"");
  command->collection_group_cursor=g_strdup(collections.group_cursor);command->collection_group_cursor_ordinal=collections.group_ordinal;
  command->collection_member_cursor=g_strdup(collections.member_cursor);command->collection_member_cursor_ordinal=collections.member_ordinal;
  command->collection_group_direction=collections.group_direction;command->collection_member_direction=collections.member_direction;
  command->collection_book_key=g_strdup(collections.editor_book ? collections.editor_book:collections.target_key ? collections.target_key:"");
  if(action==READER_COLLECTIONS_SAVE_GROUP || action==READER_COLLECTIONS_SAVE_MEMBER) {
    command->collection_name=g_strdup(collections.name ? gtk_entry_get_text(GTK_ENTRY(collections.name)):"");
    command->collection_position=g_strdup(collections.ordinal ? gtk_entry_get_text(GTK_ENTRY(collections.ordinal)):"0");
  }
  metadata_running=busy=TRUE;gtk_widget_set_sensitive(collections.dialog,FALSE);
  if(collections.editor) gtk_widget_set_sensitive(collections.editor,FALSE);
  if(collections.recovery) gtk_widget_set_sensitive(collections.recovery,FALSE);
  status(EXR_OK,"Working on library organization");g_async_queue_push(queue,job);state();
}
static void collections_reset_pages(void) {
  collections.group_cursor[0]=collections.member_cursor[0]=0;collections.group_ordinal=collections.member_ordinal=0;
  collections.group_direction=collections.member_direction=1;
}
static void collections_refresh(void) { collections_reset_pages();collections_queue(READER_COLLECTIONS_LIST); }
static void collections_prepare_group(GtkWidget *button,gpointer value) {
  (void)button;if(metadata_running || collections.closing) return;
  int action=GPOINTER_TO_INT(value);collections.entity=0;collections.operation=action==3 ? 0:action;
  if(action==3) collections_string(&collections.selected,"");
  collections_queue(READER_COLLECTIONS_PREPARE_GROUP);
}
static void collections_prepare_member(GtkWidget *button,gpointer value) {
  (void)button;if(metadata_running || collections.closing || !collections.selected || !collections.selected[0]) return;
  collections.entity=1;collections.operation=GPOINTER_TO_INT(value)==1 ? 1:0;
  if(GPOINTER_TO_INT(value)==0) collections_string(&collections.editor_book,collections.target_key);
  else {
    GtkListBoxRow *row=gtk_list_box_get_selected_row(GTK_LIST_BOX(collections.members));
    if(!row) return;
    collections_string(&collections.editor_book,g_object_get_data(G_OBJECT(row),"member-key"));
  }
  if(!collections.editor_book || !collections.editor_book[0]) return;
  collections_queue(READER_COLLECTIONS_PREPARE_MEMBER);
}
static void collections_editor_response(GtkDialog *dialog,int response,gpointer unused) {
  (void)dialog;(void)unused;if(metadata_running) return;
  if(response==GTK_RESPONSE_ACCEPT) {
    if(collections.entity==0 && collections.operation!=1 && (!collections.name || !gtk_entry_get_text(GTK_ENTRY(collections.name))[0])) {
      gtk_label_set_text(GTK_LABEL(collections.editor_message),"Enter a collection name");return;
    }
    collections_queue(collections.entity==0 ? READER_COLLECTIONS_SAVE_GROUP:READER_COLLECTIONS_SAVE_MEMBER);
  } else if(response==3) {
    char *parent=g_strdup(collections.editor_parent);int kind=collections.entity==0 ? 0:collections.kind;
    collections_close_editor();collections.applying=TRUE;collections.kind=kind;collections.trash=1;
    gtk_combo_box_set_active(GTK_COMBO_BOX(collections.types),kind);gtk_toggle_button_set_active(GTK_TOGGLE_BUTTON(collections.removed),TRUE);
    collections_string(&collections.selected,parent);collections_string(&collections.parent,"");g_free(parent);collections.applying=FALSE;collections_refresh();
  } else collections_close_editor();
}
static void collections_show_editor(const reader_result *result) {
  collections_close_editor();collections.token=result->collection_token;collections.operation=result->collection_operation;
  collections.entity=result->collection_response==2 ? 0:1;
  collections_string(&collections.editor_parent,collections.entity==0 ? result->collection_selected.parent:result->collection_selected.id);
  if(collections.entity==1) collections_string(&collections.editor_book,result->collection_book_key);
  collections.editor=gtk_dialog_new_with_buttons(collections.entity==0 ? "Collection details":"Book classification",GTK_WINDOW(collections.dialog),
    GTK_DIALOG_MODAL|GTK_DIALOG_DESTROY_WITH_PARENT,"Cancel",GTK_RESPONSE_CANCEL,
    collections.operation==1 ? "_Remove":collections.operation==2 ? "_Restore":"_Save",GTK_RESPONSE_ACCEPT,NULL);
  GtkWidget *grid=gtk_grid_new();gtk_grid_set_row_spacing(GTK_GRID(grid),10);gtk_grid_set_column_spacing(GTK_GRID(grid),12);
  gtk_container_set_border_width(GTK_CONTAINER(grid),16);gtk_container_add(GTK_CONTAINER(gtk_dialog_get_content_area(GTK_DIALOG(collections.editor))),grid);
  int line=0;
  if(collections.entity==0) {
    GtkWidget *name=gtk_label_new_with_mnemonic("_Name");collections.name=gtk_entry_new();
    gtk_entry_set_max_length(GTK_ENTRY(collections.name),256);gtk_entry_set_width_chars(GTK_ENTRY(collections.name),38);
    gtk_entry_set_text(GTK_ENTRY(collections.name),result->collection_selected.name ? result->collection_selected.name:"");
    gtk_entry_set_activates_default(GTK_ENTRY(collections.name),TRUE);collections_access(collections.name,"Collection name");
    gtk_label_set_mnemonic_widget(GTK_LABEL(name),collections.name);gtk_grid_attach(GTK_GRID(grid),name,0,line,1,1);gtk_grid_attach(GTK_GRID(grid),collections.name,1,line++,1,1);
    gtk_editable_set_editable(GTK_EDITABLE(collections.name),collections.operation==0);
  } else {
    char *caption=g_strdup_printf("%s\n%s",result->collection_book_title ? result->collection_book_title:"Book",result->collection_selected.name ? result->collection_selected.name:"Collection");
    GtkWidget *notice=gtk_label_new(caption);g_free(caption);gtk_grid_attach(GTK_GRID(grid),notice,0,line++,2,1);
  }
  GtkWidget *position=gtk_label_new_with_mnemonic("_Position");collections.ordinal=gtk_entry_new();
  char ordinal[32];g_snprintf(ordinal,sizeof(ordinal),"%"G_GUINT64_FORMAT,result->collection_ordinal);
  gtk_entry_set_text(GTK_ENTRY(collections.ordinal),ordinal);gtk_entry_set_max_length(GTK_ENTRY(collections.ordinal),19);
  gtk_entry_set_input_purpose(GTK_ENTRY(collections.ordinal),GTK_INPUT_PURPOSE_DIGITS);gtk_entry_set_activates_default(GTK_ENTRY(collections.ordinal),TRUE);
  gtk_label_set_mnemonic_widget(GTK_LABEL(position),collections.ordinal);collections_access(collections.ordinal,"Collection position");
  gtk_grid_attach(GTK_GRID(grid),position,0,line,1,1);gtk_grid_attach(GTK_GRID(grid),collections.ordinal,1,line++,1,1);
  gboolean ordered=collections.entity==0 ? collections.kind==0:collections.kind!=1;
  gtk_widget_set_sensitive(collections.ordinal,ordered && collections.operation==0);
  collections.editor_message=gtk_label_new(result->collection_dependency ? "Restore the parent collection first":result->collection_conflict ? "Versions differ; refresh before changing this collection":"");
  gtk_label_set_line_wrap(GTK_LABEL(collections.editor_message),TRUE);gtk_grid_attach(GTK_GRID(grid),collections.editor_message,0,line,2,1);
  if(result->collection_dependency) gtk_dialog_add_button(GTK_DIALOG(collections.editor),"View _parent",3);
  gtk_dialog_set_response_sensitive(GTK_DIALOG(collections.editor),GTK_RESPONSE_ACCEPT,!result->collection_dependency && !result->collection_conflict);
  gtk_dialog_set_default_response(GTK_DIALOG(collections.editor),GTK_RESPONSE_ACCEPT);
  g_signal_connect(collections.editor,"response",G_CALLBACK(collections_editor_response),NULL);
  g_signal_connect(collections.editor,"delete-event",G_CALLBACK(collections_delete),NULL);
  g_signal_connect(collections.editor,"destroy",G_CALLBACK(collections_editor_destroyed),NULL);
  gtk_widget_show_all(collections.editor);gtk_widget_grab_focus(collections.entity==0 ? collections.name:collections.ordinal);state();
}
static void collections_group_selected(GtkListBox *box,GtkListBoxRow *row,gpointer unused) {
  (void)box;(void)unused;if(collections.applying || collections.closing || metadata_running || !row) return;
  collections_string(&collections.selected,g_object_get_data(G_OBJECT(row),"group-id"));collections.member_cursor[0]=0;
  collections.member_ordinal=0;collections.member_direction=1;collections_queue(READER_COLLECTIONS_LIST);
}
static void collections_member_selected(GtkListBox *box,GtkListBoxRow *row,gpointer unused) {
  (void)box;(void)unused;if(collections.applying || collections.closing || closing) return;
  gboolean selected=row!=NULL && !collections.selected_deleted;
  if(collections.detach) gtk_widget_set_sensitive(collections.detach,selected);
  if(collections.position) gtk_widget_set_sensitive(collections.position,selected && collections.kind!=1);state();
}
static void collections_enter(GtkWidget *button,gpointer unused) {
  (void)button;(void)unused;if(collections.kind!=0 || collections.trash || !collections.selected || collections.selected_deleted) return;
  collections_string(&collections.parent,collections.selected);collections_string(&collections.selected,"");collections_refresh();
}
static void collections_up(GtkWidget *button,gpointer value) {
  (void)button;collections_string(&collections.parent,GPOINTER_TO_INT(value)==1 ? "":collections.navigation_parent);
  collections_string(&collections.selected,"");collections_refresh();
}
static void collections_group_activated(GtkListBox *box,GtkListBoxRow *row,gpointer unused) { (void)box;(void)row;collections_enter(NULL,unused); }
static void collections_member_activated(GtkListBox *box,GtkListBoxRow *row,gpointer unused) {
  (void)box;(void)unused;if(metadata_running || !row) return;
  int64_t *id=g_object_get_data(G_OBJECT(row),"member-sdk-id");
  if(!id || *id<=0) { gtk_label_set_text(GTK_LABEL(collections.message),"Download this original before opening it");return; }
  int64_t book=*id;collections_close();open_id(book);
}
static void collections_page(GtkWidget *button,gpointer value) {
  (void)button;int which=GPOINTER_TO_INT(value);GtkWidget *list=which<2 ? collections.groups:collections.members;
  GList *rows=gtk_container_get_children(GTK_CONTAINER(list));if(!rows) return;
  gboolean forward=(which%2)==1;GtkWidget *row=forward ? g_list_last(rows)->data:rows->data;
  uint64_t *ordinal=g_object_get_data(G_OBJECT(row),"ordinal");
  if(which<2) {
    g_snprintf(collections.group_cursor,sizeof(collections.group_cursor),"%s",(char *)g_object_get_data(G_OBJECT(row),"group-id"));
    collections.group_ordinal=ordinal ? *ordinal:0;collections.group_direction=forward ? 1:-1;
    collections_string(&collections.selected,"");collections.member_cursor[0]=0;collections.member_ordinal=0;collections.member_direction=1;
  } else {
    g_snprintf(collections.member_cursor,sizeof(collections.member_cursor),"%s",(char *)g_object_get_data(G_OBJECT(row),"member-key"));
    collections.member_ordinal=ordinal ? *ordinal:0;collections.member_direction=forward ? 1:-1;
  }
  g_list_free(rows);collections_queue(READER_COLLECTIONS_LIST);
}
static void collections_changed(GtkWidget *widget,gpointer unused) {
  (void)widget;(void)unused;if(collections.applying || collections.closing || metadata_running) return;
  collections.kind=gtk_combo_box_get_active(GTK_COMBO_BOX(collections.types));collections.trash=gtk_toggle_button_get_active(GTK_TOGGLE_BUTTON(collections.removed));
  collections_string(&collections.parent,"");collections_string(&collections.selected,"");collections_refresh();
}
static gboolean collections_keys(GtkWidget *widget,GdkEventKey *event,gpointer unused) {
  (void)widget;(void)unused;if(metadata_running) return FALSE;
  if(event->state&GDK_CONTROL_MASK) {
    if(event->keyval==GDK_KEY_Page_Down) { if(gtk_widget_get_sensitive(collections.next_groups)) collections_page(NULL,GINT_TO_POINTER(1));return TRUE; }
    if(event->keyval==GDK_KEY_Page_Up) { if(gtk_widget_get_sensitive(collections.previous_groups)) collections_page(NULL,GINT_TO_POINTER(0));return TRUE; }
  }
  if(event->state&GDK_MOD1_MASK) {
    if(event->keyval==GDK_KEY_Right) { if(gtk_widget_get_sensitive(collections.next_members)) collections_page(NULL,GINT_TO_POINTER(3));return TRUE; }
    if(event->keyval==GDK_KEY_Left) { if(gtk_widget_get_sensitive(collections.previous_members)) collections_page(NULL,GINT_TO_POINTER(2));return TRUE; }
  }
  return FALSE;
}
static void collections_response(GtkDialog *dialog,int response,gpointer unused) { (void)dialog;(void)response;(void)unused;collections_close(); }
static void collections_present(const reader_result *result) {
  GtkWidget *focus=gtk_window_get_focus(GTK_WINDOW(collections.dialog));
  gboolean group_focus=focus && (focus==collections.groups || gtk_widget_is_ancestor(focus,collections.groups));
  gboolean member_focus=focus && (focus==collections.members || gtk_widget_is_ancestor(focus,collections.members));
  GtkListBoxRow *current=gtk_list_box_get_selected_row(GTK_LIST_BOX(collections.members));
  char *member_key=g_strdup(current ? g_object_get_data(G_OBJECT(current),"member-key"):NULL);
  GtkWidget *selected_row=NULL,*selected_member=NULL;
  collections.applying=TRUE;rows_clear(collections.groups);rows_clear(collections.members);
  collections_string(&collections.selected,result->collection_selected.id);collections_string(&collections.selected_name,result->collection_selected.name);
  collections_string(&collections.selected_parent,result->collection_selected.parent);collections_string(&collections.navigation_parent,result->collection_navigation.parent);
  collections.selected_deleted=result->collection_selected.deleted;collections.dependency=result->collection_dependency;
  for(size_t i=0;i<result->collection_group_count;i++) {
    const reader_collection_group *group=&result->collection_groups[i];GtkWidget *row=gtk_list_box_row_new();
    GtkWidget *label=gtk_label_new(group->name);gtk_label_set_xalign(GTK_LABEL(label),0);gtk_widget_set_size_request(row,-1,36);
    gtk_container_add(GTK_CONTAINER(row),label);g_object_set_data_full(G_OBJECT(row),"group-id",g_strdup(group->id),g_free);
    uint64_t *ordinal=g_new(uint64_t,1);*ordinal=group->ordinal;g_object_set_data_full(G_OBJECT(row),"ordinal",ordinal,g_free);
    gtk_list_box_insert(GTK_LIST_BOX(collections.groups),row,-1);
    if(collections.selected && !strcmp(collections.selected,group->id)) { selected_row=row;gtk_list_box_select_row(GTK_LIST_BOX(collections.groups),GTK_LIST_BOX_ROW(row)); }
  }
  for(size_t i=0;i<result->collection_member_count;i++) {
    const reader_collection_member *book=&result->collection_members[i];GtkWidget *row=gtk_list_box_row_new();
    char *caption=collections.kind==1 ? g_strdup(book->title):g_strdup_printf("%"G_GUINT64_FORMAT" · %s",book->ordinal,book->title);
    GtkWidget *label=gtk_label_new(caption);g_free(caption);gtk_label_set_xalign(GTK_LABEL(label),0);gtk_widget_set_size_request(row,-1,36);
    gtk_container_add(GTK_CONTAINER(row),label);g_object_set_data_full(G_OBJECT(row),"member-key",g_strdup(book->key),g_free);
    uint64_t *ordinal=g_new(uint64_t,1);*ordinal=book->ordinal;g_object_set_data_full(G_OBJECT(row),"ordinal",ordinal,g_free);
    int64_t *id=g_new(int64_t,1);*id=book->sdk_id;g_object_set_data_full(G_OBJECT(row),"member-sdk-id",id,g_free);
    gtk_list_box_insert(GTK_LIST_BOX(collections.members),row,-1);
    if(member_key && !strcmp(member_key,book->key)) { selected_member=row;gtk_list_box_select_row(GTK_LIST_BOX(collections.members),GTK_LIST_BOX_ROW(row)); }
  }
  char *navigation=g_strdup_printf("%s%s",collections.trash ? "Removed collections":result->collection_navigation.name ? result->collection_navigation.name:"Library collections",
    result->collection_navigation.deleted ? " (parent removed)":"");
  gtk_label_set_text(GTK_LABEL(collections.navigation),navigation);g_free(navigation);
  char *selected=g_strdup_printf("%s%s",collections.selected_name && collections.selected_name[0] ? collections.selected_name:"Select a collection",
    collections.selected_deleted ? " (removed)":"");gtk_label_set_text(GTK_LABEL(collections.selected_label),selected);g_free(selected);
  gtk_widget_set_sensitive(collections.previous_groups,result->collection_group_before);gtk_widget_set_sensitive(collections.next_groups,result->collection_group_after);
  gtk_widget_set_sensitive(collections.previous_members,result->collection_member_before);gtk_widget_set_sensitive(collections.next_members,result->collection_member_after);
  gboolean selected_group=collections.selected && collections.selected[0];
  gtk_widget_set_sensitive(collections.enter,selected_group && collections.kind==0 && !collections.trash && !collections.selected_deleted);
  gtk_widget_set_sensitive(collections.up,collections.kind==0 && collections.parent && collections.parent[0] && !collections.trash);
  gtk_widget_set_sensitive(collections.rename,selected_group && !collections.selected_deleted);
  gtk_widget_set_sensitive(collections.remove,selected_group && !collections.selected_deleted);
  gtk_widget_set_sensitive(collections.restore,selected_group && collections.selected_deleted);
  gtk_widget_set_sensitive(collections.add,selected_group && !collections.selected_deleted && collections.target_key && collections.target_key[0]);
  gtk_widget_set_sensitive(collections.detach,selected_member!=NULL);gtk_widget_set_sensitive(collections.position,selected_member && collections.kind!=1);
  gtk_widget_show_all(collections.groups);gtk_widget_show_all(collections.members);collections.applying=FALSE;
  if(group_focus) gtk_widget_grab_focus(selected_row ? selected_row:collections.groups);
  else if(member_focus) gtk_widget_grab_focus(selected_member ? selected_member:collections.members);
  g_free(member_key);state();
}
static void collections_apply(host_result *done) {
  reader_result *result=&done->value;metadata_running=busy=FALSE;
  if(!collections.dialog) { state();return; }
  gtk_widget_set_sensitive(collections.dialog,TRUE);
  if(collections.editor) gtk_widget_set_sensitive(collections.editor,TRUE);
  if(collections.recovery) gtk_widget_set_sensitive(collections.recovery,TRUE);
  if(result->metadata_pending) collections_show_recovery(result->message);
  else if(result->status!=EXR_OK) {
    GtkWidget *message=collections.editor_message ? collections.editor_message:collections.message;
    gtk_label_set_text(GTK_LABEL(message),result->message[0] ? result->message:"Collection operation could not finish; current data is retained");
  } else if(result->collection_response==1) collections_present(result);
  else if(result->collection_response==2 || result->collection_response==3) collections_show_editor(result);
  else if(result->collection_response==4) {
    collections_close_editor();if(collections.recovery) gtk_widget_destroy(collections.recovery);
    if(result->collection_selected.id) collections_string(&collections.selected,result->collection_selected.id);
    if(!close_after_save) collections_refresh();
  }
  status(result->status,result->message[0] ? result->message:"Library organization ready");
  if(close_after_save) { close_after_save=FALSE;collections_close();stop_worker(); }
}
static void collections_open(GtkWidget *button,gpointer unused) {
  (void)button;(void)unused;if(closing || busy || saving || save_failed || metadata_running || metadata_dialog || collections.dialog) return;
  collections.closing=FALSE;collections.applying=TRUE;collections.kind=0;collections.trash=0;collections_reset_pages();
  GtkListBoxRow *selected=gtk_list_box_get_selected_row(GTK_LIST_BOX(shelf));
  collections.target_key=g_strdup(selected ? g_object_get_data(G_OBJECT(selected),"book-key"):"");
  const char *title=NULL;if(selected) { GtkWidget *child=gtk_bin_get_child(GTK_BIN(selected));if(GTK_IS_LABEL(child)) title=gtk_label_get_text(GTK_LABEL(child)); }
  collections.target_title=g_strdup(title ? title:"No selected book");collections.parent=g_strdup("");collections.selected=g_strdup("");
  collections.dialog=gtk_dialog_new_with_buttons("Library collections",GTK_WINDOW(window),GTK_DIALOG_MODAL|GTK_DIALOG_DESTROY_WITH_PARENT,"_Close",GTK_RESPONSE_CLOSE,NULL);
  gtk_window_set_default_size(GTK_WINDOW(collections.dialog),980,660);
  GtkWidget *area=gtk_dialog_get_content_area(GTK_DIALOG(collections.dialog));gtk_container_set_border_width(GTK_CONTAINER(area),12);
  GtkWidget *filters=gtk_box_new(GTK_ORIENTATION_HORIZONTAL,8);collections.types=gtk_combo_box_text_new();
  for(int i=0;i<3;i++) gtk_combo_box_text_append_text(GTK_COMBO_BOX_TEXT(collections.types),(const char *[]) {"Shelves","Tags","Series"}[i]);
  gtk_combo_box_set_active(GTK_COMBO_BOX(collections.types),0);collections_access(collections.types,"Collection type");
  GtkWidget *type=gtk_label_new_with_mnemonic("_Type");gtk_label_set_mnemonic_widget(GTK_LABEL(type),collections.types);
  gtk_box_pack_start(GTK_BOX(filters),type,FALSE,FALSE,0);gtk_box_pack_start(GTK_BOX(filters),collections.types,FALSE,FALSE,0);
  collections.removed=gtk_check_button_new_with_mnemonic("Re_moved");collections_access(collections.removed,"Removed collections");
  gtk_box_pack_start(GTK_BOX(filters),collections.removed,FALSE,FALSE,0);
  collections.up=collections_button(filters,"_Up",G_CALLBACK(collections_up),GINT_TO_POINTER(0));
  collections_button(filters,"Root",G_CALLBACK(collections_up),GINT_TO_POINTER(1));
  collections.navigation=gtk_label_new("Library collections");gtk_box_pack_start(GTK_BOX(filters),collections.navigation,TRUE,TRUE,0);
  gtk_box_pack_start(GTK_BOX(area),filters,FALSE,FALSE,4);
  GtkWidget *panes=gtk_box_new(GTK_ORIENTATION_HORIZONTAL,12),*left=gtk_box_new(GTK_ORIENTATION_VERTICAL,5),*right=gtk_box_new(GTK_ORIENTATION_VERTICAL,5);
  collections.groups=gtk_list_box_new();collections.members=gtk_list_box_new();gtk_widget_set_can_focus(collections.groups,TRUE);gtk_widget_set_can_focus(collections.members,TRUE);
  collections_access(collections.groups,"Collection groups");collections_access(collections.members,"Collection members");
  GtkWidget *groups=gtk_label_new_with_mnemonic("_Groups"),*members=gtk_label_new_with_mnemonic("_Books");
  gtk_label_set_mnemonic_widget(GTK_LABEL(groups),collections.groups);gtk_label_set_mnemonic_widget(GTK_LABEL(members),collections.members);
  gtk_box_pack_start(GTK_BOX(left),groups,FALSE,FALSE,0);gtk_box_pack_start(GTK_BOX(left),collections_scroll(collections.groups),TRUE,TRUE,0);
  GtkWidget *group_pages=gtk_box_new(GTK_ORIENTATION_HORIZONTAL,4);
  collections.previous_groups=collections_button(group_pages,"Previous groups",G_CALLBACK(collections_page),GINT_TO_POINTER(0));
  collections.next_groups=collections_button(group_pages,"Next groups",G_CALLBACK(collections_page),GINT_TO_POINTER(1));gtk_box_pack_start(GTK_BOX(left),group_pages,FALSE,FALSE,0);
  GtkWidget *actions=gtk_box_new(GTK_ORIENTATION_HORIZONTAL,4);
  collections_button(actions,"_New",G_CALLBACK(collections_prepare_group),GINT_TO_POINTER(3));
  collections.rename=collections_button(actions,"_Rename",G_CALLBACK(collections_prepare_group),GINT_TO_POINTER(0));
  collections.remove=collections_button(actions,"_Delete",G_CALLBACK(collections_prepare_group),GINT_TO_POINTER(1));
  collections.restore=collections_button(actions,"Re_store",G_CALLBACK(collections_prepare_group),GINT_TO_POINTER(2));
  gtk_box_pack_start(GTK_BOX(left),actions,FALSE,FALSE,0);
  collections.enter=collections_button(left,"_Enter shelf",G_CALLBACK(collections_enter),NULL);
  gtk_box_pack_start(GTK_BOX(right),members,FALSE,FALSE,0);collections.selected_label=gtk_label_new("Select a collection");
  gtk_box_pack_start(GTK_BOX(right),collections.selected_label,FALSE,FALSE,0);gtk_box_pack_start(GTK_BOX(right),collections_scroll(collections.members),TRUE,TRUE,0);
  GtkWidget *member_pages=gtk_box_new(GTK_ORIENTATION_HORIZONTAL,4);
  collections.previous_members=collections_button(member_pages,"Earlier books",G_CALLBACK(collections_page),GINT_TO_POINTER(2));
  collections.next_members=collections_button(member_pages,"Later books",G_CALLBACK(collections_page),GINT_TO_POINTER(3));gtk_box_pack_start(GTK_BOX(right),member_pages,FALSE,FALSE,0);
  collections.target_label=gtk_label_new(collections.target_title);gtk_label_set_ellipsize(GTK_LABEL(collections.target_label),PANGO_ELLIPSIZE_END);
  gtk_box_pack_start(GTK_BOX(right),collections.target_label,FALSE,FALSE,0);
  GtkWidget *joins=gtk_box_new(GTK_ORIENTATION_HORIZONTAL,4);
  collections.add=collections_button(joins,"_Add selected book",G_CALLBACK(collections_prepare_member),GINT_TO_POINTER(0));
  collections.detach=collections_button(joins,"Remove membersh_ip",G_CALLBACK(collections_prepare_member),GINT_TO_POINTER(1));
  collections.position=collections_button(joins,"_Position",G_CALLBACK(collections_prepare_member),GINT_TO_POINTER(2));
  gtk_box_pack_start(GTK_BOX(right),joins,FALSE,FALSE,0);
  gtk_box_pack_start(GTK_BOX(panes),left,TRUE,TRUE,0);gtk_box_pack_start(GTK_BOX(panes),right,TRUE,TRUE,0);gtk_box_pack_start(GTK_BOX(area),panes,TRUE,TRUE,4);
  collections.message=gtk_label_new("");gtk_label_set_line_wrap(GTK_LABEL(collections.message),TRUE);gtk_box_pack_start(GTK_BOX(area),collections.message,FALSE,FALSE,4);
  g_signal_connect(collections.types,"changed",G_CALLBACK(collections_changed),NULL);g_signal_connect(collections.removed,"toggled",G_CALLBACK(collections_changed),NULL);
  g_signal_connect(collections.groups,"row-selected",G_CALLBACK(collections_group_selected),NULL);g_signal_connect(collections.groups,"row-activated",G_CALLBACK(collections_group_activated),NULL);
  g_signal_connect(collections.members,"row-selected",G_CALLBACK(collections_member_selected),NULL);g_signal_connect(collections.members,"row-activated",G_CALLBACK(collections_member_activated),NULL);
  g_signal_connect(collections.dialog,"response",G_CALLBACK(collections_response),NULL);g_signal_connect(collections.dialog,"delete-event",G_CALLBACK(collections_delete),NULL);
  g_signal_connect(collections.dialog,"destroy",G_CALLBACK(collections_destroyed),NULL);g_signal_connect(collections.dialog,"key-press-event",G_CALLBACK(collections_keys),NULL);
  collections.applying=FALSE;gtk_widget_show_all(collections.dialog);collections_queue(READER_COLLECTIONS_LIST);
}
static char *collections_observation(void) {
  GKeyFile *file=g_key_file_new();g_key_file_set_integer(file,"collections","visible",collections.dialog && !collections.closing);
  g_key_file_set_integer(file,"collections","editor",collections.editor && !collections.editor_closing && !collections.closing);
  g_key_file_set_integer(file,"collections","recovery",collections.recovery && !collections.closing);
  g_key_file_set_integer(file,"collections","kind",collections.kind);g_key_file_set_integer(file,"collections","removed",collections.trash);
  GString *groups=g_string_new(NULL),*members=g_string_new(NULL),*ordinals=g_string_new(NULL);int counts[2]={0,0};
  GtkWidget *lists[]={collections.groups,collections.members};
  if(!collections.closing && !closing) for(int k=0;k<2;k++) if(lists[k]) {
    GList *rows=gtk_container_get_children(GTK_CONTAINER(lists[k]));
    for(GList *item=rows;item;item=item->next) {
      const char *key=g_object_get_data(G_OBJECT(item->data),k==0 ? "group-id":"member-key");
      GString *out=k==0 ? groups:members;if(counts[k]++) g_string_append_c(out,',');g_string_append(out,key ? key:"");
      if(k==1) { uint64_t *ordinal=g_object_get_data(G_OBJECT(item->data),"ordinal");if(counts[k]>1) g_string_append_c(ordinals,',');g_string_append_printf(ordinals,"%"G_GUINT64_FORMAT,ordinal ? *ordinal:0); }
    }
    g_list_free(rows);
  }
  g_key_file_set_integer(file,"collections","group_count",counts[0]);g_key_file_set_integer(file,"collections","member_count",counts[1]);
  g_key_file_set_string(file,"collections","group_ids",groups->str);g_key_file_set_string(file,"collections","member_keys",members->str);g_key_file_set_string(file,"collections","member_ordinals",ordinals->str);
  g_key_file_set_string(file,"collections","selected_id",collections.selected ? collections.selected:"");
  g_key_file_set_string(file,"collections","parent_id",collections.parent ? collections.parent:"");
  g_key_file_set_string(file,"collections","selected_name",collections.selected_name ? collections.selected_name:"");
  g_key_file_set_integer(file,"collections","selected_deleted",collections.selected_deleted);
  g_key_file_set_integer(file,"collections","dependency",collections.dependency);
  g_key_file_set_integer(file,"collections","editor_accept",collections.editor && !collections.closing && !closing &&
    gtk_widget_get_sensitive(gtk_dialog_get_widget_for_response(GTK_DIALOG(collections.editor),GTK_RESPONSE_ACCEPT)));
  g_key_file_set_string(file,"collections","editor_parent",collections.editor_parent ? collections.editor_parent:"");
  GtkWidget *buttons[]={collections.previous_groups,collections.next_groups,collections.previous_members,collections.next_members};
  const char *names[]={"group_before","group_after","member_before","member_after"};
  for(size_t i=0;i<G_N_ELEMENTS(buttons);i++) g_key_file_set_integer(file,"collections",names[i],!collections.closing && !closing && buttons[i] && gtk_widget_get_sensitive(buttons[i]));
  char *data=g_key_file_to_data(file,NULL,NULL);g_key_file_free(file);g_string_free(groups,TRUE);g_string_free(members,TRUE);g_string_free(ordinals,TRUE);return data;
}
