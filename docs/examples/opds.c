/* SPDX-License-Identifier: MIT */
#include <exr/opds.h>
#include <stdio.h>
#include <string.h>

int main(void) {
  const char feed[] =
      "<feed xmlns='http://www.w3.org/2005/Atom'>"
      "<title>Catalog</title>"
      "<entry><title>Book</title>"
      "<link rel='http://opds-spec.org/acquisition' type='application/epub+zip'"
      " href='../books/a.epub'/></entry></feed>";
  exr_opds_feed parsed = {0};
  exr_error error = {0};
  exr_status status = exr_opds_parse(feed, sizeof(feed) - 1,
                                     "https://example.test/catalog/root.xml", &parsed, &error);
  if (status != EXR_OK) {
    fprintf(stderr, "parse failed: %s\n", error.message);
    return 1;
  }
  printf("title=%s entries=%zu first=%s\n", parsed.title ? parsed.title : "",
         parsed.entry_count,
         parsed.entry_count ? parsed.entries[0].download_url : "");
  exr_opds_feed_free(&parsed);
  return 0;
}
