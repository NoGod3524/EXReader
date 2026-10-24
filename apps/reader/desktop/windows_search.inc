/* SPDX-License-Identifier: MIT
 * One bounded batch on the existing serialized worker. The F1 handle never
 * survives its creating OS thread; the UI retains only copied selectors/cursor.
 */
static void winsearch_hit_free(host_search_hit *h) {
  free(h->part_path);free(h->page_id);
  free(h->anchor.exact);free(h->anchor.prefix);free(h->anchor.suffix);free(h->anchor.chapter);
  free(h->fixed.page_id);free(h->fixed.exact);free(h->fixed.prefix);free(h->fixed.suffix);
  memset(h,0,sizeof(*h));
}
static void winsearch_batch_free(host_search_batch *b) {
  for(size_t i=0;i<HOST_SEARCH_BATCH;i++) winsearch_hit_free(&b->hits[i]);
  memset(b,0,sizeof(*b));
}
static char *winsearch_bytes(const char *s,size_t n) {
  if(!s) return NULL;
  if(n==SIZE_MAX) return NULL;
  char *p=malloc(n+1);
  if(p) { memcpy(p,s,n);p[n]=0; }
  return p;
}
static int winsearch_hit_copy(host_search_hit *out,const host_search_hit *h) {
  memset(out,0,sizeof(*out));out->mode=h->mode;out->unit=h->unit;
  if(h->part_path && !(out->part_path=host_strdup(h->part_path))) goto fail;
  if(h->page_id && !(out->page_id=host_strdup(h->page_id))) goto fail;
  if(h->mode!=READER_SEARCH_FIXED) {
    if(!host_anchor_copy(&out->anchor,&h->anchor)) goto fail;
  } else {
    out->fixed=h->fixed;
    out->fixed.page_id=NULL;out->fixed.exact=NULL;out->fixed.prefix=NULL;out->fixed.suffix=NULL;
    if(h->fixed.page_id && !(out->fixed.page_id=host_strdup(h->fixed.page_id))) goto fail;
    if(h->fixed.exact && !(out->fixed.exact=winsearch_bytes(h->fixed.exact,h->fixed.exact_size))) goto fail;
    if(h->fixed.prefix && !(out->fixed.prefix=winsearch_bytes(h->fixed.prefix,h->fixed.prefix_size))) goto fail;
    if(h->fixed.suffix && !(out->fixed.suffix=winsearch_bytes(h->fixed.suffix,h->fixed.suffix_size))) goto fail;
  }
  return 1;
fail:
  winsearch_hit_free(out);return 0;
}
static exr_status winsearch_identity(int64_t book,exr_format format,int fixed,int bounded,
  char out[READER_SEARCH_SOURCE_KEY_MAX+1],const exr_control *control,exr_error *error) {
  char digest[65];uint64_t bytes=0;
  EnterCriticalSection(&g.library_lock);
  exr_status status=reader_catalog_sdk_original_identity(g.library,book,control,digest,&bytes,error);
  LeaveCriticalSection(&g.library_lock);
  if(status!=EXR_OK) return status;
  snprintf(out,READER_SEARCH_SOURCE_KEY_MAX+1,"sdk3.40.0:projection1:%d:%d:%s:%llu",
    (int)format,fixed ? READER_SEARCH_FIXED:bounded ? READER_SEARCH_EPUB:READER_SEARCH_REFLOW,
    digest,(unsigned long long)bytes);
  return EXR_OK;
}
static exr_status winsearch_status(reader_search_status code,const reader_search_error *error) {
  if(code==READER_SEARCH_OK) return EXR_OK;
  if(code==READER_SEARCH_CANCELLED) return EXR_CANCELLED;
  if(code==READER_SEARCH_MEMORY) return EXR_MEMORY;
  if(code==READER_SEARCH_SDK && error->sdk_code) return (exr_status)error->sdk_code;
  return EXR_ARGUMENT;
}
static int winsearch_cancel_check(void *context) {
#ifdef EXR_HOST_WORKER_REVIEW
  /* Existing isolated worker gate, reached by F1's actual control callback. */
  review_pause(4,(host_job *)context);
#endif
  return job_cancel_check(context);
}
static exr_status winsearch_batch_run(host_job *job) {
  reader_search *search=NULL;reader_search_error error={0};reader_search_result result={0};
  reader_search_options options={0};reader_search_status code;
  options.struct_size=sizeof(options);options.control=(exr_control){winsearch_cancel_check,NULL,job};
  options.source_key=g.session.search_key;
  options.resume=job->search_has_resume ? &job->search_resume:NULL;
  if(g.session.fixed) code=reader_search_open_fixed(g.session.fixed_document,job->search_query,
    strlen(job->search_query),&options,&search,&error);
  else if(g.session.bounded) {
    exr_chapter_options chapter=exr_chapter_options_defaults();
    chapter.workspace_budget=8*1024*1024;chapter.window_bytes=64*1024;
    code=reader_search_open_epub(g.session.publication,g.font,&g.session.config,&chapter,
      job->search_query,strlen(job->search_query),&options,&search,&error);
  } else code=reader_search_open_reflow(g.session.document,job->search_query,
    strlen(job->search_query),&options,&search,&error);
  if(code==READER_SEARCH_OK) code=reader_search_next(search,HOST_SEARCH_BATCH,&result,&error);
#ifdef EXR_HOST_WORKER_REVIEW
  if(code==READER_SEARCH_OK) review_pause(5,job);
#endif
  exr_status status=winsearch_status(code,&error);
  if(status==EXR_OK) {
    for(size_t i=0;i<result.count;i++) {
      const reader_search_hit *h=&result.hits[i];
      host_search_hit view={0};view.mode=h->mode;view.unit=h->unit;
      view.part_path=h->part_path;view.page_id=h->page_id;view.anchor=h->anchor;view.fixed=h->fixed;
      if(!winsearch_hit_copy(&job->search_batch.hits[i],&view)) { status=EXR_MEMORY;break; }
      job->search_batch.count++;
    }
    job->search_batch.next=result.next;job->search_batch.complete=result.complete;
  }
  reader_search_result_free(&result);
  if(search) {
    reader_search_error close_error={0};
    if(reader_search_close(&search,&close_error)!=READER_SEARCH_OK && status==EXR_OK) status=EXR_ARGUMENT;
  }
  if(status!=EXR_OK) { winsearch_batch_free(&job->search_batch);snprintf(job->error.message,sizeof(job->error.message),"%s",error.message); }
  return status;
}
static exr_status winsearch_fresh(host_job *job,host_session *out) {
  exr_status status;exr_error *error=&job->error;
  memset(out,0,sizeof(*out));out->book_id=job->book_id;out->fixed=g.session.fixed;out->bounded=g.session.bounded;
  out->config=g.session.config;
  EnterCriticalSection(&g.library_lock);
  if(out->fixed) {
    exr_fixed_open_options options={0};options.struct_size=sizeof(options);options.fallback_font=g.font;
    options.control=(exr_control){job_cancel_check,NULL,job};
    status=exr_library_fixed_source(g.library,job->book_id,&options,&out->fixed_document,error);
  } else if(out->bounded) {
    exr_source source={0};status=exr_library_source(g.library,job->book_id,&source,error);
    if(status==EXR_OK) {
      source.control=(exr_control){job_cancel_check,NULL,job};
      status=exr_publication_open_source(&source,&out->publication,error);
      if(status!=EXR_OK) source.release(source.context);
    }
  } else status=exr_library_document(g.library,job->book_id,&out->document,error);
  LeaveCriticalSection(&g.library_lock);return status;
}
static exr_status winsearch_fixed_resolve(exr_fixed_document *doc,const host_search_hit *hit,
  const exr_control *control,size_t *page,exr_anchor_match *match,exr_error *error) {
  size_t count=0,found=SIZE_MAX;
  const exr_fixed_page *pages=exr_fixed_pages(doc,&count);exr_fixed_text *text=NULL;
  if(!hit->page_id || !pages) return EXR_ARGUMENT;
  for(size_t i=0;i<count;i++) if(pages[i].id && !strcmp(pages[i].id,hit->page_id)) {
    if(found!=SIZE_MAX) return EXR_ARGUMENT;
    found=i;
  }
  if(found==SIZE_MAX) return EXR_ARGUMENT;
  exr_status status=exr_fixed_load_text(doc,found,control,&text,error);
  if(status==EXR_OK) status=exr_fixed_anchor_resolve(pages[found].id,text,&hit->fixed,control,match,error);
  exr_fixed_text_free(text);
  if(status==EXR_OK && match->state!=EXR_ANCHOR_FOUND) return EXR_ARGUMENT;
  if(status==EXR_OK) *page=found;
  return status;
}
static exr_status winsearch_open_run(host_job *job) {
  host_session fresh={0};host_search_hit *hit=&job->search_hit;
  exr_control control={job_cancel_check,NULL,job};exr_anchor_match match={0};
  exr_status status=winsearch_fresh(job,&fresh);size_t target=0;
  if(status==EXR_OK && hit->mode==READER_SEARCH_FIXED && fresh.fixed)
    status=winsearch_fixed_resolve(fresh.fixed_document,hit,&control,&target,&match,&job->error);
  else if(status==EXR_OK && hit->mode==READER_SEARCH_EPUB && fresh.bounded) {
    size_t count=0;const exr_part *parts=exr_publication_parts(fresh.publication,&count);
    if(hit->unit>=count || !hit->part_path || !parts[hit->unit].path || strcmp(parts[hit->unit].path,hit->part_path)) status=EXR_ARGUMENT;
    else {
      status=bounded_pager(&fresh,(size_t)hit->unit,&fresh.pager,&job->error);
      if(status==EXR_OK) status=exr_pager_anchor_resolve(fresh.pager,&hit->anchor,&control,&match,&job->error);
    }
  } else if(status==EXR_OK && hit->mode==READER_SEARCH_REFLOW && !fresh.fixed && !fresh.bounded)
    status=exr_anchor_resolve_ex(fresh.document,&hit->anchor,&control,&match,&job->error);
  else if(status==EXR_OK) status=EXR_ARGUMENT;
  if(status==EXR_OK && match.state!=EXR_ANCHOR_FOUND) status=EXR_ARGUMENT;
  session_clear(&fresh);
  if(status!=EXR_OK || job_cancel_flag(job)) return status!=EXR_OK ? status:EXR_CANCELLED;
  if(hit->mode==READER_SEARCH_FIXED) {
    /* Resolve the stable page ID again against the live renderer's document. */
    status=winsearch_fixed_resolve(g.session.fixed_document,hit,&control,&target,&match,&job->error);
    if(status!=EXR_OK) return status;
    job->target_page=target;job->note_start=match.start;job->note_end=match.end;job->resolved_selection=1;
  } else {
    job->has_anchor=job->anchor_host_owned=1;
    if(!host_anchor_copy(&job->anchor,&hit->anchor)) return EXR_MEMORY;
    job->use_offset=1;
    if(hit->mode==READER_SEARCH_EPUB) {
      job->target_part=(size_t)hit->unit;job->part_path=host_strdup(hit->part_path);
      if(!job->part_path) return EXR_MEMORY;
    }
  }
  return job_go(job);
}
static exr_status winsearch_job(host_job *job) {
  if(!g.session.active || job->book_id!=g.session.book_id || job->book_id!=g.current.id) return EXR_CANCELLED;
  exr_control control={job_cancel_check,NULL,job};char key[READER_SEARCH_SOURCE_KEY_MAX+1];
  exr_status status=winsearch_identity(job->book_id,g.current.format,g.session.fixed,g.session.bounded,key,&control,&job->error);
  if(status!=EXR_OK) return status;
  if(strcmp(key,g.session.search_key)) {
    snprintf(job->error.message,sizeof(job->error.message),"The original changed; reopen the book before searching");return EXR_ARGUMENT;
  }
  if(g.current.format==EXR_CBZ) {
    snprintf(job->error.message,sizeof(job->error.message),"Image-only CBZ pages do not contain searchable text; OCR is not enabled");
    return EXR_UNSUPPORTED;
  }
  return job->kind==JOB_SEARCH_BATCH ? winsearch_batch_run(job):winsearch_open_run(job);
}
static void winsearch_controls(void) {
  if(!inbook.dialog) return;
  HWND focused=GetFocus();
  int busy=inbook.running || g.job || g.pending || g.closing;
  EnableWindow(inbook.find,!busy);
  EnableWindow(inbook.next,!busy && inbook.have_cursor && !inbook.batch.complete);
  LRESULT selected=SendMessageW(inbook.rows,LB_GETCURSEL,0,0);
  EnableWindow(inbook.open,!busy && selected!=LB_ERR && (size_t)selected<inbook.batch.count);
  EnableWindow(inbook.cancel,inbook.running);
  /* Disabling an invoked button can clear native keyboard focus. Keep Escape
     and Tab available while the worker runs and after it publishes a result. */
  if(focused && IsChild(inbook.dialog,focused) && !IsWindowEnabled(focused) &&
     GetActiveWindow()==inbook.dialog) {
    HWND current=GetFocus();
    if(!current || current==focused || !IsWindowEnabled(current))
      SetFocus(inbook.running ? inbook.cancel:inbook.query);
  }
}
static void winsearch_cancel(void) {
  if(g.job && (g.job->kind==JOB_SEARCH_BATCH || g.job->kind==JOB_SEARCH_OPEN))
    InterlockedExchange(&g.job->cancel,1);
}
static void winsearch_close(void) {
  inbook.generation++;winsearch_cancel();
  HWND dialog=inbook.dialog;inbook.dialog=NULL;
  if(dialog) DestroyWindow(dialog);
  winsearch_batch_free(&inbook.batch);inbook.have_cursor=0;
  inbook.query=inbook.find=inbook.next=inbook.rows=inbook.open=inbook.cancel=inbook.message=NULL;
  inbook.book_id=0;
  if(!g.closing && g.page) SetFocus(g.page);
}
static void winsearch_submit(int next,int open_hit) {
  if(!inbook.dialog || inbook.running || g.job || g.pending || g.closing ||
     !g.session.active || g.current.id!=inbook.book_id) return;
  host_job *job=job_new(open_hit ? JOB_SEARCH_OPEN:JOB_SEARCH_BATCH);
  if(!job) { SetWindowTextW(inbook.message,L"内存不足，未启动查找。");return; }
  job->book_id=inbook.book_id;job->search_generation=inbook.generation;
  if(open_hit) {
    LRESULT selected=SendMessageW(inbook.rows,LB_GETCURSEL,0,0);
    if(selected==LB_ERR || (size_t)selected>=inbook.batch.count ||
       !winsearch_hit_copy(&job->search_hit,&inbook.batch.hits[selected])) { job_release(job);return; }
  } else {
    wchar_t wide[4097];GetWindowTextW(inbook.query,wide,4097);
    job->search_query=host_utf8(wide);
    if(!job->search_query || !job->search_query[0] || strlen(job->search_query)>READER_SEARCH_QUERY_MAX) {
      job_release(job);SetWindowTextW(inbook.message,L"请输入1至4096字节的有效文字。");return;
    }
    if(next) {
      if(!inbook.have_cursor || inbook.batch.complete) { job_release(job);return; }
      job->search_resume=inbook.batch.next;job->search_has_resume=1;
    }
  }
  inbook.running=1;SetWindowTextW(inbook.message,open_hit ? L"正在独立核对原文…":L"正在查找，可随时取消…");
  job_submit(job);
  if(!g.job || (g.job->kind!=JOB_SEARCH_BATCH && g.job->kind!=JOB_SEARCH_OPEN)) inbook.running=0;
  winsearch_controls();
}
static void winsearch_accept(host_job *job) {
  inbook.running=0;
  if(!inbook.dialog || job->search_generation!=inbook.generation || g.closing || g.pending ||
     job->book_id!=g.current.id || job->book_id!=inbook.book_id) { winsearch_controls();return; }
  if(job->status!=EXR_OK || job_cancel_flag(job)) {
    SetWindowTextW(inbook.message,job->status==EXR_CANCELLED || job_cancel_flag(job) ?
      L"已取消，上一批结果和位置已保留。":job->status==EXR_UNSUPPORTED && g.current.format==EXR_CBZ ?
      L"本书是图像页，暂不支持文字查找（不包含OCR）。":L"查找或原文核对失败，未跳转；请重新打开书籍后重试。");
    winsearch_controls();return;
  }
  if(job->kind==JOB_SEARCH_OPEN) {
    /* Reuse the host's existing frame acceptance/progress path after the worker
       independently resolved FOUND. No search offset becomes a navigation hint. */
    job->kind=JOB_GO;handle_job_complete(job);
    SetWindowTextW(inbook.message,L"已独立核对原文并定位。");winsearch_controls();return;
  }
  if(job->search_batch.count || !inbook.have_cursor) {
    winsearch_batch_free(&inbook.batch);inbook.batch=job->search_batch;
    memset(&job->search_batch,0,sizeof(job->search_batch));
    SendMessageW(inbook.rows,LB_RESETCONTENT,0,0);
    for(size_t i=0;i<inbook.batch.count;i++) {
      host_search_hit *hit=&inbook.batch.hits[i];char preview[256];wchar_t line[384];
      const char *exact=hit->mode==READER_SEARCH_FIXED ? hit->fixed.exact:hit->anchor.exact;
      size_t size=hit->mode==READER_SEARCH_FIXED ? hit->fixed.exact_size:exact ? strlen(exact):0;
      truncate_utf8(preview,sizeof(preview),exact,size);
      wchar_t *text=host_wide(preview,strlen(preview));
      swprintf(line,384,L"%llu · %ls",(unsigned long long)(hit->unit+1),text ? text:L"");free(text);
      SendMessageW(inbook.rows,LB_ADDSTRING,0,(LPARAM)line);
    }
    if(inbook.batch.count) SendMessageW(inbook.rows,LB_SETCURSEL,0,0);
  } else {
    /* The public F1 contract requires a final empty batch for exactly 32 hits.
       Preserve the previous page; empty tail does not mean no matches. */
    inbook.batch.next=job->search_batch.next;inbook.batch.complete=job->search_batch.complete;
  }
  inbook.have_cursor=1;
  SetWindowTextW(inbook.message,inbook.batch.complete ?
    (inbook.batch.count ? L"已查找完毕。":L"没有匹配结果。") : L"本批最多32项，可继续下一批。");
  winsearch_controls();
}
static LRESULT CALLBACK winsearch_procedure(HWND window,UINT message,WPARAM wparam,LPARAM lparam) {
  if(message==WM_COMMAND) {
    int id=LOWORD(wparam),code=HIWORD(wparam);
    if(id==IDC_INBOOK_QUERY && code==EN_CHANGE) {
      inbook.generation++;winsearch_cancel();winsearch_batch_free(&inbook.batch);inbook.have_cursor=0;
      SendMessageW(inbook.rows,LB_RESETCONTENT,0,0);SetWindowTextW(inbook.message,L"输入文字后查找。");
      winsearch_controls();return 0;
    }
    if(id==IDC_INBOOK_HITS && code==LBN_SELCHANGE) { winsearch_controls();return 0; }
    if(id==IDC_INBOOK_HITS && code==LBN_DBLCLK) { winsearch_submit(0,1);return 0; }
    if(id==IDC_INBOOK_FIND) { winsearch_submit(0,0);return 0; }
    if(id==IDC_INBOOK_NEXT) { winsearch_submit(1,0);return 0; }
    if(id==IDC_INBOOK_OPEN) { winsearch_submit(0,1);return 0; }
    if(id==IDC_INBOOK_CANCEL) { winsearch_cancel();return 0; }
    if(id==IDC_INBOOK_CLOSE || id==IDCANCEL) { winsearch_close();return 0; }
  }
  if(message==WM_CLOSE) { winsearch_close();return 0; }
  if(message==WM_SIZE && wparam==SIZE_MINIMIZED) { winsearch_cancel();return 0; }
  return DefWindowProcW(window,message,wparam,lparam);
}
static void winsearch_show(void) {
  if(inbook.dialog) { SetForegroundWindow(inbook.dialog);return; }
  if(g.job || g.pending || g.closing || !g.session.active) { set_status(L"打开书籍并等待当前任务完成后，可书内查找。");return; }
  WNDCLASSW type={0};type.lpfnWndProc=winsearch_procedure;type.hInstance=GetModuleHandleW(NULL);
  type.hCursor=LoadCursor(NULL,IDC_ARROW);type.hbrBackground=(HBRUSH)(COLOR_BTNFACE+1);type.lpszClassName=L"EXReaderInBookSearch";
  if(!RegisterClassW(&type) && GetLastError()!=ERROR_CLASS_ALREADY_EXISTS) return;
  inbook.dialog=CreateWindowExW(WS_EX_CONTROLPARENT,type.lpszClassName,L"书内查找",
    WS_OVERLAPPED|WS_CAPTION|WS_SYSMENU|WS_MINIMIZEBOX, CW_USEDEFAULT,CW_USEDEFAULT,680,450,
    g.window,NULL,type.hInstance,NULL);
  if(!inbook.dialog) return;
  HWND window=inbook.dialog;inbook.book_id=g.current.id;inbook.generation++;inbook.running=0;
  HWND label=make_static(window,0,L"查找文字(&Q)");MoveWindow(label,12,12,110,22,TRUE);
  inbook.query=CreateWindowExW(WS_EX_CLIENTEDGE,L"EDIT",L"",WS_CHILD|WS_VISIBLE|WS_TABSTOP|ES_AUTOHSCROLL,
    124,10,404,26,window,(HMENU)(INT_PTR)IDC_INBOOK_QUERY,NULL,NULL);
  SendMessageW(inbook.query,WM_SETFONT,(WPARAM)GetStockObject(DEFAULT_GUI_FONT),TRUE);
  SendMessageW(inbook.query,EM_SETLIMITTEXT,4096,0);
  inbook.find=make_button(window,IDC_INBOOK_FIND,L"查找(&F)");MoveWindow(inbook.find,540,10,108,26,TRUE);
  HWND results_label=make_static(window,0,L"书内查找结果(&R)");MoveWindow(results_label,12,44,636,22,TRUE);
  inbook.rows=CreateWindowExW(WS_EX_CLIENTEDGE,L"LISTBOX",L"书内查找结果",WS_CHILD|WS_VISIBLE|WS_TABSTOP|WS_VSCROLL|LBS_NOTIFY|LBS_NOINTEGRALHEIGHT,
    12,70,636,236,window,(HMENU)(INT_PTR)IDC_INBOOK_HITS,NULL,NULL);
  SendMessageW(inbook.rows,WM_SETFONT,(WPARAM)GetStockObject(DEFAULT_GUI_FONT),TRUE);
  inbook.message=make_static(window,IDC_INBOOK_MESSAGE,L"输入文字后查找。边界：逐字、区分大小写；不包含扫描页OCR。");MoveWindow(inbook.message,12,316,636,36,TRUE);
  inbook.next=make_button(window,IDC_INBOOK_NEXT,L"下一批(&N)");MoveWindow(inbook.next,12,360,120,28,TRUE);
  inbook.open=make_button(window,IDC_INBOOK_OPEN,L"定位(&O)");MoveWindow(inbook.open,144,360,120,28,TRUE);
  inbook.cancel=make_button(window,IDC_INBOOK_CANCEL,L"取消查找(&X)");MoveWindow(inbook.cancel,276,360,120,28,TRUE);
  HWND close=make_button(window,IDC_INBOOK_CLOSE,L"关闭(&C)");MoveWindow(close,528,360,120,28,TRUE);
  winsearch_controls();ShowWindow(window,SW_SHOW);SetFocus(inbook.query);
}
static int winsearch_translate(MSG *message) {
  if(message->message==WM_KEYDOWN && message->wParam=='F' && (GetKeyState(VK_CONTROL)&0x8000) &&
     !(GetKeyState(VK_SHIFT)&0x8000) && IsWindowEnabled(g.window)) { winsearch_show();return 1; }
  if(!inbook.dialog || (message->hwnd!=inbook.dialog && !IsChild(inbook.dialog,message->hwnd))) return 0;
  if(message->message==WM_KEYDOWN && message->wParam==VK_ESCAPE) {
    if(inbook.running) winsearch_cancel();else winsearch_close();return 1;
  }
  if(message->message==WM_KEYDOWN && message->wParam==VK_RETURN) {
    if(GetFocus()==inbook.query) { winsearch_submit(0,0);return 1; }
    if(GetFocus()==inbook.rows) { winsearch_submit(0,1);return 1; }
  }
  return IsDialogMessageW(inbook.dialog,message)!=0;
}
