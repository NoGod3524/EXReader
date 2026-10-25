/* SPDX-License-Identifier: MIT */
/* Cloud-only gates around the real public atomic-save call. */
#define review_message prefs_original_review_message
#include "../windows_host/worker_review/hooks.h"
#undef review_message
static LRESULT review_message(HWND window, WPARAM code, LPARAM value) {
  if (code == 111 || code == 112) {
    LRESULT armed = prefs_original_review_message(window, 101, 0);
    if (armed) InterlockedExchange(&review_armed, (LONG)code - 100);
    return armed;
  }
  return prefs_original_review_message(window, code, value);
}
