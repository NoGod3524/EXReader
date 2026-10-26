/* SPDX-License-Identifier: MIT */
/* Wave 3 owner-worker features: annotation import preview and confirmation,
   local font library leases, original export, jump history and read-only sync
   status. Included by reading.c after the records backend; every call runs on
   the one SDK owner worker, so the SDK, revisions and borrowed fonts have a
   single serialized owner. No GTK, SQL or network code lives here. */
#define W3_LAND_MOVE 4
#define W3_SELECTION_FILE "reader-font.sel"

static int w3_hash_valid(const char *hash) {
  if(!hash || strlen(hash)!=RFL_HASH_BYTES-1) return 0;
  for(size_t i=0;i<RFL_HASH_BYTES-1;i++) if(!g_ascii_isdigit(hash[i]) && !(hash[i]>='a' && hash[i]<='f')) return 0;
  return 1;
}
static exr_status w3_rfl_status(rfl_status code) {
  switch(code) {
    case RFL_OK: return EXR_OK;
    case RFL_CANCELLED: return EXR_CANCELLED;
    case RFL_ENCODING: case RFL_FONT: case RFL_LIMIT: case RFL_ARGUMENT: return EXR_FORMAT;
    default: return EXR_IO;
  }
}
static char *w3_selection_path(linux_reader *reader) {
  char *home=g_path_get_dirname(reader->catalog_path),*path=g_build_filename(home,W3_SELECTION_FILE,NULL);
  g_free(home);return path;
}
static void w3_selection_save(linux_reader *reader) {
  char *path=w3_selection_path(reader);
  g_file_set_contents(path,reader->w3_font_hash,-1,NULL);g_free(path);
}
static exr_status w3_fonts_ready(linux_reader *reader,reader_result *result) {
  if(reader->w3_fonts) return EXR_OK;
  char *home=g_path_get_dirname(reader->catalog_path),*directory=g_build_filename(home,"fonts",NULL);
  rfl_error problem={0};exr_status status=EXR_IO;
  if(accounts_private_directory(directory,1)) {
    rfl_status code=rfl_open(directory,NULL,&reader->w3_fonts,&problem);
    status=w3_rfl_status(code);
    if(status!=EXR_OK) snprintf(result->message,sizeof(result->message),"Font library unavailable: %.120s",problem.message);
  } else snprintf(result->message,sizeof(result->message),"Font library needs an app-private profile directory");
  g_free(directory);g_free(home);return status;
}
/* Called once, before the first book exists, so no pager borrows the base font yet. */
static void w3_font_restore(linux_reader *reader,reader_result *result) {
  if(reader->w3_font_restored) return;
  reader->w3_font_restored=1;
  if(reader->current.id || reader->current.pager || reader->current.fixed_document) return;
  char *path=w3_selection_path(reader),*saved=NULL;
  if(!g_file_get_contents(path,&saved,NULL,NULL) || !saved || !saved[0]) { g_free(path);g_free(saved);return; }
  g_free(path);
  if(!w3_hash_valid(saved)) { g_free(saved);return; }
  rfl_lease *lease=NULL;exr_font *font=NULL;rfl_error problem={0};
  if(w3_fonts_ready(reader,result)==EXR_OK && rfl_font_open(reader->w3_fonts,saved,0,&lease,&problem)==RFL_OK) {
    if(rfl_lease_font(lease,&font,&problem)==RFL_OK) {
      reader->font=font;reader->w3_lease=lease;g_strlcpy(reader->w3_font_hash,saved,sizeof(reader->w3_font_hash));
    } else rfl_lease_release(lease,&problem);
  }
  if(!reader->w3_lease) snprintf(result->message,sizeof(result->message),"Saved reading font was unavailable; built-in font used");
  g_free(saved);
}
static void w3_item_discard(linux_reader *reader) {
  if(reader->w3_item_valid) reader_jh_item_release(&reader->w3_item);
  reader->w3_item_valid=0;reader->w3_kind=0;
}
static void w3_candidate_discard(linux_reader *reader) {
  if(reader->w3_candidate_lease) { rfl_error problem={0};rfl_lease_release(reader->w3_candidate_lease,&problem); }
  reader->w3_candidate_lease=NULL;reader->w3_candidate_font=NULL;reader->w3_candidate_pending=0;
}
static void w3_pending_discard(linux_reader *reader) {
  w3_candidate_discard(reader);w3_item_discard(reader);
}
/* Runs after the accepted pending frame replaced reader->current, so the old pager is gone. */
static void w3_free(linux_reader *reader) {
  w3_pending_discard(reader);
  if(reader->w3_exporter) roe_destroy(&reader->w3_exporter);
  if(reader->w3_history) { reader_jh_error problem={0};reader_jh_close(&reader->w3_history,&problem); }
  if(reader->w3_lease) { rfl_error problem={0};rfl_lease_release(reader->w3_lease,&problem); }
  reader->w3_lease=NULL;reader->font=reader->w3_base_font ? reader->w3_base_font:reader->font;
  if(reader->w3_fonts) { rfl_error problem={0};rfl_close(reader->w3_fonts,&problem); }
  reader->w3_fonts=NULL;
}
static exr_status w3_book_key(linux_reader *reader,char key[73]) {
  char hash[65];uint64_t bytes=0;exr_error error={0};exr_format format=EXR_CUSTOM;exr_book *books=NULL;size_t count=0;
  if(!reader->current.id) return EXR_ARGUMENT;
  exr_status status=reader_catalog_sdk_original_identity(reader->library,reader->current.id,&reader->control,hash,&bytes,&error);
  if(status!=EXR_OK) return status;
  status=exr_library_books(reader->library,"",&books,&count,&error);
  if(status==EXR_OK) for(size_t i=0;i<count;i++) if(books[i].id==reader->current.id) { format=books[i].format;break; }
  exr_books_free(books,count);if(status!=EXR_OK) return status;
  static const struct { exr_format value;const char *name; } names[]={{EXR_TXT,"txt"},{EXR_HTML,"html"},{EXR_FB2,"fb2"},{EXR_EPUB,"epub"},{EXR_DOCX,"docx"},{EXR_RTF,"rtf"},{EXR_MOBI,"mobi"},{EXR_PDF,"pdf"},{EXR_CBZ,"cbz"}};
  const char *name=NULL;for(size_t i=0;i<G_N_ELEMENTS(names);i++) if(format==names[i].value) name=names[i].name;
  if(!name) return EXR_ARGUMENT;
  snprintf(key,73,"%s:%s",name,hash);return EXR_OK;
}
static exr_status w3_history_ready(linux_reader *reader) {
  reader_jh_error problem={0};
  if(reader->w3_history) return EXR_OK;
  return reader_jh_open(NULL,&reader->w3_history,&problem)==READER_JH_OK ? EXR_OK:EXR_MEMORY;
}
static void w3_history_state(linux_reader *reader,reader_result *result) {
  reader_jh_state state={0};reader_jh_error problem={0};
  result->has_w3=1;
  if(reader->w3_history && reader_jh_state_get(reader->w3_history,&state,&problem)==READER_JH_OK) {
    result->w3_can_back=state.can_back;result->w3_can_forward=state.can_forward;
    result->w3_history_count=(int)state.count;result->w3_history_cursor=(int)state.cursor;
  }
  result->w3_history_code=reader->w3_history_code;
  g_strlcpy(result->w3_font_active,reader->w3_font_hash,sizeof(result->w3_font_active));
}
/* A landing the user really reached; failure leaves the history untouched. */
static void w3_land(linux_reader *reader,int kind) {
  reader_session *session=&reader->current;char key[73];received_owner *owner=NULL;
  reader->w3_history_code=-1;
  if(w3_history_ready(reader)!=EXR_OK || (!session->pager && !session->fixed_document) ||
     w3_book_key(reader,key)!=EXR_OK || received_ready(reader,&owner)!=EXR_OK) return;
  reader_rs_capture captured;exr_anchor anchor={0};exr_fixed_anchor fixed={0};exr_error error={0};
  size_t unit=session->fixed_document ? session->page:session->part;
  size_t at=session->fixed_document ? 0:session->position;
  if(records_capture(reader,session,unit,at,at,&captured,&anchor,&fixed,&error)==EXR_OK) {
    reader_jh_position position={key,exr_version(),(reader_jh_kind)kind,&captured,session->bounded ? session->part:0};
    reader_jh_result landed;reader_jh_error problem={0};
    reader->w3_history_code=(int)reader_jh_commit(reader->w3_history,owner->revisions,&position,&landed,&problem);
  }
  exr_anchor_free(&anchor);exr_fixed_anchor_free(&fixed);
}
static void w3_mark_pending(linux_reader *reader,const reader_command *command) {
  switch(command->action) {
    case READER_SEARCH_CHOOSE: reader->w3_kind=READER_JH_SEARCH;break;
    case READER_NAVIGATION_CHOOSE: reader->w3_kind=READER_JH_TOC;break;
    case READER_W3_HISTORY: reader->w3_kind=W3_LAND_MOVE;break;
    case READER_FONT: case READER_ZOOM: case READER_SETTINGS: case READER_W3_FONT_USE: reader->w3_kind=0;break;
    default: reader->w3_kind=READER_JH_PAGE;break;
  }
}
/* After READER_COMMIT persisted and installed the pending frame. */
static void w3_after_commit(linux_reader *reader,reader_result *result) {
  if(reader->w3_candidate_pending) {
    rfl_lease *old=reader->w3_lease;
    reader->font=reader->w3_candidate_font;reader->w3_lease=reader->w3_candidate_lease;
    g_strlcpy(reader->w3_font_hash,reader->w3_candidate_hash,sizeof(reader->w3_font_hash));
    reader->w3_candidate_lease=NULL;reader->w3_candidate_font=NULL;reader->w3_candidate_pending=0;
    if(old) { rfl_error problem={0};rfl_lease_release(old,&problem); }
    w3_selection_save(reader);
  }
  if(reader->w3_kind==W3_LAND_MOVE) {
    reader_jh_error problem={0};
    if(reader->w3_item_valid) reader->w3_history_code=(int)reader_jh_complete(reader->w3_history,&reader->w3_item,&problem);
    w3_item_discard(reader);
  } else if(reader->w3_kind>0) {
    w3_land(reader,reader->w3_kind);reader->w3_kind=0;
  }
  w3_history_state(reader,result);
}
static exr_status w3_font_list(linux_reader *reader,reader_result *result) {
  size_t count=0;rfl_error problem={0};
  if(rfl_count(reader->w3_fonts,&count,&problem)!=RFL_OK) return EXR_IO;
  result->w3_font_hashes=calloc(count+1,sizeof(char *));result->w3_font_names=calloc(count+1,sizeof(char *));
  if(!result->w3_font_hashes || !result->w3_font_names) return EXR_MEMORY;
  for(size_t i=0;i<count;i++) {
    rfl_record record;
    if(rfl_get(reader->w3_fonts,i,&record,&problem)!=RFL_OK) return EXR_IO;
    result->w3_font_hashes[i]=g_strdup(record.hash);result->w3_font_names[i]=g_strdup(record.display_name);
    result->w3_font_count=(int)i+1;
  }
  g_strlcpy(result->w3_font_active,reader->w3_font_hash,sizeof(result->w3_font_active));
  return EXR_OK;
}
static int w3_font_progress(void *context,const char *stage,uint64_t done,uint64_t total) {
  (void)stage;(void)done;(void)total;return cancel((linux_reader *)context)==EXR_CANCELLED;
}
static exr_status w3_font_import(linux_reader *reader,const reader_command *command,reader_result *result) {
  rfl_control control={w3_font_progress,reader};rfl_record record;int created=0;rfl_error problem={0};
  char *base=g_path_get_basename(command->w3_path ? command->w3_path:"font");
  const char *name=command->w3_name && command->w3_name[0] ? command->w3_name:base;
  rfl_status code=rfl_import_file(reader->w3_fonts,command->w3_path,name,&control,&record,&created,&problem);
  if(code==RFL_OK) snprintf(result->message,sizeof(result->message),created ? "Font added to the library":"That font is already in the library");
  else snprintf(result->message,sizeof(result->message),"Font was not added; library unchanged (%.120s)",problem.message);
  g_free(base);return w3_rfl_status(code);
}
static exr_status w3_font_remove(linux_reader *reader,const reader_command *command,reader_result *result) {
  rfl_error problem={0};
  if(!w3_hash_valid(command->w3_hash)) return EXR_ARGUMENT;
  if(!strcmp(command->w3_hash,reader->w3_font_hash) || (reader->w3_candidate_pending && !strcmp(command->w3_hash,reader->w3_candidate_hash))) {
    snprintf(result->message,sizeof(result->message),"This font is in use; switch to another font before removing it");return EXR_ARGUMENT;
  }
  rfl_status code=rfl_remove(reader->w3_fonts,command->w3_hash,&problem);
  snprintf(result->message,sizeof(result->message),code==RFL_OK ? "Font removed from the library":"Font was not removed (%.120s)",problem.message);
  return w3_rfl_status(code);
}
/* Produces a pending frame laid out with the leased face. The accepted pager keeps
   the previous face until READER_COMMIT; a refused or failed lease changes nothing. */
static exr_status w3_font_use(linux_reader *reader,reader_session *next,const reader_command *command,
                              reader_result *result,exr_error *error) {
  rfl_lease *lease=NULL;exr_font *font=reader->w3_base_font;rfl_error problem={0};char hash[RFL_HASH_BYTES]="";
  if(next->fixed_document) {
    snprintf(result->message,sizeof(result->message),"Reading font applies to text books; fixed pages keep their own fonts");return EXR_ARGUMENT;
  }
  if(command->w3_hash && command->w3_hash[0]) {
    exr_status ready=w3_fonts_ready(reader,result);
    if(ready!=EXR_OK) return ready;
    if(!w3_hash_valid(command->w3_hash)) return EXR_ARGUMENT;
    if(rfl_font_open(reader->w3_fonts,command->w3_hash,0,&lease,&problem)!=RFL_OK) {
      snprintf(result->message,sizeof(result->message),"Selected font could not be opened; previous font and page retained (%.80s)",problem.message);return EXR_FORMAT;
    }
    if(rfl_lease_font(lease,&font,&problem)!=RFL_OK) {
      rfl_lease_release(lease,&problem);
      snprintf(result->message,sizeof(result->message),"Selected font could not be used; previous font and page retained");return EXR_FORMAT;
    }
    g_strlcpy(hash,command->w3_hash,sizeof(hash));
  }
  exr_anchor point={0};exr_anchor_match match={0};size_t position=next->position;
  exr_status status=capture(reader,next,position,position,&point,error);
  if(status==EXR_OK) {
    exr_font *previous=reader->font;
    next->pager=NULL;reader->font=font;
    status=pager_create(reader,next,next->part,next->font,&next->pager,error);
    reader->font=previous;
  }
  if(status==EXR_OK) {
    status=next->bounded ? exr_pager_anchor_resolve(next->pager,&point,&reader->control,&match,error):
      exr_anchor_resolve_ex(next->document,&point,&reader->control,&match,error);
    if(status==EXR_OK && match.state==EXR_ANCHOR_FOUND) position=match.start;
    else if(status==EXR_OK) {
      next->hold_progress=1;strcpy(result->message,"Position not unique; retained chapter offset, stored point unchanged");
    }
  }
  if(status==EXR_OK && position>extent(next)) status=EXR_ARGUMENT;
  if(status==EXR_OK) { status=render(reader,next,0,1,position,result,error);next->position=position; }
  exr_anchor_free(&point);
  if(status!=EXR_OK) {
    if(lease) rfl_lease_release(lease,&problem);
    if(!result->message[0]) snprintf(result->message,sizeof(result->message),"Reading font could not be applied; previous font and page retained");
    return status;
  }
  reader->w3_candidate_lease=lease;reader->w3_candidate_font=font;reader->w3_candidate_pending=1;
  g_strlcpy(reader->w3_candidate_hash,hash,sizeof(reader->w3_candidate_hash));
  return EXR_OK;
}

typedef struct { linux_reader *reader;int preview;uint64_t records;char title[256]; } w3_import;
static int w3_import_cancel(void *opaque) { return cancel(((w3_import *)opaque)->reader)==EXR_CANCELLED; }
static int w3_import_metadata(void *opaque,const reader_annotation_import_metadata *meta) {
  w3_import *run=opaque;
  if(meta->annotation_id) run->records++;
  else if(meta->book_title) g_strlcpy(run->title,meta->book_title,sizeof(run->title));
  /* The header precedes every commit, so stopping here previews a fully validated file. */
  return run->preview && !meta->annotation_id;
}
static int w3_import_item(void *opaque,const reader_annotation_import_item *item) {
  (void)item;return cancel(((w3_import *)opaque)->reader)==EXR_CANCELLED;
}
static exr_status w3_annotation(linux_reader *reader,const reader_command *command,reader_result *result) {
  records_book book={0};received_owner *owner=NULL;
  exr_status status=records_book_identity(reader,command,result,&book);
  if(status==EXR_OK) status=received_ready(reader,&owner);
  if(status!=EXR_OK) { snprintf(result->message,sizeof(result->message),"Open the book first; annotation import needs its verified original identity");records_book_free(&book);return status; }
  w3_import run;memset(&run,0,sizeof(run));run.reader=reader;run.preview=command->action==READER_W3_ANNOTATION_PREVIEW;
  reader_annotation_import_options options={0};options.struct_size=sizeof(options);options.revisions=owner->revisions;
  options.jsonl_path=command->w3_path;options.target_book_key=result->records_key;
  options.cancel=w3_import_cancel;options.item=w3_import_item;options.metadata=w3_import_metadata;options.context=&run;
  reader_annotation_import_stats stats={0};reader_annotation_import_error problem={0};
  reader_annotation_import_status code=reader_annotation_import_run(&options,&stats,&problem);
  result->has_w3=1;result->w3_ann_code=(int)code;result->w3_ann_validated=stats.validated;
  result->w3_ann_bytes=stats.input_bytes;result->w3_ann_annotations=stats.annotations;result->w3_ann_heads=stats.head_wires;
  result->w3_ann_omitted=stats.omitted_history;result->w3_ann_created=stats.created;result->w3_ann_duplicates=stats.duplicates;
  result->w3_ann_committed=stats.committed;g_strlcpy(result->w3_ann_title,run.title,sizeof(result->w3_ann_title));
  if(run.preview && code==READER_AI_CANCELLED && stats.validated) {
    status=EXR_OK;
    snprintf(result->message,sizeof(result->message),"Annotation file checked; nothing has been imported yet");
  } else if(code==READER_AI_OK) {
    status=EXR_OK;
    snprintf(result->message,sizeof(result->message),"Imported annotations: %llu new, %llu already present",
      (unsigned long long)stats.created,(unsigned long long)stats.duplicates);
  } else {
    status=code==READER_AI_CANCELLED ? EXR_CANCELLED:EXR_FORMAT;
    snprintf(result->message,sizeof(result->message),"Annotation file refused: %.120s",problem.message);
  }
  records_book_free(&book);return status;
}

static int w3_roe_enter(void *context) {
  linux_reader *reader=context;
  if(reader->w3_export_depth) return 1;
  reader->w3_export_depth=1;return 0;
}
static void w3_roe_leave(void *context) { ((linux_reader *)context)->w3_export_depth=0; }
static int w3_roe_cancelled(void *context) { return cancel((linux_reader *)context)==EXR_CANCELLED; }
static void w3_roe_progress(void *context,size_t index,roe_event event,const roe_item *item) {
  (void)context;(void)index;(void)event;(void)item;
}
static void w3_slug(linux_reader *reader,char slug[65]) {
  exr_book *books=NULL;size_t count=0;exr_error error={0};size_t used=0;
  strcpy(slug,"book");
  if(exr_library_books(reader->library,"",&books,&count,&error)==EXR_OK) {
    for(size_t i=0;i<count;i++) if(books[i].id==reader->current.id && books[i].title) {
      char text[65];used=0;
      for(const char *p=books[i].title;*p && used<48;p++) {
        if(g_ascii_isalnum(*p)) text[used++]=*p;
        else if((*p==' ' || *p=='-' || *p=='_') && used && text[used-1]!='-') text[used++]='-';
      }
      while(used && text[used-1]=='-') used--;
      if(used) { memcpy(slug,text,used);slug[used]=0; }
      break;
    }
  }
  exr_books_free(books,count);
}
static exr_status w3_export(linux_reader *reader,const reader_command *command,reader_result *result) {
  result->has_w3=1;
  if(!reader->current.id || reader->current.id!=command->book) {
    snprintf(result->message,sizeof(result->message),"Open the book first; original export uses the current book");return EXR_ARGUMENT;
  }
  if(!reader->w3_exporter) {
    /* The owner gate lives in the reader, which outlives the exporter. */
    reader->w3_owner.enter=w3_roe_enter;reader->w3_owner.leave=w3_roe_leave;reader->w3_owner.context=reader;
    roe_status created=roe_create(reader->library,&reader->w3_owner,&reader->w3_exporter);
    if(created!=ROE_OK) { snprintf(result->message,sizeof(result->message),"Original export is unavailable (code %d)",(int)created);return EXR_IO; }
  }
  char slug[65];w3_slug(reader,slug);
  roe_selection selection={reader->current.id,slug};roe_result *run=NULL;
  roe_options options={0};options.directory=command->w3_path;options.naming=ROE_DISPLAY_NAME;
  options.callbacks.cancelled=w3_roe_cancelled;options.callbacks.progress=w3_roe_progress;options.callbacks.context=reader;
  roe_status code=roe_run(reader->w3_exporter,&selection,1,&options,&run);
  result->w3_export_code=(int)code;
  if(run && run->count) {
    const roe_item *item=&run->items[0];
    result->w3_export_sdk=(int)item->sdk_status;result->w3_export_created=item->created;
    result->w3_export_durable=item->durable;result->w3_export_bytes=item->bytes;
    g_strlcpy(result->w3_export_path,item->output_path,sizeof(result->w3_export_path));
  }
  exr_status status=code==ROE_OK ? EXR_OK:code==ROE_CANCELLED ? EXR_CANCELLED:code==ROE_CONFLICT ? EXR_ARGUMENT:EXR_IO;
  if(code==ROE_OK) snprintf(result->message,sizeof(result->message),result->w3_export_created ? "Original exported unchanged":"The same original is already in that folder");
  else snprintf(result->message,sizeof(result->message),"Original was not exported (code %d); the book and library are unchanged",(int)code);
  roe_result_free(run);return status;
}

static exr_status w3_sync(linux_reader *reader,const reader_command *command,reader_result *result) {
  result->has_w3=1;
  if(!command->w3_session) {
    result->w3_sync_text=g_strdup("No sync session is active in this window. Choose Sync library to start one; nothing is sent from this view.");
    return EXR_OK;
  }
  received_owner *owner=NULL;exr_status status=received_ready(reader,&owner);
  if(status!=EXR_OK) return status;
  reader_sync_view_options options={0};options.row_limit=20;options.detect_conflicts=1;
  reader_sync_view_snapshot *snapshot=NULL;reader_sync_view_error problem={0};
  reader_sync_view_status code=reader_sync_view_capture((reader_account_session *)command->w3_session,owner->revisions,&options,&snapshot,&problem);
  result->w3_sync_code=(int)code;
  if(code!=READER_SYNC_VIEW_OK) {
    result->w3_sync_text=g_strdup_printf("Sync status could not be read: %s",problem.message);return EXR_DATABASE;
  }
  reader_sync_view_summary summary;memset(&summary,0,sizeof(summary));
  reader_sync_view_summary_get(snapshot,&summary);
  GString *text=g_string_new(NULL);
  g_string_append_printf(text,"Phase: %s\nReason: %s\nSweeps completed: %llu · Operations: %llu (pushed %llu, pulled %llu, originals verified %llu)\n",
    reader_sync_view_phase_text(summary.phase),reader_sync_view_reason_text(summary.reason),
    (unsigned long long)summary.completed_sweeps,(unsigned long long)summary.operations,(unsigned long long)summary.pushed_operations,
    (unsigned long long)summary.pulled_operations,(unsigned long long)summary.originals_verified_operations);
  g_string_append_printf(text,"Shards: %u of %u · Resumable: %s · Whole library synchronized: no\n",
    summary.completed_shards,summary.shard_count,summary.resumable ? "yes":"no");
  g_string_append_printf(text,"Pending records: %zu%s · Retried: %zu · Conflicts: %zu\n",
    summary.pending_records,summary.more_may_exist ? " (more may follow)":"",summary.retried_records,summary.conflict_records);
  reader_sync_view_row rows[20];size_t copied=0;
  if(reader_sync_view_rows(snapshot,0,rows,20,&copied)==READER_SYNC_VIEW_OK) {
    for(size_t i=0;i<copied;i++)
      g_string_append_printf(text,"%s %s %s · %llu bytes · attempts %lld%s\n",rows[i].operation,rows[i].entity_kind,rows[i].revision_id,
        (unsigned long long)rows[i].bytes,(long long)rows[i].attempts,rows[i].conflict ? " · conflict":"");
  }
  g_string_append_printf(text,"Pending count: %zu\n",summary.pending_records);
  result->w3_sync_text=g_string_free(text,FALSE);
  reader_sync_view_release(&snapshot);return EXR_OK;
}

static void w3_execute(linux_reader *reader,const reader_command *command,reader_result *result) {
  result->has_w3=1;
  switch(command->action) {
    case READER_W3_ANNOTATION_PREVIEW: case READER_W3_ANNOTATION_IMPORT: result->status=w3_annotation(reader,command,result);break;
    case READER_W3_EXPORT: result->status=w3_export(reader,command,result);break;
    case READER_W3_SYNC_STATUS: result->status=w3_sync(reader,command,result);break;
    default: {
      exr_status status=w3_fonts_ready(reader,result);
      if(status==EXR_OK && command->action==READER_W3_FONT_IMPORT) status=w3_font_import(reader,command,result);
      if(status==EXR_OK && command->action==READER_W3_FONT_REMOVE) status=w3_font_remove(reader,command,result);
      /* The retained set is listed even after a refused import or removal. */
      if(reader->w3_fonts) { exr_status listed=w3_font_list(reader,result);if(status==EXR_OK) status=listed; }
      result->status=status;
    }
  }
  if(!result->message[0]) snprintf(result->message,sizeof(result->message),"%s",result->status==EXR_OK ? "Ready":"Operation did not complete; the library and book are unchanged");
}
/* Same landing proof as a saved record: an independent session must resolve FOUND
   before the visible session moves, and READER_COMMIT alone completes the cursor. */
static exr_status w3_history_jump(linux_reader *reader,reader_session *next,const reader_command *command,
                                  reader_result *result,exr_error *error) {
  received_owner *owner=NULL;char key[73];reader_jh_item item;reader_jh_error problem={0};
  reader_rs_record decoded={0};reader_rs_error decode_problem={0};reader_session independent={0};
  exr_anchor_match first={0},second={0};size_t unit=0;
  memset(&item,0,sizeof(item));result->has_w3=1;
  exr_status status=w3_history_ready(reader);
  if(status==EXR_OK) status=w3_book_key(reader,key);
  if(status==EXR_OK) status=received_ready(reader,&owner);
  if(status==EXR_OK) {
    reader_jh_status code=reader_jh_peek(reader->w3_history,command->direction<0 ? READER_JH_BACK:READER_JH_FORWARD,&item,&problem);
    if(code==READER_JH_EMPTY) {
      snprintf(result->message,sizeof(result->message),command->direction<0 ? "No earlier reading position":"No later reading position");status=EXR_ARGUMENT;
    } else if(code!=READER_JH_OK) status=EXR_DATABASE;
  }
  if(status==EXR_OK && strcmp(item.book_key,key)) {
    snprintf(result->message,sizeof(result->message),"That position belongs to another book; open it from the shelf. History unchanged");status=EXR_ARGUMENT;
  }
  if(status==EXR_OK && reader_rs_decode(owner->revisions,item.wire,item.wire_bytes,&decoded,&decode_problem)!=READER_RS_OK) status=EXR_ARGUMENT;
  if(status==EXR_OK) status=records_resolve(reader,&decoded,&independent,&first,&unit,error);
  if(status==EXR_OK) {
    if(next->fixed_document && decoded.mode==READER_RS_FIXED_PAGE) {
      size_t current_page=0;reader_rs_status code=reader_rs_resolve_fixed(next->fixed_document,&decoded,&reader->control,&current_page,&second,&decode_problem);
      if(code!=READER_RS_OK || second.state!=EXR_ANCHOR_FOUND || current_page!=unit || first.start!=second.start || first.end!=second.end) status=EXR_ARGUMENT;
      else status=render_fixed(reader,next,unit,result,error);
    } else if(next->bounded && decoded.mode==READER_RS_EPUB_CHAPTER) {
      size_t part_index=0;
      if(reader_rs_epub_record_part(next->publication,&decoded,&part_index,&decode_problem)!=READER_RS_OK || part_index!=unit) status=EXR_ARGUMENT;
      else {
        next->pager=NULL;next->part=unit;status=pager_create(reader,next,unit,next->font,&next->pager,error);
        if(status==EXR_OK && reader_rs_resolve_epub(next->publication,next->pager,unit,&decoded,&reader->control,&second,&decode_problem)!=READER_RS_OK) status=EXR_ARGUMENT;
        if(status==EXR_OK && (second.state!=EXR_ANCHOR_FOUND || first.start!=second.start || first.end!=second.end)) status=EXR_ARGUMENT;
        if(status==EXR_OK) status=render(reader,next,0,1,second.start,result,error);
      }
    } else if(next->document && !next->bounded && decoded.mode==READER_RS_REFLOW_GLOBAL) {
      if(reader_rs_resolve_reflow(next->document,&decoded,&reader->control,&second,&decode_problem)!=READER_RS_OK || second.state!=EXR_ANCHOR_FOUND ||
         first.start!=second.start || first.end!=second.end) status=EXR_ARGUMENT;
      else status=render(reader,next,0,1,second.start,result,error);
    } else status=EXR_ARGUMENT;
    if(status==EXR_OK) {
      next->position=next->fixed_document ? unit:second.start;
      result->select_range=1;result->selected_start=second.start;result->selected_end=second.end;
    }
  }
  if(status==EXR_OK) { reader->w3_item=item;reader->w3_item_valid=1; }
  else {
    reader_jh_item_release(&item);
    if(!result->message[0]) snprintf(result->message,sizeof(result->message),"History position was not independently proved; reading unchanged");
  }
  reader_rs_record_free(&decoded);session_free(&independent);return status;
}
