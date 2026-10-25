/* SPDX-License-Identifier: MIT */
#include "reader_reading_commands.h"
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <set>
#include <string>
#include <vector>

#ifdef EXR_READER_SELECTOR_BYTES_CANDIDATE
reader_rs_status reader_rs_encode_retained_raw_v3(reader_revisions *,const reader_rs_envelope *,const reader_rs_capture *,unsigned,size_t,char **,size_t *,reader_rs_error *);
#endif

static reader_revision_status reader_candidate_reader_revision_get(bool raw,reader_revisions *s,const char *id,char **w,size_t *n,reader_revision_info *i,reader_revision_error *e){
#ifdef EXR_READER_SELECTOR_BYTES_CANDIDATE
if(raw)return reader_revision_get_raw_v3(s,id,w,n,i,e);
#else
(void)raw;
#endif
return reader_revision_get(s,id,w,n,i,e);}
static reader_revision_status reader_candidate_reader_revision_selected(bool raw,reader_revisions *s,const char *k,const char *id,char **w,size_t *n,reader_revision_info *i,reader_revision_selection *g,reader_revision_error *e){
#ifdef EXR_READER_SELECTOR_BYTES_CANDIDATE
if(raw)return reader_revision_selected_raw_v3(s,k,id,w,n,i,g,e);
#else
(void)raw;
#endif
return reader_revision_selected(s,k,id,w,n,i,g,e);}
static reader_rs_status reader_candidate_reader_rs_decode(bool raw,reader_revisions *s,const void *w,size_t n,reader_rs_record *r,reader_rs_error *e){
#ifdef EXR_READER_SELECTOR_BYTES_CANDIDATE
if(raw)return reader_rs_decode_raw_v3(s,w,n,r,e);
#else
(void)raw;
#endif
return reader_rs_decode(s,w,n,r,e);}
static reader_revision_status reader_candidate_reader_revision_local_reading(bool raw,reader_revisions *s,const void *w,size_t n,const char *const *p,size_t c,reader_revision_info *i,int *created,reader_revision_error *e){
#ifdef EXR_READER_SELECTOR_BYTES_CANDIDATE
if(raw)return reader_revision_local_reading_raw_v3(s,w,n,p,c,i,created,e);
#else
(void)raw;
#endif
return reader_revision_local_reading(s,w,n,p,c,i,created,e);}
namespace {
struct failure {reader_rc_status code;const char *message;reader_rs_error encode;reader_revision_error revision;};
[[noreturn]] void reject(const char *message){throw failure{READER_RC_ARGUMENT,message,{},{}};}
[[noreturn]] void refuse(reader_rc_status code,const char *message){throw failure{code,message,{},{}};}
bool hex32(const std::string &value){return value.size()==32&&value.find_first_not_of("0123456789abcdef")==std::string::npos;}
std::string bounded(const char *value,size_t maximum,const char *message){
  if(!value)reject(message);
  size_t size=0;while(size<=maximum&&value[size])++size;
  if(size>maximum)reject(message);
  return std::string(value,size);
}
/* Strict UTF-8: no NUL, overlong, surrogate or scalar above U+10FFFF. */
bool utf8(const std::string &s){
  size_t i=0,n=s.size();
  while(i<n){
    unsigned char c=(unsigned char)s[i];
    if(!c)return false;
    if(c<0x80){++i;continue;}
    size_t extra=c>=0xc2&&c<=0xdf?1:(c>=0xe0&&c<=0xef)?2:(c>=0xf0&&c<=0xf4)?3:0;
    if(!extra||i+extra>=n)return false;
    unsigned scalar=extra==1?(c&0x1fu):extra==2?(c&0x0fu):(c&0x07u);
    for(size_t k=1;k<=extra;++k){
      unsigned char d=(unsigned char)s[i+k];
      if((d&0xc0)!=0x80)return false;
      scalar=(scalar<<6)|(d&0x3fu);
    }
    if((extra==2&&scalar<0x800)||(extra==3&&(scalar<0x10000||scalar>0x10ffff))||(scalar>=0xd800&&scalar<=0xdfff))return false;
    i+=extra+1;
  }
  return true;
}
std::string book(const char *value){
  std::string key=bounded(value,72,"Missing or oversized original book key");
  size_t colon=key.find(':');
  if(colon==std::string::npos||colon==0||key.size()-colon-1!=64||key.find_first_not_of("0123456789abcdef",colon+1)!=std::string::npos)
    reject("Invalid original book key");
  return key;
}
void assigned(char *target,size_t capacity,const std::string &value){
  if(value.size()>=capacity)reject("Assigned identity exceeds its bound");
  std::memcpy(target,value.c_str(),value.size()+1);
}
bool point(const reader_rs_capture *c){
  if(c->mode==READER_RS_FIXED_PAGE)return c->fixed&&c->fixed->exact_size==0;
  return c->anchor&&c->anchor->exact&&!c->anchor->exact[0];
}
const char *operation_name(reader_rc_operation op){
  switch(op){case READER_RC_PUT:return "put";case READER_RC_DELETE:return "delete";case READER_RC_RESTORE:return "restore";}
  reject("Unknown reading command operation");
}
struct owned {char *wire=nullptr;~owned(){reader_revision_bytes_free(wire);}};
struct produced {char *wire=nullptr;~produced(){reader_rs_free(wire);}};
struct decoded {reader_rs_record r{};~decoded(){reader_rs_record_free(&r);}};
const char *z(const char *s){return s?s:"";}
bool same(const char *a,size_t an,const char *b,size_t bn){return an==bn&&(!an||!std::memcmp(a,b,an));}
/* Everything but id, parents and note text must match the source decode. */
bool same_location(const reader_rs_record &a,const reader_rs_record &b){
  return (!a.exact)==(!b.exact)&&(!a.prefix)==(!b.prefix)&&(!a.suffix)==(!b.suffix)&&a.has_location&&b.has_location&&a.mode==b.mode&&a.anchor_version==b.anchor_version&&a.page==b.page&&a.part==b.part&&
    a.start==b.start&&a.end==b.end&&!std::strcmp(z(a.part_path),z(b.part_path))&&!std::strcmp(z(a.page_id),z(b.page_id))&&
    !std::strcmp(a.parser_version,b.parser_version)&&!std::strcmp(z(a.chapter),z(b.chapter))&&(!a.chapter)==(!b.chapter)&&
    same(z(a.exact),a.exact_size,z(b.exact),b.exact_size)&&same(z(a.prefix),a.prefix_size,z(b.prefix),b.prefix_size)&&
    same(z(a.suffix),a.suffix_size,z(b.suffix),b.suffix_size);
}
struct request {
  const reader_rc_context &context;const reader_rc_command &command;reader_rc_result &result;
  std::string revision_id,book_key,annotation_id,key,text;std::vector<std::string> parents;std::vector<const char *> pointers;
  bool annotation=false;bool raw_api=false;
  request(const reader_rc_context *c,const reader_rc_command *m,reader_rc_result *r,bool raw=false):context(*c),command(*m),result(*r),raw_api(raw){
    if(!context.store||(context.expected_count&&!context.expected_heads)||context.expected_count>READER_REVISION_MAX_PARENTS)reject("Invalid observed head set");
    revision_id=bounded(context.revision_id,32,"A stable revision ID is required");
    if(!hex32(revision_id))reject("Invalid stable revision ID");
    std::set<std::string> unique;
    for(size_t n=0;n<context.expected_count;++n){
      std::string head=bounded(context.expected_heads[n],32,"Missing observed head ID");
      if(!hex32(head))reject("Invalid observed head ID");
      if(!unique.insert(head).second)reject("Duplicate observed head");
    }
    parents.assign(unique.begin(),unique.end());
    for(const auto &p:parents)pointers.push_back(p.c_str());
    book_key=book(command.book_key);
    if(command.kind<READER_RC_PROGRESS||command.kind>READER_RC_NOTE_TEXT)reject("Unknown reading command kind");
    operation_name(command.operation);
    annotation=command.kind!=READER_RC_PROGRESS;
    std::string given=command.annotation_id?bounded(command.annotation_id,32,"Oversized annotation ID"):std::string();
    if(!annotation){
      if(!given.empty()||command.text)reject("Progress carries neither an annotation ID nor text");
      key=book_key;
    }else{
      if(given.empty()){
        if(command.operation!=READER_RC_PUT||command.kind==READER_RC_NOTE_TEXT||!parents.empty())reject("Only a new bookmark or highlight can allocate its annotation ID");
        given=retained_annotation();
        if(given.empty()){
          char generated[33];reader_revision_error e{};
          if(reader_revision_new_id(generated,&e)!=READER_REV_OK)throw failure{READER_RC_REVISION,"Cannot allocate an annotation ID",{},e};
          given=generated;
        }
      }else if(!hex32(given))reject("Invalid annotation ID");
      annotation_id=given;key=book_key+":"+annotation_id;assigned(result.annotation_id,sizeof(result.annotation_id),annotation_id);
    }
    assigned(result.entity_key,sizeof(result.entity_key),key);assigned(result.revision_id,sizeof(result.revision_id),revision_id);
    if(command.operation!=READER_RC_PUT&&parents.empty())reject("Delete or restore requires observed history");
    if(command.kind==READER_RC_NOTE_TEXT&&(command.operation!=READER_RC_PUT||parents.size()!=1))reject("A note edit is a put over exactly one observed head");
    if(command.operation==READER_RC_DELETE){if(command.text)reject("Delete carries no text");}
    else if(annotation){text=bounded(command.text,65536,"Annotation text is missing or exceeds its bound");if(!utf8(text))reject("Annotation text is not strict UTF-8");}
  }
  reader_rs_envelope envelope(const char *parser)const{
    reader_rs_envelope env{};env.revision_id=revision_id.c_str();env.operation=operation_name(command.operation);
    env.entity_kind=annotation?"annotation":"progress";env.book_key=book_key.c_str();env.annotation_id=annotation?annotation_id.c_str():nullptr;
    env.parents=pointers.empty()?nullptr:pointers.data();env.parent_count=pointers.size();env.note_text=annotation?text.c_str():nullptr;env.parser_version=parser;
    return env;
  }
  /* A caller that lost the first response keeps only the stable revision ID, so an
     empty annotation ID must not mean "allocate another identity": if a revision is
     already retained under that ID, its annotation is re-derived from the retained
     entity key. The rebuilt wire is then byte-identical, which the module answers
     with created == 0 (COLLISION only if the payload really differs). */
  std::string retained_annotation()const{
    owned held;size_t bytes=0;reader_revision_info info{};reader_revision_error e{};
    reader_revision_status st=reader_candidate_reader_revision_get(raw_api,context.store,revision_id.c_str(),&held.wire,&bytes,&info,&e);
    if(st==READER_REV_NOT_FOUND)return std::string();
    if(st!=READER_REV_OK)throw failure{READER_RC_REVISION,"Cannot read the retained revision",{},e};
    if(std::strcmp(info.entity_kind,"annotation"))refuse(READER_RC_SOURCE,"The retained revision ID belongs to another entity");
    std::string retained=info.entity_key;size_t colon=retained.rfind(':');
    if(colon==std::string::npos||retained.size()-colon-1!=32||retained.compare(0,colon,book_key))
      refuse(READER_RC_SOURCE,"The retained revision belongs to another annotation");
    std::string aid=retained.substr(colon+1);
    if(!hex32(aid))refuse(READER_RC_SOURCE,"The retained revision has no annotation identity");
    return aid;
  }
  std::string encode(const reader_rs_envelope &env,const reader_rs_capture &capture,size_t part,unsigned version)const{
    produced out;size_t bytes=0;reader_rs_error e{};
        reader_rs_status st;
#ifdef EXR_READER_SELECTOR_BYTES_CANDIDATE
    if(raw_api)st=reader_rs_encode_retained_raw_v3(context.store,&env,&capture,version,part,&out.wire,&bytes,&e);else
#endif
    st=version==1?reader_rs_encode(context.store,&env,&capture,&out.wire,&bytes,&e):
      reader_rs_encode_v2(context.store,&env,&capture,part,&out.wire,&bytes,&e);
    if(st!=READER_RS_OK){
      reader_rc_status code=st==READER_RS_ARGUMENT?READER_RC_ARGUMENT:st==READER_RS_MEMORY?READER_RC_MEMORY:READER_RC_ENCODE;
      throw failure{code,"The capture cannot be encoded as a lossless reading revision",e,{}};
    }
    return std::string(out.wire,bytes);
  }
  /* Selector of the head being edited: the retained revision itself on an exact
     retry, otherwise the one safe selected head that is also the observed head. */
  std::string source()const{
    owned held;size_t bytes=0;reader_revision_info info{};reader_revision_error e{};
    reader_revision_status st=reader_candidate_reader_revision_get(raw_api,context.store,revision_id.c_str(),&held.wire,&bytes,&info,&e);
    if(st==READER_REV_OK){
      if(key!=info.entity_key)refuse(READER_RC_SOURCE,"The retained revision ID belongs to another entity");
      return std::string(held.wire,bytes);
    }
    if(st!=READER_REV_NOT_FOUND)throw failure{READER_RC_REVISION,"Cannot read the retained revision",{},e};
    owned chosen;reader_revision_selection selection{};e={};info={};bytes=0;
    st=reader_candidate_reader_revision_selected(raw_api,context.store,"annotation",key.c_str(),&chosen.wire,&bytes,&info,&selection,&e);
    if(st==READER_REV_NOT_FOUND||st==READER_REV_UNSAFE)refuse(READER_RC_SOURCE,"The annotation has no single safe head to edit");
    if(st!=READER_REV_OK)throw failure{READER_RC_REVISION,"Cannot read the selected annotation",{},e};
    if(parents[0]!=info.revision_id)refuse(READER_RC_UNSAFE,"The observed head is not the current safe head");
    return std::string(chosen.wire,bytes);
  }
  std::string build()const{
    const char *parser=context.parser_version?context.parser_version:"";
    if(command.kind==READER_RC_NOTE_TEXT){
      std::string original=source();decoded old;reader_rs_error e{};
      reader_rs_status st=reader_candidate_reader_rs_decode(raw_api,context.store,original.data(),original.size(),&old.r,&e);
      if(st!=READER_RS_OK)throw failure{READER_RC_ENCODE,"The source revision cannot be decoded",e,{}};
      if(std::strcmp(old.r.entity_kind,"annotation")||book_key!=old.r.book_key||annotation_id!=old.r.annotation_id)
        refuse(READER_RC_SOURCE,"The source is not a revision of this annotation");
      if(!std::strcmp(old.r.operation,"delete")||!old.r.has_location)refuse(READER_RC_SOURCE,"A tombstone needs an explicit restore with a real capture");
      exr_anchor a{};exr_fixed_anchor f{};reader_rs_capture c{};c.mode=old.r.mode;
      static char empty[1]={0};
      if(old.r.mode==READER_RS_FIXED_PAGE){
        f.start=(size_t)old.r.start;f.end=(size_t)old.r.end;f.page_id=old.r.page_id;f.exact=raw_api?old.r.exact:old.r.exact?old.r.exact:empty;
        f.prefix=raw_api?old.r.prefix:old.r.prefix?old.r.prefix:empty;f.suffix=raw_api?old.r.suffix:old.r.suffix?old.r.suffix:empty;
        f.exact_size=old.r.exact_size;f.prefix_size=old.r.prefix_size;f.suffix_size=old.r.suffix_size;c.fixed=&f;c.page=(size_t)old.r.page;
      }else{
        a.start=(size_t)old.r.start;a.end=(size_t)old.r.end;a.exact=old.r.exact?old.r.exact:empty;
        a.prefix=old.r.prefix?old.r.prefix:empty;a.suffix=old.r.suffix?old.r.suffix:empty;
        a.chapter=old.r.mode==READER_RS_REFLOW_GLOBAL?old.r.chapter:nullptr;c.anchor=&a;c.part_path=old.r.part_path;
      }
      unsigned version=(unsigned)old.r.anchor_version;
      std::string wire=encode(envelope(old.r.parser_version),c,(size_t)old.r.part,version);
      decoded fresh;st=reader_candidate_reader_rs_decode(raw_api,context.store,wire.data(),wire.size(),&fresh.r,&e);
      if(st!=READER_RS_OK||!same_location(old.r,fresh.r)||std::strcmp(z(fresh.r.note_text),text.c_str()))
        refuse(READER_RC_SOURCE,"The edited revision would not preserve the original selector");
      return wire;
    }
    reader_rs_capture none{};
    if(command.operation==READER_RC_DELETE){
      if(!command.capture||command.capture->anchor||command.capture->fixed)reject("Delete names only the capture mode");
      none.mode=command.capture->mode;
      return encode(envelope(parser),none,0,raw_api?3:2);
    }
    if(!command.capture)reject("A real SDK capture is required");
    if(!parser[0])reject("A parser version is required");
    if(command.kind==READER_RC_BOOKMARK&&!point(command.capture))reject("A bookmark requires a point capture");
    if(command.kind==READER_RC_HIGHLIGHT&&(point(command.capture)||(command.capture->mode!=READER_RS_FIXED_PAGE&&command.capture->anchor&&!command.capture->anchor->exact)))
      reject("A highlight requires a nonempty range capture");
    return encode(envelope(parser),*command.capture,command.part,raw_api?3:2);
  }
};
}
static reader_rc_status apply(bool raw_api,const reader_rc_context *context,const reader_rc_command *command,reader_rc_result *result,reader_rc_error *error){
  if(error)std::memset(error,0,sizeof(*error));
  if(result)std::memset(result,0,sizeof(*result));
  auto fail=[&](const failure &f){
    if(error){error->code=f.code;error->encode=f.encode;error->revision=f.revision;std::snprintf(error->message,sizeof(error->message),"%s",f.message);}
    return f.code;
  };
  try{
    if(!context||!command||!result)reject("Missing reading command arguments");
    request r(context,command,result,raw_api);
    std::string wire=r.build();
    reader_revision_error e{};
    reader_revision_status st=reader_candidate_reader_revision_local_reading(raw_api,context->store,wire.data(),wire.size(),r.pointers.empty()?nullptr:r.pointers.data(),
      r.pointers.size(),&result->revision,&result->created,&e);
    if(st!=READER_REV_OK){
      /* Failed commits leave history and outbox untouched; created stays zero. */
      return fail(failure{st==READER_REV_UNSAFE?READER_RC_UNSAFE:READER_RC_REVISION,
        st==READER_REV_UNSAFE?"Observed heads are stale or the history is not safe":"Reading revision was refused",{},e});
    }
    assigned(result->sha256,sizeof(result->sha256),result->revision.sha256);result->bytes=wire.size();
    return READER_RC_OK;
  }catch(const failure &f){return fail(f);}
  catch(...){return fail(failure{READER_RC_MEMORY,"Cannot allocate a bounded reading command",{},{}});}
}

extern "C" reader_rc_status reader_rc_apply(const reader_rc_context *c,const reader_rc_command *m,reader_rc_result *r,reader_rc_error *e){return apply(false,c,m,r,e);}
#ifdef EXR_READER_SELECTOR_BYTES_CANDIDATE
extern "C" reader_rc_status reader_rc_apply_fixed_v3(const reader_rc_context *c,const reader_rc_command *m,reader_rc_result *r,reader_rc_error *e){
  if(m&&m->capture&&m->capture->mode!=READER_RS_FIXED_PAGE){if(r)std::memset(r,0,sizeof(*r));if(e){std::memset(e,0,sizeof(*e));e->code=READER_RC_ARGUMENT;}return READER_RC_ARGUMENT;}
  return apply(true,c,m,r,e);
}
#endif