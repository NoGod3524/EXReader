/* SPDX-License-Identifier: MIT
 * Synthetic compositor capability only. Never product performance evidence.
 */
#include <gtk/gtk.h>
#include <stdio.h>
static GPtrArray *frames;
static GtkWidget *label;
static guint presented;
static gboolean tick(GtkWidget *widget,GdkFrameClock *clock,gpointer data) {
 (void)widget;(void)data;
 GdkFrameTimings *timing=gdk_frame_clock_get_current_timings(clock);
 if(timing)g_ptr_array_add(frames,gdk_frame_timings_ref(timing));
 char text[64];g_snprintf(text,sizeof(text),"compositor capability frame %u",frames->len);
 gtk_label_set_text(GTK_LABEL(label),text);
 return frames->len<120;
}
static gboolean finish(gpointer data) {
 (void)data;
 printf("{\"synthetic_only\":true,\"frames\":[");
 for(guint i=0;i<frames->len;i++){
  GdkFrameTimings *t=g_ptr_array_index(frames,i);
  gint64 p=gdk_frame_timings_get_presentation_time(t);
  gboolean complete=gdk_frame_timings_get_complete(t);
  if(complete&&p>0)presented++;
  printf("%s{\"counter\":%"G_GINT64_FORMAT",\"complete\":%s,\"presentation_us\":%"G_GINT64_FORMAT",\"refresh_us\":%"G_GINT64_FORMAT"}",
   i?",":"",gdk_frame_timings_get_frame_counter(t),complete?"true":"false",p,gdk_frame_timings_get_refresh_interval(t));
 }
 printf("],\"presented\":%u,\"total\":%u,\"physical_display_proven\":false}\n",presented,frames->len);
 gtk_main_quit();return G_SOURCE_REMOVE;
}
int main(int argc,char **argv) {
 gtk_init(&argc,&argv);frames=g_ptr_array_new_with_free_func((GDestroyNotify)gdk_frame_timings_unref);
 GtkWidget *window=gtk_window_new(GTK_WINDOW_TOPLEVEL);gtk_window_set_default_size(GTK_WINDOW(window),400,200);
 label=gtk_label_new("compositor capability");gtk_container_add(GTK_CONTAINER(window),label);
 gtk_widget_add_tick_callback(window,tick,NULL,NULL);gtk_widget_show_all(window);
 g_timeout_add(4000,finish,NULL);gtk_main();
 gboolean ok=frames->len>=60&&presented>=frames->len-2;
 g_ptr_array_unref(frames);gtk_widget_destroy(window);return ok?0:1;
}
