/* SPDX-License-Identifier: GPL-3.0-only */
#ifndef EXR_PDF_INTERNAL_H
#define EXR_PDF_INTERNAL_H
#include "internal.h"
#include "vector_internal.h"
#define EXR_PDF_NONE UINT32_MAX
#define EXR_PDF_MAX_VALUES 1048576u
typedef enum {
  EXR_PDF_NULL,EXR_PDF_BOOL,EXR_PDF_INT,EXR_PDF_REAL,EXR_PDF_NAME,
  EXR_PDF_STRING,EXR_PDF_ARRAY,EXR_PDF_DICT,EXR_PDF_REF,EXR_PDF_STREAM
} exr_pdf_kind;
typedef struct {
  exr_pdf_kind kind;
  /* REAL uses first for an internal retained number spelling; collections use
     it for their first child. Other scalar kinds keep it EXR_PDF_NONE. */
  uint32_t next,first;
  union { double number; int64_t integer; struct { uint32_t offset,length; } bytes; struct { uint32_t object,generation; } ref; } u;
} exr_pdf_value;
typedef struct exr_pdf_file exr_pdf_file;
/* The input is borrowed until close. IDs remain stable; value pointers may move
   when another indirect object is resolved. Public access uses the fixed-document adapter. */
exr_status exr_pdf_open(const void *data,size_t size,exr_pdf_file **out,exr_error *error);
void exr_pdf_close(exr_pdf_file *file);
/* Borrowed only for the duration of one synchronous adapter operation. */
void exr_pdf_control(exr_pdf_file *file,const exr_control *control);
exr_status exr_pdf_metadata_string(exr_pdf_file *file,uint32_t id,char **out,exr_error *error);
/* Patch document-subject XMP without flattening unknown RDF structures. */
exr_status exr_pdf_xmp_write(const void *data,size_t size,const exr_metadata_entry *changes,size_t count,
  const exr_control *control,exr_buffer *out,exr_error *error);
exr_status exr_pdf_page_annotations(exr_pdf_file *file,uint32_t id,const exr_control *control,
  exr_page_annotation **out,size_t *count,exr_error *error);
uint32_t exr_pdf_info(const exr_pdf_file *file);
uint32_t exr_pdf_root(const exr_pdf_file *file);
/* Effective latest trailer values are borrowed and deliberately not resolved.
   Missing Info/ID are EXR_PDF_NONE. size is the latest declared /Size. */
typedef struct { size_t startxref,size; uint32_t root,info,id; } exr_pdf_revision_info;
void exr_pdf_revision(const exr_pdf_file *file,exr_pdf_revision_info *out);
exr_status exr_pdf_object_identity(const exr_pdf_file *file,uint32_t value,
  uint32_t *object,uint32_t *generation,exr_error *error);
/* Appends a complete value without resolving references or copying streams.
   Keys are filtered only in the outermost dictionary. Failure restores size. */
exr_status exr_pdf_serialize(const exr_pdf_file *file,uint32_t value,
  const char *const *skip_keys,size_t skip_count,exr_buffer *out,
  const exr_control *control,exr_error *error);
/* Locale independent, finite PDF real syntax without exponent notation. */
exr_status exr_pdf_real(exr_buffer *out,double value,exr_error *error);
const exr_pdf_value *exr_pdf_value_at(const exr_pdf_file *file,uint32_t value);
const unsigned char *exr_pdf_bytes(const exr_pdf_file *file,uint32_t value,size_t *size);
uint32_t exr_pdf_get(exr_pdf_file *file,uint32_t dict,const char *key);
exr_status exr_pdf_resolve(exr_pdf_file *file,uint32_t value,uint32_t *out,exr_error *error);
exr_status exr_pdf_stream_data(exr_pdf_file *file,uint32_t stream,const unsigned char **data,
                                 size_t *size,exr_error *error);
typedef enum { EXR_PDF_STREAM_RAW,EXR_PDF_STREAM_JPEG } exr_pdf_stream_codec;
/* Decodes lossless prefixes and preserves a final image codec for the image
   decoder. Ordinary stream_data always rejects an encoded image tail. */
exr_status exr_pdf_image_payload(exr_pdf_file *file,uint32_t stream,const unsigned char **data,size_t *size,
                                  exr_pdf_stream_codec *codec,uint32_t *parameters,exr_error *error);
typedef struct {
  uint32_t object,resources,contents,annotations;
  double media[4],crop[4],user_unit;
  unsigned rotation;
} exr_pdf_page_info;
/* Caller frees the page snapshot and content buffer. Object IDs borrow file. */
exr_status exr_pdf_pages(exr_pdf_file *file,exr_pdf_page_info **pages,size_t *count,exr_error *error);
exr_status exr_pdf_content(exr_pdf_file *file,uint32_t contents,exr_buffer *out,exr_error *error);
/* Operand arena and its IDs/bytes are borrowed only for the callback. */
typedef exr_status (*exr_pdf_operator_fn)(void *context,exr_pdf_file *operands,const char *operator_name,
                                         const uint32_t *values,size_t count,exr_error *error);
exr_status exr_pdf_content_ops(const void *data,size_t size,exr_pdf_operator_fn operation,void *context,
                               const exr_control *control,exr_error *error);
/* Inline image dictionaries live in the operand arena; ColorSpace names are
   resolved against the current page/Form resource dictionary. */
exr_status exr_pdf_content_ops_resources(exr_pdf_file *owner,uint32_t resources,const void *data,size_t size,
  exr_pdf_operator_fn operation,void *context,size_t *decode_budget,const exr_control *control,exr_error *error);
exr_status exr_pdf_syntax_ops(const void *data,size_t size,exr_pdf_operator_fn operation,void *context,
                              size_t maximum_operands,const exr_control *control,exr_error *error);
typedef struct exr_pdf_cmap exr_pdf_cmap;
typedef struct { uint32_t code; unsigned code_bytes; char utf8[256]; size_t size; } exr_pdf_mapping;
exr_status exr_pdf_cmap_parse(const void *data,size_t size,const exr_control *control,exr_pdf_cmap **out,exr_error *error);
void exr_pdf_cmap_free(exr_pdf_cmap *map);
exr_status exr_pdf_cmap_next(const exr_pdf_cmap *map,const unsigned char *data,size_t size,size_t *at,
                            exr_pdf_mapping *out,exr_error *error);
typedef struct exr_pdf_font exr_pdf_font;
typedef enum { EXR_PDF_TYPE1,EXR_PDF_TRUETYPE,EXR_PDF_CID_TYPE0,EXR_PDF_CID_TYPE2,EXR_PDF_TYPE3 } exr_pdf_font_kind;
typedef struct {
  exr_pdf_font_kind kind; const char *base_name,*encoding_name,*program_type;
  const unsigned char *program; size_t program_size; unsigned composite,vertical,flags;
  double ascent,descent; /* Logical cell height in 1000-em units; descriptor or estimated. */
  double type3_quad[8]; /* Declared FontBBox after its full normalized FontMatrix. */
} exr_pdf_font_info;
typedef struct {
  exr_pdf_mapping text; uint32_t cid,glyph; unsigned glyph_known;
  double width,vertical_advance,vertical_x,vertical_y;
  const char *glyph_name;
} exr_pdf_character;
/* Font metadata/mapping are owned; decoded program bytes borrow the PDF file. */
exr_status exr_pdf_font_open(exr_pdf_file *file,uint32_t dictionary,const exr_control *control,exr_pdf_font **out,exr_error *error);
void exr_pdf_font_close(exr_pdf_font *font);
const exr_pdf_font_info *exr_pdf_font_description(const exr_pdf_font *font);
exr_status exr_pdf_font_next(const exr_pdf_font *font,const unsigned char *data,size_t size,size_t *at,
                             exr_pdf_character *out,exr_error *error);
size_t exr_pdf_cmap_memory(const exr_pdf_cmap *map);
size_t exr_pdf_font_memory(const exr_pdf_font *font);
/* Type3 metrics stay in normalized 1000-em text units. Matrix maps raw
   CharProc glyph coordinates to those units; an absent glyph is NONE. */
exr_status exr_pdf_font_type3(exr_pdf_file *file,const exr_pdf_font *font,uint32_t code,
  uint32_t *stream,uint32_t *resources,double matrix[6],exr_error *error);
/* Immutable normative facts; glyph names and encoded byte values are distinct
   from ToUnicode's semantic text. Unknown names/metrics return no mapping. */
const char *exr_pdf_encoding_glyph(const char *encoding,unsigned code);
size_t exr_pdf_glyph_unicode(const char *name,int dingbats,char out[256]);
int exr_pdf_standard_font(const char *name);
int exr_pdf_standard_width(const char *font,const char *glyph,double *width);
typedef enum { EXR_PDF_DEVICE_GRAY=1,EXR_PDF_DEVICE_RGB=3,EXR_PDF_DEVICE_CMYK=4 } exr_pdf_color_space;
typedef struct { exr_pdf_color_space space; double values[4],alpha; } exr_pdf_color;
/* Immutable source spaces shared by vector colours and image samples. CIE
   conversion targets fixed sRGB/D65; ICCBased uses its Alternate, not LUTs. */
typedef struct exr_pdf_colorspace exr_pdf_colorspace;
exr_status exr_pdf_colorspace_open(exr_pdf_file *file,uint32_t value,exr_pdf_file *resource_file,
  uint32_t resources,const exr_control *control,exr_pdf_colorspace **out,exr_error *error);
void exr_pdf_colorspace_free(exr_pdf_colorspace *space);
size_t exr_pdf_colorspace_memory(const exr_pdf_colorspace *space);
unsigned exr_pdf_colorspace_components(const exr_pdf_colorspace *space);
exr_pdf_color_space exr_pdf_colorspace_device(const exr_pdf_colorspace *space);
int exr_pdf_colorspace_indexed(const exr_pdf_colorspace *space);
#define EXR_PDF_MAX_COLORANTS 32u
void exr_pdf_colorspace_ranges(const exr_pdf_colorspace *space,double *ranges);
void exr_pdf_colorspace_initial(const exr_pdf_colorspace *space,double *values);
exr_status exr_pdf_colorspace_rgb(const exr_pdf_colorspace *space,const double *values,double rgb[3],exr_error *error);
int exr_pdf_colorspace_no_paint(const exr_pdf_colorspace *space);
size_t exr_pdf_colorspace_cost(const exr_pdf_colorspace *space);
typedef struct {
  exr_pdf_color fill,stroke; exr_vector_stroke_style line;exr_blend_mode blend;
  const double *dashes; size_t dash_count; double dash_phase,matrix[6];
} exr_pdf_paint_state;
typedef struct {
  const exr_pdf_font *font; exr_pdf_character character;
  double transform[6]; /* glyph coordinates in 1000 units to output space */
  size_t sequence; unsigned rendering_mode;
  exr_pdf_paint_state paint; /* Drawing walker only; text-only traversal skips paint state. */
} exr_pdf_text_glyph;
/* Glyph/font/name pointers are borrowed only during each streaming callback. */
typedef exr_status (*exr_pdf_text_fn)(void *context,const exr_pdf_text_glyph *glyph,exr_error *error);
enum { EXR_PDF_FILL=1,EXR_PDF_STROKE=2,EXR_PDF_CLIP=4 };
typedef struct {
  const exr_vector_segment *segments; size_t count; unsigned flags;
  exr_vector_rule rule; exr_pdf_paint_state paint;
} exr_pdf_path_paint;
typedef enum { EXR_PDF_SAVE,EXR_PDF_RESTORE,EXR_PDF_BEGIN_TEXT,EXR_PDF_END_TEXT } exr_pdf_state_event;
typedef exr_status (*exr_pdf_path_fn)(void *context,const exr_pdf_path_paint *path,exr_error *error);
typedef exr_status (*exr_pdf_state_fn)(void *context,exr_pdf_state_event event,exr_error *error);
typedef exr_status (*exr_pdf_image_fn)(void *context,exr_pdf_file *file,uint32_t image,exr_pdf_file *resource_file,uint32_t resources,const exr_pdf_paint_state *paint,exr_error *error);
typedef struct {
  exr_pdf_text_fn glyph;exr_pdf_path_fn path;exr_pdf_state_fn state;exr_pdf_image_fn image;
  exr_draw_group_begin_fn begin_group;exr_draw_layer_end_fn end_layer;
} exr_pdf_draw_callbacks;
enum { EXR_PDF_GROUP_ISOLATED=1,EXR_PDF_GROUP_NONISOLATED=2 };
exr_status exr_pdf_group_rgb(exr_pdf_file *file,uint32_t group,int page,int *present,exr_error *error);
exr_status exr_pdf_text_ops(exr_pdf_file *file,uint32_t resources,const void *data,size_t size,
                            exr_pdf_text_fn glyph,void *context,const exr_control *control,exr_error *error);
/* All event arrays/pointers are borrowed only during their callback. Path points
   already include construction-time CTMs; paint.matrix is the painting-time CTM. */
exr_status exr_pdf_draw_ops(exr_pdf_file *file,uint32_t resources,const void *data,size_t size,
                            const double initial[6],const exr_pdf_draw_callbacks *callbacks,void *context,
                            const exr_control *control,exr_error *error);
#endif
