/* SPDX-License-Identifier: MIT
 * Test-only GTK module + preload observer. No product behavior changes.
 * Timings remain GDK/Xvfb observations, not physical-display presentation.
 */
#define _GNU_SOURCE
#include <gtk/gtk.h>
#include <gmodule.h>
#include <errno.h>
#include <dlfcn.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <stdint.h>
#include <pthread.h>
#define CAP 65536u
#define CLOCKS 64u
typedef struct {
  unsigned clock_id;
  gint64 counter, before, after;
  GdkFrameTimings *timings;
} Frame;
typedef struct { gint64 start,end; size_t bytes; int ok; unsigned frame_count; } Write;
static Frame frames[CAP];
static Write writes[CAP];
static GdkFrameClock *clocks[CLOCKS];
static gint64 begins[CLOCKS];
static unsigned nf,nw,nc,overflow;
static pthread_mutex_t lock=PTHREAD_MUTEX_INITIALIZER;
static gboolean enabled;
static gboolean (*real_write)(const gchar*,const gchar*,gssize,GError**);
static void find_write(void) {
  void *symbol=dlsym(RTLD_NEXT,"g_file_set_contents");
  memcpy(&real_write,&symbol,sizeof(real_write));
}
static pthread_once_t resolve_once=PTHREAD_ONCE_INIT;
gboolean g_file_set_contents(const gchar *name,const gchar *contents,gssize length,GError **error) {
  pthread_once(&resolve_once,find_write);
  if(!real_write) { errno=ENOSYS;return FALSE; }
  gboolean capture=enabled && name && contents && (length<0 || length>=16)
      && strncmp(contents,"[host]\nsequence=",16)==0
      && g_str_has_suffix(name,"/state.ini");
  gint64 start=capture?g_get_monotonic_time():0;
  gboolean result=real_write(name,contents,length,error);
  gint64 end=capture?g_get_monotonic_time():0;
  if(capture) {
    pthread_mutex_lock(&lock);
    if(nw<CAP) writes[nw++]=(Write){start,end,length<0?strlen(contents):(size_t)length,result,nf};
    else overflow++;
    pthread_mutex_unlock(&lock);
  }
  return result;
}
static void before(GdkFrameClock *clock,gpointer user) {
  (void)clock;
  unsigned i=GPOINTER_TO_UINT(user);
  begins[i]=g_get_monotonic_time();
}
static void after(GdkFrameClock *clock,gpointer user) {
  unsigned i=GPOINTER_TO_UINT(user);
  gint64 counter=gdk_frame_clock_get_frame_counter(clock);
  GdkFrameTimings *t=gdk_frame_clock_get_timings(clock,counter);
  pthread_mutex_lock(&lock);
  if(nf<CAP) frames[nf++]=(Frame){i,counter,begins[i],g_get_monotonic_time(),t?gdk_frame_timings_ref(t):NULL};
  else overflow++;
  pthread_mutex_unlock(&lock);
}
static gboolean realized(GSignalInvocationHint *hint,guint n,const GValue *v,gpointer data) {
  (void)hint;(void)data;
  if(!n || !GTK_IS_WINDOW(g_value_get_object(v))) return TRUE;
  GtkWidget *widget=GTK_WIDGET(g_value_get_object(v));
  GdkFrameClock *clock=gtk_widget_get_frame_clock(widget);
  if(!clock) return TRUE;
  for(unsigned i=0;i<nc;i++) if(clocks[i]==clock) return TRUE;
  if(nc==CLOCKS) { overflow++;return TRUE; }
  unsigned i=nc++;
  clocks[i]=g_object_ref(clock);
  g_signal_connect(clock,"before-paint",G_CALLBACK(before),GUINT_TO_POINTER(i));
  g_signal_connect_after(clock,"after-paint",G_CALLBACK(after),GUINT_TO_POINTER(i));
  return TRUE;
}
G_MODULE_EXPORT void gtk_module_init(gint *argc,gchar ***argv) {
  (void)argc;(void)argv;
  const char *dir=getenv("EXR_F08_OUTPUT");
  if(!dir || !*dir || enabled) return;
  enabled=TRUE;
  gpointer widget_class=g_type_class_ref(GTK_TYPE_WIDGET);
  guint id=g_signal_lookup("realize",GTK_TYPE_WIDGET);
  if(!id || !g_signal_add_emission_hook(id,0,realized,NULL,NULL)) overflow++;
  g_type_class_unref(widget_class);
}
static void quoted(FILE *f,const char *s) {
  fputc('"',f);
  for(const unsigned char *p=(const unsigned char *)(s?s:"");*p;p++) {
    if(*p=='"' || *p=='\\') { fputc('\\',f);fputc(*p,f); }
    else if(*p<32) fprintf(f,"\\u%04x",*p);
    else fputc(*p,f);
  }
  fputc('"',f);
}
__attribute__((destructor)) static void finish(void) {
  if(!enabled) return;
  enabled=FALSE;
  const char *dir=getenv("EXR_F08_OUTPUT");
  char path[4096],exe[4096];
  ssize_t len=readlink("/proc/self/exe",exe,sizeof(exe)-1);
  if(len<0) exe[0]=0;else exe[len]=0;
  if(snprintf(path,sizeof(path),"%s/%ld.json",dir,(long)getpid())>=(int)sizeof(path)) {
    fprintf(stderr,"F08 probe output path overflow\n");return;
  }
  FILE *f=fopen(path,"wx");
  if(!f) { perror("F08 probe output");return; }
  pthread_mutex_lock(&lock);
  fprintf(f,"{\"schema\":1,\"pid\":%ld,\"source\":",(long)getpid());
  quoted(f,getenv("GITHUB_SHA"));
  fprintf(f,",\"run\":");quoted(f,getenv("GITHUB_RUN_ID"));
  fprintf(f,",\"attempt\":");quoted(f,getenv("GITHUB_RUN_ATTEMPT"));
  fprintf(f,",\"executable\":");quoted(f,exe);
  fprintf(f,",\"clock_count\":%u,\"overflow\":%u,\"capacity\":%u,\"probe_static_bytes\":%zu,\"frames\":[",nc,overflow,CAP,sizeof(frames)+sizeof(writes)+sizeof(clocks)+sizeof(begins));
  for(unsigned i=0;i<nf;i++) {
    Frame *r=&frames[i];GdkFrameTimings *t=r->timings;
    gint64 frame=t?gdk_frame_timings_get_frame_time(t):0;
    gint64 presentation=t?gdk_frame_timings_get_presentation_time(t):0;
    gint64 predicted=t?gdk_frame_timings_get_predicted_presentation_time(t):0;
    gint64 refresh=t?gdk_frame_timings_get_refresh_interval(t):0;
    fprintf(f,"%s{\"clock\":%u,\"counter\":%"G_GINT64_FORMAT",\"before_us\":%"G_GINT64_FORMAT",\"after_us\":%"G_GINT64_FORMAT",\"complete\":%s,\"frame_time_us\":%"G_GINT64_FORMAT",\"presentation_us\":",i?",":"",r->clock_id,r->counter,r->before,r->after,t&&gdk_frame_timings_get_complete(t)?"true":"false",frame);
    if(presentation>0) fprintf(f,"%"G_GINT64_FORMAT,presentation);else fputs("null",f);
    fprintf(f,",\"predicted_presentation_us\":%"G_GINT64_FORMAT",\"refresh_interval_us\":%"G_GINT64_FORMAT"}",predicted,refresh);
  }
  fputs("],\"writes\":[",f);
  for(unsigned i=0;i<nw;i++) {
    Write *w=&writes[i];
    fprintf(f,"%s{\"start_us\":%"G_GINT64_FORMAT",\"end_us\":%"G_GINT64_FORMAT",\"bytes\":%zu,\"ok\":%s,\"frames_seen\":%u}",i?",":"",w->start,w->end,w->bytes,w->ok?"true":"false",w->frame_count);
  }
  fputs("]}\n",f);
  pthread_mutex_unlock(&lock);
  int failed=ferror(f);
  if(fclose(f)!=0 || failed) fprintf(stderr,"F08 probe output flush failed\n");
}
