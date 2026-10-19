/* SPDX-License-Identifier: MIT */
#include "vector_internal.h"
typedef struct {
  exr_vector_polyline path; size_t *work; const exr_control *control; exr_error *error; exr_status status;
} flatten_reader;
typedef struct { exr_vector_point p[4]; unsigned degree,depth; } curve_node;
static int fail(flatten_reader *r,exr_status code,const char *message) { r->status=exr_fail(r->error,code,"%s",message); return 0; }
static int step(flatten_reader *r) {
  if(!exr_vector_work(r->work,1)) return fail(r,EXR_LIMIT,"Vector flatten work budget exceeded");
  if(!(*r->work&255) && (r->status=exr_control_cancel(r->control,r->error))!=EXR_OK) return 0;
  return 1;
}
static int point(flatten_reader *r,exr_vector_point p) {
  exr_vector_polyline *path=&r->path;
  if(path->point_count==1048576) return fail(r,EXR_LIMIT,"Vector flattened point count exceeds one million");
  if(!exr_grow((void **)&path->points,&path->point_capacity,path->point_count+1,sizeof(*path->points))) return fail(r,EXR_MEMORY,"Vector point allocation failed");
  path->points[path->point_count++]=p; path->contours[path->contour_count-1].count++; return 1;
}
static int contour(flatten_reader *r,exr_vector_point p) {
  exr_vector_polyline *path=&r->path;
  if(path->contour_count==1048576) return fail(r,EXR_LIMIT,"Vector contour count exceeds one million");
  if(!exr_grow((void **)&path->contours,&path->contour_capacity,path->contour_count+1,sizeof(*path->contours))) return fail(r,EXR_MEMORY,"Vector contour allocation failed");
  path->contours[path->contour_count++]=(exr_vector_contour){path->point_count,0,0}; return point(r,p);
}
static int transformed(flatten_reader *r,exr_vector_point p,const double *matrix,exr_vector_point *out) {
  if(!isfinite(p.x) || !isfinite(p.y) || fabs(p.x)>1e7 || fabs(p.y)>1e7) return fail(r,EXR_ARGUMENT,"Invalid vector curve coordinates");
  out->x=matrix[0]*p.x+matrix[2]*p.y+matrix[4]; out->y=matrix[1]*p.x+matrix[3]*p.y+matrix[5];
  if(!isfinite(out->x) || !isfinite(out->y) || fabs(out->x)>1e7 || fabs(out->y)>1e7) return fail(r,EXR_LIMIT,"Transformed vector coordinates exceed budget");
  return 1;
}
static double distance_squared(exr_vector_point p,exr_vector_point a,exr_vector_point b) {
  double dx=b.x-a.x,dy=b.y-a.y,denominator=dx*dx+dy*dy,t=denominator ? ((p.x-a.x)*dx+(p.y-a.y)*dy)/denominator : 0;
  t=fmax(0,fmin(1,t)); dx=p.x-(a.x+t*dx); dy=p.y-(a.y+t*dy); return dx*dx+dy*dy;
}
static int curve(flatten_reader *r,const curve_node *first,double tolerance) {
  curve_node stack[64]; size_t count=1; stack[0]=*first;
  while(count) {
    curve_node node=stack[--count],left={0},right={0}; exr_vector_point points[4]; unsigned i,level; int flat=1;
    if(!step(r)) return 0;
    for(i=1;i<node.degree;i++) if(distance_squared(node.p[i],node.p[0],node.p[node.degree])>tolerance*tolerance) flat=0;
    if(flat) { if(!point(r,node.p[node.degree])) return 0; continue; }
    if(node.depth==32 || count+2>64) return fail(r,EXR_LIMIT,"Vector curve subdivision exceeds depth budget");
    left.degree=right.degree=node.degree; left.depth=right.depth=node.depth+1;
    memcpy(points,node.p,sizeof(points)); left.p[0]=points[0]; right.p[node.degree]=points[node.degree];
    for(level=1;level<=node.degree;level++) {
      for(i=0;i<=node.degree-level;i++) { points[i].x=(points[i].x+points[i+1].x)/2; points[i].y=(points[i].y+points[i+1].y)/2; }
      left.p[level]=points[0]; right.p[node.degree-level]=points[node.degree-level];
    }
    stack[count++]=right; stack[count++]=left;
  }
  return 1;
}
void exr_vector_polyline_free(exr_vector_polyline *path) {
  if(path) { free(path->points); free(path->contours); memset(path,0,sizeof(*path)); }
}
exr_status exr_vector_flatten(const exr_vector_segment *segments,size_t count,const double transform[6],
                               double tolerance,exr_vector_polyline *out,size_t *work,
                               const exr_control *control,exr_error *error) {
  const double identity[6]={1,0,0,1,0,0}; flatten_reader r={0}; size_t local_work=0,i;
  if(out) memset(out,0,sizeof(*out));
  if(!out || (count && !segments) || !isfinite(tolerance) || tolerance<=0 || tolerance>1e7) return exr_fail(error,EXR_ARGUMENT,"Invalid vector path input or tolerance");
  if(count>1048576) return exr_fail(error,EXR_LIMIT,"Vector path command budget exceeded");
  if(!transform) transform=identity;
  for(i=0;i<6;i++) if(!isfinite(transform[i]) || fabs(transform[i])>1e7) return exr_fail(error,EXR_ARGUMENT,"Invalid vector path transform");
  r.work=work ? work : &local_work;
  if(!exr_vector_work(r.work,0)) return exr_fail(error,EXR_LIMIT,"Vector flatten work budget exceeded");
  r.control=control; r.error=error; r.status=exr_control_cancel(control,error);
  if(r.status!=EXR_OK) return r.status;
  for(i=0;i<count;i++) {
    const exr_vector_segment *segment=&segments[i]; exr_vector_point p[3]; unsigned points,k;
    if(!step(&r)) goto done;
    if((unsigned)segment->verb>EXR_VECTOR_CLOSE) { fail(&r,EXR_ARGUMENT,"Invalid vector path verb"); goto done; }
    points=segment->verb==EXR_VECTOR_CLOSE ? 0 : segment->verb==EXR_VECTOR_QUAD ? 2 : segment->verb==EXR_VECTOR_CUBIC ? 3 : 1;
    for(k=0;k<points;k++) if(!transformed(&r,segment->points[k],transform,&p[k])) goto done;
    if(segment->verb==EXR_VECTOR_MOVE) { if(!contour(&r,p[0])) goto done; }
    else {
      exr_vector_contour *current; curve_node node={0};
      if(!r.path.contour_count) { fail(&r,EXR_ARGUMENT,"Vector drawing command has no current point"); goto done; }
      current=&r.path.contours[r.path.contour_count-1];
      if(segment->verb==EXR_VECTOR_CLOSE) { current->closed=1; continue; }
      if(current->closed && !contour(&r,r.path.points[current->start])) goto done;
      if(segment->verb==EXR_VECTOR_LINE) { if(!point(&r,p[0])) goto done; continue; }
      node.p[0]=r.path.points[r.path.point_count-1]; node.degree=points;
      for(k=0;k<points;k++) node.p[k+1]=p[k];
      if(!curve(&r,&node,tolerance)) goto done;
    }
  }
  r.status=exr_control_cancel(control,error);
  if(r.status==EXR_OK) { *out=r.path; memset(&r.path,0,sizeof(r.path)); r.status=exr_fail(error,EXR_OK,""); }
done:
  exr_vector_polyline_free(&r.path); return r.status;
}
exr_status exr_vector_edges(const exr_vector_polyline *path,int close_open,exr_vector_edge **out,
                             size_t *count,size_t *work,const exr_control *control,exr_error *error) {
  exr_vector_edge *edges=NULL; size_t used=0,at=0,i,j,local_work=0; exr_status status;
  if(out) *out=NULL;
  if(count) *count=0;
  if(!path || !out || !count || (path->point_count && !path->points) || (path->contour_count && !path->contours)) return exr_fail(error,EXR_ARGUMENT,"Missing vector polyline input/output");
  if(path->point_count>1048576 || path->contour_count>1048576) return exr_fail(error,EXR_LIMIT,"Vector polyline exceeds vertex budget");
  if(!work) work=&local_work;
  if(!exr_vector_work(work,path->point_count+path->contour_count)) return exr_fail(error,EXR_LIMIT,"Vector edge construction work budget exceeded");
  status=exr_control_cancel(control,error); if(status!=EXR_OK) return status;
  if(path->point_count) { edges=malloc(path->point_count*sizeof(*edges)); if(!edges) return exr_fail(error,EXR_MEMORY,"Vector edge allocation failed"); }
  for(i=0;i<path->contour_count;i++) {
    const exr_vector_contour *c=&path->contours[i];
    status=exr_control_cancel(control,error); if(status!=EXR_OK) goto done;
    if(c->start!=at || !c->count || c->count>path->point_count-at || c->closed>1) goto invalid;
    for(j=0;j<c->count;j++) {
      const exr_vector_point *p=&path->points[at+j];
      if(!isfinite(p->x) || !isfinite(p->y) || fabs(p->x)>1e7 || fabs(p->y)>1e7) goto invalid;
      if(j) { const exr_vector_point *previous=p-1; edges[used++]=(exr_vector_edge){previous->x,previous->y,p->x,p->y}; }
    }
    if(c->count>1 && (c->closed || close_open)) {
      const exr_vector_point *a=&path->points[at+c->count-1],*b=&path->points[at]; edges[used++]=(exr_vector_edge){a->x,a->y,b->x,b->y};
    }
    at+=c->count;
  }
  if(at!=path->point_count) goto invalid;
  *out=edges; *count=used; return exr_fail(error,EXR_OK,"");
invalid:
  status=exr_fail(error,EXR_ARGUMENT,"Invalid vector polyline spans or points");
done:
  free(edges); return status;
}
