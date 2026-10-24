/* SPDX-License-Identifier: MIT */
/* Only the installed public SDK/sideload APIs. No product/network dependency. */
#include <exr_sideload.h>
#include <jni.h>
#include <pthread.h>
#include <stdlib.h>
#include <stdio.h>
#include <string.h>
#include <stdint.h>
typedef struct {exr_library *library;pthread_t owner;} sdk_owner;
static sdk_owner *owned(JNIEnv *env,jlong token){
  sdk_owner *owner=(sdk_owner *)(intptr_t)token;
  if(!owner||!pthread_equal(owner->owner,pthread_self())){
    jclass error=(*env)->FindClass(env,"java/lang/IllegalStateException");
    if(error)(*env)->ThrowNew(env,error,"SDK operation requires its owner queue");
    return NULL;
  }
  return owner;
}
JNIEXPORT jlong JNICALL Java_org_exreader_sessionprobe_NativeSdk_open(JNIEnv *env,jclass type,jstring path){
  const char *text=(*env)->GetStringUTFChars(env,path,NULL);sdk_owner *owner;exr_error error={0};(void)type;
  if(!text)return 0;
  owner=calloc(1,sizeof(*owner));
  if(owner){owner->owner=pthread_self();if(exr_library_open(text,&owner->library,&error)!=EXR_OK){free(owner);owner=NULL;}}
  (*env)->ReleaseStringUTFChars(env,path,text);return (jlong)(intptr_t)owner;
}
JNIEXPORT jlongArray JNICALL Java_org_exreader_sessionprobe_NativeSdk_importFile(JNIEnv *env,jclass type,jlong token,jstring path,jint format){
  sdk_owner *owner=owned(env,token);const char *text;exr_sideload_result result={0};exr_error error={0};jlong values[3];jlongArray out;(void)type;
  if(!owner)return NULL;
  text=(*env)->GetStringUTFChars(env,path,NULL);if(!text)return NULL;result.struct_size=sizeof(result);
  values[0]=exr_sideload_import_file(owner->library,(exr_format)format,text,NULL,NULL,&result,&error);values[1]=result.book_id;values[2]=result.created;
  (*env)->ReleaseStringUTFChars(env,path,text);out=(*env)->NewLongArray(env,3);if(out)(*env)->SetLongArrayRegion(env,out,0,3,values);return out;
}
typedef struct {uint64_t cancel_at,received;} export_control;
static int cancelled(void *context){export_control *control=context;return control->received>=control->cancel_at;}
static void progress(void *context,exr_stage stage,uint64_t received,uint64_t total){(void)stage;(void)total;((export_control *)context)->received=received;}
JNIEXPORT jobjectArray JNICALL Java_org_exreader_sessionprobe_NativeSdk_exportOriginal(JNIEnv *env,jclass type,jlong token,jlong book,jstring path,jlong cancel_at,jlong maximum){
  sdk_owner *owner=owned(env,token);const char *text;exr_sideload_options options={0};exr_error error={0};export_control control={(uint64_t)cancel_at,0};uint64_t bytes=0;
  char code[24],length[32];exr_status status;jclass string_type;jobjectArray out;(void)type;
  if(!owner)return NULL;
  text=(*env)->GetStringUTFChars(env,path,NULL);if(!text)return NULL;
  options.struct_size=sizeof(options);options.max_input_bytes=(uint64_t)maximum;options.control=(exr_control){cancelled,progress,&control};
  status=exr_sideload_export_original(owner->library,(int64_t)book,text,&options,&bytes,&error);
  (*env)->ReleaseStringUTFChars(env,path,text);snprintf(code,sizeof(code),"%d",status);snprintf(length,sizeof(length),"%llu",(unsigned long long)bytes);
  string_type=(*env)->FindClass(env,"java/lang/String");if(!string_type)return NULL;out=(*env)->NewObjectArray(env,3,string_type,NULL);
  if(out){(*env)->SetObjectArrayElement(env,out,0,(*env)->NewStringUTF(env,code));(*env)->SetObjectArrayElement(env,out,1,(*env)->NewStringUTF(env,length));(*env)->SetObjectArrayElement(env,out,2,(*env)->NewStringUTF(env,error.message));}return out;
}
JNIEXPORT void JNICALL Java_org_exreader_sessionprobe_NativeSdk_close(JNIEnv *env,jclass type,jlong token){sdk_owner *owner=owned(env,token);(void)type;if(owner){exr_library_close(owner->library);free(owner);}}
