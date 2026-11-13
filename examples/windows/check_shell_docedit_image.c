/* SPDX-License-Identifier: MIT */
/* Console model acceptance. Link against the SDK; no windows or input events. */
#include <windows.h>
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <string.h>
#include <assert.h>
#include <exr/edit.h>
typedef struct {size_t block,run,byte;} de_pos;
static struct {
  exr_edit_doc *doc;
  size_t caret_block,selected_block;
  de_pos caret,anchor;
  exr_edit_run_props pending_props;
  int dirty,layout_dirty;
} de;
static int refreshes,errors;
static wchar_t *host_wide(const char *text,size_t size) {
  int n=MultiByteToWideChar(CP_UTF8,MB_ERR_INVALID_CHARS,text,(int)size,NULL,0);
  wchar_t *out=n ? malloc(((size_t)n+1)*sizeof(*out)):NULL;
  if(out) {MultiByteToWideChar(CP_UTF8,MB_ERR_INVALID_CHARS,text,(int)size,out,n);out[n]=0;}
  return out;
}
static void set_status(const wchar_t *text) {(void)text;errors++;}
static void de_error(const wchar_t *text,exr_status status,exr_error *error) {
  (void)text;(void)status;(void)error;errors++;
}
static de_pos de_start(size_t block) {de_pos p={block,0,0};return p;}
static de_pos de_caret(void) {return de.caret;}
static void de_set_caret(de_pos p) {de.caret=p;de.caret_block=p.block;}
static void de_set_anchor(de_pos p) {de.anchor=p;}
static de_pos de_normalize(de_pos p) {
  size_t n=exr_edit_block_count(de.doc);if(p.block>=n)p.block=n ? n-1:0;return p;
}
static void de_refresh(int reveal) {assert(reveal);refreshes++;}
#include "shell_docedit_image.inc"

int main(int argc,char **argv) {
  assert(argc==2);
  exr_edit_block paragraphs[2]={{0}};
  paragraphs[0].kind=paragraphs[1].kind=EXR_EDIT_PARAGRAPH;
  assert(exr_edit_doc_create(NULL,0,paragraphs,2,NULL,0,NULL,&de.doc)==EXR_OK);
  de.selected_block=SIZE_MAX;
  const char *formats[]={"png","bmp","gif"};
  for(size_t i=0;i<3;i++) {
    char path[4096];snprintf(path,sizeof(path),"%s/tests/fixtures/images/%s/one.%s",argv[1],formats[i],formats[i]);
    de_set_caret(de_start(0));de_set_anchor(de_caret());
    exr_edit_id first=exr_edit_block_at(de.doc,0)->id,last=exr_edit_block_at(de.doc,1)->id;
    size_t before=exr_edit_block_count(de.doc);int refresh_before=refreshes;
    assert(!de_image_at_caret());assert(de_image_insert(path));
    assert(exr_edit_block_count(de.doc)==before+1 && de.selected_block==1);
    assert(exr_edit_block_at(de.doc,0)->id==first && exr_edit_block_at(de.doc,2)->id==last);
    assert(de_image_at_caret() && de.dirty && de.layout_dirty && refreshes==refresh_before+1);
    exr_edit_id image=exr_edit_block_at(de.doc,1)->id;
    assert(!de_image_insert(path)); /* An image caret is not a paragraph. */
    assert(de_image_delete_selected());assert(exr_edit_block_count(de.doc)==before);
    assert(de.selected_block==SIZE_MAX && !de_image_at_caret());
    assert(!de_image_delete_selected());
    assert(exr_edit_undo(de.doc)==EXR_OK && exr_edit_block_count(de.doc)==before+1);
    assert(exr_edit_block_at(de.doc,1)->id==image);
    assert(exr_edit_undo(de.doc)==EXR_OK && exr_edit_block_count(de.doc)==before);
    assert(exr_edit_redo(de.doc)==EXR_OK && exr_edit_block_count(de.doc)==before+1);
    assert(exr_edit_redo(de.doc)==EXR_OK && exr_edit_block_count(de.doc)==before);
    printf("%s: insert %zu->%zu; delete %zu->%zu; undo delete +1; undo insert -1; redo both PASS\n",
      formats[i],before,before+1,before+1,before);
  }
  de_set_caret(de_start(0));de.selected_block=SIZE_MAX;de.dirty=de.layout_dirty=0;
  size_t before=exr_edit_block_count(de.doc);int refresh_before=refreshes;
  assert(!de_image_insert(NULL) && !de_image_insert("") && !de_image_insert("missing.png"));
  char path[4096];snprintf(path,sizeof(path),"%s/tests/fixtures/images/png/truncated.png",argv[1]);
  assert(!de_image_insert(path));
  de.selected_block=0;assert(!de_image_delete_selected());
  de.selected_block=SIZE_MAX-1;assert(!de_image_delete_selected());
  assert(exr_edit_block_count(de.doc)==before && !de.dirty && !de.layout_dirty && refreshes==refresh_before);
  exr_edit_doc_free(de.doc);de.doc=NULL;
  assert(!de_image_at_caret() && !de_image_insert(path) && !de_image_delete_selected());
  printf("invalid path/image/selection and inactive document: unchanged PASS (errors=%d)\n",errors);
  return 0;
}
