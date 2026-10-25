/* SPDX-License-Identifier: MIT */
#include "s06_handoff.h"
#include <exr_desktop_drop.h>
#include <stdio.h>
#include <string.h>

/* Copies whatever the installed adapter reported into the platform-neutral
   result. Only EXR_DROP_ITEM_FILE entries are usable by the host's import
   entry; the others are recorded so the probe can assert they are refused. */
void s06_handoff_collect(exr_drop_status status, exr_drop_request *request,
    const char *platform_note, s06_handoff_result *out) {
  exr_drop_request_info info = {0};
  size_t index;
  out->status = (int)status;
  if (platform_note) snprintf(out->detail, sizeof(out->detail), "%s", platform_note);
  if (status != EXR_DROP_OK || !request) {
    if (request) exr_drop_request_release(request);
    return;
  }
  info.struct_size = sizeof(info);
  if (exr_drop_request_get_info(request, &info) != EXR_DROP_OK) {
    snprintf(out->detail, sizeof(out->detail), "adapter request info unavailable");
    exr_drop_request_release(request);
    return;
  }
  out->delivered = 1;
  out->item_count = info.item_count;
  out->file_count = info.file_count;
  out->directory_count = info.directory_count;
  for (index = 0; index < info.item_count && index < S06_HANDOFF_MAX_ITEMS; index++) {
    exr_drop_item item = {0};
    item.struct_size = sizeof(item);
    if (exr_drop_request_get_item(request, index, &item) != EXR_DROP_OK) continue;
    out->kind[index] = (size_t)item.status;
    if (item.path) snprintf(out->path[index], S06_HANDOFF_MAX_PATH, "%s", item.path);
  }
  exr_drop_request_release(request);
}
