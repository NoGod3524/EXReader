/* SPDX-License-Identifier: MIT */
/* The tree owns only disposable labels; jumps resolve stable model IDs. */
#include <commctrl.h>
typedef struct {
  exr_edit_id id;
  size_t view;
  unsigned level,expanded;
  wchar_t *text;
  HTREEITEM node;
} de_outline_entry;
static struct {
  de_outline_entry *items;
  size_t count;
  HWND pane,tree,levels,empty;
  unsigned max_level;
  int syncing;
  WNDPROC tree_proc;
} deo;

static int de_outline_width(int width) {
  if(!deo.pane)return 0;
  int wanted=shell_px(240,shell_dpi);
  return width/3<wanted ? width/3:wanted;
}
static int de_outline_jump(exr_edit_id id) {
  for(size_t i=0,n=de_block_count(de.doc);i<n;i++) {
    const exr_edit_block *block=de_block_at(de.doc,i);
    if(block->id!=id || !de_heading_level(block))continue;
    de_set_caret(de_normalize(de_start(i)));de_set_anchor(de_caret_pos());
    de_refresh(1);return 1;
  }
  return 0;
}
static void de_outline_level(unsigned level) {
  if(level<1 || level>6)return;
  deo.max_level=level;int syncing=deo.syncing;deo.syncing=1;
  for(size_t i=0;i<deo.count;i++) {
    deo.items[i].expanded=deo.items[i].level<level;
    if(deo.tree)SendMessageW(deo.tree,TVM_EXPAND,
      deo.items[i].expanded ? TVE_EXPAND:TVE_COLLAPSE,(LPARAM)deo.items[i].node);
  }
  if(deo.levels)SendMessageW(deo.levels,CB_SETCURSEL,level-1,0);
  deo.syncing=syncing;
}
static LRESULT CALLBACK de_outline_tree_window(HWND window,UINT message,WPARAM wp,LPARAM lp) {
  if(message==WM_KEYDOWN && (wp==VK_RETURN || wp==VK_ESCAPE)) {
    if(g.page)SetFocus(g.page);return 0;
  }
  return CallWindowProcW(deo.tree_proc,window,message,wp,lp);
}
static LRESULT CALLBACK de_outline_window(HWND window,UINT message,WPARAM wp,LPARAM lp) {
  if(message==WM_COMMAND && (HWND)lp==deo.levels && HIWORD(wp)==CBN_SELCHANGE) {
    de_outline_level((unsigned)SendMessageW(deo.levels,CB_GETCURSEL,0,0)+1);return 0;
  }
  if(message==WM_NOTIFY && !deo.syncing && ((NMHDR *)lp)->hwndFrom==deo.tree) {
    NMHDR *header=(NMHDR *)lp;
    if(header->code==TVN_SELCHANGEDW) {
      size_t item=(size_t)((NMTREEVIEWW *)lp)->itemNew.lParam;
      if(item && item<=deo.count)de_outline_jump(deo.items[item-1].id);
      return 0;
    }
    if(header->code==NM_CLICK) {
      DWORD position=GetMessagePos();TVHITTESTINFO hit={0};
      hit.pt.x=(short)LOWORD(position);hit.pt.y=(short)HIWORD(position);
      ScreenToClient(deo.tree,&hit.pt);SendMessageW(deo.tree,TVM_HITTEST,0,(LPARAM)&hit);
      if(hit.hItem && (hit.flags&TVHT_ONITEMLABEL)) {
        TVITEMW item={0};item.mask=TVIF_PARAM;item.hItem=hit.hItem;
        if(SendMessageW(deo.tree,TVM_GETITEMW,0,(LPARAM)&item) && item.lParam>0 &&
          (size_t)item.lParam<=deo.count) {
          HTREEITEM selected=(HTREEITEM)SendMessageW(deo.tree,TVM_GETNEXTITEM,TVGN_CARET,0);
          if(selected==hit.hItem)de_outline_jump(deo.items[item.lParam-1].id);
          else SendMessageW(deo.tree,TVM_SELECTITEM,TVGN_CARET,(LPARAM)hit.hItem);
          SetFocus(g.page);return 1;
        }
      }
    }
  }
  return DefWindowProcW(window,message,wp,lp);
}
static void de_outline_create(void) {
  if(!g.page || deo.pane)return;
  INITCOMMONCONTROLSEX controls={sizeof(controls),ICC_TREEVIEW_CLASSES};
  if(!InitCommonControlsEx(&controls))return;
  WNDCLASSW wc={0};wc.lpfnWndProc=de_outline_window;wc.hInstance=GetModuleHandleW(NULL);
  wc.lpszClassName=L"EXReaderDocOutline";wc.hbrBackground=(HBRUSH)(COLOR_WINDOW+1);
  RegisterClassW(&wc);
  deo.pane=CreateWindowW(wc.lpszClassName,L"大纲",WS_CHILD|WS_VISIBLE|WS_CLIPCHILDREN,
    0,0,0,0,g.page,NULL,wc.hInstance,NULL);
  if(!deo.pane)return;
  SetWindowLongPtrW(g.page,GWL_STYLE,GetWindowLongPtrW(g.page,GWL_STYLE)|WS_CLIPCHILDREN);
  CreateWindowW(L"STATIC",L"大纲",WS_CHILD|WS_VISIBLE,8,8,48,24,deo.pane,NULL,wc.hInstance,NULL);
  deo.levels=CreateWindowW(L"COMBOBOX",L"显示标题级别",WS_CHILD|WS_VISIBLE|WS_TABSTOP|CBS_DROPDOWNLIST,
    56,4,140,240,deo.pane,NULL,wc.hInstance,NULL);
  for(unsigned i=1;i<=6;i++) {
    wchar_t label[24];swprintf(label,24,L"显示 %u 级",i);
    SendMessageW(deo.levels,CB_ADDSTRING,0,(LPARAM)label);
  }
  SendMessageW(deo.levels,CB_SETCURSEL,deo.max_level-1,0);
  deo.tree=CreateWindowW(WC_TREEVIEWW,L"文档标题（Ctrl+Shift+O）",WS_CHILD|WS_VISIBLE|WS_TABSTOP|
    TVS_HASBUTTONS|TVS_HASLINES|TVS_LINESATROOT|TVS_SHOWSELALWAYS,
    0,36,0,0,deo.pane,NULL,wc.hInstance,NULL);
  if(deo.tree) {
    SendMessageW(deo.tree,TVM_SETINDENT,shell_px(18,shell_dpi),0);
    deo.tree_proc=(WNDPROC)SetWindowLongPtrW(deo.tree,GWLP_WNDPROC,(LONG_PTR)de_outline_tree_window);
  }
  deo.empty=CreateWindowW(L"STATIC",L"无标题",WS_CHILD,12,44,100,24,deo.pane,NULL,wc.hInstance,NULL);
  HWND children[]={deo.levels,deo.tree,deo.empty};
  for(size_t i=0;i<sizeof(children)/sizeof(*children);i++)
    SendMessageW(children[i],WM_SETFONT,(WPARAM)GetStockObject(DEFAULT_GUI_FONT),FALSE);
}
static void de_outline_layout(int width,int height) {
  if(!deo.pane)return;
  int w=de_outline_width(width),top=(int)de_toolbar_height(),header=shell_px(36,shell_dpi);
  MoveWindow(deo.pane,0,top,w,height>top ? height-top:0,TRUE);
  SendMessageW(deo.tree,TVM_SETINDENT,shell_px(18,shell_dpi),0);
  MoveWindow(deo.levels,shell_px(52,shell_dpi),shell_px(4,shell_dpi),
    w>shell_px(56,shell_dpi) ? w-shell_px(56,shell_dpi):0,shell_px(240,shell_dpi),TRUE);
  MoveWindow(deo.tree,0,header,w,height>top+header ? height-top-header:0,TRUE);
}
static void de_outline_free(de_outline_entry *items,size_t count) {
  for(size_t i=0;i<count;i++)free(items[i].text);
  free(items);
}
static void de_outline_update(void) {
  if(!de.doc || deo.syncing)return;
  if(!deo.max_level)deo.max_level=6;
  int created=!deo.pane && g.page!=NULL;
  de_outline_create();
  size_t count=0,n=de_block_count(de.doc);
  de_outline_entry *items=calloc(n ? n:1,sizeof(*items));if(!items)return;
  for(size_t i=0;i<n;i++) {
    const exr_edit_block *block=de_block_at(de.doc,i);unsigned level=de_heading_level(block);
    if(!level)continue;
    wchar_t *text=de_paragraph_text(block);
    if(!text) {de_outline_free(items,count);return;}
    items[count++]=(de_outline_entry){block->id,i,level,level<deo.max_level,text,NULL};
  }
  int same=count==deo.count && !created;
  for(size_t i=0;i<deo.count;i++)if(deo.tree && deo.items[i].node)
    deo.items[i].expanded=(SendMessageW(deo.tree,TVM_GETITEMSTATE,(WPARAM)deo.items[i].node,TVIS_EXPANDED)&TVIS_EXPANDED)!=0;
  for(size_t i=0;i<count;i++) {
    if(i>=deo.count || items[i].id!=deo.items[i].id || items[i].level!=deo.items[i].level ||
      wcscmp(items[i].text,deo.items[i].text))same=0;
    for(size_t j=0;j<deo.count;j++)if(items[i].id==deo.items[j].id) {
      items[i].expanded=deo.items[j].expanded;items[i].node=deo.items[j].node;break;
    }
  }
  de_outline_free(deo.items,deo.count);deo.items=items;deo.count=count;
  if(same || !deo.tree)return;
  deo.syncing=1;SendMessageW(deo.tree,WM_SETREDRAW,FALSE,0);
  SendMessageW(deo.tree,TVM_DELETEITEM,0,(LPARAM)TVI_ROOT);
  HTREEITEM parents[7]={0};
  for(size_t i=0;i<count;i++) {
    de_outline_entry *item=&items[i];unsigned parent=item->level-1;
    while(parent && !parents[parent])parent--;
    /* Preserve the visible indent even when a document skips heading levels. */
    unsigned spaces=(item->level-parent-1)*3;
    size_t length=wcslen(item->text);wchar_t *label=malloc((length+spaces+1)*sizeof(*label));
    if(label) {for(unsigned j=0;j<spaces;j++)label[j]=L' ';memcpy(label+spaces,item->text,(length+1)*sizeof(*label));}
    TVINSERTSTRUCTW insert={0};insert.hParent=parent ? parents[parent]:TVI_ROOT;
    insert.hInsertAfter=TVI_LAST;insert.item.mask=TVIF_TEXT|TVIF_PARAM;
    insert.item.pszText=label ? label:item->text;insert.item.lParam=(LPARAM)(i+1);
    item->node=(HTREEITEM)SendMessageW(deo.tree,TVM_INSERTITEMW,0,(LPARAM)&insert);free(label);
    parents[item->level]=item->node;
    for(unsigned j=item->level+1;j<=6;j++)parents[j]=NULL;
  }
  for(size_t i=0;i<count;i++)if(items[i].expanded)
    SendMessageW(deo.tree,TVM_EXPAND,TVE_EXPAND,(LPARAM)items[i].node);
  ShowWindow(deo.tree,count ? SW_SHOWNA:SW_HIDE);ShowWindow(deo.empty,count ? SW_HIDE:SW_SHOWNA);
  SendMessageW(deo.tree,WM_SETREDRAW,TRUE,0);InvalidateRect(deo.tree,NULL,TRUE);deo.syncing=0;
}
static void de_outline_close(void) {
  deo.syncing=1;if(deo.pane)DestroyWindow(deo.pane);
  de_outline_free(deo.items,deo.count);memset(&deo,0,sizeof(deo));
}
