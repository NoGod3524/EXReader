/* SPDX-License-Identifier: MIT
 * GTK3 acceptance probe: a real GtkWindow with a real drop destination, and a
 * real X11 clipboard owned and read back by this process. Every payload is
 * created here under g_get_tmp_dir(); the session clipboard is overwritten and
 * cleared by the probe itself.
 */
#include <exr_desktop_drop.h>
#include <exr_desktop_drop_gtk.h>
#include "report.h"
#include <glib/gstdio.h>
#include <gtk/gtk.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static GtkWidget *g_window;
static char *g_uri_payload;
static char *g_gnome_payload;
static char *g_text_payload;

typedef struct {
  int calls;
  exr_drop_status status;
  exr_drop_request *request;
  size_t items;
  exr_drop_item_status first_status;
  char first_path[600];
  int hold_request;
  int destroy_in_callback;
  exr_drop_gtk_target *target;
  exr_drop_status destroy_status;
} capture;

static void capture_reset(capture *state) {
  if (state->request) exr_drop_request_release(state->request);
  memset(state, 0, sizeof(*state));
}

static void on_drop(void *context, exr_drop_status status, exr_drop_request *request) {
  capture *state = (capture *)context;
  exr_drop_request_info info;
  state->calls++;
  state->status = status;
  state->items = 0;
  if (request) {
    memset(&info, 0, sizeof(info));
    info.struct_size = sizeof(info);
    if (exr_drop_request_get_info(request, &info) == EXR_DROP_OK && info.item_count) {
      exr_drop_item item;
      state->items = info.item_count;
      memset(&item, 0, sizeof(item));
      item.struct_size = sizeof(item);
      if (exr_drop_request_get_item(request, 0, &item) == EXR_DROP_OK) {
        state->first_status = item.status;
        if (item.path) {
          strncpy(state->first_path, item.path, sizeof(state->first_path) - 1);
          state->first_path[sizeof(state->first_path) - 1] = 0;
        }
      }
    }
    if (state->hold_request)
      state->request = request;
    else
      exr_drop_request_release(request);
  }
  if (state->destroy_in_callback && state->target) {
    state->destroy_status = exr_drop_gtk_detach(state->target);
    state->target = NULL;
  }
}

/* ---- clipboard ownership -------------------------------------------- */
static void clipboard_fill(GtkClipboard *clipboard, GtkSelectionData *data, guint info, gpointer user) {
  const char *payload = info == 2 ? g_text_payload : info == 1 ? g_gnome_payload : g_uri_payload;
  (void)clipboard;
  (void)user;
  if (!payload) return;
  gtk_selection_data_set(data, gtk_selection_data_get_target(data), 8, (const guchar *)payload,
      (gint)strlen(payload));
}
static void clipboard_clear(GtkClipboard *clipboard, gpointer user) {
  (void)clipboard;
  (void)user;
}

static int clipboard_own(const char *uri, const char *gnome, const char *text) {
  static const GtkTargetEntry entries[] = {
    {(gchar *)"text/uri-list", 0, 0},
    {(gchar *)"x-special/gnome-copied-files", 0, 1},
    {(gchar *)"text/plain;charset=utf-8", 0, 2}
  };
  GtkClipboard *clipboard = gtk_clipboard_get(GDK_SELECTION_CLIPBOARD);
  g_free(g_uri_payload);
  g_free(g_gnome_payload);
  g_free(g_text_payload);
  g_uri_payload = uri ? g_strdup(uri) : NULL;
  g_gnome_payload = gnome ? g_strdup(gnome) : NULL;
  g_text_payload = text ? g_strdup(text) : NULL;
  return gtk_clipboard_set_with_data(clipboard, entries, 3, clipboard_fill, clipboard_clear, NULL);
}

static GtkSelectionData *clipboard_contents(const char *target) {
  return gtk_clipboard_wait_for_contents(gtk_clipboard_get(GDK_SELECTION_CLIPBOARD),
      gdk_atom_intern_static_string(target));
}

/* ---- fixtures -------------------------------------------------------- */
static char *tmp_dir;
static char path_file[1200];
static char path_unicode[1200];
static char path_dir[1200];
static char uri_file[1600];
static char uri_unicode[1600];
static char uri_dir[1600];
static char expected_file[1200];
static char expected_unicode[1200];
static char expected_dir[1200];

static void write_file(const char *path) {
  g_file_set_contents(path, "x", 1, NULL);
}
static int make_fixtures(void) {
  GError *error = NULL;
  tmp_dir = g_dir_make_tmp("exr-drop-probe-XXXXXX", &error);
  if (!tmp_dir) {
    if (error) g_error_free(error);
    return 0;
  }
  snprintf(path_file, sizeof(path_file), "%s/a.txt", tmp_dir);
  snprintf(path_unicode, sizeof(path_unicode), "%s/exr drop \xE4\xB8\xAD\xE6\x96\x87.epub", tmp_dir);
  snprintf(path_dir, sizeof(path_dir), "%s/sub", tmp_dir);
  write_file(path_file);
  write_file(path_unicode);
  g_mkdir_with_parents(path_dir, 0700);
  {
    char *uri;
    uri = g_filename_to_uri(path_file, NULL, NULL);
    if (!uri) return 0;
    snprintf(uri_file, sizeof(uri_file), "%s", uri);
    g_free(uri);
    uri = g_filename_to_uri(path_unicode, NULL, NULL);
    if (!uri) return 0;
    snprintf(uri_unicode, sizeof(uri_unicode), "%s", uri);
    g_free(uri);
    uri = g_filename_to_uri(path_dir, NULL, NULL);
    if (!uri) return 0;
    snprintf(uri_dir, sizeof(uri_dir), "%s", uri);
    g_free(uri);
  }
  snprintf(expected_file, sizeof(expected_file), "%s", path_file);
  snprintf(expected_unicode, sizeof(expected_unicode), "%s", path_unicode);
  snprintf(expected_dir, sizeof(expected_dir), "%s", path_dir);
  return 1;
}

/* ---- threads --------------------------------------------------------- */
typedef struct {
  GMainContext *context;
  GMutex mutex;
  GCond condition;
  int ready;
  int held;
  int finishing;
} hold_job;

/* Another thread owns the default main context, as a running GTK loop would. */
static gpointer hold_thread(gpointer data) {
  hold_job *job = (hold_job *)data;
  g_mutex_lock(&job->mutex);
  job->held = g_main_context_acquire(job->context);
  job->ready = 1;
  g_cond_signal(&job->condition);
  while (!job->finishing) g_cond_wait(&job->condition, &job->mutex);
  g_mutex_unlock(&job->mutex);
  if (job->held) g_main_context_release(job->context);
  return NULL;
}

static int attach_status_from_main(exr_drop_gtk_target **out) {
  exr_drop_target_options options;
  memset(&options, 0, sizeof(options));
  options.struct_size = sizeof(options);
  options.on_drop = on_drop;
  return (int)exr_drop_gtk_attach(g_window, &options, out);
}
static gpointer detach_thread(gpointer data) {
  exr_drop_gtk_target *target = (exr_drop_gtk_target *)data;
  return GINT_TO_POINTER((int)exr_drop_gtk_detach(target));
}

/* ---- helpers --------------------------------------------------------- */
static int cancel_probe(void *context) {
  int *seen = (int *)context;
  (*seen)++;
  return *seen > 1;
}

/* ---- cases ----------------------------------------------------------- */
static void case_clipboard_uri(capture *state, const char *name, const char *payload,
    exr_drop_item_status want_item, const char *want_path, size_t want_items) {
  exr_drop_request *request = NULL;
  exr_drop_status status;
  if (!clipboard_own(payload, NULL, NULL)) {
    report_fail(name, "clipboard ownership failed");
    return;
  }
  status = exr_drop_gtk_clipboard_request(gtk_clipboard_get(GDK_SELECTION_CLIPBOARD),
      EXR_DROP_ORIGIN_CLIPBOARD, NULL, &request);
  if (status != EXR_DROP_OK) {
    report_fail(name, exr_drop_status_name(status));
    return;
  }
  {
    exr_drop_request_info info;
    exr_drop_item item;
    memset(&info, 0, sizeof(info));
    info.struct_size = sizeof(info);
    memset(&item, 0, sizeof(item));
    item.struct_size = sizeof(item);
    exr_drop_request_get_info(request, &info);
    exr_drop_request_get_item(request, 0, &item);
    if (info.item_count != want_items || item.status != want_item
        || (want_path && (!item.path || strcmp(item.path, want_path) != 0))) {
      char detail[600];
      snprintf(detail, sizeof(detail), "items=%zu status=%s path=%s", info.item_count,
          exr_drop_item_status_name(item.status), item.path ? item.path : "(null)");
      report_fail(name, detail);
    } else {
      report_pass(name, "real clipboard roundtrip");
    }
    exr_drop_request_release(request);
  }
  (void)state;
}

int main(int argc, char **argv) {
  capture state;
  exr_drop_gtk_target *target = NULL;
  exr_drop_target_options options;
  exr_drop_request *request = NULL;

  memset(&state, 0, sizeof(state));
  report_expect("gtk_init", gtk_init_check(&argc, &argv) != FALSE, "GTK display available");
  g_window = gtk_window_new(GTK_WINDOW_TOPLEVEL);
  report_expect("gtk_window_created", g_window != NULL, "probe window");
  if (!g_window) return report_summary("gtk");
  report_expect("fixtures_created", make_fixtures(), "temp files with a non-ASCII name");

  memset(&options, 0, sizeof(options));
  options.struct_size = sizeof(options);
  options.on_drop = on_drop;
  options.context = &state;
  report_expect("attach_real_widget", exr_drop_gtk_attach(g_window, &options, &target) == EXR_DROP_OK,
      "gtk_drag_dest_set installed");
  {
    GtkTargetList *targets = gtk_drag_dest_get_target_list(g_window);
    guint info = 0;
    report_expect("drop_target_list_registered",
        targets && gtk_target_list_find(targets, gdk_atom_intern_static_string("text/uri-list"), &info),
        "text/uri-list is a registered drop target");
  }
  report_expect("attach_null_widget", exr_drop_gtk_attach(NULL, &options, &target) == EXR_DROP_ARGUMENT,
      "NULL widget refused");
  {
    hold_job job;
    GThread *thread;
    exr_drop_gtk_target *refused = NULL;
    int status;
    memset(&job, 0, sizeof(job));
    g_mutex_init(&job.mutex);
    g_cond_init(&job.condition);
    job.context = g_main_context_default();
    thread = g_thread_new("hold-context", hold_thread, &job);
    g_mutex_lock(&job.mutex);
    while (!job.ready) g_cond_wait(&job.condition, &job.mutex);
    g_mutex_unlock(&job.mutex);
    status = attach_status_from_main(&refused);
    report_expect("attach_while_context_owned",
        job.held && status == (int)EXR_DROP_PLATFORM && refused == NULL,
        "attaching while another thread owns the GTK main context is refused");
    g_mutex_lock(&job.mutex);
    job.finishing = 1;
    g_cond_signal(&job.condition);
    g_mutex_unlock(&job.mutex);
    g_thread_join(thread);
    g_mutex_clear(&job.mutex);
    g_cond_clear(&job.condition);
  }

  case_clipboard_uri(&state, "clipboard_uri_one_file", uri_file, EXR_DROP_ITEM_FILE, expected_file, 1);
  {
    char two[3300];
    snprintf(two, sizeof(two), "%s\r\n%s\r\n", uri_file, uri_unicode);
    case_clipboard_uri(&state, "clipboard_uri_unicode_name", two, EXR_DROP_ITEM_FILE, expected_file, 2);
  }
  case_clipboard_uri(&state, "clipboard_uri_directory", uri_dir, EXR_DROP_ITEM_DIRECTORY, expected_dir, 1);
  case_clipboard_uri(&state, "clipboard_remote_url", "https://example.invalid/x.epub", EXR_DROP_ITEM_REMOTE_URL,
      NULL, 1);
  case_clipboard_uri(&state, "clipboard_remote_host", "file://server/share/x.epub", EXR_DROP_ITEM_REMOTE_HOST,
      NULL, 1);
  case_clipboard_uri(&state, "clipboard_virtual_scheme", "mtp://device/1.epub", EXR_DROP_ITEM_VIRTUAL, NULL, 1);
  case_clipboard_uri(&state, "clipboard_bad_percent", "file:///a%ZZ.epub", EXR_DROP_ITEM_INVALID, NULL, 1);
  case_clipboard_uri(&state, "clipboard_bad_utf8", "file:///a%FF.epub", EXR_DROP_ITEM_BAD_ENCODING, NULL, 1);

  {
    char long_uri[4600];
    size_t used = (size_t)snprintf(long_uri, 16, "file:///");
    while (used < EXR_DROP_MAX_PATH_BYTES + 100) long_uri[used++] = 'a';
    long_uri[used] = 0;
    case_clipboard_uri(&state, "clipboard_too_long_path", long_uri, EXR_DROP_ITEM_TOO_LONG, NULL, 1);
  }
  {
    char cap[64 * 400];
    size_t used = 0, index;
    for (index = 0; index < 300; index++)
      used += (size_t)snprintf(cap + used, 64, "https://example.invalid/%03zu\n", index);
    cap[used] = 0;
    if (!clipboard_own(cap, NULL, NULL)) {
      report_fail("clipboard_item_cap", "clipboard ownership failed");
    } else {
      exr_drop_status status = exr_drop_gtk_clipboard_request(gtk_clipboard_get(GDK_SELECTION_CLIPBOARD),
          EXR_DROP_ORIGIN_CLIPBOARD, NULL, &request);
      exr_drop_request_info info;
      memset(&info, 0, sizeof(info));
      info.struct_size = sizeof(info);
      if (status == EXR_DROP_OK) exr_drop_request_get_info(request, &info);
      report_expect("clipboard_item_cap",
          status == EXR_DROP_OK && info.item_count == 256 && info.overflow_count == 44 && info.truncated,
          "cap at 256 items with overflow recorded");
      exr_drop_request_release(request);
      request = NULL;
    }
  }
  {
    int seen = 0;
    exr_drop_control control;
    memset(&control, 0, sizeof(control));
    control.struct_size = sizeof(control);
    control.cancelled = cancel_probe;
    control.context = &seen;
    char two[3300];
    snprintf(two, sizeof(two), "%s\r\n%s\r\n", uri_file, uri_unicode);
    if (!clipboard_own(two, NULL, NULL)) {
      report_fail("clipboard_cancel", "clipboard ownership failed");
    } else {
      exr_drop_status status = exr_drop_gtk_clipboard_request(gtk_clipboard_get(GDK_SELECTION_CLIPBOARD),
          EXR_DROP_ORIGIN_CLIPBOARD, &control, &request);
      report_expect("clipboard_cancel", status == EXR_DROP_CANCELLED && request == NULL,
          "cancellation honoured on the clipboard route");
      exr_drop_request_release(request);
      request = NULL;
    }
  }
  {
    gtk_clipboard_clear(gtk_clipboard_get(GDK_SELECTION_CLIPBOARD));
    request = NULL;
    report_expect("clipboard_empty",
        exr_drop_gtk_clipboard_request(gtk_clipboard_get(GDK_SELECTION_CLIPBOARD), EXR_DROP_ORIGIN_CLIPBOARD,
            NULL, &request) == EXR_DROP_EMPTY
            && request == NULL,
        "cleared clipboard reported as empty");
  }

  /* ---- genuine GtkSelectionData from the clipboard ------------------- */
  {
    GtkSelectionData *selection;
    if (!clipboard_own(uri_unicode, NULL, NULL)) {
      report_fail("selection_data_unicode", "clipboard ownership failed");
    } else {
      selection = clipboard_contents("text/uri-list");
      if (!selection) {
        report_fail("selection_data_unicode", "no selection data");
      } else {
        request = NULL;
        if (exr_drop_gtk_request_from_selection(selection, EXR_DROP_ORIGIN_DROP, NULL, &request) == EXR_DROP_OK) {
          exr_drop_item item;
          memset(&item, 0, sizeof(item));
          item.struct_size = sizeof(item);
          exr_drop_request_get_item(request, 0, &item);
          report_expect("selection_data_unicode",
              item.status == EXR_DROP_ITEM_FILE && item.path && strcmp(item.path, expected_unicode) == 0,
              "percent-encoded UTF-8 decoded through a real GtkSelectionData");
          exr_drop_request_release(request);
          request = NULL;
        } else {
          report_fail("selection_data_unicode", "selection parse failed");
        }
        gtk_selection_data_free(selection);
      }
    }
  }
  {
    GtkSelectionData *selection;
    if (clipboard_own(NULL, NULL, "plain text") && (selection = clipboard_contents("text/plain;charset=utf-8"))) {
      request = NULL;
      report_expect("selection_wrong_target",
          exr_drop_gtk_request_from_selection(selection, EXR_DROP_ORIGIN_DROP, NULL, &request)
                  == EXR_DROP_UNSUPPORTED
              && request == NULL,
          "a non file-like target is unsupported");
      gtk_selection_data_free(selection);
    } else {
      report_skip("selection_wrong_target", "text target unavailable");
    }
  }
  {
    /* derive a fresh GtkSelectionData for the emitted signal */
    GtkSelectionData *selection;
    if (!clipboard_own(uri_file, NULL, NULL)) {
      report_fail("drag_signal_delivers", "clipboard ownership failed");
    } else {
      selection = clipboard_contents("text/uri-list");
      if (!selection) {
        report_fail("drag_signal_delivers", "no selection data");
      } else {
        capture_reset(&state);
        g_signal_emit_by_name(g_window, "drag-data-received", NULL, 0, 0, selection, 0, 0);
        report_expect("drag_signal_delivers",
            state.calls == 1 && state.status == EXR_DROP_OK && state.first_status == EXR_DROP_ITEM_FILE
                && strcmp(state.first_path, expected_file) == 0,
            "drag-data-received reached the installed handler");
      }
      if (selection) gtk_selection_data_free(selection);
    }
  }
  {
    /* request outlives the selection data and the clipboard owner */
    GtkSelectionData *selection;
    exr_drop_request *held = NULL;
    if (!clipboard_own(uri_unicode, NULL, NULL) || !(selection = clipboard_contents("text/uri-list"))) {
      report_fail("request_outlives_selection_data", "clipboard ownership failed");
    } else {
      exr_drop_gtk_request_from_selection(selection, EXR_DROP_ORIGIN_CLIPBOARD, NULL, &held);
      gtk_selection_data_free(selection);
      gtk_clipboard_clear(gtk_clipboard_get(GDK_SELECTION_CLIPBOARD));
      if (held) {
        exr_drop_item item;
        memset(&item, 0, sizeof(item));
        item.struct_size = sizeof(item);
        exr_drop_request_get_item(held, 0, &item);
        report_expect("request_outlives_selection_data",
            item.status == EXR_DROP_ITEM_FILE && item.path && strcmp(item.path, expected_unicode) == 0,
            "path bytes survive the selection data and the clipboard");
        exr_drop_request_release(held);
      } else {
        report_fail("request_outlives_selection_data", "no request");
      }
    }
  }
  {
    /* gnome-copied-files flavour on the clipboard route */
    if (!clipboard_own(NULL, "copy\nfile:///exr/missing.epub\n", NULL)) {
      report_fail("clipboard_gnome_copy", "clipboard ownership failed");
    } else {
      exr_drop_status status = exr_drop_gtk_clipboard_request(gtk_clipboard_get(GDK_SELECTION_CLIPBOARD),
          EXR_DROP_ORIGIN_CLIPBOARD, NULL, &request);
      exr_drop_item item;
      memset(&item, 0, sizeof(item));
      item.struct_size = sizeof(item);
      if (status == EXR_DROP_OK) exr_drop_request_get_item(request, 0, &item);
      report_expect("clipboard_gnome_copy",
          status == EXR_DROP_OK && item.status == EXR_DROP_ITEM_MISSING
              && item.path && strcmp(item.path, "/exr/missing.epub") == 0,
          "copy preamble ignored");
      exr_drop_request_release(request);
      request = NULL;
    }
  }

  /* ---- lifecycle ----------------------------------------------------- */
  {
    GThread *thread = g_thread_new("detach", detach_thread, target);
    int status = GPOINTER_TO_INT(g_thread_join(thread));
    report_expect("detach_from_other_thread", status == (int)EXR_DROP_WRONG_THREAD,
        "wrong thread refused, target unchanged");
  }
  {
    GtkWidget *callback_window = gtk_window_new(GTK_WINDOW_TOPLEVEL);
    exr_drop_gtk_target *victim = NULL;
    capture inner;
    memset(&inner, 0, sizeof(inner));
    inner.destroy_in_callback = 1;
    options.context = &inner;
    if (callback_window && exr_drop_gtk_attach(callback_window, &options, &victim) == EXR_DROP_OK) {
      GtkSelectionData *selection;
      inner.target = victim;
      if (!clipboard_own(uri_file, NULL, NULL) || !(selection = clipboard_contents("text/uri-list"))) {
        report_fail("detach_inside_callback", "selection unavailable");
      } else {
        g_signal_emit_by_name(callback_window, "drag-data-received", NULL, 0, 0, selection, 0, 0);
        gtk_selection_data_free(selection);
        report_expect("detach_inside_callback",
            inner.calls == 1 && inner.destroy_status == EXR_DROP_OK && inner.target == NULL,
            "target destroyed from its own callback");
      }
    } else {
      report_fail("detach_inside_callback", "attach failed");
    }
    if (callback_window) gtk_widget_destroy(callback_window);
    options.context = &state;
  }
  {
    GtkWidget *spare = gtk_window_new(GTK_WINDOW_TOPLEVEL);
    exr_drop_gtk_target *victim = NULL;
    if (exr_drop_gtk_attach(spare, &options, &victim) == EXR_DROP_OK) {
      gtk_widget_destroy(spare);
      report_expect("widget_destroyed_before_detach", exr_drop_gtk_detach(victim) == EXR_DROP_OK,
          "detach after the widget died only frees memory");
    } else {
      report_fail("widget_destroyed_before_detach", "attach failed");
    }
  }
  report_expect("detach_owner_thread", exr_drop_gtk_detach(target) == EXR_DROP_OK, "final detach");
  gtk_widget_destroy(g_window);
  return report_summary("gtk");
}
