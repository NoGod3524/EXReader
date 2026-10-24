/* SPDX-License-Identifier: MIT */
#include "internal.h"
#include "exr_desktop_drop_windows.h"
#include <shlobj.h>
#include <stdlib.h>
#include <string.h>

typedef struct win_target {
  struct exr_drop_target base; /* must be first */
  IDropTarget iface;
  volatile LONG refs;
  HWND window;
  DWORD owner_tid;
  int registered;
  int can_drop;
} win_target;

#define WIN_FROM_IFACE(p) ((win_target *)((char *)(p) - offsetof(win_target, iface)))

static int win_owner_thread(const struct exr_drop_target *base) {
  const win_target *target = (const win_target *)base;
  return GetCurrentThreadId() == target->owner_tid;
}

static void win_release_object(struct exr_drop_target *base);

/* ---- payload extraction --------------------------------------------- */
static CLIPFORMAT file_group_format(void) {
  return RegisterClipboardFormatW(CFSTR_FILEDESCRIPTORW);
}

static exr_drop_status request_from_unicode_text(HGLOBAL handle, exr_drop_origin origin,
    const exr_drop_control *control, exr_drop_request **out) {
  drop_builder builder;
  const wchar_t *text;
  size_t length;
  exr_drop_status status;
  if (!handle) { *out = NULL; return EXR_DROP_PLATFORM; }
  text = (const wchar_t *)GlobalLock(handle);
  if (!text) { *out = NULL; return EXR_DROP_PLATFORM; }
  length = wcsnlen(text, EXR_DROP_MAX_INPUT_BYTES / 2u + 1u);
  if (length > EXR_DROP_MAX_INPUT_BYTES / 2u) {
    GlobalUnlock(handle);
    *out = NULL;
    return EXR_DROP_TOO_LARGE;
  }
  drop_builder_init(&builder, origin, control);
  drop_utf16_split((const uint16_t *)(const void *)text, length, EXR_DROP_UTF16_LINES, &builder);
  status = drop_builder_finish(&builder, out);
  GlobalUnlock(handle);
  return status;
}

static exr_drop_status request_from_file_group(HGLOBAL handle, exr_drop_origin origin,
    const exr_drop_control *control, exr_drop_request **out) {
  const FILEGROUPDESCRIPTORW *group;
  drop_builder builder;
  UINT index;
  exr_drop_status status;
  if (!handle) { *out = NULL; return EXR_DROP_UNSUPPORTED; }
  group = (const FILEGROUPDESCRIPTORW *)GlobalLock(handle);
  if (!group) { *out = NULL; return EXR_DROP_PLATFORM; }
  drop_builder_init(&builder, origin, control);
  for (index = 0; index < group->cItems && !drop_builder_stopped(&builder); index++)
    drop_add_virtual(&builder, (const uint16_t *)(const void *)group->fgd[index].cFileName,
        wcsnlen(group->fgd[index].cFileName, 260));
  status = drop_builder_finish(&builder, out);
  GlobalUnlock(handle);
  if (status == EXR_DROP_EMPTY) status = EXR_DROP_UNSUPPORTED;
  return status;
}

exr_drop_status exr_drop_windows_request_from_hdrop(HDROP drop, exr_drop_origin origin,
    const exr_drop_control *control, exr_drop_request **out) {
  drop_builder builder;
  UINT count, index;
  uint64_t units = 0;
  if (!out) return EXR_DROP_ARGUMENT;
  *out = NULL;
  if (!drop) return EXR_DROP_ARGUMENT;
  if (origin < EXR_DROP_ORIGIN_DROP || origin > EXR_DROP_ORIGIN_TEXT) return EXR_DROP_ARGUMENT;
  if (control && control->struct_size != sizeof(*control)) return EXR_DROP_ARGUMENT;
  count = DragQueryFileW(drop, 0xFFFFFFFFu, NULL, 0);
  if (count == 0) return EXR_DROP_EMPTY;
  for (index = 0; index < count; index++) {
    units += (uint64_t)DragQueryFileW(drop, index, NULL, 0) + 1u;
    if (units * 2u > (uint64_t)EXR_DROP_MAX_INPUT_BYTES) return EXR_DROP_TOO_LARGE;
  }
  drop_builder_init(&builder, origin, control);
  for (index = 0; index < count && !drop_builder_stopped(&builder); index++) {
    UINT length = DragQueryFileW(drop, index, NULL, 0);
    wchar_t *path = (wchar_t *)malloc(((size_t)length + 1u) * sizeof(wchar_t));
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
    if (target->registered) { target->registered = 0; RevokeDragDrop(target->window); }
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

static const IDropTargetVtbl win_vtbl = {win_QueryInterface, win_AddRef, win_Release, win_DragEnter,
    win_DragOver, win_DragLeave, win_Drop};

/* ---- lifecycle ------------------------------------------------------- */
static void win_release_object(struct exr_drop_target *base) {
  win_target *target = (win_target *)base;
  if (target->registered) {
    target->registered = 0;
    RevokeDragDrop(target->window);
  }
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
  drop_target_init(&created->base, options, win_owner_thread, win_release_object);
  created->iface.lpVtbl = &win_vtbl;
  created->refs = 1;
  created->window = window;
  created->owner_tid = owner;
  result = RegisterDragDrop(window, &created->iface);
  if (FAILED(result)) {
    free(created);
    return EXR_DROP_PLATFORM;
  }
  created->registered = 1;
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
