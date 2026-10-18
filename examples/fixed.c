/* SPDX-License-Identifier: GPL-3.0-only */
#include <exreader.h>
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
static int example_main(int argc,char **argv) {
  exr_fixed_text *text=NULL; exr_fixed_document *document=NULL; exr_font *font=NULL; exr_fixed_open_options options={0}; exr_bitmap bitmap={0}; exr_error error={0}; exr_status status=EXR_OK; size_t page=0,count=0;
  if(argc<3 || argc>5) { fprintf(stderr,"usage: exreader-fixed-example book.pdf|book.cbz output.png [page] [font.ttf]\n"); return 2; }
  if(argc>=4) {
    char *end; unsigned long long value; errno=0;
    if(!argv[3][0] || argv[3][0]=='-' || argv[3][0]=='+') return 2;
    value=strtoull(argv[3],&end,10); if(errno || *end || value>SIZE_MAX) return 2; page=(size_t)value;
  }
  options.struct_size=sizeof(options);
  if(argc==5) status=exr_font_open(argv[4],&font,&error);
  options.fallback_font=font;
  if(status==EXR_OK) status=exr_fixed_open(argv[1],&options,&document,&error);
  exr_font_free(font); /* The opened document retains its fallback font. */
  if(status==EXR_OK) status=exr_fixed_load_text(document,page,NULL,&text,&error);
  if(status==EXR_OK) { size_t bytes,regions; exr_fixed_text_string(text,&bytes); exr_fixed_text_regions(text,&regions); printf("text_bytes=%zu regions=%zu\n",bytes,regions); }
  exr_fixed_text_free(text);
  if(status==EXR_OK) status=exr_fixed_render(document,page,1,NULL,&bitmap,&error);
  if(status==EXR_OK) status=exr_bitmap_write_png(&bitmap,argv[2],&error);
  if(status==EXR_OK) { exr_fixed_pages(document,&count); printf("pages=%zu rendered=%zu bitmap=%ux%u\n",count,page,bitmap.width,bitmap.height); }
  else fprintf(stderr,"%d: %s\n",status,error.message);
  exr_bitmap_free(&bitmap); exr_fixed_free(document); return status==EXR_OK ? 0 : 1;
}
#include "entry.h"
