/* SPDX-License-Identifier: MIT
 * On-demand, native Win32 controls. The ordinary shelf remains unchanged; the
 * expanded bookshelf is a native extended-selection list of a stable snapshot.
 */
static void winio_accept(host_job *job);
static void winio_controls(void) {
  if(!winio.dialog) return;
  int idle=!winio.running && !g.job && !g.pending && !g.closing;
  const int controls[]={IDC_IO_GO,IDC_IO_ROOT,IDC_IO_UP,IDC_IO_ACTION,IDC_IO_GROUPS,IDC_IO_MORE,IDC_IO_RESUME,IDC_IO_ACK,IDC_IO_CLEANUP,IDC_IO_ROWS};
  for(size_t i=0;i<sizeof(controls)/sizeof(controls[0]);i++) EnableWindow(GetDlgItem(winio.dialog,controls[i]),idle);
  EnableWindow(GetDlgItem(winio.dialog,IDC_IO_CANCEL),winio.running);
  EnableWindow(GetDlgItem(winio.dialog,IDC_IO_ACK),idle && winio.summary.complete);
  EnableWindow(GetDlgItem(winio.dialog,IDC_IO_MORE),idle && winio.group_count==200);
  EnableWindow(GetDlgItem(winio.dialog,IDC_IO_CLEANUP),idle && (winio.retained!=NULL || winio.orphans));
  if(winio.mode==WINIO_CLOUD) EnableWindow(GetDlgItem(winio.dialog,IDC_IO_GO),idle && !winio.retained && !winio.orphans);
}
static void winio_destroy(void) {
  if(winio.running) return;
  if(winio.dialog) DestroyWindow(winio.dialog);
}
static host_job *winio_new(int operation) {
  host_job *job=job_new(JOB_IMPORT_ORGANIZE);if(!job) return NULL;
  job->io=calloc(1,sizeof(*job->io));if(!job->io) { job_release(job);return NULL; }
  job->io->operation=operation;job->io->mode=winio.mode;job->io->generation=winio.generation;
  snprintf(job->io->account,sizeof(job->io->account),"%s",acct.owner.id);
  return job;
}
static void winio_submit(host_job *job) {
  if(!job) { SetWindowTextW(winio.message,L"无法创建任务。");return; }
  winio.running=1;winio_controls();SetWindowTextW(winio.message,L"正在处理；取消只停止尚未提交的项目。");job_submit(job);
  if(!g.job && !g.pending) { winio.running=0;winio_controls(); }
}
static void winio_list(const char *resource) {
  if(winio.running || g.job || g.pending || g.closing) return;
  host_job *job=winio_new(WINIO_LIST);if(!job) return;
  snprintf(job->io->resource,sizeof(job->io->resource),"%s",resource);winio_submit(job);
}
static void winio_groups_load(int more) {
  if(winio.running || g.job || g.pending || g.closing) return;
  int action=(int)SendMessageW(winio.action,CB_GETCURSEL,0,0);
  winio.action_value=action;
  if(action<2) { SendMessageW(winio.groups,LB_RESETCONTENT,0,0);winio.group_count=0;return; }
  host_job *job=winio_new(WINIO_GROUPS);if(!job) return;
  job->io->group_kind=(action-2)/2;job->io->more=more;
  snprintf(job->io->parent,sizeof(job->io->parent),"%s",job->io->group_kind==0 ? winio.parent:"");
  if(more && winio.group_count) {
    winio_group *last=&winio.group_rows[winio.group_count-1];
    snprintf(job->io->after,sizeof(job->io->after),"%s",last->id);job->io->after_ordinal=last->ordinal;
  }
  winio_submit(job);
}
static void winio_go(void) {
  if(winio.running || g.job || g.pending || g.closing) return;
  if(winio.mode==WINIO_CLOUD) {
    LRESULT row=SendMessageW(winio.rows,LB_GETCURSEL,0,0);
    if(row==LB_ERR || (size_t)row>=winio.listing.count || winio.retained) return;
    exr_webdav_entry *entry=&winio.listing.entries[row];
    if(entry->collection) { winio_list(entry->resource);return; }
    if(reader_cloud_format_from_name(entry->display_name)==EXR_CUSTOM) { SetWindowTextW(winio.message,L"此文件不是支持的九种书籍格式。");return; }
    host_job *job=winio_new(WINIO_DOWNLOAD);if(!job) return;
    snprintf(job->io->resource,sizeof(job->io->resource),"%s",entry->resource);
    snprintf(job->io->name,sizeof(job->io->name),"%s",entry->display_name);
    job->io->bytes=entry->has_size ? entry->bytes:0;winio_submit(job);
  } else {
    LRESULT count=SendMessageW(winio.rows,LB_GETSELCOUNT,0,0);
    if(count<1 || count>READER_BULK_MAX_BATCH) { SetWindowTextW(winio.message,L"明确选择 1–100 本书（Ctrl/Shift 多选）；未选中的书不会修改。");return; }
    int selected[READER_BULK_MAX_BATCH];
    if(SendMessageW(winio.rows,LB_GETSELITEMS,READER_BULK_MAX_BATCH,(LPARAM)selected)!=count) return;
    host_job *job=winio_new(WINIO_RUN);if(!job) return;
    winio_job *v=job->io;v->action=(int)SendMessageW(winio.action,CB_GETCURSEL,0,0);v->count=(size_t)count;
    if(v->action<0 || v->action>7) { job_release(job);return; }
    if(v->action>=2) {
      LRESULT group=SendMessageW(winio.groups,LB_GETCURSEL,0,0);
      if(group<0 || (size_t)group>=winio.group_count) { job_release(job);SetWindowTextW(winio.message,L"请明确选择一个现有子书架、标签或系列；双击子书架进入下级。");return; }
      snprintf(v->group,sizeof(v->group),"%s",winio.group_rows[group].id);
    }
    for(size_t i=0;i<v->count;i++) {
      if(selected[i]<0 || (size_t)selected[i]>=winio.count) { job_release(job);return; }
      snprintf(v->keys[i],sizeof(v->keys[i]),"%s",winio.keys[selected[i]]);v->ids[i]=winio.ids[selected[i]];
    }
    winio_submit(job);
  }
}
static void winio_render_bulk(winio_job *v) {
  winio.summary=v->summary;memcpy(winio.results,v->results,sizeof(winio.results));
  SendMessageW(winio.report,LB_RESETCONTENT,0,0);
  for(size_t i=0;i<v->summary.total && i<READER_BULK_MAX_BATCH;i++) {
    reader_bulk_item_result *item=&v->results[i];wchar_t row[512];
    swprintf(row,512,L"%llu %hs | outcome=%d committed=%d created=%d conflict=%d replayed=%d | revision=%hs",
      (unsigned long long)(i+1),item->book_key,(int)item->outcome,item->committed,item->created,item->conflict,item->replayed,item->revision_id);
    SendMessageW(winio.report,LB_ADDSTRING,0,(LPARAM)row);
  }
  wchar_t text[512];swprintf(text,512,L"status=%d；committed=%llu created=%llu conflict=%llu unchanged=%llu failed=%llu not_run=%llu complete=%d。已提交不会回滚；恢复沿用原 revision。",
    (int)v->bulk_status,(unsigned long long)v->summary.committed,(unsigned long long)v->summary.created,
    (unsigned long long)v->summary.conflicts,(unsigned long long)v->summary.unchanged,(unsigned long long)v->summary.failed,
    (unsigned long long)v->summary.not_run,v->summary.complete);
  SetWindowTextW(winio.message,text);
}
static void winio_accept(host_job *job) {
  winio_job *v=job->io;winio.running=0;
  if(!v) return;
  /* Receipts and staged ownership survive stale UI generations. Only the
     current, still-open dialog can publish a listing or start the SDK phase. */
  int current=winio.dialog && v->generation==winio.generation && !winio.close_wanted && !g.closing;
  if(v->operation==WINIO_DOWNLOAD && job->status==EXR_OK && v->staged && current && !job_cancel_flag(job)) {
    host_job *next=winio_new(WINIO_IMPORT);
    if(next) { next->io->staged=v->staged;v->staged=NULL;snprintf(next->io->account,sizeof(next->io->account),"%s",v->account);winio_submit(next);return; }
  }
  if(v->operation==WINIO_DOWNLOAD && v->staged && v->cloud_status==READER_CLOUD_OK) {
    reader_cloud_staged_discard(&v->staged);v->cloud_status=READER_CLOUD_CANCELLED;
    v->imported.staging_removed=v->staged==NULL;v->receipt_saved=winio_receipt(job);
  }
  if(v->staged) { winio.retained=v->staged;v->staged=NULL; }
  if(current) {
    if(v->operation==WINIO_LIST && job->status==EXR_OK && !job_cancel_flag(job)) {
      exr_webdav_listing_free(&winio.listing);winio.listing=v->listing;memset(&v->listing,0,sizeof(v->listing));
      snprintf(winio.resource,sizeof(winio.resource),"%s",v->resource);SendMessageW(winio.rows,LB_RESETCONTENT,0,0);
      for(size_t i=0;i<winio.listing.count;i++) {
        exr_webdav_entry *e=&winio.listing.entries[i];wchar_t *name=host_wide(e->display_name,strlen(e->display_name)),line[1200];
        swprintf(line,1200,L"%ls%ls",e->collection ? L"[目录] ":L"",name ? name:L"");free(name);
        SendMessageW(winio.rows,LB_ADDSTRING,0,(LPARAM)line);
      }
      /* No implicit selection, even after refresh. */
      SendMessageW(winio.rows,LB_SETCURSEL,(WPARAM)-1,0);SetWindowTextW(winio.message,job->message);
    } else if(v->operation==WINIO_GROUPS && job->status==EXR_OK) {
      winio.group_count=v->group_count;memcpy(winio.group_rows,v->groups,sizeof(v->groups));SendMessageW(winio.groups,LB_RESETCONTENT,0,0);
      for(size_t i=0;i<v->group_count;i++) SendMessageW(winio.groups,LB_ADDSTRING,0,(LPARAM)v->groups[i].name);
      SetWindowTextW(winio.message,L"选择现有分组；书架可双击进入下级。Ctrl/Shift 多选书籍，最多 100 本。");
    } else if(v->mode==WINIO_BULK) {
      winio_render_bulk(v);if(v->summary.committed || v->operation==WINIO_ACK) product_shelf_schedule(0,0);
    } else {
      wchar_t text[512];
      if(v->operation==WINIO_LIST) swprintf(text,512,L"目录失败/取消 status=%d HTTP=%d；书库未改变。",v->dav_error.code,v->dav_error.http_status);
      else swprintf(text,512,L"status=%d HTTP=%d committed=%d created=%d book=%lld staging_removed=%d mapped=%d retained=%d receipt_saved=%d。",
        v->cloud_status,v->cloud_error.http_status,v->imported.committed,v->imported.created,(long long)v->imported.book_id,
        v->imported.staging_removed,v->mapped,winio.retained!=NULL,v->receipt_saved);
      SetWindowTextW(winio.message,text);
    }
  }
  if(v->imported.committed) {
    if(v->mapped) { if(job->product_key[0]) snprintf(g.shelf_selected_key,sizeof(g.shelf_selected_key),"%s",job->product_key);product_shelf_schedule(0,0); }
    else { g.product_pending=1;g.product_ready=0;set_status(L"原书已提交；书目映射待刷新或重开恢复。"); }
  }
  winio_controls();
  if(winio.close_wanted || g.closing) winio_destroy();
}
static void winio_close(void) {
  winio.close_wanted=1;winio.generation++;
  if(winio.running && g.job && winio_kind(g.job->kind)) InterlockedExchange(&g.job->cancel,1);
  else winio_destroy();
}
static INT_PTR CALLBACK winio_dialog_proc(HWND dialog,UINT message,WPARAM wparam,LPARAM lparam) {
  (void)lparam;
  if(message==WM_INITDIALOG) {
    winio.dialog=dialog;SetWindowTextW(dialog,winio.mode==WINIO_CLOUD ? L"从已配置云盘导入":L"书架批量整理");
    MoveWindow(make_static(dialog,0,winio.mode==WINIO_CLOUD ? L"云盘目录与书籍(&L)":L"书架多选（Ctrl/Shift，最多100本）(&L)"),16,12,720,24,TRUE);
    winio.rows=CreateWindowExW(WS_EX_CLIENTEDGE,L"LISTBOX",winio.mode==WINIO_CLOUD ? L"云盘目录与书籍":L"书架多选",
      WS_CHILD|WS_VISIBLE|WS_TABSTOP|WS_VSCROLL|LBS_NOTIFY|(winio.mode==WINIO_BULK ? LBS_EXTENDEDSEL:0),16,38,720,210,dialog,(HMENU)(INT_PTR)IDC_IO_ROWS,NULL,NULL);
    SendMessageW(winio.rows,WM_SETFONT,(WPARAM)GetStockObject(DEFAULT_GUI_FONT),TRUE);
    if(winio.mode==WINIO_BULK) {
      for(size_t i=0;i<winio.count;i++) SendMessageW(winio.rows,LB_ADDSTRING,0,(LPARAM)winio.titles[i]);
      MoveWindow(make_static(dialog,0,L"明确动作(&A)"),16,258,130,24,TRUE);
      winio.action=CreateWindowExW(0,L"COMBOBOX",L"整理动作",WS_CHILD|WS_VISIBLE|WS_TABSTOP|CBS_DROPDOWNLIST|WS_VSCROLL,150,254,250,240,dialog,(HMENU)(INT_PTR)IDC_IO_ACTION,NULL,NULL);
      const wchar_t *actions[]={L"收藏",L"取消收藏",L"加入子书架",L"移出子书架",L"加入标签",L"移出标签",L"加入系列",L"移出系列"};
      for(int i=0;i<8;i++) SendMessageW(winio.action,CB_ADDSTRING,0,(LPARAM)actions[i]);SendMessageW(winio.action,CB_SETCURSEL,0,0);
      winio.groups=CreateWindowExW(WS_EX_CLIENTEDGE,L"LISTBOX",L"现有分组",WS_CHILD|WS_VISIBLE|WS_TABSTOP|WS_VSCROLL|LBS_NOTIFY,16,290,390,105,dialog,(HMENU)(INT_PTR)IDC_IO_GROUPS,NULL,NULL);
      MoveWindow(make_button(dialog,IDC_IO_ROOT,L"根分组"),420,290,100,28,TRUE);
      MoveWindow(make_button(dialog,IDC_IO_UP,L"上级"),528,290,100,28,TRUE);
      MoveWindow(make_button(dialog,IDC_IO_MORE,L"更多分组"),636,290,100,28,TRUE);
      MoveWindow(make_button(dialog,IDC_IO_RESUME,L"恢复原请求(&R)"),420,330,150,28,TRUE);
      MoveWindow(make_button(dialog,IDC_IO_ACK,L"确认已完成报告"),580,330,156,28,TRUE);
      winio.report=CreateWindowExW(WS_EX_CLIENTEDGE,L"LISTBOX",L"逐项提交与未执行回执",WS_CHILD|WS_VISIBLE|WS_TABSTOP|WS_VSCROLL|WS_HSCROLL|LBS_NOTIFY,16,405,720,105,dialog,(HMENU)(INT_PTR)IDC_IO_REPORT,NULL,NULL);
      SendMessageW(winio.report,LB_SETHORIZONTALEXTENT,1600,0);
    } else {
      MoveWindow(make_button(dialog,IDC_IO_ROOT,L"根目录/刷新"),16,260,140,28,TRUE);
      MoveWindow(make_button(dialog,IDC_IO_UP,L"上级目录"),166,260,120,28,TRUE);
      MoveWindow(make_button(dialog,IDC_IO_CLEANUP,L"重试暂存清理"),296,260,170,28,TRUE);
    }
    int y=winio.mode==WINIO_CLOUD ? 310:520;
    winio.message=make_static(dialog,IDC_IO_MESSAGE,L"明确选择后才会修改书库。");MoveWindow(winio.message,16,y,720,68,TRUE);
    MoveWindow(make_button(dialog,IDC_IO_GO,winio.mode==WINIO_CLOUD ? L"打开目录/导入选书(&I)":L"应用到选中书籍(&I)"),16,y+78,250,30,TRUE);
    MoveWindow(make_button(dialog,IDC_IO_CANCEL,L"取消未执行(&C)"),276,y+78,170,30,TRUE);
    MoveWindow(make_button(dialog,IDC_IO_CLOSE,L"关闭"),616,y+78,120,30,TRUE);
    SendMessageW(dialog,DM_SETDEFID,IDC_IO_GO,0);winio_controls();SetFocus(winio.rows);return FALSE;
  }
  if(message==WM_COMMAND) {
    int id=LOWORD(wparam),code=HIWORD(wparam);
    if(id==IDCANCEL || id==IDC_IO_CLOSE) { winio_close();return TRUE; }
    if(id==IDC_IO_CANCEL) { if(g.job && winio_kind(g.job->kind)) InterlockedExchange(&g.job->cancel,1);return TRUE; }
    if(winio.running || g.job || g.pending || g.closing) return TRUE;
    if(id==IDOK || id==IDC_IO_GO || (id==IDC_IO_ROWS && code==LBN_DBLCLK && winio.mode==WINIO_CLOUD)) winio_go();
    else if(id==IDC_IO_ACTION && code==CBN_SELCHANGE) { winio.parent[0]=0;winio.depth=0;winio_groups_load(0); }
    else if(id==IDC_IO_GROUPS && code==LBN_DBLCLK && winio.action_value>=2 && winio.action_value<=3) {
      LRESULT selected=SendMessageW(winio.groups,LB_GETCURSEL,0,0);
      if(selected>=0 && (size_t)selected<winio.group_count && winio.depth<32) {
        snprintf(winio.parents[winio.depth++],33,"%s",winio.parent);snprintf(winio.parent,33,"%s",winio.group_rows[selected].id);winio_groups_load(0);
      }
    } else if(id==IDC_IO_ROOT || id==IDC_IO_UP) {
      if(winio.mode==WINIO_CLOUD) {
        char parent[4097];snprintf(parent,sizeof(parent),"%s",winio.resource);
        if(id==IDC_IO_ROOT) parent[0]=0;
        else { size_t n=strlen(parent);if(n && parent[n-1]=='/') parent[--n]=0;char *slash=strrchr(parent,'/');if(slash) slash[1]=0;else parent[0]=0; }
        winio_list(parent);
      } else {
        if(id==IDC_IO_ROOT) { winio.parent[0]=0;winio.depth=0; }
        else if(winio.depth) snprintf(winio.parent,33,"%s",winio.parents[--winio.depth]);
        winio_groups_load(0);
      }
    } else if(id==IDC_IO_MORE) winio_groups_load(1);
    else if(id==IDC_IO_RESUME || id==IDC_IO_ACK || id==IDC_IO_CLEANUP)
      winio_submit(winio_new(id==IDC_IO_RESUME ? WINIO_RESUME:id==IDC_IO_ACK ? WINIO_ACK:WINIO_CLEAN));
    return TRUE;
  }
  if(message==WM_CLOSE) { winio_close();return TRUE; }
  if(message==WM_DESTROY) {
    winio.dialog=winio.rows=winio.groups=winio.action=winio.message=winio.report=NULL;
    exr_webdav_listing_free(&winio.listing);winio.close_wanted=0;
    host_a11y_owner_enabled(1);if(!g.closing) { SetActiveWindow(g.window);SetFocus(winio.mode==WINIO_CLOUD ? g.import_button:g.books);product_shelf_dispatch(); }
    return TRUE;
  }
  return FALSE;
}
static void winio_show(int mode) {
  if(winio.dialog || winio.running || g.closing || g.job || g.pending || g.metadata_dialog || acct.dialog || acct_busy() || !g.product_ready || g.product_pending) return;
  winio.mode=mode;winio.generation++;winio.close_wanted=0;winio.depth=0;winio.parent[0]=winio.resource[0]=0;winio.group_count=0;
  if(mode==WINIO_BULK) {
    winio.count=g.shelf_count<150 ? g.shelf_count:150;
    for(size_t i=0;i<winio.count;i++) { snprintf(winio.keys[i],73,"%s",g.shelf_cursors[i].key);winio.ids[i]=g.shelf[i].id;shelf_display(&g.shelf[i],winio.titles[i],512); }
  }
  union { DWORD align;unsigned char bytes[sizeof(DLGTEMPLATE)+6]; } data={0};
  DLGTEMPLATE *dialog=(DLGTEMPLATE *)data.bytes;dialog->style=WS_POPUP|WS_CAPTION|WS_SYSMENU|DS_MODALFRAME;dialog->cx=420;dialog->cy=360;
  HWND window=CreateDialogIndirectParamW(GetModuleHandleW(NULL),dialog,g.window,winio_dialog_proc,0);
  if(!window) return;
  RECT r;GetWindowRect(g.window,&r);SetWindowPos(window,HWND_TOP,r.left+70,r.top+30,770,mode==WINIO_CLOUD ? 470:680,SWP_SHOWWINDOW);
  host_a11y_owner_enabled(0);SetForegroundWindow(window);SetFocus(winio.rows);
  if(mode==WINIO_CLOUD) winio_list("");else winio_submit(winio_new(WINIO_INSPECT));
}
static int winio_context(HWND source,LPARAM where) {
  if(source!=g.import_button && source!=g.books && source!=g.metadata_button) return 0;
  if(g.job || g.pending || g.closing || winio.dialog || acct.dialog || g.metadata_dialog) return 1;
  HMENU menu=CreatePopupMenu();if(!menu) return 1;
  AppendMenuW(menu,MF_STRING,source==g.import_button ? IDC_CLOUD_IMPORT:IDC_BULK_ORGANIZE,
    source==g.import_button ? L"从已配置云盘导入…":L"批量整理选书…");
  POINT p={(short)LOWORD(where),(short)HIWORD(where)};
  if(p.x==-1 && p.y==-1) { RECT r;GetWindowRect(source,&r);p.x=r.left;p.y=r.bottom; }
  int id=TrackPopupMenu(menu,TPM_RETURNCMD|TPM_RIGHTBUTTON,p.x,p.y,0,g.window,NULL);DestroyMenu(menu);
  if(id) winio_show(id==IDC_CLOUD_IMPORT ? WINIO_CLOUD:WINIO_BULK);return 1;
}
