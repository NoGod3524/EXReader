/* SPDX-License-Identifier: MIT */
#include "exreader.h"
#include "../src/vector_internal.h"
#include "../src/pixels_internal.h"
static exr_error error; static unsigned checks;
#define CHECK(x) do { checks++; if(!(x)) { fprintf(stderr,"line %d: %s (%d: %s)\n",__LINE__,#x,error.code,error.message); exit(1); } } while(0)
#define OK(x) CHECK((x)==EXR_OK)
static exr_bitmap bitmap(unsigned channels,unsigned value) {
  exr_bitmap out={0}; out.width=out.height=8; out.channels=channels; out.stride=8*channels; out.pixels=malloc((size_t)out.stride*out.height);
  CHECK(out.pixels); memset(out.pixels,value,(size_t)out.stride*out.height); return out;
}
static void rectangle(exr_vector_edge *edges,double left,double top,double right,double bottom,int reverse) {
  double x[4]={left,right,right,left},y[4]={top,top,bottom,bottom}; size_t i;
  for(i=0;i<4;i++) { size_t a=reverse ? 3-i : i,b=reverse ? (6-i)%4 : (i+1)%4; edges[i]=(exr_vector_edge){x[a],y[a],x[b],y[b]}; }
}
static unsigned pixel(const exr_bitmap *out,unsigned x,unsigned y,unsigned channel) { return out->pixels[(size_t)y*out->stride+x*out->channels+channel]; }
static void mask_fill_equivalence(void) {
  exr_bitmap mask=bitmap(1,0),rgba=bitmap(4,0),clip=bitmap(1,0);
  unsigned trial,i;size_t work;
  for(trial=0;trial<100;trial++) {
    double shift=(trial-50.)/97.;
    exr_vector_edge edges[5]={{-1+shift,.1,5.7,1.3},{5.7,1.3,8.2,5.1},
      {8.2,5.1,3.2+shift,7.9},{3.2+shift,7.9,.2,4.2},{.2,4.2,-1+shift,.1}};
    for(i=0;i<64;i++) {
      mask.pixels[i]=(unsigned char)(i*31+trial);
      memset(rgba.pixels+4*i,mask.pixels[i],3);rgba.pixels[4*i+3]=255;
      clip.pixels[i]=(unsigned char)(i*17+trial*3);
    }
    work=0;OK(exr_vector_fill(&mask,edges,5,EXR_VECTOR_EVENODD,0xffffffff,trial&1 ? &clip : NULL,&work,NULL,&error));
    work=0;OK(exr_vector_fill(&rgba,edges,5,EXR_VECTOR_EVENODD,0xffffffff,trial&1 ? &clip : NULL,&work,NULL,&error));
    for(i=0;i<64;i++) CHECK(mask.pixels[i]==rgba.pixels[4*i] && mask.pixels[i]==rgba.pixels[4*i+1] && mask.pixels[i]==rgba.pixels[4*i+2]);
  }
  free(mask.pixels);free(rgba.pixels);free(clip.pixels);
}
static int cancel(void *context) { unsigned *calls=context; return ++*calls>=3; }
static int keep_drawing(void *context) { (void)context; return 0; }
static void compound_spans(void) {
  unsigned char fill[]={255,255,255,0,80,0,0,0},stroke[]={0,0,255,255,100,0,0,0};
  unsigned char clip[]={255,255,255,255,128,255,0,255},actual[32],reference[32];
  const exr_bitmap fm={8,1,8,fill,1},sm={8,1,8,stroke,1},cm={8,1,8,clip,1};
  exr_bitmap fast={8,1,32,actual,4},slow={8,1,32,reference,4};
  const uint32_t bounds[]={0,0,8,1};
  const size_t limit=(size_t)256*1024*1024;
  size_t a=0,b=limit-(8+5*12);
  for(size_t i=0;i<sizeof(actual);i++) actual[i]=reference[i]=(unsigned char)(i*13);
  OK(exr_composite_compound(&fast,&fm,&sm,bounds,0xaabbccff,0x112233ff,EXR_BLEND_NORMAL,&(exr_clip_mask){.bitmap=cm},NULL,&a,NULL,&error));
  OK(exr_composite_compound(&slow,&fm,&sm,bounds,0xaabbccff,0x112233ff,EXR_BLEND_NORMAL,&(exr_clip_mask){.bitmap=cm},NULL,&b,NULL,&error));
  CHECK(a==8+5*12 && b==limit && !memcmp(actual,reference,sizeof(actual)));
  CHECK(!memcmp(actual,"\xaa\xbb\xcc\xff\xaa\xbb\xcc\xff\x11\x22\x33\xff\x11\x22\x33\xff",16));
  /* Exhaustive check of fast opaque normal-blend AA and offset masks against the slow path. */
  {
    const unsigned char vals[]={0,1,37,127,128,219,254,255};
    unsigned char fbuf[64],sbuf[64],cbuf[16*8],fast_px[16*8*4],slow_px[16*8*4];
    const exr_bitmap tight_f={8,8,8,fbuf,1},tight_s={8,8,8,sbuf,1};
    unsigned char full_f[16*8],full_s[16*8];
    const exr_bitmap big_f={16,8,16,full_f,1},big_s={16,8,16,full_s,1},big_c={16,8,16,cbuf,1};
    const uint32_t bnds[]={5,0,13,8};
    memset(full_f,0,sizeof(full_f)); memset(full_s,0,sizeof(full_s));
    for(unsigned y=0;y<8;y++) for(unsigned x=0;x<8;x++) {
      fbuf[y*8+x]=full_f[y*16+5+x]=vals[x];
      sbuf[y*8+x]=full_s[y*16+5+x]=vals[y];
    }
    for(unsigned use_clip=0;use_clip<2;use_clip++) for(unsigned bg_a=0;bg_a<3;bg_a++) {
      exr_bitmap fbm={16,8,64,fast_px,4},sbm={16,8,64,slow_px,4};
      for(size_t i=0;i<16*8;i++) {
        fast_px[i*4+0]=slow_px[i*4+0]=(unsigned char)(i*19+7);
        fast_px[i*4+1]=slow_px[i*4+1]=(unsigned char)(i*31+3);
        fast_px[i*4+2]=slow_px[i*4+2]=(unsigned char)(i*43+11);
        fast_px[i*4+3]=slow_px[i*4+3]=bg_a==0 ? 255 : bg_a==1 ? 0 : (unsigned char)((i*29)%255);
        cbuf[i]=vals[(i*3+use_clip)%8];
      }
      size_t wf=0,ws=0;
      exr_composite_state slow_state={0};
      OK(exr_composite_compound_at(&fbm,&tight_f,&tight_s,5,0,bnds,0x357bd1ff,0xd94e2aff,EXR_BLEND_NORMAL,use_clip ? &(exr_clip_mask){.bitmap=big_c} : NULL,NULL,&wf,NULL,&error));
      OK(exr_composite_compound(&sbm,&big_f,&big_s,bnds,0x357bd1ff,0xd94e2aff,EXR_BLEND_NORMAL,use_clip ? &(exr_clip_mask){.bitmap=big_c} : NULL,&slow_state,&ws,NULL,&error));
      CHECK(!memcmp(fast_px,slow_px,sizeof(fast_px)));
    }
  }
}
static void stable_clip_rows(void) {
  exr_vector_edge edges[8];
  exr_bitmap actual=bitmap(1,0),reference=bitmap(1,0),clip=bitmap(1,0);
  exr_control control={0};
  control.cancelled=keep_drawing;
  rectangle(edges,.2,.125,7.6,7.875,0);
  rectangle(edges+4,2.3,2.875,5.1,5.125,1);
  for(size_t i=0;i<64;i++) clip.pixels[i]=(unsigned char)(i*37);
  for(unsigned sloped=0;sloped<2;sloped++) {
    if(sloped) edges[4].x0=edges[7].x1=2.7;
    for(unsigned rule=0;rule<2;rule++) {
      exr_vector_rule fill_rule=rule ? EXR_VECTOR_EVENODD : EXR_VECTOR_NONZERO;
      for(size_t remaining=0;remaining<=1024;remaining++) {
        size_t a=(size_t)256*1024*1024-remaining,b=a;
        memset(actual.pixels,17,64);memset(reference.pixels,17,64);
        exr_status s=exr_vector_fill(&actual,edges,8,fill_rule,0xffffffff,&clip,&a,NULL,&error);
        exr_status t=exr_vector_fill(&reference,edges,8,fill_rule,0xffffffff,&clip,&b,&control,&error);
        CHECK(s==t && a==b && !memcmp(actual.pixels,reference.pixels,64));
      }
    }
  }
  free(actual.pixels);free(reference.pixels);free(clip.pixels);
}
static double segment_distance(exr_vector_point p,exr_vector_point a,exr_vector_point b) {
  double length=hypot(b.x-a.x,b.y-a.y),left=hypot(p.x-a.x,p.y-a.y),right=hypot(p.x-b.x,p.y-b.y);
  if(!length || left*left>=right*right+length*length || right*right>=left*left+length*length) return fmin(left,right);
  return fabs((b.x-a.x)*(a.y-p.y)-(a.x-p.x)*(b.y-a.y))/length;
}
static void curve_distance(const exr_vector_polyline *path,const exr_vector_point *p,unsigned degree,const double *m,double tolerance) {
  unsigned i; size_t j;
  for(i=0;i<=1000;i++) {
    double t=i/1000.0,s=1-t,distance=1e20; exr_vector_point point;
    if(degree==2) { point.x=s*s*p[0].x+2*s*t*p[1].x+t*t*p[2].x; point.y=s*s*p[0].y+2*s*t*p[1].y+t*t*p[2].y; }
    else { point.x=s*s*s*p[0].x+3*s*s*t*p[1].x+3*s*t*t*p[2].x+t*t*t*p[3].x; point.y=s*s*s*p[0].y+3*s*s*t*p[1].y+3*s*t*t*p[2].y+t*t*t*p[3].y; }
    if(m) { exr_vector_point original=point; point.x=m[0]*original.x+m[2]*original.y+m[4]; point.y=m[1]*original.x+m[3]*original.y+m[5]; }
    for(j=1;j<path->point_count;j++) distance=fmin(distance,segment_distance(point,path->points[j-1],path->points[j]));
    CHECK(distance<=tolerance+1e-8);
  }
}
static void curves(void) {
  const double transform[6]={2,.5,-.25,3,10,-2}; const exr_vector_point quadratic[3]={{1,7},{4,-3},{7,7}},cubic[4]={{0,0},{10,0},{-10,0},{1,0}};
  exr_vector_segment segments[4]={{EXR_VECTOR_MOVE,{{1,7}}},{EXR_VECTOR_QUAD,{{4,-3},{7,7}}},{EXR_VECTOR_CLOSE,{{0}}}};
  exr_vector_polyline path={0}; exr_vector_edge *edges=NULL; size_t count=0,work=0,i;
  OK(exr_vector_flatten(segments,3,transform,.125,&path,&work,NULL,&error));
  CHECK(path.contour_count==1 && path.contours[0].closed && path.point_count>2); curve_distance(&path,quadratic,2,transform,.125);
  OK(exr_vector_edges(&path,0,&edges,&count,&work,NULL,&error)); CHECK(count==path.point_count && edges[count-1].x1==path.points[0].x);
  free(edges); exr_vector_polyline_free(&path); CHECK(!path.points && !path.contours);
  OK(exr_vector_flatten(segments,3,NULL,.05,&path,&work,NULL,&error));
  OK(exr_vector_edges(&path,1,&edges,&count,&work,NULL,&error));
  { exr_bitmap image=bitmap(1,255); OK(exr_vector_fill(&image,edges,count,EXR_VECTOR_NONZERO,0x000000ff,NULL,&work,NULL,&error));
    CHECK(pixel(&image,4,4,0)==0 && pixel(&image,0,4,0)==255 && pixel(&image,4,0,0)==255 && pixel(&image,4,7,0)==255); free(image.pixels);
  }
  free(edges); exr_vector_polyline_free(&path);
  segments[0]=(exr_vector_segment){EXR_VECTOR_MOVE,{{0,0}}}; segments[1]=(exr_vector_segment){EXR_VECTOR_CUBIC,{{10,0},{-10,0},{1,0}}};
  OK(exr_vector_flatten(segments,2,NULL,.01,&path,&work,NULL,&error)); CHECK(path.point_count>2); curve_distance(&path,cubic,3,NULL,.01);
  { double low=0,high=0; for(i=0;i<path.point_count;i++) { low=fmin(low,path.points[i].x); high=fmax(high,path.points[i].x); } CHECK(low<-1 && high>2); }
  exr_vector_polyline_free(&path);
  segments[1]=(exr_vector_segment){EXR_VECTOR_LINE,{{2,0}}}; segments[2].verb=EXR_VECTOR_CLOSE; segments[3]=(exr_vector_segment){EXR_VECTOR_LINE,{{0,2}}};
  OK(exr_vector_flatten(segments,4,NULL,.25,&path,&work,NULL,&error)); CHECK(path.contour_count==2 && path.contours[0].closed && !path.contours[1].closed && path.contours[1].count==2);
  OK(exr_vector_edges(&path,0,&edges,&count,&work,NULL,&error)); CHECK(count==3); free(edges);
  OK(exr_vector_edges(&path,1,&edges,&count,&work,NULL,&error)); CHECK(count==4); free(edges); exr_vector_polyline_free(&path);
  CHECK(exr_vector_flatten(segments+1,1,NULL,.25,&path,&work,NULL,&error)==EXR_ARGUMENT && !path.points);
  CHECK(exr_vector_flatten(segments,4,NULL,0,&path,&work,NULL,&error)==EXR_ARGUMENT);
  CHECK(exr_vector_flatten(segments,1048577,NULL,.25,&path,&work,NULL,&error)==EXR_LIMIT);
  segments[0].points[0].x=INFINITY; CHECK(exr_vector_flatten(segments,4,NULL,.25,&path,&work,NULL,&error)==EXR_ARGUMENT && !path.points && !path.contours);
  segments[0].points[0].x=1e7; CHECK(exr_vector_flatten(segments,4,transform,.25,&path,&work,NULL,&error)==EXR_LIMIT && !path.points);
  segments[0].points[0].x=0;
  { exr_control control={0}; unsigned calls=2; control.cancelled=cancel; control.context=&calls;
    CHECK(exr_vector_flatten(segments,4,NULL,.25,&path,&work,&control,&error)==EXR_CANCELLED && !path.points);
  }
  { size_t limited=(size_t)256*1024*1024; CHECK(exr_vector_flatten(segments,4,NULL,.25,&path,&limited,NULL,&error)==EXR_LIMIT && !path.points); }
  OK(exr_vector_flatten(NULL,0,NULL,.25,&path,&work,NULL,&error)); CHECK(!path.point_count && !path.contour_count); exr_vector_polyline_free(&path);
}
static exr_bitmap stroked(const exr_vector_polyline *source,const exr_vector_stroke_style *style,const double *matrix,uint32_t color) {
  exr_vector_polyline outline={0}; exr_vector_edge *edges=NULL; size_t count,work=0; exr_bitmap image=bitmap(1,255);
  OK(exr_vector_stroke(source,style,matrix,.01,&outline,&work,NULL,&error));
  OK(exr_vector_edges(&outline,0,&edges,&count,&work,NULL,&error));
  OK(exr_vector_fill(&image,edges,count,EXR_VECTOR_NONZERO,color,NULL,&work,NULL,&error));
  free(edges); exr_vector_polyline_free(&outline); return image;
}
static void strokes(void) {
  exr_vector_segment commands[5]={{EXR_VECTOR_MOVE,{{2,4}}},{EXR_VECTOR_LINE,{{6,4}}}};
  exr_vector_polyline line={0},out={0}; exr_vector_stroke_style style={2,10,EXR_VECTOR_BUTT,EXR_VECTOR_MITER}; exr_bitmap image; size_t work=0,i;
  OK(exr_vector_flatten(commands,2,NULL,.1,&line,&work,NULL,&error));
  image=stroked(&line,&style,NULL,0x000000ff); CHECK(pixel(&image,1,3,0)==255 && pixel(&image,2,3,0)==0 && pixel(&image,5,4,0)==0 && pixel(&image,6,3,0)==255); free(image.pixels);
  style.cap=EXR_VECTOR_SQUARE; image=stroked(&line,&style,NULL,0x000000ff); CHECK(pixel(&image,1,3,0)==0 && pixel(&image,6,4,0)==0 && pixel(&image,0,4,0)==255); free(image.pixels);
  style.cap=EXR_VECTOR_ROUND_CAP; image=stroked(&line,&style,NULL,0x000000ff); CHECK(pixel(&image,1,3,0)>30 && pixel(&image,1,3,0)<90 && pixel(&image,3,3,0)==0 && pixel(&image,0,3,0)==255); free(image.pixels);
  exr_vector_polyline_free(&line);
  commands[0].points[0]=(exr_vector_point){1,5}; commands[1].points[0]=(exr_vector_point){5,5}; commands[2]=(exr_vector_segment){EXR_VECTOR_LINE,{{5,1}}};
  OK(exr_vector_flatten(commands,3,NULL,.1,&line,&work,NULL,&error)); style.cap=EXR_VECTOR_BUTT;
  image=stroked(&line,&style,NULL,0x000000ff); CHECK(pixel(&image,5,5,0)==0); free(image.pixels);
  style.join=EXR_VECTOR_BEVEL; image=stroked(&line,&style,NULL,0x000000ff); CHECK(pixel(&image,5,5,0)==127); free(image.pixels);
  style.join=EXR_VECTOR_ROUND_JOIN; image=stroked(&line,&style,NULL,0x000000ff); CHECK(pixel(&image,5,5,0)>30 && pixel(&image,5,5,0)<90); free(image.pixels);
  style.join=EXR_VECTOR_MITER; style.miter_limit=1; image=stroked(&line,&style,NULL,0x000000ff); CHECK(pixel(&image,5,5,0)==127); free(image.pixels);
  style.miter_limit=10; image=stroked(&line,&style,NULL,0x00000080); CHECK(pixel(&image,4,4,0)==127); free(image.pixels); exr_vector_polyline_free(&line);
  commands[0].points[0]=(exr_vector_point){4,4}; commands[1].points[0]=(exr_vector_point){4.1,4}; commands[2].points[0]=(exr_vector_point){4.1,4.1};
  OK(exr_vector_flatten(commands,3,NULL,.1,&line,&work,NULL,&error)); style.width=4; style.join=EXR_VECTOR_ROUND_JOIN;
  image=stroked(&line,&style,NULL,0x000000ff); CHECK(pixel(&image,3,3,0)==255 && pixel(&image,4,3,0)==0); free(image.pixels); exr_vector_polyline_free(&line);
  style.join=EXR_VECTOR_MITER;
  commands[0].points[0]=(exr_vector_point){1,2}; commands[1].points[0]=(exr_vector_point){3,2};
  OK(exr_vector_flatten(commands,2,NULL,.1,&line,&work,NULL,&error));
  { const double matrix[6]={2,0,0,3,0,0}; style.width=0; image=stroked(&line,&style,matrix,0x000000ff);
    CHECK(pixel(&image,3,5,0)==127 && pixel(&image,3,6,0)==127 && pixel(&image,3,4,0)==255); free(image.pixels);
    style.width=2; image=stroked(&line,&style,matrix,0x000000ff); CHECK(pixel(&image,3,4,0)==0 && pixel(&image,1,4,0)==255); free(image.pixels);
  }
  exr_vector_polyline_free(&line);
  commands[0].points[0]=(exr_vector_point){4,4}; commands[1].points[0]=(exr_vector_point){4,4}; style.width=4; style.cap=EXR_VECTOR_ROUND_CAP;
  OK(exr_vector_flatten(commands,2,NULL,.1,&line,&work,NULL,&error)); image=stroked(&line,&style,NULL,0x000000ff);
  CHECK(pixel(&image,4,4,0)==0 && pixel(&image,1,4,0)==255); free(image.pixels);
  style.cap=EXR_VECTOR_BUTT; image=stroked(&line,&style,NULL,0x000000ff); for(i=0;i<64;i++) CHECK(image.pixels[i]==255); free(image.pixels);
  style.width=-1; CHECK(exr_vector_stroke(&line,&style,NULL,.1,&out,&work,NULL,&error)==EXR_ARGUMENT && !out.points); style.width=2;
  style.miter_limit=.5; CHECK(exr_vector_stroke(&line,&style,NULL,.1,&out,&work,NULL,&error)==EXR_ARGUMENT && !out.points); style.miter_limit=10;
  { exr_control control={0}; unsigned calls=2; control.context=&calls; control.cancelled=cancel;
    CHECK(exr_vector_stroke(&line,&style,NULL,.1,&out,&work,&control,&error)==EXR_CANCELLED && !out.points);
  }
  CHECK(exr_vector_stroke(&line,&style,NULL,.1,&line,&work,NULL,&error)==EXR_ARGUMENT && line.points);
  { size_t limited=(size_t)256*1024*1024; CHECK(exr_vector_stroke(&line,&style,NULL,.1,&out,&limited,NULL,&error)==EXR_LIMIT && !out.points); }
  exr_vector_polyline_free(&line);
}
static void interval(const exr_vector_polyline *path,size_t index,double first,double last) {
  const exr_vector_contour *c; CHECK(index<path->contour_count); c=&path->contours[index];
  CHECK(fabs(path->points[c->start].x-first)<1e-9 && fabs(path->points[c->start+c->count-1].x-last)<1e-9);
}
static void dashes(void) {
  exr_vector_segment commands[5]={{EXR_VECTOR_MOVE,{{0,4}}},{EXR_VECTOR_LINE,{{12,4}}}};
  exr_vector_polyline line={0},dashed={0}; size_t work=0,i; const double pattern[2]={2,1},odd[3]={2,1,1},dots[2]={0,2},zero_gap[2]={2,0};
  OK(exr_vector_flatten(commands,2,NULL,.1,&line,&work,NULL,&error));
  OK(exr_vector_dash(&line,pattern,2,0,&dashed,&work,NULL,&error)); CHECK(dashed.contour_count==4);
  for(i=0;i<4;i++) interval(&dashed,i,3*(double)i,3*(double)i+2); exr_vector_polyline_free(&dashed);
  OK(exr_vector_dash(&line,pattern,2,-1,&dashed,&work,NULL,&error)); CHECK(dashed.contour_count==4); interval(&dashed,0,1,3); interval(&dashed,3,10,12); exr_vector_polyline_free(&dashed);
  OK(exr_vector_dash(&line,odd,3,0,&dashed,&work,NULL,&error)); CHECK(dashed.contour_count==5); interval(&dashed,0,0,2); interval(&dashed,1,3,4); interval(&dashed,2,6,7); interval(&dashed,4,11,12); exr_vector_polyline_free(&dashed);
  OK(exr_vector_dash(&line,dots,2,0,&dashed,&work,NULL,&error)); CHECK(dashed.contour_count==7);
  for(i=0;i<7;i++) { CHECK(dashed.contours[i].count==2); interval(&dashed,i,2*(double)i,2*(double)i); } exr_vector_polyline_free(&dashed);
  OK(exr_vector_dash(&line,zero_gap,2,0,&dashed,&work,NULL,&error)); CHECK(dashed.contour_count==6); interval(&dashed,5,10,12); exr_vector_polyline_free(&dashed);
  OK(exr_vector_dash(&line,NULL,0,0,&dashed,&work,NULL,&error)); CHECK(dashed.point_count==line.point_count && dashed.points!=line.points && !memcmp(dashed.points,line.points,line.point_count*sizeof(*line.points))); exr_vector_polyline_free(&dashed); exr_vector_polyline_free(&line);
  commands[1].points[0].x=3; commands[2]=(exr_vector_segment){EXR_VECTOR_MOVE,{{10,4}}}; commands[3]=(exr_vector_segment){EXR_VECTOR_LINE,{{13,4}}};
  OK(exr_vector_flatten(commands,4,NULL,.1,&line,&work,NULL,&error));
  OK(exr_vector_dash(&line,pattern,2,1,&dashed,&work,NULL,&error)); CHECK(dashed.contour_count==4); interval(&dashed,0,0,1); interval(&dashed,1,2,3); interval(&dashed,2,10,11); interval(&dashed,3,12,13); exr_vector_polyline_free(&dashed); exr_vector_polyline_free(&line);
  commands[0].points[0]=(exr_vector_point){2,2}; commands[1].points[0]=(exr_vector_point){6,2}; commands[2]=(exr_vector_segment){EXR_VECTOR_LINE,{{6,6}}}; commands[3]=(exr_vector_segment){EXR_VECTOR_LINE,{{2,6}}}; commands[4]=(exr_vector_segment){EXR_VECTOR_CLOSE,{{0}}};
  OK(exr_vector_flatten(commands,5,NULL,.1,&line,&work,NULL,&error));
  { const double solid[2]={100,1}; OK(exr_vector_dash(&line,solid,2,0,&dashed,&work,NULL,&error)); CHECK(dashed.contour_count==1 && dashed.contours[0].closed); exr_vector_polyline_free(&dashed); }
  { const double wraps[2]={3,2}; exr_vector_contour *c;
    OK(exr_vector_dash(&line,wraps,2,0,&dashed,&work,NULL,&error)); CHECK(dashed.contour_count==3); c=&dashed.contours[2]; CHECK(c->count==3 && !c->closed);
    CHECK(dashed.points[c->start].x==2 && dashed.points[c->start].y==3 && dashed.points[c->start+1].x==2 && dashed.points[c->start+1].y==2 && dashed.points[c->start+2].x==5);
    exr_vector_polyline_free(&dashed);
  }
  { const double wraps[4]={0,0,3,2}; exr_vector_edge *edges=NULL; size_t count;
    OK(exr_vector_dash(&line,wraps,4,0,&dashed,&work,NULL,&error)); OK(exr_vector_edges(&dashed,0,&edges,&count,&work,NULL,&error)); CHECK(count>0); free(edges); exr_vector_polyline_free(&dashed);
  }
  { const double wraps[6]={0,0,3,0,0,2}; exr_vector_edge *edges=NULL; size_t count; exr_vector_contour *last;
    line.points[0].x=line.points[3].x=1;
    OK(exr_vector_dash(&line,wraps,6,0,&dashed,&work,NULL,&error)); CHECK(dashed.contour_count==11);
    last=&dashed.contours[10]; CHECK(last->count==2 && dashed.points[last->start].x==1 && dashed.points[last->start].y==2);
    OK(exr_vector_edges(&dashed,0,&edges,&count,&work,NULL,&error)); CHECK(count>0); free(edges); exr_vector_polyline_free(&dashed);
  }
  { const double invalid[2]={0,0}; CHECK(exr_vector_dash(&line,invalid,2,0,&dashed,&work,NULL,&error)==EXR_ARGUMENT && !dashed.points); }
  { const double invalid[2]={1,-1}; CHECK(exr_vector_dash(&line,invalid,2,0,&dashed,&work,NULL,&error)==EXR_ARGUMENT && !dashed.points); }
  { const double tiny[2]={1e-300,1e-300}; CHECK(exr_vector_dash(&line,tiny,2,0,&dashed,&work,NULL,&error)==EXR_LIMIT && !dashed.points); }
  CHECK(exr_vector_dash(&line,pattern,2,0,&line,&work,NULL,&error)==EXR_ARGUMENT && line.points);
  { exr_control control={0}; unsigned calls=2; control.context=&calls; control.cancelled=cancel;
    CHECK(exr_vector_dash(&line,pattern,2,0,&dashed,&work,&control,&error)==EXR_CANCELLED && !dashed.points);
  }
  exr_vector_polyline_free(&line);
  commands[0].points[0]=(exr_vector_point){0,4}; commands[1].points[0]=(exr_vector_point){8,4};
  OK(exr_vector_flatten(commands,2,NULL,.1,&line,&work,NULL,&error));
  { const double gaps[2]={2,2}; exr_vector_stroke_style style={2,10,EXR_VECTOR_BUTT,EXR_VECTOR_MITER}; exr_bitmap image;
    OK(exr_vector_dash(&line,gaps,2,0,&dashed,&work,NULL,&error)); image=stroked(&dashed,&style,NULL,0x000000ff);
    for(i=0;i<8;i++) CHECK(pixel(&image,(unsigned)i,3,0)==(i%4<2 ? 0 : 255)); free(image.pixels); exr_vector_polyline_free(&dashed);
  }
  exr_vector_polyline_free(&line);
}
static void rectangle_fill_equivalence(void) {
  const uint32_t colors[]={0x123456ff,0xffffffff,0x000000ff,0xed5b27ff,0x49a2ef80};
  exr_vector_edge shapes[8][4],split[5],clip_edges[4];
  exr_bitmap clips[2]={bitmap(1,0),bitmap(1,0)};
  size_t shape,color,background,mask,channels,work=0;
  rectangle(shapes[0],0,0,8,8,0); rectangle(shapes[1],1,2,6,7,0);
  rectangle(shapes[2],1,2,6,7,1); rectangle(shapes[3],-2,-1,5,6,0);
  rectangle(shapes[4],3,1,3,6,0); rectangle(shapes[5],1.25,1.25,6.75,6.75,0);
  /* Retraced edges have a nonempty bbox but enclose no area. */
  shapes[6][0]=(exr_vector_edge){1,1,6,1}; shapes[6][1]=(exr_vector_edge){6,1,1,1};
  shapes[6][2]=(exr_vector_edge){1,1,1,6}; shapes[6][3]=(exr_vector_edge){1,6,1,1};
  shapes[7][0]=(exr_vector_edge){1,1,6,1}; shapes[7][1]=(exr_vector_edge){6,1,5,6};
  shapes[7][2]=(exr_vector_edge){5,6,1,6}; shapes[7][3]=(exr_vector_edge){1,6,1,1};
  rectangle(clip_edges,1,2,7,7,0);
  OK(exr_vector_fill(&clips[0],clip_edges,4,EXR_VECTOR_NONZERO,0xffffffff,NULL,&work,NULL,&error));
  rectangle(clip_edges,.25,.5,6.75,7.25,0);
  OK(exr_vector_fill(&clips[1],clip_edges,4,EXR_VECTOR_NONZERO,0xffffffff,NULL,&work,NULL,&error));
  CHECK(clips[1].pixels[0]>0 && clips[1].pixels[0]<255 && pixel(&clips[1],2,2,0)==255);
  for(shape=0;shape<8;shape++) {
    const exr_vector_edge first=shapes[shape][0];
    double mx=(first.x0+first.x1)/2,my=(first.y0+first.y1)/2;
    split[0]=(exr_vector_edge){first.x0,first.y0,mx,my};
    split[1]=(exr_vector_edge){mx,my,first.x1,first.y1};
    memcpy(split+2,shapes[shape]+1,3*sizeof(*split));
    for(channels=1;channels<=4;channels+=3) for(background=0;background<3;background++) for(color=0;color<5;color++) for(mask=0;mask<3;mask++) {
      exr_bitmap actual=bitmap((unsigned)channels,background==1 ? 255 : 0),reference=bitmap((unsigned)channels,background==1 ? 255 : 0);
      const exr_bitmap *clip=mask ? &clips[mask-1] : NULL;
      if(background==2) {
        size_t i;
        if(channels==1) { memset(actual.pixels,128,64); memset(reference.pixels,128,64); }
        else for(i=0;i<64;i++) {
          unsigned char rgba[4]={73,162,239,128};
          memcpy(actual.pixels+i*4,rgba,4); memcpy(reference.pixels+i*4,rgba,4);
        }
      }
      work=0;
      OK(exr_vector_fill(&actual,shapes[shape],4,EXR_VECTOR_NONZERO,colors[color],clip,&work,NULL,&error));
      /* A collinear midpoint preserves coverage while count=5 forces the
         ordinary scanline rasterizer, independently of the rectangle path. */
      OK(exr_vector_fill(&reference,split,5,EXR_VECTOR_NONZERO,colors[color],clip,&work,NULL,&error));
      CHECK(!memcmp(actual.pixels,reference.pixels,(size_t)actual.stride*actual.height));
      free(actual.pixels); free(reference.pixels);
    }
  }
  for(channels=1;channels<=4;channels+=3) {
    exr_bitmap image=bitmap((unsigned)channels,255); exr_control control={0}; unsigned calls=0;
    control.cancelled=cancel; control.context=&calls; work=0;
    CHECK(exr_vector_fill(&image,shapes[0],4,EXR_VECTOR_NONZERO,0x123456ff,NULL,&work,&control,&error)==EXR_CANCELLED);
    CHECK(pixel(&image,0,0,0)==(channels==1 ? 46 : 0x12) && pixel(&image,0,1,0)==255);
    work=(size_t)256*1024*1024-4;
    CHECK(exr_vector_fill(&image,shapes[0],4,EXR_VECTOR_NONZERO,0x123456ff,NULL,&work,NULL,&error)==EXR_LIMIT);
    free(image.pixels);
  }
  free(clips[0].pixels); free(clips[1].pixels);
}
/* Integer arithmetic on an eighth-pixel grid is an independent area oracle;
   unlike the scanline reference it includes edges between the four samples. */
static unsigned overlap_eighths(int pixel_index,int first,int last) {
  int low=pixel_index*8>first ? pixel_index*8 : first;
  int high=(pixel_index+1)*8<last ? (pixel_index+1)*8 : last;
  return high>low ? (unsigned)(high-low) : 0;
}
static void rectangle_area(void) {
  const int boxes[][4]={{8,8,56,56},{9,11,54,51},{-11,-9,35,41},
                       {18,19,21,22},{7,7,9,9},{-8,1,3,5}};
  const uint32_t colors[]={0x123456ff,0xed5b2780,0x49a2ef00};
  const double inks[4]={.2,.4,.1,.3};
  exr_bitmap clip=bitmap(1,0); size_t box,work=0; unsigned i,channels,reverse,kind,mode,mask,color;
  for(i=0;i<64;i++) clip.pixels[i]=(unsigned char)(i*73);
  clip.pixels[3]=255;
  for(box=0;box<sizeof(boxes)/sizeof(*boxes);box++) for(channels=1;channels<=4;channels+=3)
    for(reverse=0;reverse<2;reverse++) for(kind=0;kind<4;kind++)
    for(mode=0;mode<=EXR_BLEND_LUMINOSITY;mode++) for(mask=0;mask<2;mask++) for(color=0;color<3;color++) {
      exr_vector_edge edges[4]; exr_bitmap actual=bitmap(channels,128),reference=bitmap(channels,128);
      exr_composite_state state={0}; const exr_clip_mask *mask_bitmap=mask ? &(exr_clip_mask){.bitmap=clip} : NULL;
      exr_composite_state *s=kind>=2 ? &state : NULL;
      unsigned x,y;
      if(kind==0 && mode!=EXR_BLEND_NORMAL) { free(actual.pixels); free(reference.pixels); continue; }
      state.soft_mask=clip.pixels; state.soft_mask_width=state.soft_mask_height=8; state.gray=kind==2;
      rectangle(edges,boxes[box][0]/8.,boxes[box][1]/8.,boxes[box][2]/8.,boxes[box][3]/8.,(int)reverse);
      work=0;
      if(kind==3) OK(exr_vector_fill_blend_cmyk(&actual,edges,4,reverse ? EXR_VECTOR_EVENODD : EXR_VECTOR_NONZERO,
                        inks,(colors[color]&255)/255.,mask_bitmap,(exr_blend_mode)mode,s,&work,NULL,&error));
      else OK(exr_vector_fill_blend(&actual,edges,4,reverse ? EXR_VECTOR_EVENODD : EXR_VECTOR_NONZERO,
                        colors[color],mask_bitmap,(exr_blend_mode)mode,s,&work,NULL,&error));
      for(y=0;y<8;y++) for(x=0;x<8;x++) {
        unsigned alpha=(overlap_eighths((int)x,boxes[box][0],boxes[box][2])*
                        overlap_eighths((int)y,boxes[box][1],boxes[box][3])*255+32)/64;
        if(mask) alpha=(alpha*clip.pixels[y*8+x]+127)/255;
        if(!alpha) continue;
        if(kind==3) exr_pixel_composite_cmyk(&reference,(int)x,(int)y,inks,(colors[color]&255)/255.,alpha,(exr_blend_mode)mode,s);
        else if(s) exr_pixel_composite(&reference,(int)x,(int)y,colors[color],alpha,(exr_blend_mode)mode,s);
        else if(mode==EXR_BLEND_NORMAL) exr_pixel(&reference,(int)x,(int)y,colors[color],alpha);
        else exr_pixel_blend(&reference,(int)x,(int)y,colors[color],alpha,(exr_blend_mode)mode);
      }
      CHECK(!memcmp(actual.pixels,reference.pixels,(size_t)actual.stride*actual.height));
      free(actual.pixels); free(reference.pixels);
    }
  { exr_vector_edge edges[4]; exr_bitmap image=bitmap(1,0);
    rectangle(edges,1.0002,.9998,6.9998,7.0002,0);
    work=0; OK(exr_vector_fill(&image,edges,4,EXR_VECTOR_NONZERO,0xffffffff,NULL,&work,NULL,&error));
    CHECK(pixel(&image,1,1,0)==255 && pixel(&image,6,6,0)==255 && pixel(&image,0,1,0)==0 && pixel(&image,1,7,0)==0);
    /* Sub-epsilon transform residuals qualify; a visible slant must not. */
    rectangle(edges,1.125,1.125,6.75,6.75,0); edges[0].y1+=1e-10; edges[1].y0+=1e-10;
    memset(image.pixels,0,64); work=0;
    OK(exr_vector_fill(&image,edges,4,EXR_VECTOR_NONZERO,0xffffffff,NULL,&work,NULL,&error));
    CHECK(pixel(&image,2,1,0)==223);
    edges[0].y1+=1e-4; edges[1].y0+=1e-4;
    memset(image.pixels,0,64); work=0;
    OK(exr_vector_fill(&image,edges,4,EXR_VECTOR_NONZERO,0xffffffff,NULL,&work,NULL,&error));
    CHECK(pixel(&image,2,1,0)==191);
    free(image.pixels);
  }
  /* Coincident contours keep analytic coverage, nonzero winding and even-odd
     cancellation, including reversed contours used by annotation appearances. */
  { unsigned repeats,pattern,rule;
    for(repeats=1;repeats<=3;repeats++) for(pattern=0;pattern<3;pattern++) for(rule=0;rule<2;rule++) {
      exr_vector_edge edges[12]; exr_bitmap actual=bitmap(1,0),reference=bitmap(1,0);
      int winding=0; unsigned x,y,filled;
      for(i=0;i<repeats;i++) {
        unsigned reversed=pattern==2 || (pattern==1 && (i&1)); winding+=reversed ? -1 : 1;
        rectangle(edges+i*4,1.125,1.375,6.75,6.375,(int)reversed);
      }
      filled=rule ? repeats%2 : winding!=0; work=0;
      OK(exr_vector_fill(&actual,edges,repeats*4,rule ? EXR_VECTOR_EVENODD : EXR_VECTOR_NONZERO,
                         0xffffffff,NULL,&work,NULL,&error));
      if(filled) for(y=0;y<8;y++) for(x=0;x<8;x++)
        reference.pixels[y*8+x]=(unsigned char)((overlap_eighths((int)x,9,54)*overlap_eighths((int)y,11,51)*255+32)/64);
      CHECK(!memcmp(actual.pixels,reference.pixels,64));
      free(actual.pixels); free(reference.pixels);
    }
  }
  free(clip.pixels);
}
static void composite_rows(void) {
  /* Every source/destination alpha pair, padded/unaligned rows and an offset
     destination. The existing integer pixel compositor is the pixel oracle. */
  exr_bitmap source={256,256,1027,NULL,4},target={260,260,1043,NULL,4},expected,clip={260,260,263,NULL,1};
  size_t bytes=(size_t)target.stride*target.height,x,y,work,want;unsigned test;
  float unused=0;exr_composite_state isolated={0},flags={0};
  source.pixels=malloc((size_t)source.stride*source.height);target.pixels=malloc(bytes);clip.pixels=malloc((size_t)clip.stride*clip.height);
  expected=target;expected.pixels=malloc(bytes);CHECK(source.pixels && target.pixels && clip.pixels && expected.pixels);
  isolated.isolated=1;isolated.pixels=&unused;isolated.left=3;isolated.top=1;isolated.right=253;isolated.bottom=255;
  flags.alpha_flags=EXR_ALPHA_CONSTANT_SHAPE|EXR_ALPHA_IMAGE_SHAPE;
  for(test=0;test<8;test++) {
    const exr_composite_state *state=test==5 ? &isolated : NULL;
    size_t left=state ? state->left : 0,top=state ? state->top : 0,right=state ? state->right : 256,bottom=state ? state->bottom : 256;
    double opacity=test==7 ? .37 : 1;
    memset(source.pixels,0xa5,(size_t)source.stride*source.height);memset(target.pixels,0x5a,bytes);memset(clip.pixels,255,(size_t)clip.stride*clip.height);
    for(y=0;y<256;y++) for(x=0;x<256;x++) {
      unsigned char *s=source.pixels+y*source.stride+x*4,*d=target.pixels+(y+2)*target.stride+(x+2)*4;
      s[0]=(unsigned char)(x*73+y*19);s[1]=(unsigned char)(x*11+y*53);s[2]=(unsigned char)(x*37+y*7);
      s[3]=(unsigned char)(test==1 ? 255 : test==2 && y%3!=2 ? (y%3 ? 0 : 255) : x);
      d[0]=(unsigned char)(x*13+y*23);d[1]=(unsigned char)(x*59+y*3);d[2]=(unsigned char)(x*17+y*31);d[3]=(unsigned char)y;
      if(test==4 && y%2) clip.pixels[(y+2)*clip.stride+x+2]=(unsigned char)(x*29);
    }
    memcpy(expected.pixels,target.pixels,bytes);want=(right-left)*(bottom-top);
    for(y=top;y<bottom;y++) for(x=left;x<right;x++) {
      const unsigned char *s=source.pixels+y*source.stride+x*4;
      unsigned a=(unsigned)floor(s[3]*opacity+.5),coverage=test==3 || test==4 ? clip.pixels[(y+2)*clip.stride+x+2] : 255;
      uint32_t color=((uint32_t)s[0]<<24)|((uint32_t)s[1]<<16)|((uint32_t)s[2]<<8)|a;
      if(a && coverage) { want++;exr_pixel(&expected,(int)x+2,(int)y+2,color,coverage); }
    }
    work=0;OK(exr_composite_frame(&target,&source,opacity,EXR_BLEND_NORMAL,test==3 || test==4 ? &(exr_clip_mask){.bitmap=clip} : NULL,
      test==6 ? &flags : NULL,state,NULL,2,2,&work,NULL,&error));
    CHECK(work==want);CHECK(!memcmp(target.pixels,expected.pixels,bytes));
  }
  for(test=0;test<4;test++) {
    unsigned calls=0;exr_control control={0};size_t active=test%2 ? 256 : 255;
    const size_t limit=(size_t)256*1024*1024;
    memset(target.pixels,0x5a,bytes);
    for(y=0;y<256;y++) for(x=0;x<256;x++) {
      unsigned char *s=source.pixels+y*source.stride+x*4;
      s[0]=21;s[1]=93;s[2]=187;s[3]=(unsigned char)(test%2 ? 255 : x);
    }
    memcpy(expected.pixels,target.pixels,bytes);
    /* Budget exhaustion after the first row and ten painted pixels of row 2;
       cancellation on the third poll leaves exactly the first row painted. */
    for(y=0;y<(test<2 ? 2u : 1u);y++) for(x=0;x<(y ? (test%2 ? 10u : 11u) : 256u);x++) {
      const unsigned char *s=source.pixels+y*source.stride+x*4;
      exr_pixel(&expected,(int)x+2,(int)y+2,0x155dbb00u|s[3],255);
    }
    control.cancelled=cancel;control.context=&calls;
    work=test<2 ? limit-256-active-256-10 : 0;
    CHECK(exr_composite_frame(&target,&source,1,EXR_BLEND_NORMAL,NULL,NULL,NULL,NULL,2,2,&work,test<2 ? NULL : &control,&error)==(test<2 ? EXR_LIMIT : EXR_CANCELLED));
    CHECK(work==(test<2 ? limit : 256+active));CHECK(!memcmp(target.pixels,expected.pixels,bytes));
    if(test>=2) CHECK(calls==3);
  }
  free(source.pixels);free(target.pixels);free(expected.pixels);free(clip.pixels);
}
/* The scanline keeps an active edge list, coverage blocks and interior runs.
   Each must reproduce a direct transcription of the all-edge scan, including
   its work charge, for gray, mask and RGBA targets with and without a clip. */
typedef struct { double x; int winding; } reference_crossing;
static int reference_compare(const void *a,const void *b) {
  const reference_crossing *x=a,*y=b; return x->x<y->x ? -1 : x->x>y->x;
}
static void reference_span(float *coverage,int origin,uint32_t width,double left,double right) {
  int x,first,last; double end=origin+(double)width;
  if(left<origin) left=origin;
  if(right>end) right=end;
  if(right<=left) return;
  first=(int)left;last=(int)right;
  if(right==last) last--;
  if(first==last) { coverage[first-origin]+=(float)(right-left);return; }
  coverage[first-origin]+=(float)(first+1-left);
  for(x=first+1;x<last;x++) coverage[x-origin]+=1.f;
  coverage[last-origin]+=(float)(right-last);
}
static void reference_fill(exr_bitmap *bitmap,const exr_vector_edge *edges,size_t count,exr_vector_rule rule,uint32_t color,
                           const exr_bitmap *clip,size_t *work) {
  double low=1e300,high=-1e300,left_bound=1e300,right_bound=-1e300; size_t i; int y,top,bottom,left,right; uint32_t row_width,x;
  reference_crossing *crossings=malloc(count*sizeof(*crossings)); float *coverage;
  for(i=0;i<count;i++) {
    left_bound=fmin(left_bound,fmin(edges[i].x0,edges[i].x1)); right_bound=fmax(right_bound,fmax(edges[i].x0,edges[i].x1));
    if(edges[i].y0!=edges[i].y1) { low=fmin(low,fmin(edges[i].y0,edges[i].y1)); high=fmax(high,fmax(edges[i].y0,edges[i].y1)); }
  }
  *work+=count;
  if(high<=0 || low>=bitmap->height || low>=high || right_bound<=0 || left_bound>=bitmap->width || left_bound>=right_bound) { free(crossings); return; }
  top=(int)fmax(0,floor(low)); bottom=(int)fmin(bitmap->height,ceil(high));
  left=(int)fmax(0,floor(left_bound)); right=(int)fmin(bitmap->width,ceil(right_bound)); row_width=(uint32_t)(right-left);
  coverage=calloc(row_width,sizeof(*coverage)); CHECK(crossings && coverage);
  for(y=top;y<bottom;y++) {
    unsigned sample;
    memset(coverage,0,row_width*sizeof(*coverage));
    for(sample=0;sample<4;sample++) {
      double scan=y+(sample+.5)/4,previous=0; size_t n=0,at=0,levels=0; int winding=0;
      *work+=count;
      for(i=0;i<count;i++) {
        const exr_vector_edge *e=&edges[i]; int upward=e->y1>e->y0;
        double minimum=upward ? e->y0 : e->y1,maximum=upward ? e->y1 : e->y0;
        if(scan>=minimum && scan<maximum) crossings[n++]=(reference_crossing){e->x0+(scan-e->y0)/(e->y1-e->y0)*(e->x1-e->x0),upward ? 1 : -1};
      }
      for(i=n;i>1;i=(i+1)/2) levels++;
      *work+=n*(levels+1)+row_width;
      qsort(crossings,n,sizeof(*crossings),reference_compare);
      while(at<n) {
        double current=crossings[at].x; int delta=0;
        if(winding) reference_span(coverage,left,row_width,previous,current);
        do { delta+=rule==EXR_VECTOR_EVENODD ? 1 : crossings[at].winding; at++; } while(at<n && crossings[at].x==current);
        winding=rule==EXR_VECTOR_EVENODD ? (winding+delta)&1 : winding+delta;
        previous=current;
      }
    }
    *work+=row_width;
    for(x=0;x<row_width;x++) {
      unsigned alpha=coverage[x]>=4 ? 255u : (unsigned)(coverage[x]*255/4+.5);
      if(clip) alpha=(alpha*clip->pixels[(size_t)y*clip->stride+(unsigned)left+x]+127)/255;
      if(bitmap->channels==1 && color==0xffffffffu) {
        unsigned char *t=bitmap->pixels+(size_t)y*bitmap->stride+(unsigned)left+x;
        if(!*t || alpha==255) *t=(unsigned char)alpha; else *t=(unsigned char)(*t+((255-*t)*alpha+127)/255);
      } else if(alpha) exr_pixel(bitmap,left+(int)x,y,color,alpha);
    }
  }
  free(crossings); free(coverage);
}
static double scan_random(unsigned *state) { *state=*state*1103515245u+12345u; return (*state>>8)/16777216.; }
static void scanline_reference(void) {
  enum { W=70,H=30,MAX_EDGES=256 };
  exr_vector_edge edges[MAX_EDGES]; unsigned state=7,shape;
  unsigned char start[W*H*4],clip_pixels[W*H];
  const uint32_t colors[]={0xffffffffu,0x2a6fd3ffu,0x80402080u,0x000000ffu};
  for(size_t i=0;i<sizeof(start);i++) start[i]=(unsigned char)(scan_random(&state)*256);
  for(size_t i=0;i<sizeof(clip_pixels);i++) clip_pixels[i]=i%5==0 ? 255 : i%7==0 ? 0 : (unsigned char)(scan_random(&state)*256);
  for(shape=0;shape<400;shape++) {
    size_t count=0,k; unsigned contours=1+shape%3,contour,variant;
    for(contour=0;contour<contours;contour++) {
      unsigned points=shape%4==3 ? 4+(unsigned)(scan_random(&state)*20) : 5+(unsigned)(scan_random(&state)*14);
      double cx=-8+scan_random(&state)*(W+16),cy=-4+scan_random(&state)*(H+8),r=1+scan_random(&state)*30,inner=.2+scan_random(&state)*.7;
      exr_vector_point p[64];
      if(count+2*points>MAX_EDGES) break;
      for(k=0;k<2*points && shape%4!=3;k++) {
        double angle=k*3.14159265358979/points,rad=k%2 ? r*inner : r;
        p[k]=(exr_vector_point){cx+rad*cos(angle),cy+rad*sin(angle)*(contour%2 ? -1 : 1)};
        if(shape%5==1) p[k].x=floor(p[k].x),p[k].y=floor(p[k].y);
        if(shape%7==2 && k%3==0 && k) p[k].x=p[k-1].x;
      }
      /* A thin band along a wave, shaped like a stroke outline. */
      if(shape%4==3) for(k=0;k<points;k++) {
        double t=k/(points-1.),x=cx-r+2*r*t,wave=cy+r*.3*sin(t*6.283);
        p[k]=(exr_vector_point){x,wave-.4}; p[2*points-1-k]=(exr_vector_point){x,wave+.4+(shape%3)*.3};
      }
      for(k=0;k<2*points;k++) edges[count++]=(exr_vector_edge){p[k].x,p[k].y,p[(k+1)%(2*points)].x,p[(k+1)%(2*points)].y};
    }
    for(variant=0;variant<8;variant++) {
      unsigned channels=variant<4 ? 1 : 4; uint32_t color=channels==1 ? (variant&2 ? 0x000000ffu : 0xffffffffu) : colors[variant&3];
      exr_vector_rule rule=shape%2 ? EXR_VECTOR_EVENODD : EXR_VECTOR_NONZERO;
      unsigned char actual_pixels[W*H*4],reference_pixels[W*H*4];
      exr_bitmap actual={W,H,W*channels,actual_pixels,channels},reference={W,H,W*channels,reference_pixels,channels};
      const exr_bitmap clip={W,H,W,clip_pixels,1};
      size_t a=0,b=0;
      memcpy(actual_pixels,start,sizeof(start)); memcpy(reference_pixels,start,sizeof(start));
      if(channels==1 && color==0xffffffffu && variant&4) { memset(actual_pixels,0,W*H); memset(reference_pixels,0,W*H); }
      OK(exr_vector_fill(&actual,edges,count,rule,color,variant&1 ? &clip : NULL,&a,NULL,&error));
      reference_fill(&reference,edges,count,rule,color,variant&1 ? &clip : NULL,&b);
      CHECK(a==b && !memcmp(actual_pixels,reference_pixels,(size_t)W*H*channels));
    }
  }
}
int main(void) {
  composite_rows(); scanline_reference();
  exr_vector_edge edges[8]; exr_bitmap gray=bitmap(1,255),rgba=bitmap(4,0),clip=bitmap(1,255); size_t work=0,i; unsigned x,y;
  curves(); strokes(); dashes(); mask_fill_equivalence(); compound_spans(); stable_clip_rows(); rectangle_fill_equivalence(); rectangle_area(); rectangle(edges,1,1,5,5,0); OK(exr_vector_fill(&gray,edges,4,EXR_VECTOR_NONZERO,0x000000ff,NULL,&work,NULL,&error)); CHECK(work>0);
  for(y=0;y<8;y++) for(x=0;x<8;x++) CHECK(pixel(&gray,x,y,0)==(x>=1 && x<5 && y>=1 && y<5 ? 0 : 255));
  memset(gray.pixels,255,64); rectangle(edges,1.25,1.25,4.75,4.75,0);
  OK(exr_vector_fill(&gray,edges,4,EXR_VECTOR_NONZERO,0x000000ff,NULL,&work,NULL,&error)); CHECK(pixel(&gray,1,1,0)==112 && pixel(&gray,2,2,0)==0 && pixel(&gray,0,0,0)==255);
  for(i=0;i<3;i++) {
    memset(gray.pixels,255,64); rectangle(edges,0,0,8,8,0); rectangle(edges+4,2,2,6,6,i==0);
    OK(exr_vector_fill(&gray,edges,8,i==1 ? EXR_VECTOR_EVENODD : EXR_VECTOR_NONZERO,0x000000ff,NULL,&work,NULL,&error));
    CHECK(pixel(&gray,0,0,0)==0 && pixel(&gray,3,3,0)==(i==2 ? 0 : 255));
  }
  rectangle(edges,0,0,8,8,0);
  OK(exr_vector_fill(&rgba,edges,4,EXR_VECTOR_NONZERO,0xff000080,NULL,&work,NULL,&error));
  CHECK(pixel(&rgba,3,3,0)==255 && pixel(&rgba,3,3,1)==0 && pixel(&rgba,3,3,3)==128);
  OK(exr_vector_fill(&rgba,edges,4,EXR_VECTOR_NONZERO,0x0000ff80,NULL,&work,NULL,&error));
  CHECK(pixel(&rgba,3,3,0)==85 && pixel(&rgba,3,3,2)==170 && pixel(&rgba,3,3,3)==192);
  memset(rgba.pixels,255,256); for(i=0;i<64;i++) rgba.pixels[i*4+3]=1;
  OK(exr_vector_fill(&rgba,edges,4,EXR_VECTOR_NONZERO,0xffffff80,NULL,&work,NULL,&error));
  CHECK(pixel(&rgba,3,3,0)==255 && pixel(&rgba,3,3,1)==255 && pixel(&rgba,3,3,2)==255 && pixel(&rgba,3,3,3)==128);
  memset(gray.pixels,255,64); memset(clip.pixels,128,64); clip.pixels[0]=0; clip.pixels[1]=255;
  OK(exr_vector_fill(&gray,edges,4,EXR_VECTOR_NONZERO,0x000000ff,&clip,&work,NULL,&error)); CHECK(gray.pixels[0]==255 && gray.pixels[1]==0 && gray.pixels[2]==127);
  memset(gray.pixels,255,64); memset(clip.pixels,0,64); for(y=0;y<8;y++) clip.pixels[y*8+4]=255; rectangle(edges,3,1,6,5,0);
  OK(exr_vector_fill(&gray,edges,4,EXR_VECTOR_NONZERO,0x000000ff,&clip,&work,NULL,&error)); CHECK(pixel(&gray,4,2,0)==0 && pixel(&gray,3,2,0)==255 && pixel(&gray,5,2,0)==255);
  rectangle(edges,0,0,8,8,0);
  { exr_vector_edge triangles[6]={{0,0,8,0},{8,0,8,8},{8,8,0,0},{0,0,8,8},{8,8,0,8},{0,8,0,0}};
    memset(gray.pixels,255,64); OK(exr_vector_fill(&gray,triangles,6,EXR_VECTOR_NONZERO,0x000000ff,NULL,&work,NULL,&error));
    for(i=0;i<64;i++) CHECK(!gray.pixels[i]);
  }
  { exr_control control={0}; unsigned calls=0; control.cancelled=cancel; control.context=&calls;
    CHECK(exr_vector_fill(&gray,edges,4,EXR_VECTOR_NONZERO,0x000000ff,NULL,&work,&control,&error)==EXR_CANCELLED);
  }
  { size_t limited=(size_t)256*1024*1024-1;
    CHECK(exr_vector_fill(&gray,edges,4,EXR_VECTOR_NONZERO,0x000000ff,NULL,&limited,NULL,&error)==EXR_LIMIT);
  }
  edges[0].x0=NAN; CHECK(exr_vector_fill(&gray,edges,4,EXR_VECTOR_NONZERO,0x000000ff,NULL,NULL,NULL,&error)==EXR_ARGUMENT); edges[0].x0=0;
  CHECK(exr_vector_fill(&gray,edges,1048577,EXR_VECTOR_NONZERO,0x000000ff,NULL,NULL,NULL,&error)==EXR_LIMIT);
  CHECK(exr_vector_fill(&gray,edges,4,EXR_VECTOR_NONZERO,0x000000ff,&gray,NULL,NULL,&error)==EXR_ARGUMENT);
  { exr_bitmap alias=gray; alias.pixels++; CHECK(exr_vector_fill(&gray,edges,4,EXR_VECTOR_NONZERO,0x000000ff,&alias,NULL,NULL,&error)==EXR_ARGUMENT); }
  OK(exr_vector_fill(&gray,NULL,0,EXR_VECTOR_NONZERO,0x000000ff,NULL,NULL,NULL,&error));
  { exr_bitmap large={0}; size_t small_work=0; large.width=large.height=large.stride=512; large.channels=1; large.pixels=malloc(512*512); CHECK(large.pixels); memset(large.pixels,255,512*512);
    rectangle(edges,200,100,204,104,0); OK(exr_vector_fill(&large,edges,4,EXR_VECTOR_NONZERO,0x000000ff,NULL,&small_work,NULL,&error));
    CHECK(small_work<1000 && pixel(&large,202,102,0)==0 && pixel(&large,100,100,0)==255); free(large.pixels);
  }
  free(gray.pixels); free(rgba.pixels); free(clip.pixels); printf("%u native vector fill checks passed\n",checks); return 0;
}
