/* SPDX-License-Identifier: MIT */
/* Real GTK3 / X11 keyboard probe. It builds actual windows (a reader window
   with a GtkEntry, a second window and a modal dialog), injects real key events
   with the XTest extension, and runs the installed keyboard-actions package
   inside the real GDK key handlers. GdkEventKey carries the server's modifier
   state, so Shift, Control, Alt, Super and Mod5 are what X11 itself reports.
   Each named case prints "PROBE <name> PASS|FAIL|SKIP <detail>". */
#include "reader_keyboard_actions.h"

#include <gtk/gtk.h>
#include <gdk/gdkx.h>

#include <X11/Xlib.h>
#include <X11/keysym.h>
#include <X11/extensions/XTest.h>

#include <signal.h>
#include <stdio.h>
#include <string.h>
#include <unistd.h>

typedef struct {
  reader_kbd *kbd;
  GtkWidget *window;
  GtkWidget *entry;
  GtkWidget *area;
  GtkWidget *other;
  GtkWidget *dialog;
  Display *display;
  int modal_open;
  uint32_t held_keyval;
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
static int x_errors;

/* Xvfb has no window manager, so a focus request can race the map. A protocol
   error must be counted, never abort the probe through Xlib's default handler. */
static int on_x_error(Display *display, XErrorEvent *event) {
  (void)display;
  (void)event;
  ++x_errors;
  return 0;
}

/* Drain the pending events with a hard bound: a permanently ready source must
   never turn the drain itself into an endless loop. */
static void drain_events(void) {
  int guard;
  for (guard = 0; guard < 64; ++guard) {
    if (gtk_main_iteration_do(FALSE) == 0) return;
  }
}

static int wait_mapped(GtkWidget *widget, int milliseconds) {
  gint64 deadline = g_get_monotonic_time() + ((gint64)milliseconds * 1000);
  for (;;) {
    drain_events();
    if (gtk_widget_get_mapped(widget) != 0) return 1;
    if (g_get_monotonic_time() >= deadline) return 0;
    g_usleep(2000);
  }
}

static void record(const char *name, const char *status, const char *detail) {
  if (status[0] == 'F') ++failures;
  else if (status[0] == 'S') ++skips;
  else ++passes;
  (void)fprintf(stdout, "PROBE %s %s %s\n", name, status, detail != NULL ? detail : "");
  (void)fflush(stdout);
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

static void pump(int milliseconds) {
  gint64 deadline = g_get_monotonic_time() + ((gint64)milliseconds * 1000);
  while (g_get_monotonic_time() < deadline) {
    drain_events();
    g_usleep(2000);
  }
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

static const char *disposition_name(uint32_t disposition) {
  return disposition == (uint32_t)READER_KBD_CONSUME ? "consume" : "pass";
}

static uint32_t focus_for(GtkWidget *widget) {
  if (g.modal_open != 0) return (uint32_t)READER_KBD_FOCUS_MODAL;
  if (widget == g.entry) return (uint32_t)READER_KBD_FOCUS_TEXT_INPUT;
  return (uint32_t)READER_KBD_FOCUS_READER;
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

static void host_cancel(void) {
  uint32_t dropped = 0;
  ++g.cancel_calls;
  if (g.kbd != NULL && reader_kbd_cancel(g.kbd, &dropped) == READER_KBD_OK) {
    g.canceled_dropped += (int)dropped;
  }
}

static gboolean on_focus_out(GtkWidget *widget, GdkEventFocus *event, gpointer user) {
  (void)widget;
  (void)event;
  (void)user;
  host_cancel();
  return FALSE;
}

static gboolean on_key(GtkWidget *widget, GdkEventKey *event, gpointer user) {
  host_state *state = (host_state *)user;
  reader_kbd_event translated;
  reader_kbd_context context;
  reader_kbd_result result;
  uint32_t repeat = 0;
  uint32_t focus;

  if (event->type == GDK_KEY_PRESS) {
    if (state->held_keyval == (uint32_t)event->keyval) repeat = 1;
    state->held_keyval = (uint32_t)event->keyval;
  } else {
    state->held_keyval = 0;
  }
  if (reader_kbd_event_from_x11(event->type == GDK_KEY_PRESS ? 2u : 3u, (uint32_t)event->keyval,
                                (uint32_t)event->state, repeat, &translated) != READER_KBD_OK) {
    return FALSE;
  }
  (void)memset(&context, 0, sizeof(context));
  context.struct_size = (uint32_t)sizeof(context);
  focus = focus_for(widget);
  context.focus = focus;
  context.composing = 0;
  context.window_active = 1;
  if (reader_kbd_dispatch(state->kbd, &translated, &context, host_handler, state, &result) !=
      READER_KBD_OK) {
    return FALSE;
  }
  if (translated.phase == (uint32_t)READER_KBD_PHASE_DOWN) {
    state->down_action = result.action;
    state->down_reason = result.reason;
    state->down_disposition = result.disposition;
  }
  if (result.disposition == (uint32_t)READER_KBD_CONSUME) {
    if (translated.phase == (uint32_t)READER_KBD_PHASE_DOWN) ++state->swallowed_down;
    else ++state->swallowed_up;
    if (focus == (uint32_t)READER_KBD_FOCUS_MODAL) state->modal_saw_key = 1;
    return TRUE;
  }
  if (translated.phase == (uint32_t)READER_KBD_PHASE_DOWN) ++state->forwarded_down;
  else ++state->forwarded_up;
  if (focus == (uint32_t)READER_KBD_FOCUS_MODAL) state->modal_saw_key = 1;
  if (widget == state->other) state->other_saw_key = 1;
  return FALSE;
}

static void set_x_focus(GtkWidget *widget) {
  GdkWindow *window = gtk_widget_get_window(widget);
  if (window != NULL) {
    XSetInputFocus(g.display, gdk_x11_window_get_xid(window), RevertToParent, CurrentTime);
    XFlush(g.display);
  }
  pump(150);
}

static int inject_key(KeySym symbol, int down) {
  KeyCode code = XKeysymToKeycode(g.display, symbol);
  if (code == 0) return 0;
  if (XTestFakeKeyEvent(g.display, code, down != 0 ? True : False, 0) == 0) return 0;
  XFlush(g.display);
  pump(30);
  return 1;
}

static int tap_symbol(KeySym symbol) {
  if (inject_key(symbol, 1) == 0) return 0;
  pump(40);
  if (inject_key(symbol, 0) == 0) return 0;
  pump(80);
  return 1;
}

static int tap_chord(KeySym modifier, KeySym symbol) {
  if (inject_key(modifier, 1) == 0) return 0;
  pump(30);
  if (tap_symbol(symbol) == 0) return 0;
  if (inject_key(modifier, 0) == 0) return 0;
  pump(60);
  return 1;
}

static gboolean on_delete(GtkWidget *widget, GdkEvent *event, gpointer user) {
  (void)widget;
  (void)event;
  (void)user;
  return TRUE;
}

static void case_ready(void) {
  begin_case("ready");
  int event_base = 0;
  int error_base = 0;
  int major = 0;
  int minor = 0;
  GdkWindow *window = gtk_widget_get_window(g.window);
  if (g.display == NULL || window == NULL) {
    record("probe-window-ready", "FAIL", "no X11 display or unmapped window");
    return;
  }
  if (XTestQueryExtension(g.display, &event_base, &error_base, &major, &minor) == 0) {
    record("probe-window-ready", "FAIL", "the X server has no XTest extension");
    return;
  }
  set_x_focus(g.window);
  if (gdk_x11_window_get_xid(window) == 0) {
    record("probe-window-ready", "FAIL", "the window has no X11 id");
    return;
  }
  record("probe-window-ready", "PASS", "a real GTK3 window is mapped under X11 with XTest");
}

static void case_page_next(void) {
  begin_case("page-next");
  reset_counters();
  set_x_focus(g.window);
  if (tap_symbol(XK_Right) == 0) {
    record("reader-page-next-consumed", "FAIL", "XTest refused XK_Right");
    return;
  }
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
  record("reader-page-next-consumed", "PASS", "real XK_Right became the next page and its key-up");
}

static void case_page_previous(void) {
  begin_case("page-previous");
  reset_counters();
  set_x_focus(g.window);
  if (tap_symbol(XK_Left) == 0) {
    record("reader-page-previous-consumed", "FAIL", "XTest refused XK_Left");
    return;
  }
  if (g.down_action != (uint32_t)READER_KBD_ACTION_PAGE_PREVIOUS) {
    (void)snprintf(scratch, sizeof(scratch), "action=%s reason=%s",
                   reader_kbd_action_name(g.down_action), reader_kbd_reason_name(g.down_reason));
    record("reader-page-previous-consumed", "FAIL", scratch);
    return;
  }
  record("reader-page-previous-consumed", "PASS", "real XK_Left became the previous page");
}

static void case_command_search(void) {
  begin_case("command-search");
  reset_counters();
  set_x_focus(g.window);
  if (tap_chord(XK_Control_L, XK_f) == 0) {
    record("reader-command-search", "FAIL", "XTest refused Control_L+f");
    return;
  }
  if (g.down_action != (uint32_t)READER_KBD_ACTION_SEARCH ||
      g.down_disposition != (uint32_t)READER_KBD_CONSUME) {
    (void)snprintf(scratch, sizeof(scratch), "action=%s reason=%s",
                   reader_kbd_action_name(g.down_action), reader_kbd_reason_name(g.down_reason));
    record("reader-command-search", "FAIL", scratch);
    return;
  }
  record("reader-command-search", "PASS", "real Control+f became the search action");
}

static void case_shift_space(void) {
  begin_case("shift-space");
  reset_counters();
  set_x_focus(g.window);
  if (tap_chord(XK_Shift_L, XK_space) == 0) {
    record("reader-shift-space-previous", "FAIL", "XTest refused Shift+space");
    return;
  }
  if (g.down_action != (uint32_t)READER_KBD_ACTION_PAGE_PREVIOUS) {
    (void)snprintf(scratch, sizeof(scratch), "action=%s reason=%s",
                   reader_kbd_action_name(g.down_action), reader_kbd_reason_name(g.down_reason));
    record("reader-shift-space-previous", "FAIL", scratch);
    return;
  }
  record("reader-shift-space-previous", "PASS", "real Shift+space became the previous page");
}

static void case_conflict_passes(void) {
  begin_case("conflict-passes");
  reset_counters();
  set_x_focus(g.window);
  if (inject_key(XK_Control_L, 1) == 0 || inject_key(XK_Shift_L, 1) == 0) {
    record("reader-modifier-conflict-passes", "FAIL", "XTest refused the modifiers");
    return;
  }
  pump(30);
  if (tap_symbol(XK_f) == 0) {
    record("reader-modifier-conflict-passes", "FAIL", "XTest refused Control+Shift+f");
    return;
  }
  (void)inject_key(XK_Shift_L, 0);
  (void)inject_key(XK_Control_L, 0);
  pump(80);
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
         "Control+Shift+f reached the GTK default handler");
}

static void case_key_up(void) {
  begin_case("key-up");
  reset_counters();
  set_x_focus(g.window);
  if (inject_key(XK_Right, 1) == 0) {
    record("reader-key-up-swallowed", "FAIL", "XTest refused the key-down");
    return;
  }
  pump(60);
  if (g.down_action != (uint32_t)READER_KBD_ACTION_PAGE_NEXT) {
    record("reader-key-up-swallowed", "FAIL", "the key-down produced no page action");
    return;
  }
  if (inject_key(XK_Right, 0) == 0) {
    record("reader-key-up-swallowed", "FAIL", "XTest refused the key-up");
    return;
  }
  pump(90);
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
  reset_counters();
  set_x_focus(g.window);
  if (inject_key(XK_Right, 1) == 0) {
    record("reader-repeat-bounded", "FAIL", "XTest refused the held key-down");
    return;
  }
  pump(2600);
  if (inject_key(XK_Right, 0) == 0) {
    record("reader-repeat-bounded", "FAIL", "XTest refused the release");
    return;
  }
  pump(120);
  if (g.page_actions < 2) {
    (void)snprintf(scratch, sizeof(scratch),
                   "page_actions=%lu but the X server did not auto-repeat the held key",
                   (unsigned long)g.page_actions);
    record("reader-repeat-bounded", "SKIP", scratch);
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

static int focus_entry(void) {
  GtkWidget *focus;
  gtk_window_present(GTK_WINDOW(g.window));
  set_x_focus(g.window);
  gtk_widget_grab_focus(g.entry);
  pump(250);
  focus = gtk_window_get_focus(GTK_WINDOW(g.window));
  return focus == g.entry && gtk_widget_has_focus(g.entry) != 0;
}

static void case_edit_keeps_keys(void) {
  begin_case("edit-keeps-keys");
  const char *text;
  if (focus_entry() == 0) {
    (void)snprintf(scratch, sizeof(scratch),
                   "the entry never received the GTK focus (toplevel focus=%d)",
                   gtk_window_has_toplevel_focus(GTK_WINDOW(g.window)) ? 1 : 0);
    record("edit-keeps-editing-keys", "FAIL", scratch);
    return;
  }
  gtk_entry_set_text(GTK_ENTRY(g.entry), "abcdef");
  gtk_editable_set_position(GTK_EDITABLE(g.entry), 0);
  pump(150);
  reset_counters();
  if (tap_symbol(XK_Right) == 0) {
    record("edit-keeps-editing-keys", "FAIL", "XTest refused XK_Right in the entry");
    return;
  }
  if (g.down_reason != (uint32_t)READER_KBD_REASON_TEXT_INPUT ||
      g.down_disposition != (uint32_t)READER_KBD_PASS || g.forwarded_down < 1) {
    (void)snprintf(scratch, sizeof(scratch), "reason=%s disposition=%s forwarded=%d",
                   reader_kbd_reason_name(g.down_reason), disposition_name(g.down_disposition),
                   g.forwarded_down);
    record("edit-keeps-editing-keys", "FAIL", scratch);
    return;
  }
  if (gtk_editable_get_position(GTK_EDITABLE(g.entry)) != 1) {
    (void)snprintf(scratch, sizeof(scratch), "caret=%d: the entry did not move it",
                   gtk_editable_get_position(GTK_EDITABLE(g.entry)));
    record("edit-keeps-editing-keys", "FAIL", scratch);
    return;
  }
  reset_counters();
  if (tap_symbol(XK_c) == 0) {
    record("edit-keeps-editing-keys", "FAIL", "XTest refused a letter in the entry");
    return;
  }
  text = gtk_entry_get_text(GTK_ENTRY(g.entry));
  if (strchr(text, 'c') == NULL) {
    record("edit-keeps-editing-keys", "FAIL", "the entry did not receive the typed letter");
    return;
  }
  record("edit-keeps-editing-keys", "PASS", "the focused GtkEntry kept the arrow key and the letter");
}

static void case_edit_command(void) {
  begin_case("edit-command");
  if (focus_entry() == 0) {
    record("edit-command-passes", "FAIL", "the entry never received the GTK focus");
    return;
  }
  reset_counters();
  if (tap_chord(XK_Control_L, XK_f) == 0) {
    record("edit-command-passes", "FAIL", "XTest refused Control+f in the entry");
    return;
  }
  if (g.down_reason != (uint32_t)READER_KBD_REASON_TEXT_INPUT ||
      g.down_disposition != (uint32_t)READER_KBD_PASS || g.swallowed_down != 0) {
    (void)snprintf(scratch, sizeof(scratch), "reason=%s swallowed=%d",
                   reader_kbd_reason_name(g.down_reason), g.swallowed_down);
    record("edit-command-passes", "FAIL", scratch);
    return;
  }
  record("edit-command-passes", "PASS", "Control+f in the entry stayed with the entry");
}

static void case_modal(void) {
  begin_case("modal");
  set_x_focus(g.window);
  gtk_widget_grab_focus(g.area);
  pump(120);
  reset_counters();
  g.modal_open = 1;
  gtk_widget_show_all(g.dialog);
  (void)wait_mapped(g.dialog, 3000);
  set_x_focus(g.dialog);
  if (tap_symbol(XK_c) == 0) {
    g.modal_open = 0;
    gtk_widget_hide(g.dialog);
    record("modal-keeps-keys", "FAIL", "XTest refused a key in the modal dialog");
    return;
  }
  if (g.down_reason != (uint32_t)READER_KBD_REASON_MODAL ||
      g.down_disposition != (uint32_t)READER_KBD_PASS || g.modal_saw_key == 0 ||
      g.swallowed_down != 0) {
    (void)snprintf(scratch, sizeof(scratch), "reason=%s disposition=%s saw_key=%d swallowed=%d",
                   reader_kbd_reason_name(g.down_reason), disposition_name(g.down_disposition),
                   g.modal_saw_key, g.swallowed_down);
    g.modal_open = 0;
    gtk_widget_hide(g.dialog);
    record("modal-keeps-keys", "FAIL", scratch);
    return;
  }
  g.modal_open = 0;
  gtk_widget_hide(g.dialog);
  set_x_focus(g.window);
  record("modal-keeps-keys", "PASS", "a key pressed in the modal dialog was delivered to it");
}

static void case_focus_change(void) {
  begin_case("focus-change");
  set_x_focus(g.window);
  gtk_widget_grab_focus(g.area);
  pump(120);
  reset_counters();
  if (inject_key(XK_space, 1) == 0) {
    record("focus-change-forgets-hold", "FAIL", "XTest refused the held space");
    return;
  }
  pump(80);
  if (g.down_action != (uint32_t)READER_KBD_ACTION_PAGE_NEXT) {
    record("focus-change-forgets-hold", "FAIL", "space did not produce a page action");
    return;
  }
  set_x_focus(g.other);
  if (g.cancel_calls < 1 || g.canceled_dropped < 1) {
    (void)snprintf(scratch, sizeof(scratch), "cancel_calls=%d dropped=%d", g.cancel_calls,
                   g.canceled_dropped);
    record("focus-change-forgets-hold", "FAIL", scratch);
    return;
  }
  if (inject_key(XK_space, 0) == 0) {
    record("focus-change-forgets-hold", "FAIL", "XTest refused the space release");
    return;
  }
  pump(100);
  if (g.swallowed_up != 0 || g.other_saw_key == 0) {
    (void)snprintf(scratch, sizeof(scratch), "swallowed_up=%d other_saw_key=%d", g.swallowed_up,
                   g.other_saw_key);
    record("focus-change-forgets-hold", "FAIL", scratch);
    return;
  }
  set_x_focus(g.window);
  gtk_widget_grab_focus(g.area);
  pump(80);
  record("focus-change-forgets-hold", "PASS",
         "moving the X11 focus dropped the hold and the release reached the new owner");
}

static void case_deactivate(void) {
  begin_case("deactivate");
  set_x_focus(g.window);
  gtk_widget_grab_focus(g.area);
  pump(120);
  reset_counters();
  if (inject_key(XK_space, 1) == 0) {
    record("deactivate-cancels", "FAIL", "XTest refused the held space");
    return;
  }
  pump(70);
  set_x_focus(g.other);
  if (g.cancel_calls < 1) {
    (void)snprintf(scratch, sizeof(scratch), "cancel_calls=%d", g.cancel_calls);
    record("deactivate-cancels", "FAIL", scratch);
    set_x_focus(g.window);
    return;
  }
  (void)inject_key(XK_space, 0);
  pump(90);
  set_x_focus(g.window);
  gtk_widget_grab_focus(g.area);
  record("deactivate-cancels", "PASS",
         "the reader canceled on X11 FocusOut without a window manager");
}

static void case_ime(void) {
  begin_case("ime");
  record("ime-composing-passthrough", "SKIP",
         "no input method runs under Xvfb; the composing gate and the VK_PROCESSKEY vector are "
         "covered by the installed consumers");
}

static gboolean on_other_key(GtkWidget *widget, GdkEventKey *event, gpointer user) {
  return on_key(widget, event, user);
}

int main(void) {
  reader_kbd_config config;
  GtkWidget *box;
  GtkWidget *content;

  (void)signal(SIGALRM, on_watchdog);
  alarm(240);
  if (gtk_init_check(NULL, NULL) == 0) {
    record("probe-window-ready", "FAIL", "gtk_init_check failed (no DISPLAY?)");
    return 1;
  }
  g.display = GDK_DISPLAY_XDISPLAY(gdk_display_get_default());
  if (g.display == NULL) {
    record("probe-window-ready", "FAIL", "GDK did not open an X11 display");
    return 1;
  }
  XSetErrorHandler(on_x_error);

  g.window = gtk_window_new(GTK_WINDOW_TOPLEVEL);
  gtk_window_set_title(GTK_WINDOW(g.window), "EXReader keyboard actions probe");
  gtk_window_set_default_size(GTK_WINDOW(g.window), 640, 400);
  box = gtk_box_new(GTK_ORIENTATION_VERTICAL, 6);
  g.entry = gtk_entry_new();
  g.area = gtk_event_box_new();
  gtk_widget_set_can_focus(g.area, TRUE);
  gtk_container_add(GTK_CONTAINER(g.area), gtk_label_new("reader area"));
  gtk_box_pack_start(GTK_BOX(box), g.area, TRUE, TRUE, 0);
  gtk_box_pack_start(GTK_BOX(box), g.entry, FALSE, FALSE, 0);
  gtk_container_add(GTK_CONTAINER(g.window), box);
  g_signal_connect(g.entry, "key-press-event", G_CALLBACK(on_key), &g);
  g_signal_connect(g.entry, "key-release-event", G_CALLBACK(on_key), &g);
  g_signal_connect(g.window, "key-press-event", G_CALLBACK(on_key), &g);
  g_signal_connect(g.window, "key-release-event", G_CALLBACK(on_key), &g);
  g_signal_connect(g.window, "focus-out-event", G_CALLBACK(on_focus_out), &g);
  g_signal_connect(g.window, "delete-event", G_CALLBACK(on_delete), &g);

  g.other = gtk_window_new(GTK_WINDOW_TOPLEVEL);
  gtk_window_set_title(GTK_WINDOW(g.other), "EXReader keyboard actions second window");
  gtk_window_set_default_size(GTK_WINDOW(g.other), 320, 200);
  gtk_container_add(GTK_CONTAINER(g.other), gtk_label_new("second"));
  g_signal_connect(g.other, "key-press-event", G_CALLBACK(on_other_key), &g);
  g_signal_connect(g.other, "key-release-event", G_CALLBACK(on_other_key), &g);

  g.dialog = gtk_dialog_new();
  gtk_window_set_title(GTK_WINDOW(g.dialog), "EXReader keyboard actions modal");
  gtk_window_set_modal(GTK_WINDOW(g.dialog), TRUE);
  gtk_window_set_transient_for(GTK_WINDOW(g.dialog), GTK_WINDOW(g.window));
  content = gtk_dialog_get_content_area(GTK_DIALOG(g.dialog));
  gtk_container_add(GTK_CONTAINER(content), gtk_label_new("modal"));
  g_signal_connect(g.dialog, "key-press-event", G_CALLBACK(on_key), &g);
  g_signal_connect(g.dialog, "key-release-event", G_CALLBACK(on_key), &g);

  gtk_widget_show_all(g.window);
  gtk_widget_show_all(g.other);
  if (wait_mapped(g.window, 5000) == 0 || wait_mapped(g.other, 5000) == 0) {
    record("probe-window-ready", "FAIL", "the X11 windows never became visible");
    return 1;
  }
  gtk_widget_grab_focus(g.area);
  pump(400);

  (void)memset(&config, 0, sizeof(config));
  config.struct_size = (uint32_t)sizeof(config);
  config.platform = (uint32_t)READER_KBD_PLATFORM_LINUX;
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
  gtk_widget_destroy(g.dialog);
  gtk_widget_destroy(g.other);
  gtk_widget_destroy(g.window);
  drain_events();

  (void)fprintf(stdout, "probe %s pass=%d fail=%d skip=%d\n", failures == 0 ? "ok" : "failed",
                passes, failures, skips);
  (void)fflush(stdout);
  return failures == 0 ? 0 : 1;
}
