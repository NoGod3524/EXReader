/* SPDX-License-Identifier: MIT */
/* Mesh shadings, types 4 and 5 (PDF Reference 4.6.3). The mesh is rasterised into
   a bitmap covering its bounding box and emitted like axial and radial shadings,
   so the drawing sink needs no mesh interface. */
#include "pdf_internal.h"
#include "pdf_function_internal.h"
#include "vector_internal.h"

#define MESH_MAX_VERTICES 65536
#define MESH_MAX_SIDE 1024

typedef struct { double x,y,rgb[4]; } mesh_vertex;
typedef struct {
  const unsigned char *data;
  size_t size,bit;
  unsigned coordinate,component,flag,components;
  const double *decode;
  int truncated;
} mesh_stream;

typedef struct {
  exr_pdf_function *function;exr_pdf_colorspace *space;unsigned components,intent;
  size_t *work;const exr_control *control;exr_error *error;
} mesh_painter;

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
static int mesh_read_color(mesh_stream *s,double out[4],exr_pdf_function *function,
                           exr_pdf_colorspace *space,unsigned intent,exr_error *e) {
  unsigned i,n=function ? 1u : s->components;
  (void)space;(void)intent;(void)e;
  for(i=0;i<n;i++) out[i]=mesh_map(mesh_bits(s,s->component),s->component,s->decode[4+i*2],s->decode[5+i*2]);
  for(;i<4;i++) out[i]=0;
  return !s->truncated;
}

static int mesh_read_point(mesh_stream *s,mesh_vertex *v) {
  v->x=mesh_map(mesh_bits(s,s->coordinate),s->coordinate,s->decode[0],s->decode[1]);
  v->y=mesh_map(mesh_bits(s,s->coordinate),s->coordinate,s->decode[2],s->decode[3]);
  return !s->truncated;
}
static int mesh_read_vertex(mesh_stream *s,mesh_vertex *v,exr_pdf_function *function,
                       exr_pdf_colorspace *space,unsigned intent,exr_error *e) {
  if(!mesh_read_point(s,v)) return 0;
  { int ok=mesh_read_color(s,v->rgb,function,space,intent,e);s->bit=(s->bit+7)&~(size_t)7;return ok; }
}
static exr_status mesh_triangle(exr_bitmap *bitmap,double left,double top,double scale,
                          const mesh_vertex *a,const mesh_vertex *b,const mesh_vertex *c,mesh_painter *paint) {
  double ax=(a->x-left)*scale,ay=(a->y-top)*scale;
  double bx=(b->x-left)*scale,by=(b->y-top)*scale;
  double cx=(c->x-left)*scale,cy=(c->y-top)*scale;
  double area=(bx-ax)*(cy-ay)-(by-ay)*(cx-ax);
  int x0,x1,y0,y1,x,y;
  if(fabs(area)<1e-9) return EXR_OK;
  x0=(int)floor(fmin(ax,fmin(bx,cx)));x1=(int)ceil(fmax(ax,fmax(bx,cx)));
  y0=(int)floor(fmin(ay,fmin(by,cy)));y1=(int)ceil(fmax(ay,fmax(by,cy)));
  if(x0<0) x0=0;
  if(y0<0) y0=0;
  if(x1>(int)bitmap->width) x1=(int)bitmap->width;
  if(y1>(int)bitmap->height) y1=(int)bitmap->height;
  for(y=y0;y<y1;y++) {
    if(exr_control_cancel(paint->control,paint->error)!=EXR_OK) return EXR_CANCELLED;
    if(!exr_vector_work(paint->work,(size_t)(x1>x0 ? x1-x0 : 0)*(4+exr_pdf_colorspace_cost(paint->space)+exr_pdf_function_cost(paint->function))))
      return exr_fail(paint->error,EXR_LIMIT,"PDF mesh raster work budget exceeded");
    for(x=x0;x<x1;x++) {
    double px=x+0.5,py=y+0.5;
    double w0=((bx-px)*(cy-py)-(by-py)*(cx-px))/area;
    double w1=((cx-px)*(ay-py)-(cy-py)*(ax-px))/area;
    double w2=1.0-w0-w1;
    unsigned char *p;
    if(w0<0||w1<0||w2<0) continue;
    p=bitmap->pixels+(size_t)y*bitmap->stride+(size_t)x*4;
    { double native[4]={0},values[4]={0},rgb[3]={0};unsigned k;exr_status status;
      for(k=0;k<(paint->function ? 1u : paint->components);k++) native[k]=w0*a->rgb[k]+w1*b->rgb[k]+w2*c->rgb[k];
      if(paint->function) { status=exr_pdf_function_eval(paint->function,native[0],values,paint->error);if(status!=EXR_OK) return status; }
      else memcpy(values,native,sizeof(values));
      status=exr_pdf_colorspace_rgb_intent(paint->space,values,rgb,paint->intent,paint->error);if(status!=EXR_OK) return status;
      for(k=0;k<3;k++) p[k]=(unsigned char)fmin(255,fmax(0,floor(rgb[k]*255+.5)));
      p[3]=255;
    }
    }
  }
  return EXR_OK;
}

static int mesh_number(exr_pdf_file *file,uint32_t id,double *out) {
  uint32_t resolved;const exr_pdf_value *v;
  if(exr_pdf_resolve(file,id,&resolved,NULL)!=EXR_OK) return 0;
  v=exr_pdf_value_at(file,resolved);
  if(!v || (v->kind!=EXR_PDF_INT && v->kind!=EXR_PDF_REAL)) return 0;
  *out=v->kind==EXR_PDF_INT ? (double)v->u.integer : v->u.number;
  return isfinite(*out) && fabs(*out)<=1e7;
}
static int mesh_integer(exr_pdf_file *file,uint32_t dict,const char *key,unsigned fallback,unsigned *out) {
  uint32_t id=exr_pdf_get(file,dict,key);double value;
  if(id==EXR_PDF_NONE) { *out=fallback; return 1; }
  if(!mesh_number(file,id,&value) || value<0 || value>4096 || floor(value)!=value) return 0;
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
/* Types 6 and 7 (PDF 32000-1 8.7.4.5.7-8). A Coons patch carries 12 boundary
   control points; a tensor-product patch adds four interior points. Patches may
   share one edge with the previous patch (flag 1/2/3); corner colours are
   interpolated bilinearly. Patch records form a continuous bit stream. */
#define MESH_MAX_PATCHES 65536
#define MESH_MAX_TRIANGLES 2000000
#define MESH_PATCH_SUBDIV 64
typedef struct { mesh_vertex p[16],c[4]; } mesh_patch;

static int mesh_patch_read(mesh_stream *s,mesh_patch *cur,const mesh_patch *prev,int tensor,
                           exr_pdf_function *function,exr_pdf_colorspace *space,unsigned intent,
                           exr_error *e) {
  static const unsigned edge_points[4][4]={{0,1,2,3},{3,4,5,6},{6,7,8,9},{9,10,11,0}};
  static const unsigned edge_colors[4][2]={{0,1},{1,2},{2,3},{3,0}};
  unsigned flag,k;size_t cstart;
  if(s->bit>=s->size*8 || s->size*8-s->bit<8) return 0;
  flag=(unsigned)(mesh_bits(s,s->flag)&3u);
  if(s->truncated) return -1;
  memset(cur,0,sizeof(*cur));
  if(flag==0) {
    for(k=0;k<12;k++) if(!mesh_read_point(s,&cur->p[k])) return -1;
  } else {
    if(!prev) return -1;
    for(k=0;k<4;k++) cur->p[k]=prev->p[edge_points[flag][k]];
    cur->c[0]=prev->c[edge_colors[flag][0]];
    cur->c[1]=prev->c[edge_colors[flag][1]];
    for(k=4;k<12;k++) if(!mesh_read_point(s,&cur->p[k])) return -1;
  }
  if(tensor) for(k=12;k<16;k++) if(!mesh_read_point(s,&cur->p[k])) return -1;
  cstart=flag==0 ? 0 : 2;
  for(k=(unsigned)cstart;k<4;k++) {
    double rgb[4];
    if(!mesh_read_color(s,rgb,function,space,intent,e)) return -1;
    memcpy(cur->c[k].rgb,rgb,sizeof(rgb));
  }
  return 1;
}
static double mesh_cubic(double a,double b,double c,double d,double t) {
  double m=1-t;
  return m*m*m*a+3*t*m*m*b+3*t*t*m*c+t*t*t*d;
}
static void mesh_edge(const mesh_patch *p,unsigned a,unsigned b,unsigned c,unsigned d,double t,
                      double *x,double *y) {
  *x=mesh_cubic(p->p[a].x,p->p[b].x,p->p[c].x,p->p[d].x,t);
  *y=mesh_cubic(p->p[a].y,p->p[b].y,p->p[c].y,p->p[d].y,t);
}
static void mesh_patch_point(const mesh_patch *p,int tensor,double u,double v,double *x,double *y) {
  double c1x,c1y,c2x,c2y,d1x,d1y,d2x,d2y,sbx,sby;
  if(tensor) {
    mesh_vertex g[4][4];double bu[4],bv[4],px=0,py=0,mu=1-u,mv=1-v;int i,j;
    g[0][0]=p->p[0];g[0][1]=p->p[1];g[0][2]=p->p[2];g[0][3]=p->p[3];
    g[3][0]=p->p[9];g[3][1]=p->p[8];g[3][2]=p->p[7];g[3][3]=p->p[6];
    g[1][0]=p->p[11];g[2][0]=p->p[10];
    g[1][3]=p->p[4];g[2][3]=p->p[5];
    g[1][1]=p->p[12];g[1][2]=p->p[13];g[2][2]=p->p[14];g[2][1]=p->p[15];
    bu[0]=mu*mu*mu;bu[1]=3*u*mu*mu;bu[2]=3*u*u*mu;bu[3]=u*u*u;
    bv[0]=mv*mv*mv;bv[1]=3*v*mv*mv;bv[2]=3*v*v*mv;bv[3]=v*v*v;
    for(i=0;i<4;i++) for(j=0;j<4;j++) {
      double w=bu[i]*bv[j];
      px+=w*g[i][j].x;py+=w*g[i][j].y;
    }
    *x=px;*y=py;return;
  }
  /* Coons: S = (1-v)*bottom(u) + v*top(u) + (1-u)*left(v) + u*right(v) - bilinear */
  mesh_edge(p,0,11,10,9,u,&c1x,&c1y);
  mesh_edge(p,3,4,5,6,u,&c2x,&c2y);
  mesh_edge(p,0,1,2,3,v,&d1x,&d1y);
  mesh_edge(p,9,8,7,6,v,&d2x,&d2y);
  sbx=(1-u)*(1-v)*p->p[0].x+(1-u)*v*p->p[3].x+u*v*p->p[6].x+u*(1-v)*p->p[9].x;
  sby=(1-u)*(1-v)*p->p[0].y+(1-u)*v*p->p[3].y+u*v*p->p[6].y+u*(1-v)*p->p[9].y;
  *x=(1-v)*c1x+v*c2x+(1-u)*d1x+u*d2x-sbx;
  *y=(1-v)*c1y+v*c2y+(1-u)*d1y+u*d2y-sby;
}
static void mesh_patch_color(const mesh_patch *p,double u,double v,double rgb[4]) {
  double w0=(1-u)*(1-v),w1=(1-u)*v,w2=u*v,w3=u*(1-v);unsigned k;
  for(k=0;k<4;k++) rgb[k]=w0*p->c[0].rgb[k]+w1*p->c[1].rgb[k]+w2*p->c[2].rgb[k]+w3*p->c[3].rgb[k];
}
static exr_status mesh_patch_paint(exr_bitmap *bitmap,double left,double top,double scale,
                             const mesh_patch *p,int tensor,mesh_vertex *lattice,size_t *triangles,mesh_painter *paint) {
  double minx=p->p[0].x,maxx=p->p[0].x,miny=p->p[0].y,maxy=p->p[0].y,span;
  unsigned n,iu,iv,k,points=tensor ? 16u : 12u;
  for(k=1;k<points;k++) {
    if(p->p[k].x<minx) minx=p->p[k].x;
    if(p->p[k].x>maxx) maxx=p->p[k].x;
    if(p->p[k].y<miny) miny=p->p[k].y;
    if(p->p[k].y>maxy) maxy=p->p[k].y;
  }
  span=fmax(maxx-minx,maxy-miny)*scale;
  n=(unsigned)ceil(span/6.0);
  if(n<4) n=4;
  if(n>MESH_PATCH_SUBDIV) n=MESH_PATCH_SUBDIV;
  for(iv=0;iv<=n;iv++) for(iu=0;iu<=n;iu++) {
    mesh_vertex *v=&lattice[iv*(n+1)+iu];
    double u=(double)iu/n,vv=(double)iv/n,rgb[4];
    mesh_patch_point(p,tensor,u,vv,&v->x,&v->y);
    mesh_patch_color(p,u,vv,rgb);
    memcpy(v->rgb,rgb,sizeof(rgb));
  }
  for(iv=0;iv<n;iv++) for(iu=0;iu<n;iu++) {
    const mesh_vertex *a=&lattice[iv*(n+1)+iu],*b=a+1,*c=&lattice[(iv+1)*(n+1)+iu],*d=c+1;
    exr_status status;
    if(*triangles>MESH_MAX_TRIANGLES-2) return exr_fail(paint->error,EXR_LIMIT,"PDF mesh triangle limit exceeded");
    status=mesh_triangle(bitmap,left,top,scale,a,b,c,paint);if(status!=EXR_OK) return status;(*triangles)++;
    status=mesh_triangle(bitmap,left,top,scale,b,d,c,paint);if(status!=EXR_OK) return status;(*triangles)++;
  }
  return EXR_OK;
}
static exr_status mesh_shading_patches(const double ctm[6],int type,mesh_stream *s,
                                       exr_pdf_function *function,exr_pdf_colorspace *space,
                                       unsigned intent,exr_pdf_shading_fn emit,void *context,
                                       exr_error *error,mesh_painter *paint,const exr_pdf_paint_state *state) {
  mesh_patch cur,prev;int tensor=type==7,have_prev=0;
  size_t patches=0,triangles=0,k;double minx=0,miny=0,maxx=0,maxy=0;
  int first=1;exr_bitmap bitmap={0};mesh_vertex *lattice=NULL;
  double left,top,scale,local[6],matrix[6];exr_status status=EXR_OK;
  for(;;) {
    int read;
    if(exr_control_cancel(paint->control,error)!=EXR_OK) return EXR_CANCELLED;
    read=mesh_patch_read(s,&cur,have_prev?&prev:NULL,tensor,function,space,intent,error);
    unsigned count=tensor ? 16u : 12u;
    if(read==0) break;
    if(read<0) {
      if(error->code!=EXR_OK) return error->code;
      return exr_fail(error,EXR_FORMAT,"Truncated PDF mesh shading stream at patch %zu (bit %zu of %zu)",patches,s->bit,s->size*8);
    }
    for(k=0;k<count;k++) {
      if(first) { minx=maxx=cur.p[k].x;miny=maxy=cur.p[k].y;first=0; }
      else {
        if(cur.p[k].x<minx) minx=cur.p[k].x;
        if(cur.p[k].x>maxx) maxx=cur.p[k].x;
        if(cur.p[k].y<miny) miny=cur.p[k].y;
        if(cur.p[k].y>maxy) maxy=cur.p[k].y;
      }
    }
    prev=cur;have_prev=1;
    if(++patches>MESH_MAX_PATCHES) return exr_fail(error,EXR_LIMIT,"PDF mesh patch limit exceeded");
  }
  if(!patches) return exr_fail(error,EXR_FORMAT,"Empty PDF mesh shading stream");
  if(!(maxx>minx) || !(maxy>miny)) return exr_fail(error,EXR_FORMAT,"Degenerate PDF mesh shading");
  scale=1.0;
  { double span=maxx-minx>maxy-miny ? maxx-minx : maxy-miny; if(span>0) scale=MESH_MAX_SIDE/span; }
  if(scale<1e-3) scale=1e-3;
  {
    unsigned side_x=(unsigned)fmax(1.0,ceil((maxx-minx)*scale));
    unsigned side_y=(unsigned)fmax(1.0,ceil((maxy-miny)*scale));
    if(side_x>MESH_MAX_SIDE) side_x=MESH_MAX_SIDE;
    if(side_y>MESH_MAX_SIDE) side_y=MESH_MAX_SIDE;
    bitmap.width=side_x;bitmap.height=side_y;bitmap.channels=4;bitmap.stride=side_x*4;
    bitmap.pixels=calloc((size_t)bitmap.stride*side_y,1);
    if(!bitmap.pixels) return exr_fail(error,EXR_MEMORY,"PDF mesh shading bitmap allocation failed");
  }
  lattice=malloc(((size_t)MESH_PATCH_SUBDIV+1)*((size_t)MESH_PATCH_SUBDIV+1)*sizeof(*lattice));
  if(!lattice) { free(bitmap.pixels); return exr_fail(error,EXR_MEMORY,"PDF mesh shading allocation failed"); }
  left=minx;top=miny;
  local[0]=maxx-minx;local[1]=0;local[2]=0;local[3]=maxy-miny;local[4]=left;local[5]=top;
  s->bit=0;s->truncated=0;have_prev=0;
  for(;;) {
    int read=mesh_patch_read(s,&cur,have_prev?&prev:NULL,tensor,function,space,intent,error);
    if(read<=0) {
      if(read<0) status=error->code!=EXR_OK ? error->code : exr_fail(error,EXR_FORMAT,"Truncated PDF mesh shading stream");
      break;
    }
    status=mesh_patch_paint(&bitmap,left,top,scale,&cur,tensor,lattice,&triangles,paint);if(status!=EXR_OK) break;
    prev=cur;have_prev=1;
  }
  if(status==EXR_OK) {
    mesh_matrix(ctm,local,matrix);
    status=emit(context,&bitmap,matrix,state,error);
  }
  free(lattice);free(bitmap.pixels);
  return status;
}
exr_status exr_pdf_shading_mesh(exr_pdf_file *file,exr_pdf_file *resource_file,uint32_t resources,uint32_t value,int type,
                                const double ctm[6],const exr_pdf_paint_state *state,size_t *work,
                                exr_pdf_shading_fn emit,void *context,
                                const exr_control *control,exr_error *error) {
  uint32_t id,stream_id,space_id,function_id=EXR_PDF_NONE;
  const exr_pdf_value *array;uint32_t at;
  const unsigned char *data=NULL;size_t size=0;
  double decode[12]={0,1,0,1,0,1,0,1,0,1,0,1};
  double left,top,scale;unsigned side_x,side_y,vertices_per_row=0;
  exr_pdf_colorspace *space=NULL;exr_pdf_function *function=NULL;
  mesh_vertex *points=NULL;size_t count=0;
  mesh_stream stream;exr_bitmap bitmap={0};exr_status status=EXR_OK;double local[6],matrix[6];
  unsigned intent=state->intent;mesh_painter paint={0};
  if(exr_control_cancel(control,error)!=EXR_OK) return EXR_CANCELLED;
  if(type<4 || type>7) return exr_fail(error,EXR_UNSUPPORTED,"Only PDF mesh shading types 4 to 7 are implemented");
  memset(&stream,0,sizeof(stream));
  if(!mesh_integer(file,value,"BitsPerCoordinate",0,&stream.coordinate) || !stream.coordinate)
    return exr_fail(error,EXR_FORMAT,"Invalid PDF mesh shading bits");
  if(!mesh_integer(file,value,"BitsPerComponent",8,&stream.component))
    return exr_fail(error,EXR_FORMAT,"Invalid PDF mesh shading bits");
  stream.flag=0;
  if(type==4 || type==6 || type==7) {
    if(!mesh_integer(file,value,"BitsPerFlag",8,&stream.flag) || !stream.flag)
      return exr_fail(error,EXR_FORMAT,"Invalid PDF mesh shading bits");
  } else if(!mesh_integer(file,value,"VerticesPerRow",0,&vertices_per_row) || !vertices_per_row)
    return exr_fail(error,EXR_FORMAT,"Invalid PDF mesh shading lattice");
  if(!((stream.coordinate==1)||(stream.coordinate==2)||(stream.coordinate==4)||(stream.coordinate==8)||(stream.coordinate==12)||(stream.coordinate==16)||(stream.coordinate==24)||(stream.coordinate==32)) ||
     !((stream.component==1)||(stream.component==2)||(stream.component==4)||(stream.component==8)||(stream.component==12)||(stream.component==16)) ||
     (type!=5 && stream.flag!=2 && stream.flag!=4 && stream.flag!=8) || (type==5 && vertices_per_row<2))
    return exr_fail(error,EXR_FORMAT,"Invalid PDF mesh bit widths or row count");
  if(exr_pdf_resolve(file,exr_pdf_get(file,value,"ColorSpace"),&space_id,error)!=EXR_OK) return error->code;
  if(exr_pdf_get(file,value,"Function")!=EXR_PDF_NONE) {
    if(exr_pdf_resolve(file,exr_pdf_get(file,value,"Function"),&function_id,error)!=EXR_OK) return error->code;
  }
  status=exr_pdf_colorspace_open(file,space_id,resource_file,resources,control,&space,error);
  if(status!=EXR_OK) return status;
  stream.components=exr_pdf_colorspace_components(space);
  if(stream.components<1 || stream.components>4) { exr_pdf_colorspace_free(space); return exr_fail(error,EXR_UNSUPPORTED,"Unsupported PDF mesh shading colour space"); }
  if(function_id!=EXR_PDF_NONE) {
    status=exr_pdf_function_open(file,function_id,stream.components,control,&function,error);
    if(status!=EXR_OK) { exr_pdf_colorspace_free(space); return status; }
  }
  /* Decode holds x/y ranges plus one pair per colour component (or a single
     parametric pair when a Function is present). */
  if(exr_pdf_resolve(file,exr_pdf_get(file,value,"Decode"),&id,error)!=EXR_OK) { status=error->code; goto done; }
  array=exr_pdf_value_at(file,id);
  if(!array || array->kind!=EXR_PDF_ARRAY) { status=exr_fail(error,EXR_FORMAT,"Invalid PDF mesh shading decode array"); goto done; }
  { unsigned wanted=function ? 6u : 4u+stream.components*2u;unsigned k;at=array->first;
    if(wanted>12) wanted=12;
    for(k=0;k<wanted;k++) {
      uint32_t item;
      if(at==EXR_PDF_NONE || exr_pdf_resolve(file,at,&item,error)!=EXR_OK || !mesh_number(file,item,&decode[k])) {
        status=exr_fail(error,EXR_FORMAT,"Invalid PDF mesh shading decode array"); goto done;
      }
      at=exr_pdf_value_at(file,at)->next;
    }
    if(at!=EXR_PDF_NONE) { status=exr_fail(error,EXR_FORMAT,"Unexpected extra PDF mesh Decode entries");goto done; }
  }
  if(exr_pdf_resolve(file,exr_pdf_get(file,value,"Stream"),&stream_id,error)!=EXR_OK) { status=error->code; goto done; }
  status=exr_pdf_stream_data(file,value,&data,&size,error);
  if(status!=EXR_OK) goto done;
  stream.data=data;stream.size=size;stream.decode=decode;
  paint=(mesh_painter){function,space,stream.components,intent,work,control,error};
  if(type>=6) {
    status=mesh_shading_patches(ctm,type,&stream,function,space,intent,emit,context,error,&paint,state);
    goto done;
  }
  /* First pass: bounding box (and vertex count for the lattice). */
  {
    double minx=0,miny=0,maxx=0,maxy=0;int first_point=1;
    for(;;) {
      mesh_vertex v;unsigned flag=0;
      if(exr_control_cancel(control,error)!=EXR_OK) { status=EXR_CANCELLED;goto done; }
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
          status=mesh_triangle(&bitmap,left,top,scale,&a,&b,&c,&paint);if(status!=EXR_OK) goto done;
        } else if(have_prev && flag==1) {
          a=b;b=c;c=v;
          status=mesh_triangle(&bitmap,left,top,scale,&a,&b,&c,&paint);if(status!=EXR_OK) goto done;
        } else if(have_prev && flag==2) {
          /* PDF reference 4.6.3: flag 2 continues from the edge (va, vc). */
          status=mesh_triangle(&bitmap,left,top,scale,&a,&c,&v,&paint);if(status!=EXR_OK) goto done;
          b=c; c=v; /* va stays at the shared corner */
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
      if(count%vertices_per_row || count<=vertices_per_row) { status=exr_fail(error,EXR_FORMAT,"Invalid PDF mesh shading lattice"); goto done; }
      { size_t row,column,rows=count/vertices_per_row;
        for(row=0;row+1<rows;row++) for(column=0;column+1<vertices_per_row;column++) {
          size_t i0=row*vertices_per_row+column,i1=i0+1,i2=i0+vertices_per_row,i3=i2+1;
          status=mesh_triangle(&bitmap,left,top,scale,&points[i0],&points[i1],&points[i2],&paint);if(status!=EXR_OK) goto done;
          status=mesh_triangle(&bitmap,left,top,scale,&points[i1],&points[i3],&points[i2],&paint);if(status!=EXR_OK) goto done;
        }
      }
    }
    mesh_matrix(ctm,local,matrix);
    status=emit(context,&bitmap,matrix,state,error);
  }
done:
  free(bitmap.pixels);free(points);
  exr_pdf_function_free(function);exr_pdf_colorspace_free(space);
  return status;
}
