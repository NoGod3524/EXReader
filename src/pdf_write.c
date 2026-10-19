/* SPDX-License-Identifier: MIT */
#include "pdf_internal.h"
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
  size_t input_size; revision_object objects[3]; size_t count;
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
  if(w->status!=EXR_OK) return;
  if(w->count==3) { w->status=exr_fail(w->error,EXR_LIMIT,"PDF revision object limit exceeded"); return; }
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
  free(w.bytes.data); free(items); free(pages); exr_pdf_close(w.file); return status;
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
  free(packet.data); free(w.bytes.data); exr_pdf_close(w.file); return status;
}
