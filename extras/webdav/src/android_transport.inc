/* SPDX-License-Identifier: MIT */
/* Included only by the Android platform branch of webdav.cpp. */
JavaVM *android_vm=nullptr;
jclass android_type=nullptr;
struct android_methods {
  jmethodID create=nullptr,execute=nullptr,status=nullptr,headers=nullptr,read=nullptr,close_exchange=nullptr,
    close_client=nullptr,error=nullptr,parser=nullptr,next=nullptr,event=nullptr;
} android_java;
std::mutex android_mutex;
std::set<exr_webdav_client *> android_clients;
uint64_t android_attached=0,android_detached=0;

void android_check(JNIEnv *env,exr_webdav_status fallback,const char *message){
  if(!env->ExceptionCheck())return;
  jthrowable error=env->ExceptionOccurred();env->ExceptionClear();
  jint code=env->CallStaticIntMethod(android_type,android_java.error,error,(jint)fallback);
  if(env->ExceptionCheck()){env->ExceptionClear();code=fallback;}
  env->DeleteLocalRef(error);
  reject(code>EXR_DAV_OK&&code<=EXR_DAV_EXISTS?(exr_webdav_status)code:fallback,message);
}
struct android_frame {
  JNIEnv *env=nullptr;JavaVM *vm=nullptr;bool attached=false,pushed=false;
  android_frame(){
    {std::lock_guard<std::mutex> lock(android_mutex);vm=android_type?android_vm:nullptr;}
    if(!vm)reject(EXR_DAV_IO,"Android WebDAV support is not initialized");
    jint status=vm->GetEnv((void **)&env,JNI_VERSION_1_6);
    if(status==JNI_EDETACHED){
      if(vm->AttachCurrentThread(&env,nullptr)!=JNI_OK)reject(EXR_DAV_IO,"Cannot attach Android transport worker");
      attached=true;std::lock_guard<std::mutex> lock(android_mutex);android_attached++;
    }else if(status!=JNI_OK)reject(EXR_DAV_IO,"Android transport VM is unavailable");
    if(env->PushLocalFrame(64)!=JNI_OK){
      if(env->ExceptionCheck())env->ExceptionClear();
      if(attached){vm->DetachCurrentThread();std::lock_guard<std::mutex> lock(android_mutex);android_detached++;}
      reject(EXR_DAV_MEMORY,"Cannot allocate Android JNI frame");
    }pushed=true;
  }
  ~android_frame(){
    if(env&&env->ExceptionCheck())env->ExceptionClear();
    if(pushed)env->PopLocalFrame(nullptr);
    if(attached){vm->DetachCurrentThread();std::lock_guard<std::mutex> lock(android_mutex);android_detached++;}
  }
};
std::string android_text(JNIEnv *env,jstring value){
  if(!value)return {};
  jsize length=env->GetStringLength(value);if(length>65536)reject(EXR_DAV_LIMIT,"Android response text exceeds its bound");
  const jchar *units=env->GetStringChars(value,nullptr);android_check(env,EXR_DAV_MEMORY,"Cannot copy Android response text");
  std::string out;
  try{
    for(jsize i=0;i<length;i++){
      uint32_t scalar=units[i];
      if(scalar>=0xd800&&scalar<=0xdbff){
        if(i+1==length||units[i+1]<0xdc00||units[i+1]>0xdfff)reject(EXR_DAV_FORMAT,"Invalid Android UTF-16 response text");
        scalar=0x10000+((scalar-0xd800)<<10)+(units[++i]-0xdc00);
      }else if(scalar>=0xdc00&&scalar<=0xdfff)reject(EXR_DAV_FORMAT,"Invalid Android UTF-16 response text");
      if(scalar<0x80)out+=(char)scalar;
      else if(scalar<0x800){out+=(char)(0xc0|(scalar>>6));out+=(char)(0x80|(scalar&63));}
      else if(scalar<0x10000){out+=(char)(0xe0|(scalar>>12));out+=(char)(0x80|((scalar>>6)&63));out+=(char)(0x80|(scalar&63));}
      else{out+=(char)(0xf0|(scalar>>18));out+=(char)(0x80|((scalar>>12)&63));out+=(char)(0x80|((scalar>>6)&63));out+=(char)(0x80|(scalar&63));}
      if(out.size()>65536)reject(EXR_DAV_LIMIT,"Android response text exceeds its bound");
    }
  }catch(...){env->ReleaseStringChars(value,units);throw;}
  env->ReleaseStringChars(value,units);return out;
}
std::vector<std::string> android_strings(JNIEnv *env,jobjectArray values){
  if(!values)reject(EXR_DAV_IO,"Missing Android response fields");
  std::vector<std::string> out;jsize count=env->GetArrayLength(values);
  if(count>32768)reject(EXR_DAV_LIMIT,"Too many Android response fields");
  for(jsize i=0;i<count;i++){
    jstring value=(jstring)env->GetObjectArrayElement(values,i);android_check(env,EXR_DAV_MEMORY,"Cannot copy Android response field");
    try{out.push_back(android_text(env,value));}catch(...){if(value)env->DeleteLocalRef(value);throw;}
    if(value)env->DeleteLocalRef(value);
  }return out;
}
struct android_operation {
  exr_webdav_client *client;
  explicit android_operation(exr_webdav_client *c):client(c){
    std::lock_guard<std::mutex> lock(android_mutex);
    if(!android_clients.count(c)||c->android_owner!=std::this_thread::get_id()||c->android_active)
      reject(EXR_DAV_ARGUMENT,"Android DAV calls require the creating worker without reentry");
    c->android_active=true;
  }
  ~android_operation(){std::lock_guard<std::mutex> lock(android_mutex);client->android_active=false;}
};
void android_create(exr_webdav_client *client){
  android_frame frame;JNIEnv *env=frame.env;
  jobject local=env->CallStaticObjectMethod(android_type,android_java.create);android_check(env,EXR_DAV_IO,"Cannot create Android transport client");
  if(!local)reject(EXR_DAV_IO,"Android transport client is unavailable");
  try{
    client->android_backend=env->NewGlobalRef(local);android_check(env,EXR_DAV_MEMORY,"Cannot retain Android transport client");
    if(!client->android_backend)reject(EXR_DAV_MEMORY,"Cannot retain Android transport client");
    std::lock_guard<std::mutex> lock(android_mutex);android_clients.insert(client);
  }
  catch(...){env->CallStaticVoidMethod(android_type,android_java.close_client,local);if(env->ExceptionCheck())env->ExceptionClear();env->DeleteGlobalRef(client->android_backend);client->android_backend=nullptr;throw;}
}
bool android_release(exr_webdav_client *client){
  if(!client)return false;
  {std::lock_guard<std::mutex> lock(android_mutex);
    if(!android_clients.count(client)||client->android_owner!=std::this_thread::get_id()||client->android_active)return false;}
  try{
    android_frame frame;frame.env->CallStaticVoidMethod(android_type,android_java.close_client,client->android_backend);
    if(frame.env->ExceptionCheck())frame.env->ExceptionClear();
    frame.env->DeleteGlobalRef(client->android_backend);client->android_backend=nullptr;
  }catch(...){return false;}
  std::lock_guard<std::mutex> lock(android_mutex);android_clients.erase(client);return true;
}
struct android_upload {
  upload *input;std::thread::id owner=std::this_thread::get_id();failure error{EXR_DAV_OK,"",0};
  explicit android_upload(upload *source):input(source){}
};
std::map<jlong,android_upload *> android_uploads;
jlong android_sequence=0;
struct android_upload_token {
  jlong value;android_upload context;
  explicit android_upload_token(upload *input):value(0),context(input){
    if(input){
      std::lock_guard<std::mutex> lock(android_mutex);
      if(android_sequence==std::numeric_limits<jlong>::max())reject(EXR_DAV_LIMIT,"Android upload context budget exhausted");
      value=++android_sequence;android_uploads.emplace(value,&context);
    }
  }
  ~android_upload_token(){if(value){std::lock_guard<std::mutex> lock(android_mutex);android_uploads.erase(value);}}
};
jint android_read_upload(JNIEnv *env,jclass,jlong token,jbyteArray bytes){
  android_upload *context=nullptr;
  {std::lock_guard<std::mutex> lock(android_mutex);auto found=android_uploads.find(token);if(found!=android_uploads.end()&&found->second->owner==std::this_thread::get_id())context=found->second;}
  if(!context){jclass error=env->FindClass("java/io/IOException");if(error)env->ThrowNew(error,"Expired Android upload context");return -1;}
  try{
    if(!bytes||env->GetArrayLength(bytes)<1)reject(EXR_DAV_ARGUMENT,"Missing Android upload buffer");
    unsigned char buffer[65536];size_t count=context->input->read(buffer,std::min<size_t>(sizeof(buffer),(size_t)env->GetArrayLength(bytes)));
    env->SetByteArrayRegion(bytes,0,(jsize)count,(jbyte *)buffer);
    if(env->ExceptionCheck()){context->error={EXR_DAV_MEMORY,"Cannot copy Android upload bytes",0};return -1;}return (jint)count;
  }catch(const failure &f){context->error=f;}catch(...){context->error={EXR_DAV_MEMORY,"Cannot read Android upload source",0};}
  jclass error=env->FindClass("java/io/IOException");if(error)env->ThrowNew(error,"Native upload source refused");return -1;
}
exr_webdav_status android_initialize(JNIEnv *env){
  if(!env)return EXR_DAV_ARGUMENT;
  std::lock_guard<std::mutex> lock(android_mutex);if(android_type)return EXR_DAV_OK;
  jclass local=env->FindClass("org/exreader/webdav/Transport");
  if(!local){env->ExceptionClear();return EXR_DAV_IO;}
  android_methods methods;
  auto lookup=[&](const char *name,const char *signature){return env->ExceptionCheck()?nullptr:env->GetStaticMethodID(local,name,signature);};
  methods.create=lookup("createClient","()Ljava/lang/Object;");
  methods.execute=lookup("execute","(Ljava/lang/Object;Ljava/lang/String;Ljava/lang/String;Ljava/lang/String;IJJ)Ljava/lang/Object;");
  methods.status=lookup("status","(Ljava/lang/Object;)I");
  methods.headers=lookup("headers","(Ljava/lang/Object;)[Ljava/lang/String;");
  methods.read=lookup("read","(Ljava/lang/Object;[B)I");
  methods.close_exchange=lookup("closeExchange","(Ljava/lang/Object;)V");
  methods.close_client=lookup("closeClient","(Ljava/lang/Object;)V");
  methods.error=lookup("errorCode","(Ljava/lang/Throwable;I)I");
  methods.parser=lookup("parser","([B)Ljava/lang/Object;");
  methods.next=lookup("next","(Ljava/lang/Object;)I");
  methods.event=lookup("event","(Ljava/lang/Object;)[Ljava/lang/String;");
  bool complete=methods.create&&methods.execute&&methods.status&&methods.headers&&methods.read&&methods.close_exchange&&methods.close_client&&methods.error&&methods.parser&&methods.next&&methods.event;
  if(!complete||env->ExceptionCheck()){env->ExceptionClear();env->DeleteLocalRef(local);return EXR_DAV_IO;}
  JNINativeMethod callback{const_cast<char *>("readUpload"),const_cast<char *>("(J[B)I"),reinterpret_cast<void *>(android_read_upload)};
  if(env->RegisterNatives(local,&callback,1)!=JNI_OK||env->GetJavaVM(&android_vm)!=JNI_OK){env->ExceptionClear();env->DeleteLocalRef(local);return EXR_DAV_IO;}
  android_type=(jclass)env->NewGlobalRef(local);env->DeleteLocalRef(local);
  if(!android_type||env->ExceptionCheck()){env->ExceptionClear();android_type=nullptr;return EXR_DAV_MEMORY;}
  android_java=methods;return EXR_DAV_OK;
}
response perform(exr_webdav_client &client,const url &u,const char *method,int expected,sink &output,clock_type::time_point deadline,upload *input=nullptr){
  android_frame frame;JNIEnv *env=frame.env;android_upload_token token(input);
  jobject exchange=nullptr;
  struct close_response {
    JNIEnv *env;jobject &exchange;
    ~close_response(){if(exchange){env->CallStaticVoidMethod(android_type,android_java.close_exchange,exchange);if(env->ExceptionCheck())env->ExceptionClear();}}
  } cleanup{env,exchange};
  cancelled(output.control);jstring target=env->NewStringUTF(full(u).c_str()),verb=env->NewStringUTF(method),authorization=env->NewStringUTF(client.authorization.c_str());
  android_check(env,EXR_DAV_MEMORY,"Cannot copy Android request arguments");
  exchange=env->CallStaticObjectMethod(android_type,android_java.execute,client.android_backend,target,verb,authorization,(jint)remaining(deadline),token.value,(jlong)(input?input->length:0));
  if(token.context.error.code!=EXR_DAV_OK){if(env->ExceptionCheck())env->ExceptionClear();throw token.context.error;}
  if(stop(output.control)){if(env->ExceptionCheck())env->ExceptionClear();cancelled(output.control);}
  android_check(env,EXR_DAV_IO,"Android HTTPS request failed");if(!exchange)reject(EXR_DAV_IO,"Missing Android HTTPS response");
  response result;result.status=env->CallStaticIntMethod(android_type,android_java.status,exchange);android_check(env,EXR_DAV_IO,"Missing Android HTTPS status");
  auto fields=(jobjectArray)env->CallStaticObjectMethod(android_type,android_java.headers,exchange);android_check(env,EXR_DAV_FORMAT,"Invalid Android HTTPS response headers");
  auto headers=android_strings(env,fields);if(headers.size()%2)reject(EXR_DAV_FORMAT,"Incomplete Android HTTPS response headers");
  for(size_t i=0;i<headers.size();i+=2){
    std::string name=headers[i],value=trim(headers[i+1]);for(char &ch:name)ch=(char)std::tolower((unsigned char)ch);
    if(name=="location"){if(value.size()>8192||!result.location.empty())reject(EXR_DAV_FORMAT,"Invalid redirect header");result.location=value;}
    if(name=="content-length"){uint64_t length=number(value);if(result.has_length&&length!=result.length)reject(EXR_DAV_FORMAT,"Conflicting byte lengths");result.length=length;result.has_length=true;}
  }
  head(result,expected,output);if(redirect(result.status))return result;
  jbyteArray bytes=env->NewByteArray(65536);android_check(env,EXR_DAV_MEMORY,"Cannot allocate Android response buffer");unsigned char copied[65536];
  for(;;){
    cancelled(output.control);remaining(deadline);jint got=env->CallStaticIntMethod(android_type,android_java.read,exchange,bytes);
    if(stop(output.control)){if(env->ExceptionCheck())env->ExceptionClear();cancelled(output.control);}
    android_check(env,EXR_DAV_IO,"Android HTTPS body read failed");if(got==-1)break;if(got<=0||got>65536)reject(EXR_DAV_IO,"Invalid Android HTTPS body read");
    env->GetByteArrayRegion(bytes,0,got,(jbyte *)copied);android_check(env,EXR_DAV_MEMORY,"Cannot copy Android HTTPS body");output.append(copied,(size_t)got);
  }
  if(result.has_length&&result.length!=output.received)reject(EXR_DAV_IO,"Incomplete HTTPS response body");
  remaining(deadline);return result;
}
template<class Event>void android_xml(const std::vector<unsigned char> &bytes,Event event){
  android_frame frame;JNIEnv *env=frame.env;jbyteArray input=env->NewByteArray((jsize)bytes.size());android_check(env,EXR_DAV_MEMORY,"Cannot copy bounded XML input");
  env->SetByteArrayRegion(input,0,(jsize)bytes.size(),(const jbyte *)bytes.data());android_check(env,EXR_DAV_MEMORY,"Cannot copy bounded XML input");
  jobject parser=env->CallStaticObjectMethod(android_type,android_java.parser,input);android_check(env,EXR_DAV_FORMAT,"Cannot create safe Android XML reader");
  if(!parser)reject(EXR_DAV_FORMAT,"Missing Android XML reader");
  for(;;){jint kind=env->CallStaticIntMethod(android_type,android_java.next,parser);android_check(env,EXR_DAV_FORMAT,"Malformed WebDAV XML");if(!kind)break;
    auto values=(jobjectArray)env->CallStaticObjectMethod(android_type,android_java.event,parser);android_check(env,EXR_DAV_FORMAT,"Invalid WebDAV XML event");
    auto text=android_strings(env,values);env->DeleteLocalRef(values);if(text.size()!=3||kind<1||kind>3)reject(EXR_DAV_FORMAT,"Invalid WebDAV XML event");
    event(kind,text[0],text[1],text[2],false);
  }
}
#ifdef EXR_WEBDAV_ANDROID_TESTING
extern "C" void exr_webdav_android_test_stats(uint64_t out[4]){
  std::lock_guard<std::mutex> lock(android_mutex);out[0]=android_clients.size();out[1]=android_uploads.size();out[2]=android_attached;out[3]=android_detached;
}
#endif
