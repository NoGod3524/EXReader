/* SPDX-License-Identifier: MIT */
#include "reader_keyboard_actions.h"

#include <string.h>

static void begin(reader_kbd_event *out) {
  memset(out, 0, sizeof(*out));
  out->struct_size = (uint32_t)sizeof(*out);
}

static void named(reader_kbd_event *out, uint32_t key) { out->key = key; }

static void character(reader_kbd_event *out, uint32_t cp) {
  out->key = READER_KBD_KEY_CHAR;
  out->codepoint = cp;
}

reader_kbd_status reader_kbd_event_from_win32(uint32_t message, uint64_t wparam, int64_t lparam,
                                              uint32_t mods, reader_kbd_event *out,
                                              uint32_t *composing) {
  uint32_t vk = (uint32_t)(wparam & 0xffffu);
  if (composing) *composing = 0;
  if (!out) return READER_KBD_ARGUMENT;
  begin(out);
  if (message == 0x100u || message == 0x104u) {
    out->phase = READER_KBD_PHASE_DOWN;
    out->repeat = (uint32_t)((lparam >> 30) & 1);
  } else if (message == 0x101u || message == 0x105u) {
    out->phase = READER_KBD_PHASE_UP;
  } else {
    begin(out);
    out->struct_size = 0;
    return READER_KBD_ARGUMENT;
  }
  if (mods & READER_KBD_WIN32_SHIFT) out->modifiers |= READER_KBD_MOD_SHIFT;
  if ((mods & READER_KBD_WIN32_CTRL) && (mods & READER_KBD_WIN32_RALT) &&
      !(mods & READER_KBD_WIN32_LALT)) {
    out->modifiers |= READER_KBD_MOD_ALTGR; /* AltGr is reported as Ctrl+right Alt */
  } else {
    if (mods & READER_KBD_WIN32_CTRL) out->modifiers |= READER_KBD_MOD_CTRL;
    if (mods & (READER_KBD_WIN32_LALT | READER_KBD_WIN32_RALT)) out->modifiers |= READER_KBD_MOD_ALT;
  }
  if (mods & READER_KBD_WIN32_WIN) out->modifiers |= READER_KBD_MOD_META;
  if (vk >= 0x41u && vk <= 0x5au) character(out, vk + 32u);
  else if (vk >= 0x30u && vk <= 0x39u) character(out, vk);
  else switch (vk) {
    case 0x25: named(out, READER_KBD_KEY_LEFT); break;
    case 0x26: named(out, READER_KBD_KEY_UP); break;
    case 0x27: named(out, READER_KBD_KEY_RIGHT); break;
    case 0x28: named(out, READER_KBD_KEY_DOWN); break;
    case 0x21: named(out, READER_KBD_KEY_PAGE_UP); break;
    case 0x22: named(out, READER_KBD_KEY_PAGE_DOWN); break;
    case 0x24: named(out, READER_KBD_KEY_HOME); break;
    case 0x23: named(out, READER_KBD_KEY_END); break;
    case 0x20: named(out, READER_KBD_KEY_SPACE); break;
    case 0x0d: named(out, READER_KBD_KEY_ENTER); break;
    case 0x1b: named(out, READER_KBD_KEY_ESCAPE); break;
    case 0x08: named(out, READER_KBD_KEY_BACKSPACE); break;
    case 0x09: named(out, READER_KBD_KEY_TAB); break;
    case 0xa6: named(out, READER_KBD_KEY_BROWSER_BACK); break;
    case 0xdb: character(out, '['); break;
    case 0xe5: if (composing) *composing = 1; break; /* VK_PROCESSKEY: unidentified */
    default: break;
  }
  return READER_KBD_OK;
}

reader_kbd_status reader_kbd_event_from_x11(uint32_t type, uint32_t keysym, uint32_t state,
                                            uint32_t repeat, reader_kbd_event *out) {
  if (!out) return READER_KBD_ARGUMENT;
  begin(out);
  if (type == 2u) {
    out->phase = READER_KBD_PHASE_DOWN;
    out->repeat = repeat ? 1u : 0u;
  } else if (type == 3u) {
    out->phase = READER_KBD_PHASE_UP;
  } else {
    out->struct_size = 0;
    return READER_KBD_ARGUMENT;
  }
  if (state & 0x01u) out->modifiers |= READER_KBD_MOD_SHIFT;   /* ShiftMask */
  if (state & 0x04u) out->modifiers |= READER_KBD_MOD_CTRL;    /* ControlMask */
  if (state & 0x08u) out->modifiers |= READER_KBD_MOD_ALT;     /* Mod1Mask */
  if (state & 0x40u) out->modifiers |= READER_KBD_MOD_META;    /* Mod4Mask (Super) */
  if (state & 0x80u) out->modifiers |= READER_KBD_MOD_ALTGR;   /* Mod5Mask (Level3) */
  if (keysym >= 0x41u && keysym <= 0x5au) character(out, keysym + 32u);
  else if (keysym >= 0x61u && keysym <= 0x7au) character(out, keysym);
  else if (keysym >= 0x30u && keysym <= 0x39u) character(out, keysym);
  else switch (keysym) {
    case 0xff51: named(out, READER_KBD_KEY_LEFT); break;
    case 0xff52: named(out, READER_KBD_KEY_UP); break;
    case 0xff53: named(out, READER_KBD_KEY_RIGHT); break;
    case 0xff54: named(out, READER_KBD_KEY_DOWN); break;
    case 0xff55: named(out, READER_KBD_KEY_PAGE_UP); break;
    case 0xff56: named(out, READER_KBD_KEY_PAGE_DOWN); break;
    case 0xff50: named(out, READER_KBD_KEY_HOME); break;
    case 0xff57: named(out, READER_KBD_KEY_END); break;
    case 0x20: named(out, READER_KBD_KEY_SPACE); break;
    case 0xff0d: named(out, READER_KBD_KEY_ENTER); break;
    case 0xff1b: named(out, READER_KBD_KEY_ESCAPE); break;
    case 0xff08: named(out, READER_KBD_KEY_BACKSPACE); break;
    case 0xff09: named(out, READER_KBD_KEY_TAB); break;
    case 0x5b: character(out, '['); break;
    default: break;
  }
  return READER_KBD_OK;
}

reader_kbd_status reader_kbd_event_from_apple(uint32_t type, uint32_t key_code, uint64_t flags,
                                              uint32_t unmodified_codepoint, uint32_t is_repeat,
                                              reader_kbd_event *out) {
  if (!out) return READER_KBD_ARGUMENT;
  begin(out);
  if (type == 10u) {
    out->phase = READER_KBD_PHASE_DOWN;
    out->repeat = is_repeat ? 1u : 0u;
  } else if (type == 11u) {
    out->phase = READER_KBD_PHASE_UP;
  } else {
    out->struct_size = 0;
    return READER_KBD_ARGUMENT;
  }
  if (flags & (1ull << 17)) out->modifiers |= READER_KBD_MOD_SHIFT;
  if (flags & (1ull << 18)) out->modifiers |= READER_KBD_MOD_CTRL;
  if (flags & (1ull << 19)) out->modifiers |= READER_KBD_MOD_ALT;
  if (flags & (1ull << 20)) out->modifiers |= READER_KBD_MOD_META;
  switch (key_code) {
    case 0x7b: named(out, READER_KBD_KEY_LEFT); break;
    case 0x7c: named(out, READER_KBD_KEY_RIGHT); break;
    case 0x7d: named(out, READER_KBD_KEY_DOWN); break;
    case 0x7e: named(out, READER_KBD_KEY_UP); break;
    case 0x74: named(out, READER_KBD_KEY_PAGE_UP); break;
    case 0x79: named(out, READER_KBD_KEY_PAGE_DOWN); break;
    case 0x73: named(out, READER_KBD_KEY_HOME); break;
    case 0x77: named(out, READER_KBD_KEY_END); break;
    case 0x31: named(out, READER_KBD_KEY_SPACE); break;
    case 0x24: case 0x4c: named(out, READER_KBD_KEY_ENTER); break;
    case 0x35: named(out, READER_KBD_KEY_ESCAPE); break;
    case 0x33: named(out, READER_KBD_KEY_BACKSPACE); break;
    case 0x30: named(out, READER_KBD_KEY_TAB); break;
    default:
      if (unmodified_codepoint <= READER_KBD_MAX_CODEPOINT &&
          !(unmodified_codepoint >= 0xd800u && unmodified_codepoint <= 0xdfffu)) {
        character(out, unmodified_codepoint);
      }
      break;
  }
  return READER_KBD_OK;
}

reader_kbd_status reader_kbd_event_from_android(uint32_t action, uint32_t key_code,
                                                uint32_t meta_state, uint32_t repeat_count,
                                                reader_kbd_event *out) {
  if (!out) return READER_KBD_ARGUMENT;
  begin(out);
  if (action == 0u) {
    out->phase = READER_KBD_PHASE_DOWN;
    out->repeat = repeat_count > 0u ? 1u : 0u;
  } else if (action == 1u) {
    out->phase = READER_KBD_PHASE_UP;
  } else {
    out->struct_size = 0;
    return READER_KBD_ARGUMENT;
  }
  if (meta_state & 0x1u) out->modifiers |= READER_KBD_MOD_SHIFT;     /* META_SHIFT_ON */
  if (meta_state & 0x2u) out->modifiers |= READER_KBD_MOD_ALT;       /* META_ALT_ON */
  if (meta_state & 0x1000u) out->modifiers |= READER_KBD_MOD_CTRL;   /* META_CTRL_ON */
  if (meta_state & 0x10000u) out->modifiers |= READER_KBD_MOD_META;  /* META_META_ON */
  if (key_code >= 29u && key_code <= 54u) character(out, 'a' + (key_code - 29u));
  else if (key_code >= 7u && key_code <= 16u) character(out, '0' + (key_code - 7u));
  else switch (key_code) {
    case 21: named(out, READER_KBD_KEY_LEFT); break;
    case 22: named(out, READER_KBD_KEY_RIGHT); break;
    case 19: named(out, READER_KBD_KEY_UP); break;
    case 20: named(out, READER_KBD_KEY_DOWN); break;
    case 92: named(out, READER_KBD_KEY_PAGE_UP); break;
    case 93: named(out, READER_KBD_KEY_PAGE_DOWN); break;
    case 122: named(out, READER_KBD_KEY_HOME); break;
    case 123: named(out, READER_KBD_KEY_END); break;
    case 62: named(out, READER_KBD_KEY_SPACE); break;
    case 66: named(out, READER_KBD_KEY_ENTER); break;
    case 111: named(out, READER_KBD_KEY_ESCAPE); break;
    case 67: named(out, READER_KBD_KEY_BACKSPACE); break;
    case 61: named(out, READER_KBD_KEY_TAB); break;
    case 4: named(out, READER_KBD_KEY_BROWSER_BACK); break;
    case 71: character(out, '['); break;
    default: break;
  }
  return READER_KBD_OK;
}
