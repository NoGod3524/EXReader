// SPDX-License-Identifier: MIT
#include "reader_annotation_export.h"
#include <reader_projection.h>
#include <algorithm>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <exception>
#include <new>
#include <string>
#include <vector>
#ifdef _WIN32
#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#else
#include <errno.h>
#include <fcntl.h>
#include <unistd.h>
#endif

namespace {
typedef reader_annotation_export_status export_status;
struct failure {export_status code;int revision_code,rs_code,os_error;std::string message;};
[[noreturn]] void fail(export_status code,const std::string &message,int revision_code=0,int rs_code=0,int os_error=0){
  throw failure{code,revision_code,rs_code,os_error,message};
}
int last_os_error(){
#ifdef _WIN32
  return (int)GetLastError();
#else
  return errno;
#endif
}
const size_t kBuffer=65536;

bool well_formed(const char *s,size_t n){
  const unsigned char *p=(const unsigned char *)s;size_t i=0;
  while(i<n){
    unsigned char c=p[i];
    if(c==0)return false;
    if(c<0x80){i++;continue;}
    size_t len;uint32_t cp;
    if(c>=0xC2&&c<=0xDF){len=2;cp=c&0x1Fu;}
    else if((c&0xF0)==0xE0){len=3;cp=c&0x0Fu;}
    else if(c>=0xF0&&c<=0xF4){len=4;cp=c&0x07u;}
    else return false;
    if(i+len>n)return false;
    for(size_t k=1;k<len;k++){if((p[i+k]&0xC0)!=0x80)return false;cp=(cp<<6)|(p[i+k]&0x3Fu);}
    if(len==3&&(cp<0x800||(cp>=0xD800&&cp<=0xDFFF)))return false;
    if(len==4&&(cp<0x10000||cp>0x10FFFF))return false;
    i+=len;
  }
  return true;
}
bool is_separator(char c){
#ifdef _WIN32
  return c=='/'||c=='\\';
#else
  return c=='/';
#endif
}
void check_path(const char *path,const char *what){
  if(!path||!*path)fail(READER_ANNOTATION_EXPORT_ARGUMENT,std::string(what)+" path is empty");
  size_t n=std::strlen(path);
  if(n>READER_ANNOTATION_EXPORT_PATH_MAX)fail(READER_ANNOTATION_EXPORT_ARGUMENT,std::string(what)+" path exceeds 4096 bytes");
  if(!well_formed(path,n))fail(READER_ANNOTATION_EXPORT_ARGUMENT,std::string(what)+" path is not well-formed UTF-8");
  if(is_separator(path[n-1]))fail(READER_ANNOTATION_EXPORT_ARGUMENT,std::string(what)+" path names a directory");
}
#ifdef _WIN32
std::wstring wide(const std::string &s){
  if(s.empty())return std::wstring();
  int n=MultiByteToWideChar(CP_UTF8,MB_ERR_INVALID_CHARS,s.data(),(int)s.size(),nullptr,0);
  if(n<=0)fail(READER_ANNOTATION_EXPORT_ARGUMENT,"path is not valid UTF-8");
  std::wstring w((size_t)n,L'\0');
  MultiByteToWideChar(CP_UTF8,MB_ERR_INVALID_CHARS,s.data(),(int)s.size(),&w[0],n);
  return w;
}
#endif

/* One output: fresh temporary file beside the target, bounded, synced, then an
   atomic rename. Destruction before publication removes the temporary file. */
class sink {
 public:
  sink(const std::string &target,uint64_t budget,const reader_annotation_export_options &options):
    target_(target),budget_(budget),options_(options){buffer_.reserve(kBuffer);}
  ~sink(){discard();}
  sink(const sink &)=delete;
  sink &operator=(const sink &)=delete;
  void open(){
    char id[33];reader_revision_error e{};
    if(reader_revision_new_id(id,&e)!=READER_REV_OK)fail(READER_ANNOTATION_EXPORT_IO,"Temporary name generation failed",(int)e.code);
#ifdef _WIN32
    size_t cut=target_.find_last_of("/\\:");
#else
    size_t cut=target_.find_last_of('/');
#endif
    std::string directory=cut==std::string::npos?std::string():target_.substr(0,cut+1);
    std::string temp=directory+".exr-export-"+id+".tmp";
#ifdef _WIN32
    handle_=CreateFileW(wide(temp).c_str(),GENERIC_WRITE,0,nullptr,CREATE_NEW,FILE_ATTRIBUTE_NORMAL,nullptr);
    if(handle_==INVALID_HANDLE_VALUE)fail(READER_ANNOTATION_EXPORT_IO,"Cannot create the temporary output file",0,0,last_os_error());
#else
    fd_=::open(temp.c_str(),O_WRONLY|O_CREAT|O_EXCL,0666);
    if(fd_<0)fail(READER_ANNOTATION_EXPORT_IO,"Cannot create the temporary output file",0,0,last_os_error());
#endif
    temp_=temp;
  }
  void put(const char *p,size_t n){
    if(!n)return;
    if(n>budget_-total_)fail(READER_ANNOTATION_EXPORT_LIMIT,"Output size budget exceeded");
    total_+=n;
    if(buffer_.size()+n>kBuffer){flush();}
    if(n>=kBuffer){poll();write_all(p,n);}
    else buffer_.append(p,n);
  }
  void put(const std::string &s){put(s.data(),s.size());}
  void put(const char *s){put(s,std::strlen(s));}
  void complete(){
    flush();
#ifdef _WIN32
    if(!FlushFileBuffers(handle_))fail(READER_ANNOTATION_EXPORT_IO,"Cannot flush the output file",0,0,last_os_error());
    HANDLE h=handle_;handle_=INVALID_HANDLE_VALUE;
    if(!CloseHandle(h))fail(READER_ANNOTATION_EXPORT_IO,"Cannot close the output file",0,0,last_os_error());
#else
#ifdef __APPLE__
    if(::fcntl(fd_,F_FULLFSYNC)!=0&&::fsync(fd_)!=0)fail(READER_ANNOTATION_EXPORT_IO,"Cannot flush the output file",0,0,last_os_error());
#else
    if(::fsync(fd_)!=0)fail(READER_ANNOTATION_EXPORT_IO,"Cannot flush the output file",0,0,last_os_error());
#endif
    int f=fd_;fd_=-1;
    if(::close(f)!=0)fail(READER_ANNOTATION_EXPORT_IO,"Cannot close the output file",0,0,last_os_error());
#endif
    completed_=true;
  }
  void publish(){
    if(!completed_||temp_.empty())fail(READER_ANNOTATION_EXPORT_ARGUMENT,"Output is not complete");
#ifdef _WIN32
    if(!MoveFileExW(wide(temp_).c_str(),wide(target_).c_str(),MOVEFILE_REPLACE_EXISTING|MOVEFILE_WRITE_THROUGH))
      fail(READER_ANNOTATION_EXPORT_IO,"Cannot publish the output file",0,0,last_os_error());
    temp_.clear();
#else
    if(::rename(temp_.c_str(),target_.c_str())!=0)fail(READER_ANNOTATION_EXPORT_IO,"Cannot publish the output file",0,0,last_os_error());
    temp_.clear();
    size_t cut=target_.find_last_of('/');
    std::string directory=cut==std::string::npos?std::string("."):cut==0?std::string("/"):target_.substr(0,cut);
    int d=::open(directory.c_str(),O_RDONLY);
    if(d>=0){(void)::fsync(d);::close(d);}  /* best effort: the rename itself already succeeded */
#endif
  }
  void discard() noexcept {
#ifdef _WIN32
    if(handle_!=INVALID_HANDLE_VALUE){CloseHandle(handle_);handle_=INVALID_HANDLE_VALUE;}
    if(!temp_.empty()){try{DeleteFileW(wide(temp_).c_str());}catch(...){}}
#else
    if(fd_>=0){::close(fd_);fd_=-1;}
    if(!temp_.empty())(void)::unlink(temp_.c_str());
#endif
    temp_.clear();
  }
  uint64_t bytes() const{return total_;}
 private:
  void poll(){
    if(options_.cancel&&options_.cancel(options_.cancel_context))fail(READER_ANNOTATION_EXPORT_CANCELLED,"Export was cancelled");
  }
  void flush(){
    poll();
    if(buffer_.empty())return;
    write_all(buffer_.data(),buffer_.size());
    buffer_.clear();
  }
  void write_all(const char *p,size_t n){
#ifdef _WIN32
    while(n){
      DWORD chunk=(DWORD)(n>((size_t)1<<30)?((size_t)1<<30):n),written=0;
      if(!WriteFile(handle_,p,chunk,&written,nullptr)||!written)fail(READER_ANNOTATION_EXPORT_IO,"Cannot write the output file",0,0,last_os_error());
      p+=written;n-=written;
    }
#else
    while(n){
      ssize_t written=::write(fd_,p,n>((size_t)1<<30)?((size_t)1<<30):n);
      if(written<0){if(errno==EINTR)continue;fail(READER_ANNOTATION_EXPORT_IO,"Cannot write the output file",0,0,errno);}
      if(!written)fail(READER_ANNOTATION_EXPORT_IO,"Cannot write the output file",0,0,0);
      p+=written;n-=(size_t)written;
    }
#endif
  }
  std::string target_,temp_,buffer_;
  uint64_t budget_,total_=0;
  const reader_annotation_export_options &options_;
  bool completed_=false;
#ifdef _WIN32
  HANDLE handle_=INVALID_HANDLE_VALUE;
#else
  int fd_=-1;
#endif
};

/* ---- text encodings ---- */
void json_string(std::string &out,const char *p,size_t n){
  static const char hex[]="0123456789abcdef";
  out.push_back('"');
  for(size_t i=0;i<n;i++){
    unsigned char c=(unsigned char)p[i];
    switch(c){
      case '"':out+="\\\"";break;
      case '\\':out+="\\\\";break;
      case '\b':out+="\\b";break;
      case '\f':out+="\\f";break;
      case '\n':out+="\\n";break;
      case '\r':out+="\\r";break;
      case '\t':out+="\\t";break;
      default:
        if(c<0x20){out+="\\u00";out.push_back(hex[c>>4]);out.push_back(hex[c&15]);}
        else out.push_back((char)c);
    }
  }
  out.push_back('"');
}
void json_string(std::string &out,const std::string &s){json_string(out,s.data(),s.size());}
/* Inline Markdown text: every ASCII punctuation byte is backslash-escaped (a
   CommonMark literal), line breaks and controls become one space. */
std::string md_inline(const std::string &s){
  std::string out;
  for(char ch:s){
    unsigned char c=(unsigned char)ch;
    if(c<0x20||c==0x7f)out.push_back(' ');
    else if((c>=0x21&&c<=0x2f)||(c>=0x3a&&c<=0x40)||(c>=0x5b&&c<=0x60)||(c>=0x7b&&c<=0x7e)){out.push_back('\\');out.push_back(ch);}
    else out.push_back(ch);
  }
  return out;
}
/* Block text: LF line ends; controls other than TAB/LF become U+2400 pictures. */
std::string md_text(const char *p,size_t n){
  std::string out;
  for(size_t i=0;i<n;i++){
    unsigned char c=(unsigned char)p[i];
    if(c=='\r'){if(i+1<n&&p[i+1]=='\n')i++;out.push_back('\n');}
    else if(c=='\n'||c=='\t')out.push_back((char)c);
    else if(c<0x20){out.append("\xE2\x90",2);out.push_back((char)(0x80+c));}
    else if(c==0x7f){out.append("\xE2\x90\xA1",3);}
    else out.push_back((char)c);
  }
  return out;
}
void md_fence(std::string &out,const char *p,size_t n){
  std::string body=md_text(p,n);
  size_t run=0,best=0;
  for(char c:body){if(c=='`'){run++;best=std::max(best,run);}else run=0;}
  std::string fence(std::max<size_t>(3,best+1),'`');
  out+=fence;out+="text\n";out+=body;
  if(body.empty()||body.back()!='\n')out.push_back('\n');
  out+=fence;out.push_back('\n');
}
const char *mode_name(reader_rs_mode mode){
  return mode==READER_RS_REFLOW_GLOBAL?"reflow_global":mode==READER_RS_EPUB_CHAPTER?"epub_chapter":mode==READER_RS_FIXED_PAGE?"fixed_page":"unknown";
}
const char *selection_name(reader_selection_kind kind){
  switch(kind){
    case READER_SELECTION_SAFE:return "safe";
    case READER_SELECTION_PENDING_PARENTS:return "pending_parents";
    case READER_SELECTION_CONCURRENT:return "concurrent";
    case READER_SELECTION_BLOCKED_RESTORE:return "blocked_restore";
    default:return "missing";
  }
}

struct head_ref {std::string id,operation,sha;};
struct head_collector {std::vector<head_ref> heads;bool failed=false;};
int collect_head(void *context,const reader_revision_head *head){
  head_collector &c=*(head_collector *)context;
  try{c.heads.push_back(head_ref{head->revision_id,head->operation,head->sha256});}catch(...){c.failed=true;return 1;}
  return 0;
}
struct row_copy {std::string id;reader_revision_selection selection;reader_revision_info info;};
struct page_collector {std::vector<row_copy> rows;bool failed=false;};
int collect_row(void *context,const reader_revision_annotation_row *row){
  page_collector &c=*(page_collector *)context;
  try{c.rows.push_back(row_copy{row->annotation_id,row->selection,row->info});}catch(...){c.failed=true;return 1;}
  return 0;
}
struct wire_copy {
  char *data=nullptr;size_t size=0;
  wire_copy()=default;
  wire_copy(const wire_copy &)=delete;
  wire_copy &operator=(const wire_copy &)=delete;
  ~wire_copy(){reader_revision_bytes_free(data);}
};
struct record_guard {
  reader_rs_record record{};
  ~record_guard(){reader_rs_record_free(&record);}
};

class exporter {
 public:
  exporter(const reader_annotation_export_options &o,sink *json,sink *markdown,reader_annotation_export_stats &stats):
    o_(o),revisions_(o.revisions),json_(json),markdown_(markdown),stats_(stats),book_(o.book_key){}
  void run(){
    derive_title();
    write_headers();
    std::string after;bool have_after=false;
    for(;;){
      poll();
      page_collector page;reader_revision_error e{};
      reader_revision_status s=reader_revision_annotations_page(revisions_,book_.c_str(),have_after?after.c_str():nullptr,1,100,collect_row,&page,&e);
      if(page.failed)fail(READER_ANNOTATION_EXPORT_MEMORY,"Out of memory while reading an annotation page");
      if(s!=READER_REV_OK)fail(s==READER_REV_ARGUMENT?READER_ANNOTATION_EXPORT_ARGUMENT:READER_ANNOTATION_EXPORT_REVISION,e.message,(int)s,0,e.sqlite_code);
      if(page.rows.empty())break;
      for(const row_copy &row:page.rows){poll();entity(row);}
      after=page.rows.back().id;have_after=true;
    }
    write_footers();
  }
 private:
  void poll(){
    if(o_.cancel&&o_.cancel(o_.cancel_context))fail(READER_ANNOTATION_EXPORT_CANCELLED,"Export was cancelled");
  }
  void derive_title(){
    if(o_.book_title){
      size_t n=std::strlen(o_.book_title);
      if(n>READER_ANNOTATION_EXPORT_TITLE_MAX||!well_formed(o_.book_title,n))fail(READER_ANNOTATION_EXPORT_ARGUMENT,"Book title is too long or not well-formed UTF-8");
      title_=o_.book_title;have_title_=true;return;
    }
    /* Best effort: the title of the single safe non-delete book head, if present. */
    head_collector heads;reader_revision_state state{};reader_revision_error e{};
    if(reader_revision_heads(revisions_,"book",book_.c_str(),collect_head,&heads,&state,&e)!=READER_REV_OK||heads.failed)return;
    if(heads.heads.size()!=1||heads.heads[0].operation=="delete"||!state.projection_safe)return;
    char *title=nullptr;
    if(reader_revision_book_title(revisions_,heads.heads[0].id.c_str(),&title,&e)==READER_REV_OK&&title){
      size_t n=std::strlen(title);
      if(n<=READER_ANNOTATION_EXPORT_TITLE_MAX&&well_formed(title,n)){title_=title;have_title_=true;}
    }
    reader_revision_bytes_free(title);
  }
  void write_headers(){
    if(json_){
      std::string line="{\"type\":\"header\",\"format\":\"exreader-annotation-export\",\"format_version\":1,\"module_version\":\"" READER_ANNOTATION_EXPORT_VERSION "\",\"book_key\":";
      json_string(line,book_);line+=",\"book_title\":";
      if(have_title_)json_string(line,title_);else line+="null";
      line+=",\"order\":\"annotation_id_ascending\",\"wire_encoding\":\"json_string_utf8\"}\n";
      json_->put(line);
    }
    if(markdown_){
      std::string text="# "+md_inline(have_title_?title_:book_)+"\n\n";
      text+="- 书籍标识：`"+book_+"`\n";
      text+="- 导出：EXReader 标注导出（格式版本 1）。纯文本，未执行任何 HTML，未联网，未解析书中位置。\n";
      text+="- 说明：偏移只是保存的提示；有多个头的批注逐个列出，没有选择或合并。\n\n";
      markdown_->put(text);
    }
  }
  void write_footers(){
    if(json_){
      std::string line="{\"type\":\"footer\",\"annotations\":"+std::to_string(stats_.annotations)+",\"current\":"+std::to_string(stats_.current)+
        ",\"tombstones\":"+std::to_string(stats_.tombstones)+",\"pending_parents\":"+std::to_string(stats_.pending_parents)+
        ",\"concurrent\":"+std::to_string(stats_.concurrent)+",\"blocked_restore\":"+std::to_string(stats_.blocked_restore)+
        ",\"head_wires\":"+std::to_string(stats_.head_wires)+",\"complete\":true}\n";
      json_->put(line);
    }
    if(markdown_){
      std::string text="---\n\n共 "+std::to_string(stats_.annotations)+" 条标注实体：当前 "+std::to_string(stats_.current)+
        "，已删除 "+std::to_string(stats_.tombstones)+"，冲突 "+std::to_string(stats_.concurrent+stats_.blocked_restore)+
        "，未定位 "+std::to_string(stats_.pending_parents)+"。\n";
      markdown_->put(text);
    }
  }
  void entity(const row_copy &row){
    const std::string key=book_+":"+row.id;
    std::vector<head_ref> heads;reader_revision_state graph{};
    if(row.selection.kind==READER_SELECTION_SAFE){
      heads.push_back(head_ref{row.info.revision_id,row.info.operation,row.info.sha256});
      graph=row.selection.graph;
    }else{
      head_collector collected;reader_revision_error e{};
      reader_revision_status s=reader_revision_heads(revisions_,"annotation",key.c_str(),collect_head,&collected,&graph,&e);
      if(collected.failed)fail(READER_ANNOTATION_EXPORT_MEMORY,"Out of memory while reading heads");
      if(s!=READER_REV_OK)fail(READER_ANNOTATION_EXPORT_REVISION,e.message,(int)s,0,e.sqlite_code);
      heads.swap(collected.heads);
      std::sort(heads.begin(),heads.end(),[](const head_ref &a,const head_ref &b){return a.id<b.id;});
    }
    bool tombstone=row.selection.kind==READER_SELECTION_SAFE&&heads.size()==1&&heads[0].operation=="delete";
    stats_.annotations++;
    switch(row.selection.kind){
      case READER_SELECTION_SAFE:if(tombstone)stats_.tombstones++;else stats_.current++;break;
      case READER_SELECTION_CONCURRENT:stats_.concurrent++;break;
      case READER_SELECTION_BLOCKED_RESTORE:stats_.blocked_restore++;break;
      default:stats_.pending_parents++;break;
    }
    const size_t number=(size_t)stats_.annotations;
    if(json_){
      std::string line="{\"type\":\"annotation\",\"annotation_id\":";
      json_string(line,row.id);line+=",\"entity_key\":";json_string(line,key);
      line+=std::string(",\"selection\":\"")+selection_name(row.selection.kind)+"\",\"tombstone\":"+(tombstone?"true":"false");
      line+=",\"graph\":{\"revisions\":"+std::to_string(graph.revisions)+",\"heads\":"+std::to_string(graph.heads)+
        ",\"missing_parents\":"+std::to_string(graph.missing_parents)+",\"foreign_parents\":"+std::to_string(graph.foreign_parents)+
        ",\"projection_safe\":"+(graph.projection_safe?"true":"false")+",\"deleted\":"+(graph.deleted?"true":"false")+
        ",\"requires_restore\":"+(graph.requires_restore?"true":"false")+"},\"heads\":[";
      json_->put(line);
    }
    if(markdown_)markdown_->put(markdown_entity(number,row,graph,tombstone,heads.size()));
    for(size_t i=0;i<heads.size();i++){
      poll();
      wire_copy wire;reader_revision_info info{};reader_revision_error e{};
      reader_revision_status s=reader_revision_get(revisions_,heads[i].id.c_str(),&wire.data,&wire.size,&info,&e);
      if(s!=READER_REV_OK)fail(READER_ANNOTATION_EXPORT_REVISION,e.message,(int)s,0,e.sqlite_code);
      if(heads[i].sha!=info.sha256||key!=info.entity_key||std::strcmp(info.entity_kind,"annotation")!=0||info.bytes!=wire.size)
        fail(READER_ANNOTATION_EXPORT_REVISION,"A retained head differs from its revision graph");
      if(!well_formed(wire.data,wire.size))fail(READER_ANNOTATION_EXPORT_REVISION,"A retained wire is not well-formed UTF-8");
      stats_.head_wires++;
      if(json_){
        std::string line=i?",":"";
        line+="{\"revision_id\":";json_string(line,heads[i].id);
        line+=",\"operation\":";json_string(line,info.operation);
        line+=",\"sha256\":";json_string(line,info.sha256);
        line+=",\"bytes\":"+std::to_string(wire.size)+",\"wire\":";
        json_string(line,wire.data,wire.size);line+="}";
        json_->put(line);
      }
      if(markdown_){
        record_guard decoded;reader_rs_error re{};
        reader_rs_status ds=reader_rs_decode(revisions_,wire.data,wire.size,&decoded.record,&re);
        if(ds!=READER_RS_OK)fail(READER_ANNOTATION_EXPORT_DECODE,re.message,re.revision_code,(int)ds,0);
        markdown_->put(markdown_head(i+1,heads.size(),heads[i].id,info.operation,decoded.record));
      }
    }
    if(json_)json_->put("]}\n");
  }
  std::string markdown_entity(size_t number,const row_copy &row,const reader_revision_state &graph,bool tombstone,size_t head_count){
    std::string text="## 批注 "+std::to_string(number)+"\n\n- 标注标识：`"+row.id+"`\n- 状态：";
    switch(row.selection.kind){
      case READER_SELECTION_SAFE:
        text+=tombstone?"已删除（墓碑；该批注当前没有位置和正文）":"当前批注（唯一的安全头）";break;
      case READER_SELECTION_CONCURRENT:
        text+="冲突：存在 "+std::to_string(head_count)+" 个并发头，未选择任何一个；以下逐个列出";break;
      case READER_SELECTION_BLOCKED_RESTORE:
        text+="冲突：删除后被隐式恢复，需要显式恢复才能确定当前批注；以下逐个列出";break;
      case READER_SELECTION_PENDING_PARENTS:
        text+="未定位：缺少父修订或父修订不属于本批注，无法确定唯一的当前批注；以下列出已保留的头";break;
      default:
        text+="未定位：没有可用的修订";break;
    }
    text+="\n- 修订图：修订 "+std::to_string(graph.revisions)+"，头 "+std::to_string(graph.heads)+"，缺失父修订 "+
      std::to_string(graph.missing_parents)+"，外来父修订 "+std::to_string(graph.foreign_parents)+"\n\n";
    return text;
  }
  std::string markdown_head(size_t index,size_t count,const std::string &id,const char *operation,const reader_rs_record &r){
    std::string text="### 头 "+std::to_string(index)+"/"+std::to_string(count)+"：修订 `"+id+"`（"+md_inline(operation)+"）\n\n";
    if(!r.has_location){
      text+="- 该头是删除记录，没有位置和正文。\n\n";
      return text;
    }
    text+=std::string("- 位置模式：")+mode_name(r.mode)+"；锚点版本："+std::to_string(r.anchor_version)+"\n";
    if(r.mode==READER_RS_EPUB_CHAPTER){
      text+="- 书内部分路径："+md_inline(r.part_path?r.part_path:"")+"\n";
      if(r.anchor_version>=2)text+="- 部分序号："+std::to_string(r.part)+"\n";
    }
    if(r.mode==READER_RS_FIXED_PAGE)
      text+="- 页面标识："+md_inline(r.page_id?r.page_id:"")+"；页索引（从0起）："+std::to_string(r.page)+"\n";
    if(r.mode==READER_RS_REFLOW_GLOBAL&&r.anchor_version>=2)
      text+="- 章节范围："+(r.chapter?md_inline(r.chapter):std::string("无"))+"\n";
    text+="- 偏移提示（仅供参考，未用于定位）："+std::to_string(r.start)+"–"+std::to_string(r.end)+"\n\n";
    if(r.exact_size){text+="引文：\n\n";md_fence(text,r.exact,r.exact_size);}
    else text+="引文：（无，位置点或书签）\n";
    if(r.prefix_size){text+="\n前文：\n\n";md_fence(text,r.prefix,r.prefix_size);}
    if(r.suffix_size){text+="\n后文：\n\n";md_fence(text,r.suffix,r.suffix_size);}
    if(r.note_text&&*r.note_text){text+="\n批注：\n\n";md_fence(text,r.note_text,std::strlen(r.note_text));}
    else text+="\n批注：（空）\n";
    text+="\n";
    return text;
  }
  const reader_annotation_export_options &o_;
  reader_revisions *revisions_;
  sink *json_,*markdown_;
  reader_annotation_export_stats &stats_;
  std::string book_,title_;
  bool have_title_=false;
};

void validate(const reader_annotation_export_options *o){
  if(!o||o->struct_size<sizeof(*o)||!o->revisions||!o->book_key)fail(READER_ANNOTATION_EXPORT_ARGUMENT,"Missing export options, revision store or book key");
  size_t n=std::strlen(o->book_key);
  if(!n||n>73)fail(READER_ANNOTATION_EXPORT_ARGUMENT,"Book key length is outside 1..73");
  for(size_t i=0;i<n;i++){
    unsigned char c=(unsigned char)o->book_key[i];
    if(!((c>='0'&&c<='9')||(c>='a'&&c<='z')||(c>='A'&&c<='Z')||c==':'||c=='.'||c=='_'||c=='-'))fail(READER_ANNOTATION_EXPORT_ARGUMENT,"Book key contains an unsupported character");
  }
  if(!o->jsonl_path&&!o->markdown_path)fail(READER_ANNOTATION_EXPORT_ARGUMENT,"At least one output path is required");
  if(o->jsonl_path)check_path(o->jsonl_path,"JSONL");
  if(o->markdown_path)check_path(o->markdown_path,"Markdown");
  if(o->jsonl_path&&o->markdown_path&&std::strcmp(o->jsonl_path,o->markdown_path)==0)fail(READER_ANNOTATION_EXPORT_ARGUMENT,"Both outputs name the same path");
  if(o->max_output_bytes>READER_ANNOTATION_EXPORT_HARD_MAX_BYTES)fail(READER_ANNOTATION_EXPORT_ARGUMENT,"Output budget exceeds the 1 GiB maximum");
}
void export_book(const reader_annotation_export_options &o,reader_annotation_export_stats &stats){
  uint64_t budget=o.max_output_bytes?o.max_output_bytes:READER_ANNOTATION_EXPORT_DEFAULT_MAX_BYTES;
  std::vector<sink *> owned;
  struct releaser {std::vector<sink *> &v;~releaser(){for(sink *s:v)delete s;}} release{owned};
  sink *json=nullptr,*markdown=nullptr;
  if(o.jsonl_path){json=new sink(o.jsonl_path,budget,o);owned.push_back(json);json->open();}
  if(o.markdown_path){markdown=new sink(o.markdown_path,budget,o);owned.push_back(markdown);markdown->open();}
  exporter(o,json,markdown,stats).run();
  if(json)json->complete();
  if(markdown)markdown->complete();
  stats.jsonl_bytes=json?json->bytes():0;
  stats.markdown_bytes=markdown?markdown->bytes():0;
  if(json){json->publish();stats.jsonl_published=1;}
  if(markdown){markdown->publish();stats.markdown_published=1;}
}
}  // namespace

extern "C" reader_annotation_export_status reader_annotation_export_run(const reader_annotation_export_options *options,
  reader_annotation_export_stats *stats,reader_annotation_export_error *error){
  if(stats)std::memset(stats,0,sizeof(*stats));
  if(error)std::memset(error,0,sizeof(*error));
  reader_annotation_export_stats local{};
  export_status code=READER_ANNOTATION_EXPORT_OK;int revision_code=0,rs_code=0,os_error=0;std::string message;
  try{
    validate(options);
    export_book(*options,local);
  }catch(const failure &f){
    code=f.code;revision_code=f.revision_code;rs_code=f.rs_code;os_error=f.os_error;message=f.message;
  }catch(const std::bad_alloc &){
    code=READER_ANNOTATION_EXPORT_MEMORY;message="Out of memory";
  }catch(const std::exception &e){
    code=READER_ANNOTATION_EXPORT_MEMORY;message=e.what();
  }catch(...){
    code=READER_ANNOTATION_EXPORT_MEMORY;message="Unexpected failure";
  }
  if(stats)*stats=local;
  if(error&&code!=READER_ANNOTATION_EXPORT_OK){
    error->code=code;error->revision_code=revision_code;error->rs_code=rs_code;error->os_error=os_error;
    size_t keep=std::min(message.size(),sizeof(error->message)-1);
    std::memcpy(error->message,message.data(),keep);
  }
  return code;
}
