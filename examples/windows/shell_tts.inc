/* SPDX-License-Identifier: MIT */
/* UI-thread orchestration. Only shell_speech.cpp owns COM and the audio device. */
static shell_speech *tts_voice;
static exr_ssml_chunk tts_chunk;
static exr_ssml_position tts_next;
static exr_text_position tts_position;
static int64_t tts_book;
static size_t tts_sentence=SIZE_MAX;
static unsigned long tts_stream,tts_events,tts_jumps,tts_chunks;
static int tts_rate=1,tts_voice_index,tts_need_chunk;
static HWND tts_panel,tts_status,tts_pause_button,tts_voices,tts_rates;
static HFONT tts_font;
static unsigned tts_font_dpi;
static wchar_t tts_message[256]=L"已停止";

static void tts_label(const wchar_t *text) {
  copy_wstring(tts_message,256,text);
  if(tts_status) SetWindowTextW(tts_status,text);
  if(tts_pause_button) SetWindowTextW(tts_pause_button,tts_state==2 ? L"继续":L"暂停");
}
static void tts_stop(void) {
  HRESULT hr=shell_speech_stop(tts_voice);
  tts_state=0;tts_need_chunk=0;tts_stream=0;tts_sentence=SIZE_MAX;
  if(g.window) KillTimer(g.window,0x5453);
  exr_ssml_chunk_free(&tts_chunk);
  tts_label(FAILED(hr) ? L"停止朗读失败，请重试。":L"已停止");
  if(g.page && !g.closing) page_dirty(g.page,0);
}
static void tts_error(const wchar_t *text) {
  tts_stop();tts_label(text);set_status(text);
  if(!host_offscreen) MessageBoxW(g.window,text,L"朗读",MB_OK|MB_ICONERROR);
}
static int tts_init(void) {
  HRESULT hr=tts_voice ? S_OK:shell_speech_create(&tts_voice);
  if(FAILED(hr)) {tts_error(L"无法初始化 Windows 语音服务。");return 0;}
  if(!shell_speech_count(tts_voice) || (host_offscreen && getenv("EXREADER_TTS_NO_VOICES"))) {
    tts_error(L"没有可用的系统语音。请在 Windows 设置中安装中文或英文语音包。");return 0;
  }
  return 1;
}
static void tts_follow(void) {
  if(!tts_state || tts_sentence==SIZE_MAX || IsIconic(g.window) || g.job || g.pending || shell_layout_waiting || shelf_exit_pending || shelf_requested) return;
  if(tts_position.part==g.frame.part && tts_position.offset>=g.frame.range_start && tts_position.offset<g.frame.range_end) return;
  exr_document *doc=NULL;host_job *job=job_new(JOB_GO);
  if(!job || exr_publication_load(select_publication(),tts_position.part,&doc,NULL)!=EXR_OK ||
     exr_anchor_create(doc,tts_position.offset,tts_position.offset,&job->anchor,NULL)!=EXR_OK) {
    if(job) job_release(job);
    exr_document_free(doc);tts_error(L"无法定位当前朗读文字。");return;
  }
  exr_document_free(doc);job->book_id=tts_book;job->use_offset=job->has_anchor=job->shell_search_jump=1;
  job->target_part=tts_position.part;job->target_offset=tts_position.offset;
  if(g.session.bounded) {
    size_t n;const exr_part *parts=exr_publication_parts(g.session.publication,&n);
    if(tts_position.part>=n || !(job->part_path=host_strdup(parts[tts_position.part].path))) {
      job_release(job);tts_error(L"朗读章节已不可用。");return;
    }
  }
  tts_jumps++;job_submit(job);
}
static void tts_boundary(size_t offset) {
  for(size_t i=0;i<tts_chunk.sentence_count;i++) {
    const exr_ssml_sentence *s=&tts_chunk.sentences[i];
    size_t first=(size_t)MultiByteToWideChar(CP_UTF8,0,tts_chunk.ssml,(int)s->ssml_start,NULL,0);
    size_t last=(size_t)MultiByteToWideChar(CP_UTF8,0,tts_chunk.ssml,(int)s->ssml_end,NULL,0);
    if(offset<first || offset>=last) continue;
    tts_sentence=i;tts_position=s->range.start;
    /* SAPI offsets count UTF-16 XML, including entities. Map the word position
       back into the contiguous original sentence, preserving astral UTF-8. */
    size_t at=s->ssml_start,source=s->range.start.offset,units=first;
    while(at<s->ssml_end && units<offset) {
      unsigned char c=(unsigned char)tts_chunk.ssml[at];
      size_t bytes=c<128 ? 1:c<224 ? 2:c<240 ? 3:4;
      if(c=='&') {
        const char *end=strchr(tts_chunk.ssml+at,';');
        if(!end) break;
        units+=(size_t)(end-(tts_chunk.ssml+at))+1;at=(size_t)(end-tts_chunk.ssml)+1;source++;
      } else {at+=bytes;source+=bytes;units+=bytes==4 ? 2:1;}
    }
    if(source<s->range.end.offset) tts_position.offset=source;
    page_dirty(g.page,0);return;
  }
}
static void tts_poll(void) {
  if(!tts_state) return;
  if(tts_book!=g.session.book_id || !shell_active || !g.session.active) {tts_stop();return;}
  if(tts_state==2) return;
  int type;unsigned long stream;size_t offset;
  while(shell_speech_event(tts_voice,&type,&stream,&offset)) {
    if(stream!=tts_stream) continue;
    tts_events++;
    if(type==1 && tts_chunk.sentence_count) {
      tts_sentence=0;tts_position=tts_chunk.sentences[0].range.start;page_dirty(g.page,0);
    } else if(type==2) tts_boundary(offset);
    else if(type==3) {
      unsigned long state,current;size_t word;
      if(FAILED(shell_speech_status(tts_voice,&state,&current,&word))) {
        tts_error(L"系统语音播放失败。请检查音频输出及对应语言的语音包。");return;
      }
      tts_need_chunk=1;tts_stream=0;
    }
  }
  if(tts_need_chunk && !g.job && !g.pending) {
    if(tts_chunk.end) {tts_stop();tts_label(L"朗读完成");return;}
    exr_ssml_chunk_free(&tts_chunk);tts_sentence=SIZE_MAX;
    exr_error error={0};
    if(exr_document_ssml(select_publication(),tts_next,800,&tts_chunk,0,NULL,&error)!=EXR_OK) {
      tts_error(L"无法生成朗读内容。");return;
    }
    tts_next=tts_chunk.next;
    if(!tts_chunk.characters) {
      if(tts_chunk.end) {tts_stop();tts_label(L"朗读完成");}
      return;
    }
    HRESULT hr=shell_speech_speak(tts_voice,tts_chunk.ssml,&tts_stream);
    if(FAILED(hr)) {tts_error(L"系统语音无法朗读此内容。");return;}
    tts_chunks++;tts_need_chunk=0;
  }
  tts_follow();
}
static void tts_start(void) {
  if(!shell_active || !g.frame.valid || g.frame.fixed || !select_publication()) {
    tts_error(L"请先打开有可朗读文字的书籍。");return;
  }
  if(g.job || g.pending) {tts_label(L"页面正在加载，请稍后开始。");return;}
  tts_stop();
  if(!tts_init()) return;
  if(FAILED(shell_speech_voice(tts_voice,(size_t)tts_voice_index)) || FAILED(shell_speech_rate(tts_voice,tts_rate))) {
    tts_error(L"无法设置系统音色或语速。");return;
  }
  tts_next=(exr_ssml_position){g.frame.part,g.frame.range_start,0};
  tts_book=g.session.book_id;tts_state=1;tts_need_chunk=1;tts_events=tts_jumps=tts_chunks=0;
  tts_label(L"正在朗读");SetTimer(g.window,0x5453,30,NULL);tts_poll();
}
static void tts_pause(int pause) {
  if(!tts_state) return;
  if(FAILED(shell_speech_pause(tts_voice,pause))) {tts_error(L"无法暂停或继续朗读。");return;}
  tts_state=pause ? 2:1;tts_label(pause ? L"已暂停":L"正在朗读");
}
static int tts_set_rate(int index) {
  if(index<0 || index>3 || !tts_init() || FAILED(shell_speech_rate(tts_voice,index))) return 0;
  tts_rate=index;if(tts_rates) SendMessageW(tts_rates,CB_SETCURSEL,index,0);return 1;
}
static int tts_set_voice(int index) {
  if(index<0 || !tts_init() || (size_t)index>=shell_speech_count(tts_voice)) return 0;
  /* Changing voice stops this stream. Start resumes from the visible page. */
  tts_stop();
  if(FAILED(shell_speech_voice(tts_voice,(size_t)index))) return 0;
  tts_voice_index=index;if(tts_voices) SendMessageW(tts_voices,CB_SETCURSEL,index,0);return 1;
}
static LRESULT CALLBACK tts_panel_proc(HWND window,UINT message,WPARAM wp,LPARAM lp) {
  if(message==WM_COMMAND) {
    int id=LOWORD(wp);
    if(id==105 && HIWORD(wp)==CBN_SELCHANGE) {
      if(!tts_set_voice((int)SendMessageW(tts_voices,CB_GETCURSEL,0,0))) tts_error(L"无法切换系统音色。");
      return 0;
    }
    if(id==106 && HIWORD(wp)==CBN_SELCHANGE) {
      if(!tts_set_rate((int)SendMessageW(tts_rates,CB_GETCURSEL,0,0))) tts_error(L"无法调整语速。");
      return 0;
    }
    if(tts_command(id)) return 0;
  }
  if(message==WM_CLOSE) {ShowWindow(window,SW_HIDE);return 0;}
  return DefWindowProcW(window,message,wp,lp);
}
static int tts_translate(const MSG *message) {
  if(!tts_panel || !IsWindowVisible(tts_panel) ||
     (message->hwnd!=tts_panel && !IsChild(tts_panel,message->hwnd))) return 0;
  if(message->message==WM_KEYDOWN && message->wParam==VK_ESCAPE) {
    ShowWindow(tts_panel,SW_HIDE);SetFocus(g.page);return 1;
  }
  return IsDialogMessageW(tts_panel,(MSG *)message);
}
static void tts_layout(void) {
  if(!tts_panel) return;
  RECT client;GetClientRect(g.window,&client);
  int w=shell_px(480,shell_dpi);
  SetWindowPos(tts_panel,HWND_TOP,max(shell_px(8,shell_dpi),client.right-w-shell_px(12,shell_dpi)),
    shell_px(SHELL_TOPBAR_H+8,shell_dpi),w,shell_px(164,shell_dpi),SWP_NOACTIVATE);
  const int boxes[][5]={{101,12,12,156,30},{102,176,12,92,30},{103,276,12,92,30},{104,376,12,92,30},
    {105,54,51,414,220},{106,54,87,110,160},{107,12,55,40,22},{108,12,91,40,22},{109,12,127,456,24}};
  for(size_t i=0;i<sizeof(boxes)/sizeof(*boxes);i++) MoveWindow(GetDlgItem(tts_panel,boxes[i][0]),
    shell_px(boxes[i][1],shell_dpi),shell_px(boxes[i][2],shell_dpi),shell_px(boxes[i][3],shell_dpi),shell_px(boxes[i][4],shell_dpi),TRUE);
  if(tts_font_dpi!=shell_dpi) {
    HFONT font=CreateFontW(-shell_px(14,shell_dpi),0,0,0,FW_NORMAL,FALSE,FALSE,FALSE,DEFAULT_CHARSET,
      OUT_DEFAULT_PRECIS,CLIP_DEFAULT_PRECIS,CLEARTYPE_QUALITY,DEFAULT_PITCH,L"Microsoft YaHei UI");
    if(font) {
      for(HWND child=GetWindow(tts_panel,GW_CHILD);child;child=GetWindow(child,GW_HWNDNEXT)) SendMessageW(child,WM_SETFONT,(WPARAM)font,TRUE);
      if(tts_font) DeleteObject(tts_font);
      tts_font=font;tts_font_dpi=shell_dpi;
    }
  }
}
static void tts_show(void) {
  if(!tts_init()) return;
  if(!tts_panel) {
    WNDCLASSW type={0};type.lpfnWndProc=tts_panel_proc;type.hInstance=GetModuleHandleW(NULL);
    type.lpszClassName=L"EXReaderSpeech";type.hbrBackground=(HBRUSH)(COLOR_WINDOW+1);type.hCursor=LoadCursor(NULL,IDC_ARROW);
    RegisterClassW(&type);
    tts_panel=CreateWindowExW(WS_EX_CONTROLPARENT,L"EXReaderSpeech",L"朗读",WS_CHILD|WS_BORDER,
      0,0,450,164,g.window,NULL,type.hInstance,NULL);
    const wchar_t *labels[]={L"从当前位置开始",L"暂停",L"停止",L"关闭"};
    for(int i=0;i<4;i++) {
      HWND control=CreateWindowW(L"BUTTON",labels[i],WS_CHILD|WS_VISIBLE|WS_TABSTOP,
        12+i*108,12,102,30,tts_panel,(HMENU)(INT_PTR)(101+i),type.hInstance,NULL);
      SendMessageW(control,WM_SETFONT,(WPARAM)GetStockObject(DEFAULT_GUI_FONT),TRUE);
      if(i==1) tts_pause_button=control;
    }
    CreateWindowW(L"STATIC",L"音色",WS_CHILD|WS_VISIBLE,12,55,40,22,tts_panel,(HMENU)107,type.hInstance,NULL);
    tts_voices=CreateWindowW(L"COMBOBOX",L"系统音色",WS_CHILD|WS_VISIBLE|WS_TABSTOP|CBS_DROPDOWNLIST|WS_VSCROLL,
      54,51,378,220,tts_panel,(HMENU)105,type.hInstance,NULL);
    for(size_t i=0;i<shell_speech_count(tts_voice);i++) SendMessageW(tts_voices,CB_ADDSTRING,0,(LPARAM)shell_speech_name(tts_voice,i));
    SendMessageW(tts_voices,CB_SETCURSEL,tts_voice_index,0);
    CreateWindowW(L"STATIC",L"语速",WS_CHILD|WS_VISIBLE,12,91,40,22,tts_panel,(HMENU)108,type.hInstance,NULL);
    tts_rates=CreateWindowW(L"COMBOBOX",L"语速",WS_CHILD|WS_VISIBLE|WS_TABSTOP|CBS_DROPDOWNLIST,
      54,87,110,160,tts_panel,(HMENU)106,type.hInstance,NULL);
    const wchar_t *rates[]={L"0.8×",L"1.0×",L"1.2×",L"1.5×"};
    for(int i=0;i<4;i++) SendMessageW(tts_rates,CB_ADDSTRING,0,(LPARAM)rates[i]);
    SendMessageW(tts_rates,CB_SETCURSEL,tts_rate,0);
    tts_status=CreateWindowW(L"STATIC",tts_message,WS_CHILD|WS_VISIBLE,12,127,420,24,tts_panel,(HMENU)109,type.hInstance,NULL);
    HWND controls[]={tts_rates,tts_voices,tts_status};
    for(size_t i=0;i<3;i++) SendMessageW(controls[i],WM_SETFONT,(WPARAM)GetStockObject(DEFAULT_GUI_FONT),TRUE);
  }
  tts_layout();ShowWindow(tts_panel,SW_SHOWNOACTIVATE);SetFocus(GetDlgItem(tts_panel,101));
}
static int tts_command(int command) {
  switch(command) {
    case 100:tts_show();return 1;
    case 101:tts_start();return 1;
    case 102:tts_pause(tts_state!=2);return 1;
    case 103:tts_stop();return 1;
    case 104:if(tts_panel) ShowWindow(tts_panel,SW_HIDE);return 1;
  }
  return 0;
}
static void tts_menu(HMENU menu) {
  AppendMenuW(menu,MF_SEPARATOR,0,NULL);
  AppendMenuW(menu,MF_STRING,100,L"朗读…（音色与语速）");
  AppendMenuW(menu,MF_STRING,101,L"从当前位置开始朗读");
  AppendMenuW(menu,MF_STRING|(tts_state ? 0:MF_GRAYED),102,tts_state==2 ? L"继续朗读":L"暂停朗读");
  AppendMenuW(menu,MF_STRING|(tts_state ? 0:MF_GRAYED),103,L"停止朗读");
}
static void tts_pixels(uint32_t *pixels,int width,int height) {
  if(!tts_state || tts_book!=g.frame.book_id || tts_sentence>=tts_chunk.sentence_count) return;
  exr_text_range range=tts_chunk.sentences[tts_sentence].range;
  if(range.start.part!=g.frame.part) return;
  HRGN region=select_region_for(range.start.offset,range.end.offset);RECT bounds;GetRgnBox(region,&bounds);
  for(int y=max(0,bounds.top);y<min(height,bounds.bottom);y++) for(int x=max(0,bounds.left);x<min(width,bounds.right);x++) if(PtInRegion(region,x,y)) {
    size_t at=(size_t)y*width+x;uint32_t q=g.frame.dib[at];unsigned r=(q>>16)&255,b=q&255,green=(q>>8)&255;
    if(!g.frame.display_shell_paper && r==b && b==green)
      pixels[at]=shell_blend(shell_colors->text,shell_blend(shell_colors->layer_page,SHELL_ACCENT_SOFT_RGB,SHELL_ACCENT_SOFTER_ALPHA),r/255.f);
    else pixels[at]=shell_blend(pixels[at],SHELL_ACCENT_SOFT_RGB,(float)max(r,max(b,green))/255.f*SHELL_ACCENT_SOFTER_ALPHA);
  }
  DeleteObject(region);
}
static void tts_destroy(void) {
  tts_stop();shell_speech_free(tts_voice);tts_voice=NULL;
  if(tts_panel) DestroyWindow(tts_panel);
  if(tts_font) DeleteObject(tts_font);
  tts_font=NULL;tts_font_dpi=0;
  tts_panel=tts_status=tts_pause_button=tts_voices=tts_rates=NULL;
}
