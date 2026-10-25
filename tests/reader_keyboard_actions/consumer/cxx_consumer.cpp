// SPDX-License-Identifier: MIT
#include "reader_keyboard_actions.hpp"

#include <cstdio>
#include <cstring>
#include <stdexcept>
#include <thread>
#include <utility>

/* Installed-package C++ consumer. It sees only the installed headers and the
   installed static library: no source path is added to this target. Expectations
   were fixed before any run. Each named check prints
   "CHECK <name> PASS|FAIL <detail>". */

namespace {

char detail[300];

uint32_t u32(reader_kbd_platform value) { return static_cast<uint32_t>(value); }
uint32_t u32(reader_preferences_turn_direction value) { return static_cast<uint32_t>(value); }
uint32_t u32(reader_preferences_turn_input value) { return static_cast<uint32_t>(value); }
uint32_t u32(reader_kbd_focus value) { return static_cast<uint32_t>(value); }
uint32_t u32(reader_kbd_phase value) { return static_cast<uint32_t>(value); }
uint32_t u32(reader_kbd_key value) { return static_cast<uint32_t>(value); }

reader_kbd_config make_config(reader_kbd_platform platform,
                              reader_preferences_turn_direction direction,
                              reader_preferences_turn_input input) {
  reader_kbd_config config;
  std::memset(&config, 0, sizeof(config));
  config.struct_size = static_cast<uint32_t>(sizeof(config));
  config.platform = u32(platform);
  config.page_turn_direction = u32(direction);
  config.page_turn_input = u32(input);
  return config;
}

reader_kbd_context make_context(reader_kbd_focus focus) {
  reader_kbd_context context;
  std::memset(&context, 0, sizeof(context));
  context.struct_size = static_cast<uint32_t>(sizeof(context));
  context.focus = u32(focus);
  context.window_active = 1;
  return context;
}

reader_kbd_event make_event(reader_kbd_phase phase, reader_kbd_key key, uint32_t codepoint,
                            uint32_t modifiers, uint32_t repeat) {
  reader_kbd_event event;
  std::memset(&event, 0, sizeof(event));
  event.struct_size = static_cast<uint32_t>(sizeof(event));
  event.phase = u32(phase);
  event.key = u32(key);
  event.codepoint = codepoint;
  event.modifiers = modifiers;
  event.repeat = repeat;
  return event;
}

int fail(const char *what) {
  std::snprintf(detail, sizeof(detail), "%s", what);
  return 0;
}

struct Recorder {
  int calls = 0;
  uint32_t action = READER_KBD_ACTION_NONE;
  int answer = 1;
};

int accepting_handler(void *user, uint32_t action, const reader_kbd_event *) {
  Recorder *recorder = static_cast<Recorder *>(user);
  ++recorder->calls;
  recorder->action = action;
  return recorder->answer;
}

int throwing_handler(void *user, uint32_t action, const reader_kbd_event *) {
  Recorder *recorder = static_cast<Recorder *>(user);
  ++recorder->calls;
  recorder->action = action;
  throw std::runtime_error("host handler failed");
}

int named_make_move() {
  reader_kbd_config config =
      make_config(READER_KBD_PLATFORM_LINUX, READER_PREFERENCES_TURN_LTR,
                  READER_PREFERENCES_INPUT_HARDWARE_KEYS);
  reader::KeyboardActions first(config);
  if (!first || first.create_status() != READER_KBD_OK) return fail("create");
  reader::KeyboardActions second(std::move(first));
  if (first || !second) return fail("move construction did not transfer ownership");
  reader::KeyboardActions third;
  third = std::move(second);
  if (second || !third) return fail("move assignment did not transfer ownership");
  reader_kbd_result result;
  reader_kbd_context context = make_context(READER_KBD_FOCUS_READER);
  reader_kbd_event event =
      make_event(READER_KBD_PHASE_DOWN, READER_KBD_KEY_RIGHT, 0, 0, 0);
  if (third.translate(event, context, result) != READER_KBD_OK ||
      result.action != READER_KBD_ACTION_PAGE_NEXT)
    return fail("moved-to object is not functional");
  reader::KeyboardActions fourth(std::move(third));
  if (third || !fourth) return fail("second move did not transfer ownership");
  third = std::move(fourth); /* move assignment into a moved-from handle */
  if (!third || fourth) return fail("move assignment from a live handle");
  return 1;
}

int named_dispatch() {
  reader::KeyboardActions kbd(make_config(READER_KBD_PLATFORM_LINUX,
                                         READER_PREFERENCES_TURN_LTR,
                                         READER_PREFERENCES_INPUT_HARDWARE_KEYS));
  if (!kbd) return fail("create");
  reader_kbd_context context = make_context(READER_KBD_FOCUS_READER);
  reader_kbd_result result;
  Recorder recorder;
  reader_kbd_event down = make_event(READER_KBD_PHASE_DOWN, READER_KBD_KEY_CHAR, 'f',
                                     READER_KBD_MOD_CTRL, 0);
  if (kbd.dispatch(down, context, &accepting_handler, &recorder, result) != READER_KBD_OK)
    return fail("dispatch status");
  if (recorder.calls != 1 || recorder.action != READER_KBD_ACTION_SEARCH)
    return fail("handler did not see the search action");
  if (result.action != READER_KBD_ACTION_SEARCH || result.disposition != READER_KBD_CONSUME)
    return fail("accepted action not reported");
  uint32_t held = 99;
  if (kbd.held_count(held) != READER_KBD_OK || held != 1) return fail("accepted action not committed");
  reader_kbd_event up = make_event(READER_KBD_PHASE_UP, READER_KBD_KEY_CHAR, 'f', 0, 0);
  if (kbd.dispatch(up, context, &accepting_handler, &recorder, result) != READER_KBD_OK)
    return fail("dispatch up");
  /* A key-up produces no action, so the handler must not run for it. */
  if (recorder.calls != 1 || result.disposition != READER_KBD_CONSUME ||
      result.reason != READER_KBD_REASON_KEY_UP_SWALLOWED)
    return fail("key-up of a consumed down was not swallowed");
  /* A null handler must behave exactly like translate(). */
  if (kbd.dispatch(up, context, nullptr, nullptr, result) != READER_KBD_OK ||
      result.reason != READER_KBD_REASON_KEY_UP)
    return fail("null handler did not behave like translate");
  return 1;
}

int named_decline_rollback() {
  reader::KeyboardActions kbd(make_config(READER_KBD_PLATFORM_WINDOWS,
                                         READER_PREFERENCES_TURN_LTR,
                                         READER_PREFERENCES_INPUT_HARDWARE_KEYS));
  if (!kbd) return fail("create");
  reader_kbd_context context = make_context(READER_KBD_FOCUS_READER);
  reader_kbd_result result;
  Recorder recorder;
  recorder.answer = 0;
  reader_kbd_event down = make_event(READER_KBD_PHASE_DOWN, READER_KBD_KEY_LEFT, 0, 0, 0);
  if (kbd.dispatch(down, context, &accepting_handler, &recorder, result) != READER_KBD_OK)
    return fail("dispatch status");
  if (recorder.calls != 1 || result.action != READER_KBD_ACTION_NONE ||
      result.disposition != READER_KBD_PASS || result.reason != READER_KBD_REASON_DECLINED)
    return fail("declined action must be reported as PASS/declined");
  uint32_t held = 99;
  if (kbd.held_count(held) != READER_KBD_OK || held != 0) return fail("declined action was committed");
  reader_kbd_event up = make_event(READER_KBD_PHASE_UP, READER_KBD_KEY_LEFT, 0, 0, 0);
  if (kbd.translate(up, context, result) != READER_KBD_OK ||
      result.reason != READER_KBD_REASON_KEY_UP)
    return fail("declined key-down must not swallow its key-up");
  return 1;
}

int named_throw_declines() {
  reader::KeyboardActions kbd(make_config(READER_KBD_PLATFORM_APPLE,
                                         READER_PREFERENCES_TURN_LTR,
                                         READER_PREFERENCES_INPUT_HARDWARE_KEYS));
  if (!kbd) return fail("create");
  reader_kbd_context context = make_context(READER_KBD_FOCUS_READER);
  reader_kbd_result result;
  Recorder recorder;
  reader_kbd_event down = make_event(READER_KBD_PHASE_DOWN, READER_KBD_KEY_PAGE_DOWN, 0, 0, 0);
  if (kbd.dispatch(down, context, &throwing_handler, &recorder, result) != READER_KBD_OK)
    return fail("throwing handler must not escape dispatch");
  if (recorder.calls != 1 || result.disposition != READER_KBD_PASS ||
      result.reason != READER_KBD_REASON_DECLINED)
    return fail("a throw must be reported as a decline");
  uint32_t held = 99;
  if (kbd.held_count(held) != READER_KBD_OK || held != 0) return fail("a throw must not commit state");
  /* The in-call flag must be clear again: a later dispatch still works. */
  Recorder second;
  reader_kbd_event next = make_event(READER_KBD_PHASE_DOWN, READER_KBD_KEY_RIGHT, 0, 0, 0);
  if (kbd.dispatch(next, context, &accepting_handler, &second, result) != READER_KBD_OK)
    return fail("object refused a call after a throwing handler");
  if (second.calls != 1 || result.action != READER_KBD_ACTION_PAGE_NEXT)
    return fail("object is unusable after a throwing handler");
  return 1;
}

int named_wrong_thread() {
  reader::KeyboardActions kbd(make_config(READER_KBD_PLATFORM_LINUX,
                                         READER_PREFERENCES_TURN_LTR,
                                         READER_PREFERENCES_INPUT_HARDWARE_KEYS));
  if (!kbd) return fail("create");
  reader_kbd *raw = kbd.get();
  reader_kbd_context context = make_context(READER_KBD_FOCUS_READER);
  reader_kbd_event event = make_event(READER_KBD_PHASE_DOWN, READER_KBD_KEY_RIGHT, 0, 0, 0);
  reader_kbd_result result;
  reader_kbd_status from_thread = READER_KBD_OK;
  reader_kbd_status destroy_from_thread = READER_KBD_OK;
  uint32_t count_from_thread = 0;
  std::thread worker([&]() {
    from_thread = reader_kbd_translate(raw, &event, &context, &result);
    uint32_t count = 0;
    count_from_thread = reader_kbd_held_count(raw, &count);
    destroy_from_thread = reader_kbd_destroy(raw);
  });
  worker.join();
  if (from_thread != READER_KBD_WRONG_THREAD || count_from_thread != READER_KBD_WRONG_THREAD ||
      destroy_from_thread != READER_KBD_WRONG_THREAD)
    return fail("a foreign thread touched the object");
  /* The owner thread still owns a working object and must free it. */
  if (kbd.translate(event, context, result) != READER_KBD_OK ||
      result.action != READER_KBD_ACTION_PAGE_NEXT)
    return fail("owner thread lost the object after a foreign-thread attempt");
  uint32_t held = 99;
  if (kbd.held_count(held) != READER_KBD_OK || held != 1) return fail("owner state changed");
  return 1;
}

int named_empty_object() {
  reader::KeyboardActions empty;
  if (empty || empty.get() != nullptr) return fail("default object must hold nothing");
  reader_kbd_context context = make_context(READER_KBD_FOCUS_READER);
  reader_kbd_result result;
  reader_kbd_event event = make_event(READER_KBD_PHASE_DOWN, READER_KBD_KEY_RIGHT, 0, 0, 0);
  if (empty.translate(event, context, result) != READER_KBD_ARGUMENT)
    return fail("translate on an empty object must return ARGUMENT");
  if (empty.cancel() != READER_KBD_ARGUMENT) return fail("cancel on an empty object");
  uint32_t held = 0;
  if (empty.held_count(held) != READER_KBD_ARGUMENT) return fail("held_count on an empty object");
  if (empty.set_config(make_config(READER_KBD_PLATFORM_APPLE, READER_PREFERENCES_TURN_RTL,
                                   READER_PREFERENCES_INPUT_TAP)) != READER_KBD_ARGUMENT)
    return fail("set_config on an empty object");
  reader_kbd_event down = make_event(READER_KBD_PHASE_DOWN, READER_KBD_KEY_CHAR, 'f',
                                     READER_KBD_MOD_META, 0);
  if (empty.dispatch(down, context, &accepting_handler, nullptr, result) != READER_KBD_ARGUMENT)
    return fail("dispatch on an empty object");
  return 1;
}

int named_config_and_cancel() {
  reader_preferences preferences = reader_preferences_defaults();
  preferences.page_turn_direction = u32(READER_PREFERENCES_TURN_RTL);
  preferences.page_turn_input = u32(READER_PREFERENCES_INPUT_HARDWARE_KEYS);
  reader_kbd_config config =
      reader_kbd_config_from_preferences(u32(READER_KBD_PLATFORM_APPLE), &preferences, 0);
  reader::KeyboardActions kbd(config);
  if (!kbd) return fail("create from preferences");
  reader_kbd_context context = make_context(READER_KBD_FOCUS_READER);
  reader_kbd_result result;
  reader_kbd_event down = make_event(READER_KBD_PHASE_DOWN, READER_KBD_KEY_RIGHT, 0, 0, 0);
  if (kbd.translate(down, context, result) != READER_KBD_OK ||
      result.action != READER_KBD_ACTION_PAGE_PREVIOUS)
    return fail("RTL direction was not applied");
  reader_kbd_config ltr = make_config(READER_KBD_PLATFORM_APPLE, READER_PREFERENCES_TURN_LTR,
                                      READER_PREFERENCES_INPUT_HARDWARE_KEYS);
  if (kbd.set_config(ltr) != READER_KBD_OK) return fail("set_config");
  uint32_t dropped = 99;
  if (kbd.cancel(&dropped) != READER_KBD_OK || dropped != 1)
    return fail("cancel must drop the hold kept across the preference change");
  reader_kbd_event again = make_event(READER_KBD_PHASE_DOWN, READER_KBD_KEY_RIGHT, 0, 0, 0);
  if (kbd.translate(again, context, result) != READER_KBD_OK ||
      result.action != READER_KBD_ACTION_PAGE_NEXT)
    return fail("new direction was not applied");
  return 1;
}

struct Named {
  const char *name;
  int (*fn)();
};

const Named named[] = {
    {"create-move-ownership", named_make_move},
    {"dispatch-and-keyup", named_dispatch},
    {"decline-rollback", named_decline_rollback},
    {"throw-declines", named_throw_declines},
    {"wrong-thread-refused", named_wrong_thread},
    {"empty-object-argument", named_empty_object},
    {"config-and-cancel", named_config_and_cancel},
};

}  // namespace

int main() {
  int failures = 0;
  for (const Named &entry : named) {
    detail[0] = 0;
    int passed = entry.fn();
    std::printf("CHECK %s %s %s\n", entry.name, passed ? "PASS" : "FAIL", passed ? "" : detail);
    if (!passed) ++failures;
  }
  std::printf("cpp-consumer %s\n", failures ? "failed" : "ok");
  return failures ? 1 : 0;
}
