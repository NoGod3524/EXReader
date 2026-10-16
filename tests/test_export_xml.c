/* SPDX-License-Identifier: GPL-3.0-only */
#include "exreader.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static exr_error error;
static unsigned checks;
#define CHECK(x)                                                                                    \
  do {                                                                                              \
    checks++;                                                                                       \
    if (!(x)) {                                                                                     \
      fprintf(stderr, "line %d: %s (%d: %s)\n", __LINE__, #x, (int)error.code, error.message);       \
      exit(1);                                                                                      \
    }                                                                                               \
  } while (0)
#define OK(x) CHECK((x) == EXR_OK)

static const exr_format xml_formats[] = {EXR_HTML, EXR_FB2, EXR_EPUB, EXR_DOCX};

static exr_document *document(const char *title, const char *text) {
  exr_node_input nodes[] = {
      {EXR_NODE_DOCUMENT, SIZE_MAX, NULL, NULL, NULL, 0},
      {EXR_NODE_CHAPTER, 0, NULL, NULL, NULL, 0},
      {EXR_NODE_PARAGRAPH, 1, NULL, NULL, NULL, 0},
      {EXR_NODE_TEXT, 2, NULL, text, NULL, 0}};
  exr_chapter_input chapter = {"main", "main.unit", 1, 1};
  exr_document_input input = {title, nodes, 4, &chapter, 1, NULL, 0};
  exr_document *doc = NULL;
  OK(exr_document_create(&input, &doc, &error));
  return doc;
}

static void scalar(uint32_t cp, char text[8]) {
  size_t n = 0;
  text[n++] = 'A';
  if (cp <= 0x7f)
    text[n++] = (char)cp;
  else if (cp <= 0x7ff) {
    text[n++] = (char)(0xc0 | (cp >> 6));
    text[n++] = (char)(0x80 | (cp & 63));
  } else if (cp <= 0xffff) {
    text[n++] = (char)(0xe0 | (cp >> 12));
    text[n++] = (char)(0x80 | ((cp >> 6) & 63));
    text[n++] = (char)(0x80 | (cp & 63));
  } else {
    text[n++] = (char)(0xf0 | (cp >> 18));
    text[n++] = (char)(0x80 | ((cp >> 12) & 63));
    text[n++] = (char)(0x80 | ((cp >> 6) & 63));
    text[n++] = (char)(0x80 | (cp & 63));
  }
  text[n++] = 'B';
  text[n] = 0;
}

static void rejects(exr_document *doc, const char *field) {
  size_t i;
  for (i = 0; i < sizeof(xml_formats) / sizeof(*xml_formats); i++) {
    void *bytes = (void *)(uintptr_t)1;
    size_t size = 99;
    if (xml_formats[i] == EXR_DOCX && !strcmp(field, "title"))
      continue; /* This exporter does not serialize a DOCX title. */
    CHECK(exr_document_export(doc, xml_formats[i], &bytes, &size, &error) == EXR_ENCODING);
    CHECK(!bytes && !size && error.code == EXR_ENCODING);
    CHECK(strstr(error.message, "XML 1.0") && strstr(error.message, field));
    CHECK(exr_document_export(doc, xml_formats[i], &bytes, &size, NULL) == EXR_ENCODING);
    CHECK(!bytes && !size);
  }
}

static void roundtrip(exr_document *doc, exr_format format, int exact_text) {
  exr_document *copy = NULL;
  void *bytes = NULL;
  size_t size;
  OK(exr_document_export(doc, format, &bytes, &size, &error));
  CHECK(bytes && size);
  OK(exr_document_open_memory(format, bytes, size, &copy, &error));
  if (exact_text)
    CHECK(!strcmp(exr_document_text(doc, NULL), exr_document_text(copy, NULL)));
  exr_document_free(copy);
  exr_free(bytes);
}

static void forbidden(void) {
  uint32_t cp;
  /* XML 1.0 forbids C0 controls except TAB/LF/CR, and BMP U+FFFE/U+FFFF. */
  for (cp = 1; cp <= 0xffff; cp++) {
    exr_document *body, *title;
    char text[8];
    if (!((cp < 0x20 && cp != 9 && cp != 10 && cp != 13) || cp >= 0xfffe))
      continue;
    scalar(cp, text);
    body = document("Valid title", text);
    title = document(text, "Valid body");
    rejects(body, "document text");
    rejects(title, "title");
    roundtrip(title, EXR_DOCX, 1);
    /* TXT and RTF can represent these scalars and retain their existing behavior. */
    roundtrip(body, EXR_TXT, 1);
    roundtrip(body, EXR_RTF, 1);
    roundtrip(title, EXR_TXT, 1);
    roundtrip(title, EXR_RTF, 1);
    exr_document_free(body);
    exr_document_free(title);
  }
}

static void allowed(void) {
  static const uint32_t codepoints[] = {
      9, 10, 13, 0x20, 0x7f, 0x85, 0xd7ff, 0xe000, 0xfdd0, 0xfdef,
      0xfffd, 0x10000, 0x1fffe, 0x1ffff, 0x10fffe, 0x10ffff};
  size_t i, j;
  for (i = 0; i < sizeof(codepoints) / sizeof(*codepoints); i++) {
    char text[8];
    exr_document *doc;
    scalar(codepoints[i], text);
    doc = document(text, text);
    for (j = 0; j < sizeof(xml_formats) / sizeof(*xml_formats); j++)
      roundtrip(doc, xml_formats[j], 1);
    exr_document_free(doc);
  }
  {
    /* Entity-looking literal text must be escaped, not interpreted as a scalar. */
    exr_document *doc = document("<&\"' title", "A &#1; &#xFFFF; <>&\"' B");
    for (i = 0; i < sizeof(xml_formats) / sizeof(*xml_formats); i++)
      roundtrip(doc, xml_formats[i], 1);
    exr_document_free(doc);
  }
}

int main(void) {
  forbidden();
  allowed();
  printf("export XML: %u checks\n", checks);
  return 0;
}
