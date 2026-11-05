/* SPDX-License-Identifier: MIT */
/* Test-only suffix appended to a byte-verified Debug review include in Actions. */
extern "C" JNIEXPORT jbyteArray JNICALL Java_org_exreader_host_ConflictBoundaryTest_readWire(JNIEnv *env,jclass,jlong handle,jstring revision){
  return product_jni::call(env,handle,[&](product_jni::owner &owner)->jbyteArray{
    auto id=product_jni::utf8(env,revision);char *wire=nullptr;size_t size=0;reader_revision_info info{};reader_revision_error error{};
    auto status=reader_revision_get(owner.revisions,id.c_str(),&wire,&size,&info,&error);
    struct release {char *p;~release(){reader_revision_bytes_free(p);}} cleanup{wire};
    product_jni::database(status,error.message);
    if(size>READER_REVISION_MAX_BYTES)product_jni::reject("java/lang/IllegalStateException","Wire exceeds documented bound");
    jbyteArray result=env->NewByteArray(static_cast<jsize>(size));product_jni::pending(env);
    env->SetByteArrayRegion(result,0,static_cast<jsize>(size),reinterpret_cast<const jbyte *>(wire));product_jni::pending(env);return result;
  });
}
extern "C" JNIEXPORT jobjectArray JNICALL Java_org_exreader_host_ConflictBoundaryTest_ingest(JNIEnv *env,jclass,jlong handle,jbyteArray value,jstring expected,jboolean remote){
  return product_jni::call(env,handle,[&](product_jni::owner &owner)->jobjectArray{
    if(!value)product_jni::reject("java/lang/IllegalArgumentException","Missing revision bytes");
    jsize size=env->GetArrayLength(value);product_jni::pending(env);
    if(size<2||static_cast<size_t>(size)>READER_REVISION_MAX_BYTES)product_jni::reject("java/lang/IllegalArgumentException","Wire size outside revision contract");
    std::vector<char> wire(static_cast<size_t>(size));env->GetByteArrayRegion(value,0,size,reinterpret_cast<jbyte *>(wire.data()));product_jni::pending(env);
    reader_revision_info info{};reader_revision_error error{};int created=0;reader_revision_status status;
    if(remote){auto hash=product_jni::utf8(env,expected);status=reader_revision_receive(owner.revisions,wire.data(),wire.size(),hash.c_str(),&info,&created,&error);}
    else status=reader_revision_local(owner.revisions,wire.data(),wire.size(),&info,&created,&error);
    return product_jni::strings(env,{std::to_string(status),std::to_string(created),info.revision_id,info.sha256,error.message});
  });
}
extern "C" JNIEXPORT jobjectArray JNICALL Java_org_exreader_host_ConflictBoundaryTest_probeIdentity(JNIEnv *env,jclass,jlong handle){
  return product_jni::call(env,handle,[&](product_jni::owner &)->jobjectArray{
    Dl_info a{},b{};if(!dladdr(reinterpret_cast<void *>(&reader_revision_receive),&a)||!dladdr(reinterpret_cast<void *>(&reader_revision_heads),&b)||!a.dli_fname||!b.dli_fname)
      product_jni::reject("java/lang/IllegalStateException","Revision provider identity unavailable");
    return product_jni::strings(env,{a.dli_fname,b.dli_fname,std::to_string(READER_REVISION_MAX_ENTITY_HISTORY),READER_REVISIONS_VERSION});
  });
}
