/* SPDX-License-Identifier: MIT */
/* Include after shell_docedit_input.inc. Host integration:
   de_find_key(key,control,shift) before de_key; de_find_close() before de_close;
   de_find_layout() on page resize. The native child bar owns its command routing.
   Search is literal, case-sensitive, within top-level paragraphs. */
typedef struct { de_pos first,last; } de_find_hit;
static HWND de_find_bar,de_find_query,de_find_replacement;
static WNDPROC de_find_edit_proc;
static int de_find_replace_mode;

/* Match across adjacent text runs, but never across protected inline content. */
static int de_find_match(de_pos start,const char *query,size_t length,de_pos *end) {
  const exr_edit_block *b=exr_edit_block_at(de.doc,start.block);
  size_t at=0;
  if(!b || b->kind!=EXR_EDIT_PARAGRAPH)return 0;
  for(size_t r=start.run;r<b->run_count;r++) {
    const exr_edit_run *run=&b->runs[r];
    if(de_run_trivia(run))continue;
    if(run->kind!=EXR_EDIT_TEXT)return 0;
    size_t byte=r==start.run ? start.byte:0;
    while(byte<run->text_size && at<length)
      if(run->text[byte++]!=query[at++])return 0;
    if(at==length) {de_pos p={start.block,r,byte};*end=p;return 1;}
  }
  return 0;
}
static int de_find_collect(const char *query,de_find_hit **hits,size_t *count) {
  size_t capacity=0,length=strlen(query);*hits=NULL;*count=0;
  if(!length || !de.doc)return 1;
  for(size_t i=0;i<exr_edit_block_count(de.doc);i++) {
    const exr_edit_block *b=exr_edit_block_at(de.doc,i);
    if(b->kind!=EXR_EDIT_PARAGRAPH)continue;
    for(size_t r=0;r<b->run_count;r++) {
      const exr_edit_run *run=&b->runs[r];
      if(run->kind!=EXR_EDIT_TEXT)continue;
      for(size_t byte=0;byte<run->text_size;) {
        de_pos p={i,r,byte},end;
        if(de_find_match(p,query,length,&end)) {
          if(*count==capacity) {
            size_t next=capacity ? capacity*2:16;
            if(next<capacity || next>SIZE_MAX/sizeof(**hits))goto fail;
            void *memory=realloc(*hits,next*sizeof(**hits));if(!memory)goto fail;
            *hits=memory;capacity=next;
          }
          (*hits)[(*count)++]=(de_find_hit){p,end};
        }
        byte=de_next_byte(run->text,run->text_size,byte);
      }
    }
  }
  return 1;
fail:
  free(*hits);*hits=NULL;*count=0;set_status(L"查找内存不足。");return 0;
}
static int de_find_next(const char *query,int previous) {
  de_find_hit *hits=NULL;size_t count=0;
  if(!de_find_collect(query,&hits,&count))return 0;
  if(!count) {free(hits);set_status(L"没有找到匹配文本。");return 0;}
  de_pos edge=de_normalize(de_caret());
  if(previous && de_selected())edge=de_normalize(de_anchor());
  size_t pick=previous ? count-1:0;
  if(previous) {
    for(size_t i=count;i>0;i--)if(de_compare(de_normalize(hits[i-1].first),edge)<0) {pick=i-1;break;}
  } else {
    for(size_t i=0;i<count;i++)if(de_compare(de_normalize(hits[i].first),edge)>=0) {pick=i;break;}
  }
  de_set_anchor(hits[pick].first);de_set_caret(hits[pick].last);
  free(hits);de_refresh(1);return 1;
}
static int de_find_replace(const char *query,const char *replacement,int all) {
  de_find_hit *hits=NULL;size_t count=0,used=0;
  if(!*query || !de_find_collect(query,&hits,&count))return 0;
  de_pos caret=de_caret(),anchor=de_anchor();
  if(all) {
    for(size_t i=0;i<count;i++)
      if(!used || de_compare(hits[i].first,hits[used-1].last)>=0)hits[used++]=hits[i];
  } else {
    de_pos a=de_normalize(anchor),b=de_normalize(caret);
    if(de_compare(a,b)>0) {de_pos temp=a;a=b;b=temp;}
    for(size_t i=0;i<count;i++)if(!de_compare(a,de_normalize(hits[i].first)) &&
      !de_compare(b,de_normalize(hits[i].last))) {hits[0]=hits[i];used=1;break;}
  }
  if(!used) {free(hits);return de_find_next(query,0);}
  exr_edit_tx *tx=exr_edit_begin(de.doc);exr_status status=tx ? EXR_OK:EXR_MEMORY;
  if(tx) {
    for(size_t i=used;i>0 && status==EXR_OK;i--) {
      de_find_hit hit=hits[i-1];
      /* Keep the first run/template, including its style, even across runs. */
      const exr_edit_block *b=exr_edit_block_at(de.doc,hit.first.block);
      exr_edit_id id=b->id;
      for(size_t r=hit.last.run;r>hit.first.run && status==EXR_OK;r--) {
        b=exr_edit_find_block(de.doc,id);
        if(b->runs[r].kind==EXR_EDIT_TEXT)
          status=de_replace_run(id,r,0,r==hit.last.run ? hit.last.byte:b->runs[r].text_size,NULL,0);
      }
      b=exr_edit_find_block(de.doc,id);
      if(status==EXR_OK)status=de_replace_run(id,hit.first.run,hit.first.byte,
        hit.first.run==hit.last.run ? hit.last.byte:b->runs[hit.first.run].text_size,
        replacement,strlen(replacement));
    }
    if(status==EXR_OK)status=exr_edit_commit(tx);else exr_edit_rollback(tx);
  }
  if(status==EXR_OK) {
    de_pos p=hits[0].first;p.byte+=strlen(replacement);
    de_set_caret(p);de_set_anchor(p);de.dirty=1;de.layout_dirty=1;de_refresh(1);
    set_status(all ? L"全部替换完成（可一次撤销）。":L"替换完成。");
  } else {de_set_caret(caret);de_set_anchor(anchor);set_status(L"替换失败，修改已撤回。");}
  free(hits);return status==EXR_OK;
}
static char *de_find_text(HWND edit) {
  int length=GetWindowTextLengthW(edit);wchar_t *wide=calloc((size_t)length+1,sizeof(*wide));
  if(!wide)return NULL;
  GetWindowTextW(edit,wide,length+1);
  int bytes=WideCharToMultiByte(CP_UTF8,WC_ERR_INVALID_CHARS,wide,-1,NULL,0,NULL,NULL);
  char *text=bytes ? malloc((size_t)bytes):NULL;
  if(text)WideCharToMultiByte(CP_UTF8,WC_ERR_INVALID_CHARS,wide,-1,text,bytes,NULL,NULL);
  free(wide);return text;
}
static void de_find_action(int command) {
  char *query=de_find_text(de_find_query),*replacement=de_find_text(de_find_replacement);
  if(query && replacement) {
    if(command==1 || command==2)de_find_next(query,command==2);
    else de_find_replace(query,replacement,command==4);
  }
  free(query);free(replacement);
}
static void de_find_close(void) {
  if(de_find_bar)DestroyWindow(de_find_bar);
  de_find_bar=de_find_query=de_find_replacement=NULL;
}
static void de_find_layout(void) {
  if(!de_find_bar)return;
  RECT area;GetClientRect(g.page,&area);
  int y=(int)de_toolbar_height(),height=shell_px(32,shell_dpi);
  MoveWindow(de_find_bar,0,y,area.right,height,TRUE);
  int input=area.right/4,button=shell_px(64,shell_dpi);
  MoveWindow(de_find_query,0,0,input,height,TRUE);
  MoveWindow(de_find_replacement,input,0,input,height,TRUE);
  ShowWindow(de_find_replacement,de_find_replace_mode ? SW_SHOW:SW_HIDE);
  int x=de_find_replace_mode ? input*2:input;
  for(int id=1;id<=4;id++) {
    HWND child=GetDlgItem(de_find_bar,id);
    MoveWindow(child,x,0,button,height,TRUE);x+=button;
    ShowWindow(child,id<=2 || de_find_replace_mode ? SW_SHOW:SW_HIDE);
  }
}
static LRESULT CALLBACK de_find_edit_window(HWND window,UINT message,WPARAM wp,LPARAM lp) {
  if(message==WM_KEYDOWN && (wp==VK_RETURN || wp==VK_ESCAPE)) {
    if(wp==VK_ESCAPE) {de_find_close();SetFocus(g.page);}
    else de_find_action((GetKeyState(VK_SHIFT)&0x8000) ? 2:1);
    return 0;
  }
  if(message==WM_CHAR && (wp==VK_RETURN || wp==VK_ESCAPE))return 0;
  return CallWindowProcW(de_find_edit_proc,window,message,wp,lp);
}
static LRESULT CALLBACK de_find_window(HWND window,UINT message,WPARAM wp,LPARAM lp) {
  if(message==WM_COMMAND && HIWORD(wp)==BN_CLICKED && LOWORD(wp)>=1 && LOWORD(wp)<=4) {
    de_find_action(LOWORD(wp));return 0;
  }
  return DefWindowProcW(window,message,wp,lp);
}
static int de_find_key(WPARAM key,int control,int shift) {
  (void)shift;
  if(!de.doc || !control || (key!='F' && key!='H'))return 0;
  de_find_replace_mode=key=='H';
  if(!de_find_bar) {
    WNDCLASSW wc={0};wc.lpfnWndProc=de_find_window;wc.hInstance=GetModuleHandleW(NULL);
    wc.lpszClassName=L"EXReaderDocFind";wc.hbrBackground=(HBRUSH)(COLOR_BTNFACE+1);
    RegisterClassW(&wc);
    de_find_bar=CreateWindowW(wc.lpszClassName,L"查找替换",WS_CHILD|WS_VISIBLE,
      0,0,0,0,g.page,NULL,wc.hInstance,NULL);
    if(!de_find_bar)return 1;
    de_find_query=CreateWindowExW(WS_EX_CLIENTEDGE,L"EDIT",L"",WS_CHILD|WS_VISIBLE|WS_TABSTOP|ES_AUTOHSCROLL,
      0,0,0,0,de_find_bar,(HMENU)10,wc.hInstance,NULL);
    de_find_replacement=CreateWindowExW(WS_EX_CLIENTEDGE,L"EDIT",L"",WS_CHILD|WS_TABSTOP|ES_AUTOHSCROLL,
      0,0,0,0,de_find_bar,(HMENU)11,wc.hInstance,NULL);
    if(!de_find_query || !de_find_replacement) {de_find_close();return 1;}
    de_find_edit_proc=(WNDPROC)SetWindowLongPtrW(de_find_query,GWLP_WNDPROC,(LONG_PTR)de_find_edit_window);
    SetWindowLongPtrW(de_find_replacement,GWLP_WNDPROC,(LONG_PTR)de_find_edit_window);
    SendMessageW(de_find_query,EM_SETCUEBANNER,0,(LPARAM)L"查找");
    SendMessageW(de_find_replacement,EM_SETCUEBANNER,0,(LPARAM)L"替换为");
    const wchar_t *labels[]={L"下一个",L"上一个",L"替换",L"全部替换"};
    for(int id=1;id<=4;id++)CreateWindowW(L"BUTTON",labels[id-1],WS_CHILD|WS_VISIBLE|WS_TABSTOP,
      0,0,0,0,de_find_bar,(HMENU)(INT_PTR)id,wc.hInstance,NULL);
  }
  de_find_layout();SetFocus(de_find_query);return 1;
}
