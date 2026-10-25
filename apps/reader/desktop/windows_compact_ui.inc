/* SPDX-License-Identifier: MIT */
/* Independent default-OFF candidate. All commands reuse the real host owner. */
enum { IDC_COMPACT_SHELF = 46001, IDC_COMPACT_READ, IDC_COMPACT_MORE, IDC_COMPACT_IMPORT };
static int compact_reading, compact_expanded;
static HWND compact_back, compact_resume;
static void layout_controls(void);

static void compact_controls(void) {
  EnableWindow(compact_back, !g.closing);
  EnableWindow(compact_resume, !g.closing && !g.job && !g.pending && g.has_current && g.frame.valid);
}

static void compact_visible(HWND window, int visible) {
  if (window) ShowWindow(window, visible ? SW_SHOWNA : SW_HIDE);
}

static int compact_layout(void) {
  RECT area;
  HWND controls[] = {g.import_label,g.import_edit,g.import_button,g.open_button,g.delete_button,
    g.prev_button,g.next_button,g.select_button,g.copy_button,g.add_button,g.update_button,
    g.remove_button,g.jump_button,g.font_dec,g.font_inc,g.zoom_dec,g.zoom_inc,g.cancel_button,
    g.shelf_label,g.books,g.notes_label,g.notes,g.note_edit_label,g.note_edit,g.page,g.page_label,
    g.status,g.shelf_search_label,
#ifdef EXR_READER_PRODUCT_CATALOG
    g.shelf_search,g.shelf_refresh,
#endif
#ifdef EXR_READER_DESKTOP_METADATA
    g.metadata_button,
#endif
#ifdef EXR_READER_WINDOWS_ACCOUNT
    g.account_button,
#endif
#ifdef EXR_READER_WINDOWS_SEARCH
    inbook.button,
#endif
#ifdef EXR_READER_WINDOWS_NAVIGATION
    directory.button,
#endif
#ifdef EXR_READER_WINDOWS_RECORDS
    records.button,
#endif
  };
  for (size_t i=0;i<sizeof(controls)/sizeof(controls[0]);i++) compact_visible(controls[i],compact_expanded);
  compact_visible(compact_back,0);compact_visible(compact_resume,0);
  if (compact_expanded) return 0;
  GetClientRect(g.window,&area);
  int width=area.right,height=area.bottom;
  compact_visible(g.status,1);MoveWindow(g.status,12,height-28,width-24,22,TRUE);
  if (compact_reading) {
    compact_visible(compact_back,1);MoveWindow(compact_back,12,10,80,28,TRUE);
    compact_visible(g.prev_button,1);MoveWindow(g.prev_button,100,10,80,28,TRUE);
    compact_visible(g.next_button,1);MoveWindow(g.next_button,188,10,80,28,TRUE);
    compact_visible(g.page_label,1);MoveWindow(g.page_label,280,14,width-292,22,TRUE);
    compact_visible(g.page,1);MoveWindow(g.page,12,48,width-24,height-84,TRUE);
  } else {
    compact_visible(g.import_button,1);MoveWindow(g.import_button,width-92,10,80,28,TRUE);
    compact_visible(g.open_button,1);MoveWindow(g.open_button,width-180,10,80,28,TRUE);
    compact_visible(compact_resume,1);MoveWindow(compact_resume,width-268,10,80,28,TRUE);
#ifdef EXR_READER_PRODUCT_CATALOG
    compact_visible(g.shelf_search_label,1);MoveWindow(g.shelf_search_label,12,14,52,22,TRUE);
    compact_visible(g.shelf_search,1);MoveWindow(g.shelf_search,68,10,width-348,28,TRUE);
#endif
    compact_visible(g.shelf_label,1);MoveWindow(g.shelf_label,12,48,width-24,20,TRUE);
    compact_visible(g.books,1);MoveWindow(g.books,12,72,width-24,height-108,TRUE);
#ifdef EXR_READER_PRODUCT_CATALOG
    if(g.product_ready) PostMessageW(g.window,WM_APP+31,0,0);
#endif
  }
  compact_controls();
  HWND focus=GetFocus();
  if(focus && IsChild(g.window,focus) && !IsWindowVisible(focus)) SetFocus(compact_reading ? g.page:g.books);
  InvalidateRect(g.page,NULL,TRUE);
  return 1;
}

static void compact_switch(int reading) {
  compact_reading=reading && g.has_current && g.frame.valid;
  compact_expanded=0;
  layout_controls();SetFocus(compact_reading ? g.page:g.books);
}

static void compact_import(void) {
  if(g.job || g.pending || g.closing) return;
  wchar_t path[HOST_PATH]={0};OPENFILENAMEW choose={0};
  choose.lStructSize=sizeof(choose);choose.hwndOwner=g.window;
  choose.lpstrFilter=L"支持的书籍\0*.epub;*.txt;*.pdf;*.html;*.htm;*.docx;*.mobi;*.fb2;*.rtf;*.cbz\0所有文件\0*.*\0\0";
  choose.lpstrFile=path;choose.nMaxFile=HOST_PATH;
  choose.Flags=OFN_FILEMUSTEXIST|OFN_PATHMUSTEXIST|OFN_NOCHANGEDIR|OFN_EXPLORER;
  if(GetOpenFileNameW(&choose)) {
    SetWindowTextW(g.import_edit,path);host_command(IDC_IMPORT_BUTTON);
  } else if(CommDlgExtendedError()) set_status(L"无法打开系统文件选择器。");
}

static void compact_expand(int expanded) {
  compact_expanded=expanded;
  /* The existing full panel keeps its original usable minimum geometry. */
  if(expanded) {
    RECT bounds;GetWindowRect(g.window,&bounds);
    if(bounds.right-bounds.left<1060 || bounds.bottom-bounds.top<660)
      SetWindowPos(g.window,NULL,0,0,1060,660,SWP_NOMOVE|SWP_NOZORDER|SWP_NOACTIVATE);
  }
  layout_controls();
}

static int compact_command(int id) {
  if(id==IDC_COMPACT_IMPORT || (id==IDC_IMPORT_BUTTON && !compact_expanded)) { compact_import();return 1; }
  if(id==IDC_COMPACT_SHELF) { compact_switch(0);return 1; }
  if(id==IDC_COMPACT_READ) { compact_switch(1);return 1; }
  if(id==IDC_ADD_NOTE && !compact_expanded) {
    compact_expand(1);SetFocus(g.note_edit);return 1;
  }
  if(id==IDC_COMPACT_MORE) {
    compact_expand(!compact_expanded);return 1;
  }
  return 0;
}

static void compact_complete(const host_job *job) {
  if(!g.has_current && compact_reading) compact_switch(0);
  else if(job->kind==JOB_OPEN && job->status==EXR_OK && g.has_current && g.frame.valid) compact_switch(1);
}

static void compact_menu_update(void) {
  HMENU menu=GetMenu(g.window);
  const struct { int id;HWND control; } items[] = {
    {IDC_COMPACT_IMPORT,g.import_button},{IDC_OPEN_BUTTON,g.open_button},{IDC_DELETE_BUTTON,g.delete_button},
    {IDC_COMPACT_READ,compact_resume},{IDC_PREV,g.prev_button},{IDC_NEXT,g.next_button},
    {IDC_SELECT_ALL,g.select_button},{IDC_COPY_QUOTE,g.copy_button},
    {IDC_ADD_NOTE,g.add_button},{IDC_UPDATE_NOTE,g.update_button},{IDC_DELETE_NOTE,g.remove_button},{IDC_JUMP_NOTE,g.jump_button},
    {IDC_FONT_DEC,g.font_dec},{IDC_FONT_INC,g.font_inc},{IDC_ZOOM_DEC,g.zoom_dec},{IDC_ZOOM_INC,g.zoom_inc},{IDC_CANCEL,g.cancel_button},
#ifdef EXR_READER_DESKTOP_METADATA
    {IDC_METADATA_BUTTON,g.metadata_button},
#endif
#ifdef EXR_READER_WINDOWS_ACCOUNT
    {IDC_ACCOUNT_BUTTON,g.account_button},
#endif
  };
  for(size_t i=0;i<sizeof(items)/sizeof(items[0]);i++)
    EnableMenuItem(menu,items[i].id,MF_BYCOMMAND|(IsWindowEnabled(items[i].control)?MF_ENABLED:MF_GRAYED));
  CheckMenuItem(menu,IDC_COMPACT_MORE,MF_BYCOMMAND|(compact_expanded?MF_CHECKED:MF_UNCHECKED));
}

static void compact_create(HWND parent) {
  compact_back=make_button(parent,IDC_COMPACT_SHELF,L"书架");
  compact_resume=make_button(parent,IDC_COMPACT_READ,L"继续阅读");
  HMENU menu=GetMenu(parent),library=CreatePopupMenu(),reading=CreatePopupMenu(),view=CreatePopupMenu();
  int had_menu=menu!=NULL;
  if(!menu) menu=CreateMenu();
  if(!menu || !library || !reading || !view) {
    if(library) DestroyMenu(library);if(reading) DestroyMenu(reading);if(view) DestroyMenu(view);
    if(menu && !had_menu) DestroyMenu(menu);
    compact_expanded=1;return;
  }
  AppendMenuW(library,MF_STRING,IDC_COMPACT_IMPORT,L"导入书籍…\tCtrl+O");
  AppendMenuW(library,MF_STRING,IDC_OPEN_BUTTON,L"打开所选书籍");
  AppendMenuW(library,MF_STRING,IDC_COMPACT_READ,L"继续阅读");
  AppendMenuW(library,MF_STRING,IDC_DELETE_BUTTON,L"删除所选书籍");
#ifdef EXR_READER_DESKTOP_METADATA
  AppendMenuW(library,MF_STRING,IDC_METADATA_BUTTON,L"书籍详情…");
#endif
#ifdef EXR_READER_WINDOWS_ACCOUNT
  AppendMenuW(library,MF_STRING,IDC_ACCOUNT_BUTTON,L"同步账号…");
#endif
#ifdef EXR_READER_WINDOWS_IMPORT_ORGANIZE
  AppendMenuW(library,MF_STRING,IDC_CLOUD_IMPORT,L"从云盘导入…");
  AppendMenuW(library,MF_STRING,IDC_BULK_ORGANIZE,L"批量整理…");
#endif
  AppendMenuW(reading,MF_STRING,IDC_PREV,L"上一页");AppendMenuW(reading,MF_STRING,IDC_NEXT,L"下一页");
#ifdef EXR_READER_WINDOWS_SEARCH
  AppendMenuW(reading,MF_STRING,IDC_INBOOK,L"书内搜索…");
#endif
#ifdef EXR_READER_WINDOWS_NAVIGATION
  AppendMenuW(reading,MF_STRING,IDC_DIRECTORY,L"目录…");
#endif
#ifdef EXR_READER_WINDOWS_RECORDS
  AppendMenuW(reading,MF_STRING,IDC_RECORDS,L"书签与阅读记录…");
#endif
  AppendMenuW(reading,MF_STRING,IDC_SELECT_ALL,L"选择本页文字");AppendMenuW(reading,MF_STRING,IDC_COPY_QUOTE,L"复制引用");
  AppendMenuW(reading,MF_STRING,IDC_ADD_NOTE,L"标注编辑…");
  AppendMenuW(reading,MF_STRING,IDC_FONT_DEC,L"缩小字号");AppendMenuW(reading,MF_STRING,IDC_FONT_INC,L"增大字号");
  AppendMenuW(reading,MF_STRING,IDC_ZOOM_DEC,L"缩小固定页");AppendMenuW(reading,MF_STRING,IDC_ZOOM_INC,L"放大固定页");
  AppendMenuW(view,MF_STRING,IDC_COMPACT_SHELF,L"书架\tCtrl+L");
  AppendMenuW(view,MF_STRING,IDC_COMPACT_MORE,L"更多操作(&M)");
  AppendMenuW(view,MF_STRING,IDC_CANCEL,L"取消当前任务");
  InsertMenuW(menu,0,MF_BYPOSITION|MF_POPUP,(UINT_PTR)library,L"书库(&B)");
  InsertMenuW(menu,1,MF_BYPOSITION|MF_POPUP,(UINT_PTR)reading,L"阅读(&R)");
  InsertMenuW(menu,2,MF_BYPOSITION|MF_POPUP,(UINT_PTR)view,L"视图(&V)");
  SetMenu(parent,menu);DrawMenuBar(parent);
}

static int compact_translate(const MSG *message) {
  if(message->message!=WM_KEYDOWN || !IsWindowEnabled(g.window) || !(GetKeyState(VK_CONTROL)&0x8000) ||
      (GetKeyState(VK_SHIFT)&0x8000) || (message->hwnd!=g.window && !IsChild(g.window,message->hwnd))) return 0;
  if(message->wParam=='L') { compact_switch(0);return 1; }
  if(message->wParam=='O') { compact_import();return 1; }
  return 0;
}
