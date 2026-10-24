/* SPDX-License-Identifier: MIT */
#ifndef EXR_LINUX_READING_H
#define EXR_LINUX_READING_H
#include <exreader.h>

/* Private GTK host messages. SDK handles stay on one worker; results own their
   page bytes and list strings and contain no borrowed layout pointers. */
typedef struct linux_reader linux_reader;
typedef enum { READER_SHELF, READER_OPEN, READER_IMPORT, READER_NEXT,
  READER_PREVIOUS, READER_FONT, READER_NOTE_ADD, READER_NOTE_REMOVE,
  READER_NOTE_JUMP, READER_COMMIT, READER_ZOOM, READER_SHELF_QUERY,
  READER_METADATA_PREPARE, READER_METADATA_SAVE, READER_METADATA_RETRY,
  READER_METADATA_DISCARD, READER_COLLECTIONS_LIST, READER_COLLECTIONS_PREPARE_GROUP,
  READER_COLLECTIONS_SAVE_GROUP, READER_COLLECTIONS_PREPARE_MEMBER,
  READER_COLLECTIONS_SAVE_MEMBER, READER_COLLECTIONS_RETRY, READER_COLLECTIONS_DISCARD } reader_action;
typedef struct {
  reader_action action;
  int64_t book,note;
  size_t part,start,end;
  int font;
  const char *path,*comment;
  int zoom;
  size_t page;
  const char *query,*cursor_title,*cursor_key,*anchor_key;
  int direction;
  const char *metadata_key,*metadata_title,*metadata_author;
  uint64_t metadata_token;
  int metadata_favorite;
  int collection_kind,collection_removed,collection_operation;
  int collection_group_direction,collection_member_direction;
  uint64_t collection_token,collection_group_cursor_ordinal,collection_member_cursor_ordinal;
  const char *collection_parent,*collection_id,*collection_name,*collection_position,*collection_book_key;
  const char *collection_group_cursor,*collection_member_cursor;
} reader_command;
typedef struct { int64_t id;size_t part,start,end;char *text; } reader_note;
typedef struct { char *key,*sort_title; } reader_shelf_cursor;
typedef struct { char *id,*name,*parent;uint64_t ordinal;int deleted; } reader_collection_group;
typedef struct { char *key,*title,*author;uint64_t ordinal;int64_t sdk_id; } reader_collection_member;
typedef struct {
  exr_status status;
  char message[160];
  int has_frame,has_shelf,bounded,font,select_range;
  int64_t book;
  size_t part,page,start,end,position,selected_start,selected_end;
  size_t width,height,stride,text_size;
  unsigned char *pixels;
  char *text;
  exr_book *books;size_t book_count;
  reader_shelf_cursor *cursors;
  int shelf_before,shelf_after,shelf_direction,shelf_pending;
  reader_note *notes;size_t note_count;
  exr_chapter_stats chapter;
  int fixed,zoom;
  size_t page_count;
  int has_metadata,metadata_favorite,metadata_conflict,metadata_needs_bootstrap;
  int metadata_pending,metadata_committed;
  uint64_t metadata_token;
  char *metadata_title,*metadata_author;
  int has_collections,collection_response,collection_kind,collection_removed,collection_operation;
  int collection_group_before,collection_group_after,collection_member_before,collection_member_after;
  int collection_conflict,collection_dependency,collection_membership_present,collection_membership_deleted;
  uint64_t collection_token,collection_ordinal;
  reader_collection_group *collection_groups;size_t collection_group_count;
  reader_collection_member *collection_members;size_t collection_member_count;
  reader_collection_group collection_selected,collection_navigation,collection_dependency_group;
  char *collection_book_key,*collection_book_title;
} reader_result;
exr_status linux_reader_open(const char *database,const char *font,const exr_control *control,
                            linux_reader **out,exr_error *error);
void linux_reader_close(linux_reader *reader);
void linux_reader_execute(linux_reader *reader,const reader_command *command,reader_result *result);
void reader_result_free(reader_result *result);
#endif
