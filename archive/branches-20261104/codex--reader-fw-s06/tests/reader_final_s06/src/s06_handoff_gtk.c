/* SPDX-License-Identifier: MIT */
/* Real GTK3 handoff: the probe owns text/uri-list on the X11 clipboard and
   reads it back through the installed EXReaderDesktopDrop GTK adapter. */
#include "s06_handoff_internal.h"
#include <exr_desktop_drop_gtk.h>
#include <gtk/gtk.h>
#include <stdio.h>
#include <string.h>

static char *handoff_uris[S06_HANDOFF_MAX_ITEMS];
static size_t handoff_uri_count;

static void handoff_fill(GtkClipboard *clipboard, GtkSelectionData *data, guint info, gpointer user) {
  GString *list;
  size_t index;
  (void)clipboard;
  (void)user;
  if (info != 0) return;
  list = g_string_new(NULL);
  for (index = 0; index < handoff_uri_count; index++) {
    g_string_append(list, handoff_uris[index]);
    g_string_append(list, "\r\n");
  }
  gtk_selection_data_set(data, gtk_selection_data_get_target(data), 8,
      (const guchar *)list->str, (gint)list->len);
  g_string_free(list, TRUE);
}

static void handoff_clear(GtkClipboard *clipboard, gpointer user) {
  (void)clipboard;
  (void)user;
}

int s06_handoff_deliver(const char *const *paths, size_t count, s06_handoff_result *out) {
  static GtkTargetEntry entries[] = {{(gchar *)"text/uri-list", 0, 0}};
  GtkClipboard *clipboard;
  exr_drop_status status;
  exr_drop_request *request = NULL;
  size_t index;
  memset(out, 0, sizeof(*out));
  out->status = -1;
  if (count == 0 || count > S06_HANDOFF_MAX_ITEMS) {
    snprintf(out->detail, sizeof(out->detail), "unsupported handoff item count %zu", count);
    return 0;
  }
  if (!gtk_init_check(NULL, NULL)) {
    snprintf(out->detail, sizeof(out->detail), "gtk_init_check failed; no display available");
    return 0;
  }
  for (index = 0; index < count; index++) {
    GError *error = NULL;
    handoff_uris[index] = g_filename_to_uri(paths[index], NULL, &error);
    if (!handoff_uris[index]) {
      snprintf(out->detail, sizeof(out->detail), "g_filename_to_uri failed for item %zu: %s",
          index, error ? error->message : "unknown");
      if (error) g_error_free(error);
      return 0;
    }
  }
  handoff_uri_count = count;
  clipboard = gtk_clipboard_get(GDK_SELECTION_CLIPBOARD);
  if (!gtk_clipboard_set_with_data(clipboard, entries, 1, handoff_fill, handoff_clear, NULL)) {
    snprintf(out->detail, sizeof(out->detail), "gtk_clipboard_set_with_data was refused");
    return 0;
  }
  status = exr_drop_gtk_clipboard_request(clipboard, EXR_DROP_ORIGIN_CLIPBOARD, NULL, &request);
  s06_handoff_collect(status, request, "gtk3-clipboard-text/uri-list", out);
  return 1;
}
