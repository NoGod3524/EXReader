/* SPDX-License-Identifier: MIT */
#include "pixels_internal.h"
#include "vector_internal.h"
#include "icc_internal.h"
uint32_t exr_gray_color(uint32_t color) {
  double linear[3],gray;unsigned k,r=(color>>24)&255,g=(color>>16)&255,b=(color>>8)&255,l;
  if(r==g && g==b) return color;
  for(k=0;k<3;k++) { double c=((color>>(24-8*k))&255)/255.;linear[k]=c<=.04045 ? c/12.92 : pow((c+.055)/1.055,2.4); }
  gray=.2126*linear[0]+.7152*linear[1]+.0722*linear[2];
  gray=gray<=.0031308 ? 12.92*gray : 1.055*pow(gray,1/2.4)-.055;
  l=(unsigned)fmax(0,fmin(255,floor(gray*255+.5)));
  return (l<<24)|(l<<16)|(l<<8)|(color&255);
}
static double lum(const double c[3]) { return .3*c[0]+.59*c[1]+.11*c[2]; }
static double saturation(const double c[3]) { return fmax(c[0],fmax(c[1],c[2]))-fmin(c[0],fmin(c[1],c[2])); }
static void set_lum(double c[3],double l) {
  double d=l-lum(c),n,x;unsigned k;
  for(k=0;k<3;k++) c[k]+=d;
  n=fmin(c[0],fmin(c[1],c[2]));x=fmax(c[0],fmax(c[1],c[2]));
  if(n<0) for(k=0;k<3;k++) c[k]=l+(c[k]-l)*l/(l-n);
  if(x>1) for(k=0;k<3;k++) c[k]=l+(c[k]-l)*(1-l)/(x-l);
}
static void set_sat(double c[3],double s) {
  unsigned order[3]={0,1,2},i,j,t;
  for(i=0;i<2;i++) for(j=i+1;j<3;j++) if(c[order[i]]>c[order[j]]) { t=order[i];order[i]=order[j];order[j]=t; }
  if(c[order[2]]>c[order[0]]) {
    c[order[1]]=(c[order[1]]-c[order[0]])*s/(c[order[2]]-c[order[0]]);c[order[2]]=s;
  } else c[order[1]]=c[order[2]]=0;
  c[order[0]]=0;
}
static double component(double b,double s,exr_blend_mode mode) {
  switch(mode) {
  case EXR_BLEND_MULTIPLY:return b*s;
  case EXR_BLEND_SCREEN:return b+s-b*s;
  case EXR_BLEND_OVERLAY:return b<=.5 ? 2*b*s : 1-2*(1-b)*(1-s);
  case EXR_BLEND_DARKEN:return fmin(b,s);
  case EXR_BLEND_LIGHTEN:return fmax(b,s);
  case EXR_BLEND_COLOR_DODGE:return s==1 ? 1 : fmin(1,b/(1-s));
  case EXR_BLEND_COLOR_BURN:return s==0 ? 0 : 1-fmin(1,(1-b)/s);
  case EXR_BLEND_HARD_LIGHT:return s<=.5 ? 2*b*s : 1-2*(1-b)*(1-s);
  case EXR_BLEND_SOFT_LIGHT:return s<=.5 ? b-(1-2*s)*b*(1-b) : b+(2*s-1)*((b<=.25 ? ((16*b-12)*b+4)*b : sqrt(b))-b);
  case EXR_BLEND_DIFFERENCE:return fabs(b-s);
  case EXR_BLEND_EXCLUSION:return b+s-2*b*s;
  default:return s;
  }
}
static void blend_rgb(const double b[3],const double s[3],exr_blend_mode mode,double blend[3]) {
  unsigned k;
  if(mode>=EXR_BLEND_HUE) {
    memcpy(blend,mode==EXR_BLEND_SATURATION || mode==EXR_BLEND_LUMINOSITY ? b : s,3*sizeof(*blend));
    if(mode==EXR_BLEND_HUE) set_sat(blend,saturation(b));
    if(mode==EXR_BLEND_SATURATION) set_sat(blend,saturation(s));
    set_lum(blend,mode==EXR_BLEND_LUMINOSITY ? lum(s) : lum(b));
  } else for(k=0;k<3;k++) blend[k]=component(b[k],s[k],mode);
}
/* A region-sized buffer is addressed with local coordinates; the origin maps a
   local coordinate back to the parent canvas when the backdrop is consulted. */
static size_t buffer_index(const exr_composite_state *state,size_t width,size_t x,size_t y) {
  (void)state;
  return (size_t)y*width + (size_t)x;
}
/* fmax(0,fmin(255,floor(fmax(0,fmin(1,v))*255+.5))) without libm calls.
   fmin(1,NaN) is 1; the clamped product plus .5 lies in [.5,255.5], where
   truncation is floor and the outer clamp is the identity. */
static inline unsigned char unit_byte(double v) {
  double c=v<0 ? 0 : v<1 ? v : 1;
  return (unsigned char)(int)(c*255+.5);
}
static void read_rgba(const exr_bitmap *b,const exr_composite_state *state,size_t x,size_t y,double out[4]) {
  unsigned k;
  if(state && state->pixels) {
    const float *p=state->pixels+buffer_index(state,b->width,x,y)*5;
    if(p[4]>0) for(k=0;k<4;k++) out[k]=p[k];
    else if(state->isolated || state->backdrop_transparent) for(k=0;k<4;k++) out[k]=0;
    else read_rgba(&state->backdrop,state->backdrop_state,x+(size_t)state->origin_x,y+(size_t)state->origin_y,out);
  }
  else {
    const unsigned char *p=b->pixels+y*b->stride+x*b->channels;out[3]=b->channels==1 ? 1 : p[3]/255.;
    for(k=0;k<3;k++) out[k]=p[b->channels==1 ? 0 : k]/255.*out[3];
  }
}
/* The group's initial backdrop: transparent for isolated groups, otherwise the
   parent bitmap (or its precision state) captured when the group began. */
static void read_backdrop(const exr_composite_state *state,size_t x,size_t y,double out[4]) {
  unsigned k;
  if(state->isolated || state->backdrop_transparent) { for(k=0;k<4;k++) out[k]=0; return; }
  read_rgba(&state->backdrop,state->backdrop_state,x+(size_t)state->origin_x,y+(size_t)state->origin_y,out);
}
static void over_rgba(const double back[4],const double source[3],double alpha,exr_blend_mode mode,double out[4]) {
  double b[3],blend[3];unsigned k;
  for(k=0;k<3;k++) b[k]=back[3]>0 ? back[k]/back[3] : 0;
  blend_rgb(b,source,mode,blend);out[3]=alpha+back[3]*(1-alpha);
  for(k=0;k<3;k++) out[k]=(1-alpha)*back[k]+alpha*((1-back[3])*source[k]+back[3]*blend[k]);
}
static void write_rgba(exr_bitmap *b,exr_composite_state *state,size_t x,size_t y,const double out[4],double object_alpha,double shape) {
  unsigned char *p=b->pixels+y*b->stride+x*b->channels;unsigned k;double a=fmax(0,fmin(1,out[3]));
  if(state && state->pixels) {
    float *q=state->pixels+buffer_index(state,b->width,x,y)*5;for(k=0;k<3;k++) q[k]=(float)fmax(0,fmin(a,out[k]));q[3]=(float)a;
    q[4]=(float)fmax(0,fmin(1,object_alpha+(1-(state->knockout ? shape : object_alpha))*q[4]));
    if(state->shape) { float *f=state->shape+buffer_index(state,b->width,x,y);*f=(float)fmax(0,fmin(1,shape+(1-shape)*(*f))); }
    if(object_alpha>0 || (shape>0 && state->shape)) {
      if(x<state->left) state->left=(uint32_t)x;
      if(y<state->top) state->top=(uint32_t)y;
      if(x>=state->right) state->right=(uint32_t)x+1;
      if(y>=state->bottom) state->bottom=(uint32_t)y+1;
    }
  }
  if(b->channels==1) p[0]=a>0 ? (unsigned char)fmax(0,fmin(255,floor((77*out[0]+150*out[1]+29*out[2])*255/(256*a)+.5))) : 0;
  else {
    for(k=0;k<3;k++) p[k]=a>0 ? (unsigned char)fmax(0,fmin(255,floor(out[k]*255/a+.5))) : 0;
    p[3]=(unsigned char)floor(a*255+.5);
  }
}
/* DeviceCMYK working buffers keep [C M Y K A object] floats per pixel with the
   four colour components premultiplied, using the same device model as page
   painting. The RGBA state stays in sync as a preview for group commits. */
static size_t cmyk_index(const exr_bitmap *b,size_t x,size_t y) { return (size_t)y*b->width+(size_t)x; }
void exr_cmyk_from_rgb(const double rgb[3],double cmyk[4]) {
  unsigned k;cmyk[3]=fmax(0,fmin(1,1-fmax(rgb[0],fmax(rgb[1],rgb[2]))));
  for(k=0;k<3;k++) cmyk[k]=fmax(0,fmin(1,1-rgb[k]-cmyk[3]));
}
static void read_cmyk(const exr_bitmap *b,const exr_composite_state *state,size_t x,size_t y,double out[5]);
static void read_cmyk_backdrop(const exr_composite_state *state,size_t x,size_t y,double out[5]) {
  unsigned k;
  if(state->isolated || state->backdrop_transparent) { memset(out,0,5*sizeof(*out));return; }
  if(state->backdrop_state && state->backdrop_state->cmyk_pixels) {
    read_cmyk(&state->backdrop,state->backdrop_state,x+(size_t)state->origin_x,y+(size_t)state->origin_y,out);return;
  }
  { double back[4],rgb[3],cmyk[4];
    read_rgba(&state->backdrop,state->backdrop_state,x+(size_t)state->origin_x,y+(size_t)state->origin_y,back);
    for(k=0;k<3;k++) rgb[k]=back[3]>0 ? back[k]/back[3] : 0;
    exr_device_cmyk_from_rgb(state->cmyk_profile,rgb,cmyk);for(k=0;k<4;k++) out[k]=cmyk[k]*back[3];out[4]=back[3];
  }
}
static void read_cmyk(const exr_bitmap *b,const exr_composite_state *state,size_t x,size_t y,double out[5]) {
  const float *p=state->cmyk_pixels+cmyk_index(b,x,y)*6;unsigned k;
  if(p[5]>0) { for(k=0;k<5;k++) out[k]=p[k]; }
  else read_cmyk_backdrop(state,x,y,out);
}
static void over_cmyk(const double back[5],const double source[4],double alpha,exr_blend_mode mode,double out[5]) {
  double b[4],blend[4];unsigned k;
  for(k=0;k<4;k++) b[k]=back[4]>0 ? back[k]/back[4] : 0;
  /* ISO 32000-1 11.3.5: blend subtractive components in additive form.
     Nonseparable CMY uses the RGB formulas; K is selected independently. */
  if(mode>=EXR_BLEND_HUE) {
    double brgb[3],srgb[3],rgb[3];
    for(k=0;k<3;k++) { brgb[k]=1-b[k];srgb[k]=1-source[k]; }
    blend_rgb(brgb,srgb,mode,rgb);for(k=0;k<3;k++) blend[k]=1-rgb[k];
    blend[3]=mode==EXR_BLEND_LUMINOSITY ? source[3] : b[3];
  } else for(k=0;k<4;k++) blend[k]=1-component(1-b[k],1-source[k],mode);
  out[4]=alpha+back[4]*(1-alpha);
  for(k=0;k<4;k++) out[k]=(1-alpha)*back[k]+alpha*((1-back[4])*source[k]+back[4]*blend[k]);
}
static void write_cmyk(exr_bitmap *b,exr_composite_state *state,size_t x,size_t y,const double out[5],double object_alpha,double shape) {
  float *q=state->cmyk_pixels+cmyk_index(b,x,y)*6;unsigned char *p=b->pixels+y*b->stride+x*b->channels;
  double a=fmax(0,fmin(1,out[4])),cmyk[4],rgb[3];unsigned k;
  for(k=0;k<5;k++) q[k]=(float)fmax(0,fmin(1,out[k]));
  q[5]=(float)fmax(0,fmin(1,object_alpha+(1-(state->knockout ? shape : object_alpha))*q[5]));
  if(state->shape) { float *f=state->shape+cmyk_index(b,x,y);*f=(float)fmax(0,fmin(1,shape+(1-shape)*(*f))); }
  if(object_alpha>0 || (shape>0 && state->shape)) {
    if(x<state->left) state->left=(uint32_t)x;
    if(y<state->top) state->top=(uint32_t)y;
    if(x>=state->right) state->right=(uint32_t)x+1;
    if(y>=state->bottom) state->bottom=(uint32_t)y+1;
  }
  for(k=0;k<4;k++) cmyk[k]=a>0 ? out[k]/a : 0;
  exr_device_cmyk_rgb(state->cmyk_profile,cmyk,rgb,1);
  if(state->pixels) {
    float *v=state->pixels+cmyk_index(b,x,y)*5;
    for(k=0;k<3;k++) v[k]=(float)(rgb[k]*a);
    v[3]=(float)a;v[4]=q[5];
  }
  for(k=0;k<3;k++) p[k]=(unsigned char)fmax(0,fmin(255,floor(rgb[k]*255+.5)));
  p[3]=(unsigned char)floor(a*255+.5);
}
void exr_pixel_alpha_shape(const exr_composite_state *state,size_t x,size_t y,double alpha,double shape,
                           double constant,unsigned coverage,double *out_alpha,double *out_shape) {
  double mask=1,clip=coverage/255.;
  if(state && state->soft_mask) mask=x<state->soft_mask_width && y<state->soft_mask_height ?
    state->soft_mask[y*state->soft_mask_width+x]/255. : 0;
  *out_alpha=alpha*constant*mask*clip;
  *out_shape=shape*clip*(state && (state->alpha_flags&EXR_ALPHA_CONSTANT_SHAPE) ? constant*mask : 1);
}
void exr_pixel_object_cmyk(exr_bitmap *bitmap,int x,int y,const double source[4],double alpha,double shape,
                            exr_blend_mode mode,exr_composite_state *state) {
  double back[5],out[5];unsigned k;
  if(!shape || (!alpha && !(state && (state->knockout || state->shape)))) return;
  if(!state || !state->cmyk_pixels) {
    double rgb[3];uint32_t color=0;
    exr_device_cmyk_rgb(state ? state->cmyk_profile : NULL,source,rgb,1);
    for(k=0;k<3;k++) color|=(uint32_t)fmin(255,floor(rgb[k]*255+.5))<<(24-8*k);
    exr_pixel_object(bitmap,x,y,color,alpha,shape,mode,state);return;
  }
  if(state->knockout) {
    double base[5],painted[5],current[5];
    read_cmyk_backdrop(state,(size_t)x,(size_t)y,base);over_cmyk(base,source,alpha/shape,mode,painted);
    read_cmyk(bitmap,state,(size_t)x,(size_t)y,current);
    for(k=0;k<5;k++) out[k]=shape*painted[k]+(1-shape)*current[k];
  } else { read_cmyk(bitmap,state,(size_t)x,(size_t)y,back);over_cmyk(back,source,alpha,mode,out); }
  write_cmyk(bitmap,state,(size_t)x,(size_t)y,out,alpha,shape);
}
void exr_pixel_object(exr_bitmap *bitmap,int x,int y,uint32_t color,double alpha,double shape,
                       exr_blend_mode mode,exr_composite_state *state) {
  double back[4],source[3],out[4];unsigned k;
  if(!shape || (!alpha && !(state && (state->knockout || state->shape)))) return;
  if(state && state->gray) color=exr_gray_color(color);
  if(!state || (!state->pixels && !state->cmyk_pixels)) {
    color=(color&0xffffff00u)|(unsigned)fmin(255,floor(alpha*255+.5));exr_pixel_blend(bitmap,x,y,color,255,mode);return;
  }
  for(k=0;k<3;k++) source[k]=((color>>(24-8*k))&255)/255.;
  if(state->cmyk_pixels) {
    double cmyk[4];exr_device_cmyk_from_rgb(state->cmyk_profile,source,cmyk);
    exr_pixel_object_cmyk(bitmap,x,y,cmyk,alpha,shape,mode,state);return;
  }
  if(!state->knockout && mode==EXR_BLEND_NORMAL && alpha==1 && shape==1 && !state->shape && bitmap->channels==4) {
    float *q=state->pixels+buffer_index(state,bitmap->width,(size_t)x,(size_t)y)*5;
    unsigned char *p=bitmap->pixels+(size_t)y*bitmap->stride+(size_t)x*4;
    for(k=0;k<3;k++) { q[k]=(float)source[k];p[k]=(unsigned char)(color>>(24-8*k)); }
    q[3]=q[4]=1.0f;p[3]=255;
    if((size_t)x<state->left) state->left=(uint32_t)x;
    if((size_t)y<state->top) state->top=(uint32_t)y;
    if((size_t)x>=state->right) state->right=(uint32_t)x+1;
    if((size_t)y>=state->bottom) state->bottom=(uint32_t)y+1;
    return;
  }
  if(state->knockout) {
    double base[4],painted[4],current[4];
    read_backdrop(state,(size_t)x,(size_t)y,base);over_rgba(base,source,alpha/shape,mode,painted);
    read_rgba(bitmap,state,(size_t)x,(size_t)y,current);
    for(k=0;k<4;k++) out[k]=shape*painted[k]+(1-shape)*current[k];
  } else { read_rgba(bitmap,state,(size_t)x,(size_t)y,back);over_rgba(back,source,alpha,mode,out); }
  write_rgba(bitmap,state,(size_t)x,(size_t)y,out,alpha,shape);
}
void exr_pixel_composite_cmyk(exr_bitmap *bitmap,int x,int y,const double cmyk[4],double alpha,unsigned coverage,
                              exr_blend_mode mode,exr_composite_state *state) {
  double source[4],object_alpha,shape;unsigned k;
  if(!state || !state->cmyk_pixels) {
    double rgb[3];uint32_t color=0;
    exr_device_cmyk_rgb(state ? state->cmyk_profile : NULL,cmyk,rgb,1);
    for(k=0;k<3;k++) color|=(uint32_t)fmin(255,floor(rgb[k]*255+.5))<<(24-8*k);
    color|=(uint32_t)fmin(255,floor(alpha*255+.5));exr_pixel_composite(bitmap,x,y,color,coverage,mode,state);return;
  }
  exr_pixel_alpha_shape(state,(size_t)x,(size_t)y,1,1,alpha,coverage,&object_alpha,&shape);
  for(k=0;k<4;k++) source[k]=fmax(0,fmin(1,cmyk[k]));
  exr_pixel_object_cmyk(bitmap,x,y,source,object_alpha,shape,mode,state);
}
void exr_pixel_composite(exr_bitmap *bitmap,int x,int y,uint32_t color,unsigned coverage,exr_blend_mode mode,exr_composite_state *state) {
  double alpha,shape;
  if(!state || (!state->pixels && !state->cmyk_pixels)) {
    if(state && state->gray) color=exr_gray_color(color);
    if(state && state->soft_mask) {
      size_t mx=(size_t)x,my=(size_t)y;unsigned mask=mx<state->soft_mask_width && my<state->soft_mask_height ? state->soft_mask[my*state->soft_mask_width+mx] : 0;
      coverage=(coverage*mask+127)/255;
    }
    exr_pixel_blend(bitmap,x,y,color,coverage,mode);return;
  }
  exr_pixel_alpha_shape(state,(size_t)x,(size_t)y,1,1,(color&255)/255.,coverage,&alpha,&shape);
  exr_pixel_object(bitmap,x,y,color,alpha,shape,mode,state);
}
exr_status exr_composite_initialize(exr_bitmap *child,exr_composite_state *state,const exr_bitmap *parent,
  const exr_composite_state *parent_state,int origin_x,int origin_y,size_t *work,const exr_control *control,exr_error *e) {
  size_t y,x;
  state->backdrop=*parent;state->backdrop_state=parent_state;state->depth=parent_state ? parent_state->depth+1 : 1;
  state->left=child->width;state->top=child->height;
  state->origin_x=origin_x;state->origin_y=origin_y;
  if(state->backdrop_transparent) return exr_control_cancel(control,e);
  for(y=0;y<child->height;y++) {
    size_t py=y+(size_t)origin_y;
    if(exr_control_cancel(control,e)!=EXR_OK) return EXR_CANCELLED;
    if(!exr_vector_work(work,child->width)) return exr_fail(e,EXR_LIMIT,"Group backdrop copy exceeds work budget");
    if(parent->channels==4) memcpy(child->pixels+y*child->stride,parent->pixels+py*parent->stride+(size_t)origin_x*4,child->width*4);
    else for(x=0;x<child->width;x++) { unsigned char *p=child->pixels+y*child->stride+x*4;p[0]=p[1]=p[2]=parent->pixels[py*parent->stride+(size_t)origin_x+x];p[3]=255; }
  }
  return EXR_OK;
}
void exr_pixel_blend(exr_bitmap *bitmap,int x,int y,uint32_t color,unsigned coverage,exr_blend_mode mode) {
  unsigned alpha=(color&255)*coverage/255,k;double b[3],s[3],blend[3],out[3],ab,as,a;
  unsigned char *p;
  if(mode==EXR_BLEND_NORMAL) { exr_pixel(bitmap,x,y,color,coverage);return; }
  if(!alpha) return;
  p=bitmap->pixels+(size_t)y*bitmap->stride+(size_t)x*bitmap->channels;
  ab=bitmap->channels==1 ? 1 : p[3]/255.;as=alpha/255.;a=as+ab*(1-as);
  for(k=0;k<3;k++) { b[k]=p[bitmap->channels==1 ? 0 : k]/255.;s[k]=((color>>(24-8*k))&255)/255.; }
  blend_rgb(b,s,mode,blend);
  for(k=0;k<3;k++) out[k]=fmax(0,fmin(255,255*((1-as)*ab*b[k]+as*((1-ab)*s[k]+ab*blend[k]))/a));
  if(bitmap->channels==1) p[0]=(unsigned char)floor((77*out[0]+150*out[1]+29*out[2])/256+.5);
  else { for(k=0;k<3;k++) p[k]=(unsigned char)floor(out[k]+.5);p[3]=(unsigned char)floor(a*255+.5); }
}

exr_status exr_bitmap_to_gray(exr_bitmap *b,const exr_control *control,exr_error *e) {
  unsigned char *gray;size_t y,x;
  if(!b || b->channels!=4 || !b->pixels) return exr_fail(e,EXR_ARGUMENT,"Missing owned RGB bitmap");
  gray=malloc((size_t)b->width*b->height);if(!gray) return exr_fail(e,EXR_MEMORY,"Gray output allocation failed");
  for(y=0;y<b->height;y++) {
    if(exr_control_cancel(control,e)!=EXR_OK) { free(gray);return EXR_CANCELLED; }
    for(x=0;x<b->width;x++) { const unsigned char *p=b->pixels+y*b->stride+x*4;gray[y*b->width+x]=(unsigned char)((77*p[0]+150*p[1]+29*p[2]+128)>>8); }
  }
  free(b->pixels);b->pixels=gray;b->channels=1;b->stride=b->width;return EXR_OK;
}

static exr_status frame_cmyk(exr_bitmap *target,const exr_bitmap *source,double opacity,exr_blend_mode mode,
  const exr_clip_mask *clip,exr_composite_state *target_state,const exr_composite_state *source_state,
  int origin_x,int origin_y,size_t *work,const exr_control *control,exr_error *e) {
  size_t y,x,left=source_state->left,top=source_state->top,right=source_state->right,bottom=source_state->bottom;
  unsigned cost=mode==EXR_BLEND_NORMAL ? 1 : mode<EXR_BLEND_HUE ? 24 : 64;
  int dst_cmyk=target_state && target_state->cmyk_pixels;
  if(exr_control_cancel(control,e)!=EXR_OK) return EXR_CANCELLED;
  for(y=top;y<bottom;y++) {
    size_t ty=y+(size_t)origin_y;
    const unsigned char *clip_row=exr_clip_row(clip,ty);
    if(exr_control_cancel(control,e)!=EXR_OK) return EXR_CANCELLED;
    if(!exr_vector_work(work,(right>left ? right-left : 0)*(size_t)(cost+64))) return exr_fail(e,EXR_LIMIT,"Layer composite work budget exceeded");
    for(x=left;x<right;x++) {
      size_t tx=x+(size_t)origin_x;
      const float *q=source_state->cmyk_pixels+((size_t)y*source->width+x)*6;
      double covered=clip_row ? clip_row[tx]/255. : 1,base_alpha,alpha,src[4],back[5],out[5],obj;
      double shape=source_state->shape ? source_state->shape[y*source->width+x] : 1,object_opacity=opacity;unsigned k;
      if(target_state && target_state->soft_mask) object_opacity*=
        tx<target_state->soft_mask_width && ty<target_state->soft_mask_height ? target_state->soft_mask[ty*target_state->soft_mask_width+tx]/255. : 0;
      if(target_state && (target_state->alpha_flags&EXR_ALPHA_CONSTANT_SHAPE)) shape*=object_opacity;
      if(!covered || !shape) continue;
      if(!object_opacity && !(target_state && (target_state->knockout || target_state->shape))) continue;
      if(source_state->isolated) {
        base_alpha=q[4]*object_opacity;
        if(base_alpha<=0 && !(target_state && (target_state->knockout || target_state->shape))) continue;
        for(k=0;k<4;k++) src[k]=q[4]>0 ? fmax(0,fmin(1,q[k]/q[4])) : 0;
      } else {
        obj=q[5];if(obj<=0 && !(target_state && (target_state->knockout || target_state->shape))) continue;
        read_cmyk_backdrop(source_state,x,y,back);
        for(k=0;k<4;k++) src[k]=obj>0 ? fmax(0,fmin(1,(q[k]-(1-obj)*back[k])/obj)) : 0;
        base_alpha=obj*object_opacity;
      }
      alpha=base_alpha*covered;
      if(dst_cmyk) {
        if(target_state->knockout) {
          double base[5],painted[5],current[5];unsigned c;
          read_cmyk_backdrop(target_state,tx,ty,base);
          read_cmyk(target,target_state,tx,ty,current);
          over_cmyk(base,src,base_alpha/shape,mode,painted);
          for(c=0;c<5;c++) out[c]=covered*shape*painted[c]+(1-covered*shape)*current[c];
          write_cmyk(target,target_state,tx,ty,out,base_alpha*covered,covered*shape);
        } else {
          read_cmyk(target,target_state,tx,ty,back);
          over_cmyk(back,src,alpha,mode,out);
          write_cmyk(target,target_state,tx,ty,out,alpha,covered*shape);
        }
      } else {
        double rgb[3];exr_device_cmyk_rgb(source_state->cmyk_profile,src,rgb,1);
        if(target_state && target_state->knockout) {
          double base[4],painted[4],current[4];unsigned c;
          read_backdrop(target_state,tx,ty,base);read_rgba(target,target_state,tx,ty,current);
          over_rgba(base,rgb,base_alpha/shape,mode,painted);
          for(c=0;c<4;c++) out[c]=covered*shape*painted[c]+(1-covered*shape)*current[c];
          write_rgba(target,target_state,tx,ty,out,base_alpha*covered,covered*shape);
        } else {
          double rgba[4];read_rgba(target,target_state,tx,ty,rgba);
          over_rgba(rgba,rgb,alpha,mode,out);
          write_rgba(target,target_state,tx,ty,out,alpha,covered*shape);
        }
      }
    }
  }
  return EXR_OK;
}
exr_status exr_composite_frame(exr_bitmap *target,const exr_bitmap *source,double opacity,exr_blend_mode mode,
  const exr_clip_mask *clip,exr_composite_state *target_state,const exr_composite_state *source_state,
  const exr_layer_damage *damage,int origin_x,int origin_y,size_t *work,const exr_control *control,exr_error *e) {
  size_t y,x,left=0,top=0,right=source->width,bottom=source->height;unsigned cost=mode==EXR_BLEND_NORMAL ? 1 : mode<EXR_BLEND_HUE ? 24 : 64;
  const uint16_t *solid=clip && clip->solid_is_rect ? clip->solid_rect : NULL;
  const unsigned char *previous_mask=NULL;
  unsigned covered=255;
  int plain=opacity==1 && mode==EXR_BLEND_NORMAL && source->channels==4 && target->channels==4 &&
    (!target_state || (!target_state->pixels && !target_state->soft_mask && !target_state->shape &&
      !target_state->knockout && !target_state->gray && !target_state->cmyk_pixels)) &&
    (!source_state || (!source_state->cmyk_pixels && !source_state->shape && (!source_state->pixels || source_state->isolated)));
  if(source_state && source_state->cmyk_pixels)
    return frame_cmyk(target,source,opacity,mode,clip,target_state,source_state,origin_x,origin_y,work,control,e);
  if(exr_control_cancel(control,e)!=EXR_OK) return EXR_CANCELLED;
  if(source_state) { left=source_state->left;top=source_state->top;right=source_state->right;bottom=source_state->bottom; }
  for(y=top;y<bottom;y++) {
    size_t ty=y+(size_t)origin_y;
    const unsigned char *clip_row=exr_clip_row(clip,ty);
    if(exr_control_cancel(control,e)!=EXR_OK) return EXR_CANCELLED;
    if(!exr_vector_work(work,right-left)) return exr_fail(e,EXR_LIMIT,"Layer composite work budget exceeded");
    if(plain) {
      size_t first=left,last=right;
      if(damage && damage->band_height) {
        size_t band=y/damage->band_height;
        if(first<damage->bands[band].left) first=damage->bands[band].left;
        if(last>damage->bands[band].right) last=damage->bands[band].right;
        if(first>=last) continue;
      }
      if(solid) {
        covered=(ty>=solid[1] && ty<solid[3] &&
                 first+(size_t)origin_x>=solid[0] && last+(size_t)origin_x<=solid[2]) ? 255 : 0;
      } else {
        const unsigned char *mask=clip_row ? clip_row+(size_t)origin_x : NULL;
        if(mask!=previous_mask) {
          covered=255;
          for(x=left;mask && x<right;x++) covered&=mask[x];
          previous_mask=mask;
        }
      }
      /* Reserve the maximum blend charge. Near the limit, retain the generic
         loop's partial-row writes and exact failure point. */
      if(covered==255 && exr_vector_work(work,last-first)) {
        const unsigned char *p=source->pixels+y*source->stride+first*4;
        unsigned char *q=target->pixels+ty*target->stride+(first+(size_t)origin_x)*4;
        /* Classify a block while it is hot. Transparent blocks only refund
           the reserved work. Opaque blocks replace any backdrop in one copy. */
        for(x=first;x<last;) {
          size_t n=last-x<32 ? last-x : 32;
          unsigned any=0,all=255;
          for(size_t i=0;i<n;i++) { any|=p[4*i+3]; all&=p[4*i+3]; }
          if(!any) *work-=n;
          else if(all==255) memcpy(q,p,n*4);
          else for(size_t i=0;i<n;i++) {
            const unsigned char *src=p+4*i;
            if(!src[3]) (*work)--;
            else if(src[3]==255) memcpy(q+4*i,src,4);
            else {
              uint32_t color=((uint32_t)src[0]<<24)|((uint32_t)src[1]<<16)|((uint32_t)src[2]<<8)|src[3];
              exr_pixel(target,(int)(x+i+(size_t)origin_x),(int)ty,color,255);
            }
          }
          p+=4*n; q+=4*n; x+=n;
        }
        continue;
      }
    }
    for(x=left;x<right;x++) {
      size_t tx=x+(size_t)origin_x;
      unsigned char gray_pixel[4];const unsigned char *p=source->pixels+y*source->stride+x*4;
      unsigned a,coverage=clip_row ? clip_row[tx] : 255;uint32_t color;
      double shape=source_state && source_state->shape ? source_state->shape[y*source->width+x] : 1,object_opacity=opacity;
      if(target_state && target_state->soft_mask) {
        unsigned mask=tx<target_state->soft_mask_width && ty<target_state->soft_mask_height ? target_state->soft_mask[ty*target_state->soft_mask_width+tx] : 0;
        object_opacity*=mask/255.;
      }
      if(target_state && (target_state->alpha_flags&EXR_ALPHA_CONSTANT_SHAPE)) shape*=object_opacity;
      a=plain ? p[3] : (unsigned)floor(p[3]*object_opacity+.5);
      if(!coverage || !shape) continue;
      if(target_state && target_state->cmyk_pixels) {
        /* An isolated RGB child converts only its finished colour, preserving
           the parent's inks and blending the group opacity in the parent space. */
        double rgb[3],inks[4],out[5],alpha=p[3]/255.*object_opacity,covered=coverage/255.;unsigned k;
        if(!alpha && !(target_state->knockout || target_state->shape)) continue;
        if(!exr_vector_work(work,cost+96)) return exr_fail(e,EXR_LIMIT,"RGB to CMYK group commit exceeds work budget");
        for(k=0;k<3;k++) rgb[k]=p[k]/255.;
        exr_device_cmyk_from_rgb(target_state->cmyk_profile,rgb,inks);
        if(target_state->knockout) {
          double base[5],painted[5],current[5];
          read_cmyk_backdrop(target_state,tx,ty,base);read_cmyk(target,target_state,tx,ty,current);
          over_cmyk(base,inks,alpha/shape,mode,painted);
          for(k=0;k<5;k++) out[k]=covered*shape*painted[k]+(1-covered*shape)*current[k];
          write_cmyk(target,target_state,tx,ty,out,alpha*covered,covered*shape);
        } else {
          double back[5];read_cmyk(target,target_state,tx,ty,back);
          over_cmyk(back,inks,alpha*covered,mode,out);write_cmyk(target,target_state,tx,ty,out,alpha*covered,covered*shape);
        }
        continue;
      }
      if(target_state && target_state->gray) {
        color=exr_gray_color(((uint32_t)p[0]<<24)|((uint32_t)p[1]<<16)|((uint32_t)p[2]<<8)|p[3]);
        gray_pixel[0]=gray_pixel[1]=gray_pixel[2]=(unsigned char)(color>>24);gray_pixel[3]=p[3];p=gray_pixel;
      }
      if(target_state && target_state->knockout) {
        /* A group nested in a knockout group is one element: it composites with the
           knockout group's initial backdrop and replaces the accumulated result. */
        double base[4],painted[4],current[4],out[4],rgb[3],alpha=(p[3]/255.)*object_opacity,covered=coverage/255.;unsigned k;
        read_backdrop(target_state,tx,ty,base);read_rgba(target,target_state,tx,ty,current);
        if(source_state && source_state->pixels && !source_state->isolated) {
          const float *q=source_state->pixels+(y*source->width+x)*5;double initial[4],ag=q[4];
          read_backdrop(source_state,x,y,initial);
          for(k=0;k<3;k++) rgb[k]=ag>0 ? fmax(0,fmin(1,(q[k]-(1-ag)*initial[k])/ag)) : 0;
          alpha=ag*object_opacity;
        } else for(k=0;k<3;k++) rgb[k]=p[k]/255.;
        over_rgba(base,rgb,alpha/shape,mode,painted);
        for(k=0;k<4;k++) out[k]=covered*shape*painted[k]+(1-covered*shape)*current[k];
        write_rgba(target,target_state,tx,ty,out,alpha*covered,covered*shape);
        continue;
      }
      if((source_state && source_state->pixels && !source_state->isolated) || (target_state && target_state->pixels)) {
        double back[4],rgb[3],out[4],ag=p[3]/255.;unsigned k;
        const float *q=source_state && source_state->pixels && !source_state->isolated ? source_state->pixels+(y*source->width+x)*5 : NULL;
        if(q) ag=q[4];
        if((!ag || !object_opacity) && !(target_state && target_state->shape)) continue;
        if(!exr_vector_work(work,cost+32+(target_state ? target_state->depth*4 : 0))) return exr_fail(e,EXR_LIMIT,"Group backdrop removal exceeds work budget");
        if(q && ag==1 && object_opacity==1 && coverage==255 && mode==EXR_BLEND_NORMAL && !target_state && target->channels==4) {
          unsigned char *dst=target->pixels+ty*target->stride+tx*4;
          const unsigned char *mask=clip_row ? clip_row+(size_t)origin_x : NULL;
          const unsigned char rgba[4]={unit_byte(q[0]),unit_byte(q[1]),unit_byte(q[2]),255};
          const float *next=q+5;
          size_t end=x+1;
          /* Opaque spans from an aligned shading share the same RGB. Keep
             the float-to-byte conversion and work charge of the first pixel. */
          while(end<right && (!mask || mask[end]==255) && next[4]==1 &&
                next[0]==q[0] && next[1]==q[1] && next[2]==q[2]) {
            end++;next+=5;
          }
          if(!exr_vector_work(work,(end-x-1)*(cost+32))) {
            /* The first pixel is already paid. Keep exactly the writable prefix. */
            memcpy(dst,rgba,4);
            while(++x<end && exr_vector_work(work,cost+32)) { dst+=4;memcpy(dst,rgba,4); }
            return exr_fail(e,EXR_LIMIT,"Group backdrop removal exceeds work budget");
          }
          for(;x<end;x++,dst+=4) memcpy(dst,rgba,4);
          x--;continue;
        }
        read_rgba(target,target_state,tx,ty,back);
        { double initial[4];if(q && ag<1) read_backdrop(source_state,x,y,initial);
          for(k=0;k<3;k++) rgb[k]=q ? (ag>=1 ? fmax(0,fmin(1,(double)q[k])) : (ag>0 ? fmax(0,fmin(1,(q[k]-(1-ag)*initial[k])/ag)) : 0)) : p[k]/255.; }
        ag*=object_opacity*coverage/255.;over_rgba(back,rgb,ag,mode,out);write_rgba(target,target_state,tx,ty,out,ag,shape*coverage/255.);continue;
      }
      if(!a) continue;
      if(!exr_vector_work(work,cost)) return exr_fail(e,EXR_LIMIT,"Layer blend work budget exceeded");
      color=((uint32_t)p[0]<<24)|((uint32_t)p[1]<<16)|((uint32_t)p[2]<<8)|a;
      if(mode==EXR_BLEND_NORMAL) exr_pixel(target,(int)tx,(int)ty,color,coverage);else exr_pixel_blend(target,(int)tx,(int)ty,color,coverage,mode);
    }
  }
  return EXR_OK;
}

/* ISO 32000-1 11.6.2: fill+stroke form one transparency element. Each
   visible subobject sees the original backdrop; visible stroke shape replaces
   fill. A zero-opacity stroke does not hide a visible fill. An entirely
   zero-opacity element still has shape when a knockout/shape parent needs it.
   Clip covers the resulting element once. Pixels where both coverages are zero
   are left untouched, so only the coverage bounds are scanned; the skipped rows
   are still charged so the work budget matches a full-canvas scan. */
static exr_status compound_scan(const exr_bitmap *target,const uint32_t bounds[4],size_t *y0,size_t *y1,size_t *x0,size_t *x1,
  size_t *work,const exr_control *control,exr_error *e) {
  *x0=bounds[0];*y0=bounds[1];*x1=bounds[2]<target->width ? bounds[2] : target->width;*y1=bounds[3]<target->height ? bounds[3] : target->height;
  if(*x0>=*x1 || *y0>=*y1) *x0=*x1=*y0=*y1=0;
  if(exr_control_cancel(control,e)!=EXR_OK) return EXR_CANCELLED;
  if(!exr_vector_work(work,(size_t)target->width*(target->height-(*y1-*y0)))) return exr_fail(e,EXR_LIMIT,"Compound path scan exceeds budget");
  return EXR_OK;
}
static inline unsigned char clamp_round_u8(double v) {
  double r=v+0.5;
  return r<=0.0 ? 0 : r>=255.0 ? 255 : (unsigned char)(unsigned)r;
}
exr_status exr_composite_compound_at(exr_bitmap *target,const exr_bitmap *fill,const exr_bitmap *stroke,uint32_t mask_x,uint32_t mask_y,
  const uint32_t bounds[4],uint32_t fill_color,uint32_t stroke_color,exr_blend_mode mode,const exr_clip_mask *clip,exr_composite_state *state,
  size_t *work,const exr_control *control,exr_error *e) {
  size_t y,x,y0,y1,x0,x1;unsigned cost=mode==EXR_BLEND_NORMAL ? 12 : mode<EXR_BLEND_HUE ? 60 : 140;
  int opaque=mode==EXR_BLEND_NORMAL && !state && target->channels==4 && ((fill_color&stroke_color)&255)==255;
  const unsigned char fill_rgba[4]={(unsigned char)(fill_color>>24),(unsigned char)(fill_color>>16),(unsigned char)(fill_color>>8),255};
  const unsigned char stroke_rgba[4]={(unsigned char)(stroke_color>>24),(unsigned char)(stroke_color>>16),(unsigned char)(stroke_color>>8),255};
  uint32_t fill_px,stroke_px;
  double fr_d=fill_rgba[0],fg_d=fill_rgba[1],fb_d=fill_rgba[2],sr_d=stroke_rgba[0],sg_d=stroke_rgba[1],sb_d=stroke_rgba[2];
  exr_status status=compound_scan(target,bounds,&y0,&y1,&x0,&x1,work,control,e);
  memcpy(&fill_px,fill_rgba,4); memcpy(&stroke_px,stroke_rgba,4);
  if(status!=EXR_OK) return status;
  for(y=y0;y<y1;y++) {
    const unsigned char *fill_row=fill->pixels+(y-mask_y)*fill->stride+(x0-mask_x);
    const unsigned char *stroke_row=stroke->pixels+(y-mask_y)*stroke->stride+(x0-mask_x);
    const unsigned char *clip_row=exr_clip_row(clip,y);
    size_t w=x1-x0,row_budget;
    int solid_spans;
    if(clip_row) clip_row+=x0;
    if(exr_control_cancel(control,e)!=EXR_OK) return EXR_CANCELLED;
    if(!exr_vector_work(work,target->width)) return exr_fail(e,EXR_LIMIT,"Compound path scan exceeds budget");
    /* Near the limit, keep the original pixel-by-pixel failure point. */
    row_budget=*work;
    solid_spans=opaque && exr_vector_work(&row_budget,w*cost);
    if(solid_spans && !clip_row) {
      unsigned char *dst_row=target->pixels+y*target->stride+x0*4;
      for(size_t i=0;i<w;) {
        unsigned fv=fill_row[i],sv=stroke_row[i];
        if(!(fv|sv)) {
          i++;
          while(i+8<=w) {
            uint64_t fw64,sw64;
            memcpy(&fw64,fill_row+i,8); memcpy(&sw64,stroke_row+i,8);
            if(fw64|sw64) break;
            i+=8;
          }
          continue;
        }
        if(sv==255) {
          size_t end=i+1;
          while(end+8<=w) {
            uint64_t sw64; memcpy(&sw64,stroke_row+end,8);
            if(sw64!=UINT64_MAX) break;
            end+=8;
          }
          while(end<w && stroke_row[end]==255) end++;
          exr_vector_work(work,(end-i)*cost);
          unsigned char *pixel=dst_row+i*4;
          size_t n=end-i;
          for(size_t k=0;k<n;k++) memcpy(pixel+k*4,&stroke_px,4);
          i=end; continue;
        }
        if(fv==255 && !sv) {
          size_t end=i+1;
          while(end+8<=w) {
            uint64_t fw64,sw64;
            memcpy(&fw64,fill_row+end,8); memcpy(&sw64,stroke_row+end,8);
            if(fw64!=UINT64_MAX || sw64!=0) break;
            end+=8;
          }
          while(end<w && fill_row[end]==255 && !stroke_row[end]) end++;
          exr_vector_work(work,(end-i)*cost);
          unsigned char *pixel=dst_row+i*4;
          size_t n=end-i;
          for(size_t k=0;k<n;k++) memcpy(pixel+k*4,&fill_px,4);
          i=end; continue;
        }
        /* Opaque normal-blend AA pixel with exact same double formula as below. */
        exr_vector_work(work,cost);
        {
          unsigned char *p=dst_row+i*4;
          double f=fv/255.,s=sv/255.,fw=f*(1-s),sw=s,bw=1-fw-sw;
          if(p[3]==255) {
            double a=fw+sw+bw;
            p[0]=clamp_round_u8((fw*fr_d+sw*sr_d+bw*p[0])/a);
            p[1]=clamp_round_u8((fw*fg_d+sw*sg_d+bw*p[1])/a);
            p[2]=clamp_round_u8((fw*fb_d+sw*sb_d+bw*p[2])/a);
            p[3]=clamp_round_u8(a*255);
          } else {
            double ba=p[3]/255.,a=fw+sw+bw*ba;
            p[0]=a>0 ? clamp_round_u8((fw*fr_d+sw*sr_d+bw*ba*p[0])/a) : 0;
            p[1]=a>0 ? clamp_round_u8((fw*fg_d+sw*sg_d+bw*ba*p[1])/a) : 0;
            p[2]=a>0 ? clamp_round_u8((fw*fb_d+sw*sb_d+bw*ba*p[2])/a) : 0;
            p[3]=clamp_round_u8(a*255);
          }
        }
        i++;
      }
      continue;
    }
    if(solid_spans) {
      unsigned char *dst_row=target->pixels+y*target->stride+x0*4;
      for(size_t i=0;i<w;) {
        unsigned fv=fill_row[i],sv=stroke_row[i],kv=clip_row[i];
        if(!kv || !(fv|sv)) { i++; continue; }
        if(kv==255 && (sv==255 || (fv==255 && !sv))) {
          size_t end=i+1;
          uint32_t px=sv==255 ? stroke_px : fill_px;
          if(sv==255) while(end<w && stroke_row[end]==255 && clip_row[end]==255) end++;
          else while(end<w && fill_row[end]==255 && !stroke_row[end] && clip_row[end]==255) end++;
          exr_vector_work(work,(end-i)*cost);
          unsigned char *pixel=dst_row+i*4;
          size_t n=end-i;
          for(size_t k=0;k<n;k++) memcpy(pixel+k*4,&px,4);
          i=end; continue;
        }
        exr_vector_work(work,cost);
        {
          unsigned char *p=dst_row+i*4;
          double f=fv/255.,s=sv/255.,k=kv/255.,fw=f*(1-s)*k,sw=s*k,bw=1-fw-sw;
          if(p[3]==255) {
            double a=fw+sw+bw;
            p[0]=clamp_round_u8((fw*fr_d+sw*sr_d+bw*p[0])/a);
            p[1]=clamp_round_u8((fw*fg_d+sw*sg_d+bw*p[1])/a);
            p[2]=clamp_round_u8((fw*fb_d+sw*sb_d+bw*p[2])/a);
            p[3]=clamp_round_u8(a*255);
          } else {
            double ba=p[3]/255.,a=fw+sw+bw*ba;
            p[0]=a>0 ? clamp_round_u8((fw*fr_d+sw*sr_d+bw*ba*p[0])/a) : 0;
            p[1]=a>0 ? clamp_round_u8((fw*fg_d+sw*sg_d+bw*ba*p[1])/a) : 0;
            p[2]=a>0 ? clamp_round_u8((fw*fb_d+sw*sb_d+bw*ba*p[2])/a) : 0;
            p[3]=clamp_round_u8(a*255);
          }
        }
        i++;
      }
      continue;
    }
    for(size_t i=0;i<w;i++) {
      x=x0+i;
      unsigned char *p=target->pixels+y*target->stride+x*target->channels,fp[4]={0},sp[4]={0};
      double f=fill_row[i]/255.,s=stroke_row[i]/255.,k=clip_row ? clip_row[i]/255. : 1;
      double fw,sw,bw,fa,sa,ba,a,m=1;unsigned channel;
      exr_bitmap first={1,1,target->channels,fp,target->channels},second={1,1,target->channels,sp,target->channels};
      if((fill_color&255) || (stroke_color&255) || !(state && (state->knockout || state->shape))) {
        if(!(fill_color&255)) f=0;
        if(!(stroke_color&255)) s=0;
      }
      fw=f*(1-s)*k;sw=s*k;bw=1-fw-sw;
      if((!f && !s) || !k) continue;
      if(!exr_vector_work(work,cost+(state ? 64+state->depth*4 : 0))) return exr_fail(e,EXR_LIMIT,"Compound path blend exceeds budget");
      if(state && state->soft_mask) {
        m=((size_t)x<state->soft_mask_width && (size_t)y<state->soft_mask_height) ?
          state->soft_mask[(size_t)y*state->soft_mask_width+(size_t)x]/255. : 0;
        if(!m && (!(state->knockout || state->shape) || (state->alpha_flags&EXR_ALPHA_CONSTANT_SHAPE))) continue;
      }
      if(state && (state->pixels || (state->alpha_flags&EXR_ALPHA_CONSTANT_SHAPE))) {
        double back[4],base[4],fc[3],sc[3],fr[4],sr[4],out[4],af=(fill_color&255)/255.,as=(stroke_color&255)/255.;
        double opacity_mask=m,shape_mask=1;
        if(state->alpha_flags&EXR_ALPHA_CONSTANT_SHAPE) {
          f*=af;s*=as;af=as=1;opacity_mask=1;shape_mask=m;
          fw=f*(1-s)*k;sw=s*k;bw=1-fw-sw;
        }
        read_rgba(target,state,x,y,back);
        /* A knockout group treats fill+stroke as one element over the initial backdrop. */
        if(state->knockout) read_backdrop(state,x,y,base);else memcpy(base,back,sizeof(base));
        for(channel=0;channel<3;channel++) { fc[channel]=((fill_color>>(24-8*channel))&255)/255.;sc[channel]=((stroke_color>>(24-8*channel))&255)/255.; }
        over_rgba(base,fc,af*opacity_mask,mode,fr);over_rgba(base,sc,as*opacity_mask,mode,sr);
        for(channel=0;channel<4;channel++) out[channel]=shape_mask*(fw*fr[channel]+sw*sr[channel])+(shape_mask*bw+(1-shape_mask))*back[channel];
        write_rgba(target,state,x,y,out,shape_mask*opacity_mask*(fw*af+sw*as),shape_mask*(fw+sw));continue;
      }
      memcpy(fp,p,target->channels);memcpy(sp,p,target->channels);
      exr_pixel_blend(&first,0,0,fill_color,255,mode);exr_pixel_blend(&second,0,0,stroke_color,255,mode);
      if(target->channels==1) { p[0]=(unsigned char)floor(m*(fw*fp[0]+sw*sp[0])+(m*bw+(1-m))*p[0]+.5);continue; }
      fa=fp[3]/255.;sa=sp[3]/255.;ba=p[3]/255.;a=m*(fw*fa+sw*sa)+(m*bw+(1-m))*ba;
      for(channel=0;channel<3;channel++) p[channel]=a>0 ? (unsigned char)fmin(255,floor((m*fw*fa*fp[channel]+m*sw*sa*sp[channel]+(m*bw+(1-m))*ba*p[channel])/a+.5)) : 0;
      p[3]=(unsigned char)fmin(255,floor(a*255+.5));
    }
  }
  return EXR_OK;
}
exr_status exr_composite_compound(exr_bitmap *target,const exr_bitmap *fill,const exr_bitmap *stroke,const uint32_t bounds[4],
  uint32_t fill_color,uint32_t stroke_color,exr_blend_mode mode,const exr_clip_mask *clip,exr_composite_state *state,
  size_t *work,const exr_control *control,exr_error *e) {
  return exr_composite_compound_at(target,fill,stroke,0,0,bounds,fill_color,stroke_color,mode,clip,state,work,control,e);
}
exr_status exr_composite_compound_cmyk_at(exr_bitmap *target,const exr_bitmap *fill,const exr_bitmap *stroke,uint32_t mask_x,uint32_t mask_y,
  const uint32_t bounds[4],const double fill_cmyk[4],const double stroke_cmyk[4],double fill_alpha,double stroke_alpha,exr_blend_mode mode,
  const exr_clip_mask *clip,exr_composite_state *state,size_t *work,const exr_control *control,exr_error *e) {
  size_t y,x,y0,y1,x0,x1;unsigned cost=mode==EXR_BLEND_NORMAL ? 12 : mode<EXR_BLEND_HUE ? 60 : 140;exr_status status;
  if(!state || !state->cmyk_pixels) {
    double rf[3],rs[3];uint32_t fc=0,sc=0;unsigned c;
    exr_device_cmyk_rgb(state ? state->cmyk_profile : NULL,fill_cmyk,rf,1);exr_device_cmyk_rgb(state ? state->cmyk_profile : NULL,stroke_cmyk,rs,1);
    for(c=0;c<3;c++) { fc|=(uint32_t)fmin(255,floor(rf[c]*255+.5))<<(24-8*c);sc|=(uint32_t)fmin(255,floor(rs[c]*255+.5))<<(24-8*c); }
    return exr_composite_compound_at(target,fill,stroke,mask_x,mask_y,bounds,fc|(uint32_t)fmin(255,floor(fill_alpha*255+.5)),
      sc|(uint32_t)fmin(255,floor(stroke_alpha*255+.5)),mode,clip,state,work,control,e);
  }
  status=compound_scan(target,bounds,&y0,&y1,&x0,&x1,work,control,e);
  if(status!=EXR_OK) return status;
  for(y=y0;y<y1;y++) {
    const unsigned char *fill_row=fill->pixels+(y-mask_y)*fill->stride+(x0-mask_x);
    const unsigned char *stroke_row=stroke->pixels+(y-mask_y)*stroke->stride+(x0-mask_x);
    if(exr_control_cancel(control,e)!=EXR_OK) return EXR_CANCELLED;
    if(!exr_vector_work(work,target->width)) return exr_fail(e,EXR_LIMIT,"Compound path scan exceeds budget");
    const unsigned char *clip_row=exr_clip_row(clip,y);
    for(size_t i=0;i<x1-x0;i++) {
      x=x0+i;
      double f=fill_row[i]/255.,s=stroke_row[i]/255.,k=clip_row ? clip_row[x]/255. : 1;
      double fw,sw,bw,m=1,back[5],base[5],fr[5],sr[5],out[5],af=fill_alpha,as=stroke_alpha,opacity_mask,shape_mask=1;unsigned c;
      if(fill_alpha>0 || stroke_alpha>0 || !(state->knockout || state->shape)) {
        if(fill_alpha<=0) f=0;
        if(stroke_alpha<=0) s=0;
      }
      fw=f*(1-s)*k;sw=s*k;bw=1-fw-sw;
      if((!f && !s) || !k) continue;
      if(!exr_vector_work(work,cost+64+(size_t)state->depth*4)) return exr_fail(e,EXR_LIMIT,"Compound path blend exceeds budget");
      if(state->soft_mask) {
        m=((size_t)x<state->soft_mask_width && (size_t)y<state->soft_mask_height) ?
          state->soft_mask[(size_t)y*state->soft_mask_width+(size_t)x]/255. : 0;
        if(!m && (!(state->knockout || state->shape) || (state->alpha_flags&EXR_ALPHA_CONSTANT_SHAPE))) continue;
      }
      opacity_mask=m;
      if(state->alpha_flags&EXR_ALPHA_CONSTANT_SHAPE) {
        f*=af;s*=as;af=as=1;opacity_mask=1;shape_mask=m;
        fw=f*(1-s)*k;sw=s*k;bw=1-fw-sw;
      }
      read_cmyk(target,state,x,y,back);
      if(state->knockout) {
        read_cmyk_backdrop(state,x,y,base);
      } else memcpy(base,back,sizeof(base));
      over_cmyk(base,fill_cmyk,af*opacity_mask,mode,fr);
      over_cmyk(base,stroke_cmyk,as*opacity_mask,mode,sr);
      for(c=0;c<5;c++) out[c]=shape_mask*(fw*fr[c]+sw*sr[c])+(shape_mask*bw+(1-shape_mask))*back[c];
      write_cmyk(target,state,x,y,out,shape_mask*opacity_mask*(fw*af+sw*as),shape_mask*(fw+sw));
    }
  }
  return EXR_OK;
}
exr_status exr_composite_compound_cmyk(exr_bitmap *target,const exr_bitmap *fill,const exr_bitmap *stroke,const uint32_t bounds[4],
  const double fill_cmyk[4],const double stroke_cmyk[4],double fill_alpha,double stroke_alpha,exr_blend_mode mode,
  const exr_clip_mask *clip,exr_composite_state *state,size_t *work,const exr_control *control,exr_error *e) {
  return exr_composite_compound_cmyk_at(target,fill,stroke,0,0,bounds,fill_cmyk,stroke_cmyk,fill_alpha,stroke_alpha,mode,clip,state,work,control,e);
}
