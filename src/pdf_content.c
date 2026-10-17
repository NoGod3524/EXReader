/* SPDX-License-Identifier: GPL-3.0-only */
#include "pdf_internal.h"
typedef struct {
  double ctm[6],size,char_space,word_space,scale,leading,rise;
  exr_pdf_font *font; unsigned mode; exr_pdf_paint_state paint;
  const exr_pdf_colorspace *fill_space,*stroke_space;
} content_state;
typedef struct { uint32_t id; exr_pdf_font *font; } cached_font;
typedef struct { uint32_t id,resources; exr_pdf_colorspace *space; } cached_color;
typedef struct dash_profile { struct dash_profile *next; size_t count; double phase; double values[]; } dash_profile;
typedef struct {
  exr_vector_segment *segments; size_t count,capacity;
  exr_vector_point current,start; unsigned has_point,pending_clip; exr_vector_rule clip_rule;
} content_path;
typedef struct {
  exr_pdf_file *file; uint32_t resources; const exr_control *control;
  exr_pdf_draw_callbacks callbacks; void *context; unsigned graphics;
  content_path path; dash_profile *profiles; size_t profile_bytes,path_bytes,inline_work;
  content_state state,stack[128]; size_t depth,floor,sequence,font_count,font_bytes,operations,form_depth;
  uint32_t forms[32];
  double matrix[6],line[6]; unsigned inside,compatibility;
  unsigned type3,declared,uncolored;
  cached_font fonts[128];
  cached_color colors[128]; size_t color_count,color_bytes,color_work;
} content_reader;
static void identity(double matrix[6]) { memset(matrix,0,6*sizeof(double)); matrix[0]=matrix[3]=1; }
static int multiply(double out[6],const double left[6],const double right[6]) {
  double m[6]; size_t i;
  m[0]=left[0]*right[0]+left[2]*right[1]; m[1]=left[1]*right[0]+left[3]*right[1];
  m[2]=left[0]*right[2]+left[2]*right[3]; m[3]=left[1]*right[2]+left[3]*right[3];
  m[4]=left[0]*right[4]+left[2]*right[5]+left[4]; m[5]=left[1]*right[4]+left[3]*right[5]+left[5];
  for(i=0;i<6;i++) if(!isfinite(m[i]) || fabs(m[i])>1e12) return 0;
  memcpy(out,m,sizeof(m)); return 1;
}
static int translate(double matrix[6],double x,double y) { const double move[6]={1,0,0,1,x,y}; return multiply(matrix,matrix,move); }
static int numeric(exr_pdf_file *arena,uint32_t id,double *out) {
  const exr_pdf_value *v=exr_pdf_value_at(arena,id);
  if(!v || (v->kind!=EXR_PDF_INT && v->kind!=EXR_PDF_REAL)) return 0;
  *out=v->kind==EXR_PDF_INT ? (double)v->u.integer : v->u.number;
  return isfinite(*out) && fabs(*out)<=1e7;
}
static exr_status resolved(exr_pdf_file *file,uint32_t id,uint32_t *out,exr_error *error) { return exr_pdf_resolve(file,id,out,error); }
static exr_status resource(content_reader *r,exr_pdf_file *arena,uint32_t name,const char *kind,uint32_t *out,exr_error *error) {
  const unsigned char *data; size_t n; char key[128]; uint32_t dictionary;
  data=exr_pdf_bytes(arena,name,&n);
  if(!data || exr_pdf_value_at(arena,name)->kind!=EXR_PDF_NAME || !n || n>127 || memchr(data,0,n)) return exr_fail(error,EXR_FORMAT,"Invalid PDF text resource name");
  memcpy(key,data,n); key[n]=0;
  if(resolved(r->file,exr_pdf_get(r->file,r->resources,kind),&dictionary,error)!=EXR_OK) return error->code;
  if(resolved(r->file,exr_pdf_get(r->file,dictionary,key),out,error)!=EXR_OK) return error->code;
  if(*out==EXR_PDF_NONE) return exr_fail(error,EXR_FORMAT,"Missing PDF text resource");
  return EXR_OK;
}
static exr_status select_font(content_reader *r,uint32_t id,double size,exr_error *error) {
  size_t i,bytes; exr_pdf_font *font=NULL;
  for(i=0;i<r->font_count;i++) if(r->fonts[i].id==id) { r->state.font=r->fonts[i].font; r->state.size=size; return EXR_OK; }
  if(r->font_count==128) return exr_fail(error,EXR_LIMIT,"PDF page font cache exceeds 128 fonts");
  if(exr_pdf_font_open(r->file,id,r->control,&font,error)!=EXR_OK) return error->code;
  bytes=exr_pdf_font_memory(font);
  if(bytes>EXR_MAX_INPUT-r->font_bytes) { exr_pdf_font_close(font); return exr_fail(error,EXR_LIMIT,"PDF page font cache exceeds 128 MiB"); }
  r->fonts[r->font_count++]=(cached_font){id,font}; r->font_bytes+=bytes; r->state.font=font; r->state.size=size; return EXR_OK;
}
static exr_pdf_paint_state paint_state(const content_reader *r) {
  exr_pdf_paint_state paint=r->state.paint; memcpy(paint.matrix,r->state.ctm,sizeof(paint.matrix));
  if(exr_pdf_colorspace_no_paint(r->state.fill_space)) paint.fill.alpha=0;
  if(exr_pdf_colorspace_no_paint(r->state.stroke_space)) paint.stroke.alpha=0;
  return paint;
}
static exr_status event(content_reader *r,exr_pdf_state_event kind,exr_error *error) {
  exr_status status=r->callbacks.state ? r->callbacks.state(r->context,kind,error) : EXR_OK;
  return status==EXR_OK && error->code!=EXR_OK ? error->code : status;
}
static exr_status type3(content_reader *r,const exr_pdf_text_glyph *glyph,exr_error *error);
static exr_status show(content_reader *r,exr_pdf_file *arena,uint32_t string,exr_error *error) {
  size_t n,at=0; const unsigned char *data=exr_pdf_bytes(arena,string,&n); const exr_pdf_font_info *font;
  if(!data || exr_pdf_value_at(arena,string)->kind!=EXR_PDF_STRING || !r->state.font) return exr_fail(error,EXR_FORMAT,"PDF text needs a string and selected font");
  font=exr_pdf_font_description(r->state.font);
  while(at<n) {
    exr_pdf_text_glyph glyph={0}; double scale[6]={0},matrix[6],advance,spacing;
    if(r->sequence==EXR_MAX_ITEMS) return exr_fail(error,EXR_LIMIT,"PDF page glyph budget exceeded");
    if(!(r->sequence&255) && exr_control_cancel(r->control,error)!=EXR_OK) return error->code;
    if(exr_pdf_font_next(r->state.font,data,n,&at,&glyph.character,error)!=EXR_OK) return error->code;
    scale[0]=r->state.size*r->state.scale/1000; scale[3]=r->state.size/1000; scale[5]=r->state.rise;
    if(font->vertical) { scale[4]=-glyph.character.vertical_x*scale[0]; scale[5]-=glyph.character.vertical_y*scale[3]; }
    if(!multiply(matrix,r->matrix,scale) || !multiply(glyph.transform,r->state.ctm,matrix)) return exr_fail(error,EXR_LIMIT,"PDF glyph transform exceeds coordinate budget");
    glyph.font=r->state.font; glyph.sequence=r->sequence++; glyph.rendering_mode=r->state.mode; glyph.paint=paint_state(r);
    { exr_status status=r->callbacks.glyph ? r->callbacks.glyph(r->context,&glyph,error) : EXR_OK; if(status!=EXR_OK) return status; if(error->code!=EXR_OK) return error->code; }
    if(r->graphics && font->kind==EXR_PDF_TYPE3 && r->state.mode!=3 && r->state.mode!=7) {
      exr_status status=type3(r,&glyph,error); if(status!=EXR_OK) return status;
    }
    spacing=r->state.char_space+(glyph.character.text.code_bytes==1 && glyph.character.text.code==32 ? r->state.word_space : 0);
    advance=(font->vertical ? glyph.character.vertical_advance : glyph.character.width)*r->state.size/1000+spacing;
    if(!translate(r->matrix,font->vertical ? 0 : advance*r->state.scale,font->vertical ? advance : 0)) return exr_fail(error,EXR_LIMIT,"PDF text position exceeds coordinate budget");
  }
  return EXR_OK;
}
static int new_line(content_reader *r,double x,double y) {
  if(!translate(r->line,x,y)) return 0;
  memcpy(r->matrix,r->line,sizeof(r->matrix)); return 1;
}
static int name_is(exr_pdf_file *arena,uint32_t id,const char *name) {
  size_t size; const unsigned char *bytes=exr_pdf_bytes(arena,id,&size);
  return bytes && exr_pdf_value_at(arena,id)->kind==EXR_PDF_NAME && size==strlen(name) && !memcmp(bytes,name,size);
}
static int device_space(exr_pdf_file *arena,uint32_t id,exr_pdf_color_space *space) {
  if(name_is(arena,id,"DeviceGray")) *space=EXR_PDF_DEVICE_GRAY;
  else if(name_is(arena,id,"DeviceRGB")) *space=EXR_PDF_DEVICE_RGB;
  else if(name_is(arena,id,"DeviceCMYK")) *space=EXR_PDF_DEVICE_CMYK;
  else return 0;
  return 1;
}
static exr_status color_model(content_reader *r,uint32_t id,const exr_pdf_colorspace **out,exr_error *error) {
  size_t i,bytes; exr_pdf_colorspace *model=NULL;
  for(i=0;i<r->color_count;i++) if(r->colors[i].id==id && r->colors[i].resources==r->resources) { *out=r->colors[i].space; return EXR_OK; }
  if(i==128) return exr_fail(error,EXR_LIMIT,"PDF color space cache exceeds 128 entries");
  if(exr_pdf_colorspace_open(r->file,id,r->file,r->resources,r->control,&model,error)!=EXR_OK) return error->code;
  bytes=exr_pdf_colorspace_memory(model);
  if(bytes>(size_t)32*1024*1024-r->color_bytes) { exr_pdf_colorspace_free(model); return exr_fail(error,EXR_LIMIT,"PDF color space cache exceeds 32 MiB"); }
  r->colors[r->color_count++]=(cached_color){id,r->resources,model}; r->color_bytes+=bytes; *out=model; return EXR_OK;
}
static exr_status set_dash(content_reader *r,exr_pdf_file *arena,uint32_t array,uint32_t phase_id,exr_error *error) {
  double values[1024],phase,total=0; size_t count=0,bytes; uint32_t at,id; const exr_pdf_value *v; dash_profile *profile;
  if(resolved(arena,array,&array,error)!=EXR_OK || resolved(arena,phase_id,&phase_id,error)!=EXR_OK) return error->code;
  v=exr_pdf_value_at(arena,array);
  if(!v || v->kind!=EXR_PDF_ARRAY || !numeric(arena,phase_id,&phase) || phase<0) goto invalid;
  at=v->first;
  while(at!=EXR_PDF_NONE) {
    uint32_t next=exr_pdf_value_at(arena,at)->next;
    if(count==1024) return exr_fail(error,EXR_LIMIT,"PDF dash array exceeds 1024 lengths");
    if(resolved(arena,at,&id,error)!=EXR_OK || !numeric(arena,id,&values[count]) || values[count]<0) goto invalid;
    total+=values[count++]; at=next;
  }
  if(count && !total) goto invalid;
  if(!count) { r->state.paint.dashes=NULL; r->state.paint.dash_count=0; r->state.paint.dash_phase=0; return EXR_OK; }
  if(count==r->state.paint.dash_count && phase==r->state.paint.dash_phase && !memcmp(values,r->state.paint.dashes,count*sizeof(double))) return EXR_OK;
  bytes=sizeof(*profile)+count*sizeof(double);
  if(bytes>(size_t)32*1024*1024-r->profile_bytes) return exr_fail(error,EXR_LIMIT,"PDF dash profile cache exceeds 32 MiB");
  profile=malloc(bytes); if(!profile) return exr_fail(error,EXR_MEMORY,"PDF dash profile allocation failed");
  profile->next=r->profiles; profile->count=count; profile->phase=phase; memcpy(profile->values,values,count*sizeof(double));
  r->profiles=profile; r->profile_bytes+=bytes; r->state.paint.dashes=profile->values; r->state.paint.dash_count=count; r->state.paint.dash_phase=phase; return EXR_OK;
invalid:
  if(error->code!=EXR_OK) return error->code;
  return exr_fail(error,EXR_FORMAT,"Invalid PDF dash array or phase");
}
static int line_parameter(content_reader *r,const char *name,double value) {
  if(!strcmp(name,"w") || !strcmp(name,"LW")) { if(value<0) return 0; r->state.paint.line.width=value; }
  else if(!strcmp(name,"M") || !strcmp(name,"ML")) { if(value<1) return 0; r->state.paint.line.miter_limit=value; }
  else {
    if(value<0 || value>2 || floor(value)!=value) return 0;
    if(!strcmp(name,"J") || !strcmp(name,"LC")) r->state.paint.line.cap=(exr_vector_cap)(unsigned)value;
    else r->state.paint.line.join=(exr_vector_join)(unsigned)value;
  }
  return 1;
}
static exr_status apply_ext_state(content_reader *r,uint32_t dictionary,exr_error *error) {
  const char *keys[]={"LW","LC","LJ","ML","CA","ca"}; size_t i; uint32_t id; double value;
  for(i=0;i<6;i++) {
    if(resolved(r->file,exr_pdf_get(r->file,dictionary,keys[i]),&id,error)!=EXR_OK) return error->code;
    if(id==EXR_PDF_NONE || exr_pdf_value_at(r->file,id)->kind==EXR_PDF_NULL) continue;
    if(!numeric(r->file,id,&value)) goto invalid;
    if(i<4) { if(!line_parameter(r,keys[i],value)) goto invalid; }
    else { if(value<0 || value>1) goto invalid; if(i==4) r->state.paint.stroke.alpha=value; else r->state.paint.fill.alpha=value; }
  }
  if(resolved(r->file,exr_pdf_get(r->file,dictionary,"D"),&id,error)!=EXR_OK) return error->code;
  if(id!=EXR_PDF_NONE && exr_pdf_value_at(r->file,id)->kind!=EXR_PDF_NULL) {
    const exr_pdf_value *v=exr_pdf_value_at(r->file,id); uint32_t array,phase;
    if(v->kind!=EXR_PDF_ARRAY || (array=v->first)==EXR_PDF_NONE || (phase=exr_pdf_value_at(r->file,array)->next)==EXR_PDF_NONE || exr_pdf_value_at(r->file,phase)->next!=EXR_PDF_NONE) goto invalid;
    if(set_dash(r,r->file,array,phase,error)!=EXR_OK) return error->code;
  }
  if(resolved(r->file,exr_pdf_get(r->file,dictionary,"BM"),&id,error)!=EXR_OK) return error->code;
  if(id!=EXR_PDF_NONE && exr_pdf_value_at(r->file,id)->kind!=EXR_PDF_NULL && !name_is(r->file,id,"Normal") && !name_is(r->file,id,"Compatible")) return exr_fail(error,EXR_FORMAT,"PDF blend modes are not implemented yet");
  if(resolved(r->file,exr_pdf_get(r->file,dictionary,"SMask"),&id,error)!=EXR_OK) return error->code;
  if(id!=EXR_PDF_NONE && exr_pdf_value_at(r->file,id)->kind!=EXR_PDF_NULL && !name_is(r->file,id,"None")) return exr_fail(error,EXR_FORMAT,"PDF soft-mask graphics states are not implemented yet");
  return EXR_OK;
invalid:
  if(error->code!=EXR_OK) return error->code;
  return exr_fail(error,EXR_FORMAT,"Invalid PDF line style or alpha graphics state");
}
static exr_status append_path(content_reader *r,exr_vector_verb verb,const exr_vector_point *points,exr_error *error) {
  content_path *path=&r->path; size_t old=path->capacity,next=old ? old*2 : 64; unsigned count=verb==EXR_VECTOR_CUBIC ? 3 : verb==EXR_VECTOR_CLOSE ? 0 : 1;
  exr_vector_segment segment={0}; unsigned i;
  if(verb!=EXR_VECTOR_MOVE && !path->has_point) return exr_fail(error,EXR_FORMAT,"PDF path command has no current point");
  if(path->count==1048576) return exr_fail(error,EXR_LIMIT,"PDF path exceeds one million commands");
  if(path->count==old && (next-old)*sizeof(segment)>EXR_MAX_INPUT-r->path_bytes) return exr_fail(error,EXR_LIMIT,"PDF active path storage exceeds 128 MiB");
  if(!exr_grow((void **)&path->segments,&path->capacity,path->count+1,sizeof(segment))) return exr_fail(error,EXR_MEMORY,"PDF path allocation failed");
  r->path_bytes+=(path->capacity-old)*sizeof(segment); segment.verb=verb;
  for(i=0;i<count;i++) segment.points[i]=points[i];
  path->segments[path->count++]=segment;
  if(verb==EXR_VECTOR_CLOSE) path->current=path->start;
  else { path->current=points[count-1]; if(verb==EXR_VECTOR_MOVE) { path->start=points[0]; path->has_point=1; } }
  return EXR_OK;
}
static int world_point(const content_reader *r,double x,double y,exr_vector_point *out) {
  out->x=r->state.ctm[0]*x+r->state.ctm[2]*y+r->state.ctm[4]; out->y=r->state.ctm[1]*x+r->state.ctm[3]*y+r->state.ctm[5];
  return isfinite(out->x) && isfinite(out->y) && fabs(out->x)<=1e7 && fabs(out->y)<=1e7;
}
static exr_status path_event(content_reader *r,const exr_vector_segment *segments,size_t count,unsigned flags,exr_vector_rule rule,exr_error *error) {
  exr_pdf_path_paint path={0}; exr_status status;
  if(!r->callbacks.path) return EXR_OK;
  path.segments=segments; path.count=count; path.flags=flags; path.rule=rule; path.paint=paint_state(r);
  status=r->callbacks.path(r->context,&path,error); return status==EXR_OK && error->code!=EXR_OK ? error->code : status;
}
static exr_status finish_path(content_reader *r,unsigned flags,exr_vector_rule rule,exr_error *error) {
  exr_status status=EXR_OK;
  if(flags) status=path_event(r,r->path.segments,r->path.count,flags,rule,error);
  if(status==EXR_OK && r->path.pending_clip) status=path_event(r,r->path.segments,r->path.count,EXR_PDF_CLIP,r->path.clip_rule,error);
  r->path.count=0; r->path.has_point=r->path.pending_clip=0; return status;
}
static exr_status graphics_operation(content_reader *r,exr_pdf_file *arena,const char *name,const uint32_t *values,size_t count,int *handled,exr_error *error) {
  double numbers[6]; size_t i,expected; exr_vector_point points[4]; exr_vector_verb verb; uint32_t id;
  *handled=1;
  if(!strcmp(name,"w") || !strcmp(name,"J") || !strcmp(name,"j") || !strcmp(name,"M")) {
    if(count!=1 || !numeric(arena,values[0],&numbers[0]) || !line_parameter(r,name,numbers[0])) goto invalid;
    return EXR_OK;
  }
  if(!strcmp(name,"d")) { if(count!=2) goto invalid; return set_dash(r,arena,values[0],values[1],error); }
  if(!strcmp(name,"G") || !strcmp(name,"g") || !strcmp(name,"RG") || !strcmp(name,"rg") || !strcmp(name,"K") || !strcmp(name,"k") ||
     !strcmp(name,"SC") || !strcmp(name,"sc") || !strcmp(name,"SCN") || !strcmp(name,"scn")) {
    int stroke=name[0]>='A' && name[0]<='Z'; exr_pdf_color *color=stroke ? &r->state.paint.stroke : &r->state.paint.fill;
    const exr_pdf_colorspace **source=stroke ? &r->state.stroke_space : &r->state.fill_space;
    if(!strcmp(name,"G") || !strcmp(name,"g")) { color->space=EXR_PDF_DEVICE_GRAY; *source=NULL; }
    else if(!strcmp(name,"RG") || !strcmp(name,"rg")) { color->space=EXR_PDF_DEVICE_RGB; *source=NULL; }
    else if(!strcmp(name,"K") || !strcmp(name,"k")) { color->space=EXR_PDF_DEVICE_CMYK; *source=NULL; }
    if(count!=(*source ? exr_pdf_colorspace_components(*source) : (size_t)color->space)) goto invalid;
    for(i=0;i<count;i++) if(!numeric(arena,values[i],&numbers[i])) goto invalid;
    if(*source) {
      if(!exr_vector_work(&r->color_work,exr_pdf_colorspace_cost(*source))) return exr_fail(error,EXR_LIMIT,"PDF content colour computation budget exceeded");
      if(exr_pdf_colorspace_rgb(*source,numbers,color->values,error)!=EXR_OK) return error->code;
      color->space=EXR_PDF_DEVICE_RGB; color->values[3]=0;
    }
    else { for(i=0;i<count;i++) color->values[i]=fmax(0,fmin(1,numbers[i])); for(;i<4;i++) color->values[i]=0; }
    return EXR_OK;
  }
  if(!strcmp(name,"CS") || !strcmp(name,"cs")) {
    int stroke=!strcmp(name,"CS"); exr_pdf_color *color=stroke ? &r->state.paint.stroke : &r->state.paint.fill;
    const exr_pdf_colorspace **source=stroke ? &r->state.stroke_space : &r->state.fill_space;
    if(count!=1) goto invalid;
    *source=NULL;
    if(!device_space(arena,values[0],&color->space)) {
      exr_pdf_color_space device;
      if(resource(r,arena,values[0],"ColorSpace",&id,error)!=EXR_OK || color_model(r,id,source,error)!=EXR_OK) return error->code;
      device=exr_pdf_colorspace_device(*source);
      if(device) { color->space=device; *source=NULL; }
    }
    memset(color->values,0,sizeof(color->values));
    if(*source) {
      double initial[4];
      if(!exr_vector_work(&r->color_work,exr_pdf_colorspace_cost(*source))) return exr_fail(error,EXR_LIMIT,"PDF content colour computation budget exceeded");
      exr_pdf_colorspace_initial(*source,initial); if(exr_pdf_colorspace_rgb(*source,initial,color->values,error)!=EXR_OK) return error->code;
      color->space=EXR_PDF_DEVICE_RGB;
    }
    else if(color->space==EXR_PDF_DEVICE_CMYK) color->values[3]=1;
    return EXR_OK;
  }
  if(!strcmp(name,"W") || !strcmp(name,"W*")) {
    if(count || r->inside) goto invalid;
    r->path.pending_clip=1; r->path.clip_rule=!strcmp(name,"W*") ? EXR_VECTOR_EVENODD : EXR_VECTOR_NONZERO; return EXR_OK;
  }
  if(!strcmp(name,"S") || !strcmp(name,"s") || !strcmp(name,"f") || !strcmp(name,"F") || !strcmp(name,"f*") ||
     !strcmp(name,"B") || !strcmp(name,"B*") || !strcmp(name,"b") || !strcmp(name,"b*") || !strcmp(name,"n")) {
    unsigned flags=0; exr_vector_rule rule=strchr(name,'*') ? EXR_VECTOR_EVENODD : EXR_VECTOR_NONZERO;
    if(count || r->inside) goto invalid;
    if((name[0]=='s' || name[0]=='b') && r->path.has_point && append_path(r,EXR_VECTOR_CLOSE,NULL,error)!=EXR_OK) return error->code;
    if(name[0]=='S' || name[0]=='s' || name[0]=='B' || name[0]=='b') flags|=EXR_PDF_STROKE;
    if(name[0]=='f' || name[0]=='F' || name[0]=='B' || name[0]=='b') flags|=EXR_PDF_FILL;
    return finish_path(r,flags,rule,error);
  }
  if(!strcmp(name,"m") || !strcmp(name,"l") || !strcmp(name,"c") || !strcmp(name,"v") || !strcmp(name,"y") || !strcmp(name,"h") || !strcmp(name,"re")) {
    expected=!strcmp(name,"h") ? 0 : !strcmp(name,"c") ? 6 : !strcmp(name,"re") || !strcmp(name,"v") || !strcmp(name,"y") ? 4 : 2;
    if(r->inside || count!=expected) goto invalid;
    for(i=0;i<count;i++) if(!numeric(arena,values[i],&numbers[i])) goto invalid;
    if(!strcmp(name,"h")) return append_path(r,EXR_VECTOR_CLOSE,NULL,error);
    if(!strcmp(name,"re")) {
      const double x[4]={numbers[0],numbers[0]+numbers[2],numbers[0]+numbers[2],numbers[0]},y[4]={numbers[1],numbers[1],numbers[1]+numbers[3],numbers[1]+numbers[3]};
      for(i=0;i<4;i++) { if(!world_point(r,x[i],y[i],&points[i])) goto limit; if(append_path(r,i ? EXR_VECTOR_LINE : EXR_VECTOR_MOVE,&points[i],error)!=EXR_OK) return error->code; }
      return append_path(r,EXR_VECTOR_CLOSE,NULL,error);
    }
    if(!strcmp(name,"m") || !strcmp(name,"l")) {
      if(!world_point(r,numbers[0],numbers[1],&points[0])) goto limit;
      verb=!strcmp(name,"m") ? EXR_VECTOR_MOVE : EXR_VECTOR_LINE; return append_path(r,verb,points,error);
    }
    if(!strcmp(name,"v")) {
      if(!r->path.has_point) goto invalid;
      points[0]=r->path.current;
      if(!world_point(r,numbers[0],numbers[1],&points[1]) || !world_point(r,numbers[2],numbers[3],&points[2])) goto limit;
    } else if(!strcmp(name,"y")) {
      if(!world_point(r,numbers[0],numbers[1],&points[0]) || !world_point(r,numbers[2],numbers[3],&points[2])) goto limit;
      points[1]=points[2];
    } else for(i=0;i<3;i++) if(!world_point(r,numbers[2*i],numbers[2*i+1],&points[i])) goto limit;
    return append_path(r,EXR_VECTOR_CUBIC,points,error);
  }
  if(!strcmp(name,"sh")) return exr_fail(error,EXR_FORMAT,"PDF shading is not implemented yet");
  *handled=0; return EXR_OK;
invalid:
  if(error->code!=EXR_OK) return error->code;
  return exr_fail(error,EXR_FORMAT,"Invalid PDF path, color or line-style operands");
limit:
  return exr_fail(error,EXR_LIMIT,"PDF path coordinate budget exceeded");
}
static exr_status content_operation(void *context,exr_pdf_file *arena,const char *name,const uint32_t *values,size_t count,exr_error *error);
static exr_status clip_bounds(content_reader *r,const double box[4],exr_error *error) {
  exr_vector_segment boundary[5]={0}; size_t i; const double x[4]={box[0],box[2],box[2],box[0]},y[4]={box[1],box[1],box[3],box[3]};
  for(i=0;i<4;i++) {
    boundary[i].verb=i ? EXR_VECTOR_LINE : EXR_VECTOR_MOVE;
    if(!world_point(r,x[i],y[i],&boundary[i].points[0])) return exr_fail(error,EXR_LIMIT,"PDF stream clip coordinates exceed budget");
  }
  boundary[4].verb=EXR_VECTOR_CLOSE;
  return path_event(r,boundary,5,EXR_PDF_CLIP,EXR_VECTOR_NONZERO,error);
}
/* Forms and Type3 CharProcs share one interpreter, recursion guard and work
   budget. A glyph may contain its own BT/ET while the caller stays inside BT. */
static exr_status stream_scope(content_reader *r,uint32_t id,uint32_t resources,const double ctm[6],const double *box,unsigned glyph,exr_error *error) {
  content_state saved=r->state; content_path saved_path; double saved_matrix[6],saved_line[6];
  uint32_t saved_resources=r->resources; size_t saved_floor=r->floor,saved_depth=r->depth,i,n;
  unsigned saved_inside=r->inside,saved_compatibility=r->compatibility,saved_type3=r->type3,saved_declared=r->declared,saved_uncolored=r->uncolored;
  const unsigned char *data; exr_status status;
  if(r->form_depth==32) return exr_fail(error,EXR_LIMIT,"PDF Form/Type3 stream depth exceeds 32");
  for(i=0;i<r->form_depth;i++) if(r->forms[i]==id) return exr_fail(error,EXR_FORMAT,"Cyclic PDF Form/Type3 stream invocation");
  if(exr_control_cancel(r->control,error)!=EXR_OK) return EXR_CANCELLED;
  if(exr_pdf_stream_data(r->file,id,&data,&n,error)!=EXR_OK) return error->code;
  status=event(r,EXR_PDF_SAVE,error); if(status!=EXR_OK) return status;
  memcpy(saved_matrix,r->matrix,sizeof(saved_matrix)); memcpy(saved_line,r->line,sizeof(saved_line)); saved_path=r->path;
  memcpy(r->state.ctm,ctm,sizeof(r->state.ctm)); if(resources!=EXR_PDF_NONE) r->resources=resources;
  memset(&r->path,0,sizeof(r->path)); r->floor=r->depth; r->inside=0; r->compatibility=0; r->type3=glyph; r->declared=0;
  identity(r->matrix); identity(r->line); r->forms[r->form_depth++]=id;
  if(r->graphics && box) status=clip_bounds(r,box,error);
  if(status==EXR_OK) status=exr_pdf_content_ops_resources(r->file,r->resources,data,n,content_operation,r,&r->inline_work,r->control,error);
  if(status==EXR_OK && glyph && !r->declared) status=exr_fail(error,EXR_FORMAT,"PDF Type3 CharProc requires d0 or d1 metrics");
  if(status==EXR_OK && (r->inside || r->depth!=saved_depth || r->compatibility)) status=exr_fail(error,EXR_FORMAT,"Unbalanced PDF Form/Type3 text/graphics state");
  if(status==EXR_OK && r->graphics && (r->path.count || r->path.pending_clip)) status=exr_fail(error,EXR_FORMAT,"Unterminated PDF Form/Type3 path object");
  /* Also balance consumer scopes on a failed stream, preserving its first
     error. A raster canvas may already be failed, but custom sinks can recover. */
  if(r->inside) { exr_error ignored={0}; (void)event(r,EXR_PDF_END_TEXT,&ignored); }
  for(i=r->depth;i>saved_depth;i--) { exr_error ignored={0}; (void)event(r,EXR_PDF_RESTORE,&ignored); }
  r->path_bytes-=r->path.capacity*sizeof(*r->path.segments); free(r->path.segments); r->path=saved_path;
  r->form_depth--; r->state=saved; r->resources=saved_resources; r->floor=saved_floor; r->depth=saved_depth;
  r->inside=saved_inside; r->compatibility=saved_compatibility; r->type3=saved_type3; r->declared=saved_declared; r->uncolored=saved_uncolored;
  memcpy(r->matrix,saved_matrix,sizeof(saved_matrix)); memcpy(r->line,saved_line,sizeof(saved_line));
  { exr_error restore_error={0}; exr_status restored=event(r,EXR_PDF_RESTORE,&restore_error);
    if(status==EXR_OK && restored!=EXR_OK) { status=restored; *error=restore_error; }
  }
  return status;
}
static exr_status form(content_reader *r,uint32_t id,exr_error *error) {
  double matrix[6],ctm[6],box[4]; uint32_t value,at,resources=EXR_PDF_NONE; size_t i; const exr_pdf_value *v;
  if(r->inside) return exr_fail(error,EXR_FORMAT,"PDF Form invoked inside a text object");
  v=exr_pdf_value_at(r->file,id);
  if(!v || v->kind!=EXR_PDF_STREAM) return exr_fail(error,EXR_FORMAT,"PDF Form is not a stream");
  if(resolved(r->file,exr_pdf_get(r->file,id,"FormType"),&value,error)!=EXR_OK) return error->code;
  if(value!=EXR_PDF_NONE && exr_pdf_value_at(r->file,value)->kind!=EXR_PDF_NULL) { v=exr_pdf_value_at(r->file,value); if(v->kind!=EXR_PDF_INT || v->u.integer!=1) goto invalid; }
  if(resolved(r->file,exr_pdf_get(r->file,id,"BBox"),&value,error)!=EXR_OK) return error->code;
  v=exr_pdf_value_at(r->file,value); if(!v || v->kind!=EXR_PDF_ARRAY) goto invalid;
  at=v->first;
  for(i=0;i<4;i++) {
    uint32_t number;
    if(at==EXR_PDF_NONE || resolved(r->file,at,&number,error)!=EXR_OK || !numeric(r->file,number,&box[i])) goto invalid;
    at=exr_pdf_value_at(r->file,at)->next;
  }
  if(at!=EXR_PDF_NONE || box[0]>box[2] || box[1]>box[3]) goto invalid;
  identity(matrix);
  if(resolved(r->file,exr_pdf_get(r->file,id,"Matrix"),&value,error)!=EXR_OK) return error->code;
  if(value!=EXR_PDF_NONE && exr_pdf_value_at(r->file,value)->kind!=EXR_PDF_NULL) {
    v=exr_pdf_value_at(r->file,value); if(v->kind!=EXR_PDF_ARRAY) goto invalid; at=v->first;
    for(i=0;i<6;i++) {
      uint32_t number;
      if(at==EXR_PDF_NONE || resolved(r->file,at,&number,error)!=EXR_OK || !numeric(r->file,number,&matrix[i])) goto invalid;
      at=exr_pdf_value_at(r->file,at)->next;
    }
    if(at!=EXR_PDF_NONE) goto invalid;
  }
  if(r->graphics) {
    if(resolved(r->file,exr_pdf_get(r->file,id,"Group"),&value,error)!=EXR_OK) return error->code;
    if(value!=EXR_PDF_NONE && exr_pdf_value_at(r->file,value)->kind!=EXR_PDF_NULL) return exr_fail(error,EXR_FORMAT,"PDF transparency groups are not implemented yet");
  }
  if(resolved(r->file,exr_pdf_get(r->file,id,"Resources"),&value,error)!=EXR_OK) return error->code;
  if(value!=EXR_PDF_NONE && exr_pdf_value_at(r->file,value)->kind!=EXR_PDF_NULL) {
    if(exr_pdf_value_at(r->file,value)->kind!=EXR_PDF_DICT) goto invalid;
    resources=value;
  }
  if(!multiply(ctm,r->state.ctm,matrix)) return exr_fail(error,EXR_LIMIT,"PDF Form transform exceeds coordinate budget");
  return stream_scope(r,id,resources,ctm,box,0,error);
invalid:
  if(error->code!=EXR_OK) return error->code;
  return exr_fail(error,EXR_FORMAT,"Invalid PDF Form type, bounding box, matrix or resources");
}
static exr_status type3(content_reader *r,const exr_pdf_text_glyph *glyph,exr_error *error) {
  uint32_t stream,resources; double matrix[6],ctm[6]; exr_status status;
  status=exr_pdf_font_type3(r->file,glyph->font,glyph->character.cid,&stream,&resources,matrix,error); if(status!=EXR_OK) return status;
  if(stream==EXR_PDF_NONE) return EXR_OK;
  if(!multiply(ctm,glyph->transform,matrix)) return exr_fail(error,EXR_LIMIT,"PDF Type3 glyph transform exceeds coordinate budget");
  return stream_scope(r,stream,resources,ctm,NULL,1,error);
}
static exr_status content_operation(void *context,exr_pdf_file *arena,const char *name,const uint32_t *values,size_t count,exr_error *error) {
  content_reader *r=context; double numbers[6]; size_t i; uint32_t id;
  if(++r->operations>1048576) return exr_fail(error,EXR_LIMIT,"PDF content/Form operation budget exceeded");
  if(!strcmp(name,"d0") || !strcmp(name,"d1")) {
    int uncolored=!strcmp(name,"d1");
    if(!r->type3 || r->declared || count!=(uncolored ? 6u : 2u)) goto invalid;
    for(i=0;i<count;i++) if(!numeric(arena,values[i],numbers+i)) goto invalid;
    if(numbers[1]!=0 || (uncolored && (numbers[2]>numbers[4] || numbers[3]>numbers[5]))) goto invalid;
    r->declared=1; if(uncolored) r->uncolored=1;
    return uncolored && r->graphics ? clip_bounds(r,numbers+2,error) : EXR_OK;
  }
  if(r->type3 && !r->declared) return exr_fail(error,EXR_FORMAT,"PDF Type3 CharProc must start with d0 or d1");
  if(r->uncolored) {
    const char *colors[]={"G","g","RG","rg","K","k","CS","cs","SC","sc","SCN","scn"};
    for(i=0;i<sizeof(colors)/sizeof(*colors);i++) if(!strcmp(name,colors[i])) return exr_fail(error,EXR_FORMAT,"Uncolored PDF Type3 CharProc cannot set colors");
  }
  if(r->graphics) {
    int handled; exr_status status=graphics_operation(r,arena,name,values,count,&handled,error);
    if(status!=EXR_OK || handled) return status;
  }
  if(!strcmp(name,"BI")) {
    exr_pdf_paint_state paint=paint_state(r);
    if(r->inside || count!=1 || exr_pdf_value_at(arena,values[0])->kind!=EXR_PDF_STREAM) goto invalid;
    if(r->uncolored) {
      const exr_pdf_value *mask=exr_pdf_value_at(arena,exr_pdf_get(arena,values[0],"ImageMask"));
      if(!mask || mask->kind!=EXR_PDF_BOOL || !mask->u.number) return exr_fail(error,EXR_FORMAT,"Uncolored PDF Type3 inline image must be a stencil mask");
    }
    return r->callbacks.image ? r->callbacks.image(r->context,arena,values[0],r->file,r->resources,&paint,error) : EXR_OK;
  }
  if(!strcmp(name,"q")) { if(count) goto invalid; if(r->depth==128) goto limit; r->stack[r->depth++]=r->state; return event(r,EXR_PDF_SAVE,error); }
  if(!strcmp(name,"Q")) { if(count || r->depth==r->floor) goto invalid; r->state=r->stack[--r->depth]; return event(r,EXR_PDF_RESTORE,error); }
  if(!strcmp(name,"BT")) { if(count || r->inside) goto invalid; r->inside=1; identity(r->matrix); identity(r->line); return event(r,EXR_PDF_BEGIN_TEXT,error); }
  if(!strcmp(name,"ET")) { if(count || !r->inside) goto invalid; r->inside=0; return event(r,EXR_PDF_END_TEXT,error); }
  if(!strcmp(name,"BX")) { if(count) goto invalid; if(r->compatibility==128) goto limit; r->compatibility++; return EXR_OK; }
  if(!strcmp(name,"EX")) { if(count || !r->compatibility) goto invalid; r->compatibility--; return EXR_OK; }
  if(!strcmp(name,"cm")) {
    if(count!=6) goto invalid;
    for(i=0;i<6;i++) if(!numeric(arena,values[i],&numbers[i])) goto invalid;
    if(!multiply(r->state.ctm,r->state.ctm,numbers)) goto limit;
    return EXR_OK;
  }
  if(!strcmp(name,"gs")) {
    uint32_t font,at,size_id; const exr_pdf_value *v; double size;
    if(count!=1 || resource(r,arena,values[0],"ExtGState",&id,error)!=EXR_OK) goto invalid;
    v=exr_pdf_value_at(r->file,id); if(!v || v->kind!=EXR_PDF_DICT) goto invalid;
    if(r->graphics && apply_ext_state(r,id,error)!=EXR_OK) return error->code;
    if(resolved(r->file,exr_pdf_get(r->file,id,"Font"),&font,error)!=EXR_OK) return error->code;
    if(font==EXR_PDF_NONE || exr_pdf_value_at(r->file,font)->kind==EXR_PDF_NULL) return EXR_OK;
    v=exr_pdf_value_at(r->file,font); if(v->kind!=EXR_PDF_ARRAY || (at=v->first)==EXR_PDF_NONE) goto invalid;
    size_id=exr_pdf_value_at(r->file,at)->next;
    if(size_id==EXR_PDF_NONE || exr_pdf_value_at(r->file,size_id)->next!=EXR_PDF_NONE ||
       resolved(r->file,at,&id,error)!=EXR_OK || resolved(r->file,size_id,&size_id,error)!=EXR_OK || !numeric(r->file,size_id,&size)) goto invalid;
    return select_font(r,id,size,error);
  }
  if(!strcmp(name,"Do")) {
    uint32_t subtype; size_t n; const unsigned char *type;
    if(r->inside || count!=1 || resource(r,arena,values[0],"XObject",&id,error)!=EXR_OK) goto invalid;
    if(resolved(r->file,exr_pdf_get(r->file,id,"Subtype"),&subtype,error)!=EXR_OK) return error->code;
    type=exr_pdf_bytes(r->file,subtype,&n);
    if(type && exr_pdf_value_at(r->file,subtype)->kind==EXR_PDF_NAME && n==5 && !memcmp(type,"Image",5)) {
      exr_pdf_paint_state paint=paint_state(r);
      if(r->graphics && exr_pdf_value_at(r->file,id)->kind!=EXR_PDF_STREAM) return exr_fail(error,EXR_FORMAT,"PDF Image XObject is not a stream");
      if(r->uncolored) {
        uint32_t mask; const exr_pdf_value *v;
        if(resolved(r->file,exr_pdf_get(r->file,id,"ImageMask"),&mask,error)!=EXR_OK) return error->code;
        v=exr_pdf_value_at(r->file,mask);
        if(!v || v->kind!=EXR_PDF_BOOL || !v->u.number) return exr_fail(error,EXR_FORMAT,"Uncolored PDF Type3 image must be a stencil mask");
      }
      return r->callbacks.image ? r->callbacks.image(r->context,r->file,id,r->file,r->resources,&paint,error) : EXR_OK;
    }
    if(type && exr_pdf_value_at(r->file,subtype)->kind==EXR_PDF_NAME && n==4 && !memcmp(type,"Form",4)) return form(r,id,error);
    return exr_fail(error,EXR_FORMAT,"Unsupported PDF text XObject subtype");
  }
  if(!strcmp(name,"Tf")) {
    if(!r->inside || count!=2 || !numeric(arena,values[1],&numbers[0])) goto invalid;
    if(resource(r,arena,values[0],"Font",&id,error)!=EXR_OK) return error->code;
    return select_font(r,id,numbers[0],error);
  }
  if(!strcmp(name,"Tj") || !strcmp(name,"'") || !strcmp(name,"\"")) {
    size_t expected=!strcmp(name,"\"") ? 3 : 1;
    if(!r->inside || count!=expected) goto invalid;
    if(expected==3) {
      if(!numeric(arena,values[0],&r->state.word_space) || !numeric(arena,values[1],&r->state.char_space)) goto invalid;
    }
    if(strcmp(name,"Tj") && !new_line(r,0,-r->state.leading)) goto limit;
    return show(r,arena,values[count-1],error);
  }
  if(!strcmp(name,"TJ")) {
    const exr_pdf_value *v; uint32_t at;
    if(!r->inside || count!=1 || !(v=exr_pdf_value_at(arena,values[0])) || v->kind!=EXR_PDF_ARRAY || !r->state.font) goto invalid;
    for(at=v->first;at!=EXR_PDF_NONE;at=exr_pdf_value_at(arena,at)->next) {
      if(numeric(arena,at,&numbers[0])) {
        int vertical=exr_pdf_font_description(r->state.font)->vertical;
        double move=-numbers[0]*r->state.size/1000;
        if(!translate(r->matrix,vertical ? 0 : move*r->state.scale,vertical ? move : 0)) goto limit;
      } else { exr_status status=show(r,arena,at,error); if(status!=EXR_OK) return status; }
    }
    return EXR_OK;
  }
  if(!strcmp(name,"Tm") || !strcmp(name,"Td") || !strcmp(name,"TD") || !strcmp(name,"T*")) {
    size_t expected=!strcmp(name,"Tm") ? 6 : !strcmp(name,"T*") ? 0 : 2;
    if(!r->inside || count!=expected) goto invalid;
    for(i=0;i<count;i++) if(!numeric(arena,values[i],&numbers[i])) goto invalid;
    if(expected==6) { memcpy(r->matrix,numbers,sizeof(numbers)); memcpy(r->line,numbers,sizeof(numbers)); }
    else {
      if(!strcmp(name,"TD")) r->state.leading=-numbers[1];
      if(!new_line(r,expected ? numbers[0] : 0,expected ? numbers[1] : -r->state.leading)) goto limit;
    }
    return EXR_OK;
  }
  if(!strcmp(name,"Tc") || !strcmp(name,"Tw") || !strcmp(name,"Tz") || !strcmp(name,"TL") || !strcmp(name,"Ts") || !strcmp(name,"Tr")) {
    if(!r->inside || count!=1 || !numeric(arena,values[0],&numbers[0])) goto invalid;
    if(!strcmp(name,"Tc")) r->state.char_space=numbers[0];
    else if(!strcmp(name,"Tw")) r->state.word_space=numbers[0];
    else if(!strcmp(name,"Tz")) r->state.scale=numbers[0]/100;
    else if(!strcmp(name,"TL")) r->state.leading=numbers[0];
    else if(!strcmp(name,"Ts")) r->state.rise=numbers[0];
    else { if(numbers[0]<0 || numbers[0]>7 || floor(numbers[0])!=numbers[0]) goto invalid; r->state.mode=(unsigned)numbers[0]; }
    return EXR_OK;
  }
  { const char *ignored[]={"m","l","c","v","y","h","re","S","s","f","F","f*","B","B*","b","b*","n","W","W*","w","J","j","M","d","ri","i","G","g","RG","rg","K","k","CS","cs","SC","sc","SCN","scn","sh","d0","d1","BMC","BDC","EMC","MP","DP"};
    for(i=0;i<sizeof(ignored)/sizeof(*ignored);i++) if(!strcmp(name,ignored[i])) return EXR_OK;
  }
  if(r->compatibility) return EXR_OK;
invalid:
  if(error->code!=EXR_OK) return error->code;
  return exr_fail(error,EXR_FORMAT,"Invalid or unsupported PDF content operator/operands");
limit:
  return exr_fail(error,EXR_LIMIT,"PDF content state or coordinate budget exceeded");
}
static exr_status walk_content(exr_pdf_file *file,uint32_t resources,const void *data,size_t size,
                                  const double initial[6],const exr_pdf_draw_callbacks *callbacks,unsigned graphics,void *context,
                                  const exr_control *control,exr_error *error) {
  content_reader *r; exr_error local={0}; exr_status status; size_t i;
  if(!file || !callbacks || (!callbacks->glyph && !callbacks->path && !callbacks->state && !callbacks->image) || (!data && size))
    return exr_fail(error,EXR_ARGUMENT,"Missing PDF content input or callbacks");
  if(initial) for(i=0;i<6;i++) if(!isfinite(initial[i]) || fabs(initial[i])>1e7) return exr_fail(error,EXR_ARGUMENT,"Invalid initial PDF drawing transform");
  r=calloc(1,sizeof(*r)); if(!r) return exr_fail(error,EXR_MEMORY,"PDF content state allocation failed");
  r->file=file; r->resources=resources; r->control=control; r->callbacks=*callbacks; r->context=context; r->state.scale=1; r->graphics=graphics;
  r->state.paint.fill.space=r->state.paint.stroke.space=EXR_PDF_DEVICE_GRAY; r->state.paint.fill.alpha=r->state.paint.stroke.alpha=1;
  r->state.paint.line=(exr_vector_stroke_style){1,10,EXR_VECTOR_BUTT,EXR_VECTOR_MITER};
  identity(r->state.ctm); if(initial) memcpy(r->state.ctm,initial,sizeof(r->state.ctm)); identity(r->matrix); identity(r->line);
  status=exr_pdf_content_ops_resources(r->file,r->resources,data,size,content_operation,r,&r->inline_work,control,&local);
  if(status==EXR_OK && (r->inside || r->depth || r->compatibility)) status=exr_fail(&local,EXR_FORMAT,"Unbalanced PDF text/graphics/compatibility state");
  if(status==EXR_OK && graphics && (r->path.count || r->path.pending_clip)) status=exr_fail(&local,EXR_FORMAT,"Unterminated PDF path object");
  for(i=0;i<r->font_count;i++) exr_pdf_font_close(r->fonts[i].font);
  for(i=0;i<r->color_count;i++) exr_pdf_colorspace_free(r->colors[i].space);
  while(r->profiles) { dash_profile *next=r->profiles->next; free(r->profiles); r->profiles=next; }
  free(r->path.segments); free(r); if(error) *error=local; return status;
}
exr_status exr_pdf_text_ops(exr_pdf_file *file,uint32_t resources,const void *data,size_t size,
                            exr_pdf_text_fn glyph,void *context,const exr_control *control,exr_error *error) {
  exr_pdf_draw_callbacks callbacks={0}; callbacks.glyph=glyph;
  if(!glyph) return exr_fail(error,EXR_ARGUMENT,"Missing PDF text callback");
  return walk_content(file,resources,data,size,NULL,&callbacks,0,context,control,error);
}
exr_status exr_pdf_draw_ops(exr_pdf_file *file,uint32_t resources,const void *data,size_t size,
                            const double initial[6],const exr_pdf_draw_callbacks *callbacks,void *context,
                            const exr_control *control,exr_error *error) {
  return walk_content(file,resources,data,size,initial,callbacks,1,context,control,error);
}
