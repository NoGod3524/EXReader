/* SPDX-License-Identifier: MIT */
#include <exr_desktop_display.h>
#include <stdio.h>
#include <string.h>
int main(void) {
  exr_display_lease *lease=(exr_display_lease *)(uintptr_t)1;
  if(exr_display_create(NULL,&lease)!=EXR_DISPLAY_ARGUMENT || lease) return 1;
  if(exr_display_close(NULL)!=EXR_DISPLAY_OK) return 2;
  if(strcmp(exr_display_status_name(EXR_DISPLAY_UNAVAILABLE),"UNAVAILABLE")) return 3;
  printf("{\"case\":\"installed_c_abi\",\"result\":\"PASS\",\"module\":\"%s\"}\n",exr_display_build_id());
  return 0;
}
