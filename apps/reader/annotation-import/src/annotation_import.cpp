// SPDX-License-Identifier: MIT
#include "reader_annotation_import.h"
#include <algorithm>
#include <cerrno>
#include <cstdio>
#include <cstring>
#include <cstdint>
#include <limits>
#include <new>
#include <set>
#include <string>
#ifdef _WIN32
#define NOMINMAX
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <io.h>
#include <fcntl.h>
#else
#include <fcntl.h>
#include <sys/stat.h>
#include <unistd.h>
#endif
namespace {
struct failure {reader_annotation_import_status code;const char *text;int revision=0;int os=0;};
[[noreturn]] void fail(reader_annotation_import_status c,const char *s,int r=0,int o=0){throw failure{c,s,r,o};}
void need(bool b,const char *s){if(!b)fail(READER_AI_FORMAT,s);}
thread_local bool active=false;
struct active_guard {active_guard(){active=true;}~active_guard(){active=false;}};
struct file {FILE *p=nullptr;~file(){if(p)std::fclose(p);}file()=default;file(const file &)=delete;file &operator=(const file &)=delete;};
bool utf8(const std::string &s){
  for(size_t i=0;i<s.size();){unsigned char c=(unsigned char)s[i++];if(!c)return false;if(c<128)continue;
    unsigned n;uint32_t cp;
    if(c>=0xc2&&c<=0xdf){n=1;cp=c&31u;}else if(c>=0xe0&&c<=0xef){n=2;cp=c&15u;}else if(c>=0xf0&&c<=0xf4){n=3;cp=c&7u;}else return false;
    if(n>s.size()-i)return false;
    for(unsigned j=0;j<n;j++){c=(unsigned char)s[i++];if((c&0xc0)!=0x80)return false;cp=(cp<<6)|(c&63u);}
    if((n==1&&cp<128)||(n==2&&cp<2048)||(n==3&&cp<65536)||cp>0x10ffff||(cp>=0xd800&&cp<=0xdfff))return false;
  }return true;
}
bool hex(const std::string &s,size_t n){return s.size()==n&&s.find_first_not_of("0123456789abcdef")==std::string::npos;}
bool book_key(const std::string &s){size_t p=s.find(':');if(p==std::string::npos)return false;std::string f=s.substr(0,p);return (f=="txt"||f=="epub"||f=="pdf"||f=="mobi"||f=="fb2"||f=="cbz"||f=="html"||f=="rtf"||f=="docx")&&hex(s.substr(p+1),64);}
#ifdef _WIN32
std::wstring wide(const char *s){int n=MultiByteToWideChar(CP_UTF8,MB_ERR_INVALID_CHARS,s,-1,nullptr,0);if(!n)fail(READER_AI_ARGUMENT,"Invalid UTF-8 path");std::wstring w((size_t)n,L'\0');MultiByteToWideChar(CP_UTF8,MB_ERR_INVALID_CHARS,s,-1,&w[0],n);return w;}
#endif
void open_source(file &f,const char *path){
#ifdef _WIN32
  HANDLE h=CreateFileW(wide(path).c_str(),GENERIC_READ,FILE_SHARE_READ|FILE_SHARE_WRITE|FILE_SHARE_DELETE,nullptr,OPEN_EXISTING,FILE_FLAG_OPEN_REPARSE_POINT,nullptr);
  if(h==INVALID_HANDLE_VALUE)fail(READER_AI_IO,"Cannot open input",0,(int)GetLastError());
  BY_HANDLE_FILE_INFORMATION info{};
  if(!GetFileInformationByHandle(h,&info)||(info.dwFileAttributes&(FILE_ATTRIBUTE_DIRECTORY|FILE_ATTRIBUTE_REPARSE_POINT))||GetFileType(h)!=FILE_TYPE_DISK){CloseHandle(h);fail(READER_AI_IO,"Input must be a regular non-link file");}
  int fd=_open_osfhandle((intptr_t)h,_O_RDONLY|_O_BINARY);if(fd<0){CloseHandle(h);fail(READER_AI_IO,"Cannot wrap input handle",0,errno);}f.p=_fdopen(fd,"rb");if(!f.p)_close(fd);
#else
  int fd=::open(path,O_RDONLY|O_NOFOLLOW|O_NONBLOCK);if(fd<0)fail(READER_AI_IO,"Cannot open input",0,errno);
  struct stat st{};if(fstat(fd,&st)||!S_ISREG(st.st_mode)){::close(fd);fail(READER_AI_IO,"Input must be a regular non-link file");}
  f.p=fdopen(fd,"rb");if(!f.p)::close(fd);
#endif
  if(!f.p)fail(READER_AI_IO,"Cannot open input stream",0,errno);
}
void open_spool(file &f){
#ifdef _WIN32
  wchar_t temp[MAX_PATH+1];DWORD n=GetTempPathW(MAX_PATH,temp);if(!n||n>MAX_PATH)fail(READER_AI_IO,"Cannot locate private spool directory");
  // Refuse a reparse-point temp root; CREATE_NEW refuses any occupied final name.
  DWORD attr=GetFileAttributesW(temp);if(attr==INVALID_FILE_ATTRIBUTES||(attr&FILE_ATTRIBUTE_REPARSE_POINT))fail(READER_AI_IO,"Unsafe spool directory");
  char id[33];reader_revision_error e{};if(reader_revision_new_id(id,&e)!=READER_REV_OK)fail(READER_AI_IO,"Cannot generate private spool name");
  std::wstring path=temp;path+=L"exr-ai-";path+=wide(id).c_str();path+=L".tmp";
  HANDLE h=CreateFileW(path.c_str(),GENERIC_READ|GENERIC_WRITE,0,nullptr,CREATE_NEW,FILE_ATTRIBUTE_TEMPORARY|FILE_FLAG_DELETE_ON_CLOSE,nullptr);
  if(h==INVALID_HANDLE_VALUE)fail(READER_AI_IO,"Cannot create private spool",0,(int)GetLastError());
  int fd=_open_osfhandle((intptr_t)h,_O_RDWR|_O_BINARY);if(fd<0){CloseHandle(h);fail(READER_AI_IO,"Cannot wrap spool handle",0,errno);}f.p=_fdopen(fd,"w+b");if(!f.p)_close(fd);
#else
  // tmpfile atomically creates an exclusive mode0600 file and immediately unlinks
  // it. No caller-provided temporary path, shared reopen, or surviving name.
  f.p=std::tmpfile();
#endif
  if(!f.p)fail(READER_AI_IO,"Cannot create private spool",0,errno);
}
void poll(const reader_annotation_import_options &o){if(o.cancel){int stop=0;try{stop=o.cancel(o.context);}catch(...){fail(READER_AI_CALLBACK,"Cancel callback threw");}if(stop)fail(READER_AI_CANCELLED,"Import cancelled; previous commits retained");}}
/* Streaming, nonrecursive grammar for exactly the original G05 record layout.
   No whole line/object/file aggregation and no permissive generic JSON fallback. */
class parser {
 public:
  FILE *f;uint64_t line=1;explicit parser(FILE *p):f(p){}
  int peek(){int c=std::fgetc(f);if(c!=EOF)std::ungetc(c,f);else if(std::ferror(f))fail(READER_AI_IO,"Cannot read private spool",0,errno);return c;}
  int get(){int c=std::fgetc(f);if(c==EOF&&std::ferror(f))fail(READER_AI_IO,"Cannot read private spool",0,errno);return c;}
  void space(){while(peek()==' '||peek()=='\t')get();}
  void ch(int c){space();need(get()==c,"Unexpected JSON token, duplicate/unknown key or truncated input");}
  void literal(const char *s){space();while(*s)need(get()==*s++,"Invalid JSON literal");}
  void endline(){space();need(get()=='\n',"Every complete record must end in LF");++line;}
  unsigned u4(){unsigned value=0;for(int i=0;i<4;i++){int c=get();need((c>='0'&&c<='9')||(c>='a'&&c<='f')||(c>='A'&&c<='F'),"Bad Unicode escape");value=value*16u+(unsigned)(c<='9'?c-'0':c<='F'?c-'A'+10:c-'a'+10);}return value;}
  std::string str(size_t limit){
    ch('"');std::string s;
    for(;;){int c=get();need(c!=EOF&&c>=0x20,"Truncated string or unescaped control");if(c=='"')break;
      if(c=='\\'){c=get();switch(c){case '"':case '\\':case '/':s.push_back((char)c);break;
        case 'b':s.push_back('\b');break;case 'f':s.push_back('\f');break;case 'n':s.push_back('\n');break;case 'r':s.push_back('\r');break;case 't':s.push_back('\t');break;
        case 'u':{uint32_t cp=u4();if(cp>=0xd800&&cp<=0xdbff){need(get()=='\\'&&get()=='u',"Unpaired high surrogate");uint32_t low=u4();need(low>=0xdc00&&low<=0xdfff,"Invalid low surrogate");cp=0x10000+((cp-0xd800)<<10)+(low-0xdc00);}else need(cp<0xdc00||cp>0xdfff,"Unpaired low surrogate");
          if(cp<128)s.push_back((char)cp);else if(cp<2048){s.push_back((char)(0xc0|(cp>>6)));s.push_back((char)(0x80|(cp&63)));}else if(cp<65536){s.push_back((char)(0xe0|(cp>>12)));s.push_back((char)(0x80|((cp>>6)&63)));s.push_back((char)(0x80|(cp&63)));}else{s.push_back((char)(0xf0|(cp>>18)));s.push_back((char)(0x80|((cp>>12)&63)));s.push_back((char)(0x80|((cp>>6)&63)));s.push_back((char)(0x80|(cp&63)));}break;}
        default:fail(READER_AI_FORMAT,"Unknown JSON escape");}
      }else s.push_back((char)c);
      if(s.size()>limit)fail(READER_AI_LIMIT,"JSON string exceeds its field limit");
    }need(utf8(s),"String is not non-NUL scalar UTF-8");return s;
  }
  uint64_t number(){space();int c=get();need(c>='0'&&c<='9',"Expected unsigned integer");uint64_t n=(unsigned)(c-'0');if(c=='0')need(peek()<'0'||peek()>'9',"Leading zero in number");
    while(peek()>='0'&&peek()<='9'){unsigned d=(unsigned)(get()-'0');need(n<=(std::numeric_limits<uint64_t>::max()-d)/10,"Integer overflow");n=n*10+d;}return n;}
  bool boolean(){space();if(peek()=='t'){literal("true");return true;}literal("false");return false;}
  void key(const char *name,bool first=false){if(!first)ch(',');need(str(64)==name,"Unknown, duplicate, missing or reordered G05 field");ch(':');}
};
struct counts {uint64_t annotations=0,current=0,tombstones=0,pending=0,concurrent=0,blocked=0,heads=0,omitted=0;};
size_t bounded_count(parser &p,uint64_t max){uint64_t n=p.number();need(n<=max,"Graph count exceeds public limit");return (size_t)n;}
reader_revision_state graph(parser &p){reader_revision_state g{};p.ch('{');p.key("revisions",true);g.revisions=bounded_count(p,READER_REVISION_MAX_ENTITY_HISTORY);p.key("heads");g.heads=bounded_count(p,READER_REVISION_MAX_ENTITY_HISTORY);
  p.key("missing_parents");g.missing_parents=bounded_count(p,READER_REVISION_MAX_ENTITY_HISTORY*READER_REVISION_MAX_PARENTS);p.key("foreign_parents");g.foreign_parents=bounded_count(p,READER_REVISION_MAX_ENTITY_HISTORY*READER_REVISION_MAX_PARENTS);
  p.key("projection_safe");g.projection_safe=p.boolean();p.key("deleted");g.deleted=p.boolean();p.key("requires_restore");g.requires_restore=p.boolean();p.ch('}');
  need(g.revisions>=g.heads,"Graph has fewer revisions than heads");
  need((g.revisions==0)==(g.heads==0),"Nonempty acyclic graph must have heads");
  need(g.missing_parents+g.foreign_parents<=g.revisions*READER_REVISION_MAX_PARENTS,"Graph parent counts exceed total parent slots");
  need(g.heads||!g.requires_restore,"Empty graph cannot require restore");
  need((g.projection_safe!=0)==(g.heads==1&&!g.missing_parents&&!g.foreign_parents&&!g.requires_restore),"Projection safety differs from graph flags");need(!g.deleted||g.projection_safe,"Unsafe graph marked deleted");return g;}
const char *selection(const reader_revision_state &g){if(!g.heads)return "missing";if(g.missing_parents||g.foreign_parents)return "pending_parents";if(g.heads>1)return "concurrent";return g.projection_safe?"safe":"blocked_restore";}
struct wire_guard {char *data=nullptr;~wire_guard(){reader_revision_bytes_free(data);}};
void notify(const reader_annotation_import_options &o,const reader_annotation_import_item &item){if(o.item){int stop=0;try{stop=o.item(o.context,&item);}catch(...){fail(READER_AI_CALLBACK,"Item callback threw after reported commit");}if(stop)fail(READER_AI_CANCELLED,"Item callback cancelled; reported commit retained");}}
class importer {
 public:
  const reader_annotation_import_options &o;reader_annotation_import_stats &stats;reader_annotation_import_error &error;
  importer(const reader_annotation_import_options &a,reader_annotation_import_stats &s,reader_annotation_import_error &e):o(a),stats(s),error(e){}
  void scan(FILE *f,bool apply){
    parser p(f);counts c;std::set<std::string> ids;std::string previous;
    p.ch('{');p.key("type",true);need(p.str(16)=="header","First line must be header");p.key("format");need(p.str(64)=="exreader-annotation-export","Unknown export format");p.key("format_version");need(p.number()==1,"Unknown export format version");p.key("module_version");need(p.str(32)=="0.1.0","Unknown G05 module version");
    p.key("book_key");need(p.str(72)==o.target_book_key,"Header does not match host-confirmed original book identity");p.key("book_title");p.space();std::string title;bool have_title=p.peek()!='n';if(have_title)title=p.str(16384);else p.literal("null");
    p.key("order");need(p.str(64)=="annotation_id_ascending","Unknown annotation order");p.key("wire_encoding");need(p.str(64)=="json_string_utf8","Unknown wire encoding");p.ch('}');p.endline();
    if(apply&&o.metadata){reader_annotation_import_metadata m{};m.book_title=have_title?title.c_str():nullptr;metadata(m);}
    for(;;){
      error.line=p.line;error.item_index=c.heads;poll(o);p.ch('{');p.key("type",true);std::string type=p.str(16);
      if(type=="footer"){
        p.key("annotations");need(p.number()==c.annotations,"Footer annotation count mismatch");p.key("current");need(p.number()==c.current,"Footer current count mismatch");p.key("tombstones");need(p.number()==c.tombstones,"Footer tombstone count mismatch");p.key("pending_parents");need(p.number()==c.pending,"Footer pending count mismatch");p.key("concurrent");need(p.number()==c.concurrent,"Footer concurrent count mismatch");p.key("blocked_restore");need(p.number()==c.blocked,"Footer restore count mismatch");p.key("head_wires");need(p.number()==c.heads,"Footer head count mismatch");p.key("complete");need(p.boolean(),"Incomplete export footer");p.ch('}');p.endline();need(p.peek()==EOF,"Data after footer");break;
      }
      need(type=="annotation","Expected annotation or footer");p.key("annotation_id");std::string aid=p.str(32);need(hex(aid,32)&&aid>previous,"Duplicate or unordered annotation ID");previous=aid;
      p.key("entity_key");std::string key=p.str(105);need(key==std::string(o.target_book_key)+":"+aid,"Annotation identity does not match target book");
      p.key("selection");std::string kind=p.str(32);p.key("tombstone");bool tomb=p.boolean();p.key("graph");reader_revision_state g=graph(p);need(kind==selection(g),"Selection differs from original graph");need(tomb==(g.deleted!=0),"Tombstone differs from graph");
      if(apply&&o.metadata){reader_annotation_import_metadata m{};m.annotation_id=aid.c_str();m.entity_key=key.c_str();m.selection=kind.c_str();m.graph=g;m.tombstone=tomb;metadata(m);}
      ++c.annotations;c.omitted+=g.revisions-g.heads;if(kind=="safe"){if(tomb)++c.tombstones;else ++c.current;}else if(kind=="concurrent")++c.concurrent;else if(kind=="blocked_restore")++c.blocked;else ++c.pending;
      p.key("heads");p.ch('[');std::string previous_head;size_t heads=0;
      while(p.peek()!=']'){
        if(heads){p.ch(',');}
        p.ch('{');p.key("revision_id",true);std::string rid=p.str(32);need(hex(rid,32)&&rid>previous_head,"Duplicate or unordered revision ID");previous_head=rid;
        if(!apply){need(ids.insert(rid).second,"Duplicate revision ID in file");}
        if(c.heads>=READER_ANNOTATION_IMPORT_MAX_ITEMS)fail(READER_AI_LIMIT,"Too many imported heads");
        p.key("operation");std::string op=p.str(7);need(op=="put"||op=="delete"||op=="restore","Unknown operation");p.key("sha256");std::string sha=p.str(64);need(hex(sha,64),"Invalid wire SHA-256");p.key("bytes");uint64_t bytes=p.number();if(bytes>READER_REVISION_MAX_BYTES)fail(READER_AI_LIMIT,"Wire exceeds public limit");
        p.key("wire");std::string wire=p.str(READER_REVISION_MAX_BYTES);p.ch('}');need(bytes==wire.size(),"Wire byte length mismatch");
        error.item_index=c.heads;poll(o);reader_revision_info info{};reader_revision_error re{};
        reader_revision_status status=reader_revision_validate(o.revisions,wire.data(),wire.size(),sha.c_str(),&info,&re);
        if(status!=READER_REV_OK)fail(READER_AI_REVISION,"Public wire validation rejected input",status);
        need(rid==info.revision_id&&op==info.operation&&key==info.entity_key&&std::strcmp(info.entity_kind,"annotation")==0&&std::strcmp(info.book_key,o.target_book_key)==0,"Head metadata differs from exact wire identity");
        if(g.projection_safe)need((g.deleted!=0)==(op=="delete"),"Safe head operation differs from graph");
        need(g.revisions+g.missing_parents+g.foreign_parents>=g.heads+info.parent_count,"Graph omits required head parent slots");
        if(!apply){
          wire_guard old;size_t size=0;reader_revision_info prior{};status=reader_revision_get(o.revisions,rid.c_str(),&old.data,&size,&prior,&re);
          if(status==READER_REV_OK){if(size!=wire.size()||std::memcmp(old.data,wire.data(),size))fail(READER_AI_REVISION,"Existing revision ID has different exact wire",READER_REV_COLLISION);}
          else if(status!=READER_REV_NOT_FOUND)fail(READER_AI_REVISION,"Cannot inspect existing revision",status);
        }else if(c.heads>=o.resume_index){
          reader_annotation_import_item item{};item.index=c.heads;item.info=info;int made=0;
          status=reader_revision_receive(o.revisions,wire.data(),wire.size(),sha.c_str(),&item.info,&made,&re);
          if(status!=READER_REV_OK){item.info=info;} // receive clears its output on failure; retain the preflight identity.
          item.revision_code=status;item.created=made;item.committed=status==READER_REV_OK;item.exact_duplicate=item.committed&&!made;
          if(item.committed){stats.committed++;stats.created+=(uint64_t)made;stats.duplicates+=(uint64_t)!made;stats.next_index=c.heads+1;
            reader_revision_status gs=reader_revision_heads(o.revisions,"annotation",key.c_str(),nullptr,nullptr,&item.graph,&re);
            if(gs!=READER_REV_OK){item.revision_code=gs;item.outcome=READER_AI_REJECTED;notify(o,item);fail(READER_AI_REVISION,"Committed item but graph read failed",gs);}
            item.outcome=!made?READER_AI_EXACT_DUPLICATE:item.graph.missing_parents||item.graph.foreign_parents?READER_AI_MISSING_PARENT:item.graph.heads>1?READER_AI_CONFLICT:item.graph.requires_restore?READER_AI_BLOCKED_RESTORE:READER_AI_NEW;
          }else item.outcome=READER_AI_REJECTED;
          notify(o,item);if(status!=READER_REV_OK)fail(READER_AI_REVISION,"Per-item receive rejected; earlier commits retained",status);
        }
        ++c.heads;++heads;p.space();
      }
      p.ch(']');p.ch('}');p.endline();need(heads==g.heads,"Graph head count differs from records");
    }
    if(!apply){need(o.resume_index<=c.heads,"Resume cursor is beyond input");stats.annotations=c.annotations;stats.head_wires=c.heads;stats.omitted_history=c.omitted;stats.validated=1;stats.next_index=o.resume_index;}
  }
 private:
  void metadata(const reader_annotation_import_metadata &m){int stop=0;try{stop=o.metadata(o.context,&m);}catch(...){fail(READER_AI_CALLBACK,"Metadata callback threw");}if(stop)fail(READER_AI_CANCELLED,"Metadata callback cancelled; prior commits retained");}
};
void execute(const reader_annotation_import_options &o,reader_annotation_import_stats &stats,reader_annotation_import_error &error){
  if(o.struct_size<sizeof(o)||!o.revisions||!o.jsonl_path||!o.target_book_key)fail(READER_AI_ARGUMENT,"Missing import options");
  std::string path=o.jsonl_path,book=o.target_book_key;
  if(path.empty()||path.size()>4096||!utf8(path)||!book_key(book)||o.max_input_bytes>READER_ANNOTATION_IMPORT_HARD_MAX_BYTES)fail(READER_AI_ARGUMENT,"Invalid path, original book identity or byte budget");
  reader_revision_state state{};reader_revision_error re{};
  reader_revision_status rs=reader_revision_heads(o.revisions,"book",book.c_str(),nullptr,nullptr,&state,&re);
  if(rs!=READER_REV_OK)fail(READER_AI_REVISION,"Revision owner/graph check rejected before input I/O",rs);
  file source,spool;open_source(source,path.c_str());open_spool(spool);uint64_t budget=o.max_input_bytes?o.max_input_bytes:READER_ANNOTATION_IMPORT_DEFAULT_MAX_BYTES;
  char buffer[65536];for(;;){poll(o);size_t n=std::fread(buffer,1,sizeof(buffer),source.p);if(std::ferror(source.p))fail(READER_AI_IO,"Cannot read input",0,errno);if(n>budget-stats.input_bytes)fail(READER_AI_LIMIT,"Input exceeds configured byte budget");if(!n)break;
    if(std::fwrite(buffer,1,n,spool.p)!=n){fail(READER_AI_IO,"Cannot write private spool",0,errno);}
    stats.input_bytes+=n;}
  if(std::fflush(spool.p)||std::fseek(spool.p,0,SEEK_SET))fail(READER_AI_IO,"Cannot rewind private spool",0,errno);
  importer run(o,stats,error);run.scan(spool.p,false);
  if(std::fseek(spool.p,0,SEEK_SET))fail(READER_AI_IO,"Cannot rewind verified spool",0,errno);
  run.scan(spool.p,true);
}
}
extern "C" reader_annotation_import_status reader_annotation_import_run(const reader_annotation_import_options *o,reader_annotation_import_stats *stats,reader_annotation_import_error *error){
  if(active){if(error){std::memset(error,0,sizeof(*error));error->code=READER_AI_ARGUMENT;std::snprintf(error->message,sizeof(error->message),"%s","Reentrant annotation import refused");}return READER_AI_ARGUMENT;}
  active_guard guard;reader_annotation_import_stats s{};reader_annotation_import_error e{};
  try{if(!o)fail(READER_AI_ARGUMENT,"Missing import options");execute(*o,s,e);}
  catch(const failure &f){e.code=f.code;e.revision_code=f.revision;e.os_error=f.os;std::snprintf(e.message,sizeof(e.message),"%s",f.text);}
  catch(const std::bad_alloc &){e.code=READER_AI_MEMORY;std::snprintf(e.message,sizeof(e.message),"%s","Allocation failed");}
  catch(...){e.code=READER_AI_MEMORY;std::snprintf(e.message,sizeof(e.message),"%s","Unexpected implementation failure");}
  if(stats){*stats=s;}
  if(error){*error=e;}
  return e.code;
}
