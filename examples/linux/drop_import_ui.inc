/* SPDX-License-Identifier: MIT */
#include <exr_desktop_drop.h>
static struct {
  GtkWidget *zone;
  guint token,timeout;
  int pending,inflight,closed;
  unsigned accepted,rejected;
  size_t bytes;
  char sha256[65];
} file_input;
typedef struct { guint token;int kind; } file_clipboard_request;
static void file_input_cancel(void) {
  file_input.token++;file_input.pending=0;
  if(file_input.timeout) { g_source_remove(file_input.timeout);file_input.timeout=0; }
  if(!file_input.closed) { status(EXR_CANCELLED,"File paste cancelled");state(); }
}
static int file_input_ready(void) {
  return !file_input.closed && !closing && profile_writable && !folder.dialog &&
    !folder.has_owner && !folder_paused();
}
static int file_input_receive(GtkSelectionData *selection,int kind,int origin) {
  gint bytes=selection ? gtk_selection_data_get_length(selection):-1;
  const guchar *data=selection ? gtk_selection_data_get_data(selection):NULL;
  if(!file_input_ready() || bytes<=0 || !data || gtk_selection_data_get_format(selection)!=8 ||
     (size_t)bytes>EXR_DROP_MAX_INPUT_BYTES) {
    file_input.rejected++;status(EXR_ARGUMENT,"No usable file list, input too large, or an import is already active");state();return 0;
  }
  char *copy=g_try_malloc((size_t)bytes);
  if(!copy) { file_input.rejected++;status(EXR_MEMORY,"File input could not be copied");return 0; }
  memcpy(copy,data,(size_t)bytes);
  host_job *job=g_new0(host_job,1);job->command.batch_payload=copy;job->command.batch_payload_bytes=(size_t)bytes;
  job->command.batch_input=kind;job->command.batch_origin=origin;
  char *sha=g_compute_checksum_for_data(G_CHECKSUM_SHA256,data,(gsize)bytes);
  g_strlcpy(file_input.sha256,sha,sizeof(file_input.sha256));g_free(sha);file_input.bytes=(size_t)bytes;
  file_input.accepted++;folder_start(NULL,0,job);return 1;
}
static void file_input_drop(GtkWidget *widget,GdkDragContext *context,gint x,gint y,
  GtkSelectionData *selection,guint info,guint time,gpointer unused) {
  (void)widget;(void)x;(void)y;(void)unused;
  int accepted=!file_input.pending && !file_input.closed &&
    file_input_receive(selection,info ? 2:1,EXR_DROP_ORIGIN_DROP);
  gtk_drag_finish(context,accepted,FALSE,time);
}
static gboolean file_input_timeout(gpointer token) {
  if(GPOINTER_TO_UINT(token)==file_input.token && file_input.pending) {
    file_input.timeout=0;file_input_cancel();
  }
  return G_SOURCE_REMOVE;
}
static void file_clipboard_received(GtkClipboard *clipboard,GtkSelectionData *selection,gpointer context) {
  file_clipboard_request *request=context;
  if(file_input.closed || closing || request->token!=file_input.token || !file_input.pending) {
    file_input.inflight=0;if(!file_input.closed && !closing) state();g_free(request);return;
  }
  if((!selection || gtk_selection_data_get_length(selection)<0) && request->kind==1) {
    request->kind=2;
    gtk_clipboard_request_contents(clipboard,gdk_atom_intern_static_string("x-special/gnome-copied-files"),file_clipboard_received,request);return;
  }
  file_input.pending=file_input.inflight=0;
  if(file_input.timeout) { g_source_remove(file_input.timeout);file_input.timeout=0; }
  file_input_receive(selection,request->kind,EXR_DROP_ORIGIN_CLIPBOARD);g_free(request);
}
static void file_input_paste(GtkWidget *widget,gpointer unused) {
  (void)widget;(void)unused;
  if(file_input.inflight || !file_input_ready()) { status(EXR_ARGUMENT,"Finish the current file request or reading operation first");return; }
  file_clipboard_request *request=g_new0(file_clipboard_request,1);
  request->token=++file_input.token;request->kind=1;file_input.pending=file_input.inflight=1;
  file_input.timeout=g_timeout_add_seconds(15,file_input_timeout,GUINT_TO_POINTER(request->token));
  status(EXR_OK,"Reading file clipboard… Escape cancels");state();
  gtk_clipboard_request_contents(gtk_clipboard_get(GDK_SELECTION_CLIPBOARD),gdk_atom_intern_static_string("text/uri-list"),file_clipboard_received,request);
}
static void file_input_attach(GtkWidget *zone) {
  static const GtkTargetEntry targets[]={{(gchar *)"text/uri-list",0,0},{(gchar *)"x-special/gnome-copied-files",0,1}};
  file_input.zone=zone;
  gtk_drag_dest_set(zone,GTK_DEST_DEFAULT_MOTION|GTK_DEST_DEFAULT_DROP,targets,G_N_ELEMENTS(targets),GDK_ACTION_COPY);
  g_signal_connect(zone,"drag-data-received",G_CALLBACK(file_input_drop),NULL);
}
static void file_input_shutdown(void) {
  file_input.closed=1;file_input_cancel();
  if(file_input.zone) gtk_drag_dest_unset(file_input.zone);
  file_input.zone=NULL;
}
static char *file_input_observation(void) {
  return g_strdup_printf("[file_input]\npending=%d\ninflight=%d\nclosed=%d\naccepted=%u\nrejected=%u\npayload_bytes=%zu\npayload_sha256=%s\nsource_items=%zu\nsource_duplicates=%zu\nsource_overflow=%zu\n",
    file_input.pending,file_input.inflight,file_input.closed,file_input.accepted,file_input.rejected,file_input.bytes,file_input.sha256,
    folder.source_items,folder.source_duplicates,folder.source_overflow);
}
