/* SPDX-License-Identifier: MIT */
#ifndef READER_KEYBOARD_ACTIONS_H
#define READER_KEYBOARD_ACTIONS_H

#include <stddef.h>
#include <stdint.h>

#include <reader_preferences.h>

#ifdef __cplusplus
extern "C" {
#endif

#define READER_KBD_VERSION_STRING "0.1.0"
#define READER_KBD_ABI_VERSION 1u

/* Hard limits. Both are enforced, never grown.
   Held keys: the object remembers at most READER_KBD_MAX_HELD distinct consumed
   key-downs. Pressing one more evicts the oldest entry, so its later key-up and
   auto-repeat are delivered to the new focus owner instead of being swallowed.
   Repeats: a held page key emits at most READER_KBD_MAX_REPEAT_ACTIONS page
   actions; further repeats stay CONSUME with REASON_REPEAT_LIMIT so the key-up
   pairing and the focus owner are still correct. */
#define READER_KBD_MAX_HELD 8u             /* tracked consumed key-downs */
#define READER_KBD_MAX_REPEAT_ACTIONS 64u  /* repeat actions per held page key */
#define READER_KBD_MAX_CODEPOINT 0x10FFFFu

/* Pure keyboard-to-action mapping. A reader_kbd is a small state object: it
   registers no global hotkey, installs no hook, reads no device and never moves
   focus. The host feeds it one native key event plus the focus state it observed
   and receives an ACTION and a disposition. It never executes the action.

   Ownership and memory: reader_kbd_create allocates one opaque object; the
   caller owns it and frees it with reader_kbd_destroy. Every struct passed in is
   a plain caller-owned value that is read during the call and never retained.
   Results are plain values; nothing returned points into library memory.

   Threading: the object belongs to the thread that created it. Every call on
   another thread returns READER_KBD_WRONG_THREAD without touching state. Two
   objects never share state, so different owners may run on different threads.

   Reentry: reader_kbd_dispatch invokes the host handler synchronously. While
   the handler runs, any call on the same object (translate, dispatch, cancel,
   set_config, destroy) returns READER_KBD_REENTRANT and changes nothing.

   Commit boundary: state changes are computed on a copy. They are committed
   after the handler returns nonzero (or immediately when there is no handler).
   A handler that returns zero declines the action: nothing is committed, the
   result is PASS with reason DECLINED, and the matching key-up is not swallowed.
   Any error status leaves the object byte-for-byte unchanged and zeroes the
   result (PASS, no action).

   Errors/cancel: invalid struct sizes or enum values return ARGUMENT.
   reader_kbd_cancel is the cancellation primitive: call it when the window
   loses activation or focus moves; it forgets every consumed key-down so later
   repeats and key-ups reach the new focus owner.

   Native events stay native: the host passes the numeric fields of its own
   event plus the modifier state it observed, and keeps ownership of delivery.
   Returning CONSUME means "do not forward this event to the native focus
   owner"; PASS means "forward it unchanged". The library never posts, injects
   or synthesizes an event.

   Focus policy is the host's, expressed per event through reader_kbd_context:
   TEXT_INPUT and MODAL keep every editing key, only a CONTROL keeps Space and
   Enter, and page keys additionally require the stored input mode (or the
   ALWAYS_PAGE_KEYS flag). No global hotkey is registered and no focus is ever
   moved by this library. */
typedef enum {
  READER_KBD_OK = 0,
  READER_KBD_ARGUMENT = 1,
  READER_KBD_WRONG_THREAD = 2,
  READER_KBD_REENTRANT = 3,
  READER_KBD_NOMEM = 4
} reader_kbd_status;

typedef enum {
  READER_KBD_PLATFORM_WINDOWS = 1,
  READER_KBD_PLATFORM_LINUX = 2,
  READER_KBD_PLATFORM_APPLE = 3,
  READER_KBD_PLATFORM_ANDROID = 4
} reader_kbd_platform;

typedef enum {
  READER_KBD_ACTION_NONE = 0,
  READER_KBD_ACTION_PAGE_PREVIOUS = 1,
  READER_KBD_ACTION_PAGE_NEXT = 2,
  READER_KBD_ACTION_SEARCH = 3,
  READER_KBD_ACTION_BACK = 4,
  READER_KBD_ACTION_CONTENTS = 5,
  READER_KBD_ACTION_BOOKMARK = 6
} reader_kbd_action;

typedef enum {
  READER_KBD_PHASE_DOWN = 1,
  READER_KBD_PHASE_UP = 2
} reader_kbd_phase;

/* Logical key. CHAR uses 'codepoint' (the character the key produces without
   modifiers; the library folds ASCII A-Z to a-z). Codepoint 0 with CHAR is an
   unidentified key and never maps. */
typedef enum {
  READER_KBD_KEY_CHAR = 0,
  READER_KBD_KEY_LEFT = 1,
  READER_KBD_KEY_RIGHT = 2,
  READER_KBD_KEY_UP = 3,
  READER_KBD_KEY_DOWN = 4,
  READER_KBD_KEY_PAGE_UP = 5,
  READER_KBD_KEY_PAGE_DOWN = 6,
  READER_KBD_KEY_HOME = 7,
  READER_KBD_KEY_END = 8,
  READER_KBD_KEY_SPACE = 9,
  READER_KBD_KEY_ENTER = 10,
  READER_KBD_KEY_ESCAPE = 11,
  READER_KBD_KEY_BACKSPACE = 12,
  READER_KBD_KEY_TAB = 13,
  READER_KBD_KEY_BROWSER_BACK = 14 /* Android BACK, Windows VK_BROWSER_BACK */
} reader_kbd_key;

/* Modifier bits as pressed at event time. Lock states are not modifiers: the
   native translators drop Caps/Num lock. ALTGR marks a text-producing AltGr (or
   Level3) state; it never forms a shortcut. META is Windows/Super/Command. */
enum {
  READER_KBD_MOD_SHIFT = 1u << 0,
  READER_KBD_MOD_CTRL = 1u << 1,
  READER_KBD_MOD_ALT = 1u << 2,
  READER_KBD_MOD_META = 1u << 3,
  READER_KBD_MOD_ALTGR = 1u << 4,
  READER_KBD_MOD_ALL = 0x1fu
};

typedef enum {
  READER_KBD_FOCUS_READER = 1,     /* reader content or other non-editing view */
  READER_KBD_FOCUS_TEXT_INPUT = 2, /* edit field, search box, any text editor */
  READER_KBD_FOCUS_MODAL = 3,      /* modal dialog/sheet/popup owns the keyboard */
  READER_KBD_FOCUS_CONTROL = 4     /* push button/list: Space and Enter belong to it */
} reader_kbd_focus;

typedef struct {
  uint32_t struct_size; /* sizeof(reader_kbd_event) */
  uint32_t phase;       /* reader_kbd_phase */
  uint32_t key;         /* reader_kbd_key */
  uint32_t codepoint;   /* <= READER_KBD_MAX_CODEPOINT; used when key == CHAR */
  uint32_t modifiers;   /* READER_KBD_MOD_* */
  uint32_t repeat;      /* nonzero: operating-system auto-repeat of a held key */
} reader_kbd_event;

typedef struct {
  uint32_t struct_size; /* sizeof(reader_kbd_context) */
  uint32_t focus;       /* reader_kbd_focus, observed by the host for this event */
  uint32_t composing;   /* nonzero while an IME composition is active */
  uint32_t window_active; /* nonzero while the reader window is the active one */
} reader_kbd_context;

enum {
  /* Page keys normally need page_turn_input == HARDWARE_KEYS. This flag makes a
     desktop host honor them regardless of the stored input mode. */
  READER_KBD_CONFIG_ALWAYS_PAGE_KEYS = 1u << 0,
  /* Do not emit repeated page actions for a held key; first press only. */
  READER_KBD_CONFIG_NO_REPEAT_PAGING = 1u << 1,
  READER_KBD_CONFIG_ALL_FLAGS = 3u
};

typedef struct {
  uint32_t struct_size;          /* sizeof(reader_kbd_config) */
  uint32_t platform;             /* reader_kbd_platform */
  uint32_t page_turn_direction;  /* reader_preferences_turn_direction value */
  uint32_t page_turn_input;      /* reader_preferences_turn_input value */
  uint32_t flags;                /* READER_KBD_CONFIG_* */
} reader_kbd_config;

typedef enum {
  READER_KBD_PASS = 0,    /* not ours: deliver to the native focus owner */
  READER_KBD_CONSUME = 1  /* ours (acted or deliberately swallowed): stop delivery */
} reader_kbd_disposition;

typedef enum {
  READER_KBD_REASON_ACTION = 0,           /* an action was produced */
  READER_KBD_REASON_UNMAPPED = 1,         /* key has no binding */
  READER_KBD_REASON_MODIFIER_CONFLICT = 2,/* bound key with another modifier set */
  READER_KBD_REASON_TEXT_INPUT = 3,       /* text field keeps its editing keys */
  READER_KBD_REASON_MODAL = 4,            /* modal owns the keyboard */
  READER_KBD_REASON_COMPOSING = 5,        /* IME composition active */
  READER_KBD_REASON_INACTIVE = 6,         /* window not active */
  READER_KBD_REASON_PAGE_KEYS_DISABLED = 7,
  READER_KBD_REASON_CONTROL_OWNS = 8,     /* Space/Enter on a focused control */
  READER_KBD_REASON_REPEAT_SUPPRESSED = 9,/* command key held: acts once */
  READER_KBD_REASON_REPEAT_LIMIT = 10,    /* page repeat hit the hard cap */
  READER_KBD_REASON_ORPHAN_REPEAT = 11,   /* repeat of a key we never consumed */
  READER_KBD_REASON_KEY_UP_SWALLOWED = 12,/* up of a consumed down */
  READER_KBD_REASON_KEY_UP = 13,          /* up of a key we did not consume */
  READER_KBD_REASON_DECLINED = 14         /* handler returned zero */
} reader_kbd_reason;

typedef struct {
  uint32_t struct_size;   /* set by the library */
  uint32_t action;        /* reader_kbd_action; NONE unless reason == ACTION */
  uint32_t disposition;   /* reader_kbd_disposition */
  uint32_t reason;        /* reader_kbd_reason */
  uint32_t repeat_actions;/* page actions emitted by repeats of this hold */
} reader_kbd_result;

typedef struct reader_kbd reader_kbd;

/* Called on the owner thread inside dispatch with the object locked. Return
   nonzero if the host performed the action. Must not call back into 'kbd'.
   A C++ host that may throw must not let the exception cross this frame: the
   reader::KeyboardActions wrapper runs the handler behind an extern-C trampoline
   that converts a throw into "declined", which keeps the object usable. */
typedef int (*reader_kbd_handler)(void *user, uint32_t action, const reader_kbd_event *event);

#if defined(_WIN32) && defined(READER_KBD_BUILD_SHARED)
#define READER_KBD_API __declspec(dllexport)
#elif defined(_WIN32) && defined(READER_KBD_USE_SHARED)
#define READER_KBD_API __declspec(dllimport)
#else
#define READER_KBD_API
#endif

READER_KBD_API uint32_t reader_kbd_abi_version(void);
READER_KBD_API const char *reader_kbd_status_name(uint32_t status);
READER_KBD_API const char *reader_kbd_action_name(uint32_t action);
READER_KBD_API const char *reader_kbd_reason_name(uint32_t reason);

/* Fill a config from stored preferences (direction and operation values). The
   preferences must already be valid; an invalid pointer yields struct_size 0,
   which create/set_config reject. */
READER_KBD_API reader_kbd_config reader_kbd_config_from_preferences(
    uint32_t platform, const reader_preferences *preferences, uint32_t flags);

READER_KBD_API reader_kbd_status reader_kbd_create(const reader_kbd_config *config,
                                                   reader_kbd **out);
/* NULL is accepted. Owner thread only, never from a handler. */
READER_KBD_API reader_kbd_status reader_kbd_destroy(reader_kbd *kbd);
/* Atomic: invalid config changes nothing. Held keys are kept so a mid-press
   preference change still swallows the matching key-up. */
READER_KBD_API reader_kbd_status reader_kbd_set_config(reader_kbd *kbd,
                                                       const reader_kbd_config *config);
/* Forget all consumed key-downs. dropped may be NULL. */
READER_KBD_API reader_kbd_status reader_kbd_cancel(reader_kbd *kbd, uint32_t *dropped);
READER_KBD_API reader_kbd_status reader_kbd_held_count(const reader_kbd *kbd, uint32_t *count);

/* Translate and commit immediately (no handler). */
READER_KBD_API reader_kbd_status reader_kbd_translate(reader_kbd *kbd,
                                                      const reader_kbd_event *event,
                                                      const reader_kbd_context *context,
                                                      reader_kbd_result *result);
/* Translate, run handler when an action is produced, then commit or roll back
   as described above. handler may be NULL (same as translate). */
READER_KBD_API reader_kbd_status reader_kbd_dispatch(reader_kbd *kbd,
                                                     const reader_kbd_event *event,
                                                     const reader_kbd_context *context,
                                                     reader_kbd_handler handler, void *user,
                                                     reader_kbd_result *result);

/* ---- Native event translators ------------------------------------------
   Pure functions over the numeric fields of the platform's own event. They do
   not include platform headers, read device state or allocate. On failure the
   output event is zeroed. composing (optional) is set when the native event
   itself says the key went to an input method. */

/* Windows: message WM_KEYDOWN 0x100, WM_KEYUP 0x101, WM_SYSKEYDOWN 0x104,
   WM_SYSKEYUP 0x105 with its wParam (virtual key) and lParam. The host reads
   modifier state (GetKeyState) into READER_KBD_WIN32_*. Ctrl plus right Alt
   without left Alt is AltGr and becomes MOD_ALTGR, not Ctrl+Alt. VK_PROCESSKEY
   (0xE5) sets *composing. Lock keys are ignored by design. */
enum {
  READER_KBD_WIN32_SHIFT = 1u << 0,
  READER_KBD_WIN32_CTRL = 1u << 1,
  READER_KBD_WIN32_LALT = 1u << 2,
  READER_KBD_WIN32_RALT = 1u << 3,
  READER_KBD_WIN32_WIN = 1u << 4
};
READER_KBD_API reader_kbd_status reader_kbd_event_from_win32(
    uint32_t message, uint64_t wparam, int64_t lparam, uint32_t win32_modifiers,
    reader_kbd_event *out, uint32_t *composing);

/* X11: type KeyPress 2 / KeyRelease 3, KeySym of the unmodified key (shift level
   0 or 1), XKeyEvent.state. repeat is supplied by the host (X reports detectable
   auto-repeat as KeyPress without a preceding KeyRelease). Mod5 maps to ALTGR. */
READER_KBD_API reader_kbd_status reader_kbd_event_from_x11(
    uint32_t type, uint32_t keysym, uint32_t state, uint32_t repeat, reader_kbd_event *out);

/* Apple: NSEventType keyDown 10 / keyUp 11, kVK_* key_code, NSEventModifierFlags
   and the first scalar of charactersIgnoringModifiers (0 when none). Command is
   META. Function/NumericPad/CapsLock flag bits are dropped. */
READER_KBD_API reader_kbd_status reader_kbd_event_from_apple(
    uint32_t type, uint32_t key_code, uint64_t flags, uint32_t unmodified_codepoint,
    uint32_t is_repeat, reader_kbd_event *out);

/* Android: KeyEvent action ACTION_DOWN 0 / ACTION_UP 1, KEYCODE_*, metaState and
   repeatCount. Covered by numeric vectors only; no device is exercised here. */
READER_KBD_API reader_kbd_status reader_kbd_event_from_android(
    uint32_t action, uint32_t key_code, uint32_t meta_state, uint32_t repeat_count,
    reader_kbd_event *out);

#ifdef __cplusplus
}
#endif
#endif
