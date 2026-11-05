/* SPDX-License-Identifier: MIT */
/* Real AppKit handoff: the probe owns file URLs on the general pasteboard and
   reads them back through the installed EXReaderDesktopDrop Apple adapter. */
#include "s06_handoff_internal.h"
#import <exr_desktop_drop_apple.h>
#import <AppKit/AppKit.h>
#import <Foundation/Foundation.h>
#include <stdio.h>
#include <string.h>

int s06_handoff_deliver(const char *const *paths, size_t count, s06_handoff_result *out) {
  memset(out, 0, sizeof(*out));
  out->status = -1;
  if (count == 0 || count > S06_HANDOFF_MAX_ITEMS) {
    snprintf(out->detail, sizeof(out->detail), "unsupported handoff item count %zu", count);
    return 0;
  }
  @autoreleasepool {
    NSMutableArray *urls = [NSMutableArray array];
    NSPasteboard *pasteboard = [NSPasteboard generalPasteboard];
    exr_drop_status status;
    exr_drop_request *request = NULL;
    size_t index;
    for (index = 0; index < count; index++) {
      NSString *base = [NSString stringWithUTF8String:paths[index]];
      if (!base) {
        snprintf(out->detail, sizeof(out->detail), "handoff path %zu is not valid UTF-8", index);
        return 0;
      }
      [urls addObject:[NSURL fileURLWithPath:base]];
    }
    [pasteboard clearContents];
    if (![pasteboard writeObjects:urls]) {
      snprintf(out->detail, sizeof(out->detail), "NSPasteboard refused the file URLs");
      return 0;
    }
    status = exr_drop_apple_request_from_pasteboard(pasteboard, EXR_DROP_ORIGIN_CLIPBOARD, NULL, &request);
    s06_handoff_collect(status, request, "appkit-general-pasteboard-file-url", out);
  }
  return 1;
}
