/* SPDX-License-Identifier: MIT */
#include "vector_internal.h"
#include <float.h>
typedef struct {
  exr_vector_polyline path; const double *lengths; size_t length_count,effective,index,*work;
  double remaining; int active;
  const exr_control *control; exr_error *error; exr_status status;
} dash_reader;
static int failed(dash_reader *r,exr_status status,const char *message) { r->status=exr_fail(r->error,status,"%s",message); return 0; }
static int work(dash_reader *r,size_t amount) {
  if(!exr_vector_work(r->work,amount)) return failed(r,EXR_LIMIT,"Vector dash work budget exceeded");
  r->status=exr_control_cancel(r->control,r->error); return r->status==EXR_OK;
}
static int equal(exr_vector_point a,exr_vector_point b) { return a.x==b.x && a.y==b.y; }
static int append(dash_reader *r,exr_vector_point p) {
  exr_vector_polyline *path=&r->path;
  if(path->point_count==1048576) return failed(r,EXR_LIMIT,"Vector dash vertex budget exceeded");
  if(!exr_grow((void **)&path->points,&path->point_capacity,path->point_count+1,sizeof(*path->points))) return failed(r,EXR_MEMORY,"Vector dash point allocation failed");
  path->points[path->point_count++]=p; path->contours[path->contour_count-1].count++; return 1;
}
static int begin(dash_reader *r,exr_vector_point p) {
  exr_vector_polyline *path=&r->path;
  if(path->contour_count==1048576) return failed(r,EXR_LIMIT,"Vector dash contour budget exceeded");
  if(!exr_grow((void **)&path->contours,&path->contour_capacity,path->contour_count+1,sizeof(*path->contours))) return failed(r,EXR_MEMORY,"Vector dash contour allocation failed");
  path->contours[path->contour_count++]=(exr_vector_contour){path->point_count,0,0}; return append(r,p);
}
static int dot(dash_reader *r,exr_vector_point p) { r->active=0; return begin(r,p) && append(r,p); }
static int transitions(dash_reader *r,exr_vector_point p) {
  size_t steps=0;
  while(!r->remaining) {
    if(!work(r,1)) return 0;
    if(++steps>r->effective) return failed(r,EXR_ARGUMENT,"Dash pattern has no positive lengths");
    if(!(r->index&1) && !r->lengths[r->index%r->length_count] && !dot(r,p)) return 0;
    r->index=(r->index+1)%r->effective; r->remaining=r->lengths[r->index%r->length_count]; r->active=0;
  }
  return 1;
}
static int nonzero(const exr_vector_polyline *path,size_t index) {
  const exr_vector_contour *c=&path->contours[index]; size_t i;
  for(i=1;i<c->count;i++) if(!equal(path->points[c->start],path->points[c->start+i])) return 1;
  return 0;
}
static int seam(dash_reader *r,size_t base,exr_vector_point origin) {
  exr_vector_polyline *path=&r->path; size_t first=base,last=path->contour_count,i,removed,insert,tail;
  exr_vector_point *saved; exr_vector_contour *a,*b;
  while(first<last && !nonzero(path,first)) first++;
  while(last>first && !nonzero(path,last-1)) last--;
  if(first==last) return 1;
  last--; a=&path->contours[first]; b=&path->contours[last];
  if(!equal(path->points[a->start],origin) || !equal(path->points[b->start+b->count-1],origin)) return 1;
  if(first==last) { a->closed=1; return 1; }
  if(!work(r,path->point_count-a->start+path->contour_count-first)) return 0;
  removed=a->count; saved=malloc(removed*sizeof(*saved));
  if(!saved) return failed(r,EXR_MEMORY,"Vector dash seam allocation failed");
  memcpy(saved,path->points+a->start,removed*sizeof(*saved));
  memmove(path->points+a->start,path->points+a->start+removed,(path->point_count-a->start-removed)*sizeof(*path->points));
  path->point_count-=removed;
  for(i=first+1;i<path->contour_count;i++) path->contours[i].start-=removed;
  memmove(path->contours+first,path->contours+first+1,(path->contour_count-first-1)*sizeof(*path->contours)); path->contour_count--;
  b=&path->contours[last-1]; insert=b->start+b->count; tail=removed-1;
  memmove(path->points+insert+tail,path->points+insert,(path->point_count-insert)*sizeof(*path->points));
  memcpy(path->points+insert,saved+1,tail*sizeof(*saved)); free(saved);
  b->count+=tail; path->point_count+=tail;
  for(i=last;i<path->contour_count;i++) path->contours[i].start+=tail;
  return 1;
}
exr_status exr_vector_dash(const exr_vector_polyline *source,const double *lengths,size_t length_count,
                            double phase,exr_vector_polyline *out,size_t *shared_work,
                            const exr_control *control,exr_error *error) {
  dash_reader r={0}; double period=0; size_t local_work=0,at=0,i,j;
  if(source==out) return exr_fail(error,EXR_ARGUMENT,"Vector dash input and output must be distinct");
  if(out) memset(out,0,sizeof(*out));
  if(!source || !out || (source->point_count && !source->points) || (source->contour_count && !source->contours) ||
     (length_count && !lengths) || !isfinite(phase) || fabs(phase)>1e12) return exr_fail(error,EXR_ARGUMENT,"Invalid vector dash input or phase");
  if(source->point_count>1048576 || source->contour_count>1048576 || length_count>1024) return exr_fail(error,EXR_LIMIT,"Vector dash input budget exceeded");
  r.work=shared_work ? shared_work : &local_work; r.control=control; r.error=error; r.lengths=lengths; r.length_count=length_count; r.effective=length_count*(length_count%2 ? 2 : 1);
  if(!work(&r,source->point_count+source->contour_count+length_count)) goto done;
  for(i=0;i<length_count;i++) {
    if(!isfinite(lengths[i]) || lengths[i]<0 || lengths[i]>1e7) { failed(&r,EXR_ARGUMENT,"Invalid vector dash length"); goto done; }
    period+=lengths[i];
  }
  if(length_count && !period) { failed(&r,EXR_ARGUMENT,"Vector dash pattern has no positive lengths"); goto done; }
  if(length_count%2) period*=2;
  for(i=0;i<source->point_count;i++) {
    exr_vector_point p=source->points[i];
    if(!(i&1023) && !work(&r,0)) goto done;
    if(!isfinite(p.x) || !isfinite(p.y) || fabs(p.x)>1e7 || fabs(p.y)>1e7) { failed(&r,EXR_ARGUMENT,"Invalid vector dash source coordinates"); goto done; }
  }
  for(i=0;i<source->contour_count;i++) {
    const exr_vector_contour *c=&source->contours[i];
    if(c->start!=at || !c->count || c->count>source->point_count-at || c->closed>1) { failed(&r,EXR_ARGUMENT,"Invalid vector dash contour spans"); goto done; }
    at+=c->count;
  }
  if(at!=source->point_count) { failed(&r,EXR_ARGUMENT,"Vector dash source has unclaimed points"); goto done; }
  if(!length_count) {
    if(source->point_count) {
      r.path.points=malloc(source->point_count*sizeof(*r.path.points));
      if(!r.path.points) { failed(&r,EXR_MEMORY,"Vector dash copy allocation failed"); goto done; }
      memcpy(r.path.points,source->points,source->point_count*sizeof(*r.path.points)); r.path.point_count=r.path.point_capacity=source->point_count;
    }
    if(source->contour_count) {
      r.path.contours=malloc(source->contour_count*sizeof(*r.path.contours));
      if(!r.path.contours) { failed(&r,EXR_MEMORY,"Vector dash contour copy failed"); goto done; }
      memcpy(r.path.contours,source->contours,source->contour_count*sizeof(*r.path.contours)); r.path.contour_count=r.path.contour_capacity=source->contour_count;
    }
    goto success;
  }
  for(i=0;i<source->contour_count;i++) {
    const exr_vector_contour *c=&source->contours[i]; exr_vector_point current=source->points[c->start]; size_t base=r.path.contour_count; int moved=0;
    double offset=fmod(phase,period); if(offset<0) offset+=period;
    if(c->count<2) continue;
    r.index=0; r.remaining=lengths[0]; r.active=0;
    while(offset>0) {
      if(!work(&r,1)) goto done;
      if(offset<r.remaining) { r.remaining-=offset; offset=0; }
      else { offset-=r.remaining; r.index=(r.index+1)%r.effective; r.remaining=lengths[r.index%length_count]; }
    }
    if(!transitions(&r,current)) goto done;
    for(j=1;j<c->count+(size_t)c->closed;j++) {
      exr_vector_point end=source->points[c->start+(j==c->count ? 0 : j)]; double left=hypot(end.x-current.x,end.y-current.y);
      while(left>0) {
        double amount,remaining,epsilon; exr_vector_point next;
        if(!transitions(&r,current) || !work(&r,1)) goto done;
        epsilon=16*DBL_EPSILON*fmax(1,fmax(left,r.remaining));
        amount=fmin(left,r.remaining); remaining=left-amount;
        next=remaining<epsilon ? end : (exr_vector_point){current.x+(end.x-current.x)*(amount/left),current.y+(end.y-current.y)*(amount/left)};
        if(remaining==left || equal(next,current)) { failed(&r,EXR_LIMIT,"Dash length is below coordinate precision"); goto done; }
        if(!(r.index&1)) {
          if(!r.active) { if(!begin(&r,current)) goto done; r.active=1; }
          if(!append(&r,next)) goto done;
        }
        current=next; moved=1;
        r.remaining=amount==r.remaining ? 0 : r.remaining-amount; if(r.remaining<epsilon) r.remaining=0;
        left=remaining; if(left<epsilon) { left=0; current=end; }
        if(!r.remaining) r.active=0;
      }
    }
    if(!transitions(&r,current)) goto done;
    if(!moved && !(r.index&1) && !dot(&r,current)) goto done;
    if(c->closed && !seam(&r,base,source->points[c->start])) goto done;
  }
success:
  r.status=exr_control_cancel(control,error); if(r.status!=EXR_OK) goto done;
  *out=r.path; memset(&r.path,0,sizeof(r.path)); r.status=exr_fail(error,EXR_OK,"");
done:
  exr_vector_polyline_free(&r.path); return r.status;
}
