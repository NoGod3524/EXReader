/* SPDX-License-Identifier: MIT
 * Windows acceptance probe: a real window with RegisterDragDrop, real shell and
 * synthetic OLE data objects, and real clipboard contents. Every input is
 * created by this program under %TEMP%; no user file and no user clipboard
 * content is read.
 */
#include <exr_desktop_drop.h>
#include <exr_desktop_drop_windows.h>
#include "report.h"
#include <shlobj.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <wchar.h>

#define CASE_MAX 260

static HWND g_window;
static wchar_t g_root[MAX_PATH];
static int g_clipboard_ok;

typedef struct {
  int calls;
  exr_drop_status status;
  exr_drop_request *request;
  size_t items;
  exr_drop_item_status first_status;
  char first_path[600];
  int hold_request;
  int destroy_in_callback;
  exr_drop_windows_target *target;
  exr_drop_status destroy_status;
} capture;

static CLIPFORMAT file_group_format(void) {
  /* CFSTR_FILEDESCRIPTORW is a narrow literal in this SDK; the atom is wide. */
  return (CLIPFORMAT)RegisterClipboardFormatW(L"FileGroupDescriptorW");
}

static void capture_reset(capture *state) {
  if (state->request) exr_drop_request_release(state->request);
  memset(state, 0, sizeof(*state));
}

static void on_drop(void *context, exr_drop_status status, exr_drop_request *request) {
  capture *state = (capture *)context;
  exr_drop_request_info info;
  state->calls++;
  state->status = status;
  state->items = 0;
  state->first_status = (exr_drop_item_status)0;
  state->first_path[0] = 0;
  if (request) {
    memset(&info, 0, sizeof(info));
    info.struct_size = sizeof(info);
    if (exr_drop_request_get_info(request, &info) == EXR_DROP_OK) {
      state->items = info.item_count;
      if (info.item_count) {
        exr_drop_item item;
        memset(&item, 0, sizeof(item));
        item.struct_size = sizeof(item);
        if (exr_drop_request_get_item(request, 0, &item) == EXR_DROP_OK) {
          state->first_status = item.status;
          if (item.path) {
            size_t copy = strlen(item.path);
            if (copy >= sizeof(state->first_path)) copy = sizeof(state->first_path) - 1;
            memcpy(state->first_path, item.path, copy);
            state->first_path[copy] = 0;
          }
        }
      }
    }
    if (state->hold_request)
      state->request = request;
    else
      exr_drop_request_release(request);
  }
  if (state->destroy_in_callback && state->target) {
    state->destroy_status = exr_drop_windows_detach(state->target);
    state->target = NULL;
  }
}

/* ---- fixtures -------------------------------------------------------- */
static int make_root(void) {
  DWORD pid = GetCurrentProcessId();
  wchar_t temp[MAX_PATH];
  if (!GetTempPathW(MAX_PATH, temp)) return 0;
  swprintf_s(g_root, MAX_PATH, L"%sexr-drop-probe-%lu", temp, (unsigned long)pid);
  CreateDirectoryW(g_root, NULL);
  {
    wchar_t ascii[MAX_PATH];
    swprintf_s(ascii, MAX_PATH, L"%s\\a.txt", g_root);
    CreateFileW(ascii, GENERIC_WRITE, 0, NULL, CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, NULL);
  }
  {
    wchar_t unicode[MAX_PATH];
    HANDLE handle;
    swprintf_s(unicode, MAX_PATH, L"%s\\exr drop \x4E2D\x6587.epub", g_root);
    handle = CreateFileW(unicode, GENERIC_WRITE, 0, NULL, CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, NULL);
    if (handle != INVALID_HANDLE_VALUE) CloseHandle(handle);
  }
  {
    wchar_t directory[MAX_PATH];
    swprintf_s(directory, MAX_PATH, L"%s\\sub", g_root);
    CreateDirectoryW(directory, NULL);
  }
  return 1;
}

static HGLOBAL make_hdrop(wchar_t **paths, size_t count) {
  size_t bytes = sizeof(DROPFILES), index;
  HGLOBAL handle;
  DROPFILES *header;
  char *cursor;
  for (index = 0; index < count; index++) bytes += (wcslen(paths[index]) + 1) * sizeof(wchar_t);
  bytes += sizeof(wchar_t);
  handle = GlobalAlloc(GHND, bytes);
  if (!handle) return NULL;
  header = (DROPFILES *)GlobalLock(handle);
  if (!header) {
    GlobalFree(handle);
    return NULL;
  }
  memset(header, 0, sizeof(*header));
  header->pFiles = (DWORD)sizeof(DROPFILES);
  header->fWide = TRUE;
  cursor = (char *)header + sizeof(DROPFILES);
  for (index = 0; index < count; index++) {
    size_t size = (wcslen(paths[index]) + 1) * sizeof(wchar_t);
    memcpy(cursor, paths[index], size);
    cursor += size;
  }
  GlobalUnlock(handle);
  return handle;
}

static HGLOBAL make_wide(const wchar_t *text, size_t units) {
  HGLOBAL handle = GlobalAlloc(GHND, (units + 1) * sizeof(wchar_t));
  wchar_t *target;
  if (!handle) return NULL;
  target = (wchar_t *)GlobalLock(handle);
  if (!target) {
    GlobalFree(handle);
    return NULL;
  }
  memcpy(target, text, units * sizeof(wchar_t));
  target[units] = 0;
  GlobalUnlock(handle);
  return handle;
}

static HGLOBAL make_file_group(const wchar_t *name) {
  HGLOBAL handle = GlobalAlloc(GHND, sizeof(FILEGROUPDESCRIPTORW));
  FILEGROUPDESCRIPTORW *group;
  if (!handle) return NULL;
  group = (FILEGROUPDESCRIPTORW *)GlobalLock(handle);
  if (!group) {
    GlobalFree(handle);
    return NULL;
  }
  memset(group, 0, sizeof(*group));
  group->cItems = 1;
  wcsncpy_s(group->fgd[0].cFileName, 260, name, _TRUNCATE);
  GlobalUnlock(handle);
  return handle;
}

static int clipboard_put(CLIPFORMAT format, HGLOBAL memory) {
  int attempt;
  for (attempt = 0; attempt < 10; attempt++) {
    if (OpenClipboard(g_window)) break;
    Sleep(20);
  }
  if (attempt == 10) {
    GlobalFree(memory);
    return 0;
  }
  EmptyClipboard();
  if (!SetClipboardData(format, memory)) {
    GlobalFree(memory);
    CloseClipboard();
    return 0;
  }
  CloseClipboard();
  return 1;
}

/* ---- synthetic IDataObject ------------------------------------------- */
typedef struct test_object {
  IDataObjectVtbl *lpVtbl;
  LONG refs;
  CLIPFORMAT format;
  HGLOBAL memory;
} test_object;

static HRESULT STDMETHODCALLTYPE test_QueryInterface(IDataObject *iface, REFIID iid, void **out) {
  test_object *object = (test_object *)iface;
  if (!out) return E_POINTER;
  if (IsEqualIID(iid, &IID_IUnknown) || IsEqualIID(iid, &IID_IDataObject)) {
    object->refs++;
    *out = iface;
    return S_OK;
  }
  *out = NULL;
  return E_NOINTERFACE;
}
static ULONG STDMETHODCALLTYPE test_AddRef(IDataObject *iface) {
  return (ULONG)++((test_object *)iface)->refs;
}
static ULONG STDMETHODCALLTYPE test_Release(IDataObject *iface) {
  test_object *object = (test_object *)iface;
  LONG left = --object->refs;
  if (left == 0) {
    if (object->memory) GlobalFree(object->memory);
    free(object);
  }
  return (ULONG)left;
}
static HRESULT STDMETHODCALLTYPE test_GetData(IDataObject *iface, FORMATETC *format, STGMEDIUM *medium) {
  test_object *object = (test_object *)iface;
  HGLOBAL copy;
  SIZE_T bytes;
  void *source, *target;
  if (!format || !medium) return E_POINTER;
  if (format->cfFormat != object->format || !(format->tymed & TYMED_HGLOBAL)) return DV_E_FORMATETC;
  bytes = GlobalSize(object->memory);
  copy = GlobalAlloc(GHND, bytes);
  if (!copy) return STG_E_MEDIUMFULL;
  source = GlobalLock(object->memory);
  target = GlobalLock(copy);
  if (!source || !target) {
    if (target) GlobalUnlock(copy);
    GlobalFree(copy);
    return E_OUTOFMEMORY;
  }
  memcpy(target, source, bytes);
  GlobalUnlock(copy);
  GlobalUnlock(object->memory);
  memset(medium, 0, sizeof(*medium));
  medium->tymed = TYMED_HGLOBAL;
  medium->hGlobal = copy;
  medium->pUnkForRelease = NULL;
  return S_OK;
}
static HRESULT STDMETHODCALLTYPE test_GetDataHere(IDataObject *iface, FORMATETC *format, STGMEDIUM *medium) {
  (void)iface;
  (void)format;
  (void)medium;
  return E_NOTIMPL;
}
static HRESULT STDMETHODCALLTYPE test_QueryGetData(IDataObject *iface, FORMATETC *format) {
  test_object *object = (test_object *)iface;
  if (!format) return E_POINTER;
  if (format->cfFormat != object->format) return DV_E_FORMATETC;
  if (!(format->tymed & TYMED_HGLOBAL)) return DV_E_TYMED;
  return S_OK;
}
static HRESULT STDMETHODCALLTYPE test_GetCanonicalFormatEtc(IDataObject *iface, FORMATETC *in, FORMATETC *out) {
  (void)iface;
  (void)in;
  (void)out;
  return E_NOTIMPL;
}
static HRESULT STDMETHODCALLTYPE test_SetData(IDataObject *iface, FORMATETC *format, STGMEDIUM *medium, BOOL release) {
  (void)iface;
  (void)format;
  (void)medium;
  (void)release;
  return E_NOTIMPL;
}
static HRESULT STDMETHODCALLTYPE test_EnumFormatEtc(IDataObject *iface, DWORD direction, IEnumFORMATETC **out) {
  (void)iface;
  (void)direction;
  if (out) *out = NULL;
  return E_NOTIMPL;
}
static HRESULT STDMETHODCALLTYPE test_DAdvise(IDataObject *iface, FORMATETC *f, DWORD flags, IAdviseSink *sink,
    DWORD *connection) {
  (void)iface;
  (void)f;
  (void)flags;
  (void)sink;
  (void)connection;
  return OLE_E_ADVISENOTSUPPORTED;
}
static HRESULT STDMETHODCALLTYPE test_DUnadvise(IDataObject *iface, DWORD connection) {
  (void)iface;
  (void)connection;
  return OLE_E_ADVISENOTSUPPORTED;
}
static HRESULT STDMETHODCALLTYPE test_EnumDAdvise(IDataObject *iface, IEnumSTATDATA **out) {
  (void)iface;
  if (out) *out = NULL;
  return OLE_E_ADVISENOTSUPPORTED;
}

static IDataObjectVtbl test_vtbl = {test_QueryInterface, test_AddRef, test_Release, test_GetData,
    test_GetDataHere, test_QueryGetData, test_GetCanonicalFormatEtc, test_SetData, test_EnumFormatEtc,
    test_DAdvise, test_DUnadvise, test_EnumDAdvise};

static IDataObject *test_object_create(CLIPFORMAT format, HGLOBAL memory) {
  test_object *object = (test_object *)calloc(1, sizeof(*object));
  if (!object) return NULL;
  object->lpVtbl = &test_vtbl;
  object->refs = 1;
  object->format = format;
  object->memory = memory;
  return (IDataObject *)object;
}

/* ---- malformed-buffer fixtures --------------------------------------- */
static HGLOBAL make_raw(const void *bytes, size_t size) {
  HGLOBAL handle = GlobalAlloc(GHND, size ? size : 1);
  void *target;
  if (!handle) return NULL;
  target = GlobalLock(handle);
  if (!target) {
    GlobalFree(handle);
    return NULL;
  }
  if (size) memcpy(target, bytes, size);
  GlobalUnlock(handle);
  return handle;
}

/* Header plus a caller-controlled list; the allocation is exactly what the
   header claims so pFiles and truncation cases are real. */
static HGLOBAL make_hdrop_raw(DWORD pfiles, BOOL wide, const void *list, size_t list_bytes) {
  size_t total = sizeof(DROPFILES) + list_bytes;
  HGLOBAL handle = GlobalAlloc(GHND, total);
  DROPFILES *header;
  if (!handle) return NULL;
  header = (DROPFILES *)GlobalLock(handle);
  if (!header) {
    GlobalFree(handle);
    return NULL;
  }
  memset(header, 0, sizeof(*header));
  header->pFiles = pfiles;
  header->fWide = wide;
  if (list && list_bytes) memcpy((unsigned char *)header + sizeof(DROPFILES), list, list_bytes);
  GlobalUnlock(handle);
  return handle;
}

static exr_drop_windows_target *g_target;

/* Deliver a synthetic data object and check the outcome. A rejected buffer must
   produce one callback with no request and DROPEFFECT_NONE. */
static void deliver_object(capture *state, const char *name, CLIPFORMAT format, HGLOBAL memory,
    exr_drop_status want_status, exr_drop_item_status want_item, size_t want_items) {
  IDataObject *object;
  DWORD effect = DROPEFFECT_COPY;
  char detail[300];
  if (!memory) {
    report_fail(name, "fixture allocation failed");
    return;
  }
  object = test_object_create(format, memory);
  if (!object) {
    GlobalFree(memory);
    report_fail(name, "object allocation failed");
    return;
  }
  capture_reset(state);
  if (!g_target || exr_drop_windows_deliver_drop(g_target, object, &effect) != EXR_DROP_OK) {
    report_fail(name, "deliver refused");
  } else if (want_status != EXR_DROP_OK) {
    snprintf(detail, sizeof(detail), "status=%s items=%zu request=%s effect=%lu",
        exr_drop_status_name(state->status), state->items, state->request ? "set" : "null",
        (unsigned long)effect);
    report_expect(name, state->calls == 1 && state->status == want_status && state->request == NULL
        && effect == DROPEFFECT_NONE, detail);
  } else {
    snprintf(detail, sizeof(detail), "status=%s items=%zu first=%s path=%s",
        exr_drop_status_name(state->status), state->items,
        exr_drop_item_status_name(state->first_status), state->first_path);
    report_expect(name, state->calls == 1 && state->status == EXR_DROP_OK && state->items == want_items
        && state->first_status == want_item, detail);
  }
  object->lpVtbl->Release(object);
}

static IDataObject *shell_data_object(const wchar_t *folder, const wchar_t *file) {
  PIDLIST_ABSOLUTE folder_pidl = NULL, file_pidl = NULL;
  PCUITEMID_CHILD child;
  IDataObject *object = NULL;
  SFGAOF attributes = 0;
  if (FAILED(SHParseDisplayName(folder, NULL, &folder_pidl, 0, &attributes))) return NULL;
  if (FAILED(SHParseDisplayName(file, NULL, &file_pidl, 0, &attributes))) {
    ILFree(folder_pidl);
    return NULL;
  }
  child = ILFindLastID(file_pidl);
  if (FAILED(SHCreateDataObject(folder_pidl, 1, (PCUITEMID_CHILD_ARRAY)&child, NULL, &IID_IDataObject,
          (void **)&object)))
    object = NULL;
  ILFree(file_pidl);
  ILFree(folder_pidl);
  return object;
}

/* ---- window ---------------------------------------------------------- */
static LRESULT CALLBACK probe_proc(HWND window, UINT message, WPARAM wparam, LPARAM lparam) {
  return DefWindowProcW(window, message, wparam, lparam);
}
static HWND make_window(void) {
  WNDCLASSW cls;
  memset(&cls, 0, sizeof(cls));
  cls.lpfnWndProc = probe_proc;
  cls.hInstance = GetModuleHandleW(NULL);
  cls.lpszClassName = L"EXRDropProbeWindow";
  RegisterClassW(&cls);
  return CreateWindowExW(0, cls.lpszClassName, L"EXR drop probe", WS_OVERLAPPEDWINDOW, 0, 0, 200, 160, NULL,
      NULL, cls.hInstance, NULL);
}

/* ---- worker threads -------------------------------------------------- */
typedef struct {
  int attach_status;
  int detach_status;
  HWND window;
} worker_result;

static DWORD WINAPI attach_worker(LPVOID parameter) {
  worker_result *result = (worker_result *)parameter;
  exr_drop_windows_target *target = NULL;
  exr_drop_target_options options;
  memset(&options, 0, sizeof(options));
  options.struct_size = sizeof(options);
  options.on_drop = on_drop;
  result->window = make_window();
  result->attach_status = (int)exr_drop_windows_attach(result->window, &options, &target);
  if (target) exr_drop_windows_detach(target);
  if (result->window) DestroyWindow(result->window);
  return 0;
}

typedef struct {
  exr_drop_windows_target *target;
  int status;
} detach_job;

static DWORD WINAPI detach_worker(LPVOID parameter) {
  detach_job *job = (detach_job *)parameter;
  job->status = (int)exr_drop_windows_detach(job->target);
  return 0;
}

/* ---- helpers --------------------------------------------------------- */
static int cancel_calls;
static int cancel_after_one(void *context) {
  int *seen = (int *)context;
  (void)cancel_calls;
  (*seen)++;
  return *seen > 1;
}

static void report_skip_clipboard(const char *name) {
  report_skip(name, "clipboard unavailable on this runner session");
}

int main(void) {
  capture state;
  exr_drop_windows_target *target = NULL;
  exr_drop_target_options options;
  exr_drop_request *request = NULL;
  exr_drop_control control;
  int cancelled = 0;
  HGLOBAL memory;
  DWORD effect;
  HRESULT ole;

  memset(&state, 0, sizeof(state));
  ole = OleInitialize(NULL);
  report_expect("ole_initialize", ole == S_OK || ole == S_FALSE, "OLE apartment ready on this thread");
  if (!make_root()) {
    report_fail("fixtures_created", "temp root unavailable");
  } else {
    report_pass("fixtures_created", "temp files under %TEMP%");
  }
  g_window = make_window();
  report_expect("window_created", g_window != NULL, "probe window");
  if (!g_window) return report_summary("windows");

  memset(&options, 0, sizeof(options));
  options.struct_size = sizeof(options);
  options.on_drop = on_drop;
  options.context = &state;
  report_expect("attach_real_window", exr_drop_windows_attach(g_window, &options, &target) == EXR_DROP_OK,
      "RegisterDragDrop succeeded");
  g_target = target;
  {
    exr_drop_windows_target *scratch = NULL;
    report_expect("attach_null_window", exr_drop_windows_attach(NULL, &options, &scratch) == EXR_DROP_ARGUMENT,
        "NULL window refused");
    scratch = NULL;
    report_expect("attach_bad_options", exr_drop_windows_attach(g_window, NULL, &scratch) == EXR_DROP_ARGUMENT,
        "NULL options refused");
  }
  {
    worker_result worker;
    HANDLE thread;
    memset(&worker, 0, sizeof(worker));
    thread = CreateThread(NULL, 0, attach_worker, &worker, 0, NULL);
    if (!thread) {
      report_skip("attach_needs_ole_per_thread", "thread creation failed");
    } else {
      WaitForSingleObject(thread, INFINITE);
      CloseHandle(thread);
      report_expect("attach_needs_ole_per_thread", worker.attach_status == (int)EXR_DROP_PLATFORM,
          "a thread without OLE initialization is refused");
    }
  }

  /* ---- clipboard ----------------------------------------------------- */
  {
    int probe = 0, attempt;
    for (attempt = 0; attempt < 10; attempt++) {
      if (OpenClipboard(g_window)) {
        probe = 1;
        CloseClipboard();
        break;
      }
      Sleep(20);
    }
    g_clipboard_ok = probe;
  }
  if (!g_clipboard_ok) {
    report_skip_clipboard("clipboard_hdrop_unicode_paths");
    report_skip_clipboard("clipboard_empty");
    report_skip_clipboard("clipboard_text_lines");
    report_skip_clipboard("clipboard_unpaired_surrogate");
    report_skip_clipboard("clipboard_bom_skipped");
    report_skip_clipboard("clipboard_relative_text");
    report_skip_clipboard("clipboard_directory");
    report_skip_clipboard("clipboard_duplicates");
    report_skip_clipboard("clipboard_item_cap");
    report_skip_clipboard("clipboard_long_path");
    report_skip_clipboard("clipboard_cancel");
    report_skip_clipboard("request_outlives_clipboard");
  } else {
    {
      wchar_t ascii[MAX_PATH], unicode[MAX_PATH];
      wchar_t *paths[2];
      swprintf_s(ascii, MAX_PATH, L"%s\\a.txt", g_root);
      swprintf_s(unicode, MAX_PATH, L"%s\\exr drop \x4E2D\x6587.epub", g_root);
      paths[0] = ascii;
      paths[1] = unicode;
      memory = make_hdrop(paths, 2);
      capture_reset(&state);
      if (!clipboard_put(CF_HDROP, memory)) {
        report_fail("clipboard_hdrop_unicode_paths", "SetClipboardData failed");
      } else {
        exr_drop_status status = exr_drop_windows_clipboard_request(EXR_DROP_ORIGIN_CLIPBOARD, NULL, &request);
        if (status == EXR_DROP_OK) {
          exr_drop_request_info local;
          memset(&local, 0, sizeof(local));
          local.struct_size = sizeof(local);
          exr_drop_request_get_info(request, &local);
          report_expect("clipboard_hdrop_unicode_paths",
              local.item_count == 2 && local.file_count == 2 && local.origin == EXR_DROP_ORIGIN_CLIPBOARD,
              "two existing files with a non-ASCII name");
          exr_drop_request_release(request);
          request = NULL;
        } else {
          report_fail("clipboard_hdrop_unicode_paths", exr_drop_status_name(status));
        }
      }
    }
    {
      int attempt;
      capture_reset(&state);
      for (attempt = 0; attempt < 10; attempt++) {
        if (OpenClipboard(g_window)) break;
        Sleep(20);
      }
      EmptyClipboard();
      CloseClipboard();
      if (exr_drop_windows_clipboard_request(EXR_DROP_ORIGIN_CLIPBOARD, NULL, &request) == EXR_DROP_EMPTY)
        report_pass("clipboard_empty", "empty clipboard reported as empty");
      else
        report_fail("clipboard_empty", "empty clipboard not reported");
    }
    {
      const wchar_t *lines = L"https://example.invalid/a.epub\r\nfile:///C:/exr/missing.epub\r\n";
      memory = make_wide(lines, wcslen(lines));
      if (!clipboard_put(CF_UNICODETEXT, memory)) {
        report_fail("clipboard_text_lines", "SetClipboardData failed");
      } else {
        exr_drop_status status = exr_drop_windows_clipboard_request(EXR_DROP_ORIGIN_CLIPBOARD, NULL, &request);
        if (status != EXR_DROP_OK) {
          report_fail("clipboard_text_lines", exr_drop_status_name(status));
        } else {
          exr_drop_item item;
          exr_drop_request_info local;
          memset(&local, 0, sizeof(local));
          local.struct_size = sizeof(local);
          exr_drop_request_get_info(request, &local);
          memset(&item, 0, sizeof(item));
          item.struct_size = sizeof(item);
          exr_drop_request_get_item(request, 0, &item);
          report_expect("clipboard_text_lines",
              local.item_count == 2 && item.status == EXR_DROP_ITEM_REMOTE_URL, "CRLF text splits into entries");
          exr_drop_request_release(request);
          request = NULL;
        }
      }
    }
    {
      wchar_t units[16];
      size_t index = 0;
      exr_drop_status status;
      units[index++] = L'C';
      units[index++] = L':';
      units[index++] = L'\\';
      units[index++] = L'x';
      units[index++] = 0xD800;
      units[index++] = L'.';
      units[index++] = L't';
      memory = make_wide(units, index);
      status = clipboard_put(CF_UNICODETEXT, memory)
          ? exr_drop_windows_clipboard_request(EXR_DROP_ORIGIN_CLIPBOARD, NULL, &request)
          : EXR_DROP_PLATFORM;
      if (status != EXR_DROP_OK) {
        report_fail("clipboard_unpaired_surrogate", exr_drop_status_name(status));
      } else {
        exr_drop_item item;
        memset(&item, 0, sizeof(item));
        item.struct_size = sizeof(item);
        exr_drop_request_get_item(request, 0, &item);
        report_expect("clipboard_unpaired_surrogate", item.status == EXR_DROP_ITEM_BAD_ENCODING,
            "lone surrogate rejected as one item");
        exr_drop_request_release(request);
        request = NULL;
      }
    }
    {
      wchar_t units[64];
      static const wchar_t uri_text[] = L"https://example.invalid/x.epub";
      size_t text_length = wcslen(uri_text);
      exr_drop_status status;
      units[0] = (wchar_t)0xFEFF;
      memcpy(units + 1, uri_text, text_length * sizeof(wchar_t));
      units[text_length + 1] = 0;
      status = clipboard_put(CF_UNICODETEXT, make_wide(units, text_length + 1))
          ? exr_drop_windows_clipboard_request(EXR_DROP_ORIGIN_CLIPBOARD, NULL, &request)
          : EXR_DROP_PLATFORM;
      if (status != EXR_DROP_OK) {
        report_fail("clipboard_bom_skipped", exr_drop_status_name(status));
      } else {
        exr_drop_item item;
        memset(&item, 0, sizeof(item));
        item.struct_size = sizeof(item);
        exr_drop_request_get_item(request, 0, &item);
        report_expect("clipboard_bom_skipped", item.status == EXR_DROP_ITEM_REMOTE_URL,
            "leading BOM ignored");
        exr_drop_request_release(request);
        request = NULL;
      }
    }
    {
      const wchar_t *text = L"not a path at all";
      exr_drop_status status = clipboard_put(CF_UNICODETEXT, make_wide(text, wcslen(text)))
          ? exr_drop_windows_clipboard_request(EXR_DROP_ORIGIN_CLIPBOARD, NULL, &request)
          : EXR_DROP_PLATFORM;
      if (status != EXR_DROP_OK) {
        report_fail("clipboard_relative_text", exr_drop_status_name(status));
      } else {
        exr_drop_item item;
        memset(&item, 0, sizeof(item));
        item.struct_size = sizeof(item);
        exr_drop_request_get_item(request, 0, &item);
        report_expect("clipboard_relative_text", item.status == EXR_DROP_ITEM_INVALID,
            "relative text rejected");
        exr_drop_request_release(request);
        request = NULL;
      }
    }
    {
      wchar_t directory[MAX_PATH];
      wchar_t *paths[1];
      swprintf_s(directory, MAX_PATH, L"%s\\sub", g_root);
      paths[0] = directory;
      if (!clipboard_put(CF_HDROP, make_hdrop(paths, 1))) {
        report_fail("clipboard_directory", "SetClipboardData failed");
      } else {
        exr_drop_status status = exr_drop_windows_clipboard_request(EXR_DROP_ORIGIN_CLIPBOARD, NULL, &request);
        exr_drop_item item;
        memset(&item, 0, sizeof(item));
        item.struct_size = sizeof(item);
        if (status == EXR_DROP_OK) exr_drop_request_get_item(request, 0, &item);
        report_expect("clipboard_directory",
            status == EXR_DROP_OK && item.status == EXR_DROP_ITEM_DIRECTORY, "directory flagged, not recursed");
        exr_drop_request_release(request);
        request = NULL;
      }
    }
    {
      wchar_t ascii[MAX_PATH];
      wchar_t *paths[2];
      swprintf_s(ascii, MAX_PATH, L"%s\\a.txt", g_root);
      paths[0] = ascii;
      paths[1] = ascii;
      if (!clipboard_put(CF_HDROP, make_hdrop(paths, 2))) {
        report_fail("clipboard_duplicates", "SetClipboardData failed");
      } else {
        exr_drop_status status = exr_drop_windows_clipboard_request(EXR_DROP_ORIGIN_CLIPBOARD, NULL, &request);
        exr_drop_request_info local;
        memset(&local, 0, sizeof(local));
        local.struct_size = sizeof(local);
        if (status == EXR_DROP_OK) exr_drop_request_get_info(request, &local);
        report_expect("clipboard_duplicates",
            status == EXR_DROP_OK && local.item_count == 1 && local.duplicate_count == 1,
            "duplicate merged");
        exr_drop_request_release(request);
        request = NULL;
      }
    }
    {
      wchar_t *paths[300];
      wchar_t buffer[300][64];
      size_t index;
      HGLOBAL drop;
      for (index = 0; index < 300; index++) {
        swprintf_s(buffer[index], 64, L"C:\\exr-missing\\%03zu.epub", index);
        paths[index] = buffer[index];
      }
      drop = make_hdrop(paths, 300);
      if (!drop) {
        report_fail("clipboard_item_cap", "allocation failed");
      } else if (!clipboard_put(CF_HDROP, drop)) {
        report_fail("clipboard_item_cap", "SetClipboardData failed");
      } else {
        exr_drop_status status = exr_drop_windows_clipboard_request(EXR_DROP_ORIGIN_CLIPBOARD, NULL, &request);
        exr_drop_request_info local;
        memset(&local, 0, sizeof(local));
        local.struct_size = sizeof(local);
        if (status == EXR_DROP_OK) exr_drop_request_get_info(request, &local);
        report_expect("clipboard_item_cap",
            status == EXR_DROP_OK && local.item_count == 256 && local.overflow_count == 44 && local.truncated,
            "cap at 256 items with overflow recorded");
        exr_drop_request_release(request);
        request = NULL;
      }
    }
    {
      wchar_t *paths[1];
      size_t index;
      wchar_t *long_path = (wchar_t *)calloc(5200, sizeof(wchar_t));
      if (!long_path) {
        report_skip("clipboard_long_path", "allocation failed");
      } else {
        long_path[0] = L'C';
        long_path[1] = L':';
        long_path[2] = L'\\';
        for (index = 3; index < 5000; index++) long_path[index] = L'a';
        paths[0] = long_path;
        if (!clipboard_put(CF_HDROP, make_hdrop(paths, 1))) {
          report_fail("clipboard_long_path", "SetClipboardData failed");
        } else {
          exr_drop_status status = exr_drop_windows_clipboard_request(EXR_DROP_ORIGIN_CLIPBOARD, NULL, &request);
          exr_drop_item item;
          memset(&item, 0, sizeof(item));
          item.struct_size = sizeof(item);
          if (status == EXR_DROP_OK) exr_drop_request_get_item(request, 0, &item);
          report_expect("clipboard_long_path",
              status == EXR_DROP_OK && item.status == EXR_DROP_ITEM_TOO_LONG, "over-long path item");
          exr_drop_request_release(request);
          request = NULL;
        }
        free(long_path);
      }
    }
    {
      const wchar_t *lines = L"https://example.invalid/a.epub\r\nhttps://example.invalid/b.epub\r\nhttps://example.invalid/c.epub\r\n";
      int seen = 0;
      control.struct_size = sizeof(control);
      control.cancelled = cancel_after_one;
      control.context = &seen;
      request = NULL;
      if (!clipboard_put(CF_UNICODETEXT, make_wide(lines, wcslen(lines)))) {
        report_fail("clipboard_cancel", "SetClipboardData failed");
      } else {
        exr_drop_status status = exr_drop_windows_clipboard_request(EXR_DROP_ORIGIN_CLIPBOARD, &control, &request);
        report_expect("clipboard_cancel", status == EXR_DROP_CANCELLED && request == NULL,
            "clipboard read cancelled after the first entry");
        exr_drop_request_release(request);
        request = NULL;
        (void)cancelled;
      }
    }
    {
      wchar_t ascii[MAX_PATH];
      wchar_t *paths[1];
      char expected[600];
      swprintf_s(ascii, MAX_PATH, L"%s\\a.txt", g_root);
      paths[0] = ascii;
      WideCharToMultiByte(CP_UTF8, 0, ascii, -1, expected, (int)sizeof(expected), NULL, NULL);
      if (!clipboard_put(CF_HDROP, make_hdrop(paths, 1))) {
        report_fail("request_outlives_clipboard", "SetClipboardData failed");
      } else {
        exr_drop_status status = exr_drop_windows_clipboard_request(EXR_DROP_ORIGIN_CLIPBOARD, NULL, &request);
        int attempt;
        for (attempt = 0; attempt < 10; attempt++) {
          if (OpenClipboard(g_window)) break;
          Sleep(20);
        }
        EmptyClipboard();
        CloseClipboard();
        {
          exr_drop_item item;
          memset(&item, 0, sizeof(item));
          item.struct_size = sizeof(item);
          if (status == EXR_DROP_OK) exr_drop_request_get_item(request, 0, &item);
          report_expect("request_outlives_clipboard",
              status == EXR_DROP_OK && item.status == EXR_DROP_ITEM_FILE && item.path
                  && strcmp(item.path, expected) == 0,
              "path bytes survive clipboard emptying");
        }
        exr_drop_request_release(request);
        request = NULL;
      }
    }
  }

  /* ---- data objects --------------------------------------------------- */
  {
    wchar_t ascii[MAX_PATH];
    IDataObject *object;
    swprintf_s(ascii, MAX_PATH, L"%s\\a.txt", g_root);
    object = shell_data_object(g_root, ascii);
    report_expect("shell_data_object_created", object != NULL, "SHCreateDataObject with a real file");
    if (object) {
      capture_reset(&state);
      effect = 0;
      if (exr_drop_windows_deliver_drop(target, object, &effect) == EXR_DROP_OK) {
        report_expect("shell_drop_delivers_file",
            state.calls == 1 && state.status == EXR_DROP_OK && state.items == 1
                && state.first_status == EXR_DROP_ITEM_FILE && effect == DROPEFFECT_COPY,
            state.first_path);
      } else {
        report_fail("shell_drop_delivers_file", "deliver refused");
      }
      object->lpVtbl->Release(object);
    }
  }
  {
    wchar_t ascii[MAX_PATH];
    wchar_t unicode[MAX_PATH];
    wchar_t *paths[2];
    IDataObject *object;
    swprintf_s(ascii, MAX_PATH, L"%s\\a.txt", g_root);
    swprintf_s(unicode, MAX_PATH, L"%s\\exr drop \x4E2D\x6587.epub", g_root);
    paths[0] = ascii;
    paths[1] = unicode;
    object = test_object_create(CF_HDROP, make_hdrop(paths, 2));
    capture_reset(&state);
    effect = 0;
    if (object && exr_drop_windows_deliver_drop(target, object, &effect) == EXR_DROP_OK)
      report_expect("object_hdrop_delivers", state.calls == 1 && state.items == 2
          && state.first_status == EXR_DROP_ITEM_FILE && effect == DROPEFFECT_COPY, "two files");
    else
      report_fail("object_hdrop_delivers", "deliver failed");
    if (object) object->lpVtbl->Release(object);
  }
  {
    const wchar_t *text = L"https://example.invalid/z.epub";
    IDataObject *object = test_object_create(CF_UNICODETEXT, make_wide(text, wcslen(text)));
    capture_reset(&state);
    effect = 0;
    if (object && exr_drop_windows_deliver_drop(target, object, &effect) == EXR_DROP_OK)
      report_expect("object_unicode_text_delivers",
          state.calls == 1 && state.first_status == EXR_DROP_ITEM_REMOTE_URL, "remote URL item");
    else
      report_fail("object_unicode_text_delivers", "deliver failed");
    if (object) object->lpVtbl->Release(object);
  }
  {
    IDataObject *object = test_object_create(file_group_format(),
        make_file_group(L"promised.epub"));
    capture_reset(&state);
    effect = 0;
    if (object && exr_drop_windows_deliver_drop(target, object, &effect) == EXR_DROP_OK)
      report_expect("object_virtual_descriptor",
          state.calls == 1 && state.first_status == EXR_DROP_ITEM_VIRTUAL, "promised file reported as virtual");
    else
      report_fail("object_virtual_descriptor", "deliver failed");
    if (object) object->lpVtbl->Release(object);
  }
  {
    IDataObject *object = test_object_create((CLIPFORMAT)RegisterClipboardFormatW(L"EXRProbeUnsupported"),
        make_wide(L"x", 1));
    capture_reset(&state);
    effect = DROPEFFECT_COPY;
    if (object && exr_drop_windows_deliver_drop(target, object, &effect) == EXR_DROP_OK)
      report_expect("object_unsupported_format",
          state.calls == 1 && state.status == EXR_DROP_UNSUPPORTED && state.request == NULL
              && effect == DROPEFFECT_NONE,
          "unsupported format reported, no request");
    else
      report_fail("object_unsupported_format", "deliver failed");
    if (object) object->lpVtbl->Release(object);
  }
  {
    wchar_t ascii[MAX_PATH];
    wchar_t *paths[1];
    IDataObject *object;
    swprintf_s(ascii, MAX_PATH, L"%s\\a.txt", g_root);
    paths[0] = ascii;
    object = test_object_create(CF_HDROP, make_hdrop(paths, 1));
    capture_reset(&state);
    state.hold_request = 1;
    effect = 0;
    if (object && exr_drop_windows_deliver_drop(target, object, &effect) == EXR_DROP_OK) {
      exr_drop_item item;
      memset(&item, 0, sizeof(item));
      item.struct_size = sizeof(item);
      object->lpVtbl->Release(object); /* data object gone before the request is read */
      if (state.request) exr_drop_request_get_item(state.request, 0, &item);
      report_expect("request_outlives_data_object",
          state.request && item.status == EXR_DROP_ITEM_FILE && item.path && strcmp(item.path, state.first_path) == 0,
          "path bytes survive the data object");
      exr_drop_request_release(state.request);
      state.request = NULL;
      state.hold_request = 0;
    } else {
      report_fail("request_outlives_data_object", "deliver failed");
      if (object) object->lpVtbl->Release(object);
      state.hold_request = 0;
    }
  }

  /* ---- malformed platform buffers ------------------------------------- */
  {
    static const unsigned char raw[4] = {'A', 0, 'B', 0}; /* two units, no terminator */
    deliver_object(&state, "reject_text_without_terminator", CF_UNICODETEXT, make_raw(raw, sizeof(raw)),
        EXR_DROP_PLATFORM, (exr_drop_item_status)0, 0);
  }
  {
    static const unsigned char raw[5] = {'A', 0, 'B', 0, 'C'}; /* odd byte count */
    deliver_object(&state, "reject_text_odd_bytes", CF_UNICODETEXT, make_raw(raw, sizeof(raw)),
        EXR_DROP_PLATFORM, (exr_drop_item_status)0, 0);
  }
  {
    static const unsigned char raw[1] = {'A'}; /* smaller than one UTF-16 unit */
    deliver_object(&state, "reject_text_short_global", CF_UNICODETEXT, make_raw(raw, sizeof(raw)),
        EXR_DROP_PLATFORM, (exr_drop_item_status)0, 0);
  }
  {
    static const wchar_t text[] = L"https://e.x"; /* 11 units plus the terminator, nothing spare */
    deliver_object(&state, "accept_text_exact_terminator", CF_UNICODETEXT, make_raw(text, sizeof(text)),
        EXR_DROP_OK, EXR_DROP_ITEM_REMOTE_URL, 1);
  }
  {
    static const unsigned char raw[4] = {1, 0, 0, 0}; /* cItems without a descriptor */
    deliver_object(&state, "reject_file_group_short_header", file_group_format(),
        make_raw(raw, sizeof(raw)), EXR_DROP_PLATFORM, (exr_drop_item_status)0, 0);
  }
  {
    HGLOBAL memory = GlobalAlloc(GHND, sizeof(FILEGROUPDESCRIPTORW));
    FILEGROUPDESCRIPTORW *group = memory ? (FILEGROUPDESCRIPTORW *)GlobalLock(memory) : NULL;
    if (!group) {
      report_fail("reject_file_group_beyond_allocation", "fixture allocation failed");
      if (memory) GlobalFree(memory);
    } else {
      group->cItems = 3; /* promises three, the allocation holds one */
      wcsncpy_s(group->fgd[0].cFileName, 260, L"a.epub", _TRUNCATE);
      GlobalUnlock(memory);
      deliver_object(&state, "reject_file_group_beyond_allocation",
          file_group_format(), memory, EXR_DROP_PLATFORM, (exr_drop_item_status)0, 0);
    }
  }
  {
    HGLOBAL memory = GlobalAlloc(GHND, sizeof(FILEGROUPDESCRIPTORW));
    FILEGROUPDESCRIPTORW *group = memory ? (FILEGROUPDESCRIPTORW *)GlobalLock(memory) : NULL;
    if (!group) {
      report_fail("reject_file_group_extreme_count", "fixture allocation failed");
      if (memory) GlobalFree(memory);
    } else {
      group->cItems = 0xFFFFFFFFu;
      wcsncpy_s(group->fgd[0].cFileName, 260, L"a.epub", _TRUNCATE);
      GlobalUnlock(memory);
      deliver_object(&state, "reject_file_group_extreme_count",
          file_group_format(), memory, EXR_DROP_PLATFORM, (exr_drop_item_status)0, 0);
    }
  }
  {
    HGLOBAL memory = GlobalAlloc(GHND, sizeof(FILEGROUPDESCRIPTORW));
    FILEGROUPDESCRIPTORW *group = memory ? (FILEGROUPDESCRIPTORW *)GlobalLock(memory) : NULL;
    if (!group) {
      report_fail("reject_file_group_empty", "fixture allocation failed");
      if (memory) GlobalFree(memory);
    } else {
      group->cItems = 0;
      GlobalUnlock(memory);
      deliver_object(&state, "reject_file_group_empty", file_group_format(),
          memory, EXR_DROP_UNSUPPORTED, (exr_drop_item_status)0, 0);
    }
  }
  {
    static const unsigned char raw[4] = {0x18, 0, 0, 0}; /* shorter than DROPFILES */
    deliver_object(&state, "reject_hdrop_short_header", CF_HDROP, make_raw(raw, sizeof(raw)),
        EXR_DROP_PLATFORM, (exr_drop_item_status)0, 0);
  }
  deliver_object(&state, "reject_hdrop_pfiles_out_of_range", CF_HDROP,
      make_hdrop_raw((DWORD)(sizeof(DROPFILES) + 64), FALSE, NULL, 0), EXR_DROP_PLATFORM,
      (exr_drop_item_status)0, 0);
  deliver_object(&state, "reject_hdrop_pfiles_before_header", CF_HDROP, make_hdrop_raw(4, FALSE, NULL, 0),
      EXR_DROP_PLATFORM, (exr_drop_item_status)0, 0);
  {
    static const wchar_t list[] = L"C:\\a.txt"; /* own terminator only, no empty entry */
    deliver_object(&state, "reject_hdrop_wide_unterminated", CF_HDROP,
        make_hdrop_raw((DWORD)sizeof(DROPFILES), TRUE, list, sizeof(list)), EXR_DROP_PLATFORM,
        (exr_drop_item_status)0, 0);
  }
  {
    static const char list[] = "C:\\a.txt"; /* own terminator only, no empty entry */
    deliver_object(&state, "reject_hdrop_ansi_unterminated", CF_HDROP,
        make_hdrop_raw((DWORD)sizeof(DROPFILES), FALSE, list, sizeof(list)), EXR_DROP_PLATFORM,
        (exr_drop_item_status)0, 0);
  }
  {
    static const char list[] = "C:\\a.txt\0"; /* string plus the terminating empty entry */
    HGLOBAL memory = make_hdrop_raw((DWORD)sizeof(DROPFILES), FALSE, list, sizeof(list));
    deliver_object(&state, "accept_hdrop_ansi_list", CF_HDROP, memory, EXR_DROP_OK, EXR_DROP_ITEM_MISSING, 1);
  }
  {
    static const unsigned char list[5] = {'A', 0, 'B', 0x33, 0x01}; /* truncated second unit */
    deliver_object(&state, "reject_hdrop_wide_truncated_unit", CF_HDROP,
        make_hdrop_raw((DWORD)sizeof(DROPFILES), TRUE, list, sizeof(list)), EXR_DROP_PLATFORM,
        (exr_drop_item_status)0, 0);
  }
  if (g_clipboard_ok) {
    /* The clipboard normalises CF_UNICODETEXT (it hands back a terminated
       copy), so the structural negative here is an HDROP whose pFiles leaves
       the allocation: the platform stores that verbatim. */
    HGLOBAL fixture = make_hdrop_raw((DWORD)(sizeof(DROPFILES) + 64), FALSE, NULL, 0);
    if (!fixture) {
      report_fail("reject_clipboard_hdrop_invalid_pfiles", "fixture allocation failed");
    } else if (!clipboard_put(CF_HDROP, fixture)) {
      report_fail("reject_clipboard_hdrop_invalid_pfiles", "SetClipboardData failed");
    } else {
      exr_drop_request *rejected = NULL;
      exr_drop_status status = exr_drop_windows_clipboard_request(EXR_DROP_ORIGIN_CLIPBOARD, NULL, &rejected);
      report_expect("reject_clipboard_hdrop_invalid_pfiles",
          status == EXR_DROP_PLATFORM && rejected == NULL, exr_drop_status_name(status));
      exr_drop_request_release(rejected);
    }
  } else {
    report_skip_clipboard("reject_clipboard_hdrop_invalid_pfiles");
  }

  /* ---- lifecycle ----------------------------------------------------- */
  {
    detach_job job;
    HANDLE thread;
    job.target = target;
    job.status = -1;
    thread = CreateThread(NULL, 0, detach_worker, &job, 0, NULL);
    if (!thread) {
      report_skip("detach_from_other_thread", "thread creation failed");
    } else {
      WaitForSingleObject(thread, INFINITE);
      CloseHandle(thread);
      report_expect("detach_from_other_thread", job.status == (int)EXR_DROP_WRONG_THREAD,
          "wrong thread refused, target unchanged");
    }
  }
  {
    HWND callback_window = make_window();
    exr_drop_windows_target *victim = NULL;
    capture inner;
    memset(&inner, 0, sizeof(inner));
    inner.destroy_in_callback = 1;
    options.context = &inner;
    if (callback_window && exr_drop_windows_attach(callback_window, &options, &victim) == EXR_DROP_OK) {
      inner.target = victim;
      {
        wchar_t ascii[MAX_PATH];
        wchar_t *paths[1];
        IDataObject *object;
        swprintf_s(ascii, MAX_PATH, L"%s\\a.txt", g_root);
        paths[0] = ascii;
        object = test_object_create(CF_HDROP, make_hdrop(paths, 1));
        effect = 0;
        exr_drop_windows_deliver_drop(victim, object, &effect);
        object->lpVtbl->Release(object);
      }
      report_expect("detach_inside_callback",
          inner.calls == 1 && inner.destroy_status == EXR_DROP_OK && inner.target == NULL,
          "target destroyed from its own callback without OLE use-after-free");
    } else {
      report_fail("detach_inside_callback", "attach failed");
    }
    if (callback_window) DestroyWindow(callback_window);
    options.context = &state;
  }
  {
    HWND spare = make_window();
    exr_drop_windows_target *victim = NULL;
    if (spare && exr_drop_windows_attach(spare, &options, &victim) == EXR_DROP_OK) {
      DestroyWindow(spare); /* WM_DESTROY revokes the OLE registration and drops OLE's reference */
      report_expect("window_destroyed_before_detach", exr_drop_windows_detach(victim) == EXR_DROP_OK,
          "detach after DestroyWindow frees the last reference");
    } else {
      report_fail("window_destroyed_before_detach", "attach failed");
    }
  }
  {
    HWND spare = make_window();
    exr_drop_windows_target *victim = NULL;
    LONG_PTR before = spare ? GetWindowLongPtrW(spare, GWLP_WNDPROC) : 0;
    LONG_PTR during = 0, after = 0;
    if (!spare) {
      report_fail("window_proc_restored_after_detach", "window unavailable");
    } else if (exr_drop_windows_attach(spare, &options, &victim) != EXR_DROP_OK) {
      report_fail("window_proc_restored_after_detach", "attach failed");
    } else {
      during = GetWindowLongPtrW(spare, GWLP_WNDPROC);
      exr_drop_windows_detach(victim);
      after = GetWindowLongPtrW(spare, GWLP_WNDPROC);
      report_expect("window_proc_restored_after_detach", during != before && after == before,
          "one transparent subclass installed and restored");
      DestroyWindow(spare);
    }
  }
  {
#ifdef EXR_DESKTOP_DROP_TEST_HOOKS
    size_t live_before = exr_drop_windows_test_live_targets();
    HWND spare = make_window();
    exr_drop_windows_target *victim = NULL;
    if (!spare) {
      report_fail("com_object_reclaimed_after_window_destroy", "window unavailable");
    } else if (exr_drop_windows_attach(spare, &options, &victim) != EXR_DROP_OK) {
      report_fail("com_object_reclaimed_after_window_destroy", "attach failed");
      DestroyWindow(spare);
    } else {
      size_t live_during = exr_drop_windows_test_live_targets();
      exr_drop_status status;
      size_t live_after;
      char detail[160];
      DestroyWindow(spare);
      status = exr_drop_windows_detach(victim);
      live_after = exr_drop_windows_test_live_targets();
      snprintf(detail, sizeof(detail), "live %zu -> %zu -> %zu, detach=%s", live_before, live_during,
          live_after, exr_drop_status_name(status));
      report_expect("com_object_reclaimed_after_window_destroy",
          live_during == live_before + 1 && status == EXR_DROP_OK && live_after == live_before, detail);
    }
#else
    report_skip("com_object_reclaimed_after_window_destroy",
        "requires the EXR_DESKTOP_DROP_TEST_HOOKS build");
#endif
  }
  {
    DWORD local_effect = DROPEFFECT_COPY;
    report_expect("deliver_null_object", exr_drop_windows_deliver_drop(target, NULL, &local_effect)
            == EXR_DROP_ARGUMENT,
        "NULL data object refused");
  }
  report_expect("detach_owner_thread", exr_drop_windows_detach(target) == EXR_DROP_OK, "final detach");
  target = NULL;

  if (g_window) DestroyWindow(g_window);
  OleUninitialize();
  return report_summary("windows");
}
