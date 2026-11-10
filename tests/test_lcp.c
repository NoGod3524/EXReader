/* SPDX-License-Identifier: MIT */
#include "exreader.h"
#include "formats_internal.h"
#include <miniz.h>
#include <stdio.h>

static exr_error error;
static unsigned checks;
static const char pass[] = "LCP caf\xc3\xa9 \xe5\x8f\xa3\xe4\xbb\xa4";
#define CHECK(x) do { checks++; if (!(x)) { fprintf(stderr, "LCP line %d: %s (%d: %s)\n", __LINE__, #x, error.code, error.message); exit(1); } } while (0)
#define OK(x) CHECK((x) == EXR_OK)
static void path(char out[4096], const char *dir, const char *name) {
  CHECK(snprintf(out, 4096, "%s/%s.epub", dir, name) > 0);
}
static void expect(const char *dir, const char *name, const char *password, exr_status expected) {
  char file[4096]; exr_publication *p = (void *)1;
  path(file, dir, name);
  CHECK(exr_publication_open_ex(file, password, &p, &error) == expected);
  CHECK(!p && error.code == expected && error.message[0]);
  /* A diagnostic object is optional, including on failed key/JSON paths. */
  p = (void *)1;
  CHECK(exr_publication_open_ex(file, password, &p, NULL) == expected && !p);
}
typedef struct { unsigned char *bytes; size_t size, released; int fail; } memory;
static size_t read_at(void *ctx, uint64_t offset, void *out, size_t n) {
  memory *m = ctx;
  if (m->fail) return 0;
  CHECK(offset <= m->size && n <= m->size - (size_t)offset);
  if (n > 17) n = 17;
  memcpy(out, m->bytes + (size_t)offset, n); return n;
}
static void source_release(void *ctx) { ((memory *)ctx)->released++; }

static size_t compare(const char *encrypted, const char *clear, const char *password, const char *font_path) {
  exr_publication *p = NULL, *q = NULL;
  exr_font *font = NULL;
  const exr_part *parts;
  size_t count, other_count, i, pages = 0, resources = 0, bytes_compared = 0;
  exr_layout_config config = exr_layout_config_defaults();
  OK(exr_publication_open_ex(encrypted, password, &p, &error));
  OK(exr_publication_open(clear, &q, &error));
  OK(exr_font_open(font_path, &font, &error));
  parts = exr_publication_parts(p, &count); exr_publication_parts(q, &other_count);
  CHECK(parts && count > 0 && count == other_count);
  for (i = 0; i < count; i++) {
    exr_document *d = NULL, *original = NULL;
    exr_layout *layout = NULL;
    const char *a, *b;
    const exr_resource *res, *orig_res;
    size_t na, nb, j, nr;
    OK(exr_publication_load(p, i, &d, &error));
    OK(exr_publication_load(q, i, &original, &error));
    a = exr_document_text(d, &na); b = exr_document_text(original, &nb);
    CHECK(na == nb && !memcmp(a, b, na));
    if (!i) {
      res = exr_document_resources(d, &nr); orig_res = exr_document_resources(original, &nb);
      CHECK(nr == nb);
      for (j = 0; j < nr; j++) {
        void *x = NULL, *y = NULL;
        CHECK(!strcmp(res[j].path, orig_res[j].path));
        OK(exr_document_resource(d, j, &x, &na, &error));
        OK(exr_document_resource(original, j, &y, &nb, &error));
        CHECK(na == nb && !memcmp(x, y, na)); resources++; bytes_compared += na;
        exr_free(x); exr_free(y);
      }
    }
    if (parts[i].in_reading_order) {
      OK(exr_layout_create_ex(d, font, &config, &layout, &error));
      exr_layout_pages(layout, &na); CHECK(na > 0); pages += na;
      exr_layout_free(layout);
    }
    exr_document_free(d); exr_document_free(original);
  }
  { const exr_navigation *navigation; size_t n;
    OK(exr_publication_navigation(p, &navigation, &n, &error)); CHECK(n > 0);
  }
  exr_font_free(font); exr_publication_free(p); exr_publication_free(q);
  CHECK(pages > 0 && resources > 0);
  printf("{\"pages\":%zu,\"resources_equal\":%zu,\"resource_bytes_equal\":%zu}\n", pages, resources, bytes_compared);
  return pages;
}
typedef struct { size_t used, calls, fail_at; } ledger;
typedef struct { exr_allocation_alignment align; size_t size; } allocation;
static void *allocate(void *ctx, size_t n) {
  ledger *l = ctx; allocation *a;
  if (++l->calls == l->fail_at || n > 2 * 1024 * 1024) return NULL;
  a = malloc(sizeof(*a) + n); if (!a) return NULL;
  a->size = n; l->used += n; return a + 1;
}
static void release(void *ctx, void *data) {
  ledger *l = ctx; allocation *a;
  if (!data) return;
  a = (allocation *)data - 1; CHECK(l->used >= a->size); l->used -= a->size; free(a);
}
static void *resize(void *ctx, void *data, size_t n) {
  allocation *a; void *out;
  if (!data) return allocate(ctx, n);
  if (!n) { release(ctx, data); return NULL; }
  a = (allocation *)data - 1; out = allocate(ctx, n);
  if (out) { memcpy(out, data, a->size < n ? a->size : n); release(ctx, data); }
  return out;
}
typedef struct { const void *bytes; size_t size, at, final; } sink;
static exr_status feed(void *ctx, const void *data, size_t n, int final, exr_error *e) {
  sink *s = ctx; (void)e;
  CHECK(n <= s->size - s->at && n <= 32768);
  if (n) CHECK(!memcmp(data, (const char *)s->bytes + s->at, n));
  s->at += n; s->final += (unsigned)final; return EXR_OK;
}
static int cancel(void *ctx) { (void)ctx; return 1; }
static void lifetime(const char *dir) {
  char file[4096]; memory m = {0}; exr_source source = {0};
  exr_publication *p = NULL; exr_document *d = NULL, *index = NULL;
  void *bytes = NULL; size_t n, total, i;
  ledger l = {0}; exr_resource_allocator allocator = {&l, allocate, resize, release};
  sink s = {0}; exr_control control = {0};
  path(file, dir, "normal"); OK(exr_read(file, &m.bytes, &m.size, &error));
  source.size=m.size;source.read_at=read_at;source.context=&m;source.release=source_release;
  CHECK(exr_publication_open_source_ex(&source,"wrong",&p,&error)==EXR_DRM_PASSPHRASE_INCORRECT);
  CHECK(!p && !m.released);
  OK(exr_publication_open_source_ex(&source,pass,&p,&error));
  OK(exr_publication_load(p,0,&d,&error));exr_publication_free(p);
  CHECK(!m.released);OK(exr_document_resource(d,0,&bytes,&n,&error));exr_free(bytes);
  exr_document_free(d);CHECK(m.released==1);
  OK(exr_publication_open_memory_ex(EXR_EPUB,m.bytes,m.size,pass,&p,&error));
  memset(m.bytes,0,m.size);free(m.bytes);m.bytes=NULL;
  OK(exr_publication_load(p,0,&d,&error));exr_publication_free(p);
  OK(exr_document_resource(d,0,&bytes,&n,&error));exr_free(bytes);exr_document_free(d);
  OK(exr_read(file,&m.bytes,&m.size,&error));
  OK(exr_epub_index_ex(m.bytes,m.size,pass,&index,&error));free(m.bytes);
  OK(exr_document_resource(index,0,&bytes,&n,&error));
  s=(sink){bytes,n,0,0};OK(exr_epub_chapter_feed_bounded(index,0,feed,&s,&allocator,NULL,&error));
  CHECK(s.at==n && s.final==1 && !l.used);total=l.calls;
  for(i=1;i<=total;i++) {
    l=(ledger){0,0,i};s=(sink){bytes,n,0,0};
    CHECK(exr_epub_chapter_feed_bounded(index,0,feed,&s,&allocator,NULL,&error)!=EXR_OK);
    CHECK(!l.used && !s.final);
  }
  control.cancelled=cancel;l=(ledger){0};s=(sink){bytes,n,0,0};
  CHECK(exr_epub_chapter_feed_bounded(index,0,feed,&s,&allocator,&control,&error)==EXR_CANCELLED);
  CHECK(!l.used && !s.final);
  { void *bounded=NULL;size_t size=0;
    l=(ledger){0};OK(exr_document_resource_bounded(index,0,&allocator,NULL,&bounded,&size,&error));
    CHECK(size==n && !memcmp(bytes,bounded,n));release(&l,bounded);CHECK(!l.used);total=l.calls;
    for(i=1;i<=total;i++) {
      l=(ledger){0,0,i};bounded=(void *)1;size=1;
      CHECK(exr_document_resource_bounded(index,0,&allocator,NULL,&bounded,&size,&error)!=EXR_OK);
      CHECK(!bounded && !size && !l.used);
    }
  }
  exr_free(bytes);exr_document_free(index);
}
int main(int argc, char **argv) {
  char normal[4096], clear[4096], alias[4096]; size_t i;
  CHECK(argc >= 4);
  if (!strcmp(argv[1],"sample")) { CHECK(argc==6);compare(argv[2],argv[3],argv[4],argv[5]);return 0; }
  if (!strcmp(argv[1],"normal")) {
    path(normal,argv[2],"normal");path(clear,argv[2],"clear");path(alias,argv[2],"alias");
    compare(normal,clear,pass,argv[3]);compare(alias,clear,pass,argv[3]);
  } else if (!strcmp(argv[1],"credentials")) {
    exr_publication *p=NULL; unsigned char *data=NULL; size_t n=0;
    expect(argv[2],"normal",NULL,EXR_DRM_PASSPHRASE_REQUIRED);
    expect(argv[2],"normal","wrong",EXR_DRM_PASSPHRASE_INCORRECT);
    expect(argv[2],"normal","",EXR_DRM_PASSPHRASE_INCORRECT);
    path(normal,argv[2],"normal");
    CHECK(exr_publication_open(normal,&p,&error)==EXR_DRM_PASSPHRASE_REQUIRED && !p);
    OK(exr_read(normal,&data,&n,&error));
    CHECK(exr_publication_open_memory(EXR_EPUB,data,n,&p,&error)==EXR_DRM_PASSPHRASE_REQUIRED && !p);
    CHECK(exr_publication_open_memory_ex(EXR_EPUB,data,n,"wrong",&p,&error)==EXR_DRM_PASSPHRASE_INCORRECT && !p);
    exr_free(data);path(clear,argv[2],"clear");
    OK(exr_publication_open_ex(clear,"ignored for clear EPUB",&p,&error));exr_publication_free(p);
  } else if (!strcmp(argv[1],"expired")) {
    expect(argv[2],"expired",pass,EXR_DRM_LICENSE_EXPIRED);CHECK(strstr(error.message,"2001-02-03T04:05:06Z"));
    expect(argv[2],"expired-offset",pass,EXR_DRM_LICENSE_EXPIRED);CHECK(strstr(error.message,"+05:30"));
    expect(argv[2],"future",pass,EXR_DRM_LICENSE_INVALID);CHECK(strstr(error.message,"not valid before"));
  } else if (!strcmp(argv[1],"unsupported")) {
    const char *names[]={"profile","kdf","cipher","resource-algorithm","compression","adept-marker"};
    for(i=0;i<sizeof(names)/sizeof(*names);i++) expect(argv[2],names[i],pass,EXR_DRM_UNSUPPORTED);
  } else if (!strcmp(argv[1],"malformed")) {
    const char *names[]={"bad-date","bad-base64","duplicate","json-depth","json-trailing","unsafe-path","missing-license","bad-xml"};
    for(i=0;i<sizeof(names)/sizeof(*names);i++) expect(argv[2],names[i],pass,EXR_DRM_LICENSE_INVALID);
    expect(argv[2],"oversize",pass,EXR_LIMIT);
    { exr_publication *p=NULL;exr_document *d=NULL;void *bytes=(void *)1;size_t n=1;
      path(normal,argv[2],"truncated");OK(exr_publication_open_ex(normal,pass,&p,&error));
      CHECK(exr_publication_load(p,0,&d,&error)==EXR_DRM_LICENSE_INVALID && !d);exr_publication_free(p);
      path(normal,argv[2],"length");OK(exr_publication_open_ex(normal,pass,&p,&error));
      OK(exr_publication_load(p,0,&d,&error));
      CHECK(exr_document_resource(d,3,&bytes,&n,&error)==EXR_DRM_LICENSE_INVALID && !bytes && !n);
      exr_document_free(d);exr_publication_free(p);
    }
  } else if (!strcmp(argv[1],"lifetime")) lifetime(argv[2]);
  else CHECK(0);
  printf("%u LCP %s checks passed\n",checks,argv[1]);return 0;
}
