/* SPDX-License-Identifier: MIT */
#include <exr_sideload.h>
int export_c_contract(void) {
  uint64_t bytes=100;exr_error error={0};
  return exr_sideload_export_original(0,0,0,0,&bytes,&error)!=EXR_ARGUMENT||bytes!=0;
}
