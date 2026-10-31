/* SPDX-License-Identifier: MIT
 * UI-thread bounded shelf. Catalog queries run only on the existing worker. */
static ULONGLONG product_shelf_due;
static int product_shelf_reveal;
static void product_shelf_remember(void) {
  if(!g.books || !g.shelf_cursors || g.shelf_applying || g.shelf_filter_pending || product_shelf_reveal) return;
  LRESULT top=SendMessageW(g.books,LB_GETTOPINDEX,0,0),selected=SendMessageW(g.books,LB_GETCURSEL,0,0);
  if(top>=0 && (size_t)top<g.shelf_count) snprintf(g.shelf_top_key,sizeof(g.shelf_top_key),"%s",g.shelf_cursors[top].key);
  if(selected!=LB_ERR && selected>=0 && (size_t)selected<g.shelf_count)
    snprintf(g.shelf_selected_key,sizeof(g.shelf_selected_key),"%s",g.shelf_cursors[selected].key);
}
static void product_shelf_schedule(int direction,int reset) {
  if(g.closing) return;
  if(reset) { product_shelf_reveal=0;g.shelf_top_key[0]=0;g.shelf_selected_key[0]=0;g.shelf_filter_pending=1; }
  else product_shelf_remember();
  g.shelf_generation++;g.shelf_requested_direction=direction;g.shelf_need_refresh=1;
  product_shelf_due=GetTickCount64()+(reset ? 200:30);
  SetTimer(g.window,3,reset ? 200:30,NULL);
}
static void product_shelf_search_changed(void) {
  wchar_t text[257];GetWindowTextW(g.shelf_search,text,257);
  char *query=host_utf8(text);
  if(!query) { set_status(L"无法读取搜索文字，保留当前书架。");return; }
  free(g.shelf_query);g.shelf_query=query;
  product_shelf_schedule(0,1);
  settings_save();
}
static void product_shelf_dispatch(void) {
  if(!g.books || !IsWindowVisible(g.books)) return;
#ifdef EXR_READER_WINDOWS_IMPORT_ORGANIZE
  if(winio_modal_blocked()) return;
#endif
#ifdef EXR_READER_DESKTOP_METADATA
  if(g.metadata_dialog || g.metadata_running) return;
#endif
  if(!g.shelf_need_refresh || !g.product_ready || g.product_pending || g.closing || g.job || g.pending) return;
  ULONGLONG now=GetTickCount64();
  if(now<product_shelf_due) { SetTimer(g.window,3,(UINT)(product_shelf_due-now),NULL);return; }
  host_job *job=job_new(JOB_PRODUCT_SHELF);
  if(!job) { g.shelf_need_refresh=0;set_status(L"无法建立书架查询任务。");return; }
  job->product_shelf_generation=g.shelf_generation;job->product_shelf_direction=g.shelf_requested_direction;
  snprintf(job->product_group_id,sizeof(job->product_group_id),"%s",g.shelf_group_id);
  job->product_group_kind=g.shelf_group_kind;
  job->product_shelf_query=host_strdup(g.shelf_query ? g.shelf_query:"");
  if(job->product_shelf_direction && g.shelf_cursors && g.shelf_count) {
    size_t at=job->product_shelf_direction<0 ? 0:g.shelf_count-1;
    job->product_cursor_ordinal=g.shelf_cursors[at].ordinal;
    job->product_cursor_title=host_strdup(g.shelf_cursors[at].sort_title);
    job->product_cursor_key=host_strdup(g.shelf_cursors[at].key);
    if(!job->product_cursor_title || !job->product_cursor_key) { job_release(job);g.shelf_need_refresh=0;return; }
  } else {
    job->product_shelf_direction=0;
    if(!g.shelf_filter_pending && g.shelf_top_key[0]) job->product_anchor_key=host_strdup(g.shelf_top_key);
    if(!g.shelf_filter_pending && g.shelf_top_key[0] && !job->product_anchor_key) { job_release(job);g.shelf_need_refresh=0;return; }
    if(job->product_anchor_key && g.shelf_group_id[0]) {
      for(size_t i=0;i<g.shelf_count;i++) if(!strcmp(g.shelf_cursors[i].key,job->product_anchor_key)) {
        job->product_cursor_ordinal=g.shelf_cursors[i].ordinal;
        job->product_cursor_key=host_strdup(g.shelf_cursors[i].key);
        if(!job->product_cursor_key) { job_release(job);g.shelf_need_refresh=0;return; }
        break;
      }
    }
  }
  if(!job->product_shelf_query) { job_release(job);g.shelf_need_refresh=0;return; }
  g.shelf_need_refresh=0;g.shelf_queries++;job_start(job);
}
static void product_shelf_edges(void) {
  if(!g.books || !IsWindowVisible(g.books)) return;
  if(!g.product_ready || g.product_pending || !g.shelf_cursors || !g.shelf_count || g.shelf_filter_pending ||
     g.shelf_applying || g.closing || g.job || g.pending || g.shelf_need_refresh) return;
  RECT area;GetClientRect(g.books,&area);LRESULT height=SendMessageW(g.books,LB_GETITEMHEIGHT,0,0);
  LRESULT top=SendMessageW(g.books,LB_GETTOPINDEX,0,0);
  if(height<=0 || top<0) return;
  size_t visible=(size_t)((area.bottom+height-1)/height),last=(size_t)top+visible;
  if(g.shelf_after && last+4>=g.shelf_count) product_shelf_schedule(1,0);
  else if(g.shelf_before && top<4) product_shelf_schedule(-1,0);
}
/* Native observers can distinguish a complete list from LB_RESETCONTENT /
   LB_ADDSTRING in progress without assuming that two messages are atomic. */
static ULONG_PTR product_shelf_snapshot_serial;
static void product_shelf_snapshot_changed(void) {
  SetPropW(g.books,L"EXReaderShelfSnapshot",(HANDLE)++product_shelf_snapshot_serial);
}
static void product_shelf_accept(host_job *job) {
  if(g.closing || job_cancel_flag(job) || job->product_shelf_generation!=g.shelf_generation) return;
  int direction=job->product_shelf_direction;size_t old=g.shelf_count,incoming=job->product_book_count;
  if(incoming>50) return;
  product_shelf_remember();
  if(!direction && !g.shelf_filter_pending && job->product_anchor_key &&
     strcmp(job->product_anchor_key,g.shelf_top_key)) { product_shelf_schedule(0,0);return; }
  char top_key[72];snprintf(top_key,sizeof(top_key),"%s",g.shelf_top_key);
  size_t drop=direction && old+incoming>150 ? old+incoming-150:0;
  if(drop && g.shelf_cursors) {
    RECT area;GetClientRect(g.books,&area);LRESULT height=SendMessageW(g.books,LB_GETITEMHEIGHT,0,0);
    LRESULT top=SendMessageW(g.books,LB_GETTOPINDEX,0,0);
    size_t first=top<0 ? 0:(size_t)top;
    size_t visible=height>0 ? (size_t)((area.bottom+height-1)/height):old;
    size_t last=first+visible;
    if((direction>0 && first<drop) || (direction<0 && last>old-drop)) return;
  }
  size_t retained=direction ? old-drop:0,count=retained+incoming;
  exr_book *books=calloc(count ? count:1,sizeof(*books));
  host_shelf_cursor *cursors=calloc(count ? count:1,sizeof(*cursors));
  if(!books || !cursors) { free(books);free(cursors);set_status(L"无法更新书架窗口，保留旧列表。");return; }
  size_t offset=direction<0 ? incoming:0,first_old=direction>0 ? drop:0;
  for(size_t i=0;i<retained;i++) {
    size_t from=first_old+i;books[offset+i]=g.shelf[from];memset(&g.shelf[from],0,sizeof(*books));
    if(g.shelf_cursors) { cursors[offset+i]=g.shelf_cursors[from];memset(&g.shelf_cursors[from],0,sizeof(*cursors)); }
  }
  offset=direction<0 ? 0:retained;
  for(size_t i=0;i<incoming;i++) {
    books[offset+i]=job->product_books[i];memset(&job->product_books[i],0,sizeof(*books));
    cursors[offset+i]=job->product_cursors[i];memset(&job->product_cursors[i],0,sizeof(*cursors));
  }
  int before=direction>0 ? g.shelf_before:job->product_shelf_before;
  int after=direction<0 ? g.shelf_after:job->product_shelf_after;
  if(drop) { if(direction<0) after=1;else before=1; }
#ifdef EXR_WINDOWS_FRAME_REVIEW
  f08_shelf_pending=job->review;
  f08_record("shelf_apply",0,&job->review,(unsigned long)product_shelf_snapshot_serial,0,IDC_BOOKS,0,0,count,direction);
#endif
  g.shelf_applying=1;shelf_clear();g.shelf=books;g.shelf_cursors=cursors;g.shelf_count=count;
  g.shelf_before=before;g.shelf_after=after;g.shelf_filter_pending=0;
  g.shelf_evicted+=(unsigned)drop;if(count>g.shelf_max_cached) g.shelf_max_cached=(unsigned)count;
  product_shelf_snapshot_changed();
  SendMessageW(g.books,WM_SETREDRAW,FALSE,0);SendMessageW(g.books,LB_RESETCONTENT,0,0);
  LRESULT top=job->product_anchor_predecessor && count ? (LRESULT)(count-1):0,selected=LB_ERR;
  for(size_t i=0;i<count;i++) {
    wchar_t line[512];shelf_display(&books[i],line,512);SendMessageW(g.books,LB_ADDSTRING,0,(LPARAM)line);
    if(cursors[i].key && !strcmp(cursors[i].key,top_key)) top=(LRESULT)i;
    if(cursors[i].key && !strcmp(cursors[i].key,g.shelf_selected_key)) selected=(LRESULT)i;
  }
  SendMessageW(g.books,LB_SETCURSEL,(WPARAM)selected,0);SendMessageW(g.books,LB_SETTOPINDEX,(WPARAM)top,0);
  SendMessageW(g.books,WM_SETREDRAW,TRUE,0);InvalidateRect(g.books,NULL,TRUE);g.shelf_applying=0;
  product_shelf_snapshot_changed();
  product_shelf_reveal=0;product_shelf_remember();SetTimer(g.window,4,300,NULL);PostMessageW(g.window,WM_APP+31,0,0);
}
static LRESULT CALLBACK product_shelf_procedure(HWND window,UINT message,WPARAM wparam,LPARAM lparam) {
#ifdef EXR_WINDOWS_FRAME_REVIEW
  if(f08_count_query(message)) return CallWindowProcW(g.shelf_procedure,window,message,wparam,lparam);
#endif
  if(message==WM_NCDESTROY) {
    RemovePropW(window,L"EXReaderShelfSnapshot");
#ifdef EXR_WINDOWS_FRAME_REVIEW
    RemovePropW(window,L"EXReaderF08ShelfPaintedSnapshot");RemovePropW(window,L"EXReaderF08ShelfTopBookId");
#endif
  }
#ifdef EXR_WINDOWS_FRAME_REVIEW
  /* Every native listbox message is retained, including direct GDI paths.
     Getters bypass this subclass so observations cannot recursively trace themselves. */
  LONGLONG f08_start=f08_tick();LONG f08_previous=f08_active_input;
  LRESULT f08_top=CallWindowProcW(g.shelf_procedure,window,LB_GETTOPINDEX,0,0);
  LRESULT f08_count_before=CallWindowProcW(g.shelf_procedure,window,LB_GETCOUNT,0,0);
  if(message==WM_MOUSEWHEEL || message==WM_VSCROLL || message==WM_KEYDOWN || message==WM_LBUTTONDOWN || message==LB_SETTOPINDEX)
    f08_previous=f08_input_begin(IDC_BOOKS,message);
  f08_origin f08_old_pending=f08_shelf_pending;
  int f08_direct=message==WM_MOUSEWHEEL || message==WM_VSCROLL || message==WM_HSCROLL || message==WM_KEYDOWN || message==LB_SETTOPINDEX;
  if(f08_direct) { memset(&f08_shelf_pending,0,sizeof(f08_shelf_pending));
    f08_shelf_pending.id=-InterlockedIncrement(&f08_direct_frames);f08_shelf_pending.input_id=f08_active_input;
    f08_shelf_pending.worker_start_qpc=f08_start; }
  f08_origin f08_source=f08_shelf_pending;
  f08_record("shelf_message_begin",f08_start,&f08_source,(unsigned long)product_shelf_snapshot_serial,0,IDC_BOOKS,message,0,f08_top,f08_count_before);
#endif
  LRESULT result=CallWindowProcW(g.shelf_procedure,window,message,wparam,lparam);
#ifdef EXR_WINDOWS_FRAME_REVIEW
  { BOOL flushed=GdiFlush();
    LRESULT top=CallWindowProcW(g.shelf_procedure,window,LB_GETTOPINDEX,0,0);
    LRESULT count=CallWindowProcW(g.shelf_procedure,window,LB_GETCOUNT,0,0);
    BOOL pending=GetUpdateRect(window,NULL,FALSE);int changed=top!=f08_top || count!=f08_count_before;
    if(message==WM_SETREDRAW) f08_shelf_redraw=wparam!=0;
    f08_record("shelf_gdi_complete",f08_start,&f08_source,(unsigned long)product_shelf_snapshot_serial,0,IDC_BOOKS,message,
      flushed ? 1+(pending ? 2:0)+(f08_shelf_redraw ? 4:0):-1,top,count);
    if(flushed && f08_shelf_redraw && !pending && !(product_shelf_snapshot_serial&1) &&
        (message==WM_PAINT || (f08_direct && changed))) {
      LONGLONG top_book=top>=0 && (size_t)top<g.shelf_count ? g.shelf[top].id:0;
      SetPropW(window,L"EXReaderF08ShelfPaintedSnapshot",(HANDLE)product_shelf_snapshot_serial);
      SetPropW(window,L"EXReaderF08ShelfTopBookId",(HANDLE)(ULONG_PTR)top_book);
      f08_record("shelf_frame_complete",f08_start,&f08_source,(unsigned long)product_shelf_snapshot_serial,top_book,IDC_BOOKS,message,1,top,count);
      memset(&f08_shelf_pending,0,sizeof(f08_shelf_pending));
    } else if(f08_direct && !changed) f08_shelf_pending=f08_old_pending;
  }
  f08_active_input=f08_previous;
#endif
  if(message==WM_VSCROLL || message==WM_MOUSEWHEEL || message==WM_KEYDOWN || message==WM_SIZE) {
    product_shelf_remember();SetTimer(g.window,4,300,NULL);PostMessageW(g.window,WM_APP+31,0,0);
  }
  return result;
}
