/* SPDX-License-Identifier: MIT */
#include "reader_bulk.h"
#include <algorithm>
#include <cstdio>
#include <cstring>
#include <exception>
#include <filesystem>
#include <memory>
#include <string>
#include <system_error>
#include <thread>
#include <vector>
#ifdef _WIN32
#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#else
#include <cerrno>
#include <fcntl.h>
#include <sys/stat.h>
#include <unistd.h>
#endif

namespace fs=std::filesystem;

namespace {
enum item_phase {PHASE_PENDING=0,PHASE_STAGED=1,PHASE_DONE=2};
struct item_state {
  std::string book_key,entity_key,revision_id,message;
  uint64_t phase=PHASE_PENDING,outcome=READER_BULK_ITEM_NOT_RUN,created=0,replayed=0,heads_known=0,metadata=READER_METADATA_OK;
  std::vector<std::string> heads;
};
struct batch {
  std::string database,batch_id,group_id;
  uint64_t action=0,ordinal_base=0,cancelled=0;
  std::vector<item_state> items;
};
struct failure {reader_bulk_status code;reader_metadata_status metadata;std::string message;};
[[noreturn]] void reject(reader_bulk_status code,const char *message,reader_metadata_status metadata=READER_METADATA_OK){throw failure{code,metadata,message};}
}

struct reader_bulk {
  std::thread::id thread=std::this_thread::get_id();
  bool active=false;
  reader_metadata_owner *owner=nullptr;
  reader_revisions *revisions=nullptr;
  std::string database;
  fs::path journal;
  ~reader_bulk(){reader_revisions_close(&revisions,nullptr);}
};

namespace {
struct guard {
  reader_bulk *handle;
  explicit guard(reader_bulk *value):handle(value){
    if(!handle||handle->thread!=std::this_thread::get_id()||handle->active)reject(READER_BULK_OWNER,"Bulk organization requires its creating worker without reentry");
    handle->active=true;
  }
  ~guard(){handle->active=false;}
};
void set_error(reader_bulk_error *error,reader_bulk_status code,reader_metadata_status metadata,const std::string &message){
  if(!error)return;
  std::memset(error,0,sizeof(*error));error->code=code;error->metadata=metadata;
  size_t n=std::min(message.size(),sizeof(error->message)-1);std::memcpy(error->message,message.data(),n);error->message[n]=0;
}
template<class Function>reader_bulk_status call(reader_bulk_error *error,Function function){
  if(error)std::memset(error,0,sizeof(*error));
  try{return function();}
  catch(const failure &failed){set_error(error,failed.code,failed.metadata,failed.message);return failed.code;}
  catch(const fs::filesystem_error &){set_error(error,READER_BULK_IO,READER_METADATA_OK,"Bulk journal file operation failed");return READER_BULK_IO;}
  catch(...){set_error(error,READER_BULK_IO,READER_METADATA_OK,"Cannot allocate bounded bulk batch state");return READER_BULK_IO;}
}
void copy_text(char *destination,size_t capacity,const std::string &value){
  size_t n=std::min(value.size(),capacity-1);std::memcpy(destination,value.data(),n);destination[n]=0;
}
bool is_id(const std::string &value){return value.size()==32&&value.find_first_not_of("0123456789abcdef")==std::string::npos;}
std::string bounded_text(const char *value,size_t maximum,const char *message){
  if(!value)reject(READER_BULK_ARGUMENT,message);
  size_t n=0;while(n<=maximum&&value[n])++n;
  if(!n||n>maximum)reject(READER_BULK_ARGUMENT,message);
  return std::string(value,n);
}
const char *kind_name(reader_group_kind kind){return kind==READER_GROUP_SHELF?"shelf":kind==READER_GROUP_TAG?"tag":"series";}
bool is_membership(uint64_t action){return action>=READER_BULK_SHELF_ADD;}
bool is_add(uint64_t action){return action==READER_BULK_SHELF_ADD||action==READER_BULK_TAG_ADD||action==READER_BULK_SERIES_ADD;}
reader_group_kind kind_of(uint64_t action){
  return action<=READER_BULK_SHELF_REMOVE?READER_GROUP_SHELF:action<=READER_BULK_TAG_REMOVE?READER_GROUP_TAG:READER_GROUP_SERIES;
}
std::string expected_entity(const batch &b,const item_state &item){
  if(!is_membership(b.action))return item.book_key;
  return std::string(kind_name(kind_of(b.action)))+":"+b.group_id+":"+item.book_key;
}

/* ---- journal encoding: length-prefixed fields, CRC-32 trailer (corruption check, not security) ---- */
uint32_t checksum(const std::vector<unsigned char> &bytes,size_t count){
  uint32_t crc=0xffffffffu;
  for(size_t i=0;i<count;++i){crc^=bytes[i];for(int bit=0;bit<8;++bit)crc=(crc>>1)^((crc&1u)?0xedb88320u:0u);}
  return ~crc;
}
void put_number(std::vector<unsigned char> &bytes,uint64_t value){for(int n=7;n>=0;--n)bytes.push_back((unsigned char)(value>>(n*8)));}
void put_string(std::vector<unsigned char> &bytes,const std::string &value){put_number(bytes,value.size());bytes.insert(bytes.end(),value.begin(),value.end());}
std::vector<unsigned char> encode(const batch &b){
  std::vector<unsigned char> bytes={'E','X','R','B','U','L','K','1'};
  put_number(bytes,b.action);put_number(bytes,b.ordinal_base);put_number(bytes,b.cancelled);
  put_string(bytes,b.database);put_string(bytes,b.batch_id);put_string(bytes,b.group_id);
  put_number(bytes,b.items.size());
  for(const auto &item:b.items){
    put_string(bytes,item.book_key);put_string(bytes,item.entity_key);put_string(bytes,item.revision_id);put_string(bytes,item.message);
    put_number(bytes,item.phase);put_number(bytes,item.outcome);put_number(bytes,item.created);put_number(bytes,item.replayed);
    put_number(bytes,item.heads_known);put_number(bytes,item.metadata);
    put_number(bytes,item.heads.size());for(const auto &head:item.heads)put_string(bytes,head);
  }
  put_number(bytes,checksum(bytes,bytes.size()));
  if(bytes.size()>READER_BULK_JOURNAL_MAX_BYTES)reject(READER_BULK_IO,"Bulk journal exceeds its byte limit");
  return bytes;
}
struct decoder {
  const std::vector<unsigned char> &bytes;size_t at=8;
  uint64_t number(){
    if(at>bytes.size()||bytes.size()-at<8)reject(READER_BULK_CORRUPT,"Truncated bulk journal");
    uint64_t n=0;for(int i=0;i<8;++i)n=(n<<8)|bytes[at++];return n;
  }
  std::string string(size_t maximum){
    uint64_t n=number();
    if(n>maximum||at>bytes.size()||n>bytes.size()-at)reject(READER_BULK_CORRUPT,"Invalid bulk journal field length");
    std::string value((const char *)bytes.data()+at,(size_t)n);at+=(size_t)n;
    if(value.find('\0')!=std::string::npos)reject(READER_BULK_CORRUPT,"NUL in bulk journal field");
    return value;
  }
};
batch decode(const std::vector<unsigned char> &bytes){
  if(bytes.size()<24||bytes.size()>READER_BULK_JOURNAL_MAX_BYTES||std::memcmp(bytes.data(),"EXRBULK1",8))
    reject(READER_BULK_CORRUPT,"Unknown or oversized bulk journal");
  uint64_t stored=0;for(size_t i=bytes.size()-8;i<bytes.size();++i)stored=(stored<<8)|bytes[i];
  if(stored!=checksum(bytes,bytes.size()-8))reject(READER_BULK_CORRUPT,"Bulk journal checksum mismatch");
  std::vector<unsigned char> body(bytes.begin(),bytes.end()-8);
  decoder d{body};batch b;
  b.action=d.number();b.ordinal_base=d.number();b.cancelled=d.number();
  b.database=d.string(32768);b.batch_id=d.string(32);b.group_id=d.string(32);
  uint64_t count=d.number();
  if(b.action>READER_BULK_SERIES_REMOVE||count==0||count>READER_BULK_MAX_BATCH||!is_id(b.batch_id)||(is_membership(b.action)&&!is_id(b.group_id)))
    reject(READER_BULK_CORRUPT,"Invalid bulk journal header");
  for(uint64_t i=0;i<count;++i){
    item_state item;
    item.book_key=d.string(72);item.entity_key=d.string(257);item.revision_id=d.string(32);item.message=d.string(160);
    item.phase=d.number();item.outcome=d.number();item.created=d.number();item.replayed=d.number();
    item.heads_known=d.number();item.metadata=d.number();
    uint64_t heads=d.number();
    if(item.phase>PHASE_DONE||item.outcome>READER_BULK_ITEM_FAILED||heads>READER_BULK_MAX_HEADS||item.book_key.empty())
      reject(READER_BULK_CORRUPT,"Invalid bulk journal item");
    for(uint64_t h=0;h<heads;++h)item.heads.push_back(d.string(32));
    b.items.push_back(std::move(item));
  }
  if(d.at!=body.size())reject(READER_BULK_CORRUPT,"Trailing bytes in bulk journal");
  return b;
}

/* ---- private sidecar file: flushed temporary file + atomic replace ---- */
void sync_directory(const fs::path &file){
#ifndef _WIN32
  int fd=open(file.parent_path().c_str(),O_RDONLY|O_DIRECTORY|O_CLOEXEC);
  if(fd<0)reject(READER_BULK_IO,"Cannot open bulk journal directory for durable publication");
  int result=fsync(fd);close(fd);if(result)reject(READER_BULK_IO,"Cannot synchronize bulk journal directory");
#else
  (void)file;
#endif
}
bool read_file(const fs::path &path,std::vector<unsigned char> &bytes){
#ifdef _WIN32
  HANDLE file=CreateFileW(path.c_str(),GENERIC_READ,FILE_SHARE_READ,nullptr,OPEN_EXISTING,FILE_FLAG_OPEN_REPARSE_POINT,nullptr);
  if(file==INVALID_HANDLE_VALUE){
    DWORD code=GetLastError();
    if(code==ERROR_FILE_NOT_FOUND||code==ERROR_PATH_NOT_FOUND)return false;
    reject(READER_BULK_IO,"Cannot read bulk journal");
  }
  BY_HANDLE_FILE_INFORMATION info{};LARGE_INTEGER size{};
  bool valid=GetFileInformationByHandle(file,&info)&&!(info.dwFileAttributes&(FILE_ATTRIBUTE_DIRECTORY|FILE_ATTRIBUTE_REPARSE_POINT))
    &&GetFileSizeEx(file,&size)&&size.QuadPart>0&&size.QuadPart<=(LONGLONG)READER_BULK_JOURNAL_MAX_BYTES;
  if(!valid){CloseHandle(file);reject(READER_BULK_CORRUPT,"Bulk journal is not a bounded regular file");}
  try{bytes.resize((size_t)size.QuadPart);}catch(...){CloseHandle(file);throw;}
  DWORD n=0;
  bool ok=ReadFile(file,bytes.data(),(DWORD)bytes.size(),&n,nullptr)&&n==(DWORD)bytes.size();CloseHandle(file);
  if(!ok)reject(READER_BULK_IO,"Cannot read complete bulk journal");
#else
  int file=open(path.c_str(),O_RDONLY|O_CLOEXEC|O_NOFOLLOW);
  if(file<0){if(errno==ENOENT)return false;reject(READER_BULK_IO,"Cannot read bulk journal");}
  struct stat info{};
  if(fstat(file,&info)||!S_ISREG(info.st_mode)||info.st_size<=0||(uint64_t)info.st_size>READER_BULK_JOURNAL_MAX_BYTES){
    close(file);reject(READER_BULK_CORRUPT,"Bulk journal is not a bounded regular file");
  }
  try{bytes.resize((size_t)info.st_size);}catch(...){close(file);throw;}
  size_t at=0;
  while(at<bytes.size()){
    ssize_t n=read(file,bytes.data()+at,bytes.size()-at);
    if(n<0&&errno==EINTR)continue;
    if(n<=0){close(file);reject(READER_BULK_IO,"Cannot read complete bulk journal");}
    at+=(size_t)n;
  }
  close(file);
#endif
  return true;
}
void write_file(const fs::path &target,const std::vector<unsigned char> &bytes){
  fs::path temporary=target;temporary+=".tmp";
  std::error_code ec;fs::remove(temporary,ec);
  if(ec)reject(READER_BULK_IO,"Cannot remove unfinished bulk journal publication");
#ifdef _WIN32
  HANDLE file=CreateFileW(temporary.c_str(),GENERIC_WRITE,0,nullptr,CREATE_NEW,FILE_ATTRIBUTE_NORMAL,nullptr);
  if(file==INVALID_HANDLE_VALUE)reject(READER_BULK_IO,"Cannot create bulk journal publication file");
  DWORD n=0;
  bool ok=WriteFile(file,bytes.data(),(DWORD)bytes.size(),&n,nullptr)&&n==(DWORD)bytes.size()&&FlushFileBuffers(file);
  CloseHandle(file);
  if(!ok)reject(READER_BULK_IO,"Cannot durably write bulk journal");
  if(!MoveFileExW(temporary.c_str(),target.c_str(),MOVEFILE_REPLACE_EXISTING|MOVEFILE_WRITE_THROUGH))
    reject(READER_BULK_IO,"Cannot atomically publish bulk journal");
#else
  int file=open(temporary.c_str(),O_WRONLY|O_CREAT|O_EXCL|O_CLOEXEC|O_NOFOLLOW,0600);
  if(file<0)reject(READER_BULK_IO,"Cannot create bulk journal publication file");
  size_t at=0;
  while(at<bytes.size()){
    ssize_t n=write(file,bytes.data()+at,bytes.size()-at);
    if(n<0&&errno==EINTR)continue;
    if(n<=0){close(file);reject(READER_BULK_IO,"Cannot write bulk journal");}
    at+=(size_t)n;
  }
  int flushed=fsync(file);int closed=close(file);
  if(flushed||closed)reject(READER_BULK_IO,"Cannot durably write bulk journal");
  if(rename(temporary.c_str(),target.c_str()))reject(READER_BULK_IO,"Cannot atomically publish bulk journal");
#endif
  sync_directory(target);
}
bool load(const reader_bulk &h,batch &b){
  std::vector<unsigned char> bytes;
  if(!read_file(h.journal,bytes))return false;
  b=decode(bytes);
  if(b.database!=h.database)reject(READER_BULK_CORRUPT,"Bulk journal is bound to another product database");
  return true;
}
void save(const reader_bulk &h,const batch &b){write_file(h.journal,encode(b));}
void remove_journal(const reader_bulk &h){
  std::error_code ec;fs::remove(h.journal,ec);
  if(ec)reject(READER_BULK_IO,"Cannot remove bulk journal");
  sync_directory(h.journal);
}

/* ---- results ---- */
void fill_result(const batch &b,size_t index,reader_bulk_item_result *out){
  const item_state &item=b.items[index];
  std::memset(out,0,sizeof(*out));
  out->struct_size=sizeof(*out);out->index=index;copy_text(out->book_key,sizeof(out->book_key),item.book_key);
  out->outcome=(reader_bulk_item_outcome)item.outcome;
  out->committed=item.outcome==READER_BULK_ITEM_COMMITTED?1:0;
  out->created=(int)item.created;out->replayed=(int)item.replayed;
  out->conflict=(item.outcome==READER_BULK_ITEM_CONFLICT||item.outcome==READER_BULK_ITEM_DEPENDENCY_DELETED)?1:0;
  out->metadata=(reader_metadata_status)item.metadata;
  copy_text(out->entity_key,sizeof(out->entity_key),item.entity_key);
  copy_text(out->revision_id,sizeof(out->revision_id),item.revision_id);
  out->heads_known=(int)item.heads_known;out->head_count=item.heads.size();
  for(size_t i=0;i<item.heads.size()&&i<READER_BULK_MAX_HEADS;++i)copy_text(out->heads[i],sizeof(out->heads[i]),item.heads[i]);
  copy_text(out->message,sizeof(out->message),item.message);
}
void summarize(const batch &b,reader_bulk_summary *out){
  if(!out)return;
  std::memset(out,0,sizeof(*out));
  copy_text(out->batch_id,sizeof(out->batch_id),b.batch_id);
  out->action=(reader_bulk_action)b.action;out->total=b.items.size();out->cancelled=(int)b.cancelled;
  bool complete=true;
  for(const auto &item:b.items){
    if(item.phase!=PHASE_DONE){
      complete=false;
      if(item.outcome!=READER_BULK_ITEM_COMMITTED){++out->not_run;continue;}
    }
    switch(item.outcome){
      case READER_BULK_ITEM_COMMITTED:++out->committed;if(item.created)++out->created;break;
      case READER_BULK_ITEM_UNCHANGED:++out->unchanged;break;
      case READER_BULK_ITEM_CONFLICT:case READER_BULK_ITEM_DEPENDENCY_DELETED:++out->conflicts;break;
      default:++out->failed;break;
    }
  }
  out->complete=complete?1:0;
}
void export_results(const batch &b,reader_bulk_item_result *results,size_t capacity,reader_bulk_summary *summary){
  summarize(b,summary);
  for(size_t i=0;i<b.items.size()&&i<capacity;++i){
    fill_result(b,i,&results[i]);
    if(b.items[i].phase!=PHASE_DONE&&b.items[i].outcome!=READER_BULK_ITEM_COMMITTED){
      results[i].outcome=READER_BULK_ITEM_NOT_RUN;results[i].committed=0;results[i].conflict=0;
    }
  }
}
void notify(const reader_bulk_control *control,reader_bulk_event event,const batch &b,size_t index){
  if(!control||!control->progress)return;
  reader_bulk_item_result item;fill_result(b,index,&item);
  control->progress(control->context,event,index,&item);
}

struct snapshot_deleter {void operator()(reader_metadata_snapshot *value) const {reader_metadata_snapshot_free(value);}};
typedef std::unique_ptr<reader_metadata_snapshot,snapshot_deleter> snapshot_ptr;
enum step {STEP_NEXT=0,STEP_STOP};
struct stop_reason {reader_bulk_status code=READER_BULK_OK;reader_metadata_status metadata=READER_METADATA_OK;std::string message;};

void stop(stop_reason &reason,reader_bulk_status code,reader_metadata_status metadata,const char *message){
  reason.code=code;reason.metadata=metadata;reason.message=message;
}
void finish_item(batch &b,item_state &item,reader_bulk_item_outcome outcome,reader_metadata_status metadata,const std::string &message){
  (void)b;item.phase=PHASE_DONE;item.outcome=outcome;item.metadata=metadata;item.message=message;
}
reader_bulk_item_outcome outcome_for(reader_metadata_status status){
  return status==READER_METADATA_CONFLICT?READER_BULK_ITEM_CONFLICT:status==READER_METADATA_NEEDS_BOOTSTRAP?READER_BULK_ITEM_NEEDS_BOOTSTRAP:READER_BULK_ITEM_FAILED;
}
bool fatal_for_batch(reader_metadata_status status){return status==READER_METADATA_OWNER||status==READER_METADATA_IO;}
void copy_heads(const reader_metadata_view *view,item_state &item){
  item.heads.clear();
  for(size_t i=0;i<view->head_count&&i<READER_BULK_MAX_HEADS;++i)item.heads.emplace_back(view->heads[i]);
  item.heads_known=1;item.entity_key=view->entity_key?view->entity_key:"";
}

/* Complete one pending metadata-owner intent that belongs to the first unfinished item. */
step recover_pending(reader_bulk &h,batch &b,const reader_bulk_control *control,stop_reason &reason){
  reader_metadata_result pending{};reader_metadata_error me{};
  reader_metadata_status status=reader_metadata_pending(h.owner,&pending,&me);
  if(status==READER_METADATA_NO_PENDING)return STEP_NEXT;
  if(status!=READER_METADATA_OK){stop(reason,READER_BULK_METADATA,status,"Cannot inspect the metadata owner's pending intent");return STEP_STOP;}
  size_t index=0;while(index<b.items.size()&&b.items[index].phase==PHASE_DONE)++index;
  if(index==b.items.size()){stop(reason,READER_BULK_FOREIGN_PENDING,status,"Metadata owner holds an intent that is not part of this batch");return STEP_STOP;}
  item_state &item=b.items[index];
  if(expected_entity(b,item)!=pending.command.entity_key||(item.phase==PHASE_STAGED&&item.revision_id!=pending.command.revision_id)){
    stop(reason,READER_BULK_FOREIGN_PENDING,status,"Metadata owner holds an intent that does not match the next batch item");return STEP_STOP;
  }
  reader_metadata_result done{};
  status=reader_metadata_finish_pending(h.owner,&done,&me);
  if(status!=READER_METADATA_OK){stop(reason,READER_BULK_METADATA,status,"Pending batch intent was not completed; it is retained for the next resume");return STEP_STOP;}
  if(item.phase==PHASE_PENDING)item.heads_known=0;
  item.entity_key=pending.command.entity_key;item.revision_id=pending.command.revision_id;
  item.created=done.command.created?1:0;item.replayed=done.command.created?0:1;
  finish_item(b,item,READER_BULK_ITEM_COMMITTED,READER_METADATA_OK,"Recovered staged intent was committed");
  save(h,b);notify(control,READER_BULK_EVENT_ITEM_DONE,b,index);
  return STEP_NEXT;
}

step process_item(reader_bulk &h,batch &b,size_t index,const reader_bulk_control *control,stop_reason &reason){
  item_state &item=b.items[index];
  const bool membership=is_membership(b.action);
  const reader_group_kind kind=kind_of(b.action);
  reader_metadata_error me{};
  reader_metadata_snapshot *raw=nullptr;
  if(membership&&is_add(b.action)){
    /* A group member may not be added for an absent or deleted book. */
    reader_metadata_status known=reader_metadata_prepare_book(h.owner,item.book_key.c_str(),&raw,&me);
    snapshot_ptr book(raw);raw=nullptr;
    const reader_metadata_view *view=book?reader_metadata_snapshot_view(book.get()):nullptr;
    if(fatal_for_batch(known)){stop(reason,READER_BULK_METADATA,known,"Metadata owner failed while checking the book");return STEP_STOP;}
    if(!view||!view->present||view->deleted){
      finish_item(b,item,READER_BULK_ITEM_MISSING,known,"Book is absent or deleted");return STEP_NEXT;
    }
  }
  reader_metadata_status prepared=membership?
    reader_metadata_prepare_membership(h.owner,kind,b.group_id.c_str(),item.book_key.c_str(),&raw,&me):
    reader_metadata_prepare_book(h.owner,item.book_key.c_str(),&raw,&me);
  snapshot_ptr snapshot(raw);
  const reader_metadata_view *view=snapshot?reader_metadata_snapshot_view(snapshot.get()):nullptr;
  if(fatal_for_batch(prepared)){stop(reason,READER_BULK_METADATA,prepared,"Metadata owner failed while preparing an item");return STEP_STOP;}
  if(!view){
    finish_item(b,item,READER_BULK_ITEM_FAILED,prepared,me.message[0]?me.message:"Metadata snapshot was not available");return STEP_NEXT;
  }
  copy_heads(view,item);
  if(!membership&&(!view->present||view->deleted)){
    finish_item(b,item,READER_BULK_ITEM_MISSING,prepared,"Book is absent or deleted");return STEP_NEXT;
  }
  if(view->dependency_deleted){
    finish_item(b,item,READER_BULK_ITEM_DEPENDENCY_DELETED,READER_METADATA_CONFLICT,
      membership?"Target group or book was deleted":"Book dependency was deleted");return STEP_NEXT;
  }
  if(prepared==READER_METADATA_CONFLICT){
    finish_item(b,item,READER_BULK_ITEM_CONFLICT,prepared,"Concurrent metadata heads require explicit resolution");return STEP_NEXT;
  }
  if(prepared==READER_METADATA_NEEDS_BOOTSTRAP){
    finish_item(b,item,READER_BULK_ITEM_NEEDS_BOOTSTRAP,prepared,"Legacy book needs an explicit verified bootstrap");return STEP_NEXT;
  }
  if(prepared!=READER_METADATA_OK){
    finish_item(b,item,READER_BULK_ITEM_FAILED,prepared,me.message[0]?me.message:"Metadata preparation was refused");return STEP_NEXT;
  }

  reader_metadata_result staged{};reader_metadata_status status;
  if(!membership){
    const int target=b.action==READER_BULK_FAVORITE_SET?1:0;
    if(view->book.favorite==target){finish_item(b,item,READER_BULK_ITEM_UNCHANGED,READER_METADATA_OK,"Favorite already has the requested value");return STEP_NEXT;}
    reader_book_command command=view->book;command.operation=READER_COMMAND_PUT;command.favorite=target;
    status=reader_metadata_stage_book(h.owner,snapshot.get(),&command,&staged,&me);
  }else{
    const bool exists=view->present&&!view->deleted;
    reader_membership_command command{READER_COMMAND_PUT,kind,b.group_id.c_str(),item.book_key.c_str(),0};
    if(is_add(b.action)){
      if(exists){finish_item(b,item,READER_BULK_ITEM_UNCHANGED,READER_METADATA_OK,"Book is already a member");return STEP_NEXT;}
      command.operation=view->deleted?READER_COMMAND_RESTORE:READER_COMMAND_PUT;
      if(kind!=READER_GROUP_TAG)command.ordinal=b.ordinal_base+(uint64_t)index;
    }else{
      if(!exists){finish_item(b,item,READER_BULK_ITEM_UNCHANGED,READER_METADATA_OK,"Book is not a member");return STEP_NEXT;}
      if(!view->head_count){finish_item(b,item,READER_BULK_ITEM_FAILED,READER_METADATA_NEEDS_BOOTSTRAP,"Existing membership has no observed head to delete");return STEP_NEXT;}
      command.operation=READER_COMMAND_DELETE;command.ordinal=view->membership.ordinal;
    }
    if(command.operation==READER_COMMAND_RESTORE&&!view->head_count){
      finish_item(b,item,READER_BULK_ITEM_CONFLICT,READER_METADATA_CONFLICT,"Restore requires an observed deleted head");return STEP_NEXT;
    }
    status=reader_metadata_stage_membership(h.owner,snapshot.get(),&command,&staged,&me);
  }
  if(status==READER_METADATA_PENDING){stop(reason,READER_BULK_FOREIGN_PENDING,status,"Metadata owner holds an unrelated pending intent");return STEP_STOP;}
  if(fatal_for_batch(status)){stop(reason,READER_BULK_METADATA,status,"Metadata owner failed while staging an item");return STEP_STOP;}
  if(status!=READER_METADATA_OK){
    finish_item(b,item,outcome_for(status),status,me.message[0]?me.message:"Metadata staging was refused");return STEP_NEXT;
  }
  item.phase=PHASE_STAGED;item.revision_id=staged.command.revision_id;item.entity_key=staged.command.entity_key;
  save(h,b);
  notify(control,READER_BULK_EVENT_STAGED,b,index);

  reader_metadata_result applied{};
  status=reader_metadata_apply_pending(h.owner,&applied,&me);
  if(status!=READER_METADATA_OK){
    /* Nothing committed: remove the unretained intent so the next item can run. */
    reader_metadata_error abandon_error{};
    reader_metadata_status abandoned=reader_metadata_abandon_pending(h.owner,&abandon_error);
    if(abandoned!=READER_METADATA_OK&&abandoned!=READER_METADATA_NO_PENDING){
      stop(reason,READER_BULK_METADATA,abandoned,"Refused intent could not be removed; resume will retry it");return STEP_STOP;
    }
    item.revision_id.clear();
    finish_item(b,item,outcome_for(status),status,me.message[0]?me.message:"Metadata apply was refused");
    save(h,b);return STEP_NEXT;
  }
  item.created=applied.command.created?1:0;
  // Apply is the commit boundary even when clearing the pending intent fails.
  item.outcome=READER_BULK_ITEM_COMMITTED;item.replayed=applied.command.created?0:1;
  notify(control,READER_BULK_EVENT_COMMITTED,b,index);

  reader_metadata_result cleared{};
  status=reader_metadata_finish_pending(h.owner,&cleared,&me);
  if(status!=READER_METADATA_OK){
    stop(reason,READER_BULK_METADATA,status,"Item committed but its pending intent was not cleared; resume will finish it");return STEP_STOP;
  }
  finish_item(b,item,READER_BULK_ITEM_COMMITTED,READER_METADATA_OK,"Committed");
  save(h,b);
  return STEP_NEXT;
}

reader_bulk_status execute(reader_bulk &h,batch &b,const reader_bulk_control *control,reader_bulk_error *error){
  stop_reason reason;
  try{
    b.cancelled=0;
    if(recover_pending(h,b,control,reason)==STEP_NEXT){
      for(size_t index=0;index<b.items.size();++index){
        item_state &item=b.items[index];
        if(item.phase==PHASE_DONE)continue;
        if(item.phase==PHASE_STAGED){
          /* Pending file is gone: either the intent committed and was cleaned, or it vanished uncommitted. */
          char *wire=nullptr;size_t bytes=0;reader_revision_info info{};reader_revision_error re{};
          reader_revision_status found=reader_revision_get(h.revisions,item.revision_id.c_str(),&wire,&bytes,&info,&re);
          reader_revision_bytes_free(wire);
          if(found==READER_REV_OK){
            item.created=0;item.replayed=1;
            finish_item(b,item,READER_BULK_ITEM_COMMITTED,READER_METADATA_OK,"Recovered committed item");
            save(h,b);notify(control,READER_BULK_EVENT_ITEM_DONE,b,index);continue;
          }
          if(found!=READER_REV_NOT_FOUND){stop(reason,READER_BULK_METADATA,READER_METADATA_REVISION,"Cannot verify the staged revision");break;}
          item.phase=PHASE_PENDING;item.revision_id.clear();item.heads.clear();item.heads_known=0;
        }
        if(control&&control->cancelled&&control->cancelled(control->context)){
          b.cancelled=1;save(h,b);
          return READER_BULK_CANCELLED;
        }
        if(process_item(h,b,index,control,reason)==STEP_STOP)break;
        notify(control,READER_BULK_EVENT_ITEM_DONE,b,index);
      }
    }
    save(h,b);
  }catch(const failure &failed){
    set_error(error,failed.code,failed.metadata,failed.message);return failed.code;
  }catch(const fs::filesystem_error &){
    set_error(error,READER_BULK_IO,READER_METADATA_OK,"Bulk journal file operation failed");return READER_BULK_IO;
  }catch(...){
    set_error(error,READER_BULK_IO,READER_METADATA_OK,"Cannot allocate bounded bulk batch state");return READER_BULK_IO;
  }
  if(reason.code!=READER_BULK_OK){set_error(error,reason.code,reason.metadata,reason.message);return reason.code;}
  return READER_BULK_OK;
}

void validate_results(reader_bulk_item_result *results,size_t capacity,size_t count){
  if(!results)reject(READER_BULK_ARGUMENT,"Missing result array");
  if(capacity<count)reject(READER_BULK_CAPACITY,"Result array is smaller than the batch");
}
}

extern "C" reader_bulk_status reader_bulk_open(reader_metadata_owner *owner,const char *product_path,const char *journal_path,
    reader_bulk **out,reader_bulk_error *error){
  if(out)*out=nullptr;
  return call(error,[&]{
    if(!out||!owner)reject(READER_BULK_ARGUMENT,"Missing metadata owner or bulk handle output");
    auto handle=std::make_unique<reader_bulk>();
    handle->owner=owner;
    handle->database=fs::weakly_canonical(fs::absolute(fs::u8path(bounded_text(product_path,32768,"Missing product database path")))).u8string();
    fs::path requested=fs::absolute(fs::u8path(bounded_text(journal_path,32768,"Missing bulk journal path")));
    handle->journal=fs::weakly_canonical(requested.parent_path())/requested.filename();
    if(handle->journal==fs::u8path(handle->database))reject(READER_BULK_ARGUMENT,"Bulk journal must be separate from the product database");
    reader_revision_error re{};
    if(reader_revisions_open(handle->database.c_str(),&handle->revisions,&re)!=READER_REV_OK)
      reject(READER_BULK_METADATA,"Cannot open the product revision store",READER_METADATA_REVISION);
    *out=handle.release();return READER_BULK_OK;
  });
}
extern "C" reader_bulk_status reader_bulk_close(reader_bulk **handle,reader_bulk_error *error){
  return call(error,[&]{
    if(!handle)reject(READER_BULK_ARGUMENT,"Missing bulk handle pointer");
    if(!*handle)return READER_BULK_OK;
    if((*handle)->thread!=std::this_thread::get_id()||(*handle)->active)reject(READER_BULK_OWNER,"Bulk close requires its creating worker without reentry");
    delete *handle;*handle=nullptr;return READER_BULK_OK;
  });
}
extern "C" reader_bulk_status reader_bulk_run(reader_bulk *handle,const reader_bulk_request *request,reader_bulk_item_result *results,
    size_t capacity,reader_bulk_summary *summary,reader_bulk_error *error){
  return call(error,[&]{
    guard lock(handle);
    if(!request||request->struct_size!=sizeof(*request)||(uint64_t)request->action>READER_BULK_SERIES_REMOVE)reject(READER_BULK_ARGUMENT,"Invalid bulk request");
    if(!request->book_keys||request->book_count==0||request->book_count>READER_BULK_MAX_BATCH)reject(READER_BULK_ARGUMENT,"Bulk batch must select 1..100 books");
    validate_results(results,capacity,request->book_count);
    batch b;b.database=handle->database;b.action=(uint64_t)request->action;
    if(is_membership(b.action)){
      b.group_id=bounded_text(request->group_id,32,"Missing group identity");
      if(!is_id(b.group_id))reject(READER_BULK_ARGUMENT,"Invalid global group identity");
      if(is_add(b.action)&&kind_of(b.action)!=READER_GROUP_TAG){
        if(request->ordinal_base>(uint64_t)INT64_MAX-READER_BULK_MAX_BATCH)reject(READER_BULK_ARGUMENT,"Ordinal base is too large");
        b.ordinal_base=request->ordinal_base;
      }
    }
    for(size_t i=0;i<request->book_count;++i){
      item_state item;item.book_key=bounded_text(request->book_keys[i],72,"Invalid book key");
      for(const auto &earlier:b.items)if(earlier.book_key==item.book_key)reject(READER_BULK_ARGUMENT,"Duplicate book key in one batch");
      b.items.push_back(std::move(item));
    }
    std::vector<unsigned char> existing;
    if(read_file(handle->journal,existing))reject(READER_BULK_JOURNAL_ACTIVE,"An earlier bulk journal must be resumed, acknowledged or abandoned");
    reader_metadata_result pending{};reader_metadata_error me{};
    reader_metadata_status pending_status=reader_metadata_pending(handle->owner,&pending,&me);
    if(pending_status==READER_METADATA_OK)reject(READER_BULK_FOREIGN_PENDING,"Metadata owner already holds a pending intent",pending_status);
    if(pending_status!=READER_METADATA_NO_PENDING)reject(READER_BULK_METADATA,"Cannot inspect the metadata owner's pending intent",pending_status);
    char id[33];reader_revision_error re{};
    if(reader_revision_new_id(id,&re)!=READER_REV_OK)reject(READER_BULK_METADATA,"Cannot allocate a batch identity",READER_METADATA_REVISION);
    b.batch_id=id;
    save(*handle,b);
    reader_bulk_status status=execute(*handle,b,&request->control,error);
    export_results(b,results,capacity,summary);
    return status;
  });
}
extern "C" reader_bulk_status reader_bulk_resume(reader_bulk *handle,const reader_bulk_control *control,reader_bulk_item_result *results,
    size_t capacity,reader_bulk_summary *summary,reader_bulk_error *error){
  return call(error,[&]{
    guard lock(handle);
    batch b;
    if(!load(*handle,b))reject(READER_BULK_NO_JOURNAL,"No bulk journal to resume");
    validate_results(results,capacity,b.items.size());
    bool complete=true;for(const auto &item:b.items)if(item.phase!=PHASE_DONE)complete=false;
    reader_bulk_status status=READER_BULK_OK;
    if(!complete)status=execute(*handle,b,control,error);
    export_results(b,results,capacity,summary);
    return status;
  });
}
extern "C" reader_bulk_status reader_bulk_inspect(reader_bulk *handle,reader_bulk_item_result *results,size_t capacity,
    reader_bulk_summary *summary,reader_bulk_error *error){
  return call(error,[&]{
    guard lock(handle);
    batch b;
    if(!load(*handle,b))reject(READER_BULK_NO_JOURNAL,"No bulk journal");
    validate_results(results,capacity,b.items.size());
    export_results(b,results,capacity,summary);
    return READER_BULK_OK;
  });
}
extern "C" reader_bulk_status reader_bulk_acknowledge(reader_bulk *handle,reader_bulk_error *error){
  return call(error,[&]{
    guard lock(handle);
    batch b;
    if(!load(*handle,b))reject(READER_BULK_NO_JOURNAL,"No bulk journal to acknowledge");
    for(const auto &item:b.items)if(item.phase!=PHASE_DONE)reject(READER_BULK_ARGUMENT,"Bulk batch is not complete; resume or abandon it");
    remove_journal(*handle);return READER_BULK_OK;
  });
}
extern "C" reader_bulk_status reader_bulk_abandon(reader_bulk *handle,reader_bulk_error *error){
  return call(error,[&]{
    guard lock(handle);
    std::vector<unsigned char> existing;
    bool present;
    try{present=read_file(handle->journal,existing);}catch(const failure &){present=true;}
    if(!present)reject(READER_BULK_NO_JOURNAL,"No bulk journal to abandon");
    reader_metadata_result pending{};reader_metadata_error me{};
    reader_metadata_status status=reader_metadata_pending(handle->owner,&pending,&me);
    if(status==READER_METADATA_OK)reject(READER_BULK_FOREIGN_PENDING,"Metadata owner holds an intent; resume it instead",status);
    if(status!=READER_METADATA_NO_PENDING)reject(READER_BULK_METADATA,"Cannot inspect the metadata owner's pending intent",status);
    remove_journal(*handle);return READER_BULK_OK;
  });
}
