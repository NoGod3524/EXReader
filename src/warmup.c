/* SPDX-License-Identifier: MIT */
#include "exr/render.h"
#include "base_internal.h"

exr_status exr_publication_warmup(exr_publication *publication, exr_font *font,
  const exr_layout_config *config, size_t pages, exr_error *error) {
  size_t count = 0, part;
  const exr_part *parts;
  exr_status status = EXR_OK;
  if (!publication || !font)
    return exr_fail(error, EXR_ARGUMENT, "Missing warmup publication or font");
  parts = exr_publication_parts(publication, &count);
  for (part = 0; part < count && pages; part++) {
    exr_document *document = NULL;
    exr_pager *pager = NULL;
    exr_layout *page = NULL;
    if (!parts[part].in_reading_order) continue;
    status = exr_control_cancel(config ? &config->control : NULL, error);
    if (status == EXR_OK) status = exr_publication_load(publication, part, &document, error);
    if (status == EXR_OK) status = exr_pager_create(document, font, config, &pager, error);
    while (status == EXR_OK && pages) {
      exr_bitmap bitmap = {0};
      status = exr_pager_next(pager, &page, error);
      if (status != EXR_OK || !page) break;
      status = exr_render_page_ex(page, exr_layout_font(page), 0, 4,
        config ? &config->control : NULL, &bitmap, error);
      exr_bitmap_free(&bitmap);
      exr_layout_free(page); page = NULL;
      if (status == EXR_OK) pages--;
    }
    exr_layout_free(page);
    exr_pager_free(pager);
    exr_document_free(document);
    if (status != EXR_OK) return status;
  }
  return exr_fail(error, EXR_OK, "");
}
