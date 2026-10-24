/* SPDX-License-Identifier: MIT */
/* Included on the original SDK worker. G03/G04 borrow received_owner.revisions.
   The profile's existing lifetime flock serializes windows and processes. */
#include <reader_commands.h>
#define RECORDS_PENDING_LIMIT (2u*1024u*1024u)
typedef struct { char ids[32][33];size_t count;int overflow; } records_heads;
typedef struct {
  char *key,*format,*title,*author,*sort;uint64_t bytes;int favorite,deleted;int64_t sdk_id;
} records_book;
static void records_book_free(records_book *book) {
  g_free(book->key);g_free(book->format);g_free(book->title);g_free(book->author);g_free(book->sort);memset(book,0,sizeof(*book));
}
static int records_book_copy(void *opaque,const reader_catalog_row *row) {
  records_book *book=opaque;book->key=g_strdup(row->book_key);book->format=g_strdup(row->format);
  book->title=g_strdup(row->title);book->author=g_strdup(row->author);book->sort=g_strdup(row->sort_title);
  book->bytes=row->source_bytes;book->favorite=row->favorite;book->deleted=row->deleted;book->sdk_id=row->sdk_book_id;return 0;
}
static int records_head_copy(void *opaque,const reader_revision_head *head) {
  records_heads *heads=opaque;
  if(heads->count==32) { heads->overflow=1;return 1; }
  g_strlcpy(heads->ids[heads->count++],head->revision_id,33);return 0;
}
static int records_hex(const char *id,size_t length) {
  if(!id || strlen(id)!=length) return 0;
  for(size_t i=0;i<length;i++) if(!g_ascii_isdigit(id[i]) && !(id[i]>='a' && id[i]<='f')) return 0;
  return 1;
}
static char *records_pending_path(linux_reader *reader) { return g_strconcat(reader->catalog_path,".reading.pending",NULL); }
/* 0 absent, 1 valid bounded private keyfile, -1 retained and refused. */
static int records_pending_read(linux_reader *reader,GKeyFile **out) {
  char *path=records_pending_path(reader);int file=open(path,O_RDONLY|O_CLOEXEC|O_NOFOLLOW);g_free(path);*out=NULL;
  if(file<0) return errno==ENOENT ? 0:-1;
  struct stat before,after;char *bytes=NULL;int answer=-1;
  if(fstat(file,&before) || !accounts_private_file(&before) || before.st_size<=0 || before.st_size>RECORDS_PENDING_LIMIT) goto done;
  bytes=g_malloc((gsize)before.st_size+1);size_t at=0;
  while(at<(size_t)before.st_size) {
    ssize_t got=read(file,bytes+at,(size_t)before.st_size-at);if(got<0 && errno==EINTR) continue;
    if(got<=0) goto done;
    at+=(size_t)got;
  }
  if(fstat(file,&after) || !received_same_file(&before,&after) || memchr(bytes,0,at)) goto done;
  bytes[at]=0;GKeyFile *pending=g_key_file_new();
  if(!g_key_file_load_from_data(pending,bytes,at,G_KEY_FILE_NONE,NULL) || g_key_file_get_integer(pending,"request","version",NULL)!=1) {
    g_key_file_free(pending);goto done;
  }
  static const char *required[]={"version","sdk_book","kind","operation","book","annotation","revision","bootstrap","body","parser","capture","format","title","author","sort","source_bytes","favorite","heads"};
  gsize group_count=0,key_count=0;char **groups=g_key_file_get_groups(pending,&group_count),**keys=g_key_file_get_keys(pending,"request",&key_count,NULL);
  int shape=group_count==1 && !strcmp(groups[0],"request") && key_count==G_N_ELEMENTS(required);
  for(size_t i=0;i<G_N_ELEMENTS(required);i++) if(!g_key_file_has_key(pending,"request",required[i],NULL)) shape=0;
  g_strfreev(groups);g_strfreev(keys);
  if(!shape) { g_key_file_free(pending);goto done; }
  char *revision=g_key_file_get_string(pending,"request","revision",NULL);
  char *book=g_key_file_get_string(pending,"request","book",NULL);
  exr_format format;const char *hash=NULL;
  int valid=records_hex(revision,32) && received_format(book,&format,&hash);
  g_free(revision);g_free(book);if(!valid) { g_key_file_free(pending);goto done; }
  *out=pending;answer=1;
done:
  g_free(bytes);close(file);return answer;
}
static exr_status records_pending_write(linux_reader *reader,GKeyFile *pending) {
  GKeyFile *existing=NULL;int state=records_pending_read(reader,&existing);if(existing) g_key_file_free(existing);
  if(state) return EXR_DATABASE;
  gsize size=0;char *bytes=g_key_file_to_data(pending,&size,NULL),*path=records_pending_path(reader);
  char *temporary=g_strconcat(path,".XXXXXX",NULL),*directory=g_path_get_dirname(path);
  int file=-1,dir=-1,created=0;exr_status status=EXR_IO;
  if(!bytes || size>RECORDS_PENDING_LIMIT || !accounts_private_directory(directory,0)) goto done;
  file=g_mkstemp_full(temporary,O_RDWR|O_CLOEXEC,0600);if(file<0) goto done;
  created=1;
  size_t at=0;while(at<size) { ssize_t got=write(file,bytes+at,size-at);if(got<0 && errno==EINTR) continue;if(got<=0) goto done;at+=(size_t)got; }
  if(fsync(file)) goto done;
  if(close(file)) { file=-1;goto done; }file=-1;
  if(rename(temporary,path)) goto done;
  created=0;
  dir=open(directory,O_RDONLY|O_DIRECTORY|O_CLOEXEC);if(dir<0 || fsync(dir)) goto done;
  status=EXR_OK;
done:
  if(file>=0) close(file);
  if(dir>=0) close(dir);
  if(created) unlink(temporary);
  g_free(directory);g_free(temporary);g_free(path);g_free(bytes);return status;
}
static exr_status records_pending_clear(linux_reader *reader,const char *revision) {
  GKeyFile *pending=NULL;int state=records_pending_read(reader,&pending);
  if(!state) return EXR_OK;
  if(state<0) return EXR_DATABASE;
  char *actual=g_key_file_get_string(pending,"request","revision",NULL);
  int same=actual && revision && !strcmp(actual,revision);g_free(actual);g_key_file_free(pending);
  if(!same) return EXR_DATABASE;
  char *path=records_pending_path(reader),*directory=g_path_get_dirname(path);exr_status status=EXR_IO;
  if(!unlink(path)) { int dir=open(directory,O_RDONLY|O_DIRECTORY|O_CLOEXEC);if(dir>=0) { status=fsync(dir) ? EXR_IO:EXR_OK;close(dir); } }
  g_free(directory);g_free(path);return status;
}
static void records_pending_status(linux_reader *reader,reader_result *result) {
  GKeyFile *pending=NULL;int state=records_pending_read(reader,&pending);
  result->records_pending=state!=0;result->records_pending_error=state<0;
  if(pending) { char *id=g_key_file_get_string(pending,"request","revision",NULL);g_strlcpy(result->records_revision,id,33);g_free(id);g_key_file_free(pending); }
}
static exr_status records_book_identity(linux_reader *reader,const reader_command *command,reader_result *result,records_book *book) {
  if(!reader->current.id || reader->current.id!=command->book || !reader->catalog) return EXR_ARGUMENT;
  char hash[65];uint64_t bytes=0;exr_error error={0};
  exr_status status=reader_catalog_sdk_original_identity(reader->library,command->book,&reader->control,hash,&bytes,&error);
  if(status!=EXR_OK) return status;
  exr_format format=EXR_CUSTOM;exr_book *books=NULL;size_t count=0;
  status=exr_library_books(reader->library,"",&books,&count,&error);
  if(status==EXR_OK) for(size_t i=0;i<count;i++) if(books[i].id==command->book) { format=books[i].format;break; }
  exr_books_free(books,count);if(status!=EXR_OK) return status;
  static const struct { exr_format value;const char *name; } names[]={{EXR_TXT,"txt"},{EXR_HTML,"html"},{EXR_FB2,"fb2"},{EXR_EPUB,"epub"},{EXR_DOCX,"docx"},{EXR_RTF,"rtf"},{EXR_MOBI,"mobi"},{EXR_PDF,"pdf"},{EXR_CBZ,"cbz"}};
  const char *name=NULL;for(size_t i=0;i<G_N_ELEMENTS(names);i++) if(format==names[i].value) name=names[i].name;
  if(!name) return EXR_ARGUMENT;
  snprintf(result->records_key,sizeof(result->records_key),"%s:%s",name,hash);
  int found=0;if(reader_catalog_metadata(reader->catalog,result->records_key,records_book_copy,book,&found,NULL) || !found ||
     book->deleted || book->sdk_id!=command->book || book->bytes!=bytes || strcmp(book->format,name)) return EXR_DATABASE;
  return EXR_OK;
}
static exr_status records_selected(received_owner *owner,const char *book,const char *id,int progress,
    const char *expected,const char *sha,char **wire,size_t *size,reader_revision_info *info,reader_revision_selection *selection) {
  char *key=progress ? g_strdup(book):g_strdup_printf("%s:%s",book,id ? id:"");
  reader_revision_status code=reader_revision_selected(owner->revisions,progress ? "progress":"annotation",key,wire,size,info,selection,NULL);g_free(key);
  if(code!=READER_REV_OK && code!=READER_REV_UNSAFE && code!=READER_REV_NOT_FOUND) return EXR_DATABASE;
  if(expected && expected[0] && (code!=READER_REV_OK || strcmp(expected,info->revision_id) || !sha || strcmp(sha,info->sha256))) return EXR_ARGUMENT;
  return EXR_OK;
}
static void records_capture_from_record(const reader_rs_record *record,reader_rs_capture *capture,exr_anchor *anchor,exr_fixed_anchor *fixed) {
  memset(capture,0,sizeof(*capture));memset(anchor,0,sizeof(*anchor));memset(fixed,0,sizeof(*fixed));
  capture->mode=record->mode;capture->part_path=record->part_path;capture->page=(size_t)record->page;
  if(!record->has_location) return;
  if(record->mode==READER_RS_FIXED_PAGE) {
    fixed->start=(size_t)record->start;fixed->end=(size_t)record->end;fixed->page_id=record->page_id;
    fixed->exact=record->exact;fixed->prefix=record->prefix;fixed->suffix=record->suffix;
    fixed->exact_size=record->exact_size;fixed->prefix_size=record->prefix_size;fixed->suffix_size=record->suffix_size;capture->fixed=fixed;
  } else {
    anchor->start=(size_t)record->start;anchor->end=(size_t)record->end;anchor->exact=record->exact;anchor->prefix=record->prefix;anchor->suffix=record->suffix;
    anchor->chapter=record->chapter;capture->anchor=anchor;
  }
}
/* A fresh public SDK session verifies a selector. It never changes current. */
static exr_status records_resolve(linux_reader *reader,const reader_rs_record *record,reader_session *source,
    exr_anchor_match *match,size_t *unit,exr_error *error) {
  reader_result opened={0};reader_rs_error problem={0};
  exr_status status=open_book(reader,reader->current.id,reader->current.font,reader->current.zoom,source,&opened,error);
  reader_result_free(&opened);if(status!=EXR_OK) return status;
  reader_rs_status code=READER_RS_IDENTITY;
  if(source->fixed_document && record->mode==READER_RS_FIXED_PAGE) code=reader_rs_resolve_fixed(source->fixed_document,record,&reader->control,unit,match,&problem);
  else if(source->bounded && record->mode==READER_RS_EPUB_CHAPTER) {
    code=reader_rs_epub_record_part(source->publication,record,unit,&problem);
    if(code==READER_RS_OK) {
      exr_pager_free(source->pager);source->pager=NULL;source->part=*unit;
      status=pager_create(reader,source,*unit,source->font,&source->pager,error);
      code=status==EXR_OK ? reader_rs_resolve_epub(source->publication,source->pager,*unit,record,&reader->control,match,&problem):READER_RS_SDK;
    }
  } else if(!source->bounded && source->document && record->mode==READER_RS_REFLOW_GLOBAL) {
    *unit=0;code=reader_rs_resolve_reflow(source->document,record,&reader->control,match,&problem);
  }
  if(code==READER_RS_OK && match->state==EXR_ANCHOR_FOUND) return EXR_OK;
  return cancel(reader)==EXR_CANCELLED ? EXR_CANCELLED:EXR_ARGUMENT;
}
static exr_status records_capture(linux_reader *reader,reader_session *source,size_t unit,size_t start,size_t end,
    reader_rs_capture *capture_value,exr_anchor *anchor,exr_fixed_anchor *fixed,exr_error *error) {
  memset(capture_value,0,sizeof(*capture_value));
  if(source->fixed_document) {
    exr_fixed_text *text=NULL;exr_status status=exr_fixed_load_text(source->fixed_document,unit,&reader->control,&text,error);
    size_t count=0;const exr_fixed_page *pages=exr_fixed_pages(source->fixed_document,&count);
    if(status==EXR_OK && (!pages || unit>=count)) status=EXR_ARGUMENT;
    if(status==EXR_OK) status=exr_fixed_anchor_create(pages[unit].id,text,start,end,fixed,error);
    exr_fixed_text_free(text);capture_value->mode=READER_RS_FIXED_PAGE;capture_value->page=unit;capture_value->fixed=fixed;return status;
  }
  capture_value->mode=source->bounded ? READER_RS_EPUB_CHAPTER:READER_RS_REFLOW_GLOBAL;
  capture_value->anchor=anchor;capture_value->part_path=source->bounded ? route(source,unit):NULL;
  return capture(reader,source,start,end,anchor,error);
}
static exr_status records_list(linux_reader *reader,received_owner *owner,const reader_command *command,reader_result *result) {
  reader_av_options options={0};options.struct_size=sizeof(options);options.max_page_bytes=READER_AV_PAGE_BYTES_MIN;
  options.cancel=reader->control.cancelled;options.cancel_context=reader->control.context;
  reader_av_view *view=NULL;reader_av_error error={0};reader_av_cursor from={0};
  reader_av_status code=reader_av_open(owner->revisions,result->records_key,&options,&view,&error);
  if(code==READER_AV_OK) code=reader_av_cursor_start(view,command->direction<0 ? -1:1,&from,&error);
  if(code==READER_AV_OK && command->records_after && command->records_after[0]) {
    if(!records_hex(command->records_after,32)) code=READER_AV_CURSOR;
    else { from.has_after=1;g_strlcpy(from.after_id,command->records_after,33); }
  }
  if(code==READER_AV_OK) code=reader_av_page_get(view,&from,32,&result->records_page,&error);
  reader_av_close(&view,NULL);result->records_code=code;
  if(code!=READER_AV_OK) return code==READER_AV_CANCELLED ? EXR_CANCELLED:EXR_DATABASE;
  char *wire=NULL;size_t bytes=0;reader_revision_info info={0};reader_revision_selection selected={0};
  exr_status status=records_selected(owner,result->records_key,NULL,1,NULL,NULL,&wire,&bytes,&info,&selected);
  reader_revision_bytes_free(wire);if(status!=EXR_OK) return status;
  result->records_progress_state=selected.kind;result->records_progress_deleted=selected.graph.deleted;
  result->records_progress_revisions=selected.graph.revisions;result->records_progress_heads=selected.graph.heads;
  result->records_progress_missing=selected.graph.missing_parents;result->records_progress_foreign=selected.graph.foreign_parents;
  if(selected.kind==READER_SELECTION_SAFE) { g_strlcpy(result->records_progress_head,info.revision_id,33);g_strlcpy(result->records_progress_sha,info.sha256,65); }
  records_pending_status(reader,result);
  snprintf(result->message,sizeof(result->message),"%zu records · %s%s%s",result->records_page.count,
    result->records_page.complete ? "This direction is complete":"More records remain",
    result->records_page.budget_stopped ? " · 2 MiB page budget reached":"",result->records_pending ? " · Previous save needs confirmation":"");
  return EXR_OK;
}
static void records_key_string(GKeyFile *pending,const char *key,const char *value) { g_key_file_set_string(pending,"request",key,value ? value:""); }
static exr_status records_prepare(linux_reader *reader,received_owner *owner,const records_book *book,const reader_command *command,reader_result *result) {
  GKeyFile *existing=NULL;int pending_state=records_pending_read(reader,&existing);if(existing) g_key_file_free(existing);
  if(pending_state) { result->records_pending=1;result->records_pending_error=pending_state<0;return EXR_DATABASE; }
  if(command->records_kind<READER_RC_PROGRESS || command->records_kind>READER_RC_NOTE_TEXT ||
     command->records_operation<READER_RC_PUT || command->records_operation>READER_RC_RESTORE) return EXR_ARGUMENT;
  int kind=command->records_kind,progress=kind==READER_RC_PROGRESS;
  const char *body=command->records_text ? command->records_text:"";
  if(strlen(body)>65536 || !g_utf8_validate(body,-1,NULL) || (progress && body[0])) return EXR_ARGUMENT;
  char annotation[33]={0},revision[33]={0},bootstrap[33]={0};
  if(command->records_id && command->records_id[0]) { if(!records_hex(command->records_id,32)) return EXR_ARGUMENT;g_strlcpy(annotation,command->records_id,33); }
  if(!progress && !annotation[0] && reader_revision_new_id(annotation,NULL)!=READER_REV_OK) return EXR_DATABASE;
  if(reader_revision_new_id(revision,NULL)!=READER_REV_OK || reader_revision_new_id(bootstrap,NULL)!=READER_REV_OK) return EXR_DATABASE;
  char *old_wire=NULL;size_t old_size=0;reader_revision_info info={0};reader_revision_selection selected={0};
  exr_status status=records_selected(owner,book->key,annotation,progress,command->records_head,command->records_sha,&old_wire,&old_size,&info,&selected);
  if(status!=EXR_OK) goto done;
  if(selected.kind!=READER_SELECTION_MISSING && selected.kind!=READER_SELECTION_SAFE) { status=EXR_ARGUMENT;goto done; }
  if(selected.kind==READER_SELECTION_SAFE && (!command->records_head || !command->records_head[0])) { status=EXR_ARGUMENT;goto done; }
  if(command->records_operation==READER_RC_RESTORE ? !selected.graph.deleted:selected.graph.deleted) { status=EXR_ARGUMENT;goto done; }
  records_heads heads={0};reader_revision_state graph={0};char *entity=progress ? g_strdup(book->key):g_strdup_printf("%s:%s",book->key,annotation);
  reader_revision_status hcode=reader_revision_heads(owner->revisions,progress ? "progress":"annotation",entity,records_head_copy,&heads,&graph,NULL);g_free(entity);
  if(hcode!=READER_REV_OK || heads.overflow || heads.count!=graph.heads || heads.count>1) { status=EXR_ARGUMENT;goto done; }
  const char *parents[32];for(size_t i=0;i<heads.count;i++) parents[i]=heads.ids[i];
  reader_rs_record retained={0};reader_rs_error problem={0};reader_rs_capture captured={0};exr_anchor anchor={0};exr_fixed_anchor fixed={0};
  reader_session source={0};exr_error sdk_error={0};size_t capture_unit=reader->current.fixed_document ? reader->current.page:reader->current.part;
  char *capture_wire=NULL;size_t capture_bytes=0;
  if(command->records_operation==READER_RC_RESTORE) {
    char *history=NULL;size_t history_bytes=0;reader_revision_info historical={0};
    reader_revision_status code=reader_revision_get(owner->revisions,command->records_version,&history,&history_bytes,&historical,NULL);
    if(code!=READER_REV_OK || strcmp(historical.entity_key,info.entity_key) || strcmp(historical.book_key,book->key) || !strcmp(historical.operation,"delete")) status=EXR_ARGUMENT;
    if(status==EXR_OK && reader_rs_decode(owner->revisions,history,history_bytes,&retained,&problem)!=READER_RS_OK) status=EXR_ARGUMENT;
    reader_revision_bytes_free(history);
    if(status==EXR_OK) { body=retained.note_text ? retained.note_text:"";if(!progress) kind=retained.start==retained.end ? READER_RC_BOOKMARK:READER_RC_HIGHLIGHT; }
    exr_anchor_match match={0};size_t unit=0;
    if(status==EXR_OK) status=records_resolve(reader,&retained,&source,&match,&unit,&sdk_error);
    if(status==EXR_OK) { capture_unit=unit;status=records_capture(reader,&source,unit,match.start,match.end,&captured,&anchor,&fixed,&sdk_error); }
  } else if(command->records_operation==READER_RC_DELETE) {
    if(!old_wire || reader_rs_decode(owner->revisions,old_wire,old_size,&retained,&problem)!=READER_RS_OK) status=EXR_ARGUMENT;
    else captured.mode=retained.mode;
  } else if(command->records_kind!=READER_RC_NOTE_TEXT) {
    size_t start=command->records_kind==READER_RC_HIGHLIGHT ? command->start:reader->current.fixed_document ? 0:reader->current.position;
    size_t end=command->records_kind==READER_RC_HIGHLIGHT ? command->end:start;
    if(command->records_kind==READER_RC_HIGHLIGHT && (start>=end || start<reader->current.start || end>reader->current.end)) status=EXR_ARGUMENT;
    else status=records_capture(reader,&reader->current,capture_unit,start,end,&captured,&anchor,&fixed,&sdk_error);
  }
  if(status==EXR_OK && command->records_kind!=READER_RC_NOTE_TEXT) {
    reader_rs_envelope envelope={revision,command->records_operation==READER_RC_DELETE ? "delete":command->records_operation==READER_RC_RESTORE ? "restore":"put",
      progress ? "progress":"annotation",book->key,progress ? NULL:annotation,parents,heads.count,progress || command->records_operation==READER_RC_DELETE ? NULL:body,exr_version()};
    if(reader_rs_encode_v2(owner->revisions,&envelope,&captured,capture_unit,&capture_wire,&capture_bytes,&problem)!=READER_RS_OK) { status=EXR_ARGUMENT;snprintf(result->message,sizeof(result->message),"Capture cannot be retained: %.120s",problem.message); }
  }
  if(status==EXR_OK) status=cancel(reader);
  if(status==EXR_OK) {
    GKeyFile *pending=g_key_file_new();g_key_file_set_integer(pending,"request","version",1);
    g_key_file_set_int64(pending,"request","sdk_book",command->book);g_key_file_set_integer(pending,"request","kind",kind);
    g_key_file_set_integer(pending,"request","operation",command->records_operation);
    records_key_string(pending,"book",book->key);records_key_string(pending,"annotation",annotation);records_key_string(pending,"revision",revision);
    records_key_string(pending,"bootstrap",bootstrap);records_key_string(pending,"body",body);records_key_string(pending,"parser",exr_version());
    records_key_string(pending,"capture",capture_wire);records_key_string(pending,"format",book->format);records_key_string(pending,"title",book->title);
    records_key_string(pending,"author",book->author);records_key_string(pending,"sort",book->sort);
    g_key_file_set_uint64(pending,"request","source_bytes",book->bytes);g_key_file_set_integer(pending,"request","favorite",book->favorite);
    g_key_file_set_string_list(pending,"request","heads",parents,heads.count);
    status=records_pending_write(reader,pending);g_key_file_free(pending);
    if(status==EXR_OK) { result->records_pending=1;g_strlcpy(result->records_revision,revision,33);g_strlcpy(result->records_annotation,annotation,33); }
  }
  reader_rs_free(capture_wire);reader_rs_record_free(&retained);exr_anchor_free(&anchor);exr_fixed_anchor_free(&fixed);session_free(&source);
done:
  reader_revision_bytes_free(old_wire);
  if(status!=EXR_OK && !result->message[0]) snprintf(result->message,sizeof(result->message),"Save did not complete. Refresh this record before trying again");
  return status;
}
static exr_status records_retry(linux_reader *reader,received_owner *owner,const records_book *book,reader_result *result) {
  GKeyFile *pending=NULL;int pending_state=records_pending_read(reader,&pending);
  if(pending_state!=1) { result->records_pending=pending_state!=0;result->records_pending_error=pending_state<0;return EXR_DATABASE; }
  GError *error=NULL;char *key=g_key_file_get_string(pending,"request","book",error ? NULL : &error);
  char *revision=g_key_file_get_string(pending,"request","revision",error ? NULL : &error),*bootstrap=g_key_file_get_string(pending,"request","bootstrap",error ? NULL : &error);
  char *annotation=g_key_file_get_string(pending,"request","annotation",error ? NULL : &error),*body=g_key_file_get_string(pending,"request","body",error ? NULL : &error);
  char *parser=g_key_file_get_string(pending,"request","parser",error ? NULL : &error),*wire=g_key_file_get_string(pending,"request","capture",error ? NULL : &error);
  char *format=g_key_file_get_string(pending,"request","format",error ? NULL : &error),*title=g_key_file_get_string(pending,"request","title",error ? NULL : &error);
  char *author=g_key_file_get_string(pending,"request","author",error ? NULL : &error),*sort=g_key_file_get_string(pending,"request","sort",error ? NULL : &error);
  gsize head_count=0;char **heads=g_key_file_get_string_list(pending,"request","heads",&head_count,error ? NULL : &error);
  int kind=g_key_file_get_integer(pending,"request","kind",error ? NULL : &error),operation=g_key_file_get_integer(pending,"request","operation",error ? NULL : &error);
  uint64_t bytes=g_key_file_get_uint64(pending,"request","source_bytes",error ? NULL : &error);int favorite=g_key_file_get_integer(pending,"request","favorite",error ? NULL : &error);
  int64_t sdk_book=g_key_file_get_int64(pending,"request","sdk_book",error ? NULL : &error);exr_status status=EXR_ARGUMENT;
  reader_rs_record decoded={0};reader_rs_error decode_error={0};reader_rs_capture capture_value={0};exr_anchor anchor={0};exr_fixed_anchor fixed={0};
  if(error || !key || strcmp(key,book->key) || sdk_book!=reader->current.id || !records_hex(bootstrap,32) || !records_hex(revision,32) ||
     head_count>32 || !body || strlen(body)>65536 || !g_utf8_validate(body,-1,NULL) || kind<READER_RC_PROGRESS || kind>READER_RC_NOTE_TEXT || operation<READER_RC_PUT || operation>READER_RC_RESTORE ||
     !format || strcmp(format,book->format) || bytes!=book->bytes || !title || !author || !sort || !parser || !wire || (kind!=READER_RC_PROGRESS && !records_hex(annotation,32))) goto done;
  for(size_t i=0;i<head_count;i++) if(!records_hex(heads[i],32)) goto done;
  if(kind!=READER_RC_NOTE_TEXT) {
    if(reader_rs_decode(owner->revisions,wire,strlen(wire),&decoded,&decode_error)!=READER_RS_OK || strcmp(decoded.book_key,key) ||
       strcmp(decoded.entity_kind,kind==READER_RC_PROGRESS ? "progress":"annotation") || (kind!=READER_RC_PROGRESS && strcmp(decoded.annotation_id,annotation))) goto done;
    records_capture_from_record(&decoded,&capture_value,&anchor,&fixed);
  }
  /* From the durable boundary onwards no UI cancellation interrupts a product
     transaction. Closing only discards its callback; an uncertain result keeps
     this exact request for explicit retry on the next real process. */
  uint64_t retained_bytes=0;reader_revision_status identity=reader_revision_book_identity(owner->revisions,key,&retained_bytes,NULL);
  if(identity==READER_REV_NOT_FOUND) {
    reader_command_context context={owner->revisions,bootstrap,NULL,0};
    reader_book_command bootstrap_command={READER_COMMAND_PUT,key,format,strchr(key,':')+1,title,author,sort,bytes,favorite};
    reader_command_result submitted={0};reader_command_error problem={0};
    if(reader_command_apply_book(&context,&bootstrap_command,&submitted,&problem)!=READER_COMMAND_OK) { status=EXR_DATABASE;snprintf(result->message,sizeof(result->message),"Book preparation refused: %.120s",problem.message);goto done; }
  } else if(identity!=READER_REV_OK || retained_bytes!=bytes) { status=EXR_DATABASE;goto done; }
  reader_rc_context context={owner->revisions,revision,(const char *const *)heads,head_count,parser};
  reader_rc_command command={(reader_rc_kind)kind,(reader_rc_operation)operation,key,kind==READER_RC_PROGRESS ? NULL:annotation,
    kind==READER_RC_NOTE_TEXT ? NULL:&capture_value,(size_t)decoded.part,kind==READER_RC_PROGRESS || operation==READER_RC_DELETE ? NULL:body};
  reader_rc_result saved={0};reader_rc_error problem={0};reader_rc_status code=reader_rc_apply(&context,&command,&saved,&problem);
  result->records_code=code;result->records_created=saved.created;g_strlcpy(result->records_revision,revision,33);g_strlcpy(result->records_annotation,saved.annotation_id,33);
  status=code==READER_RC_OK ? records_pending_clear(reader,revision):EXR_DATABASE;
  snprintf(result->message,sizeof(result->message),"%s",code==READER_RC_OK ? saved.created ? "Reading record saved":"Original save confirmed; no duplicate record":
    code==READER_RC_UNSAFE || code==READER_RC_SOURCE ? "Reading history changed; refresh and review the retained request":"Save needs confirmation; the exact original request was retained");
done:
  if(error) g_error_free(error);
  reader_rs_record_free(&decoded);g_strfreev(heads);g_free(key);g_free(revision);g_free(bootstrap);g_free(annotation);
  g_free(body);g_free(parser);g_free(wire);g_free(format);g_free(title);g_free(author);g_free(sort);g_key_file_free(pending);
  if(status!=EXR_OK && !result->message[0]) snprintf(result->message,sizeof(result->message),"Original reading request could not be verified; retained for review");
  records_pending_status(reader,result);return status;
}
static exr_status records_jump(linux_reader *reader,reader_session *next,const reader_command *command,reader_result *result,exr_error *error) {
  result->has_records=1;result->records_token=command->records_token;received_owner *owner=NULL;records_book book={0};
  exr_status status=records_book_identity(reader,command,result,&book);if(status==EXR_OK) status=received_ready(reader,&owner);
  char *wire=NULL;size_t bytes=0;reader_revision_info info={0};reader_revision_selection selection={0};reader_rs_record decoded={0};reader_rs_error problem={0};
  reader_session independent={0};exr_anchor_match first={0},second={0};size_t unit=0;
  if(status==EXR_OK) status=records_selected(owner,book.key,command->records_id,command->records_progress,command->records_head,command->records_sha,&wire,&bytes,&info,&selection);
  if(status==EXR_OK && (selection.kind!=READER_SELECTION_SAFE || selection.graph.deleted || !wire || reader_rs_decode(owner->revisions,wire,bytes,&decoded,&problem)!=READER_RS_OK)) status=EXR_ARGUMENT;
  if(status==EXR_OK) status=records_resolve(reader,&decoded,&independent,&first,&unit,error);
  if(status==EXR_OK) {
    if(next->fixed_document && decoded.mode==READER_RS_FIXED_PAGE) {
      size_t current_page=0;reader_rs_status code=reader_rs_resolve_fixed(next->fixed_document,&decoded,&reader->control,&current_page,&second,&problem);
      if(code!=READER_RS_OK || second.state!=EXR_ANCHOR_FOUND || current_page!=unit || first.start!=second.start || first.end!=second.end) status=EXR_ARGUMENT;
      else status=render_fixed(reader,next,unit,result,error);
    } else if(next->bounded && decoded.mode==READER_RS_EPUB_CHAPTER) {
      size_t part_index=0;if(reader_rs_epub_record_part(next->publication,&decoded,&part_index,&problem)!=READER_RS_OK || part_index!=unit) status=EXR_ARGUMENT;
      else {
        next->pager=NULL;next->part=unit;status=pager_create(reader,next,unit,next->font,&next->pager,error);
        if(status==EXR_OK && reader_rs_resolve_epub(next->publication,next->pager,unit,&decoded,&reader->control,&second,&problem)!=READER_RS_OK) status=EXR_ARGUMENT;
        if(status==EXR_OK && (second.state!=EXR_ANCHOR_FOUND || first.start!=second.start || first.end!=second.end)) status=EXR_ARGUMENT;
        if(status==EXR_OK) status=render(reader,next,0,1,second.start,result,error);
      }
    } else if(next->document && !next->bounded && decoded.mode==READER_RS_REFLOW_GLOBAL) {
      if(reader_rs_resolve_reflow(next->document,&decoded,&reader->control,&second,&problem)!=READER_RS_OK || second.state!=EXR_ANCHOR_FOUND || first.start!=second.start || first.end!=second.end) status=EXR_ARGUMENT;
      else status=render(reader,next,0,1,second.start,result,error);
    } else status=EXR_ARGUMENT;
    if(status==EXR_OK) { next->position=next->fixed_document ? unit:second.start;result->select_range=1;result->selected_start=second.start;result->selected_end=second.end;result->records_match=EXR_ANCHOR_FOUND; }
  }
  if(status!=EXR_OK) { result->records_match=first.state;snprintf(result->message,sizeof(result->message),"Record location was not independently proved; reading unchanged"); }
  records_book_free(&book);reader_revision_bytes_free(wire);reader_rs_record_free(&decoded);session_free(&independent);return status;
}
/* Decode only an ASCII JSON string from already public-validated revision
   bytes. This bounded root-parents reader is not an alternate wire validator. */
static int records_ascii_string(const char **at,const char *end,char *out,size_t capacity) {
  const char *p=*at;size_t size=0;if(p==end || *p++!='"') return 0;
  while(p<end && *p!='"') {
    unsigned value=(unsigned char)*p++;
    if(value=='\\') {
      if(p==end) return 0;
      value=(unsigned char)*p++;
      if(value=='u') {
        if(end-p<4) return 0;
        value=0;
        for(int i=0;i<4;i++) { int digit=g_ascii_xdigit_value(p[i]);if(digit<0) return 0;value=value*16+(unsigned)digit; }
        p+=4;
      } else if(value=='b') value=8;
      else if(value=='f') value=12;
      else if(value=='n') value=10;
      else if(value=='r') value=13;
      else if(value=='t') value=9;
      else if(value!='"' && value!='\\' && value!='/') return 0;
    }
    if(value>127 || !value || size+1>=capacity) return 0;
    out[size++]=(char)value;
  }
  if(p==end) return 0;
  out[size]=0;*at=p+1;return 1;
}
static int records_parents(const char *wire,size_t size,records_heads *parents) {
  const char *p=wire,*end=wire+size;unsigned depth=0;int root_key=0;
  while(p<end) {
    char c=*p;
    if(c=='"') {
      if(depth==1 && root_key) {
        char name[128];if(!records_ascii_string(&p,end,name,sizeof(name))) return 0;
        while(p<end && g_ascii_isspace(*p)) p++;
        if(p==end || *p++!=':') return 0;
        if(!strcmp(name,"parents")) {
          while(p<end && g_ascii_isspace(*p)) p++;
          if(p==end || *p++!='[') return 0;
          for(;;) {
            while(p<end && g_ascii_isspace(*p)) p++;
            if(p<end && *p==']') return 1;
            if(parents->count==32 || !records_ascii_string(&p,end,parents->ids[parents->count],33) || !records_hex(parents->ids[parents->count],32)) return 0;
            parents->count++;
            while(p<end && g_ascii_isspace(*p)) p++;
            if(p<end && *p==']') return 1;
            if(p==end || *p++!=',') return 0;
          }
        }
        root_key=0;continue;
      }
      p++;
      while(p<end && *p!='"') { if(*p=='\\' && p+1<end) p++;p++; }
      if(p==end) return 0;
      p++;continue;
    }
    if(c=='{' || c=='[') { depth++;if(depth==1) root_key=1; }
    else if(c=='}' || c==']') { if(!depth) return 0;depth--; }
    else if(c==',' && depth==1) root_key=1;
    p++;
  }
  return 0;
}
static exr_status records_history(linux_reader *reader,received_owner *owner,const reader_command *command,reader_result *result) {
  char *selected=NULL;size_t selected_size=0;reader_revision_info info={0};reader_revision_selection graph={0};
  exr_status status=records_selected(owner,result->records_key,command->records_id,command->records_progress,
    command->records_head,command->records_sha,&selected,&selected_size,&info,&graph);
  reader_revision_bytes_free(selected);
  if(status!=EXR_OK || graph.kind!=READER_SELECTION_SAFE || !graph.graph.deleted) return EXR_ARGUMENT;
  /* ponytail: one explicit bounded historical batch; expose truncation rather
     than caching an unbounded history graph in the low-frequency dialog. */
  char pending[128][33]={{0}},seen[128][33]={{0}};size_t queued=1,at=0,seen_count=0,total=0;g_strlcpy(pending[0],info.revision_id,33);
  result->records_versions=calloc(32,sizeof(char *));result->records_version_labels=calloc(32,sizeof(char *));
  if(!result->records_versions || !result->records_version_labels) return EXR_MEMORY;
  int stopped=0;
  while(at<queued && !stopped) {
    status=cancel(reader);if(status!=EXR_OK) return status;
    const char *id=pending[at++];int known=0;for(size_t i=0;i<seen_count;i++) if(!strcmp(seen[i],id)) known=1;
    if(known) continue;
    if(seen_count==128) { stopped=1;break; }
    g_strlcpy(seen[seen_count++],id,33);
    char *wire=NULL;size_t bytes=0;reader_revision_info historical={0};reader_rs_record decoded={0};reader_rs_error error={0};
    if(reader_revision_get(owner->revisions,id,&wire,&bytes,&historical,NULL)!=READER_REV_OK || strcmp(historical.entity_key,info.entity_key)) { reader_revision_bytes_free(wire);return EXR_DATABASE; }
    if(bytes>RECORDS_PENDING_LIMIT-total) { reader_revision_bytes_free(wire);stopped=1;break; }total+=bytes;
    records_heads parents={0};if(!records_parents(wire,bytes,&parents)) { reader_revision_bytes_free(wire);return EXR_DATABASE; }
    for(size_t i=0;i<parents.count;i++) {
      int duplicate=0;for(size_t j=0;j<queued;j++) if(!strcmp(pending[j],parents.ids[i])) duplicate=1;
      if(duplicate) continue;
      if(queued==128) { stopped=1;break; }
      g_strlcpy(pending[queued++],parents.ids[i],33);
    }
    if(strcmp(historical.operation,"delete")) {
      if(reader_rs_decode(owner->revisions,wire,bytes,&decoded,&error)!=READER_RS_OK || !decoded.has_location) { reader_rs_record_free(&decoded);reader_revision_bytes_free(wire);return EXR_DATABASE; }
      size_t index=result->records_version_count++;
      result->records_versions[index]=g_strdup(historical.revision_id);
      char *preview=g_utf8_substring(decoded.note_text && decoded.note_text[0] ? decoded.note_text:"Saved location",0,120);
      result->records_version_labels[index]=g_strdup_printf("Retained version %.8s · %s",historical.revision_id,preview);g_free(preview);
      if(result->records_version_count==32) stopped=1;
    }
    reader_rs_record_free(&decoded);reader_revision_bytes_free(wire);
  }
  result->records_history_complete=!stopped && at==queued;
  snprintf(result->message,sizeof(result->message),"%zu retained versions · %s",result->records_version_count,
    result->records_history_complete ? "History is complete":"History stopped at its 32-version / 128-node / 2 MiB limit; this is not a complete list");
  return EXR_OK;
}
static void records_execute(linux_reader *reader,const reader_command *command,reader_result *result) {
  result->has_records=1;result->records_token=command->records_token;records_book book={0};received_owner *owner=NULL;
  result->status=records_book_identity(reader,command,result,&book);
  if(result->status==EXR_OK) result->status=received_ready(reader,&owner);
  if(result->status==EXR_OK && command->action==READER_RECORDS_LIST) result->status=records_list(reader,owner,command,result);
  else if(result->status==EXR_OK && command->action==READER_RECORDS_SAVE) {
    result->status=records_prepare(reader,owner,&book,command,result);
    if(result->status==EXR_OK) result->status=records_retry(reader,owner,&book,result);
  } else if(result->status==EXR_OK && command->action==READER_RECORDS_RETRY) result->status=records_retry(reader,owner,&book,result);
  else if(result->status==EXR_OK && command->action==READER_RECORDS_DISCARD) result->status=records_pending_clear(reader,command->records_head);
  else if(result->status==EXR_OK && command->action==READER_RECORDS_HISTORY) result->status=records_history(reader,owner,command,result);
  else if(result->status==EXR_OK) result->status=EXR_UNSUPPORTED;
  if(command->action==READER_RECORDS_SAVE || command->action==READER_RECORDS_RETRY || command->action==READER_RECORDS_DISCARD) records_pending_status(reader,result);
  if(!result->message[0]) snprintf(result->message,sizeof(result->message),"%s",result->status==EXR_OK ? "Reading records ready":"Reading operation did not complete; saved records retained");
  records_book_free(&book);
}
