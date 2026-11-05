/* SPDX-License-Identifier: MIT
 * S12 C11 consumer against the installed public C ABI only.
 *
 * Read-only traversal of the Unicode product database written by the C++
 * consumer, plus the counted UTF-16 command boundary. The row text is
 * byte-identical in shape to the C++ consumer's, so the checker can require
 * both ABIs to agree field for field.
 */
#include <catalog.h>
#include <reader_commands.h>

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define MAX_ITEMS 256
#define MAX_NAME 128
#define TEXT_CAPACITY 65536
#define ROW_CAPACITY 4096
#define PAGE_CAPACITY 32768

struct item {
  char id[MAX_NAME];
  int kind;
  unsigned char *data;
  char *text; /* NUL-terminated copy, never used for UTF-16 payloads */
  size_t size;
};

static struct item items[MAX_ITEMS];
static int item_count;
static FILE *sink;

static unsigned read32(const unsigned char *p) {
  return (unsigned)p[0] | ((unsigned)p[1] << 8) | ((unsigned)p[2] << 16) | ((unsigned)p[3] << 24);
}

static int load(const char *path) {
  FILE *file = fopen(path, "rb");
  long size;
  unsigned char *blob;
  size_t at;
  unsigned count, index;
  if (!file) return 1;
  if (fseek(file, 0, SEEK_END) != 0) { fclose(file); return 1; }
  size = ftell(file);
  if (size < 12) { fclose(file); return 1; }
  rewind(file);
  blob = (unsigned char *)malloc((size_t)size);
  if (!blob) { fclose(file); return 1; }
  if (fread(blob, 1, (size_t)size, file) != (size_t)size) { fclose(file); free(blob); return 1; }
  fclose(file);
  if (memcmp(blob, "S121", 4) != 0 || read32(blob + 4) != 1) { free(blob); return 1; }
  count = read32(blob + 8);
  at = 12;
  for (index = 0; index < count && item_count < MAX_ITEMS; ++index) {
    unsigned name_length = read32(blob + at);
    unsigned kind, length;
    at += 4;
    if (name_length >= MAX_NAME || at + name_length + 8 > (size_t)size) { free(blob); return 1; }
    memcpy(items[item_count].id, blob + at, name_length);
    items[item_count].id[name_length] = 0;
    at += name_length;
    kind = read32(blob + at);
    at += 4;
    length = read32(blob + at);
    at += 4;
    if (at + length > (size_t)size) { free(blob); return 1; }
    items[item_count].kind = (int)kind;
    items[item_count].size = length;
    items[item_count].data = (unsigned char *)malloc((size_t)length + 1);
    items[item_count].text = (char *)malloc((size_t)length + 1);
    if (!items[item_count].data || !items[item_count].text) { free(blob); return 1; }
    memcpy(items[item_count].data, blob + at, length);
    items[item_count].data[length] = 0;
    memcpy(items[item_count].text, blob + at, length);
    items[item_count].text[length] = 0;
    at += length;
    ++item_count;
  }
  free(blob);
  return 0;
}

static const struct item *need(const char *id) {
  int index;
  for (index = 0; index < item_count; ++index)
    if (strcmp(items[index].id, id) == 0) return &items[index];
  return NULL;
}

static void record(const char *name) { fprintf(sink, "#%s\n", name); }
static void field(const char *key, const char *value) { fprintf(sink, "%s=%s\n", key, value); }
static void number(const char *key, long long value) { fprintf(sink, "%s=%lld\n", key, value); }

static void convert(const struct item *value, char *output, size_t capacity, size_t *bytes, int *status) {
  uint16_t units[16385];
  size_t count = value->size / 2, index;
  reader_command_error error;
  memset(&error, 0, sizeof(error));
  if (value->size % 2 || count > 16384) {
    *bytes = 0;
    *status = -1;
    output[0] = 0;
    return;
  }
  for (index = 0; index < count; ++index)
    units[index] = (uint16_t)((uint16_t)value->data[index * 2] | ((uint16_t)value->data[index * 2 + 1] << 8));
  *status = (int)reader_command_utf16(units, count, output, capacity, bytes, &error);
}
static void must_convert(const char *id, char *output, size_t capacity) {
  size_t bytes = 0;
  int status = 0;
  const struct item *value = need(id);
  if (!value) { fprintf(stderr, "missing item %s\n", id); exit(6); }
  convert(value, output, capacity, &bytes, &status);
  if (status != 0) { fprintf(stderr, "cannot convert %s\n", id); exit(6); }
}
static void text_record(const char *name, const char *id) {
  char output[TEXT_CAPACITY];
  size_t bytes = 0;
  int status = 0;
  const struct item *value = need(id);
  if (!value) { fprintf(stderr, "missing item %s\n", id); exit(6); }
  convert(value, output, sizeof(output), &bytes, &status);
  record(name);
  number("status", status);
  number("bytes", (long long)bytes);
  fprintf(sink, "hex=");
  if (status == 0) {
    size_t index;
    for (index = 0; index < bytes; ++index) fprintf(sink, "%02x", (unsigned char)output[index]);
  }
  fprintf(sink, "\n");
}

static void append_hex(char *out, const char *text) {
  size_t used = strlen(out), index;
  const unsigned char *data = (const unsigned char *)(text ? text : "");
  for (index = 0; index < strlen((const char *)data); ++index)
    used += (size_t)snprintf(out + used, ROW_CAPACITY - used, "%02x", data[index]);
}
static void build_row(char *out, const reader_catalog_row *row) {
  size_t used;
  out[0] = 0;
  snprintf(out, ROW_CAPACITY, "titlehex=");
  append_hex(out, row->title);
  snprintf(out + strlen(out), ROW_CAPACITY - strlen(out), ";authorhex=");
  append_hex(out, row->author);
  snprintf(out + strlen(out), ROW_CAPACITY - strlen(out), ";sorthex=");
  append_hex(out, row->sort_title);
  used = strlen(out);
  snprintf(out + used, ROW_CAPACITY - used, ";key=%s;format=%s;bytes=%llu;fav=%d;sdk=%lld;loc=%s;deleted=%d",
           row->book_key ? row->book_key : "", row->format ? row->format : "",
           (unsigned long long)row->source_bytes, row->favorite, (long long)row->sdk_book_id,
           row->location_kind ? row->location_kind : "", row->deleted);
}
struct page {
  char joined[PAGE_CAPACITY];
  size_t rows;
};
static int collect(void *context, const reader_catalog_row *row) {
  struct page *collected = (struct page *)context;
  char text[ROW_CAPACITY];
  build_row(text, row);
  if (collected->rows) strncat(collected->joined, "|", sizeof(collected->joined) - strlen(collected->joined) - 1);
  strncat(collected->joined, text, sizeof(collected->joined) - strlen(collected->joined) - 1);
  collected->rows += 1;
  return 0;
}
static void page_record(const char *name, int status, const struct page *value, const reader_catalog_error *error) {
  record(name);
  number("status", status);
  number("error", error->code);
  number("rows", (long long)value->rows);
  field("joined", value->joined);
}
static void row_record(const char *name, int status, int found, const struct page *value) {
  record(name);
  number("status", status);
  number("found", found);
  number("rows", (long long)value->rows);
  field("joined", value->joined);
}

int main(int argc, char **argv) {
  char root[2048] = {0}, database[4096];
  char workspace[512], space[512], library[512], database_name[512];
  char query_ascii[512], query_unicode[1024], sort_nfc[2048], sort_nfd[2048];
  const char *input = NULL, *output = NULL;
  int index;

  for (index = 1; index + 1 < argc; index += 2) {
    if (strcmp(argv[index], "--input") == 0) input = argv[index + 1];
    else if (strcmp(argv[index], "--root") == 0) snprintf(root, sizeof(root), "%s", argv[index + 1]);
    else if (strcmp(argv[index], "--output") == 0) output = argv[index + 1];
    else return 2;
  }
  if (!input || !output || !root[0]) return 2;
  if (load(input)) { fprintf(stderr, "cannot load the request container\n"); return 1; }

  must_convert("dir.workspace", workspace, sizeof(workspace));
  must_convert("dir.space", space, sizeof(space));
  must_convert("dir.library", library, sizeof(library));
  /* The frozen copy of the initial state, so both ABIs observe the same rows. */
  must_convert("file.frozen", database_name, sizeof(database_name));
  must_convert("query.ascii", query_ascii, sizeof(query_ascii));
  must_convert("query.unicode", query_unicode, sizeof(query_unicode));
  must_convert("book.1.sort", sort_nfc, sizeof(sort_nfc));
  must_convert("book.2.sort", sort_nfd, sizeof(sort_nfd));
  snprintf(database, sizeof(database), "%s/%s/%s/%s/%s", root, workspace, space, library, database_name);

  sink = fopen(output, "wb");
  if (!sink) return 4;

  record("c.version");
  field("commands", READER_COMMANDS_VERSION);
  field("revisions", READER_REVISIONS_VERSION);
  text_record("c.utf16.title.nfc", "title.nfc");
  text_record("c.utf16.author.cjk", "author.cjk");
  text_record("c.utf16.file.main", "file.main");
  text_record("c.utf16.nul", "nul.product");

  {
    reader_catalog *catalog = NULL;
    reader_catalog_error error;
    int status;
    memset(&error, 0, sizeof(error));
    status = reader_catalog_open(database, &catalog, &error);
    record("c.catalog.open");
    number("status", status);
    number("error", error.code);
    if (status != 0) {
      fclose(sink);
      return 5;
    }
    {
      struct page collected;
      reader_catalog_error page_error;
      memset(&collected, 0, sizeof(collected));
      memset(&page_error, 0, sizeof(page_error));
      page_record("c.page.all", reader_catalog_page(catalog, NULL, NULL, 200, collect, &collected, &page_error),
                  &collected, &page_error);
      record("c.rows");
      number("count", (long long)collected.rows);
      memset(&collected, 0, sizeof(collected));
      memset(&page_error, 0, sizeof(page_error));
      page_record("c.page.forward.0", reader_catalog_page(catalog, NULL, NULL, 2, collect, &collected, &page_error),
                  &collected, &page_error);
      memset(&collected, 0, sizeof(collected));
      memset(&page_error, 0, sizeof(page_error));
      page_record("c.query.ascii",
                  reader_catalog_query_page(catalog, NULL, NULL, query_ascii, 1, 200, collect, &collected,
                                            &page_error),
                  &collected, &page_error);
      memset(&collected, 0, sizeof(collected));
      memset(&page_error, 0, sizeof(page_error));
      page_record("c.query.unicode",
                  reader_catalog_query_page(catalog, NULL, NULL, query_unicode, 1, 200, collect, &collected,
                                            &page_error),
                  &collected, &page_error);
      memset(&collected, 0, sizeof(collected));
      memset(&page_error, 0, sizeof(page_error));
      page_record("c.canonical.nfc",
                  reader_catalog_local_canonical_page(catalog, NULL, NULL, sort_nfc, sort_nfd, 1, 0, 200, collect,
                                                      &collected, &page_error),
                  &collected, &page_error);
      memset(&collected, 0, sizeof(collected));
      memset(&page_error, 0, sizeof(page_error));
      page_record("c.canonical.null",
                  reader_catalog_local_canonical_page(catalog, NULL, NULL, NULL, sort_nfd, 1, 0, 200, collect,
                                                      &collected, &page_error),
                  &collected, &page_error);
      {
        int found = -1;
        memset(&collected, 0, sizeof(collected));
        memset(&page_error, 0, sizeof(page_error));
        status = reader_catalog_local_lookup(catalog, (int64_t)atoll(need("book.3.sdk")->text), NULL, collect,
                                            &collected, &found, &page_error);
        row_record("c.lookup.id", status, found, &collected);
      }
      {
        int found = -1;
        memset(&collected, 0, sizeof(collected));
        memset(&page_error, 0, sizeof(page_error));
        status = reader_catalog_metadata(catalog, need("book.1.key")->text, collect, &collected, &found, &page_error);
        row_record("c.metadata.one", status, found, &collected);
        found = -1;
        memset(&collected, 0, sizeof(collected));
        status = reader_catalog_metadata(catalog, need("book.2.key")->text, collect, &collected, &found, &page_error);
        row_record("c.metadata.two", status, found, &collected);
        found = -1;
        memset(&collected, 0, sizeof(collected));
        status = reader_catalog_metadata(catalog, "", collect, &collected, &found, &page_error);
        row_record("c.metadata.empty", status, found, &collected);
        found = -1;
        memset(&collected, 0, sizeof(collected));
        status = reader_catalog_metadata(catalog, NULL, collect, &collected, &found, &page_error);
        row_record("c.metadata.null", status, found, &collected);
      }
    }
    reader_catalog_close(&catalog, &error);
  }
  fclose(sink);
  return 0;
}
