/* SPDX-License-Identifier: MIT */
#include "exr/formats.h"
#include <miniz.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static exr_error error;
#define CHECK(x) do { if (!(x)) { fprintf(stderr, "line %d: %s: %s\n", __LINE__, #x, error.message); exit(1); } } while (0)
static const char container[] = "<container><rootfiles><rootfile full-path=\"OPS/book.opf\"/></rootfiles></container>";
static const char package[] = "<package><manifest><item id=\"main\" href=\"main.xhtml\" media-type=\"application/xhtml+xml\"/></manifest><spine><itemref idref=\"main\"/></spine></package>";
static const char chapter[] = "<html><body><p>Readable text</p></body></html>";
static void add(mz_zip_archive *z, const char *name, const char *body, unsigned flags) {
  CHECK(mz_zip_writer_add_mem(z, name, body, strlen(body), flags));
}
static unsigned char *book(const char *mime, int late, int compressed, int no_container, size_t *n) {
  mz_zip_archive z = {0};
  void *data = NULL;
  CHECK(mz_zip_writer_init_heap(&z, 0, 0));
  if (late) add(&z, "before", "first", 0);
  if (mime) add(&z, "mimetype", mime, compressed ? 9 : 0);
  if (!no_container) add(&z, "META-INF/container.xml", container, 0);
  add(&z, "OPS/book.opf", package, 0);
  add(&z, "OPS/main.xhtml", chapter, 0);
  add(&z, "OPS/alternate.xhtml", "<html><body><p>Wrong chapter</p></body></html>", 0);
  add(&z, "OPS/evil.xhtml", "<html><body><p>Replaced text</p></body></html>", 0);
  add(&z, "empty", "", 0);
  CHECK(mz_zip_writer_finalize_heap_archive(&z, &data, n));
  CHECK(mz_zip_writer_end(&z));
  return data;
}
static void readable(const unsigned char *data, size_t n) {
  exr_document *d = NULL;
  CHECK(exr_document_open_memory(EXR_EPUB, data, n, &d, &error) == EXR_OK);
  CHECK(d != NULL);
  exr_document_free(d);
}
static void rejected(const unsigned char *data, size_t n, const char *member) {
  CHECK(exr_epub_validate_memory(data, n, &error) == EXR_FORMAT);
  CHECK(strstr(error.message, member) && strstr(error.message, "expected") && strstr(error.message, "found"));
}
static size_t directory(unsigned char *data, size_t n, const char *name) {
  size_t i, len = strlen(name);
  for (i = 0; i + 46 + len <= n; i++)
    if (!memcmp(data + i, "PK\1\2", 4) && data[i + 28] == len && !data[i + 29] &&
        !memcmp(data + i + 46, name, len)) return i;
  CHECK(0);
  return 0;
}
static void mimetype_tests(void) {
  const char *values[] = {"application/epub+zip", "application/not-epub", "application/epub+zip\n", "", NULL};
  size_t i, n;
  unsigned char *data;
  for (i = 0; i < sizeof(values) / sizeof(*values); i++) {
    data = book(values[i], 0, 0, 0, &n);
    readable(data, n);
    if (!i) {
      CHECK(exr_epub_validate_memory(data, n, &error) == EXR_OK && !error.message[0]);
      CHECK(exr_epub_validate_memory(data, n, NULL) == EXR_OK);
    }
    else rejected(data, n, "mimetype");
    mz_free(data);
  }
  data = book(values[0], 1, 0, 0, &n);
  readable(data, n); rejected(data, n, "mimetype"); mz_free(data);
  { mz_zip_archive z = {0}; void *body = NULL;
    const char extra[] = {0x34, 0x12, 0, 0};
    CHECK(mz_zip_writer_init_heap(&z, 0, 0));
    CHECK(mz_zip_writer_add_mem_ex_v2(&z, "mimetype", values[0], strlen(values[0]),
          NULL, 0, 0, 0, 0, NULL, extra, sizeof(extra), NULL, 0));
    add(&z, "META-INF/container.xml", container, 0);
    add(&z, "OPS/book.opf", package, 0);
    add(&z, "OPS/main.xhtml", chapter, 0);
    CHECK(mz_zip_writer_finalize_heap_archive(&z, &body, &n));
    CHECK(mz_zip_writer_end(&z));
    readable(body, n); rejected(body, n, "mimetype"); mz_free(body);
  }
  data = book(values[0], 0, 1, 0, &n);
  CHECK(data[8] == 8); /* Ensure this really exercises compressed mimetype. */
  readable(data, n); rejected(data, n, "mimetype"); mz_free(data);
}
static void directory_tests(void) {
  const size_t fields[] = {42, 20, 24};
  size_t i, n, at;
  unsigned char *data;
  for (i = 0; i < sizeof(fields) / sizeof(*fields); i++) {
    data = book("application/epub+zip", 0, 0, 0, &n);
    at = directory(data, n, "mimetype"); data[at + fields[i]]++;
    readable(data, n); rejected(data, n, "mimetype"); mz_free(data);
  }
  /* Extraction trusts the directory filename. Strict validation also checks the
     actual local name, including for a member whose CRC/content still match. */
  data = book("application/epub+zip", 0, 0, 0, &n);
  at = directory(data, n, "OPS/main.xhtml");
  { size_t offset = (size_t)data[at + 42] | ((size_t)data[at + 43] << 8) |
                    ((size_t)data[at + 44] << 16) | ((size_t)data[at + 45] << 24);
    data[offset + 30] = 'X';
  }
  readable(data, n); rejected(data, n, "OPS/main.xhtml"); mz_free(data);
  /* A self-consistent directory can redirect a chapter to another local
     member. CRC alone cannot detect that substitution; the local name can. */
  data = book("application/epub+zip", 0, 0, 0, &n);
  at = directory(data, n, "OPS/main.xhtml");
  { size_t other = directory(data, n, "OPS/alternate.xhtml");
    exr_document *d = NULL;
    memcpy(data + at + 16, data + other + 16, 12); /* CRC and sizes */
    memcpy(data + at + 42, data + other + 42, 4); /* local offset */
    CHECK(exr_document_open_memory(EXR_EPUB, data, n, &d, &error) == EXR_OK);
    CHECK(strstr(exr_document_text(d, NULL), "Wrong chapter"));
    exr_document_free(d);
  }
  rejected(data, n, "OPS/main.xhtml"); mz_free(data);
  /* A self-consistent directory can redirect a requested name to another valid
     member. CRC/size checks alone accept the wrong content. No local scan occurs. */
  data = book("application/epub+zip", 0, 0, 0, &n);
  at = directory(data, n, "OPS/main.xhtml");
  { size_t other = directory(data, n, "OPS/evil.xhtml");
    exr_document *d = NULL;
    const char *text = NULL;
    size_t length = 0;
    memcpy(data + at + 16, data + other + 16, 12); /* CRC and sizes */
    memcpy(data + at + 42, data + other + 42, 4);  /* local-header offset */
    CHECK(exr_document_open_memory(EXR_EPUB, data, n, &d, &error) == EXR_OK);
    text = exr_document_text(d, &length);
    CHECK(length == strlen("Replaced text") && !memcmp(text, "Replaced text", length));
    exr_document_free(d);
  }
  rejected(data, n, "OPS/main.xhtml"); mz_free(data);
  data = book("application/epub+zip", 0, 0, 0, &n);
  at = directory(data, n, "OPS/main.xhtml"); data[at + 16] ^= 1;
  rejected(data, n, "OPS/main.xhtml");
  { exr_document *d = NULL;
    CHECK(exr_document_open_memory(EXR_EPUB, data, n, &d, &error) == EXR_FORMAT && !d);
  }
  mz_free(data);
  data = book("application/epub+zip", 0, 0, 0, &n);
  rejected(data, n - 1, "(archive)"); mz_free(data);
  data = book("application/epub+zip", 0, 0, 0, &n);
  at = directory(data, n, "empty");
  { size_t offset = (size_t)data[at + 42] | ((size_t)data[at + 43] << 8) |
                    ((size_t)data[at + 44] << 16) | ((size_t)data[at + 45] << 24);
    data[at + 16] = data[offset + 14] = 1; /* Matching but invalid CRC for empty content. */
  }
  readable(data, n); rejected(data, n, "empty"); mz_free(data);
}
static void container_tests(void) {
  size_t n;
  unsigned char *data = book("application/epub+zip", 0, 0, 1, &n);
  exr_document *d = NULL;
  rejected(data, n, "META-INF/container.xml");
  CHECK(exr_document_open_memory(EXR_EPUB, data, n, &d, &error) == EXR_FORMAT && !d);
  CHECK(strstr(error.message, "META-INF/container.xml"));
  mz_free(data);
  CHECK(exr_epub_validate_memory(NULL, 0, &error) == EXR_ARGUMENT);
  CHECK(exr_epub_validate(NULL, &error) == EXR_ARGUMENT);
}
int main(int argc, char **argv) {
  CHECK(argc == 2);
  if (!strcmp(argv[1], "mimetype")) mimetype_tests();
  else if (!strcmp(argv[1], "directory")) directory_tests();
  else if (!strcmp(argv[1], "container")) container_tests();
  else CHECK(0);
  puts("strict/tolerant EPUB checks passed");
  return 0;
}
