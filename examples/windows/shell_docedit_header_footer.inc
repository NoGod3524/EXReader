/* SPDX-License-Identifier: MIT */
/* L13: one active story. Body positions stay intact while a margin is edited. */
static exr_edit_id de_hf_section(void) {
  if(de.hf_mode && de.hf_section)return de.hf_section;
  const exr_edit_block *b=de_block_at(de.doc,de.caret.view);
  size_t count=0;const exr_edit_section *sections=exr_edit_sections(de.doc,&count);
  return b ? b->section_id:count ? sections[0].id:0;
}
static RECT de_hf_box(unsigned footer) {
  shell_d2d_edit_row *row=&de.hf_rows[footer];
  RECT box={(LONG)de.inset,(LONG)(row->y-de.scroll_y-shell_px(20,shell_dpi)),
    (LONG)(de.width-de.inset),(LONG)(row->y+row->height-de.scroll_y)};
  return box;
}
static int de_hf_measure(unsigned footer,float y) {
  if(!footer && de.hf_variant) {
    unsigned first=0,even=0;
    if(exr_edit_header_footer_flags(de.doc,de_hf_section(),&first,&even)==EXR_OK &&
      ((de.hf_variant==1 && !first) || (de.hf_variant==2 && !even))) {
      de.hf_variant=0;de.hf_caret=de.hf_anchor=0;
    }
  }
  exr_status status=exr_edit_header_footer_text(de.doc,de_hf_section(),footer,de.hf_variant,
    &de.hf_text[footer],&de.hf_size[footer]);
  if(status!=EXR_OK)return 0;
  wchar_t *text=host_wide(de.hf_text[footer],de.hf_size[footer]);
  if(!text)return 0;
  shell_d2d_edit_row *row=&de.hf_rows[footer];
  HRESULT hr=shell_d2d_edit_layout(host_shell,text,g.font_family[0] ? g.font_family:L"Segoe UI",
    16.f*shell_dpi/96.f,de.width-2*de.inset,&row->layout,&row->height);
  free(text);if(FAILED(hr))return 0;
  row->y=y+shell_px(20,shell_dpi);
  if(row->height<shell_px(28,shell_dpi))row->height=(float)shell_px(28,shell_dpi);
  if(de.hf_mode==footer+1) {
    if(de.hf_caret>de.hf_size[footer])de.hf_caret=de.hf_size[footer];
    if(de.hf_anchor>de.hf_size[footer])de.hf_anchor=de.hf_size[footer];
    while(de.hf_caret<de.hf_size[footer] && ((unsigned char)de.hf_text[footer][de.hf_caret]&0xc0)==0x80)de.hf_caret--;
    while(de.hf_anchor<de.hf_size[footer] && ((unsigned char)de.hf_text[footer][de.hf_anchor]&0xc0)==0x80)de.hf_anchor--;
  }
  return 1;
}
static void de_hf_refresh(int reveal) {
  de.layout_dirty=1;
  if(de.width && de.height)de_measure(de.width,de.height);
  de_refresh(reveal);
  /* Console drivers have no page HWND; use the same reveal geometry there. */
  if(!g.page && reveal && de.hf_mode) {
    shell_d2d_edit_row *row=&de.hf_rows[de.hf_mode-1];float box[4];
    if(row->layout) {
      shell_d2d_edit_position(row->layout,de_units(de.hf_text[de.hf_mode-1],de.hf_caret),box);
      float top=row->y+box[1],bottom=top+box[3];
      if(top<de.scroll_y+de_toolbar_height())de.scroll_y=top-de_toolbar_height();
      if(bottom>de.scroll_y+de.height)de.scroll_y=bottom-de.height;
      de_scroll(0);
    }
  }
}
static int de_hf_enter(unsigned footer) {
  if(!de.doc || footer>1)return 0;
  de.hf_section=de_hf_section();de.hf_mode=footer+1;
  de.hf_caret=de.hf_anchor=0;de.high_surrogate=0;de.mouse_down=0;de.color_panel=0;
  if(g.page) {if(GetCapture()==g.page)ReleaseCapture();SetFocus(g.page);}
  de_hf_refresh(1);
  set_status(footer ? L"正在编辑页脚；Esc 或双击正文返回。":L"正在编辑页眉；Esc 或双击正文返回。");
  return 1;
}
static void de_hf_leave(void) {
  de.hf_mode=0;de.hf_section=0;de.high_surrogate=0;de.mouse_down=0;
  if(g.page && GetCapture()==g.page)ReleaseCapture();
  de_hf_refresh(1);set_status(L"正在编辑正文。");
}
static int de_hf_command(int command) {
  if(command==DE_HEADER || command==DE_FOOTER)return de_hf_enter(command==DE_FOOTER);
  unsigned first=0,even=0;exr_edit_id section=de_hf_section();
  if(exr_edit_header_footer_flags(de.doc,section,&first,&even)!=EXR_OK)return 0;
  if(command==DE_VARIANT) {
    do {de.hf_variant=(de.hf_variant+1)%3;}
    while((de.hf_variant==1 && !first) || (de.hf_variant==2 && !even));
  } else {
    if(command==DE_DIFFERENT_FIRST)first=!first;
    else if(command==DE_DIFFERENT_EVEN)even=!even;
    else return 0;
    exr_status status=exr_edit_set_header_footer_flags(de.doc,section,first,even);
    if(status!=EXR_OK) {de_error(L"无法修改页眉页脚选项",status,NULL);return 0;}
    de.dirty=1;
    if((de.hf_variant==1 && !first) || (de.hf_variant==2 && !even))de.hf_variant=0;
  }
  de.hf_caret=de.hf_anchor=0;de_hf_refresh(1);return 1;
}
static int de_hf_edit(int operation,const char *text,size_t n) {
  unsigned footer=de.hf_mode-1;
  if(footer>1 || !de_measure(de.width,de.height))return 0;
  const char *old=de.hf_text[footer];size_t size=de.hf_size[footer];
  size_t a=de.hf_anchor,b=de.hf_caret;if(a>b) {size_t t=a;a=b;b=t;}
  if(a==b && operation==DE_BACKSPACE)a=de_prev_byte(old,a);
  if(a==b && operation==DE_DELETE)b=de_next_byte(old,size,b);
  if(operation==DE_ENTER) {text="\n";n=1;}
  else if(operation!=DE_TYPE)n=0;
  if(n>SIZE_MAX-(size-(b-a))-1)return 0;
  size_t length=size-(b-a)+n;char *value=malloc(length+1);if(!value)return 0;
  memcpy(value,old,a);if(n)memcpy(value+a,text,n);memcpy(value+a+n,old+b,size-b);value[length]=0;
  exr_status status=exr_edit_set_header_footer_text(de.doc,de.hf_section,footer,de.hf_variant,value,length);
  free(value);
  if(status!=EXR_OK) {de_error(L"无法编辑页眉页脚",status,NULL);return 0;}
  de.hf_caret=de.hf_anchor=a+n;de.dirty=1;de_hf_refresh(1);return 1;
}
static size_t de_hf_from_units(unsigned footer,unsigned units) {
  const char *text=de.hf_text[footer];size_t n=de.hf_size[footer],at=0;unsigned used=0;
  while(at<n) {
    size_t next=de_next_byte(text,n,at);unsigned step=de_units(text+at,next-at);
    if(used+step>units)break;used+=step;at=next;
  }
  return at;
}
static int de_hf_key(WPARAM key,int control,int shift) {
  if(key==VK_ESCAPE) {de_hf_leave();return 1;}
  unsigned footer=de.hf_mode-1;
  if(!de_measure(de.width,de.height))return 1;
  const char *text=de.hf_text[footer];size_t size=de.hf_size[footer];
  if(control) {
    if(key=='S')de_save();
    else if(key=='A') {de.hf_anchor=0;de.hf_caret=size;de_refresh(1);}
    else if(key=='Z' || key=='Y') {
      exr_status status=key=='Y' ? exr_edit_redo(de.doc):exr_edit_undo(de.doc);
      if(status==EXR_OK) {de.dirty=1;de_hf_refresh(1);}
    } else if(key==VK_HOME || key==VK_END) {
      de.hf_caret=key==VK_HOME ? 0:size;
      if(!shift)de.hf_anchor=de.hf_caret;de_refresh(1);
    }
    return 1;
  }
  if(key==VK_BACK || key==VK_DELETE || key==VK_RETURN) {
    de_hf_edit(key==VK_BACK ? DE_BACKSPACE:key==VK_DELETE ? DE_DELETE:DE_ENTER,NULL,0);return 1;
  }
  if(key==VK_TAB) {de_hf_edit(DE_TYPE,"\t",1);return 1;}
  if(key==VK_PRIOR || key==VK_NEXT) {de_scroll((float)(key==VK_PRIOR ? -de.height:de.height));return 1;}
  if(key!=VK_LEFT && key!=VK_RIGHT && key!=VK_UP && key!=VK_DOWN && key!=VK_HOME && key!=VK_END)return 0;
  if(!shift && de.hf_caret!=de.hf_anchor && (key==VK_LEFT || key==VK_RIGHT)) {
    size_t a=de.hf_anchor,b=de.hf_caret;
    de.hf_caret=key==VK_LEFT ? (a<b ? a:b):(a>b ? a:b);
  } else if(key==VK_LEFT)de.hf_caret=de_prev_byte(text,de.hf_caret);
  else if(key==VK_RIGHT)de.hf_caret=de_next_byte(text,size,de.hf_caret);
  else {
    shell_d2d_edit_row *row=&de.hf_rows[footer];float box[4];
    shell_d2d_edit_position(row->layout,de_units(text,de.hf_caret),box);
    float x=key==VK_HOME ? 0:key==VK_END ? (float)de.width:box[0];
    float y=box[1]+(key==VK_UP ? -.5f:key==VK_DOWN ? 1.5f:.5f)*box[3];
    de.hf_caret=de_hf_from_units(footer,shell_d2d_edit_hit(row->layout,x,y));
  }
  if(!shift)de.hf_anchor=de.hf_caret;de_refresh(1);return 1;
}
static int de_hf_mouse(HWND window,UINT message,LPARAM lparam) {
  POINT point={(short)LOWORD(lparam),(short)HIWORD(lparam)};
  if(message==WM_LBUTTONUP) {
    if(!de.hf_mode)return 0;
    de.mouse_down=0;if(window && GetCapture()==window)ReleaseCapture();return 1;
  }
  if(point.y<de_toolbar_height()) {
    if(message==WM_LBUTTONDOWN) {if(window)SetFocus(window);return de_toolbar_click((float)point.x,(float)point.y);}
    return 1;
  }
  int region=0;
  for(unsigned i=0;i<2;i++) {RECT box=de_hf_box(i);if(PtInRect(&box,point))region=(int)i+1;}
  if(message==WM_LBUTTONDBLCLK) {
    if(region)de_hf_enter((unsigned)region-1);
    else if(de.hf_mode) {
      de_hf_leave();de_set_caret(de_hit((float)point.x,(float)point.y));de_set_anchor(de_caret_pos());de_refresh(1);
    }
    return 1;
  }
  if(!de.hf_mode)return region!=0;
  if(region!=(int)de.hf_mode && !de.mouse_down)return 1;
  unsigned footer=de.hf_mode-1;shell_d2d_edit_row *row=&de.hf_rows[footer];
  if(message==WM_LBUTTONDOWN) {
    if(window) {SetFocus(window);SetCapture(window);}de.mouse_down=1;
  }
  de.hf_caret=de_hf_from_units(footer,shell_d2d_edit_hit(row->layout,
    point.x-de.inset,point.y+de.scroll_y-row->y));
  if(message==WM_LBUTTONDOWN && !(GetKeyState(VK_SHIFT)&0x8000))de.hf_anchor=de.hf_caret;
  de_refresh(1);return 1;
}
static HRESULT de_hf_labels(HDC dc) {
  for(unsigned i=0;i<2;i++) {
    RECT box=de_hf_box(i);box.bottom=box.top+shell_px(20,shell_dpi);
    if(box.top<de_toolbar_height() || box.top>de.height)continue;
    const wchar_t *variant=de.hf_variant==1 ? L" · 首页":de.hf_variant==2 ? L" · 偶数页":L"";
    wchar_t label[96];swprintf(label,96,L"%ls%ls%ls",i ? L"页脚":L"页眉",variant,
      de.hf_mode==i+1 ? L" · Esc 返回正文":L" · 双击编辑");
    uint32_t color=de.hf_mode==i+1 ? shell_colors->accent:shell_colors->text_disabled;
    HRESULT hr=shell_d2d_dc_text(host_shell,dc,&box,label,0,0,color,color);
    if(FAILED(hr))return hr;
  }
  return S_OK;
}
