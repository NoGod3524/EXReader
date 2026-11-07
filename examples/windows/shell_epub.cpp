/* SPDX-License-Identifier: MIT */
/* Host-only presentation copy. The source book is never written. Authored IDs
   stay on their original elements; hard-wrapped CJK text gains paragraph and
   heading blocks. The SDK still performs bounded chapter layout. Expat and
   miniz are already SDK dependencies. */
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
/* Plain-text conversions (Project Gutenberg CJK EPUBs among them) keep a whole
   chapter in one hard-wrapped <p>: interior paragraphs start with "\n　　",
   chapter headings (第…回) are a bare source line, and rows of dashes stand in
   for rules. Each source line is classified so the presentation copy can give
   headings and paragraphs their own blocks. Only character data that is
   byte-identical to the source and directly inside the block is split. */
enum line_kind {LINE_BLANK,LINE_TEXT,LINE_PARAGRAPH,LINE_HEADING,LINE_RULE};
struct source_line {size_t start,content,end;unsigned lead;line_kind kind;bool exact,bare;size_t bytes;};
/* Some SDK builds keep U+3000 as a full-width glyph, newer ones collapse it as
   white space. An authored U+3000 indent only counts when it survives. */
static bool keeps_ideographic_space() {
  static int kept=-1;
  if(kept<0) {
    const exr_node_input nodes[]={
      {EXR_NODE_DOCUMENT,SIZE_MAX,nullptr,nullptr,nullptr,0},{EXR_NODE_CHAPTER,0,nullptr,nullptr,nullptr,0},
      {EXR_NODE_PARAGRAPH,1,"p",nullptr,nullptr,0},{EXR_NODE_TEXT,2,nullptr,"\xe3\x80\x80x",nullptr,0}};
    const exr_chapter_input chapter={"c","c.xhtml",1,1};
    const exr_document_input input={"probe",nodes,4,&chapter,1,nullptr,0};
    exr_document *doc=nullptr;exr_error e={};size_t n=0;
    kept=exr_document_create(&input,&doc,&e)==EXR_OK && !std::strncmp(exr_document_text(doc,&n),"\xe3\x80\x80",3);
    exr_document_free(doc);
  }
  return kept==1;
}
static std::string indent_class(unsigned spaces) {
  return spaces && spaces<=16 && keeps_ideographic_space() ? " exr-shell-indent-"+std::to_string(spaces) : "";
}
struct element {
  size_t offset;std::string name;bool cjk=false,block=false;unsigned spaces=0;bool prefix=true;
  bool mixed=false,open=false,exact=true,text=false;size_t line_start=0,expect=0;std::string line;
  std::vector<source_line> lines;
};
struct edit {size_t offset;std::string text;};
/* A heading block that may move to the next spine document: the edit holding
   its class, its exact source text and its presentation classes. */
struct heading_block {size_t edit;std::string markup,kind;};
struct xml_classes {
  void *parser=nullptr;
  std::string source;
  std::vector<element> stack;
  std::vector<edit> edits;
  bool has_cjk=false,pending_subtitle=false,leading=true;
  std::vector<heading_block> lead,trail; /* headings before / after all other content */
  size_t body=SIZE_MAX;                   /* first byte inside <body> */
};
/* Any visible block other than a carried heading ends both heading groups. */
static void content_seen(xml_classes &x) {x.trail.clear();x.leading=false;}
static uint32_t next_scalar(const std::string &s,size_t &i) {
  unsigned c=(unsigned char)s[i++],more=0;
  if(c>=0xf0) {c&=7;more=3;} else if(c>=0xe0) {c&=15;more=2;} else if(c>=0xc0) {c&=31;more=1;}
  while(more-- && i<s.size()) c=(c<<6)|((unsigned char)s[i++]&63);
  return c;
}
static bool ideographic_space(const std::string &s,size_t i) {return !s.compare(i,3,"\xe3\x80\x80");}
static source_line close_line(element &e,size_t end) {
  source_line l={e.line_start,e.line_start,end,0,LINE_BLANK,e.exact,false,0};
  const std::string &s=e.line;size_t i=0;
  while(i<s.size()) {
    if((unsigned char)s[i]<=32) {i++;continue;}
    if(ideographic_space(s,i)) {l.lead++;i+=3;continue;}
    break;
  }
  l.content=e.line_start+i;
  size_t last=s.size();while(last>i && (unsigned char)s[last-1]<=32) last--;
  l.bytes=last-i;
  e.open=false;std::string text=s.substr(0,last);e.line.clear();
  if(i==last) return l;
  /* 第 + numerals + 回/章/節/节/卷, then the end of the line or a space. */
  if(!text.compare(i,3,"\xe7\xac\xac")) {
    static const char32_t numerals[]=U"〇零一二三四五六七八九十百千两兩0123456789０１２３４５６７８９";
    size_t at=i+3,digits=0;
    while(at<last) {
      size_t probe=at;uint32_t c=next_scalar(text,probe);bool numeral=false;
      for(const char32_t *n=numerals;*n;n++) if((uint32_t)*n==c) numeral=true;
      if(!numeral) break;
      digits++;at=probe;
    }
    size_t probe=at;uint32_t marker=at<last ? next_scalar(text,probe) : 0;
    if(digits && digits<=6 && (marker==0x56de || marker==0x7ae0 || marker==0x7bc0 || marker==0x8282 || marker==0x5377) &&
       (probe==last || (unsigned char)text[probe]<=32 || ideographic_space(text,probe)) && last-i<=180) {
      l.kind=LINE_HEADING;l.bare=true;
      for(size_t k=probe;k<last;) {
        if((unsigned char)text[k]<=32) {k++;continue;}
        if(ideographic_space(text,k)) {k+=3;continue;}
        l.bare=false;break;
      }
      return l;
    }
  }
  size_t rule=0;bool other=false;
  for(size_t k=i;k<last && !other;) {
    uint32_t c=next_scalar(text,k);
    if(c=='-' || c=='_' || c==0x2014 || c==0x2015 || c==0x2500 || c==0x2501 || c==0xff0d || c==0xff3f) rule++;
    else if(c>32) other=true;
  }
  l.kind=!other && rule>=4 ? LINE_RULE : l.lead ? LINE_PARAGRAPH : LINE_TEXT;
  return l;
}
static bool splittable(const element &e) {
  return e.name=="p" || (e.name=="div" && !e.block);
}
static bool heading_element(const element &e) {
  return e.name.size()==2 && e.name[0]=='h' && e.name[1]>='1' && e.name[1]<='6';
}
static void start(void *context,const char *name,const char **) {
  auto &x=*(xml_classes *)context;
  const char *local=std::strrchr(name,':');if(local) name=local+1;
  if(!x.stack.empty()) x.stack.back().mixed=true;
  element e;e.offset=(size_t)XML_GetCurrentByteIndex(x.parser);e.name=name;
  if(e.name=="body" && x.body==SIZE_MAX) {
    size_t i=e.offset;char quote=0;
    for(;i<x.source.size();i++) {
      if(quote) {if(x.source[i]==quote) quote=0;}
      else if(x.source[i]=='"' || x.source[i]=='\'') quote=x.source[i];
      else if(x.source[i]=='>') break;
    }
    if(i<x.source.size() && x.source[i-1]!='/') x.body=i+1;
  }
  x.stack.push_back(std::move(e));
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
  if(x.stack.empty()) return;
  auto &e=x.stack.back();
  for(int i=0;i<length && !e.text;i++) if((unsigned char)text[i]>32) e.text=true;
  if(e.mixed || (!splittable(e) && !heading_element(e))) return;
  size_t offset=(size_t)XML_GetCurrentByteIndex(x.parser);
  bool exact=offset<=x.source.size() && !x.source.compare(offset,(size_t)length,text,(size_t)length);
  for(int i=0;i<length;) {
    if(!e.open) {e.open=true;e.exact=exact;e.line_start=offset+i;}
    else if(e.expect!=offset+i || !exact) e.exact=false;
    int j=i;while(j<length && text[j]!='\n') j++;
    e.line.append(text+i,(size_t)(j-i));e.expect=offset+j;
    if(e.line.size()>4096) e.exact=false;
    if(j<length) {e.lines.push_back(close_line(e,offset+j));j++;}
    i=j;
  }
}
static void hide(xml_classes &x,size_t from,size_t to) {
  if(to<=from) return;
  x.edits.push_back({from,"<span class=\"exr-shell-hide\">"});x.edits.push_back({to,"</span>"});
}
/* Splits one hard-wrapped block; returns the classes of the element itself. */
static std::string split_lines(xml_classes &x,element &e) {
  struct block {size_t first;unsigned lead;bool heading,bare;};
  std::vector<block> blocks;
  bool after_heading=false;
  for(size_t i=0;i<e.lines.size();i++) {
    const auto &l=e.lines[i];
    if(l.kind==LINE_BLANK || l.kind==LINE_RULE) continue;
    bool begin=blocks.empty() || ((l.kind==LINE_HEADING || l.kind==LINE_PARAGRAPH || after_heading) && l.exact);
    if(begin) blocks.push_back({i,l.lead,l.kind==LINE_HEADING,l.bare});
    after_heading=l.kind==LINE_HEADING;
  }
  for(const auto &l:e.lines) if(l.kind==LINE_RULE && l.exact) hide(x,l.start,l.end);
  std::string own=" exr-shell-paragraph";
  for(size_t b=0;b<blocks.size();b++) {
    const auto &k=blocks[b];const auto &l=e.lines[k.first];
    size_t visible=0,stop=b+1<blocks.size() ? blocks[b+1].first : e.lines.size();
    for(size_t i=k.first;i<stop;i++) if(e.lines[i].kind!=LINE_BLANK && e.lines[i].kind!=LINE_RULE) visible++;
    bool subtitle=!k.heading && x.pending_subtitle && visible==1 && l.bytes<=150;
    std::string kind;
    if(k.heading) kind=k.bare ? " exr-shell-chapter exr-shell-chapter-bare" : " exr-shell-chapter";
    else if(subtitle) kind=" exr-shell-chapter-sub";
    else {
      kind=" exr-shell-paragraph";
      kind+=indent_class(k.lead);
    }
    if(!b) own=kind;
    else x.edits.push_back({l.start,"</"+e.name+"><"+e.name+" class=\"exr-shell-cjk"+kind+"\">"});
    size_t edit_index=b ? x.edits.size()-1 : SIZE_MAX; /* the element's own class edit comes later */
    /* Headings are centred: authored leading spaces would push them off-centre.
       Pushed after the split so the span opens inside the new block. */
    if((k.heading || subtitle) && l.exact && l.content>l.start) hide(x,l.start,l.content);
    /* A U+3000 between 回次 and the couplet halves is a separator, not an
       indent; EM SPACE (same byte length, same 1em) keeps it on every SDK. */
    if((k.heading || subtitle) && l.exact)
      for(size_t at=l.content;at+3<=l.end;at++)
        if(!x.source.compare(at,3,"\xe3\x80\x80")) {x.source.replace(at,3,"\xe2\x80\x83");at+=2;}
    x.pending_subtitle=k.heading && k.bare;
    if((k.heading || subtitle) && l.exact) {
      heading_block h={edit_index,x.source.substr(l.content,l.bytes),kind};
      if(x.leading) x.lead.push_back(h);
      x.trail.push_back(h);
    } else content_seen(x);
  }
  return own;
}
static void end(void *context,const char *) {
  auto &x=*(xml_classes *)context;
  auto e=std::move(x.stack.back());x.stack.pop_back();
  if(e.open) e.lines.push_back(close_line(e,e.expect));
  bool paragraph=splittable(e);
  bool heading=heading_element(e);
  bool block=paragraph || e.name=="li" || e.name=="blockquote" || heading;
  if(!x.stack.empty()) {
    auto &parent=x.stack.back();
    parent.cjk|=e.cjk;parent.block|=block || e.block;
    if(!block) parent.text|=e.text;
  }
  if(!block) return;
  std::string value=e.cjk ? " exr-shell-cjk" : " exr-shell-latin";
  bool rule=paragraph && !e.mixed,visible=false;
  for(const auto &l:e.lines) if(l.kind!=LINE_BLANK) {visible=true;rule&=l.kind==LINE_RULE;}
  if(rule && visible) value+=" exr-shell-hide"; /* a paragraph of dashes only */
  else if(paragraph && e.cjk && !e.mixed) value+=split_lines(x,e);
  else {
    if(e.text) content_seen(x);
    if(paragraph) {
      value+=" exr-shell-paragraph";
      if(e.cjk) value+=indent_class(e.spaces);
      if(e.cjk) x.pending_subtitle=false;
    } else if(heading && e.cjk) {
      value+=" exr-shell-heading";
      for(const auto &l:e.lines) if(l.kind!=LINE_BLANK) {
        if(l.kind==LINE_HEADING) value+=" exr-shell-chapter";
        break;
      }
      x.pending_subtitle=false;
    }
  }
  size_t i=e.offset+1;
  while(i<x.source.size() && x.source[i]!=' ' && x.source[i]!='\t' && x.source[i]!='\r' && x.source[i]!='\n' && x.source[i]!='>' && x.source[i]!='/') i++;
  size_t insert=i;bool existing_class=false;
  while(i<x.source.size()) {
    while(i<x.source.size() && (unsigned char)x.source[i]<=32) i++;
    if(i==x.source.size() || x.source[i]=='/' || x.source[i]=='>') break;
    size_t a=i;while(i<x.source.size() && x.source[i]!='=' && (unsigned char)x.source[i]>32) i++;
    std::string attr=x.source.substr(a,i-a);
    while(i<x.source.size() && x.source[i]!='=') i++;
    i++;while(i<x.source.size() && (unsigned char)x.source[i]<=32) i++;
    if(i==x.source.size()) break;
    char quote=x.source[i++];while(i<x.source.size() && x.source[i]!=quote) i++;
    if(attr=="class") {insert=i;existing_class=true;break;} i++;
  }
  x.edits.push_back({insert,existing_class ? value : " class=\""+value.substr(1)+"\""});
  for(auto *group:{&x.lead,&x.trail}) for(auto &h:*group) if(h.edit==SIZE_MAX) h.edit=x.edits.size()-1;
}
/* Parse only; edits are applied after neighbouring spine documents are known. */
static bool parse_classes(const std::vector<unsigned char> &bytes,xml_classes &x) {
  x.source.assign((const char *)bytes.data(),bytes.size());
  x.parser=XML_ParserCreate(nullptr);if(!x.parser) return false;
  XML_SetUserData(x.parser,&x);XML_SetElementHandler(x.parser,start,end);XML_SetCharacterDataHandler(x.parser,characters);
  bool valid=XML_Parse(x.parser,x.source.data(),(int)x.source.size(),1)!=0;
  XML_ParserFree(x.parser);x.parser=nullptr;
  return valid && x.has_cjk && !x.edits.empty();
}
static void apply_classes(xml_classes &x,std::vector<unsigned char> &bytes) {
  /* Equal offsets only occur where one hidden range closes and the next opens
     (or a split follows): the earlier-pushed text must come first. */
  std::stable_sort(x.edits.begin(),x.edits.end(),[](const edit &a,const edit &b){return a.offset>b.offset;});
  for(size_t i=0;i<x.edits.size();) {
    size_t j=i;std::string text;
    while(j<x.edits.size() && x.edits[j].offset==x.edits[i].offset) text+=x.edits[j++].text;
    x.source.insert(x.edits[i].offset,text);i=j;
  }
  bytes.assign(x.source.begin(),x.source.end());
}
/* Plain-text splits often end one spine document with the next chapter's
   heading while its text starts the next document; each document is paged on
   its own, so the heading would stand alone on a page. Hide it there and give
   it to the next document, unless that document already opens with it. */
static void carry_heading(xml_classes &from,xml_classes &to) {
  if(from.trail.empty() || from.leading || to.body==SIZE_MAX) return;
  auto key=[](const std::string &s) {
    for(size_t i=3;i+3<=s.size();i+=3)
      if(!s.compare(i,3,"回") || !s.compare(i,3,"章") || !s.compare(i,3,"節") ||
         !s.compare(i,3,"节") || !s.compare(i,3,"卷")) return s.substr(0,i+3);
    return s;
  };
  bool duplicate=!to.lead.empty() && key(from.trail.front().markup)==key(to.lead.front().markup);
  std::string prefix;
  for(const auto &h:from.trail) {
    if(h.edit>=from.edits.size()) return;
    auto &text=from.edits[h.edit].text;
    size_t quote=text.rfind('"');
    if(quote==std::string::npos) text+=" exr-shell-hide";
    else text.insert(quote," exr-shell-hide");
    if(!duplicate) prefix+="<p class=\"exr-shell-cjk"+h.kind+"\">"+h.markup+"</p>";
  }
  if(!prefix.empty()) to.edits.push_back({to.body,prefix});
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
        if(chinese) classes[i]+=indent_class(spaces);
      } else if(chinese) {
        classes[i]+=" exr-shell-heading";
        element e;e.line.assign(text+n.start,n.end-n.start);
        if(close_line(e,e.line.size()).kind==LINE_HEADING) classes[i]+=" exr-shell-chapter";
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
    struct zip_entry {size_t central,local,header,packed;std::vector<unsigned char> content;xml_classes classes;bool rewrite=false;std::string name;};
    std::vector<zip_entry> entries;
    std::vector<unsigned char> output,directory;bool changed=false;
    for(size_t index=0;index<count;index++) {
      if(at+46>input.size() || u32(input.data()+at)!=0x02014b50) return 0;
      const auto *c=input.data()+at;
      size_t cn=46+u16(c+28)+u16(c+30)+u16(c+32),local=u32(c+42);
      if(cn>input.size()-at || local+30>input.size() || u32(input.data()+local)!=0x04034b50) return 0;
      size_t header=30+u16(input.data()+local+26)+u16(input.data()+local+28),packed=u32(c+20),size=u32(c+24);
      if(header>input.size()-local || packed>input.size()-local-header) return 0;
      std::string name((const char *)c+46,u16(c+28));
      bool xml=name.size()>=5 && (name.substr(name.size()-5)==".html" || (name.size()>=6 && name.substr(name.size()-6)==".xhtml"));
      std::vector<unsigned char> content;
      if(xml && size<=96u*1024*1024 && !(u16(c+8)&1)) {
        content.resize(size);const void *data=input.data()+local+header;
        if(u16(c+10)==0 && packed==size) std::memcpy(content.data(),data,size);
        else if(u16(c+10)!=8 || tinfl_decompress_mem_to_mem(content.data(),size,data,packed,0)!=size) return 0;
      }
      zip_entry entry={at,local,header,packed,std::move(content),{},false,name};
      if(xml) entry.rewrite=parse_classes(entry.content,entry.classes);
      entries.push_back(std::move(entry));at+=cn;
    }
    /* Use the SDK's reading order, never ZIP-directory order. The borrowed
       source is only alive until publication_free, before input is destroyed. */
    if(std::any_of(entries.begin(),entries.end(),[](const zip_entry &e){return e.rewrite;})) {
      exr_source original={input.size(),read_memory,nullptr,&input,{}};
      exr_publication *raw=nullptr;
      if(exr_publication_open_source(&original,&raw,nullptr)==EXR_OK) {
        std::unique_ptr<exr_publication,decltype(&exr_publication_free)> publication(raw,exr_publication_free);
        size_t part_count=0;const auto *parts=exr_publication_parts(raw,&part_count);
        xml_classes *previous=nullptr;
        for(size_t i=0;i<part_count;i++) if(parts[i].in_reading_order) {
          auto found=std::find_if(entries.begin(),entries.end(),[&](const zip_entry &e){return e.name==parts[i].path;});
          if(found==entries.end() || !found->rewrite) {previous=nullptr;continue;}
          if(previous) carry_heading(*previous,found->classes);
          previous=&found->classes;
        }
      }
    }
    for(auto &entry:entries) {
      size_t local=entry.local,header=entry.header,packed=entry.packed;
      const auto *c=input.data()+entry.central;
      size_t cn=46+u16(c+28)+u16(c+30)+u16(c+32);
      auto &content=entry.content;bool rewrite=entry.rewrite;
      if(rewrite) apply_classes(entry.classes,content);
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
