/* SPDX-License-Identifier: MIT */
/* App-local public-API bridge. Included after the common JNI string helpers. */
#include <time.h>
typedef struct {
  exr_library *library;
  exr_source source;
  int64_t book;
  exr_publication *publication;
  exr_font *font;
  exr_pager *pager;
  exr_layout *page;
  size_t part;
  uint64_t next_calls;
  exr_document *document; /* Borrowed only by app-local themed reflow pagers. */
  int borrowed_font, themed;
  uint32_t background;
} host_epub;
typedef struct { JNIEnv *env; jobject task; jmethodID check; uint64_t deadline_ns; int expired; } host_control;
static uint64_t host_now_ns(void) {
  struct timespec value; clock_gettime(CLOCK_MONOTONIC,&value);
  return (uint64_t)value.tv_sec*1000000000u+(uint64_t)value.tv_nsec;
}
static int host_cancelled(void *context) {
  host_control *control=context;
  if((*control->env)->ExceptionCheck(control->env)) return 1;
  (*control->env)->CallVoidMethod(control->env,control->task,control->check);
  if((*control->env)->ExceptionCheck(control->env)) return 1;
  if(control->deadline_ns && host_now_ns()>=control->deadline_ns) { control->expired=1; return 1; }
  return 0;
}
static exr_control host_task_control(JNIEnv *env,jobject task,host_control *context) {
  exr_control control={0}; jclass type=(*env)->GetObjectClass(env,task);
  context->env=env; context->task=task;
  context->deadline_ns=0; context->expired=0;
  context->check=type?(*env)->GetMethodID(env,type,"check","()V"):NULL;
  if(type) (*env)->DeleteLocalRef(env,type);
  control.cancelled=host_cancelled; control.context=context; return control;
}
#if defined(READER_HOST_SEARCH) || defined(READER_HOST_NAVIGATION) || defined(READER_HOST_READING)
static exr_status host_font_bytes(JNIEnv *env,jbyteArray input,exr_font **font,exr_error *error) {
  jsize length=input?(*env)->GetArrayLength(env,input):0;jbyte *bytes;exr_font_input value={0};exr_status status;
  if(length<=0||length>64*1024*1024)return EXR_ARGUMENT;
  bytes=(*env)->GetByteArrayElements(env,input,NULL);if(!bytes)return EXR_MEMORY;
  value.data=bytes;value.size=(size_t)length;status=exr_font_create(&value,1,font,error);
  (*env)->ReleaseByteArrayElements(env,input,bytes,JNI_ABORT);return status;
}
#endif
static int bounded_mode(JNIEnv *env,exr_library *store,int64_t book) {
  exr_library_epub_info info={sizeof(info),0,0}; exr_error error={0};
  exr_status status=exr_library_epub_info_get(store,book,&info,&error);
  if(status==EXR_FORMAT || status==EXR_UNSUPPORTED) return 0;
  if(status!=EXR_OK) { throw_status(env,status,&error,"Cannot query EPUB storage mode"); return -1; }
  return info.bounded_storage;
}
JNIEXPORT jboolean JNICALL Java_org_exreader_host_NativeLibrary_nativeBounded(JNIEnv *env,jclass type,jlong owner,jlong book) {
  exr_library *store=library(env,owner); (void)type;
  return store && bounded_mode(env,store,(int64_t)book)>0;
}
static exr_status host_publication(exr_library *store,int64_t book,exr_publication **out,exr_error *error) {
  exr_source source={0}; exr_status status=exr_library_source(store,book,&source,error);
  if(status==EXR_OK) {
    status=exr_publication_open_source(&source,out,error);
    if(status!=EXR_OK) source.release(source.context);
  }
  return status;
}
static int location_cells(JNIEnv *env,jobjectArray row,jsize base,const exr_epub_location *location) {
  return set_number(env,row,base,(long long)location->part) && set_cell(env,row,base+1,location->path) &&
    set_number(env,row,base+2,(long long)location->selector.start) && set_number(env,row,base+3,(long long)location->selector.end) &&
    set_cell(env,row,base+4,location->selector.exact) && set_cell(env,row,base+5,location->selector.prefix) &&
    set_cell(env,row,base+6,location->selector.suffix) && set_cell(env,row,base+7,location->selector.chapter);
}
static jobjectArray bounded_notes(JNIEnv *env,exr_library *store,int64_t book) {
  exr_epub_note *notes=NULL; size_t count=0,i; exr_error error={0}; jobjectArray rows=NULL;
  exr_status status=exr_library_epub_notes(store,book,&notes,&count,&error);
  if(status!=EXR_OK) { throw_status(env,status,&error,"Cannot query chapter annotations"); return NULL; }
  if(count>INT_MAX) { throw_argument(env,"Too many chapter annotations"); goto done; }
  rows=new_rows(env,(jsize)count);
  for(i=0;rows && i<count;i++) {
    jobjectArray row=new_row(env,13);
    if(!row) break;
    if(!set_number(env,row,0,notes[i].id) || !set_number(env,row,1,notes[i].location.selector.start) ||
       !set_number(env,row,2,notes[i].location.selector.end) || !set_cell(env,row,3,notes[i].text) ||
       !set_cell(env,row,4,notes[i].location.selector.exact) || !location_cells(env,row,5,&notes[i].location)) {
      (*env)->DeleteLocalRef(env,row); break;
    }
    (*env)->SetObjectArrayElement(env,rows,(jsize)i,row); (*env)->DeleteLocalRef(env,row);
  }
done:
  exr_epub_notes_free(notes,count); return (*env)->ExceptionCheck(env)?NULL:rows;
}
static int bounded_note_owner(JNIEnv *env,exr_library *store,int64_t book,int64_t id) {
  exr_epub_note *notes=NULL; size_t count=0,i; int found=0; exr_error error={0};
  exr_status status=exr_library_epub_notes(store,book,&notes,&count,&error);
  if(status==EXR_OK) for(i=0;i<count;i++) if(notes[i].id==id) found=1;
  exr_epub_notes_free(notes,count);
  if(status!=EXR_OK) throw_status(env,status,&error,"Cannot verify chapter annotation ownership");
  else if(!found) throw_argument(env,"Chapter annotation does not belong to this book");
  return status==EXR_OK && found;
}
JNIEXPORT jobjectArray JNICALL Java_org_exreader_host_BoundedEpub_nativeParts(JNIEnv *env,jclass type,jlong owner,jlong book) {
  exr_library *store=library(env,owner); exr_publication *publication=NULL; exr_error error={0};
  const exr_part *parts; size_t count=0,i; jobjectArray rows=NULL; exr_status status; (void)type;
  if(!store) return NULL;
  status=host_publication(store,(int64_t)book,&publication,&error);
  if(status!=EXR_OK) { throw_status(env,status,&error,"Cannot read EPUB package"); return NULL; }
  parts=exr_publication_parts(publication,&count);
  if(count>INT_MAX) throw_argument(env,"Too many EPUB parts"); else rows=new_rows(env,(jsize)count);
  for(i=0;rows && i<count;i++) {
    jobjectArray row=new_row(env,3); if(!row) break;
    if(set_cell(env,row,0,parts[i].path) && set_number(env,row,1,parts[i].in_reading_order) && set_cell(env,row,2,parts[i].title))
      (*env)->SetObjectArrayElement(env,rows,(jsize)i,row);
    (*env)->DeleteLocalRef(env,row); if((*env)->ExceptionCheck(env)) break;
  }
  exr_publication_free(publication); return (*env)->ExceptionCheck(env)?NULL:rows;
}
static void host_epub_free(host_epub *reader) {
  if(reader) {
    exr_layout_free(reader->page); exr_pager_free(reader->pager); exr_publication_free(reader->publication);
    if(reader->source.release) reader->source.release(reader->source.context);
    if(!reader->borrowed_font) exr_font_free(reader->font); free(reader);
  }
}
JNIEXPORT jlong JNICALL Java_org_exreader_host_BoundedEpub_nativeOpen(JNIEnv *env,jclass type,jlong owner,jlong book,jint part,jbyteArray font,jfloat size,jfloat line,jfloat paragraph,jfloat margin,jlong budget,jboolean themed,jint foreground,jint background,jobject task) {
  host_epub *reader=NULL; exr_library *store=library(env,owner); exr_error error={0};
  exr_status status=EXR_OK; exr_layout_config config=exr_layout_config_defaults();
  exr_chapter_options options=exr_chapter_options_defaults(); exr_font_input input={0};
  host_control context; exr_control control=host_task_control(env,task,&context);
  jbyte *bytes=NULL; jsize length=font?(*env)->GetArrayLength(env,font):0; (void)type;
  char css[64];
  if(!store || (*env)->ExceptionCheck(env)) return 0;
  if(part<0 || size<4 || size>256 || length<=0 || length>64*1024*1024 || budget<1024*1024 || budget>8*1024*1024) { throw_argument(env,"Invalid chapter font/configuration"); return 0; }
  reader=calloc(1,sizeof(*reader)); if(!reader) { status=EXR_MEMORY; goto done; }
  reader->library=store; reader->book=(int64_t)book; reader->part=(size_t)part;
#ifdef READER_HOST_PAGE_THEME
  reader->themed=themed; reader->background=(uint32_t)background;
  if(themed) { snprintf(css,sizeof(css),"body { color: #%08x; }",(unsigned)(uint32_t)foreground); config.user_css=css; }
#else
  (void)themed;(void)foreground;(void)background;(void)css;
#endif
  status=exr_library_source(store,(int64_t)book,&reader->source,&error); if(status!=EXR_OK) goto done;
  {
    exr_source borrowed=reader->source; borrowed.release=NULL;
    status=exr_publication_open_source(&borrowed,&reader->publication,&error); if(status!=EXR_OK) goto done;
  }
  bytes=(*env)->GetByteArrayElements(env,font,NULL); if(!bytes) goto done;
  input.data=bytes; input.size=(size_t)length;
  status=exr_font_create(&input,1,&reader->font,&error); if(status!=EXR_OK) goto done;
  config.page.width=600; config.page.height=860; config.page.margin=margin; config.page.font_size=size;
  config.page.line_height=line; config.page.paragraph_spacing=paragraph; config.document_css=1; config.embedded_fonts=1;
  config.control=control; options.workspace_budget=(size_t)budget; options.window_bytes=64*1024;
  status=exr_publication_pager_create(reader->publication,(size_t)part,reader->font,&config,&options,&reader->pager,&error);
  if(status==EXR_OK) status=exr_pager_set_control(reader->pager,NULL,&error);
done:
  if(bytes) (*env)->ReleaseByteArrayElements(env,font,bytes,JNI_ABORT);
  if(status!=EXR_OK) throw_status(env,status,&error,"Cannot open bounded chapter");
  if(status!=EXR_OK || (*env)->ExceptionCheck(env)) { host_epub_free(reader); return 0; }
  return (jlong)(intptr_t)reader;
}
JNIEXPORT void JNICALL Java_org_exreader_host_BoundedEpub_nativeClose(JNIEnv *env,jclass type,jlong handle) {
  (void)env; (void)type; host_epub_free((host_epub *)(intptr_t)handle);
}
typedef struct { char *bytes; size_t size,capacity; } host_page_text;
static exr_status host_text_sink(void *context,const char *bytes,size_t size,exr_error *error) {
  host_page_text *text=context; size_t total=text->size+size; char *next; (void)error;
  if(total<text->size || total>512*1024) return EXR_LIMIT;
  if(total>text->capacity) {
    size_t capacity=total<32768?32768:total;
    next=realloc(text->bytes,capacity); if(!next) return EXR_MEMORY;
    text->bytes=next; text->capacity=capacity;
  }
  memcpy(text->bytes+text->size,bytes,size); text->size=total; return EXR_OK;
}
static jobject host_epub_frame(JNIEnv *env,jlong handle,jobject task,int advance,int render) {
  host_epub *reader=(host_epub *)(intptr_t)handle; exr_layout *layout=NULL; exr_bitmap bitmap={0};
  exr_error error={0}; exr_status status; host_page_text text={0};
  host_control context; exr_control control=host_task_control(env,task,&context);
  const exr_page *page; const exr_glyph *glyphs; const exr_line *lines; size_t pages,gc=0,lc=0,i,start,end,n;
  exr_chapter_stats stats; jlong meta[9],*spans=NULL; jfloat *geometry=NULL;
  jlongArray jm=NULL,js=NULL,jboxes=NULL; jfloatArray jg=NULL; jbyteArray jt=NULL,jp=NULL;
  jclass frame; jmethodID ctor; jobject result=NULL;
  if(!reader || (*env)->ExceptionCheck(env)) { if(!reader) throw_argument(env,"Bounded reader is closed"); return NULL; }
  if(reader->source.read_at) {
    unsigned char byte;
    if(reader->source.read_at(reader->source.context,0,&byte,1)!=1) {
      status=EXR_IO; strcpy(error.message,"Library source invalidated by external storage change"); goto done;
    }
  }
  status=exr_pager_set_control(reader->pager,&control,&error); if(status!=EXR_OK) goto done;
  if(advance) {
    reader->next_calls++;
    status=exr_pager_next(reader->pager,&layout,&error); if(status!=EXR_OK || !layout) goto done;
    exr_layout_free(reader->page); reader->page=layout;
  } else layout=reader->page;
  if(!layout) { status=EXR_ARGUMENT; goto done; }
  page=exr_layout_pages(layout,&pages); if(!page || pages!=1) { status=EXR_FORMAT; goto done; }
  glyphs=exr_layout_glyphs(layout,&gc); lines=exr_layout_lines(layout,&lc);
  stats=exr_pager_chapter_statistics(reader->pager); start=page->start; end=page->end;
  if(start==SIZE_MAX) start=0; if(end==SIZE_MAX) end=start;
  if(end<start || gc>200000 || lc>200000 || gc+lc>200000) { status=EXR_LIMIT; goto done; }
  if(render) {
#ifdef READER_HOST_PAGE_THEME
    if(reader->themed) status=exr_render_page_background(layout,exr_layout_font(layout),0,4,reader->background,&control,&bitmap,&error);
    else
#endif
    status=exr_render_page_color(layout,exr_layout_font(layout),0,&bitmap,&error);
    if(status!=EXR_OK) goto done;
    if(reader->document) {
      size_t length=0; const char *bytes=exr_document_text(reader->document,&length);
      if(start>length || end>length) { status=EXR_FORMAT; goto done; }
      status=host_text_sink(&text,bytes+start,end-start,&error);
    } else status=exr_pager_read_text(reader->pager,start,end,host_text_sink,&text,&control,&error);
    if(status!=EXR_OK) goto done;
  } else { gc=0; lc=0; }
  n=gc+lc; spans=calloc(n?n*2:1,sizeof(*spans)); geometry=calloc(n?n*4:1,sizeof(*geometry));
  if(!spans || !geometry || (uint64_t)bitmap.stride*bitmap.height>64*1024*1024) { status=EXR_LIMIT; goto done; }
  for(i=0;i<gc;i++) {
    spans[i*2]=(jlong)glyphs[i].start; spans[i*2+1]=(jlong)glyphs[i].end;
    geometry[i*4]=glyphs[i].x; geometry[i*4+1]=glyphs[i].baseline; geometry[i*4+2]=glyphs[i].advance; geometry[i*4+3]=glyphs[i].size;
  }
  for(i=0;i<lc;i++) {
    size_t at=gc+i; spans[at*2]=(jlong)lines[i].start; spans[at*2+1]=(jlong)lines[i].end;
    geometry[at*4]=lines[i].x; geometry[at*4+1]=lines[i].y; geometry[at*4+2]=lines[i].width; geometry[at*4+3]=lines[i].height;
  }
  meta[0]=(jlong)start; meta[1]=(jlong)end; meta[2]=bitmap.width; meta[3]=bitmap.height; meta[4]=bitmap.stride;
  meta[5]=(jlong)gc; meta[6]=(jlong)lc; meta[7]=(jlong)stats.peak_parse_workspace_bytes; meta[8]=(jlong)stats.projection_bytes;
  jm=(*env)->NewLongArray(env,9); js=(*env)->NewLongArray(env,(jsize)(n*2)); jg=(*env)->NewFloatArray(env,(jsize)(n*4));
  jt=(*env)->NewByteArray(env,(jsize)text.size); jp=(*env)->NewByteArray(env,(jsize)((size_t)bitmap.stride*bitmap.height));
  if(!jm || !js || !jg || !jt || !jp) goto done;
  (*env)->SetLongArrayRegion(env,jm,0,9,meta); (*env)->SetLongArrayRegion(env,js,0,(jsize)(n*2),spans);
  (*env)->SetFloatArrayRegion(env,jg,0,(jsize)(n*4),geometry);
  if(text.size) (*env)->SetByteArrayRegion(env,jt,0,(jsize)text.size,(const jbyte *)text.bytes);
  if(bitmap.pixels) (*env)->SetByteArrayRegion(env,jp,0,(jsize)((size_t)bitmap.stride*bitmap.height),(const jbyte *)bitmap.pixels);
  {
    size_t count=0;const exr_box *boxes=render&&reader->themed?exr_layout_boxes(layout,&count):NULL;
    if(count>200000){status=EXR_LIMIT;goto done;}
    jboxes=(*env)->NewLongArray(env,(jsize)(count*10));if(!jboxes)goto done;
    for(i=0;i<count;i++){
      const exr_box *box=boxes+i;uint32_t image_color=0;const exr_bitmap *image=box->kind==EXR_BOX_IMAGE?exr_layout_image(layout,box->resource):NULL;
      if(image&&image->channels==4&&image->width&&image->height){const unsigned char *pixel=image->pixels+(size_t)(image->height/2)*image->stride+(image->width/2)*4;image_color=(uint32_t)pixel[0]<<24|(uint32_t)pixel[1]<<16|(uint32_t)pixel[2]<<8|pixel[3];}
      jlong cells[10]={(jlong)box->kind,(jlong)box->resource,(jlong)box->background,(jlong)box->border_color,(jlong)(box->x*1000),(jlong)(box->y*1000),(jlong)(box->width*1000),(jlong)(box->height*1000),(jlong)image_color,(jlong)box->flags};
      (*env)->SetLongArrayRegion(env,jboxes,(jsize)(i*10),10,cells);
    }
  }
  if((*env)->ExceptionCheck(env)) goto done;
  frame=(*env)->FindClass(env,"org/exreader/host/BoundedEpub$Frame"); if(!frame) goto done;
  ctor=(*env)->GetMethodID(env,frame,"<init>","([J[J[F[B[BLjava/lang/String;[J)V"); if(!ctor) goto done;
  result=(*env)->NewObject(env,frame,ctor,jm,js,jg,jt,jp,output_string(env,exr_version()),jboxes);
done:
  exr_pager_set_control(reader->pager,NULL,NULL); exr_bitmap_free(&bitmap);
  free(text.bytes); free(spans); free(geometry);
  if(status!=EXR_OK) throw_status(env,status,&error,"Cannot read bounded page");
  return (*env)->ExceptionCheck(env)?NULL:result;
}
JNIEXPORT jobject JNICALL Java_org_exreader_host_BoundedEpub_nativeNext(JNIEnv *env,jclass type,jlong handle,jobject task,jboolean render) {
  (void)type; return host_epub_frame(env,handle,task,1,render!=0);
}
JNIEXPORT jobject JNICALL Java_org_exreader_host_BoundedEpub_nativeRender(JNIEnv *env,jclass type,jlong handle,jobject task) {
  (void)type; return host_epub_frame(env,handle,task,0,1);
}
JNIEXPORT jlong JNICALL Java_org_exreader_host_BoundedEpub_nativeCalls(JNIEnv *env,jclass type,jlong handle) {
  host_epub *reader=(host_epub *)(intptr_t)handle; (void)env; (void)type;
  return reader?(jlong)reader->next_calls:0;
}
JNIEXPORT jlong JNICALL Java_org_exreader_host_BoundedEpub_nativeExtent(JNIEnv *env,jclass type,jlong handle) {
  host_epub *reader=(host_epub *)(intptr_t)handle; (void)env; (void)type;
  return reader?(jlong)exr_pager_chapter_statistics(reader->pager).projection_bytes:0;
}
JNIEXPORT jobjectArray JNICALL Java_org_exreader_host_BoundedEpub_nativeProgress(JNIEnv *env,jclass type,jlong owner,jlong book) {
  exr_library *store=library(env,owner); exr_epub_location location={0}; int present=0; exr_error error={0};
  exr_status status; jobjectArray row=NULL; (void)type;
  if(!store) return NULL;
  status=exr_library_epub_progress_get(store,(int64_t)book,&location,&present,&error);
  if(status!=EXR_OK) throw_status(env,status,&error,"Cannot read chapter progress");
  else if(present) { row=new_row(env,8); if(row) location_cells(env,row,0,&location); }
  exr_epub_location_free(&location); return (*env)->ExceptionCheck(env)?NULL:row;
}
JNIEXPORT jlongArray JNICALL Java_org_exreader_host_BoundedEpub_nativeResolve(JNIEnv *env,jclass type,jlong handle,jobjectArray values,jlong budget_ms,jobject task) {
  host_epub *reader=(host_epub *)(intptr_t)handle; char *strings[8]={0}; size_t i,count=0;
  exr_anchor anchor={0}; exr_anchor_match match={0}; exr_error error={0}; exr_status status=EXR_OK;
  host_control context; exr_control control=host_task_control(env,task,&context);
  const exr_part *parts; jlong result[3]; jlongArray out=NULL; (void)type;
  if(!reader || !values || (*env)->GetArrayLength(env,values)!=8 || (*env)->ExceptionCheck(env)) { throw_argument(env,"Invalid chapter selector"); return NULL; }
  for(i=0;i<8;i++) { jstring value=(*env)->GetObjectArrayElement(env,values,(jsize)i); strings[i]=input_string(env,value); if(value) (*env)->DeleteLocalRef(env,value); if(!strings[i]) goto done; }
  parts=exr_publication_parts(reader->publication,&count);
  if(reader->part>=count || strcmp(strings[1],parts[reader->part].path) || strtoull(strings[0],NULL,10)!=reader->part) { status=EXR_ARGUMENT; goto done; }
  anchor.start=(size_t)strtoull(strings[2],NULL,10); anchor.end=(size_t)strtoull(strings[3],NULL,10);
  anchor.exact=strings[4]; anchor.prefix=strings[5]; anchor.suffix=strings[6]; anchor.chapter=strings[7];
  if(!anchor.chapter[0]) anchor.chapter=NULL;
  if(budget_ms>0) context.deadline_ns=host_now_ns()+(uint64_t)budget_ms*1000000u;
  status=exr_pager_anchor_resolve(reader->pager,&anchor,&control,&match,&error);
  if(status==EXR_CANCELLED && context.expired && !(*env)->ExceptionCheck(env)) {
    status=EXR_OK; result[0]=-2; result[1]=result[2]=-1;
  } else {
    if(status!=EXR_OK) goto done;
    result[0]=match.state; result[1]=match.start==SIZE_MAX?-1:(jlong)match.start; result[2]=match.end==SIZE_MAX?-1:(jlong)match.end;
  }
  out=(*env)->NewLongArray(env,3); if(out) (*env)->SetLongArrayRegion(env,out,0,3,result);
done:
  for(i=0;i<8;i++) free(strings[i]);
  if(status!=EXR_OK) throw_status(env,status,&error,"Cannot resolve chapter selector");
  return (*env)->ExceptionCheck(env)?NULL:out;
}
static exr_status host_location(host_epub *reader,jint part,jlong start,jlong end,exr_epub_location *location,exr_error *error) {
  const exr_part *parts; size_t count=0; exr_status status; unsigned char byte;
  if(!reader || part<0 || (size_t)part!=reader->part || start<0 || end<start || (uint64_t)end>=SIZE_MAX) return EXR_ARGUMENT;
  if(reader->source.read_at(reader->source.context,0,&byte,1)!=1) return EXR_IO;
  parts=exr_publication_parts(reader->publication,&count); if(reader->part>=count) return EXR_ARGUMENT;
  status=exr_pager_anchor_create(reader->pager,(size_t)start,(size_t)end,NULL,&location->selector,error);
  if(status!=EXR_OK) return status;
  location->part=reader->part; location->path=copy_string(parts[reader->part].path);
  if(!location->path) { exr_epub_location_free(location); return EXR_MEMORY; }
  return EXR_OK;
}
JNIEXPORT jobjectArray JNICALL Java_org_exreader_host_BoundedEpub_nativeCapture(JNIEnv *env,jclass type,jlong handle,jint part,jlong offset) {
  host_epub *reader=(host_epub *)(intptr_t)handle; exr_epub_location location={0}; exr_error error={0};
  exr_status status=host_location(reader,part,offset,offset,&location,&error); jobjectArray row=NULL; (void)type;
  if(status==EXR_OK) { row=new_row(env,8); if(row) location_cells(env,row,0,&location); }
  exr_epub_location_free(&location);
  if(status!=EXR_OK) throw_status(env,status,&error,"Cannot capture current chapter point");
  return (*env)->ExceptionCheck(env)?NULL:row;
}
JNIEXPORT void JNICALL Java_org_exreader_host_BoundedEpub_nativeSaveProgress(JNIEnv *env,jclass type,jlong handle,jlong owner,jlong book,jint part,jlong offset) {
  host_epub *reader=(host_epub *)(intptr_t)handle; exr_library *store=library(env,owner);
  exr_epub_location location={0}; exr_error error={0}; exr_status status; (void)type;
  if(!store) return;
  if(!reader || reader->library!=store || reader->book!=(int64_t)book) { throw_argument(env,"Chapter progress owner changed"); return; }
  status=host_location(reader,part,offset,offset,&location,&error);
  if(status==EXR_OK) status=exr_library_epub_progress(store,(int64_t)book,&location,&error);
  exr_epub_location_free(&location);
  if(status!=EXR_OK) throw_status(env,status,&error,"Cannot save chapter progress");
}
JNIEXPORT void JNICALL Java_org_exreader_host_BoundedEpub_nativeSaveNote(JNIEnv *env,jclass type,jlong handle,jlong owner,jlong book,jint part,jlong id,jlong start,jlong end,jstring comment) {
  host_epub *reader=(host_epub *)(intptr_t)handle; exr_library *store=library(env,owner); exr_epub_note note={0};
  exr_error error={0}; exr_status status=EXR_OK; int64_t saved=0; (void)type;
  if(!store || !reader || reader->library!=store || reader->book!=(int64_t)book) { throw_argument(env,"Chapter annotation owner changed"); return; }
  note.id=(int64_t)id; note.book_id=(int64_t)book; note.text=input_string(env,comment); if(!note.text) return;
  if(id==0) status=host_location(reader,part,start,end,&note.location,&error);
  if(status==EXR_OK) status=exr_library_epub_note(store,&note,&saved,&error);
  free(note.text); exr_epub_location_free(&note.location);
  if(status!=EXR_OK) throw_status(env,status,&error,"Cannot save chapter annotation");
}
