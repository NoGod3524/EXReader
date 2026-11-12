/* SPDX-License-Identifier: MIT */
/* Embedded media in EPUB: recognition, placeholders, SMIL overlays and graceful
   degradation. Everything is synthesised in memory; no playback is involved. */
#include "exreader.h"
#include <miniz.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static exr_error error;
#define CHECK(x) do { if (!(x)) { fprintf(stderr, "line %d: %s (%s)\n", __LINE__, #x, error.message); exit(1); } } while (0)
#define OK(x) CHECK((x) == EXR_OK)

typedef struct { const char *name; const void *data; size_t size; } member;

static const char container[] =
  "<?xml version=\"1.0\"?><container version=\"1.0\" xmlns=\"urn:oasis:names:tc:opendocument:xmlns:container\">"
  "<rootfiles><rootfile full-path=\"OPS/book.opf\" media-type=\"application/oebps-package+xml\"/></rootfiles></container>";

static unsigned char *zip_book(const member *m, size_t count, size_t *n) {
  mz_zip_archive z = {0};
  void *out = NULL;
  size_t i;
  CHECK(mz_zip_writer_init_heap(&z, 0, 0));
  CHECK(mz_zip_writer_add_mem(&z, "mimetype", "application/epub+zip", 20, 0));
  CHECK(mz_zip_writer_add_mem(&z, "META-INF/container.xml", container, sizeof(container) - 1, 0));
  for (i = 0; i < count; i++) CHECK(mz_zip_writer_add_mem(&z, m[i].name, m[i].data, m[i].size, 0));
  CHECK(mz_zip_writer_finalize_heap_archive(&z, &out, n));
  CHECK(mz_zip_writer_end(&z));
  return out;
}
static void put_le(unsigned char *p, unsigned long long v, int n) { while (n--) { *p++ = (unsigned char)v; v >>= 8; } }
static void put_be(unsigned char *p, unsigned long long v, int n) { while (n--) { p[n] = (unsigned char)v; v >>= 8; } }
/* One second of 8 kHz mono 8-bit PCM. */
static unsigned char wav[44 + 8000];
static void make_wav(void) {
  memcpy(wav, "RIFF", 4); put_le(wav + 4, sizeof(wav) - 8, 4); memcpy(wav + 8, "WAVEfmt ", 8);
  put_le(wav + 16, 16, 4); put_le(wav + 20, 1, 2); put_le(wav + 22, 1, 2); put_le(wav + 24, 8000, 4);
  put_le(wav + 28, 8000, 4); put_le(wav + 32, 1, 2); put_le(wav + 34, 8, 2);
  memcpy(wav + 36, "data", 4); put_le(wav + 40, 8000, 4); memset(wav + 44, 128, 8000);
}
/* ftyp + moov{mvhd}: timescale 1000, duration 12500 ms. */
static unsigned char mp4[20 + 8 + 8 + 100];
static void make_mp4(void) {
  memset(mp4, 0, sizeof(mp4));
  put_be(mp4, 20, 4); memcpy(mp4 + 4, "ftypisom", 8);
  put_be(mp4 + 20, 8 + 8 + 100, 4); memcpy(mp4 + 24, "moov", 4);
  put_be(mp4 + 28, 8 + 100, 4); memcpy(mp4 + 32, "mvhd", 4);
  put_be(mp4 + 36 + 12, 1000, 4); put_be(mp4 + 36 + 16, 12500, 4);
}
/* 100 MPEG-1 Layer III frames, 128 kbps, 44.1 kHz (417 bytes each), no Xing header. */
static unsigned char mp3[417 * 100];
static void make_mp3(void) {
  size_t i;
  for (i = 0; i < 100; i++) { unsigned char *f = mp3 + i * 417; f[0] = 0xFF; f[1] = 0xFB; f[2] = 0x90; f[3] = 0x00; }
}
static const char xhtml_head[] =
  "<?xml version=\"1.0\"?><html xmlns=\"http://www.w3.org/1999/xhtml\" xmlns:epub=\"http://www.idpf.org/2007/ops\"><head><title>t</title></head><body>";
static const char xhtml_tail[] = "</body></html>";
static char *page(const char *body) {
  char *s = malloc(strlen(xhtml_head) + strlen(body) + strlen(xhtml_tail) + 1);
  CHECK(s);
  strcpy(s, xhtml_head); strcat(s, body); strcat(s, xhtml_tail);
  return s;
}
static exr_publication *open_book(unsigned char *zip, size_t n) {
  exr_publication *p = NULL;
  OK(exr_publication_open_memory(EXR_EPUB, zip, n, &p, &error));
  CHECK(p);
  return p;
}
static const char *part_text(exr_publication *p, size_t part, exr_document **doc) {
  const char *t;
  size_t n;
  OK(exr_publication_load(p, part, doc, &error));
  t = exr_document_text(*doc, &n);
  CHECK(t);
  return t;
}
static int contains(const char *s, const char *needle) { return strstr(s, needle) != NULL; }

/* ---- group: elements -------------------------------------------------- */
static void elements(void) {
  static const char opf[] =
    "<package xmlns=\"http://www.idpf.org/2007/opf\" version=\"3.0\"><manifest>"
    "<item id=\"c1\" href=\"c1.xhtml\" media-type=\"application/xhtml+xml\"/>"
    "<item id=\"a\" href=\"audio/a.wav\" media-type=\"audio/wav\"/>"
    "<item id=\"v\" href=\"video/v.mp4\" media-type=\"video/mp4\"/>"
    "<item id=\"w\" href=\"video/v.webm\" media-type=\"video/webm\"/>"
    "<item id=\"bg\" href=\"audio/bg.mp3\" media-type=\"audio/mpeg\"/>"
    "<item id=\"p\" href=\"img/p.png\" media-type=\"image/png\"/>"
    "</manifest><spine><itemref idref=\"c1\"/></spine></package>";
  char *c1 = page("<p>Intro</p><audio src=\"audio/a.wav\" controls=\"controls\">no audio</audio>"
    "<video controls=\"controls\" poster=\"img/p.png\"><source src=\"video/v.mp4\" type=\"video/mp4\"/>"
    "<source src=\"video/v.webm\" type=\"video/webm\"/></video>"
    "<audio src=\"audio/bg.mp3\" autoplay=\"autoplay\" loop=\"loop\"/>"
    "<audio src=\"audio/a.wav\" hidden=\"hidden\"/><p>Outro</p>");
  member m[] = {{"OPS/book.opf", opf, sizeof(opf) - 1}, {"OPS/c1.xhtml", c1, strlen(c1)},
    {"OPS/audio/a.wav", wav, sizeof(wav)}, {"OPS/video/v.mp4", mp4, sizeof(mp4)},
    {"OPS/video/v.webm", "x", 1}, {"OPS/audio/bg.mp3", mp3, sizeof(mp3)}, {"OPS/img/p.png", "x", 1}};
  size_t n, count = 0;
  unsigned char *zip = zip_book(m, sizeof(m) / sizeof(*m), &n);
  exr_publication *p = open_book(zip, n);
  exr_document *d;
  const char *t = part_text(p, 0, &d);
  const exr_media_item *item = exr_document_media(d, &count);
  CHECK(count == 4 && item);
  CHECK(item[0].kind == EXR_MEDIA_AUDIO && item[0].state == EXR_MEDIA_AVAILABLE);
  CHECK(!strcmp(item[0].path, "OPS/audio/a.wav") && item[0].duration_ms == 1000);
  CHECK(item[0].flags & EXR_MEDIA_CONTROLS);
  CHECK(item[1].kind == EXR_MEDIA_VIDEO && item[1].state == EXR_MEDIA_AVAILABLE && item[1].duration_ms == 12500);
  CHECK(item[1].source_count == 2 && !strcmp(item[1].path, "OPS/video/v.mp4") && !strcmp(item[1].poster, "OPS/img/p.png"));
  CHECK(item[2].kind == EXR_MEDIA_AUDIO && (item[2].flags & EXR_MEDIA_BACKGROUND) && (item[2].flags & EXR_MEDIA_DURATION_ESTIMATED));
  CHECK(item[2].duration_ms > 2500 && item[2].duration_ms < 2700);
  CHECK(item[3].flags & EXR_MEDIA_HIDDEN && item[3].placeholder == SIZE_MAX);
  CHECK(contains(t, "[Audio: a.wav, 0:01]") && contains(t, "[Video: v.mp4, 0:13]") && contains(t, "[Audio: bg.mp3, about 0:03]"));
  CHECK(contains(t, "Intro") && contains(t, "Outro"));
  CHECK(!contains(t, "no audio"));   /* the label replaces fallback text that would contradict it */
  /* Layout consumes text nodes in source order, including media placeholders. */
  {
    size_t nodes_count, i, previous = 0;
    const exr_node *nodes = exr_document_nodes(d, &nodes_count);
    for (i = 0; i < nodes_count; i++) {
      if (nodes[i].kind != EXR_NODE_TEXT || nodes[i].start == SIZE_MAX || nodes[i].end <= nodes[i].start) continue;
      CHECK(nodes[i].start >= previous);
      previous = nodes[i].end;
    }
  }
  printf("elements: %zu media elements, labels visible in part text\n", count);
  exr_document_free(d); exr_publication_free(p); mz_free(zip); free(c1);
}

/* ---- group: overlay --------------------------------------------------- */
static void overlay(void) {
  static const char opf[] =
    "<package xmlns=\"http://www.idpf.org/2007/opf\" version=\"3.0\"><metadata xmlns:dc=\"http://purl.org/dc/elements/1.1/\">"
    "<meta property=\"media:duration\" refines=\"#ov1\">0:00:09.5</meta>"
    "<meta property=\"media:active-class\">-epub-media-overlay-active</meta></metadata><manifest>"
    "<item id=\"c1\" href=\"c1.xhtml\" media-type=\"application/xhtml+xml\" media-overlay=\"ov1\"/>"
    "<item id=\"c2\" href=\"c2.xhtml\" media-type=\"application/xhtml+xml\"/>"
    "<item id=\"c3\" href=\"c3.xhtml\" media-type=\"application/xhtml+xml\" media-overlay=\"ghost\"/>"
    "<item id=\"c4\" href=\"c4.xhtml\" media-type=\"application/xhtml+xml\" media-overlay=\"ov2\"/>"
    "<item id=\"ov1\" href=\"c1.smil\" media-type=\"application/smil+xml\"/>"
    "<item id=\"ov2\" href=\"c4.smil\" media-type=\"application/smil+xml\"/>"
    "<item id=\"a\" href=\"audio/a.wav\" media-type=\"audio/wav\"/>"
    "</manifest><spine><itemref idref=\"c1\"/><itemref idref=\"c2\"/><itemref idref=\"c3\"/><itemref idref=\"c4\"/></spine></package>";
  static const char smil[] =
    "<smil xmlns=\"http://www.w3.org/ns/SMIL\" xmlns:epub=\"http://www.idpf.org/2007/ops\" version=\"3.0\"><body>"
    "<seq id=\"s\" epub:textref=\"c1.xhtml\" epub:type=\"bodymatter chapter\">"
    "<par id=\"p1\"><text src=\"c1.xhtml#s1\"/><audio src=\"audio/a.wav\" clipBegin=\"0:00:00.000\" clipEnd=\"0:00:01.500\"/></par>"
    "<par id=\"p2\"><text src=\"c1.xhtml#s2\"/><audio src=\"audio/a.wav\" clipBegin=\"1.5s\" clipEnd=\"3000ms\"/></par>"
    "<par id=\"p3\"><text src=\"c1.xhtml#s3\"/><audio src=\"audio/gone.wav\" clipBegin=\"0:01\" clipEnd=\"0:02\"/></par>"
    "<seq id=\"inner\"><par id=\"p4\"><text src=\"c1.xhtml#nope\"/><audio src=\"audio/a.wav\" clipBegin=\"0:03\"/></par></seq>"
    "</seq></body></smil>";
  char *c1 = page("<p id=\"s1\">One.</p><p id=\"s2\">Two.</p><p id=\"s3\">Three.</p>");
  char *c2 = page("<p>Plain.</p>"), *c3 = page("<p>Dangling.</p>"), *c4 = page("<p>Broken.</p>");
  member m[] = {{"OPS/book.opf", opf, sizeof(opf) - 1}, {"OPS/c1.xhtml", c1, strlen(c1)}, {"OPS/c2.xhtml", c2, strlen(c2)},
    {"OPS/c3.xhtml", c3, strlen(c3)}, {"OPS/c4.xhtml", c4, strlen(c4)}, {"OPS/c1.smil", smil, sizeof(smil) - 1},
    {"OPS/c4.smil", "<smil><body><par>", 17}, {"OPS/audio/a.wav", wav, sizeof(wav)}};
  size_t n;
  unsigned char *zip = zip_book(m, sizeof(m) / sizeof(*m), &n);
  exr_publication *p = open_book(zip, n);
  exr_media_overlay *o = NULL;
  exr_document *d;
  const char *t;
  size_t i;
  static const char *const words[] = {"One.", "Two.", "Three."};
  OK(exr_publication_media_overlay(p, 0, &o, &error));
  CHECK(o && !strcmp(o->smil_path, "OPS/c1.smil") && o->duration_ms == 9500);
  CHECK(!strcmp(o->active_class, "-epub-media-overlay-active") && !o->playback_active_class[0]);
  CHECK(o->clip_count == 4 && o->missing_audio == 1 && o->unresolved_text == 1);
  t = part_text(p, 0, &d);
  for (i = 0; i < 3; i++) {
    const exr_overlay_clip *c = &o->clips[i];
    CHECK(c->text_part == 0 && c->text_start != SIZE_MAX && !strncmp(t + c->text_start, words[i], strlen(words[i])));
    CHECK(c->text_end - c->text_start == strlen(words[i]));
    printf("overlay: par %s  text[%zu,%zu)=\"%s\"  <->  %s %lld-%lld ms%s\n", c->par_id, c->text_start, c->text_end,
           words[i], c->audio_path, c->clip_begin_ms, c->clip_end_ms, c->audio_present ? "" : "  (audio missing)");
  }
  CHECK(o->clips[0].clip_begin_ms == 0 && o->clips[0].clip_end_ms == 1500 && o->clips[0].audio_present);
  CHECK(o->clips[1].clip_begin_ms == 1500 && o->clips[1].clip_end_ms == 3000);
  CHECK(!o->clips[2].audio_present && o->clips[2].clip_begin_ms == 1000 && o->clips[2].clip_end_ms == 2000);
  CHECK(!strcmp(o->clips[3].par_id, "p4") && o->clips[3].text_start == SIZE_MAX && o->clips[3].clip_begin_ms == 3000 &&
        o->clips[3].clip_end_ms == -1 && o->clips[3].audio_present);
  exr_document_free(d);
  exr_media_overlay_free(o); o = NULL;
  OK(exr_publication_media_overlay(p, 1, &o, &error));
  CHECK(o == NULL);
  CHECK(exr_publication_media_overlay(p, 2, &o, &error) == EXR_FORMAT && o == NULL && error.message[0]);
  CHECK(exr_publication_media_overlay(p, 3, &o, &error) == EXR_FORMAT && o == NULL && contains(error.message, "SMIL"));
  t = part_text(p, 3, &d);   /* a broken overlay never stops the text from loading */
  CHECK(contains(t, "Broken."));
  CHECK(exr_publication_media_overlay(p, 99, &o, &error) == EXR_ARGUMENT);
  exr_document_free(d); exr_publication_free(p); mz_free(zip); free(c1); free(c2); free(c3); free(c4);
}

/* ---- group: degrade --------------------------------------------------- */
static void degrade(void) {
  static const char opf[] =
    "<package xmlns=\"http://www.idpf.org/2007/opf\" version=\"3.0\"><manifest>"
    "<item id=\"c1\" href=\"c1.xhtml\" media-type=\"application/xhtml+xml\"/>"
    "<item id=\"swf\" href=\"movie.swf\" media-type=\"application/x-shockwave-flash\"/>"
    "<item id=\"flv\" href=\"clip.flv\" media-type=\"video/x-flv\"/>"
    "<item id=\"wmv\" href=\"old.wmv\" media-type=\"video/x-ms-wmv\"/>"
    "<item id=\"svg\" href=\"art.svg\" media-type=\"image/svg+xml\"/>"
    "</manifest><spine><itemref idref=\"c1\"/></spine></package>";
  char *c1 = page("<p>Before</p><audio src=\"audio/gone.mp3\" controls=\"controls\"/>"
    "<object data=\"movie.swf\" type=\"application/x-shockwave-flash\"><param name=\"movie\" value=\"movie.swf\"/>Get Flash</object>"
    "<embed src=\"clip.flv\" type=\"video/x-flv\"/>"
    "<video src=\"http://example.com/v.mp4\" controls=\"controls\"/><audio controls=\"controls\"/>"
    "<video src=\"old.wmv\" controls=\"controls\"/>"
    "<object data=\"art.svg\" type=\"image/svg+xml\"><p>svg fallback</p></object><p>After</p>");
  member m[] = {{"OPS/book.opf", opf, sizeof(opf) - 1}, {"OPS/c1.xhtml", c1, strlen(c1)}, {"OPS/movie.swf", "FWS", 3},
    {"OPS/clip.flv", "FLV", 3}, {"OPS/old.wmv", "ASF", 3}, {"OPS/art.svg", "<svg/>", 6}};
  static const exr_media_state want[] = {EXR_MEDIA_MISSING, EXR_MEDIA_UNSUPPORTED, EXR_MEDIA_UNSUPPORTED,
    EXR_MEDIA_REMOTE, EXR_MEDIA_NO_SOURCE, EXR_MEDIA_UNSUPPORTED};
  static const char *const label[] = {"is missing from this book", "not supported: movie.swf (application/x-shockwave-flash)",
    "not supported: clip.flv", "online: http://example.com/v.mp4 - not loaded", "no source given", "not supported: old.wmv"};
  size_t n, count = 0, i;
  unsigned char *zip = zip_book(m, sizeof(m) / sizeof(*m), &n);
  exr_publication *p = open_book(zip, n);
  exr_document *d;
  const char *t = part_text(p, 0, &d);
  const exr_media_item *item = exr_document_media(d, &count);
  CHECK(count == 6 && item);
  for (i = 0; i < count; i++) {
    CHECK(item[i].state == want[i]);
    CHECK(item[i].duration_ms == -1 && contains(item[i].label, label[i]) && contains(t, item[i].label));
    printf("degrade: state=%d  \"%s\"\n", (int)item[i].state, item[i].label);
  }
  CHECK(item[0].path == NULL || !strcmp(item[0].path, "OPS/audio/gone.mp3"));
  CHECK(contains(t, "Before") && contains(t, "After"));
  CHECK(!contains(t, "svg fallback"));   /* ordinary (non-media) objects keep their previous behaviour */
  exr_document_free(d); exr_publication_free(p); mz_free(zip); free(c1);
}

/* ---- group: plain ----------------------------------------------------- */
static void plain(void) {
  static const char opf[] =
    "<package xmlns=\"http://www.idpf.org/2007/opf\" version=\"3.0\"><manifest>"
    "<item id=\"c1\" href=\"c1.xhtml\" media-type=\"application/xhtml+xml\"/></manifest>"
    "<spine><itemref idref=\"c1\"/></spine></package>";
  char *c1 = page("<h1>Title</h1><p>Only words here.</p>");
  member m[] = {{"OPS/book.opf", opf, sizeof(opf) - 1}, {"OPS/c1.xhtml", c1, strlen(c1)}};
  size_t n, count = 99, size;
  unsigned char *zip = zip_book(m, 2, &n);
  exr_publication *p = open_book(zip, n);
  exr_document *d;
  const char *t = part_text(p, 0, &d);
  exr_media_overlay *o = (exr_media_overlay *)1;
  CHECK(exr_document_media(d, &count) == NULL && count == 0);
  t = exr_document_text(d, &size);
  CHECK(size == strlen("Title") + strlen("Only words here.") + 2 || contains(t, "Only words here."));
  CHECK(!contains(t, "[Audio") && !contains(t, "[Video"));
  OK(exr_publication_media_overlay(p, 0, &o, &error));
  CHECK(o == NULL);
  exr_document_free(d); exr_publication_free(p); mz_free(zip); free(c1);
}

int main(int argc, char **argv) {
  make_wav(); make_mp4(); make_mp3();
  if (argc != 2) { fprintf(stderr, "usage: test_media_epub elements|overlay|degrade|plain\n"); return 2; }
  if (!strcmp(argv[1], "elements")) elements();
  else if (!strcmp(argv[1], "overlay")) overlay();
  else if (!strcmp(argv[1], "degrade")) degrade();
  else if (!strcmp(argv[1], "plain")) plain();
  else return 2;
  puts("ok");
  return 0;
}
