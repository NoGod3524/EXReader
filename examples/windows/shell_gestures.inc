/* SPDX-License-Identifier: MIT */
/* Mouse ink drags select; gutter drags and touch pan. Lock intent after 4 DIP. */
static int gesture_state,gesture_x,gesture_y,gesture_max,gesture_ink,gesture_touch,gesture_bypass;
static int shell_zone_overlay;
static int gesture_reverse(void) {return g.frame.writing_mode==EXR_WRITING_VERTICAL_RL;}
static int gesture_tap(int x,int width) {
  int direction=x*(int64_t)100<width*(int64_t)shell_tap_edge ? -1:
    x*(int64_t)100>=width*(int64_t)(100-shell_tap_edge) ? 1:0;
  return gesture_reverse() ? -direction:direction;
}
static int gesture_has_ink(int x,int y) {
  if(!compute_view())return 0;
  float xx=(float)((x-g.view.dx)/g.view.scale),yy=(float)((y-g.view.dy)/g.view.scale);
  if(g.frame.fixed)return point_offset(x,y,0)!=SIZE_MAX;
  for(size_t i=0;i<g.frame.shell_line_count;i++) {
    const exr_line *line=&g.frame.shell_lines[i];
    if(xx>=line->x && xx<=line->x+line->width && yy>=line->y && yy<=line->y+line->height)return 1;
  }
  return 0;
}
static void gesture_dispatch(HWND window,UINT message,WPARAM wp,LPARAM lp) {
  gesture_bypass=1;SendMessageW(window,message,wp,lp);gesture_bypass=0;
}
static void gesture_reset(HWND window) {
  gesture_state=0;gesture_touch=0;
  if(GetCapture()==window)ReleaseCapture();
}
static int shell_gesture_message(HWND window,UINT message,WPARAM wp,LPARAM lp) {
  if(gesture_bypass || !shell_active)return 0;
  if(message==WM_KEYDOWN) {
    if(wp=='W' && (GetKeyState(VK_CONTROL)&0x8000)) {shelf_return();return 1;}
    if(wp==VK_ESCAPE && !shell_toc_open && !shell_panel_open && !shell_search_open) {
      if(select_valid || g.selection.active || annot_selected>=0) {annot_selected=-1;selection_clear();}
      else shelf_return();
      return 1;
    }
  }
  if(message==WM_POINTERDOWN || message==WM_POINTERUPDATE || message==WM_POINTERUP) {
    UINT id=GET_POINTERID_WPARAM(wp);POINTER_INPUT_TYPE type;POINTER_INFO info;
    if(!GetPointerType(id,&type) || type!=PT_TOUCH || !GetPointerInfo(id,&info))return 0;
    POINT p=info.ptPixelLocation;ScreenToClient(window,&p);lp=MAKELPARAM(p.x,p.y);
    if(message==WM_POINTERDOWN) {gesture_touch=1;message=WM_LBUTTONDOWN;}
    else message=message==WM_POINTERUP ? WM_LBUTTONUP:WM_MOUSEMOVE;
  }
  if(message==WM_CAPTURECHANGED || message==WM_CANCELMODE || message==WM_POINTERCAPTURECHANGED) {
    gesture_state=0;gesture_touch=0;return 0;
  }
  if(message==WM_LBUTTONDBLCLK) {
    /* Windows reports the second rapid gutter tap as DBLCLK. It still turns a
       page; word selection remains available when double-clicking text. */
    if(gesture_has_ink((short)LOWORD(lp),(short)HIWORD(lp))) {gesture_state=2;return 0;}
    message=WM_LBUTTONDOWN;
  }
  if(message==WM_LBUTTONDOWN) {
    if(shell_toc_open) {shell_toc_set(0,0);return 1;}
    if(shell_panel_open) {shell_toggle_settings();return 1;}
    if((g.job && g.job->kind!=JOB_PREFETCH) || g.pending || shelf_exit_pending)return 1;
    gesture_x=(short)LOWORD(lp);gesture_y=(short)HIWORD(lp);gesture_max=0;
    gesture_ink=!gesture_touch && gesture_has_ink(gesture_x,gesture_y);gesture_state=1;
    SetFocus(window);SetCapture(window);return 1;
  }
  if((message==WM_MOUSEMOVE || message==WM_LBUTTONUP) && gesture_state) {
    int x=(short)LOWORD(lp),y=(short)HIWORD(lp),dx=x-gesture_x,dy=y-gesture_y;
    gesture_max=max(gesture_max,max(abs(dx),abs(dy)));
    if(gesture_state==1 && gesture_max>shell_px(4,shell_dpi)) {
      if(gesture_ink) {
        gesture_state=2;
        shell_drag_begin=1;
        gesture_dispatch(window,WM_LBUTTONDOWN,MK_LBUTTON,MAKELPARAM(gesture_x,gesture_y));
        shell_drag_begin=0;
        select_clicks=1;
      } else gesture_state=3;
    }
    if(gesture_state==2) {
      if(message==WM_LBUTTONUP)gesture_state=0;
      gesture_dispatch(window,message,wp,lp);return 1;
    }
    if(message==WM_LBUTTONUP) {
      int state=gesture_state;gesture_reset(window);
      if(state==1 && gesture_max<=shell_px(4,shell_dpi)) {
        if(!g.frame.fixed && shell_footnote_click(x,y))return 1;
        if(!g.frame.fixed && annot_click(x,y))return 1;
        RECT r;GetClientRect(window,&r);int turn=gesture_tap(gesture_x,r.right);
        selection_clear();
        if(turn)page_step(turn);
        else {
          shell_bar_hidden=!shell_bar_hidden;shell_layout();
          InvalidateRect(g.window,NULL,FALSE);SetFocus(g.page);
        }
      } else if(state==3 && abs(dx)>shell_px(60,shell_dpi) && abs(dx)>abs(dy)*2) {
        int turn=dx<0 ? 1:-1;selection_clear();page_step(gesture_reverse() ? -turn:turn);
      }
      return 1;
    }
    return 1;
  }
  return 0;
}
static void gesture_label(HDC dc,const wchar_t *label,RECT r) {
  HGDIOBJ font=SelectObject(dc,shell_gdi_font(14,600));
  SetTextColor(dc,shell_colorref(shell_colors->accent));SetBkMode(dc,TRANSPARENT);
  DrawTextW(dc,label,-1,&r,DT_CENTER|DT_SINGLELINE|DT_VCENTER|DT_NOPREFIX);SelectObject(dc,font);
}
static void gesture_overlay(HDC dc,const RECT *area) {
  if(!shell_zone_overlay || !shell_active)return;
  int left=(int)((int64_t)area->right*shell_tap_edge/100),right=area->right-left;
  HPEN pen=CreatePen(PS_DASH,1,shell_colorref(shell_colors->accent));HGDIOBJ old=SelectObject(dc,pen);
  MoveToEx(dc,left,0,NULL);LineTo(dc,left,area->bottom);MoveToEx(dc,right,0,NULL);LineTo(dc,right,area->bottom);
  SelectObject(dc,old);DeleteObject(pen);
  wchar_t label[96];RECT r={0,area->bottom-shell_px(100,shell_dpi),left,area->bottom-shell_px(60,shell_dpi)};
  swprintf(label,96,L"%ls · %d%%",gesture_reverse() ? L"下一页":L"上一页",shell_tap_edge);
  gesture_label(dc,label,r);
  r.left=left;r.right=right;swprintf(label,96,L"顶栏 显示 / 隐藏 · %d%%",100-2*shell_tap_edge);gesture_label(dc,label,r);
  r.left=right;r.right=area->right;swprintf(label,96,L"%ls · %d%%",gesture_reverse() ? L"上一页":L"下一页",shell_tap_edge);gesture_label(dc,label,r);
}
