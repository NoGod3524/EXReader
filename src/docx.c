/* SPDX-License-Identifier: GPL-3.0-only */
#include "internal.h"
#include <miniz.h>
#include <ctype.h>
#define W "http://schemas.openxmlformats.org/wordprocessingml/2006/main|"
#define WS "http://purl.oclc.org/ooxml/wordprocessingml/main|"
#define R "http://schemas.openxmlformats.org/officeDocument/2006/relationships|"
#define RS "http://purl.oclc.org/ooxml/officeDocument/relationships|"
typedef struct {
  const char *id,*type,*target;
  int external;
  size_t resource;
} relationship;
typedef struct { const char *id; size_t node; } word_style;
typedef struct { int start,restart,legal; const char *format,*pattern,*suffix; size_t properties; } number_level;
typedef struct { int id; size_t node; } number_abstract;
typedef struct {
  int id,abstract_id,counter[9]; unsigned started,valid;
  size_t node; number_level *levels;
} number_instance;
typedef struct { int id,endnote; size_t ordinal,first_reference; } note_entry;
typedef struct {
  exr_document *out,*xml,*rels_xml,*styles_xml;
  exr_member_read_fn read;
  void *context;
  relationship *rels;
  size_t rel_count;
  word_style *styles;
  size_t style_count,defaults,work;
  const char *default_paragraph,*default_character;
  note_entry *notes;
  size_t note_count,note_capacity,*note_slots,footnote_count,endnote_count,reference_count,current_note;
  exr_document *numbering_xml;
  number_abstract *abstracts;
  number_instance *numbers;
  size_t abstract_count,number_count;
  char numbering_path[2048];
  const char *marker,*marker_css;
  unsigned paragraph_decorations;
  char main[2048];
  exr_status status;
  exr_error *error;
} docx;
static int put(exr_buffer *b,const char *s) { return exr_append(b,s,strlen(s)); }
static const char *attr(const exr_node *v,const char *key) {
  char expanded[160]; const char *value;
  snprintf(expanded,sizeof(expanded),W "%s",key); value=exr_node_attribute(v,expanded);
  if(value) return value;
  snprintf(expanded,sizeof(expanded),WS "%s",key); value=exr_node_attribute(v,expanded);
  return value;
}
static const char *rattr(const exr_node *v,const char *key) {
  char expanded[160]; const char *value;
  snprintf(expanded,sizeof(expanded),R "%s",key); value=exr_node_attribute(v,expanded);
  if(value) return value;
  snprintf(expanded,sizeof(expanded),RS "%s",key); return exr_node_attribute(v,expanded);
}
static const char *local(const exr_node *v) {
  const char *p=v->name ? strrchr(v->name,'|') : NULL;
  return p ? p+1 : v->name ? v->name : "";
}
static int word(const exr_node *v,const char *tag) {
  return v->name && (!strncmp(v->name,W,sizeof(W)-1) || !strncmp(v->name,WS,sizeof(WS)-1)) && !strcmp(local(v),tag);
}
static size_t child(const exr_document *d,size_t node,const char *tag) {
  size_t i;
  if(node==SIZE_MAX) return SIZE_MAX;
  for(i=d->nodes[node].first_child;i!=SIZE_MAX;i=d->nodes[i].next_sibling)
    if(word(&d->nodes[i],tag)) return i;
  return SIZE_MAX;
}
static size_t root(const exr_document *d) { return d->nodes[d->chapters[0].root].first_child; }
static const char *value(const exr_document *d,size_t node,const char *tag) {
  node=child(d,node,tag); return node==SIZE_MAX ? NULL : attr(&d->nodes[node],"val");
}
static int on(const char *s) { return !s || (strcmp(s,"0") && strcmp(s,"false") && strcmp(s,"off")); }
static int number(const char *s,int *out) {
  char *end; long n;
  if(!s || !*s || strlen(s)>10) return 0;
  n=strtol(s,&end,10); if(*end || n < -10000000 || n > 10000000) return 0;
  *out=(int)n; return 1;
}
static int pixels(exr_buffer *b,const char *property,const char *s,float scale) {
  int n; char result[100];
  if(!number(s,&n)) return 1;
  snprintf(result,sizeof(result),"%s:%.4fpx;",property,n*scale); return put(b,result);
}
static int color(exr_buffer *b,const char *property,const char *s) {
  size_t i;
  if(!s || strlen(s)!=6) return 1;
  for(i=0;i<6;i++) if(!isxdigit((unsigned char)s[i])) return 1;
  return put(b,property) && put(b,":#") && put(b,s) && put(b,";");
}
static int family(exr_buffer *b,const char *s) {
  size_t i;
  if(!s || !*s) return 1;
  if(!put(b,"font-family:\"")) return 0;
  for(i=0;s[i];i++) {
    if((s[i]=='"' || s[i]=='\\') && !put(b,"\\")) return 0;
    if((unsigned char)s[i]<32) { if(!put(b," ")) return 0; }
    else if(!exr_append(b,s+i,1)) return 0;
  }
  return put(b,"\";");
}
static int properties(docx *x,const exr_document *d,size_t node,exr_buffer *css,int *heading) {
  size_t i; const char *s;
  if(node==SIZE_MAX) return 1;
  for(i=d->nodes[node].first_child;i!=SIZE_MAX;i=d->nodes[i].next_sibling) {
    const exr_node *v=&d->nodes[i];
    if(++x->work>20000000) { x->status=EXR_LIMIT; return 0; }
    s=attr(v,"val");
    if(word(v,"b")) { if(!put(css,on(s) ? "font-weight:bold;" : "font-weight:normal;")) return 0; }
    else if(word(v,"i")) { if(!put(css,on(s) ? "font-style:italic;" : "font-style:normal;")) return 0; }
    else if(word(v,"sz")) { if(!pixels(css,"font-size",s,2.0f/3)) return 0; }
    else if(word(v,"color")) { if(!color(css,"color",s)) return 0; }
    else if(word(v,"shd")) { if(!color(css,"background-color",attr(v,"fill"))) return 0; }
    else if(word(v,"rFonts")) {
      const char *font=attr(v,"ascii"); if(!font) font=attr(v,"hAnsi"); if(!font) font=attr(v,"eastAsia");
      if(!family(css,font)) return 0;
    } else if(word(v,"jc") && s) {
      if(!strcmp(s,"both")) s="justify";
      if(!strcmp(s,"left") || !strcmp(s,"right") || !strcmp(s,"center") || !strcmp(s,"justify") || !strcmp(s,"start") || !strcmp(s,"end"))
        if(!put(css,"text-align:") || !put(css,s) || !put(css,";")) return 0;
    } else if(word(v,"bidi")) { if(!put(css,on(s) ? "direction:rtl;" : "direction:ltr;")) return 0; }
    else if(word(v,"pageBreakBefore")) { if(!put(css,on(s) ? "break-before:page;" : "break-before:auto;")) return 0; }
    else if(word(v,"outlineLvl")) { int h; if(number(s,&h) && h>=0 && h<6) *heading=h+1; }
    else if(word(v,"spacing")) {
      int line;
      if(!pixels(css,"margin-top",attr(v,"before"),1.0f/15) || !pixels(css,"margin-bottom",attr(v,"after"),1.0f/15)) return 0;
      s=attr(v,"line");
      if(number(s,&line) && line>0) {
        char result[80]; const char *rule=attr(v,"lineRule");
        if(rule && strcmp(rule,"auto")) snprintf(result,sizeof(result),"line-height:%.4fpx;",line/15.0f);
        else snprintf(result,sizeof(result),"line-height:%.4f;",line/240.0f);
        if(!put(css,result)) return 0;
      }
    } else if(word(v,"ind")) {
      if(!pixels(css,"margin-left",attr(v,"left"),1.0f/15) || !pixels(css,"margin-right",attr(v,"right"),1.0f/15) ||
          !pixels(css,"text-indent",attr(v,"firstLine"),1.0f/15) || !pixels(css,"text-indent",attr(v,"hanging"),-1.0f/15)) return 0;
    }
    /* pPr/rPr may contain run defaults. */
    if(word(v,"rPr") && !properties(x,d,i,css,heading)) return 0;
  }
  return 1;
}
static int word_decorations(docx *x,const exr_document *d,size_t props,unsigned *flags) {
  size_t i;
  if(props==SIZE_MAX) return 1;
  for(i=d->nodes[props].first_child;i!=SIZE_MAX;i=d->nodes[i].next_sibling) {
    const exr_node *v=&d->nodes[i]; const char *s=attr(v,"val");
    if(++x->work>20000000) { x->status=EXR_LIMIT; return 0; }
    if(word(v,"u")) {
      if(on(s) && (!s || strcmp(s,"none"))) *flags|=EXR_GLYPH_UNDERLINE;
      else *flags&=~EXR_GLYPH_UNDERLINE;
    } else if(word(v,"strike") || word(v,"dstrike")) {
      if(on(s)) *flags|=EXR_GLYPH_STRIKE; else *flags&=~EXR_GLYPH_STRIKE;
    } else if(word(v,"rPr") && !word_decorations(x,d,i,flags)) return 0;
  }
  return 1;
}
static int rel_order(const void *a,const void *b) { return strcmp(((const relationship *)a)->id,((const relationship *)b)->id); }
static relationship *rel(docx *x,const char *id) {
  size_t lo=0,hi=x->rel_count;
  if(!id) return NULL;
  while(lo<hi) { size_t mid=lo+(hi-lo)/2; if(strcmp(x->rels[mid].id,id)<0) lo=mid+1; else hi=mid; }
  return lo<x->rel_count && !strcmp(x->rels[lo].id,id) ? &x->rels[lo] : NULL;
}
static int rel_type(const char *type,const char *wanted) {
  const char transitional[]="http://schemas.openxmlformats.org/officeDocument/2006/relationships/";
  const char strict[]="http://purl.oclc.org/ooxml/officeDocument/relationships/";
  return type && ((!strncmp(type,transitional,sizeof(transitional)-1) && !strcmp(type+sizeof(transitional)-1,wanted)) ||
      (!strncmp(type,strict,sizeof(strict)-1) && !strcmp(type+sizeof(strict)-1,wanted)));
}
static exr_status xml_read(docx *x,const char *path,const char *tag,int optional,exr_document **out) {
  void *data=NULL; size_t size=0; exr_status status;
  *out=NULL; status=x->read(x->context,path,optional,&data,&size,x->error);
  if(status==EXR_OK && data) status=exr_xml_memory_tree(data,size,tag,out,x->error);
  mz_free(data); return status;
}
static exr_status relations(docx *x,const char *path,exr_document **xml,relationship **out,size_t *count) {
  size_t i; exr_status status=xml_read(x,path,"Relationships",1,xml);
  *out=NULL; *count=0;
  if(status!=EXR_OK || !*xml) return status;
  {
    const char *ns=(*xml)->nodes[root(*xml)].name;
    if(!ns || strcmp(ns,"http://schemas.openxmlformats.org/package/2006/relationships|Relationships"))
      return exr_fail(x->error,EXR_FORMAT,"Invalid DOCX relationship namespace");
  }
  for(i=0;i<(*xml)->node_count;i++) if((*xml)->nodes[i].name && !strcmp((*xml)->nodes[i].name,"http://schemas.openxmlformats.org/package/2006/relationships|Relationship")) (*count)++;
  if(*count>10000) return exr_fail(x->error,EXR_LIMIT,"DOCX relationships exceed limit");
  if(*count) { *out=calloc(*count,sizeof(**out)); if(!*out) return EXR_MEMORY; }
  *count=0;
  for(i=0;i<(*xml)->node_count;i++) {
    const exr_node *v=&(*xml)->nodes[i]; relationship *r; const char *mode;
    if(!v->name || strcmp(v->name,"http://schemas.openxmlformats.org/package/2006/relationships|Relationship")) continue;
    r=&(*out)[(*count)++]; r->id=exr_node_attribute(v,"Id"); r->type=exr_node_attribute(v,"Type");
    r->target=exr_node_attribute(v,"Target"); mode=exr_node_attribute(v,"TargetMode");
    r->external=mode && !strcmp(mode,"External"); r->resource=SIZE_MAX;
    if(!r->id || !*r->id || !r->type || !r->target) return exr_fail(x->error,EXR_FORMAT,"Invalid DOCX relationship");
  }
  if(*count>1) qsort(*out,*count,sizeof(**out),rel_order);
  for(i=1;i<*count;i++) if(!strcmp((*out)[i-1].id,(*out)[i].id))
    return exr_fail(x->error,EXR_FORMAT,"Duplicate DOCX relationship ID");
  return EXR_OK;
}
static int target(docx *x,const relationship *r,char path[2048]) {
  const char *s=r->target;
  if(*s=='/') return exr_resolve_path("",s+1,path);
  return exr_resolve_path(x->main,s,path);
}
static int style_order(const void *a,const void *b) { return strcmp(((const word_style *)a)->id,((const word_style *)b)->id); }
static size_t style_find(docx *x,const char *id) {
  size_t lo=0,hi=x->style_count;
  if(!id) return SIZE_MAX;
  while(lo<hi) { size_t mid=lo+(hi-lo)/2; if(strcmp(x->styles[mid].id,id)<0) lo=mid+1; else hi=mid; }
  return lo<x->style_count && !strcmp(x->styles[lo].id,id) ? x->styles[lo].node : SIZE_MAX;
}
static int style_css(docx *x,const char *id,exr_buffer *css,int *heading,unsigned depth) {
  size_t at=style_find(x,id); const char *base;
  if(at==SIZE_MAX) return 1;
  if(depth>64) { x->status=exr_fail(x->error,EXR_FORMAT,"Cyclic or excessive DOCX style inheritance"); return 0; }
  base=value(x->styles_xml,at,"basedOn");
  return (!base || style_css(x,base,css,heading,depth+1)) &&
      properties(x,x->styles_xml,child(x->styles_xml,at,"pPr"),css,heading) &&
      properties(x,x->styles_xml,child(x->styles_xml,at,"rPr"),css,heading);
}
static int decoration_style(docx *x,const char *id,unsigned *flags,unsigned depth) {
  size_t node=style_find(x,id); const char *base;
  if(node==SIZE_MAX) return 1;
  if(depth>64) { x->status=EXR_FORMAT; return 0; }
  base=value(x->styles_xml,node,"basedOn");
  return (!base || decoration_style(x,base,flags,depth+1)) &&
      word_decorations(x,x->styles_xml,child(x->styles_xml,node,"pPr"),flags) &&
      word_decorations(x,x->styles_xml,child(x->styles_xml,node,"rPr"),flags);
}
static exr_status styles(docx *x) {
  size_t i,j=0; char path[2048]; const relationship *relationship=NULL;
  for(i=0;i<x->rel_count;i++) if(rel_type(x->rels[i].type,"styles")) { relationship=&x->rels[i]; break; }
  if(!relationship) return EXR_OK;
  if(relationship->external || !target(x,relationship,path)) return exr_fail(x->error,EXR_FORMAT,"Invalid DOCX styles target");
  x->status=xml_read(x,path,"styles",0,&x->styles_xml); if(x->status!=EXR_OK) return x->status;
  if(!word(&x->styles_xml->nodes[root(x->styles_xml)],"styles")) return EXR_FORMAT;
  for(i=0;i<x->styles_xml->node_count;i++) if(word(&x->styles_xml->nodes[i],"style")) x->style_count++;
  if(x->style_count>10000) return EXR_LIMIT;
  if(x->style_count) { x->styles=calloc(x->style_count,sizeof(*x->styles)); if(!x->styles) return EXR_MEMORY; }
  for(i=0;i<x->styles_xml->node_count;i++) {
    const exr_node *v=&x->styles_xml->nodes[i];
    if(word(v,"style")) {
      const char *id=attr(v,"styleId"); if(!id || !*id) return EXR_FORMAT;
      x->styles[j++]=(word_style){id,i};
      if(attr(v,"default") && on(attr(v,"default"))) {
        const char *type=attr(v,"type");
        if(type && !strcmp(type,"paragraph")) x->default_paragraph=id;
        else if(type && !strcmp(type,"character")) x->default_character=id;
      }
    }
  }
  if(x->style_count>1) qsort(x->styles,x->style_count,sizeof(*x->styles),style_order);
  for(i=1;i<x->style_count;i++) if(!strcmp(x->styles[i-1].id,x->styles[i].id)) return EXR_FORMAT;
  x->defaults=child(x->styles_xml,root(x->styles_xml),"docDefaults");
  return EXR_OK;
}
static size_t make(docx *x,size_t parent,exr_node_kind kind,const char *tag,const char *text) {
  size_t at=exr_model_html(x->out,parent,0,kind,tag,text);
  if(at==SIZE_MAX) x->status=EXR_LIMIT;
  return at;
}
static int set(docx *x,size_t node,const char *key,const char *value) {
  if(!exr_model_attribute(x->out,node,key,value)) { x->status=EXR_LIMIT; return 0; } return 1;
}
static int image(docx *x,size_t parent,const exr_node *blip,float width,float height) {
  const char *id=rattr(blip,"embed"); relationship *r; char path[2048],numbered[80];
  size_t at,i; void *data=NULL; size_t size=0;
  if(!id) id=rattr(blip,"link");
  if(!id) id=rattr(blip,"id"); /* VML imagedata. */
  if(!id) return 1;
  r=rel(x,id);
  if(!r || !rel_type(r->type,"image")) { x->status=exr_fail(x->error,EXR_FORMAT,"DOCX image relationship is missing"); return 0; }
  if(!r->external && r->resource==SIZE_MAX) {
    exr_resource *resources; exr_resource_data *encoded; const char *media="application/octet-stream",*extension;
    if(!target(x,r,path)) { x->status=EXR_FORMAT; return 0; }
    for(i=0;i<x->out->resource_count;i++) if(!strcmp(path,x->out->resources[i].path)) break;
    if(i<x->out->resource_count) r->resource=i;
    else {
      x->status=x->read(x->context,path,0,&data,&size,x->error); if(x->status!=EXR_OK) return 0;
      if(x->out->resource_count>=9996) { mz_free(data); x->status=EXR_LIMIT; return 0; }
      resources=realloc(x->out->resources,(i+1)*sizeof(*resources));
      if(!resources) { mz_free(data); x->status=EXR_MEMORY; return 0; } x->out->resources=resources;
      encoded=realloc(x->out->resource_data,(i+1)*sizeof(*encoded));
      if(!encoded) { mz_free(data); x->status=EXR_MEMORY; return 0; } x->out->resource_data=encoded;
      x->out->resource_count=x->out->resource_capacity=i+1; memset(&resources[i],0,sizeof(resources[i]));
      encoded[i]=(exr_resource_data){data,size};
      extension=strrchr(path,'.');
      if(extension) {
        char ext[16]; size_t k; for(k=0;k<sizeof(ext)-1 && extension[k];k++) ext[k]=(char)tolower((unsigned char)extension[k]); ext[k]=0;
        if(!strcmp(ext,".png")) media="image/png";
        else if(!strcmp(ext,".jpg") || !strcmp(ext,".jpeg")) media="image/jpeg";
        else if(!strcmp(ext,".gif")) media="image/gif";
        else if(!strcmp(ext,".bmp")) media="image/bmp";
        else if(!strcmp(ext,".svg")) media="image/svg+xml";
        else if(!strcmp(ext,".webp")) media="image/webp";
      }
      snprintf(numbered,sizeof(numbered),"image-%zu",i);
      resources[i].id=exr_model_copy(x->out,numbered,strlen(numbered)); resources[i].path=exr_model_copy(x->out,path,strlen(path));
      resources[i].media_type=exr_model_copy(x->out,media,strlen(media)); resources[i].properties=exr_model_copy(x->out,"",0);
      if(!resources[i].id || !resources[i].path || !resources[i].media_type || !resources[i].properties) { x->status=EXR_LIMIT; return 0; }
      r->resource=i;
    }
  }
  at=make(x,parent,EXR_NODE_IMAGE,"img",NULL); if(at==SIZE_MAX) return 0;
  {
    exr_buffer href={0}; int ok;
    ok=r->external ? put(&href,r->target) : exr_uri_path(&href,x->out->resources[r->resource].path);
    ok=ok && set(x,at,"src",href.data); free(href.data); if(!ok) return 0;
  }
  if(width>0 && height>0) {
    snprintf(numbered,sizeof(numbered),"%.4f",width); if(!set(x,at,"width",numbered)) return 0;
    snprintf(numbered,sizeof(numbered),"%.4f",height); if(!set(x,at,"height",numbered)) return 0;
  }
  return 1;
}
static size_t note_find(docx *x,int id,int endnote) {
  size_t slot=((unsigned)id*2654435761u+(unsigned)endnote*2246822519u)&16383u;
  if(!x->note_slots) {
    x->note_slots=calloc(16384,sizeof(*x->note_slots));
    if(!x->note_slots) { x->status=EXR_MEMORY; return SIZE_MAX; }
  }
  while(x->note_slots[slot]) {
    size_t at=x->note_slots[slot]-1;
    if(x->notes[at].id==id && x->notes[at].endnote==endnote) return at;
    slot=(slot+1)&16383u;
  }
  if(x->note_count>=10000 || !exr_grow((void **)&x->notes,&x->note_capacity,x->note_count+1,sizeof(*x->notes))) {
    x->status=EXR_LIMIT; return SIZE_MAX;
  }
  x->note_slots[slot]=x->note_count+1;
  x->notes[x->note_count]=(note_entry){id,endnote,endnote ? ++x->endnote_count : ++x->footnote_count,x->reference_count};
  return x->note_count++;
}
static int note_reference(docx *x,size_t parent,const exr_node *v,int endnote,int backlink) {
  size_t index,at; char id[100],href[100],label[48]; note_entry *entry; int source_id;
  if(backlink) {
    if(x->current_note==SIZE_MAX) { x->status=EXR_FORMAT; return 0; }
    index=x->current_note;
  } else {
    if(x->current_note!=SIZE_MAX || !number(attr(v,"id"),&source_id) || source_id<0) { x->status=EXR_FORMAT; return 0; }
    index=note_find(x,source_id,endnote); if(index==SIZE_MAX) return 0;
  }
  entry=&x->notes[index];
  if(backlink) {
    snprintf(href,sizeof(href),"#noteref-%s-%d-%zu",entry->endnote ? "endnote" : "footnote",entry->id,entry->first_reference);
  } else {
    snprintf(id,sizeof(id),"noteref-%s-%d-%zu",endnote ? "endnote" : "footnote",entry->id,x->reference_count++);
    snprintf(href,sizeof(href),"#%s-%d",endnote ? "endnote" : "footnote",entry->id);
  }
  at=make(x,parent,EXR_NODE_LINK,"a",NULL);
  if(at==SIZE_MAX || !set(x,at,"href",href) || !set(x,at,"role",backlink ? "doc-backlink" : "doc-noteref") ||
      (!backlink && !set(x,at,"id",id))) return 0;
  snprintf(label,sizeof(label),"%zu",entry->ordinal);
  return make(x,at,EXR_NODE_TEXT,NULL,label)!=SIZE_MAX;
}
static int relationship_path(const char *part,char path[2048]) {
  const char *slash=strrchr(part,'/'); size_t length=strlen(part),directory=slash ? (size_t)(slash-part)+1 : 0;
  if(length>2048-12) return 0;
  memcpy(path,part,directory); memcpy(path+directory,"_rels/",6);
  memcpy(path+directory+6,part+directory,length-directory); memcpy(path+length+6,".rels",6);
  return 1;
}
static int abstract_order(const void *a,const void *b) {
  int x=((const number_abstract *)a)->id,y=((const number_abstract *)b)->id; return x<y ? -1 : x>y;
}
static int instance_order(const void *a,const void *b) {
  int x=((const number_instance *)a)->id,y=((const number_instance *)b)->id; return x<y ? -1 : x>y;
}
static int numbering_read(docx *x) {
  size_t i; exr_document *d;
  if(x->numbering_xml) return 1;
  if(!x->numbering_path[0]) { x->status=exr_fail(x->error,EXR_FORMAT,"DOCX numbering relationship is missing"); return 0; }
  x->status=xml_read(x,x->numbering_path,"numbering",0,&x->numbering_xml); if(x->status!=EXR_OK) return 0;
  d=x->numbering_xml;
  if(!word(&d->nodes[root(d)],"numbering")) { x->status=EXR_FORMAT; return 0; }
  for(i=d->nodes[root(d)].first_child;i!=SIZE_MAX;i=d->nodes[i].next_sibling) {
    if(word(&d->nodes[i],"abstractNum")) x->abstract_count++;
    else if(word(&d->nodes[i],"num")) x->number_count++;
  }
  if(x->abstract_count>10000 || x->number_count>10000) { x->status=EXR_LIMIT; return 0; }
  x->abstracts=calloc(x->abstract_count ? x->abstract_count : 1,sizeof(*x->abstracts));
  x->numbers=calloc(x->number_count ? x->number_count : 1,sizeof(*x->numbers));
  if(!x->abstracts || !x->numbers) { x->status=EXR_MEMORY; return 0; }
  x->abstract_count=x->number_count=0;
  for(i=d->nodes[root(d)].first_child;i!=SIZE_MAX;i=d->nodes[i].next_sibling) {
    int id,abstract_id;
    if(word(&d->nodes[i],"abstractNum")) {
      if(!number(attr(&d->nodes[i],"abstractNumId"),&id) || id<0) goto invalid;
      x->abstracts[x->abstract_count++]=(number_abstract){id,i};
    } else if(word(&d->nodes[i],"num")) {
      number_instance *v=&x->numbers[x->number_count++];
      if(!number(attr(&d->nodes[i],"numId"),&id) || id<=0 || !number(value(d,i,"abstractNumId"),&abstract_id) || abstract_id<0) goto invalid;
      v->id=id; v->abstract_id=abstract_id; v->node=i;
    }
  }
  if(x->abstract_count>1) qsort(x->abstracts,x->abstract_count,sizeof(*x->abstracts),abstract_order);
  if(x->number_count>1) qsort(x->numbers,x->number_count,sizeof(*x->numbers),instance_order);
  for(i=1;i<x->abstract_count;i++) if(x->abstracts[i-1].id==x->abstracts[i].id) goto invalid;
  for(i=1;i<x->number_count;i++) if(x->numbers[i-1].id==x->numbers[i].id) goto invalid;
  return 1;
invalid:
  x->status=exr_fail(x->error,EXR_FORMAT,"Invalid or duplicate DOCX numbering ID"); return 0;
}
static int level_read(docx *x,size_t node,int level,number_level *out) {
  const exr_document *d=x->numbering_xml; const char *s; int n;
  *out=(number_level){1,level-1,0,"decimal",NULL,"tab",SIZE_MAX};
  if((s=value(d,node,"start"))) { if(!number(s,&out->start)) goto invalid; }
  if((s=value(d,node,"lvlRestart"))) {
    if(!number(s,&n) || n<0 || n>level) goto invalid;
    out->restart=n-1;
  }
  if((s=value(d,node,"numFmt"))) out->format=s;
  if((s=value(d,node,"lvlText"))) out->pattern=s;
  if((s=value(d,node,"suff"))) out->suffix=s;
  node=child(d,node,"isLgl");
  if(node!=SIZE_MAX) out->legal=on(attr(&d->nodes[node],"val"));
  return 1;
invalid:
  x->status=exr_fail(x->error,EXR_FORMAT,"Invalid DOCX numbering level"); return 0;
}
static number_instance *number_prepare(docx *x,int id) {
  size_t lo=0,hi,i,node; number_instance *out; unsigned seen=0; const exr_document *d;
  if(!numbering_read(x)) return NULL;
  hi=x->number_count;
  while(lo<hi) { size_t mid=lo+(hi-lo)/2; if(x->numbers[mid].id<id) lo=mid+1; else hi=mid; }
  if(lo==x->number_count || x->numbers[lo].id!=id) goto invalid;
  out=&x->numbers[lo]; if(out->levels) return out;
  lo=0; hi=x->abstract_count;
  while(lo<hi) { size_t mid=lo+(hi-lo)/2; if(x->abstracts[mid].id<out->abstract_id) lo=mid+1; else hi=mid; }
  if(lo==x->abstract_count || x->abstracts[lo].id!=out->abstract_id) goto invalid;
  out->levels=calloc(9,sizeof(*out->levels)); if(!out->levels) { x->status=EXR_MEMORY; return NULL; }
  d=x->numbering_xml; node=x->abstracts[lo].node;
  for(i=d->nodes[node].first_child;i!=SIZE_MAX;i=d->nodes[i].next_sibling) {
    int level;
    if(++x->work>20000000) { x->status=EXR_LIMIT; return NULL; }
    if(!word(&d->nodes[i],"lvl")) continue;
    if(!number(attr(&d->nodes[i],"ilvl"),&level) || level<0 || level>8 || (out->valid&(1u<<level))) goto invalid;
    if(!level_read(x,i,level,&out->levels[level])) return NULL;
    out->levels[level].properties=child(d,i,"rPr"); out->valid|=1u<<level;
  }
  for(i=d->nodes[out->node].first_child;i!=SIZE_MAX;i=d->nodes[i].next_sibling) {
    int level,start; size_t definition; const char *s;
    if(!word(&d->nodes[i],"lvlOverride")) continue;
    if(!number(attr(&d->nodes[i],"ilvl"),&level) || level<0 || level>8 || (seen&(1u<<level))) goto invalid;
    seen|=1u<<level; definition=child(d,i,"lvl");
    if(definition!=SIZE_MAX) {
      if(!level_read(x,definition,level,&out->levels[level])) return NULL;
      out->levels[level].properties=child(d,definition,"rPr"); out->valid|=1u<<level;
    }
    s=value(d,i,"startOverride");
    if(s) { if(!number(s,&start)) goto invalid; out->levels[level].start=start; }
  }
  return out;
invalid:
  x->status=exr_fail(x->error,EXR_FORMAT,"DOCX numbering instance or level is missing/invalid"); return NULL;
}
static int number_properties(docx *x,const exr_document *d,size_t props,int *id,int *level) {
  const char *s; int n;
  props=child(d,props,"numPr"); if(props==SIZE_MAX) return 1;
  if((s=value(d,props,"numId"))) { if(!number(s,&n) || n<0) goto invalid; *id=n; }
  if((s=value(d,props,"ilvl"))) { if(!number(s,&n) || n<0 || n>8) goto invalid; *level=n; }
  return 1;
invalid:
  x->status=EXR_FORMAT; return 0;
}
static int number_style(docx *x,const char *id,int *num,int *level,unsigned depth) {
  size_t node=style_find(x,id); const char *base;
  if(node==SIZE_MAX) return 1;
  if(depth>64) { x->status=EXR_FORMAT; return 0; }
  if(++x->work>20000000) { x->status=EXR_LIMIT; return 0; }
  base=value(x->styles_xml,node,"basedOn");
  return (!base || number_style(x,base,num,level,depth+1)) &&
      number_properties(x,x->styles_xml,child(x->styles_xml,node,"pPr"),num,level);
}
static int paragraph_number(docx *x,size_t node,int *id,int *level) {
  size_t props; const char *style;
  *id=*level=0;
  if(!word(&x->xml->nodes[node],"p")) return 1;
  props=child(x->xml,node,"pPr"); style=value(x->xml,props,"pStyle");
  if(!style) style=x->default_paragraph;
  return (!style || number_style(x,style,id,level,0)) && number_properties(x,x->xml,props,id,level);
}
static int counter_text(docx *x,exr_buffer *out,int number_value,const char *format) {
  char text[100]; int n=number_value;
  if(!strcmp(format,"decimal") || !strcmp(format,"decimalZero") ||
      (n<=0 && (!strcmp(format,"lowerLetter") || !strcmp(format,"upperLetter") || !strcmp(format,"lowerRoman") || !strcmp(format,"upperRoman")))) {
    snprintf(text,sizeof(text),!strcmp(format,"decimalZero") ? "%02d" : "%d",n); return put(out,text);
  }
  if(!strcmp(format,"lowerLetter") || !strcmp(format,"upperLetter")) {
    size_t used=0; int upper=!strcmp(format,"upperLetter");
    while(n>0) { text[used++]=(char)((upper ? 'A' : 'a')+(n-1)%26); n=(n-1)/26; }
    while(used) if(!exr_append(out,&text[--used],1)) return 0;
    return 1;
  }
  if(!strcmp(format,"lowerRoman") || !strcmp(format,"upperRoman")) {
    const int values[]={1000,900,500,400,100,90,50,40,10,9,5,4,1};
    const char *labels[]={"M","CM","D","CD","C","XC","L","XL","X","IX","V","IV","I"};
    size_t i;
    if(n>3999) { snprintf(text,sizeof(text),"%d",n); return put(out,text); }
    for(i=0;i<13;i++) while(n>=values[i]) {
      const char *p=labels[i]; n-=values[i];
      while(*p) { char c=!strcmp(format,"lowerRoman") ? (char)tolower((unsigned char)*p) : *p; if(!exr_append(out,&c,1)) return 0; p++; }
    }
    return 1;
  }
  x->status=exr_fail(x->error,EXR_FORMAT,"Unsupported DOCX numbering format: %.80s",format); return 0;
}
static int number_label(docx *x,number_instance *instance,int level,exr_buffer *text,exr_buffer *css) {
  number_level *definition=&instance->levels[level]; const char *p=definition->pattern; size_t i; int dummy=0;
  if(!(instance->valid&(1u<<level))) { x->status=EXR_FORMAT; return 0; }
  if(instance->started&(1u<<level)) instance->counter[level]++;
  else { instance->counter[level]=definition->start; instance->started|=1u<<level; }
  for(i=(size_t)level+1;i<9;i++) if(instance->levels[i].restart>=level) instance->started&=~(1u<<i);
  if(!strcmp(definition->format,"none")) return 1;
  if(p) {
    if(strlen(p)>4096) { x->status=EXR_LIMIT; return 0; }
    for(i=0;p[i];i++) {
      if(p[i]=='%' && p[i+1]>='1' && p[i+1]<='9') {
        unsigned reference=(unsigned)(p[++i]-'1'); number_level *ref=&instance->levels[reference];
        if(!(instance->valid&(1u<<reference))) { x->status=EXR_FORMAT; return 0; }
        if(!counter_text(x,text,instance->started&(1u<<reference) ? instance->counter[reference] : ref->start,definition->legal ? "decimal" : ref->format)) return 0;
      } else if(!exr_append(text,p+i,1)) return 0;
    }
  } else if(!strcmp(definition->format,"bullet")) { if(!put(text,"\xe2\x80\xa2")) return 0; }
  else if(!counter_text(x,text,instance->counter[level],definition->format) || !put(text,".")) return 0;
  if(text->size && strcmp(definition->suffix,"nothing") && !put(text,!strcmp(definition->suffix,"space") ? " " : "\t")) return 0;
  return properties(x,x->numbering_xml,definition->properties,css,&dummy);
}
static int content(docx *x,size_t parent,size_t source,unsigned depth);
static int children(docx *x,size_t parent,size_t source,unsigned depth) {
  struct { size_t list,item; int id; } stack[9];
  size_t active=0,i; int id,level;
  for(i=x->xml->nodes[source].first_child;i!=SIZE_MAX;i=x->xml->nodes[i].next_sibling) {
    exr_buffer label={0},css={0}; size_t destination=parent,k; int ok;
    if(!paragraph_number(x,i,&id,&level)) return 0;
    if(id) {
      number_instance *instance=number_prepare(x,id);
      if(!instance || !number_label(x,instance,level,&label,&css)) { free(label.data); free(css.data); if(x->status==EXR_OK) x->status=EXR_LIMIT; return 0; }
      for(k=0;k<=(size_t)level;k++) {
        if(k>=active || stack[k].id!=id) {
          int ordered=strcmp(instance->levels[k].format ? instance->levels[k].format : "decimal","bullet") &&
              strcmp(instance->levels[k].format ? instance->levels[k].format : "decimal","none");
          char value[48];
          stack[k].list=make(x,k ? stack[k-1].item : parent,EXR_NODE_LIST,ordered ? "ol" : "ul",NULL);
          if(stack[k].list==SIZE_MAX || !set(x,stack[k].list,"style","list-style-type:none")) goto failed;
          if(ordered) {
            snprintf(value,sizeof(value),"%d",instance->started&(1u<<k) ? instance->counter[k] : instance->levels[k].start);
            if(!set(x,stack[k].list,"start",value)) goto failed;
          }
          stack[k].id=id; stack[k].item=SIZE_MAX; active=k+1;
        }
        if(k<(size_t)level && stack[k].item==SIZE_MAX) {
          stack[k].item=make(x,stack[k].list,EXR_NODE_LIST_ITEM,"li",NULL); if(stack[k].item==SIZE_MAX) goto failed;
        }
      }
      stack[level].item=make(x,stack[level].list,EXR_NODE_LIST_ITEM,"li",NULL); if(stack[level].item==SIZE_MAX) goto failed;
      active=(size_t)level+1; destination=stack[level].item;
      x->marker=label.data; x->marker_css=css.data;
    } else active=0;
    ok=content(x,destination,i,depth); x->marker=x->marker_css=NULL;
    free(label.data); free(css.data); if(!ok) return 0;
    continue;
failed:
    free(label.data); free(css.data); if(x->status==EXR_OK) x->status=EXR_LIMIT; return 0;
  }
  return 1;
}
static size_t alternate(const exr_document *d,size_t source) {
  size_t i,choice=SIZE_MAX;
  if(!d->nodes[source].name || strcmp(d->nodes[source].name,"http://schemas.openxmlformats.org/markup-compatibility/2006|AlternateContent")) return SIZE_MAX;
  for(i=d->nodes[source].first_child;i!=SIZE_MAX;i=d->nodes[i].next_sibling) {
    const char *name=d->nodes[i].name;
    if(name && !strcmp(name,"http://schemas.openxmlformats.org/markup-compatibility/2006|Fallback")) return i;
    if(choice==SIZE_MAX && name && !strcmp(name,"http://schemas.openxmlformats.org/markup-compatibility/2006|Choice")) choice=i;
  }
  return choice;
}
static int drawing_images(docx *x,size_t parent,size_t source,float width,float height,unsigned depth) {
  size_t i,selected=alternate(x->xml,source); const exr_node *v=&x->xml->nodes[source];
  if(depth>250 || ++x->work>20000000) { x->status=EXR_LIMIT; return 0; }
  if(!strcmp(local(v),"blip") || !strcmp(local(v),"imagedata")) return image(x,parent,v,width,height);
  if(selected!=SIZE_MAX) return drawing_images(x,parent,selected,width,height,depth+1);
  for(i=v->first_child;i!=SIZE_MAX;i=x->xml->nodes[i].next_sibling)
    if(!drawing_images(x,parent,i,width,height,depth+1)) return 0;
  return 1;
}
static int drawing(docx *x,size_t parent,size_t source,unsigned depth) {
  const exr_node *v=&x->xml->nodes[source]; size_t i,end=v->next_sibling,ancestor=v->parent;
  float width=0,height=0;
  if(depth>250) { x->status=EXR_LIMIT; return 0; }
  while(end==SIZE_MAX && ancestor!=SIZE_MAX) {
    end=x->xml->nodes[ancestor].next_sibling; ancestor=x->xml->nodes[ancestor].parent;
  }
  if(end==SIZE_MAX) end=x->xml->node_count;
  for(i=source+1;i<end;i++) if(!strcmp(local(&x->xml->nodes[i]),"extent")) {
    int cx,cy;
    if(number(exr_node_attribute(&x->xml->nodes[i],"cx"),&cx) && number(exr_node_attribute(&x->xml->nodes[i],"cy"),&cy)) {
      width=cx/9525.0f; height=cy/9525.0f; break;
    }
  }
  return drawing_images(x,parent,source,width,height,depth);

}
static int gap(docx *x,size_t row,size_t count) {
  size_t at; char number[48];
  if(!count) return 1;
  at=make(x,row,EXR_NODE_CELL,"td",NULL); if(at==SIZE_MAX) return 0;
  if(count>1) { snprintf(number,sizeof(number),"%zu",count); if(!set(x,at,"colspan",number)) return 0; }
  return 1;
}
static int table(docx *x,size_t parent,size_t source,unsigned depth) {
  size_t at=make(x,parent,EXR_NODE_TABLE,"table",NULL),row,cell,owner[256],span[256],rows[256],i;
  if(at==SIZE_MAX) return 0;
  for(i=0;i<256;i++) { owner[i]=SIZE_MAX; span[i]=rows[i]=0; }
  for(row=x->xml->nodes[source].first_child;row!=SIZE_MAX;row=x->xml->nodes[row].next_sibling) if(word(&x->xml->nodes[row],"tr")) {
    size_t tr=make(x,at,EXR_NODE_ROW,"tr",NULL),column=0; unsigned char touched[256]={0};
    if(tr==SIZE_MAX) return 0;
    {
      int before=0; const char *s=value(x->xml,child(x->xml,row,"trPr"),"gridBefore");
      if(s && (!number(s,&before) || before<0 || before>256)) goto invalid;
      if(!gap(x,tr,(size_t)before)) return 0;
      column=(size_t)before;
    }
    for(cell=x->xml->nodes[row].first_child;cell!=SIZE_MAX;cell=x->xml->nodes[cell].next_sibling) if(word(&x->xml->nodes[cell],"tc")) {
      size_t properties_node=child(x->xml,cell,"tcPr"),merge=child(x->xml,properties_node,"vMerge"),td,k;
      int columns=1; const char *merge_value=merge==SIZE_MAX ? NULL : attr(&x->xml->nodes[merge],"val"); char value_buffer[48];
      const char *grid=value(x->xml,properties_node,"gridSpan");
      if(grid && (!number(grid,&columns) || columns<1)) goto invalid;
      if(columns>256 || column+(size_t)columns>256) { x->status=EXR_LIMIT; return 0; }
      if(merge!=SIZE_MAX && (!merge_value || !strcmp(merge_value,"continue"))) {
        td=owner[column]; if(td==SIZE_MAX || span[column]!=(size_t)columns) goto invalid;
        for(k=column;k<column+(size_t)columns;k++) if(owner[k]!=td) goto invalid;
        rows[column]++; snprintf(value_buffer,sizeof(value_buffer),"%zu",rows[column]); if(!set(x,td,"rowspan",value_buffer)) return 0;
      } else {
        if(merge_value && strcmp(merge_value,"restart")) goto invalid;
        td=make(x,tr,EXR_NODE_CELL,"td",NULL); if(td==SIZE_MAX) return 0;
        if(columns>1) { snprintf(value_buffer,sizeof(value_buffer),"%d",columns); if(!set(x,td,"colspan",value_buffer)) return 0; }
        for(k=column;k<column+(size_t)columns;k++) { owner[k]=merge==SIZE_MAX ? SIZE_MAX : td; span[k]=(size_t)columns; rows[k]=1; }
      }
      for(k=column;k<column+(size_t)columns;k++) touched[k]=1;
      if(!children(x,td,cell,depth+1)) return 0;
      column+=(size_t)columns;
    }
    {
      int after=0; const char *s=value(x->xml,child(x->xml,row,"trPr"),"gridAfter");
      if(s && (!number(s,&after) || after<0 || column+(size_t)after>256)) goto invalid;
      if(!gap(x,tr,(size_t)after)) return 0;
    }
    for(i=0;i<256;i++) if(!touched[i]) owner[i]=SIZE_MAX;
  }
  return 1;
invalid:
  x->status=exr_fail(x->error,EXR_FORMAT,"Invalid DOCX table merge"); return 0;
}
static int content(docx *x,size_t parent,size_t source,unsigned depth) {
  const exr_node *v=&x->xml->nodes[source]; size_t at=parent,i,props; exr_buffer css={0}; int heading=0,ok=0;
  unsigned saved_decorations=x->paragraph_decorations;
  if(depth>250) { x->status=EXR_LIMIT; return 0; }
  i=alternate(x->xml,source);
  if(i!=SIZE_MAX) return content(x,parent,i,depth+1);
  if(v->kind==EXR_NODE_TEXT) return 1; /* Only w:t/instrText carry Word text. */
  if(word(v,"pPr") || word(v,"rPr") || word(v,"tcPr") || word(v,"trPr") || word(v,"tblPr") || word(v,"sectPr") ||
      word(v,"del") || word(v,"instrText")) return 1;
  if(word(v,"footnoteReference") || word(v,"endnoteReference")) return note_reference(x,parent,v,word(v,"endnoteReference"),0);
  if(word(v,"footnoteRef") || word(v,"endnoteRef")) return note_reference(x,parent,v,word(v,"endnoteRef"),1);
  if(word(v,"tbl")) return table(x,parent,source,depth+1);
  if(word(v,"drawing") || word(v,"pict")) return drawing(x,parent,source,depth+1);
  if(word(v,"t")) {
    for(i=v->first_child;i!=SIZE_MAX;i=x->xml->nodes[i].next_sibling)
      if(x->xml->nodes[i].kind==EXR_NODE_TEXT && make(x,parent,EXR_NODE_TEXT,NULL,x->xml->nodes[i].text)==SIZE_MAX) return 0;
    return 1;
  }
  if(word(v,"p") || word(v,"r")) {
    int paragraph=word(v,"p"); const char *style;
    unsigned decorations=paragraph ? 0 : x->paragraph_decorations;
    props=child(x->xml,source,paragraph ? "pPr" : "rPr");
    if(paragraph && x->styles_xml && x->defaults!=SIZE_MAX) {
      i=child(x->styles_xml,x->defaults,"pPrDefault");
      if(!properties(x,x->styles_xml,child(x->styles_xml,i,"pPr"),&css,&heading)) goto done;
      i=child(x->styles_xml,x->defaults,"rPrDefault");
      if(!properties(x,x->styles_xml,child(x->styles_xml,i,"rPr"),&css,&heading) ||
          !word_decorations(x,x->styles_xml,child(x->styles_xml,i,"rPr"),&decorations)) goto done;
    }
    style=value(x->xml,props,paragraph ? "pStyle" : "rStyle");
    if(!style) style=paragraph ? x->default_paragraph : x->default_character;
    if(style && (!style_css(x,style,&css,&heading,0) || !decoration_style(x,style,&decorations,0))) goto done;
    if(paragraph && !heading && style && !strncmp(style,"Heading",7) && style[7]>='1' && style[7]<='6' && !style[8]) heading=style[7]-'0';
    if(!properties(x,x->xml,props,&css,&heading) || !word_decorations(x,x->xml,props,&decorations)) goto done;
    if(paragraph) x->paragraph_decorations=decorations;
    if(paragraph) {
      char tag[4]="p"; if(heading) { tag[0]='h'; tag[1]=(char)('0'+heading); tag[2]=0; }
      at=make(x,parent,heading ? EXR_NODE_HEADING : EXR_NODE_PARAGRAPH,tag,NULL);
    } else at=make(x,parent,EXR_NODE_ELEMENT,"span",NULL);
    if(at==SIZE_MAX || (css.size && !set(x,at,"style",css.data))) goto done;
    if(paragraph && x->marker) {
      size_t marker=make(x,at,EXR_NODE_ELEMENT,"span",NULL);
      if(marker==SIZE_MAX || !set(x,marker,"role","presentation") || !set(x,marker,"aria-hidden","true") ||
          (x->marker_css && !set(x,marker,"style",x->marker_css)) || make(x,marker,EXR_NODE_TEXT,NULL,x->marker)==SIZE_MAX) goto done;
      x->marker=x->marker_css=NULL;
    }
    if(!paragraph && (decorations&EXR_GLYPH_UNDERLINE)) { at=make(x,at,EXR_NODE_ELEMENT,"u",NULL); if(at==SIZE_MAX) goto done; }
    if(!paragraph && (decorations&EXR_GLYPH_STRIKE)) { at=make(x,at,EXR_NODE_ELEMENT,"s",NULL); if(at==SIZE_MAX) goto done; }
  } else if(word(v,"hyperlink")) {
    const char *id=rattr(v,"id"),*anchor=attr(v,"anchor"); relationship *r=rel(x,id); char path[2048]; exr_buffer href={0};
    at=make(x,parent,EXR_NODE_LINK,"a",NULL); if(at==SIZE_MAX) goto done;
    if(id && (!r || !rel_type(r->type,"hyperlink"))) { x->status=EXR_FORMAT; goto done; }
    if(r) {
      if(r->external) ok=put(&href,r->target);
      else if(target(x,r,path)) {
        const char *fragment=strchr(r->target,'#');
        ok=exr_uri_path(&href,!strcmp(path,x->main) ? "document.xhtml" : path);
        if(ok && fragment && !anchor) ok=put(&href,"#bookmark-") && put(&href,fragment+1);
      }
      if(!ok) { free(href.data); x->status=EXR_FORMAT; goto done; }
    }
    if(anchor && (!put(&href,"#bookmark-") || !exr_uri_path(&href,anchor))) { free(href.data); goto done; }
    ok=!href.size || set(x,at,"href",href.data); free(href.data); if(!ok) goto done;
    ok=0;
  } else if(word(v,"bookmarkStart")) {
    const char *name=attr(v,"name");
    if(name) {
      exr_buffer id={0}; int valid=put(&id,"bookmark-") && put(&id,name);
      at=make(x,parent,EXR_NODE_ELEMENT,"span",NULL);
      valid=valid && at!=SIZE_MAX && set(x,at,"id",id.data); free(id.data); if(!valid) goto done;
    }
  } else if(word(v,"tab")) return make(x,parent,EXR_NODE_TEXT,NULL,"\t")!=SIZE_MAX;
  else if(word(v,"br") || word(v,"cr")) {
    const char *type=attr(v,"type"); int page=type && !strcmp(type,"page");
    at=make(x,parent,page ? EXR_NODE_SECTION : EXR_NODE_BREAK,page ? "div" : "br",NULL);
    return at!=SIZE_MAX && (!page || set(x,at,"style","break-before:page"));
  }
  if(!children(x,at,source,depth+1)) goto done;
  ok=1;
done:
  x->paragraph_decorations=saved_decorations;
  free(css.data);
  if(!ok && x->status==EXR_OK) x->status=EXR_LIMIT;
  return ok;
}
typedef struct { int id; size_t node; } source_note;
static int note_order(const void *a,const void *b) {
  int x=((const source_note *)a)->id,y=((const source_note *)b)->id;
  return x<y ? -1 : x>y;
}
static int append_notes(docx *x,size_t body,int endnote) {
  exr_document *source=NULL,*rels_xml=NULL,*old_xml=x->xml,*old_rels_xml=x->rels_xml;
  relationship *rels=NULL,*old_rels=x->rels; source_note *entries=NULL;
  size_t count=0,rel_count=0,old_rel_count=x->rel_count,i,section=SIZE_MAX;
  char path[2048],relpath[2048],old_main[2048]; const relationship *part=NULL; int ok=0;
  if(!(endnote ? x->endnote_count : x->footnote_count)) return 1;
  for(i=0;i<x->rel_count;i++) if(rel_type(x->rels[i].type,endnote ? "endnotes" : "footnotes")) { part=&x->rels[i]; break; }
  if(!part || part->external || !target(x,part,path) || !relationship_path(path,relpath)) {
    x->status=exr_fail(x->error,EXR_FORMAT,"Referenced DOCX notes part is missing or invalid"); return 0;
  }
  x->status=xml_read(x,path,endnote ? "endnotes" : "footnotes",0,&source); if(x->status!=EXR_OK) goto done;
  if(!word(&source->nodes[root(source)],endnote ? "endnotes" : "footnotes")) { x->status=EXR_FORMAT; goto done; }
  for(i=source->nodes[root(source)].first_child;i!=SIZE_MAX;i=source->nodes[i].next_sibling)
    if(word(&source->nodes[i],endnote ? "endnote" : "footnote")) count++;
  if(count>10000) { x->status=EXR_LIMIT; goto done; }
  entries=calloc(count ? count : 1,sizeof(*entries)); if(!entries) { x->status=EXR_MEMORY; goto done; }
  count=0;
  for(i=source->nodes[root(source)].first_child;i!=SIZE_MAX;i=source->nodes[i].next_sibling) {
    const exr_node *v=&source->nodes[i]; const char *type=attr(v,"type"); int id;
    if(!word(v,endnote ? "endnote" : "footnote")) continue;
    if(type && strcmp(type,"normal")) continue;
    if(!number(attr(v,"id"),&id) || id<0) { x->status=EXR_FORMAT; goto done; }
    entries[count++]=(source_note){id,i};
  }
  if(count>1) qsort(entries,count,sizeof(*entries),note_order);
  for(i=1;i<count;i++) if(entries[i-1].id==entries[i].id) { x->status=EXR_FORMAT; goto done; }
  x->status=relations(x,relpath,&rels_xml,&rels,&rel_count); if(x->status!=EXR_OK) goto done;
  strcpy(old_main,x->main); strcpy(x->main,path);
  x->xml=source; x->rels=rels; x->rels_xml=rels_xml; x->rel_count=rel_count;
  section=make(x,body,EXR_NODE_SECTION,"section",NULL);
  if(section==SIZE_MAX || !set(x,section,"role","doc-endnotes")) goto restore;
  for(i=0;i<x->note_count;i++) if(x->notes[i].endnote==endnote) {
    size_t lo=0,hi=count,note; char id[80];
    while(lo<hi) { size_t mid=lo+(hi-lo)/2; if(entries[mid].id<x->notes[i].id) lo=mid+1; else hi=mid; }
    if(lo==count || entries[lo].id!=x->notes[i].id) { x->status=exr_fail(x->error,EXR_FORMAT,"DOCX note reference has no body"); goto restore; }
    note=make(x,section,EXR_NODE_NOTE,"aside",NULL); if(note==SIZE_MAX) goto restore;
    snprintf(id,sizeof(id),"%s-%d",endnote ? "endnote" : "footnote",x->notes[i].id);
    if(!set(x,note,"id",id) || !set(x,note,"role",endnote ? "doc-endnote" : "doc-footnote")) goto restore;
    x->current_note=i;
    if(!children(x,note,entries[lo].node,0)) { if(x->status==EXR_OK) x->status=EXR_LIMIT; goto restore; }
  }
  ok=1;
restore:
  strcpy(x->main,old_main); x->xml=old_xml; x->rels=old_rels; x->rels_xml=old_rels_xml; x->rel_count=old_rel_count;
  x->current_note=SIZE_MAX;
done:
  free(entries); free(rels); exr_document_free(source); exr_document_free(rels_xml); return ok;
}
exr_status exr_docx(exr_document *d,exr_member_read_fn read,void *context,exr_error *e) {
  docx x={0}; exr_document *package=NULL; relationship *package_rels=NULL; size_t package_count=0;
  size_t i,body,chapter,html,head,title,out_body; char relpath[2048];
  x.out=d; x.read=read; x.context=context; x.error=e; x.defaults=x.current_note=SIZE_MAX; strcpy(x.main,"word/document.xml");
  x.status=relations(&x,"_rels/.rels",&package,&package_rels,&package_count); if(x.status!=EXR_OK) goto done;
  for(i=0;i<package_count;i++) if(rel_type(package_rels[i].type,"officeDocument")) {
    const char *target=package_rels[i].target;
    if(*target=='/') target++;
    if(package_rels[i].external || !exr_resolve_path("",target,x.main)) { x.status=EXR_FORMAT; goto done; }
    break;
  }
  x.status=xml_read(&x,x.main,"document",0,&x.xml); if(x.status!=EXR_OK) goto done;
  if(!word(&x.xml->nodes[root(x.xml)],"document")) { x.status=EXR_FORMAT; goto done; }
  body=child(x.xml,root(x.xml),"body"); if(body==SIZE_MAX) { x.status=EXR_FORMAT; goto done; }
  if(!relationship_path(x.main,relpath)) { x.status=EXR_LIMIT; goto done; }
  x.status=relations(&x,relpath,&x.rels_xml,&x.rels,&x.rel_count); if(x.status!=EXR_OK) goto done;
  x.status=styles(&x); if(x.status!=EXR_OK) goto done;
  for(i=0;i<x.rel_count;i++) if(rel_type(x.rels[i].type,"numbering")) {
    if(x.rels[i].external || !target(&x,&x.rels[i],x.numbering_path)) { x.status=EXR_FORMAT; goto done; }
    break;
  }
  if(exr_model_node(d,SIZE_MAX,SIZE_MAX,EXR_NODE_DOCUMENT,NULL,NULL,0)==SIZE_MAX) { x.status=EXR_LIMIT; goto done; }
  chapter=make(&x,0,EXR_NODE_CHAPTER,NULL,NULL); if(chapter==SIZE_MAX) goto done;
  d->chapters=calloc(1,sizeof(*d->chapters)); if(!d->chapters) { x.status=EXR_MEMORY; goto done; }
  d->chapter_count=d->chapter_capacity=1;
  /* The semantic chapter is at the package root so extracted asset paths stay valid. */
  d->chapters[0]=(exr_chapter){"main","document.xhtml",chapter,SIZE_MAX,1,1};
  html=make(&x,chapter,EXR_NODE_ELEMENT,"html",NULL); if(html==SIZE_MAX) goto done;
  head=make(&x,html,EXR_NODE_ELEMENT,"head",NULL); if(head==SIZE_MAX) goto done;
  title=make(&x,head,EXR_NODE_ELEMENT,"title",NULL); if(title==SIZE_MAX) goto done;
  if(make(&x,title,EXR_NODE_TEXT,NULL,d->title ? d->title : "Untitled")==SIZE_MAX) goto done;
  out_body=make(&x,html,EXR_NODE_ELEMENT,"body",NULL); if(out_body==SIZE_MAX) goto done;
  if(!children(&x,out_body,body,0) && x.status==EXR_OK) x.status=EXR_LIMIT;
  if(x.status==EXR_OK && (!append_notes(&x,out_body,0) || !append_notes(&x,out_body,1)) && x.status==EXR_OK) x.status=EXR_LIMIT;
done:
  for(i=0;i<x.number_count;i++) free(x.numbers ? x.numbers[i].levels : NULL);
  free(x.numbers); free(x.abstracts); exr_document_free(x.numbering_xml);
  free(x.notes); free(x.note_slots);
  free(package_rels); exr_document_free(package); free(x.rels); free(x.styles);
  exr_document_free(x.xml); exr_document_free(x.rels_xml); exr_document_free(x.styles_xml);
  if(x.status!=EXR_OK && (!e || !e->message[0])) exr_fail(e,x.status,"DOCX structure rejected");
  return x.status;
}
