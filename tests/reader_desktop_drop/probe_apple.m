// SPDX-License-Identifier: MIT
// AppKit acceptance probe: a real NSView drag destination installed by the
// adapter and a real (private) NSPasteboard filled with file URLs and text by
// this process. It never reads or writes the user's general pasteboard.
#import <AppKit/AppKit.h>
#import <Foundation/Foundation.h>
#import <dispatch/dispatch.h>
#include <exr_desktop_drop.h>
#include <exr_desktop_drop_apple.h>
#include "report.h"
#include <stdio.h>
#include <string.h>

static NSString *g_root;
static NSString *g_file;
static NSString *g_unicode;
static NSString *g_directory;
static NSPasteboard *g_pasteboard;

typedef struct {
  int calls;
  exr_drop_status status;
  exr_drop_request *request;
  size_t items;
  exr_drop_item_status first_status;
  char first_path[600];
  int hold_request;
  int destroy_in_callback;
  exr_drop_apple_target *target;
  exr_drop_status destroy_status;
} capture;

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
  if (request) {
    memset(&info, 0, sizeof(info));
    info.struct_size = sizeof(info);
    if (exr_drop_request_get_info(request, &info) == EXR_DROP_OK && info.item_count) {
      exr_drop_item item;
      state->items = info.item_count;
      memset(&item, 0, sizeof(item));
      item.struct_size = sizeof(item);
      if (exr_drop_request_get_item(request, 0, &item) == EXR_DROP_OK) {
        state->first_status = item.status;
        if (item.path) {
          strncpy(state->first_path, item.path, sizeof(state->first_path) - 1);
          state->first_path[sizeof(state->first_path) - 1] = 0;
        }
      }
    }
    if (state->hold_request)
      state->request = request;
    else
      exr_drop_request_release(request);
  }
  if (state->destroy_in_callback && state->target) {
    state->destroy_status = exr_drop_apple_detach(state->target);
    state->target = NULL;
  }
}

/* ---- dragging info double -------------------------------------------- */
@interface ProbeDraggingInfo : NSObject <NSDraggingInfo>
@property(nonatomic, strong) NSPasteboard *probePasteboard;
@end

@implementation ProbeDraggingInfo
- (NSWindow *)draggingDestinationWindow {
  return nil;
}
- (NSDragOperation)draggingSourceOperationMask {
  return NSDragOperationCopy;
}
- (NSPoint)draggingLocation {
  return NSMakePoint(10, 10);
}
- (NSPoint)draggedImageLocation {
  return NSMakePoint(10, 10);
}
- (NSImage *)draggedImage {
  return nil;
}
- (NSPasteboard *)draggingPasteboard {
  return self.probePasteboard;
}
- (id)draggingSource {
  return nil;
}
- (NSInteger)draggingSequenceNumber {
  return 1;
}
- (void)slideDraggedImageTo:(NSPoint)screenPoint {
  (void)screenPoint;
}
- (NSArray<NSString *> *)namesOfPromisedFilesDroppedAtDestination:(NSURL *)dropDestination {
  (void)dropDestination;
  return @[];
}
- (NSDragOperation)draggingFormation {
  return NSDragOperationEvery;
}
- (BOOL)animatesToDestination {
  return NO;
}
- (NSInteger)numberOfValidItemsForDrop {
  return 1;
}
@end

/* ---- helpers --------------------------------------------------------- */
static int cancel_probe(void *context) {
  int *seen = (int *)context;
  (*seen)++;
  return *seen > 1;
}

/* ---- fixtures -------------------------------------------------------- */
static int make_fixtures(void) {
  NSFileManager *manager = [NSFileManager defaultManager];
  NSError *error = nil;
  g_root = [NSTemporaryDirectory() stringByAppendingPathComponent:
      [NSString stringWithFormat:@"exr-drop-probe-%@", [[NSUUID UUID] UUIDString]]];
  if (![manager createDirectoryAtPath:g_root withIntermediateDirectories:YES attributes:nil error:&error])
    return 0;
  g_file = [g_root stringByAppendingPathComponent:@"a.txt"];
  g_unicode = [g_root stringByAppendingPathComponent:@"exr drop \u4E2D\u6587.epub"];
  g_directory = [g_root stringByAppendingPathComponent:@"sub"];
  if (![[NSData dataWithBytes:"x" length:1] writeToFile:g_file atomically:YES]) return 0;
  if (![[NSData dataWithBytes:"x" length:1] writeToFile:g_unicode atomically:YES]) return 0;
  if (![manager createDirectoryAtPath:g_directory withIntermediateDirectories:YES attributes:nil error:&error])
    return 0;
  g_pasteboard = [NSPasteboard pasteboardWithUniqueName];
  return g_pasteboard != nil;
}

static void pasteboard_urls(NSArray<NSURL *> *urls) {
  [g_pasteboard clearContents];
  [g_pasteboard writeObjects:urls];
}
static void pasteboard_string(NSString *text) {
  [g_pasteboard clearContents];
  [g_pasteboard setString:text forType:NSPasteboardTypeString];
}

static void case_pasteboard(const char *name, NSPasteboard *pasteboard, exr_drop_status want_status,
    exr_drop_item_status want_item, const char *want_path, size_t want_items) {
  exr_drop_request *request = NULL;
  exr_drop_status status = exr_drop_apple_request_from_pasteboard(pasteboard, EXR_DROP_ORIGIN_CLIPBOARD, NULL,
      &request);
  if (status != want_status) {
    report_fail(name, exr_drop_status_name(status));
    exr_drop_request_release(request);
    return;
  }
  if (want_status != EXR_DROP_OK) {
    report_expect(name, request == NULL, exr_drop_status_name(status));
    exr_drop_request_release(request);
    return;
  }
  {
    exr_drop_request_info info;
    exr_drop_item item;
    memset(&info, 0, sizeof(info));
    info.struct_size = sizeof(info);
    memset(&item, 0, sizeof(item));
    item.struct_size = sizeof(item);
    exr_drop_request_get_info(request, &info);
    exr_drop_request_get_item(request, 0, &item);
    if (info.item_count != want_items || item.status != want_item
        || (want_path && (!item.path || strcmp(item.path, want_path) != 0))) {
      char detail[700];
      snprintf(detail, sizeof(detail), "items=%zu status=%s path=%s", info.item_count,
          exr_drop_item_status_name(item.status), item.path ? item.path : "(null)");
      report_fail(name, detail);
    } else {
      report_pass(name, "real NSPasteboard roundtrip");
    }
    exr_drop_request_release(request);
  }
}

int main(void) {
  @autoreleasepool {
    capture state;
    exr_drop_apple_target *target = NULL;
    exr_drop_target_options options;
    NSView *host;

    memset(&state, 0, sizeof(state));
    (void)[NSApplication sharedApplication];
    report_expect("appkit_available", NSApp != nil, "NSApplication available");
    report_expect("fixtures_created", make_fixtures() == 1, "temp files with a non-ASCII name");
    if (!g_pasteboard) return report_summary("apple");

    host = [[NSView alloc] initWithFrame:NSMakeRect(0, 0, 320, 240)];
    report_expect("host_view_created", host != nil, "plain NSView");

    memset(&options, 0, sizeof(options));
    options.struct_size = sizeof(options);
    options.on_drop = on_drop;
    options.context = &state;
    report_expect("attach_real_view", exr_drop_apple_attach(host, &options, &target) == EXR_DROP_OK,
        "drag destination installed");
    {
      NSArray *types = nil;
      for (NSView *child in [host subviews]) types = [child registeredDraggedTypes];
      report_expect("drag_types_registered",
          types && [types containsObject:NSPasteboardTypeFileURL], "file URL drag type registered");
    }
    report_expect("attach_null_view", exr_drop_apple_attach(nil, &options, &target) == EXR_DROP_ARGUMENT,
        "nil view refused");

    /* ---- pasteboard reads -------------------------------------------- */
    pasteboard_urls(@[ [NSURL fileURLWithPath:g_file] ]);
    case_pasteboard("pasteboard_file_url", g_pasteboard, EXR_DROP_OK, EXR_DROP_ITEM_FILE,
        [g_file fileSystemRepresentation], 1);
    pasteboard_urls(@[ [NSURL fileURLWithPath:g_unicode] ]);
    case_pasteboard("pasteboard_unicode_name", g_pasteboard, EXR_DROP_OK, EXR_DROP_ITEM_FILE,
        [g_unicode fileSystemRepresentation], 1);
    pasteboard_urls(@[ [NSURL fileURLWithPath:g_directory] ]);
    case_pasteboard("pasteboard_directory", g_pasteboard, EXR_DROP_OK, EXR_DROP_ITEM_DIRECTORY,
        [g_directory fileSystemRepresentation], 1);
    pasteboard_urls(@[ [NSURL URLWithString:@"https://example.invalid/x.epub"] ]);
    case_pasteboard("pasteboard_remote_url", g_pasteboard, EXR_DROP_OK, EXR_DROP_ITEM_REMOTE_URL, NULL, 1);
    pasteboard_urls(@[ [NSURL fileURLWithPath:[g_root stringByAppendingPathComponent:@"missing.epub"]] ]);
    case_pasteboard("pasteboard_missing_path", g_pasteboard, EXR_DROP_OK, EXR_DROP_ITEM_MISSING,
        [[g_root stringByAppendingPathComponent:@"missing.epub"] fileSystemRepresentation], 1);
    pasteboard_string([NSString stringWithFormat:@"%@\nhttps://example.invalid/b.epub\n",
                                                 [NSURL fileURLWithPath:g_file]]);
    case_pasteboard("pasteboard_string_lines", g_pasteboard, EXR_DROP_OK, EXR_DROP_ITEM_FILE,
        [g_file fileSystemRepresentation], 2);
    pasteboard_string(@"file://server/share/x.epub");
    case_pasteboard("pasteboard_remote_host", g_pasteboard, EXR_DROP_OK, EXR_DROP_ITEM_REMOTE_HOST, NULL, 1);
    pasteboard_string(@"mtp://device/1.epub");
    case_pasteboard("pasteboard_virtual_scheme", g_pasteboard, EXR_DROP_OK, EXR_DROP_ITEM_VIRTUAL, NULL, 1);
    pasteboard_string(@"file:///a%ZZ.epub");
    case_pasteboard("pasteboard_bad_percent", g_pasteboard, EXR_DROP_OK, EXR_DROP_ITEM_INVALID, NULL, 1);
    pasteboard_string(@"file:///a%FF.epub");
    case_pasteboard("pasteboard_bad_utf8", g_pasteboard, EXR_DROP_OK, EXR_DROP_ITEM_BAD_ENCODING, NULL, 1);
    pasteboard_string([NSString stringWithFormat:@"file:///%@", [@"" stringByPaddingToLength:4200 withString:@"a"
                                                                                startingAtIndex:0]]);
    case_pasteboard("pasteboard_too_long_path", g_pasteboard, EXR_DROP_OK, EXR_DROP_ITEM_TOO_LONG, NULL, 1);
    {
      NSMutableString *many = [NSMutableString string];
      for (int index = 0; index < 300; index++)
        [many appendFormat:@"https://example.invalid/%03d.epub\n", index];
      pasteboard_string(many);
      {
        exr_drop_request *request = NULL;
        exr_drop_status status = exr_drop_apple_request_from_pasteboard(g_pasteboard, EXR_DROP_ORIGIN_CLIPBOARD,
            NULL, &request);
        exr_drop_request_info info;
        memset(&info, 0, sizeof(info));
        info.struct_size = sizeof(info);
        if (status == EXR_DROP_OK) exr_drop_request_get_info(request, &info);
        report_expect("pasteboard_item_cap",
            status == EXR_DROP_OK && info.item_count == 256 && info.overflow_count == 44 && info.truncated,
            "cap at 256 items with overflow recorded");
        exr_drop_request_release(request);
      }
    }
    {
      int seen = 0;
      exr_drop_control control;
      exr_drop_request *request = NULL;
      memset(&control, 0, sizeof(control));
      control.struct_size = sizeof(control);
      control.cancelled = cancel_probe;
      control.context = &seen;
      pasteboard_string([NSString stringWithFormat:@"%@\n%@\n", [NSURL fileURLWithPath:g_file],
                                                   [NSURL fileURLWithPath:g_file]]);
      report_expect("pasteboard_cancel",
          exr_drop_apple_request_from_pasteboard(g_pasteboard, EXR_DROP_ORIGIN_CLIPBOARD, &control, &request)
                  == EXR_DROP_CANCELLED
              && request == NULL,
          "cancellation honoured while reading pasteboard URLs");
    }
    {
      [g_pasteboard clearContents];
      exr_drop_request *request = NULL;
      report_expect("pasteboard_empty",
          exr_drop_apple_request_from_pasteboard(g_pasteboard, EXR_DROP_ORIGIN_CLIPBOARD, NULL, &request)
              == EXR_DROP_EMPTY,
          "cleared pasteboard reported as empty");
    }

    /* ---- drag delivery ----------------------------------------------- */
    {
      NSView *overlay = nil;
      ProbeDraggingInfo *info = [[ProbeDraggingInfo alloc] init];
      for (NSView *child in [host subviews])
        if ([[child registeredDraggedTypes] containsObject:NSPasteboardTypeFileURL]) overlay = child;
      pasteboard_urls(@[ [NSURL fileURLWithPath:g_file] ]);
      info.probePasteboard = g_pasteboard;
      report_expect("drag_entered_copy",
          overlay != nil && [overlay draggingEntered:(id<NSDraggingInfo>)info] == NSDragOperationCopy,
          "drag destination accepts file URLs");
      capture_reset(&state);
      report_expect("drag_perform_delivers",
          overlay != nil && [overlay performDragOperation:(id<NSDraggingInfo>)info] == YES
              && state.calls == 1 && state.status == EXR_DROP_OK
              && state.first_status == EXR_DROP_ITEM_FILE
              && strcmp(state.first_path, [g_file fileSystemRepresentation]) == 0,
          "performDragOperation reached the callback");
      if (overlay == nil) report_fail("drag_overlay_present", "no overlay subview");
      else report_pass("drag_overlay_present", "transparent child view installed");
    }
    {
      /* lifetime: request survives the pasteboard contents changing */
      exr_drop_request *held = NULL;
      pasteboard_urls(@[ [NSURL fileURLWithPath:g_unicode] ]);
      if (exr_drop_apple_request_from_pasteboard(g_pasteboard, EXR_DROP_ORIGIN_CLIPBOARD, NULL, &held)
          != EXR_DROP_OK) {
        report_fail("request_outlives_pasteboard", "request failed");
      } else {
        exr_drop_item item;
        [g_pasteboard clearContents];
        memset(&item, 0, sizeof(item));
        item.struct_size = sizeof(item);
        exr_drop_request_get_item(held, 0, &item);
        report_expect("request_outlives_pasteboard",
            item.status == EXR_DROP_ITEM_FILE && item.path
                && strcmp(item.path, [g_unicode fileSystemRepresentation]) == 0,
            "path bytes survive the pasteboard");
        exr_drop_request_release(held);
      }
    }
    {
      capture inner;
      exr_drop_apple_target *victim = NULL;
      NSView *overlay = nil;
      ProbeDraggingInfo *info = [[ProbeDraggingInfo alloc] init];
      memset(&inner, 0, sizeof(inner));
      inner.destroy_in_callback = 1;
      options.context = &inner;
      pasteboard_urls(@[ [NSURL fileURLWithPath:g_file] ]);
      info.probePasteboard = g_pasteboard;
      if (exr_drop_apple_attach(host, &options, &victim) == EXR_DROP_OK) {
        inner.target = victim;
        for (NSView *child in [host subviews])
          if ([[child registeredDraggedTypes] containsObject:NSPasteboardTypeFileURL]) overlay = child;
        if (overlay) [overlay performDragOperation:(id<NSDraggingInfo>)info];
        report_expect("detach_inside_callback",
            inner.calls == 1 && inner.destroy_status == EXR_DROP_OK && inner.target == NULL,
            "target destroyed from its own callback");
      } else {
        report_fail("detach_inside_callback", "attach failed");
      }
      options.context = &state;
    }

    /* ---- lifecycle --------------------------------------------------- */
    {
      __block int status = -1;
      dispatch_semaphore_t semaphore = dispatch_semaphore_create(0);
      dispatch_async(dispatch_get_global_queue(DISPATCH_QUEUE_PRIORITY_DEFAULT, 0), ^{
        status = (int)exr_drop_apple_detach(target);
        dispatch_semaphore_signal(semaphore);
      });
      dispatch_semaphore_wait(semaphore, DISPATCH_TIME_FOREVER);
      report_expect("detach_from_other_thread", status == (int)EXR_DROP_WRONG_THREAD,
          "wrong thread refused, target unchanged");
    }
    {
      NSView *spare = [[NSView alloc] initWithFrame:NSMakeRect(0, 0, 40, 40)];
      exr_drop_apple_target *victim = NULL;
      if (exr_drop_apple_attach(spare, &options, &victim) == EXR_DROP_OK) {
        [spare removeFromSuperview];
        report_expect("view_detached_before_destroy", exr_drop_apple_detach(victim) == EXR_DROP_OK,
            "detach removes the overlay and frees the target");
      } else {
        report_fail("view_detached_before_destroy", "attach failed");
      }
    }
    report_expect("detach_owner_thread", exr_drop_apple_detach(target) == EXR_DROP_OK, "final detach");
    return report_summary("apple");
  }
}
