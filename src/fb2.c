/* SPDX-License-Identifier: MIT */
#include "formats_internal.h"
#include "graphics_internal.h"
#include <miniz.h>
#include <ctype.h>

typedef struct { const char *id; size_t resource; } binary;
typedef struct {
  exr_document *out;
  const exr_document *xml;
  binary *binaries;
  size_t binary_count;
  exr_status status;
  exr_error *error;
} fb2;
static const char *local(const exr_node *n) {
  const char *p=n->name ? strrchr(n->name,'|') : NULL;
  return p ? p+1 : n->name ? n->name : "";
}
static int vocabulary(const exr_node *n) {
  static const char ns[]="http://www.gribuser.ru/xml/fictionbook/2.0|";
  return n->name && (!strchr(n->name,'|') || !strncmp(n->name,ns,sizeof(ns)-1));
}
static size_t child_named(const exr_document *d,size_t parent,const char *wanted) {
  size_t i;
  for(i=d->nodes[parent].first_child;i!=SIZE_MAX;i=d->nodes[i].next_sibling)
    if(vocabulary(&d->nodes[i]) && !strcmp(local(&d->nodes[i]),wanted)) return i;
  return SIZE_MAX;
}
static int text(const exr_document *d,size_t at,exr_buffer *b) {
  size_t i;
  if(d->nodes[at].kind==EXR_NODE_TEXT) return exr_append(b,d->nodes[at].text,strlen(d->nodes[at].text));
  for(i=d->nodes[at].first_child;i!=SIZE_MAX;i=d->nodes[i].next_sibling)
    if(!text(d,i,b)) return 0;
  return 1;
}
static int order(const void *a,const void *b) { return strcmp(((const binary *)a)->id,((const binary *)b)->id); }
static size_t binary_find(const fb2 *f,const char *href) {
  size_t lo=0,hi=f->binary_count; char id[2048];
  if(!href || *href!='#' || !exr_uri_decode(href+1,strlen(href+1),id)) return SIZE_MAX;
  while(lo<hi) { size_t mid=lo+(hi-lo)/2; if(strcmp(f->binaries[mid].id,id)<0) lo=mid+1; else hi=mid; }
  return lo<f->binary_count && !strcmp(f->binaries[lo].id,id) ? f->binaries[lo].resource : SIZE_MAX;
}
static int digit(unsigned char c) {
  if(c>='A' && c<='Z') return c-'A';
  if(c>='a' && c<='z') return c-'a'+26;
  if(c>='0' && c<='9') return c-'0'+52;
  return c=='+' ? 62 : c=='/' ? 63 : c=='=' ? 64 : -1;
}
static exr_status decode(fb2 *f,size_t node,exr_buffer *out) {
  unsigned q[4],used=0; int ended=0; size_t child,i;
  for(child=f->xml->nodes[node].first_child;child!=SIZE_MAX;child=f->xml->nodes[child].next_sibling) {
    const exr_node *v=&f->xml->nodes[child];
    if(v->kind!=EXR_NODE_TEXT) return exr_fail(f->error,EXR_FORMAT,"FB2 binary must contain base64 text");
    for(i=0;v->text[i];i++) {
      unsigned char c=(unsigned char)v->text[i], bytes[3]; int value;
      if(c==' ' || c=='\t' || c=='\r' || c=='\n') continue;
      value=digit(c);
      if(value<0 || ended) goto invalid;
      q[used++]=(unsigned)value;
      if(used!=4) continue;
      if(q[0]>=64 || q[1]>=64 || (q[2]==64 && q[3]!=64) ||
          (q[2]==64 && (q[1]&15)) || (q[3]==64 && q[2]!=64 && (q[2]&3))) goto invalid;
      bytes[0]=(unsigned char)((q[0]<<2)|(q[1]>>4));
      bytes[1]=(unsigned char)((q[1]<<4)|(q[2]>>2));
      bytes[2]=(unsigned char)((q[2]<<6)|q[3]);
      used=q[2]==64 ? 1 : q[3]==64 ? 2 : 3;
      if(out->size>32u*1024*1024-used || !exr_append(out,bytes,used))
        return exr_fail(f->error,EXR_LIMIT,"FB2 binary exceeds allocation or 32 MiB limit");
      ended=q[3]==64; used=0;
    }
  }
  if(used) goto invalid;
  return exr_append(out,"",0) ? EXR_OK : EXR_MEMORY;
invalid:
  return exr_fail(f->error,EXR_FORMAT,"Invalid FB2 base64 encoding");
}
static size_t node(fb2 *f,size_t parent,exr_node_kind kind,const char *tag,const char *value) {
  size_t at=exr_model_html(f->out,parent,0,kind,tag,value);
  if(at==SIZE_MAX) f->status=exr_fail(f->error,EXR_LIMIT,"FB2 model exceeds limit");
  return at;
}
static int attribute(fb2 *f,size_t at,const char *key,const char *value) {
  return exr_model_attribute(f->out,at,key,value);
}
static int copy(fb2 *f,size_t parent,size_t source,int heading,int notes,unsigned depth) {
  const exr_node *v=&f->xml->nodes[source]; const char *tag=local(v),*mapped=tag,*href;
  exr_node_kind kind=v->kind; size_t at,i;
  if(depth>252) { f->status=EXR_LIMIT; return 0; }
  if(kind==EXR_NODE_TEXT) return node(f,parent,EXR_NODE_TEXT,NULL,v->text)!=SIZE_MAX;
  if(vocabulary(v)) {
    if(!strcmp(tag,"title")) { kind=EXR_NODE_SECTION; mapped="section"; heading=1; }
    else if(!strcmp(tag,"p") || !strcmp(tag,"v") || !strcmp(tag,"text-author")) {
      mapped=heading ? "h1" : "p"; kind=heading ? EXR_NODE_HEADING : EXR_NODE_PARAGRAPH;
    } else if(!strcmp(tag,"subtitle")) { mapped="h2"; kind=EXR_NODE_HEADING; }
    else if(!strcmp(tag,"emphasis")) mapped="em";
    else if(!strcmp(tag,"strikethrough")) mapped="s";
    else if(!strcmp(tag,"empty-line")) { mapped="br"; kind=EXR_NODE_BREAK; }
    else if(!strcmp(tag,"image")) { mapped="img"; kind=EXR_NODE_IMAGE; }
    else if(!strcmp(tag,"epigraph") || !strcmp(tag,"cite")) { mapped="blockquote"; kind=EXR_NODE_SECTION; }
    else if(!strcmp(tag,"body") || !strcmp(tag,"poem") || !strcmp(tag,"stanza")) { mapped="section"; kind=EXR_NODE_SECTION; }
    else if(!strcmp(tag,"style")) mapped="span";
    if(!strcmp(tag,"body")) {
      const char *name=exr_node_attribute(v,"name");
      if(name && (!strcmp(name,"notes") || !strcmp(name,"comments"))) notes=1;
    }
    if(notes && !strcmp(tag,"section")) kind=EXR_NODE_NOTE;
    at=node(f,parent,kind,mapped,NULL);
  } else at=exr_model_node(f->out,parent,0,kind,v->name,NULL,0);
  if(at==SIZE_MAX) return 0;
  for(i=0;i<v->attribute_count;i++)
    if(!attribute(f,at,v->attributes[i].name,v->attributes[i].value)) return 0;
  if(vocabulary(v) && !strcmp(tag,"section") && !attribute(f,at,"data-fb2-section","1")) return 0;
  if(vocabulary(v) && !strcmp(tag,"title") && v->parent!=SIZE_MAX &&
      !strcmp(local(&f->xml->nodes[v->parent]),"section")) {
    size_t parent=v->parent,level=0; char value[24];
    for(;parent!=SIZE_MAX;parent=f->xml->nodes[parent].parent)
      if(!strcmp(local(&f->xml->nodes[parent]),"section")) level++;
    snprintf(value,sizeof(value),"%zu",level);
    if(!attribute(f,at,"data-fb2-title",value)) return 0;
  }
  if(notes && kind==EXR_NODE_NOTE && !attribute(f,at,"role","doc-footnote")) return 0;
  href=exr_node_attribute(v,"http://www.w3.org/1999/xlink|href");
  if(!href) href=exr_node_attribute(v,"href");
  if(vocabulary(v) && !strcmp(tag,"image") && href) {
    i=binary_find(f,href);
    if(i==SIZE_MAX && *href=='#') {
      f->status=exr_fail(f->error,EXR_FORMAT,"FB2 image refers to a missing binary"); return 0;
    }
    if(!attribute(f,at,"src",i==SIZE_MAX ? href : f->out->resources[i].path)) return 0;
  } else if(vocabulary(v) && !strcmp(tag,"a") && href) {
    if(!attribute(f,at,"href",href)) return 0;
    if(exr_node_attribute(v,"type") && !strcmp(exr_node_attribute(v,"type"),"note") &&
        !attribute(f,at,"role","doc-noteref")) return 0;
  }
  if(vocabulary(v) && !strcmp(tag,"style") && exr_node_attribute(v,"name") &&
      !attribute(f,at,"class",exr_node_attribute(v,"name"))) return 0;
  for(i=v->first_child;i!=SIZE_MAX;i=f->xml->nodes[i].next_sibling)
    if(!copy(f,at,i,heading,notes,depth+1)) return 0;
  return 1;
}
static exr_status fb2_xml(exr_document *d,const void *data,size_t size,exr_error *e) {
  exr_document source={0}; exr_resource source_resource={"source","book.fb2","application/fb2+xml",""};
  fb2 f={d,&source,NULL,0,EXR_OK,e}; exr_buffer title={0};
  size_t root,description,info,cover,title_node,i,j,html,head,body,chapter;
  source.resources=&source_resource; source.resource_count=1;
  f.status=exr_xml_tree(&source,data,size,0,1,1,"FictionBook",e);
  if(f.status!=EXR_OK) goto done;
  root=source.nodes[source.chapters[0].root].first_child;
  if(root==SIZE_MAX || !vocabulary(&source.nodes[root])) { f.status=EXR_FORMAT; goto done; }
  for(i=source.nodes[root].first_child;i!=SIZE_MAX;i=source.nodes[i].next_sibling)
    if(vocabulary(&source.nodes[i]) && !strcmp(local(&source.nodes[i]),"binary")) f.binary_count++;
  if(f.binary_count>9996) { f.status=EXR_LIMIT; goto done; }
  if(f.binary_count) {
    f.binaries=calloc(f.binary_count,sizeof(*f.binaries));
    d->resources=calloc(f.binary_count,sizeof(*d->resources));
    d->resource_data=calloc(f.binary_count,sizeof(*d->resource_data));
    if(!f.binaries || !d->resources || !d->resource_data) { f.status=EXR_MEMORY; goto done; }
    d->resource_count=d->resource_capacity=f.binary_count;
  }
  for(i=source.nodes[root].first_child,j=0;i!=SIZE_MAX;i=source.nodes[i].next_sibling) {
    const exr_node *v=&source.nodes[i]; exr_resource *r; exr_buffer decoded={0};
    const char *id,*media; char path[80];
    if(!vocabulary(v) || strcmp(local(v),"binary")) continue;
    id=exr_node_attribute(v,"id"); media=exr_node_attribute(v,"content-type");
    if(!id || !*id || strlen(id)>2046) { f.status=exr_fail(e,EXR_FORMAT,"FB2 binary needs a unique ID"); goto done; }
    r=&d->resources[j]; snprintf(path,sizeof(path),"assets/binary-%zu.bin",j);
    r->id=exr_model_copy(d,id,strlen(id)); r->path=exr_model_copy(d,path,strlen(path));
    if(!media || !*media) media="application/octet-stream";
    r->media_type=exr_model_copy(d,media,strlen(media)); r->properties=exr_model_copy(d,"",0);
    if(!r->id || !r->path || !r->media_type || !r->properties) { f.status=EXR_MEMORY; goto done; }
    f.status=decode(&f,i,&decoded);
    if(f.status!=EXR_OK) { free(decoded.data); goto done; }
    d->resource_data[j]=(exr_resource_data){(unsigned char *)decoded.data,decoded.size};
    f.binaries[j]=(binary){id,j}; j++;
  }
  if(f.binary_count>1) qsort(f.binaries,f.binary_count,sizeof(*f.binaries),order);
  for(i=1;i<f.binary_count;i++) if(!strcmp(f.binaries[i-1].id,f.binaries[i].id)) {
    f.status=exr_fail(e,EXR_FORMAT,"Duplicate FB2 binary ID"); goto done;
  }
  description=child_named(&source,root,"description");
  info=description==SIZE_MAX ? SIZE_MAX : child_named(&source,description,"title-info");
  title_node=info==SIZE_MAX ? SIZE_MAX : child_named(&source,info,"book-title");
  if(title_node!=SIZE_MAX && !text(&source,title_node,&title)) { f.status=EXR_LIMIT; goto done; }
  d->title=title.data; title.data=NULL;
  cover=info==SIZE_MAX ? SIZE_MAX : child_named(&source,info,"coverpage");
  if(cover!=SIZE_MAX) {
    i=child_named(&source,cover,"image");
    if(i!=SIZE_MAX) {
      const char *href=exr_node_attribute(&source.nodes[i],"http://www.w3.org/1999/xlink|href");
      if(!href) href=exr_node_attribute(&source.nodes[i],"href");
      j=binary_find(&f,href);
      if(href && *href=='#' && j==SIZE_MAX) { f.status=exr_fail(e,EXR_FORMAT,"FB2 cover refers to a missing binary"); goto done; }
      if(j!=SIZE_MAX) {
        free((void *)d->resources[j].properties);
        d->resources[j].properties=exr_model_copy(d,"cover-image",11);
        if(!d->resources[j].properties) { f.status=EXR_MEMORY; goto done; }
      }
    }
  }
  if(exr_model_node(d,SIZE_MAX,SIZE_MAX,EXR_NODE_DOCUMENT,NULL,NULL,0)==SIZE_MAX) { f.status=EXR_LIMIT; goto done; }
  chapter=node(&f,0,EXR_NODE_CHAPTER,NULL,NULL); if(chapter==SIZE_MAX) goto done;
  d->chapters=calloc(1,sizeof(*d->chapters)); if(!d->chapters) { f.status=EXR_MEMORY; goto done; }
  d->chapter_count=d->chapter_capacity=1;
  d->chapters[0]=(exr_chapter){"main","book.xhtml",chapter,SIZE_MAX,1,1};
  html=node(&f,chapter,EXR_NODE_ELEMENT,"html",NULL); if(html==SIZE_MAX) goto done;
  head=node(&f,html,EXR_NODE_ELEMENT,"head",NULL); if(head==SIZE_MAX) goto done;
  i=node(&f,head,EXR_NODE_ELEMENT,"title",NULL); if(i==SIZE_MAX) goto done;
  if(d->title && node(&f,i,EXR_NODE_TEXT,NULL,d->title)==SIZE_MAX) goto done;
  for(i=source.nodes[root].first_child;i!=SIZE_MAX;i=source.nodes[i].next_sibling) {
    if(vocabulary(&source.nodes[i]) && !strcmp(local(&source.nodes[i]),"stylesheet")) {
      size_t style=node(&f,head,EXR_NODE_ELEMENT,"style",NULL), c;
      if(style==SIZE_MAX) goto done;
      for(c=source.nodes[i].first_child;c!=SIZE_MAX;c=source.nodes[c].next_sibling)
        if(!copy(&f,style,c,0,0,0)) goto failed;
    }
  }
  body=node(&f,html,EXR_NODE_ELEMENT,"body",NULL); if(body==SIZE_MAX) goto done;
  j=0;
  for(i=source.nodes[root].first_child;i!=SIZE_MAX;i=source.nodes[i].next_sibling)
    if(vocabulary(&source.nodes[i]) && !strcmp(local(&source.nodes[i]),"body")) {
      if(!copy(&f,body,i,0,0,0)) goto failed;
      j++;
    }
  if(!j) f.status=exr_fail(e,EXR_FORMAT,"FB2 has no body");
  goto done;
failed:
  if(f.status==EXR_OK) f.status=exr_fail(e,EXR_LIMIT,"FB2 model allocation exceeds limit");
done:
  free(title.data); free(f.binaries);
  source.resources=NULL; source.resource_count=0; exr_model_free(&source);
  return f.status;
}

/* Expat already handles UTF-8/UTF-16. Decode the FB2-specific legacy code page
   here so EPUB XML encoding behavior is untouched. */
static exr_status fb2_encoded(exr_document *d,const void *data,size_t size,exr_error *e) {
  static const uint16_t cp1251[128]={
    0x402,0x403,0x201a,0x453,0x201e,0x2026,0x2020,0x2021,0x20ac,0x2030,0x409,0x2039,0x40a,0x40c,0x40b,0x40f,
    0x452,0x2018,0x2019,0x201c,0x201d,0x2022,0x2013,0x2014,0x0,0x2122,0x459,0x203a,0x45a,0x45c,0x45b,0x45f,
    0xa0,0x40e,0x45e,0x408,0xa4,0x490,0xa6,0xa7,0x401,0xa9,0x404,0xab,0xac,0xad,0xae,0x407,
    0xb0,0xb1,0x406,0x456,0x491,0xb5,0xb6,0xb7,0x451,0x2116,0x454,0xbb,0x458,0x405,0x455,0x457,
    0x410,0x411,0x412,0x413,0x414,0x415,0x416,0x417,0x418,0x419,0x41a,0x41b,0x41c,0x41d,0x41e,0x41f,
    0x420,0x421,0x422,0x423,0x424,0x425,0x426,0x427,0x428,0x429,0x42a,0x42b,0x42c,0x42d,0x42e,0x42f,
    0x430,0x431,0x432,0x433,0x434,0x435,0x436,0x437,0x438,0x439,0x43a,0x43b,0x43c,0x43d,0x43e,0x43f,
    0x440,0x441,0x442,0x443,0x444,0x445,0x446,0x447,0x448,0x449,0x44a,0x44b,0x44c,0x44d,0x44e,0x44f,
  };
  const unsigned char *s=data; size_t i,end=0; char declaration[512]; exr_buffer utf8={0}; exr_status status;
  if(size>=5 && !memcmp(s,"<?xml",5)) {
    for(end=5;end+1<size && end+1<sizeof(declaration);end++) if(s[end]=='?' && s[end+1]=='>') { end+=2; break; }
    if(end>=sizeof(declaration)) return exr_fail(e,EXR_FORMAT,"FB2_ENCODING: oversized XML declaration");
    for(i=0;i<end;i++) declaration[i]=(char)tolower(s[i]);
    declaration[end]=0;
    {
      char *enc=strstr(declaration,"encoding"),quote=0; size_t begin=0,finish=0;
      if(enc) {
        enc+=8; while(isspace((unsigned char)*enc)) enc++;
        if(*enc=='=') { enc++; while(isspace((unsigned char)*enc)) enc++; quote=*enc++; }
        if(quote=='\'' || quote=='"') {
          char *stop=strchr(enc,quote);
          if(stop && (((size_t)(stop-enc)==12 && !memcmp(enc,"windows-1251",12)) ||
                      ((size_t)(stop-enc)==6 && !memcmp(enc,"cp1251",6)))) {
            begin=(size_t)(enc-declaration); finish=(size_t)(stop-declaration);
          }
        }
      }
      if(!finish) return fb2_xml(d,data,size,e);
      for(i=0;i<size;i++) {
        uint32_t cp=s[i]<128 ? s[i] : cp1251[s[i]-128];
        if(i==begin) {
          if(!exr_append(&utf8,"UTF-8",5)) { free(utf8.data); return exr_fail(e,EXR_LIMIT,"FB2 decoded XML exceeds text limit"); }
          i=finish-1; continue;
        }
        if(!cp) { free(utf8.data); return exr_fail(e,EXR_ENCODING,"FB2_ENCODING: undefined windows-1251 byte"); }
        if(!exr_codepoint(&utf8,cp)) { free(utf8.data); return exr_fail(e,EXR_LIMIT,"FB2 decoded XML exceeds text limit"); }
      }
      status=fb2_xml(d,utf8.data,utf8.size,e); free(utf8.data); return status;
    }
  }
  return fb2_xml(d,data,size,e);
}
exr_status exr_fb2(exr_document *d,const void *data,size_t size,exr_error *e) {
  mz_zip_archive zip={0}; mz_zip_archive_file_stat stat;
  size_t i,count,member=SIZE_MAX,n=0; void *xml=NULL; exr_status status=EXR_FORMAT;
  if(size<4 || memcmp(data,"PK\003\004",4)) return fb2_encoded(d,data,size,e);
  if(!mz_zip_reader_init_mem(&zip,data,size,0)) return exr_fail(e,EXR_FORMAT,"FB2_ZIP: invalid ZIP directory");
  count=mz_zip_reader_get_num_files(&zip);
  if(count>10000) { status=EXR_LIMIT; goto bad; }
  for(i=0;i<count;i++) {
    size_t len;
    if(!mz_zip_reader_file_stat(&zip,(mz_uint)i,&stat)) goto bad;
    if(stat.m_is_directory) continue;
    len=strlen(stat.m_filename);
    if(len<4 || stat.m_filename[len-4]!='.' || tolower((unsigned char)stat.m_filename[len-3])!='f' ||
       tolower((unsigned char)stat.m_filename[len-2])!='b' || stat.m_filename[len-1]!='2') continue;
    if(member!=SIZE_MAX) goto bad;
    if(stat.m_is_encrypted) { status=EXR_UNSUPPORTED; goto bad; }
    if(stat.m_uncomp_size>EXR_MAX_INPUT) { status=EXR_LIMIT; goto bad; }
    member=i;
  }
  if(member==SIZE_MAX) goto bad;
  xml=mz_zip_reader_extract_to_heap(&zip,(mz_uint)member,&n,0);
  if(!xml) goto bad;
  status=fb2_encoded(d,xml,n,e); goto done;
bad: exr_fail(e,status,"FB2_ZIP: requires one readable .fb2 member within the input limit");
done: mz_free(xml); mz_zip_reader_end(&zip); return status;
}
