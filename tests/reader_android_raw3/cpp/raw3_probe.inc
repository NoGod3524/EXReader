/* SPDX-License-Identifier: MIT */
#include <reader_session.h>
extern "C" JNIEXPORT jobjectArray JNICALL Java_org_exreader_host_Raw3Probe_family(JNIEnv *env,jclass,jlong handle){
  return product_jni::call(env,handle,[&](product_jni::owner &)->jobjectArray{
    const char *versions[]={READER_REVISIONS_VERSION,READER_READING_STATE_VERSION,
      READER_READING_COMMANDS_VERSION,READER_ANNOTATION_VIEW_VERSION,READER_COMMANDS_VERSION,
      READER_SYNC_VERSION,READER_SESSION_VERSION};
    const void *functions[]={reinterpret_cast<const void *>(&reader_revision_get_raw_v3),
      reinterpret_cast<const void *>(&reader_rs_decode_raw_v3),reinterpret_cast<const void *>(&reader_rc_apply_raw_v3),
      reinterpret_cast<const void *>(&reader_av_page_get_raw_v3),reinterpret_cast<const void *>(&reader_command_apply_book_raw_v3),
      reinterpret_cast<const void *>(&reader_sync_step_raw_v3),reinterpret_cast<const void *>(&reader_session_create_raw_v3)};
    std::vector<std::string> result;
    for(size_t i=0;i<7;i++){Dl_info actual{};if(!dladdr(functions[i],&actual)||!actual.dli_fname)
      product_jni::reject("java/lang/IllegalStateException","Actual raw module provider missing");
      result.emplace_back(versions[i]);result.emplace_back(actual.dli_fname);}
    result.push_back(std::to_string(READER_REVISION_ANCHOR_MAX_VERSION));
    result.push_back("explicit-raw-store");
    return product_jni::strings(env,result);
  });
}
