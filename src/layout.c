/* SPDX-License-Identifier: GPL-3.0-only */
#include "layout_internal.h"
#include "opentype_internal.h"
#include FT_SYNTHESIS_H
#include FT_PARAMETER_TAGS_H
#include FT_TRUETYPE_TABLES_H
FT_Error exr_font_face_open(FT_Library library,const void *data,size_t size,unsigned face_index,FT_Face *out) {
  FT_Parameter parameter={FT_PARAM_TAG_IGNORE_SBIX,NULL}; FT_Open_Args open={0};
  open.flags=FT_OPEN_MEMORY|FT_OPEN_PARAMS; open.memory_base=data; open.memory_size=(FT_Long)size;
  open.num_params=1; open.params=&parameter;
  return FT_Open_Face(library,&open,(FT_Long)face_index,out);
}
int exr_font_face_supported(FT_Face face) {
  FT_ULong data=0,locations=0;
  return FT_IS_SCALABLE(face) || (FT_IS_SFNT(face) && FT_HAS_COLOR(face) && face->num_fixed_sizes>0 && face->num_fixed_sizes<=256 &&
    !FT_Load_Sfnt_Table(face,FT_MAKE_TAG('C','B','D','T'),0,NULL,&data) && data>=4 &&
    !FT_Load_Sfnt_Table(face,FT_MAKE_TAG('C','B','L','C'),0,NULL,&locations) && locations>=8);
}
static int bitmap_metrics(exr_face *face) {
  const TT_Header *head=FT_Get_Sfnt_Table(face->face,ft_sfnt_head);
  const TT_HoriHeader *hori=FT_Get_Sfnt_Table(face->face,ft_sfnt_hhea);
  const TT_VertHeader *vert=FT_Get_Sfnt_Table(face->face,ft_sfnt_vhea); FT_ULong size=0;
  if(!head || !head->Units_Per_EM || !hori || !hori->number_Of_HMetrics || hori->number_Of_HMetrics>face->face->num_glyphs) return 0;
  face->design_units=head->Units_Per_EM; face->hmetrics=hori->number_Of_HMetrics;
  if(FT_Load_Sfnt_Table(face->face,FT_MAKE_TAG('h','m','t','x'),0,NULL,&size) ||
     size<4*(uint64_t)face->hmetrics+2*((uint64_t)face->face->num_glyphs-face->hmetrics)) return 0;
  if(vert) {
    size=0;
    face->vmetrics=vert->number_Of_VMetrics;
    if(!face->vmetrics || face->vmetrics>(uint64_t)face->face->num_glyphs ||
       FT_Load_Sfnt_Table(face->face,FT_MAKE_TAG('v','m','t','x'),0,NULL,&size) ||
       size<4*(uint64_t)face->vmetrics+2*((uint64_t)face->face->num_glyphs-face->vmetrics)) return 0;
  }
  return 1;
}
static exr_status create_font(const exr_font_input *inputs,size_t count,int unicode,exr_font **out,exr_error *e) {
  exr_font *font;
  size_t i, total = 0;
  exr_status status = EXR_FONT;
  const char *message = unicode ? "Font must contain a supported Unicode face" : "Font must contain a supported face";
  if (!out)
    return exr_fail(e, EXR_ARGUMENT, "Missing font output");
  *out = NULL;
  if (!inputs || !count)
    return exr_fail(e, EXR_ARGUMENT, "Missing font inputs");
  if (count > 32)
    return exr_fail(e, EXR_LIMIT, "Font list exceeds 32 faces");
  for (i = 0; i < count; i++) {
    if (!inputs[i].data || !inputs[i].size || inputs[i].face_index > INT_MAX)
      return exr_fail(e, EXR_ARGUMENT, "Invalid font input");
    if (inputs[i].size > EXR_MAX_INPUT - total)
      return exr_fail(e, EXR_LIMIT, "Font bytes exceed 128 MiB");
    total += inputs[i].size;
  }
  font = calloc(1, sizeof(*font));
  if (!font)
    return exr_fail(e, EXR_MEMORY, "Font allocation failed");
  font->refs = 1;
  font->faces = calloc(count, sizeof(*font->faces));
  if (!font->faces) {
    status = EXR_MEMORY;
    message = "Font list allocation failed";
    goto bad;
  }
  font->count = font->base_count = count;
  if (FT_Init_FreeType(&font->library))
    goto bad;
  for (i = 0; i < count; i++) {
    exr_face *face = &font->faces[i];
    face->bytes = malloc(inputs[i].size);
    if (!face->bytes) {
      status = EXR_MEMORY;
      message = "Font data allocation failed";
      goto bad;
    }
    memcpy(face->bytes, inputs[i].data, inputs[i].size);
    face->bytes_size = inputs[i].size;
    face->scope = SIZE_MAX;
    /* sbix images use the shared PNG/JPEG decoder; keep scalable text metrics. */
    if (exr_font_face_open(font->library,face->bytes,inputs[i].size,inputs[i].face_index,&face->face) ||
        !exr_font_face_supported(face->face))
      goto bad;
    face->bitmap_only=!FT_IS_SCALABLE(face->face); face->bitmap_scale_y=1;
    face->design_units=face->face->units_per_EM;
    if((face->bitmap_only && !bitmap_metrics(face)) || !face->design_units) goto bad;
    if (FT_Select_Charmap(face->face, FT_ENCODING_UNICODE)) {
      if (unicode) goto bad;
      /* Codepoint lookup must not mistake an arbitrary encoding for Unicode. */
      face->face->charmap = NULL;
    }
    if (face->face->family_name)
      snprintf(face->family, sizeof(face->family), "%s", face->face->family_name);
    face->style_flags = ((face->face->style_flags & FT_STYLE_FLAG_BOLD) ? 1u : 0u) |
                         ((face->face->style_flags & FT_STYLE_FLAG_ITALIC) ? 2u : 0u);
    if (face->face->num_glyphs > 0 && face->face->num_glyphs <= 65536) {
      face->metric_count = (size_t)face->face->num_glyphs;
      face->advances = calloc(face->metric_count, sizeof(*face->advances));
      face->measured = calloc(face->metric_count, 1);
      if (!face->advances || !face->measured) {
        status = EXR_MEMORY;
        message = "Font metrics allocation failed";
        goto bad;
      }
    }
  }
  *out = font;
  return exr_fail(e, EXR_OK, "");
bad:
  exr_font_free(font);
  return exr_fail(e, status, "%s", message);
}
exr_status exr_font_create(const exr_font_input *inputs,size_t count,exr_font **out,exr_error *e) {
  return create_font(inputs,count,1,out,e);
}
exr_status exr_font_create_glyphs(const exr_font_input *inputs,size_t count,exr_font **out,exr_error *e) {
  return create_font(inputs,count,0,out,e);
}
exr_status exr_font_open(const char *path, exr_font **out, exr_error *e) {
  unsigned char *bytes = NULL;
  size_t size;
  exr_status status;
  if (!out)
    return exr_fail(e, EXR_ARGUMENT, "Missing font output");
  *out = NULL;
  if (!path)
    return exr_fail(e, EXR_ARGUMENT, "Missing font path");
  status = exr_read(path, &bytes, &size, e);
  if (status == EXR_OK) {
    exr_font_input input = {bytes, size, 0};
    status = exr_font_create(&input, 1, out, e);
  }
  free(bytes);
  return status;
}
size_t exr_font_count(const exr_font *font) { return font ? font->count : 0; }
int exr_font_has_glyph(const exr_font *font, size_t index, uint32_t cp) {
  return font && index < font->count && cp <= 0x10ffff && !(cp >= 0xd800 && cp <= 0xdfff) &&
         FT_Get_Char_Index(font->faces[index].face, cp) != 0;
}
void exr_font_free(exr_font *f) {
  size_t i;
  if (f && --f->refs) return;
  if (f) {
    for (i = 0; i < f->count; i++) {
      exr_face *face = &f->faces[i];
      exr_ot_free(face);
      exr_font_bitmaps_free(face);
      if (face->face)
        FT_Done_Face(face->face);
      free(face->advances);
      free(face->measured);
      free(face->bytes);
    }
    if (f->library)
      FT_Done_FreeType(f->library);
    exr_font_free(f->fallback);
    free(f->faces);
    free(f);
  }
}
void exr_font_ref(exr_font *f) { if (f) f->refs++; }
exr_font *exr_layout_font(const exr_layout *l) { return l ? l->font : NULL; }
exr_status exr_font_source(const exr_font *font, size_t index, exr_font_input *out, exr_error *e) {
  if (!out) return exr_fail(e, EXR_ARGUMENT, "Missing font source output");
  memset(out, 0, sizeof(*out));
  if (!font || index >= font->count) return exr_fail(e, EXR_ARGUMENT, "Invalid font source index");
  *out = (exr_font_input){font->faces[index].bytes, font->faces[index].bytes_size,
                           (size_t)font->faces[index].face->face_index};
  return exr_fail(e, EXR_OK, "");
}
int exr_font_size(exr_face *font, float pixels) {
  FT_F26Dot6 size = (FT_F26Dot6)lroundf(pixels * 64);
  if (font->metric_size == size)
    return 0;
  if(font->bitmap_only) {
    int i,selected=-1; double best=0;
    for(i=0;i<font->face->num_fixed_sizes;i++) {
      double ppem=font->face->available_sizes[i].y_ppem/64.0;
      if(ppem<=0) return 1;
      if(selected<0 || (ppem>=pixels && (best<pixels || ppem<best)) || (ppem<pixels && best<pixels && ppem>best)) { selected=i; best=ppem; }
    }
    if(selected<0 || FT_Select_Size(font->face,selected) || !font->face->size->metrics.x_ppem || !font->face->size->metrics.y_ppem) return 1;
    font->bitmap_scale_y=pixels/font->face->size->metrics.y_ppem;
  } else if(FT_Set_Char_Size(font->face,0,size,72,72)) return 1;
  font->metric_size = size;
  if (font->measured)
    memset(font->measured, 0, font->metric_count);
  return 0;
}
static int measure(exr_face *font, uint32_t glyph, unsigned flags, int vertical, float *advance) {
  unsigned key;
  flags &= EXR_GLYPH_BOLD | EXR_GLYPH_ITALIC;
  key = flags + 1 + (vertical ? 4u : 0u);
  if (glyph < font->metric_count && font->measured[glyph] == key) {
    *advance = font->advances[glyph];
    return 0;
  }
  if(font->bitmap_only) {
    unsigned metrics=vertical ? font->vmetrics : font->hmetrics;
    if(!metrics) *advance=(float)font->metric_size/64;
    else {
      unsigned char bytes[2]; FT_ULong n=2; uint32_t index=glyph<metrics ? glyph : metrics-1;
      if(FT_Load_Sfnt_Table(font->face,vertical ? FT_MAKE_TAG('v','m','t','x') : FT_MAKE_TAG('h','m','t','x'),(FT_Long)index*4,bytes,&n) || n!=2) return 1;
      *advance=((unsigned)bytes[0]*256+bytes[1])*(float)font->metric_size/(64*font->design_units);
    }
  } else {
    if (FT_Load_Glyph(font->face, glyph, vertical ? FT_LOAD_VERTICAL_LAYOUT : FT_LOAD_DEFAULT)) return 1;
    if(flags&1) FT_GlyphSlot_Embolden(font->face->glyph);
    *advance=(float)(vertical ? font->face->glyph->advance.y : font->face->glyph->advance.x)/64;
    if(vertical && !FT_HAS_VERTICAL(font->face)) *advance=(float)font->metric_size/64;
  }
  if (glyph < font->metric_count) {
    font->advances[glyph] = *advance;
    font->measured[glyph] = (unsigned char)key;
  }
  return 0;
}
int exr_measure(exr_face *font, uint32_t glyph, unsigned flags, float *advance) {
  return measure(font, glyph, flags, 0, advance);
}
int exr_measure_vertical(exr_face *font, uint32_t glyph, unsigned flags, float *advance) {
  return measure(font, glyph, flags, 1, advance);
}
exr_writing_mode exr_layout_writing_mode(const exr_layout *l) {
  return l ? l->writing_mode : EXR_WRITING_HORIZONTAL_TB;
}
exr_status exr_glyph_matrix(const exr_glyph *g, double matrix[6], exr_error *e) {
  double scale;
  if (matrix) memset(matrix, 0, 6 * sizeof(*matrix));
  if (!g || !matrix || !isfinite(g->x) || !isfinite(g->baseline) ||
      !isfinite(g->offset_x) || !isfinite(g->offset_y) || !isfinite(g->size) ||
      g->size < 0 || g->size > 4096 || (g->flags & ~(511u|EXR_GLYPH_GENERATED)) ||
      ((g->flags & EXR_GLYPH_SIDEWAYS) && !(g->flags & EXR_GLYPH_VERTICAL)))
    return exr_fail(e, EXR_ARGUMENT, "Invalid glyph transformation input");
  scale = (double)g->size / 1000;
  if (g->flags & EXR_GLYPH_SIDEWAYS) {
    matrix[1] = matrix[2] = scale;
    matrix[4] = (double)g->x + g->offset_y;
    matrix[5] = (double)g->baseline + g->offset_x;
  } else {
    matrix[0] = scale; matrix[3] = -scale;
    matrix[4] = (double)g->x + g->offset_x;
    matrix[5] = (double)g->baseline - g->offset_y;
  }
  return exr_fail(e, EXR_OK, "");
}
exr_layout_options exr_layout_defaults(void) {
  exr_layout_options o = {720, 1040, 48, 24, 1.6f, 12};
  return o;
}
float exr_kern(exr_face *f, uint32_t left, uint32_t right) {
  FT_Vector v = {0};
  if (left && right && FT_HAS_KERNING(f->face))
    FT_Get_Kerning(f->face,left,right,f->bitmap_only ? FT_KERNING_UNSCALED : FT_KERNING_DEFAULT,&v);
  return f->bitmap_only ? (float)v.x*(float)f->metric_size/(64*f->design_units) : (float)v.x/64;
}
exr_layout_config exr_layout_config_defaults(void) {
  exr_layout_config config = {0};
  config.page = exr_layout_defaults();
  config.document_css = 1;
  config.embedded_fonts = 1;
  return config;
}
exr_status exr_layout_create_ex(const exr_document *d, exr_font *f, const exr_layout_config *config,
                                exr_layout **out, exr_error *e) {
  exr_layout_config defaults = exr_layout_config_defaults();
  return exr_flow_create(d, f, config ? config : &defaults, out, e);
}
exr_status exr_layout_create(const exr_document *d, exr_font *f, const exr_layout_options *o,
                             exr_layout **out, exr_error *e) {
  exr_layout_config config = exr_layout_config_defaults();
  if (o)
    config.page = *o;
  return exr_layout_create_ex(d, f, &config, out, e);
}
void exr_layout_free(exr_layout *l) {
  if (l && l->refs > 1) { l->refs--; return; }
  if (l) {
    free(l->glyphs);
    free(l->lines);
    size_t i;
    free(l->pages);
    free(l->boxes);
    free(l->paints);
    free(l->positioned);
    exr_styles_free(l->styles, l->style_count);
    exr_font_free(l->font);
    for (i = 0; i < l->image_count; i++) {
      exr_cached_image *image = &l->images[i];
      if (!image->refs || !--*image->refs) {
        exr_bitmap_free(&image->bitmap);
        free(image->refs);
      }
    }
    free(l->images);
    free(l);
  }
}
void exr_layout_ref(exr_layout *l) { if (l) l->refs = l->refs ? l->refs + 1 : 2; }
const exr_page *exr_layout_pages(const exr_layout *l, size_t *n) {
  if (n)
    *n = l ? l->page_count : 0;
  return l ? l->pages : NULL;
}
const exr_line *exr_layout_lines(const exr_layout *l, size_t *n) {
  if (n)
    *n = l ? l->line_count : 0;
  return l ? l->lines : NULL;
}
const exr_glyph *exr_layout_glyphs(const exr_layout *l, size_t *n) {
  if (n)
    *n = l ? l->glyph_count : 0;
  return l ? l->glyphs : NULL;
}
const exr_paint *exr_layout_paints(const exr_layout *l,size_t page,size_t *count) {
  if(count) *count=0;
  if(!l || !l->positioned || page>=l->page_count) return NULL;
  if(count) *count=l->positioned[page].paint_count;
  return l->positioned[page].paint_count ? l->paints+l->positioned[page].paint_start : NULL;
}
size_t exr_layout_page_at(const exr_layout *l, size_t offset) {
  size_t lo = 0, hi;
  if (!l || !l->page_count)
    return SIZE_MAX;
  if(l->source_overlaps) {
    /* ponytail: overlap-only linear lookup; add a range index if host seek profiles need one. */
    size_t i,best=SIZE_MAX,span=SIZE_MAX;
    for(i=0;i<l->glyph_count;i++) {
      const exr_glyph *g=&l->glyphs[i];
      /* A shaped cluster can bridge out-of-flow text in source order. Prefer
         the narrowest actual range, e.g. a float's own glyph over that cluster. */
      if(g->start<=offset && offset<g->end && g->end-g->start<span) {
        best=g->page; span=g->end-g->start;
      }
    }
    if(best!=SIZE_MAX) return best;
    { size_t start=0; int found=0; best=0;
      for(i=0;i<l->page_count;i++) if(l->pages[i].start<=offset && (!found || l->pages[i].start>=start)) {
        best=i; start=l->pages[i].start; found=1;
      }
      return best;
    }
  }
  hi = l->page_count;
  while (lo + 1 < hi) {
    size_t mid = lo + (hi - lo) / 2;
    if (l->pages[mid].start <= offset)
      lo = mid;
    else
      hi = mid;
  }
  return lo;
}
size_t exr_layout_hit_test(const exr_layout *l, size_t p, float x, float y) {
  const exr_page *page;
  const exr_line *line = NULL;
  const exr_glyph *last_visible = NULL;
  size_t i;
  float distance = INFINITY;
  if (!l || p >= l->page_count || !isfinite(x) || !isfinite(y))
    return SIZE_MAX;
  page = &l->pages[p];
  for (i = page->line_start; i < page->line_start + page->line_count; i++) {
    const exr_line *candidate = &l->lines[i];
    float dx = fmaxf(0, fmaxf(candidate->x - x, x - candidate->x - candidate->width));
    float dy = fmaxf(0, fmaxf(candidate->y - y, y - candidate->y - candidate->height));
    float delta = dx * dx + dy * dy;
    if (delta < distance) {
      distance = delta;
      line = candidate;
    }
  }
  if (!line)
    return page->start;
  for (i = line->glyph_start; i < line->glyph_start + line->glyph_count;) {
    const exr_glyph *g = &l->glyphs[i];
    size_t end = i + 1;
    int visible = !(g->flags & EXR_GLYPH_HIDDEN);
    int vertical = !!(g->flags & EXR_GLYPH_VERTICAL);
    float position = vertical ? y : x;
    float left = vertical ? g->baseline : g->x, right = left + g->advance;
    while (end < line->glyph_start + line->glyph_count &&
           l->glyphs[end].cluster_start == g->cluster_start) {
      float pen = vertical ? l->glyphs[end].baseline : l->glyphs[end].x;
      left = fminf(left, pen);
      right = fmaxf(right, pen + l->glyphs[end].advance);
      visible |= !(l->glyphs[end].flags & EXR_GLYPH_HIDDEN);
      end++;
    }
    if (visible) last_visible = g;
    if (visible && position <= right)
      return (position < (left + right) / 2) != (g->bidi_level & 1) ?
                 g->cluster_start : g->cluster_end;
    i = end;
  }
  if (last_visible) {
    return last_visible->bidi_level & 1 ? last_visible->cluster_start : last_visible->cluster_end;
  }
  return line->end;
}
const exr_box *exr_layout_boxes(const exr_layout *l, size_t *n) {
  if (n)
    *n = l ? l->box_count : 0;
  return l ? l->boxes : NULL;
}
const exr_bitmap *exr_layout_image(const exr_layout *l, size_t resource) {
  size_t i;
  if (l)
    for (i = 0; i < l->image_count; i++)
      if (l->images[i].resource == resource)
        return &l->images[i].bitmap;
  return NULL;
}
