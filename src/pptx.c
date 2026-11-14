/* SPDX-License-Identifier: MIT */
#include "pdf_internal.h"
#include <miniz.h>

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

typedef enum { RECT,ELLIPSE,ROUND_RECT,TRIANGLE,LINE } pptx_geometry;

typedef struct {
  pptx_geometry geometry;
  double width,height,matrix[6];
  exr_draw_style style;
} pptx_shape;

typedef struct {
  char *part_path;
  size_t index; /* Original zero-based position in sldIdLst, before skipping. */
  pptx_shape *shapes;
  size_t count,capacity;
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
  exr_buffer fallbacks; /* Unique, NUL-separated preset names; owns XML copies. */
  double width,height;
} pptx_document;

static void release(void *context) {
  pptx_document *d=context;
  size_t i;
  if(!d) return;
  mz_zip_reader_end(&d->zip);
  for(i=0;i<d->count;i++) {
    free(d->slides[i].part_path);
    free(d->slides[i].shapes);
  }
  free(d->fallbacks.data);
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

static uint32_t color(pptx_document *d,const exr_document *xml,size_t fill) {
  static const struct { const char *name; uint32_t rgb; } theme[]={
    {"dk1",0x000000},{"lt1",0xffffff},{"dk2",0x1f497d},{"lt2",0xeeece1},
    {"accent1",0x4f81bd},{"accent2",0xc0504d},{"accent3",0x9bbb59},
    {"accent4",0x8064a2},{"accent5",0x4bacc6},{"accent6",0xf79646},
    {"hlink",0x0000ff},{"folHlink",0x800080},{"tx1",0x000000},
    {"bg1",0xffffff},{"tx2",0x1f497d},{"bg2",0xeeece1},{"phClr",0x000000}};
  size_t node=drawing_child(xml,fill,"srgbClr"),i;
  const char *value;
  uint32_t rgb=0;
  if(node!=SIZE_MAX) {
    value=exr_node_attribute(&xml->nodes[node],"val");
    if(value && strlen(value)==6) {
      for(i=0;i<6;i++) {
        unsigned c=(unsigned char)value[i],digit;
        if(c>='0' && c<='9') digit=c-'0';
        else if(c>='a' && c<='f') digit=c-'a'+10;
        else if(c>='A' && c<='F') digit=c-'A'+10;
        else break;
        rgb=(rgb<<4)|digit;
      }
      if(i==6) return (rgb<<8)|255;
    }
  } else {
    node=drawing_child(xml,fill,"schemeClr");
    value=node==SIZE_MAX ? NULL : exr_node_attribute(&xml->nodes[node],"val");
    for(i=0;value && i<sizeof(theme)/sizeof(*theme);i++)
      if(!strcmp(value,theme[i].name)) return (theme[i].rgb<<8)|255;
  }
  d->color++;
  return 0x000000ff;
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

static exr_status shape_tree(pptx_document *d,pptx_slide *slide,const exr_document *xml,
                             size_t parent,const double matrix[6],unsigned depth,
                             const exr_control *control,exr_error *e) {
  size_t i;
  for(i=xml->nodes[parent].first_child;i!=SIZE_MAX;i=xml->nodes[i].next_sibling) {
    const exr_node *node=&xml->nodes[i];
    pptx_shape shape={0};
    double local[6],size[2];
    size_t properties,xfrm,geometry,fill,line;
    int group=named(node,P,PS,"grpSp");
    exr_status status=exr_control_cancel(control,e);
    if(status!=EXR_OK) return status;
    if(named(node,P,PS,"pic") || named(node,P,PS,"graphicFrame")) {
      d->unsupported++;
      continue;
    }
    if(!group && !named(node,P,PS,"sp") && !named(node,P,PS,"cxnSp")) continue;
    if(group && depth>=MAX_GROUP_DEPTH) {
      d->depth++;
      continue;
    }
    properties=child(xml,i,group ? "grpSpPr" : "spPr");
    xfrm=drawing_child(xml,properties,"xfrm");
    if(!transform(d,xml,xfrm,group,local,size)) continue;
    multiply(matrix,local,shape.matrix);
    if(group) {
      status=shape_tree(d,slide,xml,i,shape.matrix,depth+1,control,e);
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
    fill=drawing_child(xml,properties,"solidFill");
    if(shape.geometry!=LINE && fill!=SIZE_MAX && drawing_child(xml,properties,"noFill")==SIZE_MAX) {
      shape.style.fill=color(d,xml,fill);
      shape.style.flags|=EXR_DRAW_FILL;
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
    if(!shape.style.flags) continue;
    if(d->shape_bytes>EXR_MAX_INPUT-sizeof(shape))
      return exr_fail(e,EXR_LIMIT,"PPTX shape storage exceeds 128 MiB");
    if(!exr_grow((void **)&slide->shapes,&slide->capacity,slide->count+1,sizeof(shape)))
      return exr_fail(e,EXR_MEMORY,"PPTX shapes allocation failed");
    slide->shapes[slide->count++]=shape;
    d->shape_bytes+=sizeof(shape);
  }
  return EXR_OK;
}

static exr_status read_shapes(pptx_document *d,const exr_control *control,exr_error *e) {
  const double identity[6]={1,0,0,1,0,0};
  size_t page;
  for(page=0;page<d->count;page++) {
    exr_document *xml=NULL;
    size_t parent,tree,i,count=0,visited=0;
    exr_status status=exr_control_poll(control,EXR_STAGE_READ,page,d->count,e);
    if(status==EXR_OK) status=xml_read(d,d->slides[page].part_path,"sld",0,control,&xml,e);
    if(status!=EXR_OK) return status;
    parent=root(xml);
    if(!named(&xml->nodes[parent],P,PS,"sld")) {
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
    if(status==EXR_OK && tree!=SIZE_MAX) status=shape_tree(d,&d->slides[page],xml,tree,identity,0,control,e);
    exr_document_free(xml);
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
  if(d->skipped) warning_append(message,"skipped %zu slide reference(s) with missing or invalid parts; ",d->skipped);
  if(d->missing) warning_append(message,"missing off/ext=%zu; ",d->missing);
  if(d->zero_extent) warning_append(message,"chExt=0 (1:1)=%zu; ",d->zero_extent);
  if(d->rotation) warning_append(message,"ignored rotation=%zu; ",d->rotation);
  if(d->depth) warning_append(message,"depth>16=%zu; ",d->depth);
  if(d->color) warning_append(message,"invalid color=%zu; ",d->color);
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

/* The fixed pipeline supplies the background, viewport and clipping. */
static exr_status draw(void *context,size_t page,const double matrix[6],
                       const exr_draw_sink *sink,const exr_control *control,exr_error *e) {
  pptx_document *d=context;
  size_t i;
  if(page>=d->count) {
    return exr_fail(e,EXR_ARGUMENT,"Invalid PPTX slide index");
  }
  for(i=0;i<d->slides[page].count;i++) {
    exr_path_segment path[10];
    double combined[6];
    const pptx_shape *shape=&d->slides[page].shapes[i];
    exr_status status=exr_control_poll(control,EXR_STAGE_RENDER,i,d->slides[page].count,e);
    if(status!=EXR_OK) return status;
    multiply(matrix,shape->matrix,combined);
    if(sink->path) {
      status=sink->path(sink->context,path,shape_path(shape,path),combined,&shape->style,e);
      if(status!=EXR_OK) return status;
    }
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
  if(status==EXR_OK) status=read_shapes(d,&options->control,e);
  if(status==EXR_OK) status=create_fixed(d,title,options,out,e);
done:
  free(rels);
  exr_document_free(relationships);
  exr_document_free(presentation);
  if(status!=EXR_OK) release(d);
  return status;
}
