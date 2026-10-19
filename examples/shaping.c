/* SPDX-License-Identifier: MIT */
#include <exreader.h>
#include <stdio.h>
#include <string.h>

static exr_status sample(exr_font *font, const char *label, const char *text,
                          uint32_t script, exr_direction direction, exr_error *error) {
  exr_shape_options options = exr_shape_defaults();
  exr_shaped_glyph *glyphs = NULL;
  exr_bidi *bidi = NULL;
  size_t count = 0, scalars = 0, *order = NULL, ordered = 0, i;
  exr_status status;
  options.font_size = 24;
  options.script = script;
  options.direction = direction;
  status = exr_shape(font, 0, text, strlen(text), &options, &glyphs, &count, error);
  if (status != EXR_OK) goto done;
  printf("%s: %zu logical glyphs\n", label, count);
  for (i = 0; i < count; i++) {
    const exr_shaped_glyph *g = &glyphs[i];
    printf("  glyph %u, UTF-8 cluster [%zu,%zu), advance (%.3f,%.3f), "
           "offset (%.3f,%.3f), flags %u\n", (unsigned)g->glyph, g->start, g->end,
           g->advance_x, g->advance_y, g->offset_x, g->offset_y, g->flags);
  }
  status = exr_bidi_analyze(text, strlen(text), direction, &bidi, error);
  if (status != EXR_OK) goto done;
  exr_bidi_scalars(bidi, &scalars);
  status = exr_bidi_reorder(bidi, 0, scalars, &order, &ordered, error);
  if (status != EXR_OK) goto done;
  printf("  BiDi visual scalar indices:");
  for (i = 0; i < ordered; i++) printf(" %zu", order[i]);
  printf("\n");
  /* Scalar order demonstrates UBA separately. A renderer reorders entire shaped
     clusters, keeping a ligature and its attached marks together. */
done:
  exr_free(order);
  exr_bidi_free(bidi);
  exr_free(glyphs);
  return status;
}
static int example_main(int argc, char **argv) {
  const char latin[] = "ffi a\xcc\x81 AV";
  const char arabic[] = "\xd8\xa8\xd9\x8e\xd8\xa8 \xd9\x84\xd8\xa7";
  exr_font *font = NULL;
  exr_error error = {0};
  exr_status status;
  if (argc != 2) {
    fprintf(stderr, "usage: exreader-shaping-example font.ttf\n"
                    "The SDK includes an original test font in examples/shaping-fonts/shaping.ttf.\n");
    return 2;
  }
  status = exr_font_open(argv[1], &font, &error);
  if (status == EXR_OK)
    status = sample(font, "Latin ffi, combining accent and kerning", latin,
                    EXR_TAG('l','a','t','n'), EXR_DIRECTION_LTR, &error);
  if (status == EXR_OK)
    status = sample(font, "Arabic joining, mark and lam-alef", arabic,
                    EXR_TAG('a','r','a','b'), EXR_DIRECTION_RTL, &error);
  if (status != EXR_OK) fprintf(stderr, "EXReader error %d: %s\n", (int)error.code, error.message);
  exr_font_free(font);
  return status == EXR_OK ? 0 : 1;
}
#include "entry.h"
