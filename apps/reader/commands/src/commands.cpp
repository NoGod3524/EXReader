/* SPDX-License-Identifier: MIT */
#include "reader_commands.h"
#include <algorithm>
#include <climits>
#include <cstdio>
#include <cstring>
#include <set>
#include <string>
#include <vector>

namespace {
struct failure {reader_command_status code;const char *message;reader_revision_error revision{};};
[[noreturn]] void reject(const char *message){throw failure{READER_COMMAND_ARGUMENT,message,{}};}
void revision(reader_revision_status status,const reader_revision_error &error){
  if(status!=READER_REV_OK)throw failure{READER_COMMAND_REVISION,"Native product command was refused",error};
}
std::string text(const char *value,size_t maximum,bool empty=false){
  if(!value){if(empty)return {};reject("Missing command text");}
  size_t size=0;while(size<=maximum&&value[size])++size;
  if(size>maximum||(!empty&&!size))reject("Command text exceeds its bound or is empty");
  return std::string(value,size);
}
bool identifier(const std::string &value){
  return value.size()==32&&value.find_first_not_of("0123456789abcdef")==std::string::npos;
}
std::string id(const char *value){std::string result=text(value,32);if(!identifier(result))reject("Invalid global command ID");return result;}
std::string quote(const std::string &value){
  std::string result="\"";const char *hex="0123456789abcdef";
  for(unsigned char ch:value){
    if(ch=='\"'||ch=='\\'){result+='\\';result+=(char)ch;}
    else if(ch<32){result+="\\u00";result+=hex[ch>>4];result+=hex[ch&15];}
    else result+=(char)ch;
  }
  return result+'\"';
}
const char *operation(reader_command_operation value){
  switch(value){case READER_COMMAND_PUT:return "put";case READER_COMMAND_DELETE:return "delete";
    case READER_COMMAND_RESTORE:return "restore";default:reject("Unknown command operation");}
}
const char *group(reader_group_kind value){
  switch(value){case READER_GROUP_SHELF:return "shelf";case READER_GROUP_TAG:return "tag";
    case READER_GROUP_SERIES:return "series";default:reject("Unknown command group");}
}
std::string book(const char *value){
  std::string key=text(value,72);size_t colon=key.find(':');
  if(colon==std::string::npos||key.size()-colon-1!=64||key.find_first_not_of("0123456789abcdef",colon+1)!=std::string::npos)
    reject("Invalid original book key");
  std::string format=key.substr(0,colon);
  if(format!="epub"&&format!="pdf"&&format!="cbz"&&format!="txt"&&format!="html"&&format!="fb2"&&format!="docx"&&format!="rtf"&&format!="mobi")
    reject("Unknown original book format");
  return key;
}
void assigned(char *target,size_t capacity,const std::string &value){
  if(value.size()>=capacity)reject("Assigned command identity exceeds its bound");
  std::memcpy(target,value.c_str(),value.size()+1);
}
struct command {
  const reader_command_context &context;reader_command_result &result;
  std::string revision_id;std::vector<std::string> parents;std::vector<const char *> pointers;
  command(const reader_command_context *input,reader_command_result *output,reader_command_operation op):context(*input),result(*output){
    operation(op);
    if(!context.store||context.expected_count>READER_REVISION_MAX_PARENTS||
       (context.expected_count&&!context.expected_heads))reject("Invalid observed command heads");
    if(op!=READER_COMMAND_PUT&&!context.expected_count)reject("Delete or restore requires observed history");
    std::set<std::string> unique;
    for(size_t n=0;n<context.expected_count;++n)if(!unique.insert(id(context.expected_heads[n])).second)reject("Duplicate observed head");
    parents.assign(unique.begin(),unique.end());
    for(const auto &parent:parents)pointers.push_back(parent.c_str());
    revision_id=text(context.revision_id,32,true);
    if(revision_id.empty()){char generated[33];reader_revision_error error{};revision(reader_revision_new_id(generated,&error),error);revision_id=generated;}
    else if(!identifier(revision_id))reject("Invalid stable revision ID");
    assigned(result.revision_id,sizeof(result.revision_id),revision_id);
  }
  void apply(const std::string &kind,const std::string &key,reader_command_operation op,const std::string &payload,const char *sort=nullptr){
    assigned(result.entity_key,sizeof(result.entity_key),key);
    std::string wire="{\"version\":1,\"id\":"+quote(revision_id)+",\"entity_kind\":"+quote(kind)+",\"entity_key\":"+quote(key)
      +",\"operation\":"+quote(operation(op))+",\"location_kind\":\"none\",\"parents\":[";
    for(size_t n=0;n<parents.size();++n){if(n)wire+=',';wire+=quote(parents[n]);}
    wire+="],\"payload\":"+payload+'}';
    reader_revision_error error{};
    revision(reader_revision_local_project(context.store,wire.data(),wire.size(),pointers.data(),pointers.size(),sort,
      &result.revision,&result.created,&result.applied,&error),error);
  }
};
template<class Function>reader_command_status call(const reader_command_context *context,const void *input,reader_command_result *result,
    reader_command_error *error,Function function){
  if(error)std::memset(error,0,sizeof(*error));
  if(result)std::memset(result,0,sizeof(*result));
  try{if(!context||!input||!result)reject("Missing product command arguments");function();return READER_COMMAND_OK;}
  catch(const failure &failed){if(error){error->code=failed.code;error->revision=failed.revision;std::snprintf(error->message,sizeof(error->message),"%s",failed.message);}return failed.code;}
  catch(...){if(error){error->code=READER_COMMAND_REVISION;error->revision.code=READER_REV_MEMORY;
    std::snprintf(error->message,sizeof(error->message),"Cannot allocate bounded typed command");}return READER_COMMAND_REVISION;}
}
}
extern "C" reader_command_status reader_command_utf16(const uint16_t *input,size_t units,
    char *output,size_t capacity,size_t *bytes,reader_command_error *error){
  if(error)std::memset(error,0,sizeof(*error));
  if(bytes)*bytes=0;
  if(output&&capacity)output[0]=0;
  try{
    if((!input&&units)||!output||!capacity||!bytes||units>16384)reject("Invalid bounded UTF-16 arguments");
    std::string value;
    for(size_t i=0;i<units;++i){
      uint32_t scalar=input[i];
      if(!scalar)reject("NUL is not allowed in command text");
      if(scalar>=0xd800&&scalar<=0xdbff){
        if(i+1==units||input[i+1]<0xdc00||input[i+1]>0xdfff)reject("Unpaired UTF-16 high surrogate");
        scalar=0x10000+((scalar-0xd800)<<10)+(input[++i]-0xdc00);
      }else if(scalar>=0xdc00&&scalar<=0xdfff)reject("Unpaired UTF-16 low surrogate");
      if(scalar<0x80)value+=(char)scalar;
      else if(scalar<0x800){value+=(char)(0xc0|(scalar>>6));value+=(char)(0x80|(scalar&63));}
      else if(scalar<0x10000){value+=(char)(0xe0|(scalar>>12));value+=(char)(0x80|((scalar>>6)&63));value+=(char)(0x80|(scalar&63));}
      else {value+=(char)(0xf0|(scalar>>18));value+=(char)(0x80|((scalar>>12)&63));value+=(char)(0x80|((scalar>>6)&63));value+=(char)(0x80|(scalar&63));}
      if(value.size()>16384||value.size()>=capacity)reject("UTF-8 command text exceeds output capacity");
    }
    std::memcpy(output,value.c_str(),value.size()+1);*bytes=value.size();return READER_COMMAND_OK;
  }catch(const failure &failed){if(error){error->code=failed.code;std::snprintf(error->message,sizeof(error->message),"%s",failed.message);}return failed.code;}
  catch(...){if(error){error->code=READER_COMMAND_REVISION;error->revision.code=READER_REV_MEMORY;}return READER_COMMAND_REVISION;}
}
extern "C" reader_command_status reader_command_apply_book(const reader_command_context *context,const reader_book_command *input,
    reader_command_result *result,reader_command_error *error){return call(context,input,result,error,[&]{
  command request(context,result,input->operation);std::string key=book(input->book_key),payload="null",sort;
  if(input->operation!=READER_COMMAND_DELETE){
    if(!input->title||!input->author||!input->sort_title)reject("Book metadata and host sort title are required");
    std::string format=text(input->format,8),sha=text(input->source_sha256,64);
    if(format+":"+sha!=key||!input->source_bytes||input->source_bytes>(uint64_t)INT64_MAX||(input->favorite!=0&&input->favorite!=1))
      reject("Book metadata differs from verified original identity");
    std::string title=text(input->title,16384,true),author=text(input->author,16384,true);sort=text(input->sort_title,16384,true);
    payload="{\"format\":"+quote(format)+",\"source_sha256\":"+quote(sha)+",\"source_bytes\":"+std::to_string(input->source_bytes)
      +",\"title\":"+quote(title)+",\"author\":"+quote(author)+",\"favorite\":"+(input->favorite?"true":"false")+'}';
  }
  request.apply("book",key,input->operation,payload,input->operation==READER_COMMAND_DELETE?nullptr:sort.c_str());
});}
extern "C" reader_command_status reader_command_apply_group(const reader_command_context *context,const reader_group_command *input,
    reader_command_result *result,reader_command_error *error){return call(context,input,result,error,[&]{
  command request(context,result,input->operation);const char *kind=group(input->kind);std::string key=text(input->id,32,true),payload="null";
  if(key.empty()){
    if(input->operation!=READER_COMMAND_PUT||context->expected_count)reject("Only a new group can allocate its identity");
    char generated[33];reader_revision_error failed{};revision(reader_revision_new_id(generated,&failed),failed);key=generated;
  }else if(!identifier(key))reject("Invalid group identity");
  assigned(result->entity_key,sizeof(result->entity_key),key);
  if(input->ordinal>(uint64_t)INT64_MAX)reject("Group ordinal exceeds signed storage range");
  std::string parent=text(input->parent_id,32,true);
  if(input->kind!=READER_GROUP_SHELF&&(!parent.empty()||input->ordinal))reject("Only a shelf has a parent and ordinal");
  if(!parent.empty()&&!identifier(parent))reject("Invalid shelf parent");
  if(input->operation!=READER_COMMAND_DELETE){payload="{\"name\":"+quote(text(input->name,1024));
    if(input->kind==READER_GROUP_SHELF)payload+=",\"parent_id\":"+(parent.empty()?std::string("null"):quote(parent))+",\"ordinal\":"+std::to_string(input->ordinal);
    payload+='}';
  }
  request.apply(kind,key,input->operation,payload);
});}
extern "C" reader_command_status reader_command_apply_membership(const reader_command_context *context,const reader_membership_command *input,
    reader_command_result *result,reader_command_error *error){return call(context,input,result,error,[&]{
  command request(context,result,input->operation);const char *kind=group(input->kind);
  std::string group_id=id(input->group_id),key=book(input->book_key);uint64_t bytes=0;reader_revision_error failed{};
  reader_revision_status found=reader_revision_book_identity(context->store,key.c_str(),&bytes,&failed);
  if(found==READER_REV_NOT_FOUND)throw failure{READER_COMMAND_NEEDS_BOOK_BOOTSTRAP,"NEEDS_BOOK_BOOTSTRAP",failed};
  revision(found,failed);if(!bytes)reject("Retained original length is missing");
  if(input->ordinal>(uint64_t)INT64_MAX||(input->kind==READER_GROUP_TAG&&input->ordinal))reject("Invalid membership ordinal");
  std::string payload="null";
  if(input->operation!=READER_COMMAND_DELETE)payload="{\"book_key\":"+quote(key)+",\"collection_kind\":"+quote(kind)
    +",\"collection_id\":"+quote(group_id)+",\"ordinal\":"+std::to_string(input->ordinal)+'}';
  request.apply("membership",std::string(kind)+":"+group_id+":"+key,input->operation,payload);
});}
