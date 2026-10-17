/* SPDX-License-Identifier: GPL-3.0-only */
#include "opentype_internal.h"
#include "text_internal.h"
#include "shaping_data.h"
#include "indic_data.h"
#include FT_TRUETYPE_TABLES_H
#include FT_MULTIPLE_MASTERS_H

#define OT_CONTEXT 256u
#define OT_DEPTH 16u
#define OT_TABLE_LIMIT ((size_t)64 * 1024 * 1024)
typedef struct { unsigned char *data; size_t size; } ot_table;
struct exr_ot_state { ot_table gsub, gpos, gdef; unsigned variations; };
typedef struct {
  exr_shaped_glyph out;
  uint32_t cp;
  unsigned form, ligature, component;
  unsigned syllable, category, position, indic_flags;
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
  ot_view feature_substitutions;
  FT_Fixed coordinates[64];
  unsigned axis_count;
  int positioning;
  int indic, indic_old, per_syllable, probing;
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
static ot_view required32(ot_view v, size_t at) {
  uint32_t offset = u32(v, at);
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
static unsigned indic_property(const exr_indic_range *ranges, size_t count, uint32_t cp) {
  size_t lo = 0, hi = count;
  while (lo < hi) {
    size_t mid = lo+(hi-lo)/2;
    if (cp < ranges[mid].first) hi = mid;
    else if (cp > ranges[mid].last) lo = mid+1;
    else return ranges[mid].value;
  }
  return 0;
}
#define INDIC_PROPERTY(name, cp) indic_property(exr_indic_##name, sizeof(exr_indic_##name)/sizeof(*exr_indic_##name), cp)
uint32_t exr_ot_script(uint32_t codepoint) {
  unsigned fast = property(exr_shape_script, sizeof(exr_shape_script)/sizeof(*exr_shape_script), codepoint);
  if (fast) return fast == 1 ? EXR_TAG('l','a','t','n') : EXR_TAG('a','r','a','b');
  return exr_indic_script_tags[INDIC_PROPERTY(script, codepoint)];
}
int exr_ot_transparent(uint32_t codepoint) { return joining(codepoint) == 5; }
static unsigned item_class(ot_work *w, size_t at) {
  unsigned cls = 0;
  if (w->gdef.p) cls = glyph_class(optional16(w->gdef, 4), w->items[at].out.glyph);
  if (!cls && !w->indic && joining(w->items[at].cp) == 5) cls = 3;
  return cls;
}
static int ignored_properties(ot_work *w, size_t at, unsigned flags, unsigned filtering) {
  unsigned cls;
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
static int ignored_hidden(ot_work *w,size_t at) {
  return (w->items[at].out.flags&EXR_GLYPH_HIDDEN) && w->items[at].cp!=0x200c &&
    !(w->indic && !w->positioning && w->items[at].cp==0x200d);
}
static int ignored(ot_work *w,size_t at,unsigned flags,unsigned filtering) {
  return ignored_hidden(w,at) || ignored_properties(w,at,flags,filtering);
}
static size_t next_item(ot_work *w, size_t at, int backwards, unsigned flags, unsigned filtering) {
  unsigned syllable = w->items[at].syllable;
  while (work(w, 1)) {
    if (backwards) { if (!at) return SIZE_MAX; at--; }
    else { if (++at >= w->count) return SIZE_MAX; }
    if (w->per_syllable && w->items[at].syllable != syllable) return SIZE_MAX;
    if (!ignored(w, at, flags, filtering)) return at;
  }
  return SIZE_MAX;
}
/* A default-ignorable can be an explicit component (emoji ZWJ/tag sequences).
   Lookup flags still win; only an unmatched ignorable may be skipped. */
static size_t next_match(ot_work *w,size_t at,int backwards,unsigned flags,unsigned filtering,ot_view set,int expected) {
  unsigned syllable=w->items[at].syllable;
  while(work(w,1)) {
    unsigned glyph; int matches;
    if(backwards) { if(!at) return SIZE_MAX; at--; } else if(++at>=w->count) return SIZE_MAX;
    if(w->per_syllable && w->items[at].syllable!=syllable) return SIZE_MAX;
    if(ignored_properties(w,at,flags,filtering)) continue;
    glyph=w->items[at].out.glyph;
    matches=set.p ? (expected<0 ? coverage(set,glyph)>=0 : glyph_class(set,glyph)==(unsigned)expected) : glyph==(unsigned)expected;
    if(matches && (!(w->items[at].out.flags&EXR_GLYPH_HIDDEN) || (!w->positioning && glyph))) return at;
    if(!ignored_hidden(w,at)) return SIZE_MAX;
  }
  return SIZE_MAX;
}
static int resize_items(ot_work *w, size_t count) {
  if (count > EXR_MAX_ITEMS || (w->probing && count > OT_CONTEXT)) { w->status = EXR_LIMIT; return 0; }
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
        cursor = next_match(w, cursor, 1, flags, filtering, required16(sub, field+(size_t)i*2), -1);
        if (cursor == SIZE_MAX) return 0;
      }
      field += (size_t)count*2;
    }
    input_count = u16(sub, field); field += 2;
    if (!chain) { actions = u16(sub, field); field += 2; }
    if (!input_count || input_count > OT_CONTEXT) { w->status = input_count ? EXR_LIMIT : EXR_FONT; return 0; }
    if (!bounds(sub, field, input_count, 2)) return 0;
    cursor = at;
    for (i = 0; i < input_count; i++) {
      if (i) cursor = next_match(w, cursor, 0, flags, filtering, required16(sub, field+(size_t)i*2), -1);
      if (cursor == SIZE_MAX || coverage(required16(sub, field+(size_t)i*2),
                                          w->items[cursor].out.glyph) < 0) return 0;
      positions[i] = cursor;
    }
    field += (size_t)input_count*2;
    if (chain) {
      unsigned count = u16(sub, field); field += 2;
      if (!bounds(sub, field, count, 2)) return 0;
      for (i = 0; i < count; i++) {
        cursor = next_match(w, cursor, 0, flags, filtering, required16(sub, field+(size_t)i*2), -1);
        if (cursor == SIZE_MAX) return 0;
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
          cursor = next_match(w, cursor, 1, flags, filtering,
                              format == 1 ? (ot_view){NULL,0,w} : back_classes, u16(rule, field+(size_t)i*2));
          if (cursor == SIZE_MAX) { matched = 0; break; }
        }
        field += (size_t)count*2;
      }
      input_count = u16(rule, field); field += 2;
      if (!chain) { actions = u16(rule, field); field += 2; }
      if (!input_count || input_count > OT_CONTEXT) { w->status = input_count ? EXR_LIMIT : EXR_FONT; return 0; }
      if (!bounds(rule, field, input_count-1, 2)) return 0;
      cursor = at; positions[0] = at;
      for (i = 1; matched && i < input_count; i++) {
        cursor = next_match(w, cursor, 0, flags, filtering,
                            format == 1 ? (ot_view){NULL,0,w} : input_classes, u16(rule, field+(size_t)(i-1)*2));
        if (cursor == SIZE_MAX) { matched = 0; break; }
        positions[i] = cursor;
      }
      field += (size_t)(input_count-1)*2;
      if (chain) {
        unsigned count = u16(rule, field); field += 2;
        if (!bounds(rule, field, count, 2)) return 0;
        for (i = 0; matched && i < count; i++) {
          cursor = next_match(w, cursor, 0, flags, filtering,
                              format == 1 ? (ot_view){NULL,0,w} : look_classes, u16(rule, field+(size_t)i*2));
          if (cursor == SIZE_MAX) { matched = 0; break; }
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
    w->items[at].indic_flags |= 1;
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
      w->items[at].indic_flags |= 1;
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
      w->items[at+i].indic_flags = (original.indic_flags | 1u | 4u) & ~2u;
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
        cursor = next_match(w, cursor, 0, flags, filtering, (ot_view){NULL,0,w}, u16(lig, 4+(size_t)(i-1)*2));
        if (cursor == SIZE_MAX) break;
        positions[i] = cursor;
      }
      if (i != components) continue;
      if (!valid_glyph(w, replacement)) return 0;
      if (!work(w, w->count-at)) return 0;
      end = w->items[cursor].out.end;
      w->items[at].out.glyph = replacement;
      for(i=1;i<components;i++) if(!(w->items[positions[i]].out.flags&EXR_GLYPH_HIDDEN)) w->items[at].out.flags&=~EXR_GLYPH_HIDDEN;
      w->items[at].indic_flags = (w->items[at].indic_flags | 1u | 2u) & ~4u;
      if (w->indic) for (i = 1; i < components; i++)
        if (w->items[positions[i]].position > w->items[at].position)
          w->items[at].position = w->items[positions[i]].position;
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
      cursor = next_match(w, cursor, 1, flags, filtering, required16(sub, field+(size_t)i*2), -1);
      if (cursor == SIZE_MAX) return 0;
    }
    field += (size_t)count*2; count = u16(sub, field); field += 2; cursor = at;
    if (!bounds(sub, field, count, 2)) return 0;
    for (i = 0; i < count; i++) {
      cursor = next_match(w, cursor, 0, flags, filtering, required16(sub, field+(size_t)i*2), -1);
      if (cursor == SIZE_MAX) return 0;
    }
    field += (size_t)count*2; count = u16(sub, field); field += 2;
    if (!bounds(sub, field, count, 2) || (unsigned)covered >= count) { w->status = EXR_FONT; return 0; }
    glyph = u16(sub, field+(size_t)covered*2);
    if (!valid_glyph(w, glyph)) return 0;
    w->items[at].out.glyph = glyph;
    w->items[at].indic_flags |= 1;
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
static double region_scalar(ot_work *w, ot_view regions, unsigned index) {
  unsigned axes = u16(regions, 0), count = u16(regions, 2), i;
  double scalar = 1;
  if (axes != w->axis_count || index >= count ||
      !bounds(regions, 4, count, (size_t)axes*6)) { w->status = EXR_FONT; return 0; }
  for (i = 0; i < axes; i++) {
    size_t at = 4+((size_t)index*axes+i)*6;
    int start = s16(regions, at), peak = s16(regions, at+2), end = s16(regions, at+4);
    double coordinate = (double)w->coordinates[i]/4; /* 16.16 to F2DOT14. */
    if (!work(w, 1)) return 0;
    if (start < -16384 || start > 16384 || peak < -16384 || peak > 16384 ||
        end < -16384 || end > 16384) { w->status = EXR_FONT; return 0; }
    /* The OpenType scalar algorithm ignores a malformed or cross-zero axis. */
    if (!peak || start > peak || peak > end || (start < 0 && end > 0)) continue;
    if (coordinate == peak) continue;
    if (coordinate <= start || coordinate >= end) scalar = 0;
    else if (coordinate < peak) scalar *= (coordinate-start)/(peak-start);
    else scalar *= (end-coordinate)/(end-peak);
  }
  return scalar;
}
static float variation_delta(ot_work *w, unsigned outer, unsigned inner) {
  ot_view store, data, regions;
  unsigned data_count, items, words, region_count, long_words, i;
  size_t width, row;
  double delta = 0;
  uint32_t store_offset;
  if (outer == 0xffff && inner == 0xffff) return 0;
  if (!w->gdef.p || u16(w->gdef, 2) < 3) { w->status = EXR_FONT; return 0; }
  store_offset = u32(w->gdef, 14);
  if (!store_offset) { w->status = EXR_FONT; return 0; }
  store = relative(w->gdef, store_offset);
  data_count = u16(store, 6);
  if (u16(store, 0) != 1 || outer >= data_count || !bounds(store, 8, data_count, 4)) {
    w->status = EXR_FONT; return 0;
  }
  regions = required32(store, 2);
  data = required32(store, 8+(size_t)outer*4);
  items = u16(data, 0); words = u16(data, 2); region_count = u16(data, 4);
  long_words = words >> 15; words &= 0x7fff;
  if (inner >= items || words > region_count || !bounds(data, 6, region_count, 2)) {
    w->status = EXR_FONT; return 0;
  }
  width = (size_t)words*(long_words ? 4u : 2u)+(size_t)(region_count-words)*(long_words ? 2u : 1u);
  row = 6+(size_t)region_count*2;
  if (!bounds(data, row, items, width)) return 0;
  row += (size_t)inner*width;
  for (i = 0; i < region_count && w->status == EXR_OK; i++) {
    unsigned bytes = i < words ? (long_words ? 4u : 2u) : (long_words ? 2u : 1u);
    double value, scalar;
    if (!work(w, 1)) return 0;
    if (bytes == 4) {
      uint32_t raw = u32(data, row);
      value = raw < UINT32_C(0x80000000) ? (double)raw : (double)raw-4294967296.0;
    } else if (bytes == 2) value = s16(data, row);
    else value = (int)(int8_t)data.p[row];
    scalar = region_scalar(w, regions, u16(data, 6+(size_t)i*2));
    delta += value*scalar; row += bytes;
  }
  return (float)(delta*w->scale);
}
static float device(ot_view sub, unsigned offset, unsigned ppem) {
  ot_view v;
  unsigned first, last, format, bits, count, word, shift, raw;
  if (!offset) return 0;
  v = relative(sub, offset);
  first = u16(v, 0); last = u16(v, 2); format = u16(v, 4);
  if (format == 0x8000) return variation_delta(v.work, first, last);
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
    unsigned ppem = w->face->bitmap_only ? (unsigned)fmaxf(1,roundf(w->options->font_size)) : (i & 1 ? w->face->face->size->metrics.y_ppem : w->face->face->size->metrics.x_ppem);
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
    if(!w->face->bitmap_only) {
      if (FT_Load_Glyph(w->face->face, glyph, FT_LOAD_DEFAULT)) { w->status = EXR_FONT; return 0; }
      if (w->face->face->glyph->format == FT_GLYPH_FORMAT_OUTLINE &&
        w->face->face->glyph->outline.n_points > 0 &&
        point < (unsigned)w->face->face->glyph->outline.n_points) {
        *x = (float)w->face->face->glyph->outline.points[point].x/64;
        *y = (float)w->face->face->glyph->outline.points[point].y/64;
      }
    }
  } else if (format == 3) {
    *x += device(v, u16(v, 6), w->face->bitmap_only ? (unsigned)fmaxf(1,roundf(w->options->font_size)) : w->face->face->size->metrics.x_ppem);
    *y += device(v, u16(v, 8), w->face->bitmap_only ? (unsigned)fmaxf(1,roundf(w->options->font_size)) : w->face->face->size->metrics.y_ppem);
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
    ot_view values_origin = sub;
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
      values_origin = set;
      record = 4+(size_t)lo*pair_size;
    } else if (format == 2) {
      unsigned a = glyph_class(required16(sub, 8), glyph);
      unsigned b = glyph_class(required16(sub, 10), w->items[other].out.glyph);
      unsigned ac = u16(sub, 12), bc = u16(sub, 14), width = value_size(vf1)+value_size(vf2);
      if (a >= ac || b >= bc || !bounds(sub, 16, (size_t)ac*bc, width)) { w->status = EXR_FONT; return 0; }
      record = 16+((size_t)a*bc+b)*width;
    } else { w->status = EXR_FONT; return 0; }
    record = value_record(w, values_origin, record, vf1, first);
    value_record(w, values_origin, record, vf2, second);
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
      ((w->items[at].out.flags & EXR_GLYPH_HIDDEN) && (w->positioning || !w->items[at].out.glyph))) return 0;
  table = required16(w->lookups, 2+(size_t)index*2);
  w->next_scan = at+1;
  type = u16(table, 0); flags = u16(table, 2); subtables = u16(table, 4);
  if (!type || type > (w->positioning ? 9u : 8u) || (flags & 0xe0) ||
      !bounds(table, 6, subtables, 2)) { w->status = EXR_FONT; return 0; }
  if (flags & 16) filtering = u16(table, 6+(size_t)subtables*2);
  if(ignored_properties(w,at,flags,filtering)) return 0;
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
  int status,i;
  if (face->ot) return EXR_OK;
  face->ot = calloc(1, sizeof(*face->ot));
  if (!face->ot) return EXR_MEMORY;
  for(i=0;i<face->face->num_charmaps;i++) if(FT_Get_CMap_Format(face->face->charmaps[i])==14) { face->ot->variations=1; break; }
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
  return face->ot->gsub.data || face->ot->gpos.data || face->ot->variations;
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
  if (w->indic) {
    selected = tag_table(scripts, 0, EXR_TAG('d','e','v','2'));
    if (!selected.p) {
      selected = tag_table(scripts, 0, EXR_TAG('d','e','v','a'));
      if (!w->positioning) w->indic_old = selected.p != NULL;
    }
  } else selected = tag_table(scripts, 0, script);
  if (!selected.p) selected = tag_table(scripts, 0, EXR_TAG('D','F','L','T'));
  if (!selected.p) return empty;
  if (lang) {
    ot_view specific = tag_table(selected, 2, lang);
    if (specific.p) return specific;
  }
  return optional16(selected, 0);
}
static int variation_conditions(ot_work *w, ot_view conditions) {
  unsigned count = u16(conditions, 0), i;
  int matched = 1;
  if (!bounds(conditions, 2, count, 4)) return 0;
  for (i = 0; i < count && w->status == EXR_OK; i++) {
    ot_view condition = required32(conditions, 2+(size_t)i*4);
    unsigned axis;
    int minimum, maximum;
    if (!work(w, 1)) return 0;
    /* An unrecognized condition format makes the whole condition set false. */
    if (u16(condition, 0) != 1) { matched = 0; continue; }
    axis = u16(condition, 2); minimum = s16(condition, 4); maximum = s16(condition, 6);
    if (axis >= w->axis_count || minimum < -16384 || maximum > 16384 || minimum > maximum) {
      w->status = EXR_FONT; return 0;
    }
    if (w->coordinates[axis] < (FT_Fixed)minimum*4 || w->coordinates[axis] > (FT_Fixed)maximum*4)
      matched = 0;
  }
  return matched;
}
static void feature_variations(ot_work *w, ot_view table, ot_view features) {
  ot_view variations;
  uint32_t offset, count, i;
  w->feature_substitutions = (ot_view){NULL,0,w};
  if (u16(table, 2) < 1) return;
  offset = u32(table, 10);
  if (!offset || w->status != EXR_OK) return;
  variations = relative(table, offset); count = u32(variations, 4);
  if (u16(variations, 0) != 1 || u16(variations, 2) != 0 || !bounds(variations, 8, count, 8)) {
    w->status = EXR_FONT; return;
  }
  for (i = 0; i < count && w->status == EXR_OK; i++) {
    uint32_t conditions = u32(variations, 8+(size_t)i*8);
    ot_view substitutions;
    unsigned n, j, previous = 0;
    if (!work(w, 1)) return;
    if (conditions && !variation_conditions(w, relative(variations, conditions))) continue;
    /* The first matching record wins, even when it has no substitutions. */
    offset = u32(variations, 12+(size_t)i*8);
    if (!offset || w->status != EXR_OK) return;
    substitutions = relative(variations, offset); n = u16(substitutions, 4);
    if (u16(substitutions, 0) != 1 || u16(substitutions, 2) != 0 || !bounds(substitutions, 6, n, 6)) {
      w->status = EXR_FONT; return;
    }
    for (j = 0; j < n; j++) {
      unsigned index = u16(substitutions, 6+(size_t)j*6);
      if (!work(w, 1)) return;
      if (index >= u16(features, 0) || (j && index <= previous)) { w->status = EXR_FONT; return; }
      (void)required32(substitutions, 8+(size_t)j*6);
      previous = index;
    }
    w->feature_substitutions = substitutions;
    return;
  }
}
static ot_view varied_feature(ot_work *w, ot_view original, unsigned index) {
  ot_view substitutions = w->feature_substitutions;
  unsigned lo = 0, hi = substitutions.p ? u16(substitutions, 4) : 0;
  while (lo < hi && work(w, 1)) {
    unsigned mid = lo+(hi-lo)/2, candidate = u16(substitutions, 6+(size_t)mid*6);
    if (index < candidate) hi = mid;
    else if (index > candidate) lo = mid+1;
    else return required32(substitutions, 8+(size_t)mid*6);
  }
  return original;
}
static void feature_index(ot_work *w, ot_view features, unsigned index, unsigned mask, unsigned value) {
  unsigned count = u16(features, 0), n, i;
  ot_view feature;
  if (index >= count || !bounds(features, 2, count, 6)) { w->status = EXR_FONT; return; }
  feature = required16(features, 6+(size_t)index*6);
  feature = varied_feature(w, feature, index);
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

enum { IC_OTHER, IC_C, IC_V, IC_N, IC_H, IC_M, IC_SM, IC_VD, IC_ZWJ, IC_ZWNJ, IC_CIRCLE, IC_PLACE };
enum { IP_REPH, IP_PRE_M, IP_PRE_C, IP_BASE, IP_MAIN, IP_BELOW, IP_SUB, IP_BEFORE_POST, IP_POST, IP_AFTER_POST, IP_SMVD };
enum { IM_RPHF=16, IM_PREF=32, IM_BLWF=64, IM_ABVF=128, IM_HALF=256, IM_PSTF=512, IM_INIT=1024 };
enum { IF_SUBSTITUTED=1, IF_LIGATED=2, IF_MULTIPLIED=4 };
static unsigned indic_category(uint32_t cp) {
  if (cp == 0x25cc) return IC_CIRCLE;
  if (cp == 0xa0 || cp == 0xd7) return IC_PLACE;
  switch (INDIC_PROPERTY(isc, cp)) {
    case EXR_ISC_CONSONANT: case EXR_ISC_CONSONANT_WITH_STACKER: return IC_C;
    case EXR_ISC_VOWEL_INDEPENDENT: return IC_V;
    case EXR_ISC_NUKTA: return IC_N;
    case EXR_ISC_VIRAMA: return IC_H;
    case EXR_ISC_VOWEL_DEPENDENT: return IC_M;
    case EXR_ISC_BINDU: case EXR_ISC_VISARGA: return IC_SM;
    case EXR_ISC_CANTILLATION_MARK: case EXR_ISC_TONE_MARK: case EXR_ISC_SYLLABLE_MODIFIER: return IC_VD;
    case EXR_ISC_JOINER: return IC_ZWJ;
    case EXR_ISC_NON_JOINER: return IC_ZWNJ;
    case EXR_ISC_CONSONANT_PLACEHOLDER: return IC_PLACE;
    default: return IC_OTHER;
  }
}
static int indic_consonant(const ot_item *item) {
  return item->category == IC_C || item->category == IC_V || item->category == IC_CIRCLE || item->category == IC_PLACE;
}
static int indic_joiner(const ot_item *item) { return item->category == IC_ZWJ || item->category == IC_ZWNJ; }
static int indic_halant(const ot_item *item) { return item->category == IC_H && !(item->indic_flags & IF_LIGATED); }
static void indic_move(ot_work *w, size_t from, size_t to) {
  ot_item item;
  size_t length = from > to ? from-to : to-from;
  if (!length || !work(w, length)) return;
  item = w->items[from];
  if (from < to) memmove(w->items+from, w->items+from+1, length*sizeof(item));
  else memmove(w->items+to+1, w->items+to, length*sizeof(item));
  w->items[to] = item;
}
static void indic_setup(ot_work *w) {
  static const uint32_t nukta_bases[] = {0x915,0x916,0x917,0x91c,0x921,0x922,0x92b,0x92f};
  size_t i, start;
  unsigned serial = 0;
  /* The eight Devanagari composition exclusions must remain base+nukta.
     Their original byte range is retained by both replacement scalars. */
  for (i = 0; i < w->count && w->status == EXR_OK; i++) {
    uint32_t cp = w->items[i].cp;
    if (!work(w, 1)) return;
    if (cp >= 0x958 && cp <= 0x95f) {
      ot_item original = w->items[i];
      if (!work(w, w->count-i) || !resize_items(w, w->count+1)) return;
      memmove(w->items+i+2, w->items+i+1, (w->count-i-1)*sizeof(*w->items));
      w->items[i].cp = nukta_bases[cp-0x958];
      w->items[i].out.glyph = FT_Get_Char_Index(w->face->face, w->items[i].cp);
      w->items[i+1] = original; w->items[i+1].cp = 0x93c;
      w->items[i+1].out.glyph = FT_Get_Char_Index(w->face->face, 0x93c);
      w->count++; i++;
    }
  }
  /* Canonical combining order includes nukta before halant and Vedic accents.
     Stable insertion is linear for already ordered text; moves share the
     ordinary shaping budget, including malformed long combining runs. */
  for (i = 1; i < w->count && w->status == EXR_OK; i++) {
    unsigned current = INDIC_PROPERTY(ccc, w->items[i].cp);
    size_t target = i;
    if (!work(w, 1)) return;
    while (current && target) {
      unsigned previous = INDIC_PROPERTY(ccc, w->items[target-1].cp);
      if (!previous || previous <= current) break;
      if (!work(w, 1)) return;
      target--;
    }
    indic_move(w, i, target);
  }
  for (i = 0; i < w->count; i++) w->items[i].category = indic_category(w->items[i].cp);
  for (start = 0; start < w->count && w->status == EXR_OK;) {
    size_t end = start+1, j, source_start = w->items[start].out.start, source_end = w->items[start].out.end;
    unsigned first = w->items[start].category;
    int pending = first == IC_H, broken = first == IC_N || first == IC_H || first == IC_M || first == IC_SM || first == IC_VD;
    if (first != IC_OTHER && first != IC_ZWJ && first != IC_ZWNJ) {
      while (end < w->count && work(w, 1)) {
        unsigned category = w->items[end].category;
        if (indic_consonant(&w->items[end])) { if (!pending) break; pending = 0; }
        else if (category == IC_H) pending = 1;
        else if (category == IC_M || category == IC_SM || category == IC_VD) pending = 0;
        else if (category == IC_ZWNJ && pending) { end++; break; }
        else if (category != IC_N && category != IC_ZWJ && category != IC_ZWNJ) break;
        end++;
      }
    }
    if (broken) {
      unsigned circle = FT_Get_Char_Index(w->face->face, 0x25cc);
      if (circle) {
        ot_item item = w->items[start];
        if (!work(w, w->count-start) || !resize_items(w, w->count+1)) return;
        memmove(w->items+start+1, w->items+start, (w->count-start)*sizeof(*w->items));
        item.cp = 0x25cc; item.out.glyph = circle; item.category = IC_CIRCLE;
        item.out.flags &= ~(EXR_GLYPH_HIDDEN|EXR_GLYPH_MISSING);
        w->items[start] = item; w->count++; end++;
      }
    }
    for (j = start; j < end; j++) {
      if (w->items[j].out.start < source_start) source_start = w->items[j].out.start;
      if (w->items[j].out.end > source_end) source_end = w->items[j].out.end;
    }
    serial++;
    for (j = start; j < end; j++) {
      w->items[j].syllable = serial;
      w->items[j].out.start = source_start; w->items[j].out.end = source_end;
    }
    start = end;
  }
}
/* Probe the actual GSUB implementation on a private two-glyph buffer. No
   font mutation or second lookup parser is needed; work/cancellation charges
   remain on the original operation. Only a two-to-one substitution is a
   positional-form candidate, not an unrelated single-glyph substitution. */
static int indic_pair(ot_work *w, ot_view features, ot_view lang, uint32_t tag, unsigned first, unsigned second) {
  ot_item *saved_items = w->items, *probe;
  size_t saved_count = w->count, saved_capacity = w->capacity, saved_scan = w->next_scan;
  unsigned saved_ligature = w->next_ligature;
  int result, saved_probing = w->probing;
  if (!feature_value(w->options, tag, 1)) return 0;
  probe = calloc(2, sizeof(*probe));
  if (!probe) { w->status = EXR_MEMORY; return 0; }
  probe[0].out.glyph = first; probe[1].out.glyph = second;
  probe[0].syllable = probe[1].syllable = 1;
  probe[0].parent = probe[1].parent = SIZE_MAX;
  probe[0].out.end = probe[1].out.end = 1;
  w->items = probe; w->count = w->capacity = 2; w->probing = 1;
  feature_tag(w, features, lang, tag, 0, 1);
  result = w->status == EXR_OK && w->count == 1 && (w->items[0].indic_flags & IF_LIGATED);
  free(w->items); w->items = saved_items; w->count = saved_count; w->capacity = saved_capacity;
  w->next_scan = saved_scan; w->next_ligature = saved_ligature; w->probing = saved_probing;
  return result;
}
static int indic_form_pair(ot_work *w, ot_view features, ot_view lang, uint32_t tag, unsigned glyph, unsigned virama) {
  return indic_pair(w, features, lang, tag, virama, glyph) || indic_pair(w, features, lang, tag, glyph, virama);
}
static void indic_initial(ot_work *w, ot_view features, ot_view lang) {
  size_t start;
  unsigned virama = FT_Get_Char_Index(w->face->face, 0x94d);
  for (start = 0; start < w->count && w->status == EXR_OK;) {
    size_t end = start+1, i, base = SIZE_MAX, limit = start;
    int reph = 0, seen_below = 0;
    while (end < w->count && w->items[end].syllable == w->items[start].syllable) end++;
    if (!work(w, end-start)) return;
    if (end-start >= 3 && w->items[start].cp == 0x930 && w->items[start+1].category == IC_H &&
        !indic_joiner(&w->items[start+2]) &&
        indic_pair(w, features, lang, EXR_TAG('r','p','h','f'), w->items[start].out.glyph, w->items[start+1].out.glyph)) {
      reph = 1; limit += 2;
    }
    for (i = start; i < end && w->status == EXR_OK; i++) {
      ot_item *item = &w->items[i];
      item->position = IP_BASE; item->form &= 15;
      if (item->category == IC_SM || item->category == IC_VD) item->position = IP_SMVD;
      else if (item->category == IC_M) {
        unsigned position = INDIC_PROPERTY(ipc, item->cp);
        item->position = position == EXR_IPC_LEFT ? IP_PRE_M : position == EXR_IPC_BOTTOM ? IP_SUB : IP_AFTER_POST;
      } else if (item->category == IC_C && virama) {
        unsigned glyph = item->out.glyph;
        if (indic_form_pair(w, features, lang, EXR_TAG('b','l','w','f'), glyph, virama) ||
            indic_form_pair(w, features, lang, EXR_TAG('v','a','t','u'), glyph, virama)) item->position = IP_BELOW;
        else if (indic_form_pair(w, features, lang, EXR_TAG('p','s','t','f'), glyph, virama) ||
                 indic_form_pair(w, features, lang, EXR_TAG('p','r','e','f'), glyph, virama)) item->position = IP_POST;
      }
    }
    for (i = end; i > limit;) {
      ot_item *item = &w->items[--i];
      if (indic_consonant(item)) {
        base = i;
        if (item->position != IP_BELOW && (item->position != IP_POST || seen_below)) break;
        if (item->position == IP_BELOW) seen_below = 1;
      } else if (item->category == IC_ZWJ && i > start && w->items[i-1].category == IC_H) break;
    }
    if (base == SIZE_MAX) { reph = 0; base = start; }
    for (i = start; i < base; i++) if (w->items[i].position > IP_PRE_C) w->items[i].position = IP_PRE_C;
    w->items[base].position = IP_BASE;
    if (reph) w->items[start].position = w->items[start+1].position = IP_REPH;
    if (w->indic_old) {
      for (i = base+1; i < end; i++) if (w->items[i].category == IC_H) {
        size_t last = end;
        while (last > i+1 && !indic_consonant(&w->items[last-1])) last--;
        if (last > i+1) indic_move(w, i, last-1);
        break;
      }
    }
    /* Virama/nukta/joiners travel with their owner. A post-base consonant
       instead owns its preceding virama so H+Ra remains available to rkrf. */
    {
      unsigned previous = IP_BASE;
      size_t last = base;
      for (i = start; i < end; i++) {
        ot_item *item = &w->items[i];
        if (item->category == IC_N || item->category == IC_H || indic_joiner(item)) {
          item->position = previous == IP_PRE_M && item->category == IC_H ? IP_BASE : previous;
        } else if (item->position != IP_SMVD) previous = item->position;
      }
      for (i = base+1; i < end; i++) {
        if (indic_consonant(&w->items[i])) {
          size_t j;
          for (j = last+1; j < i; j++) if (w->items[j].position < IP_SMVD) w->items[j].position = w->items[i].position;
          last = i;
        } else if (w->items[i].category == IC_M) last = i;
      }
    }
    /* At most eleven position buckets; this stable counting sort is linear
       even for a deliberately long repeated-mark syllable. */
    {
      ot_item *sorted = malloc((end-start)*sizeof(*sorted));
      size_t counts[IP_SMVD+1] = {0}, positions[IP_SMVD+1], j, cursor = 0;
      if (!sorted) { w->status = EXR_MEMORY; return; }
      for (i = start; i < end; i++) counts[w->items[i].position]++;
      for (j = 0; j <= IP_SMVD; j++) { positions[j] = cursor; cursor += counts[j]; }
      for (i = start; i < end; i++) sorted[positions[w->items[i].position]++] = w->items[i];
      memcpy(w->items+start, sorted, (end-start)*sizeof(*sorted)); free(sorted);
    }
    base = end;
    for (i = start; i < end; i++) if (w->items[i].position == IP_BASE) { base = i; break; }
    for (i = start; i < end; i++) {
      ot_item *item = &w->items[i];
      if (item->position == IP_REPH) item->form |= IM_RPHF;
      if (i < base) item->form |= IM_HALF | (w->indic_old ? 0u : IM_BLWF);
      else if (i > base) item->form |= IM_BLWF | IM_ABVF | IM_PSTF;
    }
    for (i = base+1; i+1 < end && w->status == EXR_OK; i++)
      if (indic_pair(w, features, lang, EXR_TAG('p','r','e','f'), w->items[i].out.glyph, w->items[i+1].out.glyph)) {
        w->items[i].form |= IM_PREF; w->items[i+1].form |= IM_PREF; break;
      }
    if (w->indic_old) for (i = start; i+1 < base; i++)
      if (w->items[i].cp == 0x930 && w->items[i+1].category == IC_H &&
          (i+2 == base || w->items[i+2].category != IC_ZWJ))
        w->items[i].form |= IM_BLWF, w->items[i+1].form |= IM_BLWF;
    for (i = start; i < end; i++) if (w->items[i].category == IC_ZWNJ) {
      size_t j = i;
      while (j > start) { j--; w->items[j].form &= ~IM_HALF; if (indic_consonant(&w->items[j])) break; }
    }
    start = end;
  }
}
static size_t indic_base(ot_work *w, size_t start, size_t end) {
  size_t base;
  for (base = start; base < end; base++) if (w->items[base].position >= IP_BASE) return base;
  return end;
}
static void indic_final(ot_work *w) {
  size_t start;
  for (start = 0; start < w->count && w->status == EXR_OK;) {
    size_t end = start+1, base, i, target;
    while (end < w->count && w->items[end].syllable == w->items[start].syllable) end++;
    base = indic_base(w, start, end);
    /* Unsubstituted explicit viramas delimit the last half-form group. A ZWJ
       requests the half form and keeps the matra to the left of that group. */
    target = start;
    for (i = start; i < base; i++) if (indic_halant(&w->items[i]) && w->items[i].position != IP_PRE_M &&
        (i+1 >= end || w->items[i+1].category != IC_ZWJ)) target = i;
    for (i = target; i > start; i--) if (w->items[i-1].position == IP_PRE_M) {
      indic_move(w, i-1, target); target--;
    }
    base = indic_base(w, start, end);
    if (w->items[start].position == IP_REPH &&
        (w->items[start].indic_flags & (IF_LIGATED|IF_MULTIPLIED)) == IF_LIGATED) {
      target = SIZE_MAX;
      for (i = start+1; i < base; i++) if (indic_halant(&w->items[i])) {
        target = i; if (i+1 < base && indic_joiner(&w->items[i+1])) target++; break;
      }
      if (target == SIZE_MAX) {
        target = end-1;
        while (target > start && w->items[target].position == IP_SMVD) target--;
        if (indic_halant(&w->items[target])) {
          for (i = base+1; i < target; i++) if (w->items[i].category == IC_M) { target--; break; }
        }
      }
      indic_move(w, start, target);
    }
    base = indic_base(w, start, end);
    for (i = base < end ? base+1 : end; i < end; i++) if (w->items[i].form & IM_PREF) {
      if ((w->items[i].indic_flags & (IF_LIGATED|IF_MULTIPLIED)) == IF_LIGATED) {
        target = base;
        while (target > start && w->items[target-1].category != IC_M && !indic_halant(&w->items[target-1])) target--;
        if (target > start && indic_halant(&w->items[target-1]) && target < end && indic_joiner(&w->items[target])) target++;
        indic_move(w, i, target);
      }
      break;
    }
    if (w->items[start].position == IP_PRE_M &&
        (!start || w->items[start-1].category == IC_OTHER)) w->items[start].form |= IM_INIT;
    start = end;
  }
}
static void indic_stage(ot_work *w, ot_view features, ot_view lang, uint32_t tag, unsigned mask) {
  feature_tag(w, features, lang, tag, mask, feature_value(w->options, tag, 1));
}
static void indic_substitution(ot_work *w, ot_view features, ot_view lang) {
  static const struct { uint32_t tag; unsigned mask; } stages[] = {
    {EXR_TAG('n','u','k','t'),0}, {EXR_TAG('a','k','h','n'),0}, {EXR_TAG('r','p','h','f'),IM_RPHF},
    {EXR_TAG('r','k','r','f'),0}, {EXR_TAG('p','r','e','f'),IM_PREF}, {EXR_TAG('b','l','w','f'),IM_BLWF},
    {EXR_TAG('a','b','v','f'),IM_ABVF}, {EXR_TAG('h','a','l','f'),IM_HALF}, {EXR_TAG('p','s','t','f'),IM_PSTF},
    {EXR_TAG('v','a','t','u'),0}, {EXR_TAG('c','j','c','t'),0}};
  static const uint32_t late[] = {EXR_TAG('i','n','i','t'),EXR_TAG('p','r','e','s'),EXR_TAG('a','b','v','s'),
    EXR_TAG('b','l','w','s'),EXR_TAG('p','s','t','s'),EXR_TAG('h','a','l','n'),EXR_TAG('r','l','i','g'),
    EXR_TAG('c','a','l','t'),EXR_TAG('c','l','i','g')};
  size_t i;
  w->per_syllable = 1;
  indic_stage(w, features, lang, EXR_TAG('l','o','c','l'), 0);
  indic_stage(w, features, lang, EXR_TAG('c','c','m','p'), 0);
  indic_initial(w, features, lang);
  for (i = 0; i < sizeof(stages)/sizeof(*stages) && w->status == EXR_OK; i++)
    indic_stage(w, features, lang, stages[i].tag, stages[i].mask);
  indic_final(w);
  for (i = 0; i < sizeof(late)/sizeof(*late) && w->status == EXR_OK; i++)
    indic_stage(w, features, lang, late[i], i ? 0u : IM_INIT);
  if (feature_value(w->options, EXR_TAG('l','i','g','a'), 0)) indic_stage(w, features, lang, EXR_TAG('l','i','g','a'), 0);
  for (i = 0; i < w->options->feature_count && w->status == EXR_OK; i++) {
    size_t j;
    uint32_t tag = w->options->features[i].tag;
    if (tag == EXR_TAG('r','v','r','n') || tag == EXR_TAG('l','o','c','l') || tag == EXR_TAG('c','c','m','p') || tag == EXR_TAG('l','i','g','a')) continue;
    for (j = 0; j < sizeof(stages)/sizeof(*stages) && tag != stages[j].tag; j++) {}
    if (j < sizeof(stages)/sizeof(*stages)) continue;
    for (j = 0; j < sizeof(late)/sizeof(*late) && tag != late[j]; j++) {}
    if (j == sizeof(late)/sizeof(*late)) indic_stage(w, features, lang, tag, 0);
  }
  w->per_syllable = 0;
}
static void apply_table(ot_work *w, ot_table *source, uint32_t script, int positioning, int *has_kern) {
  static const uint32_t substitution_tags[] = {
    EXR_TAG('c','c','m','p'), EXR_TAG('l','o','c','l'), EXR_TAG('i','s','o','l'),
    EXR_TAG('f','i','n','a'), EXR_TAG('m','e','d','i'), EXR_TAG('i','n','i','t'),
    EXR_TAG('r','l','i','g'), EXR_TAG('r','c','l','t'), EXR_TAG('c','a','l','t'),
    EXR_TAG('l','i','g','a'), EXR_TAG('c','l','i','g')};
  static const uint32_t position_tags[] = {
    EXR_TAG('c','u','r','s'), EXR_TAG('k','e','r','n'), EXR_TAG('d','i','s','t'),
    EXR_TAG('a','b','v','m'), EXR_TAG('b','l','w','m'), EXR_TAG('m','a','r','k'), EXR_TAG('m','k','m','k'),
    EXR_TAG('v','k','r','n')};
  const uint32_t *tags = positioning ? position_tags : substitution_tags;
  size_t count = positioning ? sizeof(position_tags)/sizeof(*position_tags) :
                               sizeof(substitution_tags)/sizeof(*substitution_tags), i, j;
  ot_view table = {source->data, source->size,w}, features, lang;
  unsigned required;
  int required_early = 0;
  if (!source->data) return;
  w->table = table; w->positioning = positioning;
  lang = language(w, table, script, w->options->language);
  features = required16(table, 6);
  if (!lang.p || w->status != EXR_OK) return;
  feature_variations(w, table, features);
  if (w->status != EXR_OK) return;
  required = u16(lang, 2);
  if (!positioning) {
    if (required != 0xffff && required < u16(features, 0) &&
        u32(features, 2+(size_t)required*6) == EXR_TAG('r','v','r','n')) {
      feature_index(w, features, required, 0, 1); required_early = 1;
    } else feature_tag(w, features, lang, EXR_TAG('r','v','r','n'), 0,
                       feature_value(w->options, EXR_TAG('r','v','r','n'), 1));
  }
  if (required != 0xffff && !required_early) feature_index(w, features, required, 0, 1);
  if (!positioning && w->indic) { indic_substitution(w, features, lang); return; }
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
    if (!positioning && tag == EXR_TAG('r','v','r','n')) continue;
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
static exr_status normalized_coordinates(ot_work *w, FT_Library library) {
  FT_MM_Var *axes = NULL;
  FT_Error code;
  unsigned i;
  if (!FT_HAS_MULTIPLE_MASTERS(w->face->face)) return EXR_OK;
  code = FT_Get_MM_Var(w->face->face, &axes);
  if (code || !axes) return EXR_FONT;
  if (!axes->num_axis || axes->num_axis > 64) {
    FT_Done_MM_Var(library, axes); return EXR_LIMIT;
  }
  w->axis_count = axes->num_axis;
  FT_Done_MM_Var(library, axes);
  /* FreeType applies avar before returning blend coordinates. Read these once
     per shape; a named instance and an explicit instance share this path. */
  if (FT_Get_Var_Blend_Coordinates(w->face->face, w->axis_count, w->coordinates)) return EXR_FONT;
  for (i = 0; i < w->axis_count; i++)
    if (w->coordinates[i] < -65536 || w->coordinates[i] > 65536) return EXR_FONT;
  return EXR_OK;
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
  uint32_t cp, script,previous_scalar=0;
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
  if (!w.face->design_units)
    return exr_fail(error, EXR_FONT, "Font has no usable design-unit scale");
  w.scale = options->font_size/(float)w.face->design_units;
  w.status = exr_text_analyze(text, size, &boundaries, error);
  if (w.status != EXR_OK) goto done;
  w.status = exr_control_cancel(&options->control, error);
  if (w.status != EXR_OK) goto done;
  w.status = tables(w.face);
  if (w.status != EXR_OK) goto done;
  w.status = normalized_coordinates(&w, font->library);
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
    if(w.count && w.face->ot->variations && exr_text_variation_selector(cp) && !exr_text_variation_selector(previous_scalar) && w.items[w.count-1].cp==previous_scalar) {
      unsigned variant=FT_Face_GetCharVariantIndex(w.face->face,previous_scalar,cp);
      if(variant) {
        if(!valid_glyph(&w,variant)) goto done;
        w.items[w.count-1].out.glyph=variant; w.items[w.count-1].out.flags&=~EXR_GLYPH_MISSING;
        previous_scalar=cp; continue;
      }
    }
    previous_scalar=cp;
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
      script = exr_ot_script(cp);
    }
  }
  if (!script) script = EXR_TAG('D','F','L','T');
  w.indic = script == EXR_TAG('d','e','v','a') || script == EXR_TAG('d','e','v','2');
  if (w.indic) indic_setup(&w);
  if (w.status != EXR_OK) goto done;
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
    if (cls == 3 && !w.indic) w.items[i].out.advance_x = w.items[i].out.advance_y = 0;
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
