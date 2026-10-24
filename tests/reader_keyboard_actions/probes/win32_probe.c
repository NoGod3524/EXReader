/* SPDX-License-Identifier: MIT */
/* Real Win32 keyboard probe. It creates an actual top-level window with an EDIT
   child and a second modal window, injects real keyboard input with SendInput,
   and runs the installed keyboard-actions package inside the real window
   procedure. Nothing here mocks a message: the numbers the module sees come from
   the messages Windows itself generated, and the modifier state is read with
   GetKeyState at event time. Each named case prints
   "PROBE <name> PASS|FAIL|SKIP <detail>". */
#if defined(_MSC_VER) && !defined(_CRT_SECURE_NO_WARNINGS)
#define _CRT_SECURE_NO_WARNINGS 1
#endif
#include "reader_keyboard_actions.h"

#include <windows.h>
#include <commctrl.h>

#include <stdio.h>
#include <string.h>
#include <wchar.h>

#define PROBE_CLASS L"ExrKbdProbeWindow"

typedef struct {
  reader_kbd *kbd;
  HWND window;
  HWND edit;
  HWND other;
  HWND modal;
  int modal_open;
  int active;
  int canceled_dropped;
  int cancel_calls;
  uint32_t down_action;
  uint32_t down_reason;
  uint32_t down_disposition;
  uint32_t down_repeat;
  uint32_t page_actions;
  int forwarded_down;
  int forwarded_up;
  int swallowed_down;
  int swallowed_up;
  int modal_saw_key;
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

static void reset_counters(void) {
  g.down_action = 0xffffffffu;
  g.down_reason = 0xffffffffu;
  g.down_disposition = 0xffffffffu;
  g.down_repeat = 0;
  g.page_actions = 0;
  g.forwarded_down = 0;
  g.forwarded_up = 0;
  g.swallowed_down = 0;
  g.swallowed_up = 0;
  g.modal_saw_key = 0;
  g.canceled_dropped = 0;
  g.cancel_calls = 0;
}

static uint32_t win_modifiers(void) {
  uint32_t modifiers = 0;
  if ((GetKeyState(VK_SHIFT) & 0x8000) != 0) modifiers |= READER_KBD_WIN32_SHIFT;
  if ((GetKeyState(VK_CONTROL) & 0x8000) != 0) modifiers |= READER_KBD_WIN32_CTRL;
  if ((GetKeyState(VK_LMENU) & 0x8000) != 0) modifiers |= READER_KBD_WIN32_LALT;
  if ((GetKeyState(VK_RMENU) & 0x8000) != 0) modifiers |= READER_KBD_WIN32_RALT;
  if ((GetKeyState(VK_LWIN) & 0x8000) != 0 || (GetKeyState(VK_RWIN) & 0x8000) != 0) {
    modifiers |= READER_KBD_WIN32_WIN;
  }
  return modifiers;
}

static uint32_t window_active(void) {
  /* A modal window of this application is still this application being active. */
  return GetActiveWindow() != NULL ? 1u : 0u;
}

static uint32_t focus_for(HWND source) {
  if (g.modal_open != 0) return (uint32_t)READER_KBD_FOCUS_MODAL;
  if (source == g.edit) return (uint32_t)READER_KBD_FOCUS_TEXT_INPUT;
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

static int deliver(UINT message, WPARAM wparam, LPARAM lparam, HWND source) {
  reader_kbd_event event;
  reader_kbd_context context;
  reader_kbd_result result;
  uint32_t composing = 0;
  uint32_t focus;
  if (g.kbd == NULL) return 0;
  if (reader_kbd_event_from_win32((uint32_t)message, (uint64_t)wparam, (int64_t)lparam,
                                  win_modifiers(), &event, &composing) != READER_KBD_OK) {
    return 0;
  }
  (void)memset(&context, 0, sizeof(context));
  context.struct_size = (uint32_t)sizeof(context);
  focus = focus_for(source);
  context.focus = focus;
  context.composing = composing;
  context.window_active = window_active();
  if (reader_kbd_dispatch(g.kbd, &event, &context, host_handler, &g, &result) != READER_KBD_OK) {
    return 0;
  }
  if (event.phase == (uint32_t)READER_KBD_PHASE_DOWN) {
    g.down_action = result.action;
    g.down_reason = result.reason;
    g.down_disposition = result.disposition;
    g.down_repeat = result.repeat_actions;
  }
  if (result.disposition == (uint32_t)READER_KBD_CONSUME) {
    if (event.phase == (uint32_t)READER_KBD_PHASE_DOWN) ++g.swallowed_down;
    else ++g.swallowed_up;
    if (focus == (uint32_t)READER_KBD_FOCUS_MODAL) g.modal_saw_key = 1;
    return 1;
  }
  if (event.phase == (uint32_t)READER_KBD_PHASE_DOWN) ++g.forwarded_down;
  else ++g.forwarded_up;
  if (focus == (uint32_t)READER_KBD_FOCUS_MODAL) g.modal_saw_key = 1;
  return 0;
}

static void host_cancel(void) {
  uint32_t dropped = 0;
  ++g.cancel_calls;
  if (g.kbd != NULL && reader_kbd_cancel(g.kbd, &dropped) == READER_KBD_OK) {
    g.canceled_dropped += (int)dropped;
  }
}

static LRESULT CALLBACK window_proc(HWND window, UINT message, WPARAM wparam, LPARAM lparam);
static LRESULT CALLBACK modal_proc(HWND window, UINT message, WPARAM wparam, LPARAM lparam);

static LRESULT CALLBACK modal_proc(HWND window, UINT message, WPARAM wparam, LPARAM lparam) {
  if (message == WM_KEYDOWN || message == WM_KEYUP || message == WM_SYSKEYDOWN ||
      message == WM_SYSKEYUP) {
    if (deliver(message, wparam, lparam, window) != 0) return 0;
  } else if (message == WM_KILLFOCUS) {
    host_cancel();
  }
  return DefWindowProcW(window, message, wparam, lparam);
}

static LRESULT CALLBACK window_proc(HWND window, UINT message, WPARAM wparam, LPARAM lparam) {
  switch (message) {
    case WM_KEYDOWN:
    case WM_KEYUP:
    case WM_SYSKEYDOWN:
    case WM_SYSKEYUP:
      if (deliver(message, wparam, lparam, window) != 0) return 0;
      break;
    case WM_ACTIVATE:
      if (window == g.window) {
        g.active = LOWORD(wparam) == WA_INACTIVE ? 0 : 1;
        if (g.active == 0) host_cancel();
      }
      break;
    case WM_KILLFOCUS:
      if (window == g.window) host_cancel();
      break;
    default:
      break;
  }
  return DefWindowProcW(window, message, wparam, lparam);
}

static LRESULT CALLBACK edit_proc(HWND window, UINT message, WPARAM wparam, LPARAM lparam,
                                  UINT_PTR id, DWORD_PTR reference) {
  (void)id;
  (void)reference;
  if (message == WM_KEYDOWN || message == WM_KEYUP || message == WM_SYSKEYDOWN ||
      message == WM_SYSKEYUP) {
    if (deliver(message, wparam, lparam, window) != 0) return 0;
  }
  return DefSubclassProc(window, message, wparam, lparam);
}

static void pump(DWORD milliseconds) {
  DWORD deadline = GetTickCount() + milliseconds;
  MSG message;
  while ((int)(GetTickCount() - deadline) < 0) {
    while (PeekMessageW(&message, NULL, 0, 0, PM_REMOVE) != 0) {
      TranslateMessage(&message);
      DispatchMessageW(&message);
    }
    Sleep(2);
  }
}

static int inject(WORD key, int down) {
  INPUT input;
  (void)memset(&input, 0, sizeof(input));
  input.type = INPUT_KEYBOARD;
  input.ki.wVk = key;
  input.ki.wScan = (WORD)MapVirtualKeyW(key, MAPVK_VK_TO_VSC);
  input.ki.dwFlags = down != 0 ? 0u : KEYEVENTF_KEYUP;
  return SendInput(1, &input, (int)sizeof(input)) == 1;
}

static int tap_word(WORD key) {
  if (inject(key, 1) == 0) return 0;
  pump(40);
  if (inject(key, 0) == 0) return 0;
  pump(80);
  return 1;
}

static int tap_chord(WORD modifier, WORD key) {
  if (inject(modifier, 1) == 0) return 0;
  pump(30);
  if (tap_word(key) == 0) return 0;
  if (inject(modifier, 0) == 0) return 0;
  pump(60);
  return 1;
}

static int tap_two(WORD first, WORD second) {
  if (inject(first, 1) == 0) return 0;
  pump(30);
  if (tap_word(second) == 0) return 0;
  if (inject(first, 0) == 0) return 0;
  pump(60);
  return 1;
}

static int focus_window(HWND window) {
  ShowWindow(window, SW_SHOW);
  SetForegroundWindow(window);
  SetActiveWindow(window);
  SetFocus(window);
  pump(150);
  return GetForegroundWindow() == window;
}

static const char *disposition_name(uint32_t disposition) {
  return disposition == (uint32_t)READER_KBD_CONSUME ? "consume" : "pass";
}

static void case_ready(void) {
  if (focus_window(g.window) == 0) {
    (void)snprintf(scratch, sizeof(scratch),
                   "foreground activation failed: foreground=%p window=%p",
                   (void *)GetForegroundWindow(), (void *)g.window);
    record("probe-window-ready", "FAIL", scratch);
    return;
  }
  if (GetFocus() != g.window) {
    record("probe-window-ready", "FAIL", "the probe window does not hold the keyboard focus");
    return;
  }
  record("probe-window-ready", "PASS", "the probe window is foreground and holds focus");
}

static void case_page_next(void) {
  reset_counters();
  if (tap_word(VK_RIGHT) == 0) {
    record("reader-page-next-consumed", "FAIL", "SendInput refused VK_RIGHT");
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
  record("reader-page-next-consumed", "PASS", "real VK_RIGHT became the next page and its key-up");
}

static void case_page_previous(void) {
  reset_counters();
  if (tap_word(VK_LEFT) == 0) {
    record("reader-page-previous-consumed", "FAIL", "SendInput refused VK_LEFT");
    return;
  }
  if (g.down_action != (uint32_t)READER_KBD_ACTION_PAGE_PREVIOUS ||
      g.down_disposition != (uint32_t)READER_KBD_CONSUME) {
    (void)snprintf(scratch, sizeof(scratch), "action=%s reason=%s",
                   reader_kbd_action_name(g.down_action), reader_kbd_reason_name(g.down_reason));
    record("reader-page-previous-consumed", "FAIL", scratch);
    return;
  }
  record("reader-page-previous-consumed", "PASS", "real VK_LEFT became the previous page");
}

static void case_command_search(void) {
  reset_counters();
  if (tap_chord(VK_CONTROL, 'F') == 0) {
    record("reader-command-search", "FAIL", "SendInput refused Ctrl+F");
    return;
  }
  if (g.down_action != (uint32_t)READER_KBD_ACTION_SEARCH ||
      g.down_disposition != (uint32_t)READER_KBD_CONSUME) {
    (void)snprintf(scratch, sizeof(scratch), "action=%s reason=%s",
                   reader_kbd_action_name(g.down_action), reader_kbd_reason_name(g.down_reason));
    record("reader-command-search", "FAIL", scratch);
    return;
  }
  record("reader-command-search", "PASS", "real Ctrl+F became the search action");
}

static void case_shift_space(void) {
  reset_counters();
  if (tap_two(VK_SHIFT, VK_SPACE) == 0) {
    record("reader-shift-space-previous", "FAIL", "SendInput refused Shift+Space");
    return;
  }
  if (g.down_action != (uint32_t)READER_KBD_ACTION_PAGE_PREVIOUS) {
    (void)snprintf(scratch, sizeof(scratch), "action=%s reason=%s",
                   reader_kbd_action_name(g.down_action), reader_kbd_reason_name(g.down_reason));
    record("reader-shift-space-previous", "FAIL", scratch);
    return;
  }
  record("reader-shift-space-previous", "PASS", "real Shift+Space became the previous page");
}

static void case_conflict_passes(void) {
  reset_counters();
  if (inject(VK_CONTROL, 1) == 0 || inject(VK_SHIFT, 1) == 0) {
    record("reader-modifier-conflict-passes", "FAIL", "SendInput refused the modifiers");
    return;
  }
  pump(30);
  if (tap_word('F') == 0) {
    record("reader-modifier-conflict-passes", "FAIL", "SendInput refused Ctrl+Shift+F");
    return;
  }
  (void)inject(VK_SHIFT, 0);
  (void)inject(VK_CONTROL, 0);
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
         "Ctrl+Shift+F reached the default window procedure");
}

static void case_key_up(void) {
  reset_counters();
  if (inject(VK_RIGHT, 1) == 0) {
    record("reader-key-up-swallowed", "FAIL", "SendInput refused the key-down");
    return;
  }
  pump(50);
  if (g.down_action != (uint32_t)READER_KBD_ACTION_PAGE_NEXT) {
    record("reader-key-up-swallowed", "FAIL", "the key-down produced no page action");
    return;
  }
  if (inject(VK_RIGHT, 0) == 0) {
    record("reader-key-up-swallowed", "FAIL", "SendInput refused the key-up");
    return;
  }
  pump(80);
  {
    uint32_t held = 42;
    if (g.swallowed_up != 1 || g.forwarded_up != 0) {
      (void)snprintf(scratch, sizeof(scratch), "swallowed_up=%d forwarded_up=%d",
                     g.swallowed_up, g.forwarded_up);
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
  reset_counters();
  if (inject(VK_RIGHT, 1) == 0) {
    record("reader-repeat-bounded", "FAIL", "SendInput refused the held key-down");
    return;
  }
  pump(2600);
  if (inject(VK_RIGHT, 0) == 0) {
    record("reader-repeat-bounded", "FAIL", "SendInput refused the release");
    return;
  }
  pump(100);
  if (g.page_actions < 2) {
    (void)snprintf(scratch, sizeof(scratch),
                   "page_actions=%lu but the runner did not auto-repeat injected input",
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

static void case_edit_keeps_keys(void) {
  wchar_t text[64];
  DWORD start = 99;
  DWORD stop = 99;
  SetFocus(g.edit);
  pump(100);
  SetWindowTextW(g.edit, L"abcdef");
  SendMessageW(g.edit, EM_SETSEL, (WPARAM)0, (LPARAM)0);
  reset_counters();
  if (tap_word(VK_RIGHT) == 0) {
    record("edit-keeps-editing-keys", "FAIL", "SendInput refused VK_RIGHT in the edit control");
    return;
  }
  SendMessageW(g.edit, EM_GETSEL, (WPARAM)&start, (LPARAM)&stop);
  if (g.down_reason != (uint32_t)READER_KBD_REASON_TEXT_INPUT ||
      g.down_disposition != (uint32_t)READER_KBD_PASS || g.forwarded_down < 1) {
    (void)snprintf(scratch, sizeof(scratch), "reason=%s disposition=%s forwarded=%d",
                   reader_kbd_reason_name(g.down_reason), disposition_name(g.down_disposition),
                   g.forwarded_down);
    record("edit-keeps-editing-keys", "FAIL", scratch);
    return;
  }
  if (start != 1) {
    (void)snprintf(scratch, sizeof(scratch), "caret=%lu: the edit control did not move it",
                   (unsigned long)start);
    record("edit-keeps-editing-keys", "FAIL", scratch);
    return;
  }
  reset_counters();
  if (tap_word('C') == 0) {
    record("edit-keeps-editing-keys", "FAIL", "SendInput refused a letter in the edit control");
    return;
  }
  text[0] = L'\0';
  GetWindowTextW(g.edit, text, (int)(sizeof(text) / sizeof(text[0])));
  if (wcschr(text, L'c') == NULL) {
    record("edit-keeps-editing-keys", "FAIL", "the edit control did not receive the typed letter");
    return;
  }
  record("edit-keeps-editing-keys", "PASS",
         "the focused EDIT kept the arrow key and the typed letter");
}

static void case_edit_command(void) {
  SetFocus(g.edit);
  pump(100);
  reset_counters();
  if (tap_chord(VK_CONTROL, 'F') == 0) {
    record("edit-command-passes", "FAIL", "SendInput refused Ctrl+F in the edit control");
    return;
  }
  if (g.down_reason != (uint32_t)READER_KBD_REASON_TEXT_INPUT ||
      g.down_disposition != (uint32_t)READER_KBD_PASS || g.swallowed_down != 0) {
    (void)snprintf(scratch, sizeof(scratch), "reason=%s swallowed=%d",
                   reader_kbd_reason_name(g.down_reason), g.swallowed_down);
    record("edit-command-passes", "FAIL", scratch);
    return;
  }
  record("edit-command-passes", "PASS", "Ctrl+F in the edit control stayed with the edit control");
}

static void case_modal(void) {
  SetFocus(g.window);
  pump(100);
  reset_counters();
  g.modal_open = 1;
  EnableWindow(g.window, FALSE);
  ShowWindow(g.modal, SW_SHOW);
  SetActiveWindow(g.modal);
  SetForegroundWindow(g.modal);
  SetFocus(g.modal);
  pump(200);
  if (tap_word('C') == 0) {
    g.modal_open = 0;
    EnableWindow(g.window, TRUE);
    ShowWindow(g.modal, SW_HIDE);
    record("modal-keeps-keys", "FAIL", "SendInput refused a key in the modal window");
    return;
  }
  if (g.down_reason != (uint32_t)READER_KBD_REASON_MODAL ||
      g.down_disposition != (uint32_t)READER_KBD_PASS || g.modal_saw_key == 0 ||
      g.swallowed_down != 0) {
    (void)snprintf(scratch, sizeof(scratch), "reason=%s disposition=%s saw_key=%d swallowed=%d",
                   reader_kbd_reason_name(g.down_reason), disposition_name(g.down_disposition),
                   g.modal_saw_key, g.swallowed_down);
    g.modal_open = 0;
    EnableWindow(g.window, TRUE);
    ShowWindow(g.modal, SW_HIDE);
    record("modal-keeps-keys", "FAIL", scratch);
    return;
  }
  g.modal_open = 0;
  EnableWindow(g.window, TRUE);
  ShowWindow(g.modal, SW_HIDE);
  SetFocus(g.window);
  pump(150);
  record("modal-keeps-keys", "PASS", "a key pressed in the modal window was delivered to it");
}

static void case_focus_change(void) {
  SetFocus(g.window);
  pump(100);
  reset_counters();
  if (inject(VK_SPACE, 1) == 0) {
    record("focus-change-forgets-hold", "FAIL", "SendInput refused the held Space");
    return;
  }
  pump(80);
  if (g.down_action != (uint32_t)READER_KBD_ACTION_PAGE_NEXT) {
    record("focus-change-forgets-hold", "FAIL", "Space did not produce a page action");
    return;
  }
  SetFocus(g.edit);
  pump(150);
  if (g.cancel_calls < 1 || g.canceled_dropped < 1) {
    (void)snprintf(scratch, sizeof(scratch), "cancel_calls=%d dropped=%d", g.cancel_calls,
                   g.canceled_dropped);
    record("focus-change-forgets-hold", "FAIL", scratch);
    return;
  }
  if (inject(VK_SPACE, 0) == 0) {
    record("focus-change-forgets-hold", "FAIL", "SendInput refused the Space release");
    return;
  }
  pump(100);
  if (g.swallowed_up != 0 || g.forwarded_up < 1) {
    (void)snprintf(scratch, sizeof(scratch), "swallowed_up=%d forwarded_up=%d",
                   g.swallowed_up, g.forwarded_up);
    record("focus-change-forgets-hold", "FAIL", scratch);
    return;
  }
  if (tap_word(VK_RIGHT) == 0) {
    record("focus-change-forgets-hold", "FAIL", "SendInput refused a key in the edit control");
    return;
  }
  if (g.down_reason != (uint32_t)READER_KBD_REASON_TEXT_INPUT) {
    (void)snprintf(scratch, sizeof(scratch), "edit reason=%s",
                   reader_kbd_reason_name(g.down_reason));
    record("focus-change-forgets-hold", "FAIL", scratch);
    return;
  }
  SetFocus(g.window);
  pump(80);
  record("focus-change-forgets-hold", "PASS",
         "moving focus to the edit control dropped the hold and released its key-up");
}

static void case_deactivate(void) {
  SetFocus(g.window);
  pump(100);
  reset_counters();
  if (focus_window(g.other) == 0) {
    focus_window(g.window);
    record("deactivate-cancels", "SKIP", "the second window could not take the foreground");
    return;
  }
  if (g.cancel_calls < 1 || g.active != 0) {
    (void)snprintf(scratch, sizeof(scratch), "cancel_calls=%d active=%d", g.cancel_calls, g.active);
    focus_window(g.window);
    record("deactivate-cancels", "FAIL", scratch);
    return;
  }
  focus_window(g.window);
  record("deactivate-cancels", "PASS", "losing activation canceled the object");
}

static void case_ime(void) {
  record("ime-composing-passthrough", "SKIP",
         "no IME is installed on a hosted Windows runner; the VK_PROCESSKEY composing path is "
         "covered by the installed consumer's win32 vectors and its composing gate");
}

static HWND create_probe_window(HINSTANCE instance, LPCWSTR title) {
  return CreateWindowExW(0, PROBE_CLASS, title, WS_OVERLAPPEDWINDOW | WS_VISIBLE, 60, 60, 720, 460,
                         NULL, NULL, instance, NULL);
}

int main(void) {
  HINSTANCE instance = GetModuleHandleW(NULL);
  WNDCLASSEXW window_class;
  reader_kbd_config config;

  (void)memset(&window_class, 0, sizeof(window_class));
  window_class.cbSize = (UINT)sizeof(window_class);
  window_class.style = CS_HREDRAW | CS_VREDRAW;
  window_class.lpfnWndProc = window_proc;
  window_class.hInstance = instance;
  window_class.hCursor = LoadCursorW(NULL, IDC_ARROW);
  window_class.hbrBackground = (HBRUSH)(COLOR_WINDOW + 1);
  window_class.lpszClassName = PROBE_CLASS;
  if (RegisterClassExW(&window_class) == 0) {
    record("probe-window-ready", "FAIL", "RegisterClassExW failed");
    return 1;
  }
  InitCommonControls();

  g.window = create_probe_window(instance, L"EXReader keyboard actions probe");
  g.other = create_probe_window(instance, L"EXReader keyboard actions second window");
  g.modal = create_probe_window(instance, L"EXReader keyboard actions modal");
  if (g.window == NULL || g.other == NULL || g.modal == NULL) {
    record("probe-window-ready", "FAIL", "window creation failed");
    return 1;
  }
  (void)SetWindowLongPtrW(g.modal, GWLP_WNDPROC, (LONG_PTR)modal_proc);
  g.edit = CreateWindowExW(WS_EX_CLIENTEDGE, L"EDIT", L"abcdef",
                           WS_CHILD | WS_VISIBLE | ES_LEFT | ES_AUTOHSCROLL, 12, 12, 320, 28,
                           g.window, NULL, instance, NULL);
  if (g.edit == NULL) {
    record("probe-window-ready", "FAIL", "edit control creation failed");
    return 1;
  }
  SetWindowSubclass(g.edit, edit_proc, 1, 0);
  ShowWindow(g.window, SW_SHOW);
  UpdateWindow(g.window);
  pump(250);

  (void)memset(&config, 0, sizeof(config));
  config.struct_size = (uint32_t)sizeof(config);
  config.platform = (uint32_t)READER_KBD_PLATFORM_WINDOWS;
  config.page_turn_direction = (uint32_t)READER_PREFERENCES_TURN_LTR;
  config.page_turn_input = (uint32_t)READER_PREFERENCES_INPUT_HARDWARE_KEYS;
  if (reader_kbd_create(&config, &g.kbd) != READER_KBD_OK || g.kbd == NULL) {
    record("probe-window-ready", "FAIL", "reader_kbd_create failed");
    return 1;
  }
  g.active = 1;

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
  DestroyWindow(g.edit);
  DestroyWindow(g.modal);
  DestroyWindow(g.other);
  DestroyWindow(g.window);

  (void)fprintf(stdout, "probe %s pass=%d fail=%d skip=%d\n", failures == 0 ? "ok" : "failed",
                passes, failures, skips);
  (void)fflush(stdout);
  return failures == 0 ? 0 : 1;
}
