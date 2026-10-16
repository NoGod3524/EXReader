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

static void text(const char *html, const char *expected) {
  exr_document *doc = NULL;
  size_t size;
  CHECK(exr_document_open_memory(EXR_HTML, html, strlen(html), &doc, &error) == EXR_OK);
  CHECK(doc);
  CHECK(!strcmp(exr_document_text(doc, &size), expected));
  CHECK(size == strlen(expected));
  exr_document_free(doc);
}

int main(void) {
  text("<script>if(a<b) foo();</script><p>hi</p>", "hi");
  text("<script>const x=\"<a\";</script><p>hi</p>", "hi");
  text("<p>before</p><script>if(a<b) foo();</script><p>after</p>", "before\nafter");
  text("<style>p::before { content: \"<a\"; }</style><p>hi</p>", "hi");
  text("<script><!-- raw <not-a-tag \" '</script><p>hi</p>", "hi");
  text("<style><!-- raw <not-a-tag \" '</style><p>hi</p>", "hi");
  text("<ScRiPt>if(a<b) foo();</sCrIpT><p>hi</p>", "hi");
  text("<StYlE>x { content: '<b'; }</sTyLe><p>hi</p>", "hi");
  text("<script>SECRET </scriptx><p>SECRET</p></script><p>hi</p>", "hi");
  text("<script>SECRET </script-x><p>SECRET</p></script><p>hi</p>", "hi");
  text("<script>SECRET </script:other><p>SECRET</p></script><p>hi</p>", "hi");
  text("<script>SECRET </script_other><p>SECRET</p></script><p>hi</p>", "hi");
  text("<style>SECRET </stylex><p>SECRET</p></style><p>hi</p>", "hi");
  text("<script>SECRET </script ><p>hi</p>", "hi");
  text("<script>SECRET </script\t\r\n><p>hi</p>", "hi");
  text("<style>SECRET </style\f><p>hi</p>", "hi");
  text("<script>SECRET </script/><p>hi</p>", "hi");
  text("<script>\"&lt;/script&gt;\"; &amp;SECRET;</script><p>A &amp; B</p>", "A & B");
  text("<script>SECRET <style>SECRET</style></script><p>hi</p>", "hi");
  text("<style>SECRET <script>SECRET</script></style><p>hi</p>", "hi");
  text("<head><script>if(a<b) foo();</script></head><body><p>hi</p></body>", "hi");
  text("<head><style>x { content: '<a'; }</style></head><body><p>hi</p></body>", "hi");
  text("<head><script>const x='</head><p>SECRET';</script>SECRET</head><p>hi</p>", "hi");
  text("<head><style>x { content: '</head><p>SECRET'; }</style>SECRET</head><p>hi</p>", "hi");
  text("<object><script>if(a<b) foo();</script>SECRET</object><p>hi</p>", "hi");
  text("<p>A<script>if(a<b) foo();</script>B<style>x{content:'<b';}</style>C</p>", "ABC");
  text("<script>SECRET</script><style>SECRET</style><h1>Heading</h1><p>Body</p>", "Heading\nBody");
  text("<!-- normal comment --><p>hi</p>", "hi");
  text("<p>hi</p><script>unterminated raw <b \" <!--", "hi");
  text("<p>hi</p><style>unterminated raw <b \" <!--", "hi");
  printf("HTML raw text: %u checks\n", checks);
  return 0;
}
