/* SPDX-License-Identifier: GPL-3.0-only */
#include "exreader.h"
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static exr_error error;
static unsigned checks;
static exr_font *font;
static const char *directory;
#define CHECK(x) do { checks++; if (!(x)) { \
  fprintf(stderr, "line %d: %s (%d: %s)\n", __LINE__, #x, (int)error.code, error.message); \
  exit(1); } } while (0)
#define OK(x) CHECK((x) == EXR_OK)
#define TAG(a,b,c,d) EXR_TAG(a,b,c,d)

enum { SPACE=1, A=2, V=3, F=4, I=5, FFI=6, FI=7, SMALL_A=8, B=9, C=10, D=11,
       X=12, Y=13, Z=14, ACUTE=15, GRAVE=16, DOT=17, BEH=18, BEH_ISOL=19,
       BEH_INIT=20, BEH_MEDI=21, BEH_FINA=22, LAM=23, LAM_ISOL=24,
       LAM_INIT=25, LAM_MEDI=26, LAM_FINA=27, ALEF=28, ALEF_ISOL=29,
       ALEF_FINA=30, LAMALEF=31, LAMALEF_FINA=32, FATHA=33 };
typedef struct {
  uint32_t glyph;
  size_t start, end;
  float ax, ay, x, y;
} expected;
static exr_shape_options options(void) {
  exr_shape_options o = exr_shape_defaults();
  o.font_size = 20;
  o.script = TAG('l','a','t','n');
  o.direction = EXR_DIRECTION_LTR;
  return o;
}
static int close_to(float a, float b) { return isfinite(a) && fabsf(a-b) < 0.015f; }
static exr_font *open_font(const char *name) {
  char path[4096];
  exr_font *result = NULL;
  snprintf(path, sizeof(path), "%s/%s", directory, name);
  OK(exr_font_open(path, &result, &error)); CHECK(result);
  return result;
}
static void expect(const char *text, const exr_shape_options *o,
                    const expected *want, size_t count) {
  exr_shaped_glyph *actual = NULL;
  size_t n = SIZE_MAX, i;
  OK(exr_shape(font, 0, text, strlen(text), o, &actual, &n, &error));
  CHECK(n == count && (n ? actual != NULL : actual == NULL));
  for (i = 0; i < n; i++) {
    if (actual[i].glyph != want[i].glyph || actual[i].start != want[i].start ||
        actual[i].end != want[i].end || !close_to(actual[i].advance_x, want[i].ax) ||
        !close_to(actual[i].advance_y, want[i].ay) ||
        !close_to(actual[i].offset_x, want[i].x) || !close_to(actual[i].offset_y, want[i].y)) {
      fprintf(stderr, "glyph %zu: got gid=%u [%zu,%zu) advance=(%.3f,%.3f) "
              "offset=(%.3f,%.3f); expected gid=%u [%zu,%zu) "
              "advance=(%.3f,%.3f) offset=(%.3f,%.3f)\n", i, actual[i].glyph,
              actual[i].start, actual[i].end, actual[i].advance_x, actual[i].advance_y,
              actual[i].offset_x, actual[i].offset_y, want[i].glyph,
              want[i].start, want[i].end, want[i].ax, want[i].ay, want[i].x, want[i].y);
      CHECK(0);
    }
    CHECK(!(actual[i].flags & (EXR_GLYPH_MISSING | EXR_GLYPH_HIDDEN)));
    CHECK(actual[i].start < actual[i].end && actual[i].end <= strlen(text));
  }
  exr_free(actual);
}
static void latin(void) {
  exr_shape_options o = options();
  exr_shape_feature feature;
  const expected ffi[] = {{FFI,0,3,15,0,0,0}};
  const expected fi[] = {{FI,0,2,9,0,0,0}};
  const expected av[] = {{A,0,1,10,0,0,0},{V,1,2,12,0,0,0}};
  const expected plain[] = {{F,0,1,6,0,0,0},{F,1,2,6,0,0,0},{I,2,3,4,0,0,0}};
  const expected av_plain[] = {{A,0,1,12,0,0,0},{V,1,2,12,0,0,0}};
  expect("ffi", &o, ffi, 1); expect("fi", &o, fi, 1); expect("AV", &o, av, 2);
  o.direction = EXR_DIRECTION_RTL;
  expect("AV", &o, av, 2); /* Shape never reverses its logical input sequence. */
  o.direction = EXR_DIRECTION_AUTO; expect("ffi", &o, ffi, 1);
  feature = (exr_shape_feature){TAG('l','i','g','a'), 0};
  o.features = &feature; o.feature_count = 1; expect("ffi", &o, plain, 3);
  feature = (exr_shape_feature){TAG('k','e','r','n'), 0}; expect("AV", &o, av_plain, 2);
  o = options(); o.font_size = 40;
  {
    const expected scaled[] = {{A,0,1,20,0,0,0},{V,1,2,24,0,0,0}};
    expect("AV", &o, scaled, 2);
  }
  o = options(); expect("AV", &o, av, 2); /* No stale metrics after resizing. */
}
static void marks(void) {
  exr_shape_options o = options();
  const expected acute[] = {{SMALL_A,0,3,10,0,0,0},{ACUTE,0,3,0,0,-4,14}};
  const expected stacked[] = {{SMALL_A,0,5,10,0,0,0},{ACUTE,0,5,0,0,-4,14},
                               {DOT,0,5,0,0,-2.4f,17.8f}};
  const expected lig_last[] = {{FI,0,4,9,0,0,0},{ACUTE,0,4,0,0,-1.4f,13}};
  const expected lig_first[] = {{FI,0,4,9,0,0,0},{ACUTE,0,4,0,0,-7,13}};
  const expected uppercase[] = {{A,0,3,12,0,0,0},{ACUTE,0,3,0,0,-5,16}};
  const expected alone[] = {{ACUTE,0,2,0,0,0,0}};
  expect("a\xcc\x81", &o, acute, 2);
  expect("a\xcc\x81\xcc\x87", &o, stacked, 3);
  expect("fi\xcc\x81", &o, lig_last, 2);
  expect("f\xcc\x81i", &o, lig_first, 2);
  expect("A\xcc\x81", &o, uppercase, 2);
  expect("\xcc\x81", &o, alone, 1);
  o.direction = EXR_DIRECTION_RTL;
  expect("a\xcc\x81", &o, acute, 2); /* Offsets are relative to the logical pen. */
}
static void long_marks(void) {
  static const struct {
    const char *prefix;
    unsigned glyph;
    float advance, x, y;
  } cases[] = {{"a", SMALL_A, 10, -4, 14}, {"fi", FI, 9, -1.4f, 13},
               {"A", A, 12, -5, 16}};
  const size_t marks = 16384;
  exr_shape_options o = options();
  size_t c;
  for (c = 0; c < sizeof(cases)/sizeof(*cases); c++) {
    size_t prefix = strlen(cases[c].prefix), size = prefix + marks*2 + 2, i, count;
    char *text = malloc(size + 1);
    exr_shaped_glyph *g = NULL;
    CHECK(text);
    memcpy(text, cases[c].prefix, prefix);
    for (i = 0; i < marks; i++) memcpy(text + prefix + i*2, "\xcc\x81", 2);
    memcpy(text + prefix + marks*2, "\xcc\x87", 3);
    OK(exr_shape(font, 0, text, size, &o, &g, &count, &error));
    CHECK(count == marks + 2 && g[0].glyph == cases[c].glyph);
    CHECK(close_to(g[0].advance_x, cases[c].advance));
    for (i = 0; i < count; i++) {
      CHECK(g[i].start == 0 && g[i].end == size);
      CHECK(!(g[i].flags & (EXR_GLYPH_HIDDEN | EXR_GLYPH_MISSING)));
      if (!i) continue;
      CHECK(g[i].glyph == (i <= marks ? ACUTE : DOT));
      CHECK(close_to(g[i].advance_x, 0));
      CHECK(close_to(g[i].offset_x, cases[c].x + (i <= marks ? 0 : 1.6f)));
      CHECK(close_to(g[i].offset_y, cases[c].y + (i <= marks ? 0 : 3.8f)));
    }
    exr_free(g); free(text);
  }
}
static void optional_lookups(void) {
  exr_shape_options o = options();
  exr_shape_feature feature = {TAG('s','s','0','1'), 1};
  const expected multiple[] = {{SMALL_A,0,1,10,0,0,0},{B,0,1,10,0,0,0}};
  const expected alternate[] = {{B,0,1,10,0,0,0}};
  const expected single[] = {{D,0,1,10,0,0,0}};
  const expected context[] = {{SMALL_A,0,1,10,0,0,0},{C,1,2,10,0,0,0}};
  const expected chain[] = {{SMALL_A,0,1,10,0,0,0},{D,1,2,10,0,0,0},{C,2,3,10,0,0,0}};
  const expected extension[] = {{X,0,1,10,0,0,0}};
  /* The API retains raw yAdvance; horizontal HarfBuzz suppresses this component. */
  const expected value[] = {{X,0,1,10.8f,1,0.4f,0.6f}};
  const expected pair_class[] = {{SMALL_A,0,1,8.4f,0,0,0},{C,1,2,10,0,0,0}};
  const expected pos_context[] = {{SMALL_A,0,1,10,0,0,0},{B,1,2,10,0,0.4f,0.6f},
                                   {C,2,3,10,0,0,0}};
  const expected pos_extension[] = {{Z,0,1,10,0,0.6f,0.8f}};
  const expected cursive[] = {{X,0,1,9,0,0,0},{Y,1,2,9,0,-1,1.6f}};
  o.features = &feature; o.feature_count = 1;
  expect("x", &o, multiple, 2);
  feature.tag = TAG('s','s','0','2'); feature.value = 2; expect("y", &o, alternate, 1);
  feature.tag = TAG('s','s','0','3'); feature.value = 1; expect("z", &o, single, 1);
  feature.tag = TAG('s','s','0','4'); expect("ab", &o, context, 2);
  feature.tag = TAG('s','s','0','5'); expect("abc", &o, chain, 3);
  feature.tag = TAG('s','s','0','6'); expect("abc", &o, chain, 3);
  feature.tag = TAG('s','s','0','7'); expect("z", &o, extension, 1);
  feature.tag = TAG('s','s','0','8'); expect("x", &o, value, 1);
  feature.tag = TAG('s','s','0','9'); expect("ac", &o, pair_class, 2);
  feature.tag = TAG('s','s','1','0'); expect("abc", &o, pos_context, 3);
  feature.tag = TAG('s','s','1','1'); expect("z", &o, pos_extension, 1);
  feature.tag = TAG('s','s','1','2'); expect("xy", &o, cursive, 2);
  o.direction = EXR_DIRECTION_RTL;
  {
    const expected rtl[] = {{X,0,1,10,0,0,2.4f},{Y,1,2,9.6f,0,0,0}};
    expect("xy", &o, rtl, 2);
  }
  o.direction = EXR_DIRECTION_LTR;
  feature.tag = TAG('s','s','0','2'); feature.value = 0;
  {
    const expected untouched[] = {{Y,0,1,10,0,0,0}};
    expect("y", &o, untouched, 1);
    feature.value = 4; expect("y", &o, untouched, 1);
  }
}
static void context_formats(void) {
  exr_shape_options o = options();
  exr_shape_feature feature;
  const expected substitution[] = {{SMALL_A,0,1,10,0,0,0},{D,1,2,10,0,0,0},
                                    {C,2,3,10,0,0,0}};
  const expected positioning[] = {{SMALL_A,0,1,10,0,0,0},{B,1,2,10,0,0.4f,0.6f},
                                   {C,2,3,10,0,0,0}};
  const expected no_context[] = {{B,0,1,10,0,0,0},{B,1,2,10,0,0,0}};
  const expected no_chain[] = {{SMALL_A,0,1,10,0,0,0},{B,1,2,10,0,0,0},
                                {D,2,3,10,0,0,0}};
  unsigned n;
  o.features = &feature; o.feature_count = 1;
  for (n = 1; n <= 10; n++) {
    int chain = n == 4 || n == 5 || n == 9 || n == 10;
    feature = (exr_shape_feature){TAG('z','z','0'+n/10,'0'+n%10), 1};
    expect(chain ? "abc" : "ab", &o, n <= 5 ? substitution : positioning, chain ? 3 : 2);
    expect(chain ? "abd" : "bb", &o, chain ? no_chain : no_context, chain ? 3 : 2);
  }
}
static void arabic(void) {
  static const char beh[] = "\xd8\xa8", behs[] = "\xd8\xa8\xd8\xa8";
  exr_shape_options o = options();
  const expected isolated[] = {{BEH_ISOL,0,2,12,0,0,0}};
  const expected pair[] = {{BEH_INIT,0,2,12,0,0,0},{BEH_FINA,2,4,12,0,0,0}};
  const expected triple[] = {{BEH_INIT,0,2,12,0,0,0},{BEH_MEDI,2,4,12,0,0,0},
                             {BEH_FINA,4,6,12,0,0,0}};
  const expected lamalef[] = {{LAMALEF,0,4,14,0,0,0}};
  const expected joined_lig[] = {{BEH_INIT,0,2,12,0,0,0},{LAMALEF_FINA,2,6,15,0,0,0}};
  const expected transparent[] = {{BEH_INIT,0,4,12,0,0,0},{FATHA,0,4,0,0,-6,12},
                                   {BEH_FINA,4,6,12,0,0,0}};
  o.script = TAG('a','r','a','b'); o.direction = EXR_DIRECTION_RTL;
  expect(beh, &o, isolated, 1); expect(behs, &o, pair, 2);
  expect("\xd8\xa8\xd8\xa8\xd8\xa8", &o, triple, 3);
  expect("\xd9\x84\xd8\xa7", &o, lamalef, 1);
  expect("\xd8\xa8\xd9\x84\xd8\xa7", &o, joined_lig, 2);
  expect("\xd8\xa8\xd9\x8e\xd8\xa8", &o, transparent, 3);
  o.script = 0; o.direction = EXR_DIRECTION_AUTO;
  expect(behs, &o, pair, 2);
  o.script = TAG('a','r','a','b'); o.direction = EXR_DIRECTION_RTL;
  o.context_before = 0x628;
  {
    const expected final[] = {{BEH_FINA,0,2,12,0,0,0}};
    expect(beh, &o, final, 1);
  }
  o.context_after = 0x628;
  {
    const expected medial[] = {{BEH_MEDI,0,2,12,0,0,0}};
    expect(beh, &o, medial, 1);
  }
  o.context_before = 0;
  {
    const expected initial[] = {{BEH_INIT,0,2,12,0,0,0}};
    expect(beh, &o, initial, 1);
  }
  o.context_before = 0x627; o.context_after = 0;
  expect(beh, &o, isolated, 1); /* Alef cannot join forward to this beh. */
  o.context_before = 0; o.script = TAG('h','e','b','r');
  {
    const expected hebrew[] = {{36,0,2,10,0,0,0},{37,2,4,10,0,0,0},{38,4,6,10,0,0,0}};
    expect("\xd7\x90\xd7\x91\xd7\x92", &o, hebrew, 3);
  }
}
static void controls_and_missing(void) {
  exr_shape_options o = options();
  exr_shaped_glyph *g = NULL;
  size_t n;
  o.script = TAG('l','a','t','n'); o.direction = EXR_DIRECTION_LTR;
  OK(exr_shape(font, 0, "f\xe2\x80\x8c" "i", 5, &o, &g, &n, &error));
  CHECK(n == 3 && g[0].glyph == F && g[2].glyph == I);
  CHECK((g[1].flags & EXR_GLYPH_HIDDEN) && !g[1].advance_x);
  exr_free(g); g = NULL;
  o.script = TAG('a','r','a','b'); o.direction = EXR_DIRECTION_RTL;
  OK(exr_shape(font, 0, "\xd8\xa8\xe2\x80\x8c\xd8\xa8", 7, &o, &g, &n, &error));
  CHECK(n == 3 && g[0].glyph == BEH_ISOL && g[2].glyph == BEH_ISOL);
  CHECK(g[0].start == 0 && g[0].end == 5 && g[1].start == 0 && g[1].end == 5);
  CHECK(g[2].start == 5 && g[2].end == 7);
  CHECK((g[1].flags & EXR_GLYPH_HIDDEN) && !g[1].advance_x && !g[1].advance_y);
  exr_free(g); g = NULL;
  OK(exr_shape(font, 0, "\xd8\xa8\xe2\x80\x8d\xd8\xa8", 7, &o, &g, &n, &error));
  CHECK(n == 3 && g[0].glyph == BEH_INIT && g[2].glyph == BEH_FINA);
  CHECK(g[0].start == 0 && g[0].end == 5 && g[1].start == 0 && g[1].end == 5);
  CHECK(g[2].start == 5 && g[2].end == 7);
  CHECK((g[1].flags & EXR_GLYPH_HIDDEN) && !g[1].advance_x && !g[1].advance_y);
  exr_free(g); g = NULL;
  o = options();
  OK(exr_shape(font, 0, "\xce\xa9", 2, &o, &g, &n, &error));
  CHECK(n == 1 && !g[0].glyph && (g[0].flags & EXR_GLYPH_MISSING));
  CHECK(g[0].start == 0 && g[0].end == 2 && close_to(g[0].advance_x, 10));
  exr_free(g); g = NULL;
  OK(exr_shape(font, 0, "\n", 1, &o, &g, &n, &error));
  CHECK(n == 1 && (g[0].flags & EXR_GLYPH_HIDDEN) && !g[0].advance_x);
  exr_free(g);
}
static void rejected(const char *text, size_t size, const exr_shape_options *o, exr_status code) {
  exr_shaped_glyph *g = (exr_shaped_glyph *)(uintptr_t)1;
  size_t count = 99;
  CHECK(exr_shape(font, 0, text, size, o, &g, &count, &error) == code);
  CHECK(!g && !count && error.code == code && error.message[0]);
}
static void validation(void) {
  exr_shape_options o = options(), defaults = exr_shape_defaults();
  exr_shape_feature feature = {TAG('l','i','g','a'), 1};
  exr_shaped_glyph *g;
  size_t count, i;
  const char *const invalid[] = {"\x80", "\xc0\xaf", "\xc2", "\xe0\x80\x80",
                                 "\xed\xa0\x80", "\xf0\x80\x80\x80", "\xf4\x90\x80\x80"};
  CHECK(defaults.font_size >= 4 && defaults.font_size <= 256 &&
        !defaults.style_flags && defaults.direction == EXR_DIRECTION_AUTO &&
        !defaults.features && !defaults.feature_count && !defaults.context_before && !defaults.context_after);
  g = (exr_shaped_glyph *)(uintptr_t)1; count = 99;
  OK(exr_shape(font, 0, NULL, 0, NULL, &g, &count, &error)); CHECK(!g && !count);
  OK(exr_shape(font, 0, "", 0, &o, &g, &count, &error)); CHECK(!g && !count);
  rejected(NULL, 1, &o, EXR_ARGUMENT);
  for (i = 0; i < sizeof(invalid)/sizeof(*invalid); i++)
    rejected(invalid[i], strlen(invalid[i]), &o, EXR_ENCODING);
  rejected("A", (size_t)64*1024*1024+1, &o, EXR_LIMIT);
  rejected("A", SIZE_MAX, &o, EXR_LIMIT);
  o.font_size = NAN; rejected("A", 1, &o, EXR_ARGUMENT);
  o.font_size = INFINITY; rejected("A", 1, &o, EXR_ARGUMENT);
  o.font_size = 3; rejected("A", 1, &o, EXR_ARGUMENT);
  o.font_size = 257; rejected("A", 1, &o, EXR_ARGUMENT);
  o = options(); o.style_flags = EXR_GLYPH_HIDDEN; rejected("A", 1, &o, EXR_ARGUMENT);
  o = options(); o.direction = (exr_direction)3; rejected("A", 1, &o, EXR_ARGUMENT);
  o = options(); o.feature_count = 1; rejected("A", 1, &o, EXR_ARGUMENT);
  o.features = &feature; o.feature_count = 257; rejected("A", 1, &o, EXR_LIMIT);
  o = options(); g = (exr_shaped_glyph *)(uintptr_t)1; count = 99;
  CHECK(exr_shape(NULL, 0, "A", 1, &o, &g, &count, &error) == EXR_ARGUMENT && !g && !count);
  g = (exr_shaped_glyph *)(uintptr_t)1; count = 99;
  CHECK(exr_shape(font, 1, "A", 1, &o, &g, &count, &error) == EXR_ARGUMENT && !g && !count);
  count = 99;
  CHECK(exr_shape(font, 0, "A", 1, &o, NULL, &count, &error) == EXR_ARGUMENT && !count);
  g = (exr_shaped_glyph *)(uintptr_t)1;
  CHECK(exr_shape(font, 0, "A", 1, &o, &g, NULL, &error) == EXR_ARGUMENT && !g);
}
static void damaged_tables(void) {
  const char *names[] = {"broken-gsub.ttf", "broken-gpos.ttf"};
  size_t i;
  exr_shape_options o = options();
  for (i = 0; i < sizeof(names)/sizeof(*names); i++) {
    exr_font *broken = open_font(names[i]);
    exr_shaped_glyph *g = (exr_shaped_glyph *)(uintptr_t)1;
    size_t count = 99;
    CHECK(exr_shape(broken, 0, "AV ffi", 6, &o, &g, &count, &error) == EXR_FONT);
    CHECK(!g && !count && error.code == EXR_FONT && error.message[0]);
    exr_font_free(broken);
  }
}
int main(int argc, char **argv) {
  CHECK(argc == 2); directory = argv[1]; font = open_font("shaping.ttf");
  validation(); latin(); marks(); long_marks(); optional_lookups(); context_formats();
  arabic(); controls_and_missing(); damaged_tables();
  exr_font_free(font);
  printf("EXReader shaping: %u checks passed\n", checks);
  return 0;
}
