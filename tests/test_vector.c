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
int main(void) {
  exr_vector_edge edges[8]; exr_bitmap gray=bitmap(1,255),rgba=bitmap(4,0),clip=bitmap(1,255); size_t work=0,i; unsigned x,y;
  rectangle(edges,1,1,5,5,0); OK(exr_vector_fill(&gray,edges,4,EXR_VECTOR_NONZERO,0x000000ff,NULL,&work,NULL,&error)); CHECK(work>0);
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
