/* SPDX-License-Identifier: MIT */
#include "internal.h"
#include <expat.h>
#include <miniz.h>
#define OPF "http://www.idpf.org/2007/opf"
#define DC "http://purl.org/dc/elements/1.1/"
#define DCT "http://purl.org/dc/terms/"
#define NS '\x1f'
typedef struct {
  const exr_node *node; size_t change,ref; int skip;
} property;
typedef struct {
  XML_Parser parser; exr_status status; exr_error *error;
  const exr_control *control; exr_buffer output,declarations;
  const exr_metadata_entry *changes; size_t count;
  property *properties; size_t property_count,property_at;
  const exr_epub_cover *cover; const char *cover_id,*cover_href,*cover_path,*package_path;
  int new_cover,version3; unsigned depth,metadata,manifest,skip;
} writer;
static int token(const char *list,const char *word) {
  size_t n=strlen(word); if(!list) return 0;
  while(*list) { size_t k; list+=strspn(list," \t\r\n"); k=strcspn(list," \t\r\n"); if(k==n && !memcmp(list,word,n)) return 1; list+=k; }
  return 0;
}
static const char *attr(const char **attributes,const char *key) {
  while(*attributes) { if(!strcmp(attributes[0],key)) return attributes[1]; attributes+=2; } return NULL;
}
static int named(const char *name,const char *uri,const char *local) {
  size_t n=strlen(uri),k=strlen(local);
  return !strncmp(name,uri,n) && name[n]==NS && !strncmp(name+n+1,local,k) && (!name[n+1+k] || name[n+1+k]==NS);
}
static int node_named(const exr_node *node,const char *uri,const char *local) {
  size_t n=strlen(uri); return node->name && !strncmp(node->name,uri,n) && node->name[n]=='|' && !strcmp(node->name+n+1,local);
}
static void fail(writer *w,exr_status code,const char *message) {
  if(w->status==EXR_OK) { w->status=exr_fail(w->error,code,"%s",message); if(w->parser) XML_StopParser(w->parser,XML_FALSE); }
}
static void append(writer *w,exr_buffer *b,const char *text,size_t n) {
  if(w->status!=EXR_OK) return;
  if(n>8*1024*1024-b->size) fail(w,EXR_LIMIT,"Written EPUB package exceeds 8 MiB");
  else if(!exr_append(b,text,n)) fail(w,EXR_MEMORY,"EPUB package writing allocation failed");
}
static void put(writer *w,exr_buffer *b,const char *text) { append(w,b,text,strlen(text)); }
static void escape(writer *w,exr_buffer *b,const char *text,size_t n) {
  size_t i,start=0;
  for(i=0;i<n && w->status==EXR_OK;i++) {
    const char *s=text[i]=='&' ? "&amp;" : text[i]=='<' ? "&lt;" : text[i]=='>' ? "&gt;" : text[i]=='\"' ? "&quot;" :
      text[i]=='\r' ? "&#13;" : text[i]=='\n' ? "&#10;" : text[i]=='\t' ? "&#9;" : NULL;
    if(s) { append(w,b,text+start,i-start); put(w,b,s); start=i+1; }
  }
  append(w,b,text+start,n-start);
}
static void qname(writer *w,const char *name) {
  const char *first=strchr(name,NS),*last=first ? strchr(first+1,NS) : NULL;
  if(!first) put(w,&w->output,name);
  else { if(last && last[1]) { put(w,&w->output,last+1); put(w,&w->output,":"); } append(w,&w->output,first+1,last ? (size_t)(last-first-1) : strlen(first+1)); }
}
static void attribute(writer *w,const char *name,const char *value) {
  put(w,&w->output," "); qname(w,name); put(w,&w->output,"=\""); escape(w,&w->output,value,strlen(value)); put(w,&w->output,"\"");
}
static void cover_properties(writer *w,const char *value,int selected) {
  exr_buffer b={0}; const char *at=value ? value : "";
  while(*at && w->status==EXR_OK) {
    size_t n; at+=strspn(at," \t\r\n"); n=strcspn(at," \t\r\n"); if(!n) break;
    if(n!=11 || memcmp(at,"cover-image",11)) { if(b.size) put(w,&b," "); append(w,&b,at,n); } at+=n;
  }
  if(selected && w->version3) { if(b.size) put(w,&b," "); put(w,&b,"cover-image"); }
  if(b.size) attribute(w,"properties",b.data);
  free(b.data);
}
static void XMLCALL ns_start(void *context,const char *prefix,const char *uri) {
  writer *w=context; put(w,&w->declarations," xmlns"); if(prefix) { put(w,&w->declarations,":"); put(w,&w->declarations,prefix); }
  put(w,&w->declarations,"=\""); if(uri) escape(w,&w->declarations,uri,strlen(uri)); put(w,&w->declarations,"\"");
}
static void XMLCALL start(void *context,const char *name,const char **attributes) {
  writer *w=context; const char **a; int item,selected=0,same_resource=0;
  if(++w->depth>256) { fail(w,EXR_LIMIT,"EPUB package nesting exceeds 256"); return; }
  if(w->depth==2 && named(name,OPF,"metadata")) w->metadata=w->depth;
  if(w->depth==2 && named(name,OPF,"manifest")) w->manifest=w->depth;
  if(!w->skip && w->metadata && w->depth==w->metadata+1) {
    if(w->property_at>=w->property_count) { fail(w,EXR_FORMAT,"EPUB metadata traversal mismatch"); return; }
    if(w->properties[w->property_at++].skip) w->skip=w->depth;
  }
  if(w->skip) { w->declarations.size=0; return; }
  item=w->cover && w->manifest && w->depth==w->manifest+1 && named(name,OPF,"item");
  if(item && w->cover->data) {
    const char *id=attr(attributes,"id"),*href=attr(attributes,"href"); char path[2048]; selected=id && !strcmp(id,w->cover_id);
    same_resource=href && exr_resolve_path(w->package_path,href,path) && !strcmp(path,w->cover_path);
  }
  put(w,&w->output,"<"); qname(w,name); append(w,&w->output,w->declarations.data,w->declarations.size); w->declarations.size=0;
  for(a=attributes;*a;a+=2) {
    if(item && !strcmp(a[0],"properties")) continue;
    if(same_resource && !strcmp(a[0],"media-type")) continue;
    attribute(w,a[0],a[1]);
  }
  if(item) cover_properties(w,attr(attributes,"properties"),selected);
  if(same_resource) attribute(w,"media-type",w->cover->media_type);
  put(w,&w->output,">");
}
static void replacements(writer *w) {
  size_t i;
  for(i=0;i<w->count && w->status==EXR_OK;i++) if(w->changes[i].value) {
    const char *local=w->changes[i].key+strlen(DCT),*id=NULL; size_t j;
    for(j=0;j<w->property_count;j++) if(w->properties[j].change==i) { id=exr_node_attribute(w->properties[j].node,"id"); if(id) break; }
    put(w,&w->output,"<dc:"); put(w,&w->output,local); put(w,&w->output," xmlns:dc=\"" DC "\"");
    if(id) attribute(w,"id",id);
    put(w,&w->output,">"); escape(w,&w->output,w->changes[i].value,strlen(w->changes[i].value)); put(w,&w->output,"</dc:"); put(w,&w->output,local); put(w,&w->output,">");
  }
  if(w->cover && w->cover->data) { put(w,&w->output,"<meta xmlns=\"" OPF "\" name=\"cover\" content=\""); escape(w,&w->output,w->cover_id,strlen(w->cover_id)); put(w,&w->output,"\"/>"); }
}
static void XMLCALL end(void *context,const char *name) {
  writer *w=context;
  if(!w->skip) {
    if(w->metadata==w->depth) replacements(w);
    if(w->manifest==w->depth && w->new_cover) {
      put(w,&w->output,"<item xmlns=\"" OPF "\""); attribute(w,"id",w->cover_id); attribute(w,"href",w->cover_href); attribute(w,"media-type",w->cover->media_type);
      if(w->version3) attribute(w,"properties","cover-image");
      put(w,&w->output,"/>");
    }
    put(w,&w->output,"</"); qname(w,name); put(w,&w->output,">");
  }
  if(w->skip==w->depth) w->skip=0;
  if(w->metadata==w->depth) w->metadata=0;
  if(w->manifest==w->depth) w->manifest=0;
  w->depth--;
}
static void XMLCALL characters(void *context,const char *text,int n) { writer *w=context; if(!w->skip) escape(w,&w->output,text,(size_t)n); }
static void XMLCALL comment(void *context,const char *text) { writer *w=context; if(!w->skip) { put(w,&w->output,"<!--"); put(w,&w->output,text); put(w,&w->output,"-->"); } }
static void XMLCALL instruction(void *context,const char *target,const char *data) { writer *w=context; if(!w->skip) { put(w,&w->output,"<?"); put(w,&w->output,target); if(data && *data) { put(w,&w->output," "); put(w,&w->output,data); } put(w,&w->output,"?>"); } }
static void XMLCALL doctype(void *context,const char *name,const char *system,const char *public_id,int internal) { (void)name; (void)system; (void)public_id; (void)internal; fail(context,EXR_FORMAT,"EPUB package document types are not writable"); }
static exr_status rewrite(writer *w,const void *bytes,size_t size) {
  size_t at=0; w->parser=XML_ParserCreateNS(NULL,NS); if(!w->parser) return exr_fail(w->error,EXR_MEMORY,"EPUB writer parser allocation failed");
  XML_SetUserData(w->parser,w); XML_SetReturnNSTriplet(w->parser,1); XML_SetNamespaceDeclHandler(w->parser,ns_start,NULL);
  XML_SetElementHandler(w->parser,start,end); XML_SetCharacterDataHandler(w->parser,characters); XML_SetCommentHandler(w->parser,comment);
  XML_SetProcessingInstructionHandler(w->parser,instruction); XML_SetStartDoctypeDeclHandler(w->parser,doctype);
  put(w,&w->output,"<?xml version=\"1.0\" encoding=\"UTF-8\"?>");
  while(at<size && w->status==EXR_OK) {
    size_t n=size-at; if(n>16384) n=16384;
    w->status=exr_control_poll(w->control,EXR_STAGE_EXPORT,at,size,w->error); if(w->status!=EXR_OK) break;
    if(XML_Parse(w->parser,(const char *)bytes+at,(int)n,at+n==size)==XML_STATUS_ERROR && w->status==EXR_OK) fail(w,EXR_FORMAT,"Invalid EPUB package XML");
    at+=n;
  }
  XML_ParserFree(w->parser); w->parser=NULL; return w->status;
}
static void *extract(mz_zip_archive *z,const char *path,size_t *size,exr_error *e) {
  int index=mz_zip_reader_locate_file(z,path,NULL,MZ_ZIP_FLAG_CASE_SENSITIVE); mz_zip_archive_file_stat stat; void *bytes;
  if(index<0 || !mz_zip_reader_file_stat(z,(mz_uint)index,&stat)) { exr_fail(e,EXR_FORMAT,"Missing EPUB package member"); return NULL; }
  if(stat.m_is_encrypted || stat.m_uncomp_size>4*1024*1024) { exr_fail(e,EXR_LIMIT,"EPUB package XML exceeds limits or is encrypted"); return NULL; }
  bytes=mz_zip_reader_extract_to_heap(z,(mz_uint)index,size,0); if(!bytes) exr_fail(e,EXR_FORMAT,"Cannot decompress EPUB package member"); return bytes;
}
static int same(const char *a,const char *b) { return a && b && !strcmp(a,b); }
static size_t key_index(const exr_node *node,const exr_metadata_entry *changes,size_t count) {
  size_t i; if(!node->name || strncmp(node->name,DC "|",strlen(DC)+1)) return SIZE_MAX;
  for(i=0;i<count;i++) if(!strcmp(node->name+strlen(DC)+1,changes[i].key+strlen(DCT))) return i;
  return SIZE_MAX;
}
static int id_exists(const exr_document *doc,const char *id) {
  size_t i; for(i=0;i<doc->node_count;i++) if(same(exr_node_attribute(&doc->nodes[i],"id"),id)) return 1; return 0;
}
static exr_status metadata_plan(writer *w,const exr_document *doc,size_t metadata,const char *package_path,exr_error *e) {
  size_t at,i,j,*queue,head=0,tail=0;
  for(at=doc->nodes[metadata].first_child;at!=SIZE_MAX;at=doc->nodes[at].next_sibling) if(doc->nodes[at].kind!=EXR_NODE_TEXT) w->property_count++;
  if(w->property_count>4096) return exr_fail(e,EXR_LIMIT,"EPUB metadata exceeds 4096 properties");
  w->properties=calloc(w->property_count ? w->property_count : 1,sizeof(*w->properties)); if(!w->properties) return exr_fail(e,EXR_MEMORY,"EPUB metadata edit plan allocation failed");
  for(at=doc->nodes[metadata].first_child,i=0;at!=SIZE_MAX;at=doc->nodes[at].next_sibling) {
    const exr_node *node=&doc->nodes[at]; property *p; if(node->kind==EXR_NODE_TEXT) continue;
    p=&w->properties[i++]; p->node=node; p->ref=SIZE_MAX; p->change=key_index(node,w->changes,w->count); p->skip=p->change!=SIZE_MAX;
    if(w->cover && node_named(node,OPF,"meta") && same(exr_node_attribute(node,"name"),"cover")) p->skip=1;
  }
  queue=malloc((w->property_count ? w->property_count : 1)*sizeof(*queue));
  if(!queue) return exr_fail(e,EXR_MEMORY,"EPUB refinement queue allocation failed");
  /* Resolve once, then visit each removed property once, bounding closure to
     two quadratic scans over at most 4096 metadata entries. */
  for(i=0;i<w->property_count;i++) {
    const char *ref=exr_node_attribute(w->properties[i].node,"refines");
    const char *fragment=ref ? strchr(ref,'#') : NULL; char decoded[2048],target[2048];
    if(w->properties[i].skip) queue[tail++]=i;
    if(fragment && exr_resolve_path(package_path,ref,target) && !strcmp(target,package_path)) {
      if(!exr_uri_decode(fragment+1,strlen(fragment+1),decoded)) { free(queue); return exr_fail(e,EXR_FORMAT,"Invalid EPUB metadata refinement fragment"); }
      for(j=0;j<w->property_count;j++) if(same(exr_node_attribute(w->properties[j].node,"id"),decoded)) {
      if(w->properties[i].ref!=SIZE_MAX) { free(queue); return exr_fail(e,EXR_FORMAT,"Ambiguous EPUB metadata refinement ID"); }
      w->properties[i].ref=j;
      }
    }
    if(exr_control_cancel(w->control,e)!=EXR_OK) { free(queue); return EXR_CANCELLED; }
  }
  while(head<tail) { size_t removed=queue[head++]; for(i=0;i<w->property_count;i++) if(!w->properties[i].skip && w->properties[i].ref==removed) { w->properties[i].skip=1; queue[tail++]=i; } }
  free(queue);
  return EXR_OK;
}
static int name_order(const void *a,const void *b) { return strcmp(*(char *const *)a,*(char *const *)b); }
static exr_status check_encryption(mz_zip_archive *zip,const char *cover_path,exr_error *e) {
  exr_document *tree=NULL; void *xml; size_t size,i; exr_status status;
  if(mz_zip_reader_locate_file(zip,"META-INF/encryption.xml",NULL,MZ_ZIP_FLAG_CASE_SENSITIVE)<0) return EXR_OK;
  xml=extract(zip,"META-INF/encryption.xml",&size,e); if(!xml) return e->code;
  status=exr_xml_memory_tree(xml,size,"encryption",&tree,e); mz_free(xml); if(status!=EXR_OK) return status;
  for(i=0;i<tree->node_count;i++) if(exr_node_attribute(&tree->nodes[i],"http://www.w3.org/XML/1998/namespace|base")) { exr_document_free(tree); return exr_fail(e,EXR_FORMAT,"EPUB encrypted resource base URIs are unsupported for cover editing"); }
  for(i=0;i<tree->node_count;i++) if(node_named(&tree->nodes[i],"http://www.w3.org/2001/04/xmlenc#","CipherReference")) {
    char path[2048]; const char *uri=exr_node_attribute(&tree->nodes[i],"URI");
    if(!uri || !exr_resolve_path("",uri,path)) { status=exr_fail(e,EXR_FORMAT,"Unsupported EPUB encrypted resource URI"); break; }
    if(!strcmp(path,cover_path)) { status=exr_fail(e,EXR_FORMAT,"Encrypted EPUB cover cannot be replaced"); break; }
  }
  exr_document_free(tree); return status;
}
exr_status exr_epub_metadata_write(const void *data,size_t size,const exr_metadata_entry *changes,size_t count,
  const exr_epub_cover *cover,const exr_control *control,void **out,size_t *out_size,exr_error *error) {
  static const char *keys[]={"title","creator","subject","description","publisher","contributor","date","type","format","source","language","relation","coverage","rights"};
  mz_zip_archive input={0},output={0}; writer w={0}; exr_document *container=NULL,*doc=NULL;
  exr_error local={0}; void *xml=NULL,*archive=NULL; size_t n=0,archive_size=0,i,j,root=SIZE_MAX,metadata=SIZE_MAX,manifest=SIZE_MAX,cover_node=SIZE_MAX;
  char path[2048],cover_path[2048]={0},cover_href[96],cover_id[96]; char **names=NULL,**sorted=NULL; mz_uint files=0; int opened=0,writing=0; exr_status status;
  if(out) *out=NULL;
  if(out_size) *out_size=0;
  if(!error) error=&local;
  if(!out || !out_size || !data || !size || (count && !changes)) return exr_fail(error,EXR_ARGUMENT,"Invalid EPUB metadata writing input");
  if(size>EXR_MAX_INPUT || count>64) return exr_fail(error,EXR_LIMIT,"EPUB metadata writing input exceeds limits");
  for(i=0;i<count;i++) {
    int known=0;
    if(!changes[i].key || strncmp(changes[i].key,DCT,strlen(DCT))) return exr_fail(error,EXR_ARGUMENT,"Unsupported EPUB metadata key");
    for(j=0;j<sizeof(keys)/sizeof(*keys);j++) if(!strcmp(changes[i].key+strlen(DCT),keys[j])) known=1;
    if(!known) return exr_fail(error,EXR_ARGUMENT,"Unsupported EPUB metadata key");
    if((same(changes[i].key,DCT "title") || same(changes[i].key,DCT "language")) &&
      (!changes[i].value || strspn(changes[i].value," \t\r\n")==strlen(changes[i].value))) return exr_fail(error,EXR_ARGUMENT,"Required EPUB title/language cannot be empty or deleted");
    for(j=0;j<i;j++) if(!strcmp(changes[j].key,changes[i].key)) return exr_fail(error,EXR_ARGUMENT,"Duplicate EPUB metadata key");
    if(changes[i].value) { n=strlen(changes[i].value); if(n>65536) return exr_fail(error,EXR_LIMIT,"EPUB metadata value exceeds 64 KiB"); status=exr_xml_text(changes[i].value,n,"EPUB metadata value",error); if(status!=EXR_OK) return status; }
  }
  if(cover) {
    if(cover->struct_size<sizeof(*cover) || cover->struct_size>4096 || (!cover->data && cover->size) || (cover->data && !cover->size)) return exr_fail(error,EXR_ARGUMENT,"Invalid EPUB cover input");
    for(i=sizeof(*cover);i<cover->struct_size;i++) if(((const unsigned char *)cover)[i]) return exr_fail(error,EXR_ARGUMENT,"Unsupported EPUB cover extension");
    if(cover->size>16*1024*1024) return exr_fail(error,EXR_LIMIT,"EPUB cover exceeds 16 MiB");
    if(cover->data && !((same(cover->media_type,"image/png") && cover->size>=8 && !memcmp(cover->data,"\x89PNG\r\n\x1a\n",8)) ||
       (same(cover->media_type,"image/jpeg") && cover->size>=3 && !memcmp(cover->data,"\xff\xd8\xff",3)))) return exr_fail(error,EXR_FORMAT,"EPUB cover requires PNG or JPEG with matching signature");
  }
  status=exr_control_cancel(control,error); if(status!=EXR_OK) return status;
  if(!count && !cover) { archive=malloc(size); if(!archive) return exr_fail(error,EXR_MEMORY,"EPUB copy allocation failed"); memcpy(archive,data,size); *out=archive; *out_size=size; return exr_fail(error,EXR_OK,""); }
  if(!mz_zip_reader_init_mem(&input,data,size,0)) return exr_fail(error,EXR_FORMAT,"Invalid EPUB ZIP container");
  opened=1;
  files=mz_zip_reader_get_num_files(&input); if(!files || files>10000) { status=exr_fail(error,EXR_LIMIT,"EPUB member count exceeds limits"); goto done; }
  names=calloc(files,sizeof(*names)); if(!names) { status=exr_fail(error,EXR_MEMORY,"EPUB member list allocation failed"); goto done; }
  for(i=0;i<files;i++) {
    mz_zip_archive_file_stat stat; mz_uint len=mz_zip_reader_get_filename(&input,(mz_uint)i,NULL,0);
    if(!len || len>2048 || !mz_zip_reader_file_stat(&input,(mz_uint)i,&stat) || stat.m_is_encrypted) { status=exr_fail(error,EXR_FORMAT,"Invalid or encrypted EPUB member"); goto done; }
    names[i]=malloc(len); if(!names[i]) { status=exr_fail(error,EXR_MEMORY,"EPUB member name allocation failed"); goto done; }
    if(mz_zip_reader_get_filename(&input,(mz_uint)i,names[i],len)!=len || strlen(names[i])+1!=len) { status=exr_fail(error,EXR_FORMAT,"Invalid EPUB member path"); goto done; }
    { char checked[2048]; size_t length=strlen(names[i]); memcpy(checked,names[i],length+1); if(stat.m_is_directory && length && checked[length-1]=='/') checked[length-1]=0;
      if(!exr_canonical_path(checked)) { status=exr_fail(error,EXR_FORMAT,"Invalid EPUB member path"); goto done; }
    }
    if(!strcmp(names[i],"META-INF/signatures.xml") || !strcmp(names[i],"META-INF/rights.xml")) { status=exr_fail(error,EXR_FORMAT,"Signed or rights-controlled EPUB is not writable"); goto done; }
    status=exr_control_cancel(control,error); if(status!=EXR_OK) goto done;
  }
  sorted=malloc(files*sizeof(*sorted)); if(!sorted) { status=exr_fail(error,EXR_MEMORY,"EPUB sorted member list allocation failed"); goto done; }
  memcpy(sorted,names,files*sizeof(*sorted)); qsort(sorted,files,sizeof(*sorted),name_order);
  for(i=1;i<files;i++) if(!strcmp(sorted[i-1],sorted[i])) { status=exr_fail(error,EXR_FORMAT,"Duplicate EPUB member path"); goto done; }
  { int index=mz_zip_reader_locate_file(&input,"mimetype",NULL,MZ_ZIP_FLAG_CASE_SENSITIVE); unsigned char mime[20];
    mz_zip_archive_file_stat stat; if(index<0 || !mz_zip_reader_file_stat(&input,(mz_uint)index,&stat) || stat.m_uncomp_size!=20 ||
      !mz_zip_reader_extract_to_mem(&input,(mz_uint)index,mime,20,0) || memcmp(mime,"application/epub+zip",20)) { status=exr_fail(error,EXR_FORMAT,"Invalid EPUB mimetype"); goto done; }
  }
  xml=extract(&input,"META-INF/container.xml",&n,error); if(!xml) { status=error->code; goto done; }
  status=exr_xml_memory_tree(xml,n,"container",&container,error); mz_free(xml); xml=NULL; if(status!=EXR_OK) goto done;
  for(i=0;i<container->node_count;i++) if(node_named(&container->nodes[i],"urn:oasis:names:tc:opendocument:xmlns:container","rootfile")) {
    const char *full=exr_node_attribute(&container->nodes[i],"full-path"); if(root!=SIZE_MAX || !full || !exr_resolve_path("",full,path)) { status=exr_fail(error,EXR_FORMAT,"EPUB requires one unambiguous package path"); goto done; } root=i;
  }
  if(root==SIZE_MAX) { status=exr_fail(error,EXR_FORMAT,"Missing EPUB rootfile"); goto done; }
  xml=extract(&input,path,&n,error); if(!xml) { status=error->code; goto done; }
  status=exr_xml_memory_tree(xml,n,"package",&doc,error); if(status!=EXR_OK) goto done; root=SIZE_MAX;
  if(doc->chapter_count) for(i=doc->nodes[doc->chapters[0].root].first_child;i!=SIZE_MAX;i=doc->nodes[i].next_sibling) if(node_named(&doc->nodes[i],OPF,"package")) { root=i; break; }
  if(root==SIZE_MAX) { status=exr_fail(error,EXR_FORMAT,"Invalid EPUB package namespace"); goto done; }
  for(i=doc->nodes[root].first_child;i!=SIZE_MAX;i=doc->nodes[i].next_sibling) {
    if(node_named(&doc->nodes[i],OPF,"metadata")) { if(metadata!=SIZE_MAX) { status=exr_fail(error,EXR_FORMAT,"Duplicate EPUB metadata element"); goto done; } metadata=i; }
    if(node_named(&doc->nodes[i],OPF,"manifest")) { if(manifest!=SIZE_MAX) { status=exr_fail(error,EXR_FORMAT,"Duplicate EPUB manifest element"); goto done; } manifest=i; }
  }
  if(metadata==SIZE_MAX || manifest==SIZE_MAX) { status=exr_fail(error,EXR_FORMAT,"Missing EPUB metadata or manifest"); goto done; }
  if(count) for(i=0;i<doc->node_count;i++) if(exr_node_attribute(&doc->nodes[i],"http://www.w3.org/XML/1998/namespace|base")) { status=exr_fail(error,EXR_FORMAT,"EPUB metadata editing does not support element base URIs"); goto done; }
  w.changes=changes; w.count=count; w.cover=cover; w.control=control; w.error=error;
  { const char *version=exr_node_attribute(&doc->nodes[root],"version"); w.version3=version && version[0]=='3'; }
  status=metadata_plan(&w,doc,metadata,path,error); if(status!=EXR_OK) goto done;
  if(cover && cover->data) {
    const char *hint=NULL;
    for(i=0;i<doc->node_count;i++) if(exr_node_attribute(&doc->nodes[i],"http://www.w3.org/XML/1998/namespace|base")) { status=exr_fail(error,EXR_FORMAT,"EPUB cover editing does not support element base URIs"); goto done; }
    for(i=0;i<w.property_count;i++) if(node_named(w.properties[i].node,OPF,"meta") && same(exr_node_attribute(w.properties[i].node,"name"),"cover")) {
      const char *value=exr_node_attribute(w.properties[i].node,"content"); if(!value || (hint && strcmp(hint,value))) { status=exr_fail(error,EXR_FORMAT,"Conflicting EPUB cover metadata"); goto done; } hint=value;
    }
    for(i=doc->nodes[manifest].first_child;i!=SIZE_MAX;i=doc->nodes[i].next_sibling) if(node_named(&doc->nodes[i],OPF,"item")) {
      const exr_node *item=&doc->nodes[i]; if(token(exr_node_attribute(item,"properties"),"cover-image") || same(exr_node_attribute(item,"id"),hint)) {
        if(cover_node!=SIZE_MAX) { status=exr_fail(error,EXR_FORMAT,"Ambiguous EPUB cover resource"); goto done; } cover_node=i;
      }
    }
    if(hint && (cover_node==SIZE_MAX || !same(exr_node_attribute(&doc->nodes[cover_node],"id"),hint))) { status=exr_fail(error,EXR_FORMAT,"Missing or conflicting EPUB cover manifest item"); goto done; }
    if(cover_node!=SIZE_MAX) {
      const exr_node *item=&doc->nodes[cover_node]; const char *href=exr_node_attribute(item,"href"),*media=exr_node_attribute(item,"media-type"); w.cover_id=exr_node_attribute(item,"id");
      if(!w.cover_id || !*w.cover_id || !href || !media || strncmp(media,"image/",6) || !exr_resolve_path(path,href,cover_path) || mz_zip_reader_locate_file(&input,cover_path,NULL,MZ_ZIP_FLAG_CASE_SENSITIVE)<0) { status=exr_fail(error,EXR_FORMAT,"Invalid EPUB cover manifest resource"); goto done; }
      if(!strcmp(cover_path,path) || !strcmp(cover_path,"mimetype") || !strncmp(cover_path,"META-INF/",9)) { status=exr_fail(error,EXR_FORMAT,"EPUB cover cannot replace a reserved package member"); goto done; }
      for(i=0;i<doc->node_count;i++) if(i!=cover_node && same(exr_node_attribute(&doc->nodes[i],"id"),w.cover_id)) { status=exr_fail(error,EXR_FORMAT,"Duplicate EPUB cover ID"); goto done; }
    } else {
      for(i=0;i<256;i++) {
        snprintf(cover_id,sizeof(cover_id),"exreader-cover-%zu",i); snprintf(cover_href,sizeof(cover_href),"exreader-cover-%zu.%s",i,same(cover->media_type,"image/png") ? "png" : "jpg");
        if(!exr_resolve_path(path,cover_href,cover_path)) { status=exr_fail(error,EXR_LIMIT,"EPUB cover path exceeds limits"); goto done; }
        if(!id_exists(doc,cover_id) && mz_zip_reader_locate_file(&input,cover_path,NULL,MZ_ZIP_FLAG_CASE_SENSITIVE)<0) break;
      }
      if(i==256) { status=exr_fail(error,EXR_LIMIT,"No unused EPUB cover resource name"); goto done; }
      w.cover_id=cover_id; w.cover_href=cover_href; w.new_cover=1;
    }
  }
  if(cover && cover->data) { status=check_encryption(&input,cover_path,error); if(status!=EXR_OK) goto done; }
  w.cover_path=cover_path; w.package_path=path;
  status=rewrite(&w,xml,n); if(status!=EXR_OK) goto done;
  if(!mz_zip_writer_init_heap(&output,0,0)) { status=exr_fail(error,EXR_MEMORY,"EPUB output archive allocation failed"); goto done; } writing=1;
  if(!mz_zip_writer_add_mem(&output,"mimetype","application/epub+zip",20,0)) { status=exr_fail(error,EXR_MEMORY,"Cannot write EPUB mimetype"); goto done; }
  for(i=0;i<files;i++) {
    mz_bool ok; if(!strcmp(names[i],"mimetype")) continue;
    status=exr_control_poll(control,EXR_STAGE_EXPORT,i,files,error); if(status!=EXR_OK) goto done;
    if(!strcmp(names[i],path)) ok=mz_zip_writer_add_mem(&output,path,w.output.data,w.output.size,6);
    else if(cover && cover->data && !strcmp(names[i],cover_path)) ok=mz_zip_writer_add_mem(&output,cover_path,cover->data,cover->size,6);
    else ok=mz_zip_writer_add_from_zip_reader(&output,&input,(mz_uint)i);
    if(!ok) { status=exr_fail(error,EXR_FORMAT,"Cannot preserve EPUB compressed member"); goto done; }
    if(output.m_archive_size>EXR_MAX_INPUT) { status=exr_fail(error,EXR_LIMIT,"Written EPUB exceeds 128 MiB"); goto done; }
  }
  if(w.new_cover && !mz_zip_writer_add_mem(&output,cover_path,cover->data,cover->size,6)) { status=exr_fail(error,EXR_MEMORY,"Cannot write EPUB cover"); goto done; }
  if(!mz_zip_writer_finalize_heap_archive(&output,&archive,&archive_size)) { status=exr_fail(error,EXR_MEMORY,"Cannot finalize EPUB output"); goto done; }
  if(archive_size>EXR_MAX_INPUT) { status=exr_fail(error,EXR_LIMIT,"Written EPUB exceeds 128 MiB"); goto done; }
  status=exr_control_cancel(control,error); if(status==EXR_OK) { *out=archive; *out_size=archive_size; archive=NULL; exr_fail(error,EXR_OK,""); }
done:
  if(writing) mz_zip_writer_end(&output);
  if(opened) mz_zip_reader_end(&input);
  for(i=0;i<files;i++) if(names) free(names[i]);
  free(names); free(sorted);
  free(w.properties); free(w.output.data); free(w.declarations.data); mz_free(xml); mz_free(archive);
  exr_document_free(container); exr_document_free(doc); return status;
}
