/* SPDX-License-Identifier: MIT */
#ifndef EXR_DOCX_EDIT_INTERNAL_H
#define EXR_DOCX_EDIT_INTERNAL_H
#include "formats_internal.h"
#include "docx_edit_model_internal.h"
#include <expat.h>
#include <miniz.h>
#define W "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
#define WS "http://purl.oclc.org/ooxml/wordprocessingml/main"
#define R "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
#define RS "http://purl.oclc.org/ooxml/officeDocument/relationships"
#define NONE SIZE_MAX
typedef struct { size_t start,open,close,end; } xml_span;
typedef struct {
  exr_document *tree;
  const char *bytes; size_t size,root,body;
  xml_span *spans;
  XML_Parser parser;
  size_t cursor,depth,stack[256];
  exr_status status;
} source_xml;
typedef struct { const char *key,*value; } attr_edit;
/* Cell edits are separate from the imported vertical-merge markers. */
enum { CELL_REPLACED=1u,CELL_VMERGE_START=2u,CELL_VMERGE_CONTINUE=4u,CELL_PATCHED=8u };
int exr_edit_xml_word(const exr_node *n,const char *tag);
const char *exr_edit_xml_attribute(const exr_node *n,const char *space,const char *strict,const char *key);
const char *exr_edit_xml_wa(const exr_node *n,const char *key);
const char *exr_edit_xml_ns(const source_xml *x);
size_t exr_edit_xml_child(const source_xml *x,size_t parent,const char *tag);
int exr_edit_xml_integer(const char *s,int32_t *out);
exr_status exr_edit_xml_parse(source_xml *x,const void *data,size_t size,const char *root,exr_error *e);
void exr_edit_xml_free(source_xml *x);
int exr_edit_xml_raw(exr_buffer *b,const source_xml *x,size_t n);
size_t exr_edit_xml_locate(const source_xml *x,const void *data,size_t size,const char *tag,size_t parent);
void exr_edit_xml_para_props(const source_xml *x,size_t pr,exr_edit_para_props *p);
exr_status exr_edit_xml_decode_runs(const source_xml *x,size_t p,exr_edit_run **out,size_t *count);
int exr_edit_xml_paragraph(exr_buffer *b,const source_xml *x,const exr_edit_block *p,size_t section,const exr_buffer *section_data);
int exr_edit_xml_start(exr_buffer *b,const source_xml *x,size_t n,const char *tag);
int exr_edit_xml_end(exr_buffer *b,const source_xml *x,size_t n,const char *tag);
int exr_edit_xml_attrs(exr_buffer *b,const source_xml *x,size_t n,const char *tag,const attr_edit *edits,size_t count);
const exr_edit_part *exr_edit_part_named(const exr_edit_part *p,size_t n,const char *name);
exr_status exr_edit_main_part(const exr_edit_part *parts,size_t n,char name[2048],exr_error *e);
exr_status exr_edit_table_decode(const source_xml *x,size_t n,exr_edit_table **out);
void exr_edit_table_decode_free(exr_edit_table *t);
int exr_edit_table_write(exr_buffer *b,const source_xml *x,const exr_edit_block *block);
/* Names and IDs are selected once per write and shared by drawing/OPC output. */
typedef struct {
  const exr_edit_block *block;
  char part[2048],target[128],rid[128];
  uint32_t drawing_id;
} edit_image_output;
exr_status exr_edit_images_prepare(const exr_edit_doc *d,const char *main,const source_xml *x,
  edit_image_output **out,size_t *count);
int exr_edit_image_write(exr_buffer *b,const source_xml *x,const edit_image_output *im);
exr_status exr_edit_images_package(mz_zip_archive *zip,const exr_edit_part *parts,size_t count,
  const char *main,const exr_buffer *xml,const edit_image_output *images,size_t image_count,exr_error *e);
#endif
