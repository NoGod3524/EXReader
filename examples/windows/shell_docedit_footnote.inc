/* SPDX-License-Identifier: MIT */
/* Footer rows and their native multiline editor mutate the same engine model. */
static int de_footnote_find(exr_edit_id id,exr_edit_footnote *note) {
  size_t count=exr_edit_footnote_count(de.doc);
  for(size_t i=0;i<count;i++)
    if(exr_edit_footnote_at(de.doc,i,note)==EXR_OK && note->id==id)return 1;
  return 0;
}
static void de_footnote_changed(void) {
  de_set_caret(de_normalize(de_caret_pos()));de_set_anchor(de_caret_pos());
  de.dirty=1;de.layout_dirty=1;de_refresh(0);
}
static int de_footnote_update(exr_edit_id id,const char *text,size_t size) {
  exr_status status=exr_edit_footnote_set_text(de.doc,id,text,size);
  if(status!=EXR_OK) {set_status(L"无法修改脚注。");return 0;}
  de_footnote_changed();return 1;
}
static int de_footnote_remove(exr_edit_id id) {
  exr_status status=exr_edit_footnote_delete(de.doc,id);
  if(status!=EXR_OK) {set_status(L"无法删除脚注。");return 0;}
  de_footnote_changed();return 1;
}
typedef struct { HWND text;exr_edit_id id; } de_note_panel;
static de_note_panel de_np;
enum { DE_NOTE_TEXT=610,DE_NOTE_SAVE,DE_NOTE_DELETE,DE_NOTE_CANCEL };
static int de_footnote_flush(void) {
  int count=GetWindowTextLengthW(de_np.text);
  wchar_t *wide=calloc((size_t)count+1,sizeof(*wide));if(!wide)return 0;
  GetWindowTextW(de_np.text,wide,count+1);
  int size=WideCharToMultiByte(CP_UTF8,WC_ERR_INVALID_CHARS,wide,count,NULL,0,NULL,NULL);
  if(count && !size) {free(wide);return 0;}
  char *text=calloc((size_t)size+1,1);if(!text) {free(wide);return 0;}
  if(size)WideCharToMultiByte(CP_UTF8,WC_ERR_INVALID_CHARS,wide,count,text,size,NULL,NULL);
  free(wide);size_t length=0;
  for(int i=0;i<size;i++)if(text[i]!='\r')text[length++]=text[i];
  int ok=de_footnote_update(de_np.id,text,length);free(text);return ok;
}
static LRESULT CALLBACK de_footnote_proc(HWND window,UINT message,WPARAM wp,LPARAM lp) {
  if(message==WM_COMMAND && HIWORD(wp)==BN_CLICKED) {
    int id=LOWORD(wp);
    if(id==DE_NOTE_CANCEL || (id==DE_NOTE_SAVE && de_footnote_flush()) ||
      (id==DE_NOTE_DELETE && de_footnote_remove(de_np.id)))DestroyWindow(window);
    return 0;
  }
  if(message==WM_CLOSE) {DestroyWindow(window);return 0;}
  return DefWindowProcW(window,message,wp,lp);
}
static void de_footnote_open(exr_edit_id id) {
  exr_edit_footnote note={0};if(!g.window || !de_footnote_find(id,&note))return;
  wchar_t *text=host_wide(note.text ? note.text:"",note.text_size);if(!text)return;
  WNDCLASSW wc={0};wc.lpfnWndProc=de_footnote_proc;wc.hInstance=GetModuleHandleW(NULL);
  wc.lpszClassName=L"EXReaderFootnoteEditor";wc.hCursor=LoadCursor(NULL,IDC_ARROW);
  wc.hbrBackground=(HBRUSH)(COLOR_WINDOW+1);RegisterClassW(&wc);
  wchar_t title[80];swprintf(title,80,L"脚注 %zu",note.number);
  HWND window=CreateWindowExW(WS_EX_DLGMODALFRAME,wc.lpszClassName,title,
    WS_OVERLAPPED|WS_CAPTION|WS_SYSMENU,CW_USEDEFAULT,CW_USEDEFAULT,580,300,
    g.window,NULL,wc.hInstance,NULL);
  if(!window) {free(text);return;}
  de_np.id=id;
  de_np.text=CreateWindowExW(WS_EX_CLIENTEDGE,L"EDIT",text,WS_CHILD|WS_VISIBLE|WS_TABSTOP|
    ES_MULTILINE|ES_WANTRETURN|ES_AUTOVSCROLL|WS_VSCROLL,12,12,540,195,
    window,(HMENU)(INT_PTR)DE_NOTE_TEXT,wc.hInstance,NULL);free(text);
  SendMessageW(de_np.text,EM_SETLIMITTEXT,1024*1024,0);
  const wchar_t *labels[]={L"保存",L"删除脚注",L"取消"};
  for(int i=0;i<3;i++) {
    HWND button=CreateWindowW(L"BUTTON",labels[i],WS_CHILD|WS_VISIBLE|WS_TABSTOP,
      222+i*112,220,104,30,window,(HMENU)(INT_PTR)(DE_NOTE_SAVE+i),wc.hInstance,NULL);
    SendMessageW(button,WM_SETFONT,(WPARAM)GetStockObject(DEFAULT_GUI_FONT),TRUE);
  }
  if(!de_np.text) {DestroyWindow(window);return;}
  SendMessageW(de_np.text,WM_SETFONT,(WPARAM)GetStockObject(DEFAULT_GUI_FONT),TRUE);
  EnableWindow(g.window,FALSE);ShowWindow(window,SW_SHOW);SetFocus(de_np.text);
  MSG msg;int result=1;
  while(IsWindow(window) && (result=GetMessageW(&msg,NULL,0,0))>0) {
    if(msg.message==WM_KEYDOWN && msg.wParam==VK_ESCAPE) {DestroyWindow(window);continue;}
    if(msg.message==WM_KEYDOWN && msg.wParam=='S' && (GetKeyState(VK_CONTROL)&0x8000)) {
      if(de_footnote_flush()) {de_save();DestroyWindow(window);}continue;
    }
    if(!IsDialogMessageW(window,&msg)) {TranslateMessage(&msg);DispatchMessageW(&msg);}
  }
  if(IsWindow(window))DestroyWindow(window);
  if(result==0)PostQuitMessage((int)msg.wParam);
  memset(&de_np,0,sizeof(de_np));EnableWindow(g.window,TRUE);SetFocus(g.page);de_refresh(0);
}
static int de_footnote_insert(void) {
  de_pos p=de_normalize(de_caret_pos());const exr_edit_block *b=de_block_at(de.doc,p.block);
  if(!b || b->kind!=EXR_EDIT_PARAGRAPH)return 0;
  exr_edit_id id=0;
  if(exr_edit_footnote_insert(de.doc,b->id,p.run,p.byte,"",0,&id)!=EXR_OK) {
    set_status(L"无法在此处插入脚注。");return 0;
  }
  exr_edit_footnote note={0};
  if(de_footnote_find(id,&note)) {p.run=note.run_index+1;p.byte=0;de_set_caret(de_normalize(p));}
  de_footnote_changed();de_footnote_open(id);return 1;
}
static int de_footnote_click(float x,float y) {
  if(x<de.inset || x>de.width-shell_px(24,shell_dpi) || y<de_toolbar_height())return 0;
  y+=de.scroll_y;
  for(size_t i=1;i<de.footnote_row_count;i++) {
    const shell_d2d_edit_row *row=&de.rows[de.row_count+i];
    if(y>=row->y && y<row->y+row->height) {
      exr_edit_footnote note={0};
      if(exr_edit_footnote_at(de.doc,i-1,&note)==EXR_OK)de_footnote_open(note.id);
      return 1;
    }
  }
  return 0;
}
