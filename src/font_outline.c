/* SPDX-License-Identifier: MIT */
#include "font_outline_internal.h"
#include FT_OUTLINE_H

typedef struct {
  exr_vector_segment *segments; size_t count,capacity,*work; double scale;
  const exr_control *control; exr_error *error; exr_status status; unsigned contour;
} outline_reader;
static int segment(outline_reader *r,exr_vector_verb verb,const FT_Vector *a,const FT_Vector *b,const FT_Vector *c) {
  exr_vector_segment s={0}; const FT_Vector *points[]={a,b,c}; size_t i;
  if(r->count==1048576 || !exr_vector_work(r->work,1)) { r->status=exr_fail(r->error,EXR_LIMIT,"Font outline command/work budget exceeded"); return 1; }
  if(!(r->count&255) && (r->status=exr_control_cancel(r->control,r->error))!=EXR_OK) return 1;
  s.verb=verb;
  for(i=0;i<3 && points[i];i++) {
    s.points[i].x=(double)points[i]->x*r->scale; s.points[i].y=(double)points[i]->y*r->scale;
    if(!isfinite(s.points[i].x) || !isfinite(s.points[i].y) || fabs(s.points[i].x)>1e7 || fabs(s.points[i].y)>1e7) {
      r->status=exr_fail(r->error,EXR_LIMIT,"Font outline coordinates exceed budget"); return 1;
    }
  }
  if(!exr_grow((void **)&r->segments,&r->capacity,r->count+1,sizeof(*r->segments))) {
    r->status=exr_fail(r->error,EXR_MEMORY,"Font outline allocation failed"); return 1;
  }
  r->segments[r->count++]=s; return 0;
}
static int move_to(const FT_Vector *to,void *context) {
  outline_reader *r=context;
  if(r->contour && segment(r,EXR_VECTOR_CLOSE,NULL,NULL,NULL)) return 1;
  r->contour=1; return segment(r,EXR_VECTOR_MOVE,to,NULL,NULL);
}
static int line_to(const FT_Vector *to,void *context) { return segment(context,EXR_VECTOR_LINE,to,NULL,NULL); }
static int conic_to(const FT_Vector *control,const FT_Vector *to,void *context) { return segment(context,EXR_VECTOR_QUAD,control,to,NULL); }
static int cubic_to(const FT_Vector *a,const FT_Vector *b,const FT_Vector *to,void *context) { return segment(context,EXR_VECTOR_CUBIC,a,b,to); }
exr_status exr_font_outline(FT_Face face,uint32_t glyph,exr_vector_segment **out,size_t *count,
                             size_t *work,const exr_control *control,exr_error *error) {
  FT_Outline_Funcs callbacks={move_to,line_to,conic_to,cubic_to,0,0}; outline_reader r={0}; size_t local_work=0; int ft_error;
  if(out) *out=NULL;
  if(count) *count=0;
  if(!out || !count || !face || !FT_IS_SCALABLE(face) || !face->units_per_EM || glyph>=(uint64_t)face->num_glyphs)
    return exr_fail(error,EXR_ARGUMENT,"Invalid scalable font outline input");
  r.work=work ? work : &local_work; r.control=control; r.error=error; r.scale=1000.0/face->units_per_EM;
  if(exr_control_cancel(control,error)!=EXR_OK) return EXR_CANCELLED;
  /* Slot transforms must not leak from another user of this face. */
  FT_Set_Transform(face,NULL,NULL);
  if(FT_Load_Glyph(face,glyph,FT_LOAD_NO_SCALE|FT_LOAD_NO_HINTING|FT_LOAD_NO_BITMAP|FT_LOAD_IGNORE_TRANSFORM) ||
     face->glyph->format!=FT_GLYPH_FORMAT_OUTLINE || FT_Outline_Check(&face->glyph->outline))
    return exr_fail(error,EXR_FORMAT,"Cannot load scalable font outline");
  if(!exr_vector_work(r.work,(size_t)face->glyph->outline.n_points)) return exr_fail(error,EXR_LIMIT,"Font outline work budget exceeded");
  ft_error=FT_Outline_Decompose(&face->glyph->outline,&callbacks,&r);
  if(!ft_error && r.contour) ft_error=segment(&r,EXR_VECTOR_CLOSE,NULL,NULL,NULL);
  if(ft_error && r.status==EXR_OK) r.status=exr_fail(error,EXR_FORMAT,"Invalid font outline contours");
  if(r.status==EXR_OK) r.status=exr_control_cancel(control,error);
  if(r.status==EXR_OK) { *out=r.segments; *count=r.count; if(error) memset(error,0,sizeof(*error)); }
  else free(r.segments);
  return r.status;
}
