/* SPDX-License-Identifier: MIT */
/* Deterministic --drive inputs go through the same HWND handlers as a mouse or
   keyboard. Offsets only locate test coordinates; they never set selection. */
static int select_drive_pointer(const char *event, size_t offset, int trailing) {
  compute_view();
  for (size_t i = 0; i < g.frame.shell_line_count; i++) {
    const exr_line *line = &g.frame.shell_lines[i];
    for (size_t j = line->glyph_start; j < line->glyph_start+line->glyph_count; j++) {
      const exr_glyph *glyph = &g.frame.glyphs[j];
      if (offset < glyph->cluster_start || offset >= glyph->cluster_end || glyph->flags & (EXR_GLYPH_HIDDEN|EXR_GLYPH_GENERATED)) continue;
      float fraction = trailing ? .9f : .1f;
      float x = glyph->x+glyph->advance*fraction, y = line->y+line->height*.5f;
      if (glyph->flags & EXR_GLYPH_VERTICAL) { x = line->x+line->width*.5f; y = glyph->baseline+glyph->advance*fraction; }
      UINT message = !strcmp(event, "down") ? WM_LBUTTONDOWN : !strcmp(event, "double") ? WM_LBUTTONDBLCLK :
        !strcmp(event, "up") ? WM_LBUTTONUP : WM_MOUSEMOVE;
      SendMessageW(g.page, message, message == WM_LBUTTONUP ? 0 : MK_LBUTTON,
        MAKELPARAM((int)lroundf(g.view.dx+x*g.view.scale), (int)lroundf(g.view.dy+y*g.view.scale)));
      return 1;
    }
  }
  return 0;
}
static void select_drive_key(UINT key, int shift, int control) {
  BYTE saved[256], state[256]; GetKeyboardState(saved); memcpy(state, saved, sizeof(state));
  state[VK_SHIFT] = shift ? 0x80 : 0; state[VK_CONTROL] = control ? 0x80 : 0;
  SetKeyboardState(state); SendMessageW(g.page, WM_KEYDOWN, key, 0); SetKeyboardState(saved);
}
static int select_drive_write(const char *name, const char *suffix, const void *data, size_t size) {
  wchar_t path[HOST_PATH], filename[256]; wchar_t *a = host_wide(name, strlen(name)), *b = host_wide(suffix, strlen(suffix));
  swprintf(filename, 256, L"%ls%ls", a, b); free(a); free(b);
  path_join(path, HOST_PATH, g.evidence_dir, filename);
  FILE *file = _wfopen(path, L"wb"); if (!file) return 0;
  int ok = fwrite(data, 1, size, file) == size; return fclose(file) == 0 && ok;
}
static int select_drive_dump(const char *name) {
  char *text = NULL; size_t bytes = shell_selection_bytes(&text);
  int ok = select_drive_write(name, ".utf8", text, bytes); free(text);
  if (OpenClipboard(g.window)) {
    HANDLE memory = GetClipboardData(CF_UNICODETEXT); wchar_t *wide = memory ? GlobalLock(memory) : NULL;
    char *clipboard = wide ? host_utf8(wide) : NULL;
    ok &= select_drive_write(name, ".clipboard.utf8", clipboard, clipboard ? strlen(clipboard) : 0);
    free(clipboard); if (wide) GlobalUnlock(memory); CloseClipboard();
  } else ok = 0;
  exr_document *document = NULL; size_t size = 0;
  if (exr_publication_load(select_publication(), g.frame.part, &document, NULL) == EXR_OK) {
    const char *source = exr_document_text(document, &size);
    ok &= select_drive_write(name, ".part.utf8", source, size); exr_document_free(document);
  } else ok = 0;
  exr_text_range_match match = {0};
  int resolved = select_anchor.start.part_id && exr_range_from_anchor(select_publication(), &select_anchor, NULL, &match, NULL) == EXR_OK &&
    match.state == EXR_ANCHOR_FOUND && match.range.start.part == select_range.start.part &&
    match.range.start.offset == select_range.start.offset && match.range.end.part == select_range.end.part && match.range.end.offset == select_range.end.offset;
  char json[512]; int count = snprintf(json, sizeof(json),
    "{\"valid\":%d,\"active\":%d,\"drag\":%d,\"start\":[%zu,%zu],\"end\":[%zu,%zu],\"bytes\":%zu,\"anchor_roundtrip\":%d}\n",
    select_valid, g.selection.active, select_drag, select_range.start.part, select_range.start.offset,
    select_range.end.part, select_range.end.offset, bytes, resolved);
  return select_drive_write(name, ".selection.json", json, (size_t)count) && ok;
}
