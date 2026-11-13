/* SPDX-License-Identifier: MIT */
/* Client-coordinate preview. A drag writes once on release; Escape only drops
   the preview, preserving dirty state, history and the original EMU dimensions. */
#include <math.h>
typedef struct { double x,y,width,height; } de_image_box;
typedef struct {
  exr_edit_id id;
  int active,handle;
  double pointer_x,pointer_y,width_pt,height_pt,scale;
  de_image_box original,preview;
} de_image_resize;

/* Clockwise from top left: NW, N, NE, E, SE, S, SW, W. */
static void de_image_handle(const de_image_box *b,int handle,double *x,double *y) {
  static const int xs[]={0,1,2,2,2,1,0,0},ys[]={0,0,0,1,2,2,2,1};
  *x=b->x+b->width*xs[handle]/2.; *y=b->y+b->height*ys[handle]/2.;
}
static int de_image_handle_hit(const de_image_box *b,double x,double y,double radius) {
  for(int i=0;i<8;i++) {
    double hx,hy; de_image_handle(b,i,&hx,&hy);
    if(fabs(x-hx)<=radius && fabs(y-hy)<=radius)return i;
  }
  return -1;
}
static int de_image_resize_begin(de_image_resize *drag,const exr_edit_doc *doc,
    exr_edit_id id,const de_image_box *box,int handle,double x,double y) {
  const exr_edit_block *b=exr_edit_find_block(doc,id);
  if(!b || !b->image || handle<0 || handle>7 || !isfinite(box->width) ||
      !isfinite(box->height) || box->width<=0 || box->height<=0 ||
      !isfinite(x) || !isfinite(y))return 0;
  memset(drag,0,sizeof(*drag));drag->active=1;drag->id=id;drag->handle=handle;
  drag->pointer_x=x;drag->pointer_y=y;drag->original=drag->preview=*box;
  drag->width_pt=b->image->width_emu/12700.;drag->height_pt=b->image->height_emu/12700.;
  drag->scale=1;return 1;
}
static void de_image_resize_move(de_image_resize *drag,double x,double y) {
  static const int dx[]={-1,0,1,1,1,0,-1,-1},dy[]={-1,-1,-1,0,1,1,1,0};
  if(!drag->active || !isfinite(x) || !isfinite(y))return;
  int h=drag->handle; const de_image_box *b=&drag->original;
  double vx=dx[h]*b->width,vy=dy[h]*b->height;
  /* Project corners onto the original diagonal; side handles use one axis. */
  double scale=1+((x-drag->pointer_x)*vx+(y-drag->pointer_y)*vy)/(vx*vx+vy*vy);
  double min_scale=8./fmin(b->width,b->height);
  double max_scale=((double)INT32_MAX/12700.)/fmax(drag->width_pt,drag->height_pt);
  if(min_scale>1)min_scale=1;
  if(scale<min_scale)scale=min_scale;
  if(scale>max_scale)scale=max_scale;
  drag->scale=scale;drag->preview=*b;
  drag->preview.width=b->width*scale;drag->preview.height=b->height*scale;
  drag->preview.x+=dx[h]<0 ? b->width-drag->preview.width:dx[h]==0 ? (b->width-drag->preview.width)/2:0;
  drag->preview.y+=dy[h]<0 ? b->height-drag->preview.height:dy[h]==0 ? (b->height-drag->preview.height)/2:0;
}
static exr_status de_image_resize_end(de_image_resize *drag,exr_edit_doc *doc,int cancel) {
  exr_status status=EXR_OK;
  if(drag->active && !cancel && drag->scale!=1)
    status=exr_edit_image_size(doc,drag->id,drag->width_pt*drag->scale,drag->height_pt*drag->scale);
  drag->active=0;return status;
}
#if defined(_WIN32) && !defined(DE_IMAGE_RESIZE_NO_PAINT)
static void de_image_resize_handles(HDC dc,const de_image_box *b,unsigned dpi,float top,float bottom) {
  int radius=MulDiv(4,(int)dpi,96);if(radius<3)radius=3;
  int saved=SaveDC(dc);IntersectClipRect(dc,0,(int)ceil(top),INT_MAX,(int)ceil(bottom));
  HBRUSH brush=CreateSolidBrush(RGB(255,255,255));HPEN pen=CreatePen(PS_SOLID,1,RGB(30,105,210));
  SelectObject(dc,brush);SelectObject(dc,pen);
  for(int i=0;i<8;i++) {
    double x,y;de_image_handle(b,i,&x,&y);
    Rectangle(dc,(int)lround(x)-radius,(int)lround(y)-radius,(int)lround(x)+radius+1,(int)lround(y)+radius+1);
  }
  RestoreDC(dc,saved);DeleteObject(pen);DeleteObject(brush);
}
#endif
