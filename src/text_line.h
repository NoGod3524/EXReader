/* SPDX-License-Identifier: GPL-3.0-only */
#ifndef EXR_TEXT_LINE_H
#define EXR_TEXT_LINE_H
#include "text_line_internal.h"
#include "unicode_data.h"
#include <stddef.h>

static int exr_unicode_property(const exr_unicode_range *ranges, size_t count, uint32_t cp) {
  size_t lo = 0, hi = count;
  while (lo < hi) {
    size_t mid = lo + (hi - lo) / 2;
    if (cp < ranges[mid].first) hi = mid;
    else if (cp > ranges[mid].last) lo = mid + 1;
    else return ranges[mid].value;
  }
  return 0;
}
static exr_lb_char exr_line_character(uint32_t cp) {
  exr_lb_char c;
  c.cp = cp;
  c.lb = exr_unicode_property(exr_lb_ranges, EXR_LB_RANGE_COUNT, cp);
  c.gc = (unsigned)exr_unicode_property(exr_gc_ranges, EXR_GC_RANGE_COUNT, cp);
  c.east = (unsigned)exr_unicode_property(exr_eaw_ranges, EXR_EAW_RANGE_COUNT, cp);
  c.ep = (unsigned)exr_unicode_property(exr_ep_ranges, EXR_EP_RANGE_COUNT, cp);
  if (c.lb == exr_lb_ai || c.lb == exr_lb_sg || c.lb == exr_lb_xx) c.lb = exr_lb_al;
  else if (c.lb == exr_lb_sa) c.lb = (c.gc & 1) ? exr_lb_cm : exr_lb_al;
  else if (c.lb == exr_lb_cj) c.lb = exr_lb_ns;
  return c;
}
static int exr_line_hard(int lb) {
  return lb == exr_lb_bk || lb == exr_lb_cr || lb == exr_lb_lf || lb == exr_lb_nl;
}
static int exr_line_base(int lb) {
  return !exr_line_hard(lb) && lb != exr_lb_sp && lb != exr_lb_zw;
}
static int exr_line_mark(int lb) { return lb == exr_lb_cm || lb == exr_lb_zwj; }
static exr_lb_char exr_line_orphan(void) {
  return (exr_lb_char){exr_lb_al, 0, 0, 0, 0x41}; /* LB10 */
}
static int exr_line_alpha(int lb) { return lb == exr_lb_al || lb == exr_lb_hl; }
static int exr_line_hangul(int lb) {
  return lb == exr_lb_jl || lb == exr_lb_jv || lb == exr_lb_jt || lb == exr_lb_h2 || lb == exr_lb_h3;
}
static int exr_line_aksara(exr_lb_char c) {
  return c.lb == exr_lb_ak || c.lb == exr_lb_as || c.cp == 0x25cc;
}
static int exr_line_quote_start(int lb) {
  return lb < 0 || exr_line_hard(lb) || lb == exr_lb_op || lb == exr_lb_qu ||
         lb == exr_lb_gl || lb == exr_lb_sp || lb == exr_lb_zw;
}
typedef struct {
  exr_text_next read;
  void *context;
  exr_lb_char current, values[2];
  size_t count;
} exr_line_ahead;
static exr_lb_char exr_line_following(exr_line_ahead *a, size_t index) {
  while (a->count <= index) {
    uint32_t cp;
    exr_lb_char c = {-1, 0, 0, 0, 0};
    while (a->read && a->read(a->context, &cp)) {
      c = exr_line_character(cp);
      if (exr_line_mark(c.lb)) {
        if (exr_line_base(a->current.lb)) continue; /* LB9 ignores attached marks. */
        c = exr_line_orphan();
      }
      break;
    }
    a->values[a->count++] = c;
    a->current = c;
  }
  return a->values[index];
}

/* Unicode 17 UAX #14 rev. 55, in rule order. GLUE additionally protects the
 * layout's emergency wrapping at structural/punctuation boundaries. Ordinary
 * word and numeric rules remain emergency-wrap candidates. */
static unsigned exr_line_boundary(const exr_line_state *s, exr_lb_char c, int raw,
                                  int ignored, exr_line_ahead *ahead) {
  exr_lb_char p = s->previous, b = s->space_base, a = s->before_previous, n;
  int left = p.lb, right = c.lb;
  if (!s->started) return 0; /* LB2 */
  if (s->raw_previous == exr_lb_cr && raw == exr_lb_lf) return EXR_BOUNDARY_GLUE;
  if (exr_line_hard(s->raw_previous)) return EXR_BOUNDARY_LINE | EXR_BOUNDARY_MANDATORY;
  if (exr_line_hard(raw)) return EXR_BOUNDARY_GLUE; /* LB4-6 */
  if (raw == exr_lb_sp || raw == exr_lb_zw) return EXR_BOUNDARY_GLUE; /* LB7 */
  if (b.lb == exr_lb_zw) return EXR_BOUNDARY_LINE; /* LB8 */
  if (s->raw_previous == exr_lb_zwj || ignored) return EXR_BOUNDARY_GLUE; /* LB8a/9 */
  if (left == exr_lb_wj || right == exr_lb_wj || left == exr_lb_gl)
    return EXR_BOUNDARY_GLUE; /* LB11/12 */
  if (right == exr_lb_gl && left != exr_lb_sp && left != exr_lb_ba &&
      left != exr_lb_hy && left != exr_lb_hh) return EXR_BOUNDARY_GLUE; /* LB12a */
  if (right == exr_lb_cl || right == exr_lb_cp || right == exr_lb_ex || right == exr_lb_sy)
    return EXR_BOUNDARY_GLUE; /* LB13 */
  if (b.lb == exr_lb_op || s->initial_quote) return EXR_BOUNDARY_GLUE; /* LB14/15a */
  if (right == exr_lb_qu && (c.gc & 4)) {
    n = exr_line_following(ahead, 0);
    if (n.lb < 0 || exr_line_hard(n.lb) || n.lb == exr_lb_sp || n.lb == exr_lb_gl ||
        n.lb == exr_lb_qu || n.lb == exr_lb_zw || n.lb == exr_lb_wj ||
        n.lb == exr_lb_cl || n.lb == exr_lb_cp || n.lb == exr_lb_ex ||
        n.lb == exr_lb_is || n.lb == exr_lb_sy) return EXR_BOUNDARY_GLUE; /* LB15b */
  }
  if (left == exr_lb_sp && right == exr_lb_is &&
      exr_line_following(ahead, 0).lb == exr_lb_nu) return EXR_BOUNDARY_LINE; /* LB15c */
  if (right == exr_lb_is) return EXR_BOUNDARY_GLUE; /* LB15d */
  if ((b.lb == exr_lb_cl || b.lb == exr_lb_cp) && right == exr_lb_ns)
    return EXR_BOUNDARY_GLUE; /* LB16 */
  if (b.lb == exr_lb_b2 && right == exr_lb_b2) return EXR_BOUNDARY_GLUE; /* LB17 */
  if (left == exr_lb_sp) return EXR_BOUNDARY_LINE; /* LB18 */
  if ((right == exr_lb_qu && !(c.gc & 2)) || (left == exr_lb_qu && !(p.gc & 4)))
    return EXR_BOUNDARY_GLUE; /* LB19 */
  if (right == exr_lb_qu && (!p.east || !(n = exr_line_following(ahead, 0)).east || n.lb < 0))
    return EXR_BOUNDARY_GLUE; /* LB19a */
  if (left == exr_lb_qu && (!c.east || !a.east || a.lb < 0)) return EXR_BOUNDARY_GLUE;
  if (left == exr_lb_cb || right == exr_lb_cb) return EXR_BOUNDARY_LINE; /* LB20 */
  if ((left == exr_lb_hy || left == exr_lb_hh) && exr_line_alpha(right) &&
      (a.lb < 0 || exr_line_hard(a.lb) || a.lb == exr_lb_sp || a.lb == exr_lb_zw ||
       a.lb == exr_lb_cb || a.lb == exr_lb_gl)) return 0; /* LB20a */
  if (right == exr_lb_ba || right == exr_lb_hh || right == exr_lb_hy ||
      right == exr_lb_ns || left == exr_lb_bb) return EXR_BOUNDARY_GLUE; /* LB21 */
  if (a.lb == exr_lb_hl && (left == exr_lb_hy || left == exr_lb_hh) && right != exr_lb_hl)
    return 0; /* LB21a */
  if (left == exr_lb_sy && right == exr_lb_hl) return 0; /* LB21b */
  if (right == exr_lb_in) return EXR_BOUNDARY_GLUE; /* LB22 */
  if ((exr_line_alpha(left) && right == exr_lb_nu) ||
      (left == exr_lb_nu && exr_line_alpha(right))) return 0; /* LB23 */
  if ((left == exr_lb_pr && (right == exr_lb_id || right == exr_lb_eb || right == exr_lb_em)) ||
      ((left == exr_lb_id || left == exr_lb_eb || left == exr_lb_em) && right == exr_lb_po))
    return 0; /* LB23a */
  if (((left == exr_lb_pr || left == exr_lb_po) && exr_line_alpha(right)) ||
      (exr_line_alpha(left) && (right == exr_lb_pr || right == exr_lb_po))) return 0; /* LB24 */
  if ((s->numeric || s->number_close) && (right == exr_lb_po || right == exr_lb_pr)) return 0;
  if ((left == exr_lb_po || left == exr_lb_pr) && right == exr_lb_op) {
    n = exr_line_following(ahead, 0);
    if (n.lb == exr_lb_nu || (n.lb == exr_lb_is && exr_line_following(ahead, 1).lb == exr_lb_nu))
      return 0;
  }
  if (right == exr_lb_nu && (left == exr_lb_po || left == exr_lb_pr || left == exr_lb_hy ||
      left == exr_lb_is || s->numeric)) return 0; /* LB25 */
  if ((left == exr_lb_jl && (right == exr_lb_jl || right == exr_lb_jv ||
                            right == exr_lb_h2 || right == exr_lb_h3)) ||
      ((left == exr_lb_jv || left == exr_lb_h2) && (right == exr_lb_jv || right == exr_lb_jt)) ||
      ((left == exr_lb_jt || left == exr_lb_h3) && right == exr_lb_jt)) return EXR_BOUNDARY_GLUE;
  if ((exr_line_hangul(left) && right == exr_lb_po) ||
      (left == exr_lb_pr && exr_line_hangul(right))) return 0; /* LB26/27 */
  if (exr_line_alpha(left) && exr_line_alpha(right)) return 0; /* LB28 */
  if ((left == exr_lb_ap && exr_line_aksara(c)) ||
      (exr_line_aksara(p) && (right == exr_lb_vf || right == exr_lb_vi)) ||
      (exr_line_aksara(a) && left == exr_lb_vi && (right == exr_lb_ak || c.cp == 0x25cc)) ||
      (exr_line_aksara(p) && exr_line_aksara(c) && exr_line_following(ahead, 0).lb == exr_lb_vf))
    return EXR_BOUNDARY_GLUE; /* LB28a */
  if (left == exr_lb_is && exr_line_alpha(right)) return 0; /* LB29 */
  if (((exr_line_alpha(left) || left == exr_lb_nu) && right == exr_lb_op && !c.east) ||
      (left == exr_lb_cp && !p.east && (exr_line_alpha(right) || right == exr_lb_nu))) return 0;
  if (left == exr_lb_ri && right == exr_lb_ri && s->ri_odd) return EXR_BOUNDARY_GLUE; /* LB30a */
  if (right == exr_lb_em && (left == exr_lb_eb || (p.ep && (p.gc & 8))))
    return EXR_BOUNDARY_GLUE; /* LB30b */
  return EXR_BOUNDARY_LINE; /* LB31 */
}
static unsigned exr_line_step(exr_line_state *s, uint32_t cp, exr_text_next next, void *context) {
  exr_lb_char c = exr_line_character(cp);
  int raw = c.lb, ignored = exr_line_mark(raw) && s->started && exr_line_base(s->previous.lb);
  exr_line_ahead ahead;
  unsigned flags;
  if (exr_line_mark(raw)) c = ignored ? s->previous : exr_line_orphan();
  ahead = (exr_line_ahead){next, context, c, {{0}}, 0};
  flags = exr_line_boundary(s, c, raw, ignored, &ahead);
  if (!ignored) {
    int before = s->started ? s->previous.lb : -1;
    s->number_close = (c.lb == exr_lb_cl || c.lb == exr_lb_cp) && s->numeric;
    s->numeric = c.lb == exr_lb_nu || ((c.lb == exr_lb_sy || c.lb == exr_lb_is) && s->numeric);
    s->ri_odd = c.lb == exr_lb_ri ? !s->ri_odd : 0;
    if (c.lb != exr_lb_sp) {
      s->space_base = c;
      s->initial_quote = c.lb == exr_lb_qu && (c.gc & 2) && exr_line_quote_start(before);
    }
    s->before_previous = s->started ? s->previous : (exr_lb_char){-1, 0, 0, 0, 0};
    s->previous = c;
  }
  s->raw_previous = raw;
  s->started = 1;
  return flags;
}
#endif
