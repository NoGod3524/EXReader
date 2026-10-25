/* SPDX-License-Identifier: MIT
 * Host-shaped consumer of the installed desktop drop package: what a reader
 * host does with a finished drop. Platform heads (Win32/GTK/AppKit) hand the
 * request here; this file only uses the portable core and the public header.
 */
#include <exr_desktop_drop.h>
#include <stdio.h>
#include <string.h>

/* Stand-in for exr_sideload_import_file(): the only entries a host may pass on
   are EXR_DROP_ITEM_FILE ones, whose UTF-8 path stays immutable until the
   import returns. */
static int import_path(const char *path) {
  if (!path || !path[0]) return 0;
  if (strlen(path) >= EXR_DROP_MAX_PATH_BYTES) return 0;
  return 1;
}

static int drain(exr_drop_request *request, unsigned *imported, unsigned *directories, unsigned *rejected) {
  exr_drop_request_info info;
  size_t index;
  int ok = 1;
  memset(&info, 0, sizeof(info));
  info.struct_size = sizeof(info);
  if (exr_drop_request_get_info(request, &info) != EXR_DROP_OK) return 0;
  for (index = 0; index < info.item_count; index++) {
    exr_drop_item item;
    memset(&item, 0, sizeof(item));
    item.struct_size = sizeof(item);
    if (exr_drop_request_get_item(request, index, &item) != EXR_DROP_OK) { ok = 0; break; }
    if (item.status == EXR_DROP_ITEM_FILE) {
      if (!import_path(item.path)) { ok = 0; break; }
      (*imported)++;
    } else if (item.status == EXR_DROP_ITEM_DIRECTORY) {
      /* Directories are never recursed here; the host asks the user instead. */
      (*directories)++;
    } else {
      (*rejected)++;
    }
  }
  return ok;
}

int main(int argc, char **argv) {
  exr_drop_request *request = NULL;
  exr_drop_status status;
  exr_drop_request_info info;
  unsigned imported = 0, directories = 0, rejected = 0;
  const char *payload = argc > 1 ? argv[1] : "https://example.invalid/book.epub\r\nmtp://device/1.epub\r\n";
  status = exr_drop_request_from_uri_list(payload, strlen(payload), EXR_DROP_ORIGIN_TEXT, NULL, &request);
  if (status != EXR_DROP_OK) {
    printf("request status %s\n", exr_drop_status_name(status));
    return status == EXR_DROP_EMPTY ? 0 : 2;
  }
  memset(&info, 0, sizeof(info));
  info.struct_size = sizeof(info);
  if (exr_drop_request_get_info(request, &info) != EXR_DROP_OK || !drain(request, &imported, &directories, &rejected)) {
    exr_drop_request_release(request);
    return 3;
  }
  printf("origin=%d items=%zu files=%zu directories=%zu duplicates=%zu truncated=%d imported=%u directories_seen=%u rejected=%u\n",
      (int)info.origin, info.item_count, info.file_count, info.directory_count, info.duplicate_count,
      info.truncated, imported, directories, rejected);
  exr_drop_request_release(request);
  return 0;
}
