/* SPDX-License-Identifier: GPL-3.0-only */
/* Mesh shadings, types 4 and 5 (PDF Reference 4.6.3). The mesh is rasterised into
   a bitmap covering its bounding box and emitted like axial and radial shadings,
   so the drawing sink needs no mesh interface. */
#include "pdf_internal.h"
#include "pdf_function_internal.h"

#define MESH_MAX_VERTICES 65536
#define MESH_MAX_SIDE 1024

typedef struct { double x,y,rgb[3]; } mesh_vertex;
typedef struct {
  const unsigned char *data;
  size_t size,bit;
  unsigned coordinate,component,flag,components;
  const double *decode;
  int truncated;
} mesh_stream;

static unsigned long mesh_bits(mesh_stream *s,unsigned bits) {
  unsigned long value=0;unsigned k;
  if(!bits || bits>32 || s->bit+bits>s->size*8) { s->truncated=1; return 0; }
  for(k=0;k<bits;k++,s->bit++) value=(value<<1)|((s->data[s->bit>>3]>>(7-(s->bit&7)))&1);
  return value;
}
static double mesh_map(unsigned long raw,unsigned bits,double lo,double hi) {
  double maximum=bits>=32 ? 4294967295.0 : (double)((1UL<<bits)-1);
  return maximum<=0 ? lo : lo+((double)raw/maximum)*(hi-lo);
}
static int mesh_read_vertex(mesh_stream *s,mesh_vertex *v,exr_pdf_function *function,
                       exr_pdf_colorspace *space,unsigned intent,exr_error *e) {
  double comp[4]={0},rgb[4]={0};unsigned i;
  v->x=mesh_map(mesh_bits(s,s->coordinate),s->coordinate,s->decode[0],s->decode[1]);
  v->y=mesh_map(mesh_bits(s,s->coordinate),s->coordinate,s->decode[2],s->decode[3]);
  if(function) {
    double t=mesh_map(mesh_bits(s,s->component),s->component,s->decode[4],s->decode[5]);
    if(exr_pdf_function_eval(function,t,rgb,e)!=EXR_OK) return 0;
    v->rgb[0]=rgb[0];v->rgb[1]=rgb[1];v->rgb[2]=rgb[2];
  } else {
    for(i=0;i<s->components;i++)
      comp[i]=mesh_map(mesh_bits(s,s->component),s->component,s->decode[4+i*2],s->decode[5+i*2]);
    if(exr_pdf_colorspace_rgb_intent(space,comp,v->rgb,intent,e)!=EXR_OK) return 0;
  }
  return !s->truncated;
}
static void mesh_triangle(exr_bitmap *bitmap,double left,double top,double scale,
                          const mesh_vertex *a,const mesh_vertex *b,const mesh_vertex *c) {
  double ax=(a->x-left)*scale,ay=(a->y-top)*scale;
  double bx=(b->x-left)*scale,by=(b->y-top)*scale;
  double cx=(c->x-left)*scale,cy=(c->y-top)*scale;
  double area=(bx-ax)*(cy-ay)-(by-ay)*(cx-ax);
  int x0,x1,y0,y1,x,y;
  if(fabs(area)<1e-9) return;
  x0=(int)floor(fmin(ax,fmin(bx,cx)));x1=(int)ceil(fmax(ax,fmax(bx,cx)));
  y0=(int)floor(fmin(ay,fmin(by,cy)));y1=(int)ceil(fmax(ay,fmax(by,cy)));
  if(x0<0) x0=0;
  if(y0<0) y0=0;
  if(x1>(int)bitmap->width) x1=(int)bitmap->width;
  if(y1>(int)bitmap->height) y1=(int)bitmap->height;
  for(y=y0;y<y1;y++) for(x=x0;x<x1;x++) {
    double px=x+0.5,py=y+0.5;
    double w0=((bx-px)*(cy-py)-(by-py)*(cx-px))/area;
    double w1=((cx-px)*(ay-py)-(cy-py)*(ax-px))/area;
    double w2=1.0-w0-w1;
    unsigned char *p;
    if(w0<0||w1<0||w2<0) continue;
    p=bitmap->pixels+(size_t)y*bitmap->stride+(size_t)x*4;
    p[0]=(unsigned char)fmin(255,fmax(0,w0*a->rgb[0]*255+w1*b->rgb[0]*255+w2*c->rgb[0]*255));
    p[1]=(unsigned char)fmin(255,fmax(0,w0*a->rgb[1]*255+w1*b->rgb[1]*255+w2*c->rgb[1]*255));
    p[2]=(unsigned char)fmin(255,fmax(0,w0*a->rgb[2]*255+w1*b->rgb[2]*255+w2*c->rgb[2]*255));
    p[3]=255;
  }
}
static int mesh_number(exr_pdf_file *file,uint32_t id,double *out) {
  uint32_t resolved;const exr_pdf_value *v;
  if(exr_pdf_resolve(file,id,&resolved,NULL)!=EXR_OK) return 0;
  v=exr_pdf_value_at(file,resolved);
  if(!v || (v->kind!=EXR_PDF_INT && v->kind!=EXR_PDF_REAL)) return 0;
  *out=v->kind==EXR_PDF_INT ? (double)v->u.integer : v->u.number;
  return 1;
}
static int mesh_integer(exr_pdf_file *file,uint32_t dict,const char *key,unsigned fallback,unsigned *out) {
  uint32_t id=exr_pdf_get(file,dict,key);double value;
  if(id==EXR_PDF_NONE) { *out=fallback; return 1; }
  if(!mesh_number(file,id,&value) || value<0 || value>4096) return 0;
  *out=(unsigned)value;
  return 1;
}
static void mesh_matrix(const double ctm[6],const double local[6],double out[6]) {
  out[0]=ctm[0]*local[0]+ctm[2]*local[1];
  out[1]=ctm[1]*local[0]+ctm[3]*local[1];
  out[2]=ctm[0]*local[2]+ctm[2]*local[3];
  out[3]=ctm[1]*local[2]+ctm[3]*local[3];
  out[4]=ctm[0]*local[4]+ctm[2]*local[5]+ctm[4];
  out[5]=ctm[1]*local[4]+ctm[3]*local[5]+ctm[5];
}
exr_status exr_pdf_shading_mesh(exr_pdf_file *file,uint32_t value,int type,
                                const double ctm[6],unsigned intent,
                                exr_pdf_shading_fn emit,void *context,
                                const exr_control *control,exr_error *error) {
  uint32_t id,stream_id,space_id,function_id=EXR_PDF_NONE;
  const exr_pdf_value *array;uint32_t at;
  const unsigned char *data=NULL;size_t size=0;
  double decode[10]={0,1,0,1,0,1,0,1,0,1};
  double left,top,scale;unsigned side_x,side_y,vertices_per_row=0;
  exr_pdf_colorspace *space=NULL;exr_pdf_function *function=NULL;
  mesh_vertex *points=NULL;size_t count=0;
  mesh_stream stream;exr_bitmap bitmap={0};exr_status status=EXR_OK;double local[6],matrix[6];
  (void)control;
  if(type!=4 && type!=5) return exr_fail(error,EXR_UNSUPPORTED,"Only mesh shading types 4 and 5 are implemented");
  memset(&stream,0,sizeof(stream));
  if(!mesh_integer(file,value,"BitsPerCoordinate",0,&stream.coordinate) || !stream.coordinate)
    return exr_fail(error,EXR_FORMAT,"Invalid PDF mesh shading bits");
  if(!mesh_integer(file,value,"BitsPerComponent",8,&stream.component))
    return exr_fail(error,EXR_FORMAT,"Invalid PDF mesh shading bits");
  stream.flag=0;
  if(type==4) {
    if(!mesh_integer(file,value,"BitsPerFlag",8,&stream.flag) || !stream.flag)
      return exr_fail(error,EXR_FORMAT,"Invalid PDF mesh shading bits");
  } else if(!mesh_integer(file,value,"VerticesPerRow",0,&vertices_per_row) || !vertices_per_row)
    return exr_fail(error,EXR_FORMAT,"Invalid PDF mesh shading lattice");
  if(exr_pdf_resolve(file,exr_pdf_get(file,value,"ColorSpace"),&space_id,error)!=EXR_OK) return error->code;
  if(exr_pdf_get(file,value,"Function")!=EXR_PDF_NONE) {
    if(exr_pdf_resolve(file,exr_pdf_get(file,value,"Function"),&function_id,error)!=EXR_OK) return error->code;
  }
  status=exr_pdf_colorspace_open(file,space_id,file,exr_pdf_get(file,value,"Resources"),&(exr_control){0},&space,error);
  if(status!=EXR_OK) return status;
  stream.components=exr_pdf_colorspace_components(space);
  if(stream.components<1 || stream.components>4) { exr_pdf_colorspace_free(space); return exr_fail(error,EXR_UNSUPPORTED,"Unsupported PDF mesh shading colour space"); }
  if(function_id!=EXR_PDF_NONE) {
    status=exr_pdf_function_open(file,function_id,stream.components,&(exr_control){0},&function,error);
    if(status!=EXR_OK) { exr_pdf_colorspace_free(space); return status; }
  }
  /* Decode holds x/y ranges plus one pair per colour component (or a single
     parametric pair when a Function is present). */
  if(exr_pdf_resolve(file,exr_pdf_get(file,value,"Decode"),&id,error)!=EXR_OK) { status=error->code; goto done; }
  array=exr_pdf_value_at(file,id);
  if(!array || array->kind!=EXR_PDF_ARRAY) { status=exr_fail(error,EXR_FORMAT,"Invalid PDF mesh shading decode array"); goto done; }
  { unsigned wanted=function ? 4u : 4u+stream.components*2u;unsigned k;at=array->first;
    if(wanted>5) wanted=5;
    for(k=0;k<wanted;k++) {
      uint32_t item;
      if(at==EXR_PDF_NONE || exr_pdf_resolve(file,at,&item,error)!=EXR_OK || !mesh_number(file,item,&decode[k])) {
        status=exr_fail(error,EXR_FORMAT,"Invalid PDF mesh shading decode array"); goto done;
      }
      at=exr_pdf_value_at(file,at)->next;
    }
  }
  if(exr_pdf_resolve(file,exr_pdf_get(file,value,"Stream"),&stream_id,error)!=EXR_OK) { status=error->code; goto done; }
  status=exr_pdf_stream_data(file,value,&data,&size,error);
  if(status!=EXR_OK) goto done;
  stream.data=data;stream.size=size;stream.decode=decode;
  /* First pass: bounding box (and vertex count for the lattice). */
  {
    double minx=0,miny=0,maxx=0,maxy=0;int first_point=1;
    for(;;) {
      mesh_vertex v;unsigned flag=0;
      if(stream.bit>=size*8) break;
      if(type==4) flag=(unsigned)(mesh_bits(&stream,stream.flag)&3u);
      if(!mesh_read_vertex(&stream,&v,function,space,intent,error)) { status=exr_fail(error,EXR_FORMAT,"Truncated PDF mesh shading stream"); goto done; }
      if(first_point) { minx=maxx=v.x;miny=maxy=v.y;first_point=0; }
      else { minx=fmin(minx,v.x);maxx=fmax(maxx,v.x);miny=fmin(miny,v.y);maxy=fmax(maxy,v.y); }
      count++;
      if(type==4 && flag==0) {
        mesh_vertex vb,vc;
        (void)mesh_bits(&stream,stream.flag);
        if(!mesh_read_vertex(&stream,&vb,function,space,intent,error)) { status=exr_fail(error,EXR_FORMAT,"Truncated PDF mesh shading stream"); goto done; }
        (void)mesh_bits(&stream,stream.flag);
        if(!mesh_read_vertex(&stream,&vc,function,space,intent,error)) { status=exr_fail(error,EXR_FORMAT,"Truncated PDF mesh shading stream"); goto done; }
        minx=fmin(minx,fmin(vb.x,vc.x));maxx=fmax(maxx,fmax(vb.x,vc.x));
        miny=fmin(miny,fmin(vb.y,vc.y));maxy=fmax(maxy,fmax(vb.y,vc.y));
        count+=2;
      }
      if(count>MESH_MAX_VERTICES) { status=exr_fail(error,EXR_LIMIT,"PDF mesh shading vertex limit exceeded"); goto done; }
    }
    if(!count) { status=exr_fail(error,EXR_FORMAT,"Empty PDF mesh shading stream"); goto done; }
    if(!(maxx>minx) || !(maxy>miny)) { status=exr_fail(error,EXR_FORMAT,"Degenerate PDF mesh shading"); goto done; }
    scale=1.0;
    { double span=maxx-minx>maxy-miny ? maxx-minx : maxy-miny; if(span>0) scale=MESH_MAX_SIDE/span; }
    if(scale<1e-3) scale=1e-3;
    side_x=(unsigned)fmax(1.0,ceil((maxx-minx)*scale));side_y=(unsigned)fmax(1.0,ceil((maxy-miny)*scale));
    if(side_x>MESH_MAX_SIDE) side_x=MESH_MAX_SIDE;
    if(side_y>MESH_MAX_SIDE) side_y=MESH_MAX_SIDE;
    bitmap.width=side_x;bitmap.height=side_y;bitmap.channels=4;bitmap.stride=side_x*4;
    bitmap.pixels=calloc((size_t)bitmap.stride*side_y,1);
    if(!bitmap.pixels) { status=exr_fail(error,EXR_MEMORY,"PDF mesh shading bitmap allocation failed"); goto done; }
    left=minx;top=miny;
    local[0]=maxx-minx;local[1]=0;local[2]=0;local[3]=maxy-miny;local[4]=left;local[5]=top;
    /* Second pass paints the mesh. */
    stream.bit=0;stream.truncated=0;
    if(type==4) {
      mesh_vertex a={0},b={0},c={0};int have_prev=0;
      for(;;) {
        mesh_vertex v;unsigned flag;
        if(stream.bit>=size*8) break;
        flag=(unsigned)(mesh_bits(&stream,stream.flag)&3u);
        if(!mesh_read_vertex(&stream,&v,function,space,intent,error)) break;
        if(flag==0) {
          mesh_vertex vb,vc;
          (void)mesh_bits(&stream,stream.flag);
          if(!mesh_read_vertex(&stream,&vb,function,space,intent,error)) break;
          (void)mesh_bits(&stream,stream.flag);
          if(!mesh_read_vertex(&stream,&vc,function,space,intent,error)) break;
          a=v;b=vb;c=vc;have_prev=1;
          mesh_triangle(&bitmap,left,top,scale,&a,&b,&c);
        } else if(have_prev && flag==1) {
          a=b;b=c;c=v;
          mesh_triangle(&bitmap,left,top,scale,&a,&b,&c);
        } else if(have_prev && flag==2) {
          mesh_vertex next=v;
          mesh_triangle(&bitmap,left,top,scale,&a,&c,&next);
          a=v; /* the shared edge becomes (c, v) */
          b=c; c=next;
        } else { status=exr_fail(error,EXR_FORMAT,"Invalid PDF mesh shading edge flag"); goto done; }
      }
    } else {
      size_t index=0;
      if(count>MESH_MAX_VERTICES) { status=exr_fail(error,EXR_LIMIT,"PDF mesh shading vertex limit exceeded"); goto done; }
      points=calloc(count,sizeof(*points));
      if(!points) { status=exr_fail(error,EXR_MEMORY,"PDF mesh shading allocation failed"); goto done; }
      while(index<count && stream.bit<size*8) {
        if(!mesh_read_vertex(&stream,&points[index],function,space,intent,error)) break;
        index++;
      }
      if(index<count) { status=exr_fail(error,EXR_FORMAT,"Truncated PDF mesh shading stream"); goto done; }
      if(count<=vertices_per_row) { status=exr_fail(error,EXR_FORMAT,"Invalid PDF mesh shading lattice"); goto done; }
      { size_t row,column,rows=count/vertices_per_row;
        for(row=0;row+1<rows;row++) for(column=0;column+1<vertices_per_row;column++) {
          size_t i0=row*vertices_per_row+column,i1=i0+1,i2=i0+vertices_per_row,i3=i2+1;
          mesh_triangle(&bitmap,left,top,scale,&points[i0],&points[i1],&points[i3]);
          mesh_triangle(&bitmap,left,top,scale,&points[i0],&points[i3],&points[i2]);
        }
      }
    }
    mesh_matrix(ctm,local,matrix);
    status=emit(context,&bitmap,matrix,NULL,error);
  }
done:
  free(bitmap.pixels);free(points);
  exr_pdf_function_free(function);exr_pdf_colorspace_free(space);
  return status;
}
