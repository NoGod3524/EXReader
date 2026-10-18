/* SPDX-License-Identifier: GPL-3.0-only */
#include "pixels_internal.h"
#include "vector_internal.h"
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
static void read_rgba(const exr_bitmap *b,const exr_composite_state *state,size_t x,size_t y,double out[4]) {
  unsigned k;
  if(state && state->pixels) {
    const float *p=state->pixels+(y*b->width+x)*5;
    if(p[4]>0) for(k=0;k<4;k++) out[k]=p[k];
    else if(state->isolated) for(k=0;k<4;k++) out[k]=0;
    else read_rgba(&state->backdrop,state->backdrop_state,x,y,out);
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
  if(state->isolated) { for(k=0;k<4;k++) out[k]=0; return; }
  read_rgba(&state->backdrop,state->backdrop_state,x,y,out);
}
static void over_rgba(const double back[4],const double source[3],double alpha,exr_blend_mode mode,double out[4]) {
  double b[3],blend[3];unsigned k;
  for(k=0;k<3;k++) b[k]=back[3]>0 ? back[k]/back[3] : 0;
  blend_rgb(b,source,mode,blend);out[3]=alpha+back[3]*(1-alpha);
  for(k=0;k<3;k++) out[k]=(1-alpha)*back[k]+alpha*((1-back[3])*source[k]+back[3]*blend[k]);
}
static void write_rgba(exr_bitmap *b,exr_composite_state *state,size_t x,size_t y,const double out[4],double object_alpha) {
  unsigned char *p=b->pixels+y*b->stride+x*b->channels;unsigned k;double a=fmax(0,fmin(1,out[3]));
  if(state && state->pixels) {
    float *q=state->pixels+(y*b->width+x)*5;for(k=0;k<3;k++) q[k]=(float)fmax(0,fmin(a,out[k]));q[3]=(float)a;
    q[4]=(float)fmax(0,fmin(1,object_alpha+(1-object_alpha)*q[4]));
    if(object_alpha>0) {
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
void exr_pixel_composite(exr_bitmap *bitmap,int x,int y,uint32_t color,unsigned coverage,exr_blend_mode mode,exr_composite_state *state) {
  double back[4],source[3],out[4],alpha;unsigned k;
  if(!state || !state->pixels) { exr_pixel_blend(bitmap,x,y,color,coverage,mode);return; }
  alpha=(color&255)/255.*coverage/255.;if(!alpha) return;
  for(k=0;k<3;k++) source[k]=((color>>(24-8*k))&255)/255.;
  if(state->knockout) {
    /* ISO 32000-1 11.4.5: the element composites with the initial backdrop and
       replaces the accumulated result inside its geometric coverage. Constant
       alpha and coverage stay separate, otherwise edges decay twice. */
    double base[4],painted[4],current[4],constant=(color&255)/255.,covered=coverage/255.;
    read_backdrop(state,(size_t)x,(size_t)y,base);
    over_rgba(base,source,constant,mode,painted);
    read_rgba(bitmap,state,(size_t)x,(size_t)y,current);
    for(k=0;k<4;k++) out[k]=covered*painted[k]+(1-covered)*current[k];
    write_rgba(bitmap,state,(size_t)x,(size_t)y,out,alpha);
    /* Knockout replaces coverage as well: the group alpha follows the top element
       instead of accumulating, so background removal divides by the result alpha. */
    if(state->pixels) state->pixels[((size_t)y*bitmap->width+(size_t)x)*5+4]=(float)fmax(0,fmin(1,out[3]));
    return;
  }
  read_rgba(bitmap,state,(size_t)x,(size_t)y,back);
  over_rgba(back,source,alpha,mode,out);write_rgba(bitmap,state,(size_t)x,(size_t)y,out,alpha);
}
exr_status exr_composite_initialize(exr_bitmap *child,exr_composite_state *state,const exr_bitmap *parent,
  const exr_composite_state *parent_state,size_t *work,const exr_control *control,exr_error *e) {
  size_t y,x;
  state->backdrop=*parent;state->backdrop_state=parent_state;state->depth=parent_state ? parent_state->depth+1 : 1;
  state->left=parent->width;state->top=parent->height;
  for(y=0;y<parent->height;y++) {
    if(exr_control_cancel(control,e)!=EXR_OK) return EXR_CANCELLED;
    if(!exr_vector_work(work,parent->width)) return exr_fail(e,EXR_LIMIT,"Group backdrop copy exceeds work budget");
    if(parent->channels==4) memcpy(child->pixels+y*child->stride,parent->pixels+y*parent->stride,(size_t)parent->width*4);
    else for(x=0;x<parent->width;x++) { unsigned char *p=child->pixels+y*child->stride+x*4;p[0]=p[1]=p[2]=parent->pixels[y*parent->stride+x];p[3]=255; }
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

exr_status exr_composite_frame(exr_bitmap *target,const exr_bitmap *source,double opacity,exr_blend_mode mode,
  const exr_bitmap *clip,exr_composite_state *target_state,const exr_composite_state *source_state,
  size_t *work,const exr_control *control,exr_error *e) {
  size_t y,x,left=0,top=0,right=source->width,bottom=source->height;unsigned cost=mode==EXR_BLEND_NORMAL ? 1 : mode<EXR_BLEND_HUE ? 24 : 64;
  if(exr_control_cancel(control,e)!=EXR_OK) return EXR_CANCELLED;
  if(source_state) { left=source_state->left;top=source_state->top;right=source_state->right;bottom=source_state->bottom; }
  for(y=top;y<bottom;y++) {
    if(exr_control_cancel(control,e)!=EXR_OK) return EXR_CANCELLED;
    if(!exr_vector_work(work,right-left)) return exr_fail(e,EXR_LIMIT,"Layer composite work budget exceeded");
    for(x=left;x<right;x++) {
      const unsigned char *p=source->pixels+y*source->stride+x*4;unsigned a=(unsigned)floor(p[3]*opacity+.5),coverage=clip ? clip->pixels[y*clip->stride+x] : 255;uint32_t color;
      if(!coverage) continue;
      if((source_state && source_state->pixels && !source_state->isolated) || (target_state && target_state->pixels)) {
        double back[4],rgb[3],out[4],ag=p[3]/255.;unsigned k;
        const float *q=source_state && source_state->pixels && !source_state->isolated ? source_state->pixels+(y*source->width+x)*5 : NULL;
        if(q) ag=q[4];
        if(!ag || !opacity) continue;
        if(!exr_vector_work(work,cost+32+(target_state ? target_state->depth*4 : 0))) return exr_fail(e,EXR_LIMIT,"Group backdrop removal exceeds work budget");
        read_rgba(target,target_state,x,y,back);
        for(k=0;k<3;k++) rgb[k]=q ? fmax(0,fmin(1,(q[k]-(1-ag)*back[k])/ag)) : p[k]/255.;
        ag*=opacity*coverage/255.;over_rgba(back,rgb,ag,mode,out);write_rgba(target,target_state,x,y,out,ag);continue;
      }
      if(!a) continue;
      if(!exr_vector_work(work,cost)) return exr_fail(e,EXR_LIMIT,"Layer blend work budget exceeded");
      color=((uint32_t)p[0]<<24)|((uint32_t)p[1]<<16)|((uint32_t)p[2]<<8)|a;
      if(mode==EXR_BLEND_NORMAL) exr_pixel(target,(int)x,(int)y,color,coverage);else exr_pixel_blend(target,(int)x,(int)y,color,coverage,mode);
    }
  }
  return EXR_OK;
}

/* ISO 32000-1 11.6.2: fill+stroke form one transparency element. Each
   visible subobject sees the original backdrop; visible stroke shape replaces
   fill. Zero-opacity strokes do not mark the element (MuPDF/PDFium behavior).
   Clip covers the resulting element once. */
exr_status exr_composite_compound(exr_bitmap *target,const exr_bitmap *fill,const exr_bitmap *stroke,
  uint32_t fill_color,uint32_t stroke_color,exr_blend_mode mode,const exr_bitmap *clip,exr_composite_state *state,
  size_t *work,const exr_control *control,exr_error *e) {
  size_t y,x;unsigned cost=mode==EXR_BLEND_NORMAL ? 12 : mode<EXR_BLEND_HUE ? 60 : 140;
  for(y=0;y<target->height;y++) {
    if(exr_control_cancel(control,e)!=EXR_OK) return EXR_CANCELLED;
    if(!exr_vector_work(work,target->width)) return exr_fail(e,EXR_LIMIT,"Compound path scan exceeds budget");
    for(x=0;x<target->width;x++) {
      unsigned char *p=target->pixels+y*target->stride+x*target->channels,fp[4]={0},sp[4]={0};
      double f=fill->pixels[y*fill->stride+x]/255.,s=stroke->pixels[y*stroke->stride+x]/255.,k=clip ? clip->pixels[y*clip->stride+x]/255. : 1;
      double fw,sw,bw,fa,sa,ba,a;unsigned channel;
      exr_bitmap first={1,1,target->channels,fp,target->channels},second={1,1,target->channels,sp,target->channels};
      if(!(stroke_color&255)) s=0;
      fw=f*(1-s)*k;sw=s*k;bw=1-fw-sw;
      if((!f && !s) || !k) continue;
      if(!exr_vector_work(work,cost+(state ? 64+state->depth*4 : 0))) return exr_fail(e,EXR_LIMIT,"Compound path blend exceeds budget");
      if(state && state->pixels) {
        double back[4],base[4],fc[3],sc[3],fr[4],sr[4],out[4],af=(fill_color&255)/255.,as=(stroke_color&255)/255.;
        read_rgba(target,state,x,y,back);
        /* A knockout group treats fill+stroke as one element over the initial backdrop. */
        if(state->knockout) read_backdrop(state,x,y,base);else memcpy(base,back,sizeof(base));
        for(channel=0;channel<3;channel++) { fc[channel]=((fill_color>>(24-8*channel))&255)/255.;sc[channel]=((stroke_color>>(24-8*channel))&255)/255.; }
        over_rgba(base,fc,af,mode,fr);over_rgba(base,sc,as,mode,sr);
        for(channel=0;channel<4;channel++) out[channel]=fw*fr[channel]+sw*sr[channel]+bw*back[channel];
        write_rgba(target,state,x,y,out,fw*af+sw*as);continue;
      }
      memcpy(fp,p,target->channels);memcpy(sp,p,target->channels);
      exr_pixel_blend(&first,0,0,fill_color,255,mode);exr_pixel_blend(&second,0,0,stroke_color,255,mode);
      if(target->channels==1) { p[0]=(unsigned char)floor(fw*fp[0]+sw*sp[0]+bw*p[0]+.5);continue; }
      fa=fp[3]/255.;sa=sp[3]/255.;ba=p[3]/255.;a=fw*fa+sw*sa+bw*ba;
      for(channel=0;channel<3;channel++) p[channel]=a>0 ? (unsigned char)fmin(255,floor((fw*fa*fp[channel]+sw*sa*sp[channel]+bw*ba*p[channel])/a+.5)) : 0;
      p[3]=(unsigned char)fmin(255,floor(a*255+.5));
    }
  }
  return EXR_OK;
}
