/* SPDX-License-Identifier: MIT */
#include "shell_geometry.h"
#include <assert.h>
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
  for (int dpi=96;dpi<=192;dpi+=24)
    for (int w=720;w<=2560;w+=37)
      for (int f=14;f<=32;f++) {
        b=shell_geometry_for(w,1440,(unsigned)dpi,(float)f,0);
        assert(w-b.width>=2*shell_px(48,(unsigned)dpi));
        assert(b.width<=shell_px(34*(float)f,(unsigned)dpi));
      }
  return 0;
}
