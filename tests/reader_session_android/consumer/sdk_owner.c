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
/* The acceptance app has no live pager. Exercise the public document/source
   release, durable point, write, reopen and resolve sequence on the SDK owner. */
JNIEXPORT jlongArray JNICALL Java_org_exreader_sessionprobe_NativeSdk_reopenAfterImport(JNIEnv *env,jclass type,jlong token,jlong old_book,jstring path,jint format,jboolean cancel){
  sdk_owner *owner=owned(env,token);exr_document *document=NULL;exr_source source={0};exr_anchor point={0},saved={0};exr_anchor_state saved_state=EXR_ANCHOR_MISSING;exr_anchor_match match={0};exr_error error={0};
  exr_sideload_options options={0};exr_sideload_result imported={0};export_control control={0,0};const char *text=NULL;size_t size=0;unsigned char first=0;jlong values[6]={-1,0,0,0,0,0};jlongArray out;(void)type;
  if(!owner)return NULL;
  if(exr_library_document(owner->library,old_book,&document,&error)!=EXR_OK)goto done;
  exr_document_text(document,&size);if(size<9||exr_anchor_create(document,8,8,&point,&error)!=EXR_OK)goto done;
  exr_document_free(document);document=NULL;
  if(exr_library_source(owner->library,old_book,&source,&error)!=EXR_OK)goto done;
  if(source.read_at(source.context,0,&first,1)!=1)goto done;
  source.release(source.context);memset(&source,0,sizeof(source));
  if(exr_library_progress(owner->library,old_book,&point,&error)!=EXR_OK)goto done;
  exr_anchor_free(&point);
  /* No SDK document, pager or source survives the write below. */
  text=(*env)->GetStringUTFChars(env,path,NULL);if(!text)goto done;
  options.struct_size=sizeof(options);if(cancel)options.control=(exr_control){cancelled,progress,&control};imported.struct_size=sizeof(imported);
  values[0]=exr_sideload_import_file(owner->library,(exr_format)format,text,NULL,&options,&imported,&error);values[1]=imported.book_id;
  (*env)->ReleaseStringUTFChars(env,path,text);text=NULL;
  if(exr_library_progress_get(owner->library,old_book,&saved,&saved_state,&error)!=EXR_OK||exr_library_document(owner->library,old_book,&document,&error)!=EXR_OK)goto done;
  if(exr_anchor_resolve(document,&saved,&match,&error)!=EXR_OK)goto done;
  values[2]=match.state;values[3]=(jlong)match.start;
  {const char *continued=exr_document_text(document,&size);values[4]=continued&&match.state==EXR_ANCHOR_FOUND&&match.start<size&&continued[match.start]=='i';}
  if(exr_library_source(owner->library,old_book,&source,&error)!=EXR_OK)goto done;
  values[5]=source.read_at(source.context,0,&first,1)==1&&first=='a';
done:
  if(text)(*env)->ReleaseStringUTFChars(env,path,text);
  if(source.release)source.release(source.context);
  exr_document_free(document);exr_anchor_free(&point);exr_anchor_free(&saved);
  out=(*env)->NewLongArray(env,6);if(out)(*env)->SetLongArrayRegion(env,out,0,6,values);return out;
}
JNIEXPORT jobjectArray JNICALL Java_org_exreader_sessionprobe_NativeSdk_inspect(JNIEnv *env,jclass type,jlong token,jlong book){
  sdk_owner *owner=owned(env,token);exr_book *books=NULL;size_t count=0,i;exr_error error={0};jobjectArray out=NULL;jclass byte_array;(void)type;
  if(!owner||exr_library_books(owner->library,NULL,&books,&count,&error)!=EXR_OK)return NULL;
  byte_array=(*env)->FindClass(env,"[B");
  for(i=0;byte_array&&i<count;i++)if(books[i].id==(int64_t)book){
    exr_library_epub_info info={0};exr_source source={0};char position[32],favorite[24],format[24],bounded[24],total[32],length[32];const char *fields[8];size_t n;
    info.struct_size=sizeof(info);if(books[i].format==EXR_EPUB)exr_library_epub_info_get(owner->library,book,&info,&error);
    if(exr_library_source(owner->library,book,&source,&error)!=EXR_OK)break;
    snprintf(position,sizeof(position),"%llu",(unsigned long long)books[i].position);snprintf(favorite,sizeof(favorite),"%d",books[i].favorite);snprintf(format,sizeof(format),"%d",books[i].format);snprintf(bounded,sizeof(bounded),"%d",info.bounded_storage);snprintf(total,sizeof(total),"%llu",(unsigned long long)count);snprintf(length,sizeof(length),"%llu",(unsigned long long)source.size);
    source.release(source.context);fields[0]=books[i].title?books[i].title:"";fields[1]=books[i].author?books[i].author:"";fields[2]=position;fields[3]=favorite;fields[4]=format;fields[5]=bounded;fields[6]=total;fields[7]=length;
    out=(*env)->NewObjectArray(env,8,byte_array,NULL);
    for(n=0;out&&n<8;n++){size_t size=strlen(fields[n]);jbyteArray bytes=(*env)->NewByteArray(env,(jsize)size);if(!bytes)break;(*env)->SetByteArrayRegion(env,bytes,0,(jsize)size,(const jbyte *)fields[n]);(*env)->SetObjectArrayElement(env,out,(jsize)n,bytes);(*env)->DeleteLocalRef(env,bytes);}
    break;
  }
  exr_books_free(books,count);return out;
}
