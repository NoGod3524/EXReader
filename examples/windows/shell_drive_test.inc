/* SPDX-License-Identifier: MIT */
/* Included only by EXR_READER_TEST_DRIVERS builds. */
static FILE *drive_file;
static int drive_step_active;
static int drive_expect_idle;
static unsigned drive_step_start;
static char drive_action[64];
static char drive_args[8][HOST_PATH];
static int drive_argc;

static unsigned long long fnv1a(const void *data, size_t size) {
  const unsigned char *bytes = data;
  unsigned long long hash = 1469598103934665603ULL;
  size_t i;
  for (i = 0; i < size; i++) {
    hash ^= bytes[i];
    hash *= 1099511628211ULL;
  }
  return hash;
}

static void escape_value(const char *input, char *out, size_t capacity) {
  size_t at = 0;
  if (!capacity) return;
  while (input && *input && at + 4 < capacity) {
    unsigned char c = (unsigned char)*input++;
    if (c == '%' || c == '\t' || c == '\r' || c == '\n' || c == ';' || c == '=' || c == '|') {
      out[at++] = '%';
      out[at++] = "0123456789ABCDEF"[c >> 4];
      out[at++] = "0123456789ABCDEF"[c & 15];
    } else if (c < 32) {
      out[at++] = ' ';
    } else {
      out[at++] = (char)c;
    }
  }
  out[at] = 0;
}

static void detail_add(char *buffer, size_t capacity, const char *key, const char *value) {
  char escaped[HOST_PATH * 2];
  size_t used;
  escape_value(value ? value : "", escaped, sizeof(escaped));
  used = strlen(buffer);
  if (used + strlen(key) + strlen(escaped) + 4 >= capacity) return;
  if (used) buffer[used++] = ';';
  strcpy(buffer + used, key);
  used += strlen(key);
  buffer[used++] = '=';
  strcpy(buffer + used, escaped);
}

static void drive_log(const char *kind, const char *action, int pass, const char *detail) {
  if (!g.drive_log) return;
  fprintf(g.drive_log, "%s\t%d\t%s\t%s\t%s\n", kind, g.drive_index, action,
          pass ? "PASS" : "FAIL", detail ? detail : "");
  fflush(g.drive_log);
}

static void drive_step_finish(int pass, const char *detail) {
  drive_log("STEP", drive_action, pass, detail);
  if (!pass) g.drive_failures++;
  drive_step_active = 0;
  drive_expect_idle = 0;
}

static int page_text_snapshot(char *out, size_t capacity) {
  size_t start, end, size = 0;
  const char *bytes = NULL;
  if (!g.frame.valid) { if (capacity) out[0] = 0; return 0; }
  if (g.frame.fixed) {
    if (g.frame.fixed_text) {
      bytes = exr_fixed_text_string(g.frame.fixed_text, &size);
      start = 0;
      end = size;
    } else {
      start = end = 0;
    }
  } else {
    bytes = g.frame.utf8; size = g.frame.text_bytes; start = 0; end = size;
  }
  if (!bytes) { if (capacity) out[0] = 0; return 0; }
  if (end > size) end = size;
  truncate_utf8(out, capacity, bytes + start, end - start);
  return (int)(end - start);
}

static void drive_state(const char *name) {
  char detail[8192];
  char status_utf8[1024];
  char *title = NULL;
  char page_prefix[HOST_TEXT_PREVIEW + 8];
  char offset_text[80];
  size_t start, end;
  int length;
  size_t i;
  unsigned long long page_hash = 0;
  size_t hashed_length = 0;
  selection_bounds(&start, &end);
  memset(detail, 0, sizeof(detail));
  if (g.has_current && g.current.title) title = host_strdup(g.current.title);
  status_utf8[0] = 0;
  {
    char *encoded = host_utf8(g.status_text);
    if (encoded) {
      strncpy(status_utf8, encoded, sizeof(status_utf8) - 1);
      status_utf8[sizeof(status_utf8) - 1] = 0;
      free(encoded);
    }
  }
  if (g.frame.valid) {
    if (!g.frame.fixed && g.frame.utf8) {
      if (g.frame.range_end - g.frame.range_start == g.frame.text_bytes) {
        page_hash = fnv1a(g.frame.utf8, g.frame.text_bytes);
        hashed_length = g.frame.text_bytes;
      }
    } else if (g.frame.fixed_text) {
      size_t size = 0;
      const char *bytes = exr_fixed_text_string(g.frame.fixed_text, &size);
      if (bytes) {
        page_hash = fnv1a(bytes, size);
        hashed_length = size;
      }
    }
  }
  length = page_text_snapshot(page_prefix, sizeof(page_prefix));
  offset_text[0] = 0;
  if (g.frame.valid) {
    if (!g.frame.fixed && g.frame.utf8) {
      truncate_utf8(offset_text, sizeof(offset_text), g.frame.utf8, g.frame.text_bytes < 64 ? g.frame.text_bytes : 64);
    } else if (g.frame.fixed_text) {
      size_t size = 0;
      const char *bytes = exr_fixed_text_string(g.frame.fixed_text, &size);
      truncate_utf8(offset_text, sizeof(offset_text), bytes, size < 64 ? size : 64);
    }
  }
  {
    char number[32];
    snprintf(number, sizeof(number), "%lld", (long long)(g.has_current ? g.current.id : 0));
    detail_add(detail, sizeof(detail), "book_id", number);
    snprintf(number, sizeof(number), "%llu", (unsigned long long)(g.frame.valid ? g.frame.page : 0));
    detail_add(detail, sizeof(detail), "page", number);
    snprintf(number, sizeof(number), "%llu", (unsigned long long)(g.frame.valid ? g.frame.page_count : 0));
    detail_add(detail, sizeof(detail), "page_count", number);
    snprintf(number, sizeof(number), "%d", g.font_percent);
    detail_add(detail, sizeof(detail), "font", number);
    snprintf(number, sizeof(number), "%d", g.zoom_percent);
    detail_add(detail, sizeof(detail), "zoom", number);
    snprintf(number, sizeof(number), "%llu", (unsigned long long)(g.frame.valid ? g.frame.range_start : 0));
    detail_add(detail, sizeof(detail), "offset", number);
    snprintf(number, sizeof(number), "%d", length);
    detail_add(detail, sizeof(detail), "page_text_len", number);
    snprintf(number, sizeof(number), "%llu", (unsigned long long)(g.frame.valid ? g.frame.range_end - g.frame.range_start : 0));
    detail_add(detail, sizeof(detail), "range_len", number);
    snprintf(number, sizeof(number), "%d", (int)current_note_count());
    detail_add(detail, sizeof(detail), "notes", number);
    {
      LRESULT selected = g.books ? SendMessageW(g.books, LB_GETCURSEL, 0, 0) : LB_ERR;
      long long selected_id = 0;
      if (selected != LB_ERR && (size_t)selected < g.shelf_count) selected_id = (long long)g.shelf[selected].id;
      snprintf(number, sizeof(number), "%lld", selected_id);
      detail_add(detail, sizeof(detail), "selected_id", number);
    }
    snprintf(number, sizeof(number), "%d", g.selection.active ? 1 : 0);
    detail_add(detail, sizeof(detail), "selection_active", number);
    snprintf(number, sizeof(number), "%llu", page_hash);
    detail_add(detail, sizeof(detail), "page_text_fnv", number);
    snprintf(number, sizeof(number), "%llu", (unsigned long long)hashed_length);
    detail_add(detail, sizeof(detail), "page_hash_len", number);
    snprintf(number, sizeof(number), "%d", g.session.bounded); detail_add(detail, sizeof(detail), "bounded", number);
    snprintf(number, sizeof(number), "%llu", (unsigned long long)g.frame.part); detail_add(detail, sizeof(detail), "part", number);
    snprintf(number, sizeof(number), "%lu", g.frame.generation); detail_add(detail, sizeof(detail), "generation", number);
    snprintf(number, sizeof(number), "%d", g.session.hold_progress); detail_add(detail, sizeof(detail), "progress_record_preserved", number);
    if (g.session.bounded) {
      const exr_part *parts; size_t part_count = 0; exr_chapter_stats stats = g.frame.chapter_stats;
      parts = exr_publication_parts(g.session.publication, &part_count);
      detail_add(detail, sizeof(detail), "part_path", g.frame.part < part_count ? parts[g.frame.part].path : "");
#define HOST_STAT(field) snprintf(number, sizeof(number), "%llu", (unsigned long long)stats.field); detail_add(detail, sizeof(detail), #field, number)
      HOST_STAT(book_bytes); HOST_STAT(index_bytes); HOST_STAT(parse_workspace_bytes); HOST_STAT(peak_parse_workspace_bytes);
      HOST_STAT(projection_bytes); HOST_STAT(page_cache_bytes); HOST_STAT(checkpoint_bytes); HOST_STAT(explicit_snapshot_bytes);
      HOST_STAT(windows_loaded); HOST_STAT(windows_evicted);
#undef HOST_STAT
      snprintf(number, sizeof(number), "%llu", (unsigned long long)(g.frame.text_bytes + 1 + (wcslen(g.frame.text) + 1) * sizeof(wchar_t) + g.frame.glyph_count * sizeof(exr_glyph)));
      detail_add(detail, sizeof(detail), "owned_frame_text_geometry_bytes", number);
      snprintf(number, sizeof(number), "%llu", (unsigned long long)((size_t)g.frame.bitmap.stride * g.frame.bitmap.height));
      detail_add(detail, sizeof(detail), "bitmap_bytes", number);
      snprintf(number, sizeof(number), "%llu", (unsigned long long)((size_t)g.frame.bitmap.width * g.frame.bitmap.height * sizeof(uint32_t)));
      detail_add(detail, sizeof(detail), "dib_bytes", number);
    }
  }
  detail_add(detail, sizeof(detail), "state", name);
#ifdef EXR_READER_PRODUCT_CATALOG
  detail_add(detail,sizeof(detail),"product_pending",g.product_pending ? "1":"0");
#endif
  detail_add(detail, sizeof(detail), "title", title ? title : "");
  detail_add(detail, sizeof(detail), "kind", g.has_current ? (g.frame.fixed ? "fixed" : "reflow") : "none");
  detail_add(detail, sizeof(detail), "page_text", page_prefix);
  detail_add(detail, sizeof(detail), "offset_text", offset_text);
  detail_add(detail, sizeof(detail), "status", status_utf8);
  if (g.selection.active) {
    char number[64];
    snprintf(number, sizeof(number), "%llu", (unsigned long long)start);
    detail_add(detail, sizeof(detail), "selection_start", number);
    snprintf(number, sizeof(number), "%llu", (unsigned long long)end);
    detail_add(detail, sizeof(detail), "selection_end", number);
  }
  drive_log("STATE", name, 1, detail);
  for (i = 0; i < g.shelf_count; i++) {
    char row[2048];
    char *author = g.shelf[i].author ? host_strdup(g.shelf[i].author) : host_strdup("");
    memset(row, 0, sizeof(row));
    detail_add(row, sizeof(row), "title", g.shelf[i].title ? g.shelf[i].title : "");
    detail_add(row, sizeof(row), "author", author);
    {
      char id[32];
      snprintf(id, sizeof(id), "%lld", (long long)g.shelf[i].id);
      detail_add(row, sizeof(row), "id", id);
    }
    {
      char format[16];
      snprintf(format, sizeof(format), "%d", (int)g.shelf[i].format);
      detail_add(row, sizeof(row), "format", format);
    }
    free(author);
    drive_log("SHELF", name, 1, row);
  }
  for (i = 0; i < current_note_count(); i++) {
    char row[4096];
    char number[64];
    char quote[512];
    char comment[1024];
    memset(row, 0, sizeof(row));
    if (g.session.fixed) {
      const exr_fixed_note *note = &g.fixed_notes[i];
      truncate_utf8(quote, sizeof(quote), note->anchor.exact, note->anchor.exact_size);
      truncate_utf8(comment, sizeof(comment), note->text, note->text ? strlen(note->text) : 0);
      snprintf(number, sizeof(number), "%lld", (long long)note->id);
      detail_add(row, sizeof(row), "id", number);
      detail_add(row, sizeof(row), "kind", "fixed");
      snprintf(number, sizeof(number), "%llu", (unsigned long long)note->page);
      detail_add(row, sizeof(row), "page", number);
    } else if (g.session.bounded) {
      const exr_epub_note *note = &g.epub_notes[i];
      truncate_utf8(quote, sizeof(quote), note->location.selector.exact, note->location.selector.exact ? strlen(note->location.selector.exact) : 0);
      truncate_utf8(comment, sizeof(comment), note->text, note->text ? strlen(note->text) : 0);
      snprintf(number, sizeof(number), "%lld", (long long)note->id); detail_add(row, sizeof(row), "id", number);
      detail_add(row, sizeof(row), "kind", "reflow"); detail_add(row, sizeof(row), "storage", "epub_notes");
      detail_add(row, sizeof(row), "path", note->location.path);
      snprintf(number, sizeof(number), "%llu", (unsigned long long)note->location.part); detail_add(row, sizeof(row), "part", number);
      snprintf(number, sizeof(number), "%llu", (unsigned long long)note->location.selector.start); detail_add(row, sizeof(row), "page", number);
    } else {
      const exr_note *note = &g.reflow_notes[i];
      truncate_utf8(quote, sizeof(quote), note->anchor.exact,
                    note->anchor.exact ? strlen(note->anchor.exact) : 0);
      truncate_utf8(comment, sizeof(comment), note->text, note->text ? strlen(note->text) : 0);
      snprintf(number, sizeof(number), "%lld", (long long)note->id);
      detail_add(row, sizeof(row), "id", number);
      detail_add(row, sizeof(row), "kind", "reflow");
      snprintf(number, sizeof(number), "%llu", (unsigned long long)note->start);
      detail_add(row, sizeof(row), "page", number);
    }
    detail_add(row, sizeof(row), "quote", quote);
    detail_add(row, sizeof(row), "comment", comment);
    drive_log("NOTE", name, 1, row);
  }
  free(title);
}

static int snapshot_png(const char *name) {
  RECT area;
  HDC screen, memory;
  BITMAPINFO info;
  void *bits = NULL;
  HBITMAP bitmap;
  HGDIOBJ previous;
  exr_bitmap image;
  exr_error error = {0};
  wchar_t path[HOST_PATH];
  wchar_t filename[256];
  char *utf8;
  int width, height, x, y, ok, nonzero = 0;
  size_t i, total;
  if (!g.evidence_dir[0] || !g.window) return 0;
  if (host_offscreen) RedrawWindow(g.window, NULL, NULL, RDW_INVALIDATE | RDW_ERASE | RDW_ALLCHILDREN | RDW_UPDATENOW);
  GetWindowRect(g.window, &area);
  width = area.right - area.left;
  height = area.bottom - area.top;
  if (width <= 0 || height <= 0) return 0;
  screen = GetDC(NULL);
  memory = CreateCompatibleDC(screen);
  memset(&info, 0, sizeof(info));
  info.bmiHeader.biSize = sizeof(BITMAPINFOHEADER);
  info.bmiHeader.biWidth = width;
  info.bmiHeader.biHeight = -height;
  info.bmiHeader.biPlanes = 1;
  info.bmiHeader.biBitCount = 32;
  info.bmiHeader.biCompression = BI_RGB;
  bitmap = CreateDIBSection(memory, &info, DIB_RGB_COLORS, &bits, NULL, 0);
  if (!bitmap || !bits) {
    DeleteDC(memory);
    ReleaseDC(NULL, screen);
    return 0;
  }
  previous = SelectObject(memory, bitmap);
  ok = (int)PrintWindow(g.window, memory, 2 /* PW_RENDERFULLCONTENT */);
#ifdef EXR_READER_WINDOWS_SHELL
  /* PrintWindow's recursive child pass does not preserve an overlapping
     D2D/GDI sibling's z-order. Capture the actual overlay HWND last. */
  HWND capture_panel=shell_toc_open || shell_toc_animating ? shell_toc_panel:shell_panel;
  if(ok && shell_active && IsWindowVisible(capture_panel)) {
    RECT panel;GetWindowRect(capture_panel,&panel);
    HDC overlay=CreateCompatibleDC(memory);
    HBITMAP image=CreateCompatibleBitmap(memory,panel.right-panel.left,panel.bottom-panel.top);
    HGDIOBJ old=SelectObject(overlay,image);
    if(PrintWindow(capture_panel,overlay,0))
      BitBlt(memory,panel.left-area.left,panel.top-area.top,panel.right-panel.left,panel.bottom-panel.top,overlay,0,0,SRCCOPY);
    else ok=0;
    SelectObject(overlay,old);DeleteObject(image);DeleteDC(overlay);
  }
#endif
  if (!ok && !host_offscreen) {
    x = area.left; y = area.top;
    BitBlt(memory, 0, 0, width, height, screen, x, y, SRCCOPY);
  }
  if (!ok && host_offscreen) {
    SelectObject(memory, previous); DeleteObject(bitmap); DeleteDC(memory); ReleaseDC(NULL, screen); return 0;
  }
  SelectObject(memory, previous);
  total = (size_t)width * height;
  image.width = (uint32_t)width;
  image.height = (uint32_t)height;
  image.stride = (uint32_t)width * 4;
  image.channels = 4;
  image.pixels = malloc(total * 4);
  if (!image.pixels) {
    DeleteObject(bitmap);
    DeleteDC(memory);
    ReleaseDC(NULL, screen);
    return 0;
  }
  for (i = 0; i < total; i++) {
    const unsigned char *p = (const unsigned char *)bits + i * 4;
    image.pixels[i * 4 + 0] = p[2];
    image.pixels[i * 4 + 1] = p[1];
    image.pixels[i * 4 + 2] = p[0];
    image.pixels[i * 4 + 3] = 255;
    if (p[0] || p[1] || p[2]) nonzero = 1;
  }
  {
    wchar_t *wide_name = host_wide(name, strlen(name));
    swprintf(filename, 256, L"%ls.png", wide_name ? wide_name : L"shot");
    free(wide_name);
  }
  path_join(path, HOST_PATH, g.evidence_dir, filename);
  utf8 = host_utf8(path);
  ok = utf8 && exr_bitmap_write_png(&image, utf8, &error) == EXR_OK;
  free(utf8);
  free(image.pixels);
  DeleteObject(bitmap);
  DeleteDC(memory);
  ReleaseDC(NULL, screen);
  if (!ok) return 0;
  {
    char detail[512];
    memset(detail, 0, sizeof(detail));
    detail_add(detail, sizeof(detail), "file", name);
    detail_add(detail, sizeof(detail), "nonzero", nonzero ? "1" : "0");
    drive_log("SHOT", name, 1, detail);
    if (host_offscreen) {
      RECT client, outer; POINT origin = {0,0}; FILE *metadata;
      GetClientRect(g.window, &client); GetWindowRect(g.window, &outer); ClientToScreen(g.window, &origin);
      wchar_t *wide_name = host_wide(name, strlen(name));
      swprintf(filename, 256, L"%ls.client.json", wide_name ? wide_name : L"shot"); free(wide_name);
      path_join(path, HOST_PATH, g.evidence_dir, filename);
      metadata = _wfopen(path, L"wb");
      if (!metadata) return 0;
      fprintf(metadata, "[%ld,%ld,%ld,%ld]\n", origin.x-outer.left, origin.y-outer.top, client.right, client.bottom);
      fclose(metadata);
    }
  }
  return 1;
}

static int clipboard_contains(const char *needle) {
  HANDLE handle;
  wchar_t *text;
  char *utf8;
  int found = 0;
  if (!OpenClipboard(g.window)) return 0;
  handle = GetClipboardData(CF_UNICODETEXT);
  if (handle) {
    text = GlobalLock(handle);
    if (text) {
      utf8 = host_utf8(text);
      if (utf8) {
        found = strstr(utf8, needle) != NULL;
        free(utf8);
      }
      GlobalUnlock(handle);
    }
  }
  CloseClipboard();
  return found;
}

static int shelf_click(const char *title) {
  wchar_t *wide = host_wide(title, strlen(title));
  int index;
  if (!wide) return 0;
  index = shelf_index_for_title(wide);
  free(wide);
  if (index < 0) return 0;
  SendMessageW(g.books, LB_SETCURSEL, (WPARAM)index, 0);
  SetFocus(g.books);
  return 1;
}

static int check_status_contains(const char *needle) {
  char *text = host_utf8(g.status_text);
  int found = text && strstr(text, needle) != NULL;
  free(text);
  return found;
}

static int check_selection(int minimum, const char *needle) {
  size_t start, end;
  char *text = NULL;
  size_t size;
  if (!g.selection.active) return 0;
  selection_bounds(&start, &end);
  if ((size_t)minimum && end - start < (size_t)minimum) return 0;
  if (!needle || !needle[0]) return 1;
  size = selection_bytes(&text);
  if (!size || !text) { free(text); return 0; }
  {
    int found = strstr(text, needle) != NULL;
    free(text);
    return found;
  }
}

#ifdef EXR_READER_WINDOWS_SHELL
#include "shell_measure.inc"
#include "shell_selection_drive.inc"
#include "shell_annotations_drive.inc"
#include "shell_style_drive.inc"
#include "shell_shelfmeta_drive.inc"
#include "shell_tts_drive.inc"
#include "shell_dictionary_drive.inc"
#endif

static int drive_execute(void) {
  const char *action = drive_args[0];
  char detail[1024];
  int launches = 0;
  memset(detail, 0, sizeof(detail));
#ifdef EXR_READER_WINDOWS_SHELL
  if (!strncmp(action,"style_",6) || !strncmp(action,"footnote_",9)) return style_drive(action);
  if (!strncmp(action,"sm_",3)) {
    drive_step_finish(sm_drive(action),"shelf metadata action");return 0;
  }
  if (!strncmp(action,"tts_",4)) {
    drive_step_finish(tts_drive(action),"speech action dispatched");return 0;
  }
  if (!strncmp(action,"annot_",6)) {
    drive_step_finish(annot_drive(action),"annotation action dispatched");return 0;
  }
  if (!strncmp(action,"dict_",5)) {
    drive_step_finish(dict_drive(action),"dictionary action dispatched");return 0;
  }
#include "shell_annotations_navigation.inc"
#include "shell_shelf_drive.inc"
  if (!strcmp(action, "select_pointer")) {
    int ok = select_drive_pointer(drive_args[1], (size_t)strtoull(drive_args[2], NULL, 10), atoi(drive_args[3]));
    drive_step_finish(ok, "selection pointer dispatched"); return 0;
  }
  if (!strcmp(action, "select_key")) {
    UINT key = !strcmp(drive_args[1], "left") ? VK_LEFT : !strcmp(drive_args[1], "right") ? VK_RIGHT :
      !strcmp(drive_args[1], "up") ? VK_UP : !strcmp(drive_args[1], "down") ? VK_DOWN :
      !strcmp(drive_args[1], "escape") ? VK_ESCAPE : (UINT)drive_args[1][0];
    select_drive_key(key, atoi(drive_args[2]), atoi(drive_args[3]));
    drive_step_finish(1, "selection key dispatched"); return 0;
  }
  if (!strcmp(action, "select_dump")) {
    drive_step_finish(select_drive_dump(drive_args[1]), "logical selection and clipboard saved"); return 0;
  }
  if (!strcmp(action, "select_edge")) {
    compute_view(); select_x = g.view.dx-8; select_y = g.view.dy+g.view.bh+8;
    if (g.frame.writing_mode != EXR_WRITING_HORIZONTAL_TB) select_y = g.view.dy+20;
    SendMessageW(g.page, WM_MOUSEMOVE, MK_LBUTTON, MAKELPARAM(select_x, select_y));
    SendMessageW(g.page, WM_TIMER, SHELL_SELECT_TIMER, 0);
    drive_step_finish(1, "selection edge turn dispatched"); return 0;
  }
#endif
  if (host_offscreen && (!strcmp(action, "activate") || !strcmp(action, "key_tab") || !strcmp(action, "probe_resize"))) {
    drive_step_finish(0, "action requires foreground; forbidden by --offscreen"); return 0;
  }
  if (!strcmp(action, "wait_idle")) {
    drive_expect_idle = 1;
    return 1;
  }
  if (!strcmp(action, "delay")) {
    g.delay_ms = atoi(drive_args[1]);
    drive_step_finish(1, "delay_ms set");
    return 0;
  }
  if (!strcmp(action, "wait")) {
    Sleep((DWORD)atoi(drive_args[1]));
    drive_step_finish(1, "waited");
    return 0;
  }
  if(!strcmp(action,"probe_move")) { page_step(atoi(drive_args[1]));drive_expect_idle=1;return 1; }
  if(!strcmp(action,"probe_wait")) {
    if(GetTickCount()-drive_step_start<(DWORD)atoi(drive_args[1]))return 1;
    drive_step_finish(1,"waited without blocking UI");return 0;
  }
  if(!strcmp(action,"probe_resize")) {
    SetWindowPos(g.window,HWND_TOPMOST,100,100,atoi(drive_args[1]),atoi(drive_args[2]),SWP_SHOWWINDOW);
    drive_step_finish(1,"test window sized");return 0;
  }
  if(!strcmp(action,"probe_mark")) { host_probe_log(drive_args[1],0);drive_step_finish(1,"marked");return 0; }
  if(!strcmp(action,"probe_begin")) {
    host_probe_reset();host_probe_log("probe_begin",0);
    host_probe_log("layout_calls",host_probe_layout_calls);host_probe_log("render_calls",host_probe_render_calls);
    page_dirty(g.page,1);UpdateWindow(g.page);
    drive_step_finish(1,"paint counters reset");return 0;
  }
  if(!strcmp(action,"probe_end")) {
    page_dirty(g.page,1);UpdateWindow(g.page);
    host_probe_log("total_presented",host_probe_presented);host_probe_log("total_blank",host_probe_blank);
    host_probe_log("total_stale_size",host_probe_stale);host_probe_log("total_present_failed",host_probe_present_failed);
    host_probe_log("total_bitblt",host_probe_bitblt);host_probe_log("total_stretch",host_probe_stretch);
    host_probe_log("total_deferred",host_probe_deferred);
    host_probe_log("layout_calls",host_probe_layout_calls);host_probe_log("render_calls",host_probe_render_calls);
    host_probe_log("probe_end",0);host_probe_counting=0;
    drive_step_finish(1,"paint counters recorded");return 0;
  }
  if(!strcmp(action,"probe_title")) {
    wchar_t *title=host_wide(drive_args[1],strlen(drive_args[1]));SetWindowTextW(g.window,title);free(title);
    RECT area;POINT pt={0,0};GetClientRect(g.window,&area);
    host_probe_log("client_w",area.right);host_probe_log("client_h",area.bottom);
    MapWindowPoints(g.page,g.window,&pt,1);GetClientRect(g.page,&area);
    host_probe_log("roi_x",pt.x);host_probe_log("roi_y",pt.y);host_probe_log("roi_w",area.right);host_probe_log("roi_h",area.bottom);
    RECT logical,physical,client;POINT client_origin={0,0};
    GetWindowRect(g.window,&logical);GetClientRect(g.window,&client);ClientToScreen(g.window,&client_origin);
    typedef HANDLE (WINAPI *probe_dpi_fn)(HANDLE);
    probe_dpi_fn fn=(probe_dpi_fn)(void (*)(void))GetProcAddress(GetModuleHandleW(L"user32.dll"),"SetThreadDpiAwarenessContext");
    HANDLE old=fn?fn((HANDLE)(INT_PTR)-4):NULL;GetWindowRect(g.window,&physical);if(fn && old)fn(old);
    double ratio=(double)(physical.right-physical.left)/(logical.right-logical.left);
    host_probe_log("cap_x",physical.left+(client_origin.x-logical.left)*ratio);
    host_probe_log("cap_y",physical.top+(client_origin.y-logical.top)*ratio);
    host_probe_log("cap_w",client.right*ratio);host_probe_log("cap_h",client.bottom*ratio);
    host_probe_log("record_ready",0);drive_step_finish(1,"record ready");return 0;
  }
  if(!strcmp(action,"probe_wheel_burst")) {
    host_probe_burst_left=100;SetTimer(g.page,HOST_PROBE_BURST_TIMER,10,NULL);drive_expect_idle=1;return 1;
  }
  if (!strcmp(action, "probe_key") || !strcmp(action, "probe_wheel")) {
    SetFocus(g.page);
    host_probe_log("input_gen",(double)g.frame.generation);
    UINT key=!strcmp(drive_args[1],"left") ? VK_LEFT : !strcmp(drive_args[1],"right") ? VK_RIGHT : VK_NEXT;
    SendMessageW(g.page,!strcmp(action,"probe_key")?WM_KEYDOWN:WM_MOUSEWHEEL,!strcmp(action,"probe_key")?key:MAKEWPARAM(0,-WHEEL_DELTA),0);
    drive_expect_idle=1;return 1;
  }
  if (!strcmp(action, "quit")) {
    drive_step_finish(1, "closing");
    g.drive_done = 1;
    PostMessageW(g.window, WM_CLOSE, 0, 0);
    return 0;
  }
  if (!strcmp(action, "state")) {
    drive_state(drive_args[1][0] ? drive_args[1] : "state");
    drive_step_finish(1, "state captured");
    return 0;
  }
  if (!strcmp(action, "snapshot")) {
    int ok = snapshot_png(drive_args[1][0] ? drive_args[1] : "shot");
    drive_step_finish(ok, ok ? "screenshot written" : "screenshot failed");
    return 0;
  }
  if (!strcmp(action, "resize")) {
    int width = atoi(drive_args[1]), height = atoi(drive_args[2]);
    SetWindowPos(g.window, NULL, 0, 0, width, height, SWP_NOMOVE | SWP_NOZORDER | SWP_NOACTIVATE);
    drive_step_finish(1, "window resized");
    return 0;
  }
#ifdef EXR_READER_WINDOWS_SHELL
  if(!strncmp(action,"toc_",4) && !host_offscreen) {drive_step_finish(0,"TOC evidence requires --offscreen");return 0;}
  if(!strcmp(action,"toc_outside")) {
    PostMessageW(g.page,WM_LBUTTONDOWN,MK_LBUTTON,MAKELPARAM(600,300));
    PostMessageW(g.page,WM_LBUTTONUP,0,MAKELPARAM(600,300));drive_step_finish(1,"outside click posted");return 0;
  }
  if(!strcmp(action,"toc_scroll_hover")) {
    RECT thumb=shell_toc_thumb();SendMessageW(shell_toc_panel,WM_MOUSEMOVE,0,MAKELPARAM(shell_toc_width()-7,(thumb.top+thumb.bottom)/2));
    drive_step_finish(1,"scroll hover delivered");return 0;
  }
  if (!strcmp(action,"toc_measure")) {
    drive_step_finish(shell_toc_measure(drive_args[1]),"TOC measured");return 0;
  }
  if (!strcmp(action,"toc_scroll")) {
    shell_toc_scroll(atoi(drive_args[1]));drive_step_finish(1,"row index scrolled");return 0;
  }
  if(!strcmp(action,"toc_busy")) {
    page_step(1);shell_toc_jump(atoi(drive_args[1]));drive_expect_idle=1;return 1;
  }
  if(!strcmp(action,"toc_wheel") || !strcmp(action,"toc_wheel_outside")) {
    RECT r;GetWindowRect(!strcmp(action,"toc_wheel") ? shell_toc_panel:g.page,&r);
    POINT p={r.right-20,r.top+200};
    SendMessageW(shell_toc_list,WM_MOUSEWHEEL,MAKEWPARAM(0,atoi(drive_args[1])*WHEEL_DELTA),MAKELPARAM(p.x,p.y));
    drive_step_finish(1,"list wheel delivered");return 0;
  }
  if (!strcmp(action,"toc_click")) {
    int row=atoi(drive_args[1]);shell_toc_scroll(row);
    int y=shell_px(8,shell_dpi)+row*shell_toc_row_h()-shell_toc_scroll_y+shell_toc_row_h()/2;
    SendMessageW(shell_toc_list,WM_LBUTTONDOWN,MK_LBUTTON,MAKELPARAM(60,y));
    SendMessageW(shell_toc_list,WM_LBUTTONUP,0,MAKELPARAM(60,y));
    drive_expect_idle=1;return 1;
  }
  if (!strcmp(action,"toc_key")) {
    WPARAM key=!strcmp(drive_args[1],"up") ? VK_UP:!strcmp(drive_args[1],"down") ? VK_DOWN:
      !strcmp(drive_args[1],"enter") ? VK_RETURN:!strcmp(drive_args[1],"escape") ? VK_ESCAPE:
      !strcmp(drive_args[1],"home") ? VK_HOME:!strcmp(drive_args[1],"end") ? VK_END:
      !strcmp(drive_args[1],"pageup") ? VK_PRIOR:!strcmp(drive_args[1],"pagedown") ? VK_NEXT:VK_TAB;
    HWND focus=shell_toc_test_focus ? shell_toc_test_focus:shell_toc_list;
    shell_toc_test_shift=atoi(drive_args[2]);
    PostMessageW(focus,WM_KEYDOWN,key,1);PostMessageW(focus,WM_KEYUP,key,(LPARAM)(1u|(1u<<30)|(1u<<31)));
    drive_expect_idle=1;return 1;
  }
  if (!strcmp(action,"toc_focus")) {
    shell_toc_test_focus=!strcmp(drive_args[1],"toc") ? shell_toc:!strcmp(drive_args[1],"settings") ? shell_settings:
      !strcmp(drive_args[1],"page") ? g.page:shell_toc_list;
    shell_toc_keyboard=1;InvalidateRect(shell_toc_list,NULL,FALSE);drive_step_finish(host_offscreen,"offscreen focus injected");return 0;
  }
  if (!strcmp(action,"toc_state")) {
    int row=atoi(drive_args[2]);int y=shell_px(8,shell_dpi)+row*shell_toc_row_h()-shell_toc_scroll_y+shell_toc_row_h()/2;
    if(!strcmp(drive_args[1],"hover")) SendMessageW(shell_toc_list,WM_MOUSEMOVE,0,MAKELPARAM(40,y));
    else if(!strcmp(drive_args[1],"pressed")) SendMessageW(shell_toc_list,WM_LBUTTONDOWN,MK_LBUTTON,MAKELPARAM(40,y));
    else {shell_toc_hot=shell_toc_pressed=-1;shell_toc_keyboard=0;InvalidateRect(shell_toc_list,NULL,FALSE);}
    drive_step_finish(host_offscreen,"row event delivered");return 0;
  }
  if (!strcmp(action, "shell_page")) {
    long target = strtol(drive_args[1], NULL, 10)-1;
    if (!host_offscreen || target < 0 || target >= 1000000 || !g.frame.valid) {
      drive_step_finish(0, "offscreen page target invalid"); return 0;
    }
    if ((size_t)target == g.frame.page) { drive_step_finish(1, "already at page"); return 0; }
    page_step((int)(target-(long)g.frame.page)); drive_expect_idle = 1; return 1;
  }
  if (!strcmp(action,"shell_click")) {
    HWND button=shell_button_named(drive_args[1]);
    if(button) SendMessageW(button,BM_CLICK,0,0);
    drive_step_finish(button!=NULL,"button invoked");return 0;
  }
  if (!strcmp(action,"shell_render_focus")) {
    HWND previous=shell_render_focus;
    shell_render_focus=shell_button_named(drive_args[1]);
    shell_bar_regions(shell_render_focus);
    if(previous) InvalidateRect(previous,NULL,FALSE);
    if(shell_render_focus) InvalidateRect(shell_render_focus,NULL,FALSE);
    drive_step_finish(host_offscreen,"offscreen drawing-state injection; no activation");return 0;
  }
  if (!strcmp(action,"settings_measure")) {
    drive_step_finish(shell_settings_measure(drive_args[1]),"settings captured");return 0;
  }
  if(!strcmp(action,"search_query")) {
    if(!shell_search_open) shell_search_set(1);
    wchar_t *query=host_wide(drive_args[1],strlen(drive_args[1]));
    SetWindowTextW(shell_search_edit,query ? query:L"");free(query);drive_expect_idle=1;return 1;
  }
  if(!strcmp(action,"search_append")) {
    double start=host_probe_ms();
    wchar_t *query=host_wide(drive_args[1],strlen(drive_args[1]));
    SendMessageW(shell_search_edit,EM_SETSEL,(WPARAM)-1,(LPARAM)-1);
    SendMessageW(shell_search_edit,EM_REPLACESEL,TRUE,(LPARAM)(query ? query:L""));free(query);
    char detail[96];snprintf(detail,sizeof(detail),"native_edit_ms=%.6f",host_probe_ms()-start);
    drive_step_finish(1,detail);return 0;
  }
  if(!strcmp(action,"search_key")) {
    MSG message={0};message.hwnd=shell_search_edit;message.message=WM_KEYDOWN;
    message.wParam=!strcmp(drive_args[1],"esc") ? VK_ESCAPE:VK_RETURN;
    shell_search_test_shift=!strcmp(drive_args[1],"shift_enter");
    int handled=shell_translate(&message);shell_search_test_shift=0;
    drive_step_finish(handled,"search keyboard routed");return 0;
  }
  if(!strcmp(action,"search_check")) {
    char detail[512];snprintf(detail,sizeof(detail),"hits=%llu current=%llu open=%d calls=%u search_ms=%.3f total_ms=%.3f",
      (unsigned long long)shell_search_count_value,(unsigned long long)(shell_search_count_value ? shell_search_current+1:0),
      shell_search_open,shell_search_calls,shell_search_last_ms,shell_search_last_total_ms);
    int landed=1;
    if(shell_search_open && shell_search_count_value) {
      exr_search_result r=shell_search_hits[shell_search_current];
      landed=r.part==(g.frame.fixed ? g.frame.page:g.frame.part) && r.offset>=g.frame.range_start && r.offset<g.frame.range_end;
      if(!g.frame.fixed) {
        size_t n=g.frame.glyph_count;const exr_glyph *glyphs=g.frame.glyphs;
        if(!glyphs && g.frame.hit_layout) glyphs=exr_layout_glyphs(g.frame.hit_layout,&n);
        int glyph=0;for(size_t i=0;i<n;i++) if(glyphs[i].cluster_start<=r.offset && glyphs[i].cluster_end>r.offset) glyph=1;
        landed=landed && glyph;
      }
    }
    size_t used=strlen(detail);snprintf(detail+used,sizeof(detail)-used," landed=%d",landed);
    int pass=landed && (!strcmp(drive_args[1],"positive") ? shell_search_count_value>0:shell_search_count_value==(size_t)strtoull(drive_args[1],NULL,10)) &&
      (!drive_args[2][0] || shell_search_current+1==(size_t)strtoull(drive_args[2],NULL,10)) &&
      (!drive_args[3][0] || shell_search_open==atoi(drive_args[3]));
    drive_step_finish(pass,detail);return 0;
  }
  if (!strcmp(action, "shell_client")) {
    RECT client = {0, 0, atoi(drive_args[1]), atoi(drive_args[2])};
    /* The actual window DPI controls its nonclient frame, even for injected DPI tests. */
    typedef UINT (WINAPI *dpi_fn)(HWND);
    dpi_fn dpi = (dpi_fn)(void (*)(void))GetProcAddress(GetModuleHandleW(L"user32.dll"), "GetDpiForWindow");
    shell_adjust_client(&client, g.window, dpi ? dpi(g.window) : 96);
    SetWindowPos(g.window, NULL, 0, 0, client.right-client.left, client.bottom-client.top,
                 SWP_NOMOVE | SWP_NOZORDER | SWP_NOACTIVATE);
    drive_expect_idle = 1; return 1;
  }
  if (!strcmp(action, "shell_dpi")) {
    RECT bounds; GetWindowRect(g.window, &bounds);
    if (!host_offscreen) { drive_step_finish(0, "injected DPI requires --offscreen"); return 0; }
    SendMessageW(g.window, WM_DPICHANGED, MAKEWPARAM(atoi(drive_args[1]), atoi(drive_args[1])), (LPARAM)&bounds);
    drive_expect_idle = 1; return 1;
  }
  if (!strcmp(action, "shell_font")) {
    float font = (float)atof(drive_args[1]);
    if (font < SHELL_BODY_MIN_FONT || font > SHELL_BODY_MAX_FONT) { drive_step_finish(0, "font outside range"); return 0; }
    shell_font = font; shell_request_layout(); drive_expect_idle = 1; return 1;
  }
  if (!strcmp(action, "shell_measure")) {
    drive_step_finish(shell_measure(drive_args[1]), "physical layout captured"); return 0;
  }
  if (!strcmp(action, "shell")) {
    /* Historical shell|on setup remains accepted; only the new UI exists. */
    shell_sync();
    drive_step_finish(1, shell_active ? "reading screen" : "bookshelf");
    return 0;
  }
  if (!strcmp(action, "shell_key")) {
    /* Alt+Left / Alt+Right as the keyboard delivers them: WM_SYSKEYDOWN with
       the context bit, posted to the focused window and read by the loop. */
    static int posted;
    int want = !strcmp(drive_args[1], "right");
    if (!posted) {
      HWND focus = GetFocus();
      WPARAM key = want ? VK_RIGHT : VK_LEFT;
      if (!focus) focus = g.window;
      PostMessageW(focus, WM_SYSKEYDOWN, key, (LPARAM)(1u | (1u << 29)));
      PostMessageW(focus, WM_SYSKEYUP, key, (LPARAM)(1u | (1u << 29) | (1u << 30) | (1u << 31)));
      posted = 1;
      return 1; /* run again once the loop has read the key */
    }
    if (shell_active != want && GetTickCount() - drive_step_start < 5000) return 1;
    posted = 0;
    drive_step_finish(shell_active == want, shell_active ? "reading screen" : "bookshelf");
    return 0;
  }
  if (!strcmp(action, "shell_hover")) {
    /* The real hover path is WM_MOUSEMOVE + TrackMouseEvent; the screenshot
       needs the state to survive the cursor being elsewhere, so it is pinned. */
    HWND button = shell_button_named(drive_args[1]), previous = shell_hover;
    if (button) SendMessageW(button, WM_MOUSEMOVE, 0, MAKELPARAM(SHELL_BUTTON_BOX / 2, SHELL_BUTTON_BOX / 2));
    shell_hover = button;
    shell_hover_pinned = button != NULL;
    if (previous) InvalidateRect(previous, NULL, FALSE);
    if (button) { InvalidateRect(button, NULL, FALSE); UpdateWindow(button); }
    drive_step_finish(!strcmp(drive_args[1], "none") || button != NULL, button ? "hover pinned" : "hover cleared");
    return 0;
  }
  if (!strcmp(action, "activate")) {
    /* Test setup: focus states only exist in the foreground window. At most
       one SetForegroundWindow per run, announced first and never retried; if
       the foreground is refused the step fails and says so. The 500 ms below
       only waits for that one request to take effect. */
    static int requests, waiting;
    if (!waiting) {
      if (requests) { drive_step_finish(0, "activation already used in this run; not retried"); return 0; }
      requests = 1;
      drive_log("NOTE", "activate", 1, "activating window for focus checks");
      SetForegroundWindow(g.window);
      waiting = 1;
    }
    if (GetForegroundWindow() != g.window && GetTickCount() - drive_step_start < 500) return 1;
    waiting = 0;
    drive_step_finish(GetForegroundWindow() == g.window,
                      GetForegroundWindow() == g.window ? "foreground" : "无法获得前台 (foreground refused; not retried)");
    return 0;
  }
  if (!strcmp(action, "key_tab")) {
    /* A real Tab keystroke through the input queue (the window must be in the
       foreground); waits until keyboard focus has moved. */
    static HWND before;
    static int sent;
    if (!sent) {
      INPUT key[2];
      memset(key, 0, sizeof(key));
      key[0].type = key[1].type = INPUT_KEYBOARD;
      key[0].ki.wVk = key[1].ki.wVk = VK_TAB;
      key[1].ki.dwFlags = KEYEVENTF_KEYUP;
      before = GetFocus();
      sent = 1;
      if (GetForegroundWindow() != g.window || SendInput(2, key, sizeof(INPUT)) != 2) {
        sent = 0;
        drive_step_finish(0, "not foreground or SendInput failed");
        return 0;
      }
      return 1;
    }
    if (GetFocus() == before && GetTickCount() - drive_step_start < 2000) return 1;
    sent = 0;
    drive_step_finish(GetFocus() != before, GetFocus() != before ? "focus moved" : "focus did not move");
    return 0;
  }
  if (!strcmp(action, "ui_cues")) {
    /* Test setup: the focus-cue state a mouse-started session has (hide) or a
       keyboard-started one has (show); the real switch is IsDialogMessage. */
    SendMessageW(g.window, WM_CHANGEUISTATE, MAKEWPARAM(!strcmp(drive_args[1], "show") ? UIS_CLEAR : UIS_SET,
                 UISF_HIDEFOCUS), 0);
    drive_step_finish(1, "focus cues set");
    return 0;
  }
  if (!strcmp(action, "shell_press")) {
    HWND button = shell_button_named(drive_args[1]);
    if (button) { SendMessageW(button, BM_SETSTATE, atoi(drive_args[2]) != 0, 0); UpdateWindow(button); }
    drive_step_finish(button != NULL, "button state set");
    return 0;
  }
  if (!strcmp(action, "shell_enable")) {
    HWND button = shell_button_named(drive_args[1]);
    if (button) { EnableWindow(button, atoi(drive_args[2]) != 0); UpdateWindow(button); }
    drive_step_finish(button != NULL, "button enabled state set");
    return 0;
  }
#endif
  if (!strcmp(action, "tab")) {
    int count = drive_args[1][0] ? atoi(drive_args[1]) : 1;
    int i;
    HWND focus = GetFocus();
    if (!focus) focus = g.window;
    for (i = 0; i < count; i++) {
      PostMessageW(focus, WM_KEYDOWN, VK_TAB, 0);
      PostMessageW(focus, WM_KEYUP, VK_TAB, 0);
    }
    drive_step_finish(1, "tab posted");
    return 0;
  }
  if (!strcmp(action, "cancel")) {
    job_cancel_button();
    drive_step_finish(1, g.job ? "cancel requested" : "no task to cancel");
    return 0;
  }
  if (!strcmp(action, "open")) {
    if (!shelf_click(drive_args[1])) { drive_step_finish(0, "book not found"); return 0; }
    open_selected_book();
    drive_expect_idle = 1;
    return 1;
  }
  if (!strcmp(action, "import_async")) {
    wchar_t *wide = host_wide(drive_args[1], strlen(drive_args[1]));
    if (!wide) { drive_step_finish(0, "invalid path"); return 0; }
    import_path(wide, 0);
    free(wide);
    drive_step_finish(g.job != NULL, "import dispatched asynchronously");
    return 0;
  }
  if (g.job || g.pending) {
    if (GetTickCount() - drive_step_start > 120000) {
      drive_step_finish(0, "timeout waiting for idle");
      return 0;
    }
    return 1;
  }
  if (!strcmp(action, "import")) {
    wchar_t *wide = host_wide(drive_args[1], strlen(drive_args[1]));
    if (!wide) { drive_step_finish(0, "invalid path"); return 0; }
    import_path(wide, 0);
    free(wide);
    launches = 1;
  } else if (!strcmp(action, "shelf")) {
    if (!shelf_click(drive_args[1])) { drive_step_finish(0, "book not found"); return 0; }
    drive_step_finish(1, "book selected");
    return 0;
  } else if (!strcmp(action, "delete_book")) {
    wchar_t *needle;
    int gone;
    if (!shelf_click(drive_args[1])) { drive_step_finish(0, "book not found"); return 0; }
    delete_selected_book();
#ifdef EXR_READER_PRODUCT_CATALOG
    if(g.job || g.pending) { drive_expect_idle=1;return 1; }
#endif
    needle = host_wide(drive_args[1], strlen(drive_args[1]));
    gone = needle && shelf_index_for_title(needle) < 0;
    free(needle);
    drive_step_finish(gone, gone ? "book removed" : "book still present");
    return 0;
  } else if (!strcmp(action, "next")) {
    page_step(1);
    launches = 1;
  } else if (!strcmp(action, "prev")) {
    page_step(-1);
    launches = 1;
  } else if (!strcmp(action, "chapter_end")) {
    page_step(1000000); launches = 1;
  } else if (!strcmp(action, "chapter_home")) {
    page_step(-1000000); launches = 1;
  } else if (!strcmp(action, "font_inc")) {
    change_font(HOST_FONT_STEP);
    launches = 1;
  } else if (!strcmp(action, "font_dec")) {
    change_font(-HOST_FONT_STEP);
    launches = 1;
  } else if (!strcmp(action, "zoom_inc")) {
    change_zoom(HOST_ZOOM_STEP);
    launches = 1;
  } else if (!strcmp(action, "zoom_dec")) {
    change_zoom(-HOST_ZOOM_STEP);
    launches = 1;
  } else if (!strcmp(action, "select_all")) {
    select_all_page();
    drive_step_finish(1, "select-all dispatched");
    return 0;
  } else if (!strcmp(action, "select_range")) {
    size_t start = (size_t)strtoull(drive_args[1], NULL, 10);
    size_t end = (size_t)strtoull(drive_args[2], NULL, 10);
    if (!g.frame.valid) { drive_step_finish(0, "no page"); return 0; }
    memset(&g.selection, 0, sizeof(g.selection));
    g.selection.active = start < end;
    g.selection.start = start;
    g.selection.end = end;
    g.selection.page = g.frame.page;
    g.selection.fixed = g.frame.fixed;
    page_dirty(g.page,0);
    drive_step_finish(g.selection.active, "selection applied");
    return 0;
  } else if (!strcmp(action, "drag")) {
    int x1 = atoi(drive_args[1]), y1 = atoi(drive_args[2]);
    int x2 = atoi(drive_args[3]), y2 = atoi(drive_args[4]);
    SendMessageW(g.page, WM_LBUTTONDOWN, MK_LBUTTON, MAKELPARAM(x1, y1));
    SendMessageW(g.page, WM_MOUSEMOVE, MK_LBUTTON, MAKELPARAM((x1 + x2) / 2, (y1 + y2) / 2));
    SendMessageW(g.page, WM_MOUSEMOVE, MK_LBUTTON, MAKELPARAM(x2, y2));
    SendMessageW(g.page, WM_LBUTTONUP, 0, MAKELPARAM(x2, y2));
    if (g.frame.bounded) { drive_expect_idle = 1; return 1; }
    drive_step_finish(g.selection.active, "mouse selection dispatched");
    return 0;
  } else if (!strcmp(action, "note")) {
    wchar_t *wide = host_wide(drive_args[1], strlen(drive_args[1]));
    if (!wide) { drive_step_finish(0, "invalid text"); return 0; }
    SetWindowTextW(g.note_edit, wide);
    free(wide);
    drive_step_finish(1, "comment set");
    return 0;
  } else if (!strcmp(action, "add_note")) {
    add_note();
    drive_step_finish(g.status_text[0] != 0, "add dispatched");
    return 0;
  } else if (!strcmp(action, "update_note")) {
    update_note();
    drive_step_finish(1, "update dispatched");
    return 0;
  } else if (!strcmp(action, "delete_note")) {
    delete_note();
    drive_step_finish(1, "delete dispatched");
    return 0;
  } else if (!strcmp(action, "note_select")) {
    int index = atoi(drive_args[1]);
    if (!current_note_count() || (size_t)index >= current_note_count()) { drive_step_finish(0, "note index out of range"); return 0; }
    SendMessageW(g.notes, LB_SETCURSEL, (WPARAM)index, 0);
    SendMessageW(g.window, WM_COMMAND, MAKEWPARAM(IDC_NOTES, LBN_SELCHANGE), (LPARAM)g.notes);
    drive_step_finish(1, "note selected");
    return 0;
  } else if (!strcmp(action, "jump_note")) {
    int index = drive_args[1][0] ? atoi(drive_args[1]) : -1;
    if (index >= 0) {
      if (!current_note_count() || (size_t)index >= current_note_count()) { drive_step_finish(0, "note index out of range"); return 0; }
      SendMessageW(g.notes, LB_SETCURSEL, (WPARAM)index, 0);
    }
    jump_selected_note();
    launches = 1;
  } else if (!strcmp(action, "copy")) {
    copy_quote();
    drive_step_finish(1, "copy dispatched");
    return 0;
  } else if (!strcmp(action, "check")) {
    const char *what = drive_args[1];
    int pass = 0;
    char number[64];
#ifdef EXR_READER_WINDOWS_SHELL
    if (!strcmp(what, "shell")) {
      RECT client, page, frame;
      POINT origin = {0, 0};
      int visible = shell_visible_children();
      GetClientRect(g.window, &client);
      GetWindowRect(g.page, &page); MapWindowPoints(NULL, g.window, (POINT *)&page, 2);
      ClientToScreen(g.window, &origin);
      GetWindowRect(g.window, &frame);
      origin.x -= frame.left; origin.y -= frame.top;
      if (atoi(drive_args[2]))
        pass = shell_active && visible == 3 && page.top == SHELL_TOPBAR_H && page.left == 0 &&
               page.right == client.right && page.bottom == client.bottom &&
               !(GetWindowLongPtrW(g.page, GWL_EXSTYLE) & WS_EX_CLIENTEDGE) &&
               IsWindowVisible(shell_toc) && IsWindowVisible(shell_settings);
      else pass = !shell_active && !IsWindowVisible(shell_toc) && !IsWindowVisible(shell_settings);
      snprintf(number, sizeof(number), "%d", shell_active); detail_add(detail, sizeof(detail), "active", number);
      snprintf(number, sizeof(number), "%d", visible); detail_add(detail, sizeof(detail), "visible_children", number);
      snprintf(number, sizeof(number), "%ld", (long)page.top); detail_add(detail, sizeof(detail), "page_top", number);
      snprintf(number, sizeof(number), "%d", (GetWindowLongPtrW(g.page, GWL_EXSTYLE) & WS_EX_CLIENTEDGE) != 0);
      detail_add(detail, sizeof(detail), "page_edge", number);
      snprintf(number, sizeof(number), "%ld,%ld", (long)origin.x, (long)origin.y);
      detail_add(detail, sizeof(detail), "client_origin", number);
      snprintf(number, sizeof(number), "%ldx%ld", (long)client.right, (long)client.bottom);
      detail_add(detail, sizeof(detail), "client", number);
    } else if (!strcmp(what, "retired_controls")) {
      pass=1;
      for(int retired=101;retired<=117;retired++) if(GetDlgItem(g.window,retired))pass=0;
      detail_add(detail,sizeof(detail),"retired_controls",pass ? "absent":"present");
    } else if (!strcmp(what, "shell_fonts")) {
      unsigned latin = 0, cjk = 0;
      char *title = host_utf8(shell_d2d_family(host_shell, SHELL_TEXT_TITLE));
      char *icon = host_utf8(shell_d2d_family(host_shell, SHELL_TEXT_ICON));
      shell_d2d_title_faces(host_shell, &latin, &cjk);
      pass = latin == 0 && cjk == 0;
      detail_add(detail, sizeof(detail), "title_family", title ? title : "");
      detail_add(detail, sizeof(detail), "icon_family", icon ? icon : "");
      snprintf(number, sizeof(number), "%u", latin); detail_add(detail, sizeof(detail), "latin_simulations", number);
      snprintf(number, sizeof(number), "%u", cjk); detail_add(detail, sizeof(detail), "cjk_simulations", number);
      free(title); free(icon);
    } else if (!strcmp(what, "focus")) {
      HWND want = !strcmp(drive_args[2], "page") ? g.page : shell_button_named(drive_args[2]);
      HWND focus = GetFocus();
      pass = want && focus == want;
      char focus_class[64] = "";
      if (focus) GetClassNameA(focus, focus_class, (int)sizeof(focus_class));
      detail_add(detail, sizeof(detail), "focus", focus == g.page ? "page" : focus == shell_toc ? "toc" :
                 focus == shell_settings ? "settings" : focus ? "other" : "none");
      detail_add(detail, sizeof(detail), "focus_class", focus_class);
      snprintf(number, sizeof(number), "%d", GetForegroundWindow() == g.window);
      detail_add(detail, sizeof(detail), "foreground", number);
      snprintf(number, sizeof(number), "%ld", (long)(focus ? SendMessageW(focus, WM_QUERYUISTATE, 0, 0) : -1));
      detail_add(detail, sizeof(detail), "uistate", number);
      {
        HWND next = focus ? GetNextDlgTabItem(g.window, focus, FALSE) : NULL;
        snprintf(number, sizeof(number), "%d", next ? GetDlgCtrlID(next) : -1);
        detail_add(detail, sizeof(detail), "next_tab_id", number);
      }
    } else
#endif
    if (!strcmp(what, "part")) {
      pass = g.frame.valid && g.frame.part == (size_t)atoi(drive_args[2]);
      snprintf(number, sizeof(number), "%llu", (unsigned long long)g.frame.part); detail_add(detail, sizeof(detail), "part", number);
    } else if (!strcmp(what, "bounded")) {
      pass = g.session.active && g.session.bounded == atoi(drive_args[2]);
      snprintf(number, sizeof(number), "%d", g.session.bounded); detail_add(detail, sizeof(detail), "bounded", number);
    } else if (!strcmp(what, "page")) {
      pass = g.frame.valid && g.frame.page + 1 == (size_t)atoi(drive_args[2]);
      snprintf(number, sizeof(number), "%llu", (unsigned long long)(g.frame.valid ? g.frame.page + 1 : 0));
      detail_add(detail, sizeof(detail), "page", number);
      snprintf(number, sizeof(number), "%llu", (unsigned long long)(g.frame.valid ? g.frame.page_count : 0));
      detail_add(detail, sizeof(detail), "page_count", number);
      detail_add(detail, sizeof(detail), "kind", g.frame.valid ? (g.frame.fixed ? "fixed" : "reflow") : "none");
    } else if (!strcmp(what, "status")) {
      pass = check_status_contains(drive_args[3]);
      detail_add(detail, sizeof(detail), "needle", drive_args[3]);
    } else if (!strcmp(what, "shelf")) {
      if (!strcmp(drive_args[2], "count")) {
        pass = g.shelf_count == (size_t)atoi(drive_args[3]);
        snprintf(number, sizeof(number), "%llu", (unsigned long long)g.shelf_count);
        detail_add(detail, sizeof(detail), "count", number);
      } else {
        wchar_t *needle = host_wide(drive_args[3], strlen(drive_args[3]));
        pass = needle && shelf_index_for_title(needle) >= 0;
        free(needle);
        detail_add(detail, sizeof(detail), "needle", drive_args[3]);
      }
    } else if (!strcmp(what, "notes")) {
      pass = current_note_count() == (size_t)atoi(drive_args[2]);
      snprintf(number, sizeof(number), "%llu", (unsigned long long)current_note_count());
      detail_add(detail, sizeof(detail), "count", number);
    } else if (!strcmp(what, "book")) {
      char *title = g.has_current && g.current.title ? host_strdup(g.current.title) : host_strdup("");
      pass = title && strstr(title, drive_args[2]) != NULL;
      detail_add(detail, sizeof(detail), "title", title);
      free(title);
    } else if (!strcmp(what, "font")) {
      pass = g.font_percent == atoi(drive_args[2]);
      snprintf(number, sizeof(number), "%d", g.font_percent);
      detail_add(detail, sizeof(detail), "font", number);
    } else if (!strcmp(what, "zoom")) {
      pass = g.zoom_percent == atoi(drive_args[2]);
      snprintf(number, sizeof(number), "%d", g.zoom_percent);
      detail_add(detail, sizeof(detail), "zoom", number);
    } else if (!strcmp(what, "selection")) {
      if (!strcmp(drive_args[2], "nonempty")) pass = check_selection(1, NULL);
      else pass = check_selection(0, drive_args[3]);
      detail_add(detail, sizeof(detail), "active", g.selection.active ? "1" : "0");
    } else if (!strcmp(what, "clipboard")) {
      pass = clipboard_contains(drive_args[3]);
      detail_add(detail, sizeof(detail), "needle", drive_args[3]);
    } else if (!strcmp(what, "focus")) {
      HWND focus = GetFocus();
      pass = focus && GetDlgCtrlID(focus) == atoi(drive_args[2]);
      snprintf(number, sizeof(number), "%d", focus ? GetDlgCtrlID(focus) : -1);
      detail_add(detail, sizeof(detail), "focus", number);
    } else if (!strcmp(what, "page_text")) {
      char text[512];
      page_text_snapshot(text, sizeof(text));
      pass = strstr(text, drive_args[2]) != NULL;
      detail_add(detail, sizeof(detail), "text", text);
    } else if (!strcmp(what, "no_book")) {
      pass = !g.has_current;
    } else {
      drive_step_finish(0, "unknown check");
      return 0;
    }
    {
      char *current = host_utf8(g.status_text);
      detail_add(detail, sizeof(detail), "window_status", current ? current : "");
      free(current);
    }
    drive_step_finish(pass, detail);
    return 0;
  }
  if (launches) {
    drive_expect_idle = 1;
    return 1;
  }
  drive_step_finish(0, "unknown action");
  return 0;
}

static int drive_read_step(void) {
  char line[HOST_PATH * 2];
  char *cursor;
  int argc = 0;
  for (;;) {
    if (!fgets(line, sizeof(line), drive_file)) return 0;
    {
      size_t length = strlen(line);
      while (length && (line[length - 1] == '\n' || line[length - 1] == '\r')) line[--length] = 0;
    }
    if (!line[0] || line[0] == '#') continue;
    break;
  }
  drive_argc = 0;
  cursor = line;
  while (argc < 8) {
    char *bar = strchr(cursor, '|');
    size_t length = bar ? (size_t)(bar - cursor) : strlen(cursor);
    if (length >= HOST_PATH) length = HOST_PATH - 1;
    memcpy(drive_args[argc], cursor, length);
    drive_args[argc][length] = 0;
    argc++;
    if (!bar) break;
    cursor = bar + 1;
  }
  drive_argc = argc;
  memset(drive_action, 0, sizeof(drive_action));
  memcpy(drive_action, drive_args[0], strnlen(drive_args[0], sizeof(drive_action) - 1));
  g.drive_index++;
  drive_step_active = 1;
  drive_step_start = GetTickCount();
  return 1;
}

static void drive_tick(void) {
  int guard = 0;
  if (!g.drive_mode || g.drive_done) return;
  while (guard++ < 16) {
    if (!drive_step_active) {
      if (!drive_read_step()) {
        drive_log("DONE", "eof", g.drive_failures == 0, "script finished");
        g.drive_done = 1;
        PostMessageW(g.window, WM_CLOSE, 0, 0);
        return;
      }
      if (drive_execute()) return;
      continue;
    }
    if (drive_expect_idle) {
      if (
#ifdef EXR_READER_WINDOWS_SHELL
          shell_layout_waiting || shell_animating || shell_search_pending || shell_search_thread || shell_search_jump_pending ||
#endif
          g.job || g.pending || host_probe_burst_left || wheel_delta<=-WHEEL_DELTA || wheel_delta>=WHEEL_DELTA) {
        if (GetTickCount() - drive_step_start > 120000) {
          drive_step_finish(0, "timeout waiting for task");
          continue;
        }
        return;
      }
      {
        char detail[1024];
        char number[64];
        char *status = host_utf8(g.status_text);
        memset(detail, 0, sizeof(detail));
        snprintf(number, sizeof(number), "%llu", (unsigned long long)(g.frame.valid ? g.frame.page + 1 : 0));
        detail_add(detail, sizeof(detail), "page", number);
        detail_add(detail, sizeof(detail), "status", status ? status : "");
        free(status);
        if(!strcmp(drive_action,"delete_book")) {
          wchar_t *needle=host_wide(drive_args[1],strlen(drive_args[1]));
          int gone=needle && shelf_index_for_title(needle)<0;free(needle);
          detail_add(detail,sizeof(detail),"book_removed",gone ? "1":"0");
          drive_step_finish(gone,detail);
        } else drive_step_finish(1, detail);
      }
      continue;
    }
    if (GetTickCount() - drive_step_start > 120000) {
      drive_step_finish(0, "timeout before action could run");
      continue;
    }
    if (drive_execute()) return;
    continue;
  }
}

static void drive_start(void) {
  wchar_t log_path[HOST_PATH];
  if (!g.script_path[0] || !g.evidence_dir[0]) return;
  ensure_directory(g.evidence_dir);
  drive_file = _wfopen(g.script_path, L"rb");
  if (!drive_file) {
    set_status(L"无法读取验收脚本。");
    return;
  }
  path_join(log_path, HOST_PATH, g.evidence_dir, L"drive.log");
  g.drive_log = _wfopen(log_path, L"wb");
  if (!g.drive_log) {
    fclose(drive_file);
    drive_file = NULL;
    set_status(L"无法写入验收日志。");
    return;
  }
  fprintf(g.drive_log, "HOST\tphase=%d\tengine=%s\tpid=%lu\n", g.phase, exr_version(),
          (unsigned long)GetCurrentProcessId());
  fflush(g.drive_log);
  g.drive_mode = 1;
  g.drive_index = 0;
  g.drive_failures = 0;
  g.drive_done = 0;
  SetTimer(g.window, 1, 40, NULL);
}

