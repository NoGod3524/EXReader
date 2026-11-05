// SPDX-License-Identifier: MIT
#include <exr_desktop_display.h>
#include <cstdio>
#include <type_traits>
static_assert(std::is_standard_layout<exr_display_options>::value, "C ABI layout");
static_assert(std::is_standard_layout<exr_display_observation>::value, "C ABI layout");
int main() {
  exr_display_lease *lease=nullptr;
  if(exr_display_create(nullptr,&lease)!=EXR_DISPLAY_ARGUMENT || lease) return 1;
  if(exr_display_close(lease)!=EXR_DISPLAY_OK) return 2;
  std::printf("{\"case\":\"installed_cpp_abi\",\"result\":\"PASS\",\"module\":\"%s\"}\n",exr_display_build_id());
  return 0;
}
