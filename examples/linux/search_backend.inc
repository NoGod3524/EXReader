/* SPDX-License-Identifier: MIT */
/* The existing SDK owner exclusively owns searches, sources and captured hits. */
typedef struct {
  reader_session source;
  reader_search *handle;
  reader_search_result batch;
  exr_layout_config layout;
  exr_chapter_options chapter;
  char css[256];
  uint64_t token;
  linux_reader *reader;
  reader_search_control *observe;
  int request;
} gtk_search_owner;
static void search_phase(gtk_search_owner *search,int phase) {
  reader_search_control *observe=search->observe;
  if(observe && g_atomic_int_get(&observe->request)==search->request) {
    g_atomic_int_set(&observe->phase,phase);if(observe->changed) observe->changed(observe->context);
  }
}
static int search_cancelled(void *context) {
  gtk_search_owner *search=context;reader_search_control *observe=search->observe;
  if(observe) {
    if(g_atomic_int_get(&observe->request)!=search->request) return 1;
    if(g_atomic_int_add(&observe->polls,1)==0 && observe->changed) observe->changed(observe->context);
  }
  return search->reader->control.cancelled && search->reader->control.cancelled(search->reader->control.context);
}

static void search_free(linux_reader *reader) {
  gtk_search_owner *search=reader->search_data;
  if(!search) return;
  reader_search_result_free(&search->batch);reader_search_close(&search->handle,NULL);
  session_free(&search->source);free(search);reader->search_data=NULL;
}
static exr_status search_status(reader_search_status status,const reader_search_error *error) {
  if(status==READER_SEARCH_OK) return EXR_OK;
  if(status==READER_SEARCH_CANCELLED) return EXR_CANCELLED;
  if(status==READER_SEARCH_MEMORY) return EXR_MEMORY;
  if(status==READER_SEARCH_SDK) return error->sdk_code;
  return EXR_ARGUMENT;
}
static void search_label_text(GString *label,const char *text,size_t size,unsigned limit) {
  size_t offset=0;if(!text) return;
  for(unsigned count=0;offset<size && count<limit;count++) {
    gunichar scalar=g_utf8_get_char_validated(text+offset,(gssize)(size-offset));
    if(scalar==(gunichar)-1 || scalar==(gunichar)-2) { scalar=0xfffd;offset++; }
    else if(!scalar) { scalar=0x2400;offset++; }
    else offset=(size_t)(g_utf8_next_char(text+offset)-text);
    g_string_append_unichar(label,scalar);
  }
  if(offset<size) g_string_append(label,"…");
}
static char *search_label(const reader_search_hit *hit) {
  int fixed=hit->mode==READER_SEARCH_FIXED;
  const char *exact=fixed ? hit->fixed.exact:hit->anchor.exact;
  const char *prefix=fixed ? hit->fixed.prefix:hit->anchor.prefix,*suffix=fixed ? hit->fixed.suffix:hit->anchor.suffix;
  GString *label=g_string_new(NULL);
  g_string_append_printf(label,"%s %"G_GUINT64_FORMAT" · ",fixed ? "Page":"Part",hit->unit+1);
  search_label_text(label,prefix,fixed ? hit->fixed.prefix_size:(prefix ? strlen(prefix):0),32);
  g_string_append(label," [");search_label_text(label,exact,fixed ? hit->fixed.exact_size:(exact ? strlen(exact):0),64);
  g_string_append(label,"] ");search_label_text(label,suffix,fixed ? hit->fixed.suffix_size:(suffix ? strlen(suffix):0),32);
  char *copy=strdup(label->str);g_string_free(label,TRUE);return copy;
}
static void search_readonly(linux_reader *reader,const reader_command *command,reader_result *result) {
  gtk_search_owner *search=reader->search_data;reader_search_error error={0};reader_search_status status=READER_SEARCH_OK;
  result->has_search=1;result->search_token=command->search_token;result->search_complete=1;
  if(command->action==READER_SEARCH_CLOSE) {
    if(!search || !command->search_token || search->token==command->search_token) search_free(reader);
    if(reader->search_pending && (!command->search_token || command->search_token==reader->search_pending_token)) pending_discard(reader);
    result->status=EXR_OK;return;
  }
  if(command->action==READER_SEARCH_BEGIN) {
    search_free(reader);search=NULL;
    if(!command->search_query || !command->book || command->book!=reader->current.id || !command->search_token) status=READER_SEARCH_ARGUMENT;
    else if(!strlen(command->search_query) || strlen(command->search_query)>READER_SEARCH_QUERY_MAX || !g_utf8_validate(command->search_query,-1,NULL)) {
      status=READER_SEARCH_QUERY;snprintf(error.message,sizeof(error.message),"Enter 1 to 4096 bytes of valid UTF-8 text");
    }
    else {
      search=calloc(1,sizeof(*search));
      if(!search) status=READER_SEARCH_MEMORY;
      else {
        reader->search_data=search;search->token=command->search_token;search->reader=reader;
        search->observe=command->search_control;search->request=search->observe ? g_atomic_int_get(&search->observe->request):0;search_phase(search,1);
        reader_result opened={0};exr_error problem={0};
        exr_status sdk=open_book(reader,command->book,reader->current.font,reader->current.zoom,&search->source,&opened,&problem);
        reader_result_free(&opened);
        if(sdk!=EXR_OK) { status=READER_SEARCH_SDK;error.sdk_code=sdk;snprintf(error.message,sizeof(error.message),"Search source could not be opened"); }
        else {
          reader_search_options options={0};options.struct_size=sizeof(options);
          options.control=(exr_control){search_cancelled,NULL,search};
          const char *query=command->search_query;size_t length=strlen(query);
          search->layout=exr_layout_config_defaults();search->layout.control=reader->control;
          search->layout.page=(exr_layout_options){520,640,28,(float)reader->current.font,1.5f,8};
#ifdef EXR_READER_PREFERENCES
          if(reader->appearance_enabled) {
            const reader_preferences *p=&reader->appearance;
            search->layout.page=(exr_layout_options){520,640,p->margin,p->font_size,p->line_spacing,p->paragraph_spacing};
            snprintf(search->css,sizeof(search->css),"*{color:#%02x%02x%02x%02x !important;}",p->light_foreground[0],p->light_foreground[1],p->light_foreground[2],p->light_foreground[3]);
            search->layout.user_css=search->css;
          }
#endif
          search->chapter=exr_chapter_options_defaults();search->chapter.window_bytes=16384;
          if(search->source.fixed_document) status=reader_search_open_fixed(search->source.fixed_document,query,length,&options,&search->handle,&error);
          else if(search->source.bounded) status=reader_search_open_epub(search->source.publication,reader->font,&search->layout,&search->chapter,query,length,&options,&search->handle,&error);
          else status=reader_search_open_reflow(search->source.document,query,length,&options,&search->handle,&error);
        }
      }
    }
  } else if(!search || search->token!=command->search_token || search->source.id!=command->book || command->book!=reader->current.id) status=READER_SEARCH_ARGUMENT;
  if(status==READER_SEARCH_OK) {
    search->observe=command->search_control;search->request=search->observe ? g_atomic_int_get(&search->observe->request):0;
    search_phase(search,2);reader_search_result next={0};status=reader_search_next(search->handle,32,&next,&error);search_phase(search,3);
    if(status==READER_SEARCH_OK) {
      reader_search_row *rows=calloc(next.count ? next.count:1,sizeof(*rows));
      if(!rows) status=READER_SEARCH_MEMORY;
      else {
        result->search_rows=rows;result->search_count=next.count;result->search_complete=next.complete;
        for(size_t i=0;i<next.count;i++) {
          const reader_search_hit *hit=&next.hits[i];rows[i]=(reader_search_row){search_label(hit),(size_t)hit->unit,(size_t)hit->start,(size_t)hit->end,hit->mode};
          if(!rows[i].label) { status=READER_SEARCH_MEMORY;break; }
        }
      }
      if(status==READER_SEARCH_OK) { reader_search_result_free(&search->batch);search->batch=next;memset(&next,0,sizeof(next)); }
    }
    reader_search_result_free(&next);
  }
  result->search_code=status;result->search_sdk_code=error.sdk_code;result->status=search_status(status,&error);
  snprintf(result->message,sizeof(result->message),"%s",status==READER_SEARCH_OK ? (result->search_count ? "Search results ready":"No matching text"):error.message[0] ? error.message:"Search did not complete; current reading retained");
  if(status!=READER_SEARCH_OK && (command->action==READER_SEARCH_BEGIN || status==READER_SEARCH_MEMORY)) search_free(reader);
}
static exr_status search_jump(linux_reader *reader,reader_session *next,const reader_command *command,reader_result *result,exr_error *error) {
  gtk_search_owner *search=reader->search_data;exr_status status=EXR_ARGUMENT;exr_anchor_match match={0};exr_fixed_text *text=NULL;
  result->has_search=1;result->search_token=command->search_token;
  if(!search || search->token!=command->search_token || search->source.id!=next->id || command->book!=next->id || command->search_index>=search->batch.count) goto done;
  const reader_search_hit *hit=&search->batch.hits[command->search_index];
  if(next->fixed_document && hit->mode==READER_SEARCH_FIXED) {
    size_t count=0,page=SIZE_MAX;const exr_fixed_page *pages=exr_fixed_pages(next->fixed_document,&count);
    for(size_t i=0;i<count;i++) if(hit->page_id && !strcmp(pages[i].id,hit->page_id)) {
      if(page!=SIZE_MAX) { match.state=EXR_ANCHOR_AMBIGUOUS;goto done; }page=i;
    }
    if(page==SIZE_MAX) goto done;
    status=exr_fixed_load_text(next->fixed_document,page,&reader->control,&text,error);
    if(status==EXR_OK) status=exr_fixed_anchor_resolve(pages[page].id,text,&hit->fixed,&reader->control,&match,error);
    if(status==EXR_OK && match.state==EXR_ANCHOR_FOUND) status=render_fixed(reader,next,page,result,error);
  } else if(next->bounded && hit->mode==READER_SEARCH_EPUB) {
    if(!hit->part_path || !route(next,(size_t)hit->unit) || strcmp(route(next,(size_t)hit->unit),hit->part_path)) goto done;
    next->part=(size_t)hit->unit;next->pager=NULL;
    status=pager_create(reader,next,next->part,next->font,&next->pager,error);
    if(status==EXR_OK) status=exr_pager_anchor_resolve(next->pager,&hit->anchor,&reader->control,&match,error);
    if(status==EXR_OK && match.state==EXR_ANCHOR_FOUND) status=render(reader,next,0,1,match.start,result,error);
  } else if(!next->bounded && !next->fixed_document && hit->mode==READER_SEARCH_REFLOW) {
    status=exr_anchor_resolve_ex(next->document,&hit->anchor,&reader->control,&match,error);
    if(status==EXR_OK && match.state==EXR_ANCHOR_FOUND) status=render(reader,next,0,1,match.start,result,error);
  }
  if(status==EXR_OK && match.state!=EXR_ANCHOR_FOUND) status=EXR_ARGUMENT;
  if(status==EXR_OK) {
    next->position=next->fixed_document ? result->page:match.start;
    result->select_range=1;result->selected_start=match.start;result->selected_end=match.end;
    search_free(reader);
  }
done:
  exr_fixed_text_free(text);result->search_match=match.state;
  if(status!=EXR_OK) snprintf(result->message,sizeof(result->message),"%s",match.state==EXR_ANCHOR_AMBIGUOUS ? "Search quote is ambiguous; reading unchanged":"Search quote could not be resolved; reading unchanged");
  return status;
}
