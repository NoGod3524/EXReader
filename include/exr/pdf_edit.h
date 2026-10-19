/* SPDX-License-Identifier: MIT */
#ifndef EXR_PDF_EDIT_H
#define EXR_PDF_EDIT_H
#include "pdf.h"
#define EXR_PDF_EDIT_VERSION "0.20.0"
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
#ifdef __cplusplus
}
#endif
#endif
