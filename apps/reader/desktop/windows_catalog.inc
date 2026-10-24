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
  if(!row->sdk_book_id) return 0;
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
static exr_status product_page_query(host_job *job,reader_catalog *catalog,reader_catalog_error *error) {
  job->product_books=calloc(50,sizeof(*job->product_books));job->product_cursors=calloc(50,sizeof(*job->product_cursors));
  if(!job->product_books || !job->product_cursors) return EXR_MEMORY;
  product_page_copy copy={job,0};int found=0,code=0,direction=job->product_shelf_direction<0 ? -1:1;
  const char *title=job->product_cursor_title,*key=job->product_cursor_key;
  if(job->product_anchor_key && job->product_anchor_key[0]) {
    code=reader_catalog_find(catalog,job->product_anchor_key,job->product_shelf_query,product_page_row,&copy,&found,error);
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
#include "windows_shelf.inc"
