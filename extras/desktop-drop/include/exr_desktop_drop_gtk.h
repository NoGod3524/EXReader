/* SPDX-License-Identifier: MIT */
#ifndef EXR_DESKTOP_DROP_GTK_H
#define EXR_DESKTOP_DROP_GTK_H
#include "exr_desktop_drop.h"
#include <gtk/gtk.h>

#ifdef __cplusplus
extern "C" {
#endif

/* GTK3 delivery for the desktop drop adapter.
 *
 * exr_drop_gtk_attach() installs a real drop destination on one widget
 * (gtk_drag_dest_set with GTK_DEST_DEFAULT_MOTION | GTK_DEST_DEFAULT_DROP and
 * the targets text/uri-list and x-special/gnome-copied-files) and connects the
 * drag-data-received / drag-leave signals. It must run on the GTK main thread;
 * the target remembers that thread's GThread and refuses detach from any other
 * one with EXR_DROP_WRONG_THREAD.
 *
 * exr_drop_gtk_request_from_selection() is the drop and paste payload entry:
 * it reads the selection target, passes the exact bytes GTK delivered to the
 * strict parser and returns the request. exr_drop_gtk_clipboard_request() does
 * the paste route: it asks the clipboard for text/uri-list, then for
 * x-special/gnome-copied-files, and returns EXR_DROP_EMPTY when the clipboard
 * has no owner or neither target. Both are pure readers: they never own, take
 * or clear the clipboard.
 *
 * The request is independent of the GtkSelectionData/GtkClipboard it came
 * from; the caller may free either at once. */
typedef struct exr_drop_gtk_target exr_drop_gtk_target;

exr_drop_status exr_drop_gtk_attach(GtkWidget *widget, const exr_drop_target_options *options,
    exr_drop_gtk_target **target);
/* Same rules as exr_drop_target_destroy(), which it forwards to. */
exr_drop_status exr_drop_gtk_detach(exr_drop_gtk_target *target);

exr_drop_status exr_drop_gtk_request_from_selection(const GtkSelectionData *selection,
    exr_drop_origin origin, const exr_drop_control *control, exr_drop_request **out);
exr_drop_status exr_drop_gtk_clipboard_request(GtkClipboard *clipboard, exr_drop_origin origin,
    const exr_drop_control *control, exr_drop_request **out);

#ifdef __cplusplus
}
#endif
#endif
