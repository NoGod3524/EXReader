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

static int list_id_checks(void) {
  static const char *ids[] = {"0", "-1", "-2", "-3", "-4", "-5", "-2147483648", "2147483647"};
  const char *level = "{\\listlevel\\levelnfc0\\levelstartat7}";
  char data[4096]; size_t i; exr_document *doc = NULL;
  for(i=0;i<sizeof(ids)/sizeof(*ids);i++) {
    sample s = {"signed list identity", data, 0};
    int count = snprintf(data,sizeof(data),"{\\rtf1{\\*\\listtable{\\list\\listid%s%s}}{\\*\\listoverridetable{\\listoverride\\listid%s\\listoverridecount0\\ls1}}\\pard\\ls1 Identity}",ids[i],level,ids[i]);
    CHECK(count>0 && (size_t)count<sizeof(data)); s.size=(size_t)count;
    CHECK(open_rtf(&s,&doc)==EXR_OK && doc);
    CHECK(strstr(exr_document_text(doc,NULL),"7. Identity"));
    exr_document_free(doc); doc=NULL;
  }
  {
    /* Different signs must never alias via abs() or an offset/sentinel map. */
    sample s = S("positive and negative identities",
      "{\\rtf1{\\*\\listtable{\\list\\listid-2{\\listlevel\\levelnfc0\\levelstartat7}}{\\list\\listid2{\\listlevel\\levelnfc0\\levelstartat19}}}"
      "{\\*\\listoverridetable{\\listoverride\\listid-2\\ls1}{\\listoverride\\listid2\\ls2}}\\pard\\ls1 Negative\\par\\pard\\ls2 Positive}");
    CHECK(open_rtf(&s,&doc)==EXR_OK && doc);
    CHECK(strstr(exr_document_text(doc,NULL),"7. Negative") && strstr(exr_document_text(doc,NULL),"19. Positive"));
    exr_document_free(doc); doc=NULL;
  }
  {
    static const sample bad[] = {
      S("duplicate signed definition", "{\\rtf1{\\*\\listtable{\\list\\listid-2{\\listlevel}}{\\list\\listid-2{\\listlevel}}}A}"),
      S("duplicate override index", "{\\rtf1{\\*\\listtable{\\list\\listid-2{\\listlevel}}}{\\*\\listoverridetable{\\listoverride\\listid-2\\ls1}{\\listoverride\\listid-2\\ls1}}A}"),
      S("negative override index", "{\\rtf1{\\*\\listoverridetable{\\listoverride\\listid-2\\ls-1}}A}"),
      S("zero override index", "{\\rtf1{\\*\\listoverridetable{\\listoverride\\listid-2\\ls0}}A}"),
      S("overflow override index", "{\\rtf1{\\*\\listoverridetable{\\listoverride\\listid-2\\ls2001}}A}"),
      S("missing signed definition", "{\\rtf1{\\*\\listoverridetable{\\listoverride\\listid-2\\ls1}}\\pard\\ls1 A}"),
      S("signed id overflow", "{\\rtf1{\\*\\listtable{\\list\\listid-2147483649{\\listlevel}}}A}"),
      S("missing id value", "{\\rtf1{\\*\\listtable{\\list\\listid{\\listlevel}}}A}"),
    };
    for(i=0;i<sizeof(bad)/sizeof(*bad);i++) {
      CHECK(open_rtf(&bad[i],&doc)==EXR_FORMAT && !doc);
    }
  }
  return 0;
}

int main(int argc, char **argv) {
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
    S("font number 32768", "{\\rtf1{\\fonttbl{\\f32768 X;}}A}"),
    S("negative font number", "{\\rtf1{\\fonttbl{\\f-1 X;}}A}"),
  };
  exr_document *base = NULL, *doc = NULL;
  const char *base_text;
  size_t i, base_nodes = 0, nodes = 0;
  char *buffer;

  if(argc==4 && !strcmp(argv[1],"--projection")) {
    FILE *output; const char *text; size_t size=0;
    CHECK(exr_document_open(argv[2],&doc,&error)==EXR_OK && doc);
    text=exr_document_text(doc,&size); CHECK(text && size);
    output=fopen(argv[3],"wb"); CHECK(output);
    CHECK(fwrite(text,1,size,output)==size); CHECK(fclose(output)==0);
    printf("{\"test\":\"public-text-projection\",\"status\":0,\"bytes\":%zu,\"exact_query_present\":%s}\n",size,strstr(text,"Policy and Procedure TTR") ? "true" : "false");
    exr_document_free(doc); return 0;
  }

  if(argc==3 && (!strcmp(argv[1],"--real-base") || !strcmp(argv[1],"--real-candidate"))) {
    exr_status expected=!strcmp(argv[1],"--real-base") ? EXR_FORMAT : EXR_OK;
    exr_status actual=exr_document_open(argv[2],&doc,&error);
    printf("{\"test\":\"original-public-open\",\"status\":%d,\"expected\":%d,\"document\":%s}\n",actual,expected,doc ? "true" : "false");
    CHECK(actual==expected && (expected==EXR_OK ? doc!=NULL : doc==NULL));
    exr_document_free(doc); return 0;
  }
  CHECK(argc==1);

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

  {
    static const sample theme = S("theme font", "{\\rtf1{\\fonttbl{\\f0 Arial;}{\\flomajor\\f31500 Cambria;}}\\f31500 Themed}");
    CHECK(open_rtf(&theme, &doc) == EXR_OK && doc);
    CHECK(strstr(exr_document_text(doc, NULL), "Themed"));
    exr_document_free(doc); doc = NULL;
  }

  {
    static const sample fonts[] = {
      S("maximum default font", "{\\rtf1\\deff32767{\\fonttbl{\\f32767 Arial;}}Default}"),
      S("maximum explicit font", "{\\rtf1{\\fonttbl{\\f32767 Arial;}}\\f32767 Explicit}"),
      S("duplicate font replaces prior name", "{\\rtf1{\\fonttbl{\\f32767 Old;}{\\f32767 New;}}\\f32767 Replaced}"),
      S("list level maximum font", "{\\rtf1{\\fonttbl{\\f32767 Arial;}}{\\*\\listtable{\\list\\listid1{\\listlevel\\levelnfc0\\f32767}}}{\\*\\listoverridetable{\\listoverride\\listid1\\ls1}}\\pard\\ls1 Maximum}"),
    };
    static const sample bad_fonts[] = {
      S("default font overflow", "{\\rtf1\\deff32768 A}"),
      S("negative default font", "{\\rtf1\\deff-1 A}"),
      S("explicit font overflow", "{\\rtf1\\f32768 A}"),
      S("list font overflow", "{\\rtf1{\\*\\listtable{\\list\\listid1{\\listlevel\\f32768}}}A}"),
      S("negative list font", "{\\rtf1{\\*\\listtable{\\list\\listid1{\\listlevel\\f-1}}}A}"),
    };
    for(i=0;i<sizeof(fonts)/sizeof(*fonts);i++) {
      CHECK(open_rtf(&fonts[i],&doc)==EXR_OK && doc);
      CHECK(exr_document_text(doc,NULL) && *exr_document_text(doc,NULL));
      exr_document_free(doc); doc=NULL;
    }
    for(i=0;i<sizeof(bad_fonts)/sizeof(*bad_fonts);i++) CHECK(open_rtf(&bad_fonts[i],&doc)==EXR_FORMAT && !doc);
  }
  CHECK(list_id_checks()==0);

  for (i = 0; i < sizeof(rejected) / sizeof(*rejected); i++) {
    exr_status status = open_rtf(&rejected[i], &doc);
    if (status != EXR_FORMAT || doc) fprintf(stderr, "rejected case \"%s\": status %d doc %p\n", rejected[i].name, status, (void *)doc);
    CHECK(status == EXR_FORMAT && !doc);
  }
  printf("{\"schema\":1,\"test\":\"rtf-real-boundary\",\"padded\":%zu,\"rejected\":%zu,\"checks\":%u}\n",
         sizeof(padded) / sizeof(*padded), sizeof(rejected) / sizeof(*rejected), checks);
  return 0;
}
