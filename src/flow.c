/* SPDX-License-Identifier: GPL-3.0-only */
#include "flow_internal.h"
#include "bidi_internal.h"
#include "ruby_internal.h"

static float used(exr_length l, float width) {
  return l.value < 0 ? 0 : l.percent ? l.value * width : l.value;
}
exr_style exr_flow_style(const exr_style *style, exr_writing_mode mode) {
  exr_style result = *style;
  if (mode != EXR_WRITING_HORIZONTAL_TB) {
    size_t map[4] = {mode == EXR_WRITING_VERTICAL_RL ? 1u : 3u, 2u,
                     mode == EXR_WRITING_VERTICAL_RL ? 3u : 1u, 0u}, j;
    result.width = style->height; result.height = style->width;
    result.max_width = style->max_height; result.max_height = style->max_width;
    for (j = 0; j < 4; j++) {
      result.margin[j] = style->margin[map[j]];
      result.padding[j] = style->padding[map[j]];
    }
  }
  return result;
}
float exr_flow_top(const flow *f) { return f->paginate ? f->layout->options.margin : 0; }
float exr_flow_bottom(const flow *f) {
  return f->layout->options.height - f->layout->options.margin - f->bottom_inset;
}
float exr_flow_room(const flow *f) {
  return f->layout->options.height - 2 * f->layout->options.margin - f->bottom_inset;
}
static exr_status fail(flow *f, exr_status code, const char *message) {
  return exr_fail(f->error, code, "%s", message);
}
exr_status exr_flow_page(flow *f, float height, size_t offset) {
  exr_layout *l = f->layout;
  exr_page *p;
  if (f->paginate && height > exr_flow_room(f) + 0.01f)
    return fail(f, EXR_LIMIT, "Unbreakable content exceeds page height");
  if (!l->page_count || (f->paginate && (f->force_break || f->y + height > exr_flow_bottom(f)))) {
    if (l->page_count && f->y <= exr_flow_top(f) && !f->force_break)
      return EXR_OK;
    if (f->page_limit && l->page_count >= (size_t)f->page_limit)
      return EXR_PAUSE;
    if (!exr_grow((void **)&l->pages, &l->page_cap, l->page_count + 1, sizeof(*l->pages)))
      return EXR_MEMORY;
    p = &l->pages[l->page_count++];
    memset(p, 0, sizeof(*p));
    p->start = p->end = offset == SIZE_MAX ? 0 : offset;
    p->line_start = l->line_count;
    f->y = exr_flow_top(f);
  }
  f->force_break = 0;
  return EXR_OK;
}
static float glyph_kern(flow *f, const exr_glyph *previous, const exr_glyph *g) {
  if (!previous || ((previous->flags | g->flags) & (EXR_GLYPH_HIDDEN | EXR_GLYPH_SHAPED)) ||
      previous->font_index != g->font_index || previous->size != g->size ||
      (previous->flags & 3) != (g->flags & 3) ||
      ((g->flags & EXR_GLYPH_VERTICAL) && !(g->flags & EXR_GLYPH_SIDEWAYS)))
    return 0;
  return exr_kern(&f->font->faces[g->font_index], previous->glyph, g->glyph);
}
exr_status exr_flow_cluster(flow *f, size_t start, size_t end) {
  exr_layout *l = f->layout;
  size_t i, face, common = SIZE_MAX, order[32], count, at;
  uint32_t candidates = f->font->count == 32 ? UINT32_MAX :
                          (UINT32_C(1) << f->font->count) - 1;
  if (l->glyphs[start].flags & EXR_GLYPH_RUBY_ITEM) return EXR_OK;
  /* Prefer a single face for the complete visible grapheme, across inline styles. */
  for (i = start; i < end && candidates; i++) {
    const exr_glyph *g = &l->glyphs[i];
    uint32_t allowed = 0;
    uint32_t cp = g->codepoint == '\t' ? ' ' : g->codepoint;
    if (g->bidi_level != UINT_MAX && (g->bidi_level & 1)) cp = exr_bidi_mirror(cp);
    if (g->flags & EXR_GLYPH_HIDDEN)
      continue;
    count = exr_font_order(f->font, f->styles[g->node].family, f->styles[g->node].flags,
                            f->doc->nodes[g->node].chapter, order);
    for (at = 0; at < count; at++) allowed |= UINT32_C(1) << order[at];
    candidates &= allowed;
    for (face = 0; face < f->font->count; face++)
      if ((candidates & (UINT32_C(1) << face)) &&
          !exr_font_has_glyph(f->font, face, cp) && !(i+1<end && exr_text_variation_selector(l->glyphs[i+1].codepoint) &&
          FT_Face_GetCharVariantIndex(f->font->faces[face].face,cp,l->glyphs[i+1].codepoint)))
        candidates &= ~(UINT32_C(1) << face);
  }
  /* Prefer an explicit UVS mapping among faces that cover the whole grapheme.
     Unsupported selectors retain the ordinary scalar fallback order. */
  for(i=start+1;i<end && candidates;i++) {
    uint32_t supported=0,cp=l->glyphs[i].codepoint,base=l->glyphs[i-1].codepoint;
    if(!exr_text_variation_selector(cp) || exr_text_variation_selector(base)) continue;
    if(l->glyphs[i-1].bidi_level!=UINT_MAX && (l->glyphs[i-1].bidi_level&1)) base=exr_bidi_mirror(base);
    for(face=0;face<f->font->count;face++) if((candidates&(UINT32_C(1)<<face)) && FT_Face_GetCharVariantIndex(f->font->faces[face].face,base,cp)) supported|=UINT32_C(1)<<face;
    if(supported) candidates=supported;
  }
  count = exr_font_order(f->font, f->styles[l->glyphs[start].node].family,
                          f->styles[l->glyphs[start].node].flags,
                          f->doc->nodes[l->glyphs[start].node].chapter, order);
  for (at = 0; at < count; at++)
    if (candidates & (UINT32_C(1) << order[at])) {
      common = order[at];
      break;
    }
  for (i = start; i < end; i++) {
    exr_glyph *g = &l->glyphs[i];
    uint32_t cp = g->codepoint == '\t' ? ' ' : g->codepoint;
    exr_face *selected;
    if (g->bidi_level != UINT_MAX && (g->bidi_level & 1)) cp = exr_bidi_mirror(cp);
    g->cluster_start = l->glyphs[start].start;
    g->cluster_end = l->glyphs[end - 1].end;
    if (g->flags & EXR_GLYPH_HIDDEN)
      continue;
    face = common;
    if (face == SIZE_MAX) {
      count = exr_font_order(f->font, f->styles[g->node].family, f->styles[g->node].flags,
                              f->doc->nodes[g->node].chapter, order);
      for (at = 0; at < count; at++) {
        face = order[at];
        if (exr_font_has_glyph(f->font, face, cp))
          break;
      }
      if (at == count) {
        face = 0;
        g->flags |= EXR_GLYPH_MISSING;
      }
    }
    g->font_index = face;
    selected = &f->font->faces[face];
    g->flags &= ~selected->style_flags;
    g->glyph = FT_Get_Char_Index(selected->face, cp);
    if (exr_font_size(selected, g->size) ||
        ((g->flags & EXR_GLYPH_VERTICAL) && !(g->flags & EXR_GLYPH_SIDEWAYS) ?
         exr_measure_vertical(selected, g->glyph, g->flags, &g->advance) :
         exr_measure(selected, g->glyph, g->flags, &g->advance)))
      return fail(f, EXR_FONT, "Cannot measure selected font");
    if (g->codepoint == '\t')
      g->advance *= 4;
  }
  return EXR_OK;
}
static exr_status project_line(flow *f, exr_line *line) {
  size_t j;
  float start = line->y, height = line->height, x = line->x, width = line->width;
  f->used_inline = fmaxf(f->used_inline, x + width + f->inline_end_inset);
  if (f->writing_mode == EXR_WRITING_HORIZONTAL_TB) return EXR_OK;
  for (j = line->glyph_start; j < line->glyph_start + line->glyph_count; j++) {
    exr_glyph *g = &f->layout->glyphs[j];
    float pen = g->x, baseline = g->baseline;
    if (!(j & 255) && exr_control_cancel(&f->config->control, f->error) != EXR_OK) return EXR_CANCELLED;
    if (g->flags & EXR_GLYPH_SIDEWAYS)
      g->x = f->writing_mode == EXR_WRITING_VERTICAL_RL ? f->origin_x - baseline :
                                                       2 * start + height - baseline;
    else {
      exr_face *face = &f->font->faces[g->font_index];
      FT_Glyph_Metrics metrics;
      if(face->bitmap_only) {
        float ox=0,oy=0;
        exr_status status=exr_font_bitmap_vertical(face,g->glyph,g->size,&ox,&oy,&f->config->control,f->error); if(status!=EXR_OK) return status;
        g->x=f->writing_mode==EXR_WRITING_VERTICAL_RL ? f->origin_x-start-height/2 : start+height/2;
        g->offset_x+=ox; g->offset_y+=oy; g->baseline=pen; continue;
      }
      if (exr_font_size(face, g->size) || FT_Load_Glyph(face->face, g->glyph, FT_LOAD_VERTICAL_LAYOUT))
        return fail(f, EXR_FONT, "Cannot position vertical font glyph");
      metrics = face->face->glyph->metrics;
      g->x = f->writing_mode == EXR_WRITING_VERTICAL_RL ? f->origin_x - start - height / 2 :
                                                       start + height / 2;
      g->offset_x += (float)(metrics.vertBearingX - metrics.horiBearingX) / 64;
      g->offset_y -= (float)(metrics.vertBearingY + metrics.horiBearingY) / 64;
    }
    g->baseline = pen;
  }
  line->x = f->writing_mode == EXR_WRITING_VERTICAL_RL ? f->origin_x - start - height : start;
  line->y = x; line->width = height; line->height = width;
  return EXR_OK;
}
static exr_status append_fragment(flow *f, const exr_line *source, const exr_glyph *glyphs,
                                    float dx, float dy) {
  exr_layout *l=f->layout;
  size_t i, destination=l->glyph_count;
  exr_line *line;
  if (source->glyph_count > EXR_MAX_ITEMS-destination || l->line_count >= EXR_MAX_ITEMS ||
      !exr_grow((void **)&l->glyphs,&l->glyph_cap,destination+source->glyph_count,sizeof(*l->glyphs)) ||
      !exr_grow((void **)&l->lines,&l->line_cap,l->line_count+1,sizeof(*l->lines)))
    return fail(f,EXR_LIMIT,"Inline fragment allocation limit exceeded");
  line=&l->lines[l->line_count++]; *line=*source;
  line->glyph_start=destination; line->page=l->page_count-1; line->x+=dx; line->y+=dy;
  for(i=0;i<source->glyph_count;i++) {
    exr_glyph g=glyphs[i]; g.x+=dx; g.baseline+=dy; g.clip_left+=dx; g.clip_right+=dx;
    g.page=line->page; l->glyphs[l->glyph_count++]=g;
  }
  l->pages[line->page].line_count++;
  return project_line(f,line);
}
static exr_status ordinary_fragment(flow *f, exr_glyph *glyphs, size_t count, float baseline) {
  exr_line line={0};
  float ascent=0,descent=0,height=0;
  size_t i;
  line.start=SIZE_MAX;
  for(i=0;i<count;i++) {
    exr_glyph *g=&glyphs[i]; exr_face *face=&f->font->faces[g->font_index];
    if(f->intrinsic && !(i&255) && exr_control_cancel(&f->config->control,f->error)!=EXR_OK) return EXR_CANCELLED;
    if(exr_font_size(face,g->size)) return EXR_FONT;
    ascent=fmaxf(ascent,exr_font_ascent(face));
    descent=fmaxf(descent,exr_font_descent(face));
    height=fmaxf(height,g->line_height);
    if(g->start<line.start) line.start=g->start;
    if(g->end>line.end) line.end=g->end;
    g->baseline=baseline; g->clip_left=f->x; g->clip_right=f->x+f->width;
  }
  height=fmaxf(height,ascent+descent);
  line.glyph_count=count; line.x=glyphs[0].x;
  line.y=baseline-ascent-(height-ascent-descent)/2;
  line.width=glyphs[count-1].x+glyphs[count-1].advance-line.x; line.height=height;
  return append_fragment(f,&line,glyphs,0,0);
}
exr_status exr_flow_emit_line(flow *f, exr_glyph *glyphs, size_t count, int forced, int final) {
  exr_layout *l=f->layout;
  size_t i,j,spaces=0,logical_start=glyphs[0].start,logical_end=glyphs[count-1].end;
  float indent=f->first_line ? f->paragraph->indent : 0;
  float available=fmaxf(1,f->width-indent),width=0,ascent=0,descent=0,height=0,x,extra=0,baseline;
  int align=f->intrinsic ? 0 : f->paragraph->align;
  unsigned base=exr_inline_base(f->bidi,logical_start);
  exr_status status;
  if(f->intrinsic) {
    while(count && (glyphs[count-1].codepoint==' ' || glyphs[count-1].codepoint=='\t')) count--;
    if(!count) return EXR_OK;
  }
  if(align==4) align=base&1 ? 2 : 0;
  if(align==5) align=base&1 ? 0 : 2;
  for(i=0;i<count;i++) {
    exr_glyph *g=&glyphs[i]; exr_face *face=&f->font->faces[g->font_index];
    if(g->flags&EXR_GLYPH_RUBY_ITEM) {
      if(!f->intrinsic && g->advance>available+.001f) return fail(f,EXR_LIMIT,"Ruby group exceeds the inline page extent");
      ascent=fmaxf(ascent,g->offset_x); descent=fmaxf(descent,g->offset_y);
    } else {
      if(exr_font_size(face,g->size)) return EXR_FONT;
      ascent=fmaxf(ascent,exr_font_ascent(face));
      descent=fmaxf(descent,exr_font_descent(face));
    }
    width+=g->advance+glyph_kern(f,i ? &glyphs[i-1] : NULL,g);
    height=fmaxf(height,g->line_height);
    if(g->codepoint==' ' && (i+1==count || glyphs[i+1].cluster_start!=g->cluster_start)) spaces++;
  }
  height=fmaxf(height,ascent+descent);
  if(f->intrinsic) {
    f->intrinsic_extent=fmax(f->intrinsic_extent,f->x+width+fmaxf(0,indent)+f->inline_end_inset);
    f->first_line=0;
    return EXR_OK; /* Measurement commits no second full glyph/line snapshot. */
  }
  status=exr_flow_page(f,height,logical_start); if(status!=EXR_OK) return status;
  status=exr_inline_reorder(f,glyphs,count); if(status!=EXR_OK) return status;
  baseline=f->y+ascent+(height-ascent-descent)/2;
  x=f->x+(base&1 ? 0 : indent);
  if(align==1) x+=fmaxf(0,available-width)/2;
  if(align==2) x+=fmaxf(0,available-width);
  if(align==3 && !final && !forced && spaces) extra=fmaxf(0,available-width)/(float)spaces;
  for(i=0;i<count;) {
    exr_glyph *g=&glyphs[i];
    if(g->flags&EXR_GLYPH_RUBY_ITEM) {
      exr_layout *ruby=NULL;
      status=exr_ruby_layout(f,g,&ruby); if(status!=EXR_OK) return status;
      for(j=0;j<ruby->line_count && status==EXR_OK;j++)
        status=append_fragment(f,&ruby->lines[j],ruby->glyphs+ruby->lines[j].glyph_start,x,baseline-g->offset_x);
      exr_layout_free(ruby); if(status!=EXR_OK) return status;
      x+=g->advance; i++;
    } else {
      size_t first=i;
      for(;i<count && !(glyphs[i].flags&EXR_GLYPH_RUBY_ITEM);i++) {
        g=&glyphs[i]; x+=glyph_kern(f,i ? &glyphs[i-1] : NULL,g); g->x=x; x+=g->advance;
        if(g->codepoint==' ' && (i+1==count || glyphs[i+1].cluster_start!=g->cluster_start)) x+=extra;
      }
      status=ordinary_fragment(f,glyphs+first,i-first,baseline); if(status!=EXR_OK) return status;
      /* Keep the original justified line rectangle, including the last space. */
      if(first==0 && i==count && l->line_count) {
        exr_line *line=&l->lines[l->line_count-1];
        if(f->writing_mode==EXR_WRITING_HORIZONTAL_TB) line->width=width+extra*(float)spaces;
        else line->height=width+extra*(float)spaces;
      }
    }
  }
  l->pages[l->page_count-1].end=logical_end;
  f->y+=height; f->first_line=0; return EXR_OK;
}
exr_box *exr_flow_box(flow *f, size_t node, size_t p, float x, float y, float width, float height,
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
  if(f->intrinsic && kind==EXR_BOX_IMAGE) f->intrinsic_extent=fmax(f->intrinsic_extent,x+width+f->inline_end_inset);
  f->used_inline = fmaxf(f->used_inline, x + width + (kind == EXR_BOX_IMAGE ? f->inline_end_inset : 0));
  if (f->writing_mode != EXR_WRITING_HORIZONTAL_TB) {
    b->x = f->writing_mode == EXR_WRITING_VERTICAL_RL ? f->origin_x - y - b->height : y;
    b->y = x; b->width = b->height; b->height = width;
  }
  b->background = s->background;
  b->border_color = s->border_color;
  b->border_width = s->border_style ? s->border_width : 0;
  return b;
}
exr_status exr_layout_image_asset(const exr_document *doc,exr_layout *l,
                                    const exr_layout_config *config,size_t resource,
                                    const exr_bitmap **bitmap,exr_error *e) {
  size_t i,size; void *data=NULL; exr_bitmap decoded={0}; exr_status status;
  *bitmap=NULL;
  if(resource>=doc->resource_count) return exr_fail(e,EXR_ARGUMENT,"Invalid image resource");
  for (i = 0; i < l->image_count; i++)
    if (l->images[i].resource == resource) {
      *bitmap = &l->images[i].bitmap;
      return EXR_OK;
    }
  status = exr_document_resource(doc, resource, &data, &size, e);
  if (status == EXR_OK && config->decode_image) {
    exr_bitmap supplied = {0};
    size_t row;
    status = config->decode_image(config->image_context, &doc->resources[resource], data,
                                     size, &supplied, e);
    if (status == EXR_OK) {
      if (!supplied.pixels || supplied.channels != 4 || !supplied.width || !supplied.height ||
          supplied.width > 8192 || supplied.height > 8192 || supplied.stride < supplied.width * 4 ||
          (size_t)supplied.width * supplied.height > 16 * 1024 * 1024 ||
          (size_t)(supplied.height - 1) > (SIZE_MAX - supplied.width * 4) / supplied.stride)
        status =
            exr_fail(e, EXR_ARGUMENT, "Host image decoder returned an invalid RGBA bitmap");
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
    config->release_image(config->image_context, &supplied);
  } else if (status == EXR_OK)
    status = exr_image_decode(data, size, &decoded, e);
  exr_free(data);
  if (status != EXR_OK) {
    if(e && e->message[0]) { e->code=status; return status; }
    return exr_fail(e,status,"Image decoding failed");
  }
  size = (size_t)decoded.stride * decoded.height;
  if (size > 64 * 1024 * 1024 - l->image_bytes ||
      !exr_grow((void **)&l->images, &l->image_cap, l->image_count + 1, sizeof(*l->images))) {
    exr_bitmap_free(&decoded);
    return exr_fail(e,EXR_LIMIT,"Decoded image cache exceeds 64 MiB");
  }
  l->images[l->image_count].resource = resource;
  l->images[l->image_count].refs = malloc(sizeof(size_t));
  if (!l->images[l->image_count].refs) {
    exr_bitmap_free(&decoded);
    return exr_fail(e,EXR_MEMORY,"Image reference allocation failed");
  }
  *l->images[l->image_count].refs = 1;
  l->images[l->image_count].bitmap = decoded;
  *bitmap = &l->images[l->image_count++].bitmap;
  l->image_bytes += size;
  return EXR_OK;
}
static exr_status image_asset(flow *f, size_t node, size_t *resource, const exr_bitmap **bitmap) {
  size_t target;
  exr_error ignored = {0};
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
  status=exr_layout_image_asset(f->doc,f->assets,f->config,*resource,bitmap,&ignored);
  if(status==EXR_FORMAT) return EXR_OK;
  return status==EXR_OK ? EXR_OK : fail(f,status,ignored.message[0] ? ignored.message : "Image decoding failed");
}
exr_status exr_flow_image(flow *f, size_t node, float x, float width) {
  exr_style logical = exr_flow_style(&f->styles[node], f->writing_mode);
  if(f->intrinsic) {
    if(logical.width.percent) logical.width.value=-1;
    if(logical.height.percent) logical.height.value=-1;
    if(logical.max_width.percent) logical.max_width.value=-1;
    if(logical.max_height.percent) logical.max_height.value=-1;
  }
  const exr_style *s = &logical;
  const exr_bitmap *bitmap;
  size_t resource;
  float w, h, scale;
  exr_box *b;
  exr_status status = image_asset(f, node, &resource, &bitmap);
  if (status != EXR_OK)
    return status;
  w = bitmap ? (float)bitmap->width : 160;
  h = bitmap ? (float)bitmap->height : 80;
  if (f->writing_mode != EXR_WRITING_HORIZONTAL_TB) { float swap = w; w = h; h = swap; }
  scale = 1;
  if (s->width.value >= 0)
    scale = used(s->width, width) / w;
  if (s->height.value >= 0) {
    float by_height = used(s->height, exr_flow_room(f)) / h;
    scale = s->width.value >= 0 ? fminf(scale, by_height) : by_height;
  }
  w *= scale;
  h *= scale;
  if (w <= 0 || h <= 0)
    return EXR_OK;
  scale = fminf(1, fminf(width / w, exr_flow_room(f) / h));
  if (s->max_width.value >= 0)
    scale = fminf(scale, used(s->max_width, width) / w);
  if (s->max_height.value >= 0)
    scale = fminf(scale, used(s->max_height, exr_flow_room(f)) / h);
  w *= scale;
  h *= scale;
  status = exr_flow_page(f, h, f->doc->nodes[node].start);
  if (status != EXR_OK)
    return status;
  if (s->margin[3].value < 0)
    x += (width - w) / (s->margin[1].value < 0 ? 2 : 1);
  else if (s->align == 1)
    x += (width - w) / 2;
  else if (s->align == 2)
    x += width - w;
  b = exr_flow_box(f, node, f->layout->page_count - 1, x, f->y, w, h, EXR_BOX_IMAGE);
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
typedef struct {
  size_t node;
  exr_layout *layout;
} cell;
static exr_status copy_cell(flow *f, const cell *c, float x, float y, float height) {
  exr_layout *l = f->layout, *from = c->layout;
  size_t i, offset = l->glyph_count, p = l->page_count - 1;
  int vertical = f->writing_mode != EXR_WRITING_HORIZONTAL_TB;
  int from_vertical = from->writing_mode != EXR_WRITING_HORIZONTAL_TB;
  float physical_width = from_vertical ? from->flow_block : from->flow_inline;
  float physical_height = from_vertical ? from->flow_inline : from->flow_block;
  float block = vertical ? physical_width : physical_height;
  float dx = vertical ? (f->writing_mode == EXR_WRITING_VERTICAL_RL ? f->origin_x-y-block : y) : x;
  float dy = vertical ? x : y;
  if(f->intrinsic) f->intrinsic_extent=fmax(f->intrinsic_extent,x+(vertical ? physical_height : physical_width)+f->inline_end_inset);
  if (from->writing_mode == EXR_WRITING_VERTICAL_RL) dx += from->flow_block;
  f->used_inline = fmaxf(f->used_inline, x + (vertical ? physical_height : physical_width) + f->inline_end_inset);
  if (from->glyph_count > EXR_MAX_ITEMS - l->glyph_count ||
      !exr_grow((void **)&l->glyphs, &l->glyph_cap, l->glyph_count + from->glyph_count,
                sizeof(exr_glyph)) ||
      !exr_grow((void **)&l->lines, &l->line_cap, l->line_count + from->line_count,
                sizeof(exr_line)) ||
      !exr_grow((void **)&l->boxes, &l->box_cap, l->box_count + from->box_count, sizeof(exr_box)))
    return EXR_LIMIT;
  for (i = 0; i < from->glyph_count; i++) {
    exr_glyph v = from->glyphs[i];
    v.x += dx;
    v.baseline += dy;
    v.clip_left += (v.flags & EXR_GLYPH_VERTICAL) ? dy : dx;
    v.clip_right += (v.flags & EXR_GLYPH_VERTICAL) ? dy : dx;
    v.page = p;
    l->glyphs[l->glyph_count++] = v;
  }
  for (i = 0; i < from->line_count; i++) {
    exr_line v = from->lines[i];
    v.x += dx;
    v.y += dy;
    v.page = p;
    v.glyph_start += offset;
    l->lines[l->line_count++] = v;
    l->pages[p].line_count++;
    if (v.end > l->pages[p].end)
      l->pages[p].end = v.end;
  }
  for (i = 0; i < from->box_count; i++) {
    exr_box v = from->boxes[i];
    v.x += dx;
    v.y += dy;
    v.page = p;
    if (v.node == c->node && v.kind == EXR_BOX_CELL) {
      if (vertical) {
        if (f->writing_mode == EXR_WRITING_VERTICAL_RL) v.x -= height - v.width;
        v.width = height;
      } else v.height = height;
    }
    l->boxes[l->box_count++] = v;
  }
  f->pending = l->glyph_count;
  if (from->page_count && from->pages[from->page_count-1].end > l->pages[p].end)
    l->pages[p].end = from->pages[from->page_count-1].end;
  return EXR_OK;
}
exr_status exr_layout_validate(const exr_layout_config *config, exr_error *e) {
  exr_layout_options o = config->page;
  if (config->direction < EXR_DIRECTION_AUTO || config->direction > EXR_DIRECTION_RTL ||
      (config->decode_image && !config->release_image) || !isfinite(o.width) ||
      !isfinite(o.height) || !isfinite(o.margin) || !isfinite(o.font_size) ||
      !isfinite(o.line_height) || !isfinite(o.paragraph_spacing) || o.width < 32 || o.height < 32 ||
      o.width > 16384 || o.height > 16384 || o.margin < 0 || o.font_size < 4 || o.font_size > 256 ||
      o.line_height < 1 || o.line_height > 5 || o.paragraph_spacing < 0 ||
      o.paragraph_spacing > 1024 || o.width - 2 * o.margin < o.font_size * 1.5f ||
      o.height - 2 * o.margin < o.font_size * o.line_height)
    return exr_fail(e, EXR_ARGUMENT, "Invalid page geometry or document");
  return EXR_OK;
}

exr_status exr_flow_copy(flow *f, const exr_layout *from, size_t index,
                          float x, float y, float height) {
  cell c = {0};
  c.node = index;
  c.layout = (exr_layout *)from;
  return copy_cell(f, &c, x, y, height);
}
