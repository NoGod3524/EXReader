/* SPDX-License-Identifier: MIT */
#include <gtk/gtk.h>
#include "probe.h"
static GDBusConnection *control;
static void pump(unsigned ms) {
  gint64 end=g_get_monotonic_time()+(gint64)ms*1000;
  do { while(g_main_context_iteration(NULL,FALSE)) {} g_usleep(2000); } while(g_get_monotonic_time()<end);
}
static GVariant *ctl(const char *method,GVariant *args,const GVariantType *type) {
  GError *error=NULL; GVariant *r=g_dbus_connection_call_sync(control,"org.exreader.DisplayFixture","/org/gnome/SessionManager","org.exreader.DisplayFixture",method,args,type,G_DBUS_CALL_FLAGS_NO_AUTO_START,1000,NULL,&error);
  if(error) { fprintf(stderr,"fixture %s: %s\n",method,error->message); g_error_free(error); ++failures; } return r;
}
static void mode(const char *s) { GVariant *r=ctl("Mode",g_variant_new("(s)",s),G_VARIANT_TYPE("()")); if(r) g_variant_unref(r); }
static unsigned count(const char *method) { guint32 n=999; GVariant *r=ctl(method,NULL,G_VARIANT_TYPE("(u)")); if(r) { g_variant_get(r,"(u)",&n); g_variant_unref(r); } return n; }
static void command(const char *s) { GVariant *r=ctl(s,NULL,G_VARIANT_TYPE("()")); if(r) g_variant_unref(r); pump(100); }
static GtkWidget *window(void) { GtkWidget *w=gtk_window_new(GTK_WINDOW_TOPLEVEL); gtk_window_set_default_size(GTK_WINDOW(w),480,320); gtk_window_set_title(GTK_WINDOW(w),"D07 display lease"); return w; }
static void focus(GtkWidget *w) { gtk_widget_show_all(w); gtk_window_deiconify(GTK_WINDOW(w)); gtk_window_present(GTK_WINDOW(w)); pump(250); }
static gpointer wrong(gpointer p) {
  exr_display_lease *l=p; exr_display_observation o={0}; o.struct_size=sizeof(o);
  return GINT_TO_POINTER(exr_display_set_active(l,1)==EXR_DISPLAY_WRONG_THREAD && exr_display_cancel(l)==EXR_DISPLAY_WRONG_THREAD && exr_display_observe(l,&o)==EXR_DISPLAY_WRONG_THREAD && exr_display_close(l)==EXR_DISPLAY_WRONG_THREAD);
}
static int reentered;
static void host_hide(GtkWidget *w,gpointer data) { exr_display_lease *l=data; (void)w; reentered=(snapshot(l).native_identity==0 && exr_display_cancel(l)==EXR_DISPLAY_OK); }
int main(int argc,char **argv) {
  GtkWidget *w,*w2; exr_display_lease *l=NULL,*b=NULL; exr_display_options o; exr_display_observation a,z; GThread *thread; gulong host_handler;
  int real=argc>1 && !strcmp(argv[1],"--real"); int child=argc>1 && !strcmp(argv[1],"--child");
  if(!gtk_init_check(&argc,&argv)) { result("gtk_available",0); return 1; }
  w=window(); focus(w); o.struct_size=sizeof(o); o.native_window=w; o.reason="EXReader reading"; o.lease_ms=10000;
  if(real || child) {
    if(exr_display_create(&o,&l)!=EXR_DISPLAY_OK) return 3;
    exr_display_set_active(l,1); pump(2300); a=snapshot(l);
    if(child) { if(a.state!=EXR_DISPLAY_OK) return 4; printf("READY %llu\n",(unsigned long long)a.native_identity); fflush(stdout); for(;;) pump(10); }
    if(a.state==EXR_DISPLAY_OK) result("real_session_service",a.native_identity!=0);
    else if(a.state==EXR_DISPLAY_UNAVAILABLE) unavailable("real_session_service","Actual session service missing denied or disconnected; fixture capability not substituted");
    else result("real_session_service",0);
    exr_display_close(l); gtk_widget_destroy(w); pump(200);
    unavailable("wayland","Not exercised; Xvfb X11 only");
    unavailable("physical_screen_energy","Virtual display cannot establish physical screen or energy effects");
    return failures?1:0;
  }
  control=g_bus_get_sync(G_BUS_TYPE_SESSION,NULL,NULL);
  result("gtk_available",1); boundaries(w);
  result("create_native_window",exr_display_create(&o,&l)==EXR_DISPLAY_OK);
  if(!l) return 1;
  exr_display_set_active(l,1); pump(200); a=snapshot(l);
  result("fixture_cookie_identity",a.state==EXR_DISPLAY_OK && a.native_identity && count("Count")==1);
  result("idle_only_flag",count("Flags")==8);
  thread=g_thread_new("wrong-thread",wrong,l); result("wrong_thread_no_mutation",GPOINTER_TO_INT(g_thread_join(thread))==1 && snapshot(l).native_identity==a.native_identity);
  exr_display_create(&o,&b); exr_display_set_active(b,1); pump(200);
  result("second_lease",snapshot(b).state==EXR_DISPLAY_OK && snapshot(b).native_identity!=a.native_identity && count("Count")==2);
  exr_display_cancel(l); pump(80); result("cancel_own_cookie_only",count("Count")==1 && snapshot(b).native_identity);
  exr_display_close(b); pump(80); exr_display_set_active(l,1); pump(200); result("retry_after_cancel",snapshot(l).state==EXR_DISPLAY_OK && count("Count")==1);
  gtk_window_iconify(GTK_WINDOW(w)); pump(300); result("minimize_releases",!snapshot(l).native_identity && count("Count")==0);
  focus(w); pump(200); result("restore_reacquires",snapshot(l).state==EXR_DISPLAY_OK);
  gtk_widget_hide(w); pump(100); result("hidden_releases",!snapshot(l).native_identity && count("Count")==0);
  focus(w); w2=window(); focus(w2); result("window_switch_releases",!snapshot(l).native_identity);
  o.native_window=w2; exr_display_create(&o,&b); exr_display_set_active(b,1); pump(200); result("second_window_acquires",snapshot(b).state==EXR_DISPLAY_OK);
  /* Reader 1 is no longer the host's active reading scene. Its prior request
     must not legitimately reacquire when destroying reader 2 restores focus. */
  exr_display_set_active(l,0);
  gtk_widget_destroy(w2); pump(100); result("destroy_releases",snapshot(b).state==EXR_DISPLAY_WINDOW_GONE && count("Count")==0); exr_display_close(b);
  focus(w); result("inactive_reader_stays_released",!snapshot(l).native_identity && count("Count")==0);
  exr_display_set_active(l,1); pump(200); host_handler=g_signal_connect(w,"hide",G_CALLBACK(host_hide),l); gtk_widget_hide(w); pump(100);
  result("native_callback_reentry",reentered && snapshot(l).state==EXR_DISPLAY_CANCELLED); g_signal_handler_disconnect(w,host_handler);
  focus(w); mode("late"); exr_display_set_active(l,1); pump(100); a=snapshot(l); exr_display_cancel(l); pump(700); z=snapshot(l);
  result("late_cancel_cookie_released",a.pending && z.state==EXR_DISPLAY_CANCELLED && z.generation>a.generation && !z.native_identity && count("Count")==0);
  exr_display_set_active(l,1); pump(100); exr_display_cancel(l); exr_display_set_active(l,1); pump(1400);
  result("late_generation_retry",snapshot(l).state==EXR_DISPLAY_OK && count("Count")==1);
  exr_display_cancel(l); mode("denied"); exr_display_set_active(l,1); pump(200);
  result("denied_unavailable",snapshot(l).state==EXR_DISPLAY_UNAVAILABLE && !snapshot(l).native_identity);
  mode("zero"); exr_display_set_active(l,1); pump(200); result("zero_cookie_unavailable",snapshot(l).state==EXR_DISPLAY_UNAVAILABLE);
  mode("normal"); exr_display_set_active(l,1); pump(200); command("Drop");
  result("service_disconnect_unavailable",snapshot(l).state==EXR_DISPLAY_UNAVAILABLE && !snapshot(l).native_identity);
  exr_display_set_active(l,1); pump(100); result("missing_service_unavailable",snapshot(l).state==EXR_DISPLAY_UNAVAILABLE);
  command("Grab"); pump(100); result("reconnect_requires_retry",snapshot(l).state==EXR_DISPLAY_UNAVAILABLE);
  exr_display_set_active(l,1); pump(200); result("explicit_reconnect",snapshot(l).state==EXR_DISPLAY_OK && count("Count")==1);
  exr_display_cancel(l); mode("timeout"); exr_display_set_active(l,1); pump(2400);
  result("timeout_disconnect_cleans_cookie",snapshot(l).state==EXR_DISPLAY_UNAVAILABLE && count("Count")==0);
  mode("late"); exr_display_set_active(l,1); pump(100); gtk_widget_destroy(w); pump(700);
  result("late_destroy_cleans_cookie",snapshot(l).state==EXR_DISPLAY_WINDOW_GONE && count("Count")==0);
  exr_display_close(l); w=window(); focus(w); o.native_window=w; o.lease_ms=10000; exr_display_create(&o,&l); exr_display_set_active(l,1); pump(100); exr_display_close(l); pump(700);
  result("close_pending_sender_cleanup",count("Count")==0);
  mode("normal"); o.lease_ms=100; exr_display_create(&o,&l); exr_display_set_active(l,1); pump(250);
  result("bounded_expiry",snapshot(l).state==EXR_DISPLAY_EXPIRED && !snapshot(l).native_identity && count("Count")==0);
  exr_display_close(l); gtk_widget_destroy(w); g_object_unref(control); pump(200);
  return failures?1:0;
}
