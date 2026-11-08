/* The 19-book corpus includes one MOBI; R3's indexed-publication path is EPUB-only. */
static int ratio_document_pager(exr_document *document, exr_font *font,
                                exr_pager **pager, exr_error *error) {
  exr_layout_config config = exr_layout_config_defaults();
  config.page.width = e1_dimension("E1_WIDTH", 800);
  config.page.height = e1_dimension("E1_HEIGHT", 1000);
  config.page.margin = e1_dimension("E1_MARGIN", 32);
  config.page.font_size = 24;
  return exr_pager_create(document, font, &config, pager, error) == EXR_OK;
}
