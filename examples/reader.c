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

enum {
  IDC_IMPORT_LABEL = 100, IDC_IMPORT_EDIT, IDC_IMPORT_BUTTON, IDC_OPEN_BUTTON,
  IDC_DELETE_BUTTON, IDC_PREV, IDC_NEXT, IDC_SELECT_ALL, IDC_COPY_QUOTE,
  IDC_ADD_NOTE, IDC_UPDATE_NOTE, IDC_DELETE_NOTE, IDC_JUMP_NOTE,
  IDC_FONT_DEC, IDC_FONT_INC, IDC_ZOOM_DEC, IDC_ZOOM_INC, IDC_CANCEL,
  IDC_SHELF_LABEL, IDC_BOOKS, IDC_NOTES_LABEL, IDC_NOTES, IDC_NOTE_EDIT,
  IDC_PAGE, IDC_PAGE_LABEL, IDC_STATUS
};

#define WM_HOST_COMPLETE (WM_APP + 1)
#define WM_HOST_PROGRESS (WM_APP + 2)

typedef struct {
  exr_bitmap bitmap;
  uint32_t *dib;
  wchar_t *text;
  size_t text_bytes;
  size_t page, range_start, range_end;
  size_t page_count;
  int valid;
  int fixed;
  int64_t book_id;
  wchar_t title[256];
  double render_scale;
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
  exr_pager *pager;
  exr_fixed_document *fixed_document;
  exr_layout_config config;
  exr_page_geometry geometry;
  double fixed_scale;
  size_t page;
  size_t page_count;
  const exr_layout *layout;
  exr_fixed_text *fixed_text;
  size_t fixed_text_page;
} host_session;

typedef struct host_job host_job;

typedef struct {
  HWND window, page, books, notes, note_edit, import_edit, status, page_label;
  HWND import_label, import_button, open_button, delete_button;
  HWND prev_button, next_button, select_button, copy_button;
  HWND add_button, update_button, remove_button, jump_button;
  HWND font_dec, font_inc, zoom_dec, zoom_inc, cancel_button;
  HWND shelf_label, notes_label;
  exr_library *library;
  exr_font *font;
  wchar_t font_path[HOST_PATH];
  wchar_t data_dir[HOST_PATH];
  wchar_t library_path[HOST_PATH];
  wchar_t settings_path[HOST_PATH];
  wchar_t evidence_dir[HOST_PATH];
  wchar_t script_path[HOST_PATH];
  exr_book *shelf;
  size_t shelf_count;
  exr_note *reflow_notes;
  size_t reflow_note_count;
  exr_fixed_note *fixed_notes;
  size_t fixed_note_count;
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
  int64_t pending_book;
} host_state;

static host_state g;

typedef exr_status (*host_progress_fn)(void *context, unsigned percent);

/* ------------------------------------------------------------------ */
/* Small helpers                                                       */
/* ------------------------------------------------------------------ */

static void set_status(const wchar_t *text) {
  if (!text) text = L"";
  wcsncpy(g.status_text, text, 767);
  g.status_text[767] = 0;
  if (g.status) SetWindowTextW(g.status, g.status_text);
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
  exr_bitmap_free(&frame->bitmap);
  free(frame->dib);
  free(frame->text);
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

static void session_clear(host_session *session) {
  if (session->fixed_text) exr_fixed_text_free(session->fixed_text);
  if (session->fixed_document) exr_fixed_free(session->fixed_document);
  if (session->pager) exr_pager_free(session->pager);
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
}

static void settings_save(void) {
  wchar_t number[64];
  if (!g.settings_path[0]) return;
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
  if (g.shelf) exr_books_free(g.shelf, g.shelf_count);
  g.shelf = NULL;
  g.shelf_count = 0;
}

static void notes_clear(void) {
  if (g.reflow_notes) exr_notes_free(g.reflow_notes, g.reflow_note_count);
  if (g.fixed_notes) exr_fixed_notes_free(g.fixed_notes, g.fixed_note_count);
  g.reflow_notes = NULL;
  g.reflow_note_count = 0;
  g.fixed_notes = NULL;
  g.fixed_note_count = 0;
}

static size_t current_note_count(void) {
  return g.session.fixed ? g.fixed_note_count : g.reflow_note_count;
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
  exr_book *books = NULL;
  size_t count = 0;
  exr_error error = {0};
  exr_status status;
  size_t i;
  EnterCriticalSection(&g.library_lock);
  status = exr_library_books(g.library, "", &books, &count, &error);
  LeaveCriticalSection(&g.library_lock);
  if (status != EXR_OK) {
    wchar_t message[512];
    describe_error(message, 512, L"读取书架失败", status, &error);
    set_status(message);
    return status;
  }
  shelf_clear();
  g.shelf = books;
  g.shelf_count = count;
  if (g.books) {
    SendMessageW(g.books, LB_RESETCONTENT, 0, 0);
    for (i = 0; i < count; i++) {
      wchar_t line[512];
      shelf_display(&books[i], line, 512);
      SendMessageW(g.books, LB_ADDSTRING, 0, (LPARAM)line);
    }
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
  notes_clear();
  if (g.notes) SendMessageW(g.notes, LB_RESETCONTENT, 0, 0);
  if (!g.has_current || !g.session.active) return EXR_OK;
  EnterCriticalSection(&g.library_lock);
  if (g.session.fixed)
    status = exr_library_fixed_notes(g.library, g.current.id, &g.fixed_notes, &g.fixed_note_count, &error);
  else
    status = exr_library_notes(g.library, g.current.id, &g.reflow_notes, &g.reflow_note_count, &error);
  LeaveCriticalSection(&g.library_lock);
  if (status != EXR_OK) {
    wchar_t message[512];
    describe_error(message, 512, L"读取标注失败", status, &error);
    set_status(message);
    return status;
  }
  if (g.notes) {
    size_t i;
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

static void note_comment_read(char *out, size_t capacity) {
  wchar_t wide[65536];
  int length;
  char *utf8;
  out[0] = 0;
  if (!g.note_edit) return;
  length = GetWindowTextW(g.note_edit, wide, 65535);
  if (length <= 0) return;
  wide[length] = 0;
  utf8 = host_utf8(wide);
  if (!utf8) return;
  strncpy(out, utf8, capacity - 1);
  out[capacity - 1] = 0;
  free(utf8);
}

static void note_comment_write(const char *utf8) {
  wchar_t *wide = utf8 ? host_wide(utf8, strlen(utf8)) : NULL;
  if (g.note_edit) SetWindowTextW(g.note_edit, wide ? wide : L"");
  free(wide);
}

/* ------------------------------------------------------------------ */
/* Jobs: one SDK-owning worker at a time                               */
/* ------------------------------------------------------------------ */

enum { JOB_NONE = 0, JOB_OPEN, JOB_GO, JOB_LAYOUT, JOB_IMPORT };

struct host_job {
  LONG refs;
  volatile LONG cancel;
  int kind;
  int64_t book_id;
  wchar_t path[HOST_PATH];
  size_t target_page;
  size_t target_offset;
  int use_offset;
  int direction;
  int font_percent;
  int zoom_percent;
  exr_anchor anchor;
  int has_anchor;
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
};

static int job_cancel_flag(host_job *job) {
  return job && InterlockedCompareExchange((volatile LONG *)&job->cancel, 0, 0) != 0;
}

static int job_cancel_check(void *context) {
  return job_cancel_flag((host_job *)context);
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

static void job_free(host_job *job) {
  if (!job) return;
  if (job->thread) CloseHandle(job->thread);
  frame_clear(&job->frame);
  if (job->has_anchor) exr_anchor_free(&job->anchor);
  free(job);
}

static void job_release(host_job *job) {
  if (!job) return;
  if (InterlockedDecrement(&job->refs) == 0) job_free(job);
}

static void host_update_controls(void);
static unsigned __stdcall job_thread(void *context);
static exr_status job_run(host_job *job);

static void job_start(host_job *job) {
  uintptr_t handle;
  unsigned thread_id = 0;
  g.job = job;
  memset(&g.selection, 0, sizeof(g.selection));
  if (g.page) InvalidateRect(g.page, NULL, TRUE);
  InterlockedIncrement(&job->refs);
  handle = _beginthreadex(NULL, 0, job_thread, job, 0, &thread_id);
  if (!handle) {
    InterlockedDecrement(&job->refs);
    g.job = NULL;
    job->status = EXR_MEMORY;
    strcpy(job->error.message, "Cannot create host worker thread");
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
    job_supersede();
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
  session->config = exr_layout_config_defaults();
  session->config.page.width = 720;
  session->config.page.height = 1040;
  session->config.page.margin = 36;
  session->config.page.font_size = (float)font_percent / 100.0f;
  session->config.page.line_height = 10;
  session->config.page.paragraph_spacing = 12;
}

static exr_status render_reflow(host_session *session, size_t page, host_frame *out,
                                const exr_control *control, exr_error *error) {
  const exr_layout *layout = NULL;
  const exr_page *info;
  const char *text;
  size_t count = 0, size = 0;
  exr_status status;
  memset(out, 0, sizeof(*out));
  status = exr_pager_get(session->pager, page, &layout, error);
  if (status != EXR_OK) return status;
  info = exr_layout_pages(layout, &count);
  if (!info || count < 1) return EXR_FORMAT;
  text = exr_document_text(session->document, &size);
  if (!text || info->start > info->end || info->end > size) return EXR_FORMAT;
  status = exr_render_page_ex(layout, exr_layout_font(layout), 0, 4, control, &out->bitmap, error);
  if (status != EXR_OK) return status;
  out->text = host_wide(text + info->start, info->end - info->start);
  if (!out->text) {
    exr_bitmap_free(&out->bitmap);
    return EXR_MEMORY;
  }
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
  session->layout = layout;
  session->page = page;
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
  if (session->fixed_text) exr_fixed_text_free(session->fixed_text);
  session->fixed_text = text;
  session->fixed_text_page = page;
  session->geometry = pages[page].geometry;
  session->fixed_scale = scale;
  session->page = page;
  session->page_count = count;
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
  status = exr_pager_get(session->pager, 0, &layout, error);
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
    status = exr_pager_get(session->pager, hi, &layout, error);
    if (status != EXR_OK) {
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
    status = exr_pager_get(session->pager, mid, &layout, error);
    if (status == EXR_OK && exr_layout_pages(layout, &count) != NULL && count > 0 &&
        exr_layout_pages(layout, &count)[0].start <= offset) {
      lo = mid;
    } else {
      hi = mid;
    }
    memset(error, 0, sizeof(*error));
  }
  status = exr_pager_get(session->pager, lo, &layout, error);
  if (status != EXR_OK) return status;
  info = exr_layout_pages(layout, &count);
  if (!info || count < 1) return EXR_FORMAT;
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
    memset(&error, 0, sizeof(error));
    if (note && note_capacity) copy_wstring(note, note_capacity, L"无法读取上次进度，从第一页开始。");
    *page = 0;
    return EXR_OK;
  }
  offset = anchor.start;
  if (state == EXR_ANCHOR_FOUND) {
    status = exr_anchor_resolve_ex(session->document, &anchor, control, &match, &error);
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

static exr_status job_open(host_job *job) {
  host_session session;
  exr_error error = {0};
  exr_status status;
  int index = shelf_index(job->book_id);
  exr_book book;
  memset(&session, 0, sizeof(session));
  memset(&book, 0, sizeof(book));
  if (index < 0) {
    copy_wstring(job->message, 512, L"该书已不在书架中。");
    return EXR_ARGUMENT;
  }
  if (!book_copy(&book, &g.shelf[index])) return EXR_MEMORY;
  session.book_id = book.id;
  session.fixed = is_fixed_format(book.format);
  if (session.fixed) {
    exr_fixed_open_options options = {0};
    const exr_fixed_page *pages;
    size_t count = 0, target;
    options.struct_size = sizeof(options);
    options.fallback_font = g.font;
    options.control.cancelled = job_cancel_check;
    options.control.context = job;
    EnterCriticalSection(&g.library_lock);
    status = exr_library_fixed(g.library, book.id, &options, &session.fixed_document, &error);
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
    session_configure(&session, job->font_percent > 0 ? job->font_percent : g.font_percent);
    session.config.control.cancelled = job_cancel_check;
    session.config.control.context = job;
    EnterCriticalSection(&g.library_lock);
    status = exr_library_document(g.library, book.id, &session.document, &error);
    LeaveCriticalSection(&g.library_lock);
    if (status == EXR_OK)
      status = exr_pager_create(session.document, g.font, &session.config, &session.pager, &error);
    if (status == EXR_OK) status = exr_pager_set_cache(session.pager, 2, 0, &error);
    if (status == EXR_OK) status = exr_pager_set_checkpoints(session.pager, 8, 4 * 1024 * 1024, 8, &error);
    if (status == EXR_OK) {
      size_t page = 0;
      exr_control control = {job_cancel_check, NULL, job};
      status = reflow_restore(&session, &control, &page, job->message, 512);
      if (status == EXR_OK) status = render_reflow(&session, page, &job->frame, &control, &error);
    }
  }
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
    session_clear(&g.session);
    g.session = session;
    {
      const char *title = book.title ? book.title : "Untitled";
      wchar_t *wide = host_wide(title, strlen(title));
      copy_wstring(job->frame.title, 256, wide ? wide : L"Untitled");
      free(wide);
    }
  } else {
    session_clear(&session);
  }
  book_clear(&book);
  return status;
}

static exr_status job_go(host_job *job) {
  exr_error error = {0};
  exr_status status;
  if (!g.session.active) return EXR_ARGUMENT;
  if (job->book_id && job->book_id != g.session.book_id) return EXR_CANCELLED;
  if (g.session.fixed) {
    size_t count = g.session.page_count;
    if (!count) return EXR_FORMAT;
    if (job->target_page >= count) return EXR_ARGUMENT;
    status = render_fixed(&g.session, job->target_page,
                          job->zoom_percent > 0 ? job->zoom_percent : g.zoom_percent,
                          &job->frame, NULL, &error);
  } else {
    exr_control control = {job_cancel_check, NULL, job};
    size_t page = job->target_page;
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
  if (!g.session.active || g.session.fixed || !g.session.document) return EXR_ARGUMENT;
  if (job->book_id && job->book_id != g.session.book_id) return EXR_CANCELLED;
  config = g.session.config;
  config.page.font_size = (float)job->font_percent / 100.0f;
  config.control.cancelled = job_cancel_check;
  config.control.context = job;
  status = exr_pager_create(g.session.document, g.font, &config, &pager, &error);
  if (status == EXR_OK) status = exr_pager_set_cache(pager, 2, 0, &error);
  if (status == EXR_OK) status = exr_pager_set_checkpoints(pager, 8, 4 * 1024 * 1024, 8, &error);
  if (status == EXR_OK && job->has_anchor) {
    exr_anchor_match match;
    exr_status resolved = exr_anchor_resolve_ex(g.session.document, &job->anchor, &control, &match, &error);
    if (resolved == EXR_OK && match.state == EXR_ANCHOR_FOUND)
      offset = match.start;
    else if (resolved == EXR_OK && match.state == EXR_ANCHOR_AMBIGUOUS)
      copy_wstring(job->message, 512, L"字号变化时锚点存在歧义，已按保存的文本偏移重排。");
    else
      copy_wstring(job->message, 512, L"字号变化时锚点未匹配，已按保存的文本偏移重排。");
    memset(&error, 0, sizeof(error));
  }
  if (status == EXR_OK) {
    /* Search and render with the new pager before discarding the old one. */
    exr_pager *previous = g.session.pager;
    exr_layout_config previous_config = g.session.config;
    g.session.pager = pager;
    pager = NULL;
    g.session.config = config;
    status = page_for_offset(&g.session, offset, &control, &page, NULL, NULL, &error);
    if (status == EXR_OK)
      status = render_reflow(&g.session, page, &job->frame, &control, &error);
    if (status == EXR_OK) {
      exr_pager_free(previous);
      job->have_frame = 1;
      job->applied_page = page;
      job->session_swapped = 0;
    } else {
      exr_pager *failed = g.session.pager;
      g.session.pager = previous;
      g.session.config = previous_config;
      if (failed) exr_pager_free(failed);
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
  status = read_import_file(job, &data, &size, &error);
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
  EnterCriticalSection(&g.library_lock);
  status = exr_library_import_unique(g.library, format, data, size, NULL, &id, &created, &error);
  LeaveCriticalSection(&g.library_lock);
  free(path);
  free(data);
  if (status == EXR_OK && job_cancel_flag(job)) {
    if (created && id > 0) {
      exr_error discard = {0};
      EnterCriticalSection(&g.library_lock);
      exr_library_delete(g.library, id, &discard);
      LeaveCriticalSection(&g.library_lock);
    }
    return EXR_CANCELLED;
  }
  if (status == EXR_OK) {
    job->imported = 1;
    job->imported_id = id;
    job->created = created;
  }
  return status;
}

static unsigned __stdcall job_thread(void *context) {
  host_job *job = context;
  job_pause(job);
  if (job_cancel_flag(job))
    job->status = EXR_CANCELLED;
  else
    job->status = job_run(job);
  if (job->status == EXR_CANCELLED) frame_clear(&job->frame);
  if (!PostMessageW(g.window, WM_HOST_COMPLETE, 0, (LPARAM)job)) {
    /* Window gone; the UI-side reference is released during shutdown. */
  }
  job_release(job);
  return 0;
}

static exr_status job_run(host_job *job) {
  switch (job->kind) {
    case JOB_OPEN: return job_open(job);
    case JOB_GO: return job_go(job);
    case JOB_LAYOUT: return job_layout(job);
    case JOB_IMPORT: return job_import(job);
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
static void save_progress(void);
static void update_page_label(void);
static void handle_job_complete(host_job *job);

static int dragging;

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

static void create_controls(HWND parent) {
  g.import_label = make_static(parent, IDC_IMPORT_LABEL, L"导入路径");
  g.import_edit = CreateWindowExW(WS_EX_CLIENTEDGE, L"EDIT", L"", WS_CHILD | WS_VISIBLE | WS_TABSTOP |
                                  ES_AUTOHSCROLL, 0, 0, 10, 10, parent, (HMENU)(INT_PTR)IDC_IMPORT_EDIT, NULL, NULL);
  SendMessageW(g.import_edit, WM_SETFONT, (WPARAM)GetStockObject(DEFAULT_GUI_FONT), TRUE);
  g.import_button = make_button(parent, IDC_IMPORT_BUTTON, L"导入");
  g.open_button = make_button(parent, IDC_OPEN_BUTTON, L"打开");
  g.delete_button = make_button(parent, IDC_DELETE_BUTTON, L"删除");
  g.prev_button = make_button(parent, IDC_PREV, L"上一页");
  g.next_button = make_button(parent, IDC_NEXT, L"下一页");
  g.select_button = make_button(parent, IDC_SELECT_ALL, L"全选本页");
  g.copy_button = make_button(parent, IDC_COPY_QUOTE, L"复制引用");
  g.add_button = make_button(parent, IDC_ADD_NOTE, L"添加标注");
  g.update_button = make_button(parent, IDC_UPDATE_NOTE, L"更新标注");
  g.remove_button = make_button(parent, IDC_DELETE_NOTE, L"删除标注");
  g.jump_button = make_button(parent, IDC_JUMP_NOTE, L"跳转标注");
  g.font_dec = make_button(parent, IDC_FONT_DEC, L"字号-");
  g.font_inc = make_button(parent, IDC_FONT_INC, L"字号+");
  g.zoom_dec = make_button(parent, IDC_ZOOM_DEC, L"缩放-");
  g.zoom_inc = make_button(parent, IDC_ZOOM_INC, L"缩放+");
  g.cancel_button = make_button(parent, IDC_CANCEL, L"取消");
  g.shelf_label = make_static(parent, IDC_SHELF_LABEL, L"书架");
  g.books = CreateWindowExW(WS_EX_CLIENTEDGE, L"LISTBOX", L"书架",
                            WS_CHILD | WS_VISIBLE | WS_TABSTOP | WS_VSCROLL | LBS_NOTIFY | LBS_NOINTEGRALHEIGHT,
                            0, 0, 10, 10, parent, (HMENU)(INT_PTR)IDC_BOOKS, NULL, NULL);
  SendMessageW(g.books, WM_SETFONT, (WPARAM)GetStockObject(DEFAULT_GUI_FONT), TRUE);
  g.notes_label = make_static(parent, IDC_NOTES_LABEL, L"标注（双击跳转）");
  g.notes = CreateWindowExW(WS_EX_CLIENTEDGE, L"LISTBOX", L"标注列表",
                            WS_CHILD | WS_VISIBLE | WS_TABSTOP | WS_VSCROLL | LBS_NOTIFY | LBS_NOINTEGRALHEIGHT,
                            0, 0, 10, 10, parent, (HMENU)(INT_PTR)IDC_NOTES, NULL, NULL);
  SendMessageW(g.notes, WM_SETFONT, (WPARAM)GetStockObject(DEFAULT_GUI_FONT), TRUE);
  g.note_edit = CreateWindowExW(WS_EX_CLIENTEDGE, L"EDIT", L"", WS_CHILD | WS_VISIBLE | WS_TABSTOP |
                                 ES_MULTILINE | ES_AUTOVSCROLL | WS_VSCROLL,
                                 0, 0, 10, 10, parent, (HMENU)(INT_PTR)IDC_NOTE_EDIT, NULL, NULL);
  SendMessageW(g.note_edit, WM_SETFONT, (WPARAM)GetStockObject(DEFAULT_GUI_FONT), TRUE);
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
  books_height = (content_bottom - content_top - 30) * 45 / 100;
  if (books_height < 120) books_height = 120;
  MoveWindow(g.books, 8, content_top + 20, left_width - 16, books_height, TRUE);
  notes_top = content_top + 20 + books_height + 24;
  notes_height = content_bottom - 62 - notes_top;
  if (notes_height < 80) notes_height = 80;
  MoveWindow(g.notes_label, 8, notes_top - 20, left_width - 16, 18, TRUE);
  MoveWindow(g.notes, 8, notes_top, left_width - 16, notes_height, TRUE);
  MoveWindow(g.note_edit, 8, content_bottom - 56, left_width - 16, 52, TRUE);
  MoveWindow(g.page, left_width + 4, content_top, width - left_width - 12, content_bottom - content_top - 4, TRUE);
  MoveWindow(g.page_label, 8, content_bottom + 8, 330, 22, TRUE);
  MoveWindow(g.status, 346, content_bottom + 8, width - 354, 22, TRUE);
}

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
  if (!g.selection.active || !g.frame.valid) return;
  if (g.session.book_id != g.frame.book_id) return;
  selection_bounds(&start, &end);
  if (start == end) return;
  if (!g.frame.fixed) {
    const exr_glyph *glyphs;
    size_t count = 0, i;
    if (!g.session.layout || g.session.page != g.frame.page) return;
    glyphs = exr_layout_glyphs(g.session.layout, &count);
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
    if (!g.session.fixed_text || g.session.fixed_text_page != g.frame.page) return;
    if (exr_fixed_text_select(g.session.fixed_text, start, end, NULL, &regions, &count, &error) != EXR_OK)
      return;
    if (exr_viewport_create(&g.session.geometry, g.frame.render_scale, &viewport, &error) != EXR_OK) {
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
  if (!g.view.valid && !compute_view()) return SIZE_MAX;
  if (g.session.book_id != g.frame.book_id) return SIZE_MAX;
  lx = (float)((x - g.view.dx) / g.view.scale);
  ly = (float)((y - g.view.dy) / g.view.scale);
  if (lx < 0 || ly < 0 || lx > g.frame.bitmap.width || ly > g.frame.bitmap.height) return SIZE_MAX;
  if (!g.frame.fixed) {
    size_t offset;
    if (!g.session.layout || g.session.page != g.frame.page) return SIZE_MAX;
    offset = exr_layout_hit_test(g.session.layout, 0, lx, ly);
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
    if (!g.session.fixed_text || g.session.fixed_text_page != g.frame.page) return SIZE_MAX;
    if (exr_viewport_create(&g.session.geometry, g.frame.render_scale, &viewport, &error) != EXR_OK)
      return SIZE_MAX;
    sx = viewport.inverse[0] * lx + viewport.inverse[2] * ly + viewport.inverse[4];
    sy = viewport.inverse[1] * lx + viewport.inverse[3] * ly + viewport.inverse[5];
    if (exr_fixed_text_hit(g.session.fixed_text, sx, sy, 80.0, EXR_REGION_INVISIBLE, NULL,
                           &region, &error) != EXR_OK || region == SIZE_MAX)
      return SIZE_MAX;
    regions = exr_fixed_text_regions(g.session.fixed_text, &count);
    if (!regions || region >= count) return SIZE_MAX;
    return at_end ? regions[region].end : regions[region].start;
  }
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
    case WM_GETDLGCODE:
      return DLGC_WANTARROWS | DLGC_WANTCHARS;
    case WM_LBUTTONDOWN:
      if (g.job || g.pending || !g.frame.valid) return 0;
      SetFocus(window);
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
      if (dragging) {
        size_t offset = point_offset((short)LOWORD(lparam), (short)HIWORD(lparam), 1);
        if (offset != SIZE_MAX && offset != g.selection.end) {
          g.selection.end = offset;
          InvalidateRect(window, NULL, FALSE);
        }
      }
      return 0;
    case WM_LBUTTONUP:
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
    swprintf(text, 256, L"第 %llu 页 · %ls · 字号 %d%%",
             (unsigned long long)(g.frame.page + 1),
             format_name(g.current.format), g.font_percent);
    SetWindowTextW(g.page_label, text);
  }
}

static void save_progress(void) {
  exr_error error = {0};
  exr_status status;
  if (!g.has_current || !g.session.active || !g.frame.valid || g.job || g.pending) return;
  EnterCriticalSection(&g.library_lock);
  if (g.session.fixed) {
    exr_book snapshot;
    if (book_copy(&snapshot, &g.current)) {
      snapshot.position = g.frame.page;
      status = exr_library_update(g.library, &snapshot, &error);
      book_clear(&snapshot);
      (void)status;
    }
  } else {
    exr_anchor anchor = {0};
    status = exr_anchor_create(g.session.document, g.frame.range_start, g.frame.range_start,
                               &anchor, &error);
    if (status == EXR_OK) {
      status = exr_library_progress(g.library, g.current.id, &anchor, &error);
      exr_anchor_free(&anchor);
    }
    if (status != EXR_OK) {
      exr_book snapshot;
      memset(&error, 0, sizeof(error));
      if (book_copy(&snapshot, &g.current)) {
        snapshot.position = g.frame.range_start;
        status = exr_library_update(g.library, &snapshot, &error);
        book_clear(&snapshot);
        (void)status;
      }
    }
  }
  LeaveCriticalSection(&g.library_lock);
}

static void apply_pending_selection(void) {
  size_t start, end;
  if (!g.pending_selection) return;
  g.pending_selection = 0;
  if (!g.has_current || g.pending_book != g.current.id || !g.frame.valid) return;
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
  } else if (direction < 0 && g.frame.page == 0) {
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
  if (exr_anchor_create(g.session.document, g.frame.range_start, g.frame.range_start,
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
  job->has_anchor = 1;
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
    if (!g.session.fixed_text || g.session.fixed_text_page != g.frame.page) return 0;
    bytes = exr_fixed_text_string(g.session.fixed_text, &size);
    if (!bytes || end > size) return 0;
    *text = malloc(end - start + 1);
    if (!*text) return 0;
    memcpy(*text, bytes + start, end - start);
    (*text)[end - start] = 0;
    return end - start;
  } else {
    const char *bytes;
    size_t size = 0;
    if (!g.session.document) return 0;
    bytes = exr_document_text(g.session.document, &size);
    if (!bytes || end > size) return 0;
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
      const exr_note *note = &g.reflow_notes[index];
      const char *quote = note->anchor.exact ? note->anchor.exact : "";
      const char *comment = note->text ? note->text : "";
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
  int64_t id = 0;
  exr_error error = {0};
  exr_status status;
  if (!g.has_current || !g.frame.valid) { set_status(L"请先打开一本书。"); return; }
  if (!g.selection.active) { set_status(L"请先选择文字，再添加标注。"); return; }
  note_comment_read(comment, sizeof(comment));
  EnterCriticalSection(&g.library_lock);
  if (g.session.fixed) {
    exr_fixed_note note;
    memset(&note, 0, sizeof(note));
    note.book_id = g.current.id;
    note.page = g.selection.page;
    note.start = g.selection.start;
    note.end = g.selection.end;
    note.text = comment;
    status = exr_library_fixed_note(g.library, &note, NULL, &id, &error);
  } else {
    exr_note note;
    exr_anchor anchor = {0};
    memset(&note, 0, sizeof(note));
    status = exr_anchor_create(g.session.document, g.selection.start, g.selection.end,
                               &anchor, &error);
    if (status == EXR_OK) {
      note.book_id = g.current.id;
      note.start = g.selection.start;
      note.end = g.selection.end;
      note.text = comment;
      note.anchor = anchor;
      status = exr_library_note(g.library, &note, &id, &error);
      exr_anchor_free(&anchor);
    }
  }
  LeaveCriticalSection(&g.library_lock);
  if (status != EXR_OK) {
    wchar_t message[512];
    describe_error(message, 512, L"添加标注失败", status, &error);
    set_status(message);
    return;
  }
  reload_notes();
  if (g.notes && current_note_count()) {
    SendMessageW(g.notes, LB_SETCURSEL, (WPARAM)(current_note_count() - 1), 0);
  }
  set_statusf(L"已添加标注 #%lld。", (long long)id);
}

static void update_note(void) {
  int index = notes_selected();
  char comment[65536];
  exr_error error = {0};
  exr_status status;
  if (index < 0) { set_status(L"请先在标注列表中选择一条标注。"); return; }
  note_comment_read(comment, sizeof(comment));
  EnterCriticalSection(&g.library_lock);
  if (g.session.fixed) {
    exr_fixed_note note = g.fixed_notes[index];
    note.text = comment;
    status = exr_library_fixed_note(g.library, &note, NULL, &note.id, &error);
  } else {
    status = exr_library_note_text(g.library, g.reflow_notes[index].id, comment, &error);
  }
  LeaveCriticalSection(&g.library_lock);
  if (status != EXR_OK) {
    wchar_t message[512];
    describe_error(message, 512, L"更新标注失败", status, &error);
    set_status(message);
    return;
  }
  reload_notes();
  if (g.notes) SendMessageW(g.notes, LB_SETCURSEL, (WPARAM)index, 0);
  set_status(L"已更新标注。");
}

static void delete_note(void) {
  int index = notes_selected();
  exr_error error = {0};
  exr_status status;
  if (index < 0) { set_status(L"请先在标注列表中选择一条标注。"); return; }
  EnterCriticalSection(&g.library_lock);
  if (g.session.fixed)
    status = exr_library_remove_fixed_note(g.library, g.fixed_notes[index].id, &error);
  else
    status = exr_library_remove_note(g.library, g.reflow_notes[index].id, &error);
  LeaveCriticalSection(&g.library_lock);
  if (status != EXR_OK) {
    wchar_t message[512];
    describe_error(message, 512, L"删除标注失败", status, &error);
    set_status(message);
    return;
  }
  reload_notes();
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
    const exr_note *note = &g.reflow_notes[index];
    exr_anchor_match match;
    exr_error error = {0};
    size_t offset;
    size_t target_start = note->start, target_end = note->end;
    if (!g.session.document) return;
    if (!note->anchor.exact) {
      if (note->start == SIZE_MAX) { set_status(L"该标注没有可用的文本锚点。"); return; }
      offset = note->start;
      set_status(L"旧版标注：按保存的文本偏移跳转。");
    } else {
      if (exr_anchor_resolve(g.session.document, &note->anchor, &match, &error) != EXR_OK) {
        set_status(L"标注锚点解析失败。");
        return;
      }
      if (match.state == EXR_ANCHOR_AMBIGUOUS) {
        set_status(L"标注定位存在歧义：同一文本出现多处，未跳转。");
        return;
      }
      if (match.state == EXR_ANCHOR_MISSING) {
        set_status(L"标注原文已不存在，未跳转。");
        return;
      }
      if (match.state == EXR_ANCHOR_LEGACY) {
        set_status(L"标注没有文本锚点，未跳转。");
        return;
      }
      offset = match.start;
      target_start = match.start;
      target_end = match.end;
    }
    job = job_new(JOB_GO);
    if (!job) return;
    job->book_id = g.current.id;
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
  if (!g.job && !g.pending) save_progress();
  job = job_new(JOB_OPEN);
  if (!job) { set_status(L"内存不足，无法打开书籍。"); return; }
  job->book_id = g.shelf[index].id;
  job->font_percent = g.font_percent;
  job_submit(job);
}

static void delete_selected_book(void) {
  LRESULT index;
  int64_t id;
  exr_error error = {0};
  exr_status status;
  if (g.job || g.pending) return;
  if (!g.books) return;
  index = SendMessageW(g.books, LB_GETCURSEL, 0, 0);
  if (index == LB_ERR || (size_t)index >= g.shelf_count) {
    set_status(L"请先在书架中选择一本书。");
    return;
  }
  id = g.shelf[index].id;
  EnterCriticalSection(&g.library_lock);
  status = exr_library_delete(g.library, id, &error);
  LeaveCriticalSection(&g.library_lock);
  if (status != EXR_OK) {
    wchar_t message[512];
    describe_error(message, 512, L"删除书籍失败", status, &error);
    set_status(message);
    return;
  }
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
  reload_shelf();
  host_update_controls();
  set_status(L"已删除书籍及其标注。");
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

static void import_title_fallback(const wchar_t *path, int64_t id) {
  int index = shelf_index(id);
  exr_book *row;
  exr_book copy;
  wchar_t stem[HOST_PATH];
  const wchar_t *base;
  wchar_t *dot;
  char *utf8;
  exr_error error = {0};
  if (index < 0) return;
  row = &g.shelf[index];
  if (row->title && row->title[0] && strcmp(row->title, "Untitled")) return;
  base = wcsrchr(path, L'\\');
  base = base ? base + 1 : path;
  copy_wstring(stem, HOST_PATH, base);
  dot = wcsrchr(stem, L'.');
  if (dot && dot != stem) *dot = 0;
  if (!stem[0]) return;
  utf8 = host_utf8(stem);
  if (!utf8) return;
  if (!book_copy(&copy, row)) { free(utf8); return; }
  free(copy.title);
  copy.title = utf8;
  EnterCriticalSection(&g.library_lock);
  exr_library_update(g.library, &copy, &error);
  LeaveCriticalSection(&g.library_lock);
  book_clear(&copy);
  reload_shelf();
}

static void host_update_controls(void) {
  int busy = (g.job != NULL) || (g.pending != NULL);
  int has = g.has_current && g.frame.valid;
  EnableWindow(g.import_button, !busy);
  EnableWindow(g.open_button, g.shelf_count > 0);
  EnableWindow(g.delete_button, !busy && g.shelf_count > 0);
  EnableWindow(g.prev_button, !busy && has && g.frame.page > 0);
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
}

static void handle_job_complete(host_job *job) {
  if (job->status == EXR_OK) {
    if (job->kind == JOB_OPEN) {
      int index = shelf_index(job->book_id);
      if (job->session_swapped && job->have_frame && index >= 0) {
        book_clear(&g.current);
        if (book_copy(&g.current, &g.shelf[index])) {
          g.has_current = 1;
          g.active_book_id = g.current.id;
          frame_move(&g.frame, &job->frame);
          memset(&g.selection, 0, sizeof(g.selection));
          g.session.page = g.frame.page;
          reload_notes();
          update_page_label();
          settings_save();
          {
            wchar_t *title = g.current.title ? host_wide(g.current.title, strlen(g.current.title)) : NULL;
            if (job->message[0])
              set_statusf(L"已打开《%ls》 · %ls", title ? title : L"Untitled", job->message);
            else
              set_statusf(L"已打开《%ls》。", title ? title : L"Untitled");
            free(title);
          }
          save_progress();
        } else {
          set_status(L"内存不足，无法保存当前书籍信息。");
        }
      } else {
        set_status(L"打开书籍失败：任务结果不完整。");
      }
    } else if (job->kind == JOB_GO || job->kind == JOB_LAYOUT) {
      if (job->have_frame) {
        frame_move(&g.frame, &job->frame);
        memset(&g.selection, 0, sizeof(g.selection));
        g.session.page = g.frame.page;
        if (job->kind == JOB_LAYOUT && job->font_percent > 0) g.font_percent = job->font_percent;
        if (job->zoom_percent > 0) g.zoom_percent = job->zoom_percent;
        save_progress();
        update_page_label();
        settings_save();
        if (job->message[0]) set_status(job->message);
        else set_statusf(L"第 %llu 页。", (unsigned long long)(g.frame.page + 1));
        apply_pending_selection();
      } else {
        set_status(L"翻页失败：任务没有生成画面。");
      }
    } else if (job->kind == JOB_IMPORT) {
      reload_shelf();
      if (job->created) import_title_fallback(job->path, job->imported_id);
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
      if (g.auto_open_imported && job->imported) {
        host_job *open = job_new(JOB_OPEN);
        g.auto_open_imported = 0;
        if (open) {
          open->book_id = job->imported_id;
          open->font_percent = g.font_percent;
          job_submit(open);
        }
      }
    }
  } else if (job->status == EXR_CANCELLED) {
    set_status(job->kind == JOB_IMPORT ? L"导入已取消；书架内容与当前画面保持不变。"
                                       : L"任务已取消；当前画面保持原书。");
  } else if (job->kind == JOB_GO && job->status == EXR_ARGUMENT && job->direction > 0) {
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
  switch (id) {
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
    if (g.session.fixed_text) {
      bytes = exr_fixed_text_string(g.session.fixed_text, &size);
      start = 0;
      end = size;
    } else {
      start = end = 0;
    }
  } else {
    if (g.session.document) bytes = exr_document_text(g.session.document, &size);
    start = g.frame.range_start;
    end = g.frame.range_end;
    if (end > size) end = size;
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
    if (!g.frame.fixed && g.session.document) {
      size_t size = 0;
      const char *bytes = exr_document_text(g.session.document, &size);
      if (bytes && g.frame.range_end <= size) {
        page_hash = fnv1a(bytes + g.frame.range_start, g.frame.range_end - g.frame.range_start);
        hashed_length = g.frame.range_end - g.frame.range_start;
      }
    } else if (g.session.fixed_text) {
      size_t size = 0;
      const char *bytes = exr_fixed_text_string(g.session.fixed_text, &size);
      if (bytes) {
        page_hash = fnv1a(bytes, size);
        hashed_length = size;
      }
    }
  }
  length = page_text_snapshot(page_prefix, sizeof(page_prefix));
  offset_text[0] = 0;
  if (g.frame.valid) {
    if (!g.frame.fixed && g.session.document) {
      size_t size = 0;
      const char *bytes = exr_document_text(g.session.document, &size);
      if (bytes && g.frame.range_start <= size)
        truncate_utf8(offset_text, sizeof(offset_text), bytes + g.frame.range_start,
                      size - g.frame.range_start < 64 ? size - g.frame.range_start : 64);
    } else if (g.session.fixed_text) {
      size_t size = 0;
      const char *bytes = exr_fixed_text_string(g.session.fixed_text, &size);
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
  }
  detail_add(detail, sizeof(detail), "state", name);
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
    if (!strcmp(what, "page")) {
      pass = g.frame.valid && g.frame.page + 1 == (size_t)atoi(drive_args[2]);
      snprintf(number, sizeof(number), "%llu", (unsigned long long)(g.frame.valid ? g.frame.page + 1 : 0));
      detail_add(detail, sizeof(detail), "page", number);
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
        drive_step_finish(1, detail);
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

static LRESULT CALLBACK procedure(HWND window, UINT message, WPARAM wparam, LPARAM lparam) {
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
      if (id == IDC_BOOKS && code == LBN_DBLCLK) {
        open_selected_book();
        return 0;
      }
      if (id == IDC_NOTES && code == LBN_SELCHANGE) {
        int index = notes_selected();
        if (index >= 0) {
          if (g.session.fixed) note_comment_write(g.fixed_notes[index].text);
          else note_comment_write(g.reflow_notes[index].text);
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
      g.job = NULL;
      handle_job_complete(job);
      job_release(job);
      if (g.pending) {
        host_job *next = g.pending;
        g.pending = NULL;
        job_start(next);
      } else {
        host_update_controls();
      }
      if (g.closing) DestroyWindow(window);
      return 0;
    }
    case WM_TIMER:
      if (wparam == 1 && g.drive_mode) drive_tick();
      return 0;
    case WM_CLOSE:
      if (g.closing) return 0;
      g.closing = 1;
      KillTimer(window, 1);
      if (g.pending) {
        job_release(g.pending);
        g.pending = NULL;
      }
      if (g.job) {
        InterlockedExchange(&g.job->cancel, 1);
        if (WaitForSingleObject(g.job->thread, 20000) != WAIT_OBJECT_0) {
          /* Cooperative cancellation failed; do not free SDK objects in use. */
          ExitProcess(0);
        }
        g.discard = g.job;
        g.job = NULL;
      }
      if (g.has_current && g.session.active && g.frame.valid) save_progress();
      settings_save();
      DestroyWindow(window);
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
    if (g.window && IsDialogMessageW(g.window, &message)) continue;
    TranslateMessage(&message);
    DispatchMessageW(&message);
  }
  return (int)message.wParam;
}

static void host_cleanup(void) {
  if (g.job) {
    InterlockedExchange(&g.job->cancel, 1);
    if (g.job->thread) WaitForSingleObject(g.job->thread, 20000);
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
  if (g.library) exr_library_close(g.library);
  g.library = NULL;
  exr_font_free(g.font);
  g.font = NULL;
  if (g.drive_log) fclose(g.drive_log);
  g.drive_log = NULL;
  if (drive_file) fclose(drive_file);
  drive_file = NULL;
  DeleteCriticalSection(&g.library_lock);
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
      DeleteCriticalSection(&g.library_lock);
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
  if (script[0]) drive_start();
  if (book_path[0] && !script[0]) {
    g.auto_open_imported = 1;
    import_path(book_path, 0);
  } else if (g.active_book_id > 0 && shelf_index(g.active_book_id) >= 0) {
    host_job *job = job_new(JOB_OPEN);
    SendMessageW(g.books, LB_SETCURSEL, (WPARAM)shelf_index(g.active_book_id), 0);
    if (job) {
      job->book_id = g.active_book_id;
      job->font_percent = g.font_percent;
      job_submit(job);
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
