/* SPDX-License-Identifier: MIT */
/* Fail each allocation of the text command and require atomic rollback. */
#include <exr/edit.h>
#include <stdlib.h>
#include <stdio.h>
#include <string.h>
static size_t budget=SIZE_MAX,live=0;
static void *checked_calloc(size_t n,size_t size) {
  void *p;
  if (budget!=SIZE_MAX) { if (!budget) return NULL; budget--; }
  p=calloc(n,size); if (p) live++; return p;
}
static void checked_free(void *p) { if (p) { live--; free(p); } }
#define calloc checked_calloc
#define free checked_free
#include "../../../../src/docx_edit.c"
#undef calloc
#undef free
#define CHECK(x) do { if (!(x)) { fprintf(stderr,"text allocation line %d: %s\n",__LINE__,#x); exit(1); } } while (0)
int main(void) {
  unsigned transaction; size_t fail,covered=0;
  for (transaction=0;transaction<2;transaction++) for (fail=0;fail<128;fail++) {
    exr_edit_doc *doc=NULL; exr_edit_tx *tx=NULL; exr_edit_block block={0}; exr_edit_run run={0};
    exr_status status; const exr_edit_block *result;
    run.id=10; run.text="original"; run.text_size=8;
    run.props.present=EXR_EDIT_BOLD; run.props.bold=1;
    block.id=20; block.runs=&run; block.run_count=1;
    CHECK(exr_edit_doc_create(NULL,0,&block,1,NULL,0,NULL,&doc)==EXR_OK);
    if (transaction) { tx=exr_edit_begin(doc); CHECK(tx); }
    budget=fail;
    status=exr_edit_set_run_text(doc,20,0,"replacement",11);
    budget=SIZE_MAX;
    if (transaction) CHECK(exr_edit_commit(tx)==status);
    result=exr_edit_block_at(doc,0);
    CHECK(result->id==20 && result->runs[0].id==10 && result->runs[0].props.bold==1);
    if (status) {
      CHECK(status==EXR_MEMORY && !strcmp(result->runs[0].text,"original"));
      CHECK(exr_edit_undo(doc)==EXR_ARGUMENT); covered++;
    } else {
      CHECK(!strcmp(result->runs[0].text,"replacement"));
      CHECK(exr_edit_undo(doc)==EXR_OK && !strcmp(exr_edit_block_at(doc,0)->runs[0].text,"original"));
    }
    exr_edit_doc_free(doc); CHECK(!live);
    if (!status) break;
  }
  CHECK(covered>=10);
  printf("text allocation rollback: %zu failure points, zero live allocations\n",covered);
  return 0;
}
