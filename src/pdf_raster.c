/* SPDX-License-Identifier: MIT */
#include "pdf_raster_internal.h"
#include "canvas_internal.h"
exr_status exr_pdf_raster_content(exr_pdf_file *file,uint32_t resources,const void *content,size_t size,
                                   const double initial[6],const exr_pdf_raster_config *config,
                                   const exr_control *control,exr_bitmap *out,exr_error *e) {
  exr_canvas *canvas=NULL; exr_canvas_config settings={0}; exr_draw_sink_ex sink={0}; exr_status status; size_t i;int gray=0;
  if(out) memset(out,0,sizeof(*out));
  if(!out || !file || !config || (!content && size) || !config->width || !config->height || config->width>16384 || config->height>16384 ||
     (config->channels!=1 && config->channels!=4) || config->width>(size_t)64*1024*1024/config->channels/config->height)
    return exr_fail(e,EXR_ARGUMENT,"Invalid PDF raster output configuration");
  if(exr_control_cancel(control,e)!=EXR_OK) return EXR_CANCELLED;
  if(config->initial_clip) {
    const double *b=config->initial_clip;
    for(i=0;i<4;i++) if(!isfinite(b[i]) || fabs(b[i])>1e7) return exr_fail(e,EXR_ARGUMENT,"Invalid initial PDF raster clip");
    if(b[0]>b[2] || b[1]>b[3]) return exr_fail(e,EXR_ARGUMENT,"Inverted initial PDF raster clip");
  }
  settings.width=config->width; settings.height=config->height; settings.channels=config->channels; settings.background=config->background; settings.mask_budget=config->mask_budget;
  if(config->channels==1) { gray=1;settings.channels=4;settings.background|=255; }
  if(control) settings.control=*control;
  status=exr_canvas_create(&settings,&canvas,e); if(status!=EXR_OK) return status;
  if(config->work) canvas->work=*config->work;
  if(config->initial_clip) {
    const double *b=config->initial_clip; exr_path_segment rect[5]={0};
    rect[0].verb=EXR_PATH_MOVE; rect[0].points[0]=(exr_path_point){b[0],b[1]};
    rect[1].verb=EXR_PATH_LINE; rect[1].points[0]=(exr_path_point){b[2],b[1]};
    rect[2].verb=EXR_PATH_LINE; rect[2].points[0]=(exr_path_point){b[2],b[3]};
    rect[3].verb=EXR_PATH_LINE; rect[3].points[0]=(exr_path_point){b[0],b[3]}; rect[4].verb=EXR_PATH_CLOSE;
    status=exr_canvas_clip(canvas,rect,5,config->initial_clip_transform,EXR_FILL_NONZERO,e); if(status!=EXR_OK) goto done;
  }
  sink.struct_size=sizeof(sink);status=exr_canvas_get_sink_ex(canvas,&sink,e);
  if(status==EXR_OK) status=exr_canvas_begin_group(canvas,1,EXR_BLEND_NORMAL,
    config->group_present ? config->group_flags : EXR_GROUP_ISOLATED,e);
  if(status==EXR_OK) {
    exr_error cleanup={0};exr_status ended;
    status=exr_pdf_paint_content_ex(file,resources,content,size,initial,&sink,config->program,config->context,&canvas->work,config->active_mask_bytes,control,e);
    ended=exr_canvas_end_layer(canvas,status==EXR_OK,&cleanup);
    if(status==EXR_OK && ended!=EXR_OK) { status=ended;if(e) *e=cleanup; }
  }
  if(status==EXR_OK) status=exr_canvas_take(canvas,out,e);
  if(status==EXR_OK && gray) status=exr_bitmap_to_gray(out,control,e);
  if(status!=EXR_OK) { free(out->pixels);memset(out,0,sizeof(*out)); }
done:
  if(config->work) *config->work=canvas->work;
  exr_canvas_free(canvas); return status;
}
