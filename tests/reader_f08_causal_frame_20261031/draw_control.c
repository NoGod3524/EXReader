/* SPDX-License-Identifier: MIT
 * Isolated GTK dispatch control, excluded from all timed product cohorts.
 * Two explicit renders compare pixels; no redraw loop or product stimulus.
 */
#include <gtk/gtk.h>
#include <string.h>
#include "shelf_content.h"
static GtkWidget *target;
static unsigned emissions,callbacks;
static gboolean painted;
static F08ShelfContent observed_content;
static gboolean hook(GSignalInvocationHint *hint,guint n,const GValue *v,gpointer data){
 (void)hint;(void)data;
 if(n && g_value_get_object(v)==G_OBJECT(target))emissions++;
 return TRUE;
}
static gboolean passive(GtkWidget *widget,cairo_t *cr,gpointer data){
 (void)data;callbacks++;observed_content=f08_shelf_content(widget,cr);return FALSE;
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
 GtkWidget *scroll=gtk_scrolled_window_new(NULL,NULL);gtk_container_add(GTK_CONTAINER(window),scroll);
 target=gtk_list_box_new();gtk_container_add(GTK_CONTAINER(scroll),target);
 for(int i=0;i<12;i++){
  GtkWidget *row=gtk_list_box_row_new(),*label=gtk_label_new("F08 isolated content row");
  int64_t *id=g_new(int64_t,1);*id=101+i;g_object_set_data_full(G_OBJECT(row),"book-id",id,g_free);
  gtk_widget_set_size_request(row,-1,48);
  gtk_container_add(GTK_CONTAINER(row),label);gtk_container_add(GTK_CONTAINER(target),row);
 }
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
 g_assert_true(observed_content.available);g_assert_true(observed_content.clip_intersects);
 g_assert_true(observed_content.list_drawable);g_assert_true(observed_content.row_drawable);
 g_assert_cmpint(observed_content.top_id,==,101);g_assert_cmpint(observed_content.index,==,0);
 gsize bytes=(gsize)cairo_image_surface_get_stride(unhandled)*cairo_image_surface_get_height(unhandled);
 const guchar *a=cairo_image_surface_get_data(unhandled),*b=cairo_image_surface_get_data(observed);
 g_assert_cmpint(memcmp(a,b,bytes),==,0);
 gboolean nonzero=FALSE;for(gsize i=0;i<bytes;i++)if(a[i]){nonzero=TRUE;break;}
 g_assert_true(nonzero);
 gchar *digest=g_compute_checksum_for_data(G_CHECKSUM_SHA256,a,bytes);
 unsigned observed_emissions=emissions,observed_callbacks=callbacks;
 GtkListBoxRow *later=gtk_list_box_get_row_at_index(GTK_LIST_BOX(target),5);
 GtkAllocation allocation;gtk_widget_get_allocation(GTK_WIDGET(later),&allocation);
 GtkAdjustment *adjustment=gtk_scrolled_window_get_vadjustment(GTK_SCROLLED_WINDOW(scroll));
 gtk_adjustment_set_value(adjustment,allocation.y+1);
 cairo_surface_t *shifted=render();
 g_assert_true(observed_content.available);g_assert_true(observed_content.clip_intersects);
 g_assert_cmpint(observed_content.top_id,==,106);g_assert_cmpint(observed_content.index,==,5);
 g_assert_cmpfloat(observed_content.scroll,>=,observed_content.y);
 g_assert_cmpfloat(observed_content.scroll,<,observed_content.y+observed_content.height);
 cairo_surface_destroy(shifted);
 cairo_surface_t *tiny=cairo_image_surface_create(CAIRO_FORMAT_ARGB32,1,1);
 cairo_t *outside=cairo_create(tiny);
 F08ShelfContent clipped=f08_shelf_content(target,outside);
 g_assert_true(clipped.available);g_assert_false(clipped.clip_intersects);
 g_object_set_data(G_OBJECT(later),"book-id",NULL);
 F08ShelfContent missing=f08_shelf_content(target,outside);g_assert_false(missing.available);
 cairo_destroy(outside);cairo_surface_destroy(tiny);
 g_print("{\"passed\":true,\"hook_only\":%u,\"with_handler\":%u,\"callbacks\":%u,"
         "\"pixels_equal\":true,\"nonempty\":true,\"pixel_sha256\":\"%s\","
         "\"gtk\":\"%u.%u.%u\",\"shelf_content_control\":true,\"initial_top_id\":101,\"scrolled_top_id\":106,\"clip_rejected\":true,\"missing_id_rejected\":true}\n",hook_only,observed_emissions,observed_callbacks,digest,
         gtk_get_major_version(),gtk_get_minor_version(),gtk_get_micro_version());
 g_free(digest);g_signal_handler_disconnect(target,handler);
 g_signal_remove_emission_hook(signal,emission);
 cairo_surface_destroy(unhandled);cairo_surface_destroy(observed);gtk_widget_destroy(window);
 return 0;
}
