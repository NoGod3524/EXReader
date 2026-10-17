/* SPDX-License-Identifier: GPL-3.0-only */
#include "pdf_raster_internal.h"
exr_status exr_pdf_page_viewport(const exr_pdf_page_info *page,double scale,exr_viewport *out,exr_error *e) {
  exr_page_geometry geometry={0}; size_t i;
  if(out) memset(out,0,sizeof(*out));
  if(!page || !out) return exr_fail(e,EXR_ARGUMENT,"Missing PDF page viewport input/output");
  for(i=0;i<4;i++) if(!isfinite(page->crop[i]) || !isfinite(page->media[i])) return exr_fail(e,EXR_FORMAT,"Invalid PDF page rectangle");
  for(i=0;i<2;i++) { geometry.bounds[i]=fmax(page->crop[i],page->media[i]); geometry.bounds[i+2]=fmin(page->crop[i+2],page->media[i+2]); }
  if(geometry.bounds[0]>=geometry.bounds[2] || geometry.bounds[1]>=geometry.bounds[3]) return exr_fail(e,EXR_FORMAT,"PDF CropBox has no visible MediaBox intersection");
  geometry.unit_scale=page->user_unit; geometry.rotation=page->rotation;
  return exr_viewport_create(&geometry,scale,out,e);
}
exr_status exr_pdf_raster_page(exr_pdf_file *file,const exr_pdf_page_info *page,double scale,
                                const exr_pdf_raster_config *config,const exr_control *control,
                                exr_bitmap *out,exr_error *e) {
  exr_pdf_raster_config settings={0}; exr_viewport view; exr_buffer content={0}; double clip[4]={0,0,0,0}; exr_status status;
  if(out) memset(out,0,sizeof(*out));
  if(!file || !out) return exr_fail(e,EXR_ARGUMENT,"Missing PDF page raster input/output");
  if(exr_control_cancel(control,e)!=EXR_OK) return EXR_CANCELLED;
  status=exr_pdf_page_viewport(page,scale,&view,e); if(status!=EXR_OK) return status;
  if(view.width>16384 || view.height>16384) return exr_fail(e,EXR_LIMIT,"PDF page bitmap dimensions exceed 16384");
  if(config) settings=*config; else { settings.channels=4; settings.background=0xffffffff; }
  settings.width=(uint32_t)ceil(view.width); settings.height=(uint32_t)ceil(view.height);
  clip[2]=view.width; clip[3]=view.height; settings.initial_clip=clip;
  status=exr_pdf_content(file,page->contents,&content,e);
  if(status==EXR_OK) status=exr_pdf_raster_content(file,page->resources,content.data,content.size,view.matrix,&settings,control,out,e);
  free(content.data); return status;
}
