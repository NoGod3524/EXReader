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
#define ALPHA "\xce\xb1"
#define BETA "\xce\xb2"
#define GAMMA "\xce\xb3"

static void text(const char *rtf, const char *expected) {
  exr_document *doc = NULL;
  size_t size;
  CHECK(exr_document_open_memory(EXR_RTF, rtf, strlen(rtf), &doc, &error) == EXR_OK);
  CHECK(doc);
  CHECK(!strcmp(exr_document_text(doc, &size), expected));
  CHECK(size == strlen(expected));
  exr_document_free(doc);
}

int main(void) {
  text("{\\rtf1\\ansi\\uc1\\u945\\tab X}", ALPHA "X");
  text("{\\rtf1\\ansi\\uc1\\u945?X}", ALPHA "X");
  text("{\\rtf1\\ansi\\uc1\\u945\\'3fX}", ALPHA "X");
  text("{\\rtf1\\ansi\\uc1\\u945\\{X}", ALPHA "X");
  text("{\\rtf1\\ansi\\uc1\\u945\\}X}", ALPHA "X");
  text("{\\rtf1\\ansi\\uc1\\u945\\\\X}", ALPHA "X");
  text("{\\rtf1\\ansi\\uc1\\u945\\~X}", ALPHA "X");
  text("{\\rtf1\\ansi\\uc1\\u945\\-X}", ALPHA "X");
  text("{\\rtf1\\ansi\\uc1\\u945\\_X}", ALPHA "X");
  text("{\\rtf1\\ansi\\uc1\\u945\\*X}", ALPHA "X");
  text("{\\rtf1\\ansi\\uc1\\u945\\unknown123 X}", ALPHA "X");
  text("{\\rtf1\\ansi\\uc1\\u945\\ansicpg932 X}", ALPHA "X");
  text("{\\rtf1\\ansi\\uc1\\u945\\uc0 X\\u946?Y}", ALPHA "X" BETA "Y");
  text("{\\rtf1\\ansi\\uc1\\u945\\par X}", ALPHA "X");
  text("{\\rtf1\\ansi\\uc1\\u945\\line X}", ALPHA "X");
  text("{\\rtf1\\ansi\\uc1\\u945\\pict X}", ALPHA "X");
  text("{\\rtf1\\ansi\\uc1\\u945\\bin3 {}\\X}", ALPHA "X");
  text("{\\rtf1\\ansi\\uc2\\u945\\bin0 ?X}", ALPHA "X");
  text("{\\rtf1\\ansi\\uc3\\u945?\\tab \\'3fX}", ALPHA "X");
  text("{\\rtf1\\ansi\\uc1\\u945\r\n?X}", ALPHA "X");
  text("{\\rtf1\\ansi\\uc0\\u945X\\tab Y}", ALPHA "X Y");
  text("{\\rtf1\\ansi\\uc1{\\u945}X}", ALPHA "X");
  text("{\\rtf1\\ansi\\uc1\\u945{X}Y}", ALPHA "XY");
  text("{\\rtf1\\ansi\\uc1{\\uc2\\u945??\\uc0\\u946X}\\u947?Y}",
       ALPHA BETA "X" GAMMA "Y");
  text("{\\rtf1\\ansi\\uc1\\u945{\\*\\unknown ignored}X}", ALPHA "X");
  text("{\\rtf1\\ansi A{\\fonttbl{\\f0 ignored;}}{\\*\\unknown ignored}B}", "AB");
  text("{\\rtf1\\ansi\\uc1\\u-10179\\tab \\u-8704\\~X}", "\xf0\x9f\x98\x80X");
  text("{\\rtf1\\ansi\\uc1\\u-10179?\\u-8704?X}", "\xf0\x9f\x98\x80X");
  text("{\\rtf1\\ansi A\\tab B\\par C}", "A B\nC");
  printf("RTF fallback: %u checks\n", checks);
  return 0;
}
