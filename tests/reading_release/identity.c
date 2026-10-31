/* SPDX-License-Identifier: MIT */
#include <exr/base.h>
#ifdef EXR_RELEASE_LIBRARY
#include <exr/library.h>
#endif
#include <stdio.h>
#include <string.h>

int main(int argc, char **argv) {
  if (strcmp(EXR_VERSION, exr_version()) || EXR_ABI_VERSION != exr_abi_version()) return 1;
#ifdef EXR_RELEASE_LIBRARY
  exr_library *library = NULL;
  exr_error error = {0};
  if (argc != 2 || exr_library_open(argv[1], &library, &error) != EXR_OK) return 1;
  exr_library_close(library);
  printf("{\"sdk_version\":\"%s\",\"abi\":%u,\"library_header_version\":\"%s\"}\n",
         exr_version(), (unsigned)exr_abi_version(), EXR_LIBRARY_VERSION);
#else
  (void)argc; (void)argv;
  printf("{\"sdk_version\":\"%s\",\"abi\":%u,\"library_header_version\":null}\n",
         exr_version(), (unsigned)exr_abi_version());
#endif
  return 0;
}
