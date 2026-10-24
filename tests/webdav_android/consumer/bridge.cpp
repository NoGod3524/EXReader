/* SPDX-License-Identifier: MIT */
#include "exr_webdav_android.h"
#include "consumer.h"
#include <string>
#include <thread>
#ifdef EXR_WEBDAV_ANDROID_TESTING
extern "C" void exr_webdav_android_test_stats(uint64_t out[4]);
#endif
namespace {
struct text_arg {
  JNIEnv *env;jstring value;const char *text;
  text_arg(JNIEnv *e,jstring v):env(e),value(v),text(e->GetStringUTFChars(v,nullptr)){}
  ~text_arg(){if(text)env->ReleaseStringUTFChars(value,text);}
};
std::string quote(const char *text){
  std::string out="\"";
  for(const unsigned char *p=(const unsigned char *)text;*p;p++){
    if(*p=='"'||*p=='\\')out+='\\';
    if(*p<32){static const char digits[]="0123456789abcdef";out+="\\u00";out+=digits[*p>>4];out+=digits[*p&15];}else out+=(char)*p;
  }
  return out+'"';
}
}
extern "C" JNIEXPORT jint JNICALL Java_org_exreader_webdav_probe_NativeDav_bind(JNIEnv *env,jclass){return exr_webdav_android_initialize(env);}
extern "C" JNIEXPORT jbyteArray JNICALL Java_org_exreader_webdav_probe_NativeDav_request(JNIEnv *env,jclass,
  jstring root,jstring auth,jstring directory,jstring action,jstring resource,jstring filename,jlongArray input,jboolean native_thread){
  text_arg r(env,root),a(env,auth),d(env,directory),m(env,action),p(env,resource),f(env,filename);
  if(env->ExceptionCheck())return nullptr;
  if(!r.text||!a.text||!d.text||!m.text||!p.text||!f.text||env->GetArrayLength(input)!=6)return nullptr;
  jlong values[6];env->GetLongArrayRegion(input,0,6,values);if(env->ExceptionCheck())return nullptr;
  uint64_t limits[6];for(size_t i=0;i<6;i++)limits[i]=(uint64_t)values[i];
  dav_result result{};auto run=[&](){dav_consume(r.text,a.text,d.text,m.text,p.text,f.text,limits,&result);};
  try{if(native_thread){std::thread worker(run);worker.join();}else run();}catch(...){return nullptr;}
  uint64_t counters[4]={0};
#ifdef EXR_WEBDAV_ANDROID_TESTING
  exr_webdav_android_test_stats(counters);
#endif
  std::string json="{\"status\":"+std::to_string(result.status)+",\"http\":"+std::to_string(result.http)+",\"count\":"+std::to_string(result.count)
    +",\"bytes\":"+std::to_string(result.bytes)+",\"published\":"+std::to_string(result.published)+",\"resource\":"+quote(result.resource)+",\"title\":"+quote(result.title)
    +",\"reentry\":"+std::to_string(result.reentry)+",\"wrong_owner\":"+std::to_string(result.wrong_owner)+",\"clients\":"+std::to_string(counters[0])
    +",\"uploads\":"+std::to_string(counters[1])+",\"attached\":"+std::to_string(counters[2])+",\"detached\":"+std::to_string(counters[3])+"}";
  jbyteArray bytes=env->NewByteArray((jsize)json.size());if(bytes)env->SetByteArrayRegion(bytes,0,(jsize)json.size(),(const jbyte *)json.data());return bytes;
}
