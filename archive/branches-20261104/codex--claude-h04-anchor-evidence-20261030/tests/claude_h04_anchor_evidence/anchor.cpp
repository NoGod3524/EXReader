// SPDX-License-Identifier: MIT
// Actions-only installed API evidence for removed-book paging anchors (after_key).
// Synthetic typed-command catalog, not GTK/SDK-original evidence.
#include <reader_commands.h>
#include <catalog.h>
#include <cstdio>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <set>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

static void need(bool value,const std::string &why){if(!value)throw std::runtime_error(why);}

static std::string jq(const std::string &s){
  static const char h[]="0123456789abcdef"; std::string o="\"";
  for(unsigned char c:s){
    if(c=='"')o+="\\\"";else if(c=='\\')o+="\\\\";
    else if(c<32){o+="\\u00";o+=h[c>>4];o+=h[c&15];}
    else o+=static_cast<char>(c);
  }return o+'"';
}

struct rows {std::vector<std::string> keys;bool all_deleted=true;};
static int collect(void *p,const reader_catalog_row *row){
  auto &r=*static_cast<rows *>(p);r.keys.emplace_back(row->book_key);r.all_deleted=r.all_deleted&&row->deleted;return 0;
}

static std::ofstream calls;
static unsigned seq=0;

// One installed-API call, one receipt line. The row list is part of the receipt so a red run is diagnosable.
static int page(reader_catalog *catalog,const char *id,const char *after,size_t limit,rows *r){
  reader_catalog_error e{};
  int rc=reader_catalog_removed_page(catalog,after,limit,collect,r,&e);
  std::ostringstream s;
  s<<"{\"schema\":1,\"type\":\"catalog_call\",\"seq\":"<<++seq<<",\"id\":"<<jq(id)
   <<",\"api\":\"reader_catalog_removed_page\",\"after_key\":"<<(after?jq(after):"null")
   <<",\"limit\":"<<limit<<",\"return_code\":"<<rc<<",\"error_code\":"<<e.code
   <<",\"callback_count\":"<<r->keys.size()<<",\"rows\":[";
  for(size_t i=0;i<r->keys.size();++i){if(i)s<<',';s<<jq(r->keys[i]);}
  s<<"],\"claim_scope\":\"installed_synthetic_api\",\"gtk_claim\":false,\"sdk_original_claim\":false}";
  calls<<s.str()<<'\n';calls.flush();
  return rc;
}

static std::string key_for(unsigned i){
  char digest[65];std::snprintf(digest,sizeof(digest),"%064x",i);return "txt:"+std::string(digest);
}

// Typed PUT then typed DELETE through the installed command module; leaves one tombstone for key_for(i).
static void put_deleted(const char *database,const std::vector<unsigned> &ids){
  reader_revisions *revision=nullptr;reader_revision_error re{};
  need(reader_revisions_open(database,&revision,&re)==READER_REV_OK,"open revisions");
  for(unsigned i:ids){
    char digest[65];std::snprintf(digest,sizeof(digest),"%064x",i);std::string key=key_for(i);
    reader_book_command input{READER_COMMAND_PUT,key.c_str(),"txt",digest,"Synthetic anchor row","Author","Sort",123,0};
    reader_command_context context{revision,nullptr,nullptr,0};reader_command_result result{};reader_command_error error{};
    need(reader_command_apply_book(&context,&input,&result,&error)==READER_COMMAND_OK&&result.created&&result.applied,"typed put "+key);
    std::string parent=result.revision_id;const char *parents[]={parent.c_str()};
    context.expected_heads=parents;context.expected_count=1;input.operation=READER_COMMAND_DELETE;
    need(reader_command_apply_book(&context,&input,&result,&error)==READER_COMMAND_OK&&result.created&&result.applied,"typed delete "+key);
  }
  need(reader_revisions_close(&revision,&re)==READER_REV_OK,"close revisions");
}

static std::vector<std::string> slice(const std::vector<std::string> &v,size_t from,size_t count){
  std::vector<std::string> o;
  for(size_t i=from;i<v.size()&&o.size()<count;++i)o.push_back(v[i]);
  return o;
}

// Follow each page's last key as the next anchor until an empty page; returns concatenated keys.
static std::vector<std::string> walk(reader_catalog *catalog,const char *id,size_t limit,size_t *pages){
  std::vector<std::string> all;std::string anchor;bool have=false;*pages=0;
  for(;;){
    rows r;need(page(catalog,id,have?anchor.c_str():nullptr,limit,&r)==0,std::string(id)+": page failed");
    need(r.keys.size()<=limit,std::string(id)+": page exceeds limit");
    ++*pages;need(*pages<=200,std::string(id)+": walk does not terminate");
    if(r.keys.empty())return all;
    need(r.all_deleted,std::string(id)+": non-removed row");
    all.insert(all.end(),r.keys.begin(),r.keys.end());anchor=r.keys.back();have=true;
  }
}

int main(int argc,char **argv){try{
  need(argc==2&&std::getenv("GITHUB_ACTIONS")&&std::string(std::getenv("GITHUB_ACTIONS"))=="true","Actions only");
  auto dir=std::filesystem::path(argv[1]).parent_path();
  calls.exceptions(std::ios::failbit|std::ios::badbit);
  calls.open(dir/"calls.jsonl",std::ios::binary|std::ios::trunc);

  std::vector<unsigned> ids;std::vector<std::string> keys;
  for(unsigned i=1;i<=51;i++){ids.push_back(i);keys.push_back(key_for(i));}
  put_deleted(argv[1],ids);

  reader_catalog *catalog=nullptr;reader_catalog_error ce{};
  need(reader_catalog_open(argv[1],&catalog,&ce)==0,"open catalog");
  unsigned checks=0;

  // 1. Chained anchors reproduce the whole removed set once, for several page sizes.
  for(size_t limit:{size_t(1),size_t(7),size_t(50),size_t(100)}){
    size_t pages=0;std::string id="chain_limit_"+std::to_string(limit);
    auto all=walk(catalog,id.c_str(),limit,&pages);
    need(all==keys,id+": chained pages differ from the removed set");
    need(std::set<std::string>(all.begin(),all.end()).size()==all.size(),id+": duplicate key across pages");
    ++checks;
  }

  // 2. A present anchor is exclusive and the page after it is the next keys in order.
  for(size_t k:{size_t(0),size_t(24),size_t(49),size_t(50)}){
    rows r;std::string id="exclusive_after_"+std::to_string(k);
    need(page(catalog,id.c_str(),keys[k].c_str(),50,&r)==0,id+": page failed");
    need(r.keys==slice(keys,k+1,50),id+": rows are not the keys strictly after the anchor");
    ++checks;
  }

  // 3. An absent anchor sorts between present keys: the page starts at the next greater key.
  {
    rows r;need(page(catalog,"absent_between_1_2",(keys[0]+"0").c_str(),50,&r)==0,"absent between: page failed");
    need(r.keys==slice(keys,1,50),"absent between: did not start at the next greater key");++checks;
    rows below;need(page(catalog,"absent_before_all","a",50,&below)==0,"absent before: page failed");
    need(below.keys==slice(keys,0,50),"absent before: not the first page");++checks;
    rows above;need(page(catalog,"absent_after_all",(key_for(0xffffffffu)+"f").c_str(),50,&above)==0&&above.keys.empty(),"absent after: not empty");++checks;
  }

  need(reader_catalog_close(&catalog,&ce)==0,"close catalog");

  // 4. The anchor is a key, not an offset: tombstones added on either side of it between sessions.
  put_deleted(argv[1],{0,52});
  need(reader_catalog_open(argv[1],&catalog,&ce)==0,"reopen catalog");
  {
    rows r;need(page(catalog,"after_mutation_anchor_49",keys[49].c_str(),50,&r)==0,"mutation: page failed");
    need(r.keys==std::vector<std::string>({keys[50],key_for(52)}),"mutation: later page shifted or missed the new greater key");++checks;
    rows head;need(page(catalog,"after_mutation_first",nullptr,100,&head)==0,"mutation: first page failed");
    need(head.keys.size()==53&&head.keys.front()==key_for(0)&&head.keys.back()==key_for(52),"mutation: first page does not hold the new keys");++checks;
    auto expected=keys;expected.push_back(key_for(52));
    rows tail;need(page(catalog,"after_mutation_anchor_0",key_for(0).c_str(),100,&tail)==0&&tail.keys==expected,"mutation: anchor at the new lowest key");++checks;
  }
  need(reader_catalog_close(&catalog,&ce)==0,"close catalog");
  calls.close();
  std::cout<<"{\"accepted\":true,\"checks\":"<<checks<<",\"rows\":53,\"gtk_claim\":false,\"sdk_original_claim\":false}\n";
  return 0;
}catch(const std::exception &e){std::cerr<<e.what()<<"\n";return 1;}}
