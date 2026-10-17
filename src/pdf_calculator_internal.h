/* SPDX-License-Identifier: GPL-3.0-only */
#ifndef EXR_PDF_CALCULATOR_INTERNAL_H
#define EXR_PDF_CALCULATOR_INTERNAL_H
#include "internal.h"
typedef struct exr_pdf_calculator exr_pdf_calculator;
/* Control context is borrowed for the enclosing synchronous render call. */
exr_status exr_pdf_calculator_open(const unsigned char *source,size_t size,const exr_control *control,
                                   exr_pdf_calculator **out,exr_error *error);
void exr_pdf_calculator_free(exr_pdf_calculator *program);
size_t exr_pdf_calculator_memory(const exr_pdf_calculator *program);
size_t exr_pdf_calculator_cost(const exr_pdf_calculator *program);
exr_status exr_pdf_calculator_eval(const exr_pdf_calculator *program,double input,unsigned outputs,double out[4],exr_error *error);
#endif
