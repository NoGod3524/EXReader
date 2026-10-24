/* SPDX-License-Identifier: MIT */
/* Independent installed-package consumer. It includes only the installed public
   headers and drives both phases the way a host would: the download on a
   "network worker" step that never touches the library, then the import on the
   "SDK owner" step. Parameters come from a UTF-8 key=value spec file so that
   Unicode names do not depend on the Windows command-line code page. */
#ifndef _WIN32
#define _POSIX_C_SOURCE 200809L
#endif
#include <reader_cloud_import.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#ifdef _WIN32
#include <windows.h>
#endif

#define MAX_KEYS 64

static char *keys[MAX_KEYS], *values[MAX_KEYS];
static int key_count;

static FILE *open_utf8(const char *path, const char *mode) {
#ifdef _WIN32
  wchar_t wide[4096], wmode[8];
  if (MultiByteToWideChar(CP_UTF8, MB_ERR_INVALID_CHARS, path, -1, wide, 4096) <= 0) return NULL;
  if (MultiByteToWideChar(CP_UTF8, 0, mode, -1, wmode, 8) <= 0) return NULL;
  return _wfopen(wide, wmode);
#else
  return fopen(path, mode);
#endif
}

static const char *get(const char *key, const char *fallback) {
  int i;
  for (i = 0; i < key_count; i++)
    if (!strcmp(keys[i], key)) return values[i];
  return fallback;
}

static unsigned long long get_u64(const char *key, unsigned long long fallback) {
  const char *text = get(key, NULL);
  return text && *text ? strtoull(text, NULL, 10) : fallback;
}

static int read_spec(const char *path) {
  FILE *file = open_utf8(path, "rb");
  char line[16384];
  if (!file) return -1;
  while (fgets(line, sizeof(line), file) && key_count < MAX_KEYS) {
    char *eq = strchr(line, '=');
    size_t n = strlen(line);
    while (n && (line[n - 1] == '\n' || line[n - 1] == '\r')) line[--n] = 0;
    if (!eq) continue;
    *eq = 0;
    keys[key_count] = strdup(line);
    values[key_count] = strdup(eq + 1);
    key_count++;
  }
  fclose(file);
  return 0;
}

static void quoted(const char *text) {
  const unsigned char *p = (const unsigned char *)text;
  putchar('"');
  for (; *p; p++) {
    if (*p == '"' || *p == '\\') printf("\\%c", *p);
    else if (*p < 32) printf("\\u%04x", *p);
    else putchar(*p);
  }
  putchar('"');
}

static exr_format parse_format(const char *name) {
  if (!strcmp(name, "TXT")) return EXR_TXT;
  if (!strcmp(name, "HTML")) return EXR_HTML;
  if (!strcmp(name, "FB2")) return EXR_FB2;
  if (!strcmp(name, "EPUB")) return EXR_EPUB;
  if (!strcmp(name, "DOCX")) return EXR_DOCX;
  if (!strcmp(name, "RTF")) return EXR_RTF;
  if (!strcmp(name, "MOBI")) return EXR_MOBI;
  if (!strcmp(name, "PDF")) return EXR_PDF;
  if (!strcmp(name, "CBZ")) return EXR_CBZ;
  return EXR_CUSTOM;
}

typedef struct {
  int phase; /* 0 download, 1 import */
  int cancel_now;
  unsigned long long net_bytes;     /* cancel once this many bytes arrived */
  unsigned long long import_poll;   /* cancel from this import poll on; 0 = never */
  unsigned long long received, polls;
} state_t;

static int cancelled(void *context) {
  state_t *s = context;
  if (s->phase == 1) {
    s->polls++;
    return s->cancel_now || (s->import_poll && s->polls >= s->import_poll);
  }
  return s->cancel_now || s->received >= s->net_bytes;
}

static void progress(void *context, uint64_t received) { ((state_t *)context)->received = received; }

static const char *base_name(const char *path) {
  const char *p, *base = path;
  for (p = path; *p; p++)
    if (*p == '/' || *p == '\\') base = p + 1;
  return base;
}

static int file_exists(const char *path) {
  FILE *file = open_utf8(path, "rb");
  if (!file) return 0;
  fclose(file);
  return 1;
}

static int tamper(const char *path, const char *mode) {
  FILE *file;
  long size;
  unsigned char byte;
  if (!strcmp(mode, "delete")) {
#ifdef _WIN32
    wchar_t wide[4096];
    if (MultiByteToWideChar(CP_UTF8, MB_ERR_INVALID_CHARS, path, -1, wide, 4096) <= 0) return -1;
    return _wremove(wide);
#else
    return remove(path);
#endif
  }
  file = open_utf8(path, "r+b");
  if (!file) return -1;
  fseek(file, 0, SEEK_END);
  size = ftell(file);
  if (!strcmp(mode, "flip")) {
    fseek(file, size / 2, SEEK_SET);
    if (fread(&byte, 1, 1, file) != 1) { fclose(file); return -1; }
    byte = (unsigned char)(byte ^ 0x5a);
    fseek(file, size / 2, SEEK_SET);
    fwrite(&byte, 1, 1, file);
  } else if (!strcmp(mode, "append")) {
    byte = 0;
    fwrite(&byte, 1, 1, file);
  } else if (!strcmp(mode, "truncate")) {
    /* rewrite a shorter copy through a second handle */
    char *copy = malloc((size_t)size);
    FILE *out;
    if (!copy) { fclose(file); return -1; }
    fseek(file, 0, SEEK_SET);
    if (fread(copy, 1, (size_t)size, file) != (size_t)size) { free(copy); fclose(file); return -1; }
    fclose(file);
    out = open_utf8(path, "wb");
    if (!out) { free(copy); return -1; }
    fwrite(copy, 1, (size_t)size / 2, out);
    fclose(out);
    free(copy);
    return 0;
  }
  fclose(file);
  return 0;
}

static void emit_error(const char *prefix, const reader_cloud_error *error, reader_cloud_status status) {
  printf("\"%s_status\":\"%s\",\"%s_webdav\":%d,\"%s_http\":%d,\"%s_sdk\":%d,\"%s_message\":",
      prefix, reader_cloud_status_name(status), prefix, (int)error->webdav_code, prefix,
      error->http_status, prefix, (int)error->sdk_code, prefix);
  quoted(error->message);
}

static int run_transfer(void) {
  state_t state;
  exr_webdav_config config;
  exr_webdav_error dav_error;
  exr_webdav_client *client = NULL;
  exr_webdav_status dav_status;
  reader_cloud_request request;
  reader_cloud_staged *staged = NULL;
  reader_cloud_error error;
  reader_cloud_status status;
  reader_cloud_import_options options;
  reader_cloud_import_result result;
  exr_library *library = NULL;
  exr_error sdk_error;
  char path[4096];
  int do_import = (int)get_u64("import", 1);

  memset(&state, 0, sizeof(state));
  state.net_bytes = get_u64("cancel_net", ~0ull);
  state.cancel_now = (int)get_u64("cancel_before", 0);
  state.import_poll = get_u64("cancel_import_poll", 0);
  memset(&config, 0, sizeof(config));
  memset(&dav_error, 0, sizeof(dav_error));
  config.root_url = get("root", "");
  config.authorization = get("auth", "");
  config.max_download_bytes = get_u64("client_max", 0);
  config.timeout_ms = (unsigned)get_u64("timeout", 0);
  dav_status = exr_webdav_create(&config, &client, &dav_error);
  printf("{\"create\":%d", (int)dav_status);
  if (dav_status != EXR_DAV_OK) {
    printf(",\"create_message\":");
    quoted(dav_error.message);
    printf("}\n");
    return 0;
  }

  reader_cloud_request_init(&request);
  request.resource = get("resource", "");
  request.display_name = get("name", "");
  request.format = parse_format(get("format", ""));
  request.expected_bytes = get_u64("expected", 0);
  request.max_bytes = get_u64("max", 0);
  request.staging_dir = get("staging", "");
  request.control.cancelled = cancelled;
  request.control.progress = progress;
  request.control.context = &state;
  memset(&error, 0, sizeof(error));
  status = reader_cloud_download(client, &request, &staged, &error);
  printf(",");
  emit_error("download", &error, status);
  printf(",\"staged\":%d", staged != NULL);
  if (staged) {
    printf(",\"staged_bytes\":%llu,\"staged_sha256\":\"%s\",\"staged_name\":",
        (unsigned long long)reader_cloud_staged_bytes(staged), reader_cloud_staged_sha256(staged));
    quoted(reader_cloud_staged_name(staged));
    snprintf(path, sizeof(path), "%s", reader_cloud_staged_path(staged));
    printf(",\"staged_file\":");
    quoted(base_name(path));
  }
  /* The client is released before the SDK phase: the two phases share nothing. */
  exr_webdav_free(client);

  if (staged && !strcmp(get("tamper", ""), "discard")) {
    snprintf(path, sizeof(path), "%s", reader_cloud_staged_path(staged));
    reader_cloud_staged_discard(&staged);
    printf(",\"discarded\":1,\"discard_nulled\":%d,\"file_after_discard\":%d", staged == NULL, file_exists(path));
    do_import = 0;
  }
  if (staged && do_import) {
    if (strcmp(get("tamper", ""), "") != 0) {
      snprintf(path, sizeof(path), "%s", reader_cloud_staged_path(staged));
      printf(",\"tamper_result\":%d", tamper(path, get("tamper", "")));
    }
    snprintf(path, sizeof(path), "%s", reader_cloud_staged_path(staged));
    memset(&sdk_error, 0, sizeof(sdk_error));
    if (exr_library_open(get("library", ""), &library, &sdk_error) != EXR_OK) {
      printf(",\"library_open\":0}\n");
      return 1;
    }
    reader_cloud_import_options_init(&options);
    options.title = *get("title", "") ? get("title", "") : NULL;
    options.max_input_bytes = get_u64("max_input", 0);
    options.control.cancelled = cancelled;
    options.control.context = &state;
    state.phase = 1;
    memset(&result, 0, sizeof(result));
    result.struct_size = sizeof(result);
    memset(&error, 0, sizeof(error));
    status = reader_cloud_import(library, &staged, &options, &result, &error);
    printf(",");
    emit_error("import", &error, status);
    printf(",\"committed\":%d,\"created\":%d,\"book_id\":%lld,\"staging_removed\":%d,\"consumed\":%d,"
        "\"staging_file_exists\":%d,\"polls\":%llu",
        result.committed, result.created, (long long)result.book_id, result.staging_removed,
        staged == NULL, file_exists(path), state.polls);
    exr_library_close(library);
  }
  if (staged) reader_cloud_staged_discard(&staged);
  printf("}\n");
  return 0;
}

static int run_readback(void) {
  exr_library *library = NULL;
  exr_error error;
  exr_book *books = NULL;
  size_t count = 0, i;
  const char *out = get("out", ".");
  memset(&error, 0, sizeof(error));
  if (exr_library_open(get("library", ""), &library, &error) != EXR_OK ||
      exr_library_books(library, NULL, &books, &count, &error) != EXR_OK) {
    printf("{\"ok\":0}\n");
    return 1;
  }
  printf("{\"ok\":1,\"books\":[");
  for (i = 0; i < count; i++) {
    exr_source source;
    char name[4096];
    FILE *file;
    unsigned char *buffer = malloc(65536);
    uint64_t at = 0;
    int ok = 0;
    memset(&source, 0, sizeof(source));
    if (i) putchar(',');
    printf("{\"id\":%lld,\"format\":%d,\"title\":", (long long)books[i].id, (int)books[i].format);
    quoted(books[i].title ? books[i].title : "");
    snprintf(name, sizeof(name), "%s/book-%lld.bin", out, (long long)books[i].id);
    if (buffer && exr_library_source(library, books[i].id, &source, &error) == EXR_OK) {
      file = open_utf8(name, "wb");
      ok = file != NULL;
      while (ok && at < source.size) {
        size_t want = source.size - at < 65536 ? (size_t)(source.size - at) : 65536, got;
        got = source.read_at(source.context, at, buffer, want);
        if (got != want || fwrite(buffer, 1, got, file) != got) ok = 0;
        at += got;
      }
      if (file) fclose(file);
      printf(",\"bytes\":%llu", (unsigned long long)source.size);
      source.release(source.context);
    }
    printf(",\"read_ok\":%d}", ok);
    free(buffer);
  }
  printf("]}\n");
  exr_books_free(books, count);
  exr_library_close(library);
  return 0;
}

/* Directory browsing is the existing exr_webdav_list; the host keeps resource,
   display_name and the listed length and hands them to the download phase. */
static int run_list(void) {
  exr_webdav_config config;
  exr_webdav_error error;
  exr_webdav_client *client = NULL;
  exr_webdav_listing listing;
  exr_webdav_status status;
  size_t i;
  memset(&config, 0, sizeof(config));
  memset(&error, 0, sizeof(error));
  memset(&listing, 0, sizeof(listing));
  config.root_url = get("root", "");
  config.authorization = get("auth", "");
  status = exr_webdav_create(&config, &client, &error);
  if (status == EXR_DAV_OK)
    status = exr_webdav_list(client, get("resource", ""), NULL, &listing, &error);
  printf("{\"list_status\":%d,\"entries\":[", (int)status);
  for (i = 0; i < listing.count; i++) {
    const exr_webdav_entry *e = &listing.entries[i];
    if (i) putchar(',');
    printf("{\"resource\":");
    quoted(e->resource);
    printf(",\"display_name\":");
    quoted(e->display_name);
    printf(",\"bytes\":%llu,\"has_size\":%d,\"collection\":%d}", (unsigned long long)e->bytes,
        e->has_size, e->collection);
  }
  printf("]}\n");
  exr_webdav_listing_free(&listing);
  exr_webdav_free(client);
  return 0;
}

int main(int argc, char **argv) {
  if (argc != 2 || read_spec(argv[1]) != 0) return 2;
  if (!strcmp(get("cmd", ""), "list")) return run_list();
  if (!strcmp(get("cmd", ""), "transfer")) return run_transfer();
  if (!strcmp(get("cmd", ""), "readback")) return run_readback();
  if (!strcmp(get("cmd", ""), "selftest")) {
    reader_cloud_request r;
    reader_cloud_request_init(&r);
    printf("{\"selftest\":%d}\n", r.struct_size == sizeof(r) &&
        reader_cloud_format_from_name("X.EpUb") == EXR_EPUB &&
        reader_cloud_format_from_name("x.exe") == EXR_CUSTOM);
    return 0;
  }
  return 2;
}
