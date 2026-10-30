// SPDX-License-Identifier: MIT
// Actions-only installed API regression. Synthetic typed-command catalog, not GTK/SDK-original evidence.
#include <reader_commands.h>
#include <catalog.h>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>
static void need(bool value,const char *why){if(!value)throw std::runtime_error(why);}

#include <filesystem>
#include <fstream>
#include <sstream>
static std::string jq(const std::string &s){
  static const char h[]="0123456789abcdef"; std::string o="\"";
  for(unsigned char c:s){
    if(c=='"')o+="\\\"";else if(c=='\\')o+="\\\\";
    else if(c<32){o+="\\u00";o+=h[c>>4];o+=h[c&15];}
    else o+=static_cast<char>(c);
  }return o+'"';
}
static std::string jp(const char *s){return s?jq(s):"null";}
struct receipts {
  std::ofstream calls,setup;
  explicit receipts(const char *database){
    auto dir=std::filesystem::path(database).parent_path();
    calls.exceptions(std::ios::failbit|std::ios::badbit);
    setup.exceptions(std::ios::failbit|std::ios::badbit);
    calls.open(dir/"calls.jsonl",std::ios::binary|std::ios::trunc);
    setup.open(dir/"setup.jsonl",std::ios::binary|std::ios::trunc);
  }
  static void line(std::ofstream &out,const std::string &s){out<<s<<'\n';out.flush();}
  void close(){calls.flush();setup.flush();calls.close();setup.close();}
};

struct rows {std::vector<std::string> keys;std::vector<int> deleted_flags;bool all_deleted=true;};
static int collect(void *p,const reader_catalog_row *row){auto &r=*static_cast<rows *>(p);r.keys.emplace_back(row->book_key);r.deleted_flags.push_back(row->deleted);r.all_deleted=r.all_deleted&&row->deleted;return 0;}

static void call_receipt(receipts &out,unsigned seq,const char *id,const char *api,
  const char *after,int limit,const char *key,const char *query,int rc,
  const reader_catalog_error &e,int before,int found,const rows &r){
  std::ostringstream s;
  s<<"{\"schema\":1,\"type\":\"catalog_call\",\"seq\":"<<seq
   <<",\"id\":"<<jq(id)<<",\"api\":"<<jq(api)
   <<",\"input\":{\"after_key\":"<<jp(after)<<",\"limit\":"
   <<(limit<0?"null":std::to_string(limit))<<",\"book_key\":"<<jp(key)<<",\"query\":"<<jp(query)
   <<"},\"return_code\":"<<rc<<",\"error\":{\"code\":"<<e.code<<",\"message\":"<<jq(e.message)
   <<"},\"found_before\":"<<(before<0?"null":std::to_string(before))
   <<",\"found_after\":"<<(found<0?"null":std::to_string(found))
   <<",\"callback_count\":"<<r.keys.size()<<",\"rows\":[";
  for(size_t i=0;i<r.keys.size();++i){
    if(i)s<<',';
    s<<"{\"callback_index\":"<<i<<",\"book_key\":"<<jq(r.keys[i])<<",\"deleted\":"<<r.deleted_flags.at(i)<<'}';
  }
  s<<']';
  if(seq==9)s<<",\"follows\":[\"reject_zero_limit\",\"reject_over_limit\",\"reject_empty_cursor\"],\"compare_with_seq\":1";
  s<<",\"claim_scope\":\"installed_synthetic_api\",\"gtk_claim\":false,\"sdk_original_claim\":false}";
  receipts::line(out.calls,s.str());
}
static reader_command_status observed_apply(receipts &out,unsigned seq,const char *op,
  reader_command_context *context,reader_book_command *input,
  reader_command_result *result,reader_command_error *error){
  auto rc=reader_command_apply_book(context,input,result,error);
  std::ostringstream s;
  s<<"{\"schema\":1,\"type\":\"typed_command\",\"seq\":"<<seq<<",\"operation\":"<<jq(op)
   <<",\"book_key\":"<<jq(input->book_key)<<",\"expected_heads\":[";
  for(size_t i=0;i<context->expected_count;++i){if(i)s<<',';s<<jq(context->expected_heads[i]);}
  s<<"],\"return_code\":"<<static_cast<int>(rc)<<",\"created\":"<<(result->created?"true":"false")
   <<",\"applied\":"<<(result->applied?"true":"false")<<",\"revision_id\":"<<jq(result->revision_id)<<'}';
  receipts::line(out.setup,s.str());return rc;
}
static int observed_page(receipts &out,unsigned seq,const char *id,reader_catalog *catalog,
  const char *after,size_t limit,reader_catalog_visit visit,rows *r,reader_catalog_error *e){
  *e={};int rc=reader_catalog_removed_page(catalog,after,limit,visit,r,e);
  call_receipt(out,seq,id,"reader_catalog_removed_page",after,static_cast<int>(limit),nullptr,nullptr,rc,*e,-1,-1,*r);
  return rc;
}
static int observed_find(receipts &out,unsigned seq,const char *id,reader_catalog *catalog,
  const char *key,const char *query,reader_catalog_visit visit,rows *r,int *found,reader_catalog_error *e){
  *e={};int before=*found;
  int rc=reader_catalog_find(catalog,key,query,visit,r,found,e);
  call_receipt(out,seq,id,"reader_catalog_find",nullptr,-1,key,query,rc,*e,before,*found,*r);
  return rc;
}
static int observed_retained(receipts &out,unsigned seq,const char *id,reader_catalog *catalog,
  const char *key,reader_catalog_visit visit,rows *r,int *found,reader_catalog_error *e){
  *e={};int before=*found;
  int rc=reader_catalog_retained_find(catalog,key,visit,r,found,e);
  call_receipt(out,seq,id,"reader_catalog_retained_find",nullptr,-1,key,nullptr,rc,*e,before,*found,*r);
  return rc;
}

int main(int argc,char **argv){try{
  need(argc==2&&std::getenv("GITHUB_ACTIONS")&&std::string(std::getenv("GITHUB_ACTIONS"))=="true","Actions only");
  receipts receipt(argv[1]);
  reader_revisions *revision=nullptr;reader_revision_error re{};
  need(reader_revisions_open(argv[1],&revision,&re)==READER_REV_OK,"open revisions");
  std::vector<std::string> keys,deleted;
  for(unsigned i=1;i<=51;i++){
    char digest[65];std::snprintf(digest,sizeof(digest),"%064x",i);std::string key="txt:"+std::string(digest);
    reader_book_command input{READER_COMMAND_PUT,key.c_str(),"txt",digest,"Synthetic paging row","Author","Sort",123,0};
    reader_command_context context{revision,nullptr,nullptr,0};reader_command_result result{};reader_command_error error{};
    need(observed_apply(receipt,2*i-1,"PUT",&context,&input,&result,&error)==READER_COMMAND_OK&&result.created&&result.applied,"typed put");
    std::string parent=result.revision_id;const char *parents[]={parent.c_str()};
    context.expected_heads=parents;context.expected_count=1;input.operation=READER_COMMAND_DELETE;
    need(observed_apply(receipt,2*i,"DELETE",&context,&input,&result,&error)==READER_COMMAND_OK&&result.created&&result.applied,"typed delete");
    keys.push_back(key);deleted.emplace_back(result.revision_id);
  }
  need(reader_revisions_close(&revision,&re)==READER_REV_OK,"close revisions");
  reader_catalog *catalog=nullptr;reader_catalog_error ce{};
  need(reader_catalog_open(argv[1],&catalog,&ce)==0,"open catalog");
  rows first;need(observed_page(receipt,1,"removed_first",catalog,nullptr,50,collect,&first,&ce)==0,"first page");
  need(first.all_deleted&&first.keys.size()==50&&first.keys.front()==keys.front()&&first.keys.back()==keys[49],"50 bounded ordered rows");
  rows second;need(observed_page(receipt,2,"removed_second",catalog,first.keys.back().c_str(),50,collect,&second,&ce)==0,"second page");
  need(second.all_deleted&&second.keys.size()==1&&second.keys[0]==keys[50],"exclusive last row");
  rows end;need(observed_page(receipt,3,"removed_end",catalog,second.keys.back().c_str(),50,collect,&end,&ce)==0&&end.keys.empty(),"empty final page");
  rows visible;int found=7;
  need(observed_find(receipt,4,"visible_find_deleted",catalog,keys[0].c_str(),nullptr,collect,&visible,&found,&ce)==0&&!found&&visible.keys.empty(),"old find excludes deleted");
  rows retained;need(observed_retained(receipt,5,"retained_find_deleted",catalog,keys[0].c_str(),collect,&retained,&found,&ce)==0&&found&&retained.all_deleted&&retained.keys.size()==1,"retained lookup finds tombstone");
  rows invalid;need(observed_page(receipt,6,"reject_zero_limit",catalog,nullptr,0,collect,&invalid,&ce)!=0&&invalid.keys.empty(),"zero limit refused");
  need(observed_page(receipt,7,"reject_over_limit",catalog,nullptr,101,collect,&invalid,&ce)!=0&&invalid.keys.empty(),"over limit refused");
  need(observed_page(receipt,8,"reject_empty_cursor",catalog,"",50,collect,&invalid,&ce)!=0&&invalid.keys.empty(),"empty cursor refused");
  rows again;need(observed_page(receipt,9,"owner_gate_reentry",catalog,nullptr,50,collect,&again,&ce)==0&&again.keys==first.keys,"invalid request releases owner gate");
  need(reader_catalog_close(&catalog,&ce)==0,"close catalog");
  receipt.close();
  std::cout<<"{\"accepted\":true,\"checks\":9,\"rows\":51,\"page_sizes\":[50,1,0],\"setup\":\"installed typed commands\",\"gtk_claim\":false,\"sdk_original_claim\":false}\n";
  return 0;
}catch(const std::exception &e){std::cerr<<e.what()<<"\n";return 1;}}
