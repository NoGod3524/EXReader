/* Reuse the unchanged public SDK snapshot functions from the complete peer
 * consumer; no SQL connection to the SDK database is introduced. */
#define main original_peer_consumer_main
#include "../reader_windows_raw3/peer-owner/probe.cpp"
#undef main

namespace {
std::string field_json(const char *value) { return value?quote(value):"null"; }
std::string anchor_json(const exr_anchor &anchor) {
  return "{\"start\":"+std::to_string(anchor.start)+",\"end\":"+std::to_string(anchor.end)+
    ",\"exact\":"+field_json(anchor.exact)+",\"prefix\":"+field_json(anchor.prefix)+
    ",\"suffix\":"+field_json(anchor.suffix)+",\"chapter\":"+field_json(anchor.chapter)+"}";
}
struct SplitState { std::string metadata,notes,sources,progress_json,sources_json; };
void validate_public_point(exr_document *document,const exr_anchor &point,exr_error &error) {
  need(point.start==point.end,"stored public progress is a point");
  exr_anchor captured{};auto status=exr_anchor_create(document,point.start,point.end,&captured,&error);
  exr_anchor_free(&captured);need(status==EXR_OK,error.message);
}
SplitState split_state(const fs::path &path) {
  Library sdk(path);exr_book *books=nullptr;size_t count=0;exr_error error{};
  need(exr_library_books(sdk.p,nullptr,&books,&count,&error)==EXR_OK,error.message);
  SplitState out;out.progress_json="[";out.sources_json="[";
  std::vector<exr_book *> ordered;for(size_t i=0;i<count;i++)ordered.push_back(&books[i]);
  std::sort(ordered.begin(),ordered.end(),[](const exr_book *a,const exr_book *b){return a->id<b->id;});
  bool first=true;
  for(const auto *book:ordered) {
    const auto &b=*book;auto id=std::to_string(b.id);
    out.metadata+=id+":"+std::to_string(b.format)+":"+std::to_string(b.status)+":"+std::to_string(b.favorite)+":";
    append(out.metadata,b.title);append(out.metadata,b.author);append(out.metadata,b.tags);
    Source source;need(exr_library_source(sdk.p,b.id,&source.s,&error)==EXR_OK,error.message);
    need(source.s.size<=128*1024*1024,"bounded public original readback");
    std::string bytes((size_t)source.s.size,'\0');size_t at=0;
    while(at<bytes.size()) {auto request=std::min<size_t>(65536,bytes.size()-at);auto n=source.s.read_at(source.s.context,at,&bytes[at],request);need(n&&n<=request,"complete public original readback");at+=n;}
    auto source_hash=sha(bytes);auto format=b.format==EXR_TXT?"txt":b.format==EXR_EPUB?"epub":b.format==EXR_PDF?"pdf":b.format==EXR_CBZ?"cbz":"unsupported";
    need(std::strcmp(format,"unsupported")!=0,"fixed received four-format scope");
    out.sources+=id+":"+format+":"+std::to_string(bytes.size())+":"+source_hash+";";
    if(!first) {out.progress_json+=",";out.sources_json+=",";}first=false;
    out.sources_json+="{\"book_id\":"+id+",\"format\":"+quote(format)+",\"bytes\":"+std::to_string(bytes.size())+",\"sha256\":"+quote(source_hash)+"}";
    std::string progress="{\"book_id\":"+id+",\"format\":"+quote(format)+",\"position\":"+std::to_string(b.position);
    out.notes+=id+":";
    if(b.format==EXR_PDF||b.format==EXR_CBZ) {
      Objects objects;need(exr_library_fixed_source(sdk.p,b.id,nullptr,&objects.fixed,&error)==EXR_OK,error.message);
      size_t pages=0;need(exr_fixed_pages(objects.fixed,&pages)!=nullptr&&b.position<pages,"valid public fixed page position");
      progress+=",\"kind\":\"fixed\",\"page_count\":"+std::to_string(pages);
      exr_fixed_note *notes=nullptr;size_t n=0;need(exr_library_fixed_notes(sdk.p,b.id,&notes,&n,&error)==EXR_OK,error.message);
      out.notes+="fixed:"+std::to_string(n)+":";
      for(size_t j=0;j<n;j++) {const auto &x=notes[j];out.notes+=std::to_string(x.id)+":"+std::to_string(x.book_id)+":"+std::to_string(x.page)+":"+std::to_string(x.start)+":"+std::to_string(x.end)+":"+std::to_string(x.anchor.start)+":"+std::to_string(x.anchor.end)+":";append(out.notes,x.text);append(out.notes,x.anchor.page_id);out.notes+=serialized(blob(x.anchor.exact,x.anchor.exact_size))+serialized(blob(x.anchor.prefix,x.anchor.prefix_size))+serialized(blob(x.anchor.suffix,x.anchor.suffix_size));}
      exr_fixed_notes_free(notes,n);
    } else {
      exr_library_epub_info info{};info.struct_size=sizeof(info);bool bounded=false;
      if(b.format==EXR_EPUB) {need(exr_library_epub_info_get(sdk.p,b.id,&info,&error)==EXR_OK,error.message);bounded=info.bounded_storage!=0;}
      if(bounded) {
        exr_epub_location location{};int present=0;need(exr_library_epub_progress_get(sdk.p,b.id,&location,&present,&error)==EXR_OK,error.message);
        progress+=",\"kind\":\"epub\",\"present\":"+std::to_string(present)+",\"part\":"+std::to_string(location.part)+",\"path\":"+field_json(location.path)+",\"selector\":"+anchor_json(location.selector);
        if(present) {
          Objects objects;Source original;
          need(exr_library_source(sdk.p,b.id,&original.s,&error)==EXR_OK,error.message);
          need(exr_publication_open_source(&original.s,&objects.pub,&error)==EXR_OK,error.message);original.s.release=nullptr;
          size_t parts_count=0;auto parts=exr_publication_parts(objects.pub,&parts_count);
          need(parts&&location.part<parts_count&&location.path&&parts[location.part].path&&std::strcmp(parts[location.part].path,location.path)==0,"actual public EPUB progress route");
          need(exr_publication_load(objects.pub,location.part,&objects.doc,&error)==EXR_OK,error.message);
          validate_public_point(objects.doc,location.selector,error);
        }
        exr_epub_location_free(&location);
        exr_epub_note *notes=nullptr;size_t n=0;need(exr_library_epub_notes(sdk.p,b.id,&notes,&n,&error)==EXR_OK,error.message);
        out.notes+="epub:"+std::to_string(n)+":";
        for(size_t j=0;j<n;j++) {const auto &x=notes[j];out.notes+=std::to_string(x.id)+":"+std::to_string(x.book_id)+":"+std::to_string(x.location.part)+":";append(out.notes,x.text);append(out.notes,x.location.path);anchor_state(out.notes,x.location.selector);}
        exr_epub_notes_free(notes,n);
      } else {
        exr_anchor anchor{};exr_anchor_state state{};need(exr_library_progress_get(sdk.p,b.id,&anchor,&state,&error)==EXR_OK,error.message);
        Objects objects;need(exr_library_document(sdk.p,b.id,&objects.doc,&error)==EXR_OK,error.message);
        need(anchor.start==b.position,"actual public global position");validate_public_point(objects.doc,anchor,error);
        progress+=",\"kind\":\"global\",\"state\":"+std::to_string(state)+",\"selector\":"+anchor_json(anchor);exr_anchor_free(&anchor);
        exr_note *notes=nullptr;size_t n=0;need(exr_library_notes(sdk.p,b.id,&notes,&n,&error)==EXR_OK,error.message);
        out.notes+="global:"+std::to_string(n)+":";
        for(size_t j=0;j<n;j++) {const auto &x=notes[j];out.notes+=std::to_string(x.id)+":"+std::to_string(x.book_id)+":"+std::to_string(x.start)+":"+std::to_string(x.end)+":";append(out.notes,x.text);anchor_state(out.notes,x.anchor);}
        exr_notes_free(notes,n);
      }
    }
    out.progress_json+=progress+",\"validated_public_state\":true}";
  }
  exr_books_free(books,count);out.progress_json+="]";out.sources_json+="]";
  out.metadata=sha(out.metadata);out.notes=sha(out.notes);out.sources=sha(out.sources);return out;
}
}

int main(int argc,char **argv) {
  if(argc!=3) return 2;
  try {
    need(std::getenv("GITHUB_ACTIONS") && std::string(std::getenv("GITHUB_ACTIONS"))=="true","Actions only");
    need(std::getenv("GITHUB_SHA") && std::string(std::getenv("GITHUB_SHA"))==PROBE_SOURCE_SHA,"actual compiled source");
    need(std::strcmp(exr_version(),"3.41.0")==0,"actual installed SDK version");
    fs::path profile=fs::u8path(argv[1]),output=fs::u8path(argv[2]);
    auto sdk=sdk_state(profile/"library.sqlite");
    auto split=split_state(profile/"library.sqlite");
    auto product=product_state(profile/"library.sqlite.product.sqlite");
    wchar_t executable[32768];auto size=GetModuleFileNameW(nullptr,executable,32768);
    need(size&&size<32768,"actual executable path");
    auto program=sha(read(fs::path(std::wstring(executable,size))));
    std::ofstream stream(output,std::ios::binary);
    stream<<"{\"source_sha\":"<<quote(PROBE_SOURCE_SHA)<<",\"owner_source_sha256\":"<<quote(PROBE_OWNER_SHA)
      <<",\"program_sha256\":"<<quote(program)<<",\"pid\":"<<GetCurrentProcessId()
      <<",\"run_id\":"<<quote(std::getenv("GITHUB_RUN_ID")?std::getenv("GITHUB_RUN_ID"):"")
      <<",\"attempt\":"<<quote(std::getenv("GITHUB_RUN_ATTEMPT")?std::getenv("GITHUB_RUN_ATTEMPT"):"")
      <<",\"sdk_version\":"<<quote(exr_version())
      <<",\"sdk_public_state\":"<<quote(sdk)<<",\"product_readonly_state\":"<<quote(product)
      <<",\"metadata_without_progress_sha256\":"<<quote(split.metadata)<<",\"notes_sha256\":"<<quote(split.notes)
      <<",\"originals_sha256\":"<<quote(split.sources)<<",\"originals\":"<<split.sources_json
      <<",\"public_progress\":"<<split.progress_json<<"}\n";
    stream.flush();need(bool(stream),"state report write");
    return 0;
  } catch(const std::exception &e) { std::cerr<<e.what()<<'\n';return 1; }
}
