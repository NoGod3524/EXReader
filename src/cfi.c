/* SPDX-License-Identifier: GPL-3.0-only */
#include "internal.h"
#define CFI_LIMIT 65536u
static int put(exr_buffer *b,const char *s) { return exr_append(b,s,strlen(s)); }
static exr_status invalid(exr_error *e) { return exr_fail(e,EXR_FORMAT,"Invalid or unsupported chapter-local CFI path"); }
static const char *identifier(const exr_node *n) {
  const char *id=exr_node_attribute(n,"id");
  return id && *id ? id : exr_node_attribute(n,"http://www.w3.org/XML/1998/namespace|id");
}
static exr_status root_element(const exr_document *d,size_t chapter,size_t *root,exr_error *e) {
  size_t child; *root=SIZE_MAX;
  if(!d || chapter>=d->chapter_count) return exr_fail(e,EXR_ARGUMENT,"Invalid CFI chapter");
  for(child=d->nodes[d->chapters[chapter].root].first_child;child!=SIZE_MAX;child=d->nodes[child].next_sibling) {
    if(d->nodes[child].kind==EXR_NODE_TEXT) {
      const char *s=d->nodes[child].text; if(s && s[strspn(s," \t\r\n")]) return invalid(e);
    } else { if(*root!=SIZE_MAX) return invalid(e); *root=child; }
  }
  return *root==SIZE_MAX ? invalid(e) : EXR_OK;
}
static size_t units(const char *s) {
  size_t n=s ? strlen(s) : 0,at=0,count=0; uint32_t cp;
  while(at<n) { if(!exr_next(s,n,&at,&cp)) return SIZE_MAX; count+=cp>0xffff ? 2 : 1; }
  return count;
}
static int escaped(exr_buffer *b,const char *s) {
  if(!s) return 1;
  for(;*s;s++) if((strchr("^[](),;",*s) && !put(b,"^")) || !exr_append(b,s,1) || b->size>CFI_LIMIT) return 0;
  return 1;
}
static int step(exr_buffer *b,size_t index,const char *id,unsigned side) {
  char number[64]; snprintf(number,sizeof(number),"/%zu",index);
  if(!put(b,number)) return 0;
  if(id && !*id) id=NULL;
  if(id && strlen(id)>4096) return 0;
  if(id || side) {
    if(!put(b,"[") || !escaped(b,id) || (side && !put(b,side==1 ? ";s=b" : ";s=a")) || !put(b,"]")) return 0;
  }
  return b->size<=CFI_LIMIT;
}
exr_status exr_document_cfi_path_create(const exr_document *d,size_t chapter,const exr_cfi_point *point,
                                          const exr_control *control,char **out,exr_error *e) {
  exr_buffer b={0}; size_t root,chain[257],depth=0,node,parent,child,k,index=0,offset=0; int text=0; exr_status status;
  if(!out) return exr_fail(e,EXR_ARGUMENT,"Missing CFI path output");
  *out=NULL;
  status=root_element(d,chapter,&root,e); if(status!=EXR_OK) return status;
  if(!point || point->node>=d->node_count || d->nodes[point->node].chapter!=chapter || point->side>2)
    return exr_fail(e,EXR_ARGUMENT,"Invalid CFI DOM point");
  status=exr_control_cancel(control,e); if(status!=EXR_OK) return status;
  node=point->node;
  if(d->nodes[node].kind==EXR_NODE_TEXT) {
    size_t length=units(d->nodes[node].text);
    if(point->offset>length || length==SIZE_MAX) return exr_fail(e,EXR_ARGUMENT,"CFI text offset exceeds UTF-16 length");
    parent=d->nodes[node].parent; index=1; offset=point->offset; text=1;
    for(child=d->nodes[parent].first_child;child!=node;child=d->nodes[child].next_sibling) {
      if(child==SIZE_MAX) return invalid(e);
      if(d->nodes[child].kind==EXR_NODE_TEXT) offset+=units(d->nodes[child].text);
      else { index+=2; offset=point->offset; }
    }
    node=parent;
  } else if(point->offset!=SIZE_MAX) {
    size_t boundary=0; index=1; text=1;
    for(child=d->nodes[node].first_child;child!=SIZE_MAX && boundary<point->offset;child=d->nodes[child].next_sibling,boundary++) {
      if(d->nodes[child].kind==EXR_NODE_TEXT) offset+=units(d->nodes[child].text);
      else { index+=2; offset=0; }
    }
    if(boundary!=point->offset) return exr_fail(e,EXR_ARGUMENT,"CFI child boundary exceeds element length");
  }
  while(node!=root) {
    if(node==SIZE_MAX || depth==256 || d->nodes[node].kind==EXR_NODE_CHAPTER || d->nodes[node].kind==EXR_NODE_TEXT) return invalid(e);
    chain[depth++]=node; node=d->nodes[node].parent;
  }
  for(k=depth;k>0;k--) {
    size_t target=chain[k-1],ordinal=0;
    status=exr_control_poll(control,EXR_STAGE_READ,depth-k,depth,e); if(status!=EXR_OK) goto done;
    for(child=d->nodes[d->nodes[target].parent].first_child;child!=SIZE_MAX;child=d->nodes[child].next_sibling) {
      if(d->nodes[child].kind!=EXR_NODE_TEXT) ordinal+=2;
      if(child==target) break;
    }
    if(child==SIZE_MAX || !step(&b,ordinal,identifier(&d->nodes[target]),k==1 && !text ? point->side : 0)) goto limit;
  }
  if(text) {
    char value[64]; snprintf(value,sizeof(value),":%zu",offset);
    if(!step(&b,index,NULL,0) || !put(&b,value) || (point->side && (!put(&b,point->side==1 ? "[;s=b]" : "[;s=a]")))) goto limit;
  } else if(!depth && point->side) { status=exr_fail(e,EXR_ARGUMENT,"A root-only CFI point cannot carry side bias"); goto done; }
  if(b.size>CFI_LIMIT) goto limit;
  status=exr_control_cancel(control,e); if(status!=EXR_OK) goto done;
  if(!b.data && !put(&b,"")) goto limit;
  *out=b.data; b.data=NULL; status=exr_fail(e,EXR_OK,""); goto done;
limit:
  status=exr_fail(e,EXR_LIMIT,"CFI path exceeds allocation or size limit");
done:
  free(b.data); return status;
}
static int integer(const char **at,size_t *out) {
  const char *p=*at; size_t n=0;
  if(*p<'0' || *p>'9' || (*p=='0' && p[1]>='0' && p[1]<='9')) return 0;
  do { unsigned v=(unsigned)(*p-'0'); if(n>(SIZE_MAX-v)/10) return 0; n=n*10+v; p++; } while(*p>='0' && *p<='9');
  *at=p; *out=n; return 1;
}
static int assertion(const char **at,exr_buffer *id,unsigned *side) {
  const char *p=*at; *side=0;
  if(*p!='[') return 1;
  p++;
  while(*p && *p!=']' && *p!=';') {
    if(*p=='^') { p++; if(!*p || !strchr("^[](),;",*p)) return 0; }
    else if(strchr("[(),",*p)) return 0;
    if(id->size==4096 || !exr_append(id,p++,1)) return 0;
  }
  if(*p==';') {
    if(strncmp(p,";s=",3) || (p[3]!='a' && p[3]!='b') || p[4]!=']') return 0;
    *side=p[3]=='b' ? 1u : 2u; p+=4;
  }
  if(*p!=']' || (!id->size && !*side)) return 0;
  *at=p+1; return 1;
}
/* Map a virtual text chunk (which may span adjacent model text nodes) back to
   a DOM point. Empty chunks resolve to a parent child boundary. */
static int chunk(const exr_document *d,size_t parent,size_t index,size_t offset,exr_cfi_point *out) {
  size_t child,ordinal=1,boundary=0,last=SIZE_MAX;
  for(child=d->nodes[parent].first_child;child!=SIZE_MAX;child=d->nodes[child].next_sibling,boundary++) {
    if(d->nodes[child].kind==EXR_NODE_TEXT) {
      if(ordinal==index) {
        size_t length=units(d->nodes[child].text); last=child;
        if(offset<=length) { out->node=child; out->offset=offset; return 1; } offset-=length;
      }
    } else {
      if(ordinal==index) { if(offset || last!=SIZE_MAX) return 0; out->node=parent; out->offset=boundary; return 1; }
      ordinal+=2;
    }
  }
  if(ordinal!=index || offset || last!=SIZE_MAX) return 0;
  out->node=parent; out->offset=boundary; return 1;
}
exr_status exr_document_cfi_path_resolve(const exr_document *d,size_t chapter,const char *path,
                                           const exr_control *control,exr_cfi_point *out,exr_error *e) {
  exr_status status; exr_cfi_point result={SIZE_MAX,SIZE_MAX,0}; exr_buffer id={0}; size_t node,depth=0,n=0,at=0; uint32_t cp;
  const char *p=path;
  if(!out) return exr_fail(e,EXR_ARGUMENT,"Missing CFI point output");
  *out=result;
  status=root_element(d,chapter,&node,e); if(status!=EXR_OK) return status;
  if(!path) return exr_fail(e,EXR_ARGUMENT,"Missing CFI path");
  while(n<=CFI_LIMIT && path[n]) n++;
  if(n>CFI_LIMIT) return exr_fail(e,EXR_LIMIT,"CFI path exceeds size limit");
  while(at<n) if(!exr_next(path,n,&at,&cp)) return exr_fail(e,EXR_ENCODING,"CFI path is not UTF-8");
  result.node=node;
  status=exr_control_cancel(control,e); if(status!=EXR_OK) return status;
  while(*p) {
    size_t index,child,ordinal=0,children=0,selected=SIZE_MAX,offset=0; unsigned side=0;
    if(*p++!='/' || ++depth>256 || !integer(&p,&index)) goto malformed;
    status=exr_control_poll(control,EXR_STAGE_READ,depth,0,e); if(status!=EXR_OK) goto done;
    if(index&1) {
      if(*p==':') { p++; if(!integer(&p,&offset)) goto malformed; }
      id.size=0; if(id.data) id.data[0]=0;
      if(!assertion(&p,&id,&side) || id.size || *p || !chunk(d,node,index,offset,&result)) goto malformed;
      result.side=side; break;
    }
    for(child=d->nodes[node].first_child;child!=SIZE_MAX;child=d->nodes[child].next_sibling,children++) {
      if(d->nodes[child].kind!=EXR_NODE_TEXT) { ordinal+=2; if(ordinal==index) selected=child; }
    }
    id.size=0; if(id.data) id.data[0]=0;
    if(!assertion(&p,&id,&side)) goto malformed;
    if(id.size) {
      const char *actual=selected!=SIZE_MAX ? identifier(&d->nodes[selected]) : NULL;
      if(!actual || strcmp(actual,id.data)) {
        size_t i; selected=SIZE_MAX;
        for(i=0;i<d->node_count;i++) if(d->nodes[i].chapter==chapter && d->nodes[i].kind!=EXR_NODE_TEXT) {
          const char *candidate=identifier(&d->nodes[i]);
          if(!(i%256)) { status=exr_control_cancel(control,e); if(status!=EXR_OK) goto done; }
          if(candidate && !strcmp(candidate,id.data)) { if(selected!=SIZE_MAX) goto malformed; selected=i; }
        }
        if(selected==SIZE_MAX) goto malformed;
      }
    }
    if(selected==SIZE_MAX) {
      if(*p || id.size || (index!=0 && index!=ordinal+2)) goto malformed;
      result.node=node; result.offset=index ? children : 0; result.side=side; break;
    }
    if(side && *p) goto malformed;
    node=selected; result.node=node; result.offset=SIZE_MAX; result.side=side;
    if(*p && *p!='/') goto malformed;
  }
  status=exr_control_cancel(control,e); if(status!=EXR_OK) goto done;
  *out=result; status=exr_fail(e,EXR_OK,""); goto done;
malformed:
  status=invalid(e);
done:
  free(id.data); return status;
}
