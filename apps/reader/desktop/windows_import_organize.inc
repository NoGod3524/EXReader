/* SPDX-License-Identifier: MIT
 * Two phases, one host scheduler. Network jobs own only their WebDAV client;
 * only WINIO_IMPORT enters the existing SDK library lock. Product work opens
 * the same installed metadata API, with separate durable intent namespaces
 * for J10 actions, legacy bootstrap, and the existing single-book editor.
 */
static struct {
  HWND dialog,rows,message,groups,action,report;
  int mode,running,close_wanted,action_value,group_more,orphans;
  unsigned long generation;
  exr_webdav_listing listing;
  reader_cloud_staged *retained;
  reader_cloud_import_result retained_receipt;
  int retained_mapped;
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
static int winio_staging_scan(int clean) {
  /* A killed native transfer can leave its own temporary copy before J01 has
     an opaque published owner. Both namespaces are private to this directory. */
  const wchar_t *patterns[]={L"cloud-*",L".exr-webdav-*.tmp"};int remaining=0;
  for(size_t i=0;i<2;i++) {
    wchar_t pattern[HOST_PATH];WIN32_FIND_DATAW entry;swprintf(pattern,HOST_PATH,L"%ls\\%ls",winio.staging,patterns[i]);
    HANDLE find=FindFirstFileW(pattern,&entry);
    if(find==INVALID_HANDLE_VALUE) { if(GetLastError()!=ERROR_FILE_NOT_FOUND) remaining=1;continue; }
    do {
      if(!clean) { remaining=1;continue; }
      wchar_t path[HOST_PATH];swprintf(path,HOST_PATH,L"%ls\\%ls",winio.staging,entry.cFileName);
      HANDLE file=acct_open_private(path,NULL);
      if(file==INVALID_HANDLE_VALUE) remaining=1;
      else { CloseHandle(file);if(!DeleteFileW(path)) remaining=1; }
    } while(FindNextFileW(find,&entry));FindClose(find);
  }
  return remaining;
}
static void winio_job_free(winio_job *value) {
  if(!value) return;
  exr_webdav_listing_free(&value->listing);
  if(value->staged) {
    /* A refused delete NEVER drops the opaque owner. New downloads are
       blocked until this exact owner has been successfully discarded. */
    if(value->staged) { winio.retained=value->staged;winio.retained_receipt=value->imported;winio.retained_mapped=value->mapped;value->staged=NULL; }
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
    winio.orphans=winio_staging_scan(0);
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
  wchar_t *name=host_wide(row->name,strlen(row->name));copy_wstring(out->name,513,name ? name:L"");free(name);return 0;
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
/* Use the existing editor intent and recovery path; never replace an earlier
   intent, or claim cancellation after the native transaction has committed. */
static exr_status winio_group_edit(host_job *job) {
  winio_job *v=job->io;reader_metadata_owner *owner=NULL;
  reader_metadata_snapshot *snapshot=NULL;reader_metadata_result result={0};
  reader_metadata_error error={0};reader_metadata_status code;
  if(v->operation==WINIO_CREATE_GROUP && acct_receive_barrier(job)!=EXR_OK) {
    copy_wstring(job->message,512,L"请先恢复或确认之前的编辑和批量整理。");return EXR_DATABASE;
  }
  if(!acct_open_metadata(&owner,&error)) return EXR_DATABASE;
  if(v->operation==WINIO_RECOVER_EDIT || v->operation==WINIO_ABANDON_EDIT) {
    code=v->operation==WINIO_RECOVER_EDIT ? reader_metadata_finish_pending(owner,&result,&error):reader_metadata_abandon_pending(owner,&error);
    if(code==READER_METADATA_NO_PENDING) code=READER_METADATA_OK;
  } else if(job_cancel_flag(job)) {
    reader_metadata_close(&owner,&error);return EXR_CANCELLED;
  } else {
    reader_group_kind kind=(reader_group_kind)v->group_kind;
    reader_group_command input={READER_COMMAND_PUT,kind,"",v->name,
      kind==READER_GROUP_SHELF && v->parent[0] ? v->parent:NULL,0};
    code=reader_metadata_prepare_group(owner,kind,"",&snapshot,&error);
    if(code==READER_METADATA_OK) code=reader_metadata_stage_group(owner,snapshot,&input,&result,&error);
    if(code==READER_METADATA_OK) code=reader_metadata_finish_pending(owner,&result,&error);
  }
  v->edit_committed=result.committed;v->edit_pending=result.pending;
  reader_metadata_snapshot_free(snapshot);
  if(reader_metadata_close(&owner,&error)!=READER_METADATA_OK && code==READER_METADATA_OK) code=error.code;
  if(code==READER_METADATA_OK) {
    copy_wstring(job->message,512,v->operation==WINIO_CREATE_GROUP ? L"分组已创建。":
      v->operation==WINIO_RECOVER_EDIT ? L"上次编辑已恢复或没有待恢复的编辑。":L"未提交的上次编辑已放弃或没有待处理编辑。");
    return EXR_OK;
  }
  copy_wstring(job->message,512,result.committed ? L"编辑已提交，但清理未完成；请使用恢复上次编辑。":
    result.pending ? L"编辑尚未完成；请使用恢复上次编辑。":L"无法创建或恢复分组，请检查名称及已有待处理操作。");
  return EXR_DATABASE;
}
static exr_status winio_bootstrap(reader_metadata_owner *owner,host_job *job) {
  winio_job *v=job->io;
  for(size_t i=0;i<v->count;i++) {
    if(job_cancel_flag(job)) return EXR_CANCELLED;
    reader_metadata_snapshot *snapshot=NULL;reader_metadata_error error={0};reader_metadata_result result={0};
    reader_metadata_status code=reader_metadata_prepare_book(owner,v->keys[i],&snapshot,&error);
    const reader_metadata_view *view=reader_metadata_snapshot_view(snapshot);
    exr_status status=EXR_OK;
    if(code==READER_METADATA_NEEDS_BOOTSTRAP && view && view->present && !view->deleted) {
      char hash[65];uint64_t bytes=0;exr_error sdk={0};
      EnterCriticalSection(&g.library_lock);
      status=reader_catalog_sdk_original_identity(g.library,v->ids[i],NULL,hash,&bytes,&sdk);
      LeaveCriticalSection(&g.library_lock);
      if(status==EXR_OK && (strcmp(hash,view->book.source_sha256) || bytes!=view->book.source_bytes)) status=EXR_DATABASE;
      if(status==EXR_OK) {
        reader_metadata_verified_source proof={view->book.format,hash,bytes};
        code=reader_metadata_stage_bootstrap(owner,snapshot,&proof,&result,&error);
        if(code==READER_METADATA_OK) code=reader_metadata_finish_pending(owner,&result,&error);
        if(result.committed) v->prepared++;
        v->bootstrap_pending=result.pending;
        if(code!=READER_METADATA_OK) status=EXR_DATABASE;
      }
    } else if(code!=READER_METADATA_OK && code!=READER_METADATA_CONFLICT && code!=READER_METADATA_NEEDS_BOOTSTRAP) status=EXR_DATABASE;
    reader_metadata_snapshot_free(snapshot);
    if(status!=EXR_OK) { v->bulk_error.metadata=error.code;return status; }
  }
  return EXR_OK;
}
static int winio_resume_local(void *context,const reader_catalog_row *row) {
  *(int64_t *)context=row->sdk_book_id;return 0;
}
static int winio_resume_pause(void *context) { (void)context;return 1; }
static int winio_open_action_owner(const char *product,reader_metadata_owner **owner,reader_metadata_error *error) {
  if(!g.product_profile_lock || g.product_profile_lock==INVALID_HANDLE_VALUE || !g.product_lock || g.product_lock==INVALID_HANDLE_VALUE) return 0;
  char *path=malloc(strlen(product)+40);if(!path) return 0;
  sprintf(path,"%s.bulk-action.pending",product);
  reader_metadata_status code=reader_metadata_open(product,path,owner,error);free(path);
  return code==READER_METADATA_OK;
}
static exr_status winio_original_selection(host_job *job,const char *product) {
  winio_job *v=job->io;reader_catalog *catalog=NULL;reader_catalog_error error={0};
  if(reader_catalog_open(product,&catalog,&error)) return EXR_DATABASE;
  v->count=0;int failed=0;
  for(size_t i=0;i<v->summary.total && i<READER_BULK_MAX_BATCH;i++) {
    if(v->results[i].outcome!=READER_BULK_ITEM_NOT_RUN) continue;
    size_t at=v->count++;snprintf(v->keys[at],sizeof(v->keys[at]),"%s",v->results[i].book_key);
    int found=0;
    if(reader_catalog_find(catalog,v->keys[at],NULL,winio_resume_local,&v->ids[at],&found,&error)) { failed=1;break; }
  }
  reader_catalog_close(&catalog,&error);return failed ? EXR_DATABASE:EXR_OK;
}
static reader_metadata_status winio_superseded_bootstrap(reader_metadata_owner *owner,host_job *job,size_t at,reader_metadata_error *error) {
  /* Explicit Resume may encounter a normal editor that already bootstrapped
     this legacy book. Never overwrite that history or discard committed
     cleanup. Prove safe current history AND retained original first; the
     public abandon operation independently rechecks the old ID is absent. */
  winio_job *v=job->io;reader_metadata_snapshot *snapshot=NULL;
  reader_metadata_status code=reader_metadata_prepare_book(owner,v->keys[at],&snapshot,error);
  const reader_metadata_view *view=reader_metadata_snapshot_view(snapshot);
  if(code==READER_METADATA_OK && view && view->present && !view->deleted && !view->needs_bootstrap && view->graph.projection_safe && view->graph.revisions && view->head_count) {
    char hash[65];uint64_t bytes=0;exr_error sdk={0};
    EnterCriticalSection(&g.library_lock);
    exr_status status=reader_catalog_sdk_original_identity(g.library,v->ids[at],NULL,hash,&bytes,&sdk);
    LeaveCriticalSection(&g.library_lock);
    if(status==EXR_OK && !strcmp(hash,view->book.source_sha256) && bytes==view->book.source_bytes)
      code=reader_metadata_abandon_pending(owner,error);
    else code=READER_METADATA_CONFLICT;
  } else if(code==READER_METADATA_OK) code=READER_METADATA_CONFLICT;
  reader_metadata_snapshot_free(snapshot);return code;
}
static exr_status winio_bootstrap_phase(host_job *job,const char *product) {
  winio_job *v=job->io;reader_metadata_owner *owner=NULL;reader_metadata_error error={0};reader_metadata_result pending={0};
  char *path=malloc(strlen(product)+40);if(!path) return EXR_MEMORY;
  sprintf(path,"%s.bulk-bootstrap.pending",product);
  /* The actual existing host process keeps product.profile.lock and
     <library>.product.lock open with share=0 from startup until shutdown.
     Sequential native owner reopens NEVER release those profile locks. */
  if(!g.product_profile_lock || g.product_profile_lock==INVALID_HANDLE_VALUE || !g.product_lock || g.product_lock==INVALID_HANDLE_VALUE) { free(path);return EXR_DATABASE; }
  reader_metadata_status code=reader_metadata_open(product,path,&owner,&error);free(path);
  if(code!=READER_METADATA_OK) { v->bulk_error.metadata=code;return EXR_DATABASE; }
  exr_status status=EXR_OK;
  code=reader_metadata_pending(owner,&pending,&error);
  if(code==READER_METADATA_OK) {
    /* This namespace is written ONLY by stage_bootstrap, never by J10 or the
       single-book editor. The unchanged J10 journal already owns the exact
       request, and only its remaining selected book can own this intent. */
    size_t at=0;while(at<v->count && strcmp(pending.command.entity_key,v->keys[at])) at++;
    if(at==v->count) status=EXR_DATABASE;
    else {
      char original[33];snprintf(original,sizeof(original),"%s",pending.command.revision_id);
      code=reader_metadata_finish_pending(owner,&pending,&error);
      if(pending.committed) v->prepared++;
      v->bootstrap_pending=pending.pending;
      if(code==READER_METADATA_CONFLICT && !pending.committed) {
        code=winio_superseded_bootstrap(owner,job,at,&error);
        if(code==READER_METADATA_OK) { snprintf(v->superseded_bootstrap,sizeof(v->superseded_bootstrap),"%s",original);v->bootstrap_pending=0; }
      }
      if(code!=READER_METADATA_OK) status=EXR_DATABASE;
    }
  } else if(code!=READER_METADATA_NO_PENDING) status=EXR_DATABASE;
  if(status==EXR_OK) status=winio_bootstrap(owner,job);
  reader_metadata_close(&owner,&error);return status;
}
static exr_status winio_bulk(host_job *job) {
  winio_job *v=job->io;reader_metadata_owner *owner=NULL;reader_metadata_error metadata={0};reader_bulk *bulk=NULL;
  char *product=host_utf8(g.product_path),*journal=NULL;exr_status status=EXR_DATABASE;
  if(!product) return EXR_MEMORY;
  journal=malloc(strlen(product)+32);if(!journal) { free(product);return EXR_MEMORY; }
  sprintf(journal,"%s.bulk.pending",product);
  if(!winio_open_action_owner(product,&owner,&metadata)) { v->bulk_status=READER_BULK_METADATA;v->bulk_error.metadata=metadata.code;goto done; }
  v->bulk_status=reader_bulk_open(owner,product,journal,&bulk,&v->bulk_error);
  if(v->bulk_status!=READER_BULK_OK) goto done;
  reader_bulk_control control={job,job_cancel_check,NULL},pause={NULL,winio_resume_pause,NULL};
  if(v->operation==WINIO_ACK) {
    v->bulk_status=reader_bulk_acknowledge(bulk,&v->bulk_error);
  } else if(v->operation==WINIO_INSPECT) {
    v->bulk_status=reader_bulk_inspect(bulk,v->results,READER_BULK_MAX_BATCH,&v->summary,&v->bulk_error);
  } else {
    if(v->operation==WINIO_RUN) {
      const char *keys[READER_BULK_MAX_BATCH];for(size_t i=0;i<v->count;i++) keys[i]=v->keys[i];
      reader_bulk_request request={0};request.struct_size=sizeof(request);request.action=(reader_bulk_action)v->action;
      request.group_id=v->group[0] ? v->group:NULL;request.book_keys=keys;request.book_count=v->count;request.control=pause;
      /* Persist the ORIGINAL request without executing any item. Thus even a
         kill in legacy preparation cannot lose the user's selected action. */
      v->bulk_status=reader_bulk_run(bulk,&request,v->results,READER_BULK_MAX_BATCH,&v->summary,&v->bulk_error);
    } else {
      /* Only J10 writes this action namespace. Editor/account intents remain
         in commands.pending, and can NEVER be adopted as a J10 receipt. */
      v->bulk_status=reader_bulk_resume(bulk,&pause,v->results,READER_BULK_MAX_BATCH,&v->summary,&v->bulk_error);
    }
    if(v->bulk_status!=READER_BULK_OK && v->bulk_status!=READER_BULK_CANCELLED) goto done;
    if(v->summary.complete) { status=EXR_OK;goto done; }
    if(job_cancel_flag(job)) { status=EXR_CANCELLED;goto done; }
    status=winio_original_selection(job,product);if(status!=EXR_OK) goto done;
    reader_bulk_close(&bulk,&v->bulk_error);reader_metadata_close(&owner,&metadata);
    /* Exactly one metadata owner at a time, on this one SDK/product worker. */
    status=winio_bootstrap_phase(job,product);
    if(status!=EXR_OK) { v->bulk_status=status==EXR_CANCELLED ? READER_BULK_CANCELLED:READER_BULK_METADATA;goto done; }
    if(!winio_open_action_owner(product,&owner,&metadata)) { status=EXR_DATABASE;v->bulk_status=READER_BULK_METADATA;goto done; }
    v->bulk_status=reader_bulk_open(owner,product,journal,&bulk,&v->bulk_error);
    if(v->bulk_status!=READER_BULK_OK) { status=EXR_DATABASE;goto done; }
    v->bulk_status=reader_bulk_resume(bulk,&control,v->results,READER_BULK_MAX_BATCH,&v->summary,&v->bulk_error);
  }
  status=(v->bulk_status==READER_BULK_OK || v->bulk_status==READER_BULK_NO_JOURNAL) ? EXR_OK:
    v->bulk_status==READER_BULK_CANCELLED ? EXR_CANCELLED:EXR_DATABASE;
done:
  if(bulk) reader_bulk_close(&bulk,&v->bulk_error);
  if(owner) reader_metadata_close(&owner,&metadata);
  free(product);free(journal);return status;
}
static exr_status winio_job_run(host_job *job) {
  winio_job *v=job->io;if(!v) return EXR_ARGUMENT;
  if(v->operation==WINIO_LIST || v->operation==WINIO_DOWNLOAD) {
    exr_status status=winio_network(job);
    if(!v->receipt_saved && winio_paths(job)) {
      if(v->operation==WINIO_LIST || (status!=EXR_OK && v->cloud_status==READER_CLOUD_OK)) {
        v->cloud_status=status==EXR_OK ? READER_CLOUD_OK:status==EXR_CANCELLED ? READER_CLOUD_CANCELLED:READER_CLOUD_REMOTE;
        v->cloud_error.webdav_code=v->dav_error.code;v->cloud_error.http_status=v->dav_error.http_status;
      }
      v->receipt_saved=winio_receipt(job);
    }
    return status;
  }
  if(v->operation==WINIO_IMPORT) return winio_import(job);
  if(v->operation==WINIO_CLEAN) {
    if(!winio_paths(job)) return EXR_IO;
    if(winio.retained) { v->imported=winio.retained_receipt;v->mapped=winio.retained_mapped; }
    v->staged=winio.retained;winio.retained=NULL;reader_cloud_staged_discard(&v->staged);
    if(!v->staged && winio.orphans) {
      winio.orphans=winio_staging_scan(1);
    }
    v->imported.staging_removed=v->staged==NULL && !winio.orphans;v->cloud_status=v->staged || winio.orphans ? READER_CLOUD_IO:READER_CLOUD_OK;
    v->receipt_saved=winio_receipt(job);return v->staged || winio.orphans ? EXR_IO:EXR_OK;
  }
  if(v->operation==WINIO_GROUPS) return winio_groups(job);
  if(v->operation==WINIO_CREATE_GROUP || v->operation==WINIO_RECOVER_EDIT || v->operation==WINIO_ABANDON_EDIT) return winio_group_edit(job);
  return winio_bulk(job);
}
