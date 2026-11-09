/* SPDX-License-Identifier: MIT */
#include "formats_internal.h"
#include <ctype.h>

/* Shared construction/loading helpers for the non-ZIP publications. The result
   is an ordinary document consumed by the EPUB pager and renderer. */
exr_status exr_book_resource(exr_document *d,const char *path,const char *type,
  const void *data,size_t size,size_t *index,exr_error *e) {
  exr_resource *r; exr_resource_data *bytes;
  if(d->resource_count>=10000 || size>EXR_MAX_INPUT)
    return exr_fail(e,EXR_LIMIT,"Book resource limit exceeded");
  if(!exr_grow((void **)&d->resources,&d->resource_capacity,d->resource_count+1,sizeof(*r))) goto memory;
  bytes=realloc(d->resource_data,(d->resource_count+1)*sizeof(*bytes));
  if(!bytes) goto memory;
  d->resource_data=bytes; *index=d->resource_count++;
  r=&d->resources[*index]; memset(r,0,sizeof(*r)); memset(&bytes[*index],0,sizeof(*bytes));
  r->id=exr_model_copy(d,path,strlen(path)); r->path=exr_model_copy(d,path,strlen(path));
  r->media_type=exr_model_copy(d,type,strlen(type)); r->properties=exr_model_copy(d,"",0);
  bytes[*index].bytes=malloc(size ? size : 1);
  if(!r->id || !r->path || !r->media_type || !r->properties || !bytes[*index].bytes) goto memory;
  if(size) memcpy(bytes[*index].bytes,data,size);
  bytes[*index].size=size; return EXR_OK;
memory:
  return exr_fail(e,EXR_MEMORY,"Book resource allocation failed");
}
exr_status exr_book_chapter(exr_document *d,size_t *body,exr_error *e) {
  char path[64]; size_t root,html,resource=0,part=d->chapter_count; exr_status status;
  if(part>=10000) return exr_fail(e,EXR_LIMIT,"Book exceeds 10000 sections");
  if(!d->node_count && exr_model_node(d,SIZE_MAX,SIZE_MAX,EXR_NODE_DOCUMENT,NULL,NULL,0)==SIZE_MAX) goto limit;
  snprintf(path,sizeof(path),"part%04zu.xhtml",part);
  status=exr_book_resource(d,path,"application/xhtml+xml",NULL,0,&resource,e);
  if(status!=EXR_OK) return status;
  if(!exr_grow((void **)&d->chapters,&d->chapter_capacity,part+1,sizeof(*d->chapters))) goto limit;
  root=exr_model_node(d,0,part,EXR_NODE_CHAPTER,NULL,NULL,0);
  if(root==SIZE_MAX) goto limit;
  d->chapters[part]=(exr_chapter){d->resources[resource].id,d->resources[resource].path,root,resource,1,1};
  d->chapter_count++;
  html=exr_model_html(d,root,part,EXR_NODE_ELEMENT,"html",NULL);
  if(html==SIZE_MAX) goto limit;
  *body=exr_model_html(d,html,part,EXR_NODE_ELEMENT,"body",NULL);
  if(*body==SIZE_MAX) goto limit;
  return EXR_OK;
limit:
  return exr_fail(e,EXR_LIMIT,"Book section model allocation limit");
}

static int clone_node(exr_document *d,const exr_document *source,size_t at,size_t parent,size_t chapter,unsigned depth) {
  const exr_node *v=&source->nodes[at]; size_t n,i;
  if(depth>254) return 0;
  n=exr_model_node(d,parent,chapter,v->kind,v->name,v->text,v->text ? strlen(v->text) : 0);
  if(n==SIZE_MAX) return 0;
  for(i=0;i<v->attribute_count;i++)
    if(!exr_model_attribute(d,n,v->attributes[i].name,v->attributes[i].value)) return 0;
  for(i=v->first_child;i!=SIZE_MAX;i=source->nodes[i].next_sibling)
    if(!clone_node(d,source,i,n,chapter,depth+1)) return 0;
  return 1;
}
exr_status exr_book_slice(void *context,size_t part,exr_document **out,exr_error *e) {
  const exr_document *source=context; exr_document *d=EXR_NEW(exr_document);
  size_t i,index=0; exr_status status=EXR_MEMORY;
  *out=NULL;
  if(!d) goto done;
  if(part>=source->chapter_count) { status=EXR_ARGUMENT; goto done; }
  d->format=source->format;
  d->title=exr_model_copy(d,exr_document_title(source),strlen(exr_document_title(source)));
  for(i=0;i<source->resource_count;i++) {
    const exr_resource *r=&source->resources[i];
    status=exr_book_resource(d,r->path,r->media_type,source->resource_data[i].bytes,source->resource_data[i].size,&index,e);
    if(status!=EXR_OK) goto done;
    free((void *)d->resources[index].properties);
    d->resources[index].properties=exr_model_copy(d,r->properties,strlen(r->properties));
    if(!d->resources[index].properties) { status=EXR_MEMORY; goto done; }
  }
  status=EXR_LIMIT;
  if(exr_model_node(d,SIZE_MAX,SIZE_MAX,EXR_NODE_DOCUMENT,NULL,NULL,0)==SIZE_MAX ||
     !clone_node(d,source,source->chapters[part].root,0,0,0)) goto done;
  d->chapters=calloc(1,sizeof(*d->chapters));
  if(!d->chapters) { status=EXR_MEMORY; goto done; }
  d->chapter_count=d->chapter_capacity=1; d->chapters[0]=source->chapters[part];
  d->chapters[0].root=1; index=d->chapters[0].resource;
  d->chapters[0].id=d->resources[index].id; d->chapters[0].path=d->resources[index].path;
  status=exr_model_finish(d,e);
done:
  if(status!=EXR_OK) { exr_document_free(d); return exr_fail(e,status,"Book section load failed"); }
  *out=d; return EXR_OK;
}

/* Tolerant Mobipocket HTML, with source byte positions retained before decoding
   CP1252. A new section is started at every mbp:pagebreak (and bounded block
   boundaries for files without page breaks). No HTML parser dependency. */
static int eq(const char *a,const char *b) { return !strcmp(a,b); }
static int unescape(const char *s,size_t size,unsigned encoding,exr_buffer *out) {
  size_t i=0;
  while(i<size) {
    uint32_t cp=(unsigned char)s[i++];
    if(cp=='&') {
      size_t j=i; uint32_t value=0; int valid=0;
      while(j<size && j-i<20 && s[j]!=';' && !isspace((unsigned char)s[j])) j++;
      if(j<size && s[j]==';') {
        size_t n=j-i; const char *a=s+i;
        if(n==3 && !memcmp(a,"amp",3)) { value='&'; valid=1; }
        else if(n==2 && !memcmp(a,"lt",2)) { value='<'; valid=1; }
        else if(n==2 && !memcmp(a,"gt",2)) { value='>'; valid=1; }
        else if(n==4 && !memcmp(a,"quot",4)) { value='"'; valid=1; }
        else if(n==4 && !memcmp(a,"apos",4)) { value='\''; valid=1; }
        else if(n==4 && !memcmp(a,"nbsp",4)) { value=160; valid=1; }
        else if(n>1 && a[0]=='#') {
          size_t k=1; unsigned base=10; valid=1;
          if(a[k]=='x' || a[k]=='X') { base=16; k++; }
          if(k==n) valid=0;
          for(;k<n && valid;k++) {
            unsigned c=(unsigned char)tolower((unsigned char)a[k]);
            unsigned digit=c>='0' && c<='9' ? c-'0' : c>='a' && c<='f' ? c-'a'+10 : 99;
            if(digit>=base || value>(0x10ffff-digit)/base) valid=0;
            else value=value*base+digit;
          }
        }
        if(valid && value && !(value>=0xd800 && value<=0xdfff)) { cp=value; i=j+1; }
      }
    } else if(encoding==1252) cp=exr_windows1252((unsigned char)cp);
    else if(cp>=128) { size_t at=i-1; if(!exr_next(s,size,&at,&cp)) return 0; i=at; }
    if(!cp) continue;
    if(!exr_codepoint(out,cp)) return 0;
  }
  return exr_append(out,"",0);
}
static int number(const char *s,size_t *out) {
  size_t n=0; if(!*s) return 0;
  for(;*s;s++) { if(*s<'0' || *s>'9' || n>(SIZE_MAX-(*s-'0'))/10) return 0; n=n*10+(*s-'0'); }
  *out=n; return 1;
}
exr_status exr_mobi_html(exr_document *d,const exr_mobi_record *records,size_t nr,
  const char *text,size_t size,unsigned encoding,exr_error *e) {
  size_t stack[256],depth=0,body=0,at=0,section_start=0,first_image;
  int pending=0; exr_status status; exr_buffer value={0}; char skip[32]={0};
  size_t *positions=NULL,*nodes=NULL,marks=0,capacity=0; /* one source mark per element */
  const unsigned char *h=records[0].data;
  first_image=((uint32_t)h[108]<<24)|((uint32_t)h[109]<<16)|((uint32_t)h[110]<<8)|h[111];
  status=exr_book_chapter(d,&body,e); if(status!=EXR_OK) return status;
  stack[0]=body;
  while(at<size) {
    size_t begin=at,n,parent; char tag[64]={0}; int closing=0,self=0;
    if(text[at]!='<') {
      while(at<size && text[at]!='<') at++;
      if(skip[0]) continue;
      for(n=begin;n<at && isspace((unsigned char)text[n]);n++) {}
      if(n==at && pending) continue;
      if(pending) { status=exr_book_chapter(d,&body,e); if(status!=EXR_OK) goto done; stack[depth=0]=body; pending=0; section_start=begin; }
      value.size=0;
      if(!unescape(text+begin,at-begin,encoding,&value)) { status=exr_fail(e,EXR_ENCODING,"MOBI text has invalid encoding"); goto done; }
      if(exr_model_html(d,stack[depth],d->chapter_count-1,EXR_NODE_TEXT,NULL,value.data)==SIZE_MAX) goto limit;
      continue;
    }
    if(size-at>=4 && !memcmp(text+at,"<!--",4)) {
      const char *end=strstr(text+at+4,"-->");
      if(!end) goto malformed;
      at=(size_t)(end-text)+3; continue;
    }
    at++; if(at<size && text[at]=='/') { closing=1; at++; }
    n=0;
    while(at<size && (isalnum((unsigned char)text[at]) || text[at]==':' || text[at]=='-')) {
      if(n+1<sizeof(tag)) tag[n++]=(char)tolower((unsigned char)text[at]);
      at++;
    }
    if(!n) { while(at<size && text[at]!='>') at++; if(at<size) at++; continue; }
    parent=stack[depth];
    if(!closing && eq(tag,"mbp:pagebreak")) pending=1;
    if(skip[0]) { if(closing && eq(tag,skip)) skip[0]=0; n=SIZE_MAX; }
    else if(eq(tag,"html") || eq(tag,"body") || eq(tag,"mbp:pagebreak")) n=SIZE_MAX;
    else if(!closing && (eq(tag,"head") || eq(tag,"script") || eq(tag,"style") || eq(tag,"object"))) {
      snprintf(skip,sizeof(skip),"%.31s",tag); n=SIZE_MAX;
    } else if(closing) {
      size_t level=depth;
      while(level && !eq(exr_html_tag(d,&d->nodes[stack[level]]),tag)) level--;
      if(level) depth=level-1;
      n=SIZE_MAX;
    } else {
      int block=eq(tag,"p") || eq(tag,"div") || (tag[0]=='h' && tag[1]>='1' && tag[1]<='6' && !tag[2]);
      if(block && begin-section_start>256*1024) pending=1;
      if(pending) { status=exr_book_chapter(d,&body,e); if(status!=EXR_OK) goto done; stack[depth=0]=body; pending=0; section_start=begin; }
      if(block && depth && eq(exr_html_tag(d,&d->nodes[stack[depth]]),"p")) depth--;
      parent=stack[depth];
      n=exr_model_html(d,parent,d->chapter_count-1,exr_xml_element_kind(tag),tag,NULL);
      if(n==SIZE_MAX) goto limit;
      if(!exr_grow((void **)&positions,&capacity,marks+1,sizeof(*positions))) goto limit;
      { size_t *grown=realloc(nodes,capacity*sizeof(*nodes)); if(!grown) goto limit; nodes=grown; }
      positions[marks]=begin; nodes[marks++]=n;
    }
    while(at<size && text[at]!='>') {
      char key[64]={0}; size_t k=0,start; char quote=0;
      while(at<size && isspace((unsigned char)text[at])) at++;
      if(at==size || text[at]=='>') break;
      if(text[at]=='/') { self=1; at++; continue; }
      while(at<size && !isspace((unsigned char)text[at]) && text[at]!='=' && text[at]!='>') {
        if(k+1<sizeof(key)) key[k++]=(char)tolower((unsigned char)text[at]);
        at++;
      }
      while(at<size && isspace((unsigned char)text[at])) at++;
      start=at;
      if(at<size && text[at]=='=') {
        at++; while(at<size && isspace((unsigned char)text[at])) at++;
        if(at<size && (text[at]=='\'' || text[at]=='"')) quote=text[at++];
        start=at;
        while(at<size && (quote ? text[at]!=quote : !isspace((unsigned char)text[at]) && text[at]!='>')) at++;
      }
      value.size=0;
      if(!unescape(text+start,at-start,encoding,&value)) goto malformed;
      if(quote) { if(at==size) goto malformed; at++; }
      if(n!=SIZE_MAX && key[0] && !exr_model_attribute(d,n,key,value.data)) goto limit;
    }
    if(at==size) goto malformed;
    at++;
    if(n==SIZE_MAX) continue;
    if(eq(tag,"img")) {
      const char *rec=exr_node_attribute(&d->nodes[n],"recindex"); size_t number_,r,index; char path[64];
      if(rec) {
        if(!number(rec,&number_) || !number_ || first_image>=nr || number_-1>=nr-first_image) goto image_error;
        r=first_image+number_-1; snprintf(path,sizeof(path),"image%05zu.bin",r);
        for(index=0;index<d->resource_count;index++) if(eq(d->resources[index].path,path)) break;
        if(index==d->resource_count) {
          const unsigned char *p=records[r].data; size_t len=records[r].size;
          const char *mime=len>=8 && !memcmp(p,"\x89PNG\r\n\x1a\n",8) ? "image/png" :
            len>=6 && (!memcmp(p,"GIF87a",6) || !memcmp(p,"GIF89a",6)) ? "image/gif" :
            len>=3 && p[0]==255 && p[1]==216 && p[2]==255 ? "image/jpeg" : NULL;
          if(!mime) goto image_error;
          status=exr_book_resource(d,path,mime,p,len,&index,e); if(status!=EXR_OK) goto done;
        }
        if(!exr_model_attribute(d,n,"src",path)) goto limit;
      }
    }
    if(!self && !eq(tag,"img") && !eq(tag,"br") && !eq(tag,"hr") && !eq(tag,"meta") && !eq(tag,"link")) {
      if(depth==254) goto limit;
      stack[++depth]=n;
    }
  }
  /* Resolve filepos in original bytes, before CP1252 expansion or HTML repair. */
  for(at=0;at<d->node_count;at++) {
    const char *pos=exr_node_attribute(&d->nodes[at],"filepos"); size_t offset,lo=0,hi=marks,target; char id[64],href[128];
    if(!pos) continue;
    if(!number(pos,&offset) || offset>=size || !marks) goto malformed;
    while(lo<hi) { size_t mid=lo+(hi-lo)/2; if(positions[mid]<=offset) lo=mid+1; else hi=mid; }
    target=nodes[lo ? lo-1 : 0]; snprintf(id,sizeof(id),"filepos-%zu",positions[lo ? lo-1 : 0]);
    { const char *existing=exr_node_attribute(&d->nodes[target],"id");
      if(existing) snprintf(href,sizeof(href),"%s#%s",d->chapters[d->nodes[target].chapter].path,existing);
      else { if(!exr_model_attribute(d,target,"id",id)) goto limit;
        snprintf(href,sizeof(href),"%s#%s",d->chapters[d->nodes[target].chapter].path,id); }
    }
    if(!exr_model_attribute(d,at,"href",href)) goto limit;
  }
  status=exr_mobi_navigation(d,records,nr,positions,nodes,marks,e); goto done;
image_error: status=exr_fail(e,EXR_FORMAT,"MOBI RECINDEX references a missing or unsupported image record"); goto done;
malformed: status=exr_fail(e,EXR_FORMAT,"MOBI malformed HTML or filepos target"); goto done;
limit: status=exr_fail(e,EXR_LIMIT,"MOBI section model exceeds limit");
done: free(value.data); free(positions); free(nodes); return status;
}

typedef struct {
  exr_document *out;
  const exr_document *source;
  size_t body,owner,head;
  exr_error *error;
} fb2_split;
static int marked_below(const exr_document *d,size_t at) {
  size_t i;
  if(exr_node_attribute(&d->nodes[at],"data-fb2-section")) return 1;
  for(i=d->nodes[at].first_child;i!=SIZE_MAX;i=d->nodes[i].next_sibling)
    if(marked_below(d,i)) return 1;
  return 0;
}
static exr_status split_walk(fb2_split *f,size_t at,size_t owner,unsigned depth) {
  const exr_node *v=&f->source->nodes[at]; size_t i; exr_status status;
  if(depth>254) return exr_fail(f->error,EXR_LIMIT,"FB2 section nesting exceeds limit");
  if(exr_node_attribute(v,"data-fb2-section")) owner=at;
  if(marked_below(f->source,at)) {
    for(i=v->first_child;i!=SIZE_MAX;i=f->source->nodes[i].next_sibling) {
      status=split_walk(f,i,owner,depth+1); if(status!=EXR_OK) return status;
    }
    return EXR_OK;
  }
  if(v->kind==EXR_NODE_TEXT) {
    const char *s=v->text; while(*s && isspace((unsigned char)*s)) s++;
    if(!*s) return EXR_OK;
  }
  if(!f->out->chapter_count || owner!=f->owner) {
    size_t part,wrapper;
    status=exr_book_chapter(f->out,&f->body,f->error); if(status!=EXR_OK) return status;
    f->owner=owner; part=f->out->chapter_count-1;
    if(f->head!=SIZE_MAX && !clone_node(f->out,f->source,f->head,f->out->nodes[f->body].parent,part,0)) goto limit;
    if(owner!=SIZE_MAX) {
      const exr_node *o=&f->source->nodes[owner];
      wrapper=exr_model_html(f->out,f->body,part,o->kind,"section",NULL); if(wrapper==SIZE_MAX) goto limit;
      for(i=0;i<o->attribute_count;i++)
        if(!exr_model_attribute(f->out,wrapper,o->attributes[i].name,o->attributes[i].value)) goto limit;
      f->body=wrapper;
    }
  }
  if(!clone_node(f->out,f->source,at,f->body,f->out->chapter_count-1,0)) goto limit;
  return EXR_OK;
limit: return exr_fail(f->error,EXR_LIMIT,"FB2 section model limit");
}
static exr_status split_fb2(exr_document **document,exr_error *e) {
  exr_document *old=*document,*d=EXR_NEW(exr_document); size_t i,index,body=SIZE_MAX;
  fb2_split f={d,old,0,SIZE_MAX,SIZE_MAX,e}; exr_status status=EXR_MEMORY;
  if(!d) return exr_fail(e,EXR_MEMORY,"FB2 section allocation failed");
  d->format=EXR_FB2; d->title=exr_model_copy(d,exr_document_title(old),strlen(exr_document_title(old)));
  if(!d->title) goto done;
  for(i=0;i<old->resource_count;i++) {
    status=exr_book_resource(d,old->resources[i].path,old->resources[i].media_type,
      old->resource_data[i].bytes,old->resource_data[i].size,&index,e);
    if(status!=EXR_OK) goto done;
    free((void *)d->resources[index].properties);
    d->resources[index].properties=exr_model_copy(d,old->resources[i].properties,strlen(old->resources[i].properties));
    if(!d->resources[index].properties) { status=EXR_MEMORY; goto done; }
  }
  for(i=0;i<old->node_count;i++) {
    const char *tag=exr_html_tag(old,&old->nodes[i]);
    if(!tag) continue;
    if(!strcmp(tag,"head")) f.head=i;
    if(!strcmp(tag,"body")) body=i;
  }
  if(body==SIZE_MAX) { status=EXR_FORMAT; goto done; }
  for(i=0;i<d->resource_count;i++) {
    size_t j,cover_body,image;
    if(strcmp(d->resources[i].properties,"cover-image")) continue;
    for(j=0;j<old->node_count;j++) {
      const char *src=exr_node_attribute(&old->nodes[j],"src");
      if(src && !strcmp(src,d->resources[i].path)) break;
    }
    if(j<old->node_count) continue;
    status=exr_book_chapter(d,&cover_body,e); if(status!=EXR_OK) goto done;
    image=exr_model_html(d,cover_body,0,EXR_NODE_IMAGE,"img",NULL);
    if(image==SIZE_MAX || !exr_model_attribute(d,image,"src",d->resources[i].path)) { status=EXR_LIMIT; goto done; }
    f.owner=SIZE_MAX-1;
    break;
  }
  status=split_walk(&f,body,SIZE_MAX,0); if(status!=EXR_OK) goto done;
  if(!d->chapter_count) { status=exr_fail(e,EXR_FORMAT,"FB2_EMPTY: no readable sections"); goto done; }
  /* Route note links and cross-section anchors through the shared href resolver. */
  for(i=0;i<d->node_count;i++) {
    const char *href=exr_node_attribute(&d->nodes[i],"href"); size_t j;
    if(!href || *href!='#') continue;
    for(j=0;j<d->node_count;j++) {
      const char *id=exr_node_attribute(&d->nodes[j],"id");
      if(id && !strcmp(id,href+1)) {
        exr_buffer path={0};
        if(!exr_append(&path,d->chapters[d->nodes[j].chapter].path,strlen(d->chapters[d->nodes[j].chapter].path)) ||
           !exr_append(&path,href,strlen(href)) || !exr_model_attribute(d,i,"href",path.data)) {
          free(path.data); status=EXR_LIMIT; goto done;
        }
        free(path.data); break;
      }
    }
  }
  status=exr_model_finish(d,e);
done:
  if(status!=EXR_OK) { exr_document_free(d); return status; }
  exr_document_free(old); *document=d; return EXR_OK;
}
static exr_status heading_navigation(exr_format_book *b,exr_error *e) {
  exr_document *d=b->index; size_t i,capacity=0,stack[256],levels[256],depth=0;
  for(i=0;i<d->node_count;i++) {
    exr_node *v=&d->nodes[i]; exr_navigation *n; char id[64],href[2048];
    const char *fb2_title=exr_node_attribute(v,"data-fb2-title"); size_t level=0;
    if((d->format==EXR_FB2 ? !fb2_title : v->kind!=EXR_NODE_HEADING) ||
        v->start==SIZE_MAX || v->end<=v->start) continue;
    if(fb2_title) level=(size_t)strtoul(fb2_title,NULL,10);
    if(b->navigation_count>=10000) return exr_fail(e,EXR_LIMIT,"Book navigation exceeds 10000 entries");
    if(!exr_grow((void **)&b->navigation,&capacity,b->navigation_count+1,sizeof(*n))) return EXR_MEMORY;
    n=&b->navigation[b->navigation_count++]; memset(n,0,sizeof(*n));
    snprintf(id,sizeof(id),"book-heading-%zu",i);
    { const char *existing=exr_node_attribute(v,"id");
      if(!existing && !exr_model_attribute(d,i,"id",id)) return EXR_LIMIT;
      snprintf(href,sizeof(href),"%s#%s",d->chapters[v->chapter].path,existing ? existing : id); }
    while(depth && levels[depth-1]>=level) depth--;
    n->parent=depth ? stack[depth-1] : SIZE_MAX;
    if(depth==256) return exr_fail(e,EXR_LIMIT,"FB2 navigation nesting exceeds limit");
    stack[depth]=b->navigation_count-1; levels[depth++]=level;
    n->part=v->chapter; n->label=exr_copy(d->text+v->start,v->end-v->start);
    n->href=exr_copy(href,strlen(href)); n->base=exr_copy("",0); n->role=exr_copy("toc",3);
    if(!n->label || !n->href || !n->base || !n->role) return EXR_MEMORY;
  }
  return EXR_OK;
}
void exr_book_free(void *context) {
  exr_format_book *b=context;
  if(!b) return;
  if(b->release) b->release(b->context);
  exr_document_free(b->index); exr_navigation_free(b->navigation,b->navigation_count); free(b);
}
exr_status exr_book_load(void *context,size_t part,exr_document **out,exr_error *e) {
  exr_format_book *b=context;
  return b->load(b->context,part,out,e);
}
exr_status exr_book_open(exr_format format,const void *data,size_t size,exr_format_book **out,exr_error *e) {
  exr_format_book *b; exr_status status;
  *out=NULL;
  if(!data || !size || size>EXR_MAX_INPUT) return exr_fail(e,size>EXR_MAX_INPUT ? EXR_LIMIT : EXR_ARGUMENT,"Invalid book bytes");
  b=calloc(1,sizeof(*b)); if(!b) return exr_fail(e,EXR_MEMORY,"Book index allocation failed");
  if(format==EXR_MOBI) status=exr_mobi_book(data,size,b,e);
  else {
    status=exr_document_open_memory(format,data,size,&b->index,e);
    if(status==EXR_OK && format==EXR_FB2) status=split_fb2(&b->index,e);
    b->context=b->index; b->load=exr_book_slice;
  }
  if(status==EXR_OK && !b->navigation_count) {
    status=exr_document_navigation(b->index,&b->navigation,&b->navigation_count,e);
    if(status==EXR_OK && !b->navigation_count && b->index->node_count) status=heading_navigation(b,e);
  }
  if(status!=EXR_OK) { exr_book_free(b); return status; }
  b->memory+=exr_document_memory_size(b->index);
  *out=b; return EXR_OK;
}
