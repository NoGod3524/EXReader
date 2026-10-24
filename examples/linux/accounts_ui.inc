/* SPDX-License-Identifier: MIT */
/* GTK only controls the existing SDK owner and the native session's worker. */
static struct {
  GtkWidget *dialog,*form,*root,*user,*password,*remember,*session_only,*identity,*notice,*progress,*resume_focus;
  GtkWidget *load,*apply,*forget,*scan,*receive,*cancel,*retry,*disconnect;
  GtkWidget *spinner,*main_content,*return_focus;
  reader_session *session;reader_session_snapshot view;reader_account_control control;
  char *id,*bound_root,*receive_key,*conflict_cursor,*conflict_keys,*conflict_heads,*resolutions;
  guint timer,stage_idle;reader_action next_stage;
  gboolean owner_busy,preparing,want_start,close_wanted,exit_wanted,applying;
  int credential_status,bound,stage_status;
  int phase,projection_status,import_pending;
  gboolean want_open,open_after_load,close_for_import,import_retry;
  int64_t open_book,imported_book,restored_book;
  int imported_created,restore_failed;
  size_t restored_part,restored_position,conflict_rows;
  uint64_t projected,conflicted,waiting,receive_seen,receive_attempt;
  size_t receive_page_rows,max_receive_page_rows;
  size_t reading_rows,reading_found,reading_unresolved;
  int reading_more;
  uint64_t seen,prepared,existing,pending,failed,bootstraps,generation,closed_generation,ticks;
  size_t page_rows,max_page_rows;
} accounts;
enum {ACCOUNT_IDLE,ACCOUNT_PREPARE,ACCOUNT_PROJECT,ACCOUNT_IMPORT,ACCOUNT_CONFLICTS};
static void accounts_submit(reader_action,int);
static void accounts_finish_close(void);
static gboolean accounts_tick(gpointer);
static gboolean accounts_opened(void) { return accounts.dialog!=NULL; }
static void accounts_text(char **value,const char *text) { g_free(*value);*value=g_strdup(text ? text:""); }
static void accounts_notice(const char *text) {
  if(accounts.notice) gtk_label_set_text(GTK_LABEL(accounts.notice),text);
}
static void accounts_update_controls(void) {
  if(!accounts.dialog) return;
  gboolean edit=!accounts.owner_busy && !accounts.preparing && !accounts.session && !accounts.close_wanted;
  gtk_widget_set_sensitive(accounts.form,edit);gtk_widget_set_sensitive(accounts.load,edit);
  gtk_widget_set_sensitive(accounts.apply,edit);gtk_widget_set_sensitive(accounts.forget,edit);
  gtk_widget_set_sensitive(accounts.scan,!accounts.owner_busy && !accounts.preparing && !accounts.close_wanted &&
    (!accounts.session || accounts.view.state==READER_SESSION_FINISHED || accounts.view.state==READER_SESSION_FAILED ||
     accounts.view.state==READER_SESSION_CANCELLED));
  gtk_widget_set_sensitive(accounts.receive,!accounts.owner_busy && !accounts.preparing && !accounts.close_wanted &&
    accounts.session && accounts.view.state==READER_SESSION_FINISHED);
  gtk_widget_set_sensitive(accounts.cancel,!accounts.close_wanted && (accounts.preparing ||
    (accounts.session && (accounts.view.state==READER_SESSION_RUNNING || accounts.view.state==READER_SESSION_CANCELLING))));
  gtk_widget_set_sensitive(accounts.retry,!accounts.owner_busy && !accounts.preparing && !accounts.close_wanted &&
    ((accounts.session && (accounts.view.state==READER_SESSION_FAILED || accounts.view.state==READER_SESSION_CANCELLED)) ||
     accounts.projection_status || accounts.import_retry));
  gtk_button_set_label(GTK_BUTTON(accounts.scan),accounts.want_open ? "_Sync and open":"_Sync library");
  gtk_button_set_use_underline(GTK_BUTTON(accounts.scan),TRUE);
  gtk_widget_set_sensitive(accounts.disconnect,accounts.session && !accounts.close_wanted && accounts.view.state!=READER_SESSION_CLOSING);
  if(accounts.owner_busy || accounts.preparing || (accounts.session &&
     (accounts.view.state==READER_SESSION_RUNNING || accounts.view.state==READER_SESSION_CANCELLING || accounts.view.state==READER_SESSION_CLOSING)))
    gtk_spinner_start(GTK_SPINNER(accounts.spinner));
  else gtk_spinner_stop(GTK_SPINNER(accounts.spinner));
}
static void accounts_timer(void) {
  if(!accounts.timer) accounts.timer=g_timeout_add(150,accounts_tick,NULL);
}
static void accounts_destroyed(GtkWidget *widget,gpointer unused) {
  (void)widget;(void)unused;accounts.dialog=accounts.form=accounts.root=accounts.user=accounts.password=NULL;
  accounts.remember=accounts.session_only=accounts.identity=accounts.notice=accounts.progress=NULL;
  accounts.load=accounts.apply=accounts.forget=accounts.scan=accounts.receive=accounts.cancel=accounts.retry=accounts.disconnect=NULL;
  accounts.spinner=NULL;
  if(accounts.main_content) gtk_widget_set_sensitive(accounts.main_content,TRUE);
  accounts.main_content=NULL;
  if(!closing && !accounts.exit_wanted) {
    gtk_window_present(GTK_WINDOW(window));
    if(accounts.return_focus && gtk_widget_get_toplevel(accounts.return_focus)==window &&
       gtk_widget_get_visible(accounts.return_focus) && gtk_widget_is_sensitive(accounts.return_focus))
      gtk_widget_grab_focus(accounts.return_focus);
    else gtk_widget_grab_focus(search);
  }
  g_clear_object(&accounts.return_focus);
  g_clear_object(&accounts.resume_focus);accounts.close_wanted=FALSE;
  if(!closing && shelf_filter_pending) shelf_request(0,FALSE);
  state();
}
static void accounts_destroy_dialog(void) {
  if(!accounts.dialog) return;
  gtk_entry_set_text(GTK_ENTRY(accounts.user),"");gtk_entry_set_text(GTK_ENTRY(accounts.password),"");
  gtk_widget_destroy(accounts.dialog);
}
static void accounts_finish_close(void) {
  if(accounts.owner_busy || accounts.preparing || accounts.session) return;
  if(accounts.close_wanted || accounts.exit_wanted) accounts_destroy_dialog();
  if(accounts.exit_wanted && !closing) {
    accounts.exit_wanted=FALSE;close_window(window,NULL,NULL);
  } else if(accounts.open_book>0 && !closing) {
    int64_t id=accounts.open_book;accounts.open_book=0;open_id(id);
  }
}
static void accounts_close_requested(void) {
  accounts.close_wanted=TRUE;accounts.want_start=accounts.want_open=accounts.open_after_load=accounts.close_for_import=FALSE;
  g_atomic_int_set(&accounts.control.cancelled,1);
  if(accounts.session) reader_session_request_close(accounts.session);
  accounts_notice("Stopping safely. Saved books and changes will be kept");
  accounts_timer();accounts_update_controls();accounts_finish_close();state();
}
static gboolean accounts_delete(GtkWidget *widget,GdkEvent *event,gpointer unused) {
  (void)widget;(void)event;(void)unused;accounts_close_requested();return TRUE;
}
static void accounts_response(GtkDialog *dialog,int response,gpointer unused) {
  (void)dialog;(void)response;(void)unused;accounts_close_requested();
}
static gboolean accounts_defer_exit(void) {
  if(closing) return FALSE;
  if(!accounts.owner_busy && !accounts.preparing && !accounts.session) { accounts_destroy_dialog();return FALSE; }
  accounts.exit_wanted=TRUE;accounts_close_requested();return TRUE;
}
static gboolean accounts_stage_idle(gpointer unused) {
  (void)unused;accounts.stage_idle=0;
  if(accounts.phase==ACCOUNT_CONFLICTS && !accounts.dialog && g_atomic_int_get(&accounts.control.cancelled)) {
    accounts.preparing=FALSE;accounts.phase=ACCOUNT_IDLE;accounts_finish_close();state();return G_SOURCE_REMOVE;
  }
  if(accounts.preparing && !accounts.owner_busy && (busy || saving || save_failed)) {
    accounts.stage_idle=g_timeout_add(25,accounts_stage_idle,NULL);return G_SOURCE_REMOVE;
  }
  if(accounts.preparing && !accounts.owner_busy) accounts_submit(accounts.next_stage,0);
  return G_SOURCE_REMOVE;
}
static void accounts_stage_next(reader_action action) {
  accounts.next_stage=action;
  if(!accounts.stage_idle) accounts.stage_idle=g_idle_add(accounts_stage_idle,NULL);
}
static void accounts_start_network(void) {
  if(!accounts.dialog || accounts.close_wanted || accounts.exit_wanted || g_atomic_int_get(&accounts.control.cancelled)) {
    accounts_finish_close();return;
  }
  const char *user=gtk_entry_get_text(GTK_ENTRY(accounts.user)),*password=gtk_entry_get_text(GTK_ENTRY(accounts.password));
  char *pair=g_strconcat(user,":",password,NULL),*encoded=g_base64_encode((const guchar *)pair,strlen(pair));
  char *authorization=g_strconcat("Basic ",encoded,NULL);reader_secret_free(pair);reader_secret_free(encoded);
  char *product=g_build_filename(home,"library.sqlite.product.sqlite",NULL),*work=g_build_filename(home,"sync-work",NULL);
  char *originals=g_build_filename(home,"sync-originals",NULL);reader_session_config config={0};
  config.product_path=product;config.private_directory=work;config.original_directory=originals;config.account_id=accounts.id;
  config.dav.root_url=accounts.bound_root;config.dav.authorization=authorization;
  reader_session_status code=reader_session_create(&config,&accounts.session);
  reader_secret_free(authorization);g_free(product);g_free(work);g_free(originals);
  if(code==READER_SESSION_OK) { accounts.generation++;code=reader_session_start(accounts.session); }
  if(accounts.session) reader_session_observe(accounts.session,&accounts.view);
  accounts.phase=ACCOUNT_IDLE;
  if(code!=READER_SESSION_OK) accounts_notice("Sync could not start. Your saved library was kept");
  else accounts_notice("Syncing your library and checking book files");
  accounts_timer();accounts_update_controls();state();
}
static void accounts_submit(reader_action action,int saved_only) {
  gboolean background=action==READER_RECEIVE_CONFLICTS_BEGIN || action==READER_RECEIVE_CONFLICTS_NEXT;
  if((!accounts.dialog && !background) || accounts.owner_busy || busy || saving || save_failed || closing) return;
  host_job *job=g_new0(host_job,1);job->generation=g_atomic_int_get(&generation);job->shelf_generation=g_atomic_int_get(&shelf_generation);
  job->command.action=action;job->command.account_id=g_strdup(accounts.id ? accounts.id:"");
  job->command.account_root=g_strdup(accounts.dialog ? gtk_entry_get_text(GTK_ENTRY(accounts.root)):
    (accounts.bound_root ? accounts.bound_root:""));job->command.account_saved_only=saved_only;
  job->command.account_control=&accounts.control;
  if(action==READER_RECEIVE_OPEN) job->command.receive_key=g_strdup(accounts.receive_key);
  if(action==READER_RECEIVE_OPEN) accounts.receive_attempt++;
  if(action==READER_RECEIVE_CONFLICTS_BEGIN) job->command.receive_key=g_strdup(accounts.conflict_cursor);
  if(action==READER_ACCOUNT_SET) {
    job->command.account_user=g_strdup(gtk_entry_get_text(GTK_ENTRY(accounts.user)));
    job->command.account_password=g_strdup(gtk_entry_get_text(GTK_ENTRY(accounts.password)));
    job->command.account_remember=gtk_toggle_button_get_active(GTK_TOGGLE_BUTTON(accounts.remember));
  }
  g_clear_object(&accounts.resume_focus);GtkWidget *focus=accounts.dialog ? gtk_window_get_focus(GTK_WINDOW(accounts.dialog)):NULL;
  if(focus) accounts.resume_focus=g_object_ref(focus);
  accounts.owner_busy=busy=TRUE;accounts_update_controls();g_async_queue_push(queue,job);accounts_timer();state();
}
static void accounts_credentials(GtkWidget *button,gpointer value) {
  (void)button;if(accounts.owner_busy || accounts.preparing || accounts.session) return;
  reader_action action=(reader_action)GPOINTER_TO_INT(value);accounts.want_start=FALSE;
  accounts_submit(action,action==READER_ACCOUNT_LOAD);
}
static void accounts_scan(GtkWidget *button,gpointer unused) {
  (void)button;(void)unused;
  if(accounts.owner_busy || accounts.preparing || accounts.close_wanted) return;
  accounts.want_start=TRUE;g_atomic_int_set(&accounts.control.cancelled,0);accounts.stage_status=0;
  if(accounts.session) {
    reader_session_request_close(accounts.session);accounts_notice("Closing the previous connection before preparing a new library scan");
    accounts_timer();accounts_update_controls();return;
  }
  accounts.preparing=TRUE;accounts.phase=ACCOUNT_PREPARE;accounts.projection_status=0;accounts_submit(READER_ACCOUNT_SET,0);
}
static void accounts_cancel(GtkWidget *button,gpointer unused) {
  (void)button;(void)unused;accounts.want_start=accounts.want_open=accounts.open_after_load=FALSE;g_atomic_int_set(&accounts.control.cancelled,1);
  if(accounts.session) reader_session_cancel(accounts.session);
  if(accounts.preparing) accounts_notice("Stopping. Saved books and changes will be kept");
  accounts_update_controls();state();
}
static void accounts_receive(GtkWidget *button,gpointer unused) {
  (void)button;(void)unused;
  if(!accounts.dialog || accounts.owner_busy || accounts.preparing || accounts.close_wanted ||
     !accounts.session || accounts.view.state!=READER_SESSION_FINISHED) return;
  g_atomic_int_set(&accounts.control.cancelled,0);accounts.preparing=TRUE;accounts.phase=ACCOUNT_PROJECT;accounts.projection_status=0;
  accounts_notice("Adding received books to your shelf");accounts_stage_next(READER_RECEIVE_BEGIN);
  accounts_update_controls();state();
}
static void accounts_retry(GtkWidget *button,gpointer unused) {
  (void)button;(void)unused;if(accounts.close_wanted) return;
  if(accounts.import_retry && !accounts.session) {
    g_atomic_int_set(&accounts.control.cancelled,0);accounts.preparing=accounts.want_open=TRUE;
    accounts.phase=ACCOUNT_IMPORT;accounts_stage_next(READER_RECEIVE_OPEN);accounts_update_controls();return;
  }
  if(accounts.projection_status && (!accounts.session || accounts.view.state==READER_SESSION_FINISHED)) {
    g_atomic_int_set(&accounts.control.cancelled,0);accounts.preparing=TRUE;accounts.phase=ACCOUNT_PROJECT;accounts.projection_status=0;
    accounts_stage_next(READER_RECEIVE_BEGIN);accounts_update_controls();return;
  }
  if(!accounts.session) return;
  reader_session_status code=reader_session_start(accounts.session);
  if(code==READER_SESSION_OK) {
    g_atomic_int_set(&accounts.control.cancelled,0);
    accounts_notice("Retrying sync. Saved changes will be kept");
  }
  reader_session_observe(accounts.session,&accounts.view);accounts_update_controls();state();
}
static void accounts_disconnect(GtkWidget *button,gpointer unused) {
  (void)button;(void)unused;if(!accounts.session) return;
  accounts.want_start=FALSE;reader_session_request_close(accounts.session);
  accounts_notice("Disconnecting safely");accounts_timer();accounts_update_controls();state();
}
static void accounts_present_conflicts(reader_result *result) {
  rows_clear(received_list);accounts.conflict_rows=result->receive_conflict_count;
  g_clear_pointer(&accounts.conflict_cursor,g_free);
  GString *keys=g_string_new(NULL),*heads=g_string_new(NULL);
  for(size_t i=0;i<result->receive_conflict_count;i++) {
    reader_received_conflict *entry=&result->receive_conflicts[i];
    GtkWidget *row=gtk_list_box_row_new();char *caption=g_strdup_printf("%s\n%s (%zu versions)",entry->title,
      entry->kind==READER_SELECTION_CONCURRENT ? "Version conflict":"Version details need attention",entry->head_count);
    GtkWidget *title=gtk_label_new(caption);g_free(caption);gtk_label_set_xalign(GTK_LABEL(title),0);
    gtk_label_set_ellipsize(GTK_LABEL(title),PANGO_ELLIPSIZE_END);gtk_container_add(GTK_CONTAINER(row),title);
    g_object_set_data_full(G_OBJECT(row),"book-key",g_strdup(entry->key),g_free);
    g_object_set_data_full(G_OBJECT(row),"received-heads",g_strdup(entry->heads),g_free);
    gtk_container_add(GTK_CONTAINER(received_list),row);
    if(i) { g_string_append_c(keys,',');g_string_append_c(heads,'|'); }
    g_string_append(keys,entry->key);g_string_append(heads,entry->heads);
    accounts_text(&accounts.conflict_cursor,entry->key);
  }
  g_free(accounts.conflict_keys);g_free(accounts.conflict_heads);
  accounts.conflict_keys=g_string_free(keys,FALSE);accounts.conflict_heads=g_string_free(heads,FALSE);
  gtk_widget_show_all(received_list);gtk_widget_set_visible(received_panel,result->receive_conflict_count>0 || result->receive_conflict_more);
  gtk_widget_set_sensitive(received_next,result->receive_conflict_more);
}
static void accounts_conflict_activated(GtkListBox *box,GtkListBoxRow *row,gpointer unused) {
  (void)box;(void)unused;
  const char *key=g_object_get_data(G_OBJECT(row),"book-key");if(key) accounts_text(&accounts.receive_key,key);
  GtkWidget *notice=gtk_message_dialog_new(GTK_WINDOW(window),GTK_DIALOG_DESTROY_WITH_PARENT,GTK_MESSAGE_INFO,GTK_BUTTONS_CLOSE,
    "%s","This book has unresolved versions. Sync or review the versions before opening it.");
  gtk_window_set_title(GTK_WINDOW(notice),"Book versions");
  g_signal_connect_swapped(notice,"response",G_CALLBACK(gtk_widget_destroy),notice);gtk_widget_show_all(notice);state();
}
static void accounts_conflicts_page(GtkWidget *button,gpointer value) {
  (void)button;
  if(closing || accounts.dialog || accounts.owner_busy || accounts.preparing || busy || saving || save_failed) return;
  if(!GPOINTER_TO_INT(value)) g_clear_pointer(&accounts.conflict_cursor,g_free);
  accounts.phase=ACCOUNT_CONFLICTS;accounts.preparing=TRUE;g_atomic_int_set(&accounts.control.cancelled,0);
  status(EXR_OK,"Checking book versions");accounts_submit(READER_RECEIVE_CONFLICTS_BEGIN,0);
}
static void accounts_received_apply(reader_result *result) {
  accounts.receive_page_rows=result->receive_page_rows;
  accounts.max_receive_page_rows=MAX(accounts.max_receive_page_rows,result->receive_page_rows);
  if(result->receive_response==5 || result->receive_response==7) {
    if(result->receive_response==5) {
      accounts.receive_seen=result->receive_seen;accounts.projected=result->receive_projected;
      accounts.conflicted=result->receive_conflicted;accounts.waiting=result->receive_waiting;
    }
    if(result->status==EXR_OK && result->receive_more) {
      accounts_stage_next(result->receive_response==5 ? READER_RECEIVE_NEXT:READER_RECEIVE_CONFLICTS_NEXT);
    } else {
      accounts.preparing=FALSE;accounts.phase=ACCOUNT_IDLE;
      if(result->receive_response==5) accounts.projection_status=(int)result->status;
      if(result->status==EXR_OK) {
        accounts_present_conflicts(result);if(result->receive_response==5) shelf_filter_pending=TRUE;
        accounts_notice(accounts.conflicted ? "Sync finished. Some books have version conflicts; open the others to add them to this device":
          "Sync finished. Open a book to add it to this device's reading library");
        if(accounts.want_open && accounts.dialog && !accounts.close_wanted && !accounts.exit_wanted) {
          accounts.close_for_import=accounts.preparing=TRUE;accounts.phase=ACCOUNT_IMPORT;
          if(accounts.session) reader_session_request_close(accounts.session);
          else { accounts.close_for_import=FALSE;accounts_stage_next(READER_RECEIVE_OPEN); }
        }
      } else {
        accounts_notice(result->message);
        if(!accounts.dialog && !accounts.exit_wanted) status(result->status,result->message);
      }
    }
  } else if(result->receive_response==6) {
    accounts.preparing=FALSE;accounts.phase=ACCOUNT_IDLE;accounts.import_pending=result->receive_pending;
    accounts.imported_book=result->receive_book;accounts.imported_created=result->receive_created;
    accounts.restored_book=result->receive_restored_book;accounts.restored_part=result->receive_restored_part;
    accounts.restored_position=result->receive_restored_position;accounts.restore_failed=result->receive_restore_failed;
    accounts.reading_rows=result->receive_reading_rows;accounts.reading_found=result->receive_reading_found;
    accounts.reading_unresolved=result->receive_reading_unresolved;accounts.reading_more=result->receive_reading_more;
    accounts_text(&accounts.resolutions,result->receive_resolutions);
    accounts.import_retry=result->receive_pending || (result->status!=EXR_OK && result->status!=EXR_ARGUMENT);
    if(accounts.close_wanted || accounts.exit_wanted || g_atomic_int_get(&accounts.control.cancelled)) {
      accounts.want_open=FALSE;accounts_notice(result->receive_book>0 ? "The saved book was kept":"Opening stopped. Your library was kept");
    } else if(result->status==EXR_OK && result->receive_needs_download) {
      if(accounts.credential_status==EXR_CRED_OK && gtk_entry_get_text(GTK_ENTRY(accounts.password))[0]) accounts_scan(NULL,NULL);
      else accounts_notice("This book needs its file. Enter the server login, then choose Sync and open");
    } else if(result->status==EXR_OK && result->receive_book>0) {
      accounts.import_retry=FALSE;shelf_filter_pending=TRUE;
      if(accounts.want_open) { accounts.open_book=result->receive_book;accounts.want_open=FALSE;accounts.close_wanted=TRUE; }
      accounts_notice("Book added to this device's reading library");
    } else {
      if(result->status==EXR_ARGUMENT) accounts.want_open=FALSE;
      accounts_notice(result->message);
    }
  }
  accounts_update_controls();accounts_finish_close();state();
}
static void accounts_apply(host_result *done) {
  reader_result *result=&done->value;accounts.owner_busy=busy=FALSE;
  if(result->receive_response) { accounts_received_apply(result);return; }
  accounts.credential_status=result->account_credential_status;accounts.bound=result->account_bound;
  if(result->account_id) accounts_text(&accounts.id,result->account_id);
  if(result->account_root) accounts_text(&accounts.bound_root,result->account_root);
  accounts.seen=result->account_seen;accounts.prepared=result->account_prepared;accounts.existing=result->account_existing;
  accounts.pending=result->account_pending;accounts.failed=result->account_failed;accounts.bootstraps=result->account_bootstraps;
  accounts.page_rows=result->account_page_rows;if(accounts.page_rows>accounts.max_page_rows) accounts.max_page_rows=accounts.page_rows;
  if(!accounts.dialog) { accounts.preparing=accounts.want_start=FALSE;accounts_finish_close();state();return; }
  accounts_update_controls();
  if(accounts.resume_focus && gtk_widget_get_toplevel(accounts.resume_focus)==accounts.dialog) gtk_widget_grab_focus(accounts.resume_focus);
  g_clear_object(&accounts.resume_focus);
  gtk_label_set_text(GTK_LABEL(accounts.identity),accounts.bound ? "This library uses the server folder below":"Choose the server folder for this library");
  if(result->account_response==1) {
    gtk_entry_set_text(GTK_ENTRY(accounts.root),accounts.bound_root ? accounts.bound_root:"");
    gtk_entry_set_text(GTK_ENTRY(accounts.user),result->account_user ? result->account_user:"");
    gtk_entry_set_text(GTK_ENTRY(accounts.password),result->account_password ? result->account_password:"");
    gtk_toggle_button_set_active(GTK_TOGGLE_BUTTON(result->account_remember ? accounts.remember:accounts.session_only),TRUE);
    if(accounts.open_after_load && !accounts.close_wanted && !accounts.exit_wanted) {
      accounts.open_after_load=FALSE;accounts.preparing=TRUE;accounts.phase=ACCOUNT_IMPORT;
      accounts_notice("Checking this book's file");accounts_stage_next(READER_RECEIVE_OPEN);
    }
  } else if(result->account_response==3) {
    gtk_entry_set_text(GTK_ENTRY(accounts.user),"");gtk_entry_set_text(GTK_ENTRY(accounts.password),"");
    gtk_toggle_button_set_active(GTK_TOGGLE_BUTTON(accounts.session_only),TRUE);
  }
  if(result->message[0]) accounts_notice(result->message);
  else if(result->status!=EXR_OK) accounts_notice("The account operation could not finish; saved library data was retained");
  if(result->account_response==2) {
    if(!accounts.want_start || result->status!=EXR_OK || result->account_credential_status!=EXR_CRED_OK || g_atomic_int_get(&accounts.control.cancelled) ||
       accounts.close_wanted || accounts.exit_wanted) accounts.preparing=accounts.want_start=FALSE;
    else accounts_stage_next(READER_ACCOUNT_STAGE_BEGIN);
  } else if(result->account_response==4) {
    if(result->status!=EXR_OK) { accounts.preparing=accounts.want_start=FALSE;accounts.stage_status=(int)result->status; }
    else if(result->account_more) accounts_stage_next(READER_ACCOUNT_STAGE_NEXT);
    else {
      accounts.preparing=FALSE;
      if(accounts.want_start) { accounts.want_start=FALSE;accounts_start_network(); }
    }
  } else if(result->status!=EXR_OK) accounts.preparing=accounts.want_start=FALSE;
  accounts_update_controls();accounts_finish_close();state();
}
static gboolean accounts_tick(gpointer unused) {
  (void)unused;accounts.ticks++;
  if(accounts.session) {
    reader_session_snapshot previous=accounts.view;reader_session_observe(accounts.session,&accounts.view);
    if(accounts.view.state!=previous.state) {
      if(accounts.view.state==READER_SESSION_FINISHED && accounts.want_open && !accounts.close_wanted && !accounts.exit_wanted && !accounts.preparing) {
        accounts.preparing=TRUE;accounts.phase=ACCOUNT_PROJECT;accounts.projection_status=0;
        accounts_notice("Updating your shelf");accounts_stage_next(READER_RECEIVE_BEGIN);
      }
      else if(accounts.view.state==READER_SESSION_FINISHED)
        accounts_notice("Sync finished. This does not mean those books are readable yet; choose Receive books to add them to your shelf");
      else if(accounts.view.state==READER_SESSION_CANCELLED)
        accounts_notice("Sync stopped. Retry to continue");
      else if(accounts.view.state==READER_SESSION_FAILED)
        accounts_notice(accounts.view.status==READER_SESSION_ACCOUNT ?
          "This library uses a different server folder or account":
          accounts.view.error.dav_code==EXR_DAV_AUTH ? "Login failed. Disconnect to edit the server login":
          "Sync failed. Retry to continue");
    }
    if(accounts.view.state==READER_SESSION_CLOSED) {
      if(reader_session_destroy(&accounts.session)==READER_SESSION_OK) accounts.closed_generation=accounts.generation;
      if(!accounts.session && accounts.close_for_import) {
        accounts.close_for_import=FALSE;
        if(accounts.want_open && !accounts.close_wanted && !accounts.exit_wanted && !g_atomic_int_get(&accounts.control.cancelled)) {
          accounts.preparing=TRUE;accounts.phase=ACCOUNT_IMPORT;accounts_stage_next(READER_RECEIVE_OPEN);
        } else { accounts.preparing=FALSE;accounts.phase=ACCOUNT_IDLE; }
      } else if(!accounts.session && accounts.want_start && !accounts.close_wanted && !accounts.exit_wanted) {
        accounts.preparing=TRUE;accounts.phase=ACCOUNT_PREPARE;accounts_submit(READER_ACCOUNT_SET,0);
      }
    }
  }
  if(accounts.progress) {
    char *text;
    if(accounts.preparing) text=g_strdup(accounts.phase==ACCOUNT_PROJECT ? "Updating your shelf…":
      accounts.phase==ACCOUNT_IMPORT ? "Adding book…":accounts.phase==ACCOUNT_CONFLICTS ? "Checking book versions…":"Preparing books…");
    else if(accounts.session && accounts.view.state==READER_SESSION_RUNNING) text=g_strdup("Downloading and checking book files…");
    else text=g_strdup("Sync downloads and verifies book files");
    gtk_label_set_text(GTK_LABEL(accounts.progress),text);g_free(text);
  }
  accounts_update_controls();accounts_finish_close();state();
  if(!accounts.dialog && !accounts.session && !accounts.owner_busy && !accounts.preparing) { accounts.timer=0;return G_SOURCE_REMOVE; }
  return G_SOURCE_CONTINUE;
}
static GtkWidget *accounts_button(GtkWidget *box,const char *text,GCallback callback,gpointer value) {
  GtkWidget *button=gtk_button_new_with_mnemonic(text);gtk_box_pack_start(GTK_BOX(box),button,FALSE,FALSE,0);
  g_signal_connect(button,"clicked",callback,value);return button;
}
static GtkWidget *accounts_entry(GtkWidget *grid,int row,const char *caption,const char *access) {
  GtkWidget *label=gtk_label_new_with_mnemonic(caption),*entry=gtk_entry_new();gtk_label_set_xalign(GTK_LABEL(label),0);
  gtk_label_set_mnemonic_widget(GTK_LABEL(label),entry);gtk_grid_attach(GTK_GRID(grid),label,0,row,1,1);gtk_grid_attach(GTK_GRID(grid),entry,1,row,1,1);
  atk_object_set_name(gtk_widget_get_accessible(entry),access);gtk_widget_set_hexpand(entry,TRUE);return entry;
}
static void accounts_open(GtkWidget *button,gpointer unused) {
  (void)button;(void)unused;
  if(closing || busy || saving || save_failed || metadata_running || metadata_dialog || collections_opened() || accounts.dialog ||
     accounts.preparing || accounts.owner_busy || !profile_writable) return;
  accounts.close_wanted=accounts.want_start=accounts.preparing=FALSE;g_atomic_int_set(&accounts.control.cancelled,0);
  GtkWidget *focus=gtk_window_get_focus(GTK_WINDOW(window));
  g_clear_object(&accounts.return_focus);if(focus) accounts.return_focus=g_object_ref(focus);
  /* The parent WM close event still retires preparation/session state. */
  accounts.main_content=gtk_bin_get_child(GTK_BIN(window));gtk_widget_set_sensitive(accounts.main_content,FALSE);
  accounts.dialog=gtk_dialog_new_with_buttons("Account and Sync",GTK_WINDOW(window),GTK_DIALOG_MODAL|GTK_DIALOG_DESTROY_WITH_PARENT,"_Back",GTK_RESPONSE_CLOSE,NULL);
  gtk_window_set_default_size(GTK_WINDOW(accounts.dialog),760,480);
  GtkWidget *area=gtk_dialog_get_content_area(GTK_DIALOG(accounts.dialog));gtk_container_set_border_width(GTK_CONTAINER(area),16);
  accounts.identity=gtk_label_new("Loading this library's account");gtk_label_set_xalign(GTK_LABEL(accounts.identity),0);
  gtk_box_pack_start(GTK_BOX(area),accounts.identity,FALSE,FALSE,6);
  accounts.form=gtk_grid_new();gtk_grid_set_row_spacing(GTK_GRID(accounts.form),9);gtk_grid_set_column_spacing(GTK_GRID(accounts.form),12);
  accounts.root=accounts_entry(accounts.form,0,"_WebDAV root","HTTPS WebDAV root");gtk_entry_set_max_length(GTK_ENTRY(accounts.root),8192);
  gtk_entry_set_placeholder_text(GTK_ENTRY(accounts.root),"https://server.example/books/");
  accounts.user=accounts_entry(accounts.form,1,"_Username","WebDAV username");gtk_entry_set_max_length(GTK_ENTRY(accounts.user),512);
  accounts.password=accounts_entry(accounts.form,2,"_Password","WebDAV password");
  gtk_entry_set_max_length(GTK_ENTRY(accounts.password),512);gtk_entry_set_visibility(GTK_ENTRY(accounts.password),FALSE);
  gtk_entry_set_input_purpose(GTK_ENTRY(accounts.password),GTK_INPUT_PURPOSE_PASSWORD);
  gtk_entry_set_input_hints(GTK_ENTRY(accounts.password),GTK_INPUT_HINT_NO_SPELLCHECK);
  accounts.remember=gtk_radio_button_new_with_mnemonic(NULL,"Re_member in system secure storage");
  accounts.session_only=gtk_radio_button_new_with_mnemonic_from_widget(GTK_RADIO_BUTTON(accounts.remember),"Only for t_his app session");
  gtk_toggle_button_set_active(GTK_TOGGLE_BUTTON(accounts.session_only),TRUE);
  gtk_grid_attach(GTK_GRID(accounts.form),accounts.remember,1,3,1,1);gtk_grid_attach(GTK_GRID(accounts.form),accounts.session_only,1,4,1,1);
  gtk_box_pack_start(GTK_BOX(area),accounts.form,FALSE,FALSE,4);
  GtkWidget *credentials=gtk_box_new(GTK_ORIENTATION_HORIZONTAL,7);
  accounts.load=accounts_button(credentials,"_Load saved",G_CALLBACK(accounts_credentials),GINT_TO_POINTER(READER_ACCOUNT_LOAD));
  accounts.apply=accounts_button(credentials,"_Apply credentials",G_CALLBACK(accounts_credentials),GINT_TO_POINTER(READER_ACCOUNT_SET));
  accounts.forget=accounts_button(credentials,"_Forget credentials",G_CALLBACK(accounts_credentials),GINT_TO_POINTER(READER_ACCOUNT_DELETE));
  gtk_box_pack_start(GTK_BOX(area),credentials,FALSE,FALSE,7);
  GtkWidget *operations=gtk_box_new(GTK_ORIENTATION_HORIZONTAL,7);
  accounts.scan=accounts_button(operations,"_Sync library",G_CALLBACK(accounts_scan),NULL);
  accounts.receive=accounts_button(operations,"_Receive books",G_CALLBACK(accounts_receive),NULL);
  accounts.cancel=accounts_button(operations,"_Cancel",G_CALLBACK(accounts_cancel),NULL);
  accounts.retry=accounts_button(operations,"Re_try",G_CALLBACK(accounts_retry),NULL);
  accounts.disconnect=accounts_button(operations,"_Disconnect",G_CALLBACK(accounts_disconnect),NULL);
  gtk_box_pack_start(GTK_BOX(area),operations,FALSE,FALSE,7);
  accounts.spinner=gtk_spinner_new();gtk_box_pack_start(GTK_BOX(area),accounts.spinner,FALSE,FALSE,4);
  accounts.notice=gtk_label_new("");accounts.progress=gtk_label_new("");
  gtk_label_set_line_wrap(GTK_LABEL(accounts.notice),TRUE);gtk_label_set_line_wrap(GTK_LABEL(accounts.progress),TRUE);
  gtk_label_set_xalign(GTK_LABEL(accounts.notice),0);gtk_label_set_xalign(GTK_LABEL(accounts.progress),0);
  gtk_box_pack_start(GTK_BOX(area),accounts.notice,FALSE,FALSE,7);gtk_box_pack_start(GTK_BOX(area),accounts.progress,FALSE,FALSE,7);
  g_signal_connect(accounts.dialog,"response",G_CALLBACK(accounts_response),NULL);
  g_signal_connect(accounts.dialog,"delete-event",G_CALLBACK(accounts_delete),NULL);
  g_signal_connect(accounts.dialog,"destroy",G_CALLBACK(accounts_destroyed),NULL);
  gtk_widget_show_all(accounts.dialog);gtk_widget_grab_focus(accounts.root);accounts_submit(READER_ACCOUNT_LOAD,0);
}
static void accounts_open_book(const char *key) {
  if(closing || busy || saving || save_failed || metadata_running || metadata_dialog || collections_opened() ||
     accounts.dialog || accounts.preparing || accounts.owner_busy || !profile_writable) return;
  accounts_text(&accounts.receive_key,key);accounts.want_open=accounts.open_after_load=TRUE;
  accounts.import_retry=FALSE;accounts.import_pending=0;accounts.open_book=0;accounts_open(NULL,NULL);
  if(!accounts.dialog) accounts.want_open=accounts.open_after_load=FALSE;
}
static char *accounts_observation(void) {
  GKeyFile *file=g_key_file_new();const char *group="account";
  g_key_file_set_integer(file,group,"visible",accounts.dialog!=NULL);g_key_file_set_integer(file,group,"owner_busy",accounts.owner_busy);
  g_key_file_set_integer(file,group,"preparing",accounts.preparing);g_key_file_set_integer(file,group,"credential_status",accounts.credential_status);
  g_key_file_set_integer(file,group,"bound",accounts.bound);g_key_file_set_integer(file,group,"closing",accounts.close_wanted);
  g_key_file_set_integer(file,group,"stage_status",accounts.stage_status);g_key_file_set_integer(file,group,"session_present",accounts.session!=NULL);
  g_key_file_set_integer(file,group,"cancel_requested",g_atomic_int_get(&accounts.control.cancelled));
  g_key_file_set_integer(file,group,"session_state",accounts.view.state);g_key_file_set_integer(file,group,"session_status",accounts.view.status);
  g_key_file_set_uint64(file,group,"session_generation",accounts.generation);g_key_file_set_uint64(file,group,"closed_generation",accounts.closed_generation);
  g_key_file_set_uint64(file,group,"ticks",accounts.ticks);g_key_file_set_uint64(file,group,"attempt",accounts.view.attempt);
  g_key_file_set_uint64(file,group,"seen",accounts.seen);g_key_file_set_uint64(file,group,"prepared",accounts.prepared);
  g_key_file_set_uint64(file,group,"existing",accounts.existing);g_key_file_set_uint64(file,group,"pending",accounts.pending);
  g_key_file_set_uint64(file,group,"failed",accounts.failed);g_key_file_set_uint64(file,group,"bootstraps",accounts.bootstraps);
  g_key_file_set_uint64(file,group,"page_rows",accounts.page_rows);g_key_file_set_uint64(file,group,"max_page_rows",accounts.max_page_rows);
  g_key_file_set_integer(file,group,"phase",accounts.phase);g_key_file_set_integer(file,group,"projection_status",accounts.projection_status);
  g_key_file_set_integer(file,group,"import_pending",accounts.import_pending);g_key_file_set_integer(file,group,"import_created",accounts.imported_created);
  g_key_file_set_int64(file,group,"imported_book",accounts.imported_book);g_key_file_set_int64(file,group,"restored_book",accounts.restored_book);
  g_key_file_set_uint64(file,group,"restored_part",accounts.restored_part);g_key_file_set_uint64(file,group,"restored_position",accounts.restored_position);
  g_key_file_set_integer(file,group,"restore_failed",accounts.restore_failed);
  g_key_file_set_uint64(file,group,"reading_rows",accounts.reading_rows);g_key_file_set_uint64(file,group,"reading_found",accounts.reading_found);
  g_key_file_set_uint64(file,group,"reading_unresolved",accounts.reading_unresolved);g_key_file_set_integer(file,group,"reading_more",accounts.reading_more);
  g_key_file_set_string(file,group,"resolutions",accounts.resolutions ? accounts.resolutions:"");
  g_key_file_set_uint64(file,group,"receive_seen",accounts.receive_seen);g_key_file_set_uint64(file,group,"projected",accounts.projected);
  g_key_file_set_uint64(file,group,"receive_attempt",accounts.receive_attempt);
  g_key_file_set_uint64(file,group,"conflicted",accounts.conflicted);g_key_file_set_uint64(file,group,"waiting",accounts.waiting);
  g_key_file_set_uint64(file,group,"receive_page_rows",accounts.receive_page_rows);g_key_file_set_uint64(file,group,"max_receive_page_rows",accounts.max_receive_page_rows);
  g_key_file_set_uint64(file,group,"conflict_rows",accounts.conflict_rows);
  g_key_file_set_string(file,group,"conflict_keys",accounts.conflict_keys ? accounts.conflict_keys:"");
  g_key_file_set_string(file,group,"conflict_heads",accounts.conflict_heads ? accounts.conflict_heads:"");
  g_key_file_set_uint64(file,group,"pushed",accounts.view.pushed);g_key_file_set_uint64(file,group,"pulled",accounts.view.pulled);
  g_key_file_set_integer(file,group,"completed_shards",accounts.view.completed_shards);
  g_key_file_set_integer(file,group,"full_library_complete",accounts.view.full_library_complete);
  g_key_file_set_string(file,group,"id",accounts.id ? accounts.id:"");g_key_file_set_string(file,group,"root",accounts.bound_root ? accounts.bound_root:"");
  if(accounts.dialog && !closing) {
    g_key_file_set_integer(file,group,"focused",gtk_window_is_active(GTK_WINDOW(accounts.dialog)));
    g_key_file_set_integer(file,group,"password_visible",gtk_entry_get_visibility(GTK_ENTRY(accounts.password)));
    g_key_file_set_integer(file,group,"has_password",gtk_entry_get_text(GTK_ENTRY(accounts.password))[0]!=0);
    g_key_file_set_integer(file,group,"has_user",gtk_entry_get_text(GTK_ENTRY(accounts.user))[0]!=0);
    g_key_file_set_integer(file,group,"remember",gtk_toggle_button_get_active(GTK_TOGGLE_BUTTON(accounts.remember)));
    g_key_file_set_integer(file,group,"form_enabled",gtk_widget_get_sensitive(accounts.form));
    g_key_file_set_integer(file,group,"retry_enabled",gtk_widget_get_sensitive(accounts.retry));
    g_key_file_set_integer(file,group,"cancel_enabled",gtk_widget_get_sensitive(accounts.cancel));
    g_key_file_set_integer(file,group,"receive_enabled",gtk_widget_get_sensitive(accounts.receive));
    g_key_file_set_string(file,group,"notice",gtk_label_get_text(GTK_LABEL(accounts.notice)));
  }
  char *data=g_key_file_to_data(file,NULL,NULL);g_key_file_free(file);return data;
}
static void accounts_cleanup(void) {
  if(accounts.timer) g_source_remove(accounts.timer);
  if(accounts.stage_idle) g_source_remove(accounts.stage_idle);
  g_clear_object(&accounts.resume_focus);g_clear_object(&accounts.return_focus);g_free(accounts.id);g_free(accounts.bound_root);
  g_free(accounts.receive_key);g_free(accounts.conflict_cursor);g_free(accounts.conflict_keys);g_free(accounts.conflict_heads);
  g_free(accounts.resolutions);
}
