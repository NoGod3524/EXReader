/* SPDX-License-Identifier: MIT */
#include "shell_docedit_table_history.h"
enum { DE_TTEXT=100,DE_TPREV,DE_TNEXT,DE_TADD,DE_TREMOVE,DE_TNARROW,DE_TWIDE };
typedef struct {
  HWND window,text,label;
  exr_edit_id table;
  size_t row,col;
  int changed,loading;
} de_table_panel;
static de_table_panel de_tp;
static void de_table_changed(void) {
  de.dirty=1;de.layout_dirty=1;de_refresh(1);
}
static int de_table_load(void) {
  const exr_edit_block *b=exr_edit_find_block(de.doc,de_tp.table);
  if(!b || !b->table)return 0;
  const exr_edit_table *t=b->table;
  if(de_tp.row>=t->row_count)de_tp.row=t->row_count-1;
  if(de_tp.col>=t->rows[de_tp.row].cell_count)de_tp.col=t->rows[de_tp.row].cell_count-1;
  const exr_edit_cell *cell=&t->rows[de_tp.row].cells[de_tp.col];
  size_t size=0;
  for(size_t i=0;i<cell->block_count;i++) {
    if(i)size+=2;
    for(size_t j=0;j<cell->blocks[i].run_count;j++)size+=cell->blocks[i].runs[j].text_size;
  }
  if(size>INT_MAX)return 0;
  char *text=calloc(size+1,1);if(!text)return 0;size_t at=0;
  for(size_t i=0;i<cell->block_count;i++) {
    if(i) {text[at++]='\r';text[at++]='\n';}
    for(size_t j=0;j<cell->blocks[i].run_count;j++) {
      const exr_edit_run *r=&cell->blocks[i].runs[j];
      if(r->text_size)memcpy(text+at,r->text,r->text_size);at+=r->text_size;
    }
  }
  wchar_t *wide=host_wide(text,at);free(text);if(!wide)return 0;
  de_tp.loading=1;SetWindowTextW(de_tp.text,wide);free(wide);
  de_tp.changed=0;de_tp.loading=0;
  /* Whole-cell replacement is intentionally limited to plain, uniform text.
     Rich/protected cells stay readable without discarding their formatting. */
  int editable=exr_edit_table_cell_paragraph(de.doc,de_tp.table,de_tp.row,de_tp.col,0)!=NULL;
  exr_edit_run_props props={0};int have_props=0;
  for(size_t i=0;i<cell->block_count;i++) {
    if(cell->blocks[i].kind!=EXR_EDIT_PARAGRAPH)editable=0;
    if(i && memcmp(&cell->blocks[0].props,&cell->blocks[i].props,sizeof(cell->blocks[i].props)))editable=0;
    for(size_t j=0;j<cell->blocks[i].run_count;j++) {
      const exr_edit_run *r=&cell->blocks[i].runs[j];
      if(r->kind!=EXR_EDIT_TEXT)editable=0;
      if(have_props && memcmp(&props,&r->props,sizeof(props)))editable=0;
      props=r->props;have_props=1;
    }
  }
  SendMessageW(de_tp.text,EM_SETREADONLY,!editable,0);
  wchar_t label[240];int width=t->column_widths ? t->column_widths[de_tp.col]:
    t->width_twips/(int32_t)t->column_count;
  swprintf(label,240,L"行 %zu/%zu · 列 %zu/%zu · 宽 %d twips%ls · Ctrl+Z/Y 撤销/重做",
    de_tp.row+1,t->row_count,de_tp.col+1,t->rows[de_tp.row].cell_count,width,
    editable ? L"":L" · 只读");
  SetWindowTextW(de_tp.label,label);return 1;
}
static int de_table_flush(void) {
  if(!de_tp.changed)return 1;
  int count=GetWindowTextLengthW(de_tp.text);
  wchar_t *wide=calloc((size_t)count+1,sizeof(*wide));if(!wide)return 0;
  GetWindowTextW(de_tp.text,wide,count+1);
  int n=WideCharToMultiByte(CP_UTF8,WC_ERR_INVALID_CHARS,wide,count,NULL,0,NULL,NULL);
  if(count && !n) {free(wide);return 0;}
  char *text=calloc((size_t)n+1,1);if(!text) {free(wide);return 0;}
  WideCharToMultiByte(CP_UTF8,WC_ERR_INVALID_CHARS,wide,count,text,n,NULL,NULL);free(wide);
  size_t size=0;for(int i=0;i<n;i++)if(text[i]!='\r')text[size++]=text[i];
  exr_status status=de_table_text(de.doc,de_tp.table,de_tp.row,de_tp.col,text,size);free(text);
  if(status!=EXR_OK) {set_status(L"无法修改此单元格；此次修改已撤回。");return 0;}
  de_tp.changed=0;de_table_changed();return 1;
}
static int de_table_history(int redo) {
  if(!de_table_flush())return 0;
  exr_status status=de_history(redo);
  if(status==EXR_OK)return de_table_load();
  return 1;
}
static void de_table_action(int command) {
  if(!de_table_flush())return;
  const exr_edit_block *b=exr_edit_find_block(de.doc,de_tp.table);if(!b || !b->table)return;
  exr_status status=EXR_OK;
  if(command==DE_TPREV) {
    if(de_tp.col)de_tp.col--;
    else if(de_tp.row) {de_tp.row--;de_tp.col=b->table->rows[de_tp.row].cell_count-1;}
  } else if(command==DE_TNEXT) {
    if(de_tp.col+1<b->table->rows[de_tp.row].cell_count)de_tp.col++;
    else if(de_tp.row+1<b->table->row_count) {de_tp.row++;de_tp.col=0;}
  } else if(command==DE_TADD) {
    status=exr_edit_table_insert_row(de.doc,de_tp.table,de_tp.row);
    if(status==EXR_OK) {de_tp.row++;de_tp.col=0;}
  } else if(command==DE_TREMOVE)status=exr_edit_table_delete_row(de.doc,de_tp.table,de_tp.row);
  else if(command==DE_TNARROW || command==DE_TWIDE)
    status=de_table_width(de.doc,de_tp.table,de_tp.col,command==DE_TWIDE ? 120:-120);
  if(status!=EXR_OK)set_status(L"无法修改此表格；此次修改已撤回。");
  else if(command>=DE_TADD)de_table_changed();
  de_table_load();SetFocus(de_tp.text);
}
static LRESULT CALLBACK de_table_proc(HWND window,UINT message,WPARAM wp,LPARAM lp) {
  if(message==WM_COMMAND) {
    int id=LOWORD(wp);
    if(id==DE_TTEXT && HIWORD(wp)==EN_CHANGE && !de_tp.loading)de_tp.changed=1;
    else if(id>=DE_TPREV && id<=DE_TWIDE && HIWORD(wp)==BN_CLICKED)de_table_action(id);
    return 0;
  }
  if(message==WM_CLOSE) {if(de_table_flush())DestroyWindow(window);return 0;}
  return DefWindowProcW(window,message,wp,lp);
}
static void de_table_open(void) {
  size_t count=exr_edit_block_count(de.doc),start=de.caret.block;
  exr_edit_id table=0;
  for(size_t i=0;i<count;i++) {
    const exr_edit_block *b=exr_edit_block_at(de.doc,(start+i)%count);
    if(b->table) {table=b->id;break;}
  }
  if(!table) {set_status(L"文档中没有可编辑表格。");return;}
  WNDCLASSW wc={0};wc.lpfnWndProc=de_table_proc;wc.hInstance=GetModuleHandleW(NULL);
  wc.lpszClassName=L"EXReaderTableHistory";wc.hCursor=LoadCursor(NULL,IDC_ARROW);
  wc.hbrBackground=(HBRUSH)(COLOR_WINDOW+1);RegisterClassW(&wc);
  memset(&de_tp,0,sizeof(de_tp));de_tp.table=table;
  HWND window=CreateWindowExW(WS_EX_DLGMODALFRAME,wc.lpszClassName,L"表格编辑 · Enter 换段 · 关闭提交",
    WS_OVERLAPPED|WS_CAPTION|WS_SYSMENU, CW_USEDEFAULT,CW_USEDEFAULT,720,360,
    g.window,NULL,wc.hInstance,NULL);
  if(!window)return;de_tp.window=window;
  de_tp.label=CreateWindowW(L"STATIC",L"",WS_CHILD|WS_VISIBLE,12,12,680,24,window,NULL,wc.hInstance,NULL);
  de_tp.text=CreateWindowExW(WS_EX_CLIENTEDGE,L"EDIT",L"",WS_CHILD|WS_VISIBLE|WS_TABSTOP|
    ES_MULTILINE|ES_WANTRETURN|ES_AUTOVSCROLL|WS_VSCROLL,12,44,680,210,
    window,(HMENU)(INT_PTR)DE_TTEXT,wc.hInstance,NULL);
  SendMessageW(de_tp.text,EM_SETLIMITTEXT,1024*1024,0);
  const wchar_t *labels[]={L"上一格",L"下一格",L"+行",L"删行",L"列宽−",L"列宽+"};
  for(int i=0;i<6;i++)CreateWindowW(L"BUTTON",labels[i],WS_CHILD|WS_VISIBLE|WS_TABSTOP,
    12+i*112,270,104,32,window,(HMENU)(INT_PTR)(DE_TPREV+i),wc.hInstance,NULL);
  if(!de_tp.label || !de_tp.text || !de_table_load()) {DestroyWindow(window);return;}
  EnableWindow(g.window,FALSE);ShowWindow(window,SW_SHOW);SetFocus(de_tp.text);
  MSG msg;int result=1;
  while(IsWindow(window) && (result=GetMessageW(&msg,NULL,0,0))>0) {
    if(msg.message==WM_KEYDOWN && (GetKeyState(VK_CONTROL)&0x8000) &&
      (msg.wParam=='Z' || msg.wParam=='Y' || msg.wParam=='S')) {
      if(msg.wParam=='S') {if(de_table_flush())de_save();}
      else de_table_history(msg.wParam=='Y');
      continue;
    }
    if(msg.message==WM_KEYDOWN && msg.wParam==VK_ESCAPE) {SendMessageW(window,WM_CLOSE,0,0);continue;}
    if(!IsDialogMessageW(window,&msg)) {TranslateMessage(&msg);DispatchMessageW(&msg);}
  }
  if(IsWindow(window))DestroyWindow(window);
  if(result==0)PostQuitMessage((int)msg.wParam);
  memset(&de_tp,0,sizeof(de_tp));EnableWindow(g.window,TRUE);SetFocus(g.page);de_refresh(1);
}
