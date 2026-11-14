/* SPDX-License-Identifier: MIT */
/* EXReader Windows native reference host.
 *
 * Win32 host for the installed EXReader SDK: SQLite-backed bookshelf, queued
 * import, reflow and fixed-page reading, text selection, annotations, anchored
 * progress restore and a UI-level acceptance driver. The original 26-check
 * --self-test path is kept below for the packaging tool.
 *
 * The implementation intentionally stays in this single translation unit because
 * examples/CMakeLists.txt is owned by the integration branch. examples/windows
 * contains an independent consumer build against the installed SDK.
 */
#define _CRT_SECURE_NO_WARNINGS
#define WIN32_LEAN_AND_MEAN
#define UNICODE
#define _UNICODE
#ifndef _WIN32_WINNT
#define _WIN32_WINNT 0x0602
#endif
#include <windows.h>
#include <commdlg.h>
#include <shellapi.h>
#include <process.h>
#include <exreader.h>
#include <exr/font_manager.h>
#include "windows/paint_probe.h"
#ifdef EXR_READER_WINDOWS_SHELL
#include "windows/shell_d2d.h"
#include "windows/shell_geometry.h"
#include "../tools/convert_json.h"
#include "windows/shell_speech.h"
int shell_epub_source(exr_source *source);
int shell_style_document(exr_document **document);
/* Created with the main window; draws the reading screen (windows/shell_screen.inc). */
static shell_d2d *host_shell;
static int de_active(void);
static int de_exit(void);
static void de_controls(void);
static int de_draw_item(const DRAWITEMSTRUCT *item);
#endif
#include <math.h>
#include <limits.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdarg.h>
#include <wchar.h>
#ifdef EXR_READER_PRODUCT_CATALOG
#include "catalog_sdk.h"
#endif
#ifdef EXR_READER_WINDOWS_TXT_RECOVERY
#include <original_import.h>
#endif
#ifdef EXR_READER_WINDOWS_TXT_PROGRESS
#include <reader_txt_progress.h>
#define TXT_TRACE(step) do { if (getenv("EXR_TRACE_TXT")) { fprintf(stderr, "TXT_TRACE %s\n", step); fflush(stderr); } } while (0)
#endif
#ifdef EXR_READER_DESKTOP_METADATA
#include <reader_metadata.h>
#endif
#ifdef EXR_READER_WINDOWS_ACCOUNT
#include <bcrypt.h>
#include <reader_session.h>
#include <reader_projection.h>
#include <exr_credentials.h>
#include <exr_sideload.h>
#endif

#define HOST_PATH 4096
#define HOST_IMPORT_LIMIT ((size_t)96 * 1024 * 1024)
#define HOST_FONT_MIN 80
#define HOST_FONT_MAX 300
#define HOST_FONT_STEP 10
#define HOST_ZOOM_MIN 25
#define HOST_ZOOM_MAX 400
#define HOST_ZOOM_STEP 25
#define HOST_TEXT_PREVIEW 160
#define HOST_NOTE_PREVIEW 96
#define HOST_PAGE_TEXT_LIMIT ((size_t)1024 * 1024)
#ifdef EXR_READER_WINDOWS_TXT_PROGRESS
/* Product revision history is append-only and bounded per entity, so an accepted
   page is persisted once it moves a whole block or when the session leaves it. */
#define HOST_TXT_SAVE_BYTES ((uint64_t)32768)
#endif
#define HOST_PAGE_GLYPH_LIMIT ((size_t)65536)
#ifdef EXR_READER_WINDOWS_IMPORT_ORGANIZE
#include "../apps/reader/desktop/windows_import_organize_types.h"
#endif
#ifdef EXR_READER_WINDOWS_SEARCH
#include "../apps/reader/desktop/windows_search_types.h"
#endif
#ifdef EXR_READER_WINDOWS_NAVIGATION
#include "../apps/reader/desktop/windows_navigation_types.h"
#endif
#ifdef EXR_READER_WINDOWS_RECORDS
#include "../apps/reader/desktop/windows_records_types.h"
#endif
#ifdef EXR_READER_WINDOWS_PREFERENCES
#include "../apps/reader/desktop/windows_preferences.h"
#endif
#ifdef EXR_READER_WINDOWS_RAW3
#include "../apps/reader/desktop/windows_raw3_apis.h"
#endif
#ifdef EXR_READER_WINDOWS_WAVE3
#include "../apps/reader/desktop/windows_wave3_types.h"
#endif

enum {
  IDC_SHELF_LABEL = 118, IDC_BOOKS, IDC_NOTES_LABEL, IDC_NOTES, IDC_NOTE_EDIT,
  IDC_PAGE, IDC_PAGE_LABEL, IDC_STATUS, IDC_SHELF_SEARCH, IDC_SHELF_REFRESH,
  IDC_METADATA_BUTTON, IDC_METADATA_TITLE, IDC_METADATA_AUTHOR, IDC_METADATA_FAVORITE,
  IDC_METADATA_SAVE, IDC_METADATA_CANCEL, IDC_METADATA_RETRY, IDC_METADATA_DISCARD,
  IDC_METADATA_MESSAGE,
  IDC_ACCOUNT_BUTTON, IDC_ACCOUNT_ROOT, IDC_ACCOUNT_USER, IDC_ACCOUNT_PASSWORD, IDC_ACCOUNT_REMEMBER,
  IDC_ACCOUNT_APPLY, IDC_ACCOUNT_SYNC, IDC_ACCOUNT_CANCEL, IDC_ACCOUNT_RETRY, IDC_ACCOUNT_FORGET,
  IDC_ACCOUNT_CLOSE, IDC_ACCOUNT_MESSAGE, IDC_ACCOUNT_DETAIL,
  /* Labels for the remaining model/dialog controls. */
  IDC_SHELF_SEARCH_LABEL = 150, IDC_NOTE_EDIT_LABEL
};

enum {
  HOST_CMD_IMPORT = 0x9000, HOST_CMD_OPEN
};

#define WM_HOST_COMPLETE (WM_APP + 1)
#define WM_HOST_PROGRESS (WM_APP + 2)
#define WM_HOST_SDK_JOB (WM_APP + 0x590)

static int host_offscreen;
/* Offscreen acceptance must never activate the shared desktop. Applies to included host UI too. */
static HWND host_focus(HWND window) { return host_offscreen ? GetFocus() : SetFocus(window); }
#define SetFocus host_focus
#ifdef EXR_READER_WINDOWS_SHELL
static int shell_active;
static int shelf_requested, shelf_visible, shelf_exit_pending, shell_bar_hidden, shell_tap_edge=25;
static void shelf_create(HWND parent);
static void shelf_show(int show);
static int shelf_layout(void);
static void shelf_refresh(void);
static void shelf_return(void);
static void shelf_pump(void);
static int shelf_capture(void);
static int shelf_before_exit(void);
static void shelf_imported(int64_t id,const wchar_t *path);
static void shelf_opened(void);
static void shelf_resume(size_t offset);
static void shelf_load(void);
static void shelf_destroy(void);
static void gesture_overlay(HDC dc,const RECT *area);
static unsigned shell_dpi = 96;
static BOOL shell_dpi_requested;
static DWORD shell_dpi_error;
static int shell_pmv2, shell_dpi_changing, shell_layout_waiting, shell_vertical;
static int shell_search_open;
static float shell_font = SHELL_BODY_DEFAULT_FONT;
static exr_reader_style shell_style={18,1.75f,.5f,40,48,40,48,0};
static void shell_style_load(void);
static int shell_style_save(void);
static int shell_footnote_click(int x,int y);
static int shell_footnote_translate(const MSG *message);
static void shell_footnote_close(void);
static int shell_theme_mode=2; /* light, dark, system */
static int shell_system_dark(void) {
  DWORD value=1,bytes=sizeof(value);
  RegGetValueW(HKEY_CURRENT_USER,L"Software\\Microsoft\\Windows\\CurrentVersion\\Themes\\Personalize",
    L"AppsUseLightTheme",RRF_RT_REG_DWORD,NULL,&value,&bytes);
  return value==0;
}
/* Windows high contrast wins over the light/dark choice: the palette is the
   system colours, never the design tokens. 2 is the `dark` value that selects it. */
static int shell_contrast;
static unsigned shell_contrast_generation;
static uint32_t shell_sys_rgb(int index) { DWORD c=GetSysColor(index); return ((c&255u)<<16)|(c&0xff00u)|((c>>16)&255u); }
static void shell_contrast_refresh(void) {
  HIGHCONTRASTW high; memset(&high,0,sizeof(high)); high.cbSize=sizeof(high);
  shell_contrast=SystemParametersInfoW(SPI_GETHIGHCONTRAST,sizeof(high),&high,0) && (high.dwFlags&HCF_HIGHCONTRASTON);
  if(!shell_contrast) return;
  shell_theme_contrast=(shell_theme){
    shell_sys_rgb(COLOR_WINDOW),shell_sys_rgb(COLOR_WINDOW),shell_sys_rgb(COLOR_WINDOW),
    shell_sys_rgb(COLOR_BTNFACE),shell_sys_rgb(COLOR_BTNFACE),shell_sys_rgb(COLOR_WINDOW),
    shell_sys_rgb(COLOR_WINDOWTEXT),shell_sys_rgb(COLOR_WINDOWTEXT),shell_sys_rgb(COLOR_GRAYTEXT),
    shell_sys_rgb(COLOR_HOTLIGHT),shell_sys_rgb(COLOR_HIGHLIGHT),shell_sys_rgb(COLOR_HIGHLIGHTTEXT),
    shell_sys_rgb(COLOR_WINDOWTEXT)};
  shell_contrast_generation++;
}
static int shell_is_dark(void) {
  if(shell_contrast) return 2;
  return shell_theme_mode==1 || (shell_theme_mode==2 && shell_system_dark());
}
static void shell_step_font(int delta);
static unsigned long shell_epoch = 1, shell_pager_builds, shell_failed_epoch;
static shell_geometry shell_target;
static void shell_request_layout(void);
static void shell_pump_layout(void);
static int select_valid, select_drag, select_turn;
static int shell_drag_begin;
static void shell_selection_reset(void);
static void shell_selection_landed(void);
static void annot_sync(void);
static int annot_translate(const MSG *message);
static int annot_command(int command);
static int annot_click(int x,int y);
static void annot_pixels(uint32_t *pixels,int width,int height);
static void annot_marks(HDC dc);
static int annot_count,annot_selected=-1;
static int tts_state; /* 0 stopped, 1 speaking, 2 paused */
static void tts_stop(void);
static void tts_destroy(void);
static void tts_poll(void);
static void tts_pixels(uint32_t *pixels,int width,int height);
static void tts_menu(HMENU menu);
static int tts_command(int command);
static void tts_layout(void);
static int tts_translate(const MSG *message);
static void shell_selection_paint(HDC dc);
static size_t shell_selection_bytes(char **out);
static void dict_lookup(void);
static void dict_auto_lookup(void);
static void dict_hide(void);
static void dict_close_all(void);
static void dict_manager_open(void);
static int dict_translate(const MSG *message);
static void dict_shutdown(void);
#endif

typedef struct {
#ifdef EXR_READER_WINDOWS_SHELL
  shell_geometry shell_geometry;
  unsigned long shell_epoch;
  int writing_mode;
  int display_shell_theme;
  int display_shell_paper;
  exr_line *shell_lines;
  size_t shell_line_count;
  int shell_anchored;
  RECT shell_image; /* The sole decoded image's source pixels; empty on text/mixed pages. */
  uint32_t *shell_image_pixels; /* Owned full image, independent of page clipping/CSS. */
  size_t shell_image_count;
  unsigned shell_image_flags;
  int shell_visible_text, shell_image_available;
#endif
  exr_bitmap bitmap;
  uint32_t *dib;
  wchar_t *text;
  size_t text_bytes;
  char *utf8;
  exr_glyph *glyphs;
  size_t glyph_count;
  size_t part;
  unsigned long generation;
  exr_anchor point;
  exr_chapter_stats chapter_stats;
  size_t page, range_start, range_end;
#if defined(EXR_READER_WINDOWS_TXT_PROGRESS) && defined(EXR_READER_WINDOWS_SEARCH) && defined(EXR_READER_WINDOWS_WAVE3)
  /* A history-resolved point belongs to this frame only. */
  size_t txt_history_point;
  int txt_has_history_point;
#endif
  size_t page_count;
  int valid;
  int fixed;
  int bounded;
  int hold_progress;
  int64_t book_id;
  wchar_t title[256];
  double render_scale;
  /* Independent UI selection data, never a borrowed pager-cache entry. */
  exr_layout *hit_layout;
  exr_fixed_text *fixed_text;
  exr_page_geometry geometry;
  HBITMAP display_bitmap;
  int display_width,display_height;
} host_frame;

typedef struct {
  int active;
  int fixed;
  size_t page, start, end;
} host_selection;

typedef struct {
  int active;
  int fixed;
  int txt; /* Product original, with no SDK book identity. */
  int txt_pager_invalid; /* Recreate after a failed or cancelled layout. */
#if defined(EXR_READER_WINDOWS_TXT_RECOVERY) || defined(EXR_READER_WINDOWS_SHELL)
  int txt_checkpoint_valid;
  exr_txt_checkpoint txt_checkpoint;
#endif
  exr_source txt_source; /* Borrowed from the pager. */
#ifdef EXR_READER_WINDOWS_TXT_PROGRESS
  char txt_key[73];      /* Product content identity of this session. */
#endif
  int64_t book_id;
  exr_document *document;
  exr_publication *publication;
  int bounded;
  int hold_progress;
  size_t part;
  exr_pager *pager;
  exr_fixed_document *fixed_document;
  exr_layout_config config;
#ifdef EXR_READER_WINDOWS_SHELL
  shell_geometry shell_geometry;
#endif
  size_t page;
  size_t page_count;
#if defined(EXR_READER_WINDOWS_SEARCH) || defined(EXR_READER_WINDOWS_NAVIGATION) || defined(EXR_READER_WINDOWS_RECORDS)
  char source_key[256];
#endif
#ifdef EXR_READER_WINDOWS_PREFERENCES
  /* Effective page palette of this session. Plain values, so a copied session
     never points at another session's stylesheet text. */
  uint32_t background, foreground;
  int themed;
#endif
} host_session;

typedef struct host_job host_job;
#ifdef EXR_READER_PRODUCT_CATALOG
typedef struct { char *key,*sort_title;uint64_t ordinal; } host_shelf_cursor;
#endif

typedef struct {
  HWND window, page, books, notes, note_edit, status, page_label;
#ifdef EXR_READER_WINDOWS_IMPORT_ORGANIZE
  HWND import_button; /* optional cloud-import context anchor */
#endif
  HWND shelf_label, notes_label, shelf_search_label, note_edit_label;
  exr_library *library;
  exr_font *font;
  exr_font_manager *font_manager;
  int font_fell_back;
  wchar_t font_family[128], font_label[192];
  wchar_t font_path[HOST_PATH];
  wchar_t data_dir[HOST_PATH];
  wchar_t library_path[HOST_PATH];
#ifdef EXR_READER_PRODUCT_CATALOG
  wchar_t product_path[HOST_PATH];
#ifdef EXR_READER_WINDOWS_TXT_RECOVERY
  wchar_t original_root[HOST_PATH];
#endif
  HANDLE product_lock;
  HANDLE product_profile_lock;
  int product_pending;
  HWND shelf_search,shelf_refresh;
  WNDPROC shelf_procedure;
  host_shelf_cursor *shelf_cursors;
  char *shelf_query;
  char shelf_group_id[33];int shelf_group_kind;
  char shelf_top_key[72],shelf_selected_key[72];
  unsigned long shelf_generation;
  int shelf_before,shelf_after,shelf_filter_pending,shelf_applying;
  int shelf_need_refresh,shelf_requested_direction,product_ready;
  unsigned shelf_max_cached,shelf_evicted,shelf_queries;
#endif
#ifdef EXR_READER_DESKTOP_METADATA
  HWND metadata_button,metadata_dialog,metadata_title,metadata_author,metadata_favorite,metadata_message;
  reader_metadata_snapshot *metadata_snapshot;
  wchar_t *metadata_title_value,*metadata_author_value;
  wchar_t metadata_notice[512];
  char metadata_key[72];
  int64_t metadata_book;
  int metadata_running,metadata_recovery,metadata_editable,metadata_favorite_value;
#endif
#ifdef EXR_READER_WINDOWS_ACCOUNT
  HWND account_button;
#endif
  wchar_t settings_path[HOST_PATH];
  wchar_t evidence_dir[HOST_PATH];
  wchar_t script_path[HOST_PATH];
  exr_book *shelf;
  size_t shelf_count;
  exr_note *reflow_notes;
  exr_epub_note *epub_notes;
  size_t epub_note_count;
  size_t reflow_note_count;
  exr_fixed_note *fixed_notes;
  size_t fixed_note_count;
  int64_t notes_book_id;
  exr_book current;
  int has_current;
  host_session session;
  host_frame frame;
  host_selection selection;
  int font_percent;
  int zoom_percent;
  int window_width;
  int window_height;
  host_job *job;
  host_job *pending;
  host_job *discard;
  int auto_open_imported;
  int closing;
  int ready;
  CRITICAL_SECTION library_lock;
  struct { int valid; double scale; int dx, dy; int bw, bh; } view;
  int drive_mode;
  FILE *drive_log;
  int drive_index;
  int drive_failures;
  int drive_done;
  int drive_waiting;
  unsigned drive_deadline;
  int delay_ms;
  int phase;
  wchar_t status_text[768];
  int64_t active_book_id;
  int restore_pending;
  int restored_anchor;
  wchar_t restore_note[256];
  int pending_selection;
  size_t pending_start, pending_end;
  size_t pending_part;
  int hit_pending, hit_up;
  float hit_x, hit_y;
  unsigned long gesture;
  int64_t pending_book;
  int progress_failed;
#ifdef EXR_READER_WINDOWS_TXT_PROGRESS
  /* Last durably committed TXT position. The UI never treats the in-memory page
     as saved: only a completed product revision updates these values. */
  char txt_saved_key[73];
  char active_txt_key[73];
  uint64_t txt_saved_offset;
  int txt_saved_valid;
  int txt_force_save; /* one-shot: close, book switch or relayout must persist */
  int txt_save_abandoned; /* a refused close-time write must not trap the exit */
#endif
  unsigned long saved_generation;
  unsigned long frame_sequence;
} host_state;

static host_state g;
#ifdef EXR_READER_WINDOWS_SHELL
static exr_status shelf_restore(host_session *session,const exr_control *control,size_t *page,size_t *offset,int *found,exr_error *error);
static exr_status shell_align_anchor(host_session *,size_t,host_frame *,const exr_control *,exr_error *);
static void shelf_fixed_page(int64_t id,const exr_fixed_page *pages,size_t count,size_t *target);
#endif
static int dragging;
#ifdef EXR_READER_WINDOWS_SHELL
static int shell_wants_reading(void) {
  return host_shell && 1;
}
static shell_geometry shell_snapshot(void) {
  RECT client = {0}; shell_geometry out = {0};
  if (shell_wants_reading() && !IsIconic(g.window)) {
    GetClientRect(g.window, &client);
    out = shell_geometry_for(client.right, client.bottom-(shell_search_open ? shell_px(48,shell_dpi):0), shell_dpi, shell_font, shell_vertical);
    out.style=shell_style;out.style.font_size=shell_font;
    out.width=client.right-shell_px(shell_style.left+shell_style.right,shell_dpi);
    out.height=client.bottom-shell_px(SHELL_TOPBAR_H+SHELL_PAGE_NUMBER_H+shell_style.top+shell_style.bottom,shell_dpi)
      -(shell_search_open ? shell_px(48,shell_dpi):0);
    out.enabled=out.width>=64 && out.height>=80;
  }
  return out;
}
static void shell_apply_config(exr_layout_config *config, shell_geometry geometry) {
  /* Pager creation copies CSS. Host jobs are serialized, including reflow. */
  static char css[4096];
  if (!geometry.enabled) return;
  char style_css[1024];float scale=geometry.dpi/96.f;
  exr_reader_style style=geometry.style;style.font_size=geometry.font;
  if(exr_reader_style_config(&style,geometry.width+(style.left+style.right)*scale,
      geometry.height+(style.top+style.bottom)*scale,scale,config,style_css,NULL)!=EXR_OK) return;
  snprintf(css,sizeof(css),"%s.exr-shell-cjk.exr-shell-paragraph{text-indent:2em}"
    ".exr-shell-latin.exr-shell-paragraph{text-indent:0}"
    ".exr-shell-paragraph{%s:0!important;%s:%.7gem!important}",style_css,
    geometry.vertical ? "margin-right":"margin-top",geometry.vertical ? "margin-left":"margin-bottom",
    (double)style.paragraph_spacing);
  for(int i=1;i<=16;i++) {
    size_t used=strlen(css);
    snprintf(css+used,sizeof(css)-used,".exr-shell-cjk.exr-shell-indent-%d{text-indent:%dem}",i,2-i);
  }
  /* Headings never justify: centred, as 回目 couplets are set in print. A
     detected chapter heading (第…回/章) opens a new page; the previous
     chapter's last page keeps its blank remainder. Dash rows and authored
     heading prefixes are hidden by shell_epub.cpp markup. */
  {
    size_t used=strlen(css);
    snprintf(css+used,sizeof(css)-used,
      ".exr-shell-hide{display:none}"
      ".exr-shell-cjk.exr-shell-heading{text-align:center;text-indent:0}"
      ".exr-shell-cjk.exr-shell-chapter{break-before:page;text-align:center;text-indent:0;"
        "font-size:1.25em;font-weight:normal;line-height:1.6;%s}"
      ".exr-shell-cjk.exr-shell-chapter-bare{%s}"
      ".exr-shell-cjk.exr-shell-chapter-sub{text-align:center;text-indent:0;"
        "font-size:1.25em;font-weight:normal;line-height:1.6;%s}",
      geometry.vertical ? "margin-right:2em;margin-left:1.6em" : "margin-top:2em;margin-bottom:1.6em",
      geometry.vertical ? "margin-left:0.3em" : "margin-bottom:0.3em",
      geometry.vertical ? "margin-right:0;margin-left:1.6em" : "margin-top:0;margin-bottom:1.6em");
  }
  config->user_css=css;
}
#endif
#ifdef EXR_HOST_WORKER_REVIEW
static int review_query_failure(int kind);
#endif
#ifdef EXR_READER_PRODUCT_CATALOG
static void product_shelf_remember(void);
static void product_shelf_dispatch(void);
static void product_shelf_schedule(int direction,int reset);
static void product_shelf_edges(void);
static void product_shelf_accept(host_job *job);
static void product_shelf_snapshot_changed(void);
static void product_shelf_search_changed(void);
static LRESULT CALLBACK product_shelf_procedure(HWND,UINT,WPARAM,LPARAM);
#endif

typedef exr_status (*host_progress_fn)(void *context, unsigned percent);

/* ------------------------------------------------------------------ */
/* Small helpers                                                       */
/* ------------------------------------------------------------------ */

/* Native accessibility providers live in one owner file (windows_accessibility.inc).
   These entry points are used by code that is compiled before that file. */
static void host_a11y_status_changed(void);
/* Accessible name/help for a window-based control; a panel appearing or going away. */
static void host_a11y_describe(HWND window, const wchar_t *name, const wchar_t *help);
static void host_a11y_panel_toggled(HWND panel, int shown);
static void host_a11y_prepare_note(void);
static inline void host_a11y_owner_enabled(int enabled);

static void set_status(const wchar_t *text) {
  if (!text) text = L"";
  wcsncpy(g.status_text, text, 767);
  g.status_text[767] = 0;
#ifdef EXR_READER_PRODUCT_CATALOG
  if(g.product_pending && !wcsstr(g.status_text,L"书架信息待恢复")) {
    size_t length=wcslen(g.status_text);
    wcsncat(g.status_text,L" · 书架信息待恢复",767-length);
  }
#endif
  if (g.status) { SetWindowTextW(g.status, g.status_text); host_a11y_status_changed(); }
}

static void set_statusf(const wchar_t *format, ...) {
  wchar_t buffer[768];
  va_list args;
  va_start(args, format);
  if (vswprintf(buffer, 768, format, args) < 0) buffer[767] = 0;
  va_end(args);
  set_status(buffer);
}

static const wchar_t *status_name(exr_status status) {
  switch (status) {
    case EXR_OK: return L"成功";
    case EXR_ARGUMENT: return L"参数或位置无效";
    case EXR_MEMORY: return L"内存不足";
    case EXR_IO: return L"读写失败";
    case EXR_ENCODING: return L"文本编码无效";
    case EXR_FORMAT: return L"文件格式无效";
    case EXR_LIMIT: return L"超出宿主或SDK限制";
    case EXR_DATABASE: return L"书架数据库错误";
    case EXR_FONT: return L"字体错误";
    case EXR_CANCELLED: return L"已取消";
    case EXR_PASSWORD: return L"需要PDF密码";
    case EXR_UNSUPPORTED: return L"当前SDK不支持该操作";
    default: return L"未知错误";
  }
}

static void describe_error(wchar_t *out, size_t capacity, const wchar_t *prefix,
                           exr_status status, const exr_error *error) {
  wchar_t detail[256] = L"";
  if (error && error->message[0]) {
    wchar_t *converted = NULL;
    int n = MultiByteToWideChar(CP_UTF8, 0, error->message, -1, NULL, 0);
    if (n > 0) {
      converted = calloc((size_t)n, sizeof(*converted));
      if (converted && MultiByteToWideChar(CP_UTF8, 0, error->message, -1, converted, n) > 0) {
        wcsncpy(detail, converted, 255);
        detail[255] = 0;
      }
      free(converted);
    }
  }
  if (detail[0])
    swprintf(out, capacity, L"%ls：%ls（%ls）", prefix ? prefix : L"操作失败",
             status_name(status), detail);
  else
    swprintf(out, capacity, L"%ls：%ls", prefix ? prefix : L"操作失败", status_name(status));
  out[capacity - 1] = 0;
}

static char *host_utf8(const wchar_t *value) {
  int size = WideCharToMultiByte(CP_UTF8, 0, value, -1, NULL, 0, NULL, NULL);
  char *out = size > 0 ? malloc((size_t)size) : NULL;
  if (out && !WideCharToMultiByte(CP_UTF8, 0, value, -1, out, size, NULL, NULL)) {
    free(out);
    out = NULL;
  }
  return out;
}

static wchar_t *host_wide(const char *value, size_t size) {
  int n;
  wchar_t *out;
  if (!value) return NULL;
  if (size > INT_MAX) return NULL;
  n = MultiByteToWideChar(CP_UTF8, MB_ERR_INVALID_CHARS, value, (int)size, NULL, 0);
  if (!n && size) return NULL;
  out = calloc((size_t)n + 1, sizeof(*out));
  if (out && n && !MultiByteToWideChar(CP_UTF8, MB_ERR_INVALID_CHARS, value, (int)size, out, n)) {
    free(out);
    return NULL;
  }
  return out;
}

static char *host_strdup(const char *text) {
  size_t size;
  char *copy;
  if (!text) return NULL;
  size = strlen(text) + 1;
  copy = malloc(size);
  if (copy) memcpy(copy, text, size);
  return copy;
}

static int host_anchor_copy(exr_anchor *out, const exr_anchor *anchor) {
  *out = *anchor;
  out->exact = anchor->exact ? host_strdup(anchor->exact) : NULL;
  out->prefix = anchor->prefix ? host_strdup(anchor->prefix) : NULL;
  out->suffix = anchor->suffix ? host_strdup(anchor->suffix) : NULL;
  out->chapter = anchor->chapter ? host_strdup(anchor->chapter) : NULL;
  return (!anchor->exact || out->exact) && (!anchor->prefix || out->prefix) &&
         (!anchor->suffix || out->suffix) && (!anchor->chapter || out->chapter);
}

static void copy_wstring(wchar_t *dst, size_t capacity, const wchar_t *src) {
  if (!capacity) return;
  if (!src) src = L"";
  wcsncpy(dst, src, capacity - 1);
  dst[capacity - 1] = 0;
}

static int ensure_directory(const wchar_t *path) {
  wchar_t buffer[HOST_PATH];
  size_t i, length;
  if (!path || !path[0]) return 0;
  copy_wstring(buffer, HOST_PATH, path);
  length = wcslen(buffer);
  for (i = 0; i < length; i++) {
    if (buffer[i] == L'\\' || buffer[i] == L'/') {
      wchar_t saved = buffer[i];
      buffer[i] = 0;
      if (i > 2 && !CreateDirectoryW(buffer, NULL) && GetLastError() != ERROR_ALREADY_EXISTS) {
        buffer[i] = saved;
        return 0;
      }
      buffer[i] = saved;
    }
  }
  if (!CreateDirectoryW(buffer, NULL) && GetLastError() != ERROR_ALREADY_EXISTS) return 0;
  return 1;
}

static void path_join(wchar_t *out, size_t capacity, const wchar_t *dir, const wchar_t *name) {
  swprintf(out, capacity, L"%ls\\%ls", dir, name);
  out[capacity - 1] = 0;
}

static void module_directory(wchar_t *out, size_t capacity) {
  wchar_t buffer[HOST_PATH];
  wchar_t *slash;
  out[0] = 0;
  if (!GetModuleFileNameW(NULL, buffer, HOST_PATH - 32)) return;
  slash = wcsrchr(buffer, L'\\');
  if (!slash) return;
  slash[1] = 0;
  copy_wstring(out, capacity, buffer);
}

static const wchar_t *format_name(exr_format format) {
  switch (format) {
    case EXR_TXT: return L"TXT";
    case EXR_HTML: return L"HTML";
    case EXR_FB2: return L"FB2";
    case EXR_EPUB: return L"EPUB";
    case EXR_DOCX: return L"DOCX";
    case EXR_RTF: return L"RTF";
    case EXR_MOBI: return L"MOBI";
    case EXR_PDF: return L"PDF";
    case EXR_CBZ: return L"CBZ";
    default: return L"未知";
  }
}

static int is_fixed_format(exr_format format) {
  return format == EXR_PDF || format == EXR_CBZ;
}

static int format_for_path(const wchar_t *path, exr_format *format) {
  const wchar_t *extension = wcsrchr(path, L'.');
  if (!extension) return 0;
  if (!_wcsicmp(extension, L".epub")) *format = EXR_EPUB;
  else if (!_wcsicmp(extension, L".pdf")) *format = EXR_PDF;
  else if (!_wcsicmp(extension, L".cbz")) *format = EXR_CBZ;
  else if (!_wcsicmp(extension, L".txt")) *format = EXR_TXT;
  else if (!_wcsicmp(extension, L".html") || !_wcsicmp(extension, L".htm")) *format = EXR_HTML;
  else if (!_wcsicmp(extension, L".fb2")) *format = EXR_FB2;
  else if (!_wcsicmp(extension, L".docx")) *format = EXR_DOCX;
  else if (!_wcsicmp(extension, L".rtf")) *format = EXR_RTF;
  else if (!_wcsicmp(extension, L".mobi") || !_wcsicmp(extension, L".azw3")) *format = EXR_MOBI;
  else return 0;
  return 1;
}

static void frame_clear(host_frame *frame) {
  host_probe_require_ui();
  if(frame->display_bitmap)DeleteObject(frame->display_bitmap);
#ifdef EXR_READER_WINDOWS_SHELL
  free(frame->shell_lines);
  free(frame->shell_image_pixels);
#endif
  exr_layout_free(frame->hit_layout);
  exr_fixed_text_free(frame->fixed_text);
  exr_bitmap_free(&frame->bitmap);
  free(frame->dib);
  free(frame->text);
  free(frame->utf8);
  free(frame->glyphs);
  exr_anchor_free(&frame->point);
  memset(frame, 0, sizeof(*frame));
}

/* The frame owns its display bitmap. The pixel worker prepares it before the
   UI joins; cached frames retain it and need no conversion on a cache hit. */
static int frame_prepare_display(host_frame *frame) {
  RECT area;if(!frame->valid || !frame->dib || !g.page)return 0;
  if(!GetClientRect(g.page,&area))return 0;
  double scale=fmin((area.right-8.0)/frame->bitmap.width,(area.bottom-8.0)/frame->bitmap.height);
#ifdef EXR_READER_WINDOWS_SHELL
  if (frame->shell_geometry.enabled) scale = 1.0;
#endif
  int w=(int)(frame->bitmap.width*scale),h=(int)(frame->bitmap.height*scale);
  if(w<=0 || h<=0)return 0;
  if(frame->display_bitmap && frame->display_width==w && frame->display_height==h)return 1;
  BITMAPINFO target={0},source={0};void *bits=NULL;
  target.bmiHeader.biSize=sizeof(BITMAPINFOHEADER);target.bmiHeader.biWidth=w;
  target.bmiHeader.biHeight=-h;target.bmiHeader.biPlanes=1;target.bmiHeader.biBitCount=32;
  HDC dc=CreateCompatibleDC(NULL);if(!dc)return 0;
  HBITMAP bitmap=CreateDIBSection(dc,&target,DIB_RGB_COLORS,&bits,NULL,0);
  if(!bitmap){DeleteDC(dc);return 0;}
  HGDIOBJ old=SelectObject(dc,bitmap);
  source.bmiHeader=target.bmiHeader;source.bmiHeader.biWidth=(LONG)frame->bitmap.width;
  source.bmiHeader.biHeight=-(LONG)frame->bitmap.height;
#ifdef EXR_READER_WINDOWS_SHELL
  if (frame->shell_geometry.enabled) {
    memcpy(bits, frame->dib, (size_t)w * h * sizeof(uint32_t));
    SelectObject(dc,old);DeleteDC(dc);
    if(frame->display_bitmap)DeleteObject(frame->display_bitmap);
    frame->display_shell_theme=0;frame->display_bitmap=bitmap;frame->display_width=w;frame->display_height=h;return 1;
  }
#endif
  SetStretchBltMode(dc,HALFTONE);SetBrushOrgEx(dc,0,0,NULL);
  if(host_probe_counting)InterlockedIncrement(&host_probe_stretch);
  int copied=StretchDIBits(dc,0,0,w,h,0,0,frame->bitmap.width,frame->bitmap.height,frame->dib,&source,DIB_RGB_COLORS,SRCCOPY);
  SelectObject(dc,old);DeleteDC(dc);
  if(!copied || copied==(int)GDI_ERROR){DeleteObject(bitmap);return 0;}
  if(frame->display_bitmap)DeleteObject(frame->display_bitmap);
#ifdef EXR_READER_WINDOWS_SHELL
  frame->display_shell_theme=0;
#endif
  frame->display_bitmap=bitmap;frame->display_width=w;frame->display_height=h;return 1;
}
static void frame_move(host_frame *dst, host_frame *src) {
  frame_clear(dst);
  *dst = *src;
  memset(src, 0, sizeof(*src));
}

/* Four UI-owned frames. The pixel worker only touches its unpublished job
   frame; UI joins it before accepting or freeing any of those pixels. */
static host_frame page_cache[4];
static unsigned page_cache_next;
static void page_cache_clear(void) { for(int i=0;i<4;i++)frame_clear(&page_cache[i]); }
static int page_cache_find(int64_t book,size_t part,size_t page) {
  for(int i=0;i<4;i++)if(page_cache[i].valid &&
#ifdef EXR_READER_WINDOWS_SHELL
    page_cache[i].shell_epoch == shell_epoch &&
#endif
    page_cache[i].book_id==book && page_cache[i].part==part && page_cache[i].page==page)return i;
  return -1;
}
static void page_cache_put(host_frame *frame) {
  int i=page_cache_find(frame->book_id,frame->part,frame->page);
  if(i<0)i=(int)(page_cache_next++%4);
  frame_move(&page_cache[i],frame);
}
static RECT last_page_rect;
static int last_page_rect_valid;
static int compute_view(void);
static void compose_page_view(HWND window);
static void page_dirty(HWND window,int full) {
#ifdef EXR_READER_WINDOWS_SHELL
  if (shell_active) full = 1; /* the footer changes with every accepted frame */
#endif
  RECT client,dirty,old;GetClientRect(window,&client);dirty=client;
  if(!full && g.frame.valid && g.view.valid) {
    old=last_page_rect_valid?last_page_rect:client;
    if(compute_view()) {
      RECT now={g.view.dx,g.view.dy,g.view.dx+(LONG)(g.frame.bitmap.width*g.view.scale)+2,g.view.dy+(LONG)(g.frame.bitmap.height*g.view.scale)+2};
      UnionRect(&dirty,&old,&now);IntersectRect(&dirty,&dirty,&client);
    }
  }
  compose_page_view(window);
  InvalidateRect(window,&dirty,FALSE);
}
static long wheel_delta;
#define PAGE_WHEEL_TIMER 0x5750
#define PAGE_PREFETCH_TIMER 0x5751
static void book_clear(exr_book *book) {
  free(book->title);
  free(book->author);
  free(book->tags);
  memset(book, 0, sizeof(*book));
}

static int book_copy(exr_book *dst, const exr_book *src) {
  memset(dst, 0, sizeof(*dst));
  *dst = *src;
  dst->title = src->title ? host_strdup(src->title) : NULL;
  dst->author = src->author ? host_strdup(src->author) : NULL;
  dst->tags = src->tags ? host_strdup(src->tags) : NULL;
  if ((src->title && !dst->title) || (src->author && !dst->author) || (src->tags && !dst->tags)) {
    book_clear(dst);
    return 0;
  }
  return 1;
}
static exr_status local_book_copy(int64_t id,exr_book *out,exr_error *error) {
  exr_book *books=NULL;size_t count=0,index;exr_status status;
  memset(out,0,sizeof(*out));EnterCriticalSection(&g.library_lock);
  status=exr_library_books(g.library,"",&books,&count,error);
  if(status==EXR_OK) {
    for(index=0;index<count && books[index].id!=id;index++) {}
    if(index==count) status=EXR_ARGUMENT;
    else if(!book_copy(out,&books[index])) status=EXR_MEMORY;
  }
  exr_books_free(books,count);LeaveCriticalSection(&g.library_lock);return status;
}

static void session_clear(host_session *session) {
  host_probe_require_ui();
  if (session->fixed_document) exr_fixed_free(session->fixed_document);
  if (session->pager) exr_pager_free(session->pager);
  if (session->publication) exr_publication_free(session->publication);
  if (session->document) exr_document_free(session->document);
  memset(session, 0, sizeof(*session));
}

static void selection_clear(void) {
#ifdef EXR_READER_WINDOWS_SHELL
  shell_selection_reset();
#endif
  memset(&g.selection, 0, sizeof(g.selection));
  if (g.page) page_dirty(g.page,1);
}

#ifdef EXR_READER_WINDOWS_PREFERENCES
/* Defined with the other preference state below, after the job record. */
static void prefs_initialize(void);
#endif

#ifdef EXR_READER_WINDOWS_SHELL
#include "windows/shell_style_store.inc"
#endif

/* Settings: host preferences only. Books, progress and annotations live in SQLite. */
static void settings_load(void) {
#ifdef EXR_READER_WINDOWS_SHELL
  shell_tap_edge=GetPrivateProfileIntW(L"Host",L"TapEdge",25,g.settings_path)==20 ? 20:25;
  shell_theme_mode=(int)GetPrivateProfileIntW(L"Host",L"ShellTheme",2,g.settings_path);
  if(shell_theme_mode<0 || shell_theme_mode>2) shell_theme_mode=2;
  int font=(int)GetPrivateProfileIntW(L"Host",L"ShellFont",SHELL_BODY_DEFAULT_FONT,g.settings_path);
  for(size_t i=0;i<sizeof(SHELL_FONT_STEPS)/sizeof(*SHELL_FONT_STEPS);i++)
    if(font==SHELL_FONT_STEPS[i]) shell_font=(float)font;
  shell_style_load();
#endif
  g.font_percent = (int)GetPrivateProfileIntW(L"Host", L"FontPercent", 150, g.settings_path);
  g.zoom_percent = (int)GetPrivateProfileIntW(L"Host", L"ZoomPercent", 100, g.settings_path);
  g.window_width = (int)GetPrivateProfileIntW(L"Host", L"WindowWidth", 1180, g.settings_path);
  g.window_height = (int)GetPrivateProfileIntW(L"Host", L"WindowHeight", 900, g.settings_path);
  g.active_book_id = (int64_t)GetPrivateProfileIntW(L"Host", L"ActiveBook", 0, g.settings_path);
  if (g.font_percent < HOST_FONT_MIN || g.font_percent > HOST_FONT_MAX) g.font_percent = 150;
  if (g.zoom_percent < HOST_ZOOM_MIN || g.zoom_percent > HOST_ZOOM_MAX) g.zoom_percent = 100;
  if (g.window_width < 900) g.window_width = 900;
  if (g.window_height < 600) g.window_height = 600;
#ifdef EXR_READER_PRODUCT_CATALOG
  wchar_t query[257],key[73];
  GetPrivateProfileStringW(L"Shelf",L"Query",L"",query,257,g.settings_path);g.shelf_query=host_utf8(query);
  GetPrivateProfileStringW(L"Shelf",L"TopKey",L"",key,73,g.settings_path);
  char *utf8=host_utf8(key);if(utf8 && strlen(utf8)<sizeof(g.shelf_top_key)) strcpy(g.shelf_top_key,utf8);free(utf8);
  GetPrivateProfileStringW(L"Shelf",L"SelectedKey",L"",key,73,g.settings_path);
  utf8=host_utf8(key);if(utf8 && strlen(utf8)<sizeof(g.shelf_selected_key)) strcpy(g.shelf_selected_key,utf8);free(utf8);
#ifdef EXR_READER_WINDOWS_TXT_PROGRESS
  GetPrivateProfileStringW(L"Host",L"ActiveTxtKey",L"",key,73,g.settings_path);
  utf8=host_utf8(key);
  if(utf8 && strlen(utf8)==68 && !strncmp(utf8,"txt:",4)) strcpy(g.active_txt_key,utf8);
  free(utf8);
#endif
#endif
#ifdef EXR_READER_WINDOWS_PREFERENCES
  /* Bounded local read of the installed F3 record; no SDK work here. */
  prefs_initialize();
#endif
}

static void settings_write(const wchar_t *section,const wchar_t *key,const wchar_t *value,const wchar_t *path) {
  wchar_t previous[512];
  DWORD length=GetPrivateProfileStringW(section,key,L"",previous,512,path);
  /* Page turns usually change no setting. Preserve missing/empty keys and long
     values; only skip writes when the complete existing value is identical. */
  if(length && length<511 && !wcscmp(previous,value)) return;
  WritePrivateProfileStringW(section,key,value,path);
}
static void settings_save(void) {
  wchar_t number[64];
  if (!g.settings_path[0]) return;
#ifdef EXR_READER_WINDOWS_SHELL
  swprintf(number,64,L"%d",shell_tap_edge);
  settings_write(L"Host",L"TapEdge",number,g.settings_path);
  swprintf(number,64,L"%d",shell_theme_mode);
  settings_write(L"Host",L"ShellTheme",number,g.settings_path);
  swprintf(number,64,L"%.0f",(double)shell_font);
  settings_write(L"Host",L"ShellFont",number,g.settings_path);
  if(!shell_style_save()) set_status(L"阅读样式保存失败，原 shelf.json 已保留。");
#endif
#ifdef EXR_READER_PRODUCT_CATALOG
  product_shelf_remember();
  wchar_t *query=host_wide(g.shelf_query ? g.shelf_query:"",g.shelf_query ? strlen(g.shelf_query):0);
  settings_write(L"Shelf",L"Query",query ? query:L"",g.settings_path);free(query);
  wchar_t *key=host_wide(g.shelf_top_key,strlen(g.shelf_top_key));
  settings_write(L"Shelf",L"TopKey",key ? key:L"",g.settings_path);free(key);
  key=host_wide(g.shelf_selected_key,strlen(g.shelf_selected_key));
  settings_write(L"Shelf",L"SelectedKey",key ? key:L"",g.settings_path);free(key);
#endif
  swprintf(number, 64, L"%d", g.font_percent);
  settings_write(L"Host", L"FontPercent", number, g.settings_path);
  swprintf(number, 64, L"%d", g.zoom_percent);
  settings_write(L"Host", L"ZoomPercent", number, g.settings_path);
  swprintf(number, 64, L"%d", g.window_width);
  settings_write(L"Host", L"WindowWidth", number, g.settings_path);
  swprintf(number, 64, L"%d", g.window_height);
  settings_write(L"Host", L"WindowHeight", number, g.settings_path);
  swprintf(number, 64, L"%lld", (long long)g.active_book_id);
  settings_write(L"Host", L"ActiveBook", number, g.settings_path);
#ifdef EXR_READER_WINDOWS_TXT_PROGRESS
  {
    wchar_t *key=host_wide(g.active_txt_key,strlen(g.active_txt_key));
    settings_write(L"Host",L"ActiveTxtKey",key ? key:L"",g.settings_path);
    free(key);
  }
#endif
}

/* ------------------------------------------------------------------ */
/* Bookshelf and annotation snapshots                                  */
/* ------------------------------------------------------------------ */

#ifdef EXR_READER_WINDOWS_SHELL
static void sm_refresh(void);
static void sm_show(int mode);
static void sm_activity(void);
static void sm_landed(int opened);
static HWND sm_view;
static void sm_tick(void);
static void sm_shelf_visibility(int show);
static void opds_create(HWND parent);
static void opds_layout(void);
static void opds_show(void);
static volatile LONG opds_busy;
static void sm_edit_open(int shelf);
static const char *sm_title(size_t shelf);
static const char *sm_author(size_t shelf);
#endif
static void shelf_clear(void) {
#ifdef EXR_READER_PRODUCT_CATALOG
  if(g.shelf_cursors) for(size_t i=0;i<g.shelf_count;i++) {
    free(g.shelf_cursors[i].key);free(g.shelf_cursors[i].sort_title);
  }
  free(g.shelf_cursors);g.shelf_cursors=NULL;
#endif
  if (g.shelf) exr_books_free(g.shelf, g.shelf_count);
  g.shelf = NULL;
  g.shelf_count = 0;
}

static void notes_clear(void) {
  if (g.epub_notes) exr_epub_notes_free(g.epub_notes, g.epub_note_count);
  g.epub_notes = NULL; g.epub_note_count = 0;
  if (g.reflow_notes) exr_notes_free(g.reflow_notes, g.reflow_note_count);
  if (g.fixed_notes) exr_fixed_notes_free(g.fixed_notes, g.fixed_note_count);
  g.reflow_notes = NULL;
  g.reflow_note_count = 0;
  g.fixed_notes = NULL;
  g.fixed_note_count = 0;
  g.notes_book_id = 0;
}

static size_t current_note_count(void) {
  return g.session.fixed ? g.fixed_note_count : g.session.bounded ? g.epub_note_count : g.reflow_note_count;
}

static void truncate_utf8(char *out, size_t capacity, const char *text, size_t bytes) {
  size_t n = bytes;
  if (!capacity) return;
  if (!text) { out[0] = 0; return; }
  if (n > capacity - 1) n = capacity - 1;
  while (n && ((unsigned char)text[n] & 0xc0) == 0x80) n--;
  memcpy(out, text, n);
  out[n] = 0;
}

static void shelf_display(const exr_book *book, wchar_t *out, size_t capacity) {
  const wchar_t *mark = (g.has_current && g.current.id == book->id) ? L" · 当前" : L"";
  wchar_t *title = book->title ? host_wide(book->title, strlen(book->title)) : NULL;
  wchar_t *author = book->author ? host_wide(book->author, strlen(book->author)) : NULL;
#ifdef EXR_READER_PRODUCT_CATALOG
  if(g.shelf_cursors) swprintf(out,capacity,L"《%ls》 — %ls · %ls%ls%ls",title ? title:L"Untitled",
    author && author[0] ? author:L"未知作者",format_name(book->format),book->id || book->format==EXR_TXT ? L"":L" · 阅读尚未支持",mark);
  else
#endif
  if (is_fixed_format(book->format))
    swprintf(out, capacity, L"《%ls》 — %ls · %ls · 第 %llu 页%ls",
             title ? title : L"Untitled",
             author && author[0] ? author : L"未知作者",
             format_name(book->format), (unsigned long long)(book->position + 1), mark);
  else
    swprintf(out, capacity, L"《%ls》 — %ls · %ls · 偏移 %llu%ls",
             title ? title : L"Untitled",
             author && author[0] ? author : L"未知作者",
             format_name(book->format), (unsigned long long)book->position, mark);
  out[capacity - 1] = 0;
  free(title);
  free(author);
}

static exr_status reload_shelf(void) {
#ifdef EXR_READER_PRODUCT_CATALOG
  product_shelf_remember();
#endif
  exr_book *books = NULL;
  size_t count = 0;
  exr_error error = {0};
  exr_status status;
  size_t i;
  EnterCriticalSection(&g.library_lock);
#ifdef EXR_HOST_WORKER_REVIEW
  if (review_query_failure(2)) status = EXR_DATABASE;
  else
#endif
  status = exr_library_books(g.library, "", &books, &count, &error);
  LeaveCriticalSection(&g.library_lock);
  if (status != EXR_OK) {
    wchar_t message[512];
    describe_error(message, 512, L"读取书架失败", status, &error);
    set_status(message);
    return status;
  }
#ifdef EXR_READER_PRODUCT_CATALOG
  if(count>50) {
    exr_book *bounded=calloc(50,sizeof(*bounded));
    if(!bounded) { exr_books_free(books,count);return EXR_MEMORY; }
    for(i=0;i<50;i++) { bounded[i]=books[i];memset(&books[i],0,sizeof(*books)); }
    exr_books_free(books,count);books=bounded;count=50;
  }
#endif
  shelf_clear();
  g.shelf = books;
  g.shelf_count = count;
  if (g.books) {
#ifdef EXR_READER_PRODUCT_CATALOG
    product_shelf_snapshot_changed();
#endif
    SendMessageW(g.books, LB_RESETCONTENT, 0, 0);
    for (i = 0; i < count; i++) {
      wchar_t line[512];
      shelf_display(&books[i], line, 512);
      SendMessageW(g.books, LB_ADDSTRING, 0, (LPARAM)line);
    }
#ifdef EXR_READER_PRODUCT_CATALOG
    product_shelf_snapshot_changed();
#endif
  }
#ifdef EXR_READER_WINDOWS_SHELL
  sm_refresh();
#endif
  return EXR_OK;
}

static int shelf_index(int64_t id) {
  size_t i;
  for (i = 0; i < g.shelf_count; i++)
    if (g.shelf[i].id == id) return (int)i;
  return -1;
}

#ifdef EXR_READER_TEST_DRIVERS
static int shelf_index_for_title(const wchar_t *needle) {
  size_t i;
  if (!needle || !needle[0]) return -1;
  for (i = 0; i < g.shelf_count; i++) {
    wchar_t *title = host_wide(g.shelf[i].title ? g.shelf[i].title : "",
                               g.shelf[i].title ? strlen(g.shelf[i].title) : 0);
    int match = title && wcsstr(title, needle) != NULL;
    free(title);
    if (match) return (int)i;
  }
  return -1;
}
#endif

static exr_status reload_notes(void) {
  exr_error error = {0};
  exr_status status = EXR_OK;
  exr_note *reflow = NULL;
  exr_epub_note *epub = NULL;
  exr_fixed_note *fixed = NULL;
  size_t count = 0;
  if (!g.has_current || !g.session.active || g.session.txt) {
    notes_clear();
    if (g.notes) SendMessageW(g.notes, LB_RESETCONTENT, 0, 0);
    return EXR_OK;
  }
  EnterCriticalSection(&g.library_lock);
#ifdef EXR_HOST_WORKER_REVIEW
  if (review_query_failure(1)) status = EXR_DATABASE;
  else
#endif
  if (g.session.fixed)
    status = exr_library_fixed_notes(g.library, g.current.id, &fixed, &count, &error);
  else if (g.session.bounded)
    status = exr_library_epub_notes(g.library, g.current.id, &epub, &count, &error);
  else
    status = exr_library_notes(g.library, g.current.id, &reflow, &count, &error);
  LeaveCriticalSection(&g.library_lock);
  if (status != EXR_OK) {
    wchar_t message[512];
    if (g.notes_book_id != g.current.id) {
      notes_clear();
      if (g.notes) SendMessageW(g.notes, LB_RESETCONTENT, 0, 0);
    }
    describe_error(message, 512, L"读取标注失败", status, &error);
    set_status(message);
    return status;
  }
  notes_clear();
  g.notes_book_id = g.current.id;
  g.reflow_notes = reflow; g.fixed_notes = fixed;
  g.epub_notes = epub;
  if (g.session.fixed) g.fixed_note_count = count;
  else if (g.session.bounded) g.epub_note_count = count;
  else g.reflow_note_count = count;
  if (g.notes) {
    size_t i;
    SendMessageW(g.notes, LB_RESETCONTENT, 0, 0);
    for (i = 0; i < current_note_count(); i++) {
      wchar_t line[512];
      char quote[128];
      char comment[128];
      wchar_t *wquote;
      wchar_t *wcomment;
      if (g.session.fixed) {
        const exr_fixed_note *note = &g.fixed_notes[i];
        truncate_utf8(quote, sizeof(quote), note->anchor.exact, note->anchor.exact_size);
        truncate_utf8(comment, sizeof(comment), note->text, note->text ? strlen(note->text) : 0);
        wquote = host_wide(quote, strlen(quote));
        wcomment = host_wide(comment, strlen(comment));
        swprintf(line, 512, L"[第 %llu 页] %ls — %ls",
                 (unsigned long long)(note->page + 1), wquote ? wquote : L"", wcomment ? wcomment : L"");
      } else if (g.session.bounded) {
        const exr_epub_note *note = &g.epub_notes[i];
        truncate_utf8(quote, sizeof(quote), note->location.selector.exact,
                      note->location.selector.exact ? strlen(note->location.selector.exact) : 0);
        truncate_utf8(comment, sizeof(comment), note->text, note->text ? strlen(note->text) : 0);
        wquote = host_wide(quote, strlen(quote)); wcomment = host_wide(comment, strlen(comment));
        swprintf(line, 512, L"[章 %llu · 待解析] %ls — %ls",
                 (unsigned long long)(note->location.part + 1), wquote ? wquote : L"", wcomment ? wcomment : L"");
      } else {
        const exr_note *note = &g.reflow_notes[i];
        truncate_utf8(quote, sizeof(quote), note->anchor.exact,
                      note->anchor.exact ? strlen(note->anchor.exact) : 0);
        truncate_utf8(comment, sizeof(comment), note->text, note->text ? strlen(note->text) : 0);
        wquote = host_wide(quote, strlen(quote));
        wcomment = host_wide(comment, strlen(comment));
        if (note->start == SIZE_MAX)
          swprintf(line, 512, L"[未定位] %ls — %ls", wquote ? wquote : L"", wcomment ? wcomment : L"");
        else
          swprintf(line, 512, L"[偏移 %llu] %ls — %ls",
                   (unsigned long long)note->start, wquote ? wquote : L"", wcomment ? wcomment : L"");
      }
      free(wquote);
      free(wcomment);
      SendMessageW(g.notes, LB_ADDSTRING, 0, (LPARAM)line);
    }
  }
  return EXR_OK;
}

static int notes_selected(void) {
  LRESULT index;
  if (!g.notes) return -1;
  index = SendMessageW(g.notes, LB_GETCURSEL, 0, 0);
  if (index == LB_ERR) return -1;
  if ((size_t)index >= current_note_count()) return -1;
  return (int)index;
}

static int note_comment_read(char *out, size_t capacity) {
  wchar_t wide[65536];
  int length;
  char *utf8;
  out[0] = 0;
  if (!g.note_edit) return 1;
  if (GetWindowTextLengthW(g.note_edit) > 65535) {
    set_status(L"批注超出长度上限，未保存。"); return 0;
  }
  length = GetWindowTextW(g.note_edit, wide, 65536);
  if (length <= 0) return 1;
  wide[length] = 0;
  utf8 = host_utf8(wide);
  if (!utf8) { set_status(L"批注包含无效文字，未保存。"); return 0; }
  if (strlen(utf8) >= capacity) {
    free(utf8); set_status(L"批注 UTF-8 超出 65535 字节上限，未保存。"); return 0;
  }
  strcpy(out, utf8);
  free(utf8);
  return 1;
}

static void note_comment_write(const char *utf8) {
  wchar_t *wide = utf8 ? host_wide(utf8, strlen(utf8)) : NULL;
  if (g.note_edit) SetWindowTextW(g.note_edit, wide ? wide : L"");
  free(wide);
}

/* ------------------------------------------------------------------ */
/* Jobs: one SDK-owning worker at a time                               */
/* ------------------------------------------------------------------ */

enum { JOB_NONE = 0, JOB_OPEN, JOB_GO, JOB_LAYOUT, JOB_IMPORT, JOB_NOTE_ADD, JOB_NOTE_UPDATE, JOB_ROLLBACK, JOB_HIT, JOB_SAVE,
  JOB_PRODUCT_ATTACH, JOB_PRODUCT_REPAIR, JOB_PRODUCT_DELETE, JOB_PRODUCT_SHELF,
  JOB_METADATA_PREPARE, JOB_METADATA_SAVE, JOB_METADATA_RETRY, JOB_METADATA_DISCARD,
  JOB_ACCOUNT_LOAD, JOB_ACCOUNT_SET, JOB_ACCOUNT_FORGET, JOB_ACCOUNT_STAGE, JOB_ACCOUNT_RECEIVE,
  JOB_SEARCH_BATCH, JOB_SEARCH_OPEN, JOB_NAVIGATION_ROWS, JOB_NAVIGATION_OPEN, JOB_RECORDS, JOB_IMPORT_ORGANIZE,
  JOB_PREFERENCES, JOB_WAVE3, JOB_PREFETCH
#ifdef EXR_READER_WINDOWS_TXT_PROGRESS
  , JOB_TXT_PROGRESS
#endif
  };
#ifdef EXR_READER_WINDOWS_ACCOUNT
static int account_job_kind(int kind) { return kind>=JOB_ACCOUNT_LOAD && kind<=JOB_ACCOUNT_RECEIVE; }
#endif
#ifdef EXR_READER_DESKTOP_METADATA
static int metadata_job_kind(int kind) { return kind>=JOB_METADATA_PREPARE && kind<=JOB_METADATA_DISCARD; }
#endif
static int job_commit_barrier(int kind);
#ifdef EXR_READER_PRODUCT_CATALOG
static int product_job_kind(int kind) {
  return kind==JOB_PRODUCT_ATTACH || kind==JOB_PRODUCT_REPAIR || kind==JOB_PRODUCT_DELETE || kind==JOB_PRODUCT_SHELF;
}
#endif

struct host_job {
#ifdef EXR_READER_WINDOWS_IMPORT_ORGANIZE
  winio_job *io;
#endif
  LONG refs;
#ifdef EXR_READER_WINDOWS_SHELL
  shell_geometry shell_geometry;
  unsigned long shell_epoch;
  int shell_toc_jump, shell_search_jump, shelf_restored;
#endif
  volatile LONG cancel;
  int kind;
  int64_t book_id;
  wchar_t path[HOST_PATH];
  size_t target_page;
  size_t target_part;
  char *part_path;
  unsigned long generation, gesture;
  float hit_x, hit_y;
  size_t hit_offset;
  int hit_down, hit_up;
  size_t target_offset;
  int use_offset;
  int direction;
  int batch_delta;
  int font_percent;
  int zoom_percent;
  exr_anchor anchor;
  int has_anchor;
  int anchor_host_owned;
  HANDLE thread;
  exr_status status;
  exr_error error;
  host_frame frame;
  int have_frame;
  int at_end;
  int imported;
  int created;
  int64_t imported_id;
  size_t page_count;
  size_t applied_page;
  wchar_t message[512];
  volatile LONG progress;
  int session_swapped;
  host_session candidate;
  exr_book opened_book;
  exr_pager *candidate_pager;
  exr_layout_config candidate_config;
  char *comment;
  int64_t note_id;
  size_t note_start, note_end;
  int rollback_failed;
  int note_fixed;
  int resolved_selection;
#ifdef EXR_READER_WINDOWS_RECORDS
  volatile LONG records_durable;
  unsigned long records_generation;
  int records_action,records_kind,records_operation,records_progress;
  char records_annotation[33],records_head[33],records_sha[65],records_version[33],records_after[33],records_pending[33];
  char *records_body;
  winrecords_response records;
#endif
#ifdef EXR_READER_WINDOWS_SEARCH
  char *search_query;
  unsigned long search_generation;
  reader_search_cursor search_resume;
#ifdef EXR_READER_WINDOWS_TXT_PROGRESS
  host_txt_search_cursor search_txt_resume;
#endif
  int search_has_resume;
  host_search_batch search_batch;
  host_search_hit search_hit;
#if defined(EXR_READER_WINDOWS_TXT_PROGRESS) && defined(EXR_READER_WINDOWS_WAVE3)
  size_t txt_history_origin;
  exr_anchor txt_history_before, txt_history_after;
  int txt_history_ready, txt_history_failed;
#endif
#endif
#ifdef EXR_READER_WINDOWS_NAVIGATION
  unsigned long navigation_generation;
  uint64_t navigation_parent,navigation_first,navigation_row,navigation_explicit_part;
  size_t navigation_depth;
  int navigation_accept_part;
  host_navigation_result navigation;
#endif
#ifdef EXR_READER_PRODUCT_CATALOG
  int product_auto_open,product_deleted;
#ifdef EXR_READER_WINDOWS_TXT_RECOVERY
  int original_import,original_recovery_failed;
#endif
  int product_shelf_direction,product_shelf_before,product_shelf_after;
  char product_group_id[33];int product_group_kind;uint64_t product_cursor_ordinal;int product_anchor_predecessor;
  unsigned long product_shelf_generation;
  char *product_shelf_query,*product_cursor_title,*product_cursor_key,*product_anchor_key;
  exr_book *product_books;size_t product_book_count;
  char product_key[READER_BOOK_KEY_CAPACITY];
  host_shelf_cursor *product_cursors;
#endif
#if defined(EXR_READER_WINDOWS_TXT_PROGRESS) || defined(EXR_READER_WINDOWS_SHELL)
  uint64_t txt_offset;
#endif
#ifdef EXR_READER_WINDOWS_TXT_PROGRESS
  /* Copied values for one TXT position write; the worker never reads UI state. */
  char txt_key[73];
  char txt_context[READER_TXP_CONTEXT_BYTES + 1];
  size_t txt_context_bytes;
  uint64_t txt_saved_offset;
  int txt_saved_valid;
#endif
#ifdef EXR_READER_DESKTOP_METADATA
  reader_metadata_snapshot *metadata_snapshot;
  wchar_t *metadata_title_value,*metadata_author_value;
  wchar_t *metadata_input_title,*metadata_input_author;
  char metadata_key[72];
  int metadata_favorite,metadata_conflict,metadata_has_view,metadata_has_pending,metadata_committed;
#endif
#ifdef EXR_READER_WINDOWS_ACCOUNT
  int account_action,account_remember;
  char *account_root,*account_user,*account_password;
#endif
#ifdef EXR_READER_WINDOWS_PREFERENCES
  reader_preferences prefs;
  int prefs_valid,prefs_persist,system_theme;
  volatile LONG prefs_committed;
#endif
#ifdef EXR_READER_WINDOWS_WAVE3
  w3_job *w3;
#endif
};

static int job_commit_barrier(int kind) {
  return kind==JOB_SAVE
#ifdef EXR_READER_WINDOWS_TXT_PROGRESS
    || kind==JOB_TXT_PROGRESS
#endif
#ifdef EXR_READER_DESKTOP_METADATA
    || metadata_job_kind(kind)
#endif
#ifdef EXR_READER_WINDOWS_RECORDS
    || (kind==JOB_RECORDS&&g.job&&InterlockedCompareExchange(&g.job->records_durable,0,0))
#endif
  ;
}

static int job_cancel_flag(host_job *job) {
  return job && InterlockedCompareExchange((volatile LONG *)&job->cancel, 0, 0) != 0;
}
static int job_preferences_committed(host_job *job) {
#if defined(EXR_READER_WINDOWS_PREFERENCES) && !defined(EXR_PREFS_OLD_CANCEL_VETO_CONTROL)
  return job && InterlockedCompareExchange(&job->prefs_committed, 0, 0) != 0;
#else
  (void)job;
  return 0;
#endif
}
#ifdef EXR_HOST_WORKER_REVIEW
#include EXR_HOST_WORKER_REVIEW_HEADER
#define OFFSET_GET(pager,index,out,error) review_offset_get(pager,index,out,error)
#else
#define OFFSET_GET(pager,index,out,error) exr_pager_get(pager,index,out,error)
#endif

static int job_cancel_check(void *context) {
  return job_cancel_flag((host_job *)context);
}

/* Long-lived pager configs must not retain a job pointer: completed jobs are
   freed. This callback always consults the current serialized job instead. */
static int host_cancel_check(void *context) {
  (void)context;
  return g.job ? job_cancel_flag(g.job) : 0;
}

#ifdef EXR_READER_WINDOWS_PREFERENCES
/* Colour helpers, the bounded store and the F3 navigation values. This file
   never creates an SDK object and never touches the worker. */
#include "../apps/reader/desktop/windows_preferences_state.inc"
#endif

static void job_pause(host_job *job) {
  int remaining = g.delay_ms;
  while (remaining > 0 && !job_cancel_flag(job)) {
    int slice = remaining > 10 ? 10 : remaining;
    Sleep((DWORD)slice);
    remaining -= slice;
  }
}

static host_job *job_new(int kind) {
  host_job *job = calloc(1, sizeof(*job));
  if (!job) return NULL;
  job->refs = 1;
  job->kind = kind;
  job->zoom_percent = g.zoom_percent;
#ifdef EXR_READER_WINDOWS_SHELL
  job->shell_geometry = shell_snapshot();
  job->shell_epoch = shell_epoch;
#endif
#ifdef EXR_READER_WINDOWS_PREFERENCES
  /* Immutable value snapshot: the worker never reads the owner's record. */
  prefs_job_init(job);
#endif
  return job;
}
/* A dialog may also be opened over the compact shelf while a book remains
   loaded. Restore focus to a currently operable surface, never a hidden page. */
#if defined(EXR_READER_WINDOWS_SEARCH) || defined(EXR_READER_WINDOWS_NAVIGATION) || defined(EXR_READER_WINDOWS_RECORDS) || defined(EXR_READER_WINDOWS_PREFERENCES)
static void host_restore_content_focus(void) {
  HWND targets[] = {g.page, g.books};
  if (g.closing) return;
  for (size_t i = 0; i < sizeof(targets) / sizeof(targets[0]); i++) {
    if (targets[i] && IsWindowVisible(targets[i]) && IsWindowEnabled(targets[i])) {
      SetFocus(targets[i]); return;
    }
  }
}
#endif

static int host_work_area(HWND window, RECT *area) {
  MONITORINFO info = {0}; info.cbSize = sizeof(info);
  HMONITOR monitor = MonitorFromWindow(window, MONITOR_DEFAULTTOPRIMARY);
  if (!monitor || !GetMonitorInfoW(monitor, &info)) return 0;
  *area = info.rcWork;
  return area->right > area->left && area->bottom > area->top;
}

static void host_fit_work_area(HWND window) {
  RECT bounds, area;
  if (!GetWindowRect(window, &bounds) || !host_work_area(window, &area)) return;
  int width = bounds.right - bounds.left, height = bounds.bottom - bounds.top;
  int available_width = area.right - area.left, available_height = area.bottom - area.top;
  if (width > available_width) width = available_width;
  if (height > available_height) height = available_height;
  int x = bounds.left, y = bounds.top;
  if (x + width > area.right) x = area.right - width;
  if (y + height > area.bottom) y = area.bottom - height;
  if (x < area.left) x = area.left;
  if (y < area.top) y = area.top;
  SetWindowPos(window, NULL, x, y, width, height, SWP_NOZORDER | SWP_NOACTIVATE);
}

#ifdef EXR_READER_WINDOWS_SEARCH
static void winsearch_hit_free(host_search_hit *hit);
static void winsearch_batch_free(host_search_batch *batch);
static exr_status winsearch_job(host_job *job);
static void winsearch_accept(host_job *job);
static void winsearch_close(void);
#endif
#if defined(EXR_READER_WINDOWS_SEARCH) || defined(EXR_READER_WINDOWS_NAVIGATION) || defined(EXR_READER_WINDOWS_RECORDS)
static exr_status winreader_identity(int64_t book,exr_format format,int fixed,int bounded,
  char out[256],const exr_control *control,exr_error *error);
#endif
#ifdef EXR_READER_WINDOWS_NAVIGATION
static void winnav_result_free(host_navigation_result *result);
static exr_status winnav_job(host_job *job);
static void winnav_accept(host_job *job);
static void winnav_close(void);
#endif
#ifdef EXR_READER_WINDOWS_RECORDS
static exr_status winrecords_job(host_job *job);
static void winrecords_accept(host_job *job);
static void winrecords_close(void);
#endif
#ifdef EXR_READER_WINDOWS_WAVE3
static void w3_job_free(w3_job *job);
static exr_status w3_run(host_job *job);
#ifdef EXR_READER_WINDOWS_RAW3
static exr_status w3_prepare_open(host_job *job, const exr_book *book, exr_error *error);
#endif
static void w3_failed_to_start(host_job *job);
#endif

static void job_free(host_job *job) {
  host_probe_require_ui();
  if (!job) return;
#ifdef EXR_READER_WINDOWS_WAVE3
  w3_job_free(job->w3);
#endif
#ifdef EXR_READER_WINDOWS_IMPORT_ORGANIZE
  winio_job_free(job->io);
#endif
#ifdef EXR_READER_WINDOWS_RECORDS
  free(job->records_body);winrecords_response_free(&job->records);
#endif
#ifdef EXR_READER_WINDOWS_SEARCH
  free(job->search_query);
  winsearch_hit_free(&job->search_hit);
  winsearch_batch_free(&job->search_batch);
#if defined(EXR_READER_WINDOWS_TXT_PROGRESS) && defined(EXR_READER_WINDOWS_WAVE3)
  exr_anchor_free(&job->txt_history_before);
  exr_anchor_free(&job->txt_history_after);
#endif
#endif
#ifdef EXR_READER_WINDOWS_NAVIGATION
  winnav_result_free(&job->navigation);
#endif
#ifdef EXR_READER_DESKTOP_METADATA
  reader_metadata_snapshot_free(job->metadata_snapshot);
  free(job->metadata_title_value);free(job->metadata_author_value);
  free(job->metadata_input_title);free(job->metadata_input_author);
#endif
#ifdef EXR_READER_WINDOWS_ACCOUNT
  free(job->account_root);
  if(job->account_user) { SecureZeroMemory(job->account_user,strlen(job->account_user));free(job->account_user); }
  if(job->account_password) { SecureZeroMemory(job->account_password,strlen(job->account_password));free(job->account_password); }
#endif
#ifdef EXR_READER_PRODUCT_CATALOG
  if(job->product_cursors) for(size_t i=0;i<job->product_book_count;i++) {
    free(job->product_cursors[i].key);free(job->product_cursors[i].sort_title);
  }
  free(job->product_cursors);exr_books_free(job->product_books,job->product_book_count);
  free(job->product_shelf_query);free(job->product_cursor_title);free(job->product_cursor_key);free(job->product_anchor_key);
#endif
  if (job->thread) CloseHandle(job->thread);
  frame_clear(&job->frame);
  if (job->has_anchor) {
    if (job->anchor_host_owned) {
      free(job->anchor.exact); free(job->anchor.prefix); free(job->anchor.suffix); free(job->anchor.chapter);
    } else exr_anchor_free(&job->anchor);
  }
  session_clear(&job->candidate);
  book_clear(&job->opened_book);
  exr_pager_free(job->candidate_pager);
  free(job->comment);
  free(job->part_path);
  free(job);
}

static void job_release(host_job *job) {
  if (!job) return;
  if (InterlockedDecrement(&job->refs) == 0) job_free(job);
}

static void host_update_controls(void);
static unsigned __stdcall job_thread(void *context);
static exr_status job_run(host_job *job);
#ifdef EXR_READER_DESKTOP_METADATA
static void metadata_failed_to_start(host_job *job);
#endif

static void job_start_failed(host_job *job) {
#ifdef EXR_READER_PRODUCT_CATALOG
    if(product_job_kind(job->kind)) g.product_pending=1;
#endif
    g.job = NULL;
    job->status = EXR_MEMORY;
    strcpy(job->error.message, "Cannot create host worker thread");
#ifdef EXR_READER_WINDOWS_WAVE3
    w3_failed_to_start(job);
#endif
#ifdef EXR_READER_DESKTOP_METADATA
    if(metadata_job_kind(job->kind)) metadata_failed_to_start(job);
#endif
    job_release(job);
    set_status(L"无法创建后台任务线程。");
    host_update_controls();
}

static void job_start(host_job *job) {
  host_probe_require_ui();
#ifdef EXR_READER_WINDOWS_SHELL
  if(job->kind==JOB_OPEN) {tts_stop();dict_close_all();}
#endif
  if(job->kind==JOB_OPEN || job->kind==JOB_LAYOUT || job->kind==JOB_IMPORT || job->kind==JOB_PREFERENCES || job->kind==JOB_PRODUCT_DELETE || (job->zoom_percent>0 && job->zoom_percent!=g.zoom_percent))page_cache_clear();
  g.job = job;
  if (job->kind != JOB_HIT && job->kind != JOB_SAVE && job->kind != JOB_PREFETCH && job->kind != JOB_IMPORT_ORGANIZE
#ifdef EXR_READER_WINDOWS_WAVE3
      && job->kind != JOB_WAVE3
#endif
#ifdef EXR_READER_WINDOWS_SEARCH
      && job->kind != JOB_SEARCH_BATCH
#endif
#ifdef EXR_READER_WINDOWS_NAVIGATION
      && job->kind != JOB_NAVIGATION_ROWS
#endif
#ifdef EXR_READER_WINDOWS_RECORDS
      && job->kind != JOB_RECORDS
#endif
#ifdef EXR_READER_PRODUCT_CATALOG
      && !product_job_kind(job->kind)
#endif
#ifdef EXR_READER_DESKTOP_METADATA
      && !metadata_job_kind(job->kind)
#endif
#ifdef EXR_READER_WINDOWS_ACCOUNT
      && !account_job_kind(job->kind)
#endif
  ) {
#ifdef EXR_READER_WINDOWS_SHELL
  if (shell_active && select_valid && (job->kind == JOB_GO || job->kind == JOB_LAYOUT)) {
    /* Content selection survives page turns and geometry-only reflow. */
  } else {
    shell_selection_reset();
#endif
  dragging = 0;
  g.hit_pending = 0; g.gesture++;
  if (GetCapture() == g.page) ReleaseCapture();
  memset(&g.selection, 0, sizeof(g.selection));
#ifdef EXR_READER_WINDOWS_SHELL
  }
#endif
  /* Keep the accepted page visible until the new frame is ready. */
  }
  if (!PostMessageW(g.window, WM_HOST_SDK_JOB, 0, (LPARAM)job)) job_start_failed(job);
  else host_update_controls();
}

static void job_launch_pixels(host_job *job) {
#if defined(EXR_READER_WINDOWS_SHELL) && !defined(EXR_HOST_WORKER_REVIEW)
  /* A prefetched native-size DIB is already prepared. Keep the same UI accept
     queue, without starting and joining a worker that would immediately return. */
  if(!g.delay_ms && job->kind==JOB_GO && job->status==EXR_OK && job->frame.valid &&
     job->frame.shell_geometry.enabled && job->frame.display_bitmap &&
     job->frame.display_width==(int)job->frame.bitmap.width &&
     job->frame.display_height==(int)job->frame.bitmap.height) {
    host_probe_log("pixel_reused",1);
    host_probe_log("frame_ready_gen",(double)job->frame.generation);
    PostMessageW(g.window,WM_HOST_COMPLETE,0,(LPARAM)job);
    return;
  }
#endif
  unsigned thread_id=0;
  uintptr_t handle=_beginthreadex(NULL,0,job_thread,job,0,&thread_id);
  if(!handle) {
    /* SDK transactions already ran on UI; retain their result if pixels
       cannot get a worker, instead of reporting a false SDK failure. */
    if(job->status==EXR_OK && job->frame.valid)frame_prepare_display(&job->frame);
    PostMessageW(g.window,WM_HOST_COMPLETE,0,(LPARAM)job);return;
  }
  job->thread=(HANDLE)handle;
  host_update_controls();
}

static void job_supersede(void) {
  if(g.job&&job_commit_barrier(g.job->kind)) return;
  if (g.pending) {
    job_release(g.pending);
    g.pending = NULL;
  }
  if (g.job) {
    InterlockedExchange(&g.job->cancel, 1);
    set_status(L"正在取消上一个任务…");
  }
}

static void job_submit(host_job *job) {
  if (!job) return;
  if (g.closing) {
    job_release(job);
    return;
  }
  if (g.job) {
#ifdef EXR_READER_WINDOWS_RECORDS
    if(g.job->kind==JOB_RECORDS&&job_commit_barrier(g.job->kind)) {
      job_release(job);set_status(L"正在确认已保存的阅读请求，完成后可继续操作。");return;
    }
#endif
#ifdef EXR_READER_DESKTOP_METADATA
    if(metadata_job_kind(g.job->kind)) {
      job_release(job);set_status(L"正在提交书籍编辑，完成后可继续操作。");return;
    }
#endif
    if (g.job->kind != JOB_SAVE) job_supersede();
    else if (g.pending) { job_release(g.pending); g.pending = NULL; }
    g.pending = job;
    host_update_controls();
    return;
  }
  job_start(job);
}

static inline void job_cancel_button(void) {
  if (g.pending) {
    job_release(g.pending);
    g.pending = NULL;
  }
  if (g.job) {
    if (job_commit_barrier(g.job->kind)) { set_status(L"正在保存已接受的操作，完成后可继续操作。"); return; }
    InterlockedExchange(&g.job->cancel, 1);
    set_status(L"已请求取消，等待当前任务释放 SDK 句柄…");
  } else {
    set_status(L"当前没有可取消的任务。");
  }
}

/* ------------------------------------------------------------------ */
/* Sessions and rendering                                              */
/* ------------------------------------------------------------------ */

static void session_configure(host_session *session, host_job *job) {
  /* exr_layout_options.font_size is a point size, not a scale: the preserved
     self-test uses 28 points with 1.5 line height. Percent maps onto that base. */
  int font_percent = (job && job->font_percent > 0) ? job->font_percent : g.font_percent;
  session->config = exr_layout_config_defaults();
  session->config.page.width = 720;
  session->config.page.height = 1040;
#ifdef EXR_READER_WINDOWS_SHELL
  session->shell_geometry = job ? job->shell_geometry : (shell_geometry){0};
  host_probe_log("open_shell_geometry_height",session->shell_geometry.height);
  if (session->shell_geometry.enabled) {
    shell_apply_config(&session->config, session->shell_geometry);
    host_probe_log("open_page_height",session->config.page.height);
    if(session->txt) session->config.user_css=NULL;
    return;
  }
#endif
#ifdef EXR_READER_WINDOWS_PREFERENCES
  /* An explicitly chosen F3 record replaces the legacy percent mapping. Until
     then the original mapping below is what an untouched install still uses. */
  if (job && job->prefs_valid) {
    session->config.page.margin = job->prefs.margin;
    session->config.page.font_size = job->prefs.font_size;
    session->config.page.line_height = job->prefs.line_spacing;
    session->config.page.paragraph_spacing = job->prefs.paragraph_spacing;
    session->background = prefs_background_of(&job->prefs, job->system_theme);
    session->foreground = prefs_foreground_of(&job->prefs, job->system_theme);
    session->themed = 1;
    return;
  }
#endif
  if (font_percent < HOST_FONT_MIN) font_percent = HOST_FONT_MIN;
  if (font_percent > HOST_FONT_MAX) font_percent = HOST_FONT_MAX;
  session->config.page.margin = 36;
  session->config.page.font_size = 28.0f * (float)font_percent / 100.0f;
  session->config.page.line_height = 1.5f;
  session->config.page.paragraph_spacing = 10;
}

typedef struct { char *bytes; size_t used, capacity; } host_text_sink;
static exr_status page_text_sink(void *context, const char *bytes, size_t size, exr_error *error) {
  host_text_sink *sink = context;
  if (sink->used > sink->capacity || size > sink->capacity - sink->used) {
    if (error) { error->code = EXR_LIMIT; strcpy(error->message, "Page text exceeds owned frame capacity"); }
    return EXR_LIMIT;
  }
  memcpy(sink->bytes + sink->used, bytes, size); sink->used += size; return EXR_OK;
}

static exr_status bounded_pager(host_session *session, size_t part, exr_pager **out, exr_error *error) {
  exr_chapter_options options = exr_chapter_options_defaults();
  exr_status status;
  options.workspace_budget = 8 * 1024 * 1024; options.window_bytes = 64 * 1024;
#ifdef EXR_READER_WINDOWS_PREFERENCES
  status = prefs_chapter_pager(session->publication, part, &session->config, session->themed,
                               session->foreground, &options, out, error);
#else
  status = exr_publication_pager_create(session->publication, part, g.font, &session->config, &options, out, error);
#endif
  if (status == EXR_OK) status = exr_pager_set_cache(*out, 2, 32 * 1024 * 1024, error);
  if (status == EXR_OK) status = exr_pager_set_checkpoints(*out, 8, 4 * 1024 * 1024, 8, error);
  if (status != EXR_OK) { exr_pager_free(*out); *out = NULL; }
  return status;
}

/* A valid get-mode pager reports this exact public error only for normal EOF.
   Other ARGUMENT/IO/LIMIT failures are never treated as a chapter boundary. */
static int pager_eof(exr_status status, const exr_error *error) {
  return status == EXR_ARGUMENT && error && !strcmp(error->message, "Page index is outside the document");
}

#ifdef EXR_READER_WINDOWS_SHELL
/* Copy while the pager owns layout; no UI pointer into a bounded pager survives. */
static int shell_capture_layout(host_frame *frame, const host_session *session, const exr_layout *layout) {
  const exr_line *lines; const exr_glyph *glyphs;
  frame->writing_mode = (int)exr_layout_writing_mode(layout);
  frame->shell_geometry = session->shell_geometry;
  host_probe_log("image_shell_geometry_height",session->shell_geometry.height);
  if (!session->shell_geometry.enabled) return 1;
  lines = exr_layout_lines(layout, &frame->shell_line_count);
  if (frame->shell_line_count) {
    frame->shell_lines = malloc(frame->shell_line_count * sizeof(*lines));
    if (!frame->shell_lines) return 0;
    memcpy(frame->shell_lines, lines, frame->shell_line_count * sizeof(*lines));
  }
  if (!frame->glyphs) {
    glyphs = exr_layout_glyphs(layout, &frame->glyph_count);
    if (frame->glyph_count > HOST_PAGE_GLYPH_LIMIT) return 0;
    if (frame->glyph_count) {
      frame->glyphs = malloc(frame->glyph_count * sizeof(*glyphs));
      if (!frame->glyphs) return 0;
      memcpy(frame->glyphs, glyphs, frame->glyph_count * sizeof(*glyphs));
    }
  }
  size_t box_count=0, image_count=0;
  const exr_box *boxes=exr_layout_boxes(layout,&box_count), *image=NULL;
  int visible_text=0;
  for(size_t i=0;i<frame->glyph_count;i++) {
    unsigned c=frame->glyphs[i].codepoint;
    if(c>32 && c!=0x3000 && c!=0xfffc) visible_text=1;
  }
  for(size_t i=0;i<box_count;i++) {
    if(boxes[i].kind==EXR_BOX_IMAGE) {image=boxes+i;image_count++;}
  }
  frame->shell_image_count=image_count;
  frame->shell_visible_text=visible_text;
  frame->shell_image_flags=image ? image->flags : 0;
  host_probe_log("image_count",(double)image_count);
  host_probe_log("image_visible_text",visible_text);
  if(image) {
    host_probe_log("image_flags",image->flags);
    host_probe_log("image_box_y",image->y);
    host_probe_log("image_box_height",image->height);
  }
  /* Image flags are not CSS alignment/margins: 0x1 means a missing-image
     placeholder. Unknown image bits also keep the SDK's normal page paint. */
  if(!visible_text && image_count==1 && !image->flags && image->width>0 && image->height>0) {
    const exr_bitmap *source=exr_layout_image(layout,image->resource);
    frame->shell_image_available=source!=NULL;
    host_probe_log("image_source_available",source!=NULL);
    if(source && source->channels==4 && source->width && source->height) {
      size_t count=(size_t)source->width*source->height;
      if(count>SIZE_MAX/sizeof(uint32_t)) return 0;
      frame->shell_image_pixels=malloc(count*sizeof(uint32_t));
      if(!frame->shell_image_pixels) return 0;
      for(size_t i=0;i<count;i++) {
        const unsigned char *p=source->pixels+(i/source->width)*source->stride+(i%source->width)*4;
        unsigned a=p[3],r=(p[0]*a+255*(255-a)+127)/255;
        unsigned green=(p[1]*a+255*(255-a)+127)/255,b=(p[2]*a+255*(255-a)+127)/255;
        frame->shell_image_pixels[i]=(r<<16)|(green<<8)|b;
      }
      frame->shell_image=(RECT){0,0,(LONG)source->width,(LONG)source->height};
    }
  }
  return 1;
}
#endif

static exr_status render_reflow(host_session *session, size_t page, host_frame *out,
                                const exr_control *control, exr_error *error) {
  const exr_layout *layout = NULL;
  const exr_page *info;
  exr_page saved_info;
  const char *text;
  size_t count = 0, size = 0;
  exr_status status;
  memset(out, 0, sizeof(*out));
  host_probe_log("layout_request",(double)page);
  status = exr_pager_get(session->pager, page, &layout, error);
  if (status != EXR_OK) return status;
  info = exr_layout_pages(layout, &count);
  if (!info || count < 1) return EXR_FORMAT;
  saved_info = *info; info = &saved_info;
  if (info->start > info->end || info->end - info->start > HOST_PAGE_TEXT_LIMIT) return EXR_LIMIT;
  text = session->bounded ? NULL : exr_document_text(session->document, &size);
  if (!session->bounded && (!text || info->end > size)) return EXR_FORMAT;
#ifdef EXR_READER_WINDOWS_PREFERENCES
  if (session->themed)
    status = host_probe_render(layout, control, &out->bitmap, error, session->background);
  else
#endif
  status = host_probe_render(layout, control, &out->bitmap, error, 0xffffffff);
  if (status != EXR_OK) return status;
  out->text_bytes = info->end - info->start;
  out->utf8 = malloc(out->text_bytes + 1);
  if (!out->utf8) { frame_clear(out); return EXR_MEMORY; }
  if (session->bounded) {
    const exr_glyph *glyphs = exr_layout_glyphs(layout, &out->glyph_count);
    if (out->glyph_count > HOST_PAGE_GLYPH_LIMIT) { frame_clear(out); return EXR_LIMIT; }
    if (out->glyph_count) {
      out->glyphs = malloc(out->glyph_count * sizeof(*out->glyphs));
      if (!out->glyphs) { frame_clear(out); return EXR_MEMORY; }
      memcpy(out->glyphs, glyphs, out->glyph_count * sizeof(*out->glyphs));
    }
  } else memcpy(out->utf8, text + info->start, out->text_bytes);
  out->utf8[out->text_bytes] = 0;
  out->text = session->bounded ? NULL : host_wide(out->utf8, out->text_bytes);
  if (!session->bounded && !out->text) { frame_clear(out); return EXR_MEMORY; }
#ifdef EXR_READER_WINDOWS_SHELL
  if (!shell_capture_layout(out, session, layout)) { frame_clear(out); return EXR_MEMORY; }
#endif
  out->bounded = session->bounded; out->part = session->part;
  out->hold_progress = session->hold_progress;
  out->generation = ++g.frame_sequence;
  out->text_bytes = info->end - info->start;
  out->page = page;
  out->range_start = info->start;
  out->range_end = info->end;
  out->valid = 1;
  out->fixed = 0;
  out->render_scale = 1;
  out->book_id = session->book_id;
  {
    size_t total = (size_t)out->bitmap.width * out->bitmap.height;
    size_t i;
    if (out->bitmap.channels != 4 || total > SIZE_MAX / sizeof(uint32_t)) {
      frame_clear(out);
      return EXR_FORMAT;
    }
    out->dib = malloc(total * sizeof(uint32_t));
    if (!out->dib) {
      frame_clear(out);
      return EXR_MEMORY;
    }
    for (i = 0; i < total; i++) {
      const unsigned char *p = out->bitmap.pixels + (i / out->bitmap.width) * out->bitmap.stride +
                               (i % out->bitmap.width) * 4;
      unsigned a = p[3];
      unsigned r = (p[0] * a + 255 * (255 - a) + 127) / 255;
      unsigned g = (p[1] * a + 255 * (255 - a) + 127) / 255;
      unsigned b = (p[2] * a + 255 * (255 - a) + 127) / 255;
      out->dib[i] = (r << 16) | (g << 8) | b;
    }
  }
  if (!session->bounded) {
    exr_positioned_page positioned = {0};
    exr_positioned_input input = {0};
    exr_layout_config hit = exr_layout_config_defaults();
    positioned.width = (float)out->bitmap.width;
    positioned.height = (float)out->bitmap.height;
    positioned.content = *info;
    positioned.content.box_start = positioned.content.box_count = 0;
    input.struct_size = sizeof(input);
    input.pages = &positioned; input.page_count = 1;
    input.glyphs = exr_layout_glyphs(layout, &input.glyph_count);
    input.lines = exr_layout_lines(layout, &input.line_count);
    hit.page.width = positioned.width; hit.page.height = positioned.height; hit.page.margin = 0;
    if (control) hit.control = *control;
    status = exr_layout_create_positioned(session->document, exr_layout_font(layout), &input, &hit,
                                          &out->hit_layout, error);
    if (status != EXR_OK) { frame_clear(out); return status; }
  }
  if (session->bounded) {
    host_text_sink sink = {out->utf8, 0, out->text_bytes};
    status = exr_pager_read_text(session->pager, info->start, info->end, page_text_sink, &sink, control, error);
    if (status == EXR_OK && sink.used != out->text_bytes) status = EXR_FORMAT;
    if (status == EXR_OK) {
      out->text = host_wide(out->utf8, out->text_bytes);
      if (!out->text) status = EXR_MEMORY;
    }
    size_t head = info->start;
#ifdef EXR_READER_WINDOWS_SHELL
    if (out->shell_line_count) head = out->shell_lines[0].start;
#endif
    if (status == EXR_OK) status = exr_pager_anchor_create(session->pager, head, head, control, &out->point, error);
    if (status != EXR_OK) { frame_clear(out); return status; }
    out->chapter_stats = exr_pager_chapter_statistics(session->pager);
  }
  return EXR_OK;
}

static exr_status render_fixed(host_session *session, size_t page, int zoom_percent,
                               host_frame *out, const exr_control *control, exr_error *error) {
  const exr_fixed_page *pages;
  size_t count = 0;
  double width, height, base, scale;
  exr_fixed_render_options options = {0};
  exr_fixed_text *text = NULL;
  const char *bytes = NULL;
  size_t size = 0;
  exr_status status;
  memset(out, 0, sizeof(*out));
  pages = exr_fixed_pages(session->fixed_document, &count);
  if (!pages || page >= count) return EXR_ARGUMENT;
  width = (pages[page].geometry.bounds[2] - pages[page].geometry.bounds[0]) * pages[page].geometry.unit_scale;
  height = (pages[page].geometry.bounds[3] - pages[page].geometry.bounds[1]) * pages[page].geometry.unit_scale;
  if (!(width > 0) || !(height > 0) || !isfinite(width) || !isfinite(height)) return EXR_FORMAT;
  base = fmin(1.0, 1440.0 / fmax(width, height));
  scale = base * ((double)zoom_percent / 100.0);
#ifdef EXR_READER_WINDOWS_SHELL
  if (session->shell_geometry.enabled)
    scale = fmin(session->shell_geometry.width / width, session->shell_geometry.height / height);
#endif
  if (!isfinite(scale) || scale <= 0) return EXR_ARGUMENT;
  if (width * scale > 4096.0 || height * scale > 4096.0) {
#ifdef EXR_READER_WINDOWS_PREFERENCES
    /* A chosen F3 zoom is never silently reduced: the host bound is reported. */
    if (session->themed) {
      strcpy(error->message, "Fixed page exceeds the host 4096 pixel bound");
      return EXR_LIMIT;
    }
#endif
    {
      double limit = fmin(4096.0 / width, 4096.0 / height);
      scale = limit;
    }
  }
  options.channels = 4;
  options.background = 0xffffffffu;
  if (control) options.control = *control;
  status = exr_fixed_render(session->fixed_document, page, scale, &options, &out->bitmap, error);
  if (status != EXR_OK) return status;
  {
    exr_status text_status = exr_fixed_load_text(session->fixed_document, page, control, &text, error);
    if (text_status == EXR_OK) {
      bytes = exr_fixed_text_string(text, &size);
    } else if (text_status == EXR_CANCELLED) {
      exr_bitmap_free(&out->bitmap);
      if (text) exr_fixed_text_free(text);
      return EXR_CANCELLED;
    } else {
      memset(error, 0, sizeof(*error));
      bytes = "";
      size = 0;
      if (text) {
        exr_fixed_text_free(text);
        text = NULL;
      }
    }
  }
  out->text = host_wide(bytes ? bytes : "", size);
  if (!out->text) {
    exr_bitmap_free(&out->bitmap);
    exr_fixed_text_free(text);
    return EXR_MEMORY;
  }
  out->text_bytes = size;
#ifdef EXR_READER_WINDOWS_SHELL
  out->shell_geometry=session->shell_geometry;
  if(session->shell_geometry.enabled && !size)
    out->shell_image=(RECT){0,0,(LONG)out->bitmap.width,(LONG)out->bitmap.height};
#endif
  out->page = page;
  out->range_start = 0;
  out->range_end = size;
  out->page_count = count;
  out->valid = 1;
  out->fixed = 1;
  out->generation = ++g.frame_sequence;
  out->render_scale = scale;
  out->book_id = session->book_id;
  {
    size_t total = (size_t)out->bitmap.width * out->bitmap.height;
    size_t i;
    if (out->bitmap.channels != 4 || total > SIZE_MAX / sizeof(uint32_t)) {
      frame_clear(out);
      exr_fixed_text_free(text);
      return EXR_FORMAT;
    }
    out->dib = malloc(total * sizeof(uint32_t));
    if (!out->dib) {
      frame_clear(out);
      exr_fixed_text_free(text);
      return EXR_MEMORY;
    }
    for (i = 0; i < total; i++) {
      const unsigned char *p = out->bitmap.pixels + (i / out->bitmap.width) * out->bitmap.stride +
                               (i % out->bitmap.width) * 4;
      unsigned a = p[3];
      unsigned r = (p[0] * a + 255 * (255 - a) + 127) / 255;
      unsigned gg = (p[1] * a + 255 * (255 - a) + 127) / 255;
      unsigned b = (p[2] * a + 255 * (255 - a) + 127) / 255;
      out->dib[i] = (r << 16) | (gg << 8) | b;
    }
  }
  out->fixed_text = text;
  out->geometry = pages[page].geometry;
  return EXR_OK;
}

/* Locate the page that owns a reflow text offset. The pager has no page count,
   so the search doubles and then bisects; each get() is checkpoint-resumable. */
static exr_status page_for_offset(host_session *session, size_t offset, const exr_control *control,
                                  size_t *page, size_t *start, size_t *end, exr_error *error) {
  const exr_layout *layout = NULL;
  const exr_page *info;
  size_t count = 0, lo = 0, hi = 1, guard = 0;
  exr_status status;
  int bounded = 0;
  /* The bounded pager and the TXT pager both report normal EOF as a pager
     error and expose no page count; a resident document uses EXR_ARGUMENT. */
  const int pager_bounded = session->bounded || session->txt;
  /* TXT get-mode retains only a few recent checkpoints. Doubling past a
     distant offset then bisecting can repeatedly replay the entire prefix.
     Walk forward once, preserving the same last-start-at-or-before rule. */
  if (session->txt) {
    size_t index, chosen = 0, chosen_start = 0, chosen_end = 0;
    int have = 0;
    for (index = 0; index <= 1000000; index++) {
      if (control && control->cancelled && control->cancelled(control->context)) return EXR_CANCELLED;
      status = OFFSET_GET(session->pager, index, &layout, error);
      if (status != EXR_OK) {
        if (!have || !pager_eof(status, error)) return status;
        memset(error, 0, sizeof(*error));
        break;
      }
      info = exr_layout_pages(layout, &count);
      if (!info || count < 1) return EXR_FORMAT;
      if (have && info->start > offset) break;
      chosen = index; chosen_start = info->start; chosen_end = info->end; have = 1;
      if (!index && offset < info->end) break;
    }
    if (!have) return EXR_FORMAT;
    if (page) *page = chosen;
    if (start) *start = chosen_start;
    if (end) *end = chosen_end;
    return EXR_OK;
  }
  status = OFFSET_GET(session->pager, 0, &layout, error);
  if (status != EXR_OK) return status;
  info = exr_layout_pages(layout, &count);
  if (!info || count < 1) return EXR_FORMAT;
  if (offset < info->end) {
    if (page) *page = 0;
    if (start) *start = info->start;
    if (end) *end = info->end;
    return EXR_OK;
  }
  while (guard++ < 64) {
    size_t next = hi * 2;
    status = OFFSET_GET(session->pager, hi, &layout, error);
    if (status != EXR_OK) {
      if (pager_bounded ? !pager_eof(status, error) : status != EXR_ARGUMENT) return status;
      memset(error, 0, sizeof(*error));
      bounded = 1;
      break;
    }
    info = exr_layout_pages(layout, &count);
    if (!info || count < 1) return EXR_FORMAT;
    if (info->start > offset) break;
    lo = hi;
    if (next > 1000000) {
      hi = 1000000;
      break;
    }
    hi = next;
  }
  (void)bounded;
  while (lo + 1 < hi) {
    size_t mid = lo + (hi - lo) / 2;
    status = OFFSET_GET(session->pager, mid, &layout, error);
    if (status != EXR_OK && (pager_bounded ? !pager_eof(status, error) : status != EXR_ARGUMENT)) return status;
    if (status == EXR_OK && exr_layout_pages(layout, &count) != NULL && count > 0 &&
        exr_layout_pages(layout, &count)[0].start <= offset) {
      lo = mid;
    } else {
      hi = mid;
    }
    memset(error, 0, sizeof(*error));
  }
  status = OFFSET_GET(session->pager, lo, &layout, error);
  if (status != EXR_OK) return status;
  info = exr_layout_pages(layout, &count);
  if (!info || count < 1) return EXR_FORMAT;
  {
    size_t extent = 0;
    /* The TXT pager does not expose its projected length; every saved TXT point
       is a page start in the same projection, so the located page owns it. */
    if (session->bounded) extent = exr_pager_chapter_statistics(session->pager).projection_bytes;
    else if (!session->txt) exr_document_text(session->document, &extent);
    if (offset < info->start) return EXR_ARGUMENT;
    if (!session->txt && offset >= info->end && !(offset == extent && info->end == extent))
      return EXR_ARGUMENT;
  }
  if (page) *page = lo;
  if (start) *start = info->start;
  if (end) *end = info->end;
  return EXR_OK;
}

static exr_status reflow_restore(host_session *session, const exr_control *control,
                                 size_t *page, wchar_t *note, size_t note_capacity) {
  exr_anchor anchor = {0};
  exr_anchor_state state = EXR_ANCHOR_MISSING;
  exr_error error = {0};
  exr_anchor_match match;
  exr_status status;
  size_t offset = 0;
  if (note && note_capacity) note[0] = 0;
  EnterCriticalSection(&g.library_lock);
  status = exr_library_progress_get(g.library, session->book_id, &anchor, &state, &error);
  LeaveCriticalSection(&g.library_lock);
  if (status != EXR_OK) {
    exr_anchor_free(&anchor);
    if (note && note_capacity) copy_wstring(note, note_capacity, L"无法读取上次进度，未覆盖原位置，请重试。");
    return status;
  }
  offset = anchor.start;
  if (state == EXR_ANCHOR_FOUND) {
    status = exr_anchor_resolve_ex(session->document, &anchor, control, &match, &error);
    if (status != EXR_OK) { exr_anchor_free(&anchor); return status; }
    if (status == EXR_OK && match.state == EXR_ANCHOR_FOUND) {
      offset = match.start;
      if (note && note_capacity) copy_wstring(note, note_capacity, L"已按文本锚点恢复到上次位置。");
    } else if (status == EXR_OK && match.state == EXR_ANCHOR_AMBIGUOUS) {
      offset = anchor.start;
      if (note && note_capacity)
        copy_wstring(note, note_capacity, L"锚点存在歧义（同一文本出现多处），已按上次保存的文本偏移恢复。");
    } else {
      offset = anchor.start;
      if (note && note_capacity)
        copy_wstring(note, note_capacity, L"锚点未匹配，已按上次保存的文本偏移恢复。");
    }
  } else if (state == EXR_ANCHOR_LEGACY) {
    if (note && note_capacity)
      copy_wstring(note, note_capacity, offset ? L"旧版进度：按保存的文本偏移恢复。" : L"从第一页开始。");
  } else {
    if (note && note_capacity) copy_wstring(note, note_capacity, L"锚点状态未知，从第一页开始。");
    offset = 0;
  }
  exr_anchor_free(&anchor);
  return page_for_offset(session, offset, control, page, NULL, NULL, &error);
}

static exr_status bounded_restore(host_session *session, const exr_control *control,
                                   size_t *page, wchar_t *note, size_t capacity, exr_error *error) {
  exr_epub_location location = {0}; exr_anchor_match match;
  const exr_part *parts; size_t count = 0, first = SIZE_MAX, i; int present = 0;
  exr_status status;
  parts = exr_publication_parts(session->publication, &count);
  for (i = 0; parts && i < count; i++) if (parts[i].in_reading_order) { first = i; break; }
  if (first == SIZE_MAX) return EXR_FORMAT;
  EnterCriticalSection(&g.library_lock);
  status = exr_library_epub_progress_get(g.library, session->book_id, &location, &present, error);
  LeaveCriticalSection(&g.library_lock);
  if (status != EXR_OK) return status;
  session->part = present ? location.part : first;
  if (session->part >= count || !parts[session->part].in_reading_order ||
      (present && (!location.path || strcmp(location.path, parts[session->part].path)))) {
    exr_epub_location_free(&location); return EXR_FORMAT;
  }
  status = bounded_pager(session, session->part, &session->pager, error);
  *page = 0;
  if (status == EXR_OK && present) {
    status = exr_pager_anchor_resolve(session->pager, &location.selector, control, &match, error);
    if (status == EXR_OK) {
      size_t offset = match.state == EXR_ANCHOR_FOUND ? match.start : location.selector.start;
      if (match.state != EXR_ANCHOR_FOUND) {
        host_text_sink sink = {NULL, 0, 0};
        /* Validate the stored chapter-local UTF-8 boundary before using a
           numerical fallback. This does not change the anchor match state. */
        status = exr_pager_read_text(session->pager, offset, offset, page_text_sink, &sink, control, error);
        session->hold_progress = 1;
        copy_wstring(note, capacity, match.state == EXR_ANCHOR_AMBIGUOUS ?
          L"进度锚点存在歧义，按已保存章内偏移回退恢复（未精确锚定）；保留原记录，翻页后保存新位置。" :
          L"进度锚点未匹配，按已保存章内偏移回退恢复（未精确锚定）；保留原记录，翻页后保存新位置。");
      } else copy_wstring(note, capacity, L"已按章节与文本锚点恢复到上次位置。");
      if (status == EXR_OK) status = page_for_offset(session, offset, control, page, NULL, NULL, error);
    }
  } else if (status == EXR_OK) copy_wstring(note, capacity, L"从首个阅读章节开始。");
  exr_epub_location_free(&location); return status;
}

#if defined(EXR_READER_WINDOWS_TXT_RECOVERY) || defined(EXR_READER_WINDOWS_SHELL)
/* The verified handle is the source: no path reopen between verification and read.
   The pager owns this context after successful creation. The worker serializes
   catalog operations and session disposal; Windows sharing prevents mutation. */
static inline size_t txt_read(void *context,uint64_t offset,void *buffer,size_t size) {
  HANDLE h=(HANDLE)context; LARGE_INTEGER at; DWORD got=0;
  if(offset>INT64_MAX || size>UINT32_MAX) return 0;
  at.QuadPart=(LONGLONG)offset;
  if(!SetFilePointerEx(h,at,NULL,FILE_BEGIN) || !ReadFile(h,buffer,(DWORD)size,&got,NULL)) return 0;
  return (size_t)got;
}
static inline void txt_release(void *context) { CloseHandle((HANDLE)context); }
static exr_status txt_frame(host_session *session, const exr_source *source, const exr_layout *layout,
                            size_t page, host_frame *frame, exr_error *error) {
  exr_txt_cursor *cursor=NULL; const exr_page *info; size_t count=0;
  exr_txt_checkpoint saved={0}; int have_saved=0;
  exr_status status=EXR_OK;
  info=exr_layout_pages(layout,&count);
  if(!info || !count || info->start>info->end || info->end-info->start>HOST_PAGE_TEXT_LIMIT) return EXR_FORMAT;
  (*frame).range_start=info->start; (*frame).range_end=info->end;
  (*frame).text_bytes=info->end-info->start;
  (*frame).utf8=calloc((*frame).text_bytes+1,1);
  if(!(*frame).utf8) { status=EXR_MEMORY;goto done; }
  /* TXT pager deliberately has no text query. Project the same page range
     through the public bounded cursor for accessibility and page text. */
  status=exr_txt_cursor_create(source,&cursor,error);
  if(status!=EXR_OK) goto done;
  if(session->txt_checkpoint_valid && session->txt_checkpoint.projection_offset<=info->start) {
    status=exr_txt_cursor_restore(cursor,&session->txt_checkpoint,error);
    if(status!=EXR_OK) goto done;
  }
  {
    size_t filled=0; uint64_t offset; const char *text; size_t length;
    while(filled<(*frame).text_bytes) {
      exr_txt_checkpoint before;
      status=exr_txt_cursor_checkpoint(cursor,&before,error);
      if(status!=EXR_OK) goto done;
      status=exr_txt_cursor_next(cursor,&offset,&text,&length,error);
      if(status!=EXR_OK || !text) { if(status==EXR_OK) status=EXR_FORMAT;goto done; }
      if(offset<=info->start) { saved=before; have_saved=1; }
      if(offset + length < info->start + filled) continue;
      if(offset>info->start+filled) {
        if(offset!=info->start+filled+1) { status=EXR_FORMAT;goto done; }
        (*frame).utf8[filled++]='\n';
      }
      if(offset+length>info->start+filled) {
        size_t skip=(size_t)(info->start+filled-offset), n=length-skip;
        if(n>(*frame).text_bytes-filled) n=(*frame).text_bytes-filled;
        memcpy((*frame).utf8+filled,text+skip,n);filled+=n;
      }
    }
  }
  (*frame).text=host_wide((*frame).utf8,(*frame).text_bytes);
  if(!(*frame).text) { status=EXR_MEMORY;goto done; }
  status=exr_render_page_ex(layout,exr_layout_font(layout),0,4,&session->config.control,&(*frame).bitmap,error);
  if(status!=EXR_OK) goto done;
  {
    const exr_glyph *glyphs=exr_layout_glyphs(layout,&frame->glyph_count);
    if(frame->glyph_count>HOST_PAGE_GLYPH_LIMIT) { status=EXR_LIMIT;goto done; }
    if(frame->glyph_count) {
      if(!glyphs) { status=EXR_FORMAT;goto done; }
      frame->glyphs=malloc(frame->glyph_count*sizeof(*frame->glyphs));
      if(!frame->glyphs) { status=EXR_MEMORY;goto done; }
      memcpy(frame->glyphs,glyphs,frame->glyph_count*sizeof(*frame->glyphs));
    }
  }
  {
    exr_bitmap *b=&(*frame).bitmap; size_t total=(size_t)b->width*b->height;
    if(b->channels!=4 || total>SIZE_MAX/sizeof(uint32_t)) { status=EXR_FORMAT;goto done; }
    (*frame).dib=malloc(total*sizeof(uint32_t));
    if(!(*frame).dib) { status=EXR_MEMORY;goto done; }
    for(size_t i=0;i<total;i++) {
      const unsigned char *p=b->pixels+(i/b->width)*b->stride+(i%b->width)*4; unsigned a=p[3];
      unsigned r=(p[0]*a+255*(255-a)+127)/255, g=(p[1]*a+255*(255-a)+127)/255, bl=(p[2]*a+255*(255-a)+127)/255;
      (*frame).dib[i]=(r<<16)|(g<<8)|bl;
    }
  }
#ifdef EXR_READER_WINDOWS_SHELL
  if (!shell_capture_layout(frame, session, layout)) { status=EXR_MEMORY;goto done; }
#endif
  (*frame).valid=1; (*frame).render_scale=1; (*frame).generation=++g.frame_sequence;
  frame->hold_progress=session->hold_progress;
  frame->page=page;
  if(have_saved) { session->txt_checkpoint=saved; session->txt_checkpoint_valid=1; }
 done:
  if(cursor) exr_txt_cursor_free(cursor);
  if(status!=EXR_OK) frame_clear(frame);
  return status;
}

#endif
#ifdef EXR_READER_WINDOWS_TXT_RECOVERY
#ifdef EXR_READER_WINDOWS_TXT_PROGRESS
static exr_status txt_restore(host_session *session, const char *key, size_t *page,
                              wchar_t *note, size_t capacity, exr_error *error);
static int txt_open_book_row(void *context, const reader_catalog_row *row) {
  exr_book *book = context;
  if (row->deleted || strcmp(row->format, "txt")) return 1;
  book->format = EXR_TXT;
  book->favorite = row->favorite;
  book->title = host_strdup(row->title ? row->title : "");
  book->author = host_strdup(row->author ? row->author : "");
  return 1;
}
#endif

static exr_status job_open_txt(host_job *job) {
  reader_catalog *catalog=NULL; reader_catalog_error ce={0};
  reader_original_callbacks callbacks={job,job_cancel_check,NULL};
  reader_original_status rs; char *root=host_utf8(g.original_root),*path=host_utf8(g.product_path);
  void *handle=NULL; uint64_t bytes=0; exr_source source={0}; exr_error error={0};
  host_session session={0}; const exr_layout *layout=NULL;
  exr_status status=EXR_IO; const exr_page *info; size_t count=0;
  if(!root || !path) { status=EXR_MEMORY; goto done; }
  if(reader_catalog_open(path,&catalog,&ce)) { status=EXR_DATABASE; goto done; }
#ifdef EXR_READER_WINDOWS_TXT_PROGRESS
  if (!job->opened_book.title) {
    int found=0;
    if (reader_catalog_metadata(catalog,job->product_key,txt_open_book_row,&job->opened_book,&found,&ce) ||
        !found || !job->opened_book.title || !job->opened_book.author) {
      status=EXR_IO; goto done;
    }
  }
#endif
  rs=reader_original_verified_handle(catalog,root,job->product_key,&callbacks,&handle,&bytes);
  if(rs!=ROI_OK) { status=rs==ROI_CANCELLED?EXR_CANCELLED:rs==ROI_MEMORY?EXR_MEMORY:EXR_IO; goto done; }
  source.size=bytes; source.context=handle; source.read_at=txt_read; source.release=txt_release;
  source.control.cancelled=host_cancel_check;
  session.txt=1; session_configure(&session,job);
  session.config.control.cancelled=host_cancel_check;
  status=exr_txt_pager_create(&source,g.font,&session.config,&session.pager,&error);
  if(status!=EXR_OK) goto done;
  handle=NULL; /* pager now owns it */
  status=exr_pager_set_cache(session.pager,2,8*1024*1024,&error);
  if(status==EXR_OK) status=exr_pager_set_checkpoints(session.pager,8,4*1024*1024,8,&error);
  session.txt_source=source;
#ifdef EXR_READER_WINDOWS_TXT_PROGRESS
  snprintf(session.txt_key,sizeof(session.txt_key),"%s",job->product_key);
  TXT_TRACE("pager-created");
  /* Restore before the first page is accepted: the product content identity and
     the captured projection window decide the page, never a stored page number. */
  {
    size_t target=0; wchar_t note[256]={0};
    TXT_TRACE("restore-start");
    status=txt_restore(&session,job->product_key,&target,note,256,&error);
    TXT_TRACE("restore-finished");
    if(status==EXR_OK) status=exr_pager_get(session.pager,target,&layout,&error);
    if(status!=EXR_OK || !layout) { if(status==EXR_OK) status=EXR_FORMAT; goto done; }
    info=exr_layout_pages(layout,&count);
    if(!info || !count || info->start>info->end || info->end-info->start>HOST_PAGE_TEXT_LIMIT) { status=EXR_FORMAT;goto done; }
    TXT_TRACE("first-page-ready");
    status=txt_frame(&session,&source,layout,target,&job->frame,&error);
    TXT_TRACE("first-frame-finished");
    if(status!=EXR_OK) goto done;
    copy_wstring(job->message,512,note[0]?note:L"从第一页开始。");
  }
#else
  if(status==EXR_OK) status=exr_pager_get(session.pager,0,&layout,&error);
  if(status!=EXR_OK || !layout) { if(status==EXR_OK) status=EXR_FORMAT; goto done; }
  info=exr_layout_pages(layout,&count);
  if(!info || !count || info->start>info->end || info->end-info->start>HOST_PAGE_TEXT_LIMIT) { status=EXR_FORMAT;goto done; }
  status=txt_frame(&session,&source,layout,0,&job->frame,&error);
  if(status!=EXR_OK) goto done;
#endif
  { const char *title=job->opened_book.title?job->opened_book.title:"Untitled";
    wchar_t *wide=host_wide(title,strlen(title));copy_wstring(job->frame.title,256,wide?wide:L"Untitled");free(wide); }
  session.active=1;job->candidate=session;memset(&session,0,sizeof(session));
  job->session_swapped=job->have_frame=1;

 done:
  session_clear(&session);
  if(handle) CloseHandle((HANDLE)handle);
  if(catalog && reader_catalog_close(&catalog,&ce) && status==EXR_OK) status=EXR_DATABASE;
  free(root);free(path);
  if(status!=EXR_OK) { frame_clear(&job->frame);job->error=error; }
  return status;
}
static exr_status job_txt_go(host_job *job) {
  host_session *session=&g.session;
  exr_error error={0}; const exr_layout *layout=NULL;
  exr_status status=EXR_IO;
  if(session->txt_pager_invalid) {
    exr_source source=session->txt_source; exr_pager *pager=NULL; HANDLE copy=NULL;
    if(!DuplicateHandle(GetCurrentProcess(),(HANDLE)source.context,GetCurrentProcess(),
                        &copy,0,FALSE,DUPLICATE_SAME_ACCESS)) goto done;
    source.context=copy;
    status=exr_txt_pager_create(&source,g.font,&session->config,&pager,&error);
    if(status!=EXR_OK) { CloseHandle(copy); goto done; }
    status=exr_pager_set_cache(pager,2,8*1024*1024,&error);
    if(status==EXR_OK) status=exr_pager_set_checkpoints(pager,8,4*1024*1024,8,&error);
    if(status!=EXR_OK) { exr_pager_free(pager); goto done; }
    exr_pager_free(session->pager);
    session->pager=pager; session->txt_source=source; session->txt_pager_invalid=0;
  }
  status=exr_pager_get(session->pager,job->target_page,&layout,&error);
  if(pager_eof(status,&error)) { job->at_end=1; goto done; }
  if(status!=EXR_OK) { session->txt_pager_invalid=1; goto done; }
  status=txt_frame(session,&session->txt_source,layout,job->target_page,&job->frame,&error);
  if(status==EXR_OK) {
    copy_wstring(job->frame.title,256,g.frame.title);
    job->have_frame=1;
  }
 done:
  if(status!=EXR_OK) job->error=error;
  return status;
}

#ifdef EXR_READER_WINDOWS_TXT_PROGRESS
/* ---- TXT reading position: product content identity + canonical offset ----
   A product TXT original has no SDK book identity, so the position is the
   pager's own normalized projection offset for the top of the accepted page,
   captured together with a bounded window of the real projected text. Every
   product write and read runs on the serialized host worker; the UI only hands
   over copied values and never touches the revision store. */
static int txt_store_open(reader_txt_progress **store, exr_error *error) {
  char *path = host_utf8(g.product_path);
  reader_txp_error detail = {0};
  reader_txp_status status;
  int raw = 0;
#ifdef EXR_READER_WINDOWS_RAW3
  raw = 1;
#endif
  if (!path) { if (error) error->code = EXR_MEMORY; return 0; }
  status = reader_txp_open(path, raw, store, &detail);
  free(path);
  if (status != READER_TXP_OK) {
    if (error) {
      error->code = status == READER_TXP_MEMORY ? EXR_MEMORY : EXR_DATABASE;
      snprintf(error->message, sizeof(error->message), "%s", detail.message);
    }
    return 0;
  }
  return 1;
}

/* Reads [offset, offset+size) of the same normalized projection the page ranges
   use. Paragraph separators are the single synthesized newline the page text
   path uses, so a captured window compares byte for byte. */
static exr_status txt_window(const exr_source *source, uint64_t offset, size_t size, char *buffer, size_t *written, exr_error *error) {
  exr_txt_cursor *cursor = NULL;
  exr_status status;
  size_t filled = 0;
  uint64_t at = 0;
  const char *text = NULL;
  size_t length = 0;
  if (written) *written = 0;
  status = exr_txt_cursor_create(source, &cursor, error);
  if (status != EXR_OK) return status;
  while (filled < size) {
    status = exr_txt_cursor_next(cursor, &at, &text, &length, error);
    if (status != EXR_OK || !text) { if (status == EXR_OK) status = EXR_FORMAT; break; }
    if (at + (uint64_t)length < offset + (uint64_t)filled) continue;
    if (at > offset + (uint64_t)filled) {
      if (at != offset + (uint64_t)filled + 1) { status = EXR_FORMAT; break; }
      buffer[filled++] = '\n';
    }
    if (at + (uint64_t)length > offset + (uint64_t)filled) {
      const size_t skip = (size_t)(offset + (uint64_t)filled - at);
      size_t take = length - skip;
      if (take > size - filled) take = size - filled;
      memcpy(buffer + filled, text + skip, take);
      filled += take;
    }
  }
  if (cursor) exr_txt_cursor_free(cursor);
  if (written) *written = filled;
  return status;
}

typedef struct {
  char *title, *author, *sort;
  uint64_t bytes;
  int favorite, found;
} txt_book_metadata;
static int txt_metadata_row(void *context, const reader_catalog_row *row) {
  txt_book_metadata *meta = context;
  if (meta->found) return 1;
  meta->title = host_strdup(row->title ? row->title : "");
  meta->author = host_strdup(row->author ? row->author : "");
  meta->sort = host_strdup(row->sort_title ? row->sort_title : "");
  meta->bytes = row->source_bytes;
  meta->favorite = row->favorite;
  meta->found = meta->title && meta->author && meta->sort;
  return 1;
}
static void txt_metadata_clear(txt_book_metadata *meta) {
  free(meta->title); free(meta->author); free(meta->sort);
  memset(meta, 0, sizeof(*meta));
}
/* The retained book revision is the product content identity. It is bootstrapped
   from the verified catalog row exactly once and never rewritten afterwards. */
static exr_status txt_bootstrap(reader_txt_progress *store, const char *key, exr_error *error) {
  reader_catalog *catalog = NULL;
  reader_catalog_error catalog_error = {0};
  reader_txp_book book = {0};
  reader_txp_result result = {0};
  reader_txp_error detail = {0};
  txt_book_metadata meta = {0};
  char *path = host_utf8(g.product_path);
  int found = 0, code = 0;
  reader_txp_status status;
  exr_status outcome = EXR_DATABASE;
  if (!path) return EXR_MEMORY;
  if (reader_catalog_open(path, &catalog, &catalog_error)) { free(path); return EXR_DATABASE; }
  code = reader_catalog_metadata(catalog, key, txt_metadata_row, &meta, &found, &catalog_error);
  reader_catalog_close(&catalog, &catalog_error);
  free(path);
  if (code || !found || !meta.found || !meta.bytes) { txt_metadata_clear(&meta); return EXR_FORMAT; }
  book.book_key = key;
  book.title = meta.title;
  book.author = meta.author;
  book.sort_title = meta.sort;
  book.source_bytes = meta.bytes;
  book.favorite = meta.favorite;
  status = reader_txp_ensure_book(store, &book, &result, &detail);
  if (status == READER_TXP_OK) outcome = EXR_OK;
  else if (status == READER_TXP_IDENTITY) outcome = EXR_FORMAT;
  else if (status == READER_TXP_ARGUMENT) outcome = EXR_ARGUMENT;
  else if (status == READER_TXP_MEMORY) outcome = EXR_MEMORY;
  else outcome = EXR_DATABASE;
  if (outcome != EXR_OK && error) {
    error->code = outcome;
    snprintf(error->message, sizeof(error->message), "%s",
             detail.message[0] ? detail.message : "Cannot retain the product book identity");
  }
  txt_metadata_clear(&meta);
  return outcome;
}

static const wchar_t *txt_status_note(reader_txp_status status) {
  switch (status) {
    case READER_TXP_MISSING: return L"这本书还没有保存过阅读位置；从第一页开始。";
    case READER_TXP_CONFLICT: return L"这本书存在多个并发阅读位置记录；未选择、未覆盖，从第一页开始。";
    case READER_TXP_PENDING: return L"阅读位置记录缺少父记录；保留原记录，从第一页开始。";
    case READER_TXP_BLOCKED: return L"阅读位置记录需要显式恢复；保留原记录，从第一页开始。";
    case READER_TXP_LEGACY: return L"存在旧版阅读位置记录；本机不据此跳转，原记录保留。";
    case READER_TXP_BOOTSTRAP: return L"这本书还没有产品内容身份记录；从第一页开始。";
    case READER_TXP_UNSAFE: return L"阅读位置记录刚被其他写入改变；未覆盖，从第一页开始。";
    default: return L"无法读取阅读位置记录；从第一页开始，原记录未被覆盖。";
  }
}

/* Restore a matching anchor v2 point. A new book starts at the beginning and
   may save normally; uncertain existing history blocks automatic overwrite. */
static exr_status txt_restore(host_session *session, const char *key, size_t *page,
                              wchar_t *note, size_t capacity, exr_error *error) {
  reader_txt_progress *store = NULL;
  reader_txp_position saved = {0};
  reader_txp_result meta = {0};
  reader_txp_error detail = {0};
  reader_txp_status status;
  exr_control control = {host_cancel_check, NULL, NULL};
  if (page) *page = 0;
  if (note && capacity) note[0] = 0;
  if (!key || !key[0]) { copy_wstring(note, capacity, L"缺少书籍身份；从第一页开始。"); return EXR_OK; }
  TXT_TRACE("store-open-start");
  if (!txt_store_open(&store, error)) {
    session->hold_progress = 1;
    copy_wstring(note, capacity, L"无法打开阅读位置记录；从第一页开始，原记录未被覆盖。");
    if (error) memset(error, 0, sizeof(*error));
    return EXR_OK;
  }
  TXT_TRACE("store-open-finished");
  status = reader_txp_load(store, key, &saved, &meta, &detail);
  TXT_TRACE("position-load-finished");
  reader_txp_close(&store);
  TXT_TRACE("store-close-finished");
  if (status == READER_TXP_MISSING) {
    copy_wstring(note, capacity, txt_status_note(status));
    return EXR_OK;
  }
  if (status != READER_TXP_OK) {
    session->hold_progress = 1;
    copy_wstring(note, capacity, txt_status_note(status));
    if (error) memset(error, 0, sizeof(*error));
    return EXR_OK;
  }
  if (saved.context_bytes) {
    char window[READER_TXP_CONTEXT_BYTES];
    size_t got = 0;
    int matches = 0;
    exr_status read = txt_window(&session->txt_source, saved.offset, saved.context_bytes,
                                 window, &got, error);
    if (read != EXR_OK) {
      session->hold_progress = 1;
      copy_wstring(note, capacity, L"无法核对已保存的文本位置；从第一页开始，原记录未被覆盖。");
      if (error) memset(error, 0, sizeof(*error));
      return EXR_OK;
    }
    if (reader_txp_match(&saved, window, saved.offset, got, &matches, &detail) != READER_TXP_OK || !matches) {
      session->hold_progress = 1;
      copy_wstring(note, capacity, L"保存的内容位置与当前文本投影不一致；未跳转，原记录保留。");
      return EXR_OK;
    }
  }
  {
    exr_status located = EXR_OK;
    size_t found = 0;
    if (saved.offset > (uint64_t)SIZE_MAX) located = EXR_ARGUMENT;
    else located = page_for_offset(session, (size_t)saved.offset, &control, &found, NULL, NULL, error);
    if (located != EXR_OK) {
      session->hold_progress = 1;
      copy_wstring(note, capacity, L"保存的内容位置不在当前分页范围内；从第一页开始，原记录保留。");
      if (error) memset(error, 0, sizeof(*error));
      return EXR_OK;
    }
    if (page) *page = found;
  }
  copy_wstring(note, capacity, L"已按内容位置恢复到上次阅读位置。");
  return EXR_OK;
}

/* One durable position write for the accepted page. Failure keeps the previous
   record: the module refuses on stale, concurrent, pending or blocked history
   and the catalog/revision transaction either commits or not. */
static exr_status job_txt_progress(host_job *job) {
  reader_txt_progress *store = NULL;
  reader_txp_position position = {0};
  reader_txp_result result = {0};
  reader_txp_error detail = {0};
  reader_txp_status status;
  exr_status outcome;
  if (!txt_store_open(&store, &job->error)) return EXR_DATABASE;
  status = reader_txp_capture(&position, job->txt_offset, job->txt_context, job->txt_context_bytes, &detail);
  if (status != READER_TXP_OK) {
    reader_txp_close(&store);
    job->error.code = EXR_ARGUMENT;
    snprintf(job->error.message, sizeof(job->error.message), "%s", detail.message);
    return EXR_ARGUMENT;
  }
  status = reader_txp_save(store, job->txt_key, exr_version(), &position, &result, &detail);
  if (status == READER_TXP_BOOTSTRAP) {
    /* First write for a book imported before this feature existed. */
    outcome = txt_bootstrap(store, job->txt_key, &job->error);
    if (outcome == EXR_OK)
      status = reader_txp_save(store, job->txt_key, exr_version(), &position, &result, &detail);
    else { reader_txp_close(&store); return outcome; }
  }
  reader_txp_close(&store);
  if (status == READER_TXP_OK) {
    job->txt_saved_offset = position.offset;
    job->txt_saved_valid = 1;
    return EXR_OK;
  }
  if (status == READER_TXP_UNSAFE || status == READER_TXP_CONFLICT || status == READER_TXP_PENDING ||
      status == READER_TXP_BLOCKED || status == READER_TXP_LEGACY || status == READER_TXP_LIMIT) {
    job->error.code = EXR_DATABASE;
    snprintf(job->error.message, sizeof(job->error.message), "%s",
             detail.message[0] ? detail.message : "The reading position was not written");
    return EXR_DATABASE;
  }
  job->error.code = status == READER_TXP_MEMORY ? EXR_MEMORY : EXR_DATABASE;
  snprintf(job->error.message, sizeof(job->error.message), "%s",
           detail.message[0] ? detail.message : "The reading position was not written");
  return job->error.code;
}
#endif

#endif
static exr_status job_open(host_job *job) {
#ifdef EXR_READER_WINDOWS_TXT_RECOVERY
  if(job->product_key[0] && job->book_id==0) return job_open_txt(job);
#endif
  host_session session;
  exr_error error = {0};
  exr_status status;
  exr_book book;
  memset(&session, 0, sizeof(session));
  memset(&book, 0, sizeof(book));
  /* The UI may evict or replace its metadata window while this worker runs.
     The public SDK currently enumerates into a temporary worker-only array;
     no pointer into that array or the UI cache survives this lookup. */
  status=local_book_copy(job->book_id,&book,&error);
  if (status != EXR_OK) {
    job->error = error;
    copy_wstring(job->message, 512, L"无法读取该书的本地信息。");
    book_clear(&book);
    return status;
  }
  if (job_cancel_flag(job)) {
    book_clear(&book);
    return EXR_CANCELLED;
  }
  if (book.id != job->book_id) {
    book_clear(&book);
    return EXR_ARGUMENT;
  }
  session.book_id = book.id;
  session.fixed = is_fixed_format(book.format);
#ifdef EXR_READER_WINDOWS_PREFERENCES
  if (job->prefs_valid) {
    session.background = prefs_background_of(&job->prefs, job->system_theme);
    session.foreground = prefs_foreground_of(&job->prefs, job->system_theme);
    session.themed = 1;
  }
#endif
#ifdef EXR_READER_WINDOWS_SHELL
  session.shell_geometry = job->shell_geometry;
#endif
  if (session.fixed) {
    exr_fixed_open_options options = {0};
    const exr_fixed_page *pages;
    size_t count = 0, target;
    options.struct_size = sizeof(options);
    options.fallback_font = g.font;
    options.control.cancelled = host_cancel_check;
    options.control.context = NULL;
    EnterCriticalSection(&g.library_lock);
    status = exr_library_fixed_source(g.library, book.id, &options, &session.fixed_document, &error);
    LeaveCriticalSection(&g.library_lock);
    if (status != EXR_OK) {
      book_clear(&book);
      return status;
    }
    pages = exr_fixed_pages(session.fixed_document, &count);
    if (!pages || !count) {
      session_clear(&session);
      book_clear(&book);
      return EXR_FORMAT;
    }
    session.page_count = count;
    target = book.position;
#ifdef EXR_READER_WINDOWS_SHELL
    shelf_fixed_page(book.id,pages,count,&target);
#endif
    if (target >= count) {
      target = count - 1;
      copy_wstring(job->message, 512, L"保存的页码超出范围，已回到最后一页。");
    }
    {
      exr_control control = {job_cancel_check, NULL, job};
      status = render_fixed(&session, target, job->zoom_percent > 0 ? job->zoom_percent : g.zoom_percent,
                            &job->frame, &control, &error);
    }
  } else {
    exr_library_epub_info info = {sizeof(info), 0, 0};
    session_configure(&session, job);
    session.config.control.cancelled = host_cancel_check;
    session.config.control.context = NULL;
    EnterCriticalSection(&g.library_lock);
    status = book.format == EXR_EPUB ? exr_library_epub_info_get(g.library, book.id, &info, &error) : EXR_OK;
    session.bounded = status == EXR_OK && info.bounded_storage;
    if (status == EXR_OK && session.bounded) {
      exr_source source = {0};
      status = exr_library_source(g.library, book.id, &source, &error);
      if (status == EXR_OK) {
        source.control.cancelled = host_cancel_check;
#ifdef EXR_READER_WINDOWS_SHELL
        if(!shell_epub_source(&source)) {
          source.release(source.context);status=EXR_FORMAT;
        } else
#endif
        {
        status = exr_publication_open_source(&source, &session.publication, &error);
        if (status != EXR_OK) source.release(source.context);
        }
      }
    } else if (status == EXR_OK) status = exr_library_document(g.library, book.id, &session.document, &error);
    LeaveCriticalSection(&g.library_lock);
#ifdef EXR_READER_WINDOWS_SHELL
    if(status==EXR_OK && !session.bounded && !shell_style_document(&session.document)) status=EXR_FORMAT;
#endif
    if (status == EXR_OK && !session.bounded)
      status = exr_pager_create(session.document, g.font, &session.config, &session.pager, &error);
    if (status == EXR_OK && !session.bounded) status = exr_pager_set_cache(session.pager, 2, 0, &error);
    if (status == EXR_OK && !session.bounded) status = exr_pager_set_checkpoints(session.pager, 8, 4 * 1024 * 1024, 8, &error);
    if (status == EXR_OK) {
      size_t page = 0;
      exr_control control = {job_cancel_check, NULL, job};
      size_t shelf_offset=0;int shelf_found=0;
#ifdef EXR_READER_WINDOWS_SHELL
      status=shelf_restore(&session,&control,&page,&shelf_offset,&shelf_found,&error);
      if(status==EXR_OK && !shelf_found)
#endif
      status = session.bounded ? bounded_restore(&session, &control, &page, job->message, 512, &error)
                               : reflow_restore(&session, &control, &page, job->message, 512);
      if (status == EXR_OK) status = render_reflow(&session, page, &job->frame, &control, &error);
#ifdef EXR_READER_WINDOWS_SHELL
      if(status==EXR_OK && shelf_found) {
        status=shell_align_anchor(&session,shelf_offset,&job->frame,&control,&error);
        job->shelf_restored=1;job->target_offset=shelf_offset;
      }
#else
      (void)shelf_offset;(void)shelf_found;
#endif
    }
  }
#if defined(EXR_READER_WINDOWS_SEARCH) || defined(EXR_READER_WINDOWS_NAVIGATION) || defined(EXR_READER_WINDOWS_RECORDS)
  if(status==EXR_OK) {
    exr_control control={job_cancel_check,NULL,job};
    status=winreader_identity(book.id,book.format,session.fixed,session.bounded,session.source_key,&control,&error);
  }
#endif
  if (status == EXR_OK && job_cancel_flag(job)) {
    session_clear(&session);
    book_clear(&book);
    return EXR_CANCELLED;
  }
#if defined(EXR_READER_WINDOWS_WAVE3) && defined(EXR_READER_WINDOWS_RAW3)
  if (status == EXR_OK) status = w3_prepare_open(job, &book, &error);
#endif
  if (status == EXR_OK) {
    session.active = 1;
    job->have_frame = 1;
    job->page_count = session.page_count;
    job->session_swapped = 1;
    job->candidate = session;
    {
      const char *title = book.title ? book.title : "Untitled";
      wchar_t *wide = host_wide(title, strlen(title));
      copy_wstring(job->frame.title, 256, wide ? wide : L"Untitled");
      free(wide);
    }
  } else {
    session_clear(&session);
  }
  if (status == EXR_OK) { job->opened_book = book; memset(&book, 0, sizeof(book)); }
  book_clear(&book);
  if (status != EXR_OK) job->error = error;
  return status;
}

static exr_status chapter_last_page(exr_pager *pager, size_t *page, exr_error *error) {
  size_t lo = 0, hi = 1; const exr_layout *layout = NULL; exr_status status;
  status = exr_pager_get(pager, 0, &layout, error); if (status != EXR_OK) return status;
  for (;;) {
    status = exr_pager_get(pager, hi, &layout, error);
    if (pager_eof(status, error)) break;
    if (status != EXR_OK) return status;
    lo = hi; if (hi >= 1000000) return EXR_LIMIT; hi = hi > 500000 ? 1000000 : hi * 2;
  }
  while (lo + 1 < hi) {
    size_t mid = lo + (hi - lo) / 2;
    status = exr_pager_get(pager, mid, &layout, error);
    if (status == EXR_OK) lo = mid;
    else if (pager_eof(status, error)) hi = mid;
    else return status;
  }
  *page = lo; memset(error, 0, sizeof(*error)); return EXR_OK;
}

/* Resolve a coalesced wheel move across publication parts without rendering
   the skipped pages. Own at most one temporary pager until UI acceptance. */
static exr_status job_bounded_batch(host_job *job) {
  host_session candidate=g.session;exr_pager *owned=NULL;exr_error error={0};
  exr_control control={job_cancel_check,NULL,job};exr_status status=EXR_OK;
  size_t count=0,page=g.frame.page,part=candidate.part;
  const exr_part *parts=exr_publication_parts(candidate.publication,&count);
  if(!parts || part>=count)return EXR_FORMAT;
  candidate.hold_progress=0;
  size_t left=(size_t)(job->batch_delta<0?-(int64_t)job->batch_delta:job->batch_delta);
  while(left && status==EXR_OK) {
    if(job_cancel_check(job)) { status=EXR_CANCELLED;break; }
    if(job->batch_delta>0) {
      const exr_layout *layout=NULL;size_t last;
      if(left>SIZE_MAX-page) { status=EXR_LIMIT;break; }
      status=exr_pager_get(candidate.pager,page+left,&layout,&error);
      if(status==EXR_OK) { page+=left;break; }
      if(!pager_eof(status,&error))break;
      status=chapter_last_page(candidate.pager,&last,&error);if(status!=EXR_OK)break;
      left-=last-page+1;
      size_t next=part+1;while(next<count && !parts[next].in_reading_order)next++;
      if(next==count) { page=last;job->at_end=1;break; }
      part=next;page=0;
    } else {
      if(left<=page) { page-=left;break; }
      left-=page+1;size_t prev=part;
      while(prev && !parts[--prev].in_reading_order) {}
      if(prev==part || !parts[prev].in_reading_order) {page=0;break;}
      part=prev;
    }
    exr_pager *next=NULL;status=bounded_pager(&candidate,part,&next,&error);
    if(status!=EXR_OK)break;
    exr_pager_free(owned);owned=next;candidate.pager=next;candidate.part=part;
    if(job->batch_delta<0)status=chapter_last_page(next,&page,&error);
  }
  if(status==EXR_OK)status=render_reflow(&candidate,page,&job->frame,&control,&error);
  if(status==EXR_OK) {
    job->have_frame=1;job->applied_page=page;
    if(owned) {job->candidate_pager=owned;owned=NULL;job->candidate_config=candidate.config;}
  } else job->error=error;
  exr_pager_free(owned);return status;
}
#ifdef EXR_READER_WINDOWS_SHELL
static exr_status shell_align_anchor(host_session *,size_t,host_frame *,const exr_control *,exr_error *);
#endif
static exr_status job_bounded_go(host_job *job) {
  if(!job->use_offset && (job->batch_delta>1 || job->batch_delta<-1))return job_bounded_batch(job);
  host_session candidate = g.session; exr_pager *pager = NULL;
  exr_error error = {0}; exr_status status = EXR_OK;
  exr_control control = {job_cancel_check, NULL, job};
  const exr_part *parts; size_t count = 0, part = candidate.part, page = job->target_page;
  int switching = 0;
  if (!job->use_offset && job->direction) candidate.hold_progress = 0;
  parts = exr_publication_parts(candidate.publication, &count);
  if (job->use_offset) {
    part = job->target_part;
    if (part >= count || !parts[part].in_reading_order || !job->part_path || strcmp(parts[part].path, job->part_path)) return EXR_ARGUMENT;
    switching = part != candidate.part;
  } else if (job->direction < 0 && g.frame.page == 0 && page == SIZE_MAX) {
    size_t at = part;
    while (at && !parts[--at].in_reading_order) {}
    if (at == part || !parts[at].in_reading_order) return EXR_ARGUMENT;
    part = at; switching = 1;
  }
  if (switching) {
    status = bounded_pager(&candidate, part, &pager, &error);
    if (status != EXR_OK) { job->error = error; return status; }
    candidate.pager = pager; candidate.part = part;
    if (!job->use_offset && job->direction < 0) status = chapter_last_page(pager, &page, &error);
  }
  if (status == EXR_OK && job->use_offset) {
    exr_anchor_match match;
    status = exr_pager_anchor_resolve(candidate.pager, &job->anchor, &control, &match, &error);
    if (status == EXR_OK && match.state != EXR_ANCHOR_FOUND) {
      copy_wstring(job->message, 512, match.state == EXR_ANCHOR_AMBIGUOUS ? L"标注定位存在歧义，未跳转。" : L"标注原文未匹配，未跳转。");
      status = EXR_ARGUMENT;
    }
    if (status == EXR_OK) {
      job->note_start = match.start; job->note_end = match.end; job->resolved_selection = 1;
      status = page_for_offset(&candidate, match.start, &control, &page, NULL, NULL, &error);
    }
  }
  if (status == EXR_OK && page == SIZE_MAX) status = chapter_last_page(candidate.pager, &page, &error);
  if (status == EXR_OK) status = render_reflow(&candidate, page, &job->frame, &control, &error);
#ifdef EXR_READER_WINDOWS_SHELL
  if(status==EXR_OK && job->shell_toc_jump) status=shell_align_anchor(&candidate,job->note_start,&job->frame,&control,&error);
#endif
  if (!switching && !job->use_offset && job->direction > 0 && pager_eof(status, &error)) {
    size_t at = part + 1;
    while (at < count && !parts[at].in_reading_order) at++;
    if (at < count) {
      status = bounded_pager(&candidate, at, &pager, &error);
      if (status == EXR_OK) {
        candidate.pager = pager; candidate.part = at;
        status = render_reflow(&candidate, 0, &job->frame, &control, &error);
      }
    } else job->at_end = 1;
  }
  if (status == EXR_OK) {
    job->have_frame = 1; job->applied_page = job->frame.page;
    if (pager) { job->candidate_pager = pager; pager = NULL; job->candidate_config = candidate.config; }
  }
  exr_pager_free(pager); if (status != EXR_OK) job->error = error; return status;
}

#ifdef EXR_READER_WINDOWS_SHELL
#include "windows/shell_anchor.inc"
#endif

static exr_status job_go(host_job *job) {
  LONG layout_before=host_probe_layout_calls;
  LONG render_before=host_probe_render_calls;
  exr_error error = {0};
  exr_status status;
  if (!g.session.active) return EXR_ARGUMENT;
  if (job->book_id && job->book_id != g.session.book_id) return EXR_CANCELLED;
#ifdef EXR_READER_WINDOWS_SHELL
  if (g.session.shell_geometry.enabled && g.frame.shell_anchored && !job->use_offset &&
      job->direction > 0 && job->batch_delta == 1) {
    exr_control control = {job_cancel_check, NULL, job};
    size_t page = g.frame.page, offset = g.frame.range_end;
    const exr_layout *layout = NULL;
    /* The joined viewport ends in this page or a nearby following page.
       Walk that tail; do not replay a distant book from page zero. */
    for (;;) {
      size_t count = 0;
      status = exr_pager_get(g.session.pager, page, &layout, &error);
      if (status != EXR_OK) break;
      const exr_page *info = exr_layout_pages(layout, &count);
      if (!info || !count) { status = EXR_FORMAT; break; }
      if (offset < info->end) break;
      page++;
    }
    if (status == EXR_OK) {
      if (g.session.txt) {
        if (status == EXR_OK) status = txt_frame(&g.session, &g.session.txt_source, layout, page, &job->frame, &error);
      } else
      status = render_reflow(&g.session, page, &job->frame, &control, &error);
    }
    if (status == EXR_OK && offset < job->frame.range_end) {
      status = shell_align_anchor(&g.session, offset, &job->frame, &control, &error);
      if (status == EXR_OK) { job->have_frame = 1; job->applied_page = page; job->page_count = g.session.page_count; }
      else job->error = error;
      return status;
    }
    frame_clear(&job->frame);
    /* At chapter EOF the existing next-chapter path still owns traversal. */
    if (status != EXR_OK && !pager_eof(status, &error)) { job->error = error; return status; }
  }
#endif
  if(!job->use_offset) {
    int i=page_cache_find(g.session.book_id,g.session.part,job->target_page);
    if(i>=0) {
      frame_move(&job->frame,&page_cache[i]);job->frame.generation=++g.frame_sequence;job->frame.hold_progress=0;
      job->have_frame=1;job->applied_page=job->frame.page;job->page_count=g.session.page_count;
      host_probe_log("cache_hit",(double)job->frame.page);
      host_probe_log("cache_layout_delta",(double)(host_probe_layout_calls-layout_before));
      host_probe_log("cache_render_delta",(double)(host_probe_render_calls-render_before));
#ifdef EXR_READER_WINDOWS_PREFERENCES
      return prefs_commit(job,EXR_OK);
#else
      return EXR_OK;
#endif
    }
  }

#ifdef EXR_READER_WINDOWS_TXT_RECOVERY
  if (g.session.txt) return job_txt_go(job);
#endif
  if (g.session.bounded) return job_bounded_go(job);
  if (g.session.fixed) {
    size_t count = g.session.page_count;
    if (!count) return EXR_FORMAT;
    if (job->target_page >= count) return EXR_ARGUMENT;
    exr_control control = {job_cancel_check, NULL, job};
    status = render_fixed(&g.session, job->target_page,
                          job->zoom_percent > 0 ? job->zoom_percent : g.zoom_percent,
                          &job->frame, &control, &error);
  } else {
    exr_control control = {job_cancel_check, NULL, job};
    size_t page = job->target_page;
    if (job->use_offset && job->has_anchor) {
      exr_anchor_match match;
      status = exr_anchor_resolve_ex(g.session.document, &job->anchor, &control, &match, &error);
      if (status != EXR_OK) return status;
      if (match.state != EXR_ANCHOR_FOUND) {
        copy_wstring(job->message, 512, match.state == EXR_ANCHOR_AMBIGUOUS ?
          L"标注定位存在歧义，未跳转。" : L"标注原文未匹配，未跳转。");
        return EXR_ARGUMENT;
      }
      job->target_offset = match.start; job->note_start = match.start; job->note_end = match.end;
      job->resolved_selection = 1;
    }
    if (job->use_offset) {
      status = page_for_offset(&g.session, job->target_offset, &control, &page, NULL, NULL, &error);
    } else {
      status = EXR_OK;
    }
    if (status == EXR_OK) status = render_reflow(&g.session, page, &job->frame, &control, &error);
#ifdef EXR_READER_WINDOWS_SHELL
    if(status==EXR_OK && job->shell_toc_jump) status=shell_align_anchor(&g.session,job->target_offset,&job->frame,&control,&error);
#endif
  }
  if (status == EXR_OK) {
    job->have_frame = 1;
    job->applied_page = job->frame.page;
    job->page_count = g.session.page_count;
  }
#ifdef EXR_READER_WINDOWS_PREFERENCES
  return prefs_commit(job, status);
#else
  return status;
#endif
}

static exr_status job_layout(host_job *job) {
  exr_error error = {0};
  exr_status status;
  exr_pager *pager = NULL;
  exr_layout_config config;
  exr_control control = {job_cancel_check, NULL, job};
  size_t page = 0;
  size_t offset = job->has_anchor ? job->anchor.start : 0;
#ifdef EXR_READER_WINDOWS_PREFERENCES
  uint32_t background = g.session.background, foreground = g.session.foreground;
  int themed = g.session.themed;
  if (job->prefs_valid) {
    background = prefs_background_of(&job->prefs, job->system_theme);
    foreground = prefs_foreground_of(&job->prefs, job->system_theme);
    themed = 1;
  }
#endif
#ifdef EXR_READER_WINDOWS_SHELL
  if (g.session.fixed) {
    host_session candidate = g.session; candidate.shell_geometry = job->shell_geometry;
    status = render_fixed(&candidate, g.frame.page, job->zoom_percent, &job->frame, &control, &error);
    job->have_frame = status == EXR_OK; job->error = error;
    return status;
  }
#endif
  config = g.session.config;
#ifdef EXR_READER_WINDOWS_PREFERENCES
  if (job->prefs_valid) {
    config.page.margin = job->prefs.margin;
    config.page.font_size = job->prefs.font_size;
    config.page.line_height = job->prefs.line_spacing;
    config.page.paragraph_spacing = job->prefs.paragraph_spacing;
  } else
#endif
  config.page.font_size = 28.0f * (float)job->font_percent / 100.0f;
#ifdef EXR_READER_WINDOWS_SHELL
  if (job->shell_geometry.enabled || g.session.shell_geometry.enabled) {
    host_session target = {0}; session_configure(&target, job); config = target.config;
    shell_pager_builds++;
  }
#endif
  config.control.cancelled = host_cancel_check;
  config.control.context = NULL;
#if defined(EXR_READER_WINDOWS_TXT_PROGRESS) || defined(EXR_READER_WINDOWS_SHELL)
  if (g.session.txt) {
    host_session candidate = g.session;
    exr_source source = g.session.txt_source;
    HANDLE copy = NULL;
    const exr_layout *laid = NULL;
    if (!DuplicateHandle(GetCurrentProcess(), (HANDLE)source.context, GetCurrentProcess(),
                         &copy, 0, FALSE, DUPLICATE_SAME_ACCESS)) return EXR_IO;
    source.context = copy;
    candidate.config = config;
    candidate.config.user_css = NULL; /* The public TXT pager has no CSS interface. */
    config.user_css = NULL;
#ifdef EXR_READER_WINDOWS_SHELL
    candidate.shell_geometry = job->shell_geometry;
#endif
    status = exr_txt_pager_create(&source, g.font, &config, &pager, &error);
    if (status != EXR_OK) { CloseHandle(copy); return status; }
    copy = NULL; /* the new pager owns this handle */
    if (status == EXR_OK) status = exr_pager_set_cache(pager, 2, 8 * 1024 * 1024, &error);
    if (status == EXR_OK) status = exr_pager_set_checkpoints(pager, 8, 4 * 1024 * 1024, 8, &error);
    if (status == EXR_OK && job->txt_offset > (uint64_t)SIZE_MAX) status = EXR_ARGUMENT;
    candidate.pager = pager;
    candidate.txt_source = source;
    if (status == EXR_OK)
      status = page_for_offset(&candidate, (size_t)job->txt_offset, &control, &page, NULL, NULL, &error);
    if (status == EXR_OK) status = exr_pager_get(pager, page, &laid, &error);
    if (status == EXR_OK && !laid) status = EXR_FORMAT;
    if (status == EXR_OK) status = txt_frame(&candidate, &source, laid, page, &job->frame, &error);
#ifdef EXR_READER_WINDOWS_SHELL
    if (status == EXR_OK) status = shell_align_anchor(&candidate, (size_t)job->txt_offset, &job->frame, &control, &error);
#endif
    if (status == EXR_OK) {
      job->candidate_pager = pager; pager = NULL;
      job->candidate_config = config;
      job->candidate.txt_source = source;
      job->have_frame = 1; job->applied_page = page; job->session_swapped = 0;
      copy_wstring(job->message, 512, L"已按内容位置重新排版。");
    }
    if (pager) exr_pager_free(pager);
    job->error = error;
    return status;
  }
#endif
  if (!g.session.active || g.session.fixed || (!g.session.document && !g.session.bounded)) return EXR_ARGUMENT;
  if (job->book_id && job->book_id != g.session.book_id) return EXR_CANCELLED;
  if (g.session.bounded) {
    host_session candidate = g.session; exr_anchor point = {0}; exr_anchor_match match;
    status = job->has_anchor ? (host_anchor_copy(&point, &job->anchor) ? EXR_OK : EXR_MEMORY) :
      exr_pager_anchor_create(g.session.pager, g.frame.range_start, g.frame.range_start, &control, &point, &error);
    candidate.config = config;
#ifdef EXR_READER_WINDOWS_SHELL
    candidate.shell_geometry = job->shell_geometry;
#endif
#ifdef EXR_READER_WINDOWS_PREFERENCES
    candidate.background = background;
    candidate.foreground = foreground;
    candidate.themed = themed;
#endif
    if (status == EXR_OK) status = bounded_pager(&candidate, candidate.part, &pager, &error);
    candidate.pager = pager;
    if (status == EXR_OK) status = exr_pager_anchor_resolve(pager, &point, &control, &match, &error);
    if (status == EXR_OK) {
      size_t target = match.state == EXR_ANCHOR_FOUND ? match.start : point.start;
      offset = target;
      if (match.state != EXR_ANCHOR_FOUND) {
        host_text_sink sink = {NULL, 0, 0};
        status = exr_pager_read_text(pager, target, target, page_text_sink, &sink, &control, &error);
        candidate.hold_progress = 1;
        copy_wstring(job->message, 512, L"字号变化时锚点未唯一匹配，按原章内偏移重排（未精确锚定）；保留原进度记录。");
      }
      if (status == EXR_OK) status = page_for_offset(&candidate, target, &control, &page, NULL, NULL, &error);
    }
    if (status == EXR_OK) status = render_reflow(&candidate, page, &job->frame, &control, &error);
#ifdef EXR_READER_WINDOWS_SHELL
    if (status == EXR_OK) status = shell_align_anchor(&candidate, offset, &job->frame, &control, &error);
#endif
    exr_anchor_free(&point);
    if (status == EXR_OK) {
      job->candidate_pager = pager; job->candidate_config = config; job->have_frame = 1; job->applied_page = page;
    } else exr_pager_free(pager);
    job->error = error;
#ifdef EXR_READER_WINDOWS_PREFERENCES
    return prefs_commit(job, status);
#else
    return status;
#endif
  }
#ifdef EXR_READER_WINDOWS_PREFERENCES
  status = prefs_page_pager(g.session.document, &config, themed, foreground, &pager, &error);
#else
  status = exr_pager_create(g.session.document, g.font, &config, &pager, &error);
#endif
  if (status == EXR_OK) status = exr_pager_set_cache(pager, 2, 0, &error);
  if (status == EXR_OK) status = exr_pager_set_checkpoints(pager, 8, 4 * 1024 * 1024, 8, &error);
  if (status == EXR_OK && job->has_anchor) {
    exr_anchor_match match;
    exr_status resolved = exr_anchor_resolve_ex(g.session.document, &job->anchor, &control, &match, &error);
    if (resolved != EXR_OK) {
      exr_pager_free(pager);
#ifdef EXR_READER_WINDOWS_PREFERENCES
      return prefs_commit(job, resolved);
#else
      return resolved;
#endif
    }
    if (resolved == EXR_OK && match.state == EXR_ANCHOR_FOUND)
      offset = match.start;
    else if (resolved == EXR_OK && match.state == EXR_ANCHOR_AMBIGUOUS)
      copy_wstring(job->message, 512, L"字号变化时锚点存在歧义，已按保存的文本偏移重排。");
    else
      copy_wstring(job->message, 512, L"字号变化时锚点未匹配，已按保存的文本偏移重排。");
    memset(&error, 0, sizeof(error));
  }
  if (status == EXR_OK) {
    host_session candidate = g.session;
    candidate.pager = pager;
    candidate.config = config;
#ifdef EXR_READER_WINDOWS_SHELL
    candidate.shell_geometry = job->shell_geometry;
#endif
#ifdef EXR_READER_WINDOWS_PREFERENCES
    candidate.background = background;
    candidate.foreground = foreground;
    candidate.themed = themed;
#endif
    status = page_for_offset(&candidate, offset, &control, &page, NULL, NULL, &error);
    if (status == EXR_OK)
      status = render_reflow(&candidate, page, &job->frame, &control, &error);
#ifdef EXR_READER_WINDOWS_SHELL
    if (status == EXR_OK) status = shell_align_anchor(&candidate, offset, &job->frame, &control, &error);
#endif
    if (status == EXR_OK) {
      job->candidate_pager = pager; pager = NULL;
      job->candidate_config = config;
      job->have_frame = 1;
      job->applied_page = page;
      job->session_swapped = 0;
    }
  }
  if (pager) exr_pager_free(pager);
#ifdef EXR_READER_WINDOWS_PREFERENCES
  return prefs_commit(job, status);
#else
  return status;
#endif
}

static exr_status read_import_file(host_job *job, void **data, size_t *size, exr_error *error) {
  HANDLE file;
  LARGE_INTEGER extent;
  size_t total, at = 0;
  unsigned char *buffer;
  DWORD got;
  if (!data || !size) return EXR_ARGUMENT;
  *data = NULL;
  *size = 0;
  file = CreateFileW(job->path, GENERIC_READ, FILE_SHARE_READ, NULL, OPEN_EXISTING,
                     FILE_ATTRIBUTE_NORMAL | FILE_FLAG_SEQUENTIAL_SCAN, NULL);
  if (file == INVALID_HANDLE_VALUE) {
    strcpy(error->message, "Cannot open the selected file");
    return EXR_IO;
  }
  if (!GetFileSizeEx(file, &extent) || extent.QuadPart <= 0) {
    CloseHandle(file);
    strcpy(error->message, "Selected file is empty");
    return EXR_FORMAT;
  }
  if (extent.QuadPart > (LONGLONG)HOST_IMPORT_LIMIT) {
    CloseHandle(file);
    strcpy(error->message, "Selected file exceeds the 96 MiB host import limit");
    return EXR_LIMIT;
  }
  total = (size_t)extent.QuadPart;
  buffer = malloc(total);
  if (!buffer) {
    CloseHandle(file);
    return EXR_MEMORY;
  }
  while (at < total) {
    DWORD chunk = (DWORD)((total - at) > 262144 ? 262144 : (total - at));
    if (job_cancel_flag(job)) {
      free(buffer);
      CloseHandle(file);
      strcpy(error->message, "Import cancelled before the SDK call");
      return EXR_CANCELLED;
    }
    job_pause(job);
    if (!ReadFile(file, buffer + at, chunk, &got, NULL) || got != chunk) {
      free(buffer);
      CloseHandle(file);
      strcpy(error->message, "Cannot read the selected file");
      return EXR_IO;
    }
    at += got;
    InterlockedExchange(&job->progress, (LONG)((at * 100) / total));
    if (g.window) PostMessageW(g.window, WM_HOST_PROGRESS, 0, 0);
  }
  CloseHandle(file);
  *data = buffer;
  *size = total;
  return EXR_OK;
}

static exr_status rollback_import(host_job *job) {
  exr_status status = EXR_OK;
  if (job->created && job->imported_id > 0) {
    EnterCriticalSection(&g.library_lock);
    status = exr_library_delete(g.library, job->imported_id, &job->error);
    LeaveCriticalSection(&g.library_lock);
    if (status != EXR_OK) {
      job->rollback_failed = 1;
      copy_wstring(job->message, 512, L"取消导入后删除失败；新书仍在数据库中，请重试删除。");
      return status;
    }
    job->created = 0;
  }
  job->imported = 0;
  return EXR_CANCELLED;
}

static exr_status job_note(host_job *job) {
  exr_status status;
  exr_control control = {job_cancel_check, NULL, job};
  if (job_cancel_flag(job)) return EXR_CANCELLED;
  if (!g.session.active || job->book_id != g.session.book_id) return EXR_CANCELLED;
  EnterCriticalSection(&g.library_lock);
  if (job->note_fixed) {
    exr_fixed_note note = {0};
    note.id = job->note_id; note.book_id = job->book_id;
    note.page = job->target_page; note.start = job->note_start; note.end = job->note_end; note.text = job->comment;
#ifdef EXR_HOST_WORKER_REVIEW
    review_pause(1, job);
#endif
    status = exr_library_fixed_note(g.library, &note, &control, &job->note_id, &job->error);
  } else if (g.session.bounded) {
    exr_epub_note note = {0}; const exr_part *parts; size_t count = 0;
    note.id = job->note_id; note.book_id = job->book_id; note.text = job->comment;
    if (job->kind == JOB_NOTE_ADD) {
      parts = exr_publication_parts(g.session.publication, &count);
      if (g.session.part >= count || job->target_part != g.session.part) status = EXR_ARGUMENT;
      else {
        status = exr_pager_anchor_create(g.session.pager, job->note_start, job->note_end, &control, &job->anchor, &job->error);
        if (status == EXR_OK) {
          job->has_anchor = 1; note.location.part = g.session.part; note.location.path = (char *)parts[g.session.part].path;
          note.location.selector = job->anchor;
          status = exr_library_epub_note(g.library, &note, &job->note_id, &job->error);
        }
      }
    } else status = exr_library_epub_note(g.library, &note, &job->note_id, &job->error);
  } else if (job->kind == JOB_NOTE_UPDATE) {
    status = exr_library_note_text(g.library, job->note_id, job->comment, &job->error);
  } else {
    exr_note note = {0};
    note.book_id = job->book_id; note.start = job->note_start; note.end = job->note_end;
    note.text = job->comment; note.anchor = job->anchor;
    status = exr_library_note(g.library, &note, &job->note_id, &job->error);
  }
  LeaveCriticalSection(&g.library_lock);
  return status;
}

typedef struct { HANDLE file; host_job *job; } host_import_source;
static size_t import_source_read(void *context, uint64_t offset, void *buffer, size_t size) {
  host_import_source *source = context; LARGE_INTEGER position; DWORD got = 0;
  if (size > MAXDWORD || job_cancel_flag(source->job)) return 0;
  position.QuadPart = (LONGLONG)offset;
  if (!SetFilePointerEx(source->file, position, NULL, FILE_BEGIN) || !ReadFile(source->file, buffer, (DWORD)size, &got, NULL)) return 0;
  return got;
}
static void import_source_progress(void *context, exr_stage stage, uint64_t done, uint64_t total) {
  host_job *job = context; (void)stage;
  InterlockedExchange(&job->progress, total ? (LONG)(done * 100 / total) : 0);
  if (g.window) PostMessageW(g.window, WM_HOST_PROGRESS, 0, 0);
}
static exr_status import_bounded_epub(host_job *job, int64_t *id, int *created, exr_error *error) {
  host_import_source context; exr_source source = {0}; LARGE_INTEGER length; exr_status status;
  context.job = job;
  context.file = CreateFileW(job->path, GENERIC_READ, FILE_SHARE_READ, NULL, OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, NULL);
  if (context.file == INVALID_HANDLE_VALUE) return EXR_IO;
  if (!GetFileSizeEx(context.file, &length) || length.QuadPart <= 0) status = EXR_FORMAT;
  else if ((uint64_t)length.QuadPart > HOST_IMPORT_LIMIT) status = EXR_LIMIT;
  else {
    source.size = (uint64_t)length.QuadPart; source.read_at = import_source_read; source.context = &context;
    source.control.cancelled = job_cancel_check; source.control.progress = import_source_progress; source.control.context = job;
    EnterCriticalSection(&g.library_lock);
    status = exr_library_import_source_unique(g.library, EXR_EPUB, &source, NULL, id, created, error);
    LeaveCriticalSection(&g.library_lock);
  }
  CloseHandle(context.file); return status;
}

#ifdef EXR_READER_WINDOWS_TXT_RECOVERY
static exr_status product_import_original(host_job *job);
#endif
static exr_status job_import(host_job *job) {
  exr_format format;
  exr_error error = {0};
  exr_status status;
  void *data = NULL;
  size_t size = 0;
  char *path = NULL;
  int created = 0;
  int64_t id = 0;
  if (!format_for_path(job->path, &format)) {
    copy_wstring(job->message, 512, L"不支持的扩展名；当前宿主接受 .epub .pdf .cbz .txt .html .fb2 .docx .rtf .mobi .azw3。");
    return EXR_UNSUPPORTED;
  }
#ifdef EXR_READER_WINDOWS_TXT_RECOVERY
  if (format == EXR_TXT) {
    WIN32_FILE_ATTRIBUTE_DATA attributes;
    if (GetFileAttributesExW(job->path, GetFileExInfoStandard, &attributes)) {
      uint64_t bytes = ((uint64_t)attributes.nFileSizeHigh << 32) | attributes.nFileSizeLow;
      if (bytes > 16ULL * 1024 * 1024) return product_import_original(job);
    }
  }
#endif
  status = format == EXR_EPUB ? EXR_OK : read_import_file(job, &data, &size, &error);
  if (status != EXR_OK) return status;
  path = host_utf8(job->path);
  if (!path) {
    free(data);
    return EXR_MEMORY;
  }
  if (job_cancel_flag(job)) {
    free(path);
    free(data);
    return EXR_CANCELLED;
  }
  if (format == EXR_EPUB) status = import_bounded_epub(job, &id, &created, &error);
  else {
    EnterCriticalSection(&g.library_lock);
    status = exr_library_import_unique(g.library, format, data, size, NULL, &id, &created, &error);
    LeaveCriticalSection(&g.library_lock);
  }
  free(path);
  free(data);
  if (status == EXR_OK) {
    job->imported = 1;
    job->imported_id = id;
    job->created = created;
#ifdef EXR_HOST_WORKER_REVIEW
    review_pause(3, job);
#endif
    if (job_cancel_flag(job)) return rollback_import(job);
  }
  if (status != EXR_OK) job->error = error;
  return status;
}

#ifdef EXR_READER_PRODUCT_CATALOG
#include EXR_READER_WINDOWS_PRODUCT_HEADER
#endif
#ifdef EXR_READER_DESKTOP_METADATA
#include "../apps/reader/desktop/windows_metadata.inc"
#endif
#ifdef EXR_READER_WINDOWS_ACCOUNT
#include "../apps/reader/desktop/windows_accounts.inc"
#endif
#ifdef EXR_READER_WINDOWS_IMPORT_ORGANIZE
#include "../apps/reader/desktop/windows_import_organize.inc"
#endif
#ifdef EXR_READER_WINDOWS_PREFERENCES
#include "../apps/reader/desktop/windows_preferences.inc"
#endif
/* SDK entry points execute in WM_HOST_SDK_JOB on the UI thread. This worker
   borrows the job until UI joins it; it never calls exr_* or frees SDK objects. */
static unsigned __stdcall job_thread(void *context) {
  host_job *job=context;
  double start=host_probe_ms();
  host_probe_log("pixel_thread_id",(double)GetCurrentThreadId());
  job_pause(job);
  if(job->status==EXR_OK && job->frame.valid)frame_prepare_display(&job->frame);
  host_probe_log("pixel_copy_ms",host_probe_ms()-start);
  if(job->kind==JOB_GO && job->status==EXR_OK && job->frame.valid)host_probe_log("frame_ready_gen",(double)job->frame.generation);
#ifdef EXR_HOST_WORKER_REVIEW
  if (job->status == EXR_OK) {
    int stage=job->kind==JOB_OPEN ? 4:job->kind==JOB_GO ? 2:0;
#ifdef EXR_HOST_SHELF_REVIEW
    if(job->kind==JOB_PRODUCT_SHELF) stage=5;
#endif
    review_pause(stage,job);
  }
#endif
  PostMessageW(g.window,WM_HOST_COMPLETE,0,(LPARAM)job);
  return 0;
}

static void job_finish_sdk(host_job *job) {
  host_probe_require_ui();
  if (job->status == EXR_OK && job_cancel_flag(job) && job->kind != JOB_NOTE_ADD && job->kind != JOB_NOTE_UPDATE
      && !job_preferences_committed(job)
#ifdef EXR_READER_WINDOWS_WAVE3
      && job->kind != JOB_WAVE3
#endif
#ifdef EXR_READER_WINDOWS_IMPORT_ORGANIZE
      && !winio_kind(job->kind)
#endif
#ifdef EXR_READER_DESKTOP_METADATA
      && !metadata_job_kind(job->kind)
#endif
#ifdef EXR_READER_PRODUCT_CATALOG
      && !(job->kind==JOB_PRODUCT_DELETE && job->product_deleted)
#endif
#ifdef EXR_READER_WINDOWS_TXT_RECOVERY
      && !job->original_import
#endif
  )
    job->status = job->kind == JOB_IMPORT ? rollback_import(job) : EXR_CANCELLED;
  if (job->status == EXR_CANCELLED) frame_clear(&job->frame);
}

static exr_status job_hit(host_job *job) {
  const exr_layout *layout = NULL; exr_status status;
  if ((!g.session.bounded && !g.session.txt) || (g.session.txt && g.session.txt_pager_invalid) ||
      g.session.book_id != job->book_id || g.session.part != job->target_part ||
      g.frame.generation != job->generation || g.frame.page != job->target_page) return EXR_CANCELLED;
  status = exr_pager_get(g.session.pager, job->target_page, &layout, &job->error);
  if (status != EXR_OK) return status;
  job->hit_offset = exr_layout_hit_test(layout, 0, job->hit_x, job->hit_y);
  if (job->hit_offset == SIZE_MAX || job->hit_offset < g.frame.range_start || job->hit_offset > g.frame.range_end) return EXR_ARGUMENT;
  return EXR_OK;
}

static exr_status job_save(host_job *job) {
  exr_epub_location location = {0}; exr_status status;
  if (!g.session.bounded || job->book_id != g.frame.book_id || job->generation != g.frame.generation ||
      job->target_part != g.frame.part) return EXR_ARGUMENT;
  location.part = job->target_part; location.path = job->part_path; location.selector = job->anchor;
  EnterCriticalSection(&g.library_lock);
  status = exr_library_epub_progress(g.library, job->book_id, &location, &job->error);
  LeaveCriticalSection(&g.library_lock); return status;
}

static exr_status job_run(host_job *job) {
  host_probe_require_ui();
  switch (job->kind) {
#ifdef EXR_READER_WINDOWS_IMPORT_ORGANIZE
    case JOB_IMPORT_ORGANIZE: return winio_job_run(job);
#endif
#ifdef EXR_READER_WINDOWS_PREFERENCES
    case JOB_PREFERENCES: return prefs_job(job);
#endif
#ifdef EXR_READER_WINDOWS_WAVE3
    case JOB_WAVE3: return w3_run(job);
#endif
    case JOB_OPEN: return job_open(job);
    case JOB_GO: return job_go(job);
    case JOB_PREFETCH: {
      exr_control control={job_cancel_check,NULL,job};exr_error error={0};
      host_probe_log("prefetch_begin",(double)job->target_page);
      if(g.session.fixed) return render_fixed(&g.session,job->target_page,g.zoom_percent,&job->frame,&control,&error);
      return render_reflow(&g.session,job->target_page,&job->frame,&control,&error);
    }
    case JOB_LAYOUT: return job_layout(job);
    case JOB_IMPORT: return job_import(job);
    case JOB_NOTE_ADD: case JOB_NOTE_UPDATE: return job_note(job);
    case JOB_ROLLBACK: return rollback_import(job);
    case JOB_HIT: return job_hit(job);
    case JOB_SAVE: return job_save(job);
#ifdef EXR_READER_WINDOWS_TXT_PROGRESS
    case JOB_TXT_PROGRESS: return job_txt_progress(job);
#endif
#ifdef EXR_READER_WINDOWS_SEARCH
    case JOB_SEARCH_BATCH: case JOB_SEARCH_OPEN: return winsearch_job(job);
#endif
#ifdef EXR_READER_WINDOWS_NAVIGATION
    case JOB_NAVIGATION_ROWS: case JOB_NAVIGATION_OPEN: return winnav_job(job);
#endif
#ifdef EXR_READER_WINDOWS_RECORDS
    case JOB_RECORDS: return winrecords_job(job);
#endif
#ifdef EXR_READER_DESKTOP_METADATA
    case JOB_METADATA_PREPARE: case JOB_METADATA_SAVE: case JOB_METADATA_RETRY: case JOB_METADATA_DISCARD:
      return metadata_job_run(job);
#endif
#ifdef EXR_READER_WINDOWS_ACCOUNT
    case JOB_ACCOUNT_LOAD: case JOB_ACCOUNT_SET: case JOB_ACCOUNT_FORGET: case JOB_ACCOUNT_STAGE: case JOB_ACCOUNT_RECEIVE:
      return account_job_run(job);
#endif
#ifdef EXR_READER_PRODUCT_CATALOG
    case JOB_PRODUCT_ATTACH: case JOB_PRODUCT_REPAIR: case JOB_PRODUCT_DELETE: case JOB_PRODUCT_SHELF: return product_job_run(job);
#endif
    default: return EXR_ARGUMENT;
  }
}

/* ------------------------------------------------------------------ */
/* Window controls and page view                                       */
/* ------------------------------------------------------------------ */

static void host_command(int id);
static void page_step(int direction);
static inline void change_font(int delta);
static inline void change_zoom(int delta);
static void select_all_page(void);
static void selection_bounds(size_t *start,size_t *end);
static void copy_quote(void);
static inline void add_note(void);
static inline void update_note(void);
static inline void delete_note(void);
static inline void jump_selected_note(void);
static void open_selected_book(void);
static inline void delete_selected_book(void);
static void import_path(const wchar_t *path, int dialog_fallback);
static int save_progress(void);
static void update_page_label(void);
static void handle_job_complete(host_job *job);
/* Used by the accessibility provider, which is compiled before this function. */
static size_t point_offset(int x, int y, int at_end);

static inline HWND make_button(HWND parent, int id, const wchar_t *text) {
  HWND window = CreateWindowExW(0, L"BUTTON", text,
                                WS_CHILD | WS_VISIBLE | WS_TABSTOP,
                                0, 0, 10, 10, parent, (HMENU)(INT_PTR)id, NULL, NULL);
  if (window) SendMessageW(window, WM_SETFONT, (WPARAM)GetStockObject(DEFAULT_GUI_FONT), TRUE);
  return window;
}

static HWND make_static(HWND parent, int id, const wchar_t *text) {
  HWND window = CreateWindowExW(0, L"STATIC", text, WS_CHILD | WS_VISIBLE | SS_LEFT,
                                0, 0, 10, 10, parent, (HMENU)(INT_PTR)id, NULL, NULL);
  if (window) SendMessageW(window, WM_SETFONT, (WPARAM)GetStockObject(DEFAULT_GUI_FONT), TRUE);
  return window;
}
#ifdef EXR_READER_DESKTOP_METADATA
#include "../apps/reader/desktop/windows_metadata_ui.inc"
#endif
#ifdef EXR_READER_WINDOWS_ACCOUNT
#include "../apps/reader/desktop/windows_accounts_ui.inc"
#endif
#ifdef EXR_READER_WINDOWS_IMPORT_ORGANIZE
#include "../apps/reader/desktop/windows_import_organize_ui.inc"
#endif
#if defined(EXR_READER_WINDOWS_SEARCH) || defined(EXR_READER_WINDOWS_NAVIGATION) || defined(EXR_READER_WINDOWS_RECORDS)
#include "../apps/reader/desktop/windows_source.inc"
#endif
#ifdef EXR_READER_WINDOWS_SEARCH
#include "../apps/reader/desktop/windows_search.inc"
#endif
#ifdef EXR_READER_WINDOWS_NAVIGATION
#include "../apps/reader/desktop/windows_navigation.inc"
#endif
#ifdef EXR_READER_WINDOWS_RECORDS
#include "../apps/reader/desktop/windows_records.inc"
#endif
#ifdef EXR_READER_WINDOWS_WAVE3
#include "../apps/reader/desktop/windows_wave3.inc"
#endif
#ifdef EXR_READER_WINDOWS_PREFERENCES
#include "../apps/reader/desktop/windows_preferences_ui.inc"
#endif

#ifdef EXR_READER_WINDOWS_SHELL
static void shell_create(HWND parent);
static void layout_controls(void);
#endif
static void create_controls(HWND parent) {
#ifdef EXR_READER_WINDOWS_SEARCH
  inbook.button = make_button(parent, IDC_INBOOK, L"书内查找(&B)");
#endif
#ifdef EXR_READER_WINDOWS_NAVIGATION
  directory.button=make_button(parent,IDC_DIRECTORY,L"目录(&G)");
#endif
#ifdef EXR_READER_WINDOWS_RECORDS
  records.button=make_button(parent,IDC_RECORDS,L"阅读记录(&L)");
#endif
  g.shelf_label = make_static(parent, IDC_SHELF_LABEL, L"书架");
  g.books = CreateWindowExW(WS_EX_CLIENTEDGE, L"LISTBOX", L"书架",
                            WS_CHILD | WS_TABSTOP | WS_VSCROLL | LBS_NOTIFY | LBS_NOINTEGRALHEIGHT,
                            0, 0, 10, 10, parent, (HMENU)(INT_PTR)IDC_BOOKS, NULL, NULL);
  SendMessageW(g.books, WM_SETFONT, (WPARAM)GetStockObject(DEFAULT_GUI_FONT), TRUE);
#ifdef EXR_READER_PRODUCT_CATALOG
  /* A real static with a mnemonic names the search box (the same native path the
     import field already uses) and gives it an Alt access key. */
  g.shelf_search_label=make_static(parent,IDC_SHELF_SEARCH_LABEL,L"\u641c\u7d22(&S)");
  g.shelf_search=CreateWindowExW(WS_EX_CLIENTEDGE,L"EDIT",L"",WS_CHILD|WS_TABSTOP|ES_AUTOHSCROLL,
    0,0,10,10,parent,(HMENU)(INT_PTR)IDC_SHELF_SEARCH,NULL,NULL);
  SendMessageW(g.shelf_search,WM_SETFONT,(WPARAM)GetStockObject(DEFAULT_GUI_FONT),TRUE);
  SendMessageW(g.shelf_search,EM_SETLIMITTEXT,256,0);
  g.shelf_refresh=make_button(parent,IDC_SHELF_REFRESH,L"刷新(&F)");
#ifdef EXR_READER_DESKTOP_METADATA
  g.metadata_button=make_button(parent,IDC_METADATA_BUTTON,L"详情(&E)");
#endif
#ifdef EXR_READER_WINDOWS_ACCOUNT
  g.account_button=make_button(parent,IDC_ACCOUNT_BUTTON,L"账号(&K)");
#endif
  g.shelf_applying=1;
  wchar_t *shelf_query=host_wide(g.shelf_query ? g.shelf_query:"",g.shelf_query ? strlen(g.shelf_query):0);
  SetWindowTextW(g.shelf_search,shelf_query ? shelf_query:L"");free(shelf_query);g.shelf_applying=0;
  g.shelf_procedure=(WNDPROC)SetWindowLongPtrW(g.books,GWLP_WNDPROC,(LONG_PTR)product_shelf_procedure);
#endif
  g.notes_label = make_static(parent, IDC_NOTES_LABEL, L"标注（双击跳转）");
  g.notes = CreateWindowExW(WS_EX_CLIENTEDGE, L"LISTBOX", L"标注列表",
                            WS_CHILD | WS_TABSTOP | WS_VSCROLL | LBS_NOTIFY | LBS_NOINTEGRALHEIGHT,
                            0, 0, 10, 10, parent, (HMENU)(INT_PTR)IDC_NOTES, NULL, NULL);
  SendMessageW(g.notes, WM_SETFONT, (WPARAM)GetStockObject(DEFAULT_GUI_FONT), TRUE);
  g.note_edit_label = make_static(parent, IDC_NOTE_EDIT_LABEL, L"\u6807\u6ce8\u5185\u5bb9(&M)");
  g.note_edit = CreateWindowExW(WS_EX_CLIENTEDGE, L"EDIT", L"", WS_CHILD | WS_TABSTOP |
                                 ES_MULTILINE | ES_AUTOVSCROLL | WS_VSCROLL,
                                 0, 0, 10, 10, parent, (HMENU)(INT_PTR)IDC_NOTE_EDIT, NULL, NULL);
  SendMessageW(g.note_edit, WM_SETFONT, (WPARAM)GetStockObject(DEFAULT_GUI_FONT), TRUE);
  /* Multiline editing without swallowing Tab: see host_a11y_prepare_note. */
  host_a11y_prepare_note();
  g.page = CreateWindowExW(0, L"EXReaderPage", L"阅读区域",
                           WS_CHILD | WS_TABSTOP, 0, 0, 10, 10, parent,
                           (HMENU)(INT_PTR)IDC_PAGE, NULL, NULL);
  g.page_label = make_static(parent, IDC_PAGE_LABEL, L"未打开书籍");
  g.status = make_static(parent, IDC_STATUS, L"就绪");
  SetWindowLongPtrW(g.status, GWL_STYLE, GetWindowLongPtrW(g.status, GWL_STYLE) | SS_ENDELLIPSIS);
  SetWindowTextW(parent, L"EXReader");
#ifdef EXR_READER_WINDOWS_PREFERENCES
  /* One native menu entry; every low-frequency control lives inside it. */
  prefs_create_menu(parent);
#endif
#ifdef EXR_READER_WINDOWS_SHELL
  /* Model HWNDs are never a screen: only the shell creates visible UI. */
  for(HWND child=GetWindow(parent,GW_CHILD);child;child=GetWindow(child,GW_HWNDNEXT)) ShowWindow(child,SW_HIDE);
  shell_create(parent);
#endif
}

#ifdef EXR_READER_WINDOWS_SHELL
#include "windows/shell_screen.inc"
#endif

static void layout_controls(void) {
#ifdef EXR_READER_WINDOWS_SHELL
  shell_layout();
#else
  RECT area; GetClientRect(g.window, &area);
  MoveWindow(g.page, 0, 0, area.right, area.bottom, TRUE);
  ShowWindow(g.page, SW_SHOWNA);
#endif
}
static int compute_view(void);
#ifdef __GNUC__
/* The shared accessibility owner contains MSVC linker pragmas. */
#pragma GCC diagnostic push
#pragma GCC diagnostic ignored "-Wunknown-pragmas"
#endif
#include "../apps/reader/desktop/windows_accessibility.inc"
#ifdef __GNUC__
#pragma GCC diagnostic pop
#endif

static int compute_view_impl(void) {
  RECT area;
  double scale;
  g.view.valid = 0;
  if (!g.frame.valid || !g.frame.bitmap.width || !g.frame.bitmap.height || !g.page) return 0;
  GetClientRect(g.page, &area);
  if (area.right < 16 || area.bottom < 16) return 0;
#ifdef EXR_READER_WINDOWS_SHELL
  if (shell_active && g.frame.shell_geometry.enabled) {
    int body_top=shell_px(g.frame.shell_geometry.style.top,shell_dpi);
    int body_height=area.bottom-shell_px(g.frame.shell_geometry.style.bottom+SHELL_PAGE_NUMBER_H,shell_dpi)-body_top;
    g.view.scale = 1.0;
    g.view.bw = (int)g.frame.bitmap.width; g.view.bh = (int)g.frame.bitmap.height;
    g.view.dx = shell_px(g.frame.shell_geometry.style.left,shell_dpi);
    g.view.dy = body_top;
    if(!IsRectEmpty(&g.frame.shell_image)) {
      RECT client={0};GetClientRect(g.window,&client);
      host_probe_log("image_client_height",client.bottom);
      host_probe_log("image_page_client_height",area.bottom);
      host_probe_log("image_frame_geometry_height",g.frame.shell_geometry.height);
      const RECT *image=&g.frame.shell_image;
      shell_image_view fit=shell_fit_image(area.right,area.bottom,shell_dpi,shell_font,
        image->right-image->left,image->bottom-image->top);
      host_probe_log("image_fit_body_height",body_height);
      host_probe_log("image_fit_height",fit.height);
      if(fit.width<=0 || fit.height<=0) return 0;
      g.view.bw=fit.width;g.view.bh=fit.height;
      g.view.dx=fit.left;g.view.dy=fit.top;
      g.view.scale=(double)fit.width/(image->right-image->left);
    } else if(g.frame.fixed) {
      g.view.dy+=(body_height-g.view.bh)/2;
    }
    g.view.valid = 1;
    return 1;
  }
#endif
  scale = fmin((area.right - 8.0) / g.frame.bitmap.width,
               (area.bottom - 8.0) / g.frame.bitmap.height);
  if (!(scale > 0) || !isfinite(scale)) return 0;
  g.view.scale = scale;
  g.view.bw = (int)g.frame.bitmap.width;
  g.view.bh = (int)g.frame.bitmap.height;
  g.view.dx = (int)((area.right - g.frame.bitmap.width * scale) / 2);
  g.view.dy = (int)((area.bottom - g.frame.bitmap.height * scale) / 2);
  g.view.valid = 1;
  return 1;
}

static int compute_view(void) {
  double start=host_probe_ms();int valid=compute_view_impl();
  host_probe_log("shift_ms",host_probe_ms()-start);return valid;
}

static void selection_bounds(size_t *start, size_t *end) {
  size_t a = g.selection.start, b = g.selection.end;
  if (a > b) { size_t t = a; a = b; b = t; }
  *start = a;
  *end = b;
}

static void paint_selection(HDC dc) {
#ifdef EXR_READER_WINDOWS_SHELL
  if (shell_active && !g.frame.fixed) { shell_selection_paint(dc); return; }
#endif
  size_t start, end;
  if (g.job || g.pending || !g.selection.active || !g.frame.valid) return;
  if (g.session.book_id != g.frame.book_id) return;
  selection_bounds(&start, &end);
  if (start == end) return;
  if (!g.frame.fixed) {
    const exr_glyph *glyphs;
    size_t count = 0, i;
    if (g.session.page != g.frame.page || g.session.part != g.frame.part) return;
    if (g.frame.bounded || g.session.txt) { glyphs = g.frame.glyphs; count = g.frame.glyph_count; }
    else if (g.frame.hit_layout) glyphs = exr_layout_glyphs(g.frame.hit_layout, &count);
    else return;
    if (!glyphs) return;
    for (i = 0; i < count; i++) {
      const exr_glyph *glyph = &glyphs[i];
      int left, top, w, h;
      if (glyph->flags & EXR_GLYPH_HIDDEN) continue;
      if (glyph->cluster_end <= start || glyph->cluster_start >= end) continue;
      left = g.view.dx + (int)(glyph->x * g.view.scale);
      w = (int)(glyph->advance * g.view.scale);
      if (w < 1) w = 1;
      top = g.view.dy + (int)((glyph->baseline - glyph->size) * g.view.scale);
      h = (int)(glyph->size * 1.25 * g.view.scale);
      if (h < 1) h = 1;
      PatBlt(dc, left, top, w, h, DSTINVERT);
    }
  } else {
    exr_text_region *regions = NULL;
    size_t count = 0, i;
    exr_error error = {0};
    exr_viewport viewport;
    if (!g.frame.fixed_text || g.session.page != g.frame.page) return;
    if (exr_fixed_text_select(g.frame.fixed_text, start, end, NULL, &regions, &count, &error) != EXR_OK)
      return;
    if (exr_viewport_create(&g.frame.geometry, g.frame.render_scale, &viewport, &error) != EXR_OK) {
      exr_free(regions);
      return;
    }
    SetROP2(dc, R2_NOT);
    SelectObject(dc, GetStockObject(NULL_PEN));
    SelectObject(dc, GetStockObject(BLACK_BRUSH));
    for (i = 0; i < count; i++) {
      POINT points[4];
      int j;
      for (j = 0; j < 4; j++) {
        double sx = regions[i].quad[j * 2], sy = regions[i].quad[j * 2 + 1];
        double vx = viewport.matrix[0] * sx + viewport.matrix[2] * sy + viewport.matrix[4];
        double vy = viewport.matrix[1] * sx + viewport.matrix[3] * sy + viewport.matrix[5];
        points[j].x = g.view.dx + (LONG)(vx * g.view.scale);
        points[j].y = g.view.dy + (LONG)(vy * g.view.scale);
      }
      Polygon(dc, points, 4);
    }
    SetROP2(dc, R2_COPYPEN);
    exr_free(regions);
  }
}

static HDC page_buffer_dc;
static HBITMAP page_buffer_bitmap;
static HGDIOBJ page_buffer_old;
static int page_buffer_width, page_buffer_height;
static int page_buffer_has_page;
static unsigned long page_buffer_generation;
#ifdef EXR_READER_WINDOWS_SHELL
static shell_geometry page_buffer_geometry;
/* A resize is debounced. Until its frame is ready, do not submit an old-size
   buffer. Completion invalidates the page and resumes presentation. Compare
   the live snapshot, since child WM_SIZE precedes the parent's layout request. */
static int page_frame_current(void) {
  return !shell_active || (g.frame.valid &&
    shell_geometry_equal(g.frame.shell_geometry,shell_snapshot()));
}
#endif
static void page_buffer_release(void) {
  if(page_buffer_dc && page_buffer_old)SelectObject(page_buffer_dc,page_buffer_old);
  if(page_buffer_bitmap)DeleteObject(page_buffer_bitmap);
  if(page_buffer_dc)DeleteDC(page_buffer_dc);
  page_buffer_old=NULL;
  page_buffer_dc=NULL;page_buffer_bitmap=NULL;page_buffer_width=page_buffer_height=0;
  page_buffer_has_page=0;page_buffer_generation=0;
}
static void compose_page_view(HWND window) {
#ifdef EXR_READER_WINDOWS_SHELL
  if(!page_frame_current())return;
#endif
  double paint_start=host_probe_ms();
  host_probe_log("compose_begin_gen",(double)g.frame.generation);
  HDC screen = GetDC(window), dc;
  RECT area;
  GetClientRect(window, &area);
  if(area.right<=0 || area.bottom<=0){ReleaseDC(window,screen);return;}
  if(!page_buffer_dc || page_buffer_width!=area.right || page_buffer_height!=area.bottom) {
    page_buffer_release();
    page_buffer_dc=CreateCompatibleDC(screen);
    page_buffer_bitmap=CreateCompatibleBitmap(screen,area.right,area.bottom);
    if(!page_buffer_dc || !page_buffer_bitmap){page_buffer_release();ReleaseDC(window,screen);return;}
    page_buffer_old=SelectObject(page_buffer_dc,page_buffer_bitmap);
    page_buffer_width=area.right;page_buffer_height=area.bottom;
    host_probe_log("buffer_alloc",1);
  }
  dc=page_buffer_dc;
  page_buffer_has_page=0;page_buffer_generation=g.frame.generation;
#ifdef EXR_READER_WINDOWS_SHELL
  page_buffer_geometry=g.frame.shell_geometry;
  if(shell_active) {
    HBRUSH bg=CreateSolidBrush(shell_colorref(shell_colors->layer_page));
    FillRect(dc,&area,bg);DeleteObject(bg);
    shell_color_display(&g.frame);
  } else
#endif
  FillRect(dc, &area, (HBRUSH)GetStockObject(WHITE_BRUSH));
  if (g.frame.valid && compute_view()) {
    last_page_rect=(RECT){g.view.dx,g.view.dy,g.view.dx+(LONG)(g.frame.bitmap.width*g.view.scale)+2,g.view.dy+(LONG)(g.frame.bitmap.height*g.view.scale)+2};
    last_page_rect_valid=1;
    BITMAPINFO info;
    memset(&info, 0, sizeof(info));
    info.bmiHeader.biSize = sizeof(BITMAPINFOHEADER);
    info.bmiHeader.biWidth = (LONG)g.frame.bitmap.width;
    info.bmiHeader.biHeight = -(LONG)g.frame.bitmap.height;
    info.bmiHeader.biPlanes = 1;
    info.bmiHeader.biBitCount = 32;
    info.bmiHeader.biCompression = BI_RGB;
    SetStretchBltMode(dc, HALFTONE);
    SetBrushOrgEx(dc, 0, 0, NULL);
#ifdef EXR_READER_WINDOWS_SHELL
    if(shell_active && !IsRectEmpty(&g.frame.shell_image)) {
      RECT source=g.frame.shell_image;
      RECT image={g.view.dx,g.view.dy,g.view.dx+g.view.bw,g.view.dy+g.view.bh};
      const uint32_t *pixels=g.frame.shell_image_pixels ? g.frame.shell_image_pixels : g.frame.dib;
      unsigned pitch=g.frame.shell_image_pixels ? (unsigned)source.right*4 : g.frame.bitmap.width*4;
      page_buffer_has_page=SUCCEEDED(shell_d2d_page_image(host_shell,dc,&area,&image,
        (unsigned)source.right,(unsigned)source.bottom,pixels,pitch,shell_colors->layer_page));
    } else
#endif
    if(frame_prepare_display(&g.frame)) {
      HDC source=CreateCompatibleDC(dc);
      if(source) {
        HGDIOBJ old=SelectObject(source,g.frame.display_bitmap);
        page_buffer_has_page=BitBlt(dc,g.view.dx,g.view.dy,g.frame.display_width,g.frame.display_height,source,0,0,SRCCOPY)!=0;
        if(host_probe_counting)host_probe_bitblt++;
        SelectObject(source,old);DeleteDC(source);
      }
    }
#ifdef EXR_READER_WINDOWS_SHELL
    /* Shell display allocation failure stays observable as a blank submission;
       never fall through to a scaling or direct-DIB presentation path. */
    else if (g.frame.shell_geometry.enabled) host_probe_log("display_prepare_failed",1);
#endif
    else {
      if(host_probe_counting)InterlockedIncrement(&host_probe_stretch);
      page_buffer_has_page=StretchDIBits(dc, g.view.dx, g.view.dy,
                  (int)(g.frame.bitmap.width * g.view.scale),
                  (int)(g.frame.bitmap.height * g.view.scale),
                  0, 0, (int)g.frame.bitmap.width, (int)g.frame.bitmap.height,
                  g.frame.dib, &info, DIB_RGB_COLORS, SRCCOPY)>0;
    }
#ifdef EXR_READER_WINDOWS_SHELL
    if(shell_active) shell_search_paint(dc);
#endif
    paint_selection(dc);
  } else {
    const wchar_t *hint = L"打开一本书开始阅读\n\n导入 EPUB/PDF/CBZ 后从左侧书架打开";
    RECT text = area;
    SetBkMode(dc, TRANSPARENT);
#ifdef EXR_READER_WINDOWS_SHELL
    if(shell_active) SetTextColor(dc,shell_colorref(shell_colors->text_secondary));else
#endif
    SetTextColor(dc, shell_contrast ? GetSysColor(COLOR_WINDOWTEXT) : RGB(90, 90, 90));
    DrawTextW(dc, hint, -1, &text, DT_CENTER | DT_VCENTER | DT_WORDBREAK);
  }
#ifdef EXR_READER_WINDOWS_SHELL
  gesture_overlay(dc,&area);
  if (shell_page_footer(dc, &area)) {
  } else
#endif
  if (GetFocus() == window) {
    RECT focus = area;
    focus.left += 1; focus.top += 1; focus.right -= 1; focus.bottom -= 1;
    DrawFocusRect(dc, &focus);
  }
  host_probe_stamp(dc,&area,g.frame.generation);
  ReleaseDC(window,screen);
  host_probe_log("compose_ms",host_probe_ms()-paint_start);
}
static void paint_page_view(HWND window) {
  PAINTSTRUCT paint;double start=host_probe_ms();
  host_probe_log("paint",0);
  RECT area;GetClientRect(window,&area);
#ifdef EXR_READER_WINDOWS_SHELL
  if(!page_frame_current()) {
    BeginPaint(window,&paint);EndPaint(window,&paint);
    if(host_probe_counting)host_probe_deferred++;
    return;
  }
#endif
  if(!page_buffer_dc || page_buffer_width!=area.right || page_buffer_height!=area.bottom)
    compose_page_view(window);
  HDC screen=BeginPaint(window,&paint);
  double blit_start=host_probe_ms();
  int submitted=0,stale=0;
#ifdef EXR_READER_WINDOWS_SHELL
  stale=shell_active && !shell_geometry_equal(page_buffer_geometry,shell_snapshot());
#endif
  if(page_buffer_dc && !stale)submitted=BitBlt(screen,paint.rcPaint.left,paint.rcPaint.top,
    paint.rcPaint.right-paint.rcPaint.left,paint.rcPaint.bottom-paint.rcPaint.top,
    page_buffer_dc,paint.rcPaint.left,paint.rcPaint.top,SRCCOPY);
  host_probe_log("blit_ms",host_probe_ms()-blit_start);
  EndPaint(window,&paint);host_probe_log("paint_ms",host_probe_ms()-start);
  host_probe_present((double)g.frame.generation);
#ifdef EXR_READER_WINDOWS_SHELL
  if(shell_active) {
    host_probe_log("presented",1);
    if(shell_is_dark()) host_probe_log("dark_presented",1);
    if(!page_buffer_dc || !g.frame.valid) host_probe_log("blank",1);
  }
#endif
  if(host_probe_counting && submitted) {
    host_probe_log("present_client_w",area.right);host_probe_log("present_client_h",area.bottom);
    host_probe_log("present_buffer_w",page_buffer_width);host_probe_log("present_buffer_h",page_buffer_height);
#ifdef EXR_READER_WINDOWS_SHELL
    shell_geometry expected=shell_snapshot();
    host_probe_log("present_page_w",page_buffer_geometry.width);host_probe_log("present_page_h",page_buffer_geometry.height);
    host_probe_log("present_expected_w",expected.width);host_probe_log("present_expected_h",expected.height);
#endif
  }
  host_probe_submission(submitted,page_buffer_has_page,stale,(double)page_buffer_generation);
}

static size_t point_offset(int x, int y, int at_end) {
  float lx, ly;
  if (g.job || g.pending) return SIZE_MAX;
  if (!g.view.valid && !compute_view()) return SIZE_MAX;
  if (g.session.book_id != g.frame.book_id) return SIZE_MAX;
  lx = (float)((x - g.view.dx) / g.view.scale);
  ly = (float)((y - g.view.dy) / g.view.scale);
  if (lx < 0 || ly < 0 || lx > g.frame.bitmap.width || ly > g.frame.bitmap.height) return SIZE_MAX;
  if (!g.frame.fixed) {
    size_t offset;
    if (!g.frame.hit_layout || g.session.page != g.frame.page) return SIZE_MAX;
    offset = exr_layout_hit_test(g.frame.hit_layout, 0, lx, ly);
    if (offset == SIZE_MAX) return SIZE_MAX;
    if (offset < g.frame.range_start) offset = g.frame.range_start;
    if (offset > g.frame.range_end) offset = g.frame.range_end;
    return offset;
  } else {
    exr_error error = {0};
    exr_viewport viewport;
    const exr_text_region *regions;
    size_t count = 0, region = SIZE_MAX;
    double sx, sy;
    if (!g.frame.fixed_text || g.session.page != g.frame.page) return SIZE_MAX;
    if (exr_viewport_create(&g.frame.geometry, g.frame.render_scale, &viewport, &error) != EXR_OK)
      return SIZE_MAX;
    sx = viewport.inverse[0] * lx + viewport.inverse[2] * ly + viewport.inverse[4];
    sy = viewport.inverse[1] * lx + viewport.inverse[3] * ly + viewport.inverse[5];
    if (exr_fixed_text_hit(g.frame.fixed_text, sx, sy, 80.0, EXR_REGION_INVISIBLE, NULL,
                           &region, &error) != EXR_OK || region == SIZE_MAX)
      return SIZE_MAX;
    regions = exr_fixed_text_regions(g.frame.fixed_text, &count);
    if (!regions || region >= count) return SIZE_MAX;
    return at_end ? regions[region].end : regions[region].start;
  }
}

static void bounded_hit(float x, float y, int down, int up) {
  host_job *job;
  if (g.job) {
    if (g.job->kind == JOB_HIT && !down) { g.hit_pending = 1; g.hit_x = x; g.hit_y = y; g.hit_up |= up; }
    return;
  }
  job = job_new(JOB_HIT); if (!job) return;
  job->book_id = g.frame.book_id; job->target_part = g.frame.part; job->target_page = g.frame.page;
  job->generation = g.frame.generation; job->gesture = g.gesture;
  job->hit_x = x; job->hit_y = y; job->hit_down = down; job->hit_up = up;
  job_submit(job);
}

static void bounded_mouse(int x, int y, int down, int up) {
  if (!g.view.valid && !compute_view()) return;
#ifdef EXR_READER_WINDOWS_SHELL
  if (shell_active && (x < g.view.dx || y < g.view.dy ||
      x >= g.view.dx + g.view.bw || y >= g.view.dy + g.view.bh)) {
    if (up) { dragging = 0; if (GetCapture() == g.page) ReleaseCapture(); }
    return;
  }
#endif
  if (down) {
    g.gesture++; g.hit_pending = g.hit_up = 0; memset(&g.selection, 0, sizeof(g.selection));
    dragging = 1; SetCapture(g.page);
  }
  if (!dragging) return;
  bounded_hit((float)((x - g.view.dx) / g.view.scale), (float)((y - g.view.dy) / g.view.scale), down, up);
  if (up) { dragging = 0; if (GetCapture() == g.page) ReleaseCapture(); }
}

static void selection_report(void) {
  size_t start, end;
  selection_bounds(&start, &end);
  if (!g.selection.active || start == end) {
    set_status(L"未选择到文字。请拖动选择或使用“全选本页”。");
    return;
  }
  if (g.session.txt) set_statusf(L"已选择 %llu 字节文字 · 可复制引用。", (unsigned long long)(end - start));
  else set_statusf(L"已选择 %llu 字节文字 · 可复制引用或添加标注。", (unsigned long long)(end - start));
}

#ifdef EXR_READER_WINDOWS_SHELL
#include "windows/shell_selection.inc"
#include "windows/shell_annotations.inc"
#include "windows/shell_footnotes.inc"
#include "windows/shell_recent.inc"
#include "windows/shell_shelfmeta.inc"
#include "windows/shell_opds.inc"
#include "windows/shell_gestures.inc"
#include "windows/shell_tts.inc"
#include "windows/shell_dictionary.inc"
#include "windows/shell_sync.inc"
#include "windows/shell_docedit.inc"
#include "windows/shell_docedit_toolbar.inc"
#include "windows/shell_docedit_outline.inc"
#include "windows/shell_docedit_paint.inc"
#include "windows/shell_docedit_input.inc"
#endif
static LRESULT CALLBACK page_procedure(HWND window, UINT message, WPARAM wparam, LPARAM lparam) {
#ifdef EXR_READER_WINDOWS_SHELL
  if (de_message(window,message,wparam,lparam)) return 0;
  if (shell_gesture_message(window, message, wparam, lparam)) return 0;
  if (shell_selection_message(window, message, wparam, lparam)) return 0;
#endif
  switch (message) {
    case WM_ERASEBKGND: return 1;
    case WM_PAINT:
      paint_page_view(window);
      return 0;
    case WM_SIZE:
      page_dirty(window,1);
      return 0;
    case WM_SETFOCUS:
    case WM_KILLFOCUS:
      page_dirty(window,1);
      return 0;
    case WM_GETOBJECT:
      return host_a11y_page_object(window, wparam, lparam);
    case WM_NCDESTROY:
      page_buffer_release();
      host_a11y_page_destroyed();
      return DefWindowProcW(window, message, wparam, lparam);
    case HOST_A11Y_CALL: {
      /* A provider call from another thread runs here, on the UI thread. */
      host_a11y_task *task = (host_a11y_task *)lparam;
      if (task && task->fn) task->fn(task->context);
      return 0;
    }
    case WM_GETDLGCODE:
      return DLGC_WANTARROWS | DLGC_WANTCHARS;
#ifdef EXR_READER_WINDOWS_SHELL
    case WM_UPDATEUISTATE:
      /* The focus outline depends on the cue state; the buffer must follow it. */
      {
        LRESULT done = DefWindowProcW(window, message, wparam, lparam); /* updates the state first */
        if (shell_active) page_dirty(window, 1);
        return done;
      }
#endif
    case WM_LBUTTONDOWN:
#ifdef EXR_READER_WINDOWS_SHELL
      if(shell_toc_open) {shell_toc_set(0,0);SetFocus(window);return 0;}
#endif
      if (g.job || g.pending || !g.frame.valid) return 0;
      SetFocus(window);
#ifdef EXR_READER_WINDOWS_PREFERENCES
      prefs_press_active = 1;
      prefs_press_x = (short)LOWORD(lparam);
      prefs_press_y = (short)HIWORD(lparam);
#endif
      if (g.frame.bounded || g.session.txt) { bounded_mouse((short)LOWORD(lparam), (short)HIWORD(lparam), 1, 0); return 0; }
      {
        size_t offset = point_offset((short)LOWORD(lparam), (short)HIWORD(lparam), 0);
        if (offset == SIZE_MAX) {
          set_status(L"该位置没有可选文字。");
          return 0;
        }
        dragging = 1;
        memset(&g.selection, 0, sizeof(g.selection));
        g.selection.start = g.selection.end = offset;
        g.selection.page = g.frame.page;
        g.selection.fixed = g.frame.fixed;
        SetCapture(window);
        page_dirty(window,0);
      }
      return 0;
    case WM_MOUSEMOVE:
      if ((g.frame.bounded || g.session.txt) && dragging) { bounded_mouse((short)LOWORD(lparam), (short)HIWORD(lparam), 0, 0); return 0; }
      if (g.job || g.pending) return 0;
      if (dragging) {
        size_t offset = point_offset((short)LOWORD(lparam), (short)HIWORD(lparam), 1);
        if (offset != SIZE_MAX && offset != g.selection.end) {
          g.selection.end = offset;
          page_dirty(window,0);
        }
      }
      return 0;
    case WM_LBUTTONUP:
#ifdef EXR_READER_WINDOWS_PREFERENCES
      if (prefs.active && prefs_press_active) {
        RECT area;
        int dx = (short)LOWORD(lparam) - prefs_press_x;
        int dy = (short)HIWORD(lparam) - prefs_press_y;
        int turn = prefs_turn_from_swipe(dx, dy);
        prefs_press_active = 0;
        if (!turn && dx <= PREFS_TAP_DISTANCE && dx >= -PREFS_TAP_DISTANCE &&
            dy <= PREFS_TAP_DISTANCE && dy >= -PREFS_TAP_DISTANCE) {
          GetClientRect(window, &area);
          turn = prefs_turn_from_tap(prefs_press_x, prefs_press_y, area.right, area.bottom);
        }
        if (turn) {
          dragging = 0;
          g.hit_pending = g.hit_up = 0;
          if (GetCapture() == window) ReleaseCapture();
          memset(&g.selection, 0, sizeof(g.selection));
          if (g.job || g.pending) prefs_turn_pending = turn;
          else page_step(turn);
          page_dirty(window,0);
          return 0;
        }
      }
#endif
      if ((g.frame.bounded || g.session.txt) && dragging) { bounded_mouse((short)LOWORD(lparam), (short)HIWORD(lparam), 0, 1); return 0; }
      if (g.job || g.pending) { dragging = 0; if (GetCapture() == window) ReleaseCapture(); return 0; }
      if (dragging) {
        size_t offset = point_offset((short)LOWORD(lparam), (short)HIWORD(lparam), 1);
        if (offset != SIZE_MAX) g.selection.end = offset;
        dragging = 0;
        ReleaseCapture();
        {
          size_t start, end;
          selection_bounds(&start, &end);
          g.selection.start = start;
          g.selection.end = end;
          g.selection.active = start < end;
        }
        selection_report();
        page_dirty(window,0);
        host_a11y_page_changed(1);
      }
      return 0;
    case WM_MOUSEWHEEL:
#ifdef EXR_READER_WINDOWS_SHELL
      sm_activity();
#endif
      host_probe_log("wheel",(short)HIWORD(wparam));
      wheel_delta += (short)HIWORD(wparam);
      SetTimer(window,PAGE_WHEEL_TIMER,16,NULL);
      return 0;
    case WM_TIMER:
      if(wparam==HOST_PROBE_BURST_TIMER) {
        SendMessageW(window,WM_MOUSEWHEEL,MAKEWPARAM(0,-WHEEL_DELTA),0);
        if(--host_probe_burst_left<=0)KillTimer(window,HOST_PROBE_BURST_TIMER);
        return 0;
      }
      if(wparam==PAGE_WHEEL_TIMER) {
        if((g.job && g.job->kind!=JOB_PREFETCH) || g.pending)return 0;
        int steps=(int)(wheel_delta/WHEEL_DELTA);
        if(steps) {
          if(g.session.txt)steps=steps>0?1:-1;
          wheel_delta-=(long)steps*WHEEL_DELTA;page_step(-steps);
        } else KillTimer(window,PAGE_WHEEL_TIMER);
        return 0;
      }
      break;
    case WM_KEYDOWN:
      host_probe_log("key",(double)wparam);
      if ((g.job && g.job->kind!=JOB_PREFETCH) || g.pending) return 0;
      switch (wparam) {
#ifdef EXR_READER_WINDOWS_PREFERENCES
        /* An open input-method composition owns the key: never turn a page. */
        case VK_PROCESSKEY: break;
#endif
        case VK_LEFT: case VK_PRIOR:
#ifdef EXR_READER_WINDOWS_PREFERENCES
          if (prefs.active) { page_step(prefs_turn_from_key(wparam)); return 0; }
#endif
          page_step(wparam==VK_LEFT && exr_publication_page_progression(g.session.publication)==EXR_DIRECTION_RTL ? 1 : -1); return 0;
        case VK_RIGHT: case VK_NEXT:
#ifdef EXR_READER_WINDOWS_PREFERENCES
          if (prefs.active) { page_step(prefs_turn_from_key(wparam)); return 0; }
#endif
          page_step(wparam==VK_RIGHT && exr_publication_page_progression(g.session.publication)==EXR_DIRECTION_RTL ? -1 : 1); return 0;
        case VK_DOWN:
#ifdef EXR_READER_WINDOWS_PREFERENCES
          if (prefs.active) { page_step(prefs_turn_from_key(VK_DOWN)); return 0; }
#endif
          break;
        case VK_UP:
#ifdef EXR_READER_WINDOWS_PREFERENCES
          if (prefs.active) { page_step(prefs_turn_from_key(VK_UP)); return 0; }
#endif
          break;
        case VK_HOME: page_step(-1000000); return 0;
        case 'A':
          if (GetKeyState(VK_CONTROL) & 0x8000) { select_all_page(); return 0; }
          break;
        case 'C':
          if (GetKeyState(VK_CONTROL) & 0x8000) { copy_quote(); return 0; }
          break;
        case 'O':
          if (GetKeyState(VK_CONTROL) & 0x8000) { host_command(HOST_CMD_OPEN); return 0; }
          break;
        case 'I':
          if (GetKeyState(VK_CONTROL) & 0x8000) { host_command(HOST_CMD_IMPORT); return 0; }
          break;
        case VK_ESCAPE:
          selection_clear();
          set_status(L"已清除选择。");
          return 0;
      }
      break;
  }
  return DefWindowProcW(window, message, wparam, lparam);
}

/* ------------------------------------------------------------------ */
/* Commands                                                            */
/* ------------------------------------------------------------------ */

static void update_page_label(void) {
  host_a11y_page_changed(0);
  if (!g.frame.valid || !g.has_current) {
    SetWindowTextW(g.page_label, L"未打开书籍");
    return;
  }
  if (g.frame.fixed) {
    wchar_t text[256];
    swprintf(text, 256, L"第 %llu / %llu 页 · %ls · 缩放 %d%%",
             (unsigned long long)(g.frame.page + 1),
             (unsigned long long)(g.frame.page_count ? g.frame.page_count : g.frame.page + 1),
             format_name(g.current.format), g.zoom_percent);
    SetWindowTextW(g.page_label, text);
  } else {
    wchar_t text[256];
#ifdef EXR_READER_WINDOWS_PREFERENCES
    if (prefs.active && !g.session.txt) {
      swprintf(text, 256, L"第 %llu 页 · %ls · 字号 %.1f 磅",
               (unsigned long long)(g.frame.page + 1), format_name(g.current.format),
               (double)prefs.value.font_size);
      SetWindowTextW(g.page_label, text);
      return;
    }
#endif
    if (g.session.bounded) swprintf(text, 256, L"章 %llu · 本章第 %llu 页 · EPUB · 字号 %d%%",
             (unsigned long long)(g.frame.part + 1), (unsigned long long)(g.frame.page + 1), g.font_percent);
    else swprintf(text, 256, L"第 %llu 页 · %ls · 字号 %d%%",
             (unsigned long long)(g.frame.page + 1),
             format_name(g.current.format), g.font_percent);
    SetWindowTextW(g.page_label, text);
  }
}

#ifdef EXR_READER_WINDOWS_TXT_PROGRESS
/* A TXT position is a product revision, so the accepted page is written on the
   serialized worker. The write is skipped while the in-memory page did not move
   by a whole block; close, book switch and relayout force it. */
static int save_txt_progress(void) {
  host_job *job;
  reader_txp_position captured = {0};
  reader_txp_error detail = {0};
  const uint64_t offset = (uint64_t)g.frame.range_start;
  size_t take = g.frame.text_bytes;
  const int force = g.txt_force_save;
  g.txt_force_save = 0;
  if (!g.session.txt_key[0] || g.txt_save_abandoned) return 1;
  if (g.session.hold_progress || g.frame.hold_progress) return 1;
  if (!force && g.txt_saved_valid && !strcmp(g.txt_saved_key, g.session.txt_key)) {
    const uint64_t moved = offset > g.txt_saved_offset ? offset - g.txt_saved_offset : g.txt_saved_offset - offset;
    if (moved < HOST_TXT_SAVE_BYTES) return 1;
  }
  if (reader_txp_capture(&captured, offset, g.frame.utf8, take, &detail) != READER_TXP_OK) {
    set_status(L"无法记录阅读位置：文本位置不在可表示范围内；原记录保留。");
    return 0;
  }
  job = job_new(JOB_TXT_PROGRESS);
  if (!job) { set_status(L"内存不足，未保存阅读位置。"); return 0; }
  snprintf(job->txt_key, sizeof(job->txt_key), "%s", g.session.txt_key);
  job->txt_offset = captured.offset;
  memcpy(job->txt_context, captured.context, captured.context_bytes);
  job->txt_context[captured.context_bytes] = 0;
  job->txt_context_bytes = captured.context_bytes;
  job_start(job);
  return 1;
}
#endif

static int save_progress(void) {
  exr_error error = {0};
  exr_status status;
  if (!g.has_current || !g.session.active || !g.frame.valid || g.job || g.pending) return 1;
#ifdef EXR_READER_WINDOWS_TXT_PROGRESS
  if (g.session.txt) return save_txt_progress();
#endif
  if (g.session.txt) return 1;
  if (g.session.book_id != g.current.id || g.frame.book_id != g.current.id || g.frame.fixed != g.session.fixed) {
    g.progress_failed = 1; set_status(L"书籍状态不一致，未覆盖原进度。"); return 0;
  }
  if (g.session.bounded) {
    host_job *job; const exr_part *parts; size_t count = 0;
    if (g.session.hold_progress) return 1;
    if (!g.progress_failed && g.saved_generation == g.frame.generation) return 1;
    parts = exr_publication_parts(g.session.publication, &count);
    if (g.frame.part != g.session.part || g.frame.part >= count || !g.frame.point.exact) {
      g.progress_failed = 1; set_status(L"章节状态不一致，未覆盖原进度。"); return 0;
    }
    job = job_new(JOB_SAVE);
    if (!job) { g.progress_failed = 1; set_status(L"内存不足，未保存阅读位置。"); return 0; }
    job->book_id = g.frame.book_id; job->target_part = g.frame.part; job->generation = g.frame.generation;
    job->part_path = host_strdup(parts[g.frame.part].path);
    job->has_anchor = 1; job->anchor_host_owned = 1;
    if (!job->part_path || !host_anchor_copy(&job->anchor, &g.frame.point)) {
      job_release(job); g.progress_failed = 1; set_status(L"内存不足，未保存阅读位置。"); return 0;
    }
    job_start(job); return 1;
  }
  status = EXR_MEMORY;
  EnterCriticalSection(&g.library_lock);
  if (g.session.fixed) {
    exr_book snapshot;
    if (book_copy(&snapshot, &g.current)) {
      snapshot.position = g.frame.page;
      status = exr_library_update(g.library, &snapshot, &error);
      book_clear(&snapshot);
    }
  } else {
    exr_anchor anchor = {0};
    status = exr_anchor_create(g.session.document, g.frame.range_start, g.frame.range_start,
                               &anchor, &error);
    if (status == EXR_OK) {
      status = exr_library_progress(g.library, g.current.id, &anchor, &error);
      exr_anchor_free(&anchor);
    }
  }
  LeaveCriticalSection(&g.library_lock);
  g.progress_failed = status != EXR_OK;
  if (status != EXR_OK) {
    wchar_t message[512]; describe_error(message, 512, L"保存进度失败，请重试", status, &error); set_status(message);
    return 0;
  }
  g.current.position = g.session.bounded ? 0 : g.frame.fixed ? g.frame.page : g.frame.range_start;
  {
    int index = shelf_index(g.current.id);
    if (index >= 0) g.shelf[index].position = g.current.position;
  }
  return 1;
}

static void apply_pending_selection(void) {
  size_t start, end;
  if (!g.pending_selection) return;
  g.pending_selection = 0;
  if (!g.has_current || g.pending_book != g.current.id || !g.frame.valid) return;
  if (g.session.bounded && g.pending_part != g.frame.part) return;
  start = g.pending_start;
  end = g.pending_end;
  if (start == SIZE_MAX || end == SIZE_MAX || start >= end) return;
  if (g.frame.fixed) {
    if (end > g.frame.text_bytes) return;
  } else if (start < g.frame.range_start || end > g.frame.range_end) {
    return;
  }
  g.selection.active = 1;
  g.selection.fixed = g.frame.fixed;
  g.selection.page = g.frame.page;
  g.selection.start = start;
  g.selection.end = end;
  page_dirty(g.page,0);
  set_statusf(L"已跳转到标注位置（第 %llu 页），并高亮原文。",
              (unsigned long long)(g.frame.page + 1));
}

static void page_step(int direction) {
#ifdef EXR_READER_WINDOWS_SHELL
  sm_activity();
#endif
  size_t target;
  host_job *job;
  if (!g.has_current || !g.frame.valid || (g.job && g.job->kind!=JOB_PREFETCH) || g.pending) return;
  if (g.session.txt && direction >= 1000000) { set_status(L"TXT 跳到末页尚未实现。"); return; }
  if (!direction) return;
  if (direction <= -1000000) target = 0;
  else if (direction >= 1000000) target = (size_t)-1;
  else if (direction < 0 && (g.frame.fixed || !g.session.bounded) && (size_t)(-direction) > g.frame.page) target = 0;
  else target = (direction > 0) ? g.frame.page + (size_t)direction : g.frame.page - (size_t)(-direction);
  if (g.frame.fixed) {
    if (direction <= -1000000) target = 0;
    else if (direction >= 1000000) target = g.frame.page_count ? g.frame.page_count - 1 : 0;
    else if (direction < 0 && g.frame.page == 0) {
      set_status(L"已经是第一页。");
      return;
    } else if (target >= g.frame.page_count) {
      if (direction > 1 && direction < 1000000 && g.frame.page_count) target = g.frame.page_count - 1;
      else { set_status(L"已到最后一页；当前页未改变。");
        return; }
    }
  } else if (direction < 0 && g.frame.page == 0 && !g.session.bounded) {
    set_status(L"已经是第一页。");
    return;
  }
  if (target == g.frame.page && direction > 0 && direction < 1000000) {
    set_status(L"已到最后一页；当前页未改变。");
    return;
  }
  job = job_new(JOB_GO);
  if (!job) { set_status(L"内存不足，无法翻页。"); return; }
  job->book_id = g.current.id;
  job->target_page = target;
  job->batch_delta = (direction>-1000000 && direction<1000000)?direction:0;
  job->direction = direction > 0 ? 1 : -1;
  host_probe_log("frame_request",(double)target);
  if (g.session.bounded && direction < 0 && direction > -1000000 && g.frame.page == 0) job->target_page = SIZE_MAX;
  job_submit(job);
}

static inline void change_font(int delta) {
#ifdef EXR_READER_WINDOWS_SHELL
  if (shell_active && !g.frame.fixed) {
    shell_step_font(delta); return;
  }
#endif
  int next;
  host_job *job;
  exr_anchor anchor = {0};
  exr_error error = {0};
  if (!g.has_current || !g.frame.valid) { set_status(L"请先打开一本书。"); return; }
#ifdef EXR_READER_WINDOWS_TXT_PROGRESS
  /* A TXT relayout keeps the product content position: the new pager is built
     from the same immutable source and the page that owns the current offset is
     accepted, so a different font size lands on the same text. */
  if (g.session.txt) {
    if (g.job || g.pending) return;
    next = g.font_percent + delta;
    if (next < HOST_FONT_MIN) { set_statusf(L"字号已到下限（%d%%）。", HOST_FONT_MIN); return; }
    if (next > HOST_FONT_MAX) { set_statusf(L"字号已到上限（%d%%）。", HOST_FONT_MAX); return; }
    job = job_new(JOB_LAYOUT);
    if (!job) { set_status(L"内存不足，无法重排。"); return; }
    job->font_percent = next;
    job->txt_offset = (uint64_t)g.frame.range_start;
    g.txt_force_save = 1;
    job_submit(job);
    return;
  }
#else
  if (g.session.txt) { set_status(L"TXT 字号调整尚未实现。"); return; }
#endif
  if (g.frame.fixed) { set_status(L"当前是固定页书籍，请使用“缩放+”或“缩放-”。"); return; }
#ifdef EXR_READER_WINDOWS_PREFERENCES
  /* Once a reading preference is accepted it owns the point size. A request
     outside the public range or the page envelope is reported, not clamped. */
  if (prefs.active) {
    reader_preferences candidate = prefs.value;
    float next_font = candidate.font_size + (delta > 0 ? 2.0f : -2.0f);
    if (next_font < PREFS_FONT_MIN) { set_statusf(L"字号已到下限（%.0f 磅）。", (double)PREFS_FONT_MIN); return; }
    if (next_font > PREFS_FONT_MAX) { set_statusf(L"字号已到上限（%.0f 磅）。", (double)PREFS_FONT_MAX); return; }
    candidate.font_size = next_font;
    if (!prefs_geometry_ok(&candidate)) { set_status(L"该字号在当前页面放不下，未应用。"); return; }
    if (g.job || g.pending) return;
    if (!g.session.bounded &&
        exr_anchor_create(g.session.document, g.frame.range_start, g.frame.range_start,
                          &anchor, &error) != EXR_OK) {
      wchar_t message[512];
      describe_error(message, 512, L"无法建立字号重排锚点", error.code, &error);
      set_status(message);
      return;
    }
    job = job_new(JOB_LAYOUT);
    if (!job) { exr_anchor_free(&anchor); set_status(L"内存不足，无法重排。"); return; }
    job->book_id = g.current.id;
    job->font_percent = (int)(next_font + 0.5f);
    job->anchor = anchor;
    job->has_anchor = !g.session.bounded;
    job->prefs = candidate;
    job->prefs_valid = 1;
    job->prefs_persist = 1;
    job_submit(job);
    return;
  }
#endif
  if (g.job || g.pending) return;
  next = g.font_percent + delta;
  if (next < HOST_FONT_MIN) { set_statusf(L"字号已到下限（%d%%）。", HOST_FONT_MIN); return; }
  if (next > HOST_FONT_MAX) { set_statusf(L"字号已到上限（%d%%）。", HOST_FONT_MAX); return; }
  if (!g.session.bounded && exr_anchor_create(g.session.document, g.frame.range_start, g.frame.range_start,
                        &anchor, &error) != EXR_OK) {
    wchar_t message[512];
    describe_error(message, 512, L"无法建立字号重排锚点", error.code, &error);
    set_status(message);
    return;
  }
  job = job_new(JOB_LAYOUT);
  if (!job) { exr_anchor_free(&anchor); set_status(L"内存不足，无法重排。"); return; }
  job->book_id = g.current.id;
  job->font_percent = next;
  job->anchor = anchor;
  job->has_anchor = !g.session.bounded;
  job_submit(job);
}

static inline void change_zoom(int delta) {
  int next;
  host_job *job;
  if (!g.has_current || !g.frame.valid) { set_status(L"请先打开一本书。"); return; }
  if (!g.frame.fixed) { set_status(L"当前是重排书籍，请使用“字号+”或“字号-”。"); return; }
#ifdef EXR_READER_WINDOWS_PREFERENCES
  if (prefs.active) {
    reader_preferences candidate = prefs.value;
    int next_zoom = (int)candidate.fixed_page_zoom + (delta > 0 ? HOST_ZOOM_STEP : -HOST_ZOOM_STEP);
    if (next_zoom < HOST_ZOOM_MIN) { set_statusf(L"缩放已到下限（%d%%）。", HOST_ZOOM_MIN); return; }
    if (next_zoom > HOST_ZOOM_MAX) { set_statusf(L"缩放已到上限（%d%%）。", HOST_ZOOM_MAX); return; }
    if (g.job || g.pending) return;
    candidate.fixed_page_zoom = (uint32_t)next_zoom;
    job = job_new(JOB_GO);
    if (!job) { set_status(L"内存不足，无法缩放。"); return; }
    job->book_id = g.current.id;
    job->target_page = g.frame.page;
    job->zoom_percent = next_zoom;
    job->prefs = candidate;
    job->prefs_valid = 1;
    job->prefs_persist = 1;
    job_submit(job);
    return;
  }
#endif
  if (g.job || g.pending) return;
  next = g.zoom_percent + delta;
  if (next < HOST_ZOOM_MIN) { set_statusf(L"缩放已到下限（%d%%）。", HOST_ZOOM_MIN); return; }
  if (next > HOST_ZOOM_MAX) { set_statusf(L"缩放已到上限（%d%%）。", HOST_ZOOM_MAX); return; }
  job = job_new(JOB_GO);
  if (!job) { set_status(L"内存不足，无法缩放。"); return; }
  job->book_id = g.current.id;
  job->target_page = g.frame.page;
  job->zoom_percent = next;
  job_submit(job);
}

static size_t selection_bytes(char **text) {
#ifdef EXR_READER_WINDOWS_SHELL
  if (shell_active && select_valid) return shell_selection_bytes(text);
#endif
  size_t start, end;
  *text = NULL;
  if (!g.selection.active || !g.frame.valid) return 0;
  if (g.session.book_id != g.frame.book_id) return 0;
  selection_bounds(&start, &end);
  if (start >= end) return 0;
  if (g.frame.fixed) {
    const char *bytes;
    size_t size = 0;
    if (!g.frame.fixed_text || g.session.page != g.frame.page) return 0;
    bytes = exr_fixed_text_string(g.frame.fixed_text, &size);
    if (!bytes || end > size) return 0;
    *text = malloc(end - start + 1);
    if (!*text) return 0;
    memcpy(*text, bytes + start, end - start);
    (*text)[end - start] = 0;
    return end - start;
  } else {
    const char *bytes;
    bytes = g.frame.utf8;
    if (!bytes || start < g.frame.range_start || end > g.frame.range_end) return 0;
    start -= g.frame.range_start; end -= g.frame.range_start;
    *text = malloc(end - start + 1);
    if (!*text) return 0;
    memcpy(*text, bytes + start, end - start);
    (*text)[end - start] = 0;
    return end - start;
  }
}

static int clipboard_set(const char *utf8, size_t size) {
  wchar_t *wide = host_wide(utf8, size);
  HGLOBAL memory;
  void *target;
  size_t bytes;
  if (!wide) return 0;
  bytes = (wcslen(wide) + 1) * sizeof(wchar_t);
  memory = GlobalAlloc(GMEM_MOVEABLE, bytes);
  if (!memory) { free(wide); return 0; }
  target = GlobalLock(memory);
  if (!target) { GlobalFree(memory); free(wide); return 0; }
  memcpy(target, wide, bytes);
  GlobalUnlock(memory);
  if (!OpenClipboard(g.window)) { GlobalFree(memory); free(wide); return 0; }
  EmptyClipboard();
  if (!SetClipboardData(CF_UNICODETEXT, memory)) {
    GlobalFree(memory);
    CloseClipboard();
    free(wide);
    return 0;
  }
  CloseClipboard();
  free(wide);
  return 1;
}

static void select_all_page(void) {
#ifdef EXR_READER_WINDOWS_SHELL
  if (shell_active && !g.frame.fixed && select_publication()) { select_all_part(); return; }
#endif
  if (!g.frame.valid) { set_status(L"请先打开一本书。"); return; }
  memset(&g.selection, 0, sizeof(g.selection));
  if (g.frame.fixed) {
    g.selection.start = 0;
    g.selection.end = g.frame.text_bytes;
  } else {
    g.selection.start = g.frame.range_start;
    g.selection.end = g.frame.range_end;
  }
  g.selection.page = g.frame.page;
  g.selection.fixed = g.frame.fixed;
  g.selection.active = g.selection.start < g.selection.end;
  if (!g.selection.active) {
    memset(&g.selection, 0, sizeof(g.selection));
    set_status(L"本页没有可选文字。");
  } else {
    selection_report();
  }
  page_dirty(g.page,0);
  host_a11y_page_changed(1);
}

static void copy_quote(void) {
  char *text = NULL;
  size_t size = 0;
  if (g.selection.active
#ifdef EXR_READER_WINDOWS_SHELL
      || (shell_active && select_valid)
#endif
  ) size = selection_bytes(&text);
  if (size && text) {
    if (clipboard_set(text, size)) set_statusf(L"已复制引用（%llu 字节）到剪贴板。", (unsigned long long)size);
    else set_status(L"无法访问剪贴板。");
    free(text);
    return;
  }
#ifdef EXR_READER_WINDOWS_SHELL
  if (shell_active && !g.frame.fixed) { set_status(L"请先选择要复制的文字。"); return; }
#endif
  {
    int index = g.session.txt ? -1 : notes_selected();
    if (index < 0) {
      set_status(L"请先选择文字，或在标注列表中选择一条标注。");
      return;
    }
    if (g.session.fixed) {
      const exr_fixed_note *note = &g.fixed_notes[index];
      size = note->anchor.exact_size + (note->text ? strlen(note->text) : 0) + 5;
      text = malloc(size + 1);
      if (text) {
        size_t at = 0;
        if (note->anchor.exact_size) { memcpy(text, note->anchor.exact, note->anchor.exact_size); at = note->anchor.exact_size; }
        memcpy(text + at, "\r\n\r\n", 4); at += 4;
        if (note->text) { size_t n = strlen(note->text); memcpy(text + at, note->text, n); at += n; }
        text[at] = 0;
        size = at;
      }
    } else {
      const char *quote = g.session.bounded ? g.epub_notes[index].location.selector.exact : g.reflow_notes[index].anchor.exact;
      const char *comment = g.session.bounded ? g.epub_notes[index].text : g.reflow_notes[index].text;
      if (!quote) quote = "";
      if (!comment) comment = "";
      size = strlen(quote) + strlen(comment) + 5;
      text = malloc(size + 1);
      if (text) {
        size_t at = strlen(quote);
        memcpy(text, quote, at);
        memcpy(text + at, "\r\n\r\n", 4); at += 4;
        memcpy(text + at, comment, strlen(comment)); at += strlen(comment);
        text[at] = 0;
        size = at;
      }
    }
    if (text && size && clipboard_set(text, size)) set_status(L"已复制标注引用到剪贴板。");
    else set_status(L"无法复制标注引用。");
    free(text);
  }
}

static inline void add_note(void) {
  char comment[65536];
  exr_error error = {0};
  host_job *job;
  if (g.job || g.pending) return;
  if (!g.has_current || !g.frame.valid) { set_status(L"请先打开一本书。"); return; }
  if (!g.selection.active) { set_status(L"请先选择文字，再添加标注。"); return; }
  if (!note_comment_read(comment, sizeof(comment))) return;
  job = job_new(JOB_NOTE_ADD);
  if (!job) { set_status(L"内存不足，未添加标注。"); return; }
  job->book_id = g.current.id; job->target_page = g.selection.page; job->note_fixed = g.frame.fixed;
  job->target_part = g.frame.part;
  selection_bounds(&job->note_start, &job->note_end);
  job->comment = host_strdup(comment);
  if (!job->comment || (!job->note_fixed && !g.session.bounded && exr_anchor_create(g.session.document, job->note_start, job->note_end,
                                                               &job->anchor, &error) != EXR_OK)) {
    job_release(job); set_status(L"无法建立标注，未保存。"); return;
  }
  job->has_anchor = !job->note_fixed && !g.session.bounded;
  job_submit(job);
}

static inline void update_note(void) {
  int index = notes_selected();
  char comment[65536];
  host_job *job;
  if (g.job || g.pending) return;
  if (index < 0) { set_status(L"请先在标注列表中选择一条标注。"); return; }
  if (!note_comment_read(comment, sizeof(comment))) return;
  job = job_new(JOB_NOTE_UPDATE);
  if (!job) { set_status(L"内存不足，未更新标注。"); return; }
  job->book_id = g.current.id; job->note_fixed = g.frame.fixed;
  if (job->note_fixed) {
    job->note_id = g.fixed_notes[index].id; job->target_page = g.fixed_notes[index].page;
    job->note_start = g.fixed_notes[index].start; job->note_end = g.fixed_notes[index].end;
  } else job->note_id = g.session.bounded ? g.epub_notes[index].id : g.reflow_notes[index].id;
  job->comment = host_strdup(comment);
  if (!job->comment) { job_release(job); set_status(L"内存不足，未更新标注。"); return; }
  job_submit(job);
}

static inline void delete_note(void) {
  int index = notes_selected();
  exr_error error = {0};
  exr_status status;
  if (g.job || g.pending) return;
  if (index < 0) { set_status(L"请先在标注列表中选择一条标注。"); return; }
  EnterCriticalSection(&g.library_lock);
  if (g.session.fixed)
    status = exr_library_remove_fixed_note(g.library, g.fixed_notes[index].id, &error);
  else if (g.session.bounded)
    status = exr_library_remove_epub_note(g.library, g.epub_notes[index].id, &error);
  else
    status = exr_library_remove_note(g.library, g.reflow_notes[index].id, &error);
  LeaveCriticalSection(&g.library_lock);
  if (status != EXR_OK) {
    wchar_t message[512];
    describe_error(message, 512, L"删除标注失败", status, &error);
    set_status(message);
    return;
  }
  if (reload_notes() != EXR_OK) return;
  if (g.notes && current_note_count()) {
    size_t selected = (size_t)index < current_note_count() ? (size_t)index : current_note_count() - 1;
    SendMessageW(g.notes, LB_SETCURSEL, (WPARAM)selected, 0);
  }
  set_status(L"已删除标注。");
}

static inline void jump_selected_note(void) {
  int index = notes_selected();
  host_job *job;
  if (index < 0) { set_status(L"请先在标注列表中选择一条标注。"); return; }
  if (!g.has_current || !g.frame.valid) return;
  if (g.job || g.pending) return;
  if (g.session.fixed) {
    const exr_fixed_note *note = &g.fixed_notes[index];
    if (note->page == g.frame.page) {
      if (note->start < note->end && note->end <= g.frame.text_bytes) {
        g.selection.active = 1;
        g.selection.fixed = 1;
        g.selection.page = g.frame.page;
        g.selection.start = note->start;
        g.selection.end = note->end;
        page_dirty(g.page,0);
        set_statusf(L"已定位到当前页标注（第 %llu 页）。", (unsigned long long)(note->page + 1));
      } else {
        set_status(L"标注范围超出当前页文字，未高亮。");
      }
      return;
    }
    job = job_new(JOB_GO);
    if (!job) return;
    job->book_id = g.current.id;
    job->target_page = note->page;
    job->direction = note->page > g.frame.page ? 1 : -1;
    g.pending_selection = 1;
    g.pending_start = note->start;
    g.pending_end = note->end;
    g.pending_book = g.current.id;
    job_submit(job);
    return;
  }
  {
    exr_note converted = {0}; const exr_note *note;
    if (g.session.bounded) {
      const exr_epub_note *epub = &g.epub_notes[index];
      converted.start = epub->location.selector.start; converted.end = epub->location.selector.end;
      converted.anchor = epub->location.selector; note = &converted;
    } else note = &g.reflow_notes[index];
    size_t offset;
    size_t target_start = note->start, target_end = note->end;
    if (!g.session.document && !g.session.bounded) return;
    job = job_new(JOB_GO);
    if (!job) return;
    if (!note->anchor.exact) {
      if (note->start == SIZE_MAX) { job_release(job); set_status(L"该标注没有可用的文本锚点。"); return; }
      offset = note->start;
      set_status(L"旧版标注：按保存的文本偏移跳转。");
    } else {
      job->anchor = note->anchor;
      job->has_anchor = 1;
      job->anchor_host_owned = 1;
      job->anchor.exact = note->anchor.exact ? host_strdup(note->anchor.exact) : NULL;
      job->anchor.prefix = note->anchor.prefix ? host_strdup(note->anchor.prefix) : NULL;
      job->anchor.suffix = note->anchor.suffix ? host_strdup(note->anchor.suffix) : NULL;
      job->anchor.chapter = note->anchor.chapter ? host_strdup(note->anchor.chapter) : NULL;
      if (!job->anchor.exact || (note->anchor.prefix && !job->anchor.prefix) ||
          (note->anchor.suffix && !job->anchor.suffix) || (note->anchor.chapter && !job->anchor.chapter)) {
        job_release(job); set_status(L"内存不足，标注未跳转。"); return;
      }
      offset = note->anchor.start;
    }
    job->book_id = g.current.id;
    if (g.session.bounded) {
      job->target_part = g.epub_notes[index].location.part;
      job->part_path = host_strdup(g.epub_notes[index].location.path);
      if (!job->part_path) { job_release(job); return; }
      g.pending_part = job->target_part;
    }
    job->use_offset = 1;
    job->target_offset = offset;
    job->direction = 0;
    g.pending_selection = 1;
    g.pending_start = target_start;
    g.pending_end = target_end;
    g.pending_book = g.current.id;
    job_submit(job);
  }
}

static void open_selected_book(void) {
#ifdef EXR_READER_WINDOWS_SHELL
  if(de_active() && !de_exit())return;
#endif
  LRESULT index;
  host_job *job;
#ifdef EXR_READER_WINDOWS_SHELL
  if(!shelf_before_exit()) return;
  if(!shelf_capture()) return;
  shelf_requested=0;shell_bar_hidden=0;
#endif
  if (!g.books) return;
  index = SendMessageW(g.books, LB_GETCURSEL, 0, 0);
  if (index == LB_ERR || (size_t)index >= g.shelf_count) {
    set_status(L"请先在书架中选择一本书。");
    return;
  }
#ifdef EXR_READER_PRODUCT_CATALOG
  if(g.shelf_cursors && g.shelf[index].id<=0 && g.shelf[index].format!=EXR_TXT) {
    set_status(L"此书尚未下载到本机。");return;
  }
#endif
#ifdef EXR_READER_WINDOWS_TXT_PROGRESS
  if (g.session.txt) g.txt_force_save = 1;
#endif
  if (!g.job && !g.pending && !save_progress()) return;
  job = job_new(JOB_OPEN);
  if (!job) { set_status(L"内存不足，无法打开书籍。"); return; }
  job->book_id = g.shelf[index].id;
#ifdef EXR_READER_WINDOWS_TXT_RECOVERY
  if(job->book_id==0 && g.shelf_cursors && g.shelf[index].format==EXR_TXT) {
    snprintf(job->product_key,sizeof(job->product_key),"%s",g.shelf_cursors[index].key);
    if(!book_copy(&job->opened_book,&g.shelf[index])) { job_release(job);return; }
  } else
#endif
  if(job->book_id<=0) { job_release(job);set_status(L"此书尚未下载到本机。");return; }
  job->font_percent = g.font_percent;
  job_submit(job);
}

static void show_deleted_book(int64_t id) {
  if (g.has_current && g.current.id == id) {
    session_clear(&g.session);
    book_clear(&g.current);
    g.has_current = 0;
    frame_clear(&g.frame);
    notes_clear();
    if (g.notes) SendMessageW(g.notes, LB_RESETCONTENT, 0, 0);
    memset(&g.selection, 0, sizeof(g.selection));
    g.active_book_id = 0;
#ifdef EXR_READER_WINDOWS_TXT_PROGRESS
    g.active_txt_key[0] = 0;
#endif
    settings_save();
    update_page_label();
    page_dirty(g.page,1);
  }
  if (reload_shelf() != EXR_OK) return;
  host_update_controls();
  set_status(L"已删除书籍及其标注。");
}
static inline void delete_selected_book(void) {
  if(g.job || g.pending || !g.books) return;
  LRESULT index=SendMessageW(g.books,LB_GETCURSEL,0,0);
  if(index==LB_ERR || (size_t)index>=g.shelf_count) {
    set_status(L"请先在书架中选择一本书。");return;
  }
  int64_t id=g.shelf[index].id;
  if(id<=0) { set_status(L"此书没有可移除的本机原书。");return; }
#ifdef EXR_READER_PRODUCT_CATALOG
  host_job *job=job_new(JOB_PRODUCT_DELETE);
  if(!job) { set_status(L"内存不足，无法删除书籍。");return; }
  job->book_id=id;job_submit(job);
#else
  exr_error error={0};EnterCriticalSection(&g.library_lock);
  exr_status status=exr_library_delete(g.library,id,&error);
  LeaveCriticalSection(&g.library_lock);
  if(status!=EXR_OK) {
    wchar_t message[512];describe_error(message,512,L"删除书籍失败",status,&error);set_status(message);return;
  }
  show_deleted_book(id);
#endif
}

static void import_path(const wchar_t *path, int dialog_fallback) {
#ifdef EXR_READER_WINDOWS_SHELL
  if(de_active() && !de_exit())return;
#endif
  host_job *job;
  wchar_t chosen[HOST_PATH] = L"";
  if (g.job || g.pending) {
    set_status(L"已有任务运行，请等待或取消。");
    return;
  }
  if (path && path[0]) {
    copy_wstring(chosen, HOST_PATH, path);
  } else if (dialog_fallback) {
    OPENFILENAMEW dialog;
    memset(&dialog, 0, sizeof(dialog));
    dialog.lStructSize = sizeof(dialog);
    dialog.hwndOwner = g.window;
    dialog.lpstrFile = chosen;
    dialog.nMaxFile = HOST_PATH;
    dialog.lpstrFilter = L"电子书\0*.epub;*.pdf;*.cbz;*.txt;*.fb2;*.html;*.docx;*.rtf;*.mobi;*.azw3\0所有文件\0*.*\0";
    dialog.Flags = OFN_FILEMUSTEXIST | OFN_NOCHANGEDIR | OFN_PATHMUSTEXIST;
    if (!GetOpenFileNameW(&dialog)) return;
  } else {
    set_status(L"请输入要导入的文件路径。");
    return;
  }
#ifdef EXR_READER_WINDOWS_TXT_RECOVERY
  {
    exr_format format;
    if (format_for_path(chosen, &format) && format == EXR_TXT && (!g.product_ready || g.product_pending)) {
      set_status(L"书目恢复尚未完成，暂不能导入 TXT；请重试恢复或重启。");
      return;
    }
  }
#endif
  job = job_new(JOB_IMPORT);
  if (!job) { set_status(L"内存不足，无法导入。"); return; }
#ifdef EXR_READER_WINDOWS_SHELL
  if(!shelf_before_exit() || !shelf_capture()) {job_release(job);return;}
#endif
  copy_wstring(job->path, HOST_PATH, chosen);
  set_statusf(L"正在导入：%ls", chosen);
  job_submit(job);
}

static int import_title_fallback(const wchar_t *path, int64_t id) {
  exr_book copy={0};
  wchar_t stem[HOST_PATH];
  const wchar_t *base;
  wchar_t *dot;
  char *utf8;
  exr_error error = {0};
  if(local_book_copy(id,&copy,&error)!=EXR_OK) { set_status(L"无法读取已导入书籍的信息，原书仍保留。");return 0; }
  if(copy.title && copy.title[0] && strcmp(copy.title,"Untitled")) { book_clear(&copy);return 1; }
  base = wcsrchr(path, L'\\');
  base = base ? base + 1 : path;
  copy_wstring(stem, HOST_PATH, base);
  dot = wcsrchr(stem, L'.');
  if (dot && dot != stem) *dot = 0;
  if (!stem[0]) { book_clear(&copy);return 1; }
  utf8 = host_utf8(stem);
  if (!utf8) { book_clear(&copy);set_status(L"无法更新导入书籍标题。"); return 0; }
  free(copy.title);
  copy.title = utf8;
  EnterCriticalSection(&g.library_lock);
  {
    exr_status status = exr_library_update(g.library, &copy, &error);
    LeaveCriticalSection(&g.library_lock);
    book_clear(&copy);
    if (status != EXR_OK) { set_status(L"书籍已导入，但更新标题失败，请重试。"); return 0; }
  }
  return reload_shelf() == EXR_OK;
}

static void host_update_controls(void) {
  HWND focused = GetFocus();
  int busy = (g.job != NULL) || (g.pending != NULL);
  (void)busy;
#ifdef EXR_READER_WINDOWS_NAVIGATION
  winnav_controls();
#endif
#ifdef EXR_READER_WINDOWS_RECORDS
  winrecords_controls();
#endif
#ifdef EXR_READER_WINDOWS_WAVE3
  w3_controls();
#endif
#ifdef EXR_READER_PRODUCT_CATALOG
  EnableWindow(g.shelf_refresh,!busy && !g.closing);
#endif
#ifdef EXR_READER_DESKTOP_METADATA
  EnableWindow(g.metadata_button,!busy && !g.closing && g.product_ready && !g.product_pending && g.shelf_count>0);
#endif
#ifdef EXR_READER_WINDOWS_ACCOUNT
  EnableWindow(g.account_button,!g.closing && !g.metadata_running && !g.metadata_dialog);
#endif
  /* A command that just disabled itself must not take keyboard focus with it. */
  host_a11y_focus_guard(focused);
  /* A modal dialog owns the keyboard: keep the truthful blocked state. */
  host_a11y_owner_reapply();
#ifdef EXR_READER_WINDOWS_SHELL
  shell_sync();
  de_controls();
#endif
}

static void handle_job_complete(host_job *job) {
#ifdef EXR_READER_WINDOWS_SHELL
  if (job->kind == JOB_OPEN && job->status == EXR_OK &&
      !shell_geometry_equal(job->shell_geometry, shell_snapshot())) {
    host_job *latest = job_new(JOB_OPEN);
    if (latest && !g.pending) {
      latest->book_id = job->book_id; latest->font_percent = job->font_percent;
#ifdef EXR_READER_WINDOWS_TXT_RECOVERY
      memcpy(latest->product_key, job->product_key, sizeof(latest->product_key));
#endif
      job_submit(latest);
    } else if (latest) job_release(latest);
    return;
  }
  if (job->kind == JOB_LAYOUT && job->status != EXR_OK && job->shell_epoch == shell_epoch)
    shell_failed_epoch = shell_epoch;
  if ((job->kind == JOB_LAYOUT || job->kind == JOB_GO || job->kind == JOB_PREFETCH) &&
      (job->shell_epoch != shell_epoch || (job->frame.valid &&
       !shell_geometry_equal(job->frame.shell_geometry, shell_target)))) return;
#endif
  if(job->kind==JOB_PREFETCH) {
    if(job->status==EXR_OK && !job_cancel_flag(job) && !g.closing && job->frame.book_id==g.session.book_id && job->frame.part==g.session.part) {
      page_cache_put(&job->frame);host_probe_log("prefetch_ready",(double)job->target_page);
    }
    return;
  }
#ifdef EXR_READER_WINDOWS_TXT_RECOVERY
  if(job->original_recovery_failed) {
    g.product_pending=1;g.product_ready=0;
    copy_wstring(job->message,512,L"TXT 导入恢复未完成；请重启后重试，原书状态需要恢复。");
  }
#endif
#ifdef EXR_READER_WINDOWS_PREFERENCES
  prefs.last_ok = 0;
  if(job->kind==JOB_PREFERENCES) { prefs_accept(job);return; }
#endif
#ifdef EXR_READER_WINDOWS_IMPORT_ORGANIZE
  if(winio_kind(job->kind)) { winio_accept(job);return; }
#endif
#ifdef EXR_READER_WINDOWS_SEARCH
  if(job->kind==JOB_SEARCH_BATCH || job->kind==JOB_SEARCH_OPEN) { winsearch_accept(job);return; }
#endif
#ifdef EXR_READER_WINDOWS_NAVIGATION
  if(job->kind==JOB_NAVIGATION_ROWS || job->kind==JOB_NAVIGATION_OPEN) { winnav_accept(job);return; }
#endif
#ifdef EXR_READER_WINDOWS_RECORDS
  if(job->kind==JOB_RECORDS) { winrecords_accept(job);return; }
#endif
#ifdef EXR_READER_WINDOWS_WAVE3
  if(job->kind==JOB_WAVE3) { w3_accept(job);return; }
#endif
#ifdef EXR_READER_WINDOWS_ACCOUNT
  if(account_job_kind(job->kind)) { acct_job_accept(job);return; }
#endif
#ifdef EXR_READER_DESKTOP_METADATA
  if(metadata_job_kind(job->kind)) { metadata_job_accept(job);return; }
#endif
#ifdef EXR_READER_PRODUCT_CATALOG
  if(job->kind==JOB_PRODUCT_SHELF) {
    if(job_cancel_flag(job) && !g.closing && g.pending &&
       job->product_shelf_generation==g.shelf_generation) {
      g.shelf_need_refresh=1;g.shelf_requested_direction=0;
    }
    if(!g.closing && !job_cancel_flag(job) && job->product_shelf_generation==g.shelf_generation) {
      if(job->status==EXR_OK) product_shelf_accept(job);
      else set_status(L"书架查询失败，保留当前列表；可刷新后重试。");
    }
    return;
  }
  if(product_job_kind(job->kind)) {
    if(job->status!=EXR_OK) { g.product_pending=1;g.product_ready=0;g.shelf_need_refresh=0; }
    else if(job->kind==JOB_PRODUCT_REPAIR) { g.product_pending=0;g.product_ready=1; }
    /* The imported row was selected by its SDK ID; carry that choice to the stable product key
       so the bounded page refresh restores it instead of clearing the selection. */
    if(job->kind==JOB_PRODUCT_ATTACH && job->status==EXR_OK && job->product_key[0] && !g.closing)
      snprintf(g.shelf_selected_key,sizeof(g.shelf_selected_key),"%s",job->product_key);
    if(job->status==EXR_OK && !g.product_pending) { g.product_ready=1;product_shelf_schedule(0,0); }
    if(job->kind==JOB_PRODUCT_DELETE && job->product_deleted) {
      show_deleted_book(job->book_id);return;
    }
    if(job->status!=EXR_OK) {
      set_status(job->kind==JOB_PRODUCT_DELETE ? L"原书仍保留；删除未完成，书目映射将在重启后修复。":
        L"原书已保存在本机；书架信息将在重启后重试恢复。");
    } else if(job->kind==JOB_PRODUCT_ATTACH) set_status(job->message[0] ? job->message:L"原书与书目索引已保存。");
    if(job->product_auto_open && !job_cancel_flag(job) && !g.closing) {
      host_job *open=job_new(JOB_OPEN);
      if(open) { open->book_id=job->book_id;open->font_percent=g.font_percent;job_submit(open); }
    }
    return;
  }
#endif
  if (job->kind == JOB_SAVE
#ifdef EXR_READER_WINDOWS_TXT_PROGRESS
      || job->kind == JOB_TXT_PROGRESS
#endif
  ) {
    g.progress_failed = job->status != EXR_OK;
    if (!g.progress_failed) {
      g.saved_generation = job->generation;
#ifdef EXR_READER_WINDOWS_TXT_PROGRESS
      if (job->kind == JOB_TXT_PROGRESS) {
        snprintf(g.txt_saved_key, sizeof(g.txt_saved_key), "%s", job->txt_key);
        g.txt_saved_offset = job->txt_saved_offset;
        g.txt_saved_valid = job->txt_saved_valid;
      }
#endif
    } else {
      wchar_t message[512];
#ifdef EXR_READER_WINDOWS_TXT_PROGRESS
      describe_error(message, 512, job->kind == JOB_TXT_PROGRESS ? L"阅读位置未保存，原记录保留" : L"保存进度失败，请重试",
                     job->status, &job->error);
#else
      describe_error(message, 512, L"保存进度失败，请重试", job->status, &job->error);
#endif
      set_status(message);
      if (g.pending) { job_release(g.pending); g.pending = NULL; }
#ifdef EXR_READER_WINDOWS_TXT_PROGRESS
      /* A refused product write must not trap the user in a window that cannot
         close; the retained record is untouched and the notice stays on screen. */
      if (job->kind == JOB_TXT_PROGRESS && g.closing) g.txt_save_abandoned = 1;
#endif
#ifdef EXR_READER_WINDOWS_TXT_PROGRESS
      if (g.closing && !g.txt_save_abandoned) { g.closing = 0; KillTimer(g.window, 2); if (g.drive_mode) SetTimer(g.window, 1, 30, NULL); }
#else
      if (g.closing) { g.closing = 0; KillTimer(g.window, 2); if (g.drive_mode) SetTimer(g.window, 1, 30, NULL); }
#endif
    }
    return;
  }
  if (job->kind == JOB_HIT) {
    int accept = job->status == EXR_OK && !job_cancel_flag(job) && !g.closing && !g.pending &&
      job->book_id == g.frame.book_id && job->target_part == g.frame.part &&
      job->target_page == g.frame.page && job->generation == g.frame.generation && job->gesture == g.gesture;
    if (accept) {
      if (job->hit_down) { g.selection.start = job->hit_offset; g.selection.page = g.frame.page; }
      g.selection.end = job->hit_offset;
      g.selection.active = g.selection.start != g.selection.end;
      if (job->hit_up) { dragging = 0; selection_report(); }
      page_dirty(g.page,0);
      if (g.hit_pending) {
        float x = g.hit_x, y = g.hit_y; int up = g.hit_up;
        g.hit_pending = g.hit_up = 0; bounded_hit(x, y, 0, up);
      }
    } else {
      g.hit_pending = g.hit_up = 0; dragging = 0; selection_clear();
    }
    return;
  }
  if (job->kind == JOB_ROLLBACK || job->rollback_failed) {
    exr_status refreshed = reload_shelf();
    if ((job->rollback_failed || refreshed != EXR_OK) && g.closing) {
      g.closing = 0; KillTimer(g.window, 2);
      if (g.drive_mode) SetTimer(g.window, 1, 30, NULL);
    }
    if (refreshed != EXR_OK) return;
#ifdef EXR_READER_PRODUCT_CATALOG
    if(g.product_ready && !g.product_pending) product_shelf_schedule(0,0);
#endif
    if (job->rollback_failed) set_status(job->message);
    else set_status(L"导入已取消；新建书架条目已回滚。");
    g.auto_open_imported = 0;
    return;
  }
  if (job->status == EXR_OK && job_cancel_flag(job) && job->kind == JOB_IMPORT
#ifdef EXR_READER_WINDOWS_TXT_RECOVERY
      && !job->original_import
#endif
  ) {
    if (job->created && job->imported_id > 0) {
      host_job *rollback = job_new(JOB_ROLLBACK);
      if (!rollback) {
        reload_shelf(); set_status(L"取消导入后无法启动回滚；新书仍在数据库中，请删除。");
      } else {
        rollback->created = 1; rollback->imported_id = job->imported_id;
        job_start(rollback);
      }
      g.auto_open_imported = 0;
      return;
    }
    job->status = EXR_CANCELLED;
  }
  if (job->status == EXR_OK && !job_preferences_committed(job) && (job_cancel_flag(job) || g.closing) &&
      (job->kind == JOB_OPEN || job->kind == JOB_GO || job->kind == JOB_LAYOUT)) job->status = EXR_CANCELLED;
  if (job->status != EXR_OK) g.pending_selection = 0;
  if (job->status == EXR_OK) {
#ifdef EXR_READER_WINDOWS_PREFERENCES
    /* The worker saved strictly before returning OK, so the published frame
       and this record always describe the same accepted selection. */
    if (job->prefs_valid) {
      prefs.value = job->prefs;
      prefs.active = 1;
      prefs.corrupt = 0;
      prefs.file_present = 1;
      prefs.load_status = READER_PREFERENCES_OK;
      prefs.last_ok = 1;
    }
#endif
    if (job->kind == JOB_OPEN) {
#ifdef EXR_READER_WINDOWS_TXT_PROGRESS
      if (job->product_key[0]) TXT_TRACE("ui-open-accept");
#endif
      if (job->session_swapped && job->have_frame && job->candidate.book_id == job->book_id && job->frame.book_id == job->book_id) {
        exr_book next = {0};
        if (job->opened_book.id == job->book_id) {
          next = job->opened_book; memset(&job->opened_book, 0, sizeof(job->opened_book));
          session_clear(&g.session); g.session = job->candidate; memset(&job->candidate, 0, sizeof(job->candidate));
          book_clear(&g.current); g.current = next;
          g.has_current = 1;
#ifdef EXR_READER_WINDOWS_SEARCH
          winsearch_close();
#endif
#ifdef EXR_READER_WINDOWS_NAVIGATION
          winnav_close();
#endif
#ifdef EXR_READER_WINDOWS_RECORDS
          winrecords_close();
#endif
#ifdef EXR_READER_WINDOWS_WAVE3
          w3_book_changed();
#endif
          g.active_book_id = g.current.id;
#ifdef EXR_READER_WINDOWS_TXT_PROGRESS
          snprintf(g.active_txt_key,sizeof(g.active_txt_key),"%s",g.session.txt ? g.session.txt_key : "");
#endif
          frame_move(&g.frame, &job->frame);
#ifdef EXR_READER_WINDOWS_SHELL
          shelf_requested=0;shell_bar_hidden=0;
          if(job->shelf_restored) shelf_resume(job->target_offset);
          shelf_opened();
          sm_landed(1);
          shell_toc_load();
#endif
          memset(&g.selection, 0, sizeof(g.selection));
          g.pending_selection = 0;
          g.session.page = g.frame.page;
          update_page_label();
#ifdef EXR_READER_WINDOWS_WAVE3
          /* Capture only an accepted frame, before save_progress starts another worker. */
          if (job == w3.font_job) w3_after_font_job(job);
          else if (!job->w3 && !g.session.txt) w3_history_land(job);
#endif
          settings_save();
          if (reload_notes() != EXR_OK) { save_progress(); return; }
#ifdef EXR_READER_WINDOWS_TXT_PROGRESS
          if (g.session.txt) TXT_TRACE("ui-before-save");
#endif
          if (!save_progress()) return;
          {
            wchar_t *title = g.current.title ? host_wide(g.current.title, strlen(g.current.title)) : NULL;
            if (job->message[0])
              set_statusf(L"已打开《%ls》 · %ls", title ? title : L"Untitled", job->message);
            else
              set_statusf(L"已打开《%ls》。", title ? title : L"Untitled");
            free(title);
          }
        } else {
          set_status(L"打开任务没有提供一致的书籍信息。");
        }
      } else {
        set_status(L"打开书籍失败：任务结果不完整。");
      }
    } else if (job->kind == JOB_GO || job->kind == JOB_LAYOUT) {
      if (job->have_frame && g.has_current && job->book_id == g.current.id &&
          job->frame.book_id == g.current.id && g.session.book_id == g.current.id) {
#ifdef EXR_READER_WINDOWS_SHELL
        if (job->kind == JOB_LAYOUT && g.session.fixed) g.session.shell_geometry = job->shell_geometry;
#endif
        if (job->candidate_pager) {
          exr_pager_free(g.session.pager); g.session.pager = job->candidate_pager; job->candidate_pager = NULL;
          if (g.session.txt) g.session.txt_source = job->candidate.txt_source;
          g.session.config = job->candidate_config;
#ifdef EXR_READER_WINDOWS_SHELL
          g.session.shell_geometry = job->shell_geometry;
#endif
        }
        if(job->kind==JOB_GO && g.frame.valid && g.frame.book_id==job->frame.book_id && g.frame.part==job->frame.part)page_cache_put(&g.frame);
        frame_move(&g.frame, &job->frame);
        g.session.part = g.frame.part;
#ifdef EXR_READER_WINDOWS_SHELL
        sm_landed(job->kind==JOB_GO ? 0:-1);
#endif
        g.session.hold_progress = g.frame.hold_progress;
        memset(&g.selection, 0, sizeof(g.selection));
#ifdef EXR_READER_WINDOWS_SHELL
        shell_selection_landed();
#endif
        g.session.page = g.frame.page;
#ifdef EXR_READER_WINDOWS_SHELL
        shell_toc_update_current();
        if(job->shell_toc_jump) {
          page_dirty(g.page,1);UpdateWindow(g.page);
          host_probe_log("toc_landed_gen",(double)g.frame.generation);
          shell_toc_close_pending=1;
        }
#endif
        if (job->kind == JOB_LAYOUT && job->font_percent > 0
#ifdef EXR_READER_WINDOWS_SHELL
            && !job->shell_geometry.enabled
#endif
        ) g.font_percent = job->font_percent;
        if (job->zoom_percent > 0) g.zoom_percent = job->zoom_percent;
        update_page_label();
#ifdef EXR_READER_WINDOWS_WAVE3
        if (job->kind == JOB_GO && !job->w3 && !g.session.txt) w3_history_land(job);
#if defined(EXR_READER_WINDOWS_TXT_PROGRESS) && defined(EXR_READER_WINDOWS_SEARCH)
        else if (job->kind == JOB_GO && !job->w3 && g.session.txt && job->txt_history_ready)
          w3_txt_search_history_land(job);
#endif
#endif
        settings_save();
        if (!save_progress()) { g.pending_selection = 0; return; }
        if (job->message[0]) set_status(job->message);
        else set_statusf(L"第 %llu 页。", (unsigned long long)(g.frame.page + 1));
#ifdef EXR_READER_WINDOWS_SHELL
        if(job->shell_search_jump) {job->resolved_selection=0;memset(&g.selection,0,sizeof(g.selection));g.pending_selection=0;}
#endif
        if (job->resolved_selection) {
          g.pending_book = g.current.id; g.pending_part = g.frame.part;
          g.pending_start = job->note_start; g.pending_end = job->note_end;
          g.pending_selection = 1;
        }
        apply_pending_selection();
      } else {
        set_status(L"翻页失败：任务没有生成画面。");
      }
    } else if (job->kind == JOB_IMPORT) {
#ifdef EXR_READER_WINDOWS_TXT_RECOVERY
      if (job->original_import) {
        g.auto_open_imported=0;
        if(job->product_key[0]) {
          SendMessageW(g.books,LB_SETCURSEL,(WPARAM)-1,0);
          product_shelf_schedule(0,0);
          product_shelf_reveal=1;
          snprintf(g.shelf_selected_key,sizeof(g.shelf_selected_key),"%s",job->product_key);
          snprintf(g.shelf_top_key,sizeof(g.shelf_top_key),"%s",job->product_key);
        }
#ifdef EXR_READER_WINDOWS_TXT_PROGRESS
        set_status(job->created ? L"TXT 原书已保存到书架。" : L"TXT 原书已存在。");
#else
        set_status(job->created ? L"TXT 原书已保存到书架；阅读功能尚未完成。" : L"TXT 原书已存在；阅读功能尚未完成。");
#endif
        return;
      }
#endif
      if (reload_shelf() != EXR_OK) return;
      if (job->created && !import_title_fallback(job->path, job->imported_id)) return;
#ifdef EXR_READER_WINDOWS_SHELL
      shelf_imported(job->imported_id,job->path);
#endif
      {
        int index = shelf_index(job->imported_id);
        if (index >= 0 && g.books) SendMessageW(g.books, LB_SETCURSEL, (WPARAM)index, 0);
      }
      if (job->created) {
        int found = shelf_index(job->imported_id);
        wchar_t *title = found >= 0 && g.shelf[found].title
                           ? host_wide(g.shelf[found].title, strlen(g.shelf[found].title)) : NULL;
        set_statusf(L"已导入《%ls》并写入书架。", title ? title : L"Untitled");
        free(title);
      } else {
        set_status(L"已存在完全相同的内容，未重复导入（去重命中）。");
      }
#ifdef EXR_READER_PRODUCT_CATALOG
      /* All three import cancellation/compensation boundaries and fallback
         title publication have passed. Only now create product metadata. */
      host_job *attach=job_new(JOB_PRODUCT_ATTACH);
      if(attach) {
        attach->book_id=job->imported_id;
        copy_wstring(attach->message,512,g.status_text);
        attach->product_auto_open=g.auto_open_imported && job->imported;
        g.auto_open_imported=0;job_submit(attach);
      } else {
        g.product_pending=1;g.auto_open_imported=0;set_status(L"原书已保存；无法启动书目索引任务，重启后重试。");
      }
#else
      if (g.auto_open_imported && job->imported) {
        host_job *open = job_new(JOB_OPEN);
        g.auto_open_imported = 0;
        if (open) {
          open->book_id = job->imported_id;
          open->font_percent = g.font_percent;
          job_submit(open);
        }
      }
#endif
    } else if (job->kind == JOB_NOTE_ADD || job->kind == JOB_NOTE_UPDATE) {
      if (g.has_current && job->book_id == g.current.id && reload_notes() == EXR_OK) {
        size_t i;
        for (i = 0; i < current_note_count(); i++) {
          int64_t id = g.session.fixed ? g.fixed_notes[i].id : g.session.bounded ? g.epub_notes[i].id : g.reflow_notes[i].id;
          if (id == job->note_id && g.notes) SendMessageW(g.notes, LB_SETCURSEL, (WPARAM)i, 0);
        }
        if (job_cancel_flag(job)) set_status(L"标注已保存；取消到达保存之后。");
        else if (job->kind == JOB_NOTE_ADD) set_statusf(L"已添加标注 #%lld。", (long long)job->note_id);
        else set_status(L"已更新标注。");
      }
    }
  } else if (job->status == EXR_CANCELLED) {
    set_status(job->kind == JOB_IMPORT ? L"导入已取消；书架内容与当前画面保持不变。"
                                       : L"任务已取消；当前画面保持原书。");
  } else if (job->kind == JOB_GO && job->status == EXR_ARGUMENT && job->direction > 0 && (!g.session.bounded || job->at_end)) {
    set_status(L"已到最后一页；当前页未改变。");
  } else {
    wchar_t message[768];
    describe_error(message, 768,
                   job->kind == JOB_IMPORT ? L"导入失败" :
                   job->kind == JOB_OPEN ? L"打开书籍失败" : L"翻页或重排失败",
                   job->status, &job->error);
    set_status(message);
  }
}

static void host_command(int id) {
#ifdef EXR_READER_WINDOWS_SHELL
  if(de_active() && !de_exit())return;
#endif
  if (g.session.txt && id != HOST_CMD_OPEN && id != HOST_CMD_IMPORT
#ifdef EXR_READER_WINDOWS_ACCOUNT
      && id != IDC_ACCOUNT_BUTTON
#endif
#if defined(EXR_READER_WINDOWS_TXT_PROGRESS) && defined(EXR_READER_WINDOWS_SEARCH)
      && id != IDC_INBOOK
#endif
#if defined(EXR_READER_WINDOWS_TXT_PROGRESS) && defined(EXR_READER_WINDOWS_WAVE3)
      && id != IDC_W3_ORIGINALS && id != IDC_W3_FONTS && id != IDC_W3_ANNOTATIONS
#ifdef EXR_READER_WINDOWS_SEARCH
      && id != IDC_W3_BACK && id != IDC_W3_FORWARD
#endif
#endif
#if defined(EXR_READER_WINDOWS_TXT_PROGRESS) && defined(EXR_READER_WINDOWS_RECORDS)
      && id != IDC_RECORDS
#endif
#ifdef EXR_READER_WINDOWS_IMPORT_ORGANIZE
      && id != IDC_CLOUD_IMPORT && id != IDC_BULK_ORGANIZE
#endif
  ) {
#ifdef EXR_READER_WINDOWS_TXT_PROGRESS
    set_status(L"TXT 的此功能尚未实现。"); return;
#else
    set_status(L"TXT 的此功能及阅读位置保存尚未实现。"); return;
#endif
  }
#ifdef EXR_READER_WINDOWS_PREFERENCES
  if(prefs_ui_open() && id!=IDC_PREFERENCES) return;
#endif
#ifdef EXR_READER_WINDOWS_IMPORT_ORGANIZE
  if(id==IDC_CLOUD_IMPORT || id==IDC_BULK_ORGANIZE) { winio_show(id==IDC_CLOUD_IMPORT ? WINIO_CLOUD:WINIO_BULK);return; }
  if(winio.dialog) return;
#endif
#ifdef EXR_READER_WINDOWS_SEARCH
  if(id==IDC_INBOOK) { winsearch_show();return; }
#endif
#ifdef EXR_READER_WINDOWS_NAVIGATION
  if(id==IDC_DIRECTORY) { winnav_show();return; }
#endif
#ifdef EXR_READER_WINDOWS_RECORDS
  if(id==IDC_RECORDS) { winrecords_show();return; }
#endif
#ifdef EXR_READER_WINDOWS_WAVE3
  if(w3_command(id)) return;
#endif
#ifdef EXR_READER_DESKTOP_METADATA
  if(g.metadata_running) { set_status(L"正在提交书籍编辑，已接受的结果将保留。");return; }
#endif
  switch (id) {
#ifdef EXR_READER_DESKTOP_METADATA
    case IDC_METADATA_BUTTON: metadata_edit_selected();break;
#endif
#ifdef EXR_READER_WINDOWS_ACCOUNT
    case IDC_ACCOUNT_BUTTON: acct_open_dialog();break;
#endif
    case HOST_CMD_IMPORT: import_path(NULL, 1); break;
    case HOST_CMD_OPEN: open_selected_book(); break;
  }
}

/* ------------------------------------------------------------------ */
/* UI-level acceptance driver                                          */
/* ------------------------------------------------------------------ */

#ifdef EXR_READER_TEST_DRIVERS
#include "windows/shell_drive_test.inc"
#endif

/* ------------------------------------------------------------------ */
/* Preserved Windows self-check (26 documented checks, same body)      */
/* ------------------------------------------------------------------ */

typedef struct {
  exr_document *document;
  exr_fixed_document *fixed;
  exr_pager *pager;
  wchar_t file[HOST_PATH];
} selftest_book;

typedef struct {
  exr_bitmap bitmap;
  uint32_t *dib;
  wchar_t *text;
  size_t page;
} selftest_frame;

static void st_close_book(selftest_book *value) {
  if (!value) return;
  exr_pager_free(value->pager);
  exr_fixed_free(value->fixed);
  exr_document_free(value->document);
  free(value);
}

static void st_close_frame(selftest_frame *value) {
  exr_bitmap_free(&value->bitmap);
  free(value->dib);
  free(value->text);
  memset(value, 0, sizeof(*value));
}

static exr_status st_open_book(const wchar_t *path, exr_font *font, selftest_book **out) {
  WIN32_FILE_ATTRIBUTE_DATA attributes;
  selftest_book *value = NULL;
  exr_fixed_open_options fixed = {0};
  exr_layout_config config = exr_layout_config_defaults();
  exr_error error = {0};
  exr_status status;
  char *name = NULL;
  const wchar_t *extension = wcsrchr(path, L'.');
  *out = NULL;
  if (wcslen(path) >= HOST_PATH) return EXR_LIMIT;
  if (!GetFileAttributesExW(path, GetFileExInfoStandard, &attributes)) return EXR_IO;
  if (attributes.nFileSizeHigh || !attributes.nFileSizeLow || attributes.nFileSizeLow > 32u * 1024u * 1024u)
    return EXR_LIMIT;
  name = host_utf8(path);
  value = calloc(1, sizeof(*value));
  if (!name || !value) { status = EXR_MEMORY; goto done; }
  wcscpy(value->file, path);
  if (extension && (!_wcsicmp(extension, L".pdf") || !_wcsicmp(extension, L".cbz"))) {
    fixed.struct_size = sizeof(fixed);
    fixed.fallback_font = font;
    status = exr_fixed_open(name, &fixed, &value->fixed, &error);
  } else {
    status = exr_document_open(name, &value->document, &error);
    config.page = (exr_layout_options){720, 1040, 36, 28, 1.5f, 10};
    if (status == EXR_OK) status = exr_pager_create(value->document, font, &config, &value->pager, &error);
  }
done:
  free(name);
  if (status != EXR_OK) st_close_book(value);
  else *out = value;
  return status;
}

static exr_status st_render(selftest_book *value, size_t index, selftest_frame *out) {
  exr_error error = {0};
  exr_status status;
  exr_fixed_text *text = NULL;
  const char *bytes = "";
  size_t size = 0;
  memset(out, 0, sizeof(*out));
  out->page = index;
  if (value->fixed) {
    size_t count = 0;
    const exr_fixed_page *pages = exr_fixed_pages(value->fixed, &count);
    double width, height, scale;
    if (index >= count) return EXR_ARGUMENT;
    width = (pages[index].geometry.bounds[2] - pages[index].geometry.bounds[0]) * pages[index].geometry.unit_scale;
    height = (pages[index].geometry.bounds[3] - pages[index].geometry.bounds[1]) * pages[index].geometry.unit_scale;
    if (!(width > 0) || !(height > 0) || !isfinite(width) || !isfinite(height)) return EXR_FORMAT;
    scale = fmin(1, 1440 / fmax(width, height));
    status = exr_fixed_render(value->fixed, index, scale, NULL, &out->bitmap, &error);
    if (status == EXR_OK && exr_fixed_load_text(value->fixed, index, NULL, &text, &error) == EXR_OK)
      bytes = exr_fixed_text_string(text, &size);
  } else {
    const exr_layout *layout = NULL;
    status = exr_pager_get(value->pager, index, &layout, &error);
    if (status == EXR_OK) {
      const exr_page *page = exr_layout_pages(layout, NULL);
      const char *all = exr_document_text(value->document, &size);
      if (!page || page->start > page->end || page->end > size) status = EXR_FORMAT;
      else {
        bytes = all + page->start;
        size = page->end - page->start;
        status = exr_render_page_color(layout, exr_layout_font(layout), 0, &out->bitmap, &error);
      }
    }
  }
  if (status == EXR_OK) {
    size_t count = (size_t)out->bitmap.width * out->bitmap.height;
    if (out->bitmap.channels != 4 || count > SIZE_MAX / sizeof(*out->dib)) status = EXR_FORMAT;
    else {
      out->text = host_wide(bytes ? bytes : "", size);
      out->dib = malloc(count * sizeof(*out->dib));
      if (!out->text || !out->dib) status = EXR_MEMORY;
      else {
        size_t y, x;
        for (y = 0; y < out->bitmap.height; y++)
          for (x = 0; x < out->bitmap.width; x++) {
            const unsigned char *p = out->bitmap.pixels + y * out->bitmap.stride + x * 4;
            unsigned a = p[3], r = (p[0] * a + 255 * (255 - a) + 127) / 255;
            unsigned g = (p[1] * a + 255 * (255 - a) + 127) / 255;
            unsigned b = (p[2] * a + 255 * (255 - a) + 127) / 255;
            out->dib[y * out->bitmap.width + x] = (r << 16) | (g << 8) | b;
          }
      }
    }
  }
  exr_fixed_text_free(text);
  if (status != EXR_OK) st_close_frame(out);
  return status;
}

static int selftest(wchar_t **argv, int argc) {
  selftest_book *r = NULL;
  selftest_frame a = {0}, b = {0}, again = {0};
  exr_error error = {0};
  char *name = NULL, *output = NULL;
  FILE *report = NULL;
  exr_font *font = NULL;
  unsigned checks = 0;
  int result = 1;
#define CHECK(value) do { if(!(value)) goto done; checks++; } while(0)
  if (argc != 7) return 2;
  name = host_utf8(argv[2]);
  CHECK(name);
  CHECK(exr_font_open(name, &font, &error) == EXR_OK);
  free(name);
  name = NULL;
  CHECK(st_open_book(argv[3], font, &r) == EXR_OK);
  CHECK(r && r->pager);
  CHECK(st_render(r, 0, &a) == EXR_OK);
  CHECK(a.bitmap.width == 720);
  CHECK(a.bitmap.height == 1040);
  CHECK(a.bitmap.channels == 4);
  CHECK(a.dib && a.text && a.text[0]);
  CHECK(a.bitmap.stride >= a.bitmap.width * 4);
  output = host_utf8(argv[6]);
  CHECK(output);
  CHECK(exr_bitmap_write_png(&a.bitmap, output, &error) == EXR_OK);
  CHECK(st_render(r, 1, &b) == EXR_OK);
  CHECK(b.page == 1);
  st_close_frame(&b);
  CHECK(st_render(r, 0, &again) == EXR_OK);
  CHECK(a.bitmap.stride == again.bitmap.stride);
  CHECK(!memcmp(a.bitmap.pixels, again.bitmap.pixels, (size_t)a.bitmap.stride * a.bitmap.height));
  CHECK(!wcscmp(a.text, again.text));
  st_close_frame(&again);
  st_close_book(r);
  r = NULL;
  CHECK(a.bitmap.pixels && a.text[0]);
  st_close_frame(&a);
  CHECK(st_open_book(argv[4], font, &r) == EXR_OK);
  CHECK(r && r->fixed);
  CHECK(st_render(r, 0, &a) == EXR_OK);
  CHECK(a.bitmap.width > 0 && a.bitmap.height > 0);
  CHECK(a.bitmap.width <= 1440 && a.bitmap.height <= 1440);
  CHECK(a.bitmap.channels == 4 && a.dib);
  report = _wfopen(argv[5], L"wb");
  CHECK(report);
  fprintf(report, "{\n  \"schema\": 1, \"passed\": true, \"platform\": \"Windows\", \"checks\": %u, \"engine_version\": \"%s\"\n}\n",
          checks, exr_version());
  { int closed = fclose(report); report = NULL; CHECK(!closed); }
  result = 0;
done:
  if (report) fclose(report);
  st_close_frame(&a);
  st_close_frame(&b);
  st_close_frame(&again);
  st_close_book(r);
  exr_font_free(font);
  font = NULL;
  free(name);
  free(output);
  return result;
#undef CHECK
}

/* ------------------------------------------------------------------ */
/* Main window procedure and entry point                               */
/* ------------------------------------------------------------------ */

static void finish_close(HWND window) {
  if (g.job || g.pending) return;
#ifdef EXR_READER_WINDOWS_SHELL
  if(!shelf_before_exit() || !shelf_capture()) {g.closing=0;return;}
#endif
#ifdef EXR_READER_WINDOWS_PREFERENCES
  prefs_close();
#endif
#ifdef EXR_READER_WINDOWS_ACCOUNT
  /* The network worker reaches CLOSED first; the UI never waits for the network. */
  if (acct_exit_blocked()) return;
#endif
  KillTimer(window, 2);
  if (!save_progress()) {
    g.closing = 0;
    if (g.drive_mode) SetTimer(window, 1, 30, NULL);
    host_update_controls();
    return;
  }
  if (g.job) return;
  settings_save();
  DestroyWindow(window);
}

static LRESULT CALLBACK procedure(HWND window, UINT message, WPARAM wparam, LPARAM lparam) {
  if (host_offscreen && message == WM_WINDOWPOSCHANGING) {
    WINDOWPOS *position = (WINDOWPOS *)lparam;
    position->flags |= SWP_NOACTIVATE;
    if (!(position->flags & SWP_NOMOVE)) position->x = position->y = -32000;
  }
#ifdef EXR_READER_WINDOWS_IMPORT_ORGANIZE
  if(message==WM_CONTEXTMENU && winio_context((HWND)wparam,lparam)) return 0;
#endif
#ifdef EXR_HOST_WORKER_REVIEW
  if (message == WM_APP + 30) {
    /* Cloud review only: read the actual published frame/selection. These
     * observations cannot navigate, select text, or modify persisted state. */
    if (wparam == 40) return (LRESULT)g.selection.start;
    if (wparam == 41) return (LRESULT)g.selection.end;
    if (wparam == 42) return (LRESULT)g.frame.part;
    if (wparam == 43) return (LRESULT)g.frame.range_start;
    if (wparam == 44) return (LRESULT)g.frame.range_end;
    if (wparam == 45) return (LRESULT)g.selection.active;
    return review_message(window, wparam, lparam);
  }
#endif
#ifdef EXR_READER_PRODUCT_CATALOG
  if(message==WM_APP+31) { product_shelf_edges();return 0; }
#endif
#ifdef EXR_READER_WINDOWS_SHELL
  if(message==WM_SY_DONE) { sy_done(); return 0; }
  if(message==WM_ACTIVATE) sm_focus(LOWORD(wparam)!=WA_INACTIVE);
#endif
  switch (message) {
    case WM_CREATE:
      g.window = window;
      create_controls(window);
      layout_controls();
#ifdef EXR_READER_WINDOWS_SHELL
      if (FAILED(shell_d2d_create(window, &host_shell))) host_shell = NULL;
      shell_update_dpi(window);
      shell_apply_theme();
      if(host_shell) shell_prepare_settings();
      sm_create(window);
      opds_create(window);
#endif
      return 0;
    case WM_SIZE: {
      RECT bounds;
      GetWindowRect(window, &bounds);
      g.window_width = bounds.right - bounds.left;
      g.window_height = bounds.bottom - bounds.top;
#ifdef EXR_READER_WINDOWS_SHELL
      if (shell_dpi_changing) return 0;
      if (host_shell) shell_d2d_resize(host_shell, LOWORD(lparam), HIWORD(lparam));
      if (wparam != SIZE_MINIMIZED) shell_request_layout();
      if (wparam != SIZE_MINIMIZED) tts_layout();
#endif
      layout_controls();
      page_dirty(g.page,1);
      return 0;
    }
#ifdef EXR_READER_WINDOWS_SHELL
    case WM_DPICHANGED: {
      RECT *suggested = (RECT *)lparam;
      shell_dpi = HIWORD(wparam);
      shell_dpi_changing = 1;
      SetWindowPos(window, NULL, suggested->left, suggested->top,
                   suggested->right - suggested->left, suggested->bottom - suggested->top,
                   SWP_NOZORDER | SWP_NOACTIVATE);
      shell_dpi_changing = 0;
      if (host_shell) {
        RECT client; GetClientRect(window, &client);
        shell_d2d_set_dpi(host_shell, shell_dpi);
        shell_d2d_resize(host_shell, (UINT)client.right, (UINT)client.bottom);
        shell_prepare_settings();
      }
      layout_controls(); shell_request_layout(); page_dirty(g.page, 1);
      InvalidateRect(window, NULL, FALSE);
      return 0;
    }
    case WM_SYSCOLORCHANGE:
    case WM_SETTINGCHANGE:
    case WM_THEMECHANGED:
      shell_apply_theme(); break;
    case WM_ERASEBKGND:
      if (shell_active) return 1;
      break;
    case WM_PAINT:
      if (shell_active) { shell_paint(window); return 0; }
      break;
    case WM_DRAWITEM:
      if (shell_draw_item((const DRAWITEMSTRUCT *)lparam)) return TRUE;
      break;
#endif
    case WM_GETMINMAXINFO: {
      MINMAXINFO *limits = (MINMAXINFO *)lparam;
      limits->ptMinTrackSize.x = 480;
      limits->ptMinTrackSize.y = 360;
#ifdef EXR_READER_WINDOWS_SHELL
      {
        RECT minimum = {0, 0, shell_px(SHELL_MIN_CLIENT_W, shell_dpi), shell_px(SHELL_MIN_CLIENT_H, shell_dpi)};
        shell_adjust_client(&minimum, window, shell_dpi);
        limits->ptMinTrackSize.x = minimum.right - minimum.left;
        limits->ptMinTrackSize.y = minimum.bottom - minimum.top;
      }
#endif
      if (host_offscreen) {
        limits->ptMaxTrackSize.x = limits->ptMaxTrackSize.y = 32767;
      }
      RECT work;
      if (host_work_area(window, &work)) {
        if (limits->ptMinTrackSize.x > work.right - work.left) limits->ptMinTrackSize.x = work.right - work.left;
        if (limits->ptMinTrackSize.y > work.bottom - work.top) limits->ptMinTrackSize.y = work.bottom - work.top;
      }
      return 0;
    }
#ifdef EXR_READER_WINDOWS_PREFERENCES
    case WM_SETTINGCHANGE:
    case WM_THEMECHANGED:
      /* Sampled here, on the UI owner, and handed to the worker as a value. */
      prefs_system_changed();
      prefs_pump();
      return 0;
#endif
    case WM_COMMAND: {
      int id = LOWORD(wparam);
      int code = HIWORD(wparam);
#ifdef EXR_READER_WINDOWS_SHELL
      if(id==IDC_SHELL_DOCEDIT) {de_enter();return 0;}
      if (id == IDC_SHELL_BACK) { shelf_return(); return 0; }
      if (id == IDC_SHELL_SEARCH) { shell_search_set(!shell_search_open); return 0; }
      if (id == IDC_SHELL_SETTINGS) { shell_toggle_settings(); return 0; }
      if (shell_settings_command(id)) return 0;
      if (id == IDC_SHELL_TOC) { shell_toc_set(!shell_toc_open,shell_toc_keyboard); return 0; }
#endif
#ifdef EXR_READER_WINDOWS_PREFERENCES
      if(id==IDC_PREFERENCES) { prefs_show();return 0; }
#endif
#ifdef EXR_READER_PRODUCT_CATALOG
      if(id==IDC_SHELF_SEARCH && code==EN_CHANGE) {
        if(!g.shelf_applying) product_shelf_search_changed();
        return 0;
      }
      if(id==IDC_SHELF_REFRESH && code==BN_CLICKED) {
        if(!g.job && !g.pending && !g.closing) {
          product_shelf_remember();host_job *repair=job_new(JOB_PRODUCT_REPAIR);
          if(repair) { g.product_ready=0;job_submit(repair); }
        }
        return 0;
      }
      if(id==IDC_BOOKS && code==LBN_SELCHANGE) {
        product_shelf_remember();SetTimer(window,4,300,NULL);return 0;
      }
#endif
      if (id == IDC_BOOKS && code == LBN_DBLCLK) {
        open_selected_book();
        return 0;
      }
      if (id == IDC_NOTES && code == LBN_SELCHANGE) {
        if (g.job || g.pending || g.notes_book_id != g.current.id) return 0;
        int index = notes_selected();
        if (index >= 0) {
          if (g.session.fixed) note_comment_write(g.fixed_notes[index].text);
          else note_comment_write(g.session.bounded ? g.epub_notes[index].text : g.reflow_notes[index].text);
        }
        return 0;
      }
      if (id == IDC_NOTES && code == LBN_DBLCLK) {
        jump_selected_note();
        return 0;
      }
      if (code == 0 || code == BN_CLICKED) host_command(id);
      return 0;
    }
    case WM_HOST_SDK_JOB: {
      host_job *job=(host_job *)lparam;
      if(!job || job!=g.job)return 0;
      host_probe_require_ui();
      host_probe_log("sdk_thread_id",(double)GetCurrentThreadId());
      host_probe_log("sdk_job_begin",(double)job->kind);
      host_probe_pager_ms=host_probe_raster_ms=0;
      if(job_cancel_flag(job) && job->kind!=JOB_ROLLBACK && job->kind!=JOB_IMPORT_ORGANIZE && !job_commit_barrier(job->kind))job->status=EXR_CANCELLED;
      else job->status=job_run(job);
#ifdef EXR_READER_WINDOWS_SHELL
      if (job->frame.valid) {
        job->frame.shell_epoch = job->shell_epoch;
        if (job->frame.fixed) job->frame.shell_geometry = job->shell_geometry;
      }
#endif
      host_probe_log("stage_anchor_pager_ms",host_probe_pager_ms);
      host_probe_log("stage_raster_ms",host_probe_raster_ms);
      host_probe_log("sdk_job_end",(double)job->kind);
      if(job->frame.valid)host_probe_log("sdk_ready_gen",(double)job->frame.generation);
      job_launch_pixels(job);
      return 0;
    }
    case WM_HOST_PROGRESS:
      if (g.job && g.job->kind == JOB_IMPORT && !job_cancel_flag(g.job))
        set_statusf(L"正在导入… %ld%%（读取文件，可点取消）", (long)g.job->progress);
      return 0;
    case WM_HOST_COMPLETE: {
      host_job *job = (host_job *)lparam;
      if (!job || job != g.job) return 0;
      /* UI owns SDK objects; join the pixel borrower before accepting/freeing. */
      int repaint = job->kind != JOB_SAVE && job->kind != JOB_PREFETCH;
      int schedule_prefetch = job->have_frame && job->status==EXR_OK;
      if(job->thread)WaitForSingleObject(job->thread, INFINITE);
      host_probe_log("ui_complete_gen",(double)job->frame.generation);
      job_finish_sdk(job);
      g.job = NULL;
      handle_job_complete(job);
#ifdef EXR_READER_WINDOWS_WAVE3
      w3_after_complete(job);
#endif
      job_release(job);
      host_probe_log("ui_accepted_gen",(double)g.frame.generation);
      if(repaint) {
        page_dirty(g.page,0);
        /* Submit the accepted buffer before queued progress/storage jobs can
           delay the low-priority WM_PAINT message. */
        if(g.frame.valid) UpdateWindow(g.page);
      }
      if(schedule_prefetch)SetTimer(window,PAGE_PREFETCH_TIMER,150,NULL);
      if (!g.job && g.pending) {
        host_job *next = g.pending;
        g.pending = NULL;
        job_start(next);
      } else {
        host_update_controls();
      }
#ifdef EXR_READER_WINDOWS_PREFERENCES
      prefs_after_complete();
#endif
#ifdef EXR_READER_PRODUCT_CATALOG
      product_shelf_dispatch();host_update_controls();
      if(!g.job && !g.pending) PostMessageW(window,WM_APP+31,0,0);
#endif
#ifdef EXR_READER_WINDOWS_SEARCH
      winsearch_controls();
#endif
#ifdef EXR_READER_WINDOWS_NAVIGATION
      winnav_controls();
#endif
#ifdef EXR_READER_WINDOWS_SHELL
      shelf_pump();
      shell_pump_layout();
#endif
      if (g.closing) finish_close(window);
      return 0;
    }
    case WM_TIMER:
#ifdef EXR_READER_WINDOWS_SHELL
      if (wparam == SHELF_TIMER) {shelf_pump();return 0;}
      if(wparam==0x5760) { sm_tick(); return 0; }
      if(wparam==0x5C01 || wparam==0x5C02) { sy_timer(wparam); return 0; }
      if(wparam==0x5453) {tts_poll();return 0;}
      if (wparam == 0x5756) { shell_search_start(); return 0; }
      if (wparam == 0x5757) { shell_search_poll(); return 0; }
      if (wparam == 0x5753) { shell_animate(); return 0; }
      if (wparam == 0x5754) { shell_toc_animate(); return 0; }
      if (wparam == 0x5755) { shell_toc_pump(); return 0; }
      if (wparam == 0x5752) {
        KillTimer(window, 0x5752); shell_layout_waiting = 0; shell_pump_layout(); return 0;
      }
#endif
      if(wparam==PAGE_PREFETCH_TIMER) {
        KillTimer(window,PAGE_PREFETCH_TIMER);
#ifdef EXR_READER_WINDOWS_SHELL
        if(shell_toc_animating) {SetTimer(window,PAGE_PREFETCH_TIMER,20,NULL);return 0;}
#endif
        if(g.closing || !g.session.active || !g.frame.valid || g.session.txt)return 0;
#ifdef EXR_READER_WINDOWS_SHELL
        if (shell_layout_waiting || !shell_geometry_equal(g.session.shell_geometry, shell_target)) return 0;
#endif
        if(g.job || g.pending) { SetTimer(window,PAGE_PREFETCH_TIMER,20,NULL);return 0; }
        if(page_cache_find(g.session.book_id,g.session.part,g.frame.page+1)>=0)return 0;
        if(g.session.fixed && g.frame.page+1>=g.session.page_count)return 0;
        host_job *next=job_new(JOB_PREFETCH);
        if(next) { next->book_id=g.session.book_id;next->target_page=g.frame.page+1;job_start(next); }
        return 0;
      }
#ifdef EXR_READER_PRODUCT_CATALOG
      if(wparam==3) { KillTimer(window,3);product_shelf_dispatch();return 0; }
      if(wparam==4) { KillTimer(window,4);if(!g.closing) settings_save();return 0; }
#endif
#ifdef EXR_READER_WINDOWS_ACCOUNT
      if(wparam==5) { acct_tick();return 0; }
#endif
      if (wparam == 2 && g.closing && g.job) { ExitProcess(1); return 0; }
#ifdef EXR_READER_TEST_DRIVERS
      if (wparam == 1 && g.drive_mode) drive_tick();
#endif
      return 0;
    case WM_CLOSE:
#ifdef EXR_READER_WINDOWS_SHELL
      if(de_active() && !de_exit())return 0;
      tts_stop();
#endif
      if (g.closing) return 0;
#ifdef EXR_READER_WINDOWS_PREFERENCES
      prefs_close();
#endif
#ifdef EXR_READER_WINDOWS_IMPORT_ORGANIZE
      winio_close();
#endif
#ifdef EXR_READER_WINDOWS_SEARCH
      winsearch_close();
#endif
#ifdef EXR_READER_WINDOWS_NAVIGATION
      winnav_close();
#endif
#ifdef EXR_READER_WINDOWS_RECORDS
      winrecords_close();
#endif
#ifdef EXR_READER_WINDOWS_WAVE3
      w3_close();
#endif
#ifdef EXR_READER_PRODUCT_CATALOG
      product_shelf_remember();KillTimer(window,3);KillTimer(window,4);
#endif
#ifdef EXR_READER_WINDOWS_SHELL
      if(!sm_flush()) return 0;
#endif
      g.closing = 1;
#ifdef EXR_READER_WINDOWS_TXT_PROGRESS
      if (g.session.txt) g.txt_force_save = 1;
#endif
      KillTimer(window, 1);
#ifdef EXR_READER_WINDOWS_ACCOUNT
      acct_exit();
#endif
      if (g.pending) {
        job_release(g.pending);
        g.pending = NULL;
      }
      if (g.job) {
        if (!job_commit_barrier(g.job->kind)) InterlockedExchange(&g.job->cancel, 1);
        SetTimer(window, 2, 20000, NULL);
        host_update_controls();
        return 0;
      }
      finish_close(window);
      return 0;
    case WM_DESTROY:
      KillTimer(window, 1);
#ifdef EXR_READER_WINDOWS_PREFERENCES
      prefs_destroy_menu(window);
#endif
      settings_save();
#ifdef EXR_READER_WINDOWS_SHELL
      shell_search_destroy();
      shelf_destroy();
      tts_destroy();
      annot_clear();
      if(annot_brush){DeleteObject(annot_brush);annot_brush=NULL;}
      shell_d2d_destroy(host_shell);
      host_shell = NULL;
#endif
      PostQuitMessage(g.drive_mode ? (g.drive_failures ? 1 : 0) : 0);
      return 0;
  }
  return DefWindowProcW(window, message, wparam, lparam);
}

static int register_host_classes(HINSTANCE instance) {
  WNDCLASSW type;
  memset(&type, 0, sizeof(type));
  type.style = CS_HREDRAW | CS_VREDRAW;
  type.lpfnWndProc = procedure;
  type.hInstance = instance;
  type.hCursor = LoadCursor(NULL, IDC_ARROW);
#ifdef EXR_READER_WINDOWS_SHELL
  type.hbrBackground = CreateSolidBrush(shell_colorref(shell_is_dark() ? shell_theme_dark.layer_page : shell_theme_light.layer_page));
#else
  type.hbrBackground = (HBRUSH)GetStockObject(WHITE_BRUSH);
#endif
  type.lpszClassName = L"EXReaderHost";
  if (!RegisterClassW(&type)) return 0;
  memset(&type, 0, sizeof(type));
  type.style = CS_HREDRAW | CS_VREDRAW;
  type.style |= CS_DBLCLKS;
  type.lpfnWndProc = page_procedure;
  type.hInstance = instance;
  type.hCursor = LoadCursor(NULL, IDC_IBEAM);
#ifdef EXR_READER_WINDOWS_SHELL
  type.hbrBackground = CreateSolidBrush(shell_colorref(shell_is_dark() ? shell_theme_dark.layer_page : shell_theme_light.layer_page));
#else
  type.hbrBackground = (HBRUSH)GetStockObject(WHITE_BRUSH);
#endif
  type.lpszClassName = L"EXReaderPage";
  if (!RegisterClassW(&type)) return 0;
  return 1;
}

static int message_loop(void) {
  MSG message;
  while (GetMessageW(&message, NULL, 0, 0) > 0) {
#ifdef EXR_READER_WINDOWS_SHELL
    if(de_translate(&message))continue;
#endif
#ifdef EXR_READER_WINDOWS_SEARCH
    if(winsearch_translate(&message)) continue;
#endif
#ifdef EXR_READER_WINDOWS_NAVIGATION
    if(winnav_translate(&message)) continue;
#endif
#ifdef EXR_READER_WINDOWS_RECORDS
    if(winrecords_translate(&message)) continue;
#endif
#ifdef EXR_READER_WINDOWS_WAVE3
    if(w3_translate(&message)) continue;
#endif
#ifdef EXR_READER_DESKTOP_METADATA
    if(g.metadata_dialog && IsDialogMessageW(g.metadata_dialog,&message)) continue;
#endif
#ifdef EXR_READER_WINDOWS_ACCOUNT
    if(acct.dialog && IsDialogMessageW(acct.dialog,&message)) continue;
    if(message.message==WM_KEYDOWN && message.wParam=='A' && (GetKeyState(VK_CONTROL)&0x8000) && (GetKeyState(VK_SHIFT)&0x8000) &&
       !acct.dialog && g.window && IsWindowEnabled(g.window)) { acct_open_dialog();continue; }
#endif
#ifdef EXR_READER_WINDOWS_IMPORT_ORGANIZE
    if(winio.dialog && IsDialogMessageW(winio.dialog,&message)) continue;
    if(message.message==WM_KEYDOWN && (GetKeyState(VK_CONTROL)&0x8000) && (GetKeyState(VK_SHIFT)&0x8000) &&
       g.window && IsWindowEnabled(g.window) && (message.wParam=='I' || message.wParam=='O')) {
      winio_show(message.wParam=='I' ? WINIO_CLOUD:WINIO_BULK);continue;
    }
#endif
#ifdef EXR_READER_WINDOWS_PREFERENCES
    if(prefs_ui_open() && IsDialogMessageW(prefs_dialog_handle(),&message)) continue;
    prefs_translate(&message);
    if(message.message==WM_NULL) continue;
#endif
#ifdef EXR_READER_WINDOWS_SHELL
    if (shell_footnote_translate(&message)) continue;
    if (shell_translate(&message)) continue;
#endif
    if (g.window && IsDialogMessageW(g.window, &message)) continue;
    TranslateMessage(&message);
    DispatchMessageW(&message);
  }
  return (int)message.wParam;
}

static void host_cleanup(void) {
#ifdef EXR_HOST_WORKER_REVIEW
  review_shutdown();
#endif
  if (g.job) {
    if(!job_commit_barrier(g.job->kind)) InterlockedExchange(&g.job->cancel, 1);
    if (g.job->thread && WaitForSingleObject(g.job->thread, 20000) != WAIT_OBJECT_0) ExitProcess(1);
    job_release(g.job);
    g.job = NULL;
  }
  if (g.pending) {
    job_release(g.pending);
    g.pending = NULL;
  }
  if (g.discard) {
    job_release(g.discard);
    g.discard = NULL;
  }
  page_cache_clear();
#ifdef EXR_READER_WINDOWS_SHELL
  free(shell_synced_title); shell_synced_title = NULL;
  exr_anchor_free(&shell_anchor); shell_anchor_valid = 0;
  shell_selection_reset();
  dict_shutdown();
  de_close();
#endif
  session_clear(&g.session);
  frame_clear(&g.frame);
  notes_clear();
  shelf_clear();
  book_clear(&g.current);
#ifdef EXR_READER_DESKTOP_METADATA
  metadata_dialog_close();
#endif
#ifdef EXR_READER_WINDOWS_ACCOUNT
  acct_shutdown();
#endif
#ifdef EXR_READER_WINDOWS_IMPORT_ORGANIZE
  if(winio.profile_lock) { CloseHandle(winio.profile_lock);winio.profile_lock=NULL; }
#endif
#ifdef EXR_READER_PRODUCT_CATALOG
  free(g.shelf_query);g.shelf_query=NULL;
#endif
#ifdef EXR_READER_WINDOWS_WAVE3
  w3_shutdown();
#endif
  if (g.library) exr_library_close(g.library);
  g.library = NULL;
  exr_font_free(g.font);
  g.font = NULL;
  exr_font_manager_free(g.font_manager);
  g.font_manager = NULL;
#ifdef EXR_READER_TEST_DRIVERS
  if (g.drive_log) fclose(g.drive_log);
  g.drive_log = NULL;
  if (drive_file) fclose(drive_file);
  drive_file = NULL;
#endif
  DeleteCriticalSection(&g.library_lock);
#ifdef EXR_READER_PRODUCT_CATALOG
  if(g.product_lock && g.product_lock!=INVALID_HANDLE_VALUE) CloseHandle(g.product_lock);
  if(g.product_profile_lock && g.product_profile_lock!=INVALID_HANDLE_VALUE) CloseHandle(g.product_profile_lock);
  g.product_lock=NULL;
  g.product_profile_lock=NULL;
#endif
}

#include "windows/host_font.inc"

int WINAPI WinMain(HINSTANCE instance, HINSTANCE previous, LPSTR command, int show) {
  int argc = 0;
  wchar_t **argv = CommandLineToArgvW(GetCommandLineW(), &argc);
  wchar_t font_path[HOST_PATH] = L"";
  wchar_t font_config[HOST_PATH] = L"";
  wchar_t data_dir[HOST_PATH] = L"";
  wchar_t book_path[HOST_PATH] = L"";
  wchar_t library_override[HOST_PATH] = L"";
  wchar_t script[HOST_PATH] = L"";
  wchar_t evidence[HOST_PATH] = L"";
  wchar_t phase[32] = L"0";
  int i;
  INT_PTR result = 1;
  host_probe_ui_thread=GetCurrentThreadId();
  host_probe_log("ui_thread_id",(double)host_probe_ui_thread);
  (void)previous;
  (void)command;
  {
    typedef BOOL (WINAPI *dpi_context_fn)(HANDLE);
    dpi_context_fn dpi=(dpi_context_fn)(void (*)(void))GetProcAddress(GetModuleHandleW(L"user32.dll"),"SetProcessDpiAwarenessContext");
#ifdef EXR_READER_WINDOWS_SHELL
    SetLastError(0);
    shell_dpi_requested = dpi ? dpi((HANDLE)(INT_PTR)-4) : SetProcessDPIAware();
    shell_dpi_error = shell_dpi_requested ? 0 : GetLastError();
#else
    if(dpi) dpi((HANDLE)(INT_PTR)-4); else SetProcessDPIAware();
#endif
  }
  if (!argv) return 2;
  if (argc > 1 && !wcscmp(argv[1], L"--self-test")) {
    result = selftest(argv, argc);
    LocalFree(argv);
    return (int)result;
  }
  for (i = 1; i < argc; i++) {
    const wchar_t *value = (i + 1 < argc) ? argv[i + 1] : L"";
    if (!wcscmp(argv[i], L"--offscreen")) { host_offscreen = 1; }
#ifdef EXR_READER_TEST_DRIVERS
    else if (!wcscmp(argv[i], L"--drive")) { copy_wstring(script, HOST_PATH, value); i++; }
#endif
    else if (!wcscmp(argv[i], L"--evidence")) { copy_wstring(evidence, HOST_PATH, value); i++; }
    else if (!wcscmp(argv[i], L"--data")) { copy_wstring(data_dir, HOST_PATH, value); i++; }
    else if (!wcscmp(argv[i], L"--library")) { copy_wstring(library_override, HOST_PATH, value); i++; }
    else if (!wcscmp(argv[i], L"--font-config")) { copy_wstring(font_config, HOST_PATH, value); i++; }
    else if (!wcscmp(argv[i], L"--font")) { copy_wstring(font_path, HOST_PATH, value); i++; }
    else if (!wcscmp(argv[i], L"--phase")) { copy_wstring(phase, 32, value); i++; }
    else if (argv[i][0] != L'-') copy_wstring(book_path, HOST_PATH, argv[i]);
  }
  g.phase = _wtoi(phase);
  if (!data_dir[0]) {
    wchar_t local[HOST_PATH];
    if (!GetEnvironmentVariableW(L"LOCALAPPDATA", local, HOST_PATH - 32)) {
      MessageBoxW(NULL, L"无法确定宿主数据目录。", L"EXReader", MB_OK | MB_ICONERROR);
      LocalFree(argv);
      return 2;
    }
    swprintf(data_dir, HOST_PATH, L"%ls\\EXReaderHost", local);
  }
  {
    wchar_t absolute[HOST_PATH];
    if (GetFullPathNameW(data_dir, HOST_PATH, absolute, NULL)) copy_wstring(data_dir, HOST_PATH, absolute);
  }
  ensure_directory(data_dir);
  copy_wstring(g.data_dir, HOST_PATH, data_dir);
  path_join(g.settings_path, HOST_PATH, data_dir, L"host.ini");
  if (library_override[0]) copy_wstring(g.library_path, HOST_PATH, library_override);
  else path_join(g.library_path, HOST_PATH, data_dir, L"library.sqlite");
  if (script[0] && !evidence[0]) path_join(evidence, HOST_PATH, data_dir, L"drive");
  if (evidence[0]) {
    copy_wstring(g.evidence_dir, HOST_PATH, evidence);
    ensure_directory(g.evidence_dir);
  }
  if (script[0]) copy_wstring(g.script_path, HOST_PATH, script);
#ifdef EXR_READER_PRODUCT_CATALOG
  {
    wchar_t lock_path[HOST_PATH];
    if(wcslen(g.library_path)>HOST_PATH-32 || wcslen(g.data_dir)>HOST_PATH-32) { LocalFree(argv);return 2; }
    swprintf(lock_path,HOST_PATH,L"%ls\\product.profile.lock",g.data_dir);
    g.product_profile_lock=CreateFileW(lock_path,GENERIC_READ|GENERIC_WRITE,0,NULL,OPEN_ALWAYS,FILE_ATTRIBUTE_NORMAL,NULL);
    if(g.product_profile_lock==INVALID_HANDLE_VALUE) {
      if(!script[0]) MessageBoxW(NULL,L"此本机阅读配置正在使用，或无法取得访问权限。",L"EXReader",MB_OK|MB_ICONERROR);
      LocalFree(argv);return 2;
    }
    swprintf(g.product_path,HOST_PATH,L"%ls.product.sqlite",g.library_path);
#ifdef EXR_READER_WINDOWS_TXT_RECOVERY
    swprintf(g.original_root,HOST_PATH,L"%ls.originals",g.library_path);
#endif
    swprintf(lock_path,HOST_PATH,L"%ls.product.lock",g.library_path);
    g.product_lock=CreateFileW(lock_path,GENERIC_READ|GENERIC_WRITE,0,NULL,OPEN_ALWAYS,FILE_ATTRIBUTE_NORMAL,NULL);
    if(g.product_lock==INVALID_HANDLE_VALUE) {
      if(!script[0]) MessageBoxW(NULL,L"此本机书库正在使用，或无法取得访问权限。",L"EXReader",MB_OK|MB_ICONERROR);
      CloseHandle(g.product_profile_lock);g.product_profile_lock=NULL;
      LocalFree(argv);return 2;
    }
  }
#endif
  settings_load();
  InitializeCriticalSection(&g.library_lock);
  {
    exr_error error = {0};
    char *path = host_utf8(library_override[0] ? library_override : g.library_path);
    exr_status status = path ? exr_library_open(path, &g.library, &error) : EXR_MEMORY;
    free(path);
    if (status != EXR_OK) {
      wchar_t message[512];
      describe_error(message, 512, L"无法打开书架数据库", status, &error);
      if (!script[0]) MessageBoxW(NULL, message, L"EXReader", MB_OK | MB_ICONERROR);
      set_status(message);
      host_cleanup();
      LocalFree(argv);
      return 2;
    }
  }
  {
    exr_error error = {0};
    exr_status status = host_open_body_font(font_path, font_config, &error);
    if (status != EXR_OK) {
      wchar_t message[512];
      describe_error(message, 512, L"无法打开正文字体", status, &error);
      if (!script[0]) MessageBoxW(NULL, message, L"EXReader", MB_OK | MB_ICONERROR);
      set_status(message);
      host_cleanup();
      LocalFree(argv);
      return 2;
    }
  }
  if (!register_host_classes(instance)) {
    host_cleanup();
    LocalFree(argv);
    return 2;
  }
  g.drive_mode = script[0] != 0;
  g.window = CreateWindowExW(host_offscreen ? WS_EX_NOACTIVATE : 0, L"EXReaderHost", L"EXReader", WS_OVERLAPPEDWINDOW,
                           host_offscreen ? -32000 : CW_USEDEFAULT, host_offscreen ? -32000 : CW_USEDEFAULT, g.window_width, g.window_height,
                           NULL, NULL, instance, NULL);
  if (!g.window) {
    host_cleanup();
    LocalFree(argv);
    return 2;
  }
  {
    LONG_PTR style = GetWindowLongPtrW(g.window, GWL_EXSTYLE);
    SetWindowLongPtrW(g.window, GWL_EXSTYLE, style | WS_EX_CONTROLPARENT);
  }
  if (!host_offscreen) host_fit_work_area(g.window);
  ShowWindow(g.window, host_offscreen ? SW_SHOWNOACTIVATE : (show ? show : SW_SHOWNORMAL));
  UpdateWindow(g.window);
#ifdef EXR_READER_WINDOWS_WAVE3
  w3_startup();
#endif
  reload_shelf();
#ifdef EXR_READER_WINDOWS_SHELL
  shelf_load();
#endif
#ifdef EXR_READER_PRODUCT_CATALOG
  {
    host_job *repair=job_new(JOB_PRODUCT_REPAIR);
    if(repair) job_start(repair);
    else { g.product_pending=1;set_status(L"无法启动书目修复；原书仍保留，可重启后重试。"); }
  }
#endif
#ifdef EXR_READER_TEST_DRIVERS
  if (script[0]) drive_start();
#endif
  if (book_path[0] && !script[0]) {
    g.auto_open_imported = 1;
#ifdef EXR_READER_PRODUCT_CATALOG
    host_job *import=job_new(JOB_IMPORT);
    if(import) {
      copy_wstring(import->path,HOST_PATH,book_path);
      if(g.job) g.pending=import;else job_submit(import);
    }
#else
    import_path(book_path, 0);
#endif
#ifdef EXR_READER_WINDOWS_TXT_PROGRESS
  } else if (g.active_txt_key[0]) {
    host_job *job = job_new(JOB_OPEN);
    if (job) {
      snprintf(job->product_key,sizeof(job->product_key),"%s",g.active_txt_key);
      job->font_percent=g.font_percent;
      if(g.job) g.pending=job; else job_submit(job);
    }
#endif
  } else if (g.active_book_id > 0
#ifndef EXR_READER_PRODUCT_CATALOG
             && shelf_index(g.active_book_id) >= 0
#endif
  ) {
    host_job *job = job_new(JOB_OPEN);
    int selected=shelf_index(g.active_book_id);
    if(selected>=0) SendMessageW(g.books, LB_SETCURSEL, (WPARAM)selected, 0);
    if (job) {
      job->book_id = g.active_book_id;
      job->font_percent = g.font_percent;
#ifdef EXR_READER_PRODUCT_CATALOG
      if(g.job) g.pending=job;else job_submit(job);
#else
      job_submit(job);
#endif
    }
  } else if (g.shelf_count > 0) {
    SendMessageW(g.books, LB_SETCURSEL, 0, 0);
    set_status(L"选择一本书并点击“打开”，或导入新书。");
  } else {
    set_status(L"书架为空：打开一本书开始阅读。");
  }
#ifdef EXR_READER_WINDOWS_SHELL
#endif
  host_update_controls();
  result = message_loop();
  host_cleanup();
  LocalFree(argv);
  return (int)result;
}
