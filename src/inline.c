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
    if (f->styles[node].display == EXR_CSS_NONE || n->start == SIZE_MAX || f->styles[node].float_side)
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
    unsigned generated = 0;
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
      int context_only = (v->flags & EXR_GLYPH_HIDDEN) && (v->bidi_level == UINT_MAX || v->cluster_start == g->cluster_start);
      /* Hidden selectors share their base's shaping run across inline styles;
         X9 controls also remain available to the surrounding shaping context. */
      if ((v->flags & EXR_GLYPH_RUBY_ITEM) || (!context_only && (v->font_index != g->font_index || v->size != g->size ||
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
        /* One scan per shaped cluster, including a long combining sequence. */
        generated = 0;
        { size_t source; for(source=k;source<finish;source++) generated |= l->glyphs[i+source].flags & EXR_GLYPH_GENERATED; }
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
      v.flags |= generated;
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
  b->scan_ascent=b->scan_descent=b->scan_leading=0;
  b->initialized = 1;
  b->rewrite=0;
}
void exr_inline_rescan(exr_line_buffer *b) {
  reset_line_scan(b); b->line_ready=0; b->line.glyph_count=0;
}
static exr_status line_metric(flow *f,const exr_glyph *g,float *ascent,float *descent,float *leading) {
  if(g->flags&EXR_GLYPH_RUBY_ITEM) {
    *ascent=fmaxf(*ascent,g->offset_x); *descent=fmaxf(*descent,g->offset_y);
  } else {
    exr_face *face=&f->font->faces[g->font_index];
    if(exr_font_size(face,g->size)) return exr_fail(f->error,EXR_FONT,"Cannot size inline corridor font");
    *ascent=fmaxf(*ascent,exr_font_ascent(face)); *descent=fmaxf(*descent,exr_font_descent(face));
  }
  *leading=fmaxf(*leading,g->line_height); return EXR_OK;
}
static exr_status line_work(flow *f, size_t count) {
  const size_t limit = 64 * 1024 * 1024;
  if (count > limit - f->assets->shape_work)
    return exr_fail(f->error, EXR_LIMIT, "Line shaping work limit exceeded");
  f->assets->shape_work += count;
  return EXR_OK;
}
size_t exr_inline_extra_size(const exr_line_buffer *b,int compact) {
  size_t bytes=(compact ? b->edit_count : b->edit_capacity)*sizeof(*b->edits);
  if(b->word) bytes+=sizeof(*b->word)+(compact ? b->word->edit_count : b->word->edit_capacity)*sizeof(*b->word->edits);
  return bytes;
}
static size_t line_payload(const exr_line_buffer *b) {
  return (b->run.glyph_cap+b->raw.glyph_cap+b->line.glyph_cap)*sizeof(exr_glyph)+exr_inline_extra_size(b,0);
}
static exr_status edit_reserve(flow *f,exr_line_buffer *b,exr_hyphen_edit **items,size_t *capacity,size_t count) {
  size_t next=*capacity ? *capacity : 4,other=line_payload(b)-*capacity*sizeof(**items);void *p;
  if(count<=*capacity) return EXR_OK;
  while(next<count) next*=2;
  if(other>=16*1024*1024 || next>(16*1024*1024-other)/sizeof(**items)) return exr_fail(f->error,EXR_LIMIT,"Hyphenation line payload exceeds 16 MiB");
  p=realloc(*items,next*sizeof(**items));if(!p) return exr_fail(f->error,EXR_MEMORY,"Hyphenation line allocation failed");
  *items=p;*capacity=next;return EXR_OK;
}
static exr_status line_reserve(flow *f, exr_line_buffer *b, exr_layout *target, size_t count) {
  size_t other=line_payload(b)-target->glyph_cap*sizeof(exr_glyph),limit;
  if(other>=16*1024*1024) return exr_fail(f->error,EXR_LIMIT,"Line buffer exceeds 16 MiB");
  limit=(16*1024*1024-other)/sizeof(exr_glyph);
  if (count > limit)
    return exr_fail(f->error, EXR_LIMIT, "Line buffer exceeds 16 MiB");
  target->glyph_limit = limit;
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
  if (hyphen && count && to->glyphs[count - 1].codepoint == 0xad &&
      f->styles[to->glyphs[count-1].node].hyphens!=EXR_HYPHENS_NONE) {
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
static exr_status generated_hyphen(flow *f,exr_line_buffer *b,exr_layout *to,size_t point,size_t first,const exr_glyph *anchor) {
  flow child=*f;exr_glyph g=*anchor; size_t i,n,order[32]; exr_status status;
  n=exr_font_order(f->font,f->styles[g.node].family,f->styles[g.node].flags,f->doc->nodes[g.node].chapter,order);
  for(i=0;i<n && !exr_font_has_glyph(f->font,order[i],0x2010);i++) {}
  g.codepoint=i<n ? 0x2010 : '-';
  g.flags=f->styles[g.node].flags|EXR_GLYPH_GENERATED;
  if(f->writing_mode!=EXR_WRITING_HORIZONTAL_TB) g.flags|=exr_vertical_flags(g.codepoint,f->styles[g.node].orientation);
  g.start=g.cluster_start=first;g.end=g.cluster_end=point;g.boundaries=EXR_BOUNDARY_GRAPHEME;
  g.offset_x=g.offset_y=0;
  status=line_reserve(f,b,to,to->glyph_count+1); if(status!=EXR_OK) return status;
  to->glyphs[to->glyph_count++]=g; child.layout=to;
  return exr_flow_cluster(&child,to->glyph_count-1,to->glyph_count);
}
/* Each replacement side is one source cluster. Expanded glyphs share that
   source interval, so selection never invents offsets inside generated text. */
static exr_status generated_text(flow *f,exr_line_buffer *b,exr_layout *to,const exr_glyph *anchor,
                                 const char *text,size_t size,size_t first,size_t last) {
  size_t at=0,start=to->glyph_count;flow child=*f;exr_status status;
  do {
    exr_glyph g=*anchor;uint32_t cp=0x200b;
    if(size && !exr_next(text,size,&at,&cp)) return exr_fail(f->error,EXR_ENCODING,"Invalid generated replacement text");
    g.codepoint=cp;g.start=g.cluster_start=first;g.end=g.cluster_end=last;
    g.flags=f->styles[g.node].flags|EXR_GLYPH_GENERATED;
    if(!size) g.flags|=EXR_GLYPH_HIDDEN;
    if(f->writing_mode!=EXR_WRITING_HORIZONTAL_TB) g.flags|=exr_vertical_flags(cp,f->styles[g.node].orientation);
    g.boundaries=to->glyph_count==start ? EXR_BOUNDARY_GRAPHEME : 0;g.offset_x=g.offset_y=g.advance=0;
    status=line_reserve(f,b,to,to->glyph_count+1);if(status!=EXR_OK) return status;
    to->glyphs[to->glyph_count++]=g;
  } while(at<size);
  child.layout=to;status=exr_flow_cluster(&child,start,to->glyph_count);
  return status==EXR_OK ? line_work(f,to->glyph_count-start) : status;
}
static size_t edit_at(const exr_line_buffer *b,size_t point) {
  size_t lo=0,hi=b->edit_count;
  while(lo<hi) { size_t mid=lo+(hi-lo)/2;if(b->edits[mid].point<point) lo=mid+1;else hi=mid; }
  return lo<b->edit_count && b->edits[lo].point==point ? lo+1 : 0;
}
static size_t raw_at(const exr_line_buffer *b,size_t point) {
  size_t lo=0,hi=b->raw.glyph_count;
  while(lo<hi) { size_t mid=lo+(hi-lo)/2;if(b->raw.glyphs[mid].start<point) lo=mid+1;else hi=mid; }
  return lo;
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
static exr_status line_geometry(flow *f,exr_line_buffer *b,float *width) {
  size_t i; float ascent=0,descent=0,leading=0,minimum=0,old_y=f->y;
  float indent=f->first_line ? f->paragraph->indent : 0; exr_status status;
  *width=0;
  for(i=0;i<b->line.glyph_count;i++) {
    exr_glyph *g=&b->line.glyphs[i];
    if(f->floats->count && !f->intrinsic) {
      status=line_metric(f,g,&ascent,&descent,&leading); if(status!=EXR_OK) return status;
    } else if(exr_font_size(&f->font->faces[g->font_index],g->size)) return exr_fail(f->error,EXR_FONT,"Cannot size final line font");
    *width+=g->advance+line_kern(f,i ? g-1 : NULL,g);
    if(!i || g->cluster_start==b->line.glyphs[0].cluster_start) minimum=*width;
  }
  b->line_x=f->x; b->line_width=f->width;
  if(!f->intrinsic && f->floats->count && b->line.glyph_count) {
    status=exr_flow_line_slot(f,fmaxf(leading,ascent+descent),fmaxf(1,minimum+indent),b->line.glyphs[0].start,&b->line_x,&b->line_width);
    if(status!=EXR_OK) return status;
    if(f->y!=old_y) return EXR_REFLOW;
  }
  return EXR_OK;
}
static void merge_inserted_cluster(exr_glyph *glyphs,size_t count);
static const char *node_language(const flow *f,size_t node);
static int word_joiner(uint32_t cp);
static size_t word_index(const size_t *offsets,size_t count,size_t byte);
/* Raw-source candidates may cross a provisional ligature. Reshape the complete
   selected prefix, including the inserted character, then rebuild its carry. */
static exr_status fit_dictionary(flow *f,exr_line_buffer *b,int *found) {
  size_t i,limit=0,source_end; int any=0; exr_status status;
  float indent=f->first_line ? f->paragraph->indent : 0;
  *found=0; if(!f->hyphenator || !b->ready) return EXR_OK;
  source_end=b->run.glyphs[b->scan<b->ready ? b->scan : b->ready-1].cluster_end;
  while(limit<b->raw.glyph_count && b->raw.glyphs[limit].start<source_end) limit++;
  for(i=0;i<b->edit_count;i++) { size_t at=raw_at(b,b->edits[i].point);if(at>limit && at<b->raw.glyph_count) limit=at; }
  for(i=1;i<b->raw.glyph_count && i<=limit;i++) any|=!!(b->raw.glyphs[i].boundaries&EXR_BOUNDARY_AUTO_HYPHEN);
  if(!any) return EXR_OK;
  /* A complete fitting final/forced line must retain its original ligatures. */
  if(!f->intrinsic && (b->final || b->forced)) {
    float width; size_t end=b->run.glyphs[b->line_end-1].cluster_end,count=0;
    while(count<b->raw.glyph_count && b->raw.glyphs[count].start<end) count++;
    status=shape_line_copy(f,b,&b->line,b->raw.glyphs,count,0,0,0); if(status!=EXR_OK) return status;
    status=line_geometry(f,b,&width); if(status!=EXR_OK) return status;
    if(width<=fmaxf(1,b->line_width-indent)+.001f) { b->raw_end=count; b->line_ready=1; *found=1; return EXR_OK; }
  }
  for(i=f->intrinsic==1 ? 1 : limit;i && i<=limit;i=f->intrinsic==1 ? i+1 : i-1) {
    unsigned boundaries; int automatic; float width;flow child=*f;size_t consumed=0,point,rewrite=0,raw_end=i;
    if(i>=b->raw.glyph_count) continue;
    boundaries=b->raw.glyphs[i].boundaries;
    if(!(boundaries&EXR_BOUNDARY_GRAPHEME) || (boundaries&EXR_BOUNDARY_GLUE) ||
       !(boundaries&(EXR_BOUNDARY_LINE|EXR_BOUNDARY_AUTO_HYPHEN))) continue;
    point=b->raw.glyphs[i].start;
    if(boundaries&EXR_BOUNDARY_AUTO_HYPHEN) rewrite=edit_at(b,point);
    automatic=!!(boundaries&EXR_BOUNDARY_AUTO_HYPHEN) && (!(boundaries&EXR_BOUNDARY_LINE) || rewrite);
    if(automatic) {
      /* Start from unshaped source again, so kerning/joining includes the hyphen. */
      size_t prefix=i;const exr_hyphen_edit *edit=rewrite ? &b->edits[rewrite-1] : NULL;
      if(edit) {
        if(edit->start<b->raw.glyphs[0].start) continue;
        prefix=edit->mapped ? edit->raw_start : raw_at(b,edit->start);
        raw_end=edit->mapped ? edit->raw_end : raw_at(b,edit->end);
        if(edit->mapped && edit->raw_point!=i) return exr_fail(f->error,EXR_FORMAT,"Stale mapped hyphenation point");
        if(prefix>i || raw_end<i || raw_end>b->raw.glyph_count || (raw_end==b->raw.glyph_count && b->raw.glyphs[raw_end-1].end<edit->end)) continue;
      }
      status=copy_glyphs(f,b,&b->line,b->raw.glyphs,prefix);if(status!=EXR_OK) return status;
      status=line_work(f,prefix+1);if(status!=EXR_OK) return status;
      if(edit && edit->before) {
        status=generated_text(f,b,&b->line,&b->raw.glyphs[i-1],edit->text,edit->before,edit->start,point);if(status!=EXR_OK) return status;
      }
      status=generated_hyphen(f,b,&b->line,point,edit && !edit->before ? edit->start : point,&b->raw.glyphs[i-1]);if(status!=EXR_OK) return status;
      if(edit && edit->mapped) merge_inserted_cluster(b->line.glyphs,b->line.glyph_count);
      child.layout=&b->line; status=exr_inline_shape(&child,0,0,0); if(status!=EXR_OK) return status;
      status=line_work(f,b->line.glyph_count); if(status!=EXR_OK) return status;
    } else { status=shape_line_copy(f,b,&b->line,b->raw.glyphs,i,0,0,1); if(status!=EXR_OK) return status; }
    status=line_geometry(f,b,&width); if(status!=EXR_OK) return status;
    if(!f->intrinsic && width>fmaxf(1,b->line_width-indent)+.001f) continue;
    while(consumed<b->ready && b->run.glyphs[consumed].start<point) consumed++;
    if(!consumed) continue;
    b->line_end=consumed;b->raw_end=raw_end;b->rewrite=rewrite; b->forced=b->final=0; b->line_ready=1;
    *found=1; return EXR_OK;
  }
  return EXR_OK;
}
/* A provisional ligature is one protected cluster. Final fitting can retreat
   across its start, never through it or a GLUE boundary. */
static exr_status fit_line(flow *f, exr_line_buffer *b) {
  float indent = f->first_line ? f->paragraph->indent : 0;
  float available;
  size_t tries = 0;
  { int found; exr_status status=fit_dictionary(f,b,&found); if(status!=EXR_OK || found) return status; }
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
    status=line_geometry(f,b,&width); if(status!=EXR_OK) return status;
    available=fmaxf(1,b->line_width-indent);
    if (f->intrinsic || width <= available + 0.001f) break;
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
static int wait_for_word(const exr_line_buffer *b) {
  size_t source_end,raw_end,i;
  if(!b->ready || !b->line_end || !b->raw.glyph_count) return 0;
  source_end=b->run.glyphs[b->scan<b->ready ? b->scan : b->ready-1].cluster_end;
  raw_end=b->raw.glyphs[b->raw.glyph_count-1].end;
  if(b->word && b->word->edit_count && b->word->start<source_end && b->word->until>raw_end) return 1;
  for(i=0;i<b->edit_count;i++) if(b->edits[i].word_start<source_end && b->edits[i].until>raw_end) return 1;
  return 0;
}
static void prune_edits(exr_line_buffer *b,size_t through) {
  size_t i,n=0;for(i=0;i<b->edit_count;i++) if(b->edits[i].point>through) b->edits[n++]=b->edits[i];
  b->edit_count=n;
}
/* Mapped edit indices refer to the unshaped FIFO, not shaped glyph indices.
   Never turn an edit whose left context was consumed into an ordinary hyphen. */
static void advance_mapped_edits(exr_line_buffer *b,size_t consumed) {
  size_t i,n=0;
  for(i=0;i<b->edit_count;i++) {
    exr_hyphen_edit edit=b->edits[i];
    if(edit.mapped) {
      if(edit.raw_start<consumed || edit.raw_point<consumed || edit.raw_end<consumed) {
        if(edit.raw_point<b->raw.glyph_count) b->raw.glyphs[edit.raw_point].boundaries&=~EXR_BOUNDARY_AUTO_HYPHEN;
        continue;
      }
      edit.raw_start-=consumed;edit.raw_point-=consumed;edit.raw_end-=consumed;
    }
    b->edits[n++]=edit;
  }
  b->edit_count=n;
}
static exr_status mapped_edit(flow *f,exr_line_buffer *b,const exr_hyphen_edit *edit) {
  size_t lo=0,hi=b->edit_count;exr_status status;
  while(lo<hi) { size_t mid=lo+(hi-lo)/2;if(b->edits[mid].point<edit->point) lo=mid+1;else hi=mid; }
  if(lo<b->edit_count && b->edits[lo].point==edit->point) return EXR_OK;
  status=edit_reserve(f,b,&b->edits,&b->edit_capacity,b->edit_count+1);if(status!=EXR_OK) return status;
  memmove(b->edits+lo+1,b->edits+lo,(b->edit_count-lo)*sizeof(*b->edits));
  b->edits[lo]=*edit;b->edit_count++;return EXR_OK;
}
static size_t mapped_edge(const exr_line_buffer *b,size_t at,size_t until) {
  return at<b->raw.glyph_count && b->raw.glyphs[at].start<until ? b->raw.glyphs[at].start : until;
}
static int deleted_placeholder(const exr_glyph *g) {
  return (g->flags&(EXR_GLYPH_GENERATED|EXR_GLYPH_HIDDEN))==(EXR_GLYPH_GENERATED|EXR_GLYPH_HIDDEN);
}
static exr_status rematch_token(flow *f,exr_line_buffer *b,const char *text,size_t bytes,const size_t *offsets,
                               const size_t *indices,size_t count,size_t origin,size_t until) {
  char previous[256]={0};int have_previous=0;size_t k;exr_status status;
  for(k=0;k<count;k++) {
    const exr_glyph *g=&b->raw.glyphs[indices[k]];char key[256];exr_hyphenation *result=NULL;const exr_hyphen_break *items;size_t n,j;
    if(g->start<=origin || f->styles[g->node].hyphens!=EXR_HYPHENS_AUTO || !(g->boundaries&EXR_BOUNDARY_GRAPHEME) ||
       (g->boundaries&EXR_BOUNDARY_GLUE) || !exr_hyphen_language(node_language(f,g->node),key)) continue;
    if(have_previous && !strcmp(previous,key)) continue;
    memcpy(previous,key,strlen(key)+1);have_previous=1;
    status=line_work(f,count+1);if(status!=EXR_OK) return status;
    status=exr_hyphenator_query(f->hyphenator,key,text,bytes,&f->config->control,&result,f->error);if(status!=EXR_OK) return status;
    items=exr_hyphenation_breaks(result,&n);
    for(j=0;j<n;j++) {
      const exr_hyphen_break *item=&items[j];size_t point=word_index(offsets,count,item->point);const exr_glyph *candidate;char language[256];
      if(point==SIZE_MAX || point>=count) { status=exr_fail(f->error,EXR_FORMAT,"Unmapped display hyphenation point");break; }
      candidate=&b->raw.glyphs[indices[point]];
      if(candidate->start<=origin || !(candidate->boundaries&EXR_BOUNDARY_GRAPHEME) || (candidate->boundaries&EXR_BOUNDARY_GLUE) ||
         f->styles[candidate->node].hyphens!=EXR_HYPHENS_AUTO ||
         !exr_hyphen_language(node_language(f,candidate->node),language) || strcmp(language,key)) continue;
      if(item->start!=item->point || item->end!=item->point || item->before_size || item->after_size) {
        size_t first=word_index(offsets,count,item->start),last=word_index(offsets,count,item->end);exr_hyphen_edit edit={0};
        if(first==SIZE_MAX || last==SIZE_MAX) { status=exr_fail(f->error,EXR_FORMAT,"Unmapped display replacement range");break; }
        edit.point=candidate->start;edit.start=mapped_edge(b,indices[first],until);edit.end=mapped_edge(b,indices[last],until);
        edit.word_start=b->raw.glyphs[indices[0]].start;edit.until=until;edit.before=item->before_size;edit.after=item->after_size;
        edit.raw_point=indices[point];edit.raw_start=indices[first];edit.raw_end=indices[last];edit.mapped=1;
        if(edit.start>edit.point || edit.end<edit.point) { status=exr_fail(f->error,EXR_FORMAT,"Nonmonotonic display replacement range");break; }
        memcpy(edit.text,item->before,item->before_size);memcpy(edit.text+item->before_size+1,item->after,item->after_size);
        status=mapped_edit(f,b,&edit);if(status!=EXR_OK) break;
      }
      b->raw.glyphs[indices[point]].boundaries|=EXR_BOUNDARY_AUTO_HYPHEN;
    }
    exr_hyphenation_free(result);if(status!=EXR_OK) return status;
  }
  return EXR_OK;
}
static exr_status rematch_remainder(flow *f,exr_line_buffer *b,size_t origin,size_t until) {
  size_t i=0,end=0;exr_status status;
  while(end<b->raw.glyph_count && b->raw.glyphs[end].start<until) end++;
  while(i<end) {
    char text[1024];size_t bytes=0,count=0,offsets[257],indices[257];int numeric=0,previous=0,oversized=0;
    if(deleted_placeholder(&b->raw.glyphs[i]) || !exr_hyphen_word_kind(b->raw.glyphs[i].codepoint)) { i++;continue; }
    for(;i<end;i++) {
      const exr_glyph *g=&b->raw.glyphs[i];unsigned kind=exr_hyphen_word_kind(g->codepoint);char encoded[5];exr_buffer scalar={encoded,0,sizeof(encoded)};size_t next=i+1;
      if(deleted_placeholder(g)) continue;
      while(next<end && deleted_placeholder(&b->raw.glyphs[next])) next++;
      if(!kind && !(word_joiner(g->codepoint) && previous && next<end && exr_hyphen_word_kind(b->raw.glyphs[next].codepoint))) break;
      numeric|=kind==3 || (!count && kind!=1);previous=!!kind;
      if(oversized) continue;
      if(!exr_codepoint(&scalar,g->codepoint)) return exr_fail(f->error,EXR_ENCODING,"Invalid display word scalar");
      if(count==256 || scalar.size>sizeof(text)-bytes) { oversized=1;continue; }
      offsets[count]=bytes;indices[count++]=i;memcpy(text+bytes,scalar.data,scalar.size);bytes+=scalar.size;
    }
    if(count && !numeric && !oversized) {
      offsets[count]=bytes;indices[count]=i;
      status=rematch_token(f,b,text,bytes,offsets,indices,count,origin,until);if(status!=EXR_OK) return status;
    }
  }
  return EXR_OK;
}
/* A zero-cut insertion and the following original grapheme share a source
   start. Keep one complete source cluster: hit testing needs its original end,
   and fitting must consume that grapheme even when the inserted text clips. */
static void merge_inserted_cluster(exr_glyph *glyphs,size_t count) {
  size_t i,j,k;
  for(i=0;i<count;i=j) {
    size_t end=glyphs[i].cluster_end;j=i+1;
    while(j<count && glyphs[j].cluster_start==glyphs[i].cluster_start) {
      if(glyphs[j].cluster_end>end) end=glyphs[j].cluster_end;
      j++;
    }
    for(k=i;k<j;k++) { glyphs[k].cluster_end=end;if(k>i) glyphs[k].boundaries=0; }
  }
}
static exr_status replacement_carry(flow *f,exr_line_buffer *b) {
  exr_hyphen_edit edit=b->edits[b->rewrite-1];size_t at=edit.mapped ? edit.raw_point : raw_at(b,edit.point),prefix=0,i,unready=b->run.glyph_count-b->ready;
  size_t extra_cluster=b->cluster_start-b->ready,tail=b->raw.glyph_count-b->raw_end;exr_glyph anchor=b->raw.glyphs[at];exr_status status;
  b->line.glyph_count=0;
  if(edit.after || edit.end>edit.point) {
    status=generated_text(f,b,&b->line,&anchor,edit.text+edit.before+1,edit.after,edit.point,edit.end);if(status!=EXR_OK) return status;
    prefix=b->line.glyph_count;
  }
  status=line_reserve(f,b,&b->raw,prefix+tail);if(status!=EXR_OK) return status;
  memmove(b->raw.glyphs+prefix,b->raw.glyphs+b->raw_end,tail*sizeof(*b->raw.glyphs));
  if(prefix) memcpy(b->raw.glyphs,b->line.glyphs,prefix*sizeof(*b->raw.glyphs));
  b->raw.glyph_count=prefix+tail;
  if(prefix && edit.end==edit.point) merge_inserted_cluster(b->raw.glyphs,b->raw.glyph_count);
  /* Future original input must not restore stale points. The complete ready
     remainder is re-queried below using its actual display spelling. */
  b->blocked_until=edit.until;
  for(i=0;i<b->raw.glyph_count;i++) if(b->raw.glyphs[i].start<edit.until) b->raw.glyphs[i].boundaries&=~EXR_BOUNDARY_AUTO_HYPHEN;
  for(i=b->ready;i<b->run.glyph_count;i++) if(b->run.glyphs[i].start<edit.until) b->run.glyphs[i].boundaries&=~EXR_BOUNDARY_AUTO_HYPHEN;
  prune_edits(b,edit.until);
  status=rematch_remainder(f,b,edit.point,edit.until);if(status!=EXR_OK) return status;
  status=shape_line_copy(f,b,&b->line,b->raw.glyphs,b->raw.glyph_count,0,b->after,0);if(status!=EXR_OK) return status;
  status=line_reserve(f,b,&b->run,b->line.glyph_count+unready);if(status!=EXR_OK) return status;
  memmove(b->run.glyphs+b->line.glyph_count,b->run.glyphs+b->ready,unready*sizeof(*b->run.glyphs));
  if(b->line.glyph_count) memcpy(b->run.glyphs,b->line.glyphs,b->line.glyph_count*sizeof(*b->run.glyphs));
  b->ready=b->line.glyph_count;b->run.glyph_count=b->ready+unready;b->cluster_start=b->ready+extra_cluster;b->before=0;
  for(i=b->raw.glyph_count;i;i--) if(!exr_ot_transparent(b->raw.glyphs[i-1].codepoint)) { b->before=b->raw.glyphs[i-1].codepoint;break; }
  b->line.glyph_count=0;b->line_ready=0;reset_line_scan(b);return EXR_OK;
}
/* Max-content uses the same measured/shaped segments, retaining only joining
   context and one previous glyph. A long paragraph does not become one huge
   provisional line or a second full glyph snapshot. */
static exr_status measure_unwrapped(flow *f,exr_line_buffer *b) {
  size_t i,count=b->ready;
  for(i=0;i<count;i++) {
    exr_glyph *g=&b->run.glyphs[i]; float advance;
    if(!(i&255) && exr_control_cancel(&f->config->control,f->error)!=EXR_OK) return EXR_CANCELLED;
    if(g->boundaries&EXR_BOUNDARY_MANDATORY) {
      f->intrinsic_extent=fmax(f->intrinsic_extent,f->x+b->measure_width-b->measure_trailing+f->inline_end_inset);
      b->measure_width=b->measure_trailing=0; b->measure_has_last=0;
    }
    if(exr_font_size(&f->font->faces[g->font_index],g->size)) return exr_fail(f->error,EXR_FONT,"Cannot size intrinsic line font");
    if(f->first_line) { b->measure_width+=fmaxf(0,f->paragraph->indent); f->first_line=0; }
    advance=g->advance+line_kern(f,b->measure_has_last ? &b->measure_last : NULL,g);
    b->measure_width+=advance;
    if(g->codepoint==' ' || g->codepoint=='\t') b->measure_trailing+=advance;
    else if(!(g->flags&EXR_GLYPH_HIDDEN)) b->measure_trailing=0;
    b->measure_last=*g; b->measure_has_last=1;
  }
  if(b->finishing) f->intrinsic_extent=fmax(f->intrinsic_extent,f->x+b->measure_width-b->measure_trailing+f->inline_end_inset);
  if(count) memmove(b->run.glyphs,b->run.glyphs+count,(b->run.glyph_count-count)*sizeof(*b->run.glyphs));
  b->run.glyph_count-=count; b->cluster_start-=count; b->ready=0; b->raw.glyph_count=0;
  return EXR_OK;
}
exr_status exr_inline_drain(flow *f, exr_line_buffer *b) {
  if (!b->initialized) reset_line_scan(b);
  if(f->intrinsic==2) return measure_unwrapped(f,b);
  for (;;) {
    if (!b->line_end) {
      float indent = f->first_line ? f->paragraph->indent : 0;
      while (b->scan < b->ready) {
        size_t i = b->scan;
        exr_glyph *g = &b->run.glyphs[i];
        float advance,available=fmaxf(1,f->width-indent);
        if (exr_font_size(&f->font->faces[g->font_index], g->size))
          return exr_fail(f->error, EXR_FONT, "Cannot size line font");
        if(f->floats->count && !f->intrinsic) {
          float x,width,next; exr_status status=line_metric(f,g,&b->scan_ascent,&b->scan_descent,&b->scan_leading);
          if(status!=EXR_OK) return status;
          exr_flow_area(f,f->y,fmaxf(b->scan_leading,b->scan_ascent+b->scan_descent),&x,&width,&next);
          available=fmaxf(1,width-indent);
        }
        if (i && (g->boundaries & EXR_BOUNDARY_MANDATORY)) {
          b->line_end = i; b->forced = 1; b->final = 0; break;
        }
        if (i && (g->boundaries & EXR_BOUNDARY_GRAPHEME) && !(g->boundaries & EXR_BOUNDARY_GLUE)) {
          b->emergency = i;
          if (g->boundaries & EXR_BOUNDARY_LINE) b->soft = i;
        }
        if(f->intrinsic==1 && i && b->soft==i) { b->line_end=i; b->forced=b->final=0; break; }
        advance = g->advance + line_kern(f, i ? g - 1 : NULL, g);
        if (!f->intrinsic && i && b->scan_width + advance > available &&
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
        if(wait_for_word(b)) return EXR_OK;
        status = fit_line(f, b);
        if(status==EXR_REFLOW) { exr_inline_rescan(b); continue; }
        if (status != EXR_OK) return status;
      }
      end = b->line.glyph_count;
      if (end) {
        float old_x=f->x,old_width=f->width;
        f->x=b->line_x; f->width=b->line_width;
        status = exr_flow_emit_line(f, b->line.glyphs, end, b->forced, b->final);
        f->x=old_x; f->width=old_width;
        if (status != EXR_OK) return status;
      }
      if(b->rewrite) {
        status=replacement_carry(f,b);if(status!=EXR_OK) return status;
        continue;
      }
      if(b->raw_end) prune_edits(b,b->raw.glyphs[b->raw_end-1].end);
      advance_mapped_edits(b,b->raw_end);
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
exr_status exr_inline_pending(flow *f,exr_line_buffer *b,float *width) {
  size_t i; exr_status status=measure_line_cluster(f,b); *width=0;
  if(status==EXR_OK) status=shape_line_segment(f,b,0);
  if(status==EXR_OK) status=exr_inline_drain(f,b);
  if(status!=EXR_OK) return status;
  for(i=0;i<b->ready;i++) {
    exr_glyph *g=&b->run.glyphs[i];
    if(exr_font_size(&f->font->faces[g->font_index],g->size)) return EXR_FONT;
    *width+=g->advance+line_kern(f,i ? g-1 : NULL,g);
  }
  return EXR_OK;
}
exr_status exr_inline_break(flow *f,exr_line_buffer *b) {
  if(!b->ready) return EXR_OK;
  b->line_end=b->ready; b->line_ready=0; b->forced=b->final=0;
  return exr_inline_drain(f,b);
}
typedef struct { flow *f; size_t node, at, start; } inline_text_cursor;
static int following_inline_scalar(void *context, uint32_t *cp) {
  inline_text_cursor *c = context;
  while (c->node != SIZE_MAX) {
    const exr_node *n = &c->f->doc->nodes[c->node];
    if (c->at<n->end && exr_ruby_node(c->f->doc,c->node)) { c->start=c->at; c->at=n->end; *cp=0xfffc; return 1; }
    if (c->at < n->end) {
      c->start=c->at;
      return exr_next(c->f->doc->text, n->end, &c->at, cp);
    }
    c->node = next_text(c->f, following(c->f, c->node));
    if (c->node != SIZE_MAX) c->at = c->f->doc->nodes[c->node].start;
  }
  return 0;
}
static const char *node_language(const flow *f,size_t node) {
  for(;node!=SIZE_MAX;node=f->doc->nodes[node].parent) {
    const exr_node *n=&f->doc->nodes[node]; const char *value=exr_node_attribute(n,"http://www.w3.org/XML/1998/namespace|lang");
    if(!value) value=exr_node_attribute(n,"xml:lang");
    if(!value) value=exr_node_attribute(n,"lang");
    if(value) return value;
  }
  return f->doc->language ? f->doc->language : "";
}
static int word_joiner(uint32_t cp) { return cp=='\'' || cp==0x2019 || cp=='-' || cp==0x2013 || cp==0xb7; }
static int word_after(inline_text_cursor cursor) {
  uint32_t cp; return following_inline_scalar(&cursor,&cp) && exr_hyphen_word_kind(cp)!=0;
}
static size_t word_index(const size_t *offsets,size_t count,size_t byte) {
  size_t lo=0,hi=count+1;
  while(lo<hi) { size_t mid=lo+(hi-lo)/2;if(offsets[mid]<byte) lo=mid+1;else hi=mid; }
  return lo<=count && offsets[lo]==byte ? lo : SIZE_MAX;
}
static exr_status word_points(flow *f,exr_line_buffer *b,const char key[256]) {
  char text[1024];unsigned char points[1025];size_t bytes=0,count=0,offsets[257],sources[257];
  inline_text_cursor cursor={f,b->word_node,b->word_start,0};uint32_t cp;int numeric=0,previous=0;
  exr_hyphen_word *w=b->word;exr_status status;
  w->start=b->word_start;w->until=b->word_start;w->count=w->edit_count=0;memcpy(w->language,key,strlen(key)+1);
  while(following_inline_scalar(&cursor,&cp)) {
    unsigned kind=exr_hyphen_word_kind(cp);size_t size=cursor.at-cursor.start;
    if(!kind && !(word_joiner(cp) && previous && word_after(cursor))) break;
    if(count==256 || size>sizeof(text)-bytes) { w->until=SIZE_MAX;return EXR_OK; }
    offsets[count]=bytes;sources[count++]=cursor.start;
    memcpy(text+bytes,f->doc->text+cursor.start,size);bytes+=size;w->until=cursor.at;
    numeric|=kind==3 || (count==1 && kind!=1);previous=!!kind;
  }
  if(numeric || !bytes) return EXR_OK;
  if(!exr_hyphenator_replacements(f->hyphenator)) {
    status=exr_hyphenator_breaks(f->hyphenator,key,text,bytes,points,&f->config->control,f->error);
    if(status!=EXR_OK) return status;
    for(bytes=0;bytes<count;bytes++) if(points[offsets[bytes]]) w->points[w->count++]=sources[bytes];
  } else {
    exr_hyphenation *result=NULL;const exr_hyphen_break *items;size_t n,i;
    offsets[count]=bytes;sources[count]=w->until;
    status=exr_hyphenator_query(f->hyphenator,key,text,bytes,&f->config->control,&result,f->error);if(status!=EXR_OK) return status;
    items=exr_hyphenation_breaks(result,&n);
    for(i=0;i<n;i++) {
      const exr_hyphen_break *item=&items[i];size_t at=word_index(offsets,count,item->point);
      if(at==SIZE_MAX) continue;
      status=line_work(f,24);if(status!=EXR_OK) break;
      w->points[w->count++]=sources[at];
      if(item->start!=item->point || item->end!=item->point || item->before_size || item->after_size) {
        size_t first=word_index(offsets,count,item->start),last=word_index(offsets,count,item->end);exr_hyphen_edit *edit;
        if(first==SIZE_MAX || last==SIZE_MAX) { status=exr_fail(f->error,EXR_FORMAT,"Unmapped replacement source range");break; }
        status=edit_reserve(f,b,&w->edits,&w->edit_capacity,w->edit_count+1);if(status!=EXR_OK) break;
        edit=&w->edits[w->edit_count++];memset(edit,0,sizeof(*edit));
        edit->point=sources[at];edit->start=sources[first];edit->end=sources[last];edit->word_start=w->start;edit->until=w->until;
        edit->before=item->before_size;edit->after=item->after_size;
        memcpy(edit->text,item->before,item->before_size);memcpy(edit->text+item->before_size+1,item->after,item->after_size);
      }
    }
    exr_hyphenation_free(result);if(status!=EXR_OK) return status;
  }
  return EXR_OK;
}
static exr_status hyphenate_scalar(flow *f,exr_line_buffer *b,exr_glyph *g) {
  unsigned kind=exr_hyphen_word_kind(g->codepoint); size_t i; char key[256];
  inline_text_cursor after={f,g->node,g->end,0}; exr_status status;
  if(!kind && !(word_joiner(g->codepoint) && b->in_word && exr_hyphen_word_kind(b->previous_scalar) && word_after(after))) {
    b->in_word=0; if(b->word) b->word->until=0; return EXR_OK;
  }
  if(!b->in_word) { b->word_node=g->node; b->word_start=g->start; b->in_word=1; }
  if(g->start<b->blocked_until || f->styles[g->node].hyphens!=EXR_HYPHENS_AUTO || !(g->boundaries&EXR_BOUNDARY_GRAPHEME) ||
      (g->boundaries&EXR_BOUNDARY_GLUE) || !exr_hyphen_language(node_language(f,g->node),key)) return EXR_OK;
  if(!b->word) {
    if(sizeof(*b->word)>16*1024*1024-line_payload(b)) return exr_fail(f->error,EXR_LIMIT,"Hyphenation word exceeds line budget");
    b->word=calloc(1,sizeof(*b->word)); if(!b->word) return exr_fail(f->error,EXR_MEMORY,"Hyphenation word cache allocation failed"); }
  if(b->word->start==b->word_start && b->word->until==SIZE_MAX) return EXR_OK;
  if(b->word->start!=b->word_start || b->word->until<=g->start || strcmp(b->word->language,key)) {
    status=word_points(f,b,key); if(status!=EXR_OK) return status;
  }
  for(i=0;i<b->word->count;i++) if(b->word->points[i]==g->start) {
    size_t j;g->boundaries|=EXR_BOUNDARY_AUTO_HYPHEN;
    for(j=0;j<b->word->edit_count;j++) if(b->word->edits[j].point==g->start) {
      if(!edit_at(b,g->start)) {
        status=edit_reserve(f,b,&b->edits,&b->edit_capacity,b->edit_count+1);if(status!=EXR_OK) return status;
        b->edits[b->edit_count++]=b->word->edits[j];
      }
      break;
    }
    break;
  }
  return EXR_OK;
}
exr_status exr_inline_feed(flow *f, exr_line_buffer *b, exr_glyph g) {
  exr_status status;
  if (!b->initialized) reset_line_scan(b);
  {
    inline_text_cursor cursor = {f, g.node, g.end,0};
    g.boundaries = exr_text_step(&b->text, g.codepoint, following_inline_scalar, &cursor);
  }
  if(b->previous_scalar==0xad && f->styles[b->previous_node].hyphens==EXR_HYPHENS_NONE) g.boundaries&=~EXR_BOUNDARY_LINE;
  if(f->hyphenator && f->intrinsic!=2 && !(g.flags&EXR_GLYPH_RUBY_ITEM)) {
    status=hyphenate_scalar(f,b,&g); if(status!=EXR_OK) return status;
  } else if(f->hyphenator) { b->in_word=0; if(b->word) b->word->until=0; }
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
  b->previous_scalar=g.codepoint; b->previous_node=g.node;
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
  b->measure_width=b->measure_trailing=0; b->measure_has_last=0;
  b->edit_count=b->blocked_until=0;
  b->in_word=0; b->previous_scalar=0; b->previous_node=0; if(b->word) b->word->until=0;
  reset_line_scan(b);
  return EXR_OK;
}
void exr_inline_buffer_clear(exr_line_buffer *b) {
  free(b->run.glyphs); free(b->raw.glyphs); free(b->line.glyphs);
  if(b->word) free(b->word->edits);
  free(b->word);free(b->edits);
  memset(b, 0, sizeof(*b));
}
