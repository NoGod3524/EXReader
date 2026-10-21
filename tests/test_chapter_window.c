/* SPDX-License-Identifier: MIT */
#include "chapter_internal.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static exr_error error;
static size_t checks;
#define BUDGET ((size_t)32*1024*1024)
#define CHECK(x) do { checks++; if (!(x)) { fprintf(stderr,"chapter window line %d: %s (%d)\n",__LINE__,#x,error.code); exit(1); } } while (0)
#define OK(x) CHECK((x) == EXR_OK)
typedef struct { const char *xml; size_t size, chunk, delivered; int final, fail_after; } source;

static exr_status pump(void *context,exr_chapter_sink_fn sink,void *sink_context,
                        const exr_control *control,exr_error *e) {
  source *s = context;
  size_t at = 0;
  (void)control;
  s->delivered = 0;
  while (at < s->size) {
    size_t part = s->size - at < s->chunk ? s->size - at : s->chunk;
    exr_status status = sink(sink_context,s->xml + at,part,0,e);
    if (status != EXR_OK) return status;
    at += part; s->delivered += part;
  }
  if (s->final) {
    exr_status status = sink(sink_context,NULL,0,1,e);
    if (status != EXR_OK) return status;
  }
  return s->fail_after ? EXR_IO : EXR_OK;
}
static exr_document *snapshot(const char *xml) {
  exr_document *d = NULL;
  OK(exr_xml_memory_tree(xml,strlen(xml),"html",&d,&error));
  d->format = EXR_EPUB;
  OK(exr_model_finish(d,&error));
  return d;
}
static exr_chapter_index *make_index(const char *xml) {
  exr_chapter_index *index = NULL;
  OK(exr_chapter_index_begin(NULL,BUDGET,&index,&error));
  OK(exr_chapter_index_feed(index,xml,strlen(xml),1,&error));
  return index;
}
static size_t find(const exr_document *d,const char *id) {
  size_t i;
  for (i = 0; i < d->node_count; i++) {
    const char *value = exr_node_attribute(&d->nodes[i],"id");
    if (value && !strcmp(value,id)) return i;
  }
  CHECK(0); return 0;
}
static size_t subtree_end(const exr_document *d,size_t node) {
  size_t next;
  for (next = node + 1; next < d->node_count; next++) {
    size_t at = d->nodes[next].parent;
    while (at != SIZE_MAX && at != node) at = d->nodes[at].parent;
    if (at == SIZE_MAX) break;
  }
  return next;
}
static size_t local_id(const exr_chapter_window *w,size_t global) {
  size_t i;
  for (i = 0; i < w->node_count; i++) if (w->global_nodes[i] == global) return i;
  return SIZE_MAX;
}
static void selection(void) {
  static const char xml[] =
    "<html xmlns='http://www.w3.org/1999/xhtml' xmlns:e='http://www.idpf.org/2007/ops'>"
    "<head><style>p{color:red}</style><link rel='stylesheet' href='book.css'/></head>"
    "<body xml:lang='zh' class='outer'><p id='before'>not retained</p>"
    "<section class='inner'><p id='selected'>\xe4\xb8\xad<!--join-->\xe6\x96\x87 <em> A &amp; B </em> tail</p>"
    "<p id='next' e:type='footnote'>second<br/>line</p></section>"
    "<p id='after'>not retained either</p><style>body .inner p{font-size:20px}</style></body></html>";
  static const size_t chunks[] = {1, 3, 17, 32768};
  exr_document *d = snapshot(xml);
  exr_chapter_index *index = make_index(xml);
  size_t first = find(d,"selected"), last = subtree_end(d,first), c, i;
  for (c = 0; c < sizeof(chunks)/sizeof(chunks[0]); c++) {
    exr_chapter_window w = {0};
    source s = {xml,sizeof(xml) - 1,chunks[c],0,1,0};
    size_t styles = 0, links = 0;
    OK(exr_chapter_window_load(index,d,first,last,1,pump,&s,BUDGET,NULL,&w,&error));
    CHECK(s.delivered == sizeof(xml) - 1);
    CHECK(w.document && w.node_count == w.document->node_count && w.memory_bytes <= BUDGET);
    CHECK(w.document->resources == d->resources && w.document->resource_count == d->resource_count);
    CHECK(local_id(&w,find(d,"before")) == SIZE_MAX && local_id(&w,find(d,"after")) == SIZE_MAX);
    CHECK(w.text_base == d->nodes[first].start);
    CHECK(w.document->size == d->nodes[first].end - d->nodes[first].start);
    CHECK(!memcmp(w.document->text,d->text + w.text_base,w.document->size));
    for (i = 0; i < w.node_count; i++) {
      const exr_node *a = &w.document->nodes[i], *b = &d->nodes[w.global_nodes[i]];
      size_t j;
      if (i) CHECK(w.global_nodes[i] > w.global_nodes[i - 1]);
      if (w.global_nodes[i] > 1) CHECK(a->parent != SIZE_MAX && w.global_nodes[a->parent] == b->parent);
      CHECK(a->kind == b->kind);
      CHECK((!a->name && !b->name) || (a->name && b->name && !strcmp(a->name,b->name)));
      CHECK(a->attribute_count == b->attribute_count);
      for (j = 0; j < a->attribute_count; j++)
        CHECK(!strcmp(a->attributes[j].name,b->attributes[j].name) && !strcmp(a->attributes[j].value,b->attributes[j].value));
      if (w.global_nodes[i] >= first && w.global_nodes[i] < last && a->kind == EXR_NODE_TEXT) {
        CHECK(a->start + w.text_base == b->start && a->end + w.text_base == b->end);
        CHECK(!strcmp(a->text,b->text));
      }
      if (a->name && strstr(a->name,"|style")) { styles++; CHECK(a->first_child != SIZE_MAX); }
      if (a->name && strstr(a->name,"|link")) links++;
    }
    CHECK(styles == 2 && links == 1);
    exr_chapter_window_free(&w); exr_chapter_window_free(&w);
    CHECK(!w.document && !w.global_nodes && !w.node_count && !w.memory_bytes);
  }
  {
    exr_chapter_window w = {0};
    source s = {xml,sizeof(xml) - 1,7,0,1,0};
    size_t next = find(d,"next");
    OK(exr_chapter_window_load(index,d,first,subtree_end(d,next),1,pump,&s,BUDGET,NULL,&w,&error));
    CHECK(!memcmp(w.document->text,d->text + w.text_base,w.document->size));
    exr_chapter_window_free(&w);
    OK(exr_chapter_window_load(index,d,0,0,0,pump,&s,BUDGET,NULL,&w,&error));
    CHECK(!w.document->text && !w.document->size && local_id(&w,first) == SIZE_MAX);
    for (i = 2; i < w.node_count; i++) {
      const exr_node *a = &w.document->nodes[i], *b = &d->nodes[w.global_nodes[i]];
      CHECK(w.global_nodes[i] > w.global_nodes[i - 1]);
      CHECK(a->parent != SIZE_MAX && w.global_nodes[a->parent] == b->parent);
    }
    exr_chapter_window_free(&w);
  }
  exr_chapter_index_free(index); exr_document_free(d);
}
typedef struct { unsigned calls, after; } cancel_state;
static int cancel(void *context) { cancel_state *s = context; return ++s->calls > s->after; }
static void failure(void) {
  const char *xml = "<html><body><p id='p'>text &amp; more</p></body></html>";
  exr_document *d = snapshot(xml);
  exr_chapter_index *index = make_index(xml);
  size_t first = find(d,"p"), last = subtree_end(d,first), i;
  exr_chapter_window w = {0};
  source s = {xml,strlen(xml),7,0,1,0};
  cancel_state state = {0,0};
  exr_control control = {0};
  CHECK(exr_chapter_window_load(index,d,first,last,1,pump,&s,1,NULL,&w,&error) == EXR_LIMIT);
  CHECK(!w.document && !w.global_nodes);
  control.context = &state; control.cancelled = cancel;
  CHECK(exr_chapter_window_load(index,d,first,last,1,pump,&s,BUDGET,&control,&w,&error) == EXR_CANCELLED);
  CHECK(!w.document && !w.global_nodes);
  s.fail_after = 1;
  CHECK(exr_chapter_window_load(index,d,first,last,1,pump,&s,BUDGET,NULL,&w,&error) == EXR_IO);
  CHECK(!w.document && !w.global_nodes); s.fail_after = 0; s.final = 0;
  CHECK(exr_chapter_window_load(index,d,first,last,1,pump,&s,BUDGET,NULL,&w,&error) == EXR_FORMAT);
  CHECK(!w.document && !w.global_nodes); s.final = 1;
  {
    static const char *bad[] = {"<html><body><p>text</body></html>",
      "<!DOCTYPE html [<!ENTITY local 'text'>]><html><body><p>&local;</p></body></html>"};
    for (i = 0; i < sizeof(bad)/sizeof(bad[0]); i++) {
      s.xml = bad[i]; s.size = strlen(bad[i]);
      CHECK(exr_chapter_window_load(index,d,first,last,1,pump,&s,BUDGET,NULL,&w,&error) == EXR_FORMAT);
      CHECK(!w.document && !w.global_nodes);
    }
  }
  CHECK(d->resources && d->text && !strcmp(d->text,"text & more"));
  exr_chapter_window_free(&w); exr_chapter_index_free(index); exr_document_free(d);
}
static void pending_failure_budget(void) {
  char name[1025], xml[2200];
  size_t budget, limited = 0, passed = 0;
  exr_document *d;
  exr_chapter_index *index;
  source s;
  memset(name,'a',sizeof(name) - 1); name[sizeof(name) - 1] = 0;
  (void)snprintf(xml,sizeof(xml),"<html><body><%s id='pending' lang='en'/></body></html>",name);
  d = snapshot(xml); index = make_index(xml);
  s = (source){xml,strlen(xml),32768,0,1,0};
  /* Exercise adjacent allocation boundaries, including an unselected pending
     name that cannot fit although its smaller attribute array could fit.
     LeakSanitizer verifies ownership on each rejected parse. */
  for (budget = 32768; budget <= 65536; budget += 16) {
    exr_chapter_window w = {0};
    exr_status status = exr_chapter_window_load(index,d,0,0,0,pump,&s,budget,NULL,&w,&error);
    CHECK(status == EXR_OK || status == EXR_LIMIT);
    if (status == EXR_LIMIT) {
      limited++; CHECK(!w.document && !w.global_nodes && !w.memory_bytes);
    } else { passed++; CHECK(w.document && w.memory_bytes <= budget); }
    exr_chapter_window_free(&w);
  }
  CHECK(limited && passed);
  exr_chapter_index_free(index); exr_document_free(d);
}
static void large_text(void) {
  size_t size = 1024*1024, first, last;
  char *xml = malloc(size + 128);
  exr_document metadata = {0};
  exr_chapter_index *index;
  exr_chapter_window w = {0};
  source s;
  size_t prefix = strlen("<html><body><p>");
  CHECK(xml != NULL);
  memcpy(xml,"<html><body><p>",prefix); memset(xml + prefix,'x',size);
  strcpy(xml + prefix + size,"</p><p>next</p></body></html>");
  index = make_index(xml); first = 4; last = 6; metadata.format = EXR_EPUB;
  s = (source){xml,strlen(xml),32768,0,1,0};
  CHECK(exr_chapter_window_load(index,&metadata,first,last,1,pump,&s,512*1024,NULL,&w,&error) == EXR_LIMIT);
  CHECK(!w.document && !w.global_nodes);
  OK(exr_chapter_window_load(index,&metadata,first,last,0,pump,&s,512*1024,NULL,&w,&error));
  CHECK(w.document->node_count == 6 && !w.document->nodes[5].text && w.memory_bytes < 512*1024);
  exr_chapter_window_free(&w);
  OK(exr_chapter_window_load(index,&metadata,6,8,1,pump,&s,512*1024,NULL,&w,&error));
  CHECK(w.document->size == 4 && !strcmp(w.document->text,"next") && w.text_base == size + 1);
  CHECK(w.memory_bytes < 512*1024 && s.delivered == strlen(xml));
  exr_chapter_window_free(&w); exr_chapter_index_free(index); free(xml);
}
static void leading_empty_ranges(void) {
  const char *xml = "<html><body><p>before</p><p id='selected'>  <em>visible</em> tail</p></body></html>";
  exr_document *d = snapshot(xml);
  exr_chapter_index *index = make_index(xml);
  exr_chapter_window w = {0};
  size_t first = find(d,"selected"), last = subtree_end(d,first), i;
  source s = {xml,strlen(xml),3,0,1,0};
  OK(exr_chapter_window_load(index,d,first,last,1,pump,&s,BUDGET,NULL,&w,&error));
  CHECK(!memcmp(w.document->text,d->text + w.text_base,w.document->size));
  for (i = 0; i < w.node_count; i++) if (w.global_nodes[i] >= first && w.global_nodes[i] < last &&
      w.document->nodes[i].kind == EXR_NODE_TEXT) {
    const exr_node *a = &w.document->nodes[i], *b = &d->nodes[w.global_nodes[i]];
    CHECK(a->start + w.text_base == b->start && a->end + w.text_base == b->end);
  }
  exr_chapter_window_free(&w); exr_chapter_index_free(index); exr_document_free(d);
}
static void boundaries(void) {
  char xml[8192], replay[8192];
  size_t i, at = 0;
  exr_chapter_index *index;
  exr_document metadata = {0};
  exr_chapter_window w = {0};
  source s;
  metadata.format = EXR_EPUB;
  memcpy(xml,"<html>",6); at = 6;
  for (i = 0; i < 255; i++) { memcpy(xml + at,"<g>",3); at += 3; }
  for (i = 0; i < 255; i++) { memcpy(xml + at,"</g>",4); at += 4; }
  strcpy(xml + at,"</html>");
  index = make_index(xml); s = (source){xml,strlen(xml),17,0,1,0};
  OK(exr_chapter_window_load(index,&metadata,0,0,0,pump,&s,BUDGET,NULL,&w,&error));
  exr_chapter_window_free(&w);
  at = 6 + 255*3; memcpy(replay,xml,at); memcpy(replay + at,"<g></g>",7); strcpy(replay + at + 7,xml + at);
  s.xml = replay; s.size = strlen(replay);
  CHECK(exr_chapter_window_load(index,&metadata,0,0,0,pump,&s,BUDGET,NULL,&w,&error) == EXR_LIMIT);
  CHECK(!w.document && !w.global_nodes); exr_chapter_index_free(index);
  index = make_index("<html/>");
  at = (size_t)snprintf(xml,sizeof(xml),"<html");
  for (i = 0; i < 256; i++) at += (size_t)snprintf(xml + at,sizeof(xml) - at," a%zu='x'",i);
  strcpy(xml + at,"/>"); s = (source){xml,strlen(xml),13,0,1,0};
  OK(exr_chapter_window_load(index,&metadata,0,0,0,pump,&s,BUDGET,NULL,&w,&error));
  exr_chapter_window_free(&w);
  (void)snprintf(xml + at,sizeof(xml) - at," a256='x'/>"); s.size = strlen(xml);
  CHECK(exr_chapter_window_load(index,&metadata,0,0,0,pump,&s,BUDGET,NULL,&w,&error) == EXR_LIMIT);
  CHECK(!w.document && !w.global_nodes); exr_chapter_index_free(index);
}
typedef struct { size_t size, delivered; } generated_source;
static exr_status generated_pump(void *context,exr_chapter_sink_fn sink,void *sink_context,
                                  const exr_control *control,exr_error *e) {
  static const char prefix[] = "<html><body><p>", suffix[] = "</p><p>tail</p></body></html>";
  generated_source *s = context;
  char chunk[32768];
  size_t left = s->size;
  exr_status status;
  (void)control;
  s->delivered = 0; memset(chunk,'x',sizeof(chunk));
  status = sink(sink_context,prefix,sizeof(prefix) - 1,0,e);
  if (status != EXR_OK) return status;
  s->delivered += sizeof(prefix) - 1;
  while (left) {
    size_t size = left < sizeof(chunk) ? left : sizeof(chunk);
    status = sink(sink_context,chunk,size,0,e);
    if (status != EXR_OK) return status;
    left -= size; s->delivered += size;
  }
  status = sink(sink_context,suffix,sizeof(suffix) - 1,1,e);
  if (status == EXR_OK) s->delivered += sizeof(suffix) - 1;
  return status;
}
static exr_status index_sink(void *context,const void *data,size_t size,int final,exr_error *e) {
  return exr_chapter_index_feed(context,data,size,final,e);
}
static void streamed_window(size_t mib) {
  generated_source s = {mib*1024*1024,0};
  exr_chapter_index *index = NULL;
  exr_document metadata = {0};
  exr_chapter_window w = {0};
  size_t total;
  metadata.format = EXR_EPUB;
  OK(exr_chapter_index_begin(NULL,BUDGET,&index,&error));
  OK(generated_pump(&s,index_sink,index,NULL,&error)); total = s.delivered;
  CHECK(exr_chapter_index_count(index) == 8);
  OK(exr_chapter_window_load(index,&metadata,4,6,0,generated_pump,&s,256*1024,NULL,&w,&error));
  CHECK(s.delivered == total && !w.document->nodes[5].text && w.memory_bytes < 256*1024);
  exr_chapter_window_free(&w);
  OK(exr_chapter_window_load(index,&metadata,6,8,1,generated_pump,&s,256*1024,NULL,&w,&error));
  CHECK(s.delivered == total && w.text_base == s.size + 1 && !strcmp(w.document->text,"tail"));
  CHECK(w.memory_bytes < 256*1024);
  printf("%zu MiB replayed: tail-window=%zu bytes, fixed-generator=32768 bytes\n",mib,w.memory_bytes);
  exr_chapter_window_free(&w); exr_chapter_index_free(index);
}
typedef struct { source input; size_t calls; int fail_second; cancel_state *cancel_second; } visit_source;
static exr_status counted_pump(void *context,exr_chapter_sink_fn sink,void *target,
                                const exr_control *control,exr_error *e) {
  visit_source *s = context;
  s->calls++;
  s->input.fail_after = s->fail_second && s->calls == 2;
  if (s->cancel_second && s->calls == 2) s->cancel_second->after = s->cancel_second->calls + 3;
  return pump(&s->input,sink,target,control,e);
}
typedef struct { const exr_document *snapshot; unsigned char *seen; size_t calls, fail_at, budget; } visitor_audit;
static int declaration_node(const exr_document *d,size_t node) {
  for (; node != SIZE_MAX; node = d->nodes[node].parent) {
    const char *name = d->nodes[node].name;
    const char *tag = name ? strrchr(name,'|') : NULL;
    if (tag) tag++; else tag = name;
    if (tag && (!strcmp(tag,"style") || !strcmp(tag,"link"))) return 1;
  }
  return 0;
}
static exr_status audit_batch(const exr_chapter_window *w,void *context,exr_error *e) {
  visitor_audit *audit = context;
  size_t i, styles = 0, links = 0, previous_declaration = 0;
  (void)e;
  audit->calls++;
  CHECK(w->document && w->node_count == w->document->node_count && w->memory_bytes <= audit->budget);
  for (i = 0; i < w->node_count; i++) {
    uint32_t global = w->global_nodes[i];
    const exr_node *a = &w->document->nodes[i], *b;
    size_t j;
    CHECK(global < audit->snapshot->node_count); audit->seen[global] = 1;
    b = &audit->snapshot->nodes[global];
    CHECK(a->kind == b->kind && a->attribute_count == b->attribute_count);
    CHECK((!a->name && !b->name) || (a->name && b->name && !strcmp(a->name,b->name)));
    for (j = 0; j < a->attribute_count; j++) CHECK(!strcmp(a->attributes[j].name,b->attributes[j].name) &&
      !strcmp(a->attributes[j].value,b->attributes[j].value));
    for (j = 0; j < i; j++) CHECK(w->global_nodes[j] != global);
    if (global > 1)
      CHECK(a->parent != SIZE_MAX && w->global_nodes[a->parent] == b->parent);
    if (a->kind == EXR_NODE_TEXT) {
      if (declaration_node(audit->snapshot,global)) CHECK(a->text && !strcmp(a->text,b->text));
      else CHECK(a->text == NULL);
    }
    if (a->name && (strstr(a->name,"|style") || strstr(a->name,"|link"))) {
      CHECK(global > previous_declaration); previous_declaration = global;
      styles += strstr(a->name,"|style") != NULL; links += strstr(a->name,"|link") != NULL;
    }
  }
  CHECK(styles == 2 && links == 1);
  return audit->calls == audit->fail_at ? EXR_IO : EXR_OK;
}
static void visit_batches(void) {
  char xml[16384];
  size_t used = 0, i, j;
  exr_document *d;
  exr_chapter_index *index;
  static const size_t batches[] = {1, 32};
  used += (size_t)sprintf(xml + used,"<html xmlns='http://www.w3.org/1999/xhtml'><head><style>p{color:red}</style><link rel='stylesheet' href='book.css'/></head><body xml:lang='en'><section class='outer'>");
  for (i = 0; i < 60; i++) used += (size_t)sprintf(xml + used,"<p id='p%zu'>word <em>text</em> tail</p>",i);
  used += (size_t)sprintf(xml + used,"</section><aside class='late'><section lang='fr'><style>body .outer p{font-size:20px}</style></section></aside></body></html>");
  d = snapshot(xml); index = make_index(xml);
  for (j = 0; j < sizeof(batches)/sizeof(batches[0]); j++) {
    unsigned char *seen = calloc(d->node_count,1);
    visitor_audit audit = {d,seen,0,0,256*1024};
    visit_source s = {{xml,used,7,0,1,0},0,0,NULL};
    CHECK(seen != NULL);
    OK(exr_chapter_windows_visit(index,d,batches[j],counted_pump,&s,audit.budget,NULL,audit_batch,&audit,&error));
    CHECK(s.calls == 2 && s.input.delivered == used && audit.calls > 1);
    for (i = 0; i < d->node_count; i++) CHECK(seen[i] == 1);
    free(seen);
  }
  {
    unsigned char *seen = calloc(d->node_count,1);
    visitor_audit audit = {d,seen,0,2,BUDGET};
    visit_source s = {{xml,used,7,0,1,0},0,0,NULL};
    cancel_state state = {0,UINT_MAX};
    exr_control control = {0};
    CHECK(seen != NULL);
    CHECK(exr_chapter_windows_visit(index,d,1,counted_pump,&s,audit.budget,NULL,audit_batch,&audit,&error) == EXR_IO);
    CHECK(s.calls == 2 && audit.calls == 2);
    audit.calls = audit.fail_at = 0; s.calls = 0; s.fail_second = 1;
    CHECK(exr_chapter_windows_visit(index,d,32,counted_pump,&s,audit.budget,NULL,audit_batch,&audit,&error) == EXR_IO);
    CHECK(s.calls == 2 && audit.calls > 0);
    audit.calls = 0; s.calls = 0; s.fail_second = 0; s.cancel_second = &state;
    control.context = &state; control.cancelled = cancel;
    CHECK(exr_chapter_windows_visit(index,d,1,counted_pump,&s,audit.budget,&control,audit_batch,&audit,&error) == EXR_CANCELLED);
    CHECK(s.calls == 2);
    audit.calls = 0; s.calls = 0; s.cancel_second = NULL;
    CHECK(exr_chapter_windows_visit(index,d,32,counted_pump,&s,16384,NULL,audit_batch,&audit,&error) == EXR_LIMIT);
    CHECK(audit.calls == 0);
    free(seen);
  }
  exr_chapter_index_free(index); exr_document_free(d);
}
int main(void) {
  selection(); failure(); pending_failure_budget(); large_text(); leading_empty_ranges(); boundaries(); streamed_window(50); streamed_window(100); visit_batches();
  printf("%zu chapter window checks passed\n",checks);
  return 0;
}
