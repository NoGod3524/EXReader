/* SPDX-License-Identifier: MIT */
/* UI controller unit check: ABI doubles record writes; the companion Python
   test exercises the real engine, history and DOCX serialization. No window. */
#include <exr/edit.h>
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include <stdint.h>
#define DE_IMAGE_RESIZE_NO_PAINT
#include "../examples/windows/shell_docedit_image_resize.inc"
static exr_edit_image im;
static exr_edit_block block;
static int writes;
static double written_width,written_height;
const exr_edit_block *exr_edit_find_block(const exr_edit_doc *doc,exr_edit_id id) {
  assert(doc);return id==42 ? &block:NULL;
}
exr_status exr_edit_image_size(exr_edit_doc *doc,exr_edit_id id,double width,double height) {
  assert(doc && id==42);writes++;written_width=width;written_height=height;return EXR_OK;
}
int main(void) {
  exr_edit_doc *doc=(exr_edit_doc *)&block;
  im.width_emu=1270000;im.height_emu=635000;block.image=&im;
  de_image_box box={20,80,200,100};de_image_resize drag={0};
  for(int h=0;h<8;h++) {
    double x,y;de_image_handle(&box,h,&x,&y);
    assert(de_image_handle_hit(&box,x,y,4)==h);
    assert(de_image_resize_begin(&drag,doc,42,&box,h,x,y));
    de_image_resize_move(&drag,x+(x-(box.x+100))*2,y+(y-(box.y+50))*2);
    assert(fabs(drag.scale-2)<1e-9);
    assert(fabs(drag.preview.width/drag.preview.height-2)<1e-9);
    assert(de_image_resize_end(&drag,doc,1)==EXR_OK && !writes);
  }
  assert(de_image_handle_hit(&box,120,130,4)==-1);
  assert(de_image_resize_begin(&drag,doc,42,&box,4,220,180));
  de_image_resize_move(&drag,320,230);
  assert(fabs(drag.preview.width-300)<1e-9 && fabs(drag.preview.height-150)<1e-9);
  assert(!writes && de_image_resize_end(&drag,doc,0)==EXR_OK);
  assert(writes==1 && written_width==150 && written_height==75);
  assert(de_image_resize_begin(&drag,doc,42,&box,4,220,180));
  de_image_resize_move(&drag,-1000,-1000);
  assert(drag.preview.width>0 && drag.preview.height>=8);
  de_image_resize_move(&drag,INFINITY,0);assert(isfinite(drag.preview.width));
  assert(de_image_resize_end(&drag,doc,1)==EXR_OK && writes==1);
  assert(de_image_resize_begin(&drag,doc,42,&box,4,220,180));
  assert(de_image_resize_end(&drag,doc,0)==EXR_OK && writes==1);
  assert(!de_image_resize_begin(&drag,doc,43,&box,4,220,180));
  puts("L09 controller: 8 handles, SE 200x100 -> 300x150, ratio, cancel=0 writes, commit=1 write, clamp PASS");
  return 0;
}
