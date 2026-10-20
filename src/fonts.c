/* SPDX-License-Identifier: MIT */
#include "font_internal.h"
#include "css_internal.h"
#include <ctype.h>

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
      exr_font_svg_free(face);
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
float exr_kern(exr_face *f, uint32_t left, uint32_t right) {
  FT_Vector v = {0};
  if (left && right && FT_HAS_KERNING(f->face))
    FT_Get_Kerning(f->face,left,right,f->bitmap_only ? FT_KERNING_UNSCALED : FT_KERNING_DEFAULT,&v);
  return f->bitmap_only ? (float)v.x*(float)f->metric_size/(64*f->design_units) : (float)v.x/64;
}

static int ws(unsigned char c) { return c == ' ' || (c >= 9 && c <= 13); }
static int same(const char *s, size_t n, const char *word) {
  size_t i;
  if (strlen(word) != n) return 0;
  for (i = 0; i < n; i++)
    if (tolower((unsigned char)s[i]) != tolower((unsigned char)word[i])) return 0;
  return 1;
}
int exr_family_equal(const char *a, const char *b) { return same(a, strlen(a), b); }
int exr_family_next(const char *s, size_t *at, char out[128]) {
  size_t i = *at, start, end;
  int quote = 0;
  while (ws((unsigned char)s[i])) i++;
  if (!s[i]) return 0;
  if (s[i] == '\'' || s[i] == '"') quote = s[i++];
  start = i;
  while (s[i] && (quote ? s[i] != quote : s[i] != ',')) {
    if (s[i] == '\\' && s[i + 1]) i++;
    else if (!quote && (s[i] == '\'' || s[i] == '"' || s[i] == '(' ||
                       s[i] == ')' || s[i] == ';' || s[i] == '{' || s[i] == '}')) return -1;
    i++;
  }
  end = i;
  if (quote) { if (s[i] != quote) return -1; i++; }
  else while (end > start && ws((unsigned char)s[end - 1])) end--;
  while (ws((unsigned char)s[i])) i++;
  if (s[i] && s[i] != ',') return -1;
  if (!exr_css_unescape(s + start, end - start, out, 128)) return -1;
  if (!quote) {
    size_t a, b = 0;
    for (a = 0; out[a]; a++) {
      if (ws((unsigned char)out[a])) {
        if (b && out[b - 1] != ' ') out[b++] = ' ';
      } else out[b++] = out[a];
    }
    if (b && out[b - 1] == ' ') b--;
    out[b] = 0;
    if (!b) return -1;
  }
  if (s[i] == ',') {
    i++;
    while (ws((unsigned char)s[i])) i++;
    if (!s[i]) return -1;
  }
  *at = i;
  return 1;
}
size_t exr_font_order(const exr_font *f, const char *list, unsigned flags,
                       size_t chapter, size_t order[32]) {
  char family[128];
  size_t at = 0, count = 0, i;
  uint32_t seen = 0;
  unsigned score;
  while (list && exr_family_next(list, &at, family) == 1) {
    for (score = 0; score < 4; score++) {
      for (i = f->count; i; i--) {
        size_t index = i - 1 < f->base_count ? f->base_count - i : i - 1;
        const exr_face *face = &f->faces[index];
        if ((seen & (UINT32_C(1) << index)) ||
            (face->scope != SIZE_MAX && face->scope != chapter) ||
            !exr_family_equal(family, face->family) || ((flags ^ face->style_flags) & 3) != score)
          continue;
        seen |= UINT32_C(1) << index;
        order[count++] = index;
      }
    }
  }
  for (i = 0; i < f->base_count; i++)
    if (!(seen & (UINT32_C(1) << i))) order[count++] = i;
  return count;
}
