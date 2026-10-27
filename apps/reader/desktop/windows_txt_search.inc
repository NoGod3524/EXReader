/* SPDX-License-Identifier: MIT
 * Bounded TXT search on the host's existing serialized worker. The cursor is
 * checkpointed at paragraph boundaries and only copied values reach the UI. */
static exr_status wintxt_search_source(host_job *job,exr_source *source,HANDLE *handle) {
  reader_catalog *catalog=NULL;reader_catalog_error ce={0};
  reader_original_callbacks callbacks={job,job_cancel_check,NULL};
  char *database=host_utf8(g.product_path),*root=host_utf8(g.original_root);
  void *opened=NULL;uint64_t bytes=0;reader_original_status result=ROI_IO;
  memset(source,0,sizeof(*source));*handle=NULL;
  if(!database || !root) { free(database);free(root);return EXR_MEMORY; }
  if(!reader_catalog_open(database,&catalog,&ce))
    result=reader_original_verified_handle(catalog,root,job->txt_key,&callbacks,&opened,&bytes);
  if(catalog) reader_catalog_close(&catalog,&ce);
  free(database);free(root);
  if(result!=ROI_OK) return result==ROI_CANCELLED ? EXR_CANCELLED:result==ROI_MEMORY ? EXR_MEMORY:EXR_IO;
  *handle=(HANDLE)opened;
  source->size=bytes;source->context=opened;source->read_at=txt_read;
  source->control=(exr_control){job_cancel_check,NULL,job};
  return EXR_OK;
}

/* KMP visits each projected byte once per batch. A resumed batch replays only
 * the paragraph containing the preceding hit; separators are real projected LF. */
typedef struct {
  host_job *job;const char *query;size_t length,matched;
  size_t prefix[READER_SEARCH_QUERY_MAX];
} wintxt_match;
static exr_status wintxt_feed(wintxt_match *m,unsigned char value,uint64_t at) {
  while(m->matched && value!=(unsigned char)m->query[m->matched]) m->matched=m->prefix[m->matched-1];
  if(value==(unsigned char)m->query[m->matched]) m->matched++;
  if(m->matched==m->length) {
    host_search_hit *hit;uint64_t end=at+1,start=end-m->length;
    if(end>SIZE_MAX) return EXR_LIMIT;
    hit=&m->job->search_batch.hits[m->job->search_batch.count];
    hit->txt=1;hit->mode=READER_SEARCH_REFLOW;hit->unit=start;
    hit->anchor.start=(size_t)start;hit->anchor.end=(size_t)end;
    hit->anchor.exact=host_strdup(m->query);
    if(!hit->anchor.exact) return EXR_MEMORY;
    m->job->search_batch.count++;m->matched=0;
  }
  return EXR_OK;
}
static exr_status wintxt_search_batch(host_job *job) {
  exr_source source=g.session.txt_source;exr_txt_cursor *cursor=NULL;
  exr_txt_checkpoint before={0};const char *text=NULL;uint64_t offset=0,from=0;
  size_t size=0;exr_status status;wintxt_match scan={0};
  scan.job=job;scan.query=job->search_query;scan.length=strlen(scan.query);
  if(!scan.length || scan.length>READER_SEARCH_QUERY_MAX ||
     !MultiByteToWideChar(CP_UTF8,MB_ERR_INVALID_CHARS,scan.query,(int)scan.length,NULL,0))
    return EXR_ARGUMENT;
  for(size_t i=1,j=0;i<scan.length;i++) {
    while(j && scan.query[i]!=scan.query[j]) j=scan.prefix[j-1];
    if(scan.query[i]==scan.query[j]) j++;
    scan.prefix[i]=j;
  }
  /* The live source is the no-write/no-delete shared handle verified on open.
     The serialized worker owns it for this call; no per-batch whole-file hash. */
  source.control=(exr_control){job_cancel_check,NULL,job};
  status=exr_txt_cursor_create(&source,&cursor,&job->error);
  if(status!=EXR_OK) goto done;
  if(job->search_has_resume) {
    if(!job->search_txt_resume.present) { status=EXR_ARGUMENT;goto done; }
    before=job->search_txt_resume.checkpoint;from=job->search_txt_resume.next_offset;
    if(from<before.projection_offset) { status=EXR_ARGUMENT;goto done; }
    status=exr_txt_cursor_restore(cursor,&before,&job->error);
    if(status!=EXR_OK) goto done;
  }
  for(;;) {
    status=exr_txt_cursor_checkpoint(cursor,&before,&job->error);
    if(status!=EXR_OK) goto done;
    status=exr_txt_cursor_next(cursor,&offset,&text,&size,&job->error);
    if(status!=EXR_OK) goto done;
    if(!text) { job->search_batch.complete=1;break; }
    if(offset && offset-1>=from) {
      status=wintxt_feed(&scan,'\n',offset-1);
      if(status!=EXR_OK) goto done;
      if(job->search_batch.count==HOST_SEARCH_BATCH) {
        job->search_batch.txt_next=(host_txt_search_cursor){before,offset,1};break;
      }
    }
    for(size_t i=0;i<size;i++) {
      uint64_t at=offset+i;
      if(!(i&4095) && job_cancel_flag(job)) { status=EXR_CANCELLED;goto done; }
      if(at<from) continue;
      status=wintxt_feed(&scan,(unsigned char)text[i],at);
      if(status!=EXR_OK) goto done;
      if(job->search_batch.count==HOST_SEARCH_BATCH) {
        job->search_batch.txt_next=(host_txt_search_cursor){before,at+1,1};goto done;
      }
    }
  }
done:
  exr_txt_cursor_free(cursor);
  if(status!=EXR_OK) winsearch_batch_free(&job->search_batch);
  return status;
}

/* A hit is accepted only after the immutable product original is opened and
 * verified again and both the fresh and live projections confirm the exact text. */
static exr_status wintxt_search_open(host_job *job) {
  exr_source fresh={0},live=g.session.txt_source;HANDLE handle=NULL;
  const host_search_hit *hit=&job->search_hit;exr_control control={job_cancel_check,NULL,job};
  uint64_t start=UINT64_MAX,end=UINT64_MAX;size_t page=0,count=0;
  const exr_layout *layout=NULL;const exr_page *info;exr_status status;
  if(!hit->txt || !hit->anchor.exact || g.session.txt_pager_invalid) return EXR_ARGUMENT;
  status=wintxt_search_source(job,&fresh,&handle);
  if(status!=EXR_OK) return status;
  status=exr_txt_find_source(&fresh,hit->anchor.exact,hit->anchor.start,&start,&end,&job->error);
  if(status==EXR_OK && (start!=hit->anchor.start || end!=hit->anchor.end)) status=EXR_ARGUMENT;
  if(handle) CloseHandle(handle);
  if(status!=EXR_OK) return status;
  live.control=control;start=end=UINT64_MAX;
  status=exr_txt_find_source(&live,hit->anchor.exact,hit->anchor.start,&start,&end,&job->error);
  if(status!=EXR_OK || start!=hit->anchor.start || end!=hit->anchor.end) return status==EXR_OK ? EXR_ARGUMENT:status;
  status=page_for_offset(&g.session,(size_t)start,&control,&page,NULL,NULL,&job->error);
  if(status==EXR_OK) status=exr_pager_get(g.session.pager,page,&layout,&job->error);
  if(status!=EXR_OK) { g.session.txt_pager_invalid=1;return status; }
  status=txt_frame(&g.session,&g.session.txt_source,layout,page,&job->frame,&job->error);
  if(status!=EXR_OK) return status;
  info=exr_layout_pages(layout,&count);
  if(!info || !count || start<info->start || start>=info->end) { frame_clear(&job->frame);return EXR_FORMAT; }
  copy_wstring(job->frame.title,256,g.frame.title);
  job->have_frame=1;job->applied_page=page;job->target_page=page;
  job->note_start=(size_t)start;job->note_end=(size_t)(end<info->end ? end:info->end);
  job->resolved_selection=job->note_start<job->note_end;
  return job_cancel_flag(job) ? EXR_CANCELLED:EXR_OK;
}
