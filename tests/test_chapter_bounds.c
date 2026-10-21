/* SPDX-License-Identifier: MIT */
/* WP6 chapter-boundary guards: the declared 32 MiB member limit must reject an
   oversized chapter with EXR_LIMIT (not be raised to make 50/100 MiB chapters
   "pass"), and a loaded chapter must retain a bounded multiple of its projected
   text instead of geometric growth slack left over from parsing. */
#include "exreader.h"
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static exr_error error;
static unsigned checks;
#define CHECK(x)                                                                                   \
  do {                                                                                             \
    checks++;                                                                                      \
    if (!(x)) {                                                                                    \
      fprintf(stderr, "line %d: %s (%d: %s)\n", __LINE__, #x, (int)error.code, error.message);      \
      exit(1);                                                                                     \
    }                                                                                              \
  } while (0)
#define OK(x) CHECK((x) == EXR_OK)

typedef struct {
  unsigned char *data;
  size_t size, capacity;
} bytes;

static void append(bytes *b, const void *data, size_t size) {
  if (b->size + size > b->capacity) {
    size_t capacity = b->capacity ? b->capacity : 4096;
    unsigned char *grown;
    while (capacity < b->size + size)
      capacity *= 2;
    grown = realloc(b->data, capacity);
    CHECK(grown != NULL);
    b->data = grown;
    b->capacity = capacity;
  }
  memcpy(b->data + b->size, data, size);
  b->size += size;
}
static void put16(bytes *b, uint16_t value) {
  unsigned char raw[2] = {(unsigned char)(value & 0xFF), (unsigned char)(value >> 8)};
  append(b, raw, sizeof(raw));
}
static void put32(bytes *b, uint32_t value) {
  unsigned char raw[4] = {(unsigned char)(value & 0xFF), (unsigned char)((value >> 8) & 0xFF),
                          (unsigned char)((value >> 16) & 0xFF), (unsigned char)(value >> 24)};
  append(b, raw, sizeof(raw));
}
static uint32_t crc32_bytes(const void *data, size_t size) {
  static uint32_t table[256];
  static int ready;
  const unsigned char *p = data;
  uint32_t crc = 0xFFFFFFFFu;
  size_t i;
  if (!ready) {
    uint32_t n, k, c;
    for (n = 0; n < 256; n++) {
      c = n;
      for (k = 0; k < 8; k++)
        c = (c & 1) ? 0xEDB88320u ^ (c >> 1) : c >> 1;
      table[n] = c;
    }
    ready = 1;
  }
  for (i = 0; i < size; i++)
    crc = table[(crc ^ p[i]) & 0xFF] ^ (crc >> 8);
  return crc ^ 0xFFFFFFFFu;
}

typedef struct {
  const char *name;
  const unsigned char *data;
  size_t size;
} member;

/* Stored (uncompressed) ZIP so the test needs no compressor; the date is fixed. */
static void zip_write(bytes *zip, const member *members, size_t count) {
  size_t i;
  uint32_t central_size;
  size_t central_offset;
  uint32_t *offsets = calloc(count, sizeof(*offsets));
  CHECK(offsets != NULL);
  for (i = 0; i < count; i++) {
    uint32_t crc = crc32_bytes(members[i].data, members[i].size);
    size_t name = strlen(members[i].name);
    offsets[i] = (uint32_t)zip->size;
    put32(zip, 0x04034b50u);
    put16(zip, 20);
    put16(zip, 0);
    put16(zip, 0);
    put16(zip, 0);
    put16(zip, 23585); /* 2026-01-01 */
    put32(zip, crc);
    put32(zip, (uint32_t)members[i].size);
    put32(zip, (uint32_t)members[i].size);
    put16(zip, (uint16_t)name);
    put16(zip, 0);
    append(zip, members[i].name, name);
    append(zip, members[i].data, members[i].size);
  }
  central_offset = zip->size;
  for (i = 0; i < count; i++) {
    uint32_t crc = crc32_bytes(members[i].data, members[i].size);
    size_t name = strlen(members[i].name);
    put32(zip, 0x02014b50u);
    put16(zip, 20);
    put16(zip, 20);
    put16(zip, 0);
    put16(zip, 0);
    put16(zip, 0);
    put16(zip, 23585);
    put32(zip, crc);
    put32(zip, (uint32_t)members[i].size);
    put32(zip, (uint32_t)members[i].size);
    put16(zip, (uint16_t)name);
    put16(zip, 0);
    put16(zip, 0);
    put16(zip, 0);
    put16(zip, 0);
    put32(zip, 0);
    put32(zip, offsets[i]);
    append(zip, members[i].name, name);
  }
  central_size = (uint32_t)(zip->size - central_offset);
  put32(zip, 0x06054b50u);
  put16(zip, 0);
  put16(zip, 0);
  put16(zip, (uint16_t)count);
  put16(zip, (uint16_t)count);
  put32(zip, central_size);
  put32(zip, (uint32_t)central_offset);
  put16(zip, 0);
  free(offsets);
}

static const char *CONTAINER =
    "<?xml version=\"1.0\"?><container version=\"1.0\" "
    "xmlns=\"urn:oasis:names:tc:opendocument:xmlns:container\"><rootfiles>"
    "<rootfile full-path=\"OPS/package.opf\" "
    "media-type=\"application/oebps-package+xml\"/></rootfiles></container>";
static const char *PACKAGE =
    "<?xml version=\"1.0\"?><package xmlns=\"http://www.idpf.org/2007/opf\" version=\"3.0\" "
    "unique-identifier=\"id\"><metadata "
    "xmlns:dc=\"http://purl.org/dc/elements/1.1/\"><dc:identifier "
    "id=\"id\">urn:test</dc:identifier><dc:title>Bounds</dc:title>"
    "<dc:language>en</dc:language></metadata><manifest>\n"
    "<item id=\"c0\" href=\"c0.xhtml\" media-type=\"application/xhtml+xml\"/>"
    "</manifest><spine><itemref idref=\"c0\"/></spine></package>";

/* One XHTML chapter whose body is at least body_bytes of 400-byte paragraphs. */
static char *chapter(size_t body_bytes) {
  const size_t paragraph = 400;
  const size_t count = body_bytes / paragraph;
  const size_t fill = paragraph - 8; /* "<p>" + fill + "</p>\n" */
  const char *head = "<?xml version=\"1.0\"?><html "
                     "xmlns=\"http://www.w3.org/1999/xhtml\"><head><title>c</title></head>"
                     "<body>";
  const char *tail = "</body></html>";
  size_t head_size = strlen(head), tail_size = strlen(tail), i, at;
  char *text = malloc(head_size + count * (paragraph + 7) + tail_size + 1);
  CHECK(text != NULL);
  memcpy(text, head, head_size);
  at = head_size;
  for (i = 0; i < count; i++) {
    size_t j;
    memcpy(text + at, "<p>", 3);
    at += 3;
    for (j = 0; j < fill; j++)
      text[at + j] = (char)('a' + (int)((i + j) % 26));
    at += fill;
    memcpy(text + at, "</p>\n", 5);
    at += 5;
  }
  memcpy(text + at, tail, tail_size + 1);
  return text;
}

static void expect_limit(const char *label, size_t body_bytes) {
  bytes zip = {0};
  char *body = chapter(body_bytes);
  member members[4];
  exr_publication *publication = NULL;
  exr_document *document = NULL;
  exr_status status;
  members[0] = (member){"mimetype", (const unsigned char *)"application/epub+zip", 20};
  members[1] = (member){"META-INF/container.xml", (const unsigned char *)CONTAINER,
                        strlen(CONTAINER)};
  members[2] = (member){"OPS/package.opf", (const unsigned char *)PACKAGE, strlen(PACKAGE)};
  members[3] = (member){"OPS/c0.xhtml", (const unsigned char *)body, strlen(body)};
  zip_write(&zip, members, 4);
  OK(exr_publication_open_memory(EXR_EPUB, zip.data, zip.size, &publication, &error));
  status = exr_publication_load(publication, 0, &document, &error);
  if (status == EXR_OK) {
    fprintf(stderr, "%s: a %zu-byte chapter must not load\n", label, body_bytes);
    exit(1);
  }
  CHECK(status == EXR_LIMIT);
  CHECK(document == NULL);
  CHECK(strstr(error.message, "limit") != NULL);
  /* Failure cleanup: the publication still answers, and a retry repeats the limit. */
  {
    size_t parts = 0;
    (void)exr_publication_parts(publication, &parts);
    CHECK(parts == 1);
  }
  CHECK(exr_publication_load(publication, 0, &document, &error) == EXR_LIMIT);
  CHECK(document == NULL);
  exr_publication_free(publication);
  free(body);
  free(zip.data);
}

static void bounded_chapter(void) {
  bytes zip = {0};
  char *body = chapter(1024 * 1024);
  member members[4];
  exr_publication *publication = NULL;
  exr_document *document = NULL;
  size_t text_bytes = 0, owned;
  members[0] = (member){"mimetype", (const unsigned char *)"application/epub+zip", 20};
  members[1] = (member){"META-INF/container.xml", (const unsigned char *)CONTAINER,
                        strlen(CONTAINER)};
  members[2] = (member){"OPS/package.opf", (const unsigned char *)PACKAGE, strlen(PACKAGE)};
  members[3] = (member){"OPS/c0.xhtml", (const unsigned char *)body, strlen(body)};
  zip_write(&zip, members, 4);
  OK(exr_publication_open_memory(EXR_EPUB, zip.data, zip.size, &publication, &error));
  OK(exr_publication_load(publication, 0, &document, &error));
  (void)exr_document_text(document, &text_bytes);
  CHECK(text_bytes > 900 * 1024);
  owned = exr_document_memory_size(document);
  /* Text is copied twice today (raw node text plus the whitespace-collapsed
     projection); anything above three times the projection is growth slack. */
  CHECK(owned <= 3 * text_bytes);
  exr_document_free(document);
  exr_publication_free(publication);
  free(body);
  free(zip.data);
}

int main(void) {
  bytes zip = {0};
  char *body = chapter(512 * 1024);
  member members[4];
  exr_publication *publication = NULL;
  exr_document *document = NULL;
  size_t parts = 0;
  members[0] = (member){"mimetype", (const unsigned char *)"application/epub+zip", 20};
  members[1] = (member){"META-INF/container.xml", (const unsigned char *)CONTAINER,
                        strlen(CONTAINER)};
  members[2] = (member){"OPS/package.opf", (const unsigned char *)PACKAGE, strlen(PACKAGE)};
  members[3] = (member){"OPS/c0.xhtml", (const unsigned char *)body, strlen(body)};
  zip_write(&zip, members, 4);
  OK(exr_publication_open_memory(EXR_EPUB, zip.data, zip.size, &publication, &error));
  (void)exr_publication_parts(publication, &parts);
  CHECK(parts == 1);
  OK(exr_publication_load(publication, 0, &document, &error));
  CHECK(exr_document_nodes(document, NULL) != NULL);
  exr_document_free(document);
  exr_publication_free(publication);
  free(body);
  free(zip.data);
  bounded_chapter();
  /* 33 MiB exceeds the declared per-member limit before any decompression. */
  expect_limit("member limit", 33 * 1024 * 1024);
  printf("%u chapter bound checks passed\n", checks);
  return 0;
}
