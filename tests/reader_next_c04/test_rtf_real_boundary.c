/* SPDX-License-Identifier: MIT */
/* Public-API boundary checks for the RTF root-tail candidate: padding that
   some writers append after the final group is accepted and changes nothing;
   truncated, unbalanced, overflowing, bad-\bin and garbage-tailed streams
   stay EXR_FORMAT with no document. Linked only against the installed SDK. */
#include "exreader.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static exr_error error;
static unsigned checks;
#define CHECK(x) do { checks++; if(!(x)) { fprintf(stderr,"line %d: %s (%d: %s)\n",__LINE__,#x,error.code,error.message); return 1; } } while(0)
typedef struct { const char *name; const char *data; size_t size; } sample;
#define S(name,text) { name, text, sizeof(text) - 1 }

static exr_status open_rtf(const sample *s, exr_document **doc) {
  *doc = NULL;
  return exr_document_open_memory(EXR_RTF, s->data, s->size, doc, &error);
}

int main(void) {
  static const char body[] = "{\\rtf1\\ansi\\ansicpg1252\\uc1 Hello {\\b world}\\par Second \\u8217\\'92 end}";
  static const sample padded[] = {
    S("none", ""), S("crlf", "\r\n"), S("one NUL", "\0"), S("many NUL", "\0\0\0\0\0\0\0\0"),
    S("mixed", "\r\n\0 \t\0"),
  };
  static const sample rejected[] = {
    S("truncated in text", "{\\rtf1 Hello"),
    S("truncated nested group", "{\\rtf1 Hello{\\b world}"),
    S("truncated at escape", "{\\rtf1 Hello\\"),
    S("truncated hex escape", "{\\rtf1 A\\'4"),
    S("only the header", "{\\rtf1"),
    S("too short", "{\\rt"),
    S("extra close", "{\\rtf1 A}}"),
    S("text after root", "{\\rtf1 A}x"),
    S("NUL then text", "{\\rtf1 A}\0x"),
    S("second root", "{\\rtf1 A}{\\rtf1 B}"),
    S("control after root", "{\\rtf1 A}\\par"),
    S("SUB after root", "{\\rtf1 A}\x1a"),
    S("NUL inside the body", "{\\rtf1 A\0B}"),
    S("escaped NUL", "{\\rtf1 A\\'00B}"),
    S("parameter 2^31", "{\\rtf1\\unknown2147483648 A}"),
    S("parameter beyond 64 bit", "{\\rtf1\\unknown99999999999999999999 A}"),
    S("parameter below -2^31", "{\\rtf1\\unknown-2147483649 A}"),
    S("bin longer than the stream", "{\\rtf1 {\\pict\\pngblip\\bin10 abc}}"),
    S("bin length 2^31-1", "{\\rtf1 {\\pict\\pngblip\\bin2147483647 abc}}"),
    S("negative bin", "{\\rtf1 {\\pict\\pngblip\\bin-1 abc}}"),
    S("bin without length", "{\\rtf1 {\\pict\\pngblip\\bin abc}}"),
    S("unicode out of range", "{\\rtf1 \\u70000 A}"),
    S("lone high surrogate", "{\\rtf1 \\u55357 A}"),
    S("other code page", "{\\rtf1\\ansi\\ansicpg1251 A}"),
  };
  exr_document *base = NULL, *doc = NULL;
  const char *base_text;
  size_t i, base_nodes = 0, nodes = 0;
  char *buffer;

  /* The unpadded stream is the reference. */
  CHECK(open_rtf(&(sample){ "base", body, sizeof(body) - 1 }, &base) == EXR_OK && base);
  base_text = exr_document_text(base, NULL);
  CHECK(base_text && strstr(base_text, "Hello world") && strstr(base_text, "Second \xe2\x80\x99 end"));
  exr_document_nodes(base, &base_nodes);
  CHECK(base_nodes > 4);

  for (i = 0; i < sizeof(padded) / sizeof(*padded); i++) {
    size_t at = sizeof(body) - 1;
    buffer = malloc(at + padded[i].size + 1);
    CHECK(buffer);
    memcpy(buffer, body, at); memcpy(buffer + at, padded[i].data, padded[i].size);
    {
      sample s = { padded[i].name, buffer, at + padded[i].size };
      exr_status status = open_rtf(&s, &doc);
      if (status != EXR_OK) fprintf(stderr, "padded case %s: %d %s\n", padded[i].name, status, error.message);
      CHECK(status == EXR_OK && doc);
    }
    CHECK(!strcmp(exr_document_text(doc, NULL), base_text));
    exr_document_nodes(doc, &nodes);
    CHECK(nodes == base_nodes);
    exr_document_free(doc); doc = NULL; free(buffer);
  }
  exr_document_free(base);

  for (i = 0; i < sizeof(rejected) / sizeof(*rejected); i++) {
    exr_status status = open_rtf(&rejected[i], &doc);
    if (status != EXR_FORMAT || doc) fprintf(stderr, "rejected case \"%s\": status %d doc %p\n", rejected[i].name, status, (void *)doc);
    CHECK(status == EXR_FORMAT && !doc);
  }
  printf("{\"schema\":1,\"test\":\"rtf-real-boundary\",\"padded\":%zu,\"rejected\":%zu,\"checks\":%u}\n",
         sizeof(padded) / sizeof(*padded), sizeof(rejected) / sizeof(*rejected), checks);
  return 0;
}
