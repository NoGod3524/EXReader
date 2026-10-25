/* SPDX-License-Identifier: MIT */
#include "reading_internal.h"

namespace {
void check_sdk(exr_status status,const char *message){if(status!=EXR_OK)reject(READER_RS_SDK,message,READER_RS_GAP_NONE,(int)status);}
void require_selector(const reader_rs_record *r,reader_rs_mode mode){
  if(!r||!r->has_location||r->mode!=mode||!r->exact)reject(READER_RS_ARGUMENT,"Record has no selector for this reading mode");
#ifdef EXR_READER_SELECTOR_BYTES_CANDIDATE
  if(r->anchor_version==3)reject(READER_RS_ARGUMENT,"Anchor3 requires the explicit candidate resolver");
#endif
  if(r->end<r->start||r->end-r->start!=r->exact_size)reject(READER_RS_ARGUMENT,"Wire offset hints disagree with the quote length");
  if(r->start>SIZE_MAX||r->end>SIZE_MAX)reject(READER_RS_ARGUMENT,"Selector exceeds this host's address range");
}
void require_note(const reader_rs_record *r,reader_rs_mode mode){
  if(!r||std::strcmp(r->entity_kind,"annotation")||!std::strcmp(r->operation,"delete"))reject(READER_RS_ARGUMENT,"Only annotation put/restore records create SDK notes");
  require_selector(r,mode);
}
exr_anchor text_anchor(const reader_rs_record *r,const char *chapter){
  exr_anchor a{};a.start=(size_t)r->start;a.end=(size_t)r->end;
  a.exact=r->exact;a.prefix=r->prefix;a.suffix=r->suffix;a.chapter=const_cast<char *>(chapter);return a;
}
void found(const exr_anchor_match &m){if(m.state!=EXR_ANCHOR_FOUND)reject(READER_RS_UNRESOLVED,"Public resolve did not return FOUND; original record retained");}
void resolve_reflow(const exr_document *doc,const reader_rs_record *r,const exr_control *control,exr_anchor_match *match){
  if(!doc||!match)reject(READER_RS_ARGUMENT,"Missing document or match output");
  require_selector(r,READER_RS_REFLOW_GLOBAL);
  exr_anchor a=text_anchor(r,r->anchor_version==2?r->chapter:nullptr);exr_error e{};
  check_sdk(exr_anchor_resolve_ex(doc,&a,control,match,&e),"Public reflow resolve failed");found(*match);
}
size_t epub_part(const exr_publication *pub,const char *path){
  if(!pub||!path)reject(READER_RS_ARGUMENT,"Missing publication or part path");
  size_t count=0,hits=0,part=SIZE_MAX;const exr_part *parts=exr_publication_parts(pub,&count);
  for(size_t i=0;i<count;i++)if(parts[i].path&&!std::strcmp(parts[i].path,path)){hits++;part=i;}
  if(hits!=1)reject(READER_RS_IDENTITY,hits?"EPUB part path repeats in the spine; part is ambiguous":"EPUB part path is absent from this package",READER_RS_GAP_ROUTE);
  return part;
}
size_t record_part(const exr_publication *pub,const reader_rs_record *r){
  if(!pub||!r||r->mode!=READER_RS_EPUB_CHAPTER||!r->part_path)reject(READER_RS_ARGUMENT,"Missing EPUB record route");
  if(r->anchor_version==1)return epub_part(pub,r->part_path);
  size_t count=0;const exr_part *parts=exr_publication_parts(pub,&count);
  if(r->anchor_version!=2||r->part>=count||!parts[r->part].path||std::strcmp(parts[r->part].path,r->part_path))
    reject(READER_RS_IDENTITY,"EPUB spine index and path disagree",READER_RS_GAP_ROUTE);
  return (size_t)r->part;
}
void resolve_epub(const exr_publication *pub,exr_pager *pager,size_t part,const reader_rs_record *r,const exr_control *control,exr_anchor_match *match){
  if(!pager||!match)reject(READER_RS_ARGUMENT,"Missing pager or match output");
  require_selector(r,READER_RS_EPUB_CHAPTER);
  if(record_part(pub,r)!=part)reject(READER_RS_IDENTITY,"Pager part differs from the record part path",READER_RS_GAP_ROUTE);
  exr_anchor a=text_anchor(r,r->part_path);exr_error e{};
  check_sdk(exr_pager_anchor_resolve(pager,&a,control,match,&e),"Public bounded-pager resolve failed");found(*match);
}
size_t fixed_page(exr_fixed_document *doc,const char *page_id){
  if(!doc||!page_id)reject(READER_RS_ARGUMENT,"Missing fixed document or page ID");
  size_t count=0,hits=0,page=SIZE_MAX;const exr_fixed_page *pages=exr_fixed_pages(doc,&count);
  for(size_t i=0;i<count;i++)if(pages[i].id&&!std::strcmp(pages[i].id,page_id)){hits++;page=i;}
  if(hits!=1)reject(READER_RS_IDENTITY,"Fixed page ID is not unique in this original");
  return page;
}
size_t resolve_fixed(exr_fixed_document *doc,const reader_rs_record *r,const exr_control *control,exr_anchor_match *match,bool raw=false){
  if(!match)reject(READER_RS_ARGUMENT,"Missing match output");
  if(raw){
    if(!r||r->anchor_version!=3||r->mode!=READER_RS_FIXED_PAGE||!r->has_location||!r->exact||r->end<r->start||r->end-r->start!=r->exact_size||r->start>SIZE_MAX||r->end>SIZE_MAX)
      reject(READER_RS_ARGUMENT,"Invalid fixed anchor3 selector");
  }else require_selector(r,READER_RS_FIXED_PAGE);
  size_t page=fixed_page(doc,r->page_id);
  if(page!=r->page)reject(READER_RS_IDENTITY,"Page-number hint disagrees with the page ID; no page is guessed");
  exr_fixed_text *text=nullptr;exr_error e{};
  check_sdk(exr_fixed_load_text(doc,page,control,&text,&e),"Public fixed text load failed");
  exr_fixed_anchor a{};a.start=(size_t)r->start;a.end=(size_t)r->end;a.page_id=r->page_id;
  a.exact=r->exact;a.prefix=r->prefix;a.suffix=r->suffix;a.exact_size=r->exact_size;a.prefix_size=r->prefix_size;a.suffix_size=r->suffix_size;
  exr_status status=exr_fixed_anchor_resolve(r->page_id,text,&a,control,match,&e);exr_fixed_text_free(text);
  check_sdk(status,"Public fixed resolve failed");found(*match);return page;
}
}

extern "C" reader_rs_status reader_rs_resolve_reflow(const exr_document *doc,const reader_rs_record *r,const exr_control *control,exr_anchor_match *match,reader_rs_error *error){
  return call(error,[&]{resolve_reflow(doc,r,control,match);});
}
extern "C" reader_rs_status reader_rs_epub_part(const exr_publication *pub,const char *path,size_t *part,reader_rs_error *error){
  if(part)*part=SIZE_MAX;
  return call(error,[&]{if(!part)reject(READER_RS_ARGUMENT,"Missing part output");*part=epub_part(pub,path);});
}
extern "C" reader_rs_status reader_rs_resolve_epub(const exr_publication *pub,exr_pager *pager,size_t part,const reader_rs_record *r,const exr_control *control,exr_anchor_match *match,reader_rs_error *error){
  return call(error,[&]{resolve_epub(pub,pager,part,r,control,match);});
}
extern "C" reader_rs_status reader_rs_epub_record_part(const exr_publication *pub,const reader_rs_record *r,size_t *part,reader_rs_error *error){
  if(part)*part=SIZE_MAX;
  return call(error,[&]{if(!part)reject(READER_RS_ARGUMENT,"Missing EPUB part output");*part=record_part(pub,r);});
}
extern "C" reader_rs_status reader_rs_fixed_page(exr_fixed_document *doc,const char *page_id,size_t *page,reader_rs_error *error){
  if(page)*page=SIZE_MAX;
  return call(error,[&]{if(!page)reject(READER_RS_ARGUMENT,"Missing page output");*page=fixed_page(doc,page_id);});
}
extern "C" reader_rs_status reader_rs_resolve_fixed(exr_fixed_document *doc,const reader_rs_record *r,const exr_control *control,size_t *page,exr_anchor_match *match,reader_rs_error *error){
  if(page)*page=SIZE_MAX;
  return call(error,[&]{size_t found_page=resolve_fixed(doc,r,control,match);if(page)*page=found_page;});
}
#ifdef EXR_READER_SELECTOR_BYTES_CANDIDATE
extern "C" reader_rs_status reader_rs_resolve_fixed_v3(exr_fixed_document *doc,const reader_rs_record *r,const exr_control *control,size_t *page,exr_anchor_match *match,reader_rs_error *error){
  if(page)*page=SIZE_MAX;
  if(match){match->state=EXR_ANCHOR_MISSING;match->start=match->end=SIZE_MAX;}
  return call(error,[&]{size_t n=resolve_fixed(doc,r,control,match,true);if(page)*page=n;});
}
#endif
extern "C" reader_rs_status reader_rs_store_reflow_note(exr_library *lib,int64_t book,const exr_document *doc,const reader_rs_record *r,int64_t existing,int64_t *id,exr_anchor_match *match,reader_rs_error *error){
  if(id)*id=0;
  return call(error,[&]{
    if(!lib||book<=0||existing<0||!id)reject(READER_RS_ARGUMENT,"Missing SDK note target");
    require_note(r,READER_RS_REFLOW_GLOBAL);exr_anchor_match local{};exr_anchor_match *m=match?match:&local;resolve_reflow(doc,r,nullptr,m);
    exr_note note{};note.id=existing;note.book_id=book;note.start=m->start;note.end=m->end;note.text=r->note_text?r->note_text:const_cast<char *>("");
    exr_error e{};check_sdk(exr_library_note(lib,&note,id,&e),"Public SDK note write failed");
  });
}
extern "C" reader_rs_status reader_rs_store_epub_note(exr_library *lib,int64_t book,const exr_publication *pub,exr_pager *pager,size_t part,const reader_rs_record *r,int64_t existing,int64_t *id,exr_anchor_match *match,reader_rs_error *error){
  if(id)*id=0;
  return call(error,[&]{
    if(!lib||book<=0||existing<0||!id)reject(READER_RS_ARGUMENT,"Missing SDK note target");
    require_note(r,READER_RS_EPUB_CHAPTER);exr_anchor_match local{};exr_anchor_match *m=match?match:&local;resolve_epub(pub,pager,part,r,nullptr,m);
    exr_anchor selector{};exr_error e{};
    check_sdk(exr_pager_anchor_create(pager,m->start,m->end,nullptr,&selector,&e),"Public bounded-pager capture failed");
    if(!selector.exact||std::strlen(selector.exact)!=r->exact_size||std::memcmp(selector.exact,r->exact,r->exact_size)){exr_anchor_free(&selector);reject(READER_RS_IDENTITY,"Recaptured quote differs from the FOUND record");}
    exr_epub_note note{};note.id=existing;note.book_id=book;note.location.part=part;note.location.path=r->part_path;note.location.selector=selector;
    note.text=r->note_text?r->note_text:const_cast<char *>("");
    exr_status status=exr_library_epub_note(lib,&note,id,&e);exr_anchor_free(&selector);
    check_sdk(status,"Public SDK EPUB note write failed");
  });
}
extern "C" reader_rs_status reader_rs_store_fixed_note(exr_library *lib,int64_t book,exr_fixed_document *doc,const reader_rs_record *r,int64_t existing,int64_t *id,exr_anchor_match *match,reader_rs_error *error){
  if(id)*id=0;
  return call(error,[&]{
    if(!lib||book<=0||existing<0||!id)reject(READER_RS_ARGUMENT,"Missing SDK note target");
    require_note(r,READER_RS_FIXED_PAGE);exr_anchor_match local{};exr_anchor_match *m=match?match:&local;size_t page=resolve_fixed(doc,r,nullptr,m);
    exr_fixed_note note{};note.id=existing;note.book_id=book;note.page=page;note.start=m->start;note.end=m->end;
    note.text=r->note_text?r->note_text:const_cast<char *>("");
    exr_error e{};check_sdk(exr_library_fixed_note(lib,&note,nullptr,id,&e),"Public SDK fixed note write failed");
  });
}
