/* SPDX-License-Identifier: MIT */
#include "reader_conflict_actions.h"
#include <algorithm>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <memory>
#include <new>
#include <string>
#include <thread>
#include <vector>

struct reader_conflict_snapshot {
  reader_conflict_target_kind kind=READER_CONFLICT_TARGET_BOOK;
  reader_group_kind group_kind=READER_GROUP_SHELF;
  std::string entity_kind,entity_key;
  std::vector<reader_conflict_head> heads;
  std::vector<std::string> wires,ids;
  std::vector<const char *> id_pointers;
  reader_conflict_view view{};
};
struct reader_conflict_owner {
  std::thread::id thread=std::this_thread::get_id();
  bool active=false;
  reader_revisions *store=nullptr;
};

namespace {
struct failure {reader_conflict_status code;std::string message;reader_revision_error revision{};reader_command_error command{};};
[[noreturn]] void reject(reader_conflict_status code,const char *message){throw failure{code,message,{},{}};}
void fill(reader_conflict_error *error,const failure &failed){
  if(!error)return;
  *error={};error->revision=failed.revision;error->command=failed.command;
  std::snprintf(error->message,sizeof(error->message),"%s",failed.message.c_str());
}
struct guard {
  reader_conflict_owner *owner;
  explicit guard(reader_conflict_owner *value):owner(value){
    if(!owner||!owner->store||owner->thread!=std::this_thread::get_id()||owner->active)
      reject(READER_CONFLICT_OWNER,"Conflict owner requires its creating worker without reentry");
    owner->active=true;
  }
  ~guard(){owner->active=false;}
};
template<class Function>reader_conflict_status call(reader_conflict_error *error,Function function){
  if(error)*error={};
  try{function();return READER_CONFLICT_OK;}
  catch(const failure &failed){fill(error,failed);return failed.code;}
  catch(const std::bad_alloc &){fill(error,failure{READER_CONFLICT_MEMORY,"Cannot allocate bounded conflict snapshot",{},{}});return READER_CONFLICT_MEMORY;}
  catch(...){fill(error,failure{READER_CONFLICT_MEMORY,"Unexpected conflict action failure",{},{}});return READER_CONFLICT_MEMORY;}
}
void poll(const reader_conflict_cancel *cancel){
  if(cancel&&cancel->is_cancelled&&cancel->is_cancelled(cancel->context))reject(READER_CONFLICT_CANCELLED,"Conflict action was cancelled before commit");
}
void revision(reader_revision_status status,const reader_revision_error &error,const char *message){
  if(status!=READER_REV_OK)throw failure{READER_CONFLICT_REVISION,message,error,{}};
}
bool hex(const char *value,size_t size){
  if(!value||std::strlen(value)!=size)return false;
  for(size_t n=0;n<size;++n)if(!((value[n]>='0'&&value[n]<='9')||(value[n]>='a'&&value[n]<='f')))return false;
  return true;
}
bool book_key(const char *value){
  if(!value)return false;
  const char *colon=std::strchr(value,':');
  if(!colon||!hex(colon+1,64))return false;
  std::string format(value,(size_t)(colon-value));
  for(const char *known:{"epub","pdf","cbz","txt","html","fb2","docx","rtf","mobi"})if(format==known)return true;
  return false;
}
const char *group_name(reader_group_kind kind){
  switch(kind){case READER_GROUP_SHELF:return "shelf";case READER_GROUP_TAG:return "tag";case READER_GROUP_SERIES:return "series";}
  reject(READER_CONFLICT_ARGUMENT,"Unknown group kind");
}
struct heads_read {
  std::vector<reader_revision_head> heads;
  reader_revision_state graph{};
  bool overflow=false;
};
int collect(void *context,const reader_revision_head *head){
  auto &read=*static_cast<heads_read *>(context);
  if(read.heads.size()>=READER_CONFLICT_MAX_HEADS){read.overflow=true;return 1;}
  read.heads.push_back(*head);return 0;
}
heads_read read_heads(reader_revisions *store,const std::string &kind,const std::string &key){
  heads_read read;reader_revision_error error{};
  revision(reader_revision_heads(store,kind.c_str(),key.c_str(),collect,&read,&read.graph,&error),error,"Cannot read the complete head set");
  if(read.overflow||read.graph.heads>READER_CONFLICT_MAX_HEADS)reject(READER_CONFLICT_LIMIT,"More concurrent heads than one merge revision can name");
  return read;
}
bool same(const heads_read &a,const heads_read &b){
  if(a.heads.size()!=b.heads.size()||a.graph.revisions!=b.graph.revisions||a.graph.missing_parents!=b.graph.missing_parents||
     a.graph.foreign_parents!=b.graph.foreign_parents)return false;
  for(size_t n=0;n<a.heads.size();++n)
    if(std::strcmp(a.heads[n].revision_id,b.heads[n].revision_id)||std::strcmp(a.heads[n].sha256,b.heads[n].sha256)||
       a.heads[n].complete!=b.heads[n].complete||a.heads[n].requires_restore!=b.heads[n].requires_restore)return false;
  return true;
}
bool is_delete(const reader_revision_head &head){return !std::strcmp(head.operation,"delete");}
reader_conflict_state classify(const reader_revision_state &graph,const std::vector<reader_conflict_head> &heads){
  bool tombstone=false,incomplete=graph.missing_parents||graph.foreign_parents;
  for(const auto &item:heads){incomplete=incomplete||!item.head.complete;tombstone=tombstone||is_delete(item.head)||item.head.requires_restore;}
  if(incomplete)return READER_CONFLICT_STATE_INCOMPLETE;
  if(tombstone)return READER_CONFLICT_STATE_TOMBSTONED;
  return heads.size()>1?READER_CONFLICT_STATE_CONCURRENT:READER_CONFLICT_STATE_SAFE;
}
void build(reader_conflict_snapshot &out,const heads_read &read,std::vector<std::string> &&wires,std::vector<reader_revision_info> &&infos){
  out.wires=std::move(wires);out.heads.clear();out.ids.clear();out.id_pointers.clear();
  out.heads.reserve(read.heads.size());out.ids.reserve(read.heads.size());
  size_t total=0;
  for(size_t n=0;n<read.heads.size();++n){
    reader_conflict_head item{};item.head=read.heads[n];item.info=infos[n];item.wire=out.wires[n].c_str();item.wire_bytes=out.wires[n].size();
    total+=item.wire_bytes;out.heads.push_back(item);out.ids.emplace_back(read.heads[n].revision_id);
  }
  for(const auto &id:out.ids)out.id_pointers.push_back(id.c_str());
  auto &view=out.view;view={};view.kind=out.kind;view.entity_kind=out.entity_kind.c_str();view.entity_key=out.entity_key.c_str();
  view.graph=read.graph;view.heads=out.heads.data();view.head_count=out.heads.size();view.head_ids=out.id_pointers.data();view.wire_bytes=total;
  view.state=classify(read.graph,out.heads);
  bool editable=out.kind==READER_CONFLICT_TARGET_BOOK||out.kind==READER_CONFLICT_TARGET_GROUP||out.kind==READER_CONFLICT_TARGET_MEMBERSHIP;
  view.resolvable=editable&&view.state!=READER_CONFLICT_STATE_SAFE&&view.state!=READER_CONFLICT_STATE_INCOMPLETE;
}
void identify(const reader_conflict_target &target,reader_conflict_snapshot &out){
  out.kind=target.kind;out.group_kind=target.group_kind;
  switch(target.kind){
    case READER_CONFLICT_TARGET_BOOK:
    case READER_CONFLICT_TARGET_PROGRESS:
      if(!book_key(target.book_key))reject(READER_CONFLICT_ARGUMENT,"Invalid original book key");
      out.entity_kind=target.kind==READER_CONFLICT_TARGET_BOOK?"book":"progress";out.entity_key=target.book_key;break;
    case READER_CONFLICT_TARGET_GROUP:
      if(!hex(target.group_id,32))reject(READER_CONFLICT_ARGUMENT,"Invalid group identity");
      out.entity_kind=group_name(target.group_kind);out.entity_key=target.group_id;break;
    case READER_CONFLICT_TARGET_MEMBERSHIP:
      if(!hex(target.group_id,32)||!book_key(target.book_key))reject(READER_CONFLICT_ARGUMENT,"Invalid membership identity");
      out.entity_kind="membership";out.entity_key=std::string(group_name(target.group_kind))+":"+target.group_id+":"+target.book_key;break;
    case READER_CONFLICT_TARGET_ANNOTATION:
      if(!book_key(target.book_key)||!hex(target.annotation_id,32))reject(READER_CONFLICT_ARGUMENT,"Invalid annotation identity");
      out.entity_kind="annotation";out.entity_key=std::string(target.book_key)+":"+target.annotation_id;break;
    default:reject(READER_CONFLICT_ARGUMENT,"Unknown conflict target");
  }
}
bool retained(reader_revisions *store,const std::string &id){
  if(id.empty())return false;
  char *wire=nullptr;size_t bytes=0;reader_revision_info info{};reader_revision_error error{};
  bool found=reader_revision_get(store,id.c_str(),&wire,&bytes,&info,&error)==READER_REV_OK;
  reader_revision_bytes_free(wire);return found;
}
/* Shared pre-write checks; `identity` already matched the typed command. */
void admit(reader_conflict_owner &owner,const reader_conflict_snapshot &snapshot,reader_command_operation operation,const std::string &id){
  const auto &view=snapshot.view;
  if(snapshot.kind==READER_CONFLICT_TARGET_PROGRESS||snapshot.kind==READER_CONFLICT_TARGET_ANNOTATION)
    reject(READER_CONFLICT_READING_HOST,"Reading anchor conflicts are shown to the host and never resolved here");
  if(retained(owner.store,id))return; /* Exact retry/collision is decided by the native transaction. */
  if(view.state==READER_CONFLICT_STATE_INCOMPLETE)reject(READER_CONFLICT_INCOMPLETE,"History has missing or foreign parents; wait for them and prepare again");
  if(view.state==READER_CONFLICT_STATE_SAFE)reject(READER_CONFLICT_NOT_CONFLICT,"One complete safe head needs no conflict action");
  bool tombstone=false,all_deleted=true;
  for(size_t n=0;n<view.head_count;++n){
    const auto &head=view.heads[n].head;
    tombstone=tombstone||is_delete(head)||head.requires_restore;all_deleted=all_deleted&&is_delete(head);
  }
  bool direct=false;
  for(size_t n=0;n<view.head_count;++n)direct=direct||is_delete(view.heads[n].head);
  if(operation==READER_COMMAND_PUT&&tombstone)reject(READER_CONFLICT_RESTORE_REQUIRED,"A tombstone is observed; choose an explicit restore");
  if(operation==READER_COMMAND_RESTORE&&!direct)reject(READER_CONFLICT_NOT_TOMBSTONED,"Restore requires a directly observed delete head");
  if(operation==READER_COMMAND_DELETE&&all_deleted)reject(READER_CONFLICT_NOT_CONFLICT,"Every observed head is already a tombstone");
}
template<class Check,class Apply>reader_conflict_status resolve(reader_conflict_owner *owner,const reader_conflict_snapshot *snapshot,const char *revision_id,
    reader_conflict_target_kind expected,reader_command_operation operation,const void *input,const reader_conflict_cancel *cancel,
    reader_conflict_result *result,reader_conflict_error *error,Check check,Apply apply){
  if(result)*result={};
  return call(error,[&]{
    if(!owner||!snapshot||!input||!result)reject(READER_CONFLICT_ARGUMENT,"Missing conflict resolution arguments");
    guard lock(owner);
    std::string id=revision_id?revision_id:"";
    if(id.size()>32)reject(READER_CONFLICT_ARGUMENT,"Invalid stable revision ID");
    if(!id.empty()&&!hex(id.c_str(),32))reject(READER_CONFLICT_ARGUMENT,"Invalid stable revision ID");
    if(!id.empty())std::snprintf(result->command.revision_id,sizeof(result->command.revision_id),"%s",id.c_str());
    if(snapshot->kind!=expected&&snapshot->kind!=READER_CONFLICT_TARGET_PROGRESS&&snapshot->kind!=READER_CONFLICT_TARGET_ANNOTATION)
      reject(READER_CONFLICT_IDENTITY,"Snapshot belongs to a different entity type");
    check();
    admit(*owner,*snapshot,operation,id);
    poll(cancel);
    result->observed_heads=snapshot->view.head_count;
    reader_command_context context{owner->store,id.empty()?nullptr:id.c_str(),snapshot->id_pointers.data(),snapshot->id_pointers.size()};
    reader_command_error failed{};
    reader_command_status status=apply(context,result->command,failed);
    if(status==READER_COMMAND_OK){result->committed=1;return;}
    if(status==READER_COMMAND_NEEDS_BOOK_BOOTSTRAP)throw failure{READER_CONFLICT_NEEDS_BOOTSTRAP,"Membership needs verified retained book history",failed.revision,failed};
    if(status==READER_COMMAND_REVISION&&failed.revision.code==READER_REV_UNSAFE){
      /* Classify after the native rollback: a changed head set is STALE, otherwise a graph rule refused it. */
      heads_read now;bool changed=false;
      try{now=read_heads(owner->store,snapshot->entity_kind,snapshot->entity_key);}catch(const failure &){changed=true;}
      if(!changed){
        changed=now.heads.size()!=snapshot->view.head_count;
        for(size_t n=0;!changed&&n<now.heads.size();++n)changed=std::strcmp(now.heads[n].revision_id,snapshot->view.head_ids[n])!=0;
      }
      if(changed)throw failure{READER_CONFLICT_STALE,"Head set changed after the snapshot; prepare again",failed.revision,failed};
    }
    throw failure{status==READER_COMMAND_REVISION?READER_CONFLICT_REVISION:READER_CONFLICT_COMMAND,"Typed conflict command was refused",failed.revision,failed};
  });
}
}

extern "C" reader_conflict_status reader_conflict_open(const char *path,reader_conflict_owner **out,reader_conflict_error *error){
  if(out)*out=nullptr;
  return call(error,[&]{
    if(!path||!*path||!out)reject(READER_CONFLICT_ARGUMENT,"Missing product path or owner output");
    auto *owner=new reader_conflict_owner();
    reader_revision_error failed{};
    reader_revision_status status=reader_revisions_open(path,&owner->store,&failed);
    if(status!=READER_REV_OK){delete owner;throw failure{READER_CONFLICT_REVISION,"Cannot open the product revision store",failed,{}};}
    *out=owner;
  });
}
extern "C" reader_conflict_status reader_conflict_close(reader_conflict_owner **handle,reader_conflict_error *error){
  return call(error,[&]{
    if(!handle)reject(READER_CONFLICT_ARGUMENT,"Missing owner handle");
    if(!*handle)return;
    reader_conflict_owner *owner=*handle;
    if(owner->thread!=std::this_thread::get_id()||owner->active)reject(READER_CONFLICT_OWNER,"Conflict owner requires its creating worker without reentry");
    reader_revision_error failed{};
    reader_revision_status status=reader_revisions_close(&owner->store,&failed);
    if(status!=READER_REV_OK)throw failure{READER_CONFLICT_REVISION,"Cannot close the product revision store",failed,{}};
    delete owner;*handle=nullptr;
  });
}
extern "C" reader_conflict_status reader_conflict_prepare(reader_conflict_owner *owner,const reader_conflict_target *target,
    const reader_conflict_cancel *cancel,reader_conflict_snapshot **out,reader_conflict_error *error){
  if(out)*out=nullptr;
  return call(error,[&]{
    if(!owner||!target||!out)reject(READER_CONFLICT_ARGUMENT,"Missing conflict target or snapshot output");
    guard lock(owner);
    std::unique_ptr<reader_conflict_snapshot> snapshot(new reader_conflict_snapshot());
    identify(*target,*snapshot);
    for(int attempt=0;attempt<3;++attempt){
      poll(cancel);
      heads_read before=read_heads(owner->store,snapshot->entity_kind,snapshot->entity_key);
      if(!before.graph.revisions)reject(READER_CONFLICT_NOT_FOUND,"No retained revision exists for this entity");
      std::vector<std::string> wires;std::vector<reader_revision_info> infos;size_t total=0;
      for(const auto &head:before.heads){
        poll(cancel);
        char *wire=nullptr;size_t bytes=0;reader_revision_info info{};reader_revision_error failed{};
        reader_revision_status status=reader_revision_get(owner->store,head.revision_id,&wire,&bytes,&info,&failed);
        struct release {char *value;~release(){reader_revision_bytes_free(value);}} owned{wire};
        revision(status,failed,"Cannot copy a retained head revision");
        if(std::strcmp(info.revision_id,head.revision_id)||std::strcmp(info.sha256,head.sha256)||
           snapshot->entity_kind!=info.entity_kind||snapshot->entity_key!=info.entity_key)
          reject(READER_CONFLICT_STALE,"Retained head differs from the graph read");
        total+=bytes;if(total>READER_CONFLICT_MAX_WIRE_BYTES)reject(READER_CONFLICT_LIMIT,"Head wire bytes exceed the snapshot bound");
        wires.emplace_back(wire,bytes);infos.push_back(info);
      }
      poll(cancel);
      heads_read after=read_heads(owner->store,snapshot->entity_kind,snapshot->entity_key);
      if(!same(before,after)){if(attempt==2)reject(READER_CONFLICT_STALE,"Head set kept changing while preparing");continue;}
      build(*snapshot,before,std::move(wires),std::move(infos));
      *out=snapshot.release();return;
    }
  });
}
extern "C" const reader_conflict_view *reader_conflict_snapshot_view(const reader_conflict_snapshot *snapshot){return snapshot?&snapshot->view:nullptr;}
extern "C" void reader_conflict_snapshot_free(reader_conflict_snapshot *snapshot){delete snapshot;}

extern "C" reader_conflict_status reader_conflict_resolve_book(reader_conflict_owner *owner,const reader_conflict_snapshot *snapshot,
    const char *revision_id,const reader_book_command *input,const reader_conflict_cancel *cancel,
    reader_conflict_result *result,reader_conflict_error *error){
  return resolve(owner,snapshot,revision_id,READER_CONFLICT_TARGET_BOOK,input?input->operation:READER_COMMAND_PUT,input,cancel,result,error,
    [&]{
      if(snapshot->kind==READER_CONFLICT_TARGET_BOOK&&(!input->book_key||snapshot->entity_key!=input->book_key))
        reject(READER_CONFLICT_IDENTITY,"Book command names a different original");
    },
    [&](const reader_command_context &context,reader_command_result &out,reader_command_error &failed){
      return reader_command_apply_book(&context,input,&out,&failed);
    });
}
extern "C" reader_conflict_status reader_conflict_resolve_group(reader_conflict_owner *owner,const reader_conflict_snapshot *snapshot,
    const char *revision_id,const reader_group_command *input,const reader_conflict_cancel *cancel,
    reader_conflict_result *result,reader_conflict_error *error){
  return resolve(owner,snapshot,revision_id,READER_CONFLICT_TARGET_GROUP,input?input->operation:READER_COMMAND_PUT,input,cancel,result,error,
    [&]{
      if(snapshot->kind==READER_CONFLICT_TARGET_GROUP&&(!input->id||snapshot->entity_key!=input->id||snapshot->entity_kind!=group_name(input->kind)))
        reject(READER_CONFLICT_IDENTITY,"Group command names a different group");
    },
    [&](const reader_command_context &context,reader_command_result &out,reader_command_error &failed){
      return reader_command_apply_group(&context,input,&out,&failed);
    });
}
extern "C" reader_conflict_status reader_conflict_resolve_membership(reader_conflict_owner *owner,const reader_conflict_snapshot *snapshot,
    const char *revision_id,const reader_membership_command *input,const reader_conflict_cancel *cancel,
    reader_conflict_result *result,reader_conflict_error *error){
  return resolve(owner,snapshot,revision_id,READER_CONFLICT_TARGET_MEMBERSHIP,input?input->operation:READER_COMMAND_PUT,input,cancel,result,error,
    [&]{
      if(snapshot->kind==READER_CONFLICT_TARGET_MEMBERSHIP&&(!input->group_id||!input->book_key||
         snapshot->entity_key!=std::string(group_name(input->kind))+":"+input->group_id+":"+input->book_key))
        reject(READER_CONFLICT_IDENTITY,"Membership command names a different relation");
    },
    [&](const reader_command_context &context,reader_command_result &out,reader_command_error &failed){
      return reader_command_apply_membership(&context,input,&out,&failed);
    });
}
