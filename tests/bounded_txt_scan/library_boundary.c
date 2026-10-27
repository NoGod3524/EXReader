#include "exreader.h"
#include <stdio.h>
#include <string.h>

/* This is a boundary diagnostic, not a host integration test. */
typedef struct { const char *data; size_t size; } input;
static size_t read_at(void *context, uint64_t offset, void *buffer, size_t size) {
  input *in = (input *)context;
  if (offset > in->size) return 0;
  if (size > in->size - (size_t)offset) size = in->size - (size_t)offset;
  memcpy(buffer, in->data + (size_t)offset, size);
  return size;
}
int main(void) {
  static const char text[] = "first paragraph\nsecond paragraph\n";
  input in = {text, sizeof(text) - 1};
  exr_source source = {0}, stored = {0};
  exr_library *library = NULL; exr_document *doc = NULL;
  exr_error error = {0}; int64_t id = -1, duplicate = -1;
  int created = -1; char bytes[sizeof(text)] = {0};
  source.size = in.size; source.context = &in; source.read_at = read_at;
  if (exr_library_open(":memory:", &library, &error) != EXR_OK) goto fail;
  if (exr_library_import_source_unique(library, EXR_TXT, &source, "boundary", &id, &created, &error) != EXR_UNSUPPORTED || id != 0 || created != 0) goto fail;
  if (exr_library_import_unique(library, EXR_TXT, text, in.size, "ordinary", &id, &created, &error) != EXR_OK || id <= 0 || !created) goto fail;
  if (exr_library_import_unique(library, EXR_TXT, text, in.size, "duplicate", &duplicate, &created, &error) != EXR_OK || duplicate != id || created) goto fail;
  if (exr_library_document(library, id, &doc, &error) != EXR_OK || !doc) goto fail;
  exr_document_free(doc); doc = NULL;
  if (exr_library_source(library, id, &stored, &error) != EXR_OK || stored.size != in.size) goto fail;
  if (stored.read_at(stored.context, 0, bytes, in.size) != in.size || memcmp(bytes, text, in.size)) goto fail;
  stored.release(stored.context); exr_library_close(library);
  puts("TXT streaming import is unsupported; ordinary unique import retains original bytes and snapshot access");
  return 0;
fail:
  fprintf(stderr, "library boundary failed: %d %s\n", error.code, error.message);
  if (stored.release) stored.release(stored.context);
  exr_document_free(doc); exr_library_close(library); return 1;
}
