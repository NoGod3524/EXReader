/* SPDX-License-Identifier: GPL-3.0-only */
#include "layout_internal.h"

typedef struct {
  exr_layout *layout, *assets;
  const exr_document *doc;
  const exr_style *styles, *paragraph;
  const exr_layout_config *config;
  exr_font *font;
  exr_error *error;
  float x, width, y, bottom_inset;
  size_t pending;
  int first_line, paginate, force_break, table_depth;
} flow;
static float used(exr_length l, float width) {
  return l.value < 0 ? 0 : l.percent ? l.value * width : l.value;
}
static float top(const flow *f) { return f->paginate ? f->layout->options.margin : 0; }
static float bottom(const flow *f) {
  return f->layout->options.height - f->layout->options.margin - f->bottom_inset;
}
static float room(const flow *f) {
  return f->layout->options.height - 2 * f->layout->options.margin - f->bottom_inset;
}
static exr_status fail(flow *f, exr_status code, const char *message) {
  return exr_fail(f->error, code, "%s", message);
}
static exr_status page(flow *f, float height, size_t offset) {
  exr_layout *l = f->layout;
  exr_page *p;
  if (f->paginate && height > room(f) + 0.01f)
    return fail(f, EXR_LIMIT, "Unbreakable content exceeds page height");
  if (!l->page_count || (f->paginate && (f->force_break || f->y + height > bottom(f)))) {
    if (l->page_count && f->y <= top(f) && !f->force_break)
      return EXR_OK;
    if (!exr_grow((void **)&l->pages, &l->page_cap, l->page_count + 1, sizeof(*l->pages)))
      return EXR_MEMORY;
    p = &l->pages[l->page_count++];
    memset(p, 0, sizeof(*p));
    p->start = p->end = offset == SIZE_MAX ? 0 : offset;
    p->line_start = l->line_count;
    f->y = top(f);
  }
  f->force_break = 0;
  return EXR_OK;
}
static float glyph_kern(flow *f, const exr_glyph *previous, const exr_glyph *g) {
  if (!previous || previous->size != g->size || previous->flags != g->flags)
    return 0;
  return exr_kern(f->font, previous->glyph, g->glyph);
}
static exr_status flush(flow *f) {
  exr_layout *l = f->layout;
  size_t start = f->pending;
  while (start < l->glyph_count) {
    size_t i, split = SIZE_MAX, end, spaces = 0;
    float indent = f->first_line ? f->paragraph->indent : 0;
    float available = fmaxf(1, f->width - indent), width = 0, ascent = 0, descent = 0, height = 0,
          x, extra = 0;
    exr_line *line;
    exr_status s;
    for (i = start; i < l->glyph_count; i++) {
      exr_glyph *g = &l->glyphs[i];
      float advance;
      if (exr_font_size(f->font, g->size))
        return fail(f, EXR_FONT, "Cannot size font");
      if (i > start && exr_break_before(l->glyphs[i - 1].codepoint, g->codepoint))
        split = i;
      advance = g->advance + glyph_kern(f, i == start ? NULL : &l->glyphs[i - 1], g);
      if (i > start && width + advance > available) {
        if (split != SIZE_MAX)
          i = split;
        else {
          size_t candidate = i;
          while (candidate > start && exr_cluster_continuation(l->glyphs[candidate - 1].codepoint,
                                                               l->glyphs[candidate].codepoint))
            candidate--;
          if (candidate == start) {
            width += advance;
            continue;
          }
          i = candidate;
        }
        break;
      }
      width += advance;
    }
    end = i;
    width = 0;
    for (i = start; i < end; i++) {
      exr_glyph *g = &l->glyphs[i];
      if (exr_font_size(f->font, g->size))
        return EXR_FONT;
      width += g->advance + glyph_kern(f, i == start ? NULL : &l->glyphs[i - 1], g);
      ascent = fmaxf(ascent, (float)f->font->face->size->metrics.ascender / 64);
      descent = fmaxf(descent, -(float)f->font->face->size->metrics.descender / 64);
      height = fmaxf(height, g->line_height);
      if (g->codepoint == ' ')
        spaces++;
    }
    height = fmaxf(height, ascent + descent);
    s = page(f, height, l->glyphs[start].start);
    if (s != EXR_OK)
      return s;
    if (!exr_grow((void **)&l->lines, &l->line_cap, l->line_count + 1, sizeof(*l->lines)))
      return EXR_MEMORY;
    x = f->x + indent;
    if (f->paragraph->align == 1)
      x += fmaxf(0, available - width) / 2;
    if (f->paragraph->align == 2)
      x += fmaxf(0, available - width);
    if (f->paragraph->align == 3 && end < l->glyph_count && spaces)
      extra = fmaxf(0, available - width) / (float)spaces;
    line = &l->lines[l->line_count++];
    *line = (exr_line){0};
    line->start = l->glyphs[start].start;
    line->end = l->glyphs[end - 1].end;
    line->glyph_start = start;
    line->glyph_count = end - start;
    line->page = l->page_count - 1;
    line->y = f->y;
    line->x = x;
    line->width = width + extra * (float)spaces;
    line->height = height;
    l->pages[line->page].line_count++;
    l->pages[line->page].end = line->end;
    for (i = start; i < end; i++) {
      exr_glyph *g = &l->glyphs[i];
      if (exr_font_size(f->font, g->size))
        return EXR_FONT;
      x += glyph_kern(f, i == start ? NULL : &l->glyphs[i - 1], g);
      g->x = x;
      g->baseline = f->y + ascent + (height - ascent - descent) / 2;
      g->page = line->page;
      g->clip_left = f->x;
      g->clip_right = f->x + f->width;
      x += g->advance;
      if (g->codepoint == ' ')
        x += extra;
    }
    f->y += height;
    f->first_line = 0;
    start = end;
  }
  f->pending = l->glyph_count;
  return EXR_OK;
}
static exr_status text(flow *f, size_t node) {
  exr_layout *l = f->layout;
  const exr_node *n = &f->doc->nodes[node];
  const exr_style *s = &f->styles[node];
  size_t pos = n->start;
  if (pos == SIZE_MAX)
    return EXR_OK;
  if (exr_font_size(f->font, s->font_size))
    return EXR_FONT;
  while (pos < n->end) {
    exr_glyph *g;
    uint32_t cp;
    size_t start = pos;
    if (!exr_next(f->doc->text, n->end, &pos, &cp))
      return EXR_ENCODING;
    if (++f->assets->work_glyphs > EXR_MAX_ITEMS ||
        !exr_grow((void **)&l->glyphs, &l->glyph_cap, l->glyph_count + 1, sizeof(*g)))
      return EXR_LIMIT;
    g = &l->glyphs[l->glyph_count++];
    memset(g, 0, sizeof(*g));
    g->start = start;
    g->end = pos;
    g->node = node;
    g->codepoint = cp;
    g->size = s->font_size;
    g->color = s->color;
    g->flags = s->flags;
    g->line_height = s->leading_relative ? s->leading * s->font_size : s->leading;
    g->glyph = FT_Get_Char_Index(f->font->face, cp == '\t' ? ' ' : cp);
    if (exr_measure(f->font, g->glyph, g->flags, &g->advance))
      return EXR_FONT;
    if (cp == '\t')
      g->advance *= 4;
  }
  return EXR_OK;
}
static exr_box *box(flow *f, size_t node, size_t p, float x, float y, float width, float height,
                    exr_box_kind kind) {
  exr_layout *l = f->layout;
  const exr_style *s = &f->styles[node];
  exr_box *b;
  if (l->box_count >= EXR_MAX_ITEMS ||
      !exr_grow((void **)&l->boxes, &l->box_cap, l->box_count + 1, sizeof(*b)))
    return NULL;
  b = &l->boxes[l->box_count++];
  memset(b, 0, sizeof(*b));
  b->kind = kind;
  b->node = node;
  b->page = p;
  b->resource = SIZE_MAX;
  b->start = f->doc->nodes[node].start;
  b->end = f->doc->nodes[node].end;
  b->x = x;
  b->y = y;
  b->width = width;
  b->height = fmaxf(0, height);
  b->background = s->background;
  b->border_color = s->border_color;
  b->border_width = s->border_style ? s->border_width : 0;
  return b;
}
static exr_status image_asset(flow *f, size_t node, size_t *resource, const exr_bitmap **bitmap) {
  exr_layout *l = f->assets;
  size_t target, i, size;
  void *data = NULL;
  exr_error ignored = {0};
  exr_bitmap decoded = {0};
  exr_status status;
  const exr_node *n = &f->doc->nodes[node];
  const char *src = exr_node_attribute(n, "src");
  *bitmap = NULL;
  *resource = SIZE_MAX;
  if (!src)
    src = exr_node_attribute(n, "http://www.w3.org/1999/xlink|href");
  if (!src ||
      exr_document_resolve(f->doc, n->chapter, src, resource, &target, &ignored) != EXR_OK ||
      *resource == SIZE_MAX)
    return EXR_OK;
  for (i = 0; i < l->image_count; i++)
    if (l->images[i].resource == *resource) {
      *bitmap = &l->images[i].bitmap;
      return EXR_OK;
    }
  status = exr_document_resource(f->doc, *resource, &data, &size, &ignored);
  if (status == EXR_OK && f->config->decode_image) {
    exr_bitmap supplied = {0};
    size_t row;
    status = f->config->decode_image(f->config->image_context, &f->doc->resources[*resource], data,
                                     size, &supplied, &ignored);
    if (status == EXR_OK) {
      if (!supplied.pixels || supplied.channels != 4 || !supplied.width || !supplied.height ||
          supplied.width > 8192 || supplied.height > 8192 || supplied.stride < supplied.width * 4 ||
          (size_t)supplied.width * supplied.height > 16 * 1024 * 1024 ||
          (size_t)(supplied.height - 1) > (SIZE_MAX - supplied.width * 4) / supplied.stride)
        status =
            exr_fail(&ignored, EXR_ARGUMENT, "Host image decoder returned an invalid RGBA bitmap");
      else {
        decoded = supplied;
        decoded.stride = supplied.width * 4;
        decoded.pixels = malloc((size_t)decoded.stride * decoded.height);
        if (!decoded.pixels)
          status = EXR_MEMORY;
        else
          for (row = 0; row < decoded.height; row++)
            memcpy(decoded.pixels + row * decoded.stride, supplied.pixels + row * supplied.stride,
                   decoded.stride);
      }
    }
    f->config->release_image(f->config->image_context, &supplied);
  } else if (status == EXR_OK)
    status = exr_image_decode(data, size, &decoded, &ignored);
  exr_free(data);
  if (status == EXR_FORMAT)
    return EXR_OK;
  if (status != EXR_OK)
    return fail(f, status, ignored.message[0] ? ignored.message : "Image decoding failed");
  size = (size_t)decoded.stride * decoded.height;
  if (size > 64 * 1024 * 1024 - l->image_bytes ||
      !exr_grow((void **)&l->images, &l->image_cap, l->image_count + 1, sizeof(*l->images))) {
    exr_bitmap_free(&decoded);
    return fail(f, EXR_LIMIT, "Decoded image cache exceeds 64 MiB");
  }
  l->images[l->image_count].resource = *resource;
  l->images[l->image_count].bitmap = decoded;
  *bitmap = &l->images[l->image_count++].bitmap;
  l->image_bytes += size;
  return EXR_OK;
}
static exr_status image(flow *f, size_t node, float x, float width) {
  const exr_style *s = &f->styles[node];
  const exr_bitmap *bitmap;
  size_t resource;
  float w, h, scale;
  exr_box *b;
  exr_status status = image_asset(f, node, &resource, &bitmap);
  if (status != EXR_OK)
    return status;
  w = bitmap ? (float)bitmap->width : 160;
  h = bitmap ? (float)bitmap->height : 80;
  scale = 1;
  if (s->width.value >= 0)
    scale = used(s->width, width) / w;
  if (s->height.value >= 0) {
    float by_height = used(s->height, room(f)) / h;
    scale = s->width.value >= 0 ? fminf(scale, by_height) : by_height;
  }
  w *= scale;
  h *= scale;
  if (w <= 0 || h <= 0)
    return EXR_OK;
  scale = fminf(1, fminf(width / w, room(f) / h));
  if (s->max_width.value >= 0)
    scale = fminf(scale, used(s->max_width, width) / w);
  w *= scale;
  h *= scale;
  status = page(f, h, f->doc->nodes[node].start);
  if (status != EXR_OK)
    return status;
  if (s->margin[3].value < 0)
    x += (width - w) / (s->margin[1].value < 0 ? 2 : 1);
  else if (s->align == 1)
    x += (width - w) / 2;
  else if (s->align == 2)
    x += width - w;
  b = box(f, node, f->layout->page_count - 1, x, f->y, w, h, EXR_BOX_IMAGE);
  if (!b)
    return EXR_MEMORY;
  b->resource = resource;
  if (!bitmap) {
    b->flags = 1;
    b->background = 0xeeeeeeff;
    b->border_width = 1;
    b->border_color = 0x888888ff;
  }
  f->y += h;
  f->layout->pages[f->layout->page_count - 1].end = f->doc->nodes[node].end;
  return EXR_OK;
}
static exr_status node(flow *f, size_t index, float x, float width);
typedef struct {
  size_t node, row, column, colspan, rowspan;
  exr_layout *layout;
  float height;
} cell;
static size_t span(const exr_node *n, const char *attr, size_t limit) {
  const char *s = exr_node_attribute(n, attr);
  char *end;
  unsigned long value;
  if (!s)
    return 1;
  value = strtoul(s, &end, 10);
  if (*end || end == s || !value)
    return 1;
  return value > limit ? limit : (size_t)value;
}
static int rows(flow *f, size_t parent, size_t **out, size_t *count, size_t *capacity) {
  size_t child;
  for (child = f->doc->nodes[parent].first_child; child != SIZE_MAX;
       child = f->doc->nodes[child].next_sibling) {
    if (f->styles[child].display == EXR_CSS_NONE)
      continue;
    if (f->styles[child].display == EXR_CSS_ROW) {
      if (*count >= 4096 || !exr_grow((void **)out, capacity, *count + 1, sizeof(size_t)))
        return 0;
      (*out)[(*count)++] = child;
    } else if (f->doc->nodes[child].kind != EXR_NODE_TABLE && !rows(f, child, out, count, capacity))
      return 0;
  }
  return 1;
}
static exr_status copy_cell(flow *f, const cell *c, float x, float y, float height) {
  exr_layout *l = f->layout, *from = c->layout;
  size_t i, offset = l->glyph_count, p = l->page_count - 1;
  if (from->glyph_count > EXR_MAX_ITEMS - l->glyph_count ||
      !exr_grow((void **)&l->glyphs, &l->glyph_cap, l->glyph_count + from->glyph_count,
                sizeof(exr_glyph)) ||
      !exr_grow((void **)&l->lines, &l->line_cap, l->line_count + from->line_count,
                sizeof(exr_line)) ||
      !exr_grow((void **)&l->boxes, &l->box_cap, l->box_count + from->box_count, sizeof(exr_box)))
    return EXR_LIMIT;
  for (i = 0; i < from->glyph_count; i++) {
    exr_glyph v = from->glyphs[i];
    v.x += x;
    v.baseline += y;
    v.clip_left += x;
    v.clip_right += x;
    v.page = p;
    l->glyphs[l->glyph_count++] = v;
  }
  for (i = 0; i < from->line_count; i++) {
    exr_line v = from->lines[i];
    v.x += x;
    v.y += y;
    v.page = p;
    v.glyph_start += offset;
    l->lines[l->line_count++] = v;
    l->pages[p].line_count++;
    if (v.end > l->pages[p].end)
      l->pages[p].end = v.end;
  }
  for (i = 0; i < from->box_count; i++) {
    exr_box v = from->boxes[i];
    v.x += x;
    v.y += y;
    v.page = p;
    if (v.node == c->node && v.kind == EXR_BOX_CELL)
      v.height = height;
    l->boxes[l->box_count++] = v;
  }
  f->pending = l->glyph_count;
  return EXR_OK;
}
static exr_status table(flow *f, size_t index, float x, float width) {
  size_t *row = NULL, nrows = 0, rowcap = 0, occupied[64] = {0};
  size_t i, j, ncols = 0, count = 0, capacity = 0;
  cell *cells = NULL;
  float *heights = NULL, *positions = NULL;
  exr_status result = EXR_OK;
  if (f->table_depth >= 8)
    return fail(f, EXR_LIMIT, "Nested table limit exceeded");
  if (!rows(f, index, &row, &nrows, &rowcap)) {
    result = EXR_LIMIT;
    goto done;
  }
  if (!nrows)
    goto done;
  for (i = 0; i < nrows; i++) {
    size_t child, col = 0;
    for (child = f->doc->nodes[row[i]].first_child; child != SIZE_MAX;
         child = f->doc->nodes[child].next_sibling) {
      size_t cs, rs, k;
      cell *c;
      if (f->styles[child].display != EXR_CSS_CELL)
        continue;
      cs = span(&f->doc->nodes[child], "colspan", 65);
      rs = span(&f->doc->nodes[child], "rowspan", nrows - i);
      for (;;) {
        while (col < 64 && occupied[col] > i)
          col++;
        if (cs > 64 - col) {
          result = EXR_LIMIT;
          goto done;
        }
        for (k = 0; k < cs && occupied[col + k] <= i; k++) {
        }
        if (k == cs)
          break;
        col += k + 1;
      }
      if (count >= 4096 || !exr_grow((void **)&cells, &capacity, count + 1, sizeof(*cells))) {
        result = EXR_LIMIT;
        goto done;
      }
      c = &cells[count++];
      *c = (cell){0};
      c->node = child;
      c->row = i;
      c->column = col;
      c->colspan = cs;
      c->rowspan = rs;
      for (k = 0; k < cs; k++)
        occupied[col + k] = i + rs;
      col += cs;
      if (col > ncols)
        ncols = col;
    }
  }
  if (!ncols)
    goto done;
  heights = calloc(nrows, sizeof(float));
  positions = calloc(nrows + 1, sizeof(float));
  if (!heights || !positions) {
    result = EXR_MEMORY;
    goto done;
  }
  for (i = 0; i < count; i++) {
    flow child = *f;
    cell *c = &cells[i];
    c->layout = calloc(1, sizeof(exr_layout));
    if (!c->layout) {
      result = EXR_MEMORY;
      goto done;
    }
    c->layout->options = f->layout->options;
    child.layout = c->layout;
    child.y = 0;
    child.pending = 0;
    child.force_break = 0;
    child.paginate = 0;
    child.bottom_inset = 0;
    child.table_depth++;
    result = node(&child, c->node, 0, width * (float)c->colspan / (float)ncols);
    if (result == EXR_OK)
      result = flush(&child);
    if (result != EXR_OK)
      goto done;
    c->height = child.y;
    if (c->rowspan == 1)
      heights[c->row] = fmaxf(heights[c->row], c->height);
  }
  for (i = 0; i < count; i++) {
    cell *c = &cells[i];
    float total = 0;
    for (j = c->row; j < c->row + c->rowspan; j++)
      total += heights[j];
    if (total < c->height)
      heights[c->row + c->rowspan - 1] += c->height - total;
  }
  for (i = 0; i < nrows; i++)
    positions[i + 1] = positions[i] + heights[i];
  for (i = 0; i < nrows;) {
    size_t end = i + 1, old;
    do {
      old = end;
      for (j = 0; j < count; j++)
        if (cells[j].row >= i && cells[j].row < end && cells[j].row + cells[j].rowspan > end)
          end = cells[j].row + cells[j].rowspan;
    } while (old != end);
    result = page(f, positions[end] - positions[i], f->doc->nodes[row[i]].start);
    if (result != EXR_OK)
      goto done;
    for (j = 0; j < count; j++)
      if (cells[j].row >= i && cells[j].row < end) {
        cell *c = &cells[j];
        result = copy_cell(f, c, x + width * (float)c->column / (float)ncols,
                           f->y + positions[c->row] - positions[i],
                           positions[c->row + c->rowspan] - positions[c->row]);
        if (result != EXR_OK)
          goto done;
      }
    f->y += positions[end] - positions[i];
    i = end;
  }
done:
  for (i = 0; i < count; i++)
    exr_layout_free(cells[i].layout);
  free(cells);
  free(row);
  free(heights);
  free(positions);
  if (result != EXR_OK && (!f->error || !f->error->message[0]))
    return fail(f, result, "Table layout limit exceeded");
  return result;
}
static exr_status node(flow *f, size_t index, float x, float width) {
  const exr_node *n = &f->doc->nodes[index];
  const exr_style *s = &f->styles[index], *old_paragraph = f->paragraph;
  size_t child, first_page;
  float outer_x, outer_width, content_width, first_y, old_x = f->x, old_width = f->width;
  float ml, mr, pl, pr, pt, pb;
  float border = s->border_style ? s->border_width : 0;
  int is_block;
  exr_status result;
  if (s->display == EXR_CSS_NONE || n->start == SIZE_MAX)
    return EXR_OK;
  if (n->kind == EXR_NODE_TEXT)
    return text(f, index);
  if (n->kind == EXR_NODE_BREAK)
    return flush(f);
  is_block = s->display != EXR_CSS_INLINE || n->kind == EXR_NODE_IMAGE;
  if (!is_block) {
    for (child = n->first_child; child != SIZE_MAX; child = f->doc->nodes[child].next_sibling) {
      result = node(f, child, x, width);
      if (result != EXR_OK)
        return result;
    }
    return EXR_OK;
  }
  result = flush(f);
  if (result != EXR_OK)
    return result;
  if (s->before && f->layout->page_count && f->y > top(f))
    f->force_break = 1;
  ml = used(s->margin[3], width);
  mr = used(s->margin[1], width);
  pl = used(s->padding[3], width) + border;
  pr = used(s->padding[1], width) + border;
  pt = used(s->padding[0], width) + border;
  pb = used(s->padding[2], width) + border;
  content_width = width - ml - mr - pl - pr;
  if (s->width.value >= 0 && n->kind != EXR_NODE_IMAGE)
    content_width = fminf(content_width, used(s->width, width));
  if (s->max_width.value >= 0 && n->kind != EXR_NODE_IMAGE)
    content_width = fminf(content_width, used(s->max_width, width));
  if (content_width < 1 || !isfinite(content_width))
    return fail(f, EXR_ARGUMENT, "CSS leaves no content width");
  outer_width = content_width + pl + pr;
  outer_x = x + ml;
  if (s->margin[3].value < 0)
    outer_x += fmaxf(0, width - outer_width - mr) / (s->margin[1].value < 0 ? 2 : 1);
  f->y += used(s->margin[0], width);
  result = page(f, pt + pb, n->start);
  if (result != EXR_OK)
    return result;
  first_page = f->layout->page_count - 1;
  first_y = f->y;
  if (f->paginate)
    f->bottom_inset += pb;
  f->y += pt;
  f->x = outer_x + pl;
  f->width = content_width;
  f->paragraph = s;
  f->first_line = 1;
  if (n->kind == EXR_NODE_IMAGE)
    result = image(f, index, f->x, content_width);
  else if (s->display == EXR_CSS_TABLE)
    result = table(f, index, f->x, content_width);
  else {
    result = EXR_OK;
    for (child = n->first_child; child != SIZE_MAX && result == EXR_OK;
         child = f->doc->nodes[child].next_sibling)
      result = node(f, child, f->x, content_width);
  }
  if (result == EXR_OK)
    result = flush(f);
  if (result != EXR_OK)
    return result;
  if (f->paginate) {
    f->y = fminf(f->y, bottom(f));
    f->bottom_inset -= pb;
  }
  f->y += pb;
  if ((s->background & 255) || border > 0 || s->display == EXR_CSS_CELL) {
    size_t p;
    for (p = first_page; p < f->layout->page_count; p++) {
      float y = p == first_page ? first_y : top(f);
      float end = p + 1 == f->layout->page_count ? f->y : bottom(f);
      if (!box(f, index, p, outer_x, y, outer_width, end - y,
               s->display == EXR_CSS_CELL ? EXR_BOX_CELL : EXR_BOX_BLOCK))
        return EXR_MEMORY;
    }
  }
  f->y += used(s->margin[2], width);
  f->x = old_x;
  f->width = old_width;
  f->paragraph = old_paragraph;
  f->first_line = 1;
  if (s->after)
    f->force_break = 1;
  return EXR_OK;
}
static int box_order(const void *a, const void *b) {
  const exr_box *x = a, *y = b;
  if (x->page != y->page)
    return x->page < y->page ? -1 : 1;
  if (x->node != y->node)
    return x->node < y->node ? -1 : 1;
  return (int)x->kind - (int)y->kind;
}
exr_status exr_layout_validate(const exr_layout_config *config, exr_error *e) {
  exr_layout_options o = config->page;
  if ((config->decode_image && !config->release_image) || !isfinite(o.width) ||
      !isfinite(o.height) || !isfinite(o.margin) || !isfinite(o.font_size) ||
      !isfinite(o.line_height) || !isfinite(o.paragraph_spacing) || o.width < 32 || o.height < 32 ||
      o.width > 16384 || o.height > 16384 || o.margin < 0 || o.font_size < 4 || o.font_size > 256 ||
      o.line_height < 1 || o.line_height > 5 || o.paragraph_spacing < 0 ||
      o.paragraph_spacing > 1024 || o.width - 2 * o.margin < o.font_size * 1.5f ||
      o.height - 2 * o.margin < o.font_size * o.line_height)
    return exr_fail(e, EXR_ARGUMENT, "Invalid page geometry or document");
  return EXR_OK;
}
exr_status exr_flow_create(const exr_document *d, exr_font *font, const exr_layout_config *config,
                           exr_layout **out, exr_error *e) {
  exr_layout *l;
  exr_layout_options o = config->page;
  exr_status status;
  flow f = {0};
  size_t i;
  if (!out)
    return exr_fail(e, EXR_ARGUMENT, "Missing layout output");
  *out = NULL;
  if (e)
    memset(e, 0, sizeof(*e));
  if (!d || !font)
    return exr_fail(e, EXR_ARGUMENT, "Missing document or font");
  status = exr_layout_validate(config, e);
  if (status != EXR_OK)
    return status;
  l = calloc(1, sizeof(*l));
  if (!l)
    return EXR_MEMORY;
  l->options = o;
  status = exr_compute_styles(d, config, &l->styles, e);
  if (status != EXR_OK)
    goto bad;
  f.layout = f.assets = l;
  f.doc = d;
  f.styles = l->styles;
  f.paragraph = &l->styles[0];
  f.config = config;
  f.font = font;
  f.error = e;
  f.paginate = 1;
  f.y = o.margin;
  f.x = o.margin;
  f.width = o.width - 2 * o.margin;
  for (i = 0; i < d->chapter_count; i++)
    if (d->chapters[i].in_spine && d->chapters[i].linear) {
      status = node(&f, d->chapters[i].root, o.margin, o.width - 2 * o.margin);
      if (status != EXR_OK)
        goto bad;
    }
  if (!l->page_count) {
    status = exr_fail(e, EXR_FORMAT, "No layout content");
    goto bad;
  }
  l->pages[l->page_count - 1].end = d->size;
  if (l->box_count)
    qsort(l->boxes, l->box_count, sizeof(*l->boxes), box_order);
  for (i = 0; i < l->box_count; i++) {
    exr_page *p = &l->pages[l->boxes[i].page];
    if (!p->box_count)
      p->box_start = i;
    p->box_count++;
  }
  *out = l;
  return EXR_OK;
bad:
  exr_layout_free(l);
  if (e && !e->message[0])
    exr_fail(e, status, "Native flow layout failed");
  return status;
}
