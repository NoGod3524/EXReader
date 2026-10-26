// SPDX-License-Identifier: MIT
#include <cstdio>
#ifndef FAMILY_VERSION
#define FAMILY_VERSION "unknown"
#endif
int main() {
  std::printf("FOUNDATION-CONSUMER %s\n", FAMILY_VERSION);
  return 0;
}
