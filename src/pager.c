/* SPDX-License-Identifier: GPL-3.0-only */
#include "flow_internal.h"

typedef struct {
  size_t node, child, position;
  int phase, entered;
  float x, width, old_x, old_width, outer_x, outer_width;
  float pt, pb, first_y, parent_inset;
  const exr_style *old_paragraph;
  exr_table_cursor *table;
} frame;
typedef struct {
  size_t index, bytes;
  exr_layout *layout;
} cached_page;
struct exr_pager {
  flow f;
  exr_layout_config config;
  exr_style *styles;
  exr_layout *assets;
  exr_layout run; /* Current line/carry and the not-yet-closed grapheme only. */
  exr_text_state text;
  frame frames[258];
  size_t depth, chapter, position, emitted;
  size_t cluster_start, ready, scan, soft, emergency, line_end;
  float scan_width;
  int finishing, forced, final, finished, failed, busy;
  int mode; /* Owned sequential output or borrowed cached output. */
  cached_page cache[64]; /* Most recently used first. */
  size_t cache_count, cache_bytes, cache_capacity, cache_budget;
};
static float used(exr_length l, float width) {
  return l.value < 0 ? 0 : l.percent ? l.value * width : l.value;
}
static exr_status failure(exr_pager *p, exr_status status, const char *message) {
  return exr_fail(p->f.error, status, "%s", message);
}
static void reset_scan(exr_pager *p) {
  p->scan = p->line_end = 0;
  p->soft = p->emergency = SIZE_MAX;
  p->scan_width = 0;
}
static float kern(exr_pager *p, size_t index) {
  const exr_glyph *g = &p->run.glyphs[index], *before;
  if (!index)
    return 0;
  before = g - 1;
  if ((g->flags | before->flags) & EXR_GLYPH_HIDDEN ||
      g->font_index != before->font_index || g->size != before->size ||
      (g->flags & 3) != (before->flags & 3))
    return 0;
  return exr_kern(&p->f.font->faces[g->font_index], before->glyph, g->glyph);
}
static exr_status measure_cluster(exr_pager *p) {
  flow f = p->f;
  exr_status status;
  if (p->cluster_start == p->run.glyph_count)
    return EXR_OK;
  f.layout = &p->run;
  status = exr_flow_cluster(&f, p->cluster_start, p->run.glyph_count);
  if (status == EXR_OK)
    p->ready = p->cluster_start = p->run.glyph_count;
  return status;
}
static exr_status drain(exr_pager *p) {
  flow *f = &p->f;
  exr_layout *l = f->layout;
  for (;;) {
    if (!p->line_end) {
      float indent = f->first_line ? f->paragraph->indent : 0;
      float available = fmaxf(1, f->width - indent);
      while (p->scan < p->ready) {
        size_t i = p->scan;
        exr_glyph *g = &p->run.glyphs[i];
        float advance;
        if (exr_font_size(&f->font->faces[g->font_index], g->size))
          return failure(p, EXR_FONT, "Cannot size line font");
        if (i && (g->boundaries & EXR_BOUNDARY_MANDATORY)) {
          p->line_end = i;
          p->forced = 1;
          p->final = 0;
          break;
        }
        if (i && (g->boundaries & EXR_BOUNDARY_GRAPHEME) &&
            !(g->boundaries & EXR_BOUNDARY_GLUE)) {
          p->emergency = i;
          if (g->boundaries & EXR_BOUNDARY_LINE)
            p->soft = i;
        }
        advance = g->advance + kern(p, i);
        if (i && p->scan_width + advance > available &&
            (p->soft != SIZE_MAX || p->emergency != SIZE_MAX)) {
          p->line_end = p->soft != SIZE_MAX ? p->soft : p->emergency;
          p->forced = p->final = 0;
          break;
        }
        p->scan_width += advance;
        p->scan++;
      }
      if (!p->line_end && p->finishing && p->ready) {
        p->line_end = p->ready;
        p->forced = 0;
        p->final = 1;
      }
    }
    if (!p->line_end)
      return EXR_OK;
    {
      size_t end = p->line_end, destination = l->glyph_count;
      exr_status status;
      if (end > EXR_MAX_ITEMS - destination ||
          !exr_grow((void **)&l->glyphs, &l->glyph_cap, destination + end, sizeof(*l->glyphs)))
        return failure(p, EXR_LIMIT, "Page glyph allocation limit exceeded");
      memcpy(l->glyphs + destination, p->run.glyphs, end * sizeof(*l->glyphs));
      status = exr_flow_emit_line(f, l->glyphs + destination, end, destination,
                                   p->forced, p->final);
      if (status != EXR_OK)
        return status;
      l->glyph_count += end;
      memmove(p->run.glyphs, p->run.glyphs + end,
              (p->run.glyph_count - end) * sizeof(*p->run.glyphs));
      p->run.glyph_count -= end;
      p->ready -= end;
      p->cluster_start -= end;
      reset_scan(p);
    }
  }
}
static exr_status finish_run(exr_pager *p) {
  exr_status status;
  if (!p->finishing) {
    status = measure_cluster(p);
    if (status != EXR_OK)
      return status;
    p->finishing = 1;
  }
  status = drain(p);
  if (status != EXR_OK)
    return status;
  memset(&p->text, 0, sizeof(p->text));
  p->finishing = 0;
  reset_scan(p);
  return EXR_OK;
}
static exr_status scalar(exr_pager *p, frame *current) {
  const exr_node *n = &p->f.doc->nodes[current->node];
  const exr_style *s = &p->styles[current->node];
  exr_glyph g = {0};
  exr_status status;
  uint32_t cp;
  size_t start = current->position;
  if (!exr_next(p->f.doc->text, n->end, &current->position, &cp))
    return failure(p, EXR_ENCODING, "Invalid document text");
  g.boundaries = exr_text_step(&p->text, cp);
  if ((g.boundaries & EXR_BOUNDARY_GRAPHEME) && p->cluster_start < p->run.glyph_count) {
    status = measure_cluster(p);
    if (status != EXR_OK)
      return status;
  }
  if (++p->assets->work_glyphs > EXR_MAX_ITEMS ||
      !exr_grow((void **)&p->run.glyphs, &p->run.glyph_cap,
                  p->run.glyph_count + 1, sizeof(g)))
    return failure(p, EXR_LIMIT, "Text work limit exceeded");
  g.start = start;
  g.end = current->position;
  g.node = current->node;
  g.codepoint = cp;
  g.size = s->font_size;
  g.color = s->color;
  g.flags = s->flags | (exr_text_hidden(cp) ? EXR_GLYPH_HIDDEN : 0);
  g.line_height = s->leading_relative ? s->leading * s->font_size : s->leading;
  p->run.glyphs[p->run.glyph_count++] = g;
  p->position = current->position;
  return drain(p);
}
static exr_status push(exr_pager *p, size_t index, float x, float width) {
  frame *f;
  if (p->depth == sizeof(p->frames) / sizeof(*p->frames))
    return failure(p, EXR_LIMIT, "Layout tree depth exceeded");
  f = &p->frames[p->depth++];
  memset(f, 0, sizeof(*f));
  f->node = index;
  f->x = x;
  f->width = width;
  return EXR_OK;
}
static exr_status advance(exr_pager *p) {
  flow *f = &p->f;
  exr_status status = drain(p);
  if (status != EXR_OK)
    return status;
  while (!p->finished) {
    frame *v;
    const exr_node *n;
    const exr_style *s;
    if (!p->depth) {
      while (p->chapter < f->doc->chapter_count &&
             (!f->doc->chapters[p->chapter].in_spine || !f->doc->chapters[p->chapter].linear))
        p->chapter++;
      if (p->chapter == f->doc->chapter_count) {
        status = finish_run(p);
        if (status != EXR_OK)
          return status;
        p->finished = 1;
        p->position = f->doc->size;
        return EXR_OK;
      }
      status = push(p, f->doc->chapters[p->chapter++].root,
                       p->config.page.margin, p->config.page.width - 2 * p->config.page.margin);
      if (status != EXR_OK)
        return status;
    }
    v = &p->frames[p->depth - 1];
    n = &f->doc->nodes[v->node];
    s = &p->styles[v->node];
    switch (v->phase) {
    case 0:
      if (s->display == EXR_CSS_NONE || n->start == SIZE_MAX) {
        p->depth--;
        break;
      }
      if (n->kind == EXR_NODE_TEXT) {
        v->position = n->start;
        v->phase = 10;
      } else if (n->kind == EXR_NODE_BREAK)
        v->phase = 11;
      else if (s->display == EXR_CSS_INLINE && n->kind != EXR_NODE_IMAGE) {
        v->child = n->first_child;
        v->phase = 20;
      } else
        v->phase = 1;
      break;
    case 1:
      status = finish_run(p);
      if (status != EXR_OK)
        return status;
      if (s->before && f->layout->page_count && f->y > exr_flow_top(f))
        f->force_break = 1;
      {
        float border = s->border_style ? s->border_width : 0;
        float ml = used(s->margin[3], v->width), mr = used(s->margin[1], v->width);
        float pl = used(s->padding[3], v->width) + border;
        float pr = used(s->padding[1], v->width) + border;
        float content = v->width - ml - mr - pl - pr;
        if (s->width.value >= 0 && n->kind != EXR_NODE_IMAGE)
          content = fminf(content, used(s->width, v->width));
        if (s->max_width.value >= 0 && n->kind != EXR_NODE_IMAGE)
          content = fminf(content, used(s->max_width, v->width));
        if (content < 1 || !isfinite(content))
          return failure(p, EXR_ARGUMENT, "CSS leaves no content width");
        v->old_x = f->x;
        v->old_width = f->width;
        v->old_paragraph = f->paragraph;
        v->outer_width = content + pl + pr;
        v->outer_x = v->x + ml;
        if (s->margin[3].value < 0)
          v->outer_x += fmaxf(0, v->width - v->outer_width - mr) /
                        (s->margin[1].value < 0 ? 2 : 1);
        v->x = v->outer_x + pl;
        v->width = content;
        v->pt = used(s->padding[0], f->width) + border;
        v->pb = used(s->padding[2], f->width) + border;
        v->parent_inset = f->bottom_inset;
        f->y += used(s->margin[0], f->width);
      }
      v->phase = 2;
      break;
    case 2:
      status = exr_flow_page(f, v->pt + v->pb, n->start);
      if (status != EXR_OK)
        return status;
      v->first_y = f->y;
      f->bottom_inset += v->pb;
      f->y += v->pt;
      f->x = v->x;
      f->width = v->width;
      f->paragraph = s;
      f->first_line = 1;
      v->entered = 1;
      v->child = n->first_child;
      v->phase = 3;
      break;
    case 3:
      if (n->kind == EXR_NODE_IMAGE) {
        status = exr_flow_image(f, v->node, f->x, f->width);
        if (status != EXR_OK)
          return status;
        v->phase = 5;
      } else if (s->display == EXR_CSS_TABLE) {
        int done;
        if (!v->table) {
          status = exr_table_create(f, v->node, f->x, f->width, &v->table);
          if (status != EXR_OK)
            return status;
        }
        status = exr_table_step(f, v->table, &done);
        if (exr_table_position(v->table) > p->position)
          p->position = exr_table_position(v->table);
        if (status != EXR_OK)
          return status;
        if (done) {
          exr_table_free(v->table);
          v->table = NULL;
          v->phase = 5;
        }
      } else
        v->phase = 4;
      break;
    case 4:
    case 20:
      if (v->child == SIZE_MAX) {
        if (v->phase == 20)
          p->depth--;
        else
          v->phase = 5;
      } else {
        size_t child = v->child;
        v->child = f->doc->nodes[child].next_sibling;
        status = push(p, child, f->x, f->width);
        if (status != EXR_OK)
          return status;
      }
      break;
    case 5:
      status = finish_run(p);
      if (status != EXR_OK)
        return status;
      f->y = fminf(f->y, exr_flow_bottom(f));
      f->bottom_inset -= v->pb;
      f->y += v->pb;
      if ((s->background & 255) || (s->border_style && s->border_width > 0) || s->display == EXR_CSS_CELL)
        if (!exr_flow_box(f, v->node, 0, v->outer_x, v->first_y, v->outer_width,
                            f->y - v->first_y,
                            s->display == EXR_CSS_CELL ? EXR_BOX_CELL : EXR_BOX_BLOCK))
          return failure(p, EXR_MEMORY, "Block fragment allocation failed");
      f->y += used(s->margin[2], v->old_width);
      f->x = v->old_x;
      f->width = v->old_width;
      f->paragraph = v->old_paragraph;
      f->first_line = 1;
      if (s->after)
        f->force_break = 1;
      v->entered = 0;
      p->depth--;
      break;
    case 10:
      if (v->position == n->end)
        p->depth--;
      else {
        status = scalar(p, v);
        if (status != EXR_OK)
          return status;
      }
      break;
    case 11:
      status = finish_run(p);
      if (status != EXR_OK)
        return status;
      p->depth--;
      break;
    default:
      return failure(p, EXR_FORMAT, "Invalid layout continuation");
    }
  }
  return EXR_OK;
}
static int box_order(const void *a, const void *b) {
  const exr_box *x = a, *y = b;
  if (x->node != y->node)
    return x->node < y->node ? -1 : 1;
  return (int)x->kind - (int)y->kind;
}
static exr_status seal(exr_pager *p, int partial) {
  flow *f = &p->f;
  exr_layout *l = f->layout;
  size_t i, j;
  if (partial)
    for (i = 0; i < p->depth; i++) {
      frame *v = &p->frames[i];
      const exr_style *s = &p->styles[v->node];
      if (!v->entered)
        continue;
      if ((s->background & 255) || (s->border_style && s->border_width > 0) || s->display == EXR_CSS_CELL) {
        float end = p->config.page.height - p->config.page.margin - v->parent_inset;
        if (!exr_flow_box(f, v->node, 0, v->outer_x, v->first_y, v->outer_width,
                            end - v->first_y,
                            s->display == EXR_CSS_CELL ? EXR_BOX_CELL : EXR_BOX_BLOCK))
          return failure(p, EXR_MEMORY, "Page fragment allocation failed");
      }
      v->first_y = p->config.page.margin;
    }
  else
    l->pages[0].end = p->f.doc->size;
  if (l->box_count)
    qsort(l->boxes, l->box_count, sizeof(*l->boxes), box_order);
  l->pages[0].box_count = l->box_count;
  /* Pages retain immutable image pixels without copying a full bitmap per page. */
  for (i = 0; i < p->assets->image_count; i++) {
    const exr_cached_image *source = &p->assets->images[i];
    exr_cached_image *copy;
    size_t size;
    for (j = 0; j < l->box_count; j++)
      if (l->boxes[j].kind == EXR_BOX_IMAGE && !l->boxes[j].flags &&
          l->boxes[j].resource == source->resource)
        break;
    if (j == l->box_count)
      continue;
    size = (size_t)source->bitmap.stride * source->bitmap.height;
    if (!exr_grow((void **)&l->images, &l->image_cap, l->image_count + 1, sizeof(*l->images)))
      return failure(p, EXR_MEMORY, "Page image allocation failed");
    copy = &l->images[l->image_count];
    if (*source->refs == SIZE_MAX)
      return failure(p, EXR_LIMIT, "Image reference limit exceeded");
    *copy = *source;
    ++*copy->refs;
    l->image_count++;
    l->image_bytes += size;
  }
  return EXR_OK;
}
exr_status exr_pager_create(const exr_document *doc, exr_font *font,
                             const exr_layout_config *config, exr_pager **out, exr_error *e) {
  exr_layout_config defaults = exr_layout_config_defaults();
  exr_pager *p;
  exr_status status;
  size_t size = 0;
  if (!out)
    return exr_fail(e, EXR_ARGUMENT, "Missing pager output");
  *out = NULL;
  if (!doc || !font)
    return exr_fail(e, EXR_ARGUMENT, "Missing pager document or font");
  if (!config)
    config = &defaults;
  status = exr_layout_validate(config, e);
  if (status != EXR_OK)
    return status;
  p = calloc(1, sizeof(*p));
  if (!p)
    return exr_fail(e, EXR_MEMORY, "Pager allocation failed");
  p->config = *config;
  p->config.user_css = NULL;
  if (config->user_css) {
    while (size <= 1024*1024 && config->user_css[size])
      size++;
    if (size > 1024*1024) {
      exr_pager_free(p);
      return exr_fail(e, EXR_LIMIT, "Pager CSS exceeds 1 MiB");
    }
    p->config.user_css = exr_copy(config->user_css, size);
    if (!p->config.user_css) {
      exr_pager_free(p);
      return exr_fail(e, EXR_MEMORY, "Pager CSS allocation failed");
    }
  }
  status = exr_compute_styles(doc, &p->config, &p->styles, e);
  if (status != EXR_OK) {
    exr_pager_free(p);
    return status;
  }
  p->assets = calloc(1, sizeof(*p->assets));
  if (!p->assets) {
    exr_pager_free(p);
    return exr_fail(e, EXR_MEMORY, "Pager asset allocation failed");
  }
  p->assets->options = config->page;
  p->f.assets = p->assets;
  p->f.doc = doc;
  p->f.font = font;
  p->f.config = &p->config;
  p->f.styles = p->styles;
  p->f.paragraph = &p->styles[0];
  p->f.paginate = p->f.page_limit = 1;
  p->f.x = p->f.y = config->page.margin;
  p->f.width = config->page.width - 2 * config->page.margin;
  p->cache_capacity = 1;
  reset_scan(p);
  *out = p;
  return exr_fail(e, EXR_OK, "");
}
static exr_status next_page(exr_pager *p, exr_layout **out, exr_error *e) {
  exr_layout *l;
  exr_status status;
  if (!out)
    return exr_fail(e, EXR_ARGUMENT, "Missing page output");
  *out = NULL;
  if (!p || p->busy || p->failed)
    return exr_fail(e, EXR_ARGUMENT, "Invalid, failed or reentrant pager");
  if (p->finished)
    return exr_fail(e, EXR_OK, "");
  l = calloc(1, sizeof(*l));
  if (!l)
    return exr_fail(e, EXR_MEMORY, "Page allocation failed");
  l->options = p->config.page;
  if (e)
    memset(e, 0, sizeof(*e));
  p->f.layout = l;
  p->f.error = e;
  p->f.y = p->config.page.margin;
  p->busy = 1;
  status = advance(p);
  if (status == EXR_OK && !l->page_count && !p->emitted)
    status = failure(p, EXR_FORMAT, "No layout content");
  if ((status == EXR_OK || status == EXR_PAUSE) && l->page_count)
    status = seal(p, status == EXR_PAUSE);
  p->busy = 0;
  p->f.layout = NULL;
  p->f.error = NULL;
  if (status != EXR_OK) {
    p->failed = 1;
    exr_layout_free(l);
    if (!e || !e->message[0])
      exr_fail(e, status, "Page layout failed");
    return status;
  }
  if (l->page_count) {
    p->emitted++;
    *out = l;
  } else
    exr_layout_free(l);
  return exr_fail(e, EXR_OK, "");
}
exr_status exr_pager_next(exr_pager *p, exr_layout **out, exr_error *e) {
  if (!out)
    return exr_fail(e, EXR_ARGUMENT, "Missing page output");
  *out = NULL;
  if (!p || p->busy || p->mode == 2)
    return exr_fail(e, EXR_ARGUMENT, "Invalid, reentrant or cached-mode pager");
  p->mode = 1;
  return next_page(p, out, e);
}

static void reset_cursor(exr_pager *p) {
  const exr_document *doc = p->f.doc;
  exr_font *font = p->f.font;
  size_t i;
  for (i = 0; i < p->depth; i++)
    exr_table_free(p->frames[i].table);
  memset(p->frames, 0, sizeof(p->frames));
  memset(&p->text, 0, sizeof(p->text));
  memset(&p->f, 0, sizeof(p->f));
  p->f.doc = doc;
  p->f.font = font;
  p->f.assets = p->assets;
  p->f.config = &p->config;
  p->f.styles = p->styles;
  p->f.paragraph = &p->styles[0];
  p->f.paginate = p->f.page_limit = 1;
  p->f.x = p->f.y = p->config.page.margin;
  p->f.width = p->config.page.width - 2 * p->config.page.margin;
  p->run.glyph_count = 0;
  p->assets->work_glyphs = 0;
  p->depth = p->chapter = p->position = p->emitted = 0;
  p->cluster_start = p->ready = 0;
  p->finishing = p->forced = p->final = p->finished = p->failed = 0;
  reset_scan(p);
}
static void evict_page(exr_pager *p) {
  cached_page *entry = &p->cache[--p->cache_count];
  p->cache_bytes -= entry->bytes;
  exr_layout_free(entry->layout);
}
exr_status exr_pager_set_cache(exr_pager *p, size_t capacity, size_t bytes, exr_error *e) {
  if (!p || p->busy || p->mode == 1 || !capacity || capacity > 64)
    return exr_fail(e, EXR_ARGUMENT, "Invalid, reentrant or sequential-mode pager cache");
  p->mode = 2;
  p->cache_capacity = capacity;
  p->cache_budget = bytes;
  while (p->cache_count > capacity || (bytes && p->cache_bytes > bytes))
    evict_page(p);
  return exr_fail(e, EXR_OK, "");
}
exr_status exr_pager_get(exr_pager *p, size_t index, const exr_layout **out, exr_error *e) {
  cached_page entry = {0};
  exr_layout *page = NULL;
  exr_status status;
  size_t i;
  if (!out)
    return exr_fail(e, EXR_ARGUMENT, "Missing cached page output");
  *out = NULL;
  if (!p || p->busy || p->mode == 1)
    return exr_fail(e, EXR_ARGUMENT, "Invalid, reentrant or sequential-mode pager");
  p->mode = 2;
  for (i = 0; i < p->cache_count; i++)
    if (p->cache[i].index == index) {
      entry = p->cache[i];
      memmove(p->cache + 1, p->cache, i * sizeof(*p->cache));
      p->cache[0] = entry;
      *out = entry.layout;
      return exr_fail(e, EXR_OK, "");
    }
  if (p->failed || index < p->emitted)
    reset_cursor(p);
  while (p->emitted <= index) {
    status = next_page(p, &page, e);
    if (status != EXR_OK) {
      p->failed = 1;
      return status;
    }
    if (!page)
      return exr_fail(e, EXR_ARGUMENT, "Page index is outside the document");
    if (p->emitted - 1 == index)
      break;
    exr_layout_free(page);
    page = NULL;
  }
  entry.bytes = exr_layout_memory_size(page);
  if (entry.bytes == SIZE_MAX || (p->cache_budget && entry.bytes > p->cache_budget)) {
    exr_layout_free(page);
    p->failed = 1;
    return exr_fail(e, EXR_LIMIT, "Page exceeds the pager cache byte budget");
  }
  while (p->cache_count &&
         (p->cache_count == p->cache_capacity || entry.bytes > SIZE_MAX - p->cache_bytes ||
          (p->cache_budget && entry.bytes > p->cache_budget - p->cache_bytes)))
    evict_page(p);
  memmove(p->cache + 1, p->cache, p->cache_count * sizeof(*p->cache));
  entry.index = index;
  entry.layout = page;
  p->cache[0] = entry;
  p->cache_count++;
  p->cache_bytes += entry.bytes;
  *out = page;
  return exr_fail(e, EXR_OK, "");
}
size_t exr_pager_cached_count(const exr_pager *p) { return p ? p->cache_count : 0; }
size_t exr_pager_cached_bytes(const exr_pager *p) { return p ? p->cache_bytes : 0; }
size_t exr_pager_position(const exr_pager *p) { return p ? p->position : 0; }
void exr_pager_free(exr_pager *p) {
  size_t i;
  if (!p)
    return;
  for (i = 0; i < p->depth; i++)
    exr_table_free(p->frames[i].table);
  while (p->cache_count)
    evict_page(p);
  free(p->run.glyphs);
  exr_layout_free(p->assets);
  free(p->styles);
  free((void *)p->config.user_css);
  free(p);
}
static exr_status append_page(exr_layout *all, exr_layout *page, exr_error *e) {
  size_t i, j, ng = all->glyph_count, nl = all->line_count, nb = all->box_count;
  size_t np = all->page_count;
  if (page->glyph_count > EXR_MAX_ITEMS - ng || page->line_count > EXR_MAX_ITEMS - nl ||
      page->box_count > EXR_MAX_ITEMS - nb || np >= EXR_MAX_ITEMS)
    return exr_fail(e, EXR_LIMIT, "Whole-document layout exceeds item limits");
  if (!exr_grow((void **)&all->glyphs, &all->glyph_cap, ng + page->glyph_count, sizeof(*all->glyphs)) ||
      !exr_grow((void **)&all->lines, &all->line_cap, nl + page->line_count, sizeof(*all->lines)) ||
      !exr_grow((void **)&all->boxes, &all->box_cap, nb + page->box_count, sizeof(*all->boxes)) ||
      !exr_grow((void **)&all->pages, &all->page_cap, np + 1, sizeof(*all->pages)))
    return exr_fail(e, EXR_MEMORY, "Whole-document layout allocation failed");
  for (i = 0; i < page->glyph_count; i++) {
    exr_glyph g = page->glyphs[i];
    g.page = np;
    all->glyphs[all->glyph_count++] = g;
  }
  for (i = 0; i < page->line_count; i++) {
    exr_line line = page->lines[i];
    line.page = np;
    line.glyph_start += ng;
    all->lines[all->line_count++] = line;
  }
  for (i = 0; i < page->box_count; i++) {
    exr_box b = page->boxes[i];
    b.page = np;
    all->boxes[all->box_count++] = b;
  }
  all->pages[np] = page->pages[0];
  all->pages[np].line_start = nl;
  all->pages[np].box_start = nb;
  all->page_count++;
  for (i = 0; i < page->image_count; i++) {
    for (j = 0; j < all->image_count; j++)
      if (all->images[j].resource == page->images[i].resource)
        break;
    if (j < all->image_count)
      continue;
    if (!exr_grow((void **)&all->images, &all->image_cap, all->image_count + 1, sizeof(*all->images)))
      return exr_fail(e, EXR_MEMORY, "Image directory allocation failed");
    all->images[all->image_count++] = page->images[i];
    all->image_bytes += (size_t)page->images[i].bitmap.stride * page->images[i].bitmap.height;
    memset(&page->images[i].bitmap, 0, sizeof(page->images[i].bitmap));
    page->images[i].refs = NULL;
  }
  return EXR_OK;
}
exr_status exr_flow_create(const exr_document *doc, exr_font *font,
                            const exr_layout_config *config, exr_layout **out, exr_error *e) {
  exr_pager *pager = NULL;
  exr_layout *all, *page = NULL;
  exr_status status;
  if (!out)
    return exr_fail(e, EXR_ARGUMENT, "Missing layout output");
  *out = NULL;
  status = exr_pager_create(doc, font, config, &pager, e);
  if (status != EXR_OK)
    return status;
  all = calloc(1, sizeof(*all));
  if (!all) {
    exr_pager_free(pager);
    return exr_fail(e, EXR_MEMORY, "Whole-document layout allocation failed");
  }
  all->options = pager->config.page;
  while ((status = exr_pager_next(pager, &page, e)) == EXR_OK && page) {
    status = append_page(all, page, e);
    exr_layout_free(page);
    page = NULL;
    if (status != EXR_OK)
      break;
  }
  if (status == EXR_OK) {
    all->styles = pager->styles;
    all->style_count = doc->node_count;
    all->work_glyphs = pager->assets->work_glyphs;
    pager->styles = NULL;
    *out = all;
  } else
    exr_layout_free(all);
  exr_pager_free(pager);
  return status;
}
