/* SPDX-License-Identifier: MIT */
#ifndef EXR_STYLE_INTERNAL_H
#define EXR_STYLE_INTERNAL_H
#include "document_internal.h"
#include "exr/layout.h"
#define EXR_DECORATIONS (EXR_GLYPH_UNDERLINE | EXR_GLYPH_STRIKE)
typedef struct {
  float value;
  int percent;
} exr_length; /* value < 0 means auto */
enum { EXR_CSS_NONE, EXR_CSS_INLINE, EXR_CSS_BLOCK, EXR_CSS_TABLE, EXR_CSS_ROW, EXR_CSS_CELL };
enum { EXR_CELL_BASELINE,EXR_CELL_TOP,EXR_CELL_MIDDLE,EXR_CELL_BOTTOM };
enum { EXR_HYPHENS_MANUAL,EXR_HYPHENS_AUTO,EXR_HYPHENS_NONE };
typedef struct {
  char family[128], source[2048], base[2048];
  size_t chapter;
  unsigned flags;
} exr_font_rule;
/* Border sides use CSS physical order: 0 top, 1 right, 2 bottom, 3 left. */
typedef struct {
  float font_size, leading, indent, border_width[4];
  const char *family;
  int family_owned;
  int leading_relative, align, display, before, after, border_style[4], writing_declared;
  int ruby_position, ruby_align;
  int table_fixed;
  int border_collapse;
  float border_spacing[2]; /* CSS physical horizontal, vertical lengths. */
  int vertical_align;
  int float_side,clear_side; /* CSS line-left=1, line-right=2, both=3. */
  int hyphens;
  unsigned flags;
  exr_direction direction;
  exr_writing_mode writing_mode;
  exr_text_orientation orientation;
  uint32_t color, background, border_color[4];
  exr_length width, height, max_width, max_height, margin[4], padding[4];
} exr_style;
/* A visible border occupies its width; CSS "hidden" reserves no space outside
   the collapsing model. */
static inline float exr_border_extent(const exr_style *s, int side) {
  int style = s->border_style[side];
  return style != 0 && style != 2 ? s->border_width[side] : 0;
}
static inline int exr_border_any(const exr_style *s) {
  int side;
  for (side = 0; side < 4; side++)
    if (exr_border_extent(s, side) > 0)
      return 1;
  return 0;
}
/* All four sides share one width, colour and style; the single-border box path
   can then keep the compact representation. */
static inline int exr_border_uniform(const exr_style *s) {
  int side;
  for (side = 1; side < 4; side++) {
    if (s->border_style[side] != s->border_style[0])
      return 0;
    if (s->border_style[side] &&
        (s->border_width[side] != s->border_width[0] ||
         s->border_color[side] != s->border_color[0]))
      return 0;
  }
  return 1;
}
exr_status exr_compute_styles(const exr_document *doc, const exr_layout_config *config,
                              exr_style **styles, exr_font_rule **fonts, size_t *font_count,
                              exr_error *error);
typedef struct { size_t retained_bytes, retained_fonts_bytes, peak_bytes; } exr_style_memory;
exr_status exr_compute_styles_bounded(const exr_document *doc,const exr_layout_config *config,
  size_t budget,exr_style **styles,exr_font_rule **fonts,size_t *font_count,
  exr_style_memory *memory,exr_error *error);
static inline const exr_style *exr_doc_style(const exr_document *doc,const exr_style *styles,size_t node) {
  return doc->view ? doc->view->style(doc->view->context,node) : &styles[node];
}
void exr_styles_free(exr_style *styles, size_t count);
int exr_family_next(const char *value, size_t *offset, char out[128]);
int exr_family_equal(const char *a, const char *b);
int exr_parse_font_rule(const char *body, size_t size, const char *base,
                         size_t chapter, exr_font_rule *rule);
size_t exr_css_delimiter(const char *text, size_t size, char delimiter);

#endif
