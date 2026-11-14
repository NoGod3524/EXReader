/* SPDX-License-Identifier: MIT
 * Reuse the all-page product probe, adding only numeric crash context.
 * No book text, raster bytes or engine error strings are recorded here.
 */
#include "exreader.h"
#include <stdio.h>
static size_t audit_part, audit_page, audit_global_page;
static void context(const char *stage, size_t page) {
  fprintf(stderr,"AUDIT_CONTEXT part=%zu page=%zu completed_renders=%zu stage=%s\n",audit_part,page,audit_global_page,stage);
  fflush(stderr);
}
static exr_status audit_font(const char *p,exr_font **f,exr_error *e) {
  context("font",0);return exr_font_open(p,f,e);
}
static exr_status audit_open(const char *p,exr_publication **d,exr_error *e) {
  context("open_publication",0);return exr_publication_open(p,d,e);
}
static exr_status audit_document(const char *p,exr_document **d,exr_error *e) {
  context("open_document",0);return exr_document_open(p,d,e);
}
static exr_status audit_pager(const exr_document *d,exr_font *f,const exr_layout_config *c,exr_pager **p,exr_error *e) {
  context("create_pager",0);return exr_pager_create(d,f,c,p,e);
}
static exr_status audit_load(exr_publication *p,size_t i,exr_document **d,exr_error *e) {
  audit_part=i;audit_page=0;context("load",0);
  return exr_publication_load(p,i,d,e);
}
static exr_status audit_next(exr_pager *p,exr_layout **l,exr_error *e) {
  context("paginate",audit_page);
  exr_status s=exr_pager_next(p,l,e);
  if(s==EXR_OK && *l) audit_page++;
  return s;
}
static exr_status audit_render(const exr_layout *l,exr_font *f,size_t flags,exr_bitmap *b,exr_error *e) {
  context("render",audit_page ? audit_page-1 : 0);
  exr_status s=exr_render_page_color(l,f,flags,b,e);
  if(s==EXR_OK) {
    fprintf(stderr,"AUDIT_RENDERED mode=%d\n",(int)exr_layout_writing_mode(l));
    audit_global_page++;
  }
  return s;
}
static exr_status audit_fixed(exr_fixed_document *d,size_t i,double s,const exr_fixed_render_options *c,exr_bitmap *b,exr_error *e) {
  context("fixed_render",i);
  exr_status result=exr_fixed_render(d,i,s,c,b,e);
  if(result==EXR_OK) { fprintf(stderr,"AUDIT_FIXED_RENDERED\n");audit_global_page++; }
  return result;
}
static exr_status audit_fixed_open(const char *p,const exr_fixed_open_options *o,exr_fixed_document **d,exr_error *e) {
  context("fixed_open",0);return exr_fixed_open(p,o,d,e);
}
static exr_status audit_fixed_text(exr_fixed_document *d,size_t i,const exr_control *c,exr_fixed_text **t,exr_error *e) {
  context("fixed_text",i);return exr_fixed_load_text(d,i,c,t,e);
}
#define exr_publication_open audit_open
#define exr_font_open audit_font
#define exr_document_open audit_document
#define exr_pager_create audit_pager
#define exr_publication_load audit_load
#define exr_pager_next audit_next
#define exr_render_page_color audit_render
#define exr_fixed_render audit_fixed
#define exr_fixed_open audit_fixed_open
#define exr_fixed_load_text audit_fixed_text
#include "../check_document.c"
