/* SPDX-License-Identifier: MIT */
/* Logical selection belongs to content, never to a raster page. UI thread only. */
enum { SHELL_SELECT_TIMER = 0x5345 };
static exr_text_position select_origin, select_focus;
static exr_text_range select_range;
static exr_content_anchor select_anchor;
static int64_t select_book;
static int select_clicks;
static int select_x, select_y, select_last_x, select_last_y;
static DWORD select_last_time;
static exr_publication *select_single;

static int select_before(exr_text_position a, exr_text_position b) {
  return a.part < b.part || (a.part == b.part && a.offset < b.offset);
}
static void shell_selection_reset(void) {
  dict_hide();
  select_valid = select_drag = select_turn = 0;
  exr_content_anchor_free(&select_anchor);
  exr_publication_free(select_single); select_single = NULL;
  if (g.page) KillTimer(g.page, SHELL_SELECT_TIMER);
  if (g.page && GetCapture() == g.page) ReleaseCapture();
}
static exr_status select_load_single(void *context, size_t part, exr_document **out, exr_error *error) {
  (void)context;
  if (part) return EXR_ARGUMENT;
  EnterCriticalSection(&g.library_lock);
  exr_status status = exr_library_document(g.library, g.session.book_id, out, error);
  LeaveCriticalSection(&g.library_lock);
  return status;
}
static exr_publication *select_publication(void) {
  if (g.session.publication) return g.session.publication;
  if (!select_single && g.session.document) {
    exr_part part = {"content", "content.txt", "text/plain", 1};
    exr_publication_input input = {0};
    input.parts = &part; input.part_count = 1; input.load = select_load_single;
    exr_publication_create(&input, &select_single, NULL);
  }
  return select_single;
}
static void select_sync(void) {
  memset(&g.selection, 0, sizeof(g.selection));
  if (!select_valid || select_book != g.frame.book_id ||
      g.frame.part < select_range.start.part || g.frame.part > select_range.end.part) return;
  g.selection.start = g.frame.part == select_range.start.part ? select_range.start.offset : 0;
  g.selection.end = g.frame.part == select_range.end.part ? select_range.end.offset : SIZE_MAX;
  g.selection.active = select_before(select_range.start, select_range.end);
  g.selection.page = g.frame.page;
}
static int select_set(exr_text_position a, exr_text_position b, int unit, int finalize) {
  exr_text_range range = {a, b};
  exr_publication *publication = select_publication();
  exr_error error = {0};
  if (!publication) return 0;
  if (select_before(b, a)) { range.start = b; range.end = a; }
  if (unit >= 0 && exr_range_expand(publication, &range, (exr_range_unit)unit, NULL, &range, &error) != EXR_OK) return 0;
  if (finalize) {
    exr_content_anchor anchor = {0};
    if (exr_anchor_from_range(publication, &range, NULL, &anchor, &error) != EXR_OK) return 0;
    exr_content_anchor_free(&select_anchor); select_anchor = anchor;
    if (unit >= 0) {
      int reverse = select_before(b, a);
      select_origin = reverse ? range.end : range.start;
      select_focus = reverse ? range.start : range.end;
    }
  }
  annot_selected=-1;
  select_range = range; select_book = g.frame.book_id; select_valid = 1;
  select_sync(); page_dirty(g.page, 0); host_a11y_page_changed(1);
  return 1;
}
static int select_hit(int x, int y, exr_text_position *position) {
  const exr_layout *layout = g.frame.hit_layout;
  if (!compute_view()) return 0;
  if (!layout && exr_pager_get(g.session.pager, g.frame.page, &layout, NULL) != EXR_OK) return 0;
  if (!g.frame.hit_layout && g.frame.shell_anchored && g.session.publication) {
    exr_document *document = NULL;
    if (exr_publication_load(g.session.publication, g.frame.part, &document, NULL) != EXR_OK) return 0;
    exr_positioned_page page = {0}; exr_positioned_input input = {0};
    exr_layout_config config = exr_layout_config_defaults();
    page.width = config.page.width = (float)g.frame.bitmap.width;
    page.height = config.page.height = (float)g.frame.bitmap.height; config.page.margin = 0;
    page.content = (exr_page){g.frame.range_start, g.frame.range_end, 0, g.frame.shell_line_count, 0, 0};
    input.struct_size = sizeof(input); input.pages = &page; input.page_count = 1;
    input.glyphs = g.frame.glyphs; input.glyph_count = g.frame.glyph_count;
    input.lines = g.frame.shell_lines; input.line_count = g.frame.shell_line_count;
    exr_status status = exr_layout_create_positioned(document, exr_layout_font(layout), &input, &config, &g.frame.hit_layout, NULL);
    exr_document_free(document); if (status != EXR_OK) return 0;
    layout = g.frame.hit_layout;
  }
  return exr_hit_test(layout, g.frame.part, 0, (float)((x-g.view.dx)/g.view.scale),
    (float)((y-g.view.dy)/g.view.scale), position, NULL) == EXR_OK && position->offset != SIZE_MAX;
}
static size_t shell_selection_bytes(char **out) {
  char *result = NULL; size_t used = 0;
  exr_publication *publication = select_publication();
  *out = NULL;
  if (!publication || !select_valid || select_book != g.frame.book_id) return 0;
  for (size_t part = select_range.start.part; part <= select_range.end.part; part++) {
    exr_document *document = NULL; size_t size = 0;
    if (exr_publication_load(publication, part, &document, NULL) != EXR_OK) { free(result); return 0; }
    const char *text = exr_document_text(document, &size);
    size_t start = part == select_range.start.part ? select_range.start.offset : 0;
    size_t end = part == select_range.end.part ? select_range.end.offset : size;
    if (!text || start > end || end > size || end-start > SIZE_MAX-used-1) {
      exr_document_free(document); free(result); return 0;
    }
    char *next = realloc(result, used+end-start+1);
    if (!next) { exr_document_free(document); free(result); return 0; }
    result = next; memcpy(result+used, text+start, end-start); used += end-start;
    exr_document_free(document);
  }
  if (result) result[used] = 0;
  *out = result; return used;
}
static void select_all_part(void) {
  exr_document *document = NULL; size_t size = 0;
  exr_publication *publication = select_publication();
  if (!publication || exr_publication_load(publication, g.frame.part, &document, NULL) != EXR_OK) return;
  exr_document_text(document, &size); exr_document_free(document);
  select_origin = (exr_text_position){g.frame.part, 0};
  select_focus = (exr_text_position){g.frame.part, size};
  select_set(select_origin, select_focus, -1, 1);
}

/* Clip each selected cluster to its line band. In vertical text advance is y.
   Union first: overlapping glyphs/ligatures must receive alpha exactly once. */
static HRGN select_region_for(size_t start,size_t end) {
  HRGN region = CreateRectRgn(0, 0, 0, 0);
  if (start>=end) return region;
  for (size_t i = 0; i < g.frame.shell_line_count; i++) {
    const exr_line *line = &g.frame.shell_lines[i];
    for (size_t j = line->glyph_start; j < line->glyph_start+line->glyph_count; j++) {
      const exr_glyph *glyph = &g.frame.glyphs[j];
      if (glyph->flags & EXR_GLYPH_HIDDEN || glyph->cluster_end <= start ||
          glyph->cluster_start >= end) continue;
      float x = glyph->x, y = line->y, w = glyph->advance, h = line->height;
      if (glyph->flags & EXR_GLYPH_VERTICAL) {
        x = line->x; y = glyph->baseline; w = line->width; h = glyph->advance;
      }
      if (w < 0) { x += w; w = -w; }
      if (h < 0) { y += h; h = -h; }
      HRGN box = CreateRectRgn((int)floorf(x), (int)floorf(y), (int)ceilf(x+w), (int)ceilf(y+h));
      CombineRgn(region, region, box, RGN_OR); DeleteObject(box);
    }
  }
  return region;
}
static HRGN select_region(void) { return select_region_for(g.selection.active ? g.selection.start : 0,g.selection.active ? g.selection.end : 0); }
static void shell_selection_paint(HDC dc) {
  if ((!tts_state && !annot_count && (!select_valid || select_book != g.frame.book_id || !g.selection.active)) || !g.frame.display_bitmap) return;
  HRGN region = select_region(); RECT bounds;
  GetRgnBox(region, &bounds);
  DIBSECTION section = {0};
  GetObject(g.frame.display_bitmap, sizeof(section), &section);
  /* A temporary DIB keeps the cached SDK raster and its themed display intact.
     Recompose ink over accent-soft: opaque glyph pixels keep their original ink. */
  BITMAPINFO info = {0}; void *pixels = NULL;
  int width = g.frame.display_width, height = g.frame.display_height;
  info.bmiHeader.biSize = sizeof(BITMAPINFOHEADER); info.bmiHeader.biWidth = width;
  info.bmiHeader.biHeight = -height; info.bmiHeader.biPlanes = 1; info.bmiHeader.biBitCount = 32;
  HBITMAP bitmap = CreateDIBSection(dc, &info, DIB_RGB_COLORS, &pixels, NULL, 0);
  if (!bitmap || !section.dsBm.bmBits) { if (bitmap) DeleteObject(bitmap); DeleteObject(region); return; }
  memcpy(pixels, section.dsBm.bmBits, (size_t)width*height*4);
  annot_pixels(pixels,width,height);
  tts_pixels(pixels,width,height);
  /* High contrast selects with the system highlight pair, fully opaque. */
  uint32_t background = shell_contrast ? shell_colors->accent_hover :
    shell_blend(shell_colors->layer_page, shell_is_dark() ? 0x7c88ff : 0x4553e0, shell_is_dark() ? .16f : .10f);
  uint32_t ink = shell_contrast ? shell_colors->on_accent : shell_colors->text;
  for (int y = max(0, bounds.top); y < min(height, bounds.bottom); y++) {
    for (int x = max(0, bounds.left); x < min(width, bounds.right); x++) if (PtInRegion(region, x, y)) {
      size_t index = (size_t)y*width+x; uint32_t q = g.frame.dib[index];
      unsigned r = (q>>16)&255, green = (q>>8)&255, b = q&255;
      if (!g.frame.display_shell_paper && r == green && green == b)
        ((uint32_t *)pixels)[index] = shell_blend(ink, background, r/255.f);
      else {
        /* Book-painted paper (e.g. Grass Pillow's cream) is already opaque.
           Its lightness is the remaining paper coverage; black ink stays ink. */
        float coverage = (float)max(r, max(green, b))/255.f;
        ((uint32_t *)pixels)[index] = shell_blend(q, shell_contrast ? background : shell_is_dark() ? 0x7c88ff : 0x4553e0,
          coverage*(shell_contrast ? 1.f : shell_is_dark() ? .16f : .10f));
      }
    }
  }
  HDC source = CreateCompatibleDC(dc); HGDIOBJ old = SelectObject(source, bitmap);
  BitBlt(dc, g.view.dx, g.view.dy, width, height, source, 0, 0, SRCCOPY);
  SelectObject(source, old); DeleteDC(source); DeleteObject(bitmap); DeleteObject(region);
  annot_marks(dc);
}
static void select_update(int x, int y, int finalize) {
  exr_text_position position;
  if (select_hit(x, y, &position)) {
    select_focus = position;
    select_set(select_origin, select_focus, select_clicks == 3 ? EXR_RANGE_PARAGRAPH : EXR_RANGE_WORD, finalize);
  } else if (finalize && select_valid) select_set(select_range.start, select_range.end, -1, 1);
}
static void select_move(UINT key) {
  exr_publication *publication = select_publication();
  exr_text_range unit; exr_document *document = NULL; size_t size = 0;
  if (!publication) return;
  if (!select_valid) select_origin = select_focus = (exr_text_position){g.frame.part, g.frame.range_start};
  if (exr_publication_load(publication, select_focus.part, &document, NULL) != EXR_OK) return;
  const char *text = exr_document_text(document, &size);
  int vertical = g.frame.writing_mode != EXR_WRITING_HORIZONTAL_TB;
  int forward = vertical ? (key == VK_DOWN || (key == VK_LEFT && g.frame.writing_mode == EXR_WRITING_VERTICAL_RL) ||
    (key == VK_RIGHT && g.frame.writing_mode == EXR_WRITING_VERTICAL_LR)) : key == VK_RIGHT || key == VK_DOWN;
  size_t at = select_focus.offset;
  int along = vertical ? key == VK_UP || key == VK_DOWN : key == VK_LEFT || key == VK_RIGHT;
  if (!along) {
    /* Adjacent physical row/column, retaining the inline caret coordinate. */
    for (size_t i = 0; i < g.frame.shell_line_count; i++) {
      const exr_line *line = &g.frame.shell_lines[i];
      if (at < line->start || (at >= line->end && at != g.frame.range_end)) continue;
      size_t next = forward ? i+1 : i ? i-1 : SIZE_MAX;
      if (next < g.frame.shell_line_count) {
        const exr_line *target = &g.frame.shell_lines[next];
        float coordinate = vertical ? line->y : line->x;
        for (size_t j = line->glyph_start; j < line->glyph_start+line->glyph_count; j++) {
          const exr_glyph *gph = &g.frame.glyphs[j];
          coordinate = vertical ? gph->baseline : gph->x;
          if (gph->cluster_end > at) break;
          coordinate += gph->advance;
        }
        float distance = INFINITY;
        for (size_t j = target->glyph_start; j < target->glyph_start+target->glyph_count; j++) {
          const exr_glyph *gph = &g.frame.glyphs[j];
          float delta = fabsf((vertical ? gph->baseline : gph->x)-coordinate);
          if (delta < distance) { distance = delta; at = gph->cluster_start; }
        }
      } else at = forward ? g.frame.range_end : g.frame.range_start;
      break;
    }
  } else if (forward && at < size) {
    unit = (exr_text_range){{select_focus.part, at}, {select_focus.part, at}};
    if (exr_range_expand(publication, &unit, EXR_RANGE_CHAR, NULL, &unit, NULL) == EXR_OK) at = unit.end.offset;
  } else if (!forward && at) {
    at--; while (at && ((unsigned char)text[at]&0xc0) == 0x80) at--;
    unit = (exr_text_range){{select_focus.part, at}, {select_focus.part, at}};
    if (exr_range_expand(publication, &unit, EXR_RANGE_CHAR, NULL, &unit, NULL) == EXR_OK) at = unit.start.offset;
  }
  exr_document_free(document);
  select_focus.offset = at; select_set(select_origin, select_focus, -1, 1);
  if (at < g.frame.range_start || at >= g.frame.range_end) page_step(forward ? 1 : -1);
}
static HMENU select_context_menu(void) {
  HMENU menu = CreatePopupMenu();
  int active = select_valid && select_before(select_range.start, select_range.end);
  int annot_active=active || annot_selected>=0;
  AppendMenuW(menu, MF_STRING | (active ? 0 : MF_GRAYED), 1, L"复制\tCtrl+C");
  AppendMenuW(menu, MF_STRING, 2, L"全选当前章节\tCtrl+A");
  AppendMenuW(menu, MF_STRING | (active ? 0 : MF_GRAYED), 8, L"查词\tCtrl+D");
  AppendMenuW(menu, MF_STRING | (annot_active ? 0 : MF_GRAYED), 3, L"高亮 · 黄\tCtrl+H");
  AppendMenuW(menu, MF_STRING | (annot_active ? 0 : MF_GRAYED), 4, L"高亮 · 绿");
  AppendMenuW(menu, MF_STRING | (annot_active ? 0 : MF_GRAYED), 5, L"高亮 · 蓝");
  AppendMenuW(menu, MF_STRING | (annot_active ? 0 : MF_GRAYED), 6, L"笔记…\tCtrl+N");
  AppendMenuW(menu, MF_STRING | (annot_selected>=0 ? 0:MF_GRAYED), 7, L"删除选中的标注\tDelete");
  tts_menu(menu);
  return menu;
}
static int shell_selection_message(HWND window, UINT message, WPARAM wparam, LPARAM lparam) {
  if (!shell_active || g.frame.fixed || (!g.session.publication && !g.session.document)) return 0;
  if (message==WM_KEYUP && wparam>=VK_LEFT && wparam<=VK_DOWN) {dict_auto_lookup();return 0;}
  if (message == WM_KEYDOWN && wparam == VK_ESCAPE) {
    annot_selected=-1; selection_clear(); return 1;
  }
  if (message == WM_CAPTURECHANGED || message == WM_CANCELMODE) {
    if (select_drag) { select_drag = 0; KillTimer(window, SHELL_SELECT_TIMER); }
    return 0;
  }
  if (message == WM_TIMER && wparam == SHELL_SELECT_TIMER) {
    if (select_drag && !g.job && !g.pending) {
      compute_view();
      int vertical = g.frame.writing_mode != EXR_WRITING_HORIZONTAL_TB;
      int direction = vertical ? (select_x < g.view.dx ? 1 : select_x > g.view.dx+g.view.bw ? -1 : 0) :
        (select_y < g.view.dy ? -1 : select_y > g.view.dy+g.view.bh ? 1 : 0);
      if (vertical && g.frame.writing_mode == EXR_WRITING_VERTICAL_LR) direction = -direction;
      if (direction) { select_turn = direction; page_step(direction); }
    }
    return 1;
  }
  if ((g.job && g.job->kind != JOB_PREFETCH) || g.pending) {
    if (message == WM_LBUTTONUP && select_drag) {
      select_drag = 0; KillTimer(window, SHELL_SELECT_TIMER); ReleaseCapture();
      select_set(select_range.start, select_range.end, -1, 1);
    }
    return message == WM_LBUTTONDOWN || message == WM_LBUTTONDBLCLK || message == WM_MOUSEMOVE || message == WM_LBUTTONUP;
  }
  if (message == WM_LBUTTONDOWN || message == WM_LBUTTONDBLCLK) {
    if (shell_toc_open) return 0;
    exr_text_position position;
    int x = (short)LOWORD(lparam), y = (short)HIWORD(lparam);
    if (message == WM_LBUTTONDOWN && !shell_drag_begin && shell_footnote_click(x,y)) return 1;
    if (message == WM_LBUTTONDOWN && !shell_drag_begin && annot_click(x,y)) return 1;
    if (!select_hit(x, y, &position)) return 1;
    DWORD now = GetMessageTime();
    int nearby = abs(x-select_last_x) <= GetSystemMetrics(SM_CXDOUBLECLK) && abs(y-select_last_y) <= GetSystemMetrics(SM_CYDOUBLECLK);
    select_clicks = nearby && now-select_last_time <= GetDoubleClickTime() ? select_clicks%3+1 : 1;
    if (message == WM_LBUTTONDBLCLK) select_clicks = 2;
    select_last_time = now; select_last_x = x; select_last_y = y;
    SetFocus(window); select_origin = select_focus = position;
    select_valid = 0; select_drag = 1; select_x = x; select_y = y;
    if(GetCapture()!=window)SetCapture(window);
    SetTimer(window, SHELL_SELECT_TIMER, 350, NULL);
    select_set(position, position, select_clicks == 1 ? -1 : select_clicks == 2 ? EXR_RANGE_WORD : EXR_RANGE_PARAGRAPH, 0);
    return 1;
  }
  if (message == WM_MOUSEMOVE && select_drag) {
    select_x = (short)LOWORD(lparam); select_y = (short)HIWORD(lparam);
    if (abs(select_x-select_last_x)+abs(select_y-select_last_y) > 2) select_update(select_x, select_y, 0);
    return 1;
  }
  if (message == WM_LBUTTONUP && select_drag) {
    int x = (short)LOWORD(lparam), y = (short)HIWORD(lparam);
    if (select_clicks == 1 && abs(x-select_last_x)+abs(y-select_last_y) <= 2 && !g.selection.active)
      select_set(select_origin, select_focus, -1, 1);
    else select_update(x, y, 1);
    select_drag = 0; KillTimer(window, SHELL_SELECT_TIMER); ReleaseCapture(); selection_report(); dict_auto_lookup(); return 1;
  }
  if (message == WM_KEYDOWN) {
    if ((GetKeyState(VK_CONTROL)&0x8000) && wparam == 'D') { dict_lookup(); return 1; }
    if ((GetKeyState(VK_SHIFT)&0x8000) && wparam >= VK_LEFT && wparam <= VK_DOWN) { select_move((UINT)wparam); return 1; }
    if ((GetKeyState(VK_CONTROL)&0x8000) && wparam == 'A') { select_all_part(); return 1; }
    if (wparam==VK_DELETE && annot_command(7)) return 1;
    if ((GetKeyState(VK_CONTROL)&0x8000) && (wparam=='H' || wparam=='N')) { annot_command(wparam=='H' ? 3:6); return 1; }
    if ((GetKeyState(VK_CONTROL)&0x8000) && wparam == 'C') { copy_quote(); return 1; }
  }
  if (message == WM_CONTEXTMENU) {
    POINT point = {(short)LOWORD(lparam), (short)HIWORD(lparam)};
    if (point.x == -1 && point.y == -1) { point = (POINT){g.view.dx+16, g.view.dy+16}; ClientToScreen(window, &point); }
    HMENU menu = select_context_menu();
    UINT command = TrackPopupMenu(menu, TPM_RETURNCMD | TPM_RIGHTBUTTON, point.x, point.y, 0, window, NULL);
    DestroyMenu(menu);
    if (command == 1) copy_quote();
    if (command == 2) select_all_part();
    if (command >= 100) tts_command((int)command);
    if (command == 8) dict_lookup();
    if (command >= 3 && command <= 7) annot_command((int)command);
    return 1;
  }
  return 0;
}
static void shell_selection_landed(void) {
  if (!select_valid) return;
  if (select_book != g.frame.book_id) { shell_selection_reset(); return; }
  select_sync();
  if (select_drag && select_turn) {
    select_focus = (exr_text_position){g.frame.part, select_turn > 0 ? g.frame.range_start : g.frame.range_end};
    select_set(select_origin, select_focus, EXR_RANGE_WORD, 0); select_turn = 0;
  }
}
