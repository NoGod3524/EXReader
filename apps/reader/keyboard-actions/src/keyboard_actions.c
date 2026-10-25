/* SPDX-License-Identifier: MIT */
#include "reader_keyboard_actions.h"

#include <stdlib.h>
#include <string.h>

#ifdef _WIN32
#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN 1
#endif
#include <windows.h>
typedef DWORD owner_id;
static owner_id current_owner(void) { return GetCurrentThreadId(); }
static int same_owner(owner_id a, owner_id b) { return a == b; }
#else
#include <pthread.h>
typedef pthread_t owner_id;
static owner_id current_owner(void) { return pthread_self(); }
static int same_owner(owner_id a, owner_id b) { return pthread_equal(a, b) != 0; }
#endif

typedef struct {
  uint32_t key;
  uint32_t codepoint;
  uint32_t repeats;
} held_key;

typedef struct {
  held_key held[READER_KBD_MAX_HELD];
  uint32_t count;
} held_table;

struct reader_kbd {
  reader_kbd_config config;
  held_table table;
  int in_call;
  owner_id owner;
};

uint32_t reader_kbd_abi_version(void) { return READER_KBD_ABI_VERSION; }

const char *reader_kbd_status_name(uint32_t status) {
  switch (status) {
    case READER_KBD_OK: return "ok";
    case READER_KBD_ARGUMENT: return "argument";
    case READER_KBD_WRONG_THREAD: return "wrong-thread";
    case READER_KBD_REENTRANT: return "reentrant";
    case READER_KBD_NOMEM: return "nomem";
    default: return "unknown";
  }
}

const char *reader_kbd_action_name(uint32_t action) {
  switch (action) {
    case READER_KBD_ACTION_NONE: return "none";
    case READER_KBD_ACTION_PAGE_PREVIOUS: return "page-previous";
    case READER_KBD_ACTION_PAGE_NEXT: return "page-next";
    case READER_KBD_ACTION_SEARCH: return "search";
    case READER_KBD_ACTION_BACK: return "back";
    case READER_KBD_ACTION_CONTENTS: return "contents";
    case READER_KBD_ACTION_BOOKMARK: return "bookmark";
    default: return "unknown";
  }
}

const char *reader_kbd_reason_name(uint32_t reason) {
  switch (reason) {
    case READER_KBD_REASON_ACTION: return "action";
    case READER_KBD_REASON_UNMAPPED: return "unmapped";
    case READER_KBD_REASON_MODIFIER_CONFLICT: return "modifier-conflict";
    case READER_KBD_REASON_TEXT_INPUT: return "text-input";
    case READER_KBD_REASON_MODAL: return "modal";
    case READER_KBD_REASON_COMPOSING: return "composing";
    case READER_KBD_REASON_INACTIVE: return "inactive";
    case READER_KBD_REASON_PAGE_KEYS_DISABLED: return "page-keys-disabled";
    case READER_KBD_REASON_CONTROL_OWNS: return "control-owns";
    case READER_KBD_REASON_REPEAT_SUPPRESSED: return "repeat-suppressed";
    case READER_KBD_REASON_REPEAT_LIMIT: return "repeat-limit";
    case READER_KBD_REASON_ORPHAN_REPEAT: return "orphan-repeat";
    case READER_KBD_REASON_KEY_UP_SWALLOWED: return "key-up-swallowed";
    case READER_KBD_REASON_KEY_UP: return "key-up";
    case READER_KBD_REASON_DECLINED: return "declined";
    default: return "unknown";
  }
}

reader_kbd_config reader_kbd_config_from_preferences(uint32_t platform,
                                                     const reader_preferences *preferences,
                                                     uint32_t flags) {
  reader_kbd_config config;
  memset(&config, 0, sizeof(config));
  if (!preferences) return config;
  config.struct_size = (uint32_t)sizeof(config);
  config.platform = platform;
  config.page_turn_direction = preferences->page_turn_direction;
  config.page_turn_input = preferences->page_turn_input;
  config.flags = flags;
  return config;
}

static int config_valid(const reader_kbd_config *c) {
  return c && c->struct_size == sizeof(*c) &&
         c->platform >= READER_KBD_PLATFORM_WINDOWS && c->platform <= READER_KBD_PLATFORM_ANDROID &&
         c->page_turn_direction >= (uint32_t)READER_PREFERENCES_TURN_LTR &&
         c->page_turn_direction <= (uint32_t)READER_PREFERENCES_TURN_VERTICAL &&
         c->page_turn_input >= (uint32_t)READER_PREFERENCES_INPUT_TAP &&
         c->page_turn_input <= (uint32_t)READER_PREFERENCES_INPUT_HARDWARE_KEYS &&
         (c->flags & ~READER_KBD_CONFIG_ALL_FLAGS) == 0;
}

static int event_valid(const reader_kbd_event *e) {
  return e && e->struct_size == sizeof(*e) &&
         (e->phase == READER_KBD_PHASE_DOWN || e->phase == READER_KBD_PHASE_UP) &&
         e->key <= READER_KBD_KEY_BROWSER_BACK &&
         e->codepoint <= READER_KBD_MAX_CODEPOINT &&
         !(e->codepoint >= 0xd800u && e->codepoint <= 0xdfffu) &&
         (e->modifiers & ~READER_KBD_MOD_ALL) == 0;
}

static int context_valid(const reader_kbd_context *c) {
  return c && c->struct_size == sizeof(*c) && c->focus >= READER_KBD_FOCUS_READER &&
         c->focus <= READER_KBD_FOCUS_CONTROL;
}

static void result_clear(reader_kbd_result *r) {
  memset(r, 0, sizeof(*r));
  r->struct_size = (uint32_t)sizeof(*r);
  r->disposition = READER_KBD_PASS;
  r->reason = READER_KBD_REASON_UNMAPPED;
}

static uint32_t fold(const reader_kbd_event *e) {
  uint32_t cp = e->key == READER_KBD_KEY_CHAR ? e->codepoint : 0u;
  if (cp >= 'A' && cp <= 'Z') cp += 32u;
  return cp;
}

static uint32_t primary_modifier(const reader_kbd_config *c) {
  return c->platform == READER_KBD_PLATFORM_APPLE ? READER_KBD_MOD_META : READER_KBD_MOD_CTRL;
}

/* True when some modifier set binds this key under the configuration. */
static int key_is_bound(const reader_kbd_config *c, const reader_kbd_event *e, uint32_t cp) {
  switch (e->key) {
    case READER_KBD_KEY_LEFT: case READER_KBD_KEY_RIGHT: case READER_KBD_KEY_PAGE_UP:
    case READER_KBD_KEY_PAGE_DOWN: case READER_KBD_KEY_SPACE: case READER_KBD_KEY_ESCAPE:
    case READER_KBD_KEY_BROWSER_BACK:
      return 1;
    case READER_KBD_KEY_UP: case READER_KBD_KEY_DOWN:
      return c->page_turn_direction == (uint32_t)READER_PREFERENCES_TURN_VERTICAL;
    case READER_KBD_KEY_CHAR:
      return cp == 'f' || cp == 't' || cp == 'd' ||
             (cp == '[' && c->platform == READER_KBD_PLATFORM_APPLE);
    default:
      return 0;
  }
}

/* Exact modifier match; extra Shift/Ctrl/Alt/Meta/AltGr never forms a shortcut. */
static int binding(const reader_kbd_config *c, const reader_kbd_event *e, uint32_t cp,
                   uint32_t *action, int *is_page) {
  uint32_t mods = e->modifiers;
  int ltr = c->page_turn_direction == (uint32_t)READER_PREFERENCES_TURN_LTR;
  int vertical = c->page_turn_direction == (uint32_t)READER_PREFERENCES_TURN_VERTICAL;
  *is_page = 0;
  if (mods == 0u) {
    switch (e->key) {
      case READER_KBD_KEY_PAGE_DOWN: case READER_KBD_KEY_SPACE:
        *action = READER_KBD_ACTION_PAGE_NEXT; *is_page = 1; return 1;
      case READER_KBD_KEY_PAGE_UP:
        *action = READER_KBD_ACTION_PAGE_PREVIOUS; *is_page = 1; return 1;
      case READER_KBD_KEY_RIGHT:
        *action = ltr ? READER_KBD_ACTION_PAGE_NEXT : READER_KBD_ACTION_PAGE_PREVIOUS;
        *is_page = 1; return 1;
      case READER_KBD_KEY_LEFT:
        *action = ltr ? READER_KBD_ACTION_PAGE_PREVIOUS : READER_KBD_ACTION_PAGE_NEXT;
        *is_page = 1; return 1;
      case READER_KBD_KEY_DOWN:
        if (!vertical) return 0;
        *action = READER_KBD_ACTION_PAGE_NEXT; *is_page = 1; return 1;
      case READER_KBD_KEY_UP:
        if (!vertical) return 0;
        *action = READER_KBD_ACTION_PAGE_PREVIOUS; *is_page = 1; return 1;
      case READER_KBD_KEY_ESCAPE: case READER_KBD_KEY_BROWSER_BACK:
        *action = READER_KBD_ACTION_BACK; return 1;
      default:
        return 0;
    }
  }
  if (mods == READER_KBD_MOD_SHIFT && e->key == READER_KBD_KEY_SPACE) {
    *action = READER_KBD_ACTION_PAGE_PREVIOUS; *is_page = 1; return 1;
  }
  if (mods == READER_KBD_MOD_ALT && e->key == READER_KBD_KEY_LEFT &&
      c->platform != READER_KBD_PLATFORM_APPLE) {
    *action = READER_KBD_ACTION_BACK; return 1;
  }
  if (mods == primary_modifier(c) && e->key == READER_KBD_KEY_CHAR) {
    if (cp == 'f') { *action = READER_KBD_ACTION_SEARCH; return 1; }
    if (cp == 't') { *action = READER_KBD_ACTION_CONTENTS; return 1; }
    if (cp == 'd') { *action = READER_KBD_ACTION_BOOKMARK; return 1; }
    if (cp == '[' && c->platform == READER_KBD_PLATFORM_APPLE) {
      *action = READER_KBD_ACTION_BACK; return 1;
    }
  }
  return 0;
}

static int table_find(const held_table *t, uint32_t key, uint32_t cp) {
  uint32_t i;
  for (i = 0; i < t->count; ++i) {
    if (t->held[i].key == key && t->held[i].codepoint == cp) return (int)i;
  }
  return -1;
}

static void table_remove(held_table *t, int index) {
  uint32_t i;
  if (index < 0) return;
  for (i = (uint32_t)index + 1u; i < t->count; ++i) t->held[i - 1u] = t->held[i];
  --t->count;
  memset(&t->held[t->count], 0, sizeof(t->held[0]));
}

static void table_add(held_table *t, uint32_t key, uint32_t cp) {
  if (t->count == READER_KBD_MAX_HELD) table_remove(t, 0); /* evict the oldest */
  t->held[t->count].key = key;
  t->held[t->count].codepoint = cp;
  t->held[t->count].repeats = 0;
  ++t->count;
}

static void pass(reader_kbd_result *r, held_table *t, int index, uint32_t reason) {
  table_remove(t, index);
  r->disposition = READER_KBD_PASS;
  r->action = READER_KBD_ACTION_NONE;
  r->reason = reason;
}

/* Pure decision on a table copy. Returns the action it wants delivered. */
static void decide(const reader_kbd_config *c, held_table *t, const reader_kbd_event *e,
                   const reader_kbd_context *ctx, reader_kbd_result *r) {
  uint32_t cp = fold(e);
  uint32_t action = READER_KBD_ACTION_NONE;
  int is_page = 0;
  int index = table_find(t, e->key, cp);
  int page_keys;

  if (e->phase == READER_KBD_PHASE_UP) {
    if (index >= 0) {
      table_remove(t, index);
      r->disposition = READER_KBD_CONSUME;
      r->reason = READER_KBD_REASON_KEY_UP_SWALLOWED;
    } else {
      r->reason = READER_KBD_REASON_KEY_UP;
    }
    return;
  }
  if (!ctx->window_active) { pass(r, t, index, READER_KBD_REASON_INACTIVE); return; }
  if (ctx->composing) { pass(r, t, index, READER_KBD_REASON_COMPOSING); return; }
  if (ctx->focus == READER_KBD_FOCUS_TEXT_INPUT) { pass(r, t, index, READER_KBD_REASON_TEXT_INPUT); return; }
  if (ctx->focus == READER_KBD_FOCUS_MODAL) { pass(r, t, index, READER_KBD_REASON_MODAL); return; }
  /* A focused control owns Space and Enter whatever the modifier set is, so the
     button/list activation is never stolen and Shift+Space is not a page turn. */
  if (ctx->focus == READER_KBD_FOCUS_CONTROL &&
      (e->key == READER_KBD_KEY_SPACE || e->key == READER_KBD_KEY_ENTER)) {
    pass(r, t, index, READER_KBD_REASON_CONTROL_OWNS);
    return;
  }
  if (!binding(c, e, cp, &action, &is_page)) {
    pass(r, t, index, key_is_bound(c, e, cp) ? READER_KBD_REASON_MODIFIER_CONFLICT
                                              : READER_KBD_REASON_UNMAPPED);
    return;
  }
  page_keys = c->page_turn_input == (uint32_t)READER_PREFERENCES_INPUT_HARDWARE_KEYS ||
              (c->flags & READER_KBD_CONFIG_ALWAYS_PAGE_KEYS) != 0;
  if (is_page && !page_keys) { pass(r, t, index, READER_KBD_REASON_PAGE_KEYS_DISABLED); return; }

  if (e->repeat) {
    if (index < 0) { pass(r, t, index, READER_KBD_REASON_ORPHAN_REPEAT); return; }
    r->disposition = READER_KBD_CONSUME;
    if (!is_page || (c->flags & READER_KBD_CONFIG_NO_REPEAT_PAGING)) {
      r->reason = READER_KBD_REASON_REPEAT_SUPPRESSED;
    } else if (t->held[index].repeats >= READER_KBD_MAX_REPEAT_ACTIONS) {
      r->reason = READER_KBD_REASON_REPEAT_LIMIT;
    } else {
      ++t->held[index].repeats;
      r->action = action;
      r->reason = READER_KBD_REASON_ACTION;
    }
    r->repeat_actions = t->held[index].repeats;
    return;
  }
  table_remove(t, index); /* a fresh press restarts the hold */
  table_add(t, e->key, cp);
  r->disposition = READER_KBD_CONSUME;
  r->action = action;
  r->reason = READER_KBD_REASON_ACTION;
}

static reader_kbd_status entry(const reader_kbd *kbd) {
  if (!kbd) return READER_KBD_ARGUMENT;
  if (!same_owner(kbd->owner, current_owner())) return READER_KBD_WRONG_THREAD;
  if (kbd->in_call) return READER_KBD_REENTRANT;
  return READER_KBD_OK;
}

reader_kbd_status reader_kbd_create(const reader_kbd_config *config, reader_kbd **out) {
  reader_kbd *kbd;
  if (!out) return READER_KBD_ARGUMENT;
  *out = NULL;
  if (!config_valid(config)) return READER_KBD_ARGUMENT;
  kbd = (reader_kbd *)calloc(1, sizeof(*kbd));
  if (!kbd) return READER_KBD_NOMEM;
  kbd->config = *config;
  kbd->owner = current_owner();
  *out = kbd;
  return READER_KBD_OK;
}

reader_kbd_status reader_kbd_destroy(reader_kbd *kbd) {
  reader_kbd_status status;
  if (!kbd) return READER_KBD_OK;
  status = entry(kbd);
  if (status != READER_KBD_OK) return status;
  memset(kbd, 0, sizeof(*kbd));
  free(kbd);
  return READER_KBD_OK;
}

reader_kbd_status reader_kbd_set_config(reader_kbd *kbd, const reader_kbd_config *config) {
  reader_kbd_status status = entry(kbd);
  if (status != READER_KBD_OK) return status;
  if (!config_valid(config)) return READER_KBD_ARGUMENT;
  kbd->config = *config;
  return READER_KBD_OK;
}

reader_kbd_status reader_kbd_cancel(reader_kbd *kbd, uint32_t *dropped) {
  reader_kbd_status status = entry(kbd);
  if (status != READER_KBD_OK) return status;
  if (dropped) *dropped = kbd->table.count;
  memset(&kbd->table, 0, sizeof(kbd->table));
  return READER_KBD_OK;
}

reader_kbd_status reader_kbd_held_count(const reader_kbd *kbd, uint32_t *count) {
  reader_kbd_status status = entry(kbd);
  if (status != READER_KBD_OK) return status;
  if (!count) return READER_KBD_ARGUMENT;
  *count = kbd->table.count;
  return READER_KBD_OK;
}

reader_kbd_status reader_kbd_dispatch(reader_kbd *kbd, const reader_kbd_event *event,
                                      const reader_kbd_context *context,
                                      reader_kbd_handler handler, void *user,
                                      reader_kbd_result *result) {
  held_table next;
  reader_kbd_result r;
  reader_kbd_status status;
  if (result) result_clear(result);
  status = entry(kbd);
  if (status != READER_KBD_OK) return status;
  if (!result || !event_valid(event) || !context_valid(context)) return READER_KBD_ARGUMENT;
  next = kbd->table;
  result_clear(&r);
  decide(&kbd->config, &next, event, context, &r);
  if (handler && r.action != READER_KBD_ACTION_NONE) {
    int handled;
    kbd->in_call = 1;
    handled = handler(user, r.action, event);
    kbd->in_call = 0;
    if (!handled) {
      result_clear(result);
      result->reason = READER_KBD_REASON_DECLINED;
      return READER_KBD_OK;
    }
  }
  kbd->table = next;
  *result = r;
  return READER_KBD_OK;
}

reader_kbd_status reader_kbd_translate(reader_kbd *kbd, const reader_kbd_event *event,
                                       const reader_kbd_context *context,
                                       reader_kbd_result *result) {
  return reader_kbd_dispatch(kbd, event, context, NULL, NULL, result);
}
