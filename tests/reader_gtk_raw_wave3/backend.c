/* SPDX-License-Identifier: MIT */
/* Actions-only owner probe of the five Wave 3 GTK tools on the explicit raw0.2
   installed family. It compiles the literal GTK worker source, so every check
   reads the actual history wire, the actual raw store and the actual public SDK
   capture/resolve path. Nothing is simulated, no private symbol is externed and
   no schema, header or existing entry point is added. */
#include REAL_READING_SOURCE
/* The explicit raw0.2 exporter declares its own entry in the candidate header. */
#include <reader_annotation_export_raw3.h>

static unsigned checks;
#define REQUIRE(test) do { checks++;if(!(test)) { fprintf(stderr,"check %u failed at %d: %s\n",checks,__LINE__,#test);exit(1); } } while(0)
#define PASS(name) do { printf("{\"check\":\"%s\",\"pass\":true}\n",name);fflush(stdout); } while(0)

static int never(void *unused) { (void)unused;return 0; }
static reader_command w3_command(reader_action action,int64_t book) {
  reader_command value={0};value.action=action;value.book=book;value.font=24;value.zoom=100;value.records_token=1;return value;
}
/* The worker refuses a bound command whose part/page disagree with the live
   session, so every history or font command is built from the current state. */
static reader_command w3_bound(linux_reader *reader,reader_action action,int64_t book) {
  reader_command value=w3_command(action,book);
  value.part=reader->current.part;value.page=reader->current.page;
  return value;
}
static reader_result w3_run(linux_reader *reader,reader_command value) {
  reader_result result={0};linux_reader_execute(reader,&value,&result);return result;
}
static reader_result w3_accept(linux_reader *reader,const reader_result *frame) {
  reader_command value=w3_command(READER_COMMIT,frame->book);value.part=frame->part;value.page=frame->page;value.start=frame->start;
  reader_result result=w3_run(reader,value);REQUIRE(result.status==EXR_OK);return result;
}
static int64_t w3_open(linux_reader *reader,reader_action action,const char *path,int64_t book,reader_result *landed) {
  reader_command value=w3_command(action,book);value.path=path;reader_result frame=w3_run(reader,value);
  REQUIRE(frame.status==EXR_OK && frame.has_frame);int64_t id=frame.book;
  *landed=w3_accept(reader,&frame);reader_result_free(&frame);return id;
}
static reader_result w3_search(linux_reader *reader,int64_t book,uint64_t token,const char *query,reader_search_control *control) {
  reader_command value=w3_command(READER_SEARCH_BEGIN,book);value.search_token=token;value.search_query=query;value.search_control=control;
  g_atomic_int_inc(&control->request);g_atomic_int_set(&control->phase,0);g_atomic_int_set(&control->polls,0);
  value.search_request=g_atomic_int_get(&control->request);
  reader_result found=w3_run(reader,value);REQUIRE(found.status==EXR_OK && found.search_count>=1);reader_result_free(&found);
  value=w3_bound(reader,READER_SEARCH_CHOOSE,book);value.search_token=token;value.search_index=0;
  reader_result frame=w3_run(reader,value);
  REQUIRE(frame.status==EXR_OK && frame.has_frame && frame.search_match==EXR_ANCHOR_FOUND && frame.select_range);return frame;
}
static void w3_write_text(const char *path,const char *title) {
  GString *text=g_string_new(NULL);
  for(int i=0;i<900;i++) {
    g_string_append_printf(text,"%s line %d keeps ordinary reading words moving through the page so that several pages exist.\n",title,i);
    if(i==120) g_string_append(text,"NEEDLEONE appears only here.\n");
    if(i==520) g_string_append(text,"NEEDLETWO appears only here.\n");
  }
  REQUIRE(g_file_set_contents(path,text->str,(gssize)text->len,NULL));g_string_free(text,TRUE);
}
static received_owner *w3_store(linux_reader *reader) {
  received_owner *owner=NULL;REQUIRE(received_ready(reader,&owner)==EXR_OK && owner);return owner;
}
/* One history slot exactly as the raw store retains it. */
static void w3_slot(linux_reader *reader,size_t index,reader_jh_item *item,reader_rs_record *record) {
  reader_jh_error problem={0};
  REQUIRE(reader_jh_item_at(reader->w3_history,index,item,&problem)==READER_JH_OK);
  REQUIRE(reader_rs_decode_raw_v3(w3_store(reader)->revisions,item->wire,item->wire_bytes,record,NULL)==READER_RS_OK);
}
static size_t w3_count(linux_reader *reader) {
  reader_jh_state state={0};reader_jh_error problem={0};
  REQUIRE(reader_jh_state_get(reader->w3_history,&state,&problem)==READER_JH_OK);
  return state.count;
}
static size_t w3_cursor(linux_reader *reader) {
  reader_jh_state state={0};reader_jh_error problem={0};
  REQUIRE(reader_jh_state_get(reader->w3_history,&state,&problem)==READER_JH_OK);
  return state.cursor;
}
static int w3_bytes_equal(const char *left,size_t left_size,const char *right,size_t right_size) {
  if(!left || !right) return !left && !right;
  return left_size==right_size && !memcmp(left,right,left_size);
}
/* The retained slot must equal a fresh public SDK capture of the live session. */
static void w3_slot_matches_capture(linux_reader *reader,size_t index) {
  reader_jh_item item={0};reader_rs_record record={0};w3_slot(reader,index,&item,&record);
  reader_rs_capture captured;exr_anchor anchor={0};exr_fixed_anchor fixed={0};exr_error error={0};
  size_t unit=reader->current.fixed_document ? reader->current.page:reader->current.part;
  size_t at=reader->current.fixed_document ? 0:reader->current.position;
  REQUIRE(records_capture(reader,&reader->current,unit,at,at,&captured,&anchor,&fixed,&error)==EXR_OK);
  if(record.mode==READER_RS_FIXED_PAGE) {
    printf("{\"info\":\"slot_vs_capture\",\"mode\":%d,\"rec_a\":%llu,\"rec_ex\":%zu,\"rec_pre\":%zu,"
           "\"rec_suf\":%zu,\"rec_hx\":%d,\"rec_hp\":%d,\"rec_hs\":%d,\"cap_ex\":%zu,\"cap_pre\":%zu,"
           "\"cap_suf\":%zu,\"cap_hx\":%d,\"cap_hp\":%d,\"cap_hs\":%d}\n",(int)record.mode,
      (unsigned long long)record.anchor_version,record.exact_size,record.prefix_size,record.suffix_size,
      record.exact?1:0,record.prefix?1:0,record.suffix?1:0,fixed.exact_size,fixed.prefix_size,fixed.suffix_size,
      fixed.exact?1:0,fixed.prefix?1:0,fixed.suffix?1:0);fflush(stdout);
  }
  REQUIRE(record.mode==captured.mode && record.start==record.end);
  if(record.mode==READER_RS_FIXED_PAGE) {
    REQUIRE(record.anchor_version==3);
    REQUIRE(fixed.exact_size==record.exact_size && fixed.prefix_size==record.prefix_size && fixed.suffix_size==record.suffix_size);
    REQUIRE((fixed.exact?1:0)==(record.exact?1:0) && (fixed.prefix?1:0)==(record.prefix?1:0) &&
            (fixed.suffix?1:0)==(record.suffix?1:0));
    REQUIRE(w3_bytes_equal(fixed.exact,record.exact_size,record.exact,record.exact_size));
    REQUIRE(w3_bytes_equal(fixed.prefix,record.prefix_size,record.prefix,record.prefix_size));
    REQUIRE(w3_bytes_equal(fixed.suffix,record.suffix_size,record.suffix,record.suffix_size));
  } else {
    REQUIRE(record.anchor_version==2 && captured.anchor);
    REQUIRE(w3_bytes_equal(captured.anchor->exact,record.exact_size,record.exact,record.exact_size));
    REQUIRE(w3_bytes_equal(captured.anchor->prefix,record.prefix_size,record.prefix,record.prefix_size));
    REQUIRE(w3_bytes_equal(captured.anchor->suffix,record.suffix_size,record.suffix,record.suffix_size));
    REQUIRE(w3_bytes_equal(captured.part_path,captured.part_path?strlen(captured.part_path):0,
      record.part_path,record.part_path?strlen(record.part_path):0));
  }
  exr_anchor_free(&anchor);exr_fixed_anchor_free(&fixed);
  reader_rs_record_free(&record);reader_jh_item_release(&item);
}
static size_t outbox_rows;
static int outbox_visit(void *opaque,const reader_revision_outbox_row *row) {
  (void)opaque;(void)row;outbox_rows++;return 0;
}
static size_t w3_outbox(linux_reader *reader) {
  received_owner *owner=w3_store(reader);outbox_rows=0;
  REQUIRE(reader_revision_outbox_raw_v3(owner->revisions,200,outbox_visit,NULL,NULL)==READER_REV_OK);
  return outbox_rows;
}
/* One decoded selector, byte for byte, including the nullable pointers. */
typedef struct {
  reader_rs_mode mode;uint64_t anchor_version,start,end;
  size_t exact_size,prefix_size,suffix_size;
  int has_exact,has_prefix,has_suffix;
  char exact[65536],prefix[512],suffix[512];
} w3_selector;
static void w3_selector_copy(const reader_rs_record *record,w3_selector *out) {
  memset(out,0,sizeof(*out));
  out->mode=record->mode;out->anchor_version=record->anchor_version;out->start=record->start;out->end=record->end;
  out->exact_size=record->exact_size;out->prefix_size=record->prefix_size;out->suffix_size=record->suffix_size;
  out->has_exact=record->exact ? 1:0;out->has_prefix=record->prefix ? 1:0;out->has_suffix=record->suffix ? 1:0;
  if(record->exact) { REQUIRE(record->exact_size<sizeof(out->exact));memcpy(out->exact,record->exact,record->exact_size); }
  if(record->prefix) { REQUIRE(record->prefix_size<sizeof(out->prefix));memcpy(out->prefix,record->prefix,record->prefix_size); }
  if(record->suffix) { REQUIRE(record->suffix_size<sizeof(out->suffix));memcpy(out->suffix,record->suffix,record->suffix_size); }
}
static int w3_same_selector(const w3_selector *left,const w3_selector *right) {
  return left->mode==right->mode && left->anchor_version==right->anchor_version && left->start==right->start &&
    left->end==right->end && left->has_exact==right->has_exact && left->has_prefix==right->has_prefix &&
    left->has_suffix==right->has_suffix && w3_bytes_equal(left->exact,left->exact_size,right->exact,right->exact_size) &&
    w3_bytes_equal(left->prefix,left->prefix_size,right->prefix,right->prefix_size) &&
    w3_bytes_equal(left->suffix,left->suffix_size,right->suffix,right->suffix_size);
}
/* Every retained annotation selector of one store, in list order. */
static size_t w3_annotation_selectors(linux_reader *reader,int64_t book,w3_selector *out,size_t capacity) {
  received_owner *owner=w3_store(reader);reader_result listed={0};size_t stored=0;
  reader_command value=w3_command(READER_RECORDS_LIST,book);listed=w3_run(reader,value);
  REQUIRE(listed.status==EXR_OK);
  for(size_t i=0;i<listed.records_page.count && stored<capacity;i++) {
    const reader_av_item *item=&listed.records_page.items[i];
    if(item->deleted) continue;
    char *wire=NULL;size_t bytes=0;reader_revision_info info={0};reader_rs_record record={0};
    REQUIRE(reader_revision_get_raw_v3(owner->revisions,item->revision_id,&wire,&bytes,&info,NULL)==READER_REV_OK);
    REQUIRE(reader_rs_decode_raw_v3(owner->revisions,wire,bytes,&record,NULL)==READER_RS_OK);
    w3_selector_copy(&record,&out[stored++]);
    reader_rs_record_free(&record);reader_revision_bytes_free(wire);
  }
  reader_result_free(&listed);return stored;
}
static void w3_save(linux_reader *reader,int kind,const char *body,size_t start,size_t end,char revision[33]) {
  reader_command value=w3_command(READER_RECORDS_SAVE,reader->current.id);
  value.records_kind=kind;value.records_operation=READER_RC_PUT;value.records_text=body;value.start=start;value.end=end;
  reader_result saved=w3_run(reader,value);
  if(saved.status!=EXR_OK || !saved.records_created)
    printf("{\"info\":\"save_refused\",\"kind\":%d,\"status\":%d,\"records_code\":%d,\"created\":%d,"
           "\"message\":\"%s\"}\n",kind,(int)saved.status,saved.records_code,saved.records_created,
      saved.message);
  REQUIRE(saved.status==EXR_OK && saved.records_created);
  if(revision) g_strlcpy(revision,saved.records_revision,33);
  reader_result_free(&saved);
}

/* The raw GUI round needs the same book and an annotations file the raw0.2
   importer really accepts: the file is written by the installed raw exporter
   from a real raw store, never by hand. This mode is fixture production only. */
static int w3_seed(char **argv) {
  const char *library=argv[1],*font=argv[3],*work=argv[5],*book=argv[7];
  exr_control control={never,NULL,NULL};linux_reader *reader=NULL;exr_error error={0};
  w3_write_text(book,"History");
  REQUIRE(linux_reader_open(library,font,&control,&reader,&error)==EXR_OK);
  reader_result landed={0};REQUIRE(w3_open(reader,READER_IMPORT,book,0,&landed)>0);reader_result_free(&landed);
  size_t start=reader->current.start,end=start+6;REQUIRE(end<=reader->current.end && start<end);
  w3_save(reader,READER_RC_HIGHLIGHT,"Seed highlight",start,end,NULL);
  w3_save(reader,READER_RC_BOOKMARK,"Seed bookmark",reader->current.start,reader->current.start,NULL);
  char key[73];REQUIRE(w3_book_key(reader,key)==EXR_OK);
  char *product=g_strconcat(library,".product.sqlite",NULL),*jsonl=g_build_filename(work,"annotations.jsonl",NULL);
  reader_revisions *store=NULL;REQUIRE(reader_revisions_open_raw_v3(product,&store,NULL)==READER_REV_OK);
  reader_annotation_export_options options={0};options.struct_size=sizeof(options);options.revisions=store;
  options.book_key=key;options.jsonl_path=jsonl;
  reader_annotation_export_stats stats={0};reader_annotation_export_error problem={0};
  reader_annotation_export_status code=reader_annotation_export_raw3_run(&options,&stats,&problem);
  if(code!=READER_ANNOTATION_EXPORT_OK)
    fprintf(stderr,"seed export failed code=%d %s\n",(int)code,problem.message);
  REQUIRE(code==READER_ANNOTATION_EXPORT_OK && stats.annotations==2 && stats.jsonl_published);
  REQUIRE(reader_revisions_close(&store,NULL)==READER_REV_OK);
  printf("{\"seed\":true,\"book\":\"%s\",\"key\":\"%s\",\"annotations\":%llu,\"annotations_path\":\"%s\"}\n",
    book,key,(unsigned long long)stats.annotations,jsonl);fflush(stdout);
  linux_reader_close(reader);g_free(product);g_free(jsonl);return 0;
}

int main(int argc,char **argv) {
  if(argc==8 && !strcmp(argv[6],"seed")) return w3_seed(argv);
  REQUIRE(argc==6);
  const char *library_a=argv[1],*library_b=argv[2],*font=argv[3],*fixtures=argv[4],*work=argv[5];
  exr_control control={never,NULL,NULL};linux_reader *reader=NULL;exr_error error={0};reader_search_control search={0};
  int64_t text_book=0;
  char *text_path=g_build_filename(work,"history.txt",NULL);w3_write_text(text_path,"History");
  REQUIRE(linux_reader_open(library_a,font,&control,&reader,&error)==EXR_OK);

  /* 1. Reflow history keeps the real anchor v2 point. */
  {
    reader_result landed={0};text_book=w3_open(reader,READER_IMPORT,text_path,0,&landed);
    REQUIRE(landed.has_w3 && landed.w3_history_count==1 && !landed.w3_can_back && !landed.w3_can_forward);
    reader_result_free(&landed);
    reader_jh_item item={0};reader_rs_record record={0};w3_slot(reader,0,&item,&record);
    REQUIRE(record.mode==READER_RS_REFLOW_GLOBAL && record.anchor_version==2 && record.has_location);
    /* A landing is a caret: no range and no invented quote (the module's own
       point rule keeps the selector empty and anchors it on the bytes around). */
    REQUIRE(record.start==record.end && !record.exact_size);
    reader_rs_record_free(&record);reader_jh_item_release(&item);
    char progress[33]={0};w3_save(reader,READER_RC_PROGRESS,"",0,0,progress);
    received_owner *owner=w3_store(reader);char *wire=NULL;size_t bytes=0;reader_rs_record saved={0};
    REQUIRE(reader_revision_get_raw_v3(owner->revisions,progress,&wire,&bytes,NULL,NULL)==READER_REV_OK);
    REQUIRE(reader_rs_decode_raw_v3(owner->revisions,wire,bytes,&saved,NULL)==READER_RS_OK);
    REQUIRE(saved.mode==READER_RS_REFLOW_GLOBAL && saved.anchor_version==2 && saved.start==saved.end && !saved.exact_size);
    REQUIRE(bytes && wire);reader_rs_record_free(&saved);reader_revision_bytes_free(wire);
    reader_result one=w3_search(reader,text_book,1,"NEEDLEONE",&search);size_t one_start=one.selected_start;
    landed=w3_accept(reader,&one);
    REQUIRE(landed.w3_history_count==2 && landed.w3_history_cursor==1 && landed.w3_can_back && !landed.w3_can_forward);
    reader_result_free(&landed);reader_result_free(&one);
    reader_result two=w3_search(reader,text_book,2,"NEEDLETWO",&search);size_t two_start=two.selected_start;
    REQUIRE(two_start>one_start);landed=w3_accept(reader,&two);
    REQUIRE(landed.w3_history_count==3 && landed.w3_history_cursor==2);
    reader_result_free(&landed);reader_result_free(&two);
    w3_slot(reader,1,&item,&record);
    REQUIRE(record.anchor_version==2 && record.start==one_start && record.start==record.end && record.mode==READER_RS_REFLOW_GLOBAL);
    reader_rs_record_free(&record);reader_jh_item_release(&item);
    reader_command value=w3_bound(reader,READER_W3_HISTORY,text_book);value.direction=-1;
    reader_result frame=w3_run(reader,value);
    REQUIRE(frame.status==EXR_OK && frame.has_frame && frame.select_range && frame.selected_start==one_start);
    reader_result moved=w3_accept(reader,&frame);REQUIRE(moved.w3_history_cursor==1 && moved.w3_can_forward);
    reader_result_free(&moved);reader_result_free(&frame);
    value=w3_bound(reader,READER_W3_HISTORY,text_book);value.direction=1;frame=w3_run(reader,value);
    REQUIRE(frame.status==EXR_OK && frame.has_frame && frame.selected_start==two_start);
    moved=w3_accept(reader,&frame);REQUIRE(moved.w3_history_cursor==2 && !moved.w3_can_forward);
    reader_result_free(&moved);reader_result_free(&frame);
    PASS("reflow_history_and_progress_are_real_v2_points");
    PASS("history_back_and_forward_prove_the_point_before_moving");
  }

  /* 2. EPUB: a page turn is one landing, not two, and a search landing keeps
        the real anchor v2 route. The fixture carries its own markers so the
        search target cannot coincide with the page caret. */
  {
    char *epub=g_build_filename(work,"markers.epub",NULL);reader_result landed={0};
    size_t before=w3_count(reader);
    int64_t epub_book=w3_open(reader,READER_IMPORT,epub,0,&landed);reader_result_free(&landed);
    REQUIRE(w3_count(reader)==before+1);
    {
      reader_jh_item item={0};reader_rs_record record={0};w3_slot(reader,before,&item,&record);
      REQUIRE(record.mode==READER_RS_EPUB_CHAPTER && record.anchor_version==2 && record.part_path);
      REQUIRE(record.part==reader->current.part && record.start==record.end && !record.exact_size);
      reader_rs_record_free(&record);reader_jh_item_release(&item);
    }
    w3_slot_matches_capture(reader,before);
    PASS("epub_history_slot_is_the_real_anchor_v2_route_point");
    reader_result next=w3_run(reader,w3_command(READER_NEXT,epub_book));REQUIRE(next.status==EXR_OK && next.has_frame);
    reader_result moved=w3_accept(reader,&next);
    REQUIRE(moved.w3_history_count==(int)before+1 && moved.w3_history_cursor==(int)before);
    reader_result_free(&moved);reader_result_free(&next);
    w3_slot_matches_capture(reader,before);
    PASS("epub_page_turn_replaces_one_landing_with_the_new_real_point");
    reader_result hit=w3_search(reader,epub_book,3,"NEEDLEONE",&search);
    moved=w3_accept(reader,&hit);reader_result_free(&moved);reader_result_free(&hit);
    REQUIRE(w3_count(reader)==before+2);
    {
      reader_jh_item item={0};reader_rs_record record={0};w3_slot(reader,before+1,&item,&record);
      REQUIRE(record.mode==READER_RS_EPUB_CHAPTER && record.anchor_version==2 && record.start==record.end);
      reader_rs_record_free(&record);reader_jh_item_release(&item);
    }
    PASS("epub_search_landing_is_appended_as_a_real_anchor_v2_point");
    reader_result second_hit=w3_search(reader,epub_book,4,"NEEDLETWO",&search);
    moved=w3_accept(reader,&second_hit);reader_result_free(&moved);reader_result_free(&second_hit);
    REQUIRE(w3_count(reader)==before+3);
    {
      reader_command value=w3_bound(reader,READER_W3_HISTORY,epub_book);value.direction=-1;
      reader_result frame=w3_run(reader,value);
      printf("{\"info\":\"epub_history_jump\",\"status\":%d,\"match\":%d,\"message\":\"%s\"}\n",
        (int)frame.status,(int)frame.search_match,frame.message);fflush(stdout);
      REQUIRE(frame.status==EXR_OK && frame.has_frame && frame.select_range);
      moved=w3_accept(reader,&frame);REQUIRE(moved.w3_history_cursor==(int)before+1);
      reader_result_free(&moved);reader_result_free(&frame);
    }
    PASS("epub_history_jumps_only_to_a_resolved_anchor_v2_route");
    reader_result shelf=w3_run(reader,w3_command(READER_SHELF,epub_book));REQUIRE(shelf.status==EXR_OK);reader_result_free(&shelf);
    g_free(epub);
  }

  /* 3. Fixed pages: the history retains the real anchor3 page point with every
        nullable selector byte, exactly as the public SDK captured it. */
  char *pdf=g_build_filename(fixtures,"pdf-public-text.pdf",NULL);int64_t pdf_book=0;
  w3_selector original[4];size_t original_count=0;
  {
    /* The pointer may sit behind forward entries; opening a new book is a new
       landing, which truncates them and is then appended. */
    size_t cursor_before=w3_cursor(reader),tail=0;
    reader_result landed={0};
    pdf_book=w3_open(reader,READER_IMPORT,pdf,0,&landed);reader_result_free(&landed);
    {
      reader_jh_state state={0};reader_jh_error problem={0};
      REQUIRE(reader_jh_state_get(reader->w3_history,&state,&problem)==READER_JH_OK);
      REQUIRE(state.count==cursor_before+2 && state.cursor==state.count-1);
      tail=state.count-1;
      REQUIRE(reader->w3_history_code==(int)READER_JH_OK);
    }
    {
      reader_jh_item item={0};reader_rs_record record={0};w3_slot(reader,tail,&item,&record);
      REQUIRE(record.mode==READER_RS_FIXED_PAGE && record.anchor_version==3 && record.has_location);
      REQUIRE(record.start==record.end && !record.exact_size);
      REQUIRE((record.suffix && memchr(record.suffix,0,record.suffix_size)) ||
              (record.exact && memchr(record.exact,0,record.exact_size)) ||
              (record.prefix && memchr(record.prefix,0,record.prefix_size)));
      reader_rs_record_free(&record);reader_jh_item_release(&item);
    }
    w3_slot_matches_capture(reader,tail);
    PASS("fixed_history_slot_is_anchor3_with_every_nullable_selector_byte");
    /* Boundary of this family, asserted by the module itself: the installed raw
       product store refuses a fixed-page record that has no quote, and this host
       has no fixed text selection, so no annotation fixture is created here. The
       byte-for-byte selector proof for fixed pages is the history slot above. */
    /* A fixed history jump needs a second representable page of the same book.
       The shipped public fixed fixtures deliberately contain unrenderable pages
       after the first one, so this probe stops at the byte-exact anchor3 landing,
       which is what the raw wire and the nullable selectors are about. */
    PASS("fixed_history_landing_is_the_real_anchor3_page_point");
  }

  /* 4. The two single-family tools still work on the raw host. */
  {
    char *primary=g_build_filename(fixtures,"fonts","primary.ttf",NULL);
    reader_command importing=w3_command(READER_W3_FONT_IMPORT,pdf_book);importing.w3_path=primary;
    reader_result added=w3_run(reader,importing);REQUIRE(added.status==EXR_OK && added.w3_font_count==1);
    char hash[RFL_HASH_BYTES];g_strlcpy(hash,added.w3_font_hashes[0],sizeof(hash));reader_result_free(&added);
    reader_command open=w3_command(READER_OPEN,pdf_book);open.font=24;
    reader_result frame=w3_run(reader,open);REQUIRE(frame.status==EXR_OK && frame.has_frame);
    reader_result landed=w3_accept(reader,&frame);reader_result_free(&landed);reader_result_free(&frame);
    reader_command use=w3_bound(reader,READER_W3_FONT_USE,pdf_book);use.w3_hash=hash;use.font=24;
    reader_result candidate=w3_run(reader,use);
    REQUIRE(candidate.status!=EXR_OK && !candidate.has_frame && strstr(candidate.message,"fixed pages"));
    reader_result_free(&candidate);
    reader_command removal=w3_command(READER_W3_FONT_REMOVE,pdf_book);removal.w3_hash=hash;
    reader_result removed=w3_run(reader,removal);REQUIRE(removed.status==EXR_OK && removed.w3_font_count==0);
    reader_result_free(&removed);
    char *out=g_build_filename(work,"exported",NULL);REQUIRE(g_mkdir_with_parents(out,0700)==0);
    reader_command exporting=w3_command(READER_W3_EXPORT,pdf_book);exporting.w3_path=out;
    reader_result done=w3_run(reader,exporting);
    REQUIRE(done.status==EXR_OK && done.w3_export_created && done.w3_export_durable && done.w3_export_bytes);
    gchar *original=NULL,*copy=NULL;gsize original_size=0,copy_size=0;
    REQUIRE(g_file_get_contents(pdf,&original,&original_size,NULL) && g_file_get_contents(done.w3_export_path,&copy,&copy_size,NULL));
    REQUIRE(original_size==copy_size && !memcmp(original,copy,original_size));
    g_free(original);g_free(copy);reader_result_free(&done);
    g_free(out);g_free(primary);PASS("original_export_and_font_refusal_keep_the_raw_host_intact");
  }

  /* 5. Read-only sync status: an absent session, then a real raw session whose
     sweep fails. Neither capture starts, retries, acks nor writes. */
  {
    size_t before=w3_outbox(reader);
    reader_result status=w3_run(reader,w3_command(READER_W3_SYNC_STATUS,pdf_book));
    REQUIRE(status.status==EXR_OK && status.w3_sync_text && strstr(status.w3_sync_text,"No sync session"));
    REQUIRE(w3_outbox(reader)==before);reader_result_free(&status);
    PASS("sync_without_session_is_explicit_and_writes_nothing");
    char *product=g_strconcat(library_a,".product.sqlite",NULL),*home=g_path_get_dirname(library_a),
      *originals=g_build_filename(work,"originals",NULL);REQUIRE(g_mkdir_with_parents(originals,0700)==0);
    reader_session_config config;memset(&config,0,sizeof(config));
    config.product_path=product;config.private_directory=home;config.original_directory=originals;
    config.account_id="00000000-0000-4000-8000-000000000001";
    config.dav.root_url="https://127.0.0.1:9/exreader-sync-v1/";config.dav.authorization=NULL;config.dav.timeout_ms=1500;
    reader_account_session *session=NULL;REQUIRE(reader_session_create_raw_v3(&config,&session)==READER_SESSION_OK && session);
    reader_session_snapshot first={0};REQUIRE(reader_session_observe(session,&first)==READER_SESSION_OK);
    reader_command value=w3_command(READER_W3_SYNC_STATUS,pdf_book);value.w3_session=session;
    status=w3_run(reader,value);
    REQUIRE(status.status==EXR_OK && status.w3_sync_text && strstr(status.w3_sync_text,"Phase:") &&
            strstr(status.w3_sync_text,"Whole library synchronized: no"));
    reader_session_snapshot second={0};REQUIRE(reader_session_observe(session,&second)==READER_SESSION_OK);
    REQUIRE(second.state==first.state && second.attempt==first.attempt && second.steps==first.steps);
    REQUIRE(w3_outbox(reader)==before);reader_result_free(&status);
    PASS("sync_capture_never_starts_or_advances_the_session");
    /* A real sweep start against a closed port. Its own status is reported, not
       asserted: this probe owns the view's read-only contract, not the network. */
    reader_session_status started=reader_session_start(session);
    printf("{\"info\":\"session_start\",\"status\":%d}\n",(int)started);fflush(stdout);
    if(started==READER_SESSION_OK) for(int i=0;i<120;i++) {
      reader_session_snapshot now={0};REQUIRE(reader_session_observe(session,&now)==READER_SESSION_OK);
      if(now.state!=READER_SESSION_RUNNING && now.state!=READER_SESSION_IDLE) break;
      g_usleep(50000);
    }
    value=w3_command(READER_W3_SYNC_STATUS,pdf_book);value.w3_session=session;status=w3_run(reader,value);
    REQUIRE(status.status==EXR_OK && status.w3_sync_text && strstr(status.w3_sync_text,"Phase:") &&
            strstr(status.w3_sync_text,"Whole library synchronized: no"));
    REQUIRE(w3_outbox(reader)==before);reader_result_free(&status);
    PASS("sweep_attempt_stays_read_only_and_never_claims_a_complete_library");
    REQUIRE(reader_session_request_close(session)==READER_SESSION_OK);
    for(int i=0;i<120;i++) {
      reader_session_snapshot now={0};REQUIRE(reader_session_observe(session,&now)==READER_SESSION_OK);
      if(now.state==READER_SESSION_CLOSED) break;
      g_usleep(50000);
    }
    REQUIRE(reader_session_destroy(&session)==READER_SESSION_OK && !session);
    g_free(product);g_free(home);g_free(originals);
  }

  /* 6. The raw0.2 exporter writes, the raw0.2 importer previews and commits the
     same immutable bytes, and the roundtrip keeps every real selector byte. The
     fixture is the reflow book: this host has no fixed text selection and the
     installed store refuses a fixed record without a quote. */
  {
    {
      reader_command back=w3_command(READER_OPEN,text_book);back.font=24;
      reader_result frame=w3_run(reader,back);REQUIRE(frame.status==EXR_OK && frame.has_frame);
      reader_result reopened=w3_accept(reader,&frame);reader_result_free(&reopened);reader_result_free(&frame);
    }
    size_t start=reader->current.start,end=start+6;REQUIRE(end<=reader->current.end && start<end);
    w3_save(reader,READER_RC_HIGHLIGHT,"Roundtrip highlight",start,end,NULL);
    w3_save(reader,READER_RC_BOOKMARK,"Roundtrip bookmark",reader->current.position,reader->current.position,NULL);
    original_count=w3_annotation_selectors(reader,text_book,original,4);REQUIRE(original_count==2);
    char key[73];REQUIRE(w3_book_key(reader,key)==EXR_OK);
    char *product=g_strconcat(library_a,".product.sqlite",NULL),*jsonl=g_build_filename(work,"annotations.jsonl",NULL);
    reader_revisions *store=NULL;REQUIRE(reader_revisions_open_raw_v3(product,&store,NULL)==READER_REV_OK);
    reader_annotation_export_options options={0};options.struct_size=sizeof(options);options.revisions=store;
    options.book_key=key;options.jsonl_path=jsonl;
    reader_annotation_export_stats stats={0};reader_annotation_export_error problem={0};
    REQUIRE(reader_annotation_export_raw3_run(&options,&stats,&problem)==READER_ANNOTATION_EXPORT_OK);
    REQUIRE(stats.annotations==2 && stats.jsonl_published);
    REQUIRE(reader_revisions_close(&store,NULL)==READER_REV_OK);
    PASS("raw3_export_writes_both_retained_annotations");
    linux_reader_close(reader);reader=NULL;
    REQUIRE(linux_reader_open(library_b,font,&control,&reader,&error)==EXR_OK);
    reader_result landed={0};int64_t imported=w3_open(reader,READER_IMPORT,text_path,0,&landed);reader_result_free(&landed);
    /* The raw importer only commits into a store that already retains this
       original identity; one real reading record is what a user creates first. */
    w3_save(reader,READER_RC_PROGRESS,"",reader->current.position,reader->current.position,NULL);
    reader_command listing=w3_command(READER_RECORDS_LIST,imported);reader_result rows=w3_run(reader,listing);
    REQUIRE(rows.status==EXR_OK && rows.records_page.count==0);reader_result_free(&rows);
    reader_command preview=w3_command(READER_W3_ANNOTATION_PREVIEW,imported);preview.w3_path=jsonl;
    reader_result checked=w3_run(reader,preview);
    REQUIRE(checked.status==EXR_OK && checked.w3_ann_validated && checked.w3_ann_annotations==2 &&
            checked.w3_ann_heads==2 && !checked.w3_ann_committed);
    reader_result_free(&checked);
    rows=w3_run(reader,listing);REQUIRE(rows.status==EXR_OK && rows.records_page.count==0);reader_result_free(&rows);
    PASS("raw_preview_validates_the_export_without_writing");
    reader_result discarded=w3_run(reader,w3_command(READER_W3_ANNOTATION_DISCARD,imported));
    REQUIRE(discarded.status==EXR_OK);reader_result_free(&discarded);
    reader_command confirm=w3_command(READER_W3_ANNOTATION_IMPORT,imported);confirm.w3_path=jsonl;
    reader_result refused=w3_run(reader,confirm);REQUIRE(refused.status!=EXR_OK && !refused.w3_ann_committed);
    reader_result_free(&refused);
    PASS("raw_commit_without_the_checked_fingerprint_is_refused");
    checked=w3_run(reader,preview);REQUIRE(checked.status==EXR_OK && checked.w3_ann_validated);reader_result_free(&checked);
    gchar *checked_bytes=NULL;gsize checked_size=0;
    REQUIRE(g_file_get_contents(jsonl,&checked_bytes,&checked_size,NULL) && checked_size>12);
    REQUIRE(g_file_set_contents(jsonl,checked_bytes,(gssize)(checked_size-12),NULL));
    reader_result done=w3_run(reader,confirm);REQUIRE(done.status!=EXR_OK && !done.w3_ann_committed);reader_result_free(&done);
    REQUIRE(g_file_set_contents(jsonl,checked_bytes,(gssize)checked_size,NULL));
    PASS("raw_truncated_export_is_refused_without_commit");
    checked=w3_run(reader,preview);REQUIRE(checked.status==EXR_OK && checked.w3_ann_validated);reader_result_free(&checked);
    done=w3_run(reader,confirm);
    REQUIRE(done.status==EXR_OK && done.w3_ann_committed==2 && done.w3_ann_created==2 && done.w3_ann_duplicates==0);
    reader_result_free(&done);
    rows=w3_run(reader,listing);REQUIRE(rows.status==EXR_OK && rows.records_page.count==2);reader_result_free(&rows);
    PASS("raw_confirmed_import_commits_the_checked_file");
    {
      w3_selector received[4];size_t count=w3_annotation_selectors(reader,imported,received,4);REQUIRE(count==2);
      int matched=0;
      for(size_t i=0;i<count;i++) {
        REQUIRE(received[i].anchor_version==2);
        for(size_t j=0;j<original_count;j++) if(w3_same_selector(&received[i],&original[j])) matched++;
      }
      REQUIRE(matched==2);
    }
    PASS("raw_roundtrip_preserves_every_reflow_selector_byte");
    checked=w3_run(reader,preview);REQUIRE(checked.status==EXR_OK && checked.w3_ann_validated);reader_result_free(&checked);
    done=w3_run(reader,confirm);REQUIRE(done.status==EXR_OK && done.w3_ann_created==0 && done.w3_ann_duplicates==2);
    reader_result_free(&done);
    PASS("raw_exact_retry_is_a_duplicate");
    char *other=g_build_filename(work,"other.txt",NULL);w3_write_text(other,"Other");
    int64_t other_book=w3_open(reader,READER_IMPORT,other,0,&landed);reader_result_free(&landed);
    reader_command mismatch=w3_command(READER_W3_ANNOTATION_PREVIEW,other_book);mismatch.w3_path=jsonl;
    refused=w3_run(reader,mismatch);
    REQUIRE(refused.status!=EXR_OK && !refused.w3_ann_validated && strstr(refused.message,"refused"));
    reader_result_free(&refused);
    reader_command back=w3_command(READER_OPEN,imported);back.font=24;
    reader_result frame=w3_run(reader,back);REQUIRE(frame.status==EXR_OK && frame.has_frame);
    reader_result reopened=w3_accept(reader,&frame);reader_result_free(&reopened);reader_result_free(&frame);
    rows=w3_run(reader,listing);REQUIRE(rows.status==EXR_OK && rows.records_page.count==2);reader_result_free(&rows);
    PASS("raw_wrong_book_is_refused_without_commit");
    g_free(checked_bytes);g_free(other);g_free(jsonl);g_free(product);
  }

  linux_reader_close(reader);g_free(text_path);g_free(pdf);
  printf("{\"backend_checks\":%u}\n",checks);return 0;
}