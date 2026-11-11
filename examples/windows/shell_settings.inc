/* SPDX-License-Identifier: MIT */
/* Included by shell_screen.inc: UI-thread settings and theme presentation. */
static HDC page_buffer_dc; /* UI-owned backing store, defined after this include. */
/* Style fields: 3 IDs per field (minus, plus, edit). Font size is field 0. */
enum {IDC_STYLE_BASE=1800,IDC_STYLE_RESET=1840,IDC_STYLE_SAVE,IDC_STYLE_PRESET,IDC_STYLE_PRESETS};
static HWND shell_tap_buttons[2],shell_dictionary_button;
static HWND style_edits[8],style_buttons[16],style_reset,style_save,style_preset,style_presets;
static int style_refreshing;
static const float style_min[]={12,1.2f,0,0,0,0,0,-.02f};
static const float style_max[]={32,2.2f,1.5f,120,120,120,120,.06f};
static const float style_step[]={1,.05f,.1f,4,4,4,4,.01f};
/* Panel rows, top to bottom: the typography first, then the four margins. */
static const int style_rows[8]={0,1,2,7,3,5,6,4};
static const wchar_t *const style_names[8]={L"字号 px",L"行距 ×",L"段距 em",L"上边距 px",L"右边距 px",L"下边距 px",L"左边距 px",L"字距 em"};
/* Panel geometry in DIPs from the visible surface's corner. Every setting is
   one 34-high row, label left and control right (ART-DIRECTION e-4); rows are
   42 apart so that neighbouring 4-wide control frames never overlap. */
enum { PANEL_TITLE_Y=14,PANEL_ROW_Y=56,PANEL_ROW_PITCH=42,PANEL_PRESET_Y=PANEL_ROW_Y+8*PANEL_ROW_PITCH,
       PANEL_THEME_Y=PANEL_PRESET_Y+50,PANEL_TAP_Y=PANEL_THEME_Y+PANEL_ROW_PITCH,PANEL_DICTIONARY_Y=PANEL_TAP_Y+50,
       PANEL_RIGHT=SHELL_PANEL_W-SHELL_PANEL_PAD,PANEL_STEPPER_VALUE=56,PANEL_STEPPER_GAP=6,
       PANEL_PRESET_W=196,PANEL_THEME_W=222,PANEL_TAP_W=190,PANEL_TRACK_H=SHELL_SEGMENT_H+2*SHELL_SEGMENT_PAD,
       PANEL_LABELS=11 };
typedef char panel_height_matches_token[PANEL_DICTIONARY_Y+SHELL_CONTROL_H+SHELL_PANEL_PAD==SHELL_PANEL_H ? 1:-1];
static COLORREF shell_colorref(uint32_t rgb) { return RGB((rgb>>16)&255,(rgb>>8)&255,rgb&255); }

/* Every popup surface: a copy of the page pixels beneath the window goes under
   the translucent shadow and rounded corners, then the surface and its text. */
static void shell_surface_paint(HWND window,HDC dc,const RECT *box,const shell_d2d_label *labels,int count) {
  BITMAPINFO info={0};void *bits=NULL;
  info.bmiHeader.biSize=sizeof(BITMAPINFOHEADER);info.bmiHeader.biWidth=box->right;
  info.bmiHeader.biHeight=-box->bottom;info.bmiHeader.biPlanes=1;info.bmiHeader.biBitCount=32;
  HDC underlay=CreateCompatibleDC(dc);HBITMAP bitmap=CreateDIBSection(dc,&info,DIB_RGB_COLORS,&bits,NULL,0);
  if(underlay && bitmap) {
    HGDIOBJ old=SelectObject(underlay,bitmap);RECT place;GetWindowRect(window,&place);
    MapWindowPoints(NULL,g.page,(POINT *)&place,2);
    HBRUSH bg=CreateSolidBrush(shell_colorref(shell_colors->layer_page));FillRect(underlay,box,bg);DeleteObject(bg);
    if(page_buffer_dc) BitBlt(underlay,0,0,box->right,box->bottom,page_buffer_dc,place.left,place.top,SRCCOPY);
    GdiFlush();SelectObject(underlay,old);
  } else bits=NULL;
  shell_d2d_surface(host_shell,dc,box,shell_is_dark(),bits,labels,count);
  if(bitmap) DeleteObject(bitmap);
  if(underlay) DeleteDC(underlay);
}
/* A surface whose only text is its title (notes, footnotes, dictionary). */
static void shell_card_paint(HWND window,HDC dc,const RECT *box,const wchar_t *title) {
  shell_d2d_label label={title,16,10,0,26,SHELL_TEXT_TITLE};
  shell_surface_paint(window,dc,box,&label,1);
}

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
  for(size_t i=0;i<pixels;i++) {
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
  EnableWindow(style_presets,shell_preset_count>0);
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
  if(i==shell_preset_count) shell_preset_count++;
  EnableWindow(style_presets,TRUE);
  return shell_style_save();
}
static int shell_preset_use(int i) {
  if(i<0 || i>=shell_preset_count)return 0;
  shell_style=shell_presets[i].style;shell_style_changed();return 1;
}
/* Applies a saved preset and names it in the field, as the menu does. */
static int shell_preset_pick(int i) {
  if(!shell_preset_use(i)) return 0;
  wchar_t *name=host_wide(shell_presets[i].name,strlen(shell_presets[i].name));
  SetWindowTextW(style_preset,name ? name:L"");free(name);return 1;
}
static void shell_preset_menu(void) {
  HMENU menu=shell_preset_count ? CreatePopupMenu():NULL;RECT field;
  if(!menu) return;
  for(int i=0;i<shell_preset_count;i++) {
    wchar_t *name=host_wide(shell_presets[i].name,strlen(shell_presets[i].name));
    AppendMenuW(menu,MF_STRING,(UINT_PTR)i+1,name ? name:L"?");free(name);
  }
  GetWindowRect(style_presets,&field);
  int pick=TrackPopupMenu(menu,TPM_RETURNCMD|TPM_RIGHTALIGN|TPM_TOPALIGN,field.right,field.bottom,0,shell_panel,NULL);
  DestroyMenu(menu);
  if(pick>0) shell_preset_pick(pick-1);
}
static int shell_settings_command(int id) {
  if(id==IDC_SHELL_TAP20 || id==IDC_SHELL_TAP25) {
    shell_tap_edge=id==IDC_SHELL_TAP20 ? 20:25;settings_save();shell_settings_refresh();return 1;
  }
  if(id==IDC_SHELL_DICTIONARY) {shell_toggle_settings();dict_manager_open();return 1;}
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
  if(id==IDC_STYLE_PRESETS){shell_preset_menu();return 1;}
  if(id>=IDC_SHELL_LIGHT && id<=IDC_SHELL_SYSTEM) {
    shell_theme_mode=id-IDC_SHELL_LIGHT; settings_save(); shell_apply_theme(); return 1;
  }
  return 0;
}

/* Panel client pixels of a DIP box given from the surface's corner. Edges are
   rounded one by one, so adjoining boxes share their boundary at any DPI. */
static RECT panel_rect(float x,float y,float w,float h) {
  int left=shell_px(SHELL_SHADOW_PAD,shell_dpi),top=shell_px(SHELL_SHADOW_TOP,shell_dpi);
  RECT r={left+shell_px(x,shell_dpi),top+shell_px(y,shell_dpi),left+shell_px(x+w,shell_dpi),top+shell_px(y+h,shell_dpi)};
  return r;
}
/* A button's window is its visual box plus the frame for its shadow and ring. */
static void panel_place(HWND control,float x,float y,float w,float h) {
  RECT r=panel_rect(x-SHELL_CONTROL_FRAME,y-SHELL_CONTROL_FRAME,w+2*SHELL_CONTROL_FRAME,h+2*SHELL_CONTROL_FRAME);
  MoveWindow(control,r.left,r.top,r.right-r.left,r.bottom-r.top,TRUE);
}
/* A single-line EDIT as tall as its font, centred in a row-high box. */
static void panel_place_edit(HWND edit,float x,float y,float w,HFONT font) {
  RECT r=panel_rect(x,y,w,SHELL_CONTROL_H);int line=shell_gdi_line(font);
  SendMessageW(edit,WM_SETFONT,(WPARAM)font,FALSE);
  MoveWindow(edit,r.left,r.top+(r.bottom-r.top-line)/2,r.right-r.left,line,TRUE);
}
/* Equal whole-pixel segments, the track ending at the right padding. */
static void panel_place_track(HWND *segments,int count,float y,float width) {
  RECT r=panel_rect(PANEL_RIGHT-width,y+(SHELL_CONTROL_H-PANEL_TRACK_H)/2.f,width,PANEL_TRACK_H);
  int each=(r.right-r.left)/count;
  for(int i=0;i<count;i++) MoveWindow(segments[i],r.right-(count-i)*each,r.top,each,r.bottom-r.top,TRUE);
}
static RECT panel_preset_field(void) {
  return panel_rect(SHELL_PANEL_PAD-SHELL_CONTROL_FRAME,PANEL_PRESET_Y-SHELL_CONTROL_FRAME,
    PANEL_PRESET_W+2*SHELL_CONTROL_FRAME,SHELL_CONTROL_H+2*SHELL_CONTROL_FRAME);
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
  HFONT value=shell_gdi_font(SHELL_VALUE_FONT,SHELL_CONTROL_WEIGHT);
  const float stepper=PANEL_RIGHT-2*SHELL_STEPPER_W-2*PANEL_STEPPER_GAP-PANEL_STEPPER_VALUE;
  panel_place(style_reset,PANEL_RIGHT-80,PANEL_TITLE_Y,80,SHELL_CONTROL_H);
  for(int row=0;row<8;row++) {
    int i=style_rows[row];float y=(float)(PANEL_ROW_Y+row*PANEL_ROW_PITCH);
    panel_place(style_buttons[2*i],stepper,y,SHELL_STEPPER_W,SHELL_CONTROL_H);
    panel_place_edit(style_edits[i],stepper+SHELL_STEPPER_W+PANEL_STEPPER_GAP,y,PANEL_STEPPER_VALUE,value);
    panel_place(style_buttons[2*i+1],PANEL_RIGHT-SHELL_STEPPER_W,y,SHELL_STEPPER_W,SHELL_CONTROL_H);
  }
  /* Preset name inside its field frame, the list button at the field's end. */
  panel_place_edit(style_preset,SHELL_PANEL_PAD+12,PANEL_PRESET_Y,PANEL_PRESET_W-12-36,shell_gdi_font(SHELL_VALUE_FONT,FW_NORMAL));
  RECT list=panel_rect(SHELL_PANEL_PAD+PANEL_PRESET_W-37,PANEL_PRESET_Y+1,36,SHELL_CONTROL_H-2);
  MoveWindow(style_presets,list.left,list.top,list.right-list.left,list.bottom-list.top,TRUE);
  panel_place(style_save,SHELL_PANEL_PAD+PANEL_PRESET_W+8,PANEL_PRESET_Y,PANEL_RIGHT-SHELL_PANEL_PAD-PANEL_PRESET_W-8,SHELL_CONTROL_H);
  panel_place_track(shell_segments,3,PANEL_THEME_Y,PANEL_THEME_W);
  panel_place_track(shell_tap_buttons,2,PANEL_TAP_Y,PANEL_TAP_W);
  panel_place(shell_dictionary_button,SHELL_PANEL_PAD,PANEL_DICTIONARY_Y,PANEL_RIGHT-SHELL_PANEL_PAD,SHELL_CONTROL_H);
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

static void shell_panel_paint(HWND window,HDC dc) {
  RECT box;GetClientRect(window,&box);
  /* Animate by clipping, never rescaling the content/shadow. */
  box.bottom=shell_px(SHELL_PANEL_H+SHELL_SHADOW_TOP+SHELL_SHADOW_PAD,shell_dpi);
  if(!host_shell) return;
  shell_d2d_label labels[PANEL_LABELS]={{L"阅读设置",SHELL_PANEL_PAD,PANEL_TITLE_Y,200,SHELL_CONTROL_H,SHELL_TEXT_TITLE}};
  for(int row=0;row<8;row++)
    labels[1+row]=(shell_d2d_label){style_names[style_rows[row]],SHELL_PANEL_PAD,(float)(PANEL_ROW_Y+row*PANEL_ROW_PITCH),170,SHELL_CONTROL_H,SHELL_TEXT_LABEL};
  labels[9]=(shell_d2d_label){L"主题",SHELL_PANEL_PAD,PANEL_THEME_Y,90,SHELL_CONTROL_H,SHELL_TEXT_LABEL};
  labels[10]=(shell_d2d_label){L"点击分区 左/中/右",SHELL_PANEL_PAD,PANEL_TAP_Y,125,SHELL_CONTROL_H,SHELL_TEXT_LABEL};
  shell_surface_paint(window,dc,&box,labels,PANEL_LABELS);
  RECT field=panel_preset_field();HWND focus=GetFocus();
  shell_d2d_look look={SHELL_CONTROL_FIELD,focus==style_preset ? SHELL_STATE_FOCUS:0,shell_colors->layer_float,0,1};
  shell_d2d_control(host_shell,dc,&field,L"",shell_is_dark(),&look);
}

static LRESULT CALLBACK shell_panel_procedure(HWND window,UINT message,WPARAM wp,LPARAM lp) {
  switch(message) {
    case WM_ERASEBKGND:return 1;
    case WM_COMMAND:
      if(LOWORD(wp)==IDC_STYLE_PRESET) {
        if(HIWORD(wp)==EN_SETFOCUS || HIWORD(wp)==EN_KILLFOCUS) {RECT field=panel_preset_field();InvalidateRect(window,&field,FALSE);}
        return 0;
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
    case WM_CTLCOLOREDIT:case WM_CTLCOLORSTATIC: {
      static HBRUSH brush;static uint32_t color;
      if(!brush || color!=shell_colors->layer_float){if(brush)DeleteObject(brush);color=shell_colors->layer_float;brush=CreateSolidBrush(shell_colorref(color));}
      SetTextColor((HDC)wp,shell_colorref(shell_colors->text));SetBkColor((HDC)wp,shell_colorref(color));return (LRESULT)brush;
    }
    case WM_DRAWITEM: if(shell_draw_settings((const DRAWITEMSTRUCT *)lp)) return TRUE;break;
    case WM_PAINT: {PAINTSTRUCT paint;shell_panel_paint(window,BeginPaint(window,&paint));EndPaint(window,&paint);return 0;}
    case WM_PRINTCLIENT: shell_panel_paint(window,(HDC)wp);return 0;
  }
  return DefWindowProcW(window,message,wp,lp);
}

static HWND shell_panel_button(int id,const wchar_t *name) {
  HWND button=shell_make_button(shell_panel,id,name);
  ShowWindow(button,SW_SHOW);return button;
}
static void shell_create_panel(HWND parent) {
  WNDCLASSW type={0};type.lpfnWndProc=shell_panel_procedure;
  type.hInstance=(HINSTANCE)GetWindowLongPtrW(parent,GWLP_HINSTANCE);type.lpszClassName=L"EXReaderSettings";
  type.hCursor=LoadCursor(NULL,IDC_ARROW);RegisterClassW(&type);
  shell_panel=CreateWindowExW(WS_EX_CONTROLPARENT,type.lpszClassName,L"阅读设置",WS_CHILD|WS_CLIPCHILDREN,
    0,0,0,0,parent,NULL,type.hInstance,NULL);
  /* Creation order is the Tab order: top to bottom, as the rows are drawn. */
  style_reset=shell_panel_button(IDC_STYLE_RESET,L"恢复默认");
  for(int row=0;row<8;row++) {
    int i=style_rows[row];
    style_buttons[2*i]=shell_panel_button(IDC_STYLE_BASE+3*i,L"−");
    style_edits[i]=CreateWindowExW(0,L"EDIT",L"",WS_CHILD|WS_VISIBLE|WS_TABSTOP|ES_CENTER|ES_AUTOHSCROLL,
      0,0,0,0,shell_panel,(HMENU)(INT_PTR)(IDC_STYLE_BASE+3*i+2),type.hInstance,NULL);
    SendMessageW(style_edits[i],EM_SETLIMITTEXT,16,0);
    style_buttons[2*i+1]=shell_panel_button(IDC_STYLE_BASE+3*i+1,L"+");
  }
  shell_minus=style_buttons[0];shell_plus=style_buttons[1];
  style_preset=CreateWindowExW(0,L"EDIT",L"预设 1",WS_CHILD|WS_VISIBLE|WS_TABSTOP|ES_AUTOHSCROLL,
    0,0,0,0,shell_panel,(HMENU)(INT_PTR)IDC_STYLE_PRESET,type.hInstance,NULL);
  SendMessageW(style_preset,EM_SETLIMITTEXT,40,0);
  style_presets=shell_panel_button(IDC_STYLE_PRESETS,L"▾");
  style_save=shell_panel_button(IDC_STYLE_SAVE,L"保存为预设");
  const wchar_t *names[3]={L"浅色",L"深色",L"跟随系统"};
  for(int i=0;i<3;i++) shell_segments[i]=shell_panel_button(IDC_SHELL_LIGHT+i,names[i]);
  shell_tap_buttons[0]=shell_panel_button(IDC_SHELL_TAP20,L"20 / 60 / 20");
  shell_tap_buttons[1]=shell_panel_button(IDC_SHELL_TAP25,L"25 / 50 / 25");
  shell_dictionary_button=shell_panel_button(IDC_SHELL_DICTIONARY,L"词典与生词本");
  shell_settings_refresh();
}

static int shell_draw_settings(const DRAWITEMSTRUCT *item) {
  if(!shell_panel || GetParent(item->hwndItem)!=shell_panel || !host_shell) return 0;
  int id=GetDlgCtrlID(item->hwndItem);
  wchar_t text[32];GetWindowTextW(item->hwndItem,text,32);
  shell_d2d_look look={SHELL_CONTROL_STANDARD,shell_item_state(item),shell_colors->layer_float,0,1};
  if(id==IDC_SHELL_TAP20 || id==IDC_SHELL_TAP25) {
    look.kind=SHELL_CONTROL_SEGMENT;look.index=id-IDC_SHELL_TAP20;look.count=2;
    if(shell_tap_edge==(id==IDC_SHELL_TAP20 ? 20:25)) look.state|=SHELL_STATE_SELECTED;
  } else if(id>=IDC_SHELL_LIGHT && id<=IDC_SHELL_SYSTEM) {
    look.kind=SHELL_CONTROL_SEGMENT;look.index=id-IDC_SHELL_LIGHT;look.count=3;
    if(look.index==shell_theme_mode) look.state|=SHELL_STATE_SELECTED;
  } else if(id==IDC_STYLE_RESET || id==IDC_STYLE_PRESETS) look.kind=SHELL_CONTROL_GHOST;
  shell_d2d_control(host_shell,item->hDC,&item->rcItem,text,shell_is_dark(),&look);
  return 1;
}

/* Warm the cached blurs before input starts the animation clock: the surface
   and every button at the size the layout gives it. */
static void shell_prepare_settings(void) {
  RECT box={0,0,shell_px(SHELL_PANEL_W+2*SHELL_SHADOW_PAD,shell_dpi),shell_px(SHELL_PANEL_H+SHELL_SHADOW_TOP+SHELL_SHADOW_PAD,shell_dpi)};
  HDC dc=CreateCompatibleDC(NULL);if(!dc) return;
  HDC screen=GetDC(g.window);
  HBITMAP bitmap=CreateCompatibleBitmap(screen,box.right,box.bottom);ReleaseDC(g.window,screen);
  if(bitmap) {
    HGDIOBJ old=SelectObject(dc,bitmap);
    shell_d2d_surface(host_shell,dc,&box,shell_is_dark(),NULL,NULL,0);
    shell_panel_layout();
    for(HWND child=GetWindow(shell_panel,GW_CHILD);child;child=GetWindow(child,GW_HWNDNEXT)) {
      DRAWITEMSTRUCT item={0};wchar_t type[8];
      if(!GetClassNameW(child,type,8) || _wcsicmp(type,L"Button")) continue;
      item.hwndItem=child;item.hDC=dc;GetClientRect(child,&item.rcItem);
      shell_draw_settings(&item);
    }
    SelectObject(dc,old);DeleteObject(bitmap);
  }
  DeleteDC(dc);
}
