/* SPDX-License-Identifier: MIT */
/* Native widgets carry copied labels and indices; SDK work uses the old owner. */
#include <reader_navigation.h>
static void directory_progress(void *);
static struct {
  GtkWidget *dialog,*content,*return_focus,*list,*status,*open,*children,*back,*more,*cancel,*part_start,*cfi;
  gboolean running,has_owner,suppress_focus,candidate_mode,part_only;
  uint64_t token,parent,next,total,selected,pending_row,parents[64];unsigned depth,actions,closed;
  uint64_t *candidates;size_t candidate_count,candidate_first;
  int code,match,verified,kind;
  reader_navigation_control control;
} directory={.parent=READER_NAVIGATION_NONE,.next=READER_NAVIGATION_NONE,.selected=READER_NAVIGATION_NONE,.control={.changed=directory_progress}};
static gboolean directory_progress_idle(gpointer unused) { (void)unused;state();return G_SOURCE_REMOVE; }
static void directory_progress(void *unused) { (void)unused;g_idle_add(directory_progress_idle,NULL); }
static gboolean directory_opened(void) { return directory.dialog!=NULL; }
static void directory_message(const char *message) {
  if(directory.status) { gtk_label_set_text(GTK_LABEL(directory.status),message);atk_object_set_name(gtk_widget_get_accessible(directory.status),message); }
}
static void directory_controls(void) {
  if(!directory.dialog) return;
  gtk_widget_set_sensitive(directory.list,!directory.running);
  gtk_widget_set_sensitive(directory.open,!directory.running && directory.selected!=READER_NAVIGATION_NONE);
  gtk_widget_set_sensitive(directory.children,!directory.running && !directory.candidate_mode && directory.selected!=READER_NAVIGATION_NONE);
  gtk_widget_set_sensitive(directory.back,!directory.running && (directory.depth || directory.candidate_mode));
  gtk_widget_set_sensitive(directory.more,!directory.running && directory.next!=READER_NAVIGATION_NONE);
  gtk_widget_set_sensitive(directory.cancel,directory.running);
  gtk_widget_set_sensitive(directory.part_start,!directory.running && directory.part_only);
  gtk_widget_set_sensitive(directory.cfi,!directory.running);
}
static void directory_clear(void) {
  if(directory.list) { GList *rows=gtk_container_get_children(GTK_CONTAINER(directory.list));for(GList *p=rows;p;p=p->next) gtk_widget_destroy(p->data);g_list_free(rows); }
  directory.selected=READER_NAVIGATION_NONE;
}
static void directory_release(void) {
  if(directory.running) { g_atomic_int_inc(&generation);busy=FALSE;directory.running=FALSE; }
  if(directory.has_owner) {
    host_job *job=g_new0(host_job,1);job->generation=g_atomic_int_get(&generation);job->command.action=READER_NAVIGATION_CLOSE;
    job->command.navigation_token=directory.token;g_async_queue_push(queue,job);
  }
  directory.has_owner=FALSE;directory.token++;
}
static void directory_destroyed(GtkWidget *widget,gpointer unused) {
  (void)widget;(void)unused;directory.dialog=directory.list=directory.status=NULL;
  if(directory.content) gtk_widget_set_sensitive(directory.content,TRUE);
  directory.content=NULL;
  g_clear_pointer(&directory.candidates,g_free);directory.candidate_count=0;
  if(!closing && !directory.suppress_focus) {
    gtk_window_present(GTK_WINDOW(window));
    if(directory.return_focus && gtk_widget_get_toplevel(directory.return_focus)==window && gtk_widget_is_sensitive(directory.return_focus)) gtk_widget_grab_focus(directory.return_focus);
    else gtk_widget_grab_focus(text);
  }
  g_clear_object(&directory.return_focus);state();
}
static void directory_close(void) {
  directory_release();directory_clear();directory.closed++;if(directory.dialog) gtk_widget_destroy(directory.dialog);
}
static void directory_response(GtkDialog *dialog,int response,gpointer unused) { (void)dialog;(void)response;(void)unused;directory_close(); }
static gboolean directory_background(GtkWidget *widget,GdkEventWindowState *event,gpointer unused) {
  (void)widget;(void)unused;
  if(directory.dialog && (event->new_window_state&(GDK_WINDOW_STATE_ICONIFIED|GDK_WINDOW_STATE_WITHDRAWN))) {
    directory.suppress_focus=TRUE;directory_close();directory.suppress_focus=FALSE;
  }return FALSE;
}
static void directory_queue(reader_action action,uint64_t first,uint64_t explicit_part,gboolean part_start,const char *cfi) {
  if(!directory.dialog || directory.running || busy || saving || save_failed || !book_id) return;
  host_job *job=g_new0(host_job,1);job->generation=g_atomic_int_add(&generation,1)+1;
  job->command.action=action;job->command.book=book_id;job->command.part=part;job->command.page=page_number;
  job->command.navigation_token=directory.token;job->command.navigation_parent=directory.parent;job->command.navigation_first=first;
  job->command.navigation_row=directory.pending_row;job->command.navigation_explicit_part=explicit_part;job->command.navigation_accept_part=part_start;
  job->command.navigation_cfi=cfi ? g_strdup(cfi):NULL;
  g_atomic_int_set(&directory.control.request,job->generation);g_atomic_int_set(&directory.control.phase,0);g_atomic_int_set(&directory.control.polls,0);
  job->command.navigation_control=&directory.control;job->command.navigation_request=job->generation;
  directory.running=directory.has_owner=TRUE;directory.actions++;busy=TRUE;directory_controls();
  directory_message(action==READER_NAVIGATION_CHOOSE ? "Verifying directory target…":"Reading directory…");g_async_queue_push(queue,job);state();
}
static void directory_row(uint64_t index,const char *label,unsigned children,gboolean candidate) {
  GtkWidget *row=gtk_list_box_row_new();char *name=candidate ? g_strdup_printf("Spine item %"G_GUINT64_FORMAT,index+1):g_strdup_printf("Directory entry %"G_GUINT64_FORMAT": %s",index+1,label);
  GtkWidget *value=gtk_label_new(name);gtk_label_set_xalign(GTK_LABEL(value),0);gtk_label_set_line_wrap(GTK_LABEL(value),TRUE);
  gtk_container_add(GTK_CONTAINER(row),value);atk_object_set_name(gtk_widget_get_accessible(row),name);g_free(name);
  g_object_set_data(G_OBJECT(row),"navigation-index",GSIZE_TO_POINTER((size_t)index));g_object_set_data(G_OBJECT(row),"navigation-children",GUINT_TO_POINTER(children));
  gtk_container_add(GTK_CONTAINER(directory.list),row);
}
static void directory_candidates(void) {
  directory_clear();size_t end=MIN(directory.candidate_first+32,directory.candidate_count);
  for(size_t i=directory.candidate_first;i<end;i++) directory_row(directory.candidates[i],"",0,TRUE);
  directory.next=end<directory.candidate_count ? end:READER_NAVIGATION_NONE;gtk_widget_show_all(directory.list);directory_controls();state();
}
static void directory_selected(GtkListBox *list,GtkListBoxRow *row,gpointer unused) {
  (void)list;(void)unused;directory.selected=row ? GPOINTER_TO_SIZE(g_object_get_data(G_OBJECT(row),"navigation-index")):READER_NAVIGATION_NONE;
  directory_controls();if(directory.dialog && row) gtk_widget_set_sensitive(directory.children,!directory.running && !directory.candidate_mode && GPOINTER_TO_UINT(g_object_get_data(G_OBJECT(row),"navigation-children"))>0);state();
}
static void directory_choose(GtkWidget *widget,gpointer unused) {
  (void)widget;(void)unused;if(directory.selected==READER_NAVIGATION_NONE) return;
  uint64_t explicit_part=directory.candidate_mode ? directory.selected:READER_NAVIGATION_NONE;
  if(!directory.candidate_mode) directory.pending_row=directory.selected;
  directory_queue(READER_NAVIGATION_CHOOSE,0,explicit_part,FALSE,NULL);
}
static void directory_activate(GtkListBox *list,GtkListBoxRow *row,gpointer unused) {
  (void)list;(void)unused;
  if(row && gtk_widget_get_parent(GTK_WIDGET(row))==directory.list) { directory_selected(list,row,NULL);directory_choose(NULL,NULL); }
}
static void directory_child(GtkWidget *widget,gpointer unused) {
  (void)widget;(void)unused;if(directory.selected==READER_NAVIGATION_NONE || directory.depth>=64) return;
  directory.parents[directory.depth++]=directory.parent;directory.parent=directory.selected;directory.part_only=FALSE;
  directory_queue(READER_NAVIGATION_ROWS,0,READER_NAVIGATION_NONE,FALSE,NULL);
}
static void directory_back(GtkWidget *widget,gpointer unused) {
  (void)widget;(void)unused;
  if(directory.candidate_mode) { directory.candidate_mode=FALSE;g_clear_pointer(&directory.candidates,g_free);directory.candidate_count=0; }
  else if(directory.depth) directory.parent=directory.parents[--directory.depth];else return;
  directory.part_only=FALSE;directory_queue(READER_NAVIGATION_ROWS,0,READER_NAVIGATION_NONE,FALSE,NULL);
}
static void directory_more(GtkWidget *widget,gpointer unused) {
  (void)widget;(void)unused;if(directory.next==READER_NAVIGATION_NONE) return;
  if(directory.candidate_mode) { directory.candidate_first=(size_t)directory.next;directory_candidates(); }
  else directory_queue(READER_NAVIGATION_ROWS,directory.next,READER_NAVIGATION_NONE,FALSE,NULL);
}
static void directory_part_start(GtkWidget *widget,gpointer unused) {
  (void)widget;(void)unused;if(directory.part_only) directory_queue(READER_NAVIGATION_CHOOSE,0,directory.candidate_mode ? directory.selected:READER_NAVIGATION_NONE,TRUE,NULL);
}
static void directory_cfi(GtkEntry *entry,gpointer unused) {
  (void)unused;directory_queue(READER_NAVIGATION_CHOOSE,0,READER_NAVIGATION_NONE,FALSE,gtk_entry_get_text(entry));
}
static void directory_cancel(GtkWidget *widget,gpointer unused) {
  (void)widget;(void)unused;directory_release();directory_clear();directory.code=READER_NAVIGATION_CANCELLED;directory.next=READER_NAVIGATION_NONE;
  directory_controls();directory_message("Directory cancelled. Close and reopen to start again");state();
}
static void directory_open(GtkWidget *widget,gpointer unused) {
  (void)widget;(void)unused;if(closing || busy || saving || save_failed || !book_id || directory.dialog) return;
#ifdef EXR_READER_SEARCH_UI
  if(inbook_opened()) return;
#endif
#ifdef EXR_READER_PREFERENCES_UI
  if(preferences_opened()) return;
#endif
#ifdef EXR_READER_ACCOUNT
  if(accounts_opened()) return;
#endif
  GtkWidget *focus=gtk_window_get_focus(GTK_WINDOW(window));if(focus) directory.return_focus=g_object_ref(focus);
  directory.content=gtk_bin_get_child(GTK_BIN(window));gtk_widget_set_sensitive(directory.content,FALSE);
  directory.dialog=gtk_dialog_new_with_buttons("Directory and page entries",GTK_WINDOW(window),GTK_DIALOG_MODAL|GTK_DIALOG_DESTROY_WITH_PARENT,"_Close",GTK_RESPONSE_CLOSE,NULL);
  gtk_style_context_add_class(gtk_widget_get_style_context(directory.dialog),"exreader-appearance");
  GtkWindowGroup *group=gtk_window_group_new();gtk_window_group_add_window(group,GTK_WINDOW(directory.dialog));g_object_unref(group);
  GtkWidget *area=gtk_dialog_get_content_area(GTK_DIALOG(directory.dialog));gtk_container_set_border_width(GTK_CONTAINER(area),12);
  directory.status=gtk_label_new("");gtk_label_set_line_wrap(GTK_LABEL(directory.status),TRUE);gtk_box_pack_start(GTK_BOX(area),directory.status,FALSE,FALSE,4);
  directory.list=gtk_list_box_new();gtk_list_box_set_activate_on_single_click(GTK_LIST_BOX(directory.list),FALSE);atk_object_set_name(gtk_widget_get_accessible(directory.list),"Directory entries");
  GtkWidget *view=gtk_scrolled_window_new(NULL,NULL);gtk_widget_set_size_request(view,500,300);gtk_container_add(GTK_CONTAINER(view),directory.list);gtk_box_pack_start(GTK_BOX(area),view,TRUE,TRUE,4);
  GtkWidget *actions=gtk_box_new(GTK_ORIENTATION_HORIZONTAL,4);gtk_box_pack_start(GTK_BOX(area),actions,FALSE,FALSE,4);
  directory.open=gtk_button_new_with_mnemonic("_Open entry");directory.children=gtk_button_new_with_mnemonic("S_how children");directory.back=gtk_button_new_with_mnemonic("_Back");
  directory.more=gtk_button_new_with_mnemonic("_More entries");directory.cancel=gtk_button_new_with_mnemonic("Ca_ncel directory");directory.part_start=gtk_button_new_with_mnemonic("Open _part start");
  GtkWidget *buttons[]={directory.open,directory.children,directory.back,directory.more,directory.cancel,directory.part_start};
  for(size_t i=0;i<G_N_ELEMENTS(buttons);i++) gtk_box_pack_start(GTK_BOX(actions),buttons[i],FALSE,FALSE,0);
  directory.cfi=gtk_entry_new();gtk_entry_set_max_length(GTK_ENTRY(directory.cfi),4096);gtk_entry_set_placeholder_text(GTK_ENTRY(directory.cfi),"Full EPUB CFI · Enter verifies and opens");
  atk_object_set_name(gtk_widget_get_accessible(directory.cfi),"Full EPUB CFI");gtk_box_pack_start(GTK_BOX(area),directory.cfi,FALSE,FALSE,4);
  g_signal_connect(directory.open,"clicked",G_CALLBACK(directory_choose),NULL);g_signal_connect(directory.children,"clicked",G_CALLBACK(directory_child),NULL);
  g_signal_connect(directory.back,"clicked",G_CALLBACK(directory_back),NULL);g_signal_connect(directory.more,"clicked",G_CALLBACK(directory_more),NULL);
  g_signal_connect(directory.cancel,"clicked",G_CALLBACK(directory_cancel),NULL);g_signal_connect(directory.part_start,"clicked",G_CALLBACK(directory_part_start),NULL);
  g_signal_connect(directory.list,"row-selected",G_CALLBACK(directory_selected),NULL);g_signal_connect(directory.list,"row-activated",G_CALLBACK(directory_activate),NULL);
  g_signal_connect(directory.cfi,"activate",G_CALLBACK(directory_cfi),NULL);g_signal_connect(directory.dialog,"destroy",G_CALLBACK(directory_destroyed),NULL);
  g_signal_connect(directory.dialog,"response",G_CALLBACK(directory_response),NULL);g_signal_connect(directory.dialog,"window-state-event",G_CALLBACK(directory_background),NULL);
  directory.token++;directory.depth=0;directory.parent=directory.next=directory.selected=READER_NAVIGATION_NONE;directory.part_only=directory.candidate_mode=FALSE;
  directory.code=directory.match=directory.verified=0;gtk_widget_show_all(directory.dialog);gtk_widget_grab_focus(directory.list);
  directory_queue(READER_NAVIGATION_BEGIN,0,READER_NAVIGATION_NONE,FALSE,NULL);
}
static gboolean directory_apply(host_result *done) {
  reader_result *result=&done->value;if(done->action==READER_NAVIGATION_CLOSE) return TRUE;
  if(done->generation!=g_atomic_int_get(&generation) || !directory.dialog || result->navigation_token!=directory.token) return TRUE;
  directory.running=FALSE;directory.code=result->navigation_code;directory.match=result->navigation_match;directory.verified=result->navigation_verified;
  if(done->action==READER_NAVIGATION_CHOOSE && result->status==EXR_OK && result->has_frame && result->navigation_verified) {
    directory.has_owner=FALSE;gtk_widget_destroy(directory.dialog);return FALSE;
  }
  busy=FALSE;directory.part_only=directory.code==READER_NAVIGATION_PART_ONLY;
  if(done->action!=READER_NAVIGATION_CHOOSE && result->status==EXR_OK) {
    directory_clear();directory.parent=result->navigation_parent;directory.next=result->navigation_next;directory.total=result->navigation_total;directory.kind=result->navigation_kind;
    for(size_t i=0;i<result->navigation_count;i++) { reader_navigation_ui_row *row=&result->navigation_rows[i];directory_row(row->index,row->label,row->children,FALSE); }
    gtk_widget_show_all(directory.list);
  } else if(result->navigation_candidate_count) {
    g_free(directory.candidates);directory.candidates=result->navigation_candidates;result->navigation_candidates=NULL;
    directory.candidate_count=result->navigation_candidate_count;directory.candidate_first=0;directory.candidate_mode=TRUE;directory_candidates();
  }
  directory_message(result->message);directory_controls();state();return TRUE;
}
static char *directory_observation(void) {
  return g_strdup_printf("[directory]\nvisible=%d\nrunning=%d\ntoken=%"G_GUINT64_FORMAT"\nparent=%"G_GUINT64_FORMAT"\nnext=%"G_GUINT64_FORMAT"\ntotal=%"G_GUINT64_FORMAT"\ndepth=%u\ncode=%d\nmatch=%d\nverified=%d\nkind=%d\ncandidate_mode=%d\ncandidates=%zu\nactions=%u\nclosed=%u\nphase=%d\npolls=%d\n",
    directory.dialog!=NULL,directory.running,directory.token,directory.parent,directory.next,directory.total,directory.depth,directory.code,directory.match,directory.verified,directory.kind,
    directory.candidate_mode,directory.candidate_count,directory.actions,directory.closed,g_atomic_int_get(&directory.control.phase),g_atomic_int_get(&directory.control.polls));
}
