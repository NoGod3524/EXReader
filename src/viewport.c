/* SPDX-License-Identifier: MIT */
#include "base_internal.h"
exr_status exr_viewport_create(const exr_page_geometry *page,double scale,exr_viewport *out,exr_error *e) {
  exr_viewport view={0}; double factor,width,height,base[6],rotation[6]={1,0,0,1,0,0},det; size_t i;
  if(out) memset(out,0,sizeof(*out));
  if(!out || !page || !isfinite(scale) || scale<=0 || scale>1e7 || !isfinite(page->unit_scale) || page->unit_scale<=0 ||
     page->unit_scale>1e7 || page->y_down>1 || page->rotation>270 || page->rotation%90)
    return exr_fail(e,EXR_ARGUMENT,"Invalid page geometry, rotation or scale");
  for(i=0;i<4;i++) if(!isfinite(page->bounds[i]) || fabs(page->bounds[i])>1e7) return exr_fail(e,EXR_ARGUMENT,"Invalid page bounds");
  if(page->bounds[0]>=page->bounds[2] || page->bounds[1]>=page->bounds[3]) return exr_fail(e,EXR_ARGUMENT,"Empty page bounds");
  factor=scale*page->unit_scale; width=(page->bounds[2]-page->bounds[0])*factor; height=(page->bounds[3]-page->bounds[1])*factor;
  if(!isfinite(width) || !isfinite(height) || width<=0 || height<=0 || width>1e7 || height>1e7) goto limit;
  base[0]=factor; base[1]=base[2]=0; base[3]=page->y_down ? factor : -factor;
  base[4]=-page->bounds[0]*factor; base[5]=(page->y_down ? -page->bounds[1] : page->bounds[3])*factor;
  if(page->rotation==90) { rotation[0]=rotation[3]=0; rotation[1]=1; rotation[2]=-1; rotation[4]=height; }
  else if(page->rotation==180) { rotation[0]=rotation[3]=-1; rotation[4]=width; rotation[5]=height; }
  else if(page->rotation==270) { rotation[0]=rotation[3]=0; rotation[1]=-1; rotation[2]=1; rotation[5]=width; }
  view.width=page->rotation%180 ? height : width; view.height=page->rotation%180 ? width : height;
  view.matrix[0]=rotation[0]*base[0]; view.matrix[1]=rotation[1]*base[0];
  view.matrix[2]=rotation[2]*base[3]; view.matrix[3]=rotation[3]*base[3];
  view.matrix[4]=rotation[0]*base[4]+rotation[2]*base[5]+rotation[4];
  view.matrix[5]=rotation[1]*base[4]+rotation[3]*base[5]+rotation[5];
  det=view.matrix[0]*view.matrix[3]-view.matrix[1]*view.matrix[2]; if(!isfinite(det) || !det) goto limit;
  view.inverse[0]=view.matrix[3]/det; view.inverse[1]=-view.matrix[1]/det; view.inverse[2]=-view.matrix[2]/det; view.inverse[3]=view.matrix[0]/det;
  view.inverse[4]=-(view.inverse[0]*view.matrix[4]+view.inverse[2]*view.matrix[5]);
  view.inverse[5]=-(view.inverse[1]*view.matrix[4]+view.inverse[3]*view.matrix[5]);
  for(i=0;i<6;i++) if(!isfinite(view.matrix[i]) || !isfinite(view.inverse[i]) || fabs(view.matrix[i])>1e7 || fabs(view.inverse[i])>1e7) goto limit;
  *out=view; return exr_fail(e,EXR_OK,"");
limit:
  return exr_fail(e,EXR_LIMIT,"Page viewport exceeds coordinate or precision budget");
}
