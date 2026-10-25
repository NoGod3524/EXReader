/* SPDX-License-Identifier: MIT */
#include <gtk/gtk.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static gchar *payload;static gsize payload_size;static guint delay_ms;
static const char *target_name;
static void selection(GtkSelectionData *data) {
  printf("NATIVE_FILE_REQUEST_BEGIN target=%s\n",target_name);fflush(stdout);
  if(delay_ms) g_usleep((gulong)delay_ms*1000);
  gtk_selection_data_set(data,gdk_atom_intern(target_name,FALSE),8,(const guchar *)payload,(gint)payload_size);
  printf("NATIVE_FILE_SELECTION target=%s bytes=%zu\n",target_name,(size_t)payload_size);fflush(stdout);
}
static void clipboard_get(GtkClipboard *clipboard,GtkSelectionData *data,guint info,gpointer unused) {
  (void)clipboard;(void)info;(void)unused;selection(data);
}
static void clipboard_clear(GtkClipboard *clipboard,gpointer unused) { (void)clipboard;(void)unused; }
static void drag_get(GtkWidget *widget,GdkDragContext *context,GtkSelectionData *data,guint info,guint time,gpointer unused) {
  (void)widget;(void)context;(void)info;(void)time;(void)unused;selection(data);
}
int main(int argc,char **argv) {
  if(argc!=5 && argc!=6) return 2;
  if(!getenv("GITHUB_ACTIONS") || strcmp(getenv("GITHUB_ACTIONS"),"true")) return 3;
  gtk_init(NULL,NULL);target_name=argv[2];delay_ms=argc==6 ? (guint)strtoul(argv[5],NULL,10):0;
  if(!g_file_get_contents(argv[3],&payload,&payload_size,NULL) || payload_size>2u*1024u*1024u) return 4;
  GtkTargetEntry target={(gchar *)target_name,0,0};
  if(!strcmp(argv[1],"clipboard")) {
    if(!gtk_clipboard_set_with_data(gtk_clipboard_get(GDK_SELECTION_CLIPBOARD),&target,1,clipboard_get,clipboard_clear,NULL)) return 5;
  } else {
    GtkWidget *window=gtk_window_new(GTK_WINDOW_TOPLEVEL),*button=gtk_button_new_with_label("Drag real book files");
    gtk_window_set_title(GTK_WINDOW(window),argv[4]);gtk_window_set_default_size(GTK_WINDOW(window),240,90);
    gtk_container_add(GTK_CONTAINER(window),button);gtk_drag_source_set(button,GDK_BUTTON1_MASK,&target,1,GDK_ACTION_COPY);
    g_signal_connect(button,"drag-data-get",G_CALLBACK(drag_get),NULL);gtk_widget_show_all(window);
  }
  puts("NATIVE_FILE_SOURCE_READY");fflush(stdout);gtk_main();g_free(payload);return 0;
}
