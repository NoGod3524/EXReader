/* SPDX-License-Identifier: MIT */
/* Included by shell_screen.inc: UI-thread settings and theme presentation. */
static HDC page_buffer_dc; /* UI-owned backing store, defined after this include. */
static HWND shell_tap_buttons[2];
enum { IDC_SHELL_MINUS=162, IDC_SHELL_PLUS, IDC_SHELL_LIGHT, IDC_SHELL_DARK, IDC_SHELL_SYSTEM };
/* Keep style controls distinct from the shelf/back/tap command IDs (180..182). */
enum {IDC_STYLE_BASE=1800,IDC_STYLE_RESET=1840,IDC_STYLE_SAVE,IDC_STYLE_PRESET};
static HWND style_edits[8],style_buttons[16],style_reset,style_save,style_preset;
static int style_refreshing;
static const float style_min[]={12,1.2f,0,0,0,0,0,-.02f};
static const float style_max[]={32,2.2f,1.5f,120,120,120,120,.06f};
static const float style_step[]={1,.05f,.1f,4,4,4,4,.01f};
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
  size_t pixels=(size_t)frame->display_width*frame->display_height, colored=0;
  for(size_t i=0;i<pixels;i++) {
    uint32_t q=src[i];unsigned b=q&255,gc=(q>>8)&255,r=(q>>16)&255;
    colored+=r!=gc || gc!=b;
  }
  /* Opaque book-painted paper carries its own ink contrast. Recolouring just
     its grayscale ink produces white interiors with dark edges in dark mode. */
  frame->display_shell_paper=colored>pixels/2;
  uint32_t shades[256];
  for(unsigned i=0;i<256;i++) shades[i]=shell_blend(shell_colors->text,shell_colors->layer_page,i/255.f);
  for(size_t i=0;i<(size_t)frame->display_width*frame->display_height;i++) {
    uint32_t q=src[i];unsigned b=q&255,gc=(q>>8)&255,r=(q>>16)&255;
    dst[i]=(!frame->display_shell_paper && r==gc && gc==b) ? shades[r] : q;
  }
  frame->display_shell_theme=theme;
}

static void shell_settings_refresh(void) {
  style_refreshing=1;shell_style.font_size=shell_font;
  for(int i=0;i<8;i++) if(style_edits[i]) {
    wchar_t value[32];swprintf(value,32,i==0 || (i>=3 && i<=6)?L"%.0f":L"%.2f",(double)*style_value(&shell_style,i));
    SetWindowTextW(style_edits[i],value);
    EnableWindow(style_edits[i],!g.frame.fixed);
  }
  style_refreshing=0;
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

static void shell_style_changed(void) {
  shell_font=shell_style.font_size;shell_footnote_close();
  shell_request_layout();settings_save();shell_settings_refresh();
}
static int shell_style_set(int i,float value) {
  exr_reader_style next=shell_style;next.font_size=shell_font;
  if(i<0 || i>=8)return 0;
  *style_value(&next,i)=value;if(!style_valid(next))return 0;
  shell_style=next;shell_style_changed();return 1;
}
static int shell_preset_save(const wchar_t *name) {
  char *utf8=host_utf8(name);if(!utf8 || !*utf8 || strlen(utf8)>=128){free(utf8);return 0;}
  int i;for(i=0;i<shell_preset_count;i++)if(!strcmp(shell_presets[i].name,utf8))break;
  if(i==16){free(utf8);return 0;}
  shell_style.font_size=shell_font;shell_presets[i].style=shell_style;strcpy(shell_presets[i].name,utf8);free(utf8);
  if(i==shell_preset_count) {
    shell_preset_count++;SendMessageW(style_preset,CB_ADDSTRING,0,(LPARAM)name);
  }
  return shell_style_save();
}
static int shell_preset_use(int i) {
  if(i<0 || i>=shell_preset_count)return 0;
  shell_style=shell_presets[i].style;shell_style_changed();return 1;
}
static int shell_settings_command(int id) {
  if(id==IDC_SHELL_TAP20 || id==IDC_SHELL_TAP25) {
    shell_tap_edge=id==IDC_SHELL_TAP20 ? 20:25;settings_save();shell_settings_refresh();return 1;
  }
  if(id==IDC_SHELL_DICTIONARY) {shell_toggle_settings();dict_manager_open();return 1;}
  if(id==IDC_SHELL_MINUS || id==IDC_SHELL_PLUS) { shell_step_font(id==IDC_SHELL_PLUS ? 1 : -1);return 1; }
  if(id>=IDC_STYLE_BASE && id<IDC_STYLE_BASE+24) {
    int i=(id-IDC_STYLE_BASE)/3,op=(id-IDC_STYLE_BASE)%3;
    if(op<2) {
      shell_style.font_size=shell_font;float v=*style_value(&shell_style,i)+(op ? 1:-1)*style_step[i];
      shell_style_set(i,fmaxf(style_min[i],fminf(style_max[i],roundf(v*100)/100)));
    }
    return 1;
  }
  if(id==IDC_STYLE_RESET){shell_style=exr_reader_style_defaults();shell_style_changed();return 1;}
  if(id==IDC_STYLE_SAVE){wchar_t name[64];GetWindowTextW(style_preset,name,64);if(!shell_preset_save(name))set_status(L"无法保存预设。");return 1;}
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
  for(int i=0;i<8;i++) {
    int y=48+i*42;
    MoveWindow(style_buttons[2*i],kpad+shell_px(166,shell_dpi),top+shell_px(y,shell_dpi),shell_px(34,shell_dpi),shell_px(32,shell_dpi),TRUE);
    MoveWindow(style_edits[i],kpad+shell_px(208,shell_dpi),top+shell_px(y+3,shell_dpi),shell_px(66,shell_dpi),shell_px(26,shell_dpi),TRUE);
    MoveWindow(style_buttons[2*i+1],kpad+shell_px(282,shell_dpi),top+shell_px(y,shell_dpi),shell_px(34,shell_dpi),shell_px(32,shell_dpi),TRUE);
  }
  for(int i=0;i<3;i++)MoveWindow(shell_segments[i],kpad+shell_px(20+i*96,shell_dpi),top+shell_px(394,shell_dpi),shell_px(92,shell_dpi),shell_px(32,shell_dpi),TRUE);
  MoveWindow(style_preset,kpad+shell_px(20,shell_dpi),top+shell_px(452,shell_dpi),shell_px(190,shell_dpi),shell_px(200,shell_dpi),TRUE);
  MoveWindow(style_save,kpad+shell_px(220,shell_dpi),top+shell_px(448,shell_dpi),shell_px(112,shell_dpi),shell_px(34,shell_dpi),TRUE);
  MoveWindow(style_reset,kpad+shell_px(20,shell_dpi),top+shell_px(506,shell_dpi),shell_px(148,shell_dpi),shell_px(34,shell_dpi),TRUE);
  for(int i=0;i<2;i++)MoveWindow(shell_tap_buttons[i],kpad+shell_px(20+156*i,shell_dpi),top+shell_px(586,shell_dpi),shell_px(148,shell_dpi),shell_px(32,shell_dpi),TRUE);
  MoveWindow(GetDlgItem(shell_panel,IDC_SHELL_DICTIONARY),kpad+shell_px(176,shell_dpi),top+shell_px(506,shell_dpi),shell_px(156,shell_dpi),shell_px(34,shell_dpi),TRUE);
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
  if(!shell_panel_open && shell_toc_open) shell_toc_set(0,0);
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
    case WM_COMMAND:
      if(LOWORD(wp)==IDC_STYLE_PRESET && HIWORD(wp)==CBN_SELCHANGE) {
        shell_preset_use((int)SendMessageW(style_preset,CB_GETCURSEL,0,0));return 0;
      }
      if(LOWORD(wp)>=IDC_STYLE_BASE && LOWORD(wp)<IDC_STYLE_BASE+24 && (LOWORD(wp)-IDC_STYLE_BASE)%3==2) {
        if(HIWORD(wp)==EN_KILLFOCUS && !style_refreshing) {
          int i=(LOWORD(wp)-IDC_STYLE_BASE)/3;wchar_t text[64],*end;GetWindowTextW(style_edits[i],text,64);
          double v=wcstod(text,&end);if(end==text || *end || !shell_style_set(i,(float)v))shell_settings_refresh();
        }
        return 0;
      }
      if(shell_settings_command(LOWORD(wp))) return 0;
      break;
    case WM_CTLCOLOREDIT:case WM_CTLCOLORSTATIC:case WM_CTLCOLORLISTBOX: {
      static HBRUSH brush;static uint32_t color;
      if(!brush || color!=shell_colors->layer_float){if(brush)DeleteObject(brush);color=shell_colors->layer_float;brush=CreateSolidBrush(shell_colorref(color));}
      SetTextColor((HDC)wp,shell_colorref(shell_colors->text));SetBkColor((HDC)wp,shell_colorref(color));return (LRESULT)brush;
    }
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
          GdiFlush();shell_d2d_panel(host_shell,dc,&box,shell_is_dark(),font,g.font_label,g.font_path,bits);
          SelectObject(underlay,old);
        } else shell_d2d_panel(host_shell,dc,&box,shell_is_dark(),font,g.font_label,g.font_path,NULL);
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
  HFONT font=(HFONT)GetStockObject(DEFAULT_GUI_FONT);
  for(int i=0;i<8;i++) {
    style_buttons[2*i]=shell_make_button(shell_panel,IDC_STYLE_BASE+3*i,L"−");
    style_buttons[2*i+1]=shell_make_button(shell_panel,IDC_STYLE_BASE+3*i+1,L"+");
    style_edits[i]=CreateWindowExW(0,L"EDIT",L"",WS_CHILD|WS_VISIBLE|WS_TABSTOP|ES_CENTER|ES_AUTOHSCROLL,
      0,0,0,0,shell_panel,(HMENU)(INT_PTR)(IDC_STYLE_BASE+3*i+2),type.hInstance,NULL);
    SendMessageW(style_edits[i],WM_SETFONT,(WPARAM)font,0);SendMessageW(style_edits[i],EM_SETLIMITTEXT,16,0);
    ShowWindow(style_buttons[2*i],SW_SHOW);ShowWindow(style_buttons[2*i+1],SW_SHOW);
  }
  shell_minus=style_buttons[0];shell_plus=style_buttons[1];
  const wchar_t *names[3]={L"浅色",L"深色",L"跟随系统"};
  for(int i=0;i<3;i++){shell_segments[i]=shell_make_button(shell_panel,IDC_SHELL_LIGHT+i,names[i]);ShowWindow(shell_segments[i],SW_SHOW);}
  style_preset=CreateWindowExW(0,L"COMBOBOX",L"",WS_CHILD|WS_VISIBLE|WS_TABSTOP|CBS_DROPDOWN|WS_VSCROLL,
    0,0,0,0,shell_panel,(HMENU)IDC_STYLE_PRESET,type.hInstance,NULL);
  SendMessageW(style_preset,WM_SETFONT,(WPARAM)font,0);SendMessageW(style_preset,CB_LIMITTEXT,40,0);
  for(int i=0;i<shell_preset_count;i++){wchar_t *name=host_wide(shell_presets[i].name,strlen(shell_presets[i].name));SendMessageW(style_preset,CB_ADDSTRING,0,(LPARAM)name);free(name);}
  SetWindowTextW(style_preset,L"预设 1");
  style_save=shell_make_button(shell_panel,IDC_STYLE_SAVE,L"保存为预设");ShowWindow(style_save,SW_SHOW);
  style_reset=shell_make_button(shell_panel,IDC_STYLE_RESET,L"恢复默认");ShowWindow(style_reset,SW_SHOW);
  shell_settings_refresh();
  shell_tap_buttons[0]=shell_make_button(shell_panel,IDC_SHELL_TAP20,L"20 / 60 / 20");
  shell_tap_buttons[1]=shell_make_button(shell_panel,IDC_SHELL_TAP25,L"25 / 50 / 25");
  for(int i=0;i<2;i++)ShowWindow(shell_tap_buttons[i],SW_SHOW);
  HWND dictionary=shell_make_button(shell_panel,IDC_SHELL_DICTIONARY,L"词典与生词本");ShowWindow(dictionary,SW_SHOW);
}

static int shell_draw_settings(const DRAWITEMSTRUCT *item) {
  if(!shell_panel || GetParent(item->hwndItem)!=shell_panel || !host_shell) return 0;
  unsigned state=0;
  if(shell_hover==item->hwndItem) state|=1;
  if(item->itemState&ODS_SELECTED) state|=2;
  if((item->itemState&ODS_FOCUS) && !(item->itemState&ODS_NOFOCUSRECT)) state|=4;
  if(host_offscreen && g.drive_mode && shell_render_focus==item->hwndItem &&
     !(SendMessageW(item->hwndItem,WM_QUERYUISTATE,0,0)&UISF_HIDEFOCUS)) state|=4;
  if(item->itemState&ODS_DISABLED) state|=8;
  int id=GetDlgCtrlID(item->hwndItem),variant=0;
  wchar_t text[32];GetWindowTextW(item->hwndItem,text,32);
  if(id==IDC_SHELL_MINUS) wcscpy(text,L"−");
  else if(id==IDC_SHELL_PLUS) wcscpy(text,L"+");
  else if(id==IDC_SHELL_TAP20 || id==IDC_SHELL_TAP25) variant=(id==IDC_SHELL_TAP20 ? shell_tap_edge==20:shell_tap_edge==25) ? 1:2;
  else if(id>=IDC_SHELL_LIGHT && id<=IDC_SHELL_SYSTEM) variant=id-IDC_SHELL_LIGHT==shell_theme_mode ? 1 : 2;
  else if(id==IDC_SHELL_DICTIONARY) variant=2;
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
    shell_d2d_panel(host_shell,dc,&box,shell_is_dark(),L"",g.font_label,g.font_path,NULL);
    box.right=shell_px(SHELL_STEPPER_W+2*SHELL_CONTROL_FRAME,shell_dpi);
    box.bottom=shell_px(SHELL_CONTROL_H+2*SHELL_CONTROL_FRAME,shell_dpi);
    shell_d2d_control(host_shell,dc,&box,L"",shell_is_dark(),0,0);
    box.right=shell_px(SHELL_SEGMENT_W+2*SHELL_CONTROL_FRAME,shell_dpi);
    shell_d2d_control(host_shell,dc,&box,L"",shell_is_dark(),1,0);
    SelectObject(dc,old);DeleteObject(bitmap);
  }
  DeleteDC(dc);
}
