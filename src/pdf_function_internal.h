/* SPDX-License-Identifier: GPL-3.0-only */
#ifndef EXR_PDF_FUNCTION_INTERNAL_H
#define EXR_PDF_FUNCTION_INTERNAL_H
#include "pdf_internal.h"
typedef struct exr_pdf_function exr_pdf_function;
exr_status exr_pdf_function_open(exr_pdf_file *file,uint32_t value,unsigned outputs,const exr_control *control,exr_pdf_function **out,exr_error *error);
void exr_pdf_function_free(exr_pdf_function *function);
exr_status exr_pdf_function_eval(const exr_pdf_function *function,double input,double output[4],exr_error *error);
size_t exr_pdf_function_memory(const exr_pdf_function *function);
size_t exr_pdf_function_cost(const exr_pdf_function *function);
#endif
