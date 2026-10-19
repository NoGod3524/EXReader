/* SPDX-License-Identifier: MIT */
#ifndef EXR_TEXTINDEX_H
#define EXR_TEXTINDEX_H
#include "base.h"
#define EXR_TEXTINDEX_VERSION "0.19.0"
#ifdef __cplusplus
extern "C" {
#endif
/* Optional, derived full-text database. Source/part IDs belong to the host;
   indexed UTF-8 bytes are not tied to a book format, document model or UI. */
typedef struct exr_text_index exr_text_index;
typedef struct exr_text_query exr_text_query;
typedef struct {
  const char *source,*part,*text; size_t text_size,start,end;
} exr_text_hit;
EXR_API int exr_text_index_available(void);
EXR_API exr_status exr_text_index_open(const char *path,exr_text_index **index,exr_error *error);
EXR_API void exr_text_index_close(exr_text_index *index);
/* Replaces one part atomically. IDs <=4096 UTF-8 bytes; part may be empty.
   Text <=64 MiB-1, including NUL. No normalization/case folding is applied. */
EXR_API exr_status exr_text_index_put(exr_text_index *index,const char *source,const char *part,const void *text,
                                       size_t size,const exr_control *control,exr_error *error);
/* NULL part removes every part for this source, in one transaction. */
EXR_API exr_status exr_text_index_remove(exr_text_index *index,const char *source,const char *part,
                                          const exr_control *control,exr_error *error);
/* Streaming source replacement. Provider output borrows bytes until the next
   callback or replace() return. found=0 ends the sequence; an empty sequence
   clears this source. All parts replace atomically, including FTS postings. */
typedef struct { const char *id; const void *text; size_t size; } exr_text_part;
typedef exr_status (*exr_text_part_fn)(void *context,size_t index,exr_text_part *part,int *found,exr_error *error);
EXR_API exr_status exr_text_index_replace(exr_text_index *index,const char *source,exr_text_part_fn provider,void *context,
                                           const exr_control *control,exr_error *error);
/* Literal substring query (1..4096 UTF-8 bytes), optionally limited to source.
   One live query per index handle; release it before writing. Query retains the
   index and can outlive close(). Control/context remain borrowed until free(). */
EXR_API exr_status exr_text_index_query(exr_text_index *index,const char *source,const void *query,size_t size,
                                         const exr_control *control,exr_text_query **out,exr_error *error);
/* Row/insertion order, then UTF-8 byte range, including overlapping matches.
   Hit strings/text borrow the query until next/free. EOF: found=0. Errors clear
   outputs and invalidate the query; free it and start a new query to retry. */
EXR_API exr_status exr_text_query_next(exr_text_query *query,exr_text_hit *hit,int *found,exr_error *error);
EXR_API void exr_text_query_free(exr_text_query *query);
#ifdef __cplusplus
}
#endif
#endif
