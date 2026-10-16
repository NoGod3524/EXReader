/* SPDX-License-Identifier: GPL-3.0-only */
#include "exreader.h"
#include <math.h>
#include <miniz.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static exr_error error;
static unsigned checks;
static const char *fixtures;
static exr_font *font;
#define CHECK(x)                                                                                   \
  do {                                                                                             \
    checks++;                                                                                      \
    if (!(x)) {                                                                                    \
      fprintf(stderr, "line %d: %s (%d: %s)\n", __LINE__, #x, (int)error.code, error.message);     \
      exit(1);                                                                                     \
    }                                                                                              \
  } while (0)
#define OK(x) CHECK((x) == EXR_OK)

typedef struct {
  unsigned loads[4], released;
  int fail_layout;
} statistics;
typedef struct {
  statistics *stats;
} provider;

static void release_provider(void *context) {
  provider *p = context;
  p->stats->released++;
  free(p);
}
static exr_status load_part(void *context, size_t part, exr_document **out, exr_error *e) {
  provider *p = context;
  static const char *text[] = {"alpha native framework", "second independent text", "", "fourth text"};
  *out = NULL;
  CHECK(part < 4);
  p->stats->loads[part]++;
  if (part == 2) {
    e->code = EXR_FORMAT;
    snprintf(e->message, sizeof(e->message), "Intentionally broken host part");
    return EXR_FORMAT;
  }
  if (!part || (part == 3 && p->stats->fail_layout)) {
    exr_attribute attr = {"style", "line-height:1000px"};
    exr_node_input nodes[] = {
        {EXR_NODE_DOCUMENT, SIZE_MAX, NULL, NULL, NULL, 0},
        {EXR_NODE_CHAPTER, 0, NULL, NULL, NULL, 0},
        {EXR_NODE_PARAGRAPH, 1, NULL, NULL, part ? &attr : NULL, part ? 1 : 0},
        {EXR_NODE_TEXT, 2, NULL, text[part], NULL, 0}};
    exr_chapter_input chapter = {"zero", "units/zero.unit", 1, 1};
    exr_document_input input = {"Constructed part", nodes, 4, &chapter, 1, NULL, 0};
    return exr_document_create(&input, out, e);
  }
  return exr_document_open_memory(EXR_TXT, text[part], strlen(text[part]), out, e);
}
static exr_publication *host_publication(statistics *stats) {
  char title[] = "Open host publication", id[] = "zero", path[] = "units/zero.unit";
  char part_title[] = "A host-defined unit";
  exr_part parts[] = {{id, path, part_title, 1},
                      {"one", "units/one.unit", "One", 1},
                      {"broken", "units/broken.unit", "Broken", 1},
                      {"aux", "units/aux.unit", "Auxiliary", 0}};
  provider *context = malloc(sizeof(*context));
  exr_publication *publication = NULL;
  exr_publication_input input = {title, parts, 4, load_part, context, release_provider};
  CHECK(context);
  context->stats = stats;
  OK(exr_publication_create(&input, &publication, &error));
  CHECK(publication && !stats->released);
  memset(title, '!', sizeof(title) - 1);
  memset(id, '!', sizeof(id) - 1);
  memset(path, '!', sizeof(path) - 1);
  memset(part_title, '!', sizeof(part_title) - 1);
  memset(parts, 0, sizeof(parts));
  return publication;
}
static void local_geometry(const exr_document *doc, const exr_layout *layout) {
  size_t size, count, pages, i;
  const exr_glyph *glyphs = exr_layout_glyphs(layout, &count);
  const exr_page *page = exr_layout_pages(layout, &pages);
  CHECK(exr_document_text(doc, &size) && size && pages && count);
  CHECK(page[0].start == 0 && page[pages - 1].end == size);
  for (i = 0; i < count; i++) {
    CHECK(glyphs[i].start < glyphs[i].end && glyphs[i].end <= size);
    CHECK(glyphs[i].page < pages);
  }
}
static void host_cache(void) {
  statistics stats = {0};
  exr_publication *publication = host_publication(&stats);
  const exr_part *parts;
  const exr_document *doc = NULL, *zero_doc, *one_doc;
  const exr_layout *layout = NULL, *zero_layout, *one_layout;
  exr_document *owned = NULL;
  exr_layout *standalone = NULL;
  exr_session *session = NULL;
  exr_layout_config config = exr_layout_config_defaults();
  char css[] = "* {font-size:17px;color:#123456}";
  size_t count;
  const exr_glyph *glyphs;
  exr_bitmap bitmap = {0};
  exr_anchor anchor = {0};
  exr_anchor_match match;
  CHECK(!strcmp(exr_publication_title(publication), "Open host publication"));
  parts = exr_publication_parts(publication, &count);
  CHECK(count == 4 && !strcmp(parts[0].id, "zero"));
  CHECK(!strcmp(parts[0].path, "units/zero.unit"));
  CHECK(!strcmp(parts[0].title, "A host-defined unit") && !parts[3].in_reading_order);
  CHECK(!stats.loads[0] && !stats.loads[1] && !stats.loads[2] && !stats.loads[3]);
  CHECK(exr_session_create(publication, font, &config, 0, &session, &error) == EXR_ARGUMENT);
  CHECK(!session && !stats.released);
  CHECK(exr_session_create(publication, font, &config, 65, &session, &error) == EXR_ARGUMENT);
  CHECK(!session && !stats.released);
  config.user_css = css;
  config.page.width = 310;
  config.page.height = 420;
  OK(exr_session_create(publication, font, &config, 2, &session, &error));
  CHECK(!exr_session_cached(session) && !stats.loads[0]);
  memset(css, ' ', sizeof(css) - 1);
  config.page.width = 900;
  OK(exr_session_get(session, 0, &doc, &layout, &error));
  zero_doc = doc;
  zero_layout = layout;
  CHECK(stats.loads[0] == 1 && !stats.loads[1] && !stats.loads[2] && !stats.loads[3]);
  CHECK(exr_session_cached(session) == 1 && exr_document_format(doc) == EXR_CUSTOM);
  glyphs = exr_layout_glyphs(layout, &count);
  CHECK(count && fabsf(glyphs[0].size - 17) < 0.1f && glyphs[0].color == 0x123456ff);
  OK(exr_render_page_color(layout, font, 0, &bitmap, &error));
  CHECK(bitmap.width == 310 && bitmap.height == 420);
  exr_bitmap_free(&bitmap);
  local_geometry(doc, layout);
  OK(exr_session_get(session, 1, &doc, &layout, &error));
  one_doc = doc;
  one_layout = layout;
  CHECK(stats.loads[1] == 1 && exr_session_cached(session) == 2);
  CHECK(!strcmp(exr_document_text(doc, NULL), "second independent text"));
  OK(exr_session_get(session, 0, &doc, &layout, &error));
  CHECK(doc == zero_doc && layout == zero_layout && stats.loads[0] == 1);
  CHECK(exr_session_get(session, 2, &doc, &layout, &error) == EXR_FORMAT);
  CHECK(!doc && !layout && stats.loads[2] == 1 && exr_session_cached(session) == 2);
  OK(exr_session_get(session, 1, &doc, &layout, &error));
  CHECK(doc == one_doc && layout == one_layout && stats.loads[1] == 1);
  OK(exr_session_get(session, 0, &doc, &layout, &error));
  stats.fail_layout = 1;
  CHECK(exr_session_get(session, 3, &doc, &layout, &error) == EXR_LIMIT);
  CHECK(!doc && !layout && stats.loads[3] == 1 && exr_session_cached(session) == 2);
  OK(exr_session_get(session, 0, &doc, &layout, &error));
  CHECK(doc == zero_doc && layout == zero_layout && stats.loads[0] == 1);
  stats.fail_layout = 0;
  OK(exr_session_get(session, 3, &doc, &layout, &error));
  CHECK(stats.loads[3] == 2 && exr_session_cached(session) == 2);
  OK(exr_session_get(session, 0, &doc, &layout, &error));
  CHECK(stats.loads[0] == 1 && doc == zero_doc && layout == zero_layout);
  OK(exr_session_get(session, 1, &doc, &layout, &error));
  CHECK(stats.loads[1] == 2 && exr_session_cached(session) == 2);
  CHECK(exr_session_get(session, 4, &doc, &layout, &error) == EXR_ARGUMENT);
  CHECK(!doc && !layout && exr_session_cached(session) == 2);
  exr_session_clear(session);
  CHECK(!exr_session_cached(session));
  OK(exr_session_get(session, 1, &doc, &layout, &error));
  CHECK(stats.loads[1] == 3 && exr_session_cached(session) == 1);
  glyphs = exr_layout_glyphs(layout, &count);
  CHECK(count && fabsf(glyphs[0].size - 17) < 0.1f && glyphs[0].color == 0x123456ff);
  OK(exr_publication_load(publication, 0, &owned, &error));
  CHECK(owned && owned != doc);
  exr_publication_free(publication);
  CHECK(!stats.released);
  OK(exr_session_get(session, 3, &doc, &layout, &error));
  CHECK(stats.loads[3] == 3 && !stats.released);
  exr_session_free(session);
  CHECK(stats.released == 1);
  CHECK(!strcmp(exr_document_text(owned, NULL), "alpha native framework"));
  OK(exr_anchor_create(owned, 0, 5, &anchor, &error));
  CHECK(!strcmp(anchor.exact, "alpha") && !strcmp(anchor.chapter, "units/zero.unit"));
  OK(exr_anchor_resolve(owned, &anchor, &match, &error));
  CHECK(match.state == EXR_ANCHOR_FOUND && match.start == 0 && match.end == 5);
  OK(exr_layout_create(owned, font, NULL, &standalone, &error));
  OK(exr_render_page(standalone, font, 0, &bitmap, &error));
  CHECK(bitmap.pixels && bitmap.width && bitmap.height);
  exr_bitmap_free(&bitmap);
  exr_layout_free(standalone);
  exr_anchor_free(&anchor);
  exr_document_free(owned);
  CHECK(stats.released == 1);
}
static void ownership_on_failure(void) {
  statistics stats = {0};
  provider *context = malloc(sizeof(*context));
  exr_part part = {"part", "part.unit", "Part", 1};
  exr_publication_input input = {"Invalid source", &part, 1, NULL, context, release_provider};
  exr_publication *publication = (exr_publication *)(uintptr_t)1;
  CHECK(context);
  context->stats = &stats;
  CHECK(exr_publication_create(&input, &publication, &error) == EXR_ARGUMENT);
  CHECK(!publication && !stats.released);
  release_provider(context);
  CHECK(stats.released == 1);
}
static void reject_metadata(exr_publication_input *input, exr_status expected,
                             statistics *stats) {
  exr_publication *publication = (exr_publication *)(uintptr_t)1;
  CHECK(exr_publication_create(input, &publication, &error) == expected);
  CHECK(!publication && error.code == expected && !stats->released);
  CHECK(!stats->loads[0]);
}
static void metadata_boundaries(void) {
  statistics stats = {0};
  provider *context = malloc(sizeof(*context));
  exr_part part = {"part", "part.unit", "Part", 1};
  exr_publication_input input = {"Publication", &part, 1, load_part, context, release_provider};
  const char invalid[] = "\xc0\xaf";
  char *large = malloc(65538);
  CHECK(context && large);
  context->stats = &stats;
  memset(large, 'x', 65537);
  large[65537] = 0;
  input.title = invalid;
  reject_metadata(&input, EXR_ENCODING, &stats);
  input.title = "Publication";
  part.id = invalid;
  reject_metadata(&input, EXR_ENCODING, &stats);
  part.id = "part";
  part.path = invalid;
  reject_metadata(&input, EXR_ENCODING, &stats);
  part.path = "part.unit";
  part.title = invalid;
  reject_metadata(&input, EXR_ENCODING, &stats);
  part.title = "Part";
  input.title = large;
  reject_metadata(&input, EXR_LIMIT, &stats);
  input.title = "Publication";
  part.id = large;
  reject_metadata(&input, EXR_LIMIT, &stats);
  part.id = "part";
  part.path = large;
  reject_metadata(&input, EXR_LIMIT, &stats);
  part.path = "part.unit";
  part.title = large;
  reject_metadata(&input, EXR_LIMIT, &stats);
  part.title = "Part";
  input.part_count = 10001;
  reject_metadata(&input, EXR_LIMIT, &stats);
  input.part_count = 1;
  CHECK(exr_publication_create(&input, NULL, &error) == EXR_ARGUMENT);
  CHECK(!stats.released && !stats.loads[0]);
  free(large);
  release_provider(context);
  CHECK(stats.released == 1);
}
static void session_boundaries(void) {
  statistics stats = {0};
  exr_publication *publication = host_publication(&stats);
  exr_session *session = NULL;
  exr_layout_config config;
  const exr_document *doc = (const exr_document *)(uintptr_t)1;
  const exr_layout *layout = (const exr_layout *)(uintptr_t)1;
  exr_document *owned = (exr_document *)(uintptr_t)1;
  unsigned i;
  for (i = 0; i < 5; i++) {
    config = exr_layout_config_defaults();
    if (!i)
      config.page.width = NAN;
    else if (i == 1)
      config.page.height = INFINITY;
    else if (i == 2)
      config.page.margin = config.page.width;
    else if (i == 3)
      config.page.font_size = 1;
    else
      config.page.line_height = 0;
    session = (exr_session *)(uintptr_t)1;
    CHECK(exr_session_create(publication, font, &config, 1, &session, &error) == EXR_ARGUMENT);
    CHECK(!session && error.code == EXR_ARGUMENT && !stats.loads[0] && !stats.released);
  }
  CHECK(exr_session_create(publication, NULL, NULL, 1, &session, &error) == EXR_ARGUMENT);
  CHECK(!session && !stats.loads[0]);
  OK(exr_session_create(publication, font, NULL, 64, &session, &error));
  CHECK(!exr_session_cached(session) && !stats.loads[0]);
  CHECK(exr_publication_load(publication, 0, NULL, &error) == EXR_ARGUMENT);
  CHECK(!stats.loads[0]);
  CHECK(exr_publication_load(NULL, 0, &owned, &error) == EXR_ARGUMENT);
  CHECK(!owned);
  CHECK(exr_session_get(NULL, 0, &doc, &layout, &error) == EXR_ARGUMENT);
  CHECK(!doc && !layout);
  layout = (const exr_layout *)(uintptr_t)1;
  CHECK(exr_session_get(session, 0, NULL, &layout, &error) == EXR_ARGUMENT);
  CHECK(!layout);
  doc = (const exr_document *)(uintptr_t)1;
  CHECK(exr_session_get(session, 0, &doc, NULL, &error) == EXR_ARGUMENT);
  CHECK(!doc && !stats.loads[0] && !exr_session_cached(session));
  exr_session_free(session);
  CHECK(!stats.released);
  exr_publication_free(publication);
  CHECK(stats.released == 1);
}
typedef struct {
  unsigned calls, released, nested_calls;
  int mode;
  exr_session *session;
} edge_provider;
static void release_edge_provider(void *context) {
  edge_provider *provider = context;
  provider->released++;
}
static exr_status edge_load(void *context, size_t part, exr_document **out, exr_error *e) {
  edge_provider *provider = context;
  const char text[] = "An independent document from a host callback.";
  exr_status status;
  CHECK(part == 0);
  provider->calls++;
  *out = NULL;
  if (provider->mode == 0)
    return EXR_OK; /* Malformed success must become a clean failure. */
  if (provider->mode == 2) {
    const exr_document *doc = (const exr_document *)(uintptr_t)1;
    const exr_layout *layout = (const exr_layout *)(uintptr_t)1;
    exr_error nested = {0};
    CHECK(provider->session);
    CHECK(exr_session_get(provider->session, 0, &doc, &layout, &nested) == EXR_ARGUMENT);
    CHECK(!doc && !layout && nested.code == EXR_ARGUMENT);
    provider->nested_calls++;
  }
  status = exr_document_open_memory(EXR_TXT, text, sizeof(text) - 1, out, e);
  if (status == EXR_OK && provider->mode == 1) {
    e->code = EXR_IO;
    snprintf(e->message, sizeof(e->message), "Host failure with a partial document");
    return EXR_IO; /* Engine owns cleanup even when the loader leaves a partial result. */
  }
  return status;
}
static void callback_boundaries(void) {
  edge_provider provider = {0};
  exr_part part = {"edge", "edge.unit", "Callback edge cases", 1};
  exr_publication_input input = {"Host callback boundaries", &part, 1, edge_load, &provider,
                                 release_edge_provider};
  exr_publication *publication = NULL;
  exr_document *owned = (exr_document *)(uintptr_t)1;
  exr_session *session = NULL;
  const exr_document *doc = NULL;
  const exr_layout *layout = NULL;
  unsigned i;
  OK(exr_publication_create(&input, &publication, &error));
  CHECK(!provider.calls && !provider.released);
  CHECK(exr_publication_load(publication, 0, &owned, &error) == EXR_FORMAT);
  CHECK(!owned && provider.calls == 1);
  provider.mode = 1;
  /* ASan/LSan also checks that each intentionally abandoned partial document is freed. */
  for (i = 0; i < 4; i++) {
    owned = (exr_document *)(uintptr_t)1;
    CHECK(exr_publication_load(publication, 0, &owned, &error) == EXR_IO);
    CHECK(!owned);
  }
  OK(exr_session_create(publication, font, NULL, 1, &session, &error));
  provider.session = session;
  provider.mode = 0;
  CHECK(exr_session_get(session, 0, &doc, &layout, &error) == EXR_FORMAT);
  CHECK(!doc && !layout && !exr_session_cached(session));
  provider.mode = 1;
  CHECK(exr_session_get(session, 0, &doc, &layout, &error) == EXR_IO);
  CHECK(!doc && !layout && !exr_session_cached(session));
  provider.mode = 2;
  OK(exr_session_get(session, 0, &doc, &layout, &error));
  CHECK(doc && layout && provider.nested_calls == 1 && provider.calls == 8);
  CHECK(exr_session_cached(session) == 1);
  OK(exr_session_get(session, 0, &doc, &layout, &error));
  CHECK(provider.nested_calls == 1 && provider.calls == 8);
  exr_publication_free(publication);
  CHECK(!provider.released);
  exr_session_free(session);
  CHECK(provider.released == 1);
}
static exr_publication *open_publication(const char *name) {
  char path[4096];
  exr_publication *publication = NULL;
  snprintf(path, sizeof(path), "%s/%s", fixtures, name);
  OK(exr_publication_open(path, &publication, &error));
  return publication;
}
static const exr_glyph *glyph_with_id(const exr_document *doc, const exr_layout *layout,
                                     const char *id) {
  size_t count, i, node;
  const exr_node *nodes = exr_document_nodes(doc, NULL);
  const exr_glyph *glyphs = exr_layout_glyphs(layout, &count);
  for (i = 0; i < count; i++)
    for (node = glyphs[i].node; node != SIZE_MAX; node = nodes[node].parent) {
      const char *value = exr_node_attribute(&nodes[node], "id");
      if (value && !strcmp(value, id))
        return &glyphs[i];
    }
  return NULL;
}
static void indexed_epub(void) {
  exr_publication *publication = open_publication("structure.epub");
  exr_document *doc = NULL, *other = NULL, *aux = NULL, *eager = NULL;
  exr_layout *layout = NULL;
  const exr_part *parts;
  const exr_chapter *chapters;
  const exr_glyph *glyph;
  size_t count, resource, node, size, global_start, global_end, local_start, local_end;
  void *bytes = NULL;
  exr_bitmap bitmap = {0};
  exr_anchor anchor = {0}, from_eager = {0};
  exr_anchor_match match;
  const char *text, *selected;
  char path[4096];
  CHECK(!strcmp(exr_publication_title(publication), "Structured EPUB"));
  parts = exr_publication_parts(publication, &count);
  CHECK(count == 4);
  CHECK(!strcmp(parts[0].id, "second") && !strcmp(parts[1].id, "first"));
  CHECK(!strcmp(parts[2].id, "notes") && !strcmp(parts[3].id, "nav"));
  CHECK(parts[0].in_reading_order && parts[1].in_reading_order);
  CHECK(!parts[2].in_reading_order && !parts[3].in_reading_order);
  CHECK(!strcmp(parts[1].path, "OPS Book/text/100%-first.xhtml"));
  OK(exr_publication_load(publication, 0, &doc, &error));
  CHECK(exr_document_format(doc) == EXR_EPUB);
  chapters = exr_document_chapters(doc, &count);
  CHECK(count == 1 && !strcmp(chapters[0].path, parts[0].path));
  text = exr_document_text(doc, NULL);
  CHECK(strstr(text, "Second in manifest") && strstr(text, "Alpha bold"));
  CHECK(!strstr(text, "First in manifest") && !strstr(text, "Auxiliary note."));
  CHECK(!strstr(text, "SECRET_HIDDEN") && !strstr(text, "SECRET_SCRIPT"));
  selected = strstr(text, "Alpha");
  CHECK(selected);
  OK(exr_anchor_create(doc, (size_t)(selected - text), (size_t)(selected - text) + 5, &anchor,
                         &error));
  CHECK(!strcmp(anchor.chapter, parts[0].path));
  OK(exr_publication_load(publication, 1, &other, &error));
  CHECK(strstr(exr_document_text(other, NULL), "First in manifest"));
  CHECK(!strstr(exr_document_text(other, NULL), "Second in manifest"));
  snprintf(path, sizeof(path), "%s/structure.epub", fixtures);
  OK(exr_document_open(path, &eager, &error));
  OK(exr_document_find(eager, "Final paragraph.", 0, &global_start, &global_end, &error));
  OK(exr_document_find(other, "Final paragraph.", 0, &local_start, &local_end, &error));
  CHECK(global_start > local_start && global_end > local_end);
  OK(exr_anchor_create(eager, global_start, global_end, &from_eager, &error));
  CHECK(!strcmp(from_eager.chapter, parts[1].path));
  OK(exr_anchor_resolve(other, &from_eager, &match, &error));
  CHECK(match.state == EXR_ANCHOR_FOUND && match.start == local_start && match.end == local_end);
  /* Resolution returns a part-local range; it never rewrites the saved global hint. */
  CHECK(from_eager.start == global_start && from_eager.end == global_end);
  exr_anchor_free(&from_eager);
  exr_document_free(eager);
  OK(exr_publication_load(publication, 2, &aux, &error));
  CHECK(strstr(exr_document_text(aux, NULL), "Auxiliary note."));
  exr_document_free(aux);
  aux = NULL;
  OK(exr_publication_load(publication, 3, &aux, &error));
  CHECK(strstr(exr_document_text(aux, NULL), "Chapter two"));
  exr_document_free(aux);
  exr_document_free(other);
  exr_publication_free(publication);
  /* Owned part documents keep their resource backing after the index is freed. */
  OK(exr_document_resolve(doc, 0, "../images/pic.png", &resource, &node, &error));
  CHECK(resource != SIZE_MAX && node == SIZE_MAX);
  OK(exr_document_resource(doc, resource, &bytes, &size, &error));
  CHECK(size > 8 && !memcmp(bytes, "\x89PNG\r\n\x1a\n", 8));
  exr_free(bytes);
  bytes = NULL;
  OK(exr_document_resolve(doc, 0, "../styles/main.css", &resource, &node, &error));
  CHECK(resource != SIZE_MAX);
  OK(exr_document_resource(doc, resource, &bytes, &size, &error));
  CHECK(size && memchr(bytes, '{', size));
  exr_free(bytes);
  OK(exr_layout_create(doc, font, NULL, &layout, &error));
  glyph = glyph_with_id(doc, layout, "local");
  CHECK(glyph && fabsf(glyph->size - 28.8f) < 0.1f && glyph->color == 0x123456ff);
  local_geometry(doc, layout);
  OK(exr_render_page_color(layout, font, 0, &bitmap, &error));
  CHECK(bitmap.pixels && bitmap.channels == 4);
  exr_bitmap_free(&bitmap);
  OK(exr_anchor_resolve(doc, &anchor, &match, &error));
  CHECK(match.state == EXR_ANCHOR_FOUND && match.start == anchor.start && match.end == anchor.end);
  exr_anchor_free(&anchor);
  exr_layout_free(layout);
  exr_document_free(doc);
  publication = open_publication("structure-broken.epub");
  doc = (exr_document *)(uintptr_t)1;
  CHECK(exr_publication_load(publication, 0, &doc, &error) == EXR_FORMAT);
  CHECK(!doc);
  OK(exr_publication_load(publication, 1, &doc, &error));
  CHECK(strstr(exr_document_text(doc, NULL), "First in manifest"));
  exr_document_free(doc);
  exr_publication_free(publication);
}
static void add_member(mz_zip_archive *zip, const char *path, const char *data, size_t size) {
  CHECK(mz_zip_writer_add_mem(zip, path, data, size, MZ_BEST_SPEED));
}
static void *large_epub(size_t *size) {
  enum { PARTS = 400, PARAGRAPHS = 128 };
  const char container[] = "<container><rootfiles><rootfile full-path=\"book.opf\"/>"
                           "</rootfiles></container>";
  mz_zip_archive zip = {0};
  char *opf = malloc(PARTS * 192 + 1024), *chapter = malloc(32768);
  char path[64];
  void *bytes = NULL;
  size_t used;
  unsigned i, j;
  CHECK(opf && chapter);
  used = (size_t)snprintf(opf, PARTS * 192 + 1024,
                          "<package><metadata><title>Four hundred independent parts</title>"
                          "</metadata><manifest>");
  for (i = 0; i < PARTS; i++)
    used += (size_t)snprintf(opf + used, PARTS * 192 + 1024 - used,
                             "<item id=\"p%u\" href=\"part%u.xhtml\" "
                             "media-type=\"application/xhtml+xml\"/>", i, i);
  used += (size_t)snprintf(opf + used, PARTS * 192 + 1024 - used, "</manifest><spine>");
  for (i = 0; i < PARTS; i++)
    used += (size_t)snprintf(opf + used, PARTS * 192 + 1024 - used,
                             "<itemref idref=\"p%u\"/>", i);
  used += (size_t)snprintf(opf + used, PARTS * 192 + 1024 - used, "</spine></package>");
  CHECK(used < PARTS * 192 + 1024);
  CHECK(mz_zip_writer_init_heap(&zip, 0, 0));
  add_member(&zip, "mimetype", "application/epub+zip", 20);
  add_member(&zip, "META-INF/container.xml", container, sizeof(container) - 1);
  add_member(&zip, "book.opf", opf, used);
  for (i = 0; i < PARTS; i++) {
    used = (size_t)snprintf(chapter, 32768,
                            "<html xmlns=\"http://www.w3.org/1999/xhtml\"><head/>"
                            "<body>");
    if (i + 1 == PARTS)
      used += (size_t)snprintf(chapter + used, 32768 - used, "<p>Broken final chapter</body>");
    else {
      for (j = 0; j < PARAGRAPHS; j++)
        used += (size_t)snprintf(chapter + used, 32768 - used,
                                 "<p>Only chapter %04u, paragraph %03u: The native framework "
                                 "loads this independent unit on demand and keeps every other "
                                 "chapter out of its document tree.</p>", i, j);
      used += (size_t)snprintf(chapter + used, 32768 - used, "</body></html>");
    }
    CHECK(used < 32768);
    snprintf(path, sizeof(path), "part%u.xhtml", i);
    add_member(&zip, path, chapter, used);
  }
  CHECK(mz_zip_writer_finalize_heap_archive(&zip, &bytes, size));
  mz_zip_writer_end(&zip);
  free(opf);
  free(chapter);
  CHECK(bytes && *size);
  return bytes;
}
static void many_parts(void) {
  exr_publication *publication = NULL;
  exr_session *session = NULL;
  const exr_document *doc = NULL, *first_doc;
  const exr_layout *layout = NULL, *first_layout;
  const exr_part *parts;
  size_t size, count;
  void *bytes = large_epub(&size);
  /* More than seven MiB of XHTML, but indexing never parses the broken last part.
     Parts remain atomic: this test promises neither page-level suspension nor a
     hard byte budget for one exceptionally large part or its temporary work. */
  OK(exr_publication_open_memory(EXR_EPUB, bytes, size, &publication, &error));
  memset(bytes, 0, size);
  mz_free(bytes);
  parts = exr_publication_parts(publication, &count);
  CHECK(count == 400 && !strcmp(parts[399].id, "p399"));
  OK(exr_session_create(publication, font, NULL, 1, &session, &error));
  CHECK(!exr_session_cached(session));
  OK(exr_session_get(session, 0, &doc, &layout, &error));
  first_doc = doc;
  first_layout = layout;
  CHECK(strstr(exr_document_text(doc, &size), "Only chapter 0000"));
  CHECK(!strstr(exr_document_text(doc, NULL), "Only chapter 0001"));
  CHECK(size > 16000 && size < 32768 && exr_session_cached(session) == 1);
  exr_document_nodes(doc, &count);
  CHECK(count < 1000);
  local_geometry(doc, layout);
  CHECK(exr_session_get(session, 399, &doc, &layout, &error) == EXR_FORMAT);
  CHECK(!doc && !layout && exr_session_cached(session) == 1);
  OK(exr_session_get(session, 0, &doc, &layout, &error));
  CHECK(doc == first_doc && layout == first_layout);
  OK(exr_session_get(session, 398, &doc, &layout, &error));
  CHECK(strstr(exr_document_text(doc, NULL), "Only chapter 0398"));
  CHECK(!strstr(exr_document_text(doc, NULL), "Only chapter 0000"));
  CHECK(exr_session_cached(session) == 1);
  exr_publication_free(publication);
  exr_session_clear(session);
  CHECK(!exr_session_cached(session));
  OK(exr_session_get(session, 1, &doc, &layout, &error));
  CHECK(strstr(exr_document_text(doc, NULL), "Only chapter 0001"));
  exr_session_free(session);
}
int main(int argc, char **argv) {
  const char *font_path = getenv("EXR_TEST_FONT");
  CHECK(argc == 2);
  fixtures = argv[1];
#ifdef _WIN32
  if (!font_path)
    font_path = "C:/Windows/Fonts/arial.ttf";
#elif defined(__APPLE__)
  if (!font_path)
    font_path = "/System/Library/Fonts/Supplemental/Arial.ttf";
#else
  if (!font_path)
    font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf";
#endif
  OK(exr_font_open(font_path, &font, &error));
  ownership_on_failure();
  metadata_boundaries();
  session_boundaries();
  callback_boundaries();
  host_cache();
  indexed_epub();
  many_parts();
  exr_font_free(font);
  printf("EXReader lazy loading: %u checks passed\n", checks);
  return 0;
}
