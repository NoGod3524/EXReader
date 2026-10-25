#include <reader_commands.h>
#include <reader_sync.h>
#include <algorithm>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <sstream>
#include <string>
#include <vector>
#include <thread>
#include <cstring>
#include <stdexcept>
namespace fs=std::filesystem;
static void need(bool yes,const char *why){if(!yes)throw std::runtime_error(why);}
static std::string read(const fs::path &p){std::ifstream f(p,std::ios::binary);need((bool)f,"read wire");std::ostringstream s;s<<f.rdbuf();return s.str();}
static void write(const fs::path &p,const std::string &s){std::ofstream f(p,std::ios::binary);f.write(s.data(),s.size());need((bool)f,"write exported wire");}
static size_t pending(reader_revisions *s){size_t count=0;need(reader_revision_outbox_raw_v3(s,100,[](void *p,const reader_revision_outbox_row *){++*static_cast<size_t *>(p);return 0;},&count,nullptr)==READER_REV_OK,"raw outbox");return count;}
static std::string retained(reader_revisions *s,const char *id){char *w=nullptr;size_t n=0;need(reader_revision_get_raw_v3(s,id,&w,&n,nullptr,nullptr)==READER_REV_OK,"raw get");std::string r(w,n);reader_revision_bytes_free(w);return r;}
int main(int argc,char **argv){try{
  if(argc!=4)return 2;std::string mode=argv[1];fs::path work=fs::u8path(argv[2]),packet=fs::u8path(argv[3]);fs::create_directories(work);reader_revisions *s=nullptr;need(reader_revisions_open_raw_v3((work/"catalog.sqlite").u8string().c_str(),&s,nullptr)==READER_REV_OK,"raw open");
  std::vector<fs::path> files;for(auto &file:fs::directory_iterator(packet))if(file.path().extension()==".json")files.push_back(file.path());std::sort(files.begin(),files.end());
  std::string book="pdf:5627a430fa04cbe11d38eb2682e336ef21e147d445753ed46ed11a7d5e3167cc";
  if(mode=="seed"){
    reader_command_context c{};c.store=s;c.revision_id="00000000000000000000000000000001";reader_book_command b{};b.operation=READER_COMMAND_PUT;b.book_key=book.c_str();b.format="pdf";b.source_sha256=book.c_str()+4;b.source_bytes=8845;b.title="actual PDF";b.author="";b.sort_title="actual PDF";reader_command_result r{};reader_command_error error{};
    need(reader_command_apply_book_raw_v3(&c,&b,&r,&error)==READER_COMMAND_OK&&r.created&&r.applied,error.message);
    need(retained(s,c.revision_id)==read(packet/(std::string(c.revision_id)+".json")),"typed bootstrap preserves original real SDK book wire");
    for(auto &p:files){auto wire=read(p);reader_revision_info info{};need(reader_revision_validate_raw_v3(s,wire.data(),wire.size(),nullptr,&info,nullptr)==READER_REV_OK,"source actual wire validates");if(!std::strcmp(info.entity_kind,"book"))continue;int made=0;need(reader_revision_local_raw_v3(s,wire.data(),wire.size(),&info,&made,nullptr)==READER_REV_OK&&made,"queue exact actual reading graph");}
    c.revision_id="00000000000000000000000000001000";reader_group_command group{};group.kind=READER_GROUP_TAG;group.operation=READER_COMMAND_PUT;group.id="dddddddddddddddddddddddddddddddd";group.name="raw store tag";
    need(reader_command_apply_group_raw_v3(&c,&group,&r,&error)==READER_COMMAND_OK&&r.created&&r.applied,error.message);
    c.revision_id="00000000000000000000000000001001";reader_membership_command membership{};membership.kind=READER_GROUP_TAG;membership.operation=READER_COMMAND_PUT;membership.group_id=group.id;membership.book_key=book.c_str();need(reader_command_apply_membership_raw_v3(&c,&membership,&r,&error)==READER_COMMAND_OK&&r.created&&r.applied,error.message);
    size_t before=pending(s);c.revision_id="00000000000000000000000000002000";group.id="eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee";need(reader_command_apply_group(&c,&group,&r,&error)!=READER_COMMAND_OK&&!r.created&&pending(s)==before,"legacy command refuses raw store without writes");
    reader_revision_status wrong=READER_REV_OK;std::thread t([&]{reader_revision_state state{};wrong=reader_revision_heads_raw_v3(s,"book",book.c_str(),nullptr,nullptr,&state,nullptr);});t.join();need(wrong==READER_REV_OWNER,"raw store still requires its creating thread");
    fs::create_directories(work/"expected");struct sink{fs::path path;size_t count=0;}out{work/"expected"};need(reader_revision_outbox_raw_v3(s,100,[](void *p,const reader_revision_outbox_row *row){auto &o=*static_cast<sink *>(p);write(o.path/(std::string(row->info.revision_id)+".json"),std::string(row->wire,row->info.bytes));++o.count;return 0;},&out,nullptr)==READER_REV_OK&&out.count==files.size()+2,"complete actual graph plus typed metadata exported");
    std::cout<<"{\"accepted\":true,\"queued\":"<<out.count<<",\"owner_refused\":true,\"bootstrap_exact\":true}"<<std::endl;
  }else if(mode=="check"){
    for(auto &p:files){auto wire=read(p);reader_revision_info info{};need(reader_revision_validate_raw_v3(s,wire.data(),wire.size(),nullptr,&info,nullptr)==READER_REV_OK,"expected wire validates");need(retained(s,info.revision_id)==wire,"received wire bytes identical");}
    need(pending(s)==0,"remote reception did not enqueue");uint64_t bytes=0;need(reader_revision_book_identity_raw_v3(s,book.c_str(),&bytes,nullptr)==READER_REV_OK&&bytes==8845,"immutable actual book identity preserved");std::cout<<"{\"accepted\":true,\"received\":"<<files.size()<<",\"outbox\":0}"<<std::endl;
  }else return 2;
  need(reader_revisions_close(&s,nullptr)==READER_REV_OK,"owner close");return 0;
}catch(const std::exception &e){std::cerr<<e.what()<<std::endl;return 1;}}
