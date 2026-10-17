/* SPDX-License-Identifier: GPL-3.0-only */
#ifndef EXR_RUBY_INTERNAL_H
#define EXR_RUBY_INTERNAL_H
#include "flow_internal.h"
int exr_ruby_node(const exr_document *doc, size_t node);
exr_status exr_ruby_item(flow *f, size_t node, size_t part, exr_glyph *item, int *done);
exr_status exr_ruby_layout(flow *f, const exr_glyph *item, exr_layout **out);
#endif
