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
JNIEXPORT jlong JNICALL Java_org_exreader_EXReader_nativePdfOpen(JNIEnv *env,jclass cls,jbyteArray bytes,jbyteArray font,jint face,jint format,jbyteArray password,jlongArray security) {
  jbyte *input=NULL,*program=NULL; jsize size,font_size=0; exr_fixed_document *document=NULL; exr_font *fallback=NULL; exr_font_input source={0}; exr_fixed_open_options options={0}; exr_error error={0}; exr_status status=EXR_OK; (void)cls;
  if(!bytes || face<0) { argument(env,"Missing PDF bytes or invalid face index"); return 0; }
  unsigned char secret[1024]={0}; jsize secret_size=password ? (*env)->GetArrayLength(env,password) : 0; size_t i;
  exr_pdf_security_info info={0}; info.struct_size=sizeof(info);
  if(secret_size>1024 || !security || (*env)->GetArrayLength(env,security)!=6) { argument(env,"Invalid PDF password/security output"); return 0; }
  size=(*env)->GetArrayLength(env,bytes); if(size<=0 || size>128*1024*1024) { argument(env,"Invalid PDF input size"); return 0; }
  input=(*env)->GetByteArrayElements(env,bytes,NULL); if(!input) return 0;
  if(font) {
    font_size=(*env)->GetArrayLength(env,font); if(font_size<=0 || font_size>128*1024*1024) { argument(env,"Invalid font input size"); goto finish; }
    program=(*env)->GetByteArrayElements(env,font,NULL); if(!program) goto finish;
    source.data=program; source.size=(size_t)font_size; source.face_index=(unsigned)face;
    status=exr_font_create_glyphs(&source,1,&fallback,&error); if(status!=EXR_OK) goto finish;
  }
  if(secret_size) { (*env)->GetByteArrayRegion(env,password,0,secret_size,(jbyte *)secret); if((*env)->ExceptionCheck(env)) goto finish; }
  options.struct_size=sizeof(options); options.fallback_font=fallback; options.pdf_password=secret; options.pdf_password_size=(size_t)secret_size;
  if(format==EXR_PDF) options.pdf_security=&info;
  status=exr_fixed_open_memory((exr_format)format,input,(size_t)size,&options,&document,&error);
  if(status==EXR_OK) {
    jlong values[6]={info.encrypted,info.revision,info.key_bits,info.owner_authenticated,info.permissions,info.metadata_encrypted};
    (*env)->SetLongArrayRegion(env,security,0,6,values);
    if((*env)->ExceptionCheck(env)) { exr_fixed_free(document); document=NULL; }
  }
finish:
  { volatile unsigned char *p=secret; for(i=0;i<sizeof(secret);i++) p[i]=0; }
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

/* Java serializes each publication and its descendants through one shared gate.
   These references let close(parent) precede close(child) without dangling C data. */
typedef struct { exr_document *document; size_t refs; } jni_document;
typedef struct { jni_document *owner; exr_font *font; exr_pager *pager; } jni_pager;
typedef struct { jni_document *owner; exr_layout *layout; } jni_page;
static jobject bitmap_value(JNIEnv *env,const exr_bitmap *b) {
  jbyteArray pixels; jclass type; jmethodID ctor; jobject out;
  if(!b || !b->pixels) return NULL;
  pixels=byte_array(env,b->pixels,(size_t)b->stride*b->height); if(!pixels) return NULL;
  type=(*env)->FindClass(env,"org/exreader/EXReader$Bitmap"); if(!type) return NULL;
  ctor=(*env)->GetMethodID(env,type,"<init>","(IIII[B)V"); if(!ctor) return NULL;
  out=(*env)->NewObject(env,type,ctor,(jint)b->width,(jint)b->height,(jint)b->stride,(jint)b->channels,pixels);
  return (*env)->ExceptionCheck(env) ? NULL : out;
}
static void document_release(jni_document *d) { if(d && !--d->refs) { exr_document_free(d->document); free(d); } }
static void *input_copy(JNIEnv *env,jbyteArray bytes,size_t limit,size_t *size) {
  jsize n; char *out; exr_error error={0};
  if(!bytes) { argument(env,"Missing input bytes"); return NULL; }
  n=(*env)->GetArrayLength(env,bytes);
  if((size_t)n>limit) { argument(env,"Input exceeds adapter limit"); return NULL; }
  out=malloc((size_t)n+1);
  if(!out) { engine_error(env,EXR_MEMORY,&error); return NULL; }
  if(n) (*env)->GetByteArrayRegion(env,bytes,0,n,(jbyte *)out);
  if((*env)->ExceptionCheck(env)) { free(out); return NULL; }
  out[n]=0; *size=(size_t)n; return out;
}
static jbyteArray string_bytes(JNIEnv *env,const char *s) { return s ? byte_array(env,s,strlen(s)) : NULL; }
JNIEXPORT jlong JNICALL Java_org_exreader_EXReader_nativePublicationOpen(JNIEnv *env,jclass cls,jbyteArray bytes,jboolean memory) {
  size_t size=0; void *input=input_copy(env,bytes,128*1024*1024,&size); exr_publication *p=NULL; exr_error error={0}; exr_status status; (void)cls;
  if(!input) return 0;
  if(!memory && (!size || memchr(input,0,size))) { free(input); argument(env,"Invalid publication path"); return 0; }
  status=memory ? exr_publication_open_memory(EXR_EPUB,input,size,&p,&error) : exr_publication_open(input,&p,&error);
  free(input); if(status!=EXR_OK) engine_error(env,status,&error); return (jlong)(intptr_t)p;
}
JNIEXPORT void JNICALL Java_org_exreader_EXReader_nativePublicationClose(JNIEnv *env,jclass cls,jlong handle) { (void)cls; exr_publication_free(pointer(env,handle)); }
JNIEXPORT jbyteArray JNICALL Java_org_exreader_EXReader_nativePublicationTitle(JNIEnv *env,jclass cls,jlong handle) {
  exr_publication *p=pointer(env,handle); (void)cls; return p ? string_bytes(env,exr_publication_title(p)) : NULL;
}
JNIEXPORT jobjectArray JNICALL Java_org_exreader_EXReader_nativePublicationParts(JNIEnv *env,jclass cls,jlong handle) {
  exr_publication *p=pointer(env,handle); const exr_part *parts; size_t count=0,i; jobjectArray out; jclass type; jmethodID ctor; (void)cls;
  if(!p) return NULL;
  parts=exr_publication_parts(p,&count);
  if(count>INT_MAX) { argument(env,"Too many parts"); return NULL; }
  type=(*env)->FindClass(env,"org/exreader/EXReader$Part"); if(!type) return NULL;
  ctor=(*env)->GetMethodID(env,type,"<init>","([B[B[BZ)V"); if(!ctor) return NULL;
  out=(*env)->NewObjectArray(env,(jsize)count,type,NULL); if(!out) return NULL;
  for(i=0;i<count;i++) {
    jbyteArray id,path,title; jobject part;
    if((*env)->PushLocalFrame(env,8)<0) return NULL;
    id=string_bytes(env,parts[i].id); if((*env)->ExceptionCheck(env)) { (*env)->PopLocalFrame(env,NULL); return NULL; }
    path=string_bytes(env,parts[i].path); if((*env)->ExceptionCheck(env)) { (*env)->PopLocalFrame(env,NULL); return NULL; }
    title=string_bytes(env,parts[i].title); if((*env)->ExceptionCheck(env)) { (*env)->PopLocalFrame(env,NULL); return NULL; }
    part=(*env)->NewObject(env,type,ctor,id,path,title,(jboolean)(parts[i].in_reading_order!=0));
    if((*env)->ExceptionCheck(env)) { (*env)->PopLocalFrame(env,NULL); return NULL; }
    (*env)->SetObjectArrayElement(env,out,(jsize)i,part); (*env)->PopLocalFrame(env,NULL);
    if((*env)->ExceptionCheck(env)) return NULL;
  }
  return out;
}
JNIEXPORT jlong JNICALL Java_org_exreader_EXReader_nativePublicationLoad(JNIEnv *env,jclass cls,jlong handle,jint part) {
  exr_publication *p=pointer(env,handle); jni_document *d; exr_status status; exr_error error={0}; (void)cls;
  if(!p) return 0;
  if(part<0) { argument(env,"Negative part"); return 0; }
  d=calloc(1,sizeof(*d)); if(!d) { engine_error(env,EXR_MEMORY,&error); return 0; }
  status=exr_publication_load(p,(size_t)part,&d->document,&error);
  if(status!=EXR_OK) { free(d); engine_error(env,status,&error); return 0; }
  d->refs=1; return (jlong)(intptr_t)d;
}
JNIEXPORT jlong JNICALL Java_org_exreader_EXReader_nativeDocumentOpen(JNIEnv *env,jclass cls,jbyteArray bytes,jint format) {
  size_t size=0; void *input=input_copy(env,bytes,128*1024*1024,&size); jni_document *d; exr_status status; exr_error error={0}; (void)cls;
  if(!input) return 0;
  if(format<0 || format>EXR_MOBI || (!format && (!size || memchr(input,0,size)))) { free(input); argument(env,"Invalid document format or path"); return 0; }
  d=calloc(1,sizeof(*d)); if(!d) { free(input); engine_error(env,EXR_MEMORY,&error); return 0; }
  status=format ? exr_document_open_memory((exr_format)format,input,size,&d->document,&error) : exr_document_open(input,&d->document,&error);
  free(input); if(status!=EXR_OK) { free(d); engine_error(env,status,&error); return 0; }
  d->refs=1; return (jlong)(intptr_t)d;
}
JNIEXPORT void JNICALL Java_org_exreader_EXReader_nativeDocumentClose(JNIEnv *env,jclass cls,jlong handle) { (void)cls; document_release(pointer(env,handle)); }
JNIEXPORT jbyteArray JNICALL Java_org_exreader_EXReader_nativeDocumentTitle(JNIEnv *env,jclass cls,jlong handle) {
  jni_document *d=pointer(env,handle); (void)cls; return d ? string_bytes(env,exr_document_title(d->document)) : NULL;
}
JNIEXPORT jbyteArray JNICALL Java_org_exreader_EXReader_nativeDocumentText(JNIEnv *env,jclass cls,jlong handle) {
  jni_document *d=pointer(env,handle); const char *text; size_t size=0; (void)cls;
  if(!d) return NULL;
  text=exr_document_text(d->document,&size); return byte_array(env,text,size);
}
static jlong index_value(size_t value) { return value==SIZE_MAX ? -1 : (jlong)value; }
JNIEXPORT jobjectArray JNICALL Java_org_exreader_EXReader_nativeDocumentNodes(JNIEnv *env,jclass cls,jlong handle) {
  jni_document *d=pointer(env,handle); const exr_node *nodes; size_t count=0,i,j; jobjectArray out; jclass type,bytes_type; jmethodID ctor; (void)cls;
  if(!d) return NULL;
  nodes=exr_document_nodes(d->document,&count); if(count>INT_MAX) { argument(env,"Too many nodes"); return NULL; }
  type=(*env)->FindClass(env,"org/exreader/EXReader$Node"); if(!type) return NULL;
  ctor=(*env)->GetMethodID(env,type,"<init>","(I[J[[B)V"); if(!ctor) return NULL;
  bytes_type=(*env)->FindClass(env,"[B"); if(!bytes_type) return NULL;
  out=(*env)->NewObjectArray(env,(jsize)count,type,NULL); if(!out) return NULL;
  for(i=0;i<count;i++) {
    const exr_node *n=&nodes[i]; jlong indices[6]; jlongArray ranges; jobjectArray strings; jobject node;
    if(n->attribute_count>(size_t)(INT_MAX-2)/2) { argument(env,"Too many node attributes"); return NULL; }
    if((*env)->PushLocalFrame(env,8)<0) return NULL;
    indices[0]=index_value(n->parent); indices[1]=index_value(n->first_child); indices[2]=index_value(n->next_sibling);
    indices[3]=index_value(n->chapter); indices[4]=index_value(n->start); indices[5]=index_value(n->end);
    ranges=(*env)->NewLongArray(env,6); if(!ranges) { (*env)->PopLocalFrame(env,NULL); return NULL; }
    (*env)->SetLongArrayRegion(env,ranges,0,6,indices);
    if((*env)->ExceptionCheck(env)) { (*env)->PopLocalFrame(env,NULL); return NULL; }
    strings=(*env)->NewObjectArray(env,(jsize)(2+2*n->attribute_count),bytes_type,NULL);
    if(!strings) { (*env)->PopLocalFrame(env,NULL); return NULL; }
    for(j=0;j<2+n->attribute_count*2;j++) {
      const char *value=j==0 ? n->name : j==1 ? n->text : (j&1) ? n->attributes[(j-2)/2].value : n->attributes[(j-2)/2].name;
      jbyteArray text=string_bytes(env,value);
      if((*env)->ExceptionCheck(env)) { (*env)->PopLocalFrame(env,NULL); return NULL; }
      (*env)->SetObjectArrayElement(env,strings,(jsize)j,text); if(text) (*env)->DeleteLocalRef(env,text);
      if((*env)->ExceptionCheck(env)) { (*env)->PopLocalFrame(env,NULL); return NULL; }
    }
    node=(*env)->NewObject(env,type,ctor,(jint)n->kind,ranges,strings);
    if((*env)->ExceptionCheck(env)) { (*env)->PopLocalFrame(env,NULL); return NULL; }
    (*env)->SetObjectArrayElement(env,out,(jsize)i,node); (*env)->PopLocalFrame(env,NULL);
    if((*env)->ExceptionCheck(env)) return NULL;
  }
  return out;
}
JNIEXPORT jlong JNICALL Java_org_exreader_EXReader_nativePagerCreate(JNIEnv *env,jclass cls,jlong handle,jbyteArray font,jint face,jfloatArray page,jbyteArray css,jboolean styles,jboolean embedded,jint direction) {
  jni_document *d=pointer(env,handle); jni_pager *p=NULL; void *program=NULL; char *sheet=NULL; size_t font_size=0,css_size=0;
  exr_font_input input={0}; exr_layout_config config=exr_layout_config_defaults(); exr_error error={0}; exr_status status=EXR_OK; jfloat values[6]; (void)cls;
  if(!d) return 0;
  if(face<0 || !page || (*env)->GetArrayLength(env,page)!=6 || direction<0 || direction>2) { argument(env,"Invalid layout config"); return 0; }
  (*env)->GetFloatArrayRegion(env,page,0,6,values); if((*env)->ExceptionCheck(env)) return 0;
  config.page.width=values[0]; config.page.height=values[1]; config.page.margin=values[2]; config.page.font_size=values[3]; config.page.line_height=values[4]; config.page.paragraph_spacing=values[5];
  config.document_css=styles!=0; config.embedded_fonts=embedded!=0; config.direction=(exr_direction)direction;
  program=input_copy(env,font,128*1024*1024,&font_size); if(!program) return 0;
  if(css) {
    sheet=input_copy(env,css,4*1024*1024,&css_size); if(!sheet) goto finish;
    if(memchr(sheet,0,css_size)) { argument(env,"NUL in stylesheet"); goto finish; }
    config.user_css=sheet;
  }
  p=calloc(1,sizeof(*p)); if(!p) { status=EXR_MEMORY; goto finish; }
  input.data=program; input.size=font_size; input.face_index=(unsigned)face;
  status=exr_font_create(&input,1,&p->font,&error); if(status!=EXR_OK) goto finish;
  status=exr_pager_create(d->document,p->font,&config,&p->pager,&error);
finish:
  free(program); free(sheet);
  if(status!=EXR_OK) engine_error(env,status,&error);
  if(status!=EXR_OK || (*env)->ExceptionCheck(env)) { if(p) { exr_pager_free(p->pager); exr_font_free(p->font); free(p); } return 0; }
  p->owner=d; d->refs++; return (jlong)(intptr_t)p;
}
JNIEXPORT void JNICALL Java_org_exreader_EXReader_nativePagerHyphenation(JNIEnv *env,jclass cls,jlong handle,jobjectArray languages,jobjectArray patterns,jintArray minima,jlong budget) {
  jni_pager *p=pointer(env,handle); exr_hyphen_pattern_input inputs[64]={{0}}; jint edges[128];
  exr_hyphenator *h=NULL; exr_error error={0}; exr_status status=EXR_OK; jsize count,i; size_t total=0; (void)cls;
  if(!p) return;
  if(!languages || !patterns || !minima || budget<0 || budget>128*1024*1024) { argument(env,"Invalid hyphenation inputs"); return; }
  count=(*env)->GetArrayLength(env,languages);
  if(count>64 || (*env)->GetArrayLength(env,patterns)!=count || (*env)->GetArrayLength(env,minima)!=count*2) { argument(env,"Invalid hyphenation array sizes"); return; }
  if(count) (*env)->GetIntArrayRegion(env,minima,0,count*2,edges);
  if((*env)->ExceptionCheck(env)) return;
  for(i=0;i<count;i++) {
    jbyteArray lang=NULL,data=NULL; size_t n=0;
    if(edges[i*2]<0 || edges[i*2]>64 || edges[i*2+1]<0 || edges[i*2+1]>64) { argument(env,"Invalid hyphenation minima"); break; }
    lang=(jbyteArray)(*env)->GetObjectArrayElement(env,languages,i);
    if((*env)->ExceptionCheck(env)) break;
    inputs[i].language=input_copy(env,lang,255,&n); if(lang) (*env)->DeleteLocalRef(env,lang);
    if(!inputs[i].language) break;
    if(memchr(inputs[i].language,0,n)) { argument(env,"NUL in dictionary language"); break; }
    data=(jbyteArray)(*env)->GetObjectArrayElement(env,patterns,i);
    if((*env)->ExceptionCheck(env)) break;
    inputs[i].patterns=input_copy(env,data,8*1024*1024,&inputs[i].size); if(data) (*env)->DeleteLocalRef(env,data);
    if(!inputs[i].patterns) break;
    total+=inputs[i].size;
    if(total>32*1024*1024) { argument(env,"Dictionary input exceeds 32 MiB"); break; }
    inputs[i].struct_size=sizeof(inputs[i]); inputs[i].left_min=(unsigned)edges[i*2]; inputs[i].right_min=(unsigned)edges[i*2+1];
  }
  if(!(*env)->ExceptionCheck(env)) {
    if(count) status=exr_hyphenator_create_patterns(inputs,(size_t)count,(size_t)budget,NULL,&h,&error);
    if(status==EXR_OK) status=exr_pager_set_hyphenator(p->pager,h,&error);
    if(status!=EXR_OK) engine_error(env,status,&error);
  }
  exr_hyphenator_free(h);
  for(i=0;i<count;i++) { free((void *)inputs[i].language); free((void *)inputs[i].patterns); }
}
JNIEXPORT void JNICALL Java_org_exreader_EXReader_nativePagerClose(JNIEnv *env,jclass cls,jlong handle) {
  jni_pager *p=pointer(env,handle); (void)cls;
  if(p) { exr_pager_free(p->pager); exr_font_free(p->font); document_release(p->owner); free(p); }
}
JNIEXPORT jlong JNICALL Java_org_exreader_EXReader_nativePagerNext(JNIEnv *env,jclass cls,jlong handle) {
  jni_pager *p=pointer(env,handle); jni_page *page; exr_status status; exr_error error={0}; (void)cls;
  if(!p) return 0;
  page=calloc(1,sizeof(*page)); if(!page) { engine_error(env,EXR_MEMORY,&error); return 0; }
  status=exr_pager_next(p->pager,&page->layout,&error);
  if(status!=EXR_OK || !page->layout) { exr_layout_free(page->layout); free(page); if(status!=EXR_OK) engine_error(env,status,&error); return 0; }
  page->owner=p->owner; page->owner->refs++; return (jlong)(intptr_t)page;
}
JNIEXPORT void JNICALL Java_org_exreader_EXReader_nativePageClose(JNIEnv *env,jclass cls,jlong handle) {
  jni_page *p=pointer(env,handle); (void)cls; if(p) { exr_layout_free(p->layout); document_release(p->owner); free(p); }
}
JNIEXPORT jlong JNICALL Java_org_exreader_EXReader_nativePageHit(JNIEnv *env,jclass cls,jlong handle,jfloat x,jfloat y) {
  jni_page *p=pointer(env,handle); (void)cls; return p ? index_value(exr_layout_hit_test(p->layout,0,x,y)) : -1;
}
JNIEXPORT jobject JNICALL Java_org_exreader_EXReader_nativePageRender(JNIEnv *env,jclass cls,jlong handle) {
  jni_page *p=pointer(env,handle); exr_bitmap bitmap={0}; exr_error error={0}; exr_status status; jobject out; (void)cls;
  if(!p) return NULL;
  status=exr_render_page_color(p->layout,exr_layout_font(p->layout),0,&bitmap,&error);
  if(status!=EXR_OK) { engine_error(env,status,&error); return NULL; }
  out=bitmap_value(env,&bitmap);
  exr_bitmap_free(&bitmap); return out;
}
JNIEXPORT jobject JNICALL Java_org_exreader_EXReader_nativePageImage(JNIEnv *env,jclass cls,jlong handle,jint resource) {
  jni_page *p=pointer(env,handle); (void)cls;
  if(resource<0) { argument(env,"Negative resource index"); return NULL; }
  return p ? bitmap_value(env,exr_layout_image(p->layout,(size_t)resource)) : NULL;
}
JNIEXPORT jobject JNICALL Java_org_exreader_EXReader_nativePageFont(JNIEnv *env,jclass cls,jlong handle,jint index) {
  jni_page *p=pointer(env,handle); exr_font_input input={0}; exr_font_axis *axes=NULL; size_t count=0,i;
  exr_font *font; exr_error error={0}; exr_status status; jobject out=NULL; jbyteArray bytes; jdoubleArray coordinates; jclass type; jmethodID ctor; jdouble values[64*6]; (void)cls;
  if(!p) return NULL;
  if(index<0) { argument(env,"Negative font index"); return NULL; }
  font=exr_layout_font(p->layout); status=exr_font_source(font,(size_t)index,&input,&error);
  if(status!=EXR_OK) { engine_error(env,status,&error); return NULL; }
  status=exr_font_axes(font,(size_t)index,&axes,&count,&error);
  if(status!=EXR_OK) { engine_error(env,status,&error); return NULL; }
  if(count>64) { exr_free(axes); argument(env,"Too many font axes"); return NULL; }
  for(i=0;i<count;i++) { size_t at=i*6; values[at]=axes[i].tag; values[at+1]=axes[i].flags; values[at+2]=axes[i].minimum; values[at+3]=axes[i].initial; values[at+4]=axes[i].maximum; values[at+5]=axes[i].value; }
  exr_free(axes);
  bytes=byte_array(env,input.data,input.size); if(!bytes) return NULL;
  coordinates=(*env)->NewDoubleArray(env,(jsize)(count*6)); if(!coordinates) return NULL;
  if(count) (*env)->SetDoubleArrayRegion(env,coordinates,0,(jsize)(count*6),values);
  if((*env)->ExceptionCheck(env)) return NULL;
  type=(*env)->FindClass(env,"org/exreader/EXReader$FontSource"); if(!type) return NULL;
  ctor=(*env)->GetMethodID(env,type,"<init>","([BI[D)V"); if(!ctor) return NULL;
  out=(*env)->NewObject(env,type,ctor,bytes,(jint)input.face_index,coordinates);
  return (*env)->ExceptionCheck(env) ? NULL : out;
}
JNIEXPORT jobject JNICALL Java_org_exreader_EXReader_nativePageSnapshot(JNIEnv *env,jclass cls,jlong handle) {
  jni_page *p=pointer(env,handle); size_t ng=0,nl=0,nb=0,at; const exr_glyph *g; const exr_line *l; const exr_box *b; const exr_page *page;
  jlongArray gd,ld,bd; jfloatArray gp,lp,bp; jclass type; jmethodID ctor; jobject out; (void)cls;
  if(!p) return NULL;
  page=exr_layout_pages(p->layout,NULL); g=exr_layout_glyphs(p->layout,&ng); l=exr_layout_lines(p->layout,&nl); b=exr_layout_boxes(p->layout,&nb);
  if(ng>INT_MAX/12 || nl>INT_MAX/4 || nb>INT_MAX/8) { argument(env,"Layout snapshot is too large"); return NULL; }
  gd=(*env)->NewLongArray(env,(jsize)(ng*12)); if(!gd) return NULL;
  gp=(*env)->NewFloatArray(env,(jsize)(ng*9)); if(!gp) return NULL;
  ld=(*env)->NewLongArray(env,(jsize)(nl*4)); if(!ld) return NULL;
  lp=(*env)->NewFloatArray(env,(jsize)(nl*4)); if(!lp) return NULL;
  bd=(*env)->NewLongArray(env,(jsize)(nb*8)); if(!bd) return NULL;
  bp=(*env)->NewFloatArray(env,(jsize)(nb*5)); if(!bp) return NULL;
  for(at=0;at<ng;at+=128) {
    jlong d[128*12]; jfloat f[128*9]; size_t i,n=ng-at; if(n>128) n=128;
    for(i=0;i<n;i++) {
      const exr_glyph *v=&g[at+i]; size_t a=i*12,c=i*9;
      d[a]=index_value(v->start); d[a+1]=index_value(v->end); d[a+2]=v->codepoint; d[a+3]=v->glyph; d[a+4]=index_value(v->node); d[a+5]=v->color; d[a+6]=v->flags;
      d[a+7]=index_value(v->cluster_start); d[a+8]=index_value(v->cluster_end); d[a+9]=v->boundaries; d[a+10]=index_value(v->font_index); d[a+11]=v->bidi_level;
      f[c]=v->x; f[c+1]=v->baseline; f[c+2]=v->advance; f[c+3]=v->size; f[c+4]=v->clip_left; f[c+5]=v->clip_right; f[c+6]=v->line_height; f[c+7]=v->offset_x; f[c+8]=v->offset_y;
    }
    (*env)->SetLongArrayRegion(env,gd,(jsize)(at*12),(jsize)(n*12),d); if((*env)->ExceptionCheck(env)) return NULL;
    (*env)->SetFloatArrayRegion(env,gp,(jsize)(at*9),(jsize)(n*9),f); if((*env)->ExceptionCheck(env)) return NULL;
  }
  for(at=0;at<nl;at+=128) {
    jlong d[128*4]; jfloat f[128*4]; size_t i,n=nl-at; if(n>128) n=128;
    for(i=0;i<n;i++) { const exr_line *v=&l[at+i]; size_t a=i*4;
      d[a]=index_value(v->start); d[a+1]=index_value(v->end); d[a+2]=index_value(v->glyph_start); d[a+3]=(jlong)v->glyph_count;
      f[a]=v->x; f[a+1]=v->y; f[a+2]=v->width; f[a+3]=v->height;
    }
    (*env)->SetLongArrayRegion(env,ld,(jsize)(at*4),(jsize)(n*4),d); if((*env)->ExceptionCheck(env)) return NULL;
    (*env)->SetFloatArrayRegion(env,lp,(jsize)(at*4),(jsize)(n*4),f); if((*env)->ExceptionCheck(env)) return NULL;
  }
  for(at=0;at<nb;at+=128) {
    jlong d[128*8]; jfloat f[128*5]; size_t i,n=nb-at; if(n>128) n=128;
    for(i=0;i<n;i++) { const exr_box *v=&b[at+i]; size_t a=i*8,c=i*5;
      d[a]=v->kind; d[a+1]=index_value(v->node); d[a+2]=index_value(v->resource); d[a+3]=index_value(v->start); d[a+4]=index_value(v->end); d[a+5]=v->background; d[a+6]=v->border_color; d[a+7]=v->flags;
      f[c]=v->x; f[c+1]=v->y; f[c+2]=v->width; f[c+3]=v->height; f[c+4]=v->border_width;
    }
    (*env)->SetLongArrayRegion(env,bd,(jsize)(at*8),(jsize)(n*8),d); if((*env)->ExceptionCheck(env)) return NULL;
    (*env)->SetFloatArrayRegion(env,bp,(jsize)(at*5),(jsize)(n*5),f); if((*env)->ExceptionCheck(env)) return NULL;
  }
  type=(*env)->FindClass(env,"org/exreader/EXReader$LayoutSnapshot"); if(!type) return NULL;
  ctor=(*env)->GetMethodID(env,type,"<init>","(JJI[J[F[J[F[J[F)V"); if(!ctor) return NULL;
  out=(*env)->NewObject(env,type,ctor,(jlong)page->start,(jlong)page->end,(jint)exr_layout_writing_mode(p->layout),gd,gp,ld,lp,bd,bp);
  return (*env)->ExceptionCheck(env) ? NULL : out;
}
JNIEXPORT jobject JNICALL Java_org_exreader_EXReader_nativeReadM4b(JNIEnv *env,jclass cls,jbyteArray input) {
  size_t path_size=0,count=0,n=0,i,size=0; uint64_t duration; char *path=input_copy(env,input,1024*1024,&path_size);
  exr_m4b_inspection *m=NULL; exr_error error={0}; exr_status status; const exr_metadata_entry *metadata;
  const exr_audio_chapter *chapters; const void *cover; const char *media_type; jobject out=NULL;
  jclass chapter_type,type; jmethodID ctor,chapter_ctor; jobjectArray values,chapter_values; jbyteArray pixels=NULL,media=NULL; (void)cls;
  if(!path) return NULL;
  if(!path_size || memchr(path,0,path_size)) { free(path); argument(env,"Invalid M4B metadata path"); return NULL; }
  status=exr_m4b_inspect(path,NULL,&m,&error); free(path);
  if(status!=EXR_OK) { engine_error(env,status,&error); return NULL; }
  metadata=exr_m4b_inspection_metadata(m,&count); chapters=exr_m4b_inspection_chapters(m,&n);
  duration=exr_m4b_inspection_duration(m);
  if(duration!=UINT64_MAX && duration>INT64_MAX) goto timestamp_limit;
  for(i=0;i<n;i++) if(chapters[i].start_ms>INT64_MAX || (chapters[i].end_ms!=UINT64_MAX && chapters[i].end_ms>INT64_MAX)) goto timestamp_limit;
  values=metadata_values(env,metadata,count); if(!values) goto finish;
  chapter_type=(*env)->FindClass(env,"org/exreader/EXReader$AudioChapter"); if(!chapter_type) goto finish;
  chapter_ctor=(*env)->GetMethodID(env,chapter_type,"<init>","([B[BJJJ)V"); if(!chapter_ctor) goto finish;
  chapter_values=(*env)->NewObjectArray(env,(jsize)n,chapter_type,NULL); if(!chapter_values) goto finish;
  for(i=0;i<n;i++) {
    jbyteArray id,title; jobject chapter;
    if((*env)->PushLocalFrame(env,8)<0) goto finish;
    id=string_bytes(env,chapters[i].id); if((*env)->ExceptionCheck(env)) { (*env)->PopLocalFrame(env,NULL); goto finish; }
    title=string_bytes(env,chapters[i].title); if((*env)->ExceptionCheck(env)) { (*env)->PopLocalFrame(env,NULL); goto finish; }
    chapter=(*env)->NewObject(env,chapter_type,chapter_ctor,id,title,index_value(chapters[i].parent),(jlong)chapters[i].start_ms,(jlong)chapters[i].end_ms);
    if((*env)->ExceptionCheck(env)) { (*env)->PopLocalFrame(env,NULL); goto finish; }
    (*env)->SetObjectArrayElement(env,chapter_values,(jsize)i,chapter); (*env)->PopLocalFrame(env,NULL);
    if((*env)->ExceptionCheck(env)) goto finish;
  }
  cover=exr_m4b_inspection_cover(m,&size,&media_type);
  if(cover) { pixels=byte_array(env,cover,size); if(!pixels) goto finish; media=string_bytes(env,media_type); if((*env)->ExceptionCheck(env)) goto finish; }
  type=(*env)->FindClass(env,"org/exreader/EXReader$AudioBookMetadata"); if(!type) goto finish;
  ctor=(*env)->GetMethodID(env,type,"<init>","([[B[Lorg/exreader/EXReader$AudioChapter;J[B[B)V"); if(!ctor) goto finish;
  out=(*env)->NewObject(env,type,ctor,values,chapter_values,duration==UINT64_MAX ? (jlong)-1 : (jlong)duration,pixels,media);
  if((*env)->ExceptionCheck(env)) out=NULL;
  goto finish;
timestamp_limit:
  error.code=EXR_LIMIT; strcpy(error.message,"M4B timestamps exceed Java signed range"); engine_error(env,EXR_LIMIT,&error);
finish:
  exr_m4b_inspection_free(m); return out;
}
