/* SPDX-License-Identifier: MIT */
/* Installed-package consumer: creates the product/SDK fixtures and prints one
 * snapshot as JSON. It never links the module's private objects. */
#include <reader_book_information.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#ifdef _WIN32
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <shellapi.h>
#endif

static char **arg_vector;
static int arg_count;

#ifdef _WIN32
static int prepare_args(int argc, char **argv) {
  wchar_t **wide;
  int i;
  (void)argc; (void)argv;
  wide = CommandLineToArgvW(GetCommandLineW(), &arg_count);
  if (!wide) return 0;
  arg_vector = (char **)calloc((size_t)arg_count + 1, sizeof(*arg_vector));
  if (!arg_vector) { LocalFree(wide); return 0; }
  for (i = 0; i < arg_count; i++) {
    int n = WideCharToMultiByte(CP_UTF8, WC_ERR_INVALID_CHARS, wide[i], -1, NULL, 0, NULL, NULL);
    if (n <= 0) { LocalFree(wide); return 0; }
    arg_vector[i] = (char *)malloc((size_t)n);
    if (!arg_vector[i]) { LocalFree(wide); return 0; }
    WideCharToMultiByte(CP_UTF8, WC_ERR_INVALID_CHARS, wide[i], -1, arg_vector[i], n, NULL, NULL);
  }
  LocalFree(wide);
  return 1;
}
#else
static int prepare_args(int argc, char **argv) {
  arg_vector = argv; arg_count = argc; return 1;
}
#endif

static void json_string(const char *s) {
  const unsigned char *p;
  if (!s) { fputs("null", stdout); return; }
  putchar('"');
  for (p = (const unsigned char *)s; *p; p++) {
    if (*p == '"' || *p == '\\') { putchar('\\'); putchar((char)*p); }
    else if (*p < 0x20) printf("\\u%04x", (unsigned)*p);
    else putchar((char)*p);
  }
  putchar('"');
}

static int format_of(const char *name) {
  static const struct { const char *name; int format; } map[] = {
    {"txt", (int)EXR_TXT}, {"html", (int)EXR_HTML}, {"fb2", (int)EXR_FB2},
    {"epub", (int)EXR_EPUB}, {"docx", (int)EXR_DOCX}, {"rtf", (int)EXR_RTF},
    {"mobi", (int)EXR_MOBI}, {"pdf", (int)EXR_PDF}, {"cbz", (int)EXR_CBZ}};
  size_t i;
  for (i = 0; i < sizeof(map)/sizeof(*map); i++) if (!strcmp(map[i].name, name)) return map[i].format;
  return -1;
}

static void *slurp(const char *path, size_t *size) {
  FILE *file = fopen(path, "rb");
  long length;
  void *data;
  *size = 0;
  if (!file) return NULL;
  if (fseek(file, 0, SEEK_END) != 0) { fclose(file); return NULL; }
  length = ftell(file);
  if (length < 0) { fclose(file); return NULL; }
  rewind(file);
  data = malloc((size_t)length ? (size_t)length : 1);
  if (!data) { fclose(file); return NULL; }
  if (fread(data, 1, (size_t)length, file) != (size_t)length) { free(data); fclose(file); return NULL; }
  fclose(file);
  *size = (size_t)length;
  return data;
}

typedef struct { int limit; int calls; } cancel_state;
static int cancel_cb(void *context) {
  cancel_state *state = (cancel_state *)context;
  state->calls++;
  return state->limit > 0 && state->calls >= state->limit;
}

static void print_view(const reader_book_information_view *v) {
  size_t i;
  printf("\"view\":{");
  printf("\"book_key\":"); json_string(v->book_key);
  printf(",\"format\":"); json_string(v->format);
  printf(",\"location_kind\":"); json_string(v->location_kind);
  printf(",\"title\":"); json_string(v->title);
  printf(",\"author\":"); json_string(v->author);
  printf(",\"author_known\":%d", v->author_known);
  printf(",\"title_truncated\":%d", v->title_truncated);
  printf(",\"author_truncated\":%d", v->author_truncated);
  printf(",\"favorite\":%d", v->favorite);
  printf(",\"deleted\":%d", v->deleted);
  printf(",\"product_source_bytes\":%llu", (unsigned long long)v->product_source_bytes);
  printf(",\"availability\":%d", (int)v->availability);
  printf(",\"identity\":%d", (int)v->identity);
  printf(",\"verified_bytes\":%llu", (unsigned long long)v->verified_bytes);
  printf(",\"verified_sha256\":"); json_string(v->verified_sha256);
  printf(",\"parser_status\":%d", (int)v->parser_status);
  printf(",\"page_count_known\":%d", v->page_count_known);
  printf(",\"page_count\":%llu", (unsigned long long)v->page_count);
  printf(",\"parser_title\":"); json_string(v->parser_title);
  printf(",\"parser_title_truncated\":%d", v->parser_title_truncated);
  printf(",\"epub_mode_known\":%d", v->epub_mode_known);
  printf(",\"epub_bounded_storage\":%d", v->epub_bounded_storage);
  printf(",\"epub_global_extent_known\":%d", v->epub_global_extent_known);
  printf(",\"property_count\":%llu", (unsigned long long)v->property_count);
  printf(",\"properties_omitted\":%llu", (unsigned long long)v->properties_omitted);
  printf(",\"properties\":[");
  for (i = 0; i < v->property_count; i++) {
    if (i) putchar(',');
    printf("{\"key\":"); json_string(v->properties[i].key);
    printf(",\"value\":"); json_string(v->properties[i].value);
    printf(",\"key_truncated\":%d,\"value_truncated\":%d}",
           v->properties[i].key_truncated, v->properties[i].value_truncated);
  }
  printf("]}");
}

static int command_import(void) {
  exr_library *library = NULL;
  exr_error error;
  int64_t id = 0;
  int format, status, memory;
  void *data = NULL;
  size_t size = 0;
  memset(&error, 0, sizeof(error));
  format = format_of(arg_vector[3]);
  memory = !strcmp(arg_vector[5], "memory");
  status = format < 0 ? (int)EXR_ARGUMENT : (int)exr_library_open(arg_vector[2], &library, &error);
  if (status == (int)EXR_OK && memory) {
    data = slurp(arg_vector[4], &size);
    if (!data) status = (int)EXR_IO;
    else status = (int)exr_library_import(library, (exr_format)format, data, size, NULL, &id, &error);
  } else if (status == (int)EXR_OK) {
    status = (int)exr_library_import_file(library, (exr_format)format, arg_vector[4], NULL, &id, &error);
  }
  free(data);
  if (library) exr_library_close(library);
  printf("{\"status\":%d,\"id\":%lld,\"message\":", status, (long long)id);
  json_string(error.message);
  printf("}\n");
  return 0;
}

static int command_attach(void) {
  reader_catalog *catalog = NULL;
  reader_catalog_error error;
  reader_catalog_book book;
  int status;
  memset(&error, 0, sizeof(error));
  memset(&book, 0, sizeof(book));
  book.format = arg_vector[3];
  book.sha256 = arg_vector[4];
  book.source_bytes = strtoull(arg_vector[5], NULL, 10);
  book.title = arg_vector[6];
  book.author = arg_vector[7];
  book.sort_title = arg_vector[8];
  book.location_kind = strcmp(arg_vector[9], "-") ? arg_vector[9] : NULL;
  book.sdk_book_id = (int64_t)strtoll(arg_vector[10], NULL, 10);
  book.favorite = arg_count > 11 ? atoi(arg_vector[11]) : 0;
  status = reader_catalog_open(arg_vector[2], &catalog, &error);
  if (status == 0) {
    status = reader_catalog_attach(catalog, &book, &error);
    reader_catalog_close(&catalog, &error);
  }
  printf("{\"status\":%d,\"message\":", status);
  json_string(error.message);
  printf("}\n");
  return 0;
}

static int command_unmap(void) {
  reader_catalog *catalog = NULL;
  reader_catalog_error error;
  int status;
  memset(&error, 0, sizeof(error));
  status = reader_catalog_open(arg_vector[2], &catalog, &error);
  if (status == 0) {
    status = reader_catalog_remove_local(catalog, (int64_t)strtoll(arg_vector[3], NULL, 10), &error);
    reader_catalog_close(&catalog, &error);
  }
  printf("{\"status\":%d,\"message\":", status);
  json_string(error.message);
  printf("}\n");
  return 0;
}

static int command_read(void) {
  reader_catalog *catalog = NULL;
  exr_library *library = NULL;
  reader_book_information *snapshot = NULL;
  const reader_book_information_view *view = NULL;
  reader_book_information_options options;
  reader_book_information_error error;
  reader_catalog_error catalog_error;
  cancel_state state;
  exr_error sdk_error;
  int status, rc;
  memset(&error, 0, sizeof(error));
  memset(&catalog_error, 0, sizeof(catalog_error));
  memset(&sdk_error, 0, sizeof(sdk_error));
  memset(&options, 0, sizeof(options));
  options.struct_size = sizeof(options);
  options.verify_source = atoi(arg_vector[5]);
  options.read_parser_fields = atoi(arg_vector[6]);
  state.limit = atoi(arg_vector[7]);
  state.calls = 0;
  options.cancelled = cancel_cb;
  options.context = &state;
  rc = reader_catalog_open(arg_vector[2], &catalog, &catalog_error);
  if (rc == 0 && strcmp(arg_vector[3], "-") != 0) {
    rc = (int)exr_library_open(arg_vector[3], &library, &sdk_error);
    if (rc != 0) { reader_catalog_close(&catalog, &catalog_error); rc = -1; }
  }
  if (rc != 0) {
    printf("{\"status\":-1,\"out\":false,\"message\":");
    json_string(strcmp(arg_vector[3], "-") == 0 ? catalog_error.message : sdk_error.message);
    printf("}\n");
    return 0;
  }
  status = (int)reader_book_information_read(catalog, library, arg_vector[4], &options,
                                             &snapshot, &error);
  view = reader_book_information_get(snapshot);
  printf("{\"status\":%d,\"catalog\":%d,\"sdk\":%d,\"polls\":%d,\"out\":%s,\"message\":",
         status, error.catalog_code, error.sdk_code, state.calls, view ? "true" : "false");
  json_string(error.message);
  if (view) { printf(","); print_view(view); }
  printf("}\n");
  reader_book_information_free(snapshot);
  if (library) exr_library_close(library);
  reader_catalog_close(&catalog, &catalog_error);
  return 0;
}

static void arg_case(int index, const char *name, int status) {
  if (index) putchar(',');
  printf("{\"name\":");
  json_string(name);
  printf(",\"status\":%d}", status);
}

static int command_argcheck(void) {
  reader_catalog *catalog = NULL;
  exr_library *library = NULL;
  reader_catalog_error catalog_error;
  exr_error sdk_error;
  reader_book_information_error error;
  reader_book_information_options options;
  reader_book_information *snapshot = NULL;
  int status;
  char long_key[200];
  memset(&catalog_error, 0, sizeof(catalog_error));
  memset(&sdk_error, 0, sizeof(sdk_error));
  memset(&options, 0, sizeof(options));
  options.struct_size = sizeof(options);
  if (reader_catalog_open(arg_vector[2], &catalog, &catalog_error) != 0) return 2;
  if (exr_library_open(arg_vector[3], &library, &sdk_error) != 0) return 2;
  fputs("{\"cases\":[", stdout);
  status = (int)reader_book_information_read(NULL, library, arg_vector[4], &options, &snapshot, &error);
  arg_case(0, "null-catalog", status);
  status = (int)reader_book_information_read(catalog, library, arg_vector[4], &options, NULL, &error);
  arg_case(1, "null-output", status);
  status = (int)reader_book_information_read(catalog, library, "", &options, &snapshot, &error);
  arg_case(2, "empty-key", status);
  memset(long_key, 'a', sizeof(long_key) - 1);
  long_key[sizeof(long_key) - 1] = 0;
  status = (int)reader_book_information_read(catalog, library, long_key, &options, &snapshot, &error);
  arg_case(3, "overlong-key", status);
  status = (int)reader_book_information_read(catalog, library, "pdf:XYZ", &options, &snapshot, &error);
  arg_case(4, "malformed-key", status);
  status = (int)reader_book_information_read(catalog, library, "noseparator", &options, &snapshot, &error);
  arg_case(5, "missing-separator", status);
  {
    reader_book_information_options short_options;
    memset(&short_options, 0, sizeof(short_options));
    short_options.struct_size = 4;
    status = (int)reader_book_information_read(catalog, library, arg_vector[4], &short_options, &snapshot, &error);
    arg_case(6, "short-options", status);
  }
  status = (int)reader_book_information_read(catalog, library, "pdf:0000000000000000000000000000000000000000000000000000000000000000",
                                             &options, &snapshot, &error);
  arg_case(7, "absent-key", status);
  memset(&error, 0, sizeof(error));
  error.status = READER_BOOK_INFORMATION_MEMORY;
  strcpy(error.message, "stale");
  status = (int)reader_book_information_read(catalog, library, arg_vector[4], &options, &snapshot, &error);
  arg_case(8, "error-cleared", status == 0 && error.status == READER_BOOK_INFORMATION_OK &&
           error.message[0] == 0 && error.catalog_code == 0 && error.sdk_code == 0 ? 0 : 1);
  reader_book_information_free(snapshot);
  snapshot = NULL;
  printf("],\"get-null\":%s,\"free-null\":", reader_book_information_get(NULL) ? "false" : "true");
  reader_book_information_free(NULL);
  fputs("true}\n", stdout);
  exr_library_close(library);
  reader_catalog_close(&catalog, &catalog_error);
  return 0;
}

int main(int argc, char **argv) {
  if (!prepare_args(argc, argv)) return 2;
  if (arg_count < 2) return 2;
  if (!strcmp(arg_vector[1], "import") && arg_count == 6) return command_import();
  if (!strcmp(arg_vector[1], "attach") && arg_count >= 11) return command_attach();
  if (!strcmp(arg_vector[1], "unmap") && arg_count == 4) return command_unmap();
  if (!strcmp(arg_vector[1], "read") && arg_count == 8) return command_read();
  if (!strcmp(arg_vector[1], "argcheck") && arg_count == 5) return command_argcheck();
  fputs("{\"status\":-2,\"message\":\"unknown command\"}\n", stdout);
  return 2;
}
