/* SPDX-License-Identifier: GPL-3.0-only */
#include "variable_internal.h"
#include FT_MULTIPLE_MASTERS_H
static exr_status axes(const exr_font *font,size_t index,FT_MM_Var **out,exr_error *e) {
  FT_Error code; FT_UInt i,j; *out=NULL;
  if(!FT_HAS_MULTIPLE_MASTERS(font->faces[index].face)) return EXR_OK;
  code=FT_Get_MM_Var(font->faces[index].face,out);
  if(code) return exr_fail(e,code==FT_Err_Out_Of_Memory ? EXR_MEMORY : EXR_FONT,"Cannot read variable font axes");
  if(!(*out)->num_axis || (*out)->num_axis>64) { FT_Done_MM_Var(font->library,*out); *out=NULL; return exr_fail(e,EXR_LIMIT,"Variable font axes exceed 64"); }
  for(i=0;i<(*out)->num_axis;i++) {
    const FT_Var_Axis *a=&(*out)->axis[i];
    if(!a->tag || a->tag>UINT32_MAX || a->minimum<INT32_MIN || a->maximum>INT32_MAX || a->minimum>a->def || a->def>a->maximum) goto malformed;
    for(j=0;j<i;j++) if(a->tag==(*out)->axis[j].tag) goto malformed;
  }
  return EXR_OK;
malformed:
  FT_Done_MM_Var(font->library,*out); *out=NULL; return exr_fail(e,EXR_FONT,"Invalid or duplicate variable font axis");
}
exr_status exr_font_axes(const exr_font *font,size_t index,exr_font_axis **out,size_t *count,exr_error *e) {
  FT_MM_Var *var=NULL; FT_Fixed current[64]; FT_UInt i; exr_font_axis *result=NULL; exr_status status;
  if(out) *out=NULL;
  if(count) *count=0;
  if(!font || index>=font->count || !out || !count) return exr_fail(e,EXR_ARGUMENT,"Invalid font axes query");
  status=axes(font,index,&var,e); if(status!=EXR_OK) return status;
  if(!var) return exr_fail(e,EXR_OK,"");
  if(FT_Get_Var_Design_Coordinates(font->faces[index].face,var->num_axis,current)) { status=exr_fail(e,EXR_FONT,"Cannot read font instance coordinates"); goto done; }
  result=calloc(var->num_axis,sizeof(*result)); if(!result) { status=exr_fail(e,EXR_MEMORY,"Font axes snapshot allocation failed"); goto done; }
  for(i=0;i<var->num_axis;i++) {
    FT_UInt flags=0; const FT_Var_Axis *a=&var->axis[i];
    if(FT_Get_Var_Axis_Flags(var,i,&flags)) { status=exr_fail(e,EXR_FONT,"Cannot read font axis flags"); goto done; }
    result[i]=(exr_font_axis){(uint32_t)a->tag,(flags&FT_VAR_AXIS_FLAG_HIDDEN) ? EXR_FONT_AXIS_HIDDEN : 0,
      (double)a->minimum/65536,(double)a->def/65536,(double)a->maximum/65536,(double)current[i]/65536};
  }
  *out=result; result=NULL; *count=var->num_axis; status=exr_fail(e,EXR_OK,"");
done:
  free(result); FT_Done_MM_Var(font->library,var); return status;
}
exr_status exr_font_create_variable(const exr_font_input *inputs,size_t count,const exr_font_coordinate *coordinates,size_t coordinate_count,exr_font **out,exr_error *e) {
  exr_font *font=NULL; size_t i,j,face; exr_status status;
  if(out) *out=NULL;
  if(!out || (coordinate_count && !coordinates)) return exr_fail(e,EXR_ARGUMENT,"Invalid variable font creation input");
  if(coordinate_count>2048) return exr_fail(e,EXR_LIMIT,"Variable font coordinate list exceeds 2048");
  for(i=0;i<coordinate_count;i++) {
    if(coordinates[i].font_index>=count || !coordinates[i].tag || !isfinite(coordinates[i].value)) return exr_fail(e,EXR_ARGUMENT,"Invalid font coordinate");
    for(j=0;j<i;j++) if(coordinates[i].font_index==coordinates[j].font_index && coordinates[i].tag==coordinates[j].tag) return exr_fail(e,EXR_ARGUMENT,"Duplicate font axis coordinate");
  }
  status=exr_font_create(inputs,count,&font,e); if(status!=EXR_OK) return status;
  for(face=0;face<font->count && status==EXR_OK;face++) {
    FT_MM_Var *var=NULL; FT_Fixed values[64]; FT_UInt axis; int changed=0;
    for(i=0;i<coordinate_count;i++) if(coordinates[i].font_index==face) changed=1;
    status=axes(font,face,&var,e); if(status!=EXR_OK) break;
    if(!changed) { if(var) FT_Done_MM_Var(font->library,var); continue; }
    if(!var) { status=exr_fail(e,EXR_ARGUMENT,"Coordinates require a variable font face"); break; }
    if(FT_Get_Var_Design_Coordinates(font->faces[face].face,var->num_axis,values)) status=exr_fail(e,EXR_FONT,"Cannot read initial font coordinates");
    for(i=0;i<coordinate_count && status==EXR_OK;i++) if(coordinates[i].font_index==face) {
      const exr_font_coordinate *c=&coordinates[i];
      for(axis=0;axis<var->num_axis && var->axis[axis].tag!=c->tag;axis++) {}
      if(axis==var->num_axis) status=exr_fail(e,EXR_ARGUMENT,"Unknown variable font axis tag");
      else if(c->value<(double)var->axis[axis].minimum/65536 || c->value>(double)var->axis[axis].maximum/65536) status=exr_fail(e,EXR_ARGUMENT,"Font axis coordinate is outside its design range");
      else values[axis]=(FT_Fixed)llround(c->value*65536);
    }
    if(status==EXR_OK && FT_Set_Var_Design_Coordinates(font->faces[face].face,var->num_axis,values)) status=exr_fail(e,EXR_FONT,"Cannot select variable font coordinates");
    FT_Done_MM_Var(font->library,var);
  }
  if(status!=EXR_OK) { exr_font_free(font); return status; }
  *out=font; return exr_fail(e,EXR_OK,"");
}
exr_status exr_font_copy_variations(exr_font *to,size_t to_index,const exr_font *from,size_t from_index,exr_error *e) {
  FT_MM_Var *var=NULL; FT_Fixed values[64]; exr_status status=axes(from,from_index,&var,e);
  if(status!=EXR_OK || !var) return status;
  if(FT_Get_Var_Design_Coordinates(from->faces[from_index].face,var->num_axis,values) ||
     FT_Set_Var_Design_Coordinates(to->faces[to_index].face,var->num_axis,values)) status=exr_fail(e,EXR_FONT,"Cannot retain font variation coordinates");
  FT_Done_MM_Var(from->library,var); return status;
}
