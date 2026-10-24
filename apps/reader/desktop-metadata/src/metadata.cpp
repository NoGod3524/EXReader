/* SPDX-License-Identifier: MIT */
#include "reader_metadata.h"
#include <catalog.h>
#include <algorithm>
#include <cerrno>
#include <cstdio>
#include <cstring>
#include <exception>
#include <filesystem>
#include <memory>
#include <string>
#include <thread>
#include <vector>
#ifdef _WIN32
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#else
#include <fcntl.h>
#include <sys/file.h>
#include <sys/stat.h>
#include <unistd.h>
#endif

namespace fs=std::filesystem;
struct reader_metadata_snapshot {
  reader_metadata_entity entity=READER_METADATA_BOOK;
  reader_group_kind kind=READER_GROUP_SHELF;
  reader_command_operation operation=READER_COMMAND_PUT;
  std::string database,key,revision_id,book_key,group_id,name,parent,format,sha,title,author,sort;
  uint64_t source_bytes=0,ordinal=0;
  int favorite=0,present=0,deleted=0,needs_bootstrap=0,dependency_deleted=0;
  reader_revision_state graph{};
  std::vector<std::string> heads;
  std::vector<const char *> head_pointers;
  reader_metadata_view view{};
};
struct reader_metadata_owner {
  std::thread::id thread=std::this_thread::get_id();
  bool active=false;
  std::string database;
  fs::path pending;
  reader_catalog *catalog=nullptr;
  reader_revisions *revisions=nullptr;
#ifdef _WIN32
  HANDLE lock=INVALID_HANDLE_VALUE;
#else
  int lock=-1;
#endif
  ~reader_metadata_owner(){
    reader_revisions_close(&revisions,nullptr);reader_catalog_close(&catalog,nullptr);
#ifdef _WIN32
    if(lock!=INVALID_HANDLE_VALUE)CloseHandle(lock);
#else
    if(lock>=0)close(lock);
#endif
  }
};
namespace {
struct failure {reader_metadata_status code;const char *message;reader_command_error command{};};
[[noreturn]] void reject(reader_metadata_status code,const char *message){throw failure{code,message,{}};}
struct guard {
  reader_metadata_owner *owner;
  explicit guard(reader_metadata_owner *value):owner(value){
    if(!owner||owner->thread!=std::this_thread::get_id()||owner->active)
      reject(READER_METADATA_OWNER,"Metadata requires its creating worker without reentry");
    owner->active=true;
  }
  ~guard(){owner->active=false;}
};
std::string text(const char *value,size_t maximum,bool empty=false){
  if(!value){if(empty)return {};reject(READER_METADATA_ARGUMENT,"Missing typed metadata text");}
  size_t n=0;while(n<=maximum&&value[n])++n;
  if(n>maximum||(!empty&&!n))reject(READER_METADATA_ARGUMENT,"Typed metadata text exceeds its bound or is empty");
  return std::string(value,n);
}
bool id(const std::string &value){return value.size()==32&&value.find_first_not_of("0123456789abcdef")==std::string::npos;}
const char *kind_name(reader_group_kind kind){
  switch(kind){case READER_GROUP_SHELF:return "shelf";case READER_GROUP_TAG:return "tag";case READER_GROUP_SERIES:return "series";}
  reject(READER_METADATA_ARGUMENT,"Unknown metadata group kind");
}
const char *entity_name(const reader_metadata_snapshot &value){
  return value.entity==READER_METADATA_BOOK?"book":value.entity==READER_METADATA_MEMBERSHIP?"membership":kind_name(value.kind);
}
void revision_check(reader_revision_status status,const reader_revision_error &error){
  if(status!=READER_REV_OK){reader_command_error command{};command.code=READER_COMMAND_REVISION;command.revision=error;
    throw failure{status==READER_REV_UNSAFE?READER_METADATA_CONFLICT:READER_METADATA_REVISION,"Native revision operation was refused",command};}
}
void catalog_check(int status,const reader_catalog_error &error){
  if(status){(void)error;reject(READER_METADATA_REVISION,"Native catalog query was refused");}
}
template<class Function>reader_metadata_status call(reader_metadata_error *error,Function function){
  if(error)std::memset(error,0,sizeof(*error));
  try{reader_metadata_status status=function();if(error)error->code=status;return status;}
  catch(const failure &failed){if(error){error->code=failed.code;error->command=failed.command;std::snprintf(error->message,sizeof(error->message),"%s",failed.message);}return failed.code;}
  catch(const fs::filesystem_error &){if(error){error->code=READER_METADATA_IO;std::snprintf(error->message,sizeof(error->message),"Metadata profile file operation failed");}return READER_METADATA_IO;}
  catch(...){if(error){error->code=READER_METADATA_REVISION;std::snprintf(error->message,sizeof(error->message),"Cannot allocate bounded metadata intent");}return READER_METADATA_REVISION;}
}
void result_identity(const reader_metadata_snapshot &value,reader_metadata_result *out){
  if(!out)reject(READER_METADATA_ARGUMENT,"Missing metadata command result");
  std::snprintf(out->command.entity_key,sizeof(out->command.entity_key),"%s",value.key.c_str());
  std::snprintf(out->command.revision_id,sizeof(out->command.revision_id),"%s",value.revision_id.c_str());out->pending=1;
}
uint32_t checksum(const std::vector<unsigned char> &bytes,size_t count){
  uint32_t crc=0xffffffffu;
  for(size_t i=0;i<count;++i){crc^=bytes[i];for(int bit=0;bit<8;++bit)crc=(crc>>1)^((crc&1)?0xedb88320u:0u);}
  return ~crc;
}
void number(std::vector<unsigned char> &bytes,uint64_t value){for(int n=7;n>=0;--n)bytes.push_back((unsigned char)(value>>(n*8)));}
void string(std::vector<unsigned char> &bytes,const std::string &value){number(bytes,value.size());bytes.insert(bytes.end(),value.begin(),value.end());}
std::vector<unsigned char> encode(const reader_metadata_snapshot &value){
  std::vector<unsigned char> bytes={'E','X','R','M','E','T','A','1'};
  number(bytes,(uint64_t)value.entity);number(bytes,(uint64_t)value.kind);number(bytes,(uint64_t)value.operation);
  number(bytes,value.source_bytes);number(bytes,value.ordinal);number(bytes,(uint64_t)value.favorite);
  for(const std::string *part:{&value.database,&value.key,&value.revision_id,&value.book_key,&value.group_id,&value.name,
      &value.parent,&value.format,&value.sha,&value.title,&value.author,&value.sort})string(bytes,*part);
  number(bytes,value.heads.size());for(const auto &head:value.heads)string(bytes,head);
  number(bytes,checksum(bytes,bytes.size()));
  if(bytes.size()>READER_METADATA_PENDING_MAX_BYTES)reject(READER_METADATA_ARGUMENT,"Pending typed metadata exceeds its byte limit");
  return bytes;
}
struct decoder {
  const std::vector<unsigned char> &bytes;size_t at=8;
  uint64_t number(){if(at>bytes.size()||bytes.size()-at<8)reject(READER_METADATA_IO,"Truncated pending metadata intent");uint64_t n=0;for(int i=0;i<8;++i)n=(n<<8)|bytes[at++];return n;}
  std::string string(size_t maximum){uint64_t n=number();if(n>maximum||at>bytes.size()||n>bytes.size()-at)reject(READER_METADATA_IO,"Invalid pending metadata field length");
    std::string value((const char *)bytes.data()+at,(size_t)n);at+=(size_t)n;if(value.find('\0')!=std::string::npos)reject(READER_METADATA_IO,"NUL in pending metadata field");return value;}
};
std::unique_ptr<reader_metadata_snapshot> decode(const reader_metadata_owner &owner,const std::vector<unsigned char> &bytes){
  if(bytes.size()<16||bytes.size()>READER_METADATA_PENDING_MAX_BYTES||std::memcmp(bytes.data(),"EXRMETA1",8))
    reject(READER_METADATA_IO,"Unknown or oversized pending metadata intent");
  decoder d{bytes};auto value=std::make_unique<reader_metadata_snapshot>();
  uint64_t entity=d.number(),kind=d.number(),operation=d.number();
  if(entity>READER_METADATA_MEMBERSHIP||kind>READER_GROUP_SERIES||operation>READER_COMMAND_RESTORE)
    reject(READER_METADATA_IO,"Invalid pending typed metadata discriminant");
  value->entity=(reader_metadata_entity)entity;value->kind=(reader_group_kind)kind;value->operation=(reader_command_operation)operation;
  value->source_bytes=d.number();value->ordinal=d.number();uint64_t favorite=d.number();
  if(favorite>1)reject(READER_METADATA_IO,"Invalid pending favorite value");
  value->favorite=(int)favorite;
  value->database=d.string(32768);value->key=d.string(256);value->revision_id=d.string(32);value->book_key=d.string(72);
  value->group_id=d.string(32);value->name=d.string(1024);value->parent=d.string(32);value->format=d.string(8);value->sha=d.string(64);
  value->title=d.string(16384);value->author=d.string(16384);value->sort=d.string(16384);
  uint64_t count=d.number();if(count>READER_REVISION_MAX_PARENTS)reject(READER_METADATA_IO,"Too many pending expected heads");
  for(uint64_t i=0;i<count;++i){auto head=d.string(32);if(!id(head)||std::find(value->heads.begin(),value->heads.end(),head)!=value->heads.end())reject(READER_METADATA_IO,"Invalid pending expected head set");value->heads.push_back(head);}
  size_t end=d.at;uint64_t stored=d.number();
  if(d.at!=bytes.size()||stored!=checksum(bytes,end)||value->database!=owner.database||!id(value->revision_id))
    reject(READER_METADATA_IO,"Pending metadata identity or checksum differs");
  return value;
}
void sync_directory(const fs::path &file){
#ifndef _WIN32
  int fd=open(file.parent_path().c_str(),O_RDONLY|O_DIRECTORY|O_CLOEXEC);
  if(fd<0)reject(READER_METADATA_IO,"Cannot open metadata directory for durable publication");
  int result=fsync(fd);close(fd);if(result)reject(READER_METADATA_IO,"Cannot synchronize metadata directory");
#else
  (void)file;
#endif
}
bool read_file(const fs::path &path,std::vector<unsigned char> &bytes){
#ifdef _WIN32
  HANDLE file=CreateFileW(path.c_str(),GENERIC_READ,FILE_SHARE_READ,nullptr,OPEN_EXISTING,FILE_FLAG_OPEN_REPARSE_POINT,nullptr);
  if(file==INVALID_HANDLE_VALUE){if(GetLastError()==ERROR_FILE_NOT_FOUND)return false;reject(READER_METADATA_IO,"Cannot read pending metadata intent");}
  BY_HANDLE_FILE_INFORMATION info{};LARGE_INTEGER size{};
  bool valid=GetFileInformationByHandle(file,&info)&&!(info.dwFileAttributes&(FILE_ATTRIBUTE_DIRECTORY|FILE_ATTRIBUTE_REPARSE_POINT))&&GetFileSizeEx(file,&size)&&size.QuadPart>0&&size.QuadPart<=(LONGLONG)READER_METADATA_PENDING_MAX_BYTES;
  if(!valid){CloseHandle(file);reject(READER_METADATA_IO,"Pending metadata is not a bounded regular file");}
  try{bytes.resize((size_t)size.QuadPart);}catch(...){CloseHandle(file);throw;}
  DWORD n=0;
  bool ok=ReadFile(file,bytes.data(),(DWORD)bytes.size(),&n,nullptr)&&n==bytes.size();CloseHandle(file);
  if(!ok)reject(READER_METADATA_IO,"Cannot read complete pending metadata intent");
#else
  int file=open(path.c_str(),O_RDONLY|O_CLOEXEC|O_NOFOLLOW);
  if(file<0){if(errno==ENOENT)return false;reject(READER_METADATA_IO,"Cannot read pending metadata intent");}
  struct stat info{};if(fstat(file,&info)||!S_ISREG(info.st_mode)||info.st_size<=0||(uint64_t)info.st_size>READER_METADATA_PENDING_MAX_BYTES){close(file);reject(READER_METADATA_IO,"Pending metadata is not a bounded regular file");}
  try{bytes.resize((size_t)info.st_size);}catch(...){close(file);throw;}
  size_t at=0;
  while(at<bytes.size()){ssize_t n=read(file,bytes.data()+at,bytes.size()-at);if(n<0&&errno==EINTR)continue;if(n<=0){close(file);reject(READER_METADATA_IO,"Cannot read complete pending metadata intent");}at+=(size_t)n;}
  close(file);
#endif
  return true;
}
std::unique_ptr<reader_metadata_snapshot> pending(reader_metadata_owner &owner){std::vector<unsigned char> bytes;if(!read_file(owner.pending,bytes))return {};return decode(owner,bytes);}
void persist(reader_metadata_owner &owner,const reader_metadata_snapshot &value,reader_metadata_result *out){
  if(pending(owner))reject(READER_METADATA_PENDING,"An earlier typed metadata intent requires replay or explicit abandonment");
  auto bytes=encode(value);fs::path temporary=owner.pending;temporary+=".tmp";
  std::error_code ec;fs::remove(temporary,ec);if(ec)reject(READER_METADATA_IO,"Cannot remove unfinished metadata publication");
#ifdef _WIN32
  HANDLE file=CreateFileW(temporary.c_str(),GENERIC_WRITE,0,nullptr,CREATE_NEW,FILE_ATTRIBUTE_NORMAL,nullptr);
  if(file==INVALID_HANDLE_VALUE)reject(READER_METADATA_IO,"Cannot create metadata publication file");
  DWORD n=0;bool ok=WriteFile(file,bytes.data(),(DWORD)bytes.size(),&n,nullptr)&&n==bytes.size()&&FlushFileBuffers(file);CloseHandle(file);
  if(!ok)reject(READER_METADATA_IO,"Cannot durably write pending metadata intent");
  if(!MoveFileExW(temporary.c_str(),owner.pending.c_str(),MOVEFILE_WRITE_THROUGH))reject(READER_METADATA_IO,"Cannot atomically publish pending metadata intent");
#else
  int file=open(temporary.c_str(),O_WRONLY|O_CREAT|O_EXCL|O_CLOEXEC|O_NOFOLLOW,0600);
  if(file<0)reject(READER_METADATA_IO,"Cannot create metadata publication file");
  size_t at=0;while(at<bytes.size()){ssize_t n=write(file,bytes.data()+at,bytes.size()-at);if(n<0&&errno==EINTR)continue;if(n<=0){close(file);reject(READER_METADATA_IO,"Cannot write pending metadata intent");}at+=(size_t)n;}
  int result=fsync(file);int closed=close(file);if(result||closed)reject(READER_METADATA_IO,"Cannot durably write pending metadata intent");
  if(rename(temporary.c_str(),owner.pending.c_str()))reject(READER_METADATA_IO,"Cannot atomically publish pending metadata intent");
#endif
  result_identity(value,out);sync_directory(owner.pending);
}
void clear(reader_metadata_owner &owner){if(!fs::remove(owner.pending))reject(READER_METADATA_IO,"Pending metadata intent disappeared before acknowledgement");sync_directory(owner.pending);}
int receive_head(void *context,const reader_revision_head *head){
  auto *value=static_cast<reader_metadata_snapshot *>(context);
  if(value->heads.size()>=READER_REVISION_MAX_PARENTS)return 1;
  value->heads.emplace_back(head->revision_id);return 0;
}
void observe(reader_metadata_owner &owner,reader_metadata_snapshot &value){
  if(value.key.empty())return;
  reader_revision_error error{};revision_check(reader_revision_heads(owner.revisions,entity_name(value),value.key.c_str(),receive_head,&value,&value.graph,&error),error);
  value.deleted=value.deleted||value.graph.deleted;
  if(value.graph.heads!=value.heads.size())reject(READER_METADATA_CONFLICT,"Observed metadata head set exceeds the command bound");
}
bool conflict(const reader_metadata_snapshot &value){return value.dependency_deleted||value.graph.heads>1||value.graph.missing_parents||value.graph.foreign_parents||value.graph.requires_restore;}
struct receive_context {reader_metadata_snapshot *value;std::exception_ptr error;};
int receive_book(void *context,const reader_catalog_row *row){
  auto *copy=static_cast<receive_context *>(context);
  try{
    auto *value=copy->value;value->present=1;
    value->book_key=text(row->book_key,72);value->format=text(row->format,8);value->sha=value->book_key.substr(value->format.size()+1);
    value->source_bytes=row->source_bytes;value->title=text(row->title,16384,true);value->author=text(row->author,16384,true);
    value->sort=text(row->sort_title,16384,true);value->favorite=row->favorite;return 0;
  }catch(...){copy->error=std::current_exception();return 1;}
}
reader_catalog_group_kind catalog_kind(reader_group_kind kind){
  switch(kind){case READER_GROUP_SHELF:return READER_CATALOG_SHELF;case READER_GROUP_TAG:return READER_CATALOG_TAG;case READER_GROUP_SERIES:return READER_CATALOG_SERIES;}
  reject(READER_METADATA_ARGUMENT,"Unknown metadata group kind");
}
int receive_group(void *context,const reader_catalog_group_row *row){
  auto *copy=static_cast<receive_context *>(context);
  try{
    auto *value=copy->value;value->present=1;value->group_id=text(row->id,32);value->name=text(row->name,1024);
    value->parent=text(row->parent_id,32,true);value->ordinal=row->ordinal;value->deleted=row->deleted;return 0;
  }catch(...){copy->error=std::current_exception();return 1;}
}
int receive_member(void *context,const reader_catalog_membership_row *row){
  auto *copy=static_cast<receive_context *>(context);
  try{
    auto *value=copy->value;value->present=1;value->group_id=text(row->group_id,32);value->book_key=text(row->book_key,72);
    value->ordinal=row->ordinal;value->dependency_deleted=row->group_deleted||row->book_deleted;return 0;
  }catch(...){copy->error=std::current_exception();return 1;}
}
void validate_snapshot(reader_metadata_owner &owner,const reader_metadata_snapshot *value,reader_metadata_entity entity){
  if(!value||value->database!=owner.database||value->entity!=entity)reject(READER_METADATA_ARGUMENT,"Metadata command does not match its prepared product snapshot");
  if(conflict(*value))reject(READER_METADATA_CONFLICT,"Metadata conflict requires explicit resolution before editing");
}
void assign_revision(reader_metadata_snapshot &value){char generated[33];reader_revision_error error{};revision_check(reader_revision_new_id(generated,&error),error);value.revision_id=generated;}
void operation(reader_command_operation value){if(value!=READER_COMMAND_PUT&&value!=READER_COMMAND_DELETE&&value!=READER_COMMAND_RESTORE)reject(READER_METADATA_ARGUMENT,"Unknown typed metadata operation");}
void book_input(reader_metadata_snapshot &value,const reader_book_command &input){
  operation(input.operation);if(text(input.book_key,72)!=value.key)reject(READER_METADATA_ARGUMENT,"Book command differs from its prepared key");
  value.operation=input.operation;
  if(input.operation!=READER_COMMAND_DELETE){
    if(text(input.format,8)!=value.format||text(input.source_sha256,64)!=value.sha||input.source_bytes!=value.source_bytes)
      reject(READER_METADATA_ARGUMENT,"Book command differs from its prepared original identity");
    if(input.favorite!=0&&input.favorite!=1)reject(READER_METADATA_ARGUMENT,"Invalid favorite value");
    value.title=text(input.title,16384,true);value.author=text(input.author,16384,true);value.sort=text(input.sort_title,16384,true);value.favorite=input.favorite;
  }
}
reader_metadata_status apply(reader_metadata_owner &owner,reader_metadata_result *out){
  auto value=pending(owner);if(!value)return READER_METADATA_NO_PENDING;
  result_identity(*value,out);value->head_pointers.clear();for(const auto &head:value->heads)value->head_pointers.push_back(head.c_str());
  reader_command_context context{owner.revisions,value->revision_id.c_str(),value->head_pointers.data(),value->head_pointers.size()};
  reader_command_error error{};reader_command_status status;
  if(value->entity==READER_METADATA_BOOK){
    reader_book_command input{value->operation,value->key.c_str(),value->format.c_str(),value->sha.c_str(),value->title.c_str(),value->author.c_str(),value->sort.c_str(),value->source_bytes,value->favorite};
    status=reader_command_apply_book(&context,&input,&out->command,&error);
  }else if(value->entity==READER_METADATA_GROUP){
    reader_group_command input{value->operation,value->kind,value->group_id.c_str(),value->name.c_str(),value->parent.c_str(),value->ordinal};
    status=reader_command_apply_group(&context,&input,&out->command,&error);
  }else{
    reader_membership_command input{value->operation,value->kind,value->group_id.c_str(),value->book_key.c_str(),value->ordinal};
    status=reader_command_apply_membership(&context,&input,&out->command,&error);
  }
  if(status!=READER_COMMAND_OK){
    reader_metadata_status mapped=status==READER_COMMAND_NEEDS_BOOK_BOOTSTRAP?READER_METADATA_NEEDS_BOOTSTRAP:
      status==READER_COMMAND_ARGUMENT?READER_METADATA_ARGUMENT:error.revision.code==READER_REV_UNSAFE?READER_METADATA_CONFLICT:READER_METADATA_REVISION;
    throw failure{mapped,"Pending typed metadata command was refused; original intent retained",error};
  }
  out->committed=1;return READER_METADATA_OK;
}
}

extern "C" reader_metadata_status reader_metadata_open(const char *product_path,const char *pending_path,reader_metadata_owner **out,reader_metadata_error *error){
  if(out)*out=nullptr;
  return call(error,[&]{
    if(!out)reject(READER_METADATA_ARGUMENT,"Missing metadata owner output");
    auto owner=std::make_unique<reader_metadata_owner>();
    owner->database=fs::weakly_canonical(fs::absolute(fs::u8path(text(product_path,32768)))).u8string();
    fs::path requested=fs::absolute(fs::u8path(text(pending_path,32768)));
    owner->pending=fs::weakly_canonical(requested.parent_path())/requested.filename();
    if(owner->pending==fs::u8path(owner->database))reject(READER_METADATA_ARGUMENT,"Pending intent must be separate from product database");
    fs::path lock=owner->pending;lock+=".lock";
#ifdef _WIN32
    owner->lock=CreateFileW(lock.c_str(),GENERIC_READ|GENERIC_WRITE,0,nullptr,OPEN_ALWAYS,FILE_FLAG_OPEN_REPARSE_POINT,nullptr);
    if(owner->lock==INVALID_HANDLE_VALUE)reject(READER_METADATA_OWNER,"Another metadata owner holds this profile or its lock is unavailable");
    BY_HANDLE_FILE_INFORMATION info{};if(!GetFileInformationByHandle(owner->lock,&info)||(info.dwFileAttributes&(FILE_ATTRIBUTE_DIRECTORY|FILE_ATTRIBUTE_REPARSE_POINT)))reject(READER_METADATA_IO,"Metadata lock is not a regular profile file");
#else
    owner->lock=open(lock.c_str(),O_RDWR|O_CREAT|O_CLOEXEC|O_NOFOLLOW,0600);
    if(owner->lock<0||flock(owner->lock,LOCK_EX|LOCK_NB))reject(READER_METADATA_OWNER,"Another metadata owner holds this profile or its lock is unavailable");
    struct stat info{};if(fstat(owner->lock,&info)||!S_ISREG(info.st_mode))reject(READER_METADATA_IO,"Metadata lock is not a regular profile file");
#endif
    (void)pending(*owner);
    reader_revision_error revision_error{};revision_check(reader_revisions_open(owner->database.c_str(),&owner->revisions,&revision_error),revision_error);
    reader_catalog_error catalog_error{};catalog_check(reader_catalog_open(owner->database.c_str(),&owner->catalog,&catalog_error),catalog_error);
    *out=owner.release();return READER_METADATA_OK;
  });
}
extern "C" reader_metadata_status reader_metadata_close(reader_metadata_owner **owner,reader_metadata_error *error){return call(error,[&]{
  if(!owner)reject(READER_METADATA_ARGUMENT,"Missing metadata owner pointer");
  if(!*owner)return READER_METADATA_OK;
  if((*owner)->thread!=std::this_thread::get_id()||(*owner)->active)reject(READER_METADATA_OWNER,"Metadata close requires its creating worker without reentry");
  delete *owner;*owner=nullptr;return READER_METADATA_OK;
});}
extern "C" reader_metadata_status reader_metadata_prepare_book(reader_metadata_owner *owner,const char *book_key,reader_metadata_snapshot **out,reader_metadata_error *error){
  if(out)*out=nullptr;
  return call(error,[&]{guard lock(owner);if(!out)reject(READER_METADATA_ARGUMENT,"Missing metadata snapshot output");
    auto value=std::make_unique<reader_metadata_snapshot>();value->database=owner->database;value->key=text(book_key,72);value->book_key=value->key;
    reader_catalog_error e{};int found=0;receive_context copy{value.get(),{}};
    catalog_check(reader_catalog_find(owner->catalog,value->key.c_str(),nullptr,receive_book,&copy,&found,&e),e);
    if(copy.error)std::rethrow_exception(copy.error);
    observe(*owner,*value);
    value->needs_bootstrap=value->present&&!value->graph.revisions;
    reader_metadata_status status=!value->present||conflict(*value)?READER_METADATA_CONFLICT:value->needs_bootstrap?READER_METADATA_NEEDS_BOOTSTRAP:READER_METADATA_OK;
    *out=value.release();return status;
  });
}
extern "C" reader_metadata_status reader_metadata_prepare_group(reader_metadata_owner *owner,reader_group_kind kind,const char *group_id,reader_metadata_snapshot **out,reader_metadata_error *error){
  if(out)*out=nullptr;
  return call(error,[&]{guard lock(owner);if(!out)reject(READER_METADATA_ARGUMENT,"Missing metadata snapshot output");
    auto value=std::make_unique<reader_metadata_snapshot>();value->database=owner->database;value->entity=READER_METADATA_GROUP;value->kind=kind;
    reader_catalog_group_kind native_kind=catalog_kind(kind);value->key=value->group_id=text(group_id,32,true);
    if(!value->key.empty()){
      if(!id(value->key))reject(READER_METADATA_ARGUMENT,"Invalid global group identity");
      reader_catalog_error e{};int found=0;receive_context copy{value.get(),{}};
      catalog_check(reader_catalog_group_find(owner->catalog,native_kind,value->key.c_str(),receive_group,&copy,&found,&e),e);
      if(copy.error)std::rethrow_exception(copy.error);
      observe(*owner,*value);
    }
    reader_metadata_status status=conflict(*value)?READER_METADATA_CONFLICT:READER_METADATA_OK;
    *out=value.release();return status;
  });
}
extern "C" reader_metadata_status reader_metadata_prepare_membership(reader_metadata_owner *owner,reader_group_kind kind,const char *group_id,const char *book_key,reader_metadata_snapshot **out,reader_metadata_error *error){
  if(out)*out=nullptr;
  return call(error,[&]{guard lock(owner);if(!out)reject(READER_METADATA_ARGUMENT,"Missing metadata snapshot output");
    auto value=std::make_unique<reader_metadata_snapshot>();value->database=owner->database;value->entity=READER_METADATA_MEMBERSHIP;value->kind=kind;
    reader_catalog_group_kind native_kind=catalog_kind(kind);value->group_id=text(group_id,32);value->book_key=text(book_key,72);
    if(!id(value->group_id))reject(READER_METADATA_ARGUMENT,"Invalid global group identity");
    value->key=std::string(kind_name(kind))+":"+value->group_id+":"+value->book_key;
    reader_catalog_error e{};int found=0;receive_context copy{value.get(),{}};
    catalog_check(reader_catalog_membership_find(owner->catalog,native_kind,value->group_id.c_str(),value->book_key.c_str(),receive_member,&copy,&found,&e),e);
    if(copy.error)std::rethrow_exception(copy.error);
    reader_metadata_snapshot group;receive_context group_copy{&group,{}};int group_found=0;
    catalog_check(reader_catalog_group_find(owner->catalog,native_kind,value->group_id.c_str(),receive_group,&group_copy,&group_found,&e),e);
    if(group_copy.error)std::rethrow_exception(group_copy.error);
    value->dependency_deleted=value->dependency_deleted||!group_found||group.deleted;
    observe(*owner,*value);uint64_t bytes=0;reader_revision_error revision_error{};
    reader_revision_status known=reader_revision_book_identity(owner->revisions,value->book_key.c_str(),&bytes,&revision_error);
    if(known==READER_REV_NOT_FOUND)value->needs_bootstrap=1;else revision_check(known,revision_error);
    reader_metadata_status status=conflict(*value)?READER_METADATA_CONFLICT:value->needs_bootstrap?READER_METADATA_NEEDS_BOOTSTRAP:READER_METADATA_OK;
    *out=value.release();return status;
  });
}
extern "C" const reader_metadata_view *reader_metadata_snapshot_view(reader_metadata_snapshot *value){
  if(!value)return nullptr;
  try{
    value->head_pointers.clear();for(const auto &head:value->heads)value->head_pointers.push_back(head.c_str());
    auto &v=value->view;v={};v.entity=value->entity;v.entity_key=value->key.c_str();v.present=value->present;v.deleted=value->deleted;v.needs_bootstrap=value->needs_bootstrap;v.dependency_deleted=value->dependency_deleted;v.graph=value->graph;
    v.heads=value->head_pointers.data();v.head_count=value->head_pointers.size();
    v.book={value->operation,value->book_key.c_str(),value->format.c_str(),value->sha.c_str(),value->title.c_str(),value->author.c_str(),value->sort.c_str(),value->source_bytes,value->favorite};
    v.group={value->operation,value->kind,value->group_id.c_str(),value->name.c_str(),value->parent.c_str(),value->ordinal};
    v.membership={value->operation,value->kind,value->group_id.c_str(),value->book_key.c_str(),value->ordinal};return &v;
  }catch(...){return nullptr;}
}
extern "C" void reader_metadata_snapshot_free(reader_metadata_snapshot *value){delete value;}
extern "C" reader_metadata_status reader_metadata_stage_book(reader_metadata_owner *owner,const reader_metadata_snapshot *snapshot,const reader_book_command *input,reader_metadata_result *out,reader_metadata_error *error){
  if(out)std::memset(out,0,sizeof(*out));
  return call(error,[&]{guard lock(owner);validate_snapshot(*owner,snapshot,READER_METADATA_BOOK);
    if(!input||!out)reject(READER_METADATA_ARGUMENT,"Missing typed book edit");
    if(snapshot->needs_bootstrap)reject(READER_METADATA_NEEDS_BOOTSTRAP,"Legacy book needs explicit verified-source bootstrap before editing");
    if(!snapshot->present)reject(READER_METADATA_CONFLICT,"Prepared book is unavailable");
    reader_metadata_snapshot value=*snapshot;book_input(value,*input);assign_revision(value);persist(*owner,value,out);return READER_METADATA_OK;
  });
}
extern "C" reader_metadata_status reader_metadata_stage_bootstrap(reader_metadata_owner *owner,const reader_metadata_snapshot *snapshot,const reader_metadata_verified_source *source,reader_metadata_result *out,reader_metadata_error *error){
  if(out)std::memset(out,0,sizeof(*out));
  return call(error,[&]{guard lock(owner);validate_snapshot(*owner,snapshot,READER_METADATA_BOOK);
    if(!source||!out||!snapshot->present||!snapshot->needs_bootstrap||snapshot->graph.revisions)reject(READER_METADATA_ARGUMENT,"Bootstrap requires a current catalog-only book snapshot");
    if(text(source->format,8)!=snapshot->format||text(source->source_sha256,64)!=snapshot->sha||source->source_bytes!=snapshot->source_bytes)
      reject(READER_METADATA_ARGUMENT,"Public SDK verified source differs from product metadata");
    reader_metadata_snapshot value=*snapshot;value.operation=READER_COMMAND_PUT;assign_revision(value);persist(*owner,value,out);return READER_METADATA_OK;
  });
}
extern "C" reader_metadata_status reader_metadata_stage_group(reader_metadata_owner *owner,const reader_metadata_snapshot *snapshot,const reader_group_command *input,reader_metadata_result *out,reader_metadata_error *error){
  if(out)std::memset(out,0,sizeof(*out));
  return call(error,[&]{guard lock(owner);validate_snapshot(*owner,snapshot,READER_METADATA_GROUP);
    if(!input||!out)reject(READER_METADATA_ARGUMENT,"Missing typed group edit");
    operation(input->operation);
    if(input->kind!=snapshot->kind||text(input->id,32,true)!=snapshot->group_id)reject(READER_METADATA_ARGUMENT,"Group command differs from its prepared identity");
    reader_metadata_snapshot value=*snapshot;value.operation=input->operation;value.name=text(input->name,1024,input->operation==READER_COMMAND_DELETE);value.parent=text(input->parent_id,32,true);value.ordinal=input->ordinal;
    if(value.group_id.empty()){
      if(input->operation!=READER_COMMAND_PUT)reject(READER_METADATA_ARGUMENT,"Only a new put may allocate a group identity");
      char generated[33];reader_revision_error e{};revision_check(reader_revision_new_id(generated,&e),e);value.group_id=value.key=generated;
    }
    assign_revision(value);persist(*owner,value,out);return READER_METADATA_OK;
  });
}
extern "C" reader_metadata_status reader_metadata_stage_membership(reader_metadata_owner *owner,const reader_metadata_snapshot *snapshot,const reader_membership_command *input,reader_metadata_result *out,reader_metadata_error *error){
  if(out)std::memset(out,0,sizeof(*out));
  return call(error,[&]{guard lock(owner);validate_snapshot(*owner,snapshot,READER_METADATA_MEMBERSHIP);
    if(!input||!out)reject(READER_METADATA_ARGUMENT,"Missing typed membership edit");
    operation(input->operation);
    if(snapshot->needs_bootstrap)reject(READER_METADATA_NEEDS_BOOTSTRAP,"Membership requires an explicit verified book bootstrap");
    if(input->kind!=snapshot->kind||text(input->group_id,32)!=snapshot->group_id||text(input->book_key,72)!=snapshot->book_key)
      reject(READER_METADATA_ARGUMENT,"Membership command differs from its prepared identity");
    reader_metadata_snapshot value=*snapshot;value.operation=input->operation;value.ordinal=input->ordinal;assign_revision(value);persist(*owner,value,out);return READER_METADATA_OK;
  });
}
extern "C" reader_metadata_status reader_metadata_apply_pending(reader_metadata_owner *owner,reader_metadata_result *out,reader_metadata_error *error){
  if(out)std::memset(out,0,sizeof(*out));
  return call(error,[&]{guard lock(owner);return apply(*owner,out);});
}
extern "C" reader_metadata_status reader_metadata_finish_pending(reader_metadata_owner *owner,reader_metadata_result *out,reader_metadata_error *error){
  if(out)std::memset(out,0,sizeof(*out));
  return call(error,[&]{guard lock(owner);reader_metadata_status status=apply(*owner,out);if(status!=READER_METADATA_OK)return status;
    try{clear(*owner);out->pending=0;}catch(...){reject(READER_METADATA_COMMITTED_PENDING_CLEAR,"Product command committed; pending intent cleanup requires retry");}
    return READER_METADATA_OK;
  });
}
extern "C" reader_metadata_status reader_metadata_pending(reader_metadata_owner *owner,reader_metadata_result *out,reader_metadata_error *error){
  if(out)std::memset(out,0,sizeof(*out));
  return call(error,[&]{guard lock(owner);auto value=pending(*owner);if(!value)return READER_METADATA_NO_PENDING;result_identity(*value,out);return READER_METADATA_OK;});
}
extern "C" reader_metadata_status reader_metadata_abandon_pending(reader_metadata_owner *owner,reader_metadata_error *error){return call(error,[&]{guard lock(owner);auto value=pending(*owner);if(!value)return READER_METADATA_NO_PENDING;
  char *wire=nullptr;size_t bytes=0;reader_revision_info info{};reader_revision_error e{};
  reader_revision_status status=reader_revision_get(owner->revisions,value->revision_id.c_str(),&wire,&bytes,&info,&e);reader_revision_bytes_free(wire);
  if(status==READER_REV_OK)reject(READER_METADATA_CONFLICT,"Committed pending intent must be replayed and finished");
  if(status!=READER_REV_NOT_FOUND)revision_check(status,e);
  clear(*owner);return READER_METADATA_OK;
});}
