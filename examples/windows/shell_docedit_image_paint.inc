/* SPDX-License-Identifier: MIT */
/* Image rows use the same document coordinates for paint and hit testing.
   Include after shell_d2d.h and exr/edit.h. The caller owns decoded pixels. */
#include <exr/graphics.h>
#include <math.h>
#include <string.h>

typedef struct {
  exr_bitmap bitmap;
  float x,y,width,height;
  size_t block;
} de_image_view;

static void de_image_release(de_image_view *view) {
  exr_bitmap_free(&view->bitmap);
  memset(view,0,sizeof(*view));
}

/* Start with a fresh view (or release the previous one before remeasuring).
   The public block view supplies borrowed payload and exact EMUs; decoded
   pixels below are owned independently of later model mutations. */
static exr_status de_image_measure(const exr_edit_doc *doc,size_t block,
    float left,float y,float available,unsigned dpi,de_image_view *view) {
  const exr_edit_block *b=exr_edit_block_at(doc,block);
  memset(view,0,sizeof(*view));
  if(!b || b->kind!=EXR_EDIT_IMAGE || !b->image || !dpi ||
      !isfinite(left) || !isfinite(y) || !isfinite(available) || available<=0)
    return EXR_ARGUMENT;
  const exr_edit_image *im=b->image;
  if(im->width_emu<=0 || im->height_emu<=0)return EXR_ARGUMENT;
  exr_status status=exr_image_decode(im->data,im->size,&view->bitmap,NULL);
  if(status!=EXR_OK)return status;
  double width=(double)im->width_emu*dpi/914400.,height=(double)im->height_emu*dpi/914400.;
  if(width>available) {height*=available/width;width=available;}
  if(!isfinite(height) || height>1e7 || height<=0) {
    de_image_release(view);return EXR_LIMIT;
  }
  view->block=block;view->width=(float)width;view->height=(float)height;
  view->x=left+(available-view->width)*.5f;view->y=y;
  return EXR_OK;
}

/* Client coordinates; toolbar and blank margins never select an image.
   SIZE_MAX is the deselected state, including a click on whitespace. */
static size_t de_image_hit(const de_image_view *views,size_t count,
    float x,float y,float scroll,float top,float viewport_height) {
  if(!isfinite(x) || !isfinite(y) || y<top || y>=viewport_height)return SIZE_MAX;
  y+=scroll;
  for(size_t i=0;i<count;i++) {
    const de_image_view *v=views+i;
    if(v->bitmap.pixels && x>=v->x && x<v->x+v->width &&
        y>=v->y && y<v->y+v->height)return v->block;
  }
  return SIZE_MAX;
}

static HRESULT de_image_paint(shell_d2d *shell,HDC dc,const RECT *area,int dark,
    const de_image_view *view,float scroll,float top,size_t selected) {
  return shell_d2d_edit_image(shell,dc,area,dark,view->bitmap.pixels,
    view->bitmap.width,view->bitmap.height,(unsigned)view->bitmap.stride,
    view->x,view->y-scroll,view->width,view->height,top,selected==view->block);
}
