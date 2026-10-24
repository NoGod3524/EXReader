/* SPDX-License-Identifier: MIT */
#include "reader_navigation.h"
#include <cctype>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <memory>
#include <new>
#include <string>
#include <utility>
#include <vector>

namespace {
const uint64_t NONE=READER_NAVIGATION_NONE;
struct failure { reader_navigation_status code; int sdk; std::string message; };
struct soft { reader_navigation_status code=READER_NAVIGATION_OK; const char *message=""; };
[[noreturn]] void reject(reader_navigation_status code,const std::string &message,int sdk=0){throw failure{code,sdk,message};}
reader_navigation_status report(reader_navigation_error *e,const failure &f){
  if(e){e->code=f.code;e->sdk_code=f.sdk;std::snprintf(e->message,sizeof(e->message),"%s",f.message.c_str());}
  return f.code;
}
/* Every public call clears its error, runs inside one try block and reports the first
   failure. A lambda returns a `soft` status when it produced a usable output together
   with a documented caveat (PART_ONLY, AMBIGUOUS). */
template<class Function>reader_navigation_status call(reader_navigation_error *e,Function function){
  if(e)std::memset(e,0,sizeof(*e));
  try{
    soft s=function();
    if(s.code!=READER_NAVIGATION_OK&&e){e->code=s.code;std::snprintf(e->message,sizeof(e->message),"%s",s.message);}
    return s.code;
  }
  catch(const failure &f){return report(e,f);}
  catch(...){return report(e,failure{READER_NAVIGATION_MEMORY,0,"Cannot allocate navigation memory"});}
}
/* damaged: whether SDK ARGUMENT also means a bad target (CFI text, fragment escape). */
[[noreturn]] void sdk_fail(exr_status status,const char *what,const exr_error &se,bool damaged){
  std::string message=what;
  if(se.message[0]){message+=": ";message+=se.message;}
  switch(status){
    case EXR_CANCELLED:reject(READER_NAVIGATION_CANCELLED,message,(int)status);
    case EXR_MEMORY:reject(READER_NAVIGATION_MEMORY,message,(int)status);
    case EXR_LIMIT:reject(READER_NAVIGATION_LIMIT,message,(int)status);
    case EXR_FORMAT:case EXR_ENCODING:reject(READER_NAVIGATION_CORRUPT,message,(int)status);
    case EXR_ARGUMENT:
      if(damaged)reject(READER_NAVIGATION_CORRUPT,message,(int)status);
      reject(READER_NAVIGATION_SDK,message,(int)status);
    default:reject(READER_NAVIGATION_SDK,message,(int)status);
  }
}
char *dup(const std::string &s){
  char *p=(char *)std::malloc(s.size()+1);
  if(!p)throw std::bad_alloc();
  std::memcpy(p,s.data(),s.size());p[s.size()]=0;return p;
}
uint64_t fnv(uint64_t h,const void *data,size_t n){
  const unsigned char *p=(const unsigned char *)data;
  for(size_t i=0;i<n;i++){h^=p[i];h*=1099511628211ull;}
  return h;
}
uint64_t fnv_text(uint64_t h,const char *s){
  size_t n=s?std::strlen(s):0;
  h=fnv(h,s?s:"",n);
  unsigned char zero=0;return fnv(h,&zero,1);
}

/* Cooperative cancellation for one call; the control's context is borrowed for that call. */
struct canceller {
  exr_control control{};
  const exr_control *ptr()const{return control.cancelled||control.progress?&control:nullptr;}
  void poll()const{if(control.cancelled&&control.cancelled(control.context))reject(READER_NAVIGATION_CANCELLED,"Navigation cancelled by the caller",(int)EXR_CANCELLED);}
};

struct row_data {
  uint64_t parent=NONE,part=NONE;
  uint32_t depth=0,child_count=0,target_class=READER_NAVIGATION_TARGET_NONE;
  std::string label,href,base,role,part_path,part_id;
};
struct limits { uint32_t nodes,depth; uint64_t text; };
struct unit { const char *path; const char *id; };
}

struct reader_navigation {
  reader_navigation_kind kind=READER_NAVIGATION_AUTHORED;
  reader_navigation_source source=READER_NAVIGATION_FROM_PUBLICATION;
  std::vector<row_data> rows;
  std::vector<std::vector<uint64_t>> kids; /* kids[rows.size()] lists the roots */
  uint64_t text_bytes=0,depth_levels=0,part_count=0,identity=0;
  int busy=0;
};

namespace {
struct busy_guard {
  reader_navigation &n;
  explicit busy_guard(reader_navigation &x):n(x){
    if(n.busy)reject(READER_NAVIGATION_BUSY,"Reentrant call on a navigation snapshot");
    n.busy=1;
  }
  ~busy_guard(){n.busy=0;}
};

limits make_limits(const reader_navigation_options *o,canceller &c){
  limits l{READER_NAVIGATION_NODES_MAX,READER_NAVIGATION_DEPTH_MAX,READER_NAVIGATION_TEXT_MAX};
  if(!o)return l;
  if(o->struct_size!=sizeof(*o))reject(READER_NAVIGATION_ARGUMENT,"options.struct_size differs from sizeof(reader_navigation_options)");
  if(o->max_nodes>READER_NAVIGATION_NODES_MAX||o->max_depth>READER_NAVIGATION_DEPTH_MAX||o->max_text_bytes>READER_NAVIGATION_TEXT_MAX)
    reject(READER_NAVIGATION_ARGUMENT,"A limit option exceeds the compile-time maximum");
  if(o->max_nodes)l.nodes=o->max_nodes;
  if(o->max_depth)l.depth=o->max_depth;
  if(o->max_text_bytes)l.text=o->max_text_bytes;
  c.control=o->control;
  return l;
}

/* Classification only looks at the shape of the text; it never fetches or opens anything. */
uint32_t classify(const char *href){
  if(!href||!*href)return READER_NAVIGATION_TARGET_NONE;
  if(href[0]=='/'&&href[1]=='/')return READER_NAVIGATION_TARGET_EXTERNAL;
  if(std::isalpha((unsigned char)href[0])){
    size_t i=1;
    while(std::isalnum((unsigned char)href[i])||href[i]=='+'||href[i]=='-'||href[i]=='.')i++;
    if(href[i]==':')return READER_NAVIGATION_TARGET_EXTERNAL;
  }
  return READER_NAVIGATION_TARGET_LOCAL;
}

void add_text(reader_navigation &n,const limits &l,std::string &dst,const char *src){
  size_t len=src?std::strlen(src):0;
  if((uint64_t)len>=l.text||n.text_bytes+len+1>l.text)
    reject(READER_NAVIGATION_LIMIT,"Navigation text exceeds the checked limit");
  dst.assign(src?src:"",len);
  n.text_bytes+=len+1;
}

void finish_tree(reader_navigation &n){
  n.kids.assign(n.rows.size()+1,std::vector<uint64_t>());
  for(size_t i=0;i<n.rows.size();i++){
    uint64_t p=n.rows[i].parent;
    n.kids[p==NONE?n.rows.size():(size_t)p].push_back(i);
  }
  for(size_t i=0;i<n.rows.size();i++)n.rows[i].child_count=(uint32_t)n.kids[i].size();
}

uint64_t book_identity(const std::vector<unit> &units){
  uint64_t h=14695981039346656037ull;
  for(const unit &u:units){h=fnv_text(h,u.path);h=fnv_text(h,u.id);}
  return h;
}

void copy_authored(reader_navigation &n,const exr_navigation *entries,size_t count,const std::vector<unit> &units,
                   const limits &l,const canceller &c){
  if(count>l.nodes)reject(READER_NAVIGATION_LIMIT,"Navigation has more rows than the checked limit");
  n.part_count=units.size();n.identity=book_identity(units);
  n.rows.reserve(count);
  for(size_t i=0;i<count;i++){
    if(!(i&255))c.poll();
    const exr_navigation &e=entries[i];
    row_data r;
    if(e.parent!=SIZE_MAX&&e.parent>=i)reject(READER_NAVIGATION_CORRUPT,"A navigation parent does not precede its child");
    if(e.part!=SIZE_MAX&&e.part>=units.size())reject(READER_NAVIGATION_CORRUPT,"A navigation part is outside the book");
    r.parent=e.parent==SIZE_MAX?NONE:(uint64_t)e.parent;
    r.part=e.part==SIZE_MAX?NONE:(uint64_t)e.part;
    r.depth=r.parent==NONE?0:n.rows[(size_t)r.parent].depth+1;
    if(r.depth>=l.depth)reject(READER_NAVIGATION_LIMIT,"Navigation is nested deeper than the checked limit");
    if(r.depth+1>n.depth_levels)n.depth_levels=r.depth+1;
    add_text(n,l,r.label,e.label);add_text(n,l,r.href,e.href);add_text(n,l,r.base,e.base);add_text(n,l,r.role,e.role);
    r.target_class=classify(e.href);
    if(r.part!=NONE){
      add_text(n,l,r.part_path,units[(size_t)r.part].path);
      add_text(n,l,r.part_id,units[(size_t)r.part].id);
    }
    n.rows.push_back(std::move(r));
  }
  finish_tree(n);
}

void authored_snapshot(reader_navigation_source source,exr_status status,const exr_navigation *entries,size_t count,
                       const exr_error &se,const std::vector<unit> &units,const limits &l,const canceller &c,
                       std::unique_ptr<reader_navigation> &out){
  if(status!=EXR_OK)sdk_fail(status,"The SDK could not read the book's navigation",se,false);
  c.poll();
  std::unique_ptr<reader_navigation> n(new reader_navigation);
  n->kind=READER_NAVIGATION_AUTHORED;n->source=source;
  copy_authored(*n,entries,count,units,l,c);
  out=std::move(n);
}

/* --- target helpers -------------------------------------------------------------------- */
int hex(char c){return std::isdigit((unsigned char)c)?c-'0':std::tolower((unsigned char)c)-'a'+10;}
/* Same shape as the SDK's local-path rule: no '?', no scheme, no leading '/', no
   backslash, percent escapes decoded, "." and ".." folded and never above the root.
   Used only to explain an SDK-unresolved target and to check an explicit identity; a
   part the SDK did resolve is taken from the SDK. */
bool normalize(const std::string &base,const std::string &href,std::string &out){
  size_t hash=href.find('#');
  std::string h=href.substr(0,hash==std::string::npos?href.size():hash);
  if(h.find('?')!=std::string::npos||h.size()>=2048)return false;
  std::string d;
  for(size_t i=0;i<h.size();i++){
    unsigned char c=(unsigned char)h[i];
    if(c=='%'){
      if(h.size()-i<3||!std::isxdigit((unsigned char)h[i+1])||!std::isxdigit((unsigned char)h[i+2]))return false;
      c=(unsigned char)(hex(h[i+1])*16+hex(h[i+2]));i+=2;
    }
    if(c<32||c==127)return false;
    d.push_back((char)c);
  }
  if(!d.empty()&&d[0]=='/')return false;
  if(d.find(':')!=std::string::npos||d.find('\\')!=std::string::npos)return false;
  std::string joined;
  if(d.empty())joined=base;
  else{
    size_t slash=base.rfind('/');
    if(slash!=std::string::npos)joined=base.substr(0,slash+1);
    joined+=d;
  }
  if(joined.size()>=2048)return false;
  std::vector<std::string> segments;
  size_t i=0;
  while(i<joined.size()){
    size_t start=i;
    while(i<joined.size()&&joined[i]!='/')i++;
    std::string part=joined.substr(start,i-start);
    if(i<joined.size())i++;
    if(part.empty()||part==".")continue;
    if(part==".."){if(segments.empty())return false;segments.pop_back();continue;}
    if(segments.size()>=256)return false;
    segments.push_back(part);
  }
  out.clear();
  for(size_t k=0;k<segments.size();k++){if(k)out+='/';out+=segments[k];}
  return !out.empty();
}

void target_reset(reader_navigation_target *t){
  std::memset(t,0,sizeof(*t));
  t->row=t->part=t->node=t->cfi_node=t->cfi_offset=NONE;
}
void target_release(reader_navigation_target *t){
  std::free(t->part_path);std::free(t->part_id);std::free(t->fragment);std::free(t->cfi);std::free(t->candidates);
  target_reset(t);
}
/* Holds a target under construction; an exception frees it, so a failed call leaves nothing. */
struct target_holder {
  reader_navigation_target t;
  bool keep=false;
  target_holder(){target_reset(&t);}
  ~target_holder(){if(!keep)target_release(&t);}
};

void parse_resolve_options(const reader_navigation_resolve_options *o,canceller &c,uint64_t &explicit_part){
  explicit_part=NONE;
  if(!o)return;
  if(o->struct_size!=sizeof(*o))reject(READER_NAVIGATION_ARGUMENT,"options.struct_size differs from sizeof(reader_navigation_resolve_options)");
  c.control=o->control;explicit_part=o->explicit_part;
}
/* The live book must be the snapshot's book: same number of parts and the same ids and
   paths in order, or no verdict is given. */
void verify_book(const reader_navigation &n,const std::vector<unit> &units,uint64_t row){
  if(units.size()!=n.part_count||book_identity(units)!=n.identity)
    reject(READER_NAVIGATION_MISMATCH,"The live book is not the book this snapshot was taken from");
  const row_data &r=n.rows[(size_t)row];
  if(r.part!=NONE){
    const unit &u=units[(size_t)r.part];
    if(r.part_path!=(u.path?u.path:"")||r.part_id!=(u.id?u.id:""))reject(READER_NAVIGATION_MISMATCH,"The row's part identity differs from the live book");
  }
}
void fill_part(reader_navigation_target &t,uint64_t part,const unit &u,bool path){
  t.part=part;
  if(path)t.part_path=dup(u.path?u.path:"");
  t.part_id=dup(u.id?u.id:"");
}
/* Returns true with `part` chosen, or false after AMBIGUOUS candidates were put in `h`. */
bool choose_part(const reader_navigation &n,uint64_t row,const std::vector<unit> &units,uint64_t explicit_part,
                 target_holder &h,uint64_t &part){
  const row_data &r=n.rows[(size_t)row];
  if(r.target_class==READER_NAVIGATION_TARGET_EXTERNAL)
    reject(READER_NAVIGATION_NEEDS_HOST,"External target: the host decides, nothing is fetched or opened");
  if(r.target_class==READER_NAVIGATION_TARGET_NONE)reject(READER_NAVIGATION_UNRESOLVED,"The row has no target");
  if(explicit_part!=NONE&&explicit_part>=units.size())reject(READER_NAVIGATION_RANGE,"explicit_part is outside the book");
  if(r.part!=NONE){
    if(explicit_part!=NONE&&explicit_part!=r.part)
      reject(READER_NAVIGATION_MISMATCH,"explicit_part differs from the part the SDK resolved");
    part=r.part;return true;
  }
  std::string path;
  if(!normalize(r.base,r.href,path))reject(READER_NAVIGATION_RANGE,"The target leaves the book container or is malformed");
  std::vector<uint64_t> found;
  for(size_t i=0;i<units.size();i++)if(units[i].path&&path==units[i].path)found.push_back(i);
  if(found.empty())reject(READER_NAVIGATION_UNRESOLVED,"No part has the target path");
  if(explicit_part!=NONE){
    for(uint64_t f:found)if(f==explicit_part){part=f;return true;}
    reject(READER_NAVIGATION_MISMATCH,"explicit_part does not have the target's path");
  }
  if(found.size()>=2){
    h.t.candidates=(uint64_t *)std::malloc(found.size()*sizeof(uint64_t));
    if(!h.t.candidates)throw std::bad_alloc();
    std::memcpy(h.t.candidates,found.data(),found.size()*sizeof(uint64_t));
    h.t.candidate_count=found.size();
    return false;
  }
  reject(READER_NAVIGATION_UNRESOLVED,"The SDK left this target unresolved; no part is guessed");
}
void set_fragment(target_holder &h,const std::string &href,std::string &uri){
  size_t hash=href.find('#');
  uri.clear();
  if(hash==std::string::npos||hash+1>=href.size())return;
  std::string fragment=href.substr(hash+1);
  h.t.fragment=dup(fragment);
  uri="#"+fragment;
}
void need_row(const reader_navigation &n,uint64_t row){
  if(row>=n.rows.size())reject(READER_NAVIGATION_RANGE,"Row index is outside the snapshot");
}
struct document_free_deleter{void operator()(exr_document *d)const{exr_document_free(d);}};
typedef std::unique_ptr<exr_document,document_free_deleter> document_ptr;
std::vector<unit> publication_units(exr_publication *p){
  size_t count=0;const exr_part *parts=exr_publication_parts(p,&count);
  std::vector<unit> units;units.reserve(count);
  for(size_t i=0;i<count;i++)units.push_back({parts[i].path,parts[i].id});
  return units;
}

/* --- pages ----------------------------------------------------------------------------- */
void free_rows(reader_navigation_row *rows,size_t count){
  for(size_t i=0;i<count;i++){
    std::free(rows[i].label);std::free(rows[i].href);std::free(rows[i].base);std::free(rows[i].role);
    std::free(rows[i].part_path);std::free(rows[i].part_id);
  }
  std::free(rows);
}
struct page_builder {
  reader_navigation_row *rows=nullptr;size_t count=0;
  ~page_builder(){free_rows(rows,count);}
};
void fill_page(const reader_navigation &n,const std::vector<uint64_t> *sequence,uint64_t first,size_t max_rows,
               reader_navigation_page *page){
  uint64_t total=sequence?sequence->size():n.rows.size();
  if(max_rows<1||max_rows>READER_NAVIGATION_PAGE_MAX)reject(READER_NAVIGATION_ARGUMENT,"max_rows must be 1..100");
  if(first>total)reject(READER_NAVIGATION_RANGE,"first is beyond the end of the sequence");
  size_t take=(size_t)(total-first<max_rows?total-first:max_rows);
  page_builder b;
  if(take){
    b.rows=(reader_navigation_row *)std::calloc(take,sizeof(reader_navigation_row));
    if(!b.rows)throw std::bad_alloc();
    b.count=take;
  }
  for(size_t i=0;i<take;i++){
    uint64_t index=sequence?(*sequence)[(size_t)first+i]:first+i;
    const row_data &r=n.rows[(size_t)index];
    reader_navigation_row &o=b.rows[i];
    o.index=index;o.parent=r.parent;o.part=r.part;o.depth=r.depth;o.child_count=r.child_count;o.target_class=r.target_class;
    o.label=dup(r.label);o.href=dup(r.href);o.base=dup(r.base);o.role=dup(r.role);
    o.part_path=dup(r.part_path);o.part_id=dup(r.part_id);
  }
  page->rows=b.rows;page->count=take;page->total=total;
  page->next=first+take<total?first+take:NONE;
  b.rows=nullptr;b.count=0;
}
}

/* --- public API ------------------------------------------------------------------------ */
extern "C" {
reader_navigation_status reader_navigation_open_publication(exr_publication *publication,
  const reader_navigation_options *options,reader_navigation **out,reader_navigation_error *error){
  if(out)*out=nullptr;
  return call(error,[&]()->soft{
    if(!publication||!out)reject(READER_NAVIGATION_ARGUMENT,"Missing publication or output");
    canceller c;limits l=make_limits(options,c);
    c.poll();
    const exr_navigation *entries=nullptr;size_t count=0;exr_error se;std::memset(&se,0,sizeof(se));
    exr_status status=exr_publication_navigation(publication,&entries,&count,&se);
    std::vector<unit> units=publication_units(publication);
    std::unique_ptr<reader_navigation> n;
    authored_snapshot(READER_NAVIGATION_FROM_PUBLICATION,status,entries,count,se,units,l,c,n);
    *out=n.release();
    return soft{};
  });
}
reader_navigation_status reader_navigation_open_document(const exr_document *document,
  const reader_navigation_options *options,reader_navigation **out,reader_navigation_error *error){
  if(out)*out=nullptr;
  return call(error,[&]()->soft{
    if(!document||!out)reject(READER_NAVIGATION_ARGUMENT,"Missing document or output");
    canceller c;limits l=make_limits(options,c);
    c.poll();
    exr_navigation *entries=nullptr;size_t count=0;exr_error se;std::memset(&se,0,sizeof(se));
    exr_status status=exr_document_navigation(document,&entries,&count,&se);
    /* The SDK allocation is released on every path, including exceptions below. */
    struct owned{exr_navigation *e;size_t n;~owned(){if(e)exr_navigation_free(e,n);}} keep{entries,count};
    size_t chapters=0;const exr_chapter *list=exr_document_chapters(document,&chapters);
    std::vector<unit> units;units.reserve(chapters);
    for(size_t i=0;i<chapters;i++)units.push_back({list[i].path,list[i].id});
    std::unique_ptr<reader_navigation> n;
    authored_snapshot(READER_NAVIGATION_FROM_DOCUMENT,status,entries,count,se,units,l,c,n);
    *out=n.release();
    return soft{};
  });
}
reader_navigation_status reader_navigation_open_pages(exr_fixed_document *document,
  const reader_navigation_options *options,reader_navigation **out,reader_navigation_error *error){
  if(out)*out=nullptr;
  return call(error,[&]()->soft{
    if(!document||!out)reject(READER_NAVIGATION_ARGUMENT,"Missing fixed document or output");
    canceller c;limits l=make_limits(options,c);
    c.poll();
    size_t count=0;const exr_fixed_page *pages=exr_fixed_pages(document,&count);
    if(count>l.nodes)reject(READER_NAVIGATION_LIMIT,"The book has more pages than the checked row limit");
    if(count&&!pages)reject(READER_NAVIGATION_SDK,"The SDK reported pages without a page directory");
    std::unique_ptr<reader_navigation> n(new reader_navigation);
    n->kind=READER_NAVIGATION_PAGES;n->source=READER_NAVIGATION_FROM_FIXED;n->part_count=count;
    std::vector<unit> units;units.reserve(count);
    for(size_t i=0;i<count;i++)units.push_back({nullptr,pages[i].id});
    n->identity=book_identity(units);
    n->rows.reserve(count);
    for(size_t i=0;i<count;i++){
      if(!(i&255))c.poll();
      row_data r;
      const char *label=pages[i].label&&*pages[i].label?pages[i].label:pages[i].id;
      add_text(*n,l,r.label,label);add_text(*n,l,r.role,"page");add_text(*n,l,r.part_id,pages[i].id);
      r.part=i;r.target_class=READER_NAVIGATION_TARGET_PAGE;
      if(n->depth_levels<1)n->depth_levels=1;
      n->rows.push_back(std::move(r));
    }
    finish_tree(*n);
    *out=n.release();
    return soft{};
  });
}
reader_navigation_status reader_navigation_info_get(reader_navigation *navigation,reader_navigation_info *info,
  reader_navigation_error *error){
  return call(error,[&]()->soft{
    if(!navigation||!info)reject(READER_NAVIGATION_ARGUMENT,"Missing snapshot or output");
    busy_guard g(*navigation);
    std::memset(info,0,sizeof(*info));
    info->kind=navigation->kind;info->source=navigation->source;
    info->author_outline=navigation->kind==READER_NAVIGATION_AUTHORED&&!navigation->rows.empty()?1u:0u;
    info->node_count=navigation->rows.size();
    info->root_count=navigation->kids.empty()?0:navigation->kids.back().size();
    info->depth_levels=navigation->depth_levels;info->text_bytes=navigation->text_bytes;
    info->part_count=navigation->part_count;
    return soft{};
  });
}
reader_navigation_status reader_navigation_close(reader_navigation **navigation,reader_navigation_error *error){
  return call(error,[&]()->soft{
    if(!navigation)reject(READER_NAVIGATION_ARGUMENT,"Missing snapshot pointer");
    if(!*navigation)return soft{};
    if((*navigation)->busy)reject(READER_NAVIGATION_BUSY,"Cannot close a snapshot from inside its own call");
    delete *navigation;*navigation=nullptr;
    return soft{};
  });
}
reader_navigation_status reader_navigation_rows(reader_navigation *navigation,uint64_t first,size_t max_rows,
  reader_navigation_page *page,reader_navigation_error *error){
  if(page){std::memset(page,0,sizeof(*page));page->next=NONE;}
  return call(error,[&]()->soft{
    if(!navigation||!page)reject(READER_NAVIGATION_ARGUMENT,"Missing snapshot or page output");
    busy_guard g(*navigation);
    fill_page(*navigation,nullptr,first,max_rows,page);
    return soft{};
  });
}
reader_navigation_status reader_navigation_children(reader_navigation *navigation,uint64_t parent,uint64_t first,
  size_t max_rows,reader_navigation_page *page,reader_navigation_error *error){
  if(page){std::memset(page,0,sizeof(*page));page->next=NONE;}
  return call(error,[&]()->soft{
    if(!navigation||!page)reject(READER_NAVIGATION_ARGUMENT,"Missing snapshot or page output");
    busy_guard g(*navigation);
    if(parent!=NONE&&parent>=navigation->rows.size())reject(READER_NAVIGATION_RANGE,"Parent row is outside the snapshot");
    const std::vector<uint64_t> &sequence=navigation->kids[parent==NONE?navigation->rows.size():(size_t)parent];
    fill_page(*navigation,&sequence,first,max_rows,page);
    return soft{};
  });
}
void reader_navigation_page_free(reader_navigation_page *page){
  if(!page)return;
  free_rows(page->rows,page->count);
  std::memset(page,0,sizeof(*page));page->next=NONE;
}

reader_navigation_status reader_navigation_resolve_publication(reader_navigation *navigation,uint64_t row,
  exr_publication *publication,const reader_navigation_resolve_options *options,
  reader_navigation_target *target,reader_navigation_error *error){
  if(target)target_reset(target);
  return call(error,[&]()->soft{
    if(!navigation||!publication||!target)reject(READER_NAVIGATION_ARGUMENT,"Missing snapshot, publication or target output");
    busy_guard g(*navigation);
    if(navigation->source!=READER_NAVIGATION_FROM_PUBLICATION||navigation->kind!=READER_NAVIGATION_AUTHORED)
      reject(READER_NAVIGATION_ARGUMENT,"The snapshot was not opened from a publication");
    need_row(*navigation,row);
    canceller c;uint64_t explicit_part;parse_resolve_options(options,c,explicit_part);
    std::vector<unit> units=publication_units(publication);
    verify_book(*navigation,units,row);
    c.poll();
    target_holder h;h.t.kind=READER_NAVIGATION_RESULT_SPINE;h.t.row=row;
    uint64_t part=NONE;
    if(!choose_part(*navigation,row,units,explicit_part,h,part)){
      h.keep=true;*target=h.t;
      return soft{READER_NAVIGATION_AMBIGUOUS,"Several parts share the target path; the host must choose one (see candidates)"};
    }
    std::string uri;set_fragment(h,navigation->rows[(size_t)row].href,uri);
    fill_part(h.t,part,units[(size_t)part],true);
    exr_document *loaded=nullptr;exr_error se;std::memset(&se,0,sizeof(se));
    exr_status status=exr_publication_load(publication,(size_t)part,&loaded,&se);
    document_ptr doc(loaded);
    if(status!=EXR_OK)sdk_fail(status,"The SDK could not load the target part",se,false);
    c.poll();
    soft result;
    if(!uri.empty()){
      size_t resource=SIZE_MAX,node=SIZE_MAX;
      status=exr_document_resolve(doc.get(),0,uri.c_str(),&resource,&node,&se);
      if(status!=EXR_OK)sdk_fail(status,"The SDK could not resolve the fragment",se,true);
      c.poll();
      if(node==SIZE_MAX)result=soft{READER_NAVIGATION_PART_ONLY,"The part exists but has no element with the fragment id"};
      else h.t.node=node;
    }
    h.keep=true;*target=h.t;
    return result;
  });
}
reader_navigation_status reader_navigation_resolve_document(reader_navigation *navigation,uint64_t row,
  const exr_document *document,const reader_navigation_resolve_options *options,
  reader_navigation_target *target,reader_navigation_error *error){
  if(target)target_reset(target);
  return call(error,[&]()->soft{
    if(!navigation||!document||!target)reject(READER_NAVIGATION_ARGUMENT,"Missing snapshot, document or target output");
    busy_guard g(*navigation);
    if(navigation->source!=READER_NAVIGATION_FROM_DOCUMENT||navigation->kind!=READER_NAVIGATION_AUTHORED)
      reject(READER_NAVIGATION_ARGUMENT,"The snapshot was not opened from a document");
    need_row(*navigation,row);
    canceller c;uint64_t explicit_part;parse_resolve_options(options,c,explicit_part);
    size_t chapters=0;const exr_chapter *list=exr_document_chapters(document,&chapters);
    std::vector<unit> units;units.reserve(chapters);
    for(size_t i=0;i<chapters;i++)units.push_back({list[i].path,list[i].id});
    verify_book(*navigation,units,row);
    c.poll();
    target_holder h;h.t.kind=READER_NAVIGATION_RESULT_CHAPTER;h.t.row=row;
    uint64_t part=NONE;
    if(!choose_part(*navigation,row,units,explicit_part,h,part)){
      h.keep=true;*target=h.t;
      return soft{READER_NAVIGATION_AMBIGUOUS,"Several chapters share the target path; the host must choose one (see candidates)"};
    }
    std::string uri;set_fragment(h,navigation->rows[(size_t)row].href,uri);
    fill_part(h.t,part,units[(size_t)part],true);
    soft result;
    if(!uri.empty()){
      size_t resource=SIZE_MAX,node=SIZE_MAX;exr_error se;std::memset(&se,0,sizeof(se));
      exr_status status=exr_document_resolve(document,(size_t)part,uri.c_str(),&resource,&node,&se);
      if(status!=EXR_OK)sdk_fail(status,"The SDK could not resolve the fragment",se,true);
      c.poll();
      if(node==SIZE_MAX)result=soft{READER_NAVIGATION_PART_ONLY,"The chapter exists but has no element with the fragment id"};
      else h.t.node=node;
    }
    h.keep=true;*target=h.t;
    return result;
  });
}
reader_navigation_status reader_navigation_resolve_page(reader_navigation *navigation,uint64_t row,
  exr_fixed_document *document,const reader_navigation_resolve_options *options,
  reader_navigation_target *target,reader_navigation_error *error){
  if(target)target_reset(target);
  return call(error,[&]()->soft{
    if(!navigation||!document||!target)reject(READER_NAVIGATION_ARGUMENT,"Missing snapshot, fixed document or target output");
    busy_guard g(*navigation);
    if(navigation->source!=READER_NAVIGATION_FROM_FIXED||navigation->kind!=READER_NAVIGATION_PAGES)
      reject(READER_NAVIGATION_ARGUMENT,"The snapshot was not opened from a fixed document's pages");
    need_row(*navigation,row);
    canceller c;uint64_t explicit_part;parse_resolve_options(options,c,explicit_part);
    size_t count=0;const exr_fixed_page *pages=exr_fixed_pages(document,&count);
    std::vector<unit> units;units.reserve(count);
    for(size_t i=0;i<count;i++)units.push_back({nullptr,pages[i].id});
    verify_book(*navigation,units,row);
    c.poll();
    const row_data &r=navigation->rows[(size_t)row];
    if(explicit_part!=NONE&&explicit_part!=r.part)reject(READER_NAVIGATION_MISMATCH,"explicit_part differs from the page of the row");
    if(r.part>=count||r.part_id!=pages[(size_t)r.part].id)reject(READER_NAVIGATION_MISMATCH,"The page id differs from the live document");
    target_holder h;h.t.kind=READER_NAVIGATION_RESULT_PAGE;h.t.row=row;
    fill_part(h.t,r.part,units[(size_t)r.part],false);
    h.keep=true;*target=h.t;
    return soft{};
  });
}
reader_navigation_status reader_navigation_resolve_cfi(reader_navigation *navigation,exr_publication *publication,
  const char *cfi,const reader_navigation_resolve_options *options,reader_navigation_target *target,
  reader_navigation_error *error){
  if(target)target_reset(target);
  return call(error,[&]()->soft{
    if(!navigation||!publication||!cfi||!target)reject(READER_NAVIGATION_ARGUMENT,"Missing snapshot, publication, CFI or target output");
    busy_guard g(*navigation);
    if(navigation->source!=READER_NAVIGATION_FROM_PUBLICATION||navigation->kind!=READER_NAVIGATION_AUTHORED)
      reject(READER_NAVIGATION_ARGUMENT,"The snapshot was not opened from a publication");
    size_t size=std::strlen(cfi);
    if(!size||size>READER_NAVIGATION_CFI_MAX)reject(READER_NAVIGATION_ARGUMENT,"A CFI is 1..4096 bytes");
    canceller c;uint64_t explicit_part;parse_resolve_options(options,c,explicit_part);
    std::vector<unit> units=publication_units(publication);
    if(units.size()!=navigation->part_count||book_identity(units)!=navigation->identity)
      reject(READER_NAVIGATION_MISMATCH,"The live book is not the book this snapshot was taken from");
    c.poll();
    size_t part=SIZE_MAX;exr_document *loaded=nullptr;exr_cfi_point point={SIZE_MAX,SIZE_MAX,0};
    exr_error se;std::memset(&se,0,sizeof(se));
    exr_status status=exr_publication_cfi_resolve(publication,cfi,c.ptr(),&part,&loaded,&point,&se);
    document_ptr doc(loaded);
    if(status!=EXR_OK)sdk_fail(status,"The SDK could not resolve the CFI",se,true);
    c.poll();
    if(part>=units.size())reject(READER_NAVIGATION_CORRUPT,"The SDK returned a part outside the publication");
    target_holder h;h.t.kind=READER_NAVIGATION_RESULT_CFI;
    fill_part(h.t,part,units[part],true);
    h.t.cfi=dup(std::string(cfi,size));
    h.t.cfi_node=point.node==SIZE_MAX?NONE:(uint64_t)point.node;
    h.t.cfi_offset=point.offset==SIZE_MAX?NONE:(uint64_t)point.offset;
    h.t.cfi_side=point.side;
    h.keep=true;*target=h.t;
    return soft{};
  });
}
void reader_navigation_target_free(reader_navigation_target *target){
  if(target)target_release(target);
}
}
