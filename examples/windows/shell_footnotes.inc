/* SPDX-License-Identifier: MIT */
/* A horizontal native text control, independent of the book's writing mode. */
static HWND footnote_panel,footnote_text;
static HFONT footnote_font;
static size_t footnote_index=SIZE_MAX;
static int64_t footnote_book;
static wchar_t footnote_title[160];
static void shell_footnote_close(void) {
  if(footnote_panel)ShowWindow(footnote_panel,SW_HIDE);
  footnote_index=SIZE_MAX;
}
static LRESULT CALLBACK footnote_procedure(HWND window,UINT message,WPARAM wp,LPARAM lp) {
  switch(message) {
    case WM_ERASEBKGND:return 1;
    case WM_KEYDOWN:if(wp==VK_ESCAPE){shell_footnote_close();SetFocus(g.page);return 0;}break;
    case WM_CTLCOLOREDIT:case WM_CTLCOLORSTATIC: {
      static HBRUSH brush;static uint32_t color;
      if(!brush || color!=shell_colors->layer_float) {
        if(brush){DeleteObject(brush);}
        color=shell_colors->layer_float;brush=CreateSolidBrush(shell_colorref(color));
      }
      SetBkColor((HDC)wp,shell_colorref(color));SetTextColor((HDC)wp,shell_colorref(shell_colors->text));return (LRESULT)brush;
    }
    case WM_PAINT:case WM_PRINTCLIENT: {
      PAINTSTRUCT paint;RECT box;GetClientRect(window,&box);HDC dc=message==WM_PAINT?BeginPaint(window,&paint):(HDC)wp;
      shell_card_paint(window,dc,&box,footnote_title);
      if(message==WM_PAINT)EndPaint(window,&paint);
      return 0;
    }
  }
  return DefWindowProcW(window,message,wp,lp);
}
static int shell_footnote_open(size_t index,int x,int y) {
  const exr_footnote *notes;const exr_footnote_reference *refs;size_t n,r;
  exr_publication *p=select_publication();
  if(!p || exr_publication_footnotes(p,&notes,&n,&refs,&r,NULL)!=EXR_OK || index>=n)return 0;
  if(!footnote_panel) {
    WNDCLASSW type={0};type.lpfnWndProc=footnote_procedure;type.hInstance=GetModuleHandleW(NULL);
    type.hCursor=LoadCursor(NULL,IDC_ARROW);type.lpszClassName=L"EXReaderFootnote";RegisterClassW(&type);
    footnote_panel=CreateWindowExW(WS_EX_CONTROLPARENT,type.lpszClassName,L"脚注",WS_CHILD|WS_CLIPCHILDREN,
      0,0,0,0,g.window,NULL,type.hInstance,NULL);
    footnote_text=CreateWindowExW(0,L"EDIT",L"",WS_CHILD|WS_VISIBLE|WS_TABSTOP|ES_MULTILINE|ES_READONLY|ES_AUTOVSCROLL|WS_VSCROLL,
      0,0,0,0,footnote_panel,(HMENU)1,type.hInstance,NULL);
    SendMessageW(footnote_text,EM_SETLIMITTEXT,16*1024*1024,0);
  }
  if(!footnote_panel || !footnote_text)return 0;
  wchar_t *text=host_wide(notes[index].text,strlen(notes[index].text)),*label=host_wide(notes[index].label,strlen(notes[index].label));
  if(!text || !label){free(text);free(label);return 0;}
  swprintf(footnote_title,160,L"脚注 %ls",label);free(label);SetWindowTextW(footnote_text,text);free(text);
  HFONT font=CreateFontW(-shell_px(16,shell_dpi),0,0,0,FW_NORMAL,FALSE,FALSE,FALSE,DEFAULT_CHARSET,0,0,CLEARTYPE_QUALITY,0,L"Segoe UI");
  SendMessageW(footnote_text,WM_SETFONT,(WPARAM)font,TRUE);if(footnote_font)DeleteObject(footnote_font);footnote_font=font;
  SendMessageW(footnote_text,EM_SETSEL,0,0);SendMessageW(footnote_text,EM_SCROLLCARET,0,0);
  RECT area;GetClientRect(g.window,&area);int pad=shell_px(SHELL_SHADOW_PAD,shell_dpi),top=shell_px(SHELL_SHADOW_TOP,shell_dpi);
  int width=min(shell_px(360,shell_dpi),area.right-shell_px(24,shell_dpi));
  /* Height follows the wrapped text; at most half the client, then scroll. */
  int maxh=area.bottom/2,inner=width-shell_px(32,shell_dpi),chrome=shell_px(60,shell_dpi);
  MoveWindow(footnote_text,0,0,inner,max(1,maxh-chrome),FALSE);
  HDC measure=GetDC(footnote_text);TEXTMETRICW metrics={0};HGDIOBJ previous=SelectObject(measure,font);
  GetTextMetricsW(measure,&metrics);SelectObject(measure,previous);ReleaseDC(footnote_text,measure);
  int lines=(int)SendMessageW(footnote_text,EM_GETLINECOUNT,0,0);
  int height=min(maxh,chrome+lines*metrics.tmHeight+shell_px(8,shell_dpi));
  ShowScrollBar(footnote_text,SB_VERT,height==maxh);
  POINT point={x,y};MapWindowPoints(g.page,g.window,&point,1);
  int left=max(12,min(point.x,area.right-width-12)),above=point.y+12;
  if(above+height>area.bottom-12)above=max(12,point.y-height-12);
  SetWindowPos(footnote_panel,HWND_TOP,left-pad,above-top,width+2*pad,height+top+pad,SWP_NOACTIVATE);
  MoveWindow(footnote_text,pad+shell_px(16,shell_dpi),top+shell_px(44,shell_dpi),inner,height-chrome,TRUE);
  footnote_index=index;footnote_book=g.frame.book_id;ShowWindow(footnote_panel,SW_SHOWNOACTIVATE);SetFocus(footnote_text);
  RedrawWindow(footnote_panel,NULL,NULL,RDW_INVALIDATE|RDW_ALLCHILDREN);return 1;
}
static int shell_footnote_click(int x,int y) {
  exr_text_position position;const exr_footnote *notes;const exr_footnote_reference *refs;size_t n,r;
  if(!select_hit(x,y,&position))return 0;
  exr_publication *p=select_publication();
  if(!p || exr_publication_footnotes(p,&notes,&n,&refs,&r,NULL)!=EXR_OK)return 0;
  for(size_t i=0;i<r;i++)if(refs[i].part==position.part && refs[i].start<=position.offset && position.offset<refs[i].end)
    return shell_footnote_open(refs[i].footnote,x,y);
  shell_footnote_close();return 0;
}
static int shell_footnote_translate(const MSG *message) {
  if(!footnote_panel || !IsWindowVisible(footnote_panel))return 0;
  if(footnote_book!=g.frame.book_id){shell_footnote_close();return 0;}
  if(message->message==WM_KEYDOWN && message->wParam==VK_ESCAPE){shell_footnote_close();SetFocus(g.page);return 1;}
  if(message->message==WM_LBUTTONDOWN || message->message==WM_RBUTTONDOWN || message->message==WM_POINTERDOWN) {
    HWND target=message->hwnd;
    if(target!=footnote_panel && !IsChild(footnote_panel,target)) {
      shell_footnote_close();
      /* Dismissal on the page must not also begin a tap-to-turn gesture. */
      return target==g.page;
    }
  }
  return 0;
}
