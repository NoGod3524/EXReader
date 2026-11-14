/* SPDX-License-Identifier: MIT */
#include "pdf_internal.h"
#include "flow_internal.h"
#include "exr/font_manager.h"
#include <miniz.h>
#include <expat.h>

#define P "http://schemas.openxmlformats.org/presentationml/2006/main|"
#define PS "http://purl.oclc.org/ooxml/presentationml/main|"
#define A "http://schemas.openxmlformats.org/drawingml/2006/main|"
#define AS "http://purl.oclc.org/ooxml/drawingml/main|"
#define R "http://schemas.openxmlformats.org/officeDocument/2006/relationships|"
#define RS "http://purl.oclc.org/ooxml/officeDocument/relationships|"
#define REL "http://schemas.openxmlformats.org/package/2006/relationships|"
#define SLIDE "http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide"
#define SLIDE_STRICT "http://purl.oclc.org/ooxml/officeDocument/relationships/slide"
#define PRESENTATION "ppt/presentation.xml"
#define RELATIONSHIPS "ppt/_rels/presentation.xml.rels"
#define MAX_SLIDES 10000
#define MAX_SHAPES 10000
#define MAX_GROUP_DEPTH 16
#define MAX_STOPS 256
#define MAX_TABLE_DIMENSION 200
#define IMAGE_REL "http://schemas.openxmlformats.org/officeDocument/2006/relationships/image"
#define IMAGE_STRICT "http://purl.oclc.org/ooxml/officeDocument/relationships/image"

typedef enum { RECT,ELLIPSE,ROUND_RECT,TRIANGLE,LINE } pptx_geometry;
typedef struct { double position; uint32_t rgba; } pptx_stop;
typedef struct { char *path; exr_bitmap bitmap; } pptx_image;

/* Resolved values, overlaid from presentation -> master -> list -> paragraph
   -> run. XML strings are borrowed only while the corresponding part is open. */
typedef struct {
  double size,tracking,margin,indent,line,before,after;
  const char *latin,*ea,*cs,*bullet;
  uint32_t color;
  unsigned flags;
  int align,line_pct,before_pct,after_pct,number,start;
} pptx_text_style;
typedef struct { size_t faces[32],count; exr_font *font; } pptx_text_font;
typedef struct { exr_layout *layout; } pptx_paragraph;
typedef struct { double width; uint32_t rgba; unsigned present; } pptx_border;

typedef struct {
  pptx_geometry geometry;
  double width,height,matrix[6];
  exr_draw_style style;
  pptx_stop *stops;
  size_t stop_count,image;
  double angle;
  unsigned texture,tile; /* 1: embedded image, 2: linear gradient. */
  pptx_paragraph *paragraphs;
  size_t paragraph_count,paragraph_capacity;
  pptx_border borders[4]; /* Left, right, top, bottom; table cells only. */
  size_t table_cells; /* 0: shape, SIZE_MAX: cell, otherwise first cell's table size. */
} pptx_shape;

typedef struct {
  char *part_path;
  size_t index; /* Original zero-based position in sldIdLst, before skipping. */
  pptx_shape *shapes;
  size_t count,capacity;
  pptx_shape background;
  pptx_text_style text_styles[3][9];
} pptx_slide;

typedef struct {
  const char *id,*target,*type;
  int external;
} pptx_relationship;

typedef struct {
  mz_zip_archive zip;
  unsigned char *data;
  pptx_slide *slides;
  size_t count,skipped,expanded;
  size_t missing,zero_extent,rotation,depth,color,unsupported,shape_bytes;
  size_t theme_warning,alpha,image_warning,gradient_warning,tile_warning,paint_bytes;
  size_t invalid_utf8;
  uint32_t theme[12];
  uint32_t placeholder;
  exr_document *theme_xml;
  pptx_image *images;
  size_t image_count,image_capacity;
  exr_buffer fallbacks; /* Unique, NUL-separated preset names; owns XML copies. */
  double width,height;
  pptx_text_style default_text[9];
  exr_font_manager *font_manager;
  pptx_text_font *text_fonts;
  size_t text_font_count,text_font_capacity,font_bytes,text_bytes;
  size_t text_scale_warning,text_level_warning;
  size_t table_grid_warning,table_span_warning,table_row_warning,table_height_warning,table_style_warning;
  exr_buffer font_fallbacks,glyph_fallbacks;
} pptx_document;

static void text_free(pptx_shape *shape) {
  size_t i;
  for(i=0;i<shape->paragraph_count;i++) exr_layout_free(shape->paragraphs[i].layout);
  free(shape->paragraphs);
}

static void release(void *context) {
  pptx_document *d=context;
  size_t i,j;
  if(!d) return;
  mz_zip_reader_end(&d->zip);
  for(i=0;i<d->count;i++) {
    free(d->slides[i].part_path);
    free(d->slides[i].background.stops);
    for(j=0;j<d->slides[i].count;j++) {
      free(d->slides[i].shapes[j].stops);
      text_free(&d->slides[i].shapes[j]);
    }
    free(d->slides[i].shapes);
  }
  for(i=0;i<d->image_count;i++) {
    free(d->images[i].path);
    exr_bitmap_free(&d->images[i].bitmap);
  }
  free(d->images);
  exr_document_free(d->theme_xml);
  free(d->fallbacks.data);
  for(i=0;i<d->text_font_count;i++) exr_font_free(d->text_fonts[i].font);
  free(d->text_fonts);
  exr_font_manager_free(d->font_manager);
  free(d->font_fallbacks.data);
  free(d->glyph_fallbacks.data);
  free(d->slides);
  free(d->data);
  free(d);
}

static int named(const exr_node *node,const char *ns,const char *strict,const char *tag) {
  const char *name=node->name;
  size_t n=strlen(ns);
  if(!name) {
    return 0;
  }
  if(!strncmp(name,ns,n) && !strcmp(name+n,tag)) {
    return 1;
  }
  if(!strict) {
    return 0;
  }
  n=strlen(strict);
  return !strncmp(name,strict,n) && !strcmp(name+n,tag);
}

static size_t root(const exr_document *xml) {
  return xml->nodes[xml->chapters[0].root].first_child;
}

static size_t child(const exr_document *xml,size_t parent,const char *tag) {
  size_t i;
  for(i=xml->nodes[parent].first_child;i!=SIZE_MAX;i=xml->nodes[i].next_sibling)
    if(named(&xml->nodes[i],P,PS,tag)) {
      return i;
    }
  return SIZE_MAX;
}

static const char *relationship_id(const exr_node *node) {
  const char *id=exr_node_attribute(node,R "id");
  return id ? id : exr_node_attribute(node,RS "id");
}

/* Check every member, including media which M1 never extracts. This prevents
   unsupported content from bypassing the common 128 MiB input budget. */
static exr_status check_archive(pptx_document *d,const exr_control *control,exr_error *e) {
  mz_uint i,count=mz_zip_reader_get_num_files(&d->zip);
  for(i=0;i<count;i++) {
    mz_zip_archive_file_stat st;
    exr_status status=exr_control_poll(control,EXR_STAGE_READ,i,count,e);
    if(status!=EXR_OK) {
      return status;
    }
    if(!mz_zip_reader_file_stat(&d->zip,i,&st))
      return exr_fail(e,EXR_FORMAT,"Cannot inspect PPTX ZIP directory");
    if(st.m_uncomp_size>EXR_MAX_INPUT)
      return exr_fail(e,EXR_LIMIT,"ZIP member exceeds 128 MiB: %s",st.m_filename);
    if(st.m_is_encrypted)
      return exr_fail(e,EXR_UNSUPPORTED,"Encrypted PPTX ZIP member: %s",st.m_filename);
  }
  return EXR_OK;
}

typedef struct {
  XML_Parser parser;
  unsigned char *data;
  size_t size,depth,handled,skipped;
  struct { size_t start; unsigned run,text,bad; } stack[256];
  int failed,other_encoding;
} pptx_utf8;

static void XMLCALL text_xml_declaration(void *context,const XML_Char *version,
                                        const XML_Char *encoding,int standalone) {
  pptx_utf8 *p=context;
  size_t i=0;
  (void)version; (void)standalone;
  if(!encoding) return;
  while(encoding[i] && "utf-8"[i] && ((unsigned char)encoding[i]|32u)==(unsigned char)"utf-8"[i]) i++;
  if(encoding[i] || "utf-8"[i]) {
    p->other_encoding=1; XML_StopParser(p->parser,XML_FALSE);
  }
}

static void XMLCALL text_xml_start(void *context,const char *name,const char **attributes) {
  pptx_utf8 *p=context;
  exr_node node={0};
  int64_t offset=XML_GetCurrentByteIndex64(p->parser);
  (void)attributes;
  if(p->depth==256 || offset<0) {
    p->failed=1; XML_StopParser(p->parser,XML_FALSE); return;
  }
  node.name=name;
  p->stack[p->depth].start=(size_t)offset;
  p->stack[p->depth].run=(unsigned)named(&node,A,AS,"r");
  p->stack[p->depth].text=(unsigned)named(&node,A,AS,"t");
  p->stack[p->depth++].bad=0;
}

static void XMLCALL text_xml_end(void *context,const char *name) {
  pptx_utf8 *p=context;
  size_t at=--p->depth;
  int64_t offset=XML_GetCurrentByteIndex64(p->parser);
  int64_t count=XML_GetCurrentByteCount64(p->parser);
  (void)name;
  if(p->stack[at].run && p->stack[at].bad && offset>=0 && count>=0 &&
     (size_t)offset<=p->size && (size_t)count<=p->size-(size_t)offset) {
    /* Keep byte offsets stable while the SAX parser reads the separate copy. */
    memset(p->data+p->stack[at].start,' ',(size_t)offset+(size_t)count-p->stack[at].start);
    p->skipped++;
  }
}

static void XMLCALL text_xml_characters(void *context,const XML_Char *text,int length) {
  pptx_utf8 *p=context;
  int64_t offset=XML_GetCurrentByteIndex64(p->parser);
  int64_t count=XML_GetCurrentByteCount64(p->parser);
  size_t at,end,bad=0;
  uint32_t cp;
  (void)text; (void)length;
  if(offset<0 || count<0 || (size_t)offset>p->size || (size_t)count>p->size-(size_t)offset) {
    p->failed=1; XML_StopParser(p->parser,XML_FALSE); return;
  }
  at=(size_t)offset; end=at+(size_t)count;
  while(at<end) if(!exr_next((const char *)p->data,end,&at,&cp)) { bad++; at++; }
  if(!bad) return;
  if(p->depth<2 || !p->stack[p->depth-1].text || !p->stack[p->depth-2].run) {
    p->failed=1; XML_StopParser(p->parser,XML_FALSE); return;
  }
  p->stack[p->depth-2].bad=1;
  p->handled+=bad;
}

static void XMLCALL text_xml_entity(void *context,const XML_Char *name,int parameter,
  const XML_Char *value,int length,const XML_Char *base,const XML_Char *system,
  const XML_Char *public_id,const XML_Char *notation) {
  pptx_utf8 *p=context;
  (void)name; (void)parameter; (void)value; (void)length; (void)base;
  (void)system; (void)public_id; (void)notation;
  p->failed=1; XML_StopParser(p->parser,XML_FALSE);
}

/* Repair only malformed UTF-8 in DrawingML run text. An equal-length scratch
   copy lets Expat validate namespaces, attributes and the entire XML structure
   before the normal tree reader consumes the version with bad runs removed. */
static exr_status skip_invalid_runs(pptx_document *d,void *data,size_t size,
                                    const exr_control *control,exr_error *e) {
  pptx_utf8 p={0};
  unsigned char *copy;
  size_t at=0,bad=0;
  uint32_t cp;
  enum XML_Status parsed;
  /* The XML reader also accepts UTF-16; its byte sequences are not UTF-8. */
  if(size>=2 && ((((unsigned char *)data)[0]==0xff && ((unsigned char *)data)[1]==0xfe) ||
                (((unsigned char *)data)[0]==0xfe && ((unsigned char *)data)[1]==0xff))) return EXR_OK;
  while(at<size && exr_next(data,size,&at,&cp)) {}
  if(at==size) return EXR_OK;
  copy=malloc(size);
  if(!copy) return exr_fail(e,EXR_MEMORY,"PPTX UTF-8 recovery allocation failed");
  memcpy(copy,data,size);
  while(at<size) {
    if(!(at&4095) && exr_control_cancel(control,e)!=EXR_OK) { free(copy); return EXR_CANCELLED; }
    if(!exr_next(data,size,&at,&cp)) { copy[at++]='?'; bad++; }
  }
  p.data=data; p.size=size;
  p.parser=XML_ParserCreateNS(NULL,'|');
  if(!p.parser) { free(copy); return exr_fail(e,EXR_MEMORY,"PPTX UTF-8 parser allocation failed"); }
  XML_SetUserData(p.parser,&p);
  XML_SetXmlDeclHandler(p.parser,text_xml_declaration);
  XML_SetElementHandler(p.parser,text_xml_start,text_xml_end);
  XML_SetCharacterDataHandler(p.parser,text_xml_characters);
  XML_SetEntityDeclHandler(p.parser,text_xml_entity);
  XML_SetParamEntityParsing(p.parser,XML_PARAM_ENTITY_PARSING_NEVER);
  parsed=XML_Parse(p.parser,(const char *)copy,(int)size,XML_TRUE);
  XML_ParserFree(p.parser);
  free(copy);
  if(p.other_encoding) return EXR_OK; /* Leave other declared encodings to the XML reader. */
  if(parsed!=XML_STATUS_OK || p.failed || p.handled!=bad)
    return exr_fail(e,EXR_FORMAT,"Invalid PPTX XML outside recoverable UTF-8 run text");
  d->invalid_utf8+=p.skipped;
  return EXR_OK;
}

/* Each XML part is parsed once at open. Each allocation is charged before
   extraction; the XML tree reader supplies namespace/depth/entity validation. */
static exr_status xml_read(pptx_document *d,const char *path,const char *tag,int optional,
                           const exr_control *control,exr_document **out,exr_error *e) {
  mz_zip_archive_file_stat st;
  int index;
  void *data;
  size_t size;
  exr_status status;
  *out=NULL;
  status=exr_control_cancel(control,e);
  if(status!=EXR_OK) {
    return status;
  }
  index=mz_zip_reader_locate_file(&d->zip,path,NULL,MZ_ZIP_FLAG_CASE_SENSITIVE);
  if(index<0) {
    return optional ? EXR_OK : exr_fail(e,EXR_FORMAT,"PPTX part missing: %s",path);
  }
  if(!mz_zip_reader_file_stat(&d->zip,(mz_uint)index,&st))
    return exr_fail(e,EXR_FORMAT,"Cannot inspect PPTX part: %s",path);
  if(st.m_uncomp_size>EXR_MAX_INPUT-d->expanded-d->paint_bytes)
    return exr_fail(e,EXR_LIMIT,"PPTX metadata exceeds 128 MiB: %s",path);
  size=(size_t)st.m_uncomp_size;
  data=malloc(size ? size : 1);
  if(!data) {
    return exr_fail(e,EXR_MEMORY,"PPTX part allocation failed: %s",path);
  }
  if(!mz_zip_reader_extract_to_mem(&d->zip,(mz_uint)index,data,size,0)) {
    free(data);
    return exr_fail(e,EXR_FORMAT,"Cannot decompress PPTX part: %s",path);
  }
  d->expanded+=size;
  status=exr_control_cancel(control,e);
  if(status==EXR_OK) status=skip_invalid_runs(d,data,size,control,e);
  if(status==EXR_OK) status=exr_xml_memory_tree(data,size,tag,out,e);
  free(data);
  if(status==EXR_FORMAT) {
    return exr_fail(e,status,"Invalid PPTX XML part: %s",path);
  }
  return status;
}

static int compare_relationships(const void *a,const void *b) {
  return strcmp(((const pptx_relationship *)a)->id,((const pptx_relationship *)b)->id);
}

static exr_status read_relationships(const exr_document *xml,pptx_relationship **out,
                                     size_t *count,exr_error *e) {
  size_t i,n=0,parent;
  pptx_relationship *rels;
  *out=NULL;
  *count=0;
  if(!xml) {
    return EXR_OK;
  }
  parent=root(xml);
  if(!named(&xml->nodes[parent],REL,NULL,"Relationships"))
    return exr_fail(e,EXR_FORMAT,"Invalid PPTX relationship namespace");
  for(i=xml->nodes[parent].first_child;i!=SIZE_MAX;i=xml->nodes[i].next_sibling)
    if(named(&xml->nodes[i],REL,NULL,"Relationship")) n++;
  if(n>MAX_SLIDES) {
    return exr_fail(e,EXR_LIMIT,"PPTX relationships exceed 10000");
  }
  if(!n) {
    return EXR_OK;
  }
  rels=calloc(n,sizeof(*rels));
  if(!rels) {
    return exr_fail(e,EXR_MEMORY,"PPTX relationships allocation failed");
  }
  *out=rels;
  for(i=xml->nodes[parent].first_child;i!=SIZE_MAX;i=xml->nodes[i].next_sibling) {
    const exr_node *node=&xml->nodes[i];
    const char *mode;
    pptx_relationship *r;
    if(!named(node,REL,NULL,"Relationship")) continue;
    r=&rels[(*count)++];
    r->id=exr_node_attribute(node,"Id");
    r->target=exr_node_attribute(node,"Target");
    r->type=exr_node_attribute(node,"Type");
    mode=exr_node_attribute(node,"TargetMode");
    r->external=mode && strcmp(mode,"Internal");
    if(!r->id || !*r->id || !r->target || !*r->target || !r->type)
      return exr_fail(e,EXR_FORMAT,"Invalid PPTX relationship in " RELATIONSHIPS);
  }
  qsort(rels,*count,sizeof(*rels),compare_relationships);
  for(i=1;i<*count;i++)
    if(!strcmp(rels[i-1].id,rels[i].id))
      return exr_fail(e,EXR_FORMAT,"Duplicate PPTX relationship ID: %s",rels[i].id);
  return EXR_OK;
}

static const pptx_relationship *find_relationship(const pptx_relationship *rels,
                                                  size_t count,const char *id) {
  size_t lo=0,hi=count;
  if(!id) {
    return NULL;
  }
  while(lo<hi) {
    size_t mid=lo+(hi-lo)/2;
    int order=strcmp(id,rels[mid].id);
    if(!order) {
      return &rels[mid];
    }
    if(order<0) hi=mid;
    else lo=mid+1;
  }
  return NULL;
}

/* Positive integer EMUs, parsed without locale or floating-point overflow.
   The geometry abstraction bounds coordinates to 1e7 points. */
static int dimension(const char *text,double *out) {
  uint64_t value=0;
  const uint64_t maximum=127000000000ULL;
  if(!text || !*text) {
    return 0;
  }
  for(;*text;text++) {
    unsigned digit=(unsigned char)*text-'0';
    if(digit>9 || value>(maximum-digit)/10) {
      return 0;
    }
    value=value*10+digit;
  }
  if(!value) {
    return 0;
  }
  *out=(double)value/12700.0;
  return 1;
}

static exr_status read_presentation(pptx_document *d,const exr_document *xml,
                                    const pptx_relationship *rels,size_t rel_count,
                                    const exr_control *control,exr_error *e) {
  size_t parent=root(xml),size_node,list,i,n=0,index=0;
  if(!named(&xml->nodes[parent],P,PS,"presentation"))
    return exr_fail(e,EXR_FORMAT,"Invalid PPTX presentation namespace");
  d->width=720;
  d->height=540;
  size_node=child(xml,parent,"sldSz");
  if(size_node!=SIZE_MAX) {
    double width,height;
    const exr_node *node=&xml->nodes[size_node];
    if(dimension(exr_node_attribute(node,"cx"),&width) &&
       dimension(exr_node_attribute(node,"cy"),&height)) {
      d->width=width;
      d->height=height;
    }
  }
  list=child(xml,parent,"sldIdLst");
  if(list==SIZE_MAX) {
    return EXR_OK;
  }
  for(i=xml->nodes[list].first_child;i!=SIZE_MAX;i=xml->nodes[i].next_sibling)
    if(named(&xml->nodes[i],P,PS,"sldId")) n++;
  if(n>MAX_SLIDES) {
    return exr_fail(e,EXR_LIMIT,"PPTX slides exceed 10000");
  }
  if(!n) {
    return EXR_OK;
  }
  d->slides=calloc(n,sizeof(*d->slides));
  if(!d->slides) {
    return exr_fail(e,EXR_MEMORY,"PPTX slide directory allocation failed");
  }
  for(i=xml->nodes[list].first_child;i!=SIZE_MAX;i=xml->nodes[i].next_sibling) {
    const pptx_relationship *r;
    char path[2048];
    int member;
    mz_zip_archive_file_stat st;
    exr_status status;
    if(!named(&xml->nodes[i],P,PS,"sldId")) continue;
    status=exr_control_poll(control,EXR_STAGE_READ,index,n,e);
    if(status!=EXR_OK) {
      return status;
    }
    r=find_relationship(rels,rel_count,relationship_id(&xml->nodes[i]));
    /* Missing, external, wrong-type and unsafe references never become pages. */
    if(!r || r->external || (strcmp(r->type,SLIDE) && strcmp(r->type,SLIDE_STRICT)) ||
       !exr_resolve_path(r->target[0]=='/' ? "" : PRESENTATION,
                         r->target[0]=='/' ? r->target+1 : r->target,path)) {
      d->skipped++;
      index++;
      continue;
    }
    member=mz_zip_reader_locate_file(&d->zip,path,NULL,MZ_ZIP_FLAG_CASE_SENSITIVE);
    if(member<0) {
      d->skipped++;
      index++;
      continue;
    }
    if(!mz_zip_reader_file_stat(&d->zip,(mz_uint)member,&st))
      return exr_fail(e,EXR_FORMAT,"Cannot inspect PPTX slide part: %s",path);
    if(st.m_is_directory) {
      d->skipped++;
      index++;
      continue;
    }
    d->slides[d->count].part_path=exr_copy(path,strlen(path));
    if(!d->slides[d->count].part_path)
      return exr_fail(e,EXR_MEMORY,"PPTX slide path allocation failed");
    d->slides[d->count].index=index++;
    d->count++;
  }
  return EXR_OK;
}

static size_t drawing_child(const exr_document *xml,size_t parent,const char *tag) {
  size_t i;
  if(parent==SIZE_MAX) return SIZE_MAX;
  for(i=xml->nodes[parent].first_child;i!=SIZE_MAX;i=xml->nodes[i].next_sibling)
    if(named(&xml->nodes[i],A,AS,tag)) return i;
  return SIZE_MAX;
}

/* Signed integer syntax, including zero, for offsets, extents and rotations. */
static int integer(const char *text,int64_t *out) {
  uint64_t value=0,maximum=127000000000ULL;
  int negative;
  if(!text || !*text) return 0;
  negative=*text=='-';
  if(negative) text++;
  if(!*text) return 0;
  for(;*text;text++) {
    unsigned digit=(unsigned char)*text-'0';
    if(digit>9 || value>(maximum-digit)/10) return 0;
    value=value*10+digit;
  }
  *out=negative ? -(int64_t)value : (int64_t)value;
  return 1;
}

static int pair(const exr_document *xml,size_t xfrm,const char *tag,int extent,double out[2]) {
  size_t node=drawing_child(xml,xfrm,tag);
  int64_t x,y;
  if(node==SIZE_MAX || !integer(exr_node_attribute(&xml->nodes[node],extent ? "cx" : "x"),&x) ||
     !integer(exr_node_attribute(&xml->nodes[node],extent ? "cy" : "y"),&y) ||
     (extent && (x<0 || y<0))) return 0;
  out[0]=(double)x/12700.0;
  out[1]=(double)y/12700.0;
  return 1;
}

static void multiply(const double a[6],const double b[6],double out[6]) {
  double result[6]={a[0]*b[0]+a[2]*b[1],a[1]*b[0]+a[3]*b[1],
    a[0]*b[2]+a[2]*b[3],a[1]*b[2]+a[3]*b[3],
    a[0]*b[4]+a[2]*b[5]+a[4],a[1]*b[4]+a[3]*b[5]+a[5]};
  memcpy(out,result,sizeof(result));
}

static int flipped(const exr_node *node,const char *attribute) {
  const char *value=exr_node_attribute(node,attribute);
  return value && (!strcmp(value,"1") || !strcmp(value,"true"));
}

static int transform(pptx_document *d,const exr_document *xml,size_t xfrm,int group,
                     double matrix[6],double size[2]) {
  double off[2],ch_off[2]={0,0},ch_ext[2],sx=1,sy=1,center[2],orientation[6],base[6];
  const exr_node *node;
  const char *rot;
  int64_t angle=0;
  int turn=0;
  static const double cosine[4]={1,0,-1,0},sine[4]={0,1,0,-1};
  if(!pair(xml,xfrm,"off",0,off) || !pair(xml,xfrm,"ext",1,size) ||
     (group && (!pair(xml,xfrm,"chOff",0,ch_off) || !pair(xml,xfrm,"chExt",1,ch_ext)))) {
    d->missing++;
    return 0;
  }
  node=&xml->nodes[xfrm];
  rot=exr_node_attribute(node,"rot");
  if(rot) {
    if(!integer(rot,&angle) || angle%5400000) d->rotation++;
    else turn=(int)((angle/5400000%4+4)%4);
  }
  if(group) {
    if(!ch_ext[0] || !ch_ext[1]) d->zero_extent++;
    if(ch_ext[0]) sx=size[0]/ch_ext[0];
    if(ch_ext[1]) sy=size[1]/ch_ext[1];
  }
  base[0]=sx; base[1]=0; base[2]=0; base[3]=sy;
  base[4]=off[0]-ch_off[0]*sx; base[5]=off[1]-ch_off[1]*sy;
  center[0]=off[0]+size[0]/2; center[1]=off[1]+size[1]/2;
  /* Flip in the unrotated box, then rotate clockwise in the y-down page. */
  orientation[0]=cosine[turn]*(flipped(node,"flipH") ? -1 : 1);
  orientation[1]=sine[turn]*(flipped(node,"flipH") ? -1 : 1);
  orientation[2]=-sine[turn]*(flipped(node,"flipV") ? -1 : 1);
  orientation[3]=cosine[turn]*(flipped(node,"flipV") ? -1 : 1);
  orientation[4]=center[0]-orientation[0]*center[0]-orientation[2]*center[1];
  orientation[5]=center[1]-orientation[1]*center[0]-orientation[3]*center[1];
  multiply(orientation,base,matrix);
  return 1;
}

static int theme_slot(const char *name) {
  static const char *const names[]={"dk1","lt1","dk2","lt2","accent1","accent2",
    "accent3","accent4","accent5","accent6","hlink","folHlink","tx1","bg1","tx2","bg2"};
  size_t i;
  for(i=0;name && i<sizeof(names)/sizeof(*names);i++)
    if(!strcmp(name,names[i])) return i<12 ? (int)i : (int)i-12;
  return -1;
}

static int hex_rgb(const char *value,uint32_t *out) {
  size_t i;
  uint32_t rgb=0;
  if(!value || strlen(value)!=6) return 0;
  for(i=0;i<6;i++) {
    unsigned c=(unsigned char)value[i],digit;
    if(c>='0' && c<='9') digit=c-'0';
    else if(c>='a' && c<='f') digit=c-'a'+10;
    else if(c>='A' && c<='F') digit=c-'A'+10;
    else return 0;
    rgb=(rgb<<4)|digit;
  }
  *out=rgb;
  return 1;
}

static exr_status read_theme(pptx_document *d,const exr_control *control,exr_error *e) {
  static const uint32_t defaults[]={0x000000,0xffffff,0x1f497d,0xeeece1,
    0x4f81bd,0xc0504d,0x9bbb59,0x8064a2,0x4bacc6,0xf79646,0x0000ff,0x800080};
  exr_document *xml=NULL;
  size_t parent,i;
  exr_status status;
  memcpy(d->theme,defaults,sizeof(defaults));
  d->placeholder=0x000000ff;
  status=xml_read(d,"ppt/theme/theme1.xml","theme",1,control,&xml,e);
  if(status!=EXR_OK) return status;
  if(!xml) { d->theme_warning++;return EXR_OK; }
  parent=root(xml);
  if(!named(&xml->nodes[parent],A,AS,"theme")) parent=SIZE_MAX;
  parent=drawing_child(xml,parent,"themeElements");
  parent=drawing_child(xml,parent,"clrScheme");
  if(parent==SIZE_MAX) d->theme_warning++;
  else for(i=xml->nodes[parent].first_child;i!=SIZE_MAX;i=xml->nodes[i].next_sibling) {
    size_t node;
    int slot=-1;
    const char *name=xml->nodes[i].name,*value;
    uint32_t rgb;
    if(name && !strncmp(name,A,strlen(A))) slot=theme_slot(name+strlen(A));
    else if(name && !strncmp(name,AS,strlen(AS))) slot=theme_slot(name+strlen(AS));
    if(slot<0) continue;
    node=drawing_child(xml,i,"srgbClr");
    if(node!=SIZE_MAX) value=exr_node_attribute(&xml->nodes[node],"val");
    else {
      node=drawing_child(xml,i,"sysClr");
      value=node==SIZE_MAX ? NULL : exr_node_attribute(&xml->nodes[node],"lastClr");
    }
    if(hex_rgb(value,&rgb)) d->theme[slot]=rgb;
    else d->color++;
  }
  d->theme_xml=xml;
  return EXR_OK;
}

static double clamp_unit(double value) { return fmax(0,fmin(1,value)); }

static void rgb_hsl(uint32_t rgb,double hsl[3]) {
  double r=(double)(rgb>>16)/255,g=(double)((rgb>>8)&255)/255,b=(double)(rgb&255)/255;
  double hi=fmax(r,fmax(g,b)),lo=fmin(r,fmin(g,b)),delta=hi-lo;
  hsl[0]=hsl[1]=0;hsl[2]=(hi+lo)/2;
  if(!delta) return;
  hsl[1]=delta/(1-fabs(2*hsl[2]-1));
  if(hi==r) hsl[0]=(g-b)/delta+(g<b ? 6 : 0);
  else if(hi==g) hsl[0]=(b-r)/delta+2;
  else hsl[0]=(r-g)/delta+4;
  hsl[0]/=6;
}

static uint32_t hsl_rgb(const double hsl[3]) {
  double chroma=(1-fabs(2*hsl[2]-1))*hsl[1],h=hsl[0]*6;
  double x=chroma*(1-fabs(fmod(h,2)-1)),m=hsl[2]-chroma/2;
  double r=0,g=0,b=0;
  if(h<1) { r=chroma;g=x; }
  else if(h<2) { r=x;g=chroma; }
  else if(h<3) { g=chroma;b=x; }
  else if(h<4) { g=x;b=chroma; }
  else if(h<5) { r=x;b=chroma; }
  else { r=chroma;b=x; }
  return ((uint32_t)floor(clamp_unit(r+m)*255+0.5)<<16)|
    ((uint32_t)floor(clamp_unit(g+m)*255+0.5)<<8)|(uint32_t)floor(clamp_unit(b+m)*255+0.5);
}

static uint32_t color(pptx_document *d,const exr_document *xml,size_t fill) {
  size_t node=drawing_child(xml,fill,"srgbClr"),i;
  const char *value;
  uint32_t rgb=0,alpha=255;
  double hsl[3];
  int valid=0;
  if(node!=SIZE_MAX) valid=hex_rgb(exr_node_attribute(&xml->nodes[node],"val"),&rgb);
  else {
    int slot;
    node=drawing_child(xml,fill,"schemeClr");
    value=node==SIZE_MAX ? NULL : exr_node_attribute(&xml->nodes[node],"val");
    slot=theme_slot(value);
    if(slot>=0) { rgb=d->theme[slot];valid=1; }
    else if(value && !strcmp(value,"phClr")) {
      rgb=d->placeholder>>8; alpha=d->placeholder&255; valid=1;
    }
    else if(node==SIZE_MAX) {
      node=drawing_child(xml,fill,"sysClr");
      if(node!=SIZE_MAX) valid=hex_rgb(exr_node_attribute(&xml->nodes[node],"lastClr"),&rgb);
    }
  }
  if(!valid) { d->color++;return 0x000000ff; }
  rgb_hsl(rgb,hsl);
  /* DrawingML applies transforms in XML order, clamping each lightness step. */
  for(i=xml->nodes[node].first_child;i!=SIZE_MAX;i=xml->nodes[i].next_sibling) {
    const exr_node *op=&xml->nodes[i];
    int64_t amount;
    int mod=named(op,A,AS,"lumMod"),off=named(op,A,AS,"lumOff");
    int tint=named(op,A,AS,"tint"),shade=named(op,A,AS,"shade");
    if(named(op,A,AS,"alpha")) {
      if(!integer(exr_node_attribute(op,"val"),&amount) || amount<0 || amount>100000) {
        alpha=255;d->alpha++;
      } else alpha=(uint32_t)((amount*255+50000)/100000);
    } else if(mod || off || tint || shade) {
      double fraction;
      if(!integer(exr_node_attribute(op,"val"),&amount) ||
         (!off && amount<0) || ((tint || shade) && amount>100000)) { d->color++;continue; }
      fraction=(double)amount/100000;
      if(mod || shade) hsl[2]*=fraction;
      else if(off) hsl[2]+=fraction;
      else hsl[2]=1-(1-hsl[2])*fraction;
      hsl[2]=clamp_unit(hsl[2]);
    }
  }
  return (hsl_rgb(hsl)<<8)|alpha;
}

/* Cache by resolved package path, including failed decodes. No relationship can
   cause filesystem or network access. Encoded and decoded bytes share a budget. */
static exr_status image_read(pptx_document *d,const char *path,size_t *out,
                             const exr_control *control,exr_error *e) {
  size_t i,size,bytes;
  int index;
  void *data;
  uint32_t width,height;
  mz_zip_archive_file_stat st;
  pptx_image *image;
  exr_error local={0};
  exr_status status;
  for(i=0;i<d->image_count;i++) if(!strcmp(path,d->images[i].path)) {
    *out=i;
    return EXR_OK;
  }
  if(!exr_grow((void **)&d->images,&d->image_capacity,d->image_count+1,sizeof(*image)))
    return exr_fail(e,EXR_MEMORY,"PPTX image directory allocation failed");
  image=&d->images[d->image_count];
  memset(image,0,sizeof(*image));
  image->path=exr_copy(path,strlen(path));
  if(!image->path) return exr_fail(e,EXR_MEMORY,"PPTX image path allocation failed");
  *out=d->image_count++;
  index=mz_zip_reader_locate_file(&d->zip,path,NULL,MZ_ZIP_FLAG_CASE_SENSITIVE);
  if(index<0 || !mz_zip_reader_file_stat(&d->zip,(mz_uint)index,&st) || st.m_is_directory)
    return EXR_OK;
  if(st.m_uncomp_size>EXR_MAX_INPUT-d->expanded-d->paint_bytes)
    return exr_fail(e,EXR_LIMIT,"PPTX media exceeds 128 MiB");
  size=(size_t)st.m_uncomp_size;
  data=malloc(size ? size : 1);
  if(!data) return exr_fail(e,EXR_MEMORY,"PPTX media allocation failed");
  d->expanded+=size;
  if(!mz_zip_reader_extract_to_mem(&d->zip,(mz_uint)index,data,size,0)) { free(data); return EXR_OK; }
  status=exr_image_dimensions(data,size,&width,&height,&local);
  bytes=status==EXR_OK ? (size_t)width*height*4 : 0;
  if(bytes>EXR_MAX_INPUT-d->expanded-d->paint_bytes) {
    free(data);
    return exr_fail(e,EXR_LIMIT,"PPTX decoded images exceed 128 MiB");
  }
  if(status==EXR_OK) status=exr_image_decode_control(data,size,control,&image->bitmap,&local);
  free(data);
  if(status==EXR_CANCELLED || status==EXR_MEMORY) return exr_fail(e,status,"%s",local.message);
  if(status!=EXR_OK) exr_bitmap_free(&image->bitmap);
  else d->paint_bytes+=bytes;
  return exr_control_cancel(control,e);
}

static exr_status image_fill(pptx_document *d,pptx_shape *shape,const char *part,
                             const exr_document *xml,size_t fill,const pptx_relationship *rels,
                             size_t rel_count,const exr_control *control,exr_error *e) {
  size_t blip=drawing_child(xml,fill,"blip"),tile=drawing_child(xml,fill,"tile"),i;
  const char *id=blip==SIZE_MAX ? NULL : exr_node_attribute(&xml->nodes[blip],R "embed");
  const pptx_relationship *r;
  char path[2048];
  exr_status status;
  if(!id && blip!=SIZE_MAX) id=exr_node_attribute(&xml->nodes[blip],RS "embed");
  r=find_relationship(rels,rel_count,id);
  shape->style.fill=0xccccccff;
  shape->style.flags|=EXR_DRAW_FILL;
  if(!r || r->external || (strcmp(r->type,IMAGE_REL) && strcmp(r->type,IMAGE_STRICT)) ||
     !exr_resolve_path(r->target[0]=='/' ? "" : part,
                       r->target[0]=='/' ? r->target+1 : r->target,path)) {
    d->image_warning++;
    return EXR_OK;
  }
  status=image_read(d,path,&shape->image,control,e);
  if(status!=EXR_OK) return status;
  if(!d->images[shape->image].bitmap.pixels) { d->image_warning++; return EXR_OK; }
  shape->texture=1;
  if(tile!=SIZE_MAX) {
    static const char *attributes[]={"tx","ty","sx","sy","flip","algn"};
    int simple=1;
    for(i=0;i<sizeof(attributes)/sizeof(*attributes);i++) {
      const char *value=exr_node_attribute(&xml->nodes[tile],attributes[i]);
      int64_t number;
      if(!value) continue;
      if(i<4) {
        if(!integer(value,&number) || number!=(i<2 ? 0 : 100000)) simple=0;
      } else if(strcmp(value,i==4 ? "none" : "tl")) simple=0;
    }
    if(simple) shape->tile=1;
    else d->tile_warning++;
  }
  return EXR_OK;
}

static exr_status gradient_fill(pptx_document *d,pptx_shape *shape,const exr_document *xml,
                                size_t fill,exr_error *e) {
  size_t list=drawing_child(xml,fill,"gsLst"),i,n=0,at,lin=drawing_child(xml,fill,"lin");
  int64_t value;
  const char *text;
  pptx_stop *stops;
  if(list!=SIZE_MAX)
    for(i=xml->nodes[list].first_child;i!=SIZE_MAX;i=xml->nodes[i].next_sibling)
      if(named(&xml->nodes[i],A,AS,"gs")) n++;
  if(n>MAX_STOPS) return exr_fail(e,EXR_LIMIT,"PPTX gradient exceeds 256 stops");
  shape->style.flags|=EXR_DRAW_FILL;
  shape->style.fill=0x000000ff;
  if(n<2) {
    if(n) for(i=xml->nodes[list].first_child;i!=SIZE_MAX;i=xml->nodes[i].next_sibling)
      if(named(&xml->nodes[i],A,AS,"gs")) { shape->style.fill=color(d,xml,i); break; }
    d->gradient_warning++;
    return EXR_OK;
  }
  if(n*sizeof(*stops)>EXR_MAX_INPUT-d->shape_bytes)
    return exr_fail(e,EXR_LIMIT,"PPTX gradient storage exceeds 128 MiB");
  stops=calloc(n,sizeof(*stops));
  if(!stops) return exr_fail(e,EXR_MEMORY,"PPTX gradient allocation failed");
  shape->stops=stops; shape->stop_count=n;
  d->shape_bytes+=n*sizeof(*stops);
  n=0;
  for(i=xml->nodes[list].first_child;i!=SIZE_MAX;i=xml->nodes[i].next_sibling) {
    pptx_stop stop;
    if(!named(&xml->nodes[i],A,AS,"gs")) continue;
    if(!integer(exr_node_attribute(&xml->nodes[i],"pos"),&value) || value<0 || value>100000) {
      value=0; d->gradient_warning++;
    }
    stop.position=(double)value/100000.0;
    stop.rgba=color(d,xml,i);
    /* Stable sort preserves the document order of coincident stops. */
    for(at=n;at && stops[at-1].position>stop.position;at--) stops[at]=stops[at-1];
    stops[at]=stop;
    n++;
  }
  text=lin==SIZE_MAX ? NULL : exr_node_attribute(&xml->nodes[lin],"ang");
  if(!text || !integer(text,&value)) { value=0; d->gradient_warning++; }
  shape->angle=(double)(value%21600000)/60000.0*3.14159265358979323846/180;
  shape->texture=2;
  return EXR_OK;
}

static exr_status preset(pptx_document *d,const char *name,pptx_geometry *geometry,exr_error *e) {
  size_t at=0;
  *geometry=RECT;
  if(!name || !strcmp(name,"rect")) return EXR_OK;
  if(!strcmp(name,"ellipse")) *geometry=ELLIPSE;
  else if(!strcmp(name,"roundRect")) *geometry=ROUND_RECT;
  else if(!strcmp(name,"triangle")) *geometry=TRIANGLE;
  else if(!strcmp(name,"line")) *geometry=LINE;
  else {
    while(at<d->fallbacks.size) {
      if(!strcmp(name,d->fallbacks.data+at)) return EXR_OK;
      at+=strlen(d->fallbacks.data+at)+1;
    }
    if(!exr_append(&d->fallbacks,name,strlen(name)+1))
      return exr_fail(e,EXR_MEMORY,"PPTX preset warning allocation failed");
  }
  return EXR_OK;
}

static int text_warning(exr_buffer *list,const char *name) {
  size_t at=0;
  while(at<list->size) {
    if(!strcmp(list->data+at,name)) return 1;
    at+=strlen(list->data+at)+1;
  }
  return list->size<65536 && exr_append(list,name,strlen(name)+1);
}

static void text_run_style(pptx_document *d,pptx_text_style *s,const exr_document *xml,size_t at) {
  const exr_node *n;
  const char *v;
  int64_t value;
  size_t c;
  if(at==SIZE_MAX) return;
  n=&xml->nodes[at];
  if(integer(exr_node_attribute(n,"sz"),&value) && value>0 && value<=409600) s->size=value/100.0;
  if(integer(exr_node_attribute(n,"spc"),&value)) s->tracking=value/100.0;
  if((v=exr_node_attribute(n,"b"))) {
    s->flags&=~EXR_GLYPH_BOLD;
    if(!strcmp(v,"1") || !strcmp(v,"true")) s->flags|=EXR_GLYPH_BOLD;
  }
  if((v=exr_node_attribute(n,"i"))) {
    s->flags&=~EXR_GLYPH_ITALIC;
    if(!strcmp(v,"1") || !strcmp(v,"true")) s->flags|=EXR_GLYPH_ITALIC;
  }
  if((v=exr_node_attribute(n,"u"))) {
    s->flags&=~EXR_GLYPH_UNDERLINE;
    if(strcmp(v,"none")) s->flags|=EXR_GLYPH_UNDERLINE;
  }
  c=drawing_child(xml,at,"solidFill");
  if(c!=SIZE_MAX) s->color=color(d,xml,c);
  c=drawing_child(xml,at,"latin");
  if(c!=SIZE_MAX && (v=exr_node_attribute(&xml->nodes[c],"typeface")) && *v) s->latin=v;
  c=drawing_child(xml,at,"ea");
  if(c!=SIZE_MAX && (v=exr_node_attribute(&xml->nodes[c],"typeface")) && *v) s->ea=v;
  c=drawing_child(xml,at,"cs");
  if(c!=SIZE_MAX && (v=exr_node_attribute(&xml->nodes[c],"typeface")) && *v) s->cs=v;
}

static void text_spacing(const exr_document *xml,size_t parent,const char *tag,double *value,int *pct) {
  size_t at=drawing_child(xml,parent,tag),c=drawing_child(xml,at,"spcPct");
  int64_t n;
  if(c!=SIZE_MAX && integer(exr_node_attribute(&xml->nodes[c],"val"),&n) && n>=0) {
    *value=n/100000.0; *pct=1;
  } else {
    c=drawing_child(xml,at,"spcPts");
    if(c!=SIZE_MAX && integer(exr_node_attribute(&xml->nodes[c],"val"),&n) && n>=0) {
      *value=n/100.0; *pct=0;
    }
  }
}

static void text_paragraph_style(pptx_document *d,pptx_text_style *s,const exr_document *xml,size_t at) {
  const char *v;
  int64_t n;
  size_t c;
  if(at==SIZE_MAX) return;
  v=exr_node_attribute(&xml->nodes[at],"algn");
  if(v) s->align=!strcmp(v,"ctr") ? 1 : !strcmp(v,"r") ? 2 : !strcmp(v,"just") ? 3 : 0;
  if(integer(exr_node_attribute(&xml->nodes[at],"marL"),&n)) s->margin=n/12700.0;
  if(integer(exr_node_attribute(&xml->nodes[at],"indent"),&n)) s->indent=n/12700.0;
  text_spacing(xml,at,"lnSpc",&s->line,&s->line_pct);
  text_spacing(xml,at,"spcBef",&s->before,&s->before_pct);
  text_spacing(xml,at,"spcAft",&s->after,&s->after_pct);
  if(drawing_child(xml,at,"buNone")!=SIZE_MAX) { s->bullet=NULL; s->number=0; }
  if((c=drawing_child(xml,at,"buChar"))!=SIZE_MAX) {
    s->bullet=exr_node_attribute(&xml->nodes[c],"char"); s->number=0;
  }
  if((c=drawing_child(xml,at,"buAutoNum"))!=SIZE_MAX) {
    s->bullet=NULL; s->number=1; s->start=0;
    if(integer(exr_node_attribute(&xml->nodes[c],"startAt"),&n) && n>0 && n<=32767) s->start=(int)n;
  }
  text_run_style(d,s,xml,drawing_child(xml,at,"defRPr"));
}

static void text_list_style(pptx_document *d,pptx_text_style *s,const exr_document *xml,size_t list,int level) {
  char tag[16];
  if(!xml || list==SIZE_MAX) return;
  text_paragraph_style(d,s,xml,drawing_child(xml,list,"defPPr"));
  snprintf(tag,sizeof(tag),"lvl%dpPr",level+1);
  text_paragraph_style(d,s,xml,drawing_child(xml,list,tag));
}

static void text_defaults(pptx_document *d,const exr_document *xml) {
  size_t list=child(xml,root(xml),"defaultTextStyle");
  int i;
  for(i=0;i<9;i++) {
    pptx_text_style s={0};
    s.size=18; s.color=0x000000ff; s.latin="Segoe UI"; s.ea=s.cs="sans-serif";
    s.line=1; s.line_pct=1;
    text_list_style(d,&s,xml,list,i);
    d->default_text[i]=s;
  }
}

/* Relationship-driven master lookup; no hard-coded slideMaster1 assumption. */
static exr_status text_related(pptx_document *d,const char *part,const char *kind,
                               const exr_control *control,char target[2048],exr_error *e) {
  const char *slash=strrchr(part,'/');
  char path[2048];
  exr_document *xml=NULL;
  pptx_relationship *rels=NULL;
  size_t count=0,i;
  int length=snprintf(path,sizeof(path),"%.*s_rels/%s.rels",slash ? (int)(slash-part+1) : 0,
                      part,slash ? slash+1 : part);
  exr_status status;
  target[0]=0;
  if(length<0 || length>=(int)sizeof(path)) return exr_fail(e,EXR_LIMIT,"PPTX text relationship path too long");
  status=xml_read(d,path,"Relationships",1,control,&xml,e);
  if(status==EXR_OK) status=read_relationships(xml,&rels,&count,e);
  if(status==EXR_OK) for(i=0;i<count;i++) {
    const char *type=rels[i].type,*last=strrchr(type,'/');
    if(!rels[i].external && last && !strcmp(last+1,kind) &&
       (!strncmp(type,R,sizeof(R)-2) || !strncmp(type,RS,sizeof(RS)-2))) {
      if(!exr_resolve_path(rels[i].target[0]=='/' ? "" : part,
                          rels[i].target[0]=='/' ? rels[i].target+1 : rels[i].target,target)) target[0]=0;
      break;
    }
  }
  free(rels); exr_document_free(xml);
  return status;
}

static exr_status text_master(pptx_document *d,pptx_slide *slide,const exr_control *control,
                              exr_document **master,char layout[2048],char path[2048],exr_error *e) {
  static const char *const tags[]={"titleStyle","bodyStyle","otherStyle"};
  size_t list=SIZE_MAX;
  int i,j;
  exr_status status=text_related(d,slide->part_path,"slideLayout",control,layout,e);
  *master=NULL;
  path[0]=0;
  if(status==EXR_OK && *layout) {
    status=text_related(d,layout,"slideMaster",control,path,e);
    if(status==EXR_OK && *path) status=xml_read(d,path,"sldMaster",1,control,master,e);
  }
  if(status!=EXR_OK) return status;
  if(*master && named(&(*master)->nodes[root(*master)],P,PS,"sldMaster"))
    list=child(*master,root(*master),"txStyles");
  for(i=0;i<3;i++) for(j=0;j<9;j++) {
    slide->text_styles[i][j]=d->default_text[j];
    if(list!=SIZE_MAX) text_list_style(d,&slide->text_styles[i][j],*master,child(*master,list,tags[i]),j);
  }
  return EXR_OK;
}

static int text_script(uint32_t cp) {
  if((cp>=0x2e80 && cp<=0x9fff) || (cp>=0xac00 && cp<=0xd7af) ||
     (cp>=0xf900 && cp<=0xfaff) || (cp>=0xff00 && cp<=0xffef) || cp>=0x20000) return 1;
  return cp>=0x590 && cp<=0x8ff ? 2 : 0;
}

static const char *text_theme_family(const pptx_document *d,const char *family) {
  const char *group,*script,*typeface;
  size_t at;
  if(!d->theme_xml || !family || family[0]!='+') return family;
  if(!strncmp(family,"+mj-",4)) group="majorFont";
  else if(!strncmp(family,"+mn-",4)) group="minorFont";
  else return family;
  if(!strcmp(family+4,"lt")) script="latin";
  else if(!strcmp(family+4,"ea")) script="ea";
  else if(!strcmp(family+4,"cs")) script="cs";
  else return family;
  at=drawing_child(d->theme_xml,root(d->theme_xml),"themeElements");
  at=drawing_child(d->theme_xml,at,"fontScheme");
  at=drawing_child(d->theme_xml,at,group);
  at=drawing_child(d->theme_xml,at,script);
  typeface=at==SIZE_MAX ? NULL : exr_node_attribute(&d->theme_xml->nodes[at],"typeface");
  return typeface && *typeface ? typeface : family;
}

/* Pick each requested script/style before constructing one bounded engine font
   set. This preserves EA and bold faces that a coverage-compacted chain omits. */
static exr_status text_font(pptx_document *d,exr_document *model,exr_style *styles,
                            exr_font **out,exr_error *e) {
  pptx_text_font key={0};
  size_t i,j,at;
  exr_status status;
  exr_font_input inputs[32]={0};
  unsigned char *bytes[32]={0};
  if(!d->font_manager) {
    exr_font_manager_options options={0};
    options.struct_size=sizeof(options); options.flags=EXR_FONT_MANAGER_PLATFORM_DIRECTORIES;
    status=exr_font_manager_create(&options,&d->font_manager,e);
    if(status!=EXR_OK) return status;
  }
  for(i=3;i<model->node_count;i++) {
    const exr_node *node=&model->nodes[i];
    const char *family=styles[i].family;
    exr_font_chain_link *chain=NULL;
    size_t chain_count=0;
    if(node->kind!=EXR_NODE_TEXT) continue;
    family=text_theme_family(d,family);
    styles[i].family=family;
    if(strcmp(family,"sans-serif") && !exr_font_manager_has_family(d->font_manager,family)) {
      if(!text_warning(&d->font_fallbacks,family)) return exr_fail(e,EXR_LIMIT,"PPTX font warnings exceed budget");
      family=exr_font_manager_has_family(d->font_manager,"Segoe UI") ? "Segoe UI" : "sans-serif";
      styles[i].family=family;
    }
    status=exr_font_manager_chain(d->font_manager,family,styles[i].flags&3,&chain,&chain_count,e);
    if(status!=EXR_OK) return status;
    at=node->start;
    while(at<node->end) {
      uint32_t cp;
      exr_font_pick_result pick={0};
      if(!exr_next(model->text,model->size,&at,&cp)) { free(chain); return exr_fail(e,EXR_ENCODING,"PPTX text is not UTF-8"); }
      pick.struct_size=sizeof(pick);
      pick.face=SIZE_MAX;
      for(j=0;j<chain_count;j++) if(exr_font_manager_face_covers(d->font_manager,chain[j].face,cp)) {
        pick.face=chain[j].face; pick.step=chain[j].step; break;
      }
      if(cp>32 && (pick.face==SIZE_MAX || pick.step>=EXR_FONT_STEP_FALLBACK)) {
        char warning[192];
        snprintf(warning,sizeof(warning),"%s U+%04X%s",family,(unsigned)cp,pick.face==SIZE_MAX ? " missing" : " fallback");
        if(!text_warning(&d->glyph_fallbacks,warning)) { free(chain); return exr_fail(e,EXR_LIMIT,"PPTX glyph warnings exceed budget"); }
      }
      if(pick.face==SIZE_MAX) {
        status=exr_font_manager_pick(d->font_manager,"sans-serif",0,'?',&pick,e);
        if(status!=EXR_OK) { free(chain); return status; }
        if(pick.face==SIZE_MAX) { free(chain); return exr_fail(e,EXR_FONT,"PPTX has no default font"); }
      }
      for(j=0;j<key.count && key.faces[j]!=pick.face;j++) { }
      if(j==key.count) {
        if(key.count==32) { free(chain); return exr_fail(e,EXR_LIMIT,"PPTX paragraph exceeds 32 font faces"); }
        key.faces[key.count++]=pick.face;
      }
    }
    free(chain);
  }
  if(!key.count) { *out=NULL; return EXR_OK; }
  for(i=0;i<d->text_font_count;i++) if(key.count==d->text_fonts[i].count &&
      !memcmp(key.faces,d->text_fonts[i].faces,key.count*sizeof(size_t))) {
    *out=d->text_fonts[i].font; return EXR_OK;
  }
  status=EXR_OK;
  for(i=0;i<key.count && status==EXR_OK;i++) {
    exr_font_face_info info={0}; size_t size=0;
    info.struct_size=sizeof(info);
    status=exr_font_manager_face(d->font_manager,key.faces[i],&info,e);
    if(status==EXR_OK) status=exr_read(info.path,&bytes[i],&size,e);
    if(status==EXR_OK && size>EXR_FONT_MANAGER_MAX_BYTES-d->font_bytes)
      status=exr_fail(e,EXR_LIMIT,"PPTX fonts exceed 256 MiB");
    if(status==EXR_OK) { d->font_bytes+=size; inputs[i]=(exr_font_input){bytes[i],size,info.face_index}; }
  }
  if(status==EXR_OK) status=exr_font_create_managed(inputs,key.count,&key.font,e);
  for(i=0;i<key.count;i++) free(bytes[i]);
  if(status!=EXR_OK) return status;
  if(!exr_grow((void **)&d->text_fonts,&d->text_font_capacity,d->text_font_count+1,sizeof(key))) {
    exr_font_free(key.font); return exr_fail(e,EXR_MEMORY,"PPTX font directory allocation failed");
  }
  d->text_fonts[d->text_font_count++]=key; *out=key.font;
  return EXR_OK;
}

typedef struct { pptx_text_style style; const char *family; } pptx_text_span;

/* DrawingML whitespace is significant. Avoid the HTML model projection's
   whitespace folding while retaining the engine's ordinary text-node ranges. */
static exr_status text_model_finish(exr_document *model,exr_error *e) {
  exr_buffer text={0};
  size_t i;
  for(i=3;i<model->node_count;i++) {
    exr_node *node=&model->nodes[i];
    const char *s=node->kind==EXR_NODE_BREAK ? "\n" : node->text;
    node->start=text.size;
    if(s && !exr_append(&text,s,strlen(s))) {
      free(text.data); return exr_fail(e,EXR_LIMIT,"PPTX text projection exceeds 64 MiB");
    }
    node->end=text.size;
  }
  model->text=text.data; model->size=text.size; model->text_capacity=text.capacity;
  for(i=0;i<3;i++) { model->nodes[i].start=0; model->nodes[i].end=text.size; }
  return EXR_OK;
}

static exr_status text_add(exr_document *model,pptx_text_span **spans,size_t *capacity,
                           const char *text,size_t length,const pptx_text_style *style,exr_error *e) {
  size_t at=0,first=0,node;
  int script=-1;
  while(at<length) {
    size_t start=at;
    uint32_t cp;
    int next;
    if(!exr_next(text,length,&at,&cp)) return exr_fail(e,EXR_ENCODING,"PPTX text is not UTF-8");
    next=text_script(cp);
    if(script<0) script=next;
    if(next!=script || at==length) {
      size_t end=next!=script ? start : at;
      node=exr_model_node(model,2,0,EXR_NODE_TEXT,NULL,text+first,end-first);
      if(node==SIZE_MAX || !exr_grow((void **)spans,capacity,model->node_count,sizeof(**spans)))
        return exr_fail(e,EXR_LIMIT,"PPTX text model exceeds node budget");
      (*spans)[node]=(pptx_text_span){*style,script==1 ? style->ea : script==2 ? style->cs : style->latin};
      first=end; script=next;
      if(at==length && first<length) {
        node=exr_model_node(model,2,0,EXR_NODE_TEXT,NULL,text+first,length-first);
        if(node==SIZE_MAX || !exr_grow((void **)spans,capacity,model->node_count,sizeof(**spans)))
          return exr_fail(e,EXR_LIMIT,"PPTX text model exceeds node budget");
        (*spans)[node]=(pptx_text_span){*style,script==1 ? style->ea : script==2 ? style->cs : style->latin};
      }
    }
  }
  return EXR_OK;
}

static exr_status text_paragraph(pptx_document *d,pptx_shape *shape,const exr_document *xml,size_t para,
                                 const pptx_text_style *base,double scale,double reduction,double width,
                                 double left,double *y,int wrap,const exr_control *control,exr_error *e) {
  exr_document *model=calloc(1,sizeof(*model));
  exr_style *styles=NULL;
  pptx_text_span *spans=NULL;
  size_t capacity=0,i,j,k,bullet_end=3;
  pptx_text_style bullet_style=*base;
  char number[24];
  const char *bullet=NULL;
  size_t bullet_length=0;
  exr_shaped_glyph *bullet_glyphs=NULL;
  size_t bullet_count=0,bullet_face=0;
  double text_offset=0;
  exr_buffer plain={0};
  exr_font *font=NULL;
  exr_layout *layout=NULL;
  exr_layout_config config=exr_layout_config_defaults();
  exr_status status=EXR_OK;
  flow parent={0}; exr_layout viewport={0},assets={0}; exr_float_state floats={0};
  float height;
  if(!model) return exr_fail(e,EXR_MEMORY,"PPTX paragraph allocation failed");
  model->chapters=calloc(1,sizeof(*model->chapters));
  if(!model->chapters) { status=exr_fail(e,EXR_MEMORY,"PPTX chapter allocation failed"); goto done; }
  model->chapter_count=1; model->chapters[0].root=1; model->chapters[0].resource=SIZE_MAX;
  model->chapters[0].in_spine=model->chapters[0].linear=1;
  if(exr_model_node(model,SIZE_MAX,0,EXR_NODE_DOCUMENT,NULL,NULL,0)==SIZE_MAX ||
     exr_model_node(model,0,0,EXR_NODE_CHAPTER,NULL,NULL,0)==SIZE_MAX ||
     exr_model_node(model,1,0,EXR_NODE_PARAGRAPH,"p",NULL,0)==SIZE_MAX) {
    status=exr_fail(e,EXR_LIMIT,"PPTX paragraph model allocation failed"); goto done;
  }
  for(i=xml->nodes[para].first_child;i!=SIZE_MAX;i=xml->nodes[i].next_sibling)
    if(named(&xml->nodes[i],A,AS,"r")) {
      text_run_style(d,&bullet_style,xml,drawing_child(xml,i,"rPr")); break;
    }
  if(base->bullet) {
    size_t n=0; uint32_t cp;
    if(exr_next(base->bullet,strlen(base->bullet),&n,&cp)) { bullet=base->bullet; bullet_length=n; }
  } else if(base->number) {
    bullet_length=(size_t)snprintf(number,sizeof(number),"%d.",base->start); bullet=number;
  }
  if(bullet) status=text_add(model,&spans,&capacity,bullet,bullet_length,&bullet_style,e);
  bullet_end=model->node_count;
  for(i=xml->nodes[para].first_child;status==EXR_OK && i!=SIZE_MAX;i=xml->nodes[i].next_sibling) {
    pptx_text_style style=*base;
    if(named(&xml->nodes[i],A,AS,"br")) {
      size_t node=exr_model_node(model,2,0,EXR_NODE_BREAK,"br",NULL,0);
      if(node==SIZE_MAX) status=exr_fail(e,EXR_LIMIT,"PPTX break model allocation failed");
      continue;
    }
    if(!named(&xml->nodes[i],A,AS,"r") && !named(&xml->nodes[i],A,AS,"fld")) continue;
    text_run_style(d,&style,xml,drawing_child(xml,i,"rPr"));
    j=drawing_child(xml,i,"t");
    plain.size=0;
    if(j!=SIZE_MAX) for(k=xml->nodes[j].first_child;k!=SIZE_MAX;k=xml->nodes[k].next_sibling) {
      const char *t=xml->nodes[k].text;
      if(t && !exr_append(&plain,t,strlen(t))) { status=exr_fail(e,EXR_LIMIT,"PPTX run exceeds text budget"); break; }
    }
    if(status==EXR_OK) status=text_add(model,&spans,&capacity,plain.data,plain.size,&style,e);
  }
  if(status!=EXR_OK) goto done;
  status=text_model_finish(model,e);
  if(status!=EXR_OK) goto done;
  styles=calloc(model->node_count,sizeof(*styles));
  if(!styles) { status=exr_fail(e,EXR_MEMORY,"PPTX styles allocation failed"); goto done; }
  for(i=0;i<model->node_count;i++) {
    exr_style *s=&styles[i];
    const pptx_text_style *t=i>=3 && model->nodes[i].kind==EXR_NODE_TEXT ? &spans[i].style : base;
    s->font_size=(float)(t->size*scale); s->leading=1; s->leading_relative=1;
    s->tracking=(float)(t->tracking*scale);
    s->family=i>=3 && model->nodes[i].kind==EXR_NODE_TEXT ? spans[i].family : base->latin;
    s->color=t->color; s->flags=t->flags; s->display=i<3 ? EXR_CSS_BLOCK : EXR_CSS_INLINE;
    s->width.value=s->height.value=s->max_width.value=s->max_height.value=-1;
    s->indent_declared=1; s->hyphens=EXR_HYPHENS_NONE;
    if(i>=3 && i<bullet_end) s->display=EXR_CSS_NONE;
  }
  styles[2].align=wrap ? base->align : 0; styles[2].indent=bullet ? 0 : (float)base->indent;
  status=text_font(d,model,styles,&font,e);
  if(status!=EXR_OK) goto done;
  if(!font) {
    size_t lines=1;
    double advance=base->line_pct ? base->size*scale*base->line : base->line;
    for(i=3;i<model->node_count;i++) if(model->nodes[i].kind==EXR_NODE_BREAK) lines++;
    *y+=(base->before_pct ? base->before*base->size*scale : base->before)+
        advance*(1-reduction)*lines+(base->after_pct ? base->after*base->size*scale : base->after);
    goto done;
  }
  if(bullet) {
    size_t order[32],count=exr_font_order(font,styles[3].family,bullet_style.flags,0,order),at=0;
    exr_shape_options options=exr_shape_defaults();
    uint32_t cp;
    double advance=0;
    exr_next(bullet,bullet_length,&at,&cp);
    for(i=0;i<count;i++) if(exr_font_has_glyph(font,order[i],cp)) { bullet_face=order[i]; break; }
    options.font_size=(float)(bullet_style.size*scale); options.style_flags=bullet_style.flags&3; options.control=*control;
    status=exr_shape(font,bullet_face,bullet,bullet_length,&options,&bullet_glyphs,&bullet_count,e);
    if(status!=EXR_OK) goto done;
    for(i=0;i<bullet_count;i++) advance+=bullet_glyphs[i].advance_x;
    /* Missing/default indentation still needs room for the marker and a gap. */
    text_offset=fmax(0,base->indent+advance+bullet_style.size*scale/4);
  }
  config.page=(exr_layout_options){16384,16384,0,18,1,0}; config.control=*control;
  viewport.options=config.page; assets.font=font;
  parent.layout=&viewport; parent.assets=&assets; parent.doc=model; parent.font=font;
  parent.config=&config; parent.styles=styles; parent.paragraph=&styles[0]; parent.error=e;
  parent.floats=&floats; parent.width=(float)fmax(1,width-base->margin-text_offset);
  status=exr_flow_unit(&parent,2,wrap ? parent.width : 10000000,&layout,&height);
  if(status!=EXR_OK || !layout) goto done;
  *y+=base->before_pct ? base->before*base->size*scale : base->before;
  for(i=0;i<layout->line_count;i++) {
    exr_line *line=&layout->lines[i];
    double advance=base->line_pct ? line->height*base->line : base->line;
    double shift=0;
    /* DrawingML justifies between visible words. The generic flow also
       allocates a share to the trailing separator; return that share to the
       internal spaces, keeping explicit breaks and final lines unexpanded. */
    if(wrap && base->align==3 && i+1<layout->line_count) {
      size_t end=line->glyph_count,spaces=0,next=layout->lines[i+1].start;
      int forced=0;
      double extra=0,add=0;
      for(j=line->start;j<next && j<model->size;j++) if(model->text[j]=='\n') forced=1;
      while(end) {
        const exr_glyph *g=&layout->glyphs[line->glyph_start+end-1];
        if(!(g->flags&EXR_GLYPH_HIDDEN) && g->codepoint!=' ' && g->codepoint!='\t') break;
        end--;
      }
      for(j=0;j<end;j++) if(layout->glyphs[line->glyph_start+j].codepoint==' ') spaces++;
      if(!forced && end && spaces) {
        const exr_glyph *last=&layout->glyphs[line->glyph_start+end-1];
        extra=fmax(0,parent.width-last->x-last->advance)/(double)spaces;
        for(j=0;j<end;j++) {
          exr_glyph *g=&layout->glyphs[line->glyph_start+j];
          g->x+=(float)add;
          if(g->codepoint==' ') add+=extra;
        }
      }
    }
    if(!wrap && base->align==1) shift=(parent.width-line->width)/2;
    else if(!wrap && base->align==2) shift=parent.width-line->width;
    advance*=1-reduction;
    for(j=0;j<line->glyph_count;j++) {
      exr_glyph *g=&layout->glyphs[line->glyph_start+j];
      g->x+=(float)(left+base->margin+text_offset+shift);
      g->baseline+=(float)(*y-line->y);
    }
    *y+=advance;
  }
  if(bullet && layout->line_count && layout->glyph_count) {
    double x=left+base->margin+base->indent;
    float baseline=layout->glyphs[layout->lines[0].glyph_start].baseline;
    if(!exr_grow((void **)&layout->glyphs,&layout->glyph_cap,layout->glyph_count+bullet_count,sizeof(exr_glyph)))
      status=exr_fail(e,EXR_MEMORY,"PPTX bullet glyph allocation failed");
    if(status==EXR_OK) for(i=0;i<bullet_count;i++) {
      exr_glyph g={0};
      g.glyph=bullet_glyphs[i].glyph; g.font_index=bullet_face; g.size=(float)(bullet_style.size*scale); g.color=bullet_style.color;
      g.x=(float)x; g.baseline=baseline; g.advance=bullet_glyphs[i].advance_x;
      g.offset_x=bullet_glyphs[i].offset_x; g.offset_y=bullet_glyphs[i].offset_y;
      g.flags=bullet_glyphs[i].flags|(bullet_style.flags&EXR_GLYPH_UNDERLINE);
      layout->glyphs[layout->glyph_count++]=g; x+=g.advance;
    }
    if(status!=EXR_OK) goto done;
  }
  *y+=base->after_pct ? base->after*base->size*scale : base->after;
  if(layout->glyph_count>(EXR_MAX_INPUT-d->text_bytes)/sizeof(exr_glyph)) {
    status=exr_fail(e,EXR_LIMIT,"PPTX text storage exceeds 128 MiB"); goto done;
  }
  d->text_bytes+=layout->glyph_count*sizeof(exr_glyph);
  if(!exr_grow((void **)&shape->paragraphs,&shape->paragraph_capacity,shape->paragraph_count+1,sizeof(*shape->paragraphs))) {
    status=exr_fail(e,EXR_MEMORY,"PPTX paragraph directory allocation failed"); goto done;
  }
  shape->paragraphs[shape->paragraph_count++]=(pptx_paragraph){layout}; layout=NULL;
done:
  exr_layout_free(layout); free(styles); free(spans); free(plain.data); free(bullet_glyphs); exr_document_free(model);
  return status;
}

static exr_status text_body(pptx_document *d,pptx_slide *slide,pptx_shape *shape,const exr_document *xml,
                            size_t sp,const exr_control *control,exr_error *e) {
  int cell=named(&xml->nodes[sp],A,AS,"tc");
  size_t body=cell ? drawing_child(xml,sp,"txBody") : child(xml,sp,"txBody"),props,list,p,ph,nv,i,j;
  double inset[4]={3.6,7.2,3.6,7.2},scale=1,reduction=0,y=0,offset,remaining;
  static const char *const attrs[]={"tIns","rIns","bIns","lIns"};
  const char *anchor=NULL,*v;
  int wrap=1,kind=2,numbers[9]={0};
  int64_t n;
  if(body==SIZE_MAX) return EXR_OK;
  props=drawing_child(xml,body,"bodyPr"); list=drawing_child(xml,body,"lstStyle");
  if(props!=SIZE_MAX) {
    const exr_node *node=&xml->nodes[props];
    anchor=exr_node_attribute(node,"anchor"); v=exr_node_attribute(node,"wrap"); wrap=!v || strcmp(v,"none");
    for(i=0;i<4;i++) if(integer(exr_node_attribute(node,attrs[i]),&n) && n>=0) inset[i]=n/12700.0;
    i=drawing_child(xml,props,"normAutofit");
    if(i!=SIZE_MAX) {
      v=exr_node_attribute(&xml->nodes[i],"fontScale");
      if(v && (!integer(v,&n) || n<=0 || n>100000)) d->text_scale_warning++;
      else if(v) scale=n/100000.0;
      if(integer(exr_node_attribute(&xml->nodes[i],"lnSpcReduction"),&n) && n>=0 && n<=100000) reduction=n/100000.0;
    }
  }
  if(cell) {
    static const char *const margins[]={"marT","marR","marB","marL"};
    size_t tcpr=drawing_child(xml,sp,"tcPr");
    anchor=NULL;
    for(i=0;i<4;i++) inset[i]=7.2;
    if(tcpr!=SIZE_MAX) {
      const exr_node *node=&xml->nodes[tcpr];
      anchor=exr_node_attribute(node,"anchor");
      for(i=0;i<4;i++) if(integer(exr_node_attribute(node,margins[i]),&n) && n>=0) inset[i]=n/12700.0;
    }
  }
  nv=child(xml,sp,"nvSpPr"); nv=nv==SIZE_MAX ? SIZE_MAX : child(xml,nv,"nvPr");
  ph=nv==SIZE_MAX ? SIZE_MAX : child(xml,nv,"ph");
  v=ph==SIZE_MAX ? NULL : exr_node_attribute(&xml->nodes[ph],"type");
  if(v && (!strcmp(v,"title") || !strcmp(v,"ctrTitle"))) kind=0;
  else if(ph!=SIZE_MAX && (!v || !strcmp(v,"body") || !strcmp(v,"obj") || !strcmp(v,"subTitle"))) kind=1;
  for(p=xml->nodes[body].first_child;p!=SIZE_MAX;p=xml->nodes[p].next_sibling) {
    pptx_text_style style;
    size_t ppr;
    int level=0;
    exr_status status;
    if(!named(&xml->nodes[p],A,AS,"p")) continue;
    ppr=drawing_child(xml,p,"pPr");
    if(ppr!=SIZE_MAX && integer(exr_node_attribute(&xml->nodes[ppr],"lvl"),&n)) {
      if(n>8) { n=8; d->text_level_warning++; }
      if(n>=0) level=(int)n;
    }
    style=slide->text_styles[kind][level];
    text_list_style(d,&style,xml,list,level);
    text_paragraph_style(d,&style,xml,ppr);
    if(style.number) {
      numbers[level]=style.start ? style.start : numbers[level]+1;
      style.start=numbers[level];
    } else numbers[level]=0;
    for(i=(size_t)level+1;i<9;i++) numbers[i]=0;
    status=text_paragraph(d,shape,xml,p,&style,scale,reduction,shape->width-inset[1]-inset[3],inset[3],&y,wrap,control,e);
    if(status!=EXR_OK) return status;
  }
  if(cell && y+inset[0]+inset[2]>shape->height+0.01) d->table_height_warning++;
  offset=inset[0];
  remaining=shape->height-inset[0]-inset[2]-y;
  if(cell) remaining=fmax(0,remaining);
  if(anchor && !strcmp(anchor,"ctr")) offset+=remaining/2;
  else if(anchor && !strcmp(anchor,"b")) offset+=remaining;
  for(i=0;i<shape->paragraph_count;i++) for(j=0;j<shape->paragraphs[i].layout->glyph_count;j++)
    shape->paragraphs[i].layout->glyphs[j].baseline+=(float)offset;
  return EXR_OK;
}

/* Takes ownership of the shape's allocations, including on failure. */
static exr_status shape_append(pptx_document *d,pptx_slide *slide,pptx_shape *shape,exr_error *e) {
  exr_status status=EXR_OK;
  if(d->shape_bytes>EXR_MAX_INPUT-sizeof(*shape))
    status=exr_fail(e,EXR_LIMIT,"PPTX shape storage exceeds 128 MiB");
  else if(!exr_grow((void **)&slide->shapes,&slide->capacity,slide->count+1,sizeof(*shape)))
    status=exr_fail(e,EXR_MEMORY,"PPTX shapes allocation failed");
  if(status!=EXR_OK) { free(shape->stops); text_free(shape); return status; }
  slide->shapes[slide->count++]=*shape;
  d->shape_bytes+=sizeof(*shape);
  return EXR_OK;
}

static size_t table_span(pptx_document *d,const exr_node *cell,const char *attr,size_t remaining) {
  const char *value=exr_node_attribute(cell,attr);
  size_t n=0;
  if(!value) return 1;
  for(;*value;value++) {
    unsigned digit=(unsigned char)*value-'0';
    if(digit>9) { d->table_span_warning++; return 1; }
    /* Saturate before multiplying, even for arbitrarily long attributes. */
    if(n<=remaining) n=n*10+digit;
  }
  if(!n) { d->table_span_warning++; return 1; }
  if(n>remaining) { d->table_span_warning++; return remaining; }
  return n;
}

static exr_status table_read(pptx_document *d,pptx_slide *slide,const exr_document *xml,size_t frame,
                             const double parent[6],const exr_control *control,exr_error *e) {
  size_t table=drawing_child(xml,frame,"graphic"),grid,props,i,r,c,rows=0,cols=0,start=slide->count;
  size_t row_nodes[MAX_TABLE_DIMENSION];
  double xs[MAX_TABLE_DIMENSION+1]={0},ys[MAX_TABLE_DIMENSION+1]={0},local[6],matrix[6],size[2];
  table=drawing_child(xml,table,"graphicData"); table=drawing_child(xml,table,"tbl");
  if(table==SIZE_MAX) { d->unsupported++; return EXR_OK; }
  grid=drawing_child(xml,table,"tblGrid"); props=drawing_child(xml,table,"tblPr");
  if(props!=SIZE_MAX && (drawing_child(xml,props,"tableStyleId")!=SIZE_MAX ||
     flipped(&xml->nodes[props],"firstRow") || flipped(&xml->nodes[props],"bandRow"))) d->table_style_warning++;
  if(grid!=SIZE_MAX) for(i=xml->nodes[grid].first_child;i!=SIZE_MAX;i=xml->nodes[i].next_sibling) {
    double width=0;
    if(!named(&xml->nodes[i],A,AS,"gridCol")) continue;
    if(cols==MAX_TABLE_DIMENSION) return exr_fail(e,EXR_LIMIT,"PPTX table columns exceed 200");
    if(!dimension(exr_node_attribute(&xml->nodes[i],"w"),&width)) d->table_grid_warning++;
    xs[cols+1]=xs[cols]+width; cols++;
  }
  for(i=xml->nodes[table].first_child;i!=SIZE_MAX;i=xml->nodes[i].next_sibling) {
    int64_t height=0;
    if(!named(&xml->nodes[i],A,AS,"tr")) continue;
    if(rows==MAX_TABLE_DIMENSION) return exr_fail(e,EXR_LIMIT,"PPTX table rows exceed 200");
    row_nodes[rows]=i;
    if(!integer(exr_node_attribute(&xml->nodes[i],"h"),&height) || height<0) {
      height=0; d->table_grid_warning++;
    }
    ys[rows+1]=ys[rows]+height/12700.0; rows++;
  }
  if(xs[cols]>10000000 || ys[rows]>10000000)
    return exr_fail(e,EXR_LIMIT,"PPTX table extent exceeds 1e7 points");
  if(!transform(d,xml,child(xml,frame,"xfrm"),0,local,size)) return EXR_OK;
  multiply(parent,local,matrix);
  if(fabs(xs[cols]-size[0])>0.5/12700.0) d->table_grid_warning++;
  for(r=0;r<rows;r++) {
    size_t count=0;
    for(i=xml->nodes[row_nodes[r]].first_child;i!=SIZE_MAX;i=xml->nodes[i].next_sibling)
      if(named(&xml->nodes[i],A,AS,"tc") && ++count>MAX_TABLE_DIMENSION)
        return exr_fail(e,EXR_LIMIT,"PPTX table row cells exceed 200");
    if(!count) { d->table_row_warning++; continue; }
    if(count!=cols) d->table_grid_warning++;
    c=0;
    for(i=xml->nodes[row_nodes[r]].first_child;i!=SIZE_MAX && c<cols;i=xml->nodes[i].next_sibling) {
      static const char *const sides[]={"lnL","lnR","lnT","lnB"};
      const exr_node *node=&xml->nodes[i];
      pptx_shape cell={0};
      double offset[6]={1,0,0,1,0,0};
      size_t cs,rs,tcpr,fill,b;
      exr_status status;
      if(!named(node,A,AS,"tc")) continue;
      status=exr_control_cancel(control,e);
      if(status!=EXR_OK) return status;
      cs=table_span(d,node,"gridSpan",cols-c); rs=table_span(d,node,"rowSpan",rows-r);
      offset[4]=xs[c]; offset[5]=ys[r];
      cell.width=xs[c+cs]-xs[c]; cell.height=ys[r+rs]-ys[r]; c++;
      if(flipped(node,"hMerge") || flipped(node,"vMerge")) continue;
      multiply(matrix,offset,cell.matrix);
      cell.table_cells=SIZE_MAX;
      cell.style=exr_draw_style_defaults(); cell.style.flags=0;
      tcpr=drawing_child(xml,i,"tcPr");
      fill=drawing_child(xml,tcpr,"solidFill");
      if(fill!=SIZE_MAX && drawing_child(xml,tcpr,"noFill")==SIZE_MAX) {
        cell.style.fill=color(d,xml,fill); cell.style.flags=EXR_DRAW_FILL;
      }
      for(b=0;b<4;b++) {
        size_t line=drawing_child(xml,tcpr,sides[b]);
        int64_t width;
        fill=drawing_child(xml,line,"solidFill");
        if(fill!=SIZE_MAX && drawing_child(xml,line,"noFill")==SIZE_MAX) {
          pptx_border *border=&cell.borders[b];
          border->present=1; border->rgba=color(d,xml,fill); border->width=cell.style.line.width;
          if(integer(exr_node_attribute(&xml->nodes[line],"w"),&width) && width>=0) border->width=width/12700.0;
        } else if(tcpr==SIZE_MAX && drawing_child(xml,i,"txBody")==SIZE_MAX)
          cell.borders[b]=(pptx_border){1,0x000000ff,1};
      }
      status=text_body(d,slide,&cell,xml,i,control,e);
      if(status!=EXR_OK) { text_free(&cell); return status; }
      status=shape_append(d,slide,&cell,e);
      if(status!=EXR_OK) return status;
    }
  }
  if(slide->count>start) slide->shapes[start].table_cells=slide->count-start;
  return EXR_OK;
}

static exr_status shape_tree(pptx_document *d,pptx_slide *slide,const exr_document *xml,
                             size_t parent,const double matrix[6],unsigned depth,
                             const pptx_relationship *rels,size_t rel_count,
                             const exr_control *control,exr_error *e) {
  size_t i;
  for(i=xml->nodes[parent].first_child;i!=SIZE_MAX;i=xml->nodes[i].next_sibling) {
    const exr_node *node=&xml->nodes[i];
    pptx_shape shape={0};
    double local[6],size[2];
    size_t properties,xfrm,geometry,fill,line;
    int group=named(node,P,PS,"grpSp"),pic=named(node,P,PS,"pic");
    exr_status status=exr_control_cancel(control,e);
    if(status!=EXR_OK) return status;
    if(named(node,P,PS,"graphicFrame")) {
      status=table_read(d,slide,xml,i,matrix,control,e);
      if(status!=EXR_OK) return status;
      continue;
    }
    if(pic && child(xml,i,"spPr")==SIZE_MAX) {
      d->unsupported++;
      continue;
    }
    if(!group && !pic && !named(node,P,PS,"sp") && !named(node,P,PS,"cxnSp")) continue;
    if(group && depth>=MAX_GROUP_DEPTH) {
      d->depth++;
      continue;
    }
    properties=child(xml,i,group ? "grpSpPr" : "spPr");
    xfrm=drawing_child(xml,properties,"xfrm");
    if(!transform(d,xml,xfrm,group,local,size)) continue;
    multiply(matrix,local,shape.matrix);
    if(group) {
      status=shape_tree(d,slide,xml,i,shape.matrix,depth+1,rels,rel_count,control,e);
      if(status!=EXR_OK) return status;
      continue;
    }
    shape.width=size[0]; shape.height=size[1];
    geometry=drawing_child(xml,properties,"prstGeom");
    status=preset(d,geometry==SIZE_MAX ? NULL : exr_node_attribute(&xml->nodes[geometry],"prst"),
                  &shape.geometry,e);
    if(status!=EXR_OK) return status;
    shape.style=exr_draw_style_defaults();
    shape.style.flags=0;
    if(shape.geometry!=LINE && drawing_child(xml,properties,"noFill")==SIZE_MAX) {
      fill=pic ? child(xml,i,"blipFill") : drawing_child(xml,properties,"blipFill");
      if(fill!=SIZE_MAX) status=image_fill(d,&shape,slide->part_path,xml,fill,rels,rel_count,control,e);
      else if((fill=drawing_child(xml,properties,"gradFill"))!=SIZE_MAX)
        status=gradient_fill(d,&shape,xml,fill,e);
      else if((fill=drawing_child(xml,properties,"solidFill"))!=SIZE_MAX) {
        shape.style.fill=color(d,xml,fill);
        shape.style.flags|=EXR_DRAW_FILL;
      }
      if(status!=EXR_OK) { free(shape.stops); return status; }
    }
    line=drawing_child(xml,properties,"ln");
    fill=drawing_child(xml,line,"solidFill");
    if(fill!=SIZE_MAX && drawing_child(xml,line,"noFill")==SIZE_MAX) {
      int64_t width;
      const char *value=exr_node_attribute(&xml->nodes[line],"w");
      shape.style.stroke=color(d,xml,fill);
      shape.style.flags|=EXR_DRAW_STROKE;
      if(value && integer(value,&width) && width>=0) shape.style.line.width=(double)width/12700.0;
    }
    status=text_body(d,slide,&shape,xml,i,control,e);
    if(status!=EXR_OK) { free(shape.stops); text_free(&shape); return status; }
    if(!shape.style.flags && !shape.paragraph_count) continue;
    status=shape_append(d,slide,&shape,e);
    if(status!=EXR_OK) return status;
  }
  return EXR_OK;
}

static exr_status background_fill(pptx_document *d,pptx_shape *shape,const exr_document *xml,
                                  size_t fill,const char *part,const exr_control *control,exr_error *e) {
  exr_document *relationships=NULL;
  pptx_relationship *rels=NULL;
  size_t count=0;
  exr_status status;
  if(fill==SIZE_MAX || named(&xml->nodes[fill],A,AS,"noFill")) return EXR_OK;
  if(named(&xml->nodes[fill],A,AS,"solidFill")) {
    shape->style.fill=color(d,xml,fill); shape->style.flags=EXR_DRAW_FILL;
    return EXR_OK;
  }
  if(named(&xml->nodes[fill],A,AS,"gradFill")) return gradient_fill(d,shape,xml,fill,e);
  if(named(&xml->nodes[fill],A,AS,"blipFill")) {
    const char *slash=strrchr(part,'/');
    char path[2048];
    int length=snprintf(path,sizeof(path),"%.*s_rels/%s.rels",slash ? (int)(slash-part+1) : 0,
                        part,slash ? slash+1 : part);
    if(length<0 || length>=(int)sizeof(path)) return exr_fail(e,EXR_LIMIT,"PPTX background relationship path too long");
    status=xml_read(d,path,"Relationships",1,control,&relationships,e);
    if(status==EXR_OK) status=read_relationships(relationships,&rels,&count,e);
    if(status==EXR_OK) status=image_fill(d,shape,part,xml,fill,rels,count,control,e);
    free(rels); exr_document_free(relationships);
    return status;
  }
  d->color++;
  return EXR_OK;
}

/* The nearest explicit background wins; image relationships belong to the
   selected slide/layout/master (or to the theme for a style reference). */
static exr_status read_background(pptx_document *d,pptx_slide *slide,const exr_document *xml,
                                  const exr_document *master,const char *layout_path,const char *master_path,
                                  const exr_control *control,exr_error *e) {
  exr_document *layout=NULL;
  const char *part=slide->part_path;
  size_t common=child(xml,root(xml),"cSld"),bg=common==SIZE_MAX ? SIZE_MAX : child(xml,common,"bg");
  size_t props,fill;
  pptx_shape *shape=&slide->background;
  exr_status status=EXR_OK;
  if(bg==SIZE_MAX && *layout_path) {
    status=xml_read(d,layout_path,"sldLayout",1,control,&layout,e);
    if(status!=EXR_OK) return status;
    if(layout) {
      common=child(layout,root(layout),"cSld");
      bg=common==SIZE_MAX ? SIZE_MAX : child(layout,common,"bg");
      if(bg!=SIZE_MAX) { xml=layout; part=layout_path; }
    }
  }
  if(bg==SIZE_MAX && master) {
    common=child(master,root(master),"cSld");
    bg=common==SIZE_MAX ? SIZE_MAX : child(master,common,"bg");
    if(bg!=SIZE_MAX) { xml=master; part=master_path; }
  }
  if(bg==SIZE_MAX) { exr_document_free(layout); return EXR_OK; }
  shape->width=d->width; shape->height=d->height;
  shape->matrix[0]=shape->matrix[3]=1;
  shape->style=exr_draw_style_defaults(); shape->style.flags=0;
  props=child(xml,bg,"bgPr");
  if(props!=SIZE_MAX) {
    fill=xml->nodes[props].first_child;
    status=background_fill(d,shape,xml,fill,part,control,e);
  } else {
    int64_t index;
    size_t ref=child(xml,bg,"bgRef"),list;
    uint32_t previous=d->placeholder;
    if(ref==SIZE_MAX || !integer(exr_node_attribute(&xml->nodes[ref],"idx"),&index) || index<0) d->color++;
    else if(index && index!=1000) {
      d->placeholder=color(d,xml,ref);
      list=d->theme_xml ? drawing_child(d->theme_xml,root(d->theme_xml),"themeElements") : SIZE_MAX;
      list=drawing_child(d->theme_xml,list,"fmtScheme");
      list=drawing_child(d->theme_xml,list,index>=1001 ? "bgFillStyleLst" : "fillStyleLst");
      index-=index>=1001 ? 1001 : 1;
      fill=list==SIZE_MAX ? SIZE_MAX : d->theme_xml->nodes[list].first_child;
      while(fill!=SIZE_MAX && index--) fill=d->theme_xml->nodes[fill].next_sibling;
      if(fill==SIZE_MAX) d->color++;
      else status=background_fill(d,shape,d->theme_xml,fill,"ppt/theme/theme1.xml",control,e);
    }
    d->placeholder=previous;
  }
  exr_document_free(layout);
  return status;
}

static exr_status read_shapes(pptx_document *d,const exr_control *control,exr_error *e) {
  const double identity[6]={1,0,0,1,0,0};
  size_t page;
  for(page=0;page<d->count;page++) {
    exr_document *xml=NULL,*relationships=NULL,*master=NULL;
    pptx_relationship *rels=NULL;
    const char *part=d->slides[page].part_path,*slash=strrchr(part,'/');
    char rel_path[2048],layout_path[2048],master_path[2048];
    size_t parent,tree,i,count=0,visited=0,rel_count=0;
    int length=snprintf(rel_path,sizeof(rel_path),"%.*s_rels/%s.rels",
                        slash ? (int)(slash-part+1) : 0,part,slash ? slash+1 : part);
    exr_status status=exr_control_poll(control,EXR_STAGE_READ,page,d->count,e);
    if(length<0 || length>=(int)sizeof(rel_path)) return exr_fail(e,EXR_LIMIT,"PPTX relationship path too long");
    if(status==EXR_OK) status=xml_read(d,d->slides[page].part_path,"sld",0,control,&xml,e);
    if(status!=EXR_OK) return status;
    status=xml_read(d,rel_path,"Relationships",1,control,&relationships,e);
    if(status==EXR_OK) status=read_relationships(relationships,&rels,&rel_count,e);
    if(status!=EXR_OK) { free(rels); exr_document_free(relationships); exr_document_free(xml); return status; }
    parent=root(xml);
    if(!named(&xml->nodes[parent],P,PS,"sld")) {
      free(rels);
      exr_document_free(relationships);
      exr_document_free(xml);
      return exr_fail(e,EXR_FORMAT,"Invalid PPTX slide namespace");
    }
    parent=child(xml,parent,"cSld");
    tree=parent==SIZE_MAX ? SIZE_MAX : child(xml,parent,"spTree");
    /* Count even descendants below the recursion cutoff and unsupported objects. */
    i=tree;
    while(i!=SIZE_MAX) {
      const exr_node *node=&xml->nodes[i];
      if(!(visited++%256)) {
        status=exr_control_cancel(control,e);
        if(status!=EXR_OK) break;
      }
      if(named(node,P,PS,"sp") || named(node,P,PS,"grpSp") || named(node,P,PS,"cxnSp") ||
         named(node,P,PS,"pic") || named(node,P,PS,"graphicFrame")) count++;
      if(count>MAX_SHAPES) {
        status=exr_fail(e,EXR_LIMIT,"PPTX shapes exceed 10000 on slide %zu",page+1);
        break;
      }
      if(node->first_child!=SIZE_MAX) {
        i=node->first_child;
        continue;
      }
      while(i!=tree && xml->nodes[i].next_sibling==SIZE_MAX) i=xml->nodes[i].parent;
      if(i==tree) break;
      i=xml->nodes[i].next_sibling;
    }
    if(status==EXR_OK) status=text_master(d,&d->slides[page],control,&master,layout_path,master_path,e);
    if(status==EXR_OK) status=read_background(d,&d->slides[page],xml,master,layout_path,master_path,control,e);
    if(status==EXR_OK && tree!=SIZE_MAX)
      status=shape_tree(d,&d->slides[page],xml,tree,identity,0,rels,rel_count,control,e);
    free(rels);
    exr_document_free(relationships);
    exr_document_free(xml);
    exr_document_free(master);
    if(status!=EXR_OK) return status;
  }
  return EXR_OK;
}

static size_t shape_path(const pptx_shape *shape,exr_path_segment path[10]) {
  double w=shape->width,h=shape->height,k=0.5522847498307936;
  memset(path,0,10*sizeof(*path));
  path[0].verb=EXR_PATH_MOVE;
  if(shape->geometry==ELLIPSE) {
    double x=w/2,y=h/2;
    path[0].points[0]=(exr_path_point){w,y};
    path[1]=(exr_path_segment){EXR_PATH_CUBIC,{{w,y+k*y},{x+k*x,h},{x,h}}};
    path[2]=(exr_path_segment){EXR_PATH_CUBIC,{{x-k*x,h},{0,y+k*y},{0,y}}};
    path[3]=(exr_path_segment){EXR_PATH_CUBIC,{{0,y-k*y},{x-k*x,0},{x,0}}};
    path[4]=(exr_path_segment){EXR_PATH_CUBIC,{{x+k*x,0},{w,y-k*y},{w,y}}};
    path[5].verb=EXR_PATH_CLOSE;
    return 6;
  }
  if(shape->geometry==ROUND_RECT) {
    /* Default DrawingML roundRect adjustment: 1/6 of the shorter side. */
    double r=fmin(w,h)/6;
    path[0].points[0]=(exr_path_point){r,0};
    path[1]=(exr_path_segment){EXR_PATH_LINE,{{w-r,0}}};
    path[2]=(exr_path_segment){EXR_PATH_CUBIC,{{w-r+k*r,0},{w,r-k*r},{w,r}}};
    path[3]=(exr_path_segment){EXR_PATH_LINE,{{w,h-r}}};
    path[4]=(exr_path_segment){EXR_PATH_CUBIC,{{w,h-r+k*r},{w-r+k*r,h},{w-r,h}}};
    path[5]=(exr_path_segment){EXR_PATH_LINE,{{r,h}}};
    path[6]=(exr_path_segment){EXR_PATH_CUBIC,{{r-k*r,h},{0,h-r+k*r},{0,h-r}}};
    path[7]=(exr_path_segment){EXR_PATH_LINE,{{0,r}}};
    path[8]=(exr_path_segment){EXR_PATH_CUBIC,{{0,r-k*r},{r-k*r,0},{r,0}}};
    path[9].verb=EXR_PATH_CLOSE;
    return 10;
  }
  if(shape->geometry==LINE) {
    path[1]=(exr_path_segment){EXR_PATH_LINE,{{w,h}}};
    return 2;
  }
  if(shape->geometry==TRIANGLE) {
    path[0].points[0]=(exr_path_point){w/2,0};
    path[1]=(exr_path_segment){EXR_PATH_LINE,{{w,h}}};
    path[2]=(exr_path_segment){EXR_PATH_LINE,{{0,h}}};
    path[3].verb=EXR_PATH_CLOSE;
    return 4;
  }
  path[1]=(exr_path_segment){EXR_PATH_LINE,{{w,0}}};
  path[2]=(exr_path_segment){EXR_PATH_LINE,{{w,h}}};
  path[3]=(exr_path_segment){EXR_PATH_LINE,{{0,h}}};
  path[4].verb=EXR_PATH_CLOSE;
  return 5;
}

/* A one-dimensional RGBA ramp uses the existing image sampler at every angle.
   ponytail: 4096 samples bound temporary storage; native paint if finer stops
   or high-precision colour become necessary. Coordinates stay in shape space. */
static void gradient_ramp(const pptx_shape *shape,unsigned char pixels[16384],double matrix[6]) {
  double x=cos(shape->angle),y=sin(shape->angle),w=shape->width,h=shape->height;
  double lo=fmin(x*w,0)+fmin(y*h,0),side=fmin(-y*w,0)+fmin(x*h,0);
  double span=fabs(x*w)+fabs(y*h),cross=fabs(y*w)+fabs(x*h);
  size_t i,j=0,k;
  matrix[0]=x*span; matrix[1]=y*span;
  matrix[2]=-y*cross; matrix[3]=x*cross;
  matrix[4]=x*lo-y*side; matrix[5]=y*lo+x*side;
  for(i=0;i<4096;i++) {
    double t=((double)i+0.5)/4096,f=0;
    const pptx_stop *a,*b;
    while(j+1<shape->stop_count && shape->stops[j+1].position<=t) j++;
    a=&shape->stops[j]; b=a;
    if(t>a->position && j+1<shape->stop_count) {
      b=a+1;
      f=(t-a->position)/(b->position-a->position);
    }
    for(k=0;k<4;k++) {
      unsigned shift=(unsigned)(3-k)*8;
      double first=(a->rgba>>shift)&255,last=(b->rgba>>shift)&255;
      pixels[i*4+k]=(unsigned char)floor(first+(last-first)*f+0.5);
    }
  }
}

static exr_status texture_draw(const pptx_document *d,const pptx_shape *shape,
                               const double combined[6],const exr_draw_sink *sink,
                               const exr_control *control,exr_error *e) {
  exr_image_layer image={0};
  unsigned char ramp[16384];
  double local[6]={shape->width,0,0,shape->height,0,0},matrix[6],tw=0,th=0;
  size_t columns=1,rows=1,x,y;
  exr_status status=EXR_OK;
  int clipped=sink->clip && sink->state,saved=0;
  if(!sink->image || !shape->width || !shape->height) return EXR_OK;
  if(shape->texture==2) {
    gradient_ramp(shape,ramp,local);
    image.bitmap=(exr_bitmap){4096,1,16384,ramp,4};
    image.interpolate=1;
  } else {
    image.bitmap=d->images[shape->image].bitmap;
    image.interpolate=!shape->tile;
    if(shape->tile) {
      /* M3 intrinsic tile size uses 96 dpi: one image pixel is 0.75 pt. */
      tw=image.bitmap.width*0.75; th=image.bitmap.height*0.75;
      if(ceil(shape->width/tw)>65536 || ceil(shape->height/th)>65536 ||
         ceil(shape->width/tw)*ceil(shape->height/th)>65536)
        return exr_fail(e,EXR_LIMIT,"PPTX image tile count exceeds 65536");
      columns=(size_t)ceil(shape->width/tw); rows=(size_t)ceil(shape->height/th);
      local[0]=tw; local[3]=th;
    }
  }
  if(clipped) {
    exr_path_segment path[10];
    status=sink->state(sink->context,EXR_DRAW_SAVE,e);
    saved=status==EXR_OK;
    if(status==EXR_OK) status=sink->clip(sink->context,path,shape_path(shape,path),combined,EXR_FILL_NONZERO,0,e);
  }
  for(y=0;status==EXR_OK && y<rows;y++) for(x=0;status==EXR_OK && x<columns;x++) {
    status=exr_control_cancel(control,e);
    if(status!=EXR_OK) break;
    if(shape->tile) { local[4]=x*tw; local[5]=y*th; }
    multiply(combined,local,matrix);
    status=sink->image(sink->context,&image,matrix,1,e);
  }
  if(saved) {
    exr_error cleanup={0};
    exr_status restored=sink->state(sink->context,EXR_DRAW_RESTORE,status==EXR_OK ? e : &cleanup);
    if(status==EXR_OK) status=restored;
  }
  return status;
}

static void warning_append(char message[256],const char *format,...) {
  size_t size=strlen(message);
  int written;
  va_list args;
  if(size>=252) return;
  va_start(args,format);
  written=vsnprintf(message+size,256-size,format,args);
  va_end(args);
  if(written>=(int)(256-size)) memcpy(message+252,"...",4);
}

static void warnings(const pptx_document *d,exr_error *e) {
  char message[256]="PPTX warning: ";
  size_t at=0;
  if(d->table_grid_warning) warning_append(message,"table gridCol count/width mismatch or invalid dimensions=%zu; ",d->table_grid_warning);
  if(d->table_span_warning) warning_append(message,"table span clipped/invalid=%zu; ",d->table_span_warning);
  if(d->table_row_warning) warning_append(message,"table row missing tc=%zu; ",d->table_row_warning);
  if(d->table_height_warning) warning_append(message,"table overflow (no auto row height)=%zu; ",d->table_height_warning);
  if(d->table_style_warning) warning_append(message,"tableStyleId/firstRow/bandRow styling not applied=%zu; ",d->table_style_warning);
  if(d->invalid_utf8) warning_append(message,"invalid UTF-8 skipped run(s)=%zu; ",d->invalid_utf8);
  if(d->text_scale_warning) warning_append(message,"invalid fontScale (100%%)=%zu; ",d->text_scale_warning);
  if(d->text_level_warning) warning_append(message,"level>8 (clamped)=%zu; ",d->text_level_warning);
  if(d->font_fallbacks.size) {
    warning_append(message,"font fallback=");
    while(at<d->font_fallbacks.size) {
      warning_append(message,"%s%s",at ? "," : "",d->font_fallbacks.data+at);
      at+=strlen(d->font_fallbacks.data+at)+1;
    }
    warning_append(message,"; ");
  }
  at=0;
  if(d->glyph_fallbacks.size) {
    warning_append(message,"missing glyph: ");
    while(at<d->glyph_fallbacks.size) {
      warning_append(message,"%s; ",d->glyph_fallbacks.data+at);
      at+=strlen(d->glyph_fallbacks.data+at)+1;
    }
  }
  at=0;
  if(d->skipped) warning_append(message,"skipped %zu slide reference(s) with missing or invalid parts; ",d->skipped);
  if(d->missing) warning_append(message,"missing off/ext=%zu; ",d->missing);
  if(d->zero_extent) warning_append(message,"chExt=0 (1:1)=%zu; ",d->zero_extent);
  if(d->rotation) warning_append(message,"ignored rotation=%zu; ",d->rotation);
  if(d->depth) warning_append(message,"depth>16=%zu; ",d->depth);
  if(d->color) warning_append(message,"invalid color=%zu; ",d->color);
  if(d->theme_warning) warning_append(message,"missing theme1.xml/clrScheme (default theme)=%zu; ",d->theme_warning);
  if(d->alpha) warning_append(message,"invalid alpha (opaque)=%zu; ",d->alpha);
  if(d->image_warning) warning_append(message,"missing/invalid image (gray)=%zu; ",d->image_warning);
  if(d->gradient_warning) warning_append(message,"gradient fallback/invalid=%zu; ",d->gradient_warning);
  if(d->tile_warning) warning_append(message,"unsupported tile (stretch)=%zu; ",d->tile_warning);
  if(d->unsupported) warning_append(message,"skipped pic/graphicFrame=%zu; ",d->unsupported);
  if(d->fallbacks.size) {
    warning_append(message,"rect fallback=");
    while(at<d->fallbacks.size) {
      warning_append(message,"%s%s",at ? "," : "",d->fallbacks.data+at);
      at+=strlen(d->fallbacks.data+at)+1;
    }
  }
  if(strlen(message)>14) exr_fail(e,EXR_OK,"%s",message);
}

static exr_status text_draw(const pptx_shape *shape,const double matrix[6],const exr_draw_sink *sink,
                            const exr_control *control,exr_error *e) {
  size_t i,j;
  if(!sink->path) return EXR_OK;
  for(i=0;i<shape->paragraph_count;i++) {
    const exr_layout *layout=shape->paragraphs[i].layout;
    for(j=0;j<layout->glyph_count;j++) {
      const exr_glyph *g=&layout->glyphs[j];
      exr_path_segment *path=NULL;
      size_t count=0;
      double local[6],combined[6];
      exr_draw_style style=exr_draw_style_defaults();
      exr_status status=exr_control_cancel(control,e);
      if(status!=EXR_OK) return status;
      if(g->flags&EXR_GLYPH_HIDDEN) continue;
      status=exr_font_glyph_outline(layout->font,g->font_index,g->glyph,&path,&count,control,e);
      if(status==EXR_OK) status=exr_glyph_matrix(g,local,e);
      /* Flow already clears style bits supplied by a physical bold/italic face. */
      if(status==EXR_OK) {
        if(g->flags&EXR_GLYPH_ITALIC) local[2]=local[0]*0.2;
        multiply(matrix,local,combined);
      }
      style.flags=EXR_DRAW_FILL; style.fill=g->color;
      if(g->flags&EXR_GLYPH_BOLD) {
        style.flags|=EXR_DRAW_STROKE; style.stroke=g->color; style.line.width=25;
      }
      if(status==EXR_OK && count) status=sink->path(sink->context,path,count,combined,&style,e);
      free(path);
      if(status!=EXR_OK) return status;
      if(g->flags&EXR_GLYPH_UNDERLINE) {
        exr_path_segment underline[2]={{EXR_PATH_MOVE,{{g->x,g->baseline+g->size*0.1}}},
                                      {EXR_PATH_LINE,{{g->x+g->advance,g->baseline+g->size*0.1}}}};
        style.flags=EXR_DRAW_STROKE; style.stroke=g->color; style.line.width=fmax(0.5,g->size/16);
        status=sink->path(sink->context,underline,2,matrix,&style,e);
        if(status!=EXR_OK) return status;
      }
    }
  }
  return EXR_OK;
}

static exr_status table_cell_draw(const pptx_shape *shape,const double matrix[6],const exr_draw_sink *sink,
                                  const exr_control *control,exr_error *e) {
  size_t b;
  exr_status status=EXR_OK;
  int saved=0;
  if(!sink->path) return EXR_OK;
  for(b=0;b<4;b++) if(shape->borders[b].present) {
    double w=shape->width,h=shape->height;
    exr_path_segment path[2]={{EXR_PATH_MOVE,{{0,0}}},{EXR_PATH_LINE,{{0,0}}}};
    exr_draw_style style=exr_draw_style_defaults();
    if(b==0) path[1].points[0]=(exr_path_point){0,h};
    else if(b==1) { path[0].points[0]=(exr_path_point){w,0}; path[1].points[0]=(exr_path_point){w,h}; }
    else if(b==2) path[1].points[0]=(exr_path_point){w,0};
    else { path[0].points[0]=(exr_path_point){0,h}; path[1].points[0]=(exr_path_point){w,h}; }
    style.flags=EXR_DRAW_STROKE; style.stroke=shape->borders[b].rgba; style.line.width=shape->borders[b].width;
    status=sink->path(sink->context,path,2,matrix,&style,e);
    if(status!=EXR_OK) return status;
  }
  if(!shape->paragraph_count) return EXR_OK;
  if(sink->clip && sink->state) {
    exr_path_segment path[10];
    status=sink->state(sink->context,EXR_DRAW_SAVE,e); saved=status==EXR_OK;
    if(status==EXR_OK) status=sink->clip(sink->context,path,shape_path(shape,path),matrix,EXR_FILL_NONZERO,0,e);
  }
  if(status==EXR_OK) status=text_draw(shape,matrix,sink,control,e);
  if(saved) {
    exr_error cleanup={0};
    exr_status restored=sink->state(sink->context,EXR_DRAW_RESTORE,status==EXR_OK ? e : &cleanup);
    if(status==EXR_OK) status=restored;
  }
  return status;
}

/* The fixed pipeline supplies the white fallback, viewport and clipping. */
static exr_status draw(void *context,size_t page,const double matrix[6],
                       const exr_draw_sink *sink,const exr_control *control,exr_error *e) {
  pptx_document *d=context;
  const pptx_shape *background;
  exr_status status;
  size_t i;
  if(page>=d->count) {
    return exr_fail(e,EXR_ARGUMENT,"Invalid PPTX slide index");
  }
  background=&d->slides[page].background;
  status=exr_control_cancel(control,e);
  if(status!=EXR_OK) return status;
  if(background->texture) status=texture_draw(d,background,matrix,sink,control,e);
  else if(background->style.flags && sink->path) {
    exr_path_segment path[10];
    status=sink->path(sink->context,path,shape_path(background,path),matrix,&background->style,e);
  }
  if(status!=EXR_OK) return status;
  for(i=0;i<d->slides[page].count;i++) {
    exr_path_segment path[10];
    double combined[6];
    const pptx_shape *shape=&d->slides[page].shapes[i];
    exr_draw_style style=shape->style;
    exr_status status=exr_control_poll(control,EXR_STAGE_RENDER,i,d->slides[page].count,e);
    if(status!=EXR_OK) return status;
    multiply(matrix,shape->matrix,combined);
    if(shape->table_cells) {
      /* Fill the whole table first; later cell borders then win shared edges. */
      if(shape->table_cells!=SIZE_MAX && sink->path) {
        size_t j;
        for(j=i;j<i+shape->table_cells;j++) {
          const pptx_shape *cell=&d->slides[page].shapes[j];
          double cell_matrix[6];
          status=exr_control_cancel(control,e);
          if(status!=EXR_OK) return status;
          if(!cell->style.flags) continue;
          multiply(matrix,cell->matrix,cell_matrix);
          status=sink->path(sink->context,path,shape_path(cell,path),cell_matrix,&cell->style,e);
          if(status!=EXR_OK) return status;
        }
      }
      status=table_cell_draw(shape,combined,sink,control,e);
      if(status!=EXR_OK) return status;
      continue;
    }
    if(shape->texture) {
      status=texture_draw(d,shape,combined,sink,control,e);
      if(status!=EXR_OK) return status;
      style.flags&=~EXR_DRAW_FILL;
    }
    if(sink->path && style.flags) {
      status=sink->path(sink->context,path,shape_path(shape,path),combined,&style,e);
      if(status!=EXR_OK) return status;
    }
    status=text_draw(shape,combined,sink,control,e);
    if(status!=EXR_OK) return status;
  }
  return exr_control_cancel(control,e);
}

static exr_status create_fixed(pptx_document *d,const char *title,
                               const exr_fixed_open_options *options,
                               exr_fixed_document **out,exr_error *e) {
  exr_fixed_input input={0};
  exr_fixed_page *pages=NULL;
  size_t i;
  exr_status status;
  if(d->count) {
    pages=calloc(d->count,sizeof(*pages));
    if(!pages) {
      return exr_fail(e,EXR_MEMORY,"PPTX fixed pages allocation failed");
    }
  }
  for(i=0;i<d->count;i++) {
    /* Generated page IDs stay unique even for repeated references to a part.
       The provider retains the ordered part paths separately. */
    pages[i].geometry.bounds[2]=d->width;
    pages[i].geometry.bounds[3]=d->height;
    pages[i].geometry.unit_scale=1;
    pages[i].geometry.y_down=1;
    pages[i].label=d->slides[i].part_path;
  }
  input.struct_size=sizeof(input);
  input.title=title;
  input.pages=pages;
  input.page_count=d->count;
  input.draw=draw;
  input.context=d;
  input.release=release;
  status=exr_control_poll(&options->control,EXR_STAGE_READ,d->count,d->count,e);
  if(status==EXR_OK) status=exr_fixed_create(&input,out,e);
  free(pages);
  if(status==EXR_OK) warnings(d,e);
  return status;
}

exr_status exr_pptx_open_owned(unsigned char *data,size_t size,const char *title,
                              const exr_fixed_open_options *options,
                              exr_fixed_document **out,exr_error *e) {
  pptx_document *d;
  exr_document *presentation=NULL,*relationships=NULL;
  pptx_relationship *rels=NULL;
  size_t rel_count=0;
  exr_format format=EXR_CUSTOM;
  exr_status status;
  *out=NULL;
  d=calloc(1,sizeof(*d));
  if(!d) {
    free(data);
    return exr_fail(e,EXR_MEMORY,"PPTX document allocation failed");
  }
  d->data=data;
  if(size>EXR_MAX_INPUT) {
    status=exr_fail(e,EXR_LIMIT,"PPTX input exceeds 128 MiB");
    goto done;
  }
  status=exr_control_cancel(&options->control,e);
  if(status!=EXR_OK) {
    goto done;
  }
  status=exr_zip_format(data,size,&format,e);
  if(status!=EXR_OK) {
    goto done;
  }
  if(format!=EXR_PPTX) {
    status=exr_fail(e,EXR_FORMAT,"PPTX presentation content type missing in [Content_Types].xml");
    goto done;
  }
  if(!mz_zip_reader_init_mem(&d->zip,data,size,0)) {
    status=exr_fail(e,EXR_FORMAT,"Invalid or truncated PPTX ZIP container");
    goto done;
  }
  status=check_archive(d,&options->control,e);
  if(status!=EXR_OK) {
    goto done;
  }
  status=xml_read(d,PRESENTATION,"presentation",0,&options->control,&presentation,e);
  if(status!=EXR_OK) {
    goto done;
  }
  status=xml_read(d,RELATIONSHIPS,"Relationships",1,&options->control,&relationships,e);
  if(status!=EXR_OK) {
    goto done;
  }
  status=read_relationships(relationships,&rels,&rel_count,e);
  if(status!=EXR_OK) {
    goto done;
  }
  status=read_presentation(d,presentation,rels,rel_count,&options->control,e);
  if(status==EXR_OK) text_defaults(d,presentation);
  if(status==EXR_OK) status=read_theme(d,&options->control,e);
  if(status==EXR_OK) status=read_shapes(d,&options->control,e);
  if(status==EXR_OK) status=create_fixed(d,title,options,out,e);
done:
  free(rels);
  exr_document_free(relationships);
  exr_document_free(presentation);
  if(status!=EXR_OK) release(d);
  return status;
}
