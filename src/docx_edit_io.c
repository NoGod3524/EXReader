/* SPDX-License-Identifier: MIT */
#include "docx_edit_internal.h"
#include <ctype.h>
#include <time.h>

#define DEFAULT_RPR "<w:rPr><w:rFonts w:ascii=\"Times New Roman\" w:hAnsi=\"Times New Roman\" w:eastAsia=\"Times New Roman\" w:cs=\"Times New Roman\"/><w:sz w:val=\"24\"/><w:szCs w:val=\"24\"/></w:rPr>"

static int put(exr_buffer *b,const char *s) { return exr_append(b,s,strlen(s)); }
int exr_edit_xml_word(const exr_node *n,const char *tag) {
  const char *p=n->name ? strrchr(n->name,'|') : NULL;
  return p && !strcmp(p+1,tag) &&
    (((size_t)(p-n->name)==sizeof(W)-1 && !memcmp(n->name,W,sizeof(W)-1)) ||
     ((size_t)(p-n->name)==sizeof(WS)-1 && !memcmp(n->name,WS,sizeof(WS)-1)));
}
const char *exr_edit_xml_attribute(const exr_node *n,const char *space,const char *strict,const char *key) {
  char name[256]; const char *v;
  snprintf(name,sizeof(name),"%s|%s",space,key); v=exr_node_attribute(n,name);
  if (!v && strict) { snprintf(name,sizeof(name),"%s|%s",strict,key); v=exr_node_attribute(n,name); }
  return v;
}
const char *exr_edit_xml_wa(const exr_node *n,const char *key) { return exr_edit_xml_attribute(n,W,WS,key); }
size_t exr_edit_xml_child(const source_xml *x,size_t parent,const char *tag) {
  size_t i;
  if (parent==NONE) return NONE;
  for (i=x->tree->nodes[parent].first_child;i!=NONE;i=x->tree->nodes[i].next_sibling)
    if (exr_edit_xml_word(x->tree->nodes+i,tag)) return i;
  return NONE;
}
int exr_edit_xml_integer(const char *s,int32_t *out) {
  char *end; long long v;
  if (!s || !*s || strlen(s)>12) return 0;
  v=strtoll(s,&end,10);
  if (*end || v<INT32_MIN || v>INT32_MAX) return 0;
  *out=(int32_t)v; return 1;
}
static unsigned on(const char *s) { return !s || (strcmp(s,"0") && strcmp(s,"false") && strcmp(s,"off")); }
static int escaped(exr_buffer *b,const char *s,size_t n) {
  size_t i;
  for (i=0;i<n;i++) {
    const char *r=s[i]=='&' ? "&amp;" : s[i]=='<' ? "&lt;" : s[i]=='>' ? "&gt;" :
      s[i]=='\"' ? "&quot;" : s[i]=='\r' ? "&#13;" : NULL;
    if (!(r ? put(b,r) : exr_append(b,s+i,1))) return 0;
  }
  return 1;
}
static void XMLCALL span_start(void *context,const char *name,const char **attrs) {
  source_xml *x=context; size_t i=x->cursor; xml_span *s;
  (void)attrs;
  if (x->status) return;
  while (i<x->tree->node_count && !x->tree->nodes[i].name) i++;
  if (i==x->tree->node_count || strcmp(x->tree->nodes[i].name,name) || x->depth==256) {
    x->status=EXR_FORMAT; XML_StopParser(x->parser,XML_FALSE); return;
  }
  x->cursor=i+1; x->stack[x->depth++]=i; s=x->spans+i;
  s->start=(size_t)XML_GetCurrentByteIndex64(x->parser);
  s->open=s->start+(size_t)XML_GetCurrentByteCount64(x->parser);
}
static void XMLCALL span_end(void *context,const char *name) {
  source_xml *x=context; xml_span *s; size_t at,count;
  (void)name;
  if (x->status || !x->depth) return;
  s=x->spans+x->stack[--x->depth];
  at=(size_t)XML_GetCurrentByteIndex64(x->parser); count=(size_t)XML_GetCurrentByteCount64(x->parser);
  s->end=at+count; s->close=count ? at : s->open; /* Empty element callbacks have count=0. */
}
static void XMLCALL xml_encoding(void *context,const char *version,const char *encoding,int standalone) {
  source_xml *x=context; char lower[32]; size_t i;
  (void)version; (void)standalone;
  if (!encoding) return;
  for (i=0;encoding[i] && i+1<sizeof(lower);i++) lower[i]=(char)tolower((unsigned char)encoding[i]);
  lower[i]=0;
  if (strcmp(lower,"utf-8") && strcmp(lower,"us-ascii")) {
    x->status=EXR_UNSUPPORTED; XML_StopParser(x->parser,XML_FALSE);
  }
}
void exr_edit_xml_free(source_xml *x) {
  if (x->parser) XML_ParserFree(x->parser);
  exr_document_free(x->tree); free(x->spans); memset(x,0,sizeof(*x));
}
exr_status exr_edit_xml_parse(source_xml *x,const void *data,size_t size,const char *root,exr_error *e) {
  exr_status status; size_t i;
  memset(x,0,sizeof(*x)); x->root=x->body=NONE;
  if (size>EXR_MAX_INPUT) return exr_fail(e,EXR_LIMIT,"DOCX XML exceeds input limit");
  /* Raw slices and generated XML must share an encoding. Never mix UTF-16
     source bytes with UTF-8 edits. The DOM parser validates the declaration. */
  if (memchr(data,0,size)) return exr_fail(e,EXR_UNSUPPORTED,"Editable DOCX requires UTF-8 XML");
  status=exr_xml_memory_tree(data,size,root,&x->tree,e);
  if (status) return status;
  x->bytes=data; x->size=size;
  x->spans=calloc(x->tree->node_count,sizeof(*x->spans));
  x->parser=XML_ParserCreateNS(NULL,'|');
  if (!x->spans || !x->parser) { exr_edit_xml_free(x); return EXR_MEMORY; }
  XML_SetUserData(x->parser,x); XML_SetElementHandler(x->parser,span_start,span_end);
  XML_SetXmlDeclHandler(x->parser,xml_encoding);
  /* The existing DOM parser has already rejected entity declarations. */
  if (XML_Parse(x->parser,data,(int)size,XML_TRUE)!=XML_STATUS_OK || x->status) {
    status=x->status ? x->status : EXR_FORMAT; exr_edit_xml_free(x); return status;
  }
  for (i=0;i<x->tree->node_count;i++) if (x->tree->nodes[i].name) { x->root=i; break; }
  x->body=exr_edit_xml_child(x,x->root,"body"); return EXR_OK;
}
int exr_edit_xml_raw(exr_buffer *b,const source_xml *x,size_t n) {
  return n==NONE || exr_append(b,x->bytes+x->spans[n].start,x->spans[n].end-x->spans[n].start);
}
size_t exr_edit_xml_locate(const source_xml *x,const void *data,size_t size,const char *tag,size_t parent) {
  size_t i;
  if (!size || !x->tree) return NONE;
  for (i=parent==NONE ? 0 : x->tree->nodes[parent].first_child;i!=NONE && i<x->tree->node_count;
       i=parent==NONE ? i+1 : x->tree->nodes[i].next_sibling) if (exr_edit_xml_word(x->tree->nodes+i,tag) &&
      x->spans[i].end-x->spans[i].start==size && !memcmp(x->bytes+x->spans[i].start,data,size)) return i;
  return NONE;
}
static void run_props(const source_xml *x,size_t pr,exr_edit_run_props *p) {
  size_t i; int32_t v; const char *s; memset(p,0,sizeof(*p));
  if (pr==NONE) return;
  for (i=x->tree->nodes[pr].first_child;i!=NONE;i=x->tree->nodes[i].next_sibling) {
    const exr_node *n=x->tree->nodes+i; s=exr_edit_xml_wa(n,"val");
    if (exr_edit_xml_word(n,"rFonts")) {
      s=exr_edit_xml_wa(n,"ascii"); if (!s) s=exr_edit_xml_wa(n,"hAnsi"); if (!s) s=exr_edit_xml_wa(n,"eastAsia"); if (!s) s=exr_edit_xml_wa(n,"cs");
      if (s && strlen(s)<sizeof(p->font)) { strcpy(p->font,s); p->present|=EXR_EDIT_FONT; }
    } else if (exr_edit_xml_word(n,"sz") && exr_edit_xml_integer(s,&v) && v>0 && v<=1638) {
      p->present|=EXR_EDIT_SIZE; p->size_half_points=(uint32_t)v;
    } else if (exr_edit_xml_word(n,"b")) { p->present|=EXR_EDIT_BOLD; p->bold=on(s); }
    else if (exr_edit_xml_word(n,"i")) { p->present|=EXR_EDIT_ITALIC; p->italic=on(s); }
    else if (exr_edit_xml_word(n,"color") && s && strlen(s)==6 && strspn(s,"0123456789abcdefABCDEF")==6) {
      p->present|=EXR_EDIT_COLOR; p->color_rgb=(uint32_t)strtoul(s,NULL,16);
    }
  }
}
void exr_edit_xml_para_props(const source_xml *x,size_t pr,exr_edit_para_props *p) {
  size_t i,n; int32_t v; const char *s; memset(p,0,sizeof(*p));
  if (pr==NONE) return;
  for (i=x->tree->nodes[pr].first_child;i!=NONE;i=x->tree->nodes[i].next_sibling) {
    const exr_node *a=x->tree->nodes+i; s=exr_edit_xml_wa(a,"val");
    if (exr_edit_xml_word(a,"jc") && s) {
      if (!strcmp(s,"left") || !strcmp(s,"start")) p->alignment=EXR_EDIT_LEFT;
      else if (!strcmp(s,"center")) p->alignment=EXR_EDIT_CENTER;
      else if (!strcmp(s,"right") || !strcmp(s,"end")) p->alignment=EXR_EDIT_RIGHT;
      else if (!strcmp(s,"both") || !strcmp(s,"distribute")) p->alignment=EXR_EDIT_JUSTIFY;
      else continue;
      p->present|=EXR_EDIT_ALIGN;
    } else if (exr_edit_xml_word(a,"ind")) {
      p->present|=EXR_EDIT_INDENT;
      if (exr_edit_xml_integer(exr_edit_xml_wa(a,"left"),&v) || exr_edit_xml_integer(exr_edit_xml_wa(a,"start"),&v)) p->indent_left=v;
      if (exr_edit_xml_integer(exr_edit_xml_wa(a,"right"),&v) || exr_edit_xml_integer(exr_edit_xml_wa(a,"end"),&v)) p->indent_right=v;
      if (exr_edit_xml_integer(exr_edit_xml_wa(a,"firstLine"),&v)) p->indent_first_line=v;
      if (exr_edit_xml_integer(exr_edit_xml_wa(a,"hanging"),&v) && v>=0) p->indent_first_line=-v;
    } else if (exr_edit_xml_word(a,"spacing")) {
      p->present|=EXR_EDIT_SPACING;
      if (exr_edit_xml_integer(exr_edit_xml_wa(a,"before"),&v) && v>=0) p->space_before=(uint32_t)v;
      if (exr_edit_xml_integer(exr_edit_xml_wa(a,"after"),&v) && v>=0) p->space_after=(uint32_t)v;
      if (exr_edit_xml_integer(exr_edit_xml_wa(a,"line"),&v) && v>=0) p->line=(uint32_t)v;
      s=exr_edit_xml_wa(a,"lineRule"); p->line_rule=s && !strcmp(s,"exact") ? EXR_EDIT_LINE_EXACT :
        s && !strcmp(s,"atLeast") ? EXR_EDIT_LINE_AT_LEAST : EXR_EDIT_LINE_AUTO;
    } else if (exr_edit_xml_word(a,"keepNext")) { p->present|=EXR_EDIT_KEEP_NEXT; p->keep_next=on(s); }
    else if (exr_edit_xml_word(a,"keepLines")) { p->present|=EXR_EDIT_KEEP_LINES; p->keep_lines=on(s); }
    else if (exr_edit_xml_word(a,"pageBreakBefore")) { p->present|=EXR_EDIT_PAGE_BEFORE; p->page_break_before=on(s); }
    else if (exr_edit_xml_word(a,"numPr")) {
      n=exr_edit_xml_child(x,i,"numId");
      if (n!=NONE && exr_edit_xml_integer(exr_edit_xml_wa(x->tree->nodes+n,"val"),&v) && v>=0) {
        p->present|=EXR_EDIT_NUMBERING; p->numbering_id=(uint32_t)v;
        n=exr_edit_xml_child(x,i,"ilvl");
        if (n!=NONE && exr_edit_xml_integer(exr_edit_xml_wa(x->tree->nodes+n,"val"),&v) && v>=0 && v<=8) p->numbering_level=(uint32_t)v;
      }
    }
  }
}
static void section_props(const source_xml *x,size_t pr,exr_edit_section *s) {
  size_t i; int32_t v; memset(s,0,sizeof(*s));
  s->page_width=12240; s->page_height=15840;
  s->margin_top=s->margin_right=s->margin_bottom=s->margin_left=1440;
  s->header_distance=s->footer_distance=720;
  if (pr==NONE) return;
  for (i=x->tree->nodes[pr].first_child;i!=NONE;i=x->tree->nodes[i].next_sibling) {
    const exr_node *n=x->tree->nodes+i; const char *value;
    if (exr_edit_xml_word(n,"pgSz")) {
      if (exr_edit_xml_integer(exr_edit_xml_wa(n,"w"),&v) && v>0) s->page_width=v;
      if (exr_edit_xml_integer(exr_edit_xml_wa(n,"h"),&v) && v>0) s->page_height=v;
      value=exr_edit_xml_wa(n,"orient"); s->landscape=value && !strcmp(value,"landscape");
    } else if (exr_edit_xml_word(n,"pgMar")) {
#define M(key,field) if (exr_edit_xml_integer(exr_edit_xml_wa(n,key),&v)) s->field=v
      M("top",margin_top); M("right",margin_right); M("bottom",margin_bottom); M("left",margin_left);
      M("header",header_distance); M("footer",footer_distance);
#undef M
    } else if (exr_edit_xml_word(n,"headerReference") || exr_edit_xml_word(n,"footerReference")) {
      const char *type=exr_edit_xml_wa(n,"type"),*id=exr_edit_xml_attribute(n,R,RS,"id");
      size_t slot=type && !strcmp(type,"first") ? 1 : type && !strcmp(type,"even") ? 2 : 0;
      if (type && strcmp(type,"default") && strcmp(type,"first") && strcmp(type,"even")) continue;
      if (id && strlen(id)<128) strcpy(exr_edit_xml_word(n,"headerReference") ? s->header_refs[slot] : s->footer_refs[slot],id);
    }
  }
}

/* Each child remains an independent raw run unless it is a plain text run.
   Fields, hyperlinks, drawings, revisions and note references remain opaque;
   editing their neighbouring text can never flatten them into plain text. */
exr_status exr_edit_xml_decode_runs(const source_xml *x,size_t p,exr_edit_run **out,size_t *count) {
  size_t i,j,k=0,capacity=0,at=x->spans[p].open; exr_edit_run *runs=NULL; exr_status status=EXR_MEMORY;
  *out=NULL; *count=0;
  for (i=x->tree->nodes[p].first_child;i!=NONE;i=x->tree->nodes[i].next_sibling) {
    exr_edit_run r={0}; exr_buffer text={0}; int simple=1; size_t texts=0;
    if (!x->tree->nodes[i].name) continue;
    if (x->spans[i].start>at) {
      if (!exr_grow((void **)&runs,&capacity,k+1,sizeof(*runs))) goto fail;
      r.kind=EXR_EDIT_OPAQUE_RUN; r.opaque_xml=x->bytes+at; r.opaque_size=x->spans[i].start-at; runs[k++]=r;
    }
    at=x->spans[i].end;
    if (exr_edit_xml_word(x->tree->nodes+i,"pPr")) continue;
    memset(&r,0,sizeof(r)); r.kind=EXR_EDIT_OPAQUE_RUN;
    r.opaque_xml=x->bytes+x->spans[i].start; r.opaque_size=x->spans[i].end-x->spans[i].start;
    if (exr_edit_xml_word(x->tree->nodes+i,"r")) {
      run_props(x,exr_edit_xml_child(x,i,"rPr"),&r.props);
      for (j=x->tree->nodes[i].first_child;j!=NONE;j=x->tree->nodes[j].next_sibling) {
        const exr_node *n=x->tree->nodes+j;
        if (!n->name) continue;
        if (exr_edit_xml_word(n,"t")) {
          size_t t;
          if (++texts>1) simple=0;
          for (t=n->first_child;t!=NONE;t=x->tree->nodes[t].next_sibling) {
            const exr_node *v=x->tree->nodes+t;
            if (v->name) simple=0;
            else if (v->text && !put(&text,v->text)) { free(text.data); goto fail; }
          }
        } else if (!exr_edit_xml_word(n,"rPr")) simple=0;
      }
      for (j=x->spans[i].start;j+3<x->spans[i].end;j++) if (x->bytes[j]=='<' &&
          (x->bytes[j+1]=='?' || !memcmp(x->bytes+j,"<!--",4))) simple=0;
      if (simple) {
        r.kind=EXR_EDIT_TEXT; r.text=text.data; r.text_size=text.size; text.data=NULL;
      }
    }
    free(text.data);
    if (!exr_grow((void **)&runs,&capacity,k+1,sizeof(*runs))) { free((void *)r.text); goto fail; }
    runs[k++]=r;
  }
  if (x->spans[p].close>at) {
    exr_edit_run r={0}; r.kind=EXR_EDIT_OPAQUE_RUN;
    r.opaque_xml=x->bytes+at; r.opaque_size=x->spans[p].close-at;
    if (!exr_grow((void **)&runs,&capacity,k+1,sizeof(*runs))) goto fail;
    runs[k++]=r;
  }
  *out=runs; *count=k; return EXR_OK;
fail:
  for (i=0;i<k;i++) free((void *)runs[i].text);
  free(runs); return status;
}
static void blocks_free(exr_edit_block *blocks,size_t n) {
  size_t i,j;
  for (i=0;i<n;i++) {
    for (j=0;j<blocks[i].run_count;j++) free((void *)blocks[i].runs[j].text);
    free((void *)blocks[i].runs);
    exr_edit_table_decode_free((exr_edit_table *)blocks[i].table);
    free((void *)blocks[i].image);
  }
  free(blocks);
}
static exr_status decode_blocks(const source_xml *x,exr_edit_section **sections,size_t *ns,
                               exr_edit_block **blocks,size_t *nb) {
  size_t i,start=0,sc=0,bc=0,at=x->spans[x->body].open;
  *sections=NULL; *blocks=NULL; *ns=*nb=0;
  for (i=x->tree->nodes[x->body].first_child;i!=NONE;i=x->tree->nodes[i].next_sibling) {
    exr_edit_block b={0}; size_t sec=NONE; int paragraph=exr_edit_xml_word(x->tree->nodes+i,"p");
    if (!x->tree->nodes[i].name) continue;
    if (x->spans[i].start>at) {
      b.kind=EXR_EDIT_OPAQUE_BLOCK; b.opaque_xml=x->bytes+at; b.opaque_size=x->spans[i].start-at;
      if (!exr_grow((void **)blocks,&bc,*nb+1,sizeof(**blocks))) return EXR_MEMORY;
      (*blocks)[(*nb)++]=b;
    }
    at=x->spans[i].end;
    if (exr_edit_xml_word(x->tree->nodes+i,"sectPr")) sec=i;
    else {
      memset(&b,0,sizeof(b));
      b.kind=paragraph ? EXR_EDIT_PARAGRAPH : exr_edit_xml_word(x->tree->nodes+i,"tbl") ? EXR_EDIT_TABLE : EXR_EDIT_OPAQUE_BLOCK;
      b.opaque_xml=x->bytes+x->spans[i].start; b.opaque_size=x->spans[i].end-x->spans[i].start;
      if (!exr_grow((void **)blocks,&bc,*nb+1,sizeof(**blocks))) return EXR_MEMORY;
      (*blocks)[(*nb)++]=b;
      if (paragraph) {
        exr_edit_run *runs; size_t nr; exr_status status;
        size_t pr=exr_edit_xml_child(x,i,"pPr"); exr_edit_xml_para_props(x,pr,&(*blocks)[*nb-1].props);
        status=exr_edit_xml_decode_runs(x,i,&runs,&nr); if (status) return status;
        (*blocks)[*nb-1].runs=runs; (*blocks)[*nb-1].run_count=nr; sec=exr_edit_xml_child(x,pr,"sectPr");
      } else if (b.kind==EXR_EDIT_TABLE) {
        exr_edit_table *table; exr_status status=exr_edit_table_decode(x,i,&table);
        if (status) return status;
        (*blocks)[*nb-1].table=table;
      }
    }
    if (sec!=NONE) {
      size_t j;
      if (!exr_grow((void **)sections,&sc,*ns+1,sizeof(**sections))) return EXR_MEMORY;
      section_props(x,sec,*sections+*ns); (*sections)[*ns].id=*ns+1; (*ns)++;
      for (j=start;j<*nb;j++) (*blocks)[j].section_id=*ns;
      start=*nb;
    }
  }
  if (!*ns || start<*nb) {
    size_t j;
    if (!exr_grow((void **)sections,&sc,*ns+1,sizeof(**sections))) return EXR_MEMORY;
    section_props(x,NONE,*sections+*ns); (*sections)[*ns].id=*ns+1; (*ns)++;
    for (j=start;j<*nb;j++) (*blocks)[j].section_id=*ns;
  }
  /* Whitespace/comments after the final body sectPr belong to the last section. */
  if (x->spans[x->body].close>at) {
    exr_edit_block b={0}; b.kind=EXR_EDIT_OPAQUE_BLOCK; b.section_id=*ns;
    b.opaque_xml=x->bytes+at; b.opaque_size=x->spans[x->body].close-at;
    if (!exr_grow((void **)blocks,&bc,*nb+1,sizeof(**blocks))) return EXR_MEMORY;
    (*blocks)[(*nb)++]=b;
  }
  return EXR_OK;
}
const exr_edit_part *exr_edit_part_named(const exr_edit_part *p,size_t n,const char *name) {
  size_t i; for (i=0;i<n;i++) if (!strcmp(p[i].name,name)) return p+i; return NULL;
}
static int part_path(const char *name) {
  size_t n; char path[2048];
  if (!name || !(n=strlen(name)) || n>=sizeof(path)) return 0;
  memcpy(path,name,n+1);
  if (path[n-1]=='/') path[--n]=0;
  return n && exr_canonical_path(path);
}
exr_status exr_edit_main_part(const exr_edit_part *parts,size_t n,char name[2048],exr_error *e) {
  const exr_edit_part *p=exr_edit_part_named(parts,n,"_rels/.rels"); source_xml x={0}; size_t i; exr_status status;
  if (!p) return EXR_FORMAT;
  status=exr_edit_xml_parse(&x,p->data,p->size,"Relationships",e); if (status) return status;
  strcpy(name,"word/document.xml");
  for (i=0;i<x.tree->node_count;i++) {
    const exr_node *v=x.tree->nodes+i; const char *type=exr_node_attribute(v,"Type");
    if (type && (!strcmp(type,R "/officeDocument") || !strcmp(type,RS "/officeDocument"))) {
      const char *target=exr_node_attribute(v,"Target"),*mode=exr_node_attribute(v,"TargetMode");
      if (!target || (mode && !strcmp(mode,"External"))) { status=EXR_FORMAT; break; }
      if (*target=='/') target++;
      if (!exr_resolve_path("",target,name)) status=EXR_FORMAT;
      break;
    }
  }
  exr_edit_xml_free(&x); return status;
}
exr_status exr_edit_docx_read(const void *data,size_t size,const exr_edit_options *options,
                            exr_edit_doc **out,exr_error *e) {
  mz_zip_archive zip={0}; exr_document *readonly=NULL; source_xml x={0};
  exr_edit_part *parts=NULL; exr_edit_block *blocks=NULL; exr_edit_section *sections=NULL;
  size_t np=0,nb=0,ns=0,i,total=0; exr_status status; int opened=0; char main[2048];
  const exr_edit_part *p;
  if (e) memset(e,0,sizeof(*e));
  if (!out) return exr_fail(e,EXR_ARGUMENT,"Missing editable document output");
  *out=NULL;
  if (!data || !size) return exr_fail(e,EXR_ARGUMENT,"Missing DOCX input");
  if (size>EXR_MAX_INPUT) return exr_fail(e,EXR_LIMIT,"DOCX exceeds input limit");
  /* Reuse docx.c's semantic decoder and its relationship/image/note validation.
     Its HTML projection deliberately omits source OOXML, so the existing XML
     DOM supplies direct properties and byte spans supply the lossless layer. */
  status=exr_document_open_memory(EXR_DOCX,data,size,&readonly,e);
  if (status) goto done;
  exr_document_free(readonly); readonly=NULL;
  status=EXR_FORMAT;
  if (!mz_zip_reader_init_mem(&zip,data,size,0)) goto done;
  opened=1; np=mz_zip_reader_get_num_files(&zip);
  if (np>10000) { status=EXR_LIMIT; goto done; }
  parts=calloc(np,sizeof(*parts)); if (!parts) { status=EXR_MEMORY; goto done; }
  for (i=0;i<np;i++) {
    mz_zip_archive_file_stat s; size_t length; mz_uint name_size; char *name;
    if (!mz_zip_reader_file_stat(&zip,(mz_uint)i,&s)) goto done;
    name_size=mz_zip_reader_get_filename(&zip,(mz_uint)i,NULL,0);
    if (!name_size || name_size>2048) { status=EXR_LIMIT; goto done; }
    name=malloc(name_size); if (!name) { status=EXR_MEMORY; goto done; }
    parts[i].name=name;
    if (mz_zip_reader_get_filename(&zip,(mz_uint)i,name,name_size)!=name_size || !part_path(name)) goto done;
    if (s.m_uncomp_size>EXR_MAX_INPUT-total) { status=EXR_LIMIT; goto done; }
    total+=(size_t)s.m_uncomp_size;
    if (!s.m_is_directory) {
      parts[i].data=mz_zip_reader_extract_to_heap(&zip,(mz_uint)i,&length,0);
      if (!parts[i].data) goto done;
      parts[i].size=length;
    }
  }
  status=exr_edit_main_part(parts,np,main,e); if (status) goto done;
  p=exr_edit_part_named(parts,np,main); if (!p) { status=EXR_FORMAT; goto done; }
  status=exr_edit_xml_parse(&x,p->data,p->size,"document",e); if (status) goto done;
  if (x.body==NONE || !exr_edit_xml_word(x.tree->nodes+x.root,"document")) { status=EXR_FORMAT; goto done; }
  status=decode_blocks(&x,&sections,&ns,&blocks,&nb); if (status) goto done;
  status=exr_edit_images_decode(&x,parts,np,main,&blocks,&nb,ns); if (status) goto done;
  status=exr_edit_doc_create(sections,ns,blocks,nb,parts,np,options,out);
done:
  exr_edit_xml_free(&x); exr_document_free(readonly); blocks_free(blocks,nb); free(sections);
  if (parts) for (i=0;i<np;i++) { free((void *)parts[i].name); mz_free((void *)parts[i].data); }
  free(parts); if (opened) mz_zip_reader_end(&zip);
  return status ? (e && e->code==status && e->message[0] ? status :
    exr_fail(e,status,"Cannot read editable DOCX")) : EXR_OK;
}
exr_status exr_edit_docx_open(const char *path,const exr_edit_options *options,exr_edit_doc **out,exr_error *e) {
  unsigned char *data=NULL; size_t size=0; exr_status status;
  if (!out) return exr_fail(e,EXR_ARGUMENT,"Missing editable document output");
  *out=NULL;
  if (!path) return exr_fail(e,EXR_ARGUMENT,"Missing DOCX path");
  status=exr_read(path,&data,&size,e);
  if (!status) status=exr_edit_docx_read(data,size,options,out,e);
  free(data); return status;
}

typedef struct { size_t start,name,end,value,length; } attr_span;
/* Lex only a validated start tag, keeping quotes, whitespace and unknown
   attributes byte-for-byte. Expat, rather than this lexer, validates XML. */
static int next_attr(const char *s,size_t end,size_t *at,attr_span *a) {
  char quote; size_t p=*at;
  while (p<end && isspace((unsigned char)s[p])) p++;
  if (p==end || s[p]=='/' || s[p]=='>') return 0;
  a->start=*at; a->name=p;
  while (p<end && !isspace((unsigned char)s[p]) && s[p]!='=') p++;
  a->length=p-a->name;
  while (p<end && isspace((unsigned char)s[p])) p++;
  if (p==end || s[p++]!='=') return 0;
  while (p<end && isspace((unsigned char)s[p])) p++;
  if (p==end || (s[p]!='\'' && s[p]!='\"')) return 0;
  quote=s[p++]; a->value=p;
  while (p<end && s[p]!=quote) p++;
  if (p==end) return 0;
  a->end=p+1; *at=a->end; return 1;
}
static size_t tag_name_end(const source_xml *x,size_t n) {
  size_t p=x->spans[n].start+1;
  while (p<x->spans[n].open && !isspace((unsigned char)x->bytes[p]) && x->bytes[p]!='/' && x->bytes[p]!='>') p++;
  return p;
}
static int namespaced_attribute(const source_xml *x,size_t n,const attr_span *a,const char *key,int relationship) {
  const char *s=x->bytes,*colon=memchr(s+a->name,':',a->length); size_t prefix,i;
  if (!colon || a->length-(size_t)(colon-(s+a->name))-1!=strlen(key) ||
      memcmp(colon+1,key,strlen(key))) return 0;
  prefix=(size_t)(colon-(s+a->name));
  for (i=n;i!=NONE;i=x->tree->nodes[i].parent) if (x->tree->nodes[i].name) {
    size_t at=tag_name_end(x,i); attr_span v;
    while (next_attr(s,x->spans[i].open,&at,&v)) if (v.length==prefix+6 &&
        !memcmp(s+v.name,"xmlns:",6) && !memcmp(s+v.name+6,s+a->name,prefix)) {
      size_t len=v.end-v.value-1;
      return relationship ? ((len==sizeof(R)-1 && !memcmp(s+v.value,R,len)) ||
        (len==sizeof(RS)-1 && !memcmp(s+v.value,RS,len))) :
        ((len==sizeof(W)-1 && !memcmp(s+v.value,W,len)) ||
        (len==sizeof(WS)-1 && !memcmp(s+v.value,WS,len)));
    }
  }
  return 0;
}
const char *exr_edit_xml_ns(const source_xml *x) {
  return x->tree && x->root!=NONE && exr_edit_xml_word(x->tree->nodes+x->root,"document") &&
    !strncmp(x->tree->nodes[x->root].name,WS "|",sizeof(WS)) ? WS : W;
}
static void unused_prefix(const source_xml *x,const char *base,char prefix[64]) {
  unsigned suffix=0; size_t i,len; int found;
  do {
    snprintf(prefix,64,"%s%u",base,suffix++); len=strlen(prefix); found=0;
    for (i=0;i+len<=x->size;i++) if (!memcmp(x->bytes+i,prefix,len)) { found=1; break; }
  } while (found);
}
int exr_edit_xml_start(exr_buffer *b,const source_xml *x,size_t n,const char *tag) {
  return n!=NONE ? exr_append(b,x->bytes+x->spans[n].start,x->spans[n].open-x->spans[n].start-
      (x->spans[n].open>=2 && x->bytes[x->spans[n].open-2]=='/' ? 2 : 1)) && put(b,">") :
    put(b,"<w:") && put(b,tag) && put(b," xmlns:w=\"") && put(b,exr_edit_xml_ns(x)) && put(b,"\" xmlns:r=\"") && put(b,R) && put(b,"\">");
}
int exr_edit_xml_end(exr_buffer *b,const source_xml *x,size_t n,const char *tag) {
  if (n!=NONE && x->spans[n].close<x->spans[n].end)
    return exr_append(b,x->bytes+x->spans[n].close,x->spans[n].end-x->spans[n].close);
  if (n!=NONE) {
    size_t end=tag_name_end(x,n);
    return put(b,"</") && exr_append(b,x->bytes+x->spans[n].start+1,end-x->spans[n].start-1) && put(b,">");
  }
  return put(b,"</w:") && put(b,tag) && put(b,">");
}
/* A section can move off its original paragraph after insert/split/delete.
   Carry the visible namespace bindings with it, including those used only by
   opaque descendants. Closer declarations shadow more distant ancestors. */
static int section_start(exr_buffer *b,const source_xml *x,size_t n) {
  size_t ancestor,i,at; attr_span a,v;
  if (!exr_edit_xml_start(b,x,n,"sectPr")) return 0;
  if (n==NONE || x->tree->nodes[n].parent==x->body) return 1;
  b->size--;
  for (ancestor=x->tree->nodes[n].parent;ancestor!=NONE;ancestor=x->tree->nodes[ancestor].parent) {
    if (!x->tree->nodes[ancestor].name) continue;
    at=tag_name_end(x,ancestor);
    while (next_attr(x->bytes,x->spans[ancestor].open,&at,&a)) {
      int shadowed=0;
      if (!((a.length==5 && !memcmp(x->bytes+a.name,"xmlns",5)) ||
          (a.length>6 && !memcmp(x->bytes+a.name,"xmlns:",6)))) continue;
      for (i=n;i!=ancestor && !shadowed;i=x->tree->nodes[i].parent) if (x->tree->nodes[i].name) {
        size_t inner=tag_name_end(x,i);
        while (next_attr(x->bytes,x->spans[i].open,&inner,&v))
          if (v.length==a.length && !memcmp(x->bytes+v.name,x->bytes+a.name,a.length)) { shadowed=1; break; }
      }
      if (!shadowed && !exr_append(b,x->bytes+a.start,a.end-a.start)) return 0;
    }
  }
  return put(b,">");
}
int exr_edit_xml_attrs(exr_buffer *b,const source_xml *x,size_t n,const char *tag,
                         const attr_edit *edits,size_t count) {
  size_t i,at,name_end=0; attr_span a; char prefix[64]="w",rel_prefix[64]; int declare=0,relation=0;
  if (n!=NONE) {
    const char *colon; size_t length;
    name_end=tag_name_end(x,n); length=name_end-x->spans[n].start-1;
    colon=memchr(x->bytes+x->spans[n].start+1,':',length);
    if (colon && (size_t)(colon-x->bytes-x->spans[n].start-1)<sizeof(prefix)) {
      length=(size_t)(colon-x->bytes-x->spans[n].start-1);
      memcpy(prefix,x->bytes+x->spans[n].start+1,length); prefix[length]=0;
    } else {
      /* A fresh prefix cannot shadow a binding used by opaque descendants. */
      unused_prefix(x,"exrEditW",prefix);
      declare=1;
    }
    if (!exr_append(b,x->bytes+x->spans[n].start,name_end-x->spans[n].start)) return 0;
  } else {
    declare=1;
    if (!put(b,"<w:") || !put(b,tag)) return 0;
  }
  if (declare && (!put(b," xmlns:") || !put(b,prefix) || !put(b,"=\"") || !put(b,exr_edit_xml_ns(x)) || !put(b,"\""))) return 0;
  for (i=0;i<count;i++) if (!strncmp(edits[i].key,"r:",2) && edits[i].value) relation=1;
  if (relation) {
    unused_prefix(x,"exrEditR",rel_prefix);
    if (!put(b," xmlns:") || !put(b,rel_prefix) || !put(b,"=\"") ||
        !put(b,!strcmp(exr_edit_xml_ns(x),WS) ? RS : R) || !put(b,"\"")) return 0;
  }
  if (n!=NONE) {
    at=tag_name_end(x,n);
    while (next_attr(x->bytes,x->spans[n].open,&at,&a)) {
      int skip=0;
      for (i=0;i<count && !skip;i++) {
        int rel=!strncmp(edits[i].key,"r:",2);
        if (namespaced_attribute(x,n,&a,edits[i].key+(rel ? 2 : 0),rel)) skip=1;
      }
      if (!skip && !exr_append(b,x->bytes+a.start,a.end-a.start)) return 0;
    }
  }
  for (i=0;i<count;i++) if (edits[i].value &&
      (!put(b," ") || !put(b,!strncmp(edits[i].key,"r:",2) ? rel_prefix : prefix) || !put(b,":") ||
       !put(b,edits[i].key+(!strncmp(edits[i].key,"r:",2) ? 2 : 0)) || !put(b,"=\"") ||
       !escaped(b,edits[i].value,strlen(edits[i].value)) || !put(b,"\""))) return 0;
  if (n==NONE || x->spans[n].open==x->spans[n].end) return put(b,"/>");
  return put(b,">") && exr_append(b,x->bytes+x->spans[n].open,x->spans[n].close-x->spans[n].open) &&
    exr_append(b,x->bytes+x->spans[n].close,x->spans[n].end-x->spans[n].close);
}
static int scalar(exr_buffer *b,const source_xml *x,size_t n,const char *tag,const char *value) {
  attr_edit a={"val",value}; return exr_edit_xml_attrs(b,x,n,tag,&a,1);
}
static int run_equal(const exr_edit_run_props *a,const exr_edit_run_props *b,unsigned bit) {
  if ((a->present&bit)!=(b->present&bit)) return 0;
  if (!(a->present&bit)) return 1;
  switch (bit) {
    case EXR_EDIT_FONT: return !strcmp(a->font,b->font);
    case EXR_EDIT_SIZE: return a->size_half_points==b->size_half_points;
    case EXR_EDIT_BOLD: return a->bold==b->bold;
    case EXR_EDIT_ITALIC: return a->italic==b->italic;
    default: return a->color_rgb==b->color_rgb;
  }
}
static int para_equal(const exr_edit_para_props *a,const exr_edit_para_props *b,unsigned bit) {
  if ((a->present&bit)!=(b->present&bit)) return 0;
  if (!(a->present&bit)) return 1;
  switch (bit) {
    case EXR_EDIT_ALIGN: return a->alignment==b->alignment;
    case EXR_EDIT_INDENT: return a->indent_left==b->indent_left && a->indent_right==b->indent_right && a->indent_first_line==b->indent_first_line;
    case EXR_EDIT_SPACING: return a->space_before==b->space_before && a->space_after==b->space_after && a->line==b->line && a->line_rule==b->line_rule;
    case EXR_EDIT_KEEP_NEXT: return a->keep_next==b->keep_next;
    case EXR_EDIT_KEEP_LINES: return a->keep_lines==b->keep_lines;
    case EXR_EDIT_PAGE_BEFORE: return a->page_break_before==b->page_break_before;
    default: return a->numbering_id==b->numbering_id && a->numbering_level==b->numbering_level;
  }
}
static const char *const rt[]={"rFonts","b","i","color","sz","szCs"};
static const unsigned rb[]={EXR_EDIT_FONT,EXR_EDIT_BOLD,EXR_EDIT_ITALIC,EXR_EDIT_COLOR,EXR_EDIT_SIZE,EXR_EDIT_SIZE};
/* ECMA property ordering for the supported subset. New properties are inserted
   before the next existing supported property; unknown children stay in place. */
static const char *const pt[]={"keepNext","keepLines","pageBreakBefore","numPr","spacing","ind","jc"};
static const unsigned pb[]={EXR_EDIT_KEEP_NEXT,EXR_EDIT_KEEP_LINES,EXR_EDIT_PAGE_BEFORE,EXR_EDIT_NUMBERING,EXR_EDIT_SPACING,EXR_EDIT_INDENT,EXR_EDIT_ALIGN};
static int property_rank(const char *name,int paragraph) {
  const char *order=paragraph==2 ?
    "|headerReference|footerReference|footnotePr|endnotePr|type|pgSz|pgMar|paperSrc|pgBorders|lnNumType|pgNumType|cols|formProt|vAlign|noEndnote|titlePg|textDirection|bidi|rtlGutter|docGrid|printerSettings|sectPrChange|" : paragraph ?
    "|pStyle|keepNext|keepLines|pageBreakBefore|framePr|widowControl|numPr|suppressLineNumbers|pBdr|shd|tabs|suppressAutoHyphens|kinsoku|wordWrap|overflowPunct|topLinePunct|autoSpaceDE|autoSpaceDN|bidi|adjustRightInd|snapToGrid|spacing|ind|contextualSpacing|mirrorIndents|suppressOverlap|jc|textDirection|textAlignment|textboxTightWrap|outlineLvl|divId|cnfStyle|rPr|sectPr|pPrChange|" :
    "|rStyle|rFonts|b|bCs|i|iCs|caps|smallCaps|strike|dstrike|outline|shadow|emboss|imprint|noProof|snapToGrid|vanish|webHidden|color|spacing|w|kern|position|sz|szCs|highlight|u|effect|bdr|shd|fitText|vertAlign|rtl|cs|em|lang|eastAsianLayout|specVanish|oMath|rPrChange|";
  char token[64]; const char *found;
  snprintf(token,sizeof(token),"|%s|",name); found=strstr(order,token);
  return found ? (int)(found-order) : -1;
}
static int emit_run_prop(exr_buffer *b,const source_xml *x,size_t n,size_t k,const exr_edit_run_props *p) {
  char value[32];
  if (!(p->present&rb[k])) return 1;
  if (k==0) { attr_edit a[]={{"ascii",p->font},{"hAnsi",p->font},{"eastAsia",p->font},{"cs",p->font},
      {"asciiTheme",NULL},{"hAnsiTheme",NULL},{"eastAsiaTheme",NULL},{"cstheme",NULL}};
    return exr_edit_xml_attrs(b,x,n,rt[k],a,sizeof(a)/sizeof(a[0])); }
  if (k==1 || k==2) return scalar(b,x,n,rt[k],(k==1 ? p->bold : p->italic) ? "1" : "0");
  if (k==3) {
    attr_edit a[]={{"val",value},{"themeColor",NULL},{"themeTint",NULL},{"themeShade",NULL}};
    snprintf(value,sizeof(value),"%06X",p->color_rgb); return exr_edit_xml_attrs(b,x,n,rt[k],a,4);
  }
  snprintf(value,sizeof(value),"%u",p->size_half_points); return scalar(b,x,n,rt[k],value);
}
static int emit_para_prop(exr_buffer *b,const source_xml *x,size_t n,size_t k,const exr_edit_para_props *p) {
  char v[4][32]; size_t i;
  if (!(p->present&pb[k])) return 1;
  if (k<3) return scalar(b,x,n,pt[k],(k==0 ? p->keep_next : k==1 ? p->keep_lines : p->page_break_before) ? "1" : "0");
  if (k==3) {
    size_t j,at=n==NONE ? 0 : x->spans[n].open; unsigned seen=0;
    snprintf(v[0],32,"%u",p->numbering_level); snprintf(v[1],32,"%u",p->numbering_id);
    if (!exr_edit_xml_start(b,x,n,"numPr")) return 0;
    if (n!=NONE) for (j=x->tree->nodes[n].first_child;j!=NONE;j=x->tree->nodes[j].next_sibling) {
      if (!x->tree->nodes[j].name) continue;
      if (!exr_append(b,x->bytes+at,x->spans[j].start-at)) return 0;
      if (exr_edit_xml_word(x->tree->nodes+j,"ilvl")) { if (!scalar(b,x,j,"ilvl",v[0])) return 0; seen|=1; }
      else if (exr_edit_xml_word(x->tree->nodes+j,"numId")) { if (!(seen&1) && !scalar(b,x,NONE,"ilvl",v[0])) return 0;
        if (!scalar(b,x,j,"numId",v[1])) return 0;
        seen|=3; }
      else if (!exr_edit_xml_raw(b,x,j)) return 0;
      at=x->spans[j].end;
    }
    if (!(seen&1) && !scalar(b,x,NONE,"ilvl",v[0])) return 0;
    if (!(seen&2) && !scalar(b,x,NONE,"numId",v[1])) return 0;
    return (n==NONE || exr_append(b,x->bytes+at,x->spans[n].close-at)) && exr_edit_xml_end(b,x,n,"numPr");
  }
  if (k==4) {
    const exr_node *nd=n==NONE ? NULL : x->tree->nodes+n;
    int has_b=p->space_before!=0 || (nd && exr_edit_xml_wa(nd,"before")) || (!p->space_after && !p->line);
    int has_a=p->space_after!=0 || (nd && exr_edit_xml_wa(nd,"after"));
    int has_l=p->line!=0 || (nd && exr_edit_xml_wa(nd,"line"));
    const char *rule=p->line_rule==EXR_EDIT_LINE_EXACT ? "exact" : p->line_rule==EXR_EDIT_LINE_AT_LEAST ? "atLeast" : "auto";
    attr_edit a[]={{"before",has_b ? v[0] : NULL},{"after",has_a ? v[1] : NULL},{"line",has_l ? v[2] : NULL},{"lineRule",has_l ? rule : NULL}};
    snprintf(v[0],32,"%u",p->space_before); snprintf(v[1],32,"%u",p->space_after); snprintf(v[2],32,"%u",p->line);
    return exr_edit_xml_attrs(b,x,n,"spacing",a,4);
  }
  if (k==5) {
    const exr_node *nd=n==NONE ? NULL : x->tree->nodes+n;
    int has_l=p->indent_left!=0 || (nd && (exr_edit_xml_wa(nd,"left") || exr_edit_xml_wa(nd,"start"))) || (!p->indent_right && !p->indent_first_line);
    int has_r=p->indent_right!=0 || (nd && (exr_edit_xml_wa(nd,"right") || exr_edit_xml_wa(nd,"end")));
    int has_f=p->indent_first_line!=0 || (nd && (exr_edit_xml_wa(nd,"firstLine") || exr_edit_xml_wa(nd,"hanging")));
    attr_edit a[]={{"left",has_l ? v[0] : NULL},{"right",has_r ? v[1] : NULL},{"firstLine",NULL},{"hanging",NULL},{"start",NULL},{"end",NULL}};
    snprintf(v[0],32,"%d",p->indent_left); snprintf(v[1],32,"%d",p->indent_right);
    snprintf(v[2],32,"%lld",p->indent_first_line<0 ? -(long long)p->indent_first_line : (long long)p->indent_first_line);
    if (has_f) a[p->indent_first_line<0 ? 3 : 2].value=v[2];
    return exr_edit_xml_attrs(b,x,n,"ind",a,6);
  }
  i=(size_t)p->alignment; return scalar(b,x,n,"jc",i==1 ? "center" : i==2 ? "right" : i==3 ? "both" : "left");
}
static int append_section(exr_buffer *b,const source_xml *x,size_t n,const exr_buffer *section) {
  return section ? exr_append(b,section->data,section->size) : exr_edit_xml_raw(b,x,n);
}
static int write_properties(exr_buffer *b,const source_xml *x,size_t n,const void *props,int paragraph,
                            size_t section,const exr_buffer *section_data) {
  exr_edit_para_props op; exr_edit_run_props orp;
  const char *const *tags=paragraph ? pt : rt; const unsigned *bits=paragraph ? pb : rb;
  size_t count=paragraph ? 7 : 6,i,k,at=n==NONE ? 0 : x->spans[n].open; unsigned changed=0,seen=0;
  if (paragraph) exr_edit_xml_para_props(x,n,&op); else run_props(x,n,&orp);
  for (k=0;k<count;k++) if (!(paragraph ? para_equal(&op,props,bits[k]) : run_equal(&orp,props,bits[k]))) changed|=1u<<k;
  if (!changed && (!paragraph || (exr_edit_xml_child(x,n,"sectPr")==section && (!section_data ||
      (section!=NONE && section_data->size==x->spans[section].end-x->spans[section].start &&
       !memcmp(section_data->data,x->bytes+x->spans[section].start,section_data->size)))))) return exr_edit_xml_raw(b,x,n);
  if (!exr_edit_xml_start(b,x,n,paragraph ? "pPr" : "rPr")) return 0;
  if (n!=NONE) for (i=x->tree->nodes[n].first_child;i!=NONE;i=x->tree->nodes[i].next_sibling) {
    if (!x->tree->nodes[i].name) continue;
    if (!exr_append(b,x->bytes+at,x->spans[i].start-at)) return 0;
    for (k=0;k<count && !exr_edit_xml_word(x->tree->nodes+i,tags[k]);k++) {}
    /* Insert missing earlier properties, but do not duplicate ones that already
       exist later in the source. */
    { size_t j; const char *local=strrchr(x->tree->nodes[i].name,'|'); int rank=-1;
      if (local && exr_edit_xml_word(x->tree->nodes+i,local+1)) rank=property_rank(local+1,paragraph);
      for (j=0;j<count;j++) if ((changed&(1u<<j)) && !(seen&(1u<<j)) && exr_edit_xml_child(x,n,tags[j])==NONE &&
          rank>property_rank(tags[j],paragraph)) {
        if (!(paragraph ? emit_para_prop(b,x,NONE,j,props) : emit_run_prop(b,x,NONE,j,props))) return 0;
        seen|=1u<<j;
      }
    }
    if (paragraph && exr_edit_xml_word(x->tree->nodes+i,"sectPr")) {
      if (!append_section(b,x,section,section_data)) return 0;
      section=NONE; section_data=NULL;
    }
    else if (k<count && (changed&(1u<<k))) {
      if (!(paragraph ? emit_para_prop(b,x,i,k,props) : emit_run_prop(b,x,i,k,props))) return 0;
    } else if (!exr_edit_xml_raw(b,x,i)) return 0;
    if (k<count) seen|=1u<<k;
    at=x->spans[i].end;
  }
  for (k=0;k<count;k++) if ((changed&(1u<<k)) && !(seen&(1u<<k)) &&
      !(paragraph ? emit_para_prop(b,x,NONE,k,props) : emit_run_prop(b,x,NONE,k,props))) return 0;
  return (n==NONE || exr_append(b,x->bytes+at,x->spans[n].close-at)) &&
    append_section(b,x,section,section_data) && exr_edit_xml_end(b,x,n,paragraph ? "pPr" : "rPr");
}
static int text_start(exr_buffer *b,const source_xml *x,size_t n) {
  size_t at; attr_span a;
  if (n==NONE) return put(b,"<w:t xmlns:w=\"") && put(b,exr_edit_xml_ns(x)) && put(b,"\" xml:space=\"preserve\">");
  at=tag_name_end(x,n);
  if (!exr_append(b,x->bytes+x->spans[n].start,at-x->spans[n].start)) return 0;
  while (next_attr(x->bytes,x->spans[n].open,&at,&a)) if (!(a.length==9 && !memcmp(x->bytes+a.name,"xml:space",9)) &&
      !exr_append(b,x->bytes+a.start,a.end-a.start)) return 0;
  return put(b," xml:space=\"preserve\">");
}
static int write_run(exr_buffer *b,const source_xml *x,const exr_edit_run *r,size_t parent) {
  size_t n,pr,i,j,at; exr_buffer text={0}; int same;
  if (r->kind==EXR_EDIT_OPAQUE_RUN) return exr_append(b,r->opaque_xml,r->opaque_size);
  n=exr_edit_xml_locate(x,r->opaque_xml,r->opaque_size,"r",parent); pr=exr_edit_xml_child(x,n,"rPr");
  if (n!=NONE) {
    for (i=x->tree->nodes[n].first_child;i!=NONE;i=x->tree->nodes[i].next_sibling) if (exr_edit_xml_word(x->tree->nodes+i,"t"))
      for (j=x->tree->nodes[i].first_child;j!=NONE;j=x->tree->nodes[j].next_sibling)
        if (x->tree->nodes[j].text && !put(&text,x->tree->nodes[j].text)) { free(text.data); return 0; }
  }
  same=text.size==r->text_size && (!text.size || !memcmp(text.data,r->text,text.size)); free(text.data);
  if (!exr_edit_xml_start(b,x,n,"r") || !write_properties(b,x,pr,&r->props,0,NONE,NULL)) return 0;
  if (n!=NONE && same) {
    at=x->spans[n].open;
    for (i=x->tree->nodes[n].first_child;i!=NONE;i=x->tree->nodes[i].next_sibling) if (x->tree->nodes[i].name) {
      if (!exr_append(b,x->bytes+at,x->spans[i].start-at) || (i!=pr && !exr_edit_xml_raw(b,x,i))) return 0;
      at=x->spans[i].end;
    }
    if (!exr_append(b,x->bytes+at,x->spans[n].close-at)) return 0;
  } else {
    size_t t=exr_edit_xml_child(x,n,"t");
    if (!text_start(b,x,t) || !escaped(b,r->text,r->text_size) || !exr_edit_xml_end(b,x,t,"t")) return 0;
  }
  return exr_edit_xml_end(b,x,n,"r");
}
int exr_edit_xml_paragraph(exr_buffer *b,const source_xml *x,const exr_edit_block *p,size_t section,const exr_buffer *section_data) {
  size_t i=0,n=exr_edit_xml_locate(x,p->opaque_xml,p->opaque_size,"p",NONE),pr=exr_edit_xml_child(x,n,"pPr");
  if (!exr_edit_xml_start(b,x,n,"p")) return 0;
  /* The decoder retains lexical bytes preceding pPr as the first opaque run.
     Emit that run before the properties, without moving comments/PIs across it.
     A split that no longer owns the run must not duplicate the source trivia. */
  if (pr!=NONE && p->run_count && p->runs[0].kind==EXR_EDIT_OPAQUE_RUN &&
      p->runs[0].opaque_size==x->spans[pr].start-x->spans[n].open &&
      !memcmp(p->runs[0].opaque_xml,x->bytes+x->spans[n].open,p->runs[0].opaque_size)) {
    if (!write_run(b,x,p->runs,n)) return 0;
    i=1;
  }
  if (!write_properties(b,x,pr,&p->props,1,section,section_data)) return 0;
  for (;i<p->run_count;i++) if (!write_run(b,x,p->runs+i,n)) return 0;
  return exr_edit_xml_end(b,x,n,"p");
}
static int reference_slot(const exr_node *n) {
  const char *type=exr_edit_xml_wa(n,"type"); int kind;
  if (exr_edit_xml_word(n,"headerReference")) kind=0;
  else if (exr_edit_xml_word(n,"footerReference")) kind=3;
  else return -1;
  if (!type || !strcmp(type,"default")) return kind;
  if (!strcmp(type,"first")) return kind+1;
  if (!strcmp(type,"even")) return kind+2;
  return -1;
}
static int write_reference(exr_buffer *b,const source_xml *x,size_t n,size_t slot,const char *id) {
  static const char *types[]={"default","first","even"};
  attr_edit edits[]={{"type",types[slot%3]},{"r:id",id}};
  return !*id || exr_edit_xml_attrs(b,x,n,slot<3 ? "headerReference" : "footerReference",edits,2);
}
static int missing_references(exr_buffer *b,const source_xml *x,const exr_edit_section *s,unsigned seen,
                              size_t kind,int header) {
  size_t i;
  for (i=0;i<3;i++) if (!(seen&(1u<<(kind*3+i)))) {
    const char *id=kind ? s->footer_refs[i] : s->header_refs[i];
    if (!*id && !kind && !i && header) id="exrHeader";
    if (!write_reference(b,x,NONE,kind*3+i,id)) return 0;
  }
  return 1;
}
static int section_xml(exr_buffer *b,const source_xml *x,size_t n,const exr_edit_section *s,int header) {
  exr_edit_section old; char v[8][32]; attr_edit sz[3],mar[6]; size_t i,at=n==NONE ? 0 : x->spans[n].open;
  int size_seen=0,margin_seen=0; unsigned seen=0; size_t emitted=0;
  section_props(x,n,&old); old.id=s->id;
  if (n!=NONE && !memcmp(&old,s,sizeof(old))) {
    if (x->tree->nodes[n].parent==x->body) return exr_edit_xml_raw(b,x,n);
    return section_start(b,x,n) && exr_append(b,x->bytes+x->spans[n].open,x->spans[n].close-x->spans[n].open) &&
      exr_edit_xml_end(b,x,n,"sectPr");
  }
  snprintf(v[0],32,"%d",s->page_width); snprintf(v[1],32,"%d",s->page_height);
  sz[0]=(attr_edit){"w",v[0]}; sz[1]=(attr_edit){"h",v[1]}; sz[2]=(attr_edit){"orient",s->landscape ? "landscape" : NULL};
  snprintf(v[2],32,"%d",s->margin_top); snprintf(v[3],32,"%d",s->margin_right);
  snprintf(v[4],32,"%d",s->margin_bottom); snprintf(v[5],32,"%d",s->margin_left);
  snprintf(v[6],32,"%d",s->header_distance); snprintf(v[7],32,"%d",s->footer_distance);
  mar[0]=(attr_edit){"top",v[2]}; mar[1]=(attr_edit){"right",v[3]}; mar[2]=(attr_edit){"bottom",v[4]};
  mar[3]=(attr_edit){"left",v[5]}; mar[4]=(attr_edit){"header",v[6]}; mar[5]=(attr_edit){"footer",v[7]};
  if (!section_start(b,x,n)) return 0;
  if (n!=NONE) for (i=x->tree->nodes[n].first_child;i!=NONE;i=x->tree->nodes[i].next_sibling) {
    int slot=reference_slot(x->tree->nodes+i);
    if (slot>=0) seen|=1u<<(unsigned)slot;
  }
  if (n!=NONE) for (i=x->tree->nodes[n].first_child;i!=NONE;i=x->tree->nodes[i].next_sibling) if (x->tree->nodes[i].name) {
    int slot=reference_slot(x->tree->nodes+i);
    const char *local=strrchr(x->tree->nodes[i].name,'|');
    int rank=local && exr_edit_xml_word(x->tree->nodes+i,local+1) ? property_rank(local+1,2) : -1;
    size_t kind=exr_edit_xml_word(x->tree->nodes+i,"headerReference") ? 0 : exr_edit_xml_word(x->tree->nodes+i,"footerReference") ? 1 : 2;
    while (emitted<kind) {
      if (!missing_references(b,x,s,seen,emitted,0)) return 0;
      emitted++;
    }
    if (!exr_append(b,x->bytes+at,x->spans[i].start-at)) return 0;
    if (!size_seen && exr_edit_xml_child(x,n,"pgSz")==NONE && rank>property_rank("pgSz",2)) {
      if (!exr_edit_xml_attrs(b,x,NONE,"pgSz",sz,3)) return 0;
      size_seen=1;
    }
    if (!margin_seen && exr_edit_xml_child(x,n,"pgMar")==NONE && rank>property_rank("pgMar",2)) {
      if (!exr_edit_xml_attrs(b,x,NONE,"pgMar",mar,6)) return 0;
      margin_seen=1;
    }
    if (slot>=0) {
      const char *id=slot<3 ? s->header_refs[slot] : s->footer_refs[slot-3];
      const char *previous=slot<3 ? old.header_refs[slot] : old.footer_refs[slot-3];
      if (!(strcmp(id,previous) ? write_reference(b,x,i,(size_t)slot,id) : exr_edit_xml_raw(b,x,i))) return 0;
    }
    else if (exr_edit_xml_word(x->tree->nodes+i,"pgSz")) { if (!exr_edit_xml_attrs(b,x,i,"pgSz",sz,3)) return 0; size_seen=1; }
    else if (exr_edit_xml_word(x->tree->nodes+i,"pgMar")) { if (!exr_edit_xml_attrs(b,x,i,"pgMar",mar,6)) return 0; margin_seen=1; }
    else if (!exr_edit_xml_raw(b,x,i)) return 0;
    at=x->spans[i].end;
  }
  while (emitted<2) {
    if (!missing_references(b,x,s,seen,emitted,header)) return 0;
    emitted++;
  }
  if (!size_seen && !exr_edit_xml_attrs(b,x,NONE,"pgSz",sz,3)) return 0;
  if (!margin_seen && !exr_edit_xml_attrs(b,x,NONE,"pgMar",mar,6)) return 0;
  return (n==NONE || exr_append(b,x->bytes+at,x->spans[n].close-at)) && exr_edit_xml_end(b,x,n,"sectPr");
}

/* Only lexical gaps may follow a section-ending paragraph. An opaque element
   can contain visible content and must stay before that section's break. */
static int trivia_block(const exr_edit_block *b) {
  const char *s=b->opaque_xml; size_t i=0,n=b->opaque_size;
  if (b->kind!=EXR_EDIT_OPAQUE_BLOCK) return 0;
  while (i<n) {
    const char *end; size_t length;
    if (isspace((unsigned char)s[i])) { i++; continue; }
    if (n-i>=4 && !memcmp(s+i,"<!--",4)) { i+=4; end="-->"; length=3; }
    else if (n-i>=2 && !memcmp(s+i,"<?",2)) { i+=2; end="?>"; length=2; }
    else return 0;
    while (n-i>=length && memcmp(s+i,end,length)) i++;
    if (n-i<length) return 0;
    i+=length;
  }
  return 1;
}

int exr_edit_zip_add_part(mz_zip_archive *zip,const char *name,const void *data,size_t size) {
  MZ_TIME_T modified={0};
#ifndef MINIZ_NO_TIME
  /* Fixed local ZIP epoch keeps an unchanged model byte-identical across writes. */
  struct tm epoch={0};
  epoch.tm_year=80; epoch.tm_mday=1; epoch.tm_isdst=-1;
  modified=mktime(&epoch);
#endif
  return mz_zip_writer_add_mem_ex_v2(zip,name,data,size,NULL,0,6,0,0,&modified,NULL,0,NULL,0);
}

exr_status exr_edit_docx_write(const exr_edit_doc *doc,void **data,size_t *size,exr_error *e) {
  const exr_edit_part *parts,*p; const exr_edit_section *sections;
  size_t np,ns,nb,i,j,si=0,*sn=NULL; char main[2048]; source_xml x={0};
  exr_buffer xml={0},section={0}; mz_zip_archive zip={0}; exr_status status=EXR_MEMORY; int opened=0;
  edit_image_output *images=NULL; size_t image_count=0,image_index=0;
  if (e) memset(e,0,sizeof(*e));
  if (data) *data=NULL;
  if (size) *size=0;
  if (!doc || !data || !size) return exr_fail(e,EXR_ARGUMENT,"Invalid editable DOCX output");
  parts=exr_edit_parts(doc,&np); sections=exr_edit_sections(doc,&ns); nb=exr_edit_block_count(doc);
  if (!ns) return exr_fail(e,EXR_ARGUMENT,"Editable document has no sections");
  for (i=0;i<np;i++) if (!part_path(parts[i].name)) return exr_fail(e,EXR_ARGUMENT,"Invalid DOCX part path");
  strcpy(main,"word/document.xml");
  if (np) { status=exr_edit_main_part(parts,np,main,e); if (status) goto done; }
  p=exr_edit_part_named(parts,np,main);
  if (p) {
    status=exr_edit_xml_parse(&x,p->data,p->size,"document",e); if (status) goto done;
    if (x.body==NONE) { status=EXR_FORMAT; goto done; }
  }
  status=exr_edit_images_prepare(doc,main,&x,&images,&image_count); if (status) goto done;
  status=EXR_MEMORY;
  for (i=0;i<nb;i++) {
    const exr_edit_block *block=exr_edit_block_at(doc,i); size_t node=NONE,k;
    if (block->kind!=EXR_EDIT_PARAGRAPH) continue;
    if (block->opaque_size) {
      node=exr_edit_xml_locate(&x,block->opaque_xml,block->opaque_size,"p",NONE);
      if (node==NONE) { status=exr_fail(e,EXR_UNSUPPORTED,"Paragraph template requires its original DOCX main part"); goto done; }
    }
    for (k=0;k<block->run_count;k++) if (block->runs[k].kind==EXR_EDIT_TEXT && block->runs[k].opaque_size &&
        exr_edit_xml_locate(&x,block->runs[k].opaque_xml,block->runs[k].opaque_size,"r",node)==NONE) {
      status=exr_fail(e,EXR_UNSUPPORTED,"Text run template requires its original DOCX main part"); goto done;
    }
  }
  status=EXR_MEMORY; sn=malloc(ns*sizeof(*sn)); if (!sn) goto done;
  for (i=0;i<ns;i++) sn[i]=NONE;
  if (p) {
    for (i=x.tree->nodes[x.body].first_child;i!=NONE;i=x.tree->nodes[i].next_sibling) {
      size_t s=exr_edit_xml_word(x.tree->nodes+i,"sectPr") ? i : exr_edit_xml_child(&x,exr_edit_xml_child(&x,i,"pPr"),"sectPr");
      if (s!=NONE && si<ns) sn[si++]=s;
    }
    if (!exr_append(&xml,x.bytes,x.spans[x.body].start) || !exr_edit_xml_start(&xml,&x,x.body,"body")) goto done;
  } else if (!put(&xml,"<?xml version=\"1.0\" encoding=\"UTF-8\"?><w:document xmlns:w=\"" W "\" xmlns:r=\"" R "\"><w:body>")) goto done;
  j=0;
  for (si=0;si<ns;si++) {
    exr_edit_section original;
    int emitted=0,paragraph_break=si+1<ns ||
      (sn[si]!=NONE && x.tree->nodes[sn[si]].parent!=x.body);
    section_props(&x,sn[si],&original); original.id=sections[si].id;
    section.size=0;
    if (!section_xml(&section,&x,sn[si],sections+si,!np)) goto done;
    while (j<nb) {
      const exr_edit_block *b=exr_edit_block_at(doc,j); size_t next=j+1;
      if (b->section_id!=sections[si].id) break;
      /* Final body trivia was decoded after sectPr. Keep it there instead of
         silently pulling comments/PIs across the final section boundary. */
      if (!paragraph_break && si+1==ns && sn[si]!=NONE && j+1==nb && trivia_block(b) &&
          b->opaque_size==x.spans[x.body].close-x.spans[sn[si]].end &&
          !memcmp(b->opaque_xml,x.bytes+x.spans[sn[si]].end,b->opaque_size)) {
        if (!exr_append(&xml,section.data,section.size) || !exr_append(&xml,b->opaque_xml,b->opaque_size)) goto done;
        emitted=1; j++; continue;
      }
      while (next<nb && exr_edit_block_at(doc,next)->section_id==b->section_id &&
          (trivia_block(exr_edit_block_at(doc,next)) ||
           (exr_edit_block_at(doc,next)->image && exr_edit_block_at(doc,next)->image->anchor_run_id))) next++;
      if (b->kind==EXR_EDIT_PARAGRAPH) {
        int last=paragraph_break && (next==nb || exr_edit_block_at(doc,next)->section_id!=b->section_id);
        if (last) {
          size_t node=exr_edit_xml_locate(&x,b->opaque_xml,b->opaque_size,"p",NONE);
          /* Its original paragraph still supplies every namespace binding.
             Only relocated or changed sections need the expanded template. */
          const exr_buffer *replacement=sn[si]!=NONE && !memcmp(&original,sections+si,sizeof(original)) &&
            exr_edit_xml_child(&x,exr_edit_xml_child(&x,node,"pPr"),"sectPr")==sn[si] ? NULL : &section;
          if (!exr_edit_xml_paragraph(&xml,&x,b,sn[si],replacement)) goto done;
          emitted=1;
        } else if (!exr_edit_xml_paragraph(&xml,&x,b,NONE,NULL)) goto done;
      } else if (b->kind==EXR_EDIT_PAGE_BREAK) {
        if (!put(&xml,"<w:p xmlns:w=\"") || !put(&xml,exr_edit_xml_ns(&x)) || !put(&xml,"\"><w:r><w:br w:type=\"page\"/></w:r></w:p>")) goto done;
      } else if (b->kind==EXR_EDIT_TABLE) {
        if (!exr_edit_table_write(&xml,&x,b)) goto done;
      } else if (b->kind==EXR_EDIT_IMAGE) {
        if (b->image->anchor_run_id) { j++; continue; }
        if (image_index>=image_count || !exr_edit_image_write(&xml,&x,images+image_index++)) goto done;
      } else if (!exr_append(&xml,b->opaque_xml,b->opaque_size)) goto done;
      j++;
    }
    if (paragraph_break && !emitted) {
      if (!put(&xml,"<w:p xmlns:w=\"") || !put(&xml,exr_edit_xml_ns(&x)) || !put(&xml,"\"><w:pPr>") ||
          !exr_append(&xml,section.data,section.size) || !put(&xml,"</w:pPr></w:p>")) goto done;
    } else if (si+1==ns && !paragraph_break && !emitted &&
        (!p || sn[si]!=NONE || memcmp(&original,sections+si,sizeof(original))) &&
        !exr_append(&xml,section.data,section.size)) goto done;
  }
  if (j!=nb) { status=EXR_ARGUMENT; goto done; }
  if (p) {
    if (!exr_edit_xml_end(&xml,&x,x.body,"body") || !exr_append(&xml,x.bytes+x.spans[x.body].end,x.size-x.spans[x.body].end)) goto done;
  }
  else if (!put(&xml,"</w:body></w:document>")) goto done;
  { exr_document *check=NULL;
    status=exr_xml_memory_tree(xml.data,xml.size,"document",&check,e);
    exr_document_free(check); if (status) goto done;
    status=EXR_MEMORY;
  }
  if (!mz_zip_writer_init_heap(&zip,0,0)) goto done;
  opened=1;
  if (np) {
    status=exr_edit_images_package(&zip,parts,np,main,&xml,images,image_count,e);
    if (status) goto done;
  }
  status=EXR_MEMORY;
  if (!np) {
    const char *types="<Types xmlns=\"http://schemas.openxmlformats.org/package/2006/content-types\"><Default Extension=\"rels\" ContentType=\"application/vnd.openxmlformats-package.relationships+xml\"/><Default Extension=\"xml\" ContentType=\"application/xml\"/><Override PartName=\"/word/document.xml\" ContentType=\"application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml\"/><Override PartName=\"/word/header1.xml\" ContentType=\"application/vnd.openxmlformats-officedocument.wordprocessingml.header+xml\"/><Override PartName=\"/word/styles.xml\" ContentType=\"application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml\"/></Types>";
    const char *rels="<Relationships xmlns=\"http://schemas.openxmlformats.org/package/2006/relationships\"><Relationship Id=\"officeDocument\" Type=\"" R "/officeDocument\" Target=\"word/document.xml\"/></Relationships>";
    const char *dr="<Relationships xmlns=\"http://schemas.openxmlformats.org/package/2006/relationships\"><Relationship Id=\"exrHeader\" Type=\"" R "/header\" Target=\"header1.xml\"/><Relationship Id=\"exrStyles\" Type=\"" R "/styles\" Target=\"styles.xml\"/></Relationships>";
    const char *styles="<w:styles xmlns:w=\"" W "\"><w:docDefaults><w:rPrDefault>" DEFAULT_RPR "</w:rPrDefault></w:docDefaults><w:style w:type=\"paragraph\" w:default=\"1\" w:styleId=\"Normal\"><w:name w:val=\"Normal\"/>" DEFAULT_RPR "</w:style></w:styles>";
    const char *header="<w:hdr xmlns:w=\"" W "\"><w:p><w:pPr><w:spacing w:after=\"0\" w:line=\"240\" w:lineRule=\"auto\"/><w:jc w:val=\"right\"/>" DEFAULT_RPR "</w:pPr><w:fldSimple w:instr=\" PAGE \" w:dirty=\"true\"><w:r>" DEFAULT_RPR "<w:t>1</w:t></w:r></w:fldSimple><w:fldSimple w:instr=\" DATE \\@ &quot;MMMM d, yyyy&quot; \" w:dirty=\"true\"><w:r>" DEFAULT_RPR "<w:t> </w:t></w:r></w:fldSimple></w:p></w:hdr>";
    exr_edit_part base[5]={{0}};
    const char *names[]={"[Content_Types].xml","_rels/.rels","word/_rels/document.xml.rels","word/styles.xml","word/header1.xml"};
    const char *values[]={types,rels,dr,styles,header};
    for (i=0;i<5;i++) { base[i].name=names[i]; base[i].data=values[i]; base[i].size=strlen(values[i]); }
    status=exr_edit_images_package(&zip,base,5,main,&xml,images,image_count,e); if (status) goto done;
    status=EXR_MEMORY;
  }
  if (!exr_edit_zip_add_part(&zip,main,xml.data,xml.size) || !mz_zip_writer_finalize_heap_archive(&zip,data,size)) goto done;
  status=EXR_OK;
done:
  if (status && *data) { mz_free(*data); *data=NULL; *size=0; }
  if (opened) mz_zip_writer_end(&zip);
  free(images); free(sn); free(xml.data); free(section.data); exr_edit_xml_free(&x);
  return status ? (e && e->code==status && e->message[0] ? status :
    exr_fail(e,status,"Cannot write editable DOCX")) : EXR_OK;
}
