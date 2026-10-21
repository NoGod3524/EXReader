/* SPDX-License-Identifier: MIT */
#include "chapter_internal.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static exr_error error;
static size_t checks;
static size_t scenario;
#define BUDGET ((size_t)32*1024*1024)
#define CHECK(x) do { checks++; if (!(x)) { fprintf(stderr, "chapter index line %d: %s (%d)\n", __LINE__, #x, error.code); exit(1); } } while (0)
#define OK(x) CHECK((x) == EXR_OK)

static size_t coordinate(uint32_t v) { return v == EXR_CHAPTER_NONE ? SIZE_MAX : (size_t)v; }

static void equivalent(const char *xml, size_t chunk) {
  exr_document *snapshot = NULL;
  exr_chapter_index *index = NULL;
  size_t size = strlen(xml), at, i;
  OK(exr_xml_memory_tree(xml, size, "html", &snapshot, &error));
  snapshot->format = EXR_EPUB; /* Match the chapter loader's HTML tag semantics. */
  OK(exr_model_finish(snapshot, &error));
  OK(exr_chapter_index_begin(NULL, BUDGET, &index, &error));
  for (at = 0; at < size;) {
    size_t part = size - at < chunk ? size - at : chunk;
    OK(exr_chapter_index_feed(index, xml + at, part, chunk == 32768 && at + part == size, &error));
    CHECK(exr_chapter_index_memory(index) <= BUDGET);
    at += part;
  }
  if (chunk != 32768) OK(exr_chapter_index_feed(index, NULL, 0, 1, &error));
  CHECK(exr_chapter_index_count(index) == snapshot->node_count);
  if (exr_chapter_index_text_size(index) != snapshot->size)
    fprintf(stderr, "scenario=%zu chunk=%zu projected index=%zu snapshot=%zu\n", scenario, chunk,
      exr_chapter_index_text_size(index), snapshot->size);
  CHECK(exr_chapter_index_text_size(index) == snapshot->size);
  for (i = 0; i < snapshot->node_count; i++) {
    const exr_node *a = &snapshot->nodes[i];
    const exr_chapter_entry *b = exr_chapter_index_entry(index, i);
    const char *name = exr_chapter_index_name(index, i);
    if (b && (coordinate(b->start) != a->start || coordinate(b->end) != a->end))
      fprintf(stderr, "scenario=%zu chunk=%zu node=%zu kind=%u range index=%zu:%zu snapshot=%zu:%zu\n",
        scenario, chunk, i, (unsigned)a->kind, coordinate(b->start), coordinate(b->end), a->start, a->end);
    CHECK(b != NULL);
    CHECK((b->tag_kind & 255u) == (unsigned)a->kind);
    CHECK((!a->name && !name) || (a->name && name && !strcmp(a->name, name)));
    CHECK(coordinate(b->parent) == a->parent);
    CHECK(coordinate(b->first_child) == a->first_child);
    CHECK(coordinate(b->next_sibling) == a->next_sibling);
    CHECK(coordinate(b->start) == a->start);
    CHECK(coordinate(b->end) == a->end);
    CHECK(b->source_start <= b->source_end && b->source_end <= size);
    if (i > 1 && a->kind != EXR_NODE_TEXT) CHECK(xml[b->source_start] == '<');
  }
  CHECK(exr_chapter_index_entry(index, snapshot->node_count) == NULL);
  CHECK(exr_chapter_index_name(index, snapshot->node_count) == NULL);
  CHECK(exr_chapter_index_feed(index, NULL, 0, 1, &error) == EXR_ARGUMENT);
  exr_chapter_index_free(index);
  exr_document_free(snapshot);
}

static void snapshots(void) {
  static const char *cases[] = {
    "<html/>",
    "<html><head><title>title</title><style>p{color:red}</style></head><body><p>visible</p><div hidden=''><p>hidden</p></div><script>skip</script><object><span>skip</span></object><template>skip</template><p>tail</p></body></html>",
    "<html> \n<body><p> a <em> \t b &amp; c </em> d </p> \n<p>  </p><p><span/> e <span> f </span> </p></body></html>",
    "<?xml version='1.0'?><html><body><p>A<!--comment-->B<![CDATA[ C]]>&#x1F600;&#169;&lt;&quot;&apos;</p><?done value?><p>last</p></body></html>",
    "<h:html xmlns:h='http://www.w3.org/1999/xhtml' xmlns:z='urn:custom'><h:body><h:p xml:lang='zh'>\xe4\xb8\xad\xe6\x96\x87 <z:q>\xf0\x9f\x98\x80</z:q></h:p><h:p>next</h:p></h:body></h:html>",
    "<html xmlns:epub='http://www.idpf.org/2007/ops'><body><aside epub:type='other footnote'>one</aside><section role='doc-endnote other'><p>two</p></section><p role='doc-footnote'>three</p></body></html>",
    "<html><body><h1>Heading</h1><ul><li>one</li><li>two<br/>three<img src='x.png'/></li></ul><table><tr><td>A</td><td/></tr></table><hr/><p/></body></html>",
    "<html><body><div>before<span> </span><div>nested</div> after <b>bold</b></div><pre> x \n y </pre></body></html>"
  };
  static const size_t chunks[] = {1, 2, 3, 7, 31, 32768};
  size_t i, j;
  for (i = 0; i < sizeof(cases)/sizeof(cases[0]); i++) {
    scenario = i;
    for (j = 0; j < sizeof(chunks)/sizeof(chunks[0]); j++) equivalent(cases[i], chunks[j]);
  }
}

static void rejected(const char *xml, exr_status expected) {
  exr_chapter_index *index = NULL;
  OK(exr_chapter_index_begin(NULL, BUDGET, &index, &error));
  CHECK(exr_chapter_index_feed(index, xml, strlen(xml), 1, &error) == expected);
  CHECK(exr_chapter_index_feed(index, NULL, 0, 0, &error) == expected);
  CHECK(exr_chapter_index_memory(index) <= BUDGET);
  exr_chapter_index_free(index);
}

typedef struct { unsigned calls, after; } cancel_state;
static int cancel(void *context) { cancel_state *s = context; return ++s->calls > s->after; }

static void failures(void) {
  exr_chapter_index *index = (exr_chapter_index *)(uintptr_t)1;
  char xml[8192];
  size_t i, used;
  cancel_state state = {0, UINT_MAX};
  exr_control control = {0};
  CHECK(exr_chapter_index_begin(NULL, 0, &index, &error) == EXR_LIMIT && index == NULL);
  CHECK(exr_chapter_index_begin(NULL, BUDGET, NULL, &error) == EXR_ARGUMENT);
  CHECK(exr_chapter_index_feed(NULL, NULL, 0, 1, &error) == EXR_ARGUMENT);
  CHECK(exr_chapter_index_entry(NULL, 0) == NULL && exr_chapter_index_name(NULL, 0) == NULL);
  CHECK(!exr_chapter_index_count(NULL) && !exr_chapter_index_text_size(NULL) && !exr_chapter_index_memory(NULL));
  exr_chapter_index_free(NULL);
  rejected("<html><p></html>", EXR_FORMAT);
  rejected("<other/>", EXR_FORMAT);
  rejected("<!DOCTYPE html [<!ENTITY local 'text'>]><html>&local;</html>", EXR_FORMAT);
  rejected("<html>&unknown;</html>", EXR_FORMAT);
  rejected("<html>\xc0\xaf</html>", EXR_FORMAT);
  used = (size_t)snprintf(xml, sizeof(xml), "<html>");
  for (i = 0; i < 255; i++) { memcpy(xml + used, "<g>", 3); used += 3; }
  for (i = 0; i < 255; i++) { memcpy(xml + used, "</g>", 4); used += 4; }
  memcpy(xml + used, "</html>", 8);
  equivalent(xml, 17);
  used = (size_t)snprintf(xml, sizeof(xml), "<html>");
  for (i = 0; i < 256; i++) { memcpy(xml + used, "<g>", 3); used += 3; }
  for (i = 0; i < 256; i++) { memcpy(xml + used, "</g>", 4); used += 4; }
  memcpy(xml + used, "</html>", 8);
  rejected(xml, EXR_LIMIT);
  used = (size_t)snprintf(xml, sizeof(xml), "<html");
  for (i = 0; i < 256; i++) used += (size_t)snprintf(xml + used, sizeof(xml) - used, " a%zu='x'", i);
  (void)snprintf(xml + used, sizeof(xml) - used, "/>");
  equivalent(xml, 17);
  used = (size_t)snprintf(xml, sizeof(xml), "<html");
  for (i = 0; i < 257; i++) used += (size_t)snprintf(xml + used, sizeof(xml) - used, " a%zu='x'", i);
  (void)snprintf(xml + used, sizeof(xml) - used, "/>");
  rejected(xml, EXR_LIMIT);
  control.context = &state; control.cancelled = cancel;
  OK(exr_chapter_index_begin(&control, BUDGET, &index, &error));
  OK(exr_chapter_index_feed(index, "<html>", 6, 0, &error));
  state.after = state.calls;
  CHECK(exr_chapter_index_feed(index, "<p>x</p></html>", 14, 1, &error) == EXR_CANCELLED);
  CHECK(exr_chapter_index_feed(index, NULL, 0, 0, &error) == EXR_CANCELLED);
  exr_chapter_index_free(index);
  OK(exr_chapter_index_begin(NULL, 200*1024, &index, &error));
  OK(exr_chapter_index_feed(index, "<html>", 6, 0, &error));
  for (i = 0; i < 4096; i++) {
    exr_status status = exr_chapter_index_feed(index, "<p>x</p>", 8, 0, &error);
    if (status != EXR_OK) { CHECK(status == EXR_LIMIT); break; }
  }
  CHECK(i < 4096);
  CHECK(exr_chapter_index_memory(index) <= 200*1024);
  exr_chapter_index_free(index);
  OK(exr_chapter_index_begin(NULL, BUDGET, &index, &error));
  CHECK(exr_chapter_index_feed(index, NULL, 1, 0, &error) == EXR_ARGUMENT);
  OK(exr_chapter_index_feed(index, "<html/>", 7, 1, &error));
  exr_chapter_index_free(index);
}

static void large_index(size_t mib) {
  char chunk[32768];
  exr_chapter_index *index = NULL;
  size_t i, blocks = mib*1024, peak = 0;
  for (i = 0; i < sizeof(chunk); i += 1024) {
    memcpy(chunk + i, "<p>", 3); memset(chunk + i + 3, 'x', 1017); memcpy(chunk + i + 1020, "</p>", 4);
  }
  OK(exr_chapter_index_begin(NULL, BUDGET, &index, &error));
  OK(exr_chapter_index_feed(index, "<html><body>", 12, 0, &error));
  for (i = 0; i < blocks/32; i++) {
    size_t memory;
    OK(exr_chapter_index_feed(index, chunk, sizeof(chunk), 0, &error));
    memory = exr_chapter_index_memory(index);
    CHECK(memory <= BUDGET);
    if (memory > peak) peak = memory;
  }
  OK(exr_chapter_index_feed(index, "</body></html>", 14, 1, &error));
  CHECK(exr_chapter_index_count(index) == 4 + 2*blocks);
  CHECK(exr_chapter_index_text_size(index) == 1018*blocks - 1);
  CHECK(exr_chapter_index_memory(index) <= BUDGET);
  printf("%zu MiB streamed: %zu nodes, sampled-accounted=%zu bytes, retained=%zu bytes, generator=%zu bytes\n",
    mib, exr_chapter_index_count(index), peak, exr_chapter_index_memory(index), sizeof(chunk));
  exr_chapter_index_free(index);
}

int main(void) {
  CHECK(sizeof(exr_chapter_entry) == 32);
  snapshots(); failures(); large_index(50); large_index(100);
  printf("%zu chapter index checks passed\n", checks);
  return 0;
}
