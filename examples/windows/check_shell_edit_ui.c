/* SPDX-License-Identifier: MIT */
/* Production HWND input, DirectWrite geometry and atomic save paths.
   Physical Microsoft Pinyin input requires visible-window verification. */
#define WinMain reader_WinMain
#include "../reader.c"
#undef WinMain
#include <assert.h>

static void same(const char *text) {
  assert(editor.model.size==strlen(text));
  assert(!memcmp(editor.model.text,text,strlen(text)+1));
}
static void key(UINT code,int shift,int control) {
  BYTE saved[256],state[256]; assert(GetKeyboardState(saved)); memcpy(state,saved,sizeof(state));
  memset(state,0,sizeof(state)); state[VK_SHIFT]=shift ? 0x80:0; state[VK_CONTROL]=control ? 0x80:0;
  assert(SetKeyboardState(state)); SendMessageW(g.page,WM_KEYDOWN,code,1); assert(SetKeyboardState(saved));
}
static void type(const wchar_t *text) {
  for (;*text;text++) SendMessageW(g.page,WM_CHAR,*text,1);
}
static void snapshot(const wchar_t *directory,const wchar_t *name) {
  wchar_t path[HOST_PATH]; path_join(path,HOST_PATH,directory,name);
  assert(edit_atomic_write(path,editor.model.text,editor.model.size));
}
static void clipboard(const wchar_t *text) {
  size_t bytes=(wcslen(text)+1)*sizeof(*text);
  HGLOBAL data=GlobalAlloc(GMEM_MOVEABLE,bytes); assert(data);
  void *target=GlobalLock(data); assert(target); memcpy(target,text,bytes); GlobalUnlock(data);
  assert(OpenClipboard(g.window)); assert(EmptyClipboard()); assert(SetClipboardData(CF_UNICODETEXT,data)); CloseClipboard();
}
static int dialog_choice,dialog_count;
static DWORD dialog_started;
static int dialog_logged;
static BOOL CALLBACK log_child(HWND child,LPARAM unused) {
  (void)unused;
  wchar_t name[128]; GetWindowTextW(child,name,128); char *text=host_utf8(name);
  fprintf(stderr,"CHILD %d %s\n",GetDlgCtrlID(child),text ? text:""); free(text); return TRUE;
}
static BOOL CALLBACK answer_dialog(HWND window,LPARAM unused) {
  (void)unused;
  wchar_t name[32]; GetClassNameW(window,name,32);
  if (!dialog_count && !wcscmp(name,L"#32770") && GetWindow(window,GW_OWNER)==g.window) {
    if (!dialog_logged) {
      wchar_t title[128]; GetWindowTextW(window,title,128); char *text=host_utf8(title);
      fprintf(stderr,"DIALOG choice=%d title=%s\n",dialog_choice,text ? text:""); free(text);
      EnumChildWindows(window,log_child,0); dialog_logged=1;
    }
    int button=dialog_choice;
    /* A single native OK button may expose IDCANCEL (it also handles Esc). */
    if (button==IDOK && !GetDlgItem(window,IDOK)) button=IDCANCEL;
    if (!GetDlgItem(window,button)) return TRUE;
    if (dialog_choice!=IDOK) {
      assert(GetDlgItem(window,IDYES)); assert(GetDlgItem(window,IDNO)); assert(GetDlgItem(window,IDCANCEL));
    }
    dialog_count++;
    PostMessageW(window,WM_COMMAND,MAKEWPARAM(button,BN_CLICKED),(LPARAM)GetDlgItem(window,button));
  }
  return TRUE;
}
static void CALLBACK dialog_tick(HWND window,UINT message,UINT_PTR id,DWORD time) {
  (void)window; (void)message; (void)id; (void)time;
  assert(GetTickCount()-dialog_started<10000);
  EnumThreadWindows(GetCurrentThreadId(),answer_dialog,0);
}
static UINT_PTR expect_dialog(int choice) {
  dialog_choice=choice; dialog_count=0; dialog_logged=0; dialog_started=GetTickCount();
  UINT_PTR timer=SetTimer(NULL,0,50,dialog_tick); assert(timer); return timer;
}
static void dialog_done(UINT_PTR timer) { assert(KillTimer(NULL,timer)); assert(dialog_count==1); }
int main(int argc,char **argv) {
  if (argc==3 && !strcmp(argv[1],"--reopen")) {
    wchar_t *directory=host_wide(argv[2],strlen(argv[2])),path[HOST_PATH]; assert(directory);
    path_join(path,HOST_PATH,directory,L"roundtrip.docx");
    assert(edit_load(&editor.model,path)==EXR_OK); snapshot(directory,L"process-after-reopen.utf8");
    edit_model_free(&editor.model); free(directory); puts("PASS: fresh-process DOCX reopen"); return 0;
  }
  assert(argc==2); setvbuf(stdout,NULL,_IONBF,0);
  SetErrorMode(SEM_FAILCRITICALERRORS|SEM_NOGPFAULTERRORBOX);
  SetProcessDPIAware(); assert(SUCCEEDED(OleInitialize(NULL)));
  wchar_t *directory=host_wide(argv[1],strlen(argv[1])); assert(directory);
  g.window=CreateWindowW(L"STATIC",L"Editor check",WS_OVERLAPPEDWINDOW,-32000,-32000,900,700,NULL,NULL,NULL,NULL);
  assert(g.window);
  WNDCLASSW wc={0}; wc.lpfnWndProc=page_procedure; wc.lpszClassName=L"EditorCheckPage";
  assert(RegisterClassW(&wc));
  g.page=CreateWindowW(wc.lpszClassName,L"",WS_CHILD,0,0,860,600,g.window,NULL,NULL,NULL); assert(g.page);
  assert(SUCCEEDED(shell_d2d_create(g.window,&host_shell)));
  shell_active=1; shell_dpi=96; shell_font=20; g.zoom_percent=100;
  copy_wstring(g.font_family,128,L"Arial"); shell_edit_create(g.window);
  edit_model empty={0}; void *package=NULL; size_t package_size=0; wchar_t empty_path[HOST_PATH];
  assert(exr_edit_doc_create(NULL,0,NULL,0,NULL,0,NULL,&empty.doc)==EXR_OK);
  assert(edit_export_docx(&empty,&package,&package_size)==EXR_OK);
  path_join(empty_path,HOST_PATH,directory,L"empty.docx"); assert(edit_atomic_write(empty_path,package,package_size));
  exr_free(package); edit_model_free(&empty);
  assert(edit_load(&empty,empty_path)==EXR_OK); assert(empty.count==1 && empty.size==0);
  assert(edit_replace(&empty,0,0,"x",1,0)==EXR_OK); assert(edit_history_move(&empty,0)==EXR_OK); assert(!empty.size);
  edit_model_free(&empty);
  assert(edit_seed(&editor.model,"",0)==EXR_OK); assert(shell_edit_relayout());
  type(L"ignored"); same(""); assert(!editor.enabled); shell_edit_toggle(); assert(editor.enabled);
  SendMessageW(g.page,WM_CHAR,L'x',5); same("xxxxx"); key('Z',0,1); same("");
  type(L"0123456789"); same("0123456789"); assert(editor.model.tx);
  key('Z',0,1); same(""); assert(!edit_dirty(&editor.model));
  snapshot(directory,L"cjk-hwnd-before.utf8");
  type(L"\u4f60\u597d\u4e16\u754c"); same("\xe4\xbd\xa0\xe5\xa5\xbd\xe4\xb8\x96\xe7\x95\x8c");
  snapshot(directory,L"cjk-hwnd-wmchar.utf8");
  key('Z',0,1); same(""); snapshot(directory,L"cjk-hwnd-one-ctrl-z.utf8");
  puts("PASS (not physical IME): HWND WM_CHAR CJK before=empty result=你好世界 one Ctrl+Z=empty");
  type(L"0123456789"); key('Z',0,1); same("");
  key('Y',0,1); same("0123456789");
  MSG tab={0}; tab.hwnd=g.page; tab.message=WM_KEYDOWN; tab.wParam=VK_TAB;
  assert(!(SendMessageW(g.page,WM_GETDLGCODE,VK_TAB,(LPARAM)&tab)&DLGC_WANTTAB));
  assert(!shell_edit_translate(&tab)); same("0123456789");
  key(VK_HOME,0,0); assert(editor.model.selection.focus==0);
  key(VK_RIGHT,0,0); assert(editor.model.selection.focus==1);
  key(VK_LEFT,0,0); assert(editor.model.selection.focus==0);
  key(VK_END,0,0); assert(editor.model.selection.focus==10);
  key(VK_BACK,0,0); same("012345678");
  key(VK_HOME,0,0); key(VK_DELETE,0,0); same("12345678");
  puts("PASS: Tab delegated without text mutation; Home=0 Right=1 Left=0 End=10; Backspace=012345678 Delete=12345678");
  key('A',0,1); key(VK_DELETE,0,0); same("");
  type(L"A\U0001f600e\u0301");
  key(VK_BACK,0,0); same("A\xf0\x9f\x98\x80");
  key(VK_LEFT,1,0); assert(editor.model.selection.anchor-editor.model.selection.focus==4);
  key(VK_DELETE,0,0); same("A"); key(VK_RETURN,0,0); type(L"B"); same("A\nB");
  key(VK_HOME,0,0); key(VK_BACK,0,0); same("AB"); key('Z',0,1); same("A\nB");
  key('A',0,1); clipboard(L"first\r\n\r\n\u4f60\u597d\u4e16\u754c\rfinal"); key('V',0,1);
  same("first\n\n\xe4\xbd\xa0\xe5\xa5\xbd\xe4\xb8\x96\xe7\x95\x8c\nfinal");
  assert(editor.model.count==4); key('A',0,1); key('C',0,1); assert(clipboard_contains("\r\n\r\n"));
  key('X',0,1); same(""); key('Z',0,1); assert(editor.model.count==4);
  key(VK_HOME,0,1); key(VK_DOWN,0,0); assert(editor.model.selection.focus==6);
  float box[4]; assert(edit_caret_box(box));
  assert(edit_byte_at(&editor.model,shell_edit_view_hit(editor.view,box[0],box[1]+box[3]*.4f))==editor.model.selection.focus);
  size_t block=edit_span_at(&editor.model,editor.model.selection.focus);
  assert(exr_edit_find_block(editor.model.doc,editor.model.spans[block].id));
  float first[4],last[4];
  assert(SUCCEEDED(shell_edit_view_caret(editor.view,0,first)));
  assert(SUCCEEDED(shell_edit_view_caret(editor.view,5,last)));
  SendMessageW(g.page,WM_LBUTTONDOWN,MK_LBUTTON,MAKELPARAM((int)(editor.left+first[0]),(int)(editor.top+first[1]+first[3]*.4f)));
  SendMessageW(g.page,WM_MOUSEMOVE,MK_LBUTTON,MAKELPARAM((int)lroundf(editor.left+last[0]),(int)(editor.top+last[1]+last[3]*.4f)));
  SendMessageW(g.page,WM_LBUTTONUP,0,MAKELPARAM((int)lroundf(editor.left+last[0]),(int)(editor.top+last[1]+last[3]*.4f)));
  assert(editor.model.selection.anchor==0 && editor.model.selection.focus==5 && !editor.drag);
  g.zoom_percent=200; shell_dpi=144; assert(shell_edit_relayout());
  float scaled[4]; assert(edit_caret_box(scaled)); assert(fabsf(scaled[3]/box[3]-3)<.02f);
  /* Preview occupies layout only, including replacement of a selection. */
  char *before=host_strdup(editor.model.text); assert(before);
  editor.composing=1; editor.composition=_wcsdup(L"nihao"); editor.composition_size=5; editor.composition_cursor=2;
  assert(shell_edit_relayout()); same(before); assert(wcsstr(editor.display,L"nihao"));
  IMECHARPOSITION query={0}; query.dwSize=sizeof(query); query.dwCharPos=2;
  assert(SendMessageW(g.page,WM_IME_REQUEST,IMR_QUERYCHARPOSITION,(LPARAM)&query));
  assert(query.cLineHeight==(UINT)ceilf(scaled[3]));
  float composing_box[4]; assert(edit_caret_box(composing_box));
  POINT expected_position={(LONG)lroundf(editor.left+composing_box[0]),(LONG)lroundf(editor.top+composing_box[1]-editor.scroll)};
  assert(ClientToScreen(g.page,&expected_position));
  assert(query.pt.x==expected_position.x && query.pt.y==expected_position.y);
  query.dwCharPos=6; assert(!SendMessageW(g.page,WM_IME_REQUEST,IMR_QUERYCHARPOSITION,(LPARAM)&query));
  edit_cancel_composition(); assert(shell_edit_relayout()); same(before); free(before);
  snapshot(directory,L"ui-before-save.utf8");
  path_join(editor.path,HOST_PATH,directory,L"roundtrip.docx"); assert(shell_edit_save(0));
  assert(!edit_dirty(&editor.model)); assert(shell_edit_open(editor.path)); assert(!editor.enabled);
  snapshot(directory,L"ui-after-reopen.utf8");
  shell_edit_toggle(); key(VK_END,0,1);
  snapshot(directory,L"ui-undo-before.utf8");
  for (int i=0;i<20;i++) { type(L"x"); key(VK_RIGHT,0,0); }
  snapshot(directory,L"ui-redo-before.utf8");
  for (int i=0;i<20;i++) key('Z',0,1);
  snapshot(directory,L"ui-undo-after.utf8");
  for (int i=0;i<20;i++) key('Z',1,1);
  snapshot(directory,L"ui-redo-after.utf8");
  assert(editor.model.cursor==20);
  /* Failed saves leave the document dirty and do not alter the saved file. */
  const wchar_t *invalid=L"?:\\missing\\file.txt";
  assert(!edit_atomic_write(invalid,"bad",3)); assert(edit_dirty(&editor.model));
  UINT_PTR hook=expect_dialog(IDCANCEL); assert(!shell_edit_before_close()); dialog_done(hook); assert(edit_dirty(&editor.model));
  hook=expect_dialog(IDNO); assert(shell_edit_before_close()); dialog_done(hook); assert(edit_dirty(&editor.model));
  wchar_t protected_path[HOST_PATH]; copy_wstring(protected_path,HOST_PATH,editor.path);
  HANDLE locked=CreateFileW(protected_path,GENERIC_READ,FILE_SHARE_READ,NULL,OPEN_EXISTING,0,NULL); assert(locked!=INVALID_HANDLE_VALUE);
  hook=expect_dialog(IDOK); assert(!shell_edit_save(0)); dialog_done(hook); assert(edit_dirty(&editor.model));
  CloseHandle(locked);
  edit_model disk={0}; assert(edit_load(&disk,protected_path)==EXR_OK);
  assert(!strcmp(disk.text,editor.model.saved)); edit_model_free(&disk);
  path_join(editor.path,HOST_PATH,directory,L"close-save.docx");
  hook=expect_dialog(IDYES); assert(shell_edit_before_close()); dialog_done(hook); assert(!edit_dirty(&editor.model));
  shell_edit_destroy(); shell_d2d_destroy(host_shell); host_shell=NULL;
  DestroyWindow(g.window); free(directory); OleUninitialize();
  puts("PASS: readonly switch; WM_CHAR burst; keys/graphemes; clipboard paragraphs; hit-test/drag; DPI/zoom; preview isolation/IME coordinates; DOCX save/reopen; 20 HWND undo/redo; close save/discard/cancel; locked-file preservation");
  return 0;
}
