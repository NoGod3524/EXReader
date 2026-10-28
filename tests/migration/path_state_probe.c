/* SPDX-License-Identifier: MIT */
#include "lm.h"
#include <stdio.h>
int main(int argc, char **argv) {
  if (argc != 2) return 2;
  printf("%d\n", lm_path_state(argv[1]));
  return 0;
}
