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
  exr_layout_config config=exr_layout_config_defaults();exr_status s=EXR_ARGUMENT;size_t parts=0,total=0,current=0,middle=0;int rc=1;
  page_metric *metrics=NULL;size_t capacity=0;
  if(argc!=5 && argc!=6){fputs("Usage: exreader-render-visual book.epub font output-directory shortname [duplicate-shortname]\n",stderr);return 2;}
  config.page=(exr_layout_options){1280,800,36,18,1.5f,10};
  config.user_css="html,body{font-size:18px!important}";
  stage="font";s=exr_font_open(argv[2],&font,&error);if(s!=EXR_OK)goto done;
  stage="open";s=exr_publication_open(argv[1],&publication,&error);if(s!=EXR_OK)goto done;
  exr_publication_parts(publication,&parts);
  /* First pass counts all paged parts. Render first page while it is alive. */
  for(size_t part=0;part<parts;part++){
    stage="load";s=exr_publication_load(publication,part,&doc,&error);if(s!=EXR_OK)goto done;
    stage="paginate";s=exr_pager_create(doc,font,&config,&pager,&error);if(s!=EXR_OK)goto done;
    for(;;){s=exr_pager_next(pager,&page,&error);if(s!=EXR_OK)goto done;if(!page)break;
      total++;
      if(total>capacity){size_t next=capacity ? capacity*2:256;page_metric *grown=realloc(metrics,next*sizeof(*metrics));if(!grown){s=EXR_MEMORY;goto done;}metrics=grown;capacity=next;}
      {size_t glyphs=0,boxes=0,images=0;exr_layout_glyphs(page,&glyphs);const exr_box *b=exr_layout_boxes(page,&boxes);for(size_t j=0;j<boxes;j++)images+=b[j].kind==EXR_BOX_IMAGE;metrics[total-1]=(page_metric){glyphs,images};}
      if(total==1){s=save_page(page,argv[3],argv[4],1);if(s!=EXR_OK)goto done;if(argc==6){s=save_page(page,argv[3],argv[5],1);if(s!=EXR_OK)goto done;}}
      exr_layout_free(page);page=NULL;
    }
    exr_pager_free(pager);pager=NULL;exr_document_free(doc);doc=NULL;
  }
  if(!total){strcpy(error.message,"Publication has no paginated pages");s=EXR_FORMAT;goto done;}
  middle=(total+1)/2;
  if(!strcmp(argv[4],"pachinko") || !strcmp(argv[4],"diary")){
    size_t anchor=middle,best=SIZE_MAX;
    for(size_t i=total/4;i<total*3/4;i++){
      int eligible=!strcmp(argv[4],"pachinko") ? metrics[i].glyphs>=100 : metrics[i].glyphs>=20 && metrics[i].images>0;
      size_t index=i+1,distance=index>anchor ? index-anchor:anchor-index;
      if(eligible && distance<best){best=distance;middle=index;}
    }
  }
  /* Second pass seeks the middle in the exact same global page numbering. */
  for(size_t part=0;part<parts;part++){
    stage="load";s=exr_publication_load(publication,part,&doc,&error);if(s!=EXR_OK)goto done;
    stage="paginate";s=exr_pager_create(doc,font,&config,&pager,&error);if(s!=EXR_OK)goto done;
    for(;;){s=exr_pager_next(pager,&page,&error);if(s!=EXR_OK)goto done;if(!page)break;current++;
      if(current==middle){s=save_page(page,argv[3],argv[4],middle);if(s!=EXR_OK)goto done;rc=0;goto done;}
      exr_layout_free(page);page=NULL;
    }
    exr_pager_free(pager);pager=NULL;exr_document_free(doc);doc=NULL;
  }
done:
  if(rc && error.message[0])fprintf(stderr,"Error %d: %s\n",(int)s,error.message);
  printf("VISUAL_BOOK {\"parts\":%zu,\"pages\":%zu,\"middle_page\":%zu,\"status\":%d,\"success\":%s}\n",parts,total,middle,(int)s,rc==0 ? "true":"false");fflush(stdout);
  free(metrics);exr_layout_free(page);exr_pager_free(pager);exr_document_free(doc);exr_publication_free(publication);exr_font_free(font);return rc;
}
#include "C:/Users/Oscar/Documents/Codex/EXReader-real-books-20261105/examples/entry.h"
