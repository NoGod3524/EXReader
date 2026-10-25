/* SPDX-License-Identifier: MIT
 * Original identity and fresh public SDK input for search and navigation.
 * Called only by the existing serialized worker, never by a UI callback.
 */
static exr_status winreader_identity(int64_t book,exr_format format,int fixed,int bounded,
  char out[256],const exr_control *control,exr_error *error) {
  char digest[65];uint64_t bytes=0;
  EnterCriticalSection(&g.library_lock);
  exr_status status=reader_catalog_sdk_original_identity(g.library,book,control,digest,&bytes,error);
  LeaveCriticalSection(&g.library_lock);
  if(status==EXR_OK) snprintf(out,256,"sdk3.40.0:projection1:%d:%d:%s:%llu",
    (int)format,fixed ? 3:bounded ? 2:1,digest,(unsigned long long)bytes);
  return status;
}
static exr_status winreader_fresh(host_job *job,host_session *out) {
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
