/* SPDX-License-Identifier: MIT */
/* Public revision projection and SDK import stay on the existing SDK owner. */
typedef struct { char *key;reader_revision_info info;reader_revision_selection selection; } received_book;
typedef struct {
  reader_revisions *revisions;
  char *home,*cache,*imports,*cursor;
  received_book page[50];size_t count,index;
  reader_received_conflict conflicts[50];size_t conflict_count;
  uint64_t seen,projected,conflicted,waiting;
  int scanning,conflicts_only,conflict_more;
} received_owner;

static void received_conflict_clear(reader_received_conflict *row) {
  g_free(row->key);g_free(row->title);g_free(row->heads);memset(row,0,sizeof(*row));
}
static void received_page_clear(received_owner *owner) {
  for(size_t i=0;i<owner->count;i++) g_free(owner->page[i].key);
  memset(owner->page,0,sizeof(owner->page));owner->count=owner->index=0;
}
static void received_conflicts_clear(received_owner *owner) {
  for(size_t i=0;i<owner->conflict_count;i++) received_conflict_clear(&owner->conflicts[i]);
  owner->conflict_count=0;
}
static void received_free(linux_reader *reader) {
  received_owner *owner=reader->received_data;if(!owner) return;
  received_page_clear(owner);received_conflicts_clear(owner);
  reader_revisions_close(&owner->revisions,NULL);
  g_free(owner->home);g_free(owner->cache);g_free(owner->imports);g_free(owner->cursor);free(owner);reader->received_data=NULL;
}
static exr_status received_ready(linux_reader *reader,received_owner **out) {
  received_owner *owner=reader->received_data;
  if(!owner) {
    owner=calloc(1,sizeof(*owner));if(!owner) return EXR_MEMORY;
    owner->home=g_path_get_dirname(reader->catalog_path);owner->cache=g_build_filename(owner->home,"sync-work",NULL);
    owner->imports=g_build_filename(owner->home,"sync-imports",NULL);reader->received_data=owner;
  }
  if(!owner->revisions && reader_revisions_open(reader->catalog_path,&owner->revisions,NULL)!=READER_REV_OK) return EXR_DATABASE;
  *out=owner;return EXR_OK;
}
static void received_annotate_shelf(linux_reader *reader,reader_result *result) {
  if(!result->cursors) return;
  received_owner *owner=NULL;if(received_ready(reader,&owner)!=EXR_OK) return;
  for(size_t i=0;i<result->book_count;i++) {
    reader_revision_state graph={0};reader_shelf_cursor *cursor=&result->cursors[i];
    if(reader_revision_heads(owner->revisions,"book",cursor->key,NULL,NULL,&graph,NULL)!=READER_REV_OK) {
      cursor->receive_kind=READER_SELECTION_PENDING_PARENTS;continue;
    }
    cursor->receive_heads=graph.heads;
    if(graph.revisions && (!graph.projection_safe || graph.deleted)) cursor->receive_kind=
      graph.heads>1 ? READER_SELECTION_CONCURRENT:READER_SELECTION_BLOCKED_RESTORE;
  }
}
static int received_copy_book(void *opaque,const reader_revision_entity_row *row) {
  received_owner *owner=opaque;if(owner->count>=50) return 1;
  received_book *book=&owner->page[owner->count++];book->key=g_strdup(row->entity_key);
  book->info=row->info;book->selection=row->selection;return 0;
}
typedef struct { GString *ids;size_t count; } received_heads;
static int received_copy_head(void *opaque,const reader_revision_head *head) {
  received_heads *copy=opaque;if(copy->count==32) return 1;
  if(copy->count++) g_string_append_c(copy->ids,',');
  g_string_append(copy->ids,head->revision_id);return 0;
}
static int received_copy_title(void *opaque,const reader_catalog_row *row) {
  char **title=opaque;*title=g_strdup(row->title);return 0;
}
typedef struct {const char *title;char *sort;} received_sort;
static int received_copy_sort(void *opaque,const reader_catalog_row *row) {
  received_sort *copy=opaque;
  if(!strcmp(copy->title,row->title)) copy->sort=g_strdup(row->sort_title);
  return 0;
}
static char *received_sort_title(linux_reader *reader,const char *key,const char *title) {
  /* An unchanged title retains the host's existing NFC sort key, including
     its legacy bootstrap key. New titles use the ordinary NFC conversion. */
  received_sort copy={title,NULL};int found=0;
  if(reader_catalog_metadata(reader->catalog,key,received_copy_sort,&copy,&found,NULL)!=0) return NULL;
  return copy.sort ? copy.sort:g_utf8_normalize(title,-1,G_NORMALIZE_DEFAULT_COMPOSE);
}
static exr_status received_add_conflict(linux_reader *reader,received_owner *owner,const received_book *book) {
  if(owner->conflict_count==50) { owner->conflict_more=1;return EXR_OK; }
  reader_received_conflict *row=&owner->conflicts[owner->conflict_count];row->key=g_strdup(book->key);
  int found=0;reader_catalog_metadata(reader->catalog,book->key,received_copy_title,&row->title,&found,NULL);
  received_heads heads={g_string_new(NULL),0};reader_revision_state graph={0};
  reader_revision_status code=reader_revision_heads(owner->revisions,"book",book->key,received_copy_head,&heads,&graph,NULL);
  row->heads=g_string_free(heads.ids,FALSE);row->head_count=graph.heads;row->kind=(int)book->selection.kind;
  if(code!=READER_REV_OK) { received_conflict_clear(row);return EXR_DATABASE; }
  if(!row->title) {
    GString *names=g_string_new(NULL);char **ids=g_strsplit(row->heads,",",32);
    for(size_t i=0;ids[i];i++) {
      char *title=NULL;
      if(reader_revision_book_title(owner->revisions,ids[i],&title,NULL)==READER_REV_OK) {
        char *short_title=g_utf8_substring(title,0,MIN((glong)120,g_utf8_strlen(title,-1)));
        if(names->len) g_string_append(names," / ");
        g_string_append(names,short_title);g_free(short_title);
      }
      reader_revision_bytes_free(title);
    }
    g_strfreev(ids);row->title=g_string_free(names,FALSE);
    if(!row->title[0]) { g_free(row->title);row->title=g_strdup("Book versions need attention"); }
  }
  owner->conflict_count++;return EXR_OK;
}
static exr_status received_project_one(linux_reader *reader,received_owner *owner,const received_book *book) {
  if(book->selection.kind!=READER_SELECTION_SAFE) {
    owner->conflicted++;return received_add_conflict(reader,owner,book);
  }
  if(owner->conflicts_only) return EXR_OK;
  char *title=NULL,*sort=NULL;reader_revision_status code=READER_REV_OK;
  if(!book->selection.graph.deleted) {
    code=reader_revision_book_title(owner->revisions,book->info.revision_id,&title,NULL);
    if(code==READER_REV_OK) { sort=received_sort_title(reader,book->key,title);if(!sort) code=READER_REV_FORMAT; }
  }
  if(code==READER_REV_OK) code=reader_revision_project(owner->revisions,"book",book->key,book->info.revision_id,sort,NULL,NULL);
  reader_revision_bytes_free(title);g_free(sort);
  if(code==READER_REV_OK) { owner->projected++;return EXR_OK; }
  if(code==READER_REV_UNSAFE || code==READER_REV_NOT_FOUND || code==READER_REV_MISSING_PARENT) { owner->waiting++;return EXR_OK; }
  return EXR_DATABASE;
}
static exr_status received_copy_conflicts(received_owner *owner,reader_result *result) {
  result->receive_conflict_more=owner->conflict_more;
  if(!owner->conflict_count) return EXR_OK;
  result->receive_conflicts=calloc(owner->conflict_count,sizeof(*result->receive_conflicts));if(!result->receive_conflicts) return EXR_MEMORY;
  result->receive_conflict_count=owner->conflict_count;
  for(size_t i=0;i<owner->conflict_count;i++) {
    reader_received_conflict *to=&result->receive_conflicts[i],*from=&owner->conflicts[i];
    to->key=g_strdup(from->key);to->title=g_strdup(from->title);to->heads=g_strdup(from->heads);
    to->head_count=from->head_count;to->kind=from->kind;
  }
  return EXR_OK;
}
static exr_status received_project(linux_reader *reader,received_owner *owner,const reader_command *command,reader_result *result) {
  account_control control={reader,command->account_control};exr_status status=EXR_OK;
  int begin=command->action==READER_RECEIVE_BEGIN || command->action==READER_RECEIVE_CONFLICTS_BEGIN;
  result->receive_response=command->action>=READER_RECEIVE_CONFLICTS_BEGIN ? 7:5;
  if(begin) {
    status=accounts_pending(reader,result);if(status!=EXR_OK) return status;
    received_page_clear(owner);received_conflicts_clear(owner);g_free(owner->cursor);
    owner->cursor=command->receive_key && command->receive_key[0] ? g_strdup(command->receive_key):NULL;
    owner->seen=owner->projected=owner->conflicted=owner->waiting=0;owner->conflict_more=0;owner->scanning=1;
    owner->conflicts_only=command->action==READER_RECEIVE_CONFLICTS_BEGIN;
  }
  if(!owner->scanning) return EXR_ARGUMENT;
  if(accounts_cancelled(&control)) { owner->scanning=0;return EXR_CANCELLED; }
  if(owner->index==owner->count) {
    received_page_clear(owner);
    if(reader_revision_entities_page(owner->revisions,"book",owner->cursor,1,50,received_copy_book,owner,NULL)!=READER_REV_OK) {
      owner->scanning=0;return EXR_DATABASE;
    }
    if(!owner->count) owner->scanning=0;
  }
  if(owner->scanning) {
    received_book *book=&owner->page[owner->index++];owner->seen++;
    status=accounts_pending(reader,result);
    if(status==EXR_OK) status=received_project_one(reader,owner,book);
    g_free(owner->cursor);owner->cursor=g_strdup(book->key);
    if(status!=EXR_OK || (owner->index==owner->count && owner->count<50)) owner->scanning=0;
    if(owner->conflicts_only && owner->conflict_count==50) { owner->conflict_more=1;owner->scanning=0; }
  }
  result->receive_seen=owner->seen;result->receive_projected=owner->projected;
  result->receive_conflicted=owner->conflicted;result->receive_waiting=owner->waiting;
  result->receive_more=owner->scanning;result->receive_page_rows=owner->count;
  if(!owner->scanning && status==EXR_OK) status=received_copy_conflicts(owner,result);
  return status;
}
static int received_format(const char *key,exr_format *format,const char **hash) {
  static const struct {const char *name;exr_format value;} formats[]={
    {"txt",EXR_TXT},{"html",EXR_HTML},{"fb2",EXR_FB2},{"epub",EXR_EPUB},{"docx",EXR_DOCX},
    {"rtf",EXR_RTF},{"mobi",EXR_MOBI},{"pdf",EXR_PDF},{"cbz",EXR_CBZ}};
  if(!key) return 0;
  for(size_t i=0;i<G_N_ELEMENTS(formats);i++) {
    size_t size=strlen(formats[i].name);
    if(!strncmp(key,formats[i].name,size) && key[size]==':' && strlen(key+size+1)==64) {
      *hash=key+size+1;*format=formats[i].value;
      for(size_t n=0;n<64;n++) if(!g_ascii_isdigit((*hash)[n]) && !((*hash)[n]>='a' && (*hash)[n]<='f')) return 0;
      return 1;
    }
  }
  return 0;
}
static int received_same_file(const struct stat *a,const struct stat *b) {
  return a->st_dev==b->st_dev && a->st_ino==b->st_ino && a->st_size==b->st_size && a->st_nlink==b->st_nlink &&
    a->st_mtim.tv_sec==b->st_mtim.tv_sec && a->st_mtim.tv_nsec==b->st_mtim.tv_nsec &&
    a->st_ctim.tv_sec==b->st_ctim.tv_sec && a->st_ctim.tv_nsec==b->st_ctim.tv_nsec;
}
static exr_status received_snapshot(received_owner *owner,const char *key,const char *hash,uint64_t bytes,
    account_control *control,char **snapshot,int *missing) {
  *snapshot=NULL;*missing=0;const char *colon=strchr(key,':');char leaf[80];
  snprintf(leaf,sizeof(leaf),"%s.%.*s",hash,(int)(colon-key),key);
  char *cache=g_build_filename(owner->cache,leaf,NULL);int source=open(cache,O_RDONLY|O_CLOEXEC|O_NOFOLLOW),output=-1;
  exr_status status=EXR_DATABASE;GChecksum *sum=NULL;char *temporary=NULL;struct stat before,after,path_info;uint64_t total=0;
  if(source<0) { if(errno==ENOENT) { *missing=1;status=EXR_OK; }else status=EXR_IO;goto done; }
  if(!accounts_private_directory(owner->home,0) || !accounts_private_directory(owner->cache,0) ||
     !accounts_private_directory(owner->imports,1) || fstat(source,&before)<0 || !accounts_private_file(&before) ||
     before.st_size<0 || (uint64_t)before.st_size!=bytes || bytes>EXR_SIDELOAD_STREAM_LIMIT) goto done;
  temporary=g_build_filename(owner->imports,".reader-import-XXXXXX",NULL);
  output=g_mkstemp_full(temporary,O_RDWR|O_CLOEXEC,0600);if(output<0) { status=EXR_IO;goto done; }
  sum=g_checksum_new(G_CHECKSUM_SHA256);if(!sum) { status=EXR_MEMORY;goto done; }
  unsigned char buffer[65536];
  for(;;) {
    if(accounts_cancelled(control)) { status=EXR_CANCELLED;goto done; }
    ssize_t got=read(source,buffer,sizeof(buffer));if(got<0 && errno==EINTR) continue;
    if(got<0) { status=EXR_IO;goto done; }if(!got) break;
    total+=(uint64_t)got;if(total>bytes) goto done;
    g_checksum_update(sum,buffer,(gssize)got);size_t at=0;
    while(at<(size_t)got) {
      ssize_t wrote=write(output,buffer+at,(size_t)got-at);if(wrote<0 && errno==EINTR) continue;
      if(wrote<=0) { status=EXR_IO;goto done; }at+=(size_t)wrote;
    }
    accounts_progress(control,EXR_STAGE_READ,total,bytes);
  }
  if(fstat(source,&after)<0 || lstat(cache,&path_info)<0 || !accounts_private_file(&path_info) ||
     !received_same_file(&before,&after) || !received_same_file(&after,&path_info) || total!=bytes ||
     strcmp(g_checksum_get_string(sum),hash)) goto done;
  if(fsync(output)) { status=EXR_IO;goto done; }
  if(close(output)) { output=-1;status=EXR_IO;goto done; }output=-1;
  *snapshot=temporary;temporary=NULL;status=EXR_OK;
done:
  if(sum) g_checksum_free(sum);
  if(source>=0) close(source);
  if(output>=0) close(output);
  if(temporary) { unlink(temporary);g_free(temporary); }
  g_free(cache);return status;
}
/* Resolve on fresh public SDK readers, without copying product annotations into
   SDK notes or changing either the current frame or its persisted progress. */
static exr_status received_resolve_one(linux_reader *reader,received_owner *owner,const char *key,
    int64_t book,exr_format format,uint64_t source_bytes,const char *revision,const char *wire,size_t bytes,
    account_control *control,reader_result *result,GString *matches) {
  if(accounts_cancelled(control)) return EXR_CANCELLED;
  reader_rs_record record={0};reader_rs_error error={0};exr_anchor_match match={0};size_t part=SIZE_MAX,page=SIZE_MAX;
  reader_rs_status status=reader_rs_decode(owner->revisions,wire,bytes,&record,&error);
  if(status==READER_RS_OK && !record.has_location) { reader_rs_record_free(&record);return EXR_OK; }
  exr_control sdk_control={accounts_cancelled,accounts_progress,control};
  if(status==READER_RS_OK && strcmp(record.book_key,key)) status=READER_RS_IDENTITY;
  if(status==READER_RS_OK && record.mode==READER_RS_EPUB_CHAPTER) {
    exr_source source={0};exr_publication *publication=NULL;exr_pager *pager=NULL;exr_error sdk_error={0};
    exr_status sdk=exr_library_source(reader->library,book,&source,&sdk_error);
    if(sdk==EXR_OK) {
      source.control=sdk_control;sdk=exr_publication_open_source(&source,&publication,&sdk_error);
      if(sdk!=EXR_OK && source.release) source.release(source.context);
    }
    status=sdk==EXR_OK ? reader_rs_epub_record_part(publication,&record,&part,&error):READER_RS_SDK;
    if(status==READER_RS_OK) {
      exr_layout_config layout=exr_layout_config_defaults();exr_chapter_options options=exr_chapter_options_defaults();
      sdk=exr_publication_pager_create(publication,part,reader->font,&layout,&options,&pager,&sdk_error);
      status=sdk==EXR_OK ? reader_rs_resolve_epub(publication,pager,part,&record,&sdk_control,&match,&error):READER_RS_SDK;
    }
    exr_pager_free(pager);exr_publication_free(publication);
  } else if(status==READER_RS_OK && record.mode==READER_RS_FIXED_PAGE) {
    exr_fixed_document *document=NULL;exr_fixed_open_options options={0};exr_error sdk_error={0};options.struct_size=sizeof(options);
    options.control=sdk_control;options.fallback_font=reader->font;
    exr_status sdk=exr_library_fixed_source(reader->library,book,&options,&document,&sdk_error);
    status=sdk==EXR_OK ? reader_rs_resolve_fixed(document,&record,&sdk_control,&page,&match,&error):READER_RS_SDK;
    exr_fixed_free(document);
  } else if(status==READER_RS_OK && record.mode==READER_RS_REFLOW_GLOBAL) {
    /* Global legacy projections are a bounded compatibility path. Large EPUB
       histories stay unresolved rather than forcing a whole-book allocation. */
    if(source_bytes>EXR_SIDELOAD_MEMORY_LIMIT) status=READER_RS_UNRESOLVED;
    else {
      exr_document *document=NULL;exr_error sdk_error={0};
      exr_status sdk=exr_library_document(reader->library,book,&document,&sdk_error);
      status=sdk==EXR_OK ? reader_rs_resolve_reflow(document,&record,&sdk_control,&match,&error):READER_RS_SDK;
      exr_document_free(document);
    }
  } else if(status==READER_RS_OK) status=READER_RS_IDENTITY;
  (void)format;
  result->receive_reading_rows++;
  if(status==READER_RS_OK && match.state==EXR_ANCHOR_FOUND) result->receive_reading_found++;
  else result->receive_reading_unresolved++;
  if(matches->len) g_string_append_c(matches,';');
  g_string_append_printf(matches,"%s|%d|%d|%zu|%zu|%zu|%zu",revision,(int)status,(int)match.state,part,page,match.start,match.end);
  reader_rs_record_free(&record);return accounts_cancelled(control) ? EXR_CANCELLED:EXR_OK;
}
typedef struct {int found,safe;char annotation[33],revision[33];char *wire;size_t bytes;} received_annotation;
static int received_copy_annotation(void *opaque,const reader_revision_annotation_row *row) {
  received_annotation *copy=opaque;copy->found=1;
  g_strlcpy(copy->annotation,row->annotation_id,sizeof(copy->annotation));
  copy->safe=row->selection.kind==READER_SELECTION_SAFE;
  if(copy->safe && row->wire) {
    g_strlcpy(copy->revision,row->info.revision_id,sizeof(copy->revision));copy->bytes=row->info.bytes;
    copy->wire=g_strndup(row->wire,copy->bytes);
  }
  return 0;
}
static exr_status received_resolve(linux_reader *reader,received_owner *owner,const char *key,int64_t book,
    exr_format format,uint64_t source_bytes,account_control *control,reader_result *result) {
  char *wire=NULL;size_t bytes=0;reader_revision_info info={0};reader_revision_selection selected={0};
  GString *matches=g_string_new(NULL);exr_status status=EXR_OK;
  reader_revision_status code=reader_revision_selected(owner->revisions,"progress",key,&wire,&bytes,&info,&selected,NULL);
  if(code==READER_REV_OK) status=received_resolve_one(reader,owner,key,book,format,source_bytes,info.revision_id,wire,bytes,control,result,matches);
  else if(code!=READER_REV_NOT_FOUND && code!=READER_REV_UNSAFE) status=EXR_DATABASE;
  reader_revision_bytes_free(wire);
  char after[33]={0};size_t count=0;
  while(status==EXR_OK && count<100) {
    if(accounts_cancelled(control)) { status=EXR_CANCELLED;break; }
    received_annotation copy={0};
    code=reader_revision_annotations_page(owner->revisions,key,after[0] ? after:NULL,1,1,received_copy_annotation,&copy,NULL);
    if(code!=READER_REV_OK) { g_free(copy.wire);status=EXR_DATABASE;break; }
    if(!copy.found) break;
    count++;g_strlcpy(after,copy.annotation,sizeof(after));
    if(copy.safe && copy.wire) status=received_resolve_one(reader,owner,key,book,format,source_bytes,
      copy.revision,copy.wire,copy.bytes,control,result,matches);
    else { result->receive_reading_rows++;result->receive_reading_unresolved++; }
    g_free(copy.wire);
  }
  if(status==EXR_OK && count==100) {
    received_annotation extra={0};
    code=reader_revision_annotations_page(owner->revisions,key,after,1,1,received_copy_annotation,&extra,NULL);
    if(code!=READER_REV_OK) status=EXR_DATABASE;
    else result->receive_reading_more=extra.found;
    g_free(extra.wire);
  }
  result->receive_resolutions=g_string_free(matches,FALSE);return status;
}
static exr_status received_open(linux_reader *reader,received_owner *owner,const reader_command *command,reader_result *result) {
  result->receive_response=6;account_control control={reader,command->account_control};
  exr_status status=accounts_pending(reader,result);if(status!=EXR_OK) return status;
  exr_format format;const char *hash=NULL;
  if(!received_format(command->receive_key,&format,&hash)) return EXR_ARGUMENT;
  char *wire=NULL,*title=NULL,*sort=NULL,*snapshot=NULL;size_t size=0;
  reader_revision_info info={0};reader_revision_selection selected={0};
  reader_revision_status code=reader_revision_selected(owner->revisions,"book",command->receive_key,&wire,&size,&info,&selected,NULL);
  reader_revision_bytes_free(wire);wire=NULL;
  if(code!=READER_REV_OK || selected.kind!=READER_SELECTION_SAFE || selected.graph.deleted) {
    snprintf(result->message,sizeof(result->message),"This book has unresolved versions. Sync or review its versions before opening");return EXR_ARGUMENT;
  }
  if(strcmp(info.book_key,command->receive_key) || !info.source_bytes || info.source_bytes>EXR_SIDELOAD_STREAM_LIMIT) return EXR_ARGUMENT;
  code=reader_revision_book_title(owner->revisions,info.revision_id,&title,NULL);
  if(code==READER_REV_OK) { sort=received_sort_title(reader,command->receive_key,title);if(!sort) code=READER_REV_FORMAT; }
  if(code==READER_REV_OK) code=reader_revision_project(owner->revisions,"book",command->receive_key,info.revision_id,sort,NULL,NULL);
  g_free(sort);sort=NULL;
  if(code!=READER_REV_OK) { status=EXR_DATABASE;goto done; }
  int missing=0;status=received_snapshot(owner,command->receive_key,hash,info.source_bytes,&control,&snapshot,&missing);
  if(missing) { result->receive_needs_download=1;goto done; }
  if(status!=EXR_OK) goto done;
  exr_sideload_options options={sizeof(options),info.source_bytes,{accounts_cancelled,accounts_progress,&control}};
  exr_sideload_result imported={0};imported.struct_size=sizeof(imported);exr_error error={0};
  reader_import_saved saved={0};status=reader_import_suspend(reader,&saved);
  if(status==EXR_OK) {
    status=exr_sideload_import_file(reader->library,format,snapshot,title,&options,&imported,&error);
    reader_import_resume(reader,&saved,result);
  }
  if(status!=EXR_OK) goto done;
  result->receive_book=imported.book_id;result->receive_created=imported.created;
  /* The SDK commit is retained even when the device-local mapping fails.
     Finish verification/attach without turning a late cancellation into deletion. */
  exr_control committed={NULL,accounts_progress,&control};char actual[65],attached[READER_BOOK_KEY_CAPACITY];uint64_t bytes=0;
  status=reader_catalog_sdk_original_identity(reader->library,imported.book_id,&committed,actual,&bytes,&error);
  if(status==EXR_OK && (strcmp(actual,hash) || bytes!=info.source_bytes)) status=EXR_DATABASE;
  exr_book book={0};book.id=imported.book_id;book.format=format;book.title=title;book.author="";
  if(status==EXR_OK) status=reader_catalog_sdk_attach(reader->catalog,reader->library,&book,&committed,attached,&error);
  if(status==EXR_OK && strcmp(attached,command->receive_key)) status=EXR_DATABASE;
  if(status!=EXR_OK) {
    result->receive_pending=1;snprintf(result->message,sizeof(result->message),"The book was saved. Updating this device's shelf is pending; Retry keeps the saved book");goto done;
  }
  reader_revision_info current={0};reader_revision_selection now={0};
  code=reader_revision_selected(owner->revisions,"book",command->receive_key,&wire,&size,&current,&now,NULL);
  reader_revision_bytes_free(wire);wire=NULL;
  if(code!=READER_REV_OK || now.kind!=READER_SELECTION_SAFE || now.graph.deleted || strcmp(current.revision_id,info.revision_id)) {
    status=EXR_ARGUMENT;snprintf(result->message,sizeof(result->message),"Book versions changed. The saved file was kept; sync before opening");
  }
  if(status==EXR_OK) status=received_resolve(reader,owner,command->receive_key,imported.book_id,format,info.source_bytes,&control,result);
done:
  reader_revision_bytes_free(title);g_free(sort);
  if(snapshot) { unlink(snapshot);g_free(snapshot); }
  if(status!=EXR_OK && !result->message[0]) snprintf(result->message,sizeof(result->message),"%s",
    status==EXR_CANCELLED ? "Opening cancelled; saved library data was kept":"The book file could not be verified or added. Saved books were kept");
  return status;
}
static void received_execute(linux_reader *reader,const reader_command *command,reader_result *result) {
  result->receive_response=command->action==READER_RECEIVE_OPEN ? 6:
    command->action>=READER_RECEIVE_CONFLICTS_BEGIN ? 7:5;
  received_owner *owner=NULL;result->status=received_ready(reader,&owner);
  if(result->status!=EXR_OK) return;
  if(command->action==READER_RECEIVE_OPEN) result->status=received_open(reader,owner,command,result);
  else result->status=received_project(reader,owner,command,result);
  if(result->status!=EXR_OK && !result->message[0]) snprintf(result->message,sizeof(result->message),"Library update could not finish. Received versions were kept for Retry");
}
