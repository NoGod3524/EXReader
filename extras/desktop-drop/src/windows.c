/* SPDX-License-Identifier: MIT */
#include "internal.h"
#include "exr_desktop_drop_windows.h"
#include <shlobj.h>
#include <stddef.h>
#include <stdlib.h>
#include <string.h>
#include <wchar.h>

#ifdef EXR_DESKTOP_DROP_TEST_HOOKS
static volatile LONG win_live_targets;
#endif

typedef struct win_target {
  struct exr_drop_target base; /* must be first */
  IDropTarget iface;
  volatile LONG refs;
  HWND window;
  DWORD owner_tid;
  WNDPROC original_proc;
  int registered;
  int subclassed;
  int can_drop;
} win_target;

#define WIN_FROM_IFACE(p) ((win_target *)((char *)(p) - offsetof(win_target, iface)))

static const wchar_t win_property[] = L"EXReaderDesktopDropTarget";

static int win_owner_thread(const struct exr_drop_target *base) {
  const win_target *target = (const win_target *)base;
  return GetCurrentThreadId() == target->owner_tid;
}

static void win_release_object(struct exr_drop_target *base);

/* Every read below is bounded by the real allocation the platform handed us:
   the 1 MiB payload budget is a product limit, never a buffer size. */
static size_t global_extent(HGLOBAL handle) {
  SIZE_T size;
  if (!handle) return 0;
  size = GlobalSize(handle);
  return (size_t)size;
}

/* ---- payload extraction --------------------------------------------- */
static CLIPFORMAT file_group_format(void) {
  /* CFSTR_FILEDESCRIPTORW is a narrow literal in this SDK; the atom is wide. */
  return (CLIPFORMAT)RegisterClipboardFormatW(L"FileGroupDescriptorW");
}

static exr_drop_status request_from_unicode_text(HGLOBAL handle, exr_drop_origin origin,
    const exr_drop_control *control, exr_drop_request **out) {
  drop_builder builder;
  const wchar_t *text;
  size_t capacity, units;
  exr_drop_status status;
  *out = NULL;
  capacity = global_extent(handle) / sizeof(wchar_t); /* an odd trailing byte is unusable */
  if (capacity == 0) return EXR_DROP_PLATFORM;
  text = (const wchar_t *)GlobalLock(handle);
  if (!text) return EXR_DROP_PLATFORM;
  units = wcsnlen(text, capacity);
  if (units == capacity) {
    /* No terminator inside the allocation: reading on would leave the buffer. */
    GlobalUnlock(handle);
    return EXR_DROP_PLATFORM;
  }
  if (units > EXR_DROP_MAX_INPUT_BYTES / 2u) {
    GlobalUnlock(handle);
    return EXR_DROP_TOO_LARGE;
  }
  drop_builder_init(&builder, origin, control);
  drop_utf16_split((const uint16_t *)(const void *)text, units, EXR_DROP_UTF16_LINES, &builder);
  status = drop_builder_finish(&builder, out);
  GlobalUnlock(handle);
  return status;
}

static exr_drop_status request_from_file_group(HGLOBAL handle, exr_drop_origin origin,
    const exr_drop_control *control, exr_drop_request **out) {
  const FILEGROUPDESCRIPTORW *group;
  drop_builder builder;
  size_t bytes, available;
  UINT declared, index;
  exr_drop_status status;
  *out = NULL;
  bytes = global_extent(handle);
  if (bytes < sizeof(FILEGROUPDESCRIPTORW)) return EXR_DROP_PLATFORM;
  group = (const FILEGROUPDESCRIPTORW *)GlobalLock(handle);
  if (!group) return EXR_DROP_PLATFORM;
  declared = group->cItems;
  if (declared == 0) {
    GlobalUnlock(handle);
    return EXR_DROP_UNSUPPORTED;
  }
  /* The header may promise more descriptors than the allocation holds. */
  available = (bytes - offsetof(FILEGROUPDESCRIPTORW, fgd)) / sizeof(FILEDESCRIPTORW);
  if ((size_t)declared > available) {
    GlobalUnlock(handle);
    return EXR_DROP_PLATFORM;
  }
  drop_builder_init(&builder, origin, control);
  for (index = 0; index < declared && !drop_builder_stopped(&builder); index++)
    drop_add_virtual(&builder, (const uint16_t *)(const void *)group->fgd[index].cFileName,
        wcsnlen(group->fgd[index].cFileName, 260));
  status = drop_builder_finish(&builder, out);
  GlobalUnlock(handle);
  if (status == EXR_DROP_EMPTY) status = EXR_DROP_UNSUPPORTED;
  return status;
}

/* An HDROP list must be complete inside its allocation before the shell parses
   it: header present, pFiles in range, and a wide or ANSI list terminated by an
   empty entry inside the buffer. Wide units are read bytewise so a truncated
   code unit can never be read past the end. */
typedef struct {
  UINT count;
  size_t units;
} hdrop_scan;

static exr_drop_status hdrop_scan_list(HGLOBAL handle, hdrop_scan *scan) {
  const DROPFILES *header;
  const unsigned char *bytes_from;
  size_t bytes, offset, capacity, index;
  exr_drop_status status = EXR_DROP_OK;
  memset(scan, 0, sizeof(*scan));
  bytes = global_extent(handle);
  if (bytes < sizeof(DROPFILES)) return EXR_DROP_PLATFORM;
  header = (const DROPFILES *)GlobalLock(handle);
  if (!header) return EXR_DROP_PLATFORM;
  offset = (size_t)header->pFiles;
  if (offset < sizeof(DROPFILES) || offset > bytes) {
    GlobalUnlock(handle);
    return EXR_DROP_PLATFORM;
  }
  bytes_from = (const unsigned char *)(const void *)header + offset;
  if (header->fWide) {
    capacity = (bytes - offset) / sizeof(wchar_t);
    index = 0;
    for (;;) {
      size_t start = index;
      while (index < capacity
          && (bytes_from[index * 2] != 0 || bytes_from[index * 2 + 1] != 0))
        index++;
      if (index >= capacity) { status = EXR_DROP_PLATFORM; break; }
      if (index == start) break; /* empty entry terminates the list */
      scan->count++;
      scan->units += (index - start) + 1;
      if (scan->units > EXR_DROP_MAX_INPUT_BYTES / 2u) { status = EXR_DROP_TOO_LARGE; break; }
      index++;
    }
  } else {
    capacity = bytes - offset;
    index = 0;
    for (;;) {
      size_t start = index;
      while (index < capacity && bytes_from[index] != 0) index++;
      if (index >= capacity) { status = EXR_DROP_PLATFORM; break; }
      if (index == start) break;
      scan->count++;
      scan->units += (index - start) + 1;
      if (scan->units > EXR_DROP_MAX_INPUT_BYTES / 2u) { status = EXR_DROP_TOO_LARGE; break; }
      index++;
    }
  }
  GlobalUnlock(handle);
  return status;
}

exr_drop_status exr_drop_windows_request_from_hdrop(HDROP drop, exr_drop_origin origin,
    const exr_drop_control *control, exr_drop_request **out) {
  drop_builder builder;
  hdrop_scan scan;
  UINT index;
  exr_drop_status status;
  if (!out) return EXR_DROP_ARGUMENT;
  *out = NULL;
  if (!drop) return EXR_DROP_ARGUMENT;
  if (origin < EXR_DROP_ORIGIN_DROP || origin > EXR_DROP_ORIGIN_TEXT) return EXR_DROP_ARGUMENT;
  if (control && control->struct_size != sizeof(*control)) return EXR_DROP_ARGUMENT;
  status = hdrop_scan_list((HGLOBAL)drop, &scan);
  if (status != EXR_DROP_OK) return status;
  if (scan.count == 0) return EXR_DROP_EMPTY;
  drop_builder_init(&builder, origin, control);
  for (index = 0; index < scan.count && !drop_builder_stopped(&builder); index++) {
    UINT length = DragQueryFileW(drop, index, NULL, 0);
    wchar_t *path;
    if (length == 0 || length >= EXR_DROP_MAX_INPUT_BYTES / 2u) {
      builder.failure = EXR_DROP_PLATFORM;
      break;
    }
    path = (wchar_t *)malloc(((size_t)length + 1u) * sizeof(wchar_t));
    if (!path) { builder.failure = EXR_DROP_NO_MEMORY; break; }
    if (DragQueryFileW(drop, index, path, length + 1u) != length) {
      free(path);
      builder.failure = EXR_DROP_PLATFORM;
      break;
    }
    drop_add_utf16_entry(&builder, (const uint16_t *)(const void *)path, length);
    free(path);
  }
  return drop_builder_finish(&builder, out);
}

static exr_drop_status get_hglobal(IDataObject *object, CLIPFORMAT format, STGMEDIUM *medium) {
  FORMATETC wanted;
  HRESULT result;
  memset(&wanted, 0, sizeof(wanted));
  wanted.cfFormat = format;
  wanted.dwAspect = DVASPECT_CONTENT;
  wanted.lindex = -1;
  wanted.tymed = TYMED_HGLOBAL;
  result = object->lpVtbl->GetData(object, &wanted, medium);
  if (FAILED(result) || medium->tymed != TYMED_HGLOBAL || !medium->hGlobal) {
    if (SUCCEEDED(result)) ReleaseStgMedium(medium);
    return EXR_DROP_UNSUPPORTED;
  }
  return EXR_DROP_OK;
}

exr_drop_status exr_drop_windows_request_from_data_object(IDataObject *object,
    exr_drop_origin origin, const exr_drop_control *control, exr_drop_request **out) {
  STGMEDIUM medium;
  CLIPFORMAT group;
  if (!out) return EXR_DROP_ARGUMENT;
  *out = NULL;
  if (!object) return EXR_DROP_ARGUMENT;
  if (origin < EXR_DROP_ORIGIN_DROP || origin > EXR_DROP_ORIGIN_TEXT) return EXR_DROP_ARGUMENT;
  if (control && control->struct_size != sizeof(*control)) return EXR_DROP_ARGUMENT;
  if (get_hglobal(object, CF_HDROP, &medium) == EXR_DROP_OK) {
    exr_drop_status status = exr_drop_windows_request_from_hdrop((HDROP)medium.hGlobal, origin, control, out);
    ReleaseStgMedium(&medium);
    return status;
  }
  if (get_hglobal(object, CF_UNICODETEXT, &medium) == EXR_DROP_OK) {
    exr_drop_status status = request_from_unicode_text(medium.hGlobal, origin, control, out);
    ReleaseStgMedium(&medium);
    return status;
  }
  group = file_group_format();
  if (group && get_hglobal(object, group, &medium) == EXR_DROP_OK) {
    exr_drop_status status = request_from_file_group(medium.hGlobal, origin, control, out);
    ReleaseStgMedium(&medium);
    return status;
  }
  return EXR_DROP_UNSUPPORTED;
}

exr_drop_status exr_drop_windows_clipboard_request(exr_drop_origin origin,
    const exr_drop_control *control, exr_drop_request **out) {
  exr_drop_status status;
  int attempt;
  if (!out) return EXR_DROP_ARGUMENT;
  *out = NULL;
  if (origin < EXR_DROP_ORIGIN_DROP || origin > EXR_DROP_ORIGIN_TEXT) return EXR_DROP_ARGUMENT;
  if (control && control->struct_size != sizeof(*control)) return EXR_DROP_ARGUMENT;
  for (attempt = 0; attempt < 8; attempt++) {
    if (OpenClipboard(NULL)) break;
    Sleep(10);
  }
  if (attempt == 8) return EXR_DROP_PLATFORM;
  if (IsClipboardFormatAvailable(CF_HDROP)) {
    HGLOBAL handle = GetClipboardData(CF_HDROP);
    status = handle ? exr_drop_windows_request_from_hdrop((HDROP)handle, origin, control, out)
                    : EXR_DROP_PLATFORM;
  } else if (IsClipboardFormatAvailable(CF_UNICODETEXT)) {
    HGLOBAL handle = GetClipboardData(CF_UNICODETEXT);
    status = handle ? request_from_unicode_text(handle, origin, control, out) : EXR_DROP_PLATFORM;
  } else {
    status = EXR_DROP_EMPTY;
  }
  CloseClipboard();
  return status;
}

/* ---- lifecycle ------------------------------------------------------- */
/* Revoking drops OLE's reference; it must happen while the window is valid. */
static void win_revoke(win_target *target) {
  HWND window = target->window;
  if (!target->registered) return;
  target->registered = 0;
  if (window && IsWindow(window)) RevokeDragDrop(window);
}

static void win_restore_window(win_target *target) {
  HWND window = target->window;
  if (target->subclassed) {
    target->subclassed = 0;
    if (window && IsWindow(window)) {
      if (target->original_proc) SetWindowLongPtrW(window, GWLP_WNDPROC, (LONG_PTR)target->original_proc);
      RemovePropW(window, win_property);
    }
  }
  target->original_proc = NULL;
}

static LRESULT CALLBACK win_window_proc(HWND window, UINT message, WPARAM wparam, LPARAM lparam) {
  win_target *target = (win_target *)GetPropW(window, win_property);
  WNDPROC original = target ? target->original_proc : NULL;
  if (message == WM_DESTROY && target) win_revoke(target); /* frees OLE's reference in time */
  if (message == WM_NCDESTROY && target) {
    target->subclassed = 0;
    target->original_proc = NULL;
    target->window = NULL;
    RemovePropW(window, win_property);
    if (original) SetWindowLongPtrW(window, GWLP_WNDPROC, (LONG_PTR)original);
  }
  if (original) return CallWindowProcW(original, window, message, wparam, lparam);
  return DefWindowProcW(window, message, wparam, lparam);
}

/* ---- COM object ------------------------------------------------------ */
static HRESULT STDMETHODCALLTYPE win_QueryInterface(IDropTarget *iface, REFIID iid, void **out) {
  win_target *target = WIN_FROM_IFACE(iface);
  if (!out) return E_POINTER;
  if (IsEqualIID(iid, &IID_IUnknown) || IsEqualIID(iid, &IID_IDropTarget)) {
    InterlockedIncrement(&target->refs);
    *out = iface;
    return S_OK;
  }
  *out = NULL;
  return E_NOINTERFACE;
}
static ULONG STDMETHODCALLTYPE win_AddRef(IDropTarget *iface) {
  return (ULONG)InterlockedIncrement(&WIN_FROM_IFACE(iface)->refs);
}
static ULONG STDMETHODCALLTYPE win_Release(IDropTarget *iface) {
  win_target *target = WIN_FROM_IFACE(iface);
  LONG left = InterlockedDecrement(&target->refs);
  if (left == 0) {
#ifdef EXR_DESKTOP_DROP_TEST_HOOKS
    InterlockedDecrement(&win_live_targets);
#endif
    free(target);
  }
  return (ULONG)left;
}

static int win_accepts(IDataObject *object) {
  FORMATETC wanted;
  CLIPFORMAT group = file_group_format();
  if (!object) return 0;
  memset(&wanted, 0, sizeof(wanted));
  wanted.dwAspect = DVASPECT_CONTENT;
  wanted.lindex = -1;
  wanted.tymed = TYMED_HGLOBAL;
  wanted.cfFormat = CF_HDROP;
  if (object->lpVtbl->QueryGetData(object, &wanted) == S_OK) return 1;
  wanted.cfFormat = CF_UNICODETEXT;
  if (object->lpVtbl->QueryGetData(object, &wanted) == S_OK) return 1;
  if (group) {
    wanted.cfFormat = group;
    if (object->lpVtbl->QueryGetData(object, &wanted) == S_OK) return 1;
  }
  return 0;
}

static void win_deliver(win_target *target, IDataObject *object, DWORD *effect) {
  exr_drop_request *request = NULL;
  exr_drop_status status;
  if (effect) *effect = DROPEFFECT_NONE;
  if (!target || target->base.dead) return;
  status = exr_drop_windows_request_from_data_object(object, EXR_DROP_ORIGIN_DROP,
      drop_target_control(&target->base), &request);
  if (effect && status == EXR_DROP_OK) *effect = DROPEFFECT_COPY;
  drop_target_deliver(&target->base, status, request);
}

static HRESULT STDMETHODCALLTYPE win_DragEnter(IDropTarget *iface, IDataObject *object, DWORD keys,
    POINTL point, DWORD *effect) {
  win_target *target = WIN_FROM_IFACE(iface);
  (void)keys;
  (void)point;
  target->can_drop = win_accepts(object);
  if (effect) *effect = target->can_drop ? DROPEFFECT_COPY : DROPEFFECT_NONE;
  return S_OK;
}
static HRESULT STDMETHODCALLTYPE win_DragOver(IDropTarget *iface, DWORD keys, POINTL point, DWORD *effect) {
  win_target *target = WIN_FROM_IFACE(iface);
  (void)keys;
  (void)point;
  if (effect) *effect = target->can_drop ? DROPEFFECT_COPY : DROPEFFECT_NONE;
  return S_OK;
}
static HRESULT STDMETHODCALLTYPE win_DragLeave(IDropTarget *iface) {
  WIN_FROM_IFACE(iface)->can_drop = 0;
  return S_OK;
}
static HRESULT STDMETHODCALLTYPE win_Drop(IDropTarget *iface, IDataObject *object, DWORD keys,
    POINTL point, DWORD *effect) {
  win_target *target = WIN_FROM_IFACE(iface);
  (void)keys;
  (void)point;
  target->can_drop = 0;
  win_deliver(target, object, effect);
  return S_OK;
}

/* Not const: the C form of IDropTarget::lpVtbl is a plain pointer. */
static IDropTargetVtbl win_vtbl = {win_QueryInterface, win_AddRef, win_Release, win_DragEnter,
    win_DragOver, win_DragLeave, win_Drop};

static void win_release_object(struct exr_drop_target *base) {
  win_target *target = (win_target *)base;
  win_restore_window(target);
  win_revoke(target);
  win_Release(&target->iface);
}

exr_drop_status exr_drop_windows_attach(HWND window, const exr_drop_target_options *options,
    exr_drop_windows_target **target) {
  win_target *created;
  HRESULT result;
  DWORD owner;
  if (!target) return EXR_DROP_ARGUMENT;
  *target = NULL;
  if (!window || !drop_target_options_valid(options)) return EXR_DROP_ARGUMENT;
  owner = GetWindowThreadProcessId(window, NULL);
  if (!owner || owner != GetCurrentThreadId()) return EXR_DROP_PLATFORM;
  created = (win_target *)calloc(1, sizeof(*created));
  if (!created) return EXR_DROP_NO_MEMORY;
#ifdef EXR_DESKTOP_DROP_TEST_HOOKS
  InterlockedIncrement(&win_live_targets);
#endif
  drop_target_init(&created->base, options, win_owner_thread, win_release_object);
  created->iface.lpVtbl = &win_vtbl;
  created->refs = 1;
  created->window = window;
  created->owner_tid = owner;
  result = RegisterDragDrop(window, &created->iface);
  if (FAILED(result)) {
    win_Release(&created->iface);
    return EXR_DROP_PLATFORM;
  }
  created->registered = 1;
  SetPropW(window, win_property, created);
  SetLastError(0);
  created->original_proc = (WNDPROC)SetWindowLongPtrW(window, GWLP_WNDPROC, (LONG_PTR)win_window_proc);
  if (!created->original_proc && GetLastError() != 0) {
    RemovePropW(window, win_property);
    win_revoke(created);
    win_Release(&created->iface);
    return EXR_DROP_PLATFORM;
  }
  created->subclassed = 1;
  *target = (exr_drop_windows_target *)created;
  return EXR_DROP_OK;
}

exr_drop_status exr_drop_windows_detach(exr_drop_windows_target *target) {
  return exr_drop_target_destroy((exr_drop_target *)target);
}

exr_drop_status exr_drop_windows_deliver_drop(exr_drop_windows_target *target, IDataObject *object,
    DWORD *effect) {
  win_target *concrete = (win_target *)target;
  if (!concrete || !object) return EXR_DROP_ARGUMENT;
  if (!win_owner_thread(&concrete->base)) return EXR_DROP_WRONG_THREAD;
  if (concrete->base.dead) return EXR_DROP_ARGUMENT;
  win_deliver(concrete, object, effect);
  return EXR_DROP_OK;
}

#ifdef EXR_DESKTOP_DROP_TEST_HOOKS
size_t exr_drop_windows_test_live_targets(void) {
  return (size_t)InterlockedCompareExchange(&win_live_targets, 0, 0);
}
#endif
