/* Local CLI only: paginated global pages, explicit viewport/font settings. */
#include "exreader.h"
#include <windows.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static double clock_ms(void){LARGE_INTEGER n,f;QueryPerformanceCounter(&n);QueryPerformanceFrequency(&f);return 1000.0*n.QuadPart/f.QuadPart;}
static exr_error error;
static const char *stage="arguments";
typedef struct {size_t glyphs,images;} page_metric;
static exr_status save_page(const exr_layout *page,const char *directory,const char *slug,size_t index){
  char output[2048],name[200];exr_bitmap bitmap={0};size_t n=0,vertical=0,missing=0,boxes=0,images=0;
  float min=1e9f,max=0;const exr_glyph *g=exr_layout_glyphs(page,&n);
  const exr_box *box=exr_layout_boxes(page,&boxes);for(size_t i=0;i<boxes;i++)images+=box[i].kind==EXR_BOX_IMAGE;
  for(size_t i=0;i<n;i++){vertical+=!!(g[i].flags&EXR_GLYPH_VERTICAL);missing+=!!(g[i].flags&EXR_GLYPH_MISSING);if(g[i].size<min)min=g[i].size;if(g[i].size>max)max=g[i].size;}
  if(!n)min=0;
  snprintf(name,sizeof(name),"%s-%zu.png",slug,index);snprintf(output,sizeof(output),"%s/%s",directory,name);
  stage="render";double started=clock_ms();exr_status s=exr_render_page_color(page,exr_layout_font(page),0,&bitmap,&error);double elapsed=clock_ms()-started;
  if(s==EXR_OK && (bitmap.width!=1280 || bitmap.height!=800 || bitmap.channels!=4)){s=EXR_FORMAT;strcpy(error.message,"Unexpected rendered bitmap geometry");}
  if(s==EXR_OK){stage="write_png";s=exr_bitmap_write_png(&bitmap,output,&error);}
  printf("VISUAL_IMAGE {\"filename\":\"%s\",\"page\":%zu,\"width\":1280,\"height\":800,\"font_size\":18,\"render_ms\":%.6f,\"success\":%s,\"status\":%d,\"writing_mode\":%d,\"glyphs\":%zu,\"vertical_glyphs\":%zu,\"missing_glyphs\":%zu,\"image_boxes\":%zu,\"glyph_font_min\":%.6f,\"glyph_font_max\":%.6f}\n",name,index,elapsed,s==EXR_OK ? "true":"false",(int)s,(int)exr_layout_writing_mode(page),n,vertical,missing,images,min,max);fflush(stdout);
  exr_bitmap_free(&bitmap);return s;
}

static int example_main(int argc,char **argv){
  exr_font *font=NULL;exr_publication *publication=NULL;exr_document *doc=NULL;exr_pager *pager=NULL;exr_layout *page=NULL;
  exr_layout_config config=exr_layout_config_defaults();exr_status s=EXR_ARGUMENT;size_t parts=0,total=0;int rc=1;
  if(argc!=4){fputs("Usage: exreader-render-neighbors book font output-directory\n",stderr);return 2;}
  config.page=(exr_layout_options){1280,800,36,18,1.5f,10};config.user_css="html,body{font-size:18px!important}";
  s=exr_font_open(argv[2],&font,&error);if(s!=EXR_OK)goto done;
  s=exr_publication_open(argv[1],&publication,&error);if(s!=EXR_OK)goto done;exr_publication_parts(publication,&parts);
  for(size_t part=0;part<parts;part++){
    size_t first=total+1,local=0,text_bytes=0,end=0;
    s=exr_publication_load(publication,part,&doc,&error);if(s!=EXR_OK)goto done;
    (void)exr_document_text(doc,&text_bytes);
    s=exr_pager_create(doc,font,&config,&pager,&error);if(s!=EXR_OK)goto done;
    for(;;){s=exr_pager_next(pager,&page,&error);if(s!=EXR_OK)goto done;if(!page)break;total++;local++;
      size_t count=0,glyphs=0,lines=0,boxes=0,images=0;const exr_page *view=exr_layout_pages(page,&count);
      exr_layout_glyphs(page,&glyphs);exr_layout_lines(page,&lines);const exr_box *box=exr_layout_boxes(page,&boxes);
      for(size_t i=0;i<boxes;i++)images+=box[i].kind==EXR_BOX_IMAGE;
      if(count)end=view[count-1].end;
      if(total>=255 && total<=260)printf("NEIGHBOR_PAGE {\"page\":%zu,\"part_index\":%zu,\"local_page\":%zu,\"glyphs\":%zu,\"lines\":%zu,\"images\":%zu,\"document_text_bytes\":%zu,\"page_start\":%zu,\"page_end\":%zu}\n",total,part,local,glyphs,lines,images,text_bytes,count ? view[0].start:0,end);
      if(total==256 || total==258){s=save_page(page,argv[3],"pachinko",total);if(s!=EXR_OK)goto done;}
      exr_layout_free(page);page=NULL;
    }
    if(total>=255 && first<=260)printf("NEIGHBOR_PART {\"part_index\":%zu,\"first_page\":%zu,\"last_page\":%zu,\"pages\":%zu,\"document_text_bytes\":%zu,\"last_page_end\":%zu,\"pager_eof\":true}\n",part,first,total,local,text_bytes,end);
    exr_pager_free(pager);pager=NULL;exr_document_free(doc);doc=NULL;
    if(total>=260){rc=0;goto done;}
  }
done:
  if(rc && error.message[0])fprintf(stderr,"Error %d: %s\n",(int)s,error.message);
  exr_layout_free(page);exr_pager_free(pager);exr_document_free(doc);exr_publication_free(publication);exr_font_free(font);return rc;
}
#include "C:/Users/Oscar/Documents/Codex/EXReader-real-books-20261105/examples/entry.h"
