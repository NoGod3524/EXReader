/* SPDX-License-Identifier: MIT */
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <exr/edit.h>
#include "shell_d2d.h"
#include "shell_docedit_image_paint.inc"

int main(void) {
  SetErrorMode(SEM_FAILCRITICALERRORS|SEM_NOGPFAULTERRORBOX);
  _set_error_mode(_OUT_TO_STDERR);
  _set_abort_behavior(0,_WRITE_ABORT_MSG|_CALL_REPORTFAULT);
  setvbuf(stdout,NULL,_IONBF,0);
  assert(SUCCEEDED(CoInitializeEx(NULL,COINIT_APARTMENTTHREADED)));
  shell_d2d *shell=NULL;assert(shell_d2d_create(NULL,&shell)==S_OK);
  /* 2x1 RGB PNG, red then blue. Exercise the real insert/decode path. */
  const unsigned char png[]={
    137,80,78,71,13,10,26,10,0,0,0,13,73,72,68,82,0,0,0,2,0,0,0,1,
    8,2,0,0,0,123,64,232,221,0,0,0,15,73,68,65,84,120,156,99,248,207,
    192,192,192,240,31,0,7,0,1,255,126,8,177,208,0,0,0,0,73,69,78,68,
    174,66,96,130};
  exr_edit_doc *doc=NULL;exr_edit_id id=0;
  assert(exr_edit_doc_create(NULL,0,NULL,0,NULL,0,NULL,&doc)==EXR_OK);
  exr_status status=exr_edit_insert_image(doc,0,png,sizeof(png),300,150,&id);
  if(status!=EXR_OK)fprintf(stderr,"insert image status=%d\n",(int)status);
  assert(status==EXR_OK);
  de_image_view view;
  assert(de_image_measure(doc,0,24,40,152,96,&view)==EXR_OK);
  assert(view.x==24 && view.width==152 && view.height==76);
  BITMAPINFO info={0};info.bmiHeader.biSize=sizeof(BITMAPINFOHEADER);
  info.bmiHeader.biWidth=200;info.bmiHeader.biHeight=-160;
  info.bmiHeader.biPlanes=1;info.bmiHeader.biBitCount=32;
  uint32_t *pixels=NULL;HDC dc=CreateCompatibleDC(NULL);assert(dc);
  HBITMAP bitmap=CreateDIBSection(dc,&info,DIB_RGB_COLORS,(void **)&pixels,NULL,0);assert(bitmap);
  HGDIOBJ old=SelectObject(dc,bitmap);RECT area={0,0,200,160};
  assert(shell_d2d_edit_paint(shell,dc,&area,0,NULL,0,24,0,32)==S_OK);
  assert(de_image_paint(shell,dc,&area,0,&view,0,32,SIZE_MAX)==S_OK);GdiFlush();
  size_t red=0,blue=0;
  for(int y=40;y<116;y++)for(int x=24;x<176;x++) {
    uint32_t rgb=pixels[y*200+x]&0xffffff;
    red+=((rgb>>16)&255)>180 && (rgb&255)<80;
    blue+=(rgb&255)>180 && ((rgb>>16)&255)<80;
  }
  assert(red>0 && blue>0);
  printf("PASS inserted bitmap red_pixels=%zu blue_pixels=%zu\n",red,blue);
  size_t selected=de_image_hit(&view,1,100,78,0,32,160);assert(selected==0);
  assert(de_image_paint(shell,dc,&area,0,&view,0,32,selected)==S_OK);GdiFlush();
  uint32_t border=pixels[40*200+24]&0xffffff;
  assert(border!=(pixels[42*200+26]&0xffffff));
  assert((pixels[42*200+26]&0xffffff)==0xff0000);
  puts("PASS center click selected_block=0 highlight=1px");
  selected=de_image_hit(&view,1,10,78,0,32,160);assert(selected==SIZE_MAX);
  assert(de_image_paint(shell,dc,&area,0,&view,0,32,selected)==S_OK);GdiFlush();
  assert((pixels[40*200+24]&0xffffff)==0xff0000);
  puts("PASS blank click selected_block=SIZE_MAX highlight_cleared=1");
  uint32_t background=pixels[150*200+190]&0xffffff;
  const unsigned char alpha[]={255,0,0,128,0,0,255,0};
  assert(shell_d2d_edit_image(shell,dc,&area,0,alpha,2,1,8,180,140,20,10,32,0)==S_OK);
  GdiFlush();assert((pixels[145*200+199]&0xffffff)==background);
  uint32_t blended=pixels[145*200+180]&0xffffff;
  assert(((blended>>16)&255)>180 && (blended&255)>50 && (blended&255)<200);
  const unsigned char green[]={0,255,0,255};
  assert(shell_d2d_edit_image(shell,dc,&area,0,green,1,1,4,0,0,20,40,32,0)==S_OK);
  GdiFlush();assert((pixels[10*200+10]&0xffffff)==background);
  assert((pixels[35*200+10]&0xffffff)==0x00ff00);
  puts("PASS premultiplied alpha, preserved background, paint clipped below toolbar");
  assert(de_image_hit(&view,1,100,28,50,32,160)==SIZE_MAX);
  assert(de_image_hit(&view,1,100,38,40,32,160)==0);
  assert(de_image_hit(&view,1,176,78,0,32,160)==SIZE_MAX);
  assert(de_image_hit(&view,1,100,116,0,32,160)==SIZE_MAX);
  assert(de_image_hit(&view,1,100,160,0,32,160)==SIZE_MAX);
  assert(de_image_hit(NULL,0,100,78,0,32,160)==SIZE_MAX);
  assert(de_image_hit(NULL,1,100,78,0,32,160)==SIZE_MAX);
  assert(de_image_hit(&view,1,100,78,NAN,32,160)==SIZE_MAX);
  assert(de_image_hit(&view,1,100,78,0,NAN,160)==SIZE_MAX);
  assert(de_image_hit(&view,1,100,78,0,32,NAN)==SIZE_MAX);
  de_image_release(&view);
  assert(de_image_measure(doc,0,24,40,600,144,&view)==EXR_OK);
  assert(view.width==600 && view.height==300);de_image_release(&view);
  assert(de_image_measure(doc,0,24,40,1000,96,&view)==EXR_OK);
  assert(view.width==400 && view.height==200 && view.x==324);de_image_release(&view);
  puts("PASS aspect ratio, centering, DPI, scrolling, toolbar clipping, edges, invalid hit inputs");
  SelectObject(dc,old);DeleteObject(bitmap);DeleteDC(dc);
  exr_edit_doc_free(doc);shell_d2d_destroy(shell);CoUninitialize();return 0;
}
