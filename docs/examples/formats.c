/* SPDX-License-Identifier: MIT */
#include <exr/formats.h>
#include <exr/opds.h>
#include <string.h>
#include <stdio.h>

int main(void) {
  const char html[] = "<html><body><h1>Chapter</h1><p>Hello.</p></body></html>";
  exr_document *document = NULL;
  exr_error error = {0};
  exr_status status = exr_document_open_memory(EXR_HTML, html, sizeof(html) - 1,
                                               &document, &error);
  if (status == EXR_OK)
    printf("format=%d\n", (int)exr_document_format(document));
  else
    fprintf(stderr, "%s\n", error.message);
  exr_document_free(document);
  if (status != EXR_OK) return 1;
  const char atom[] = "<feed xmlns='http://www.w3.org/2005/Atom'><title>Catalog</title>"
    "<entry><title>Example</title><link rel='http://opds-spec.org/acquisition' "
    "type='application/epub+zip' href='../books/a.epub'/></entry></feed>";
  exr_opds_feed feed = {0};
  status = exr_opds_parse(atom, sizeof(atom) - 1, "https://example.test/catalog/root.xml", &feed, &error);
  int catalog_ok = status == EXR_OK && feed.entry_count == 1 && feed.entries[0].download_url &&
    !strcmp(feed.entries[0].download_url, "https://example.test/books/a.epub");
  if (catalog_ok) printf("OPDS entries=%zu title=%s\n", feed.entry_count, feed.title);
  else fprintf(stderr, "OPDS parse failed: %s\n", error.message);
  exr_opds_feed_free(&feed);
  return catalog_ok ? 0 : 1;
}
