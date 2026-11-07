/* SPDX-License-Identifier: MIT */
#include "shell_geometry.h"
#include <assert.h>
#include <stdlib.h>
int main(void) {
  shell_geometry a = shell_geometry_for(1280,800,96,18,0);
  assert(a.enabled && a.width==612 && a.height==640);
  shell_geometry b = shell_geometry_for(2560,800,96,18,0);
  assert(shell_geometry_equal(a,b));
  b = shell_geometry_for(2560,1440,96,18,0);
  assert(b.width==612 && b.height==1280 && !shell_geometry_equal(a,b));
  b = shell_geometry_for(720,800,96,32,0);
  assert(b.width==624 && (720-b.width)/2==48);
  b = shell_geometry_for(1280,800,96,18,1);
  assert(b.height==612 && b.vertical);
  b = shell_geometry_for(2560,1440,144,18,1);
  assert(b.height==918 && b.width==918);
  b = shell_geometry_for(1920,1080,120,18,0);
  assert(b.width==765 && b.height==880);
  assert(!shell_geometry_for(0,0,96,18,0).enabled);
  const int sizes[][2]={{1242,742},{1280,800},{900,600},{720,560}};
  const int images[][2]={{600,900},{2400,3600},{3600,2400},{13,27}};
  for(unsigned i=0;i<sizeof(sizes)/sizeof(*sizes);i++)
    for(unsigned j=0;j<sizeof(images)/sizeof(*images);j++)
      for(unsigned dpi=96;dpi<=144;dpi+=24) {
        int w=sizes[i][0],h=sizes[i][1]-shell_px(SHELL_TOPBAR_H,dpi);
        shell_image_view v=shell_fit_image(w,h,dpi,17,images[j][0],images[j][1]);
        shell_geometry body=shell_geometry_for(w,sizes[i][1],dpi,17,0);
        assert(v.width>0 && v.height>0 && v.width<=body.width && v.height<=body.height);
        assert(abs(2*v.left+v.width-w)<=1);
        assert(abs(2*(v.top-shell_px(SHELL_BODY_TOP,dpi))+v.height-body.height)<=1);
        assert(v.left>=shell_px(16,dpi) && v.top>=shell_px(16,dpi));
        assert(w-v.left-v.width>=shell_px(16,dpi) && h-v.top-v.height>=shell_px(16,dpi));
        assert(fabs((double)v.width/v.height-(double)images[j][0]/images[j][1])<=.01);
      }
  for (int dpi=96;dpi<=192;dpi+=24)
    for (int w=720;w<=2560;w+=37)
      for (int f=14;f<=32;f++) {
        b=shell_geometry_for(w,1440,(unsigned)dpi,(float)f,0);
        assert(w-b.width>=2*shell_px(48,(unsigned)dpi));
        assert(b.width<=shell_px(34*(float)f,(unsigned)dpi));
      }
  return 0;
}
