/* SPDX-License-Identifier: MIT
 * Isolated GTK dispatch control, excluded from all timed product cohorts.
 * Two explicit renders compare pixels; no redraw loop or product stimulus.
 */
#include <gtk/gtk.h>
#include <string.h>
static GtkWidget *target;
static unsigned emissions,callbacks;
static gboolean painted;
static gboolean hook(GSignalInvocationHint *hint,guint n,const GValue *v,gpointer data){
 (void)hint;(void)data;
 if(n && g_value_get_object(v)==G_OBJECT(target))emissions++;
 return TRUE;
}
static gboolean passive(GtkWidget *widget,cairo_t *cr,gpointer data){
 (void)widget;(void)cr;(void)data;callbacks++;return FALSE;
}
static void after_paint(GdkFrameClock *clock,gpointer data){
 (void)clock;(void)data;painted=TRUE;
}
static cairo_surface_t *render(void){
 int width=gtk_widget_get_allocated_width(target),height=gtk_widget_get_allocated_height(target);
 g_assert_cmpint(width,>,0);g_assert_cmpint(height,>,0);
 cairo_surface_t *s=cairo_image_surface_create(CAIRO_FORMAT_ARGB32,width,height);
 cairo_t *cr=cairo_create(s);gtk_widget_draw(target,cr);cairo_destroy(cr);
 cairo_surface_flush(s);g_assert_cmpint(cairo_surface_status(s),==,CAIRO_STATUS_SUCCESS);
 return s;
}
int main(int argc,char **argv){
 gtk_init(&argc,&argv);
 g_object_set(gtk_settings_get_default(),"gtk-enable-animations",FALSE,NULL);
 GtkWidget *window=gtk_window_new(GTK_WINDOW_TOPLEVEL);
 gtk_window_set_default_size(GTK_WINDOW(window),320,180);
 target=gtk_list_box_new();gtk_container_add(GTK_CONTAINER(window),target);
 gtk_container_add(GTK_CONTAINER(target),gtk_label_new("F08 synthetic bookshelf row"));
 guint signal=g_signal_lookup("draw",GTK_TYPE_WIDGET);
 gulong emission=g_signal_add_emission_hook(signal,0,hook,NULL,NULL);
 g_assert_cmpuint(emission,>,0);
 gtk_widget_show_all(window);
 GdkFrameClock *clock=gtk_widget_get_frame_clock(window);g_assert_nonnull(clock);
 gulong frame_handler=g_signal_connect_after(clock,"after-paint",G_CALLBACK(after_paint),NULL);
 while(!painted)g_main_context_iteration(NULL,TRUE);
 g_signal_handler_disconnect(clock,frame_handler);
 emissions=0;
 g_assert_false(g_signal_has_handler_pending(target,signal,0,FALSE));
 cairo_surface_t *unhandled=render();
 unsigned hook_only=emissions;g_assert_cmpuint(hook_only,==,0);
 gulong handler=g_signal_connect(target,"draw",G_CALLBACK(passive),NULL);
 g_assert_true(g_signal_has_handler_pending(target,signal,0,FALSE));
 emissions=callbacks=0;
 cairo_surface_t *observed=render();
 g_assert_cmpuint(emissions,==,1);g_assert_cmpuint(callbacks,==,1);
 gsize bytes=(gsize)cairo_image_surface_get_stride(unhandled)*cairo_image_surface_get_height(unhandled);
 const guchar *a=cairo_image_surface_get_data(unhandled),*b=cairo_image_surface_get_data(observed);
 g_assert_cmpint(memcmp(a,b,bytes),==,0);
 gboolean nonzero=FALSE;for(gsize i=0;i<bytes;i++)if(a[i]){nonzero=TRUE;break;}
 g_assert_true(nonzero);
 gchar *digest=g_compute_checksum_for_data(G_CHECKSUM_SHA256,a,bytes);
 g_print("{\"passed\":true,\"hook_only\":%u,\"with_handler\":%u,\"callbacks\":%u,"
         "\"pixels_equal\":true,\"nonempty\":true,\"pixel_sha256\":\"%s\","
         "\"gtk\":\"%u.%u.%u\"}\n",hook_only,emissions,callbacks,digest,
         gtk_get_major_version(),gtk_get_minor_version(),gtk_get_micro_version());
 g_free(digest);g_signal_handler_disconnect(target,handler);
 g_signal_remove_emission_hook(signal,emission);
 cairo_surface_destroy(unhandled);cairo_surface_destroy(observed);gtk_widget_destroy(window);
 return 0;
}
