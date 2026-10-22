/* SPDX-License-Identifier: MIT */
#include "pdf_internal.h"
#include "exr/pdf_edit.h"
#include <inttypes.h>
static const char *const property_keys[]={
  "http://purl.org/dc/terms/description","http://purl.org/dc/terms/creator",
  "http://purl.org/dc/terms/subject","http://ns.adobe.com/xap/1.0/CreateDate",
  "http://ns.adobe.com/xap/1.0/ModifyDate"
};
static const char *const property_names[]={"Contents","T","Subj","CreationDate","M"};
typedef struct { uint32_t raw,value; unsigned remove; } annotation_slot;
typedef struct { uint32_t object,generation; size_t offset; } revision_object;
typedef struct {
  exr_pdf_file *file; exr_buffer bytes; exr_status status;
  const exr_control *control; exr_error *error;
  size_t input_size; revision_object *objects; size_t count,capacity;
} pdf_writer;
typedef struct { double x,y; } point;
static double cross(point a,point b,point c) { return (b.x-a.x)*(c.y-a.y)-(b.y-a.y)*(c.x-a.x); }
/* Accept both perimeter and PDF text-markup Z order without self-intersection. */
static int quad_hull(const double *quad,point hull[8]) {
  point sorted[4]; size_t i,j,n=0,lower;
  for(i=0;i<4;i++) {
    point p={quad[i*2],quad[i*2+1]}; j=i;
    while(j && (sorted[j-1].x>p.x || (sorted[j-1].x==p.x && sorted[j-1].y>p.y))) { sorted[j]=sorted[j-1]; j--; }
    sorted[j]=p;
  }
  for(i=0;i<4;i++) { while(n>=2 && cross(hull[n-2],hull[n-1],sorted[i])<=0) n--; hull[n++]=sorted[i]; }
  lower=n;
  for(i=3;i>0;i--) { point p=sorted[i-1]; while(n>lower && cross(hull[n-2],hull[n-1],p)<=0) n--; hull[n++]=p; }
  return n==5;
}
/* The first edge declares text orientation. Match the opposite corners by
   hull adjacency, so both Z order and perimeter order retain that orientation. */
static int quad_edges(const double *quad,const point hull[8],point edges[4]) {
  size_t i,first=4,second=4;
  for(i=0;i<4;i++) {
    if(hull[i].x==quad[0] && hull[i].y==quad[1]) first=i;
    if(hull[i].x==quad[2] && hull[i].y==quad[3]) second=i;
  }
  if(first==4 || second==4) return 0;
  edges[0]=hull[first]; edges[1]=hull[second];
  if((first+1)%4==second) { edges[2]=hull[(first+3)%4]; edges[3]=hull[(first+2)%4]; }
  else if((first+3)%4==second) { edges[2]=hull[(first+1)%4]; edges[3]=hull[(first+2)%4]; }
  else return 0;
  return 1;
}
static int line_markup(const char *kind) {
  return !strcmp(kind,"Underline") || !strcmp(kind,"StrikeOut") || !strcmp(kind,"Squiggly");
}
static exr_status text_valid(const char *s,int nonempty,int encode,exr_error *e) {
  size_t n=0,at=0,encoded=2; uint32_t cp;
  if(!s || (nonempty && !*s)) return exr_fail(e,EXR_ARGUMENT,"Missing PDF annotation text");
  while(n<=65536 && s[n]) n++;
  if(n>65536) return exr_fail(e,EXR_LIMIT,"PDF annotation text exceeds 64 KiB");
  while(at<n) {
    if(!exr_next(s,n,&at,&cp)) return exr_fail(e,EXR_ENCODING,"PDF annotation text is not UTF-8");
    encoded+=cp>0xffff ? 4 : 2;
  }
  if(encode && encoded>65536) return exr_fail(e,EXR_LIMIT,"PDF annotation UTF-16 string exceeds 64 KiB");
  return EXR_OK;
}
static exr_status validate(const exr_page_annotation *a,const exr_control *control,exr_error *e) {
  size_t i,j; unsigned seen=0; exr_status status;
  if(!a || !a->kind || (strcmp(a->kind,"Text") && strcmp(a->kind,"Highlight") && !line_markup(a->kind)))
    return exr_fail(e,EXR_ARGUMENT,"Unsupported PDF annotation subtype");
  status=text_valid(a->id,1,1,e); if(status!=EXR_OK) return status;
  for(i=0;i<4;i++) if(!isfinite(a->bounds[i]) || fabs(a->bounds[i])>1e7)
    return exr_fail(e,EXR_ARGUMENT,"Invalid PDF annotation bounds");
  if(a->bounds[0]>=a->bounds[2] || a->bounds[1]>=a->bounds[3]) return exr_fail(e,EXR_ARGUMENT,"PDF annotation bounds require positive area");
  if(a->bounds[2]-a->bounds[0]>1e7 || a->bounds[3]-a->bounds[1]>1e7) return exr_fail(e,EXR_ARGUMENT,"PDF annotation dimensions exceed appearance bounds");
  if(a->quad_count>32768) return exr_fail(e,EXR_LIMIT,"PDF annotation exceeds 32768 quads");
  if((a->quad_count && !a->quads) || (!strcmp(a->kind,"Text") ? a->quad_count!=0 : a->quad_count==0))
    return exr_fail(e,EXR_ARGUMENT,"Invalid quads for PDF annotation subtype");
  for(i=0;i<a->quad_count;i++) {
    point hull[8],edges[4]; const double *q=a->quads+i*8;
    if((i&255)==0 && (status=exr_control_cancel(control,e))!=EXR_OK) return status;
    for(j=0;j<8;j++) if(!isfinite(q[j]) || q[j]<a->bounds[j%2] || q[j]>a->bounds[j%2+2])
      return exr_fail(e,EXR_ARGUMENT,"PDF annotation quad is outside its bounds");
    if(!quad_hull(q,hull)) return exr_fail(e,EXR_ARGUMENT,"PDF annotation quad must have four convex corners");
    if(line_markup(a->kind) && !quad_edges(q,hull,edges))
      return exr_fail(e,EXR_ARGUMENT,"PDF line markup requires its first two corners to declare the text top edge");
  }
  if(a->property_count>5) return exr_fail(e,EXR_ARGUMENT,"Unsupported PDF annotation properties");
  if(a->property_count && !a->properties) return exr_fail(e,EXR_ARGUMENT,"Missing PDF annotation properties");
  for(i=0;i<a->property_count;i++) {
    if(!a->properties[i].key) return exr_fail(e,EXR_ARGUMENT,"Missing PDF annotation property key");
    for(j=0;j<5;j++) if(!strcmp(a->properties[i].key,property_keys[j])) break;
    if(j==5 || (seen&(1u<<j))) return exr_fail(e,EXR_ARGUMENT,"Unsupported or duplicate PDF annotation property");
    seen|=1u<<j; status=text_valid(a->properties[i].value,0,1,e); if(status!=EXR_OK) return status;
  }
  return EXR_OK;
}
static void add(pdf_writer *w,const char *s,size_t n) {
  if(w->status!=EXR_OK) return;
  if(w->bytes.size>EXR_MAX_TEXT || n>EXR_MAX_TEXT-w->bytes.size) w->status=exr_fail(w->error,EXR_LIMIT,"PDF revision exceeds 64 MiB");
  else if(!exr_append(&w->bytes,s,n)) w->status=exr_fail(w->error,EXR_MEMORY,"PDF revision allocation failed");
}
static void literal(pdf_writer *w,const char *s) { add(w,s,strlen(s)); }
static void format(pdf_writer *w,const char *fmt,...) {
  char text[128]; int n; va_list args;
  if(w->status!=EXR_OK) return;
  va_start(args,fmt); n=vsnprintf(text,sizeof(text),fmt,args); va_end(args);
  if(n<0 || (size_t)n>=sizeof(text)) w->status=exr_fail(w->error,EXR_LIMIT,"PDF revision number exceeds bounds");
  else add(w,text,(size_t)n);
}
static void number(pdf_writer *w,double value) {
  if(w->status==EXR_OK) w->status=exr_pdf_real(&w->bytes,value,w->error);
}
static void numbers(pdf_writer *w,const double *values,size_t n) {
  size_t i; for(i=0;i<n && w->status==EXR_OK;i++) { if(i) literal(w," "); number(w,values[i]); }
}
static void string(pdf_writer *w,const char *s) {
  static const char hex[]="0123456789ABCDEF"; size_t n=strlen(s),at=0; uint32_t cp;
  literal(w,"<FEFF");
  while(at<n && w->status==EXR_OK) {
    uint16_t units[2]; size_t count=1,i;
    if(!exr_next(s,n,&at,&cp)) { w->status=exr_fail(w->error,EXR_ENCODING,"Invalid UTF-8 annotation text"); break; }
    if(cp>0xffff) { cp-=0x10000; units[0]=(uint16_t)(0xd800+(cp>>10)); units[1]=(uint16_t)(0xdc00+(cp&1023)); count=2; }
    else units[0]=(uint16_t)cp;
    for(i=0;i<count;i++) { char bytes[4]; unsigned v=units[i]; bytes[0]=hex[v>>12]; bytes[1]=hex[(v>>8)&15]; bytes[2]=hex[(v>>4)&15]; bytes[3]=hex[v&15]; add(w,bytes,4); }
  }
  literal(w,">");
}
static void serialized(pdf_writer *w,uint32_t value,const char *const *skip,size_t n) {
  if(w->status==EXR_OK) w->status=exr_pdf_serialize(w->file,value,skip,n,&w->bytes,w->control,w->error);
}
static void dictionary(pdf_writer *w,uint32_t value,const char *const *skip,size_t n) {
  if(value==EXR_PDF_NONE) literal(w,"<<");
  else { serialized(w,value,skip,n); if(w->status==EXR_OK) w->bytes.size-=2; }
}
static void begin_object(pdf_writer *w,uint32_t id,uint32_t generation) {
  revision_object *items; size_t i;
  if(w->status!=EXR_OK) return;
  for(i=0;i<w->count;i++) if(w->objects[i].object==id) { w->status=exr_fail(w->error,EXR_FORMAT,"PDF revision objects alias each other"); return; }
  if(w->count==32768) { w->status=exr_fail(w->error,EXR_LIMIT,"PDF revision object limit exceeded"); return; }
  if(w->count==w->capacity) {
    size_t capacity=w->capacity ? w->capacity*2 : 8;
    items=realloc(w->objects,capacity*sizeof(*items));
    if(!items) { w->status=exr_fail(w->error,EXR_MEMORY,"PDF revision object allocation failed"); return; }
    w->objects=items; w->capacity=capacity;
  }
  w->objects[w->count++]=(revision_object){id,generation,w->input_size+w->bytes.size};
  format(w,"%" PRIu32 " %" PRIu32 " obj\n",id,generation);
}
static point quad_position(const point edges[4],double along,double down) {
  point top={edges[0].x+(edges[1].x-edges[0].x)*along,edges[0].y+(edges[1].y-edges[0].y)*along};
  point bottom={edges[2].x+(edges[3].x-edges[2].x)*along,edges[2].y+(edges[3].y-edges[2].y)*along};
  return (point){top.x+(bottom.x-top.x)*down,top.y+(bottom.y-top.y)*down};
}
static void path_point(pdf_writer *w,point p,const exr_page_annotation *a,int first) {
  number(w,p.x-a->bounds[0]); literal(w," "); number(w,p.y-a->bounds[1]); literal(w,first ? " m " : " l ");
}
static void line_appearance(pdf_writer *w,const exr_page_annotation *a,size_t *segments) {
  size_t i,j; int squiggly=!strcmp(a->kind,"Squiggly"),strike=!strcmp(a->kind,"StrikeOut");
  for(i=0;i<a->quad_count && w->status==EXR_OK;i++) {
    point hull[8],edges[4]; int forward; size_t steps=1; double top=strike ? .46 : .90,bottom=strike ? .54 : .98;
    if(!quad_hull(a->quads+i*8,hull) || !quad_edges(a->quads+i*8,hull,edges)) {
      w->status=exr_fail(w->error,EXR_ARGUMENT,"Invalid PDF line markup quad"); break;
    }
    if((i&255)==0) w->status=exr_control_cancel(w->control,w->error);
    forward=cross(edges[0],edges[1],edges[3])>0;
    if(squiggly) {
      double length=(hypot(edges[1].x-edges[0].x,edges[1].y-edges[0].y)+hypot(edges[3].x-edges[2].x,edges[3].y-edges[2].y))*.5;
      double height=(hypot(edges[2].x-edges[0].x,edges[2].y-edges[0].y)+hypot(edges[3].x-edges[1].x,edges[3].y-edges[1].y))*.5;
      double required=ceil(4*length/height);
      if(!isfinite(required) || required>16384) { w->status=exr_fail(w->error,EXR_LIMIT,"PDF squiggly exceeds 16384 appearance intervals"); break; }
      steps=(size_t)required; if(steps<2) steps=2; if(steps&1) steps++;
    }
    /* One fill unions all strips without alpha darkening or reversed winding
       cancellation. Stay below the renderer's bounded path allocation. */
    if(2*(steps+1)+1>1048576-*segments) { w->status=exr_fail(w->error,EXR_LIMIT,"PDF annotation appearance exceeds one million path segments"); break; }
    *segments+=2*(steps+1)+1;
    for(j=0;j<=steps && w->status==EXR_OK;j++) {
      size_t at=forward ? j : steps-j; double down=squiggly ? .90+(at%2 ? .05 : -.05)-.025 : top;
      if((j&255)==0) w->status=exr_control_cancel(w->control,w->error);
      path_point(w,quad_position(edges,(double)at/steps,down),a,j==0);
    }
    for(j=0;j<=steps && w->status==EXR_OK;j++) {
      size_t at=forward ? steps-j : j; double down=squiggly ? .90+(at%2 ? .05 : -.05)+.025 : bottom;
      if((j&255)==0) w->status=exr_control_cancel(w->control,w->error);
      path_point(w,quad_position(edges,(double)at/steps,down),a,0);
    }
    literal(w,"h\n");
  }
  literal(w,"f\n");
}
static void appearance(pdf_writer *w,uint32_t id,const exr_page_annotation *a,uint32_t color,double opacity) {
  exr_buffer content={0}; pdf_writer p={0}; double width=a->bounds[2]-a->bounds[0],height=a->bounds[3]-a->bounds[1];
  double rgb[3]={(double)((color>>16)&255)/255,(double)((color>>8)&255)/255,(double)(color&255)/255}; size_t i,j;
  p.status=EXR_OK; p.error=w->error; p.control=w->control;
  literal(&p,"q /GS gs "); numbers(&p,rgb,3); literal(&p," rg\n");
  if(!strcmp(a->kind,"Highlight")) {
    for(i=0;i<a->quad_count && p.status==EXR_OK;i++) {
      point hull[8]; (void)quad_hull(a->quads+i*8,hull);
      if((i&255)==0) p.status=exr_control_cancel(w->control,w->error);
      for(j=0;j<4;j++) { number(&p,hull[j].x-a->bounds[0]); literal(&p," "); number(&p,hull[j].y-a->bounds[1]); literal(&p,j ? " l " : " m "); }
      literal(&p,"h\n");
    }
    literal(&p,"f\n");
  } else if(line_markup(a->kind)) {
    size_t segments=0; line_appearance(&p,a,&segments);
  } else {
    literal(&p,"0.2 0.2 0.2 RG "); number(&p,fmin(width,height)/32); literal(&p," w 0 0 "); number(&p,width); literal(&p," "); number(&p,height); literal(&p," re B\n");
    number(&p,width*.65); literal(&p," "); number(&p,height); literal(&p," m "); number(&p,width*.65); literal(&p," "); number(&p,height*.65);
    literal(&p," l "); number(&p,width); literal(&p," "); number(&p,height*.65); literal(&p," l S\n");
  }
  literal(&p,"Q\n"); content=p.bytes;
  if(p.status!=EXR_OK) { w->status=p.status; free(content.data); return; }
  begin_object(w,id,0); literal(w,"<< /Type /XObject /Subtype /Form /FormType 1 /BBox [0 0 "); number(w,width); literal(w," "); number(w,height);
  literal(w,"] /Resources << /ExtGState << /GS << /Type /ExtGState /ca "); number(w,opacity); literal(w," /CA "); number(w,opacity);
  format(w," >> >> >> /Length %zu >>\nstream\n",content.size); add(w,content.data,content.size); literal(w,"endstream\nendobj\n"); free(content.data);
}
static exr_status slots(exr_pdf_file *file,uint32_t annotations,const char *id,const exr_control *control,
  annotation_slot **out,size_t *count,size_t *match,exr_error *e) {
  const exr_pdf_value *v; annotation_slot *items=NULL; uint32_t first,at; size_t n=0,i; exr_status status;
  *out=NULL; *count=0; *match=SIZE_MAX;
  status=exr_pdf_resolve(file,annotations,&annotations,e); if(status!=EXR_OK) return status;
  v=exr_pdf_value_at(file,annotations); if(!v || v->kind==EXR_PDF_NULL) return EXR_OK;
  if(v->kind!=EXR_PDF_ARRAY) return exr_fail(e,EXR_FORMAT,"PDF Annots is not an array");
  first=v->first;
  for(at=first;at!=EXR_PDF_NONE;at=exr_pdf_value_at(file,at)->next) if(n++==4096) return exr_fail(e,EXR_LIMIT,"PDF page exceeds 4096 annotations");
  if(n && !(items=calloc(n,sizeof(*items)))) return exr_fail(e,EXR_MEMORY,"PDF annotation slots allocation failed");
  for(at=first,i=0;at!=EXR_PDF_NONE;i++) {
    uint32_t next=exr_pdf_value_at(file,at)->next,resolved; char *name=NULL;
    status=exr_control_poll(control,EXR_STAGE_READ,i,n,e); if(status!=EXR_OK) goto failure;
    status=exr_pdf_resolve(file,at,&resolved,e); if(status!=EXR_OK) goto failure;
    items[i]=(annotation_slot){at,resolved,0}; v=exr_pdf_value_at(file,resolved);
    if(v && v->kind!=EXR_PDF_NULL) {
      if(v->kind!=EXR_PDF_DICT) { status=exr_fail(e,EXR_FORMAT,"PDF annotation is not a dictionary"); goto failure; }
      status=exr_pdf_metadata_string(file,exr_pdf_get(file,resolved,"NM"),&name,e); if(status!=EXR_OK) goto failure;
      if(name && !strcmp(name,id)) {
        free(name); if(*match!=SIZE_MAX) { status=exr_fail(e,EXR_FORMAT,"Ambiguous PDF annotation ID"); goto failure; } *match=i;
      } else free(name);
    }
    at=next;
  }
  *out=items; *count=n; return EXR_OK;
failure:
  free(items); return status;
}
static exr_status permission(exr_pdf_file *file,exr_error *e) {
  uint32_t value; const exr_pdf_value *v; exr_status status;
  status=exr_pdf_resolve(file,exr_pdf_get(file,exr_pdf_root(file),"Perms"),&value,e); if(status!=EXR_OK) return status;
  v=exr_pdf_value_at(file,value);
  return !v || v->kind==EXR_PDF_NULL ? EXR_OK : exr_fail(e,EXR_FORMAT,"PDF catalog permission constraints are unsupported for writing");
}
static void annotation_object(pdf_writer *w,uint32_t object,uint32_t generation,uint32_t previous,uint32_t page,uint32_t page_generation,
  uint32_t ap,const exr_page_annotation *a,uint32_t color,double opacity) {
  static const char *const skip[]={"Type","Subtype","NM","Rect","QuadPoints","P","Contents","T","Subj","CreationDate","M","AP","C","CA","RC","AS"};
  double rgb[3]={(double)((color>>16)&255)/255,(double)((color>>8)&255)/255,(double)(color&255)/255}; size_t i,j;
  begin_object(w,object,generation); dictionary(w,previous,skip,sizeof(skip)/sizeof(*skip));
  format(w," /Type /Annot /Subtype /%s /P %" PRIu32 " %" PRIu32 " R /NM ",a->kind,page,page_generation); string(w,a->id);
  literal(w," /Rect ["); numbers(w,a->bounds,4); literal(w,"]");
  if(previous==EXR_PDF_NONE) literal(w," /F 4");
  if(a->quad_count) {
    literal(w," /QuadPoints [");
    for(i=0;i<a->quad_count && w->status==EXR_OK;i++) {
      if((i&255)==0) w->status=exr_control_cancel(w->control,w->error);
      if(i) literal(w," ");
      numbers(w,a->quads+i*8,8);
    }
    literal(w,"]");
  }
  for(i=0;i<a->property_count;i++) {
    for(j=0;j<5;j++) if(!strcmp(a->properties[i].key,property_keys[j])) break;
    format(w," /%s ",property_names[j]); string(w,a->properties[i].value);
  }
  literal(w," /C ["); numbers(w,rgb,3); literal(w,"] /CA "); number(w,opacity);
  format(w," /AP << /N %" PRIu32 " 0 R >> >>\nendobj\n",ap);
}
static void page_object(pdf_writer *w,const exr_pdf_page_info *page,uint32_t object,uint32_t generation,
  const annotation_slot *items,size_t n,size_t match,uint32_t annotation,uint32_t annotation_generation,int removing) {
  static const char *const skip[]={"Annots"}; size_t i;
  begin_object(w,object,generation); dictionary(w,page->object,skip,1); literal(w," /Annots [");
  for(i=0;i<n && w->status==EXR_OK;i++) {
    if(items[i].remove) continue;
    if(!removing && i==match) format(w,"%" PRIu32 " %" PRIu32 " R",annotation,annotation_generation);
    else serialized(w,items[i].raw,NULL,0);
    literal(w," ");
  }
  if(!removing && match==SIZE_MAX) format(w,"%" PRIu32 " %" PRIu32 " R",annotation,annotation_generation);
  literal(w,"] >>\nendobj\n");
}
static void finish(pdf_writer *w,const exr_pdf_revision_info *revision,size_t new_size,uint32_t root,uint32_t info) {
  size_t i,j,start=w->input_size+w->bytes.size;
  for(i=1;i<w->count;i++) { revision_object o=w->objects[i]; j=i; while(j && w->objects[j-1].object>o.object) { w->objects[j]=w->objects[j-1]; j--; } w->objects[j]=o; }
  literal(w,"xref\n");
  for(i=0;i<w->count;i++) format(w,"%" PRIu32 " 1\n%010zu %05" PRIu32 " n \n",w->objects[i].object,w->objects[i].offset,w->objects[i].generation);
  format(w,"trailer\n<< /Size %zu /Prev %zu /Root ",new_size,revision->startxref);
  if(root==EXR_PDF_NONE) serialized(w,revision->root,NULL,0); else format(w,"%" PRIu32 " 0 R",root);
  if(info!=EXR_PDF_NONE) format(w," /Info %" PRIu32 " 0 R",info);
  else if(revision->info!=EXR_PDF_NONE) { literal(w," /Info "); serialized(w,revision->info,NULL,0); }
  if(revision->id!=EXR_PDF_NONE) { literal(w," /ID "); serialized(w,revision->id,NULL,0); }
  format(w," >>\nstartxref\n%zu\n%%%%EOF\n",start);
}
static exr_status output(pdf_writer *w,const void *input,void **out,size_t *out_size) {
  unsigned char *copy; size_t size; exr_status status;
  if(w->status!=EXR_OK) return w->status;
  if(w->input_size>EXR_MAX_INPUT || w->bytes.size>EXR_MAX_INPUT-w->input_size) return exr_fail(w->error,EXR_LIMIT,"Written PDF exceeds 128 MiB");
  size=w->input_size+w->bytes.size;
  status=exr_control_cancel(w->control,w->error); if(status!=EXR_OK) return status;
  copy=malloc(size); if(!copy) return exr_fail(w->error,EXR_MEMORY,"Written PDF allocation failed");
  memcpy(copy,input,w->input_size); if(w->bytes.size) memcpy(copy+w->input_size,w->bytes.data,w->bytes.size);
  status=exr_control_poll(w->control,EXR_STAGE_EXPORT,size,size,w->error);
  if(status!=EXR_OK) { free(copy); return status; }
  *out=copy; *out_size=size; return exr_fail(w->error,EXR_OK,"");
}
static exr_status edit(const void *data,size_t size,size_t page_index,const char *id,const exr_page_annotation *a,
  uint32_t color,double opacity,const exr_control *control,void **out,size_t *out_size,exr_error *e) {
  pdf_writer w={0}; exr_pdf_page_info *pages=NULL; annotation_slot *items=NULL; exr_pdf_revision_info revision;
  size_t page_count=0,n=0,match=SIZE_MAX,i; uint32_t page_object_id,page_generation,annotation=0,generation=0,ap=0; exr_status status;
  w.status=EXR_OK; w.error=e; w.control=control; w.input_size=size;
  status=exr_control_poll(control,EXR_STAGE_READ,0,size,e); if(status!=EXR_OK) return status;
  status=exr_pdf_open(data,size,&w.file,e); if(status!=EXR_OK) return status;
  status=exr_pdf_pages(w.file,&pages,&page_count,e); if(status!=EXR_OK) goto done;
  if(page_index>=page_count) { status=exr_fail(e,EXR_ARGUMENT,"PDF annotation page is out of range"); goto done; }
  status=slots(w.file,pages[page_index].annotations,id,control,&items,&n,&match,e); if(status!=EXR_OK) goto done;
  if(!a && match==SIZE_MAX) { status=output(&w,data,out,out_size); goto done; }
  status=permission(w.file,e); if(status!=EXR_OK) goto done;
  if(a && ((const unsigned char *)data)[5]=='1' && ((const unsigned char *)data)[7]<'4') {
    status=exr_fail(e,EXR_FORMAT,"PDF annotation appearance writing requires PDF 1.4 or newer"); goto done;
  }
  status=exr_pdf_object_identity(w.file,pages[page_index].object,&page_object_id,&page_generation,e); if(status!=EXR_OK) goto done;
  exr_pdf_revision(w.file,&revision);
  if(a) {
    size_t needed=2;
    if(match!=SIZE_MAX) {
      const exr_pdf_value *raw=exr_pdf_value_at(w.file,items[match].raw);
      if(raw && raw->kind==EXR_PDF_REF) {
        status=exr_pdf_object_identity(w.file,items[match].raw,&annotation,&generation,e); if(status!=EXR_OK) goto done; needed=1;
        if(annotation==page_object_id) { status=exr_fail(e,EXR_FORMAT,"PDF page and annotation share an object"); goto done; }
      }
    } else if(n==4096) { status=exr_fail(e,EXR_LIMIT,"PDF page exceeds 4096 annotations"); goto done; }
    if(revision.size>EXR_PDF_MAX_VALUES-needed) { status=exr_fail(e,EXR_LIMIT,"PDF annotation object limit exceeded"); goto done; }
    ap=(uint32_t)revision.size; if(needed==2) annotation=ap+1;
    literal(&w,"\n"); appearance(&w,ap,a,color,opacity);
    annotation_object(&w,annotation,generation,match==SIZE_MAX ? EXR_PDF_NONE : items[match].value,page_object_id,page_generation,ap,a,color,opacity);
    page_object(&w,&pages[page_index],page_object_id,page_generation,items,n,match,annotation,generation,0);
    finish(&w,&revision,revision.size+needed,EXR_PDF_NONE,EXR_PDF_NONE);
  } else {
    uint32_t popup; status=exr_pdf_resolve(w.file,exr_pdf_get(w.file,items[match].value,"Popup"),&popup,e); if(status!=EXR_OK) goto done;
    items[match].remove=1;
    /* Some files only keep Popup -> Parent, without the reverse link. */
    for(i=0;i<n;i++) if(!items[i].remove) {
      uint32_t subtype,parent; size_t length; const unsigned char *name; const exr_pdf_value *v;
      v=exr_pdf_value_at(w.file,items[i].value); if(!v || v->kind!=EXR_PDF_DICT) continue;
      status=exr_pdf_resolve(w.file,exr_pdf_get(w.file,items[i].value,"Subtype"),&subtype,e); if(status!=EXR_OK) goto done;
      v=exr_pdf_value_at(w.file,subtype); name=exr_pdf_bytes(w.file,subtype,&length);
      if(!v || v->kind!=EXR_PDF_NAME || length!=5 || !name || memcmp(name,"Popup",5)) continue;
      if(popup!=EXR_PDF_NONE && items[i].value==popup) { items[i].remove=1; continue; }
      status=exr_pdf_resolve(w.file,exr_pdf_get(w.file,items[i].value,"Parent"),&parent,e); if(status!=EXR_OK) goto done;
      if(parent==items[match].value) items[i].remove=1;
    }
    literal(&w,"\n"); page_object(&w,&pages[page_index],page_object_id,page_generation,items,n,match,0,0,1); finish(&w,&revision,revision.size,EXR_PDF_NONE,EXR_PDF_NONE);
  }
  status=output(&w,data,out,out_size);
done:
  free(w.objects); free(w.bytes.data); free(items); free(pages); exr_pdf_close(w.file); return status;
}
exr_pdf_annotation_write_options exr_pdf_annotation_write_defaults(void) {
  exr_pdf_annotation_write_options options={0}; options.struct_size=sizeof(options); options.color=0xffff00; options.opacity=.35; return options;
}
exr_status exr_pdf_annotation_write(const void *data,size_t size,size_t page,const exr_page_annotation *a,
  const exr_pdf_annotation_write_options *options,void **out,size_t *out_size,exr_error *e) {
  exr_pdf_annotation_write_options config=exr_pdf_annotation_write_defaults(); exr_status status; size_t i;
  if(out) *out=NULL;
  if(out_size) *out_size=0;
  if(!out || !out_size) return exr_fail(e,EXR_ARGUMENT,"Missing written PDF outputs");
  if(options) {
    if(options->struct_size<sizeof(config) || options->struct_size>4096) return exr_fail(e,EXR_ARGUMENT,"Invalid PDF annotation write options size");
    for(i=sizeof(config);i<options->struct_size;i++) if(((const unsigned char *)options)[i]) return exr_fail(e,EXR_ARGUMENT,"Unsupported PDF annotation write options extension");
    config=*options;
  }
  if(config.color>0xffffff || !isfinite(config.opacity) || config.opacity<0 || config.opacity>1)
    return exr_fail(e,EXR_ARGUMENT,"Invalid PDF annotation color or opacity");
  status=exr_control_cancel(&config.control,e); if(status!=EXR_OK) return status;
  status=validate(a,&config.control,e); if(status!=EXR_OK) return status;
  return edit(data,size,page,a->id,a,config.color,config.opacity,&config.control,out,out_size,e);
}
exr_status exr_pdf_annotation_remove(const void *data,size_t size,size_t page,const char *id,
  const exr_control *control,void **out,size_t *out_size,exr_error *e) {
  exr_status status;
  if(out) *out=NULL;
  if(out_size) *out_size=0;
  if(!out || !out_size) return exr_fail(e,EXR_ARGUMENT,"Missing written PDF outputs");
  status=exr_control_cancel(control,e); if(status!=EXR_OK) return status;
  status=text_valid(id,1,0,e); if(status!=EXR_OK) return status;
  return edit(data,size,page,id,NULL,0,0,control,out,out_size,e);
}
typedef struct { unsigned part[6],precision,zone,hours,minutes; } metadata_date;
static int date_digits(const char **at,const char *end,unsigned digits,unsigned *out) {
  unsigned i,value=0; const char *p=*at;
  if((size_t)(end-p)<digits) return 0;
  for(i=0;i<digits;i++) { if(p[i]<'0' || p[i]>'9') return 0; value=value*10+(unsigned)(p[i]-'0'); }
  *at=p+digits; *out=value; return 1;
}
static exr_status date_convert(const char *text,char pdf[32],char xmp[32],exr_error *e) {
  static const unsigned days[]={31,28,31,30,31,30,31,31,30,31,30,31};
  metadata_date date={{0},0,0,0,0}; const char *at=text,*end=text+strlen(text); size_t a,b; unsigned i;
  int native=(end-at>=2 && at[0]=='D' && at[1]==':');
  if(native) at+=2;
  if(!date_digits(&at,end,4,date.part)) goto invalid;
  date.precision=1;
  if(native) {
    while(at<end && *at>='0' && *at<='9' && date.precision<6) {
      if(!date_digits(&at,end,2,date.part+date.precision)) goto invalid;
      date.precision++;
    }
    /* XMP date-time precision includes at least hours and minutes. */
    if(date.precision==4) goto unsupported;
  } else {
    while(date.precision<3 && at<end && *at=='-') {
      at++; if(!date_digits(&at,end,2,date.part+date.precision)) goto invalid;
      date.precision++;
    }
    if(at<end && *at=='T') {
      if(date.precision!=3) goto invalid;
      at++; if(!date_digits(&at,end,2,date.part+3) || at==end || *at++!=':' || !date_digits(&at,end,2,date.part+4)) goto invalid;
      date.precision=5;
      if(at<end && *at==':') { at++; if(!date_digits(&at,end,2,date.part+5)) goto invalid; date.precision=6; }
      if(at<end && *at=='.') {
        const char *fraction=++at; int nonzero=0;
        if(date.precision!=6) goto invalid;
        while(at<end && *at>='0' && *at<='9') { if(*at!='0') nonzero=1; at++; }
        if(at==fraction) goto invalid;
        if(nonzero) goto unsupported;
      }
    }
  }
  if(at<end) {
    if(date.precision<5) goto unsupported;
    if(*at=='Z') { date.zone=1; at++; }
    else if(*at=='+' || *at=='-') {
      date.zone=*at++=='+' ? 2 : 3;
      if(!date_digits(&at,end,2,&date.hours)) goto invalid;
      if(at<end) {
        int quote=native && *at=='\'';
        if(*at==':' || quote) at++;
        if(!date_digits(&at,end,2,&date.minutes)) goto invalid;
        if(quote && at<end && *at=='\'') at++;
      }
    } else goto invalid;
  }
  if(at!=end || !date.part[0] || date.part[0]>9999 || (date.precision>=2 && (!date.part[1] || date.part[1]>12)) ||
     date.part[3]>23 || date.part[4]>59 || date.part[5]>59 || date.hours>23 || date.minutes>59) goto invalid;
  if(date.precision>=3) {
    unsigned maximum=days[date.part[1]-1],year=date.part[0];
    if(date.part[1]==2 && year%4==0 && (year%100!=0 || year%400==0)) maximum++;
    if(!date.part[2] || date.part[2]>maximum) goto invalid;
  }
  a=(size_t)snprintf(pdf,32,"D:%04u",date.part[0]); b=(size_t)snprintf(xmp,32,"%04u",date.part[0]);
  for(i=1;i<date.precision;i++) {
    a+=(size_t)snprintf(pdf+a,32-a,"%02u",date.part[i]);
    b+=(size_t)snprintf(xmp+b,32-b,"%c%02u",i<3 ? '-' : i==3 ? 'T' : ':',date.part[i]);
  }
  if(date.zone==1) { snprintf(pdf+a,32-a,"Z"); snprintf(xmp+b,32-b,"Z"); }
  else if(date.zone) {
    snprintf(pdf+a,32-a,"%c%02u'%02u'",date.zone==2 ? '+' : '-',date.hours,date.minutes);
    snprintf(xmp+b,32-b,"%c%02u:%02u",date.zone==2 ? '+' : '-',date.hours,date.minutes);
  }
  return EXR_OK;
unsupported:
  return exr_fail(e,EXR_ARGUMENT,"PDF/XMP date precision cannot be represented without losing information");
invalid:
  return exr_fail(e,EXR_ARGUMENT,"Invalid PDF D: or ISO8601 metadata date");
}
exr_status exr_pdf_metadata_write(const void *data,size_t size,const exr_metadata_entry *changes,size_t count,
  const exr_control *control,void **out,size_t *out_size,exr_error *e) {
  static const char *const names[]={"Title","Author","Subject","Keywords","Creator","Producer","CreationDate","ModDate"};
  static const char *const keys[]={"http://purl.org/dc/terms/title","http://purl.org/dc/terms/creator","http://purl.org/dc/terms/description",
    "http://ns.adobe.com/pdf/1.3/Keywords","http://ns.adobe.com/xap/1.0/CreatorTool","http://ns.adobe.com/pdf/1.3/Producer",
    "http://ns.adobe.com/xap/1.0/CreateDate","http://ns.adobe.com/xap/1.0/ModifyDate"};
  static const char *const metadata_key[]={"Metadata"};
  pdf_writer w={0}; exr_pdf_revision_info revision; exr_buffer packet={0}; const char *skip[8],*info_values[8];
  exr_metadata_entry xmp_changes[8]; char info_dates[8][32],xmp_dates[8][32];
  uint32_t info,xmp,form,xfa,new_info,new_xmp=EXR_PDF_NONE,new_root=EXR_PDF_NONE;
  const exr_pdf_value *value; size_t i,j,needed=1; unsigned seen=0; exr_status status;
  if(out) *out=NULL;
  if(out_size) *out_size=0;
  if(!out || !out_size || (count && !changes)) return exr_fail(e,EXR_ARGUMENT,"Missing PDF metadata changes or outputs");
  if(count>8) return exr_fail(e,EXR_ARGUMENT,"PDF metadata writer supports eight distinct properties");
  status=exr_control_cancel(control,e); if(status!=EXR_OK) return status;
  for(i=0;i<count;i++) {
    if(!changes[i].key) return exr_fail(e,EXR_ARGUMENT,"Missing PDF metadata property key");
    for(j=0;j<8;j++) if(!strcmp(changes[i].key,keys[j])) break;
    if(j==8 || (seen&(1u<<j))) return exr_fail(e,EXR_ARGUMENT,"Unsupported or duplicate PDF metadata property");
    seen|=1u<<j; skip[i]=names[j]; info_values[i]=changes[i].value; xmp_changes[i]=changes[i];
    if(changes[i].value) { status=text_valid(changes[i].value,0,1,e); if(status!=EXR_OK) return status; }
    if(j>=6 && changes[i].value) {
      status=date_convert(changes[i].value,info_dates[i],xmp_dates[i],e); if(status!=EXR_OK) return status;
      info_values[i]=info_dates[i]; xmp_changes[i].value=xmp_dates[i];
    }
  }
  w.status=EXR_OK; w.error=e; w.control=control; w.input_size=size;
  status=exr_control_poll(control,EXR_STAGE_READ,0,size,e); if(status!=EXR_OK) return status;
  status=exr_pdf_open(data,size,&w.file,e); if(status!=EXR_OK) return status;
  if(!count) { status=output(&w,data,out,out_size); goto done; }
  status=permission(w.file,e); if(status!=EXR_OK) goto done;
  status=exr_pdf_resolve(w.file,exr_pdf_get(w.file,exr_pdf_root(w.file),"AcroForm"),&form,e); if(status!=EXR_OK) goto done;
  value=exr_pdf_value_at(w.file,form);
  if(value && value->kind!=EXR_PDF_NULL && value->kind!=EXR_PDF_DICT) { status=exr_fail(e,EXR_FORMAT,"PDF AcroForm is not a dictionary"); goto done; }
  status=exr_pdf_resolve(w.file,exr_pdf_get(w.file,form,"XFA"),&xfa,e); if(status!=EXR_OK) goto done;
  value=exr_pdf_value_at(w.file,xfa);
  if(value && value->kind!=EXR_PDF_NULL) { status=exr_fail(e,EXR_FORMAT,"PDF XFA metadata synchronization is unsupported"); goto done; }
  status=exr_pdf_resolve(w.file,exr_pdf_info(w.file),&info,e); if(status!=EXR_OK) goto done;
  value=exr_pdf_value_at(w.file,info);
  if(!value || value->kind==EXR_PDF_NULL) info=EXR_PDF_NONE;
  else if(value->kind!=EXR_PDF_DICT) { status=exr_fail(e,EXR_FORMAT,"PDF Info is not a dictionary"); goto done; }
  status=exr_pdf_resolve(w.file,exr_pdf_get(w.file,exr_pdf_root(w.file),"Metadata"),&xmp,e); if(status!=EXR_OK) goto done;
  value=exr_pdf_value_at(w.file,xmp);
  if(value && value->kind!=EXR_PDF_NULL) {
    const unsigned char *bytes; size_t n;
    if(value->kind!=EXR_PDF_STREAM) { status=exr_fail(e,EXR_FORMAT,"PDF Metadata is not a stream"); goto done; }
    status=exr_pdf_stream_data(w.file,xmp,&bytes,&n,e); if(status!=EXR_OK) goto done;
    status=exr_pdf_xmp_write(bytes,n,xmp_changes,count,control,&packet,e); if(status!=EXR_OK) goto done;
    needed=3;
  }
  exr_pdf_revision(w.file,&revision);
  if(revision.size>EXR_PDF_MAX_VALUES-needed) { status=exr_fail(e,EXR_LIMIT,"PDF metadata object limit exceeded"); goto done; }
  new_info=(uint32_t)revision.size;
  if(needed==3) { new_xmp=new_info+1; new_root=new_info+2; }
  literal(&w,"\n"); begin_object(&w,new_info,0); dictionary(&w,info,skip,count);
  for(i=0;i<count;i++) if(info_values[i]) { literal(&w," /"); literal(&w,skip[i]); literal(&w," "); string(&w,info_values[i]); }
  literal(&w," >>\nendobj\n");
  if(needed==3) {
    begin_object(&w,new_xmp,0);
    format(&w,"<< /Type /Metadata /Subtype /XML /Length %zu >>\nstream\n",packet.size);
    add(&w,packet.data,packet.size); literal(&w,"\nendstream\nendobj\n");
    begin_object(&w,new_root,0); dictionary(&w,exr_pdf_root(w.file),metadata_key,1);
    format(&w," /Metadata %" PRIu32 " 0 R >>\nendobj\n",new_xmp);
  }
  finish(&w,&revision,revision.size+needed,new_root,new_info); status=output(&w,data,out,out_size);
done:
  free(packet.data); free(w.objects); free(w.bytes.data); exr_pdf_close(w.file); return status;
}

/* AcroForm uses the same bounded object arena and revision writer as annotation
   editing. IDs, never arena pointers, survive lazy indirect-object resolution. */
typedef struct { uint32_t id,raw,inherit[8],*widgets; size_t widget_count; } form_entry;
typedef struct {
  exr_pdf_file *file; exr_pdf_form_options options; exr_error *error;
  exr_pdf_form_field *fields; form_entry *entries; size_t count,widgets,text_bytes,nodes;
  unsigned char *seen; uint32_t *pages; uint32_t acroform; unsigned issues;
} form_reader;
static const char *const form_inherited[]={"FT","Ff","V","DV","DA","Q","MaxLen","Opt"};
static exr_status form_resolve(form_reader *r,uint32_t raw,uint32_t *id) {
  return exr_pdf_resolve(r->file,raw,id,r->error);
}
static exr_status form_get(form_reader *r,uint32_t dict,const char *key,uint32_t *id) {
  return form_resolve(r,exr_pdf_get(r->file,dict,key),id);
}
static int form_kind(form_reader *r,uint32_t id,exr_pdf_kind kind) {
  const exr_pdf_value *v=exr_pdf_value_at(r->file,id); return v && v->kind==kind;
}
static int form_name_is(form_reader *r,uint32_t id,const char *name) {
  size_t n; const unsigned char *s=exr_pdf_bytes(r->file,id,&n);
  return form_kind(r,id,EXR_PDF_NAME) && n==strlen(name) && !memcmp(s,name,n);
}
static exr_status form_charge(form_reader *r,size_t n) {
  if(n>r->options.max_text_bytes-r->text_bytes) return exr_fail(r->error,EXR_LIMIT,"PDF form text budget exceeded");
  r->text_bytes+=n; return EXR_OK;
}
static exr_status form_string(form_reader *r,uint32_t id,int name,char **out) {
  exr_status status; size_t n,at=0; uint32_t cp; const unsigned char *bytes;
  *out=NULL; status=form_resolve(r,id,&id); if(status!=EXR_OK) return status;
  if(id==EXR_PDF_NONE || form_kind(r,id,EXR_PDF_NULL)) return EXR_OK;
  if(name) {
    if(!form_kind(r,id,EXR_PDF_NAME)) return exr_fail(r->error,EXR_FORMAT,"PDF form value requires a name");
    bytes=exr_pdf_bytes(r->file,id,&n);
    if(n>65536) return exr_fail(r->error,EXR_LIMIT,"PDF form name exceeds 64 KiB");
    while(at<n) if(!exr_next((const char *)bytes,n,&at,&cp) || !cp) return exr_fail(r->error,EXR_ENCODING,"PDF form name is not UTF-8");
    *out=exr_copy((const char *)bytes,n);
    if(!*out) return exr_fail(r->error,EXR_MEMORY,"PDF form name allocation failed");
  } else {
    status=exr_pdf_metadata_string(r->file,id,out,r->error); if(status!=EXR_OK) return status;
  }
  status=form_charge(r,strlen(*out)+1); if(status!=EXR_OK) { free(*out); *out=NULL; } return status;
}
static exr_status form_uint(form_reader *r,uint32_t id,uint32_t *out) {
  const exr_pdf_value *v; exr_status status=form_resolve(r,id,&id); *out=0; if(status!=EXR_OK) return status;
  v=exr_pdf_value_at(r->file,id); if(!v || v->kind==EXR_PDF_NULL) return EXR_OK;
  if(v->kind!=EXR_PDF_INT || v->u.integer<0 || (uint64_t)v->u.integer>UINT32_MAX)
    return exr_fail(r->error,EXR_FORMAT,"PDF form integer is out of range");
  *out=(uint32_t)v->u.integer; return EXR_OK;
}
static void form_values_free(const char *const *values,size_t count) {
  size_t i; for(i=0;i<count;i++) free((void *)values[i]); free((void *)values);
}
void exr_pdf_form_free(exr_pdf_form_field *fields,size_t count) {
  size_t i,j; if(!fields) return;
  for(i=0;i<count;i++) {
    free((void *)fields[i].name); form_values_free(fields[i].values,fields[i].value_count);
    form_values_free(fields[i].default_values,fields[i].default_value_count);
    for(j=0;j<fields[i].option_count;j++) { free((void *)fields[i].options[j].value); free((void *)fields[i].options[j].label); }
    for(j=0;j<fields[i].widget_count;j++) free((void *)fields[i].widgets[j].on_state);
    free((void *)fields[i].options); free((void *)fields[i].widgets);
  }
  free(fields);
}
static void form_dispose(form_reader *r) {
  size_t i; for(i=0;i<r->count;i++) free(r->entries[i].widgets);
  free(r->entries); free(r->seen); free(r->pages); exr_pdf_form_free(r->fields,r->count);
}
static exr_status form_values(form_reader *r,uint32_t id,int name,int array,const char *const **out,size_t *count) {
  uint32_t at; char **items=NULL; size_t n=0; exr_status status=form_resolve(r,id,&id);
  *out=NULL; *count=0; if(status!=EXR_OK || id==EXR_PDF_NONE || form_kind(r,id,EXR_PDF_NULL)) return status;
  if(form_kind(r,id,EXR_PDF_ARRAY)) {
    if(!array) return exr_fail(r->error,EXR_FORMAT,"PDF form scalar value is an array");
    at=exr_pdf_value_at(r->file,id)->first;
  } else at=id;
  while(at!=EXR_PDF_NONE) {
    char *s=NULL; char **next; uint32_t after=form_kind(r,id,EXR_PDF_ARRAY) ? exr_pdf_value_at(r->file,at)->next : EXR_PDF_NONE;
    if(n==4096) { status=exr_fail(r->error,EXR_LIMIT,"PDF form value count exceeds 4096"); goto failed; }
    status=form_string(r,at,name,&s); if(status!=EXR_OK) goto failed;
    if(!s) { status=exr_fail(r->error,EXR_FORMAT,"PDF form value is null"); goto failed; }
    next=realloc(items,(n+1)*sizeof(*items)); if(!next) { free(s); status=exr_fail(r->error,EXR_MEMORY,"PDF form value allocation failed"); goto failed; }
    items=next; items[n++]=s; at=after;
  }
  *out=(const char *const *)items; *count=n; return EXR_OK;
failed:
  form_values_free((const char *const *)items,n); return status;
}
static exr_status form_options_read(form_reader *r,uint32_t id,exr_pdf_form_field *field) {
  uint32_t at; exr_status status=form_resolve(r,id,&id); exr_pdf_field_option *items=NULL; size_t n=0;
  if(status!=EXR_OK || id==EXR_PDF_NONE || form_kind(r,id,EXR_PDF_NULL)) return status;
  if(!form_kind(r,id,EXR_PDF_ARRAY)) return exr_fail(r->error,EXR_FORMAT,"PDF form Opt is not an array");
  at=exr_pdf_value_at(r->file,id)->first;
  while(at!=EXR_PDF_NONE) {
    uint32_t next=exr_pdf_value_at(r->file,at)->next,value,first; char *export_value=NULL,*label=NULL; exr_pdf_field_option *more;
    if(n==4096) { status=exr_fail(r->error,EXR_LIMIT,"PDF form option count exceeds 4096"); goto done; }
    status=form_resolve(r,at,&value); if(status!=EXR_OK) goto done; first=value;
    if(form_kind(r,value,EXR_PDF_ARRAY)) {
      first=exr_pdf_value_at(r->file,value)->first;
      if(first==EXR_PDF_NONE || exr_pdf_value_at(r->file,first)->next==EXR_PDF_NONE) { status=exr_fail(r->error,EXR_FORMAT,"PDF choice option pair is incomplete"); goto done; }
      value=exr_pdf_value_at(r->file,first)->next;
      if(exr_pdf_value_at(r->file,value)->next!=EXR_PDF_NONE) { status=exr_fail(r->error,EXR_FORMAT,"PDF choice option pair exceeds two strings"); goto done; }
    }
    status=form_string(r,first,0,&export_value); if(status==EXR_OK) status=form_string(r,value,0,&label);
    if(status!=EXR_OK || !export_value || !label) { free(export_value); free(label); if(status==EXR_OK) status=exr_fail(r->error,EXR_FORMAT,"PDF choice option is null"); goto done; }
    more=realloc(items,(n+1)*sizeof(*more)); if(!more) { free(export_value); free(label); status=exr_fail(r->error,EXR_MEMORY,"PDF form option allocation failed"); goto done; }
    items=more; items[n++]=(exr_pdf_field_option){export_value,label}; at=next;
  }
done:
  field->options=items; field->option_count=n; return status;
}
static exr_status form_widget(form_reader *r,size_t field_index,uint32_t raw,uint32_t id) {
  exr_pdf_form_field *field=&r->fields[field_index]; form_entry *entry=&r->entries[field_index];
  exr_pdf_field_widget widget={0},*items; uint32_t *ids,rect,at,ap,normal,state; size_t i=0; exr_status status;
  if(r->widgets==r->options.max_widgets) return exr_fail(r->error,EXR_LIMIT,"PDF form widget budget exceeded");
  widget.page=r->pages[id]==UINT32_MAX ? SIZE_MAX : r->pages[id];
  status=form_get(r,id,"Rect",&rect); if(status!=EXR_OK) return status;
  if(!form_kind(r,rect,EXR_PDF_ARRAY)) return exr_fail(r->error,EXR_FORMAT,"PDF form widget Rect is not an array");
  for(at=exr_pdf_value_at(r->file,rect)->first;at!=EXR_PDF_NONE;) {
    const exr_pdf_value *v; uint32_t next=exr_pdf_value_at(r->file,at)->next,n;
    if(i==4) return exr_fail(r->error,EXR_FORMAT,"PDF form widget Rect exceeds four numbers");
    status=form_resolve(r,at,&n); if(status!=EXR_OK) return status; v=exr_pdf_value_at(r->file,n);
    if(!v || (v->kind!=EXR_PDF_INT && v->kind!=EXR_PDF_REAL)) return exr_fail(r->error,EXR_FORMAT,"PDF form widget coordinate is not a number");
    widget.bounds[i++]=v->kind==EXR_PDF_INT ? (double)v->u.integer : v->u.number; at=next;
  }
  if(i!=4) return exr_fail(r->error,EXR_FORMAT,"PDF form widget Rect requires four numbers");
  for(i=0;i<4;i++) if(!isfinite(widget.bounds[i]) || fabs(widget.bounds[i])>1e7) return exr_fail(r->error,EXR_LIMIT,"PDF form widget bounds exceed limits");
  if(widget.bounds[0]>=widget.bounds[2] || widget.bounds[1]>=widget.bounds[3]) return exr_fail(r->error,EXR_FORMAT,"PDF form widget bounds require positive area");
  status=form_get(r,id,"A",&state); if(status!=EXR_OK) return status; if(state!=EXR_PDF_NONE) field->issues|=EXR_PDF_FORM_ACTIONS;
  status=form_get(r,id,"AA",&state); if(status!=EXR_OK) return status; if(state!=EXR_PDF_NONE) field->issues|=EXR_PDF_FORM_ACTIONS;
  status=form_get(r,id,"AP",&ap); if(status!=EXR_OK) return status;
  if(ap!=EXR_PDF_NONE && !form_kind(r,ap,EXR_PDF_DICT)) return exr_fail(r->error,EXR_FORMAT,"PDF widget AP is not a dictionary");
  if(field->kind==EXR_PDF_FIELD_CHECKBOX || field->kind==EXR_PDF_FIELD_RADIO) {
    status=form_get(r,id,"AP",&ap); if(status==EXR_OK) status=form_get(r,ap,"N",&normal); if(status!=EXR_OK) return status;
    if(!form_kind(r,normal,EXR_PDF_DICT)) return exr_fail(r->error,EXR_FORMAT,"PDF button requires named normal appearances");
    at=exr_pdf_value_at(r->file,normal)->first;
    while(at!=EXR_PDF_NONE) {
      uint32_t value=exr_pdf_value_at(r->file,at)->next,next=exr_pdf_value_at(r->file,value)->next;
      if(!form_name_is(r,at,"Off")) {
        if(widget.on_state) { free((void *)widget.on_state); return exr_fail(r->error,EXR_FORMAT,"PDF button widget has multiple on states"); }
        status=form_string(r,at,1,(char **)&widget.on_state); if(status!=EXR_OK) return status;
      }
      at=next;
    }
    if(!widget.on_state) return exr_fail(r->error,EXR_FORMAT,"PDF button widget lacks an on state");
  }
  items=realloc((void *)field->widgets,(field->widget_count+1)*sizeof(*items));
  if(!items) { free((void *)widget.on_state); return exr_fail(r->error,EXR_MEMORY,"PDF widget allocation failed"); }
  field->widgets=items;
  ids=realloc(entry->widgets,(entry->widget_count+1)*sizeof(*ids));
  if(!ids) { free((void *)widget.on_state); return exr_fail(r->error,EXR_MEMORY,"PDF widget identity allocation failed"); }
  entry->widgets=ids; ids[entry->widget_count++]=id; items[field->widget_count++]=widget; r->widgets++;
  if(!form_kind(r,raw,EXR_PDF_REF)) field->issues|=EXR_PDF_FORM_DIRECT;
  return EXR_OK;
}
static exr_status form_walk(form_reader *r,uint32_t raw,uint32_t parent,const char *prefix,const uint32_t inherited[8],size_t depth,unsigned issues) {
  uint32_t id,local[8],kids,at,parent_id,subtype,action,flags,maxlen; size_t i,index,child_count=0,widget_count=0;
  char *partial=NULL,*name=NULL; exr_pdf_form_field *field; form_entry *entry; exr_status status;
  if(depth>r->options.max_depth) return exr_fail(r->error,EXR_LIMIT,"PDF field tree depth exceeded");
  if(++r->nodes>32768) return exr_fail(r->error,EXR_LIMIT,"PDF field tree node budget exceeded");
  status=exr_control_cancel(&r->options.control,r->error); if(status!=EXR_OK) return status;
  status=form_resolve(r,raw,&id); if(status!=EXR_OK) return status;
  if(!form_kind(r,id,EXR_PDF_DICT)) return exr_fail(r->error,EXR_FORMAT,"PDF field is not a dictionary");
  if(r->seen[id]) return exr_fail(r->error,EXR_FORMAT,"PDF field tree contains a cycle or shared child");
  r->seen[id]=1;
  status=form_get(r,id,"Parent",&parent_id); if(status!=EXR_OK) return status;
  if(parent_id!=parent) return exr_fail(r->error,EXR_FORMAT,"PDF field Parent disagrees with field tree");
  status=form_get(r,id,"A",&action); if(status!=EXR_OK) return status; if(action!=EXR_PDF_NONE) issues|=EXR_PDF_FORM_ACTIONS;
  status=form_get(r,id,"AA",&action); if(status!=EXR_OK) return status; if(action!=EXR_PDF_NONE) issues|=EXR_PDF_FORM_ACTIONS;
  for(i=0;i<8;i++) { uint32_t value=exr_pdf_get(r->file,id,form_inherited[i]); local[i]=value==EXR_PDF_NONE ? inherited[i] : value; }
  status=form_string(r,exr_pdf_get(r->file,id,"T"),0,&partial); if(status!=EXR_OK) return status;
  if(partial && (!*partial || strchr(partial,'.'))) { status=exr_fail(r->error,EXR_FORMAT,"PDF partial field name is empty or contains a dot"); goto done; }
  {
    size_t a=strlen(prefix),b=partial ? strlen(partial) : 0,n=a+b+(a && b ? 1 : 0);
    if(n>65536) { status=exr_fail(r->error,EXR_LIMIT,"PDF qualified field name exceeds 64 KiB"); goto done; }
    name=malloc(n+1); if(!name) { status=exr_fail(r->error,EXR_MEMORY,"PDF qualified name allocation failed"); goto done; }
    memcpy(name,prefix,a); if(a && b) name[a++]='.'; if(b) memcpy(name+a,partial,b); name[n]=0;
  }
  status=form_get(r,id,"Kids",&kids); if(status!=EXR_OK) goto done;
  if(kids!=EXR_PDF_NONE && !form_kind(r,kids,EXR_PDF_ARRAY)) { status=exr_fail(r->error,EXR_FORMAT,"PDF field Kids is not an array"); goto done; }
  at=kids==EXR_PDF_NONE ? EXR_PDF_NONE : exr_pdf_value_at(r->file,kids)->first;
  while(at!=EXR_PDF_NONE) {
    uint32_t child,next=exr_pdf_value_at(r->file,at)->next,t;
    status=form_resolve(r,at,&child); if(status!=EXR_OK) goto done;
    if(!form_kind(r,child,EXR_PDF_DICT)) { status=exr_fail(r->error,EXR_FORMAT,"PDF field child is not a dictionary"); goto done; }
    status=form_get(r,child,"Subtype",&t); if(status!=EXR_OK) goto done;
    if(form_name_is(r,t,"Widget") && exr_pdf_get(r->file,child,"T")==EXR_PDF_NONE && exr_pdf_get(r->file,child,"FT")==EXR_PDF_NONE && exr_pdf_get(r->file,child,"Kids")==EXR_PDF_NONE) widget_count++;
    else child_count++;
    if(child_count+widget_count>32768) { status=exr_fail(r->error,EXR_LIMIT,"PDF field child budget exceeded"); goto done; } at=next;
  }
  if(child_count && widget_count) { status=exr_fail(r->error,EXR_FORMAT,"PDF field mixes field and widget children"); goto done; }
  if(child_count) {
    at=exr_pdf_value_at(r->file,kids)->first;
    while(at!=EXR_PDF_NONE) { uint32_t next=exr_pdf_value_at(r->file,at)->next; status=form_walk(r,at,id,name,local,depth+1,issues); if(status!=EXR_OK) goto done; at=next; }
    goto done;
  }
  if(!*name) { status=exr_fail(r->error,EXR_FORMAT,"PDF terminal field has no qualified name"); goto done; }
  if(r->count==r->options.max_fields) { status=exr_fail(r->error,EXR_LIMIT,"PDF form field budget exceeded"); goto done; }
  for(i=0;i<r->count;i++) if(!strcmp(name,r->fields[i].name)) { status=exr_fail(r->error,EXR_FORMAT,"PDF form qualified names are ambiguous"); goto done; }
  status=form_charge(r,strlen(name)+1); if(status!=EXR_OK) goto done;
  index=r->count++; field=&r->fields[index]; entry=&r->entries[index]; field->struct_size=sizeof(*field); field->name=name; name=NULL;
  entry->id=id; entry->raw=raw; memcpy(entry->inherit,local,sizeof(local)); field->issues=r->issues|issues;
  if(!form_kind(r,raw,EXR_PDF_REF)) field->issues|=EXR_PDF_FORM_DIRECT;
  status=form_uint(r,local[1],&flags); if(status==EXR_OK) status=form_uint(r,local[6],&maxlen); if(status!=EXR_OK) goto done;
  field->flags=flags; field->max_length=maxlen;
  status=form_resolve(r,local[0],&subtype); if(status!=EXR_OK) goto done;
  if(form_name_is(r,subtype,"Tx")) field->kind=EXR_PDF_FIELD_TEXT;
  else if(form_name_is(r,subtype,"Ch")) field->kind=EXR_PDF_FIELD_CHOICE;
  else if(form_name_is(r,subtype,"Sig")) field->kind=EXR_PDF_FIELD_SIGNATURE;
  else if(form_name_is(r,subtype,"Btn")) field->kind=(flags&(1u<<16)) ? EXR_PDF_FIELD_PUSHBUTTON : (flags&(1u<<15)) ? EXR_PDF_FIELD_RADIO : EXR_PDF_FIELD_CHECKBOX;
  else if(subtype!=EXR_PDF_NONE && !form_kind(r,subtype,EXR_PDF_NAME)) { status=exr_fail(r->error,EXR_FORMAT,"PDF field FT is not a name"); goto done; }
  if(field->kind==EXR_PDF_FIELD_UNKNOWN || field->kind==EXR_PDF_FIELD_SIGNATURE || field->kind==EXR_PDF_FIELD_PUSHBUTTON) field->issues|=EXR_PDF_FORM_UNSUPPORTED;
  else {
    int button=field->kind==EXR_PDF_FIELD_CHECKBOX || field->kind==EXR_PDF_FIELD_RADIO;
    status=form_values(r,local[2],button,field->kind==EXR_PDF_FIELD_CHOICE,&field->values,&field->value_count);
    if(status==EXR_OK) status=form_values(r,local[3],button,field->kind==EXR_PDF_FIELD_CHOICE,&field->default_values,&field->default_value_count);
    if(status!=EXR_OK) goto done;
    if(field->kind==EXR_PDF_FIELD_CHOICE) { status=form_options_read(r,local[7],field); if(status!=EXR_OK) goto done; }
  }
  status=form_get(r,id,"A",&action); if(status!=EXR_OK) goto done; if(action!=EXR_PDF_NONE) field->issues|=EXR_PDF_FORM_ACTIONS;
  status=form_get(r,id,"AA",&action); if(status!=EXR_OK) goto done; if(action!=EXR_PDF_NONE) field->issues|=EXR_PDF_FORM_ACTIONS;
  status=form_get(r,id,"Subtype",&subtype); if(status!=EXR_OK) goto done;
  if(form_name_is(r,subtype,"Widget")) { status=form_widget(r,index,raw,id); if(status!=EXR_OK) goto done; }
  at=kids==EXR_PDF_NONE ? EXR_PDF_NONE : exr_pdf_value_at(r->file,kids)->first;
  while(at!=EXR_PDF_NONE) {
    uint32_t widget,next=exr_pdf_value_at(r->file,at)->next;
    if(depth==r->options.max_depth || ++r->nodes>32768) { status=exr_fail(r->error,EXR_LIMIT,"PDF widget tree budget exceeded"); goto done; }
    status=form_resolve(r,at,&widget); if(status!=EXR_OK) goto done;
    if(r->seen[widget]) { status=exr_fail(r->error,EXR_FORMAT,"PDF widget is a cycle or shared child"); goto done; } r->seen[widget]=1;
    status=form_get(r,widget,"Parent",&parent_id); if(status!=EXR_OK) goto done;
    if(parent_id!=id) { status=exr_fail(r->error,EXR_FORMAT,"PDF widget Parent disagrees with field tree"); goto done; }
    status=form_widget(r,index,at,widget); if(status!=EXR_OK) goto done; at=next;
  }
done:
  free(partial); free(name); return status;
}
exr_pdf_form_options exr_pdf_form_defaults(void) {
  exr_pdf_form_options o={0}; o.struct_size=sizeof(o); o.max_fields=4096; o.max_widgets=16384; o.max_depth=64; o.max_text_bytes=8*1024*1024; return o;
}
static exr_status form_scan(form_reader *r) {
  exr_pdf_page_info *pages=NULL; size_t count=0,i,annotations=0; uint32_t fields,at,value,inherited[8]; exr_status status;
  r->fields=calloc(r->options.max_fields,sizeof(*r->fields)); r->entries=calloc(r->options.max_fields,sizeof(*r->entries));
  r->seen=calloc(EXR_PDF_MAX_VALUES,1); r->pages=malloc(EXR_PDF_MAX_VALUES*sizeof(*r->pages));
  if(!r->fields || !r->entries || !r->seen || !r->pages) return exr_fail(r->error,EXR_MEMORY,"PDF form snapshot allocation failed");
  memset(r->pages,255,EXR_PDF_MAX_VALUES*sizeof(*r->pages));
  status=exr_pdf_pages(r->file,&pages,&count,r->error); if(status!=EXR_OK) goto done;
  for(i=0;i<count;i++) {
    status=form_resolve(r,pages[i].annotations,&value); if(status!=EXR_OK) goto done;
    if(value==EXR_PDF_NONE || form_kind(r,value,EXR_PDF_NULL)) continue;
    if(!form_kind(r,value,EXR_PDF_ARRAY)) { status=exr_fail(r->error,EXR_FORMAT,"PDF page Annots is not an array"); goto done; }
    at=exr_pdf_value_at(r->file,value)->first;
    while(at!=EXR_PDF_NONE) {
      uint32_t next=exr_pdf_value_at(r->file,at)->next,id;
      if(++annotations>65536) { status=exr_fail(r->error,EXR_LIMIT,"PDF form annotation budget exceeded"); goto done; }
      status=form_resolve(r,at,&id); if(status!=EXR_OK) goto done;
      if(id!=EXR_PDF_NONE) { if(r->pages[id]!=UINT32_MAX) { status=exr_fail(r->error,EXR_FORMAT,"PDF annotation appears on multiple pages"); goto done; } r->pages[id]=(uint32_t)i; } at=next;
    }
  }
  status=form_get(r,exr_pdf_root(r->file),"AcroForm",&r->acroform); if(status!=EXR_OK) goto done;
  if(r->acroform==EXR_PDF_NONE || form_kind(r,r->acroform,EXR_PDF_NULL)) goto done;
  if(!form_kind(r,r->acroform,EXR_PDF_DICT)) { status=exr_fail(r->error,EXR_FORMAT,"PDF AcroForm is not a dictionary"); goto done; }
  status=form_get(r,r->acroform,"XFA",&value); if(status!=EXR_OK) goto done; if(value!=EXR_PDF_NONE) r->issues|=EXR_PDF_FORM_XFA;
  status=form_get(r,r->acroform,"Fields",&fields); if(status!=EXR_OK) goto done;
  if(!form_kind(r,fields,EXR_PDF_ARRAY)) { status=exr_fail(r->error,EXR_FORMAT,"PDF AcroForm Fields is not an array"); goto done; }
  for(i=0;i<8;i++) inherited[i]=EXR_PDF_NONE;
  inherited[4]=exr_pdf_get(r->file,r->acroform,"DA"); inherited[5]=exr_pdf_get(r->file,r->acroform,"Q");
  at=exr_pdf_value_at(r->file,fields)->first;
  while(at!=EXR_PDF_NONE) { uint32_t next=exr_pdf_value_at(r->file,at)->next; status=form_walk(r,at,EXR_PDF_NONE,"",inherited,1,0); if(status!=EXR_OK) goto done; at=next; }
done:
  free(pages); return status;
}
exr_status exr_pdf_form_read(const void *data,size_t size,const exr_pdf_form_options *options,
  exr_pdf_form_field **out,size_t *count,exr_error *e) {
  form_reader r={0}; exr_status status; size_t i; r.options=exr_pdf_form_defaults(); r.error=e;
  if(out) *out=NULL;
  if(count) *count=0;
  if(!out || !count) return exr_fail(e,EXR_ARGUMENT,"Missing PDF form outputs");
  if(options) {
    if(options->struct_size<sizeof(*options) || options->struct_size>4096) return exr_fail(e,EXR_ARGUMENT,"Invalid PDF form options size");
    for(i=sizeof(*options);i<options->struct_size;i++) if(((const unsigned char *)options)[i]) return exr_fail(e,EXR_ARGUMENT,"Unsupported PDF form options extension");
    r.options=*options;
    if(!r.options.max_fields) r.options.max_fields=4096;
    if(!r.options.max_widgets) r.options.max_widgets=16384;
    if(!r.options.max_depth) r.options.max_depth=64;
    if(!r.options.max_text_bytes) r.options.max_text_bytes=8*1024*1024;
    if(r.options.max_fields>4096 || r.options.max_widgets>16384 || r.options.max_depth>64 || r.options.max_text_bytes>8*1024*1024)
      return exr_fail(e,EXR_ARGUMENT,"PDF form options exceed implementation caps");
  }
  status=exr_control_cancel(&r.options.control,e); if(status!=EXR_OK) return status;
  status=exr_pdf_open(data,size,&r.file,e); if(status!=EXR_OK) return status; exr_pdf_control(r.file,&r.options.control);
  status=form_scan(&r);
  if(status==EXR_OK) status=exr_control_poll(&r.options.control,EXR_STAGE_READ,size,size,e);
  if(status==EXR_OK && r.count) { *out=r.fields; *count=r.count; r.fields=NULL; }
  form_dispose(&r); exr_pdf_close(r.file); return status;
}
exr_pdf_form_write_options exr_pdf_form_write_defaults(void) {
  exr_pdf_form_write_options o={0}; o.struct_size=sizeof(o); return o;
}
static void form_pdf_name(pdf_writer *w,const char *s) {
  static const char hex[]="0123456789ABCDEF"; const unsigned char *p=(const unsigned char *)s;
  literal(w,"/");
  while(*p && w->status==EXR_OK) {
    if(*p<=32 || *p>=127 || strchr("()<>[]{}/%#",*p)) { char code[3]={'#',hex[*p>>4],hex[*p&15]}; add(w,code,3); }
    else add(w,(const char *)p,1);
    p++;
  }
}
static size_t form_option_index(const exr_pdf_form_field *f,const char *s) {
  size_t i; for(i=0;i<f->option_count;i++) if(!strcmp(f->options[i].value,s)) return i; return SIZE_MAX;
}
static exr_status form_change_valid(form_reader *r,size_t index,const exr_pdf_form_change *change) {
  exr_pdf_form_field *f=&r->fields[index]; size_t i,j; exr_status status; uint32_t q;
  if(f->issues || f->kind==EXR_PDF_FIELD_UNKNOWN) return exr_fail(r->error,EXR_UNSUPPORTED,"PDF field has unsupported type, direct objects, XFA or actions");
  if(f->flags&1) return exr_fail(r->error,EXR_ARGUMENT,"PDF field is read only");
  if(change->value_count>4096 || (change->value_count && !change->values)) return exr_fail(r->error,EXR_ARGUMENT,"Invalid PDF field value list");
  for(i=0;i<change->value_count;i++) {
    status=text_valid(change->values[i],0,1,r->error); if(status!=EXR_OK) return status;
    for(j=0;j<i;j++) if(!strcmp(change->values[i],change->values[j])) return exr_fail(r->error,EXR_ARGUMENT,"PDF field values contain a duplicate");
  }
  if((f->flags&2) && (!change->value_count || !*change->values[0] ||
      ((f->kind==EXR_PDF_FIELD_CHECKBOX || f->kind==EXR_PDF_FIELD_RADIO) && !strcmp(change->values[0],"Off"))))
    return exr_fail(r->error,EXR_ARGUMENT,"PDF required field cannot be empty");
  if(f->kind!=EXR_PDF_FIELD_CHOICE || !(f->flags&(1u<<21))) {
    if(change->value_count>1) return exr_fail(r->error,EXR_ARGUMENT,"PDF field permits one value");
  }
  status=form_uint(r,r->entries[index].inherit[5],&q); if(status!=EXR_OK) return status;
  if(q>2) return exr_fail(r->error,EXR_FORMAT,"PDF field justification is outside 0 to 2");
  if(f->kind==EXR_PDF_FIELD_TEXT) {
    size_t at=0,n=change->value_count ? strlen(change->values[0]) : 0,scalars=0; uint32_t cp;
    if(f->flags&((1u<<12)|(1u<<13)|(1u<<20)|(1u<<24)|(1u<<25))) return exr_fail(r->error,EXR_UNSUPPORTED,"PDF text field mode is not supported for appearance generation");
    while(at<n) { (void)exr_next(change->values[0],n,&at,&cp); scalars++; if(cp<32 || cp==127) return exr_fail(r->error,EXR_ARGUMENT,"PDF single line value contains controls"); }
    if(f->max_length && scalars>f->max_length) return exr_fail(r->error,EXR_ARGUMENT,"PDF field value exceeds MaxLen");
  } else if(f->kind==EXR_PDF_FIELD_CHOICE) {
    if((f->flags&(1u<<18)) || ((f->flags&(1u<<17)) && (f->flags&(1u<<21)))) return exr_fail(r->error,EXR_UNSUPPORTED,"PDF editable or multiselect combo is unsupported");
    for(i=0;i<f->option_count;i++) for(j=0;j<i;j++) if(!strcmp(f->options[i].value,f->options[j].value)) return exr_fail(r->error,EXR_FORMAT,"PDF choice export values are ambiguous");
    for(i=0;i<change->value_count;i++) if(form_option_index(f,change->values[i])==SIZE_MAX) return exr_fail(r->error,EXR_ARGUMENT,"PDF choice value is absent from Opt");
  } else {
    int found=!change->value_count || !strcmp(change->values[0],"Off");
    for(i=0;i<f->widget_count && !found;i++) if(!strcmp(f->widgets[i].on_state,change->values[0])) found=1;
    if(!found) return exr_fail(r->error,EXR_ARGUMENT,"PDF button value is absent from widget on states");
    if(f->kind==EXR_PDF_FIELD_RADIO && (f->flags&(1u<<14)) && (!change->value_count || !strcmp(change->values[0],"Off")))
      return exr_fail(r->error,EXR_ARGUMENT,"PDF radio group forbids turning all widgets off");
  }
  for(i=0;i<f->widget_count;i++) {
    uint32_t mk,rotation; status=form_get(r,r->entries[index].widgets[i],"MK",&mk); if(status==EXR_OK) status=form_get(r,mk,"R",&rotation);
    if(status==EXR_OK) status=form_uint(r,rotation,&q);
    if(status!=EXR_OK) return status;
    if(q) return exr_fail(r->error,EXR_UNSUPPORTED,"Rotated PDF form widget is unsupported for writing");
  }
  return EXR_OK;
}
static void form_outline(pdf_writer *p,const exr_path_segment *segments,size_t count) {
  size_t i; exr_path_point current={0};
  for(i=0;i<count && p->status==EXR_OK;i++) {
    const exr_path_segment *s=&segments[i]; size_t j,n=s->verb==EXR_PATH_CUBIC ? 3 : 1;
    if((i&255)==0) p->status=exr_control_cancel(p->control,p->error);
    if(s->verb==EXR_PATH_CLOSE) { literal(p,"h\n"); continue; }
    if(s->verb==EXR_PATH_QUAD) {
      double coordinates[6]={current.x+(s->points[0].x-current.x)*2/3,current.y+(s->points[0].y-current.y)*2/3,
        s->points[1].x+(s->points[0].x-s->points[1].x)*2/3,s->points[1].y+(s->points[0].y-s->points[1].y)*2/3,s->points[1].x,s->points[1].y};
      numbers(p,coordinates,6); literal(p," c\n"); current=s->points[1]; continue;
    }
    for(j=0;j<n;j++) { number(p,s->points[j].x); literal(p," "); number(p,s->points[j].y); literal(p," "); }
    literal(p,s->verb==EXR_PATH_MOVE ? "m\n" : s->verb==EXR_PATH_LINE ? "l\n" : "c\n"); current=s->points[n-1];
  }
  literal(p,"f\n");
}
static void form_text_appearance(pdf_writer *p,const char *text,double width,double height,uint32_t justification,
  const exr_pdf_form_write_options *options,size_t *work) {
  double size=fmin(12,height*.65),advance=0,x=2,y=fmax(1,(height-size)*.5+size*.2); size_t i,n=strlen(text);
  if(p->status!=EXR_OK) return;
  if(options->font) {
    exr_shaped_glyph *glyphs=NULL; size_t count=0; exr_shape_options shape=exr_shape_defaults();
    shape.font_size=100; shape.control=options->control;
    p->status=exr_shape(options->font,options->font_index,text,n,&shape,&glyphs,&count,p->error);
    for(i=0;i<count && p->status==EXR_OK;i++) {
      if(!glyphs[i].glyph) p->status=exr_fail(p->error,EXR_UNSUPPORTED,"PDF form appearance font lacks a glyph");
      advance+=glyphs[i].advance_x*10;
    }
    if(advance>0) size=fmin(size,fmax(.01,(width-4)*1000/advance));
    if(justification==1) x=(width-advance*size/1000)*.5;
    if(justification==2) x=width-2-advance*size/1000;
    for(i=0;i<count && p->status==EXR_OK;i++) {
      exr_path_segment *segments=NULL; size_t segment_count=0;
      p->status=exr_font_glyph_outline(options->font,options->font_index,glyphs[i].glyph,&segments,&segment_count,p->control,p->error);
      if(segment_count>1048576-*work) p->status=exr_fail(p->error,EXR_LIMIT,"PDF form appearance outline budget exceeded");
      else *work+=segment_count;
      literal(p,"q "); number(p,size/1000); literal(p," 0 0 "); number(p,size/1000); literal(p," "); number(p,x+glyphs[i].offset_x*size/100);
      literal(p," "); number(p,y+glyphs[i].offset_y*size/100); literal(p," cm\n"); form_outline(p,segments,segment_count); literal(p,"Q\n");
      free(segments); x+=glyphs[i].advance_x*size/100;
    }
    free(glyphs);
  } else {
    static const char hex[]="0123456789ABCDEF";
    for(i=0;i<n;i++) {
      double w;
      if((unsigned char)text[i]<32 || (unsigned char)text[i]>126) { p->status=exr_fail(p->error,EXR_UNSUPPORTED,"Unicode PDF form appearance requires a font"); return; }
      if(!exr_pdf_standard_width("Helvetica",exr_pdf_encoding_glyph("StandardEncoding",(unsigned char)text[i]),&w)) w=600;
      advance+=w;
    }
    if(advance>0) size=fmin(size,fmax(.01,(width-4)*1000/advance));
    if(justification==1) x=(width-advance*size/1000)*.5;
    if(justification==2) x=width-2-advance*size/1000;
    literal(p,"BT /Helv "); number(p,size); literal(p," Tf "); number(p,x); literal(p," "); number(p,y); literal(p," Td <");
    for(i=0;i<n;i++) { unsigned c=(unsigned char)text[i]; char code[2]={hex[c>>4],hex[c&15]}; add(p,code,2); }
    literal(p,"> Tj ET\n");
  }
}
static void form_appearance(pdf_writer *w,uint32_t object,const exr_pdf_form_field *f,size_t widget,const exr_pdf_form_change *change,
  int selected,uint32_t justification,const exr_pdf_form_write_options *options,size_t *work) {
  pdf_writer p={0}; double width=f->widgets[widget].bounds[2]-f->widgets[widget].bounds[0],height=f->widgets[widget].bounds[3]-f->widgets[widget].bounds[1];
  const char *text=change->value_count ? change->values[0] : ""; size_t i;
  p.status=EXR_OK; p.error=w->error; p.control=w->control;
  literal(&p,"q 1 1 1 rg 0 0 "); number(&p,width); literal(&p," "); number(&p,height); literal(&p," re f 0 0 0 rg 0 0 0 RG 1 w 0 0 ");
  number(&p,width); literal(&p," "); number(&p,height); literal(&p," re S 1 1 "); number(&p,fmax(0,width-2)); literal(&p," "); number(&p,fmax(0,height-2)); literal(&p," re W n\n");
  if(f->kind==EXR_PDF_FIELD_CHECKBOX || f->kind==EXR_PDF_FIELD_RADIO) {
    if(selected) { number(&p,width*.2); literal(&p," "); number(&p,height*.5); literal(&p," m "); number(&p,width*.42); literal(&p," "); number(&p,height*.2);
      literal(&p," l "); number(&p,width*.8); literal(&p," "); number(&p,height*.8); literal(&p," l 2 w S\n"); }
  } else if(f->kind==EXR_PDF_FIELD_CHOICE && !(f->flags&(1u<<17))) {
    for(i=0;i<change->value_count && p.status==EXR_OK;i++) {
      size_t option=form_option_index(f,change->values[i]); double row=fmin(16,height/fmax(1,(double)change->value_count));
      literal(&p,"q 1 0 0 1 0 "); number(&p,height-(i+1)*row); literal(&p," cm\n");
      form_text_appearance(&p,f->options[option].label,width,row,justification,options,work); literal(&p,"Q\n");
    }
  } else {
    if(f->kind==EXR_PDF_FIELD_CHOICE && change->value_count) text=f->options[form_option_index(f,text)].label;
    form_text_appearance(&p,text,width,height,justification,options,work);
  }
  literal(&p,"Q\n");
  if(p.status!=EXR_OK) w->status=p.status;
  begin_object(w,object,0); literal(w,"<< /Type /XObject /Subtype /Form /FormType 1 /BBox [0 0 "); number(w,width); literal(w," "); number(w,height);
  format(w,"] /Resources << /Font << /Helv << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> >> >> /Length %zu >>\nstream\n",p.bytes.size);
  add(w,p.bytes.data,p.bytes.size); literal(w,"endstream\nendobj\n"); free(p.bytes.data);
}
static void form_value_write(pdf_writer *w,const exr_pdf_form_field *f,const exr_pdf_form_change *c) {
  size_t i,j;
  literal(w," /V ");
  if(f->kind==EXR_PDF_FIELD_CHECKBOX || f->kind==EXR_PDF_FIELD_RADIO) form_pdf_name(w,c->value_count ? c->values[0] : "Off");
  else if(f->kind==EXR_PDF_FIELD_CHOICE && (f->flags&(1u<<21))) {
    literal(w,"[");
    for(i=0;i<f->option_count;i++) for(j=0;j<c->value_count;j++) if(!strcmp(f->options[i].value,c->values[j])) { string(w,c->values[j]); literal(w," "); }
    literal(w,"]");
  } else string(w,c->value_count ? c->values[0] : "");
  if(f->kind==EXR_PDF_FIELD_CHOICE) {
    literal(w," /I [");
    for(i=0;i<f->option_count;i++) for(j=0;j<c->value_count;j++) if(!strcmp(f->options[i].value,c->values[j])) format(w,"%zu ",i);
    literal(w,"]");
  }
}
static void form_widget_write(pdf_writer *w,form_reader *r,size_t field_index,size_t widget_index,
  uint32_t off,uint32_t on,const exr_pdf_form_change *change) {
  static const char *const skip[]={"AP","AS","V","I"},*const normal_skip[]={"N"};
  const exr_pdf_form_field *f=&r->fields[field_index]; uint32_t id=r->entries[field_index].widgets[widget_index],object,generation,ap;
  int merged=id==r->entries[field_index].id,button=f->kind==EXR_PDF_FIELD_CHECKBOX || f->kind==EXR_PDF_FIELD_RADIO;
  int selected=button && change->value_count && !strcmp(change->values[0],f->widgets[widget_index].on_state);
  if(w->status==EXR_OK) w->status=exr_pdf_object_identity(w->file,id,&object,&generation,w->error);
  if(w->status!=EXR_OK) return;
  begin_object(w,object,generation); dictionary(w,id,skip,merged ? 4 : 2);
  if(merged) form_value_write(w,f,change);
  if(w->status==EXR_OK) w->status=form_get(r,id,"AP",&ap);
  if(w->status!=EXR_OK) return;
  literal(w," /AP "); dictionary(w,ap,normal_skip,1); literal(w," /N ");
  if(button) {
    format(w,"<< /Off %" PRIu32 " 0 R ",off); form_pdf_name(w,f->widgets[widget_index].on_state); format(w," %" PRIu32 " 0 R >> >> /AS ",on);
    form_pdf_name(w,selected ? f->widgets[widget_index].on_state : "Off");
  } else format(w,"%" PRIu32 " 0 R >>",off);
  literal(w," >>\nendobj\n");
}
exr_status exr_pdf_form_write(const void *data,size_t size,const exr_pdf_form_change *changes,size_t count,
  const exr_pdf_form_write_options *options,void **out,size_t *out_size,exr_error *e) {
  pdf_writer w={0}; form_reader r={0}; exr_pdf_form_write_options config=exr_pdf_form_write_defaults(); exr_pdf_revision_info revision;
  size_t i,j,k,*indices=NULL,next=0,work=0; uint32_t object,generation,root,root_generation,form_raw; exr_status status;
  static const char *const value_skip[]={"V","I"},*const form_skip[]={"NeedAppearances"},*const catalog_skip[]={"AcroForm"};
  if(out) *out=NULL;
  if(out_size) *out_size=0;
  if(!out || !out_size) return exr_fail(e,EXR_ARGUMENT,"Missing written PDF outputs");
  if(options) {
    if(options->struct_size<sizeof(config) || options->struct_size>4096) return exr_fail(e,EXR_ARGUMENT,"Invalid PDF form write options size");
    for(i=sizeof(config);i<options->struct_size;i++) if(((const unsigned char *)options)[i]) return exr_fail(e,EXR_ARGUMENT,"Unsupported PDF form write options extension");
    config=*options;
  }
  if(count>4096 || (count && !changes) || (!config.font && config.font_index) || (config.font && config.font_index>=exr_font_count(config.font)))
    return exr_fail(e,EXR_ARGUMENT,"Invalid PDF form changes or font index");
  w.status=EXR_OK; w.input_size=size; w.error=e; w.control=&config.control; r.options=exr_pdf_form_defaults(); r.options.control=config.control; r.error=e;
  status=exr_control_poll(w.control,EXR_STAGE_READ,0,size,e); if(status!=EXR_OK) return status;
  status=exr_pdf_open(data,size,&w.file,e); if(status!=EXR_OK) return status; r.file=w.file; exr_pdf_control(w.file,w.control);
  status=form_scan(&r); if(status!=EXR_OK) goto done;
  if(!count) { status=output(&w,data,out,out_size); goto done; }
  status=permission(w.file,e); if(status!=EXR_OK) goto done;
  if(r.issues&EXR_PDF_FORM_XFA) { status=exr_fail(e,EXR_UNSUPPORTED,"XFA PDF form editing is unsupported"); goto done; }
  indices=malloc(count*sizeof(*indices)); if(!indices) { status=exr_fail(e,EXR_MEMORY,"PDF form change allocation failed"); goto done; }
  for(i=0;i<count;i++) {
    status=text_valid(changes[i].name,1,0,e); if(status!=EXR_OK) goto done;
    for(j=0;j<i;j++) if(!strcmp(changes[i].name,changes[j].name)) { status=exr_fail(e,EXR_ARGUMENT,"PDF field changed more than once"); goto done; }
    for(j=0;j<r.count;j++) if(!strcmp(changes[i].name,r.fields[j].name)) break;
    if(j==r.count) { status=exr_fail(e,EXR_ARGUMENT,"PDF form field was not found"); goto done; }
    indices[i]=j; status=form_change_valid(&r,j,&changes[i]); if(status!=EXR_OK) goto done;
  }
  exr_pdf_revision(w.file,&revision); next=revision.size;
  status=exr_pdf_object_identity(w.file,exr_pdf_root(w.file),&root,&root_generation,e); if(status!=EXR_OK) goto done;
  literal(&w,"\n");
  for(i=0;i<count && w.status==EXR_OK;i++) {
    size_t index=indices[i]; exr_pdf_form_field *f=&r.fields[index]; form_entry *entry=&r.entries[index]; uint32_t justification;
    status=form_uint(&r,entry->inherit[5],&justification); if(status!=EXR_OK) goto done;
    for(j=0;j<f->widget_count && w.status==EXR_OK;j++) {
      int button=f->kind==EXR_PDF_FIELD_CHECKBOX || f->kind==EXR_PDF_FIELD_RADIO; uint32_t off=(uint32_t)next++,on=button ? (uint32_t)next++ : 0;
      if(next>EXR_PDF_MAX_VALUES) { status=exr_fail(e,EXR_LIMIT,"PDF form appearance object budget exceeded"); goto done; }
      form_appearance(&w,off,f,j,&changes[i],0,justification,&config,&work);
      if(button) form_appearance(&w,on,f,j,&changes[i],1,justification,&config,&work);
      form_widget_write(&w,&r,index,j,off,on,&changes[i]);
    }
    if(w.status!=EXR_OK) { status=w.status; goto done; }
    for(k=0;k<entry->widget_count;k++) if(entry->widgets[k]==entry->id) break;
    if(k==entry->widget_count) {
      status=exr_pdf_object_identity(w.file,entry->id,&object,&generation,e); if(status!=EXR_OK) goto done;
      begin_object(&w,object,generation); dictionary(&w,entry->id,value_skip,2); form_value_write(&w,f,&changes[i]); literal(&w," >>\nendobj\n");
    }
  }
  if(w.status!=EXR_OK) { status=w.status; goto done; }
  form_raw=exr_pdf_get(w.file,exr_pdf_root(w.file),"AcroForm");
  if(form_kind(&r,form_raw,EXR_PDF_REF)) {
    status=exr_pdf_object_identity(w.file,form_raw,&object,&generation,e); if(status!=EXR_OK) goto done;
    begin_object(&w,object,generation); dictionary(&w,r.acroform,form_skip,1); literal(&w," /NeedAppearances false >>\nendobj\n");
  } else {
    begin_object(&w,root,root_generation); dictionary(&w,exr_pdf_root(w.file),catalog_skip,1); literal(&w," /AcroForm ");
    dictionary(&w,r.acroform,form_skip,1); literal(&w," /NeedAppearances false >> >>\nendobj\n");
  }
  finish(&w,&revision,next,EXR_PDF_NONE,EXR_PDF_NONE); status=output(&w,data,out,out_size);
done:
  free(indices); free(w.objects); free(w.bytes.data); form_dispose(&r); exr_pdf_close(w.file); return status;
}
