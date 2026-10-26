/* SPDX-License-Identifier: MIT */
/* Included in the existing product owner translation unit after reading_product_jni.inc.
   It adapts the reviewed raw0.2 annotation import/export and jump-history packages to
   the creating worker's revision store. No SQL, no SDK call, no second thread. */
#include <reader_annotation_import_raw3.h>
#include <reader_annotation_export_raw3.h>
#include <reader_jump_history.h>
#include <memory>

/* Internal reading-state entry that validates through the raw store (as reading-commands does). */
reader_rs_status reader_rs_encode_retained_raw_v3(reader_revisions *,const reader_rs_envelope *,const reader_rs_capture *,unsigned,size_t,char **,size_t *,reader_rs_error *);

namespace wave3 {
using product_jni::pending;
using product_jni::reject;

/* ---- raw0.2 portable annotations ------------------------------------------- */
struct import_run {
  reading_product::control *control;jobject sink;jmethodID found;size_t total=0;
  std::vector<std::vector<std::string>> items;
};
int import_cancel(void *opaque){return reading_product::control::cancelled(static_cast<import_run *>(opaque)->control);}
int import_item(void *opaque,const reader_ai3_item *item){
  auto &run=*static_cast<import_run *>(opaque);
  try{
    run.total++;
    if(run.items.size()<200)run.items.push_back({std::to_string(item->index),std::to_string(static_cast<int>(item->outcome)),std::to_string(static_cast<int>(item->found)),
      std::to_string(item->committed),std::to_string(item->created),std::to_string(item->exact_duplicate),std::to_string(item->revision_code),item->info.entity_kind,item->info.operation});
    return 0;
  }catch(...){return 1;}
}
/* Only a genuine public SDK FOUND returns 1: the Java sink resolves the copied capture on the SDK owner. */
int import_resolve(void *opaque,const reader_rs_record *record,uint64_t){
  auto &run=*static_cast<import_run *>(opaque);JNIEnv *env=run.control->env;
  try{
    reader_av_item view{};reading_product::capture_fields(view,*record);
    jobject capture=reading_product::capture(env,record->book_key,view);
    if(!capture)return 0;
    jboolean found=env->CallBooleanMethod(run.sink,run.found,capture);
    env->DeleteLocalRef(capture);
    if(env->ExceptionCheck())return 0;
    return found?1:0;
  }catch(...){return 0;}
}
jobjectArray import_result(JNIEnv *env,const reader_ai3_stats &stats,const reader_ai3_error &error,reader_ai3_status status,const import_run &run){
  std::vector<std::vector<std::string>> rows;
  rows.push_back({std::to_string(static_cast<int>(status)),std::to_string(error.revision_code),std::to_string(error.rs_code),std::to_string(error.os_error),std::to_string(error.line),
    std::to_string(error.item_index),error.message,std::to_string(stats.input_bytes),std::to_string(stats.annotations),std::to_string(stats.head_wires),std::to_string(stats.omitted_history),
    std::to_string(stats.found),std::to_string(stats.unresolved),std::to_string(stats.null_preserved),std::to_string(stats.would_create),std::to_string(stats.would_duplicate),
    std::to_string(stats.created),std::to_string(stats.duplicates),std::to_string(stats.committed),std::to_string(stats.next_index),std::to_string(stats.source_bytes),
    stats.validated?std::string(stats.fingerprint):std::string(),std::to_string(stats.validated),std::to_string(stats.found_checked),std::to_string(stats.complete_product_accepted),std::to_string(run.total)});
  for(const auto &row:run.items)rows.push_back(row);
  jclass type=env->FindClass("[Ljava/lang/String;");pending(env);
  jobjectArray out=env->NewObjectArray(static_cast<jsize>(rows.size()),type,nullptr);env->DeleteLocalRef(type);pending(env);
  for(size_t i=0;i<rows.size();i++){jobjectArray row=product_jni::strings(env,rows[i]);env->SetObjectArrayElement(out,static_cast<jsize>(i),row);env->DeleteLocalRef(row);pending(env);}
  return out;
}

/* ---- jump history ------------------------------------------------------------- */
struct jump_owner {
  reader_jh *history=nullptr;std::map<jlong,reader_jh_item> peeks;jlong sequence=0;
  ~jump_owner(){for(auto &entry:peeks)reader_jh_item_release(&entry.second);if(history)reader_jh_close(&history,nullptr);}
};
std::map<jlong,std::unique_ptr<jump_owner>> jumps;
jump_owner &jump_for(jlong handle){
  auto &slot=jumps[handle];
  if(!slot){auto value=std::make_unique<jump_owner>();reader_jh_error error{};if(reader_jh_open(nullptr,&value->history,&error)!=READER_JH_OK)reject("java/lang/IllegalStateException","Jump history cannot be opened");slot=std::move(value);}
  return *slot;
}
void release(jlong handle){jumps.erase(handle);}

struct built_capture {
  reader_rs_capture capture{};exr_anchor anchor{};exr_fixed_anchor fixed{};
  std::array<std::string,5> fields;std::array<bool,5> present{};std::array<std::string,3> copied;std::array<bool,3> has{};jlong values[4]={0,0,0,0};
};
void build_capture(JNIEnv *env,built_capture &b,jint mode,jlongArray numeric,jobjectArray route,jobjectArray selectors){
  if(!numeric||!route||!selectors||env->GetArrayLength(numeric)!=4||env->GetArrayLength(route)!=5||env->GetArrayLength(selectors)!=3)reject("java/lang/IllegalArgumentException","A real copied reading capture is required");
  env->GetLongArrayRegion(numeric,0,4,b.values);pending(env);
  if(b.values[0]!=mode)reject("java/lang/IllegalArgumentException","Reading capture mode differs");
  b.capture.mode=static_cast<reader_rs_mode>(mode);
  for(size_t i=0;i<5;i++){jstring value=static_cast<jstring>(env->GetObjectArrayElement(route,static_cast<jsize>(i)));b.present[i]=value!=nullptr;if(value){b.fields[i]=product_jni::utf8(env,value);env->DeleteLocalRef(value);}}
  if(!b.present[0]||!b.present[1])reject("java/lang/IllegalArgumentException","Reading capture identity is incomplete");
  for(size_t i=0;i<3;i++){jbyteArray value=static_cast<jbyteArray>(env->GetObjectArrayElement(selectors,static_cast<jsize>(i)));b.has[i]=value!=nullptr;b.copied[i]=reading_product::input_bytes(env,value,i?128:65536,true);if(value)env->DeleteLocalRef(value);}
  b.capture.page=static_cast<size_t>(b.values[1]);b.capture.part_path=b.present[2]?b.fields[2].c_str():nullptr;
  if(mode==READER_RS_FIXED_PAGE){
    b.fixed.start=static_cast<size_t>(b.values[2]);b.fixed.end=static_cast<size_t>(b.values[3]);b.fixed.page_id=b.present[3]?const_cast<char *>(b.fields[3].c_str()):nullptr;
    b.fixed.exact=b.has[0]?const_cast<char *>(b.copied[0].c_str()):nullptr;b.fixed.prefix=b.has[1]?const_cast<char *>(b.copied[1].c_str()):nullptr;b.fixed.suffix=b.has[2]?const_cast<char *>(b.copied[2].c_str()):nullptr;
    b.fixed.exact_size=b.copied[0].size();b.fixed.prefix_size=b.copied[1].size();b.fixed.suffix_size=b.copied[2].size();b.capture.fixed=&b.fixed;
  }else{
    for(const auto &value:b.copied)if(value.find('\0')!=std::string::npos)reject("java/lang/IllegalArgumentException","Reflow reading selector contains NUL");
    b.anchor.start=static_cast<size_t>(b.values[2]);b.anchor.end=static_cast<size_t>(b.values[3]);
    b.anchor.exact=b.has[0]?const_cast<char *>(b.copied[0].c_str()):nullptr;b.anchor.prefix=b.has[1]?const_cast<char *>(b.copied[1].c_str()):nullptr;b.anchor.suffix=b.has[2]?const_cast<char *>(b.copied[2].c_str()):nullptr;
    b.anchor.chapter=b.present[4]?const_cast<char *>(b.fields[4].c_str()):nullptr;b.capture.anchor=&b.anchor;
  }
}
}

/* Mirrors NativeCatalog.close: histories belong to the creating worker. */
extern "C" JNIEXPORT jobjectArray JNICALL Java_org_exreader_host_NativeWave3_annotationImport(JNIEnv *env,jclass,jlong handle,jstring book,jstring path,jboolean commit,jstring fingerprint,jobject task,jobject sink){
  return product_jni::call(env,handle,[&](product_jni::owner &owner)->jobjectArray{
    reading_product::control control(env,task);control.poll();
    std::string key=product_jni::utf8(env,book),file=product_jni::utf8(env,path),confirm=product_jni::utf8(env,fingerprint,true);
    wave3::import_run run{};run.control=&control;run.sink=sink;
    if(!sink)reject("java/lang/IllegalArgumentException","A public FOUND resolver is required");
    jclass sink_type=env->GetObjectClass(sink);pending(env);run.found=env->GetMethodID(sink_type,"found","(Lorg/exreader/host/ReadingCapture;)Z");env->DeleteLocalRef(sink_type);pending(env);
    reader_ai3_options options{};options.struct_size=sizeof(options);options.revisions=owner.revisions;options.jsonl_path=file.c_str();options.target_book_key=key.c_str();
    options.mode=commit?READER_AI3_COMMIT:READER_AI3_PREVIEW;options.max_input_bytes=0;
    if(commit){if(confirm.size()!=64)reject("java/lang/IllegalArgumentException","Commit requires the preview fingerprint");std::memcpy(options.confirm_fingerprint,confirm.c_str(),65);}
    options.resume_index=0;options.policy=READER_AI3_RESOLVE_REQUIRED;options.resolve=wave3::import_resolve;options.cancel=wave3::import_cancel;options.item=wave3::import_item;options.context=&run;
    reader_ai3_stats stats{};reader_ai3_error error{};
    reader_ai3_status status=reader_annotation_import_raw3_run(&options,&stats,&error);
    pending(env);
    return wave3::import_result(env,stats,error,status,run);
  });
}
extern "C" JNIEXPORT jobjectArray JNICALL Java_org_exreader_host_NativeWave3_annotationExport(JNIEnv *env,jclass,jlong handle,jstring book,jstring title,jstring jsonl,jstring markdown,jobject task){
  return product_jni::call(env,handle,[&](product_jni::owner &owner)->jobjectArray{
    reading_product::control control(env,task);control.poll();
    std::string key=product_jni::utf8(env,book),name=product_jni::utf8(env,title,true),json=product_jni::utf8(env,jsonl,true),md=product_jni::utf8(env,markdown,true);
    reader_annotation_export_options options{};options.struct_size=sizeof(options);options.revisions=owner.revisions;options.book_key=key.c_str();options.book_title=title?name.c_str():nullptr;
    options.jsonl_path=jsonl?json.c_str():nullptr;options.markdown_path=markdown?md.c_str():nullptr;options.max_output_bytes=0;options.cancel=reading_product::control::cancelled;options.cancel_context=&control;
    reader_annotation_export_stats stats{};reader_annotation_export_error error{};
    reader_annotation_export_status status=reader_annotation_export_raw3_run(&options,&stats,&error);
    pending(env);
    return product_jni::strings(env,{std::to_string(static_cast<int>(status)),std::to_string(error.revision_code),std::to_string(error.rs_code),std::to_string(error.os_error),error.message,
      std::to_string(stats.annotations),std::to_string(stats.current),std::to_string(stats.tombstones),std::to_string(stats.pending_parents),std::to_string(stats.concurrent),std::to_string(stats.blocked_restore),
      std::to_string(stats.head_wires),std::to_string(stats.jsonl_bytes),std::to_string(stats.markdown_bytes),std::to_string(stats.jsonl_published),std::to_string(stats.markdown_published)});
  });
}

/* [status, outcome, count, cursor, can_back, can_forward, generation, rs_code, gap, message] */
extern "C" JNIEXPORT jobjectArray JNICALL Java_org_exreader_host_NativeWave3_jumpCommit(JNIEnv *env,jclass,jlong handle,jint kind,jint mode,jlongArray numeric,jobjectArray route,jobjectArray selectors,jint version){
  return product_jni::call(env,handle,[&](product_jni::owner &owner)->jobjectArray{
    wave3::built_capture built;wave3::build_capture(env,built,mode,numeric,route,selectors);
    wave3::jump_owner &jump=wave3::jump_for(handle);
    char id[33];reader_revision_error revision{};if(reader_revision_new_id(id,&revision)!=READER_REV_OK)reject("java/lang/IllegalStateException","Cannot allocate a transient position ID");
    reader_rs_envelope envelope{};envelope.revision_id=id;envelope.operation="put";envelope.entity_kind="progress";envelope.book_key=built.fields[0].c_str();envelope.parser_version=built.fields[1].c_str();
    char *wire=nullptr;size_t bytes=0;reader_rs_error encode{};
    reader_rs_status encoded=reader_rs_encode_retained_raw_v3(owner.revisions,&envelope,&built.capture,static_cast<unsigned>(version),static_cast<size_t>(built.values[1]),&wire,&bytes,&encode);
    if(encoded!=READER_RS_OK){
      return product_jni::strings(env,{"100","0","0","0","0","0","0",std::to_string(static_cast<int>(encoded)),std::to_string(static_cast<int>(encode.gap)),encode.message});
    }
    reader_jh_result result{};reader_jh_error error{};
    reader_jh_status status=reader_jh_commit_wire_raw_v3(jump.history,owner.revisions,static_cast<reader_jh_kind>(kind),wire,bytes,&result,&error);
    reader_rs_free(wire);
    reader_jh_state state{};state.struct_version=READER_JH_STRUCT_VERSION;reader_jh_error ignored{};reader_jh_state_get(jump.history,&state,&ignored);
    return product_jni::strings(env,{std::to_string(static_cast<int>(status)),std::to_string(static_cast<int>(result.outcome)),std::to_string(state.count),std::to_string(state.cursor),std::to_string(state.can_back),
      std::to_string(state.can_forward),std::to_string(state.generation),std::to_string(static_cast<int>(error.rs_code)),std::to_string(static_cast<int>(error.gap)),error.message});
  });
}
/* out = [status, token, index, count]; returns the decoded capture or null when EMPTY/refused. */
extern "C" JNIEXPORT jobject JNICALL Java_org_exreader_host_NativeWave3_jumpPeek(JNIEnv *env,jclass,jlong handle,jint direction,jlongArray out){
  return product_jni::call(env,handle,[&](product_jni::owner &owner)->jobject{
    wave3::jump_owner &jump=wave3::jump_for(handle);reader_jh_item item{};reader_jh_error error{};
    reader_jh_status status=reader_jh_peek(jump.history,static_cast<reader_jh_direction>(direction),&item,&error);
    jlong meta[4]={static_cast<jlong>(status),0,0,0};jobject capture=nullptr;
    if(status==READER_JH_OK){
      reader_rs_record record{};reader_rs_error decode{};
      if(reader_rs_decode(owner.revisions,item.wire,item.wire_bytes,&record,&decode)!=READER_RS_OK){reader_jh_item_release(&item);reject("java/lang/IllegalStateException","Jump history entry cannot be decoded");}
      std::string book=item.book_key;
      try{
        reader_av_item view{};reading_product::capture_fields(view,record);capture=reading_product::capture(env,book,view);
      }catch(...){reader_rs_record_free(&record);reader_jh_item_release(&item);throw;}
      reader_rs_record_free(&record);
      if(!capture){reader_jh_item_release(&item);meta[0]=100;}
      else{jlong token=++jump.sequence;meta[1]=token;meta[2]=static_cast<jlong>(item.index);jump.peeks.emplace(token,item);}
    }
    reader_jh_state state{};state.struct_version=READER_JH_STRUCT_VERSION;reader_jh_error ignored{};reader_jh_state_get(jump.history,&state,&ignored);meta[3]=static_cast<jlong>(state.count);
    env->SetLongArrayRegion(out,0,4,meta);pending(env);
    return capture;
  });
}
/* Moves the cursor only after the host's own FOUND navigation; returns the module status. */
extern "C" JNIEXPORT jint JNICALL Java_org_exreader_host_NativeWave3_jumpComplete(JNIEnv *env,jclass,jlong handle,jlong token){
  return product_jni::call(env,handle,[&](product_jni::owner &)->jint{
    wave3::jump_owner &jump=wave3::jump_for(handle);auto found=jump.peeks.find(token);if(found==jump.peeks.end())reject("java/lang/IllegalStateException","Unknown jump target");
    reader_jh_error error{};reader_jh_status status=reader_jh_complete(jump.history,&found->second,&error);reader_jh_item_release(&found->second);jump.peeks.erase(found);return static_cast<jint>(status);
  });
}
/* Not completing is the cancellation: the peeked copy is released and the cursor stays. */
extern "C" JNIEXPORT void JNICALL Java_org_exreader_host_NativeWave3_jumpDrop(JNIEnv *env,jclass,jlong handle,jlong token){
  product_jni::call(env,handle,[&](product_jni::owner &)->int{
    wave3::jump_owner &jump=wave3::jump_for(handle);auto found=jump.peeks.find(token);if(found!=jump.peeks.end()){reader_jh_item_release(&found->second);jump.peeks.erase(found);}return 0;
  });
}
/* [count, cursor, can_back, can_forward, generation, bytes, outstanding_peeks] */
extern "C" JNIEXPORT jlongArray JNICALL Java_org_exreader_host_NativeWave3_jumpState(JNIEnv *env,jclass,jlong handle,jboolean clear){
  return product_jni::call(env,handle,[&](product_jni::owner &)->jlongArray{
    wave3::jump_owner &jump=wave3::jump_for(handle);reader_jh_error error{};
    if(clear){for(auto &entry:jump.peeks)reader_jh_item_release(&entry.second);jump.peeks.clear();if(reader_jh_clear(jump.history,&error)!=READER_JH_OK)reject("java/lang/IllegalStateException","Jump history cannot be cleared");}
    reader_jh_state state{};state.struct_version=READER_JH_STRUCT_VERSION;if(reader_jh_state_get(jump.history,&state,&error)!=READER_JH_OK)reject("java/lang/IllegalStateException","Jump history state is unavailable");
    jlong values[7]={static_cast<jlong>(state.count),static_cast<jlong>(state.cursor),state.can_back,state.can_forward,static_cast<jlong>(state.generation),static_cast<jlong>(state.bytes),static_cast<jlong>(jump.peeks.size())};
    jlongArray out=env->NewLongArray(7);pending(env);env->SetLongArrayRegion(out,0,7,values);pending(env);return out;
  });
}
