/* SPDX-License-Identifier: MIT */
/* EXReader Windows native reference host.
 *
 * Win32 host for the installed EXReader SDK: SQLite-backed bookshelf, non-blocking
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
#include <windows.h>
#include <commdlg.h>
#include <shellapi.h>
#include <process.h>
#include <exreader.h>
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
#define HOST_PAGE_GLYPH_LIMIT ((size_t)65536)
#ifdef EXR_READER_WINDOWS_SEARCH
#include "../apps/reader/desktop/windows_search_types.h"
#endif

enum {
  IDC_IMPORT_LABEL = 100, IDC_IMPORT_EDIT, IDC_IMPORT_BUTTON, IDC_OPEN_BUTTON,
  IDC_DELETE_BUTTON, IDC_PREV, IDC_NEXT, IDC_SELECT_ALL, IDC_COPY_QUOTE,
  IDC_ADD_NOTE, IDC_UPDATE_NOTE, IDC_DELETE_NOTE, IDC_JUMP_NOTE,
  IDC_FONT_DEC, IDC_FONT_INC, IDC_ZOOM_DEC, IDC_ZOOM_INC, IDC_CANCEL,
  IDC_SHELF_LABEL, IDC_BOOKS, IDC_NOTES_LABEL, IDC_NOTES, IDC_NOTE_EDIT,
  IDC_PAGE, IDC_PAGE_LABEL, IDC_STATUS, IDC_SHELF_SEARCH, IDC_SHELF_REFRESH,
  IDC_METADATA_BUTTON, IDC_METADATA_TITLE, IDC_METADATA_AUTHOR, IDC_METADATA_FAVORITE,
  IDC_METADATA_SAVE, IDC_METADATA_CANCEL, IDC_METADATA_RETRY, IDC_METADATA_DISCARD,
  IDC_METADATA_MESSAGE,
  IDC_ACCOUNT_BUTTON, IDC_ACCOUNT_ROOT, IDC_ACCOUNT_USER, IDC_ACCOUNT_PASSWORD, IDC_ACCOUNT_REMEMBER,
  IDC_ACCOUNT_APPLY, IDC_ACCOUNT_SYNC, IDC_ACCOUNT_CANCEL, IDC_ACCOUNT_RETRY, IDC_ACCOUNT_FORGET,
  IDC_ACCOUNT_CLOSE, IDC_ACCOUNT_MESSAGE, IDC_ACCOUNT_DETAIL,
  /* Accessibility labels only: no original or account control id moves. */
  IDC_SHELF_SEARCH_LABEL = 150, IDC_NOTE_EDIT_LABEL
};

#define WM_HOST_COMPLETE (WM_APP + 1)
#define WM_HOST_PROGRESS (WM_APP + 2)

typedef struct {
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
} host_frame;

typedef struct {
  int active;
  int fixed;
  size_t page, start, end;
} host_selection;

typedef struct {
  int active;
  int fixed;
  int64_t book_id;
  exr_document *document;
  exr_publication *publication;
  int bounded;
  int hold_progress;
  size_t part;
  exr_pager *pager;
  exr_fixed_document *fixed_document;
  exr_layout_config config;
  size_t page;
  size_t page_count;
#ifdef EXR_READER_WINDOWS_SEARCH
  char search_key[READER_SEARCH_SOURCE_KEY_MAX+1];
#endif
} host_session;

typedef struct host_job host_job;
#ifdef EXR_READER_PRODUCT_CATALOG
typedef struct { char *key,*sort_title; } host_shelf_cursor;
#endif

typedef struct {
  HWND window, page, books, notes, note_edit, import_edit, status, page_label;
  HWND import_label, import_button, open_button, delete_button;
  HWND prev_button, next_button, select_button, copy_button;
  HWND add_button, update_button, remove_button, jump_button;
  HWND font_dec, font_inc, zoom_dec, zoom_inc, cancel_button;
  HWND shelf_label, notes_label, shelf_search_label, note_edit_label;
  exr_library *library;
  exr_font *font;
  wchar_t font_path[HOST_PATH];
  wchar_t data_dir[HOST_PATH];
  wchar_t library_path[HOST_PATH];
#ifdef EXR_READER_PRODUCT_CATALOG
  wchar_t product_path[HOST_PATH];
  HANDLE product_lock;
  HANDLE product_profile_lock;
  int product_pending;
  HWND shelf_search,shelf_refresh;
  WNDPROC shelf_procedure;
  host_shelf_cursor *shelf_cursors;
  char *shelf_query;
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
  unsigned long saved_generation;
  unsigned long frame_sequence;
} host_state;

static host_state g;
static int dragging;
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
static void host_a11y_prepare_note(void);
static void host_a11y_owner_enabled(int enabled);

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

static void frame_move(host_frame *dst, host_frame *src) {
  frame_clear(dst);
  *dst = *src;
  memset(src, 0, sizeof(*src));
}

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
  if (session->fixed_document) exr_fixed_free(session->fixed_document);
  if (session->pager) exr_pager_free(session->pager);
  if (session->publication) exr_publication_free(session->publication);
  if (session->document) exr_document_free(session->document);
  memset(session, 0, sizeof(*session));
}

static void selection_clear(void) {
  memset(&g.selection, 0, sizeof(g.selection));
  if (g.page) InvalidateRect(g.page, NULL, FALSE);
}

/* Settings: host preferences only. Books, progress and annotations live in SQLite. */
static void settings_load(void) {
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
#endif
}

static void settings_save(void) {
  wchar_t number[64];
  if (!g.settings_path[0]) return;
#ifdef EXR_READER_PRODUCT_CATALOG
  product_shelf_remember();
  wchar_t *query=host_wide(g.shelf_query ? g.shelf_query:"",g.shelf_query ? strlen(g.shelf_query):0);
  WritePrivateProfileStringW(L"Shelf",L"Query",query ? query:L"",g.settings_path);free(query);
  wchar_t *key=host_wide(g.shelf_top_key,strlen(g.shelf_top_key));
  WritePrivateProfileStringW(L"Shelf",L"TopKey",key ? key:L"",g.settings_path);free(key);
  key=host_wide(g.shelf_selected_key,strlen(g.shelf_selected_key));
  WritePrivateProfileStringW(L"Shelf",L"SelectedKey",key ? key:L"",g.settings_path);free(key);
#endif
  swprintf(number, 64, L"%d", g.font_percent);
  WritePrivateProfileStringW(L"Host", L"FontPercent", number, g.settings_path);
  swprintf(number, 64, L"%d", g.zoom_percent);
  WritePrivateProfileStringW(L"Host", L"ZoomPercent", number, g.settings_path);
  swprintf(number, 64, L"%d", g.window_width);
  WritePrivateProfileStringW(L"Host", L"WindowWidth", number, g.settings_path);
  swprintf(number, 64, L"%d", g.window_height);
  WritePrivateProfileStringW(L"Host", L"WindowHeight", number, g.settings_path);
  swprintf(number, 64, L"%lld", (long long)g.active_book_id);
  WritePrivateProfileStringW(L"Host", L"ActiveBook", number, g.settings_path);
}

/* ------------------------------------------------------------------ */
/* Bookshelf and annotation snapshots                                  */
/* ------------------------------------------------------------------ */

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
    author && author[0] ? author:L"未知作者",format_name(book->format),book->id ? L"":L" · 未下载",mark);
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
  return EXR_OK;
}

static int shelf_index(int64_t id) {
  size_t i;
  for (i = 0; i < g.shelf_count; i++)
    if (g.shelf[i].id == id) return (int)i;
  return -1;
}

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

static exr_status reload_notes(void) {
  exr_error error = {0};
  exr_status status = EXR_OK;
  exr_note *reflow = NULL;
  exr_epub_note *epub = NULL;
  exr_fixed_note *fixed = NULL;
  size_t count = 0;
  if (!g.has_current || !g.session.active) {
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
  JOB_SEARCH_BATCH, JOB_SEARCH_OPEN };
#ifdef EXR_READER_WINDOWS_ACCOUNT
static int account_job_kind(int kind) { return kind>=JOB_ACCOUNT_LOAD && kind<=JOB_ACCOUNT_RECEIVE; }
#endif
#ifdef EXR_READER_DESKTOP_METADATA
static int metadata_job_kind(int kind) { return kind>=JOB_METADATA_PREPARE && kind<=JOB_METADATA_DISCARD; }
#endif
static int job_commit_barrier(int kind) {
  return kind==JOB_SAVE
#ifdef EXR_READER_DESKTOP_METADATA
    || metadata_job_kind(kind)
#endif
  ;
}
#ifdef EXR_READER_PRODUCT_CATALOG
static int product_job_kind(int kind) {
  return kind==JOB_PRODUCT_ATTACH || kind==JOB_PRODUCT_REPAIR || kind==JOB_PRODUCT_DELETE || kind==JOB_PRODUCT_SHELF;
}
#endif

struct host_job {
  LONG refs;
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
#ifdef EXR_READER_WINDOWS_SEARCH
  char *search_query;
  unsigned long search_generation;
  reader_search_cursor search_resume;
  int search_has_resume;
  host_search_batch search_batch;
  host_search_hit search_hit;
#endif
#ifdef EXR_READER_PRODUCT_CATALOG
  int product_auto_open,product_deleted;
  int product_shelf_direction,product_shelf_before,product_shelf_after;
  unsigned long product_shelf_generation;
  char *product_shelf_query,*product_cursor_title,*product_cursor_key,*product_anchor_key;
  exr_book *product_books;size_t product_book_count;
  char product_key[READER_BOOK_KEY_CAPACITY];
  host_shelf_cursor *product_cursors;
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
};

static int job_cancel_flag(host_job *job) {
  return job && InterlockedCompareExchange((volatile LONG *)&job->cancel, 0, 0) != 0;
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
  return job;
}
#ifdef EXR_READER_WINDOWS_SEARCH
static void winsearch_hit_free(host_search_hit *hit);
static void winsearch_batch_free(host_search_batch *batch);
static exr_status winsearch_job(host_job *job);
static void winsearch_accept(host_job *job);
static void winsearch_close(void);
static exr_status winsearch_identity(int64_t book, exr_format format, int fixed, int bounded,
  char out[READER_SEARCH_SOURCE_KEY_MAX+1], const exr_control *control, exr_error *error);
#endif

static void job_free(host_job *job) {
  if (!job) return;
#ifdef EXR_READER_WINDOWS_SEARCH
  free(job->search_query);
  winsearch_hit_free(&job->search_hit);
  winsearch_batch_free(&job->search_batch);
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

static void job_start(host_job *job) {
  uintptr_t handle;
  unsigned thread_id = 0;
  g.job = job;
  if (job->kind != JOB_HIT && job->kind != JOB_SAVE
#ifdef EXR_READER_WINDOWS_SEARCH
      && job->kind != JOB_SEARCH_BATCH
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
  dragging = 0;
  g.hit_pending = 0; g.gesture++;
  if (GetCapture() == g.page) ReleaseCapture();
  memset(&g.selection, 0, sizeof(g.selection));
  if (g.page) InvalidateRect(g.page, NULL, TRUE);
  }
  InterlockedIncrement(&job->refs);
  handle = _beginthreadex(NULL, 0, job_thread, job, 0, &thread_id);
  if (!handle) {
#ifdef EXR_READER_PRODUCT_CATALOG
    if(product_job_kind(job->kind)) g.product_pending=1;
#endif
    InterlockedDecrement(&job->refs);
    g.job = NULL;
    job->status = EXR_MEMORY;
    strcpy(job->error.message, "Cannot create host worker thread");
#ifdef EXR_READER_DESKTOP_METADATA
    if(metadata_job_kind(job->kind)) metadata_failed_to_start(job);
#endif
    job_release(job);
    set_status(L"无法创建后台任务线程。");
    host_update_controls();
    return;
  }
  job->thread = (HANDLE)handle;
  host_update_controls();
}

static void job_supersede(void) {
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

static void job_cancel_button(void) {
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

static void session_configure(host_session *session, int font_percent) {
  /* exr_layout_options.font_size is a point size, not a scale: the preserved
     self-test uses 28 points with 1.5 line height. Percent maps onto that base. */
  if (font_percent < HOST_FONT_MIN) font_percent = HOST_FONT_MIN;
  if (font_percent > HOST_FONT_MAX) font_percent = HOST_FONT_MAX;
  session->config = exr_layout_config_defaults();
  session->config.page.width = 720;
  session->config.page.height = 1040;
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
  status = exr_publication_pager_create(session->publication, part, g.font, &session->config, &options, out, error);
  if (status == EXR_OK) status = exr_pager_set_cache(*out, 2, 8 * 1024 * 1024, error);
  if (status == EXR_OK) status = exr_pager_set_checkpoints(*out, 8, 4 * 1024 * 1024, 8, error);
  if (status != EXR_OK) { exr_pager_free(*out); *out = NULL; }
  return status;
}

/* A valid get-mode pager reports this exact public error only for normal EOF.
   Other ARGUMENT/IO/LIMIT failures are never treated as a chapter boundary. */
static int pager_eof(exr_status status, const exr_error *error) {
  return status == EXR_ARGUMENT && error && !strcmp(error->message, "Page index is outside the document");
}

static exr_status render_reflow(host_session *session, size_t page, host_frame *out,
                                const exr_control *control, exr_error *error) {
  const exr_layout *layout = NULL;
  const exr_page *info;
  exr_page saved_info;
  const char *text;
  size_t count = 0, size = 0;
  exr_status status;
  memset(out, 0, sizeof(*out));
  status = exr_pager_get(session->pager, page, &layout, error);
  if (status != EXR_OK) return status;
  info = exr_layout_pages(layout, &count);
  if (!info || count < 1) return EXR_FORMAT;
  saved_info = *info; info = &saved_info;
  if (info->start > info->end || info->end - info->start > HOST_PAGE_TEXT_LIMIT) return EXR_LIMIT;
  text = session->bounded ? NULL : exr_document_text(session->document, &size);
  if (!session->bounded && (!text || info->end > size)) return EXR_FORMAT;
  status = exr_render_page_ex(layout, exr_layout_font(layout), 0, 4, control, &out->bitmap, error);
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
    if (status == EXR_OK) status = exr_pager_anchor_create(session->pager, info->start, info->start, control, &out->point, error);
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
  if (!isfinite(scale) || scale <= 0) return EXR_ARGUMENT;
  if (width * scale > 4096.0 || height * scale > 4096.0) {
    double limit = fmin(4096.0 / width, 4096.0 / height);
    scale = limit;
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
      if (session->bounded ? !pager_eof(status, error) : status != EXR_ARGUMENT) return status;
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
    if (status != EXR_OK && (session->bounded ? !pager_eof(status, error) : status != EXR_ARGUMENT)) return status;
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
    if (session->bounded) extent = exr_pager_chapter_statistics(session->pager).projection_bytes;
    else exr_document_text(session->document, &extent);
    if (offset < info->start || (offset >= info->end && !(offset == extent && info->end == extent)))
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

static exr_status job_open(host_job *job) {
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
    if (target >= count) {
      target = count - 1;
      copy_wstring(job->message, 512, L"保存的页码超出范围，已回到最后一页。");
    }
    {
      exr_control control = {job_cancel_check, NULL, job};
      status = render_fixed(&session, target, g.zoom_percent, &job->frame, &control, &error);
    }
  } else {
    exr_library_epub_info info = {sizeof(info), 0, 0};
    session_configure(&session, job->font_percent > 0 ? job->font_percent : g.font_percent);
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
        status = exr_publication_open_source(&source, &session.publication, &error);
        if (status != EXR_OK) source.release(source.context);
      }
    } else if (status == EXR_OK) status = exr_library_document(g.library, book.id, &session.document, &error);
    LeaveCriticalSection(&g.library_lock);
    if (status == EXR_OK && !session.bounded)
      status = exr_pager_create(session.document, g.font, &session.config, &session.pager, &error);
    if (status == EXR_OK && !session.bounded) status = exr_pager_set_cache(session.pager, 2, 0, &error);
    if (status == EXR_OK && !session.bounded) status = exr_pager_set_checkpoints(session.pager, 8, 4 * 1024 * 1024, 8, &error);
    if (status == EXR_OK) {
      size_t page = 0;
      exr_control control = {job_cancel_check, NULL, job};
      status = session.bounded ? bounded_restore(&session, &control, &page, job->message, 512, &error)
                               : reflow_restore(&session, &control, &page, job->message, 512);
      if (status == EXR_OK) status = render_reflow(&session, page, &job->frame, &control, &error);
    }
  }
#ifdef EXR_READER_WINDOWS_SEARCH
  if(status==EXR_OK) {
    exr_control control={job_cancel_check,NULL,job};
    status=winsearch_identity(book.id,book.format,session.fixed,session.bounded,session.search_key,&control,&error);
  }
#endif
  if (status == EXR_OK && job_cancel_flag(job)) {
    session_clear(&session);
    book_clear(&book);
    return EXR_CANCELLED;
  }
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

static exr_status job_bounded_go(host_job *job) {
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

static exr_status job_go(host_job *job) {
  exr_error error = {0};
  exr_status status;
  if (!g.session.active) return EXR_ARGUMENT;
  if (job->book_id && job->book_id != g.session.book_id) return EXR_CANCELLED;
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
  }
  if (status == EXR_OK) {
    job->have_frame = 1;
    job->applied_page = job->frame.page;
    job->page_count = g.session.page_count;
  }
  return status;
}

static exr_status job_layout(host_job *job) {
  exr_error error = {0};
  exr_status status;
  exr_pager *pager = NULL;
  exr_layout_config config;
  exr_control control = {job_cancel_check, NULL, job};
  size_t page = 0;
  size_t offset = job->has_anchor ? job->anchor.start : 0;
  if (!g.session.active || g.session.fixed || (!g.session.document && !g.session.bounded)) return EXR_ARGUMENT;
  if (job->book_id && job->book_id != g.session.book_id) return EXR_CANCELLED;
  config = g.session.config;
  config.page.font_size = 28.0f * (float)job->font_percent / 100.0f;
  config.control.cancelled = host_cancel_check;
  config.control.context = NULL;
  if (g.session.bounded) {
    host_session candidate = g.session; exr_anchor point = {0}; exr_anchor_match match;
    status = exr_pager_anchor_create(g.session.pager, g.frame.range_start, g.frame.range_start, &control, &point, &error);
    candidate.config = config;
    if (status == EXR_OK) status = bounded_pager(&candidate, candidate.part, &pager, &error);
    candidate.pager = pager;
    if (status == EXR_OK) status = exr_pager_anchor_resolve(pager, &point, &control, &match, &error);
    if (status == EXR_OK) {
      size_t target = match.state == EXR_ANCHOR_FOUND ? match.start : point.start;
      if (match.state != EXR_ANCHOR_FOUND) {
        host_text_sink sink = {NULL, 0, 0};
        status = exr_pager_read_text(pager, target, target, page_text_sink, &sink, &control, &error);
        candidate.hold_progress = 1;
        copy_wstring(job->message, 512, L"字号变化时锚点未唯一匹配，按原章内偏移重排（未精确锚定）；保留原进度记录。");
      }
      if (status == EXR_OK) status = page_for_offset(&candidate, target, &control, &page, NULL, NULL, &error);
    }
    if (status == EXR_OK) status = render_reflow(&candidate, page, &job->frame, &control, &error);
    exr_anchor_free(&point);
    if (status == EXR_OK) {
      job->candidate_pager = pager; job->candidate_config = config; job->have_frame = 1; job->applied_page = page;
    } else exr_pager_free(pager);
    job->error = error; return status;
  }
  status = exr_pager_create(g.session.document, g.font, &config, &pager, &error);
  if (status == EXR_OK) status = exr_pager_set_cache(pager, 2, 0, &error);
  if (status == EXR_OK) status = exr_pager_set_checkpoints(pager, 8, 4 * 1024 * 1024, 8, &error);
  if (status == EXR_OK && job->has_anchor) {
    exr_anchor_match match;
    exr_status resolved = exr_anchor_resolve_ex(g.session.document, &job->anchor, &control, &match, &error);
    if (resolved != EXR_OK) { exr_pager_free(pager); return resolved; }
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
    status = page_for_offset(&candidate, offset, &control, &page, NULL, NULL, &error);
    if (status == EXR_OK)
      status = render_reflow(&candidate, page, &job->frame, &control, &error);
    if (status == EXR_OK) {
      job->candidate_pager = pager; pager = NULL;
      job->candidate_config = config;
      job->have_frame = 1;
      job->applied_page = page;
      job->session_swapped = 0;
    }
  }
  if (pager) exr_pager_free(pager);
  return status;
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
static unsigned __stdcall job_thread(void *context) {
  host_job *job = context;
  job_pause(job);
  if (job_cancel_flag(job) && job->kind != JOB_ROLLBACK && !job_commit_barrier(job->kind))
    job->status = EXR_CANCELLED;
  else
    job->status = job_run(job);
#ifdef EXR_HOST_WORKER_REVIEW
  if (job->status == EXR_OK) {
    int stage=job->kind==JOB_OPEN ? 4:job->kind==JOB_GO ? 2:0;
#ifdef EXR_HOST_SHELF_REVIEW
    if(job->kind==JOB_PRODUCT_SHELF) stage=5;
#endif
    review_pause(stage,job);
  }
#endif
  if (job->status == EXR_OK && job_cancel_flag(job) && job->kind != JOB_NOTE_ADD && job->kind != JOB_NOTE_UPDATE
#ifdef EXR_READER_DESKTOP_METADATA
      && !metadata_job_kind(job->kind)
#endif
#ifdef EXR_READER_PRODUCT_CATALOG
      && !(job->kind==JOB_PRODUCT_DELETE && job->product_deleted)
#endif
  )
    job->status = job->kind == JOB_IMPORT ? rollback_import(job) : EXR_CANCELLED;
  if (job->status == EXR_CANCELLED) frame_clear(&job->frame);
  if (!PostMessageW(g.window, WM_HOST_COMPLETE, 0, (LPARAM)job)) {
    /* Window gone; the UI-side reference is released during shutdown. */
  }
  job_release(job);
  return 0;
}

static exr_status job_hit(host_job *job) {
  const exr_layout *layout = NULL; exr_status status;
  if (!g.session.bounded || g.session.book_id != job->book_id || g.session.part != job->target_part ||
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
  switch (job->kind) {
    case JOB_OPEN: return job_open(job);
    case JOB_GO: return job_go(job);
    case JOB_LAYOUT: return job_layout(job);
    case JOB_IMPORT: return job_import(job);
    case JOB_NOTE_ADD: case JOB_NOTE_UPDATE: return job_note(job);
    case JOB_ROLLBACK: return rollback_import(job);
    case JOB_HIT: return job_hit(job);
    case JOB_SAVE: return job_save(job);
#ifdef EXR_READER_WINDOWS_SEARCH
    case JOB_SEARCH_BATCH: case JOB_SEARCH_OPEN: return winsearch_job(job);
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
static void change_font(int delta);
static void change_zoom(int delta);
static void select_all_page(void);
static void copy_quote(void);
static void add_note(void);
static void update_note(void);
static void delete_note(void);
static void jump_selected_note(void);
static void open_selected_book(void);
static void delete_selected_book(void);
static void import_path(const wchar_t *path, int dialog_fallback);
static int save_progress(void);
static void update_page_label(void);
static void handle_job_complete(host_job *job);
/* Used by the accessibility provider, which is compiled before this function. */
static size_t point_offset(int x, int y, int at_end);

static HWND make_button(HWND parent, int id, const wchar_t *text) {
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
#ifdef EXR_READER_WINDOWS_SEARCH
#include "../apps/reader/desktop/windows_search.inc"
#endif

static void create_controls(HWND parent) {
  g.import_label = make_static(parent, IDC_IMPORT_LABEL, L"导入路径");
  g.import_edit = CreateWindowExW(WS_EX_CLIENTEDGE, L"EDIT", L"", WS_CHILD | WS_VISIBLE | WS_TABSTOP |
                                  ES_AUTOHSCROLL, 0, 0, 10, 10, parent, (HMENU)(INT_PTR)IDC_IMPORT_EDIT, NULL, NULL);
  SendMessageW(g.import_edit, WM_SETFONT, (WPARAM)GetStockObject(DEFAULT_GUI_FONT), TRUE);
  g.import_button = make_button(parent, IDC_IMPORT_BUTTON, L"导入(&I)");
  g.open_button = make_button(parent, IDC_OPEN_BUTTON, L"打开(&O)");
  g.delete_button = make_button(parent, IDC_DELETE_BUTTON, L"删除(&D)");
  g.prev_button = make_button(parent, IDC_PREV, L"上一页(&P)");
  g.next_button = make_button(parent, IDC_NEXT, L"下一页(&N)");
  g.select_button = make_button(parent, IDC_SELECT_ALL, L"全选本页(&A)");
  g.copy_button = make_button(parent, IDC_COPY_QUOTE, L"复制引用(&C)");
  g.add_button = make_button(parent, IDC_ADD_NOTE, L"添加标注(&T)");
  g.update_button = make_button(parent, IDC_UPDATE_NOTE, L"更新标注(&U)");
  g.remove_button = make_button(parent, IDC_DELETE_NOTE, L"删除标注(&R)");
  g.jump_button = make_button(parent, IDC_JUMP_NOTE, L"跳转标注(&J)");
  g.font_dec = make_button(parent, IDC_FONT_DEC, L"字号-");
  g.font_inc = make_button(parent, IDC_FONT_INC, L"字号+");
  g.zoom_dec = make_button(parent, IDC_ZOOM_DEC, L"缩放-");
  g.zoom_inc = make_button(parent, IDC_ZOOM_INC, L"缩放+");
  g.cancel_button = make_button(parent, IDC_CANCEL, L"取消(&X)");
#ifdef EXR_READER_WINDOWS_SEARCH
  inbook.button = make_button(parent, IDC_INBOOK, L"书内查找(&B)");
#endif
  g.shelf_label = make_static(parent, IDC_SHELF_LABEL, L"书架");
  g.books = CreateWindowExW(WS_EX_CLIENTEDGE, L"LISTBOX", L"书架",
                            WS_CHILD | WS_VISIBLE | WS_TABSTOP | WS_VSCROLL | LBS_NOTIFY | LBS_NOINTEGRALHEIGHT,
                            0, 0, 10, 10, parent, (HMENU)(INT_PTR)IDC_BOOKS, NULL, NULL);
  SendMessageW(g.books, WM_SETFONT, (WPARAM)GetStockObject(DEFAULT_GUI_FONT), TRUE);
#ifdef EXR_READER_PRODUCT_CATALOG
  /* A real static with a mnemonic names the search box (the same native path the
     import field already uses) and gives it an Alt access key. */
  g.shelf_search_label=make_static(parent,IDC_SHELF_SEARCH_LABEL,L"\u641c\u7d22(&S)");
  g.shelf_search=CreateWindowExW(WS_EX_CLIENTEDGE,L"EDIT",L"",WS_CHILD|WS_VISIBLE|WS_TABSTOP|ES_AUTOHSCROLL,
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
                            WS_CHILD | WS_VISIBLE | WS_TABSTOP | WS_VSCROLL | LBS_NOTIFY | LBS_NOINTEGRALHEIGHT,
                            0, 0, 10, 10, parent, (HMENU)(INT_PTR)IDC_NOTES, NULL, NULL);
  SendMessageW(g.notes, WM_SETFONT, (WPARAM)GetStockObject(DEFAULT_GUI_FONT), TRUE);
  g.note_edit_label = make_static(parent, IDC_NOTE_EDIT_LABEL, L"\u6807\u6ce8\u5185\u5bb9(&M)");
  g.note_edit = CreateWindowExW(WS_EX_CLIENTEDGE, L"EDIT", L"", WS_CHILD | WS_VISIBLE | WS_TABSTOP |
                                 ES_MULTILINE | ES_AUTOVSCROLL | WS_VSCROLL,
                                 0, 0, 10, 10, parent, (HMENU)(INT_PTR)IDC_NOTE_EDIT, NULL, NULL);
  SendMessageW(g.note_edit, WM_SETFONT, (WPARAM)GetStockObject(DEFAULT_GUI_FONT), TRUE);
  /* Multiline editing without swallowing Tab: see host_a11y_prepare_note. */
  host_a11y_prepare_note();
  g.page = CreateWindowExW(WS_EX_CLIENTEDGE, L"EXReaderPage", L"阅读区域",
                           WS_CHILD | WS_VISIBLE | WS_TABSTOP, 0, 0, 10, 10, parent,
                           (HMENU)(INT_PTR)IDC_PAGE, NULL, NULL);
  g.page_label = make_static(parent, IDC_PAGE_LABEL, L"未打开书籍");
  g.status = make_static(parent, IDC_STATUS, L"就绪");
  SetWindowLongPtrW(g.status, GWL_STYLE, GetWindowLongPtrW(g.status, GWL_STYLE) | SS_ENDELLIPSIS);
  SetWindowTextW(parent, L"EXReader");
}

static void layout_controls(void) {
  RECT area;
  int width, height, left_width, content_top = 76, content_bottom;
  int books_height, notes_top, notes_height;
  const int button_y = 40, button_h = 28;
  GetClientRect(g.window, &area);
  width = area.right;
  height = area.bottom;
  content_bottom = height - 36;
  left_width = width / 4;
  if (left_width < 250) left_width = 250;
  if (left_width > 340) left_width = 340;
  MoveWindow(g.import_label, 8, 12, 62, 20, TRUE);
  MoveWindow(g.import_edit, 72, 8, width - 72 - 8 - 3 * 88, 26, TRUE);
  MoveWindow(g.import_button, width - 8 - 3 * 88 + 4, 8, 80, 26, TRUE);
  MoveWindow(g.open_button, width - 8 - 2 * 88 + 8, 8, 80, 26, TRUE);
  MoveWindow(g.delete_button, width - 8 - 88 + 4, 8, 80, 26, TRUE);
  {
    struct { HWND window; int x, w; } row[] = {
      {g.prev_button, 8, 76}, {g.next_button, 90, 76}, {g.select_button, 172, 84},
      {g.copy_button, 262, 84}, {g.add_button, 352, 80}, {g.update_button, 438, 64},
      {g.remove_button, 508, 80}, {g.jump_button, 594, 64}, {g.font_dec, 664, 64},
      {g.font_inc, 734, 64}, {g.zoom_dec, 804, 64}, {g.zoom_inc, 874, 64},
      {g.cancel_button, 944, 60}
    };
    size_t i;
    for (i = 0; i < sizeof(row) / sizeof(row[0]); i++)
      MoveWindow(row[i].window, row[i].x, button_y, row[i].w, button_h, TRUE);
  }
  MoveWindow(g.shelf_label, 8, content_top, left_width - 16, 18, TRUE);
#ifdef EXR_READER_DESKTOP_METADATA
  MoveWindow(g.shelf_label,8,content_top,left_width-104,18,TRUE);
  MoveWindow(g.metadata_button,left_width-88,content_top-2,80,22,TRUE);
#endif
#ifdef EXR_READER_WINDOWS_ACCOUNT
  /* One small secondary entry beside the shelf title; it stays inside the left pane. */
  MoveWindow(g.shelf_label,8,content_top,left_width-164,18,TRUE);
  MoveWindow(g.account_button,left_width-148,content_top-2,56,22,TRUE);
#endif
  books_height = (content_bottom - content_top - 30) * 45 / 100;
  if (books_height < 120) books_height = 120;
  MoveWindow(g.books, 8, content_top + 20, left_width - 16, books_height, TRUE);
#ifdef EXR_READER_PRODUCT_CATALOG
  MoveWindow(g.shelf_search_label,8,content_top+22,52,20,TRUE);
  MoveWindow(g.shelf_search,64,content_top+20,left_width-134,24,TRUE);
  MoveWindow(g.shelf_refresh,left_width-64,content_top+20,56,24,TRUE);
  MoveWindow(g.books,8,content_top+48,left_width-16,books_height-28,TRUE);
  if(g.product_ready) PostMessageW(g.window,WM_APP+31,0,0);
#endif
  notes_top = content_top + 20 + books_height + 24;
  notes_height = content_bottom - 80 - notes_top;
  if (notes_height < 80) notes_height = 80;
  MoveWindow(g.notes_label, 8, notes_top - 20, left_width - 16, 18, TRUE);
  MoveWindow(g.notes, 8, notes_top, left_width - 16, notes_height, TRUE);
  MoveWindow(g.note_edit_label, 8, content_bottom - 74, left_width - 16, 18, TRUE);
  MoveWindow(g.note_edit, 8, content_bottom - 54, left_width - 16, 52, TRUE);
  MoveWindow(g.page, left_width + 4, content_top, width - left_width - 12, content_bottom - content_top - 4, TRUE);
  MoveWindow(g.page_label, 8, content_bottom + 8, 330, 22, TRUE);
#ifdef EXR_READER_WINDOWS_SEARCH
  MoveWindow(inbook.button, width-128, content_bottom+6, 120, 24, TRUE);
#endif
  MoveWindow(g.status, 346, content_bottom + 8, width - 354, 22, TRUE);
#ifdef EXR_READER_WINDOWS_SEARCH
  MoveWindow(g.status,346,content_bottom+8,width-486,22,TRUE);
#endif
}
static int compute_view(void);
#include "../apps/reader/desktop/windows_accessibility.inc"

static int compute_view(void) {
  RECT area;
  double scale;
  g.view.valid = 0;
  if (!g.frame.valid || !g.frame.bitmap.width || !g.frame.bitmap.height || !g.page) return 0;
  GetClientRect(g.page, &area);
  if (area.right < 16 || area.bottom < 16) return 0;
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

static void selection_bounds(size_t *start, size_t *end) {
  size_t a = g.selection.start, b = g.selection.end;
  if (a > b) { size_t t = a; a = b; b = t; }
  *start = a;
  *end = b;
}

static void paint_selection(HDC dc) {
  size_t start, end;
  if (g.job || g.pending || !g.selection.active || !g.frame.valid) return;
  if (g.session.book_id != g.frame.book_id) return;
  selection_bounds(&start, &end);
  if (start == end) return;
  if (!g.frame.fixed) {
    const exr_glyph *glyphs;
    size_t count = 0, i;
    if (g.session.page != g.frame.page || g.session.part != g.frame.part) return;
    if (g.frame.bounded) { glyphs = g.frame.glyphs; count = g.frame.glyph_count; }
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

static void paint_page_view(HWND window) {
  PAINTSTRUCT paint;
  HDC dc = BeginPaint(window, &paint);
  RECT area;
  GetClientRect(window, &area);
  FillRect(dc, &area, (HBRUSH)GetStockObject(WHITE_BRUSH));
  if (g.frame.valid && compute_view()) {
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
    StretchDIBits(dc, g.view.dx, g.view.dy,
                  (int)(g.frame.bitmap.width * g.view.scale),
                  (int)(g.frame.bitmap.height * g.view.scale),
                  0, 0, (int)g.frame.bitmap.width, (int)g.frame.bitmap.height,
                  g.frame.dib, &info, DIB_RGB_COLORS, SRCCOPY);
    paint_selection(dc);
  } else {
    const wchar_t *hint = L"打开一本书开始阅读\n\n导入 EPUB/PDF/CBZ 后从左侧书架打开";
    RECT text = area;
    SetBkMode(dc, TRANSPARENT);
    SetTextColor(dc, RGB(90, 90, 90));
    DrawTextW(dc, hint, -1, &text, DT_CENTER | DT_VCENTER | DT_WORDBREAK);
  }
  if (GetFocus() == window) {
    RECT focus = area;
    focus.left += 1; focus.top += 1; focus.right -= 1; focus.bottom -= 1;
    DrawFocusRect(dc, &focus);
  }
  EndPaint(window, &paint);
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
  set_statusf(L"已选择 %llu 字节文字 · 可复制引用或添加标注。", (unsigned long long)(end - start));
}

static LRESULT CALLBACK page_procedure(HWND window, UINT message, WPARAM wparam, LPARAM lparam) {
  switch (message) {
    case WM_PAINT:
      paint_page_view(window);
      return 0;
    case WM_SIZE:
      InvalidateRect(window, NULL, TRUE);
      return 0;
    case WM_SETFOCUS:
    case WM_KILLFOCUS:
      InvalidateRect(window, NULL, TRUE);
      return 0;
    case WM_GETOBJECT:
      return host_a11y_page_object(window, wparam, lparam);
    case WM_NCDESTROY:
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
    case WM_LBUTTONDOWN:
      if (g.job || g.pending || !g.frame.valid) return 0;
      SetFocus(window);
      if (g.frame.bounded) { bounded_mouse((short)LOWORD(lparam), (short)HIWORD(lparam), 1, 0); return 0; }
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
        InvalidateRect(window, NULL, FALSE);
      }
      return 0;
    case WM_MOUSEMOVE:
      if (g.frame.bounded && dragging) { bounded_mouse((short)LOWORD(lparam), (short)HIWORD(lparam), 0, 0); return 0; }
      if (g.job || g.pending) return 0;
      if (dragging) {
        size_t offset = point_offset((short)LOWORD(lparam), (short)HIWORD(lparam), 1);
        if (offset != SIZE_MAX && offset != g.selection.end) {
          g.selection.end = offset;
          InvalidateRect(window, NULL, FALSE);
        }
      }
      return 0;
    case WM_LBUTTONUP:
      if (g.frame.bounded && dragging) { bounded_mouse((short)LOWORD(lparam), (short)HIWORD(lparam), 0, 1); return 0; }
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
        InvalidateRect(window, NULL, FALSE);
        host_a11y_page_changed(1);
      }
      return 0;
    case WM_MOUSEWHEEL:
      if (g.job || g.pending) return 0;
      if ((short)HIWORD(wparam) < 0) page_step(1);
      else page_step(-1);
      return 0;
    case WM_KEYDOWN:
      if (g.job || g.pending) return 0;
      switch (wparam) {
        case VK_LEFT: case VK_PRIOR: page_step(-1); return 0;
        case VK_RIGHT: case VK_NEXT: page_step(1); return 0;
        case VK_HOME: page_step(-1000000); return 0;
        case 'A':
          if (GetKeyState(VK_CONTROL) & 0x8000) { select_all_page(); return 0; }
          break;
        case 'C':
          if (GetKeyState(VK_CONTROL) & 0x8000) { copy_quote(); return 0; }
          break;
        case 'O':
          if (GetKeyState(VK_CONTROL) & 0x8000) { host_command(IDC_OPEN_BUTTON); return 0; }
          break;
        case 'I':
          if (GetKeyState(VK_CONTROL) & 0x8000) { host_command(IDC_IMPORT_BUTTON); return 0; }
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
    if (g.session.bounded) swprintf(text, 256, L"章 %llu · 本章第 %llu 页 · EPUB · 字号 %d%%",
             (unsigned long long)(g.frame.part + 1), (unsigned long long)(g.frame.page + 1), g.font_percent);
    else swprintf(text, 256, L"第 %llu 页 · %ls · 字号 %d%%",
             (unsigned long long)(g.frame.page + 1),
             format_name(g.current.format), g.font_percent);
    SetWindowTextW(g.page_label, text);
  }
}

static int save_progress(void) {
  exr_error error = {0};
  exr_status status;
  if (!g.has_current || !g.session.active || !g.frame.valid || g.job || g.pending) return 1;
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
  InvalidateRect(g.page, NULL, FALSE);
  set_statusf(L"已跳转到标注位置（第 %llu 页），并高亮原文。",
              (unsigned long long)(g.frame.page + 1));
}

static void page_step(int direction) {
  size_t target;
  host_job *job;
  if (!g.has_current || !g.frame.valid || g.job || g.pending) return;
  if (!direction) return;
  if (direction <= -1000000) target = 0;
  else if (direction >= 1000000) target = (size_t)-1;
  else target = (direction > 0) ? g.frame.page + (size_t)direction : g.frame.page - (size_t)(-direction);
  if (g.frame.fixed) {
    if (direction <= -1000000) target = 0;
    else if (direction >= 1000000) target = g.frame.page_count ? g.frame.page_count - 1 : 0;
    else if (direction < 0 && g.frame.page == 0) {
      set_status(L"已经是第一页。");
      return;
    } else if (target >= g.frame.page_count) {
      set_status(L"已到最后一页；当前页未改变。");
      return;
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
  job->direction = direction > 0 ? 1 : -1;
  if (g.session.bounded && direction < 0 && direction > -1000000 && g.frame.page == 0) job->target_page = SIZE_MAX;
  job_submit(job);
}

static void change_font(int delta) {
  int next;
  host_job *job;
  exr_anchor anchor = {0};
  exr_error error = {0};
  if (!g.has_current || !g.frame.valid) { set_status(L"请先打开一本书。"); return; }
  if (g.frame.fixed) { set_status(L"当前是固定页书籍，请使用“缩放+”或“缩放-”。"); return; }
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

static void change_zoom(int delta) {
  int next;
  host_job *job;
  if (!g.has_current || !g.frame.valid) { set_status(L"请先打开一本书。"); return; }
  if (!g.frame.fixed) { set_status(L"当前是重排书籍，请使用“字号+”或“字号-”。"); return; }
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
    size_t size = 0;
    bytes = g.frame.utf8; size = g.frame.text_bytes;
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
  InvalidateRect(g.page, NULL, FALSE);
  host_a11y_page_changed(1);
}

static void copy_quote(void) {
  char *text = NULL;
  size_t size = 0;
  if (g.selection.active) size = selection_bytes(&text);
  if (size && text) {
    if (clipboard_set(text, size)) set_statusf(L"已复制引用（%llu 字节）到剪贴板。", (unsigned long long)size);
    else set_status(L"无法访问剪贴板。");
    free(text);
    return;
  }
  {
    int index = notes_selected();
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
      if (!quote) quote = ""; if (!comment) comment = "";
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

static void add_note(void) {
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

static void update_note(void) {
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

static void delete_note(void) {
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

static void jump_selected_note(void) {
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
        InvalidateRect(g.page, NULL, FALSE);
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
  LRESULT index;
  host_job *job;
  if (!g.books) return;
  index = SendMessageW(g.books, LB_GETCURSEL, 0, 0);
  if (index == LB_ERR || (size_t)index >= g.shelf_count) {
    set_status(L"请先在书架中选择一本书。");
    return;
  }
  if (!g.job && !g.pending && !save_progress()) return;
  job = job_new(JOB_OPEN);
  if (!job) { set_status(L"内存不足，无法打开书籍。"); return; }
  job->book_id = g.shelf[index].id;
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
    settings_save();
    update_page_label();
    InvalidateRect(g.page, NULL, TRUE);
  }
  if (reload_shelf() != EXR_OK) return;
  host_update_controls();
  set_status(L"已删除书籍及其标注。");
}
static void delete_selected_book(void) {
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
  job = job_new(JOB_IMPORT);
  if (!job) { set_status(L"内存不足，无法导入。"); return; }
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
  int has = g.has_current && g.frame.valid;
  EnableWindow(g.import_button, !busy);
  EnableWindow(g.open_button, g.shelf_count > 0);
  EnableWindow(g.delete_button, !busy && g.shelf_count > 0);
  EnableWindow(g.prev_button, !busy && has && (g.frame.page > 0 || (g.session.bounded && g.frame.part > 0)));
  EnableWindow(g.next_button, !busy && has);
  EnableWindow(g.select_button, !busy && has);
  EnableWindow(g.copy_button, !busy && has);
  EnableWindow(g.add_button, !busy && has);
  EnableWindow(g.update_button, !busy && has);
  EnableWindow(g.remove_button, !busy && has);
  EnableWindow(g.jump_button, !busy && has);
  EnableWindow(g.font_dec, !busy && has && !g.frame.fixed);
  EnableWindow(g.font_inc, !busy && has && !g.frame.fixed);
  EnableWindow(g.zoom_dec, !busy && has && g.frame.fixed);
  EnableWindow(g.zoom_inc, !busy && has && g.frame.fixed);
  EnableWindow(g.cancel_button, busy || g.job != NULL);
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
}

static void handle_job_complete(host_job *job) {
#ifdef EXR_READER_WINDOWS_SEARCH
  if(job->kind==JOB_SEARCH_BATCH || job->kind==JOB_SEARCH_OPEN) { winsearch_accept(job);return; }
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
  if (job->kind == JOB_SAVE) {
    g.progress_failed = job->status != EXR_OK;
    if (!g.progress_failed) g.saved_generation = job->generation;
    else {
      wchar_t message[512]; describe_error(message, 512, L"保存进度失败，请重试", job->status, &job->error); set_status(message);
      if (g.pending) { job_release(g.pending); g.pending = NULL; }
      if (g.closing) { g.closing = 0; KillTimer(g.window, 2); if (g.drive_mode) SetTimer(g.window, 1, 30, NULL); }
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
      InvalidateRect(g.page, NULL, FALSE);
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
  if (job->status == EXR_OK && job_cancel_flag(job) && job->kind == JOB_IMPORT) {
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
  if (job->status == EXR_OK && (job_cancel_flag(job) || g.closing) &&
      (job->kind == JOB_OPEN || job->kind == JOB_GO || job->kind == JOB_LAYOUT)) job->status = EXR_CANCELLED;
  if (job->status != EXR_OK) g.pending_selection = 0;
  if (job->status == EXR_OK) {
    if (job->kind == JOB_OPEN) {
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
          g.active_book_id = g.current.id;
          frame_move(&g.frame, &job->frame);
          memset(&g.selection, 0, sizeof(g.selection));
          g.pending_selection = 0;
          g.session.page = g.frame.page;
          update_page_label();
          settings_save();
          if (reload_notes() != EXR_OK) { save_progress(); return; }
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
        if (job->candidate_pager) {
          exr_pager_free(g.session.pager); g.session.pager = job->candidate_pager; job->candidate_pager = NULL;
          g.session.config = job->candidate_config;
        }
        frame_move(&g.frame, &job->frame);
        g.session.part = g.frame.part;
        g.session.hold_progress = g.frame.hold_progress;
        memset(&g.selection, 0, sizeof(g.selection));
        g.session.page = g.frame.page;
        if (job->kind == JOB_LAYOUT && job->font_percent > 0) g.font_percent = job->font_percent;
        if (job->zoom_percent > 0) g.zoom_percent = job->zoom_percent;
        update_page_label();
        settings_save();
        if (!save_progress()) { g.pending_selection = 0; return; }
        if (job->message[0]) set_status(job->message);
        else set_statusf(L"第 %llu 页。", (unsigned long long)(g.frame.page + 1));
        if (job->resolved_selection) { g.pending_start = job->note_start; g.pending_end = job->note_end; }
        apply_pending_selection();
      } else {
        set_status(L"翻页失败：任务没有生成画面。");
      }
    } else if (job->kind == JOB_IMPORT) {
      if (reload_shelf() != EXR_OK) return;
      if (job->created && !import_title_fallback(job->path, job->imported_id)) return;
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
    if (job->message[0]) {
      set_status(job->message);
    } else {
      describe_error(message, 768,
                     job->kind == JOB_IMPORT ? L"导入失败" :
                     job->kind == JOB_OPEN ? L"打开书籍失败" : L"翻页或重排失败",
                     job->status, &job->error);
      set_status(message);
    }
  }
}

static void host_command(int id) {
#ifdef EXR_READER_WINDOWS_SEARCH
  if(id==IDC_INBOOK) { winsearch_show();return; }
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
    case IDC_IMPORT_BUTTON: {
      wchar_t path[HOST_PATH];
      path[0] = 0;
      if (g.import_edit) GetWindowTextW(g.import_edit, path, HOST_PATH);
      import_path(path, 1);
      break;
    }
    case IDC_OPEN_BUTTON: open_selected_book(); break;
    case IDC_DELETE_BUTTON: delete_selected_book(); break;
    case IDC_PREV: page_step(-1); break;
    case IDC_NEXT: page_step(1); break;
    case IDC_SELECT_ALL: select_all_page(); break;
    case IDC_COPY_QUOTE: copy_quote(); break;
    case IDC_ADD_NOTE: add_note(); break;
    case IDC_UPDATE_NOTE: update_note(); break;
    case IDC_DELETE_NOTE: delete_note(); break;
    case IDC_JUMP_NOTE: jump_selected_note(); break;
    case IDC_FONT_DEC: change_font(-HOST_FONT_STEP); break;
    case IDC_FONT_INC: change_font(HOST_FONT_STEP); break;
    case IDC_ZOOM_DEC: change_zoom(-HOST_ZOOM_STEP); break;
    case IDC_ZOOM_INC: change_zoom(HOST_ZOOM_STEP); break;
    case IDC_CANCEL: job_cancel_button(); break;
  }
}

/* ------------------------------------------------------------------ */
/* UI-level acceptance driver                                          */
/* ------------------------------------------------------------------ */

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
  if (!ok) {
    x = area.left; y = area.top;
    BitBlt(memory, 0, 0, width, height, screen, x, y, SRCCOPY);
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

static int drive_execute(void) {
  const char *action = drive_args[0];
  char detail[1024];
  int launches = 0;
  memset(detail, 0, sizeof(detail));
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
    SendMessageW(g.cancel_button, BM_CLICK, 0, 0);
    drive_step_finish(1, g.job ? "cancel requested" : "no task to cancel");
    return 0;
  }
  if (!strcmp(action, "open")) {
    if (!shelf_click(drive_args[1])) { drive_step_finish(0, "book not found"); return 0; }
    SendMessageW(g.open_button, BM_CLICK, 0, 0);
    drive_expect_idle = 1;
    return 1;
  }
  if (!strcmp(action, "import_async")) {
    wchar_t *wide = host_wide(drive_args[1], strlen(drive_args[1]));
    if (!wide) { drive_step_finish(0, "invalid path"); return 0; }
    SetWindowTextW(g.import_edit, wide);
    free(wide);
    SendMessageW(g.import_button, BM_CLICK, 0, 0);
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
    SetWindowTextW(g.import_edit, wide);
    free(wide);
    SendMessageW(g.import_button, BM_CLICK, 0, 0);
    launches = 1;
  } else if (!strcmp(action, "shelf")) {
    if (!shelf_click(drive_args[1])) { drive_step_finish(0, "book not found"); return 0; }
    drive_step_finish(1, "book selected");
    return 0;
  } else if (!strcmp(action, "delete_book")) {
    wchar_t *needle;
    int gone;
    if (!shelf_click(drive_args[1])) { drive_step_finish(0, "book not found"); return 0; }
    SendMessageW(g.delete_button, BM_CLICK, 0, 0);
#ifdef EXR_READER_PRODUCT_CATALOG
    if(g.job || g.pending) { drive_expect_idle=1;return 1; }
#endif
    needle = host_wide(drive_args[1], strlen(drive_args[1]));
    gone = needle && shelf_index_for_title(needle) < 0;
    free(needle);
    drive_step_finish(gone, gone ? "book removed" : "book still present");
    return 0;
  } else if (!strcmp(action, "next")) {
    SendMessageW(g.next_button, BM_CLICK, 0, 0);
    launches = 1;
  } else if (!strcmp(action, "prev")) {
    SendMessageW(g.prev_button, BM_CLICK, 0, 0);
    launches = 1;
  } else if (!strcmp(action, "chapter_end")) {
    page_step(1000000); launches = 1;
  } else if (!strcmp(action, "chapter_home")) {
    page_step(-1000000); launches = 1;
  } else if (!strcmp(action, "font_inc")) {
    SendMessageW(g.font_inc, BM_CLICK, 0, 0);
    launches = 1;
  } else if (!strcmp(action, "font_dec")) {
    SendMessageW(g.font_dec, BM_CLICK, 0, 0);
    launches = 1;
  } else if (!strcmp(action, "zoom_inc")) {
    SendMessageW(g.zoom_inc, BM_CLICK, 0, 0);
    launches = 1;
  } else if (!strcmp(action, "zoom_dec")) {
    SendMessageW(g.zoom_dec, BM_CLICK, 0, 0);
    launches = 1;
  } else if (!strcmp(action, "select_all")) {
    SendMessageW(g.select_button, BM_CLICK, 0, 0);
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
    InvalidateRect(g.page, NULL, FALSE);
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
    SendMessageW(g.add_button, BM_CLICK, 0, 0);
    drive_step_finish(g.status_text[0] != 0, "add dispatched");
    return 0;
  } else if (!strcmp(action, "update_note")) {
    SendMessageW(g.update_button, BM_CLICK, 0, 0);
    drive_step_finish(1, "update dispatched");
    return 0;
  } else if (!strcmp(action, "delete_note")) {
    SendMessageW(g.remove_button, BM_CLICK, 0, 0);
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
    SendMessageW(g.jump_button, BM_CLICK, 0, 0);
    launches = 1;
  } else if (!strcmp(action, "copy")) {
    SendMessageW(g.copy_button, BM_CLICK, 0, 0);
    drive_step_finish(1, "copy dispatched");
    return 0;
  } else if (!strcmp(action, "check")) {
    const char *what = drive_args[1];
    int pass = 0;
    char number[64];
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
  strncpy(drive_action, drive_args[0], sizeof(drive_action) - 1);
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
      if (g.job || g.pending) {
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
#ifdef EXR_HOST_WORKER_REVIEW
  if (message == WM_APP + 30) return review_message(window, wparam, lparam);
#endif
#ifdef EXR_READER_PRODUCT_CATALOG
  if(message==WM_APP+31) { product_shelf_edges();return 0; }
#endif
  switch (message) {
    case WM_CREATE:
      g.window = window;
      create_controls(window);
      layout_controls();
      return 0;
    case WM_SIZE: {
      RECT bounds;
      GetWindowRect(window, &bounds);
      g.window_width = bounds.right - bounds.left;
      g.window_height = bounds.bottom - bounds.top;
      layout_controls();
      InvalidateRect(g.page, NULL, TRUE);
      return 0;
    }
    case WM_GETMINMAXINFO: {
      MINMAXINFO *limits = (MINMAXINFO *)lparam;
      limits->ptMinTrackSize.x = 1060;
      limits->ptMinTrackSize.y = 660;
      return 0;
    }
    case WM_COMMAND: {
      int id = LOWORD(wparam);
      int code = HIWORD(wparam);
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
    case WM_HOST_PROGRESS:
      if (g.job && g.job->kind == JOB_IMPORT && !job_cancel_flag(g.job))
        set_statusf(L"正在导入… %ld%%（读取文件，可点取消）", (long)g.job->progress);
      return 0;
    case WM_HOST_COMPLETE: {
      host_job *job = (host_job *)lparam;
      if (!job || job != g.job) return 0;
      /* The completion is posted after all SDK work; join only the final ref
         release before the UI accepts/frees the job's owned candidates. */
      WaitForSingleObject(job->thread, INFINITE);
      g.job = NULL;
      handle_job_complete(job);
      job_release(job);
      InvalidateRect(g.page, NULL, FALSE);
      if (!g.job && g.pending) {
        host_job *next = g.pending;
        g.pending = NULL;
        job_start(next);
      } else {
        host_update_controls();
      }
#ifdef EXR_READER_PRODUCT_CATALOG
      product_shelf_dispatch();host_update_controls();
      if(!g.job && !g.pending) PostMessageW(window,WM_APP+31,0,0);
#endif
#ifdef EXR_READER_WINDOWS_SEARCH
      winsearch_controls();
#endif
      if (g.closing) finish_close(window);
      return 0;
    }
    case WM_TIMER:
#ifdef EXR_READER_PRODUCT_CATALOG
      if(wparam==3) { KillTimer(window,3);product_shelf_dispatch();return 0; }
      if(wparam==4) { KillTimer(window,4);if(!g.closing) settings_save();return 0; }
#endif
#ifdef EXR_READER_WINDOWS_ACCOUNT
      if(wparam==5) { acct_tick();return 0; }
#endif
      if (wparam == 2 && g.closing && g.job) { ExitProcess(1); return 0; }
      if (wparam == 1 && g.drive_mode) drive_tick();
      return 0;
    case WM_CLOSE:
      if (g.closing) return 0;
#ifdef EXR_READER_WINDOWS_SEARCH
      winsearch_close();
#endif
#ifdef EXR_READER_PRODUCT_CATALOG
      product_shelf_remember();KillTimer(window,3);KillTimer(window,4);
#endif
      g.closing = 1;
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
      settings_save();
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
  type.hbrBackground = (HBRUSH)GetStockObject(WHITE_BRUSH);
  type.lpszClassName = L"EXReaderHost";
  if (!RegisterClassW(&type)) return 0;
  memset(&type, 0, sizeof(type));
  type.style = CS_HREDRAW | CS_VREDRAW;
  type.lpfnWndProc = page_procedure;
  type.hInstance = instance;
  type.hCursor = LoadCursor(NULL, IDC_IBEAM);
  type.hbrBackground = (HBRUSH)GetStockObject(WHITE_BRUSH);
  type.lpszClassName = L"EXReaderPage";
  if (!RegisterClassW(&type)) return 0;
  return 1;
}

static int message_loop(void) {
  MSG message;
  while (GetMessageW(&message, NULL, 0, 0) > 0) {
#ifdef EXR_READER_WINDOWS_SEARCH
    if(winsearch_translate(&message)) continue;
#endif
#ifdef EXR_READER_DESKTOP_METADATA
    if(g.metadata_dialog && IsDialogMessageW(g.metadata_dialog,&message)) continue;
#endif
#ifdef EXR_READER_WINDOWS_ACCOUNT
    if(acct.dialog && IsDialogMessageW(acct.dialog,&message)) continue;
    if(message.message==WM_KEYDOWN && message.wParam=='A' && (GetKeyState(VK_CONTROL)&0x8000) && (GetKeyState(VK_SHIFT)&0x8000) &&
       !acct.dialog && g.window && IsWindowEnabled(g.window)) { acct_open_dialog();continue; }
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
#ifdef EXR_READER_PRODUCT_CATALOG
  free(g.shelf_query);g.shelf_query=NULL;
#endif
  if (g.library) exr_library_close(g.library);
  g.library = NULL;
  exr_font_free(g.font);
  g.font = NULL;
  if (g.drive_log) fclose(g.drive_log);
  g.drive_log = NULL;
  if (drive_file) fclose(drive_file);
  drive_file = NULL;
  DeleteCriticalSection(&g.library_lock);
#ifdef EXR_READER_PRODUCT_CATALOG
  if(g.product_lock && g.product_lock!=INVALID_HANDLE_VALUE) CloseHandle(g.product_lock);
  if(g.product_profile_lock && g.product_profile_lock!=INVALID_HANDLE_VALUE) CloseHandle(g.product_profile_lock);
  g.product_lock=NULL;
  g.product_profile_lock=NULL;
#endif
}

int WINAPI WinMain(HINSTANCE instance, HINSTANCE previous, LPSTR command, int show) {
  int argc = 0;
  wchar_t **argv = CommandLineToArgvW(GetCommandLineW(), &argc);
  wchar_t font_path[HOST_PATH] = L"";
  wchar_t data_dir[HOST_PATH] = L"";
  wchar_t book_path[HOST_PATH] = L"";
  wchar_t library_override[HOST_PATH] = L"";
  wchar_t script[HOST_PATH] = L"";
  wchar_t evidence[HOST_PATH] = L"";
  wchar_t phase[32] = L"0";
  int i;
  INT_PTR result = 1;
  (void)previous;
  (void)command;
  if (!argv) return 2;
  if (argc > 1 && !wcscmp(argv[1], L"--self-test")) {
    result = selftest(argv, argc);
    LocalFree(argv);
    return (int)result;
  }
  for (i = 1; i < argc; i++) {
    const wchar_t *value = (i + 1 < argc) ? argv[i + 1] : L"";
    if (!wcscmp(argv[i], L"--drive")) { copy_wstring(script, HOST_PATH, value); i++; }
    else if (!wcscmp(argv[i], L"--evidence")) { copy_wstring(evidence, HOST_PATH, value); i++; }
    else if (!wcscmp(argv[i], L"--data")) { copy_wstring(data_dir, HOST_PATH, value); i++; }
    else if (!wcscmp(argv[i], L"--library")) { copy_wstring(library_override, HOST_PATH, value); i++; }
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
  if (!font_path[0]) {
    wchar_t module_dir[HOST_PATH];
    module_directory(module_dir, HOST_PATH);
    path_join(font_path, HOST_PATH, module_dir, L"Reader.otf");
  }
  copy_wstring(g.font_path, HOST_PATH, font_path);
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
    char *path = host_utf8(font_path);
    exr_status status = path ? exr_font_open(path, &g.font, &error) : EXR_MEMORY;
    free(path);
    if (status != EXR_OK) {
      wchar_t message[512];
      describe_error(message, 512, L"无法打开 Reader.otf", status, &error);
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
  g.window = CreateWindowW(L"EXReaderHost", L"EXReader", WS_OVERLAPPEDWINDOW,
                           CW_USEDEFAULT, CW_USEDEFAULT, g.window_width, g.window_height,
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
  ShowWindow(g.window, show ? show : SW_SHOWNORMAL);
  UpdateWindow(g.window);
  reload_shelf();
#ifdef EXR_READER_PRODUCT_CATALOG
  {
    host_job *repair=job_new(JOB_PRODUCT_REPAIR);
    if(repair) job_start(repair);
    else { g.product_pending=1;set_status(L"无法启动书目修复；原书仍保留，可重启后重试。"); }
  }
#endif
  if (script[0]) drive_start();
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
    set_status(L"书架为空：输入文件路径后点击“导入”。");
  }
  host_update_controls();
  result = message_loop();
  host_cleanup();
  LocalFree(argv);
  return (int)result;
}
