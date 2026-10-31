/* SPDX-License-Identifier: MIT
 * Actions-only passive GTK observer. No event handling, redraw, timer or product hooks.
 */
#define _GNU_SOURCE
#include <gtk/gtk.h>
#include <gmodule.h>
#include <dlfcn.h>
#include <errno.h>
#include <pthread.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#define CAP 65536u
#define CLOCKS 64u
#define FIELDS 12u
static const char *keys[FIELDS]={"sequence","painted_generation","book","page","font",
 "busy","saving","shelf_top_id","shelf_pending","shelf_loading","shelf_restoring","reader_visible"};
typedef struct {gint64 at;gint64 values[FIELDS];gint64 end;int ok;} State;
typedef struct {gint64 at;guint32 server_ms;unsigned type,code,hardware,clock;} Input;
typedef struct {gint64 at,counter;unsigned clock,kind;} Draw;
typedef struct {gint64 before,after,counter;unsigned clock;GdkFrameTimings *timing;} Frame;
static State states[CAP];
static Input inputs[CAP];
static Draw draws[CAP];
static Frame frames[CAP];
static GdkFrameClock *clocks[CLOCKS];
static unsigned ns,ni,nd,nf,nc,overflow,event_hook,draw_hook,list_draw_handlers;
static gint64 begins[CLOCKS];
static gboolean enabled;
static pthread_mutex_t mutex=PTHREAD_MUTEX_INITIALIZER;
static pthread_once_t once=PTHREAD_ONCE_INIT;
static gboolean (*real_contents)(const gchar*,const gchar*,gssize,GError**);
static void resolve(void){void *p=dlsym(RTLD_NEXT,"g_file_set_contents");memcpy(&real_contents,&p,sizeof(real_contents));}
static gint64 value(const char *text,size_t length,const char *key){
 char needle[80];snprintf(needle,sizeof(needle),"\n%s=",key);
 size_t n=strlen(needle);
 const char *p=memmem(text,length,needle,n);
 if(!p){return -1;}
 p+=n;const char *end=text+length;guint64 result=0;
 if(p==end || *p<'0' || *p>'9'){return -1;}
 while(p<end && *p>='0' && *p<='9'){
  unsigned digit=(unsigned)(*p-'0');
  if(result>((guint64)G_MAXINT64-digit)/10u){return -1;}
  result=result*10u+digit;p++;
 }
 return (gint64)result;
}
gboolean g_file_set_contents(const gchar *name,const gchar *contents,gssize length,GError **error){
 pthread_once(&once,resolve);
 if(!real_contents){errno=ENOSYS;return FALSE;}
 gboolean capture=enabled && name && contents && (length<0 || length>=16) &&
  strncmp(contents,"[host]\nsequence=",16)==0 && g_str_has_suffix(name,"/state.ini");
 State s={0};
 if(capture){s.at=g_get_monotonic_time();for(unsigned i=0;i<FIELDS;i++)s.values[i]=value(contents,length<0?strlen(contents):(size_t)length,keys[i]);}
 gboolean result=real_contents(name,contents,length,error);
 if(capture){
  s.end=g_get_monotonic_time();s.ok=result;
  pthread_mutex_lock(&mutex);if(ns<CAP)states[ns++]=s;else overflow++;pthread_mutex_unlock(&mutex);
 }
 return result;
}
static gboolean ours(GtkWidget *w){
 GtkWidget *top=gtk_widget_get_toplevel(w);
 return GTK_IS_WINDOW(top) && g_strcmp0(gtk_window_get_title(GTK_WINDOW(top)),"EXReader Linux")==0;
}
static unsigned clock_id(GdkFrameClock *c){
 for(unsigned i=0;i<nc;i++)if(clocks[i]==c)return i;
 return CLOCKS;
}
static void before(GdkFrameClock *clock,gpointer data){
 (void)clock;begins[GPOINTER_TO_UINT(data)]=g_get_monotonic_time();
}
static void after(GdkFrameClock *clock,gpointer data){
 unsigned i=GPOINTER_TO_UINT(data);
 gint64 counter=gdk_frame_clock_get_frame_counter(clock);
 GdkFrameTimings *t=gdk_frame_clock_get_timings(clock,counter);
 pthread_mutex_lock(&mutex);
 if(nf<CAP)frames[nf++]=(Frame){begins[i],g_get_monotonic_time(),counter,i,t?gdk_frame_timings_ref(t):NULL};
 else overflow++;
 pthread_mutex_unlock(&mutex);
}
static void record_draw(GtkWidget *w,unsigned kind){
 GdkFrameClock *c=gtk_widget_get_frame_clock(w);if(!c)return;
 Draw row={g_get_monotonic_time(),gdk_frame_clock_get_frame_counter(c),clock_id(c),kind};
 pthread_mutex_lock(&mutex);if(nd<CAP)draws[nd++]=row;else overflow++;pthread_mutex_unlock(&mutex);
}
static gboolean list_draw(GtkWidget *w,cairo_t *cr,gpointer data){
 (void)cr;(void)data;
 if(enabled && ours(w) && g_strcmp0(atk_object_get_name(gtk_widget_get_accessible(w)),"Bookshelf")==0)
  record_draw(w,2u);
 /* GtkWidget skips signal emission when no instance handler exists. Observe
  * before the class draw and return FALSE so normal painting is preserved.
  * GTK 3.24.33 gtk/gtkwidget.c: gtk_widget_draw_internal(). */
 return FALSE;
}
static gboolean realized(GSignalInvocationHint *h,guint n,const GValue *v,gpointer data){
 (void)h;(void)data;
 if(!n || !GTK_IS_WIDGET(g_value_get_object(v)))return TRUE;
 GtkWidget *w=GTK_WIDGET(g_value_get_object(v));
 if(GTK_IS_LIST_BOX(w) && !g_object_get_data(G_OBJECT(w),"exr-f08-list-draw")){
  g_signal_connect(w,"draw",G_CALLBACK(list_draw),NULL);
  g_object_set_data(G_OBJECT(w),"exr-f08-list-draw",GUINT_TO_POINTER(1));
  list_draw_handlers++;
 }
 if(!GTK_IS_WINDOW(w))return TRUE;
 /* Title may be assigned after realize; clocks are harmlessly observed for all windows. */
 GdkFrameClock *c=gtk_widget_get_frame_clock(w);
 if(!c || clock_id(c)!=CLOCKS)return TRUE;
 if(nc==CLOCKS){overflow++;return TRUE;}
 unsigned i=nc++;clocks[i]=g_object_ref(c);
 g_signal_connect(c,"before-paint",G_CALLBACK(before),GUINT_TO_POINTER(i));
 g_signal_connect_after(c,"after-paint",G_CALLBACK(after),GUINT_TO_POINTER(i));
 return TRUE;
}
static gboolean event_observed(GSignalInvocationHint *h,guint n,const GValue *v,gpointer data){
 (void)h;(void)data;
 if(!enabled || n<2)return TRUE;
 GtkWidget *w=GTK_WIDGET(g_value_get_object(v));if(!ours(w))return TRUE;
 GdkEvent *e=g_value_get_boxed(v+1);if(!e)return TRUE;
 Input row={0};row.at=g_get_monotonic_time();row.server_ms=gdk_event_get_time(e);
 row.clock=clock_id(gtk_widget_get_frame_clock(w));
 if(e->type==GDK_KEY_PRESS){row.type=1;row.code=e->key.keyval;row.hardware=e->key.hardware_keycode;}
 else if(e->type==GDK_SCROLL){row.type=2;row.code=e->scroll.direction;}
 else return TRUE;
 pthread_mutex_lock(&mutex);if(ni<CAP)inputs[ni++]=row;else overflow++;pthread_mutex_unlock(&mutex);
 /* Emission-hook TRUE keeps the observer installed; it is NOT a Gtk event-handler return. */
 return TRUE;
}
static gboolean draw_observed(GSignalInvocationHint *h,guint n,const GValue *v,gpointer data){
 (void)h;(void)data;
 if(!enabled || n<1)return TRUE;
 GtkWidget *w=GTK_WIDGET(g_value_get_object(v));if(!ours(w))return TRUE;
 const char *name=atk_object_get_name(gtk_widget_get_accessible(w));
 unsigned kind=(GTK_IS_IMAGE(w) &&
  (g_strcmp0(name,"Rendered page; selectable text is in the adjacent panel")==0 ||
   g_strcmp0(name,"Rendered reading page; selectable text and notes are in More")==0))?1u:0u;
 /* Lists are recorded by the instance callback, never twice by this hook. */
 if(kind)record_draw(w,kind);
 return TRUE;
}
G_MODULE_EXPORT void gtk_module_init(gint *argc,gchar ***argv){
 (void)argc;(void)argv;
 if(enabled || !getenv("EXR_F08_CAUSAL_OUTPUT"))return;
 enabled=TRUE;gpointer klass=g_type_class_ref(GTK_TYPE_WIDGET);
 guint r=g_signal_lookup("realize",GTK_TYPE_WIDGET),e=g_signal_lookup("event",GTK_TYPE_WIDGET),d=g_signal_lookup("draw",GTK_TYPE_WIDGET);
 if(!r || !g_signal_add_emission_hook(r,0,realized,NULL,NULL))overflow++;
 event_hook=e && g_signal_add_emission_hook(e,0,event_observed,NULL,NULL)!=0;
 draw_hook=d && g_signal_add_emission_hook(d,0,draw_observed,NULL,NULL)!=0;
 if(!event_hook || !draw_hook)overflow++;
 g_type_class_unref(klass);
}
static void quoted(FILE *f,const char *s){
 fputc('"',f);
 for(const unsigned char *p=(const unsigned char*)(s?s:"");*p;p++){
  if(*p=='"' || *p=='\\'){fputc('\\',f);fputc(*p,f);}
  else if(*p<32)fprintf(f,"\\u%04x",*p);else fputc(*p,f);
 }
 fputc('"',f);
}
__attribute__((destructor)) static void finish(void){
 if(!enabled){return;}
 enabled=FALSE;
 char path[4096],exe[4096];ssize_t len=readlink("/proc/self/exe",exe,sizeof(exe)-1);
 if(len<0)exe[0]=0;else exe[len]=0;
 if(snprintf(path,sizeof(path),"%s/%ld.json",getenv("EXR_F08_CAUSAL_OUTPUT"),(long)getpid())>=(int)sizeof(path))return;
 FILE *f=fopen(path,"wx");if(!f){perror("causal output");return;}
 pthread_mutex_lock(&mutex);
 fprintf(f,"{\"schema\":1,\"pid\":%ld,\"source\":",(long)getpid());quoted(f,getenv("GITHUB_SHA"));
 fputs(",\"run\":",f);quoted(f,getenv("GITHUB_RUN_ID"));fputs(",\"attempt\":",f);quoted(f,getenv("GITHUB_RUN_ATTEMPT"));
 fputs(",\"executable\":",f);quoted(f,exe);
 fprintf(f,",\"capacity\":%u,\"overflow\":%u,\"event_hook\":%u,\"draw_hook\":%u,\"clock_count\":%u,\"probe_static_bytes\":%zu",
  CAP,overflow,event_hook,draw_hook,nc,sizeof(states)+sizeof(inputs)+sizeof(draws)+sizeof(frames));
 fprintf(f,",\"list_draw_handlers\":%u",list_draw_handlers);
 fputs(",\"states\":[",f);
 for(unsigned i=0;i<ns;i++){
  State *s=states+i;fprintf(f,"%s{\"at\":%"G_GINT64_FORMAT",\"end\":%"G_GINT64_FORMAT",\"ok\":%s",i?",":"",s->at,s->end,s->ok?"true":"false");
  for(unsigned k=0;k<FIELDS;k++){fprintf(f,",\"%s\":%"G_GINT64_FORMAT,keys[k],s->values[k]);}
  fputc('}',f);
 }
 fputs("],\"inputs\":[",f);
 for(unsigned i=0;i<ni;i++){Input *e=inputs+i;fprintf(f,"%s{\"at\":%"G_GINT64_FORMAT",\"server_ms\":%u,\"type\":%u,\"code\":%u,\"hardware\":%u,\"clock\":%u}",i?",":"",e->at,e->server_ms,e->type,e->code,e->hardware,e->clock);}
 fputs("],\"draws\":[",f);
 for(unsigned i=0;i<nd;i++){Draw *d=draws+i;fprintf(f,"%s{\"at\":%"G_GINT64_FORMAT",\"clock\":%u,\"counter\":%"G_GINT64_FORMAT",\"kind\":%u}",i?",":"",d->at,d->clock,d->counter,d->kind);}
 fputs("],\"frames\":[",f);
 for(unsigned i=0;i<nf;i++){
  Frame *r=frames+i;GdkFrameTimings *t=r->timing;
  gint64 presentation=t?gdk_frame_timings_get_presentation_time(t):0;
  fprintf(f,"%s{\"clock\":%u,\"counter\":%"G_GINT64_FORMAT",\"before\":%"G_GINT64_FORMAT",\"after\":%"G_GINT64_FORMAT",\"frame_time\":%"G_GINT64_FORMAT",\"complete\":%s,\"presentation\":",
   i?",":"",r->clock,r->counter,r->before,r->after,t?gdk_frame_timings_get_frame_time(t):0,t&&gdk_frame_timings_get_complete(t)?"true":"false");
  if(presentation>0)fprintf(f,"%"G_GINT64_FORMAT,presentation);else fputs("null",f);
  fprintf(f,",\"predicted\":%"G_GINT64_FORMAT",\"refresh\":%"G_GINT64_FORMAT"}",t?gdk_frame_timings_get_predicted_presentation_time(t):0,t?gdk_frame_timings_get_refresh_interval(t):0);
 }
 fputs("]}\n",f);pthread_mutex_unlock(&mutex);
 int failed=ferror(f);if(fclose(f)!=0 || failed)fprintf(stderr,"causal output flush failed\n");
}
