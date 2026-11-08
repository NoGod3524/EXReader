/* SPDX-License-Identifier: MIT */
#include <stdio.h>
#include <string.h>
#include "e1_platform.h"
double perf_reference_ms(void);
int main(int argc, char **argv) {
  if (!e1_pin()) return 3;
  if (argc == 2 && !strcmp(argv[1], "--busy")) {
    for (;;) perf_reference_ms();
  }
  /* One declared warmup, then 31 retained observations, no trimming. */
  double warmup = perf_reference_ms();
  printf("{\"warmup_ms\":%.6f,\"reference_ms\":[", warmup);
  for (int i = 0; i < 31; ++i) printf("%s%.6f", i ? "," : "", perf_reference_ms());
  puts("]}");
  return 0;
}
