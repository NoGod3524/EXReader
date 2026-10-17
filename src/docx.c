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
typedef struct {
  exr_document *out,*xml,*rels_xml,*styles_xml;
  exr_member_read_fn read;
  void *context;
  relationship *rels;
  size_t rel_count;
  word_style *styles;
  size_t style_count,defaults,work;
  const char *default_paragraph,*default_character;
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
      resources[i].id=exr_model_copy(x->out,r->id,strlen(r->id)); resources[i].path=exr_model_copy(x->out,path,strlen(path));
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
static int content(docx *x,size_t parent,size_t source,unsigned depth);
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
      for(k=x->xml->nodes[cell].first_child;k!=SIZE_MAX;k=x->xml->nodes[k].next_sibling)
        if(!content(x,td,k,depth+1)) return 0;
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
  if(depth>250) { x->status=EXR_LIMIT; return 0; }
  i=alternate(x->xml,source);
  if(i!=SIZE_MAX) return content(x,parent,i,depth+1);
  if(v->kind==EXR_NODE_TEXT) return 1; /* Only w:t/instrText carry Word text. */
  if(word(v,"pPr") || word(v,"rPr") || word(v,"tcPr") || word(v,"trPr") || word(v,"tblPr") || word(v,"sectPr") ||
      word(v,"del") || word(v,"instrText")) return 1;
  if(word(v,"tbl")) return table(x,parent,source,depth+1);
  if(word(v,"drawing") || word(v,"pict")) return drawing(x,parent,source,depth+1);
  if(word(v,"t")) {
    for(i=v->first_child;i!=SIZE_MAX;i=x->xml->nodes[i].next_sibling)
      if(x->xml->nodes[i].kind==EXR_NODE_TEXT && make(x,parent,EXR_NODE_TEXT,NULL,x->xml->nodes[i].text)==SIZE_MAX) return 0;
    return 1;
  }
  if(word(v,"p") || word(v,"r")) {
    int paragraph=word(v,"p"); const char *style;
    props=child(x->xml,source,paragraph ? "pPr" : "rPr");
    if(paragraph && x->styles_xml && x->defaults!=SIZE_MAX) {
      i=child(x->styles_xml,x->defaults,"pPrDefault");
      if(!properties(x,x->styles_xml,child(x->styles_xml,i,"pPr"),&css,&heading)) goto done;
      i=child(x->styles_xml,x->defaults,"rPrDefault");
      if(!properties(x,x->styles_xml,child(x->styles_xml,i,"rPr"),&css,&heading)) goto done;
    }
    style=value(x->xml,props,paragraph ? "pStyle" : "rStyle");
    if(!style) style=paragraph ? x->default_paragraph : x->default_character;
    if(style && !style_css(x,style,&css,&heading,0)) goto done;
    if(paragraph && !heading && style && !strncmp(style,"Heading",7) && style[7]>='1' && style[7]<='6' && !style[8]) heading=style[7]-'0';
    if(!properties(x,x->xml,props,&css,&heading)) goto done;
    if(paragraph) {
      char tag[4]="p"; if(heading) { tag[0]='h'; tag[1]=(char)('0'+heading); tag[2]=0; }
      at=make(x,parent,heading ? EXR_NODE_HEADING : EXR_NODE_PARAGRAPH,tag,NULL);
    } else at=make(x,parent,EXR_NODE_ELEMENT,"span",NULL);
    if(at==SIZE_MAX || (css.size && !set(x,at,"style",css.data))) goto done;
  } else if(word(v,"hyperlink")) {
    const char *id=rattr(v,"id"),*anchor=attr(v,"anchor"); relationship *r=rel(x,id); char path[2048]; exr_buffer href={0};
    at=make(x,parent,EXR_NODE_LINK,"a",NULL); if(at==SIZE_MAX) goto done;
    if(id && (!r || !rel_type(r->type,"hyperlink"))) { x->status=EXR_FORMAT; goto done; }
    if(r) {
      if(r->external) ok=put(&href,r->target);
      else if(target(x,r,path)) {
        const char *fragment=strchr(r->target,'#');
        ok=exr_uri_path(&href,!strcmp(path,x->main) ? "document.xhtml" : path);
        if(ok && fragment && !anchor) ok=put(&href,fragment);
      }
      if(!ok) { free(href.data); x->status=EXR_FORMAT; goto done; }
    }
    if(anchor && (!put(&href,"#") || !exr_uri_path(&href,anchor))) { free(href.data); goto done; }
    ok=!href.size || set(x,at,"href",href.data); free(href.data); if(!ok) goto done;
    ok=0;
  } else if(word(v,"bookmarkStart")) {
    const char *name=attr(v,"name");
    if(name) { at=make(x,parent,EXR_NODE_ELEMENT,"span",NULL); if(at==SIZE_MAX || !set(x,at,"id",name)) goto done; }
  } else if(word(v,"tab")) return make(x,parent,EXR_NODE_TEXT,NULL,"\t")!=SIZE_MAX;
  else if(word(v,"br") || word(v,"cr")) {
    const char *type=attr(v,"type"); int page=type && !strcmp(type,"page");
    at=make(x,parent,page ? EXR_NODE_SECTION : EXR_NODE_BREAK,page ? "div" : "br",NULL);
    return at!=SIZE_MAX && (!page || set(x,at,"style","break-before:page"));
  }
  for(i=v->first_child;i!=SIZE_MAX;i=x->xml->nodes[i].next_sibling)
    if(!content(x,at,i,depth+1)) goto done;
  ok=1;
done:
  free(css.data);
  if(!ok && x->status==EXR_OK) x->status=EXR_LIMIT;
  return ok;
}
exr_status exr_docx(exr_document *d,exr_member_read_fn read,void *context,exr_error *e) {
  docx x={0}; exr_document *package=NULL; relationship *package_rels=NULL; size_t package_count=0;
  size_t i,body,chapter,html,head,title,out_body; char relpath[2048]; const char *slash;
  x.out=d; x.read=read; x.context=context; x.error=e; x.defaults=SIZE_MAX; strcpy(x.main,"word/document.xml");
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
  slash=strrchr(x.main,'/');
  if(slash) snprintf(relpath,sizeof(relpath),"%.*s/_rels/%s.rels",(int)(slash-x.main),x.main,slash+1);
  else snprintf(relpath,sizeof(relpath),"_rels/%s.rels",x.main);
  if(strlen(x.main)+13>=sizeof(relpath)) { x.status=EXR_LIMIT; goto done; }
  x.status=relations(&x,relpath,&x.rels_xml,&x.rels,&x.rel_count); if(x.status!=EXR_OK) goto done;
  x.status=styles(&x); if(x.status!=EXR_OK) goto done;
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
  for(i=x.xml->nodes[body].first_child;i!=SIZE_MAX;i=x.xml->nodes[i].next_sibling)
    if(!content(&x,out_body,i,0)) { if(x.status==EXR_OK) x.status=EXR_LIMIT; break; }
done:
  free(package_rels); exr_document_free(package); free(x.rels); free(x.styles);
  exr_document_free(x.xml); exr_document_free(x.rels_xml); exr_document_free(x.styles_xml);
  if(x.status!=EXR_OK && (!e || !e->message[0])) exr_fail(e,x.status,"DOCX structure rejected");
  return x.status;
}
