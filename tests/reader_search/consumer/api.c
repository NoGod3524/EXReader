/* SPDX-License-Identifier: MIT */
/* Independent C consumer: only <reader_search.h> and the SDK, no product modules.
   Builds a generated one-page fixed document and walks the whole ownership cycle. */
#include <reader_search.h>
#include <stdio.h>
#include <string.h>

static exr_status text_page(void *context, size_t page, const exr_control *control, exr_fixed_text **out, exr_error *error) {
  static const char text[] = "alpha \xe4\xb8\xad\xe6\x96\x87 alpha \xf0\x9f\x99\x82 alpha";
  (void)context; (void)page;
  return exr_fixed_text_create(text, sizeof(text) - 1, NULL, 0, control, out, error);
}
static exr_status draw_page(void *context, size_t page, const double matrix[6], const exr_draw_sink *sink,
                            const exr_control *control, exr_error *error) {
  (void)context; (void)page; (void)matrix; (void)sink; (void)control; (void)error;
  return EXR_OK;
}
static int never(void *context) { (void)context; return 0; }

int main(void) {
  exr_fixed_page page;
  exr_fixed_input input;
  exr_fixed_document *doc = NULL;
  exr_error sdk_error;
  reader_search *search = NULL;
  reader_search_error error;
  reader_search_options options;
  reader_search_result result;
  reader_search_stats stats;
  reader_search_cursor cursor;
  size_t total = 0;
  if (strcmp(READER_SEARCH_VERSION, "0.1.0") || READER_SEARCH_BATCH_MAX != 100u || READER_SEARCH_QUERY_MAX != 4096u) return 1;
  memset(&page, 0, sizeof(page)); memset(&input, 0, sizeof(input)); memset(&sdk_error, 0, sizeof(sdk_error));
  page.id = "c-page"; page.geometry.bounds[2] = 100; page.geometry.bounds[3] = 100; page.geometry.unit_scale = 1;
  input.struct_size = sizeof(input); input.title = "c"; input.pages = &page; input.page_count = 1; input.draw = draw_page; input.text = text_page;
  if (exr_fixed_create(&input, &doc, &sdk_error) != EXR_OK) return 2;
  memset(&options, 0, sizeof(options)); options.struct_size = sizeof(options); options.control.cancelled = never;
  if (reader_search_open_fixed(doc, "alpha", 5, &options, &search, &error) != READER_SEARCH_OK || !search) return 3;
  memset(&result, 0xa5, sizeof(result));
  if (reader_search_next(search, 2, &result, &error) != READER_SEARCH_OK || result.count != 2 || result.complete) return 4;
  if (result.hits[0].mode != READER_SEARCH_FIXED || strcmp(result.hits[0].page_id, "c-page") || result.hits[0].unit != 0 ||
      result.hits[0].start != 0 || result.hits[0].end != 5 || result.hits[0].fixed.exact_size != 5) return 5;
  total += result.count;
  reader_search_result_free(&result);
  if (result.hits || result.count) return 6;
  if (reader_search_cursor_get(search, &cursor, &error) != READER_SEARCH_OK || cursor.complete) return 7;
  if (reader_search_next(search, 2, &result, &error) != READER_SEARCH_OK || result.count != 1 || !result.complete) return 8;
  total += result.count;
  reader_search_result_free(&result); reader_search_result_free(&result);
  if (total != 3) return 9;
  if (reader_search_stats_get(search, &stats, &error) != READER_SEARCH_OK || stats.calls != 2 || stats.hits_returned != 3 || !stats.bytes_scanned) return 10;
  if (reader_search_next(search, 0, &result, &error) != READER_SEARCH_ARGUMENT || result.hits) return 11;
  if (reader_search_close(&search, &error) != READER_SEARCH_OK || search) return 12;
  {
    reader_search *other = NULL;
    if (reader_search_open_fixed(doc, "", 0, NULL, &other, &error) != READER_SEARCH_QUERY || other) return 13;
    if (reader_search_open_fixed(doc, "\xc0\x80", 2, NULL, &other, &error) != READER_SEARCH_QUERY || other) return 14;
  }
  exr_fixed_free(doc);
  puts("c-consumer-ok");
  return 0;
}
