/* SPDX-License-Identifier: GPL-3.0-only */
#include "text_internal.h"
#include "unicode_data.h"

static int property(const exr_unicode_range *ranges, size_t count, uint32_t cp) {
  size_t lo = 0, hi = count;
  while (lo < hi) {
    size_t mid = lo + (hi - lo) / 2;
    if (cp < ranges[mid].first)
      hi = mid;
    else if (cp > ranges[mid].last)
      lo = mid + 1;
    else
      return ranges[mid].value;
  }
  return 0;
}
static int grapheme(uint32_t cp) {
  if (cp >= 0xac00 && cp <= 0xd7a3)
    return (cp - 0xac00) % 28 ? exr_gcb_lvt : exr_gcb_lv;
  return property(exr_gcb_ranges, EXR_GCB_RANGE_COUNT, cp);
}
static int control(int gcb) {
  return gcb == exr_gcb_cr || gcb == exr_gcb_lf || gcb == exr_gcb_control;
}
static int hard(int lb) {
  return lb == exr_lb_bk || lb == exr_lb_cr || lb == exr_lb_lf || lb == exr_lb_nl;
}
static int ideographic(int lb) {
  return lb == exr_lb_id || lb == exr_lb_eb || lb == exr_lb_em || lb == exr_lb_ri ||
         lb == exr_lb_jl || lb == exr_lb_jv || lb == exr_lb_jt ||
         lb == exr_lb_h2 || lb == exr_lb_h3;
}
static int closing(int lb) {
  return lb == exr_lb_cl || lb == exr_lb_cp || lb == exr_lb_ex ||
         lb == exr_lb_is || lb == exr_lb_sy || lb == exr_lb_ns || lb == exr_lb_in;
}
static int line_class(int lb, uint32_t cp) {
  if (cp == 0x2018 || cp == 0x201c || cp == 0x301d)
    return exr_lb_op;
  if (cp == 0x2019 || cp == 0x201d || cp == 0x301e || cp == 0x301f)
    return exr_lb_cl;
  if (lb == exr_lb_ai || lb == exr_lb_sg || lb == exr_lb_xx || lb == exr_lb_sa)
    return exr_lb_al;
  return lb == exr_lb_cj ? exr_lb_ns : lb;
}
static unsigned line_boundary(const exr_text_state *s, int current, int raw) {
  int previous = s->previous_lb;
  int base = previous == exr_lb_sp ? s->space_base : previous;
  if (!s->started)
    return 0;
  if (s->previous_raw_lb == exr_lb_cr && raw == exr_lb_lf)
    return EXR_BOUNDARY_GLUE;
  if (hard(s->previous_raw_lb))
    return EXR_BOUNDARY_LINE | EXR_BOUNDARY_MANDATORY;
  if (hard(raw))
    return EXR_BOUNDARY_GLUE;
  if (current == exr_lb_wj || previous == exr_lb_wj ||
      current == exr_lb_gl || previous == exr_lb_gl)
    return EXR_BOUNDARY_GLUE;
  if (raw == exr_lb_sp || raw == exr_lb_zw)
    return EXR_BOUNDARY_GLUE;
  if (s->previous_raw_lb == exr_lb_zwj)
    return EXR_BOUNDARY_GLUE;
  if (base == exr_lb_op || closing(current))
    return EXR_BOUNDARY_GLUE;
  if (base == exr_lb_zw || previous == exr_lb_sp)
    return EXR_BOUNDARY_LINE;
  if (previous == exr_lb_ba || previous == exr_lb_hy || previous == exr_lb_hh ||
      previous == exr_lb_b2 || previous == exr_lb_cb || current == exr_lb_cb)
    return EXR_BOUNDARY_LINE;
  /* This is a documented UAX #14 subset; dictionary, contextual quote and
     numeric tailoring are separate from the complete UAX #29 algorithm. */
  if (ideographic(previous) || ideographic(current))
    return EXR_BOUNDARY_LINE;
  return 0;
}

unsigned exr_text_step(exr_text_state *s, uint32_t cp) {
  int gcb = grapheme(cp), before = s->previous_gcb;
  int incb = property(exr_incb_ranges, EXR_INCB_RANGE_COUNT, cp);
  int ep = property(exr_ep_ranges, EXR_EP_RANGE_COUNT, cp);
  int raw = property(exr_lb_ranges, EXR_LB_RANGE_COUNT, cp), lb = line_class(raw, cp);
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
  if (raw == exr_lb_cm || raw == exr_lb_zwj)
    lb = !s->started || hard(s->previous_raw_lb) || s->previous_lb == exr_lb_sp ||
                 s->previous_lb == exr_lb_zw ? exr_lb_al : s->previous_lb;
  flags = line_boundary(s, lb, raw);
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
  if (lb != exr_lb_sp)
    s->space_base = lb;
  s->previous_gcb = gcb;
  s->previous_lb = lb;
  s->previous_raw_lb = raw;
  s->started = 1;
  return flags;
}

int exr_text_hidden(uint32_t cp) {
  return (control(grapheme(cp)) && cp != '\t') || cp == 0x200c || cp == 0x200d ||
         cp == 0x034f || (cp >= 0x180b && cp <= 0x180d) || cp == 0x180f ||
         (cp >= 0xfe00 && cp <= 0xfe0f) || (cp >= 0xe0020 && cp <= 0xe007f) ||
         (cp >= 0xe0100 && cp <= 0xe01ef);
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
    map[start] = (unsigned char)exr_text_step(&state, cp);
  }
  map[size] = EXR_BOUNDARY_GRAPHEME | EXR_BOUNDARY_LINE | EXR_BOUNDARY_MANDATORY;
  *out = map;
  return exr_fail(e, EXR_OK, "");
}
