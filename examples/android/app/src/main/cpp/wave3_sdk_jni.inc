/* SPDX-License-Identifier: MIT */
/* Included in the existing SDK owner library after the common JNI helpers. It only
   adapts the reviewed font-library and original-export packages: no second parser,
   SDK, thread or library. Every call runs on the existing host worker. */
#include <reader_font_library.h>
#include <reader_original_export.h>
#include <pthread.h>

static volatile int wave3_live_leases = 0;

typedef struct {JNIEnv *env;jobject task;jmethodID check;jclass cancelled;} wave3_control;
static int wave3_control_init(JNIEnv *env,jobject task,wave3_control *control) {
  jclass type;
  control->env=env;control->task=task;control->check=NULL;control->cancelled=NULL;
  if(!task) return 0;
  type=(*env)->GetObjectClass(env,task);if(!type) return 0;
  control->check=(*env)->GetMethodID(env,type,"check","()V");(*env)->DeleteLocalRef(env,type);
  if(!control->check) return 0;
  control->cancelled=(*env)->FindClass(env,"org/exreader/host/HostTask$Cancelled");
  return control->cancelled!=NULL;
}
/* Receipts must survive cooperative cancellation. Inspect only after clearing the
   pending exception; every other Java failure is restored unchanged. */
static int wave3_receipt_exception(wave3_control *control) {
  JNIEnv *env=control->env;jthrowable thrown;jboolean cancelled;
  if(!(*env)->ExceptionCheck(env)) return 1;
  thrown=(*env)->ExceptionOccurred(env);(*env)->ExceptionClear(env);
  cancelled=(*env)->IsInstanceOf(env,thrown,control->cancelled);
  if(!cancelled) (*env)->Throw(env,thrown);
  (*env)->DeleteLocalRef(env,thrown);
  return cancelled?1:0;
}
static int wave3_cancelled(wave3_control *control) {
  if((*control->env)->ExceptionCheck(control->env)) return 1;
  (*control->env)->CallVoidMethod(control->env,control->task,control->check);
  return (*control->env)->ExceptionCheck(control->env)?1:0;
}
static void wave3_throw(JNIEnv *env,const char *type_name,const char *message) {
  jclass type;
  if((*env)->ExceptionCheck(env)) return;
  type=(*env)->FindClass(env,type_name);if(!type) return;
  (*env)->ThrowNew(env,type,message);(*env)->DeleteLocalRef(env,type);
}

/* ---- local font library ---------------------------------------------------- */
static void wave3_font_fail(JNIEnv *env,rfl_status status,const rfl_error *error,const char *fallback) {
  char message[256];
  snprintf(message,sizeof(message),"%s (font %d)",error&&error->message[0]?error->message:fallback,(int)status);
  wave3_throw(env,"java/lang/IllegalStateException",message);
}
JNIEXPORT jlong JNICALL Java_org_exreader_host_NativeFonts_open0(JNIEnv *env,jclass type,jstring directory) {
  char *path=input_string(env,directory);rfl_library *opened=NULL;rfl_error error={0};rfl_status status;(void)type;
  if(!path) return 0;
  status=rfl_open(path,NULL,&opened,&error);free(path);
  if(status!=RFL_OK) {wave3_font_fail(env,status,&error,"Cannot open the local font library");return 0;}
  return (jlong)(intptr_t)opened;
}
/* Returns the module status; BUSY means a layout still holds a lease. */
JNIEXPORT jint JNICALL Java_org_exreader_host_NativeFonts_close(JNIEnv *env,jclass type,jlong handle) {
  rfl_library *library_handle=(rfl_library *)(intptr_t)handle;rfl_error error={0};(void)env;(void)type;
  if(!library_handle) return RFL_ARGUMENT;
  return (jint)rfl_close(library_handle,&error);
}
JNIEXPORT jobjectArray JNICALL Java_org_exreader_host_NativeFonts_list(JNIEnv *env,jclass type,jlong handle) {
  rfl_library *library_handle=(rfl_library *)(intptr_t)handle;rfl_error error={0};size_t count=0,i;rfl_status status;jobjectArray rows;(void)type;
  if(!library_handle) {wave3_throw(env,"java/lang/IllegalStateException","Font library is closed");return NULL;}
  status=rfl_count(library_handle,&count,&error);
  if(status!=RFL_OK) {wave3_font_fail(env,status,&error,"Cannot count local fonts");return NULL;}
  if(count>1024) {wave3_throw(env,"java/lang/IllegalStateException","Too many local fonts");return NULL;}
  rows=new_rows(env,(jsize)count);if(!rows) return NULL;
  for(i=0;i<count;i++) {
    rfl_record record;jobjectArray row;
    memset(&record,0,sizeof(record));
    status=rfl_get(library_handle,i,&record,&error);
    if(status!=RFL_OK) {wave3_font_fail(env,status,&error,"Cannot read a local font");return NULL;}
    row=new_row(env,3);if(!row) return NULL;
    if(!set_cell(env,row,0,record.hash)||!set_cell(env,row,1,record.display_name)||!set_number(env,row,2,(long long)record.bytes)) {(*env)->DeleteLocalRef(env,row);return NULL;}
    (*env)->SetObjectArrayElement(env,rows,(jsize)i,row);(*env)->DeleteLocalRef(env,row);
    if((*env)->ExceptionCheck(env)) return NULL;
  }
  return rows;
}
static int wave3_font_progress(void *context,const char *stage,uint64_t done,uint64_t total) {
  (void)stage;(void)done;(void)total;
  return wave3_cancelled((wave3_control *)context);
}
/* [status, created, hash, name, bytes, message]; cancellation before the manifest commit throws the task's exception. */
JNIEXPORT jobjectArray JNICALL Java_org_exreader_host_NativeFonts_importFile(JNIEnv *env,jclass type,jlong handle,jstring path,jstring name,jobject task) {
  rfl_library *library_handle=(rfl_library *)(intptr_t)handle;char *file=NULL,*label=NULL;rfl_record record;rfl_error error={0};int created=0;rfl_status status;
  wave3_control control;rfl_control callbacks;jobjectArray row=NULL;(void)type;
  memset(&record,0,sizeof(record));
  if(!library_handle||!wave3_control_init(env,task,&control)) {wave3_throw(env,"java/lang/IllegalStateException","Font library is closed");return NULL;}
  file=input_string(env,path);label=file?input_string(env,name):NULL;
  if(!file||!label) {free(file);free(label);return NULL;}
  callbacks.progress=wave3_font_progress;callbacks.context=&control;
  status=rfl_import_file(library_handle,file,label,&callbacks,&record,&created,&error);
  free(file);free(label);
  if((status==RFL_OK||status==RFL_COMMIT_UNCERTAIN)&&!wave3_receipt_exception(&control)) return NULL;
  if((*env)->ExceptionCheck(env)) return NULL;
  row=new_row(env,6);if(!row) return NULL;
  if(!set_number(env,row,0,(long long)status)||!set_number(env,row,1,created)||!set_cell(env,row,2,record.hash)||!set_cell(env,row,3,record.display_name)||!set_number(env,row,4,(long long)record.bytes)||!set_cell(env,row,5,error.message)) return NULL;
  return row;
}
JNIEXPORT jobjectArray JNICALL Java_org_exreader_host_NativeFonts_remove(JNIEnv *env,jclass type,jlong handle,jstring hash) {
  rfl_library *library_handle=(rfl_library *)(intptr_t)handle;char *value=NULL;rfl_error error={0};rfl_status status;jobjectArray row;(void)type;
  if(!library_handle) {wave3_throw(env,"java/lang/IllegalStateException","Font library is closed");return NULL;}
  value=input_string(env,hash);if(!value) return NULL;
  status=rfl_remove(library_handle,value,&error);free(value);
  row=new_row(env,2);if(!row) return NULL;
  if(!set_number(env,row,0,(long long)status)||!set_cell(env,row,1,error.message)) return NULL;
  return row;
}
/* Opens a lease only to prove the stored face is usable; the paging path opens its own lease. */
JNIEXPORT jint JNICALL Java_org_exreader_host_NativeFonts_liveLeases(JNIEnv *env,jclass type) {
  (void)env;(void)type;return (jint)__atomic_load_n(&wave3_live_leases,__ATOMIC_SEQ_CST);
}
JNIEXPORT jint JNICALL Java_org_exreader_host_NativeFonts_probe(JNIEnv *env,jclass type,jlong handle,jstring hash) {
  rfl_library *library_handle=(rfl_library *)(intptr_t)handle;char *value=input_string(env,hash);rfl_lease *lease=NULL;rfl_error error={0};exr_font *font=NULL;rfl_status status;(void)type;
  if(!library_handle||!value) {free(value);return RFL_ARGUMENT;}
  status=rfl_font_open(library_handle,value,0,&lease,&error);free(value);
  if(status!=RFL_OK) return (jint)status;
  status=rfl_lease_font(lease,&font,&error);
  if(status==RFL_OK&&!font) status=RFL_FONT;
  {rfl_status released=rfl_lease_release(lease,&error);if(status==RFL_OK) status=released;}
  return (jint)status;
}

/* The paging path owns its lease: it is released with the pager, after every layout. */
static exr_status host_lease_font(JNIEnv *env,jlong library_handle,jstring hash,exr_font **font,void **lease_out,exr_error *error) {
  char *value=input_string(env,hash);rfl_lease *lease=NULL;rfl_error local={0};rfl_status status;
  if(!library_handle||!value) {free(value);return EXR_ARGUMENT;}
  status=rfl_font_open((rfl_library *)(intptr_t)library_handle,value,0,&lease,&local);free(value);
  if(status!=RFL_OK) {snprintf(error->message,sizeof(error->message),"Local font cannot be opened (font %d)",(int)status);return EXR_IO;}
  status=rfl_lease_font(lease,font,&local);
  if(status!=RFL_OK||!*font) {rfl_lease_release(lease,&local);*font=NULL;snprintf(error->message,sizeof(error->message),"Local font lease has no font (font %d)",(int)status);return EXR_IO;}
  __atomic_add_fetch(&wave3_live_leases,1,__ATOMIC_SEQ_CST);*lease_out=lease;return EXR_OK;
}
static void host_release_lease(void *lease) {
  rfl_error error={0};
  if(!lease) return;
  rfl_lease_release((rfl_lease *)lease,&error);__atomic_sub_fetch(&wave3_live_leases,1,__ATOMIC_SEQ_CST);
}

/* ---- original export ------------------------------------------------------- */
typedef struct {pthread_t owner;wave3_control control;} wave3_export;
static int wave3_export_enter(void *context) {return pthread_equal(((wave3_export *)context)->owner,pthread_self())?0:1;}
static void wave3_export_leave(void *context) {(void)context;}
static int wave3_export_cancelled(void *context) {return wave3_cancelled(&((wave3_export *)context)->control);}
static void wave3_export_progress(void *context,size_t index,roe_event event,const roe_item *item) {(void)context;(void)index;(void)event;(void)item;}
/* Row 0: [batch status, count]; then one row per selected book with its own receipt. */
JNIEXPORT jobjectArray JNICALL Java_org_exreader_host_NativeOriginalExport_run(JNIEnv *env,jclass type,jlong handle,jlongArray books,jstring directory,jobject task) {
  exr_library *store=library(env,handle);wave3_export state;roe_owner owner;roe_exporter *exporter=NULL;roe_selection selection[ROE_MAX_ITEMS];roe_options options;roe_result *result=NULL;
  roe_status status;jsize count;jlong ids[ROE_MAX_ITEMS];char *path=NULL;jobjectArray rows=NULL;size_t i;(void)type;
  if(!store||!books) return NULL;
  count=(*env)->GetArrayLength(env,books);
  if(count<1||count>(jsize)ROE_MAX_ITEMS) {throw_argument(env,"Original export needs 1..100 explicit books");return NULL;}
  (*env)->GetLongArrayRegion(env,books,0,count,ids);if((*env)->ExceptionCheck(env)) return NULL;
  if(!wave3_control_init(env,task,&state.control)) return NULL;
  path=input_string(env,directory);if(!path) return NULL;
  state.owner=pthread_self();owner.enter=wave3_export_enter;owner.leave=wave3_export_leave;owner.context=&state;
  memset(selection,0,sizeof(selection));memset(&options,0,sizeof(options));
  for(i=0;i<(size_t)count;i++) {selection[i].book_id=(int64_t)ids[i];selection[i].display_name=NULL;}
  options.directory=path;options.naming=ROE_HASH_NAME;options.callbacks.cancelled=wave3_export_cancelled;options.callbacks.progress=wave3_export_progress;options.callbacks.context=&state;
  status=roe_create(store,&owner,&exporter);
  if(status!=ROE_OK) {free(path);wave3_throw(env,"java/lang/IllegalStateException","Original exporter cannot be created for this library");return NULL;}
  status=roe_run(exporter,selection,(size_t)count,&options,&result);
  free(path);
  {roe_status destroyed=roe_destroy(&exporter);(void)destroyed;}
  if(!wave3_receipt_exception(&state.control)) {roe_result_free(result);return NULL;}
  if(!result) {if(!(*env)->ExceptionCheck(env)) wave3_throw(env,"java/lang/IllegalStateException","Original export produced no receipt");return NULL;}
  rows=new_rows(env,(jsize)(result->count+1));
  if(rows) {
    jobjectArray head=new_row(env,2);
    if(head&&set_number(env,head,0,(long long)status)&&set_number(env,head,1,(long long)result->count)) (*env)->SetObjectArrayElement(env,rows,0,head);
    else rows=NULL;
    if(head) (*env)->DeleteLocalRef(env,head);
    if((*env)->ExceptionCheck(env)) rows=NULL;
  }
  for(i=0;rows&&i<result->count;i++) {
    const roe_item *item=&result->items[i];jobjectArray row=new_row(env,12);
    if(!row) {rows=NULL;break;}
    if(!set_number(env,row,0,(long long)item->book_id)||!set_number(env,row,1,(long long)item->status)||!set_number(env,row,2,(long long)item->sdk_status)||
       !set_number(env,row,3,item->committed)||!set_number(env,row,4,item->created)||!set_number(env,row,5,item->durable)||!set_number(env,row,6,item->cleanup_pending)||
       !set_number(env,row,7,(long long)item->format)||!set_number(env,row,8,(long long)item->bytes)||!set_cell(env,row,9,item->original_sha256)||
       !set_cell(env,row,10,item->output_path)||!set_cell(env,row,11,item->cleanup_path)) {(*env)->DeleteLocalRef(env,row);rows=NULL;break;}
    (*env)->SetObjectArrayElement(env,rows,(jsize)(i+1),row);(*env)->DeleteLocalRef(env,row);
    if((*env)->ExceptionCheck(env)) {rows=NULL;break;}
  }
  roe_result_free(result);
  if((*env)->ExceptionCheck(env)) return NULL;
  return rows;
}
