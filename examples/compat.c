/* SPDX-License-Identifier: MIT */
#include "exreader.h"
#include <stdio.h>
#include <string.h>
_Static_assert(EXR_EXPECTED_ABI==EXR_ABI_VERSION,"CMake package and header ABI differ");
int main(void) {
  if(exr_abi_version()!=EXR_ABI_VERSION || strcmp(exr_version(),EXR_VERSION)) {
    fprintf(stderr,"SDK header/runtime mismatch\n"); return 1;
  }
  printf("EXReader %s ABI %u\n",exr_version(),(unsigned)exr_abi_version()); return 0;
}
