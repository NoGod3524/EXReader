/* SPDX-License-Identifier: MIT */
#include "document_internal.h"
#define CFI_LIMIT 65536u
static exr_status range_paths(const char *cfi,char **a,char **b,exr_error *e);
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
static int assertion(const char **at,exr_buffer *id,unsigned *side,exr_buffer *after) {
  const char *p=*at; exr_buffer *value=id; *side=0;
  if(*p!='[') return 1;
  p++;
  while(*p && *p!=']' && *p!=';') {
    if(*p=='^') { p++; if(!*p || !strchr("^[](),;",*p)) return 0; }
    else if(*p==',') { if(!after || value==after) return 0; value=after; p++; continue; }
    else if(strchr("[()",*p)) return 0;
    if(value->size==4096 || !exr_append(value,p++,1)) return 0;
  }
  if(*p==';') {
    if(strncmp(p,";s=",3) || (p[3]!='a' && p[3]!='b') || p[4]!=']') return 0;
    *side=p[3]=='b' ? 1u : 2u; p+=4;
  }
  if(*p!=']' || (!id->size && (!after || !after->size) && !*side)) return 0;
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
  exr_status status; exr_cfi_point result={SIZE_MAX,SIZE_MAX,0}; exr_buffer id={0},after={0}; size_t node,depth=0,n=0,at=0; uint32_t cp;
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
      { int located;
        if(!assertion(&p,&id,&side,&after) || *p) goto malformed;
        located=chunk(d,node,index,offset,&result);
        if(!located) { result=(exr_cfi_point){SIZE_MAX,SIZE_MAX,0}; if(!id.size && !after.size) goto malformed; }
        result.side=side;
        if(id.size || after.size) { status=exr_cfi_assertion_resolve(d,chapter,id.data,after.data,control,&result,e); if(status!=EXR_OK) goto done; }
      }
      break;
    }
    for(child=d->nodes[node].first_child;child!=SIZE_MAX;child=d->nodes[child].next_sibling,children++) {
      if(d->nodes[child].kind!=EXR_NODE_TEXT) { ordinal+=2; if(ordinal==index) selected=child; }
    }
    id.size=0; if(id.data) id.data[0]=0;
    if(!assertion(&p,&id,&side,NULL)) goto malformed;
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
  free(id.data); free(after.data); return status;
}

static const char *tag(const exr_node *n) { const char *p=n->name ? strrchr(n->name,'|') : NULL; return p ? p+1 : n->name ? n->name : ""; }
/* Validate the complete reading-order mapping, including repeated itemrefs and
   non-linear entries. A separately loaded chapter must not masquerade as spine 0. */
static exr_status package_mapping(const exr_document *d,const exr_document *package,size_t wanted_chapter,
                                     size_t wanted_node,size_t *chapter,size_t *node,exr_error *e) {
  size_t root,spine=SIZE_MAX,child,next=0; exr_status status=root_element(package,0,&root,e);
  *chapter=*node=SIZE_MAX; if(status!=EXR_OK) return status;
  for(child=package->nodes[root].first_child;child!=SIZE_MAX;child=package->nodes[child].next_sibling) if(!strcmp(tag(&package->nodes[child]),"spine")) {
    if(spine!=SIZE_MAX) return invalid(e);
    spine=child;
  }
  if(spine==SIZE_MAX) return invalid(e);
  for(child=package->nodes[spine].first_child;child!=SIZE_MAX;child=package->nodes[child].next_sibling) if(!strcmp(tag(&package->nodes[child]),"itemref")) {
    const char *idref=exr_node_attribute(&package->nodes[child],"idref"); size_t resource;
    while(next<d->chapter_count && !d->chapters[next].in_spine) next++;
    if(next==d->chapter_count || (resource=d->chapters[next].resource)>=d->resource_count || !idref || strcmp(idref,d->resources[resource].id)) return invalid(e);
    if((wanted_chapter!=SIZE_MAX && next==wanted_chapter) || (wanted_node!=SIZE_MAX && child==wanted_node)) { *chapter=next; *node=child; }
    next++;
  }
  while(next<d->chapter_count && !d->chapters[next].in_spine) next++;
  return next!=d->chapter_count || *chapter==SIZE_MAX ? invalid(e) : EXR_OK;
}
exr_status exr_cfi_create_for_part(const exr_document *index,size_t part,const exr_document *d,size_t chapter,const exr_cfi_point *point,size_t context,
                                     const exr_control *control,char **out,exr_error *e) {
  exr_document *package=NULL; char *prefix=NULL,*suffix=NULL; exr_buffer b={0}; size_t mapped,node; exr_status status;
  if(!out) return exr_fail(e,EXR_ARGUMENT,"Missing full CFI output");
  *out=NULL;
  if(!index || part>=index->chapter_count || !d || chapter>=d->chapter_count || !point ||
     index->shared_archive!=d->shared_archive || strcmp(index->chapters[part].path,d->chapters[chapter].path))
    return exr_fail(e,EXR_ARGUMENT,"CFI document does not belong to this publication part");
  status=exr_document_package_tree(index,control,&package,e); if(status!=EXR_OK) goto done;
  status=package_mapping(index,package,part,SIZE_MAX,&mapped,&node,e); if(status!=EXR_OK) goto done;
  { exr_cfi_point p={node,SIZE_MAX,0}; status=exr_document_cfi_path_create(package,0,&p,control,&prefix,e); }
  if(status==EXR_OK) status=context ? exr_document_cfi_path_create_quoted(d,chapter,point,context,control,&suffix,e) : exr_document_cfi_path_create(d,chapter,point,control,&suffix,e);
  if(status!=EXR_OK) goto done;
  if(!put(&b,"epubcfi(") || !put(&b,prefix) || !put(&b,"!") || !put(&b,suffix) || !put(&b,")") || b.size>CFI_LIMIT) { status=exr_fail(e,EXR_LIMIT,"Full CFI exceeds allocation or size limit"); goto done; }
  status=exr_control_cancel(control,e); if(status==EXR_OK) { *out=b.data; b.data=NULL; status=exr_fail(e,EXR_OK,""); }
done:
  free(prefix); free(suffix); free(b.data); exr_document_free(package); return status;
}
exr_status exr_cfi_route(const exr_document *d,const char *cfi,const exr_control *control,
                            size_t *chapter,char **local,exr_error *e) {
  exr_document *package=NULL; exr_cfi_point prefix_point; char *prefix=NULL,*suffix=NULL;
  size_t n=0,i,bang=SIZE_MAX,mapped,node; int bracket=0; exr_status status;
  if(chapter) *chapter=SIZE_MAX;
  if(local) *local=NULL;
  if(!d || !cfi || !chapter || !local) return exr_fail(e,EXR_ARGUMENT,"Invalid full CFI route arguments");
  while(n<=CFI_LIMIT && cfi[n]) n++;
  if(n>CFI_LIMIT) return exr_fail(e,EXR_LIMIT,"Full CFI exceeds size limit");
  if(n<10 || strncmp(cfi,"epubcfi(",8) || cfi[n-1]!=')') return invalid(e);
  for(i=8;i<n-1;i++) {
    if(cfi[i]=='^') { if(++i==n-1) return invalid(e); continue; }
    if(cfi[i]=='[') bracket=1;
    else if(cfi[i]==']') bracket=0;
    else if(!bracket && cfi[i]=='!') { if(bang!=SIZE_MAX) return invalid(e); bang=i; }
    else if(!bracket && cfi[i]==',') {
      char *start=NULL,*end=NULL;
      status=range_paths(cfi,&start,&end,e);
      if(status==EXR_OK) status=exr_cfi_route(d,start,control,chapter,local,e);
      free(start); free(end); return status;
    }
  }
  if(bang==SIZE_MAX || bracket) return invalid(e);
  prefix=exr_copy(cfi+8,bang-8); suffix=exr_copy(cfi+bang+1,n-bang-2);
  if(!prefix || !suffix) { status=exr_fail(e,EXR_MEMORY,"CFI path allocation failed"); goto done; }
  status=exr_document_package_tree(d,control,&package,e); if(status!=EXR_OK) goto done;
  status=exr_document_cfi_path_resolve(package,0,prefix,control,&prefix_point,e); if(status!=EXR_OK) goto done;
  if(prefix_point.offset!=SIZE_MAX || prefix_point.side) { status=invalid(e); goto done; }
  status=package_mapping(d,package,SIZE_MAX,prefix_point.node,&mapped,&node,e); if(status!=EXR_OK) goto done;
  *chapter=mapped; *local=suffix; suffix=NULL; status=EXR_OK;
done:
  free(prefix); free(suffix); exr_document_free(package); return status;
}
exr_status exr_document_cfi_create(const exr_document *d,size_t chapter,const exr_cfi_point *point,
                                     const exr_control *control,char **out,exr_error *e) {
  return exr_cfi_create_for_part(d,chapter,d,chapter,point,0,control,out,e);
}
exr_status exr_document_cfi_resolve(const exr_document *d,const char *cfi,const exr_control *control,
                                      size_t *chapter,exr_cfi_point *out,exr_error *e) {
  size_t mapped; char *local=NULL; exr_cfi_point result; exr_status status;
  if(chapter) *chapter=SIZE_MAX;
  if(out) *out=(exr_cfi_point){SIZE_MAX,SIZE_MAX,0};
  if(!chapter || !out) return exr_fail(e,EXR_ARGUMENT,"Missing CFI resolve output");
  status=exr_cfi_route(d,cfi,control,&mapped,&local,e);
  if(status==EXR_OK) status=exr_document_cfi_path_resolve(d,mapped,local,control,&result,e);
  if(status==EXR_OK) { *chapter=mapped; *out=result; }
  free(local); return status;
}

/* Only canonical paths emitted by this file enter this comparator. Assertions
   do not participate in CFI order; integers compare numerically, never as text. */
static void token(const char **at,unsigned *kind,size_t *value) {
  const char *p=*at; *kind=0; *value=0;
  while(*p=='[') {
    p++;
    while(*p && *p!=']') { if(*p=='^' && p[1]) p++; p++; }
    if(*p==']') p++;
  }
  if(*p==':' || *p=='/') { *kind=*p==':' ? 1u : 2u; p++; (void)integer(&p,value); }
  else if(*p=='!') { *kind=3; p++; }
  *at=p;
}
static int point_order(const char *a,const char *b) {
  unsigned ka,kb; size_t va,vb; a+=8; b+=8;
  do {
    token(&a,&ka,&va); token(&b,&kb,&vb);
    if(ka!=kb) return ka<kb ? -1 : 1;
    if(va!=vb) return va<vb ? -1 : 1;
  } while(ka);
  return 0;
}
static const char *step_end(const char *p) {
  size_t number;
  if(*p=='!') return p+1;
  if(*p!='/') return p;
  p++; if(!integer(&p,&number)) return p;
  if(*p=='[') {
    p++; while(*p && *p!=']') { if(*p=='^' && p[1]) p++; p++; }
    if(*p==']') p++;
  }
  return p;
}
exr_status exr_document_cfi_range_create(const exr_document *d,const exr_cfi_range *range,
                                           const exr_control *control,char **out,exr_error *e) {
  char *a=NULL,*b=NULL; const char *pa,*pb,*end_a,*end_b; size_t shared=0,na,nb; exr_buffer result={0}; exr_status status;
  if(!out) return exr_fail(e,EXR_ARGUMENT,"Missing CFI range output");
  *out=NULL;
  if(!range || range->start.side || range->end.side) return exr_fail(e,EXR_ARGUMENT,"CFI ranges cannot carry endpoint side bias");
  status=exr_document_cfi_create(d,range->start_chapter,&range->start,control,&a,e);
  if(status==EXR_OK) status=exr_document_cfi_create(d,range->end_chapter,&range->end,control,&b,e);
  if(status!=EXR_OK) goto done;
  if(point_order(a,b)>0) { status=exr_fail(e,EXR_ARGUMENT,"CFI range endpoints are reversed"); goto done; }
  pa=a+8; pb=b+8; na=strlen(pa)-1; nb=strlen(pb)-1;
  while((*pa=='/' || *pa=='!') && (*pb=='/' || *pb=='!')) {
    end_a=step_end(pa); end_b=step_end(pb);
    if(end_a-pa!=end_b-pb || memcmp(pa,pb,(size_t)(end_a-pa))) break;
    shared+=(size_t)(end_a-pa); pa=end_a; pb=end_b;
  }
  if(!shared) { status=invalid(e); goto done; }
  if(!put(&result,"epubcfi(") || !exr_append(&result,a+8,shared) || !put(&result,",") ||
     !exr_append(&result,a+8+shared,na-shared) || !put(&result,",") || !exr_append(&result,b+8+shared,nb-shared) ||
     !put(&result,")") || result.size>CFI_LIMIT) { status=exr_fail(e,EXR_LIMIT,"CFI range exceeds allocation or size limit"); goto done; }
  status=exr_control_cancel(control,e); if(status==EXR_OK) { *out=result.data; result.data=NULL; status=exr_fail(e,EXR_OK,""); }
done:
  free(a); free(b); free(result.data); return status;
}
/* Split P,S,E without treating escaped/ID-assertion commas as separators. */
static exr_status range_paths(const char *cfi,char **a,char **b,exr_error *e) {
  size_t n=0,i,commas[2],count=0; int bracket=0; exr_buffer x={0},y={0}; exr_status status;
  *a=*b=NULL;
  if(!cfi) return exr_fail(e,EXR_ARGUMENT,"Missing CFI range");
  while(n<=CFI_LIMIT && cfi[n]) n++;
  if(n>CFI_LIMIT) return exr_fail(e,EXR_LIMIT,"CFI range exceeds size limit");
  if(n<11 || strncmp(cfi,"epubcfi(",8) || cfi[n-1]!=')') return invalid(e);
  for(i=8;i<n-1;i++) {
    if(cfi[i]=='^') { if(++i==n-1) return invalid(e); continue; }
    if(cfi[i]=='[') { if(bracket) return invalid(e); bracket=1; }
    else if(cfi[i]==']') { if(!bracket) return invalid(e); bracket=0; }
    else if(!bracket && cfi[i]==',') { if(count==2) return invalid(e); commas[count++]=i; }
    else if(!bracket && !count && (cfi[i]==':' || cfi[i]=='~' || cfi[i]=='@')) return invalid(e);
  }
  if(bracket || count!=2 || commas[0]==8) return invalid(e);
  if(!put(&x,"epubcfi(") || !exr_append(&x,cfi+8,commas[0]-8) ||
     !put(&y,"epubcfi(") || !exr_append(&y,cfi+8,commas[0]-8) ||
     !exr_append(&x,cfi+commas[0]+1,commas[1]-commas[0]-1) || !put(&x,")") ||
     !exr_append(&y,cfi+commas[1]+1,n-commas[1]-2) || !put(&y,")")) { status=exr_fail(e,EXR_LIMIT,"CFI range path allocation failed"); goto done; }
  *a=x.data; *b=y.data; x.data=y.data=NULL; status=EXR_OK;
done:
  free(x.data); free(y.data); return status;
}
exr_status exr_document_cfi_range_resolve(const exr_document *d,const char *cfi,const exr_control *control,
                                            exr_cfi_range *out,exr_error *e) {
  exr_cfi_range range; char *a=NULL,*b=NULL,*canonical_a=NULL,*canonical_b=NULL; exr_status status;
  if(!out) return exr_fail(e,EXR_ARGUMENT,"Missing CFI range output");
  *out=(exr_cfi_range){SIZE_MAX,SIZE_MAX,{SIZE_MAX,SIZE_MAX,0},{SIZE_MAX,SIZE_MAX,0}};
  status=range_paths(cfi,&a,&b,e); if(status!=EXR_OK) goto done;
  status=exr_document_cfi_resolve(d,a,control,&range.start_chapter,&range.start,e);
  if(status==EXR_OK) status=exr_document_cfi_resolve(d,b,control,&range.end_chapter,&range.end,e);
  if(status!=EXR_OK) goto done;
  if(range.start.side || range.end.side) { status=invalid(e); goto done; }
  /* Recreate after ID correction before comparing order; stale original step
     numbers must not reverse a successfully corrected document range. */
  status=exr_document_cfi_create(d,range.start_chapter,&range.start,control,&canonical_a,e);
  if(status==EXR_OK) status=exr_document_cfi_create(d,range.end_chapter,&range.end,control,&canonical_b,e);
  if(status!=EXR_OK) goto done;
  if(point_order(canonical_a,canonical_b)>0) { status=invalid(e); goto done; }
  *out=range; status=exr_fail(e,EXR_OK,"");
done:
  free(a); free(b); free(canonical_a); free(canonical_b); return status;
}

exr_status exr_document_cfi_path_create_quoted(const exr_document *d,size_t chapter,const exr_cfi_point *point,size_t context,
                                                const exr_control *control,char **out,exr_error *e) {
  exr_cfi_point bare; char *path=NULL,*before=NULL,*after=NULL; exr_buffer b={0}; exr_status status;
  if(out) *out=NULL;
  if(!out || !point || point->side>2 || point->offset==SIZE_MAX || !context || context>32) return exr_fail(e,EXR_ARGUMENT,"Quoted CFI needs a text boundary and 1..32 context scalars");
  bare=*point; bare.side=0; status=exr_document_cfi_path_create(d,chapter,&bare,control,&path,e); if(status!=EXR_OK) goto done;
  status=exr_cfi_context(d,chapter,point,context,control,&before,&after,e); if(status!=EXR_OK) goto done;
  if(!put(&b,path)) goto limit;
  if(*before || *after || point->side) {
    if(!put(&b,"[")) goto limit;
    if((*before || *after) && (!escaped(&b,before) || !put(&b,",") || !escaped(&b,after))) goto limit;
    if((point->side && !put(&b,point->side==1 ? ";s=b" : ";s=a")) || !put(&b,"]")) goto limit;
  }
  if(b.size>CFI_LIMIT) goto limit;
  status=exr_control_cancel(control,e); if(status!=EXR_OK) goto done;
  *out=b.data; b.data=NULL; status=exr_fail(e,EXR_OK,""); goto done;
limit:
  status=exr_fail(e,EXR_LIMIT,"Quoted CFI exceeds allocation or size limit");
done:
  free(path); free(before); free(after); free(b.data); return status;
}
exr_status exr_document_cfi_create_quoted(const exr_document *d,size_t chapter,const exr_cfi_point *point,size_t context,
                                           const exr_control *control,char **out,exr_error *e) {
  if(!context || context>32) { if(out) *out=NULL; return exr_fail(e,EXR_ARGUMENT,"Quoted CFI requires 1..32 context scalars"); }
  return exr_cfi_create_for_part(d,chapter,d,chapter,point,context,control,out,e);
}
