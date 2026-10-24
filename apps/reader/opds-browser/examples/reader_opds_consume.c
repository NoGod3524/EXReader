/* SPDX-License-Identifier: MIT */
/* Minimal in-tree integration example: open a feed, print its first page and
   optionally stage one free acquisition. Build with -DREADER_OPDS_BUILD_EXAMPLE=ON. */
#include "reader_opds_browser.h"
#include <stdio.h>
#include <string.h>

int main(int argc, char **argv) {
  reader_opds_config config;
  reader_opds_browser *browser;
  reader_opds_page *page = NULL;
  opds_error error;
  reader_opds_status status;
  size_t i, k;
  if (argc < 2) {
    fprintf(stderr, "usage: %s <feed-url> [staging-dir]\n", argv[0]);
    return 2;
  }
  printf("reader_opds_browser %s, https %s\n", READER_OPDS_BROWSER_VERSION,
         reader_opds_tls_available() ? "available" : "unavailable");
  reader_opds_config_defaults(&config);
  config.staging_dir = argc > 2 ? argv[2] : NULL;
  browser = reader_opds_browser_create(&config, &error);
  if (!browser) {
    fprintf(stderr, "create failed: %s\n", error.message);
    return 1;
  }
  status = reader_opds_open(browser, argv[1], NULL, &page, &error);
  if (status != READER_OPDS_OK) {
    fprintf(stderr, "open failed: %s (%s)\n", reader_opds_status_name(status), error.message);
    reader_opds_browser_free(browser);
    return 1;
  }
  printf("%s  identity=%.8s page=%u entries=%zu facets=%zu next=%s\n",
         page->title, page->identity, page->page_number, page->entry_count, page->facet_count,
         page->has_next ? page->cursor : "none");
  for (i = 0; i < page->entry_count; i++) {
    const reader_opds_entry *entry = &page->entries[i];
    printf("  [%zu] %s%s\n", i, entry->title, entry->is_publication ? "" : " (navigation)");
    for (k = 0; k < entry->link_count; k++) {
      const reader_opds_link *link = &entry->links[k];
      printf("      %s %s (%s)\n", reader_opds_acquire_name(link->acquire), link->title[0] ? link->title : link->type,
             link->href);
    }
  }
  if (config.staging_dir && page->entry_count) {
    reader_opds_acquired staged;
    reader_opds_status acquired = reader_opds_acquire(browser, page, 0, (size_t)page->entries[0].free_link, NULL, NULL,
                                                      &staged, &error);
    printf("acquire: %s%s\n", reader_opds_status_name(acquired), acquired == READER_OPDS_OK ? staged.path : error.message);
    if (acquired == READER_OPDS_OK) reader_opds_staged_discard(&staged, NULL);
  }
  reader_opds_page_free(page);
  reader_opds_browser_free(browser);
  return 0;
}
