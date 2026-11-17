/* SPDX-License-Identifier: MIT */
/* Included by canvas.c so glyph blits share its clip, mask and group state. */
exr_canvas *exr_canvas_from_sink(const exr_draw_sink_ex *sink) {
  return sink && sink->base.path==sink_path && sink->path_cmyk==sink_path_cmyk ? sink->base.context : NULL;
}
exr_status exr_canvas_glyph_mask(exr_canvas *c,const exr_vector_segment *segments,size_t count,
    const double matrix[6],exr_bitmap *mask,int *left,int *top,exr_error *e) {
  exr_vector_polyline flat={0};exr_vector_edge *edges=NULL;size_t n=0,i;
  double x0=1e30,y0=1e30,x1=-1e30,y1=-1e30;int right,bottom;
  exr_status status=ready(c,e);memset(mask,0,sizeof(*mask));*left=*top=0;
  if(status!=EXR_OK) return status;
  status=exr_vector_flatten(segments,count,matrix,.125,&flat,&c->work,&c->control,e);
  if(status==EXR_OK) status=exr_vector_edges(&flat,1,&edges,&n,&c->work,&c->control,e);
  if(status!=EXR_OK || !n) goto done;
  for(i=0;i<n;i++) {
    x0=fmin(x0,fmin(edges[i].x0,edges[i].x1));x1=fmax(x1,fmax(edges[i].x0,edges[i].x1));
    y0=fmin(y0,fmin(edges[i].y0,edges[i].y1));y1=fmax(y1,fmax(edges[i].y0,edges[i].y1));
  }
  if(x0<-1e7 || y0<-1e7 || x1>1e7 || y1>1e7) { status=EXR_UNSUPPORTED;goto done; }
  *left=(int)floor(x0);*top=(int)floor(y0);right=(int)ceil(x1);bottom=(int)ceil(y1);
  if(right<=*left || bottom<=*top) goto done;
  /* Oversized masks use the ordinary path, without reserving atlas memory. */
  if(right-*left>16384 || bottom-*top>16384 ||
     (size_t)(right-*left)>4u*1024u*1024u/(size_t)(bottom-*top)) { status=EXR_UNSUPPORTED;goto done; }
  mask->width=(unsigned)(right-*left);mask->height=(unsigned)(bottom-*top);
  mask->stride=mask->width;mask->channels=1;mask->pixels=calloc((size_t)mask->width,mask->height);
  if(!mask->pixels) { status=EXR_UNSUPPORTED;goto done; }
  for(i=0;i<n;i++) {
    edges[i].x0-=*left;edges[i].x1-=*left;edges[i].y0-=*top;edges[i].y1-=*top;
  }
  status=exr_vector_fill(mask,edges,n,EXR_VECTOR_NONZERO,0xffffffff,NULL,&c->work,&c->control,e);
done:
  free(edges);exr_vector_polyline_free(&flat);
  if(status!=EXR_OK) { free(mask->pixels);memset(mask,0,sizeof(*mask)); }
  return status;
}
exr_status exr_canvas_glyph_blit(exr_canvas *c,const exr_bitmap *mask,int left,int top,uint32_t color,
    size_t cached_work,exr_error *e) {
  exr_status status=ready(c,e);exr_composite_state *state;int x,y,x0,y0,x1,y1;
  if(status!=EXR_OK) return status;
  if(!exr_vector_work(&c->work,cached_work)) return finish(c,exr_fail(e,EXR_LIMIT,"Glyph atlas work budget exceeded"),e);
  if(!mask->width || !mask->height) return EXR_OK;
  left-=c->offset_x;top-=c->offset_y;
  x0=left<0 ? 0 : left;y0=top<0 ? 0 : top;
  x1=(int)fmin(c->bitmap.width,(double)left+mask->width);y1=(int)fmin(c->bitmap.height,(double)top+mask->height);
  if(x0>=x1 || y0>=y1) return EXR_OK;
  if(c->gray_groups) color=exr_gray_color(color);
  state=masked_state(c);
  for(y=y0;y<y1;y++) {
    const unsigned char *source=mask->pixels+(size_t)(y-top)*mask->stride;
    const unsigned char *clip=c->clip ? c->clip->bitmap.pixels+(size_t)y*c->clip->bitmap.stride : NULL;
    status=exr_control_cancel(&c->control,e);if(status!=EXR_OK) return finish(c,status,e);
    size_t cost=(state ? 20+state->depth*4 : 0)+(c->blend==EXR_BLEND_NORMAL ? 1 : c->blend<EXR_BLEND_HUE ? 24 : 64);
    if(!exr_vector_work(&c->work,(size_t)(x1-x0)*cost)) return finish(c,exr_fail(e,EXR_LIMIT,"Glyph atlas work budget exceeded"),e);
    for(x=x0;x<x1;x++) {
      unsigned coverage=source[x-left];
      if(clip) coverage=(coverage*clip[x]+127)/255;
      if(!coverage) continue;
      if(state) exr_pixel_composite(&c->bitmap,x,y,color,coverage,c->blend,state);
      else if(c->blend==EXR_BLEND_NORMAL) exr_pixel(&c->bitmap,x,y,color,coverage);
      else exr_pixel_blend(&c->bitmap,x,y,color,coverage,c->blend);
    }
  }
  return finish(c,EXR_OK,e);
}
