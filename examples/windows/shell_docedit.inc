/* SPDX-License-Identifier: MIT */
/* M-E1: one engine model. Layouts are disposable paragraph-local projections. */
#include <exr/edit.h>
typedef struct { size_t block,run,byte; } de_pos;
typedef struct {
  exr_edit_doc *doc;
  size_t caret_block,caret_run,caret_byte;
  size_t sel_anchor_block,sel_anchor_run,sel_anchor_byte;
  int dirty;
  char path[MAX_PATH];
  float scroll_y,extent,inset;
  shell_d2d_edit_row *rows;
  size_t row_count;
  int width,height,layout_dirty,blink,mouse_down,saved;
  unsigned dpi;
  wchar_t high_surrogate,title[512];
} shell_docedit;
static shell_docedit de;
enum { DE_TIMER=0xDE01 };
static HWND de_button;
static void de_refresh(int reveal);
static void de_drop_layout(void);
static int de_exit(void);

static de_pos de_caret(void) {
  de_pos p={de.caret_block,de.caret_run,de.caret_byte};return p;
}
static de_pos de_anchor(void) {
  de_pos p={de.sel_anchor_block,de.sel_anchor_run,de.sel_anchor_byte};return p;
}
static void de_set_caret(de_pos p) {
  de.caret_block=p.block;de.caret_run=p.run;de.caret_byte=p.byte;
}
static void de_set_anchor(de_pos p) {
  de.sel_anchor_block=p.block;de.sel_anchor_run=p.run;de.sel_anchor_byte=p.byte;
}
static int de_compare(de_pos a,de_pos b) {
  if(a.block!=b.block)return a.block<b.block ? -1:1;
  if(a.run!=b.run)return a.run<b.run ? -1:1;
  return a.byte==b.byte ? 0:a.byte<b.byte ? -1:1;
}
static size_t de_next_byte(const char *s,size_t n,size_t at) {
  if(at<n)at++;
  while(at<n && ((unsigned char)s[at]&0xc0)==0x80)at++;
  return at;
}
static size_t de_prev_byte(const char *s,size_t at) {
  if(at)at--;
  while(at && ((unsigned char)s[at]&0xc0)==0x80)at--;
  return at;
}
static int de_whitespace(const void *data,size_t n) {
  const unsigned char *s=data;
  for(size_t i=0;i<n;i++)if(s[i]!=' ' && s[i]!='\r' && s[i]!='\n' && s[i]!='\t')return 0;
  return 1;
}
static int de_run_trivia(const exr_edit_run *r) {
  return r->kind==EXR_EDIT_OPAQUE_RUN && de_whitespace(r->opaque_xml,r->opaque_size);
}
static int de_block_trivia(const exr_edit_block *b) {
  return b->kind==EXR_EDIT_OPAQUE_BLOCK && de_whitespace(b->opaque_xml,b->opaque_size);
}
static de_pos de_start(size_t block) { de_pos p={block,0,0};return p; }
static de_pos de_end(size_t block) {
  const exr_edit_block *b=exr_edit_block_at(de.doc,block);
  de_pos p={block,b ? b->run_count:0,0};
  if(b && b->run_count && b->runs[b->run_count-1].kind==EXR_EDIT_TEXT) {
    p.run--;p.byte=b->runs[p.run].text_size;
  }
  return p;
}
/* Canonicalize equivalent run boundaries, without indexing the document text. */
static de_pos de_normalize(de_pos p) {
  size_t n=exr_edit_block_count(de.doc);
  if(!n)return de_start(0);
  if(p.block>=n)p.block=n-1;
  const exr_edit_block *b=exr_edit_block_at(de.doc,p.block);
  if(p.run>b->run_count)p.run=b->run_count;
  if(p.run==b->run_count) {
    p.byte=0;
    if(p.run && b->runs[p.run-1].kind==EXR_EDIT_TEXT) {
      p.run--;p.byte=b->runs[p.run].text_size;
    }
  } else {
    const exr_edit_run *r=&b->runs[p.run];
    if(r->kind!=EXR_EDIT_TEXT)p.byte=0;
    else {
      if(p.byte>r->text_size)p.byte=r->text_size;
      while(p.byte<r->text_size && ((unsigned char)r->text[p.byte]&0xc0)==0x80)p.byte--;
    }
  }
  while(!p.byte && p.run<b->run_count && (de_run_trivia(&b->runs[p.run]) ||
    (b->runs[p.run].kind==EXR_EDIT_TEXT && !b->runs[p.run].text_size)))p.run++;
  while(p.run && !p.byte) {
    const exr_edit_run *previous=&b->runs[p.run-1];
    if(previous->kind==EXR_EDIT_TEXT) {p.run--;p.byte=previous->text_size;}
    else if(de_run_trivia(previous))p.run--;
    else break;
  }
  return p;
}
static int de_selected(void) {return de_compare(de_normalize(de_caret()),de_normalize(de_anchor()))!=0;}
static int de_active(void) {return de.doc!=NULL;}
static int de_draw_item(const DRAWITEMSTRUCT *item) {
  if(!de_button || item->hwndItem!=de_button)return 0;
  shell_draw_control(item,L"编辑",SHELL_CONTROL_GHOST,shell_colors->layer_side);return 1;
}
static void de_title_text(wchar_t title[600]) {
  if(de.doc)swprintf(title,600,L"%ls · 编辑%ls",de.title,de.dirty ? L" *":L"");
  else copy_wstring(title,600,de.title);
}
static void de_title(void) {
  if(!g.window)return;
  wchar_t title[600];de_title_text(title);SetWindowTextW(g.window,title);
}
static void de_error(const wchar_t *operation,exr_status status,exr_error *error) {
  wchar_t message[768];describe_error(message,768,operation,status,error);set_status(message);
}
static int de_save(void) {
  void *bytes=NULL;size_t size=0;exr_error error={0};
  if(!de.doc)return 0;
  exr_status status=exr_edit_docx_write(de.doc,&bytes,&size,&error);
  if(status!=EXR_OK) {de_error(L"无法生成 DOCX",status,&error);return 0;}
  wchar_t *path=host_wide(de.path,strlen(de.path)),dir[MAX_PATH],temp[MAX_PATH]=L"";
  HANDLE file=INVALID_HANDLE_VALUE;int ok=0;
  if(!path || wcslen(path)>=MAX_PATH)goto done;
  wcscpy(dir,path);wchar_t *slash=wcsrchr(dir,L'\\');
  if(!slash)slash=wcsrchr(dir,L'/');
  if(!slash)goto done;
  slash[1]=0;
  if(!GetTempFileNameW(dir,L"exr",0,temp))goto done;
  file=CreateFileW(temp,GENERIC_WRITE,0,NULL,TRUNCATE_EXISTING,FILE_ATTRIBUTE_NORMAL,NULL);
  if(file==INVALID_HANDLE_VALUE)goto done;
  size_t at=0;
  while(at<size) {
    DWORD written=0,want=(DWORD)((size-at)>0x100000 ? 0x100000:size-at);
    if(!WriteFile(file,(char *)bytes+at,want,&written,NULL) || written!=want)goto done;
    at+=written;
  }
  if(!FlushFileBuffers(file))goto done;
  if(!CloseHandle(file)) {file=INVALID_HANDLE_VALUE;goto done;}file=INVALID_HANDLE_VALUE;
  ok=ReplaceFileW(path,temp,NULL,0,NULL,NULL)!=0;
  if(!ok && GetLastError()==ERROR_FILE_NOT_FOUND)
    ok=MoveFileExW(temp,path,MOVEFILE_WRITE_THROUGH)!=0;
done:
  if(file!=INVALID_HANDLE_VALUE)CloseHandle(file);
  if(!ok && temp[0])DeleteFileW(temp);
  exr_free(bytes);free(path);
  if(ok) {de.dirty=0;de.saved=1;de_title();set_status(L"DOCX 已保存。");}
  else set_status(L"无法保存 DOCX；修改仍保留在编辑器中。");
  return ok;
}
static int de_open(const char *path) {
  if(de.doc || !path || strlen(path)>=sizeof(de.path))return 0;
  exr_error error={0};exr_edit_doc *doc=NULL;
  exr_status status=exr_edit_docx_open(path,NULL,&doc,&error);
  if(status!=EXR_OK) {de_error(L"无法编辑 DOCX",status,&error);return 0;}
  memset(&de,0,sizeof(de));de.doc=doc;strcpy(de.path,path);
  if(g.window)GetWindowTextW(g.window,de.title,512);
  size_t n=exr_edit_block_count(doc),i=0;
  while(i<n && exr_edit_block_at(doc,i)->kind!=EXR_EDIT_PARAGRAPH)i++;
  if(i==n) {
    exr_edit_id id;exr_edit_tx *tx=exr_edit_begin(doc);
    status=tx ? exr_edit_insert_paragraph(doc,0,NULL,0,NULL,&id):EXR_MEMORY;
    if(tx) {if(status==EXR_OK)status=exr_edit_commit(tx);else exr_edit_rollback(tx);}
    if(status!=EXR_OK) {exr_edit_doc_free(doc);de.doc=NULL;return 0;}
    i=0;de.dirty=1;
  }
  de_set_caret(de_start(i));de_set_anchor(de_caret());de.layout_dirty=1;de.blink=1;
  if(g.page) {SetTimer(g.page,DE_TIMER,GetCaretBlinkTime()==INFINITE ? 530:GetCaretBlinkTime(),NULL);SetFocus(g.page);}
  de_title();de_refresh(1);return 1;
}
static int de_eligible(void) {
  return g.has_current && g.current.format==EXR_DOCX && g.session.active && !g.job && !g.pending && !g.closing;
}
static void de_enter(void) {
  if(de.doc || !de_eligible())return;
  shelf_book *book=shelf_find(g.current.id);
  if(!book || !book->path || !*book->path) {set_status(L"此书没有本地 DOCX 路径；请重新从文件打开。");return;}
  shell_toc_set(0,0);shell_search_set(0);
  if(shell_panel_open)shell_toggle_settings();
  dict_close_all();tts_stop();shell_selection_reset();
  if(de_open(book->path))host_update_controls();
}
static void de_close(void) {
  if(g.page) {KillTimer(g.page,DE_TIMER);if(GetCapture()==g.page)ReleaseCapture();}
  de_drop_layout();exr_edit_doc_free(de.doc);de.doc=NULL;de_title();
  if(g.page)page_dirty(g.page,1);
}
static int de_exit_choice(int choice) {
  if(!de.doc)return 1;
  if(de.dirty) {
    if(choice==IDCANCEL)return 0;
    if(choice==IDYES && !de_save())return 0;
  }
  char path[MAX_PATH];strcpy(path,de.path);int saved=de.saved;
  de_close();
  if(g.window) {
    host_update_controls();
    /* SQLite owns an immutable imported snapshot. Reimport the saved file through
       the normal host path to refresh reading and keep the old library record. */
    if(saved) {wchar_t *wide=host_wide(path,strlen(path));if(wide) {
      g.auto_open_imported=1;import_path(wide,0);free(wide);
    }}
  }
  return 1;
}
static int de_exit(void) {
  int choice=IDNO;
  if(de.doc && de.dirty)choice=MessageBoxW(g.window,L"保存对 DOCX 的修改？\n是：保存　否：放弃　取消：继续编辑",
    L"退出编辑",MB_YESNOCANCEL|MB_ICONQUESTION);
  return de_exit_choice(choice);
}
static void de_controls(void) {
  if(!g.window)return;
  if(!de_button)de_button=shell_make_button(g.window,IDC_SHELL_DOCEDIT,L"编辑");
  RECT area;GetClientRect(g.window,&area);
  MoveWindow(de_button,area.right-shell_px(200,shell_dpi),shell_px(8,shell_dpi),
    shell_px(64,shell_dpi),shell_px(40,shell_dpi),TRUE);
  ShowWindow(de_button,shell_active && !shelf_requested && !shell_bar_hidden ? SW_SHOWNA:SW_HIDE);
  EnableWindow(de_button,de_eligible() && !de.doc);
  EnableWindow(shell_back,!de.doc);EnableWindow(shell_toc,!de.doc);
  EnableWindow(shell_search_button,!de.doc);EnableWindow(shell_settings,!de.doc);
  if(de.doc)de_title();
}
