/* SPDX-License-Identifier: MIT
   C06 installed-package probe. Built twice from installed packages only: the
   default legacy family (EXR_READER_SELECTOR_BYTES_CANDIDATE undefined) and the
   explicit raw0.2 family. Every command prints machine-readable STATUS/STATS
   lines; tests/reader_next_c06/run.py judges them with independent readers. */
#include <reader_annotation_export.h>
#include <reader_annotation_import.h>
#ifdef EXR_READER_SELECTOR_BYTES_CANDIDATE
#include <reader_annotation_export_raw3.h>
#include <reader_annotation_import_raw3.h>
#endif
#include <reader_projection.h>
#include <reader_reading_state.h>
#include <exreader.h>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <memory>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>
extern "C" int c06_c_api(void);
namespace fs=std::filesystem;
static const std::string PDF_SHA="5627a430fa04cbe11d38eb2682e336ef21e147d445753ed46ed11a7d5e3167cc";
static const std::string TXT_TEXT="A real public SDK text capture has enough context for stable matching.";
static unsigned sequence=0x1000;
static void check(bool pass,const std::string &name){if(!pass)throw std::runtime_error(name);std::cout<<"PASS "<<name<<std::endl;}
static std::string rid(){char b[33];std::snprintf(b,sizeof(b),"%032x",sequence++);return b;}
static std::string read(const fs::path &p){std::ifstream f(p,std::ios::binary);if(!f)throw std::runtime_error("read "+p.u8string());std::ostringstream s;s<<f.rdbuf();return s.str();}
static void write(const fs::path &p,const std::string &s){std::ofstream f(p,std::ios::binary);f.write(s.data(),(std::streamsize)s.size());if(!f)throw std::runtime_error("write "+p.u8string());}
static std::string pdf_key(){return "pdf:"+PDF_SHA;}
static std::string txt_key(){const char *s=std::getenv("C06_TXT_SHA");if(!s||std::strlen(s)!=64)throw std::runtime_error("C06_TXT_SHA");return std::string("txt:")+s;}
static std::string pdf2_key(){return "pdf:"+std::string(64,'8');}
static std::string amb_key(){return "txt:"+std::string(64,'7');}
static std::string amb_text(){std::string s;for(int i=0;i<400;i++)s+="ab";return s;}
static std::string book_wire(const std::string &id,const std::string &key,const char *format,size_t bytes,const char *title){
  return "{\"version\":1,\"id\":\""+id+"\",\"entity_kind\":\"book\",\"entity_key\":\""+key+"\",\"operation\":\"put\",\"location_kind\":\"none\",\"parents\":[],\"payload\":{\"format\":\""+format+"\",\"source_sha256\":\""+key.substr(key.find(':')+1)+"\",\"source_bytes\":"+std::to_string(bytes)+",\"title\":\""+title+"\",\"author\":\"\",\"favorite\":false}}";
}
struct store {
  reader_revisions *p=nullptr;
  store(const fs::path &path,bool raw){
    reader_revision_error e{};reader_revision_status st;
#ifdef EXR_READER_SELECTOR_BYTES_CANDIDATE
    st=raw?reader_revisions_open_raw_v3(path.u8string().c_str(),&p,&e):reader_revisions_open(path.u8string().c_str(),&p,&e);
#else
    if(raw)throw std::runtime_error("raw store requires the raw0.2 family");
    st=reader_revisions_open(path.u8string().c_str(),&p,&e);
#endif
    check(st==READER_REV_OK,std::string("open store ")+e.message);
  }
  ~store(){reader_revision_error e{};reader_revisions_close(&p,&e);}
  store(const store &)=delete;store &operator=(const store &)=delete;
};
static bool raw_kind(const std::string &k){if(k=="raw")return true;if(k=="legacy")return false;throw std::runtime_error("store kind");}
static void receive_wire(reader_revisions *s,bool raw,const std::string &wire){
  reader_revision_info i{};reader_revision_error e{};int made=0;
#ifdef EXR_READER_SELECTOR_BYTES_CANDIDATE
  if(raw){
    check(reader_revision_validate_raw_v3(s,wire.data(),wire.size(),nullptr,&i,&e)==READER_REV_OK,e.message);
    std::string sha=i.sha256;
    check(reader_revision_receive_raw_v3(s,wire.data(),wire.size(),sha.c_str(),&i,&made,&e)==READER_REV_OK,e.message);
    return;
  }
#else
  if(raw)throw std::runtime_error("raw receive requires the raw0.2 family");
#endif
  check(reader_revision_validate(s,wire.data(),wire.size(),nullptr,&i,&e)==READER_REV_OK,e.message);
  std::string sha=i.sha256;
  check(reader_revision_receive(s,wire.data(),wire.size(),sha.c_str(),&i,&made,&e)==READER_REV_OK,e.message);
}
static std::string legacy_encode(reader_revisions *s,unsigned version,const std::string &id,const std::string &book,const std::string &aid,const reader_rs_capture &c,const char *note){
  reader_rs_envelope e{};e.revision_id=id.c_str();e.operation="put";e.entity_kind="annotation";e.book_key=book.c_str();e.annotation_id=aid.c_str();e.note_text=note;e.parser_version=exr_version();
  char *w=nullptr;size_t n=0;reader_rs_error er{};
  reader_rs_status st=version==1?reader_rs_encode(s,&e,&c,&w,&n,&er):reader_rs_encode_v2(s,&e,&c,0,&w,&n,&er);
  check(st==READER_RS_OK,er.message);std::string out(w,n);reader_rs_free(w);return out;
}
struct text_book {
  exr_document *doc=nullptr;exr_anchor a{};
  text_book(const std::string &text,size_t start,size_t end){
    exr_error se{};check(exr_document_open_memory(EXR_TXT,text.data(),text.size(),&doc,&se)==EXR_OK,se.message);
    check(exr_anchor_create(doc,start,end,&a,&se)==EXR_OK,se.message);
  }
  ~text_book(){exr_anchor_free(&a);exr_document_free(doc);}
  reader_rs_capture capture() const {reader_rs_capture c{};c.mode=READER_RS_REFLOW_GLOBAL;c.anchor=&a;return c;}
};
static void print_status(int code,const char *message){std::cout<<"STATUS "<<code<<std::endl;std::cout<<"MESSAGE "<<(message?message:"")<<std::endl;}

/* ---- default legacy family ---- */
static void legacy_seed(const fs::path &work){
  fs::create_directories(work/"books");
  store sender(work/"legacy-sender.sqlite",false);
  std::string key=txt_key(),book=book_wire(rid(),key,"txt",TXT_TEXT.size(),"actual compatibility TXT");
  receive_wire(sender.p,false,book);write(work/"books"/"legacy-txt.json",book);
  text_book txt(TXT_TEXT,2,6);auto c=txt.capture();
  receive_wire(sender.p,false,legacy_encode(sender.p,1,rid(),key,std::string(32,'a'),c,"anchor1 note"));
  receive_wire(sender.p,false,legacy_encode(sender.p,2,rid(),key,std::string(32,'b'),c,"anchor2 note"));
  std::cout<<"KEY "<<key<<std::endl;
}
static void old_export(bool raw,const std::string &path,const std::string &book,const char *jsonl,const char *md){
  store s(path,raw);reader_annotation_export_options o{};o.struct_size=sizeof(o);o.revisions=s.p;o.book_key=book.c_str();o.jsonl_path=jsonl;o.markdown_path=md;
  reader_annotation_export_stats st{};reader_annotation_export_error er{};auto code=reader_annotation_export_run(&o,&st,&er);
  print_status((int)code,er.message);std::cout<<"REVISION "<<er.revision_code<<std::endl;
  std::cout<<"STATS "<<st.annotations<<" "<<st.head_wires<<" "<<st.jsonl_published<<" "<<st.markdown_published<<" "<<st.jsonl_bytes<<" "<<st.markdown_bytes<<std::endl;
}
static void old_import(bool raw,const std::string &path,const std::string &book,const char *jsonl){
  store s(path,raw);reader_annotation_import_options o{};o.struct_size=sizeof(o);o.revisions=s.p;o.jsonl_path=jsonl;o.target_book_key=book.c_str();
  reader_annotation_import_stats st{};reader_annotation_import_error er{};auto code=reader_annotation_import_run(&o,&st,&er);
  print_status((int)code,er.message);std::cout<<"REVISION "<<er.revision_code<<std::endl;
  std::cout<<"STATS "<<st.annotations<<" "<<st.head_wires<<" "<<st.committed<<" "<<st.created<<" "<<st.duplicates<<" "<<st.validated<<std::endl;
}
static void make_store(bool raw,const std::string &path,int argc,char **argv,int first){
  store s(path,raw);for(int i=first;i<argc;i++)receive_wire(s.p,raw,read(fs::u8path(argv[i])));
  std::cout<<"MADE "<<(argc-first)<<std::endl;
}

#ifdef EXR_READER_SELECTOR_BYTES_CANDIDATE
/* ---- explicit raw0.2 family ---- */
struct fixed {
  std::string original;exr_fixed_document *doc=nullptr;exr_fixed_text *text=nullptr;exr_fixed_anchor point{},range{};
  explicit fixed(const fs::path &path):original(read(path)){
    exr_error e{};check(original.size()==8845,"same real PDF size");
    check(exr_fixed_open_memory(EXR_PDF,original.data(),original.size(),nullptr,&doc,&e)==EXR_OK,e.message);
    size_t count=0;const auto *pages=exr_fixed_pages(doc,&count);check(count>0&&!std::strcmp(pages[0].id,"page-1"),"same page-1 route");
    check(exr_fixed_load_text(doc,0,nullptr,&text,&e)==EXR_OK,e.message);size_t n=0;const char *p=exr_fixed_text_string(text,&n);
    check(n>0&&std::memchr(p,0,n),"actual PDF public text contains NUL");
    check(exr_fixed_anchor_create("page-1",text,0,0,&point,&e)==EXR_OK,e.message);
    check(point.start==0&&point.end==0&&std::memchr(point.suffix,0,point.suffix_size),"actual zero point suffix contains NUL");
    check(exr_fixed_anchor_create("page-1",text,0,n,&range,&e)==EXR_OK,e.message);
    check(range.exact_size>0&&std::memchr(range.exact,0,range.exact_size),"actual nonempty range exact contains NUL");
  }
  ~fixed(){exr_fixed_anchor_free(&point);exr_fixed_anchor_free(&range);exr_fixed_text_free(text);exr_fixed_free(doc);}
};
static reader_rs_capture capture(const exr_fixed_anchor &a){reader_rs_capture c{};c.mode=READER_RS_FIXED_PAGE;c.fixed=&a;return c;}
static std::string encode3(reader_revisions *s,const std::string &id,const char *op,const std::string &book,const std::string &aid,
                           const std::vector<std::string> &parents,const reader_rs_capture &c,const char *note){
  std::vector<const char *> ptr;for(auto &p:parents)ptr.push_back(p.c_str());
  reader_rs_envelope e{};e.revision_id=id.c_str();e.operation=op;e.entity_kind="annotation";e.book_key=book.c_str();e.annotation_id=aid.c_str();
  e.parents=ptr.empty()?nullptr:ptr.data();e.parent_count=ptr.size();e.note_text=note;e.parser_version=exr_version();
  char *w=nullptr;size_t n=0;reader_rs_error er{};
  check(reader_rs_encode_fixed_v3(s,&e,&c,&w,&n,&er)==READER_RS_OK,er.message);std::string out(w,n);reader_rs_free(w);return out;
}
static std::string put3(store &s,const std::string &book,const std::string &aid,const char *op,const std::vector<std::string> &parents,
                        const reader_rs_capture &c,const char *note){
  std::string id=rid();receive_wire(s.p,true,encode3(s.p,id,op,book,aid,parents,c,note));return id;
}
static void raw_seed(const fs::path &pdf_path,const fs::path &work){
  fixed pdf(pdf_path);fs::create_directories(work/"books");
  store sender(work/"sender.sqlite",true);
  std::string key=pdf_key(),book=book_wire(rid(),key,"pdf",8845,"actual PDF");
  receive_wire(sender.p,true,book);write(work/"books"/"pdf.json",book);
  auto point=capture(pdf.point),range=capture(pdf.range);reader_rs_capture none{};none.mode=READER_RS_FIXED_PAGE;
  exr_fixed_anchor expression{};expression.page_id=pdf.point.page_id;auto null_capture=capture(expression);
  char empty[1]={0};exr_fixed_anchor allocated{};allocated.page_id=pdf.point.page_id;allocated.exact=empty;allocated.prefix=empty;allocated.suffix=empty;auto empty_capture=capture(allocated);
  std::string a1(32,'b'),a2(32,'c'),a3(32,'d'),a4(32,'e'),a5(32,'f');
  std::string r=put3(sender,key,a1,"put",{},point,"point");put3(sender,key,a1,"put",{r},point,"point twice");
  r=put3(sender,key,a2,"put",{},range,"range");r=put3(sender,key,a2,"delete",{r},none,nullptr);put3(sender,key,a2,"restore",{r},range,"restored");
  put3(sender,key,a3,"put",{},null_capture,"typed NULL");
  /* Allocated-empty selectors live in a second fixed book so that a unique public FOUND is not assumed for them. */
  std::string key2=pdf2_key(),book2=book_wire(rid(),key2,"pdf",8845,"allocated empty PDF");
  receive_wire(sender.p,true,book2);write(work/"books"/"pdf2.json",book2);
  put3(sender,key2,a4,"put",{},empty_capture,"allocated empty");
  r=put3(sender,key,a5,"put",{},point,"short lived");put3(sender,key,a5,"delete",{r},none,nullptr);
  /* Source anchor1/2 history in raw-store books, plus an ambiguous reflow selector. */
  store encoder(work/"legacy-encoder.sqlite",false);
  std::string tkey=txt_key(),tbook=book_wire(rid(),tkey,"txt",TXT_TEXT.size(),"actual compatibility TXT");
  receive_wire(sender.p,true,tbook);write(work/"books"/"txt.json",tbook);
  text_book txt(TXT_TEXT,2,6);auto tc=txt.capture();
  receive_wire(sender.p,true,legacy_encode(encoder.p,1,rid(),tkey,std::string(32,'a'),tc,"anchor1 note"));
  receive_wire(sender.p,true,legacy_encode(encoder.p,2,rid(),tkey,std::string(32,'b'),tc,"anchor2 note"));
  std::string abook=book_wire(rid(),amb_key(),"txt",amb_text().size(),"ambiguous TXT");
  receive_wire(sender.p,true,abook);write(work/"books"/"ambiguous.json",abook);
  text_book amb(amb_text(),400,402);auto ac=amb.capture();
  receive_wire(sender.p,true,legacy_encode(encoder.p,2,rid(),amb_key(),std::string(32,'a'),ac,"ambiguous"));
  std::cout<<"KEYS "<<key<<" "<<tkey<<" "<<amb_key()<<" "<<key2<<std::endl;
}
static void raw_export(bool raw,const std::string &path,const std::string &book,const char *jsonl,const char *md,uint64_t budget){
  store s(path,raw);reader_annotation_export_options o{};o.struct_size=sizeof(o);o.revisions=s.p;o.book_key=book.c_str();o.jsonl_path=jsonl;o.markdown_path=md;o.max_output_bytes=budget;
  reader_annotation_export_stats st{};reader_annotation_export_error er{};auto code=reader_annotation_export_raw3_run(&o,&st,&er);
  print_status((int)code,er.message);std::cout<<"REVISION "<<er.revision_code<<" RS "<<er.rs_code<<std::endl;
  std::cout<<"STATS "<<st.annotations<<" "<<st.head_wires<<" "<<st.jsonl_published<<" "<<st.markdown_published<<" "<<st.jsonl_bytes<<" "<<st.markdown_bytes<<std::endl;
}
static fixed *g_pdf=nullptr;static text_book *g_txt=nullptr,*g_amb=nullptr;
static int resolve_cb(void *,const reader_rs_record *r,uint64_t index){
  std::string key=r->book_key;reader_rs_error e{};exr_anchor_match m{};int yes=0;
  if(key==pdf_key()&&g_pdf){size_t page=SIZE_MAX;auto st=reader_rs_resolve_fixed_v3(g_pdf->doc,r,nullptr,&page,&m,&e);yes=st==READER_RS_OK&&m.state==EXR_ANCHOR_FOUND;
    std::cout<<"RESOLVE "<<index<<" fixed "<<(int)st<<" "<<(int)m.state<<std::endl;}
  else if(key==txt_key()&&g_txt){auto st=reader_rs_resolve_reflow(g_txt->doc,r,nullptr,&m,&e);yes=st==READER_RS_OK&&m.state==EXR_ANCHOR_FOUND;
    std::cout<<"RESOLVE "<<index<<" reflow "<<(int)st<<" "<<(int)m.state<<std::endl;}
  else if(key==amb_key()&&g_amb){auto st=reader_rs_resolve_reflow(g_amb->doc,r,nullptr,&m,&e);yes=st==READER_RS_OK&&m.state==EXR_ANCHOR_FOUND;
    std::cout<<"RESOLVE "<<index<<" ambiguous "<<(int)st<<" "<<(int)m.state<<" ambiguous_state="<<(int)EXR_ANCHOR_AMBIGUOUS<<std::endl;}
  return yes;
}
static uint64_t g_items=0,g_cancel_after=0;
static int item_cb(void *,const reader_ai3_item *item){
  std::cout<<"ITEM "<<item->index<<" outcome="<<(int)item->outcome<<" found="<<(int)item->found<<" committed="<<item->committed<<" created="<<item->created<<" duplicate="<<item->exact_duplicate<<std::endl;
  ++g_items;return g_cancel_after&&g_items>=g_cancel_after;
}
static void raw_import(bool raw,const std::string &path,const std::string &book,const char *jsonl,const std::string &action,const std::string &policy,
                       uint64_t fingerprint,uint64_t resume,uint64_t cancel_after,const char *pdf_path){
  store s(path,raw);std::unique_ptr<fixed> pdf;std::unique_ptr<text_book> txt,amb;
  if(pdf_path&&std::strcmp(pdf_path,"-")){pdf.reset(new fixed(fs::u8path(pdf_path)));g_pdf=pdf.get();txt.reset(new text_book(TXT_TEXT,2,6));g_txt=txt.get();amb.reset(new text_book(amb_text(),400,402));g_amb=amb.get();}
  reader_ai3_options o{};o.struct_size=sizeof(o);o.revisions=s.p;o.jsonl_path=jsonl;o.target_book_key=book.c_str();
  o.mode=action=="commit"?READER_AI3_COMMIT:READER_AI3_PREVIEW;o.policy=policy=="verified"?READER_AI3_RESOLVE_ALREADY_VERIFIED:READER_AI3_RESOLVE_REQUIRED;
  o.confirm_fingerprint=fingerprint;o.resume_index=resume;o.resolve=(policy=="verified"||policy=="nocallback")?nullptr:resolve_cb;o.item=item_cb;g_items=0;g_cancel_after=cancel_after;
  reader_ai3_stats st{};reader_ai3_error er{};auto code=reader_annotation_import_raw3_run(&o,&st,&er);
  print_status((int)code,er.message);std::cout<<"REVISION "<<er.revision_code<<" RS "<<er.rs_code<<" LINE "<<er.line<<" ITEM_INDEX "<<er.item_index<<std::endl;
  std::cout<<"STATS validated="<<st.validated<<" annotations="<<st.annotations<<" head_wires="<<st.head_wires<<" omitted="<<st.omitted_history<<" found="<<st.found
           <<" unresolved="<<st.unresolved<<" null_preserved="<<st.null_preserved<<" would_create="<<st.would_create<<" would_duplicate="<<st.would_duplicate
           <<" created="<<st.created<<" duplicates="<<st.duplicates<<" committed="<<st.committed<<" next_index="<<st.next_index<<" source_bytes="<<st.source_bytes
           <<" fingerprint="<<st.fingerprint<<" found_checked="<<st.found_checked<<" accepted="<<st.complete_product_accepted<<std::endl;
  g_pdf=nullptr;g_txt=nullptr;g_amb=nullptr;
}
#endif

int main(int argc,char **argv){try{
  check(c06_c_api()==0,"installed C ABI constants and argument contract");
  if(argc<2)return 2;std::string mode=argv[1];std::cout<<"SDK "<<exr_version()<<std::endl;
  if(mode=="legacy-seed"&&argc==3){legacy_seed(fs::u8path(argv[2]));return 0;}
  if(mode=="old-export"&&argc==7){old_export(raw_kind(argv[2]),argv[3],argv[4],argv[5],std::strcmp(argv[6],"-")?argv[6]:nullptr);return 0;}
  if(mode=="old-import"&&argc==6){old_import(raw_kind(argv[2]),argv[3],argv[4],argv[5]);return 0;}
  if(mode=="make-store"&&argc>=5){make_store(raw_kind(argv[2]),argv[3],argc,argv,4);return 0;}
#ifdef EXR_READER_SELECTOR_BYTES_CANDIDATE
  if(mode=="raw-seed"&&argc==4){raw_seed(fs::u8path(argv[2]),fs::u8path(argv[3]));return 0;}
  if(mode=="raw-export"&&argc>=8){raw_export(raw_kind(argv[2]),argv[3],argv[4],argv[5],std::strcmp(argv[6],"-")?argv[6]:nullptr,argc>=8?std::strtoull(argv[7],nullptr,10):0);return 0;}
  if(mode=="raw-import"&&argc==12){raw_import(raw_kind(argv[2]),argv[3],argv[4],argv[5],argv[6],argv[7],std::strtoull(argv[8],nullptr,10),std::strtoull(argv[9],nullptr,10),std::strtoull(argv[10],nullptr,10),argv[11]);return 0;}
#endif
  std::cerr<<"unknown mode or arguments"<<std::endl;return 2;
}catch(const std::exception &e){std::cerr<<"FAIL "<<e.what()<<std::endl;return 1;}}
