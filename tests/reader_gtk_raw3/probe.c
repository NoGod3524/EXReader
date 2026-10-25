/* Uninstalled probe includes the literal actual worker and original helpers. */
#define main retained_original_compatibility_main
#include "../reader_gtk_record_compatibility/probe.c"
#undef main

reader_rc_status __real_reader_rc_apply_raw_v3(const reader_rc_context *,const reader_rc_command *,unsigned,reader_rc_result *,reader_rc_error *);
reader_rc_status __wrap_reader_rc_apply_raw_v3(const reader_rc_context *context,const reader_rc_command *command,
    unsigned version,reader_rc_result *result,reader_rc_error *error) {
  const char *stage=getenv("GTK_RECORD_KILL_STAGE");
  if(stage && !strcmp(stage,"before")) compat_mark("before-product-commit");
  reader_rc_status status=__real_reader_rc_apply_raw_v3(context,command,version,result,error);
  if(stage && !strcmp(stage,"after") && status==READER_RC_OK) compat_mark("after-product-commit-before-pending-clear");
  return status;
}
static void raw_save(linux_reader *reader,int kind,const char *body,char annotation[33],char revision[33]) {
  reader_command command=compat_command(READER_RECORDS_SAVE);command.records_kind=kind;command.records_operation=READER_RC_PUT;
  command.records_text=body;command.start=0;command.end=reader->current.end;
  reader_result result={0};linux_reader_execute(reader,&command,&result);
  if(result.status!=EXR_OK) fprintf(stderr,"save status=%d %s\n",result.status,result.message);
  compat_check(result.status==EXR_OK && result.records_created && !result.records_pending,"raw actual owner commits public capture once");
  if(annotation) g_strlcpy(annotation,result.records_annotation,33);
  if(revision) g_strlcpy(revision,result.records_revision,33);
  reader_result_free(&result);
}
static reader_rs_record raw_record(linux_reader *reader,const char *revision) {
  received_owner *owner=compat_owner(reader);char *wire=NULL;size_t size=0;reader_revision_info info={0};reader_rs_record record={0};
  compat_check(reader_revision_get_raw_v3(owner->revisions,revision,&wire,&size,&info,NULL)==READER_REV_OK &&
    reader_rs_decode_raw_v3(owner->revisions,wire,size,&record,NULL)==READER_RS_OK,"raw immutable wire decodes through explicit public capability");
  reader_revision_bytes_free(wire);return record;
}
static void raw_capture_equal(linux_reader *reader,const reader_rs_record *record) {
  exr_anchor anchor={0};exr_fixed_anchor fixed={0};reader_rs_capture capture={0};exr_error error={0};
  compat_check(records_capture(reader,&reader->current,reader->current.page,(size_t)record->start,(size_t)record->end,
    &capture,&anchor,&fixed,&error)==EXR_OK,"actual accepted owner captures the same SDK location");
  compat_check(record->anchor_version==3 && fixed.exact_size==record->exact_size && fixed.prefix_size==record->prefix_size &&
    fixed.suffix_size==record->suffix_size && !!fixed.exact==!!record->exact && !!fixed.prefix==!!record->prefix && !!fixed.suffix==!!record->suffix &&
    compat_equal(fixed.exact,record->exact,record->exact_size) && compat_equal(fixed.prefix,record->prefix,record->prefix_size) &&
    compat_equal(fixed.suffix,record->suffix,record->suffix_size),"actual SDK and retained anchor3 preserve every nullable selector byte");
  exr_anchor_free(&anchor);exr_fixed_anchor_free(&fixed);
}
static void raw_seed(linux_reader *reader) {
  exr_fixed_text *text=NULL;exr_error error={0};size_t bytes=0;
  compat_check(exr_fixed_load_text(reader->current.fixed_document,0,NULL,&text,&error)==EXR_OK,"actual 8845B PDF public text loads");
  const char *string=exr_fixed_text_string(text,&bytes);
  compat_check(bytes && memchr(string,0,bytes),"actual PDF SDK text includes NUL");exr_fixed_text_free(text);
  char point[33],point_revision[33],range[33],range_revision[33];
  raw_save(reader,READER_RC_PROGRESS,"",NULL,NULL);
  raw_save(reader,READER_RC_BOOKMARK,"raw point",point,point_revision);
  raw_save(reader,READER_RC_HIGHLIGHT,"raw full range",range,range_revision);
  reader_rs_record p=raw_record(reader,point_revision),r=raw_record(reader,range_revision);
  compat_check(p.start==p.end && memchr(p.suffix,0,p.suffix_size),"actual point suffix retains NUL");
  compat_check(r.end>r.start && memchr(r.exact,0,r.exact_size),"actual nonempty range retains NUL exact");
  raw_capture_equal(reader,&p);raw_capture_equal(reader,&r);reader_rs_record_free(&p);reader_rs_record_free(&r);
  compat_mutate(reader,range,READER_RC_NOTE_TEXT,READER_RC_PUT,"edited raw range",NULL);
  compat_mutate(reader,point,READER_RC_BOOKMARK,READER_RC_DELETE,NULL,NULL);
  compat_mutate(reader,point,READER_RC_BOOKMARK,READER_RC_RESTORE,NULL,point_revision);
  reader_result listed={0};compat_list(reader,&listed);
  for(size_t i=0;i<listed.records_page.count;i++) {
    reader_av_item *item=&listed.records_page.items[i];
    compat_check(item->anchor_version==3 && item->state==READER_AV_STATE_SAFE && !item->deleted,"raw edit and restore retain safe anchor3");
    compat_adopt(reader,item->annotation_id,item->revision_id,item->sha256,0);
  }
  reader_result_free(&listed);
}
static void raw_retry(linux_reader *reader) {
  GKeyFile *pending=NULL;compat_check(records_pending_read(reader,&pending)==1,"actual private intent survives process kill");
  int version=g_key_file_get_integer(pending,"request","version",NULL);
  char *revision=g_key_file_get_string(pending,"request","revision",NULL),*parser=g_key_file_get_string(pending,"request","parser",NULL);
  char *wire=g_key_file_get_string(pending,"request","capture",NULL);reader_rs_record captured={0};
  received_owner *owner=compat_owner(reader);
  if(version==2) {
    gsize size=0;guchar *bytes=g_base64_decode(wire,&size);
    compat_check(g_key_file_get_integer(pending,"request","writer_version",NULL)==3 &&
      reader_private_capture_decode(bytes,size,&captured)==EXR_OK,"new private intent preserves explicit native writer3 capture");g_free(bytes);
  } else compat_check(version==1 && reader_rs_decode_raw_v3(owner->revisions,wire,strlen(wire),&captured,NULL)==READER_RS_OK,"legacy intent is read unchanged with writer2");
  int expected=getenv("GTK_RECORD_EXPECT_CREATED") ? atoi(getenv("GTK_RECORD_EXPECT_CREATED")):1;
  reader_command command=compat_command(READER_RECORDS_RETRY);reader_result result={0};linux_reader_execute(reader,&command,&result);
  compat_check(result.status==EXR_OK && result.records_created==expected && !result.records_pending && !strcmp(revision,result.records_revision),"explicit retry preserves exact revision ID and before after created boundary");
  reader_rs_record retained=raw_record(reader,revision);
  compat_check(!strcmp(retained.parser_version,parser) && retained.start==captured.start && retained.end==captured.end &&
    (version==1 ? retained.anchor_version==2:retained.anchor_version==3),"retry preserves original parser range and explicit writer version");
  if(version==2) raw_capture_equal(reader,&retained);
  else {
    char *bytes=NULL;size_t size=0;reader_revision_info info={0};
    compat_check(reader_revision_get_raw_v3(owner->revisions,revision,&bytes,&size,&info,NULL)==READER_REV_OK &&
      size==strlen(wire) && !memcmp(bytes,wire,size),"legacy private intent commits byte identical original wire without migration");reader_revision_bytes_free(bytes);
  }
  compat_created=result.records_created;g_strlcpy(compat_retry_revision,revision,33);g_strlcpy(compat_parser,parser,sizeof(compat_parser));
  reader_rs_record_free(&retained);reader_rs_record_free(&captured);reader_result_free(&result);
  g_free(revision);g_free(parser);g_free(wire);g_key_file_free(pending);
}
static void raw_legacy_restore(linux_reader *reader) {
  reader_result listed={0};compat_list(reader,&listed);unsigned seen=0;
  for(size_t i=0;i<listed.records_page.count;i++) {
    reader_av_item *item=&listed.records_page.items[i];if(item->deleted || (item->anchor_version!=1 && item->anchor_version!=2)) continue;
    unsigned version=(unsigned)item->anchor_version;char revision[33],annotation[33];g_strlcpy(revision,item->revision_id,33);g_strlcpy(annotation,item->annotation_id,33);
    compat_mutate(reader,annotation,item->start==item->end ? READER_RC_BOOKMARK:READER_RC_HIGHLIGHT,READER_RC_DELETE,NULL,NULL);
    compat_mutate(reader,annotation,item->start==item->end ? READER_RC_BOOKMARK:READER_RC_HIGHLIGHT,READER_RC_RESTORE,NULL,revision);
    reader_rs_record record=raw_record(reader,compat_revisions[compat_revision_count-1]);
    compat_check(record.anchor_version==version,"actual raw owner restore retains historical v1 or v2 representation");reader_rs_record_free(&record);seen|=1u<<version;
  }
  compat_check(seen==6,"actual raw owner restored both retained v1 and v2 sources");reader_result_free(&listed);
}
int main(int argc,char **argv) {
  if(argc!=7) return 2;
  compat_profile=argv[1];compat_report=fopen(argv[5],"wb");if(!compat_report) return 2;
  fprintf(compat_report,"{\"runtime_version\":\"%s\",\"mode\":\"%s\",\"checks\":[",exr_version(),argv[4]);
  compat_check(!strcmp(exr_version(),"3.40.0"),"raw owner uses actual frozen SDK core runtime");
  char *database=g_build_filename(argv[1],"library.sqlite",NULL);linux_reader *reader=NULL;exr_error error={0};
  compat_check(linux_reader_open(database,argv[2],NULL,&reader,&error)==EXR_OK,"actual raw GTK owner opens its profile");
  reader_command command=compat_command(!strcmp(argv[4],"seed") ? READER_IMPORT:READER_OPEN);command.path=argv[3];reader_result frame={0};
  linux_reader_execute(reader,&command,&frame);compat_check(frame.status==EXR_OK && frame.has_frame,"actual raw owner imports or reopens stored original");compat_commit(reader,&frame);reader_result_free(&frame);
  compat_original(reader,argv[3]);
  if(!strcmp(argv[4],"seed")) raw_seed(reader);
  else if(!strcmp(argv[4],"pending")) raw_save(reader,READER_RC_BOOKMARK,"uncertain raw native capture",NULL,NULL);
  else if(!strcmp(argv[4],"retry")) raw_retry(reader);
  else if(!strcmp(argv[4],"legacy-restore")) raw_legacy_restore(reader);
  else if(!strcmp(argv[4],"verify")) { reader_result listed={0};compat_list(reader,&listed);for(size_t i=0;i<listed.records_page.count;i++) {
    reader_av_item *item=&listed.records_page.items[i];if(!item->deleted)compat_adopt(reader,item->annotation_id,item->revision_id,item->sha256,0);
  }reader_result_free(&listed); }
  else compat_check(0,"known actual raw owner mode");
  compat_original(reader,argv[3]);linux_reader_close(reader);g_free(database);
  fprintf(compat_report,"],\"accepted\":true,\"check_count\":%u,\"created\":%d,\"retained_revision\":\"%s\"}\n",compat_checks,compat_created,compat_retry_revision);fclose(compat_report);return 0;
}
