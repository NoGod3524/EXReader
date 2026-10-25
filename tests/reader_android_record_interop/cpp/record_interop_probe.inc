/* SPDX-License-Identifier: MIT */
/* Included only into the existing Debug owner TU. Reads public retained APIs. */
#include <functional>
namespace record_review {
struct copied { std::vector<std::string> values;bool failed=false; };
static int copy(void *context,const reader_revision_outbox_row *row){
  auto &out=*static_cast<copied *>(context);
  try{out.values.emplace_back(row->wire,row->info.bytes);return 0;}catch(...){out.failed=true;return 1;}
}
}
extern "C" JNIEXPORT jobjectArray JNICALL Java_org_exreader_host_RecordWireProbe_outbox(JNIEnv *env,jclass,jlong handle){
  return product_jni::call(env,handle,[&](product_jni::owner &owner)->jobjectArray{
    record_review::copied out;reader_revision_error error{};
    if(reader_revision_outbox(owner.revisions,100,record_review::copy,&out,&error)!=READER_REV_OK||out.failed)product_jni::reject("java/lang/IllegalStateException","Cannot read exact existing outbox bytes");
    jclass bytes=env->FindClass("[B");product_jni::pending(env);jobjectArray result=env->NewObjectArray(static_cast<jsize>(out.values.size()),bytes,nullptr);env->DeleteLocalRef(bytes);product_jni::pending(env);
    for(size_t i=0;i<out.values.size();i++){jbyteArray value=reading_product::bytes(env,out.values[i].data(),out.values[i].size());env->SetObjectArrayElement(result,static_cast<jsize>(i),value);env->DeleteLocalRef(value);product_jni::pending(env);}return result;
  });
}
extern "C" JNIEXPORT jbyteArray JNICALL Java_org_exreader_host_RecordWireProbe_retained(JNIEnv *env,jclass,jlong handle,jstring revision){
  return product_jni::call(env,handle,[&](product_jni::owner &owner)->jbyteArray{
    auto id=product_jni::utf8(env,revision);reading_product::wire value;reader_revision_error error{};
    if(reader_revision_get(owner.revisions,id.c_str(),&value.value,&value.bytes,&value.info,&error)!=READER_REV_OK)product_jni::reject("java/lang/IllegalStateException","Exact committed revision is unavailable");
    return reading_product::bytes(env,value.value,value.bytes);
  });
}
extern "C" JNIEXPORT jobjectArray JNICALL Java_org_exreader_host_RecordWireProbe_ownerIdentity(JNIEnv *env,jclass,jlong handle){
  return product_jni::call(env,handle,[&](product_jni::owner &owner)->jobjectArray{
    Dl_info get{},write{};if(!dladdr(reinterpret_cast<void *>(&reader_revision_get),&get)||!dladdr(reinterpret_cast<void *>(&reader_rc_apply),&write))product_jni::reject("java/lang/IllegalStateException","Actual revision provider identity is unavailable");
    return product_jni::strings(env,{std::to_string(handle),std::to_string(std::hash<std::thread::id>{}(owner.thread)),get.dli_fname,write.dli_fname});
  });
}
