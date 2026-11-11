/* SPDX-License-Identifier: MIT */
/* One private search worker and immutable source snapshot, separate from pagers. */
/* Children of the search bar; IDC_SHELL_SEARCH (the top-bar button) is in shell_screen.inc. */
enum { IDC_SEARCH_EDIT=200,IDC_SEARCH_PREV,IDC_SEARCH_NEXT,
       IDC_SEARCH_CASE,IDC_SEARCH_WORD,IDC_SEARCH_CLOSE,IDC_SEARCH_COUNT };
static HWND shell_search_button,shell_search_bar,shell_search_edit,shell_search_count,shell_search_label_control;
static HWND shell_search_prev,shell_search_next,shell_search_case,shell_search_word,shell_search_close;
static exr_search_result *shell_search_hits;
static size_t shell_search_count_value,shell_search_current;
static int64_t shell_search_book;
static int shell_search_pending,shell_search_jump_pending;
static unsigned shell_search_revision,shell_search_calls;
static int shell_search_test_shift;
static double shell_search_input_start,shell_search_last_ms,shell_search_last_total_ms;
typedef struct {
  volatile LONG cancel;
  unsigned revision,flags;
  int64_t book;
  int bounded;
  exr_format format;
  char *path,*needle;
  exr_search_result *hits;
  size_t count,capacity;
  exr_status status;
  exr_error error;
  double elapsed;
  int memory_failed;
} shell_search_work;
static HANDLE shell_search_thread;
static shell_search_work *shell_search_working;
/* Only the worker accesses these; UI joins before destruction. */
static exr_publication *shell_search_publication;
static unsigned char *shell_search_original;
static size_t shell_search_original_size;
static exr_format shell_search_format;
static exr_fixed_document *shell_search_fixed;
static size_t **shell_search_maps,shell_search_map_count;
static int64_t shell_search_cached_book;
static int shell_search_cached_bounded;
static void shell_search_cache_free(void) {
  exr_fixed_free(shell_search_fixed);shell_search_fixed=NULL;
  if(shell_search_maps) for(size_t i=0;i<shell_search_map_count;i++) free(shell_search_maps[i]);
  free(shell_search_maps);shell_search_maps=NULL;shell_search_map_count=0;
  exr_publication_free(shell_search_publication);shell_search_publication=NULL;
  exr_free(shell_search_original);shell_search_original=NULL;shell_search_cached_book=0;
}
static size_t shell_search_read(void *ctx,uint64_t offset,void *data,size_t size) {
  (void)ctx;if(offset>=shell_search_original_size) return 0;
  if(size>shell_search_original_size-(size_t)offset) size=shell_search_original_size-(size_t)offset;
  memcpy(data,shell_search_original+(size_t)offset,size);return size;
}
static void shell_search_borrowed_release(void *ctx) {(void)ctx;}
static int shell_search_cancelled(void *ctx) {return InterlockedCompareExchange(&((shell_search_work *)ctx)->cancel,0,0)!=0;}
static size_t shell_search_space(const char *s,size_t n,size_t at) {
  if(at>=n) return 0;
  if(s[at]==' ' || s[at]=='\t' || s[at]=='\r' || s[at]=='\n') return 1;
  if(at+2<=n && !memcmp(s+at,"\xc2\xa0",2)) return 2;
  if(at+3<=n && !memcmp(s+at,"\xe3\x80\x80",3)) return 3;
  return 0;
}
static exr_status shell_search_load(void *ctx,size_t part,exr_document **out,exr_error *e) {
  (void)ctx;
  if(!shell_search_fixed) {
    exr_status status=exr_document_open_memory(shell_search_format,shell_search_original,shell_search_original_size,out,e);
    if(status==EXR_OK && !shell_style_document(out)) status=EXR_FORMAT;
    return status;
  }
  exr_fixed_text *text=NULL;size_t n=0,m=0;exr_status status=exr_fixed_load_text(shell_search_fixed,part,NULL,&text,e);
  if(status!=EXR_OK) return status;
  const char *raw=exr_fixed_text_string(text,&n);
  size_t blank_at=0,blank_step;
  while((blank_step=shell_search_space(raw,n,blank_at))!=0) blank_at+=blank_step;
  if(blank_at==n) {
    exr_node_input nodes[]={{EXR_NODE_DOCUMENT,SIZE_MAX,NULL,NULL,NULL,0},{EXR_NODE_CHAPTER,0,NULL,NULL,NULL,0}};
    exr_chapter_input chapter={"empty","empty.txt",1,1};
    exr_document_input input={"",nodes,2,&chapter,1,NULL,0};
    status=exr_document_create(&input,out,e);
  } else status=exr_document_open_memory(EXR_TXT,raw,n,out,e);
  if(status==EXR_OK) {
    const char *projection=exr_document_text(*out,&m);size_t *map=malloc((m+1)*sizeof(*map)),at=0;
    if(!map) status=EXR_MEMORY;
    else {
      /* TXT projection folds whitespace. Retain a byte map to native PDF quads. */
      if(n>=3 && !memcmp(raw,"\xef\xbb\xbf",3)) at=3;
      for(size_t j=0;j<m;j++) {
        size_t projected_space=shell_search_space(projection,m,j);
        if(projected_space) {
          size_t source_space=shell_search_space(raw,n,at);
          for(size_t k=0;k<projected_space;k++) map[j+k]=at+(source_space==projected_space ? k:0);
          at+=source_space;j+=projected_space-1;
        } else {
          size_t step;while((step=shell_search_space(raw,n,at))!=0) at+=step;
          if(at>=n || raw[at]!=projection[j]) {status=EXR_ENCODING;break;}
          map[j]=at++;
        }
      }
      map[m]=at;
      if(status==EXR_OK) {free(shell_search_maps[part]);shell_search_maps[part]=map;}else free(map);
    }
  }
  exr_fixed_text_free(text);
  if(status!=EXR_OK) {exr_document_free(*out);*out=NULL;}
  return status;
}
static int shell_search_collect(void *ctx,const exr_search_result *r) {
  shell_search_work *w=ctx;
  if(shell_search_cancelled(w)) return 0;
  if(w->count==w->capacity) {
    size_t cap=w->capacity ? w->capacity*2:256;
    exr_search_result *next=realloc(w->hits,cap*sizeof(*next));
    if(!next) {w->memory_failed=1;return 0;}
    w->hits=next;w->capacity=cap;
  }
  exr_search_result hit=*r;
  if(shell_search_fixed) {size_t *map=shell_search_maps[r->part];hit.offset=map[r->offset];hit.length=map[r->offset+r->length]-hit.offset;}
  w->hits[w->count++]=hit;return 1;
}
static unsigned __stdcall shell_search_worker(void *ctx) {
  shell_search_work *w=ctx;double begin=host_probe_ms();exr_status status=EXR_OK;
  if(shell_search_cached_book!=w->book || shell_search_cached_bounded!=w->bounded) {
    exr_library *library=NULL;void *original=NULL;
    shell_search_cache_free();
    status=exr_library_open(w->path,&library,&w->error);
    /* The existing blob API provides one SQL snapshot even if UI progress is
       saved concurrently. This copy and all parsing stay on the worker. */
    if(status==EXR_OK) status=exr_library_blob(library,w->book,0,&original,&shell_search_original_size,&w->error);
    exr_library_close(library);shell_search_original=original;
    if(status==EXR_OK && shell_search_original_size>HOST_IMPORT_LIMIT) status=EXR_LIMIT;
    if(status==EXR_OK && shell_search_cancelled(w)) status=EXR_CANCELLED;
    shell_search_format=w->format;
    if(status==EXR_OK && w->format==EXR_EPUB && w->bounded) {
      exr_source styled={0};styled.size=shell_search_original_size;styled.read_at=shell_search_read;styled.release=shell_search_borrowed_release;
      if(!shell_epub_source(&styled)) status=EXR_FORMAT;
      else status=exr_publication_open_source(&styled,&shell_search_publication,&w->error);
      if(status!=EXR_OK && styled.release) styled.release(styled.context);
    }
    else if(status==EXR_OK && is_fixed_format(w->format)) {
      exr_fixed_open_options options={0};options.struct_size=sizeof(options);
      options.control=(exr_control){shell_search_cancelled,NULL,w};
      status=exr_fixed_open_memory(w->format,shell_search_original,shell_search_original_size,&options,&shell_search_fixed,&w->error);
      if(status==EXR_OK) {
        exr_fixed_pages(shell_search_fixed,&shell_search_map_count);
        shell_search_maps=calloc(shell_search_map_count,sizeof(*shell_search_maps));
        exr_part *parts=calloc(shell_search_map_count,sizeof(*parts));char (*ids)[32]=calloc(shell_search_map_count,32);
        if(!shell_search_maps || !parts || !ids) status=EXR_MEMORY;
        else {
          for(size_t i=0;i<shell_search_map_count;i++) {snprintf(ids[i],32,"page-%llu",(unsigned long long)i);parts[i]=(exr_part){ids[i],ids[i],"",1};}
          exr_publication_input input={0};input.parts=parts;input.part_count=shell_search_map_count;input.load=shell_search_load;
          status=exr_publication_create(&input,&shell_search_publication,&w->error);
        }
        free(parts);free(ids);
      }
    }
    else if(status==EXR_OK) {
      exr_part part={"document","document.txt","",1};exr_publication_input input={0};
      input.parts=&part;input.part_count=1;input.load=shell_search_load;
      status=exr_publication_create(&input,&shell_search_publication,&w->error);
    }
    if(status==EXR_OK) {shell_search_cached_book=w->book;shell_search_cached_bounded=w->bounded;}else shell_search_cache_free();
  }
  if(status==EXR_OK) {
    exr_control control={shell_search_cancelled,NULL,w};size_t total;
    status=exr_publication_search_all(shell_search_publication,w->needle,w->flags,shell_search_collect,w,&control,&total,&w->error);
    if(w->memory_failed) status=EXR_MEMORY;
    if(shell_search_cancelled(w)) status=EXR_CANCELLED;
  }
  w->status=status;w->elapsed=host_probe_ms()-begin;return 0;
}
static void shell_search_label(void) {
  wchar_t text[128];
  swprintf(text,128,L"第 %llu / 共 %llu 个",(unsigned long long)(shell_search_count_value ? shell_search_current+1:0),
    (unsigned long long)shell_search_count_value);
  SetWindowTextW(shell_search_count,text);
  EnableWindow(shell_search_prev,shell_search_count_value!=0);EnableWindow(shell_search_next,shell_search_count_value!=0);
}
/* Bar children from the right: close, next, previous, the count, two toggles;
   the field takes the rest. Visual boxes are 8 apart, so their 4-wide frames
   meet without overlapping. */
static RECT shell_search_field; /* the field's frame box, in bar coordinates */
static void shell_search_layout(void) {
  if(!shell_search_bar) return;
  RECT r;GetClientRect(g.window,&r);int bar=shell_px(48,shell_dpi);
  MoveWindow(shell_search_bar,0,shell_px(SHELL_TOPBAR_H,shell_dpi),r.right,bar,TRUE);
  int frame=shell_px(SHELL_CONTROL_FRAME,shell_dpi),gap=shell_px(SHELL_SPACE_1,shell_dpi);
  int height=shell_px(SHELL_CONTROL_H,shell_dpi),y=(bar-height)/2,right=r.right-shell_px(SHELL_BAR_RIGHT,shell_dpi);
  HFONT font=shell_gdi_font(SHELL_VALUE_FONT,FW_NORMAL);int line=shell_gdi_line(font),text_y=y+(height-line)/2;
  struct {HWND control;int width;} boxes[5]={{shell_search_close,32},{shell_search_next,32},{shell_search_prev,32},
    {shell_search_word,52},{shell_search_case,40}};
  for(int i=0;i<5;i++) {
    if(i==3) {
      int width=shell_px(132,shell_dpi);right-=width;
      MoveWindow(shell_search_count,right,text_y,width,line,TRUE);right-=gap;
    }
    int width=shell_px((float)boxes[i].width,shell_dpi);right-=width;
    MoveWindow(boxes[i].control,right-frame,y-frame,width+2*frame,height+2*frame,TRUE);right-=gap;
  }
  int left=shell_px(SHELL_TITLE_LEFT,shell_dpi),label=shell_px(32,shell_dpi),inset=shell_px(12,shell_dpi);
  MoveWindow(shell_search_label_control,left,text_y,label,line,TRUE);
  left+=label+gap;
  shell_search_field=(RECT){left-frame,y-frame,max(left,right)+frame,y+height+frame};
  MoveWindow(shell_search_edit,left+inset,text_y,max(0,right-left-2*inset),line,TRUE);
  HWND texts[3]={shell_search_label_control,shell_search_count,shell_search_edit};
  for(int i=0;i<3;i++) SendMessageW(texts[i],WM_SETFONT,(WPARAM)font,TRUE);
  InvalidateRect(shell_search_bar,NULL,FALSE);
}
static void shell_search_changed(void) {
  shell_search_revision++;shell_search_pending=shell_search_open;shell_search_jump_pending=0;
  if(shell_search_working) InterlockedExchange(&shell_search_working->cancel,1);
  free(shell_search_hits);shell_search_hits=NULL;shell_search_count_value=0;shell_search_label();
  if(!shell_search_open || !GetWindowTextLengthW(shell_search_edit)) {
    shell_search_pending=0;shell_search_input_start=0;KillTimer(g.window,0x5756);page_dirty(g.page,1);return;
  }
  if(!shell_search_input_start) shell_search_input_start=host_probe_ms();
  SetWindowTextW(shell_search_count,L"搜索中…");
  SetTimer(g.window,0x5756,200,NULL);page_dirty(g.page,1);
}
static void shell_search_set(int open) {
  if(open && (!g.session.active || g.session.txt)) {set_status(L"当前格式未提供可重排文本搜索。");return;}
  shell_search_open=open;
  ShowWindow(shell_search_bar,open && shell_active ? SW_SHOWNA:SW_HIDE);
  if(!open) {
    KillTimer(g.window,0x5756);shell_search_pending=0;shell_search_revision++;
    shell_search_jump_pending=0;if(shell_search_working) InterlockedExchange(&shell_search_working->cancel,1);
  }
  shell_layout();shell_request_layout();page_dirty(g.page,1);InvalidateRect(shell_search_button,NULL,FALSE);
  SetFocus(open ? shell_search_edit:g.page);
  if(open && GetWindowTextLengthW(shell_search_edit)) shell_search_changed();
}
static void shell_search_jump(void) {
  if(!shell_search_count_value || shell_search_book!=g.session.book_id) {shell_search_jump_pending=0;return;}
  if(g.job || g.pending || shell_layout_waiting || !shell_geometry_equal(g.session.shell_geometry,shell_target)) {
    shell_search_jump_pending=1;SetTimer(g.window,0x5757,20,NULL);return;
  }
  shell_search_jump_pending=0;
  exr_search_result r=shell_search_hits[shell_search_current];exr_error error={0};
  if(g.session.fixed) {
    host_job *job=job_new(JOB_GO);if(!job) return;
    job->book_id=g.session.book_id;job->target_page=r.part;job->shell_search_jump=1;job_submit(job);return;
  }
  const exr_document *doc=g.session.document;exr_document *loaded=NULL;
  if(g.session.bounded) {if(exr_publication_load(g.session.publication,r.part,&loaded,&error)!=EXR_OK) return;doc=loaded;}
  host_job *job=job_new(JOB_GO);
  if(!job || exr_anchor_create(doc,r.offset,r.offset+r.length,&job->anchor,&error)!=EXR_OK) {
    if(job) job_release(job);
    exr_document_free(loaded);set_status(L"搜索命中锚点创建失败。");return;
  }
  job->shell_search_jump=1;job->book_id=g.session.book_id;job->use_offset=1;job->target_offset=r.offset;job->target_part=r.part;job->has_anchor=1;
  if(g.session.bounded) {
    size_t n;const exr_part *parts=exr_publication_parts(g.session.publication,&n);
    if(r.part>=n || !(job->part_path=host_strdup(parts[r.part].path))) {job_release(job);exr_document_free(loaded);return;}
  }
  exr_document_free(loaded);job_submit(job);page_dirty(g.page,1);
}
static void shell_search_step(int delta) {
  if(!shell_search_count_value) return;
  if(delta>0) shell_search_current=(shell_search_current+1)%shell_search_count_value;
  else shell_search_current=shell_search_current ? shell_search_current-1:shell_search_count_value-1;
  shell_search_label();shell_search_jump();
}
static void shell_search_start(void) {
  KillTimer(g.window,0x5756);
  if(!shell_search_pending || !shell_search_open) return;
  if(shell_search_thread) {SetTimer(g.window,0x5756,20,NULL);return;}
  wchar_t query[1025];GetWindowTextW(shell_search_edit,query,1025);
  shell_search_pending=0;
  if(!query[0]) {shell_search_label();return;}
  shell_search_work *w=calloc(1,sizeof(*w));if(!w) return;
  w->revision=shell_search_revision;w->book=g.session.book_id;w->format=g.current.format;w->bounded=g.session.bounded;
  w->path=host_utf8(g.library_path);w->needle=host_utf8(query);
  if(SendMessageW(shell_search_case,BM_GETCHECK,0,0)==BST_CHECKED) w->flags|=EXR_SEARCH_CASE_SENSITIVE;
  if(SendMessageW(shell_search_word,BM_GETCHECK,0,0)==BST_CHECKED) w->flags|=EXR_SEARCH_WHOLE_WORD;
  shell_search_working=w;
  if(w->path && w->needle) shell_search_thread=(HANDLE)_beginthreadex(NULL,0,shell_search_worker,w,0,NULL);
  if(!shell_search_thread) {free(w->path);free(w->needle);free(w);shell_search_working=NULL;SetWindowTextW(shell_search_count,L"搜索启动失败");return;}
  shell_search_calls++;SetTimer(g.window,0x5757,20,NULL);
}
static void shell_search_poll(void) {
  if(shell_search_thread && WaitForSingleObject(shell_search_thread,0)==WAIT_OBJECT_0) {
    shell_search_work *w=shell_search_working;CloseHandle(shell_search_thread);shell_search_thread=NULL;shell_search_working=NULL;
    if(w->revision==shell_search_revision && w->book==g.session.book_id && shell_search_open) {
      free(shell_search_hits);shell_search_hits=NULL;shell_search_count_value=0;shell_search_current=0;
      if(w->status==EXR_OK) {
        shell_search_hits=w->hits;w->hits=NULL;shell_search_count_value=w->count;shell_search_book=w->book;
        shell_search_last_ms=w->elapsed;shell_search_label();
        host_probe_log("search_ms",w->elapsed);host_probe_log("search_hits",(double)w->count);
        shell_search_last_total_ms=host_probe_ms()-shell_search_input_start;
        host_probe_log("search_calls",shell_search_calls);host_probe_log("search_input_total_ms",shell_search_last_total_ms);
        shell_search_input_start=0;shell_search_jump_pending=w->count!=0;
      } else {SetWindowTextW(shell_search_count,L"搜索失败，请重试");set_status(L"搜索失败，未更新结果。");}
    }
    free(w->hits);free(w->path);free(w->needle);free(w);page_dirty(g.page,1);
  }
  if(shell_search_jump_pending) shell_search_jump();
  if(!shell_search_thread && !shell_search_jump_pending) KillTimer(g.window,0x5757);
}
static LRESULT CALLBACK shell_search_proc(HWND window,UINT message,WPARAM wp,LPARAM lp) {
  switch(message) {
    case WM_COMMAND: {
      int id=LOWORD(wp),code=HIWORD(wp);
      if(id==IDC_SEARCH_EDIT && code==EN_CHANGE) {shell_search_changed();return 0;}
      if(id==IDC_SEARCH_EDIT && (code==EN_SETFOCUS || code==EN_KILLFOCUS)) {InvalidateRect(window,&shell_search_field,FALSE);return 0;}
      if(id==IDC_SEARCH_CASE || id==IDC_SEARCH_WORD) {shell_search_changed();return 0;}
      if(id==IDC_SEARCH_PREV) {shell_search_step(-1);return 0;}
      if(id==IDC_SEARCH_NEXT) {shell_search_step(1);return 0;}
      if(id==IDC_SEARCH_CLOSE) {shell_search_set(0);return 0;}break;
    }
    case WM_ERASEBKGND: return 1;
    case WM_DRAWITEM: {
      const DRAWITEMSTRUCT *item=(const DRAWITEMSTRUCT *)lp;wchar_t text[8];GetWindowTextW(item->hwndItem,text,8);
      shell_draw_control(item,text,SHELL_CONTROL_GHOST,shell_colors->layer_side);return TRUE;
    }
    case WM_PAINT: {
      PAINTSTRUCT ps;HDC dc=BeginPaint(window,&ps);RECT r;GetClientRect(window,&r);
      shell_toc_fill(dc,r,shell_colors->layer_side);r.top=r.bottom-1;
      shell_toc_fill(dc,r,shell_blend(shell_colors->layer_side,shell_colors->line_rgb,SHELL_LINE_ALPHA));
      if(host_shell && shell_search_field.right>shell_search_field.left) {
        shell_d2d_look look={SHELL_CONTROL_FIELD,GetFocus()==shell_search_edit ? SHELL_STATE_FOCUS:0,shell_colors->layer_side,0,1};
        shell_d2d_control(host_shell,dc,&shell_search_field,L"",shell_is_dark(),&look);
      }
      EndPaint(window,&ps);return 0;
    }
    case WM_CTLCOLORSTATIC:case WM_CTLCOLOREDIT: {
      /* The field is a float surface; the labels sit on the bar itself. */
      static HBRUSH brushes[2];static uint32_t colors[2];
      int edit=message==WM_CTLCOLOREDIT;uint32_t color=edit ? shell_colors->layer_float:shell_colors->layer_side;
      if(!brushes[edit] || colors[edit]!=color) {
        if(brushes[edit]) DeleteObject(brushes[edit]);
        colors[edit]=color;brushes[edit]=CreateSolidBrush(shell_colorref(color));
      }
      SetTextColor((HDC)wp,shell_colorref(edit ? shell_colors->text:shell_colors->text_secondary));
      SetBkColor((HDC)wp,shell_colorref(color));return (LRESULT)brushes[edit];
    }
  }
  return DefWindowProcW(window,message,wp,lp);
}
static void shell_search_create(HWND parent) {
  shell_search_button=shell_make_button(parent,IDC_SHELL_SEARCH,L"全文搜索");
  WNDCLASSW wc={0};wc.lpfnWndProc=shell_search_proc;wc.hInstance=GetModuleHandleW(NULL);wc.lpszClassName=L"EXReaderSearchBar";wc.hCursor=LoadCursorW(NULL,IDC_ARROW);RegisterClassW(&wc);
  shell_search_bar=CreateWindowExW(0,wc.lpszClassName,L"全文搜索",WS_CHILD|WS_CLIPCHILDREN,0,0,0,0,parent,NULL,wc.hInstance,NULL);
  shell_search_label_control=CreateWindowExW(0,L"STATIC",L"搜索",WS_CHILD|WS_VISIBLE|SS_CENTERIMAGE,0,0,0,0,shell_search_bar,NULL,NULL,NULL);
  /* Borderless: the bar paints the field frame around it. */
  shell_search_edit=CreateWindowExW(0,L"EDIT",L"",WS_CHILD|WS_VISIBLE|WS_TABSTOP|ES_AUTOHSCROLL,0,0,0,0,shell_search_bar,(HMENU)IDC_SEARCH_EDIT,NULL,NULL);
  SendMessageW(shell_search_edit,EM_SETLIMITTEXT,1024,0);
  shell_search_count=CreateWindowExW(0,L"STATIC",L"第 0 / 共 0 个",WS_CHILD|WS_VISIBLE|SS_CENTER|SS_CENTERIMAGE,0,0,0,0,shell_search_bar,(HMENU)IDC_SEARCH_COUNT,NULL,NULL);
  HWND *controls[]={&shell_search_prev,&shell_search_next,&shell_search_case,&shell_search_word,&shell_search_close};
  int ids[]={IDC_SEARCH_PREV,IDC_SEARCH_NEXT,IDC_SEARCH_CASE,IDC_SEARCH_WORD,IDC_SEARCH_CLOSE};
  const wchar_t *names[]={L"↑",L"↓",L"Aa",L"全词",L"×"};
  for(int i=0;i<5;i++) {
    int toggle=i==2 || i==3;
    *controls[i]=CreateWindowExW(0,L"BUTTON",names[i],WS_CHILD|WS_VISIBLE|WS_TABSTOP|(toggle ? BS_AUTOCHECKBOX:BS_OWNERDRAW),0,0,0,0,shell_search_bar,(HMENU)(INT_PTR)ids[i],NULL,NULL);
    if(toggle) shell_adopt_toggle(*controls[i]);else shell_adopt_button(*controls[i]);
  }
  shell_search_label();
}
static int shell_search_key(const MSG *m) {
  if(m->message!=WM_KEYDOWN) return 0;
  if(m->wParam=='F' && GetKeyState(VK_CONTROL)<0 && shell_active) {shell_search_set(1);return 1;}
  if(!shell_search_open) return 0;
  if(m->wParam==VK_ESCAPE) {shell_search_set(0);return 1;}
  if(m->wParam==VK_RETURN && (m->hwnd==shell_search_bar || IsChild(shell_search_bar,m->hwnd) || m->hwnd==g.page)) {
    if(shell_search_pending) shell_search_start();else shell_search_step((GetKeyState(VK_SHIFT)<0 || (host_offscreen && shell_search_test_shift)) ? -1:1);shell_search_test_shift=0;return 1;
  }
  if(m->hwnd==shell_search_bar || IsChild(shell_search_bar,m->hwnd)) return IsDialogMessageW(shell_search_bar,(MSG *)m)!=0;
  return 0;
}
static void shell_search_destroy(void) {
  if(shell_search_working) InterlockedExchange(&shell_search_working->cancel,1);
  if(shell_search_thread) {WaitForSingleObject(shell_search_thread,INFINITE);CloseHandle(shell_search_thread);shell_search_thread=NULL;}
  if(shell_search_working) {free(shell_search_working->hits);free(shell_search_working->path);free(shell_search_working->needle);free(shell_search_working);shell_search_working=NULL;}
  shell_search_cache_free();free(shell_search_hits);shell_search_hits=NULL;
}

static void shell_search_shade(HDC dc,HRGN region,int current) {
  typedef BOOL (WINAPI *blend_fn)(HDC,int,int,int,int,HDC,int,int,int,int,BLENDFUNCTION);
  static HMODULE module;static blend_fn blend;
  if(!module) {module=LoadLibraryW(L"msimg32.dll");if(module) blend=(blend_fn)(void (*)(void))GetProcAddress(module,"AlphaBlend");}
  RECT box;if(!blend || GetRgnBox(region,&box)==NULLREGION) return;
  BITMAPINFO info={0};void *pixel=NULL;info.bmiHeader.biSize=sizeof(BITMAPINFOHEADER);
  info.bmiHeader.biWidth=info.bmiHeader.biHeight=1;info.bmiHeader.biPlanes=1;info.bmiHeader.biBitCount=32;
  HBITMAP bitmap=CreateDIBSection(dc,&info,DIB_RGB_COLORS,&pixel,NULL,0);if(!bitmap) return;
  *(uint32_t *)pixel=SHELL_ACCENT_SOFT_RGB;HDC source=CreateCompatibleDC(dc);
  HGDIOBJ old=SelectObject(source,bitmap);int saved=SaveDC(dc);ExtSelectClipRgn(dc,region,RGN_AND);
  BLENDFUNCTION alpha={AC_SRC_OVER,0,(BYTE)lroundf(255*(current ? SHELL_ACCENT_SOFT_ALPHA:SHELL_ACCENT_SOFTER_ALPHA)),0};
  blend(dc,box.left,box.top,box.right-box.left,box.bottom-box.top,source,0,0,1,1,alpha);
  RestoreDC(dc,saved);SelectObject(source,old);DeleteDC(source);DeleteObject(bitmap);
}
/* Source clusters follow each glyph's physical advance axis, including vertical. */
static void shell_search_paint(HDC dc) {
  if(!shell_search_open || shell_search_book!=g.frame.book_id || !shell_search_count_value || !g.frame.valid) return;
  const exr_glyph *glyphs=g.frame.glyphs;size_t count=g.frame.glyph_count;
  if(!glyphs && g.frame.hit_layout) glyphs=exr_layout_glyphs(g.frame.hit_layout,&count);
  size_t part=g.frame.fixed ? g.frame.page:g.frame.part,lo=0,hi=shell_search_count_value;
  while(lo<hi) {size_t mid=lo+(hi-lo)/2;exr_search_result r=shell_search_hits[mid];if(r.part<part || (r.part==part && r.offset+r.length<=g.frame.range_start)) lo=mid+1;else hi=mid;}
  HRGN normal=CreateRectRgn(0,0,0,0),active=CreateRectRgn(0,0,0,0);
  for(size_t i=lo;i<shell_search_count_value;i++) {
    exr_search_result r=shell_search_hits[i];if(r.part!=part || r.offset>=g.frame.range_end) break;
    HRGN region=CreateRectRgn(0,0,0,0);
    if(g.frame.fixed && g.frame.fixed_text) {
      size_t n;const exr_text_region *regions=exr_fixed_text_regions(g.frame.fixed_text,&n);
      exr_viewport vp;exr_error error={0};
      if(exr_viewport_create(&g.frame.geometry,g.frame.render_scale,&vp,&error)==EXR_OK) for(size_t j=0;j<n;j++) {
        const exr_text_region *v=&regions[j];if(v->end<=r.offset || v->start>=r.offset+r.length) continue;
        POINT points[4];
        for(int k=0;k<4;k++) {
          double x=v->quad[k*2],y=v->quad[k*2+1];
          points[k].x=g.view.dx+(LONG)((vp.matrix[0]*x+vp.matrix[2]*y+vp.matrix[4])*g.view.scale);
          points[k].y=g.view.dy+(LONG)((vp.matrix[1]*x+vp.matrix[3]*y+vp.matrix[5])*g.view.scale);
        }
        HRGN q=CreatePolygonRgn(points,4,WINDING);CombineRgn(region,region,q,RGN_OR);DeleteObject(q);
      }
    } else for(size_t j=0;j<count;j++) {
      const exr_glyph *v=&glyphs[j];if((v->flags&EXR_GLYPH_HIDDEN) || v->cluster_end<=r.offset || v->cluster_start>=r.offset+r.length) continue;
      float x=v->x,y=v->baseline-v->size,w=v->advance,h=v->size*1.25f;
      if(v->flags&EXR_GLYPH_VERTICAL) {x=v->x-v->size*.5f;y=v->baseline;w=v->size;h=v->advance;}
      int left=g.view.dx+(int)floor(x*g.view.scale),top=g.view.dy+(int)floor(y*g.view.scale);
      HRGN q=CreateRectRgn(left,top,left+max(1,(int)ceil(w*g.view.scale)),top+max(1,(int)ceil(h*g.view.scale)));
      CombineRgn(region,region,q,RGN_OR);DeleteObject(q);
    }
    HRGN combined=i==shell_search_current ? active:normal;
    CombineRgn(combined,combined,region,RGN_OR);DeleteObject(region);
  }
  CombineRgn(normal,normal,active,RGN_DIFF);
  shell_search_shade(dc,normal,0);shell_search_shade(dc,active,1);DeleteObject(normal);DeleteObject(active);
}

static void shell_search_reset_book(void) {
  static int64_t previous;
  if(previous==g.session.book_id) return;
  previous=g.session.book_id;
  if(shell_search_working) InterlockedExchange(&shell_search_working->cancel,1);
  shell_search_revision++;shell_search_pending=0;shell_search_jump_pending=0;
  free(shell_search_hits);shell_search_hits=NULL;shell_search_count_value=0;shell_search_book=0;
  SetWindowTextW(shell_search_edit,L"");shell_search_label();
}
