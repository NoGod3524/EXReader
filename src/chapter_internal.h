/* SPDX-License-Identifier: MIT */
#ifndef EXR_CHAPTER_INTERNAL_H
#define EXR_CHAPTER_INTERNAL_H
#include "document_internal.h"

#define EXR_CHAPTER_NONE UINT32_MAX
/* Stable global coordinates; decoded strings and computed styles are window data.
   Chunk allocation avoids geometric array slack in the retained index. */
typedef struct {
  uint32_t parent, first_child, next_sibling, start, end;
  uint32_t source_start, source_end, tag_kind;
} exr_chapter_entry;
typedef struct exr_chapter_index exr_chapter_index;
exr_status exr_chapter_index_begin(const exr_control *control, size_t budget,
                                  exr_chapter_index **out, exr_error *error);
exr_status exr_chapter_index_feed(exr_chapter_index *index, const void *data,
                                 size_t size, int final, exr_error *error);
const exr_chapter_entry *exr_chapter_index_entry(const exr_chapter_index *index, size_t node);
const char *exr_chapter_index_name(const exr_chapter_index *index, size_t node);
size_t exr_chapter_index_count(const exr_chapter_index *index);
size_t exr_chapter_index_text_size(const exr_chapter_index *index);
size_t exr_chapter_index_memory(const exr_chapter_index *index);
size_t exr_chapter_index_peak(const exr_chapter_index *index);
void exr_chapter_index_free(exr_chapter_index *index);
typedef exr_status (*exr_chapter_sink_fn)(void *context,const void *data,size_t size,int final,exr_error *error);
typedef exr_status (*exr_chapter_pump_fn)(void *source,exr_chapter_sink_fn sink,void *context,
                                        const exr_control *control,exr_error *error);
typedef struct {
  exr_document *document;
  uint32_t *global_nodes; /* one stable global ID per local document node */
  size_t node_count, text_base, memory_bytes, peak_bytes, first, last;
} exr_chapter_window;
/* Retains only [first,last), its ancestors and every style/link declaration.
   The metadata document is borrowed until window_free; no source bytes are copied.
   projection=0 is a style-only scan; projection=1 requires a complete block range
   and validates every projected text-node range against the immutable index. */
exr_status exr_chapter_window_load(const exr_chapter_index *index,const exr_document *metadata,
  size_t first,size_t last,int projection,exr_chapter_pump_fn pump,void *source,
  size_t budget,const exr_control *control,exr_chapter_window *out,exr_error *error);
void exr_chapter_window_free(exr_chapter_window *window);
/* The consumer borrows a dense style-only batch for the duration of its call.
   memory_bytes includes the visitor's parser, declaration template and batch. */
typedef exr_status (*exr_chapter_window_consumer_fn)(const exr_chapter_window *window,
                                                    void *context,exr_error *error);
exr_status exr_chapter_windows_visit(const exr_chapter_index *index,const exr_document *metadata,
  size_t batch_nodes,exr_chapter_pump_fn pump,void *source,size_t budget,const exr_control *control,
  exr_chapter_window_consumer_fn consumer,void *context,exr_error *error);
exr_node_kind exr_xml_element_kind(const char *name);
int exr_projection_boundary(exr_node_kind kind, const char *tag);
#endif
