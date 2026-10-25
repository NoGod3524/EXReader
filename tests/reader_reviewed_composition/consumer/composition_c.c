#include <reader_cloud_import.h>
#include <reader_bulk.h>
#include <reader_link_policy.h>
#include <reader_jump_history.h>
#include <reader_keyboard_actions.h>
#include <reader_book_information.h>
#include <reader_sync_view.h>
#include <reader_account_profiles.h>
/* SPDX-License-Identifier: MIT */
/* Installed-prefix composition consumer compiled as C11.
   Same single prefix and the same exported targets as the C++ consumer: this
   translation unit includes every installed public header and runs the
   C-visible product chain (typed book command -> import -> search capture ->
   reading v2 encode -> revision -> second SDK resolve). The C++-implemented
   packages are reached through their C ABI; this file contains no C++. */
#include <catalog.h>
#include <exreader.h>
#include <exr/document.h>
#include <exr/library.h>
#include <exr_credentials.h>
#include <exr_sideload.h>
#include <exr_webdav.h>
#include <reader_batch_import.h>
#include <reader_commands.h>
#include <reader_metadata.h>
#include <reader_preferences.h>
#include <reader_projection.h>
#include <reader_reading_state.h>
#include <reader_revisions.h>
#include <reader_search.h>
#include <reader_session.h>
#include <reader_sync.h>

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static FILE *report;
static size_t failures;
static int first_entry = 1;

static void escape(const char *text, char *out, size_t capacity) {
  size_t written = 0;
  for (; text && *text && written + 8 < capacity; ++text) {
    unsigned char value = (unsigned char)*text;
    if (value == '"' || value == '\\') { out[written++] = '\\'; out[written++] = (char)value; }
    else if (value < 0x20) { written += (size_t)snprintf(out + written, capacity - written, "\\u%04x", value); }
    else out[written++] = (char)value;
  }
  out[written] = 0;
}

static void check(int ok, const char *name, const char *detail) {
  char safe_name[256], safe_detail[512];
  escape(name, safe_name, sizeof safe_name);
  escape(detail ? detail : "", safe_detail, sizeof safe_detail);
  if (!ok) { ++failures; fprintf(stderr, "FAIL %s %s\n", name, detail ? detail : ""); }
  if (!first_entry) fprintf(report, ",");
  first_entry = 0;
  fprintf(report, "{\"name\":\"%s\",\"pass\":%s,\"detail\":\"%s\"}", safe_name, ok ? "true" : "false",
          safe_detail);
}

struct entity_scan {
  char key[257];
  size_t count;
};

static int collect_entity(void *context, const reader_revision_entity_row *row) {
  struct entity_scan *scan = (struct entity_scan *)context;
  snprintf(scan->key, sizeof scan->key, "%s", row->entity_key);
  ++scan->count;
  return 0;
}

static char *slurp(const char *path, size_t *size) {
  FILE *input = fopen(path, "rb");
  char *data;
  long length;
  if (!input) return NULL;
  if (fseek(input, 0, SEEK_END) != 0) { fclose(input); return NULL; }
  length = ftell(input);
  if (length <= 0 || fseek(input, 0, SEEK_SET) != 0) { fclose(input); return NULL; }
  data = (char *)malloc((size_t)length);
  if (!data) { fclose(input); return NULL; }
  if (fread(data, 1, (size_t)length, input) != (size_t)length) { free(data); fclose(input); return NULL; }
  fclose(input);
  *size = (size_t)length;
  return data;
}

int main(int argc, char **argv) {
  const char *fixtures = NULL, *work = NULL, *report_path = NULL, *digest = NULL;
  char book_key[96];
  char parser_version[160];
  char path[4096];
  char source[4096];
  char *data = NULL;
  size_t data_size = 0;
  int index;
  int exit_code;
  exr_library *library = NULL, *receiver = NULL;
  exr_document *document = NULL, *receiver_document = NULL;
  reader_revisions *store = NULL;
  reader_catalog *catalog = NULL;
  reader_search *search = NULL;
  reader_revision_error revision_error;
  reader_catalog_error catalog_error;
  reader_search_error search_error;
  exr_error sdk_error;
  size_t text_size = 0, receiver_size = 0;
  const char *text = NULL;

  for (index = 1; index + 1 < argc; index += 2) {
    if (!strcmp(argv[index], "--fixtures")) fixtures = argv[index + 1];
    else if (!strcmp(argv[index], "--work")) work = argv[index + 1];
    else if (!strcmp(argv[index], "--report")) report_path = argv[index + 1];
    else if (!strcmp(argv[index], "--sha")) {
      const char *value = argv[index + 1];
      const char *equal = strchr(value, '=');
      digest = equal ? equal + 1 : value;
    }
  }
  if (!fixtures || !work || !report_path || !digest) {
    fprintf(stderr, "usage: composition-c --fixtures DIR --work DIR --report FILE --sha txt=<hex>\n");
    return 2;
  }
  snprintf(book_key, sizeof book_key, "txt:%s", digest);
  snprintf(parser_version, sizeof parser_version, "exreader-sdk-%s", exr_version());
  report = fopen(report_path, "wb");
  if (!report) return 2;
  fprintf(report, "{\"probe\":\"composition-c\",\"checks\":[");

  /* 1. Secure storage: validation and allocation only, no service contact. */
  {
    exr_credentials_store *credentials = NULL;
    exr_credentials_status status = exr_credentials_open("org.exreader.composition", &credentials);
    check(status == EXR_CRED_OK && credentials != NULL, "C credentials open a namespace",
          exr_credentials_status_name(status));
    if (credentials) {
      unsigned char buffer[EXR_CREDENTIALS_SECRET_MAX];
      size_t length = 1;
      memset(buffer, 0, sizeof buffer);
      status = exr_credentials_get(credentials, "00000000-0000-4000-8000-000000000000", buffer,
                                   sizeof buffer, &length);
      check(status == EXR_CRED_NOT_FOUND || status == EXR_CRED_UNAVAILABLE,
            "C credentials never invent a record", exr_credentials_status_name(status));
      check(length == 0, "C credentials report no missing length", "");
      exr_credentials_wipe(buffer, sizeof buffer);
      exr_credentials_close(credentials);
    }
  }

  /* 2. Preferences: a real device document through the C API. */
  {
    reader_preferences_error error;
    reader_preferences preferences = reader_preferences_defaults();
    reader_preferences loaded = reader_preferences_defaults();
    memset(&error, 0, sizeof error);
    check(reader_preferences_validate(&preferences, &error) == READER_PREFERENCES_OK,
          "C preferences validate defaults", error.message);
    preferences.font_size = 17.0f;
    snprintf(path, sizeof path, "%s/settings-c.json", work);
    check(reader_preferences_save(&preferences, path, NULL, &error) == READER_PREFERENCES_OK,
          "C preferences save a document", error.message);
    check(reader_preferences_load(path, &loaded, NULL, &error) == READER_PREFERENCES_OK,
          "C preferences load their own document", error.message);
    check(loaded.font_size == preferences.font_size, "C preferences round-trip a value", "");
    check(reader_preferences_abi_version() == READER_PREFERENCES_ABI_VERSION,
          "C preferences report their ABI", "");
  }

  /* 3. One product provider and two independent SDK libraries. */
  snprintf(path, sizeof path, "%s/c-library.sqlite", work);
  memset(&sdk_error, 0, sizeof sdk_error);
  check(exr_library_open(path, &library, &sdk_error) == EXR_OK, "C SDK library opens", sdk_error.message);
  snprintf(path, sizeof path, "%s/c-receiver.sqlite", work);
  memset(&sdk_error, 0, sizeof sdk_error);
  check(exr_library_open(path, &receiver, &sdk_error) == EXR_OK, "C receiver library opens", sdk_error.message);
  snprintf(path, sizeof path, "%s/c-product.sqlite", work);
  memset(&revision_error, 0, sizeof revision_error);
  check(reader_revisions_open(path, &store, &revision_error) == READER_REV_OK,
        "C product revision store opens", revision_error.message);
  memset(&catalog_error, 0, sizeof catalog_error);
  check(reader_catalog_open(path, &catalog, &catalog_error) == 0, "C product catalog opens",
        catalog_error.message);

  /* 4. Typed book command, then the imported original. */
  snprintf(source, sizeof source, "%s/sample.txt", fixtures);
  data = slurp(source, &data_size);
  check(data != NULL && data_size > 0, "C consumer reads the fixture", source);
  if (library && data) {
    int64_t book_id = 0;
    memset(&sdk_error, 0, sizeof sdk_error);
    check(exr_library_import(library, EXR_TXT, data, data_size, "c-sample", &book_id, &sdk_error) == EXR_OK &&
              book_id > 0,
          "C library imports the original", sdk_error.message);
    if (book_id > 0) {
      reader_book_command command;
      reader_command_context context;
      reader_command_result result;
      reader_command_error error;
      memset(&command, 0, sizeof command);
      command.operation = READER_COMMAND_PUT;
      command.book_key = book_key;
      command.format = "txt";
      command.source_sha256 = digest;
      command.title = "C composed sample";
      command.author = "composition";
      command.sort_title = "C composed sample";
      command.source_bytes = (uint64_t)data_size;
      memset(&context, 0, sizeof context);
      context.store = store;
      memset(&result, 0, sizeof result);
      memset(&error, 0, sizeof error);
      check(store && reader_command_apply_book(&context, &command, &result, &error) == READER_COMMAND_OK &&
                result.created && result.applied,
            "C typed book command commits its transaction", error.message);
      memset(&sdk_error, 0, sizeof sdk_error);
      check(exr_library_document(library, book_id, &document, &sdk_error) == EXR_OK,
            "C SDK exposes the imported document", sdk_error.message);
    }
    if (receiver) {
      int64_t receiver_id = 0;
      memset(&sdk_error, 0, sizeof sdk_error);
      check(exr_library_import(receiver, EXR_TXT, data, data_size, "c-sample", &receiver_id, &sdk_error) ==
                EXR_OK,
            "C receiver imports the same bytes", sdk_error.message);
      if (receiver_id > 0)
        check(exr_library_document(receiver, receiver_id, &receiver_document, &sdk_error) == EXR_OK,
              "C receiver exposes its document", sdk_error.message);
    }
  }

  /* 5. Search capture -> reading v2 encode -> revision -> decode -> resolve. */
  if (document && store) {
    const char query[] = "\xE5\xBC\x95\xE6\x93\x8E\xE6\x8E\x8C\xE6\x8E\xA7";
    reader_search_options options;
    reader_search_result result;
    text = exr_document_text(document, &text_size);
    check(text != NULL && text_size > 0, "C SDK returns the reflow text", "");
    memset(&options, 0, sizeof options);
    options.struct_size = sizeof options;
    options.source_key = book_key;
    memset(&search_error, 0, sizeof search_error);
    check(reader_search_open_reflow(document, query, sizeof query - 1, &options, &search, &search_error) ==
              READER_SEARCH_OK,
          "C search opens over the document", search_error.message);
    memset(&result, 0, sizeof result);
    if (search && reader_search_next(search, 8, &result, &search_error) == READER_SEARCH_OK && result.count >= 1) {
      char *literal = text ? strstr(text, query) : NULL;
      check(literal != NULL && result.hits[0].start == (size_t)(literal - text),
            "C search returns the exact literal offset", "");
      {
        reader_rs_capture capture;
        reader_rs_envelope envelope;
        reader_rs_error reading_error;
        reader_revision_info info;
        char revision[33];
        char annotation_id[33] = {0};
        char *wire = NULL;
        size_t bytes = 0;
        int created = 0;
        memset(&capture, 0, sizeof capture);
        capture.mode = READER_RS_REFLOW_GLOBAL;
        capture.anchor = &result.hits[0].anchor;
        check(reader_rs_classify(&capture) == READER_RS_GAP_NONE, "C search capture is representable", "");
        memset(&revision_error, 0, sizeof revision_error);
        check(reader_revision_new_id(revision, &revision_error) == READER_REV_OK, "C revision id allocates",
              revision_error.message);
        check(reader_revision_new_id(annotation_id, &revision_error) == READER_REV_OK,
              "C annotation id allocates", revision_error.message);
        memset(&envelope, 0, sizeof envelope);
        envelope.revision_id = revision;
        envelope.operation = "put";
        envelope.entity_kind = "annotation";
        envelope.book_key = book_key;
        envelope.annotation_id = annotation_id;
        envelope.note_text = "c-composition";
        envelope.parser_version = parser_version;
        memset(&reading_error, 0, sizeof reading_error);
        check(reader_rs_encode_v2(store, &envelope, &capture, 0, &wire, &bytes, &reading_error) == READER_RS_OK,
              "C reading v2 encodes the capture", reading_error.message);
        memset(&info, 0, sizeof info);
        check(wire && reader_revision_local_reading(store, wire, bytes, NULL, 0, &info, &created,
                                                    &revision_error) == READER_REV_OK && created,
              "C reading revision commits", revision_error.message);
        if (wire) reader_rs_free(wire);
      }
    } else {
      check(0, "C search returns a batch", search_error.message);
    }
    reader_search_result_free(&result);
  }

  /* 6. WebDAV and session symbols are live in this C link graph. */
  {
    exr_webdav_config configuration;
    exr_webdav_client *client = NULL;
    exr_webdav_error error;
    reader_session_config session;
    reader_session *handle = NULL;
    memset(&configuration, 0, sizeof configuration);
    configuration.root_url = "http://127.0.0.1:9/insecure/";
    memset(&error, 0, sizeof error);
    check(exr_webdav_create(&configuration, &client, &error) == EXR_DAV_ARGUMENT && client == NULL,
          "C WebDAV refuses a non-TLS root", error.message);
    memset(&session, 0, sizeof session);
    session.product_path = "";
    session.account_id = "";
    session.dav.root_url = configuration.root_url;
    check(reader_session_create(&session, &handle) == READER_SESSION_ARGUMENT && handle == NULL,
          "C session refuses an unbounded configuration", "");
  }

  /* 7. Second SDK resolves the retained selector. */
  if (receiver_document && store && text) {
    struct entity_scan scan;
    reader_revision_info info;
    reader_revision_selection selection;
    char *retained = NULL;
    size_t retained_bytes = 0;
    memset(&scan, 0, sizeof scan);
    memset(&info, 0, sizeof info);
    memset(&selection, 0, sizeof selection);
    check(reader_revision_entities_page(store, "annotation", NULL, 1, 10, collect_entity, &scan,
                                        &revision_error) == READER_REV_OK && scan.count == 1,
          "C product retains exactly one annotation entity", revision_error.message);
    if (scan.count == 1 &&
        reader_revision_selected(store, "annotation", scan.key, &retained, &retained_bytes, &info, &selection,
                                 &revision_error) == READER_REV_OK &&
        selection.kind == READER_SELECTION_SAFE) {
      reader_rs_record record;
      reader_rs_error reading_error;
      exr_anchor_match match;
      memset(&record, 0, sizeof record);
      memset(&reading_error, 0, sizeof reading_error);
      memset(&match, 0, sizeof match);
      check(reader_rs_decode(store, retained, retained_bytes, &record, &reading_error) == READER_RS_OK,
            "C record decodes from retained bytes", reading_error.message);
      receiver_size = 0;
      (void)exr_document_text(receiver_document, &receiver_size);
      check(receiver_size == text_size, "C receiver text matches the sender", "");
      check(reader_rs_resolve_reflow(receiver_document, &record, NULL, &match, &reading_error) == READER_RS_OK &&
                match.state == EXR_ANCHOR_FOUND && match.start == record.start && match.end == record.end,
            "C receiver resolves the retained selector", reading_error.message);
      check(record.anchor_version == 2, "C record keeps anchor version 2", "");
      reader_rs_record_free(&record);
    } else {
      check(0, "C receiver reads the retained annotation", revision_error.message);
    }
    if (retained) reader_revision_bytes_free(retained);
  }

  fprintf(report, "],\"failures\":%zu}\n", failures);
  fclose(report);

  if (search) reader_search_close(&search, &search_error);
  if (document) exr_document_free(document);
  if (receiver_document) exr_document_free(receiver_document);
  if (catalog) reader_catalog_close(&catalog, &catalog_error);
  if (store) reader_revisions_close(&store, &revision_error);
  if (receiver) exr_library_close(receiver);
  if (library) exr_library_close(library);
  free(data);
  exit_code = failures ? 1 : 0;
  return exit_code;
}