/* SPDX-License-Identifier: MIT */
/* Installed product/session APIs only: deliberately no SDK headers or handle. */
#include <reader_session.h>
#include <reader_metadata.h>
#include <reader_reading_state.h>
#include <catalog.h>
#include <exr_webdav_android.h>
#include <sqlite3.h>
#include <dlfcn.h>
#include <jni.h>
#include <string>
#include <vector>
#include <cstring>
namespace {
struct failed{int code;};
void require(int code){if(code)throw failed{code};}
std::string arg(JNIEnv *env,jstring input){
  if(!input)return {};
  jsize units=env->GetStringLength(input);if(units>16384)throw failed{1};
  const jchar *chars=env->GetStringChars(input,nullptr);if(!chars)throw failed{1};
  char bytes[16385];size_t count=0;reader_command_error error{};
  int code=reader_command_utf16((const uint16_t *)chars,(size_t)units,bytes,sizeof(bytes),&count,&error);
  env->ReleaseStringChars(input,chars);require(code);return std::string(bytes,count);
}
std::string quote(const std::string &text){
  static const char hex[]="0123456789abcdef";std::string out="\"";
  for(unsigned char ch:text){if(ch=='"'||ch=='\\')out+='\\';if(ch<32){out+="\\u00";out+=hex[ch>>4];out+=hex[ch&15];}else out+=(char)ch;}
  return out+'"';
}
jbyteArray bytes(JNIEnv *env,const std::string &text){jbyteArray out=env->NewByteArray((jsize)text.size());if(out)env->SetByteArrayRegion(out,0,(jsize)text.size(),(const jbyte *)text.data());return out;}
template<class F>jbyteArray result(JNIEnv *env,F action){try{return bytes(env,action());}catch(const failed &f){if(env->ExceptionCheck())return nullptr;return bytes(env,"{\"error\":true,\"code\":"+std::to_string(f.code)+"}");}catch(...){if(env->ExceptionCheck())return nullptr;return bytes(env,"{\"error\":true,\"code\":-1}");}}
struct revisions {
  reader_revisions *value=nullptr;
  explicit revisions(const std::string &path){require(reader_revisions_open(path.c_str(),&value,nullptr));}
  ~revisions(){if(value)reader_revisions_close(&value,nullptr);}
};
struct catalog {
  reader_catalog *value=nullptr;
  explicit catalog(const std::string &path){require(reader_catalog_open(path.c_str(),&value,nullptr));}
  ~catalog(){if(value)reader_catalog_close(&value,nullptr);}
};
struct metadata {
  reader_metadata_owner *value=nullptr;
  metadata(const std::string &path,const std::string &pending){require(reader_metadata_open(path.c_str(),pending.c_str(),&value,nullptr));}
  ~metadata(){if(value)reader_metadata_close(&value,nullptr);}
};
struct row {
  std::string key,title,author,sort,format,location;uint64_t length=0;int64_t sdk_id=0;int favorite=0,deleted=0;
};
int copy_row(void *opaque,const reader_catalog_row *input){auto &out=*(row *)opaque;out.key=input->book_key;out.title=input->title;out.author=input->author;out.sort=input->sort_title;out.format=input->format;out.location=input->location_kind?input->location_kind:"";out.length=input->source_bytes;out.sdk_id=input->sdk_book_id;out.favorite=input->favorite;out.deleted=input->deleted;return 0;}
std::string row_json(const row &r,int found){return "{\"present\":"+std::to_string(found)+",\"key\":"+quote(r.key)+",\"title\":"+quote(r.title)+",\"author\":"+quote(r.author)+",\"sort_title\":"+quote(r.sort)+",\"format\":"+quote(r.format)+",\"location\":"+quote(r.location)+",\"bytes\":"+std::to_string(r.length)+",\"sdk_id\":"+std::to_string(r.sdk_id)+",\"favorite\":"+std::to_string(r.favorite)+",\"deleted\":"+std::to_string(r.deleted)+"}";}
int count_outbox(void *opaque,const reader_revision_outbox_row *){++*(size_t *)opaque;return 0;}
}
extern "C" JNIEXPORT jint JNICALL Java_org_exreader_sessionprobe_NativeProduct_bind(JNIEnv *env,jclass){return exr_webdav_android_initialize(env);}
extern "C" JNIEXPORT jbyteArray JNICALL Java_org_exreader_sessionprobe_NativeProduct_provider(JNIEnv *env,jclass){
  Dl_info info{};dladdr((void *)sqlite3_open_v2,&info);std::string options;
  for(int n=0;;n++){const char *option=sqlite3_compileoption_get(n);if(!option)break;if(!options.empty())options+=';';options+=option;}
  return bytes(env,"{\"version\":"+quote(sqlite3_libversion())+",\"runtime_source\":"+quote(sqlite3_sourceid())+",\"header_source\":"+quote(SQLITE_SOURCE_ID)+",\"library\":"+quote(info.dli_fname?info.dli_fname:"")+",\"options\":"+quote(options)+"}");
}
extern "C" JNIEXPORT jbyteArray JNICALL Java_org_exreader_sessionprobe_NativeProduct_prepareBook(JNIEnv *env,jclass,jstring database,jstring pending_file,jstring format,jstring hash,jlong length,jstring title,jstring author,jstring sort_title){
  return result(env,[&]{
    std::string path=arg(env,database),pending=arg(env,pending_file),fmt=arg(env,format),sha=arg(env,hash),name=arg(env,title),writer=arg(env,author),sort=arg(env,sort_title),key=fmt+":"+sha,bootstrap;
    {
      revisions store(path);reader_command_context context{};context.store=store.value;
      reader_book_command input{};input.operation=READER_COMMAND_PUT;input.book_key=key.c_str();input.format=fmt.c_str();input.source_sha256=sha.c_str();input.source_bytes=(uint64_t)length;input.title=name.c_str();input.author=writer.c_str();input.sort_title=sort.c_str();
      reader_command_result committed{};require(reader_command_apply_book(&context,&input,&committed,nullptr));bootstrap=committed.revision_id;
    }
    metadata owner(path,pending);reader_metadata_snapshot *snapshot=nullptr;reader_metadata_result staged{},applied{},finished{};
    require(reader_metadata_prepare_book(owner.value,key.c_str(),&snapshot,nullptr));
    const reader_metadata_view *view=reader_metadata_snapshot_view(snapshot);if(!view){reader_metadata_snapshot_free(snapshot);throw failed{1};}
    reader_book_command edit=view->book;edit.favorite=1;
    int code=reader_metadata_stage_book(owner.value,snapshot,&edit,&staged,nullptr);reader_metadata_snapshot_free(snapshot);require(code);
    require(reader_metadata_apply_pending(owner.value,&applied,nullptr));std::string head=applied.command.revision_id;
    require(reader_metadata_finish_pending(owner.value,&finished,nullptr));
    return "{\"key\":"+quote(key)+",\"bootstrap\":"+quote(bootstrap)+",\"head\":"+quote(head)+",\"metadata_committed\":"+std::to_string(applied.committed)+",\"pending\":"+std::to_string(finished.pending)+"}";
  });
}
extern "C" JNIEXPORT jbyteArray JNICALL Java_org_exreader_sessionprobe_NativeProduct_inspectBook(JNIEnv *env,jclass,jstring database,jstring book_key){
  return result(env,[&]{std::string path=arg(env,database),key=arg(env,book_key),head,title;reader_revision_selection selection{};int status;
    {revisions store(path);char *wire=nullptr;size_t size=0;reader_revision_info info{};
      status=reader_revision_selected(store.value,"book",key.c_str(),&wire,&size,&info,&selection,nullptr);reader_revision_bytes_free(wire);
      if(status==READER_REV_OK){head=info.revision_id;char *copy=nullptr;require(reader_revision_book_title(store.value,info.revision_id,&copy,nullptr));title=copy;reader_revision_bytes_free(copy);}
    }
    row value;int found=0;{catalog store(path);require(reader_catalog_metadata(store.value,key.c_str(),copy_row,&value,&found,nullptr));}
    return "{\"status\":"+std::to_string(status)+",\"selection\":"+std::to_string((int)selection.kind)+",\"heads\":"+std::to_string(selection.graph.heads)+",\"head\":"+quote(head)+",\"selected_title\":"+quote(title)+",\"catalog\":"+row_json(value,found)+"}";
  });
}
extern "C" JNIEXPORT jbyteArray JNICALL Java_org_exreader_sessionprobe_NativeProduct_projectBook(JNIEnv *env,jclass,jstring database,jstring book_key,jstring revision,jstring sort_title){
  return result(env,[&]{std::string path=arg(env,database),key=arg(env,book_key),head=arg(env,revision),sort=arg(env,sort_title);revisions store(path);
    int status=reader_revision_project(store.value,"book",key.c_str(),head.c_str(),sort.c_str(),nullptr,nullptr);
    return "{\"status\":"+std::to_string(status)+"}";
  });
}
extern "C" JNIEXPORT jbyteArray JNICALL Java_org_exreader_sessionprobe_NativeProduct_attach(JNIEnv *env,jclass,jstring database,jstring format,jstring hash,jlong length,jlong sdk_id,jstring location,jstring title,jstring author,jstring sort_title){
  return result(env,[&]{std::string path=arg(env,database),fmt=arg(env,format),sha=arg(env,hash),mode=arg(env,location),name=arg(env,title),writer=arg(env,author),sort=arg(env,sort_title);catalog store(path);
    reader_catalog_book book{fmt.c_str(),sha.c_str(),name.c_str(),writer.c_str(),sort.c_str(),mode.c_str(),(uint64_t)length,(int64_t)sdk_id,0};
    int status=reader_catalog_attach(store.value,&book,nullptr);return "{\"status\":"+std::to_string(status)+"}";
  });
}
extern "C" JNIEXPORT jbyteArray JNICALL Java_org_exreader_sessionprobe_NativeProduct_outbox(JNIEnv *env,jclass,jstring database){
  return result(env,[&]{revisions store(arg(env,database));size_t count=0;require(reader_revision_outbox(store.value,100,count_outbox,&count,nullptr));return "{\"count\":"+std::to_string(count)+"}";});
}
extern "C" JNIEXPORT jlong JNICALL Java_org_exreader_sessionprobe_NativeProduct_create(JNIEnv *env,jclass,jstring database,jstring private_directory,jstring original_directory,jstring account,jstring root,jstring authorization,jint timeout){
  try{std::string path=arg(env,database),directory=arg(env,private_directory),originals=arg(env,original_directory),id=arg(env,account),url=arg(env,root),auth=arg(env,authorization);
    reader_session_config config{};config.product_path=path.c_str();config.private_directory=directory.c_str();config.original_directory=originals.c_str();config.account_id=id.c_str();config.dav.root_url=url.c_str();config.dav.authorization=auth.c_str();config.dav.timeout_ms=(unsigned)timeout;
    reader_session *session=nullptr;if(reader_session_create(&config,&session)!=READER_SESSION_OK)return 0;return (jlong)(intptr_t)session;
  }catch(...){return 0;}
}
extern "C" JNIEXPORT jbyteArray JNICALL Java_org_exreader_sessionprobe_NativeProduct_command(JNIEnv *env,jclass,jlong token,jint action){
  return result(env,[&]{reader_session *session=(reader_session *)(intptr_t)token;int code=0;reader_session_snapshot view{};
    if(action==1)code=reader_session_start(session);else if(action==2)code=reader_session_cancel(session);else if(action==3)code=reader_session_request_close(session);else if(action==4)code=reader_session_destroy(&session);else if(action!=0)throw failed{1};
    if(session)require(reader_session_observe(session,&view));else view.state=READER_SESSION_CLOSED;
    return "{\"code\":"+std::to_string(code)+",\"alive\":"+(session?"true":"false")+",\"state\":"+std::to_string((int)view.state)+",\"status\":"+std::to_string((int)view.status)+",\"attempt\":"+std::to_string(view.attempt)+",\"sweeps\":"+std::to_string(view.completed_sweeps)+",\"steps\":"+std::to_string(view.steps)+",\"shard\":"+std::to_string(view.shard)+",\"completed_shards\":"+std::to_string(view.completed_shards)+",\"pushed\":"+std::to_string(view.pushed)+",\"pulled\":"+std::to_string(view.pulled)+",\"originals_verified\":"+std::to_string(view.originals_verified)+",\"dav_code\":"+std::to_string(view.error.dav_code)+",\"revision_code\":"+std::to_string(view.error.revision_code)+",\"http_status\":"+std::to_string(view.error.http_status)+",\"full_library_complete\":"+std::to_string(view.full_library_complete)+"}";
  });
}
#ifdef EXR_WEBDAV_ANDROID_TESTING
extern "C" void exr_webdav_android_test_stats(uint64_t out[4]);
#endif
extern "C" JNIEXPORT jbyteArray JNICALL Java_org_exreader_sessionprobe_NativeProduct_stats(JNIEnv *env,jclass){
  uint64_t values[4]={0};
#ifdef EXR_WEBDAV_ANDROID_TESTING
  exr_webdav_android_test_stats(values);
#endif
  return bytes(env,"{\"clients\":"+std::to_string(values[0])+",\"uploads\":"+std::to_string(values[1])+",\"attaches\":"+std::to_string(values[2])+",\"detaches\":"+std::to_string(values[3])+"}");
}
extern "C" JNIEXPORT jbyteArray JNICALL Java_org_exreader_sessionprobe_NativeProduct_readingAppend(JNIEnv *env,jclass,jstring database,jobjectArray fields,jlongArray numbers){
  return result(env,[&]{
    if(env->GetArrayLength(fields)!=9||env->GetArrayLength(numbers)!=4)throw failed{1};
    std::string value[9];bool scoped=false;for(int n=0;n<9;n++){jstring input=(jstring)env->GetObjectArrayElement(fields,n);value[n]=arg(env,input);if(n==5&&input)scoped=true;if(input)env->DeleteLocalRef(input);}
    jlong number[4];env->GetLongArrayRegion(numbers,0,4,number);if(number[0]<1||number[0]>3||number[1]<0||number[2]<0||number[3]<number[2])throw failed{1};
    revisions store(arg(env,database));char id[33],annotation[33];require(reader_revision_new_id(id,nullptr));require(reader_revision_new_id(annotation,nullptr));
    std::string entity=value[1]+(value[0]=="annotation"?":"+std::string(annotation):"");std::vector<std::string> observed;reader_revision_state graph{};
    require(reader_revision_heads(store.value,value[0].c_str(),entity.c_str(),[](void *context,const reader_revision_head *head){((std::vector<std::string> *)context)->emplace_back(head->revision_id);return 0;},&observed,&graph,nullptr));
    std::vector<const char *> parents;for(auto &head:observed)parents.push_back(head.c_str());
    reader_rs_envelope envelope{};envelope.revision_id=id;envelope.annotation_id=annotation;envelope.operation="put";envelope.entity_kind=value[0].c_str();envelope.book_key=value[1].c_str();envelope.parents=parents.data();envelope.parent_count=parents.size();envelope.note_text=value[7].c_str();envelope.parser_version=value[8].c_str();
    exr_anchor anchor{};anchor.start=(size_t)number[2];anchor.end=(size_t)number[3];anchor.exact=value[2].data();anchor.prefix=value[3].data();anchor.suffix=value[4].data();anchor.chapter=scoped?value[5].data():nullptr;
    exr_fixed_anchor fixed{};fixed.start=anchor.start;fixed.end=anchor.end;fixed.page_id=value[6].data();fixed.exact=value[2].data();fixed.exact_size=value[2].size();fixed.prefix=value[3].data();fixed.prefix_size=value[3].size();fixed.suffix=value[4].data();fixed.suffix_size=value[4].size();
    reader_rs_capture capture{};capture.mode=(reader_rs_mode)number[0];capture.anchor=&anchor;capture.fixed=&fixed;capture.part_path=value[6].c_str();capture.page=(size_t)number[1];
    char *wire=nullptr;size_t count=0;reader_rs_error error{};require(reader_rs_encode_v2(store.value,&envelope,&capture,(size_t)number[1],&wire,&count,&error));std::string exact(wire,count);reader_rs_free(wire);
    reader_revision_info info{};int created=0;require(reader_revision_local_reading(store.value,exact.data(),exact.size(),parents.data(),parents.size(),&info,&created,nullptr));if(!created)throw failed{1};
    return "{\"revision\":"+quote(id)+",\"entity\":"+quote(entity)+",\"wire\":"+quote(exact)+",\"sha256\":"+quote(info.sha256)+"}";
  });
}
extern "C" JNIEXPORT jbyteArray JNICALL Java_org_exreader_sessionprobe_NativeProduct_readingDecode(JNIEnv *env,jclass,jstring database,jstring revision){
  return result(env,[&]{
    revisions store(arg(env,database));std::string id=arg(env,revision);char *wire=nullptr;size_t count=0;reader_revision_info info{};require(reader_revision_get(store.value,id.c_str(),&wire,&count,&info,nullptr));std::string exact(wire,count);reader_revision_bytes_free(wire);
    char *selected=nullptr;size_t selected_count=0;reader_revision_selection selection{};
    int status=reader_revision_selected(store.value,info.entity_kind,info.entity_key,&selected,&selected_count,nullptr,&selection,nullptr);
    bool selected_this=status==READER_REV_OK&&std::string(selected,selected_count)==exact;reader_revision_bytes_free(selected);
    reader_rs_record record{};reader_rs_error error{};require(reader_rs_decode(store.value,exact.data(),exact.size(),&record,&error));
    std::string out="{\"wire\":"+quote(exact)+",\"sha256\":"+quote(info.sha256)+",\"safe_selected\":"+(selected_this?"true":"false")+",\"kind\":"+quote(record.entity_kind)+",\"book_key\":"+quote(record.book_key)+",\"mode\":"+std::to_string((int)record.mode)+",\"anchor_version\":"+std::to_string(record.anchor_version)+",\"start\":"+std::to_string(record.start)+",\"end\":"+std::to_string(record.end)+",\"part\":"+std::to_string(record.part)+",\"page\":"+std::to_string(record.page)+",\"part_path\":"+quote(record.part_path?record.part_path:"")+",\"page_id\":"+quote(record.page_id?record.page_id:"")+",\"exact\":"+quote(std::string(record.exact?record.exact:"",record.exact_size))+",\"prefix\":"+quote(std::string(record.prefix?record.prefix:"",record.prefix_size))+",\"suffix\":"+quote(std::string(record.suffix?record.suffix:"",record.suffix_size))+",\"chapter\":"+(record.chapter?quote(record.chapter):"null")+"}";
    reader_rs_record_free(&record);return out;
  });
}
