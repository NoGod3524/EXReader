/* SPDX-License-Identifier: MIT */
#include "opds.h"
#include <stdio.h>
#include <string.h>

static unsigned checks, failures;
#define CHECK(x) do { checks++; if (!(x)) { failures++; fprintf(stderr,"facet check failed at line %d: %s\n",__LINE__,#x); } } while (0)
static const char atom[] =
  "<feed xmlns='http://www.w3.org/2005/Atom' xmlns:o='http://opds-spec.org/2010/catalog' "
  "xmlns:t='http://purl.org/syndication/thread/1.0' xml:base='https://catalog.test/books/'>"
  "<title>Catalog</title><link rel='http://opds-spec.org/facet' href='recent' title='Recent' o:facetGroup='Order' o:activeFacet='true'/>"
  "<link rel='http://opds-spec.org/facet' href='../popular' title='Popular' o:facetGroup='Order' t:count='42'/>"
  "<link rel='http://opds-spec.org/facet' href='?language=zh' title='Chinese' o:facetGroup='Language' t:count='0'/>"
  "<link rel='http://opds-spec.org/facet' href='/all' title='All'/></feed>";
static const char json[] =
  "{\"metadata\":{\"title\":\"Catalog\"},\"facets\":["
  "{\"metadata\":{\"title\":\"Order\"},\"links\":["
  "{\"href\":\"recent\",\"title\":\"Recent\",\"rel\":[\"alternate\",\"self\"],\"properties\":{\"numberOfItems\":42}},"
  "{\"href\":\"../popular\",\"title\":\"Popular\",\"properties\":{\"numberOfItems\":9223372036854775807}}]},"
  "{\"metadata\":{\"title\":{\"en\":\"Language\"}},\"links\":[{\"href\":\"?language=zh\",\"title\":\"Chinese\"}]}]}";

static void reject(const char *input, const opds_limits *limits, opds_status wanted) {
  opds_feed feed; opds_error error = {0}; size_t count = 99;
  memset(&feed, 0xa5, sizeof(feed));
  CHECK(opds_feed_parse(input, strlen(input), NULL, "https://catalog.test/books/", limits, &feed, &error) == wanted);
  CHECK(feed.arena == NULL && feed.entry_count == 0 && feed.link_count == 0);
  CHECK(opds_feed_facets(&feed, &count) == NULL && count == 0);
  opds_feed_free(&feed);
}

int main(int argc, char **argv) {
  opds_feed feed; opds_error error = {0}; const opds_facet *facets;
  const char empty[] = "{\"metadata\":{\"title\":\"Empty\"},\"links\":[]}";
  const char empty_atom[] = "<feed xmlns='http://www.w3.org/2005/Atom'><title>Empty</title><id></id></feed>";
  opds_limits limits; size_t count = 99;
  CHECK(opds_feed_facets(NULL, &count) == NULL && count == 0);
  CHECK(opds_feed_facets(NULL, NULL) == NULL);
  CHECK(opds_feed_parse(atom, strlen(atom), NULL, NULL, NULL, NULL, &error) == OPDS_ARGUMENT);
  CHECK(opds_feed_parse(atom, strlen(atom), NULL, NULL, NULL, &feed, &error) == OPDS_OK);
  facets = opds_feed_facets(&feed, &count);
  CHECK(facets != NULL && count == 3 && feed.link_count == 4);
  if (facets && count == 3) {
    CHECK(!strcmp(facets[0].title, "Order") && facets[0].choice_count == 2);
    CHECK(facets[0].choices[0].active && facets[0].choices[0].number_of_items == -1);
    CHECK(!strcmp(facets[0].choices[0].link.href, "https://catalog.test/books/recent"));
    CHECK(!strcmp(facets[0].choices[1].link.href, "https://catalog.test/popular"));
    CHECK(!facets[0].choices[1].active && facets[0].choices[1].number_of_items == 42);
    CHECK(!strcmp(facets[1].title, "Language") && facets[1].choices[0].number_of_items == 0);
    CHECK(!strcmp(facets[2].title, "") && facets[2].choice_count == 1);
    CHECK(opds_feed_facets(&feed, NULL) == facets);
  }
  opds_feed_free(&feed);
  CHECK(opds_feed_facets(&feed, &count) == NULL && count == 0);
  CHECK(opds_feed_parse(json, strlen(json), NULL, "https://catalog.test/books/", NULL, &feed, &error) == OPDS_OK);
  facets = opds_feed_facets(&feed, &count);
  CHECK(facets != NULL && count == 2);
  if (facets && count == 2) {
    CHECK(!strcmp(facets[0].title, "Order") && facets[0].choice_count == 2);
    CHECK(facets[0].choices[0].active && facets[0].choices[0].number_of_items == 42);
    CHECK(!facets[0].choices[1].active && facets[0].choices[1].number_of_items == INT64_MAX);
    CHECK(!strcmp(facets[0].choices[0].link.href, "https://catalog.test/books/recent"));
    CHECK(!strcmp(facets[0].choices[1].link.href, "https://catalog.test/popular"));
    CHECK(!strcmp(facets[1].title, "Language") && facets[1].choices[0].number_of_items == -1);
  }
  opds_feed_free(&feed);
  reject("{\"metadata\":{\"title\":\"X\"},\"facets\":{}}", NULL, OPDS_FORMAT);
  reject("{\"metadata\":{\"title\":\"X\"},\"facets\":[{\"links\":[]}]}", NULL, OPDS_FORMAT);
  reject("{\"metadata\":{\"title\":\"X\"},\"facets\":[{\"metadata\":{\"title\":\"G\"},\"links\":[]}]}", NULL, OPDS_FORMAT);
  reject("{\"metadata\":{\"title\":\"X\"},\"facets\":[{\"metadata\":{\"title\":2},\"links\":[{\"href\":\"a\"}]}]}", NULL, OPDS_FORMAT);
  reject("{\"metadata\":{\"title\":\"X\"},\"facets\":[{\"metadata\":{\"title\":\"G\"},\"links\":[{}]}]}", NULL, OPDS_FORMAT);
  reject("{\"metadata\":{\"title\":\"X\"},\"facets\":[{\"metadata\":{\"title\":\"G\"},\"links\":[{\"href\":\"a\",\"properties\":true}]}]}", NULL, OPDS_FORMAT);
  reject("{\"metadata\":{\"title\":\"X\"},\"facets\":[{\"metadata\":{\"title\":\"G\"},\"links\":[{\"href\":\"a\",\"properties\":{\"numberOfItems\":-1}}]}]}", NULL, OPDS_FORMAT);
  reject("{\"metadata\":{\"title\":\"X\"},\"facets\":[{\"metadata\":{\"title\":\"G\"},\"links\":[{\"href\":\"a\",\"properties\":{\"numberOfItems\":1.5}}]}]}", NULL, OPDS_FORMAT);
  reject("{\"metadata\":{\"title\":\"X\"},\"facets\":[{\"metadata\":{\"title\":\"G\"},\"links\":[{\"href\":\"a\",\"properties\":{\"numberOfItems\":\"2\"}}]}]}", NULL, OPDS_FORMAT);
  reject("{\"metadata\":{\"title\":\"X\"},\"facets\":[{\"metadata\":{\"title\":\"G\"},\"links\":[{\"href\":\"a\",\"properties\":{\"numberOfItems\":9223372036854775808}}]}]}", NULL, OPDS_FORMAT);
  reject("<feed xmlns='http://www.w3.org/2005/Atom' xmlns:o='http://opds-spec.org/2010/catalog'><title>X</title><link rel='http://opds-spec.org/facet' href='a' o:activeFacet='yes'/></feed>", NULL, OPDS_FORMAT);
  reject("<feed xmlns='http://www.w3.org/2005/Atom' xmlns:o='http://opds-spec.org/2010/catalog'><title>X</title><link rel='http://opds-spec.org/facet' href='a' o:activeFacet='true'/><link rel='http://opds-spec.org/facet' href='b' o:activeFacet='true'/></feed>", NULL, OPDS_FORMAT);
  opds_limits_defaults(&limits); limits.max_entries = 1;
  reject(atom, &limits, OPDS_LIMIT);
  reject(json, &limits, OPDS_LIMIT);
  opds_limits_defaults(&limits); limits.max_links_per_entry = 1;
  reject(atom, &limits, OPDS_LIMIT);
  reject(json, &limits, OPDS_LIMIT);
  CHECK(opds_feed_parse(empty, strlen(empty), NULL, NULL, NULL, &feed, &error) == OPDS_OK);
  CHECK(opds_feed_facets(&feed, &count) == NULL && count == 0);
  opds_feed_free(&feed);
  CHECK(opds_feed_parse(empty_atom, strlen(empty_atom), NULL, NULL, NULL, &feed, &error) == OPDS_OK);
  CHECK(feed.id && !strcmp(feed.id, ""));
  CHECK(opds_feed_facets(&feed, &count) == NULL && count == 0);
  opds_feed_free(&feed);
  printf("{\"passed\":%s,\"checks\":%u,\"failures\":%u}\n", failures ? "false" : "true", checks, failures);
  if (argc > 1) {
    FILE *result = fopen(argv[1], "wb");
    if (!result) return 2;
    if (fprintf(result, "{\"passed\":%s,\"checks\":%u,\"failures\":%u}\n", failures ? "false" : "true", checks, failures) < 0) {
      fclose(result); return 2;
    }
    if (fclose(result)) return 2;
  }
  return failures ? 1 : 0;
}
