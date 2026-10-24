/* SPDX-License-Identifier: MIT */
/* Installed C consumer: drives every phase of the acceptance suite against the
   real Windows SAPI backend. Usage:
       tts-consumer <phase> --wav-dir DIR
   The WAV directory must already exist; phase results are printed on stdout. */
#include "suite.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

int main(int argc, char **argv) {
  suite *state;
  int failed;
  if (argc != 4 || strcmp(argv[2], "--wav-dir") != 0) {
    fprintf(stderr, "usage: tts-consumer <phase> --wav-dir DIR\n");
    return 2;
  }
  state = suite_create(argv[3]);
  if (!state) {
    printf("check harness.setup fail allocation\n");
    printf("phase %s 0 1\n", argv[1]);
    return 1;
  }
  failed = suite_run(state, argv[1]);
  suite_destroy(state);
  return failed == 0 ? 0 : 1;
}
