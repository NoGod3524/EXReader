/* SPDX-License-Identifier: GPL-3.0-only */
#ifndef EXR_CASE_INTERNAL_H
#define EXR_CASE_INTERNAL_H
#include <stdint.h>
#include <stddef.h>
#define EXR_CASE_CASED 1u
#define EXR_CASE_UPPERCASE 2u
#define EXR_CASE_LOWERCASE 4u
#define EXR_CASE_TITLECASE 8u
#define EXR_CASE_IGNORABLE 16u
#define EXR_CASE_SOFT_DOTTED 32u
enum { EXR_CASE_LOWER, EXR_CASE_TITLE, EXR_CASE_UPPER, EXR_CASE_LITERAL };
unsigned exr_case_properties(uint32_t cp);
/* Unicode full mapping of one scalar in its immutable input context; <=3 output
   scalars, possibly zero for a conditional combining-dot deletion. */
unsigned exr_case_map(const uint32_t *text,size_t count,size_t at,unsigned mode,
                       const char *language,uint32_t output[3]);
/* Uniform lower/upper, initial title, or literal for mixed/uncased words. */
unsigned exr_case_word(const uint32_t *text,size_t count,size_t *first_cased);
#endif
