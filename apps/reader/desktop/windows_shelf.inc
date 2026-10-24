/* SPDX-License-Identifier: MIT
 * UI-thread bounded shelf. Catalog queries run only on the existing worker. */
static ULONGLONG product_shelf_due;
static void product_shelf_remember(void) {
  if(!g.books || !g.shelf_cursors || g.shelf_applying || g.shelf_filter_pending) return;
  LRESULT top=SendMessageW(g.books,LB_GETTOPINDEX,0,0),selected=SendMessageW(g.books,LB_GETCURSEL,0,0);
  if(top>=0 && (size_t)top<g.shelf_count) snprintf(g.shelf_top_key,sizeof(g.shelf_top_key),"%s",g.shelf_cursors[top].key);
  if(selected!=LB_ERR && selected>=0 && (size_t)selected<g.shelf_count)
    snprintf(g.shelf_selected_key,sizeof(g.shelf_selected_key),"%s",g.shelf_cursors[selected].key);
}
static void product_shelf_schedule(int direction,int reset) {
  if(g.closing) return;
  if(reset) { g.shelf_top_key[0]=0;g.shelf_selected_key[0]=0;g.shelf_filter_pending=1; }
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
#ifdef EXR_READER_DESKTOP_METADATA
  if(g.metadata_dialog || g.metadata_running) return;
#endif
  if(!g.shelf_need_refresh || !g.product_ready || g.product_pending || g.closing || g.job || g.pending) return;
  ULONGLONG now=GetTickCount64();
  if(now<product_shelf_due) { SetTimer(g.window,3,(UINT)(product_shelf_due-now),NULL);return; }
  host_job *job=job_new(JOB_PRODUCT_SHELF);
  if(!job) { g.shelf_need_refresh=0;set_status(L"无法建立书架查询任务。");return; }
  job->product_shelf_generation=g.shelf_generation;job->product_shelf_direction=g.shelf_requested_direction;
  job->product_shelf_query=host_strdup(g.shelf_query ? g.shelf_query:"");
  if(job->product_shelf_direction && g.shelf_cursors && g.shelf_count) {
    size_t at=job->product_shelf_direction<0 ? 0:g.shelf_count-1;
    job->product_cursor_title=host_strdup(g.shelf_cursors[at].sort_title);
    job->product_cursor_key=host_strdup(g.shelf_cursors[at].key);
    if(!job->product_cursor_title || !job->product_cursor_key) { job_release(job);g.shelf_need_refresh=0;return; }
  } else {
    job->product_shelf_direction=0;
    if(!g.shelf_filter_pending && g.shelf_top_key[0]) job->product_anchor_key=host_strdup(g.shelf_top_key);
    if(!g.shelf_filter_pending && g.shelf_top_key[0] && !job->product_anchor_key) { job_release(job);g.shelf_need_refresh=0;return; }
  }
  if(!job->product_shelf_query) { job_release(job);g.shelf_need_refresh=0;return; }
  g.shelf_need_refresh=0;g.shelf_queries++;job_start(job);
}
static void product_shelf_edges(void) {
  if(!g.product_ready || g.product_pending || !g.shelf_cursors || !g.shelf_count || g.shelf_filter_pending ||
     g.shelf_applying || g.closing || g.job || g.pending || g.shelf_need_refresh) return;
  RECT area;GetClientRect(g.books,&area);LRESULT height=SendMessageW(g.books,LB_GETITEMHEIGHT,0,0);
  LRESULT top=SendMessageW(g.books,LB_GETTOPINDEX,0,0);
  if(height<=0 || top<0) return;
  size_t visible=(size_t)((area.bottom+height-1)/height),last=(size_t)top+visible;
  if(g.shelf_after && last+4>=g.shelf_count) product_shelf_schedule(1,0);
  else if(g.shelf_before && top<4) product_shelf_schedule(-1,0);
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
  g.shelf_applying=1;shelf_clear();g.shelf=books;g.shelf_cursors=cursors;g.shelf_count=count;
  g.shelf_before=before;g.shelf_after=after;g.shelf_filter_pending=0;
  g.shelf_evicted+=(unsigned)drop;if(count>g.shelf_max_cached) g.shelf_max_cached=(unsigned)count;
  SendMessageW(g.books,WM_SETREDRAW,FALSE,0);SendMessageW(g.books,LB_RESETCONTENT,0,0);
  LRESULT top=0,selected=LB_ERR;
  for(size_t i=0;i<count;i++) {
    wchar_t line[512];shelf_display(&books[i],line,512);SendMessageW(g.books,LB_ADDSTRING,0,(LPARAM)line);
    if(cursors[i].key && !strcmp(cursors[i].key,top_key)) top=(LRESULT)i;
    if(cursors[i].key && !strcmp(cursors[i].key,g.shelf_selected_key)) selected=(LRESULT)i;
  }
  SendMessageW(g.books,LB_SETCURSEL,(WPARAM)selected,0);SendMessageW(g.books,LB_SETTOPINDEX,(WPARAM)top,0);
  SendMessageW(g.books,WM_SETREDRAW,TRUE,0);InvalidateRect(g.books,NULL,TRUE);g.shelf_applying=0;
  product_shelf_remember();SetTimer(g.window,4,300,NULL);PostMessageW(g.window,WM_APP+31,0,0);
}
static LRESULT CALLBACK product_shelf_procedure(HWND window,UINT message,WPARAM wparam,LPARAM lparam) {
  LRESULT result=CallWindowProcW(g.shelf_procedure,window,message,wparam,lparam);
  if(message==WM_VSCROLL || message==WM_MOUSEWHEEL || message==WM_KEYDOWN || message==WM_SIZE) {
    product_shelf_remember();SetTimer(g.window,4,300,NULL);PostMessageW(g.window,WM_APP+31,0,0);
  }
  return result;
}
