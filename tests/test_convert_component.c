/* SPDX-License-Identifier: MIT */
/* Installed-SDK conversion consumer: text export, controlled export, EPUB and
   HTML-bundle preserve export. Built/run independently from the engine tree. */
#include "exreader.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static exr_error error;
#define CHECK(x) do { checks++; if (!(x)) { fprintf(stderr, "line %d: %s (%d: %s)\n", __LINE__, #x, (int)error.code, error.message); return 1; } } while (0)
#define OK(x) CHECK((x) == EXR_OK)

static int cancelled(void *context) { (void)context; return 1; }

int main(int argc, char **argv) {
  exr_document *source = NULL, *reopened = NULL;
  void *data = NULL, *bundle = NULL, *controlled = (void *)(uintptr_t)1;
  char *entry = NULL, path[4096];
  size_t size = 0, bundle_size = 0, controlled_size = 7;
  const char *text;
  unsigned checks = 0;
  exr_control control;
  if (argc != 3) { fprintf(stderr, "usage: %s FIXTURES OUTDIR\n", argv[0]); return 2; }
  snprintf(path, sizeof(path), "%s/layout.epub", argv[1]);
  OK(exr_document_open(path, &source, &error));
  text = exr_document_text(source, NULL);
  CHECK(text && *text);
  OK(exr_document_export(source, EXR_TXT, &data, &size, &error));
  OK(exr_document_open_memory(EXR_TXT, data, size, &reopened, &error));
  CHECK(!strcmp(text, exr_document_text(reopened, NULL)));
  exr_document_free(reopened); reopened = NULL; exr_free(data); data = NULL;
  OK(exr_document_export(source, EXR_EPUB, &data, &size, &error));
  OK(exr_document_open_memory(EXR_EPUB, data, size, &reopened, &error));
  exr_document_free(reopened); reopened = NULL; exr_free(data); data = NULL;
  OK(exr_document_export_epub(source, NULL, &data, &size, &error));
  OK(exr_document_open_memory(EXR_EPUB, data, size, &reopened, &error));
  exr_document_free(reopened); reopened = NULL; exr_free(data); data = NULL;
  OK(exr_document_export_html_bundle(source, NULL, &bundle, &bundle_size, &entry, &error));
  CHECK(bundle && bundle_size && entry && *entry);
  snprintf(path, sizeof(path), "%s/converted-bundle.zip", argv[2]);
  {
    FILE *file = fopen(path, "wb");
    CHECK(file != NULL);
    CHECK(fwrite(bundle, 1, bundle_size, file) == bundle_size);
    fclose(file);
  }
  exr_free(bundle); exr_free(entry); bundle = NULL; entry = NULL;
  memset(&control, 0, sizeof(control));
  control.cancelled = cancelled;
  CHECK(exr_document_export_control(source, EXR_EPUB, &control, &controlled, &controlled_size,
                                    &error) == EXR_CANCELLED);
  CHECK(!controlled && !controlled_size);
  exr_document_free(source);
  printf("installed conversion consumer: %u checks passed\n", checks);
  return 0;
}
