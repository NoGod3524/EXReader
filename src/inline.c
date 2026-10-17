/* SPDX-License-Identifier: GPL-3.0-only */
#include "flow_internal.h"
#include "bidi_internal.h"
#include "opentype_internal.h"
#include "vertical_data.h"
#include "ruby_internal.h"

unsigned exr_vertical_flags(uint32_t cp, exr_text_orientation orientation) {
  size_t lo = 0, hi = EXR_VO_RANGE_COUNT;
  int value = exr_vo_r;
  if (orientation == EXR_ORIENTATION_UPRIGHT) return EXR_GLYPH_VERTICAL;
  if (orientation == EXR_ORIENTATION_SIDEWAYS) return EXR_GLYPH_VERTICAL | EXR_GLYPH_SIDEWAYS;
  while (lo < hi) {
    size_t mid = lo + (hi - lo) / 2;
    if (cp < exr_vo_ranges[mid].first) hi = mid;
    else if (cp > exr_vo_ranges[mid].last) lo = mid + 1;
    else { value = exr_vo_ranges[mid].value; break; }
  }
  return EXR_GLYPH_VERTICAL | ((value == exr_vo_r || value == exr_vo_tr) ? EXR_GLYPH_SIDEWAYS : 0) |
         (value == exr_vo_tr ? EXR_GLYPH_TRY_VERTICAL : 0);
}

void exr_inline_clear(exr_inline_bidi *b) {
  exr_bidi_free(b->analysis);
  free(b->offsets);
  memset(b, 0, sizeof(*b));
  b->first_node = SIZE_MAX;
}
/* Walk only the remaining visible inline portion of this block. */
static size_t following(flow *f, size_t node) {
  for (;;) {
    const exr_node *n = &f->doc->nodes[node];
    if (n->next_sibling != SIZE_MAX)
      return n->next_sibling;
    node = n->parent;
    if (node == SIZE_MAX || f->styles[node].display != EXR_CSS_INLINE)
      return SIZE_MAX;
  }
}
static size_t next_text(flow *f, size_t node) {
  while (node != SIZE_MAX) {
    const exr_node *n = &f->doc->nodes[node];
    if (f->styles[node].display == EXR_CSS_NONE || n->start == SIZE_MAX)
      node = following(f, node);
    else if (n->kind == EXR_NODE_TEXT || exr_ruby_node(f->doc,node))
      return node;
    else if (f->styles[node].display != EXR_CSS_INLINE ||
             n->kind == EXR_NODE_BREAK || n->kind == EXR_NODE_IMAGE)
      return SIZE_MAX;
    else if (n->first_child != SIZE_MAX)
      node = n->first_child;
    else
      node = following(f, node);
  }
  return SIZE_MAX;
}
exr_status exr_inline_prepare(flow *f, size_t first, exr_inline_bidi *b) {
  size_t node, bytes = 0, count = 0, at, index = 0;
  int complex = f->paragraph->direction == EXR_DIRECTION_RTL;
  exr_buffer text = {0};
  exr_status status;
  uint32_t cp;
  exr_inline_clear(b);
  b->first_node = first;
  for (node = first; node != SIZE_MAX; node = next_text(f, following(f, node))) {
    const exr_node *n = &f->doc->nodes[node];
    if (exr_ruby_node(f->doc,node)) { bytes += 3; count++; continue; }
    bytes += n->end - n->start;
    for (at = n->start; at < n->end;) {
      if (!exr_next(f->doc->text, n->end, &at, &cp))
        return exr_fail(f->error, EXR_ENCODING, "Invalid inline UTF-8");
      complex |= exr_bidi_complex(cp);
      if (++count > EXR_MAX_ITEMS)
        return exr_fail(f->error, EXR_LIMIT, "Inline scalar limit exceeded");
      if (!(count & 1023) && exr_control_cancel(&f->config->control, f->error) != EXR_OK)
        return EXR_CANCELLED;
    }
  }
  if (!complex)
    return EXR_OK;
  b->offsets = malloc(count * sizeof(*b->offsets));
  if (!b->offsets || !exr_grow((void **)&text.data, &text.capacity, bytes + 1, 1)) {
    exr_inline_clear(b);
    free(text.data);
    return exr_fail(f->error, EXR_MEMORY, "Inline bidi allocation failed");
  }
  for (node = first; node != SIZE_MAX; node = next_text(f, following(f, node))) {
    const exr_node *n = &f->doc->nodes[node];
    if (exr_ruby_node(f->doc,node)) {
      b->offsets[index++] = n->start;
      memcpy(text.data + text.size,"\xef\xbf\xbc",3); text.size += 3;
      continue;
    }
    for (at = n->start; at < n->end;) {
      b->offsets[index++] = at;
      exr_next(f->doc->text, n->end, &at, &cp);
    }
    memcpy(text.data + text.size, f->doc->text + n->start, n->end - n->start);
    text.size += n->end - n->start;
  }
  status = exr_bidi_analyze(text.data, text.size, f->paragraph->direction,
                             &b->analysis, f->error);
  free(text.data);
  if (status != EXR_OK)
    exr_inline_clear(b);
  else
    b->count = count;
  return status;
}
static size_t scalar_at(const exr_inline_bidi *b, size_t offset) {
  size_t lo = 0, hi = b->count;
  while (lo < hi) {
    size_t mid = lo + (hi - lo) / 2;
    if (b->offsets[mid] < offset)
      lo = mid + 1;
    else
      hi = mid;
  }
  return lo;
}
unsigned exr_inline_level(const exr_inline_bidi *b, size_t offset) {
  size_t index;
  if (!b || !b->analysis)
    return 0;
  index = scalar_at(b, offset);
  return index < b->count ? exr_bidi_scalars(b->analysis, NULL)[index].level : 0;
}
unsigned exr_inline_base(const exr_inline_bidi *b, size_t offset) {
  return b && b->analysis ? exr_bidi_base_level(b->analysis, scalar_at(b, offset)) : 0;
}
typedef struct { size_t start, count; unsigned level; } visual_cluster;
exr_status exr_inline_reorder(flow *f, exr_glyph *g, size_t count) {
  const exr_inline_bidi *b = f->bidi;
  visual_cluster *clusters;
  exr_glyph *copy;
  unsigned *levels, high = 0, low = UINT_MAX, level;
  size_t first, last, n = 0, i, j, k, destination = 0;
  if (!b || !b->analysis || !count)
    return EXR_OK;
  first = scalar_at(b, g[0].start);
  last = scalar_at(b, g[count - 1].end);
  if (last <= first)
    return EXR_OK;
  levels = malloc((last - first) * sizeof(*levels));
  clusters = malloc(count * sizeof(*clusters));
  copy = malloc(count * sizeof(*copy));
  if (!levels || !clusters || !copy) {
    free(levels); free(clusters); free(copy);
    return exr_fail(f->error, EXR_MEMORY, "Visual line allocation failed");
  }
  exr_bidi_line_levels(b->analysis, first, last - first, levels);
  for (i = 0; i < count; i = j) {
    size_t index = scalar_at(b, g[i].cluster_start);
    level = index >= first && index < last ? levels[index - first] : g[i].bidi_level;
    j = i + 1;
    while (j < count && g[j].cluster_start == g[i].cluster_start)
      j++;
    if (level == UINT_MAX) {
      for (k = i; k < j; k++)
        if (g[k].bidi_level != UINT_MAX) { level = g[k].bidi_level; break; }
    }
    clusters[n++] = (visual_cluster){i, j - i, level};
    if (level != UINT_MAX) {
      if (level > high) high = level;
      if ((level & 1) && level < low) low = level;
      for (k = i; k < j; k++) g[k].bidi_level = level;
    }
  }
  /* X9 controls have no visual position. Keep their source ranges at line end. */
  for (i = 0, j = 0; i < n; i++)
    if (clusters[i].level != UINT_MAX) clusters[j++] = clusters[i];
  n = j;
  if (low != UINT_MAX)
    for (level = high;; level--) {
      for (i = 0; i < n;) {
        if (clusters[i].level < level) { i++; continue; }
        j = i + 1;
        while (j < n && clusters[j].level >= level) j++;
        for (k = j; i < --k; i++) {
          visual_cluster swap = clusters[i]; clusters[i] = clusters[k]; clusters[k] = swap;
        }
        i = j;
      }
      if (level == low) break;
    }
  for (i = 0; i < n; i++) {
    memcpy(copy + destination, g + clusters[i].start, clusters[i].count * sizeof(*g));
    destination += clusters[i].count;
  }
  for (i = 0; i < count; i++)
    if (g[i].bidi_level == UINT_MAX) copy[destination++] = g[i];
  if (destination == count) memcpy(g, copy, count * sizeof(*g));
  free(levels); free(clusters); free(copy);
  return EXR_OK;
}
static int inline_grow(exr_layout *l, size_t count) {
  size_t capacity;
  exr_glyph *glyphs;
  if (l->glyph_limit && count > l->glyph_limit) return 0;
  if (!l->glyph_limit || count <= l->glyph_cap)
    return exr_grow((void **)&l->glyphs, &l->glyph_cap, count, sizeof(*l->glyphs));
  capacity = l->glyph_cap ? l->glyph_cap : 64;
  while (capacity < count && capacity <= l->glyph_limit / 2) capacity *= 2;
  if (capacity < count || capacity > l->glyph_limit) capacity = count;
  glyphs = realloc(l->glyphs, capacity * sizeof(*glyphs));
  if (!glyphs) return 0;
  l->glyphs = glyphs; l->glyph_cap = capacity;
  return 1;
}
static exr_status line_work(flow *f, size_t count);
exr_status exr_inline_shape(flow *f, size_t start, uint32_t before, uint32_t after) {
  exr_layout *l = f->layout;
  exr_layout result = {0};
  size_t i, end, j, k, *positions = NULL;
  exr_status status = EXR_OK;
  result.glyph_limit = l->glyph_limit ? l->glyph_limit - start : 0;
  for (i = start; i < l->glyph_count; i = end) {
    exr_glyph *g = &l->glyphs[i];
    exr_shaped_glyph *shaped = NULL;
    exr_shape_options options = exr_shape_defaults();
    exr_buffer text = {0};
    uint32_t tag = exr_ot_script(g->codepoint);
    unsigned orientation = g->flags & (EXR_GLYPH_VERTICAL | EXR_GLYPH_SIDEWAYS | EXR_GLYPH_TRY_VERTICAL);
    int vertical = (orientation & EXR_GLYPH_VERTICAL) &&
                   (!(orientation & EXR_GLYPH_SIDEWAYS) || (orientation & EXR_GLYPH_TRY_VERTICAL));
    size_t n = 0, finish = 0;
    end = i + 1;
    if (g->flags & EXR_GLYPH_RUBY_ITEM) {
      if (!inline_grow(&result,result.glyph_count+1)) { status=EXR_LIMIT; goto done; }
      result.glyphs[result.glyph_count++]=*g;
      continue;
    }
    while (end < l->glyph_count) {
      const exr_glyph *v = &l->glyphs[end];
      uint32_t next_tag = exr_ot_script(v->codepoint);
      int removed = (v->flags & EXR_GLYPH_HIDDEN) && v->bidi_level == UINT_MAX;
      /* X9 removes controls from visual ordering, not from shaping context. */
      if ((v->flags & EXR_GLYPH_RUBY_ITEM) || (!removed && (v->font_index != g->font_index || v->size != g->size ||
          (v->flags & (EXR_GLYPH_VERTICAL | EXR_GLYPH_SIDEWAYS | EXR_GLYPH_TRY_VERTICAL)) != orientation ||
          ((orientation & EXR_GLYPH_TRY_VERTICAL) && v->cluster_start != g->cluster_start) ||
          (((v->flags & (3|EXR_DECORATIONS)) != (g->flags & (3|EXR_DECORATIONS)) || v->color != g->color) &&
           v->cluster_start != g->cluster_start) ||
          v->bidi_level != g->bidi_level)) || (tag && next_tag && tag != next_tag) ||
          (v->boundaries & EXR_BOUNDARY_MANDATORY) ||
          (!vertical && (v->boundaries & EXR_BOUNDARY_LINE)) ||
          v->codepoint == '\t' || g->codepoint == '\t') break;
      if (!tag) tag = next_tag;
      end++;
    }
    if (!exr_ot_present(&f->font->faces[g->font_index]) || g->codepoint == '\t') {
      if (!inline_grow(&result, result.glyph_count + end - i)) { status = EXR_LIMIT; goto done; }
      memcpy(result.glyphs + result.glyph_count, g, (end - i) * sizeof(*g));
      for (j = result.glyph_count; j < result.glyph_count + end - i; j++)
        result.glyphs[j].flags &= ~EXR_GLYPH_TRY_VERTICAL;
      result.glyph_count += end - i;
      continue;
    }
    if (end - i > 8192) { status = EXR_LIMIT; goto done; }
    positions = malloc((end - i + 1) * sizeof(*positions));
    if (!positions) { status = EXR_MEMORY; goto done; }
    for (j = i; j < end; j++) {
      uint32_t cp = l->glyphs[j].codepoint;
      positions[j - i] = text.size;
      if (g->bidi_level != UINT_MAX && (g->bidi_level & 1)) cp = exr_bidi_mirror(cp);
      if (!exr_codepoint(&text, cp)) { free(text.data); status = EXR_MEMORY; goto done; }
    }
    positions[end - i] = text.size;
    options.font_size = g->size;
    options.style_flags = g->flags & 3;
    options.direction = g->bidi_level != UINT_MAX && (g->bidi_level & 1) ?
                          EXR_DIRECTION_RTL : EXR_DIRECTION_LTR;
    options.script = tag;
    options.control = f->config->control;
    j = i;
    while (j > start && exr_ot_transparent(l->glyphs[j - 1].codepoint)) j--;
    options.context_before = j > start ? l->glyphs[j - 1].codepoint : before;
    j = end;
    while (j < l->glyph_count && exr_ot_transparent(l->glyphs[j].codepoint)) j++;
    options.context_after = j < l->glyph_count ? l->glyphs[j].codepoint : after;
    status = vertical ? exr_shape_vertical(f->font, g->font_index, text.data, text.size, &options, &shaped, &n, f->error) :
                        exr_shape(f->font, g->font_index, text.data, text.size, &options, &shaped, &n, f->error);
    if (status == EXR_OK && (orientation & EXR_GLYPH_TRY_VERTICAL)) {
      exr_shaped_glyph *horizontal = NULL;
      size_t hn = 0;
      int alternate = 0;
      status = line_work(f, end - i);
      if (status == EXR_OK)
        status = exr_shape(f->font, g->font_index, text.data, text.size, &options, &horizontal, &hn, f->error);
      if (status == EXR_OK) {
        alternate = hn != n;
        for (j = 0; !alternate && j < n; j++) alternate = shaped[j].glyph != horizontal[j].glyph;
        if (alternate) { orientation &= ~EXR_GLYPH_SIDEWAYS; free(horizontal); }
        else { free(shaped); shaped = horizontal; n = hn; vertical = 0; }
      } else free(horizontal);
    }
    free(text.data);
    if (status != EXR_OK) { free(shaped); goto done; }
    if (n > EXR_MAX_ITEMS - result.glyph_count ||
        !inline_grow(&result, result.glyph_count + n)) {
      free(shaped); status = EXR_LIMIT; goto done;
    }
    for (j = 0, k = 0; j < n; j++) {
      exr_glyph v;
      while (k + 1 < end - i && positions[k + 1] <= shaped[j].start) k++;
      if (!j || shaped[j].start != shaped[j - 1].start || shaped[j].end != shaped[j - 1].end) {
        size_t low = k + 1, high = end - i;
        while (low < high) {
          size_t middle = low + (high - low) / 2;
          if (positions[middle] < shaped[j].end) low = middle + 1;
          else high = middle;
        }
        finish = low;
      }
      v = l->glyphs[i + k];
      v.start = l->glyphs[i + k].start;
      v.end = l->glyphs[i + finish - 1].end;
      if (v.cluster_start > v.start) v.cluster_start = v.start;
      v.cluster_end = l->glyphs[i + finish - 1].cluster_end;
      if (v.cluster_end < v.end) v.cluster_end = v.end;
      v.glyph = shaped[j].glyph;
      v.advance = vertical ? -shaped[j].advance_y : shaped[j].advance_x;
      v.offset_x = shaped[j].offset_x;
      v.offset_y = shaped[j].offset_y;
      v.flags = shaped[j].flags | EXR_GLYPH_SHAPED | (v.flags & EXR_DECORATIONS) |
                (orientation & (EXR_GLYPH_VERTICAL | EXR_GLYPH_SIDEWAYS));
      if (v.bidi_level == UINT_MAX) v.flags |= EXR_GLYPH_HIDDEN;
      if (result.glyph_count &&
          result.glyphs[result.glyph_count - 1].cluster_start == v.cluster_start)
        v.boundaries = 0;
      result.glyphs[result.glyph_count++] = v;
    }
    free(shaped); free(positions); positions = NULL;
  }
  if (result.glyph_count > EXR_MAX_ITEMS - start ||
      !inline_grow(l, start + result.glyph_count)) {
    status = EXR_LIMIT; goto done;
  }
  memcpy(l->glyphs + start, result.glyphs, result.glyph_count * sizeof(*l->glyphs));
  l->glyph_count = start + result.glyph_count;
done:
  free(positions); free(result.glyphs);
  return status == EXR_OK ? EXR_OK : exr_fail(f->error, status, "Inline shaping failed");
}

static void reset_line_scan(exr_line_buffer *b) {
  b->scan = b->line_end = 0;
  b->soft = b->emergency = SIZE_MAX;
  b->scan_width = 0;
  b->initialized = 1;
}
static exr_status line_work(flow *f, size_t count) {
  const size_t limit = 64 * 1024 * 1024;
  if (count > limit - f->assets->shape_work)
    return exr_fail(f->error, EXR_LIMIT, "Line shaping work limit exceeded");
  f->assets->shape_work += count;
  return EXR_OK;
}
static exr_status line_reserve(flow *f, exr_line_buffer *b, exr_layout *target, size_t count) {
  const size_t limit = 16 * 1024 * 1024 / sizeof(exr_glyph);
  size_t other = b->run.glyph_cap + b->raw.glyph_cap + b->line.glyph_cap - target->glyph_cap;
  if (other >= limit || count > limit - other)
    return exr_fail(f->error, EXR_LIMIT, "Line buffer exceeds 16 MiB");
  target->glyph_limit = limit - other;
  if (!inline_grow(target, count))
    return exr_fail(f->error, EXR_LIMIT, "Line buffer allocation limit exceeded");
  return EXR_OK;
}
static float line_kern(flow *f, const exr_glyph *left, const exr_glyph *right) {
  if (!left || ((left->flags | right->flags) & (EXR_GLYPH_HIDDEN | EXR_GLYPH_SHAPED)) ||
      left->font_index != right->font_index || left->size != right->size ||
      (left->flags & 3) != (right->flags & 3) ||
      ((right->flags & EXR_GLYPH_VERTICAL) && !(right->flags & EXR_GLYPH_SIDEWAYS))) return 0;
  return exr_kern(&f->font->faces[right->font_index], left->glyph, right->glyph);
}
static exr_status copy_glyphs(flow *f, exr_line_buffer *b, exr_layout *to,
                               const exr_glyph *from, size_t count) {
  exr_status status = line_reserve(f, b, to, count);
  if (status != EXR_OK) return status;
  if (count) memcpy(to->glyphs, from, count * sizeof(*from));
  to->glyph_count = count;
  return EXR_OK;
}
static exr_status shape_line_copy(flow *f, exr_line_buffer *b, exr_layout *to, const exr_glyph *from,
                                   size_t count, uint32_t before, uint32_t after, int hyphen) {
  flow child = *f;
  exr_status status = line_work(f, count);
  size_t soft = SIZE_MAX, i;
  if (status == EXR_OK) status = copy_glyphs(f, b, to, from, count);
  if (status != EXR_OK) return status;
  child.layout = to;
  if (hyphen && count && to->glyphs[count - 1].codepoint == 0xad) {
    exr_glyph *g = &to->glyphs[count - 1];
    size_t order[32], n = exr_font_order(f->font, f->styles[g->node].family,
                                          f->styles[g->node].flags,
                                          f->doc->nodes[g->node].chapter, order);
    soft = g->start;
    /* Prefer the Unicode hyphen throughout the allowed fallback sequence. */
    for (i = 0; i < n && !exr_font_has_glyph(f->font, order[i], 0x2010); i++) {}
    g->codepoint = i < n ? 0x2010 : '-';
    g->flags &= ~(EXR_GLYPH_HIDDEN | EXR_GLYPH_MISSING | EXR_GLYPH_SHAPED);
    g->bidi_level = exr_inline_base(f->bidi, g->start);
    for (i = count - 1; i; i--)
      if (!(to->glyphs[i - 1].flags & EXR_GLYPH_HIDDEN) &&
          to->glyphs[i - 1].bidi_level != UINT_MAX) {
        g->bidi_level = to->glyphs[i - 1].bidi_level;
        break;
      }
    status = exr_flow_cluster(&child, count - 1, count);
    if (status != EXR_OK) return status;
  }
  status = exr_inline_shape(&child, 0, before, after);
  if (soft != SIZE_MAX)
    for (i = 0; i < to->glyph_count; i++)
      if (to->glyphs[i].start == soft) to->glyphs[i].codepoint = 0xad;
  return status == EXR_OK ? line_work(f, to->glyph_count) : status;
}
static exr_status measure_line_cluster(flow *f, exr_line_buffer *b) {
  flow child = *f;
  exr_status status;
  if (b->cluster_start == b->run.glyph_count) return EXR_OK;
  child.layout = &b->run;
  status = exr_flow_cluster(&child, b->cluster_start, b->run.glyph_count);
  if (status == EXR_OK) b->cluster_start = b->run.glyph_count;
  return status;
}
static exr_status shape_line_segment(flow *f, exr_line_buffer *b, uint32_t after) {
  flow child = *f;
  exr_status status;
  size_t count = b->run.glyph_count - b->ready, i;
  uint32_t last = b->before;
  if (!count) return EXR_OK;
  status = line_reserve(f, b, &b->raw, b->raw.glyph_count + count);
  if (status != EXR_OK) return status;
  memcpy(b->raw.glyphs + b->raw.glyph_count, b->run.glyphs + b->ready,
          count * sizeof(*b->raw.glyphs));
  b->raw.glyph_count += count;
  for (i = b->run.glyph_count; i > b->ready; i--)
    if (!exr_ot_transparent(b->run.glyphs[i - 1].codepoint)) {
      last = b->run.glyphs[i - 1].codepoint;
      break;
    }
  status = line_work(f, count);
  if (status == EXR_OK) status = line_reserve(f, b, &b->run, b->run.glyph_count);
  if (status != EXR_OK) return status;
  child.layout = &b->run;
  status = exr_inline_shape(&child, b->ready, b->before, after);
  if (status == EXR_OK) status = line_work(f, b->run.glyph_count - b->ready);
  if (status == EXR_OK) {
    b->ready = b->cluster_start = b->run.glyph_count;
    b->before = last;
    b->after = after;
  }
  return status;
}
/* A provisional ligature is one protected cluster. Final fitting can retreat
   across its start, never through it or a GLUE boundary. */
static exr_status fit_line(flow *f, exr_line_buffer *b) {
  float indent = f->first_line ? f->paragraph->indent : 0;
  float available = fmaxf(1, f->width - indent);
  size_t tries = 0;
  for (;;) {
    size_t i, source_end = b->run.glyphs[b->line_end - 1].cluster_end;
    size_t low = 0, high = b->raw.glyph_count;
    float width = 0;
    exr_status status;
    while (low < high) {
      size_t middle = low + (high - low) / 2;
      if (b->raw.glyphs[middle].start < source_end) low = middle + 1;
      else high = middle;
    }
    b->raw_end = low;
    status = shape_line_copy(f, b, &b->line, b->raw.glyphs, low, 0, 0,
                             !b->final && !b->forced);
    if (status != EXR_OK) return status;
    for (i = 0; i < b->line.glyph_count; i++) {
      exr_glyph *g = &b->line.glyphs[i];
      if (exr_font_size(&f->font->faces[g->font_index], g->size))
        return exr_fail(f->error, EXR_FONT, "Cannot size final line font");
      width += g->advance + line_kern(f, i ? g - 1 : NULL, g);
    }
    if (width <= available + 0.001f) break;
    {
      size_t emergency = 0;
      i = b->line_end;
      while (--i) {
        unsigned boundaries = b->run.glyphs[i].boundaries;
        if ((boundaries & EXR_BOUNDARY_GRAPHEME) && !(boundaries & EXR_BOUNDARY_GLUE)) {
          if (!emergency) emergency = i;
          if (boundaries & EXR_BOUNDARY_LINE) break;
        }
      }
      if (!i) i = emergency;
    }
    if (!i) break; /* An indivisible first cluster keeps its clipping contract. */
    if (++tries > 256)
      return exr_fail(f->error, EXR_LIMIT, "Final line fitting retry limit exceeded");
    b->line_end = i;
    b->forced = b->final = 0;
  }
  b->line_ready = 1;
  return EXR_OK;
}
/* Only the leading carry segment can retain context from the committed line.
   Other segments are separated by an existing line opportunity. */
static exr_status reshape_carry(flow *f, exr_line_buffer *b) {
  size_t prefix = 1, old = 0, i, old_ready = b->ready, old_cluster = b->cluster_start;
  uint32_t after = b->after;
  exr_status status;
  b->before = 0;
  for (i = b->raw.glyph_count; i; i--)
    if (!exr_ot_transparent(b->raw.glyphs[i - 1].codepoint)) {
      b->before = b->raw.glyphs[i - 1].codepoint;
      break;
    }
  if (!b->raw.glyph_count) return EXR_OK;
  while (prefix < b->raw.glyph_count &&
         !(b->raw.glyphs[prefix].boundaries & (EXR_BOUNDARY_LINE | EXR_BOUNDARY_MANDATORY))) prefix++;
  while (old < b->ready && b->run.glyphs[old].start < b->raw.glyphs[prefix - 1].end) old++;
  for (i = prefix; i < b->raw.glyph_count; i++)
    if (!exr_ot_transparent(b->raw.glyphs[i].codepoint)) {
      after = b->raw.glyphs[i].codepoint;
      break;
    }
  if (i == b->raw.glyph_count)
    for (i = b->ready; i < b->run.glyph_count; i++)
      if (!exr_ot_transparent(b->run.glyphs[i].codepoint)) {
        after = b->run.glyphs[i].codepoint;
        break;
      }
  status = shape_line_copy(f, b, &b->line, b->raw.glyphs, prefix, 0, after, 0);
  if (status != EXR_OK) return status;
  status = line_reserve(f, b, &b->run, b->run.glyph_count - old + b->line.glyph_count);
  if (status != EXR_OK) return status;
  memmove(b->run.glyphs + b->line.glyph_count, b->run.glyphs + old,
           (b->run.glyph_count - old) * sizeof(*b->run.glyphs));
  if (b->line.glyph_count)
    memcpy(b->run.glyphs, b->line.glyphs, b->line.glyph_count * sizeof(*b->run.glyphs));
  b->run.glyph_count += b->line.glyph_count;
  b->run.glyph_count -= old;
  b->ready = old_ready - old + b->line.glyph_count;
  b->cluster_start = b->ready + old_cluster - old_ready;
  b->line.glyph_count = 0;
  return EXR_OK;
}
exr_status exr_inline_drain(flow *f, exr_line_buffer *b) {
  if (!b->initialized) reset_line_scan(b);
  for (;;) {
    if (!b->line_end) {
      float indent = f->first_line ? f->paragraph->indent : 0;
      float available = fmaxf(1, f->width - indent);
      while (b->scan < b->ready) {
        size_t i = b->scan;
        exr_glyph *g = &b->run.glyphs[i];
        float advance;
        if (exr_font_size(&f->font->faces[g->font_index], g->size))
          return exr_fail(f->error, EXR_FONT, "Cannot size line font");
        if (i && (g->boundaries & EXR_BOUNDARY_MANDATORY)) {
          b->line_end = i; b->forced = 1; b->final = 0; break;
        }
        if (i && (g->boundaries & EXR_BOUNDARY_GRAPHEME) && !(g->boundaries & EXR_BOUNDARY_GLUE)) {
          b->emergency = i;
          if (g->boundaries & EXR_BOUNDARY_LINE) b->soft = i;
        }
        advance = g->advance + line_kern(f, i ? g - 1 : NULL, g);
        if (i && b->scan_width + advance > available &&
            (b->soft != SIZE_MAX || b->emergency != SIZE_MAX)) {
          b->line_end = b->soft != SIZE_MAX ? b->soft : b->emergency;
          b->forced = b->final = 0; break;
        }
        b->scan_width += advance;
        b->scan++;
      }
      if (!b->line_end && b->finishing && b->ready) {
        b->line_end = b->ready; b->forced = 0; b->final = 1;
      }
    }
    if (!b->line_end) return EXR_OK;
    {
      size_t end;
      exr_status status;
      if (!b->line_ready) {
        status = fit_line(f, b);
        if (status != EXR_OK) return status;
      }
      end = b->line.glyph_count;
      if (end) {
        status = exr_flow_emit_line(f, b->line.glyphs, end, b->forced, b->final);
        if (status != EXR_OK) return status;
      }
      end = b->line_end;
      memmove(b->run.glyphs, b->run.glyphs + end,
                (b->run.glyph_count - end) * sizeof(*b->run.glyphs));
      b->run.glyph_count -= end; b->ready -= end; b->cluster_start -= end;
      memmove(b->raw.glyphs, b->raw.glyphs + b->raw_end,
                (b->raw.glyph_count - b->raw_end) * sizeof(*b->raw.glyphs));
      b->raw.glyph_count -= b->raw_end;
      b->line.glyph_count = 0; b->line_ready = 0;
      reset_line_scan(b);
      status = reshape_carry(f, b);
      if (status != EXR_OK) return status;
    }
  }
}
typedef struct { flow *f; size_t node, at; } inline_text_cursor;
static int following_inline_scalar(void *context, uint32_t *cp) {
  inline_text_cursor *c = context;
  while (c->node != SIZE_MAX) {
    const exr_node *n = &c->f->doc->nodes[c->node];
    if (c->at<n->end && exr_ruby_node(c->f->doc,c->node)) { c->at=n->end; *cp=0xfffc; return 1; }
    if (c->at < n->end)
      return exr_next(c->f->doc->text, n->end, &c->at, cp);
    c->node = next_text(c->f, following(c->f, c->node));
    if (c->node != SIZE_MAX) c->at = c->f->doc->nodes[c->node].start;
  }
  return 0;
}
exr_status exr_inline_feed(flow *f, exr_line_buffer *b, exr_glyph g) {
  exr_status status;
  if (!b->initialized) reset_line_scan(b);
  {
    inline_text_cursor cursor = {f, g.node, g.end};
    g.boundaries = exr_text_step(&b->text, g.codepoint, following_inline_scalar, &cursor);
  }
  if ((g.flags & EXR_GLYPH_RUBY_ITEM) ||
      (b->run.glyph_count && (b->run.glyphs[b->run.glyph_count-1].flags & EXR_GLYPH_RUBY_ITEM)))
    g.boundaries |= EXR_BOUNDARY_GRAPHEME;
  if (f->writing_mode != EXR_WRITING_HORIZONTAL_TB) {
    if (g.boundaries & EXR_BOUNDARY_GRAPHEME)
      b->vertical_flags = exr_vertical_flags(g.codepoint, f->styles[g.node].orientation);
    g.flags |= b->vertical_flags;
  }
  if ((g.boundaries & EXR_BOUNDARY_GRAPHEME) && b->cluster_start < b->run.glyph_count) {
    status = measure_line_cluster(f, b);
    if (status != EXR_OK) return status;
    if ((g.boundaries & (EXR_BOUNDARY_LINE | EXR_BOUNDARY_MANDATORY)) ||
        !exr_ot_present(&f->font->faces[b->run.glyphs[b->cluster_start - 1].font_index])) {
      status = shape_line_segment(f, b, g.codepoint);
      if (status != EXR_OK) return status;
    }
  }
  if (b->run.glyph_count - b->ready >= 8192)
    return exr_fail(f->error, EXR_LIMIT, "Shaping segment exceeds 8192 scalars without a break");
  status = line_reserve(f, b, &b->run, b->run.glyph_count + 1);
  if (status != EXR_OK) return status;
  b->run.glyphs[b->run.glyph_count++] = g;
  return exr_inline_drain(f, b);
}
exr_status exr_inline_finish(flow *f, exr_line_buffer *b) {
  exr_status status;
  if (!b->finishing) {
    status = measure_line_cluster(f, b);
    if (status == EXR_OK) status = shape_line_segment(f, b, 0);
    if (status != EXR_OK) return status;
    b->finishing = 1;
  }
  status = exr_inline_drain(f, b);
  if (status != EXR_OK) return status;
  memset(&b->text, 0, sizeof(b->text));
  b->raw.glyph_count = 0; b->before = b->after = 0; b->finishing = 0;
  reset_line_scan(b);
  return EXR_OK;
}
void exr_inline_buffer_clear(exr_line_buffer *b) {
  free(b->run.glyphs); free(b->raw.glyphs); free(b->line.glyphs);
  memset(b, 0, sizeof(*b));
}
