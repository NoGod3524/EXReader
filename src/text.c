/* SPDX-License-Identifier: MIT */
#include "text_internal.h"
#include "text_line.h"

static int grapheme(uint32_t cp) {
  if (cp >= 0xac00 && cp <= 0xd7a3)
    return (cp - 0xac00) % 28 ? exr_gcb_lvt : exr_gcb_lv;
  return exr_unicode_property(exr_gcb_ranges, EXR_GCB_RANGE_COUNT, cp);
}
static int control(int gcb) {
  return gcb == exr_gcb_cr || gcb == exr_gcb_lf || gcb == exr_gcb_control;
}
unsigned exr_text_step(exr_text_state *s, uint32_t cp, exr_text_next next, void *context) {
  int gcb = grapheme(cp), before = s->previous_gcb;
  int incb = exr_unicode_property(exr_incb_ranges, EXR_INCB_RANGE_COUNT, cp);
  int ep = exr_unicode_property(exr_ep_ranges, EXR_EP_RANGE_COUNT, cp);
  int split = 1;
  unsigned flags;
  if (s->started) {
    if (before == exr_gcb_cr && gcb == exr_gcb_lf)
      split = 0; /* GB3 */
    else if (control(before) || control(gcb))
      split = 1; /* GB4/GB5 */
    else if (before == exr_gcb_l && (gcb == exr_gcb_l || gcb == exr_gcb_v ||
                                     gcb == exr_gcb_lv || gcb == exr_gcb_lvt))
      split = 0; /* GB6 */
    else if ((before == exr_gcb_lv || before == exr_gcb_v) &&
             (gcb == exr_gcb_v || gcb == exr_gcb_t))
      split = 0; /* GB7 */
    else if ((before == exr_gcb_lvt || before == exr_gcb_t) && gcb == exr_gcb_t)
      split = 0; /* GB8 */
    else if (gcb == exr_gcb_extend || gcb == exr_gcb_zwj ||
             gcb == exr_gcb_spacingmark || before == exr_gcb_prepend)
      split = 0; /* GB9/9a/9b */
    else if (incb == exr_incb_consonant && s->indic_chain == 2)
      split = 0; /* GB9c */
    else if (ep && before == exr_gcb_zwj && s->zwj_after_ep)
      split = 0; /* GB11 */
    else if (before == exr_gcb_regional_indicator &&
             gcb == exr_gcb_regional_indicator && s->ri_odd)
      split = 0; /* GB12/GB13 */
  }
  flags = exr_line_step(&s->line, cp, next, context);
  if (split)
    flags |= EXR_BOUNDARY_GRAPHEME;
  else
    flags = 0;
  s->zwj_after_ep = gcb == exr_gcb_zwj && s->ep_chain;
  if (ep)
    s->ep_chain = 1;
  else if (gcb != exr_gcb_extend)
    s->ep_chain = 0;
  if (incb == exr_incb_consonant)
    s->indic_chain = 1;
  else if (incb == exr_incb_linker && s->indic_chain)
    s->indic_chain = 2;
  else if (incb != exr_incb_extend)
    s->indic_chain = 0;
  s->ri_odd = gcb == exr_gcb_regional_indicator ? !s->ri_odd : 0;
  s->previous_gcb = gcb;
  s->started = 1;
  return flags;
}

int exr_text_hidden(uint32_t cp) {
  return (control(grapheme(cp)) && cp != '\t') || cp == 0x200c || cp == 0x200d ||
         cp == 0x034f || exr_text_variation_selector(cp) || (cp >= 0xe0020 && cp <= 0xe007f);
}

typedef struct { const char *text; size_t at, size; } text_cursor;
static int following_scalar(void *context, uint32_t *cp) {
  text_cursor *c = context;
  return c->at < c->size && exr_next(c->text, c->size, &c->at, cp);
}

exr_status exr_text_analyze(const char *text, size_t size, unsigned char **out, exr_error *e) {
  unsigned char *map;
  exr_text_state state = {0};
  size_t at = 0;
  uint32_t cp;
  if (!out)
    return exr_fail(e, EXR_ARGUMENT, "Missing text boundary output");
  *out = NULL;
  if (!text)
    return exr_fail(e, EXR_ARGUMENT, "Missing UTF-8 text");
  if (size > EXR_MAX_TEXT)
    return exr_fail(e, EXR_LIMIT, "Text analysis exceeds 64 MiB");
  map = calloc(size + 1, 1);
  if (!map)
    return exr_fail(e, EXR_MEMORY, "Text boundary allocation failed");
  while (at < size) {
    size_t start = at;
    if (!exr_next(text, size, &at, &cp)) {
      free(map);
      return exr_fail(e, EXR_ENCODING, "Invalid UTF-8 in text");
    }
    {
      text_cursor cursor = {text, at, size};
      map[start] = (unsigned char)exr_text_step(&state, cp, following_scalar, &cursor);
    }
  }
  map[size] = EXR_BOUNDARY_GRAPHEME | EXR_BOUNDARY_LINE | EXR_BOUNDARY_MANDATORY;
  *out = map;
  return exr_fail(e, EXR_OK, "");
}
