/* SPDX-License-Identifier: MIT */
/* The existing serial SDK worker owns the enumerator and at most 32 receipts. */
typedef struct {
  linux_reader *reader;
  reader_batch_enumerator *scan;
  reader_batch_candidate *items;
  size_t count,index,rows;
  reader_batch_receipt receipts[READER_BATCH_DEFAULT_BATCH];
  char *staging;
  reader_batch_control *observe;
  int request,complete,truncated,stopped,cancelled,needs_map,done;
  uint64_t token,seen,attempted,imported,duplicates,failed,pending;
} gtk_batch_owner;
static int batch_cancelled(void *context) {
  gtk_batch_owner *batch=context;reader_batch_control *control=batch->observe;
  return control && (g_atomic_int_get(&control->request)!=batch->request || g_atomic_int_get(&control->cancelled));
}
static void batch_phase(gtk_batch_owner *batch,int phase) {
  if(batch->observe && g_atomic_int_get(&batch->observe->request)==batch->request)
    g_atomic_int_set(&batch->observe->phase,phase);
}
static void batch_progress(void *context,exr_stage stage,uint64_t completed,uint64_t total) {
  gtk_batch_owner *batch=context;
  if(stage==EXR_STAGE_READ && batch->observe && g_atomic_int_get(&batch->observe->request)==batch->request) {
    g_atomic_int_set(&batch->observe->current_bytes,(int)MIN(completed,(uint64_t)G_MAXINT));
    g_atomic_int_set(&batch->observe->total_bytes,(int)MIN(total,(uint64_t)G_MAXINT));
  }
}
static void batch_free(linux_reader *reader) {
  gtk_batch_owner *batch=reader->batch_data;if(!batch) return;
  reader_batch_enumerate_close(batch->scan);reader_batch_candidates_free(batch->items,batch->count);
  if(batch->staging) { g_rmdir(batch->staging);g_free(batch->staging); }
  free(batch);reader->batch_data=NULL;
}
static void batch_stop(gtk_batch_owner *batch) {
  batch->stopped=1;batch->cancelled|=batch_cancelled(batch);batch->needs_map=1;
  reader_batch_enumerate_close(batch->scan);batch->scan=NULL;
}
static exr_status batch_status(reader_batch_status code,const reader_batch_error *error) {
  if(code==READER_BATCH_OK) return EXR_OK;
  if(code==READER_BATCH_CANCELLED) return EXR_CANCELLED;
  if(code==READER_BATCH_MEMORY) return EXR_MEMORY;
  return error->status_code!=EXR_OK ? error->status_code:code==READER_BATCH_ARGUMENT ? EXR_ARGUMENT:EXR_IO;
}
static exr_status batch_map(gtk_batch_owner *batch,reader_result *result) {
  linux_reader *reader=batch->reader;reader_result listing={0};exr_error error={0};
  /* The frozen public SDK has no metadata-by-id getter. One temporary public
     snapshot per 32 imports (or stop) feeds the established repair operation.
     Only the bounded receipts and shelf page ever cross the worker queue. */
  exr_control previous=reader->control;reader->control.cancelled=NULL;reader->control.progress=NULL;
  exr_status status=exr_library_books(reader->library,"",&listing.books,&listing.book_count,&error);
  if(status==EXR_OK) status=product_refresh(reader,&listing);
  batch->pending=0;
  for(size_t i=0;i<batch->rows;i++) if(batch->receipts[i].committed) {
    int present=0;reader_catalog_error problem={0};
    if(reader->catalog && reader_catalog_has_local(reader->catalog,batch->receipts[i].book,&present,&problem)==0 && present)
      batch->receipts[i].mapped=1;
    else batch->pending++;
  }
  reader_result_free(&listing);reader->control=previous;
  batch->needs_map=0;
  if(status!=EXR_OK || batch->pending) {
    batch->done=1;
    snprintf(result->message,sizeof(result->message),"Books saved locally; catalog repair pending. Reopen the library to retry");
    return status==EXR_OK ? EXR_DATABASE:status;
  }
  if(batch->stopped || ((batch->complete || batch->truncated) && batch->index==batch->count)) batch->done=1;
  return EXR_OK;
}
static void batch_copy(gtk_batch_owner *batch,reader_result *result) {
  result->batch_token=batch->token;result->batch_done=batch->done;
  result->batch_complete=batch->complete;result->batch_truncated=batch->truncated;
  result->batch_cancelled=batch->cancelled;result->batch_map=batch->needs_map;
  result->batch_seen=batch->seen;result->batch_attempted=batch->attempted;
  result->batch_imported=batch->imported;result->batch_duplicates=batch->duplicates;
  result->batch_failed=batch->failed;result->batch_pending=batch->pending;
  if(batch->rows) {
    result->batch_rows=malloc(batch->rows*sizeof(*result->batch_rows));
    if(result->batch_rows) {
      memcpy(result->batch_rows,batch->receipts,batch->rows*sizeof(*result->batch_rows));result->batch_count=batch->rows;
    } else { result->status=EXR_MEMORY;batch_stop(batch);result->batch_map=1; }
  }
}
static void batch_execute(linux_reader *reader,const reader_command *command,reader_result *result) {
  gtk_batch_owner *batch=reader->batch_data;reader_batch_error error={0};reader_batch_status code=READER_BATCH_OK;
  result->has_batch=1;result->batch_token=command->batch_token;
  if(command->action==READER_BATCH_BEGIN) {
    if(batch || !command->batch_token || !command->batch_root || !command->batch_control) {
      result->status=EXR_ARGUMENT;snprintf(result->message,sizeof(result->message),"Finish the current folder import first");return;
    }
    batch=calloc(1,sizeof(*batch));
    if(!batch) { result->status=EXR_MEMORY;return; }
    reader->batch_data=batch;batch->reader=reader;batch->token=command->batch_token;
    batch->observe=command->batch_control;batch->request=command->batch_request;
    batch->staging=g_strconcat(reader->catalog_path,".batch-XXXXXX",NULL);
    if(!batch->staging || !g_mkdtemp_full(batch->staging,0700)) {
      result->status=EXR_IO;batch_free(reader);return;
    }
    reader_batch_scan_options options;reader_batch_scan_options_init(&options);
    options.root=command->batch_root;options.recursive=command->batch_recursive;
    options.max_candidates=command->batch_candidate_limit;
    options.control=(exr_control){batch_cancelled,batch_progress,batch};batch_phase(batch,1);
    code=reader_batch_enumerate_open(&options,&batch->scan,&error);
    if(code!=READER_BATCH_OK) {
      result->status=batch_status(code,&error);result->batch_done=1;result->batch_cancelled=code==READER_BATCH_CANCELLED;
      g_strlcpy(result->message,error.message,sizeof(result->message));batch_free(reader);return;
    }
  } else if(!batch || command->batch_token!=batch->token) {
    result->status=EXR_ARGUMENT;result->batch_done=1;return;
  }
  if(command->action==READER_BATCH_CLOSE) {
    batch_stop(batch);batch_phase(batch,3);result->status=batch_map(batch,result);batch->done=1;
    batch_copy(batch,result);batch_phase(batch,0);batch_free(reader);return;
  }
  if(command->action==READER_BATCH_MAP) {
    batch_phase(batch,3);result->status=batch_map(batch,result);batch_copy(batch,result);batch_phase(batch,0);return;
  }
  if(batch->done) { batch_copy(batch,result);return; }
  if(batch_cancelled(batch)) batch_stop(batch);
  if(batch->needs_map) { batch_copy(batch,result);return; }
  if(batch->index==batch->count) {
    reader_batch_candidates_free(batch->items,batch->count);batch->items=NULL;
    batch->count=batch->index=batch->rows=0;memset(batch->receipts,0,sizeof(batch->receipts));
    batch_phase(batch,1);
    code=reader_batch_enumerate_next(batch->scan,&batch->items,&batch->count,&batch->complete,&batch->truncated,&error);
    if(code!=READER_BATCH_OK) {
      if(code==READER_BATCH_CANCELLED) batch_stop(batch);else { batch->done=1;result->status=batch_status(code,&error); }
      g_strlcpy(result->message,error.message,sizeof(result->message));batch_copy(batch,result);return;
    }
    batch->seen+=batch->count;
    if(!batch->count) { batch->needs_map=1;batch_copy(batch,result);return; }
  }
  /* A displayed frame must commit before any SQLite import invalidates its
     borrowed source. Yield without touching it if the acceptance is pending. */
  if(reader->has_pending) { result->batch_deferred=1;batch_copy(batch,result);return; }
#ifdef EXR_READER_NAVIGATION
  navigation_free(reader);
#endif
#ifdef EXR_READER_SEARCH
  search_free(reader);
#endif
  reader_import_saved saved={0};result->status=reader_import_suspend(reader,&saved);
  if(result->status!=EXR_OK) { batch_stop(batch);batch_copy(batch,result);return; }
  reader_batch_candidate *candidate=&batch->items[batch->index];reader_batch_item item={0};
  item.struct_size=sizeof(item);item.path=candidate->path;item.format=candidate->format;
  reader_batch_import_options options;reader_batch_import_options_init(&options);options.staging_dir=batch->staging;
  options.control=(exr_control){batch_cancelled,batch_progress,batch};
  reader_batch_result *receipt=NULL;size_t count=0;batch_phase(batch,2);
  code=reader_batch_import(reader->library,&item,1,&options,&receipt,&count,&error);
  if(count==1) {
    reader_batch_receipt *row=&batch->receipts[batch->rows++];
    row->status=receipt->status;row->committed=receipt->committed;row->created=receipt->created;
    row->book=receipt->book_id;row->code=receipt->status_code;
    char *valid=g_utf8_make_valid(candidate->relative_path,-1),*short_path=g_utf8_substring(valid,0,MIN(g_utf8_strlen(valid,-1),100));
    g_strlcpy(row->path,short_path,sizeof(row->path));g_free(short_path);g_free(valid);
    g_strlcpy(row->message,receipt->message,sizeof(row->message));
    batch->attempted++;
    if(row->committed) { if(row->created) batch->imported++;else batch->duplicates++; }
    else if(row->status==READER_BATCH_ITEM_FAILED) batch->failed++;
    batch->index++;
  }
  reader_batch_results_free(receipt,count);
  exr_status restored=reader_import_resume(reader,&saved,result);
  if(restored!=EXR_OK) {
    snprintf(result->message,sizeof(result->message),"Import saved; reopen the original book from its saved position");batch_stop(batch);
  }
  if(code!=READER_BATCH_OK || batch_cancelled(batch)) {
    batch_stop(batch);
    if(code!=READER_BATCH_CANCELLED && code!=READER_BATCH_OK) result->status=batch_status(code,&error);
  }
  if(batch->index==batch->count) batch->needs_map=1;
  batch_copy(batch,result);batch_phase(batch,0);
}
