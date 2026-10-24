/* SPDX-License-Identifier: MIT */
/* Installed-package consumer: a host-shaped worker that seeds a product catalog
 * and drives reader_bulk through its public C API. All arguments are ASCII. */
#include <reader_bulk.h>
#include <catalog.h>
#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <iostream>
#include <map>
#include <sstream>
#include <string>
#include <thread>
#include <vector>

namespace {
std::string quote(const std::string &s){
  std::string out="\"";
  for(unsigned char c:s){
    if(c=='\"'||c=='\\'){out+='\\';out+=(char)c;}
    else if(c<32){char b[8];std::snprintf(b,sizeof(b),"\\u%04x",c);out+=b;}
    else out+=(char)c;
  }
  return out+'\"';
}
std::string book_key(size_t index){char b[80];std::snprintf(b,sizeof(b),"txt:%064zx",index+1);return b;}
std::string book_sha(size_t index){char b[80];std::snprintf(b,sizeof(b),"%064zx",index+1);return b;}

struct options {
  std::map<std::string,std::string> values;
  std::string get(const std::string &name,const std::string &fallback="") const {auto it=values.find(name);return it==values.end()?fallback:it->second;}
  long number(const std::string &name,long fallback) const {auto it=values.find(name);return it==values.end()?fallback:std::strtol(it->second.c_str(),nullptr,10);}
};

/* Test hooks run inside progress/control callbacks, exactly where a host UI or a
 * second writer could interfere. They never call the bulk handle or the owner. */
struct hooks {
  options opt;
  std::string db;
  long done=0;
  void pause_forever(){
    std::ofstream marker(opt.get("marker"));marker<<"ready";marker.close();
    for(;;)std::this_thread::sleep_for(std::chrono::seconds(1));
  }
  void fork_book(size_t index){
    reader_revisions *store=nullptr;reader_revision_error e{};
    if(reader_revisions_open(db.c_str(),&store,&e)!=READER_REV_OK)std::exit(21);
    std::string key=book_key(index),sha=book_sha(index),title="concurrent-"+std::to_string(index);
    char id[33];if(reader_revision_new_id(id,&e)!=READER_REV_OK)std::exit(28);
    /* A revision received from another device: no parents, concurrent with the local head. */
    std::string wire="{\"version\":1,\"id\":\""+std::string(id)+"\",\"entity_kind\":\"book\",\"entity_key\":\""+key
      +"\",\"operation\":\"put\",\"location_kind\":\"none\",\"parents\":[],\"payload\":{\"format\":\"txt\",\"source_sha256\":\""+sha
      +"\",\"source_bytes\":"+std::to_string(100+index)+",\"title\":\""+title+"\",\"author\":\"author\",\"favorite\":false}}";
    reader_revision_info info{};int created=0;
    if(reader_revision_receive(store,wire.data(),wire.size(),nullptr,&info,&created,&e)!=READER_REV_OK||!created){std::fprintf(stderr,"fork refused: %d %s\n",(int)e.code,e.message);std::exit(22);}
    if(reader_revisions_close(&store,&e)!=READER_REV_OK)std::exit(23);
  }
  static int collect(void *context,const reader_revision_head *head){
    static_cast<std::vector<std::string> *>(context)->push_back(head->revision_id);return 0;
  }
  void delete_group(const std::string &id,reader_group_kind kind){
    reader_revisions *store=nullptr;reader_revision_error e{};
    if(reader_revisions_open(db.c_str(),&store,&e)!=READER_REV_OK)std::exit(24);
    std::vector<std::string> heads;reader_revision_state state{};
    const char *name=kind==READER_GROUP_SHELF?"shelf":kind==READER_GROUP_TAG?"tag":"series";
    if(reader_revision_heads(store,name,id.c_str(),collect,&heads,&state,&e)!=READER_REV_OK||heads.empty())std::exit(25);
    std::vector<const char *> pointers;for(const auto &h:heads)pointers.push_back(h.c_str());
    reader_command_context context{store,nullptr,pointers.data(),pointers.size()};
    reader_group_command input{READER_COMMAND_DELETE,kind,id.c_str(),"",nullptr,0};
    reader_command_result result{};reader_command_error ce{};
    if(reader_command_apply_group(&context,&input,&result,&ce)!=READER_COMMAND_OK)std::exit(26);
    if(reader_revisions_close(&store,&e)!=READER_REV_OK)std::exit(27);
  }
};
void on_progress(void *context,reader_bulk_event event,size_t index,const reader_bulk_item_result *){
  auto *h=static_cast<hooks *>(context);
  const std::string pause=h->opt.get("pause");           // staged:K | committed:K
  if(!pause.empty()){
    size_t colon=pause.find(':');
    std::string name=pause.substr(0,colon);long at=std::strtol(pause.c_str()+colon+1,nullptr,10);
    if((long)index==at&&((event==READER_BULK_EVENT_STAGED&&name=="staged")||(event==READER_BULK_EVENT_COMMITTED&&name=="committed")))h->pause_forever();
  }
  if(event!=READER_BULK_EVENT_ITEM_DONE)return;
  ++h->done;
  long after=h->opt.number("interfere_after",-1);
  if((long)index==after){
    long fork=h->opt.number("fork_book",-1);
    if(fork>=0)h->fork_book((size_t)fork);
    std::string group=h->opt.get("delete_group");
    if(!group.empty())h->delete_group(group,(reader_group_kind)h->opt.number("delete_kind",0));
  }
}
int on_cancel(void *context){
  auto *h=static_cast<hooks *>(context);
  long after=h->opt.number("cancel_after",-1);
  return after>=0&&h->done>=after;
}

void print_result(reader_bulk_status status,const reader_bulk_error &error,const reader_bulk_summary &summary,
    const std::vector<reader_bulk_item_result> &items,size_t count,const std::string &extra=""){
  std::ostringstream o;
  o<<"{\"status\":"<<status<<",\"metadata\":"<<error.metadata<<",\"error\":"<<quote(error.message);
  o<<",\"summary\":{\"batch_id\":"<<quote(summary.batch_id)<<",\"action\":"<<summary.action<<",\"total\":"<<summary.total
   <<",\"committed\":"<<summary.committed<<",\"created\":"<<summary.created<<",\"unchanged\":"<<summary.unchanged
   <<",\"conflicts\":"<<summary.conflicts<<",\"failed\":"<<summary.failed<<",\"not_run\":"<<summary.not_run
   <<",\"complete\":"<<summary.complete<<",\"cancelled\":"<<summary.cancelled<<"},\"items\":[";
  for(size_t i=0;i<count&&i<items.size();++i){
    const auto &r=items[i];
    if(i)o<<',';
    o<<"{\"index\":"<<r.index<<",\"book\":"<<quote(r.book_key)<<",\"outcome\":"<<r.outcome<<",\"committed\":"<<r.committed
     <<",\"created\":"<<r.created<<",\"replayed\":"<<r.replayed<<",\"conflict\":"<<r.conflict<<",\"metadata\":"<<r.metadata
     <<",\"entity\":"<<quote(r.entity_key)<<",\"revision\":"<<quote(r.revision_id)<<",\"heads_known\":"<<r.heads_known<<",\"heads\":[";
    for(size_t h=0;h<r.head_count&&h<READER_BULK_MAX_HEADS;++h){if(h)o<<',';o<<quote(r.heads[h]);}
    o<<"],\"message\":"<<quote(r.message)<<'}';
  }
  o<<"]"<<extra<<"}";
  std::cout<<o.str()<<std::endl;
}

std::string create_group(reader_metadata_owner *owner,reader_group_kind kind,const std::string &name,const std::string &parent,uint64_t ordinal){
  reader_metadata_snapshot *snapshot=nullptr;reader_metadata_error e{};
  if(reader_metadata_prepare_group(owner,kind,"",&snapshot,&e)!=READER_METADATA_OK)std::exit(31);
  reader_group_command input{READER_COMMAND_PUT,kind,"",name.c_str(),parent.c_str(),ordinal};
  reader_metadata_result staged{};
  if(reader_metadata_stage_group(owner,snapshot,&input,&staged,&e)!=READER_METADATA_OK)std::exit(32);
  reader_metadata_snapshot_free(snapshot);
  reader_metadata_result done{};
  if(reader_metadata_finish_pending(owner,&done,&e)!=READER_METADATA_OK)std::exit(33);
  return done.command.entity_key;
}
std::string id_array(const std::vector<std::string> &ids){
  std::string out="[";for(size_t i=0;i<ids.size();++i){if(i)out+=',';out+=quote(ids[i]);}return out+"]";
}
int seed(const std::string &db,const std::string &pending,size_t count,bool legacy){
  reader_catalog *catalog=nullptr;reader_catalog_error ce{};
  if(reader_catalog_open(db.c_str(),&catalog,&ce))return 3;
  for(size_t i=0;i<count;++i){
    std::string sha=book_sha(i),title="book-"+std::to_string(i),author="author-"+std::to_string(i);
    reader_catalog_book book{"txt",sha.c_str(),title.c_str(),author.c_str(),title.c_str(),"reflow_global",(uint64_t)(100+i),(int64_t)(1000+i),0};
    if(reader_catalog_attach(catalog,&book,&ce))return 4;
  }
  if(legacy){
    /* One catalog-only book that never receives retained history. */
    std::string sha=book_sha(count),title="legacy-book";
    reader_catalog_book book{"txt",sha.c_str(),title.c_str(),"legacy-author",title.c_str(),"reflow_global",(uint64_t)(100+count),(int64_t)(1000+count),0};
    if(reader_catalog_attach(catalog,&book,&ce))return 4;
  }
  if(reader_catalog_close(&catalog,&ce))return 5;
  reader_metadata_owner *owner=nullptr;reader_metadata_error e{};
  if(reader_metadata_open(db.c_str(),pending.c_str(),&owner,&e)!=READER_METADATA_OK)return 6;
  for(size_t i=0;i<count;++i){
    std::string key=book_key(i),sha=book_sha(i);
    reader_metadata_snapshot *snapshot=nullptr;
    reader_metadata_status status=reader_metadata_prepare_book(owner,key.c_str(),&snapshot,&e);
    if(status!=READER_METADATA_NEEDS_BOOTSTRAP){reader_metadata_snapshot_free(snapshot);return 7;}
    reader_metadata_verified_source source{"txt",sha.c_str(),(uint64_t)(100+i)};
    reader_metadata_result staged{},done{};
    if(reader_metadata_stage_bootstrap(owner,snapshot,&source,&staged,&e)!=READER_METADATA_OK){reader_metadata_snapshot_free(snapshot);return 8;}
    reader_metadata_snapshot_free(snapshot);
    if(reader_metadata_finish_pending(owner,&done,&e)!=READER_METADATA_OK)return 9;
  }
  std::vector<std::string> shelves,tags,series;
  for(int i=0;i<3;++i)shelves.push_back(create_group(owner,READER_GROUP_SHELF,"shelf-"+std::to_string(i),"",(uint64_t)(i+1)));
  for(int i=0;i<3;++i)tags.push_back(create_group(owner,READER_GROUP_TAG,"tag-"+std::to_string(i),"",0));
  for(int i=0;i<2;++i)series.push_back(create_group(owner,READER_GROUP_SERIES,"series-"+std::to_string(i),"",0));
  if(reader_metadata_close(&owner,&e)!=READER_METADATA_OK)return 10;
  std::cout<<"{\"status\":0,\"books\":"<<count<<",\"shelves\":"<<id_array(shelves)<<",\"tags\":"<<id_array(tags)
           <<",\"series\":"<<id_array(series)<<"}"<<std::endl;
  return 0;
}
}

int main(int argc,char **argv){
  if(argc<5)return 2;
  std::string mode=argv[1],db=argv[2],pending=argv[3],journal=argv[4];
  options opt;
  for(int i=5;i<argc;++i){
    std::string arg=argv[i];size_t eq=arg.find('=');
    if(eq==std::string::npos)return 2;
    opt.values[arg.substr(0,eq)]=arg.substr(eq+1);
  }
  if(mode=="seed")return seed(db,pending,(size_t)opt.number("count",10),opt.number("legacy",0)!=0);

  reader_metadata_owner *owner=nullptr;reader_metadata_error me{};
  if(reader_metadata_open(db.c_str(),pending.c_str(),&owner,&me)!=READER_METADATA_OK){std::cout<<"{\"status\":-1,\"error\":"<<quote(me.message)<<"}"<<std::endl;return 0;}
  reader_bulk *bulk=nullptr;reader_bulk_error be{};
  if(reader_bulk_open(owner,db.c_str(),journal.c_str(),&bulk,&be)!=READER_BULK_OK){std::cout<<"{\"status\":-2,\"error\":"<<quote(be.message)<<"}"<<std::endl;return 0;}

  hooks h;h.opt=opt;h.db=db;
  reader_bulk_control control{&h,on_cancel,on_progress};
  std::vector<reader_bulk_item_result> items(READER_BULK_MAX_BATCH);
  reader_bulk_summary summary{};
  reader_bulk_status status=READER_BULK_OK;size_t count=0;std::string extra;
  if(mode=="run"){
    std::vector<std::string> keys;
    size_t start=(size_t)opt.number("start",0),n=(size_t)opt.number("count",1);
    long stride=opt.number("stride",1);
    for(size_t i=0;i<n;++i)keys.push_back(book_key(start+i*(size_t)stride));
    std::vector<std::string> extra_keys;std::string list=opt.get("keys");
    std::vector<const char *> pointers;
    if(!list.empty()){
      std::stringstream stream(list);std::string token;
      while(std::getline(stream,token,','))extra_keys.push_back(token);
      for(const auto &k:extra_keys)pointers.push_back(k.c_str());
    }else for(const auto &k:keys)pointers.push_back(k.c_str());
    std::string group=opt.get("group");
    reader_bulk_request request{sizeof(request),(reader_bulk_action)opt.number("action",0),
      group.empty()?nullptr:group.c_str(),(uint64_t)opt.number("ordinal",0),
      pointers.data(),pointers.size(),control};
    if(opt.get("no_results")=="1"){
      status=reader_bulk_run(bulk,&request,items.data(),0,&summary,&be);
    }else status=reader_bulk_run(bulk,&request,items.data(),items.size(),&summary,&be);
    count=pointers.size();
  }else if(mode=="resume"){
    status=reader_bulk_resume(bulk,&control,items.data(),items.size(),&summary,&be);count=summary.total;
  }else if(mode=="inspect"){
    status=reader_bulk_inspect(bulk,items.data(),items.size(),&summary,&be);count=summary.total;
  }else if(mode=="ack"){
    status=reader_bulk_acknowledge(bulk,&be);
  }else if(mode=="abandon"){
    status=reader_bulk_abandon(bulk,&be);
  }else if(mode=="foreign"){
    /* An unrelated typed edit is staged in the owner; a batch must refuse to touch it. */
    reader_metadata_snapshot *snapshot=nullptr;
    if(reader_metadata_prepare_group(owner,READER_GROUP_TAG,"",&snapshot,&me)!=READER_METADATA_OK)return 41;
    reader_group_command input{READER_COMMAND_PUT,READER_GROUP_TAG,"","foreign tag",nullptr,0};
    reader_metadata_result staged{};
    if(reader_metadata_stage_group(owner,snapshot,&input,&staged,&me)!=READER_METADATA_OK)return 42;
    reader_metadata_snapshot_free(snapshot);
    std::string key=book_key(0);const char *keys[1]={key.c_str()};
    reader_bulk_request request{sizeof(request),READER_BULK_FAVORITE_SET,nullptr,0,keys,1,control};
    status=reader_bulk_run(bulk,&request,items.data(),items.size(),&summary,&be);count=1;
    reader_metadata_error abandon_error{};
    if(reader_metadata_abandon_pending(owner,&abandon_error)!=READER_METADATA_OK)return 43;
  }else if(mode=="wrong-thread"){
    std::string key=book_key(0);const char *keys[1]={key.c_str()};
    reader_bulk_request request{sizeof(request),READER_BULK_FAVORITE_SET,nullptr,0,keys,1,control};
    std::thread other([&]{status=reader_bulk_run(bulk,&request,items.data(),items.size(),&summary,&be);});
    other.join();count=0;
  }else if(mode=="bad-request"){
    /* Each invalid request returns ARGUMENT without touching the journal. */
    std::string key=book_key(0);const char *keys[2]={key.c_str(),key.c_str()};
    int refused=0;
    reader_bulk_request request{sizeof(request),READER_BULK_FAVORITE_SET,nullptr,0,keys,2,control};
    if(reader_bulk_run(bulk,&request,items.data(),items.size(),&summary,&be)==READER_BULK_ARGUMENT)++refused; /* duplicate */
    request.book_count=0;
    if(reader_bulk_run(bulk,&request,items.data(),items.size(),&summary,&be)==READER_BULK_ARGUMENT)++refused; /* empty */
    request.book_count=101;
    if(reader_bulk_run(bulk,&request,items.data(),items.size(),&summary,&be)==READER_BULK_ARGUMENT)++refused; /* over the hard cap */
    request.book_count=1;request.action=READER_BULK_SHELF_ADD;request.group_id="not-an-id";
    if(reader_bulk_run(bulk,&request,items.data(),items.size(),&summary,&be)==READER_BULK_ARGUMENT)++refused; /* group id */
    request.group_id="00000000000000000000000000000000";request.ordinal_base=(uint64_t)INT64_MAX;
    if(reader_bulk_run(bulk,&request,items.data(),items.size(),&summary,&be)==READER_BULK_ARGUMENT)++refused; /* ordinal */
    request.action=READER_BULK_FAVORITE_SET;request.group_id=nullptr;request.ordinal_base=0;
    if(reader_bulk_run(bulk,&request,items.data(),0,&summary,&be)==READER_BULK_CAPACITY)++refused;            /* capacity */
    request.struct_size=1;
    if(reader_bulk_run(bulk,&request,items.data(),items.size(),&summary,&be)==READER_BULK_ARGUMENT)++refused; /* struct size */
    extra=",\"refused\":"+std::to_string(refused);
    status=READER_BULK_OK;
  }else return 2;

  reader_bulk_error closed{};
  if(reader_bulk_close(&bulk,&closed)!=READER_BULK_OK)return 6;
  reader_metadata_error me2{};
  if(reader_metadata_close(&owner,&me2)!=READER_METADATA_OK)return 7;
  print_result(status,be,summary,items,count,extra);
  return 0;
}
