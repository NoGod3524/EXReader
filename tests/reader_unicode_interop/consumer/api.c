/* SPDX-License-Identifier: MIT
 * G14 Unicode interop consumer compiled as C11 against the installed public
 * C ABI only. Unicode enters through reader_command_utf16 from the binary
 * request container, never through argv.
 */
#include <catalog.h>
#include <reader_commands.h>
#include <reader_projection.h>
#include <reader_revisions.h>

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define MAX_ITEMS 256
#define MAX_AUX 4096
#define TEXT_CAPACITY 16385

struct item {
  char id[64];
  int kind;
  unsigned char *data;
  size_t size;
};

struct pair {
  char key[128];
  char value[512];
};

static struct item items[MAX_ITEMS];
static int item_count;
static struct pair aux[MAX_AUX];
static int aux_count;
static FILE *sink;

static unsigned read32(const unsigned char *p) {
  return (unsigned)p[0] | ((unsigned)p[1] << 8) | ((unsigned)p[2] << 16) | ((unsigned)p[3] << 24);
}

static int load(const char *path) {
  FILE *file = fopen(path, "rb");
  long size;
  unsigned char *blob;
  size_t off = 4;
  unsigned count, i;
  if (!file) { fprintf(stderr, "cannot open request container\n"); return 1; }
  if (fseek(file, 0, SEEK_END) != 0) { fclose(file); return 1; }
  size = ftell(file);
  if (size < 8) { fclose(file); return 1; }
  rewind(file);
  blob = (unsigned char *)malloc((size_t)size);
  if (!blob) { fclose(file); return 1; }
  if (fread(blob, 1, (size_t)size, file) != (size_t)size) { fclose(file); free(blob); return 1; }
  fclose(file);
  if (memcmp(blob, "G141", 4) != 0 || read32(blob + 4) != 1) { free(blob); return 1; }
  count = read32(blob + 8);
  off = 12;
  for (i = 0; i < count && item_count < MAX_ITEMS; i++) {
    unsigned idlen = read32(blob + off); off += 4;
    if (idlen >= sizeof items[0].id) { free(blob); return 1; }
    memcpy(items[item_count].id, blob + off, idlen);
    items[item_count].id[idlen] = 0;
    off += idlen;
    items[item_count].kind = blob[off];
    off += 1;
    items[item_count].size = read32(blob + off);
    off += 4;
    items[item_count].data = (unsigned char *)malloc(items[item_count].size + 1);
    if (!items[item_count].data) { free(blob); return 1; }
    memcpy(items[item_count].data, blob + off, items[item_count].size);
    items[item_count].data[items[item_count].size] = 0;
    off += items[item_count].size;
    item_count++;
  }
  count = read32(blob + off); off += 4;
  for (i = 0; i < count && aux_count < MAX_AUX; i++) {
    unsigned keylen = read32(blob + off); off += 4;
    if (keylen >= sizeof aux[0].key) { free(blob); return 1; }
    memcpy(aux[aux_count].key, blob + off, keylen);
    aux[aux_count].key[keylen] = 0;
    off += keylen;
    {
      unsigned vallen = read32(blob + off); off += 4;
      if (vallen >= sizeof aux[0].value) { free(blob); return 1; }
      memcpy(aux[aux_count].value, blob + off, vallen);
      aux[aux_count].value[vallen] = 0;
      off += vallen;
    }
    aux_count++;
  }
  free(blob);
  return 0;
}

static const char *key_value(const char *key) {
  int i;
  for (i = 0; i < aux_count; i++) if (strcmp(aux[i].key, key) == 0) return aux[i].value;
  fprintf(stderr, "missing request key %s\n", key);
  return NULL;
}

static const struct item *find_item(const char *id) {
  int i;
  for (i = 0; i < item_count; i++) if (strcmp(items[i].id, id) == 0) return &items[i];
  return NULL;
}

static void write_hex(const char *key, const char *data, size_t size) {
  static const char *digits = "0123456789abcdef";
  size_t i;
  fprintf(sink, "%s=", key);
  for (i = 0; i < size; i++) {
    unsigned char value = (unsigned char)data[i];
    fputc(digits[value >> 4], sink);
    fputc(digits[value & 15], sink);
  }
  fputc('\n', sink);
}

struct title_sink {
  char data[TEXT_CAPACITY];
  size_t size;
};

static int visit_title(void *raw, const reader_catalog_row *row) {
  struct title_sink *holder = (struct title_sink *)raw;
  size_t size = strlen(row->title);
  if (size > sizeof holder->data - 1) size = sizeof holder->data - 1;
  memcpy(holder->data, row->title, size);
  holder->size = size;
  return 0;
}

int main(int argc, char **argv) {
  const char *input = NULL;
  const char *output = NULL;
  const char *title_name;
  const struct item *title_item;
  const struct item *database_item;
  static char title[TEXT_CAPACITY];
  static char author[TEXT_CAPACITY];
  static char sort[TEXT_CAPACITY];
  size_t title_bytes = 0, author_bytes = 0, sort_bytes = 0;
  reader_command_error command_error;
  reader_command_result result;
  reader_command_context context;
  reader_book_command book;
  reader_revision_error revision_error;
  reader_catalog_error catalog_error;
  reader_revisions *store = NULL;
  reader_catalog *catalog = NULL;
  char *wire = NULL;
  size_t wire_bytes = 0;
  reader_revision_info info;
  struct title_sink holder;
  int found = 0;
  int convert;
  int meta_status = 0;

  for (convert = 1; convert + 1 < argc; convert += 2) {
    if (strcmp(argv[convert], "--input") == 0) input = argv[convert + 1];
    else if (strcmp(argv[convert], "--output") == 0) output = argv[convert + 1];
  }
  if (!input || !output) { fprintf(stderr, "usage: unicode-c-consumer --input <cases.bin> --output <observations>\n"); return 2; }
  if (load(input) != 0) { fprintf(stderr, "request container rejected\n"); return 2; }
  sink = fopen(output, "wb");
  if (!sink) { fprintf(stderr, "cannot write observations\n"); return 2; }

  title_name = key_value("c1.title");
  title_item = title_name ? find_item(title_name) : NULL;
  database_item = find_item("p.db_d");
  if (!title_item || !database_item) { fprintf(stderr, "request container lacks c1 inputs\n"); return 2; }

  memset(&command_error, 0, sizeof command_error);
  convert = reader_command_utf16((const uint16_t *)(const void *)title_item->data,
                                 title_item->size / 2, title, sizeof title, &title_bytes,
                                 &command_error);
  fprintf(sink, "#c.utf16\nstatus=%d\nbytes=%d\n", (int)convert, (int)title_bytes);
  write_hex("hex", title, title_bytes);
  if (convert != READER_COMMAND_OK) { fclose(sink); return 3; }

  {
    const char *author_name = key_value("c1.author");
    const struct item *author_item = author_name ? find_item(author_name) : NULL;
    if (author_item && author_item->kind == 0) {
      reader_command_error error;
      memset(&error, 0, sizeof error);
      if (reader_command_utf16((const uint16_t *)(const void *)author_item->data,
                               author_item->size / 2, author, sizeof author, &author_bytes,
                               &error) != READER_COMMAND_OK) { fclose(sink); return 3; }
    }
  }
  memcpy(sort, title, title_bytes);
  sort_bytes = title_bytes;

  memset(&revision_error, 0, sizeof revision_error);
  if (reader_revisions_open((const char *)database_item->data, &store, &revision_error) != READER_REV_OK) {
    fprintf(stderr, "C store open failed: %s\n", revision_error.message);
    fclose(sink);
    return 3;
  }
  memset(&context, 0, sizeof context);
  context.store = store;
  context.revision_id = key_value("c1.rev");
  memset(&book, 0, sizeof book);
  book.operation = READER_COMMAND_PUT;
  book.book_key = key_value("c1.key");
  book.format = key_value("c1.format");
  book.source_sha256 = key_value("c1.sha");
  book.title = title;
  book.author = author;
  book.sort_title = sort;
  book.source_bytes = (uint64_t)strtoull(key_value("c1.bytes"), NULL, 10);
  book.favorite = 0;
  if (!context.revision_id || !book.book_key) { fclose(sink); return 3; }
  convert = reader_command_apply_book(&context, &book, &result, &command_error);
  fprintf(sink, "#c.cmd\nstatus=%d\ncreated=%d\napplied=%d\n", (int)convert,
          result.created, result.applied);
  if (convert == READER_COMMAND_OK) {
    fprintf(sink, "sha256=%s\nbytes=%d\n", result.revision.sha256, (int)result.revision.bytes);
  }

  memset(&catalog_error, 0, sizeof catalog_error);
  if (reader_catalog_open((const char *)database_item->data, &catalog, &catalog_error) != 0) {
    fprintf(stderr, "C catalog open failed: %s\n", catalog_error.message);
    fclose(sink);
    return 3;
  }
  {
    reader_catalog_book attached;
    int attach_status;
    memset(&attached, 0, sizeof attached);
    attached.format = book.format;
    attached.sha256 = book.source_sha256;
    attached.title = title;
    attached.author = author;
    attached.sort_title = sort;
    attached.location_kind = "reflow_global";
    attached.source_bytes = book.source_bytes;
    attached.sdk_book_id = 701;
    attached.favorite = 0;
    attach_status = reader_catalog_attach(catalog, &attached, &catalog_error);
    fprintf(sink, "#c.attach\nstatus=%d\nkey=%s\n", attach_status, book.book_key);
  }

  memset(&info, 0, sizeof info);
  memset(&revision_error, 0, sizeof revision_error);
  convert = reader_revision_get(store, context.revision_id, &wire, &wire_bytes, &info, &revision_error);
  fprintf(sink, "#c.wire\n");
  if (convert == READER_REV_OK) write_hex("hex", wire, wire_bytes);
  if (wire) reader_revision_bytes_free(wire);
  wire = NULL;

  memset(&holder, 0, sizeof holder);
  found = 0;
  meta_status = reader_catalog_metadata(catalog, book.book_key, visit_title, &holder, &found,
                                        &catalog_error);
  fprintf(sink, "#c.meta\nfound=%d\nstatus=%d\n", found, meta_status);
  write_hex("title", holder.data, holder.size);
  found = 0;
  meta_status = reader_catalog_find(catalog, book.book_key, NULL, visit_title, &holder, &found,
                                    &catalog_error);
  fprintf(sink, "#c.find\nfound=%d\nstatus=%d\n", found, meta_status);

  memset(&catalog_error, 0, sizeof catalog_error);
  reader_catalog_close(&catalog, &catalog_error);
  memset(&revision_error, 0, sizeof revision_error);
  reader_revisions_close(&store, &revision_error);

  /* second open: the retained bytes and metadata must be identical */
  memset(&revision_error, 0, sizeof revision_error);
  if (reader_revisions_open((const char *)database_item->data, &store, &revision_error) != READER_REV_OK) {
    fclose(sink);
    return 3;
  }
  memset(&catalog_error, 0, sizeof catalog_error);
  if (reader_catalog_open((const char *)database_item->data, &catalog, &catalog_error) != 0) {
    fclose(sink);
    return 3;
  }
  memset(&info, 0, sizeof info);
  convert = reader_revision_get(store, context.revision_id, &wire, &wire_bytes, &info, &revision_error);
  fprintf(sink, "#c.reopen.wire\n");
  if (convert == READER_REV_OK) write_hex("hex", wire, wire_bytes);
  if (wire) reader_revision_bytes_free(wire);
  memset(&holder, 0, sizeof holder);
  found = 0;
  meta_status = reader_catalog_metadata(catalog, book.book_key, visit_title, &holder, &found,
                                        &catalog_error);
  fprintf(sink, "#c.reopen.meta\nfound=%d\nstatus=%d\n", found, meta_status);
  write_hex("title", holder.data, holder.size);

  memset(&catalog_error, 0, sizeof catalog_error);
  reader_catalog_close(&catalog, &catalog_error);
  memset(&revision_error, 0, sizeof revision_error);
  reader_revisions_close(&store, &revision_error);
  fclose(sink);
  (void)author_bytes;
  (void)sort_bytes;
  return 0;
}
