/* SPDX-License-Identifier: GPL-3.0-only */
#include "exreader.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static exr_error error;
static unsigned checks;
#define CHECK(x)                                                                                   \
  do {                                                                                             \
    checks++;                                                                                      \
    if (!(x)) {                                                                                    \
      fprintf(stderr, "line %d: %s (%d: %s)\n", __LINE__, #x, (int)error.code, error.message);      \
      exit(1);                                                                                     \
    }                                                                                              \
  } while (0)
#define OK(x) CHECK((x) == EXR_OK)

typedef struct {
  unsigned loads[6];
  exr_session *session;
  int reenter;
} provider;

static exr_status load_part(void *context, size_t part, exr_document **out, exr_error *e) {
  provider *p = context;
  static const size_t lengths[] = {64, 512, 8192, 64, 64, 64};
  char text[8193];
  exr_status status;
  CHECK(part < 6);
  p->loads[part]++;
  if (p->session && p->reenter && part == 5) {
    exr_error nested;
    size_t count = exr_session_cached(p->session);
    size_t bytes = exr_session_cached_bytes(p->session);
    CHECK(exr_session_set_budget(p->session, 1, &nested) == EXR_ARGUMENT);
    CHECK(nested.code == EXR_ARGUMENT);
    CHECK(exr_session_cached(p->session) == count);
    CHECK(exr_session_cached_bytes(p->session) == bytes);
  }
  memset(text, 'A', lengths[part]);
  text[lengths[part]] = 0;
  if (part == 4) {
    exr_attribute style = {"style", "line-height:1000px"};
    exr_node_input nodes[] = {
        {EXR_NODE_DOCUMENT, SIZE_MAX, NULL, NULL, NULL, 0},
        {EXR_NODE_CHAPTER, 0, NULL, NULL, NULL, 0},
        {EXR_NODE_PARAGRAPH, 1, NULL, NULL, &style, 1},
        {EXR_NODE_TEXT, 2, NULL, text, NULL, 0}};
    exr_chapter_input chapter = {"large-line", "large-line.unit", 1, 1};
    exr_document_input input = {"Layout failure", nodes, 4, &chapter, 1, NULL, 0};
    return exr_document_create(&input, out, e);
  }
  status = exr_document_open_memory(EXR_TXT, text, lengths[part], out, e);
  if (part == 3 && status == EXR_OK) {
    e->code = EXR_FORMAT;
    snprintf(e->message, sizeof(e->message), "Intentional loader failure with a document");
    return EXR_FORMAT;
  }
  return status;
}

static size_t measure(exr_publication *publication, size_t part, exr_font *font,
                       const exr_layout_config *config) {
  exr_document *document = NULL;
  exr_layout *layout = NULL;
  size_t document_bytes, layout_bytes;
  OK(exr_publication_load(publication, part, &document, &error));
  OK(exr_layout_create_ex(document, font, config, &layout, &error));
  document_bytes = exr_document_memory_size(document);
  layout_bytes = exr_layout_memory_size(layout);
  CHECK(document_bytes && layout_bytes && document_bytes < SIZE_MAX - layout_bytes);
  CHECK(exr_document_memory_size(document) == document_bytes);
  CHECK(exr_layout_memory_size(layout) == layout_bytes);
  exr_layout_free(layout);
  exr_document_free(document);
  return document_bytes + layout_bytes;
}

static void accounting(void) {
  unsigned char payload[64] = {0};
  exr_node_input nodes[] = {
      {EXR_NODE_DOCUMENT, SIZE_MAX, NULL, NULL, NULL, 0},
      {EXR_NODE_CHAPTER, 0, NULL, NULL, NULL, 0},
      {EXR_NODE_PARAGRAPH, 1, NULL, NULL, NULL, 0},
      {EXR_NODE_TEXT, 2, NULL, "A sample paragraph", NULL, 0}};
  exr_chapter_input chapter = {"part", "part.unit", 1, 1};
  exr_resource_input resource = {
      {"payload", "assets/payload.bin", "application/octet-stream", ""}, payload, 7};
  exr_attribute attributes[] = {{"lang", "en"}, {"data-note", "two words"}};
  exr_document_input input = {"Accounting", nodes, 4, &chapter, 1, &resource, 1};
  exr_document *base = NULL, *changed = NULL;
  size_t base_bytes, changed_bytes, expected, i;
  OK(exr_document_create(&input, &base, &error));
  base_bytes = exr_document_memory_size(base);
  resource.size += 23;
  OK(exr_document_create(&input, &changed, &error));
  changed_bytes = exr_document_memory_size(changed);
  CHECK(changed_bytes > base_bytes && changed_bytes - base_bytes == 23);
  exr_document_free(changed);
  exr_document_free(base);

  /* Identical trees keep the same array capacities. Adding attributes owns one
     exact attribute array plus copied names and values, without changing text. */
  input.resources = NULL;
  input.resource_count = 0;
  OK(exr_document_create(&input, &base, &error));
  base_bytes = exr_document_memory_size(base);
  nodes[2].attributes = attributes;
  nodes[2].attribute_count = sizeof(attributes) / sizeof(*attributes);
  expected = sizeof(attributes);
  for (i = 0; i < nodes[2].attribute_count; i++)
    expected += strlen(attributes[i].name) + strlen(attributes[i].value) + 2;
  OK(exr_document_create(&input, &changed, &error));
  changed_bytes = exr_document_memory_size(changed);
  CHECK(changed_bytes > base_bytes && changed_bytes - base_bytes == expected);
  CHECK(!strcmp(exr_document_text(base, NULL), exr_document_text(changed, NULL)));
  exr_document_free(changed);
  exr_document_free(base);
}

static void cache_budget(exr_font *font) {
  exr_part parts[] = {{"a", "a.unit", "A", 1}, {"b", "b.unit", "B", 1},
                      {"large", "large.unit", "Large", 1}, {"broken", "broken.unit", "Broken", 1},
                      {"layout", "layout.unit", "Layout", 1}, {"c", "c.unit", "C", 1}};
  provider source = {0};
  exr_publication_input input = {"Budget", parts, 6, load_part, &source, NULL, NULL, 0};
  exr_publication *publication = NULL;
  exr_session *session = NULL;
  exr_layout_config config = exr_layout_config_defaults();
  const exr_document *document = NULL, *first_document, *second_document;
  const exr_layout *layout = NULL, *first_layout, *second_layout;
  size_t a, b, large, count;
  unsigned first_loads, second_loads;
  config.page = (exr_layout_options){280, 240, 16, 18, 1.4f, 4};
  OK(exr_publication_create(&input, &publication, &error));
  a = measure(publication, 0, font, &config);
  b = measure(publication, 1, font, &config);
  large = measure(publication, 2, font, &config);
  CHECK(b >= a && large > a + b);
  CHECK(measure(publication, 5, font, &config) == a);
  OK(exr_session_create(publication, font, &config, 3, &session, &error));
  source.session = session;
  CHECK(!exr_session_cached_bytes(session));

  /* The default and explicit zero budgets preserve the existing count limit. */
  OK(exr_session_get(session, 0, &document, &layout, &error));
  CHECK(exr_session_cached_bytes(session) == a);
  OK(exr_session_get(session, 1, &document, &layout, &error));
  CHECK(exr_session_cached_bytes(session) == a + b);
  OK(exr_session_set_budget(session, 0, &error));
  OK(exr_session_get(session, 2, &document, &layout, &error));
  CHECK(exr_session_cached(session) == 3 && exr_session_cached_bytes(session) == a + b + large);
  OK(exr_session_get(session, 5, &document, &layout, &error));
  CHECK(exr_session_cached(session) == 3 && exr_session_cached_bytes(session) == a + b + large);
  OK(exr_session_set_budget(session, SIZE_MAX, &error));
  CHECK(exr_session_cached(session) == 3 && exr_session_cached_bytes(session) == a + b + large);
  exr_session_clear(session);
  CHECK(!exr_session_cached(session) && !exr_session_cached_bytes(session));
  exr_session_clear(session);
  CHECK(!exr_session_cached_bytes(session));

  /* Exact fits work; reducing the budget drops the oldest entries immediately. */
  OK(exr_session_set_budget(session, a + b, &error));
  OK(exr_session_get(session, 0, &document, &layout, &error));
  first_document = document;
  first_layout = layout;
  first_loads = source.loads[0];
  OK(exr_session_get(session, 1, &document, &layout, &error));
  CHECK(exr_session_cached_bytes(session) == a + b);
  OK(exr_session_get(session, 0, &document, &layout, &error));
  CHECK(document == first_document && layout == first_layout && source.loads[0] == first_loads);
  CHECK(exr_session_cached_bytes(session) == a + b);
  OK(exr_session_set_budget(session, a + b, &error));
  CHECK(exr_session_cached(session) == 2 && exr_session_cached_bytes(session) == a + b);
  OK(exr_session_set_budget(session, a, &error));
  CHECK(exr_session_cached(session) == 1 && exr_session_cached_bytes(session) == a);
  OK(exr_session_get(session, 0, &document, &layout, &error));
  CHECK(document == first_document && layout == first_layout && source.loads[0] == first_loads);
  OK(exr_session_set_budget(session, a - 1, &error));
  CHECK(!exr_session_cached(session) && !exr_session_cached_bytes(session));
  CHECK(exr_session_get(session, 0, &document, &layout, &error) == EXR_LIMIT);
  CHECK(!document && !layout && !exr_session_cached_bytes(session));
  OK(exr_session_set_budget(session, 0, &error));
  OK(exr_session_get(session, 2, &document, &layout, &error));
  CHECK(exr_session_cached_bytes(session) == large);
  exr_session_clear(session);

  /* Oversized, failed loader and failed layout requests preserve the old cache
     and LRU order, so borrowed results remain usable after each failure. */
  OK(exr_session_set_budget(session, a + b, &error));
  OK(exr_session_get(session, 0, &document, &layout, &error));
  first_document = document;
  first_layout = layout;
  first_loads = source.loads[0];
  OK(exr_session_get(session, 1, &document, &layout, &error));
  second_document = document;
  second_layout = layout;
  second_loads = source.loads[1];
  OK(exr_session_get(session, 0, &document, &layout, &error));
  CHECK(exr_session_get(session, 2, &document, &layout, &error) == EXR_LIMIT);
  CHECK(!document && !layout && exr_session_cached(session) == 2);
  CHECK(exr_session_cached_bytes(session) == a + b);
  CHECK(strlen(exr_document_text(first_document, NULL)) == 64);
  CHECK(strlen(exr_document_text(second_document, NULL)) == 512);
  CHECK(exr_layout_glyphs(first_layout, &count) && count == 64);
  CHECK(exr_layout_glyphs(second_layout, &count) && count == 512);
  CHECK(exr_session_get(session, 3, &document, &layout, &error) == EXR_FORMAT);
  CHECK(!document && !layout && exr_session_cached_bytes(session) == a + b);
  CHECK(exr_session_get(session, 4, &document, &layout, &error) == EXR_LIMIT);
  CHECK(!document && !layout && exr_session_cached_bytes(session) == a + b);
  CHECK(exr_session_cached(session) == 2);
  source.reenter = 1;
  OK(exr_session_get(session, 5, &document, &layout, &error));
  CHECK(exr_session_cached(session) == 2 && exr_session_cached_bytes(session) == a + a);
  OK(exr_session_get(session, 0, &document, &layout, &error));
  CHECK(document == first_document && layout == first_layout && source.loads[0] == first_loads);
  OK(exr_session_get(session, 1, &document, &layout, &error));
  CHECK(source.loads[1] == second_loads + 1);
  CHECK(exr_session_cached(session) == 2 && exr_session_cached_bytes(session) == a + b);
  exr_session_clear(session);
  CHECK(!exr_session_cached_bytes(session));
  exr_session_free(session);
  exr_publication_free(publication);
}

int main(int argc, char **argv) {
  exr_font *font = NULL;
  char path[4096];
  CHECK(argc == 2);
  CHECK(snprintf(path, sizeof(path), "%s/primary.ttf", argv[1]) > 0);
  CHECK(!exr_document_memory_size(NULL) && !exr_layout_memory_size(NULL));
  CHECK(!exr_session_cached_bytes(NULL));
  CHECK(exr_session_set_budget(NULL, 0, &error) == EXR_ARGUMENT);
  accounting();
  OK(exr_font_open(path, &font, &error));
  cache_budget(font);
  exr_font_free(font);
  printf("%u cache byte budget checks passed\n", checks);
  return 0;
}
