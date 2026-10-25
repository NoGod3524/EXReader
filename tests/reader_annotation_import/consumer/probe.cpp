// SPDX-License-Identifier: MIT
#include <reader_annotation_import.h>
#include <reader_annotation_export.h>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <string>
#include <thread>
#include <chrono>
#ifndef _WIN32
#include <signal.h>
#include <sys/resource.h>
#endif
std::string esc(const char *s){std::string o="\"";for(;*s;s++){unsigned char c=(unsigned char)*s;if(c=='"'||c=='\\'){o+='\\';o+=(char)c;}else if(c<32){char b[8];std::snprintf(b,sizeof(b),"\\u%04x",c);o+=b;}else o+=(char)c;}return o+'"';}
struct context {
 reader_annotation_import_options *options=nullptr;reader_annotation_import_stats *stats=nullptr;
 unsigned stop=0,kill=0,seen=0;bool reenter=false,replace=false,fault=false;std::string marker;int nested=-1;
};
int item(void *v,const reader_annotation_import_item *i){auto &c=*(context *)v;++c.seen;
 std::printf("{\"item\":%llu,\"id\":%s,\"outcome\":%d,\"created\":%d,\"duplicate\":%d,\"committed\":%d,\"revision_code\":%d,\"heads\":%zu,\"missing\":%zu,\"safe\":%d,\"deleted\":%d}\n",(unsigned long long)i->index,esc(i->info.revision_id).c_str(),(int)i->outcome,i->created,i->exact_duplicate,i->committed,i->revision_code,i->graph.heads,i->graph.missing_parents,i->graph.projection_safe,i->graph.deleted);std::fflush(stdout);
 if(c.kill&&c.seen==c.kill){std::ofstream(c.marker)<<"committed";for(;;)std::this_thread::sleep_for(std::chrono::seconds(1));}
 return c.stop&&c.seen>=c.stop;
}
int meta(void *v,const reader_annotation_import_metadata *m){auto &c=*(context *)v;
 if(!m->annotation_id){
  std::printf("{\"header_title\":%s}\n",m->book_title?esc(m->book_title).c_str():"null");
  if(c.replace){std::ofstream f(c.options->jsonl_path,std::ios::binary|std::ios::trunc);f<<"replacement-not-json\n";}
  if(c.reenter){reader_annotation_import_error e{};c.nested=(int)reader_annotation_import_run(c.options,c.stats,&e);}
#ifndef _WIN32
  if(c.fault){signal(SIGXFSZ,SIG_IGN);struct rlimit r{};getrlimit(RLIMIT_FSIZE,&r);r.rlim_cur=0;setrlimit(RLIMIT_FSIZE,&r);}
#endif
 }else std::printf("{\"annotation\":%s,\"source_selection\":%s,\"source_revisions\":%zu,\"source_heads\":%zu,\"tombstone\":%d}\n",esc(m->annotation_id).c_str(),esc(m->selection).c_str(),m->graph.revisions,m->graph.heads,m->tombstone);
 return 0;
}
int main(int argc,char **argv){
 if(argc<3)return 2;reader_revisions *store=nullptr;reader_revision_error re{};
 if(reader_revisions_open(argv[2],&store,&re)!=READER_REV_OK){std::printf("{\"open_error\":%d}\n",re.code);return 1;}
 std::string action=argv[1];
 if(action=="receive"&&argc==4){std::ifstream f(argv[3],std::ios::binary);std::string line;unsigned made=0;while(std::getline(f,line)){int created=0;reader_revision_info i{};auto s=reader_revision_receive(store,line.data()+65,line.size()-65,line.substr(0,64).c_str(),&i,&created,&re);if(s!=READER_REV_OK){std::printf("{\"receive_error\":%d}\n",s);return 1;}made+=(unsigned)created;}std::printf("{\"created\":%u}\n",made);}
 else if(action=="export"&&argc==6){reader_annotation_export_options o{};o.struct_size=sizeof(o);o.revisions=store;o.book_key=argv[3];o.jsonl_path=argv[4];o.book_title=argv[5];reader_annotation_export_stats s{};reader_annotation_export_error e{};auto r=reader_annotation_export_run(&o,&s,&e);std::printf("{\"export_status\":%d,\"heads\":%llu}\n",r,(unsigned long long)s.head_wires);if(r)return 1;}
 else if(action=="import"&&argc>=5){reader_annotation_import_options o{};reader_annotation_import_stats s{};reader_annotation_import_error e{};context c;o.struct_size=sizeof(o);o.revisions=store;o.target_book_key=argv[3];o.jsonl_path=argv[4];o.item=item;o.metadata=meta;o.context=&c;c.options=&o;c.stats=&s;
  bool wrong=false;for(int n=5;n<argc;n++){std::string a=argv[n];if(a=="thread")wrong=true;else if(a=="reenter")c.reenter=true;else if(a=="replace")c.replace=true;else if(a=="fault")c.fault=true;else if(a.rfind("stop=",0)==0)c.stop=(unsigned)std::stoul(a.substr(5));else if(a.rfind("resume=",0)==0)o.resume_index=std::stoull(a.substr(7));else if(a.rfind("limit=",0)==0)o.max_input_bytes=std::stoull(a.substr(6));else if(a.rfind("kill=",0)==0){c.kill=1;c.marker=a.substr(5);}}
  reader_annotation_import_status r=READER_AI_OK;if(wrong){std::thread t([&]{r=reader_annotation_import_run(&o,&s,&e);});t.join();}else r=reader_annotation_import_run(&o,&s,&e);
  std::printf("{\"status\":%d,\"revision_code\":%d,\"message\":%s,\"line\":%llu,\"index\":%llu,\"validated\":%d,\"heads\":%llu,\"omitted\":%llu,\"created\":%llu,\"duplicates\":%llu,\"committed\":%llu,\"next\":%llu,\"nested\":%d,\"accepted\":%d}\n",r,e.revision_code,esc(e.message).c_str(),(unsigned long long)e.line,(unsigned long long)e.item_index,s.validated,(unsigned long long)s.head_wires,(unsigned long long)s.omitted_history,(unsigned long long)s.created,(unsigned long long)s.duplicates,(unsigned long long)s.committed,(unsigned long long)s.next_index,c.nested,s.complete_product_accepted);
 }else return 2;
 reader_revisions_close(&store,&re);return 0;
}
