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
struct rows {std::vector<std::string> keys;bool all_deleted=true;};
static int collect(void *p,const reader_catalog_row *row){auto &r=*static_cast<rows *>(p);r.keys.emplace_back(row->book_key);r.all_deleted=r.all_deleted&&row->deleted;return 0;}
int main(int argc,char **argv){try{
  need(argc==2&&std::getenv("GITHUB_ACTIONS")&&std::string(std::getenv("GITHUB_ACTIONS"))=="true","Actions only");
  reader_revisions *revision=nullptr;reader_revision_error re{};
  need(reader_revisions_open(argv[1],&revision,&re)==READER_REV_OK,"open revisions");
  std::vector<std::string> keys,deleted;
  for(unsigned i=1;i<=51;i++){
    char digest[65];std::snprintf(digest,sizeof(digest),"%064x",i);std::string key="txt:"+std::string(digest);
    reader_book_command input{READER_COMMAND_PUT,key.c_str(),"txt",digest,"Synthetic paging row","Author","Sort",123,0};
    reader_command_context context{revision,nullptr,nullptr,0};reader_command_result result{};reader_command_error error{};
    need(reader_command_apply_book(&context,&input,&result,&error)==READER_COMMAND_OK&&result.created&&result.applied,"typed put");
    std::string parent=result.revision_id;const char *parents[]={parent.c_str()};
    context.expected_heads=parents;context.expected_count=1;input.operation=READER_COMMAND_DELETE;
    need(reader_command_apply_book(&context,&input,&result,&error)==READER_COMMAND_OK&&result.created&&result.applied,"typed delete");
    keys.push_back(key);deleted.emplace_back(result.revision_id);
  }
  need(reader_revisions_close(&revision,&re)==READER_REV_OK,"close revisions");
  reader_catalog *catalog=nullptr;reader_catalog_error ce{};
  need(reader_catalog_open(argv[1],&catalog,&ce)==0,"open catalog");
  rows first;need(reader_catalog_removed_page(catalog,nullptr,50,collect,&first,&ce)==0,"first page");
  need(first.all_deleted&&first.keys.size()==50&&first.keys.front()==keys.front()&&first.keys.back()==keys[49],"50 bounded ordered rows");
  rows second;need(reader_catalog_removed_page(catalog,first.keys.back().c_str(),50,collect,&second,&ce)==0,"second page");
  need(second.all_deleted&&second.keys.size()==1&&second.keys[0]==keys[50],"exclusive last row");
  rows end;need(reader_catalog_removed_page(catalog,second.keys.back().c_str(),50,collect,&end,&ce)==0&&end.keys.empty(),"empty final page");
  rows visible;int found=7;
  need(reader_catalog_find(catalog,keys[0].c_str(),nullptr,collect,&visible,&found,&ce)==0&&!found&&visible.keys.empty(),"old find excludes deleted");
  rows retained;need(reader_catalog_retained_find(catalog,keys[0].c_str(),collect,&retained,&found,&ce)==0&&found&&retained.all_deleted&&retained.keys.size()==1,"retained lookup finds tombstone");
  rows invalid;need(reader_catalog_removed_page(catalog,nullptr,0,collect,&invalid,&ce)!=0&&invalid.keys.empty(),"zero limit refused");
  need(reader_catalog_removed_page(catalog,nullptr,101,collect,&invalid,&ce)!=0&&invalid.keys.empty(),"over limit refused");
  need(reader_catalog_removed_page(catalog,"",50,collect,&invalid,&ce)!=0&&invalid.keys.empty(),"empty cursor refused");
  rows again;need(reader_catalog_removed_page(catalog,nullptr,50,collect,&again,&ce)==0&&again.keys==first.keys,"invalid request releases owner gate");
  need(reader_catalog_close(&catalog,&ce)==0,"close catalog");
  std::cout<<"{\"accepted\":true,\"checks\":9,\"rows\":51,\"page_sizes\":[50,1,0],\"setup\":\"installed typed commands\",\"gtk_claim\":false,\"sdk_original_claim\":false}\n";
  return 0;
}catch(const std::exception &e){std::cerr<<e.what()<<"\n";return 1;}}
