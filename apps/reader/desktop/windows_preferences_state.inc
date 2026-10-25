/* SPDX-License-Identifier: MIT */
/* Installed F3 reading preferences: bounded local store and pure value helpers.
 *
 * Everything here runs on the UI owner except the two helpers the worker calls
 * (prefs_write, prefs_commit). They read only plain values copied into the job,
 * so no mutable GUI state ever crosses a thread boundary. No SDK object is
 * created, laid out or rendered in this file. */

#define PREFS_PAGE_WIDTH 720.0f
#define PREFS_PAGE_HEIGHT 1040.0f
#define PREFS_FONT_MIN 4.0f
#define PREFS_FONT_MAX 256.0f
#define PREFS_SWIPE_DISTANCE 40
#define PREFS_TAP_DISTANCE 6

static host_preferences prefs;
static int prefs_press_active;
static int prefs_press_x, prefs_press_y;
/* One coalesced turn request made while the worker was busy. */
static int prefs_turn_pending;

static void prefs_set_path(void) {
  if (!prefs.path[0]) path_join(prefs.path, HOST_PATH, g.data_dir, L"preferences.json");
}

/* System light/dark is sampled once per native notification on this thread. */
static reader_preferences_theme prefs_sample_system(void) {
  HKEY key;
  DWORD value = 1, size = (DWORD)sizeof(value);
  if (RegOpenKeyExW(HKEY_CURRENT_USER,
                    L"Software\\Microsoft\\Windows\\CurrentVersion\\Themes\\Personalize",
                    0, KEY_QUERY_VALUE, &key) == ERROR_SUCCESS) {
    if (RegQueryValueExW(key, L"AppsUseLightTheme", NULL, NULL, (LPBYTE)&value, &size) != ERROR_SUCCESS ||
        size != sizeof(value)) value = 1;
    RegCloseKey(key);
  }
  return value ? READER_PREFERENCES_THEME_LIGHT : READER_PREFERENCES_THEME_DARK;
}

static int prefs_geometry_ok(const reader_preferences *value) {
  float inner_width = PREFS_PAGE_WIDTH - 2.0f * value->margin;
  float inner_height = PREFS_PAGE_HEIGHT - 2.0f * value->margin;
  return inner_width >= value->font_size * 1.5f &&
         inner_height >= value->font_size * value->line_spacing;
}

static reader_preferences_theme prefs_effective(const reader_preferences *value, int system_theme) {
  return reader_preferences_effective_theme(value, (reader_preferences_theme)system_theme);
}

static uint32_t prefs_pack(const uint8_t rgba[4]) {
  return ((uint32_t)rgba[0] << 24) | ((uint32_t)rgba[1] << 16) |
         ((uint32_t)rgba[2] << 8) | (uint32_t)rgba[3];
}

static uint32_t prefs_background_of(const reader_preferences *value, int system_theme) {
  return prefs_pack(prefs_effective(value, system_theme) == READER_PREFERENCES_THEME_DARK
                        ? value->dark_background : value->light_background);
}

static uint32_t prefs_foreground_of(const reader_preferences *value, int system_theme) {
  return prefs_pack(prefs_effective(value, system_theme) == READER_PREFERENCES_THEME_DARK
                        ? value->dark_foreground : value->light_foreground);
}

/* The public user stylesheet is the only foreground mechanism: it is applied by
   the existing source/layout path after book CSS, so it wins without touching
   authored paints, images or the document itself. */
static int prefs_css_text(int themed, uint32_t foreground, char *out, size_t capacity) {
  if (!themed) return 0;
  snprintf(out, capacity, "*{color:#%08X}\n", (unsigned)foreground);
  return 1;
}

/* Stylesheet text lives on this stack frame only: the pager copies it during
   the create call, so no session or job ever retains a pointer to it. */
static exr_status prefs_page_pager(const exr_document *document, const exr_layout_config *config,
                                   int themed, uint32_t foreground, exr_pager **out, exr_error *error) {
  exr_layout_config copy = *config;
  char css[48];
  if (prefs_css_text(themed, foreground, css, sizeof(css))) copy.user_css = css;
  return exr_pager_create(document, g.font, &copy, out, error);
}

static exr_status prefs_chapter_pager(exr_publication *publication, size_t part,
                                      const exr_layout_config *config, int themed, uint32_t foreground,
                                      const exr_chapter_options *options, exr_pager **out,
                                      exr_error *error) {
  exr_layout_config copy = *config;
  char css[48];
  if (prefs_css_text(themed, foreground, css, sizeof(css))) copy.user_css = css;
  return exr_publication_pager_create(publication, part, g.font, &copy, options, out, error);
}

static exr_status prefs_status_to_exr(reader_preferences_status status) {
  switch (status) {
    case READER_PREFERENCES_OK: return EXR_OK;
    case READER_PREFERENCES_CANCELLED: return EXR_CANCELLED;
    case READER_PREFERENCES_IO: return EXR_IO;
    case READER_PREFERENCES_FORMAT: case READER_PREFERENCES_VERSION: return EXR_FORMAT;
    case READER_PREFERENCES_LIMIT: return EXR_LIMIT;
    case READER_PREFERENCES_ARGUMENT: case READER_PREFERENCES_RANGE: return EXR_ARGUMENT;
  }
  return EXR_FORMAT;
}

static const wchar_t *prefs_problem_text(reader_preferences_status status) {
  switch (status) {
    case READER_PREFERENCES_VERSION: return L"设置文件版本不受支持，原文件未改动。";
    case READER_PREFERENCES_FORMAT: return L"设置文件内容无法识别，原文件未改动。";
    case READER_PREFERENCES_RANGE: return L"设置文件中的数值超出允许范围，原文件未改动。";
    case READER_PREFERENCES_LIMIT: return L"设置文件超过大小上限，原文件未改动。";
    case READER_PREFERENCES_IO: return L"无法读写设置文件，原文件未改动。";
    case READER_PREFERENCES_CANCELLED: return L"设置操作已取消，原设置保持不变。";
    default: return L"设置文件无法使用，原文件未改动。";
  }
}

/* Bounded local read on the UI owner: one file of at most 64 KiB, no SDK work. */
static void prefs_initialize(void) {
  reader_preferences candidate;
  reader_preferences_error problem;
  char *path;
  prefs.value = reader_preferences_defaults();
  prefs.active = 0;
  prefs.file_present = 0;
  prefs.corrupt = 0;
  prefs.load_status = READER_PREFERENCES_OK;
  prefs.system_theme = (int)prefs_sample_system();
  prefs.system_events = 0;
  prefs.theme_pending = 0;
  prefs.applied = 0;
  prefs_set_path();
  if (GetFileAttributesW(prefs.path) == INVALID_FILE_ATTRIBUTES) return;
  prefs.file_present = 1;
  candidate = prefs.value;
  memset(&problem, 0, sizeof(problem));
  path = host_utf8(prefs.path);
  if (!path) {
    prefs.corrupt = 1;
    prefs.load_status = READER_PREFERENCES_IO;
    return;
  }
  prefs.load_status = (int)reader_preferences_load(path, &candidate, NULL, &problem);
  free(path);
  if (prefs.load_status == READER_PREFERENCES_OK && !prefs_geometry_ok(&candidate))
    prefs.load_status = READER_PREFERENCES_RANGE;
  if (prefs.load_status != READER_PREFERENCES_OK) {
    prefs.corrupt = 1;
    return;
  }
  prefs.value = candidate;
  prefs.active = 1;
}

/* Strict atomic save on the worker. On every failure the previous file stays
   whole and the caller keeps the accepted record and frame. */
static exr_status prefs_write(const reader_preferences *value, wchar_t *message, size_t capacity) {
  reader_preferences_error problem;
  reader_preferences_save_options options;
  reader_preferences_status status;
  char *path;
  if (!prefs_geometry_ok(value)) {
    copy_wstring(message, capacity,
                 L"字号、行距或页边距超出当前页面的排版范围，未保存；原设置保持不变。");
    return EXR_ARGUMENT;
  }
  path = host_utf8(prefs.path);
  if (!path) {
    copy_wstring(message, capacity, L"无法读写设置文件，原设置保持不变。");
    return EXR_MEMORY;
  }
  memset(&problem, 0, sizeof(problem));
  memset(&options, 0, sizeof(options));
  options.struct_size = sizeof(options);
  status = reader_preferences_save(value, path, &options, &problem);
  free(path);
  if (status != READER_PREFERENCES_OK) {
    copy_wstring(message, capacity, prefs_problem_text(status));
    return prefs_status_to_exr(status);
  }
  return EXR_OK;
}

/* A rejected or cancelled candidate never publishes: the frame prepared for it
   is discarded here, before the UI accepts anything. */
static exr_status prefs_commit(host_job *job, exr_status status) {
  exr_status saved;
  if (status == EXR_OK && job->prefs_persist) {
    saved = prefs_write(&job->prefs, job->message, 512);
    if (saved != EXR_OK) {
      frame_clear(&job->frame);
      job->have_frame = 0;
      if (job->candidate_pager) {
        exr_pager_free(job->candidate_pager);
        job->candidate_pager = NULL;
      }
      return saved;
    }
  }
  return status;
}

static void prefs_job_init(host_job *job) {
  job->prefs_valid = 0;
  job->prefs_persist = 0;
  job->system_theme = prefs.system_theme;
  if (prefs.active) {
    job->prefs = prefs.value;
    job->prefs_valid = 1;
    job->zoom_percent = (int)prefs.value.fixed_page_zoom;
  } else {
    job->prefs = reader_preferences_defaults();
  }
}

/* ---- F3 navigation semantics (values only; the page control applies them) */
static int prefs_turn_input(void) {
  return prefs.active ? (int)prefs.value.page_turn_input : 0;
}
static int prefs_vertical(void) {
  return prefs.active && prefs.value.page_turn_direction == READER_PREFERENCES_TURN_VERTICAL;
}
static int prefs_rtl(void) {
  return prefs.active && prefs.value.page_turn_direction == READER_PREFERENCES_TURN_RTL;
}
static int prefs_taps(void) {
  int input = prefs_turn_input();
  return input == READER_PREFERENCES_INPUT_TAP || input == READER_PREFERENCES_INPUT_TAP_AND_SWIPE;
}
static int prefs_swipes(void) {
  int input = prefs_turn_input();
  return input == READER_PREFERENCES_INPUT_SWIPE || input == READER_PREFERENCES_INPUT_TAP_AND_SWIPE;
}
static int prefs_hardware_keys(void) {
  return prefs_turn_input() == READER_PREFERENCES_INPUT_HARDWARE_KEYS;
}

/* +1 forward, -1 backward, 0 not a F3 turn. */
static int prefs_turn_from_tap(int x, int y, int width, int height) {
  int forward;
  if (!prefs_taps()) return 0;
  forward = prefs_vertical() ? (y >= height / 2) : (x >= width / 2);
  if (!prefs_vertical() && prefs_rtl()) forward = !forward;
  return forward ? 1 : -1;
}

static int prefs_turn_from_swipe(int dx, int dy) {
  int forward;
  if (!prefs_swipes()) return 0;
  if (prefs_vertical()) {
    if (dy <= -PREFS_SWIPE_DISTANCE) return 1;
    if (dy >= PREFS_SWIPE_DISTANCE) return -1;
    return 0;
  }
  if (dx <= -PREFS_SWIPE_DISTANCE) forward = 1;
  else if (dx >= PREFS_SWIPE_DISTANCE) forward = 0;
  else return 0;
  if (prefs_rtl()) forward = !forward;
  return forward ? 1 : -1;
}

static int prefs_turn_from_key(WPARAM key) {
  int vertical, rtl;
  if (!prefs_hardware_keys()) return 0;
  vertical = prefs_vertical();
  rtl = prefs_rtl();
  switch (key) {
    case VK_NEXT: return 1;
    case VK_PRIOR: return -1;
    case VK_RIGHT: return vertical ? 0 : (rtl ? -1 : 1);
    case VK_LEFT: return vertical ? 0 : (rtl ? 1 : -1);
    case VK_DOWN: return vertical ? 1 : 0;
    case VK_UP: return vertical ? -1 : 0;
  }
  return 0;
}

static int prefs_is_defaults(const reader_preferences *value) {
  reader_preferences base = reader_preferences_defaults();
  return value->font_size == base.font_size && value->line_spacing == base.line_spacing &&
         value->paragraph_spacing == base.paragraph_spacing && value->margin == base.margin &&
         value->theme == base.theme && value->page_turn_direction == base.page_turn_direction &&
         value->page_turn_input == base.page_turn_input &&
         value->fixed_page_zoom == base.fixed_page_zoom &&
         !memcmp(value->light_foreground, base.light_foreground, 4) &&
         !memcmp(value->light_background, base.light_background, 4) &&
         !memcmp(value->dark_foreground, base.dark_foreground, 4) &&
         !memcmp(value->dark_background, base.dark_background, 4);
}
