/* SPDX-License-Identifier: MIT */
/* Explicit host editing mode. Exact bytes and transactions live in #119;
   DirectWrite supplies Windows caret/selection geometry without normalizing
   typed whitespace or throwing away empty paragraphs. */
#include <imm.h>
#include "shell_edit_model.inc"

enum { EDIT_MODE=0x6600,EDIT_OPEN,EDIT_SAVE,EDIT_SAVE_AS,EDIT_UNDO,EDIT_REDO,
  EDIT_CUT,EDIT_COPY,EDIT_PASTE,EDIT_ALL,EDIT_BLINK=0x6630,EDIT_BATCH };
static struct {
  edit_model model;
  shell_edit_view *view;
  wchar_t *display,*composition;
  unsigned display_size,composition_size,composition_cursor;
  wchar_t path[HOST_PATH];
  int enabled,composing,drag,blink,caret_created;
  wchar_t surrogate;
  float scroll,left,top,font_size,goal_x;
  int goal_valid;
  unsigned dpi;
  int zoom;
  int64_t book_id;
  HMENU menu;
} editor;

static int shell_edit_loaded(void) { return editor.model.doc!=NULL; }
static const wchar_t *shell_edit_name(void) {
  const wchar_t *name=wcsrchr(editor.path,L'\\'); name=name ? name+1:editor.path;
  return *name ? name:L"未命名文档";
}
static unsigned edit_utf16_at(const edit_model *m,size_t offset) {
  if (!offset) return 0;
  int n=MultiByteToWideChar(CP_UTF8,MB_ERR_INVALID_CHARS,m->text,(int)min(offset,m->size),NULL,0);
  return n>0 ? (unsigned)n:0;
}
static size_t edit_byte_at(const edit_model *m,unsigned offset) {
  size_t at=0; unsigned units=0;
  while (at<m->size && units<offset) {
    unsigned char c=(unsigned char)m->text[at];
    size_t n=c<0x80 ? 1:c<0xe0 ? 2:c<0xf0 ? 3:4;
    unsigned step=n==4 ? 2:1;
    if (units+step>offset) break;
    units+=step; at+=n;
  }
  while (at && !(m->boundaries[at]&EXR_BOUNDARY_GRAPHEME)) at--;
  return at;
}
static void shell_edit_title(void) {
  if (!editor.model.doc) return;
  wchar_t title[HOST_PATH+80];
  swprintf(title,HOST_PATH+80,L"%ls%ls — EXReader [%ls]",edit_dirty(&editor.model) ? L"* ":L"",
    shell_edit_name(),editor.enabled ? L"编辑":L"阅读");
  SetWindowTextW(g.window,title);
  CheckMenuItem(editor.menu,EDIT_MODE,MF_BYCOMMAND|(editor.enabled ? MF_CHECKED:MF_UNCHECKED));
}
static void edit_error(exr_status status) {
  wchar_t message[160];
  swprintf(message,160,status==EXR_UNSUPPORTED ? L"此处包含不能编辑的表格或对象。":L"编辑未完成（%d）。",(int)status);
  set_status(message); MessageBeep(MB_ICONWARNING);
}
static int edit_caret_box(float box[4]) {
  unsigned position=edit_utf16_at(&editor.model,editor.model.selection.focus);
  if (editor.composing) position=edit_utf16_at(&editor.model,
    min(editor.model.selection.anchor,editor.model.selection.focus))+editor.composition_cursor;
  return editor.view && SUCCEEDED(shell_edit_view_caret(editor.view,position,box));
}
static void edit_native_caret(void) {
  if (editor.caret_created) DestroyCaret();
  editor.caret_created=0;
  if (editor.enabled && GetFocus()==g.page)
    editor.caret_created=CreateCaret(g.page,NULL,max(1,shell_px(1,shell_dpi)),max(1,(int)ceilf(editor.font_size*1.75f)));
}
static void edit_ime_position(void) {
  float box[4];
  if (!editor.enabled || !edit_caret_box(box)) return;
  POINT point={(LONG)lroundf(editor.left+box[0]),(LONG)lroundf(editor.top+box[1]-editor.scroll)};
  if (editor.caret_created) SetCaretPos(point.x,point.y);
  HIMC context=ImmGetContext(g.page);
  if (context) {
    COMPOSITIONFORM form={0}; form.dwStyle=CFS_POINT; form.ptCurrentPos=point;
    ImmSetCompositionWindow(context,&form);
    CANDIDATEFORM candidate={0}; candidate.dwStyle=CFS_EXCLUDE;
    candidate.ptCurrentPos=point;
    candidate.rcArea=(RECT){point.x,point.y,point.x+max(1,shell_px(1,shell_dpi)),point.y+(LONG)ceilf(box[3])};
    ImmSetCandidateWindow(context,&candidate);
    LOGFONTW font={0}; font.lfHeight=-(LONG)lroundf(editor.font_size);
    copy_wstring(font.lfFaceName,LF_FACESIZE,g.font_family);
    ImmSetCompositionFontW(context,&font); ImmReleaseContext(g.page,context);
  }
}
static void edit_blink_reset(void) {
  editor.blink=1;
  if (editor.enabled && GetFocus()==g.page) SetTimer(g.page,EDIT_BLINK,500,NULL);
  else KillTimer(g.page,EDIT_BLINK);
  edit_ime_position(); InvalidateRect(g.page,NULL,FALSE);
}
static void edit_keep_visible(void) {
  RECT area; float box[4]; GetClientRect(g.page,&area);
  if (!edit_caret_box(box)) return;
  float height=max(1,area.bottom-(int)(2*editor.top));
  if (box[1]<editor.scroll) editor.scroll=box[1];
  if (box[1]+box[3]>editor.scroll+height) editor.scroll=box[1]+box[3]-height;
  editor.scroll=max(0,editor.scroll);
  edit_ime_position();
}
static int shell_edit_relayout(void) {
  if (!editor.model.doc || !host_shell || !g.page) return 0;
  float previous_size=editor.font_size;
  RECT area; GetClientRect(g.page,&area);
  editor.dpi=shell_dpi; editor.zoom=g.zoom_percent ? g.zoom_percent:100;
  editor.left=(float)shell_px(40,shell_dpi); editor.top=(float)shell_px(28,shell_dpi);
  editor.font_size=shell_font*shell_dpi/96.f*editor.zoom/100.f;
  wchar_t *plain=host_wide(editor.model.text,editor.model.size);
  if (!plain) return 0;
  unsigned length=(unsigned)wcslen(plain);
  unsigned a=edit_utf16_at(&editor.model,min(editor.model.selection.anchor,editor.model.selection.focus));
  unsigned b=edit_utf16_at(&editor.model,max(editor.model.selection.anchor,editor.model.selection.focus));
  unsigned used=editor.composing ? length-(b-a)+editor.composition_size:length;
  wchar_t *display=calloc((size_t)used+1,sizeof(*display));
  if (!display) { free(plain); return 0; }
  if (editor.composing) {
    memcpy(display,plain,a*sizeof(*plain));
    if (editor.composition_size) memcpy(display+a,editor.composition,editor.composition_size*sizeof(*plain));
    memcpy(display+a+editor.composition_size,plain+b,(length-b)*sizeof(*plain));
  } else memcpy(display,plain,length*sizeof(*plain));
  free(plain);
  shell_edit_view *view=NULL;
  HRESULT hr=shell_edit_view_create(host_shell,display,used,g.font_family,editor.font_size,
    max(40.f,area.right-2*editor.left),&view);
  if (FAILED(hr)) { free(display); return 0; }
  shell_edit_view_free(editor.view); free(editor.display);
  editor.view=view; editor.display=display; editor.display_size=used;
  if (previous_size!=editor.font_size) edit_native_caret();
  edit_keep_visible(); edit_blink_reset(); return 1;
}
static void edit_changed(exr_status status) {
  if (status!=EXR_OK) edit_error(status);
  editor.goal_valid=0;
  if (!shell_edit_relayout()) set_status(L"无法排版编辑内容；请保存后重试。");
  shell_edit_title();
}
static int edit_complete_composition(void) {
  if (!editor.composing) return 1;
  HIMC context=ImmGetContext(g.page);
  if (context) { ImmNotifyIME(context,NI_COMPOSITIONSTR,CPS_COMPLETE,0); ImmReleaseContext(g.page,context); }
  return !editor.composing;
}
static void edit_cancel_composition(void) {
  if (editor.composing) {
    HIMC context=ImmGetContext(g.page);
    if (context) { ImmNotifyIME(context,NI_COMPOSITIONSTR,CPS_CANCEL,0); ImmReleaseContext(g.page,context); }
  }
  editor.composing=0; free(editor.composition); editor.composition=NULL;
  editor.composition_size=editor.composition_cursor=0;
}
static int edit_read_file(const wchar_t *path,void **out,size_t *size) {
  *out=NULL; *size=0;
  FILE *file=_wfopen(path,L"rb");
  if (!file) return 0;
  int okay=!_fseeki64(file,0,SEEK_END); __int64 length=okay ? _ftelli64(file):-1;
  if (length<0 || (uint64_t)length>HOST_IMPORT_LIMIT) okay=0;
  void *data=okay ? malloc((size_t)length+1):NULL;
  if (!data) okay=0;
  if (okay) { rewind(file); okay=fread(data,1,(size_t)length,file)==(size_t)length; }
  if (fclose(file)) okay=0;
  if (!okay) { free(data); return 0; }
  ((char *)data)[length]=0; *out=data; *size=(size_t)length; return 1;
}
static char *edit_normalize_wide(const wchar_t *text,size_t count) {
  if (count>EDIT_LIMIT) return NULL;
  wchar_t *clean=malloc((count+1)*sizeof(*clean)); size_t n=0;
  if (!clean) return NULL;
  for (size_t i=0;i<count;i++) {
    if (!text[i]) { free(clean); return NULL; }
    if (text[i]==L'\r') { clean[n++]=L'\n'; if (i+1<count && text[i+1]==L'\n') i++; }
    else clean[n++]=text[i];
  }
  clean[n]=0;
  int bytes=WideCharToMultiByte(CP_UTF8,WC_ERR_INVALID_CHARS,clean,(int)n,NULL,0,NULL,NULL);
  char *result=bytes>=0 && (bytes || !n) ? malloc((size_t)bytes+1):NULL;
  if (result) { WideCharToMultiByte(CP_UTF8,WC_ERR_INVALID_CHARS,clean,(int)n,result,bytes,NULL,NULL); result[bytes]=0; }
  free(clean); return result;
}
static exr_status edit_load(edit_model *model,const wchar_t *path) {
  void *data=NULL; size_t size=0; exr_status status=EXR_IO; exr_document *document=NULL;
  if (!edit_read_file(path,&data,&size)) return EXR_IO;
  const wchar_t *extension=wcsrchr(path,L'.');
  if (extension && !_wcsicmp(extension,L".txt")) {
    wchar_t *wide=NULL; size_t count=0;
    if (size>=2 && ((unsigned char *)data)[0]==0xff && ((unsigned char *)data)[1]==0xfe && !(size&1)) {
      count=(size-2)/2; wide=calloc(count+1,sizeof(*wide)); if (wide) memcpy(wide,(char *)data+2,count*2);
    } else {
      size_t bom=size>=3 && !memcmp(data,"\xef\xbb\xbf",3) ? 3:0;
      wide=host_wide((char *)data+bom,size-bom);
      if (wide && !memchr((char *)data+bom,0,size-bom)) count=wcslen(wide);
      else { free(wide); wide=NULL; }
    }
    char *text=wide ? edit_normalize_wide(wide,count):NULL;
    if (text) status=edit_seed(model,text,strlen(text)); else status=EXR_ENCODING;
    free(text); free(wide);
  } else if (extension && !_wcsicmp(extension,L".docx")) {
#ifdef EXR_READER_WINDOWS_EDIT_DOCX
    exr_edit_options options={EDIT_HISTORY};
    status=exr_edit_docx_read(data,size,&options,&model->doc,NULL);
    if (status==EXR_OK && !exr_edit_block_count(model->doc)) {
      exr_edit_id id=0;
      status=exr_edit_insert_paragraph(model->doc,0,NULL,0,NULL,&id);
    }
    if (status==EXR_OK) status=edit_refresh(model);
    if (status==EXR_OK && !edit_mark_saved(model)) status=EXR_MEMORY;
#else
    status=exr_document_open_memory(EXR_DOCX,data,size,&document,NULL);
    size_t bytes=0; const char *text=exr_document_text(document,&bytes);
    if (status==EXR_OK) status=edit_seed(model,text,bytes);
#endif
  } else status=EXR_UNSUPPORTED;
  exr_document_free(document); free(data); return status;
}
static int edit_atomic_write(const wchar_t *path,const void *data,size_t size) {
  static unsigned sequence;
  wchar_t temporary[HOST_PATH];
  if (wcslen(path)>HOST_PATH-64) return 0;
  swprintf(temporary,HOST_PATH,L"%ls.exr-%lu-%u.tmp",path,(unsigned long)GetCurrentProcessId(),++sequence);
  HANDLE file=CreateFileW(temporary,GENERIC_WRITE,0,NULL,CREATE_NEW,FILE_ATTRIBUTE_NORMAL,NULL);
  if (file==INVALID_HANDLE_VALUE) return 0;
  int okay=1; size_t at=0;
  while (okay && at<size) {
    DWORD written=0,chunk=(DWORD)min(size-at,1024*1024);
    okay=WriteFile(file,(const char *)data+at,chunk,&written,NULL) && written==chunk; at+=written;
  }
  if (okay) okay=FlushFileBuffers(file)!=0;
  if (!CloseHandle(file)) okay=0;
  if (okay) {
    DWORD attributes=GetFileAttributesW(path);
    okay=attributes!=INVALID_FILE_ATTRIBUTES ? ReplaceFileW(path,temporary,NULL,0,NULL,NULL)!=0:
      MoveFileExW(temporary,path,MOVEFILE_WRITE_THROUGH)!=0;
  }
  if (!okay) DeleteFileW(temporary);
  return okay;
}
static exr_status edit_export_docx(edit_model *m,void **data,size_t *size) {
#ifdef EXR_READER_WINDOWS_EDIT_DOCX
  return exr_edit_docx_write(m->doc,data,size,NULL);
#else
  /* #118's text-profile exporter is the compatibility path until X1 is in the
     installed SDK. Never label its normalized projection as a lossless save. */
  exr_document *projection=NULL;
  exr_status status=exr_document_open_memory(EXR_TXT,m->text,m->size,&projection,NULL);
  size_t normalized_size=0;
  const char *normalized=exr_document_text(projection,&normalized_size);
  if (status==EXR_OK && (normalized_size!=m->size || memcmp(normalized,m->text,m->size))) status=EXR_UNSUPPORTED;
  if (status==EXR_OK) status=exr_document_export(projection,EXR_DOCX,data,size,NULL);
  exr_document_free(projection); return status;
#endif
}
static int shell_edit_save(int save_as) {
  if (!editor.model.doc || !edit_complete_composition()) return 0;
  if (edit_finish(&editor.model)!=EXR_OK) return 0;
  wchar_t path[HOST_PATH]; copy_wstring(path,HOST_PATH,editor.path);
  if (save_as || !path[0]) {
    OPENFILENAMEW dialog={0}; dialog.lStructSize=sizeof(dialog); dialog.hwndOwner=g.window;
    dialog.lpstrFilter=L"Word document (*.docx)\0*.docx\0UTF-8 text (*.txt)\0*.txt\0\0";
    dialog.lpstrFile=path; dialog.nMaxFile=HOST_PATH; dialog.lpstrDefExt=L"docx";
    dialog.lpstrTitle=L"另存文档"; dialog.Flags=OFN_OVERWRITEPROMPT|OFN_PATHMUSTEXIST|OFN_NOCHANGEDIR;
    if (!GetSaveFileNameW(&dialog)) return 0;
  }
  const wchar_t *extension=wcsrchr(path,L'.');
  void *data=NULL; size_t size=0; exr_status status=EXR_UNSUPPORTED;
  int text=extension && !_wcsicmp(extension,L".txt");
  if (text) { data=editor.model.text; size=editor.model.size; status=EXR_OK; }
  else if (extension && !_wcsicmp(extension,L".docx")) status=edit_export_docx(&editor.model,&data,&size);
  /* Allocate the saved marker before touching the file, so allocation failure
     cannot falsely report that a completed disk replacement was unsaved. */
  char *saved=status==EXR_OK ? malloc(editor.model.size+1):NULL;
  if (saved) memcpy(saved,editor.model.text,editor.model.size+1);
  if (status==EXR_OK && !saved) status=EXR_MEMORY;
  if (status==EXR_OK && !edit_atomic_write(path,data,size)) status=EXR_IO;
  if (!text) exr_free(data);
  if (status!=EXR_OK) {
    free(saved); MessageBoxW(g.window,status==EXR_UNSUPPORTED ?
      L"此 SDK 的 DOCX 文本导出不能保留这些内容。请选择 UTF-8 TXT，或使用带 X1 双向桥的 SDK。":
      L"保存失败，原文件保留。请检查路径和磁盘后重试。",L"无法保存",MB_OK|MB_ICONERROR);
    shell_edit_title(); return 0;
  }
  free(editor.model.saved); editor.model.saved=saved;
  copy_wstring(editor.path,HOST_PATH,path); shell_edit_title(); set_status(L"文档已保存。"); return 1;
}
static int shell_edit_before_close(void) {
  if (!editor.model.doc) return 1;
  if (!edit_complete_composition()) return 0;
  if (edit_finish(&editor.model)!=EXR_OK) return 0;
  if (!edit_dirty(&editor.model)) return 1;
  int answer=MessageBoxW(g.window,L"文档有未保存的更改。是否保存？\n\n是：保存　否：放弃　取消：继续编辑",
    L"保存更改",MB_YESNOCANCEL|MB_ICONWARNING|MB_DEFBUTTON3);
  if (answer==IDCANCEL) return 0;
  return answer==IDYES ? shell_edit_save(0):answer==IDNO;
}
static void shell_edit_destroy(void) {
  KillTimer(g.page,EDIT_BLINK); KillTimer(g.page,EDIT_BATCH);
  edit_cancel_composition();
  if (editor.caret_created) DestroyCaret();
  editor.caret_created=0;
  ImmAssociateContextEx(g.page,NULL,IACE_DEFAULT);
  shell_edit_view_free(editor.view); editor.view=NULL; free(editor.display); editor.display=NULL;
  edit_model_free(&editor.model); editor.enabled=0; editor.path[0]=0; editor.scroll=0; editor.surrogate=0;
  if (editor.menu) CheckMenuItem(editor.menu,EDIT_MODE,MF_BYCOMMAND|MF_UNCHECKED);
}
static int shell_edit_before_leave(void) {
  if (!shell_edit_before_close()) return 0;
  shell_edit_destroy(); SetWindowTextW(g.window,L"EXReader"); page_dirty(g.page,1); return 1;
}
static int shell_edit_open(const wchar_t *path) {
  wchar_t source[HOST_PATH]; copy_wstring(source,HOST_PATH,path);
  edit_model model={0};
  exr_status status=edit_load(&model,source);
  if (status!=EXR_OK) { edit_model_free(&model); edit_error(status); return 0; }
  if (!shell_edit_before_close()) { edit_model_free(&model); return 0; }
  shell_edit_destroy(); editor.model=model; copy_wstring(editor.path,HOST_PATH,source);
  editor.book_id=g.session.book_id;
  shell_toc_set(0,0); shell_search_set(0); tts_stop(); dict_close_all();
  shell_bar_hidden=0; shelf_requested=0;
  ImmAssociateContextEx(g.page,NULL,0);
  shell_sync(); shell_layout();
  shell_edit_relayout(); shell_edit_title(); SetFocus(g.page); return 1;
}
static void shell_edit_toggle(void) {
  if (!editor.model.doc) {
    if (!shell_active || !g.frame.valid || g.frame.fixed || g.job || g.pending) {
      set_status(L"请先打开 DOCX 或 TXT 文档。"); return;
    }
    shelf_book *book=shelf_find(g.frame.book_id);
    wchar_t *path=book && book->path ? host_wide(book->path,strlen(book->path)):NULL;
    if (!path || !shell_edit_open(path)) { free(path); return; }
    free(path);
  }
  if (!edit_complete_composition()) return;
  edit_finish(&editor.model); editor.enabled=!editor.enabled;
  ImmAssociateContextEx(g.page,NULL,editor.enabled ? IACE_DEFAULT:0);
  editor.surrogate=0; shell_edit_title(); SetFocus(g.page);
  if (!editor.enabled) { KillTimer(g.page,EDIT_BLINK); if (editor.caret_created) DestroyCaret(); editor.caret_created=0; }
  else if (!editor.caret_created) edit_native_caret();
  edit_blink_reset();
}
static void edit_copy(int cut) {
  edit_model *m=&editor.model;
  size_t a=min(m->selection.anchor,m->selection.focus),b=max(m->selection.anchor,m->selection.focus);
  if (a==b || !OpenClipboard(g.window)) return;
  wchar_t *text=host_wide(m->text+a,b-a); size_t count=text ? wcslen(text):0,extra=0;
  for (size_t i=0;i<count;i++) if (text[i]==L'\n') extra++;
  HGLOBAL memory=text ? GlobalAlloc(GMEM_MOVEABLE,(count+extra+1)*sizeof(wchar_t)):NULL;
  wchar_t *out=memory ? GlobalLock(memory):NULL;
  int okay=0;
  if (out) {
    size_t used=0;
    for (size_t i=0;i<count;i++) { if (text[i]==L'\n') out[used++]=L'\r'; out[used++]=text[i]; }
    out[used]=0; GlobalUnlock(memory);
    okay=EmptyClipboard() && SetClipboardData(CF_UNICODETEXT,memory)!=NULL;
  }
  if (!okay && memory) GlobalFree(memory);
  free(text); CloseClipboard();
  if (okay && cut && editor.enabled) edit_changed(edit_replace(m,a,b,"",0,0));
}
static void edit_paste(void) {
  if (!editor.enabled || !OpenClipboard(g.window)) return;
  HANDLE data=GetClipboardData(CF_UNICODETEXT);
  SIZE_T bytes=data ? GlobalSize(data):0; const wchar_t *text=data ? GlobalLock(data):NULL;
  char *utf8=NULL;
  if (text && bytes<=EDIT_LIMIT*2u) {
    const wchar_t *end=wmemchr(text,0,bytes/sizeof(*text));
    if (end) utf8=edit_normalize_wide(text,(size_t)(end-text));
  }
  if (text) GlobalUnlock(data);
  CloseClipboard();
  if (!utf8) { MessageBeep(MB_ICONWARNING); return; }
  edit_model *m=&editor.model;
  edit_changed(edit_replace(m,min(m->selection.anchor,m->selection.focus),max(m->selection.anchor,m->selection.focus),utf8,strlen(utf8),0));
  free(utf8);
}
static void edit_move(UINT key,int shift,int control) {
  edit_model *m=&editor.model; edit_finish(m); editor.surrogate=0;
  size_t at=m->selection.focus;
  if (!shift && m->selection.anchor!=at && (key==VK_LEFT || key==VK_RIGHT))
    at=key==VK_LEFT ? min(m->selection.anchor,at):max(m->selection.anchor,at);
  else if (key==VK_LEFT || key==VK_RIGHT) at=edit_boundary(m,at,key==VK_RIGHT);
  else if (key==VK_HOME || key==VK_END) at=control ? (key==VK_HOME ? 0:m->size):
    edit_byte_at(m,shell_edit_view_line_edge(editor.view,edit_utf16_at(m,at),key==VK_END));
  else if (key==VK_UP || key==VK_DOWN) {
    float box[4];
    if (SUCCEEDED(shell_edit_view_caret(editor.view,edit_utf16_at(m,at),box))) {
      if (!editor.goal_valid) { editor.goal_x=box[0]; editor.goal_valid=1; }
      float y=box[1]+(key==VK_DOWN ? box[3]*1.5f:-box[3]*.5f);
      at=edit_byte_at(m,shell_edit_view_hit(editor.view,editor.goal_x,y));
    }
  }
  if (key!=VK_UP && key!=VK_DOWN) editor.goal_valid=0;
  m->selection.focus=at; if (!shift) m->selection.anchor=at;
  edit_keep_visible(); edit_blink_reset();
}
static void shell_edit_paint(HWND window) {
  PAINTSTRUCT paint; HDC screen=BeginPaint(window,&paint); RECT area; GetClientRect(window,&area);
  HDC dc=CreateCompatibleDC(screen); HBITMAP bitmap=CreateCompatibleBitmap(screen,max(1,area.right),max(1,area.bottom));
  HGDIOBJ old=bitmap && dc ? SelectObject(dc,bitmap):NULL;
  if (!old) { if (bitmap) DeleteObject(bitmap); if (dc) DeleteDC(dc); EndPaint(window,&paint); return; }
  HBRUSH background=CreateSolidBrush(shell_colorref(shell_colors->layer_page)); FillRect(dc,&area,background); DeleteObject(background);
  unsigned a=edit_utf16_at(&editor.model,min(editor.model.selection.anchor,editor.model.selection.focus));
  unsigned b=edit_utf16_at(&editor.model,max(editor.model.selection.anchor,editor.model.selection.focus));
  uint32_t highlight=shell_blend(shell_colors->layer_page,shell_colors->accent,shell_is_dark() ? .35f:.22f);
  shell_edit_view_paint(host_shell,editor.view,dc,&area,editor.left,editor.top-editor.scroll,
    editor.composing ? 0:a,editor.composing ? 0:b,shell_colors->layer_page,shell_colors->text,highlight);
  if (editor.composing && editor.composition_size) {
    unsigned start=edit_utf16_at(&editor.model,min(editor.model.selection.anchor,editor.model.selection.focus));
    shell_edit_view_underline(editor.view,dc,editor.left,editor.top-editor.scroll,start,
      editor.composition_size,max(1,shell_px(1,shell_dpi)),shell_colors->text);
  }
  if (editor.enabled && GetFocus()==window && (editor.blink || editor.composing)) {
    float box[4];
    if (edit_caret_box(box)) {
      int x=(int)lroundf(editor.left+box[0]),y=(int)lroundf(editor.top+box[1]-editor.scroll);
      HPEN pen=CreatePen(PS_SOLID,max(1,shell_px(1,shell_dpi)),shell_colorref(shell_colors->text)); HGDIOBJ previous=SelectObject(dc,pen);
      MoveToEx(dc,x,y,NULL); LineTo(dc,x,y+(int)lroundf(box[3])); SelectObject(dc,previous); DeleteObject(pen);
    }
  }
  if (GetFocus()==window && !(SendMessageW(window,WM_QUERYUISTATE,0,0)&UISF_HIDEFOCUS)) {
    RECT focus=area; InflateRect(&focus,-2,-2); DrawFocusRect(dc,&focus);
  }
  BitBlt(screen,0,0,area.right,area.bottom,dc,0,0,SRCCOPY);
  SelectObject(dc,old); DeleteObject(bitmap); DeleteDC(dc); EndPaint(window,&paint);
}
static int shell_edit_command(int id) {
  if (id==EDIT_OPEN) {
    wchar_t path[HOST_PATH]=L""; OPENFILENAMEW dialog={0}; dialog.lStructSize=sizeof(dialog); dialog.hwndOwner=g.window;
    dialog.lpstrFilter=L"可编辑文档\0*.docx;*.txt\0\0"; dialog.lpstrFile=path; dialog.nMaxFile=HOST_PATH;
    dialog.Flags=OFN_FILEMUSTEXIST|OFN_PATHMUSTEXIST|OFN_NOCHANGEDIR;
    if (GetOpenFileNameW(&dialog)) shell_edit_open(path);
    return 1;
  }
  if (id==EDIT_MODE) { shell_edit_toggle(); return 1; }
  if (id<EDIT_SAVE || id>EDIT_ALL) return 0;
  if (!editor.model.doc) return 1;
  if (id==EDIT_SAVE || id==EDIT_SAVE_AS) { shell_edit_save(id==EDIT_SAVE_AS); return 1; }
  if (!edit_complete_composition()) return 1;
  edit_finish(&editor.model); editor.surrogate=0;
  if (id==EDIT_COPY || id==EDIT_CUT) edit_copy(id==EDIT_CUT);
  if (id==EDIT_PASTE) edit_paste();
  if (id==EDIT_ALL) { editor.model.selection=(edit_selection){0,editor.model.size}; edit_blink_reset(); }
  if (editor.enabled && (id==EDIT_UNDO || id==EDIT_REDO)) {
    exr_status status=edit_history_move(&editor.model,id==EDIT_REDO);
    if (status==EXR_ARGUMENT) MessageBeep(MB_OK); else edit_changed(status);
  }
  return 1;
}
static void shell_edit_create(HWND window) {
  HMENU bar=GetMenu(window);
  if (!bar) bar=CreateMenu();
  HMENU file=CreatePopupMenu(),edit=CreatePopupMenu(); editor.menu=edit;
  AppendMenuW(file,MF_STRING,EDIT_OPEN,L"打开文档…\tCtrl+O");
  AppendMenuW(file,MF_STRING,EDIT_SAVE,L"保存\tCtrl+S");
  AppendMenuW(file,MF_STRING,EDIT_SAVE_AS,L"另存为…\tCtrl+Shift+S");
  AppendMenuW(edit,MF_STRING,EDIT_MODE,L"编辑模式\tCtrl+E"); AppendMenuW(edit,MF_SEPARATOR,0,NULL);
  AppendMenuW(edit,MF_STRING,EDIT_UNDO,L"撤销\tCtrl+Z"); AppendMenuW(edit,MF_STRING,EDIT_REDO,L"重做\tCtrl+Y");
  AppendMenuW(edit,MF_SEPARATOR,0,NULL); AppendMenuW(edit,MF_STRING,EDIT_CUT,L"剪切\tCtrl+X");
  AppendMenuW(edit,MF_STRING,EDIT_COPY,L"复制\tCtrl+C"); AppendMenuW(edit,MF_STRING,EDIT_PASTE,L"粘贴\tCtrl+V");
  AppendMenuW(edit,MF_STRING,EDIT_ALL,L"全选\tCtrl+A");
  AppendMenuW(bar,MF_POPUP,(UINT_PTR)file,L"文件(&F)"); AppendMenuW(bar,MF_POPUP,(UINT_PTR)edit,L"编辑(&E)");
  SetMenu(window,bar); DrawMenuBar(window);
}
static int shell_edit_translate(const MSG *message) {
  if (message->message!=WM_KEYDOWN || !IsWindowEnabled(g.window)) return 0;
  int control=GetKeyState(VK_CONTROL)<0,shift=GetKeyState(VK_SHIFT)<0;
  if (control && message->wParam=='E') { shell_edit_command(EDIT_MODE); return 1; }
  if (control && message->wParam=='O') { shell_edit_command(EDIT_OPEN); return 1; }
  if (control && message->wParam=='S' && editor.model.doc) { shell_edit_command(shift ? EDIT_SAVE_AS:EDIT_SAVE); return 1; }
  /* Dispatch editing keys directly before IsDialogMessage consumes arrows or
     Enter. TranslateMessage still produces WM_CHAR for printable input. */
  if (editor.model.doc && message->hwnd==g.page) {
    if (message->wParam==VK_TAB && !editor.composing) return 0;
    TranslateMessage(message); DispatchMessageW(message); return 1;
  }
  return 0;
}
static int shell_edit_message(HWND window,UINT message,WPARAM wp,LPARAM lp,LRESULT *result) {
  if (!editor.model.doc) return 0;
  edit_model *m=&editor.model; *result=0;
  switch (message) {
    case WM_PAINT: shell_edit_paint(window); return 1;
    case WM_SIZE: shell_edit_relayout(); return 1;
    case WM_GETDLGCODE: *result=DLGC_WANTARROWS|DLGC_WANTCHARS; return 1;
    case WM_SETCURSOR: SetCursor(LoadCursorW(NULL,editor.enabled ? IDC_IBEAM:IDC_ARROW)); *result=TRUE; return 1;
    case WM_SETFOCUS:
      edit_native_caret();
      edit_blink_reset(); return 1;
    case WM_KILLFOCUS:
      edit_complete_composition(); edit_finish(m); KillTimer(window,EDIT_BLINK); KillTimer(window,EDIT_BATCH);
      editor.blink=0; editor.surrogate=0;
      if (editor.caret_created) DestroyCaret();
      editor.caret_created=0;
      InvalidateRect(window,NULL,FALSE); return 1;
    case WM_TIMER:
      if (wp==EDIT_BLINK) { editor.blink=!editor.blink; InvalidateRect(window,NULL,FALSE); return 1; }
      if (wp==EDIT_BATCH) { KillTimer(window,EDIT_BATCH); exr_status status=edit_finish(m); if (status!=EXR_OK) edit_changed(status); return 1; }
      return 0;
    case WM_LBUTTONDOWN: case WM_LBUTTONDBLCLK:
      if (!edit_complete_composition()) return 1;
      edit_finish(m); editor.surrogate=0; SetFocus(window); SetCapture(window); editor.drag=1; editor.goal_valid=0;
      m->selection.focus=edit_byte_at(m,shell_edit_view_hit(editor.view,(short)LOWORD(lp)-editor.left,(short)HIWORD(lp)-editor.top+editor.scroll));
      if (!(GetKeyState(VK_SHIFT)<0)) m->selection.anchor=m->selection.focus;
      edit_blink_reset(); return 1;
    case WM_MOUSEMOVE: case WM_LBUTTONUP:
      if (editor.drag) {
        RECT area; GetClientRect(window,&area); int y=(short)HIWORD(lp);
        if (y<0) editor.scroll=max(0,editor.scroll-editor.font_size);
        if (y>area.bottom) editor.scroll+=editor.font_size;
        m->selection.focus=edit_byte_at(m,shell_edit_view_hit(editor.view,(short)LOWORD(lp)-editor.left,y-editor.top+editor.scroll));
        if (message==WM_LBUTTONUP) { editor.drag=0; ReleaseCapture(); }
        edit_blink_reset();
      }
      return 1;
    case WM_CAPTURECHANGED: editor.drag=0; return 1;
    case WM_MOUSEWHEEL:
      edit_finish(m);
      if (GetKeyState(VK_CONTROL)<0) { g.zoom_percent=max(25,min(400,g.zoom_percent+((short)HIWORD(wp)>0 ? 10:-10))); shell_edit_relayout(); }
      else { RECT area; GetClientRect(window,&area);
        editor.scroll=max(0,min(max(0,shell_edit_view_height(editor.view)-area.bottom+2*editor.top),
          editor.scroll-(short)HIWORD(wp)/120.f*editor.font_size*3)); edit_ime_position(); InvalidateRect(window,NULL,FALSE); }
      return 1;
    case WM_IME_SETCONTEXT:
      *result=DefWindowProcW(window,message,wp,lp&~(LPARAM)ISC_SHOWUICOMPOSITIONWINDOW); return 1;
    case WM_IME_REQUEST:
      if (wp==IMR_QUERYCHARPOSITION && lp && editor.enabled) {
        IMECHARPOSITION *position=(IMECHARPOSITION *)lp; float box[4];
        if (position->dwSize<sizeof(*position) || position->dwCharPos>(editor.composing ? editor.composition_size:0)) return 1;
        unsigned at=edit_utf16_at(m,editor.composing ? min(m->selection.anchor,m->selection.focus):m->selection.focus);
        if (FAILED(shell_edit_view_caret(editor.view,at+position->dwCharPos,box))) return 1;
        position->pt=(POINT){(LONG)lroundf(editor.left+box[0]),(LONG)lroundf(editor.top+box[1]-editor.scroll)};
        ClientToScreen(window,&position->pt); position->cLineHeight=(UINT)ceilf(box[3]);
        GetClientRect(window,&position->rcDocument);
        MapWindowPoints(window,NULL,(POINT *)&position->rcDocument,2); *result=TRUE; return 1;
      }
      return 0;
    case WM_IME_NOTIFY:
      if (wp==IMN_OPENCANDIDATE || wp==IMN_CHANGECANDIDATE) edit_ime_position();
      return 0;
    case WM_IME_STARTCOMPOSITION:
      if (!editor.enabled) return 1;
      edit_finish(m); editor.surrogate=0; editor.composing=1; editor.composition_size=editor.composition_cursor=0;
      free(editor.composition); editor.composition=NULL; shell_edit_relayout(); return 1;
    case WM_IME_COMPOSITION: {
      if (!editor.enabled) return 1;
      HIMC context=ImmGetContext(window); if (!context) return 1;
      if (lp&GCS_RESULTSTR) {
        LONG bytes=ImmGetCompositionStringW(context,GCS_RESULTSTR,NULL,0);
        if (bytes>0 && bytes<=EDIT_LIMIT && !(bytes&1)) {
          wchar_t *text=calloc((size_t)bytes/2+1,sizeof(*text));
          if (text && ImmGetCompositionStringW(context,GCS_RESULTSTR,text,(DWORD)bytes)==bytes) {
            char *utf8=edit_normalize_wide(text,(size_t)bytes/2);
            if (utf8) { editor.composing=0; editor.composition_size=editor.composition_cursor=0;
              edit_changed(edit_replace(m,min(m->selection.anchor,m->selection.focus),max(m->selection.anchor,m->selection.focus),utf8,strlen(utf8),0)); free(utf8); }
          }
          free(text);
        }
      }
      if (lp&GCS_COMPSTR) {
        LONG bytes=ImmGetCompositionStringW(context,GCS_COMPSTR,NULL,0);
        if (bytes>=0 && bytes<=EDIT_LIMIT && !(bytes&1)) {
          wchar_t *text=calloc((size_t)bytes/2+1,sizeof(*text));
          if (text && ImmGetCompositionStringW(context,GCS_COMPSTR,text,(DWORD)bytes)==bytes) {
            free(editor.composition); editor.composition=text; text=NULL;
            editor.composition_size=editor.composition_cursor=(unsigned)bytes/2; editor.composing=1;
          }
          free(text);
        }
      }
      if (lp&GCS_CURSORPOS) {
        LONG cursor=ImmGetCompositionStringW(context,GCS_CURSORPOS,NULL,0);
        if (cursor>=0) editor.composition_cursor=min((unsigned)cursor,editor.composition_size);
      }
      if (!(lp&(GCS_COMPSTR|GCS_CURSORPOS|GCS_COMPATTR|GCS_COMPCLAUSE|GCS_RESULTSTR))) {
        free(editor.composition); editor.composition=NULL; editor.composition_size=editor.composition_cursor=0;
      }
      ImmReleaseContext(window,context); shell_edit_relayout(); return 1;
    }
    case WM_IME_ENDCOMPOSITION:
      editor.composing=0; editor.composition_size=editor.composition_cursor=0; free(editor.composition); editor.composition=NULL;
      shell_edit_relayout(); return 1;
    case WM_IME_CHAR: return 1; /* RESULTSTR was already committed once. */
    case WM_UNICHAR:
      if (wp==UNICODE_NOCHAR) { *result=TRUE; return 1; }
      if (wp>0x10ffff || (wp>=0xd800 && wp<=0xdfff)) return 1;
      if (wp>0xffff) { wchar_t pair[2]={(wchar_t)(0xd800+((wp-0x10000)>>10)),(wchar_t)(0xdc00+((wp-0x10000)&1023))};
        SendMessageW(window,WM_CHAR,pair[0],1); SendMessageW(window,WM_CHAR,pair[1],1); return 1; }
      return shell_edit_message(window,WM_CHAR,wp,1,result);
    case WM_CHAR: {
      if (!editor.enabled || editor.composing || (GetKeyState(VK_CONTROL)<0 && !(GetKeyState(VK_MENU)<0))) return 1;
      if (wp<32 && wp!='\t') return 1;
      wchar_t text[3]={(wchar_t)wp,0,0}; size_t count=1;
      if (wp>=0xd800 && wp<=0xdbff) { editor.surrogate=(wchar_t)wp; return 1; }
      if (wp>=0xdc00 && wp<=0xdfff) {
        if (!editor.surrogate) return 1;
        text[0]=editor.surrogate; text[1]=(wchar_t)wp; count=2;
      }
      editor.surrogate=0; char *utf8=edit_normalize_wide(text,count);
      if (utf8) {
        size_t unit=strlen(utf8),repeat=max(1,LOWORD(lp)),size=unit*repeat;
        char *input=realloc(utf8,size+1);
        if (!input) { free(utf8); edit_error(EXR_MEMORY); return 1; }
        for (size_t at=unit;at<size;at+=unit) memcpy(input+at,input,unit);
        input[size]=0;
        exr_status status=edit_replace(m,min(m->selection.anchor,m->selection.focus),max(m->selection.anchor,m->selection.focus),input,size,1);
        edit_changed(status); free(input); SetTimer(window,EDIT_BATCH,1000,NULL);
      }
      return 1;
    }
    case WM_KEYDOWN: {
      int control=GetKeyState(VK_CONTROL)<0,shift=GetKeyState(VK_SHIFT)<0;
      if (editor.composing || wp==VK_PROCESSKEY || wp==VK_PACKET) { *result=DefWindowProcW(window,message,wp,lp); return 1; }
      if (control) {
        int command=wp=='Z' ? (shift ? EDIT_REDO:EDIT_UNDO):wp=='Y' ? EDIT_REDO:
          wp=='A' ? EDIT_ALL:wp=='C' ? EDIT_COPY:wp=='X' ? EDIT_CUT:wp=='V' ? EDIT_PASTE:
          wp=='S' ? (shift ? EDIT_SAVE_AS:EDIT_SAVE):0;
        if (command) { shell_edit_command(command); return 1; }
      }
      if ((wp>=VK_LEFT && wp<=VK_DOWN) || wp==VK_HOME || wp==VK_END) { edit_move((UINT)wp,shift,control); return 1; }
      if (wp==VK_ESCAPE) { edit_cancel_composition(); edit_finish(m); m->selection.anchor=m->selection.focus; edit_blink_reset(); return 1; }
      if (!editor.enabled) return 1;
      if (wp==VK_RETURN) { edit_changed(edit_enter(m)); return 1; }
      if (wp==VK_BACK || wp==VK_DELETE) {
        size_t a=min(m->selection.anchor,m->selection.focus),b=max(m->selection.anchor,m->selection.focus);
        if (a==b) { if (wp==VK_BACK) a=edit_boundary(m,a,0); else b=edit_boundary(m,b,1); }
        edit_changed(edit_replace(m,a,b,"",0,0)); return 1;
      }
      return 1;
    }
  }
  return 0;
}
