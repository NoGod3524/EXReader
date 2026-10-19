/* SPDX-License-Identifier: MIT */
#ifndef EXR_PDF_FACE_INTERNAL_H
#define EXR_PDF_FACE_INTERNAL_H
#include "pdf_internal.h"
#include "font_outline_internal.h"
typedef struct exr_pdf_face exr_pdf_face;
/* Embedded program wins. A host-supplied fallback is used only for an
   unembedded simple font. Library and selected bytes must outlive
   this owned FT face; no system font lookup or ToUnicode glyph guessing. */
exr_status exr_pdf_face_open(FT_Library library,const exr_pdf_font *font,const exr_font_input *fallback,
                              exr_pdf_face **out,const exr_control *control,exr_error *error);
int exr_pdf_face_matches(const exr_pdf_face *face,const exr_pdf_font *font,const exr_font_input *fallback);
exr_status exr_pdf_face_open_shared(FT_Library library,const exr_pdf_font *font,const exr_font_input *fallback,
                                     const exr_pdf_face *shared,exr_pdf_face **out,const exr_control *control,exr_error *error);
void exr_pdf_face_close(exr_pdf_face *face);
size_t exr_pdf_face_memory(const exr_pdf_face *face);
exr_status exr_pdf_face_glyph(exr_pdf_face *face,const exr_pdf_character *character,uint32_t *glyph,exr_error *error);
exr_status exr_pdf_face_outline(exr_pdf_face *face,const exr_pdf_character *character,
                                 exr_vector_segment **out,size_t *count,size_t *work,
                                 const exr_control *control,exr_error *error);
#endif
