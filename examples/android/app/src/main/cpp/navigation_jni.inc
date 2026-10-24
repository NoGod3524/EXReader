/* SPDX-License-Identifier: MIT */
#include <reader_navigation.h>
#include <pthread.h>
#include <stdatomic.h>
#include <math.h>

typedef struct {pthread_t owner;reader_navigation *snapshot;int mode;} host_navigation;
typedef struct {exr_publication *publication;exr_document *document;exr_fixed_document *fixed;exr_font *font;} navigation_input;
#ifdef READER_NAVIGATION_FIXTURES
static atomic_int host_navigation_live=0;
#endif
static void navigation_failure(JNIEnv *env,int code,int sdk) {
  jclass type;jmethodID init;jthrowable error;if((*env)->ExceptionCheck(env))return;
  type=(*env)->FindClass(env,"org/exreader/host/NativeNavigation$Failure");if(!type)return;
  init=(*env)->GetMethodID(env,type,"<init>","(II)V");error=init?(jthrowable)(*env)->NewObject(env,type,init,(jint)code,(jint)sdk):NULL;
  if(error){(*env)->Throw(env,error);(*env)->DeleteLocalRef(env,error);}(*env)->DeleteLocalRef(env,type);
}
static host_navigation *navigation_owner(JNIEnv *env,jlong handle) {
  host_navigation *value=(host_navigation *)(intptr_t)handle;
  if(!value||!pthread_equal(value->owner,pthread_self())){throw_argument(env,"Navigation requires its creating SDK owner");return NULL;}return value;
}
static void navigation_input_free(navigation_input *input) {
  exr_fixed_free(input->fixed);exr_document_free(input->document);exr_publication_free(input->publication);exr_font_free(input->font);memset(input,0,sizeof(*input));
}
static exr_status navigation_font(JNIEnv *env,jbyteArray font,exr_font **out,exr_error *error) {
  exr_font_input bytes={0};jbyte *data;jsize length=font?(*env)->GetArrayLength(env,font):0;exr_status status;
  if(length<=0||length>64*1024*1024)return EXR_ARGUMENT;data=(*env)->GetByteArrayElements(env,font,NULL);if(!data)return EXR_MEMORY;
  bytes.data=data;bytes.size=(size_t)length;status=exr_font_create(&bytes,1,out,error);(*env)->ReleaseByteArrayElements(env,font,data,JNI_ABORT);return status;
}
static exr_status navigation_input_open(JNIEnv *env,exr_library *store,jlong book,int mode,jbyteArray font,const exr_control *control,navigation_input *input,exr_error *error) {
  if(mode==READER_NAVIGATION_FROM_PUBLICATION)return host_publication(store,(int64_t)book,&input->publication,error);
  if(mode==READER_NAVIGATION_FROM_DOCUMENT)return exr_library_document(store,(int64_t)book,&input->document,error);
  if(mode==READER_NAVIGATION_FROM_FIXED){
    exr_fixed_open_options options={0};exr_status status=navigation_font(env,font,&input->font,error);if(status!=EXR_OK)return status;
    options.struct_size=sizeof(options);if(control)options.control=*control;options.fallback_font=input->font;
    return exr_library_fixed_source(store,(int64_t)book,&options,&input->fixed,error);
  }return EXR_ARGUMENT;
}
static long long navigation_number(uint64_t value){return value==READER_NAVIGATION_NONE?-1:(long long)value;}
JNIEXPORT jstring JNICALL Java_org_exreader_host_NativeNavigation_nativeVersion(JNIEnv *env,jclass type){(void)type;return output_string(env,exr_version());}
JNIEXPORT jlong JNICALL Java_org_exreader_host_NativeNavigation_nativeOpen(JNIEnv *env,jclass type,jlong owner,jlong book,jint mode,jstring source,jbyteArray font,jobject task) {
  exr_library *store=library(env,owner);navigation_input input={0};host_navigation *value=NULL;char *key=NULL;host_control context;exr_control control;exr_error sdk={0};reader_navigation_error error={0};reader_navigation_options options={0};reader_navigation_status status=READER_NAVIGATION_OK;exr_status opened;(void)type;
  if(!store||!task||book<=0){if(!(*env)->ExceptionCheck(env))throw_argument(env,"Navigation input is required");return 0;}
  key=input_string(env,source);if(!key)return 0;control=host_task_control(env,task,&context);if((*env)->ExceptionCheck(env))goto done;
  opened=navigation_input_open(env,store,book,mode,font,&control,&input,&sdk);if(opened!=EXR_OK){navigation_failure(env,READER_NAVIGATION_SDK,opened);goto done;}
  value=calloc(1,sizeof(*value));if(!value){navigation_failure(env,READER_NAVIGATION_MEMORY,0);goto done;}value->owner=pthread_self();value->mode=mode;
  options.struct_size=sizeof(options);options.source_key=key;options.control=control;
  if(mode==READER_NAVIGATION_FROM_PUBLICATION)status=reader_navigation_open_publication(input.publication,&options,&value->snapshot,&error);
  else if(mode==READER_NAVIGATION_FROM_DOCUMENT)status=reader_navigation_open_document(input.document,&options,&value->snapshot,&error);
  else status=reader_navigation_open_pages(input.fixed,&options,&value->snapshot,&error);
  if(status!=READER_NAVIGATION_OK){navigation_failure(env,status,error.sdk_code);free(value);value=NULL;}
done:
  navigation_input_free(&input);free(key);if((*env)->ExceptionCheck(env)&&value){reader_navigation_close(&value->snapshot,NULL);free(value);value=NULL;}
#ifdef READER_NAVIGATION_FIXTURES
  if(value)atomic_fetch_add(&host_navigation_live,1);
#endif
  return (jlong)(intptr_t)value;
}
JNIEXPORT jlongArray JNICALL Java_org_exreader_host_NativeNavigation_nativeInfo(JNIEnv *env,jclass type,jlong handle) {
  host_navigation *value=navigation_owner(env,handle);reader_navigation_info info={0};reader_navigation_error error={0};reader_navigation_status status;jlongArray result;jlong fields[8];(void)type;if(!value)return NULL;
  status=reader_navigation_info_get(value->snapshot,&info,&error);if(status!=READER_NAVIGATION_OK){navigation_failure(env,status,error.sdk_code);return NULL;}
  fields[0]=info.kind;fields[1]=info.source;fields[2]=info.author_outline;fields[3]=info.node_count;fields[4]=info.root_count;fields[5]=info.depth_levels;fields[6]=info.part_count;fields[7]=info.text_bytes;
  result=(*env)->NewLongArray(env,8);if(result)(*env)->SetLongArrayRegion(env,result,0,8,fields);return result;
}
JNIEXPORT jobjectArray JNICALL Java_org_exreader_host_NativeNavigation_nativePage(JNIEnv *env,jclass type,jlong handle,jlong parent,jlong first,jint limit) {
  host_navigation *value=navigation_owner(env,handle);reader_navigation_page page={0};reader_navigation_error error={0};reader_navigation_status status;jobjectArray result=NULL,row=NULL;size_t i;(void)type;
  if(!value)return NULL;if(parent< -1||first<0||limit<1||limit>32){throw_argument(env,"Invalid navigation page boundary");return NULL;}
  status=reader_navigation_children(value->snapshot,parent<0?READER_NAVIGATION_NONE:(uint64_t)parent,(uint64_t)first,(size_t)limit,&page,&error);
  if(status!=READER_NAVIGATION_OK){navigation_failure(env,status,error.sdk_code);return NULL;}
  result=new_rows(env,(jsize)page.count+1);row=new_row(env,2);if(!result||!row)goto done;
  if(!set_number(env,row,0,navigation_number(page.next))||!set_number(env,row,1,(long long)page.total))goto done;(*env)->SetObjectArrayElement(env,result,0,row);(*env)->DeleteLocalRef(env,row);row=NULL;
  for(i=0;i<page.count;i++){
    reader_navigation_row *r=page.rows+i;row=new_row(env,12);if(!row)goto done;
    if(!set_number(env,row,0,(long long)r->index)||!set_number(env,row,1,navigation_number(r->parent))||!set_number(env,row,2,navigation_number(r->part))||!set_number(env,row,3,r->depth)||!set_number(env,row,4,r->child_count)||!set_number(env,row,5,r->target_class)||!set_cell(env,row,6,r->label)||!set_cell(env,row,7,r->href)||!set_cell(env,row,8,r->base)||!set_cell(env,row,9,r->role)||!set_cell(env,row,10,r->part_path)||!set_cell(env,row,11,r->part_id))goto done;
    (*env)->SetObjectArrayElement(env,result,(jsize)i+1,row);(*env)->DeleteLocalRef(env,row);row=NULL;if((*env)->ExceptionCheck(env))goto done;
  }
done:
  if(row)(*env)->DeleteLocalRef(env,row);reader_navigation_page_free(&page);return (*env)->ExceptionCheck(env)?NULL:result;
}
/* Public DOM points have raw UTF-16 offsets. Only map bytes when the public
   normalized range is byte-identical to raw text; collapsed or surrogate-interior
   positions stay explicitly unmappable rather than becoming a guessed page. */
static int navigation_cfi_offset(const exr_document *document,const exr_cfi_point *point,size_t *offset) {
  const exr_node *nodes,*node;const char *text;size_t count,size,at=0,units=0,raw,child,k;
  nodes=exr_document_nodes(document,&count);text=exr_document_text(document,&size);if(point->node>=count)return 0;node=nodes+point->node;if(node->start>node->end||node->end>size)return 0;
  if(node->kind!=EXR_NODE_TEXT){
    if(point->offset==SIZE_MAX){*offset=node->start;return 1;}
    child=node->first_child;for(k=0;k<point->offset;k++){if(child==SIZE_MAX||child>=count)return 0;child=nodes[child].next_sibling;}
    if(child==SIZE_MAX){*offset=node->end;return 1;}if(child>=count)return 0;*offset=nodes[child].start;return *offset<=size;
  }
  if(!node->text||point->offset==SIZE_MAX)return 0;raw=strlen(node->text);if(raw!=node->end-node->start||memcmp(text+node->start,node->text,raw))return 0;
  while(at<raw&&units<point->offset){unsigned char c=(unsigned char)node->text[at];size_t bytes=c<0x80?1:c<0xe0?2:c<0xf0?3:4;size_t added=bytes==4?2:1;if(at+bytes>raw||units+added>point->offset)return 0;at+=bytes;units+=added;}
  if(units!=point->offset)return 0;*offset=node->start+at;return 1;
}
typedef struct {const char *text;size_t size,at;int mismatch;} navigation_projection;
static exr_status navigation_projection_chunk(void *opaque,const char *text,size_t size,exr_error *error) {
  navigation_projection *proof=opaque;(void)error;
  if(proof->at>proof->size||size>proof->size-proof->at||memcmp(proof->text+proof->at,text,size)){proof->mismatch=1;return EXR_FORMAT;}proof->at+=size;return EXR_OK;
}
/* No second chapter string: compare each public pager chunk with the already
   borrowed full-document projection. A different projection cannot authorize
   a destination byte offset. Configuration matches the actual reader. */
static int navigation_projection_equal(JNIEnv *env,exr_publication *publication,size_t part,const exr_document *document,jbyteArray bytes,float size,const exr_control *control,exr_error *error) {
  exr_font *font=NULL;exr_pager *pager=NULL;exr_layout_config config=exr_layout_config_defaults();exr_chapter_options options=exr_chapter_options_defaults();exr_status status;navigation_projection proof={0};int result=READER_NAVIGATION_SDK;
  proof.text=exr_document_text(document,&proof.size);status=navigation_font(env,bytes,&font,error);if(status!=EXR_OK)goto done;
  config.page.width=600;config.page.height=860;config.page.margin=32;config.page.font_size=size;config.page.line_height=1.6f;config.page.paragraph_spacing=12;config.document_css=1;config.embedded_fonts=1;if(control)config.control=*control;options.workspace_budget=8*1024*1024;options.window_bytes=64*1024;
  status=exr_publication_pager_create(publication,part,font,&config,&options,&pager,error);if(status!=EXR_OK)goto done;
  if(exr_pager_chapter_statistics(pager).projection_bytes!=proof.size){result=20;goto done;}
  status=exr_pager_read_text(pager,0,proof.size,navigation_projection_chunk,&proof,control,error);
  if(proof.mismatch){result=20;goto done;}if(status==EXR_OK)result=proof.at==proof.size?READER_NAVIGATION_OK:20;
done:
  exr_pager_free(pager);exr_font_free(font);if(status==EXR_CANCELLED)return READER_NAVIGATION_CANCELLED;return result;
}
/* A second, independently opened public SDK object verifies the module's native
   route and DOM identity. Only this verification produces a render destination. */
static int navigation_verify(JNIEnv *env,navigation_input *input,const reader_navigation_target *target,int status,jbyteArray font,float size,const exr_control *control,size_t *offset,exr_error *error) {
  const exr_node *nodes;const exr_chapter *chapters;exr_document *loaded=NULL,*document=input->document;size_t count=0,part=SIZE_MAX,node=SIZE_MAX,resource=SIZE_MAX,chapter=0;exr_status sdk=EXR_OK;char *uri=NULL;int result=READER_NAVIGATION_MISMATCH;
  *offset=0;
  if(input->fixed){const exr_fixed_page *pages=exr_fixed_pages(input->fixed,&count);if(target->kind==READER_NAVIGATION_RESULT_PAGE&&target->part<count&&target->part_id&&!strcmp(target->part_id,pages[target->part].id))return status;return result;}
  if(input->publication){
    const exr_part *parts=exr_publication_parts(input->publication,&count);if(target->part>=count||!target->part_path||!target->part_id||strcmp(target->part_path,parts[target->part].path?parts[target->part].path:"")||strcmp(target->part_id,parts[target->part].id?parts[target->part].id:""))goto done;
    if(target->kind==READER_NAVIGATION_RESULT_CFI){exr_cfi_point point={SIZE_MAX,SIZE_MAX,0};sdk=exr_publication_cfi_resolve(input->publication,target->cfi,control,&part,&loaded,&point,error);if(sdk!=EXR_OK||part!=target->part||point.node!=target->cfi_node||point.offset!=target->cfi_offset||point.side!=target->cfi_side)goto done;result=navigation_cfi_offset(loaded,&point,offset)?status:20;goto done;}
    sdk=exr_publication_load(input->publication,(size_t)target->part,&loaded,error);if(sdk!=EXR_OK)goto done;document=loaded;
  }else{
    chapters=exr_document_chapters(document,&count);if(target->part>=count||!target->part_path||!target->part_id||strcmp(target->part_path,chapters[target->part].path?chapters[target->part].path:"")||strcmp(target->part_id,chapters[target->part].id?chapters[target->part].id:""))goto done;chapter=(size_t)target->part;
  }
  if(target->fragment&&target->fragment[0]){size_t n=strlen(target->fragment);uri=malloc(n+2);if(!uri){result=READER_NAVIGATION_MEMORY;goto done;}uri[0]='#';memcpy(uri+1,target->fragment,n+1);sdk=exr_document_resolve(document,chapter,uri,&resource,&node,error);if(sdk!=EXR_OK||node!=target->node)goto done;if((status==READER_NAVIGATION_PART_ONLY)!=(node==SIZE_MAX))goto done;}
  else if(target->node!=READER_NAVIGATION_NONE)goto done;
  nodes=exr_document_nodes(document,&count);
  if(target->node!=READER_NAVIGATION_NONE){if(target->node>=count)goto done;*offset=nodes[target->node].start;}
  else if(!input->publication){size_t chapter_count;chapters=exr_document_chapters(document,&chapter_count);if(chapter>=chapter_count||chapters[chapter].root>=count)goto done;*offset=nodes[chapters[chapter].root].start;}
  result=status;
done:
  if((result==READER_NAVIGATION_OK||result==READER_NAVIGATION_PART_ONLY)&&document){size_t text_size;const char *text=exr_document_text(document,&text_size);if(*offset>text_size||(*offset<text_size&&((unsigned char)text[*offset]&0xc0)==0x80))result=20;}
  if((result==READER_NAVIGATION_OK||result==READER_NAVIGATION_PART_ONLY)&&input->publication&&loaded){int proof=navigation_projection_equal(env,input->publication,(size_t)target->part,loaded,font,size,control,error);if(proof!=READER_NAVIGATION_OK)result=proof;}
  free(uri);exr_document_free(loaded);if(sdk!=EXR_OK)return sdk==EXR_CANCELLED?READER_NAVIGATION_CANCELLED:READER_NAVIGATION_SDK;return result;
}
JNIEXPORT jobjectArray JNICALL Java_org_exreader_host_NativeNavigation_nativeResolve(JNIEnv *env,jclass type,jlong handle,jlong owner,jlong book,jint mode,jstring source,jlong row,jlong explicit_part,jstring cfi,jbyteArray font,jfloat size,jobject task) {
  host_navigation *value=navigation_owner(env,handle);exr_library *store=library(env,owner);navigation_input input={0},independent={0};char *key=NULL,*location=NULL;host_control context;exr_control control;reader_navigation_resolve_options options={0};reader_navigation_target target={0};reader_navigation_error error={0};exr_error sdk_error={0};exr_status opened;int status=READER_NAVIGATION_ARGUMENT;size_t offset=SIZE_MAX,i;jobjectArray result=NULL,fields=NULL,candidates=NULL;(void)type;
  if(!value||!store)return NULL;if(book<=0||mode!=value->mode||row< -1||explicit_part< -1||!isfinite(size)||size<18||size>40||!task){throw_argument(env,"Invalid navigation resolution input");return NULL;}
  key=input_string(env,source);if(!key)goto done;if(cfi){if((*env)->GetStringLength(env,cfi)>4096){throw_argument(env,"CFI exceeds limit");goto done;}location=input_string(env,cfi);if(!location)goto done;}
  control=host_task_control(env,task,&context);if((*env)->ExceptionCheck(env))goto done;opened=navigation_input_open(env,store,book,mode,font,&control,&input,&sdk_error);if(opened!=EXR_OK){navigation_failure(env,READER_NAVIGATION_SDK,opened);goto done;}
  options.struct_size=sizeof(options);options.source_key=key;options.explicit_part=explicit_part<0?READER_NAVIGATION_NONE:(uint64_t)explicit_part;options.control=control;
  if(location){if(mode!=READER_NAVIGATION_FROM_PUBLICATION)status=READER_NAVIGATION_CORRUPT;else status=reader_navigation_resolve_cfi(value->snapshot,input.publication,location,&options,&target,&error);}
  else if(row<0){throw_argument(env,"Navigation row is required");goto done;}
  else if(mode==READER_NAVIGATION_FROM_PUBLICATION)status=reader_navigation_resolve_publication(value->snapshot,(uint64_t)row,input.publication,&options,&target,&error);
  else if(mode==READER_NAVIGATION_FROM_DOCUMENT)status=reader_navigation_resolve_document(value->snapshot,(uint64_t)row,input.document,&options,&target,&error);
  else status=reader_navigation_resolve_page(value->snapshot,(uint64_t)row,input.fixed,&options,&target,&error);
  if((*env)->ExceptionCheck(env))goto done;
  if(status==READER_NAVIGATION_OK||status==READER_NAVIGATION_PART_ONLY){opened=navigation_input_open(env,store,book,mode,font,&control,&independent,&sdk_error);if(opened!=EXR_OK){navigation_failure(env,READER_NAVIGATION_SDK,opened);goto done;}status=navigation_verify(env,&independent,&target,status,font,size,&control,&offset,&sdk_error);if((*env)->ExceptionCheck(env))goto done;}
  if(status!=READER_NAVIGATION_OK&&status!=READER_NAVIGATION_PART_ONLY)offset=SIZE_MAX;
  if(target.candidate_count>10000){navigation_failure(env,READER_NAVIGATION_LIMIT,0);goto done;}
  result=new_rows(env,2);fields=new_row(env,13);candidates=new_row(env,(jsize)target.candidate_count);if(!result||!fields||!candidates)goto done;
  if(!set_number(env,fields,0,status)||!set_number(env,fields,1,target.kind)||!set_number(env,fields,2,navigation_number(target.row))||!set_number(env,fields,3,navigation_number(target.part))||!set_cell(env,fields,4,target.part_path?target.part_path:"")||!set_cell(env,fields,5,target.part_id?target.part_id:"")||!set_cell(env,fields,6,target.fragment?target.fragment:"")||!set_number(env,fields,7,navigation_number(target.node))||!set_cell(env,fields,8,target.cfi?target.cfi:"")||!set_number(env,fields,9,navigation_number(target.cfi_node))||!set_number(env,fields,10,navigation_number(target.cfi_offset))||!set_number(env,fields,11,target.cfi_side)||!set_number(env,fields,12,offset==SIZE_MAX?-1:(long long)offset))goto done;
  for(i=0;i<target.candidate_count;i++)if(!set_number(env,candidates,(jsize)i,(long long)target.candidates[i]))goto done;
  (*env)->SetObjectArrayElement(env,result,0,fields);(*env)->SetObjectArrayElement(env,result,1,candidates);
done:
  if(fields)(*env)->DeleteLocalRef(env,fields);if(candidates)(*env)->DeleteLocalRef(env,candidates);reader_navigation_target_free(&target);navigation_input_free(&input);navigation_input_free(&independent);free(key);free(location);return (*env)->ExceptionCheck(env)?NULL:result;
}
JNIEXPORT void JNICALL Java_org_exreader_host_NativeNavigation_nativeClose(JNIEnv *env,jclass type,jlong handle) {
  host_navigation *value=navigation_owner(env,handle);reader_navigation_error error={0};reader_navigation_status status;(void)type;if(!value)return;status=reader_navigation_close(&value->snapshot,&error);if(status!=READER_NAVIGATION_OK){navigation_failure(env,status,error.sdk_code);return;}
#ifdef READER_NAVIGATION_FIXTURES
  atomic_fetch_sub(&host_navigation_live,1);
#endif
  free(value);
}
#ifdef READER_NAVIGATION_FIXTURES
JNIEXPORT jint JNICALL Java_org_exreader_host_NativeNavigationProbe_live(JNIEnv *env,jclass type){(void)env;(void)type;return atomic_load(&host_navigation_live);}
JNIEXPORT jobjectArray JNICALL Java_org_exreader_host_NativeNavigationProbe_identity(JNIEnv *env,jclass type){Dl_info sdk={0},module={0};jobjectArray out=new_row(env,3);(void)type;if(!dladdr((void *)exr_document_resolve,&sdk)||!dladdr((void *)reader_navigation_children,&module)){throw_argument(env,"Navigation provider identity unavailable");return NULL;}if(!out||!set_cell(env,out,0,sdk.dli_fname)||!set_cell(env,out,1,module.dli_fname)||!set_cell(env,out,2,READER_NAVIGATION_VERSION))return NULL;return out;}
JNIEXPORT jstring JNICALL Java_org_exreader_host_NativeNavigationProbe_cfi(JNIEnv *env,jclass type,jlong owner,jlong book,jint mode){
  exr_library *store=library(env,owner);exr_publication *publication=NULL;exr_document *document=NULL;exr_error error={0};exr_status status;exr_cfi_point point={SIZE_MAX,SIZE_MAX,0};const exr_node *nodes;const char *wanted=mode==0?"intro":mode==1?"unicode":"collapsed";size_t count,i;char *cfi=NULL;jstring result=NULL;(void)type;if(!store)return NULL;
  status=host_publication(store,(int64_t)book,&publication,&error);if(status==EXR_OK)status=exr_publication_load(publication,1,&document,&error);if(status!=EXR_OK)goto done;
  nodes=exr_document_nodes(document,&count);for(i=0;i<count;i++){const char *id=exr_node_attribute(nodes+i,"id");if(id&&!strcmp(id,wanted)){point.node=i;if(mode!=0){point.node=nodes[i].first_child;point.offset=mode==1?1:3;}break;}}
  if(point.node==SIZE_MAX){status=EXR_ARGUMENT;goto done;}status=exr_publication_cfi_create(publication,1,document,&point,NULL,&cfi,&error);if(status==EXR_OK)result=output_string(env,cfi);
done:
  free(cfi);exr_document_free(document);exr_publication_free(publication);if(status!=EXR_OK)throw_status(env,status,&error,"Cannot create public navigation CFI fixture");return result;
}
#endif
