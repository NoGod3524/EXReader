/* SPDX-License-Identifier: MIT */
#ifndef EXR_HYPHEN_INTERNAL_H
#define EXR_HYPHEN_INTERNAL_H
#include "base_internal.h"
#include "exr/text.h"
exr_status exr_hyphenator_ref(exr_hyphenator *hyphenator,exr_error *error);
unsigned exr_hyphen_word_kind(uint32_t cp); /* L=1, M/join-control=2, N=3, other=0. */
int exr_hyphen_language(const char *language,char out[256]);
unsigned exr_hyphenator_bidi_risk(exr_hyphenator *hyphenator,const char *language);
int exr_hyphenator_replacements(const exr_hyphenator *hyphenator);
#endif
