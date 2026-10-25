/* The uninstalled probe compiles the literal actual GTK worker source with
   the actual target's definitions. No SDK version tag or owner logic changes. */
#include REAL_READING_SOURCE
#include <signal.h>

static FILE *compat_report;
static unsigned compat_checks;
static char compat_revisions[32][33];
static size_t compat_revision_count;
static const char *compat_profile;
static int compat_created=-1;
static char compat_parser[65],compat_retry_revision[33];

static void compat_check(int ok,const char *name) {
  if(compat_checks++) fputs(",",compat_report);
  fprintf(compat_report,"{\"name\":\"%s\",\"passed\":%s}",name,ok ? "true":"false");fflush(compat_report);
  if(!ok) { fprintf(stderr,"compatibility check failed: %s runtime=%s\n",name,exr_version());exit(1); }
}
static void compat_mark(const char *stage) {
  const char *path=getenv("GTK_RECORD_KILL_MARKER");
  if(!path) return;
  int file=open(path,O_WRONLY|O_CREAT|O_EXCL|O_CLOEXEC,0600);
  if(file<0 || write(file,stage,strlen(stage))!=(ssize_t)strlen(stage) || fsync(file)) _exit(99);
  close(file);raise(SIGSTOP);
}
reader_rc_status __real_reader_rc_apply(const reader_rc_context *,const reader_rc_command *,reader_rc_result *,reader_rc_error *);
reader_rc_status __wrap_reader_rc_apply(const reader_rc_context *context,const reader_rc_command *command,
    reader_rc_result *result,reader_rc_error *error) {
  const char *stage=getenv("GTK_RECORD_KILL_STAGE");
  if(stage && !strcmp(stage,"before")) compat_mark("before-product-commit");
  reader_rc_status status=__real_reader_rc_apply(context,command,result,error);
  if(stage && !strcmp(stage,"after") && status==READER_RC_OK) compat_mark("after-product-commit-before-pending-clear");
  return status;
}
static reader_command compat_command(reader_action action) {
  reader_command command={0};command.action=action;command.book=1;command.font=24;command.zoom=100;command.records_token=1;return command;
}
static void compat_commit(linux_reader *reader,reader_result *frame) {
  reader_command command=compat_command(READER_COMMIT);command.book=frame->book;command.part=frame->part;command.page=frame->page;command.start=frame->start;
  reader_result result={0};linux_reader_execute(reader,&command,&result);compat_check(result.status==EXR_OK,"actual owner accepts frame commit");reader_result_free(&result);
}
static received_owner *compat_owner(linux_reader *reader) {
  received_owner *owner=NULL;compat_check(received_ready(reader,&owner)==EXR_OK && owner,"actual account revisions owner ready");return owner;
}
static void compat_list(linux_reader *reader,reader_result *result) {
  reader_command command=compat_command(READER_RECORDS_LIST);linux_reader_execute(reader,&command,result);
  compat_check(result->status==EXR_OK && result->records_page.complete && !result->has_frame,"actual owner bounded records list complete");
}
static void compat_save(linux_reader *reader,int kind,const char *text,char annotation[33],char revision[33]) {
  reader_command command=compat_command(READER_RECORDS_SAVE);command.records_kind=kind;command.records_operation=READER_RC_PUT;
  command.records_text=text;command.start=0;command.end=6;reader_result result={0};linux_reader_execute(reader,&command,&result);
  compat_check(result.status==EXR_OK && result.records_created==1 && !result.records_pending && !result.has_frame,"actual owner saves fresh product record once");
  if(annotation) g_strlcpy(annotation,result.records_annotation,33);
  if(revision) g_strlcpy(revision,result.records_revision,33);
  g_strlcpy(compat_revisions[compat_revision_count++],result.records_revision,33);reader_result_free(&result);
}
static void compat_mutate(linux_reader *reader,const char *annotation,int kind,int operation,const char *text,const char *version) {
  reader_result listed={0};compat_list(reader,&listed);reader_av_item *item=NULL;
  for(size_t i=0;i<listed.records_page.count;i++) if(!strcmp(listed.records_page.items[i].annotation_id,annotation)) item=&listed.records_page.items[i];
  compat_check(item && item->state==READER_AV_STATE_SAFE,"actual owner mutation sees exact safe current head");
  reader_command command=compat_command(READER_RECORDS_SAVE);command.records_kind=kind;command.records_operation=operation;
  command.records_id=annotation;command.records_head=item->revision_id;command.records_sha=item->sha256;command.records_text=text;command.records_version=version;
  reader_result result={0};linux_reader_execute(reader,&command,&result);
  compat_check(result.status==EXR_OK && result.records_created==1 && !result.records_pending,"actual owner edit delete or restore commits");
  g_strlcpy(compat_revisions[compat_revision_count++],result.records_revision,33);
  reader_result_free(&result);reader_result_free(&listed);
}
static void compat_original(linux_reader *reader,const char *path) {
  gchar *expected=NULL;gsize length=0;compat_check(g_file_get_contents(path,&expected,&length,NULL),"independent original file available");
  exr_source source={0};exr_error error={0};compat_check(exr_library_source(reader->library,1,&source,&error)==EXR_OK,"public stored original source opens");
  compat_check(source.size==(uint64_t)length,"stored original advertised byte extent exact");
  unsigned char bytes[65536];uint64_t offset=0;
  while(offset<source.size) {
    size_t wanted=source.size-offset>sizeof(bytes) ? sizeof(bytes):(size_t)(source.size-offset);
    size_t got=source.read_at(source.context,offset,bytes,wanted);
    compat_check(got==wanted && !memcmp(expected+offset,bytes,wanted),"public stored original block byte identical");offset+=wanted;
  }
  source.release(source.context);g_free(expected);
}
static void compat_v1(linux_reader *reader,const char *key) {
  exr_anchor anchor={0};exr_fixed_anchor fixed={0};reader_rs_capture captured={0};exr_error sdk={0};
  size_t unit=reader->current.fixed_document ? reader->current.page:reader->current.part;
  if(reader->current.fixed_document && reader->current.end==0) return;
  compat_check(records_capture(reader,&reader->current,unit,0,6,&captured,&anchor,&fixed,&sdk)==EXR_OK,"old owner helper obtains genuine public range capture");
  reader_rs_gap gap=reader_rs_classify(&captured);
  if(gap==READER_RS_GAP_NONE) {
    received_owner *owner=compat_owner(reader);char annotation[33],revision[33];
    compat_check(reader_revision_new_id(annotation,NULL)==READER_REV_OK && reader_revision_new_id(revision,NULL)==READER_REV_OK,"legacy v1 identity allocated publicly");
    reader_rs_envelope envelope={revision,"put","annotation",key,annotation,NULL,0,"public legacy v1 range",exr_version()};
    char *wire=NULL;size_t size=0;reader_rs_error error={0};reader_revision_info info={0};int created=0;
    compat_check(reader_rs_encode(owner->revisions,&envelope,&captured,&wire,&size,&error)==READER_RS_OK,"genuine old capture losslessly encodes public anchor v1");
    compat_check(reader_revision_local_reading(owner->revisions,wire,size,NULL,0,&info,&created,NULL)==READER_REV_OK && created,"old process retains real public v1 revision");
    g_strlcpy(compat_revisions[compat_revision_count++],revision,33);reader_rs_free(wire);
  } else compat_check(gap==READER_RS_GAP_CHAPTER_SCOPE,"unrepresentable v1 chapter scope remains explicit");
  exr_anchor_free(&anchor);exr_fixed_anchor_free(&fixed);
}
static void compat_snapshot(linux_reader *reader) {
  char *native=g_build_filename(compat_profile,"native-position.tsv",NULL);FILE *position=fopen(native,"wb");g_free(native);
  compat_check(position!=NULL,"old actual SDK progress inventory opens");fprintf(position,"%zu %zu %zu\n",reader->current.part,reader->current.page,reader->current.position);fclose(position);
  char *path=g_build_filename(compat_profile,"old-revisions.tsv",NULL);FILE *out=fopen(path,"wb");g_free(path);compat_check(out!=NULL,"old immutable wire inventory opens");
  received_owner *owner=compat_owner(reader);
  for(size_t i=0;i<compat_revision_count;i++) {
    char *wire=NULL;size_t size=0;reader_revision_info info={0};
    compat_check(reader_revision_get(owner->revisions,compat_revisions[i],&wire,&size,&info,NULL)==READER_REV_OK,"public old revision readback available");
    gchar *sha=g_compute_checksum_for_data(G_CHECKSUM_SHA256,(guchar *)wire,size);
    fprintf(out,"%s\t%s\t%zu\n",info.revision_id,sha,size);
    char *name=g_strconcat(info.revision_id,".json",NULL);path=g_build_filename(compat_profile,name,NULL);
    compat_check(g_file_set_contents(path,wire,(gssize)size,NULL),"old original wire copy retained without normalization");
    g_free(path);g_free(name);g_free(sha);reader_revision_bytes_free(wire);
  }
  fclose(out);
}
static int compat_equal(const char *a,const char *b,size_t size) { return (!size || (a && b && !memcmp(a,b,size))); }
static void compat_adopt(linux_reader *reader,const char *annotation,const char *revision,const char *sha,int progress) {
  received_owner *owner=compat_owner(reader);char *wire=NULL;size_t bytes=0;reader_revision_info info={0};reader_rs_record decoded={0};
  compat_check(reader_revision_get(owner->revisions,revision,&wire,&bytes,&info,NULL)==READER_REV_OK && !strcmp(info.sha256,sha),"selected immutable wire identity read publicly");
  compat_check(reader_rs_decode(owner->revisions,wire,bytes,&decoded,NULL)==READER_RS_OK,"selected original record decodes without tag rewrite");
  reader_command command=compat_command(READER_RECORDS_JUMP);command.records_id=annotation;command.records_head=revision;command.records_sha=sha;command.records_progress=progress;
  reader_result result={0};linux_reader_execute(reader,&command,&result);
  if(result.status!=EXR_OK || !result.has_frame || result.records_match!=EXR_ANCHOR_FOUND)
    fprintf(stderr,"adopt progress=%d annotation=%s revision=%s mode=%d anchor_version=%llu parser=%s part=%llu route=%s page=%llu range=%llu..%llu current_part=%zu current_page=%zu status=%d frame=%d match=%d message=%s\n",
      progress,annotation ? annotation:"",revision,(int)decoded.mode,(unsigned long long)decoded.anchor_version,decoded.parser_version,
      (unsigned long long)decoded.part,decoded.part_path ? decoded.part_path:"",(unsigned long long)decoded.page,
      (unsigned long long)decoded.start,(unsigned long long)decoded.end,reader->current.part,reader->current.page,
      result.status,result.has_frame,result.records_match,result.message);
  compat_check(result.status==EXR_OK && result.has_frame && result.records_match==EXR_ANCHOR_FOUND,"actual GTK jump independently proves FOUND and emits accepted frame");
  compat_check(result.note_count==0,"product record adoption never invents an SDK note");
  compat_check(result.selected_start==decoded.start && result.selected_end==decoded.end,"actual GTK landing exactly matches retained selector range");
  compat_commit(reader,&result);reader_result_free(&result);
  reader_rs_capture captured={0};exr_anchor anchor={0};exr_fixed_anchor fixed={0};exr_error error={0};
  size_t unit=reader->current.fixed_document ? reader->current.page:reader->current.part;
  compat_check(records_capture(reader,&reader->current,unit,(size_t)decoded.start,(size_t)decoded.end,&captured,&anchor,&fixed,&error)==EXR_OK,"accepted actual GTK session publicly recaptures original selector");
  compat_check(captured.mode==decoded.mode,"recapture preserves original location kind");
  if(captured.mode==READER_RS_FIXED_PAGE) {
    compat_check(!strcmp(fixed.page_id,decoded.page_id) && captured.page==decoded.page && fixed.exact_size==decoded.exact_size && fixed.prefix_size==decoded.prefix_size && fixed.suffix_size==decoded.suffix_size &&
      compat_equal(fixed.exact,decoded.exact,decoded.exact_size) && compat_equal(fixed.prefix,decoded.prefix,decoded.prefix_size) && compat_equal(fixed.suffix,decoded.suffix,decoded.suffix_size),"fixed recapture exact page identity and all selector bytes");
  } else {
    compat_check(anchor.start==decoded.start && anchor.end==decoded.end && !strcmp(anchor.exact,decoded.exact) && !strcmp(anchor.prefix ? anchor.prefix:"",decoded.prefix ? decoded.prefix:"") && !strcmp(anchor.suffix ? anchor.suffix:"",decoded.suffix ? decoded.suffix:""),"reflow recapture all original selector bytes exact");
    if(captured.mode==READER_RS_EPUB_CHAPTER) compat_check(captured.part_path && !strcmp(captured.part_path,decoded.part_path),"EPUB recapture retains exact original route");
  }
  exr_anchor_free(&anchor);exr_fixed_anchor_free(&fixed);reader_rs_record_free(&decoded);reader_revision_bytes_free(wire);
}
static void compat_verify(linux_reader *reader) {
  char *native=g_build_filename(compat_profile,"native-position.tsv",NULL);FILE *position=fopen(native,"rb");g_free(native);size_t part=0,page=0,offset=0;
  compat_check(position && fscanf(position,"%zu %zu %zu",&part,&page,&offset)==3,"old SDK progress inventory retained");fclose(position);
  compat_check(reader->current.part==part && reader->current.page==page && reader->current.position==offset,"actual reopened GTK accepts exact old SDK progress");
  received_owner *owner=compat_owner(reader);char *path=g_build_filename(compat_profile,"old-revisions.tsv",NULL);FILE *input=fopen(path,"rb");g_free(path);
  compat_check(input!=NULL,"original process immutable inventory exists");
  char revision[33],sha[65];size_t bytes;
  while(fscanf(input,"%32s\t%64s\t%zu",revision,sha,&bytes)==3) {
    char *wire=NULL;size_t size=0;reader_revision_info info={0};
    compat_check(reader_revision_get(owner->revisions,revision,&wire,&size,&info,NULL)==READER_REV_OK && size==bytes && !strcmp(info.sha256,sha),"every old edit delete restore revision remains byte identical");
    char *name=g_strconcat(revision,".json",NULL);path=g_build_filename(compat_profile,name,NULL);gchar *copy=NULL;gsize copied=0;
    compat_check(g_file_get_contents(path,&copy,&copied,NULL) && copied==size && !memcmp(copy,wire,size),"old complete wire including parser and parents is not rewritten");
    g_free(path);g_free(name);g_free(copy);reader_revision_bytes_free(wire);
  }
  fclose(input);reader_result listed={0};compat_list(reader,&listed);
  compat_check(listed.records_progress_state==READER_SELECTION_SAFE && !listed.records_progress_deleted,"old product progress remains a safe selected head");
  compat_adopt(reader,NULL,listed.records_progress_head,listed.records_progress_sha,1);
  for(size_t i=0;i<listed.records_page.count;i++) {
    reader_av_item *item=&listed.records_page.items[i];compat_check(item->state==READER_AV_STATE_SAFE,"old annotation history remains SAFE");
    if(item->deleted) {
      reader_command command=compat_command(READER_RECORDS_JUMP);command.records_id=item->annotation_id;command.records_head=item->revision_id;command.records_sha=item->sha256;
      reader_result result={0};linux_reader_execute(reader,&command,&result);compat_check(result.status!=EXR_OK && !result.has_frame,"actual host refuses tombstone navigation without guessed fallback");reader_result_free(&result);
    } else compat_adopt(reader,item->annotation_id,item->revision_id,item->sha256,0);
  }
  reader_result_free(&listed);
}
int main(int argc,char **argv) {
  if(argc!=8) return 2;
  compat_profile=argv[1];compat_report=fopen(argv[5],"wb");if(!compat_report) return 2;
  fprintf(compat_report,"{\"runtime_version\":\"%s\",\"mode\":\"%s\",\"checks\":[",exr_version(),argv[4]);
  compat_check(!strcmp(exr_version(),argv[6]),"actual linked SDK runtime version exact");
  char *database=g_build_filename(argv[1],"library.sqlite",NULL);linux_reader *reader=NULL;exr_error error={0};
  compat_check(linux_reader_open(database,argv[2],NULL,&reader,&error)==EXR_OK,"real GTK owner opens profile in new process");
  reader_command command=compat_command(!strcmp(argv[4],"seed") ? READER_IMPORT:READER_OPEN);command.path=argv[3];reader_result frame={0};
  linux_reader_execute(reader,&command,&frame);compat_check(frame.status==EXR_OK && frame.has_frame,"actual host imports or reopens same stored original");compat_commit(reader,&frame);reader_result_free(&frame);
  compat_original(reader,argv[3]);
  if(!strcmp(argv[4],"seed")) {
    for(unsigned i=0;i<20 && reader->current.bounded && reader->current.part!=1;i++) { command=compat_command(READER_NEXT);linux_reader_execute(reader,&command,&frame);compat_check(frame.status==EXR_OK && frame.has_frame,"real EPUB navigation reaches unique legacy route");compat_commit(reader,&frame);reader_result_free(&frame); }
    if(reader->current.fixed_document && reader->current.end==0) { command=compat_command(READER_NEXT);linux_reader_execute(reader,&command,&frame);compat_check(frame.status==EXR_OK && frame.has_frame,"real CBZ navigation reaches original page one");compat_commit(reader,&frame);reader_result_free(&frame); }
    char bookmark[33],root[33],edited[33],deleted[33];
    compat_save(reader,READER_RC_PROGRESS,"",NULL,NULL);compat_save(reader,READER_RC_BOOKMARK,"old bookmark",bookmark,root);
    int textful=!reader->current.fixed_document || reader->current.end>0;
    compat_save(reader,textful ? READER_RC_HIGHLIGHT:READER_RC_BOOKMARK,"old note",edited,NULL);
    compat_mutate(reader,edited,READER_RC_NOTE_TEXT,READER_RC_PUT,"old edited note",NULL);
    compat_mutate(reader,bookmark,READER_RC_BOOKMARK,READER_RC_DELETE,NULL,NULL);
    compat_mutate(reader,bookmark,READER_RC_BOOKMARK,READER_RC_RESTORE,NULL,root);
    compat_save(reader,READER_RC_BOOKMARK,"retained tombstone",deleted,NULL);compat_mutate(reader,deleted,READER_RC_BOOKMARK,READER_RC_DELETE,NULL,NULL);
    reader_result listed={0};compat_list(reader,&listed);compat_v1(reader,listed.records_key);reader_result_free(&listed);compat_snapshot(reader);
  } else if(!strcmp(argv[4],"verify")) compat_verify(reader);
  else if(!strcmp(argv[4],"pending")) compat_save(reader,READER_RC_BOOKMARK,"original uncertain old process request",NULL,NULL);
  else if(!strcmp(argv[4],"retry")) {
    GKeyFile *pending=NULL;compat_check(records_pending_read(reader,&pending)==1,"original private request retained before explicit retry");
    char *parser=g_key_file_get_string(pending,"request","parser",NULL),*id=g_key_file_get_string(pending,"request","revision",NULL),*capture_wire=g_key_file_get_string(pending,"request","capture",NULL);
    compat_check(!strcmp(parser,argv[7]),"original pending parser is retained without current-runtime relabel");
    int expected=getenv("GTK_RECORD_EXPECT_CREATED") ? atoi(getenv("GTK_RECORD_EXPECT_CREATED")):1;
    received_owner *owner=compat_owner(reader);char *prior=NULL;size_t prior_size=0;reader_revision_info prior_info={0};
    reader_revision_status prior_status=reader_revision_get(owner->revisions,id,&prior,&prior_size,&prior_info,NULL);
    compat_check(expected ? prior_status==READER_REV_NOT_FOUND:prior_status==READER_REV_OK,"new host open never auto-replays original uncertain request");reader_revision_bytes_free(prior);
    command=compat_command(READER_RECORDS_RETRY);reader_result result={0};linux_reader_execute(reader,&command,&result);
    compat_check(result.status==EXR_OK && result.records_created==expected && !result.records_pending && !strcmp(id,result.records_revision),"actual host explicit retry preserves original revision and created boundary");
    compat_created=result.records_created;g_strlcpy(compat_parser,parser,sizeof(compat_parser));g_strlcpy(compat_retry_revision,id,sizeof(compat_retry_revision));
    char *wire=NULL;size_t size=0;reader_revision_info info={0};reader_rs_record decoded={0},captured={0};
    compat_check(reader_revision_get(owner->revisions,id,&wire,&size,&info,NULL)==READER_REV_OK && reader_rs_decode(owner->revisions,wire,size,&decoded,NULL)==READER_RS_OK && reader_rs_decode(owner->revisions,capture_wire,strlen(capture_wire),&captured,NULL)==READER_RS_OK,"actual retry retains public validated original capture");
    compat_check(!strcmp(decoded.parser_version,parser) && decoded.start==captured.start && decoded.end==captured.end && !strcmp(decoded.exact,captured.exact),"retry keeps original parser and selector exact");
    compat_check(size==strlen(capture_wire) && !memcmp(wire,capture_wire,size),"retry product wire byte identical to original durable capture request");
    compat_adopt(reader,decoded.annotation_id,id,info.sha256,0);reader_rs_record_free(&decoded);reader_rs_record_free(&captured);reader_revision_bytes_free(wire);
    reader_result_free(&result);g_free(parser);g_free(id);g_free(capture_wire);g_key_file_free(pending);
  } else compat_check(0,"known process mode required");
  compat_original(reader,argv[3]);linux_reader_close(reader);g_free(database);
  fprintf(compat_report,"],\"accepted\":true,\"check_count\":%u,\"created\":%d,\"retained_parser\":\"%s\",\"retained_revision\":\"%s\"}\n",compat_checks,compat_created,compat_parser,compat_retry_revision);fclose(compat_report);return 0;
}
