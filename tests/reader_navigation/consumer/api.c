/* SPDX-License-Identifier: MIT */
/* Independent C consumer: only <reader_navigation.h> and the SDK. Builds a generated
   three-page fixed document and walks the whole snapshot/page/target ownership cycle. */
#include <reader_navigation.h>
#include <stdio.h>
#include <string.h>

static exr_status draw_page(void *context, size_t page, const double matrix[6], const exr_draw_sink *sink,
                            const exr_control *control, exr_error *error) {
  (void)context; (void)page; (void)matrix; (void)sink; (void)control; (void)error;
  return EXR_OK;
}

int main(void) {
  exr_fixed_page pages[3];
  exr_fixed_input input;
  exr_fixed_document *doc = NULL;
  exr_error sdk_error;
  reader_navigation *nav = NULL;
  reader_navigation_error error;
  reader_navigation_info info;
  reader_navigation_page page;
  reader_navigation_target target;
  reader_navigation_resolve_options ro;
  size_t i;
  if (strcmp(READER_NAVIGATION_VERSION, "0.1.0") || READER_NAVIGATION_PAGE_MAX != 100u ||
      READER_NAVIGATION_NODES_MAX != 10000u || READER_NAVIGATION_DEPTH_MAX != 64u) return 1;
  memset(pages, 0, sizeof(pages)); memset(&input, 0, sizeof(input)); memset(&sdk_error, 0, sizeof(sdk_error));
  for (i = 0; i < 3; i++) { pages[i].geometry.bounds[2] = 100; pages[i].geometry.bounds[3] = 100; pages[i].geometry.unit_scale = 1; }
  pages[0].id = "c-a"; pages[0].label = "Cover";
  pages[1].id = "c-b"; pages[1].label = NULL;
  pages[2].id = "c-c"; pages[2].label = "";
  input.struct_size = sizeof(input); input.title = "c"; input.pages = pages; input.page_count = 3; input.draw = draw_page;
  if (exr_fixed_create(&input, &doc, &sdk_error) != EXR_OK) return 2;
  if (reader_navigation_open_pages(doc, NULL, &nav, &error) != READER_NAVIGATION_OK || !nav) return 3;
  if (reader_navigation_info_get(nav, &info, &error) != READER_NAVIGATION_OK) return 4;
  if (info.kind != READER_NAVIGATION_PAGES || info.author_outline != 0 || info.node_count != 3 || info.part_count != 3) return 5;
  memset(&page, 0xa5, sizeof(page));
  if (reader_navigation_rows(nav, 0, 2, &page, &error) != READER_NAVIGATION_OK || page.count != 2 || page.total != 3 || page.next != 2) return 6;
  if (strcmp(page.rows[0].label, "Cover") || strcmp(page.rows[1].label, "c-b") || strcmp(page.rows[1].role, "page") ||
      page.rows[0].target_class != READER_NAVIGATION_TARGET_PAGE || page.rows[0].part != 0) return 7;
  /* The page is an independent copy: it survives the snapshot and the SDK document. */
  if (reader_navigation_close(&nav, &error) != READER_NAVIGATION_OK || nav) return 8;
  if (strcmp(page.rows[1].part_id, "c-b")) return 9;
  reader_navigation_page_free(&page);
  if (page.rows || page.count) return 10;
  reader_navigation_page_free(&page);
  if (reader_navigation_open_pages(doc, NULL, &nav, &error) != READER_NAVIGATION_OK) return 11;
  if (reader_navigation_rows(nav, 0, 0, &page, &error) != READER_NAVIGATION_ARGUMENT || page.rows) return 12;
  if (reader_navigation_rows(nav, 0, 101, &page, &error) != READER_NAVIGATION_ARGUMENT || page.rows) return 13;
  if (reader_navigation_rows(nav, 4, 10, &page, &error) != READER_NAVIGATION_RANGE || page.rows) return 14;
  if (reader_navigation_rows(nav, 3, 10, &page, &error) != READER_NAVIGATION_OK || page.count != 0 || page.next != READER_NAVIGATION_NONE) return 15;
  reader_navigation_page_free(&page);
  if (reader_navigation_children(nav, READER_NAVIGATION_NONE, 0, 100, &page, &error) != READER_NAVIGATION_OK || page.count != 3) return 16;
  reader_navigation_page_free(&page);
  memset(&ro, 0, sizeof(ro)); ro.struct_size = sizeof(ro); ro.explicit_part = READER_NAVIGATION_NONE;
  if (reader_navigation_resolve_page(nav, 1, doc, &ro, &target, &error) != READER_NAVIGATION_OK) return 17;
  if (target.kind != READER_NAVIGATION_RESULT_PAGE || target.part != 1 || strcmp(target.part_id, "c-b") || target.part_path) return 18;
  reader_navigation_target_free(&target);
  if (target.kind || target.part_id) return 19;
  reader_navigation_target_free(&target);
  if (reader_navigation_resolve_page(nav, 3, doc, NULL, &target, &error) != READER_NAVIGATION_RANGE || target.kind) return 20;
  if (reader_navigation_close(&nav, &error) != READER_NAVIGATION_OK || nav) return 21;
  if (reader_navigation_close(&nav, &error) != READER_NAVIGATION_OK) return 22;
  exr_fixed_free(doc);
  puts("c-consumer-ok");
  return 0;
}
