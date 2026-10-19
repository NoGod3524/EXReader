/* SPDX-License-Identifier: MIT */
#ifndef EXR_CSS_INTERNAL_H
#define EXR_CSS_INTERNAL_H
#include <stddef.h>
size_t exr_css_delimiter(const char *text,size_t size,char delimiter);
int exr_css_unescape(const char *text,size_t size,char *out,size_t capacity);
#endif
