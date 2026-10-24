/* SPDX-License-Identifier: MIT */
#include <jni.h>
#include <reader_commands.h>
#include <catalog.h>
#include <sqlite3.h>
#include <dlfcn.h>
#include <map>
#include <memory>
#include <mutex>
#include <stdexcept>
#include <string>
#include <thread>
#include <vector>

namespace product_jni {
struct failure {const char *type;std::string message;};
[[noreturn]] void reject(const char *type,const std::string &message){throw failure{type,message};}
void pending(JNIEnv *env){if(env->ExceptionCheck())throw failure{nullptr,{}};}
void report(JNIEnv *env,const failure &e){if(e.type&&!env->ExceptionCheck()){jclass c=env->FindClass(e.type);if(c)env->ThrowNew(c,e.message.c_str());}}
void database(int code,const char *message){if(code)reject("android/database/sqlite/SQLiteException",message);}
std::string utf8(JNIEnv *env,jstring input,bool optional=false){
  if(!input){if(optional)return {};reject("java/lang/IllegalArgumentException","Missing product text");}
  jsize units=env->GetStringLength(input);if(units>16384)reject("java/lang/IllegalArgumentException","Product UTF-16 text exceeds its bound");
  const jchar *wide=env->GetStringChars(input,nullptr);pending(env);
  char converted[16385];size_t bytes=0;reader_command_error error{};
  auto status=reader_command_utf16(reinterpret_cast<const uint16_t *>(wide),(size_t)units,converted,sizeof(converted),&bytes,&error);
  env->ReleaseStringChars(input,wide);
  if(status!=READER_COMMAND_OK)reject("java/lang/IllegalArgumentException",error.message);
  return std::string(converted,bytes);
}
jstring string(JNIEnv *env,const std::string &value){
  jbyteArray bytes=env->NewByteArray((jsize)value.size());pending(env);
  env->SetByteArrayRegion(bytes,0,(jsize)value.size(),reinterpret_cast<const jbyte *>(value.data()));pending(env);
  jclass type=env->FindClass("org/exreader/host/NativeCatalog");pending(env);
  jmethodID decode=env->GetStaticMethodID(type,"decode","([B)Ljava/lang/String;");pending(env);
  auto result=(jstring)env->CallStaticObjectMethod(type,decode,bytes);
  env->DeleteLocalRef(bytes);env->DeleteLocalRef(type);pending(env);return result;
}
jobjectArray strings(JNIEnv *env,const std::vector<std::string> &values){
  jclass type=env->FindClass("java/lang/String");pending(env);
  jobjectArray result=env->NewObjectArray((jsize)values.size(),type,nullptr);env->DeleteLocalRef(type);pending(env);
  for(size_t i=0;i<values.size();++i){jstring value=string(env,values[i]);env->SetObjectArrayElement(result,(jsize)i,value);env->DeleteLocalRef(value);pending(env);}
  return result;
}
struct owner {
  reader_catalog *catalog=nullptr;reader_revisions *revisions=nullptr;
  std::thread::id thread=std::this_thread::get_id();bool active=false;
  ~owner(){reader_revision_error re{};reader_catalog_error ce{};
    if(revisions)reader_revisions_close(&revisions,&re);if(catalog)reader_catalog_close(&catalog,&ce);}
};
std::mutex registry_mutex;
std::map<jlong,std::unique_ptr<owner>> registry;
jlong sequence=0;
owner &get(jlong handle){
  std::lock_guard<std::mutex> lock(registry_mutex);auto found=registry.find(handle);
  if(found==registry.end())reject("java/lang/IllegalStateException","Product owner is closed or unknown");
  owner &result=*found->second;
  if(result.thread!=std::this_thread::get_id()||result.active)reject("java/lang/IllegalStateException","Product calls require the creating worker without reentry");
  return result;
}
struct entered {owner &value;explicit entered(owner &input):value(input){value.active=true;}~entered(){value.active=false;}};
template<class Function>auto call(JNIEnv *env,jlong handle,Function function)->decltype(function(std::declval<owner &>())){
  using result=decltype(function(std::declval<owner &>()));
  try{owner &value=get(handle);entered scope(value);return function(value);}
  catch(const failure &e){report(env,e);}catch(...){report(env,{"java/lang/OutOfMemoryError","Cannot allocate bounded product request"});}
  return result{};
}
struct copied_row {
  std::string key,title,format,sort,author,mode;uint64_t bytes;int64_t sdk_id;int favorite,deleted;
  explicit copied_row(const reader_catalog_row &r):key(r.book_key),title(r.title),format(r.format),sort(r.sort_title),author(r.author),
    mode(r.location_kind?r.location_kind:""),bytes(r.source_bytes),sdk_id(r.sdk_book_id),favorite(r.favorite),deleted(r.deleted){}
};
struct rows {JNIEnv *env; jobject cancel=nullptr;std::vector<copied_row> values;bool memory=false;};
int copy(void *opaque,const reader_catalog_row *row){
  auto &r=*static_cast<rows *>(opaque);
  try{
  if(r.cancel){jclass c=r.env->GetObjectClass(r.cancel);jmethodID m=r.env->GetMethodID(c,"isCanceled","()Z");
    if(r.env->ExceptionCheck())return 1;
    jboolean cancelled=r.env->CallBooleanMethod(r.cancel,m);r.env->DeleteLocalRef(c);if(cancelled||r.env->ExceptionCheck())return 1;}
  r.values.emplace_back(*row);return 0;
  }catch(...){r.memory=true;return 1;}
}
void copied(rows &r){pending(r.env);if(r.memory)reject("java/lang/OutOfMemoryError","Cannot copy bounded product rows");}
jobject shelf_book(JNIEnv *env,const copied_row &row){
  jclass c=env->FindClass("org/exreader/host/CatalogStore$ShelfBook");pending(env);
  jmethodID ctor=env->GetMethodID(c,"<init>","(Ljava/lang/String;Ljava/lang/String;JLjava/lang/String;Ljava/lang/String;Ljava/lang/String;J)V");pending(env);
  jstring sort=string(env,row.sort),key=string(env,row.key),title=string(env,row.title),author=string(env,row.author),format=string(env,row.format);
  jobject result=env->NewObject(c,ctor,sort,key,(jlong)row.sdk_id,title,author,format,(jlong)row.bytes);
  for(jobject v:{(jobject)sort,(jobject)key,(jobject)title,(jobject)author,(jobject)format})env->DeleteLocalRef(v);
  env->DeleteLocalRef(c);pending(env);return result;
}
struct context {
  std::string revision;std::vector<std::string> parents;std::vector<const char *> pointers;
  reader_command_context native{};
  context(JNIEnv *env,owner &o,jstring id,jobjectArray expected):revision(utf8(env,id)){
    if(revision.empty())reject("java/lang/IllegalArgumentException","Stable revision ID required");
    if(!expected||env->GetArrayLength(expected)>32)reject("java/lang/IllegalArgumentException","Complete bounded observed heads required");
    for(jsize i=0;i<env->GetArrayLength(expected);++i){auto value=(jstring)env->GetObjectArrayElement(expected,i);pending(env);parents.push_back(utf8(env,value));env->DeleteLocalRef(value);}
    for(const auto &value:parents)pointers.push_back(value.c_str());
    native={o.revisions,revision.c_str(),pointers.data(),pointers.size()};
  }
};
jobjectArray command_result(JNIEnv *env,reader_command_status status,const reader_command_result &result,const reader_command_error &error){
  return strings(env,{std::to_string(status),std::to_string(error.revision.code),std::to_string(error.revision.sqlite_code),
    result.entity_key,result.revision_id,std::to_string(result.created),std::to_string(result.applied),error.message});
}
int head(void *opaque,const reader_revision_head *value){static_cast<std::vector<std::string> *>(opaque)->emplace_back(value->revision_id);return 0;}
}
using namespace product_jni;
#define JNI_METHOD(name) Java_org_exreader_host_NativeCatalog_##name
extern "C" JNIEXPORT jstring JNICALL JNI_METHOD(migration)(JNIEnv *env,jclass){
  try{size_t bytes=0;const char *source=reader_catalog_migration(&bytes);return string(env,std::string(source,bytes));}
  catch(const failure &e){report(env,e);}catch(...){report(env,{"java/lang/OutOfMemoryError","Cannot copy migration"});}return nullptr;
}
extern "C" JNIEXPORT jlong JNICALL JNI_METHOD(open)(JNIEnv *env,jclass,jstring path){
  try{
    auto value=std::make_unique<owner>();std::string name=utf8(env,path);reader_catalog_error ce{};reader_revision_error re{};
    database(reader_catalog_open(name.c_str(),&value->catalog,&ce),ce.message);
    database(reader_revisions_open(name.c_str(),&value->revisions,&re),re.message);
    std::lock_guard<std::mutex> lock(registry_mutex);jlong id=++sequence;registry.emplace(id,std::move(value));return id;
  }catch(const failure &e){report(env,e);}catch(...){report(env,{"java/lang/OutOfMemoryError","Cannot open product owner"});}return 0;
}
extern "C" JNIEXPORT void JNICALL JNI_METHOD(close)(JNIEnv *env,jclass,jlong id){
  try{get(id);std::lock_guard<std::mutex> lock(registry_mutex);registry.erase(id);}
  catch(const failure &e){report(env,e);}
}
extern "C" JNIEXPORT jobjectArray JNICALL JNI_METHOD(provider)(JNIEnv *env,jclass,jlong id){return call(env,id,[&](owner &)->jobjectArray{
  Dl_info library{};if(!dladdr(reinterpret_cast<void *>(&sqlite3_open_v2),&library))reject("java/lang/IllegalStateException","Missing product provider module identity");
  std::string options;for(int i=0;sqlite3_compileoption_get(i);++i){if(i)options+=';';options+=sqlite3_compileoption_get(i);}
  return strings(env,{sqlite3_libversion(),sqlite3_sourceid(),SQLITE_SOURCE_ID,library.dli_fname?library.dli_fname:"",options});
});}
extern "C" JNIEXPORT jobjectArray JNICALL JNI_METHOD(page)(JNIEnv *env,jclass,jlong id,jstring nfc,jstring nfd,jstring sort,jstring key,jboolean before,jboolean inclusive,jobject cancel){return call(env,id,[&](owner &o)->jobjectArray{
  std::string a=utf8(env,nfc),b=utf8(env,nfd),s=utf8(env,sort,true),k=utf8(env,key,true);reader_catalog_error e{};rows found{env,cancel,{}};
  database(reader_catalog_local_canonical_page(o.catalog,sort?s.c_str():nullptr,key?k.c_str():nullptr,a.c_str(),b.c_str(),before?-1:1,inclusive?1:0,50,copy,&found,&e),e.message);copied(found);
  jclass c=env->FindClass("org/exreader/host/CatalogStore$ShelfBook");pending(env);
  jobjectArray result=env->NewObjectArray((jsize)found.values.size(),c,nullptr);env->DeleteLocalRef(c);pending(env);
  for(size_t i=0;i<found.values.size();++i){jobject row=shelf_book(env,found.values[i]);env->SetObjectArrayElement(result,(jsize)i,row);env->DeleteLocalRef(row);pending(env);}
  return result;
});}
extern "C" JNIEXPORT jobject JNICALL JNI_METHOD(lookup)(JNIEnv *env,jclass,jlong id,jlong sdk,jstring title){return call(env,id,[&](owner &o)->jobject{
  std::string name=utf8(env,title,true);reader_catalog_error e{};rows values{env,nullptr,{}};int found=0;
  database(reader_catalog_local_lookup(o.catalog,sdk,title?name.c_str():nullptr,copy,&values,&found,&e),e.message);
  copied(values);
  return found?shelf_book(env,values.values.at(0)):nullptr;
});}
extern "C" JNIEXPORT jboolean JNICALL JNI_METHOD(hasLocal)(JNIEnv *env,jclass,jlong id,jlong sdk){return call(env,id,[&](owner &o)->jboolean{
  reader_catalog_error e{};int present=0;database(reader_catalog_has_local(o.catalog,sdk,&present,&e),e.message);return present?JNI_TRUE:JNI_FALSE;
});}
extern "C" JNIEXPORT void JNICALL JNI_METHOD(removeLocal)(JNIEnv *env,jclass,jlong id,jlong sdk){call(env,id,[&](owner &o)->int{
  reader_catalog_error e{};database(reader_catalog_remove_local(o.catalog,sdk,&e),e.message);return 0;
});}
extern "C" JNIEXPORT void JNICALL JNI_METHOD(attach)(JNIEnv *env,jclass,jlong id,jstring format,jstring sha,jlong bytes,jlong sdk,jstring mode,jstring title,jstring author,jstring sort,jboolean favorite){call(env,id,[&](owner &o)->int{
  auto f=utf8(env,format),h=utf8(env,sha),m=utf8(env,mode),t=utf8(env,title),a=utf8(env,author),s=utf8(env,sort);
  reader_catalog_book input{f.c_str(),h.c_str(),t.c_str(),a.c_str(),s.c_str(),m.c_str(),(uint64_t)bytes,sdk,favorite?1:0};reader_catalog_error e{};
  database(reader_catalog_attach(o.catalog,&input,&e),e.message);return 0;
});}
extern "C" JNIEXPORT jstring JNICALL JNI_METHOD(newId)(JNIEnv *env,jclass){
  try{char id[33];reader_revision_error e{};database(reader_revision_new_id(id,&e),e.message);return string(env,id);}
  catch(const failure &e){report(env,e);}catch(...){report(env,{"java/lang/OutOfMemoryError","Cannot allocate command identity"});}return nullptr;
}
extern "C" JNIEXPORT jobjectArray JNICALL JNI_METHOD(metadata)(JNIEnv *env,jclass,jlong id,jstring key){return call(env,id,[&](owner &o)->jobjectArray{
  auto k=utf8(env,key);reader_catalog_error e{};rows values{env,nullptr,{}};int found=0;
  database(reader_catalog_metadata(o.catalog,k.c_str(),copy,&values,&found,&e),e.message);copied(values);if(!found)return nullptr;
  const auto &row=values.values.at(0);size_t colon=row.key.find(':');if(colon==std::string::npos)reject("java/lang/IllegalStateException","Corrupt product original identity");
  return strings(env,{row.format,row.key.substr(colon+1),std::to_string(row.bytes),row.title,row.author,row.sort,std::to_string(row.favorite),std::to_string(row.deleted)});
});}
extern "C" JNIEXPORT jobjectArray JNICALL JNI_METHOD(heads)(JNIEnv *env,jclass,jlong id,jstring kind,jstring key){return call(env,id,[&](owner &o)->jobjectArray{
  auto k=utf8(env,kind),v=utf8(env,key);std::vector<std::string> result;reader_revision_state state{};reader_revision_error e{};
  database(reader_revision_heads(o.revisions,k.c_str(),v.c_str(),head,&result,&state,&e),e.message);return strings(env,result);
});}
extern "C" JNIEXPORT jobjectArray JNICALL JNI_METHOD(book)(JNIEnv *env,jclass,jlong id,jstring revision,jobjectArray heads,jint op,jstring key,jstring format,jstring sha,jlong bytes,jstring title,jstring author,jstring sort,jboolean favorite){return call(env,id,[&](owner &o)->jobjectArray{
  context c(env,o,revision,heads);auto k=utf8(env,key),f=utf8(env,format,true),h=utf8(env,sha,true),t=utf8(env,title,true),a=utf8(env,author,true),s=utf8(env,sort,true);
  reader_book_command input{(reader_command_operation)op,k.c_str(),f.c_str(),h.c_str(),t.c_str(),a.c_str(),s.c_str(),(uint64_t)bytes,favorite?1:0};
  reader_command_result result{};reader_command_error e{};auto status=reader_command_apply_book(&c.native,&input,&result,&e);return command_result(env,status,result,e);
});}
extern "C" JNIEXPORT jobjectArray JNICALL JNI_METHOD(group)(JNIEnv *env,jclass,jlong id,jstring revision,jobjectArray heads,jint op,jint kind,jstring key,jstring name,jstring parent,jlong ordinal){return call(env,id,[&](owner &o)->jobjectArray{
  context c(env,o,revision,heads);auto k=utf8(env,key),n=utf8(env,name,true),p=utf8(env,parent,true);
  if(k.empty())reject("java/lang/IllegalArgumentException","Preallocate and persist group identity");
  reader_group_command input{(reader_command_operation)op,(reader_group_kind)kind,k.c_str(),n.c_str(),p.c_str(),(uint64_t)ordinal};
  reader_command_result result{};reader_command_error e{};auto status=reader_command_apply_group(&c.native,&input,&result,&e);return command_result(env,status,result,e);
});}
extern "C" JNIEXPORT jobjectArray JNICALL JNI_METHOD(membership)(JNIEnv *env,jclass,jlong id,jstring revision,jobjectArray heads,jint op,jint kind,jstring group,jstring book,jlong ordinal){return call(env,id,[&](owner &o)->jobjectArray{
  context c(env,o,revision,heads);auto g=utf8(env,group),b=utf8(env,book);
  reader_membership_command input{(reader_command_operation)op,(reader_group_kind)kind,g.c_str(),b.c_str(),(uint64_t)ordinal};
  reader_command_result result{};reader_command_error e{};auto status=reader_command_apply_membership(&c.native,&input,&result,&e);return command_result(env,status,result,e);
});}
#ifdef READER_PRODUCT_FIXTURES
#include "../../debug/cpp/catalog_fixture.inc"
#endif
