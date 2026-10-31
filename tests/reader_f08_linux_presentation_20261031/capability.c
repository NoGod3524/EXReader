/* SPDX-License-Identifier: MIT
 * Synthetic protocol capability only. No product performance claim.
 */
#include <gtk/gtk.h>
#include <gdk/gdkwayland.h>
#include <wayland-client.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <time.h>
#include <unistd.h>
#include "presentation-time-client-protocol.h"
#define COUNT 120
static struct wp_presentation *presentation;
static uint32_t presentation_clock=UINT32_MAX;
static GtkWidget *label;
static unsigned count,errors;
typedef struct { uint64_t requested,received,presented,sequence; uint32_t refresh,flags,outputs,object; int state; } Row;
static Row rows[COUNT];
static uint64_t now(void) {
 struct timespec ts;
 if(presentation_clock==UINT32_MAX || clock_gettime((clockid_t)presentation_clock,&ts)!=0){errors++;return 0;}
 return (uint64_t)ts.tv_sec*1000000000u+(uint64_t)ts.tv_nsec;
}
static void sync_output(void *data,struct wp_presentation_feedback *f,struct wl_output *output) {
 (void)f;(void)output;((Row*)data)->outputs++;
}
static void presented(void *data,struct wp_presentation_feedback *f,uint32_t hi,uint32_t lo,uint32_t ns,uint32_t refresh,uint32_t shi,uint32_t slo,uint32_t flags) {
 Row *r=data;r->received=now();r->state=1;r->presented=(((uint64_t)hi<<32)|lo)*1000000000u+ns;
 r->sequence=((uint64_t)shi<<32)|slo;r->refresh=refresh;r->flags=flags;
 if(ns>=1000000000u)errors++;
 wp_presentation_feedback_destroy(f);
}
static void discarded(void *data,struct wp_presentation_feedback *f) {
 Row *r=data;r->received=now();r->state=2;wp_presentation_feedback_destroy(f);
}
static const struct wp_presentation_feedback_listener feedback_listener={sync_output,presented,discarded};
static void clock_id(void *data,struct wp_presentation *p,uint32_t id) {
 (void)data;(void)p;presentation_clock=id;
}
static const struct wp_presentation_listener presentation_listener={clock_id};
static void global(void *data,struct wl_registry *registry,uint32_t name,const char *interface,uint32_t version) {
 (void)data;(void)version;
 if(strcmp(interface,"wp_presentation")==0) {
  presentation=wl_registry_bind(registry,name,&wp_presentation_interface,1);
  wp_presentation_add_listener(presentation,&presentation_listener,NULL);
 }
}
static void removed(void *data,struct wl_registry *registry,uint32_t name){(void)data;(void)registry;(void)name;}
static const struct wl_registry_listener registry_listener={global,removed};
static gboolean tick(GtkWidget *widget,GdkFrameClock *clock,gpointer data) {
 (void)clock;(void)data;
 if(count>=COUNT)return G_SOURCE_REMOVE;
 struct wl_surface *surface=gdk_wayland_window_get_wl_surface(gtk_widget_get_window(widget));
 if(!surface){errors++;return G_SOURCE_REMOVE;}
 Row *r=&rows[count++];r->requested=now();
 struct wp_presentation_feedback *f=wp_presentation_feedback(presentation,surface);
 r->object=wl_proxy_get_id((struct wl_proxy*)f);
 wp_presentation_feedback_add_listener(f,&feedback_listener,r);
 char text[96];g_snprintf(text,sizeof(text),"direct native presentation capability frame %u",count);
 gtk_label_set_text(GTK_LABEL(label),text);
 return count<COUNT;
}
static gboolean finish(gpointer data){(void)data;gtk_main_quit();return G_SOURCE_REMOVE;}
int main(int argc,char **argv) {
 gtk_init(&argc,&argv);GdkDisplay *display=gdk_display_get_default();
 if(!GDK_IS_WAYLAND_DISPLAY(display)){fputs("not a Wayland display\n",stderr);return 3;}
 struct wl_display *native=gdk_wayland_display_get_wl_display(display);
 struct wl_registry *registry=wl_display_get_registry(native);wl_registry_add_listener(registry,&registry_listener,NULL);
 if(wl_display_roundtrip(native)<0 || wl_display_roundtrip(native)<0 || !presentation || presentation_clock==UINT32_MAX){
  fputs("native wp_presentation unavailable\n",stderr);return 4;
 }
 GtkWidget *window=gtk_window_new(GTK_WINDOW_TOPLEVEL);gtk_window_set_default_size(GTK_WINDOW(window),400,200);
 label=gtk_label_new("native protocol capability");gtk_container_add(GTK_CONTAINER(window),label);
 gtk_widget_add_tick_callback(window,tick,NULL,NULL);gtk_widget_show_all(window);
 g_timeout_add(8000,finish,NULL);gtk_main();
 printf("{\"schema\":1,\"synthetic_only\":true,\"pid\":%ld,\"clock_id\":%u,\"errors\":%u,\"requested\":%u,\"rows\":[",(long)getpid(),presentation_clock,errors,count);
 for(unsigned i=0;i<count;i++) {Row *r=&rows[i];
  printf("%s{\"index\":%u,\"feedback_object\":%u,\"request_ns\":%llu,\"callback_ns\":%llu,\"status\":%d,\"presentation_ns\":%llu,\"refresh_ns\":%u,\"sequence\":%llu,\"flags\":%u,\"sync_outputs\":%u}",i?",":"",i,r->object,(unsigned long long)r->requested,(unsigned long long)r->received,r->state,(unsigned long long)r->presented,r->refresh,(unsigned long long)r->sequence,r->flags,r->outputs);
 }
 fputs("]}\n",stdout);gtk_widget_destroy(window);wp_presentation_destroy(presentation);wl_registry_destroy(registry);
 return errors || count!=COUNT ? 5:0;
}
