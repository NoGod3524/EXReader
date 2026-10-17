/* SPDX-License-Identifier: GPL-3.0-only */
#include "internal.h"
#include <miniz.h>
#include <expat.h>

typedef struct {
  const char *path, *media, *properties;
  size_t chapter, resource;
} member;
typedef struct {
  const exr_document *doc;
  const exr_control *control;
  exr_error *error;
  exr_status status;
  size_t visited;
} writer;
static int put(exr_buffer *b, const char *s) { return exr_append(b, s, strlen(s)); }
static int escape(writer *w, exr_buffer *b, const char *s) {
  const unsigned char *p;
  if (!s) s = "";
  w->status = exr_xml_text(s, strlen(s), "EPUB value", w->error);
  if (w->status != EXR_OK) return 0;
  for (p = (const unsigned char *)s; *p; p++) {
    if (!((size_t)(p-(const unsigned char *)s) % 4096)) {
      w->status=exr_control_cancel(w->control,w->error); if(w->status!=EXR_OK) return 0;
    }
    const char *entity = *p == '&' ? "&amp;" : *p == '<' ? "&lt;" : *p == '>' ? "&gt;" :
        *p == '"' ? "&quot;" : *p == '\r' ? "&#13;" : *p == '\n' ? "&#10;" :
        *p == '\t' ? "&#9;" : NULL;
    if (entity ? !put(b, entity) : !exr_append(b, p, 1)) return 0;
  }
  return 1;
}
static int ncstart(uint32_t c) {
  return c == '_' || (c >= 'A' && c <= 'Z') || (c >= 'a' && c <= 'z') ||
      (c >= 0xc0 && c <= 0xd6) || (c >= 0xd8 && c <= 0xf6) ||
      (c >= 0xf8 && c <= 0x2ff) || (c >= 0x370 && c <= 0x37d) ||
      (c >= 0x37f && c <= 0x1fff) || (c >= 0x200c && c <= 0x200d) ||
      (c >= 0x2070 && c <= 0x218f) || (c >= 0x2c00 && c <= 0x2fef) ||
      (c >= 0x3001 && c <= 0xd7ff) || (c >= 0xf900 && c <= 0xfdcf) ||
      (c >= 0xfdf0 && c <= 0xfffd) || (c >= 0x10000 && c <= 0xeffff);
}
static int name(writer *w, const char *expanded, const char **local, size_t *uri) {
  const char *bar = strrchr(expanded, '|');
  size_t at = 0, n; uint32_t c;
  *local = bar ? bar + 1 : expanded; *uri = bar ? (size_t)(bar - expanded) : 0;
  n = strlen(*local);
  if (!n || (bar && (!*uri || memchr(expanded, '|', *uri)))) goto invalid;
  while (at < n) {
    size_t start = at;
    if (!exr_next(*local, n, &at, &c) ||
        !(ncstart(c) || (start && (c == '-' || c == '.' || (c >= '0' && c <= '9') ||
          c == 0xb7 || (c >= 0x300 && c <= 0x36f) || (c >= 0x203f && c <= 0x2040))))) goto invalid;
  }
  if (*uri == strlen("http://www.w3.org/2000/xmlns/") &&
      !memcmp(expanded, "http://www.w3.org/2000/xmlns/", *uri)) goto invalid;
  return 1;
invalid:
  w->status = exr_fail(w->error, EXR_FORMAT, "Model name is not serializable XML: %.100s", expanded);
  return 0;
}
static int uri(writer *w, exr_buffer *b, const char *s, size_t n) {
  char *copy = exr_copy(s, n); int ok;
  if (!copy) return 0;
  ok = escape(w, b, copy); free(copy); return ok;
}
static const char *fallback(exr_node_kind kind) {
  switch (kind) {
  case EXR_NODE_SECTION: return "section";
  case EXR_NODE_PARAGRAPH: return "p";
  case EXR_NODE_HEADING: return "h1";
  case EXR_NODE_LIST: return "ul";
  case EXR_NODE_LIST_ITEM: return "li";
  case EXR_NODE_LINK: return "a";
  case EXR_NODE_IMAGE: return "img";
  case EXR_NODE_TABLE: return "table";
  case EXR_NODE_ROW: return "tr";
  case EXR_NODE_CELL: return "td";
  case EXR_NODE_BREAK: return "br";
  case EXR_NODE_NOTE: return "aside";
  default: return "div";
  }
}
static int tree(writer *w, exr_buffer *b, size_t index, unsigned depth) {
  const exr_node *v = &w->doc->nodes[index];
  const char *tag, *local; size_t ns, i, child;
  if (depth > 256) { w->status = exr_fail(w->error, EXR_LIMIT, "XML depth exceeds 256"); return 0; }
  if (!(w->visited++ % 256)) {
    w->status = exr_control_poll(w->control, EXR_STAGE_EXPORT, w->visited, 0, w->error);
    if (w->status != EXR_OK) return 0;
  }
  if (v->kind == EXR_NODE_TEXT) return escape(w, b, v->text);
  tag = v->name ? v->name : fallback(v->kind);
  if (!name(w, tag, &local, &ns)) return 0;
  if (!put(b, "<") || !put(b, local) || !put(b, " xmlns=\"") ||
      !(ns ? uri(w, b, tag, ns) : put(b, !v->name || (w->doc->format != EXR_CUSTOM && w->doc->format != EXR_EPUB) ? "http://www.w3.org/1999/xhtml" : "")) || !put(b, "\"")) return 0;
  for (i = 0; i < v->attribute_count; i++) {
    const exr_attribute *a = &v->attributes[i];
    const char *alocal; size_t ans; char prefix[48];
    if (!name(w, a->name, &alocal, &ans)) return 0;
    if (!ans && !strcmp(alocal, "xmlns")) {
      w->status = exr_fail(w->error, EXR_FORMAT, "Explicit xmlns attributes cannot be serialized"); return 0;
    }
    prefix[0] = 0;
    if (ans) {
      if (ans == strlen("http://www.w3.org/XML/1998/namespace") &&
          !memcmp(a->name, "http://www.w3.org/XML/1998/namespace", ans)) strcpy(prefix, "xml:");
      else {
        snprintf(prefix, sizeof(prefix), "a%zu", i);
        if (!put(b, " xmlns:") || !put(b, prefix) || !put(b, "=\"") ||
            !uri(w, b, a->name, ans) || !put(b, "\"")) return 0;
        strcat(prefix, ":");
      }
    }
    if (!put(b, " ") || !put(b, prefix) || !put(b, alocal) || !put(b, "=\"") ||
        !escape(w, b, a->value) || !put(b, "\"")) return 0;
  }
  if (!put(b, ">")) return 0;
  for (child = v->first_child; child != SIZE_MAX; child = w->doc->nodes[child].next_sibling)
    if (!tree(w, b, child, depth + 1)) return 0;
  return put(b, "</") && put(b, local) && put(b, ">");
}
static int chapter(writer *w, exr_buffer *b, size_t index) {
  size_t root = w->doc->chapters[index].root, child = w->doc->nodes[root].first_child;
  const char *tag = child == SIZE_MAX ? "" : exr_html_tag(w->doc, &w->doc->nodes[child]);
  int wrapped = strcmp(tag, "html") != 0;
  if (!put(b, "<?xml version=\"1.0\" encoding=\"UTF-8\"?>")) return 0;
  if (wrapped && (!put(b, "<html xmlns=\"http://www.w3.org/1999/xhtml\"><head><title>") ||
      !escape(w, b, w->doc->title) || !put(b, "</title></head><body>"))) return 0;
  for (; child != SIZE_MAX; child = w->doc->nodes[child].next_sibling)
    if (!tree(w, b, child, 0)) return 0;
  if (wrapped && !put(b, "</body></html>")) return 0;
  {
    XML_Parser parser = XML_ParserCreateNS(NULL, '|');
    int valid;
    if (!parser) return 0;
    valid = XML_Parse(parser, b->data, (int)b->size, XML_TRUE) == XML_STATUS_OK;
    XML_ParserFree(parser);
    if (!valid) w->status = exr_fail(w->error, EXR_FORMAT, "Model cannot be serialized as XHTML");
    return valid;
  }
}
static int compare(const void *a, const void *b) { return strcmp(((const member *)a)->path, ((const member *)b)->path); }
static size_t find(const member *m, size_t count, const char *path) {
  size_t lo = 0, hi = count;
  while (lo < hi) { size_t mid = lo + (hi-lo)/2; if (strcmp(m[mid].path,path)<0) lo=mid+1; else hi=mid; }
  return lo < count && !strcmp(m[lo].path,path) ? lo : SIZE_MAX;
}
static int property(const char *s, const char *wanted) {
  size_t n = strlen(wanted);
  while (s && *s) {
    const char *start;
    while (*s && strchr(" \t\r\n", *s)) s++;
    start=s; while (*s && !strchr(" \t\r\n", *s)) s++;
    if ((size_t)(s-start)==n && !memcmp(start,wanted,n)) return 1;
  }
  return 0;
}
static int zip_add(writer *w, mz_zip_archive *z, const char *path, const void *bytes, size_t size,
                   size_t *total, int compression) {
  if (size > 32u*1024*1024 || size > EXR_MAX_INPUT-*total) {
    w->status=exr_fail(w->error,EXR_LIMIT,"EPUB expansion exceeds limits"); return 0;
  }
  *total+=size;
  if (!mz_zip_writer_add_mem(z,path,bytes,size,(mz_uint)compression)) return 0;
  return 1;
}
typedef struct { const char *role; size_t index; } nav_root;
static int root_compare(const void *a, const void *b) {
  const nav_root *x=a, *y=b; int order=strcmp(x->role,y->role);
  return order ? order : x->index < y->index ? -1 : x->index > y->index;
}
static int nav_item(writer *w, exr_buffer *b, const exr_navigation *entries,
                       const size_t *first, const size_t *next, size_t at, unsigned depth) {
  const exr_navigation *entry=&entries[at]; size_t child; char path[2048];
  const char *fragment;
  if (depth>256) { w->status=exr_fail(w->error,EXR_LIMIT,"Navigation depth exceeds 256"); return 0; }
  if (!put(b,"<li>")) return 0;
  if (entry->href && *entry->href) {
    if (!put(b,"<a href=\"")) return 0;
    if (exr_resolve_path(entry->base,entry->href,path)) {
      if (!exr_uri_path(b,path)) return 0;
      fragment=strchr(entry->href,'#');
      if (fragment && !escape(w,b,fragment)) return 0;
    } else if (!escape(w,b,entry->href)) return 0;
    if (!put(b,"\">") || !escape(w,b,entry->label) || !put(b,"</a>")) return 0;
  } else if (!put(b,"<span>") || !escape(w,b,entry->label) || !put(b,"</span>")) return 0;
  if (first[at]!=SIZE_MAX) {
    if (!put(b,"<ol>")) return 0;
    for(child=first[at];child!=SIZE_MAX;child=next[child])
      if(!nav_item(w,b,entries,first,next,child,depth+1)) return 0;
    if (!put(b,"</ol>")) return 0;
  }
  return put(b,"</li>");
}
static int ncx_navigation(writer *w, exr_buffer *b) {
  exr_navigation *entries=NULL; nav_root *roots=NULL;
  size_t count=0, *first=NULL, *next=NULL, i, root_count=0; int ok=0;
  w->status=exr_epub_navigation(w->doc,0,&entries,&count,w->error);
  if(w->status!=EXR_OK) return 0;
  if (!count) { exr_navigation_free(entries,count); w->status=exr_fail(w->error,EXR_FORMAT,"NCX has no navigation entries"); return 0; }
  first=malloc(count*sizeof(*first)); next=malloc(count*sizeof(*next)); roots=malloc(count*sizeof(*roots));
  if (!first || !next || !roots) goto done;
  for(i=0;i<count;i++) first[i]=next[i]=SIZE_MAX;
  for(i=count;i-- > 0;) {
    if(entries[i].parent==SIZE_MAX) roots[root_count++]=(nav_root){entries[i].role,i};
    else { next[i]=first[entries[i].parent]; first[entries[i].parent]=i; }
  }
  qsort(roots,root_count,sizeof(*roots),root_compare);
  for(i=0;i<root_count;i++) {
    if (!i || strcmp(roots[i-1].role,roots[i].role)) {
      if (i && !put(b,"</ol></nav>")) goto done;
      if (!put(b,"<nav epub:type=\"") || !escape(w,b,roots[i].role) || !put(b,"\"><ol>")) goto done;
    }
    if (!nav_item(w,b,entries,first,next,roots[i].index,0)) goto done;
  }
  ok=put(b,"</ol></nav>");
done:
  free(first); free(next); free(roots); exr_navigation_free(entries,count); return ok;
}
exr_status exr_document_export_epub(const exr_document *d, const exr_control *control,
                                     void **out, size_t *size, exr_error *e) {
  writer w={d,control,e,EXR_OK,0}; member *members=NULL;
  exr_buffer xml={0}, opf={0}, nav={0}, container={0};
  mz_zip_archive zip={0}; int opened=0, has_nav=0;
  size_t count=0, i, j, total=0, n=0, spine=0; void *bytes=NULL, *archive=NULL;
  char package_path[80], nav_path[80], value[128], modified[32]; char **paths=NULL;
  if (out) *out=NULL;
  if (size) *size=0;
  if (!d || !out || !size) return exr_fail(e,EXR_ARGUMENT,"Invalid structured export arguments");
  if (!d->chapter_count || d->chapter_count+d->resource_count>9996)
    return exr_fail(e,EXR_LIMIT,"Structured export requires 1..9996 members");
  w.status=exr_control_cancel(control,e); if(w.status!=EXR_OK) return w.status;
  w.status=exr_export_time(modified,e); if(w.status!=EXR_OK) return w.status;
  w.status=exr_epub_export_check(d,e); if(w.status!=EXR_OK) return w.status;
  for(i=0;i<d->chapter_count;i++) if(d->chapters[i].in_spine) spine++;
  if(!spine) return exr_fail(e,EXR_FORMAT,"EPUB requires a reading order");
  members=calloc(d->chapter_count+d->resource_count,sizeof(*members));
  paths=calloc(d->chapter_count,sizeof(*paths));
  if (!members || !paths) goto failed;
  for (i=0;i<d->resource_count;i++) {
    const exr_resource *r=&d->resources[i];
    members[count++]=(member){r->path,r->media_type,r->properties,SIZE_MAX,i};
  }
  for (i=0;i<d->chapter_count;i++) {
    const char *path=d->chapters[i].path;
    if (path && *path) members[count++]=(member){path,"application/xhtml+xml","",i,SIZE_MAX};
  }
  qsort(members,count,sizeof(*members),compare);
  j=count;
  for (i=0;i<d->chapter_count;i++) {
    const char *path=d->chapters[i].path;
    if (!path || !*path) {
      size_t suffix=0;
      do { snprintf(value,sizeof(value),"exreader-chapter-%zu-%zu.xhtml",i,suffix++); }
      while (find(members,j,value)!=SIZE_MAX);
      paths[i]=exr_copy(value,strlen(value)); if(!paths[i]) goto failed;
      members[count++]=(member){paths[i],"application/xhtml+xml","",i,SIZE_MAX};
    } else {
      paths[i]=exr_copy(path,strlen(path)); if(!paths[i]) goto failed;
    }
  }
  qsort(members,count,sizeof(*members),compare);
  for (i=0,j=0;i<count;i++) {
    const char *path=members[i].path;
    if (!exr_canonical_path(path) ||
        !strcmp(path,"mimetype") || !strncmp(path,"META-INF/",9)) {
      w.status=exr_fail(e,EXR_FORMAT,"Invalid or reserved EPUB member path"); goto failed;
    }
    if (j && !strcmp(members[j-1].path,path)) {
      member *previous=&members[j-1];
      if (previous->resource!=SIZE_MAX && members[i].resource!=SIZE_MAX) {
        w.status=exr_fail(e,EXR_FORMAT,"Conflicting resource paths"); goto failed;
      }
      if ((previous->resource!=SIZE_MAX && previous->chapter==SIZE_MAX && strcmp(previous->media,"application/xhtml+xml")) ||
          (members[i].resource!=SIZE_MAX && strcmp(members[i].media,"application/xhtml+xml"))) {
        w.status=exr_fail(e,EXR_FORMAT,"Chapter path conflicts with a non-XHTML resource"); goto failed;
      }
      if (members[i].chapter!=SIZE_MAX) {
        if (previous->chapter!=SIZE_MAX) {
          exr_buffer other={0}; xml.size=0;
          if (!chapter(&w,&xml,previous->chapter) || !chapter(&w,&other,members[i].chapter)) {
            free(other.data); goto failed;
          }
          if (xml.size!=other.size || memcmp(xml.data,other.data,xml.size)) {
            free(other.data); w.status=exr_fail(e,EXR_FORMAT,"Different chapters share a path"); goto failed;
          }
          free(other.data);
        } else previous->chapter=members[i].chapter;
        previous->media="application/xhtml+xml";
      } else {
        previous->resource=members[i].resource; previous->properties=members[i].properties;
      }
    } else members[j++]=members[i];
  }
  count=j;
  for (i=0;;i++) {
    snprintf(package_path,sizeof(package_path),"exreader-package-%zu.opf",i);
    if (find(members,count,package_path)==SIZE_MAX) break;
  }
  for (i=0;;i++) {
    snprintf(nav_path,sizeof(nav_path),"exreader-navigation-%zu.xhtml",i);
    if (find(members,count,nav_path)==SIZE_MAX) break;
  }
  if (!put(&container,"<?xml version=\"1.0\"?><container version=\"1.0\" xmlns=\"urn:oasis:names:tc:opendocument:xmlns:container\"><rootfiles><rootfile full-path=\"") ||
      !put(&container,package_path) || !put(&container,"\" media-type=\"application/oebps-package+xml\"/></rootfiles></container>")) goto failed;
  snprintf(value,sizeof(value),"%08lx",(unsigned long)mz_crc32(0,(const unsigned char *)d->text,d->size));
  if (!put(&opf,"<?xml version=\"1.0\"?><package xmlns=\"http://www.idpf.org/2007/opf\" version=\"3.0\" unique-identifier=\"id\"><metadata xmlns:dc=\"http://purl.org/dc/elements/1.1/\"><dc:identifier id=\"id\">urn:exreader:") ||
      !put(&opf,value) || !put(&opf,"</dc:identifier><dc:title>") || !escape(&w,&opf,d->title) ||
      !put(&opf,"</dc:title><dc:language>und</dc:language><meta property=\"dcterms:modified\">") || !put(&opf,modified) || !put(&opf,"</meta></metadata><manifest>")) goto failed;
  if (!mz_zip_writer_init_heap(&zip,0,0)) goto failed;
  opened=1;
  if (!zip_add(&w,&zip,"mimetype","application/epub+zip",20,&total,0) ||
      !zip_add(&w,&zip,"META-INF/container.xml",container.data,container.size,&total,6)) goto failed;
  for (i=0;i<count;i++) {
    member *m=&members[i]; xml.size=0;
    w.status=exr_control_poll(control,EXR_STAGE_EXPORT,i,count,e); if(w.status!=EXR_OK) goto failed;
    if (m->chapter!=SIZE_MAX) {
      if (!chapter(&w,&xml,m->chapter)) goto failed;
      bytes=xml.data; n=xml.size;
    } else {
      w.status=exr_document_resource(d,m->resource,&bytes,&n,e); if(w.status!=EXR_OK) goto failed;
    }
    if (!zip_add(&w,&zip,m->path,bytes,n,&total,6)) {
      if (m->chapter==SIZE_MAX) free(bytes);
      bytes=NULL; goto failed;
    }
    if (m->chapter==SIZE_MAX) free(bytes);
    bytes=NULL;
    snprintf(value,sizeof(value),"<item id=\"r%zu\" href=\"",i);
    if (!put(&opf,value) || !exr_uri_path(&opf,m->path) || !put(&opf,"\" media-type=\"") ||
        !escape(&w,&opf,m->media) || !put(&opf,"\" properties=\"") ||
        !escape(&w,&opf,m->properties) || !put(&opf,"\"/>")) goto failed;
    if (property(m->properties,"nav")) has_nav=1;
  }
  if (!has_nav) {
    if (!put(&nav,"<?xml version=\"1.0\"?><html xmlns=\"http://www.w3.org/1999/xhtml\" xmlns:epub=\"http://www.idpf.org/2007/ops\"><head><title>Contents</title></head><body>")) goto failed;
    if (d->has_ncx) { if (!ncx_navigation(&w,&nav)) goto failed; }
    else {
    if (!put(&nav,"<nav epub:type=\"toc\"><ol>")) goto failed;
    for (i=0;i<d->chapter_count;i++) if (d->chapters[i].in_spine) {
      if (!put(&nav,"<li><a href=\"") || !exr_uri_path(&nav,paths[i]) || !put(&nav,"\">") ||
          !escape(&w,&nav,d->chapters[i].id && *d->chapters[i].id ? d->chapters[i].id : paths[i]) ||
          !put(&nav,"</a></li>")) goto failed;
    }
    if (!put(&nav,"</ol></nav>")) goto failed;
    }
    if (!put(&nav,"</body></html>") ||
        !zip_add(&w,&zip,nav_path,nav.data,nav.size,&total,6) ||
        !put(&opf,"<item id=\"nav\" href=\"") || !put(&opf,nav_path) ||
        !put(&opf,"\" media-type=\"application/xhtml+xml\" properties=\"nav\"/>")) goto failed;
  }
  if (!put(&opf,"</manifest><spine")) goto failed;
  if (d->has_ncx && d->ncx_resource<d->resource_count) {
    i=find(members,count,d->resources[d->ncx_resource].path);
    if (i!=SIZE_MAX) { snprintf(value,sizeof(value)," toc=\"r%zu\"",i); if(!put(&opf,value)) goto failed; }
  }
  if (!put(&opf,">")) goto failed;
  for (i=0;i<d->chapter_count;i++) if (d->chapters[i].in_spine) {
    j=find(members,count,paths[i]);
    snprintf(value,sizeof(value),"<itemref idref=\"r%zu\" linear=\"%s\"/>",j,d->chapters[i].linear ? "yes" : "no");
    if (!put(&opf,value)) goto failed;
  }
  if (!put(&opf,"</spine></package>") || !zip_add(&w,&zip,package_path,opf.data,opf.size,&total,6)) goto failed;
  if (!mz_zip_writer_finalize_heap_archive(&zip,&archive,&n) || n>EXR_MAX_INPUT) goto failed;
  w.status=exr_control_poll(control,EXR_STAGE_EXPORT,count,count,e); if(w.status!=EXR_OK) goto failed;
  *out=malloc(n); if(!*out) goto failed;
  memcpy(*out,archive,n); *size=n;
failed:
  if (opened) mz_zip_writer_end(&zip);
  mz_free(archive);
  if (paths) { for(i=0;i<d->chapter_count;i++) free(paths[i]); }
  free(paths); free(members); free(xml.data); free(opf.data); free(nav.data); free(container.data);
  if (*out) return exr_fail(e,EXR_OK,"");
  return w.status!=EXR_OK ? w.status : exr_fail(e,EXR_LIMIT,"Structured EPUB export allocation or size limit exceeded");
}
