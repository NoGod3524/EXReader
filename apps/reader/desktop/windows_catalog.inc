/* SPDX-License-Identifier: MIT
 * Host-only glue, included after host_job and the existing import worker.
 * Each temporary host worker owns its own catalog connection. */
typedef struct { host_job *job;int failed; } product_page_copy;
static exr_format product_format(const char *name) {
  static const char *names[]={"epub","pdf","cbz","txt","html","fb2","docx","rtf","mobi"};
  static const exr_format formats[]={EXR_EPUB,EXR_PDF,EXR_CBZ,EXR_TXT,EXR_HTML,EXR_FB2,EXR_DOCX,EXR_RTF,EXR_MOBI};
  for(size_t i=0;i<sizeof(names)/sizeof(names[0]);i++) if(!strcmp(name,names[i])) return formats[i];
  return EXR_CUSTOM;
}
static int product_page_row(void *context,const reader_catalog_row *row) {
  product_page_copy *copy=context;host_job *job=copy->job;
  if(job_cancel_flag(job)) return 1;
  if(job->product_book_count>=50) { copy->failed=1;return 1; }
  size_t i=job->product_book_count++;
  exr_book *book=&job->product_books[i];host_shelf_cursor *cursor=&job->product_cursors[i];
  book->id=row->sdk_book_id;book->format=product_format(row->format);book->favorite=row->favorite;
  book->title=host_strdup(row->title);book->author=host_strdup(row->author);
  cursor->key=host_strdup(row->book_key);cursor->sort_title=host_strdup(row->sort_title);
  if(!book->title || !book->author || !cursor->key || !cursor->sort_title) { copy->failed=1;return 1; }
  return 0;
}
static int product_page_exists(void *context,const reader_catalog_row *row) {
  (void)row;*(int *)context=1;return 1;
}
static int product_group_row(void *context,const reader_catalog_group_book_row *row) {
  product_page_copy *copy=context;size_t before=copy->job->product_book_count;
  int stopped=product_page_row(context,&row->book);
  if(copy->job->product_book_count>before) copy->job->product_cursors[before].ordinal=row->ordinal;
  return stopped;
}
static int product_group_exists(void *context,const reader_catalog_group_book_row *row) {
  (void)row;*(int *)context=1;return 1;
}
typedef struct { uint64_t ordinal;int active; } product_group_anchor;
static int product_group_anchor_copy(void *context,const reader_catalog_membership_row *row) {
  product_group_anchor *anchor=context;anchor->ordinal=row->ordinal;anchor->active=!row->group_deleted && !row->book_deleted;return 0;
}
static exr_status product_group_page(host_job *job,reader_catalog *catalog,reader_catalog_error *error) {
  product_page_copy copy={job,0};int found=0,code=0,direction=job->product_shelf_direction<0 ? -1:1;
  reader_catalog_group_kind kind=(reader_catalog_group_kind)job->product_group_kind;
  reader_catalog_member_cursor cursor={job->product_cursor_ordinal,job->product_cursor_key};
  const reader_catalog_member_cursor *after=job->product_cursor_key ? &cursor:NULL;
  if(job->product_anchor_key && job->product_anchor_key[0]) {
    product_group_anchor anchor={0};
    code=reader_catalog_membership_find(catalog,kind,job->product_group_id,job->product_anchor_key,
      product_group_anchor_copy,&anchor,&found,error);
    if(!code && found && anchor.active) {
      found=0;code=reader_catalog_local_find(catalog,job->product_anchor_key,job->product_shelf_query,product_page_row,&copy,&found,error);
      if(found && job->product_book_count && !copy.failed) {
        job->product_cursors[0].ordinal=anchor.ordinal;cursor.ordinal=anchor.ordinal;
        cursor.book_key=job->product_cursors[0].key;after=&cursor;
      }
    }
    direction=1;job->product_shelf_direction=0;
  }
  if(!code && !copy.failed && !job_cancel_flag(job)) code=reader_catalog_group_books_page(catalog,kind,
    job->product_group_id,after,job->product_shelf_query,1,direction,50-job->product_book_count,product_group_row,&copy,error);
  /* If the remembered member vanished at the tail, retain nearby predecessors. */
  if(!code && !copy.failed && !job_cancel_flag(job) && job->product_anchor_key && after && !job->product_book_count) {
    direction=-1;job->product_anchor_predecessor=1;
    code=reader_catalog_group_books_page(catalog,kind,job->product_group_id,after,job->product_shelf_query,1,-1,50,product_group_row,&copy,error);
  }
  if(job_cancel_flag(job)) return EXR_CANCELLED;
  if(copy.failed) return EXR_MEMORY;
  if(code) return EXR_DATABASE;
  if(direction<0) for(size_t i=0;i<job->product_book_count/2;i++) {
    size_t j=job->product_book_count-1-i;exr_book book=job->product_books[i];host_shelf_cursor saved=job->product_cursors[i];
    job->product_books[i]=job->product_books[j];job->product_cursors[i]=job->product_cursors[j];
    job->product_books[j]=book;job->product_cursors[j]=saved;
  }
  if(job->product_book_count) {
    host_shelf_cursor *first=&job->product_cursors[0],*last=&job->product_cursors[job->product_book_count-1];
    reader_catalog_member_cursor edge={first->ordinal,first->key};
    code=reader_catalog_group_books_page(catalog,kind,job->product_group_id,&edge,job->product_shelf_query,1,-1,1,
      product_group_exists,&job->product_shelf_before,error);
    edge.ordinal=last->ordinal;edge.book_key=last->key;
    if(!code) code=reader_catalog_group_books_page(catalog,kind,job->product_group_id,&edge,job->product_shelf_query,1,1,1,
      product_group_exists,&job->product_shelf_after,error);
  }
  return code ? EXR_DATABASE:job_cancel_flag(job) ? EXR_CANCELLED:EXR_OK;
}
static exr_status product_page_query(host_job *job,reader_catalog *catalog,reader_catalog_error *error) {
  job->product_books=calloc(50,sizeof(*job->product_books));job->product_cursors=calloc(50,sizeof(*job->product_cursors));
  if(!job->product_books || !job->product_cursors) return EXR_MEMORY;
  if(job->product_group_id[0]) return product_group_page(job,catalog,error);
  product_page_copy copy={job,0};int found=0,code=0,direction=job->product_shelf_direction<0 ? -1:1;
  const char *title=job->product_cursor_title,*key=job->product_cursor_key;
  if(job->product_anchor_key && job->product_anchor_key[0]) {
    code=reader_catalog_local_find(catalog,job->product_anchor_key,job->product_shelf_query,product_page_row,&copy,&found,error);
    if(found && job->product_book_count && !copy.failed) { title=job->product_cursors[0].sort_title;key=job->product_cursors[0].key; }
    else title=key=NULL;
    direction=1;job->product_shelf_direction=0;
  }
  if(!code && !copy.failed && !job_cancel_flag(job)) code=reader_catalog_local_page(catalog,title,key,
    job->product_shelf_query,direction,50-job->product_book_count,product_page_row,&copy,error);
  if(job_cancel_flag(job)) return EXR_CANCELLED;
  if(copy.failed) return EXR_MEMORY;
  if(code) return EXR_DATABASE;
  if(direction<0) for(size_t i=0;i<job->product_book_count/2;i++) {
    size_t j=job->product_book_count-1-i;exr_book book=job->product_books[i];host_shelf_cursor cursor=job->product_cursors[i];
    job->product_books[i]=job->product_books[j];job->product_books[j]=book;
    job->product_cursors[i]=job->product_cursors[j];job->product_cursors[j]=cursor;
  }
  if(job->product_book_count) {
    host_shelf_cursor *first=&job->product_cursors[0],*last=&job->product_cursors[job->product_book_count-1];
    code=reader_catalog_local_page(catalog,first->sort_title,first->key,job->product_shelf_query,-1,1,
      product_page_exists,&job->product_shelf_before,error);
    if(!code) code=reader_catalog_local_page(catalog,last->sort_title,last->key,job->product_shelf_query,1,1,
      product_page_exists,&job->product_shelf_after,error);
  }
  return code ? EXR_DATABASE:job_cancel_flag(job) ? EXR_CANCELLED:EXR_OK;
}
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
#ifdef EXR_READER_WINDOWS_TXT_RECOVERY
  if(job->kind==JOB_PRODUCT_REPAIR) {
    char *root=NULL;
    reader_original_status recovered=ROI_IO;
    if(CreateDirectoryW(g.original_root,NULL) || GetLastError()==ERROR_ALREADY_EXISTS) {
      root=host_utf8(g.original_root);
      if(root) recovered=reader_original_recover(catalog,root);
    }
    free(root);
    if(recovered!=ROI_OK) {
      job->error.code=EXR_IO;
      snprintf(job->error.message,sizeof(job->error.message),"Original recovery failed (%d)",(int)recovered);
      reader_catalog_close(&catalog,&product_error);
      return EXR_IO;
    }
  }
#endif
  if(job->kind==JOB_PRODUCT_SHELF) status=product_page_query(job,catalog,&product_error);
  else if(job->kind==JOB_PRODUCT_DELETE) {
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
      } else status=reader_catalog_sdk_attach(catalog,g.library,&books[at],&control,job->product_key,&job->error);
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
#ifdef EXR_READER_WINDOWS_TXT_RECOVERY
/* Runs on the same serialized host worker as catalog repair. Hold the picked
   file against writes and replacement while the original importer hashes and
   copies it; the importer independently rejects links and reparse points. */
static exr_status product_import_original(host_job *job) {
  wchar_t directory[HOST_PATH], *base, *slash;
  HANDLE source=INVALID_HANDLE_VALUE;
  LARGE_INTEGER length;
  char *root=NULL,*dir=NULL,*name=NULL,*catalog_path=NULL;
  reader_catalog *catalog=NULL;
  reader_catalog_error error={0};
  reader_original_status result=ROI_IO, recovered=ROI_OK;
  reader_original_callbacks callbacks={job,job_cancel_check,NULL};
  exr_status status=EXR_IO;
  job->original_import=1;
  if(!g.product_ready || g.product_pending) {
    copy_wstring(job->message,512,L"书目恢复尚未完成，暂不能导入 TXT。");
    return EXR_IO;
  }
  copy_wstring(directory,HOST_PATH,job->path);
  slash=wcsrchr(directory,L'\\');
  if(!slash) slash=wcsrchr(directory,L'/');
  if(!slash || slash<=directory+2 || !slash[1]) return EXR_ARGUMENT;
  base=slash+1;
  name=host_utf8(base);
  *slash=0;
  dir=host_utf8(directory);root=host_utf8(g.original_root);catalog_path=host_utf8(g.product_path);
  if(!name || !dir || !root || !catalog_path) { status=EXR_MEMORY;goto done; }
  source=CreateFileW(job->path,GENERIC_READ,FILE_SHARE_READ,NULL,OPEN_EXISTING,FILE_FLAG_OPEN_REPARSE_POINT,NULL);
  if(source==INVALID_HANDLE_VALUE || !GetFileSizeEx(source,&length)) goto done;
  if(length.QuadPart<=0) { status=EXR_FORMAT;goto done; }
  if((uint64_t)length.QuadPart>HOST_IMPORT_LIMIT) { status=EXR_LIMIT;goto done; }
  if(reader_catalog_open(catalog_path,&catalog,&error)) { status=EXR_DATABASE;goto done; }
  result=reader_original_import(catalog,root,dir,name,name,"",name,&callbacks,job->product_key);
  if(result!=ROI_OK && result!=ROI_DUPLICATE) {
    /* The importer intentionally leaves staged work for owner recovery. */
    recovered=reader_original_recover(catalog,root);
    if(recovered!=ROI_OK) { job->original_recovery_failed=1;status=EXR_IO; }
    else if(result==ROI_CANCELLED) status=EXR_CANCELLED;
    else if(result==ROI_MEMORY) status=EXR_MEMORY;
    else if(result==ROI_ARGUMENT) status=EXR_ARGUMENT;
    else if(result==ROI_CATALOG) status=EXR_DATABASE;
    else status=EXR_IO;
  } else {
    job->created=result==ROI_OK;
    status=EXR_OK;
  }
done:
  if(catalog && reader_catalog_close(&catalog,&error) && status==EXR_OK) {
    job->original_recovery_failed=1;status=EXR_DATABASE;
  }
  if(source!=INVALID_HANDLE_VALUE) CloseHandle(source);
  free(root);free(dir);free(name);free(catalog_path);
  return status;
}
#endif
#include "windows_shelf.inc"
