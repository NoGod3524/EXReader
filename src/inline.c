/* SPDX-License-Identifier: GPL-3.0-only */
#include "flow_internal.h"
#include "bidi_internal.h"
#include "opentype_internal.h"

void exr_inline_clear(exr_inline_bidi *b) {
  exr_bidi_free(b->analysis);
  free(b->offsets);
  memset(b, 0, sizeof(*b));
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
    else if (n->kind == EXR_NODE_TEXT)
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
  for (node = first; node != SIZE_MAX; node = next_text(f, following(f, node))) {
    const exr_node *n = &f->doc->nodes[node];
    bytes += n->end - n->start;
    for (at = n->start; at < n->end;) {
      if (!exr_next(f->doc->text, n->end, &at, &cp))
        return exr_fail(f->error, EXR_ENCODING, "Invalid inline UTF-8");
      complex |= exr_bidi_complex(cp);
      if (++count > EXR_MAX_ITEMS)
        return exr_fail(f->error, EXR_LIMIT, "Inline scalar limit exceeded");
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
static uint32_t script(uint32_t cp) {
  if ((cp >= 0x600 && cp <= 0x8ff) || (cp >= 0xfb50 && cp <= 0xfeff))
    return EXR_TAG('a','r','a','b');
  if (cp >= 0x590 && cp <= 0x5ff) return EXR_TAG('h','e','b','r');
  if ((cp >= 'A' && cp <= 'Z') || (cp >= 'a' && cp <= 'z') ||
      (cp >= 0xc0 && cp <= 0x2ff)) return EXR_TAG('l','a','t','n');
  return 0;
}
exr_status exr_inline_shape(flow *f, size_t start, uint32_t before, uint32_t after) {
  exr_layout *l = f->layout;
  exr_layout result = {0};
  size_t i, end, j, k, *positions = NULL;
  exr_status status = EXR_OK;
  for (i = start; i < l->glyph_count; i = end) {
    exr_glyph *g = &l->glyphs[i];
    exr_shaped_glyph *shaped = NULL;
    exr_shape_options options = exr_shape_defaults();
    exr_buffer text = {0};
    uint32_t tag = script(g->codepoint);
    size_t n = 0;
    end = i + 1;
    while (end < l->glyph_count) {
      const exr_glyph *v = &l->glyphs[end];
      uint32_t next_tag = script(v->codepoint);
      if (v->font_index != g->font_index || v->size != g->size ||
          (((v->flags & 3) != (g->flags & 3) || v->color != g->color) &&
           v->cluster_start != g->cluster_start) ||
          v->bidi_level != g->bidi_level || (tag && next_tag && tag != next_tag) ||
          (v->boundaries & (EXR_BOUNDARY_LINE | EXR_BOUNDARY_MANDATORY)) ||
          v->codepoint == '\t' || g->codepoint == '\t') break;
      if (!tag) tag = next_tag;
      end++;
    }
    if (!exr_ot_present(&f->font->faces[g->font_index]) || g->codepoint == '\t') {
      if (!exr_grow((void **)&result.glyphs, &result.glyph_cap,
                       result.glyph_count + end - i, sizeof(*g))) { status = EXR_MEMORY; goto done; }
      memcpy(result.glyphs + result.glyph_count, g, (end - i) * sizeof(*g));
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
    j = i;
    while (j > start && exr_ot_transparent(l->glyphs[j - 1].codepoint)) j--;
    options.context_before = j > start ? l->glyphs[j - 1].codepoint : before;
    j = end;
    while (j < l->glyph_count && exr_ot_transparent(l->glyphs[j].codepoint)) j++;
    options.context_after = j < l->glyph_count ? l->glyphs[j].codepoint : after;
    status = exr_shape(f->font, g->font_index, text.data, text.size, &options, &shaped, &n, f->error);
    free(text.data);
    if (status != EXR_OK) goto done;
    if (n > EXR_MAX_ITEMS - result.glyph_count ||
        !exr_grow((void **)&result.glyphs, &result.glyph_cap, result.glyph_count + n, sizeof(*g))) {
      free(shaped); status = EXR_LIMIT; goto done;
    }
    for (j = 0, k = 0; j < n; j++) {
      exr_glyph v;
      size_t finish;
      while (k + 1 < end - i && positions[k + 1] <= shaped[j].start) k++;
      finish = k + 1;
      while (finish < end - i && positions[finish] < shaped[j].end) finish++;
      v = l->glyphs[i + k];
      v.start = l->glyphs[i + k].start;
      v.end = l->glyphs[i + finish - 1].end;
      if (v.cluster_start > v.start) v.cluster_start = v.start;
      v.cluster_end = l->glyphs[i + finish - 1].cluster_end;
      if (v.cluster_end < v.end) v.cluster_end = v.end;
      v.glyph = shaped[j].glyph;
      v.advance = shaped[j].advance_x;
      v.offset_x = shaped[j].offset_x;
      v.offset_y = shaped[j].offset_y;
      v.flags = shaped[j].flags | EXR_GLYPH_SHAPED;
      if (v.bidi_level == UINT_MAX) v.flags |= EXR_GLYPH_HIDDEN;
      if (result.glyph_count &&
          result.glyphs[result.glyph_count - 1].cluster_start == v.cluster_start)
        v.boundaries = 0;
      result.glyphs[result.glyph_count++] = v;
    }
    free(shaped); free(positions); positions = NULL;
  }
  if (result.glyph_count > EXR_MAX_ITEMS - start ||
      !exr_grow((void **)&l->glyphs, &l->glyph_cap, start + result.glyph_count, sizeof(*l->glyphs))) {
    status = EXR_LIMIT; goto done;
  }
  memcpy(l->glyphs + start, result.glyphs, result.glyph_count * sizeof(*l->glyphs));
  l->glyph_count = start + result.glyph_count;
done:
  free(positions); free(result.glyphs);
  return status == EXR_OK ? EXR_OK : exr_fail(f->error, status, "Inline shaping failed");
}
