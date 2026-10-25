/* SPDX-License-Identifier: MIT */
/* Real Win32 handoff: the probe owns CF_HDROP on the system clipboard and
   reads it back through the installed EXReaderDesktopDrop Win32 adapter. */
#include "s06_handoff_internal.h"
#include <exr_desktop_drop_windows.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <windows.h>
#include <ole2.h>

int s06_handoff_deliver(const char *const *paths, size_t count, s06_handoff_result *out) {
  wchar_t *wide[S06_HANDOFF_MAX_ITEMS];
  size_t index, units = 1;
  HGLOBAL memory;
  DROPFILES *header;
  wchar_t *cursor;
  exr_drop_status status;
  exr_drop_request *request = NULL;
  memset(out, 0, sizeof(*out));
  out->status = -1;
  if (count == 0 || count > S06_HANDOFF_MAX_ITEMS) {
    snprintf(out->detail, sizeof(out->detail), "unsupported handoff item count %zu", count);
    return 0;
  }
  for (index = 0; index < count; index++) {
    int needed = MultiByteToWideChar(CP_UTF8, MB_ERR_INVALID_CHARS, paths[index], -1, NULL, 0);
    if (needed <= 0) {
      snprintf(out->detail, sizeof(out->detail), "handoff path %zu is not valid UTF-8", index);
      return 0;
    }
    wide[index] = (wchar_t *)malloc((size_t)needed * sizeof(wchar_t));
    if (!wide[index]) return 0;
    if (!MultiByteToWideChar(CP_UTF8, MB_ERR_INVALID_CHARS, paths[index], -1, wide[index], needed)) {
      free(wide[index]);
      return 0;
    }
    units += (size_t)needed;
  }
  memory = GlobalAlloc(GMEM_MOVEABLE | GMEM_ZEROINIT, sizeof(DROPFILES) + units * sizeof(wchar_t));
  if (!memory) {
    for (index = 0; index < count; index++) free(wide[index]);
    return 0;
  }
  header = (DROPFILES *)GlobalLock(memory);
  if (!header) {
    GlobalFree(memory);
    for (index = 0; index < count; index++) free(wide[index]);
    return 0;
  }
  header->pFiles = (DWORD)sizeof(DROPFILES);
  header->fWide = TRUE;
  cursor = (wchar_t *)((unsigned char *)header + sizeof(DROPFILES));
  for (index = 0; index < count; index++) {
    size_t length = wcslen(wide[index]);
    memcpy(cursor, wide[index], length * sizeof(wchar_t));
    cursor += length;
    *cursor++ = 0;
    free(wide[index]);
  }
  *cursor = 0;
  GlobalUnlock(memory);
  if (FAILED(OleInitialize(NULL))) {
    GlobalFree(memory);
    snprintf(out->detail, sizeof(out->detail), "OleInitialize failed");
    return 0;
  }
  if (!OpenClipboard(NULL)) {
    GlobalFree(memory);
    OleUninitialize();
    snprintf(out->detail, sizeof(out->detail), "OpenClipboard failed in this session");
    return 0;
  }
  if (!EmptyClipboard() || !SetClipboardData(CF_HDROP, memory)) {
    GlobalFree(memory);
    CloseClipboard();
    OleUninitialize();
    snprintf(out->detail, sizeof(out->detail), "clipboard rejected the CF_HDROP payload");
    return 0;
  }
  CloseClipboard();
  status = exr_drop_windows_clipboard_request(EXR_DROP_ORIGIN_CLIPBOARD, NULL, &request);
  s06_handoff_collect(status, request, "win32-clipboard-cf_hdrop", out);
  OleUninitialize();
  return 1;
}
