/* SPDX-License-Identifier: MIT */
/* Installed consumer: exercises the real platform store through the installed
   package only. Usage: credentials-consumer <phase> [--io-dir DIR]
   Input (namespaces, account IDs, hex secrets) is read from stdin, or with
   --io-dir from DIR/credentials-input.txt, which is removed after reading;
   results then also go to DIR/credentials-result.txt (an S4U scheduled task or
   an iOS simulator app has no stdin). Output never contains secrets. */
#include "suite.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define INPUT_MAX (256 * 1024)

static void emit(void *context, const char *line) {
  printf("%s\n", line);
  fflush(stdout);
  if (context) {
    fprintf((FILE *)context, "%s\n", line);
    fflush((FILE *)context);
  }
}

static void read_all(FILE *file, char *buffer) {
  size_t n = 0, got;
  while (n < INPUT_MAX && (got = fread(buffer + n, 1, INPUT_MAX - n, file)) > 0) n += got;
  buffer[n] = 0;
}

int main(int argc, char **argv) {
  char *text = (char *)calloc(1, INPUT_MAX + 1);
  suite_input *input = (suite_input *)calloc(1, sizeof *input);
  FILE *result = NULL;
  int failed;
  if ((argc != 2 && argc != 4) || !text || !input || (argc == 4 && strcmp(argv[2], "--io-dir"))) {
    fprintf(stderr, "usage: credentials-consumer <suite|reopen|seed|unavailable|cleanup> [--io-dir DIR]\n");
    return 2;
  }
  if (argc == 4) {
    char path[2048];
    FILE *in;
    snprintf(path, sizeof path, "%s/credentials-result.txt", argv[3]);
    result = fopen(path, "w");
    snprintf(path, sizeof path, "%s/credentials-input.txt", argv[3]);
    in = fopen(path, "rb");
    if (!in || !result) {
      emit(result, "check harness-input fail unreadable");
      return 2;
    }
    read_all(in, text);
    fclose(in);
    remove(path);
  } else {
    read_all(stdin, text);
  }
  if (suite_parse(text, input)) {
    emit(result, "check harness-input fail malformed");
    failed = 1;
  } else {
    failed = suite_run(argv[1], input, emit, result);
    if (failed < 0) emit(result, "check harness-phase fail unknown");
  }
  exr_credentials_wipe(text, INPUT_MAX + 1);
  suite_wipe(input);
  free(text);
  free(input);
  if (result) fclose(result);
  return failed == 0 ? 0 : 1;
}
