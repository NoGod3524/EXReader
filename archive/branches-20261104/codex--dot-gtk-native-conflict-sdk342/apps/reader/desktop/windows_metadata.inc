/* SPDX-License-Identifier: MIT */
/* Existing serialized host job. Every native owner opens and closes here;
 * only an exclusively owned, self-contained snapshot crosses job threads. */
static exr_status metadata_job_failure(host_job *job,reader_metadata_status code,const reader_metadata_error *error) {
  if(code==READER_METADATA_CONFLICT) job->metadata_conflict=1;
  job->error.code=code==READER_METADATA_IO ? EXR_IO:code==READER_METADATA_ARGUMENT ? EXR_ARGUMENT:EXR_DATABASE;
  snprintf(job->error.message,sizeof(job->error.message),"%s",error && error->message[0] ? error->message:
    code==READER_METADATA_CONFLICT ? "Book changed elsewhere; original edit is retained":
    code==READER_METADATA_PENDING ? "An earlier edit requires recovery":"Book metadata operation was refused");
  return job->error.code;
}
static void metadata_job_probe(reader_metadata_owner *owner,host_job *job) {
  reader_metadata_result pending={0};reader_metadata_error error={0};
  if(reader_metadata_pending(owner,&pending,&error)==READER_METADATA_OK) job->metadata_has_pending=1;
}
static char *metadata_strict_text(const wchar_t *wide,reader_metadata_error *error) {
  if(!wide) return NULL;
  char *result=malloc(16385);size_t bytes=0;
  if(!result) return NULL;
  reader_command_error converted={0};
  if(reader_command_utf16((const uint16_t *)wide,wcslen(wide),result,16385,&bytes,&converted)!=READER_COMMAND_OK) {
    if(error) { error->code=READER_METADATA_ARGUMENT;error->command=converted; }
    free(result);return NULL;
  }
  return result;
}
static char *metadata_normalized_title(const wchar_t *wide,reader_metadata_error *error) {
  size_t length=wcslen(wide);wchar_t *normalized=NULL;char *result=NULL;
  if(!length) return calloc(1,1);
  if(length>8192) return NULL;
  int capacity=NormalizeString(NormalizationC,wide,(int)length,NULL,0);
  if(capacity<0 && GetLastError()==ERROR_INSUFFICIENT_BUFFER) capacity=-capacity;
  for(int attempt=0;attempt<3 && capacity>0 && capacity<=32768;attempt++) {
    free(normalized);normalized=calloc((size_t)capacity+1,sizeof(*normalized));if(!normalized) break;
    int used=NormalizeString(NormalizationC,wide,(int)length,normalized,capacity);
    if(used<0 && GetLastError()==ERROR_INSUFFICIENT_BUFFER) { capacity=-used;continue; }
    if(used<=0 || used>capacity) break;
    normalized[used]=0;result=metadata_strict_text(normalized,error);break;
  }
  free(normalized);return result;
}
static exr_status metadata_prepare_job(reader_metadata_owner *owner,host_job *job) {
  reader_metadata_error error={0};reader_metadata_result result={0};
  reader_metadata_status code=reader_metadata_pending(owner,&result,&error);
  if(code==READER_METADATA_OK) { job->metadata_has_pending=1;return metadata_job_failure(job,READER_METADATA_PENDING,NULL); }
  if(code!=READER_METADATA_NO_PENDING) return metadata_job_failure(job,code,&error);
  code=reader_metadata_prepare_book(owner,job->metadata_key,&job->metadata_snapshot,&error);
  if(code!=READER_METADATA_OK && code!=READER_METADATA_NEEDS_BOOTSTRAP && code!=READER_METADATA_CONFLICT)
    return metadata_job_failure(job,code,&error);
  const reader_metadata_view *view=reader_metadata_snapshot_view(job->metadata_snapshot);
  if(!view || !view->present) return metadata_job_failure(job,READER_METADATA_CONFLICT,&error);
  if(code==READER_METADATA_NEEDS_BOOTSTRAP && !view->deleted) {
    exr_book original={0};exr_status status=local_book_copy(job->book_id,&original,&job->error);
    char sha[65];uint64_t bytes=0;
    if(status==EXR_OK && original.format!=product_format(view->book.format)) status=EXR_ARGUMENT;
    if(status==EXR_OK) {
      /* Public SDK source; a UI cancellation cannot interrupt this accepted
       * bootstrap job or disguise a committed product transaction as cancelled. */
      EnterCriticalSection(&g.library_lock);
      status=reader_catalog_sdk_original_identity(g.library,job->book_id,NULL,sha,&bytes,&job->error);
      LeaveCriticalSection(&g.library_lock);
    }
    book_clear(&original);
    if(status!=EXR_OK) return status;
    if(strcmp(sha,view->book.source_sha256) || bytes!=view->book.source_bytes) {
      snprintf(job->error.message,sizeof(job->error.message),"Stored original differs from the prepared book identity");return EXR_DATABASE;
    }
    reader_metadata_verified_source proof={view->book.format,sha,bytes};
    code=reader_metadata_stage_bootstrap(owner,job->metadata_snapshot,&proof,&result,&error);
    if(code==READER_METADATA_OK) code=reader_metadata_finish_pending(owner,&result,&error);
    job->metadata_committed=result.committed;job->metadata_has_pending=result.pending;
    if(code!=READER_METADATA_OK) { metadata_job_probe(owner,job);return metadata_job_failure(job,code,&error); }
    reader_metadata_snapshot_free(job->metadata_snapshot);job->metadata_snapshot=NULL;
    code=reader_metadata_prepare_book(owner,job->metadata_key,&job->metadata_snapshot,&error);
    if(code!=READER_METADATA_OK && code!=READER_METADATA_CONFLICT) return metadata_job_failure(job,code,&error);
    view=reader_metadata_snapshot_view(job->metadata_snapshot);
  }
  if(!view || !view->present) return EXR_ARGUMENT;
  job->metadata_title_value=host_wide(view->book.title,strlen(view->book.title));
  job->metadata_author_value=host_wide(view->book.author,strlen(view->book.author));
  if(!job->metadata_title_value || !job->metadata_author_value) return EXR_MEMORY;
  job->metadata_favorite=view->book.favorite;
  job->metadata_conflict=code==READER_METADATA_CONFLICT || view->deleted || view->needs_bootstrap || !view->graph.projection_safe;
  job->metadata_has_view=1;
  return EXR_OK;
}
static exr_status metadata_save_job(reader_metadata_owner *owner,host_job *job) {
  const reader_metadata_view *view=reader_metadata_snapshot_view(job->metadata_snapshot);
  if(!view || strcmp(view->book.book_key,job->metadata_key) || view->deleted || view->needs_bootstrap || (!view->graph.projection_safe && !job->metadata_conflict) ||
     !job->metadata_input_title || !job->metadata_input_author || (job->metadata_favorite!=0 && job->metadata_favorite!=1)) return EXR_ARGUMENT;
  reader_metadata_error error={0};reader_metadata_result result={0};
  char *title=metadata_strict_text(job->metadata_input_title,&error),*author=metadata_strict_text(job->metadata_input_author,&error);
  char *sort=title ? metadata_normalized_title(job->metadata_input_title,&error):NULL;
  if(!title || !author || !sort) { free(title);free(author);free(sort);return metadata_job_failure(job,READER_METADATA_ARGUMENT,&error); }
  reader_book_command edit=view->book;edit.operation=READER_COMMAND_PUT;
  edit.title=title;edit.author=author;edit.sort_title=sort;edit.favorite=job->metadata_favorite;
  reader_metadata_status code=job->metadata_conflict ?
    reader_metadata_stage_book_resolution(owner,job->metadata_snapshot,&edit,&result,&error):
    reader_metadata_stage_book(owner,job->metadata_snapshot,&edit,&result,&error);
  free(title);free(author);free(sort);
  if(code==READER_METADATA_OK) code=reader_metadata_finish_pending(owner,&result,&error);
  job->metadata_committed=result.committed;job->metadata_has_pending=result.pending;
  if(code!=READER_METADATA_OK) { metadata_job_probe(owner,job);return metadata_job_failure(job,code,&error); }
  return result.committed ? EXR_OK:EXR_DATABASE;
}
static exr_status metadata_job_run(host_job *job) {
  reader_metadata_owner *owner=NULL;reader_metadata_error error={0};
  char *database=host_utf8(g.product_path),*pending=NULL;
  if(!database) return EXR_MEMORY;
  size_t length=strlen(database)+32;pending=malloc(length);
  if(!pending) { free(database);return EXR_MEMORY; }
  snprintf(pending,length,"%s.commands.pending",database);
  reader_metadata_status code=reader_metadata_open(database,pending,&owner,&error);free(database);free(pending);
  if(code!=READER_METADATA_OK) return metadata_job_failure(job,code,&error);
  exr_status status;
  if(job->kind==JOB_METADATA_PREPARE) status=metadata_prepare_job(owner,job);
  else if(job->kind==JOB_METADATA_SAVE) status=metadata_save_job(owner,job);
  else {
    reader_metadata_result result={0};
    code=job->kind==JOB_METADATA_RETRY ? reader_metadata_finish_pending(owner,&result,&error):reader_metadata_abandon_pending(owner,&error);
    job->metadata_committed=result.committed;job->metadata_has_pending=result.pending;
    if(code==READER_METADATA_OK || code==READER_METADATA_NO_PENDING) status=EXR_OK;
    else { metadata_job_probe(owner,job);status=metadata_job_failure(job,code,&error); }
  }
  if(reader_metadata_close(&owner,&error)!=READER_METADATA_OK && status==EXR_OK) status=metadata_job_failure(job,error.code,&error);
  return status;
}
