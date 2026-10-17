/* SPDX-License-Identifier: GPL-3.0-only */
#include <jni.h>
#include <exreader.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <limits.h>
static void argument(JNIEnv *env,const char *message) {
  jclass cls=(*env)->FindClass(env,"java/lang/IllegalArgumentException"); if(cls) { (*env)->ThrowNew(env,cls,message); (*env)->DeleteLocalRef(env,cls); }
}
static void engine_error(JNIEnv *env,exr_status status,const exr_error *error) {
  jclass cls; jmethodID constructor; jstring message; jobject exception; jchar chars[256]; size_t i=0,n=0,len;
  const unsigned char *bytes=(const unsigned char *)(error && error->message[0] ? error->message : "Native engine failed");
  if((*env)->ExceptionCheck(env)) return;
  len=strlen((const char *)bytes);
  while(i<len && n<256) {
    uint32_t cp=bytes[i++],minimum=0; unsigned need=0,k;
    if(cp>=0xc2 && cp<=0xdf) { cp&=31; need=1; minimum=0x80; }
    else if(cp>=0xe0 && cp<=0xef) { cp&=15; need=2; minimum=0x800; }
    else if(cp>=0xf0 && cp<=0xf4) { cp&=7; need=3; minimum=0x10000; }
    else if(cp>=128) cp=0xfffd;
    if(need) {
      if(need>len-i) { cp=0xfffd; need=0; }
      for(k=0;k<need;k++) { unsigned b=bytes[i++]; if((b&0xc0)!=0x80) { cp=0xfffd; break; } cp=(cp<<6)|(b&63); }
      if(cp<minimum || cp>0x10ffff || (cp>=0xd800 && cp<=0xdfff)) cp=0xfffd;
    }
    if(cp>=0x10000) { if(n+2>256) break; cp-=0x10000; chars[n++]=(jchar)(0xd800+(cp>>10)); chars[n++]=(jchar)(0xdc00+(cp&1023)); }
    else chars[n++]=(jchar)cp;
  }
  cls=(*env)->FindClass(env,"org/exreader/EXReaderException"); if(!cls) return;
  constructor=(*env)->GetMethodID(env,cls,"<init>","(ILjava/lang/String;)V"); if(!constructor) { (*env)->DeleteLocalRef(env,cls); return; }
  message=(*env)->NewString(env,chars,(jsize)n); if(!message) { (*env)->DeleteLocalRef(env,cls); return; }
  exception=(*env)->NewObject(env,cls,constructor,(jint)status,message);
  if(exception && !(*env)->ExceptionCheck(env)) (*env)->Throw(env,(jthrowable)exception);
  if(exception) (*env)->DeleteLocalRef(env,exception);
  (*env)->DeleteLocalRef(env,message); (*env)->DeleteLocalRef(env,cls);
}
static void *pointer(JNIEnv *env,jlong handle) {
  if(!handle) { jclass cls=(*env)->FindClass(env,"java/lang/IllegalStateException"); if(cls) { (*env)->ThrowNew(env,cls,"Native handle is closed"); (*env)->DeleteLocalRef(env,cls); } return NULL; }
  return (void *)(intptr_t)handle;
}
static jbyteArray byte_array(JNIEnv *env,const void *bytes,size_t size) {
  jbyteArray out;
  if(size>INT_MAX) { argument(env,"Native byte array is too large"); return NULL; }
  out=(*env)->NewByteArray(env,(jsize)size); if(out && size) (*env)->SetByteArrayRegion(env,out,0,(jsize)size,bytes);
  if((*env)->ExceptionCheck(env)) return NULL;
  return out;
}
JNIEXPORT jstring JNICALL Java_org_exreader_EXReader_nativeVersion(JNIEnv *env,jclass cls) { (void)cls; return (*env)->NewStringUTF(env,exr_version()); }
static jobjectArray metadata_values(JNIEnv *env,const exr_metadata_entry *entries,size_t count) {
  jclass type; jobjectArray out; size_t i;
  if(count>INT_MAX/2) { argument(env,"Metadata array is too large"); return NULL; }
  type=(*env)->FindClass(env,"[B"); if(!type) return NULL;
  out=(*env)->NewObjectArray(env,(jsize)(count*2),type,NULL); (*env)->DeleteLocalRef(env,type); if(!out) return NULL;
  for(i=0;i<count;i++) {
    jbyteArray key=byte_array(env,entries[i].key,strlen(entries[i].key)),value;
    if(!key) return NULL;
    (*env)->SetObjectArrayElement(env,out,(jsize)(i*2),key); (*env)->DeleteLocalRef(env,key);
    if((*env)->ExceptionCheck(env)) return NULL;
    value=byte_array(env,entries[i].value,strlen(entries[i].value)); if(!value) return NULL;
    (*env)->SetObjectArrayElement(env,out,(jsize)(i*2+1),value); (*env)->DeleteLocalRef(env,value);
    if((*env)->ExceptionCheck(env)) return NULL;
  }
  return out;
}
JNIEXPORT jobjectArray JNICALL Java_org_exreader_EXReader_nativeReadXMP(JNIEnv *env,jclass cls,jbyteArray packet) {
  jsize size; jbyte *bytes; exr_metadata_entry *entries=NULL; size_t count=0; exr_error error={0}; exr_status status; jobjectArray out=NULL; (void)cls;
  if(!packet) { argument(env,"Missing XMP packet"); return NULL; }
  size=(*env)->GetArrayLength(env,packet); if(size<=0 || size>1024*1024) { argument(env,"Invalid XMP packet size"); return NULL; }
  bytes=(*env)->GetByteArrayElements(env,packet,NULL); if(!bytes) return NULL;
  status=exr_metadata_read_xmp(bytes,(size_t)size,NULL,&entries,&count,&error);
  (*env)->ReleaseByteArrayElements(env,packet,bytes,JNI_ABORT);
  if(status!=EXR_OK) engine_error(env,status,&error); else out=metadata_values(env,entries,count);
  exr_metadata_free(entries,count); return out;
}
JNIEXPORT jobjectArray JNICALL Java_org_exreader_EXReader_nativePdfMetadata(JNIEnv *env,jclass cls,jlong handle) {
  exr_fixed_document *d=pointer(env,handle); exr_metadata_entry *entries=NULL; size_t count=0; exr_error error={0}; exr_status status; jobjectArray out=NULL; (void)cls;
  if(!d) return NULL;
  status=exr_fixed_load_metadata(d,NULL,&entries,&count,&error);
  if(status!=EXR_OK) engine_error(env,status,&error); else out=metadata_values(env,entries,count);
  exr_metadata_free(entries,count); return out;
}
JNIEXPORT jlong JNICALL Java_org_exreader_EXReader_nativePdfOpen(JNIEnv *env,jclass cls,jbyteArray bytes,jbyteArray font,jint face) {
  jbyte *input=NULL,*program=NULL; jsize size,font_size=0; exr_fixed_document *document=NULL; exr_font *fallback=NULL; exr_font_input source={0}; exr_fixed_open_options options={0}; exr_error error={0}; exr_status status=EXR_OK; (void)cls;
  if(!bytes || face<0) { argument(env,"Missing PDF bytes or invalid face index"); return 0; }
  size=(*env)->GetArrayLength(env,bytes); if(size<=0 || size>128*1024*1024) { argument(env,"Invalid PDF input size"); return 0; }
  input=(*env)->GetByteArrayElements(env,bytes,NULL); if(!input) return 0;
  if(font) {
    font_size=(*env)->GetArrayLength(env,font); if(font_size<=0 || font_size>128*1024*1024) { argument(env,"Invalid font input size"); goto finish; }
    program=(*env)->GetByteArrayElements(env,font,NULL); if(!program) goto finish;
    source.data=program; source.size=(size_t)font_size; source.face_index=(unsigned)face;
    status=exr_font_create_glyphs(&source,1,&fallback,&error); if(status!=EXR_OK) goto finish;
  }
  options.struct_size=sizeof(options); options.fallback_font=fallback;
  status=exr_fixed_open_memory(EXR_PDF,input,(size_t)size,&options,&document,&error);
finish:
  if(program) (*env)->ReleaseByteArrayElements(env,font,program,JNI_ABORT);
  (*env)->ReleaseByteArrayElements(env,bytes,input,JNI_ABORT); exr_font_free(fallback);
  if(status!=EXR_OK) engine_error(env,status,&error);
  return (jlong)(intptr_t)document;
}
JNIEXPORT jint JNICALL Java_org_exreader_EXReader_nativePdfCount(JNIEnv *env,jclass cls,jlong handle) {
  exr_fixed_document *d=pointer(env,handle); size_t count=0; (void)cls; if(!d) return 0; exr_fixed_pages(d,&count); return (jint)count;
}
JNIEXPORT void JNICALL Java_org_exreader_EXReader_nativePdfClose(JNIEnv *env,jclass cls,jlong handle) { (void)cls; exr_fixed_free(pointer(env,handle)); }
JNIEXPORT jobject JNICALL Java_org_exreader_EXReader_nativePdfRender(JNIEnv *env,jclass cls,jlong handle,jint page,jdouble scale) {
  exr_fixed_document *d=pointer(env,handle); exr_bitmap bitmap={0}; exr_error error={0}; exr_status status; jclass type; jmethodID constructor; jbyteArray pixels; jobject out=NULL; (void)cls;
  if(!d) return NULL;
  if(page<0) { argument(env,"Negative PDF page"); return NULL; }
  status=exr_fixed_render(d,(size_t)page,scale,NULL,&bitmap,&error); if(status!=EXR_OK) { engine_error(env,status,&error); return NULL; }
  pixels=byte_array(env,bitmap.pixels,(size_t)bitmap.stride*bitmap.height); if(!pixels) goto finish;
  type=(*env)->FindClass(env,"org/exreader/EXReader$Bitmap"); if(!type) goto finish;
  constructor=(*env)->GetMethodID(env,type,"<init>","(IIII[B)V");
  if(constructor) out=(*env)->NewObject(env,type,constructor,(jint)bitmap.width,(jint)bitmap.height,(jint)bitmap.stride,(jint)bitmap.channels,pixels);
  if((*env)->ExceptionCheck(env)) out=NULL;
  (*env)->DeleteLocalRef(env,type);
finish:
  exr_bitmap_free(&bitmap); return out;
}
JNIEXPORT jobject JNICALL Java_org_exreader_EXReader_nativePdfText(JNIEnv *env,jclass cls,jlong handle,jint page) {
  exr_fixed_document *d=pointer(env,handle); exr_fixed_text *text=NULL; exr_error error={0}; exr_status status; size_t size,count,at; const char *bytes; const exr_text_region *regions;
  jbyteArray utf8; jlongArray ranges; jdoubleArray quads; jintArray flags; jclass type; jmethodID constructor; jobject out=NULL; (void)cls;
  if(!d) return NULL;
  if(page<0) { argument(env,"Negative PDF page"); return NULL; }
  status=exr_fixed_load_text(d,(size_t)page,NULL,&text,&error); if(status!=EXR_OK) { engine_error(env,status,&error); return NULL; }
  bytes=exr_fixed_text_string(text,&size); regions=exr_fixed_text_regions(text,&count);
  if(count>(size_t)INT_MAX/8) { argument(env,"Native text region array is too large"); goto finish; }
  utf8=byte_array(env,bytes,size); if(!utf8) goto finish;
  ranges=(*env)->NewLongArray(env,(jsize)(count*2)); if(!ranges) goto finish;
  quads=(*env)->NewDoubleArray(env,(jsize)(count*8)); if(!quads) goto finish;
  flags=(*env)->NewIntArray(env,(jsize)count); if(!flags) goto finish;
  for(at=0;at<count;at+=128) {
    jlong r[256]; jdouble q[1024]; jint f[128]; size_t i,n=count-at; if(n>128) n=128;
    for(i=0;i<n;i++) { r[i*2]=(jlong)regions[at+i].start; r[i*2+1]=(jlong)regions[at+i].end; memcpy(q+i*8,regions[at+i].quad,8*sizeof(*q)); f[i]=(jint)regions[at+i].flags; }
    (*env)->SetLongArrayRegion(env,ranges,(jsize)(at*2),(jsize)(n*2),r); if((*env)->ExceptionCheck(env)) goto finish;
    (*env)->SetDoubleArrayRegion(env,quads,(jsize)(at*8),(jsize)(n*8),q); if((*env)->ExceptionCheck(env)) goto finish;
    (*env)->SetIntArrayRegion(env,flags,(jsize)at,(jsize)n,f); if((*env)->ExceptionCheck(env)) goto finish;
  }
  type=(*env)->FindClass(env,"org/exreader/EXReader$TextPage"); if(!type) goto finish;
  constructor=(*env)->GetMethodID(env,type,"<init>","([B[J[D[I)V");
  if(constructor) out=(*env)->NewObject(env,type,constructor,utf8,ranges,quads,flags);
  if((*env)->ExceptionCheck(env)) out=NULL;
  (*env)->DeleteLocalRef(env,type);
finish:
  exr_fixed_text_free(text); return out;
}
JNIEXPORT jlong JNICALL Java_org_exreader_EXReader_nativeWaveOpen(JNIEnv *env,jclass cls,jbyteArray bytes) {
  exr_wave *wave=NULL; exr_error error={0}; exr_status status; jsize size; char *path; (void)cls;
  if(!bytes) { argument(env,"Missing WAVE path"); return 0; }
  size=(*env)->GetArrayLength(env,bytes); if(size<=0 || size>1024*1024) { argument(env,"Invalid WAVE path size"); return 0; }
  path=malloc((size_t)size+1); if(!path) { error.code=EXR_MEMORY; engine_error(env,EXR_MEMORY,&error); return 0; }
  (*env)->GetByteArrayRegion(env,bytes,0,size,(jbyte *)path); path[size]=0;
  if((*env)->ExceptionCheck(env)) { free(path); return 0; }
  if(memchr(path,0,(size_t)size)) { free(path); argument(env,"NUL in WAVE path"); return 0; }
  status=exr_wave_open(path,NULL,&wave,&error); free(path);
  if(status!=EXR_OK) engine_error(env,status,&error);
  return (jlong)(intptr_t)wave;
}
JNIEXPORT jobject JNICALL Java_org_exreader_EXReader_nativeWaveFormat(JNIEnv *env,jclass cls,jlong handle) {
  exr_wave *w=pointer(env,handle); const exr_wave_info *info; jclass type; jmethodID constructor; jobject out=NULL; (void)cls;
  if(!w) return NULL;
  info=exr_wave_format(w); type=(*env)->FindClass(env,"org/exreader/EXReader$WaveFormat"); if(!type) return NULL;
  constructor=(*env)->GetMethodID(env,type,"<init>","(IIIIIJZ)V");
  if(constructor) out=(*env)->NewObject(env,type,constructor,(jint)info->sample_rate,(jint)info->channels,(jint)info->bits_per_sample,(jint)info->valid_bits,(jint)info->channel_mask,(jlong)info->frames,(jboolean)info->floating);
  if((*env)->ExceptionCheck(env)) out=NULL;
  (*env)->DeleteLocalRef(env,type); return out;
}
JNIEXPORT jfloatArray JNICALL Java_org_exreader_EXReader_nativeWaveRead(JNIEnv *env,jclass cls,jlong handle,jlong first,jint frames) {
  exr_wave *w=pointer(env,handle); const exr_wave_info *info; exr_error error={0}; exr_status status; float *samples; size_t count=0,total; jfloatArray out=NULL; (void)cls;
  if(!w) return NULL;
  if(first<0 || frames<0 || frames>65536) { argument(env,"Invalid WAVE frame range"); return NULL; }
  info=exr_wave_format(w); total=(size_t)frames*info->channels; samples=total ? malloc(total*sizeof(*samples)) : NULL;
  if(total && !samples) { engine_error(env,EXR_MEMORY,&error); return NULL; }
  status=exr_wave_read(w,(uint64_t)first,(size_t)frames,samples,&count,NULL,&error);
  if(status!=EXR_OK) { free(samples); engine_error(env,status,&error); return NULL; }
  out=(*env)->NewFloatArray(env,(jsize)(count*info->channels));
  if(out && count) (*env)->SetFloatArrayRegion(env,out,0,(jsize)(count*info->channels),samples);
  free(samples); return (*env)->ExceptionCheck(env) ? NULL : out;
}
JNIEXPORT void JNICALL Java_org_exreader_EXReader_nativeWaveClose(JNIEnv *env,jclass cls,jlong handle) { (void)cls; exr_wave_free(pointer(env,handle)); }

JNIEXPORT jlong JNICALL Java_org_exreader_EXReader_nativePcmOpen(JNIEnv *env,jclass cls,jbyteArray bytes) {
  exr_pcm *wave=NULL; exr_error error={0}; exr_status status; jsize size; char *path; (void)cls;
  if(!bytes) { argument(env,"Missing PCM path"); return 0; }
  size=(*env)->GetArrayLength(env,bytes); if(size<=0 || size>1024*1024) { argument(env,"Invalid PCM path size"); return 0; }
  path=malloc((size_t)size+1); if(!path) { error.code=EXR_MEMORY; engine_error(env,EXR_MEMORY,&error); return 0; }
  (*env)->GetByteArrayRegion(env,bytes,0,size,(jbyte *)path); path[size]=0;
  if((*env)->ExceptionCheck(env)) { free(path); return 0; }
  if(memchr(path,0,(size_t)size)) { free(path); argument(env,"NUL in PCM path"); return 0; }
  status=exr_pcm_open(path,NULL,&wave,&error); free(path);
  if(status!=EXR_OK) engine_error(env,status,&error);
  return (jlong)(intptr_t)wave;
}
JNIEXPORT jobject JNICALL Java_org_exreader_EXReader_nativePcmFormat(JNIEnv *env,jclass cls,jlong handle) {
  exr_pcm *w=pointer(env,handle); const exr_pcm_info *info; jclass type; jmethodID constructor; jobject out=NULL; (void)cls;
  if(!w) return NULL;
  info=exr_pcm_format(w); type=(*env)->FindClass(env,"org/exreader/EXReader$PcmFormat"); if(!type) return NULL;
  constructor=(*env)->GetMethodID(env,type,"<init>","(IIIJ)V");
  if(constructor) out=(*env)->NewObject(env,type,constructor,(jint)info->sample_rate,(jint)info->channels,(jint)info->channel_mask,(jlong)info->frames);
  if((*env)->ExceptionCheck(env)) out=NULL;
  (*env)->DeleteLocalRef(env,type); return out;
}
JNIEXPORT jfloatArray JNICALL Java_org_exreader_EXReader_nativePcmRead(JNIEnv *env,jclass cls,jlong handle,jlong first,jint frames) {
  exr_pcm *w=pointer(env,handle); const exr_pcm_info *info; exr_error error={0}; exr_status status; float *samples; size_t count=0,total; jfloatArray out=NULL; (void)cls;
  if(!w) return NULL;
  if(first<0 || frames<0 || frames>65536) { argument(env,"Invalid PCM frame range"); return NULL; }
  info=exr_pcm_format(w); total=(size_t)frames*info->channels; samples=total ? malloc(total*sizeof(*samples)) : NULL;
  if(total && !samples) { engine_error(env,EXR_MEMORY,&error); return NULL; }
  status=exr_pcm_read(w,(uint64_t)first,(size_t)frames,samples,&count,NULL,&error);
  if(status!=EXR_OK) { free(samples); engine_error(env,status,&error); return NULL; }
  out=(*env)->NewFloatArray(env,(jsize)(count*info->channels));
  if(out && count) (*env)->SetFloatArrayRegion(env,out,0,(jsize)(count*info->channels),samples);
  free(samples); return (*env)->ExceptionCheck(env) ? NULL : out;
}
JNIEXPORT void JNICALL Java_org_exreader_EXReader_nativePcmClose(JNIEnv *env,jclass cls,jlong handle) { (void)cls; exr_pcm_free(pointer(env,handle)); }
