/* SPDX-License-Identifier: MIT */
/* L07: native command controls; table input uses the same handlers headlessly. */
enum { DA_TEXT,DA_PREV,DA_NEXT,DA_RUN,DA_ADD,DA_REMOVE,DA_TABLE,
  DA_BOLD,DA_ITALIC,DA_SMALL,DA_LARGE,DA_COLOR,DA_LEFT,DA_CENTER,
  DA_RIGHT,DA_JUSTIFY,DA_IMAGE,DA_SAVE,DA_BODY,DA_COUNT };
static const wchar_t *const da_labels[]={L"表格文字",L"上一单元格",L"下一单元格",
  L"下一段文字",L"增行",L"删行",L"下一表格",L"粗体",L"斜体",L"缩小字号",
  L"增大字号",L"更换颜色",L"左对齐",L"居中",L"右对齐",L"两端对齐",
  L"插入图片",L"保存",L"返回正文"};
static const wchar_t *const da_help[]={L"表格内当前文字，可直接输入；方向键移动，Shift 选择，Ctrl+A 全选当前文字",
  L"移动到上一单元格",L"移动到下一单元格",L"移动到当前单元格的下一文字段，保留各段格式",
  L"在当前行后插入一行",L"删除当前行",L"进入下一张表格，快捷键 Ctrl+T",
  L"切换粗体",L"切换斜体",L"减小字号",L"增大字号",L"按黑灰红绿蓝橙紫白顺序切换文字颜色",
  L"段落左对齐",L"段落居中",L"段落右对齐",L"段落两端对齐",
  L"选择并插入图片，使用标准文件对话框",L"保存 DOCX，快捷键 Ctrl+S",
  L"返回正文，快捷键 Esc；F6 在正文和命令面板之间切换"};
static struct {
  HWND panel,controls[DA_COUNT];WNDPROC edit_proc;
  exr_edit_id table;size_t row,col,para,run,byte,anchor;
  unsigned color;int loading;
  wchar_t description[768];
} da;
static void da_update(void);
static void da_action(int action);
extern exr_status l07_edit_cell_paragraph(exr_edit_doc *,exr_edit_id,size_t,size_t,
  const exr_edit_block *);
static const exr_edit_block *da_table(void) {
  const exr_edit_block *b=exr_edit_find_block(de.doc,da.table);
  return b && b->table ? b:NULL;
}
static const exr_edit_block *da_paragraph(void) {
  return exr_edit_table_cell_paragraph(de.doc,da.table,da.row,da.col,da.para);
}
static const exr_edit_run *da_run(void) {
  const exr_edit_block *b=da_paragraph();
  return b && da.run<b->run_count && b->runs[da.run].kind==EXR_EDIT_TEXT ? &b->runs[da.run]:NULL;
}
static int da_enabled(int action) {
  const exr_edit_block *b=da_paragraph();
  if(action==DA_TEXT)return b && (da_run() || !b->run_count);
  if(action>=DA_PREV && action<=DA_REMOVE)return da_table()!=NULL;
  return action>DA_TEXT && action<DA_COUNT;
}
/* One order for real Tab traversal and the headless keyboard driver. */
static int da_next_control(int current,int backwards) {
  for(int i=0;i<DA_COUNT;i++) {
    current=(current+(backwards ? DA_COUNT-1:1))%DA_COUNT;
    if(da_enabled(current))return current;
  }
  return DA_BODY;
}
static int da_control_key(int action,WPARAM key,int control,int shift) {
  if(control || shift || action<=DA_TEXT || !da_enabled(action))return 0;
  if(key!=VK_RETURN && key!=VK_SPACE)return 0;
  da_action(action);return 1;
}
static void da_changed(exr_status status) {
  if(status==EXR_OK) {de.dirty=1;de.layout_dirty=1;de_refresh(1);}
  else set_status(L"此表格操作未完成；合并、嵌套和保留内容受保护。");
  da_update();
}
/* Run-local editing retains other runs, paragraph XML and all sibling cells. */
static int da_replace(const char *text,size_t count) {
  const exr_edit_block *b=da_paragraph();const exr_edit_run *r=da_run();
  if(!b || (!r && b->run_count))return 0;
  size_t from=da.byte<da.anchor ? da.byte:da.anchor,to=da.byte>da.anchor ? da.byte:da.anchor;
  size_t length=r ? r->text_size:0;
  if(to>length || count>SIZE_MAX-length-1)return 0;
  char *bytes=malloc(length-(to-from)+count+1);if(!bytes)return 0;
  if(r)memcpy(bytes,r->text,from);
  if(count)memcpy(bytes+from,text,count);
  if(r)memcpy(bytes+from+count,r->text+to,length-to);
  size_t size=length-(to-from)+count;bytes[size]=0;
  exr_status status;
  if(r)status=exr_edit_set_run_text(de.doc,b->id,da.run,bytes,size);
  else {
    exr_edit_run run={0};run.text=bytes;run.text_size=size;
    exr_edit_block paragraph=*b;paragraph.runs=&run;paragraph.run_count=1;
    status=l07_edit_cell_paragraph(de.doc,da.table,da.row,da.col,&paragraph);
  }
  free(bytes);
  if(status==EXR_OK)da.byte=da.anchor=from+count;
  da_changed(status);return status==EXR_OK;
}
static void da_update(void) {
  const exr_edit_block *table=da_table(),*b=da_paragraph();const exr_edit_run *r=da_run();
  if(table && da.row<table->table->row_count) {
    size_t cells=table->table->rows[da.row].cell_count;
    swprintf(da.description,768,L"表格：第 %zu 行，共 %zu 行；第 %zu 列，共 %zu 列；第 %zu 段，第 %zu 文字段。%ls",
      da.row+1,table->table->row_count,da.col+1,cells,da.para+1,da.run+1,
      b ? L"可输入文字，Tab 访问命令。":L"受保护的单元格，只读；可移动到其他单元格。");
  } else {
    da.table=0;wcscpy(da.description,L"DOCX 编辑器命令。Ctrl+T 进入表格；Ctrl+S 保存；Tab 或 F6 访问命令，Esc 返回正文。");
  }
  if(!da.panel)return;
  SetWindowTextW(da.panel,da.description);
  host_a11y_describe(da.panel,NULL,da.description);
  HWND edit=da.controls[DA_TEXT];
  host_a11y_describe(edit,NULL,da.description);
  wchar_t *wide=r ? host_wide(r->text,r->text_size):NULL;
  da.loading=1;SetWindowTextW(edit,wide ? wide:L"");free(wide);da.loading=0;
  EnableWindow(edit,da_enabled(DA_TEXT));
  if(r) {
    if(da.byte>r->text_size)da.byte=r->text_size;
    if(da.anchor>r->text_size)da.anchor=r->text_size;
    while(da.byte && da.byte<r->text_size && ((unsigned char)r->text[da.byte]&0xc0)==0x80)da.byte--;
    while(da.anchor && da.anchor<r->text_size && ((unsigned char)r->text[da.anchor]&0xc0)==0x80)da.anchor--;
    SendMessageW(edit,EM_SETSEL,de_units(r->text,da.anchor),de_units(r->text,da.byte));
    SendMessageW(edit,EM_SCROLLCARET,0,0);
  }
  for(int i=DA_PREV;i<DA_COUNT;i++)EnableWindow(da.controls[i],da_enabled(i));
  NotifyWinEvent(EVENT_OBJECT_DESCRIPTIONCHANGE,edit,OBJID_CLIENT,CHILDID_SELF);
}
static int da_enter_table(void) {
  size_t n=exr_edit_block_count(de.doc),start=0;
  if(da.table)for(size_t i=0;i<n;i++)if(exr_edit_block_at(de.doc,i)->id==da.table) {start=i+1;break;}
  for(size_t j=0;j<n;j++) {
    const exr_edit_block *b=exr_edit_block_at(de.doc,(start+j)%n);
    if(b->kind==EXR_EDIT_TABLE && b->table && b->table->row_count) {
      da.table=b->id;da.row=da.col=da.para=da.run=da.byte=da.anchor=0;
      da_update();return 1;
    }
  }
  set_status(L"此文档没有可进入的表格。");return 0;
}
static void da_cell(int direction) {
  const exr_edit_block *b=da_table();if(!b)return;
  const exr_edit_table *t=b->table;
  if(direction>0) {
    if(da.col+1<t->rows[da.row].cell_count)da.col++;
    else if(da.row+1<t->row_count) {da.row++;da.col=0;}
  } else if(da.col)da.col--;
  else if(da.row) {da.row--;da.col=t->rows[da.row].cell_count ? t->rows[da.row].cell_count-1:0;}
  da.para=da.run=da.byte=da.anchor=0;da_update();
}
static void da_next_run(void) {
  size_t count=exr_edit_table_cell_block_count(de.doc,da.table,da.row,da.col);
  /* Bounded traversal includes empty paragraphs and skips opaque runs. */
  for(size_t p=0;p<=count;p++) {
    const exr_edit_block *b=da_paragraph();
    if(b)for(size_t r=da.run+1;r<b->run_count;r++)if(b->runs[r].kind==EXR_EDIT_TEXT) {
      da.run=r;da.byte=da.anchor=0;da_update();return;
    }
    da.para=count ? (da.para+1)%count:0;da.run=SIZE_MAX;
  }
  da.para=da.run=da.byte=da.anchor=0;da_update();
}
static int da_table_key(WPARAM key,int control,int shift) {
  if(!da.table)return 0;
  const exr_edit_run *r=da_run();size_t size=r ? r->text_size:0;
  if(control && key=='A') {da.anchor=0;da.byte=size;da_update();return 1;}
  if(control && key!=VK_HOME && key!=VK_END)return 0;
  if(key==VK_RETURN) {da_next_run();return 1;}
  if(key==VK_BACK || key==VK_DELETE) {
    if(da.byte==da.anchor && r) {
      if(key==VK_BACK)da.anchor=de_prev_byte(r->text,da.byte);
      else da.anchor=de_next_byte(r->text,size,da.byte);
    }
    da_replace(NULL,0);return 1;
  }
  if(key!=VK_LEFT && key!=VK_RIGHT && key!=VK_HOME && key!=VK_END)return 0;
  if(key==VK_HOME)da.byte=0;
  else if(key==VK_END)da.byte=size;
  else if(r)da.byte=key==VK_LEFT ? de_prev_byte(r->text,da.byte):de_next_byte(r->text,size,da.byte);
  if(!shift)da.anchor=da.byte;
  da_update();return 1;
}
static int da_character(wchar_t ch) {
  if(!da.table)return 0;
  if(ch<32 || ch==127)return 1;
  wchar_t wide[2]={ch,0};int length=1;
  if(ch>=0xd800 && ch<=0xdbff) {de.high_surrogate=ch;return 1;}
  if(ch>=0xdc00 && ch<=0xdfff) {
    if(!de.high_surrogate)return 1;
    wide[0]=de.high_surrogate;wide[1]=ch;length=2;
  }
  de.high_surrogate=0;
  char bytes[8];int n=WideCharToMultiByte(CP_UTF8,WC_ERR_INVALID_CHARS,wide,length,bytes,8,NULL,NULL);
  if(n)da_replace(bytes,(size_t)n);return 1;
}
static exr_status da_insert_image_path(const wchar_t *path) {
  HANDLE file=CreateFileW(path,GENERIC_READ,FILE_SHARE_READ,NULL,OPEN_EXISTING,FILE_ATTRIBUTE_NORMAL,NULL);
  if(file==INVALID_HANDLE_VALUE)return EXR_IO;
  LARGE_INTEGER length;void *bytes=NULL;exr_status status=EXR_ARGUMENT;
  if(GetFileSizeEx(file,&length) && length.QuadPart>0 && length.QuadPart<=64*1024*1024) {
    DWORD size=(DWORD)length.QuadPart,read=0;bytes=malloc(size);
    if(!bytes)status=EXR_MEMORY;
    else if(ReadFile(file,bytes,size,&read,NULL) && read==size) {
      const exr_edit_block *b=exr_edit_block_at(de.doc,de.caret_block);exr_edit_id id=0;
      status=exr_edit_insert_image(de.doc,b ? b->id:0,bytes,size,240,180,&id);
    } else status=EXR_IO;
  }
  free(bytes);CloseHandle(file);return status;
}
static void da_format(int command) {
  if(!da.table) {de_command(command,command==DE_COLOR ? de_colors[da.color]:0);return;}
  const exr_edit_block *b=da_paragraph();const exr_edit_run *r=da_run();if(!b)return;
  if(command>=DE_LEFT && command<=DE_JUSTIFY) {
    exr_edit_para_props props=b->props;props.present|=EXR_EDIT_ALIGN;
    props.alignment=(exr_edit_alignment)(command-DE_LEFT);
    exr_edit_block paragraph=*b;paragraph.props=props;
    da_changed(l07_edit_cell_paragraph(de.doc,da.table,da.row,da.col,&paragraph));return;
  }
  if(!r)return;
  exr_edit_run_props props=de_resolve_props(b,r);
  if(command==DE_BOLD) {props.present|=EXR_EDIT_BOLD;props.bold=!props.bold;}
  if(command==DE_ITALIC) {props.present|=EXR_EDIT_ITALIC;props.italic=!props.italic;}
  if(command==DE_COLOR) {props.present|=EXR_EDIT_COLOR;props.color_rgb=de_colors[da.color];}
  if(command==DE_SMALLER || command==DE_LARGER) {
    props.present|=EXR_EDIT_SIZE;unsigned size=props.size_half_points ? props.size_half_points:24;
    props.size_half_points=command==DE_SMALLER ? (size>3 ? size-2:2):(size<3274 ? size+2:3276);
  }
  exr_edit_run *runs=malloc(b->run_count*sizeof(*runs));
  if(!runs) {da_changed(EXR_MEMORY);return;}
  memcpy(runs,b->runs,b->run_count*sizeof(*runs));runs[da.run].props=props;
  exr_edit_block paragraph=*b;paragraph.runs=runs;
  exr_status status=l07_edit_cell_paragraph(de.doc,da.table,da.row,da.col,&paragraph);
  free(runs);da_changed(status);
}
static void da_action(int action) {
  if(action==DA_PREV || action==DA_NEXT)da_cell(action==DA_PREV ? -1:1);
  else if(action==DA_RUN)da_next_run();
  else if(action==DA_TABLE)da_enter_table();
  else if(action==DA_ADD || action==DA_REMOVE) {
    exr_status status=action==DA_ADD ? exr_edit_table_insert_row(de.doc,da.table,da.row):
      exr_edit_table_delete_row(de.doc,da.table,da.row);
    const exr_edit_block *b=da_table();
    if(b && da.row>=b->table->row_count)da.row=b->table->row_count ? b->table->row_count-1:0;
    da.col=da.para=da.run=da.byte=da.anchor=0;da_changed(status);
  } else if(action>=DA_BOLD && action<=DA_JUSTIFY) {
    static const int commands[]={DE_BOLD,DE_ITALIC,DE_SMALLER,DE_LARGER,DE_COLOR,DE_LEFT,DE_CENTER,DE_RIGHT,DE_JUSTIFY};
    if(action==DA_COLOR)da.color=(da.color+1)%8;
    da_format(commands[action-DA_BOLD]);
  } else if(action==DA_IMAGE) {
    wchar_t path[32768]=L"";OPENFILENAMEW dialog={0};dialog.lStructSize=sizeof(dialog);
    dialog.hwndOwner=da.panel;dialog.lpstrFile=path;dialog.nMaxFile=32768;
    dialog.lpstrTitle=L"插入图片";dialog.lpstrFilter=L"图片\0*.png;*.jpg;*.jpeg;*.gif;*.bmp\0所有文件\0*.*\0";
    dialog.Flags=OFN_FILEMUSTEXIST|OFN_PATHMUSTEXIST|OFN_NOCHANGEDIR;
    if(GetOpenFileNameW(&dialog))da_changed(da_insert_image_path(path));
  } else if(action==DA_SAVE) {de_save();da_update();}
  else if(action==DA_BODY) {da.table=0;da_update();ShowWindow(da.panel,SW_HIDE);SetFocus(g.page);}
  if(da.panel && IsWindowVisible(da.panel)) {
    SendMessageW(da.panel,WM_CHANGEUISTATE,MAKEWPARAM(UIS_CLEAR,UISF_HIDEFOCUS),0);
    if(action>=DA_PREV && action<=DA_TABLE && IsWindowEnabled(da.controls[DA_TEXT]))SetFocus(da.controls[DA_TEXT]);
  }
}
static LRESULT CALLBACK da_edit_proc(HWND window,UINT message,WPARAM wparam,LPARAM lparam) {
  if(message==WM_GETDLGCODE) {
    const MSG *key=(const MSG *)lparam;
    return DLGC_WANTCHARS|DLGC_WANTARROWS|DLGC_HASSETSEL|
      (key && key->message==WM_KEYDOWN && key->wParam==VK_RETURN ? DLGC_WANTMESSAGE:0);
  }
  if(message==WM_CHAR && !da.loading) {da_character((wchar_t)wparam);return 0;}
  if(message==WM_KEYDOWN && da_table_key(wparam,(GetKeyState(VK_CONTROL)&0x8000)!=0,
      (GetKeyState(VK_SHIFT)&0x8000)!=0))return 0;
  if(message==WM_KEYDOWN && (wparam==VK_UP || wparam==VK_DOWN))return 0;
  /* Typing, paste and cut must go through model transactions. */
  if(message==WM_PASTE || message==WM_CUT || message==WM_CLEAR)return 0;
  return CallWindowProcW(da.edit_proc,window,message,wparam,lparam);
}
static LRESULT CALLBACK da_panel_proc(HWND window,UINT message,WPARAM wparam,LPARAM lparam) {
  if(message==WM_COMMAND && HIWORD(wparam)==BN_CLICKED) {
    int action=LOWORD(wparam)-40000;if(action>DA_TEXT && action<DA_COUNT)da_action(action);return 0;
  }
  if(message==WM_CLOSE) {da_action(DA_BODY);return 0;}
  if(message==WM_SIZE) {
    RECT area;GetClientRect(window,&area);int gap=shell_px(8,shell_dpi),height=shell_px(32,shell_dpi);
    MoveWindow(da.controls[DA_TEXT],gap,gap,area.right-2*gap,height,TRUE);
    int width=(area.right-5*gap)/4;
    for(int i=1;i<DA_COUNT;i++)MoveWindow(da.controls[i],gap+(i-1)%4*(width+gap),
      height+2*gap+(i-1)/4*(height+gap),width,height,TRUE);
    return 0;
  }
  return DefWindowProcW(window,message,wparam,lparam);
}
static void da_show(void) {
  if(!de.doc || !g.window)return;
  if(!da.panel) {
    WNDCLASSW wc={0};wc.lpfnWndProc=da_panel_proc;wc.hInstance=GetModuleHandleW(NULL);
    wc.lpszClassName=L"EXReaderDoceditCommandsL07";wc.hCursor=LoadCursorW(NULL,IDC_ARROW);
    wc.hbrBackground=(HBRUSH)(COLOR_BTNFACE+1);RegisterClassW(&wc);
    da.panel=CreateWindowExW(WS_EX_CONTROLPARENT|WS_EX_TOOLWINDOW,wc.lpszClassName,L"DOCX 编辑命令",
      WS_POPUP|WS_CAPTION|WS_SYSMENU,100,100,shell_px(720,shell_dpi),shell_px(310,shell_dpi),
      g.window,NULL,wc.hInstance,NULL);
    if(!da.panel)return;
    for(int i=0;i<DA_COUNT;i++) {
      da.controls[i]=CreateWindowExW(i ? 0:WS_EX_CLIENTEDGE,i ? L"BUTTON":L"EDIT",da_labels[i],
        WS_CHILD|WS_VISIBLE|WS_TABSTOP|(i ? BS_PUSHBUTTON:ES_AUTOHSCROLL),0,0,1,1,
        da.panel,(HMENU)(INT_PTR)(40000+i),wc.hInstance,NULL);
      SendMessageW(da.controls[i],WM_SETFONT,(WPARAM)GetStockObject(DEFAULT_GUI_FONT),TRUE);
      host_a11y_describe(da.controls[i],NULL,da_help[i]);
    }
    da.edit_proc=(WNDPROC)SetWindowLongPtrW(da.controls[DA_TEXT],GWLP_WNDPROC,(LONG_PTR)da_edit_proc);
    SendMessageW(da.panel,WM_SIZE,0,0);
  }
  da_update();ShowWindow(da.panel,SW_SHOW);
  SendMessageW(da.panel,WM_CHANGEUISTATE,MAKEWPARAM(UIS_CLEAR,UISF_HIDEFOCUS),0);
  SetFocus(da.controls[da.table && IsWindowEnabled(da.controls[DA_TEXT]) ? DA_TEXT:DA_TABLE]);
}
static void da_close(void) {
  if(da.panel)DestroyWindow(da.panel);
  memset(&da,0,sizeof(da));
}
static int da_key(WPARAM key,int control,int shift) {
  if(!de.doc)return 0;
  if(control && key=='T') {da_enter_table();da_show();return 1;}
  if(control && key=='S') {de_save();da_update();return 1;}
  if(key==VK_TAB && !control) {
    da_show();if(shift && da.panel)SetFocus(da.controls[DA_BODY]);return 1;
  }
  if(key==VK_F6) {
    if(da.panel && IsWindowVisible(da.panel) && GetFocus()!=g.page) {
      da.table=0;da_update();SetFocus(g.page);
    } else da_show();
    return 1;
  }
  if(da.table) {
    if(control && (key=='B' || key=='I' || key=='L' || key=='E' || key=='R' || key=='J' ||
        (shift && (key==VK_OEM_PERIOD || key==VK_OEM_COMMA)))) {
      da_format(key=='B' ? DE_BOLD:key=='I' ? DE_ITALIC:key=='L' ? DE_LEFT:
        key=='E' ? DE_CENTER:key=='R' ? DE_RIGHT:key=='J' ? DE_JUSTIFY:
        key==VK_OEM_PERIOD ? DE_LARGER:DE_SMALLER);return 1;
    }
    if(control && (key=='Z' || key=='Y')) {
      exr_status s=key=='Z' ? exr_edit_undo(de.doc):exr_edit_redo(de.doc);da_changed(s);
      da_update();return 1;
    }
    if(key==VK_ESCAPE) {da_action(DA_BODY);return 1;}
    if(da_table_key(key,control,shift))return 1;
  }
  return 0;
}
static int da_translate(const MSG *message) {
  int control=(GetKeyState(VK_CONTROL)&0x8000)!=0,shift=(GetKeyState(VK_SHIFT)&0x8000)!=0;
  if(message->message==WM_KEYDOWN && message->wParam==VK_F2 && !de.doc) {de_enter();return 1;}
  if(!de.doc)return 0;
  if(message->message==WM_KEYDOWN && (message->hwnd==g.page || message->hwnd==g.window ||
      (da.panel && (message->hwnd==da.panel || IsChild(da.panel,message->hwnd))))) {
    if(message->wParam==VK_F6 || (control && (message->wParam=='T' || message->wParam=='S' ||
        message->wParam=='Z' || message->wParam=='Y' ||
        (da.table && message->hwnd==da.controls[DA_TEXT])))) {
      if(de_key(message->wParam,control,shift))return 1;
    }
    if(da.panel && IsWindowVisible(da.panel) && IsChild(da.panel,message->hwnd)) {
      if(message->wParam==VK_ESCAPE) {da_action(DA_BODY);return 1;}
      int action=0;while(action<DA_COUNT && da.controls[action]!=message->hwnd)action++;
      if(message->wParam==VK_TAB && !control && action<DA_COUNT) {
        SendMessageW(da.panel,WM_CHANGEUISTATE,MAKEWPARAM(UIS_CLEAR,UISF_HIDEFOCUS),0);
        SetFocus(da.controls[da_next_control(action,shift)]);return 1;
      }
      if(da_control_key(action,message->wParam,control,shift))return 1;
      if(IsDialogMessageW(da.panel,(MSG *)message))return 1;
      TranslateMessage(message);DispatchMessageW(message);return 1;
    }
  }
  return 0;
}
