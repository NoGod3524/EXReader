/* SPDX-License-Identifier: MIT */
/* G03/G04 are installed optional modules. The existing serial SDK worker owns
 * each operation; the native dialog keeps only bounded, independent values. */
static int winrecords_cancelled(void *context) {return job_cancel_flag(context);}
static void winrecords_phase(void *context,int phase) {
  host_job *job=context;
  if(phase==2) InterlockedExchange(&job->records_durable,1);
#ifdef EXR_HOST_WORKER_REVIEW
  review_pause(7+phase,phase==1 ? job:NULL);
#endif
}
static exr_status winrecords_resolve(host_job *job,host_session *input,const reader_rs_record *record,
    size_t *unit,exr_anchor_match *match,exr_pager **temporary) {
  exr_control control={job_cancel_check,NULL,job};reader_rs_error error={0};reader_rs_status code=READER_RS_IDENTITY;
#ifdef EXR_READER_WINDOWS_RAW3
  if(input->fixed && record->mode==READER_RS_FIXED_PAGE && record->anchor_version==3)
    code=reader_rs_resolve_fixed_v3(input->fixed_document,record,&control,unit,match,&error);
  else
#endif
  if(input->fixed && record->mode==READER_RS_FIXED_PAGE)
    code=reader_rs_resolve_fixed(input->fixed_document,record,&control,unit,match,&error);
  else if(input->bounded && record->mode==READER_RS_EPUB_CHAPTER) {
    code=reader_rs_epub_record_part(input->publication,record,unit,&error);
    if(code==READER_RS_OK) {
      exr_status status=bounded_pager(input,*unit,temporary,&job->error);if(status!=EXR_OK) return status;
      code=reader_rs_resolve_epub(input->publication,*temporary,*unit,record,&control,match,&error);
    }
  } else if(input->document && !input->bounded && record->mode==READER_RS_REFLOW_GLOBAL) {
    *unit=0;code=reader_rs_resolve_reflow(input->document,record,&control,match,&error);
  }
  if(code==READER_RS_OK && match->state==EXR_ANCHOR_FOUND) return EXR_OK;
  return job_cancel_flag(job) ? EXR_CANCELLED:EXR_ARGUMENT;
}
/* Resolve independently and in the live renderer before returning its actual
 * capture. Historical offsets, percentages and page hints never break ties. */
static exr_status winrecords_capture(void *context,const reader_rs_record *historical,
    reader_rs_capture *out,exr_anchor *anchor,exr_fixed_anchor *fixed,size_t *part) {
  host_job *job=context;exr_status status=EXR_OK;host_session fresh={0};
  exr_pager *first=NULL,*current=NULL;exr_anchor_match before={0},match={0};size_t unit=g.session.fixed?g.frame.page:g.frame.part;
  size_t start=job->note_start,end=job->note_end;exr_control control={job_cancel_check,NULL,job};
  if(job->book_id!=g.session.book_id || job->generation!=g.frame.generation) return EXR_ARGUMENT;
  if(historical) {
    size_t independent=0;status=winreader_fresh(job,&fresh);
    if(status==EXR_OK) status=winrecords_resolve(job,&fresh,historical,&independent,&before,&first);
    if(status==EXR_OK) status=winrecords_resolve(job,&g.session,historical,&unit,&match,&current);
    if(status==EXR_OK && (unit!=independent||before.start!=match.start||before.end!=match.end)) status=EXR_FORMAT;
    start=match.start;end=match.end;
  }
  if(status==EXR_OK && g.session.fixed) {
    exr_fixed_text *text=NULL;size_t count=0;const exr_fixed_page *pages=exr_fixed_pages(g.session.fixed_document,&count);
    if(!pages||unit>=count) status=EXR_ARGUMENT;
    if(status==EXR_OK) status=exr_fixed_load_text(g.session.fixed_document,unit,&control,&text,&job->error);
    if(status==EXR_OK) status=exr_fixed_anchor_create(pages[unit].id,text,start,end,fixed,&job->error);
    exr_fixed_text_free(text);out->mode=READER_RS_FIXED_PAGE;out->fixed=fixed;out->page=unit;
  } else if(status==EXR_OK && g.session.bounded) {
    size_t count=0;const exr_part *parts=exr_publication_parts(g.session.publication,&count);
    if(!parts||unit>=count) status=EXR_ARGUMENT;
    if(status==EXR_OK) status=exr_pager_anchor_create(current?current:g.session.pager,start,end,&control,anchor,&job->error);
    out->mode=READER_RS_EPUB_CHAPTER;out->anchor=anchor;out->part_path=status==EXR_OK?parts[unit].path:NULL;
  } else if(status==EXR_OK) {
    status=exr_anchor_create(g.session.document,start,end,anchor,&job->error);
    out->mode=READER_RS_REFLOW_GLOBAL;out->anchor=anchor;
  }
  *part=unit;exr_pager_free(first);exr_pager_free(current);session_clear(&fresh);
  return status;
}
static exr_status winrecords_route(host_job *job) {
  const reader_rs_record *record=&job->records.record;reader_rs_capture capture={0};
  exr_anchor anchor={0};exr_fixed_anchor fixed={0};size_t part=0;
  exr_status status=winrecords_capture(job,record,&capture,&anchor,&fixed,&part);
  if(status==EXR_OK) {
    if(g.session.fixed) {job->target_page=part;job->note_start=fixed.start;job->note_end=fixed.end;job->resolved_selection=1;}
    else {
      job->anchor=anchor;memset(&anchor,0,sizeof(anchor));job->has_anchor=1;job->anchor_host_owned=1;job->use_offset=1;
      job->target_part=part;if(g.session.bounded) {job->part_path=host_strdup(capture.part_path);if(!job->part_path) status=EXR_MEMORY;}
    }
  }
  exr_anchor_free(&anchor);exr_fixed_anchor_free(&fixed);
  if(status==EXR_OK && job_cancel_flag(job)) status=EXR_CANCELLED;
  return status==EXR_OK?job_go(job):status;
}
static exr_status winrecords_job(host_job *job) {
  if(!g.session.active || job->book_id!=g.current.id || job->generation!=g.frame.generation) return EXR_ARGUMENT;
  char source[256],sha[65],key[73];uint64_t bytes=0;exr_control control={job_cancel_check,NULL,job};
  exr_status status=winreader_identity(job->book_id,g.current.format,g.session.fixed,g.session.bounded,source,&control,&job->error);
  if(status!=EXR_OK || strcmp(source,g.session.source_key)) return status!=EXR_OK?status:EXR_FORMAT;
  EnterCriticalSection(&g.library_lock);
  status=reader_catalog_sdk_original_identity(g.library,job->book_id,&control,sha,&bytes,&job->error);
  LeaveCriticalSection(&g.library_lock);if(status!=EXR_OK) return status;
  const char *format=g.current.format==EXR_EPUB?"epub":g.current.format==EXR_PDF?"pdf":g.current.format==EXR_CBZ?"cbz":
    g.current.format==EXR_TXT?"txt":g.current.format==EXR_HTML?"html":g.current.format==EXR_FB2?"fb2":
    g.current.format==EXR_DOCX?"docx":g.current.format==EXR_RTF?"rtf":g.current.format==EXR_MOBI?"mobi":NULL;
  if(!format) return EXR_UNSUPPORTED;snprintf(key,sizeof(key),"%s:%s",format,sha);
  char *database=host_utf8(g.product_path);wchar_t pending[HOST_PATH];
  if(!database) return EXR_MEMORY;
  int n=swprintf(pending,HOST_PATH,L"%ls.reading.pending",g.product_path);
  if(n<0||n>=HOST_PATH) {free(database);return EXR_LIMIT;}
  winrecords_request request={0};request.database=database;request.pending_path=pending;request.book_key=key;
  request.sdk_book=job->book_id;request.source_bytes=bytes;request.action=job->records_action;
  request.kind=job->records_kind;request.operation=job->records_operation;request.progress_target=job->records_progress;
  request.direction=job->direction;request.annotation_id=job->records_annotation;request.head=job->records_head;
  request.sha256=job->records_sha;request.body=job->records_body;request.version=job->records_version;
  request.after=job->records_after;request.pending_revision=job->records_pending;
  request.context=job;request.cancelled=winrecords_cancelled;request.capture=winrecords_capture;request.phase=winrecords_phase;
  status=winrecords_execute(&request,&job->records);free(database);
  if(status==EXR_OK&&request.action==WINRECORDS_READ) status=winrecords_route(job);
  if(status!=EXR_OK&&!job->error.message[0]) snprintf(job->error.message,sizeof(job->error.message),"%s",job->records.message);
  return status;
}
static reader_av_item *winrecords_selected(int *progress) {
  LRESULT selected=SendMessageW(records.rows,LB_GETCURSEL,0,0);*progress=selected==0;
  if(selected<=0||(size_t)selected>records.result.page.count) return NULL;
  return &records.result.page.items[selected-1];
}
static void winrecords_controls(void) {
  int busy=records.running||g.job||g.pending||g.closing;
  EnableWindow(records.button,!busy&&g.session.active);
  if(!records.dialog) return;
  int progress=0;reader_av_item *item=records.history?NULL:winrecords_selected(&progress);
  int safe=progress?records.result.progress.kind==READER_SELECTION_SAFE:item&&item->state==READER_AV_STATE_SAFE;
  int deleted=progress?records.result.progress.graph.deleted:item&&item->deleted;
  int live=safe&&!deleted,ready=!busy&&!records.result.pending;
  int located=progress?records.result.progress_has_location:item&&item->has_location&&item->content_available&&item->exact!=NULL;
  for(int i=0;i<14;i++) EnableWindow(records.controls[i],!busy);
  EnableWindow(records.controls[0],ready&&!records.history&&(records.result.progress.kind==READER_SELECTION_MISSING||
    (records.result.progress.kind==READER_SELECTION_SAFE&&!records.result.progress.graph.deleted)));
  EnableWindow(records.controls[1],ready&&!records.history);
  EnableWindow(records.controls[2],ready&&!records.history&&g.selection.active&&g.selection.start!=g.selection.end);
  EnableWindow(records.controls[3],ready&&!records.history&&live&&located&&!progress);
  EnableWindow(records.controls[4],ready&&!records.history&&live);
  EnableWindow(records.controls[5],ready&&(records.history?records.result.version_count>0:safe&&deleted));
  EnableWindow(records.controls[6],!busy&&!records.history&&live&&located);
  EnableWindow(records.controls[7],!busy&&!records.history&&records.result.has_previous);
  EnableWindow(records.controls[8],!busy&&!records.history&&records.result.has_next);
  EnableWindow(records.controls[10],!busy&&records.result.pending&&!records.result.pending_corrupt);
  EnableWindow(records.controls[11],!busy&&records.result.pending&&!records.result.pending_corrupt);
  EnableWindow(records.controls[12],records.running&&(!g.job||!job_commit_barrier(g.job->kind)));
  EnableWindow(records.controls[13],!g.closing);
  EnableWindow(records.body,ready&&!records.history);
}
static void winrecords_close(void) {
  if(g.job&&g.job->kind==JOB_RECORDS&&!job_commit_barrier(g.job->kind)) InterlockedExchange(&g.job->cancel,1);
  records.generation++;HWND window=records.dialog;records.dialog=NULL;if(window) DestroyWindow(window);
  winrecords_response_free(&records.result);records.rows=records.body=records.message=NULL;records.history=0;
  host_restore_content_focus();
}
static void winrecords_submit(int action,int kind,int operation,const char *after,int direction) {
  if(!records.dialog||records.running||g.job||g.pending||g.closing||records.book_id!=g.current.id) return;
  host_job *job=job_new(JOB_RECORDS);if(!job) return;
  job->book_id=records.book_id;job->generation=g.frame.generation;job->records_generation=records.generation;
  job->records_action=action;job->records_kind=kind;job->records_operation=operation;job->direction=direction;
  job->note_start=job->note_end=g.frame.range_start;
  if(g.session.fixed) job->note_start=job->note_end=0;
  if(kind==READER_RC_HIGHLIGHT) selection_bounds(&job->note_start,&job->note_end);
  int progress=0;reader_av_item *item=winrecords_selected(&progress);
  int selected=action==WINRECORDS_READ||action==WINRECORDS_HISTORY||kind==READER_RC_NOTE_TEXT||operation!=READER_RC_PUT;
  if(selected) {
    job->records_progress=progress;
    const char *id=item?item->annotation_id:"",*head=progress?records.result.progress_info.revision_id:item?item->revision_id:"";
    const char *sha=progress?records.result.progress_info.sha256:item?item->sha256:"";
    if(records.history) {id=records.history_annotation;head=records.history_head;sha=records.history_sha;job->records_progress=records.history_progress;}
    snprintf(job->records_annotation,33,"%s",id);snprintf(job->records_head,33,"%s",head);snprintf(job->records_sha,65,"%s",sha);
    if(action==WINRECORDS_SAVE&&operation!=READER_RC_PUT) job->records_kind=job->records_progress?READER_RC_PROGRESS:READER_RC_BOOKMARK;
  } else if(kind==READER_RC_PROGRESS&&records.result.progress.kind==READER_SELECTION_SAFE) {
    snprintf(job->records_head,33,"%s",records.result.progress_info.revision_id);snprintf(job->records_sha,65,"%s",records.result.progress_info.sha256);
  }
  if(records.history&&operation==READER_RC_RESTORE) {
    LRESULT index=SendMessageW(records.rows,LB_GETCURSEL,0,0);
    if(index==LB_ERR||(size_t)index>=records.result.version_count) {job_release(job);return;}
    snprintf(job->records_version,33,"%s",records.result.versions[index]);
  }
  if(action==WINRECORDS_HISTORY) {
    records.history_progress=progress;snprintf(records.history_annotation,33,"%s",job->records_annotation);
    snprintf(records.history_head,33,"%s",job->records_head);snprintf(records.history_sha,65,"%s",job->records_sha);
  }
  if(after) snprintf(job->records_after,33,"%s",after);
  snprintf(job->records_pending,33,"%s",records.result.pending_revision);
  if(action==WINRECORDS_SAVE&&operation==READER_RC_PUT&&kind!=READER_RC_PROGRESS) {
    int size=GetWindowTextLengthW(records.body);wchar_t *body=calloc((size_t)size+1,sizeof(*body));
    if(body) {GetWindowTextW(records.body,body,size+1);job->records_body=host_utf8(body);free(body);}
    if(!job->records_body) {job_release(job);return;}
  }
  records.running=1;SetWindowTextW(records.message,L"正在核对原书和阅读记录，可在保存前取消…");
  job_submit(job);if(!g.job) records.running=0;winrecords_controls();
}
static const wchar_t *winrecords_state(int state) {
  return state==READER_SELECTION_SAFE?L"已保存":state==READER_SELECTION_CONCURRENT?L"存在冲突":
    state==READER_SELECTION_PENDING_PARENTS?L"等待历史":state==READER_SELECTION_BLOCKED_RESTORE?L"恢复受阻":L"尚未保存";
}
static void winrecords_fill(void) {
  SendMessageW(records.rows,LB_RESETCONTENT,0,0);wchar_t line[512];
  if(records.history) {
    for(size_t i=0;i<records.result.version_count;i++) {wchar_t *label=host_wide(records.result.version_labels[i],strlen(records.result.version_labels[i]));
      swprintf(line,512,L"版本 %llu · %ls",(unsigned long long)i+1,label?label:L"");free(label);SendMessageW(records.rows,LB_ADDSTRING,0,(LPARAM)line);}
    SetWindowTextW(records.message,records.result.history_complete?L"选择保留版本，然后明确恢复。":L"最多显示32个版本；仍有历史未列出。选择后明确恢复。");
  } else {
    swprintf(line,512,L"阅读位置 · %ls%ls",winrecords_state(records.result.progress.kind),records.result.progress.graph.deleted?L" · 已删除":L"");
    SendMessageW(records.rows,LB_ADDSTRING,0,(LPARAM)line);
    for(size_t i=0;i<records.result.page.count;i++) {
      reader_av_item *item=&records.result.page.items[i];wchar_t *label=NULL;
      if(item->content_available) {const char *body=item->note_text&&item->note_text[0]?item->note_text:item->exact;
        size_t n=body?strlen(body):0;if(n>280){n=280;while(n&&((unsigned char)body[n]&192)==128)n--;}
        label=host_wide(body?body:"",n);}
      const wchar_t *kind=item->deleted?L"已删除":item->kind==READER_AV_KIND_BOOKMARK?L"书签":item->kind==READER_AV_KIND_NOTE?L"笔记":L"划线";
      if(item->state==READER_AV_STATE_SAFE) swprintf(line,512,L"%ls · %ls",kind,label?label:L"");
      else swprintf(line,512,L"%ls · 历史%llu / 分支%llu / 缺失%llu / 外来%llu",winrecords_state(
        item->state==READER_AV_STATE_CONCURRENT?READER_SELECTION_CONCURRENT:item->state==READER_AV_STATE_PENDING_PARENTS?
        READER_SELECTION_PENDING_PARENTS:item->state==READER_AV_STATE_BLOCKED_RESTORE?READER_SELECTION_BLOCKED_RESTORE:READER_SELECTION_MISSING),
        (unsigned long long)item->revisions,(unsigned long long)item->heads,(unsigned long long)item->missing_parents,(unsigned long long)item->foreign_parents);
      free(label);SendMessageW(records.rows,LB_ADDSTRING,0,(LPARAM)line);
    }
    SetWindowTextW(records.message,records.result.pending?records.result.pending_corrupt?L"原保存请求无法验证，已保留文件。":L"上一保存未确认。请重试原请求，或明确放弃请求。":
      records.result.page.complete?L"本方向已读完。保存的记录可跨设备同步。":L"本批最多32条，仍有记录可继续读取。");
  }
  if(SendMessageW(records.rows,LB_GETCOUNT,0,0)>0) SendMessageW(records.rows,LB_SETCURSEL,0,0);
  winrecords_controls();
}
static void winrecords_accept(host_job *job) {
  records.running=0;
  if(!records.dialog||job->records_generation!=records.generation||job->book_id!=records.book_id||g.closing||g.pending) {winrecords_controls();return;}
  if(job->status!=EXR_OK) {
    records.result.pending=job->records.pending;records.result.pending_corrupt=job->records.pending_corrupt;
    snprintf(records.result.pending_revision,33,"%s",job->records.pending_revision);
    wchar_t message[512];describe_error(message,512,job->status==EXR_CANCELLED?L"已取消，阅读记录保留":L"操作未确认，请刷新或重试原请求",job->status,&job->error);
    SetWindowTextW(records.message,message);winrecords_controls();return;
  }
  if(job->records_action==WINRECORDS_READ) {
    if(job->have_frame) {job->kind=JOB_GO;handle_job_complete(job);SetWindowTextW(records.message,L"已在独立原书与当前绘图文档中找到并定位。");}
    winrecords_controls();return;
  }
  if(job->records_action==WINRECORDS_LIST||job->records_action==WINRECORDS_HISTORY) {
    records.history=job->records_action==WINRECORDS_HISTORY;
    winrecords_response_free(&records.result);records.result=job->records;memset(&job->records,0,sizeof(job->records));winrecords_fill();return;
  }
  records.history=0;SetWindowTextW(records.body,L"");winrecords_submit(WINRECORDS_LIST,0,0,NULL,1);
}
static LRESULT CALLBACK winrecords_procedure(HWND window,UINT message,WPARAM wparam,LPARAM lparam) {
  if(message==WM_CLOSE) {winrecords_close();return 0;}
  if(message==WM_COMMAND) {
    int id=LOWORD(wparam),notification=HIWORD(wparam);
    if(id==IDC_RECORDS_CLOSE||id==IDCANCEL) {winrecords_close();return 0;}
    if(id==IDC_RECORDS_CANCEL) {job_cancel_button();return 0;}
    if(id==IDC_RECORDS_ROWS&&notification==LBN_SELCHANGE) {
      if(!records.history) {int progress=0;reader_av_item *item=winrecords_selected(&progress);wchar_t *body=item&&item->content_available?
        host_wide(item->note_text,item->note_size):NULL;SetWindowTextW(records.body,body?body:L"");free(body);}
      winrecords_controls();return 0;
    }
    if(records.running||g.job||g.pending) return 0;
    if(id==IDC_RECORDS_PROGRESS) winrecords_submit(WINRECORDS_SAVE,READER_RC_PROGRESS,READER_RC_PUT,NULL,1);
    if(id==IDC_RECORDS_BOOKMARK) winrecords_submit(WINRECORDS_SAVE,READER_RC_BOOKMARK,READER_RC_PUT,NULL,1);
    if(id==IDC_RECORDS_HIGHLIGHT) winrecords_submit(WINRECORDS_SAVE,READER_RC_HIGHLIGHT,READER_RC_PUT,NULL,1);
    if(id==IDC_RECORDS_EDIT) winrecords_submit(WINRECORDS_SAVE,READER_RC_NOTE_TEXT,READER_RC_PUT,NULL,1);
    if(id==IDC_RECORDS_OPEN||(id==IDC_RECORDS_ROWS&&notification==LBN_DBLCLK&&!records.history)) winrecords_submit(WINRECORDS_READ,0,0,NULL,1);
    if(id==IDC_RECORDS_REFRESH) {records.history=0;winrecords_submit(WINRECORDS_LIST,0,0,NULL,1);}
    if(id==IDC_RECORDS_PREVIOUS) winrecords_submit(WINRECORDS_LIST,0,0,records.result.page.reverse.after_id,-1);
    if(id==IDC_RECORDS_NEXT) winrecords_submit(WINRECORDS_LIST,0,0,records.result.page.next.after_id,1);
    if(id==IDC_RECORDS_RETRY) winrecords_submit(WINRECORDS_RETRY,0,0,NULL,1);
    if(id==IDC_RECORDS_DELETE&&MessageBoxW(window,L"删除这条阅读记录？保留历史，之后可明确恢复。",L"删除阅读记录",MB_OKCANCEL|MB_ICONQUESTION)==IDOK)
      winrecords_submit(WINRECORDS_SAVE,0,READER_RC_DELETE,NULL,1);
    if(id==IDC_RECORDS_DISCARD&&MessageBoxW(window,L"放弃这个待确认请求？已经提交的记录仍会保留。",L"放弃原请求",MB_OKCANCEL|MB_ICONQUESTION)==IDOK)
      winrecords_submit(WINRECORDS_DISCARD,0,0,NULL,1);
    if(id==IDC_RECORDS_RESTORE) {
      if(!records.history) winrecords_submit(WINRECORDS_HISTORY,0,0,NULL,1);
      else if(MessageBoxW(window,L"用选中版本的原文位置和内容恢复这条记录？",L"明确恢复",MB_OKCANCEL|MB_ICONQUESTION)==IDOK)
        winrecords_submit(WINRECORDS_SAVE,0,READER_RC_RESTORE,NULL,1);
    }
    return 0;
  }
  return DefWindowProcW(window,message,wparam,lparam);
}
static void winrecords_show(void) {
  if(g.session.txt) { set_status(L"TXT 目前仅支持第一页；此功能尚未实现。");return; }
  if(records.dialog) {SetForegroundWindow(records.dialog);return;}
  if(g.job||g.pending||g.closing||!g.session.active) return;
  WNDCLASSW type={0};type.lpfnWndProc=winrecords_procedure;type.hInstance=GetModuleHandleW(NULL);type.hCursor=LoadCursor(NULL,IDC_ARROW);
  type.hbrBackground=(HBRUSH)(COLOR_BTNFACE+1);type.lpszClassName=L"EXReaderReadingRecords";
  if(!RegisterClassW(&type)&&GetLastError()!=ERROR_CLASS_ALREADY_EXISTS) return;
  records.dialog=CreateWindowExW(WS_EX_CONTROLPARENT,type.lpszClassName,L"阅读记录",WS_OVERLAPPED|WS_CAPTION|WS_SYSMENU|WS_MINIMIZEBOX,
    CW_USEDEFAULT,CW_USEDEFAULT,820,650,g.window,NULL,type.hInstance,NULL);if(!records.dialog) return;
  HWND window=records.dialog;records.book_id=g.current.id;records.generation++;records.running=records.history=0;
  HWND label=make_static(window,0,L"阅读记录：书签、划线、笔记和位置(&R)");MoveWindow(label,12,12,780,22,TRUE);
  records.rows=CreateWindowExW(WS_EX_CLIENTEDGE,L"LISTBOX",L"阅读记录",WS_CHILD|WS_VISIBLE|WS_TABSTOP|WS_VSCROLL|LBS_NOTIFY|LBS_NOINTEGRALHEIGHT,
    12,38,780,270,window,(HMENU)(INT_PTR)IDC_RECORDS_ROWS,NULL,NULL);
  SendMessageW(records.rows,WM_SETFONT,(WPARAM)GetStockObject(DEFAULT_GUI_FONT),TRUE);
  label=make_static(window,0,L"书签名称或笔记内容(&T)");MoveWindow(label,12,315,780,20,TRUE);
  records.body=CreateWindowExW(WS_EX_CLIENTEDGE,L"EDIT",L"",WS_CHILD|WS_VISIBLE|WS_TABSTOP|WS_VSCROLL|ES_MULTILINE|ES_AUTOVSCROLL,
    12,337,780,82,window,(HMENU)(INT_PTR)IDC_RECORDS_BODY,NULL,NULL);
  SendMessageW(records.body,WM_SETFONT,(WPARAM)GetStockObject(DEFAULT_GUI_FONT),TRUE);SendMessageW(records.body,EM_SETLIMITTEXT,65536,0);
  records.message=make_static(window,IDC_RECORDS_MESSAGE,L"正在读取…");MoveWindow(records.message,12,425,780,46,TRUE);
  const wchar_t *labels[]={L"保存位置(&P)",L"加书签(&B)",L"划线笔记(&H)",L"改笔记(&E)",L"删除(&D)",L"恢复(&V)",L"定位(&O)",
    L"上一批",L"下一批",L"刷新(&F)",L"重试原请求",L"放弃原请求",L"取消(&X)",L"关闭(&C)"};
  for(int i=0;i<14;i++) {records.controls[i]=make_button(window,IDC_RECORDS_PROGRESS+i,labels[i]);MoveWindow(records.controls[i],12+(i%7)*112,480+(i/7)*40,106,32,TRUE);}
  ShowWindow(window,SW_SHOW);SetFocus(records.rows);winrecords_submit(WINRECORDS_LIST,0,0,NULL,1);
}
static int winrecords_translate(MSG *message) {
  if(message->message==WM_KEYDOWN&&message->wParam=='L'&&(GetKeyState(VK_CONTROL)&0x8000)&&IsWindowEnabled(g.window)) {winrecords_show();return 1;}
  if(!records.dialog||(message->hwnd!=records.dialog&&!IsChild(records.dialog,message->hwnd))) return 0;
  if(message->message==WM_KEYDOWN&&message->wParam==VK_ESCAPE) {if(records.running) job_cancel_button();else winrecords_close();return 1;}
  if(message->message==WM_KEYDOWN&&message->wParam==VK_RETURN&&GetFocus()==records.rows&&!records.history) {
    SendMessageW(records.dialog,WM_COMMAND,IDC_RECORDS_OPEN,0);return 1;
  }
  return IsDialogMessageW(records.dialog,message)!=0;
}
