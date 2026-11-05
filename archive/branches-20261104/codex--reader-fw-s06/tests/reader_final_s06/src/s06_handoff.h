/* SPDX-License-Identifier: MIT */
#ifndef S06_HANDOFF_H
#define S06_HANDOFF_H
#include <stddef.h>

/* One real operating-system file handoff (pasteboard/clipboard/drop payload)
   delivered through the installed EXReaderDesktopDrop adapter and handed back
   to the portable probe. The probe never fabricates an item: whatever the
   adapter reports is what the host would have received. */
#define S06_HANDOFF_MAX_ITEMS 8
#define S06_HANDOFF_MAX_PATH 4096

typedef struct {
  int delivered;              /* 1 when the platform produced a request */
  int status;                 /* exr_drop_status value reported by the adapter */
  size_t item_count;
  size_t file_count;
  size_t directory_count;
  size_t kind[S06_HANDOFF_MAX_ITEMS];              /* exr_drop_item_status */
  char path[S06_HANDOFF_MAX_ITEMS][S06_HANDOFF_MAX_PATH];
  char detail[512];
} s06_handoff_result;

/* Puts the given native UTF-8 paths on the real platform clipboard/pasteboard
   and reads them back through the installed adapter. Returns 0 when the call
   itself could not run; the adapter status is always recorded in out->status. */
int s06_handoff_deliver(const char *const *paths, size_t count, s06_handoff_result *out);

#endif
