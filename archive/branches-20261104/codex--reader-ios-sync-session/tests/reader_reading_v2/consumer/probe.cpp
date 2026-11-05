/* SPDX-License-Identifier: MIT */
/* Reuse the fixture/SDK ownership/report helpers. The unchanged original
   main is run separately against the actual legacy revision implementation. */
#define main legacy_probe_main
#include "../../reader_reading_state/consumer/probe.cpp"
#undef main
#include <functional>
#include <filesystem>
#include <set>
#ifdef READER_V2_WEBDAV_TEST
#include <reader_sync.h>
#include <exr_sideload.h>
#endif
extern "C" int v2_c_contract(void);
namespace {
std::string final_wire,final_key;
std::string webdav_root,transport_work;
size_t network_pushed=0,network_pulled=0,originals_exported=0,metadata_projected=0;
#ifdef READER_V2_SESSION_TEST
void session_transfer(side &,side &);
#endif
std::string cached_original(const std::string &role){return transport_work+"/B-cache/"+shas[role]+"."+formats[role];}
void project_received_books(){
  std::vector<reader_revision_info> rows;reader_revision_error error{};
  if(reader_revision_entities_page(B.store,"book",nullptr,1,100,[](void *context,const reader_revision_entity_row *row){
    if(row->selection.kind!=READER_SELECTION_SAFE||row->selection.graph.deleted)fatal("received book metadata is not safe");
    ((std::vector<reader_revision_info> *)context)->push_back(row->info);return 0;
  },&rows,&error)!=READER_REV_OK||rows.size()!=4)fatal("received book discovery");
  for(const auto &row:rows){char *title=nullptr;
    if(reader_revision_book_title(B.store,row.revision_id,&title,&error)!=READER_REV_OK)fatal("received book title");
    // These fixture titles are ASCII and already NFC. Actual native hosts use
    // their established Unicode normalization before this same fenced API.
    if(reader_revision_project(B.store,"book",row.entity_key,row.revision_id,title,nullptr,&error)!=READER_REV_OK)fatal("received safe metadata projection");
    reader_revision_bytes_free(title);++metadata_projected;
  }
}
#ifdef READER_V2_WEBDAV_TEST
static int original_path(void *opaque,const char *key,char *out,size_t capacity){
  std::string value=key;size_t colon=value.find(':');std::string path=*(std::string *)opaque+"/A-originals/"+value.substr(colon+1)+"."+value.substr(0,colon);
  if(path.size()>=capacity)return 1;std::memcpy(out,path.c_str(),path.size()+1);return 0;
}
struct network_side {
  exr_webdav_client *dav=nullptr;reader_sync *sync=nullptr;
  network_side(side &device){
    std::string folder=transport_work+"/"+device.name+"-cache";std::filesystem::create_directories(std::filesystem::u8path(folder));
    exr_webdav_config config{};config.root_url=webdav_root.c_str();config.authorization=std::getenv("READER_TEST_AUTH");config.timeout_ms=15000;
    exr_webdav_error de{};if(!config.authorization||exr_webdav_create(&config,&dav,&de)!=EXR_DAV_OK)fatal("native transport create");
    reader_sync_config options{};options.dav=dav;options.revisions=device.store;options.private_directory=folder.c_str();
    if(&device==&A){options.original=original_path;options.context=&transport_work;}
    reader_sync_error se{};if(reader_sync_create(&options,&sync,&se)!=READER_SYNC_OK)fatal("native sync create");
  }
  ~network_side(){reader_sync_free(sync);exr_webdav_free(dav);}
  void step(unsigned shard){
    std::string cursor;reader_sync_report report{};
    do{reader_sync_error error{};if(reader_sync_step(sync,shard,cursor.c_str(),100,nullptr,&report,&error)!=READER_SYNC_OK)
      fatal("real native HTTPS step "+std::to_string(error.code)+"/"+std::to_string(error.http_status));
      expect(!report.pending_metadata&&!report.pending_local_original,"native transfer has verified book originals");
      network_pushed+=report.pushed;network_pulled+=report.pulled;cursor=report.after;
    }while(!report.shard_complete);
  }
};
#endif
void transfer(side &from,side &to){
  if(webdav_root.empty()){flush(from,to);return;}
#ifdef READER_V2_SESSION_TEST
  session_transfer(from,to);return;
#endif
#ifdef READER_V2_WEBDAV_TEST
  auto outgoing=pending(from);if(outgoing.empty())fatal("native transport has no actual queued revisions");
  std::set<unsigned> shards;for(const auto &row:outgoing)shards.insert((unsigned)std::stoul(row.id.substr(0,2),nullptr,16));
  network_side sender(from),receiver(to);sender.step(*shards.begin());
  expect(pending(from).empty(),"native conditional publication and GET verification ack the outbox");
  for(unsigned shard:shards)receiver.step(shard);
  for(const auto &row:outgoing){
    char *a=nullptr,*b=nullptr;size_t an=0,bn=0;
    expect(reader_revision_get(from.store,row.id.c_str(),&a,&an,nullptr,nullptr)==READER_REV_OK&&
      reader_revision_get(to.store,row.id.c_str(),&b,&bn,nullptr,nullptr)==READER_REV_OK&&an==bn&&std::string(a,an)==std::string(b,bn),"native HTTPS preserves exact retained revision bytes");
    reader_revision_bytes_free(a);reader_revision_bytes_free(b);
  }
#else
  fatal("probe was built without native WebDAV transport");
#endif
}
using resolver=std::function<reader_rs_status(const reader_rs_record *,exr_anchor_match *)>;
void roundtrip(const char *name,const char *role,const char *kind,const reader_rs_capture &capture,size_t part,
               const resolver &resolve,exr_anchor_state expected=EXR_ANCHOR_FOUND){
  std::string id=new_id(),aid=new_id(),key=keys[role]+(!std::strcmp(kind,"annotation")?":"+aid:"");
  auto observed=heads(A,kind,key);std::vector<const char *> parent;for(const auto &h:observed)parent.push_back(h.c_str());
  reader_rs_envelope envelope{};envelope.revision_id=id.c_str();envelope.operation="put";envelope.entity_kind=kind;
  envelope.book_key=keys[role].c_str();envelope.annotation_id=aid.c_str();envelope.parents=parent.data();envelope.parent_count=parent.size();
  envelope.note_text=name;envelope.parser_version=parser_version.c_str();char *wire=nullptr;size_t bytes=0;reader_rs_error error{};
  if(reader_rs_encode_v2(A.store,&envelope,&capture,part,&wire,&bytes,&error)!=READER_RS_OK)fatal(std::string(name)+" encode: "+error.message);
  std::string exact(wire,bytes);reader_rs_free(wire);reader_revision_info info{};reader_revision_error revision_error{};int created=0;
  if(reader_revision_local_reading(A.store,exact.data(),exact.size(),parent.data(),parent.size(),&info,&created,&revision_error)!=READER_REV_OK||!created)
    fatal(std::string(name)+" commit: "+revision_error.message);
  transfer(A,B);
  char *received=nullptr;size_t size=0;reader_revision_selection selection{};
  if(reader_revision_selected(B.store,kind,key.c_str(),&received,&size,&info,&selection,&revision_error)!=READER_REV_OK)fatal(std::string(name)+" select");
  expect(std::string(received,size)==exact,std::string(name)+" received exact product bytes");
  reader_rs_record record{};if(reader_rs_decode(B.store,received,size,&record,&error)!=READER_RS_OK)fatal(std::string(name)+" decode");
  reader_revision_bytes_free(received);expect(record.anchor_version==2,std::string(name)+" decodes anchor v2");
  if(capture.mode==READER_RS_REFLOW_GLOBAL){
    const char *chapter=capture.anchor->chapter;
    expect((chapter==nullptr)==(record.chapter==nullptr)&&(!chapter||!std::strcmp(chapter,record.chapter)),std::string(name)+" keeps exact chapter scope");
  }
  if(capture.mode==READER_RS_EPUB_CHAPTER)expect(record.part==part&&!std::strcmp(record.part_path,capture.part_path),std::string(name)+" keeps spine index and path");
  exr_anchor_match match{};reader_rs_status status=resolve(&record,&match);
  size_t start=capture.mode==READER_RS_FIXED_PAGE?capture.fixed->start:capture.anchor->start;
  size_t end=capture.mode==READER_RS_FIXED_PAGE?capture.fixed->end:capture.anchor->end;
  bool correct=expected==EXR_ANCHOR_FOUND?status==READER_RS_OK&&match.state==expected&&match.start==start&&match.end==end:
    status==READER_RS_UNRESOLVED&&match.state==expected;
  expect(correct,std::string(name)+" only exact FOUND permits navigation");
  if(match.state==EXR_ANCHOR_FOUND){receiver_found++;if(match.start!=start||match.end!=end)receiver_mislocated++;}
  cases.push_back(object().str("id",name).str("mode",capture.mode==READER_RS_REFLOW_GLOBAL?"reflow_global":capture.mode==READER_RS_EPUB_CHAPTER?"epub_chapter":"fixed_page")
    .str("kind",kind).set("part",num(part)).set("start",num(start)).set("end",num(end)).str("state",state_name(match.state)).str("revision_id",id)
    .str("entity_key",key).str("wire_sha256",info.sha256).set("wire_bytes",num(exact.size())).dump());
  if(!std::strcmp(kind,"annotation")){final_wire=exact;final_key=key;}
  reader_rs_record_free(&record);
}
void seed_books(){
  for(const char *role:{"txt","epub","pdf","cbz"}){
    std::string title=webdav_root.empty()?std::string(role):"Remote "+std::string(role),author=webdav_root.empty()?"":"云端作者";
    std::string id=new_id(),wire="{\"version\":1,\"id\":"+esc(id)+",\"entity_kind\":\"book\",\"entity_key\":"+esc(keys[role])+",\"operation\":\"put\",\"location_kind\":\"none\",\"parents\":[],\"payload\":{\"format\":"+esc(formats[role])+",\"source_sha256\":"+esc(shas[role])+",\"source_bytes\":"+num(sizes[role])+",\"title\":"+esc(title)+",\"author\":"+esc(author)+",\"favorite\":"+boolean(!webdav_root.empty())+"}}";
    reader_revision_error error{};int created=0;
    if(webdav_root.empty()){
      if(reader_revision_local(A.store,wire.data(),wire.size(),nullptr,&created,&error)!=READER_REV_OK)fatal("book seed");
    }else{int applied=0;
      if(reader_revision_local_project(A.store,wire.data(),wire.size(),nullptr,0,title.c_str(),nullptr,&created,&applied,&error)!=READER_REV_OK||!created||!applied)fatal("atomic local book metadata and outbox");
    }
  }
  transfer(A,B);
}
}
#ifndef READER_V2_ENTRY
#define READER_V2_ENTRY main
#endif
int READER_V2_ENTRY(int argc,char **argv){
  if(v2_c_contract())fatal("v2 C ABI");
  std::string fixtures,font,work,report_path;
  for(int i=1;i+1<argc;i+=2){std::string k=argv[i],v=argv[i+1];
    if(k=="--fixtures")fixtures=v;else if(k=="--font")font=v;else if(k=="--work")work=v;else if(k=="--report")report_path=v;else if(k=="--webdav-root")webdav_root=v;
    else if(k=="--sha"){size_t equal=v.find('=');shas[v.substr(0,equal)]=v.substr(equal+1);}else fatal("unknown argument");}
  const char *roles[][3]={{"txt","book.txt","txt"},{"spacer","spacer.txt","txt"},{"epub","book.epub","epub"},{"pdf","pages.pdf","pdf"},{"cbz","pages.cbz","cbz"}};
  for(auto &r:roles){paths[r[0]]=fixtures+"/"+r[1];formats[r[0]]=r[2];sizes[r[0]]=read_file(paths[r[0]]).size();if(!shas.count(r[0]))fatal("missing digest");keys[r[0]]=std::string(r[2])+":"+shas[r[0]];}
  parser_version=std::string("exreader-sdk-")+exr_version();
  A.lib_path=work+"/A-library.sqlite";A.product_path=work+"/A-product.sqlite";B.lib_path=work+"/B-library.sqlite";B.product_path=work+"/B-product.sqlite";
  transport_work=work;
  open_side(A);open_side(B);import(B,"spacer",EXR_TXT,false);
  for(side *s:{&A,&B}){if(!webdav_root.empty()&&s==&B)continue;import(*s,"txt",EXR_TXT,false);import(*s,"epub",EXR_EPUB,true);import(*s,"pdf",EXR_PDF,true);import(*s,"cbz",EXR_CBZ,true);
    attach(*s,"txt","reflow_global");attach(*s,"epub","epub_chapter");attach(*s,"pdf","fixed_page");attach(*s,"cbz","fixed_page");}
  if(!webdav_root.empty()){
#ifdef READER_V2_WEBDAV_TEST
    std::filesystem::create_directories(std::filesystem::u8path(work+"/A-originals"));
    for(const char *role:{"txt","epub","pdf","cbz"}){std::string destination=work+"/A-originals/"+shas[role]+"."+formats[role];uint64_t bytes=0;exr_error error{};
      if(exr_sideload_export_original(A.lib,A.ids[role],destination.c_str(),nullptr,&bytes,&error)!=EXR_OK||bytes!=sizes[role])fatal("SDK original export before network worker");++originals_exported;}
#else
    fatal("probe was built without original export");
#endif
  }
  seed_books();
  if(!webdav_root.empty()){
    project_received_books();
    auto original_paths=paths;for(const char *role:{"txt","epub","pdf","cbz"})paths[role]=cached_original(role);
    import(B,"txt",EXR_TXT,false);import(B,"epub",EXR_EPUB,true);import(B,"pdf",EXR_PDF,true);import(B,"cbz",EXR_CBZ,true);
    attach(B,"txt","reflow_global");attach(B,"epub","epub_chapter");attach(B,"pdf","fixed_page");attach(B,"cbz","fixed_page");paths=original_paths;
    for(const char *role:{"txt","epub","pdf","cbz"}){
      struct metadata_check {std::string title;int64_t sdk_id;bool ok=false;} observed{"Remote "+std::string(role),B.ids[role],false};int found=0;reader_catalog_error error{};
      if(reader_catalog_find(B.catalog,keys[role].c_str(),nullptr,[](void *context,const reader_catalog_row *row){auto &v=*(metadata_check *)context;
        v.ok=v.title==row->title&&row->favorite==1&&std::string(row->author)=="云端作者"&&v.sdk_id==row->sdk_book_id;return 0;
      },&observed,&found,&error))fatal("received book catalog mapping");
      expect(found&&observed.ok,"actual received original mapping preserves remote title author and favorite");
    }
  }
  exr_document *ta=nullptr,*tb=nullptr;SDK(exr_library_document(A.lib,A.ids["txt"],&ta,&e_));SDK(exr_library_document(B.lib,B.ids["txt"],&tb,&e_));
  size_t text_bytes=0;const char *text=exr_document_text(ta,&text_bytes);std::string t(text,text_bytes);
  exr_anchor existing_progress{};SDK(exr_anchor_create(tb,text_bytes,text_bytes,&existing_progress,&e_));SDK(exr_library_progress(B.lib,B.ids["txt"],&existing_progress,&e_));exr_anchor_free(&existing_progress);
  auto txt=[&](const char *name,const char *kind,size_t start,size_t end,exr_anchor_state expected=EXR_ANCHOR_FOUND){
    exr_anchor anchor{};SDK(exr_anchor_create(ta,start,end,&anchor,&e_));reader_rs_capture capture{};capture.mode=READER_RS_REFLOW_GLOBAL;capture.anchor=&anchor;
    roundtrip(name,"txt",kind,capture,0,[&](const reader_rs_record *r,exr_anchor_match *m){return reader_rs_resolve_reflow(tb,r,nullptr,m,nullptr);},expected);exr_anchor_free(&anchor);};
  txt("txt-progress-start","progress",0,0);size_t emoji=locate(t,"🙂");txt("txt-progress-multibyte","progress",emoji,emoji);
  txt("txt-progress-end","progress",text_bytes,text_bytes);size_t point=locate(t,"Tail alpha");txt("txt-bookmark","annotation",point,point);
  txt("txt-highlight","annotation",emoji,emoji+std::strlen("🙂"));size_t ambiguous=locate(t,"AMBIGUOUS TARGET",1);
  txt("txt-ambiguous","annotation",ambiguous,ambiguous+std::strlen("AMBIGUOUS TARGET"),EXR_ANCHOR_AMBIGUOUS);
  int64_t gaid=0,gbid=0;std::string epub=read_file(paths["epub"]);
  std::string receiver_epub=webdav_root.empty()?epub:read_file(cached_original("epub"));
  SDK(exr_library_import(A.lib,EXR_EPUB,epub.data(),epub.size(),"global",&gaid,&e_));SDK(exr_library_import(B.lib,EXR_EPUB,receiver_epub.data(),receiver_epub.size(),"global",&gbid,&e_));
  exr_document *ga=nullptr,*gb=nullptr;SDK(exr_library_document(A.lib,gaid,&ga,&e_));SDK(exr_library_document(B.lib,gbid,&gb,&e_));
  size_t gn=0;const char *gt=exr_document_text(ga,&gn);size_t chapter=locate(std::string(gt,gn),"第二章节独有文字");
  for(int point_only=0;point_only<2;point_only++){
    exr_anchor anchor{};SDK(exr_anchor_create(ga,chapter,chapter+(point_only?0:std::strlen("第二章节独有文字")),&anchor,&e_));
    expect(anchor.chapter&&anchor.chapter[0],"global EPUB capture has chapter scope");reader_rs_capture capture{};capture.mode=READER_RS_REFLOW_GLOBAL;capture.anchor=&anchor;
    roundtrip(point_only?"epub-global-progress":"epub-global-highlight","epub",point_only?"progress":"annotation",capture,0,
      [&](const reader_rs_record *r,exr_anchor_match *m){return reader_rs_resolve_reflow(gb,r,nullptr,m,nullptr);});exr_anchor_free(&anchor);
  }
  exr_document_free(ga);exr_document_free(gb);
  exr_font *fnt=nullptr;SDK(exr_font_open(font.c_str(),&fnt,&e_));exr_publication *pa=nullptr,*pb=nullptr;
  for(side *s:{&A,&B}){exr_source source{};SDK(exr_library_source(s->lib,s->ids["epub"],&source,&e_));exr_error e{};
    if(exr_publication_open_source(&source,s==&A?&pa:&pb,&e)!=EXR_OK){source.release(source.context);fatal("publication open");}}
  size_t parts_count=0;const exr_part *parts=exr_publication_parts(pa,&parts_count);expect(parts_count==3,"fixture retains repeated spine path");
  for(size_t part=0;part<parts_count;part++){
    exr_layout_config config=exr_layout_config_defaults();exr_chapter_options options=exr_chapter_options_defaults();exr_pager *ap=nullptr,*bp=nullptr;
    SDK(exr_publication_pager_create(pa,part,fnt,&config,&options,&ap,&e_));SDK(exr_publication_pager_create(pb,part,fnt,&config,&options,&bp,&e_));
    exr_anchor anchor{};SDK(exr_pager_anchor_create(ap,0,0,nullptr,&anchor,&e_));reader_rs_capture capture{};capture.mode=READER_RS_EPUB_CHAPTER;capture.anchor=&anchor;capture.part_path=parts[part].path;
    std::string name="epub-bookmark-part-"+num(part);
    auto resolver=[&](const reader_rs_record *r,exr_anchor_match *m){size_t routed=SIZE_MAX;reader_rs_error error{};
      if(reader_rs_epub_record_part(pb,r,&routed,&error)!=READER_RS_OK||routed!=part)return READER_RS_IDENTITY;
      reader_rs_record bad=*r;bad.part=parts_count;
      expect(reader_rs_epub_record_part(pb,&bad,&routed,&error)==READER_RS_IDENTITY,"out-of-range EPUB route is refused");
      return reader_rs_resolve_epub(pb,bp,part,r,nullptr,m,&error);};
    roundtrip(name.c_str(),"epub","annotation",capture,part,resolver);
    if(part==1)roundtrip("epub-chapter-progress","epub","progress",capture,part,resolver);
    exr_anchor_free(&anchor);exr_pager_free(ap);exr_pager_free(bp);
  }
  exr_publication_free(pa);exr_publication_free(pb);exr_font_free(fnt);
  for(const char *role:{"pdf","cbz"}){
    exr_fixed_open_options options{};options.struct_size=sizeof(options);exr_fixed_document *fa=nullptr,*fb=nullptr;
    SDK(exr_library_fixed(A.lib,A.ids[role],&options,&fa,&e_));SDK(exr_library_fixed(B.lib,B.ids[role],&options,&fb,&e_));
    size_t pc=0;const exr_fixed_page *pages=exr_fixed_pages(fa,&pc);
    auto fixed=[&](const char *name,const char *kind,size_t page,size_t start,size_t end){
      exr_fixed_text *page_text=nullptr;SDK(exr_fixed_load_text(fa,page,nullptr,&page_text,&e_));exr_fixed_anchor anchor{};SDK(exr_fixed_anchor_create(pages[page].id,page_text,start,end,&anchor,&e_));
      reader_rs_capture capture{};capture.mode=READER_RS_FIXED_PAGE;capture.fixed=&anchor;capture.page=page;
      roundtrip(name,role,kind,capture,0,[&](const reader_rs_record *r,exr_anchor_match *m){size_t resolved=SIZE_MAX;return reader_rs_resolve_fixed(fb,r,nullptr,&resolved,m,nullptr);});
      exr_fixed_anchor_free(&anchor);exr_fixed_text_free(page_text);};
    if(!std::strcmp(role,"pdf")){
      exr_fixed_text *p=nullptr;SDK(exr_fixed_load_text(fa,0,nullptr,&p,&e_));size_t pn=0;const char *pt=exr_fixed_text_string(p,&pn);
      size_t at=locate(std::string(pt,pn),"Shared quote across pages.");exr_fixed_text_free(p);
      fixed("pdf-highlight","annotation",0,at,at+std::strlen("Shared quote across pages."));fixed("pdf-bookmark","annotation",0,at,at);
      fixed("pdf-textless-bookmark","annotation",2,0,0);fixed("pdf-progress","progress",1,0,0);
    }else{fixed("cbz-bookmark","annotation",1,0,0);fixed("cbz-progress","progress",1,0,0);}
    exr_fixed_free(fa);exr_fixed_free(fb);
  }
  expect(count_notes(B,B.ids["txt"])==0&&count_notes(B,gbid)==0&&count_epub(B,B.ids["epub"])==0&&count_fixed(B,B.ids["pdf"])==0&&count_fixed(B,B.ids["cbz"])==0,"product-owned annotations create zero SDK note copies");
  exr_document_free(ta);exr_document_free(tb);close_side(B);open_side(B);
  char *persisted=nullptr;size_t persisted_size=0;reader_revision_selection selection{};
  expect(reader_revision_selected(B.store,"annotation",final_key.c_str(),&persisted,&persisted_size,nullptr,&selection,nullptr)==READER_REV_OK&&std::string(persisted,persisted_size)==final_wire,"global annotation survives actual library/catalog reopen without note adoption");
  reader_revision_bytes_free(persisted);exr_anchor progress{};exr_anchor_state state{};SDK(exr_library_progress_get(B.lib,B.ids["txt"],&progress,&state,&e_));
  expect(progress.start==text_bytes,"remote progress and annotations never change receiver active progress");exr_anchor_free(&progress);
  expect(cases.size()==18&&receiver_found==17&&receiver_mislocated==0,"all eighteen real captures have exact expected outcomes");
  close_side(A);close_side(B);
  object report;report.set("cases",array(cases)).set("checks",array(checks)).set("failures",num(failures)).set("receiver_found",num(receiver_found)).set("receiver_mislocated",num(receiver_mislocated))
    .set("native_webdav",boolean(!webdav_root.empty())).set("network_pushed",num(network_pushed)).set("network_pulled",num(network_pulled)).set("originals_exported",num(originals_exported)).set("metadata_projected",num(metadata_projected));
  std::ofstream output(report_path,std::ios::binary);output<<report.dump()<<"\n";return failures?1:0;
}
