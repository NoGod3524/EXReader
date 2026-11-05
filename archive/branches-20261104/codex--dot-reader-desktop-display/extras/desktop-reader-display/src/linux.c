/* SPDX-License-Identifier: MIT */
#include <gtk/gtk.h>
#include <gdk/gdkx.h>
#include <string.h>
#include "common.h"
#define SERVICE "org.gnome.SessionManager"
#define OBJECT "/org/gnome/SessionManager"
#define IDLE_ONLY 8u
struct exr_display_lease {
  GThread *thread;
  GtkWidget *window;
  GDBusConnection *bus;
  gchar *service_owner;
  gchar reason[257];
  guint timer, watch, cookie;
  guint32 duration, error;
  guint64 generation, deadline;
  int refs, wanted, pending, closed, destroyed, busy, was_eligible;
  exr_display_status state;
};
typedef struct { exr_display_lease *lease; guint64 generation; gchar *owner; } Request;
static gint live_count;
static guint64 now_ms(void) { return (guint64)(g_get_monotonic_time()/1000); }
static void refresh(exr_display_lease *);
static void unref_lease(exr_display_lease *l) {
  if(--l->refs) return;
  g_free(l->service_owner); g_free(l); g_atomic_int_add(&live_count,-1);
}
static exr_display_status enter(exr_display_lease *l) {
  if(!l) return EXR_DISPLAY_ARGUMENT;
  if(l->thread!=g_thread_self()) return EXR_DISPLAY_WRONG_THREAD;
  if(l->busy) return EXR_DISPLAY_REENTRANT;
  l->busy=1; return EXR_DISPLAY_OK;
}
static void disconnect_bus(exr_display_lease *l) {
  if(!l->bus) return;
  if(l->watch) { g_dbus_connection_signal_unsubscribe(l->bus,l->watch); l->watch=0; }
  g_signal_handlers_disconnect_by_data(l->bus,l);
  if(!g_dbus_connection_is_closed(l->bus)) g_dbus_connection_close_sync(l->bus,NULL,NULL);
  g_clear_object(&l->bus); g_clear_pointer(&l->service_owner,g_free); l->cookie=0;
}
static int release_cookie(GDBusConnection *bus,const char *owner,guint cookie) {
  GError *error=NULL;
  GVariant *r;
  if(!cookie || !bus || !owner || g_dbus_connection_is_closed(bus)) return 1;
  r=g_dbus_connection_call_sync(bus,owner,OBJECT,SERVICE,"Uninhibit",g_variant_new("(u)",cookie),
      G_VARIANT_TYPE("()"),G_DBUS_CALL_FLAGS_NO_AUTO_START,1000,NULL,&error);
  if(r) g_variant_unref(r);
  if(error) g_error_free(error);
  return r!=NULL;
}
static void revoke_lease(exr_display_lease *l,exr_display_status s) {
  guint cookie=l->cookie; l->cookie=0; ++l->generation;
  if(!release_cookie(l->bus,l->service_owner,cookie)) { disconnect_bus(l); s=EXR_DISPLAY_UNAVAILABLE; }
  l->state=s;
}
static int eligible(exr_display_lease *l) {
  GdkWindow *w;
  if(l->destroyed || !l->window || !gtk_widget_get_visible(l->window) || !gtk_widget_get_mapped(l->window) || !gtk_window_is_active(GTK_WINDOW(l->window))) return 0;
  w=gtk_widget_get_window(l->window);
  return w && !(gdk_window_get_state(w)&GDK_WINDOW_STATE_ICONIFIED);
}
static void bus_closed(GDBusConnection *bus,gboolean remote,GError *error,gpointer data) {
  exr_display_lease *l=data; (void)bus; (void)remote;
  l->cookie=0; l->error=error?(guint32)error->code:0; ++l->generation;
  if(!l->closed) l->state=EXR_DISPLAY_UNAVAILABLE;
}
static void owner_changed(GDBusConnection *bus,const gchar *sender,const gchar *path,const gchar *iface,const gchar *signal,GVariant *args,gpointer data) {
  exr_display_lease *l=data; const gchar *name,*old,*next;
  (void)bus; (void)sender; (void)path; (void)iface; (void)signal;
  g_variant_get(args,"(&s&s&s)",&name,&old,&next);
  if(l->service_owner && !strcmp(old,l->service_owner) && strcmp(old,next)) {
    l->cookie=0; ++l->generation; l->state=EXR_DISPLAY_UNAVAILABLE;
  }
}
static int connect_bus(exr_display_lease *l) {
  GError *e=NULL; gchar *address; GVariant *r;
  if(l->bus && !g_dbus_connection_is_closed(l->bus) && l->service_owner) return 1;
  disconnect_bus(l);
  address=g_dbus_address_get_for_bus_sync(G_BUS_TYPE_SESSION,NULL,&e);
  if(address && g_str_has_prefix(address,"unix:"))
    l->bus=g_dbus_connection_new_for_address_sync(address,G_DBUS_CONNECTION_FLAGS_AUTHENTICATION_CLIENT|G_DBUS_CONNECTION_FLAGS_MESSAGE_BUS_CONNECTION,NULL,NULL,&e);
  g_free(address);
  if(!l->bus) goto fail;
  g_dbus_connection_set_exit_on_close(l->bus,FALSE);
  g_signal_connect(l->bus,"closed",G_CALLBACK(bus_closed),l);
  l->watch=g_dbus_connection_signal_subscribe(l->bus,"org.freedesktop.DBus","org.freedesktop.DBus","NameOwnerChanged","/org/freedesktop/DBus",SERVICE,G_DBUS_SIGNAL_FLAGS_NONE,owner_changed,l,NULL);
  r=g_dbus_connection_call_sync(l->bus,"org.freedesktop.DBus","/org/freedesktop/DBus","org.freedesktop.DBus","GetNameOwner",g_variant_new("(s)",SERVICE),G_VARIANT_TYPE("(s)"),G_DBUS_CALL_FLAGS_NO_AUTO_START,1000,NULL,&e);
  if(!r) goto fail;
  g_variant_get(r,"(s)",&l->service_owner); g_variant_unref(r); return 1;
fail:
  l->error=e?(guint32)e->code:0; g_clear_error(&e); disconnect_bus(l); l->state=EXR_DISPLAY_UNAVAILABLE; return 0;
}
static void replied(GObject *source,GAsyncResult *result,gpointer data) {
  Request *q=data; exr_display_lease *l=q->lease; GError *e=NULL; guint cookie=0;
  GVariant *r=g_dbus_connection_call_finish(G_DBUS_CONNECTION(source),result,&e);
  l->pending=0;
  if(r) { g_variant_get(r,"(u)",&cookie); g_variant_unref(r); }
  if(!r || !cookie) {
    l->error=e?(guint32)e->code:0;
    /* Timeout may hide a cookie allocated by the service. Disconnect the
       dedicated sender, rather than cancelling and silently losing it. */
    disconnect_bus(l);
    if(!l->closed && q->generation==l->generation) l->state=EXR_DISPLAY_UNAVAILABLE;
  } else if(l->closed || q->generation!=l->generation || !l->wanted || !eligible(l) || now_ms()>=l->deadline) {
    if(!release_cookie(G_DBUS_CONNECTION(source),q->owner,cookie)) disconnect_bus(l);
  } else { l->cookie=cookie; l->state=EXR_DISPLAY_OK; l->error=0; }
  g_clear_error(&e); g_free(q->owner); g_free(q);
  if(!l->closed) refresh(l);
  unref_lease(l);
}
static void refresh(exr_display_lease *l) {
  int ok; Request *q; guint32 xid=0; GdkWindow *w;
  if(l->closed || l->destroyed) return;
  if(l->wanted && now_ms()>=l->deadline) { l->wanted=0; revoke_lease(l,EXR_DISPLAY_EXPIRED); }
  ok=l->wanted && eligible(l);
  if(!ok) {
    if(l->was_eligible) revoke_lease(l,l->wanted && l->state!=EXR_DISPLAY_UNAVAILABLE?EXR_DISPLAY_INACTIVE:l->state);
    l->was_eligible=0; return;
  }
  l->was_eligible=1;
  if(l->pending || l->cookie || l->state==EXR_DISPLAY_UNAVAILABLE) return;
  if(!connect_bus(l)) return;
  q=g_try_new0(Request,1); if(!q) { l->state=EXR_DISPLAY_NO_MEMORY; return; }
  q->lease=l; q->generation=l->generation; q->owner=g_strdup(l->service_owner); ++l->refs;
  w=gtk_widget_get_window(l->window);
  if(GDK_IS_X11_WINDOW(w)) xid=(guint32)gdk_x11_window_get_xid(w);
  l->pending=1; l->state=EXR_DISPLAY_PENDING;
  g_dbus_connection_call(l->bus,q->owner,OBJECT,SERVICE,"Inhibit",
      g_variant_new("(susu)","org.exreader.DesktopDisplay",xid,l->reason,IDLE_ONLY),
      G_VARIANT_TYPE("(u)"),G_DBUS_CALL_FLAGS_NO_AUTO_START,2000,NULL,replied,q);
}
static gboolean tick(gpointer p) { refresh(p); return G_SOURCE_CONTINUE; }
static void visibility(GtkWidget *w,gpointer p) { (void)w; refresh(p); }
static void active_notify(GObject *w,GParamSpec *s,gpointer p) { (void)w; (void)s; refresh(p); }
static gboolean state_event(GtkWidget *w,GdkEventWindowState *e,gpointer p) {
  exr_display_lease *l=p; (void)w;
  if(e->new_window_state&GDK_WINDOW_STATE_ICONIFIED) { revoke_lease(l,l->wanted && l->state!=EXR_DISPLAY_UNAVAILABLE?EXR_DISPLAY_INACTIVE:l->state); l->was_eligible=0; }
  else refresh(l);
  return FALSE;
}
static void destroyed(GtkWidget *w,gpointer p) {
  exr_display_lease *l=p; (void)w; l->destroyed=1; l->wanted=0; revoke_lease(l,EXR_DISPLAY_WINDOW_GONE);
}
exr_display_status exr_display_create(const exr_display_options *o,exr_display_lease **out) {
  exr_display_lease *l;
  if(!out) return EXR_DISPLAY_ARGUMENT;
  *out=NULL;
  if(!exr_display_valid_options(o) || !GTK_IS_WINDOW(o->native_window) || gtk_widget_in_destruction(GTK_WIDGET(o->native_window))) return EXR_DISPLAY_ARGUMENT;
  if(g_main_context_get_thread_default()!=NULL && g_main_context_get_thread_default()!=g_main_context_default()) return EXR_DISPLAY_ARGUMENT;
  if(g_atomic_int_add(&live_count,1)>=(gint)EXR_DISPLAY_MAX_LEASES) { g_atomic_int_add(&live_count,-1); return EXR_DISPLAY_LIMIT; }
  l=g_try_new0(exr_display_lease,1); if(!l) { g_atomic_int_add(&live_count,-1); return EXR_DISPLAY_NO_MEMORY; }
  l->refs=1; l->thread=g_thread_self(); l->window=g_object_ref(o->native_window); l->duration=o->lease_ms;
  l->generation=1; l->state=EXR_DISPLAY_INACTIVE; memcpy(l->reason,o->reason,strlen(o->reason)+1);
  g_signal_connect(l->window,"destroy",G_CALLBACK(destroyed),l);
  g_signal_connect(l->window,"hide",G_CALLBACK(visibility),l);
  g_signal_connect(l->window,"notify::is-active",G_CALLBACK(active_notify),l);
  g_signal_connect(l->window,"window-state-event",G_CALLBACK(state_event),l);
  l->timer=g_timeout_add(50,tick,l); *out=l; return EXR_DISPLAY_OK;
}
exr_display_status exr_display_set_active(exr_display_lease *l,int active) {
  exr_display_status s;
  if(active!=0 && active!=1) return EXR_DISPLAY_ARGUMENT;
  s=enter(l); if(s) return s;
  if(l->destroyed) { l->busy=0; return EXR_DISPLAY_WINDOW_GONE; }
  if(l->state==EXR_DISPLAY_UNAVAILABLE) disconnect_bus(l);
  l->wanted=active; l->deadline=active?now_ms()+l->duration:0;
  if(!active) revoke_lease(l,EXR_DISPLAY_INACTIVE);
  else { if(!l->cookie) l->state=EXR_DISPLAY_INACTIVE; refresh(l); }
  s=l->state; l->busy=0; return s;
}
exr_display_status exr_display_cancel(exr_display_lease *l) {
  exr_display_status s=enter(l); if(s) return s;
  l->wanted=0; l->deadline=0; revoke_lease(l,EXR_DISPLAY_CANCELLED); l->busy=0; return EXR_DISPLAY_OK;
}
exr_display_status exr_display_observe(exr_display_lease *l,exr_display_observation *o) {
  exr_display_status s;
  if(!o || o->struct_size!=sizeof(*o)) return EXR_DISPLAY_ARGUMENT;
  s=enter(l); if(s) return s; refresh(l);
  o->state=l->state; o->generation=l->generation; o->native_identity=l->cookie; o->expires_at_ms=l->deadline;
  o->native_error=l->error; o->requested=l->wanted; o->pending=l->pending; o->window_alive=!l->destroyed;
  l->busy=0; return EXR_DISPLAY_OK;
}
exr_display_status exr_display_close(exr_display_lease *l) {
  exr_display_status s; if(!l) return EXR_DISPLAY_OK; s=enter(l); if(s) return s;
  l->closed=1; l->wanted=0; revoke_lease(l,EXR_DISPLAY_CANCELLED);
  g_source_remove(l->timer); g_signal_handlers_disconnect_by_data(l->window,l); g_object_unref(l->window); l->window=NULL;
  disconnect_bus(l); l->busy=0; unref_lease(l); return EXR_DISPLAY_OK;
}
