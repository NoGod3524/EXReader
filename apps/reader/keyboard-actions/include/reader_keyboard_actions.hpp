// SPDX-License-Identifier: MIT
#ifndef READER_KEYBOARD_ACTIONS_HPP
#define READER_KEYBOARD_ACTIONS_HPP
#include "reader_keyboard_actions.h"

#include <cstdint>
#include <utility>

namespace reader {

namespace detail {

// The C layer calls the host handler while the object is locked. Exceptions must
// not cross that C frame: the trampoline below turns a throw into "declined",
// which makes the C layer take its ordinary rollback path and clears the in-call
// flag, so the object stays usable.
struct HandlerSlot {
  reader_kbd_handler fn;
  void *user;
};

inline int keyboard_actions_trampoline(void *slot, uint32_t action, const reader_kbd_event *event) {
  HandlerSlot *state = static_cast<HandlerSlot *>(slot);
  try {
    return state->fn(state->user, action, event);
  } catch (...) {
    return 0;
  }
}

}  // namespace detail

// Move-only owner of one reader_kbd. Construct, use and destroy on one thread;
// destruction from another thread reports WRONG_THREAD and leaks the object
// rather than racing it, which is why the handle is dropped but never freed.
class KeyboardActions {
 public:
  using Handler = reader_kbd_handler;

  KeyboardActions() = default;
  explicit KeyboardActions(const reader_kbd_config &config) {
    status_ = reader_kbd_create(&config, &kbd_);
  }
  KeyboardActions(const KeyboardActions &) = delete;
  KeyboardActions &operator=(const KeyboardActions &) = delete;
  KeyboardActions(KeyboardActions &&other) noexcept : kbd_(other.kbd_), status_(other.status_) {
    other.kbd_ = nullptr;
  }
  KeyboardActions &operator=(KeyboardActions &&other) noexcept {
    if (this != &other) {
      reset();
      kbd_ = other.kbd_;
      status_ = other.status_;
      other.kbd_ = nullptr;
    }
    return *this;
  }
  ~KeyboardActions() { reset(); }

  reader_kbd_status create_status() const { return status_; }
  explicit operator bool() const { return kbd_ != nullptr; }
  reader_kbd *get() const { return kbd_; }

  reader_kbd_status translate(const reader_kbd_event &event, const reader_kbd_context &context,
                              reader_kbd_result &result) {
    return reader_kbd_translate(kbd_, &event, &context, &result);
  }
  // handler may be nullptr, which behaves exactly like translate().
  reader_kbd_status dispatch(const reader_kbd_event &event, const reader_kbd_context &context,
                             Handler handler, void *user, reader_kbd_result &result) {
    if (handler == nullptr) return reader_kbd_translate(kbd_, &event, &context, &result);
    detail::HandlerSlot slot{handler, user};
    return reader_kbd_dispatch(kbd_, &event, &context, &detail::keyboard_actions_trampoline, &slot,
                               &result);
  }
  reader_kbd_status cancel(uint32_t *dropped = nullptr) { return reader_kbd_cancel(kbd_, dropped); }
  reader_kbd_status set_config(const reader_kbd_config &config) {
    return reader_kbd_set_config(kbd_, &config);
  }
  reader_kbd_status held_count(uint32_t &count) const {
    return reader_kbd_held_count(kbd_, &count);
  }

 private:
  void reset() {
    if (kbd_ && reader_kbd_destroy(kbd_) == READER_KBD_OK) kbd_ = nullptr;
    else kbd_ = nullptr;  // wrong thread or reentry: the object is intentionally not freed
  }
  reader_kbd *kbd_ = nullptr;
  reader_kbd_status status_ = READER_KBD_OK;
};

}  // namespace reader
#endif
