/* SPDX-License-Identifier: MIT */
/* Default reading build consumer: only the frozen SDK core component is
   available here, so this file may not reach any optional package. */
#include <exreader.h>
#include <exr/library.h>
#include <stdio.h>
int main(void) {
  const char *version = exr_version();
  const uint32_t abi = exr_abi_version();
  if (!version || !version[0] || abi != 1u) return 1;
  printf("default reading build: version=%s abi=%u\n", version, (unsigned)abi);
  return 0;
}
