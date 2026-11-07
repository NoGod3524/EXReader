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
    float metrics[12]={0};shell_d2d_page_metrics(host_shell,metrics);
    RECT image=g.frame.shell_image;
    if(!IsRectEmpty(&image)) OffsetRect(&image,g.view.dx,g.view.dy+shell_px(SHELL_TOPBAR_H,shell_dpi));
    fprintf(out,"{\"image\":[%ld,%ld,%ld,%ld],\"body\":[%ld,%d,%ld,%ld],\"page_number\":{\"box\":[0,%ld,%ld,%ld],\"font\":%.3f,\"weight\":%.0f,\"digits\":[",
      image.left,image.top,image.right,image.bottom,
      (client.right-g.frame.shell_geometry.width)/2,shell_px(SHELL_TOPBAR_H+SHELL_BODY_TOP,shell_dpi),
      (client.right+g.frame.shell_geometry.width)/2,client.bottom-shell_px(SHELL_PAGE_NUMBER_H+SHELL_BODY_GAP,shell_dpi),
      client.bottom-shell_px(SHELL_PAGE_NUMBER_H,shell_dpi),client.right,client.bottom,(double)metrics[0],(double)metrics[1]);
    for(int i=2;i<12;i++) fprintf(out,"%s%.6f",i==2?"":",",(double)metrics[i]);
    fprintf(out,"]},");
  }
  {
    float targets[4];
    typedef UINT (WINAPI *dpi_fn)(HWND);
    dpi_fn dpi = (dpi_fn)(void (*)(void))GetProcAddress(GetModuleHandleW(L"user32.dll"), "GetDpiForWindow");
    shell_d2d_target_dpi(host_shell, targets);
    fprintf(out, "\"actual_window_dpi\":%u,\"display\":[%d,%d],\"target_dpi\":[%.1f,%.1f,%.1f,%.1f],",
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

static int shell_settings_measure(const char *name) {
  wchar_t filename[256],path[HOST_PATH];
  wchar_t *wide=host_wide(name,strlen(name));swprintf(filename,256,L"%ls.json",wide);free(wide);
  path_join(path,HOST_PATH,g.evidence_dir,filename);FILE *out=_wfopen(path,L"wb");if(!out) return 0;
  RECT outer,client;POINT origin={0,0};GetWindowRect(g.window,&outer);GetClientRect(g.window,&client);ClientToScreen(g.window,&origin);
  LOGBRUSH brush={0};GetObject((HBRUSH)GetClassLongPtrW(g.window,GCLP_HBRBACKGROUND),sizeof(brush),&brush);
  fprintf(out,"{\"font\":%.0f,\"theme\":%d,\"dark\":%d,\"open\":%d,\"animating\":%d,\"animation_ms\":%.6f,\"class_bg\":%lu,\"foreground\":%d,\"window\":[%ld,%ld],\"client_box\":[%ld,%ld,%ld,%ld],\"controls\":{",
    (double)shell_font,shell_theme_mode,shell_is_dark(),shell_panel_open,shell_animating,shell_animation_elapsed,
    (unsigned long)brush.lbColor,GetForegroundWindow()==g.window,outer.left,outer.top,origin.x-outer.left,origin.y-outer.top,client.right,client.bottom);
  const char *names[]={"minus","plus","light","dark","system"};
  for(int i=0;i<5;i++) {
    RECT box;GetWindowRect(shell_button_named(names[i]),&box);MapWindowPoints(NULL,g.window,(POINT *)&box,2);
    fprintf(out,"%s\"%s\":[%ld,%ld,%ld,%ld]",i?",":"",names[i],box.left,box.top,box.right,box.bottom);
  }
  fprintf(out,"},\"icons\":{");
  HWND icons[]={shell_toc,shell_settings};
  for(int i=0;i<2;i++) {
    RECT box;shell_button_circle(icons[i],client.right,&box);
    fprintf(out,"%s\"%s\":[%ld,%ld,%ld,%ld]",i?",":"",i?"settings":"toc",box.left,box.top,box.right,box.bottom);
  }
  RECT panel;GetWindowRect(shell_panel,&panel);MapWindowPoints(NULL,g.window,(POINT *)&panel,2);
  panel.left+=shell_px(SHELL_SHADOW_PAD,shell_dpi);panel.right-=shell_px(SHELL_SHADOW_PAD,shell_dpi);
  panel.top+=shell_px(SHELL_SHADOW_TOP,shell_dpi);panel.bottom-=shell_px(SHELL_SHADOW_PAD,shell_dpi);
  float metrics[8]={0};if(host_shell) shell_d2d_metrics(host_shell,metrics);
  fprintf(out,"},\"panel\":[%ld,%ld,%ld,%ld],\"typography\":[%.3f,%.0f,%.3f,%.0f,%.3f,%.0f,%.3f,%.3f]}\n",
    panel.left,panel.top,panel.right,panel.bottom,(double)metrics[0],(double)metrics[1],(double)metrics[2],(double)metrics[3],(double)metrics[4],(double)metrics[5],(double)metrics[6],(double)metrics[7]);
  return fclose(out)==0;
}
