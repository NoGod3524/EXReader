/* SPDX-License-Identifier: MIT */
/* Deterministic N-original TXT corpus for the C02 product performance tools.
   Uses only the installed public SDK (exr_library_*), never product schema1.
   Book 0 is a long multi-page text; the other originals are one-line texts.
   Every 17th book carries the literal-search author "Author %_!". */
#define _CRT_SECURE_NO_WARNINGS
#include <exreader.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define PARAGRAPHS 2000u
#define PARAGRAPH_CAPACITY 256u
#define BODY_CAPACITY 256u

static exr_error failure = {0};

static void fail(const char *what, int line) {
  fprintf(stderr, "c02_seed: %s failed at line %d: %s\n", what, line, failure.message);
  exit(1);
}
#define CHECK(value) do { if(!(value)) fail(#value, __LINE__); } while(0)

static unsigned long long fnv1a(const void *bytes, size_t size) {
  const unsigned char *data = bytes;
  unsigned long long hash = 1469598103934665603ull;
  for(size_t i = 0; i < size; i++) { hash ^= data[i]; hash *= 1099511628211ull; }
  return hash;
}

static void long_body(char *buffer, size_t capacity, size_t *size) {
  size_t used = 0;
  for(unsigned paragraph = 0; paragraph < PARAGRAPHS; paragraph++) {
    int written = snprintf(buffer + used, capacity - used,
      "Shelf 0000 paragraph %04u carries deterministic bytes for the pagination measurement; "
      "every run writes the same continuation so the corpus is reproducible.\n", paragraph);
    if(written <= 0 || (size_t)written >= capacity - used) {
      fprintf(stderr, "c02_seed: long body overflow at paragraph %u\n", paragraph);
      exit(1);
    }
    used += (size_t)written;
  }
  *size = used;
}

static void short_body(char *buffer, size_t capacity, unsigned index, size_t *size) {
  int written = snprintf(buffer, capacity,
    "Shelf original %04u. Read this book and return to the same shelf position.\n", index);
  if(written <= 0 || (size_t)written >= capacity) {
    fprintf(stderr, "c02_seed: short body overflow at %u\n", index);
    exit(1);
  }
  *size = (size_t)written;
}

int main(int argc, char **argv) {
  if(argc != 4) { fprintf(stderr, "usage: %s LIBRARY_SQLITE CORPUS_JSON BOOKS\n", argv[0]); return 2; }
  unsigned books_total = (unsigned)strtoul(argv[3], NULL, 10);
  if(books_total < 100u || books_total > 9999u) { fprintf(stderr, "c02_seed: BOOKS must be 100..9999\n"); return 2; }
  exr_library *library = NULL;
  CHECK(exr_library_open(argv[1], &library, &failure) == EXR_OK);
  size_t body_capacity = (size_t)PARAGRAPHS * PARAGRAPH_CAPACITY + 1;
  char *body = malloc(body_capacity);
  int64_t *ids = calloc(books_total, sizeof(*ids));
  size_t *sizes = calloc(books_total, sizeof(*sizes));
  unsigned long long *hashes = calloc(books_total, sizeof(*hashes));
  CHECK(body != NULL && ids != NULL && sizes != NULL && hashes != NULL);
  for(unsigned index = 0; index < books_total; index++) {
    char title[32];
    const char *author = index % 17u == 0u ? "Author %_!" : "Reader";
    size_t size = 0;
    int created = 0;
    snprintf(title, sizeof(title), "Shelf %04u", index);
    if(index == 0) long_body(body, body_capacity, &size);
    else short_body(body, BODY_CAPACITY, index, &size);
    hashes[index] = fnv1a(body, size);
    CHECK(exr_library_import_unique(library, EXR_TXT, body, size, title, &ids[index], &created, &failure) == EXR_OK);
    if(!created) { fprintf(stderr, "c02_seed: book %u was not newly created\n", index); return 1; }
    exr_book book = {0};
    book.id = ids[index];
    book.title = title;
    book.author = (char *)author;
    book.tags = "";
    CHECK(exr_library_update(library, &book, &failure) == EXR_OK);
    sizes[index] = size;
  }
  exr_book *books = NULL;
  size_t count = 0;
  CHECK(exr_library_books(library, "", &books, &count, &failure) == EXR_OK);
  if(count != books_total) { fprintf(stderr, "c02_seed: expected %u books, found %zu\n", books_total, count); return 1; }
  exr_books_free(books, count);
  size_t long_bytes = sizes[0];
  unsigned long long total = 0;
  for(unsigned index = 0; index < books_total; index++) total += sizes[index];
  FILE *manifest = fopen(argv[2], "wb");
  CHECK(manifest != NULL);
  fprintf(manifest, "{\n  \"schema\": 1,\n  \"books\": %u,\n  \"long_book_bytes\": %zu,\n", books_total, sizes[0]);
  fprintf(manifest, "  \"total_original_bytes\": %llu,\n  \"first_id\": %lld,\n  \"originals\": [\n", total, (long long)ids[0]);
  for(unsigned index = 0; index < books_total; index++) {
    fprintf(manifest,
      "    {\"index\": %u, \"id\": %lld, \"title\": \"Shelf %04u\", \"author\": \"%s\", "
      "\"bytes\": %zu, \"fnv1a64\": \"%016llx\"}%s\n",
      index, (long long)ids[index], index, index % 17u == 0u ? "Author %_!" : "Reader",
      sizes[index], hashes[index], index + 1u == books_total ? "" : ",");
  }
  fprintf(manifest, "  ]\n}\n");
  if(fclose(manifest)) { fprintf(stderr, "c02_seed: manifest close failed\n"); return 1; }
  free(hashes);
  free(ids);
  free(sizes);
  free(body);
  exr_library_close(library);
  printf("{\"seeded\": %u, \"long_book_bytes\": %zu, \"total_original_bytes\": %llu}\n",
         books_total, long_bytes, total);
  return 0;
}
