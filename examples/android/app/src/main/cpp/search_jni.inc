/* SPDX-License-Identifier: MIT */
/* App-local adapter over installed Search and the existing shared SDK. */
#include <reader_search.h>
#include <pthread.h>
#include <stdatomic.h>
#include <math.h>

typedef struct {
  pthread_t owner;reader_search *search;
  exr_document *document;exr_publication *publication;exr_font *font;exr_fixed_document *fixed;
  host_control context;jobject control;char *key;int counted;
} host_search;
#ifdef READER_SEARCH_FIXTURES
static atomic_int host_search_live=0;
#endif
static void search_failure(JNIEnv *env,int code,int sdk) {
  jclass type;jmethodID constructor;jthrowable error;
  if((*env)->ExceptionCheck(env))return;
  type=(*env)->FindClass(env,"org/exreader/host/NativeSearch$Failure");if(!type)return;
  constructor=(*env)->GetMethodID(env,type,"<init>","(II)V");
  error=constructor?(jthrowable)(*env)->NewObject(env,type,constructor,(jint)code,(jint)sdk):NULL;
  if(error){(*env)->Throw(env,error);(*env)->DeleteLocalRef(env,error);}(*env)->DeleteLocalRef(env,type);
}
static host_search *search_owner(JNIEnv *env,jlong handle) {
  host_search *search=(host_search *)(intptr_t)handle;
  if(!search||!pthread_equal(search->owner,pthread_self())){throw_argument(env,"Search requires its creating SDK worker");return NULL;}
  return search;
}
static void search_free(JNIEnv *env,host_search *search) {
  if(!search)return;
  if(search->search)reader_search_close(&search->search,NULL);
  exr_document_free(search->document);exr_fixed_free(search->fixed);exr_publication_free(search->publication);exr_font_free(search->font);
  if(search->control)(*env)->DeleteGlobalRef(env,search->control);free(search->key);
#ifdef READER_SEARCH_FIXTURES
  if(search->counted)atomic_fetch_sub(&host_search_live,1);
#endif
  free(search);
}
static exr_status search_font(JNIEnv *env,jbyteArray input,exr_font **font,exr_error *error) {
  return host_font_bytes(env,input,font,error);
}
static exr_control search_control(JNIEnv *env,host_search *search,jobject value) {
  jobject next=value?(*env)->NewGlobalRef(env,value):NULL;exr_control empty={0};
  if(!next){if(!(*env)->ExceptionCheck(env))throw_argument(env,"Search control is required");return empty;}
  if(search->control)(*env)->DeleteGlobalRef(env,search->control);search->control=next;
  return host_task_control(env,next,&search->context);
}
JNIEXPORT jstring JNICALL Java_org_exreader_host_NativeSearch_nativeVersion(JNIEnv *env,jclass type) {
  (void)type;return output_string(env,exr_version());
}
JNIEXPORT jlong JNICALL Java_org_exreader_host_NativeSearch_nativeOpen(JNIEnv *env,jclass type,jlong owner,jlong book,jint mode,jstring key,jstring query,jbyteArray font,jfloat size,jobject control) {
  host_search *search=NULL;exr_library *store=library(env,owner);char *text=NULL;exr_error sdk_error={0};reader_search_error error={0};
  exr_status sdk=EXR_OK;reader_search_status status=READER_SEARCH_OK;reader_search_options options={0};exr_control cancellation;
  exr_layout_config layout=exr_layout_config_defaults();exr_chapter_options chapter=exr_chapter_options_defaults();(void)type;
  if(!store||(*env)->ExceptionCheck(env))return 0;
  if(book<=0||!isfinite(size)||size<4||size>256||!query||!key||(*env)->GetStringLength(env,query)>4096||(*env)->GetStringLength(env,key)>255){throw_argument(env,"Invalid search source or query");return 0;}
  text=input_string(env,query);if(!text)return 0;
  if(!text[0]||strlen(text)>READER_SEARCH_QUERY_MAX){free(text);search_failure(env,READER_SEARCH_QUERY,0);return 0;}
  search=calloc(1,sizeof(*search));if(!search){free(text);search_failure(env,READER_SEARCH_MEMORY,0);return 0;}
  search->owner=pthread_self();search->key=input_string(env,key);
  if(!search->key||!search->key[0]||strlen(search->key)>READER_SEARCH_SOURCE_KEY_MAX){if(!(*env)->ExceptionCheck(env))throw_argument(env,"Invalid verified search identity");goto failed;}
  cancellation=search_control(env,search,control);if((*env)->ExceptionCheck(env))goto failed;
  options.struct_size=sizeof(options);options.control=cancellation;options.source_key=search->key;
  if(mode==READER_SEARCH_REFLOW){
    sdk=exr_library_document(store,(int64_t)book,&search->document,&sdk_error);
    if(sdk==EXR_OK)status=reader_search_open_reflow(search->document,text,strlen(text),&options,&search->search,&error);
  }else if(mode==READER_SEARCH_EPUB){
    sdk=host_publication(store,(int64_t)book,&search->publication,&sdk_error);
    if(sdk==EXR_OK)sdk=search_font(env,font,&search->font,&sdk_error);
    layout.page.width=600;layout.page.height=860;layout.page.margin=32;layout.page.font_size=size;layout.page.line_height=1.6f;layout.page.paragraph_spacing=12;
    layout.document_css=1;layout.embedded_fonts=1;chapter.workspace_budget=8*1024*1024;chapter.window_bytes=64*1024;
    if(sdk==EXR_OK)status=reader_search_open_epub(search->publication,search->font,&layout,&chapter,text,strlen(text),&options,&search->search,&error);
  }else if(mode==READER_SEARCH_FIXED){
    exr_fixed_open_options fixed={0};fixed.struct_size=sizeof(fixed);fixed.control=cancellation;
    sdk=search_font(env,font,&search->font,&sdk_error);fixed.fallback_font=search->font;
    if(sdk==EXR_OK)sdk=exr_library_fixed_source(store,(int64_t)book,&fixed,&search->fixed,&sdk_error);
    if(sdk==EXR_OK)status=reader_search_open_fixed(search->fixed,text,strlen(text),&options,&search->search,&error);
  }else sdk=EXR_ARGUMENT;
  if(sdk!=EXR_OK)search_failure(env,READER_SEARCH_SDK,sdk);
  else if(status!=READER_SEARCH_OK)search_failure(env,status,error.sdk_code);
  if((*env)->ExceptionCheck(env)||sdk!=EXR_OK||status!=READER_SEARCH_OK)goto failed;
  free(text);
#ifdef READER_SEARCH_FIXTURES
  search->counted=1;atomic_fetch_add(&host_search_live,1);
#endif
  return (jlong)(intptr_t)search;
failed:
  free(text);search_free(env,search);return 0;
}
static jbyteArray search_bytes(JNIEnv *env,const char *value,size_t length) {
  jbyteArray result;if(length>65536||(!value&&length)){throw_argument(env,"Search selector exceeds its byte bound");return NULL;}
  result=(*env)->NewByteArray(env,(jsize)length);if(result&&length)(*env)->SetByteArrayRegion(env,result,0,(jsize)length,(const jbyte *)value);return result;
}
static jobject search_hit(JNIEnv *env,host_search *search,const reader_search_hit *hit) {
  jclass type=NULL,bytes_type=NULL;jmethodID constructor;jobjectArray route=NULL,selectors=NULL;jobject result=NULL;jbyteArray bytes=NULL;
  const char *values[3];size_t lengths[3],i;
  if(hit->unit>INT64_MAX||hit->start>INT64_MAX||hit->end>INT64_MAX){throw_argument(env,"Search route is out of JNI range");return NULL;}
  route=new_row(env,4);if(!route||!set_cell(env,route,0,search->key))goto done;
  if(hit->part_path&&!set_cell(env,route,1,hit->part_path))goto done;
  if(hit->page_id&&!set_cell(env,route,2,hit->page_id))goto done;
  if(hit->anchor.chapter&&!set_cell(env,route,3,hit->anchor.chapter))goto done;
  if(hit->mode==READER_SEARCH_FIXED){values[0]=hit->fixed.exact;values[1]=hit->fixed.prefix;values[2]=hit->fixed.suffix;lengths[0]=hit->fixed.exact_size;lengths[1]=hit->fixed.prefix_size;lengths[2]=hit->fixed.suffix_size;}
  else{values[0]=hit->anchor.exact;values[1]=hit->anchor.prefix;values[2]=hit->anchor.suffix;for(i=0;i<3;i++)lengths[i]=values[i]?strlen(values[i]):0;}
  bytes_type=(*env)->FindClass(env,"[B");if(!bytes_type)goto done;
  selectors=(*env)->NewObjectArray(env,3,bytes_type,NULL);if(!selectors)goto done;
  for(i=0;i<3;i++){bytes=search_bytes(env,values[i],lengths[i]);if(!bytes)goto done;(*env)->SetObjectArrayElement(env,selectors,(jsize)i,bytes);(*env)->DeleteLocalRef(env,bytes);bytes=NULL;if((*env)->ExceptionCheck(env))goto done;}
  type=(*env)->FindClass(env,"org/exreader/host/NativeSearch$Hit");if(!type)goto done;
  constructor=(*env)->GetMethodID(env,type,"<init>","(IJJJ[Ljava/lang/String;[[B)V");if(!constructor)goto done;
  result=(*env)->NewObject(env,type,constructor,(jint)hit->mode,(jlong)hit->unit,(jlong)hit->start,(jlong)hit->end,route,selectors);
done:
  if(bytes)(*env)->DeleteLocalRef(env,bytes);if(type)(*env)->DeleteLocalRef(env,type);if(bytes_type)(*env)->DeleteLocalRef(env,bytes_type);
  if(route)(*env)->DeleteLocalRef(env,route);if(selectors)(*env)->DeleteLocalRef(env,selectors);return result;
}
JNIEXPORT jobject JNICALL Java_org_exreader_host_NativeSearch_nativeNext(JNIEnv *env,jclass type,jlong handle,jint limit,jobject control) {
  host_search *search=search_owner(env,handle);reader_search_result batch={0};reader_search_error error={0};reader_search_status status;
  jobjectArray hits=NULL;jclass hit_type=NULL,batch_type=NULL;jmethodID constructor;jobject out=NULL;size_t i;(void)type;
  if(!search)return NULL;if(limit<1||limit>32){throw_argument(env,"Search batch must be bounded");return NULL;}
  search_control(env,search,control);if((*env)->ExceptionCheck(env))return NULL;
  status=reader_search_next(search->search,(size_t)limit,&batch,&error);
  if(status!=READER_SEARCH_OK){search_failure(env,status,error.sdk_code);goto done;}
  hit_type=(*env)->FindClass(env,"org/exreader/host/NativeSearch$Hit");if(!hit_type)goto done;
  hits=(*env)->NewObjectArray(env,(jsize)batch.count,hit_type,NULL);if(!hits)goto done;
  for(i=0;i<batch.count;i++){jobject hit=search_hit(env,search,&batch.hits[i]);if(!hit)goto done;(*env)->SetObjectArrayElement(env,hits,(jsize)i,hit);(*env)->DeleteLocalRef(env,hit);if((*env)->ExceptionCheck(env))goto done;}
  batch_type=(*env)->FindClass(env,"org/exreader/host/NativeSearch$Batch");if(!batch_type)goto done;
  constructor=(*env)->GetMethodID(env,batch_type,"<init>","([Lorg/exreader/host/NativeSearch$Hit;Z)V");
  if(constructor)out=(*env)->NewObject(env,batch_type,constructor,hits,(jboolean)batch.complete);
done:
  reader_search_result_free(&batch);if(hits)(*env)->DeleteLocalRef(env,hits);if(hit_type)(*env)->DeleteLocalRef(env,hit_type);if(batch_type)(*env)->DeleteLocalRef(env,batch_type);return out;
}
JNIEXPORT void JNICALL Java_org_exreader_host_NativeSearch_nativeClose(JNIEnv *env,jclass type,jlong handle) {
  host_search *search=search_owner(env,handle);reader_search_error error={0};reader_search_status status;(void)type;
  if(!search)return;status=reader_search_close(&search->search,&error);if(status!=READER_SEARCH_OK){search_failure(env,status,error.sdk_code);return;}search_free(env,search);
}
JNIEXPORT jlongArray JNICALL Java_org_exreader_host_NativeSearch_nativeResolve(JNIEnv *env,jclass type,jlong owner,jlong book,jint mode,jlong unit,jlong start,jlong end,jobjectArray route,jobjectArray selectors,jbyteArray font,jfloat size,jobject task) {
  exr_library *store=library(env,owner);char *fields[4]={0},*bytes[3]={0};size_t sizes[3]={0},i,count=0,page=SIZE_MAX;
  exr_document *document=NULL;exr_publication *publication=NULL;exr_font *face=NULL;exr_pager *pager=NULL;exr_fixed_document *fixed=NULL;exr_fixed_text *text=NULL;
  exr_anchor anchor={0};exr_fixed_anchor fixed_anchor={0};exr_anchor_match match={0};exr_error error={0};exr_status status=EXR_OK;
  host_control context;exr_control control={0};jlong values[4];jlongArray out=NULL;(void)type;
  if(!store||(*env)->ExceptionCheck(env))return NULL;
  if(book<=0||unit<0||start<0||end<start||!isfinite(size)||size<4||size>256||(uint64_t)unit>=SIZE_MAX||(uint64_t)end>=SIZE_MAX||!task||!route||!selectors||(*env)->GetArrayLength(env,route)!=4||(*env)->GetArrayLength(env,selectors)!=3){throw_argument(env,"Invalid search selector route");return NULL;}
  control=host_task_control(env,task,&context);if((*env)->ExceptionCheck(env))return NULL;
  for(i=0;i<4;i++){jstring value=(*env)->GetObjectArrayElement(env,route,(jsize)i);if(value){if((*env)->GetStringLength(env,value)>32768){(*env)->DeleteLocalRef(env,value);throw_argument(env,"Search route exceeds its bound");goto done;}fields[i]=input_string(env,value);(*env)->DeleteLocalRef(env,value);if(!fields[i])goto done;}}
  if(!fields[0]||!fields[0][0]||strlen(fields[0])>255){status=EXR_ARGUMENT;goto done;}
  for(i=0;i<3;i++){jbyteArray value=(*env)->GetObjectArrayElement(env,selectors,(jsize)i);jsize length=value?(*env)->GetArrayLength(env,value):-1;if(length<0||length>65536){if(value)(*env)->DeleteLocalRef(env,value);status=EXR_ARGUMENT;goto done;}bytes[i]=calloc((size_t)length+1,1);if(!bytes[i]){(*env)->DeleteLocalRef(env,value);status=EXR_MEMORY;goto done;}sizes[i]=(size_t)length;if(length)(*env)->GetByteArrayRegion(env,value,0,length,(jbyte *)bytes[i]);(*env)->DeleteLocalRef(env,value);if((*env)->ExceptionCheck(env))goto done;}
  anchor.start=(size_t)start;anchor.end=(size_t)end;anchor.exact=bytes[0];anchor.prefix=bytes[1];anchor.suffix=bytes[2];anchor.chapter=fields[3];
  if(mode!=READER_SEARCH_FIXED)for(i=0;i<3;i++)if(memchr(bytes[i],0,sizes[i])){status=EXR_ARGUMENT;goto done;}
  if(mode==READER_SEARCH_REFLOW){
    if(unit!=0){status=EXR_ARGUMENT;goto done;}status=exr_library_document(store,(int64_t)book,&document,&error);
    if(status==EXR_OK)status=exr_anchor_resolve_ex(document,&anchor,&control,&match,&error);page=0;
  }else if(mode==READER_SEARCH_EPUB){
    const exr_part *parts;exr_layout_config layout=exr_layout_config_defaults();exr_chapter_options options=exr_chapter_options_defaults();
    status=host_publication(store,(int64_t)book,&publication,&error);if(status!=EXR_OK)goto done;
    parts=exr_publication_parts(publication,&count);if((uint64_t)unit>=count||!fields[1]||strcmp(parts[(size_t)unit].path,fields[1])){status=EXR_ARGUMENT;goto done;}
    status=search_font(env,font,&face,&error);if(status!=EXR_OK)goto done;
    layout.page.width=600;layout.page.height=860;layout.page.margin=32;layout.page.font_size=size;layout.page.line_height=1.6f;layout.page.paragraph_spacing=12;layout.document_css=1;layout.embedded_fonts=1;layout.control=control;
    options.workspace_budget=8*1024*1024;options.window_bytes=64*1024;
    status=exr_publication_pager_create(publication,(size_t)unit,face,&layout,&options,&pager,&error);
    if(status==EXR_OK)status=exr_pager_anchor_resolve(pager,&anchor,&control,&match,&error);page=(size_t)unit;
  }else if(mode==READER_SEARCH_FIXED){
    exr_fixed_open_options options={0};const exr_fixed_page *pages;options.struct_size=sizeof(options);options.control=control;
    if(!fields[2]||!fields[2][0]){status=EXR_ARGUMENT;goto done;}
    status=search_font(env,font,&face,&error);options.fallback_font=face;if(status!=EXR_OK)goto done;
    status=exr_library_fixed_source(store,(int64_t)book,&options,&fixed,&error);if(status!=EXR_OK)goto done;
    pages=exr_fixed_pages(fixed,&count);for(i=0;i<count;i++)if(!strcmp(pages[i].id,fields[2])){page=i;break;}
    if(page==SIZE_MAX){match.state=EXR_ANCHOR_MISSING;goto resolved;}
    fixed_anchor.start=(size_t)start;fixed_anchor.end=(size_t)end;fixed_anchor.page_id=fields[2];fixed_anchor.exact=bytes[0];fixed_anchor.prefix=bytes[1];fixed_anchor.suffix=bytes[2];fixed_anchor.exact_size=sizes[0];fixed_anchor.prefix_size=sizes[1];fixed_anchor.suffix_size=sizes[2];
    status=exr_fixed_load_text(fixed,page,&control,&text,&error);if(status==EXR_OK)status=exr_fixed_anchor_resolve(pages[page].id,text,&fixed_anchor,&control,&match,&error);
  }else status=EXR_ARGUMENT;
resolved:
  if(match.state==EXR_ANCHOR_FOUND&&(match.start>INT64_MAX||match.end>INT64_MAX||match.end<match.start))status=EXR_ARGUMENT;
  if(status==EXR_OK&&!(*env)->ExceptionCheck(env)){values[0]=match.state;values[1]=page==SIZE_MAX?-1:(jlong)page;values[2]=match.state==EXR_ANCHOR_FOUND?(jlong)match.start:-1;values[3]=match.state==EXR_ANCHOR_FOUND?(jlong)match.end:-1;out=(*env)->NewLongArray(env,4);if(out)(*env)->SetLongArrayRegion(env,out,0,4,values);}
done:
  exr_fixed_text_free(text);exr_fixed_free(fixed);exr_pager_free(pager);exr_publication_free(publication);exr_document_free(document);exr_font_free(face);
  for(i=0;i<4;i++)free(fields[i]);for(i=0;i<3;i++)free(bytes[i]);if(status!=EXR_OK)search_failure(env,READER_SEARCH_SDK,status);return (*env)->ExceptionCheck(env)?NULL:out;
}
#ifdef READER_SEARCH_FIXTURES
JNIEXPORT jint JNICALL Java_org_exreader_host_NativeSearchProbe_live(JNIEnv *env,jclass type){(void)env;(void)type;return atomic_load(&host_search_live);}
JNIEXPORT jobjectArray JNICALL Java_org_exreader_host_NativeSearchProbe_identity(JNIEnv *env,jclass type){
  Dl_info sdk={0},module={0};jobjectArray out=new_row(env,3);(void)type;
  if(!dladdr((void *)exr_document_find,&sdk)||!dladdr((void *)reader_search_open_reflow,&module)){throw_argument(env,"Search provider identity unavailable");return NULL;}
  if(!out||!set_cell(env,out,0,sdk.dli_fname)||!set_cell(env,out,1,module.dli_fname)||!set_cell(env,out,2,READER_SEARCH_VERSION))return NULL;return out;
}
#endif
