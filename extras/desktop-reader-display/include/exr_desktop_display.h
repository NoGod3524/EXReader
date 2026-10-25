/* SPDX-License-Identifier: MIT */
#ifndef EXR_DESKTOP_DISPLAY_H
#define EXR_DESKTOP_DISPLAY_H
#include <stddef.h>
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
#define EXR_DISPLAY_ABI 1u
#define EXR_DISPLAY_MAX_LEASES 64u
#define EXR_DISPLAY_MAX_REASON_BYTES 256u
#define EXR_DISPLAY_MIN_LEASE_MS 100u
#define EXR_DISPLAY_MAX_LEASE_MS 600000u

typedef enum {
  EXR_DISPLAY_OK = 0, EXR_DISPLAY_ARGUMENT, EXR_DISPLAY_NO_MEMORY,
  EXR_DISPLAY_LIMIT, EXR_DISPLAY_WRONG_THREAD, EXR_DISPLAY_REENTRANT,
  EXR_DISPLAY_INACTIVE, EXR_DISPLAY_PENDING, EXR_DISPLAY_UNAVAILABLE,
  EXR_DISPLAY_CANCELLED, EXR_DISPLAY_EXPIRED, EXR_DISPLAY_WINDOW_GONE
} exr_display_status;
typedef struct exr_display_lease exr_display_lease;
typedef struct {
  size_t struct_size;
  void *native_window; /* live top-level HWND (Win32) or GtkWindow* (GTK3). */
  const char *reason;  /* 1..256 UTF-8 bytes, NUL-terminated, no controls. Copied. */
  uint32_t lease_ms;   /* bounded monotonic lifetime; set_active(1) renews it. */
} exr_display_options;
typedef struct {
  size_t struct_size;
  exr_display_status state;
  uint64_t generation;
  uint64_t native_identity; /* borrowed HANDLE value / GNOME cookie; never free. */
  uint64_t expires_at_ms;   /* platform monotonic clock, not wall-clock. */
  uint32_t native_error;    /* Win32 error / GError code; diagnostic only. */
  int requested, pending, window_alive;
} exr_display_observation;

/* Independent, SDK-free, static C ABI; no exceptions, user callbacks, worker
 * threads, settings changes, brightness control or suspend inhibition.
 * Windows: only PowerRequestDisplayRequired. GTK3: session manager IDLE=8,
 * never SUSPEND=4; this is a desktop-policy request, not proof of screen state.
 *
 * All functions on a lease run on its creating native UI thread. GTK callers
 * must use the GTK main thread and iterate the default GMainContext; a custom
 * thread-default context is rejected. Win32 callers must pump window messages.
 * Timers expire/reconcile within 50 ms while that event loop is serviced.
 * No unbounded native lease is intentionally created, but blocking/stopping
 * the host event loop delays expiry: close/cancel before stopping that loop.
 * Up to 64 live (including pending-close) leases per process. One async Linux
 * request per lease; 2-second reply timeout. Name-owner and release calls time out after 1 second
 * each; Unix bus connection authentication uses GLib defaults. Close releases native state synchronously;
 * pending replies retain only bounded internal cleanup state until dispatched.
 *
 * create initializes *out=NULL on failure and never enables inhibition.
 * set_active(1) means active READING content, not merely an active app. Native
 * visibility, focus and minimization are also enforced. set_active(0), cancel,
 * hide, minimize, focus loss, window destruction and expiry revoke the lease.
 * Explicit set_active(1) retries UNAVAILABLE/cancel/expiry; no silent fallback.
 * observe is a snapshot (output untouched on argument/thread/reentry errors).
 * Generation advances whenever a prior request is invalidated. Late replies
 * release their own cookie against the ORIGINAL unique D-Bus service owner;
 * they cannot reactivate a different window/generation. Each Linux lease owns
 * a private bus connection, so timeout/close/process exit removes its requests.
 * Linux service missing/denied/disconnected is UNAVAILABLE, not success.
 *
 * No user callbacks occur. Native dispatch reentry while an API is operating
 * is rejected with REENTRANT, without changing state. close(NULL) is OK; any
 * other handle is consumed only on OK. Do not access a consumed handle; an
 * observe/close concurrent with another call is not supported. Wrong-thread
 * calls leave the handle and observation unchanged. Destroying the window
 * does not free the lease; the owner must still close it. */
exr_display_status exr_display_create(const exr_display_options *, exr_display_lease **out);
exr_display_status exr_display_set_active(exr_display_lease *, int active);
exr_display_status exr_display_cancel(exr_display_lease *);
exr_display_status exr_display_observe(exr_display_lease *, exr_display_observation *out);
exr_display_status exr_display_close(exr_display_lease *);
const char *exr_display_status_name(exr_display_status);
const char *exr_display_build_id(void); /* module source stamp, not a runtime capability */
#ifdef __cplusplus
}
#endif
#endif
