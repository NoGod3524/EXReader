/* SPDX-License-Identifier: MIT */
/* App-owned public SDK objects. No binding handles or private SDK structures. */
typedef struct { exr_document *document; exr_font *font; } host_theme_document;
JNIEXPORT jlong JNICALL Java_org_exreader_host_ThemeReflow_nativeOpen(JNIEnv *env,jclass type,jstring path,jbyteArray font) {
  host_theme_document *owner=calloc(1,sizeof(*owner)); exr_error error={0}; exr_status status=EXR_MEMORY;
  char *file=input_string(env,path); (void)type;
  if(owner && file) { status=exr_document_open(file,&owner->document,&error); if(status==EXR_OK) status=host_font_bytes(env,font,&owner->font,&error); }
  free(file);
  if(status!=EXR_OK || (*env)->ExceptionCheck(env)) { if(owner){exr_document_free(owner->document);exr_font_free(owner->font);free(owner);}throw_status(env,status,&error,"Cannot open theme document");return 0; }
  return (jlong)(intptr_t)owner;
}
JNIEXPORT jbyteArray JNICALL Java_org_exreader_host_ThemeReflow_nativeText(JNIEnv *env,jclass type,jlong handle) {
  host_theme_document *owner=(host_theme_document *)(intptr_t)handle;size_t size=0;const char *text=exr_document_text(owner->document,&size);(void)type;
  if(size>32*1024*1024){throw_argument(env,"Reflow text exceeds host budget");return NULL;}
  jbyteArray result=(*env)->NewByteArray(env,(jsize)size);if(result && size)(*env)->SetByteArrayRegion(env,result,0,(jsize)size,(const jbyte *)text);return result;
}
JNIEXPORT jstring JNICALL Java_org_exreader_host_ThemeReflow_nativeTitle(JNIEnv *env,jclass type,jlong handle) {
  host_theme_document *owner=(host_theme_document *)(intptr_t)handle;(void)type;return output_string(env,exr_document_title(owner->document));
}
JNIEXPORT jlong JNICALL Java_org_exreader_host_ThemeReflow_nativePager(JNIEnv *env,jclass type,jlong handle,jfloat size,jfloat line,jfloat paragraph,jfloat margin,jint foreground,jint background,jobject task) {
  host_theme_document *owner=(host_theme_document *)(intptr_t)handle;host_epub *reader=calloc(1,sizeof(*reader));
  exr_error error={0};exr_status status=EXR_MEMORY;exr_layout_config config=exr_layout_config_defaults();
  host_control context;exr_control control=host_task_control(env,task,&context);char css[64];(void)type;
  if(reader){
    reader->document=owner->document;reader->font=owner->font;reader->borrowed_font=1;reader->themed=1;reader->background=(uint32_t)background;
    /* Plain text has paragraph model nodes and no HTML body element. */
    snprintf(css,sizeof(css),"%s { color: #%08x; }",exr_document_format(owner->document)==EXR_TXT?"*":"body",(unsigned)(uint32_t)foreground);
    config.page=(exr_layout_options){600,860,margin,size,line,paragraph};config.document_css=1;config.embedded_fonts=1;config.user_css=css;config.control=control;
    status=exr_pager_create(owner->document,owner->font,&config,&reader->pager,&error);
    if(status==EXR_OK)status=exr_pager_set_control(reader->pager,NULL,&error);
  }
  if(status!=EXR_OK || (*env)->ExceptionCheck(env)){host_epub_free(reader);throw_status(env,status,&error,"Cannot create theme pager");return 0;}
  return (jlong)(intptr_t)reader;
}
JNIEXPORT jobject JNICALL Java_org_exreader_host_ThemeReflow_nativeFrame(JNIEnv *env,jclass type,jlong handle,jobject task,jboolean advance,jboolean render){(void)type;return host_epub_frame(env,handle,task,advance,render);}
JNIEXPORT void JNICALL Java_org_exreader_host_ThemeReflow_nativeClosePager(JNIEnv *env,jclass type,jlong handle){(void)env;(void)type;host_epub_free((host_epub *)(intptr_t)handle);}
JNIEXPORT void JNICALL Java_org_exreader_host_ThemeReflow_nativeClose(JNIEnv *env,jclass type,jlong handle){host_theme_document *owner=(host_theme_document *)(intptr_t)handle;(void)env;(void)type;if(owner){exr_document_free(owner->document);exr_font_free(owner->font);free(owner);}}
