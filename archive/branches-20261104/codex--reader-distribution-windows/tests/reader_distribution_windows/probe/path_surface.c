/* SPDX-License-Identifier: MIT */
/* Control probe for the __FILE__ and COFF debug-path surfaces.
 * It is compiled by the workflow twice from the same bytes: once with an
 * absolute source spelling and once with a bare file name. The emitted JSON is
 * the run-time half of the proof; the object file is the compile-time half. */
#define _CRT_SECURE_NO_WARNINGS
#include <stdio.h>
#include <string.h>

static const char *surface_source_path(void) { return __FILE__; }

static void escape(const char *value, char *output, size_t capacity) {
  size_t used = 0;
  for (const char *cursor = value; *cursor && used + 3 < capacity; cursor++) {
    unsigned char byte = (unsigned char)*cursor;
    if (byte == '\\' || byte == '"') {
      output[used++] = '\\';
      output[used++] = (char)byte;
    } else if (byte < 0x20) {
      used += (size_t)snprintf(output + used, capacity - used, "\\u%04x", byte);
    } else {
      output[used++] = (char)byte;
    }
  }
  output[used] = '\0';
}

int main(int argc, char **argv) {
  char escaped[4096];
  FILE *stream = NULL;
  const char *path = surface_source_path();
  if (argc != 2) {
    fprintf(stderr, "usage: path-surface <output.json>\n");
    return 2;
  }
  escape(path, escaped, sizeof(escaped));
  stream = fopen(argv[1], "wb");
  if (!stream) {
    return 3;
  }
  fprintf(stream,
          "{\"schema\":\"reader-distribution-windows-path-surface-v1\","
          "\"file_macro\":\"%s\",\"file_macro_bytes\":%u}\n",
          escaped, (unsigned)strlen(path));
  fclose(stream);
  return 0;
}
