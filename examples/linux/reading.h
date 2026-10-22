/* SPDX-License-Identifier: MIT */
#ifndef EXR_LINUX_READING_H
#define EXR_LINUX_READING_H
#include <exreader.h>

/* Private GTK host messages. SDK handles stay on one worker; results own their
   page bytes and list strings and contain no borrowed layout pointers. */
typedef struct linux_reader linux_reader;
typedef enum { READER_SHELF, READER_OPEN, READER_IMPORT, READER_NEXT,
  READER_PREVIOUS, READER_FONT, READER_NOTE_ADD, READER_NOTE_REMOVE,
  READER_NOTE_JUMP } reader_action;
typedef struct {
  reader_action action;
  int64_t book,note;
  size_t start,end;
  int font;
  const char *path,*comment;
} reader_command;
typedef struct { int64_t id;size_t part,start,end;char *text; } reader_note;
typedef struct {
  exr_status status;
  char message[160];
  int has_frame,bounded,font,select_range;
  int64_t book;
  size_t part,page,start,end,selected_start,selected_end;
  size_t width,height,stride,text_size;
  unsigned char *pixels;
  char *text;
  exr_book *books;size_t book_count;
  reader_note *notes;size_t note_count;
  exr_chapter_stats chapter;
} reader_result;
exr_status linux_reader_open(const char *database,const char *font,const exr_control *control,
                            linux_reader **out,exr_error *error);
void linux_reader_close(linux_reader *reader);
void linux_reader_execute(linux_reader *reader,const reader_command *command,reader_result *result);
void reader_result_free(reader_result *result);
#endif
