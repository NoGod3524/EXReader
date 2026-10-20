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
} exr_archive_store;
struct exr_document {
  exr_status (*load_package)(const exr_document *,const exr_control *,exr_document **,exr_error *);
  char *text, *title,*language; /* Optional publication-level fallback; element lang wins. */
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
  exr_resource *resources;
  size_t resource_count, resource_capacity;
  exr_resource_data *resource_data; /* Copied resources from public construction inputs. */
  int owns_chapter_strings;
  unsigned char *archive;
  size_t archive_size;
  exr_archive_store *shared_archive;
  size_t ncx_resource;
  int has_ncx;
};

typedef exr_status (*exr_xml_position_fn)(void *context, size_t offset, size_t node);
/* Incremental XML input, preserving the same complete DOM/text snapshot.
   The document and error object outlive the parser; free it after success/error. */
typedef struct exr_xml_tree_parser exr_xml_tree_parser;
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
exr_status exr_document_package_tree(const exr_document *doc,const exr_control *control,exr_document **out,exr_error *error);
int exr_add_block(exr_document *doc, const char *text, size_t size, unsigned heading);
char *exr_model_copy(exr_document *doc, const char *text, size_t size);
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
