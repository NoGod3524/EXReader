/* SPDX-License-Identifier: GPL-3.0-only */
#include "../src/vector_internal.h"
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
static int cancel(void *context) { unsigned *calls=context; return ++*calls>=3; }
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
int main(void) {
  exr_vector_edge edges[8]; exr_bitmap gray=bitmap(1,255),rgba=bitmap(4,0),clip=bitmap(1,255); size_t work=0,i; unsigned x,y;
  curves(); rectangle(edges,1,1,5,5,0); OK(exr_vector_fill(&gray,edges,4,EXR_VECTOR_NONZERO,0x000000ff,NULL,&work,NULL,&error)); CHECK(work>0);
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
  free(gray.pixels); free(rgba.pixels); free(clip.pixels); printf("%u native vector fill checks passed\n",checks); return 0;
}
