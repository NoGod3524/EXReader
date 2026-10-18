/* SPDX-License-Identifier: GPL-3.0-only */
#ifndef EXR_HYPHEN_INTERNAL_H
#define EXR_HYPHEN_INTERNAL_H
#include "internal.h"
exr_status exr_hyphenator_ref(exr_hyphenator *hyphenator,exr_error *error);
unsigned exr_hyphen_word_kind(uint32_t cp); /* L=1, M/join-control=2, N=3, other=0. */
int exr_hyphen_language(const char *language,char out[256]);
#endif
