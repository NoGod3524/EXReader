/* SPDX-License-Identifier: GPL-3.0-only */
#include "opentype_internal.h"
#include "text_internal.h"
#include "shaping_data.h"
#include FT_TRUETYPE_TABLES_H

#define OT_CONTEXT 256u
#define OT_DEPTH 16u
#define OT_TABLE_LIMIT ((size_t)64 * 1024 * 1024)
typedef struct { unsigned char *data; size_t size; } ot_table;
struct exr_ot_state { ot_table gsub, gpos, gdef; };
typedef struct {
  exr_shaped_glyph out;
  uint32_t cp;
  unsigned form, ligature, component;
  size_t parent;
  size_t previous_visible, previous_base;
  float anchor_x, anchor_y;
  unsigned attach_axes, resolved;
} ot_item;
typedef struct ot_work ot_work;
typedef struct { const unsigned char *p; size_t size; ot_work *work; } ot_view;
struct ot_work {
  exr_face *face;
  ot_item *items;
  size_t count, capacity, work, work_limit;
  unsigned next_ligature;
  float scale;
  exr_status status;
  const exr_shape_options *options;
  ot_view gdef, table, lookups;
  int positioning;
  int rtl;
  int vertical;
  size_t next_scan;
  size_t control_next;
};

static int bounds(ot_view v, size_t offset, size_t count, size_t unit) {
  if (offset > v.size || (unit && count > (v.size - offset) / unit)) {
    if (v.work->status == EXR_OK) v.work->status = EXR_FONT;
    return 0;
  }
  return 1;
}
static int work(ot_work *w, size_t amount) {
  if (amount > w->work_limit - w->work) {
    if (w->status == EXR_OK) w->status = EXR_LIMIT;
    return 0;
  }
  w->work += amount;
  if (w->status == EXR_OK && w->work >= w->control_next) {
    w->status = exr_control_cancel(&w->options->control, NULL);
    w->control_next = w->work + 1024;
  }
  return w->status == EXR_OK;
}
static unsigned u16(ot_view v, size_t at) {
  return bounds(v, at, 1, 2) ? ((unsigned)v.p[at] << 8) | v.p[at + 1] : 0;
}
static int s16(ot_view v, size_t at) { return (int)(int16_t)u16(v, at); }
static uint32_t u32(ot_view v, size_t at) {
  return bounds(v, at, 1, 4) ? ((uint32_t)v.p[at] << 24) | ((uint32_t)v.p[at+1] << 16) |
                                ((uint32_t)v.p[at+2] << 8) | v.p[at+3] : 0;
}
static ot_view relative(ot_view v, size_t at) {
  ot_view out = {NULL, 0, v.work};
  if (bounds(v, at, 0, 1) && v.p) { out.p = v.p + at; out.size = v.size - at; }
  return out;
}
static ot_view optional16(ot_view v, size_t at) {
  unsigned offset = u16(v, at);
  ot_view empty = {NULL, 0, v.work};
  return offset ? relative(v, offset) : empty;
}
static ot_view required16(ot_view v, size_t at) {
  unsigned offset = u16(v, at);
  if (!offset && v.work->status == EXR_OK) v.work->status = EXR_FONT;
  return relative(v, offset);
}
static int coverage(ot_view v, unsigned glyph) {
  unsigned format = u16(v, 0), count = u16(v, 2), lo = 0, hi = count;
  if (!work(v.work, 1)) return -1;
  if (format != 1 && format != 2) { v.work->status = EXR_FONT; return -1; }
  if (!bounds(v, 4, count, format == 1 ? 2 : 6)) return -1;
  while (lo < hi) {
    unsigned mid = lo + (hi-lo)/2;
    size_t at = 4 + (size_t)mid * (format == 1 ? 2 : 6);
    unsigned first = u16(v, at), last = format == 1 ? first : u16(v, at+2);
    if (last < first) { v.work->status = EXR_FONT; return -1; }
    if (glyph < first) hi = mid;
    else if (glyph > last) lo = mid+1;
    else return format == 1 ? (int)mid : (int)(u16(v, at+4)+glyph-first);
  }
  return -1;
}
static unsigned glyph_class(ot_view v, unsigned glyph) {
  unsigned format, count, lo = 0, hi;
  if (!v.p) return 0;
  format = u16(v, 0);
  if (format == 1) {
    unsigned first = u16(v, 2);
    count = u16(v, 4);
    if (!bounds(v, 6, count, 2)) return 0;
    return glyph >= first && glyph-first < count ? u16(v, 6+(size_t)(glyph-first)*2) : 0;
  }
  if (format != 2) { v.work->status = EXR_FONT; return 0; }
  count = u16(v, 2); hi = count;
  if (!bounds(v, 4, count, 6)) return 0;
  while (lo < hi) {
    unsigned mid = lo+(hi-lo)/2;
    size_t at = 4+(size_t)mid*6;
    unsigned first = u16(v, at), last = u16(v, at+2);
    if (first > last) { v.work->status = EXR_FONT; return 0; }
    if (glyph < first) hi = mid;
    else if (glyph > last) lo = mid+1;
    else return u16(v, at+4);
  }
  return 0;
}
static unsigned property(const exr_shape_range *ranges, size_t count, uint32_t cp) {
  size_t lo = 0, hi = count;
  while (lo < hi) {
    size_t mid = lo+(hi-lo)/2;
    if (cp < ranges[mid].first) hi = mid;
    else if (cp > ranges[mid].last) lo = mid+1;
    else return ranges[mid].value;
  }
  return 0;
}
static unsigned joining(uint32_t cp) {
  return property(exr_shape_joining, sizeof(exr_shape_joining)/sizeof(*exr_shape_joining), cp);
}
int exr_ot_transparent(uint32_t codepoint) { return joining(codepoint) == 5; }
static unsigned item_class(ot_work *w, size_t at) {
  unsigned cls = 0;
  if (w->gdef.p) cls = glyph_class(optional16(w->gdef, 4), w->items[at].out.glyph);
  if (!cls && joining(w->items[at].cp) == 5) cls = 3;
  return cls;
}
static int ignored(ot_work *w, size_t at, unsigned flags, unsigned filtering) {
  unsigned cls;
  if (w->items[at].out.flags & EXR_GLYPH_HIDDEN)
    return w->items[at].cp != 0x200c; /* ZWNJ is a ligature/context barrier. */
  cls = item_class(w, at);
  if ((cls == 1 && (flags & 2)) || (cls == 2 && (flags & 4)) ||
      (cls == 3 && (flags & 8))) return 1;
  if (cls == 3 && (flags & 16)) {
    ot_view sets;
    unsigned count;
    if (!w->gdef.p || u16(w->gdef, 0) != 1 || u16(w->gdef, 2) < 2) {
      w->status = EXR_FONT; return 1;
    }
    sets = optional16(w->gdef, 12);
    count = u16(sets, 2);
    if (u16(sets, 0) != 1 || filtering >= count || !bounds(sets, 4, count, 4)) {
      w->status = EXR_FONT; return 1;
    }
    return coverage(relative(sets, u32(sets, 4+(size_t)filtering*4)), w->items[at].out.glyph) < 0;
  }
  if (cls == 3 && (flags & 0xff00)) {
    if (!w->gdef.p) { w->status = EXR_FONT; return 1; }
    return glyph_class(optional16(w->gdef, 10), w->items[at].out.glyph) != (flags >> 8);
  }
  return 0;
}
static size_t next_item(ot_work *w, size_t at, int backwards, unsigned flags, unsigned filtering) {
  while (work(w, 1)) {
    if (backwards) { if (!at) return SIZE_MAX; at--; }
    else { if (++at >= w->count) return SIZE_MAX; }
    if (!ignored(w, at, flags, filtering)) return at;
  }
  return SIZE_MAX;
}
static int resize_items(ot_work *w, size_t count) {
  if (count > EXR_MAX_ITEMS) { w->status = EXR_LIMIT; return 0; }
  if (!exr_grow((void **)&w->items, &w->capacity, count, sizeof(*w->items))) {
    w->status = EXR_MEMORY; return 0;
  }
  return 1;
}
static int valid_glyph(ot_work *w, unsigned glyph) {
  if (glyph >= (unsigned long)w->face->face->num_glyphs) { w->status = EXR_FONT; return 0; }
  return 1;
}
static unsigned feature_value(const exr_shape_options *options, uint32_t tag, unsigned fallback) {
  size_t i;
  for (i = options->feature_count; i; i--)
    if (options->features[i-1].tag == tag) return options->features[i-1].value;
  return fallback;
}
static int lookup(ot_work *, unsigned, size_t, unsigned, unsigned, unsigned);

/* Context and chaining formats share the same nested lookup action records. */
static int context(ot_work *w, ot_view sub, unsigned type, size_t at,
                     unsigned flags, unsigned filtering, unsigned value, unsigned depth) {
  unsigned format = u16(sub, 0), input_count = 0, actions = 0, i, chain;
  size_t positions[OT_CONTEXT], action_at = 0, consumed_end;
  ot_view rule = sub;
  chain = type == (w->positioning ? 8u : 6u);
  if (format == 3) {
    size_t field = 2, cursor = at;
    if (chain) {
      unsigned count = u16(sub, field); field += 2;
      if (!bounds(sub, field, count, 2)) return 0;
      for (i = 0; i < count; i++) {
        cursor = next_item(w, cursor, 1, flags, filtering);
        if (cursor == SIZE_MAX || coverage(required16(sub, field+(size_t)i*2),
                                            w->items[cursor].out.glyph) < 0) return 0;
      }
      field += (size_t)count*2;
    }
    input_count = u16(sub, field); field += 2;
    if (!chain) { actions = u16(sub, field); field += 2; }
    if (!input_count || input_count > OT_CONTEXT) { w->status = input_count ? EXR_LIMIT : EXR_FONT; return 0; }
    if (!bounds(sub, field, input_count, 2)) return 0;
    cursor = at;
    for (i = 0; i < input_count; i++) {
      if (i) cursor = next_item(w, cursor, 0, flags, filtering);
      if (cursor == SIZE_MAX || coverage(required16(sub, field+(size_t)i*2),
                                          w->items[cursor].out.glyph) < 0) return 0;
      positions[i] = cursor;
    }
    field += (size_t)input_count*2;
    if (chain) {
      unsigned count = u16(sub, field); field += 2;
      if (!bounds(sub, field, count, 2)) return 0;
      for (i = 0; i < count; i++) {
        cursor = next_item(w, cursor, 0, flags, filtering);
        if (cursor == SIZE_MAX || coverage(required16(sub, field+(size_t)i*2),
                                            w->items[cursor].out.glyph) < 0) return 0;
      }
      field += (size_t)count*2;
      actions = u16(sub, field); field += 2;
    }
    action_at = field;
  } else if (format == 1 || format == 2) {
    int covered = coverage(required16(sub, 2), w->items[at].out.glyph);
    unsigned set_count, set_index, r, rule_count;
    size_t set_field;
    ot_view sets, back_classes = {NULL,0,w}, input_classes = {NULL,0,w}, look_classes = {NULL,0,w};
    if (covered < 0) return 0;
    if (format == 1) { set_field = 4; set_index = (unsigned)covered; }
    else if (!chain) {
      input_classes = required16(sub, 4);
      set_field = 6; set_index = glyph_class(input_classes, w->items[at].out.glyph);
    } else {
      back_classes = required16(sub, 4);
      input_classes = required16(sub, 6);
      look_classes = required16(sub, 8);
      set_field = 10; set_index = glyph_class(input_classes, w->items[at].out.glyph);
    }
    set_count = u16(sub, set_field); set_field += 2;
    if (!bounds(sub, set_field, set_count, 2)) return 0;
    if (set_index >= set_count || !u16(sub, set_field+(size_t)set_index*2)) return 0;
    sets = required16(sub, set_field+(size_t)set_index*2);
    rule_count = u16(sets, 0);
    if (!bounds(sets, 2, rule_count, 2)) return 0;
    for (r = 0; r < rule_count; r++) {
      size_t field = 0, cursor = at;
      int matched = 1;
      rule = required16(sets, 2+(size_t)r*2);
      if (!work(w, 1)) return 0;
      if (chain) {
        unsigned count = u16(rule, field); field += 2;
        if (!bounds(rule, field, count, 2)) return 0;
        for (i = 0; i < count; i++) {
          unsigned actual;
          cursor = next_item(w, cursor, 1, flags, filtering);
          if (cursor == SIZE_MAX) { matched = 0; break; }
          actual = format == 1 ? w->items[cursor].out.glyph : glyph_class(back_classes, w->items[cursor].out.glyph);
          if (actual != u16(rule, field+(size_t)i*2)) { matched = 0; break; }
        }
        field += (size_t)count*2;
      }
      input_count = u16(rule, field); field += 2;
      if (!chain) { actions = u16(rule, field); field += 2; }
      if (!input_count || input_count > OT_CONTEXT) { w->status = input_count ? EXR_LIMIT : EXR_FONT; return 0; }
      if (!bounds(rule, field, input_count-1, 2)) return 0;
      cursor = at; positions[0] = at;
      for (i = 1; matched && i < input_count; i++) {
        unsigned actual;
        cursor = next_item(w, cursor, 0, flags, filtering);
        if (cursor == SIZE_MAX) { matched = 0; break; }
        actual = format == 1 ? w->items[cursor].out.glyph : glyph_class(input_classes, w->items[cursor].out.glyph);
        if (actual != u16(rule, field+(size_t)(i-1)*2)) matched = 0;
        positions[i] = cursor;
      }
      field += (size_t)(input_count-1)*2;
      if (chain) {
        unsigned count = u16(rule, field); field += 2;
        if (!bounds(rule, field, count, 2)) return 0;
        for (i = 0; matched && i < count; i++) {
          unsigned actual;
          cursor = next_item(w, cursor, 0, flags, filtering);
          if (cursor == SIZE_MAX) { matched = 0; break; }
          actual = format == 1 ? w->items[cursor].out.glyph : glyph_class(look_classes, w->items[cursor].out.glyph);
          if (actual != u16(rule, field+(size_t)i*2)) matched = 0;
        }
        field += (size_t)count*2;
        actions = u16(rule, field); field += 2;
      }
      if (matched) { action_at = field; break; }
    }
    if (r == rule_count) return 0;
  } else { w->status = EXR_FONT; return 0; }
  if (!bounds(rule, action_at, actions, 4)) return 0;
  consumed_end = positions[input_count-1]+1;
  for (i = 0; i < actions && w->status == EXR_OK; i++) {
    unsigned index = u16(rule, action_at+(size_t)i*4), nested = u16(rule, action_at+(size_t)i*4+2);
    size_t old_count = w->count, position, j;
    if (index >= input_count) { w->status = EXR_FONT; return 0; }
    position = positions[index];
    if (position >= w->count) continue;
    lookup(w, nested, position, 0, value, depth+1);
    if (w->count >= old_count) consumed_end += w->count-old_count;
    else consumed_end = consumed_end > old_count-w->count ? consumed_end-(old_count-w->count) : at;
    for (j = index+1; j < input_count; j++) {
      if (w->count >= old_count) positions[j] += w->count-old_count;
      else if (positions[j] >= old_count-w->count) positions[j] -= old_count-w->count;
    }
  }
  w->next_scan = consumed_end > w->count ? w->count : consumed_end;
  return 1;
}

static int substitute(ot_work *w, ot_view sub, unsigned type, size_t at,
                        unsigned flags, unsigned filtering, unsigned value, unsigned depth) {
  unsigned format = u16(sub, 0), glyph = w->items[at].out.glyph, i;
  int covered;
  if (type == 5 || type == 6) return context(w, sub, type, at, flags, filtering, value, depth);
  if (type == 7) {
    unsigned inner = u16(sub, 2);
    if (format != 1 || !inner || inner > 8 || inner == 7 || depth >= OT_DEPTH) {
      w->status = EXR_FONT; return 0;
    }
    return substitute(w, relative(sub, u32(sub, 4)), inner, at, flags, filtering, value, depth+1);
  }
  covered = coverage(required16(sub, 2), glyph);
  if (covered < 0) return 0;
  if (type == 1) {
    unsigned replacement;
    if (format == 1) replacement = (glyph+(unsigned)s16(sub, 4)) & 0xffffu;
    else if (format == 2) {
      unsigned count = u16(sub, 4);
      if (!bounds(sub, 6, count, 2) || (unsigned)covered >= count) { w->status = EXR_FONT; return 0; }
      replacement = u16(sub, 6+(size_t)covered*2);
    } else { w->status = EXR_FONT; return 0; }
    if (!valid_glyph(w, replacement)) return 0;
    w->items[at].out.glyph = replacement;
    return 1;
  }
  if (type == 2 || type == 3) {
    unsigned count = u16(sub, 4), n;
    ot_view sequence;
    ot_item original = w->items[at];
    if (format != 1 || !bounds(sub, 6, count, 2) || (unsigned)covered >= count) {
      w->status = EXR_FONT; return 0;
    }
    sequence = required16(sub, 6+(size_t)covered*2);
    n = u16(sequence, 0);
    if (!bounds(sequence, 2, n, 2)) return 0;
    if (type == 3) {
      unsigned replacement;
      if (!value || value > n) return 0;
      replacement = u16(sequence, 2+(size_t)(value-1)*2);
      if (!valid_glyph(w, replacement)) return 0;
      w->items[at].out.glyph = replacement;
      return 1;
    }
    if (!work(w, n) || !work(w, w->count-at-1) || !resize_items(w, w->count-1+n)) return 0;
    memmove(w->items+at+n, w->items+at+1, (w->count-at-1)*sizeof(*w->items));
    w->count = w->count-1+n;
    w->next_scan = at+n;
    for (i = 0; i < n; i++) {
      unsigned replacement = u16(sequence, 2+(size_t)i*2);
      if (!valid_glyph(w, replacement)) return 0;
      w->items[at+i] = original;
      w->items[at+i].out.glyph = replacement;
    }
    return 1;
  }
  if (type == 4) {
    unsigned count = u16(sub, 4), r, ligatures;
    ot_view set;
    if (format != 1 || !bounds(sub, 6, count, 2) || (unsigned)covered >= count) {
      w->status = EXR_FONT; return 0;
    }
    set = required16(sub, 6+(size_t)covered*2);
    ligatures = u16(set, 0);
    if (!bounds(set, 2, ligatures, 2)) return 0;
    for (r = 0; r < ligatures; r++) {
      ot_view lig = required16(set, 2+(size_t)r*2);
      unsigned replacement = u16(lig, 0), components = u16(lig, 2), component = 0;
      size_t positions[OT_CONTEXT], cursor = at, end, write, j;
      if (!components || components > OT_CONTEXT) { w->status = components ? EXR_LIMIT : EXR_FONT; return 0; }
      if (!bounds(lig, 4, components-1, 2)) return 0;
      positions[0] = at;
      for (i = 1; i < components; i++) {
        cursor = next_item(w, cursor, 0, flags, filtering);
        if (cursor == SIZE_MAX || w->items[cursor].out.glyph != u16(lig, 4+(size_t)(i-1)*2)) break;
        positions[i] = cursor;
      }
      if (i != components) continue;
      if (!valid_glyph(w, replacement)) return 0;
      if (!work(w, w->count-at)) return 0;
      end = w->items[cursor].out.end;
      w->items[at].out.glyph = replacement;
      w->items[at].out.end = end;
      w->items[at].ligature = ++w->next_ligature;
      w->items[at].component = components;
      write = at+1;
      for (j = at+1; j <= cursor; j++) {
        if (component+1 < components && j == positions[component+1]) { component++; continue; }
        w->items[write] = w->items[j];
        w->items[write].ligature = w->items[at].ligature;
        w->items[write].component = component;
        w->items[write].out.start = w->items[at].out.start;
        w->items[write].out.end = end;
        write++;
      }
      memmove(w->items+write, w->items+cursor+1, (w->count-cursor-1)*sizeof(*w->items));
      w->count -= components-1;
      /* Marks following the final component share its grapheme, even though
         they were not between the components matched by this lookup. */
      for (j = write; j < w->count && w->items[j].out.start < end; j++) {
        w->items[j].out.start = w->items[at].out.start;
        w->items[j].out.end = end;
        w->items[j].ligature = w->items[at].ligature;
        w->items[j].component = components-1;
      }
      return 1;
    }
    return 0;
  }
  if (type == 8) {
    size_t field = 4, cursor = at;
    unsigned count = u16(sub, field); field += 2;
    if (format != 1 || !bounds(sub, field, count, 2)) { w->status = EXR_FONT; return 0; }
    for (i = 0; i < count; i++) {
      cursor = next_item(w, cursor, 1, flags, filtering);
      if (cursor == SIZE_MAX || coverage(required16(sub, field+(size_t)i*2), w->items[cursor].out.glyph) < 0) return 0;
    }
    field += (size_t)count*2; count = u16(sub, field); field += 2; cursor = at;
    if (!bounds(sub, field, count, 2)) return 0;
    for (i = 0; i < count; i++) {
      cursor = next_item(w, cursor, 0, flags, filtering);
      if (cursor == SIZE_MAX || coverage(required16(sub, field+(size_t)i*2), w->items[cursor].out.glyph) < 0) return 0;
    }
    field += (size_t)count*2; count = u16(sub, field); field += 2;
    if (!bounds(sub, field, count, 2) || (unsigned)covered >= count) { w->status = EXR_FONT; return 0; }
    glyph = u16(sub, field+(size_t)covered*2);
    if (!valid_glyph(w, glyph)) return 0;
    w->items[at].out.glyph = glyph;
    return 1;
  }
  w->status = EXR_FONT;
  return 0;
}

static unsigned value_size(unsigned format) {
  unsigned n = 0;
  while (format) { n += format & 1; format >>= 1; }
  return n*2;
}
static float device(ot_view sub, unsigned offset, unsigned ppem) {
  ot_view v;
  unsigned first, last, format, bits, count, word, shift, raw;
  if (!offset) return 0;
  v = relative(sub, offset);
  first = u16(v, 0); last = u16(v, 2); format = u16(v, 4);
  if (format == 0x8000) { v.work->status = EXR_FONT; return 0; }
  if (format < 1 || format > 3 || last < first) { v.work->status = EXR_FONT; return 0; }
  bits = 1u << format;
  count = ((last-first+1)*bits+15)/16;
  if (!bounds(v, 6, count, 2) || ppem < first || ppem > last) return 0;
  word = (ppem-first)*bits/16;
  shift = 16-bits-((ppem-first)*bits%16);
  raw = (u16(v, 6+(size_t)word*2) >> shift) & ((1u << bits)-1);
  return (float)(raw & (1u << (bits-1)) ? (int)raw-(int)(1u << bits) : (int)raw);
}
static size_t value_record(ot_work *w, ot_view sub, size_t at, unsigned format, float out[4]) {
  unsigned i;
  if (format & 0xff00) { w->status = EXR_FONT; return at; }
  if (!bounds(sub, at, 1, value_size(format))) return at;
  for (i = 0; i < 4; i++) if (format & (1u << i)) { out[i] += s16(sub, at)*w->scale; at += 2; }
  for (i = 0; i < 4; i++) if (format & (16u << i)) {
    unsigned ppem = i & 1 ? w->face->face->size->metrics.y_ppem : w->face->face->size->metrics.x_ppem;
    out[i] += device(sub, u16(sub, at), ppem); at += 2;
  }
  return at;
}
static void adjust(ot_item *item, const float values[4]) {
  item->out.offset_x += values[0]; item->out.offset_y += values[1];
  item->out.advance_x += values[2]; item->out.advance_y += values[3];
}
static int anchor(ot_work *w, ot_view origin, unsigned offset, unsigned glyph, float *x, float *y) {
  ot_view v;
  unsigned format;
  if (!offset) return 0;
  v = relative(origin, offset); format = u16(v, 0);
  *x = s16(v, 2)*w->scale; *y = s16(v, 4)*w->scale;
  if (format == 2) {
    unsigned point = u16(v, 6);
    if (FT_Load_Glyph(w->face->face, glyph, FT_LOAD_DEFAULT)) { w->status = EXR_FONT; return 0; }
    if (w->face->face->glyph->format == FT_GLYPH_FORMAT_OUTLINE &&
        w->face->face->glyph->outline.n_points > 0 &&
        point < (unsigned)w->face->face->glyph->outline.n_points) {
      *x = (float)w->face->face->glyph->outline.points[point].x/64;
      *y = (float)w->face->face->glyph->outline.points[point].y/64;
    }
  } else if (format == 3) {
    *x += device(v, u16(v, 6), w->face->face->size->metrics.x_ppem);
    *y += device(v, u16(v, 8), w->face->face->size->metrics.y_ppem);
  } else if (format != 1) { w->status = EXR_FONT; return 0; }
  return w->status == EXR_OK;
}
static void attach(ot_work *w, size_t child, size_t parent, float x, float y, unsigned axes) {
  ot_item *item = &w->items[child];
  item->parent = parent; item->anchor_x = x; item->anchor_y = y; item->attach_axes = axes;
  if (axes & 1) item->out.offset_x = 0;
  if (axes & 2) item->out.offset_y = 0;
}
static int position(ot_work *w, ot_view sub, unsigned type, size_t at,
                      unsigned flags, unsigned filtering, unsigned value, unsigned depth) {
  unsigned format = u16(sub, 0), glyph = w->items[at].out.glyph;
  int covered;
  if (type == 7 || type == 8) return context(w, sub, type, at, flags, filtering, value, depth);
  if (type == 9) {
    unsigned inner = u16(sub, 2);
    if (format != 1 || !inner || inner > 8 || depth >= OT_DEPTH) { w->status = EXR_FONT; return 0; }
    return position(w, relative(sub, u32(sub, 4)), inner, at, flags, filtering, value, depth+1);
  }
  covered = coverage(required16(sub, 2), glyph);
  if (covered < 0) return 0;
  if (type == 1) {
    unsigned vf = u16(sub, 4);
    size_t record = 6;
    float values[4] = {0};
    if (format == 2) {
      unsigned count = u16(sub, 6);
      if (!bounds(sub, 8, count, value_size(vf)) || (unsigned)covered >= count) { w->status = EXR_FONT; return 0; }
      record = 8+(size_t)covered*value_size(vf);
    } else if (format != 1) { w->status = EXR_FONT; return 0; }
    value_record(w, sub, record, vf, values); adjust(&w->items[at], values);
    return 1;
  }
  if (type == 2) {
    unsigned vf1 = u16(sub, 4), vf2 = u16(sub, 6);
    size_t other = next_item(w, at, 0, flags, filtering), record;
    float first[4] = {0}, second[4] = {0};
    if (other == SIZE_MAX) return 0;
    if (format == 1) {
      unsigned count = u16(sub, 8), pairs, lo = 0, hi, pair_size = 2+value_size(vf1)+value_size(vf2);
      ot_view set;
      if (!bounds(sub, 10, count, 2) || (unsigned)covered >= count) { w->status = EXR_FONT; return 0; }
      set = required16(sub, 10+(size_t)covered*2);
      pairs = u16(set, 0); hi = pairs;
      if (!bounds(set, 2, pairs, pair_size)) return 0;
      while (lo < hi) {
        unsigned mid = lo+(hi-lo)/2, candidate = u16(set, 2+(size_t)mid*pair_size);
        if (candidate < w->items[other].out.glyph) lo = mid+1; else hi = mid;
      }
      if (lo == pairs || u16(set, 2+(size_t)lo*pair_size) != w->items[other].out.glyph) return 0;
      record = (size_t)(set.p-sub.p)+4+(size_t)lo*pair_size;
    } else if (format == 2) {
      unsigned a = glyph_class(required16(sub, 8), glyph);
      unsigned b = glyph_class(required16(sub, 10), w->items[other].out.glyph);
      unsigned ac = u16(sub, 12), bc = u16(sub, 14), width = value_size(vf1)+value_size(vf2);
      if (a >= ac || b >= bc || !bounds(sub, 16, (size_t)ac*bc, width)) { w->status = EXR_FONT; return 0; }
      record = 16+((size_t)a*bc+b)*width;
    } else { w->status = EXR_FONT; return 0; }
    record = value_record(w, sub, record, vf1, first);
    value_record(w, sub, record, vf2, second);
    adjust(&w->items[at], first); adjust(&w->items[other], second);
    if (vf2) w->next_scan = other+1;
    return 1;
  }
  if (type == 3) {
    unsigned count = u16(sub, 4);
    size_t other = next_item(w, at, 0, flags, filtering);
    int other_index;
    float exit_x, exit_y, entry_x, entry_y;
    size_t left, right;
    if (format != 1 || !bounds(sub, 6, count, 4) || (unsigned)covered >= count) { w->status = EXR_FONT; return 0; }
    if (other == SIZE_MAX) return 0;
    other_index = coverage(required16(sub, 2), w->items[other].out.glyph);
    if (other_index < 0) return 0;
    if ((unsigned)other_index >= count) { w->status = EXR_FONT; return 0; }
    /* Cursive entry/exit anchors connect in visual left-to-right order. Keep
       the returned array logical and assign those adjustments to its owners. */
    left = w->rtl ? other : at; right = w->rtl ? at : other;
    if (!anchor(w, sub, u16(sub, 8+(size_t)(w->rtl ? other_index : covered)*4),
                 w->items[left].out.glyph, &exit_x, &exit_y) ||
        !anchor(w, sub, u16(sub, 6+(size_t)(w->rtl ? covered : other_index)*4),
                 w->items[right].out.glyph, &entry_x, &entry_y)) return 0;
    w->items[left].out.advance_x = exit_x+w->items[left].out.offset_x;
    w->items[right].out.advance_x -= entry_x+w->items[right].out.offset_x;
    w->items[right].out.offset_x = -entry_x;
    if (flags & 1) attach(w, left, right, 0, entry_y-exit_y, 2);
    else attach(w, right, left, 0, exit_y-entry_y, 2);
    return 1;
  }
  if (type >= 4 && type <= 6) {
    unsigned classes = u16(sub, 6), marks, mark_class, base_count, component = 0;
    size_t base = type == 6 ? w->items[at].previous_visible : w->items[at].previous_base, record;
    int base_index;
    ot_view mark_array = required16(sub, 8), base_array = required16(sub, 10), anchors;
    float mx, my, bx, by;
    if (format != 1 || !classes) { w->status = EXR_FONT; return 0; }
    if (base == SIZE_MAX) return 0;
    base_index = coverage(required16(sub, 4), w->items[base].out.glyph);
    if (base_index < 0) return 0;
    marks = u16(mark_array, 0);
    if (!bounds(mark_array, 2, marks, 4) || (unsigned)covered >= marks) { w->status = EXR_FONT; return 0; }
    mark_class = u16(mark_array, 2+(size_t)covered*4);
    if (mark_class >= classes) { w->status = EXR_FONT; return 0; }
    base_count = u16(base_array, 0);
    if ((unsigned)base_index >= base_count) { w->status = EXR_FONT; return 0; }
    if (type == 5) {
      unsigned components;
      if (!bounds(base_array, 2, base_count, 2)) return 0;
      anchors = required16(base_array, 2+(size_t)base_index*2);
      components = u16(anchors, 0);
      if (!components || !bounds(anchors, 2, (size_t)components*classes, 2)) { w->status = EXR_FONT; return 0; }
      component = components-1;
      if (w->items[at].ligature && w->items[at].ligature == w->items[base].ligature)
        component = w->items[at].component < components ? w->items[at].component : components-1;
      record = 2+((size_t)component*classes+mark_class)*2;
    } else {
      anchors = base_array;
      if (!bounds(anchors, 2, (size_t)base_count*classes, 2)) return 0;
      record = 2+((size_t)base_index*classes+mark_class)*2;
    }
    if (!anchor(w, mark_array, u16(mark_array, 4+(size_t)covered*4), glyph, &mx, &my) ||
        !anchor(w, anchors, u16(anchors, record), w->items[base].out.glyph, &bx, &by)) return 0;
    attach(w, at, base, bx-mx, by-my, 3);
    return 1;
  }
  w->status = EXR_FONT;
  return 0;
}

static int lookup(ot_work *w, unsigned index, size_t at, unsigned mask, unsigned value, unsigned depth) {
  unsigned count = u16(w->lookups, 0), type, flags, filtering = 0, subtables, i;
  ot_view table;
  if (!work(w, 1) || depth >= OT_DEPTH) { if (w->status == EXR_OK) w->status = EXR_LIMIT; return 0; }
  if (index >= count || !bounds(w->lookups, 2, count, 2)) { w->status = EXR_FONT; return 0; }
  if (at >= w->count || (mask && !(w->items[at].form & mask)) ||
      (w->items[at].out.flags & EXR_GLYPH_HIDDEN)) return 0;
  table = required16(w->lookups, 2+(size_t)index*2);
  w->next_scan = at+1;
  type = u16(table, 0); flags = u16(table, 2); subtables = u16(table, 4);
  if (!type || type > (w->positioning ? 9u : 8u) || (flags & 0xe0) ||
      !bounds(table, 6, subtables, 2)) { w->status = EXR_FONT; return 0; }
  if (flags & 16) filtering = u16(table, 6+(size_t)subtables*2);
  for (i = 0; i < subtables && w->status == EXR_OK; i++) {
    ot_view sub = required16(table, 6+(size_t)i*2);
    int applied = w->positioning ? position(w, sub, type, at, flags, filtering, value, depth)
                                : substitute(w, sub, type, at, flags, filtering, value, depth);
    if (applied) return 1;
  }
  return 0;
}

static int table_load(exr_face *face, FT_ULong tag, ot_table *table, size_t remaining) {
  FT_ULong length = 0;
  FT_Error error = FT_Load_Sfnt_Table(face->face, tag, 0, NULL, &length);
  if (error == FT_Err_Table_Missing || !FT_IS_SFNT(face->face)) return EXR_OK;
  if (error) return EXR_FONT;
  if (length > remaining) return EXR_LIMIT;
  if (!length) return EXR_OK;
  table->data = malloc((size_t)length);
  if (!table->data) return EXR_MEMORY;
  table->size = (size_t)length;
  if (FT_Load_Sfnt_Table(face->face, tag, 0, table->data, &length) || length != table->size)
    return EXR_FONT;
  return EXR_OK;
}
void exr_ot_free(exr_face *face) {
  if (!face || !face->ot) return;
  free(face->ot->gsub.data); free(face->ot->gpos.data); free(face->ot->gdef.data);
  free(face->ot); face->ot = NULL;
}
static exr_status tables(exr_face *face) {
  int status;
  if (face->ot) return EXR_OK;
  face->ot = calloc(1, sizeof(*face->ot));
  if (!face->ot) return EXR_MEMORY;
  status = table_load(face, EXR_TAG('G','S','U','B'), &face->ot->gsub, OT_TABLE_LIMIT);
  if (!status) status = table_load(face, EXR_TAG('G','P','O','S'), &face->ot->gpos,
                                   OT_TABLE_LIMIT-face->ot->gsub.size);
  if (!status) status = table_load(face, EXR_TAG('G','D','E','F'), &face->ot->gdef,
                                   OT_TABLE_LIMIT-face->ot->gsub.size-face->ot->gpos.size);
  if (status) exr_ot_free(face);
  return (exr_status)status;
}
int exr_ot_present(exr_face *face) {
  if (!face) return 0;
  /* Route invalid tables through shape() so callers receive the actual error. */
  if (tables(face) != EXR_OK) return 1;
  return face->ot->gsub.data || face->ot->gpos.data;
}
static ot_view tag_table(ot_view records, size_t field, uint32_t tag) {
  unsigned count = u16(records, field), i;
  ot_view empty = {NULL,0,records.work};
  field += 2;
  if (!bounds(records, field, count, 6)) return empty;
  for (i = 0; i < count && work(records.work, 1); i++)
    if (u32(records, field+(size_t)i*6) == tag)
      return required16(records, field+(size_t)i*6+4);
  return empty;
}
static ot_view language(ot_work *w, ot_view table, uint32_t script, uint32_t lang) {
  ot_view scripts, selected, empty = {NULL,0,w};
  if (u16(table, 0) != 1 || u16(table, 2) > 1) { w->status = EXR_FONT; return empty; }
  scripts = required16(table, 4);
  w->lookups = required16(table, 8);
  if (!u16(table, 4) || !u16(table, 6) || !u16(table, 8) || !bounds(w->lookups, 0, 1, 2)) {
    w->status = EXR_FONT; return empty;
  }
  if (!bounds(w->lookups, 2, u16(w->lookups, 0), 2)) return empty;
  selected = tag_table(scripts, 0, script);
  if (!selected.p) selected = tag_table(scripts, 0, EXR_TAG('D','F','L','T'));
  if (!selected.p) return empty;
  if (lang) {
    ot_view specific = tag_table(selected, 2, lang);
    if (specific.p) return specific;
  }
  return optional16(selected, 0);
}
static void feature_index(ot_work *w, ot_view features, unsigned index, unsigned mask, unsigned value) {
  unsigned count = u16(features, 0), n, i;
  ot_view feature;
  if (index >= count || !bounds(features, 2, count, 6)) { w->status = EXR_FONT; return; }
  feature = required16(features, 6+(size_t)index*6);
  n = u16(feature, 2);
  if (!bounds(feature, 4, n, 2)) return;
  for (i = 0; i < n && w->status == EXR_OK; i++) {
    unsigned lookup_index = u16(feature, 4+(size_t)i*2), lookup_count = u16(w->lookups, 0), type;
    ot_view table;
    size_t at;
    int reverse;
    if (lookup_index >= lookup_count) { w->status = EXR_FONT; return; }
    table = required16(w->lookups, 2+(size_t)lookup_index*2);
    type = u16(table, 0); reverse = !w->positioning && type == 8;
    if (!w->positioning && type == 7 && u16(table, 4)) {
      ot_view extension = required16(table, 6);
      reverse = u16(extension, 2) == 8;
    }
    if (reverse) {
      for (at = w->count; at && w->status == EXR_OK;) lookup(w, lookup_index, --at, mask, value, 0);
    } else {
      for (at = 0; at < w->count && w->status == EXR_OK;) {
        w->next_scan = at+1;
        lookup(w, lookup_index, at, mask, value, 0);
        at = w->next_scan;
      }
    }
  }
}
static int feature_tag(ot_work *w, ot_view features, ot_view lang, uint32_t tag,
                         unsigned mask, unsigned value) {
  unsigned count, i, required;
  int found = 0;
  if (!value || !lang.p) return 0;
  count = u16(lang, 4); required = u16(lang, 2);
  if (!bounds(lang, 6, count, 2) || !bounds(features, 2, u16(features, 0), 6)) return 0;
  for (i = 0; i < count && w->status == EXR_OK; i++) {
    unsigned index = u16(lang, 6+(size_t)i*2);
    if (index >= u16(features, 0)) { w->status = EXR_FONT; return found; }
    if (index != required && u32(features, 2+(size_t)index*6) == tag) {
      feature_index(w, features, index, mask, value); found = 1;
    }
  }
  return found;
}
static void apply_table(ot_work *w, ot_table *source, uint32_t script, int positioning, int *has_kern) {
  static const uint32_t substitution_tags[] = {
    EXR_TAG('c','c','m','p'), EXR_TAG('l','o','c','l'), EXR_TAG('i','s','o','l'),
    EXR_TAG('f','i','n','a'), EXR_TAG('m','e','d','i'), EXR_TAG('i','n','i','t'),
    EXR_TAG('r','l','i','g'), EXR_TAG('r','c','l','t'), EXR_TAG('c','a','l','t'),
    EXR_TAG('l','i','g','a'), EXR_TAG('c','l','i','g')};
  static const uint32_t position_tags[] = {
    EXR_TAG('c','u','r','s'), EXR_TAG('k','e','r','n'), EXR_TAG('m','a','r','k'), EXR_TAG('m','k','m','k'),
    EXR_TAG('v','k','r','n')};
  const uint32_t *tags = positioning ? position_tags : substitution_tags;
  size_t count = positioning ? sizeof(position_tags)/sizeof(*position_tags) :
                               sizeof(substitution_tags)/sizeof(*substitution_tags), i, j;
  ot_view table = {source->data, source->size,w}, features, lang;
  if (!source->data) return;
  w->table = table; w->positioning = positioning;
  lang = language(w, table, script, w->options->language);
  features = required16(table, 6);
  if (!lang.p || w->status != EXR_OK) return;
  if (u16(lang, 2) != 0xffff) feature_index(w, features, u16(lang, 2), 0, 1);
  for (i = 0; i < count && w->status == EXR_OK; i++) {
    unsigned mask = 0, enabled;
    if (!positioning && i >= 2 && i <= 5) {
      if (script != EXR_TAG('a','r','a','b')) continue;
      mask = i == 2 ? 1u : i == 3 ? 8u : i == 4 ? 4u : 2u;
    }
    enabled = feature_value(w->options, tags[i],
                            tags[i] == EXR_TAG('v','k','r','n') ? (unsigned)w->vertical :
                            tags[i] == EXR_TAG('k','e','r','n') ? (unsigned)!w->vertical : 1u);
    if (feature_tag(w, features, lang, tags[i], mask, enabled) && tags[i] == EXR_TAG('k','e','r','n'))
      *has_kern = 1;
  }
  if (!positioning && w->vertical && w->status == EXR_OK) {
    unsigned enabled = feature_value(w->options, EXR_TAG('v','r','t','2'), 1);
    if (!feature_tag(w, features, lang, EXR_TAG('v','r','t','2'), 0, enabled))
      feature_tag(w, features, lang, EXR_TAG('v','e','r','t'), 0,
                  feature_value(w->options, EXR_TAG('v','e','r','t'), 1));
  }
  for (i = 0; i < w->options->feature_count && w->status == EXR_OK; i++) {
    uint32_t tag = w->options->features[i].tag;
    if (w->vertical && (tag == EXR_TAG('v','r','t','2') || tag == EXR_TAG('v','e','r','t'))) continue;
    for (j = 0; j < count && tag != tags[j]; j++) {}
    if (j == count) feature_tag(w, features, lang, tag, 0, w->options->features[i].value);
  }
}
static void joining_forms(ot_work *w) {
  size_t i, next = 0;
  unsigned previous = joining(w->options->context_before);
  for (i = 0; i < w->count; i++) {
    unsigned current = joining(w->items[i].cp), following;
    int before, after;
    if (current == 5) continue;
    if (next <= i) {
      next = i+1;
      while (next < w->count && joining(w->items[next].cp) == 5) next++;
    }
    following = next < w->count ? joining(w->items[next].cp) : joining(w->options->context_after);
    before = (previous == 2 || previous == 3 || previous == 4) &&
             (current == 1 || current == 3 || current == 4);
    after = (current == 2 || current == 3 || current == 4) &&
            (following == 1 || following == 3 || following == 4);
    w->items[i].form = before ? (after ? 4u : 8u) : (after ? 2u : 1u);
    previous = current;
  }
}
static void resolve_attachment(ot_work *w, size_t at, unsigned depth, const float *pen_x, const float *pen_y) {
  ot_item *item = &w->items[at];
  if (item->resolved == 2 || item->parent == SIZE_MAX) return;
  if (item->resolved == 1 || depth >= OT_DEPTH || item->parent >= w->count) { w->status = EXR_FONT; return; }
  item->resolved = 1;
  resolve_attachment(w, item->parent, depth+1, pen_x, pen_y);
  if (item->attach_axes & 1)
    item->out.offset_x += w->items[item->parent].out.offset_x + item->anchor_x + pen_x[item->parent]-pen_x[at];
  if (item->attach_axes & 2)
    item->out.offset_y += w->items[item->parent].out.offset_y + item->anchor_y + pen_y[item->parent]-pen_y[at];
  item->resolved = 2;
}
exr_shape_options exr_shape_defaults(void) {
  exr_shape_options options = {0};
  options.font_size = 24;
  return options;
}
static exr_status shape(exr_font *font, size_t face_index, const char *text, size_t size,
                       const exr_shape_options *options, exr_shaped_glyph **out,
                       size_t *out_count, int vertical, exr_error *error) {
  exr_shape_options defaults = exr_shape_defaults();
  ot_work w = {0};
  unsigned char *boundaries = NULL;
  float *pens = NULL;
  size_t at = 0, cluster_start = 0, cluster_end = 0, i;
  size_t previous_visible = SIZE_MAX, previous_base = SIZE_MAX;
  uint32_t cp, script;
  int has_kern = 0;
  exr_shaped_glyph *result = NULL;
  if (out) *out = NULL;
  if (out_count) *out_count = 0;
  if (!options) options = &defaults;
  if (!out || !out_count || !font || face_index >= font->count || (!text && size) ||
      !isfinite(options->font_size) || options->font_size < 4 || options->font_size > 256 ||
      options->style_flags & ~(EXR_GLYPH_BOLD | EXR_GLYPH_ITALIC) ||
      options->direction < EXR_DIRECTION_AUTO || options->direction > EXR_DIRECTION_RTL ||
      (options->feature_count && !options->features) ||
      options->context_before > 0x10ffff || options->context_after > 0x10ffff ||
      (options->context_before >= 0xd800 && options->context_before <= 0xdfff) ||
      (options->context_after >= 0xd800 && options->context_after <= 0xdfff))
    return exr_fail(error, EXR_ARGUMENT, "Invalid shaping input or options");
  if (options->feature_count > 256)
    return exr_fail(error, EXR_LIMIT, "Shaping feature list exceeds 256 entries");
  for (i = 0; i < options->feature_count; i++)
    if (!options->features[i].tag) return exr_fail(error, EXR_ARGUMENT, "Invalid OpenType feature tag");
  if (size > EXR_MAX_TEXT) return exr_fail(error, EXR_LIMIT, "Shaping text exceeds 64 MiB");
  w.status = exr_control_poll(&options->control, EXR_STAGE_SHAPE, 0, size, error);
  if (w.status != EXR_OK) return w.status;
  if (!size) return exr_fail(error, EXR_OK, "");
  w.face = &font->faces[face_index]; w.options = options; w.vertical = vertical;
  w.work_limit = 64000000u;
  if (!w.face->face->units_per_EM)
    return exr_fail(error, EXR_FONT, "Font has no usable design-unit scale");
  w.scale = options->font_size/(float)w.face->face->units_per_EM;
  w.status = exr_text_analyze(text, size, &boundaries, error);
  if (w.status != EXR_OK) goto done;
  w.status = exr_control_cancel(&options->control, error);
  if (w.status != EXR_OK) goto done;
  w.status = tables(w.face);
  if (w.status != EXR_OK) goto done;
  w.gdef = (ot_view){w.face->ot->gdef.data,w.face->ot->gdef.size,&w};
  if (w.gdef.p && (u16(w.gdef, 0) != 1 || u16(w.gdef, 2) > 3)) { w.status = EXR_FONT; goto done; }
  script = options->script;
  while (at < size) {
    size_t start = at;
    ot_item *item;
    if (!(w.count & 1023)) {
      w.status = exr_control_poll(&options->control, EXR_STAGE_SHAPE, at, size, error);
      if (w.status != EXR_OK) goto done;
    }
    if (!exr_next(text, size, &at, &cp)) { w.status = EXR_ENCODING; goto done; }
    if (!resize_items(&w, w.count+1)) goto done;
    if (start >= cluster_end) {
      cluster_start = start; cluster_end = at;
      while (cluster_end < size && !(boundaries[cluster_end] & EXR_BOUNDARY_GRAPHEME)) cluster_end++;
    }
    item = &w.items[w.count++]; memset(item, 0, sizeof(*item));
    item->out.start = cluster_start; item->out.end = cluster_end;
    item->out.glyph = FT_Get_Char_Index(w.face->face, cp); item->cp = cp; item->parent = SIZE_MAX;
    item->out.flags = options->style_flags;
    if (vertical) item->out.flags |= EXR_GLYPH_VERTICAL;
    if (exr_text_hidden(cp)) item->out.flags |= EXR_GLYPH_HIDDEN;
    else if (!item->out.glyph) item->out.flags |= EXR_GLYPH_MISSING;
    if (!script) {
      unsigned sc = property(exr_shape_script, sizeof(exr_shape_script)/sizeof(*exr_shape_script), cp);
      if (sc) script = sc == 1 ? EXR_TAG('l','a','t','n') : EXR_TAG('a','r','a','b');
      else if (vertical && ((cp >= 0x3400 && cp <= 0x9fff) || (cp >= 0x20000 && cp <= 0x3ffff)))
        script = EXR_TAG('h','a','n','i');
      else if (vertical && cp >= 0x3040 && cp <= 0x30ff) script = EXR_TAG('k','a','n','a');
      else if (vertical && cp >= 0xac00 && cp <= 0xd7af) script = EXR_TAG('h','a','n','g');
    }
  }
  if (!script) script = EXR_TAG('D','F','L','T');
  w.rtl = options->direction == EXR_DIRECTION_RTL ||
          (options->direction == EXR_DIRECTION_AUTO &&
           (script == EXR_TAG('a','r','a','b') || script == EXR_TAG('h','e','b','r')));
  joining_forms(&w);
  apply_table(&w, &w.face->ot->gsub, script, 0, &has_kern);
  if (w.status != EXR_OK) goto done;
  if (exr_font_size(w.face, options->font_size)) { w.status = EXR_FONT; goto done; }
  for (i = 0; i < w.count; i++) {
    unsigned cls;
    if (!work(&w, 1)) goto done;
    w.items[i].out.flags &= ~EXR_GLYPH_MISSING;
    if (!w.items[i].out.glyph && !(w.items[i].out.flags & EXR_GLYPH_HIDDEN))
      w.items[i].out.flags |= EXR_GLYPH_MISSING;
    if (!(w.items[i].out.flags & EXR_GLYPH_HIDDEN)) {
      float advance;
      int failed = vertical ? exr_measure_vertical(w.face, w.items[i].out.glyph, options->style_flags, &advance) :
                              exr_measure(w.face, w.items[i].out.glyph, options->style_flags, &advance);
      if (failed) { w.status = EXR_FONT; goto done; }
      if (vertical) w.items[i].out.advance_y = -advance;
      else w.items[i].out.advance_x = advance;
    }
    cls = item_class(&w, i);
    if (cls == 3) w.items[i].out.advance_x = w.items[i].out.advance_y = 0;
    /* GPOS cannot change glyph classes. Cache predecessors once, so a long
       combining sequence does not rescan the same mark run for each glyph. */
    w.items[i].previous_visible = previous_visible;
    w.items[i].previous_base = previous_base;
    if (!(w.items[i].out.flags & EXR_GLYPH_HIDDEN)) {
      previous_visible = i;
      if (cls != 3) previous_base = i;
    }
  }
  apply_table(&w, &w.face->ot->gpos, script, 1, &has_kern);
  if (!has_kern && feature_value(options, EXR_TAG('k','e','r','n'), (unsigned)!vertical)) {
    size_t previous = SIZE_MAX;
    for (i = 0; i < w.count; i++) {
      if (w.items[i].out.flags & EXR_GLYPH_HIDDEN || item_class(&w, i) == 3) continue;
      if (previous != SIZE_MAX)
        w.items[previous].out.advance_x += exr_kern(w.face, w.items[previous].out.glyph, w.items[i].out.glyph);
      previous = i;
    }
  }
  if (w.status != EXR_OK) goto done;
  if (w.count) {
    pens = calloc(w.count*2, sizeof(*pens)); result = malloc(w.count*sizeof(*result));
    if (!pens || !result) { w.status = EXR_MEMORY; goto done; }
    for (i = 1; i < w.count; i++) {
      pens[i] = pens[i-1]+w.items[i-1].out.advance_x;
      pens[w.count+i] = pens[w.count+i-1]+w.items[i-1].out.advance_y;
    }
    for (i = 0; i < w.count; i++) {
      if (!work(&w, 1)) goto done;
      resolve_attachment(&w, i, 0, pens, pens+w.count);
      result[i] = w.items[i].out;
    }
  }
  if (w.status == EXR_OK)
    w.status = exr_control_poll(&options->control, EXR_STAGE_SHAPE, size, size, error);
  if (w.status == EXR_OK) { *out = result; *out_count = w.count; result = NULL; }
done:
  free(boundaries); free(pens); free(w.items); free(result);
  if (w.status == EXR_OK) return exr_fail(error, EXR_OK, "");
  return exr_fail(error, w.status, w.status == EXR_FONT ? "Invalid or unsupported OpenType data" :
                                  w.status == EXR_LIMIT ? "OpenType shaping work limit exceeded" :
                                  w.status == EXR_ENCODING ? "Shaping text is not UTF-8" :
                                  w.status == EXR_CANCELLED ? "Operation cancelled" : "Shaping allocation failed");
}

exr_status exr_shape(exr_font *font,size_t index,const char *text,size_t size,
                       const exr_shape_options *options,exr_shaped_glyph **out,size_t *count,exr_error *e) {
  return shape(font,index,text,size,options,out,count,0,e);
}
exr_status exr_shape_vertical(exr_font *font,size_t index,const char *text,size_t size,
                                const exr_shape_options *options,exr_shaped_glyph **out,size_t *count,exr_error *e) {
  return shape(font,index,text,size,options,out,count,1,e);
}
