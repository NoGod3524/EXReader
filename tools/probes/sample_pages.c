/* External read-only CLI: count pages, render exactly five positions, no files. */
#include "exreader.h"
#include <windows.h>
#include <ctype.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static double now_ms(void){LARGE_INTEGER n,f;QueryPerformanceCounter(&n);QueryPerformanceFrequency(&f);return 1000.0*n.QuadPart/f.QuadPart;}
static const char *positions[]={"first","25%","50%","75%","last"};
static void json_error(const char *s){putchar('"');for(;*s && *s!='\n' && *s!='\r';s++){if(*s=='"' || *s=='\\')putchar('\\');if((unsigned char)*s>=32)putchar(*s);}putchar('"');}
static void emit(size_t pos,size_t index,int ok,double ms,exr_status status,const exr_error *error){
  printf("SAMPLE {\"pos\":\"%s\",\"page_index\":%zu,\"ok\":%s,\"render_ms\":%.6f,\"status\":%d,\"first_error\":",positions[pos],index,ok ? "true":"false",ms,(int)status);
  json_error(ok ? "":error->message);puts("}");fflush(stdout);
}
static int example_main(int argc,char **argv){
  exr_font *font=NULL;exr_publication *pub=NULL;exr_document *doc=NULL;exr_pager *pager=NULL;exr_layout *page=NULL;exr_fixed_document *fixed=NULL;
  exr_fixed_open_options opts={0};exr_error error={0};exr_status status=EXR_ARGUMENT;
  exr_layout_config config=exr_layout_config_defaults();size_t parts=1,total=0,calls=0,failed=0,*counts=NULL,indices[5]={0};int rc=1,is_pdf=0,is_epub=0;
  if(argc!=3)return 2;
  const char *extension=strrchr(argv[1],'.');char ext[8]={0};if(extension && strlen(extension)<sizeof(ext))for(size_t i=0;extension[i];i++)ext[i]=(char)tolower((unsigned char)extension[i]);
  is_pdf=!strcmp(ext,".pdf");is_epub=!strcmp(ext,".epub");
  config.page=(exr_layout_options){720,1040,36,28,1.5f,10};
  status=exr_font_open(argv[2],&font,&error);if(status)goto done;
  if(is_pdf){opts.struct_size=sizeof(opts);opts.fallback_font=font;status=exr_fixed_open(argv[1],&opts,&fixed,&error);if(status)goto done;exr_fixed_pages(fixed,&total);}
  else{
    if(is_epub){status=exr_publication_open(argv[1],&pub,&error);if(status)goto done;exr_publication_parts(pub,&parts);}
    counts=calloc(parts,sizeof(*counts));if(!counts){status=EXR_MEMORY;goto done;}
    for(size_t p=0;p<parts;p++){
      status=is_epub ? exr_publication_load(pub,p,&doc,&error):exr_document_open(argv[1],&doc,&error);if(status)goto done;
      status=exr_pager_create(doc,font,&config,&pager,&error);if(status)goto done;
      for(;;){status=exr_pager_next(pager,&page,&error);if(status)goto done;if(!page)break;counts[p]++;total++;exr_layout_free(page);page=NULL;}
      exr_pager_free(pager);pager=NULL;exr_document_free(doc);doc=NULL;
    }
  }
  if(!total){status=EXR_FORMAT;strcpy(error.message,"Input has no pages");goto done;}
  indices[1]=(total-1)/4;indices[2]=(total-1)/2;indices[3]=3*(total-1)/4;indices[4]=total-1;
  if(is_pdf){
    size_t count=0;const exr_fixed_page *view=exr_fixed_pages(fixed,&count);
    for(size_t i=0;i<5;i++){
      const exr_page_geometry *g=&view[indices[i]].geometry;
      double width=(g->bounds[2]-g->bounds[0])*g->unit_scale,height=(g->bounds[3]-g->bounds[1])*g->unit_scale;
      double scale=fmin(1,720/fmax(width,height));exr_bitmap bitmap={0};error=(exr_error){0};
      double started=now_ms();status=exr_fixed_render(fixed,indices[i],scale,NULL,&bitmap,&error);double elapsed=now_ms()-started;
      int ok=status==EXR_OK && bitmap.pixels && bitmap.width && bitmap.height && bitmap.channels==4;
      if(!ok && !status){status=EXR_FORMAT;strcpy(error.message,"Invalid RGBA bitmap");}
      emit(i,indices[i],ok,elapsed,status,&error);calls++;failed+=!ok;exr_bitmap_free(&bitmap);
    }
  }else{
    size_t offset=0;
    for(size_t p=0;p<parts;p++){
      int selected=0;size_t last=0;
      for(size_t i=0;i<5;i++)if(indices[i]>=offset && indices[i]<offset+counts[p]){selected=1;last=indices[i]-offset;}
      if(!selected){offset+=counts[p];continue;}
      status=is_epub ? exr_publication_load(pub,p,&doc,&error):exr_document_open(argv[1],&doc,&error);if(status)goto done;
      status=exr_pager_create(doc,font,&config,&pager,&error);if(status)goto done;
      for(size_t local=0;local<=last;local++){
        status=exr_pager_next(pager,&page,&error);if(status || !page)goto done;
        for(size_t i=0;i<5;i++)if(indices[i]==offset+local){
          exr_bitmap bitmap={0};error=(exr_error){0};double started=now_ms();
          status=exr_render_page_color(page,exr_layout_font(page),0,&bitmap,&error);double elapsed=now_ms()-started;
          int ok=status==EXR_OK && bitmap.pixels && bitmap.width==720 && bitmap.height==1040 && bitmap.channels==4;
          if(!ok && !status){status=EXR_FORMAT;strcpy(error.message,"Invalid RGBA bitmap");}
          emit(i,indices[i],ok,elapsed,status,&error);calls++;failed+=!ok;exr_bitmap_free(&bitmap);
        }
        exr_layout_free(page);page=NULL;
      }
      exr_pager_free(pager);pager=NULL;exr_document_free(doc);doc=NULL;offset+=counts[p];
    }
  }
  rc=failed ? 1:0;
done:
  if(rc && error.message[0])fprintf(stderr,"Error %d: %s\n",(int)status,error.message);
  printf("SAMPLE_BOOK {\"pages\":%zu,\"parts\":%zu,\"render_calls\":%zu,\"failed_renders\":%zu,\"status\":%d}\n",total,parts,calls,failed,(int)status);fflush(stdout);
  free(counts);exr_layout_free(page);exr_pager_free(pager);exr_document_free(doc);exr_publication_free(pub);exr_fixed_free(fixed);exr_font_free(font);return rc;
}
#include "C:/Users/Oscar/Documents/Codex/EXReader-real-books-20261105/examples/entry.h"
