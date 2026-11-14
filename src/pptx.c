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
#define MAX_STOPS 256
#define IMAGE_REL "http://schemas.openxmlformats.org/officeDocument/2006/relationships/image"
#define IMAGE_STRICT "http://purl.oclc.org/ooxml/officeDocument/relationships/image"

typedef enum { RECT,ELLIPSE,ROUND_RECT,TRIANGLE,LINE } pptx_geometry;
typedef struct { double position; uint32_t rgba; } pptx_stop;
typedef struct { char *path; exr_bitmap bitmap; } pptx_image;

typedef struct {
  pptx_geometry geometry;
  double width,height,matrix[6];
  exr_draw_style style;
  pptx_stop *stops;
  size_t stop_count,image;
  double angle;
  unsigned texture,tile; /* 1: embedded image, 2: linear gradient. */
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
  size_t theme_warning,alpha,image_warning,gradient_warning,tile_warning,paint_bytes;
  uint32_t theme[12];
  pptx_image *images;
  size_t image_count,image_capacity;
  exr_buffer fallbacks; /* Unique, NUL-separated preset names; owns XML copies. */
  double width,height;
} pptx_document;

static void release(void *context) {
  pptx_document *d=context;
  size_t i,j;
  if(!d) return;
  mz_zip_reader_end(&d->zip);
  for(i=0;i<d->count;i++) {
    free(d->slides[i].part_path);
    for(j=0;j<d->slides[i].count;j++) free(d->slides[i].shapes[j].stops);
    free(d->slides[i].shapes);
  }
  for(i=0;i<d->image_count;i++) {
    free(d->images[i].path);
    exr_bitmap_free(&d->images[i].bitmap);
  }
  free(d->images);
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
  exr_document_free(xml);
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
    else if(value && !strcmp(value,"phClr")) valid=1;
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

static exr_status image_fill(pptx_document *d,pptx_shape *shape,const pptx_slide *slide,
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
     !exr_resolve_path(r->target[0]=='/' ? "" : slide->part_path,
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
    if((pic && child(xml,i,"spPr")==SIZE_MAX) || named(node,P,PS,"graphicFrame")) {
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
      if(fill!=SIZE_MAX) status=image_fill(d,&shape,slide,xml,fill,rels,rel_count,control,e);
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
    if(!shape.style.flags) continue;
    if(d->shape_bytes>EXR_MAX_INPUT-sizeof(shape)) {
      free(shape.stops);
      return exr_fail(e,EXR_LIMIT,"PPTX shape storage exceeds 128 MiB");
    }
    if(!exr_grow((void **)&slide->shapes,&slide->capacity,slide->count+1,sizeof(shape))) {
      free(shape.stops);
      return exr_fail(e,EXR_MEMORY,"PPTX shapes allocation failed");
    }
    slide->shapes[slide->count++]=shape;
    d->shape_bytes+=sizeof(shape);
  }
  return EXR_OK;
}

static exr_status read_shapes(pptx_document *d,const exr_control *control,exr_error *e) {
  const double identity[6]={1,0,0,1,0,0};
  size_t page;
  for(page=0;page<d->count;page++) {
    exr_document *xml=NULL,*relationships=NULL;
    pptx_relationship *rels=NULL;
    const char *part=d->slides[page].part_path,*slash=strrchr(part,'/');
    char rel_path[2048];
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
    if(status==EXR_OK && tree!=SIZE_MAX)
      status=shape_tree(d,&d->slides[page],xml,tree,identity,0,rels,rel_count,control,e);
    free(rels);
    exr_document_free(relationships);
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
    exr_draw_style style=shape->style;
    exr_status status=exr_control_poll(control,EXR_STAGE_RENDER,i,d->slides[page].count,e);
    if(status!=EXR_OK) return status;
    multiply(matrix,shape->matrix,combined);
    if(shape->texture) {
      status=texture_draw(d,shape,combined,sink,control,e);
      if(status!=EXR_OK) return status;
      style.flags&=~EXR_DRAW_FILL;
    }
    if(sink->path && style.flags) {
      status=sink->path(sink->context,path,shape_path(shape,path),combined,&style,e);
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
