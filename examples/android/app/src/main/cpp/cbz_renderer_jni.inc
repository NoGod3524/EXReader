/* SPDX-License-Identifier: MIT */
/* App-local public C SDK wrapper. This is the very doc that paints CBZ frames. */
typedef struct {exr_fixed_document *document;char *key;} host_cbz;
static void host_cbz_free(host_cbz *reader){if(reader){exr_fixed_free(reader->document);free(reader->key);free(reader);}}
static jbyteArray host_cbz_bytes(JNIEnv *env,const void *bytes,size_t size){jbyteArray out;if(size>64*1024*1024){throw_argument(env,"CBZ frame exceeds byte limit");return NULL;}out=(*env)->NewByteArray(env,(jsize)size);if(out&&size)(*env)->SetByteArrayRegion(env,out,0,(jsize)size,(const jbyte *)bytes);return out;}
JNIEXPORT jlong JNICALL Java_org_exreader_host_NativeCbz_nativeOpen(JNIEnv *env,jclass type,jbyteArray bytes,jstring key,jobject task){
  host_cbz *reader=NULL;exr_fixed_open_options options={0};host_control context;exr_control control;exr_error error={0};exr_status status=EXR_ARGUMENT;jbyte *input=NULL;jsize size=bytes?(*env)->GetArrayLength(env,bytes):0;(void)type;
  if(size<=0||size>32*1024*1024||!key||!task){throw_argument(env,"Invalid CBZ original/control");return 0;}
  reader=calloc(1,sizeof(*reader));if(!reader){status=EXR_MEMORY;goto done;}reader->key=input_string(env,key);if(!reader->key)goto done;
  input=(*env)->GetByteArrayElements(env,bytes,NULL);if(!input)goto done;control=host_task_control(env,task,&context);if((*env)->ExceptionCheck(env))goto done;
  options.struct_size=sizeof(options);options.control=control;status=exr_fixed_open_memory(EXR_CBZ,input,(size_t)size,&options,&reader->document,&error);
done:
  if(input)(*env)->ReleaseByteArrayElements(env,bytes,input,JNI_ABORT);if(status!=EXR_OK&&!(*env)->ExceptionCheck(env))throw_status(env,status,&error,"Cannot open actual CBZ renderer");if(status!=EXR_OK||(*env)->ExceptionCheck(env)){host_cbz_free(reader);return 0;}return (jlong)(intptr_t)reader;
}
JNIEXPORT jobjectArray JNICALL Java_org_exreader_host_NativeCbz_nativePages(JNIEnv *env,jclass type,jlong handle){
  host_cbz *reader=(host_cbz *)(intptr_t)handle;size_t count=0,i;const exr_fixed_page *pages;jobjectArray out;(void)type;
  if(!reader){throw_argument(env,"CBZ renderer closed");return NULL;}pages=exr_fixed_pages(reader->document,&count);if(!count||count>10000){throw_argument(env,"Invalid actual CBZ page directory");return NULL;}out=new_row(env,(jsize)count);for(i=0;out&&i<count;i++)if(!set_cell(env,out,(jsize)i,pages[i].id))break;return (*env)->ExceptionCheck(env)?NULL:out;
}
JNIEXPORT jobject JNICALL Java_org_exreader_host_NativeCbz_nativeRender(JNIEnv *env,jclass type,jlong handle,jint page,jdouble scale,jobject task){
  host_cbz *reader=(host_cbz *)(intptr_t)handle;exr_bitmap bitmap={0};exr_fixed_text *text=NULL;exr_fixed_render_options options={0};host_control context;exr_control control;exr_error error={0};exr_status status=EXR_ARGUMENT;size_t count=0,text_size=0,regions=0;const exr_fixed_page *pages;const char *string;jint values[7];jintArray meta=NULL;jbyteArray pixels=NULL,utf8=NULL;jstring id=NULL;jclass target=NULL;jmethodID ctor;jobject result=NULL;(void)type;
  if(!reader||page<0||!isfinite(scale)||scale<=0||scale>80||!task){throw_argument(env,"Invalid CBZ render request");return NULL;}pages=exr_fixed_pages(reader->document,&count);if((size_t)page>=count){throw_argument(env,"CBZ page outside current renderer");return NULL;}
  control=host_task_control(env,task,&context);if((*env)->ExceptionCheck(env))goto done;options.channels=4;options.background=0xffffffff;options.control=control;
  status=exr_fixed_render(reader->document,(size_t)page,scale,&options,&bitmap,&error);if(status!=EXR_OK)goto done;
  status=exr_fixed_load_text(reader->document,(size_t)page,&control,&text,&error);if(status!=EXR_OK)goto done;string=exr_fixed_text_string(text,&text_size);exr_fixed_text_regions(text,&regions);
  if(!text||!string||text_size||regions){status=EXR_UNSUPPORTED;goto done;}
  values[0]=(jint)bitmap.width;values[1]=(jint)bitmap.height;values[2]=(jint)bitmap.stride;values[3]=(jint)bitmap.channels;values[4]=text!=NULL;values[5]=(jint)text_size;values[6]=(jint)regions;
  meta=(*env)->NewIntArray(env,7);pixels=host_cbz_bytes(env,bitmap.pixels,(size_t)bitmap.stride*bitmap.height);utf8=host_cbz_bytes(env,string,text_size);id=output_string(env,pages[page].id);if(!meta||!pixels||!utf8||!id)goto done;(*env)->SetIntArrayRegion(env,meta,0,7,values);
  target=(*env)->FindClass(env,"org/exreader/host/NativeCbz$Frame");if(!target)goto done;ctor=(*env)->GetMethodID(env,target,"<init>","([I[B[BLjava/lang/String;)V");if(ctor)result=(*env)->NewObject(env,target,ctor,meta,pixels,utf8,id);
done:
  exr_bitmap_free(&bitmap);exr_fixed_text_free(text);if(meta)(*env)->DeleteLocalRef(env,meta);if(pixels)(*env)->DeleteLocalRef(env,pixels);if(utf8)(*env)->DeleteLocalRef(env,utf8);if(id)(*env)->DeleteLocalRef(env,id);if(target)(*env)->DeleteLocalRef(env,target);if(status!=EXR_OK&&!(*env)->ExceptionCheck(env))throw_status(env,status,&error,"CBZ renderer requires a genuine empty public text snapshot");return (*env)->ExceptionCheck(env)?NULL:result;
}
JNIEXPORT jobject JNICALL Java_org_exreader_host_NativeCbz_nativeResolve(JNIEnv *env,jclass type,jlong handle,jstring page_id,jlong start,jlong end,jobjectArray selectors,jobject task){
  host_cbz *reader=(host_cbz *)(intptr_t)handle;exr_fixed_text *snapshot=NULL;exr_fixed_anchor anchor={0},recaptured={0};exr_anchor_match match={0};exr_error error={0};exr_status status=EXR_ARGUMENT;host_control context;exr_control control;char *id=NULL,*text[3]={0};size_t lengths[3]={0},count=0,unit=SIZE_MAX,i;const exr_fixed_page *pages;jlong values[5];jlongArray numeric=NULL;jclass target=NULL;jmethodID ctor;jobject capture=NULL,result=NULL;(void)type;
  if(!reader||!page_id||!selectors||(*env)->GetArrayLength(env,selectors)!=3||!task||(uint64_t)start>(uint64_t)end){throw_argument(env,"Invalid current CBZ selector");return NULL;}id=input_string(env,page_id);if(!id)goto done;
  for(i=0;i<3;i++){jbyteArray input=(*env)->GetObjectArrayElement(env,selectors,(jsize)i);jsize size=input?(*env)->GetArrayLength(env,input):0;if(size>(i?128:65536)){if(input)(*env)->DeleteLocalRef(env,input);throw_argument(env,"CBZ selector exceeds byte limit");goto done;}if(input){text[i]=calloc((size_t)size+1,1);if(!text[i]){(*env)->DeleteLocalRef(env,input);status=EXR_MEMORY;goto done;}if(size)(*env)->GetByteArrayRegion(env,input,0,size,(jbyte *)text[i]);lengths[i]=(size_t)size;(*env)->DeleteLocalRef(env,input);if((*env)->ExceptionCheck(env))goto done;}}
  anchor.page_id=id;anchor.start=(size_t)(uint64_t)start;anchor.end=(size_t)(uint64_t)end;anchor.exact=text[0];anchor.prefix=text[1];anchor.suffix=text[2];anchor.exact_size=lengths[0];anchor.prefix_size=lengths[1];anchor.suffix_size=lengths[2];
  control=host_task_control(env,task,&context);if((*env)->ExceptionCheck(env))goto done;status=EXR_OK;
  pages=exr_fixed_pages(reader->document,&count);for(i=0;i<count;i++)if(!strcmp(pages[i].id,id)){unit=i;break;}
  match.state=EXR_ANCHOR_MISSING;match.start=match.end=SIZE_MAX;
  if(unit!=SIZE_MAX){status=exr_fixed_load_text(reader->document,unit,&control,&snapshot,&error);if(status==EXR_OK)status=exr_fixed_anchor_resolve(pages[unit].id,snapshot,&anchor,&control,&match,&error);if(status!=EXR_OK)goto done;}
  if(match.state==EXR_ANCHOR_FOUND){status=exr_fixed_anchor_create(pages[unit].id,snapshot,match.start,match.end,&recaptured,&error);if(status!=EXR_OK)goto done;capture=reading_sdk_capture_value(env,3,unit,reader->key,NULL,NULL,&recaptured);if(!capture)goto done;}
  values[0]=EXR_OK;values[1]=match.state;values[2]=unit==SIZE_MAX?-1:(jlong)unit;values[3]=match.state==EXR_ANCHOR_FOUND?(jlong)match.start:-1;values[4]=match.state==EXR_ANCHOR_FOUND?(jlong)match.end:-1;
  numeric=(*env)->NewLongArray(env,5);target=(*env)->FindClass(env,"org/exreader/host/NativeReadingSdk$Match");if(!numeric||!target)goto done;(*env)->SetLongArrayRegion(env,numeric,0,5,values);ctor=(*env)->GetMethodID(env,target,"<init>","([JLorg/exreader/host/ReadingCapture;)V");if(ctor)result=(*env)->NewObject(env,target,ctor,numeric,capture);
done:
  exr_fixed_text_free(snapshot);exr_fixed_anchor_free(&recaptured);free(id);for(i=0;i<3;i++)free(text[i]);if(numeric)(*env)->DeleteLocalRef(env,numeric);if(target)(*env)->DeleteLocalRef(env,target);if(capture)(*env)->DeleteLocalRef(env,capture);if(status!=EXR_OK&&!(*env)->ExceptionCheck(env))throw_status(env,status,&error,"Cannot resolve against current CBZ renderer");return (*env)->ExceptionCheck(env)?NULL:result;
}
JNIEXPORT void JNICALL Java_org_exreader_host_NativeCbz_nativeClose(JNIEnv *env,jclass type,jlong handle){(void)env;(void)type;host_cbz_free((host_cbz *)(intptr_t)handle);}
