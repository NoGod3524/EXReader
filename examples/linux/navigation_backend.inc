/* SPDX-License-Identifier: MIT */
/* Only the existing SDK owner touches the installed snapshot or SDK inputs. */
typedef struct {
  reader_navigation *snapshot;
  reader_session source;
  uint64_t token;
  char key[128];
  linux_reader *reader;
  reader_navigation_control *observe;
  int request;
} gtk_navigation_owner;
static void navigation_phase(gtk_navigation_owner *owner,int phase) {
  if(owner->observe && g_atomic_int_get(&owner->observe->request)==owner->request) {
    g_atomic_int_set(&owner->observe->phase,phase);
    if(owner->observe->changed) owner->observe->changed(owner->observe->context);
  }
}
static int navigation_cancelled(void *opaque) {
  gtk_navigation_owner *owner=opaque;
  if(owner->observe) {
    if(g_atomic_int_get(&owner->observe->request)!=owner->request) return 1;
    if(g_atomic_int_add(&owner->observe->polls,1)==0 && owner->observe->changed) owner->observe->changed(owner->observe->context);
  }
  return owner->reader->control.cancelled && owner->reader->control.cancelled(owner->reader->control.context);
}
static void navigation_free(linux_reader *reader) {
  gtk_navigation_owner *owner=reader->navigation_data;if(!owner) return;
  reader_navigation_close(&owner->snapshot,NULL);session_free(&owner->source);free(owner);reader->navigation_data=NULL;
}
static exr_status navigation_identity(linux_reader *reader,int64_t book,char key[128],exr_error *error) {
  char sha[65];uint64_t bytes=0;exr_format format=EXR_CUSTOM;exr_book *books=NULL;size_t count=0;
  exr_status status=exr_library_books(reader->library,"",&books,&count,error);
  if(status!=EXR_OK) return status;
  for(size_t i=0;i<count;i++) if(books[i].id==book) { format=books[i].format;break; }
  exr_books_free(books,count);if(format==EXR_CUSTOM) return EXR_ARGUMENT;
  status=reader_catalog_sdk_original_identity(reader->library,book,&reader->control,sha,&bytes,error);
  if(status==EXR_OK) snprintf(key,128,"%u:%s@exreader-%s",(unsigned)format,sha,exr_version());
  return status;
}
static exr_status navigation_input(linux_reader *reader,int64_t book,reader_session *input,exr_error *error) {
  reader_result opened={0};exr_status status=open_book(reader,book,reader->current.font,reader->current.zoom,input,&opened,error);
  reader_result_free(&opened);exr_pager_free(input->pager);input->pager=NULL;return status;
}
static exr_status navigation_status(reader_navigation_status code,const reader_navigation_error *error) {
  if(code==READER_NAVIGATION_OK) return EXR_OK;
  if(code==READER_NAVIGATION_CANCELLED) return EXR_CANCELLED;
  if(code==READER_NAVIGATION_MEMORY) return EXR_MEMORY;
  if(code==READER_NAVIGATION_LIMIT) return EXR_LIMIT;
  if(code==READER_NAVIGATION_SDK) return (exr_status)error->sdk_code;
  return EXR_ARGUMENT;
}
static void navigation_readonly(linux_reader *reader,const reader_command *command,reader_result *result) {
  gtk_navigation_owner *owner=reader->navigation_data;reader_navigation_error error={0};reader_navigation_status code=READER_NAVIGATION_OK;
  result->has_navigation=1;result->navigation_token=command->navigation_token;result->navigation_next=READER_NAVIGATION_NONE;
  if(command->action==READER_NAVIGATION_CLOSE) {
    if(!owner || !command->navigation_token || owner->token==command->navigation_token) navigation_free(reader);
    if(reader->navigation_pending && (!command->navigation_token || command->navigation_token==reader->navigation_pending_token)) pending_discard(reader);
    result->status=EXR_OK;return;
  }
  if(command->action==READER_NAVIGATION_BEGIN) {
    navigation_free(reader);owner=NULL;
    if(command->book!=reader->current.id || !command->book || !command->navigation_token) code=READER_NAVIGATION_ARGUMENT;
    else {
      owner=calloc(1,sizeof(*owner));if(!owner) code=READER_NAVIGATION_MEMORY;
      else {
        reader->navigation_data=owner;owner->token=command->navigation_token;owner->reader=reader;
        owner->observe=command->navigation_control;owner->request=command->navigation_request;navigation_phase(owner,1);
        exr_error sdk={0};exr_status status=navigation_identity(reader,command->book,owner->key,&sdk);
        if(status==EXR_OK) status=navigation_input(reader,command->book,&owner->source,&sdk);
        if(status!=EXR_OK) { code=status==EXR_CANCELLED ? READER_NAVIGATION_CANCELLED:READER_NAVIGATION_SDK;error.sdk_code=status; }
        else {
          reader_navigation_options options={0};options.struct_size=sizeof(options);options.source_key=owner->key;
          options.control=(exr_control){navigation_cancelled,NULL,owner};navigation_phase(owner,2);
          if(owner->source.fixed_document) code=reader_navigation_open_pages(owner->source.fixed_document,&options,&owner->snapshot,&error);
          else if(owner->source.bounded) code=reader_navigation_open_publication(owner->source.publication,&options,&owner->snapshot,&error);
          else code=reader_navigation_open_document(owner->source.document,&options,&owner->snapshot,&error);
          if(code==READER_NAVIGATION_OK) { int64_t source_id=owner->source.id;session_free(&owner->source);owner->source.id=source_id; }
        }
      }
    }
  } else if(!owner || command->navigation_token!=owner->token || command->book!=reader->current.id) code=READER_NAVIGATION_ARGUMENT;
  if(code==READER_NAVIGATION_OK) {
    owner->observe=command->navigation_control;owner->request=command->navigation_request;
    if(navigation_cancelled(owner)) code=READER_NAVIGATION_CANCELLED;
    else {
      reader_navigation_info info={0};reader_navigation_page page={0};
      code=reader_navigation_info_get(owner->snapshot,&info,&error);
      if(code==READER_NAVIGATION_OK) code=reader_navigation_children(owner->snapshot,command->navigation_parent,command->navigation_first,32,&page,&error);
      if(code==READER_NAVIGATION_OK && navigation_cancelled(owner)) code=READER_NAVIGATION_CANCELLED;
      if(code==READER_NAVIGATION_OK) {
        result->navigation_rows=calloc(page.count ? page.count:1,sizeof(*result->navigation_rows));
        if(!result->navigation_rows) code=READER_NAVIGATION_MEMORY;
        else {
          result->navigation_kind=info.kind;result->navigation_author_outline=info.author_outline;
          result->navigation_parent=command->navigation_parent;result->navigation_total=page.total;result->navigation_next=page.next;
          for(size_t i=0;i<page.count;i++) {
            reader_navigation_row *row=&page.rows[i];reader_navigation_ui_row *copy=&result->navigation_rows[i];
            copy->index=row->index;copy->parent=row->parent;copy->children=row->child_count;copy->label=strdup(row->label);
            result->navigation_count=i+1;if(!copy->label) { code=READER_NAVIGATION_MEMORY;break; }
          }
        }
      }
      reader_navigation_page_free(&page);
    }
    navigation_phase(owner,3);
  }
  result->navigation_code=code;result->navigation_sdk_code=error.sdk_code;result->status=navigation_status(code,&error);
  snprintf(result->message,sizeof(result->message),"%s",code!=READER_NAVIGATION_OK ? "Directory did not complete; reading retained":
    result->navigation_kind==READER_NAVIGATION_PAGES ? "By-page entries · not an author outline":result->navigation_count ? "Author directory ready":"No authored directory in this book");
  if(code!=READER_NAVIGATION_OK && command->action==READER_NAVIGATION_BEGIN) navigation_free(reader);
}
static int navigation_same_target(const reader_navigation_target *a,const reader_navigation_target *b) {
  if(a->kind!=b->kind || a->part!=b->part || a->node!=b->node || a->cfi_node!=b->cfi_node || a->cfi_offset!=b->cfi_offset || a->cfi_side!=b->cfi_side) return 0;
  const char *left[]={a->part_path,a->part_id,a->fragment,a->cfi},*right[]={b->part_path,b->part_id,b->fragment,b->cfi};
  for(size_t i=0;i<4;i++) if(strcmp(left[i] ? left[i]:"",right[i] ? right[i]:"")) return 0;
  return 1;
}
static reader_navigation_status navigation_resolve(gtk_navigation_owner *owner,reader_session *input,const reader_command *command,
    const char *key,reader_navigation_target *target,reader_navigation_error *error) {
  reader_navigation_resolve_options options={0};options.struct_size=sizeof(options);options.source_key=key;
  options.explicit_part=command->navigation_explicit_part;options.control=(exr_control){navigation_cancelled,NULL,owner};
  if(command->navigation_cfi) return input->bounded ?
    reader_navigation_resolve_cfi(owner->snapshot,input->publication,command->navigation_cfi,&options,target,error):READER_NAVIGATION_CORRUPT;
  if(input->fixed_document) return reader_navigation_resolve_page(owner->snapshot,command->navigation_row,input->fixed_document,&options,target,error);
  if(input->bounded) return reader_navigation_resolve_publication(owner->snapshot,command->navigation_row,input->publication,&options,target,error);
  return reader_navigation_resolve_document(owner->snapshot,command->navigation_row,input->document,&options,target,error);
}
/* Raw DOM UTF-16 points are accepted only at provable scalar boundaries in an
   unchanged normalized range. Collapsed whitespace and half-surrogates refuse. */
static int navigation_cfi_offset(const exr_document *document,const reader_navigation_target *target,size_t *offset) {
  size_t count,size;const exr_node *nodes=exr_document_nodes(document,&count);const char *text=exr_document_text(document,&size);
  if(target->cfi_node>=count) return 0;
  const exr_node *node=&nodes[target->cfi_node];
  if(node->start>node->end || node->end>size) return 0;
  if(node->kind!=EXR_NODE_TEXT) {
    if(target->cfi_offset==READER_NAVIGATION_NONE) { *offset=node->start;return 1; }
    size_t child=node->first_child;
    for(uint64_t i=0;i<target->cfi_offset;i++) { if(child==SIZE_MAX || child>=count) return 0;child=nodes[child].next_sibling; }
    if(child==SIZE_MAX) { *offset=node->end;return 1; }
    if(child>=count) return 0;
    *offset=nodes[child].start;return *offset<=size;
  }
  if(!node->text || target->cfi_offset==READER_NAVIGATION_NONE) return 0;
  size_t raw=strlen(node->text),at=0;uint64_t units=0;
  if(raw!=node->end-node->start || memcmp(text+node->start,node->text,raw)) return 0;
  while(at<raw && units<target->cfi_offset) {
    unsigned char scalar=(unsigned char)node->text[at];size_t bytes=scalar<128 ? 1:scalar<224 ? 2:scalar<240 ? 3:4;
    unsigned added=bytes==4 ? 2:1;if(at+bytes>raw || units+added>target->cfi_offset) return 0;at+=bytes;units+=added;
  }
  if(units!=target->cfi_offset) return 0;
  *offset=node->start+at;return 1;
}
typedef struct { const char *text;size_t size,at; } navigation_projection;
static exr_status navigation_projection_chunk(void *opaque,const char *text,size_t size,exr_error *error) {
  navigation_projection *proof=opaque;(void)error;
  if(proof->at>proof->size || size>proof->size-proof->at || memcmp(proof->text+proof->at,text,size)) return EXR_FORMAT;
  proof->at+=size;return EXR_OK;
}
static exr_status navigation_jump(linux_reader *reader,reader_session *next,const reader_command *command,reader_result *result,exr_error *sdk_error) {
  gtk_navigation_owner *owner=reader->navigation_data;reader_session first={0},second={0};reader_navigation_target target={0},verified={0};
  reader_navigation_error error={0};reader_navigation_status code=READER_NAVIGATION_ARGUMENT;exr_status status=EXR_ARGUMENT;
  char key[128];exr_document *loaded=NULL;exr_anchor anchor={0};exr_anchor_match match={0};size_t offset=SIZE_MAX;
  result->has_navigation=1;result->navigation_token=command->navigation_token;
  if(!owner || owner->token!=command->navigation_token || next->id!=command->book || owner->source.id!=next->id) goto done;
  owner->observe=command->navigation_control;owner->request=command->navigation_request;navigation_phase(owner,2);
  status=navigation_identity(reader,next->id,key,sdk_error);if(status!=EXR_OK) goto done;
  status=navigation_input(reader,next->id,&first,sdk_error);if(status!=EXR_OK) goto done;
  code=navigation_resolve(owner,&first,command,key,&target,&error);
  if(code==READER_NAVIGATION_AMBIGUOUS && target.candidate_count) {
    result->navigation_candidates=malloc(target.candidate_count*sizeof(uint64_t));
    if(!result->navigation_candidates) { code=READER_NAVIGATION_MEMORY;goto done; }
    memcpy(result->navigation_candidates,target.candidates,target.candidate_count*sizeof(uint64_t));result->navigation_candidate_count=target.candidate_count;
  }
  if(code!=READER_NAVIGATION_OK && code!=READER_NAVIGATION_PART_ONLY) goto done;
  if(code==READER_NAVIGATION_PART_ONLY && !command->navigation_accept_part) goto done;
  status=navigation_input(reader,next->id,&second,sdk_error);if(status!=EXR_OK) goto done;
  reader_navigation_status independent=navigation_resolve(owner,&second,command,key,&verified,&error);
  if(independent!=code || !navigation_same_target(&target,&verified)) { code=READER_NAVIGATION_MISMATCH;goto done; }
  if(next->fixed_document) {
    size_t count;const exr_fixed_page *pages=exr_fixed_pages(next->fixed_document,&count);
    if(target.kind!=READER_NAVIGATION_RESULT_PAGE || target.part>=count || !target.part_id || strcmp(target.part_id,pages[target.part].id)) { code=READER_NAVIGATION_MISMATCH;goto done; }
    status=render_fixed(reader,next,(size_t)target.part,result,sdk_error);result->navigation_verified=status==EXR_OK;goto done;
  }
  const exr_document *document=second.document;
  if(second.bounded) {
    status=exr_publication_load(second.publication,(size_t)target.part,&loaded,sdk_error);if(status!=EXR_OK) goto done;document=loaded;
  }
  size_t count,size;const exr_node *nodes=exr_document_nodes(document,&count);const char *text=exr_document_text(document,&size);
  if(target.kind==READER_NAVIGATION_RESULT_CFI) {
    if(!navigation_cfi_offset(document,&target,&offset)) { code=READER_NAVIGATION_UNRESOLVED;goto done; }
  } else if(target.node!=READER_NAVIGATION_NONE) {
    if(target.node>=count) { code=READER_NAVIGATION_MISMATCH;goto done; }offset=nodes[target.node].start;
  } else if(second.bounded) offset=0;
  else {
    const exr_chapter *chapters=exr_document_chapters(document,&count);
    if(target.part>=count) { code=READER_NAVIGATION_MISMATCH;goto done; }
    nodes=exr_document_nodes(document,&count);if(chapters[target.part].root>=count) { code=READER_NAVIGATION_MISMATCH;goto done; }
    offset=nodes[chapters[target.part].root].start;
  }
  if(offset>size || (offset<size && ((unsigned char)text[offset]&192)==128)) { code=READER_NAVIGATION_UNRESOLVED;goto done; }
  status=exr_anchor_create(document,offset,offset,&anchor,sdk_error);if(status!=EXR_OK) goto done;
  if(next->bounded) {
    if(target.part>=SIZE_MAX || !route(next,(size_t)target.part) || !target.part_path || strcmp(route(next,(size_t)target.part),target.part_path)) { code=READER_NAVIGATION_MISMATCH;goto done; }
    next->part=(size_t)target.part;next->pager=NULL;status=pager_create(reader,next,next->part,next->font,&next->pager,sdk_error);if(status!=EXR_OK) goto done;
    navigation_projection proof={text,size,0};
    if(exr_pager_chapter_statistics(next->pager).projection_bytes!=size) { code=READER_NAVIGATION_UNRESOLVED;goto done; }
    status=exr_pager_read_text(next->pager,0,size,navigation_projection_chunk,&proof,&reader->control,sdk_error);
    if(status!=EXR_OK) goto done;
    if(proof.at!=size) { code=READER_NAVIGATION_UNRESOLVED;goto done; }
    status=exr_pager_anchor_resolve(next->pager,&anchor,&reader->control,&match,sdk_error);
  } else status=exr_anchor_resolve_ex(next->document,&anchor,&reader->control,&match,sdk_error);
  result->navigation_match=match.state;
  if(status==EXR_OK && (match.state!=EXR_ANCHOR_FOUND || match.start!=offset)) { code=READER_NAVIGATION_UNRESOLVED;goto done; }
  if(status==EXR_OK) { status=render(reader,next,0,1,match.start,result,sdk_error);if(status==EXR_OK) { next->position=match.start;result->navigation_verified=1; } }
done:
  if(owner) navigation_phase(owner,3);
  if(result->navigation_verified && status==EXR_OK) { code=READER_NAVIGATION_OK;navigation_free(reader); }
  else if(status==EXR_CANCELLED) code=READER_NAVIGATION_CANCELLED;
  else if(status!=EXR_OK && code==READER_NAVIGATION_OK) { code=READER_NAVIGATION_SDK;error.sdk_code=status; }
  result->navigation_code=code;result->navigation_sdk_code=error.sdk_code;
  exr_anchor_free(&anchor);exr_document_free(loaded);session_free(&first);session_free(&second);
  reader_navigation_target_free(&target);reader_navigation_target_free(&verified);
  if(!result->navigation_verified) snprintf(result->message,sizeof(result->message),"%s",code==READER_NAVIGATION_PART_ONLY ? "Fragment absent. Explicitly open this part's start?":
    code==READER_NAVIGATION_AMBIGUOUS ? "Repeated part path. Choose the intended spine item":code==READER_NAVIGATION_NEEDS_HOST ? "External link not opened":
    "Directory target could not be proved; reading unchanged");
  return result->navigation_verified ? status:navigation_status(code,&error);
}
