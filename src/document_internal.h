/* SPDX-License-Identifier: MIT */
#ifndef EXR_DOCUMENT_INTERNAL_H
#define EXR_DOCUMENT_INTERNAL_H
#include "base_internal.h"
#include "exr/document.h"
typedef struct {
  unsigned char *bytes;
  size_t size;
} exr_resource_data;
typedef struct {
  unsigned char *bytes;
  size_t size, refs;
  exr_source source;
  void *protection;
  void (*protection_free)(void *context);
} exr_archive_store;
/* Private reading view. Full public documents keep their contiguous arrays;
   a chapter reader supplies indexed nodes and resident projection spans. */
typedef struct {
  void *context;
  exr_node (*node)(void *context,size_t index);
  const char *(*text)(void *context,size_t offset,size_t *available);
  const void *(*style)(void *context,size_t index);
  exr_status (*writing)(void *context,size_t node,int mode,exr_error *error);
  const void *font_rules;
  size_t font_count;
  exr_status (*prepare)(void *context,size_t node,const exr_control *control,exr_error *error);
  exr_status (*status)(void *context,exr_error *error);
} exr_document_view;
/* EPUB 3 Fixed Layout rendition of one chapter (package default plus itemref
   override). spread: 0 unspecified, 1 left, 2 right, 3 center. The package
   rendition:viewport is a fallback; a content <meta name="viewport"> wins. */
typedef struct {
  unsigned char fixed, spread;
  float viewport_width, viewport_height;
} exr_rendition;
/* Parse "width=W, height=H" (HTML/EPUB viewport syntax). Returns 1 when both
   dimensions are finite and in 1..16384 CSS px; outputs are unchanged otherwise. */
int exr_viewport_parse(const char *content, float *width, float *height);
struct exr_document {
  const exr_document_view *view;
  exr_status (*load_package)(const exr_document *,const exr_control *,exr_document **,exr_error *);
  char *text, *title,*language; /* Optional publication-level fallback; element lang wins. */
  exr_direction page_progression; /* OPF spine; independent of paragraph direction. */
  size_t size, text_capacity;
  exr_block *blocks;
  size_t count, capacity;
  exr_format format;
  exr_node *nodes;
  size_t node_count, node_capacity, model_bytes;
  size_t *last_children;
  size_t last_capacity;
  exr_chapter *chapters;
  size_t chapter_count, chapter_capacity;
  exr_rendition *renditions; /* NULL unless the EPUB package declares rendition data. */
  size_t rendition_count;     /* Entries, indexed by chapter. */
  int spread_none; /* rendition:spread none. */
  exr_resource *resources;
  size_t resource_count, resource_capacity;
  exr_resource_data *resource_data; /* Copied resources from public construction inputs. */
  int owns_chapter_strings;
  unsigned char *archive;
  size_t archive_size;
  exr_archive_store *shared_archive;
  size_t ncx_resource;
  int has_ncx;
  exr_media_item *media; /* EPUB part media table; strings owned here. */
  size_t media_count, media_capacity;
};
static inline exr_node exr_doc_node(const exr_document *doc,size_t node) {
  return doc->view ? doc->view->node(doc->view->context,node) : doc->nodes[node];
}
static inline const char *exr_doc_span(const exr_document *doc,size_t offset,size_t *available) {
  if(doc->view) return doc->view->text(doc->view->context,offset,available);
  if(offset>doc->size) { *available=0;return NULL; }
  *available=doc->size-offset;return doc->text+offset;
}
static inline unsigned char exr_doc_byte(const exr_document *doc,size_t offset) {
  size_t available;const char *text=exr_doc_span(doc,offset,&available);
  return text && available ? (unsigned char)*text : 0;
}
static inline int exr_doc_next(const exr_document *doc,size_t end,size_t *offset,uint32_t *cp) {
  size_t available,at=0;const char *text;
  if(*offset>=end) return 0;
  text=exr_doc_span(doc,*offset,&available);
  if(!text) return 0;
  if(available>end-*offset) available=end-*offset;
  if(!exr_next(text,available,&at,cp)) return 0;
  *offset+=at;return 1;
}
static inline int exr_doc_copy(const exr_document *doc,size_t offset,size_t size,void *out) {
  size_t done=0;
  while(done<size) {
    size_t available,chunk;const char *text=exr_doc_span(doc,offset+done,&available);
    if(!text || !available) return 0;
    chunk=size-done<available ? size-done : available;
    memcpy((char *)out+done,text,chunk);done+=chunk;
  }
  return 1;
}

typedef exr_status (*exr_xml_position_fn)(void *context, size_t offset, size_t node);
/* Incremental XML input, preserving the same complete DOM/text snapshot.
   The document and error object outlive the parser; free it after success/error. */
typedef struct exr_xml_tree_parser exr_xml_tree_parser;
exr_node_kind exr_xml_element_kind(const char *name);
int exr_projection_boundary(exr_node_kind kind, const char *tag);
int exr_projection_cjk(uint32_t cp);
int exr_projection_space(uint32_t cp);
exr_status exr_xml_tree_begin(exr_document *doc,size_t resource,int in_spine,int linear,
  const char *root_name,exr_xml_position_fn position,void *context,
  exr_xml_tree_parser **out,exr_error *error);
exr_status exr_xml_tree_feed(exr_xml_tree_parser *parser,const void *data,size_t size,int final);
void exr_xml_tree_free(exr_xml_tree_parser *parser);
exr_status exr_fixed_anchor_validate(const exr_fixed_anchor *anchor,exr_error *error);
exr_status exr_anchor_validate(const exr_anchor *anchor, exr_error *error);
exr_status exr_cfi_context(const exr_document *doc,size_t chapter,const exr_cfi_point *point,size_t context,const exr_control *control,char **before,char **after,exr_error *error);
exr_status exr_cfi_assertion_resolve(const exr_document *doc,size_t chapter,const char *before,const char *after,const exr_control *control,exr_cfi_point *point,exr_error *error);
exr_status exr_cfi_create_for_part(const exr_document *index,size_t part,const exr_document *doc,size_t chapter,const exr_cfi_point *point,size_t context,const exr_control *control,char **out,exr_error *error);
exr_status exr_cfi_route(const exr_document *index,const char *cfi,const exr_control *control,size_t *part,char **local,exr_error *error);
exr_status exr_cfi_range_join(const char *start,const char *end,char **out,exr_error *error);
exr_status exr_document_package_tree(const exr_document *doc,const exr_control *control,exr_document **out,exr_error *error);
int exr_add_block(exr_document *doc, const char *text, size_t size, unsigned heading);
char *exr_model_copy(exr_document *doc, const char *text, size_t size);
/* XHTML media elements; each shown one gets an engine placeholder TEXT child. */
int exr_media_element(const char *local_name);
int exr_media_placeholder(const exr_document *doc, size_t node);
/* Placeholder TEXT node of a media element, SIZE_MAX when it has none. */
size_t exr_media_placeholder_of(const exr_document *doc, size_t element);
/* Classifies every media element and appends its placeholder TEXT child; call
   after parsing and before exr_model_finish. */
exr_status exr_media_scan(exr_document *doc, exr_error *error);
const char *exr_html_tag(const exr_document *doc, const exr_node *node);
size_t exr_model_node(exr_document *doc, size_t parent, size_t chapter, exr_node_kind kind,
                      const char *name, const char *text, size_t length);
exr_status exr_xhtml(exr_document *doc, const void *data, size_t size, size_t resource,
                     int in_spine, int linear, exr_error *error);
exr_status exr_xml_tree(exr_document *doc, const void *data, size_t size, size_t resource,
                         int in_spine, int linear, const char *root_name, exr_error *error);
size_t exr_model_html(exr_document *doc, size_t parent, size_t chapter, exr_node_kind kind,
                       const char *tag, const char *text);
int exr_model_attribute(exr_document *doc, size_t node, const char *name, const char *value);
exr_status exr_xml_memory_tree(const void *data, size_t size, const char *root,
                                exr_document **out, exr_error *error);
exr_status exr_model_finish(exr_document *doc, exr_error *error);
void exr_model_free(exr_document *doc);
int exr_canonical_path(const char *path);
exr_status exr_xhtml_positions(exr_document *doc, const void *data, size_t size, size_t resource,
                                 exr_xml_position_fn position, void *context, exr_error *error);

#endif
