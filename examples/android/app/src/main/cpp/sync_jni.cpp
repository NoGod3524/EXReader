/* SPDX-License-Identifier: MIT */
#include <jni.h>
#include <reader_session.h>
#ifdef READER_HOST_WAVE3
#include <reader_sync_view.h>
#endif
#include <reader_projection.h>
#include <catalog.h>
#include <exr_webdav_android.h>
#include <algorithm>
#include <map>
#include <mutex>
#include <string>
#include <vector>
#include <stdexcept>
#ifdef EXR_READER_SELECTOR_BYTES_CANDIDATE
#define reader_revisions_open reader_revisions_open_raw_v3
#define reader_revision_entities_page reader_revision_entities_page_raw_v3
#define reader_revision_book_title reader_revision_book_title_raw_v3
#define reader_revision_project reader_revision_project_raw_v3
#define reader_organization_project_page reader_organization_project_page_raw_v3
#define reader_session_create reader_session_create_raw_v3
#endif

/* Shared strict Unicode conversion from the existing product JNI. */
namespace product_jni {
std::string utf8(JNIEnv *,jstring,bool optional=false);
jobjectArray strings(JNIEnv *,const std::vector<std::string> &);
void pending(JNIEnv *);
}
namespace {
std::mutex sessions_mutex;
std::map<jlong,reader_session *> sessions;
jlong next_session=0;
void fail(JNIEnv *env){if(!env->ExceptionCheck()){jclass type=env->FindClass("java/lang/IllegalStateException");if(type)env->ThrowNew(type,"同步请求未完成；原书与已提交记录保留");}}
void need(int code){if(code)throw std::runtime_error("native operation refused");}
void wipe(std::string &value){volatile char *bytes=value.empty()?nullptr:&value[0];for(size_t n=0;n<value.size();n++)bytes[n]=0;}
struct revisions {reader_revisions *p=nullptr;explicit revisions(const std::string &path){need(reader_revisions_open(path.c_str(),&p,nullptr));}~revisions(){if(p)reader_revisions_close(&p,nullptr);}};
struct catalog {reader_catalog *p=nullptr;explicit catalog(const std::string &path){need(reader_catalog_open(path.c_str(),&p,nullptr));}~catalog(){if(p)reader_catalog_close(&p,nullptr);}};
struct entity {std::string key,head;reader_revision_selection selection{};reader_revision_info info{};};
struct page {std::vector<entity> rows;bool memory=false;};
int copy_entity(void *context,const reader_revision_entity_row *input){auto &out=*(page *)context;try{out.rows.push_back({input->entity_key,input->info.revision_id,input->selection,input->info});return 0;}catch(...){out.memory=true;return 1;}}
struct metadata {std::vector<std::string> fields;int64_t local=0;bool memory=false;};
int copy_metadata(void *context,const reader_catalog_row *input){auto &out=*(metadata *)context;try{out.fields={input->format,input->book_key,input->title,input->author,std::to_string(input->source_bytes),std::to_string(input->favorite),std::to_string(input->sdk_book_id)};out.local=input->sdk_book_id;return 0;}catch(...){out.memory=true;return 1;}}
}
extern "C" JNIEXPORT jint JNICALL Java_org_exreader_host_NativeSync_bind(JNIEnv *env,jclass){return exr_webdav_android_initialize(env);}
extern "C" JNIEXPORT jboolean JNICALL Java_org_exreader_host_NativeSync_validRoot(JNIEnv *env,jclass,jstring root){
  try{std::string url=product_jni::utf8(env,root);exr_webdav_config config{};config.root_url=url.c_str();exr_webdav_client *client=nullptr;int status=exr_webdav_create(&config,&client,nullptr);if(client)exr_webdav_free(client);return status==EXR_DAV_OK;}catch(...){return JNI_FALSE;}
}
extern "C" JNIEXPORT jlong JNICALL Java_org_exreader_host_NativeSync_create(JNIEnv *env,jclass,jstring product,jstring cache,jstring originals,jstring account,jstring root,jbyteArray authorization){
  std::string secret;
  try{
    if(!authorization)throw std::runtime_error("credential absent");jsize length=env->GetArrayLength(authorization);if(length<1||length>2048)throw std::runtime_error("credential length");secret.resize((size_t)length);env->GetByteArrayRegion(authorization,0,length,(jbyte *)secret.data());product_jni::pending(env);if(secret.find_first_of(std::string("\0\r\n",3))!=std::string::npos)throw std::runtime_error("invalid authorization header");
    std::string path=product_jni::utf8(env,product),directory=product_jni::utf8(env,cache),staged=product_jni::utf8(env,originals),id=product_jni::utf8(env,account),url=product_jni::utf8(env,root);
    reader_session_config config{};config.product_path=path.c_str();config.private_directory=directory.c_str();config.original_directory=staged.c_str();config.account_id=id.c_str();config.dav.root_url=url.c_str();config.dav.authorization=secret.c_str();config.dav.timeout_ms=15000;
    std::lock_guard<std::mutex> lock(sessions_mutex);jlong token=++next_session;auto entry=sessions.emplace(token,nullptr);
    reader_session *session=nullptr;int code=reader_session_create(&config,&session);wipe(secret);if(code){sessions.erase(entry.first);need(code);}entry.first->second=session;return token;
  }catch(...){wipe(secret);fail(env);return 0;}
}
extern "C" JNIEXPORT jlongArray JNICALL Java_org_exreader_host_NativeSync_command(JNIEnv *env,jclass,jlong token,jint action){
  try{
    std::lock_guard<std::mutex> lock(sessions_mutex);auto found=sessions.find(token);if(found==sessions.end())throw std::runtime_error("closed session");reader_session *session=found->second;int code=0;reader_session_snapshot view{};
    if(action==1)code=reader_session_start(session);else if(action==2)code=reader_session_cancel(session);else if(action==3)code=reader_session_request_close(session);else if(action==4)code=reader_session_destroy(&session);else if(action!=0)throw std::runtime_error("unknown action");
    if(session)need(reader_session_observe(session,&view));else{view.state=READER_SESSION_CLOSED;sessions.erase(found);}
    jlong data[9]={code,(jlong)view.state,(jlong)view.status,(jlong)view.error.dav_code,(jlong)view.error.http_status,(jlong)view.completed_shards,(jlong)view.pushed,(jlong)view.pulled,(jlong)view.full_library_complete};jlongArray out=env->NewLongArray(9);if(out)env->SetLongArrayRegion(out,0,9,data);return out;
  }catch(...){fail(env);return nullptr;}
}
extern "C" JNIEXPORT jobjectArray JNICALL Java_org_exreader_host_NativeSync_books(JNIEnv *env,jclass,jstring product,jstring after){
  try{
    std::string path=product_jni::utf8(env,product),cursor=product_jni::utf8(env,after,true);revisions store(path);catalog catalog_store(path);page copied;
    need(reader_revision_entities_page(store.p,"book",cursor.empty()?nullptr:cursor.c_str(),1,50,copy_entity,&copied,nullptr));if(copied.memory)throw std::bad_alloc();
    jclass row_type=env->FindClass("[Ljava/lang/String;");product_jni::pending(env);jobjectArray out=env->NewObjectArray((jsize)copied.rows.size(),row_type,nullptr);env->DeleteLocalRef(row_type);product_jni::pending(env);
    for(size_t n=0;n<copied.rows.size();n++){
      const auto &row=copied.rows[n];std::string title=row.key;bool safe=row.selection.kind==READER_SELECTION_SAFE&&!row.selection.graph.deleted;char *name=nullptr;
      if(safe){need(reader_revision_book_title(store.p,row.head.c_str(),&name,nullptr));title=name;reader_revision_bytes_free(name);}
      metadata local;int present=0;need(reader_catalog_metadata(catalog_store.p,row.key.c_str(),copy_metadata,&local,&present,nullptr));if(local.memory)throw std::bad_alloc();size_t colon=row.key.find(':');if(colon==std::string::npos)throw std::runtime_error("invalid global key");
      jobjectArray values=product_jni::strings(env,{row.key,row.head,title,row.key.substr(0,colon),row.key.substr(colon+1),std::to_string(row.info.source_bytes),std::to_string((int)row.selection.kind),std::to_string(row.selection.graph.deleted),std::to_string(local.local)});env->SetObjectArrayElement(out,(jsize)n,values);env->DeleteLocalRef(values);product_jni::pending(env);
    }
    return out;
  }catch(...){fail(env);return nullptr;}
}
extern "C" JNIEXPORT jobjectArray JNICALL Java_org_exreader_host_NativeSync_project(JNIEnv *env,jclass,jstring product,jstring key,jstring revision,jstring sort){
  try{
    std::string path=product_jni::utf8(env,product),entity=product_jni::utf8(env,key),head=product_jni::utf8(env,revision),title=product_jni::utf8(env,sort);revisions store(path);need(reader_revision_project(store.p,"book",entity.c_str(),head.c_str(),title.c_str(),nullptr,nullptr));catalog current(path);metadata value;int present=0;need(reader_catalog_metadata(current.p,entity.c_str(),copy_metadata,&value,&present,nullptr));if(value.memory)throw std::bad_alloc();if(!present||value.fields.size()!=7)throw std::runtime_error("projected metadata absent");return product_jni::strings(env,value.fields);
  }catch(...){fail(env);return nullptr;}
}
extern "C" JNIEXPORT jint JNICALL Java_org_exreader_host_NativeSync_projectBook(JNIEnv *env,jclass,jstring product,jstring key,jstring revision,jstring sort){
  try{
    std::string path=product_jni::utf8(env,product),entity=product_jni::utf8(env,key),head=product_jni::utf8(env,revision),title=product_jni::utf8(env,sort);
    revisions store(path);auto status=reader_revision_project(store.p,"book",entity.c_str(),head.c_str(),title.c_str(),nullptr,nullptr);
    if(status==READER_REV_UNSAFE)return 1;need(status);return 0;
  }catch(...){fail(env);return -1;}
}
extern "C" JNIEXPORT jobjectArray JNICALL Java_org_exreader_host_NativeSync_projectOrganization(JNIEnv *env,jclass,jstring product,jstring kind,jstring after){
  try{
    std::string path=product_jni::utf8(env,product),type=product_jni::utf8(env,kind),cursor=product_jni::utf8(env,after,true);revisions store(path);
    reader_organization_projection_row rows[50]{};size_t count=0;
    need(reader_organization_project_page(store.p,type.c_str(),cursor.empty()?nullptr:cursor.c_str(),50,rows,&count,nullptr));
    jclass row_type=env->FindClass("[Ljava/lang/String;");product_jni::pending(env);jobjectArray out=env->NewObjectArray((jsize)count,row_type,nullptr);env->DeleteLocalRef(row_type);product_jni::pending(env);
    for(size_t i=0;i<count;i++){jobjectArray row=product_jni::strings(env,{rows[i].entity_key,std::to_string((int)rows[i].result)});env->SetObjectArrayElement(out,(jsize)i,row);env->DeleteLocalRef(row);product_jni::pending(env);}
    return out;
  }catch(...){fail(env);return nullptr;}
}
#ifdef READER_PRODUCT_FIXTURES
extern "C" JNIEXPORT jint JNICALL Java_org_exreader_host_NativeSyncProbe_sessions(JNIEnv *,jclass){std::lock_guard<std::mutex> lock(sessions_mutex);return (jint)sessions.size();}
#endif
#ifdef READER_HOST_WAVE3
/* Read-only status view over the session this controller already owns. Row 0 holds the
   summary, the remaining rows hold the bounded pending page. No start/cancel/ack/retry. */
extern "C" JNIEXPORT jobjectArray JNICALL Java_org_exreader_host_NativeSync_view(JNIEnv *env,jclass,jlong token,jstring product){
  reader_sync_view_snapshot *snapshot=nullptr;
  try{
    std::string path=product_jni::utf8(env,product);revisions store(path);
    std::lock_guard<std::mutex> lock(sessions_mutex);auto found=sessions.find(token);if(found==sessions.end())throw std::runtime_error("closed session");
    reader_sync_view_options options{};options.row_limit=20;options.detect_conflicts=1;reader_sync_view_error error{};
    if(reader_sync_view_capture(found->second,store.p,&options,&snapshot,&error)!=READER_SYNC_VIEW_OK)throw std::runtime_error("sync view refused");
    reader_sync_view_summary summary{};if(reader_sync_view_summary_get(snapshot,&summary)!=READER_SYNC_VIEW_OK)throw std::runtime_error("sync summary unavailable");
    std::vector<std::vector<std::string>> out;
    out.push_back({reader_sync_view_phase_text(summary.phase),reader_sync_view_reason_text(summary.reason),std::to_string(summary.session_status),std::to_string(summary.http_status),std::to_string(summary.dav_code),
      std::to_string(summary.revision_code),std::to_string(summary.attempt),std::to_string(summary.completed_sweeps),std::to_string(summary.operations),std::to_string(summary.pushed_operations),
      std::to_string(summary.pulled_operations),std::to_string(summary.originals_verified_operations),std::to_string(summary.transfer_bytes),std::to_string(summary.completed_shards),std::to_string(summary.shard_count),
      std::to_string(summary.sweep_complete),std::to_string(summary.library_complete),std::to_string(summary.resumable),std::to_string(summary.outbox_included),std::to_string(summary.pending_records),
      std::to_string(summary.retried_records),std::to_string(summary.conflict_records),std::to_string(summary.more_may_exist),std::to_string(summary.conflicts_checked)});
    reader_sync_view_row rows[READER_SYNC_VIEW_MAX_ROWS];size_t copied=0;
    if(summary.pending_records>0){if(reader_sync_view_rows(snapshot,0,rows,READER_SYNC_VIEW_MAX_ROWS,&copied)!=READER_SYNC_VIEW_OK)throw std::runtime_error("sync rows unavailable");}
    for(size_t i=0;i<copied;i++)out.push_back({rows[i].revision_id,rows[i].entity_kind,rows[i].operation,std::to_string(rows[i].bytes),std::to_string(rows[i].attempts),
      std::to_string(rows[i].last_revision_code),reader_sync_view_reason_text(rows[i].last_reason),std::to_string(rows[i].conflict)});
    reader_sync_view_release(&snapshot);
    jclass row_type=env->FindClass("[Ljava/lang/String;");product_jni::pending(env);jobjectArray result=env->NewObjectArray((jsize)out.size(),row_type,nullptr);env->DeleteLocalRef(row_type);product_jni::pending(env);
    for(size_t i=0;i<out.size();i++){jobjectArray values=product_jni::strings(env,out[i]);env->SetObjectArrayElement(result,(jsize)i,values);env->DeleteLocalRef(values);product_jni::pending(env);}
    return result;
  }catch(...){reader_sync_view_release(&snapshot);fail(env);return nullptr;}
}
#endif
