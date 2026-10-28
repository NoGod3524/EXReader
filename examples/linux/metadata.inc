/* SPDX-License-Identifier: MIT */
/* Included by the GTK reading owner after the bounded product shelf helpers. */
static exr_status metadata_failure(reader_result *result,reader_metadata_status status,
                                    const reader_metadata_error *error) {
  snprintf(result->message,sizeof(result->message),"%s",error && error->message[0] ? error->message:
    status==READER_METADATA_CONFLICT ? "Conflicting book versions are retained; review before editing":
    status==READER_METADATA_PENDING ? "An earlier edit needs recovery before another edit":
    "Book organization is unavailable; saved reading state is retained");
  return status==READER_METADATA_IO ? EXR_IO:status==READER_METADATA_ARGUMENT ? EXR_ARGUMENT:EXR_DATABASE;
}
static exr_status metadata_ready(linux_reader *reader,reader_result *result) {
  if(reader->metadata) return EXR_OK;
  if(!reader->catalog) return EXR_DATABASE;
  size_t size=strlen(reader->catalog_path)+32;char *path=malloc(size);
  if(!path) return EXR_MEMORY;
  snprintf(path,size,"%s.commands.pending",reader->catalog_path);
  reader_metadata_error error={0};reader_metadata_status status=reader_metadata_open(
    reader->catalog_path,path,&reader->metadata,&error);free(path);
  return status==READER_METADATA_OK ? EXR_OK:metadata_failure(result,status,&error);
}
static exr_status metadata_pending_failure(linux_reader *reader,reader_result *result,
  reader_metadata_status code,const reader_metadata_error *error) {
  reader_metadata_result pending={0};reader_metadata_error probe={0};
  if(reader_metadata_pending(reader->metadata,&pending,&probe)==READER_METADATA_OK) result->metadata_pending=1;
  return metadata_failure(result,code,error);
}
static exr_status metadata_bootstrap(linux_reader *reader,const reader_metadata_view *view,reader_result *result) {
  char digest[65],key[READER_BOOK_KEY_CAPACITY];uint64_t bytes=0;exr_error source_error={0};
  exr_status status=reader_catalog_sdk_original_identity(reader->library,reader->metadata_book,
    &reader->control,digest,&bytes,&source_error);
  if(status!=EXR_OK) {
    snprintf(result->message,sizeof(result->message),"Download and verify the original before its first edit");return status;
  }
  if(strcmp(digest,view->book.source_sha256) || bytes!=view->book.source_bytes) {
    snprintf(result->message,sizeof(result->message),"Stored original identity differs; edit refused");return EXR_DATABASE;
  }
  snprintf(key,sizeof(key),"%s",view->book.book_key);
  reader_metadata_verified_source proof={view->book.format,digest,bytes};
  reader_metadata_error error={0};reader_metadata_result submitted={0};
  reader_metadata_status code=reader_metadata_stage_bootstrap(reader->metadata,reader->metadata_snapshot,&proof,&submitted,&error);
  if(code==READER_METADATA_OK) code=reader_metadata_finish_pending(reader->metadata,&submitted,&error);
  if(code!=READER_METADATA_OK) {
    result->metadata_pending=submitted.pending;return metadata_pending_failure(reader,result,code,&error);
  }
  reader_metadata_snapshot_free(reader->metadata_snapshot);reader->metadata_snapshot=NULL;
  code=reader_metadata_prepare_book(reader->metadata,key,&reader->metadata_snapshot,&error);
  return code==READER_METADATA_OK ? EXR_OK:metadata_failure(result,code,&error);
}
static exr_status metadata_prepare(linux_reader *reader,const reader_command *command,reader_result *result) {
  reader_metadata_result pending={0};reader_metadata_error error={0};
  reader_metadata_status code=reader_metadata_pending(reader->metadata,&pending,&error);
  if(code==READER_METADATA_OK) {
    result->metadata_pending=1;return metadata_failure(result,READER_METADATA_PENDING,NULL);
  }
  if(code!=READER_METADATA_NO_PENDING) return metadata_failure(result,code,&error);
  reader_metadata_snapshot_free(reader->metadata_snapshot);reader->metadata_snapshot=NULL;
  code=reader_metadata_prepare_book(reader->metadata,command->metadata_key,&reader->metadata_snapshot,&error);
  if(code!=READER_METADATA_OK && code!=READER_METADATA_NEEDS_BOOTSTRAP && code!=READER_METADATA_CONFLICT)
    return metadata_failure(result,code,&error);
  const reader_metadata_view *view=reader_metadata_snapshot_view(reader->metadata_snapshot);
  if(!view || !view->present) {
    snprintf(result->message,sizeof(result->message),"This book is no longer available in the product catalog");return EXR_ARGUMENT;
  }
  reader->metadata_book=command->book;
  if(view->needs_bootstrap && code!=READER_METADATA_CONFLICT && !view->deleted) {
    /* Establish unchanged legacy metadata before exposing editable fields.
     * A later Save is one separately durable typed edit, never a two-step replay. */
    exr_status status=metadata_bootstrap(reader,view,result);if(status!=EXR_OK) return status;
    view=reader_metadata_snapshot_view(reader->metadata_snapshot);
    if(!view) return EXR_MEMORY;
  }
  result->metadata_title=strdup(view->book.title);result->metadata_author=strdup(view->book.author);
  if(!result->metadata_title || !result->metadata_author) return EXR_MEMORY;
  if(++reader->metadata_token==0) ++reader->metadata_token;
  result->metadata_token=reader->metadata_token;
  result->metadata_favorite=view->book.favorite;result->metadata_needs_bootstrap=view->needs_bootstrap;
  result->metadata_conflict=code==READER_METADATA_CONFLICT || view->deleted;
  result->has_metadata=1;
  snprintf(result->message,sizeof(result->message),"%s",result->metadata_conflict ?
    "Conflicting or removed book versions are retained; editing is disabled":"Book details ready");
  return EXR_OK;
}
static exr_status metadata_save(linux_reader *reader,const reader_command *command,reader_result *result) {
  const reader_metadata_view *view=reader_metadata_snapshot_view(reader->metadata_snapshot);
  if(!view || !command->metadata_token || command->metadata_token!=reader->metadata_token ||
     !command->metadata_key || strcmp(command->metadata_key,view->book.book_key) ||
     !command->metadata_title || !command->metadata_author || view->deleted ||
     view->needs_bootstrap || (view->graph.revisions && !view->graph.projection_safe && !command->metadata_resolution) ||
     (command->metadata_favorite!=0 && command->metadata_favorite!=1)) return EXR_ARGUMENT;
  reader_metadata_error error={0};reader_metadata_result submitted={0};reader_metadata_status code;
  gchar *sort=g_utf8_normalize(command->metadata_title,-1,G_NORMALIZE_DEFAULT_COMPOSE);
  if(!sort) return EXR_ENCODING;
  reader_book_command edit=view->book;edit.operation=READER_COMMAND_PUT;
  edit.title=command->metadata_title;edit.author=command->metadata_author;edit.sort_title=sort;
  edit.favorite=command->metadata_favorite;
  code=command->metadata_resolution ? reader_metadata_stage_book_resolution(reader->metadata,reader->metadata_snapshot,&edit,&submitted,&error):
    reader_metadata_stage_book(reader->metadata,reader->metadata_snapshot,&edit,&submitted,&error);g_free(sort);
  if(code!=READER_METADATA_OK) return metadata_pending_failure(reader,result,code,&error);
  code=reader_metadata_finish_pending(reader->metadata,&submitted,&error);
  result->metadata_committed=submitted.committed;result->metadata_pending=submitted.pending;
  if(code!=READER_METADATA_OK) return metadata_pending_failure(reader,result,code,&error);
  if(!submitted.committed) return EXR_DATABASE;
  reader_metadata_snapshot_free(reader->metadata_snapshot);reader->metadata_snapshot=NULL;
  ++reader->metadata_token;
  snprintf(result->message,sizeof(result->message),"Book details saved locally");return EXR_OK;
}
static void metadata_execute(linux_reader *reader,const reader_command *command,reader_result *result) {
  result->status=metadata_ready(reader,result);if(result->status!=EXR_OK) return;
  if(command->action==READER_METADATA_PREPARE) result->status=metadata_prepare(reader,command,result);
  else if(command->action==READER_METADATA_SAVE) result->status=metadata_save(reader,command,result);
  else {
    reader_metadata_error error={0};reader_metadata_result submitted={0};
    reader_metadata_status code=command->action==READER_METADATA_RETRY ?
      reader_metadata_finish_pending(reader->metadata,&submitted,&error):
      reader_metadata_abandon_pending(reader->metadata,&error);
    result->metadata_committed=submitted.committed;result->metadata_pending=submitted.pending;
    result->status=code==READER_METADATA_OK || code==READER_METADATA_NO_PENDING ? EXR_OK:metadata_failure(result,code,&error);
    if(result->status==EXR_OK) snprintf(result->message,sizeof(result->message),"%s",
      command->action==READER_METADATA_RETRY ? "Earlier edit recovered":"Uncommitted edit discarded");
  }
  if((result->status==EXR_OK && command->action!=READER_METADATA_PREPARE) || result->metadata_committed) {
    reader_command shelf=*command;shelf.direction=0;shelf.cursor_key=shelf.cursor_title=NULL;
    exr_status status=product_shelf(reader,&shelf,result);
    if(status!=EXR_OK && result->status==EXR_OK) {
      snprintf(result->message,sizeof(result->message),"Edit saved; refresh the shelf to see the result");
    }
  }
}
