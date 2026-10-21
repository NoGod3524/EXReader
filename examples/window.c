/* SPDX-License-Identifier: MIT */
#include "exr/core.h"
#include <stdio.h>
#include <string.h>
static exr_status count_text(void *context,const char *text,size_t size,exr_error *error) {
  size_t *bytes=context;(void)text;(void)error;*bytes+=size;return EXR_OK;
}
int main(int argc,char **argv) {
  exr_publication *publication=NULL;exr_font *font=NULL;exr_pager *pager=NULL;
  exr_layout *page=NULL;exr_error error={0};exr_status status=EXR_ARGUMENT;
  exr_chapter_options options=exr_chapter_options_defaults();
  exr_chapter_stats stats={0};exr_anchor anchor={0};exr_anchor_match match;
  exr_cfi_point point={0},resolved;char *cfi=NULL;size_t count=0,bytes=0;
  if(argc!=3) { fprintf(stderr,"Usage: %s font.ttf book.epub\n",argv[0]);return 2; }
  options.window_bytes=512;
  status=exr_font_open(argv[1],&font,&error);
  if(status==EXR_OK) status=exr_publication_open(argv[2],&publication,&error);
  if(status==EXR_OK) status=exr_publication_pager_create(publication,0,font,NULL,&options,&pager,&error);
  exr_publication_free(publication); /* Pager retains the immutable source. */
  if(status==EXR_OK) status=exr_pager_next(pager,&page,&error);
  if(status==EXR_OK && page) {
    const exr_glyph *glyphs=exr_layout_glyphs(page,&count);
    if(count) {
      point=(exr_cfi_point){glyphs[0].node,0,0};
      status=exr_pager_cfi_create(pager,&point,4,NULL,&cfi,&error);
      if(status==EXR_OK) status=exr_pager_cfi_resolve(pager,cfi,NULL,&resolved,&error);
      if(status==EXR_OK && (resolved.node!=point.node || resolved.offset!=point.offset)) status=EXR_FORMAT;
    }
  } else if(status==EXR_OK) status=EXR_FORMAT;
  if(status==EXR_OK) status=exr_pager_anchor_create(pager,0,0,NULL,&anchor,&error);
  if(status==EXR_OK) status=exr_pager_anchor_resolve(pager,&anchor,NULL,&match,&error);
  if(status==EXR_OK && (match.state!=EXR_ANCHOR_FOUND || match.start!=0 || match.end!=0)) status=EXR_FORMAT;
  if(status==EXR_OK) {
    stats=exr_pager_chapter_statistics(pager);
    status=exr_pager_read_text(pager,0,stats.projection_bytes,count_text,&bytes,NULL,&error);
    if(status==EXR_OK && bytes!=stats.projection_bytes) status=EXR_FORMAT;
  }
  if(status==EXR_OK) printf("Bounded chapter: %zu UTF-8 bytes, %zu index bytes\n",bytes,stats.index_bytes);
  else fprintf(stderr,"Bounded chapter status %d: %s\n",status,error.message);
  exr_anchor_free(&anchor);exr_free(cfi);exr_layout_free(page);exr_pager_free(pager);exr_font_free(font);
  return status==EXR_OK ? 0 : 1;
}
