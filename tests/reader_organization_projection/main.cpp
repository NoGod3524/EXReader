#include <reader_projection.h>
#include <fstream>
#include <iostream>
#include <iterator>
#include <string>
#ifdef EXR_READER_SELECTOR_BYTES_CANDIDATE
#define OPEN reader_revisions_open_raw_v3
#define VALIDATE reader_revision_validate_raw_v3
#define RECEIVE reader_revision_receive_raw_v3
#define PROJECT reader_revision_project_raw_v3
#define PAGE reader_organization_project_page_raw_v3
#else
#define OPEN reader_revisions_open
#define VALIDATE reader_revision_validate
#define RECEIVE reader_revision_receive
#define PROJECT reader_revision_project
#define PAGE reader_organization_project_page
#endif
int main(int argc,char **argv) {
  if(argc<4) return 2;
  reader_revisions *s=nullptr; reader_revision_error e{};
  auto code=OPEN(argv[1],&s,&e); std::string action=argv[2];
  if(code==READER_REV_OK && action=="receive" && argc==4) {
    std::ifstream f(argv[3],std::ios::binary); std::string body((std::istreambuf_iterator<char>(f)),{});
    reader_revision_info i{}; code=VALIDATE(s,body.data(),body.size(),nullptr,&i,&e);
    if(code==READER_REV_OK) code=RECEIVE(s,body.data(),body.size(),i.sha256,nullptr,nullptr,&e);
  } else if(code==READER_REV_OK && action=="book" && argc==6) {
    code=PROJECT(s,"book",argv[3],argv[4],argv[5],nullptr,&e);
  } else if(code==READER_REV_OK && action=="page" && argc==6) {
    reader_organization_projection_row rows[100]{}; size_t count=0;
    code=PAGE(s,argv[3],std::string(argv[4])=="-"?nullptr:argv[4],std::stoul(argv[5]),rows,&count,&e);
    std::cout<<"{\"status\":"<<code<<",\"rows\":[";
    for(size_t i=0;i<count;i++) {if(i)std::cout<<',';std::cout<<"{\"key\":\""<<rows[i].entity_key<<"\",\"result\":"<<rows[i].result<<",\"selection\":"<<rows[i].selection.kind<<"}";}
    std::cout<<"]}"<<std::endl;
    reader_revisions_close(&s,nullptr); return 0;
  }
  std::cout<<"{\"status\":"<<code<<"}"<<std::endl;
  if(s) reader_revisions_close(&s,nullptr); return 0;
}
