/* SPDX-License-Identifier: MIT */
/* Installed-package consumer for the AcroForm corpus.  It links only the
   exported EXReader::exr_pdf_edit component, uses the public header and no
   internal symbol, and repeats the read -> edit -> reopen -> verify path for
   every ASCII corpus entry.  This proves the published checks reproduce from
   the installed component, not only inside the source tree. */
#include "exr/pdf_edit.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static exr_error error;

static unsigned char *read_file(const char *path, size_t *size) {
  FILE *file = fopen(path, "rb"); unsigned char *data; long length;
  *size = 0;
  if (!file) return NULL;
  if (fseek(file, 0, SEEK_END) != 0) { fclose(file); return NULL; }
  length = ftell(file);
  if (length < 0 || fseek(file, 0, SEEK_SET) != 0) { fclose(file); return NULL; }
  data = malloc((size_t)length + 1);
  if (!data) { fclose(file); return NULL; }
  if (length && fread(data, 1, (size_t)length, file) != (size_t)length) { free(data); fclose(file); return NULL; }
  data[length] = 0; *size = (size_t)length; fclose(file); return data;
}

static unsigned char *unhex(const char *text, size_t *size) {
  size_t length = strlen(text), i; unsigned char *data;
  if (length % 2) return NULL;
  data = malloc(length / 2 + 1);
  if (!data) return NULL;
  for (i = 0; i < length / 2; i++) {
    unsigned value = 0, j;
    for (j = 0; j < 2; j++) {
      char c = text[i * 2 + j]; unsigned digit;
      if (c >= '0' && c <= '9') digit = (unsigned)(c - '0');
      else if (c >= 'a' && c <= 'f') digit = (unsigned)(c - 'a' + 10);
      else if (c >= 'A' && c <= 'F') digit = (unsigned)(c - 'A' + 10);
      else { free(data); return NULL; }
      value = value * 16 + digit;
    }
    data[i] = (unsigned char)value;
  }
  data[length / 2] = 0; *size = length / 2; return data;
}

static int ascii_only(const unsigned char *data, size_t size) {
  size_t i;
  for (i = 0; i < size; i++) if (data[i] >= 0x80 || data[i] < 0x20) return 0;
  return 1;
}

int main(int argc, char **argv) {
  FILE *plan; char line[8192]; unsigned covered = 0, skipped = 0, failed = 0;
  char corpus[1024];
  if (argc < 2) { fprintf(stderr, "usage: %s corpus-dir [report.json]\n", argv[0]); return 2; }
  snprintf(corpus, sizeof(corpus), "%s", argv[1]);
  plan = fopen("plan.tsv", "rb");
  if (!plan) {
    char path[1200];
    snprintf(path, sizeof(path), "%s/plan.tsv", corpus);
    plan = fopen(path, "rb");
  }
  if (!plan) { fprintf(stderr, "cannot open plan.tsv\n"); return 1; }
  while (fgets(line, sizeof(line), plan)) {
    char *cells[8]; unsigned count = 0; char *at = line; size_t size = 0, out_size = 0, value_size = 0;
    unsigned char *input; void *output = NULL; exr_pdf_form_field *fields = NULL; size_t field_count = 0;
    exr_pdf_form_change change; const char *value;
    int ascii = 1;
    if (line[0] != 'P') continue;
    while (count < 8) {
      char *tab = strchr(at, '\t');
      cells[count++] = at;
      if (!tab) break;
      *tab = 0; at = tab + 1;
    }
    if (count < 5) continue;
    if (strcmp(cells[3], "write")) continue;
    {
      char path[1400];
      size_t n = strlen(cells[2]);
      if (n && cells[2][n - 1] == '\n') cells[2][n - 1] = 0;
      snprintf(path, sizeof(path), "%s/%s", corpus, cells[2]);
      input = read_file(path, &size);
      if (!input) { fprintf(stderr, "cannot read %s\n", path); failed++; continue; }
    }
    /* Pull the frozen change for this document from the following line. */
    if (!fgets(line, sizeof(line), plan)) { free(input); continue; }
    {
      char *hash = strchr(line, '\t'), *field_hex, *value_hex, *end;
      if (!hash) { free(input); continue; }
      field_hex = hash + 1;
      end = strchr(field_hex, '\t');
      if (!end) { free(input); continue; }
      *end = 0; value_hex = end + 1;
      end = strchr(value_hex, '\n');
      if (end) *end = 0;
      {
        size_t field_size = 0;
        unsigned char *field = unhex(field_hex, &field_size);
        unsigned char *raw = unhex(value_hex, &value_size);
        if (!field || !raw) { free(field); free(raw); free(input); failed++; continue; }
        if (!ascii_only(raw, value_size)) ascii = 0;
        value = (const char *)raw;
        change.name = (const char *)field;
        change.values = &value;
        change.value_count = 1;
        if (!ascii) {
          skipped++;
          free(field); free(raw); free(input);
          continue;
        }
        if (exr_pdf_form_write(input, size, &change, 1, NULL, &output, &out_size, &error) != EXR_OK ||
            !output || out_size <= size || memcmp(output, input, size) != 0) {
          fprintf(stderr, "%s: installed write failed: %s\n", cells[2], error.message);
          failed++;
        } else if (exr_pdf_form_read(output, out_size, NULL, &fields, &field_count, &error) != EXR_OK) {
          fprintf(stderr, "%s: installed reopen failed\n", cells[2]);
          failed++;
        } else {
          size_t i; int found = 0;
          for (i = 0; i < field_count; i++)
            if (!strcmp(fields[i].name, change.name) && fields[i].value_count == 1 &&
                !strcmp(fields[i].values[0], value)) found = 1;
          if (!found) { fprintf(stderr, "%s: reopened value differs\n", cells[2]); failed++; }
          else covered++;
          exr_pdf_form_free(fields, field_count);
        }
        free(field); free(raw); exr_free(output); free(input);
      }
    }
  }
  fclose(plan);
  if (argv[2]) {
    FILE *report = fopen(argv[2], "wb");
    if (report) {
      fprintf(report, "{\n \"schema\": \"exreader-acroform-installed-consumer/1\",\n");
      fprintf(report, " \"covered\": %u,\n \"skipped\": %u,\n \"failed\": %u\n}\n", covered, skipped, failed);
      fclose(report);
    }
  }
  printf("installed AcroForm consumer: covered=%u skipped=%u failed=%u\n", covered, skipped, failed);
  return failed == 0 && covered >= 20 ? 0 : 1;
}
