/* SPDX-License-Identifier: MIT
 * S10 desktop transfer entry: parse a real text/uri-list payload (exactly what
 * a GTK drop or clipboard read delivers), hand the first real file to the
 * installed SDK sideload import, and export the stored original again so an
 * independent reader can compare it with the file the user dropped.
 */
#include <exr/base.h>
#include <exr/library.h>
#include <exr_desktop_drop.h>
#include <exr_sideload.h>

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define S10_MAX_PAYLOAD (1024u * 1024u)

static unsigned char *read_all(const char *path, size_t *size) {
  FILE *file = fopen(path, "rb");
  unsigned char *buffer;
  long length;
  size_t read;
  *size = 0;
  if (!file) return NULL;
  if (fseek(file, 0, SEEK_END) || (length = ftell(file)) < 0 || (size_t)length > S10_MAX_PAYLOAD ||
      fseek(file, 0, SEEK_SET)) {
    fclose(file);
    return NULL;
  }
  buffer = (unsigned char *)malloc((size_t)length + 1u);
  if (!buffer) {
    fclose(file);
    return NULL;
  }
  read = fread(buffer, 1, (size_t)length, file);
  fclose(file);
  if (read != (size_t)length) {
    free(buffer);
    return NULL;
  }
  buffer[read] = 0;
  *size = read;
  return buffer;
}

static void write_json_string(FILE *out, const char *value) {
  const unsigned char *cursor = (const unsigned char *)value;
  if (!value) {
    fputs("null", out);
    return;
  }
  fputc('"', out);
  for (; *cursor; cursor++) {
    if (*cursor == '"' || *cursor == '\\') fprintf(out, "\\%c", *cursor);
    else if (*cursor < 0x20) fprintf(out, "\\u%04x", *cursor);
    else fputc(*cursor, out);
  }
  fputc('"', out);
}

static exr_format format_of(const char *path) {
  const char *dot = strrchr(path, '.');
  if (dot) {
    if (!strcmp(dot, ".epub")) return EXR_EPUB;
    if (!strcmp(dot, ".txt")) return EXR_TXT;
    if (!strcmp(dot, ".pdf")) return EXR_PDF;
    if (!strcmp(dot, ".cbz")) return EXR_CBZ;
  }
  return EXR_TXT;
}

int main(int argc, char **argv) {
  const char *payload_path = NULL;
  const char *library_path = NULL;
  const char *export_path = NULL;
  const char *report_path = NULL;
  const char *title = "S10 transfer";
  unsigned char *payload = NULL;
  size_t payload_size = 0, index = 0;
  exr_drop_request *request = NULL;
  exr_drop_request_info info;
  exr_drop_status drop_status;
  exr_library *library = NULL;
  exr_error error;
  exr_sideload_options options;
  exr_sideload_result result;
  exr_status import_status = EXR_ARGUMENT, export_status = EXR_ARGUMENT;
  const char *selected = NULL;
  uint64_t written = 0;
  FILE *report = NULL;
  int code = 1;
  int i;

  for (i = 1; i < argc; i++) {
    if (!strcmp(argv[i], "--payload") && i + 1 < argc) payload_path = argv[++i];
    else if (!strcmp(argv[i], "--library") && i + 1 < argc) library_path = argv[++i];
    else if (!strcmp(argv[i], "--export") && i + 1 < argc) export_path = argv[++i];
    else if (!strcmp(argv[i], "--report") && i + 1 < argc) report_path = argv[++i];
    else if (!strcmp(argv[i], "--title") && i + 1 < argc) title = argv[++i];
  }
  if (!payload_path || !library_path || !export_path || !report_path) {
    fprintf(stderr, "usage: entry_check --payload FILE --library PATH --export FILE --report FILE\n");
    return 2;
  }
  memset(&error, 0, sizeof(error));
  memset(&info, 0, sizeof(info));
  info.struct_size = sizeof(info);
  memset(&options, 0, sizeof(options));
  options.struct_size = sizeof(options);
  memset(&result, 0, sizeof(result));
  result.struct_size = sizeof(result);

  payload = read_all(payload_path, &payload_size);
  if (!payload) {
    fprintf(stderr, "cannot read payload %s\n", payload_path);
    return 2;
  }
  drop_status = exr_drop_request_from_uri_list((const char *)payload, payload_size,
                                              EXR_DROP_ORIGIN_TEXT, NULL, &request);
  if (drop_status == EXR_DROP_OK && exr_drop_request_get_info(request, &info) != EXR_DROP_OK) {
    drop_status = EXR_DROP_ARGUMENT;
    exr_drop_request_release(request);
    request = NULL;
  }
  for (index = 0; request && index < info.item_count; index++) {
    exr_drop_item item;
    memset(&item, 0, sizeof(item));
    item.struct_size = sizeof(item);
    if (exr_drop_request_get_item(request, index, &item) != EXR_DROP_OK) continue;
    if (item.status == EXR_DROP_ITEM_FILE && !selected) selected = item.path;
  }
  if (selected && exr_library_open(library_path, &library, &error) == EXR_OK) {
    import_status = exr_sideload_import_file(library, format_of(selected), selected, title,
                                             &options, &result, &error);
    if (import_status == EXR_OK) {
      export_status = exr_sideload_export_original(library, result.book_id, export_path,
                                                   &options, &written, &error);
      code = (export_status == EXR_OK) ? 0 : 1;
    }
  }

  report = fopen(report_path, "wb");
  if (report) {
    fputs("{\n  \"schema\": 1,\n  \"tool\": \"s10-desktop-entry\",\n", report);
    fprintf(report, "  \"payload_bytes\": %zu,\n", payload_size);
    fprintf(report, "  \"drop_status\": %d,\n", (int)drop_status);
    fprintf(report, "  \"drop_status_name\": ");
    write_json_string(report, exr_drop_status_name(drop_status));
    fprintf(report, ",\n  \"item_count\": %zu,\n  \"file_count\": %zu,\n  \"items\": [\n",
            info.item_count, info.file_count);
    for (index = 0; request && index < info.item_count; index++) {
      exr_drop_item item;
      memset(&item, 0, sizeof(item));
      item.struct_size = sizeof(item);
      if (exr_drop_request_get_item(request, index, &item) != EXR_DROP_OK) continue;
      fputs("    {\"index\": ", report);
      fprintf(report, "%zu, \"status\": %d, \"status_name\": ", index, (int)item.status);
      write_json_string(report, exr_drop_item_status_name(item.status));
      fputs(", \"path\": ", report);
      write_json_string(report, item.path);
      fputs("},\n", report);
    }
    fputs("  ],\n  \"selected\": ", report);
    write_json_string(report, selected);
    fprintf(report, ",\n  \"import_status\": %d,\n  \"book_id\": %lld,\n  \"created\": %d,\n",
            (int)import_status, (long long)result.book_id, result.created);
    fprintf(report, "  \"export_status\": %d,\n  \"bytes_written\": %llu,\n  \"export_path\": ",
            (int)export_status, (unsigned long long)written);
    write_json_string(report, export_path);
    fputs(",\n  \"error\": ", report);
    write_json_string(report, error.message);
    fputs("\n}\n", report);
    fclose(report);
  } else {
    fprintf(stderr, "cannot write report %s\n", report_path);
    code = 2;
  }

  if (library) exr_library_close(library);
  exr_drop_request_release(request);
  free(payload);
  return code;
}
