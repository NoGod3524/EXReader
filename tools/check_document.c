/* SPDX-License-Identifier: MIT */
#include "exreader.h"
#include <errno.h>
#include <ctype.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static int inspect_main(int argc,char **argv) {
  exr_font *font=NULL;exr_publication *publication=NULL;exr_document *document=NULL;
  exr_pager *pager=NULL;exr_layout *page=NULL;exr_fixed_document *fixed=NULL;
  exr_fixed_text *text=NULL;exr_bitmap bitmap={0};exr_error error={0};
  exr_fixed_open_options options={0};exr_layout_config config=exr_layout_config_defaults();
  exr_status status=EXR_ARGUMENT;const char *stage="arguments";size_t parts=0,pages=0,bytes=0;
  size_t completed_parts=0,max_pages=0;int complete=0,valid_bitmap=1;
  if(argc<3 || argc>4) return 2;
  if(argc==4) {
    char *end;unsigned long long n;
    for(const char *p=argv[3];*p;p++) if(*p<'0' || *p>'9') return 2;
    errno=0;n=strtoull(argv[3],&end,10);
    if(!argv[3][0] || errno==ERANGE || *end || n>SIZE_MAX) return 2;
    max_pages=(size_t)n;
  }
  stage="font";status=exr_font_open(argv[2],&font,&error);if(status!=EXR_OK) goto done;
  stage="open";
  { const char *extension=strrchr(argv[1],'.');char ext[8]={0};
    if(extension && strlen(extension)<sizeof(ext))
      for(size_t i=0;extension[i];i++) ext[i]=(char)tolower((unsigned char)extension[i]);
    int is_fixed=!strcmp(ext,".pdf") || !strcmp(ext,".cbz");
    if(is_fixed) {
      const exr_fixed_page *source;size_t count=0;
      options.struct_size=sizeof(options);options.fallback_font=font;
      status=exr_fixed_open(argv[1],&options,&fixed,&error);if(status!=EXR_OK) goto done;
      source=exr_fixed_pages(fixed,&count);parts=1;
      if(count && !source) { status=EXR_FORMAT;goto done; }
      for(size_t i=0;i<count;i++) {
        double width=(source[i].geometry.bounds[2]-source[i].geometry.bounds[0])*source[i].geometry.unit_scale;
        double height=(source[i].geometry.bounds[3]-source[i].geometry.bounds[1])*source[i].geometry.unit_scale;
        double scale;
        if(max_pages && pages>=max_pages) goto done;
        if(!(width>0) || !(height>0) || !isfinite(width) || !isfinite(height)) { status=EXR_FORMAT;goto done; }
        scale=fmin(1,720/fmax(width,height));
        stage="render";status=exr_fixed_render(fixed,i,scale,NULL,&bitmap,&error);if(status!=EXR_OK) goto done;
        valid_bitmap=bitmap.pixels && bitmap.width && bitmap.height && bitmap.channels==4 && bitmap.stride>=(size_t)bitmap.width*4;
        exr_bitmap_free(&bitmap);
        if(!valid_bitmap) { status=EXR_FORMAT;goto done; }
        stage="text";status=exr_fixed_load_text(fixed,i,NULL,&text,&error);if(status!=EXR_OK) goto done;
        { size_t n=0;const char *value=exr_fixed_text_string(text,&n);
          if(n && !value) { status=EXR_FORMAT;goto done; }bytes+=n;
        }
        exr_fixed_text_free(text);text=NULL;pages++;
      }
      completed_parts=1;complete=1;
    } else {
      stage="open";
      if(!strcmp(ext,".epub")) {
        status=exr_publication_open(argv[1],&publication,&error);if(status!=EXR_OK) goto done;
        (void)exr_publication_parts(publication,&parts);
      } else {
        status=exr_document_open(argv[1],&document,&error);if(status!=EXR_OK) goto done;
        parts=1;
      }
      config.page=(exr_layout_options){720,1040,36,28,1.5f,10};
      for(size_t i=0;i<parts;i++) {
        if(publication) {
          stage="load";status=exr_publication_load(publication,i,&document,&error);if(status!=EXR_OK) goto done;
        }
        { size_t n=0;const char *value=exr_document_text(document,&n);
          if(n && !value) { status=EXR_FORMAT;goto done; }bytes+=n;
        }
        stage="paginate";status=exr_pager_create(document,font,&config,&pager,&error);if(status!=EXR_OK) goto done;
        for(;;) {
          stage="paginate";status=exr_pager_next(pager,&page,&error);if(status!=EXR_OK) goto done;
          if(!page) break;
          if(max_pages && pages>=max_pages) goto done;
          stage="render";status=exr_render_page_color(page,exr_layout_font(page),0,&bitmap,&error);if(status!=EXR_OK) goto done;
          valid_bitmap=bitmap.pixels && bitmap.width==720 && bitmap.height==1040 && bitmap.channels==4 && bitmap.stride>=720*4;
          exr_bitmap_free(&bitmap);exr_layout_free(page);page=NULL;
          if(!valid_bitmap) { status=EXR_FORMAT;goto done; }
          pages++;
        }
        exr_pager_free(pager);pager=NULL;exr_document_free(document);document=NULL;
        completed_parts++;
      }
      complete=1;
    }
  }
done:
  exr_bitmap_free(&bitmap);exr_layout_free(page);exr_pager_free(pager);
  exr_document_free(document);exr_fixed_text_free(text);exr_fixed_free(fixed);
  exr_publication_free(publication);exr_font_free(font);
  printf("{\"schema\":1,\"engine_version\":\"%s\",\"status\":%d,\"stage\":\"%s\","
         "\"parts\":%zu,\"completed_parts\":%zu,\"pages\":%zu,\"text_bytes\":%zu,"
         "\"complete\":%s}\n",
         exr_version(),(int)status,stage,parts,completed_parts,pages,bytes,
         complete ? "true" : "false");
  return status==EXR_OK && complete ? 0 : 1;
}
#define example_main inspect_main
#include "../examples/entry.h"
