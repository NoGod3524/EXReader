/* SPDX-License-Identifier: MIT */
/* Installed-package consumer for the AcroForm corpus.  It links only the
   exported EXReader::exr_pdf_edit component, includes only the public header and
   repeats read -> edit -> reopen -> verify for every ASCII corpus document, so
   the published checks reproduce from the installed component instead of the
   source tree.  One change per document is exercised; multi-change documents
   are covered by the in-tree driver. */
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
  if (length && fread(data, 1, (size_t)length, file) != (size_t)length) {
    free(data); fclose(file); return NULL;
  }
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

static int split(char *line, char **cells, int limit) {
  int count = 0; char *at = line;
  while (count < limit) {
    char *tab = strchr(at, '\t');
    cells[count++] = at;
    if (!tab) break;
    *tab = 0; at = tab + 1;
  }
  if (count) {
    char *end = cells[count - 1] + strlen(cells[count - 1]);
    if (end > cells[count - 1] && end[-1] == '\n') end[-1] = 0;
  }
  return count;
}

int main(int argc, char **argv) {
  FILE *plan; char line[8192]; char corpus[1024];
  unsigned covered = 0, skipped = 0, failed = 0;
  if (argc < 2) { fprintf(stderr, "usage: %s corpus-dir [report.json]\n", argv[0]); return 2; }
  snprintf(corpus, sizeof(corpus), "%s", argv[1]);
  {
    char path[1200];
    snprintf(path, sizeof(path), "%s/plan.tsv", corpus);
    plan = fopen(path, "rb");
  }
  if (!plan) plan = fopen("plan.tsv", "rb");
  if (!plan) { fprintf(stderr, "cannot open plan.tsv\n"); return 1; }
  while (fgets(line, sizeof(line), plan)) {
    char *cells[8]; int cells_count; char *base;
    char *changes[6]; int change_count;
    unsigned char *input; size_t size = 0;
    if (line[0] != 'P') continue;
    cells_count = split(line, cells, 8);
    if (cells_count < 5) continue;
    if (strcmp(cells[3], "write")) continue;
    base = cells[2];
    if (!fgets(line, sizeof(line), plan)) break;
    if (line[0] != 'C') continue;
    change_count = split(line, changes, 6);
    if (change_count < 4) { failed++; continue; }
    {
      char path[1400];
      size_t field_size = 0, value_size = 0;
      unsigned char *field = unhex(changes[2], &field_size);
      unsigned char *raw = unhex(changes[3], &value_size);
      exr_pdf_form_change change;
      const char *value;
      void *output = NULL; size_t out_size = 0;
      exr_pdf_form_field *fields = NULL; size_t field_total = 0;
      snprintf(path, sizeof(path), "%s/%s", corpus, base);
      input = read_file(path, &size);
      if (!input) {
        fprintf(stderr, "%s: cannot read %s\n", base, path);
        free(field); free(raw); failed++;
        continue;
      }
      if (!field || !raw) {
        fprintf(stderr, "%s: change line is not hexadecimal\n", base);
        free(field); free(raw); free(input); failed++;
        continue;
      }
      if (!ascii_only(raw, value_size)) {
        skipped++;
        free(field); free(raw); free(input);
        continue;
      }
      value = (const char *)raw;
      change.name = (const char *)field;
      change.values = &value;
      change.value_count = 1;
      if (exr_pdf_form_write(input, size, &change, 1, NULL, &output, &out_size, &error) != EXR_OK) {
        fprintf(stderr, "%s: installed write failed: %s\n", base, error.message);
        failed++;
      } else if (!output || out_size <= size || memcmp(output, input, size) != 0) {
        fprintf(stderr, "%s: installed write did not preserve the input prefix\n", base);
        failed++;
      } else if (exr_pdf_form_read(output, out_size, NULL, &fields, &field_total, &error) != EXR_OK) {
        fprintf(stderr, "%s: installed reopen failed: %s\n", base, error.message);
        failed++;
      } else {
        size_t i; int found = 0;
        for (i = 0; i < field_total; i++)
          if (!strcmp(fields[i].name, change.name) && fields[i].value_count == 1 &&
              !strcmp(fields[i].values[0], value)) found = 1;
        if (!found) { fprintf(stderr, "%s: reopened value differs\n", base); failed++; }
        else covered++;
        exr_pdf_form_free(fields, field_total);
      }
      exr_free(output); free(field); free(raw); free(input);
    }
  }
  fclose(plan);
  if (argc > 2) {
    FILE *report = fopen(argv[2], "wb");
    if (report) {
      fprintf(report, "{\n  \"schema\": \"exreader-acroform-installed-consumer/1\",\n");
      fprintf(report, "  \"covered\": %u,\n  \"skipped\": %u,\n  \"failed\": %u\n}\n",
              covered, skipped, failed);
      fclose(report);
    }
  }
  printf("installed AcroForm consumer: covered=%u skipped=%u failed=%u\n", covered, skipped, failed);
  return failed == 0 && covered >= 20 ? 0 : 1;
}
