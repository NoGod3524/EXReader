/* SPDX-License-Identifier: MIT */
#ifndef EXR_PDF_EDIT_H
#define EXR_PDF_EDIT_H
#include "pdf.h"
#include "text.h"
#define EXR_PDF_EDIT_VERSION "3.33.0"
#ifdef __cplusplus
extern "C" {
#endif
typedef struct {
  size_t struct_size;
  uint32_t color; /* 0xRRGGBB */
  double opacity; /* [0,1], including fully transparent. */
  exr_control control;
} exr_pdf_annotation_write_options;
EXR_API exr_pdf_annotation_write_options exr_pdf_annotation_write_defaults(void);
/* Zero-based page. Upserts Text, Highlight, Underline, StrikeOut or Squiggly
   annotations by nonempty UTF-8 NM
   on that page; duplicate matching IDs are an error. Text has no quads;
   Text markup requires 1-32768 convex four-point quads within its positive-area
   bounds; coordinate magnitudes and local dimensions cannot exceed 1e7.
   Line markup treats the first two points as the top edge; the remaining two
   are the corresponding lower edge (Z or perimeter order, no diagonal edge).
   Five text properties match load_annotations: description, creator, subject,
   CreateDate and ModifyDate (use their full metadata URIs). Other keys fail.
   NULL options use yellow/0.35 for both create and update. An update replaces
   the supported fields and appearance, preserving other dictionary entries.
   Appends a revision, preserving every original byte. Input is borrowed only
   during this call; free the independent complete PDF with exr_free().
   Writing requires PDF 1.4 or newer. Encrypted PDFs and catalog permission
   constraints are unsupported. UTF-8 and encoded UTF-16 text each cap at 64 KiB. */
EXR_API exr_status exr_pdf_annotation_write(const void *data,size_t size,size_t page,
  const exr_page_annotation *annotation,const exr_pdf_annotation_write_options *options,
  void **out,size_t *out_size,exr_error *error);
/* Removes the matching annotation and its same-page Popup. A missing ID returns
   an independent byte-for-byte copy. Failures clear both outputs. */
EXR_API exr_status exr_pdf_annotation_remove(const void *data,size_t size,size_t page,const char *id,
  const exr_control *control,void **out,size_t *out_size,exr_error *error);
/* Patches the eight supported PDF Info metadata URIs and, when present, XMP.
   Missing keys stay unchanged; NULL values delete that whole property and empty
   strings remain values except typed dates, which require a valid date or NULL.
   Dates accept PDF D: or ISO8601 second precision and retain explicit timezones.
   Updated localized/list XMP properties are replaced as
   a whole; unrelated RDF structures survive. Uses incremental revisions and
   the same owned-output/cancellation/permission rules as annotation editing. */
EXR_API exr_status exr_pdf_metadata_write(const void *data,size_t size,const exr_metadata_entry *changes,size_t count,
  const exr_control *control,void **out,size_t *out_size,exr_error *error);
typedef enum {
  EXR_PDF_FIELD_UNKNOWN,EXR_PDF_FIELD_TEXT,EXR_PDF_FIELD_CHECKBOX,
  EXR_PDF_FIELD_RADIO,EXR_PDF_FIELD_CHOICE,EXR_PDF_FIELD_PUSHBUTTON,EXR_PDF_FIELD_SIGNATURE
} exr_pdf_field_kind;
enum { EXR_PDF_FORM_ACTIONS=1,EXR_PDF_FORM_XFA=2,EXR_PDF_FORM_UNSUPPORTED=4,
       EXR_PDF_FORM_DIRECT=8 };
typedef struct { const char *value,*label; } exr_pdf_field_option;
typedef struct {
  size_t page; /* Zero based; SIZE_MAX when absent from the page annotation lists. */
  double bounds[4];
  const char *on_state; /* Button export name, excluding Off; NULL for text/choice. */
} exr_pdf_field_widget;
typedef struct {
  size_t struct_size;
  const char *name; /* Fully qualified UTF-8 field name. */
  exr_pdf_field_kind kind;
  uint32_t flags; /* Effective PDF Ff bits, including ReadOnly=1 and Required=2. */
  unsigned issues; /* EXR_PDF_FORM_*; actions/XFA are never executed. */
  size_t max_length; /* Unicode scalar limit; zero means absent. */
  const char *const *values; size_t value_count;
  const char *const *default_values; size_t default_value_count;
  const exr_pdf_field_option *options; size_t option_count;
  const exr_pdf_field_widget *widgets; size_t widget_count;
} exr_pdf_form_field;
typedef struct {
  size_t struct_size;
  size_t max_fields,max_widgets,max_depth,max_text_bytes; /* Zero selects defaults. */
  exr_control control;
} exr_pdf_form_options;
EXR_API exr_pdf_form_options exr_pdf_form_defaults(void);
/* Independent owned snapshot; free with form_free. Empty forms return NULL/0.
   Defaults/caps: 4096 fields, 16384 widgets, 64 tree levels, 8 MiB text.
   Effective FT/Ff/V/DV/DA/Q/MaxLen/Opt inherit through the validated field tree.
   Cycles, shared children, duplicate qualified names and inconsistent Parent
   links fail atomically. XFA is recorded on fields and blocks writing. */
EXR_API exr_status exr_pdf_form_read(const void *data,size_t size,const exr_pdf_form_options *options,
  exr_pdf_form_field **out,size_t *count,exr_error *error);
EXR_API void exr_pdf_form_free(exr_pdf_form_field *fields,size_t count);
typedef struct { const char *name; const char *const *values; size_t value_count; } exr_pdf_form_change;
typedef struct {
  size_t struct_size;
  exr_font *font; /* Borrowed Unicode appearance font; serialized with its other uses. */
  size_t font_index;
  exr_control control;
} exr_pdf_form_write_options;
EXR_API exr_pdf_form_write_options exr_pdf_form_write_defaults(void);
/* Atomic incremental edit, preserving original bytes. Tx, checkbox/radio and
   Ch values and every associated widget appearance update together. ReadOnly,
   Required, MaxLen, option membership and single/multiple selection are checked.
   Unicode text requires font; missing glyphs fail rather than emitting tofu.
   Without font, printable ASCII uses Helvetica. Password/multiline/file-select/
   rich-text/comb text and editable combo boxes currently return UNSUPPORTED.
   Sig/pushbutton/unknown types, XFA, field/widget actions, rotation and signed
   permission constraints cannot be changed. Failures/cancellation clear outputs.
   Values are UTF-8; button values use the widget export name or Off. Empty lists
   clear a field. No formatting, calculation, validation actions or JS execute. */
EXR_API exr_status exr_pdf_form_write(const void *data,size_t size,const exr_pdf_form_change *changes,size_t count,
  const exr_pdf_form_write_options *options,void **out,size_t *out_size,exr_error *error);
#ifdef __cplusplus
}
#endif
#endif
