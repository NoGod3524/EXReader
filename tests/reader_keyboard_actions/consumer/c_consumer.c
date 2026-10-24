/* SPDX-License-Identifier: MIT */
#if defined(_WIN32)
#define _CRT_SECURE_NO_WARNINGS 1
#endif
#include "reader_keyboard_actions.h"

#include <stdio.h>
#include <string.h>

/* Installed-package C consumer. Expected values below were fixed before any run.
   Each named check prints "CHECK <name> PASS|FAIL <detail>". */
static char detail[300];

#define A_NONE READER_KBD_ACTION_NONE
#define A_PREV READER_KBD_ACTION_PAGE_PREVIOUS
#define A_NEXT READER_KBD_ACTION_PAGE_NEXT
#define A_SEARCH READER_KBD_ACTION_SEARCH
#define A_BACK READER_KBD_ACTION_BACK
#define A_TOC READER_KBD_ACTION_CONTENTS
#define A_MARK READER_KBD_ACTION_BOOKMARK
#define PASS_ READER_KBD_PASS
#define EAT READER_KBD_CONSUME
#define R_ACT READER_KBD_REASON_ACTION
#define DOWN READER_KBD_PHASE_DOWN
#define UP READER_KBD_PHASE_UP
#define K_CHAR READER_KBD_KEY_CHAR
#define SH READER_KBD_MOD_SHIFT
#define CT READER_KBD_MOD_CTRL
#define AL READER_KBD_MOD_ALT
#define ME READER_KBD_MOD_META
#define AG READER_KBD_MOD_ALTGR
#define LTR READER_PREFERENCES_TURN_LTR
#define RTL READER_PREFERENCES_TURN_RTL
#define VERT READER_PREFERENCES_TURN_VERTICAL
#define HW READER_PREFERENCES_INPUT_HARDWARE_KEYS
#define WIN_ READER_KBD_PLATFORM_WINDOWS
#define LIN_ READER_KBD_PLATFORM_LINUX
#define APL_ READER_KBD_PLATFORM_APPLE
#define AND_ READER_KBD_PLATFORM_ANDROID

static reader_kbd_config cfg(uint32_t platform, uint32_t dir, uint32_t input, uint32_t flags) {
  reader_kbd_config c;
  memset(&c, 0, sizeof(c));
  c.struct_size = (uint32_t)sizeof(c);
  c.platform = platform;
  c.page_turn_direction = dir;
  c.page_turn_input = input;
  c.flags = flags;
  return c;
}
static reader_kbd_context ctx(uint32_t focus, uint32_t composing, uint32_t active) {
  reader_kbd_context c;
  memset(&c, 0, sizeof(c));
  c.struct_size = (uint32_t)sizeof(c);
  c.focus = focus;
  c.composing = composing;
  c.window_active = active;
  return c;
}
static reader_kbd_event ev(uint32_t phase, uint32_t key, uint32_t cp, uint32_t mods, uint32_t repeat) {
  reader_kbd_event e;
  memset(&e, 0, sizeof(e));
  e.struct_size = (uint32_t)sizeof(e);
  e.phase = phase;
  e.key = key;
  e.codepoint = cp;
  e.modifiers = mods;
  e.repeat = repeat;
  return e;
}
static reader_kbd *make(uint32_t platform, uint32_t dir, uint32_t input, uint32_t flags) {
  reader_kbd_config c = cfg(platform, dir, input, flags);
  reader_kbd *k = NULL;
  if (reader_kbd_create(&c, &k) != READER_KBD_OK) return NULL;
  return k;
}

static int fail(const char *what) {
  (void)snprintf(detail, sizeof(detail), "%s", what);
  return 0;
}

/* One expectation: returns 1 on match. */
static int step(reader_kbd *k, const reader_kbd_context *c, reader_kbd_event e, uint32_t action,
                uint32_t disp, uint32_t reason, const char *label) {
  reader_kbd_result r;
  reader_kbd_status s = reader_kbd_translate(k, &e, c, &r);
  if (s != READER_KBD_OK) {
    (void)snprintf(detail, sizeof(detail), "%s: status %s", label, reader_kbd_status_name(s));
    return 0;
  }
  if (r.struct_size != sizeof(r) || r.action != action || r.disposition != disp || r.reason != reason) {
    (void)snprintf(detail, sizeof(detail), "%s: got action=%s disp=%u reason=%s want action=%s disp=%u reason=%s",
                   label, reader_kbd_action_name(r.action), (unsigned)r.disposition,
                   reader_kbd_reason_name(r.reason), reader_kbd_action_name(action), (unsigned)disp,
                   reader_kbd_reason_name(reason));
    return 0;
  }
  return 1;
}
#define S(k, c, e, a, d, r) do { if (!step((k), &(c), (e), (a), (d), (r), #e)) goto done; } while (0)
#define TAP(k, c, key, cp, mods, a, d, r) do { \
    if (!step((k), &(c), ev(DOWN, (key), (cp), (mods), 0), (a), (d), (r), "down " #key)) goto done; \
    if (!step((k), &(c), ev(UP, (key), (cp), (mods), 0), A_NONE, (d), (d) == EAT ? READER_KBD_REASON_KEY_UP_SWALLOWED : READER_KBD_REASON_KEY_UP, "up " #key)) goto done; \
  } while (0)
#define REQUIRE(cond, msg) do { if (!(cond)) { (void)snprintf(detail, sizeof(detail), "%s", msg); goto done; } } while (0)

static uint32_t held(reader_kbd *k) {
  uint32_t n = 99;
  (void)reader_kbd_held_count(k, &n);
  return n;
}

static int chk_abi(void) {
  int ok = 0;
  REQUIRE(reader_kbd_abi_version() == 1u, "abi");
  REQUIRE(sizeof(reader_kbd_event) == 24 && sizeof(reader_kbd_context) == 16 &&
          sizeof(reader_kbd_config) == 20 && sizeof(reader_kbd_result) == 20, "struct sizes");
  REQUIRE(strcmp(reader_kbd_status_name(READER_KBD_REENTRANT), "reentrant") == 0, "status name");
  REQUIRE(strcmp(reader_kbd_status_name(77), "unknown") == 0, "unknown status");
  REQUIRE(strcmp(reader_kbd_action_name(A_TOC), "contents") == 0, "action name");
  REQUIRE(strcmp(reader_kbd_action_name(77), "unknown") == 0, "unknown action");
  REQUIRE(strcmp(reader_kbd_reason_name(READER_KBD_REASON_DECLINED), "declined") == 0, "reason name");
  REQUIRE(strcmp(reader_kbd_reason_name(77), "unknown") == 0, "unknown reason");
  ok = 1;
done:
  return ok;
}

static int chk_from_preferences(void) {
  int ok = 0;
  reader_preferences p = reader_preferences_defaults();
  reader_kbd_config c;
  reader_kbd *k = NULL;
  p.page_turn_direction = (uint32_t)RTL;
  p.page_turn_input = (uint32_t)HW;
  c = reader_kbd_config_from_preferences(LIN_, &p, READER_KBD_CONFIG_NO_REPEAT_PAGING);
  REQUIRE(c.struct_size == sizeof(c) && c.platform == LIN_ && c.page_turn_direction == 2u &&
          c.page_turn_input == 4u && c.flags == READER_KBD_CONFIG_NO_REPEAT_PAGING, "fields");
  REQUIRE(reader_kbd_create(&c, &k) == READER_KBD_OK && k, "create");
  (void)reader_kbd_destroy(k);
  c = reader_kbd_config_from_preferences(LIN_, NULL, 0);
  REQUIRE(c.struct_size == 0, "null preferences");
  k = (reader_kbd *)1;
  REQUIRE(reader_kbd_create(&c, &k) == READER_KBD_ARGUMENT && k == NULL, "rejects zero config");
  p = reader_preferences_defaults(); /* default input is tap */
  c = reader_kbd_config_from_preferences(LIN_, &p, 0);
  REQUIRE(c.page_turn_input == (uint32_t)READER_PREFERENCES_INPUT_TAP, "default tap");
  ok = 1;
done:
  return ok;
}

static int chk_struct_validation(void) {
  int ok = 0;
  reader_kbd *k = NULL;
  reader_kbd_config c = cfg(LIN_, LTR, HW, 0);
  reader_kbd_context rc = ctx(READER_KBD_FOCUS_READER, 0, 1);
  reader_kbd_event e;
  reader_kbd_result r;
  reader_kbd_config bad;
  uint32_t i;
  REQUIRE(reader_kbd_create(NULL, &k) == READER_KBD_ARGUMENT, "null config");
  REQUIRE(reader_kbd_create(&c, NULL) == READER_KBD_ARGUMENT, "null out");
  for (i = 0; i < 8; ++i) {
    bad = c;
    if (i == 0) bad.struct_size = 19;
    if (i == 1) bad.platform = 0;
    if (i == 2) bad.platform = 5;
    if (i == 3) bad.page_turn_direction = 0;
    if (i == 4) bad.page_turn_direction = 4;
    if (i == 5) bad.page_turn_input = 0;
    if (i == 6) bad.page_turn_input = 5;
    if (i == 7) bad.flags = 4;
    k = (reader_kbd *)1;
    REQUIRE(reader_kbd_create(&bad, &k) == READER_KBD_ARGUMENT && k == NULL, "bad config");
  }
  REQUIRE(reader_kbd_create(&c, &k) == READER_KBD_OK, "create");
  e = ev(DOWN, READER_KBD_KEY_RIGHT, 0, 0, 0);
  REQUIRE(reader_kbd_translate(k, &e, &rc, &r) == READER_KBD_OK && r.action == A_NEXT, "baseline");
  REQUIRE(held(k) == 1, "held 1");
  for (i = 0; i < 9; ++i) {
    e = ev(DOWN, READER_KBD_KEY_LEFT, 0, 0, 0);
    if (i == 0) e.struct_size = 23;
    if (i == 1) e.phase = 0;
    if (i == 2) e.phase = 3;
    if (i == 3) e.key = 15;
    if (i == 4) { e.key = K_CHAR; e.codepoint = 0x110000u; }
    if (i == 5) { e.key = K_CHAR; e.codepoint = 0xd800u; }
    if (i == 6) e.modifiers = 0x20u;
    if (i == 7) e.modifiers = 0xffffffffu;
    r.action = 99;
    if (i == 8) {
      REQUIRE(reader_kbd_translate(k, &e, NULL, &r) == READER_KBD_ARGUMENT, "null context");
    } else {
      REQUIRE(reader_kbd_translate(k, &e, &rc, &r) == READER_KBD_ARGUMENT, "bad event");
    }
    REQUIRE(r.struct_size == sizeof(r) && r.action == A_NONE && r.disposition == PASS_ &&
            r.reason == READER_KBD_REASON_UNMAPPED, "result zeroed on error");
  }
  e = ev(DOWN, READER_KBD_KEY_LEFT, 0, 0, 0);
  rc.focus = 0;
  REQUIRE(reader_kbd_translate(k, &e, &rc, &r) == READER_KBD_ARGUMENT, "focus 0");
  rc.focus = 5;
  REQUIRE(reader_kbd_translate(k, &e, &rc, &r) == READER_KBD_ARGUMENT, "focus 5");
  rc.focus = 1;
  rc.struct_size = 12;
  REQUIRE(reader_kbd_translate(k, &e, &rc, &r) == READER_KBD_ARGUMENT, "context size");
  rc.struct_size = sizeof(rc);
  REQUIRE(reader_kbd_translate(k, &e, &rc, NULL) == READER_KBD_ARGUMENT, "null result");
  REQUIRE(reader_kbd_translate(NULL, &e, &rc, &r) == READER_KBD_ARGUMENT, "null kbd");
  REQUIRE(reader_kbd_held_count(k, NULL) == READER_KBD_ARGUMENT, "null count");
  REQUIRE(held(k) == 1, "state unchanged after every error");
  S(k, rc, ev(UP, READER_KBD_KEY_RIGHT, 0, 0, 0), A_NONE, EAT, READER_KBD_REASON_KEY_UP_SWALLOWED);
  REQUIRE(reader_kbd_destroy(NULL) == READER_KBD_OK, "destroy null");
  ok = 1;
done:
  (void)reader_kbd_destroy(k);
  return ok;
}

static int chk_page_matrix(void) {
  int ok = 0;
  reader_kbd_context rc = ctx(READER_KBD_FOCUS_READER, 0, 1);
  reader_kbd *k = make(LIN_, LTR, HW, 0);
  REQUIRE(k, "create");
  TAP(k, rc, READER_KBD_KEY_RIGHT, 0, 0, A_NEXT, EAT, R_ACT);
  TAP(k, rc, READER_KBD_KEY_LEFT, 0, 0, A_PREV, EAT, R_ACT);
  TAP(k, rc, READER_KBD_KEY_DOWN, 0, 0, A_NONE, PASS_, READER_KBD_REASON_UNMAPPED);
  TAP(k, rc, READER_KBD_KEY_UP, 0, 0, A_NONE, PASS_, READER_KBD_REASON_UNMAPPED);
  TAP(k, rc, READER_KBD_KEY_PAGE_DOWN, 0, 0, A_NEXT, EAT, R_ACT);
  TAP(k, rc, READER_KBD_KEY_PAGE_UP, 0, 0, A_PREV, EAT, R_ACT);
  TAP(k, rc, READER_KBD_KEY_SPACE, 0, 0, A_NEXT, EAT, R_ACT);
  TAP(k, rc, READER_KBD_KEY_SPACE, 0, SH, A_PREV, EAT, R_ACT);
  (void)reader_kbd_destroy(k);
  k = make(LIN_, RTL, HW, 0);
  TAP(k, rc, READER_KBD_KEY_RIGHT, 0, 0, A_PREV, EAT, R_ACT);
  TAP(k, rc, READER_KBD_KEY_LEFT, 0, 0, A_NEXT, EAT, R_ACT);
  TAP(k, rc, READER_KBD_KEY_DOWN, 0, 0, A_NONE, PASS_, READER_KBD_REASON_UNMAPPED);
  TAP(k, rc, READER_KBD_KEY_PAGE_DOWN, 0, 0, A_NEXT, EAT, R_ACT);
  TAP(k, rc, READER_KBD_KEY_SPACE, 0, 0, A_NEXT, EAT, R_ACT);
  (void)reader_kbd_destroy(k);
  k = make(LIN_, VERT, HW, 0);
  TAP(k, rc, READER_KBD_KEY_DOWN, 0, 0, A_NEXT, EAT, R_ACT);
  TAP(k, rc, READER_KBD_KEY_UP, 0, 0, A_PREV, EAT, R_ACT);
  TAP(k, rc, READER_KBD_KEY_LEFT, 0, 0, A_NEXT, EAT, R_ACT);
  TAP(k, rc, READER_KBD_KEY_RIGHT, 0, 0, A_PREV, EAT, R_ACT);
  S(k, rc, ev(DOWN, READER_KBD_KEY_UP, 0, SH, 0), A_NONE, PASS_, READER_KBD_REASON_MODIFIER_CONFLICT);
  ok = 1;
done:
  (void)reader_kbd_destroy(k);
  return ok;
}

static int chk_page_gating(void) {
  int ok = 0;
  reader_kbd_context rc = ctx(READER_KBD_FOCUS_READER, 0, 1);
  reader_kbd *k = make(LIN_, LTR, READER_PREFERENCES_INPUT_TAP, 0);
  uint32_t input;
  REQUIRE(k, "create");
  for (input = 1; input <= 3; ++input) {
    reader_kbd_config c = cfg(LIN_, LTR, input, 0);
    REQUIRE(reader_kbd_set_config(k, &c) == READER_KBD_OK, "set");
    TAP(k, rc, READER_KBD_KEY_RIGHT, 0, 0, A_NONE, PASS_, READER_KBD_REASON_PAGE_KEYS_DISABLED);
    TAP(k, rc, READER_KBD_KEY_SPACE, 0, 0, A_NONE, PASS_, READER_KBD_REASON_PAGE_KEYS_DISABLED);
    TAP(k, rc, K_CHAR, 'f', CT, A_SEARCH, EAT, R_ACT); /* commands stay available */
    TAP(k, rc, READER_KBD_KEY_ESCAPE, 0, 0, A_BACK, EAT, R_ACT);
  }
  {
    reader_kbd_config c = cfg(LIN_, LTR, READER_PREFERENCES_INPUT_TAP, READER_KBD_CONFIG_ALWAYS_PAGE_KEYS);
    REQUIRE(reader_kbd_set_config(k, &c) == READER_KBD_OK, "set always");
    TAP(k, rc, READER_KBD_KEY_RIGHT, 0, 0, A_NEXT, EAT, R_ACT);
  }
  ok = 1;
done:
  (void)reader_kbd_destroy(k);
  return ok;
}

static int chk_commands(void) {
  int ok = 0;
  reader_kbd_context rc = ctx(READER_KBD_FOCUS_READER, 0, 1);
  uint32_t plats[3] = {WIN_, LIN_, AND_};
  uint32_t i;
  reader_kbd *k = NULL;
  for (i = 0; i < 3; ++i) {
    k = make(plats[i], LTR, HW, 0);
    REQUIRE(k, "create");
    TAP(k, rc, K_CHAR, 'f', CT, A_SEARCH, EAT, R_ACT);
    TAP(k, rc, K_CHAR, 'F', CT, A_SEARCH, EAT, R_ACT);
    TAP(k, rc, K_CHAR, 't', CT, A_TOC, EAT, R_ACT);
    TAP(k, rc, K_CHAR, 'd', CT, A_MARK, EAT, R_ACT);
    TAP(k, rc, READER_KBD_KEY_ESCAPE, 0, 0, A_BACK, EAT, R_ACT);
    TAP(k, rc, READER_KBD_KEY_BROWSER_BACK, 0, 0, A_BACK, EAT, R_ACT);
    TAP(k, rc, READER_KBD_KEY_LEFT, 0, AL, A_BACK, EAT, R_ACT);
    TAP(k, rc, K_CHAR, '[', CT, A_NONE, PASS_, READER_KBD_REASON_UNMAPPED);
    (void)reader_kbd_destroy(k);
    k = NULL;
  }
  k = make(APL_, LTR, HW, 0);
  REQUIRE(k, "create apple");
  TAP(k, rc, K_CHAR, 'f', ME, A_SEARCH, EAT, R_ACT);
  TAP(k, rc, K_CHAR, 't', ME, A_TOC, EAT, R_ACT);
  TAP(k, rc, K_CHAR, 'd', ME, A_MARK, EAT, R_ACT);
  TAP(k, rc, K_CHAR, '[', ME, A_BACK, EAT, R_ACT);
  TAP(k, rc, READER_KBD_KEY_ESCAPE, 0, 0, A_BACK, EAT, R_ACT);
  TAP(k, rc, READER_KBD_KEY_LEFT, 0, AL, A_NONE, PASS_, READER_KBD_REASON_MODIFIER_CONFLICT);
  TAP(k, rc, K_CHAR, 'f', CT, A_NONE, PASS_, READER_KBD_REASON_MODIFIER_CONFLICT);
  ok = 1;
done:
  (void)reader_kbd_destroy(k);
  return ok;
}

static int chk_conflicts(void) {
  int ok = 0;
  reader_kbd_context rc = ctx(READER_KBD_FOCUS_READER, 0, 1);
  reader_kbd *k = make(LIN_, LTR, HW, 0);
  const uint32_t C = READER_KBD_REASON_MODIFIER_CONFLICT;
  REQUIRE(k, "create");
  TAP(k, rc, K_CHAR, 'f', CT | SH, A_NONE, PASS_, C);
  TAP(k, rc, K_CHAR, 'f', CT | AL, A_NONE, PASS_, C);
  TAP(k, rc, K_CHAR, 'f', CT | ME, A_NONE, PASS_, C);
  TAP(k, rc, K_CHAR, 'f', ME, A_NONE, PASS_, C);
  TAP(k, rc, K_CHAR, 'f', AG, A_NONE, PASS_, C);
  TAP(k, rc, K_CHAR, 'f', CT | AG, A_NONE, PASS_, C);
  TAP(k, rc, K_CHAR, 'f', 0, A_NONE, PASS_, C);
  TAP(k, rc, READER_KBD_KEY_LEFT, 0, SH, A_NONE, PASS_, C);
  TAP(k, rc, READER_KBD_KEY_LEFT, 0, CT, A_NONE, PASS_, C);
  TAP(k, rc, READER_KBD_KEY_LEFT, 0, AL | SH, A_NONE, PASS_, C);
  TAP(k, rc, READER_KBD_KEY_RIGHT, 0, AL, A_NONE, PASS_, C);
  TAP(k, rc, READER_KBD_KEY_SPACE, 0, CT, A_NONE, PASS_, C);
  TAP(k, rc, READER_KBD_KEY_PAGE_DOWN, 0, SH, A_NONE, PASS_, C);
  TAP(k, rc, READER_KBD_KEY_ESCAPE, 0, SH, A_NONE, PASS_, C);
  TAP(k, rc, K_CHAR, 'x', 0, A_NONE, PASS_, READER_KBD_REASON_UNMAPPED);
  TAP(k, rc, K_CHAR, 'x', CT, A_NONE, PASS_, READER_KBD_REASON_UNMAPPED);
  TAP(k, rc, READER_KBD_KEY_HOME, 0, 0, A_NONE, PASS_, READER_KBD_REASON_UNMAPPED);
  TAP(k, rc, READER_KBD_KEY_ENTER, 0, 0, A_NONE, PASS_, READER_KBD_REASON_UNMAPPED);
  TAP(k, rc, K_CHAR, 0, CT, A_NONE, PASS_, READER_KBD_REASON_UNMAPPED);
  TAP(k, rc, K_CHAR, 0xff46u, CT, A_NONE, PASS_, READER_KBD_REASON_UNMAPPED); /* fullwidth f */
  TAP(k, rc, K_CHAR, 0x10ffffu, CT, A_NONE, PASS_, READER_KBD_REASON_UNMAPPED);
  TAP(k, rc, READER_KBD_KEY_UP, 0, SH, A_NONE, PASS_, READER_KBD_REASON_UNMAPPED);
  ok = 1;
done:
  (void)reader_kbd_destroy(k);
  return ok;
}

static int chk_context_gating(void) {
  int ok = 0;
  reader_kbd *k = make(LIN_, LTR, HW, 0);
  reader_kbd_context text = ctx(READER_KBD_FOCUS_TEXT_INPUT, 0, 1);
  reader_kbd_context modal = ctx(READER_KBD_FOCUS_MODAL, 0, 1);
  reader_kbd_context ime = ctx(READER_KBD_FOCUS_READER, 1, 1);
  reader_kbd_context imetext = ctx(READER_KBD_FOCUS_TEXT_INPUT, 1, 1);
  reader_kbd_context inactive = ctx(READER_KBD_FOCUS_READER, 0, 0);
  reader_kbd_context inactivetext = ctx(READER_KBD_FOCUS_TEXT_INPUT, 1, 0);
  reader_kbd_context control = ctx(READER_KBD_FOCUS_CONTROL, 0, 1);
  REQUIRE(k, "create");
  TAP(k, text, READER_KBD_KEY_RIGHT, 0, 0, A_NONE, PASS_, READER_KBD_REASON_TEXT_INPUT);
  TAP(k, text, K_CHAR, 'f', CT, A_NONE, PASS_, READER_KBD_REASON_TEXT_INPUT);
  TAP(k, text, READER_KBD_KEY_ESCAPE, 0, 0, A_NONE, PASS_, READER_KBD_REASON_TEXT_INPUT);
  TAP(k, text, READER_KBD_KEY_SPACE, 0, 0, A_NONE, PASS_, READER_KBD_REASON_TEXT_INPUT);
  TAP(k, text, K_CHAR, 'x', 0, A_NONE, PASS_, READER_KBD_REASON_TEXT_INPUT);
  TAP(k, modal, READER_KBD_KEY_RIGHT, 0, 0, A_NONE, PASS_, READER_KBD_REASON_MODAL);
  TAP(k, modal, READER_KBD_KEY_ESCAPE, 0, 0, A_NONE, PASS_, READER_KBD_REASON_MODAL);
  TAP(k, modal, K_CHAR, 'f', CT, A_NONE, PASS_, READER_KBD_REASON_MODAL);
  TAP(k, ime, READER_KBD_KEY_RIGHT, 0, 0, A_NONE, PASS_, READER_KBD_REASON_COMPOSING);
  TAP(k, ime, READER_KBD_KEY_SPACE, 0, 0, A_NONE, PASS_, READER_KBD_REASON_COMPOSING);
  TAP(k, ime, READER_KBD_KEY_ESCAPE, 0, 0, A_NONE, PASS_, READER_KBD_REASON_COMPOSING);
  TAP(k, ime, READER_KBD_KEY_ENTER, 0, 0, A_NONE, PASS_, READER_KBD_REASON_COMPOSING);
  TAP(k, imetext, READER_KBD_KEY_RIGHT, 0, 0, A_NONE, PASS_, READER_KBD_REASON_COMPOSING);
  TAP(k, inactive, READER_KBD_KEY_RIGHT, 0, 0, A_NONE, PASS_, READER_KBD_REASON_INACTIVE);
  TAP(k, inactive, K_CHAR, 'f', CT, A_NONE, PASS_, READER_KBD_REASON_INACTIVE);
  TAP(k, inactivetext, READER_KBD_KEY_RIGHT, 0, 0, A_NONE, PASS_, READER_KBD_REASON_INACTIVE);
  TAP(k, control, READER_KBD_KEY_SPACE, 0, 0, A_NONE, PASS_, READER_KBD_REASON_CONTROL_OWNS);
  TAP(k, control, READER_KBD_KEY_SPACE, 0, SH, A_NONE, PASS_, READER_KBD_REASON_CONTROL_OWNS);
  TAP(k, control, READER_KBD_KEY_ENTER, 0, 0, A_NONE, PASS_, READER_KBD_REASON_CONTROL_OWNS);
  TAP(k, control, READER_KBD_KEY_ENTER, 0, CT, A_NONE, PASS_, READER_KBD_REASON_CONTROL_OWNS);
  TAP(k, control, READER_KBD_KEY_RIGHT, 0, 0, A_NEXT, EAT, R_ACT);
  TAP(k, control, K_CHAR, 'f', CT, A_SEARCH, EAT, R_ACT);
  { reader_kbd_context rc = ctx(READER_KBD_FOCUS_READER, 0, 1);
    TAP(k, rc, READER_KBD_KEY_RIGHT, 0, 0, A_NEXT, EAT, R_ACT); }
  ok = 1;
done:
  (void)reader_kbd_destroy(k);
  return ok;
}

static int chk_keyup_pairing(void) {
  int ok = 0;
  reader_kbd *k = make(LIN_, LTR, HW, 0);
  reader_kbd_context rc = ctx(READER_KBD_FOCUS_READER, 0, 1);
  reader_kbd_context text = ctx(READER_KBD_FOCUS_TEXT_INPUT, 0, 1);
  REQUIRE(k, "create");
  S(k, rc, ev(DOWN, READER_KBD_KEY_RIGHT, 0, 0, 0), A_NEXT, EAT, R_ACT);
  S(k, text, ev(UP, READER_KBD_KEY_RIGHT, 0, 0, 0), A_NONE, EAT, READER_KBD_REASON_KEY_UP_SWALLOWED);
  S(k, text, ev(DOWN, READER_KBD_KEY_RIGHT, 0, 0, 0), A_NONE, PASS_, READER_KBD_REASON_TEXT_INPUT);
  S(k, text, ev(UP, READER_KBD_KEY_RIGHT, 0, 0, 0), A_NONE, PASS_, READER_KBD_REASON_KEY_UP);
  S(k, rc, ev(UP, READER_KBD_KEY_LEFT, 0, 0, 0), A_NONE, PASS_, READER_KBD_REASON_KEY_UP);
  S(k, rc, ev(DOWN, K_CHAR, 'f', CT, 0), A_SEARCH, EAT, R_ACT);
  S(k, rc, ev(UP, K_CHAR, 'F', 0, 0), A_NONE, EAT, READER_KBD_REASON_KEY_UP_SWALLOWED); /* Ctrl released first */
  S(k, rc, ev(DOWN, READER_KBD_KEY_RIGHT, 0, 0, 0), A_NEXT, EAT, R_ACT);
  S(k, rc, ev(DOWN, READER_KBD_KEY_RIGHT, 0, 0, 0), A_NEXT, EAT, R_ACT); /* new press restarts hold */
  REQUIRE(held(k) == 1, "one hold");
  S(k, rc, ev(DOWN, READER_KBD_KEY_RIGHT, 0, 0, 0), A_NEXT, EAT, R_ACT);
  S(k, text, ev(DOWN, READER_KBD_KEY_RIGHT, 0, 0, 1), A_NONE, PASS_, READER_KBD_REASON_TEXT_INPUT);
  REQUIRE(held(k) == 0, "focus change in the middle of a hold forgets it");
  S(k, text, ev(UP, READER_KBD_KEY_RIGHT, 0, 0, 0), A_NONE, PASS_, READER_KBD_REASON_KEY_UP);
  ok = 1;
done:
  (void)reader_kbd_destroy(k);
  return ok;
}

static int chk_repeat_policy(void) {
  int ok = 0;
  reader_kbd_context rc = ctx(READER_KBD_FOCUS_READER, 0, 1);
  reader_kbd *k = make(LIN_, LTR, HW, 0);
  reader_kbd_result r;
  reader_kbd_event e;
  uint32_t i;
  REQUIRE(k, "create");
  S(k, rc, ev(DOWN, READER_KBD_KEY_RIGHT, 0, 0, 0), A_NEXT, EAT, R_ACT);
  for (i = 1; i <= READER_KBD_MAX_REPEAT_ACTIONS; ++i) {
    e = ev(DOWN, READER_KBD_KEY_RIGHT, 0, 0, 1);
    REQUIRE(reader_kbd_translate(k, &e, &rc, &r) == READER_KBD_OK, "repeat status");
    REQUIRE(r.action == A_NEXT && r.disposition == EAT && r.repeat_actions == i, "repeat action");
  }
  S(k, rc, ev(DOWN, READER_KBD_KEY_RIGHT, 0, 0, 1), A_NONE, EAT, READER_KBD_REASON_REPEAT_LIMIT);
  S(k, rc, ev(DOWN, READER_KBD_KEY_RIGHT, 0, 0, 1), A_NONE, EAT, READER_KBD_REASON_REPEAT_LIMIT);
  S(k, rc, ev(UP, READER_KBD_KEY_RIGHT, 0, 0, 0), A_NONE, EAT, READER_KBD_REASON_KEY_UP_SWALLOWED);
  S(k, rc, ev(DOWN, READER_KBD_KEY_RIGHT, 0, 0, 0), A_NEXT, EAT, R_ACT);
  e = ev(DOWN, READER_KBD_KEY_RIGHT, 0, 0, 1);
  REQUIRE(reader_kbd_translate(k, &e, &rc, &r) == READER_KBD_OK && r.repeat_actions == 1, "counter restarts");
  S(k, rc, ev(UP, READER_KBD_KEY_RIGHT, 0, 0, 0), A_NONE, EAT, READER_KBD_REASON_KEY_UP_SWALLOWED);
  S(k, rc, ev(DOWN, K_CHAR, 'f', CT, 0), A_SEARCH, EAT, R_ACT);
  for (i = 0; i < 5; ++i) S(k, rc, ev(DOWN, K_CHAR, 'f', CT, 1), A_NONE, EAT, READER_KBD_REASON_REPEAT_SUPPRESSED);
  S(k, rc, ev(UP, K_CHAR, 'f', CT, 0), A_NONE, EAT, READER_KBD_REASON_KEY_UP_SWALLOWED);
  S(k, rc, ev(DOWN, READER_KBD_KEY_ESCAPE, 0, 0, 0), A_BACK, EAT, R_ACT);
  S(k, rc, ev(DOWN, READER_KBD_KEY_ESCAPE, 0, 0, 1), A_NONE, EAT, READER_KBD_REASON_REPEAT_SUPPRESSED);
  S(k, rc, ev(UP, READER_KBD_KEY_ESCAPE, 0, 0, 0), A_NONE, EAT, READER_KBD_REASON_KEY_UP_SWALLOWED);
  S(k, rc, ev(DOWN, READER_KBD_KEY_LEFT, 0, 0, 1), A_NONE, PASS_, READER_KBD_REASON_ORPHAN_REPEAT);
  S(k, rc, ev(DOWN, K_CHAR, 'x', 0, 1), A_NONE, PASS_, READER_KBD_REASON_UNMAPPED);
  {
    reader_kbd_config c = cfg(LIN_, LTR, HW, READER_KBD_CONFIG_NO_REPEAT_PAGING);
    REQUIRE(reader_kbd_set_config(k, &c) == READER_KBD_OK, "set");
  }
  S(k, rc, ev(DOWN, READER_KBD_KEY_LEFT, 0, 0, 0), A_PREV, EAT, R_ACT);
  S(k, rc, ev(DOWN, READER_KBD_KEY_LEFT, 0, 0, 1), A_NONE, EAT, READER_KBD_REASON_REPEAT_SUPPRESSED);
  ok = 1;
done:
  (void)reader_kbd_destroy(k);
  return ok;
}

static int chk_held_overflow(void) {
  int ok = 0;
  reader_kbd *k = make(LIN_, LTR, HW, 0);
  reader_kbd_context rc = ctx(READER_KBD_FOCUS_READER, 0, 1);
  REQUIRE(k, "create");
  S(k, rc, ev(DOWN, READER_KBD_KEY_RIGHT, 0, 0, 0), A_NEXT, EAT, R_ACT);
  S(k, rc, ev(DOWN, READER_KBD_KEY_LEFT, 0, 0, 0), A_PREV, EAT, R_ACT);
  S(k, rc, ev(DOWN, READER_KBD_KEY_PAGE_DOWN, 0, 0, 0), A_NEXT, EAT, R_ACT);
  S(k, rc, ev(DOWN, READER_KBD_KEY_PAGE_UP, 0, 0, 0), A_PREV, EAT, R_ACT);
  S(k, rc, ev(DOWN, READER_KBD_KEY_SPACE, 0, 0, 0), A_NEXT, EAT, R_ACT);
  S(k, rc, ev(DOWN, READER_KBD_KEY_ESCAPE, 0, 0, 0), A_BACK, EAT, R_ACT);
  S(k, rc, ev(DOWN, K_CHAR, 'f', CT, 0), A_SEARCH, EAT, R_ACT);
  S(k, rc, ev(DOWN, K_CHAR, 't', CT, 0), A_TOC, EAT, R_ACT);
  REQUIRE(held(k) == READER_KBD_MAX_HELD, "table full");
  S(k, rc, ev(DOWN, K_CHAR, 'd', CT, 0), A_MARK, EAT, R_ACT);
  REQUIRE(held(k) == READER_KBD_MAX_HELD, "bounded at the hard limit");
  S(k, rc, ev(UP, READER_KBD_KEY_RIGHT, 0, 0, 0), A_NONE, PASS_, READER_KBD_REASON_KEY_UP); /* oldest evicted */
  S(k, rc, ev(UP, K_CHAR, 'd', 0, 0), A_NONE, EAT, READER_KBD_REASON_KEY_UP_SWALLOWED);
  S(k, rc, ev(UP, READER_KBD_KEY_LEFT, 0, 0, 0), A_NONE, EAT, READER_KBD_REASON_KEY_UP_SWALLOWED);
  REQUIRE(held(k) == 6, "six remain");
  ok = 1;
done:
  (void)reader_kbd_destroy(k);
  return ok;
}

static int chk_cancel(void) {
  int ok = 0;
  reader_kbd *k = make(LIN_, LTR, HW, 0);
  reader_kbd_context rc = ctx(READER_KBD_FOCUS_READER, 0, 1);
  uint32_t dropped = 99;
  REQUIRE(k, "create");
  S(k, rc, ev(DOWN, READER_KBD_KEY_RIGHT, 0, 0, 0), A_NEXT, EAT, R_ACT);
  S(k, rc, ev(DOWN, READER_KBD_KEY_LEFT, 0, 0, 0), A_PREV, EAT, R_ACT);
  S(k, rc, ev(DOWN, K_CHAR, 'f', CT, 0), A_SEARCH, EAT, R_ACT);
  REQUIRE(reader_kbd_cancel(k, &dropped) == READER_KBD_OK && dropped == 3, "dropped three");
  REQUIRE(held(k) == 0, "empty");
  S(k, rc, ev(UP, READER_KBD_KEY_RIGHT, 0, 0, 0), A_NONE, PASS_, READER_KBD_REASON_KEY_UP);
  S(k, rc, ev(DOWN, READER_KBD_KEY_LEFT, 0, 0, 1), A_NONE, PASS_, READER_KBD_REASON_ORPHAN_REPEAT);
  S(k, rc, ev(DOWN, K_CHAR, 'f', CT, 1), A_NONE, PASS_, READER_KBD_REASON_ORPHAN_REPEAT);
  REQUIRE(reader_kbd_cancel(k, &dropped) == READER_KBD_OK && dropped == 0, "second cancel");
  REQUIRE(reader_kbd_cancel(k, NULL) == READER_KBD_OK, "null dropped");
  S(k, rc, ev(DOWN, READER_KBD_KEY_RIGHT, 0, 0, 0), A_NEXT, EAT, R_ACT);
  ok = 1;
done:
  (void)reader_kbd_destroy(k);
  return ok;
}

typedef struct {
  int calls;
  uint32_t action;
  uint32_t key;
  int answer;
  reader_kbd *kbd;
  int reentry_ok;
} handler_state;

static int handler(void *user, uint32_t action, const reader_kbd_event *event) {
  handler_state *h = (handler_state *)user;
  ++h->calls;
  h->action = action;
  h->key = event->key;
  return h->answer;
}

static int chk_handler_commit(void) {
  int ok = 0;
  reader_kbd *k = make(LIN_, LTR, HW, 0);
  reader_kbd_context rc = ctx(READER_KBD_FOCUS_READER, 0, 1);
  reader_kbd_context text = ctx(READER_KBD_FOCUS_TEXT_INPUT, 0, 1);
  reader_kbd_result r;
  reader_kbd_event e;
  handler_state h;
  memset(&h, 0, sizeof(h));
  REQUIRE(k, "create");
  h.answer = 0; /* decline */
  e = ev(DOWN, READER_KBD_KEY_RIGHT, 0, 0, 0);
  REQUIRE(reader_kbd_dispatch(k, &e, &rc, handler, &h, &r) == READER_KBD_OK, "dispatch");
  REQUIRE(h.calls == 1 && h.action == A_NEXT && h.key == READER_KBD_KEY_RIGHT, "handler saw action");
  REQUIRE(r.disposition == PASS_ && r.action == A_NONE && r.reason == READER_KBD_REASON_DECLINED, "declined result");
  REQUIRE(held(k) == 0, "nothing committed");
  S(k, rc, ev(UP, READER_KBD_KEY_RIGHT, 0, 0, 0), A_NONE, PASS_, READER_KBD_REASON_KEY_UP);
  h.answer = 1; /* accept */
  REQUIRE(reader_kbd_dispatch(k, &e, &rc, handler, &h, &r) == READER_KBD_OK, "dispatch accept");
  REQUIRE(h.calls == 2 && r.disposition == EAT && r.action == A_NEXT && held(k) == 1, "accepted commit");
  h.answer = 0; /* a declined repeat keeps the earlier hold and its counter */
  e = ev(DOWN, READER_KBD_KEY_RIGHT, 0, 0, 1);
  REQUIRE(reader_kbd_dispatch(k, &e, &rc, handler, &h, &r) == READER_KBD_OK &&
          r.reason == READER_KBD_REASON_DECLINED && held(k) == 1, "declined repeat");
  h.answer = 1;
  REQUIRE(reader_kbd_dispatch(k, &e, &rc, handler, &h, &r) == READER_KBD_OK && r.repeat_actions == 1,
          "counter not advanced by the decline");
  e = ev(UP, READER_KBD_KEY_RIGHT, 0, 0, 0);
  h.calls = 0;
  REQUIRE(reader_kbd_dispatch(k, &e, &rc, handler, &h, &r) == READER_KBD_OK && r.disposition == EAT &&
          h.calls == 0, "handler is not called for key-up");
  e = ev(DOWN, READER_KBD_KEY_RIGHT, 0, 0, 0);
  REQUIRE(reader_kbd_dispatch(k, &e, &text, handler, &h, &r) == READER_KBD_OK && h.calls == 0 &&
          r.reason == READER_KBD_REASON_TEXT_INPUT, "handler is not called for pass-through");
  REQUIRE(reader_kbd_dispatch(k, &e, &rc, NULL, NULL, &r) == READER_KBD_OK && r.action == A_NEXT, "null handler");
  ok = 1;
done:
  (void)reader_kbd_destroy(k);
  return ok;
}

static int reentrant_handler(void *user, uint32_t action, const reader_kbd_event *event) {
  handler_state *h = (handler_state *)user;
  reader_kbd_result r;
  reader_kbd_context rc = ctx(READER_KBD_FOCUS_READER, 0, 1);
  reader_kbd_config c = cfg(WIN_, RTL, HW, 0);
  uint32_t n = 0;
  (void)action;
  h->reentry_ok = reader_kbd_translate(h->kbd, event, &rc, &r) == READER_KBD_REENTRANT &&
                  reader_kbd_dispatch(h->kbd, event, &rc, NULL, NULL, &r) == READER_KBD_REENTRANT &&
                  reader_kbd_cancel(h->kbd, &n) == READER_KBD_REENTRANT &&
                  reader_kbd_set_config(h->kbd, &c) == READER_KBD_REENTRANT &&
                  reader_kbd_held_count(h->kbd, &n) == READER_KBD_REENTRANT &&
                  reader_kbd_destroy(h->kbd) == READER_KBD_REENTRANT &&
                  r.action == A_NONE && r.disposition == PASS_;
  return 1;
}

static int chk_reentry(void) {
  int ok = 0;
  reader_kbd *k = make(LIN_, LTR, HW, 0);
  reader_kbd_context rc = ctx(READER_KBD_FOCUS_READER, 0, 1);
  reader_kbd_result r;
  reader_kbd_event e = ev(DOWN, READER_KBD_KEY_RIGHT, 0, 0, 0);
  handler_state h;
  memset(&h, 0, sizeof(h));
  h.kbd = k;
  REQUIRE(k, "create");
  REQUIRE(reader_kbd_dispatch(k, &e, &rc, reentrant_handler, &h, &r) == READER_KBD_OK, "dispatch");
  REQUIRE(h.reentry_ok, "every reentrant call refused with no effect");
  REQUIRE(r.action == A_NEXT && held(k) == 1, "outer call committed once");
  S(k, rc, ev(DOWN, READER_KBD_KEY_LEFT, 0, 0, 0), A_PREV, EAT, R_ACT); /* config still LTR */
  S(k, rc, ev(UP, READER_KBD_KEY_RIGHT, 0, 0, 0), A_NONE, EAT, READER_KBD_REASON_KEY_UP_SWALLOWED);
  ok = 1;
done:
  (void)reader_kbd_destroy(k);
  return ok;
}

static int chk_set_config(void) {
  int ok = 0;
  reader_kbd *k = make(LIN_, LTR, HW, 0);
  reader_kbd_context rc = ctx(READER_KBD_FOCUS_READER, 0, 1);
  reader_kbd_config rtl = cfg(LIN_, RTL, HW, 0);
  reader_kbd_config bad = rtl;
  REQUIRE(k, "create");
  S(k, rc, ev(DOWN, READER_KBD_KEY_RIGHT, 0, 0, 0), A_NEXT, EAT, R_ACT);
  bad.page_turn_direction = 9;
  REQUIRE(reader_kbd_set_config(k, &bad) == READER_KBD_ARGUMENT, "bad config refused");
  REQUIRE(reader_kbd_set_config(k, NULL) == READER_KBD_ARGUMENT, "null config refused");
  S(k, rc, ev(UP, READER_KBD_KEY_RIGHT, 0, 0, 0), A_NONE, EAT, READER_KBD_REASON_KEY_UP_SWALLOWED);
  S(k, rc, ev(DOWN, READER_KBD_KEY_RIGHT, 0, 0, 0), A_NEXT, EAT, R_ACT); /* still LTR */
  REQUIRE(reader_kbd_set_config(k, &rtl) == READER_KBD_OK, "valid config");
  S(k, rc, ev(UP, READER_KBD_KEY_RIGHT, 0, 0, 0), A_NONE, EAT, READER_KBD_REASON_KEY_UP_SWALLOWED); /* hold survived */
  S(k, rc, ev(DOWN, READER_KBD_KEY_RIGHT, 0, 0, 0), A_PREV, EAT, R_ACT);
  ok = 1;
done:
  (void)reader_kbd_destroy(k);
  return ok;
}

static int same(const reader_kbd_event *e, uint32_t phase, uint32_t key, uint32_t cp, uint32_t mods, uint32_t rep) {
  if (e->struct_size != sizeof(*e) || e->phase != phase || e->key != key || e->codepoint != cp ||
      e->modifiers != mods || e->repeat != rep) {
    (void)snprintf(detail, sizeof(detail), "got phase=%u key=%u cp=%u mods=%u rep=%u want %u %u %u %u %u",
                   (unsigned)e->phase, (unsigned)e->key, (unsigned)e->codepoint, (unsigned)e->modifiers,
                   (unsigned)e->repeat, (unsigned)phase, (unsigned)key, (unsigned)cp, (unsigned)mods,
                   (unsigned)rep);
    return 0;
  }
  return 1;
}
#define SAME(e, ph, key, cp, mods, rep) do { if (!same(&(e), (ph), (key), (cp), (mods), (rep))) goto done; } while (0)

static int chk_win32(void) {
  int ok = 0;
  reader_kbd_event e;
  uint32_t comp = 9;
  const uint32_t W_SH = READER_KBD_WIN32_SHIFT, W_CT = READER_KBD_WIN32_CTRL, W_LA = READER_KBD_WIN32_LALT,
                 W_RA = READER_KBD_WIN32_RALT, W_WIN = READER_KBD_WIN32_WIN;
  REQUIRE(reader_kbd_event_from_win32(0x100, 0x27, 0, 0, &e, &comp) == READER_KBD_OK && comp == 0, "right");
  SAME(e, DOWN, READER_KBD_KEY_RIGHT, 0, 0, 0);
  REQUIRE(reader_kbd_event_from_win32(0x100, 0x27, (int64_t)1 << 30, 0, &e, NULL) == READER_KBD_OK, "repeat");
  SAME(e, DOWN, READER_KBD_KEY_RIGHT, 0, 0, 1);
  REQUIRE(reader_kbd_event_from_win32(0x101, 0x27, (int64_t)0xc0000001ll, 0, &e, NULL) == READER_KBD_OK, "up");
  SAME(e, UP, READER_KBD_KEY_RIGHT, 0, 0, 0);
  REQUIRE(reader_kbd_event_from_win32(0x104, 0x25, 0, W_LA, &e, NULL) == READER_KBD_OK, "alt left");
  SAME(e, DOWN, READER_KBD_KEY_LEFT, 0, AL, 0);
  REQUIRE(reader_kbd_event_from_win32(0x100, 0x46, 0, W_CT, &e, NULL) == READER_KBD_OK, "ctrl f");
  SAME(e, DOWN, K_CHAR, 'f', CT, 0);
  REQUIRE(reader_kbd_event_from_win32(0x100, 0x46, 0, W_CT | W_RA, &e, NULL) == READER_KBD_OK, "altgr");
  SAME(e, DOWN, K_CHAR, 'f', AG, 0);
  REQUIRE(reader_kbd_event_from_win32(0x100, 0x46, 0, W_CT | W_LA | W_RA, &e, NULL) == READER_KBD_OK, "ctrl+both alts");
  SAME(e, DOWN, K_CHAR, 'f', CT | AL, 0);
  REQUIRE(reader_kbd_event_from_win32(0x100, 0x46, 0, W_CT | W_SH | W_WIN, &e, NULL) == READER_KBD_OK, "ctrl shift win");
  SAME(e, DOWN, K_CHAR, 'f', CT | SH | ME, 0);
  REQUIRE(reader_kbd_event_from_win32(0x100, 0xe5, 0, 0, &e, &comp) == READER_KBD_OK && comp == 1, "process key");
  SAME(e, DOWN, K_CHAR, 0, 0, 0);
  REQUIRE(reader_kbd_event_from_win32(0x100, 0xa6, 0, 0, &e, NULL) == READER_KBD_OK, "browser back");
  SAME(e, DOWN, READER_KBD_KEY_BROWSER_BACK, 0, 0, 0);
  REQUIRE(reader_kbd_event_from_win32(0x100, 0xdb, 0, W_CT, &e, NULL) == READER_KBD_OK, "bracket");
  SAME(e, DOWN, K_CHAR, '[', CT, 0);
  REQUIRE(reader_kbd_event_from_win32(0x100, 0x70, 0, 0, &e, NULL) == READER_KBD_OK, "f1 unidentified");
  SAME(e, DOWN, K_CHAR, 0, 0, 0);
  REQUIRE(reader_kbd_event_from_win32(0x102, 0x41, 0, 0, &e, &comp) == READER_KBD_ARGUMENT && e.struct_size == 0 &&
          comp == 0, "WM_CHAR refused");
  REQUIRE(reader_kbd_event_from_win32(0x100, 0x41, 0, 0, NULL, NULL) == READER_KBD_ARGUMENT, "null out");
  ok = 1;
done:
  return ok;
}

static int chk_x11(void) {
  int ok = 0;
  reader_kbd_event e;
  REQUIRE(reader_kbd_event_from_x11(2, 0xff53, 0, 0, &e) == READER_KBD_OK, "right");
  SAME(e, DOWN, READER_KBD_KEY_RIGHT, 0, 0, 0);
  REQUIRE(reader_kbd_event_from_x11(2, 0xff53, 0, 7, &e) == READER_KBD_OK, "repeat flag normalized");
  SAME(e, DOWN, READER_KBD_KEY_RIGHT, 0, 0, 1);
  REQUIRE(reader_kbd_event_from_x11(3, 0x46, 0x05, 0, &e) == READER_KBD_OK, "shift ctrl F up");
  SAME(e, UP, K_CHAR, 'f', SH | CT, 0);
  REQUIRE(reader_kbd_event_from_x11(2, 0x66, 0x04 | 0x02 | 0x10, 0, &e) == READER_KBD_OK, "caps+num ignored");
  SAME(e, DOWN, K_CHAR, 'f', CT, 0);
  REQUIRE(reader_kbd_event_from_x11(2, 0x66, 0x08 | 0x40 | 0x80, 0, &e) == READER_KBD_OK, "alt super altgr");
  SAME(e, DOWN, K_CHAR, 'f', AL | ME | AG, 0);
  REQUIRE(reader_kbd_event_from_x11(2, 0xff1b, 0, 0, &e) == READER_KBD_OK, "escape");
  SAME(e, DOWN, READER_KBD_KEY_ESCAPE, 0, 0, 0);
  REQUIRE(reader_kbd_event_from_x11(2, 0xffbe, 0, 0, &e) == READER_KBD_OK, "F1 unidentified");
  SAME(e, DOWN, K_CHAR, 0, 0, 0);
  REQUIRE(reader_kbd_event_from_x11(4, 0x66, 0, 0, &e) == READER_KBD_ARGUMENT && e.struct_size == 0, "ButtonPress refused");
  ok = 1;
done:
  return ok;
}

static int chk_apple(void) {
  int ok = 0;
  reader_kbd_event e;
  const uint64_t numpad_fn = (1ull << 21) | (1ull << 23);
  REQUIRE(reader_kbd_event_from_apple(10, 0x7c, numpad_fn, 0xf703, 0, &e) == READER_KBD_OK, "right arrow");
  SAME(e, DOWN, READER_KBD_KEY_RIGHT, 0, 0, 0);
  REQUIRE(reader_kbd_event_from_apple(10, 0x03, 1ull << 20, 'f', 0, &e) == READER_KBD_OK, "cmd f");
  SAME(e, DOWN, K_CHAR, 'f', ME, 0);
  REQUIRE(reader_kbd_event_from_apple(10, 0x03, (1ull << 20) | (1ull << 16), 'f', 1, &e) == READER_KBD_OK, "caps ignored");
  SAME(e, DOWN, K_CHAR, 'f', ME, 1);
  REQUIRE(reader_kbd_event_from_apple(11, 0x03, (1ull << 17) | (1ull << 18) | (1ull << 19), 'F', 0, &e) == READER_KBD_OK, "shift ctrl opt up");
  SAME(e, UP, K_CHAR, 'F', SH | CT | AL, 0);
  REQUIRE(reader_kbd_event_from_apple(10, 0x35, 0, 0x1b, 0, &e) == READER_KBD_OK, "escape");
  SAME(e, DOWN, READER_KBD_KEY_ESCAPE, 0, 0, 0);
  REQUIRE(reader_kbd_event_from_apple(10, 0x1e, 1ull << 20, '[', 0, &e) == READER_KBD_OK, "cmd bracket");
  SAME(e, DOWN, K_CHAR, '[', ME, 0);
  REQUIRE(reader_kbd_event_from_apple(10, 0x03, 0, 0xd800u, 0, &e) == READER_KBD_OK, "surrogate dropped");
  SAME(e, DOWN, K_CHAR, 0, 0, 0);
  REQUIRE(reader_kbd_event_from_apple(12, 0x03, 0, 'f', 0, &e) == READER_KBD_ARGUMENT && e.struct_size == 0, "flagsChanged refused");
  ok = 1;
done:
  return ok;
}

static int chk_android(void) {
  int ok = 0;
  reader_kbd_event e;
  REQUIRE(reader_kbd_event_from_android(0, 22, 0, 0, &e) == READER_KBD_OK, "dpad right");
  SAME(e, DOWN, READER_KBD_KEY_RIGHT, 0, 0, 0);
  REQUIRE(reader_kbd_event_from_android(0, 34, 0x1000, 0, &e) == READER_KBD_OK, "ctrl f");
  SAME(e, DOWN, K_CHAR, 'f', CT, 0);
  REQUIRE(reader_kbd_event_from_android(1, 4, 0, 0, &e) == READER_KBD_OK, "back up");
  SAME(e, UP, READER_KBD_KEY_BROWSER_BACK, 0, 0, 0);
  REQUIRE(reader_kbd_event_from_android(0, 21, 0x2 | 0x1, 3, &e) == READER_KBD_OK, "alt shift left repeat");
  SAME(e, DOWN, READER_KBD_KEY_LEFT, 0, AL | SH, 1);
  REQUIRE(reader_kbd_event_from_android(0, 10, 0x10000, 0, &e) == READER_KBD_OK, "meta digit 3");
  SAME(e, DOWN, K_CHAR, '3', ME, 0);
  REQUIRE(reader_kbd_event_from_android(0, 999, 0, 0, &e) == READER_KBD_OK, "unknown key");
  SAME(e, DOWN, K_CHAR, 0, 0, 0);
  REQUIRE(reader_kbd_event_from_android(2, 22, 0, 0, &e) == READER_KBD_ARGUMENT && e.struct_size == 0, "ACTION_MULTIPLE refused");
  ok = 1;
done:
  return ok;
}

static int chk_translator_to_actions(void) {
  int ok = 0;
  reader_kbd_context rc = ctx(READER_KBD_FOCUS_READER, 0, 1);
  reader_kbd_event e;
  uint32_t comp = 0;
  reader_kbd *k = make(WIN_, LTR, HW, 0);
  REQUIRE(k, "windows kbd");
  REQUIRE(reader_kbd_event_from_win32(0x100, 0x46, 0, READER_KBD_WIN32_CTRL, &e, &comp) == READER_KBD_OK, "w1");
  S(k, rc, e, A_SEARCH, EAT, R_ACT);
  REQUIRE(reader_kbd_event_from_win32(0x100, 0x46, 0, READER_KBD_WIN32_CTRL | READER_KBD_WIN32_RALT, &e, &comp) == READER_KBD_OK, "w2");
  S(k, rc, e, A_NONE, PASS_, READER_KBD_REASON_MODIFIER_CONFLICT);
  REQUIRE(reader_kbd_event_from_win32(0x100, 0xe5, 0, 0, &e, &comp) == READER_KBD_OK && comp == 1, "w3");
  rc.composing = comp;
  S(k, rc, e, A_NONE, PASS_, READER_KBD_REASON_COMPOSING);
  (void)reader_kbd_destroy(k);
  rc.composing = 0;
  k = make(APL_, LTR, HW, 0);
  REQUIRE(reader_kbd_event_from_apple(10, 0x03, 1ull << 20, 'f', 0, &e) == READER_KBD_OK, "a1");
  S(k, rc, e, A_SEARCH, EAT, R_ACT);
  REQUIRE(reader_kbd_event_from_apple(10, 0x03, 1ull << 18, 'f', 0, &e) == READER_KBD_OK, "a2");
  S(k, rc, e, A_NONE, PASS_, READER_KBD_REASON_MODIFIER_CONFLICT);
  (void)reader_kbd_destroy(k);
  k = make(LIN_, RTL, HW, 0);
  REQUIRE(reader_kbd_event_from_x11(2, 0xff51, 0, 0, &e) == READER_KBD_OK, "x1");
  S(k, rc, e, A_NEXT, EAT, R_ACT);
  (void)reader_kbd_destroy(k);
  k = make(AND_, LTR, HW, 0);
  REQUIRE(reader_kbd_event_from_android(0, 4, 0, 0, &e) == READER_KBD_OK, "d1");
  S(k, rc, e, A_BACK, EAT, R_ACT);
  ok = 1;
done:
  (void)reader_kbd_destroy(k);
  return ok;
}

typedef struct { const char *name; int (*fn)(void); } check;
static const check checks[] = {
  {"abi-and-names", chk_abi}, {"config-from-preferences", chk_from_preferences},
  {"struct-validation", chk_struct_validation}, {"page-direction-matrix", chk_page_matrix},
  {"page-input-gating", chk_page_gating}, {"command-matrix", chk_commands},
  {"modifier-conflicts", chk_conflicts}, {"context-gating", chk_context_gating},
  {"keyup-pairing", chk_keyup_pairing}, {"repeat-policy", chk_repeat_policy},
  {"held-table-limit", chk_held_overflow}, {"cancel", chk_cancel},
  {"handler-commit-boundary", chk_handler_commit}, {"reentry-refused", chk_reentry},
  {"set-config-atomic", chk_set_config}, {"win32-translator", chk_win32},
  {"x11-translator", chk_x11}, {"apple-translator", chk_apple},
  {"android-translator", chk_android}, {"translator-to-actions", chk_translator_to_actions},
};

int main(void) {
  size_t i;
  int failures = 0;
  for (i = 0; i < sizeof(checks) / sizeof(checks[0]); ++i) {
    int pass;
    detail[0] = 0;
    pass = checks[i].fn();
    (void)printf("CHECK %s %s %s\n", checks[i].name, pass ? "PASS" : "FAIL", pass ? "" : detail);
    if (!pass) ++failures;
  }
  (void)printf("c-consumer %s\n", failures ? "failed" : "ok");
  return failures ? 1 : 0;
}
