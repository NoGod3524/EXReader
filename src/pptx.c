/* SPDX-License-Identifier: MIT */
#include "pdf_internal.h"
#include <miniz.h>

#define P "http://schemas.openxmlformats.org/presentationml/2006/main|"
#define PS "http://purl.oclc.org/ooxml/presentationml/main|"
#define R "http://schemas.openxmlformats.org/officeDocument/2006/relationships|"
#define RS "http://purl.oclc.org/ooxml/officeDocument/relationships|"
#define REL "http://schemas.openxmlformats.org/package/2006/relationships|"
#define SLIDE "http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide"
#define SLIDE_STRICT "http://purl.oclc.org/ooxml/officeDocument/relationships/slide"
#define PRESENTATION "ppt/presentation.xml"
#define RELATIONSHIPS "ppt/_rels/presentation.xml.rels"
#define MAX_SLIDES 10000

typedef struct {
  char *part_path;
  size_t index; /* Original zero-based position in sldIdLst, before skipping. */
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
  double width,height;
} pptx_document;

static void release(void *context) {
  pptx_document *d=context;
  size_t i;
  if(!d) return;
  mz_zip_reader_end(&d->zip);
  for(i=0;i<d->count;i++) free(d->slides[i].part_path);
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

/* Only package metadata is parsed in M1. Each allocation is charged before
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
  if(st.m_uncomp_size>EXR_MAX_INPUT-d->expanded)
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

/* The fixed pipeline supplies the background, viewport and clipping. M1
   intentionally emits no shape or text operations. */
static exr_status draw(void *context,size_t page,const double matrix[6],
                       const exr_draw_sink *sink,const exr_control *control,exr_error *e) {
  pptx_document *d=context;
  (void)matrix;
  (void)sink;
  if(page>=d->count) {
    return exr_fail(e,EXR_ARGUMENT,"Invalid PPTX slide index");
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
  if(status==EXR_OK && d->skipped)
    exr_fail(e,EXR_OK,"PPTX warning: skipped %zu slide reference(s) with missing or invalid parts",d->skipped);
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
  if(status==EXR_OK) status=create_fixed(d,title,options,out,e);
done:
  free(rels);
  exr_document_free(relationships);
  exr_document_free(presentation);
  if(status!=EXR_OK) release(d);
  return status;
}
