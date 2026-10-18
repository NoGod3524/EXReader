/* SPDX-License-Identifier: GPL-3.0-only */
#include "flow_internal.h"

void exr_flow_area(const flow *f,float y,float height,float *x,float *width,float *next) {
  size_t i; float left=f->x,right=f->x+f->width;
  *next=INFINITY;
  for(i=0;i<f->floats->count;i++) {
    const exr_float *v=&f->floats->items[i];
    if(v->y+v->height<=y+.001f || v->y>=y+height-.001f || v->x+v->width<=f->x || v->x>=f->x+f->width) continue;
    if(v->side==1) left=fmaxf(left,v->x+v->width);
    else right=fminf(right,v->x);
    *next=fminf(*next,v->y+v->height);
  }
  *x=left; *width=fmaxf(0,right-left);
}
void exr_flow_clear(flow *f,unsigned side) {
  size_t i;
  for(i=0;i<f->floats->count;i++) if(f->floats->items[i].side&side) f->y=fmaxf(f->y,f->floats->items[i].y+f->floats->items[i].height);
}
static void prune(flow *f) {
  size_t i,n=0;
  for(i=0;i<f->floats->count;i++) if(f->floats->items[i].y+f->floats->items[i].height>f->y+.001f) f->floats->items[n++]=f->floats->items[i];
  f->floats->count=n;
}
exr_status exr_flow_float_add(flow *f,exr_float item) {
  prune(f);
  size_t n=f->floats->count;
  if(n==EXR_MAX_FLOATS) return exr_fail(f->error,EXR_LIMIT,"More than 128 live floats in one formatting context");
  f->floats->items[f->floats->count++]=item;
  return EXR_OK;
}
exr_status exr_flow_line_slot(flow *f,float height,float minimum,size_t offset,float *x,float *width) {
  size_t tries;
  for(tries=0;tries<=EXR_MAX_FLOATS;tries++) {
    prune(f);
    float next; exr_status status=exr_flow_page(f,height,offset);
    if(status!=EXR_OK) return status;
    exr_flow_area(f,f->y,height,x,width,&next);
    if(*width+.001f>=fminf(f->width,minimum) || !isfinite(next)) return EXR_OK;
    f->y=next;
    if(exr_control_cancel(&f->config->control,f->error)!=EXR_OK) return EXR_CANCELLED;
  }
  return exr_fail(f->error,EXR_LIMIT,"Cannot find an inline corridor around floats");
}
exr_status exr_flow_float_slot(flow *f,float width,float height,unsigned clear,size_t offset,float *x,float *y) {
  size_t i,tries; float candidate=f->y;
  prune(f);
  for(i=0;i<f->floats->count;i++) {
    candidate=fmaxf(candidate,f->floats->items[i].y); /* A later float cannot rise above an earlier float. */
    if(f->floats->items[i].side&clear) candidate=fmaxf(candidate,f->floats->items[i].y+f->floats->items[i].height);
  }
  for(tries=0;tries<=f->floats->count;tries++) {
    float room,next,old=f->y; exr_status status;
    exr_flow_area(f,candidate,height,x,&room,&next);
    if(room+.001f>=width || !isfinite(next)) {
      f->y=candidate; status=exr_flow_page(f,height,offset); f->y=old;
      if(status!=EXR_OK) return status;
      *y=candidate; return EXR_OK;
    }
    candidate=next;
    if(exr_control_cancel(&f->config->control,f->error)!=EXR_OK) return EXR_CANCELLED;
  }
  return exr_fail(f->error,EXR_LIMIT,"Cannot place a floating margin box");
}
