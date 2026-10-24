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
 * RegisterDragDrop(window, ...) with this module's IDropTarget; OLE owns the
 * COM reference, the returned handle owns one more. The adapter accepts
 * CF_HDROP, CF_UNICODETEXT and "FileGroupDescriptorW" (a promised virtual
 * file, reported as EXR_DROP_ITEM_VIRTUAL; the file is never materialised).
 * Every other format is answered with DROPEFFECT_NONE.
 *
 * Attach, detach and the callback all run on the window's thread; detach from
 * any other thread returns EXR_DROP_WRONG_THREAD. The callback may detach its
 * own target; the COM object then stays alive until OLE releases it after
 * Drop() returns, so no OLE call ever touches freed memory. If the window is
 * destroyed first, detach only frees memory. */
typedef struct exr_drop_windows_target exr_drop_windows_target;

exr_drop_status exr_drop_windows_attach(HWND window, const exr_drop_target_options *options,
    exr_drop_windows_target **target);
/* Same rules as exr_drop_target_destroy(), which it forwards to. */
exr_drop_status exr_drop_windows_detach(exr_drop_windows_target *target);

/* Parse an HDROP the caller owns (drag data object or clipboard). Paths are
   read with DragQueryFileW; the handle is not freed. */
exr_drop_status exr_drop_windows_request_from_hdrop(HDROP drop, exr_drop_origin origin,
    const exr_drop_control *control, exr_drop_request **out);
/* Read one of CF_HDROP, CF_UNICODETEXT or "FileGroupDescriptorW" from any
   IDataObject (OLE drag data object, shell object, test double). Formats are
   tried in that order; EXR_DROP_UNSUPPORTED when none is available. */
exr_drop_status exr_drop_windows_request_from_data_object(IDataObject *object,
    exr_drop_origin origin, const exr_drop_control *control, exr_drop_request **out);
/* Read the current clipboard while it is open: CF_HDROP, else CF_UNICODETEXT,
   else EXR_DROP_EMPTY. EXR_DROP_PLATFORM when the clipboard stays busy after
   80 ms of bounded retries. The request owns copies; it stays valid after the
   clipboard closes and the owning process exits. */
exr_drop_status exr_drop_windows_clipboard_request(exr_drop_origin origin,
    const exr_drop_control *control, exr_drop_request **out);

/* Deliver a completed drop through the entry OLE calls for IDropTarget::Drop,
   with the same effect negotiation and callback ownership rules. Hosts use it
   to forward a drop another window received; automated acceptance uses it
   where no pointer device can start a drag. */
exr_drop_status exr_drop_windows_deliver_drop(exr_drop_windows_target *target, IDataObject *object,
    DWORD *effect);

#ifdef __cplusplus
}
#endif
#endif
#endif
