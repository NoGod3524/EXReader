/* SPDX-License-Identifier: MIT */
#include "internal.h"
#include "exr_desktop_drop_gtk.h"
#include <stdlib.h>
#include <string.h>

typedef struct gtk_target {
  struct exr_drop_target base; /* must be first */
  GtkWidget *widget;
  GThread *owner;
  gulong data_handler;
  gulong leave_handler;
  gulong destroy_handler;
  int signals;
} gtk_target;

#define GTK_FROM_BASE(p) ((gtk_target *)(p))

static int gtk_owner_thread(const struct exr_drop_target *base) {
  const gtk_target *target = (const gtk_target *)base;
  return target->owner && g_thread_self() == target->owner;
}

static void gtk_release_object(struct exr_drop_target *base);

static const GtkTargetEntry gtk_entries[] = {
  {(gchar *)"text/uri-list", 0, 0},
  {(gchar *)"x-special/gnome-copied-files", 0, 1}
};

static exr_drop_status gtk_parse(gboolean gnome, const GtkSelectionData *selection,
    exr_drop_origin origin, const exr_drop_control *control, exr_drop_request **out) {
  const guchar *bytes;
  gint length;
  if (!selection) { if (out) *out = NULL; return EXR_DROP_ARGUMENT; }
  bytes = gtk_selection_data_get_data(selection);
  length = gtk_selection_data_get_length(selection);
  if (length < 0 || (length > 0 && !bytes)) {
    if (out) *out = NULL;
    return EXR_DROP_UNSUPPORTED;
  }
  return gnome
      ? exr_drop_request_from_gnome_files((const char *)bytes, (size_t)length, origin, control, out)
      : exr_drop_request_from_uri_list((const char *)bytes, (size_t)length, origin, control, out);
}

exr_drop_status exr_drop_gtk_request_from_selection(const GtkSelectionData *selection,
    exr_drop_origin origin, const exr_drop_control *control, exr_drop_request **out) {
  GdkAtom target;
  gchar *name;
  exr_drop_status status;
  if (!out) return EXR_DROP_ARGUMENT;
  *out = NULL;
  if (!selection) return EXR_DROP_ARGUMENT;
  if (origin < EXR_DROP_ORIGIN_DROP || origin > EXR_DROP_ORIGIN_TEXT) return EXR_DROP_ARGUMENT;
  if (control && control->struct_size != sizeof(*control)) return EXR_DROP_ARGUMENT;
  target = gtk_selection_data_get_target(selection);
  name = target ? gdk_atom_name(target) : NULL;
  if (name && strcmp(name, "text/uri-list") == 0) status = gtk_parse(FALSE, selection, origin, control, out);
  else if (name && strcmp(name, "x-special/gnome-copied-files") == 0)
    status = gtk_parse(TRUE, selection, origin, control, out);
  else status = EXR_DROP_UNSUPPORTED;
  g_free(name);
  return status;
}

exr_drop_status exr_drop_gtk_clipboard_request(GtkClipboard *clipboard, exr_drop_origin origin,
    const exr_drop_control *control, exr_drop_request **out) {
  static const char *const names[] = {"text/uri-list", "x-special/gnome-copied-files"};
  size_t index;
  if (!out) return EXR_DROP_ARGUMENT;
  *out = NULL;
  if (!clipboard) return EXR_DROP_ARGUMENT;
  if (origin < EXR_DROP_ORIGIN_DROP || origin > EXR_DROP_ORIGIN_TEXT) return EXR_DROP_ARGUMENT;
  if (control && control->struct_size != sizeof(*control)) return EXR_DROP_ARGUMENT;
  if (!gtk_clipboard_wait_is_available(clipboard)) return EXR_DROP_EMPTY;
  for (index = 0; index < sizeof(names) / sizeof(*names); index++) {
    GtkSelectionData *selection = gtk_clipboard_wait_for_contents(clipboard,
        gdk_atom_intern_static_string(names[index]));
    if (selection) {
      exr_drop_status status = gtk_parse(index == 1, selection, origin, control, out);
      gtk_selection_data_free(selection);
      return status;
    }
  }
  return EXR_DROP_EMPTY;
}

/* ---- signals --------------------------------------------------------- */
static void gtk_on_data_received(GtkWidget *widget, GdkDragContext *context, gint x, gint y,
    GtkSelectionData *selection, guint info, guint time, gpointer user_data) {
  gtk_target *target = (gtk_target *)user_data;
  exr_drop_request *request = NULL;
  exr_drop_status status;
  (void)widget;
  (void)x;
  (void)y;
  (void)info;
  if (!target) return;
  status = exr_drop_gtk_request_from_selection(selection, EXR_DROP_ORIGIN_DROP,
      drop_target_control(&target->base), &request);
  if (context) gtk_drag_finish(context, status == EXR_DROP_OK, FALSE, time);
  drop_target_deliver(&target->base, status, request);
}
static void gtk_on_drag_leave(GtkWidget *widget, GdkDragContext *context, guint time, gpointer user_data) {
  (void)widget;
  (void)context;
  (void)time;
  (void)user_data;
}
/* GTK drops the signal handlers with the widget; the target must not touch a
   destroyed widget afterwards, so it becomes inert here. */
static void gtk_on_widget_destroy(GtkWidget *widget, gpointer user_data) {
  gtk_target *target = (gtk_target *)user_data;
  (void)widget;
  target->signals = 0;
  target->widget = NULL;
  target->base.dead = 1;
}

/* ---- lifecycle ------------------------------------------------------- */
static void gtk_release_object(struct exr_drop_target *base) {
  gtk_target *target = GTK_FROM_BASE(base);
  if (target->signals && target->widget) {
    GObject *object = G_OBJECT(target->widget);
    if (g_signal_handler_is_connected(object, target->data_handler))
      g_signal_handler_disconnect(object, target->data_handler);
    if (g_signal_handler_is_connected(object, target->leave_handler))
      g_signal_handler_disconnect(object, target->leave_handler);
    if (g_signal_handler_is_connected(object, target->destroy_handler))
      g_signal_handler_disconnect(object, target->destroy_handler);
    target->signals = 0;
    gtk_drag_dest_unset(target->widget);
  }
  free(target);
}

exr_drop_status exr_drop_gtk_attach(GtkWidget *widget, const exr_drop_target_options *options,
    exr_drop_gtk_target **target) {
  gtk_target *created;
  if (!target) return EXR_DROP_ARGUMENT;
  *target = NULL;
  if (!widget || !GTK_IS_WIDGET(widget) || !drop_target_options_valid(options)) return EXR_DROP_ARGUMENT;
  if (!g_main_context_is_owner(g_main_context_default())) return EXR_DROP_PLATFORM;
  created = (gtk_target *)calloc(1, sizeof(*created));
  if (!created) return EXR_DROP_NO_MEMORY;
  drop_target_init(&created->base, options, gtk_owner_thread, gtk_release_object);
  created->widget = widget;
  created->owner = g_thread_self();
  gtk_drag_dest_set(widget, GTK_DEST_DEFAULT_MOTION | GTK_DEST_DEFAULT_DROP, gtk_entries,
      (gint)(sizeof(gtk_entries) / sizeof(*gtk_entries)), GDK_ACTION_COPY);
  created->data_handler = g_signal_connect(widget, "drag-data-received",
      G_CALLBACK(gtk_on_data_received), created);
  created->leave_handler = g_signal_connect(widget, "drag-leave", G_CALLBACK(gtk_on_drag_leave), created);
  created->destroy_handler = g_signal_connect(widget, "destroy", G_CALLBACK(gtk_on_widget_destroy), created);
  created->signals = 1;
  *target = (exr_drop_gtk_target *)created;
  return EXR_DROP_OK;
}

exr_drop_status exr_drop_gtk_detach(exr_drop_gtk_target *target) {
  return exr_drop_target_destroy((exr_drop_target *)target);
}
