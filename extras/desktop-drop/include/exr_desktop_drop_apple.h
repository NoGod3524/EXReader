/* SPDX-License-Identifier: MIT */
#ifndef EXR_DESKTOP_DROP_APPLE_H
#define EXR_DESKTOP_DROP_APPLE_H
#include "exr_desktop_drop.h"
#if defined(__APPLE__) && defined(__OBJC__)
#import <AppKit/AppKit.h>
#import <Foundation/Foundation.h>

#ifdef __cplusplus
extern "C" {
#endif

/* AppKit delivery for the desktop drop adapter.
 *
 * exr_drop_apple_attach() registers a transparent child NSView pinned to the
 * given view's bounds and registers NSPasteboardTypeFileURL,
 * NSPasteboardTypeURL and NSPasteboardTypeString on it. The host view is not
 * subclassed, modified or replaced; detach removes the child. Both calls must
 * run on the main thread, and drag callbacks arrive there; detach from another
 * thread returns EXR_DROP_WRONG_THREAD.
 *
 * Reads, in order: pasteboard URLs (file URLs without a host become native
 * paths, a file URL with a host is EXR_DROP_ITEM_REMOTE_HOST, any other URL is
 * EXR_DROP_ITEM_REMOTE_URL), the legacy NSFilenamesPboardType path array, then
 * plain string text split into entries. Nothing is written to, cleared from or
 * taken from the pasteboard; a request owns its bytes and outlives the
 * pasteboard, the drag session and the view. */
typedef struct exr_drop_apple_target exr_drop_apple_target;

exr_drop_status exr_drop_apple_attach(NSView *view, const exr_drop_target_options *options,
    exr_drop_apple_target **target);
/* Same rules as exr_drop_target_destroy(), which it forwards to. */
exr_drop_status exr_drop_apple_detach(exr_drop_apple_target *target);

exr_drop_status exr_drop_apple_request_from_pasteboard(NSPasteboard *pasteboard,
    exr_drop_origin origin, const exr_drop_control *control, exr_drop_request **out);
exr_drop_status exr_drop_apple_request_from_dragging(id<NSDraggingInfo> info,
    exr_drop_origin origin, const exr_drop_control *control, exr_drop_request **out);

#ifdef __cplusplus
}
#endif
#endif
#endif
