/* SPDX-License-Identifier: MIT */
#include <exreader.h>
#include <stdio.h>

int main(void) {
  /* Combining accent, ZWJ emoji, flag pair, and one CJK character. */
  const char text[] = "a\xcc\x81\xf0\x9f\x91\xa9\xe2\x80\x8d\xf0\x9f\x92\xbb"
                      "\xf0\x9f\x87\xba\xf0\x9f\x87\xb8\xe7\x94\xb2";
  const size_t offsets[] = {0, 3, 14, 22, 25};
  unsigned char *boundaries = NULL;
  exr_error error = {0};
  size_t at, next = 0;
  if (exr_text_analyze(text, sizeof(text) - 1, &boundaries, &error) != EXR_OK) {
    fprintf(stderr, "%s\n", error.message);
    return 1;
  }
  for (at = 0; at < sizeof(text); at++) {
    int expected = next < sizeof(offsets) / sizeof(*offsets) && at == offsets[next];
    if (!!(boundaries[at] & EXR_BOUNDARY_GRAPHEME) != expected) {
      fprintf(stderr, "Unexpected grapheme boundary at byte %zu\n", at);
      exr_free(boundaries);
      return 1;
    }
    if (expected)
      next++;
  }
  for (at = 1; at < next; at++)
    printf("Grapheme %zu: UTF-8 bytes [%zu, %zu)\n", at, offsets[at - 1], offsets[at]);
  printf("EXReader C %s: %zu graphemes in %zu UTF-8 bytes\n",
         exr_version(), next - 1, sizeof(text) - 1);
  exr_free(boundaries);
  return 0;
}
