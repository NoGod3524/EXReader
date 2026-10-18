/* SPDX-License-Identifier: GPL-3.0-only */
#include "flow_internal.h"
#include "opentype_internal.h"
#include "ruby_internal.h"

typedef struct {
  size_t node, child, position;
  int phase, entered, sized_inline;
  int old_intrinsic;
  float x, width, old_x, old_width, outer_x, outer_width;
  float pt, pb, first_y, parent_inset;
  float parent_inline_end, inline_end, min_inline;
  const exr_style *old_paragraph;
  exr_table_cursor *table;
  exr_pager *context;
  exr_layout *fragment;
} frame;
typedef struct {
  size_t index, bytes;
  exr_layout *layout;
} cached_page;
typedef struct {
  flow f;
  exr_line_buffer line;
  frame *frames;
  size_t depth, chapter, position, emitted, work_glyphs, shape_work;
  size_t bidi_first, bytes;
  int bidi_active;
} checkpoint;
struct exr_pager {
  flow f;
  exr_layout_config config;
  exr_layout_options physical_page;
  exr_writing_mode writing_mode;
  exr_style *styles;
  size_t style_count;
  exr_layout *assets;
  exr_line_buffer line; /* Raw source, provisional carry and finalized pending line. */
  exr_inline_bidi bidi;
  frame frames[258];
  size_t depth, chapter, position, emitted;
  int finished, failed, busy;
  int local; /* 1: bounded block context, 2: unpaginated table unit. */
  size_t local_root, resume_bidi_first;
  int resume_bidi;
  int mode; /* Owned sequential output or borrowed cached output. */
  cached_page cache[64]; /* Most recently used first. */
  size_t cache_count, cache_bytes, cache_capacity, cache_budget;
  checkpoint *checkpoints[64]; /* Most recently recorded first. */
  size_t checkpoint_count, checkpoint_bytes, checkpoint_capacity, checkpoint_budget, interval;
  size_t generated_pages, restored_checkpoints;
};
static exr_pager *context_clone(const exr_pager *source);
static size_t context_memory_size(const exr_pager *p);
static exr_status next_page(exr_pager *p, exr_layout **out, exr_error *e);
static void clear_frame(frame *f) {
  exr_table_free(f->table);
  exr_pager_free(f->context);
  exr_layout_free(f->fragment);
  f->table = NULL; f->context = NULL; f->fragment = NULL;
}
static void checkpoint_free(checkpoint *c) {
  size_t i;
  if (!c) return;
  if (c->frames)
    for (i = 0; i < c->depth; i++) clear_frame(&c->frames[i]);
  free(c->frames);
  exr_inline_buffer_clear(&c->line);
  free(c);
}
static checkpoint *checkpoint_clone(const checkpoint *source) {
  checkpoint *copy = malloc(sizeof(*copy));
  exr_layout *destinations[3];
  const exr_layout *sources[3] = {&source->line.run, &source->line.raw, &source->line.line};
  size_t i;
  if (!copy) return NULL;
  *copy = *source;
  copy->frames = NULL;
  copy->line.run.glyphs = copy->line.raw.glyphs = copy->line.line.glyphs = NULL;
  destinations[0] = &copy->line.run; destinations[1] = &copy->line.raw;
  destinations[2] = &copy->line.line;
  for (i = 0; i < 3; i++) {
    size_t count = sources[i]->glyph_count;
    destinations[i]->glyph_cap = count;
    if (!count) continue;
    destinations[i]->glyphs = malloc(count*sizeof(exr_glyph));
    if (!destinations[i]->glyphs) goto bad;
    memcpy(destinations[i]->glyphs, sources[i]->glyphs, count*sizeof(exr_glyph));
  }
  if (copy->depth) {
    copy->frames = calloc(copy->depth, sizeof(*copy->frames));
    if (!copy->frames) goto bad;
    for (i = 0; i < copy->depth; i++) {
      copy->frames[i] = source->frames[i]; copy->frames[i].table = NULL;
      copy->frames[i].context = NULL; copy->frames[i].fragment = NULL;
      if (source->frames[i].table) {
        copy->frames[i].table = exr_table_clone(source->frames[i].table);
        if (!copy->frames[i].table) goto bad;
      }
      if (source->frames[i].context) {
        copy->frames[i].context = context_clone(source->frames[i].context);
        if (!copy->frames[i].context) goto bad;
      }
      copy->frames[i].fragment = source->frames[i].fragment;
      exr_layout_ref(copy->frames[i].fragment);
    }
  }
  return copy;
bad:
  checkpoint_free(copy); return NULL;
}
static exr_pager *context_clone(const exr_pager *source) {
  checkpoint state = {0}, *saved;
  exr_pager *copy;
  size_t i;
  if (!source) return NULL;
  state.f = source->f; state.line = source->line;
  state.frames = (frame *)source->frames; state.depth = source->depth;
  saved = checkpoint_clone(&state);
  if (!saved) return NULL;
  copy = calloc(1, sizeof(*copy));
  if (!copy) { checkpoint_free(saved); return NULL; }
  copy->f = saved->f; copy->line = saved->line; memset(&saved->line, 0, sizeof(saved->line));
  copy->config = source->config; copy->config.user_css = NULL;
  copy->physical_page = source->physical_page; copy->writing_mode = source->writing_mode;
  copy->styles = source->styles; copy->assets = source->assets;
  copy->local = source->local; copy->local_root = source->local_root;
  copy->depth = source->depth; copy->chapter = source->chapter;
  copy->position = source->position; copy->emitted = source->emitted;
  copy->finished = source->finished;
  copy->f.layout = NULL; copy->f.error = NULL;
  copy->f.config = &copy->config; copy->f.bidi = &copy->bidi;
  copy->resume_bidi = source->line.text.started;
  copy->resume_bidi_first = source->resume_bidi ? source->resume_bidi_first : source->bidi.first_node;
  for (i = 0; i < copy->depth; i++) {
    copy->frames[i] = saved->frames[i];
    saved->frames[i].table = NULL; saved->frames[i].context = NULL; saved->frames[i].fragment = NULL;
  }
  checkpoint_free(saved);
  return copy;
}
static size_t context_memory_size(const exr_pager *p) {
  size_t total = sizeof(*p), i;
  const exr_layout *queues[3];
  if (!p) return 0;
  queues[0] = &p->line.run; queues[1] = &p->line.raw; queues[2] = &p->line.line;
  for (i = 0; i < 3; i++) {
    if (queues[i]->glyph_count > (SIZE_MAX-total)/sizeof(exr_glyph)) return SIZE_MAX;
    total += queues[i]->glyph_count*sizeof(exr_glyph);
  }
  for (i = 0; i < p->depth; i++) {
    size_t bytes = exr_table_memory_size(p->frames[i].table);
    if (bytes > SIZE_MAX-total) return SIZE_MAX;
    total += bytes;
    bytes = context_memory_size(p->frames[i].context);
    if (bytes > SIZE_MAX-total) return SIZE_MAX;
    total += bytes;
    if (p->frames[i].fragment) {
      bytes = exr_layout_memory_size(p->frames[i].fragment);
      if (bytes > SIZE_MAX-total) return SIZE_MAX;
      total += bytes;
    }
  }
  return total;
}
static void evict_checkpoint(exr_pager *p) {
  checkpoint *c = p->checkpoints[--p->checkpoint_count];
  p->checkpoint_bytes -= c->bytes;
  checkpoint_free(c);
}
static void save_checkpoint(exr_pager *p) {
  checkpoint state = {0}, *copy;
  size_t i, bytes = sizeof(state) + p->depth*sizeof(frame);
  const exr_layout *queues[3] = {&p->line.run, &p->line.raw, &p->line.line};
  if (p->mode != 2 || !p->checkpoint_capacity || p->finished || p->emitted % p->interval) return;
  for (i = 0; i < p->checkpoint_count; i++)
    if (p->checkpoints[i]->emitted == p->emitted) return;
  for (i = 0; i < 3; i++) {
    if (queues[i]->glyph_count > (SIZE_MAX - bytes)/sizeof(exr_glyph)) return;
    bytes += queues[i]->glyph_count*sizeof(exr_glyph);
  }
  for (i = 0; i < p->depth; i++) {
    size_t part = exr_table_memory_size(p->frames[i].table);
    if (part > SIZE_MAX - bytes) return;
    bytes += part;
    part = context_memory_size(p->frames[i].context);
    if (part > SIZE_MAX - bytes) return;
    bytes += part;
    if (p->frames[i].fragment) {
      part = exr_layout_memory_size(p->frames[i].fragment);
      if (part > SIZE_MAX - bytes) return;
      bytes += part;
    }
  }
  if (bytes > p->checkpoint_budget) return;
  state.f = p->f;
  state.f.layout = NULL; state.f.error = NULL;
  state.line = p->line; state.frames = p->frames; state.depth = p->depth;
  state.chapter = p->chapter; state.position = p->position; state.emitted = p->emitted;
  state.work_glyphs = p->assets->work_glyphs; state.shape_work = p->assets->shape_work;
  state.bidi_first = p->bidi.first_node; state.bidi_active = p->line.text.started;
  state.bytes = bytes;
  copy = checkpoint_clone(&state);
  if (!copy) return; /* Optional acceleration must not fail an otherwise valid page. */
  while (p->checkpoint_count && (p->checkpoint_count >= p->checkpoint_capacity ||
         bytes > p->checkpoint_budget - p->checkpoint_bytes)) evict_checkpoint(p);
  memmove(p->checkpoints + 1, p->checkpoints, p->checkpoint_count*sizeof(*p->checkpoints));
  p->checkpoints[0] = copy;
  p->checkpoint_count++; p->checkpoint_bytes += bytes;
}
static void reset_cursor(exr_pager *p);
static exr_status restore_checkpoint(exr_pager *p, const checkpoint *source, exr_error *e) {
  checkpoint *copy = checkpoint_clone(source);
  exr_status status = EXR_OK;
  size_t i;
  if (!copy) return exr_fail(e, EXR_MEMORY, "Cannot restore pagination checkpoint");
  reset_cursor(p);
  p->f = copy->f;
  p->f.bidi = &p->bidi; p->f.error = e;
  p->line = copy->line; memset(&copy->line, 0, sizeof(copy->line));
  p->depth = copy->depth;
  for (i = 0; i < copy->depth; i++) {
    p->frames[i] = copy->frames[i];
    copy->frames[i].table = NULL; copy->frames[i].context = NULL; copy->frames[i].fragment = NULL;
  }
  p->chapter = copy->chapter; p->position = copy->position; p->emitted = copy->emitted;
  p->assets->work_glyphs = copy->work_glyphs; p->assets->shape_work = copy->shape_work;
  if (copy->bidi_active)
    status = exr_inline_prepare(&p->f, copy->bidi_first, &p->bidi);
  p->f.error = NULL;
  checkpoint_free(copy);
  if (status == EXR_OK) {
    if (p->restored_checkpoints < SIZE_MAX) p->restored_checkpoints++;
  } else p->failed = 1;
  return status;
}
static float used(exr_length l, float width) {
  return l.value < 0 ? 0 : l.percent ? l.value * width : l.value;
}
static exr_status failure(exr_pager *p, exr_status status, const char *message) {
  return exr_fail(p->f.error, status, "%s", message);
}
static exr_status finish_run(exr_pager *p) {
  exr_status status = exr_inline_finish(&p->f, &p->line);
  if (status == EXR_OK) exr_inline_clear(&p->bidi);
  return status;
}
static exr_status scalar(exr_pager *p, frame *current) {
  const exr_node *n = &p->f.doc->nodes[current->node];
  const exr_style *s = &p->styles[current->node];
  exr_glyph g = {0};
  exr_status status;
  uint32_t cp;
  size_t start = current->position;
  if (!p->line.text.started) {
    status = exr_inline_prepare(&p->f, current->node, &p->bidi);
    if (status != EXR_OK)
      return status;
  }
  if (!exr_next(p->f.doc->text, n->end, &current->position, &cp))
    return failure(p, EXR_ENCODING, "Invalid document text");
  if (++p->assets->work_glyphs > EXR_MAX_ITEMS)
    return failure(p, EXR_LIMIT, "Text work limit exceeded");
  if (!(p->assets->work_glyphs & 255)) {
    status = exr_control_poll(&p->config.control, EXR_STAGE_LAYOUT, current->position,
                                p->f.doc->size, p->f.error);
    if (status != EXR_OK) return status;
  }
  g.start = start;
  g.end = current->position;
  g.node = current->node;
  g.codepoint = cp;
  g.size = s->font_size;
  g.color = s->color;
  g.flags = s->flags | (exr_text_hidden(cp) ? EXR_GLYPH_HIDDEN : 0);
  g.bidi_level = exr_inline_level(&p->bidi, start);
  if (g.bidi_level == UINT_MAX)
    g.flags |= EXR_GLYPH_HIDDEN;
  g.line_height = s->leading_relative ? s->leading * s->font_size : s->leading;
  p->position = current->position;
  return exr_inline_feed(&p->f, &p->line, g);
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
static exr_status context_create(flow *parent, size_t node, float width, float height,
                                  exr_writing_mode mode, int local, exr_pager **out) {
  exr_pager *p;
  exr_status status;
  *out = NULL;
  if (parent->context_depth >= 8)
    return exr_fail(parent->error, EXR_LIMIT, "Writing-mode context nesting limit exceeded");
  if (!isfinite(width) || !isfinite(height) || width < 1 || height < 1)
    return exr_fail(parent->error, EXR_LIMIT, "Invalid flow context extent %.3f x %.3f",(double)width,(double)height);
  p = calloc(1, sizeof(*p));
  if (!p) return exr_fail(parent->error, EXR_MEMORY, "Writing-mode context allocation failed");
  p->config = *parent->config; p->config.user_css = NULL;
  p->config.page.width = width; p->config.page.height = height; p->config.page.margin = 0;
  p->physical_page = p->config.page;
  if (mode != EXR_WRITING_HORIZONTAL_TB) {
    p->physical_page.width = height; p->physical_page.height = width;
  }
  p->local = local; p->local_root = node; p->writing_mode = mode;
  p->styles = (exr_style *)parent->styles; p->assets = parent->assets;
  p->f = *parent;
  if(parent->border_override && mode!=parent->writing_mode) {
    exr_style physical={0},logical; size_t j;
    size_t map[4]={0,1,2,3};
    if(parent->writing_mode!=EXR_WRITING_HORIZONTAL_TB) {
      map[0]=parent->writing_mode==EXR_WRITING_VERTICAL_RL ? 1 : 3;
      map[1]=2; map[2]=parent->writing_mode==EXR_WRITING_VERTICAL_RL ? 3 : 1; map[3]=0;
    }
    for(j=0;j<4;j++) physical.padding[map[j]].value=parent->border_insets[j];
    logical=exr_flow_style(&physical,mode);
    for(j=0;j<4;j++) p->f.border_insets[j]=logical.padding[j].value;
  }
  p->f.layout = NULL; p->f.config = &p->config; p->f.bidi = &p->bidi;
  p->f.origin_x = p->f.used_inline = p->f.x = p->f.y = p->f.bottom_inset = p->f.inline_end_inset = 0;
  p->f.width = width; p->f.pending = 0; p->f.first_line = 1;
  p->f.force_break = 0; p->f.paginate = p->f.page_limit = local == 1;
  p->f.context_depth += local == 1;
  p->f.table_depth += local == 2;
  p->f.writing_mode = mode;
  if(local==1) p->f.intrinsic=0; /* Orthogonal subcontexts measure through their physical fragment. */
  status = push(p, node, 0, width);
  if (status != EXR_OK) { exr_pager_free(p); return status; }
  *out = p; return EXR_OK;
}
static exr_status advance(exr_pager *p) {
  flow *f = &p->f;
  exr_status status = exr_control_poll(&p->config.control, EXR_STAGE_LAYOUT, p->position,
                                       p->f.doc->size, p->f.error);
  if (status != EXR_OK) return status;
  if (p->resume_bidi) {
    status = exr_inline_prepare(f, p->resume_bidi_first, &p->bidi);
    if (status != EXR_OK) return status;
    p->resume_bidi = 0;
  }
  status = exr_inline_drain(f, &p->line);
  if (status != EXR_OK)
    return status;
  while (!p->finished) {
    frame *v;
    const exr_node *n;
    const exr_style *s;
    if (!(p->assets->work_glyphs & 255)) {
      status = exr_control_poll(&p->config.control, EXR_STAGE_LAYOUT, p->position,
                                  p->f.doc->size, p->f.error);
      if (status != EXR_OK) return status;
    }
    if (!p->depth) {
      if (p->local) {
        status = finish_run(p);
        if (status != EXR_OK) return status;
        p->finished = 1; p->position = f->doc->nodes[p->local_root].end;
        return EXR_OK;
      }
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
      if (s->display != EXR_CSS_INLINE && n->kind != EXR_NODE_TEXT && n->kind != EXR_NODE_BREAK &&
          s->writing_mode != f->writing_mode) {
        int perpendicular = (s->writing_mode == EXR_WRITING_HORIZONTAL_TB) !=
                            (f->writing_mode == EXR_WRITING_HORIZONTAL_TB);
        status = finish_run(p);
        if (status != EXR_OK) return status;
        if (s->before && f->layout->page_count && f->y > exr_flow_top(f)) f->force_break = 1;
        status = context_create(f, v->node, perpendicular ? exr_flow_room(f) : f->width,
                                   perpendicular ? f->width : exr_flow_room(f),
                                   s->writing_mode, 1, &v->context);
        if (status != EXR_OK) return status;
        v->phase = 30;
        break;
      }
      if (exr_ruby_node(f->doc,v->node)) {
        v->position=0; v->phase=40;
      } else if (n->kind == EXR_NODE_TEXT) {
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
        exr_style box = exr_flow_style(s, f->writing_mode);
        const exr_style *b = &box;
        int cell_root=p->local==2 && v->node==p->local_root && s->display==EXR_CSS_CELL;
        size_t side;
        for(side=0;side<4;side++) {
          if(p->local && v->node==p->local_root && s->display==EXR_CSS_CELL) box.margin[side]=(exr_length){0,0};
          if(s->display==EXR_CSS_TABLE && s->border_collapse) box.padding[side]=(exr_length){0,0};
        }
        float border = s->border_style==1 && !(s->display==EXR_CSS_TABLE && s->border_collapse) ? s->border_width : 0;
        const float *resolved=f->border_override && v->node==f->border_node ? f->border_insets : NULL;
        float ml = used(b->margin[3], v->width), mr = used(b->margin[1], v->width);
        float pl = used(b->padding[3], v->width) + (resolved ? resolved[3] : border);
        float pr = used(b->padding[1], v->width) + (resolved ? resolved[1] : border);
        float content = v->width - ml - mr - pl - pr;
        v->old_intrinsic=f->intrinsic;
        /* A table cell's width already contributed to column allocation. Its
           percentage is relative to the table, not a second percentage here. */
        if (b->width.value >= 0 && n->kind != EXR_NODE_IMAGE &&
            !cell_root && (!f->intrinsic || !b->width.percent)) {
          content = fminf(content, used(b->width, v->width));
          /* A fixed-width descendant is a definite constraint even while
             measuring an ancestor's intrinsic width. */
          f->intrinsic=0;
        }
        if (b->max_width.value >= 0 && n->kind != EXR_NODE_IMAGE && (!f->intrinsic || !b->max_width.percent))
          content = fminf(content, used(b->max_width, v->width));
        if (content < 1 || !isfinite(content))
          return failure(p, EXR_ARGUMENT, "CSS leaves no content width");
        v->old_x = f->x;
        v->old_width = f->width;
        v->old_paragraph = f->paragraph;
        v->outer_width = content + pl + pr;
        v->outer_x = v->x + ml;
        if (b->margin[3].value < 0)
          v->outer_x += fmaxf(0, v->width - v->outer_width - mr) /
                        (b->margin[1].value < 0 ? 2 : 1);
        v->x = v->outer_x + pl;
        v->width = content;
        v->pt = used(b->padding[0], f->width) + (resolved ? resolved[0] : border);
        v->pb = used(b->padding[2], f->width) + (resolved ? resolved[2] : border);
        v->parent_inset = f->bottom_inset;
        v->parent_inline_end = f->inline_end_inset;
        v->inline_end = pr + mr;
        v->min_inline = v->outer_x + v->outer_width + mr + v->parent_inline_end;
        v->sized_inline = (b->width.value >= 0 && n->kind != EXR_NODE_IMAGE) ||
                          (s->background & 255) || (s->border_style && s->border_width > 0) ||
                          s->display == EXR_CSS_CELL;
        if(v->old_intrinsic) f->intrinsic_extent=fmax(f->intrinsic_extent,
          f->x+ml+pl+pr+mr+(f->intrinsic ? 0 : content)+f->inline_end_inset);
        f->y += used(b->margin[0], f->width);
      }
      v->phase = 2;
      break;
    case 2:
      status = exr_flow_page(f, v->pt + v->pb, n->start);
      if (status != EXR_OK)
        return status;
      v->first_y = f->y;
      if (f->paginate) f->bottom_inset += v->pb;
      f->inline_end_inset += v->inline_end;
      if (v->sized_inline) f->used_inline = fmaxf(f->used_inline, v->min_inline);
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
          float x,width;
          status = exr_table_create(f, v->node, f->x, f->width, &v->table);
          if (status != EXR_OK)
            return status;
          exr_table_geometry(v->table,&x,&width);
          v->outer_x+=x-f->x; v->x=x;
          v->outer_width-=f->width-width; v->width=width;
          f->x=x; f->width=width;
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
      if (f->paginate) {
        f->y = fminf(f->y, exr_flow_bottom(f));
        f->bottom_inset -= v->pb;
      }
      f->y += v->pb;
      if ((s->background & 255) || (s->border_style && s->border_width > 0) || s->display == EXR_CSS_CELL)
        if (!exr_flow_box(f, v->node, 0, v->outer_x, v->first_y, v->outer_width,
                            f->y - v->first_y,
                            s->display == EXR_CSS_CELL ? EXR_BOX_CELL : EXR_BOX_BLOCK))
          return failure(p, EXR_MEMORY, "Block fragment allocation failed");
      {
        exr_style box = exr_flow_style(s, f->writing_mode);
        if(!(p->local && v->node==p->local_root && s->display==EXR_CSS_CELL)) f->y += used(box.margin[2], v->old_width);
      }
      f->x = v->old_x;
      f->width = v->old_width;
      f->paragraph = v->old_paragraph;
      f->inline_end_inset = v->parent_inline_end;
      f->first_line = 1;
      f->intrinsic=v->old_intrinsic;
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
    case 30: {
      float height;
      int perpendicular = (s->writing_mode == EXR_WRITING_HORIZONTAL_TB) !=
                          (f->writing_mode == EXR_WRITING_HORIZONTAL_TB);
      if (!v->fragment) {
        v->context->config.control = p->config.control;
        status = next_page(v->context, &v->fragment, f->error);
        if (status != EXR_OK) return status;
        if (!v->fragment) {
          clear_frame(v); p->depth--; f->first_line = 1;
          if (s->after) f->force_break = 1;
          break;
        }
      }
      height = perpendicular ? v->fragment->flow_inline : v->fragment->flow_block;
      status = exr_flow_page(f, height, v->fragment->pages[0].start);
      if (status != EXR_OK) return status;
      status = exr_flow_copy(f, v->fragment, v->node, f->x, f->y, height,0);
      if (status != EXR_OK) return status;
      f->y += height; f->first_line = 1;
      if (v->context->position > p->position) p->position = v->context->position;
      exr_layout_free(v->fragment); v->fragment = NULL;
      break;
    }
    case 40: {
      exr_glyph item={0}; int done=0;
      if (!p->line.text.started) {
        status=exr_inline_prepare(f,v->node,&p->bidi);
        if(status!=EXR_OK) return status;
      }
      status=exr_ruby_item(f,v->node,v->position,&item,&done);
      if(status!=EXR_OK) return status;
      if(done) { p->depth--; break; }
      v->position++; item.bidi_level=exr_inline_level(&p->bidi,item.start);
      if(++p->assets->work_glyphs>EXR_MAX_ITEMS) return failure(p,EXR_LIMIT,"Text work limit exceeded");
      p->position=item.end;
      status=exr_inline_feed(f,&p->line,item);
      if(status!=EXR_OK) return status;
      break;
    }
    default:
      return failure(p, EXR_FORMAT, "Invalid layout continuation");
    }
  }
  return EXR_OK;
}
static int box_order(const void *a, const void *b) {
  const exr_box *x = a, *y = b;
  int xb=!!(x->flags&EXR_BOX_BORDER),yb=!!(y->flags&EXR_BOX_BORDER);
  if(xb!=yb) return xb-yb;
  if (x->node != y->node)
    return x->node < y->node ? -1 : 1;
  if(xb) {
    float xw=fminf(x->width,x->height),yw=fminf(y->width,y->height);
    if(xw!=yw) return xw<yw ? -1 : 1;
    if(x->y!=y->y) return x->y<y->y ? -1 : 1;
    if(x->x!=y->x) return x->x<y->x ? -1 : 1;
    if(x->background!=y->background) return x->background<y->background ? -1 : 1;
  }
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
    l->pages[0].end = p->local ? p->f.doc->nodes[p->local_root].end : p->f.doc->size;
  /* A block decoration belongs to this fragment's source range, so the public
     arrays can be rebuilt through the same positioned-layout validation. */
  for (i = 0; i < l->box_count; i++) {
    exr_box *box = &l->boxes[i];
    if (box->start < l->pages[0].start) box->start = l->pages[0].start;
    if (box->start > l->pages[0].end) box->start = l->pages[0].end;
    if (box->end < box->start) box->end = box->start;
    if (box->end > l->pages[0].end) box->end = l->pages[0].end;
  }
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
  l->flow_inline = f->used_inline;
  l->flow_block = f->y;
  /* Partial block backgrounds can fill the unused tail of a fragment. Their
     extent must travel with the fragment when an enclosing axis is different. */
  for (i = 0; i < l->box_count; i++) {
    const exr_box *box = &l->boxes[i];
    float end = f->writing_mode == EXR_WRITING_HORIZONTAL_TB ? box->y + box->height :
                f->writing_mode == EXR_WRITING_VERTICAL_RL ? f->origin_x - box->x : box->x + box->width;
    l->flow_block = fmaxf(l->flow_block, end);
  }
  l->writing_mode = f->writing_mode;
  l->options = p->physical_page;
  return EXR_OK;
}
/* Anonymous document/chapter wrappers follow their single visible block.
   An explicit outer declaration fixes the viewport, leaving inner changes local. */
static int substantive(const exr_pager *p, size_t node) {
  const exr_node *n = &p->f.doc->nodes[node];
  size_t at;
  if (p->styles[node].display == EXR_CSS_NONE || n->start == SIZE_MAX) return 0;
  if (n->kind != EXR_NODE_TEXT) return 1;
  for (at = n->start; at < n->end; at++) {
    unsigned char c = (unsigned char)p->f.doc->text[at];
    if (c != ' ' && c != '\t' && c != '\r' && c != '\n' && c != '\f') return 1;
  }
  return 0;
}
static exr_status writing_mode(exr_pager *p, exr_error *e) {
  size_t chapter, at, bytes = (p->style_count + CHAR_BIT - 1)/CHAR_BIT;
  unsigned char *visible = calloc(bytes ? bytes : 1, 1);
  int found = 0;
  if (!visible) return exr_fail(e, EXR_MEMORY, "Writing-mode visibility allocation failed");
  /* Parents precede children in the document model. One temporary bit per node
     identifies visible content without repeatedly walking every subtree. */
  for (at = p->style_count; at; at--) {
    size_t node = at-1, parent = p->f.doc->nodes[node].parent;
    const exr_node *n = &p->f.doc->nodes[node];
    if (!(node & 255) && exr_control_cancel(&p->config.control, e) != EXR_OK) { free(visible); return EXR_CANCELLED; }
    if ((n->kind == EXR_NODE_TEXT || n->kind == EXR_NODE_IMAGE) && substantive(p,node))
      visible[node/CHAR_BIT] |= (unsigned char)(1u << (node%CHAR_BIT));
    if (parent != SIZE_MAX && (visible[node/CHAR_BIT] & (1u << (node%CHAR_BIT))))
      visible[parent/CHAR_BIT] |= (unsigned char)(1u << (parent%CHAR_BIT));
  }
  for (chapter = 0; chapter < p->f.doc->chapter_count; chapter++) {
    size_t chain[258], count = 0, node = p->f.doc->chapters[chapter].root, i;
    exr_writing_mode mode;
    if (!p->f.doc->chapters[chapter].in_spine || !p->f.doc->chapters[chapter].linear ||
        !(visible[node/CHAR_BIT] & (1u << (node%CHAR_BIT)))) continue;
    for (;;) {
      size_t child, single = SIZE_MAX;
      if (count == sizeof(chain)/sizeof(*chain)) {
        free(visible); return exr_fail(e, EXR_LIMIT, "Writing-mode viewport depth exceeded");
      }
      chain[count++] = node;
      if (p->styles[node].writing_declared) break;
      for (child = p->f.doc->nodes[node].first_child; child != SIZE_MAX;
           child = p->f.doc->nodes[child].next_sibling) {
        if (!(visible[child/CHAR_BIT] & (1u << (child%CHAR_BIT)))) continue;
        if (single != SIZE_MAX) { single = SIZE_MAX; break; }
        single = child;
      }
      if (single == SIZE_MAX || p->styles[single].display == EXR_CSS_INLINE ||
          p->f.doc->nodes[single].kind == EXR_NODE_IMAGE) break;
      node = single;
      if (exr_control_cancel(&p->config.control, e) != EXR_OK) { free(visible); return EXR_CANCELLED; }
    }
    mode = p->styles[node].writing_mode;
    for (i = 0; i < count; i++) p->styles[chain[i]].writing_mode = mode;
    if (!found) { p->writing_mode = mode; found = 1; }
  }
  free(visible);
  if (p->writing_mode != EXR_WRITING_HORIZONTAL_TB) {
    float swap = p->config.page.width;
    p->config.page.width = p->config.page.height; p->config.page.height = swap;
  }
  p->f.writing_mode = p->writing_mode;
  p->f.origin_x = p->writing_mode == EXR_WRITING_VERTICAL_RL ? p->physical_page.width : 0;
  return EXR_OK;
}
exr_status exr_pager_create(const exr_document *doc, exr_font *font,
                             const exr_layout_config *config, exr_pager **out, exr_error *e) {
  exr_layout_config defaults = exr_layout_config_defaults();
  exr_pager *p;
  exr_status status;
  size_t size = 0;
  exr_font_rule *font_rules = NULL;
  size_t font_count = 0;
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
  p->physical_page = config->page;
  p->f.doc = doc;
  p->style_count = doc->node_count;
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
  status = exr_compute_styles(doc, &p->config, &p->styles, &font_rules, &font_count, e);
  if (status != EXR_OK) {
    exr_pager_free(p);
    return status;
  }
  status = writing_mode(p, e);
  if (status != EXR_OK) { free(font_rules); exr_pager_free(p); return status; }
  p->assets = calloc(1, sizeof(*p->assets));
  if (!p->assets) {
    free(font_rules);
    exr_pager_free(p);
    return exr_fail(e, EXR_MEMORY, "Pager asset allocation failed");
  }
  p->assets->options = p->config.page;
  status = exr_book_fonts(doc, font, p->styles, font_rules, font_count, &p->config.control,
                           &p->assets->font, e);
  free(font_rules);
  if (status != EXR_OK) { exr_pager_free(p); return status; }
  p->f.assets = p->assets;
  p->f.doc = doc;
  p->f.font = p->assets->font;
  p->f.config = &p->config;
  p->f.styles = p->styles;
  p->f.bidi = &p->bidi;
  p->f.paragraph = &p->styles[0];
  p->f.paginate = p->f.page_limit = 1;
  p->f.x = p->f.y = config->page.margin;
  p->f.width = p->config.page.width - 2 * config->page.margin;
  p->cache_capacity = 1;
  p->checkpoint_capacity = 4;
  p->checkpoint_budget = 2*1024*1024;
  p->interval = 16;
  *out = p;
  return exr_fail(e, EXR_OK, "");
}
static exr_status next_page(exr_pager *p, exr_layout **out, exr_error *e) {
  exr_layout *l;
  exr_status status;
  size_t i;
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
  l->font = p->assets->font;
  exr_font_ref(l->font);
  if (e)
    memset(e, 0, sizeof(*e));
  p->f.layout = l;
  p->f.error = e;
  p->f.y = p->config.page.margin;
  p->f.used_inline = 0;
  for (i = 0; i < p->depth; i++)
    if (p->frames[i].entered && p->frames[i].sized_inline)
      p->f.used_inline = fmaxf(p->f.used_inline, p->frames[i].min_inline);
  p->busy = 1;
  status = advance(p);
  if (status == EXR_OK && !l->page_count && !p->emitted && !p->local)
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
    if (p->generated_pages < SIZE_MAX) p->generated_pages++;
    save_checkpoint(p);
    *out = l;
  } else
    exr_layout_free(l);
  return exr_fail(e, EXR_OK, "");
}
exr_status exr_flow_unit(flow *parent, size_t node, float width,
                          exr_layout **out, float *height) {
  exr_pager *p = NULL;
  exr_status status;
  *out = NULL; *height = 0;
  status = context_create(parent, node, width, exr_flow_room(parent),
                            parent->writing_mode, 2, &p);
  if (status != EXR_OK) return status;
  status = next_page(p, out, parent->error);
  if (status == EXR_OK) {
    *height = p->f.y;
    if (!*out) {
      *out = calloc(1, sizeof(**out));
      if (!*out) status = exr_fail(parent->error, EXR_MEMORY, "Empty flow unit allocation failed");
      else (*out)->writing_mode = parent->writing_mode;
    }
  }
  exr_pager_free(p); return status;
}
exr_status exr_flow_intrinsic(flow *parent,size_t node,float width,int mode,float *out) {
  flow measure=*parent; exr_pager *p=NULL; exr_layout *layout=NULL; exr_status status;
  *out=0; measure.intrinsic=mode; measure.intrinsic_extent=0;
  status=context_create(&measure,node,width,exr_flow_room(parent),parent->writing_mode,2,&p);
  if(status==EXR_OK) status=next_page(p,&layout,parent->error);
  if(status==EXR_OK) {
    if(!isfinite(p->f.intrinsic_extent) || p->f.intrinsic_extent>1e9) status=exr_fail(parent->error,EXR_LIMIT,"Intrinsic table width exceeds coordinate budget");
    else *out=(float)p->f.intrinsic_extent;
  }
  exr_layout_free(layout); exr_pager_free(p); return status;
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
    clear_frame(&p->frames[i]);
  memset(p->frames, 0, sizeof(p->frames));
  exr_inline_buffer_clear(&p->line);
  exr_inline_clear(&p->bidi);
  memset(&p->f, 0, sizeof(p->f));
  p->f.writing_mode = p->writing_mode;
  p->f.origin_x = p->writing_mode == EXR_WRITING_VERTICAL_RL ? p->physical_page.width : 0;
  p->f.doc = doc;
  p->f.font = font;
  p->f.assets = p->assets;
  p->f.config = &p->config;
  p->f.styles = p->styles;
  p->f.bidi = &p->bidi;
  p->f.paragraph = &p->styles[0];
  p->f.paginate = p->f.page_limit = 1;
  p->f.x = p->f.y = p->config.page.margin;
  p->f.width = p->config.page.width - 2 * p->config.page.margin;
  p->assets->work_glyphs = p->assets->shape_work = 0;
  p->depth = p->chapter = p->position = p->emitted = 0;
  p->finished = p->failed = 0;
  p->resume_bidi = 0;
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
  {
    checkpoint *best = NULL;
    for (i = 0; i < p->checkpoint_count; i++) {
      checkpoint *c = p->checkpoints[i];
      if (c->emitted <= index && (!best || c->emitted > best->emitted)) best = c;
    }
    if (best && (p->failed || index < p->emitted || best->emitted > p->emitted)) {
      status = restore_checkpoint(p, best, e);
      if (status != EXR_OK) return status;
    } else if (p->failed || index < p->emitted) reset_cursor(p);
  }
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
exr_status exr_pager_set_checkpoints(exr_pager *p, size_t capacity, size_t budget,
                                      size_t interval, exr_error *e) {
  if (!p || p->busy || capacity > 64 || (capacity && (!budget || !interval)))
    return exr_fail(e, EXR_ARGUMENT, "Invalid or reentrant pagination checkpoint settings");
  p->checkpoint_capacity = capacity;
  p->checkpoint_budget = budget;
  p->interval = interval;
  while (p->checkpoint_count && (p->checkpoint_count > capacity ||
         p->checkpoint_bytes > budget)) evict_checkpoint(p);
  return exr_fail(e, EXR_OK, "");
}
exr_status exr_pager_set_control(exr_pager *p, const exr_control *control, exr_error *e) {
  if (!p || p->busy) return exr_fail(e, EXR_ARGUMENT, "Invalid or reentrant pager control");
  if (control) p->config.control = *control;
  else memset(&p->config.control, 0, sizeof(p->config.control));
  return exr_fail(e, EXR_OK, "");
}
exr_pager_stats exr_pager_statistics(const exr_pager *p) {
  exr_pager_stats out = {0};
  if (p) out = (exr_pager_stats){p->generated_pages, p->checkpoint_count,
                                 p->checkpoint_bytes, p->restored_checkpoints};
  return out;
}
size_t exr_pager_position(const exr_pager *p) { return p ? p->position : 0; }
void exr_pager_free(exr_pager *p) {
  size_t i;
  if (!p)
    return;
  for (i = 0; i < p->depth; i++)
    clear_frame(&p->frames[i]);
  while (p->cache_count)
    evict_page(p);
  while (p->checkpoint_count) evict_checkpoint(p);
  exr_inline_buffer_clear(&p->line);
  exr_inline_clear(&p->bidi);
  if (!p->local) {
    exr_layout_free(p->assets);
    exr_styles_free(p->styles, p->style_count);
  }
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
  all->options = pager->physical_page;
  all->writing_mode = pager->writing_mode;
  all->font = pager->assets->font;
  exr_font_ref(all->font);
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
