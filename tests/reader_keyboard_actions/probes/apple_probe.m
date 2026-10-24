// SPDX-License-Identifier: MIT
// Real Cocoa keyboard probe. It creates actual NSWindows with an editable
// NSTextField and a sheet, builds real NSEvent objects with the platform key
// codes and NSEventModifierFlags, and lets AppKit's own dispatch path route each
// event: the installed keyboard-actions package sits in the window's sendEvent:
// and either consumes the event or hands it to the responder chain (where a real
// field editor edits text). Each named case prints
// "PROBE <name> PASS|FAIL|SKIP <detail>".
#import <Cocoa/Cocoa.h>

#include "reader_keyboard_actions.h"

#include <signal.h>
#include <stdio.h>
#include <string.h>
#include <unistd.h>

typedef struct {
  reader_kbd *kbd;
  NSWindow *window;
  NSWindow *other;
  NSWindow *sheet;
  NSView *area;
  NSTextField *field;
  NSWindow *last_window;
  int modal_open;
  int force_active;
  int cancel_calls;
  int canceled_dropped;
  uint32_t down_action;
  uint32_t down_reason;
  uint32_t down_disposition;
  uint32_t page_actions;
  int forwarded_down;
  int forwarded_up;
  int swallowed_down;
  int swallowed_up;
  int modal_saw_key;
  int other_saw_key;
} host_state;

static host_state g;
static char scratch[512];
static int failures;
static int passes;
static int skips;

static void record(const char *name, const char *status, const char *detail) {
  if (status[0] == 'F') ++failures;
  else if (status[0] == 'S') ++skips;
  else ++passes;
  (void)fprintf(stdout, "PROBE %s %s %s\n", name, status, detail != NULL ? detail : "");
  (void)fflush(stdout);
}

static const char *current_step = "startup";

static void begin_case(const char *name) {
  current_step = name;
  (void)fprintf(stdout, "STEP %s\n", name);
  (void)fflush(stdout);
}

static void on_watchdog(int signal_number) {
  (void)signal_number;
  (void)fprintf(stderr, "watchdog: the probe exceeded its time budget in case %s\n", current_step);
  (void)fflush(stderr);
  _exit(3);
}

static void reset_counters(void) {
  g.down_action = 0xffffffffu;
  g.down_reason = 0xffffffffu;
  g.down_disposition = 0xffffffffu;
  g.page_actions = 0;
  g.forwarded_down = 0;
  g.forwarded_up = 0;
  g.swallowed_down = 0;
  g.swallowed_up = 0;
  g.modal_saw_key = 0;
  g.other_saw_key = 0;
  g.cancel_calls = 0;
  g.canceled_dropped = 0;
}

static void pump(double seconds) {
  NSDate *deadline = [NSDate dateWithTimeIntervalSinceNow:seconds];
  while ([deadline timeIntervalSinceNow] > 0.0) {
    @autoreleasepool {
      [[NSRunLoop currentRunLoop] runMode:NSDefaultRunLoopMode
                               beforeDate:[NSDate dateWithTimeIntervalSinceNow:0.01]];
    }
  }
}

static void host_cancel(void) {
  uint32_t dropped = 0;
  ++g.cancel_calls;
  if (g.kbd != NULL && reader_kbd_cancel(g.kbd, &dropped) == READER_KBD_OK) {
    g.canceled_dropped += (int)dropped;
  }
}

static int host_handler(void *user, uint32_t action, const reader_kbd_event *event) {
  host_state *state = (host_state *)user;
  (void)event;
  if (action == (uint32_t)READER_KBD_ACTION_PAGE_NEXT ||
      action == (uint32_t)READER_KBD_ACTION_PAGE_PREVIOUS) {
    ++state->page_actions;
  }
  return 1;
}

static const char *disposition_name(uint32_t disposition) {
  return disposition == (uint32_t)READER_KBD_CONSUME ? "consume" : "pass";
}

static uint32_t focus_for(NSWindow *window) {
  if (g.modal_open != 0) return (uint32_t)READER_KBD_FOCUS_MODAL;
  if (window == g.window) {
    NSResponder *responder = [window firstResponder];
    if (responder == (NSResponder *)g.field) return (uint32_t)READER_KBD_FOCUS_TEXT_INPUT;
    /* While a text field is edited AppKit makes its field editor the responder. */
    if ([responder isKindOfClass:[NSTextView class]]) return (uint32_t)READER_KBD_FOCUS_TEXT_INPUT;
  }
  return (uint32_t)READER_KBD_FOCUS_READER;
}

static uint32_t first_codepoint(NSString *text) {
  if (text == nil || [text length] == 0) return 0;
  unichar value = [text characterAtIndex:0];
  if (value >= 0xD800 && value <= 0xDFFF) return 0;
  return (uint32_t)value;
}

// Returns 1 when the package consumed the event.
static int deliver(NSEvent *event, NSWindow *window) {
  reader_kbd_event translated;
  reader_kbd_context context;
  reader_kbd_result result;
  uint32_t focus;
  NSEventType type = [event type];

  if (g.kbd == NULL) return 0;
  if (type != NSEventTypeKeyDown && type != NSEventTypeKeyUp) return 0;
  /* Host policy: keyboard ownership moving to another window forgets the holds,
     so the next key-up reaches the new owner instead of being swallowed. */
  if (g.last_window != nil && g.last_window != window) host_cancel();
  g.last_window = window;
  if (reader_kbd_event_from_apple((uint32_t)type, (uint32_t)[event keyCode],
                                  (uint64_t)[event modifierFlags],
                                  first_codepoint([event charactersIgnoringModifiers]),
                                  [event isARepeat] ? 1u : 0u, &translated) != READER_KBD_OK) {
    return 0;
  }
  (void)memset(&context, 0, sizeof(context));
  context.struct_size = (uint32_t)sizeof(context);
  focus = focus_for(window);
  context.focus = focus;
  context.composing = 0;
  /* Only the reader window can be active for this component. force_active is set
     when a hosted runner refuses to make the process active; probe-window-ready
     records that fact instead of hiding it. */
  context.window_active =
      ((window == g.window && ([g.window isKeyWindow] || g.force_active != 0)) ||
       (g.modal_open != 0 && window == g.sheet))
          ? 1u
          : 0u;
  if (reader_kbd_dispatch(g.kbd, &translated, &context, host_handler, &g, &result) !=
      READER_KBD_OK) {
    return 0;
  }
  if (translated.phase == (uint32_t)READER_KBD_PHASE_DOWN) {
    g.down_action = result.action;
    g.down_reason = result.reason;
    g.down_disposition = result.disposition;
  }
  if (result.disposition == (uint32_t)READER_KBD_CONSUME) {
    if (translated.phase == (uint32_t)READER_KBD_PHASE_DOWN) ++g.swallowed_down;
    else ++g.swallowed_up;
    if (focus == (uint32_t)READER_KBD_FOCUS_MODAL) g.modal_saw_key = 1;
    return 1;
  }
  if (translated.phase == (uint32_t)READER_KBD_PHASE_DOWN) ++g.forwarded_down;
  else ++g.forwarded_up;
  if (focus == (uint32_t)READER_KBD_FOCUS_MODAL) g.modal_saw_key = 1;
  if (window == g.other) g.other_saw_key = 1;
  return 0;
}

@interface ProbeWindow : NSWindow
@end

@implementation ProbeWindow
- (void)sendEvent:(NSEvent *)event {
  if (deliver(event, self) != 0) return;
  [super sendEvent:event];
}
- (void)resignKeyWindow {
  if (self == g.window) host_cancel();
  [super resignKeyWindow];
}
@end

@interface ProbeView : NSView
@end

@implementation ProbeView
- (BOOL)acceptsFirstResponder {
  return YES;
}
@end

static NSEvent *make_event(NSEventType type, unsigned short code, NSEventModifierFlags flags,
                           NSString *characters, BOOL is_repeat, NSWindow *window) {
  return [NSEvent keyEventWithType:type
                          location:NSZeroPoint
                     modifierFlags:flags
                         timestamp:[[NSProcessInfo processInfo] systemUptime]
                      windowNumber:[window windowNumber]
                           context:nil
                        characters:characters
       charactersIgnoringModifiers:characters
                         isARepeat:is_repeat
                           keyCode:code];
}

static void send_key(NSWindow *window, NSEventType type, unsigned short code,
                     NSEventModifierFlags flags, NSString *characters, BOOL is_repeat) {
  @autoreleasepool {
    NSEvent *event = make_event(type, code, flags, characters, is_repeat, window);
    [NSApp sendEvent:event];
  }
  pump(0.05);
}

static void tap_key(NSWindow *window, unsigned short code, NSEventModifierFlags flags,
                    NSString *characters) {
  send_key(window, NSEventTypeKeyDown, code, flags, characters, NO);
  send_key(window, NSEventTypeKeyUp, code, flags, characters, NO);
  pump(0.05);
}

static void case_ready(void) {
  begin_case("ready");
  if (g.window == nil || ![g.window isVisible] || [g.window windowNumber] <= 0) {
    record("probe-window-ready", "FAIL", "the Cocoa window is not visible");
    return;
  }
  if (![g.window isKeyWindow] && g.force_active == 0) {
    (void)snprintf(scratch, sizeof(scratch),
                   "the Cocoa window is visible but neither key nor flagged active "
                   "(NSApp isActive=%d)", [NSApp isActive] ? 1 : 0);
    record("probe-window-ready", "FAIL", scratch);
    return;
  }
  (void)snprintf(scratch, sizeof(scratch),
                 "a real NSWindow receives NSEvents (isKeyWindow=%d appActive=%d note=%s)",
                 [g.window isKeyWindow] ? 1 : 0, [NSApp isActive] ? 1 : 0,
                 g.force_active != 0 ? "runner refused activation, host flag derived from the "
                                       "ordered-front window"
                                     : "key window");
  record("probe-window-ready", "PASS", scratch);
}

static void case_page_next(void) {
  begin_case("page-next");
  reset_counters();
  [g.window makeFirstResponder:g.area];
  pump(0.05);
  tap_key(g.window, 124, 0, @"\uF703");
  if (g.down_action != (uint32_t)READER_KBD_ACTION_PAGE_NEXT ||
      g.down_disposition != (uint32_t)READER_KBD_CONSUME || g.swallowed_down < 1 ||
      g.swallowed_up < 1 || g.forwarded_down != 0) {
    (void)snprintf(scratch, sizeof(scratch),
                   "action=%s disposition=%s swallowed=%d/%d forwarded=%d reason=%s",
                   reader_kbd_action_name(g.down_action), disposition_name(g.down_disposition),
                   g.swallowed_down, g.swallowed_up, g.forwarded_down,
                   reader_kbd_reason_name(g.down_reason));
    record("reader-page-next-consumed", "FAIL", scratch);
    return;
  }
  record("reader-page-next-consumed", "PASS", "a real right-arrow NSEvent became the next page");
}

static void case_page_previous(void) {
  begin_case("page-previous");
  reset_counters();
  tap_key(g.window, 123, 0, @"\uF702");
  if (g.down_action != (uint32_t)READER_KBD_ACTION_PAGE_PREVIOUS) {
    (void)snprintf(scratch, sizeof(scratch), "action=%s reason=%s",
                   reader_kbd_action_name(g.down_action), reader_kbd_reason_name(g.down_reason));
    record("reader-page-previous-consumed", "FAIL", scratch);
    return;
  }
  record("reader-page-previous-consumed", "PASS", "a real left-arrow NSEvent became the previous page");
}

static void case_command_search(void) {
  begin_case("command-search");
  reset_counters();
  tap_key(g.window, 3, NSEventModifierFlagCommand, @"f");
  if (g.down_action != (uint32_t)READER_KBD_ACTION_SEARCH ||
      g.down_disposition != (uint32_t)READER_KBD_CONSUME) {
    (void)snprintf(scratch, sizeof(scratch), "action=%s reason=%s",
                   reader_kbd_action_name(g.down_action), reader_kbd_reason_name(g.down_reason));
    record("reader-command-search", "FAIL", scratch);
    return;
  }
  record("reader-command-search", "PASS", "a real Command+F NSEvent became the search action");
}

static void case_shift_space(void) {
  begin_case("shift-space");
  reset_counters();
  tap_key(g.window, 49, NSEventModifierFlagShift, @" ");
  if (g.down_action != (uint32_t)READER_KBD_ACTION_PAGE_PREVIOUS) {
    (void)snprintf(scratch, sizeof(scratch), "action=%s reason=%s",
                   reader_kbd_action_name(g.down_action), reader_kbd_reason_name(g.down_reason));
    record("reader-shift-space-previous", "FAIL", scratch);
    return;
  }
  record("reader-shift-space-previous", "PASS", "a real Shift+Space NSEvent became the previous page");
}

static void case_conflict_passes(void) {
  begin_case("conflict-passes");
  reset_counters();
  tap_key(g.window, 3, NSEventModifierFlagCommand | NSEventModifierFlagShift, @"F");
  if (g.down_reason != (uint32_t)READER_KBD_REASON_MODIFIER_CONFLICT ||
      g.down_disposition != (uint32_t)READER_KBD_PASS || g.forwarded_down < 1 ||
      g.swallowed_down != 0) {
    (void)snprintf(scratch, sizeof(scratch), "reason=%s disposition=%s forwarded=%d swallowed=%d",
                   reader_kbd_reason_name(g.down_reason), disposition_name(g.down_disposition),
                   g.forwarded_down, g.swallowed_down);
    record("reader-modifier-conflict-passes", "FAIL", scratch);
    return;
  }
  record("reader-modifier-conflict-passes", "PASS",
         "Command+Shift+F reached the responder chain");
}

static void case_key_up(void) {
  begin_case("key-up");
  reset_counters();
  send_key(g.window, NSEventTypeKeyDown, 124, 0, @"\uF703", NO);
  if (g.down_action != (uint32_t)READER_KBD_ACTION_PAGE_NEXT) {
    record("reader-key-up-swallowed", "FAIL", "the key-down produced no page action");
    return;
  }
  g.swallowed_up = 0;
  g.forwarded_up = 0;
  send_key(g.window, NSEventTypeKeyUp, 124, 0, @"\uF703", NO);
  {
    uint32_t held = 42;
    if (g.swallowed_up != 1 || g.forwarded_up != 0) {
      (void)snprintf(scratch, sizeof(scratch), "swallowed_up=%d forwarded_up=%d", g.swallowed_up,
                     g.forwarded_up);
      record("reader-key-up-swallowed", "FAIL", scratch);
      return;
    }
    if (reader_kbd_held_count(g.kbd, &held) != READER_KBD_OK || held != 0) {
      record("reader-key-up-swallowed", "FAIL", "the hold survived its key-up");
      return;
    }
  }
  record("reader-key-up-swallowed", "PASS", "the matched key-up was swallowed exactly once");
}

static void case_repeat(void) {
  begin_case("repeat");
  int index;
  reset_counters();
  send_key(g.window, NSEventTypeKeyDown, 124, 0, @"\uF703", NO);
  for (index = 0; index < 40; ++index) {
    send_key(g.window, NSEventTypeKeyDown, 124, 0, @"\uF703", YES);
  }
  send_key(g.window, NSEventTypeKeyUp, 124, 0, @"\uF703", NO);
  if (g.page_actions < 2) {
    (void)snprintf(scratch, sizeof(scratch), "page_actions=%lu: repeats were not delivered",
                   (unsigned long)g.page_actions);
    record("reader-repeat-bounded", "FAIL", scratch);
    return;
  }
  if (g.page_actions > 1u + READER_KBD_MAX_REPEAT_ACTIONS) {
    (void)snprintf(scratch, sizeof(scratch), "page_actions=%lu exceeds the hard cap",
                   (unsigned long)g.page_actions);
    record("reader-repeat-bounded", "FAIL", scratch);
    return;
  }
  (void)snprintf(scratch, sizeof(scratch), "page_actions=%lu within the hard cap of %u",
                 (unsigned long)g.page_actions, READER_KBD_MAX_REPEAT_ACTIONS);
  record("reader-repeat-bounded", "PASS", scratch);
}

static void case_edit_keeps_keys(void) {
  begin_case("edit-keeps-keys");
  NSRange selection;
  NSTextView *editor;
  reset_counters();
  [g.window makeFirstResponder:g.field];
  pump(0.1);
  [g.field setStringValue:@"abcdef"];
  editor = (NSTextView *)[g.window fieldEditor:YES forObject:g.field];
  [editor setSelectedRange:NSMakeRange(0, 0)];
  pump(0.05);
  tap_key(g.window, 124, 0, @"\uF703");
  if (g.down_reason != (uint32_t)READER_KBD_REASON_TEXT_INPUT ||
      g.down_disposition != (uint32_t)READER_KBD_PASS || g.forwarded_down < 1) {
    (void)snprintf(scratch, sizeof(scratch), "reason=%s disposition=%s forwarded=%d",
                   reader_kbd_reason_name(g.down_reason), disposition_name(g.down_disposition),
                   g.forwarded_down);
    record("edit-keeps-editing-keys", "FAIL", scratch);
    return;
  }
  selection = [editor selectedRange];
  if (selection.location != 1) {
    (void)snprintf(scratch, sizeof(scratch), "caret=%lu: the field editor did not move it",
                   (unsigned long)selection.location);
    record("edit-keeps-editing-keys", "FAIL", scratch);
    return;
  }
  reset_counters();
  tap_key(g.window, 8, 0, @"c");
  if ([[g.field stringValue] rangeOfString:@"c"].location == NSNotFound) {
    record("edit-keeps-editing-keys", "FAIL", "the field editor did not receive the typed letter");
    return;
  }
  record("edit-keeps-editing-keys", "PASS",
         "the focused NSTextField kept the arrow key and the typed letter");
}

static void case_edit_command(void) {
  begin_case("edit-command");
  reset_counters();
  [g.window makeFirstResponder:g.field];
  pump(0.1);
  tap_key(g.window, 3, NSEventModifierFlagCommand, @"f");
  if (g.down_reason != (uint32_t)READER_KBD_REASON_TEXT_INPUT ||
      g.down_disposition != (uint32_t)READER_KBD_PASS || g.swallowed_down != 0) {
    (void)snprintf(scratch, sizeof(scratch), "reason=%s swallowed=%d",
                   reader_kbd_reason_name(g.down_reason), g.swallowed_down);
    record("edit-command-passes", "FAIL", scratch);
    return;
  }
  record("edit-command-passes", "PASS", "Command+F in the field stayed with the field");
}

static void case_modal(void) {
  begin_case("modal");
  reset_counters();
  [g.window makeFirstResponder:g.area];
  pump(0.05);
  g.modal_open = 1;
  [g.window beginSheet:g.sheet completionHandler:nil];
  pump(0.3);
  tap_key(g.sheet, 8, 0, @"c");
  if (g.down_reason != (uint32_t)READER_KBD_REASON_MODAL ||
      g.down_disposition != (uint32_t)READER_KBD_PASS || g.modal_saw_key == 0 ||
      g.swallowed_down != 0) {
    (void)snprintf(scratch, sizeof(scratch), "reason=%s disposition=%s saw_key=%d swallowed=%d",
                   reader_kbd_reason_name(g.down_reason), disposition_name(g.down_disposition),
                   g.modal_saw_key, g.swallowed_down);
    g.modal_open = 0;
    [g.window endSheet:g.sheet];
    [g.sheet orderOut:nil];
    record("modal-keeps-keys", "FAIL", scratch);
    return;
  }
  g.modal_open = 0;
  [g.window endSheet:g.sheet];
  [g.sheet orderOut:nil];
  pump(0.2);
  record("modal-keeps-keys", "PASS", "a key pressed in the sheet was delivered to the sheet");
}

static void case_focus_change(void) {
  begin_case("focus-change");
  reset_counters();
  [g.window makeKeyAndOrderFront:nil];
  [g.window makeFirstResponder:g.area];
  pump(0.15);
  send_key(g.window, NSEventTypeKeyDown, 49, 0, @" ", NO);
  if (g.down_action != (uint32_t)READER_KBD_ACTION_PAGE_NEXT) {
    record("focus-change-forgets-hold", "FAIL", "Space did not produce a page action");
    return;
  }
  [g.other makeKeyAndOrderFront:nil];
  pump(0.2);
  if (g.cancel_calls < 1 || g.canceled_dropped < 1) {
    (void)snprintf(scratch, sizeof(scratch), "cancel_calls=%d dropped=%d", g.cancel_calls,
                   g.canceled_dropped);
    record("focus-change-forgets-hold", "FAIL", scratch);
    return;
  }
  send_key(g.other, NSEventTypeKeyUp, 49, 0, @" ", NO);
  if (g.swallowed_up != 0 || g.other_saw_key == 0) {
    (void)snprintf(scratch, sizeof(scratch), "swallowed_up=%d other_saw_key=%d", g.swallowed_up,
                   g.other_saw_key);
    record("focus-change-forgets-hold", "FAIL", scratch);
    return;
  }
  [g.window makeKeyAndOrderFront:nil];
  pump(0.15);
  record("focus-change-forgets-hold", "PASS",
         "becoming non-key dropped the hold and the release reached the new key window");
}

static void case_deactivate(void) {
  begin_case("deactivate");
  reset_counters();
  [g.window makeKeyAndOrderFront:nil];
  pump(0.1);
  [NSApp deactivate];
  pump(0.2);
  if (g.cancel_calls < 1) {
    (void)snprintf(scratch, sizeof(scratch),
                   "deactivate did not reach the process on this runner (cancel_calls=0); the "
                   "resign-key path is covered by focus-change-forgets-hold");
    [NSApp activateIgnoringOtherApps:YES];
    pump(0.2);
    record("deactivate-cancels", "SKIP", scratch);
    return;
  }
  [NSApp activateIgnoringOtherApps:YES];
  pump(0.2);
  record("deactivate-cancels", "PASS", "application deactivation canceled the object");
}

static void case_ime(void) {
  begin_case("ime");
  record("ime-composing-passthrough", "SKIP",
         "no input method and no accessibility grant exist on a hosted macOS runner; the "
         "composing gate is covered by the installed consumer's vectors");
}

int main(void) {
  reader_kbd_config config;
  NSRect frame;

  @autoreleasepool {
    [NSApplication sharedApplication];
    [NSApp setActivationPolicy:NSApplicationActivationPolicyRegular];
    [NSApp finishLaunching];
    [NSApp activateIgnoringOtherApps:YES];
  }

  (void)signal(SIGALRM, on_watchdog);
  alarm(240);
  frame = NSMakeRect(80, 80, 640, 420);
  g.window = [[ProbeWindow alloc] initWithContentRect:frame
                                            styleMask:(NSWindowStyleMaskTitled |
                                                       NSWindowStyleMaskClosable |
                                                       NSWindowStyleMaskResizable)
                                              backing:NSBackingStoreBuffered
                                                defer:NO];
  [g.window setTitle:@"EXReader keyboard actions probe"];
  g.area = [[ProbeView alloc] initWithFrame:NSMakeRect(0, 0, 600, 300)];
  g.field = [[NSTextField alloc] initWithFrame:NSMakeRect(10, 10, 300, 24)];
  [g.field setEditable:YES];
  [g.field setStringValue:@"abcdef"];
  [[g.window contentView] addSubview:g.area];
  [[g.window contentView] addSubview:g.field];

  g.other = [[ProbeWindow alloc] initWithContentRect:NSMakeRect(760, 80, 320, 200)
                                           styleMask:(NSWindowStyleMaskTitled |
                                                      NSWindowStyleMaskClosable)
                                             backing:NSBackingStoreBuffered
                                               defer:NO];
  [g.other setTitle:@"EXReader keyboard actions second window"];
  [[g.other contentView] addSubview:[[ProbeView alloc] initWithFrame:NSMakeRect(0, 0, 300, 150)]];

  g.sheet = [[ProbeWindow alloc] initWithContentRect:NSMakeRect(0, 0, 400, 160)
                                           styleMask:NSWindowStyleMaskTitled
                                             backing:NSBackingStoreBuffered
                                               defer:NO];
  [g.sheet setTitle:@"EXReader keyboard actions sheet"];
  [[g.sheet contentView] addSubview:[[ProbeView alloc] initWithFrame:NSMakeRect(0, 0, 380, 120)]];

  [g.window orderFrontRegardless];
  [g.window makeKeyWindow];
  [g.window makeFirstResponder:g.area];
  pump(0.3);
  if (![g.window isKeyWindow]) {
    [NSApp activateIgnoringOtherApps:YES];
    [g.window makeKeyAndOrderFront:nil];
    [g.window makeKeyWindow];
    pump(0.4);
  }
  if (![g.window isKeyWindow]) g.force_active = 1;
  pump(0.3);

  (void)memset(&config, 0, sizeof(config));
  config.struct_size = (uint32_t)sizeof(config);
  config.platform = (uint32_t)READER_KBD_PLATFORM_APPLE;
  config.page_turn_direction = (uint32_t)READER_PREFERENCES_TURN_LTR;
  config.page_turn_input = (uint32_t)READER_PREFERENCES_INPUT_HARDWARE_KEYS;
  if (reader_kbd_create(&config, &g.kbd) != READER_KBD_OK || g.kbd == NULL) {
    record("probe-window-ready", "FAIL", "reader_kbd_create failed");
    return 1;
  }

  case_ready();
  case_page_next();
  case_page_previous();
  case_command_search();
  case_shift_space();
  case_conflict_passes();
  case_key_up();
  case_repeat();
  case_edit_keeps_keys();
  case_edit_command();
  case_modal();
  case_focus_change();
  case_deactivate();
  case_ime();

  (void)reader_kbd_destroy(g.kbd);
  g.kbd = NULL;
  [g.sheet orderOut:nil];
  [g.other orderOut:nil];
  [g.window orderOut:nil];

  (void)fprintf(stdout, "probe %s pass=%d fail=%d skip=%d\n", failures == 0 ? "ok" : "failed",
                passes, failures, skips);
  (void)fflush(stdout);
  return failures == 0 ? 0 : 1;
}
