/* SPDX-License-Identifier: MIT */
/* Product-owner bridge. Every page and prepared snapshot stays on this worker;
 * GTK receives independent strings and a nonce, never a native handle. */
typedef struct { reader_result *result;reader_collection_group *single;int failed; } collections_groups_copy;
static int collections_kind(int kind,reader_catalog_group_kind *catalog_kind,reader_group_kind *command_kind) {
  if(kind<0 || kind>2) return 0;
  *catalog_kind=(reader_catalog_group_kind)kind;*command_kind=(reader_group_kind)kind;return 1;
}
static int collections_group_copy(reader_collection_group *out,const reader_catalog_group_row *row) {
  out->id=strdup(row->id ? row->id:"");out->name=strdup(row->name ? row->name:"");
  out->parent=strdup(row->parent_id ? row->parent_id:"");out->ordinal=row->ordinal;out->deleted=row->deleted;
  return out->id && out->name && out->parent;
}
static int collections_receive_group(void *context,const reader_catalog_group_row *row) {
  collections_groups_copy *copy=context;reader_collection_group *out=copy->single;
  if(!out) {
    if(copy->result->collection_group_count>=50) { copy->failed=1;return 1; }
    out=&copy->result->collection_groups[copy->result->collection_group_count++];
  }
  if(!collections_group_copy(out,row)) { copy->failed=1;return 1; }
  return 0;
}
static int collections_group_exists(void *context,const reader_catalog_group_row *row) { (void)row;*(int *)context=1;return 1; }
static exr_status collections_find_group(linux_reader *reader,int kind,const char *id,reader_collection_group *out) {
  if(!id || !id[0]) return EXR_OK;
  reader_catalog_group_kind native;reader_group_kind producer;
  if(!collections_kind(kind,&native,&producer)) return EXR_ARGUMENT;
  reader_catalog_error error={0};int found=0;collections_groups_copy copy={NULL,out,0};
  int code=reader_catalog_group_find(reader->catalog,native,id,collections_receive_group,&copy,&found,&error);
  return copy.failed ? EXR_MEMORY:code ? EXR_DATABASE:EXR_OK;
}
static int collections_groups_page(linux_reader *reader,const reader_command *command,
  const reader_catalog_group_cursor *cursor,int direction,size_t limit,reader_catalog_group_visit visit,void *context) {
  reader_catalog_error error={0};reader_catalog_group_kind kind=(reader_catalog_group_kind)command->collection_kind;
  if(command->collection_removed) return reader_catalog_removed_groups_page(reader->catalog,kind,cursor ? cursor->id:NULL,direction,limit,visit,context,&error);
  return reader_catalog_groups_page(reader->catalog,kind,command->collection_kind==0 && command->collection_parent && command->collection_parent[0] ?
    command->collection_parent:NULL,cursor,direction,limit,visit,context,&error);
}
typedef struct { reader_result *result;int failed; } collections_members_copy;
static int collections_receive_member(void *context,const reader_catalog_group_book_row *row) {
  collections_members_copy *copy=context;reader_result *result=copy->result;
  if(result->collection_member_count>=50) { copy->failed=1;return 1; }
  reader_collection_member *out=&result->collection_members[result->collection_member_count++];
  out->key=strdup(row->book.book_key);out->title=strdup(row->book.title);out->author=strdup(row->book.author);
  out->ordinal=row->ordinal;out->sdk_id=row->book.sdk_book_id;
  if(!out->key || !out->title || !out->author) { copy->failed=1;return 1; }
  return 0;
}
static int collections_member_exists(void *context,const reader_catalog_group_book_row *row) { (void)row;*(int *)context=1;return 1; }
static exr_status collections_list(linux_reader *reader,const reader_command *command,reader_result *result) {
  reader_catalog_group_kind native;reader_group_kind producer;
  if(!collections_kind(command->collection_kind,&native,&producer)) return EXR_ARGUMENT;
  result->collection_groups=calloc(50,sizeof(*result->collection_groups));
  result->collection_members=calloc(50,sizeof(*result->collection_members));
  if(!result->collection_groups || !result->collection_members) return EXR_MEMORY;
  reader_catalog_group_cursor cursor={command->collection_group_cursor_ordinal,command->collection_group_cursor};
  const reader_catalog_group_cursor *position=cursor.id && cursor.id[0] ? &cursor:NULL;
  int direction=command->collection_group_direction<0 ? -1:1;
  collections_groups_copy copy={result,NULL,0};
  int code=collections_groups_page(reader,command,position,direction,50,collections_receive_group,&copy);
  if(code || copy.failed) return copy.failed ? EXR_MEMORY:EXR_DATABASE;
  if(direction<0) for(size_t i=0;i<result->collection_group_count/2;i++) {
    size_t j=result->collection_group_count-1-i;reader_collection_group row=result->collection_groups[i];
    result->collection_groups[i]=result->collection_groups[j];result->collection_groups[j]=row;
  }
  if(result->collection_group_count) {
    reader_collection_group *first=&result->collection_groups[0],*last=&result->collection_groups[result->collection_group_count-1];
    reader_catalog_group_cursor before={first->ordinal,first->id},after={last->ordinal,last->id};
    code=collections_groups_page(reader,command,&before,-1,1,collections_group_exists,&result->collection_group_before);
    if(!code) code=collections_groups_page(reader,command,&after,1,1,collections_group_exists,&result->collection_group_after);
  } else if(position) {
    int *exists=direction>0 ? &result->collection_group_before:&result->collection_group_after;
    code=collections_groups_page(reader,command,position,-direction,1,collections_group_exists,exists);
  }
  if(code) return EXR_DATABASE;
  const char *selected=command->collection_id;
  if((!selected || !selected[0]) && result->collection_group_count) selected=result->collection_groups[0].id;
  exr_status status=collections_find_group(reader,command->collection_kind,selected,&result->collection_selected);
  if(status==EXR_OK && command->collection_kind==0 && command->collection_parent && command->collection_parent[0])
    status=collections_find_group(reader,0,command->collection_parent,&result->collection_navigation);
  if(status!=EXR_OK) return status;
  if(result->collection_selected.parent && result->collection_selected.parent[0]) {
    status=collections_find_group(reader,0,result->collection_selected.parent,&result->collection_dependency_group);
    if(status!=EXR_OK) return status;
    result->collection_dependency=!result->collection_dependency_group.id || result->collection_dependency_group.deleted;
  }
  if(result->collection_selected.id && !result->collection_selected.deleted) {
    reader_catalog_member_cursor member={command->collection_kind==1 ? 0:command->collection_member_cursor_ordinal,command->collection_member_cursor};
    const reader_catalog_member_cursor *after=member.book_key && member.book_key[0] ? &member:NULL;
    int member_direction=command->collection_member_direction<0 ? -1:1;reader_catalog_error error={0};
    collections_members_copy members={result,0};
    code=reader_catalog_group_books_page(reader->catalog,native,result->collection_selected.id,after,NULL,0,member_direction,50,
      collections_receive_member,&members,&error);
    if(code || members.failed) return members.failed ? EXR_MEMORY:EXR_DATABASE;
    if(member_direction<0) for(size_t i=0;i<result->collection_member_count/2;i++) {
      size_t j=result->collection_member_count-1-i;reader_collection_member row=result->collection_members[i];
      result->collection_members[i]=result->collection_members[j];result->collection_members[j]=row;
    }
    if(result->collection_member_count) {
      reader_collection_member *first=&result->collection_members[0],*last=&result->collection_members[result->collection_member_count-1];
      reader_catalog_member_cursor before={first->ordinal,first->key},later={last->ordinal,last->key};
      code=reader_catalog_group_books_page(reader->catalog,native,result->collection_selected.id,&before,NULL,0,-1,1,
        collections_member_exists,&result->collection_member_before,&error);
      if(!code) code=reader_catalog_group_books_page(reader->catalog,native,result->collection_selected.id,&later,NULL,0,1,1,
        collections_member_exists,&result->collection_member_after,&error);
    } else if(after) {
      int *exists=member_direction>0 ? &result->collection_member_before:&result->collection_member_after;
      code=reader_catalog_group_books_page(reader->catalog,native,result->collection_selected.id,after,NULL,0,-member_direction,1,
        collections_member_exists,exists,&error);
    }
    if(code) return EXR_DATABASE;
  }
  result->has_collections=1;result->collection_response=1;result->collection_kind=command->collection_kind;
  result->collection_removed=command->collection_removed;snprintf(result->message,sizeof(result->message),"Collections ready");return EXR_OK;
}
static exr_status collections_no_pending(linux_reader *reader,reader_result *result) {
  reader_metadata_result pending={0};reader_metadata_error error={0};
  reader_metadata_status code=reader_metadata_pending(reader->metadata,&pending,&error);
  if(code==READER_METADATA_NO_PENDING) return EXR_OK;
  if(code==READER_METADATA_OK) { result->metadata_pending=1;return metadata_failure(result,READER_METADATA_PENDING,NULL); }
  return metadata_failure(result,code,&error);
}
static void collections_next_token(linux_reader *reader,reader_result *result) {
  if(++reader->collection_token==0) ++reader->collection_token;
  result->collection_token=reader->collection_token;
}
static exr_status collections_prepare_group(linux_reader *reader,const reader_command *command,reader_result *result) {
  reader_catalog_group_kind native;reader_group_kind producer;
  if(!collections_kind(command->collection_kind,&native,&producer) || command->collection_operation<0 || command->collection_operation>2) return EXR_ARGUMENT;
  reader_metadata_snapshot_free(reader->collection_snapshot);reader->collection_snapshot=NULL;
  reader_metadata_error error={0};reader_metadata_status code=reader_metadata_prepare_group(reader->metadata,producer,
    command->collection_id,&reader->collection_snapshot,&error);
  if(code!=READER_METADATA_OK && code!=READER_METADATA_CONFLICT) return metadata_failure(result,code,&error);
  const reader_metadata_view *view=reader_metadata_snapshot_view(reader->collection_snapshot);
  if(!view) return metadata_failure(result,code,&error);
  const char *parent=view->present ? view->group.parent_id:command->collection_kind==0 ? command->collection_parent:"";
  snprintf(reader->collection_parent,sizeof(reader->collection_parent),"%s",parent ? parent:"");
  reader_catalog_group_row row={view->group.id,view->group.name,reader->collection_parent,view->group.ordinal,view->deleted};
  if(!collections_group_copy(&result->collection_selected,&row)) return EXR_MEMORY;
  result->collection_conflict=code==READER_METADATA_CONFLICT ||
    (view->deleted && command->collection_operation!=2) ||
    (command->collection_operation==2 && !view->deleted) ||
    (command->collection_operation!=0 && (!view->present || !view->head_count));
  if(command->collection_kind==0 && reader->collection_parent[0] && command->collection_operation!=1) {
    exr_status status=collections_find_group(reader,0,reader->collection_parent,&result->collection_dependency_group);
    if(status!=EXR_OK) return status;
    result->collection_dependency=!result->collection_dependency_group.id || result->collection_dependency_group.deleted;
  }
  reader->collection_entity=0;reader->collection_kind=command->collection_kind;reader->collection_operation=command->collection_operation;
  result->has_collections=1;result->collection_response=2;result->collection_kind=command->collection_kind;
  result->collection_operation=command->collection_operation;result->collection_ordinal=view->group.ordinal;
  collections_next_token(reader,result);return EXR_OK;
}
typedef struct { int64_t id;char *title;int failed; } collections_book_lookup;
static int collections_receive_book(void *context,const reader_catalog_row *row) {
  collections_book_lookup *book=context;book->id=row->sdk_book_id;book->title=strdup(row->title);book->failed=book->title==NULL;return 0;
}
static exr_status collections_bootstrap_book(linux_reader *reader,const char *key,reader_result *result) {
  reader_metadata_snapshot *snapshot=NULL;reader_metadata_error error={0};
  reader_metadata_status code=reader_metadata_prepare_book(reader->metadata,key,&snapshot,&error);
  if(code!=READER_METADATA_NEEDS_BOOTSTRAP) { reader_metadata_snapshot_free(snapshot);return code==READER_METADATA_OK ? EXR_OK:metadata_failure(result,code,&error); }
  reader_catalog_error catalog_error={0};int found=0;collections_book_lookup book={0};
  int lookup=reader_catalog_find(reader->catalog,key,NULL,collections_receive_book,&book,&found,&catalog_error);free(book.title);
  if(lookup || book.failed || !found || book.id<=0) {
    reader_metadata_snapshot_free(snapshot);snprintf(result->message,sizeof(result->message),"Import and verify this original before its first classification");return EXR_ARGUMENT;
  }
  reader_metadata_snapshot_free(reader->metadata_snapshot);reader->metadata_snapshot=snapshot;reader->metadata_book=book.id;
  const reader_metadata_view *view=reader_metadata_snapshot_view(snapshot);
  exr_status status=view ? metadata_bootstrap(reader,view,result):EXR_MEMORY;
  reader_metadata_snapshot_free(reader->metadata_snapshot);reader->metadata_snapshot=NULL;++reader->metadata_token;
  return status;
}
static exr_status collections_prepare_member(linux_reader *reader,const reader_command *command,reader_result *result) {
  reader_catalog_group_kind native;reader_group_kind producer;
  if(!collections_kind(command->collection_kind,&native,&producer) || !command->collection_id || !command->collection_book_key ||
    command->collection_operation<0 || command->collection_operation>2) return EXR_ARGUMENT;
  reader_metadata_snapshot_free(reader->collection_snapshot);reader->collection_snapshot=NULL;
  reader_metadata_error error={0};reader_metadata_status code=reader_metadata_prepare_membership(reader->metadata,producer,
    command->collection_id,command->collection_book_key,&reader->collection_snapshot,&error);
  if(code==READER_METADATA_NEEDS_BOOTSTRAP) {
    reader_metadata_snapshot_free(reader->collection_snapshot);reader->collection_snapshot=NULL;
    exr_status status=collections_bootstrap_book(reader,command->collection_book_key,result);if(status!=EXR_OK) return status;
    code=reader_metadata_prepare_membership(reader->metadata,producer,command->collection_id,command->collection_book_key,
      &reader->collection_snapshot,&error);
  }
  if(code!=READER_METADATA_OK && code!=READER_METADATA_CONFLICT) return metadata_failure(result,code,&error);
  const reader_metadata_view *view=reader_metadata_snapshot_view(reader->collection_snapshot);
  if(!view) return metadata_failure(result,code,&error);
  reader_catalog_error catalog_error={0};int found=0;collections_book_lookup book={0};
  int lookup=reader_catalog_metadata(reader->catalog,command->collection_book_key,collections_receive_book,&book,&found,&catalog_error);
  if(lookup || book.failed || !found) { free(book.title);return EXR_DATABASE; }
  result->collection_book_title=book.title;result->collection_book_key=strdup(command->collection_book_key);
  if(!result->collection_book_key) return EXR_MEMORY;
  exr_status status=collections_find_group(reader,command->collection_kind,command->collection_id,&result->collection_selected);
  if(status!=EXR_OK) return status;
  reader->collection_operation=command->collection_operation==0 && view->deleted ? 2:command->collection_operation;
  reader->collection_entity=1;reader->collection_kind=command->collection_kind;
  result->collection_conflict=code==READER_METADATA_CONFLICT || (reader->collection_operation==1 && !view->present);
  result->collection_dependency=view->dependency_deleted;
  result->collection_membership_present=view->present;result->collection_membership_deleted=view->deleted;
  result->has_collections=1;result->collection_response=3;result->collection_kind=command->collection_kind;
  result->collection_operation=reader->collection_operation;result->collection_ordinal=view->membership.ordinal;
  collections_next_token(reader,result);return EXR_OK;
}
static int collections_position(const char *text,uint64_t *value) {
  if(!text || !text[0] || strlen(text)>19) return 0;
  for(const char *p=text;*p;p++) if(*p<'0' || *p>'9') return 0;
  errno=0;char *end=NULL;unsigned long long parsed=strtoull(text,&end,10);
  if(errno || !end || *end || parsed>INT64_MAX) return 0;
  *value=(uint64_t)parsed;return 1;
}
static exr_status collections_save(linux_reader *reader,const reader_command *command,reader_result *result,int entity) {
  if(!reader->collection_snapshot || !command->collection_token || command->collection_token!=reader->collection_token ||
    reader->collection_entity!=entity || reader->collection_kind!=command->collection_kind || reader->collection_operation!=command->collection_operation) return EXR_ARGUMENT;
  const reader_metadata_view *view=reader_metadata_snapshot_view(reader->collection_snapshot);if(!view) return EXR_MEMORY;
  reader_metadata_result submitted={0};reader_metadata_error error={0};reader_metadata_status code;
  uint64_t ordinal=0;
  if((entity==0 && command->collection_kind==0) || (entity==1 && command->collection_kind!=1)) {
    if(!collections_position(command->collection_position,&ordinal)) { snprintf(result->message,sizeof(result->message),"Position must be a nonnegative whole number");return EXR_ARGUMENT; }
  }
  if(entity==0) {
    reader_group_command input={ (reader_command_operation)reader->collection_operation,(reader_group_kind)reader->collection_kind,
      view->group.id,command->collection_name,reader->collection_parent,ordinal };
    code=reader_metadata_stage_group(reader->metadata,reader->collection_snapshot,&input,&submitted,&error);
  } else {
    reader_membership_command input=view->membership;input.operation=(reader_command_operation)reader->collection_operation;input.ordinal=ordinal;
    code=reader_metadata_stage_membership(reader->metadata,reader->collection_snapshot,&input,&submitted,&error);
  }
  if(code==READER_METADATA_OK) code=reader_metadata_finish_pending(reader->metadata,&submitted,&error);
  result->metadata_committed=submitted.committed;result->metadata_pending=submitted.pending;
  if(code!=READER_METADATA_OK) return metadata_pending_failure(reader,result,code,&error);
  result->collection_selected.id=strdup(entity==0 ? submitted.command.entity_key:view->membership.group_id);
  result->collection_book_key=entity==1 ? strdup(view->membership.book_key):NULL;
  if(!result->collection_selected.id || (entity==1 && !result->collection_book_key)) return EXR_MEMORY;
  reader_metadata_snapshot_free(reader->collection_snapshot);reader->collection_snapshot=NULL;++reader->collection_token;
  result->has_collections=1;result->collection_response=4;result->collection_kind=command->collection_kind;
  result->collection_operation=command->collection_operation;snprintf(result->message,sizeof(result->message),"Collection change saved locally");return EXR_OK;
}
static void collections_execute(linux_reader *reader,const reader_command *command,reader_result *result) {
  result->status=metadata_ready(reader,result);if(result->status!=EXR_OK) return;
  if(command->action==READER_COLLECTIONS_RETRY || command->action==READER_COLLECTIONS_DISCARD) {
    reader_metadata_result submitted={0};reader_metadata_error error={0};
    reader_metadata_status code=command->action==READER_COLLECTIONS_RETRY ? reader_metadata_finish_pending(reader->metadata,&submitted,&error):
      reader_metadata_abandon_pending(reader->metadata,&error);
    result->metadata_committed=submitted.committed;result->metadata_pending=submitted.pending;
    result->status=code==READER_METADATA_OK || code==READER_METADATA_NO_PENDING ? EXR_OK:metadata_pending_failure(reader,result,code,&error);
    if(result->status==EXR_OK) {
      reader_metadata_snapshot_free(reader->collection_snapshot);reader->collection_snapshot=NULL;++reader->collection_token;
      result->has_collections=1;result->collection_response=4;
      snprintf(result->message,sizeof(result->message),"%s",command->action==READER_COLLECTIONS_RETRY ? "Earlier change recovered":"Uncommitted change discarded");
    }
    return;
  }
  result->status=collections_no_pending(reader,result);if(result->status!=EXR_OK) return;
  if(command->action==READER_COLLECTIONS_LIST) result->status=collections_list(reader,command,result);
  else if(command->action==READER_COLLECTIONS_PREPARE_GROUP) result->status=collections_prepare_group(reader,command,result);
  else if(command->action==READER_COLLECTIONS_PREPARE_MEMBER) result->status=collections_prepare_member(reader,command,result);
  else result->status=collections_save(reader,command,result,command->action==READER_COLLECTIONS_SAVE_GROUP ? 0:1);
}
