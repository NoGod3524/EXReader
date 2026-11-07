/* SPDX-License-Identifier: MIT */
/* Included by shell_screen.inc: UI-thread settings and theme presentation. */
static HDC page_buffer_dc; /* UI-owned backing store, defined after this include. */
enum { IDC_SHELL_MINUS=162, IDC_SHELL_PLUS, IDC_SHELL_LIGHT, IDC_SHELL_DARK, IDC_SHELL_SYSTEM };
static COLORREF shell_colorref(uint32_t rgb) { return RGB((rgb>>16)&255,(rgb>>8)&255,rgb&255); }

static void shell_apply_theme(void) {
  shell_colors=shell_is_dark() ? &shell_theme_dark : &shell_theme_light;
  /* Class brushes are owned here after registration; keep legacy white. */
  uint32_t bg=shell_active ? shell_colors->layer_page : shell_theme_light.layer_float;
  HWND windows[2]={g.window,g.page};
  for(int i=0;i<2;i++) if(windows[i]) {
    HBRUSH brush=CreateSolidBrush(shell_colorref(bg));
    HBRUSH old=(HBRUSH)SetClassLongPtrW(windows[i],GCLP_HBRBACKGROUND,(LONG_PTR)brush);
    if(old) DeleteObject(old);
  }
  if(g.page) page_dirty(g.page,1);
  if(g.window) RedrawWindow(g.window,NULL,NULL,RDW_INVALIDATE|RDW_ALLCHILDREN);
}

/* The worker leaves an unthemed DIB. Theme only the joined UI frame's display
   bitmap, keeping SDK bytes and cached layouts unchanged. Grayscale coverage
   maps black/white to text/bg; colour illustrations retain their RGB. */
static void shell_color_display(host_frame *frame) {
  int theme=shell_is_dark()+1;
  if(!frame->valid || frame->fixed || !frame->shell_geometry.enabled || !IsRectEmpty(&frame->shell_image)) return;
  if(!frame_prepare_display(frame) || frame->display_shell_theme==theme) return;
  DIBSECTION section={0};
  if(!GetObject(frame->display_bitmap,sizeof(section),&section) || !section.dsBm.bmBits) return;
  uint32_t *dst=section.dsBm.bmBits, *src=frame->dib;
  for(size_t i=0;i<(size_t)frame->display_width*frame->display_height;i++) {
    uint32_t q=src[i];unsigned b=q&255,gc=(q>>8)&255,r=(q>>16)&255;
    dst[i]=(r==gc && gc==b) ? shell_blend(shell_colors->text,shell_colors->layer_page,r/255.f) : q;
  }
  frame->display_shell_theme=theme;
}

static void shell_settings_refresh(void) {
  EnableWindow(shell_minus,!g.frame.fixed && shell_font>SHELL_BODY_MIN_FONT);
  EnableWindow(shell_plus,!g.frame.fixed && shell_font<SHELL_BODY_MAX_FONT);
  if(shell_panel) RedrawWindow(shell_panel,NULL,NULL,RDW_INVALIDATE|RDW_ALLCHILDREN);
}

static void shell_step_font(int delta) {
  size_t n=sizeof(SHELL_FONT_STEPS)/sizeof(*SHELL_FONT_STEPS);
  if(g.frame.fixed) return;
  if(delta>0) {
    for(size_t i=0;i<n;i++) if(SHELL_FONT_STEPS[i]>shell_font) { shell_font=(float)SHELL_FONT_STEPS[i];break; }
  } else {
    for(size_t i=n;i>0;i--) if(SHELL_FONT_STEPS[i-1]<shell_font) { shell_font=(float)SHELL_FONT_STEPS[i-1];break; }
  }
  shell_request_layout(); settings_save(); shell_settings_refresh();
}

static int shell_settings_command(int id) {
  if(id==IDC_SHELL_MINUS || id==IDC_SHELL_PLUS) { shell_step_font(id==IDC_SHELL_PLUS ? 1 : -1);return 1; }
  if(id>=IDC_SHELL_LIGHT && id<=IDC_SHELL_SYSTEM) {
    shell_theme_mode=id-IDC_SHELL_LIGHT; settings_save(); shell_apply_theme(); return 1;
  }
  return 0;
}

static void shell_panel_layout(void) {
  if(!shell_panel || !g.window) return;
  RECT area;GetClientRect(g.window,&area);
  int kpad=shell_px(SHELL_SHADOW_PAD,shell_dpi);
  int w=shell_px(SHELL_PANEL_W,shell_dpi)+2*kpad;
  int top=shell_px(SHELL_SHADOW_TOP,shell_dpi);
  int h=shell_px(SHELL_PANEL_H,shell_dpi)+top+kpad;
  /* The panel's shadow bounds are an ordinary child, above the page HWND. */
  SetWindowPos(shell_panel,HWND_TOP,area.right-shell_px(SHELL_SPACE_2,shell_dpi)-w+kpad,
    shell_px(SHELL_TOPBAR_H,shell_dpi),w,(int)(h*shell_animation_value+.5f),SWP_NOACTIVATE);
  HWND controls[5]={shell_minus,shell_plus,shell_segments[0],shell_segments[1],shell_segments[2]};
  int xs[5]={111,215,24,74,124};
  int widths[5]={34,34,50,50,76};
  for(int i=0;i<5;i++) {
    int frame=shell_px(i<2 ? SHELL_CONTROL_FRAME : SHELL_SEGMENT_PAD,shell_dpi);
    int y=i<2 ? 44 : 122;
    MoveWindow(controls[i],kpad+shell_px(xs[i],shell_dpi)-(i<2 ? frame : 0),top+shell_px(y,shell_dpi)-frame,
      shell_px(widths[i],shell_dpi)+(i<2 ? 2*frame : 0),
      shell_px(i<2 ? SHELL_CONTROL_H : SHELL_SEGMENT_H,shell_dpi)+2*frame,TRUE);
  }
}

static float shell_ease(float x) {
  /* Invert cubic x(t), then evaluate y(t), preserving DeckMark's curve. */
  float lo=0,hi=1,t=0;
  for(int i=0;i<24;i++) {
    t=(lo+hi)/2;float u=1-t;
    float bx=3*u*u*t*SHELL_EASE[0]+3*u*t*t*SHELL_EASE[2]+t*t*t;
    if(bx<x) lo=t;else hi=t;
  }
  float u=1-t;return 3*u*u*t*SHELL_EASE[1]+3*u*t*t*SHELL_EASE[3]+t*t*t;
}

static void shell_animate(void) {
  double elapsed=host_probe_ms()-shell_animation_start;
  float x=(float)(elapsed/SHELL_ANIMATION_MS);
  shell_animation_value=shell_animation_from+((shell_panel_open ? 1.f : 0.f)-shell_animation_from)*shell_ease(fminf(x,1));
  if(x>=1) {
    shell_animation_value=shell_panel_open ? 1.f : 0.f; shell_animating=0;
    shell_animation_elapsed=elapsed;KillTimer(g.window,0x5753);
    host_probe_log("settings_animation_ms",elapsed);
  }
  shell_panel_layout();
  if(!shell_panel_open && !shell_animating) ShowWindow(shell_panel,SW_HIDE);
  page_dirty(g.page,1);
}

static void shell_toggle_settings(void) {
  BOOL animations=FALSE;
  SystemParametersInfoW(SPI_GETCLIENTAREAANIMATION,0,&animations,0);
  shell_panel_open=!shell_panel_open;
  shell_animation_from=shell_animation_value;shell_animation_start=host_probe_ms();
  shell_animating=animations;
  if(shell_panel_open) { shell_settings_refresh(); ShowWindow(shell_panel,SW_SHOWNOACTIVATE); }
  if(animations) SetTimer(g.window,0x5753,SHELL_ANIMATION_TICK,NULL);
  else {
    KillTimer(g.window,0x5753);shell_animation_value=shell_panel_open ? 1.f : 0.f;
    shell_animation_elapsed=0;host_probe_log("settings_animation_ms",0);shell_panel_layout();
    if(!shell_panel_open) ShowWindow(shell_panel,SW_HIDE);
  }
  if(!host_offscreen) SetFocus(shell_panel_open ? shell_minus : shell_settings);
}

static LRESULT CALLBACK shell_panel_procedure(HWND window,UINT message,WPARAM wp,LPARAM lp) {
  switch(message) {
    case WM_ERASEBKGND:return 1;
    case WM_COMMAND: if(shell_settings_command(LOWORD(wp))) return 0;break;
    case WM_DRAWITEM: if(shell_draw_settings((const DRAWITEMSTRUCT *)lp)) return TRUE;break;
    case WM_PAINT:
    case WM_PRINTCLIENT: {
      PAINTSTRUCT paint;RECT box;GetClientRect(window,&box);
      /* Animate by clipping, never rescaling the content/shadow. */
      box.bottom=shell_px(SHELL_PANEL_H+SHELL_SHADOW_TOP+SHELL_SHADOW_PAD,shell_dpi);
      HDC dc=message==WM_PAINT ? BeginPaint(window,&paint) : (HDC)wp;
      wchar_t font[32];swprintf(font,32,L"%.0f px",(double)shell_font);
      if(host_shell) {
        /* Preserve the page beneath the translucent shadow and rounded corners. */
        BITMAPINFO info={0};void *bits=NULL;
        info.bmiHeader.biSize=sizeof(BITMAPINFOHEADER);info.bmiHeader.biWidth=box.right;
        info.bmiHeader.biHeight=-box.bottom;info.bmiHeader.biPlanes=1;info.bmiHeader.biBitCount=32;
        HDC underlay=CreateCompatibleDC(dc);HBITMAP bitmap=CreateDIBSection(dc,&info,DIB_RGB_COLORS,&bits,NULL,0);
        if(underlay && bitmap) {
          HGDIOBJ old=SelectObject(underlay,bitmap);RECT place;GetWindowRect(window,&place);
          MapWindowPoints(NULL,g.page,(POINT *)&place,2);
          HBRUSH bg=CreateSolidBrush(shell_colorref(shell_colors->layer_page));FillRect(underlay,&box,bg);DeleteObject(bg);
          if(page_buffer_dc) BitBlt(underlay,0,0,box.right,box.bottom,page_buffer_dc,place.left,place.top,SRCCOPY);
          GdiFlush();shell_d2d_panel(host_shell,dc,&box,shell_is_dark(),font,bits);
          SelectObject(underlay,old);
        } else shell_d2d_panel(host_shell,dc,&box,shell_is_dark(),font,NULL);
        if(bitmap) DeleteObject(bitmap);
        if(underlay) DeleteDC(underlay);
      }
      if(message==WM_PAINT) EndPaint(window,&paint);
      return 0;
    }
  }
  return DefWindowProcW(window,message,wp,lp);
}

static void shell_create_panel(HWND parent) {
  WNDCLASSW type={0};type.lpfnWndProc=shell_panel_procedure;
  type.hInstance=(HINSTANCE)GetWindowLongPtrW(parent,GWLP_HINSTANCE);type.lpszClassName=L"EXReaderSettings";
  type.hCursor=LoadCursor(NULL,IDC_ARROW);RegisterClassW(&type);
  shell_panel=CreateWindowExW(WS_EX_CONTROLPARENT,type.lpszClassName,L"阅读设置",WS_CHILD|WS_CLIPCHILDREN,
    0,0,0,0,parent,NULL,type.hInstance,NULL);
  shell_minus=shell_make_button(shell_panel,IDC_SHELL_MINUS,L"减小字号");
  shell_plus=shell_make_button(shell_panel,IDC_SHELL_PLUS,L"增大字号");
  const wchar_t *names[3]={L"浅色",L"深色",L"跟随系统"};
  for(int i=0;i<3;i++) shell_segments[i]=shell_make_button(shell_panel,IDC_SHELL_LIGHT+i,names[i]);
  ShowWindow(shell_minus,SW_SHOW);ShowWindow(shell_plus,SW_SHOW);
  for(int i=0;i<3;i++) ShowWindow(shell_segments[i],SW_SHOW);
}

static int shell_draw_settings(const DRAWITEMSTRUCT *item) {
  if(!shell_panel || GetParent(item->hwndItem)!=shell_panel || !host_shell) return 0;
  unsigned state=0;
  if(shell_hover==item->hwndItem) state|=1;
  if(item->itemState&ODS_SELECTED) state|=2;
  if((item->itemState&ODS_FOCUS) && !(item->itemState&ODS_NOFOCUSRECT)) state|=4;
  if(host_offscreen && g.drive_mode && shell_render_focus==item->hwndItem) state|=4;
  if(item->itemState&ODS_DISABLED) state|=8;
  int id=GetDlgCtrlID(item->hwndItem),variant=0;
  wchar_t text[32];GetWindowTextW(item->hwndItem,text,32);
  if(id==IDC_SHELL_MINUS) wcscpy(text,L"−");
  else if(id==IDC_SHELL_PLUS) wcscpy(text,L"+");
  else variant=id-IDC_SHELL_LIGHT==shell_theme_mode ? 1 : 2;
  shell_d2d_control(host_shell,item->hDC,&item->rcItem,text,shell_is_dark(),variant,state);
  return 1;
}

/* Warm the cached blur before input starts the animation clock. */
static void shell_prepare_settings(void) {
  RECT box={0,0,shell_px(SHELL_PANEL_W+2*SHELL_SHADOW_PAD,shell_dpi),shell_px(SHELL_PANEL_H+SHELL_SHADOW_TOP+SHELL_SHADOW_PAD,shell_dpi)};
  HDC dc=CreateCompatibleDC(NULL);if(!dc) return;
  HDC screen=GetDC(g.window);
  HBITMAP bitmap=CreateCompatibleBitmap(screen,box.right,box.bottom);ReleaseDC(g.window,screen);
  if(bitmap) {
    HGDIOBJ old=SelectObject(dc,bitmap);
    shell_d2d_panel(host_shell,dc,&box,shell_is_dark(),L"",NULL);
    box.right=shell_px(SHELL_STEPPER_W+2*SHELL_CONTROL_FRAME,shell_dpi);
    box.bottom=shell_px(SHELL_CONTROL_H+2*SHELL_CONTROL_FRAME,shell_dpi);
    shell_d2d_control(host_shell,dc,&box,L"",shell_is_dark(),0,0);
    box.right=shell_px(SHELL_SEGMENT_W+2*SHELL_CONTROL_FRAME,shell_dpi);
    shell_d2d_control(host_shell,dc,&box,L"",shell_is_dark(),1,0);
    SelectObject(dc,old);DeleteObject(bitmap);
  }
  DeleteDC(dc);
}
