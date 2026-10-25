/* SPDX-License-Identifier: MIT */
/* Installed F3 reading preferences: one native Settings entry and its dialog.
 *
 * The dialog only collects input. Every accepted change is one job on the
 * existing worker; the owner window stays disabled until the worker finishes,
 * so a second selection can never interleave with an accepted frame. */

static int prefs_ui_open(void) { return prefs_ui.dialog != NULL; }
static HWND prefs_dialog_handle(void) { return prefs_ui.dialog; }

static void prefs_notice(const wchar_t *text) {
  if (prefs_ui.message) SetWindowTextW(prefs_ui.message, text);
}

static HWND prefs_entry(HWND parent, int id, int x, int y, int width) {
  HWND entry = CreateWindowExW(WS_EX_CLIENTEDGE, L"EDIT", L"",
                               WS_CHILD | WS_VISIBLE | WS_TABSTOP | ES_AUTOHSCROLL,
                               x, y, width, 24, parent, (HMENU)(INT_PTR)id, NULL, NULL);
  SendMessageW(entry, WM_SETFONT, (WPARAM)GetStockObject(DEFAULT_GUI_FONT), TRUE);
  SendMessageW(entry, EM_SETLIMITTEXT, 12, 0);
  return entry;
}

static HWND prefs_combo(HWND parent, int id, int x, int y, int width,
                        const wchar_t *const *items, int count) {
  HWND combo = CreateWindowExW(0, L"COMBOBOX", L"",
                               WS_CHILD | WS_VISIBLE | WS_TABSTOP | WS_VSCROLL | CBS_DROPDOWNLIST,
                               x, y, width, 200, parent, (HMENU)(INT_PTR)id, NULL, NULL);
  int index;
  SendMessageW(combo, WM_SETFONT, (WPARAM)GetStockObject(DEFAULT_GUI_FONT), TRUE);
  for (index = 0; index < count; index++) SendMessageW(combo, CB_ADDSTRING, 0, (LPARAM)items[index]);
  return combo;
}

static void prefs_number(HWND entry, double value) {
  wchar_t text[32];
  swprintf(text, 32, L"%.2f", value);
  SetWindowTextW(entry, text);
}

static void prefs_integer(HWND entry, int value) {
  wchar_t text[32];
  swprintf(text, 32, L"%d", value);
  SetWindowTextW(entry, text);
}

static void prefs_color_text(HWND entry, const uint8_t rgba[4]) {
  wchar_t text[16];
  swprintf(text, 16, L"#%02X%02X%02X%02X", (unsigned)rgba[0], (unsigned)rgba[1],
           (unsigned)rgba[2], (unsigned)rgba[3]);
  SetWindowTextW(entry, text);
}

static void prefs_fill(const reader_preferences *value) {
  if (!prefs_ui.dialog) return;
  prefs_number(prefs_ui.font, (double)value->font_size);
  prefs_number(prefs_ui.line, (double)value->line_spacing);
  prefs_number(prefs_ui.paragraph, (double)value->paragraph_spacing);
  prefs_number(prefs_ui.margin, (double)value->margin);
  SendMessageW(prefs_ui.theme, CB_SETCURSEL, (WPARAM)(value->theme - 1), 0);
  SendMessageW(prefs_ui.direction, CB_SETCURSEL, (WPARAM)(value->page_turn_direction - 1), 0);
  SendMessageW(prefs_ui.input, CB_SETCURSEL, (WPARAM)(value->page_turn_input - 1), 0);
  prefs_integer(prefs_ui.zoom, (int)value->fixed_page_zoom);
  prefs_color_text(prefs_ui.light_fg, value->light_foreground);
  prefs_color_text(prefs_ui.light_bg, value->light_background);
  prefs_color_text(prefs_ui.dark_fg, value->dark_foreground);
  prefs_color_text(prefs_ui.dark_bg, value->dark_background);
}

static int prefs_read_number(HWND entry, float *out) {
  wchar_t text[64], *end = NULL;
  double value;
  int length = GetWindowTextW(entry, text, 64);
  if (length <= 0 || length >= 63) return 0;
  text[length] = 0;
  value = wcstod(text, &end);
  while (end && (*end == L' ' || *end == L'\t')) end++;
  if (!end || *end || !isfinite(value)) return 0;
  *out = (float)value;
  return 1;
}

static int prefs_read_integer(HWND entry, int *out) {
  wchar_t text[64], *end = NULL;
  long value;
  int length = GetWindowTextW(entry, text, 64);
  if (length <= 0 || length >= 63) return 0;
  text[length] = 0;
  value = wcstol(text, &end, 10);
  while (end && (*end == L' ' || *end == L'\t')) end++;
  if (!end || *end) return 0;
  *out = (int)value;
  return 1;
}

static int prefs_hex(wchar_t c) {
  if (c >= L'0' && c <= L'9') return (int)(c - L'0');
  if (c >= L'a' && c <= L'f') return (int)(c - L'a') + 10;
  if (c >= L'A' && c <= L'F') return (int)(c - L'A') + 10;
  return -1;
}

static int prefs_read_color(HWND entry, uint8_t out[4]) {
  wchar_t text[16];
  int length = GetWindowTextW(entry, text, 16), index, high, low;
  if (length != 7 && length != 9) return 0;
  if (text[0] != L'#') return 0;
  for (index = 1; index < length; index++) if (prefs_hex(text[index]) < 0) return 0;
  for (index = 0; index < 3; index++) {
    high = prefs_hex(text[1 + 2 * index]);
    low = prefs_hex(text[2 + 2 * index]);
    out[index] = (uint8_t)(high * 16 + low);
  }
  out[3] = 255;
  if (length == 9) {
    high = prefs_hex(text[7]);
    low = prefs_hex(text[8]);
    out[3] = (uint8_t)(high * 16 + low);
  }
  return 1;
}

static int prefs_read_fields(reader_preferences *value) {
  if (!prefs_read_number(prefs_ui.font, &value->font_size) ||
      !prefs_read_number(prefs_ui.line, &value->line_spacing) ||
      !prefs_read_number(prefs_ui.paragraph, &value->paragraph_spacing) ||
      !prefs_read_number(prefs_ui.margin, &value->margin)) {
    prefs_notice(L"字号、行距、段距和页边距需要填写数字。");
    return 0;
  }
  if (!prefs_read_integer(prefs_ui.zoom, &value->fixed_page_zoom)) {
    prefs_notice(L"固定页缩放需要填写整数百分比。");
    return 0;
  }
  value->theme = (uint32_t)SendMessageW(prefs_ui.theme, CB_GETCURSEL, 0, 0) + 1u;
  value->page_turn_direction = (uint32_t)SendMessageW(prefs_ui.direction, CB_GETCURSEL, 0, 0) + 1u;
  value->page_turn_input = (uint32_t)SendMessageW(prefs_ui.input, CB_GETCURSEL, 0, 0) + 1u;
  if (!prefs_read_color(prefs_ui.light_fg, value->light_foreground) ||
      !prefs_read_color(prefs_ui.light_bg, value->light_background) ||
      !prefs_read_color(prefs_ui.dark_fg, value->dark_foreground) ||
      !prefs_read_color(prefs_ui.dark_bg, value->dark_background)) {
    prefs_notice(L"配色需要填写 #RRGGBB 或 #RRGGBBAA 形式的十六进制颜色。");
    return 0;
  }
  return 1;
}

static void prefs_dialog_layout(void) {
  int index, expanded = prefs_ui.expanded;
  HWND colors[4], captions[4];
  RECT parent;
  if (!prefs_ui.dialog) return;
  for (index = 0; index < 8; index++)
    MoveWindow(prefs_ui.labels[index], 18, 18 + 36 * index, 150, 22, TRUE);
  MoveWindow(prefs_ui.font, 176, 16, 120, 24, TRUE);
  MoveWindow(prefs_ui.line, 176, 52, 120, 24, TRUE);
  MoveWindow(prefs_ui.paragraph, 176, 88, 120, 24, TRUE);
  MoveWindow(prefs_ui.margin, 176, 124, 120, 24, TRUE);
  MoveWindow(prefs_ui.theme, 176, 158, 260, 200, TRUE);
  MoveWindow(prefs_ui.direction, 176, 194, 260, 200, TRUE);
  MoveWindow(prefs_ui.input, 176, 230, 260, 200, TRUE);
  MoveWindow(prefs_ui.zoom, 176, 266, 120, 24, TRUE);
  MoveWindow(prefs_ui.toggle, 18, 298, 170, 26, TRUE);
  colors[0] = prefs_ui.light_fg; colors[1] = prefs_ui.light_bg;
  colors[2] = prefs_ui.dark_fg; colors[3] = prefs_ui.dark_bg;
  captions[0] = prefs_ui.labels[8]; captions[1] = prefs_ui.labels[9];
  captions[2] = prefs_ui.labels[10]; captions[3] = prefs_ui.labels[11];
  for (index = 0; index < 4; index++) {
    ShowWindow(captions[index], expanded ? SW_SHOW : SW_HIDE);
    ShowWindow(colors[index], expanded ? SW_SHOW : SW_HIDE);
    MoveWindow(captions[index], 18, 334 + 32 * index, 150, 20, TRUE);
    MoveWindow(colors[index], 176, 332 + 32 * index, 120, 24, TRUE);
  }
  MoveWindow(prefs_ui.note, 18, expanded ? 466 : 330, 584, 38, TRUE);
  MoveWindow(prefs_ui.apply, 18, expanded ? 508 : 372, 116, 30, TRUE);
  MoveWindow(prefs_ui.defaults, 142, expanded ? 508 : 372, 108, 30, TRUE);
  MoveWindow(prefs_ui.import, 258, expanded ? 508 : 372, 124, 30, TRUE);
  MoveWindow(prefs_ui.rebuild, 390, expanded ? 508 : 372, 122, 30, TRUE);
  MoveWindow(prefs_ui.close, 520, expanded ? 508 : 372, 84, 30, TRUE);
  MoveWindow(prefs_ui.message, 18, expanded ? 544 : 408, 584, 44, TRUE);
  GetWindowRect(g.window, &parent);
  SetWindowPos(prefs_ui.dialog, HWND_TOP, parent.left + 100, parent.top + 50, 630,
               expanded ? 632 : 496, SWP_SHOWWINDOW);
}

static void prefs_dialog_controls(void) {
  int enabled;
  if (!prefs_ui.dialog) return;
  enabled = !prefs_ui.running;
  EnableWindow(prefs_ui.font, enabled);
  EnableWindow(prefs_ui.line, enabled);
  EnableWindow(prefs_ui.paragraph, enabled);
  EnableWindow(prefs_ui.margin, enabled);
  EnableWindow(prefs_ui.theme, enabled);
  EnableWindow(prefs_ui.direction, enabled);
  EnableWindow(prefs_ui.input, enabled);
  EnableWindow(prefs_ui.zoom, enabled);
  EnableWindow(prefs_ui.light_fg, enabled);
  EnableWindow(prefs_ui.light_bg, enabled);
  EnableWindow(prefs_ui.dark_fg, enabled);
  EnableWindow(prefs_ui.dark_bg, enabled);
  EnableWindow(prefs_ui.toggle, enabled);
  EnableWindow(prefs_ui.defaults, enabled);
  EnableWindow(prefs_ui.import, enabled);
  EnableWindow(prefs_ui.rebuild, enabled && prefs.corrupt);
  EnableWindow(prefs_ui.apply, enabled);
  EnableWindow(prefs_ui.close, !prefs_ui.running);
}

/* One acceptance path for every explicit choice. A corrupt or unknown-version
   file is never overwritten by an ordinary selection; only the exact public
   defaults may replace it, and only from the explicit rebuild entry. */
static void prefs_accept_fields(void) {
  reader_preferences value = prefs.active ? prefs.value : reader_preferences_defaults();
  reader_preferences_error problem;
  exr_status status;
  if (!prefs_ui.dialog || prefs_ui.running) return;
  if (!prefs_read_fields(&value)) return;
  memset(&problem, 0, sizeof(problem));
  status = prefs_status_to_exr(reader_preferences_validate(&value, &problem));
  if (status != EXR_OK) {
    prefs_notice(L"数值或选项不在允许范围内，未应用。请检查字号、行距、段距、页边距和缩放。");
    return;
  }
  if (!prefs_geometry_ok(&value)) {
    prefs_notice(L"字号、行距或页边距在当前页面放不下，未应用。");
    return;
  }
  if (prefs.corrupt && !prefs_is_defaults(&value)) {
    prefs_notice(L"现有设置文件无法读取，没有被覆盖。要重新建立，请使用“重建默认设置”。");
    return;
  }
  if (g.job || g.pending) { prefs_notice(L"当前任务完成后才能应用设置。"); return; }
  prefs_ui.running = 1;
  prefs_dialog_controls();
  prefs_notice(L"正在应用并保存设置…");
  if (!prefs_submit(&value, 1)) {
    prefs_ui.running = 0;
    prefs_dialog_controls();
    prefs_notice(L"当前任务完成后才能应用设置。");
  }
}

static void prefs_import_entry(void) {
  reader_preferences value = prefs.active ? prefs.value : reader_preferences_defaults();
  reader_preferences_legacy legacy;
  reader_preferences_import_report report;
  reader_preferences_error problem;
  int percent, zoom;
  if (!prefs_ui.dialog || prefs_ui.running) return;
  if (GetFileAttributesW(g.settings_path) == INVALID_FILE_ATTRIBUTES) {
    prefs_notice(L"没有找到旧的显示设置，无需导入。");
    return;
  }
  percent = (int)GetPrivateProfileIntW(L"Host", L"FontPercent", 150, g.settings_path);
  zoom = (int)GetPrivateProfileIntW(L"Host", L"ZoomPercent", 100, g.settings_path);
  if (percent < HOST_FONT_MIN || percent > HOST_FONT_MAX) percent = 150;
  if (zoom < HOST_ZOOM_MIN || zoom > HOST_ZOOM_MAX) zoom = 100;
  memset(&legacy, 0, sizeof(legacy));
  legacy.struct_size = sizeof(legacy);
  legacy.present = READER_PREFERENCES_LEGACY_FONT_SIZE | READER_PREFERENCES_LEGACY_FIXED_ZOOM;
  legacy.font_size = 28.0f * (float)percent / 100.0f;
  legacy.fixed_page_zoom = (uint32_t)zoom;
  memset(&report, 0, sizeof(report));
  memset(&problem, 0, sizeof(problem));
  report.struct_size = sizeof(report);
  if (reader_preferences_import_legacy(&value, &legacy, &report, &problem) != READER_PREFERENCES_OK) {
    prefs_notice(L"旧设置内容无效，当前设置保持不变。");
    return;
  }
  prefs_fill(&value);
  prefs_notice(L"已按旧设置填入字号和缩放；点“应用”后生效。");
}

static void prefs_rebuild_entry(void) {
  reader_preferences value = reader_preferences_defaults();
  if (!prefs_ui.dialog || prefs_ui.running) return;
  if (g.job || g.pending) { prefs_notice(L"当前任务完成后才能重建。"); return; }
  prefs_fill(&value);
  prefs_ui.running = 1;
  prefs_dialog_controls();
  prefs_notice(L"正在用默认设置重建文件…");
  if (!prefs_submit(&value, 1)) {
    prefs_ui.running = 0;
    prefs_dialog_controls();
    prefs_notice(L"当前任务完成后才能重建。");
  }
}

static void prefs_dialog_refresh(void) {
  if (!prefs_ui.dialog) return;
  if (prefs_ui.running) {
    prefs_ui.running = 0;
    prefs_dialog_controls();
  }
  if (prefs.corrupt)
    prefs_notice(L"现有设置文件无法读取，没有被覆盖。可点“重建默认设置”重新建立。");
  else if (!prefs_ui.running)
    prefs_notice(prefs.active ? L"当前的阅读设置已生效。" : L"尚未选择设置，阅读外观保持原样。");
  if (prefs_ui.want_close && !prefs_ui.running) {
    prefs_ui.want_close = 0;
    if (prefs_ui.dialog) DestroyWindow(prefs_ui.dialog);
  }
}

static void prefs_close(void) {
  if (!prefs_ui.dialog) return;
  if (prefs_ui.running) { prefs_ui.want_close = 1; return; }
  DestroyWindow(prefs_ui.dialog);
}

static INT_PTR CALLBACK prefs_dialog_procedure(HWND dialog, UINT message, WPARAM wparam, LPARAM lparam) {
  (void)lparam;
  switch (message) {
    case WM_INITDIALOG: {
      static const wchar_t *const themes[] = { L"浅色", L"深色", L"跟随系统" };
      static const wchar_t *const directions[] = { L"从左到右", L"从右到左", L"竖排" };
      static const wchar_t *const inputs[] = { L"点按", L"滑动", L"点按和滑动", L"硬件按键" };
      static const wchar_t *const names[] = {
        L"字号（磅）", L"行距（倍数）", L"段落间距（磅）", L"页边距（磅）",
        L"主题", L"翻页方向", L"翻页操作", L"固定页缩放（%）",
        L"浅色文字", L"浅色背景", L"深色文字", L"深色背景"
      };
      reader_preferences initial = prefs.active ? prefs.value : reader_preferences_defaults();
      int index;
      prefs_ui.dialog = dialog;
      SetWindowTextW(dialog, L"阅读设置");
      for (index = 0; index < 12; index++)
        prefs_ui.labels[index] = make_static(dialog, IDC_PREF_FONT_LABEL + index, names[index]);
      prefs_ui.font = prefs_entry(dialog, IDC_PREF_FONT, 176, 16, 120);
      prefs_ui.line = prefs_entry(dialog, IDC_PREF_LINE, 176, 52, 120);
      prefs_ui.paragraph = prefs_entry(dialog, IDC_PREF_PARAGRAPH, 176, 88, 120);
      prefs_ui.margin = prefs_entry(dialog, IDC_PREF_MARGIN, 176, 124, 120);
      prefs_ui.theme = prefs_combo(dialog, IDC_PREF_THEME, 176, 158, 260, themes, 3);
      prefs_ui.direction = prefs_combo(dialog, IDC_PREF_DIRECTION, 176, 194, 260, directions, 3);
      prefs_ui.input = prefs_combo(dialog, IDC_PREF_INPUT, 176, 230, 260, inputs, 4);
      prefs_ui.zoom = prefs_entry(dialog, IDC_PREF_ZOOM, 176, 266, 120);
      prefs_ui.light_fg = prefs_entry(dialog, IDC_PREF_LIGHT_FG, 176, 332, 120);
      prefs_ui.light_bg = prefs_entry(dialog, IDC_PREF_LIGHT_BG, 176, 364, 120);
      prefs_ui.dark_fg = prefs_entry(dialog, IDC_PREF_DARK_FG, 176, 396, 120);
      prefs_ui.dark_bg = prefs_entry(dialog, IDC_PREF_DARK_BG, 176, 428, 120);
      prefs_ui.toggle = make_button(dialog, IDC_PREF_TOGGLE, L"展开配色(&G)");
      prefs_ui.apply = make_button(dialog, IDC_PREF_APPLY, L"应用(&A)");
      prefs_ui.defaults = make_button(dialog, IDC_PREF_DEFAULTS, L"默认值(&D)");
      prefs_ui.import = make_button(dialog, IDC_PREF_IMPORT, L"导入旧设置(&I)");
      prefs_ui.rebuild = make_button(dialog, IDC_PREF_REBUILD, L"重建默认设置(&B)");
      prefs_ui.close = make_button(dialog, IDC_PREF_CLOSE, L"关闭(&C)");
      prefs_ui.note = make_static(dialog, IDC_PREF_NOTE,
        L"主题只改变文字和页面底色；固定页书籍保留原书颜色。改动只在“应用”后生效。");
      prefs_ui.message = make_static(dialog, IDC_PREF_MESSAGE,
        prefs.corrupt ? L"现有设置文件无法读取，没有被覆盖。" : L"未做修改。");
      prefs_ui.expanded = 0;
      prefs_fill(&initial);
      prefs_dialog_layout();
      prefs_dialog_controls();
      SetFocus(prefs_ui.font);
      return FALSE;
    }
    case WM_COMMAND: {
      int id = LOWORD(wparam);
      if (id == IDCANCEL || id == IDC_PREF_CLOSE) { prefs_close(); return TRUE; }
      if (prefs_ui.running) return TRUE;
      if (id == IDC_PREF_TOGGLE) {
        prefs_ui.expanded = !prefs_ui.expanded;
        SetWindowTextW(prefs_ui.toggle, prefs_ui.expanded ? L"收起配色(&G)" : L"展开配色(&G)");
        prefs_dialog_layout();
        return TRUE;
      }
      if (id == IDC_PREF_DEFAULTS) {
        reader_preferences value = reader_preferences_defaults();
        prefs_fill(&value);
        prefs_notice(L"已填入公开默认值；点“应用”后生效。");
        return TRUE;
      }
      if (id == IDC_PREF_IMPORT) { prefs_import_entry(); return TRUE; }
      if (id == IDC_PREF_REBUILD) { prefs_rebuild_entry(); return TRUE; }
      if (id == IDC_PREF_APPLY) { prefs_accept_fields(); return TRUE; }
      return TRUE;
    }
    case WM_CLOSE:
      prefs_close();
      return TRUE;
    case WM_DESTROY:
      prefs_ui.dialog = NULL;
      prefs_ui.message = prefs_ui.toggle = prefs_ui.note = NULL;
      prefs_ui.font = prefs_ui.line = prefs_ui.paragraph = prefs_ui.margin = NULL;
      prefs_ui.theme = prefs_ui.direction = prefs_ui.input = prefs_ui.zoom = NULL;
      prefs_ui.light_fg = prefs_ui.light_bg = prefs_ui.dark_fg = prefs_ui.dark_bg = NULL;
      prefs_ui.apply = prefs_ui.defaults = prefs_ui.import = prefs_ui.rebuild = prefs_ui.close = NULL;
      prefs_ui.running = 0;
      prefs_ui.want_close = 0;
      if (g.window && IsWindow(g.window)) {
        host_a11y_owner_enabled(1);
        if (!g.closing) { SetActiveWindow(g.window); SetFocus(g.page); }
      }
      prefs_dialog_closed();
      return TRUE;
  }
  return FALSE;
}

static void prefs_show(void) {
  union { DWORD alignment; unsigned char bytes[sizeof(DLGTEMPLATE) + 6]; } data;
  DLGTEMPLATE *template;
  HWND window;
  if (prefs_ui.dialog || g.closing) return;
  if (g.job || g.pending) { set_status(L"当前任务完成后才能打开阅读设置。"); return; }
  memset(&data, 0, sizeof(data));
  template = (DLGTEMPLATE *)data.bytes;
  template->style = WS_POPUP | WS_CAPTION | WS_SYSMENU | DS_MODALFRAME;
  template->cx = 340; template->cy = 150;
  window = CreateDialogIndirectParamW(GetModuleHandleW(NULL), template, g.window,
                                      prefs_dialog_procedure, 0);
  if (!window) { set_status(L"无法打开阅读设置窗口。"); return; }
  host_a11y_owner_enabled(0);
  SetForegroundWindow(window);
  SetFocus(prefs_ui.font);
}

static void prefs_create_menu(HWND parent) {
  HMENU menu = CreateMenu(), popup = CreatePopupMenu();
  if (!menu || !popup) {
    if (menu) DestroyMenu(menu);
    if (popup) DestroyMenu(popup);
    return;
  }
  AppendMenuW(popup, MF_STRING, IDC_PREFERENCES, L"阅读设置(&R)…\tCtrl+,");
  AppendMenuW(menu, MF_POPUP, (UINT_PTR)popup, L"设置(&S)");
  SetMenu(parent, menu);
}

static void prefs_destroy_menu(HWND parent) {
  HMENU menu = parent ? GetMenu(parent) : NULL;
  if (!menu) return;
  SetMenu(parent, NULL);
  DestroyMenu(menu);
}

static void prefs_translate(MSG *message) {
  if (message->message != WM_KEYDOWN || !g.window || !IsWindowEnabled(g.window)) return;
  if (!(GetKeyState(VK_CONTROL) & 0x8000)) return;
  if (message->wParam == VK_OEM_COMMA) { prefs_show(); message->message = WM_NULL; }
}
