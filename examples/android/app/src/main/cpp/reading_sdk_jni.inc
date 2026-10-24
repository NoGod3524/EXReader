/* SPDX-License-Identifier: MIT */
/* SDK-only half: real public captures and FOUND-only independent resolution. */
#include <math.h>
typedef struct {
  exr_document *document;exr_publication *publication;exr_font *font;exr_pager *pager;
  exr_fixed_document *fixed;exr_fixed_text *text;const exr_part *parts;size_t part_count,unit;
} host_reading_input;
static void reading_sdk_free(host_reading_input *input){exr_fixed_text_free(input->text);exr_fixed_free(input->fixed);exr_pager_free(input->pager);exr_font_free(input->font);exr_publication_free(input->publication);exr_document_free(input->document);memset(input,0,sizeof(*input));}
static exr_status reading_sdk_open(JNIEnv *env,exr_library *store,jlong book,int mode,uint64_t unit,const char *path,int resolve_legacy,jbyteArray bytes,float size,const exr_control *control,host_reading_input *input,exr_error *error){
  exr_status status;exr_layout_config config=exr_layout_config_defaults();exr_chapter_options chapter=exr_chapter_options_defaults();
  input->unit=SIZE_MAX;
  if(mode==1){if(unit!=0)return EXR_ARGUMENT;input->unit=0;return exr_library_document(store,(int64_t)book,&input->document,error);}
  if(mode==2){
    size_t i,found=SIZE_MAX,count=0;status=host_publication(store,(int64_t)book,&input->publication,error);if(status!=EXR_OK)return status;
    input->parts=exr_publication_parts(input->publication,&input->part_count);if(!path||!path[0])return EXR_ARGUMENT;
    if(resolve_legacy&&unit==UINT64_MAX){for(i=0;i<input->part_count;i++)if(input->parts[i].path&&!strcmp(path,input->parts[i].path)){found=i;count++;}if(count!=1)return EXR_ARGUMENT;input->unit=found;}
    else{if(unit>=input->part_count||!input->parts[(size_t)unit].path||strcmp(path,input->parts[(size_t)unit].path))return EXR_ARGUMENT;input->unit=(size_t)unit;}
    status=host_font_bytes(env,bytes,&input->font,error);if(status!=EXR_OK)return status;
    config.page.width=600;config.page.height=860;config.page.margin=32;config.page.font_size=size;config.page.line_height=1.6f;config.page.paragraph_spacing=12;config.document_css=1;config.embedded_fonts=1;if(control)config.control=*control;
    chapter.workspace_budget=8*1024*1024;chapter.window_bytes=64*1024;
    return exr_publication_pager_create(input->publication,input->unit,input->font,&config,&chapter,&input->pager,error);
  }
  if(mode==3){exr_fixed_open_options options={0};status=host_font_bytes(env,bytes,&input->font,error);if(status!=EXR_OK)return status;options.struct_size=sizeof(options);options.fallback_font=input->font;if(control)options.control=*control;return exr_library_fixed_source(store,(int64_t)book,&options,&input->fixed,error);}
  return EXR_ARGUMENT;
}
static jbyteArray reading_sdk_bytes(JNIEnv *env,const char *data,size_t size){jbyteArray result;if(!data)return NULL;if(size>65536){throw_argument(env,"Reading selector exceeds its byte limit");return NULL;}result=(*env)->NewByteArray(env,(jsize)size);if(result&&size)(*env)->SetByteArrayRegion(env,result,0,(jsize)size,(const jbyte *)data);return result;}
static jobject reading_sdk_capture_value(JNIEnv *env,int mode,size_t unit,const char *key,const char *path,const exr_anchor *anchor,const exr_fixed_anchor *fixed){
  const char *text[3];size_t lengths[3],i;char parser[65];jclass type=NULL,byte_type=NULL;jmethodID constructor;jlong numbers[4];jlongArray numeric=NULL;jobjectArray route=NULL,selectors=NULL;jbyteArray bytes=NULL;jobject result=NULL;
  snprintf(parser,sizeof(parser),"exreader-sdk-%s",exr_version());numbers[0]=mode;numbers[1]=(jlong)unit;numbers[2]=(jlong)(fixed?fixed->start:anchor->start);numbers[3]=(jlong)(fixed?fixed->end:anchor->end);
  numeric=(*env)->NewLongArray(env,4);route=new_row(env,5);byte_type=(*env)->FindClass(env,"[B");if(!numeric||!route||!byte_type)goto done;(*env)->SetLongArrayRegion(env,numeric,0,4,numbers);
  if(!set_cell(env,route,0,key)||!set_cell(env,route,1,parser))goto done;
  if(path&&!set_cell(env,route,2,path))goto done;if(fixed&&fixed->page_id&&!set_cell(env,route,3,fixed->page_id))goto done;if(anchor&&anchor->chapter&&!set_cell(env,route,4,anchor->chapter))goto done;
  selectors=(*env)->NewObjectArray(env,3,byte_type,NULL);if(!selectors)goto done;
  if(fixed){text[0]=fixed->exact;text[1]=fixed->prefix;text[2]=fixed->suffix;lengths[0]=fixed->exact_size;lengths[1]=fixed->prefix_size;lengths[2]=fixed->suffix_size;}
  else{text[0]=anchor->exact;text[1]=anchor->prefix;text[2]=anchor->suffix;for(i=0;i<3;i++)lengths[i]=text[i]?strlen(text[i]):0;}
  for(i=0;i<3;i++){bytes=reading_sdk_bytes(env,text[i],lengths[i]);if((*env)->ExceptionCheck(env))goto done;(*env)->SetObjectArrayElement(env,selectors,(jsize)i,bytes);if(bytes)(*env)->DeleteLocalRef(env,bytes);bytes=NULL;}
  type=(*env)->FindClass(env,"org/exreader/host/ReadingCapture");if(!type)goto done;constructor=(*env)->GetMethodID(env,type,"<init>","([J[Ljava/lang/String;[[B)V");if(!constructor)goto done;result=(*env)->NewObject(env,type,constructor,numeric,route,selectors);
done:
  if(bytes)(*env)->DeleteLocalRef(env,bytes);if(type)(*env)->DeleteLocalRef(env,type);if(byte_type)(*env)->DeleteLocalRef(env,byte_type);if(numeric)(*env)->DeleteLocalRef(env,numeric);if(route)(*env)->DeleteLocalRef(env,route);if(selectors)(*env)->DeleteLocalRef(env,selectors);return result;
}
static exr_status reading_sdk_capture_at(host_reading_input *input,int mode,size_t unit,size_t start,size_t end,const exr_control *control,exr_anchor *anchor,exr_fixed_anchor *fixed,exr_error *error){
  if(mode==1)return exr_anchor_create(input->document,start,end,anchor,error);
  if(mode==2)return exr_pager_anchor_create(input->pager,start,end,control,anchor,error);
  if(mode==3){size_t count;const exr_fixed_page *pages=exr_fixed_pages(input->fixed,&count);exr_status status;if(unit>=count)return EXR_ARGUMENT;input->unit=unit;status=exr_fixed_load_text(input->fixed,unit,control,&input->text,error);if(status!=EXR_OK)return status;return exr_fixed_anchor_create(pages[unit].id,input->text,start,end,fixed,error);}
  return EXR_ARGUMENT;
}
JNIEXPORT jstring JNICALL Java_org_exreader_host_NativeReadingSdk_nativeVersion(JNIEnv *env,jclass type){(void)type;return output_string(env,exr_version());}
JNIEXPORT jobject JNICALL Java_org_exreader_host_NativeReadingSdk_nativeCapture(JNIEnv *env,jclass type,jlong owner,jlong book,jint mode,jlong unit,jstring path,jlong start,jlong end,jstring source,jbyteArray bytes,jfloat size,jobject task){
  exr_library *store=library(env,owner);host_reading_input input={0};exr_anchor anchor={0};exr_fixed_anchor fixed={0};exr_error error={0};exr_status status=EXR_ARGUMENT;char *key=NULL,*part_path=NULL;host_control context;exr_control control;jobject result=NULL;(void)type;
  if(!store)return NULL;if(book<=0||unit<0||start<0||end<start||!isfinite(size)||size<18||size>40||!task){throw_argument(env,"Invalid actual reading capture input");return NULL;}
  key=input_string(env,source);if(!key)goto done;if(path){part_path=input_string(env,path);if(!part_path)goto done;}control=host_task_control(env,task,&context);if((*env)->ExceptionCheck(env))goto done;
  status=reading_sdk_open(env,store,book,mode,(uint64_t)unit,part_path,0,bytes,size,&control,&input,&error);if(status!=EXR_OK)goto done;
  status=reading_sdk_capture_at(&input,mode,(size_t)unit,(size_t)start,(size_t)end,&control,&anchor,&fixed,&error);if(status==EXR_OK)result=reading_sdk_capture_value(env,mode,input.unit,key,mode==2?input.parts[input.unit].path:NULL,mode==3?NULL:&anchor,mode==3?&fixed:NULL);
done:
  exr_anchor_free(&anchor);exr_fixed_anchor_free(&fixed);reading_sdk_free(&input);free(key);free(part_path);if(status!=EXR_OK&&!(*env)->ExceptionCheck(env))throw_status(env,status,&error,"Cannot capture the actual reading selection");return (*env)->ExceptionCheck(env)?NULL:result;
}
JNIEXPORT jobject JNICALL Java_org_exreader_host_NativeReadingSdk_nativeResolve(JNIEnv *env,jclass type,jlong owner,jlong book,jlongArray numeric,jobjectArray route,jobjectArray selectors,jbyteArray bytes,jfloat size,jobject task){
  exr_library *store=library(env,owner);host_reading_input input={0};exr_anchor anchor={0},recaptured={0};exr_fixed_anchor fixed={0},recaptured_fixed={0};exr_anchor_match match={0};exr_error error={0};exr_status status=EXR_ARGUMENT;host_control context;exr_control control;jlong number[4],values[5];char *field[5]={0},*text[3]={0};size_t lengths[3]={0},i,count=0;int mode=0;jobject capture=NULL,result=NULL;jlongArray output=NULL;jclass target=NULL;jmethodID constructor;(void)type;
  if(!store)return NULL;if(book<=0||!numeric||!route||!selectors||!task||(*env)->GetArrayLength(env,numeric)!=4||(*env)->GetArrayLength(env,route)!=5||(*env)->GetArrayLength(env,selectors)!=3||!isfinite(size)||size<18||size>40){throw_argument(env,"Invalid reading resolution input");return NULL;}
  (*env)->GetLongArrayRegion(env,numeric,0,4,number);mode=(int)number[0];if(mode<1||mode>3||(uint64_t)number[2]>(uint64_t)number[3]){throw_argument(env,"Invalid reading selector range");return NULL;}
  for(i=0;i<5;i++){jstring value=(*env)->GetObjectArrayElement(env,route,(jsize)i);if(value){if((*env)->GetStringLength(env,value)>65536){(*env)->DeleteLocalRef(env,value);throw_argument(env,"Reading route exceeds its limit");goto done;}field[i]=input_string(env,value);(*env)->DeleteLocalRef(env,value);if(!field[i])goto done;}}
  if(!field[0]||!field[1]){throw_argument(env,"Reading original identity is required");goto done;}
  for(i=0;i<3;i++){jbyteArray value=(*env)->GetObjectArrayElement(env,selectors,(jsize)i);jsize length=value?(*env)->GetArrayLength(env,value):0;if(length>(i?128:65536)){if(value)(*env)->DeleteLocalRef(env,value);throw_argument(env,"Reading selector exceeds its limit");goto done;}if(value){text[i]=calloc((size_t)length+1,1);if(!text[i]){(*env)->DeleteLocalRef(env,value);status=EXR_MEMORY;goto done;}if(length)(*env)->GetByteArrayRegion(env,value,0,length,(jbyte *)text[i]);lengths[i]=(size_t)length;(*env)->DeleteLocalRef(env,value);if((*env)->ExceptionCheck(env))goto done;}}
  if(mode!=3)for(i=0;i<3;i++)if(text[i]&&memchr(text[i],0,lengths[i])){throw_argument(env,"Reflow selector contains NUL");goto done;}
  control=host_task_control(env,task,&context);if((*env)->ExceptionCheck(env))goto done;
  status=reading_sdk_open(env,store,book,mode,(uint64_t)number[1],field[2],1,bytes,size,&control,&input,&error);if(status!=EXR_OK)goto done;
  anchor.start=(size_t)(uint64_t)number[2];anchor.end=(size_t)(uint64_t)number[3];anchor.exact=text[0];anchor.prefix=text[1];anchor.suffix=text[2];anchor.chapter=field[4];
  if(mode==1)status=exr_anchor_resolve_ex(input.document,&anchor,&control,&match,&error);
  else if(mode==2)status=exr_pager_anchor_resolve(input.pager,&anchor,&control,&match,&error);
  else{
    const exr_fixed_page *pages=exr_fixed_pages(input.fixed,&count);if(!field[3]||!field[3][0]){status=EXR_ARGUMENT;goto done;}
    input.unit=SIZE_MAX;for(i=0;i<count;i++)if(!strcmp(pages[i].id,field[3])){input.unit=i;break;}
    if(input.unit==SIZE_MAX){match.state=EXR_ANCHOR_MISSING;status=EXR_OK;}
    else{fixed.start=(size_t)(uint64_t)number[2];fixed.end=(size_t)(uint64_t)number[3];fixed.page_id=field[3];fixed.exact=text[0];fixed.prefix=text[1];fixed.suffix=text[2];fixed.exact_size=lengths[0];fixed.prefix_size=lengths[1];fixed.suffix_size=lengths[2];status=exr_fixed_load_text(input.fixed,input.unit,&control,&input.text,&error);if(status==EXR_OK)status=exr_fixed_anchor_resolve(pages[input.unit].id,input.text,&fixed,&control,&match,&error);}
  }
  if(status!=EXR_OK)goto done;
  if(match.state==EXR_ANCHOR_FOUND){
    if(mode==3){const exr_fixed_page *pages=exr_fixed_pages(input.fixed,&count);status=exr_fixed_anchor_create(pages[input.unit].id,input.text,match.start,match.end,&recaptured_fixed,&error);}
    else status=mode==2?exr_pager_anchor_create(input.pager,match.start,match.end,&control,&recaptured,&error):exr_anchor_create(input.document,match.start,match.end,&recaptured,&error);
    if(status!=EXR_OK)goto done;capture=reading_sdk_capture_value(env,mode,input.unit,field[0],mode==2?input.parts[input.unit].path:NULL,mode==3?NULL:&recaptured,mode==3?&recaptured_fixed:NULL);if(!capture)goto done;
  }
  values[0]=status;values[1]=match.state;values[2]=input.unit==SIZE_MAX?-1:(jlong)input.unit;values[3]=match.state==EXR_ANCHOR_FOUND?(jlong)match.start:-1;values[4]=match.state==EXR_ANCHOR_FOUND?(jlong)match.end:-1;
  output=(*env)->NewLongArray(env,5);target=(*env)->FindClass(env,"org/exreader/host/NativeReadingSdk$Match");if(!output||!target)goto done;(*env)->SetLongArrayRegion(env,output,0,5,values);constructor=(*env)->GetMethodID(env,target,"<init>","([JLorg/exreader/host/ReadingCapture;)V");if(constructor)result=(*env)->NewObject(env,target,constructor,output,capture);
done:
  if(capture)(*env)->DeleteLocalRef(env,capture);if(output)(*env)->DeleteLocalRef(env,output);if(target)(*env)->DeleteLocalRef(env,target);exr_anchor_free(&recaptured);exr_fixed_anchor_free(&recaptured_fixed);reading_sdk_free(&input);for(i=0;i<5;i++)free(field[i]);for(i=0;i<3;i++)free(text[i]);if(status!=EXR_OK&&!(*env)->ExceptionCheck(env))throw_status(env,status,&error,"Cannot resolve the selected reading record");return (*env)->ExceptionCheck(env)?NULL:result;
}
