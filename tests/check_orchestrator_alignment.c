/* SPDX-License-Identifier: MIT */
/* Standalone: compile with /DEXR_STATIC /Iinclude; optionally define
   EXR_EDIT_MODEL_SOURCE to a pinned model's absolute source path. */
#include <stdio.h>
#include <stdint.h>
#ifndef EXR_EDIT_MODEL_SOURCE
#define EXR_EDIT_MODEL_SOURCE "../src/docx_edit.c"
#endif
#include EXR_EDIT_MODEL_SOURCE
#ifdef _MSC_VER
#define ALIGNOF(T) __alignof(T)
#else
#define ALIGNOF(T) _Alignof(T)
#endif
#define FIT(T) _Static_assert(ALIGNOF(T) <= ALIGNOF(edit_allocation), #T " exceeds allocation alignment")
FIT(exr_edit_block);
FIT(exr_edit_run);
FIT(exr_edit_section);
FIT(exr_edit_part);
FIT(edit_block);
FIT(edit_change);
FIT(exr_edit_tx);
FIT(exr_edit_doc);
#define SHOW(T) printf("%s sizeof=%zu alignof=%zu\n", #T, sizeof(T), (size_t)ALIGNOF(T))
int main(void) {
  size_t i, failures=0, header_failures=0;
  exr_edit_doc doc={0};
  SHOW(exr_edit_block); SHOW(exr_edit_run); SHOW(exr_edit_section);
  SHOW(exr_edit_part); SHOW(edit_allocation); SHOW(long double);
#ifndef _MSC_VER
  SHOW(max_align_t);
#endif
  for (i=1;i<=4096;i++) {
    void *p=allocate(&doc,i);
    if (!p) return 2;
    if ((uintptr_t)p % ALIGNOF(exr_edit_block) ||
        (uintptr_t)p % ALIGNOF(exr_edit_run) ||
        (uintptr_t)p % ALIGNOF(exr_edit_section)) failures++;
    if ((uintptr_t)((edit_allocation *)p-1) % ALIGNOF(edit_allocation)) header_failures++;
    release(&doc,p);
  }
  printf("4096 allocations: model misalignments=%zu, header misalignments=%zu, retained=%zu\n",failures,header_failures,doc.bytes);
  return failures || header_failures || doc.bytes ? 1 : 0;
}
