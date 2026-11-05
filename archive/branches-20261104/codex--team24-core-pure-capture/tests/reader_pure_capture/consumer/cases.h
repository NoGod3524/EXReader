/* SPDX-License-Identifier: MIT */
/* The same public calls are compiled independently as C11 and C++17. */
#include <reader_reading_state.h>
#ifdef PURE_CAPTURE_TEST_ON
#include <reader_reading_state_capture_raw_candidate.h>
#endif
#include <exreader.h>
#include <sqlite3.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#ifdef __cplusplus
#define PURE_ZERO {}
#else
#define PURE_ZERO {0}
#endif

static FILE *report;
static size_t checks, failures;
static void require_ok(int value, const char *where) {
  if (!value) { fprintf(stderr, "setup failed: %s\n", where); exit(2); }
}
static void expect(const char *name, int pass) {
  if (checks++) fputs(",", report);
  fprintf(report, "{\"name\":\"%s\",\"pass\":%s}", name, pass ? "true" : "false");
  if (!pass) { failures++; fprintf(stderr, "FAIL %s\n", name); }
}
static void path_join(char *out, size_t capacity, const char *dir, const char *name) {
  int n = snprintf(out, capacity, "%s/%s", dir, name);
  require_ok(n >= 0 && (size_t)n < capacity, "path length");
}
static sqlite3_int64 row_count(const char *path, const char *table) {
  sqlite3 *db = NULL; sqlite3_stmt *q = NULL; sqlite3_int64 n; char sql[128];
  require_ok(sqlite3_open_v2(path, &db, SQLITE_OPEN_READONLY, NULL) == SQLITE_OK, "read product");
  snprintf(sql, sizeof(sql), "SELECT count(*) FROM %s", table);
  require_ok(sqlite3_prepare_v2(db, sql, -1, &q, NULL) == SQLITE_OK, "count product prepare");
  require_ok(sqlite3_step(q) == SQLITE_ROW, "count product step"); n = sqlite3_column_int64(q, 0);
  sqlite3_finalize(q); sqlite3_close(db); return n;
}
static reader_rs_status encode_capture(reader_revisions *store, const reader_rs_envelope *env,
    const reader_rs_capture *capture, unsigned version, size_t part, char **wire, size_t *bytes, reader_rs_error *error) {
#ifdef PURE_CAPTURE_TEST_ON
  return reader_rs_encode_capture_raw_candidate(store, env, capture, version, part, wire, bytes, error);
#else
  return version == 1 ? reader_rs_encode(store, env, capture, wire, bytes, error)
                     : reader_rs_encode_v2(store, env, capture, part, wire, bytes, error);
#endif
}
static reader_rs_status decode_capture(reader_revisions *store, const void *wire, size_t bytes,
    reader_rs_record *record, reader_rs_error *error) {
#ifdef PURE_CAPTURE_TEST_ON
  return reader_rs_decode_raw_v3(store, wire, bytes, record, error);
#else
  return reader_rs_decode(store, wire, bytes, record, error);
#endif
}
static int same_nullable(const char *a, const char *b, size_t n) {
  return (a == NULL) == (b == NULL) && (!a || !memcmp(a, b, n));
}
/* The old installed codec is an independent exact-byte reference for v1/v2. */
static void text_case(const char *name, reader_revisions *store, reader_revisions *legacy,
    const reader_rs_envelope *env, const reader_rs_capture *capture, unsigned version,
    size_t part, exr_document *doc, exr_publication *pub, exr_pager *pager) {
  char *wire = NULL, *reference = NULL; size_t bytes = 0, reference_bytes = 0;
  reader_rs_error error = PURE_ZERO; reader_rs_record record = PURE_ZERO; exr_anchor_match match = PURE_ZERO; char label[160];
  reader_rs_status status = encode_capture(store, env, capture, version, part, &wire, &bytes, &error);
  snprintf(label, sizeof(label), "%s-encode", name); expect(label, status == READER_RS_OK);
  require_ok(status == READER_RS_OK && wire != NULL, error.message);
  status = version == 1 ? reader_rs_encode(legacy, env, capture, &reference, &reference_bytes, &error)
                       : reader_rs_encode_v2(legacy, env, capture, part, &reference, &reference_bytes, &error);
  snprintf(label, sizeof(label), "%s-exact-legacy-wire", name);
  expect(label, status == READER_RS_OK && bytes == reference_bytes && !memcmp(wire, reference, bytes));
  reader_rs_free(reference);
  status = decode_capture(store, wire, bytes, &record, &error);
  snprintf(label, sizeof(label), "%s-version-and-selector", name);
  expect(label, status == READER_RS_OK && record.anchor_version == version &&
    record.mode == capture->mode && record.start == capture->anchor->start && record.end == capture->anchor->end &&
    record.exact_size == strlen(capture->anchor->exact) && !strcmp(record.exact, capture->anchor->exact) &&
    !strcmp(record.prefix, capture->anchor->prefix) && !strcmp(record.suffix, capture->anchor->suffix));
  require_ok(status == READER_RS_OK, "decode text");
  if (pub) {
    size_t route = SIZE_MAX;
    status = reader_rs_epub_record_part(pub, &record, &route, &error);
    require_ok(status == READER_RS_OK && route == part, "decoded EPUB route");
    status = reader_rs_resolve_epub(pub, pager, route, &record, NULL, &match, &error);
  } else status = reader_rs_resolve_reflow(doc, &record, NULL, &match, &error);
  snprintf(label, sizeof(label), "%s-real-sdk-resolve", name);
  expect(label, status == READER_RS_OK && match.state == EXR_ANCHOR_FOUND &&
    match.start == capture->anchor->start && match.end == capture->anchor->end);
  reader_rs_record_free(&record); reader_rs_free(wire);
}
#ifdef PURE_CAPTURE_TEST_ON
static void refused_case(const char *name, reader_revisions *store, const reader_rs_envelope *env,
    const reader_rs_capture *capture, unsigned version, size_t part) {
  char sentinel = 0, *wire = &sentinel; size_t bytes = 777; reader_rs_error error = PURE_ZERO;
  reader_rs_status status = reader_rs_encode_capture_raw_candidate(store, env, capture, version, part, &wire, &bytes, &error);
  expect(name, status != READER_RS_OK && wire == NULL && bytes == 0);
}
static void fixed_case(const char *name, reader_revisions *store, reader_revisions *legacy,
    const reader_rs_envelope *env, const exr_fixed_anchor *anchor, const exr_fixed_text *text, int resolve) {
  reader_rs_capture capture = PURE_ZERO; reader_rs_record record = PURE_ZERO; reader_rs_error error = PURE_ZERO;
  char *wire = NULL; size_t bytes = 0; char label[160]; exr_anchor_match match = PURE_ZERO; exr_error sdk_error = PURE_ZERO;
  capture.mode = READER_RS_FIXED_PAGE; capture.fixed = anchor;
  require_ok(encode_capture(store, env, &capture, 3, 0, &wire, &bytes, &error) == READER_RS_OK, error.message);
  require_ok(reader_rs_decode_raw_v3(store, wire, bytes, &record, &error) == READER_RS_OK, "decode fixed3");
  snprintf(label, sizeof(label), "%s-byte-and-null-identity", name);
  expect(label, record.anchor_version == 3 && record.mode == READER_RS_FIXED_PAGE &&
    record.start == anchor->start && record.end == anchor->end && !strcmp(record.page_id, anchor->page_id) &&
    record.exact_size == anchor->exact_size && record.prefix_size == anchor->prefix_size && record.suffix_size == anchor->suffix_size &&
    same_nullable(record.exact, anchor->exact, anchor->exact_size) &&
    same_nullable(record.prefix, anchor->prefix, anchor->prefix_size) && same_nullable(record.suffix, anchor->suffix, anchor->suffix_size));
  if (resolve) {
    exr_fixed_anchor decoded = PURE_ZERO; decoded.start = (size_t)record.start; decoded.end = (size_t)record.end;
    decoded.page_id = record.page_id; decoded.exact = record.exact; decoded.prefix = record.prefix; decoded.suffix = record.suffix;
    decoded.exact_size = record.exact_size; decoded.prefix_size = record.prefix_size; decoded.suffix_size = record.suffix_size;
    require_ok(exr_fixed_anchor_resolve(record.page_id, text, &decoded, NULL, &match, &sdk_error) == EXR_OK, "resolve fixed SDK");
    snprintf(label, sizeof(label), "%s-real-sdk-resolve", name);
    expect(label, match.state == EXR_ANCHOR_FOUND && match.start == anchor->start && match.end == anchor->end);
  }
  { reader_revision_info info = PURE_ZERO; reader_revision_error revision_error = PURE_ZERO;
    snprintf(label, sizeof(label), "%s-old-validator-refuses-v3", name);
    expect(label, reader_revision_validate(legacy, wire, bytes, NULL, &info, &revision_error) != READER_REV_OK); }
  reader_rs_record_free(&record); reader_rs_free(wire);
}
#endif
static int pure_capture_main(int argc, char **argv) {
  reader_revisions *legacy = NULL, *raw = NULL, *store; reader_revision_error revision_error = PURE_ZERO;
  exr_library *library = NULL; exr_document *doc = NULL; exr_publication *pub = NULL; exr_pager *pager = NULL;
  exr_font *font = NULL; exr_anchor range = PURE_ZERO, point = PURE_ZERO, epub_range = PURE_ZERO, epub_point = PURE_ZERO;
  exr_error sdk_error = PURE_ZERO; reader_rs_envelope env = PURE_ZERO; reader_rs_capture capture = PURE_ZERO;
  char legacy_path[2048], raw_path[2048], library_path[2048], fixture[2048]; int64_t book = 0;
  const exr_part *parts; size_t count = 0; exr_layout_config layout; exr_chapter_options chapter;
  sqlite3_int64 before_revisions, before_outbox;
  require_ok(argc == 5, "usage: fixtures work report font");
  report = fopen(argv[3], "wb"); require_ok(report != NULL, "open report");
  fprintf(report, "{\"language\":\"%s\",\"checks\":[", PURE_LANGUAGE);
  path_join(legacy_path, sizeof(legacy_path), argv[2], "legacy.sqlite");
  path_join(raw_path, sizeof(raw_path), argv[2], "raw.sqlite");
  path_join(library_path, sizeof(library_path), argv[2], "sdk.sqlite");
  require_ok(reader_revisions_open(legacy_path, &legacy, &revision_error) == READER_REV_OK, "open legacy store");
#ifdef PURE_CAPTURE_TEST_RAW
  require_ok(reader_revisions_open_raw_v3(raw_path, &raw, &revision_error) == READER_REV_OK, "open raw store");
#endif
#ifdef PURE_CAPTURE_TEST_ON
  store = raw;
#else
  store = legacy;
#endif
  before_revisions = row_count(legacy_path, "reader_revisions"); before_outbox = row_count(legacy_path, "reader_outbox");
  expect("initial-legacy-history-and-outbox-empty", before_revisions == 0 && before_outbox == 0);
#ifdef PURE_CAPTURE_TEST_RAW
  expect("initial-raw-history-and-outbox-empty", row_count(raw_path, "reader_revisions") == 0 && row_count(raw_path, "reader_outbox") == 0);
#endif
  require_ok(exr_library_open(library_path, &library, &sdk_error) == EXR_OK, "open SDK library");
  path_join(fixture, sizeof(fixture), argv[1], "book.txt");
  { FILE *input = fopen(fixture, "rb"); long length; unsigned char *data; exr_status status;
    require_ok(input != NULL, "open generated TXT fixture");
    require_ok(fseek(input, 0, SEEK_END) == 0, "seek TXT fixture"); length = ftell(input);
    require_ok(length > 0 && fseek(input, 0, SEEK_SET) == 0, "size TXT fixture");
    data = (unsigned char *)malloc((size_t)length); require_ok(data != NULL, "allocate TXT bytes");
    require_ok(fread(data, 1, (size_t)length, input) == (size_t)length, "read exact TXT bytes");
    require_ok(fclose(input) == 0, "close TXT fixture");
    status = exr_library_import(library, EXR_TXT, data, (size_t)length, "capture source", &book, &sdk_error);
    free(data);
    fprintf(stderr, "SDK import TXT status=%d message=%s\n", (int)status, sdk_error.message);
    require_ok(status == EXR_OK, "import TXT bytes"); }
  { exr_status status = exr_library_document(library, book, &doc, &sdk_error);
    fprintf(stderr, "SDK open TXT document status=%d message=%s\n", (int)status, sdk_error.message);
    require_ok(status == EXR_OK, "open TXT document"); }
  { size_t text_bytes = 0; const char *text = exr_document_text(doc, &text_bytes); const char *needle = strstr(text, "Unique context alpha");
    size_t at; require_ok(text_bytes > 0 && needle != NULL, "fixture phrase"); at = (size_t)(needle - text);
    require_ok(exr_anchor_create(doc, at, at + strlen("Unique context alpha"), &range, &sdk_error) == EXR_OK, "actual TXT range capture");
    require_ok(exr_anchor_create(doc, at, at, &point, &sdk_error) == EXR_OK, "actual TXT point capture"); }
  env.revision_id = "00000000000000000000000000000001"; env.operation = "put"; env.entity_kind = "progress";
  env.book_key = "txt:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"; env.parser_version = exr_version();
  capture.mode = READER_RS_REFLOW_GLOBAL; capture.anchor = &range;
  text_case("reflow-v1-range", store, legacy, &env, &capture, 1, 0, doc, NULL, NULL);
  capture.anchor = &point;
  text_case("reflow-v2-point", store, legacy, &env, &capture, 2, 0, doc, NULL, NULL);
  require_ok(exr_font_open(argv[4], &font, &sdk_error) == EXR_OK, "open font");
  path_join(fixture, sizeof(fixture), argv[1], "book.epub");
  require_ok(exr_publication_open(fixture, &pub, &sdk_error) == EXR_OK, "open actual EPUB");
  parts = exr_publication_parts(pub, &count); require_ok(count == 3 && parts[1].path != NULL, "actual EPUB spine");
  layout = exr_layout_config_defaults(); chapter = exr_chapter_options_defaults();
  require_ok(exr_publication_pager_create(pub, 1, font, &layout, &chapter, &pager, &sdk_error) == EXR_OK, "actual EPUB pager");
  require_ok(exr_pager_anchor_create(pager, 0, 3, NULL, &epub_range, &sdk_error) == EXR_OK, "actual EPUB range capture");
  require_ok(exr_pager_anchor_create(pager, 0, 0, NULL, &epub_point, &sdk_error) == EXR_OK, "actual EPUB point capture");
  env.book_key = "epub:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb";
  capture.mode = READER_RS_EPUB_CHAPTER; capture.part_path = parts[1].path; capture.anchor = &epub_range;
  text_case("epub-v1-range", store, legacy, &env, &capture, 1, 1, NULL, pub, pager);
  capture.anchor = &epub_point;
  text_case("epub-v2-point", store, legacy, &env, &capture, 2, 1, NULL, pub, pager);
#ifdef PURE_CAPTURE_TEST_ON
  refused_case("version-zero-clears-output", raw, &env, &capture, 0, 1);
  refused_case("version-four-clears-output", raw, &env, &capture, 4, 1);
  refused_case("version-three-epub-refused", raw, &env, &capture, 3, 1);
  refused_case("wrong-legacy-store-clears-output", legacy, &env, &capture, 2, 1);
  refused_case("null-store-clears-output", NULL, &env, &capture, 2, 1);
  refused_case("v1-point-not-silently-upgraded", raw, &env, &capture, 1, 1);
  { reader_rs_capture bad = capture; bad.mode = (reader_rs_mode)99;
    refused_case("wrong-mode-clears-output", raw, &env, &bad, 2, 1); }
  { static const char source[] = {'L','e','f','t',' ','A',0,'B',' ','R','i','g','h','t'};
    exr_fixed_text *text = NULL; exr_fixed_anchor fixed = PURE_ZERO, variant; char empty[] = "";
    reader_rs_capture fixed_capture = PURE_ZERO; reader_rs_error error = PURE_ZERO; char *wire; size_t bytes;
    require_ok(exr_fixed_text_create(source, sizeof(source), NULL, 0, NULL, &text, &sdk_error) == EXR_OK, "actual fixed text NUL");
    require_ok(exr_fixed_anchor_create("page-raw", text, 5, 8, &fixed, &sdk_error) == EXR_OK, "actual fixed NUL capture");
    env.book_key = "pdf:cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc";
    env.entity_kind = "annotation"; env.annotation_id = "00000000000000000000000000000002"; env.note_text = "actual NUL range";
    fixed_case("fixed-v3-real-nul", raw, legacy, &env, &fixed, text, 1);
    fixed_capture.mode = READER_RS_FIXED_PAGE; fixed_capture.fixed = &fixed;
    refused_case("fixed-nul-v2-not-silently-upgraded", raw, &env, &fixed_capture, 2, 0);
    env.entity_kind = "progress"; env.annotation_id = NULL; env.note_text = NULL;
    variant = fixed; variant.start = variant.end = 5; variant.exact = NULL; variant.exact_size = 0;
    variant.prefix = NULL; variant.prefix_size = 0; variant.suffix = NULL; variant.suffix_size = 0;
    fixed_case("fixed-v3-null-tags", raw, legacy, &env, &variant, text, 0);
    variant.exact = empty; variant.prefix = empty; variant.suffix = empty;
    fixed_case("fixed-v3-empty-tags", raw, legacy, &env, &variant, text, 0);
    wire = empty; bytes = 777;
    expect("old-encode-v2-still-refuses-raw-store", reader_rs_encode_v2(raw, &env, &fixed_capture, 0, &wire, &bytes, &error) != READER_RS_OK && wire == NULL && bytes == 0);
    exr_fixed_anchor_free(&fixed); exr_fixed_text_free(text); }
#elif defined(PURE_CAPTURE_TEST_RAW)
  { reader_rs_error error = PURE_ZERO; char sentinel = 0, *wire = &sentinel; size_t bytes = 777;
    expect("pure-off-old-codec-refuses-raw-store", reader_rs_encode_v2(raw, &env, &capture, 1, &wire, &bytes, &error) != READER_RS_OK && wire == NULL && bytes == 0); }
#endif
  expect("legacy-revision-history-unchanged", row_count(legacy_path, "reader_revisions") == before_revisions);
  expect("legacy-outbox-unchanged", row_count(legacy_path, "reader_outbox") == before_outbox);
#ifdef PURE_CAPTURE_TEST_RAW
  expect("raw-revision-history-unchanged", row_count(raw_path, "reader_revisions") == 0);
  expect("raw-outbox-unchanged", row_count(raw_path, "reader_outbox") == 0);
#endif
  reader_revisions_close(&raw, &revision_error); reader_revisions_close(&legacy, &revision_error);
  exr_anchor_free(&range); exr_anchor_free(&point); exr_anchor_free(&epub_range); exr_anchor_free(&epub_point);
  exr_pager_free(pager); exr_publication_free(pub); exr_font_free(font); exr_document_free(doc); exr_library_close(library);
  fprintf(report, "],\"count\":%zu,\"accepted\":%s}\n", checks, failures ? "false" : "true");
  fclose(report); return failures ? 1 : 0;
}
