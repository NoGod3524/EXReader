/* SPDX-License-Identifier: MIT */
#ifndef EXR_TEXT_H
#define EXR_TEXT_H
#include "graphics.h"
#ifdef __cplusplus
extern "C" {
#endif
typedef enum {
  EXR_DIRECTION_AUTO = 0, EXR_DIRECTION_LTR = 1, EXR_DIRECTION_RTL = 2
} exr_direction;
typedef struct exr_bidi exr_bidi;
typedef struct {
  size_t start, end;
  uint32_t codepoint;
  unsigned level; /* UINT_MAX for X9-removed controls. */
} exr_bidi_scalar;
#define EXR_TAG(a, b, c, d) (((uint32_t)(a) << 24) | ((uint32_t)(b) << 16) | \
                           ((uint32_t)(c) << 8) | (uint32_t)(d))
typedef struct { uint32_t tag, value; } exr_shape_feature;
typedef struct {
  float font_size;
  unsigned style_flags;
  exr_direction direction;
  uint32_t script, language; /* OpenType tags; zero selects automatic script/default language. */
  const exr_shape_feature *features;
  size_t feature_count;
  uint32_t context_before, context_after; /* Nearest nontransparent adjacent scalar, 0 at boundary. */
  exr_control control;
} exr_shape_options;
typedef struct {
  size_t start, end; /* UTF-8 cluster range; shared by ligatures and attached marks. */
  uint32_t glyph;
  float advance_x, advance_y, offset_x, offset_y; /* Pixels; x right, y up. */
  unsigned flags;
} exr_shaped_glyph;
enum {
  EXR_BOUNDARY_GRAPHEME = 1,
  EXR_BOUNDARY_LINE = 2,
  EXR_BOUNDARY_MANDATORY = 4,
  EXR_BOUNDARY_GLUE = 8 /* No emergency wrapping at this boundary. */
};
enum {
  EXR_GLYPH_BOLD = 1, EXR_GLYPH_ITALIC = 2, EXR_GLYPH_HIDDEN = 4,
  EXR_GLYPH_MISSING = 8, /* No supplied face covers this visible scalar; glyph 0 is used. */
  EXR_GLYPH_SHAPED = 16, /* Advances/offsets include OpenType positioning. */
  EXR_GLYPH_UNDERLINE = 32, EXR_GLYPH_STRIKE = 64,
  EXR_GLYPH_VERTICAL = 128, /* advance and clipping follow the physical y axis. */
  EXR_GLYPH_SIDEWAYS = 256, /* Clockwise 90-degree outline in vertical text. */
  EXR_GLYPH_GENERATED = 2048 /* Contains generated text, e.g. an automatic hyphen.
                               Source range may be empty or cover replaced original text.
                               Copy/selection use original source, not generated spelling. */
};
typedef enum {
  EXR_WRITING_HORIZONTAL_TB=0, EXR_WRITING_VERTICAL_RL=1, EXR_WRITING_VERTICAL_LR=2
} exr_writing_mode;
typedef enum {
  EXR_ORIENTATION_MIXED=0, EXR_ORIENTATION_UPRIGHT=1, EXR_ORIENTATION_SIDEWAYS=2
} exr_text_orientation;

typedef struct {
  const void *data; /* Encoded font bytes, copied during create(). */
  size_t size;
  unsigned face_index; /* Face within a font collection, otherwise zero. */
} exr_font_input;
typedef struct {
  size_t start, end;
  uint32_t codepoint, glyph;
  float x, baseline, advance, size;
  size_t page;
  size_t node;
  uint32_t color; /* 0xRRGGBBAA */
  unsigned flags; /* EXR_GLYPH_*; HIDDEN glyphs must not be drawn. */
  float clip_left, clip_right;
  float line_height;
  size_t cluster_start, cluster_end; /* Source UTF-8 range of this grapheme group. */
  unsigned boundaries; /* Source EXR_BOUNDARY_*; zero after the first shaped glyph in a cluster. */
  size_t font_index; /* Index in the ordered exr_font input list; glyph is face-local. */
  float offset_x, offset_y; /* Shaped glyph offset; y up relative to baseline. */
  unsigned bidi_level; /* Resolved Unicode embedding level; odd means RTL. */
} exr_glyph;
/* Unicode 17 UAX #29 graphemes and default UAX #14 line-break rules.
   Line opportunities are intersected with grapheme boundaries.
   Allocates size+1 bytes indexed by UTF-8 byte offset, freed with exr_free().
   Non-boundary/continuation bytes are zero; end is GRAPHEME|LINE|MANDATORY.
   Text must be valid UTF-8, at most 64 MiB. Embedded U+0000 is a control scalar. */
EXR_API exr_status exr_text_analyze(const char *text, size_t size, unsigned char **boundaries,
                                    exr_error *error);
/* Unicode 17 UAX #9 paragraph analysis, at most 4M scalars. Scalar views are borrowed.
   Reorder accepts scalar-index line slices and returns visual indices into this view,
   excluding X9 controls. Free the returned order with exr_free(). */
EXR_API exr_status exr_bidi_analyze(const char *text, size_t size, exr_direction direction,
                                    exr_bidi **out, exr_error *error);
EXR_API const exr_bidi_scalar *exr_bidi_scalars(const exr_bidi *bidi, size_t *count);
EXR_API exr_status exr_bidi_reorder(const exr_bidi *bidi, size_t first, size_t count,
                                    size_t **out_order, size_t *out_count, exr_error *error);
EXR_API void exr_bidi_free(exr_bidi *bidi);
/* Unicode Bidi_Mirroring_Glyph for one scalar; returns the scalar unchanged when
   no mirrored glyph is defined. */
EXR_API uint32_t exr_bidi_mirror(uint32_t codepoint);
/* UAX #9 paragraph embedding base level of one scalar; UINT_MAX when bidi is
   NULL or scalar_index is past the analysed scalars. */
EXR_API unsigned exr_bidi_base_level(const exr_bidi *bidi, size_t scalar_index);
/* Borrowed encoded font bytes for a host renderer; valid while font is alive. */
EXR_API exr_status exr_font_source(const exr_font *font, size_t index, exr_font_input *source,
                                   exr_error *error);
EXR_API exr_status exr_font_open(const char *path, exr_font **out, exr_error *error);
/* Immutable ordered fallback list, 1..32 scalable or CBDT/CBLC Unicode faces, at most 128 MiB
   of copied font bytes in total. Failure leaves *out NULL. No system font lookup. */
EXR_API exr_status exr_font_create(const exr_font_input *inputs, size_t count,
                                   exr_font **out, exr_error *error);
/* Also accepts supported faces without Unicode charmaps, for direct glyph IDs.
   Such faces do not participate in Unicode character lookup. Inputs are copied. */
EXR_API exr_status exr_font_create_glyphs(const exr_font_input *inputs, size_t count,
                                          exr_font **out, exr_error *error);
enum { EXR_FONT_AXIS_HIDDEN=1 };
typedef struct { uint32_t tag,flags; double minimum,initial,maximum,value; } exr_font_axis;
typedef struct { size_t font_index; uint32_t tag; double value; } exr_font_coordinate;
/* Owned independent axis snapshot; static fonts return NULL/0. Free with exr_free.
   The initial value is the font default, value is this immutable instance's value. */
EXR_API exr_status exr_font_axes(const exr_font *font,size_t font_index,
  exr_font_axis **out,size_t *count,exr_error *error);
/* Creates a new immutable Unicode font set with sparse design coordinates.
   Unspecified axes retain the selected face/named-instance coordinates. At most
   64 axes per face and 2048 assignments; unknown, duplicate/out-of-range axes fail.
   Coordinates are rounded to the font format's 16.16 design-unit precision. */
EXR_API exr_status exr_font_create_variable(const exr_font_input *inputs,size_t count,
  const exr_font_coordinate *coordinates,size_t coordinate_count,exr_font **out,exr_error *error);
EXR_API size_t exr_font_count(const exr_font *font);
/* CPAL counts; fonts without CPAL return 0/0. Same font serialization rule as
   shape. Palette/layer queries do not change the instance's default rendering. */
EXR_API exr_status exr_font_color_palettes(const exr_font *font,size_t font_index,
  size_t *palettes,size_t *entries,exr_error *error);
typedef struct { uint32_t glyph,color; } exr_font_color_layer;
/* Owned COLR v0 layers in back-to-front order, at most 256, freed with exr_free.
   Colors are straight RRGGBBAA, with foreground alpha applied; CPAL
   entry 0xffff uses foreground itself. No layers returns NULL/0. Glyph IDs remain
   specific to this face; color/outline data can be drawn independently. */
EXR_API exr_status exr_font_color_layers(exr_font *font,size_t font_index,uint32_t glyph,
  size_t palette,uint32_t foreground,exr_font_color_layer **out,size_t *count,
  const exr_control *control,exr_error *error);
/* Intrinsic color source of one glyph. COLR v1 is reported before COLR v0 and
   before an SVG description; bitmap strikes stay with exr_font_glyph_image. */
enum { EXR_FONT_COLOR_NONE=0,EXR_FONT_COLOR_COLR_V0=1,EXR_FONT_COLOR_COLR_V1=2,
       EXR_FONT_COLOR_SVG=3 };
typedef struct {
  size_t struct_size; /* Initialize to sizeof(exr_font_color_info). */
  unsigned kind;      /* One of EXR_FONT_COLOR_*; zero when the glyph has none. */
  unsigned variable;  /* COLR v1 carries a variation store resolved by FreeType. */
  unsigned has_clip_box;
  float clip_box[4];  /* x0,y0,x1,y1 in 1000-em units, y up; only for COLR v1. */
} exr_font_color_info;
/* Does not render or allocate a surface. Palette selection may update per-face
   caches, so the same serialization rule as other font queries applies. */
EXR_API exr_status exr_font_color_info_get(exr_font *font,size_t font_index,uint32_t glyph,
  exr_font_color_info *out,const exr_control *control,exr_error *error);
enum { EXR_GLYPH_IMAGE_OUTLINE_OVERLAY=1 };
typedef struct {
  exr_bitmap bitmap;
  float left,top,scale; /* Relative to glyph origin, x right/y down; bitmap pixels times scale. */
  uint32_t flags;
} exr_glyph_image;
/* Owned sbix/CBDT intrinsic-color image at the best available strike for requested pixels.
   No image returns a zero record. Free bitmap with exr_bitmap_free. The image
   does not include text opacity or synthetic styles; glyph advances stay separate. */
EXR_API exr_status exr_font_glyph_image(exr_font *font,size_t font_index,uint32_t glyph,float pixels,
  exr_glyph_image *out,const exr_control *control,exr_error *error);
/* Scalar cmap coverage, not a shaping/sequence support test; invalid input returns 0. */
EXR_API int exr_font_has_glyph(const exr_font *font, size_t font_index, uint32_t codepoint);
EXR_API void exr_font_free(exr_font *font);
/* Owned unhinted Bézier path in 1000-em units, origin on the baseline, y up.
   Bitmap-only glyphs return NULL/0.
   Direct glyph IDs also work without a Unicode cmap. Free segments with
   exr_free(); the path outlives its font. Same font concurrency rule as shape. */
EXR_API exr_status exr_font_glyph_outline(exr_font *font,size_t font_index,uint32_t glyph,
                                           exr_path_segment **out,size_t *count,
                                           const exr_control *control,exr_error *error);
EXR_API exr_shape_options exr_shape_defaults(void);
/* One font face, logical output order; caller splits directional/script/font runs.
   Own the returned glyph array with exr_free(). Failure clears output/count.
   The font must not be used concurrently with layout, shape or rendering calls. */
EXR_API exr_status exr_shape(exr_font *font, size_t font_index, const char *utf8, size_t size,
                             const exr_shape_options *options, exr_shaped_glyph **out,
                             size_t *out_count, exr_error *error);
/* Same ownership and concurrency as shape(); uses vert/vrt2 and vertical metrics.
   advance_y is negative for progression down the page in y-up font coordinates. */
EXR_API exr_status exr_shape_vertical(exr_font *font, size_t font_index, const char *utf8, size_t size,
                                      const exr_shape_options *options, exr_shaped_glyph **out,
                                      size_t *out_count, exr_error *error);
/* Maps the 1000-em, y-up outline to the glyph's physical page coordinates.
   Affine order is [a,b,c,d,e,f]: (a*x+c*y+e,b*x+d*y+f). */
EXR_API exr_status exr_glyph_matrix(const exr_glyph *glyph, double matrix[6], exr_error *error);
/* Optional, immutable language dictionaries. No dictionary is built in or
   downloaded. Each dictionary's data/license is supplied by the host. */
typedef struct exr_hyphenator exr_hyphenator;
typedef exr_status (*exr_hyphenate_fn)(void *context,const char *language,
  const char *word,size_t size,unsigned char *breaks,const exr_control *control,exr_error *error);
typedef struct {
  size_t struct_size;
  exr_hyphenate_fn hyphenate;
  exr_context_release_fn release;
  void *context;
} exr_hyphen_provider;
/* One independent discretionary break in the original UTF-8 word. On taking
   the break, replace [start,end) with before + a display hyphen + after, with
   after at the start of the next line. Ordinary breaks have start=end=point
   and empty before/after. Text is literal UTF-8, without automatic case changes. */
typedef struct {
  size_t point,start,end;
  const char *before,*after;
  size_t before_size,after_size;
} exr_hyphen_break;
typedef struct exr_hyphenation exr_hyphenation;
typedef exr_status (*exr_hyphen_emit_fn)(void *context,const exr_hyphen_break *item,exr_error *error);
typedef exr_status (*exr_hyphenate_discretionary_fn)(void *context,const char *language,
  const char *word,size_t size,exr_hyphen_emit_fn emit,void *emit_context,
  const exr_control *control,exr_error *error);
typedef struct {
  size_t struct_size;
  exr_hyphenate_discretionary_fn hyphenate;
  exr_context_release_fn release;
  void *context;
} exr_hyphen_discretionary_provider;
/* UTF-8 TeX-style pattern tokens, optional UTF-8 header and HYPHENMIN directives.
   Digits 0..9 give weights, '.' anchors word edges, %/# introduce comments.
   NEXTLEVEL separates recursive compound rules from ordinary rules. Supports
   COMPOUND*HYPHENMIN and NOHYPHEN; without NEXTLEVEL, UTF-8 separators are implicit.
   Supports pattern/before=after[,start,cut] discretionary replacements; start
   is 1-based Unicode scalar index excluding a leading anchor. Raw TeX commands
   are rejected. left/right=0 uses file/default=2. */
typedef struct {
  size_t struct_size;
  const char *language; /* ASCII BCP47-style key; NULL/empty is the untagged key. */
  const void *patterns;
  size_t size;
  unsigned left_min,right_min; /* Minimum graphemes retained at each edge, <=64. */
} exr_hyphen_pattern_input;
EXR_API exr_status exr_hyphenator_create(const exr_hyphen_provider *provider,
  exr_hyphenator **out,exr_error *error);
/* emit copies all item/text bytes before returning. Emit only during the
   callback, <=255 distinct points, <=128 scalars/512 bytes of text per item.
   Emit errors are latched even if the provider ignores them. Ownership of
   context transfers on successful create only; serialize use/lifetime. */
EXR_API exr_status exr_hyphenator_create_discretionary(const exr_hyphen_discretionary_provider *provider,
  exr_hyphenator **out,exr_error *error);
/* 1..64 languages, <=8 MiB each / 32 MiB input total. Payload byte budget is
   0=32 MiB default, <=128 MiB. Input buffers are borrowed only during create. */
typedef enum {
  EXR_HYPHEN_CASE_LITERAL = 0, /* Existing behavior; replacement strings are literal. */
  EXR_HYPHEN_CASE_WORD = 1 /* Preserve uniform lower/upper or initial title case; mixed/uncased stays literal. */
} exr_hyphen_case_policy;
/* Native dictionaries only. Unicode 17 full mappings use original/query language
   and logical changed-word context, including tr/az/lt conditional rules. Title
   preservation may extend a replacement through the next retained grapheme.
   Original byte point stays fixed; existing payload/work limits still apply.
   Legacy create_patterns is equivalent to CASE_LITERAL. Providers stay literal. */
EXR_API exr_status exr_hyphenator_create_patterns_ex(const exr_hyphen_pattern_input *inputs,
  size_t count,size_t byte_budget,exr_hyphen_case_policy case_policy,const exr_control *control,
  exr_hyphenator **out,exr_error *error);
EXR_API exr_status exr_hyphenator_create_patterns(const exr_hyphen_pattern_input *inputs,
  size_t count,size_t byte_budget,const exr_control *control,exr_hyphenator **out,exr_error *error);
/* breaks has size+1 bytes: 1 permits a break before that UTF-8 byte; all other
   bytes are 0, including 0/size and grapheme interiors. Size <=1024 bytes / 256
   scalars. Errors on valid-sized requests clear breaks. Provider output is
   checked; language tags are case-insensitive with parent-tag lookup. Native
   patterns use full Unicode 17 case folding (Turkic overrides for tr/az).
   Native matching uses Unicode 17 NFC -> full fold -> NFC; output offsets and
   minimum graphemes refer to original text. Providers receive original bytes.
   Serialize use/lifetime per object. This bitmap omits all spelling-changing
   opportunities; use query for complete discretionary data. */
EXR_API exr_status exr_hyphenator_breaks(exr_hyphenator *hyphenator,const char *language,
  const char *word,size_t size,unsigned char *breaks,const exr_control *control,exr_error *error);
/* Owned immutable result, independent of word/provider/dictionary lifetime.
   Items are sorted by original byte point. Rewrite edges must be original
   grapheme boundaries; normalized/folded interiors cannot erase source spans.
   Query payload <=256 KiB. On failure *out=NULL; no partial result is returned. */
EXR_API exr_status exr_hyphenator_query(exr_hyphenator *hyphenator,const char *language,
  const char *word,size_t size,const exr_control *control,exr_hyphenation **out,exr_error *error);
EXR_API const exr_hyphen_break *exr_hyphenation_breaks(const exr_hyphenation *result,size_t *count);
EXR_API size_t exr_hyphenation_memory_size(const exr_hyphenation *result);
EXR_API void exr_hyphenation_free(exr_hyphenation *result);
EXR_API size_t exr_hyphenator_memory_size(const exr_hyphenator *hyphenator);
EXR_API void exr_hyphenator_free(exr_hyphenator *hyphenator);
#ifdef __cplusplus
}
#endif
#endif
