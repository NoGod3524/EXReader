/* SPDX-License-Identifier: MIT */
#ifndef EXR_DESKTOP_DROP_WINDOWS_H
#define EXR_DESKTOP_DROP_WINDOWS_H
#include "exr_desktop_drop.h"
#ifdef _WIN32
#include <windows.h>
#include <ole2.h>

#ifdef __cplusplus
extern "C" {
#endif

/* Win32 delivery for the desktop drop adapter.
 *
 * Register one drop target per window on the STA thread that owns that window
 * and has called OleInitialize(). exr_drop_windows_attach() calls
 * RegisterDragDrop(window, ...) with this module's IDropTarget, then installs
 * one native chainable window subclass so the registration can be released while
 * the window is still valid: WM_DESTROY revokes the OLE registration (which
 * drops OLE's reference) and WM_NCDESTROY removes this module's subclass. The
 * returned handle owns the remaining reference; detach, before or after the
 * window dies, therefore frees the COM object and never leaves one behind.
 * Other native subclasses may attach and detach in either order. Messages pass
 * through DefSubclassProc; detach removes only this module's own entry. Failure
 * to install the subclass revokes the new OLE registration and returns PLATFORM.
 *
 * The adapter accepts CF_HDROP, CF_UNICODETEXT and "FileGroupDescriptorW" (a
 * promised virtual file, reported as EXR_DROP_ITEM_VIRTUAL; the file is never
 * materialised). Every other format is answered with DROPEFFECT_NONE.
 *
 * Every HGLOBAL is bounded by its real allocation before any element is read:
 * CF_UNICODETEXT must carry a NUL inside GlobalSize() (an odd trailing byte is
 * unusable), "FileGroupDescriptorW" must hold its whole declared descriptor
 * array, and an HDROP must have a complete DROPFILES header, an in-range
 * pFiles offset and a wide or ANSI list that terminates inside the allocation.
 * A malformed buffer is refused with EXR_DROP_PLATFORM and never parsed.
 *
 * Attach, detach and the callback all run on the window's thread; detach from
 * any other thread returns EXR_DROP_WRONG_THREAD. */
typedef struct exr_drop_windows_target exr_drop_windows_target;

exr_drop_status exr_drop_windows_attach(HWND window, const exr_drop_target_options *options,
    exr_drop_windows_target **target);
/* Same rules as exr_drop_target_destroy(), which it forwards to. */
exr_drop_status exr_drop_windows_detach(exr_drop_windows_target *target);

/* Parse an HDROP the caller owns (drag data object or clipboard). The handle
   is validated against its allocation first and never freed. */
exr_drop_status exr_drop_windows_request_from_hdrop(HDROP drop, exr_drop_origin origin,
    const exr_drop_control *control, exr_drop_request **out);
/* Read one of CF_HDROP, CF_UNICODETEXT or "FileGroupDescriptorW" from any
   IDataObject (OLE drag data object, shell object, test double). Formats are
   tried in that order; EXR_DROP_UNSUPPORTED when none is available and
   EXR_DROP_PLATFORM when the offered buffer is malformed or truncated. */
exr_drop_status exr_drop_windows_request_from_data_object(IDataObject *object,
    exr_drop_origin origin, const exr_drop_control *control, exr_drop_request **out);
/* Read the current clipboard while it is open: CF_HDROP, else CF_UNICODETEXT,
   else EXR_DROP_EMPTY. EXR_DROP_PLATFORM when the clipboard stays busy after
   80 ms of bounded retries or hands back a malformed buffer. The request owns
   copies; it stays valid after the clipboard closes and the owning process
   exits. */
exr_drop_status exr_drop_windows_clipboard_request(exr_drop_origin origin,
    const exr_drop_control *control, exr_drop_request **out);

/* Deliver a completed drop through the entry OLE calls for IDropTarget::Drop,
   with the same effect negotiation and callback ownership rules. Hosts use it
   to forward a drop another window received; automated acceptance uses it
   where no pointer device can start a drag. */
exr_drop_status exr_drop_windows_deliver_drop(exr_drop_windows_target *target, IDataObject *object,
    DWORD *effect);

#ifdef EXR_DESKTOP_DROP_TEST_HOOKS
/* Acceptance only, compiled out of the installed binary unless the module is
   built with EXR_DESKTOP_DROP_TEST_HOOKS: live COM target objects. A completed
   attach/detach pair, including one where the window died first, must return
   to the previous value, which proves the object was reclaimed. */
size_t exr_drop_windows_test_live_targets(void);
/* Fail one subclass installation after the real OLE registration, so acceptance
   can verify rollback. Absent from the normal installed package. */
void exr_drop_windows_test_fail_next_subclass_install(void);
#endif

#ifdef __cplusplus
}
#endif
#endif
#endif
