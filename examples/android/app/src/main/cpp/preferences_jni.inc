/* SPDX-License-Identifier: MIT */
/* Installed F3 only. No SDK/product database or new owner is introduced. */
#include <reader_preferences.h>

static void preferences_error(JNIEnv *env,reader_preferences_status status,const reader_preferences_error *error){
  char message[384];jclass type;if((*env)->ExceptionCheck(env))return;
  snprintf(message,sizeof(message),"Reading settings %s: %s",reader_preferences_status_name(status),error->message);
  type=(*env)->FindClass(env,"java/lang/IllegalArgumentException");if(type){(*env)->ThrowNew(env,type,message);(*env)->DeleteLocalRef(env,type);}
}
static jobject preferences_value(JNIEnv *env,const reader_preferences *p){
  jfloat n[4]={p->font_size,p->line_spacing,p->paragraph_spacing,p->margin};
  jint c[4]={(jint)p->theme,(jint)p->page_turn_direction,(jint)p->page_turn_input,(jint)p->fixed_page_zoom};
  jbyte colors[16];jfloatArray numbers=NULL;jintArray choices=NULL;jbyteArray palette=NULL;jobject result=NULL;jclass type=NULL;jmethodID ctor;
  memcpy(colors,p->light_foreground,4);memcpy(colors+4,p->light_background,4);memcpy(colors+8,p->dark_foreground,4);memcpy(colors+12,p->dark_background,4);
  numbers=(*env)->NewFloatArray(env,4);choices=(*env)->NewIntArray(env,4);palette=(*env)->NewByteArray(env,16);
  if(!numbers||!choices||!palette)goto done;
  (*env)->SetFloatArrayRegion(env,numbers,0,4,n);(*env)->SetIntArrayRegion(env,choices,0,4,c);(*env)->SetByteArrayRegion(env,palette,0,16,colors);
  type=(*env)->FindClass(env,"org/exreader/host/ReadingPreferences");if(!type)goto done;
  ctor=(*env)->GetMethodID(env,type,"<init>","([F[I[B)V");if(ctor)result=(*env)->NewObject(env,type,ctor,numbers,choices,palette);
done:
  if(type)(*env)->DeleteLocalRef(env,type);if(numbers)(*env)->DeleteLocalRef(env,numbers);if(choices)(*env)->DeleteLocalRef(env,choices);if(palette)(*env)->DeleteLocalRef(env,palette);return result;
}
static int preferences_input(JNIEnv *env,jobject value,reader_preferences *p){
  jclass type=NULL;jmethodID method;jfloatArray numbers=NULL;jintArray choices=NULL;jbyteArray palette=NULL;jfloat n[4];jint c[4];jbyte colors[16];reader_preferences_error error={0};reader_preferences_status status;
  if(!value){throw_argument(env,"Settings value is required");return 0;}*p=reader_preferences_defaults();type=(*env)->GetObjectClass(env,value);if(!type)return 0;
  method=(*env)->GetMethodID(env,type,"numbers","()[F");if(method)numbers=(*env)->CallObjectMethod(env,value,method);
  method=(*env)->GetMethodID(env,type,"choices","()[I");if(method)choices=(*env)->CallObjectMethod(env,value,method);
  method=(*env)->GetMethodID(env,type,"colors","()[B");if(method)palette=(*env)->CallObjectMethod(env,value,method);
  if((*env)->ExceptionCheck(env))goto done;
  if(!numbers||!choices||!palette||(*env)->GetArrayLength(env,numbers)!=4||(*env)->GetArrayLength(env,choices)!=4||(*env)->GetArrayLength(env,palette)!=16){throw_argument(env,"Incomplete settings arrays");goto done;}
  (*env)->GetFloatArrayRegion(env,numbers,0,4,n);(*env)->GetIntArrayRegion(env,choices,0,4,c);(*env)->GetByteArrayRegion(env,palette,0,16,colors);
  p->font_size=n[0];p->line_spacing=n[1];p->paragraph_spacing=n[2];p->margin=n[3];p->theme=(uint32_t)c[0];p->page_turn_direction=(uint32_t)c[1];p->page_turn_input=(uint32_t)c[2];p->fixed_page_zoom=(uint32_t)c[3];
  memcpy(p->light_foreground,colors,4);memcpy(p->light_background,colors+4,4);memcpy(p->dark_foreground,colors+8,4);memcpy(p->dark_background,colors+12,4);
done:
  if(type)(*env)->DeleteLocalRef(env,type);if(numbers)(*env)->DeleteLocalRef(env,numbers);if(choices)(*env)->DeleteLocalRef(env,choices);if(palette)(*env)->DeleteLocalRef(env,palette);
  if((*env)->ExceptionCheck(env))return 0;status=reader_preferences_validate(p,&error);if(status!=READER_PREFERENCES_OK){preferences_error(env,status,&error);return 0;}return 1;
}
JNIEXPORT jobject JNICALL Java_org_exreader_host_NativePreferences_defaults(JNIEnv *env,jclass type){reader_preferences p=reader_preferences_defaults();(void)type;return preferences_value(env,&p);}
JNIEXPORT jobject JNICALL Java_org_exreader_host_NativePreferences_importLegacy(JNIEnv *env,jclass type,jfloat font,jint zoom,jint present){
  reader_preferences p=reader_preferences_defaults();reader_preferences_legacy old={0};reader_preferences_error error={0};reader_preferences_status status;(void)type;
  old.struct_size=sizeof(old);if(present&1)old.present|=READER_PREFERENCES_LEGACY_FONT_SIZE;if(present&2)old.present|=READER_PREFERENCES_LEGACY_FIXED_ZOOM;old.font_size=font;old.fixed_page_zoom=(uint32_t)zoom;
  if(present&~3){throw_argument(env,"Unknown host legacy settings bit");return NULL;}status=reader_preferences_import_legacy(&p,&old,NULL,&error);if(status!=READER_PREFERENCES_OK){preferences_error(env,status,&error);return NULL;}return preferences_value(env,&p);
}
JNIEXPORT jobject JNICALL Java_org_exreader_host_NativePreferences_load(JNIEnv *env,jclass type,jstring file,jobject task){
  reader_preferences p=reader_preferences_defaults();reader_preferences_load_options options={0};reader_preferences_error error={0};reader_preferences_status status;char *path=input_string(env,file);host_control context;exr_control control;(void)type;
  if(!path||!task){free(path);throw_argument(env,"Settings path/control required");return NULL;}control=host_task_control(env,task,&context);options.struct_size=sizeof(options);options.control.cancelled=control.cancelled;options.control.context=control.context;
  status=reader_preferences_load(path,&p,&options,&error);free(path);if(status!=READER_PREFERENCES_OK){preferences_error(env,status,&error);return NULL;}return preferences_value(env,&p);
}
JNIEXPORT void JNICALL Java_org_exreader_host_NativePreferences_validate(JNIEnv *env,jclass type,jobject value){reader_preferences p;(void)type;preferences_input(env,value,&p);}
JNIEXPORT void JNICALL Java_org_exreader_host_NativePreferences_save(JNIEnv *env,jclass type,jobject value,jstring file,jobject task){
  reader_preferences p;reader_preferences_save_options options={0};reader_preferences_error error={0};reader_preferences_status status;char *path;host_control context;exr_control control;(void)type;
  if(!preferences_input(env,value,&p))return;path=input_string(env,file);if(!path||!task){free(path);throw_argument(env,"Settings path/control required");return;}control=host_task_control(env,task,&context);options.struct_size=sizeof(options);options.control.cancelled=control.cancelled;options.control.context=control.context;
  status=reader_preferences_save(&p,path,&options,&error);free(path);if(status!=READER_PREFERENCES_OK)preferences_error(env,status,&error);
}
JNIEXPORT jint JNICALL Java_org_exreader_host_NativePreferences_effectiveTheme(JNIEnv *env,jclass type,jobject value,jint system){reader_preferences p;(void)type;if(!preferences_input(env,value,&p))return 0;return (jint)reader_preferences_effective_theme(&p,(reader_preferences_theme)system);}
