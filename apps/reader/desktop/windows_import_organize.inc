/* SPDX-License-Identifier: MIT
 * Two phases, one host scheduler. Network jobs own only their WebDAV client;
 * only WINIO_IMPORT enters the existing SDK library lock. Product work opens
 * the same installed metadata owner and same pending sidecar as single edits.
 */
static struct {
  HWND dialog,rows,message,groups,action,report;
  int mode,running,close_wanted,action_value,group_more,orphans;
  unsigned long generation;
  exr_webdav_listing listing;
  reader_cloud_staged *retained;
  char resource[4097],parent[33],parents[32][33];size_t depth;
  winio_group group_rows[200];size_t group_count;
  char keys[150][73];int64_t ids[150];size_t count;
  wchar_t titles[150][512];
  reader_bulk_summary summary;
  reader_bulk_item_result results[READER_BULK_MAX_BATCH];
  wchar_t staging[HOST_PATH],receipts[HOST_PATH];
  HANDLE profile_lock;
} winio;
static int winio_modal_blocked(void) { return winio.dialog!=NULL || winio.running; }

static int winio_kind(int kind) { return kind==JOB_IMPORT_ORGANIZE; }
static void winio_job_free(winio_job *value) {
  if(!value) return;
  exr_webdav_listing_free(&value->listing);
  if(value->staged) {
    /* A refused delete NEVER drops the opaque owner. New downloads are
       blocked until this exact owner has been successfully discarded. */
    if(value->staged) { winio.retained=value->staged;value->staged=NULL; }
  }
  free(value);
}
static int winio_paths(host_job *job) {
  if(acct_ready(job)!=EXR_OK) return 0;
  swprintf(winio.staging,HOST_PATH,L"%ls\\cloud-import",acct.home);
  swprintf(winio.receipts,HOST_PATH,L"%ls\\cloud-import.receipts",acct.home);
  if(!acct_directory(winio.staging,1)) return 0;
  if(!winio.profile_lock) {
    wchar_t lock[HOST_PATH];swprintf(lock,HOST_PATH,L"%ls\\owner.lock",winio.staging);
    HANDLE handle=CreateFileW(lock,GENERIC_READ|GENERIC_WRITE,0,NULL,OPEN_ALWAYS,FILE_ATTRIBUTE_NORMAL|FILE_FLAG_OPEN_REPARSE_POINT,NULL);
    BY_HANDLE_FILE_INFORMATION info;
    if(handle==INVALID_HANDLE_VALUE) return 0;
    if(!GetFileInformationByHandle(handle,&info) || (info.dwFileAttributes&(FILE_ATTRIBUTE_DIRECTORY|FILE_ATTRIBUTE_REPARSE_POINT)) || info.nNumberOfLinks!=1) { CloseHandle(handle);return 0; }
    winio.profile_lock=handle;
    wchar_t pattern[HOST_PATH];WIN32_FIND_DATAW entry;swprintf(pattern,HOST_PATH,L"%ls\\cloud-*",winio.staging);
    HANDLE find=FindFirstFileW(pattern,&entry);winio.orphans=find!=INVALID_HANDLE_VALUE;
    if(find!=INVALID_HANDLE_VALUE) FindClose(find);
  }
  return 1;
}
/* Append-only host receipt. It is deliberately not a product schema or sync
   entity; no credentials or remote titles are written. A failed append is
   reported independently and never changes a committed receipt. */
static int winio_receipt(host_job *job) {
  winio_job *v=job->io;char data[512];DWORD wrote=0;
  int size=snprintf(data,sizeof(data),"operation=%d account=%s status=%d http=%d committed=%d created=%d book=%lld staging_removed=%d mapped=%d retained=%d\r\n",
    v->operation,acct.owner.id,(int)v->cloud_status,v->cloud_error.http_status,v->imported.committed,v->imported.created,
    (long long)v->imported.book_id,v->imported.staging_removed,v->mapped,v->staged!=NULL);
  HANDLE f=CreateFileW(winio.receipts,FILE_APPEND_DATA,FILE_SHARE_READ,NULL,OPEN_ALWAYS,
    FILE_ATTRIBUTE_NORMAL|FILE_FLAG_OPEN_REPARSE_POINT|FILE_FLAG_WRITE_THROUGH,NULL);
  BY_HANDLE_FILE_INFORMATION info;int ok=f!=INVALID_HANDLE_VALUE && GetFileInformationByHandle(f,&info) &&
    !(info.dwFileAttributes&(FILE_ATTRIBUTE_DIRECTORY|FILE_ATTRIBUTE_REPARSE_POINT)) && info.nNumberOfLinks==1;
  if(ok) ok=size>0 && WriteFile(f,data,(DWORD)size,&wrote,NULL) && wrote==(DWORD)size && FlushFileBuffers(f);
  if(f!=INVALID_HANDLE_VALUE) CloseHandle(f);return ok;
}
static exr_status winio_network(host_job *job) {
  winio_job *v=job->io;acct_owner *o=&acct.owner;
  exr_webdav_client *client=NULL;exr_webdav_config config={0};
  char *pair=NULL,*encoded=NULL,*authorization=NULL,*directory=NULL;
  exr_status status=acct_load_job(job);
  if(status!=EXR_OK || !o->bound || !o->secret || (v->account[0] && strcmp(v->account,o->id))) {
    copy_wstring(job->message,512,L"账号未配置、凭据不可用或账号已改变；未降级保存明文。");return EXR_ARGUMENT;
  }
  if(!winio_paths(job)) return EXR_IO;
  if(v->operation==WINIO_DOWNLOAD && (winio.orphans || winio.retained)) {
    copy_wstring(job->message,512,L"先明确重试上次暂存清理；原件和已提交书籍不会删除。");return EXR_IO;
  }
  snprintf(v->account,sizeof(v->account),"%s",o->id);
  pair=calloc(o->secret_size+1,1);encoded=calloc((o->secret_size+2)/3*4+1,1);
  authorization=calloc((o->secret_size+2)/3*4+16,1);directory=host_utf8(winio.staging);
  if(!pair || !encoded || !authorization || !directory) { status=EXR_MEMORY;goto done; }
  memcpy(pair,o->secret,o->secret_size);pair[o->secret_size]=0;pair[strlen(o->user)]=':';
  acct_base64((unsigned char *)pair,o->secret_size,encoded);
  snprintf(authorization,(o->secret_size+2)/3*4+16,"Basic %s",encoded);
  config.root_url=o->root;config.authorization=authorization;config.timeout_ms=15000;
  config.max_entries=2000;
  exr_webdav_status code=exr_webdav_create(&config,&client,&v->dav_error);
  if(code!=EXR_DAV_OK) { status=EXR_IO;goto done; }
  if(v->operation==WINIO_LIST) {
    exr_webdav_control control={job_cancel_check,NULL,job};
    code=exr_webdav_list(client,v->resource,&control,&v->listing,&v->dav_error);
    status=code==EXR_DAV_OK ? EXR_OK:code==EXR_DAV_CANCELLED ? EXR_CANCELLED:EXR_IO;
    swprintf(job->message,512,L"目录 status=%d HTTP=%d；明确选择一本书后才下载。",code,v->dav_error.http_status);
  } else {
    reader_cloud_request request;reader_cloud_request_init(&request);
    request.resource=v->resource;request.display_name=v->name;request.expected_bytes=v->bytes;
    request.staging_dir=directory;request.control=(reader_cloud_control){job_cancel_check,NULL,job};
    v->cloud_status=reader_cloud_download(client,&request,&v->staged,&v->cloud_error);
    status=v->cloud_status==READER_CLOUD_OK ? EXR_OK:v->cloud_status==READER_CLOUD_CANCELLED ? EXR_CANCELLED:EXR_IO;
    v->receipt_saved=winio_receipt(job);
  }
done:
  exr_webdav_free(client);
  if(pair) { exr_credentials_wipe(pair,o->secret_size+1);free(pair); }
  if(encoded) { exr_credentials_wipe(encoded,strlen(encoded));free(encoded); }
  if(authorization) { exr_credentials_wipe(authorization,strlen(authorization));free(authorization); }
  free(directory);return status;
}
static exr_status winio_import(host_job *job) {
  winio_job *v=job->io;
  if(!v->staged || strcmp(v->account,acct.owner.id)) return EXR_ARGUMENT;
  reader_cloud_import_options options;reader_cloud_import_options_init(&options);
  options.control=(reader_cloud_control){job_cancel_check,NULL,job};
  v->imported.struct_size=sizeof(v->imported);
  EnterCriticalSection(&g.library_lock);
  v->cloud_status=reader_cloud_import(g.library,&v->staged,&options,&v->imported,&v->cloud_error);
  LeaveCriticalSection(&g.library_lock);
  if(v->imported.committed) {
    /* J01 commit wins over cancellation. The existing public original mapping
       barrier runs uncancellable AFTER that commit, never on the network job. */
    host_job attach={0};attach.kind=JOB_PRODUCT_ATTACH;attach.book_id=v->imported.book_id;
    v->mapped=product_job_run(&attach)==EXR_OK;
    snprintf(job->product_key,sizeof(job->product_key),"%s",attach.product_key);
  }
  v->receipt_saved=winio_receipt(job);
  return v->imported.committed ? EXR_OK:v->cloud_status==READER_CLOUD_CANCELLED ? EXR_CANCELLED:EXR_IO;
}
static int winio_group_visit(void *context,const reader_catalog_group_row *row) {
  winio_job *v=context;if(v->group_count>=200) return 1;
  winio_group *out=&v->groups[v->group_count++];
  snprintf(out->id,sizeof(out->id),"%s",row->id);snprintf(out->parent,sizeof(out->parent),"%s",row->parent_id ? row->parent_id:"");out->ordinal=row->ordinal;
  wchar_t *name=host_wide(row->name,strlen(row->name));copy_wstring(out->name,512,name ? name:L"");free(name);return 0;
}
static exr_status winio_groups(host_job *job) {
  winio_job *v=job->io;reader_catalog *catalog=NULL;reader_catalog_error error={0};
  char *path=host_utf8(g.product_path);if(!path) return EXR_MEMORY;
  int code=reader_catalog_open(path,&catalog,&error);free(path);
  reader_catalog_group_cursor cursor={v->after_ordinal,v->after};
  if(!code) code=reader_catalog_groups_page(catalog,(reader_catalog_group_kind)v->group_kind,
    v->parent[0] ? v->parent:NULL,v->more ? &cursor:NULL,1,200,winio_group_visit,v,&error);
  if(catalog) reader_catalog_close(&catalog,&error);
  return code ? EXR_DATABASE:EXR_OK;
}
static void winio_bootstrap(reader_metadata_owner *owner,host_job *job) {
  winio_job *v=job->io;
  /* Only explicitly selected books are eligible. Verify public retained bytes
     before legacy bootstrap; conflicts are left for J10's item receipt. */
  for(size_t i=0;i<v->count;i++) {
    if(job_cancel_flag(job)) break;
    reader_metadata_snapshot *snapshot=NULL;reader_metadata_error error={0};reader_metadata_result result={0};
    reader_metadata_status code=reader_metadata_prepare_book(owner,v->keys[i],&snapshot,&error);
    const reader_metadata_view *view=reader_metadata_snapshot_view(snapshot);
    if(code==READER_METADATA_NEEDS_BOOTSTRAP && view && view->present && !view->deleted) {
      char hash[65];uint64_t bytes=0;exr_error sdk={0};
      EnterCriticalSection(&g.library_lock);
      exr_status status=reader_catalog_sdk_original_identity(g.library,v->ids[i],NULL,hash,&bytes,&sdk);
      LeaveCriticalSection(&g.library_lock);
      if(status==EXR_OK && !strcmp(hash,view->book.source_sha256) && bytes==view->book.source_bytes) {
        reader_metadata_verified_source proof={view->book.format,hash,bytes};
        code=reader_metadata_stage_bootstrap(owner,snapshot,&proof,&result,&error);
        if(code==READER_METADATA_OK) code=reader_metadata_finish_pending(owner,&result,&error);
      }
    }
    reader_metadata_snapshot_free(snapshot);
  }
}
static exr_status winio_bulk(host_job *job) {
  winio_job *v=job->io;reader_metadata_owner *owner=NULL;reader_metadata_error metadata={0};reader_bulk *bulk=NULL;
  char *product=host_utf8(g.product_path),*journal=NULL;exr_status status=EXR_DATABASE;
  if(!product) return EXR_MEMORY;
  journal=malloc(strlen(product)+32);if(!journal) { free(product);return EXR_MEMORY; }
  sprintf(journal,"%s.bulk.pending",product);
  if(!acct_open_metadata(&owner,&metadata)) goto done;
  if(reader_bulk_open(owner,product,journal,&bulk,&v->bulk_error)!=READER_BULK_OK) goto done;
  reader_bulk_control control={job,job_cancel_check,NULL};
  if(v->operation==WINIO_RUN) {
    const char *keys[READER_BULK_MAX_BATCH];for(size_t i=0;i<v->count;i++) keys[i]=v->keys[i];
    /* Do not touch a retained request before explicitly resuming it. */
    v->bulk_status=reader_bulk_inspect(bulk,v->results,READER_BULK_MAX_BATCH,&v->summary,&v->bulk_error);
    if(v->bulk_status==READER_BULK_NO_JOURNAL) {
      winio_bootstrap(owner,job);
      reader_bulk_request request={0};request.struct_size=sizeof(request);request.action=(reader_bulk_action)v->action;
      request.group_id=v->group[0] ? v->group:NULL;request.book_keys=keys;request.book_count=v->count;request.control=control;
      v->bulk_status=reader_bulk_run(bulk,&request,v->results,READER_BULK_MAX_BATCH,&v->summary,&v->bulk_error);
    } else if(v->bulk_status==READER_BULK_OK) v->bulk_status=READER_BULK_JOURNAL_ACTIVE;
  } else if(v->operation==WINIO_RESUME)
    v->bulk_status=reader_bulk_resume(bulk,&control,v->results,READER_BULK_MAX_BATCH,&v->summary,&v->bulk_error);
  else if(v->operation==WINIO_ACK) v->bulk_status=reader_bulk_acknowledge(bulk,&v->bulk_error);
  else v->bulk_status=reader_bulk_inspect(bulk,v->results,READER_BULK_MAX_BATCH,&v->summary,&v->bulk_error);
  status=(v->bulk_status==READER_BULK_OK || v->bulk_status==READER_BULK_NO_JOURNAL) ? EXR_OK:
    v->bulk_status==READER_BULK_CANCELLED ? EXR_CANCELLED:EXR_DATABASE;
done:
  if(bulk) reader_bulk_close(&bulk,&v->bulk_error);
  if(owner) reader_metadata_close(&owner,&metadata);
  free(product);free(journal);return status;
}
static exr_status winio_job_run(host_job *job) {
  winio_job *v=job->io;if(!v) return EXR_ARGUMENT;
  if(v->operation==WINIO_LIST || v->operation==WINIO_DOWNLOAD) return winio_network(job);
  if(v->operation==WINIO_IMPORT) return winio_import(job);
  if(v->operation==WINIO_CLEAN) {
    if(!winio_paths(job)) return EXR_IO;
    v->staged=winio.retained;winio.retained=NULL;reader_cloud_staged_discard(&v->staged);
    if(!v->staged && winio.orphans) {
      wchar_t pattern[HOST_PATH];WIN32_FIND_DATAW entry;swprintf(pattern,HOST_PATH,L"%ls\\cloud-*",winio.staging);
      HANDLE find=FindFirstFileW(pattern,&entry);int failed=0;
      if(find!=INVALID_HANDLE_VALUE) {
        do {
          wchar_t path[HOST_PATH];swprintf(path,HOST_PATH,L"%ls\\%ls",winio.staging,entry.cFileName);
          /* No recursive traversal; never delete a link or unknown directory. */
          HANDLE file=acct_open_private(path,NULL);
          if(file==INVALID_HANDLE_VALUE) failed=1;
          else { CloseHandle(file);if(!DeleteFileW(path)) failed=1; }
        } while(FindNextFileW(find,&entry));FindClose(find);
      }
      winio.orphans=failed;
    }
    v->imported.staging_removed=v->staged==NULL;v->cloud_status=v->staged ? READER_CLOUD_IO:READER_CLOUD_OK;
    v->receipt_saved=winio_receipt(job);return v->staged || winio.orphans ? EXR_IO:EXR_OK;
  }
  if(v->operation==WINIO_GROUPS) return winio_groups(job);
  return winio_bulk(job);
}
