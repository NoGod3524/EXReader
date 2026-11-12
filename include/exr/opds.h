/* SPDX-License-Identifier: MIT */
#ifndef EXR_OPDS_H
#define EXR_OPDS_H
#include <exr/base.h>
#ifdef __cplusplus
extern "C" {
#endif
/* OPDS 1.x (Atom) catalog parsing. Pure data: no network access, no files.
   All strings are owned UTF-8 and released by exr_opds_feed_free. Absent
   values are NULL. URLs are resolved against the base URL given to the parser;
   data: URIs are dropped. Acquisition choice prefers epub, then pdf, then the
   other formats (mobi, fb2, cbz, txt, rtf, docx), in document order. */
typedef struct {
  char *title, *author, *summary;
  char *cover_url;    /* rel image, else image/thumbnail */
  char *download_url; /* best direct acquisition link, NULL for navigation entries */
  char *format;       /* "epub" "pdf" "mobi" "fb2" "cbz" "txt" "rtf" "docx" or "other" */
  char *detail_url;   /* sub-catalog/entry feed (navigation, or the book's own feed) */
  uint64_t size;      /* advertised download bytes (link length), 0 when absent */
} exr_opds_entry;
typedef struct {
  char *title;
  exr_opds_entry *entries;
  size_t entry_count;
  char *next_url;                /* rel="next" */
  char *search_template;         /* URL template containing {searchTerms}, from an inline search link */
  char *search_description_url;  /* rel="search" OpenSearch description document */
} exr_opds_feed;
/* Parses one Atom feed. Limits: 16 MiB input, 4096 entries, nesting 64.
   On failure the output is zeroed. data need not be NUL terminated. */
EXR_API exr_status exr_opds_parse(const void *data, size_t size, const char *base_url,
                                  exr_opds_feed *out, exr_error *error);
EXR_API void exr_opds_feed_free(exr_opds_feed *feed);
/* Reads an OpenSearch description document and returns its Atom/OPDS result
   URL template (resolved against base_url). */
EXR_API exr_status exr_opds_parse_search(const void *data, size_t size, const char *base_url,
                                         char **template_url, exr_error *error);
/* Expands a template: {searchTerms} becomes the percent-encoded UTF-8 query,
   every other {parameter} or {parameter?} becomes empty. Owned result, release
   with exr_free. An empty query or a template without {searchTerms} fails. */
EXR_API exr_status exr_opds_search_url(const char *template_url, const char *query,
                                       char **out, exr_error *error);
/* RFC 3986 reference resolution for http/https bases. Owned result. */
EXR_API exr_status exr_opds_resolve_url(const char *base_url, const char *reference,
                                        char **out, exr_error *error);
#ifdef __cplusplus
}
#endif
#endif
