/* SPDX-License-Identifier: MIT */
/* --drive telemetry of accepted frames. Coordinates come from the SDK, before raster rounding. */
static int shell_measure(const char *name) {
  wchar_t filename[256], path[HOST_PATH]; FILE *out;
  RECT client, outer; POINT origin = {0,0};
  wchar_t *wide = host_wide(name, strlen(name));
  swprintf(filename, 256, L"%ls.json", wide ? wide : L"layout"); free(wide);
  path_join(path, HOST_PATH, g.evidence_dir, filename);
  out = _wfopen(path, L"wb"); if (!out) return 0;
  GetClientRect(g.window, &client); GetWindowRect(g.window, &outer); ClientToScreen(g.window, &origin);
  compute_view();
  {
    float targets[4];
    typedef UINT (WINAPI *dpi_fn)(HWND);
    dpi_fn dpi = (dpi_fn)GetProcAddress(GetModuleHandleW(L"user32.dll"), "GetDpiForWindow");
    shell_d2d_target_dpi(host_shell, targets);
    fprintf(out, "{\"actual_window_dpi\":%u,\"display\":[%d,%d],\"target_dpi\":[%.1f,%.1f,%.1f,%.1f],",
      dpi ? dpi(g.window) : 0, g.frame.display_width, g.frame.display_height,
      (double)targets[0],(double)targets[1],(double)targets[2],(double)targets[3]);
  }
  fprintf(out, "\"client\":[%ld,%ld],\"client_box\":[%ld,%ld,%ld,%ld],\"dpi\":%u,\"pmv2\":%d,\"dpi_request\":%d,\"dpi_error\":%lu,",
    client.right,client.bottom,origin.x-outer.left,origin.y-outer.top,client.right,client.bottom,
    shell_dpi,shell_pmv2,(int)shell_dpi_requested,(unsigned long)shell_dpi_error);
  fprintf(out, "\"page\":[%u,%u],\"font\":%.6f,\"margin\":%.6f,\"line_height\":%.6f,\"paragraph\":%.6f,\"scale\":%.6f,\"origin\":[%d,%d],",
    g.frame.bitmap.width,g.frame.bitmap.height,(double)g.session.config.page.font_size,(double)g.session.config.page.margin,
    (double)g.session.config.page.line_height,(double)g.session.config.page.paragraph_spacing,g.view.scale,
    g.view.dx,g.view.dy+shell_px(SHELL_TOPBAR_H,shell_dpi));
  fprintf(out, "\"epoch\":%lu,\"frame_epoch\":%lu,\"builds\":%lu,\"mode\":%d,\"part\":%zu,\"index\":%zu,\"range\":[%zu,%zu],\"lines\":[",
    shell_epoch,g.frame.shell_epoch,shell_pager_builds,g.frame.writing_mode,g.frame.part,g.frame.page,g.frame.range_start,g.frame.range_end);
  for (size_t i=0;i<g.frame.shell_line_count;i++) {
    const exr_line *l=&g.frame.shell_lines[i];
    fprintf(out,"%s[%zu,%zu,%zu,%zu,%.6f,%.6f,%.6f,%.6f]",i?",":"",l->start,l->end,l->glyph_start,l->glyph_count,
      (double)l->x,(double)l->y,(double)l->width,(double)l->height);
  }
  fprintf(out,"],\"glyphs\":[");
  for (size_t i=0;i<g.frame.glyph_count;i++) {
    const exr_glyph *q=&g.frame.glyphs[i];
    fprintf(out,"%s[%zu,%zu,%u,%.6f,%.6f,%.6f,%.6f,%u,%zu,%zu,%zu]",i?",":"",q->start,q->end,q->codepoint,
      (double)q->x,(double)q->baseline,(double)q->advance,(double)q->size,q->flags,q->cluster_start,q->cluster_end,q->node);
  }
  fprintf(out,"],\"text\":\"");
  for (size_t i=0;i<g.frame.text_bytes && g.frame.utf8;i++) {
    unsigned char c=(unsigned char)g.frame.utf8[i];
    if(c=='"'||c=='\\')fprintf(out,"\\%c",c);
    else if(c<32)fprintf(out,"\\u%04x",c);
    else fputc(c,out);
  }
  fprintf(out,"\"}\n");
  return fclose(out)==0;
}
