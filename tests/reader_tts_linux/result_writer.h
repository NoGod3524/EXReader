/* SPDX-License-Identifier: MIT */
/* Minimal JSON result writer shared by the J19 test binaries. */
#ifndef READER_TTS_RESULT_WRITER_H
#define READER_TTS_RESULT_WRITER_H
#include <stdio.h>
#include <string.h>

static inline void rw_escape(FILE *f, const char *s) {
  const unsigned char *p = (const unsigned char *)(s ? s : "");
  fputc('"', f);
  for (; *p; ++p) {
    if (*p == '"' || *p == '\\') {
      fputc('\\', f);
      fputc((int)*p, f);
    } else if (*p < 0x20) {
      fprintf(f, "\\u%04x", (unsigned)*p);
    } else {
      fputc((int)*p, f);
    }
  }
  fputc('"', f);
}

static inline void rw_begin(FILE *f, const char *binary, const char *phase) {
  fprintf(f, "{\n  \"binary\": ");
  rw_escape(f, binary);
  fprintf(f, ",\n  \"phase\": ");
  rw_escape(f, phase);
  fprintf(f, ",\n  \"cases\": [");
}

static inline void rw_case(FILE *f, int *first, const char *name, int pass, const char *detail) {
  fprintf(f, "%s\n    {\"name\": ", *first ? "" : ",");
  *first = 0;
  rw_escape(f, name);
  fprintf(f, ", \"status\": ");
  rw_escape(f, pass ? "pass" : "fail");
  fprintf(f, ", \"detail\": ");
  rw_escape(f, detail ? detail : "");
  fputc('}', f);
}

static inline void rw_end(FILE *f, int failures) {
  fprintf(f, "\n  ],\n  \"failures\": %d\n}\n", failures);
}
#endif
