/* SPDX-License-Identifier: MIT */
#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#define _CRT_SECURE_NO_WARNINGS
#include <windows.h>
#include <bcrypt.h>
#include "windows_records_owner.h"
#include <catalog.h>
#include <reader_commands.h>
#ifdef EXR_READER_WINDOWS_RAW3
#include "windows_raw3_apis.h"
#include "reading_capture_bytes.h"
#endif
#include <algorithm>
#include <array>
#include <climits>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <limits>
#include <set>
#include <string>
#include <vector>

namespace {
constexpr size_t PENDING_MAX=2u*1024u*1024u;
enum {KEY,ANNOTATION,REVISION,BOOTSTRAP,BODY,PARSER,CAPTURE,FORMAT,TITLE,AUTHOR,SORT,
#ifdef EXR_READER_WINDOWS_RAW3
 HEADS,KIND,OPERATION,SDK_BOOK,SOURCE_BYTES,FAVORITE,LEGACY_FIELDS,
 WRITER_VERSION=LEGACY_FIELDS,SOURCE_VERSION,PRIVATE_VERSION,FIELDS};
#else
 HEADS,KIND,OPERATION,SDK_BOOK,SOURCE_BYTES,FAVORITE,FIELDS};
#endif
using fields=std::array<std::string,FIELDS>;
struct failure {exr_status status;const char *message;};
void need(bool condition,const char *message,exr_status status=EXR_ARGUMENT) {if(!condition)throw failure{status,message};}
const char *z(const char *s) {return s?s:"";}
bool hex(const std::string &s,size_t n) {return s.size()==n&&s.find_first_not_of("0123456789abcdef")==std::string::npos;}
bool utf8(const std::string &s) {return s.empty() || (s.size()<=INT_MAX&&MultiByteToWideChar(CP_UTF8,MB_ERR_INVALID_CHARS,s.data(),(int)s.size(),nullptr,0)>0);}
bool book_key(const std::string &key) {
 auto at=key.find(':');if(at==std::string::npos||at==0||at>7||key.size()!=at+65)return false;
 const std::string formats="|epub|pdf|cbz|txt|html|fb2|docx|rtf|mobi|";
 return formats.find("|"+key.substr(0,at)+"|")!=std::string::npos&&hex(key.substr(at+1),64);
}
void copy(char *out,size_t n,const std::string &s) {need(s.size()<n,"Identity exceeds its bound");std::memcpy(out,s.c_str(),s.size()+1);}
char *owned(const std::string &s) {char *p=(char *)std::malloc(s.size()+1);need(p!=nullptr,"Cannot allocate record view",EXR_MEMORY);std::memcpy(p,s.c_str(),s.size()+1);return p;}
struct handle {
 HANDLE value=INVALID_HANDLE_VALUE;
 ~handle(){if(value!=INVALID_HANDLE_VALUE)CloseHandle(value);}
};
struct store {
 reader_revisions *revisions=nullptr;reader_catalog *catalog=nullptr;
 ~store(){if(catalog)reader_catalog_close(&catalog,nullptr);if(revisions)reader_revisions_close(&revisions,nullptr);}
 explicit store(const char *path) {
  need(reader_revisions_open(path,&revisions,nullptr)==READER_REV_OK,"Cannot open reading history",EXR_DATABASE);
  if(reader_catalog_open(path,&catalog,nullptr)) {reader_revisions_close(&revisions,nullptr);throw failure{EXR_DATABASE,"Cannot open product metadata"};}
 }
};
struct wire {char *data=nullptr;size_t size=0;~wire(){reader_revision_bytes_free(data);}};
struct encoded {char *data=nullptr;size_t size=0;~encoded(){reader_rs_free(data);}};
struct record {reader_rs_record value{};~record(){reader_rs_record_free(&value);}};
#ifdef EXR_READER_WINDOWS_RAW3
bool admitted_parser(const char *recorded) {
 if(!recorded)return false;
 if(!std::strcmp(recorded,exr_version()))return true;
 return !std::strcmp(exr_version(),"3.41.0")&&(!std::strcmp(recorded,"3.40.0")||
  !std::strcmp(recorded,"exreader-sdk-3.40.0")||!std::strcmp(recorded,"exreader-sdk-3.41.0"));
}
#endif
struct capture {
 reader_rs_capture value{};exr_anchor anchor{};exr_fixed_anchor fixed{};size_t part=0;
 ~capture(){exr_anchor_free(&anchor);exr_fixed_anchor_free(&fixed);}
};
void cancel(const winrecords_request &r) {need(!r.cancelled||!r.cancelled(r.context),"Reading operation cancelled",EXR_CANCELLED);}
void phase(const winrecords_request &r,int n) {if(r.phase)r.phase(r.context,n);}
struct book {
 std::string key,format,title,author,sort;uint64_t bytes=0;int64_t sdk=0;int favorite=0,deleted=0,failed=0;
};
int collect_book(void *opaque,const reader_catalog_row *row) {
 auto &b=*(book *)opaque;
 try {b.key=z(row->book_key);b.format=z(row->format);b.title=z(row->title);b.author=z(row->author);b.sort=z(row->sort_title);
  b.bytes=row->source_bytes;b.sdk=row->sdk_book_id;b.favorite=row->favorite;b.deleted=row->deleted;
 }catch(...){b.failed=1;}return 0;
}
book verified_book(store &s,const winrecords_request &r) {
 book b;int found=0;need(book_key(z(r.book_key))&&r.sdk_book>0,"Invalid verified original identity");
 need(reader_catalog_metadata(s.catalog,r.book_key,collect_book,&b,&found,nullptr)==0&&found&&!b.failed&&
  !b.deleted&&b.key==r.book_key&&b.sdk==r.sdk_book&&b.bytes==r.source_bytes&&
  b.key==b.format+":"+b.key.substr(b.key.find(':')+1),"Original differs from current product mapping",EXR_DATABASE);
 return b;
}
std::array<unsigned char,32> digest(const unsigned char *p,size_t n) {
 need(n<=std::numeric_limits<ULONG>::max(),"Oversized local request");
 BCRYPT_ALG_HANDLE algorithm=nullptr;std::array<unsigned char,32> hash{};
 need(BCryptOpenAlgorithmProvider(&algorithm,BCRYPT_SHA256_ALGORITHM,nullptr,0)>=0,"Cannot open local integrity hash",EXR_IO);
 NTSTATUS status=BCryptHash(algorithm,nullptr,0,(PUCHAR)p,(ULONG)n,hash.data(),(ULONG)hash.size());
 BCryptCloseAlgorithmProvider(algorithm,0);need(status>=0,"Cannot hash local request",EXR_IO);return hash;
}
uint32_t u32(const unsigned char *p) {return (uint32_t)p[0]|((uint32_t)p[1]<<8)|((uint32_t)p[2]<<16)|((uint32_t)p[3]<<24);}
void put32(std::vector<unsigned char> &out,uint32_t v) {for(unsigned i=0;i<4;i++)out.push_back((unsigned char)(v>>(i*8)));}
uint64_t number(const std::string &s) {
 need(!s.empty()&&s.size()<=20&&(s.size()==1||s[0]!='0'),"Invalid request number");uint64_t value=0;
 for(unsigned char c:s) {need(c>='0'&&c<='9'&&value<=(UINT64_MAX-(c-'0'))/10,"Invalid request number");value=value*10+c-'0';}return value;
}
void shape(const fields &p) {
 need(book_key(p[KEY])&&hex(p[REVISION],32)&&hex(p[BOOTSTRAP],32),"Invalid original reading request");
 auto kind=number(p[KIND]),op=number(p[OPERATION]);
 need(kind>=READER_RC_PROGRESS&&kind<=READER_RC_NOTE_TEXT&&op<=READER_RC_RESTORE&&
  number(p[SDK_BOOK])>0&&number(p[SOURCE_BYTES])>0&&number(p[FAVORITE])<=1,"Invalid request values");
 need(kind==READER_RC_PROGRESS?p[ANNOTATION].empty():hex(p[ANNOTATION],32),"Invalid annotation identity");
 need(p[HEADS].size()<=32*32&&p[HEADS].size()%32==0&&p[BODY].size()<=65536&&
  !p[PARSER].empty()&&p[PARSER].size()<=64&&p[KEY].substr(0,p[KEY].find(':'))==p[FORMAT]&&
  number(p[SDK_BOOK])<=INT64_MAX&&utf8(p[BODY])&&utf8(p[TITLE])&&utf8(p[AUTHOR])&&utf8(p[SORT]),"Invalid request bounds");
 need(kind!=READER_RC_NOTE_TEXT || (op==READER_RC_PUT&&p[HEADS].size()==32&&p[CAPTURE].empty()),"Invalid retained note edit");
 need(op==READER_RC_PUT || p[HEADS].size()==32,"Delete or restore requires its safe head");
 std::set<std::string> unique;
 for(size_t i=0;i<p[HEADS].size();i+=32)need(hex(p[HEADS].substr(i,32),32)&&unique.insert(p[HEADS].substr(i,32)).second,"Invalid observed head set");
#ifdef EXR_READER_WINDOWS_RAW3
 auto writer=number(p[WRITER_VERSION]),source=number(p[SOURCE_VERSION]),version=number(p[PRIVATE_VERSION]);
 need((version==1&&writer==2&&source==0)||(version==2&&writer>=1&&writer<=3&&source>=1&&source<=3),
      "Invalid private request version or explicit writer/source");
 need(version!=2||op!=READER_RC_RESTORE||writer==source,"Restore must preserve its exact source version");
#endif
}
std::vector<unsigned char> pack(const fields &p) {
 shape(p);std::vector<unsigned char> payload;
 for(const auto &field:p) {need(field.size()<=PENDING_MAX-5&&payload.size()<=PENDING_MAX-field.size()-5,"Local reading request exceeds 2 MiB",EXR_LIMIT);
  put32(payload,(uint32_t)field.size()+1);payload.insert(payload.end(),field.begin(),field.end());payload.push_back(0);}
#ifdef EXR_READER_WINDOWS_RAW3
 need(p[PRIVATE_VERSION]=="2","Never republish or migrate a legacy pending request");
 auto hash=digest(payload.data(),payload.size());std::vector<unsigned char> out={'E','X','R','R','D','0','0','2'};
#else
 auto hash=digest(payload.data(),payload.size());std::vector<unsigned char> out={'E','X','R','R','D','0','0','1'};
#endif
 put32(out,(uint32_t)payload.size());out.insert(out.end(),hash.begin(),hash.end());out.insert(out.end(),payload.begin(),payload.end());return out;
}
fields unpack(const std::vector<unsigned char> &raw) {
#ifdef EXR_READER_WINDOWS_RAW3
 need(raw.size()>=44&&u32(raw.data()+8)==raw.size()-44,"Damaged reading request");
 bool legacy=!std::memcmp(raw.data(),"EXRRD001",8);
 need(legacy||!std::memcmp(raw.data(),"EXRRD002",8),"Unknown private reading request");
 auto hash=digest(raw.data()+44,raw.size()-44);need(!std::memcmp(hash.data(),raw.data()+12,32),"Reading request integrity differs");
 fields p;size_t at=44,count=legacy?(size_t)LEGACY_FIELDS:(size_t)FIELDS;
 for(size_t i=0;i<count;i++) {auto &field=p[i];
  need(at<=raw.size()&&raw.size()-at>=4,"Truncated reading request");size_t n=u32(raw.data()+at);at+=4;
  need(n>0&&n<=raw.size()-at&&raw[at+n-1]==0,"Invalid request field");
  need((!legacy&&i==CAPTURE)||!std::memchr(raw.data()+at,0,n-1),"Embedded NUL in private text field");
  field.assign((const char *)raw.data()+at,n-1);at+=n;
 }
 need(at==raw.size(),"Trailing reading request bytes");
 if(legacy) {p[WRITER_VERSION]="2";p[SOURCE_VERSION]="0";p[PRIVATE_VERSION]="1";}
 else need(p[PRIVATE_VERSION]=="2","Private header and intent version disagree");
 shape(p);return p;
#else
 need(raw.size()>=44&&!std::memcmp(raw.data(),"EXRRD001",8)&&u32(raw.data()+8)==raw.size()-44,"Damaged reading request");
 auto hash=digest(raw.data()+44,raw.size()-44);need(!std::memcmp(hash.data(),raw.data()+12,32),"Reading request integrity differs");
 fields p;size_t at=44;
 for(auto &field:p) {need(at<=raw.size()&&raw.size()-at>=4,"Truncated reading request");size_t n=u32(raw.data()+at);at+=4;
  need(n>0&&n<=raw.size()-at&&raw[at+n-1]==0&&!std::memchr(raw.data()+at,0,n-1),"Invalid request string");
  field.assign((const char *)raw.data()+at,n-1);at+=n;}
 need(at==raw.size(),"Trailing reading request bytes");shape(p);return p;
#endif
}
bool regular(HANDLE file,BY_HANDLE_FILE_INFORMATION *out=nullptr) {
 BY_HANDLE_FILE_INFORMATION info{};if(!GetFileInformationByHandle(file,&info))return false;
 if(out)*out=info;
 return !(info.dwFileAttributes&(FILE_ATTRIBUTE_REPARSE_POINT|FILE_ATTRIBUTE_DIRECTORY))&&info.nNumberOfLinks==1;
}
/* 0 absent, 1 valid. Malformed or inaccessible requests are retained and refused. */
int pending_read(const wchar_t *path,fields &p) {
 handle file;file.value=CreateFileW(path,GENERIC_READ,FILE_SHARE_READ,nullptr,OPEN_EXISTING,FILE_FLAG_OPEN_REPARSE_POINT,nullptr);
 if(file.value==INVALID_HANDLE_VALUE) {need(GetLastError()==ERROR_FILE_NOT_FOUND,"Cannot inspect original reading request",EXR_IO);return 0;}
 BY_HANDLE_FILE_INFORMATION info{};need(regular(file.value,&info)&&!info.nFileSizeHigh&&info.nFileSizeLow>=44&&
  info.nFileSizeLow<=PENDING_MAX+44,"Unsafe or oversized original reading request",EXR_IO);
 std::vector<unsigned char> raw(info.nFileSizeLow);size_t at=0;
 while(at<raw.size()) {DWORD got=0;need(ReadFile(file.value,raw.data()+at,(DWORD)std::min<size_t>(65536,raw.size()-at),&got,nullptr)&&got,"Cannot read original request",EXR_IO);at+=got;}
 p=unpack(raw);return 1;
}
void pending_status(const wchar_t *path,winrecords_response &out) {
 fields p;
 try {out.pending=pending_read(path,p);if(out.pending) {copy(out.pending_key,sizeof(out.pending_key),p[KEY]);copy(out.pending_revision,sizeof(out.pending_revision),p[REVISION]);}}
 catch(...) {out.pending=out.pending_corrupt=1;}
}
void publish(const winrecords_request &r,const fields &p) {
 const wchar_t *path=r.pending_path;
 fields existing;need(!pending_read(path,existing),"An earlier reading request needs confirmation",EXR_DATABASE);
 auto raw=pack(p);std::wstring temporary=std::wstring(path)+L".tmp-";
 for(char c:p[REVISION])temporary.push_back((wchar_t)c);
 handle file;file.value=CreateFileW(temporary.c_str(),GENERIC_WRITE,0,nullptr,CREATE_NEW,
  FILE_ATTRIBUTE_NORMAL|FILE_FLAG_OPEN_REPARSE_POINT|FILE_FLAG_WRITE_THROUGH,nullptr);
 need(file.value!=INVALID_HANDLE_VALUE&&regular(file.value),"Cannot create private reading request",EXR_IO);
 bool moved=false;
 try {
  size_t at=0;while(at<raw.size()) {cancel(r);DWORD wrote=0;need(WriteFile(file.value,raw.data()+at,(DWORD)std::min<size_t>(65536,raw.size()-at),&wrote,nullptr)&&wrote,"Cannot persist original request",EXR_IO);at+=wrote;}
  need(FlushFileBuffers(file.value)!=0,"Cannot flush original reading request",EXR_IO);
  CloseHandle(file.value);file.value=INVALID_HANDLE_VALUE;
  cancel(r);
  need(MoveFileExW(temporary.c_str(),path,MOVEFILE_WRITE_THROUGH)!=0,"Cannot publish original reading request",EXR_IO);moved=true;
 }catch(...) {if(file.value!=INVALID_HANDLE_VALUE){CloseHandle(file.value);file.value=INVALID_HANDLE_VALUE;}if(!moved)DeleteFileW(temporary.c_str());throw;}
}
void clear(const wchar_t *path,const std::string &revision) {
 fields p;if(!pending_read(path,p))return;
 need(p[REVISION]==revision,"Another original request is pending",EXR_DATABASE);
 need(DeleteFileW(path)!=0,"Committed reading request still needs confirmation",EXR_IO);
}
std::string selected(store &s,const std::string &key,bool progress,const std::string &annotation,
 const char *expected,const char *sha,reader_revision_info &info,reader_revision_selection &selection) {
 wire held;std::string entity=progress?key:key+":"+annotation;
 auto code=reader_revision_selected(s.revisions,progress?"progress":"annotation",entity.c_str(),&held.data,&held.size,&info,&selection,nullptr);
 need(code==READER_REV_OK||code==READER_REV_NOT_FOUND||code==READER_REV_UNSAFE,"Cannot read record history",EXR_DATABASE);
 if(expected&&expected[0])need(code==READER_REV_OK&&expected==std::string(info.revision_id)&&z(sha)==std::string(info.sha256),"Record changed; refresh before acting");
 return held.data?std::string(held.data,held.size):std::string();
}
struct heads {char ids[32][33]{};size_t count=0;int overflow=0;};
int collect_head(void *opaque,const reader_revision_head *h) {
 auto &out=*(heads *)opaque;if(out.count==32){out.overflow=1;return 1;}std::memcpy(out.ids[out.count++],h->revision_id,33);return 0;
}
void from_record(const reader_rs_record &r,reader_rs_capture &c,exr_anchor &a,exr_fixed_anchor &f) {
 c={};a={};f={};c.mode=r.mode;c.page=(size_t)r.page;c.part_path=r.part_path;if(!r.has_location)return;
 if(r.mode==READER_RS_FIXED_PAGE) {f.start=(size_t)r.start;f.end=(size_t)r.end;f.page_id=r.page_id;f.exact=r.exact;f.prefix=r.prefix;f.suffix=r.suffix;
  f.exact_size=r.exact_size;f.prefix_size=r.prefix_size;f.suffix_size=r.suffix_size;c.fixed=&f;
 }else {a.start=(size_t)r.start;a.end=(size_t)r.end;a.exact=r.exact;a.prefix=r.prefix;a.suffix=r.suffix;a.chapter=r.chapter;c.anchor=&a;}
}
fields prepare(store &s,const book &b,const winrecords_request &r) {
 fields p,existing;need(!pending_read(r.pending_path,existing),"An earlier reading save needs confirmation",EXR_DATABASE);
 bool progress=r.kind==READER_RC_PROGRESS;need(r.kind>=READER_RC_PROGRESS&&r.kind<=READER_RC_NOTE_TEXT&&r.operation>=0&&r.operation<=READER_RC_RESTORE,"Invalid reading operation");
 p[KEY]=b.key;p[ANNOTATION]=z(r.annotation_id);p[BODY]=progress?"":z(r.body);p[PARSER]=exr_version();
 need(p[BODY].size()<=65536&&utf8(p[BODY])&&(!progress||!z(r.body)[0]),"Record text must be bounded UTF-8");
 need(progress?p[ANNOTATION].empty():(p[ANNOTATION].empty()||hex(p[ANNOTATION],32)),"Invalid selected record identity");
 need(r.kind!=READER_RC_NOTE_TEXT||r.operation==READER_RC_PUT,"Note editing keeps the live selector");
 char id[33];need(reader_revision_new_id(id,nullptr)==READER_REV_OK,"Cannot allocate save identity",EXR_DATABASE);p[REVISION]=id;
 need(reader_revision_new_id(id,nullptr)==READER_REV_OK,"Cannot allocate bootstrap identity",EXR_DATABASE);p[BOOTSTRAP]=id;
 if(!progress&&p[ANNOTATION].empty()){need(reader_revision_new_id(id,nullptr)==READER_REV_OK,"Cannot allocate record identity",EXR_DATABASE);p[ANNOTATION]=id;}
 reader_revision_info info{};reader_revision_selection selection{};
 auto old=selected(s,b.key,progress,p[ANNOTATION],r.head,r.sha256,info,selection);
 need(selection.kind==READER_SELECTION_MISSING||selection.kind==READER_SELECTION_SAFE,"Reading history needs explicit conflict handling");
 need(selection.kind!=READER_SELECTION_SAFE||z(r.head)[0],"Refresh existing reading history before saving");
 need(r.operation==READER_RC_RESTORE?selection.graph.deleted:!selection.graph.deleted,"Deletion requires explicit restore");
 heads observed;reader_revision_state graph{};std::string entity=progress?b.key:b.key+":"+p[ANNOTATION];
 need(reader_revision_heads(s.revisions,progress?"progress":"annotation",entity.c_str(),collect_head,&observed,&graph,nullptr)==READER_REV_OK&&
  !observed.overflow&&observed.count==graph.heads&&observed.count<=1,"Complete safe head set is unavailable");
 need((r.kind!=READER_RC_NOTE_TEXT&&r.operation==READER_RC_PUT)||observed.count==1,"Editing requires an existing safe record");
 const char *parents[32];for(size_t i=0;i<observed.count;i++){parents[i]=observed.ids[i];p[HEADS]+=observed.ids[i];}
 capture actual;record retained;reader_rs_error error{};int kind=r.kind;
 if(r.operation==READER_RC_RESTORE) {
  need(hex(z(r.version),32),"Choose a retained version to restore");wire version;reader_revision_info previous{};
  need(reader_revision_get(s.revisions,r.version,&version.data,&version.size,&previous,nullptr)==READER_REV_OK&&
   std::string(previous.entity_key)==info.entity_key&&std::string(previous.book_key)==b.key&&std::strcmp(previous.operation,"delete"),"Retained version belongs to another record");
  need(reader_rs_decode(s.revisions,version.data,version.size,&retained.value,&error)==READER_RS_OK&&retained.value.has_location,"Retained selector is unavailable");
#ifdef EXR_READER_WINDOWS_RAW3
  need(admitted_parser(retained.value.parser_version),"Retained parser version is unsupported");
#endif
  need(r.capture!=nullptr,"Missing renderer capture");
  auto found=r.capture(r.context,&retained.value,&actual.value,&actual.anchor,&actual.fixed,&actual.part);
  need(found==EXR_OK,"Restore location was not independently found",found);
  p[BODY]=z(retained.value.note_text);if(!progress)kind=retained.value.start==retained.value.end?READER_RC_BOOKMARK:READER_RC_HIGHLIGHT;
 }else if(r.operation==READER_RC_DELETE) {
  need(!old.empty()&&reader_rs_decode(s.revisions,old.data(),old.size(),&retained.value,&error)==READER_RS_OK,"Current selector is unavailable");actual.value.mode=retained.value.mode;p[BODY].clear();
 }else if(r.kind!=READER_RC_NOTE_TEXT) {
  need(r.capture!=nullptr,"Missing renderer capture");
  auto found=r.capture(r.context,nullptr,&actual.value,&actual.anchor,&actual.fixed,&actual.part);
  need(found==EXR_OK,"Real current-page capture failed",found);
 }
#ifdef EXR_READER_WINDOWS_RAW3
 if(r.kind==READER_RC_NOTE_TEXT) {
  need(!old.empty()&&reader_rs_decode(s.revisions,old.data(),old.size(),&retained.value,&error)==READER_RS_OK&&
       retained.value.has_location,"Current note source is unavailable");
  need(admitted_parser(retained.value.parser_version),"Current note parser version is unsupported");
  need(retained.value.mode!=READER_RS_FIXED_PAGE||retained.value.exact!=nullptr,"NULL location cannot be edited");
  actual.value.mode=retained.value.mode;
 }
 unsigned writer=actual.value.mode==READER_RS_FIXED_PAGE?3u:2u;
 unsigned source=writer;
 if(r.operation==READER_RC_RESTORE||r.operation==READER_RC_DELETE||r.kind==READER_RC_NOTE_TEXT) {
  need(retained.value.anchor_version>=1&&retained.value.anchor_version<=3,"Unknown selected source version");
  source=(unsigned)retained.value.anchor_version;
  if(r.operation==READER_RC_RESTORE)writer=source;
 }
 p[WRITER_VERSION]=std::to_string(writer);p[SOURCE_VERSION]=std::to_string(source);p[PRIVATE_VERSION]="2";
#endif
 if(r.kind!=READER_RC_NOTE_TEXT) {
  if(r.operation!=READER_RC_DELETE&&!progress) {
   uint64_t start=actual.value.mode==READER_RS_FIXED_PAGE?actual.fixed.start:actual.anchor.start;
   uint64_t end=actual.value.mode==READER_RS_FIXED_PAGE?actual.fixed.end:actual.anchor.end;
   need(kind==READER_RC_BOOKMARK?start==end:start<end,"A bookmark is a point; a highlight requires selected text");
  }
#ifdef EXR_READER_WINDOWS_RAW3
  reader_rs_capture native=actual.value;exr_anchor borrowed_anchor{};exr_fixed_anchor borrowed_fixed{};size_t native_part=actual.part;
  if(r.operation==READER_RC_DELETE) {from_record(retained.value,native,borrowed_anchor,borrowed_fixed);native_part=(size_t)retained.value.part;}
  unsigned char *bytes=nullptr;size_t count=0;
  auto status=reader_private_capture_encode(&native,native_part,writer,&bytes,&count);
  struct private_bytes {unsigned char *value;~private_bytes(){reader_private_capture_free(value);}} held{bytes};
  need(status==EXR_OK,"Cannot persist native SDK capture",status);
  p[CAPTURE].assign((const char *)bytes,count);
#else
  reader_rs_envelope envelope={p[REVISION].c_str(),r.operation==READER_RC_DELETE?"delete":r.operation==READER_RC_RESTORE?"restore":"put",
   progress?"progress":"annotation",b.key.c_str(),progress?nullptr:p[ANNOTATION].c_str(),parents,observed.count,
   progress||r.operation==READER_RC_DELETE?nullptr:p[BODY].c_str(),p[PARSER].c_str()};
  encoded bytes;need(reader_rs_encode_v2(s.revisions,&envelope,&actual.value,actual.part,&bytes.data,&bytes.size,&error)==READER_RS_OK,"Capture has no lossless reading wire");
  p[CAPTURE].assign(bytes.data,bytes.size);
#endif
 }
 p[FORMAT]=b.format;p[TITLE]=b.title;p[AUTHOR]=b.author;p[SORT]=b.sort;p[KIND]=std::to_string(kind);p[OPERATION]=std::to_string(r.operation);
 p[SDK_BOOK]=std::to_string(r.sdk_book);p[SOURCE_BYTES]=std::to_string(b.bytes);p[FAVORITE]=std::to_string(b.favorite);
 phase(r,1);cancel(r);shape(p);return p;
}
void apply(store &s,const book &b,const winrecords_request &r,const fields &p,winrecords_response &out) {
 need(p[KEY]==b.key&&number(p[SDK_BOOK])==(uint64_t)r.sdk_book&&number(p[SOURCE_BYTES])==r.source_bytes&&p[FORMAT]==b.format,"Open the original book to retry its retained request");
 int kind=(int)number(p[KIND]),operation=(int)number(p[OPERATION]);record decoded;reader_rs_capture captured{};exr_anchor a{};exr_fixed_anchor f{};
 reader_rs_error error{};
 if(kind!=READER_RC_NOTE_TEXT) {
#ifdef EXR_READER_WINDOWS_RAW3
  if(p[PRIVATE_VERSION]=="2") {
   auto status=reader_private_capture_decode(p[CAPTURE].data(),p[CAPTURE].size(),&decoded.value);
   need(status==EXR_OK&&decoded.value.has_location&&decoded.value.anchor_version==number(p[WRITER_VERSION]),
        "Retained native capture differs",status==EXR_OK?EXR_ARGUMENT:status);
  } else {
#endif
  need(reader_rs_decode(s.revisions,p[CAPTURE].data(),p[CAPTURE].size(),&decoded.value,&error)==READER_RS_OK&&
   std::string(decoded.value.book_key)==b.key&&std::string(decoded.value.entity_kind)==(kind==READER_RC_PROGRESS?"progress":"annotation")&&
   (kind==READER_RC_PROGRESS||p[ANNOTATION]==decoded.value.annotation_id),"Retained capture identity differs");
#ifdef EXR_READER_WINDOWS_RAW3
  }
#endif
  from_record(decoded.value,captured,a,f);
#ifdef EXR_READER_WINDOWS_RAW3
  if(operation==READER_RC_DELETE) {captured.anchor=nullptr;captured.fixed=nullptr;}
#endif
 }
 uint64_t bytes=0;auto identity=reader_revision_book_identity(s.revisions,b.key.c_str(),&bytes,nullptr);
 if(identity==READER_REV_NOT_FOUND) {
  reader_command_context context={s.revisions,p[BOOTSTRAP].c_str(),nullptr,0};
  reader_book_command bootstrap={READER_COMMAND_PUT,b.key.c_str(),p[FORMAT].c_str(),std::strchr(b.key.c_str(),':')+1,
   p[TITLE].c_str(),p[AUTHOR].c_str(),p[SORT].c_str(),number(p[SOURCE_BYTES]),(int)number(p[FAVORITE])};
  reader_command_result result{};need(reader_command_apply_book(&context,&bootstrap,&result,nullptr)==READER_COMMAND_OK,"Book bootstrap refused; original save retained",EXR_DATABASE);
 }else need(identity==READER_REV_OK&&bytes==b.bytes,"Retained book history differs",EXR_DATABASE);
 heads observed;const char *parents[32];
 for(size_t i=0;i<p[HEADS].size();i+=32){std::memcpy(observed.ids[observed.count],p[HEADS].data()+i,32);parents[observed.count]=observed.ids[observed.count];observed.count++;}
 reader_rc_context context={s.revisions,p[REVISION].c_str(),parents,observed.count,p[PARSER].c_str()};
 reader_rc_command command={(reader_rc_kind)kind,(reader_rc_operation)operation,b.key.c_str(),kind==READER_RC_PROGRESS?nullptr:p[ANNOTATION].c_str(),
  kind==READER_RC_NOTE_TEXT?nullptr:&captured,(size_t)decoded.value.part,kind==READER_RC_PROGRESS||operation==READER_RC_DELETE?nullptr:p[BODY].c_str()};
#ifdef EXR_READER_WINDOWS_RAW3
 reader_rc_result saved{};reader_rc_error problem{};
 auto code=reader_rc_apply_raw_v3(&context,&command,(unsigned)number(p[WRITER_VERSION]),&saved,&problem);
#else
 reader_rc_result saved{};reader_rc_error problem{};auto code=reader_rc_apply(&context,&command,&saved,&problem);
#endif
 out.command_code=code;out.created=saved.created;out.committed=code==READER_RC_OK;
 copy(out.saved_revision,sizeof(out.saved_revision),p[REVISION]);copy(out.saved_annotation,sizeof(out.saved_annotation),p[ANNOTATION]);
 need(code==READER_RC_OK,code==READER_RC_UNSAFE||code==READER_RC_SOURCE?"History changed; original request retained for review":"Save is unconfirmed; original request retained",EXR_DATABASE);
 phase(r,3);clear(r.pending_path,p[REVISION]);
 std::snprintf(out.message,sizeof(out.message),"%s",saved.created?"Reading record saved":"Original reading save confirmed without duplication");
}
int av_cancel(void *context) {auto &r=*(const winrecords_request *)context;return r.cancelled?r.cancelled(r.context):0;}
void list(store &s,const book &b,const winrecords_request &r,winrecords_response &out) {
 reader_av_view *view=nullptr;reader_av_options options{};options.struct_size=sizeof(options);options.max_page_bytes=READER_AV_PAGE_BYTES_MIN;
 options.cancel=av_cancel;options.cancel_context=(void *)&r;reader_av_cursor cursor{};reader_av_error error{};
 auto code=reader_av_open(s.revisions,b.key.c_str(),&options,&view,&error);
 if(code==READER_AV_OK)code=reader_av_cursor_start(view,r.direction<0?-1:1,&cursor,&error);
 if(code==READER_AV_OK&&z(r.after)[0]) {if(!hex(r.after,32))code=READER_AV_CURSOR;else {cursor.has_after=1;copy(cursor.after_id,sizeof(cursor.after_id),r.after);}}
 if(code==READER_AV_OK)code=reader_av_page_get(view,&cursor,32,&out.page,&error);
 if(code==READER_AV_OK&&out.page.count) {
  if(r.direction<0)std::reverse(out.page.items,out.page.items+out.page.count);
  for(int direction:{-1,1}) {
   reader_av_cursor bound{};reader_av_page probe{};
   code=reader_av_cursor_start(view,direction,&bound,&error);
   bound.has_after=1;copy(bound.after_id,33,out.page.items[direction<0?0:out.page.count-1].annotation_id);
   if(code==READER_AV_OK)code=reader_av_page_get(view,&bound,1,&probe,&error);
   if(direction<0){out.page.reverse=bound;out.has_previous=probe.count!=0;}
   else {out.page.next=bound;out.has_next=probe.count!=0;}
   reader_av_page_free(&probe);if(code!=READER_AV_OK)break;
  }
  out.page.complete=!out.has_next;
 }
 reader_av_close(&view,nullptr);need(code==READER_AV_OK,"Record list did not complete",code==READER_AV_CANCELLED?EXR_CANCELLED:EXR_DATABASE);
 selected(s,b.key,true,"",nullptr,nullptr,out.progress_info,out.progress);
}
/* Read only ASCII root-parent IDs from public-validated wire, not an alternate
   transport validator. Nested text/quotes are skipped at their actual depth. */
std::string ascii(const char *&p,const char *end) {
 need(p<end&&*p++=='"',"Invalid validated parent string");std::string out;
 while(p<end&&*p!='"') {unsigned c=(unsigned char)*p++;
  if(c=='\\') {need(p<end,"Truncated parent escape");c=(unsigned char)*p++;
   if(c=='u') {need(end-p>=4,"Truncated parent escape");c=0;for(int i=0;i<4;i++){unsigned v=(unsigned char)*p++;unsigned d=v>='0'&&v<='9'?v-'0':v>='a'&&v<='f'?v-'a'+10:v>='A'&&v<='F'?v-'A'+10:16;need(d<16,"Invalid parent escape");c=c*16+d;}}
   else if(c=='b')c=8;else if(c=='f')c=12;else if(c=='n')c=10;else if(c=='r')c=13;else if(c=='t')c=9;
   else need(c=='"'||c=='\\'||c=='/',"Invalid parent escape");}
  need(c>0&&c<128&&out.size()<127,"Oversized parent identifier");out.push_back((char)c);}
 need(p<end,"Truncated parent string");p++;return out;
}
std::vector<std::string> parents(const char *wire,size_t size) {
 const char *p=wire,*end=wire+size;unsigned depth=0;bool root_key=false;
 auto space=[&](){while(p<end&&(*p==' '||*p=='\n'||*p=='\r'||*p=='\t'))p++;};
 while(p<end) {
  if(*p=='"') {
   if(depth==1&&root_key) {
    auto key=ascii(p,end);space();need(p<end&&*p++==':',"Invalid validated root key");
    if(key=="parents") {space();need(p<end&&*p++=='[',"Invalid parent array");std::vector<std::string> ids;
     for(;;){space();if(p<end&&*p==']')return ids;need(ids.size()<32,"Too many parents");auto id=ascii(p,end);need(hex(id,32),"Invalid parent identity");ids.push_back(id);space();if(p<end&&*p==']')return ids;need(p<end&&*p++==',',"Invalid parent array");}}
    root_key=false;continue;
   }
   p++;while(p<end&&*p!='"'){if(*p=='\\'&&p+1<end)p++;p++;}need(p<end,"Truncated validated string");p++;continue;
  }
  char c=*p++;if(c=='{'||c=='['){depth++;if(depth==1)root_key=true;}
  else if(c=='}'||c==']'){need(depth!=0,"Invalid validated depth");depth--;}
  else if(c==','&&depth==1)root_key=true;
 }
 throw failure{EXR_ARGUMENT,"Validated revision has no parent array"};
}
void read_record(store &s,const book &b,const winrecords_request &r,winrecords_response &out) {
 reader_revision_info info{};reader_revision_selection graph{};
 auto bytes=selected(s,b.key,r.progress_target!=0,z(r.annotation_id),r.head,r.sha256,info,graph);
 need(graph.kind==READER_SELECTION_SAFE&&!graph.graph.deleted&&!bytes.empty(),"Record is not a safe live location");
 need(reader_rs_decode(s.revisions,bytes.data(),bytes.size(),&out.record,nullptr)==READER_RS_OK,"Saved selector cannot be decoded");
#ifdef EXR_READER_WINDOWS_RAW3
 need(admitted_parser(out.record.parser_version),"Saved parser version is unsupported");
#endif
}
void history(store &s,const book &b,const winrecords_request &r,winrecords_response &out) {
 reader_revision_info info{};reader_revision_selection graph{};
 selected(s,b.key,r.progress_target!=0,z(r.annotation_id),r.head,r.sha256,info,graph);
 need(graph.kind==READER_SELECTION_SAFE&&graph.graph.deleted,"Restore requires a safe tombstone");
 std::vector<std::string> queue={info.revision_id};std::set<std::string> seen;size_t at=0,total=0;bool stopped=false;
 while(at<queue.size()&&!stopped) {
  cancel(r);auto id=queue[at++];if(!seen.insert(id).second)continue;
  wire held;reader_revision_info previous{};
  need(reader_revision_get(s.revisions,id.c_str(),&held.data,&held.size,&previous,nullptr)==READER_REV_OK&&
   std::string(previous.entity_key)==info.entity_key,"Retained ancestry differs",EXR_DATABASE);
  if(held.size>PENDING_MAX-total){stopped=true;break;}total+=held.size;
  for(const auto &parent:parents(held.data,held.size))if(std::find(queue.begin(),queue.end(),parent)==queue.end()) {
   if(queue.size()==128){stopped=true;break;}queue.push_back(parent);}
  if(std::strcmp(previous.operation,"delete")) {
   record decoded;need(reader_rs_decode(s.revisions,held.data,held.size,&decoded.value,nullptr)==READER_RS_OK&&decoded.value.has_location,"Historical selector is unavailable");
#ifdef EXR_READER_WINDOWS_RAW3
   if(!admitted_parser(decoded.value.parser_version)||
      (decoded.value.mode==READER_RS_FIXED_PAGE&&!decoded.value.exact))continue;
#endif
   size_t index=out.version_count++;copy(out.versions[index],33,id);
   std::string label=z(decoded.value.note_text);if(label.empty())label=z(decoded.value.exact);if(label.empty())label="Saved reading location";
   if(label.size()>240){size_t n=240;while(n&&((unsigned char)label[n]&192)==128)n--;label.resize(n);label+="…";}
   out.version_labels[index]=owned(label);if(out.version_count==32)stopped=true;
  }
 }
 out.history_complete=!stopped&&at==queue.size();
}
}

extern "C" void winrecords_response_free(winrecords_response *out) {
 if(!out)return;reader_av_page_free(&out->page);reader_rs_record_free(&out->record);
 for(char *label:out->version_labels)std::free(label);std::memset(out,0,sizeof(*out));
}
extern "C" exr_status winrecords_execute(const winrecords_request *request,winrecords_response *out) {
 if(!out)return EXR_ARGUMENT;std::memset(out,0,sizeof(*out));exr_status status=EXR_OK;
 try {
  need(request&&request->database&&request->pending_path&&request->book_key,"Missing native owner input");auto &r=*request;
  cancel(r);store s(r.database);book b=verified_book(s,r);copy(out->key,sizeof(out->key),b.key);
  if(r.action==WINRECORDS_LIST)list(s,b,r,*out);
  else if(r.action==WINRECORDS_READ)read_record(s,b,r,*out);
  else if(r.action==WINRECORDS_HISTORY)history(s,b,r,*out);
  else if(r.action==WINRECORDS_DISCARD) {need(hex(z(r.pending_revision),32),"Choose the exact pending request");clear(r.pending_path,r.pending_revision);}
  else if(r.action==WINRECORDS_SAVE||r.action==WINRECORDS_RETRY) {
   fields p;
   if(r.action==WINRECORDS_SAVE){p=prepare(s,b,r);publish(r,p);}
   else need(pending_read(r.pending_path,p)==1,"No original reading request is pending");
   phase(r,2);apply(s,b,r,p,*out);
  }else throw failure{EXR_ARGUMENT,"Unknown reading operation"};
 }catch(const failure &error){status=error.status;std::snprintf(out->message,sizeof(out->message),"%s",error.message);}
 catch(...){status=EXR_MEMORY;std::snprintf(out->message,sizeof(out->message),"Cannot allocate bounded reading operation");}
 if(request&&request->pending_path)pending_status(request->pending_path,*out);
 return status;
}
