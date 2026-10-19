/* SPDX-License-Identifier: MIT */
#include "exreader.h"
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static exr_error error; static unsigned checks;
#define CHECK(x) do { checks++; if(!(x)) { fprintf(stderr,"line %d: %s (%d: %s)\n",__LINE__,#x,error.code,error.message); exit(1); } } while(0)
#define OK(x) CHECK((x)==EXR_OK)
static void mapped(const exr_viewport *v,double x,double y,double expected_x,double expected_y) {
  double a=v->matrix[0]*x+v->matrix[2]*y+v->matrix[4],b=v->matrix[1]*x+v->matrix[3]*y+v->matrix[5];
  double original_x=v->inverse[0]*a+v->inverse[2]*b+v->inverse[4],original_y=v->inverse[1]*a+v->inverse[3]*b+v->inverse[5];
  CHECK(fabs(a-expected_x)<1e-10 && fabs(b-expected_y)<1e-10 && fabs(original_x-x)<1e-10 && fabs(original_y-y)<1e-10);
}
int main(void) {
  exr_page_geometry g={{-10,-20,30,40},2,0,0}; exr_viewport v; unsigned turn,down;
  const double corners[4][2]={{0,0},{60,0},{40,60},{0,40}};
  for(down=0;down<2;down++) for(turn=0;turn<4;turn++) {
    g.rotation=turn*90; g.y_down=down; OK(exr_viewport_create(&g,.5,&v,&error));
    CHECK(v.width==(turn%2 ? 60 : 40) && v.height==(turn%2 ? 40 : 60));
    mapped(&v,-10,down ? -20 : 40,corners[turn][0],corners[turn][1]);
    mapped(&v,10,10,v.width/2,v.height/2);
  }
  g.rotation=0; g.y_down=0; OK(exr_viewport_create(&g,1,&v,&error)); CHECK(v.width==80 && v.height==120); mapped(&v,30,-20,80,120);
  g.bounds[0]=NAN; CHECK(exr_viewport_create(&g,1,&v,&error)==EXR_ARGUMENT && !v.width && !v.matrix[0]); g.bounds[0]=-10;
  g.rotation=45; CHECK(exr_viewport_create(&g,1,&v,&error)==EXR_ARGUMENT); g.rotation=0;
  g.unit_scale=0; CHECK(exr_viewport_create(&g,1,&v,&error)==EXR_ARGUMENT); g.unit_scale=2;
  CHECK(exr_viewport_create(&g,0,&v,&error)==EXR_ARGUMENT && !v.width);
  CHECK(exr_viewport_create(&g,1e-300,&v,&error)==EXR_LIMIT && !v.width);
  CHECK(exr_viewport_create(&g,1e7,&v,&error)==EXR_LIMIT && !v.width);
  CHECK(exr_viewport_create(NULL,1,&v,&error)==EXR_ARGUMENT && !v.width);
  CHECK(exr_viewport_create(&g,1,NULL,&error)==EXR_ARGUMENT);
  printf("%u native viewport checks passed\n",checks); return 0;
}
