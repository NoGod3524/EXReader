/* SPDX-License-Identifier: MIT
 * Full GTK job-to-native-completion observer. XSync is a measured upper-bound fence.
 */
#define _GNU_SOURCE
#include <gtk/gtk.h>
#include <gdk/gdkx.h>
#include <gmodule.h>
#include <X11/Xlib.h>
#include <dlfcn.h>
#include <pthread.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include "../reader_f08_causal_frame_20261031/shelf_content.h"
#define CAP 65536u
#define CLOCKS 64u
typedef struct {gpointer ptr,data;GSourceFunc callback;gint64 queued,start,worker_end,apply_start,apply_end,image_at,draw_end,complete;int action,input,page,shelf,shelf_visible,superseded;gint64 generation,frame_generation,shelf_generation,book,page_number,font;unsigned clock;gint64 counter;guint source;} Job;
typedef struct {gint64 at;guint32 server_ms;unsigned type,code,hardware;} Input;
typedef struct {gint64 gdk_frame_start,animation_frame_time,before,draw_end,sync_start,sync_end,counter;unsigned clock,page_job,shelf_job,input,kind;int native_error,shelf_restoring,body_available;double body_scroll;int body_x,body_y,body_width,body_height;gint64 frame_generation;F08ShelfContent content;} Frame;
static Job jobs[CAP];static Input inputs[CAP];static Frame frames[CAP];
static unsigned nj,ni,nf,nc,overflow,page_job,shelf_job;
static GAsyncQueue *owner;static GdkFrameClock *clocks[CLOCKS];static Frame pending[CLOCKS];
static gint64 generation,frame_generation,shelf_generation,book,page_number,font,shelf_restoring;
static gboolean enabled;static pthread_mutex_t mutex=PTHREAD_MUTEX_INITIALIZER;
static _Thread_local unsigned worker_job,apply_job;
static GAsyncQueue *(*new_queue)(void);static void (*push_queue)(GAsyncQueue*,gpointer);static gpointer (*pop_queue)(GAsyncQueue*);
static guint (*add_idle)(GSourceFunc,gpointer);static void (*set_image)(GtkImage*,GdkPixbuf*);static void (*insert_row)(GtkListBox*,GtkWidget*,gint);
static gboolean (*contents_write)(const gchar*,const gchar*,gssize,GError**);
static pthread_once_t once=PTHREAD_ONCE_INIT;
#define RESOLVE(var,name) do{void *s=dlsym(RTLD_NEXT,name);memcpy(&(var),&s,sizeof(var));if(!var)abort();}while(0)
static void resolve(void){RESOLVE(new_queue,"g_async_queue_new");RESOLVE(push_queue,"g_async_queue_push");RESOLVE(pop_queue,"g_async_queue_pop");RESOLVE(add_idle,"g_idle_add");RESOLVE(set_image,"gtk_image_set_from_pixbuf");RESOLVE(insert_row,"gtk_list_box_insert");RESOLVE(contents_write,"g_file_set_contents");}
static gboolean caller_is_host(void *address){Dl_info info;if(!dladdr(address,&info)||!info.dli_fname)return FALSE;const char *name=strrchr(info.dli_fname,'/');return strcmp(name?name+1:info.dli_fname,"exreader-linux")==0;}
static gboolean ours(GtkWidget *w){GtkWidget *top=gtk_widget_get_toplevel(w);return GTK_IS_WINDOW(top)&&g_strcmp0(gtk_window_get_title(GTK_WINDOW(top)),"EXReader Linux")==0;}
static gboolean belongs(GtkWidget *w){GtkWidget *top=gtk_widget_get_toplevel(w);while(GTK_IS_WINDOW(top)){if(g_strcmp0(gtk_window_get_title(GTK_WINDOW(top)),"EXReader Linux")==0)return TRUE;top=GTK_WIDGET(gtk_window_get_transient_for(GTK_WINDOW(top)));}return FALSE;}
static gboolean shelf_list(GtkWidget *w){return GTK_IS_LIST_BOX(w)&&ours(w)&&g_strcmp0(atk_object_get_name(gtk_widget_get_accessible(w)),"Bookshelf")==0;}
GAsyncQueue *g_async_queue_new(void){pthread_once(&once,resolve);GAsyncQueue *q=new_queue();if(enabled&&caller_is_host(__builtin_return_address(0))){if(owner&&owner!=q)overflow++;else owner=q;}return q;}
void g_async_queue_push(GAsyncQueue *q,gpointer data){
 pthread_once(&once,resolve);if(enabled&&q==owner){pthread_mutex_lock(&mutex);if(nj<CAP){Job *j=&jobs[nj++];j->ptr=data;j->queued=g_get_monotonic_time();memcpy(&j->action,data,sizeof(j->action));j->input=(int)ni;j->generation=generation;j->shelf_generation=shelf_generation;}else overflow++;pthread_mutex_unlock(&mutex);}push_queue(q,data);
}
gpointer g_async_queue_pop(GAsyncQueue *q){
 pthread_once(&once,resolve);gpointer data=pop_queue(q);if(enabled&&q==owner){gint64 at=g_get_monotonic_time();pthread_mutex_lock(&mutex);worker_job=0;for(unsigned i=nj;i>0;i--)if(jobs[i-1].ptr==data&&!jobs[i-1].start){jobs[i-1].start=at;worker_job=i;break;}if(!worker_job)overflow++;pthread_mutex_unlock(&mutex);}return data;
}
static gboolean apply(gpointer data){
 Job *j=data;unsigned old=apply_job;apply_job=(unsigned)(j-jobs)+1;j->apply_start=g_get_monotonic_time();gboolean keep=j->callback(j->data);j->apply_end=g_get_monotonic_time();j->generation=generation;j->frame_generation=frame_generation;j->shelf_generation=shelf_generation;j->book=book;j->page_number=page_number;j->font=font;apply_job=old;return keep;
}
guint g_idle_add(GSourceFunc callback,gpointer data){
 pthread_once(&once,resolve);if(enabled&&worker_job){Job *j=&jobs[worker_job-1];j->worker_end=g_get_monotonic_time();j->callback=callback;j->data=data;worker_job=0;j->source=add_idle(apply,j);return j->source;}return add_idle(callback,data);
}
void gtk_image_set_from_pixbuf(GtkImage *image,GdkPixbuf *pixels){
 pthread_once(&once,resolve);if(enabled&&apply_job&&ours(GTK_WIDGET(image))){Job *j=&jobs[apply_job-1];j->page=1;j->image_at=g_get_monotonic_time();if(page_job&&!jobs[page_job-1].complete)jobs[page_job-1].superseded=1;page_job=apply_job;}set_image(image,pixels);
}
void gtk_list_box_insert(GtkListBox *box,GtkWidget *child,gint position){
 pthread_once(&once,resolve);if(enabled&&apply_job&&shelf_list(GTK_WIDGET(box))){Job *j=&jobs[apply_job-1];j->shelf=1;j->shelf_visible=gtk_widget_is_drawable(GTK_WIDGET(box));if(shelf_job!=apply_job&&shelf_job&&!jobs[shelf_job-1].complete)jobs[shelf_job-1].superseded=1;shelf_job=apply_job;}insert_row(box,child,position);
}
static gint64 number(const char *text,size_t length,const char *key){char needle[80];snprintf(needle,sizeof(needle),"\n%s=",key);size_t n=strlen(needle);const char *p=memmem(text,length,needle,n);if(!p)return -1;char *end=NULL;gint64 v=g_ascii_strtoll(p+n,&end,10);return end==p+n?-1:v;}
gboolean g_file_set_contents(const gchar *name,const gchar *contents,gssize length,GError **error){
 pthread_once(&once,resolve);if(enabled&&name&&contents&&(length<0||length>=16)&&strncmp(contents,"[host]\nsequence=",16)==0&&g_str_has_suffix(name,"/state.ini")){
  size_t n=length<0?strlen(contents):(size_t)length;generation=number(contents,n,"generation");frame_generation=number(contents,n,"frame_generation");shelf_generation=number(contents,n,"shelf_generation");book=number(contents,n,"book");page_number=number(contents,n,"page");font=number(contents,n,"font");shelf_restoring=number(contents,n,"shelf_restoring");
 }return contents_write(name,contents,length,error);
}
static unsigned clock_id(GdkFrameClock *clock){for(unsigned i=0;i<nc;i++)if(clocks[i]==clock)return i;return CLOCKS;}
static void before(GdkFrameClock *clock,gpointer data){unsigned i=GPOINTER_TO_UINT(data);Frame *f=&pending[i];memset(f,0,sizeof(*f));f->clock=i;f->counter=gdk_frame_clock_get_frame_counter(clock);f->before=g_get_monotonic_time();f->input=ni;}
static gboolean drawn(GtkWidget *w,cairo_t *cr,gpointer data){
 (void)data;if(!enabled||!ours(w))return FALSE;GdkFrameClock *clock=gtk_widget_get_frame_clock(w);unsigned i=clock_id(clock);if(i>=nc){overflow++;return FALSE;}Frame *f=&pending[i];
 if(GTK_IS_IMAGE(w)){const char *name=atk_object_get_name(gtk_widget_get_accessible(w));if(g_strcmp0(name,"Rendered page; selectable text is in the adjacent panel")&&g_strcmp0(name,"Rendered reading page; selectable text and notes are in More"))return FALSE;f->kind|=1;f->page_job=page_job;f->frame_generation=frame_generation;if(page_job){Job *j=&jobs[page_job-1];if(!j->complete){j->draw_end=g_get_monotonic_time();j->clock=i;j->counter=f->counter;}}}
 else if(GTK_IS_VIEWPORT(w)){GtkWidget *child=gtk_bin_get_child(GTK_BIN(w));if(shelf_list(child)){f->kind|=2;f->shelf_job=shelf_job;f->content=f08_shelf_content_for_draw(child,w,cr);f->shelf_restoring=(int)shelf_restoring;if(shelf_job){Job *j=&jobs[shelf_job-1];if(!j->complete){j->draw_end=g_get_monotonic_time();j->clock=i;j->counter=f->counter;}}}
 else {while(child&&GTK_IS_BIN(child)&&!GTK_IS_IMAGE(child))child=gtk_bin_get_child(GTK_BIN(child));if(!child||!GTK_IS_IMAGE(child))return FALSE;const char *name=atk_object_get_name(gtk_widget_get_accessible(child));if(g_strcmp0(name,"Rendered page; selectable text is in the adjacent panel")&&g_strcmp0(name,"Rendered reading page; selectable text and notes are in More"))return FALSE;f->kind|=4;f->page_job=page_job;f->frame_generation=frame_generation;f->body_available=gtk_widget_is_drawable(child);gtk_widget_translate_coordinates(child,w,0,0,&f->body_x,&f->body_y);f->body_width=gtk_widget_get_allocated_width(child);f->body_height=gtk_widget_get_allocated_height(child);double x1,y1,x2,y2;cairo_clip_extents(cr,&x1,&y1,&x2,&y2);f->body_available=f->body_available&&x2>x1&&y2>y1&&x2>f->body_x&&y2>f->body_y&&x1<f->body_x+f->body_width&&y1<f->body_y+f->body_height;GtkWidget *parent=gtk_widget_get_parent(w);while(parent&&!GTK_IS_SCROLLED_WINDOW(parent))parent=gtk_widget_get_parent(parent);if(parent)f->body_scroll=gtk_adjustment_get_value(gtk_scrolled_window_get_vadjustment(GTK_SCROLLED_WINDOW(parent)));else f->body_available=0;if(page_job){Job *j=&jobs[page_job-1];if(!j->complete){j->draw_end=g_get_monotonic_time();j->clock=i;j->counter=f->counter;}}}}
 f->draw_end=g_get_monotonic_time();return FALSE;
}
static void after(GdkFrameClock *clock,gpointer data){
 unsigned i=GPOINTER_TO_UINT(data);Frame f=pending[i];GdkFrameTimings *timing=gdk_frame_clock_get_timings(clock,f.counter);f.gdk_frame_start=timing?gdk_frame_timings_get_frame_time(timing):0;f.animation_frame_time=gdk_frame_clock_get_frame_time(clock);GdkDisplay *display=gdk_display_get_default();f.sync_start=g_get_monotonic_time();f.native_error=-1;
 if(GDK_IS_X11_DISPLAY(display)){gdk_x11_display_error_trap_push(display);gdk_display_flush(display);XSync(gdk_x11_display_get_xdisplay(display),False);f.native_error=gdk_x11_display_error_trap_pop(display);}
 f.sync_end=g_get_monotonic_time();pthread_mutex_lock(&mutex);if(nf<CAP)frames[nf++]=f;else overflow++;
 if(f.native_error==0){if(f.page_job){Job *j=&jobs[f.page_job-1];if(!j->complete)j->complete=f.sync_end;}if(f.shelf_job&&f.content.available){Job *j=&jobs[f.shelf_job-1];if(!j->complete)j->complete=f.sync_end;}}
 pthread_mutex_unlock(&mutex);
}
static gboolean realized(GSignalInvocationHint *h,guint n,const GValue *v,gpointer data){
 (void)h;(void)data;if(!n||!GTK_IS_WIDGET(g_value_get_object(v)))return TRUE;GtkWidget *w=GTK_WIDGET(g_value_get_object(v));
 if((GTK_IS_IMAGE(w)||GTK_IS_VIEWPORT(w))&&!g_object_get_data(G_OBJECT(w),"f08-native-draw")){g_signal_connect_after(w,"draw",G_CALLBACK(drawn),NULL);g_object_set_data(G_OBJECT(w),"f08-native-draw",GUINT_TO_POINTER(1));}
 if(GTK_IS_WINDOW(w)){GdkFrameClock *clock=gtk_widget_get_frame_clock(w);if(clock&&clock_id(clock)==CLOCKS){if(nc==CLOCKS){overflow++;return TRUE;}unsigned i=nc++;clocks[i]=g_object_ref(clock);g_signal_connect(clock,"before-paint",G_CALLBACK(before),GUINT_TO_POINTER(i));g_signal_connect_after(clock,"after-paint",G_CALLBACK(after),GUINT_TO_POINTER(i));}}return TRUE;
}
static gboolean event(GSignalInvocationHint *h,guint n,const GValue *v,gpointer data){
 (void)h;(void)data;if(!enabled||n<2)return TRUE;GtkWidget *w=GTK_WIDGET(g_value_get_object(v));if(!belongs(w))return TRUE;GdkEvent *e=g_value_get_boxed(v+1);if(!e)return TRUE;Input row={0};row.at=g_get_monotonic_time();row.server_ms=gdk_event_get_time(e);
 if(e->type==GDK_KEY_PRESS){row.type=1;row.code=e->key.keyval;row.hardware=e->key.hardware_keycode;}else if(e->type==GDK_SCROLL){row.type=2;row.code=e->scroll.direction;}else if(e->type==GDK_BUTTON_PRESS){row.type=3;row.code=e->button.button;}else return TRUE;
 if(ni&&inputs[ni-1].server_ms==row.server_ms&&inputs[ni-1].type==row.type&&inputs[ni-1].code==row.code&&inputs[ni-1].hardware==row.hardware)return TRUE;
 if(ni<CAP)inputs[ni++]=row;else overflow++;return TRUE;
}
G_MODULE_EXPORT void gtk_module_init(gint *argc,gchar ***argv){
 (void)argc;(void)argv;if(enabled||!getenv("EXR_F08_NATIVE_OUTPUT"))return;enabled=TRUE;pthread_once(&once,resolve);gpointer klass=g_type_class_ref(GTK_TYPE_WIDGET);guint r=g_signal_lookup("realize",GTK_TYPE_WIDGET),e=g_signal_lookup("event",GTK_TYPE_WIDGET);if(!r||!g_signal_add_emission_hook(r,0,realized,NULL,NULL)||!e||!g_signal_add_emission_hook(e,0,event,NULL,NULL))overflow++;g_type_class_unref(klass);
}
static void quote(FILE *f,const char *s){fputc('"',f);for(const unsigned char *p=(const unsigned char*)(s?s:"");*p;p++){if(*p=='"'||*p=='\\')fputc('\\',f);if(*p<32)fprintf(f,"\\u%04x",*p);else fputc(*p,f);}fputc('"',f);}
__attribute__((destructor)) static void finish(void){
 if(!enabled){return;}enabled=FALSE;char path[4096],exe[4096];ssize_t len=readlink("/proc/self/exe",exe,sizeof(exe)-1);if(len<0)exe[0]=0;else exe[len]=0;
 if(snprintf(path,sizeof(path),"%s/%ld.json",getenv("EXR_F08_NATIVE_OUTPUT"),(long)getpid())>=(int)sizeof(path)){return;}FILE *f=fopen(path,"wx");if(!f){perror("native cost output");return;}
 fprintf(f,"{\"schema\":1,\"pid\":%ld,\"source\":",(long)getpid());quote(f,getenv("GITHUB_SHA"));fputs(",\"run\":",f);quote(f,getenv("GITHUB_RUN_ID"));fputs(",\"attempt\":",f);quote(f,getenv("GITHUB_RUN_ATTEMPT"));fputs(",\"executable\":",f);quote(f,exe);fprintf(f,",\"overflow\":%u,\"capacity\":%u,\"clock_count\":%u,\"queue_observed\":%s,\"probe_static_bytes\":%zu,\"jobs\":[",overflow,CAP,nc,owner?"true":"false",sizeof(jobs)+sizeof(inputs)+sizeof(frames)+sizeof(pending));
 for(unsigned i=0;i<nj;i++){Job *j=&jobs[i];fprintf(f,"%s{\"id\":%u,\"action\":%d,\"input\":%d,\"queued\":%lld,\"start\":%lld,\"worker_end\":%lld,\"apply_start\":%lld,\"apply_end\":%lld,\"image_at\":%lld,\"draw_end\":%lld,\"complete\":%lld,\"page\":%d,\"shelf\":%d,\"shelf_visible\":%d,\"superseded\":%d,\"generation\":%lld,\"frame_generation\":%lld,\"shelf_generation\":%lld,\"book\":%lld,\"page_number\":%lld,\"font\":%lld,\"clock\":%u,\"counter\":%lld}",i?",":"",i+1,j->action,j->input,(long long)j->queued,(long long)j->start,(long long)j->worker_end,(long long)j->apply_start,(long long)j->apply_end,(long long)j->image_at,(long long)j->draw_end,(long long)j->complete,j->page,j->shelf,j->shelf_visible,j->superseded,(long long)j->generation,(long long)j->frame_generation,(long long)j->shelf_generation,(long long)j->book,(long long)j->page_number,(long long)j->font,j->clock,(long long)j->counter);}
 fputs("],\"inputs\":[",f);for(unsigned i=0;i<ni;i++){Input *r=&inputs[i];fprintf(f,"%s{\"id\":%u,\"at\":%lld,\"server_ms\":%u,\"type\":%u,\"code\":%u,\"hardware\":%u}",i?",":"",i+1,(long long)r->at,r->server_ms,r->type,r->code,r->hardware);}
 fputs("],\"frames\":[",f);for(unsigned i=0;i<nf;i++){Frame *r=&frames[i];fprintf(f,"%s{\"id\":%u,\"clock\":%u,\"counter\":%lld,\"gdk_frame_start\":%lld,\"animation_frame_time\":%lld,\"before\":%lld,\"draw_end\":%lld,\"sync_start\":%lld,\"sync_end\":%lld,\"native_error\":%d,\"kind\":%u,\"page_job\":%u,\"shelf_job\":%u,\"input\":%u,\"frame_generation\":%lld,\"shelf_restoring\":%d,\"shelf_content\":{\"available\":%s,\"top_id\":%lld,\"index\":%d,\"scroll\":%.17g}",i?",":"",i+1,r->clock,(long long)r->counter,(long long)r->gdk_frame_start,(long long)r->animation_frame_time,(long long)r->before,(long long)r->draw_end,(long long)r->sync_start,(long long)r->sync_end,r->native_error,r->kind,r->page_job,r->shelf_job,r->input,(long long)r->frame_generation,r->shelf_restoring,r->content.available?"true":"false",(long long)r->content.top_id,r->content.index,r->content.scroll);fprintf(f,",\"body\":{\"available\":%s,\"scroll\":%.17g,\"x\":%d,\"y\":%d,\"width\":%d,\"height\":%d}}",r->body_available?"true":"false",r->body_scroll,r->body_x,r->body_y,r->body_width,r->body_height);}
 fputs("]}\n",f);int error=ferror(f);if(fclose(f)!=0||error)fputs("native cost flush failed\n",stderr);
}
