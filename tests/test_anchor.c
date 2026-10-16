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
      fprintf(stderr, "line %d: %s (%d: %s)\n", __LINE__, #x, (int)error.code, error.message);       \
      exit(1);                                                                                     \
    }                                                                                              \
  } while (0)
#define OK(x) CHECK((x) == EXR_OK)

static exr_document *open_text(exr_format format, const char *text) {
  exr_document *doc = NULL;
  OK(exr_document_open_memory(format, text, strlen(text), &doc, &error));
  CHECK(doc);
  return doc;
}

static exr_document *custom(const char *const *texts, const char *const *paths,
                            const int *reading, size_t count) {
  exr_node_input *nodes = calloc(1 + count * 3, sizeof(*nodes));
  exr_chapter_input *chapters = calloc(count, sizeof(*chapters));
  exr_document_input input = {0};
  exr_document *doc = NULL;
  size_t i;
  CHECK(nodes && chapters);
  nodes[0].kind = EXR_NODE_DOCUMENT;
  nodes[0].parent = SIZE_MAX;
  for (i = 0; i < count; i++) {
    size_t root = 1 + i * 3;
    nodes[root].kind = EXR_NODE_CHAPTER;
    nodes[root].parent = 0;
    nodes[root + 1].kind = EXR_NODE_PARAGRAPH;
    nodes[root + 1].parent = root;
    nodes[root + 2].kind = EXR_NODE_TEXT;
    nodes[root + 2].parent = root + 1;
    nodes[root + 2].text = texts[i];
    chapters[i].path = paths[i];
    chapters[i].root = root;
    chapters[i].in_reading_order = reading ? reading[i] : 1;
  }
  input.nodes = nodes;
  input.node_count = 1 + count * 3;
  input.chapters = chapters;
  input.chapter_count = count;
  OK(exr_document_create(&input, &doc, &error));
  free(chapters);
  free(nodes);
  CHECK(doc);
  return doc;
}

static void match(const exr_document *doc, const exr_anchor *anchor, exr_anchor_state state,
                   size_t start) {
  exr_anchor_match result = {EXR_ANCHOR_FOUND, 123, 456};
  OK(exr_anchor_resolve(doc, anchor, &result, &error));
  CHECK(result.state == state);
  if (state == EXR_ANCHOR_FOUND) {
    CHECK(result.start == start);
    CHECK(result.end == start + strlen(anchor->exact));
  } else
    CHECK(result.start == SIZE_MAX && result.end == SIZE_MAX);
}

static void clear_anchor(exr_anchor *anchor) {
  exr_anchor_free(anchor);
  CHECK(!anchor->start && !anchor->end && !anchor->exact && !anchor->prefix &&
        !anchor->suffix && !anchor->chapter);
}

static void reject_create(const exr_document *doc, size_t start, size_t end) {
  exr_anchor anchor = {0};
  exr_status status = exr_anchor_create(doc, start, end, &anchor, &error);
  CHECK(status != EXR_OK && error.code == status);
  CHECK(!anchor.start && !anchor.end && !anchor.exact && !anchor.prefix && !anchor.suffix &&
        !anchor.chapter);
}

static void reject_selector(const exr_document *doc, const exr_anchor *anchor,
                             exr_status expected) {
  exr_anchor_match result = {EXR_ANCHOR_FOUND, 123, 456};
  exr_status status = exr_anchor_resolve(doc, anchor, &result, &error);
  CHECK(status != EXR_OK && error.code == status);
  if (expected != EXR_OK)
    CHECK(status == expected);
}

static void capture_and_relocate(void) {
  const char left[] = "abcdefghijklmnopqrstuvwxyzABCDEF";
  const char right[] = "0123456789abcdefghijklmnopqrstuv";
  char source[256], changed[320];
  exr_document *original, *updated;
  exr_anchor anchor = {0};
  size_t start;
  snprintf(source, sizeof(source), "before-%sTARGET%s-after", left, right);
  original = open_text(EXR_TXT, source);
  start = (size_t)(strstr(exr_document_text(original, NULL), "TARGET") -
                   exr_document_text(original, NULL));
  OK(exr_anchor_create(original, start, start + 6, &anchor, &error));
  CHECK(anchor.start == start && anchor.end == start + 6);
  CHECK(anchor.exact && !strcmp(anchor.exact, "TARGET"));
  CHECK(anchor.prefix && !strcmp(anchor.prefix, left));
  CHECK(anchor.suffix && !strcmp(anchor.suffix, right));
  match(original, &anchor, EXR_ANCHOR_FOUND, start);
  snprintf(changed, sizeof(changed), "Inserted frontmatter. %s", source);
  memset(source, '!', sizeof(source));
  exr_document_free(original);
  CHECK(!strcmp(anchor.exact, "TARGET") && !strcmp(anchor.prefix, left) &&
        !strcmp(anchor.suffix, right));
  updated = open_text(EXR_TXT, changed);
  anchor.start = 0;
  anchor.end = 6;
  match(updated, &anchor, EXR_ANCHOR_FOUND, start + strlen("Inserted frontmatter. "));
  exr_document_free(updated);
  snprintf(changed, sizeof(changed), "%sTARGXT%s", left, right);
  updated = open_text(EXR_TXT, changed);
  match(updated, &anchor, EXR_ANCHOR_MISSING, 0);
  exr_document_free(updated);
  updated = open_text(EXR_TXT, "The original was deleted. A different TARGET is left here.");
  match(updated, &anchor, EXR_ANCHOR_MISSING, 0);
  exr_document_free(updated);
  clear_anchor(&anchor);
  clear_anchor(&anchor);
  exr_anchor_free(NULL);
}

static void repeated_text(void) {
  char left[33], right[33], other[33], source[128], changed[256];
  exr_document *doc;
  exr_anchor anchor = {0};
  memset(left, 'a', 32);
  memset(right, 'b', 32);
  memset(other, 'c', 32);
  left[32] = right[32] = other[32] = 0;
  snprintf(source, sizeof(source), "%sTOKEN%s", left, right);
  doc = open_text(EXR_TXT, source);
  OK(exr_anchor_create(doc, 32, 37, &anchor, &error));
  exr_document_free(doc);

  snprintf(changed, sizeof(changed), "%s|%s", source, source);
  doc = open_text(EXR_TXT, changed);
  /* The saved offset still points at a match: it must not hide the duplicate. */
  match(doc, &anchor, EXR_ANCHOR_AMBIGUOUS, 0);
  exr_document_free(doc);

  snprintf(changed, sizeof(changed), "%sTOKEN%s|%s", other, other, source);
  doc = open_text(EXR_TXT, changed);
  match(doc, &anchor, EXR_ANCHOR_FOUND, strlen(source) + 1 + 32);
  exr_document_free(doc);

  snprintf(changed, sizeof(changed), "%sTOKEN%s|%s", left, other, source);
  doc = open_text(EXR_TXT, changed);
  /* Both complete contexts beat an earlier candidate with only one. */
  match(doc, &anchor, EXR_ANCHOR_FOUND, strlen(source) + 1 + 32);
  exr_document_free(doc);

  snprintf(changed, sizeof(changed), "%sTOKEN%s|%sTOKEN%s", left, other, other, right);
  doc = open_text(EXR_TXT, changed);
  match(doc, &anchor, EXR_ANCHOR_AMBIGUOUS, 0);
  exr_document_free(doc);

  /* A partial common suffix is not a complete context match. */
  snprintf(changed, sizeof(changed), "aTOKENb");
  doc = open_text(EXR_TXT, changed);
  match(doc, &anchor, EXR_ANCHOR_MISSING, 0);
  exr_document_free(doc);
  clear_anchor(&anchor);
}

static void chapter_scope(void) {
  const char body[] = "abcdefghijklmnopqrstuvwxyzABCDEFTOKEN0123456789abcdefghijklmnopqrstuv";
  const char *texts[] = {body, body, body};
  const char *paths[] = {"chapters/one.unit", "chapters/two.unit", "notes.unit"};
  const char *renamed[] = {"chapters/renamed.unit", "chapters/two.unit", "notes.unit"};
  int reading[] = {1, 1, 0};
  exr_document *doc = custom(texts, paths, reading, 3), *updated;
  exr_anchor first = {0}, second = {0}, cross = {0}, whole = {0}, host;
  size_t second_start = strlen(body) + 1 + 32;
  OK(exr_anchor_create(doc, 32, 37, &first, &error));
  CHECK(first.chapter && !strcmp(first.chapter, paths[0]));
  CHECK(first.chapter != paths[0]);
  match(doc, &first, EXR_ANCHOR_FOUND, 32);
  OK(exr_anchor_create(doc, second_start, second_start + 5, &second, &error));
  CHECK(second.chapter && !strcmp(second.chapter, paths[1]));
  match(doc, &second, EXR_ANCHOR_FOUND, second_start);
  OK(exr_anchor_create(doc, strlen(body) + 1, strlen(body) * 2 + 1, &whole, &error));
  CHECK(whole.chapter && !strcmp(whole.chapter, paths[1]));
  CHECK(whole.prefix && !whole.prefix[0] && whole.suffix && !whole.suffix[0]);
  match(doc, &whole, EXR_ANCHOR_FOUND, strlen(body) + 1);
  OK(exr_anchor_create(doc, 32, second_start + 5, &cross, &error));
  CHECK(!cross.chapter);
  match(doc, &cross, EXR_ANCHOR_FOUND, 32);
  updated = custom(texts, renamed, reading, 3);
  match(updated, &first, EXR_ANCHOR_MISSING, 0);
  host = first;
  host.chapter = NULL;
  match(updated, &host, EXR_ANCHOR_AMBIGUOUS, 0);
  host.chapter = "notes.unit";
  match(updated, &host, EXR_ANCHOR_MISSING, 0);
  exr_document_free(updated);
  exr_document_free(doc);
  CHECK(!strcmp(first.chapter, paths[0]));
  clear_anchor(&first);
  clear_anchor(&second);
  clear_anchor(&cross);
  clear_anchor(&whole);
}

static void different_formats(void) {
  const char plain[] = "Before the selected text after the selected text.";
  const char html[] = "<html><body><p>Before the selected text after the selected text.</p></body></html>";
  exr_document *a = open_text(EXR_TXT, plain), *b = open_text(EXR_HTML, html);
  exr_anchor anchor = {0}, host;
  CHECK(!strcmp(exr_document_text(a, NULL), exr_document_text(b, NULL)));
  OK(exr_anchor_create(a, 11, 24, &anchor, &error));
  host = anchor;
  /* Hosts may clear a format-specific chapter path when changing containers. */
  host.chapter = NULL;
  match(b, &host, EXR_ANCHOR_FOUND, 11);
  exr_document_free(a);
  exr_document_free(b);
  clear_anchor(&anchor);
}

static void point_bookmarks(void) {
  exr_document *doc = open_text(EXR_TXT, "aa|bb"), *updated;
  exr_anchor middle = {0}, begin = {0}, end = {0}, empty = {0};
  const char *empty_text[] = {""}, *empty_path[] = {"empty.unit"};
  const char *nonempty_text[] = {"new content"};
  OK(exr_anchor_create(doc, 3, 3, &middle, &error));
  CHECK(middle.exact && !middle.exact[0]);
  CHECK(!strcmp(middle.prefix, "aa|") && !strcmp(middle.suffix, "bb"));
  match(doc, &middle, EXR_ANCHOR_FOUND, 3);
  updated = open_text(EXR_TXT, "intro-aa|bb-tail");
  match(updated, &middle, EXR_ANCHOR_FOUND, 9);
  exr_document_free(updated);
  updated = open_text(EXR_TXT, "aa|bb;aa|bb");
  match(updated, &middle, EXR_ANCHOR_AMBIGUOUS, 0);
  exr_document_free(updated);
  updated = open_text(EXR_TXT, "wrong|other");
  match(updated, &middle, EXR_ANCHOR_MISSING, 0);
  exr_document_free(updated);
  OK(exr_anchor_create(doc, 0, 0, &begin, &error));
  CHECK(begin.prefix && !begin.prefix[0]);
  match(doc, &begin, EXR_ANCHOR_FOUND, 0);
  OK(exr_anchor_create(doc, 5, 5, &end, &error));
  CHECK(end.suffix && !end.suffix[0]);
  match(doc, &end, EXR_ANCHOR_FOUND, 5);
  /* An empty saved side is a scope boundary even when the other side changed. */
  updated = open_text(EXR_TXT, "XYZ");
  match(updated, &begin, EXR_ANCHOR_FOUND, 0);
  match(updated, &end, EXR_ANCHOR_FOUND, 3);
  exr_document_free(updated);
  /* Boundary and text searches can produce the same best candidate; the full
     two-sided match wins over the other occurrence without counting a tie. */
  updated = open_text(EXR_TXT, "aa|bb-aa|bb");
  match(updated, &begin, EXR_ANCHOR_FOUND, 0);
  match(updated, &end, EXR_ANCHOR_FOUND, 11);
  exr_document_free(updated);
  exr_document_free(doc);
  doc = custom(empty_text, empty_path, NULL, 1);
  OK(exr_anchor_create(doc, 0, 0, &empty, &error));
  CHECK(empty.exact && !empty.exact[0] && empty.prefix && !empty.prefix[0] && empty.suffix &&
        !empty.suffix[0]);
  match(doc, &empty, EXR_ANCHOR_FOUND, 0);
  updated = custom(nonempty_text, empty_path, NULL, 1);
  match(updated, &empty, EXR_ANCHOR_MISSING, 0);
  exr_document_free(updated);
  exr_document_free(doc);
  clear_anchor(&middle);
  clear_anchor(&begin);
  clear_anchor(&end);
  clear_anchor(&empty);
}

static void unicode_and_validation(void) {
  const char chinese[] = "\xe4\xb8\xad";
  const char emoji[] = "\xf0\x9f\x98\x80";
  char source[320], invalid[] = "\xf0\x28\x8c\x28", long_context[34];
  char long_chapter[2049];
  exr_document *doc;
  exr_anchor anchor = {0}, point = {0}, host, legacy = {7, 13, NULL, NULL, NULL, NULL};
  size_t i, size, start = 40 * 3;
  for (i = 0; i < 40; i++)
    memcpy(source + i * 3, chinese, 3);
  memcpy(source + start, emoji, 4);
  memcpy(source + start + 4, chinese, 3);
  for (i = 0; i < 40; i++)
    memcpy(source + start + 7 + i * 4, emoji, 4);
  source[start + 7 + 40 * 4] = 0;
  doc = open_text(EXR_TXT, source);
  exr_document_text(doc, &size);
  OK(exr_anchor_create(doc, start, start + 7, &anchor, &error));
  CHECK(strlen(anchor.exact) == 7 && !memcmp(anchor.exact, source + start, 7));
  CHECK(strlen(anchor.prefix) == 32 * 3 && !memcmp(anchor.prefix, source + 8 * 3, 32 * 3));
  CHECK(strlen(anchor.suffix) == 32 * 4 && !memcmp(anchor.suffix, source + start + 7, 32 * 4));
  match(doc, &anchor, EXR_ANCHOR_FOUND, start);
  OK(exr_anchor_create(doc, start, start, &point, &error));
  match(doc, &point, EXR_ANCHOR_FOUND, start);
  reject_create(doc, 1, start);
  reject_create(doc, start + 1, start + 7);
  reject_create(doc, start, start + 1);
  reject_create(doc, start + 7, start);
  reject_create(doc, 0, size + 1);
  reject_create(doc, 0, SIZE_MAX);
  reject_create(NULL, 0, 0);
  CHECK(exr_anchor_create(doc, 0, 0, NULL, &error) != EXR_OK);
  host = anchor;
  host.exact = invalid;
  reject_selector(doc, &host, EXR_ENCODING);
  host = anchor;
  host.prefix = invalid;
  reject_selector(doc, &host, EXR_ENCODING);
  host = anchor;
  host.suffix = invalid;
  reject_selector(doc, &host, EXR_ENCODING);
  host = anchor;
  host.chapter = invalid;
  reject_selector(doc, &host, EXR_ENCODING);
  memset(long_context, 'a', sizeof(long_context) - 1);
  long_context[sizeof(long_context) - 1] = 0;
  host = anchor;
  host.prefix = long_context;
  reject_selector(doc, &host, EXR_OK);
  host = anchor;
  host.suffix = long_context;
  reject_selector(doc, &host, EXR_OK);
  memset(long_chapter, 'a', sizeof(long_chapter) - 1);
  long_chapter[sizeof(long_chapter) - 1] = 0;
  host = anchor;
  host.chapter = long_chapter;
  reject_selector(doc, &host, EXR_OK);
  match(doc, &legacy, EXR_ANCHOR_LEGACY, 0);
  legacy.start = legacy.end = SIZE_MAX;
  match(doc, &legacy, EXR_ANCHOR_LEGACY, 0);
  exr_document_free(doc);
  clear_anchor(&anchor);
  clear_anchor(&point);
}

static void selection_limit(void) {
  const size_t limit = 64 * 1024;
  char *source = malloc(limit + 2);
  exr_document *doc;
  exr_anchor anchor = {0}, host = {0};
  CHECK(source);
  memset(source, 'x', limit + 1);
  source[limit + 1] = 0;
  doc = open_text(EXR_TXT, source);
  OK(exr_anchor_create(doc, 0, limit, &anchor, &error));
  CHECK(strlen(anchor.exact) == limit);
  match(doc, &anchor, EXR_ANCHOR_FOUND, 0);
  reject_create(doc, 0, limit + 1);
  host.exact = source;
  host.prefix = host.suffix = "";
  reject_selector(doc, &host, EXR_OK);
  exr_document_free(doc);
  free(source);
  clear_anchor(&anchor);
}

int main(void) {
  capture_and_relocate();
  repeated_text();
  chapter_scope();
  different_formats();
  point_bookmarks();
  unicode_and_validation();
  selection_limit();
  printf("%u text anchor checks passed\n", checks);
  return 0;
}
