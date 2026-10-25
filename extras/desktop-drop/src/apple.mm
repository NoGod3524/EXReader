/* SPDX-License-Identifier: MIT */
#include "exr_desktop_drop_apple.h"
#if defined(__APPLE__)
extern "C" {
#include "internal.h"
}
#import <AppKit/AppKit.h>
#import <Foundation/Foundation.h>
#include <stdlib.h>
#include <string.h>

struct exr_drop_apple_target {
  struct exr_drop_target base; /* must be first */
  NSView *host;
  NSView *overlay;
  NSThread *thread;
};

static void apple_release_object(struct exr_drop_target *base);

static int apple_owner_thread(const struct exr_drop_target *base) {
  const struct exr_drop_apple_target *target = (const struct exr_drop_apple_target *)base;
  return target->thread && [NSThread currentThread] == target->thread;
}

/* ---- payload --------------------------------------------------------- */
static void apple_add_url(drop_builder *builder, NSURL *url) {
  const char *bytes;
  if (!url) return;
  if ([url isFileURL] && [url host] == nil) {
    bytes = [url fileSystemRepresentation];
    if (bytes) drop_add_utf8_entry(builder, bytes, strlen(bytes));
    return;
  }
  bytes = [[url absoluteString] UTF8String];
  if (bytes) drop_add_utf8_entry(builder, bytes, strlen(bytes));
}

static void apple_add_text(drop_builder *builder, NSString *text) {
  const char *bytes = [text UTF8String];
  size_t length, index = 0;
  if (!bytes) return;
  length = strlen(bytes);
  while (index < length && !drop_builder_stopped(builder)) {
    size_t start = index, end;
    while (index < length && bytes[index] != '\n' && bytes[index] != '\r') index++;
    end = index;
    if (index < length) index += (bytes[index] == '\r' && index + 1 < length && bytes[index + 1] == '\n') ? 2 : 1;
    while (start < end && (bytes[start] == ' ' || bytes[start] == '\t')) start++;
    while (end > start && (bytes[end - 1] == ' ' || bytes[end - 1] == '\t')) end--;
    if (end > start) drop_add_utf8_entry(builder, bytes + start, end - start);
  }
}

extern "C" exr_drop_status exr_drop_apple_request_from_pasteboard(NSPasteboard *pasteboard,
    exr_drop_origin origin, const exr_drop_control *control, exr_drop_request **out) {
  drop_builder builder;
  NSArray<NSURL *> *urls;
  NSArray *names;
  NSString *text;
  exr_drop_status status;
  int saw_source = 0;
  if (!out) return EXR_DROP_ARGUMENT;
  *out = NULL;
  if (!pasteboard) return EXR_DROP_ARGUMENT;
  if (origin < EXR_DROP_ORIGIN_DROP || origin > EXR_DROP_ORIGIN_TEXT) return EXR_DROP_ARGUMENT;
  if (control && control->struct_size != sizeof(*control)) return EXR_DROP_ARGUMENT;
  drop_builder_init(&builder, origin, control);
  urls = [pasteboard readObjectsForClasses:@[ [NSURL class] ] options:nil];
  if ([urls count] > 0) saw_source = 1;
  for (NSURL *url in urls) {
    if (drop_builder_stopped(&builder)) break;
    apple_add_url(&builder, url);
  }
  if (builder.count == 0 && builder.failure == EXR_DROP_OK) {
    names = [pasteboard propertyListForType:@"NSFilenamesPboardType"];
    if ([names isKindOfClass:[NSArray class]]) {
      saw_source = 1;
      for (id name in names) {
        if (drop_builder_stopped(&builder)) break;
        if ([name isKindOfClass:[NSString class]]) apple_add_text(&builder, (NSString *)name);
      }
    }
  }
  if (builder.count == 0 && builder.failure == EXR_DROP_OK) {
    text = [pasteboard stringForType:NSPasteboardTypeString];
    if (text) {
      saw_source = 1;
      apple_add_text(&builder, text);
    }
  }
  status = drop_builder_finish(&builder, out);
  /* A pasteboard with content this adapter cannot represent (an image, say) is
     unsupported; an empty pasteboard is simply empty. */
  if (status == EXR_DROP_EMPTY && !saw_source && [[pasteboard types] count] > 0)
    status = EXR_DROP_UNSUPPORTED;
  return status;
}

extern "C" exr_drop_status exr_drop_apple_request_from_dragging(id<NSDraggingInfo> info,
    exr_drop_origin origin, const exr_drop_control *control, exr_drop_request **out) {
  if (!info) {
    if (out) *out = NULL;
    return EXR_DROP_ARGUMENT;
  }
  return exr_drop_apple_request_from_pasteboard([info draggingPasteboard], origin, control, out);
}

/* ---- overlay view ---------------------------------------------------- */
@interface EXRDropOverlayView : NSView {
@public
  struct exr_drop_target *dropBase;
}
@end

@implementation EXRDropOverlayView
- (BOOL)isOpaque {
  return NO;
}
- (void)drawRect:(NSRect)dirtyRect {
  (void)dirtyRect;
}
- (NSDragOperation)draggingEntered:(id<NSDraggingInfo>)sender {
  (void)sender;
  return dropBase && !dropBase->dead ? NSDragOperationCopy : NSDragOperationNone;
}
- (NSDragOperation)draggingUpdated:(id<NSDraggingInfo>)sender {
  (void)sender;
  return dropBase && !dropBase->dead ? NSDragOperationCopy : NSDragOperationNone;
}
- (void)draggingExited:(id<NSDraggingInfo>)sender {
  (void)sender;
}
- (BOOL)prepareForDragOperation:(id<NSDraggingInfo>)sender {
  (void)sender;
  return YES;
}
- (BOOL)performDragOperation:(id<NSDraggingInfo>)sender {
  exr_drop_request *request = NULL;
  exr_drop_status status;
  if (!dropBase || dropBase->dead) return NO;
  status = exr_drop_apple_request_from_dragging(sender, EXR_DROP_ORIGIN_DROP,
      drop_target_control(dropBase), &request);
  drop_target_deliver(dropBase, status, request);
  return status == EXR_DROP_OK ? YES : NO;
}
- (BOOL)wantsPeriodicDraggingUpdates {
  return NO;
}
@end

/* ---- lifecycle ------------------------------------------------------- */
static void apple_release_object(struct exr_drop_target *base) {
  struct exr_drop_apple_target *target = (struct exr_drop_apple_target *)base;
  if (target->overlay) {
    EXRDropOverlayView *overlay = (EXRDropOverlayView *)target->overlay;
    overlay->dropBase = NULL;
    [overlay unregisterDraggedTypes];
    [overlay removeFromSuperview];
    [overlay release];
    target->overlay = nil;
  }
  if (target->thread) {
    [target->thread release];
    target->thread = nil;
  }
  if (target->host) {
    [target->host release];
    target->host = nil;
  }
  free(target);
}

extern "C" exr_drop_status exr_drop_apple_attach(NSView *view, const exr_drop_target_options *options,
    exr_drop_apple_target **target) {
  struct exr_drop_apple_target *created;
  EXRDropOverlayView *overlay;
  if (!target) return EXR_DROP_ARGUMENT;
  *target = NULL;
  if (!view || !drop_target_options_valid(options)) return EXR_DROP_ARGUMENT;
  if (![NSThread isMainThread]) return EXR_DROP_PLATFORM;
  created = (struct exr_drop_apple_target *)calloc(1, sizeof(*created));
  if (!created) return EXR_DROP_NO_MEMORY;
  drop_target_init(&created->base, options, apple_owner_thread, apple_release_object);
  overlay = [[EXRDropOverlayView alloc] initWithFrame:[view bounds]];
  if (!overlay) {
    free(created);
    return EXR_DROP_NO_MEMORY;
  }
  [overlay setAutoresizingMask:NSViewWidthSizable | NSViewHeightSizable];
  [overlay registerForDraggedTypes:@[
    NSPasteboardTypeFileURL, NSPasteboardTypeURL, NSPasteboardTypeString
  ]];
  overlay->dropBase = &created->base;
  [view addSubview:overlay positioned:NSWindowAbove relativeTo:nil];
  created->host = [view retain];
  created->overlay = overlay;
  created->thread = [[NSThread currentThread] retain];
  *target = created;
  return EXR_DROP_OK;
}

extern "C" exr_drop_status exr_drop_apple_detach(exr_drop_apple_target *target) {
  return exr_drop_target_destroy((exr_drop_target *)target);
}
#endif
