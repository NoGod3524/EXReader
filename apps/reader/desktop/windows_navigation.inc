/* SPDX-License-Identifier: MIT
 * F2 snapshots live for one serialized job, on the OS thread that created them.
 * The native dialog retains only 32 owned rows and bounded pure-value selectors.
 */
static void winnav_result_free(host_navigation_result *result) {
  reader_navigation_page_free(&result->page);free(result->candidates);memset(result,0,sizeof(*result));
}
static exr_status winnav_status(reader_navigation_status code,const reader_navigation_error *error) {
  if(code==READER_NAVIGATION_OK) return EXR_OK;
  if(code==READER_NAVIGATION_CANCELLED) return EXR_CANCELLED;
  if(code==READER_NAVIGATION_MEMORY) return EXR_MEMORY;
  if(code==READER_NAVIGATION_LIMIT) return EXR_LIMIT;
  if(code==READER_NAVIGATION_SDK && error->sdk_code) return (exr_status)error->sdk_code;
  return EXR_ARGUMENT;
}
static int winnav_cancelled(void *context) {
#ifdef EXR_HOST_WORKER_REVIEW
  review_pause(6,(host_job *)context);
#endif
  return job_cancel_check(context);
}
static reader_navigation_status winnav_resolve(reader_navigation *snapshot,host_session *input,
    host_job *job,const char *cfi,reader_navigation_target *target,reader_navigation_error *error) {
  reader_navigation_resolve_options options={0};options.struct_size=sizeof(options);
  options.source_key=g.session.source_key;options.explicit_part=job->navigation_explicit_part;
  options.control=(exr_control){winnav_cancelled,NULL,job};
  if(cfi) return input->bounded ? reader_navigation_resolve_cfi(snapshot,input->publication,cfi,&options,target,error):READER_NAVIGATION_CORRUPT;
  if(input->fixed) return reader_navigation_resolve_page(snapshot,job->navigation_row,input->fixed_document,&options,target,error);
  if(input->bounded) return reader_navigation_resolve_publication(snapshot,job->navigation_row,input->publication,&options,target,error);
  return reader_navigation_resolve_document(snapshot,job->navigation_row,input->document,&options,target,error);
}
/* Compare F2's target with raw public SDK calls on a second independent input.
 * No offset, duplicate spine or missing fragment is guessed by the UI. */
static exr_status winnav_verify(host_session *input,host_job *job,const char *cfi,
    const reader_navigation_target *target,reader_navigation_status code,
    exr_document **loaded,exr_error *error) {
  size_t count=0,chapter=0,node=SIZE_MAX,resource=SIZE_MAX;
  const exr_document *document=input->document;
  exr_control control={winnav_cancelled,NULL,job};
  if(input->fixed) {
    const exr_fixed_page *pages=exr_fixed_pages(input->fixed_document,&count);
    return pages && target->kind==READER_NAVIGATION_RESULT_PAGE && target->row==job->navigation_row &&
      target->part==job->navigation_row && target->part<count && target->part_id &&
      !strcmp(target->part_id,pages[target->part].id) ? EXR_OK:EXR_FORMAT;
  }
  if(input->bounded) {
    const exr_part *parts=exr_publication_parts(input->publication,&count);
    if(target->part>=count || !target->part_path || !target->part_id ||
       strcmp(target->part_path,parts[target->part].path ? parts[target->part].path:"") ||
       strcmp(target->part_id,parts[target->part].id ? parts[target->part].id:"")) return EXR_FORMAT;
    if(cfi) {
      exr_cfi_point point={SIZE_MAX,SIZE_MAX,0};size_t part=SIZE_MAX;
      if(target->kind!=READER_NAVIGATION_RESULT_CFI || !target->cfi || strcmp(cfi,target->cfi)) return EXR_FORMAT;
      exr_status status=exr_publication_cfi_resolve(input->publication,cfi,&control,&part,loaded,&point,error);
      if(status!=EXR_OK) return status;
      return part==target->part && point.node==target->cfi_node && point.offset==target->cfi_offset &&
        point.side==target->cfi_side ? EXR_OK:EXR_FORMAT;
    }
    if(target->kind!=READER_NAVIGATION_RESULT_SPINE || target->row!=job->navigation_row) return EXR_FORMAT;
    exr_status status=exr_publication_load(input->publication,(size_t)target->part,loaded,error);
    if(status!=EXR_OK) return status;
    document=*loaded;
  } else {
    const exr_chapter *chapters=exr_document_chapters(document,&count);
    if(target->kind!=READER_NAVIGATION_RESULT_CHAPTER || target->row!=job->navigation_row ||
       target->part>=count || !target->part_path || !target->part_id ||
       strcmp(target->part_path,chapters[target->part].path ? chapters[target->part].path:"") ||
       strcmp(target->part_id,chapters[target->part].id ? chapters[target->part].id:"")) return EXR_FORMAT;
    chapter=(size_t)target->part;
  }
  if(target->fragment && target->fragment[0]) {
    size_t length=strlen(target->fragment);char *uri=malloc(length+2);if(!uri) return EXR_MEMORY;
    uri[0]='#';memcpy(uri+1,target->fragment,length+1);
    exr_status status=exr_document_resolve(document,chapter,uri,&resource,&node,error);free(uri);
    if(status!=EXR_OK) return status;
    if(node!=target->node || ((code==READER_NAVIGATION_PART_ONLY)!=(node==SIZE_MAX))) return EXR_FORMAT;
  } else if(target->node!=READER_NAVIGATION_NONE) return EXR_FORMAT;
  return EXR_OK;
}
/* Reject UTF-16 half-surrogates or a DOM range whose normalized text differs. */
static int winnav_cfi_offset(const exr_document *document,const reader_navigation_target *target,size_t *offset) {
  size_t count,size;const exr_node *nodes=exr_document_nodes(document,&count);
  const char *text=exr_document_text(document,&size);
  if(target->cfi_node>=count) return 0;
  const exr_node *node=&nodes[target->cfi_node];
  if(node->start>node->end || node->end>size) return 0;
  if(node->kind!=EXR_NODE_TEXT) {
    if(target->cfi_offset==READER_NAVIGATION_NONE) { *offset=node->start;return 1; }
    size_t child=node->first_child;
    for(uint64_t i=0;i<target->cfi_offset;i++) { if(child==SIZE_MAX || child>=count) return 0;child=nodes[child].next_sibling; }
    if(child==SIZE_MAX) { *offset=node->end;return 1; }
    if(child>=count) return 0;
    *offset=nodes[child].start;return *offset<=size;
  }
  if(!node->text || target->cfi_offset==READER_NAVIGATION_NONE) return 0;
  size_t raw=strlen(node->text),at=0;uint64_t units=0;
  if(raw!=node->end-node->start || memcmp(text+node->start,node->text,raw)) return 0;
  while(at<raw && units<target->cfi_offset) {
    unsigned char scalar=(unsigned char)node->text[at];size_t bytes=scalar<128 ? 1:scalar<224 ? 2:scalar<240 ? 3:4;
    unsigned added=bytes==4 ? 2:1;
    if(at+bytes>raw || units+added>target->cfi_offset) return 0;
    at+=bytes;units+=added;
  }
  if(units!=target->cfi_offset) return 0;
  *offset=node->start+at;return 1;
}
typedef struct { const char *text;size_t size,at; } winnav_projection;
static exr_status winnav_projection_chunk(void *opaque,const char *text,size_t size,exr_error *error) {
  winnav_projection *proof=opaque;(void)error;
  if(proof->at>proof->size || size>proof->size-proof->at || memcmp(proof->text+proof->at,text,size)) return EXR_FORMAT;
  proof->at+=size;return EXR_OK;
}
static exr_status winnav_open(reader_navigation *snapshot,host_job *job) {
  host_session first={0},second={0};reader_navigation_target target={0};reader_navigation_error error={0};
  reader_navigation_page row={0};reader_navigation_status code=READER_NAVIGATION_ARGUMENT;
  exr_status status=EXR_ARGUMENT;exr_document *loaded=NULL;exr_pager *pager=NULL;
  exr_anchor point={0};exr_anchor_match match={0};const char *cfi=NULL;size_t offset=SIZE_MAX;
  exr_control control={winnav_cancelled,NULL,job};
  code=reader_navigation_rows(snapshot,job->navigation_row,1,&row,&error);
  if(code!=READER_NAVIGATION_OK || row.count!=1) goto done;
  const char *fragment=strchr(row.rows[0].href,'#');
  if(fragment && !strncmp(fragment+1,"epubcfi(",8)) cfi=fragment+1;
  else if(!strncmp(row.rows[0].href,"epubcfi(",8)) cfi=row.rows[0].href;
  status=winreader_fresh(job,&first);if(status!=EXR_OK) goto done;
  code=winnav_resolve(snapshot,&first,job,cfi,&target,&error);
  if(code==READER_NAVIGATION_AMBIGUOUS) {
    job->navigation.candidates=target.candidates;job->navigation.candidate_count=target.candidate_count;
    target.candidates=NULL;target.candidate_count=0;goto done;
  }
  if(code!=READER_NAVIGATION_OK && code!=READER_NAVIGATION_PART_ONLY) goto done;
  if(code==READER_NAVIGATION_PART_ONLY && !job->navigation_accept_part) goto done;
  status=winreader_fresh(job,&second);if(status!=EXR_OK) goto done;
  status=winnav_verify(&second,job,cfi,&target,code,&loaded,&job->error);if(status!=EXR_OK) goto done;
  if(second.fixed) {
    size_t count=0;const exr_fixed_page *pages=exr_fixed_pages(g.session.fixed_document,&count);
    if(!pages || target.part>=count || !target.part_id || strcmp(target.part_id,pages[target.part].id)) { status=EXR_FORMAT;goto done; }
    job->target_page=(size_t)target.part;
  } else {
    const exr_document *document=second.bounded ? loaded:second.document;
    size_t count=0,size=0;const exr_node *nodes=exr_document_nodes(document,&count);
    const char *text=exr_document_text(document,&size);
    if(target.kind==READER_NAVIGATION_RESULT_CFI) {
      if(!winnav_cfi_offset(document,&target,&offset)) { status=EXR_FORMAT;goto done; }
    } else if(target.node!=READER_NAVIGATION_NONE) {
      if(target.node>=count) { status=EXR_FORMAT;goto done; }offset=nodes[target.node].start;
    } else if(second.bounded) offset=0;
    else {
      size_t chapters_count;const exr_chapter *chapters=exr_document_chapters(document,&chapters_count);
      if(target.part>=chapters_count || chapters[target.part].root>=count) { status=EXR_FORMAT;goto done; }
      offset=nodes[chapters[target.part].root].start;
    }
    if(offset>size || (offset<size && ((unsigned char)text[offset]&192)==128)) { status=EXR_FORMAT;goto done; }
    status=exr_anchor_create(document,offset,offset,&point,&job->error);if(status!=EXR_OK) goto done;
    if(second.bounded) {
      size_t parts_count;const exr_part *parts=exr_publication_parts(g.session.publication,&parts_count);
      if(target.part>=parts_count || !target.part_path || strcmp(target.part_path,parts[target.part].path)) { status=EXR_FORMAT;goto done; }
      status=bounded_pager(&g.session,(size_t)target.part,&pager,&job->error);if(status!=EXR_OK) goto done;
      winnav_projection proof={text,size,0};
      if(exr_pager_chapter_statistics(pager).projection_bytes!=size) { status=EXR_FORMAT;goto done; }
      status=exr_pager_read_text(pager,0,size,winnav_projection_chunk,&proof,&control,&job->error);
      if(status!=EXR_OK) goto done;
      if(proof.at!=size) { status=EXR_FORMAT;goto done; }
      status=exr_pager_anchor_resolve(pager,&point,&control,&match,&job->error);
      if(status==EXR_OK) {
        job->target_part=(size_t)target.part;job->part_path=host_strdup(target.part_path);
        if(!job->part_path) status=EXR_MEMORY;
      }
    } else status=exr_anchor_resolve_ex(g.session.document,&point,&control,&match,&job->error);
    if(status!=EXR_OK) goto done;
    if(match.state!=EXR_ANCHOR_FOUND || match.start!=offset) { status=EXR_FORMAT;goto done; }
    job->anchor=point;memset(&point,0,sizeof(point));job->has_anchor=job->anchor_host_owned=1;job->use_offset=1;
  }
  if(job_cancel_flag(job)) { status=EXR_CANCELLED;goto done; }
  status=job_go(job);
  if(status==EXR_OK) code=READER_NAVIGATION_OK;
done:
  if(status==EXR_CANCELLED) code=READER_NAVIGATION_CANCELLED;
  else if(status!=EXR_OK && (code==READER_NAVIGATION_OK || (code==READER_NAVIGATION_PART_ONLY && job->navigation_accept_part))) {
    code=READER_NAVIGATION_SDK;error.sdk_code=status;
  }
  job->navigation.code=code;
  exr_anchor_free(&point);exr_pager_free(pager);exr_document_free(loaded);
  session_clear(&first);session_clear(&second);reader_navigation_page_free(&row);reader_navigation_target_free(&target);
  return code==READER_NAVIGATION_OK ? status:winnav_status(code,&error);
}
static exr_status winnav_job(host_job *job) {
  reader_navigation *snapshot=NULL;reader_navigation_error error={0};reader_navigation_status code;
  exr_control control={winnav_cancelled,NULL,job};char key[256];
  if(!g.session.active || job->book_id!=g.session.book_id || job->book_id!=g.current.id) return EXR_CANCELLED;
  exr_control identity_control={job_cancel_check,NULL,job};
  exr_status status=winreader_identity(job->book_id,g.current.format,g.session.fixed,g.session.bounded,key,&identity_control,&job->error);
  if(status!=EXR_OK) return status;
  if(strcmp(key,g.session.source_key)) { job->navigation.code=READER_NAVIGATION_MISMATCH;return EXR_ARGUMENT; }
  reader_navigation_options options={0};options.struct_size=sizeof(options);options.source_key=key;options.control=control;
  if(g.session.fixed) code=reader_navigation_open_pages(g.session.fixed_document,&options,&snapshot,&error);
  else if(g.session.bounded) code=reader_navigation_open_publication(g.session.publication,&options,&snapshot,&error);
  else code=reader_navigation_open_document(g.session.document,&options,&snapshot,&error);
  if(code==READER_NAVIGATION_OK && job->kind==JOB_NAVIGATION_OPEN) status=winnav_open(snapshot,job);
  else {
    if(code==READER_NAVIGATION_OK) code=reader_navigation_info_get(snapshot,&job->navigation.info,&error);
    if(code==READER_NAVIGATION_OK) code=reader_navigation_children(snapshot,job->navigation_parent,job->navigation_first,
      HOST_NAV_BATCH,&job->navigation.page,&error);
    if(code==READER_NAVIGATION_OK && job_cancel_flag(job)) code=READER_NAVIGATION_CANCELLED;
    job->navigation.parent=job->navigation_parent;job->navigation.first=job->navigation_first;
    job->navigation.code=code;status=winnav_status(code,&error);
  }
  reader_navigation_close(&snapshot,NULL);
#ifdef EXR_HOST_WORKER_REVIEW
  if(status==EXR_OK) review_pause(7,job);
#endif
  return status;
}
static void winnav_cancel(void) {
  if(g.job && (g.job->kind==JOB_NAVIGATION_ROWS || g.job->kind==JOB_NAVIGATION_OPEN)) InterlockedExchange(&g.job->cancel,1);
}
static void winnav_controls(void) {
  int busy=directory.running || g.job || g.pending || g.closing;
  EnableWindow(directory.button,!busy && g.session.active);
  if(!directory.dialog) return;
  HWND focused=GetFocus();LRESULT selected=SendMessageW(directory.rows,LB_GETCURSEL,0,0);
  int candidate=directory.result.candidate_count!=0;
  int chosen=selected!=LB_ERR && (size_t)selected<(candidate ? directory.result.candidate_count-directory.candidate_first:directory.result.page.count);
  EnableWindow(directory.open,!busy && chosen);
  EnableWindow(directory.children,!busy && !candidate && chosen && directory.result.page.rows[selected].child_count && directory.depth<READER_NAVIGATION_DEPTH_MAX);
  EnableWindow(directory.up,!busy && (candidate || directory.depth));
  EnableWindow(directory.previous,!busy && (candidate ? directory.candidate_first>0:directory.result.first>0));
  EnableWindow(directory.next,!busy && (candidate ? directory.candidate_first+HOST_NAV_BATCH<directory.result.candidate_count:
    directory.result.page.next!=READER_NAVIGATION_NONE));
  EnableWindow(directory.cancel,directory.running);
  if(focused && IsChild(directory.dialog,focused) && !IsWindowEnabled(focused) && GetActiveWindow()==directory.dialog) SetFocus(directory.rows);
}
static void winnav_close(void) {
  directory.generation++;winnav_cancel();HWND window=directory.dialog;directory.dialog=NULL;
  if(window) DestroyWindow(window);
  winnav_result_free(&directory.result);directory.depth=directory.candidate_first=0;directory.book_id=0;
  directory.rows=directory.open=directory.children=directory.up=directory.previous=directory.next=directory.cancel=directory.message=NULL;
  if(!g.closing && g.page) SetFocus(g.page);
}
static void winnav_submit(int open,uint64_t parent,uint64_t first,uint64_t explicit_part,size_t depth) {
  if(!directory.dialog || directory.running || g.job || g.pending || g.closing || !g.session.active || directory.book_id!=g.current.id) return;
  host_job *job=job_new(open ? JOB_NAVIGATION_OPEN:JOB_NAVIGATION_ROWS);if(!job) return;
  job->book_id=directory.book_id;job->navigation_generation=directory.generation;
  job->navigation_parent=parent;job->navigation_first=first;job->navigation_explicit_part=explicit_part;
  job->navigation_depth=depth;
  if(open) {
    if(directory.result.candidate_count) job->navigation_row=directory.pending_row;
    else {
      LRESULT selected=SendMessageW(directory.rows,LB_GETCURSEL,0,0);
      if(selected==LB_ERR || (size_t)selected>=directory.result.page.count) { job_release(job);return; }
      job->navigation_row=directory.result.page.rows[selected].index;
    }
    job->navigation_accept_part=directory.accept_part;
  }
  directory.running=1;SetWindowTextW(directory.message,open ? L"正在独立核对目录目标…":L"正在读取目录，可取消…");
  job_submit(job);winnav_controls();
}
static void winnav_candidates(void) {
  SendMessageW(directory.rows,LB_RESETCONTENT,0,0);
  size_t last=directory.candidate_first+HOST_NAV_BATCH;if(last>directory.result.candidate_count) last=directory.result.candidate_count;
  for(size_t i=directory.candidate_first;i<last;i++) {
    wchar_t line[96];swprintf(line,96,L"书内顺序 %llu",(unsigned long long)(directory.result.candidates[i]+1));
    SendMessageW(directory.rows,LB_ADDSTRING,0,(LPARAM)line);
  }
  if(last>directory.candidate_first) SendMessageW(directory.rows,LB_SETCURSEL,0,0);
  SetWindowTextW(directory.message,L"相同路径在书中出现多次，请选择书内顺序。不会自动选择第一项。");winnav_controls();
}
static void winnav_accept(host_job *job) {
  directory.running=0;
  if(!directory.dialog || directory.generation!=job->navigation_generation || g.closing || g.pending ||
     job->book_id!=directory.book_id || job->book_id!=g.current.id) { winnav_controls();return; }
  if(job_cancel_flag(job) || job->status==EXR_CANCELLED) { SetWindowTextW(directory.message,L"已取消，原阅读位置和目录保留。");winnav_controls();return; }
  if(job->kind==JOB_NAVIGATION_OPEN) {
    if(job->status==EXR_OK && job->have_frame) {
      job->kind=JOB_GO;handle_job_complete(job);SetWindowTextW(directory.message,L"已独立核对原书并定位。");
    } else if(job->navigation.code==READER_NAVIGATION_AMBIGUOUS && job->navigation.candidate_count) {
      directory.pending_row=job->navigation_row;free(directory.result.candidates);
      directory.result.candidates=job->navigation.candidates;directory.result.candidate_count=job->navigation.candidate_count;
      job->navigation.candidates=NULL;job->navigation.candidate_count=0;directory.candidate_first=0;winnav_candidates();
    } else if(job->navigation.code==READER_NAVIGATION_PART_ONLY) {
      directory.accept_part=1;SetWindowTextW(directory.open,L"打开章节起点(&O)");
      SetWindowTextW(directory.message,L"目录片段已不存在。可明确选择打开章节起点，当前阅读位置保留。");
    } else SetWindowTextW(directory.message,job->navigation.code==READER_NAVIGATION_NEEDS_HOST ?
      L"这是外部链接，未打开。":L"无法证明目录目标，未跳转。请重新打开原书后重试。");
    winnav_controls();return;
  }
  if(job->status!=EXR_OK) { SetWindowTextW(directory.message,L"无法读取目录，保留上一批和阅读位置。");winnav_controls();return; }
  winnav_result_free(&directory.result);directory.result=job->navigation;memset(&job->navigation,0,sizeof(job->navigation));
  directory.depth=job->navigation_depth;
  directory.accept_part=0;directory.candidate_first=0;SetWindowTextW(directory.open,L"定位(&O)");
  SendMessageW(directory.rows,LB_RESETCONTENT,0,0);
  for(size_t i=0;i<directory.result.page.count;i++) {
    reader_navigation_row *row=&directory.result.page.rows[i];wchar_t *label=host_wide(row->label,strlen(row->label));
    if(!label) label=host_wide("",0);
    if(!label) { winnav_close();set_status(L"目录显示内存不足，阅读位置保留。");return; }
    LRESULT added=SendMessageW(directory.rows,LB_ADDSTRING,0,(LPARAM)label);free(label);
    if(added==LB_ERR || added==LB_ERRSPACE) { winnav_close();set_status(L"目录显示内存不足，阅读位置保留。");return; }
  }
  if(directory.result.page.count) SendMessageW(directory.rows,LB_SETCURSEL,0,0);
  SetWindowTextW(directory.message,directory.result.info.kind==READER_NAVIGATION_PAGES ? L"按页入口（不是作者目录）。":
    directory.result.page.count ? L"作者目录，顺序与重复项原样保留，每批最多32项。":L"本层没有目录项。");winnav_controls();
}
static LRESULT CALLBACK winnav_procedure(HWND window,UINT message,WPARAM wparam,LPARAM lparam) {
  if(message==WM_COMMAND) {
    int id=LOWORD(wparam),code=HIWORD(wparam);LRESULT selected=SendMessageW(directory.rows,LB_GETCURSEL,0,0);
    if(id==IDC_DIRECTORY_ROWS && code==LBN_SELCHANGE) {
      directory.accept_part=0;SetWindowTextW(directory.open,L"定位(&O)");winnav_controls();return 0;
    }
    if(id==IDC_DIRECTORY_OPEN || (id==IDC_DIRECTORY_ROWS && code==LBN_DBLCLK)) {
      uint64_t part=READER_NAVIGATION_NONE;
      if(directory.result.candidate_count) {
        if(selected==LB_ERR || (size_t)selected+directory.candidate_first>=directory.result.candidate_count) return 0;
        part=directory.result.candidates[directory.candidate_first+selected];
      }
      winnav_submit(1,0,0,part,directory.depth);return 0;
    }
    if(id==IDC_DIRECTORY_CANCEL) { winnav_cancel();return 0; }
    if(id==IDC_DIRECTORY_CLOSE || id==IDCANCEL) { winnav_close();return 0; }
    if(directory.running || g.job || g.pending) return 0;
    if(id==IDC_DIRECTORY_UP && directory.result.candidate_count) {
      free(directory.result.candidates);directory.result.candidates=NULL;directory.result.candidate_count=0;
      winnav_submit(0,directory.result.parent,directory.result.first,READER_NAVIGATION_NONE,directory.depth);return 0;
    }
    if((id==IDC_DIRECTORY_PREVIOUS || id==IDC_DIRECTORY_NEXT) && directory.result.candidate_count) {
      if(id==IDC_DIRECTORY_PREVIOUS && directory.candidate_first) directory.candidate_first-=HOST_NAV_BATCH;
      if(id==IDC_DIRECTORY_NEXT && directory.candidate_first+HOST_NAV_BATCH<directory.result.candidate_count) directory.candidate_first+=HOST_NAV_BATCH;
      winnav_candidates();return 0;
    }
    if(id==IDC_DIRECTORY_CHILDREN && selected!=LB_ERR && (size_t)selected<directory.result.page.count &&
        directory.result.page.rows[selected].child_count && directory.depth<READER_NAVIGATION_DEPTH_MAX) {
      directory.parents[directory.depth]=directory.result.parent;directory.starts[directory.depth]=directory.result.first;
      winnav_submit(0,directory.result.page.rows[selected].index,0,READER_NAVIGATION_NONE,directory.depth+1);return 0;
    }
    if(id==IDC_DIRECTORY_UP && directory.depth) {
      size_t depth=directory.depth-1;
      winnav_submit(0,directory.parents[depth],directory.starts[depth],READER_NAVIGATION_NONE,depth);return 0;
    }
    if(id==IDC_DIRECTORY_PREVIOUS && directory.result.first) {
      winnav_submit(0,directory.result.parent,directory.result.first>=HOST_NAV_BATCH ? directory.result.first-HOST_NAV_BATCH:0,READER_NAVIGATION_NONE,directory.depth);return 0;
    }
    if(id==IDC_DIRECTORY_NEXT && directory.result.page.next!=READER_NAVIGATION_NONE) {
      winnav_submit(0,directory.result.parent,directory.result.page.next,READER_NAVIGATION_NONE,directory.depth);return 0;
    }
  }
  if(message==WM_CLOSE) { winnav_close();return 0; }
  if(message==WM_SIZE && wparam==SIZE_MINIMIZED) winnav_cancel();
  return DefWindowProcW(window,message,wparam,lparam);
}
static void winnav_show(void) {
  if(directory.dialog) { SetForegroundWindow(directory.dialog);return; }
  if(g.job || g.pending || g.closing || !g.session.active) { set_status(L"打开书籍并等待当前任务完成后，可查看目录。");return; }
  WNDCLASSW type={0};type.lpfnWndProc=winnav_procedure;type.hInstance=GetModuleHandleW(NULL);
  type.hCursor=LoadCursor(NULL,IDC_ARROW);type.hbrBackground=(HBRUSH)(COLOR_BTNFACE+1);type.lpszClassName=L"EXReaderDirectory";
  if(!RegisterClassW(&type) && GetLastError()!=ERROR_CLASS_ALREADY_EXISTS) return;
  directory.dialog=CreateWindowExW(WS_EX_CONTROLPARENT,type.lpszClassName,L"目录",WS_OVERLAPPED|WS_CAPTION|WS_SYSMENU|WS_MINIMIZEBOX,
    CW_USEDEFAULT,CW_USEDEFAULT,720,475,g.window,NULL,type.hInstance,NULL);
  if(!directory.dialog) return;
  HWND window=directory.dialog;directory.book_id=g.current.id;directory.generation++;directory.running=directory.accept_part=0;
  directory.depth=0;directory.result.page.next=READER_NAVIGATION_NONE;
  HWND label=make_static(window,0,L"目录项(&R)");MoveWindow(label,12,10,680,22,TRUE);
  directory.rows=CreateWindowExW(WS_EX_CLIENTEDGE,L"LISTBOX",L"目录项",WS_CHILD|WS_VISIBLE|WS_TABSTOP|WS_VSCROLL|LBS_NOTIFY|LBS_NOINTEGRALHEIGHT,
    12,36,680,258,window,(HMENU)(INT_PTR)IDC_DIRECTORY_ROWS,NULL,NULL);
  SendMessageW(directory.rows,WM_SETFONT,(WPARAM)GetStockObject(DEFAULT_GUI_FONT),TRUE);
  directory.message=make_static(window,IDC_DIRECTORY_MESSAGE,L"正在读取目录…");MoveWindow(directory.message,12,300,680,45,TRUE);
  const int ids[]={IDC_DIRECTORY_OPEN,IDC_DIRECTORY_CHILDREN,IDC_DIRECTORY_UP,IDC_DIRECTORY_PREVIOUS,
    IDC_DIRECTORY_NEXT,IDC_DIRECTORY_CANCEL,IDC_DIRECTORY_CLOSE};
  const wchar_t *names[]={L"定位(&O)",L"子目录(&D)",L"上一级(&U)",L"上一批(&P)",L"下一批(&N)",L"取消(&X)",L"关闭(&C)"};
  HWND *controls[]={&directory.open,&directory.children,&directory.up,&directory.previous,&directory.next,&directory.cancel,NULL};
  for(size_t i=0;i<7;i++) {
    HWND button=make_button(window,ids[i],names[i]);MoveWindow(button,12+(int)i*98,355,92,30,TRUE);
    if(controls[i]) *controls[i]=button;
  }
  ShowWindow(window,SW_SHOW);SetFocus(directory.rows);
  winnav_submit(0,READER_NAVIGATION_NONE,0,READER_NAVIGATION_NONE,0);
}
static int winnav_translate(MSG *message) {
  if(message->message==WM_KEYDOWN && message->wParam=='G' && (GetKeyState(VK_CONTROL)&0x8000) &&
      !(GetKeyState(VK_SHIFT)&0x8000) && IsWindowEnabled(g.window)) { winnav_show();return 1; }
  if(!directory.dialog || (message->hwnd!=directory.dialog && !IsChild(directory.dialog,message->hwnd))) return 0;
  if(message->message==WM_KEYDOWN && message->wParam==VK_ESCAPE) {
    if(directory.running) winnav_cancel();else winnav_close();return 1;
  }
  if(message->message==WM_KEYDOWN && message->wParam==VK_RETURN && GetFocus()==directory.rows) {
    SendMessageW(directory.dialog,WM_COMMAND,IDC_DIRECTORY_OPEN,0);return 1;
  }
  return IsDialogMessageW(directory.dialog,message)!=0;
}
