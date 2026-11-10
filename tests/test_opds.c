/* SPDX-License-Identifier: MIT */
#include <exr/opds.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define CHECK(c) do { if (!(c)) { fprintf(stderr, "%s:%d: %s\n", __FILE__, __LINE__, #c); return 1; } } while (0)
#define STR(a, b) do { const char *x_ = (a), *y_ = (b); if (!x_ || strcmp(x_, y_)) { fprintf(stderr, "%s:%d: got [%s] want [%s]\n", __FILE__, __LINE__, x_ ? x_ : "(null)", y_); return 1; } } while (0)
#define FEED_HEAD "<?xml version=\"1.0\" encoding=\"utf-8\"?><feed xmlns=\"http://www.w3.org/2005/Atom\" xmlns:dcterms=\"http://purl.org/dc/terms/\">"
static const char acquisition[] = FEED_HEAD
  "<title>Fiction</title><dcterms:title>ignored</dcterms:title>"
  "<link rel=\"next\" href=\"page2.xml?x=1&amp;y=2\"/>"
  "<link rel=\"search\" type=\"application/atom+xml\" href=\"/search?q={searchTerms}\"/>"
  "<entry><title>Alpha</title><author><name>A. One</name></author><author><name>B. Two</name></author>"
  "<summary>Short &amp; sweet</summary><content type=\"text\">ignored when summary exists</content>"
  "<link rel=\"http://opds-spec.org/acquisition\" type=\"application/pdf\" href=\"/files/a.pdf\"/>"
  "<link rel=\"http://opds-spec.org/acquisition/open-access\" type=\"application/epub+zip\" href=\"../files/a.epub\"/>"
  "<link rel=\"http://opds-spec.org/acquisition\" type=\"application/epub+zip\" href=\"/files/second.epub\"/>"
  "<link rel=\"http://opds-spec.org/image/thumbnail\" href=\"t.jpg\"/>"
  "<link rel=\"http://opds-spec.org/image\" href=\"c.jpg\"/></entry>"
  "<entry><title>Beta</title><link rel=\"http://opds-spec.org/acquisition\" type=\"application/octet-stream\" href=\"b.mobi\"/>"
  "<link rel=\"http://opds-spec.org/image/thumbnail\" href=\"data:image/png;base64,AAAA\"/>"
  "<link rel=\"http://opds-spec.org/image/thumbnail\" href=\"bt.jpg\"/></entry>"
  "<entry><title>Gamma</title><link rel=\"subsection\" type=\"application/atom+xml;profile=opds-catalog\" href=\"gamma.opds\"/>"
  "<link rel=\"related\" type=\"application/atom+xml\" href=\"author.opds\"/>"
  "<content type=\"xhtml\"><div xmlns=\"http://www.w3.org/1999/xhtml\"><p>One</p><p>Two</p></div></content></entry>"
  "</feed>";
static const char search[] = "<?xml version=\"1.0\"?><OpenSearchDescription xmlns=\"http://a9.com/-/spec/opensearch/1.1/\">"
  "<Url type=\"text/html\" template=\"http://h/html?q={searchTerms}\"/>"
  "<Url type=\"application/atom+xml\" template=\"/plain?q={searchTerms}\"/>"
  "<Url type=\"application/atom+xml;profile=opds-catalog\" template=\"/opds?q={searchTerms}&amp;p={startPage?}\"/>"
  "</OpenSearchDescription>";
int main(void) {
  exr_opds_feed f;
  exr_error e = {0};
  char *url = NULL;
  const char *base = "https://example.org/cat/root/feed.xml";
  const char broken[] = FEED_HEAD "<entry><title>x</feed>";
  CHECK(exr_opds_parse(acquisition, sizeof(acquisition) - 1, base, &f, &e) == EXR_OK);
  STR(f.title, "Fiction");
  STR(f.next_url, "https://example.org/cat/root/page2.xml?x=1&y=2");
  STR(f.search_template, "https://example.org/search?q={searchTerms}");
  CHECK(f.entry_count == 3);
  STR(f.entries[0].title, "Alpha");
  STR(f.entries[0].author, "A. One, B. Two");
  STR(f.entries[0].summary, "Short & sweet");
  STR(f.entries[0].format, "epub");
  STR(f.entries[0].download_url, "https://example.org/cat/files/a.epub");
  STR(f.entries[0].cover_url, "https://example.org/cat/root/c.jpg");
  CHECK(!f.entries[0].detail_url);
  STR(f.entries[1].format, "mobi");
  STR(f.entries[1].cover_url, "https://example.org/cat/root/bt.jpg");
  CHECK(!f.entries[1].author);
  CHECK(!f.entries[2].download_url && !f.entries[2].cover_url);
  STR(f.entries[2].detail_url, "https://example.org/cat/root/gamma.opds");
  STR(f.entries[2].summary, "One\nTwo");
  exr_opds_feed_free(&f);
  CHECK(!f.entries && !f.title);
  /* malformed, wrong root, empty and missing inputs fail and leave nothing behind */
  CHECK(exr_opds_parse(broken, sizeof(broken) - 1, base, &f, &e) == EXR_FORMAT);
  CHECK(!f.entries && !f.title && strstr(e.message, "Malformed"));
  CHECK(exr_opds_parse("<html><body/></html>", 20, base, &f, &e) == EXR_FORMAT && strstr(e.message, "Not an OPDS"));
  CHECK(exr_opds_parse("", 0, base, &f, &e) == EXR_FORMAT);
  CHECK(exr_opds_parse(NULL, 5, base, &f, &e) == EXR_ARGUMENT);
  /* OpenSearch description picks the opds-catalog template and resolves it */
  CHECK(exr_opds_parse_search(search, sizeof(search) - 1, "https://example.org/osd.xml", &url, &e) == EXR_OK);
  STR(url, "https://example.org/opds?q={searchTerms}&p={startPage?}");
  {
    char *expanded = NULL;
    CHECK(exr_opds_search_url(url, "a b&c/\xC3\xBC", &expanded, &e) == EXR_OK);
    STR(expanded, "https://example.org/opds?q=a%20b%26c%2F%C3%BC&p=");
    exr_free(expanded);
    expanded = NULL;
    CHECK(exr_opds_search_url(url, "", &expanded, &e) == EXR_ARGUMENT && !expanded);
    CHECK(exr_opds_search_url("https://h/x?q=1", "a", &expanded, &e) == EXR_FORMAT && !expanded);
  }
  exr_free(url);
  url = NULL;
  CHECK(exr_opds_parse_search("<a/>", 4, base, &url, &e) == EXR_FORMAT && !url);
  /* RFC 3986 section 5.4 examples */
  {
    static const struct { const char *ref, *want; } cases[] = {
      {"g", "http://a/b/c/g"}, {"./g", "http://a/b/c/g"}, {"g/", "http://a/b/c/g/"}, {"/g", "http://a/g"},
      {"//g", "http://g"}, {"?y", "http://a/b/c/d;p?y"}, {"g?y", "http://a/b/c/g?y"}, {"#s", "http://a/b/c/d;p?q#s"},
      {"", "http://a/b/c/d;p?q"}, {".", "http://a/b/c/"}, {"..", "http://a/b/"}, {"../g", "http://a/b/g"},
      {"../../g", "http://a/g"}, {"../../../g", "http://a/g"}, {"g.", "http://a/b/c/g."},
      {"https://z/x", "https://z/x"}, {"g;x?y#s", "http://a/b/c/g;x?y#s"}};
    for (size_t i = 0; i < sizeof(cases) / sizeof(*cases); i++) {
      CHECK(exr_opds_resolve_url("http://a/b/c/d;p?q", cases[i].ref, &url, &e) == EXR_OK);
      if (strcmp(url, cases[i].want)) { fprintf(stderr, "resolve [%s] got [%s] want [%s]\n", cases[i].ref, url, cases[i].want); return 1; }
      exr_free(url);
    }
    url = NULL;
    CHECK(exr_opds_resolve_url("relative", "x", &url, &e) == EXR_ARGUMENT && !url);
    CHECK(exr_opds_resolve_url("http://host", "x", &url, &e) == EXR_OK);
    STR(url, "http://host/x");
    exr_free(url);
  }
  puts("opds ok");
  return 0;
}
