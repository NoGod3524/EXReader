/* SPDX-License-Identifier: MIT */
/* Host-only presentation classes. The source book is never written. ZIP entry
   payloads, XML nodes/text, and CFI routes are retained; the SDK still performs
   bounded chapter layout. Expat and miniz are already SDK dependencies. */
#include <exreader.h>
#include <algorithm>
#include <cstring>
#include <memory>
#include <string>
#include <vector>
#include <cstdint>

/* These two private SDK libraries expose their stable C entry points, but do
   not install headers. No private SDK structs are accessed. */
extern "C" {
void *XML_ParserCreate(const char *);
void XML_ParserFree(void *);
void XML_SetUserData(void *,void *);
void XML_SetElementHandler(void *,void (*)(void *,const char *,const char **),void (*)(void *,const char *));
void XML_SetCharacterDataHandler(void *,void (*)(void *,const char *,int));
long XML_GetCurrentByteIndex(void *);
int XML_Parse(void *,const char *,int,int);
size_t tinfl_decompress_mem_to_mem(void *,size_t,const void *,size_t,int);
}

static bool cjk(const char *s,size_t n) {
  for(size_t i=0;i<n;) {
    unsigned c=(unsigned char)s[i++],more=0;
    if(c>=0xf0) {c&=7;more=3;} else if(c>=0xe0) {c&=15;more=2;} else if(c>=0xc0) {c&=31;more=1;}
    while(more-- && i<n) c=(c<<6)|((unsigned char)s[i++]&63);
    if((c>=0x2e80 && c<=0x9fff) || (c>=0xac00 && c<=0xd7af) ||
       (c>=0xf900 && c<=0xfaff) || (c>=0xff66 && c<=0xff9f) ||
       (c>=0x20000 && c<=0x323af)) return true;
  }
  return false;
}
struct element {size_t offset;std::string name;bool cjk=false,block=false;unsigned spaces=0;bool prefix=true;};
struct edit {size_t offset;std::string text;};
struct xml_classes {
  void *parser=nullptr;
  std::string source;
  std::vector<element> stack;
  std::vector<edit> edits;
  bool has_cjk=false;
};
static void start(void *context,const char *name,const char **) {
  auto &x=*(xml_classes *)context;
  const char *local=std::strrchr(name,':');if(local) name=local+1;
  x.stack.push_back({(size_t)XML_GetCurrentByteIndex(x.parser),name,false,false});
}
static void characters(void *context,const char *text,int length) {
  auto &x=*(xml_classes *)context;
  if(!x.stack.empty() && cjk(text,(size_t)length)) {x.stack.back().cjk=true;x.has_cjk=true;}
  /* An authored U+3000 prefix already occupies ems. Keep its source offsets
     and subtract that width from CSS indent, rather than double-indenting. */
  for(auto &e:x.stack) if(e.prefix) {
    for(int i=0;i<length && e.prefix;) {
      if((unsigned char)text[i]<=32) {i++;continue;}
      if(i+2<length && (unsigned char)text[i]==0xe3 && (unsigned char)text[i+1]==0x80 && (unsigned char)text[i+2]==0x80) {e.spaces++;i+=3;}
      else e.prefix=false;
    }
  }
}
static void end(void *context,const char *) {
  auto &x=*(xml_classes *)context;
  auto e=x.stack.back();x.stack.pop_back();
  bool paragraph=e.name=="p" || (e.name=="div" && !e.block);
  bool block=paragraph || e.name=="li" || e.name=="blockquote" ||
    (e.name.size()==2 && e.name[0]=='h' && e.name[1]>='1' && e.name[1]<='6');
  if(!x.stack.empty()) {x.stack.back().cjk|=e.cjk;x.stack.back().block|=block || e.block;}
  if(!block) return;
  std::string value=e.cjk ? " exr-shell-cjk" : " exr-shell-latin";
  if(paragraph) {
    value+=" exr-shell-paragraph";
    if(e.cjk && e.spaces && e.spaces<=16) value+=" exr-shell-indent-"+std::to_string(e.spaces);
  }
  size_t i=e.offset+1;
  while(i<x.source.size() && x.source[i]!=' ' && x.source[i]!='\t' && x.source[i]!='\r' && x.source[i]!='\n' && x.source[i]!='>' && x.source[i]!='/') i++;
  size_t insert=i;
  while(i<x.source.size()) {
    while(i<x.source.size() && (unsigned char)x.source[i]<=32) i++;
    if(i==x.source.size() || x.source[i]=='/' || x.source[i]=='>') break;
    size_t a=i;while(i<x.source.size() && x.source[i]!='=' && (unsigned char)x.source[i]>32) i++;
    std::string attr=x.source.substr(a,i-a);
    while(i<x.source.size() && x.source[i]!='=') i++;
    i++;while(i<x.source.size() && (unsigned char)x.source[i]<=32) i++;
    if(i==x.source.size()) break;
    char quote=x.source[i++];while(i<x.source.size() && x.source[i]!=quote) i++;
    if(attr=="class") {x.edits.push_back({i,value});return;} i++;
  }
  x.edits.push_back({insert," class=\""+value.substr(1)+"\""});
}
static bool classify(std::vector<unsigned char> &bytes) {
  xml_classes x;x.source.assign((const char *)bytes.data(),bytes.size());
  x.parser=XML_ParserCreate(nullptr);if(!x.parser) return false;
  XML_SetUserData(x.parser,&x);XML_SetElementHandler(x.parser,start,end);XML_SetCharacterDataHandler(x.parser,characters);
  bool valid=XML_Parse(x.parser,x.source.data(),(int)x.source.size(),1)!=0;
  XML_ParserFree(x.parser);
  if(!valid || !x.has_cjk || x.edits.empty()) return false;
  std::sort(x.edits.begin(),x.edits.end(),[](const edit &a,const edit &b){return a.offset>b.offset;});
  for(const auto &e:x.edits) x.source.insert(e.offset,e.text);
  bytes.assign(x.source.begin(),x.source.end());return true;
}
static uint16_t u16(const unsigned char *p) {return (uint16_t)(p[0]|p[1]<<8);}
static uint32_t u32(const unsigned char *p) {return (uint32_t)u16(p)|((uint32_t)u16(p+2)<<16);}
static void put(std::vector<unsigned char> &b,size_t at,uint32_t value,int n=4) {
  for(int i=0;i<n;i++) b.at(at+i)=(unsigned char)(value>>(i*8));
}
static uint32_t crc(const std::vector<unsigned char> &b) {
  uint32_t v=0xffffffff;
  for(unsigned char c:b) {v^=c;for(int bit=0;bit<8;bit++) v=(v>>1)^(0xedb88320u&(0u-(v&1)));}
  return ~v;
}
static size_t read_memory(void *context,uint64_t offset,void *data,size_t size) {
  auto &b=*(std::vector<unsigned char> *)context;
  if(offset>=b.size()) return 0;
  size=std::min(size,b.size()-(size_t)offset);std::memcpy(data,b.data()+(size_t)offset,size);return size;
}
static void release_memory(void *context) {delete (std::vector<unsigned char> *)context;}

/* Older library entries use a resident document rather than an indexed EPUB.
   Copy through the public construction API; never mutate a borrowed SDK tree. */
extern "C" int shell_style_document(exr_document **document) {
  try {
    size_t size=0,count=0,chapters_count=0,resources_count=0;
    const char *text=exr_document_text(*document,&size);
    if(!text || !cjk(text,size)) return 1;
    const auto *nodes=exr_document_nodes(*document,&count);
    const auto *chapters=exr_document_chapters(*document,&chapters_count);
    const auto *resources=exr_document_resources(*document,&resources_count);
    std::vector<exr_node_input> input(count);
    std::vector<std::vector<exr_attribute>> attributes(count);
    std::vector<std::string> classes(count);
    for(size_t i=0;i<count;i++) {
      const auto &n=nodes[i];input[i]={n.kind,n.parent,n.name,n.text,n.attributes,n.attribute_count};
      bool paragraph=n.kind==EXR_NODE_PARAGRAPH;
      if(!paragraph && n.kind!=EXR_NODE_HEADING) continue;
      if(n.start==SIZE_MAX || n.end>size || n.end<n.start) continue;
      bool chinese=cjk(text+n.start,n.end-n.start);
      const char *original=exr_node_attribute(&n,"class");
      classes[i]=(original ? original : "")+std::string(chinese ? " exr-shell-cjk" : " exr-shell-latin");
      if(paragraph) {
        classes[i]+=" exr-shell-paragraph";
        size_t at=n.start;unsigned spaces=0;
        while(at+3<=n.end && !std::memcmp(text+at,"\xe3\x80\x80",3)) {spaces++;at+=3;}
        if(chinese && spaces && spaces<=16) classes[i]+=" exr-shell-indent-"+std::to_string(spaces);
      }
      for(size_t a=0;a<n.attribute_count;a++) if(std::strcmp(n.attributes[a].name,"class")) attributes[i].push_back(n.attributes[a]);
      attributes[i].push_back({"class",classes[i].c_str()});input[i].attributes=attributes[i].data();input[i].attribute_count=attributes[i].size();
    }
    std::vector<exr_chapter_input> cs(chapters_count);
    for(size_t i=0;i<chapters_count;i++) cs[i]={chapters[i].id,chapters[i].path,chapters[i].root,chapters[i].in_spine};
    std::vector<exr_resource_input> rs(resources_count);
    std::vector<std::unique_ptr<void,decltype(&exr_free)>> owned;
    exr_error error={};
    for(size_t i=0;i<resources_count;i++) {
      void *data=nullptr;size_t bytes=0;
      if(exr_document_resource(*document,i,&data,&bytes,&error)!=EXR_OK) return 0;
      owned.emplace_back(data,exr_free);rs[i]={resources[i],data,bytes};
    }
    exr_document_input all={exr_document_title(*document),input.data(),count,cs.data(),cs.size(),rs.data(),rs.size()};
    exr_document *styled=nullptr;
    if(exr_document_create(&all,&styled,&error)!=EXR_OK) return 0;
    exr_document_free(*document);*document=styled;return 1;
  } catch(...) {return 0;}
}

extern "C" int shell_epub_source(exr_source *source) {
  /* Match the host's existing 96MiB input ceiling; reject malformed extents. */
  if(source->size<22 || source->size>96u*1024*1024) return 0;
  try {
    std::vector<unsigned char> input((size_t)source->size);
    for(size_t at=0;at<input.size();) {
      size_t n=source->read_at(source->context,at,input.data()+at,input.size()-at);
      if(!n || n>input.size()-at) return 0;
      at+=n;
    }
    size_t end=input.size()-22;
    while(end && (u32(input.data()+end)!=0x06054b50 || end+22+u16(input.data()+end+20)!=input.size())) end--;
    if(u32(input.data()+end)!=0x06054b50) return 0;
    size_t at=u32(input.data()+end+16),count=u16(input.data()+end+10);
    std::vector<unsigned char> output,directory;bool changed=false;
    for(size_t entry=0;entry<count;entry++) {
      if(at+46>input.size() || u32(input.data()+at)!=0x02014b50) return 0;
      const auto *c=input.data()+at;
      size_t cn=46+u16(c+28)+u16(c+30)+u16(c+32),local=u32(c+42);
      if(cn>input.size()-at || local+30>input.size() || u32(input.data()+local)!=0x04034b50) return 0;
      size_t header=30+u16(input.data()+local+26)+u16(input.data()+local+28),packed=u32(c+20),size=u32(c+24);
      if(header>input.size()-local || packed>input.size()-local-header) return 0;
      std::string name((const char *)c+46,u16(c+28));
      bool xml=name.size()>=5 && (name.substr(name.size()-5)==".html" || (name.size()>=6 && name.substr(name.size()-6)==".xhtml"));
      std::vector<unsigned char> content;bool rewrite=false;
      if(xml && size<=96u*1024*1024 && !(u16(c+8)&1)) {
        content.resize(size);const void *data=input.data()+local+header;
        if(u16(c+10)==0 && packed==size) std::memcpy(content.data(),data,size);
        else if(u16(c+10)!=8 || tinfl_decompress_mem_to_mem(content.data(),size,data,packed,0)!=size) return 0;
        rewrite=classify(content);
      }
      size_t dest=output.size(),dc=directory.size();
      directory.insert(directory.end(),c,c+cn);put(directory,dc+42,(uint32_t)dest);
      if(rewrite) {
        changed=true;
        output.insert(output.end(),input.begin()+local,input.begin()+local+header);
        put(output,dest+6,u16(c+8)&~8u,2);put(output,dest+8,0,2);
        put(output,dest+14,crc(content));put(output,dest+18,(uint32_t)content.size());put(output,dest+22,(uint32_t)content.size());
        put(directory,dc+8,u16(c+8)&~8u,2);put(directory,dc+10,0,2);
        put(directory,dc+16,crc(content));put(directory,dc+20,(uint32_t)content.size());put(directory,dc+24,(uint32_t)content.size());
        output.insert(output.end(),content.begin(),content.end());
      } else {
        output.insert(output.end(),input.begin()+local,input.begin()+local+header+packed);
        /* Central-directory sizes replace an optional trailing descriptor. */
        put(output,dest+6,u16(c+8)&~8u,2);put(directory,dc+8,u16(c+8)&~8u,2);
        put(output,dest+14,u32(c+16));put(output,dest+18,u32(c+20));put(output,dest+22,u32(c+24));
      }
      at+=cn;
    }
    if(!changed) return 1;
    size_t central=output.size();output.insert(output.end(),directory.begin(),directory.end());
    size_t e=output.size();output.insert(output.end(),input.begin()+end,input.end());
    put(output,e+12,(uint32_t)directory.size());put(output,e+16,(uint32_t)central);
    auto memory=std::make_unique<std::vector<unsigned char>>(std::move(output));
    source->release(source->context);source->size=memory->size();source->context=memory.release();
    source->read_at=read_memory;source->release=release_memory;return 1;
  } catch(...) {return 0;}
}
