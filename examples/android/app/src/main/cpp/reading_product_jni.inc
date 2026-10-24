/* SPDX-License-Identifier: MIT */
/* Included in the existing product owner translation unit. No SDK calls/SQL. */
#include <reader_reading_commands.h>
#include <reader_annotation_view.h>
#include <cstring>
#include <array>
#include <cstdio>

namespace reading_product {
using product_jni::pending;
using product_jni::reject;
struct local_frame {
  JNIEnv *env;bool active=true;
  explicit local_frame(JNIEnv *e):env(e){if(env->PushLocalFrame(64)<0)pending(env);}
  ~local_frame(){if(active)env->PopLocalFrame(nullptr);}
  jobject keep(jobject value){active=false;return env->PopLocalFrame(value);}
};
struct control {
  JNIEnv *env;jobject task;jmethodID check;
  control(JNIEnv *e,jobject t):env(e),task(t){if(!task)reject("java/lang/IllegalArgumentException","Reading control is required");jclass type=env->GetObjectClass(task);pending(env);check=env->GetMethodID(type,"check","()V");env->DeleteLocalRef(type);pending(env);}
  void poll(){env->CallVoidMethod(task,check);pending(env);}
  static int cancelled(void *opaque){auto &c=*static_cast<control *>(opaque);if(c.env->ExceptionCheck())return 1;c.env->CallVoidMethod(c.task,c.check);return c.env->ExceptionCheck()?1:0;}
};
struct view {
  reader_av_view *value=nullptr;
  view(reader_revisions *store,const std::string &book,control &c){reader_av_options options{};options.struct_size=sizeof(options);options.cancel=control::cancelled;options.cancel_context=&c;options.max_page_bytes=READER_AV_PAGE_BYTES_MIN;reader_av_error error{};auto status=reader_av_open(store,book.c_str(),&options,&value,&error);pending(c.env);if(status!=READER_AV_OK)reject("java/lang/IllegalStateException","Reading list cannot be opened");}
  ~view(){if(value)reader_av_close(&value,nullptr);}
};
struct page {reader_av_page value{};~page(){reader_av_page_free(&value);}};
struct decoded {reader_rs_record value{};~decoded(){reader_rs_record_free(&value);}};
struct wire {char *value=nullptr;size_t bytes=0;reader_revision_info info{};~wire(){reader_revision_bytes_free(value);}};
static std::string text(JNIEnv *env,jstring value,bool optional=false){return product_jni::utf8(env,value,optional);}
static jbyteArray bytes(JNIEnv *env,const char *value,size_t size){if(!value)return nullptr;jbyteArray result=env->NewByteArray(static_cast<jsize>(size));pending(env);if(size)env->SetByteArrayRegion(result,0,static_cast<jsize>(size),reinterpret_cast<const jbyte *>(value));pending(env);return result;}
static jobjectArray strings(JNIEnv *env,const std::array<const char *,5> &values){jclass type=env->FindClass("java/lang/String");pending(env);jobjectArray result=env->NewObjectArray(5,type,nullptr);pending(env);for(size_t i=0;i<values.size();i++)if(values[i]){jstring string=product_jni::string(env,values[i]);env->SetObjectArrayElement(result,static_cast<jsize>(i),string);env->DeleteLocalRef(string);pending(env);}return result;}
static jobject capture(JNIEnv *env,const std::string &book,const reader_av_item &item){
  if(!item.has_location)return nullptr;local_frame frame(env);jclass byte_type=env->FindClass("[B");pending(env);jobjectArray selected=env->NewObjectArray(3,byte_type,nullptr);pending(env);
  const char *data[]={item.exact,item.prefix,item.suffix};size_t size[]={item.exact_size,item.prefix_size,item.suffix_size};for(size_t i=0;i<3;i++){jbyteArray copy=bytes(env,data[i],size[i]);env->SetObjectArrayElement(selected,static_cast<jsize>(i),copy);if(copy)env->DeleteLocalRef(copy);pending(env);}
  jlong values[]={item.mode,item.mode==READER_AV_MODE_EPUB?(item.has_part?static_cast<jlong>(item.part):-1):item.mode==READER_AV_MODE_FIXED?static_cast<jlong>(item.page):0,static_cast<jlong>(item.start),static_cast<jlong>(item.end)};jlongArray numeric=env->NewLongArray(4);pending(env);env->SetLongArrayRegion(numeric,0,4,values);pending(env);
  jobjectArray route=strings(env,{book.c_str(),item.parser_version,item.part_path,item.page_id,item.chapter});jclass type=env->FindClass("org/exreader/host/ReadingCapture");pending(env);jmethodID constructor=env->GetMethodID(type,"<init>","([J[Ljava/lang/String;[[B)V");pending(env);jobject result=env->NewObject(type,constructor,numeric,route,selected);pending(env);return frame.keep(result);
}
static jobject record(JNIEnv *env,const std::string &book,const reader_av_item &item){
  local_frame frame(env);jlong fields[]={item.state,item.kind,static_cast<jlong>(item.revisions),static_cast<jlong>(item.heads),static_cast<jlong>(item.missing_parents),static_cast<jlong>(item.foreign_parents),item.deleted,item.requires_restore,static_cast<jlong>(item.wire_bytes),item.mode,static_cast<jlong>(item.anchor_version),item.legacy_anchor};jlongArray numeric=env->NewLongArray(12);pending(env);env->SetLongArrayRegion(numeric,0,12,fields);pending(env);
  std::vector<std::string> values={item.annotation_id,item.revision_id,item.operation,item.sha256,item.note_text?std::string(item.note_text,item.note_size):std::string(),book};jobjectArray fields_text=product_jni::strings(env,values);jobject selected=capture(env,book,item);jclass type=env->FindClass("org/exreader/host/ReadingRecord");pending(env);jmethodID constructor=env->GetMethodID(type,"<init>","([J[Ljava/lang/String;Lorg/exreader/host/ReadingCapture;)V");pending(env);jobject result=env->NewObject(type,constructor,numeric,fields_text,selected);pending(env);return frame.keep(result);
}
static reader_av_state selection(reader_selection_kind state){switch(state){case READER_SELECTION_SAFE:return READER_AV_STATE_SAFE;case READER_SELECTION_CONCURRENT:return READER_AV_STATE_CONCURRENT;case READER_SELECTION_PENDING_PARENTS:return READER_AV_STATE_PENDING_PARENTS;case READER_SELECTION_BLOCKED_RESTORE:return READER_AV_STATE_BLOCKED_RESTORE;default:return READER_AV_STATE_MISSING;}}
static void capture_fields(reader_av_item &item,const reader_rs_record &r){
  std::snprintf(item.parser_version,sizeof(item.parser_version),"%s",r.parser_version);item.mode=static_cast<reader_av_mode>(r.mode);item.has_location=r.has_location;item.anchor_version=r.anchor_version;item.legacy_anchor=r.anchor_version==1;item.has_part=r.mode==READER_RS_EPUB_CHAPTER&&r.anchor_version==2;item.part=r.part;item.has_page=r.mode==READER_RS_FIXED_PAGE;item.page=r.page;item.start=r.start;item.end=r.end;item.part_path=r.part_path;item.page_id=r.page_id;item.exact=r.exact;item.prefix=r.prefix;item.suffix=r.suffix;item.exact_size=r.exact_size;item.prefix_size=r.prefix_size;item.suffix_size=r.suffix_size;item.chapter=r.chapter;item.note_text=r.note_text;item.note_size=r.note_text?std::strlen(r.note_text):0;
}
static jobject selected(JNIEnv *env,reader_revisions *store,const std::string &book,const std::string &id,const std::string &expected,bool progress,control &c){
  c.poll();wire retained;reader_revision_selection selected{};reader_revision_error error{};std::string key=progress?book:book+":"+id;auto status=reader_revision_selected(store,progress?"progress":"annotation",key.c_str(),&retained.value,&retained.bytes,&retained.info,&selected,&error);c.poll();
  if(status!=READER_REV_OK&&status!=READER_REV_NOT_FOUND&&status!=READER_REV_UNSAFE)reject("java/lang/IllegalStateException","Reading graph cannot be read");
  reader_av_item item{};item.state=selection(selected.kind);item.kind=progress?static_cast<reader_av_kind>(5):READER_AV_KIND_UNAVAILABLE;item.revisions=selected.graph.revisions;item.heads=selected.graph.heads;item.missing_parents=selected.graph.missing_parents;item.foreign_parents=selected.graph.foreign_parents;item.deleted=selected.graph.deleted;item.requires_restore=selected.graph.requires_restore;if(!progress)std::snprintf(item.annotation_id,sizeof(item.annotation_id),"%s",id.c_str());
  decoded data;
  if(status==READER_REV_OK){
    if(!expected.empty()&&expected!=retained.info.revision_id)reject("java/lang/IllegalStateException","Reading record changed; refresh");reader_rs_error decode{};if(reader_rs_decode(store,retained.value,retained.bytes,&data.value,&decode)!=READER_RS_OK)reject("java/lang/IllegalStateException","Reading selector cannot be decoded");auto &r=data.value;if(book!=r.book_key||std::strcmp(r.entity_kind,progress?"progress":"annotation")||(!progress&&id!=r.annotation_id))reject("java/lang/IllegalStateException","Reading entity identity differs");
    std::snprintf(item.revision_id,sizeof(item.revision_id),"%s",retained.info.revision_id);std::snprintf(item.operation,sizeof(item.operation),"%s",retained.info.operation);std::snprintf(item.sha256,sizeof(item.sha256),"%s",retained.info.sha256);std::snprintf(item.parser_version,sizeof(item.parser_version),"%s",r.parser_version);item.wire_bytes=retained.bytes;capture_fields(item,r);
    if(!progress)item.kind=item.deleted?READER_AV_KIND_TOMBSTONE:r.start==r.end?READER_AV_KIND_BOOKMARK:item.note_size?READER_AV_KIND_NOTE:READER_AV_KIND_HIGHLIGHT;
  }else if(!expected.empty())reject("java/lang/IllegalStateException","Reading record is no longer a safe head");
  return record(env,book,item);
}
static std::string input_bytes(JNIEnv *env,jbyteArray input,size_t maximum,bool optional){if(!input){if(optional)return {};reject("java/lang/IllegalArgumentException","Reading bytes are required");}jsize length=env->GetArrayLength(input);if(static_cast<size_t>(length)>maximum)reject("java/lang/IllegalArgumentException","Reading bytes exceed their limit");std::string result(static_cast<size_t>(length),'\0');if(length)env->GetByteArrayRegion(input,0,length,reinterpret_cast<jbyte *>(&result[0]));pending(env);return result;}
}

extern "C" JNIEXPORT jobject JNICALL Java_org_exreader_host_NativeReadingProduct_nativePage(JNIEnv *env,jclass,jlong handle,jstring book,jstring after,jboolean before,jobject task){
  return product_jni::call(env,handle,[&](product_jni::owner &owner)->jobject{
    using namespace reading_product;control c(env,task);c.poll();std::string key=text(env,book),cursor=text(env,after,true);view snapshot(owner.revisions,key,c);reader_av_cursor from{};reader_av_error error{};if(reader_av_cursor_start(snapshot.value,before?-1:1,&from,&error)!=READER_AV_OK)reject("java/lang/IllegalStateException","Reading cursor cannot start");if(!cursor.empty()){if(cursor.size()!=32)reject("java/lang/IllegalArgumentException","Invalid reading cursor");from.has_after=1;std::memcpy(from.after_id,cursor.c_str(),33);}
    page copied;auto status=reader_av_page_get(snapshot.value,&from,32,&copied.value,&error);pending(env);if(status!=READER_AV_OK)reject("java/lang/IllegalStateException","Reading page cannot be read");c.poll();jclass row_type=env->FindClass("org/exreader/host/ReadingRecord");pending(env);jobjectArray rows=env->NewObjectArray(static_cast<jsize>(copied.value.count),row_type,nullptr);pending(env);for(size_t i=0;i<copied.value.count;i++){jobject row=record(env,key,copied.value.items[i]);env->SetObjectArrayElement(rows,static_cast<jsize>(i),row);env->DeleteLocalRef(row);pending(env);}
    jobject progress=selected(env,owner.revisions,key,"","",true,c);jobjectArray cursors=product_jni::strings(env,{copied.value.next.has_after?copied.value.next.after_id:"",copied.value.reverse.has_after?copied.value.reverse.after_id:""});jlong fields[]={copied.value.complete,copied.value.budget_stopped,static_cast<jlong>(copied.value.wire_bytes),static_cast<jlong>(copied.value.output_bytes),static_cast<jlong>(copied.value.polls)};jlongArray numeric=env->NewLongArray(5);pending(env);env->SetLongArrayRegion(numeric,0,5,fields);pending(env);jclass type=env->FindClass("org/exreader/host/NativeReadingProduct$Page");pending(env);jmethodID constructor=env->GetMethodID(type,"<init>","([Lorg/exreader/host/ReadingRecord;Lorg/exreader/host/ReadingRecord;[Ljava/lang/String;[J)V");pending(env);jobject result=env->NewObject(type,constructor,rows,progress,cursors,numeric);pending(env);c.poll();return result;
  });
}
extern "C" JNIEXPORT jobject JNICALL Java_org_exreader_host_NativeReadingProduct_nativeSelected(JNIEnv *env,jclass,jlong handle,jstring book,jstring id,jstring expected,jboolean progress,jobject task){
  return product_jni::call(env,handle,[&](product_jni::owner &owner)->jobject{reading_product::control c(env,task);return reading_product::selected(env,owner.revisions,reading_product::text(env,book),reading_product::text(env,id,true),reading_product::text(env,expected,true),progress,c);});
}
extern "C" JNIEXPORT jbyteArray JNICALL Java_org_exreader_host_NativeReadingProduct_nativeRetained(JNIEnv *env,jclass,jlong handle,jstring book,jstring id,jstring revision,jboolean progress,jobject task){
  return product_jni::call(env,handle,[&](product_jni::owner &owner)->jbyteArray{using namespace reading_product;control c(env,task);c.poll();std::string key=text(env,book),annotation=text(env,id,true),rid=text(env,revision);wire retained;reader_revision_error error{};if(reader_revision_get(owner.revisions,rid.c_str(),&retained.value,&retained.bytes,&retained.info,&error)!=READER_REV_OK)reject("java/lang/IllegalStateException","Retained reading version is unavailable");std::string entity=progress?key:key+":"+annotation;if(std::strcmp(retained.info.entity_kind,progress?"progress":"annotation")||retained.info.entity_key!=entity||retained.info.book_key!=key)reject("java/lang/IllegalStateException","Retained reading version belongs to another entity");c.poll();return bytes(env,retained.value,retained.bytes);});
}
extern "C" JNIEXPORT jobject JNICALL Java_org_exreader_host_NativeReadingProduct_nativeVersion(JNIEnv *env,jclass,jlong handle,jstring book,jstring id,jstring revision,jboolean progress,jobject task){
  return product_jni::call(env,handle,[&](product_jni::owner &owner)->jobject{
    using namespace reading_product;local_frame frame(env);control c(env,task);c.poll();std::string key=text(env,book),annotation=text(env,id,true),rid=text(env,revision),entity=progress?key:key+":"+annotation;wire retained;reader_revision_error error{};
    if(reader_revision_get(owner.revisions,rid.c_str(),&retained.value,&retained.bytes,&retained.info,&error)!=READER_REV_OK)reject("java/lang/IllegalStateException","Retained reading version is unavailable");
    if(std::strcmp(retained.info.entity_kind,progress?"progress":"annotation")||retained.info.entity_key!=entity||retained.info.book_key!=key)reject("java/lang/IllegalStateException","Retained reading version belongs to another entity");
    decoded data;reader_rs_error decode{};if(reader_rs_decode(owner.revisions,retained.value,retained.bytes,&data.value,&decode)!=READER_RS_OK)reject("java/lang/IllegalStateException","Retained reading selector cannot be decoded");const auto &r=data.value;if(key!=r.book_key||std::strcmp(r.entity_kind,progress?"progress":"annotation")||(!progress&&annotation!=r.annotation_id))reject("java/lang/IllegalStateException","Retained selector identity differs");
    reader_av_item fields{};capture_fields(fields,r);jobject captured=capture(env,key,fields);jstring body=product_jni::string(env,r.note_text?r.note_text:""),version=product_jni::string(env,retained.info.revision_id),sha=product_jni::string(env,retained.info.sha256),operation=product_jni::string(env,retained.info.operation);jbyteArray original=bytes(env,retained.value,retained.bytes);jclass type=env->FindClass("org/exreader/host/ReadingVersion");pending(env);jmethodID constructor=env->GetMethodID(type,"<init>","(Lorg/exreader/host/ReadingCapture;Ljava/lang/String;Ljava/lang/String;Ljava/lang/String;Ljava/lang/String;[B)V");pending(env);jobject result=env->NewObject(type,constructor,captured,body,version,sha,operation,original);pending(env);c.poll();return frame.keep(result);
  });
}
extern "C" JNIEXPORT jobjectArray JNICALL Java_org_exreader_host_NativeReadingProduct_nativeApply(JNIEnv *env,jclass,jlong handle,jstring request,jobjectArray expected,jint kind,jint operation,jstring book,jstring id,jint mode,jlongArray numeric,jobjectArray route,jobjectArray selectors,jbyteArray body){
  return product_jni::call(env,handle,[&](product_jni::owner &owner)->jobjectArray{
    using namespace reading_product;std::string rid=text(env,request),key=text(env,book),annotation=text(env,id,true);std::vector<std::string> heads;std::vector<const char *> pointers;jsize count=expected?env->GetArrayLength(expected):0;if(count>32)reject("java/lang/IllegalArgumentException","Observed reading heads exceed their limit");heads.reserve(static_cast<size_t>(count));for(jsize i=0;i<count;i++){jstring value=static_cast<jstring>(env->GetObjectArrayElement(expected,i));heads.push_back(text(env,value));env->DeleteLocalRef(value);}for(const auto &head:heads)pointers.push_back(head.c_str());
    std::string note=input_bytes(env,body,65536,true);if(note.find('\0')!=std::string::npos)reject("java/lang/IllegalArgumentException","Reading body contains NUL");
    reader_rc_context context{};context.store=owner.revisions;context.revision_id=rid.c_str();context.expected_heads=pointers.data();context.expected_count=pointers.size();reader_rc_command command{};command.kind=static_cast<reader_rc_kind>(kind);command.operation=static_cast<reader_rc_operation>(operation);command.book_key=key.c_str();command.annotation_id=annotation.c_str();command.text=kind==READER_RC_PROGRESS||operation==READER_RC_DELETE?nullptr:note.c_str();
    reader_rs_capture capture{};exr_anchor anchor{};exr_fixed_anchor fixed{};std::array<std::string,5> fields;std::array<bool,5> present{};std::array<std::string,3> copied;std::array<bool,3> has{};jlong values[4]={mode,0,0,0};
    if(operation==READER_RC_DELETE){capture.mode=static_cast<reader_rs_mode>(mode);command.capture=&capture;}
    else if(kind!=READER_RC_NOTE_TEXT){
      if(!numeric||!route||!selectors||env->GetArrayLength(numeric)!=4||env->GetArrayLength(route)!=5||env->GetArrayLength(selectors)!=3)reject("java/lang/IllegalArgumentException","A real copied reading capture is required");env->GetLongArrayRegion(numeric,0,4,values);pending(env);capture.mode=static_cast<reader_rs_mode>(values[0]);if(values[0]!=mode)reject("java/lang/IllegalArgumentException","Reading capture mode differs");
      for(size_t i=0;i<5;i++){jstring value=static_cast<jstring>(env->GetObjectArrayElement(route,static_cast<jsize>(i)));present[i]=value!=nullptr;if(value){fields[i]=text(env,value);env->DeleteLocalRef(value);}}if(!present[0]||!present[1]||fields[0]!=key)reject("java/lang/IllegalArgumentException","Reading capture original identity differs");context.parser_version=fields[1].c_str();
      for(size_t i=0;i<3;i++){jbyteArray value=static_cast<jbyteArray>(env->GetObjectArrayElement(selectors,static_cast<jsize>(i)));has[i]=value!=nullptr;copied[i]=input_bytes(env,value,i?128:65536,true);if(value)env->DeleteLocalRef(value);}
      command.part=static_cast<size_t>(values[1]);capture.page=static_cast<size_t>(values[1]);capture.part_path=present[2]?fields[2].c_str():nullptr;
      if(mode==READER_RS_FIXED_PAGE){fixed.start=static_cast<size_t>(values[2]);fixed.end=static_cast<size_t>(values[3]);fixed.page_id=present[3]?fields[3].c_str():nullptr;fixed.exact=has[0]?const_cast<char *>(copied[0].c_str()):nullptr;fixed.prefix=has[1]?const_cast<char *>(copied[1].c_str()):nullptr;fixed.suffix=has[2]?const_cast<char *>(copied[2].c_str()):nullptr;fixed.exact_size=copied[0].size();fixed.prefix_size=copied[1].size();fixed.suffix_size=copied[2].size();capture.fixed=&fixed;}
      else{for(const auto &value:copied)if(value.find('\0')!=std::string::npos)reject("java/lang/IllegalArgumentException","Reflow reading selector contains NUL");anchor.start=static_cast<size_t>(values[2]);anchor.end=static_cast<size_t>(values[3]);anchor.exact=has[0]?const_cast<char *>(copied[0].c_str()):nullptr;anchor.prefix=has[1]?const_cast<char *>(copied[1].c_str()):nullptr;anchor.suffix=has[2]?const_cast<char *>(copied[2].c_str()):nullptr;anchor.chapter=present[4]?const_cast<char *>(fields[4].c_str()):nullptr;capture.anchor=&anchor;}
      command.capture=&capture;
    }
    reader_rc_result result{};reader_rc_error error{};auto status=reader_rc_apply(&context,&command,&result,&error);return product_jni::strings(env,{std::to_string(status),std::to_string(error.encode.gap),std::to_string(error.revision.code),result.entity_key,result.annotation_id,result.revision_id,result.sha256,std::to_string(result.bytes),result.created?"1":"0"});
  });
}
#ifdef READER_READING_FIXTURES
extern "C" JNIEXPORT jobjectArray JNICALL Java_org_exreader_host_NativeReadingProbe_identity(JNIEnv *env,jclass){
  Dl_info commands{},view{},sqlite{};if(!dladdr(reinterpret_cast<void *>(&reader_rc_apply),&commands)||!dladdr(reinterpret_cast<void *>(&reader_av_page_get),&view)||!dladdr(reinterpret_cast<void *>(&sqlite3_open_v2),&sqlite))return nullptr;
  return product_jni::strings(env,{commands.dli_fname,view.dli_fname,sqlite.dli_fname});
}
extern "C" JNIEXPORT jint JNICALL Java_org_exreader_host_NativeReadingProbe_receive(JNIEnv *env,jclass,jlong handle,jbyteArray bytes){
  return product_jni::call(env,handle,[&](product_jni::owner &owner)->jint{std::string wire=reading_product::input_bytes(env,bytes,READER_REVISION_MAX_BYTES,false);reader_revision_info info{};reader_revision_error error{};int created=0;auto status=reader_revision_receive(owner.revisions,wire.data(),wire.size(),nullptr,&info,&created,&error);if(status!=READER_REV_OK)product_jni::reject("java/lang/IllegalStateException","Public revision fixture receive refused");return created;});
}
#endif
