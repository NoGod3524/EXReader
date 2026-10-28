/* SPDX-License-Identifier: MIT */
/* Modeless native dialog over the existing main message loop. The owner window
 * is disabled while an editor is shown; accepted jobs keep their close barrier. */
static INT_PTR CALLBACK metadata_dialog_procedure(HWND,UINT,WPARAM,LPARAM);
static void metadata_clear_ui(void) {
  reader_metadata_snapshot_free(g.metadata_snapshot);g.metadata_snapshot=NULL;
  free(g.metadata_title_value);free(g.metadata_author_value);
  g.metadata_title_value=g.metadata_author_value=NULL;
}
static void metadata_dialog_close(void) {
  if(g.metadata_running) return;
  if(g.metadata_dialog) DestroyWindow(g.metadata_dialog);
  else metadata_clear_ui();
}
static void metadata_dialog_controls(void) {
  if(!g.metadata_dialog) return;
  EnableWindow(g.metadata_dialog,TRUE);
  EnableWindow(GetDlgItem(g.metadata_dialog,IDC_METADATA_SAVE),!g.metadata_running && g.metadata_editable);
  EnableWindow(GetDlgItem(g.metadata_dialog,IDC_METADATA_CANCEL),!g.metadata_running);
  EnableWindow(GetDlgItem(g.metadata_dialog,IDC_METADATA_RETRY),!g.metadata_running);
  EnableWindow(GetDlgItem(g.metadata_dialog,IDC_METADATA_DISCARD),!g.metadata_running);
  EnableWindow(g.metadata_title,!g.metadata_running && g.metadata_editable);
  EnableWindow(g.metadata_author,!g.metadata_running && g.metadata_editable);
  EnableWindow(g.metadata_favorite,!g.metadata_running && g.metadata_editable);
}
static wchar_t *metadata_read_entry(HWND entry) {
  int length=GetWindowTextLengthW(entry);
  if(length<0 || length>8192) return NULL;
  wchar_t *value=calloc((size_t)length+1,sizeof(*value));
  if(value && GetWindowTextW(entry,value,length+1)!=length) { free(value);return NULL; }
  return value;
}
static void metadata_submit_job(int kind) {
  if(g.metadata_running || g.job || g.pending || g.closing) return;
  host_job *job=job_new(kind);if(!job) { set_status(L"无法建立书籍编辑任务。");return; }
  job->book_id=g.metadata_book;
  snprintf(job->metadata_key,sizeof(job->metadata_key),"%s",g.metadata_key);
  if(kind==JOB_METADATA_SAVE) {
    if(!g.metadata_snapshot || !g.metadata_editable) { job_release(job);return; }
    job->metadata_input_title=metadata_read_entry(g.metadata_title);
    job->metadata_input_author=metadata_read_entry(g.metadata_author);
    if(!job->metadata_input_title || !job->metadata_input_author) { job_release(job);set_status(L"无法读取书名或作者，请检查输入。");return; }
    job->metadata_favorite=SendMessageW(g.metadata_favorite,BM_GETCHECK,0,0)==BST_CHECKED;
    job->metadata_conflict=g.metadata_editable==2;
    job->metadata_snapshot=g.metadata_snapshot;g.metadata_snapshot=NULL;
  }
  g.metadata_running=1;
  host_a11y_owner_enabled(0);
  metadata_dialog_controls();
  set_status(kind==JOB_METADATA_PREPARE ? L"正在读取书籍信息。":L"正在保存书籍信息，完成后可以继续操作。");job_submit(job);
}
static void metadata_failed_to_start(host_job *job) {
  g.metadata_running=0;
  if(job->metadata_snapshot && !g.metadata_snapshot) { g.metadata_snapshot=job->metadata_snapshot;job->metadata_snapshot=NULL; }
  host_a11y_owner_enabled(g.metadata_dialog==NULL);metadata_dialog_controls();
}
static HWND metadata_entry(HWND parent,int id,int y,const wchar_t *value) {
  HWND entry=CreateWindowExW(WS_EX_CLIENTEDGE,L"EDIT",value ? value:L"",WS_CHILD|WS_VISIBLE|WS_TABSTOP|ES_AUTOHSCROLL,
    108,y,486,26,parent,(HMENU)(INT_PTR)id,NULL,NULL);
  SendMessageW(entry,WM_SETFONT,(WPARAM)GetStockObject(DEFAULT_GUI_FONT),TRUE);
  SendMessageW(entry,EM_SETLIMITTEXT,8192,0);return entry;
}
static INT_PTR CALLBACK metadata_dialog_procedure(HWND dialog,UINT message,WPARAM wparam,LPARAM lparam) {
  (void)lparam;
  switch(message) {
    case WM_INITDIALOG:
      g.metadata_dialog=dialog;
      SetWindowTextW(dialog,g.metadata_recovery ? L"恢复书籍编辑":L"书籍详情");
      if(g.metadata_recovery) {
        g.metadata_message=make_static(dialog,IDC_METADATA_MESSAGE,g.metadata_notice);
        MoveWindow(g.metadata_message,18,20,572,112,TRUE);
        MoveWindow(make_button(dialog,IDC_METADATA_RETRY,L"重试(&R)"),222,160,112,30,TRUE);
        MoveWindow(make_button(dialog,IDC_METADATA_DISCARD,L"放弃未提交(&D)"),342,160,142,30,TRUE);
        MoveWindow(make_button(dialog,IDC_METADATA_CANCEL,L"关闭"),492,160,102,30,TRUE);
        SendMessageW(dialog,DM_SETDEFID,IDC_METADATA_RETRY,0);
        SetFocus(GetDlgItem(dialog,IDC_METADATA_RETRY));return FALSE;
      }
      MoveWindow(make_static(dialog,0,L"书名(&T)"),18,20,82,22,TRUE);
      g.metadata_title=metadata_entry(dialog,IDC_METADATA_TITLE,16,g.metadata_title_value);
      MoveWindow(make_static(dialog,0,L"作者(&A)"),18,58,82,22,TRUE);
      g.metadata_author=metadata_entry(dialog,IDC_METADATA_AUTHOR,54,g.metadata_author_value);
      g.metadata_favorite=CreateWindowExW(0,L"BUTTON",L"收藏(&F)",WS_CHILD|WS_VISIBLE|WS_TABSTOP|BS_AUTOCHECKBOX,
        108,94,230,26,dialog,(HMENU)(INT_PTR)IDC_METADATA_FAVORITE,NULL,NULL);
      SendMessageW(g.metadata_favorite,WM_SETFONT,(WPARAM)GetStockObject(DEFAULT_GUI_FONT),TRUE);
      SendMessageW(g.metadata_favorite,BM_SETCHECK,g.metadata_favorite_value ? BST_CHECKED:BST_UNCHECKED,0);
      g.metadata_message=make_static(dialog,IDC_METADATA_MESSAGE,g.metadata_notice);
      MoveWindow(g.metadata_message,18,132,576,48,TRUE);
      MoveWindow(make_button(dialog,IDC_METADATA_SAVE,L"保存(&S)"),364,196,110,30,TRUE);
      MoveWindow(make_button(dialog,IDC_METADATA_CANCEL,L"取消(&C)"),484,196,110,30,TRUE);
      if(!g.metadata_editable && g.metadata_snapshot) {
        const reader_metadata_view *view=reader_metadata_snapshot_view(g.metadata_snapshot);
        if(view && view->head_count>1 && !view->graph.missing_parents && !view->graph.foreign_parents && !view->graph.requires_restore)
          MoveWindow(make_button(dialog,18999,L"明确合并版本"),18,196,150,30,TRUE);
      }
      SendMessageW(dialog,DM_SETDEFID,IDC_METADATA_SAVE,0);metadata_dialog_controls();
      SetFocus(g.metadata_title);return FALSE;
    case WM_COMMAND: {
      int id=LOWORD(wparam);
      if(g.metadata_running) return TRUE;
      if(id==IDCANCEL || id==IDC_METADATA_CANCEL) metadata_dialog_close();
      else if(id==18999) {
        if(MessageBoxW(dialog,L"将以你接下来填写的书名、作者和收藏状态合并全部已观察版本。旧修订和原书不会删除。确认后仍需点击保存。",L"明确处理版本冲突",MB_YESNO|MB_ICONQUESTION)==IDYES) {
          g.metadata_editable=2;metadata_dialog_controls();
          SetWindowTextW(g.metadata_message,L"填写合并后的信息并保存；若版本已再次变化，将拒绝覆盖。");
          EnableWindow(GetDlgItem(dialog,18999),FALSE);
        }
      }
      else if(id==IDOK) metadata_submit_job(g.metadata_recovery ? JOB_METADATA_RETRY:JOB_METADATA_SAVE);
      else if(id==IDC_METADATA_SAVE) metadata_submit_job(JOB_METADATA_SAVE);
      else if(id==IDC_METADATA_RETRY) metadata_submit_job(JOB_METADATA_RETRY);
      else if(id==IDC_METADATA_DISCARD) metadata_submit_job(JOB_METADATA_DISCARD);
      return TRUE;
    }
    case WM_CLOSE:
      if(!g.metadata_running) metadata_dialog_close();
      return TRUE;
    case WM_DESTROY:
      g.metadata_dialog=g.metadata_title=g.metadata_author=g.metadata_favorite=g.metadata_message=NULL;
      metadata_clear_ui();
      if(g.window && IsWindow(g.window)) {
        host_a11y_owner_enabled(1);
        /* Closing a read-only/cancelled editor has no shelf mutation. Save and
           discard completions already schedule their own refresh; refreshing
           here disables the just-restored invoking button and loses focus. */
        if(!g.closing) { SetActiveWindow(g.window);SetFocus(g.metadata_button); }
      }
      return TRUE;
  }
  return FALSE;
}
static void metadata_show_dialog(void) {
  union { DWORD alignment; unsigned char bytes[sizeof(DLGTEMPLATE)+6]; } data={0};
  memset(&data,0,sizeof(data));
  DLGTEMPLATE *dialog=(DLGTEMPLATE *)data.bytes;
  dialog->style=WS_POPUP|WS_CAPTION|WS_SYSMENU|DS_MODALFRAME;dialog->cx=340;dialog->cy=150;
  HWND window=CreateDialogIndirectParamW(GetModuleHandleW(NULL),dialog,g.window,metadata_dialog_procedure,0);
  if(!window) { metadata_clear_ui();host_a11y_owner_enabled(1);set_status(L"无法打开书籍详情窗口。");return; }
  RECT parent;GetWindowRect(g.window,&parent);
  SetWindowPos(window,HWND_TOP,parent.left+140,parent.top+100,628,g.metadata_recovery ? 244:278,SWP_SHOWWINDOW);
  host_a11y_owner_enabled(0);SetForegroundWindow(window);
  SetFocus(g.metadata_recovery ? GetDlgItem(window,IDC_METADATA_RETRY):g.metadata_title);
}
static void metadata_edit_selected(void) {
  if(g.metadata_dialog || g.metadata_running || g.job || g.pending || g.closing || !g.product_ready || g.product_pending) return;
  LRESULT row=SendMessageW(g.books,LB_GETCURSEL,0,0);
  if(row==LB_ERR || row<0 || (size_t)row>=g.shelf_count || !g.shelf_cursors || g.shelf[row].id<=0) {
    set_status(L"请先在书架中选择一本已下载的书。");return;
  }
  g.metadata_book=g.shelf[row].id;
  snprintf(g.metadata_key,sizeof(g.metadata_key),"%s",g.shelf_cursors[row].key);
  metadata_submit_job(JOB_METADATA_PREPARE);
}
static void metadata_job_accept(host_job *job) {
  /* WM_HOST_COMPLETE has joined the old worker. Move the independent snapshot
   * here, and later move it into a new job; no native owner crosses threads. */
  g.metadata_running=0;
  if(g.closing) { metadata_dialog_close();return; }
  if(job->metadata_has_pending) {
    metadata_dialog_close();g.metadata_recovery=1;g.metadata_editable=0;
    copy_wstring(g.metadata_notice,512,job->metadata_committed ?
      L"修改已保存，恢复记录暂未清理。重试会确认保存结果，不会重复修改。":
      job->metadata_conflict ? L"这本书已在别处修改。你的修改已保留，无法覆盖当前版本。可以关闭窗口，或放弃这次未提交的修改。":
      L"这次修改尚未完成，内容已保留。可以重试，或放弃尚未提交的修改。");
    metadata_show_dialog();
  } else if(job->metadata_has_view) {
    metadata_dialog_close();g.metadata_recovery=0;g.metadata_editable=!job->metadata_conflict;
    g.metadata_snapshot=job->metadata_snapshot;job->metadata_snapshot=NULL;
    g.metadata_title_value=job->metadata_title_value;job->metadata_title_value=NULL;
    g.metadata_author_value=job->metadata_author_value;job->metadata_author_value=NULL;
    g.metadata_favorite_value=job->metadata_favorite;
    copy_wstring(g.metadata_notice,512,job->metadata_conflict ? L"书籍存在尚未处理的版本差异，暂不能编辑。":L"");
    metadata_show_dialog();
  } else if(job->status==EXR_OK || job->metadata_committed) {
    metadata_dialog_close();product_shelf_schedule(0,0);
    set_status(job->metadata_committed ? L"书籍信息已保存。":L"未提交的修改已放弃。");
  } else {
    if(job->metadata_snapshot && !g.metadata_snapshot) { g.metadata_snapshot=job->metadata_snapshot;job->metadata_snapshot=NULL; }
    if(g.metadata_dialog) {
      metadata_dialog_controls();SetWindowTextW(g.metadata_message,L"暂时无法保存，请检查输入并重试。已保存的信息不会改变。");
    } else host_a11y_owner_enabled(1);
    set_status(L"暂时无法处理书籍信息，请检查输入或重新打开详情。");
  }
}
