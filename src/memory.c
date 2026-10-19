/* SPDX-License-Identifier: MIT */
#include "layout_internal.h"

/* Requested allocation payload, excluding allocator overhead and shared or borrowed
   objects. Saturation keeps accounting safe even when a sum cannot fit size_t. */
static size_t add(size_t total, size_t bytes) {
  return bytes > SIZE_MAX - total ? SIZE_MAX : total + bytes;
}
static size_t array(size_t total, const void *data, size_t count, size_t element) {
  if (!data)
    return total;
  if (element && count > SIZE_MAX / element)
    return SIZE_MAX;
  return add(total, count * element);
}

size_t exr_document_memory_size(const exr_document *d) {
  size_t total, i;
  if (!d)
    return 0;
  total = sizeof(*d);
  total = array(total, d->text, d->text_capacity, 1);
  total = array(total, d->blocks, d->capacity, sizeof(*d->blocks));
  total = array(total, d->nodes, d->node_capacity, sizeof(*d->nodes));
  total = array(total, d->last_children, d->last_capacity, sizeof(*d->last_children));
  total = array(total, d->chapters, d->chapter_capacity, sizeof(*d->chapters));
  total = array(total, d->resources, d->resource_capacity, sizeof(*d->resources));
  total = array(total, d->resource_data, d->resource_count, sizeof(*d->resource_data));
  total = add(total, d->model_bytes);
  /* Custom construction copies its title through exr_model_copy. Chapter strings
     either alias resource metadata or were copied through that same model path. */
  if (d->title && d->format != EXR_CUSTOM)
    total = add(add(total, strlen(d->title)), 1);
  if(d->language) total=add(add(total,strlen(d->language)),1);
  for (i = 0; i < d->node_count; i++)
    total = array(total, d->nodes[i].attributes, d->nodes[i].attribute_count,
                  sizeof(*d->nodes[i].attributes));
  if (d->resource_data)
    for (i = 0; i < d->resource_count; i++)
      if (d->resource_data[i].bytes)
        total = add(total, d->resource_data[i].size ? d->resource_data[i].size : 1);
  /* Publication indexes and chapter snapshots share their compressed source.
     Count a private archive only, rather than charging every cache entry. */
  if (!d->shared_archive)
    total = array(total, d->archive, d->archive_size, 1);
  return total;
}

size_t exr_layout_memory_size(const exr_layout *l) {
  size_t total, i;
  if (!l)
    return 0;
  total = sizeof(*l);
  total = array(total, l->glyphs, l->glyph_cap, sizeof(*l->glyphs));
  total = array(total, l->lines, l->line_cap, sizeof(*l->lines));
  total = array(total, l->pages, l->page_cap, sizeof(*l->pages));
  total = array(total, l->boxes, l->box_cap, sizeof(*l->boxes));
  total = array(total, l->paints, l->paint_count, sizeof(*l->paints));
  total = array(total, l->positioned, l->page_count, sizeof(*l->positioned));
  total = array(total, l->images, l->image_cap, sizeof(*l->images));
  total = array(total, l->styles, l->style_count, sizeof(*l->styles));
  for (i = 0; i < l->style_count; i++)
    if (l->styles[i].family_owned) total = add(total, strlen(l->styles[i].family) + 1);
  /* Image bytes and their reference counters are conservatively charged to each
     referencing page, even when another page shares the same immutable pixels. */
  total = array(total, l->images, l->image_count, sizeof(size_t));
  return add(total, l->image_bytes);
}
