/* SPDX-License-Identifier: MIT
 * Host-only glue, included after host_job and the existing import worker.
 * Each temporary host worker owns its own catalog connection. */
static exr_status product_job_run(host_job *job) {
  reader_catalog *catalog=NULL;reader_catalog_error product_error={0};
  exr_book *books=NULL;size_t count=0,failed=0;exr_status status=EXR_OK;
  exr_control control={job_cancel_check,NULL,job};
  char *path=host_utf8(g.product_path);
  if(!path) return EXR_MEMORY;
  if(job_cancel_flag(job)) { free(path);return EXR_CANCELLED; }
  int result=reader_catalog_open(path,&catalog,&product_error);free(path);
  if(result!=0) {
    job->error.code=EXR_DATABASE;
    snprintf(job->error.message,sizeof(job->error.message),"%s",product_error.message);
    return EXR_DATABASE;
  }
  if(job->kind==JOB_PRODUCT_DELETE) {
    /* A failed catalog write must not delete the original and leave a stale
       local mapping. SDK failure can leave a missing mapping, repaired later. */
    result=reader_catalog_remove_local(catalog,job->book_id,&product_error);
    if(result!=0) status=EXR_DATABASE;
    else if(job_cancel_flag(job)) status=EXR_CANCELLED;
    else {
      EnterCriticalSection(&g.library_lock);
      status=exr_library_delete(g.library,job->book_id,&job->error);
      LeaveCriticalSection(&g.library_lock);
      job->product_deleted=status==EXR_OK;
    }
  } else {
    EnterCriticalSection(&g.library_lock);
    status=exr_library_books(g.library,"",&books,&count,&job->error);
    if(status==EXR_OK && job->kind==JOB_PRODUCT_ATTACH) {
      size_t at=0;while(at<count && books[at].id!=job->book_id) ++at;
      if(at==count) {
        status=EXR_ARGUMENT;job->error.code=status;
        snprintf(job->error.message,sizeof(job->error.message),"Accepted SDK book no longer exists");
      } else status=reader_catalog_sdk_attach(catalog,g.library,&books[at],&control,NULL,&job->error);
    } else if(status==EXR_OK)
      status=reader_catalog_sdk_repair(catalog,g.library,books,count,&control,&failed,&job->error);
    exr_books_free(books,count);
    LeaveCriticalSection(&g.library_lock);
  }
  if(result!=0) {
    job->error.code=EXR_DATABASE;
    snprintf(job->error.message,sizeof(job->error.message),"%s",product_error.message);
  }
  if(reader_catalog_close(&catalog,&product_error)!=0 && status==EXR_OK) {
    status=EXR_DATABASE;job->error.code=status;
    snprintf(job->error.message,sizeof(job->error.message),"%s",product_error.message);
  }
  return status;
}
