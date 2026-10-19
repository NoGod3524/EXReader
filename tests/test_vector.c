/* SPDX-License-Identifier: MIT */
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
int main(void) {
  exr_vector_edge edges[8]; exr_bitmap gray=bitmap(1,255),rgba=bitmap(4,0),clip=bitmap(1,255); size_t work=0,i; unsigned x,y;
  curves(); strokes(); dashes(); rectangle(edges,1,1,5,5,0); OK(exr_vector_fill(&gray,edges,4,EXR_VECTOR_NONZERO,0x000000ff,NULL,&work,NULL,&error)); CHECK(work>0);
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
