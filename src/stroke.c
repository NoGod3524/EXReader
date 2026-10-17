/* SPDX-License-Identifier: GPL-3.0-only */
#include "vector_internal.h"
typedef struct {
  exr_vector_polyline path; const double *matrix; const exr_vector_stroke_style *style;
  double radius,tolerance,stretch; size_t *work; const exr_control *control; exr_error *error; exr_status status;
} stroke_reader;
static int failed(stroke_reader *r,exr_status status,const char *message) { r->status=exr_fail(r->error,status,"%s",message); return 0; }
static int work(stroke_reader *r,size_t amount) {
  if(!exr_vector_work(r->work,amount)) return failed(r,EXR_LIMIT,"Vector stroke work budget exceeded");
  r->status=exr_control_cancel(r->control,r->error); return r->status==EXR_OK;
}
static int transform(stroke_reader *r,exr_vector_point p,exr_vector_point *out) {
  out->x=r->matrix[0]*p.x+r->matrix[2]*p.y+r->matrix[4]; out->y=r->matrix[1]*p.x+r->matrix[3]*p.y+r->matrix[5];
  return (isfinite(out->x) && isfinite(out->y) && fabs(out->x)<=1e7 && fabs(out->y)<=1e7) || failed(r,EXR_LIMIT,"Vector stroke coordinates exceed budget");
}
static int polygon(stroke_reader *r,const exr_vector_point *points,size_t count) {
  exr_vector_polyline *path=&r->path; double area=0; size_t i,start=path->point_count;
  if(count>1048576-path->point_count || path->contour_count==1048576) return failed(r,EXR_LIMIT,"Vector stroke vertex budget exceeded");
  if(!work(r,count*3+1)) return 0;
  if(!exr_grow((void **)&path->points,&path->point_capacity,start+count,sizeof(*path->points)) ||
     !exr_grow((void **)&path->contours,&path->contour_capacity,path->contour_count+1,sizeof(*path->contours))) return failed(r,EXR_MEMORY,"Vector stroke polygon allocation failed");
  for(i=0;i<count;i++) if(!transform(r,points[i],&path->points[start+i])) return 0;
  for(i=1;i+1<count;i++) {
    exr_vector_point a=path->points[start],b=path->points[start+i],c=path->points[start+i+1];
    area+=(b.x-a.x)*(c.y-a.y)-(b.y-a.y)*(c.x-a.x);
  }
  if(!area) return 1;
  if(area<0) for(i=0;i<count/2;i++) { exr_vector_point swap=path->points[start+i]; path->points[start+i]=path->points[start+count-1-i]; path->points[start+count-1-i]=swap; }
  path->contours[path->contour_count++]=(exr_vector_contour){start,count,1}; path->point_count+=count; return 1;
}
static int arc(stroke_reader *r,exr_vector_point center,double angle,double sweep,int full) {
  const double pi=3.14159265358979323846; double radius=r->radius*r->stretch,ratio,step,needed; size_t parts,count,i,offset; exr_vector_point *points; int ok;
  ratio=radius ? r->tolerance/radius : 1;
  step=ratio<1e-4 ? sqrt(8*ratio) : 2*acos(fmax(-1,1-ratio)); step=fmin(pi/2,step);
  if(!isfinite(step) || step<=0) return failed(r,EXR_LIMIT,"Vector stroke arc precision exceeds budget");
  needed=ceil(fabs(sweep)/step);
  if(!isfinite(needed) || needed>1048574 || needed+2>1048576-r->path.point_count) return failed(r,EXR_LIMIT,"Vector stroke arc vertex budget exceeded");
  parts=(size_t)needed; if(parts<2) parts=2;
  count=full ? parts : parts+2; offset=full ? 0 : 1;
  if(!work(r,count*20)) return 0;
  points=malloc(count*sizeof(*points)); if(!points) return failed(r,EXR_MEMORY,"Vector stroke arc allocation failed");
  if(!full) points[0]=center;
  for(i=0;i<count-offset;i++) {
    double t=angle+sweep*i/parts;
    if(!(i&255) && (r->status=exr_control_cancel(r->control,r->error))!=EXR_OK) { free(points); return 0; }
    points[i+offset]=(exr_vector_point){center.x+r->radius*cos(t),center.y+r->radius*sin(t)};
  }
  ok=polygon(r,points,count); free(points); return ok;
}
static int body(stroke_reader *r,exr_vector_point a,exr_vector_point b,exr_vector_point unit) {
  exr_vector_point p[4]; double x=-unit.y*r->radius,y=unit.x*r->radius;
  p[0]=(exr_vector_point){a.x+x,a.y+y}; p[1]=(exr_vector_point){b.x+x,b.y+y};
  p[2]=(exr_vector_point){b.x-x,b.y-y}; p[3]=(exr_vector_point){a.x-x,a.y-y}; return polygon(r,p,4);
}
static int join(stroke_reader *r,exr_vector_point center,exr_vector_point incoming,exr_vector_point outgoing) {
  double cross=incoming.x*outgoing.y-incoming.y*outgoing.x,dot=incoming.x*outgoing.x+incoming.y*outgoing.y,angle=atan2(cross,dot),side=angle>=0 ? -1 : 1;
  exr_vector_point a={center.x-side*incoming.y*r->radius,center.y+side*incoming.x*r->radius};
  exr_vector_point b={center.x-side*outgoing.y*r->radius,center.y+side*outgoing.x*r->radius},p[4];
  if(cross==0 && dot>0) return 1;
  if(r->style->join==EXR_VECTOR_ROUND_JOIN) return arc(r,center,atan2(a.y-center.y,a.x-center.x),angle,0);
  p[0]=center; p[1]=a; p[2]=b;
  if(r->style->join==EXR_VECTOR_MITER && cross!=0) {
    double t=((b.x-a.x)*outgoing.y-(b.y-a.y)*outgoing.x)/cross;
    exr_vector_point m={a.x+t*incoming.x,a.y+t*incoming.y};
    if(hypot(m.x-center.x,m.y-center.y)<=r->style->miter_limit*r->radius) { p[2]=m; p[3]=b; return polygon(r,p,4); }
  }
  return polygon(r,p,3);
}
static int cap(stroke_reader *r,exr_vector_point center,exr_vector_point direction,int start) {
  const double pi=3.14159265358979323846; exr_vector_point end;
  if(r->style->cap==EXR_VECTOR_BUTT) return 1;
  if(r->style->cap==EXR_VECTOR_ROUND_CAP) return arc(r,center,atan2(direction.x,-direction.y)+(start ? 0 : -pi),pi,0);
  end=(exr_vector_point){center.x+direction.x*r->radius*(start ? -1 : 1),center.y+direction.y*r->radius*(start ? -1 : 1)};
  return body(r,center,end,direction);
}
exr_status exr_vector_stroke(const exr_vector_polyline *path,const exr_vector_stroke_style *style,
                              const double matrix[6],double tolerance,exr_vector_polyline *out,
                              size_t *shared_work,const exr_control *control,exr_error *error) {
  const double identity[6]={1,0,0,1,0,0}; stroke_reader r={0}; size_t local_work=0,at=0,i,j;
  if(path==out) return exr_fail(error,EXR_ARGUMENT,"Vector stroke input and output must be distinct");
  if(out) memset(out,0,sizeof(*out));
  if(!path || !style || !out || (path->point_count && !path->points) || (path->contour_count && !path->contours) ||
     !isfinite(style->width) || style->width<0 || style->width>1e7 || !isfinite(style->miter_limit) || style->miter_limit<1 || style->miter_limit>1e7 ||
     (unsigned)style->cap>EXR_VECTOR_SQUARE || (unsigned)style->join>EXR_VECTOR_BEVEL || !isfinite(tolerance) || tolerance<=0 || tolerance>1e7)
    return exr_fail(error,EXR_ARGUMENT,"Invalid vector stroke input or style");
  if(path->point_count>1048576 || path->contour_count>1048576) return exr_fail(error,EXR_LIMIT,"Vector stroke source vertex budget exceeded");
  if(!matrix) matrix=identity;
  for(i=0;i<6;i++) if(!isfinite(matrix[i]) || fabs(matrix[i])>1e7) return exr_fail(error,EXR_ARGUMENT,"Invalid vector stroke transform");
  r.work=shared_work ? shared_work : &local_work; r.control=control; r.error=error; r.style=style;
  r.matrix=style->width ? matrix : identity; r.radius=style->width ? style->width/2 : .5; r.tolerance=tolerance;
  r.stretch=hypot(r.matrix[0],r.matrix[1])+hypot(r.matrix[2],r.matrix[3]);
  if(!work(&r,path->point_count+path->contour_count)) goto done;
  for(i=0;i<path->contour_count;i++) {
    const exr_vector_contour *c=&path->contours[i]; exr_vector_point first={0},previous={0},first_unit={0},last_unit={0}; int have_unit=0;
    if(c->start!=at || !c->count || c->count>path->point_count-at || c->closed>1) { failed(&r,EXR_ARGUMENT,"Invalid vector stroke contour span"); goto done; }
    for(j=0;j<c->count+(size_t)c->closed;j++) {
      exr_vector_point p=path->points[at+(j==c->count ? 0 : j)],unit; double length;
      if(!isfinite(p.x) || !isfinite(p.y) || fabs(p.x)>1e7 || fabs(p.y)>1e7) { failed(&r,EXR_ARGUMENT,"Invalid vector stroke source point"); goto done; }
      if(!style->width) {
        exr_vector_point native=p; p.x=matrix[0]*native.x+matrix[2]*native.y+matrix[4]; p.y=matrix[1]*native.x+matrix[3]*native.y+matrix[5];
        if(!isfinite(p.x) || !isfinite(p.y) || fabs(p.x)>1e7 || fabs(p.y)>1e7) { failed(&r,EXR_LIMIT,"Hairline coordinates exceed budget"); goto done; }
      }
      if(!j) { first=previous=p; continue; }
      length=hypot(p.x-previous.x,p.y-previous.y); if(!length) continue;
      unit=(exr_vector_point){(p.x-previous.x)/length,(p.y-previous.y)/length};
      if(have_unit && !join(&r,previous,last_unit,unit)) goto done;
      if(!body(&r,previous,p,unit)) goto done;
      if(!have_unit) first_unit=unit;
      have_unit=1; last_unit=unit; previous=p;
    }
    if(have_unit) {
      if(c->closed) { if(!join(&r,first,last_unit,first_unit)) goto done; }
      else if(!cap(&r,first,first_unit,1) || !cap(&r,previous,last_unit,0)) goto done;
    } else if(c->count>1 && style->cap==EXR_VECTOR_ROUND_CAP) { if(!arc(&r,first,0,6.2831853071795864769,1)) goto done; }
    at+=c->count;
  }
  if(at!=path->point_count) { failed(&r,EXR_ARGUMENT,"Vector stroke source has unclaimed points"); goto done; }
  r.status=exr_control_cancel(control,error); if(r.status!=EXR_OK) goto done;
  if(!r.path.contour_count) exr_vector_polyline_free(&r.path);
  *out=r.path; memset(&r.path,0,sizeof(r.path)); r.status=exr_fail(error,EXR_OK,"");
done:
  exr_vector_polyline_free(&r.path); return r.status;
}
