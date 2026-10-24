/* SPDX-License-Identifier: MIT
   Compiled into the same product provider only for the debug application.
   Instrumentation SQL never becomes a production owner endpoint. */
#include <cstdio>
#include <csignal>
#include <unistd.h>
namespace {
struct fixture {sqlite3 *db=nullptr;std::thread::id thread=std::this_thread::get_id();~fixture(){if(db)sqlite3_close_v2(db);}};
std::map<jlong,std::unique_ptr<fixture>> fixtures;
std::mutex fixture_mutex;jlong fixture_sequence=0;
thread_local bool interrupt_migration=false;
thread_local std::string kill_witness;
void kill_sql(sqlite3_context *context,int,sqlite3_value **){
  sqlite3 *db=sqlite3_context_db_handle(context);sqlite3_stmt *statement=nullptr;
  int status=sqlite3_prepare_v2(db,"SELECT (SELECT count(*) FROM reader_revisions),(SELECT count(*) FROM reader_outbox),(SELECT count(*) FROM reader_tags)",-1,&statement,nullptr);
  FILE *output=std::fopen(kill_witness.c_str(),"wb");
  if(output){if(status==SQLITE_OK&&sqlite3_step(statement)==SQLITE_ROW)std::fprintf(output,"%d,%d,%d",sqlite3_column_int(statement,0),sqlite3_column_int(statement,1),sqlite3_column_int(statement,2));std::fclose(output);}
  sqlite3_finalize(statement);::kill(::getpid(),SIGKILL);
}
int kill_extension(sqlite3 *db,char **,const sqlite3_api_routines *){
  return sqlite3_create_function_v2(db,"reader_test_kill",0,SQLITE_UTF8|SQLITE_INNOCUOUS,nullptr,kill_sql,nullptr,nullptr,nullptr);
}
int migration_authorizer(void *,int action,const char *table,const char *,const char *,const char *){
  if(interrupt_migration&&action==SQLITE_CREATE_TABLE&&table&&std::string(table)=="reader_book_shelves"){
    interrupt_migration=false;return SQLITE_DENY;
  }return SQLITE_OK;
}
int migration_extension(sqlite3 *db,char **,const sqlite3_api_routines *){
  return sqlite3_set_authorizer(db,migration_authorizer,nullptr);
}
fixture &get_fixture(jlong id){auto found=fixtures.find(id);
  if(found==fixtures.end()||found->second->thread!=std::this_thread::get_id())reject("java/lang/IllegalStateException","Fixture owner is closed or incorrect");
  return *found->second;
}
struct fixture_statement {sqlite3_stmt *s=nullptr;~fixture_statement(){sqlite3_finalize(s);}};
void fixture_bind(JNIEnv *env,sqlite3_stmt *s,jobjectArray args){
  if(!args)return;
  if(env->GetArrayLength(args)!=sqlite3_bind_parameter_count(s))reject("java/lang/IllegalArgumentException","Fixture binding count differs");
  jclass number=env->FindClass("java/lang/Number");pending(env);
  jmethodID numeric=env->GetMethodID(number,"longValue","()J");pending(env);
  for(jsize i=0;i<env->GetArrayLength(args);++i){jobject arg=env->GetObjectArrayElement(args,i);pending(env);int status;
    if(!arg)status=sqlite3_bind_null(s,i+1);
    else if(env->IsInstanceOf(arg,number)){jlong value=env->CallLongMethod(arg,numeric);pending(env);status=sqlite3_bind_int64(s,i+1,value);}
    else {std::string value=utf8(env,(jstring)arg);status=sqlite3_bind_text64(s,i+1,value.data(),value.size(),SQLITE_TRANSIENT,SQLITE_UTF8);}
    if(arg)env->DeleteLocalRef(arg);database(status,"Fixture binding failed");
  }env->DeleteLocalRef(number);
}
}
#define FIXTURE_METHOD(name) Java_org_exreader_host_ProductFixture_##name
extern "C" JNIEXPORT void JNICALL FIXTURE_METHOD(failNextMigration)(JNIEnv *env,jclass){
  try{database(sqlite3_auto_extension((void(*)(void))migration_extension),"Cannot install migration interruption");interrupt_migration=true;}
  catch(const failure &e){report(env,e);}
}
extern "C" JNIEXPORT void JNICALL FIXTURE_METHOD(installKill)(JNIEnv *env,jclass,jstring path){
  try{kill_witness=utf8(env,path);database(sqlite3_auto_extension((void(*)(void))kill_extension),"Cannot install killed-process boundary");}
  catch(const failure &e){report(env,e);}
}
extern "C" JNIEXPORT jlong JNICALL FIXTURE_METHOD(openNative)(JNIEnv *env,jclass,jstring path){
  try{auto value=std::make_unique<fixture>();std::string p=utf8(env,path);
    database(sqlite3_open_v2(p.c_str(),&value->db,SQLITE_OPEN_READWRITE|SQLITE_OPEN_CREATE|SQLITE_OPEN_FULLMUTEX,nullptr),"Cannot open native product fixture");
    database(sqlite3_exec(value->db,"PRAGMA foreign_keys=ON; PRAGMA trusted_schema=OFF; PRAGMA busy_timeout=5000;",nullptr,nullptr,nullptr),"Cannot configure fixture");
    std::lock_guard<std::mutex> lock(fixture_mutex);jlong id=++fixture_sequence;fixtures.emplace(id,std::move(value));return id;
  }catch(const failure &e){report(env,e);}catch(...){report(env,{"java/lang/OutOfMemoryError","Fixture allocation failed"});}return 0;
}
extern "C" JNIEXPORT void JNICALL FIXTURE_METHOD(closeNative)(JNIEnv *env,jclass,jlong id){
  try{std::lock_guard<std::mutex> lock(fixture_mutex);get_fixture(id);fixtures.erase(id);}
  catch(const failure &e){report(env,e);}
}
extern "C" JNIEXPORT void JNICALL FIXTURE_METHOD(execNative)(JNIEnv *env,jclass,jlong id,jstring sql,jobjectArray args){
  try{std::lock_guard<std::mutex> lock(fixture_mutex);auto &f=get_fixture(id);std::string query=utf8(env,sql);fixture_statement statement;
    database(sqlite3_prepare_v2(f.db,query.c_str(),-1,&statement.s,nullptr),sqlite3_errmsg(f.db));fixture_bind(env,statement.s,args);
    int status=sqlite3_step(statement.s);database(status==SQLITE_DONE?0:status,sqlite3_errmsg(f.db));
  }catch(const failure &e){report(env,e);}catch(...){report(env,{"java/lang/OutOfMemoryError","Fixture execution allocation failed"});}
}
extern "C" JNIEXPORT jobjectArray JNICALL FIXTURE_METHOD(queryNative)(JNIEnv *env,jclass,jlong id,jstring sql,jobjectArray args){
  try{std::lock_guard<std::mutex> lock(fixture_mutex);auto &f=get_fixture(id);std::string query=utf8(env,sql);fixture_statement statement;
    database(sqlite3_prepare_v2(f.db,query.c_str(),-1,&statement.s,nullptr),sqlite3_errmsg(f.db));fixture_bind(env,statement.s,args);
    int columns=sqlite3_column_count(statement.s);std::vector<std::vector<std::string>> values(1);
    for(int i=0;i<columns;++i)values[0].emplace_back(sqlite3_column_name(statement.s,i));
    int status;
    while((status=sqlite3_step(statement.s))==SQLITE_ROW){
      if(values.size()>5000)reject("java/lang/IllegalStateException","Fixture query bound exceeded");
      values.emplace_back();for(int i=0;i<columns;++i){const char *text=(const char *)sqlite3_column_text(statement.s,i);values.back().emplace_back(text?text:"");}
    }database(status==SQLITE_DONE?0:status,sqlite3_errmsg(f.db));
    jclass array=env->FindClass("[Ljava/lang/String;");pending(env);jobjectArray result=env->NewObjectArray((jsize)values.size(),array,nullptr);env->DeleteLocalRef(array);pending(env);
    for(size_t i=0;i<values.size();++i){jobject row=strings(env,values[i]);env->SetObjectArrayElement(result,(jsize)i,row);env->DeleteLocalRef(row);pending(env);}return result;
  }catch(const failure &e){report(env,e);}catch(...){report(env,{"java/lang/OutOfMemoryError","Fixture query allocation failed"});}return nullptr;
}
