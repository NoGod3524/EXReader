/* SPDX-License-Identifier: MIT */
#define _POSIX_C_SOURCE 200809L
#include "exreader.h"
#include <inttypes.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/resource.h>
#include <time.h>

/* Installed public SDK only. Timings exclude hashing, PPM writes and free. */
#define SEQUENTIAL 32
#define RANDOM 16
#define MAX_SAMPLES 65
typedef struct {
  const char *phase;
  size_t part,page;
  double layout_ms,render_ms,total_ms;
  uint32_t width,height;
  uint64_t bitmap_bytes,hash,fixed_document_bytes;
  uint64_t text_hash,text_bytes;
  size_t layout_bytes,text_start,text_end;
  int oversize_fallback,cache_rejection_status;
  double failed_cache_ms;
  exr_chapter_stats memory;
} sample;
typedef struct { size_t part,page; } route;
static double now_ms(void) {
  struct timespec value;
  if(clock_gettime(CLOCK_MONOTONIC,&value)) return -1;
  return (double)value.tv_sec*1000.0+(double)value.tv_nsec/1000000.0;
}
static uint64_t rss(void) {
  struct rusage value;
  return getrusage(RUSAGE_SELF,&value) || value.ru_maxrss<0 ? 0 : (uint64_t)value.ru_maxrss*1024;
}
static int bitmap_sample(exr_bitmap *bitmap,sample *item,const char *dump) {
  size_t x,y,row=(size_t)bitmap->width*4;
  uint64_t hash=UINT64_C(14695981039346656037);
  FILE *file=NULL;
  if(!bitmap->pixels || !bitmap->width || !bitmap->height || bitmap->width>4096 ||
     bitmap->height>4096 || bitmap->channels!=4 || bitmap->stride<row) return 0;
  item->width=bitmap->width;item->height=bitmap->height;
  item->bitmap_bytes=(uint64_t)bitmap->stride*bitmap->height;
  if(dump) { file=fopen(dump,"wb");if(!file) return 0;
    fprintf(file,"P6\n%u %u\n255\n",bitmap->width,bitmap->height); }
  for(y=0;y<bitmap->height;y++) for(x=0;x<row;x++) {
    unsigned char value=bitmap->pixels[y*bitmap->stride+x];
    hash^=value;hash*=UINT64_C(1099511628211);
    if(file && x%4!=3 && fputc(value,file)==EOF) { fclose(file);return 0; }
  }
  item->hash=hash;
  return !file || fclose(file)==0;
}
static int fixed_page(exr_fixed_document *fixed,size_t page,const char *phase,
                      sample *item,const char *dump,exr_error *error) {
  exr_fixed_render_options options={0};exr_bitmap bitmap={0};
  double at=now_ms();int ok;
  options.channels=4;options.background=0xffffffffu;
  item->phase=phase;item->page=page;
  ok=exr_fixed_render(fixed,page,1.0,&options,&bitmap,error)==EXR_OK;
  item->render_ms=item->total_ms=now_ms()-at;
  item->fixed_document_bytes=exr_fixed_memory_size(fixed);
  if(ok) ok=bitmap_sample(&bitmap,item,dump);
  exr_bitmap_free(&bitmap);return ok;
}
static int create_pager(exr_publication *publication,size_t part,exr_font *font,int cached,
                        exr_pager **pager,exr_error *error) {
  exr_layout_config config=exr_layout_config_defaults();
  exr_chapter_options options=exr_chapter_options_defaults();
  exr_pager_free(*pager);*pager=NULL;
  config.page.width=800;config.page.height=1000;config.page.margin=32;config.page.font_size=24;
  options.workspace_budget=16u*1024u*1024u;options.window_bytes=16u*1024u;
  return exr_publication_pager_create(publication,part,font,&config,&options,pager,error)==EXR_OK &&
    (!cached || (exr_pager_set_cache(*pager,2,8u*1024u*1024u,error)==EXR_OK &&
    exr_pager_set_checkpoints(*pager,4,2u*1024u*1024u,16,error)==EXR_OK));
}
static exr_status text_sink(void *context,const char *text,size_t bytes,exr_error *error) {
  sample *item=context;size_t i;(void)error;
  for(i=0;i<bytes;i++) { item->text_hash^=(unsigned char)text[i];item->text_hash*=UINT64_C(1099511628211); }
  item->text_bytes+=bytes;return EXR_OK;
}
static int text_sample(exr_pager *pager,const exr_layout *layout,sample *item,exr_error *error) {
  size_t count=0;const exr_page *pages=exr_layout_pages(layout,&count);
  if(!pages || count!=1) return 0;
  item->layout_bytes=exr_layout_memory_size(layout);
  item->text_start=pages[0].start;item->text_end=pages[0].end;
  item->text_hash=UINT64_C(14695981039346656037);item->text_bytes=0;
  return exr_pager_read_text(pager,item->text_start,item->text_end,text_sink,item,NULL,error)==EXR_OK;
}
static int reflow_page(exr_pager *pager,size_t part,size_t page,
                       const char *phase,int cached,sample *item,exr_error *error) {
  const exr_layout *layout=NULL;exr_layout *owned=NULL;exr_bitmap bitmap={0};double at=now_ms();int ok;
  item->phase=phase;item->part=part;item->page=page;
  if(cached) {
    if(exr_pager_get(pager,page,&layout,error)!=EXR_OK) {
      item->failed_cache_ms=now_ms()-at;item->cache_rejection_status=(int)error->code;return 0;
    }
  } else {
    if(exr_pager_next(pager,&owned,error)!=EXR_OK) return 0;
    layout=owned;
  }
  item->layout_ms=now_ms()-at;
  if(!layout) return 2;
  at=now_ms();ok=exr_render_page_ex(layout,exr_layout_font(layout),0,4,NULL,&bitmap,error)==EXR_OK;
  item->render_ms=now_ms()-at;item->total_ms=item->layout_ms+item->render_ms;
  item->memory=exr_pager_chapter_statistics(pager);
  if(ok) ok=bitmap_sample(&bitmap,item,NULL);
  if(ok) ok=text_sample(pager,layout,item,error);
  exr_bitmap_free(&bitmap);exr_layout_free(owned);return ok;
}
static int oversize_owned_page(exr_publication *publication,exr_font *font,route target,sample *item) {
  exr_pager *probe=NULL;exr_layout *layout=NULL;exr_error error={0};exr_bitmap bitmap={0};
  size_t page;double at=now_ms();int ok=0;
  if(item->cache_rejection_status!=EXR_LIMIT || !create_pager(publication,target.part,font,0,&probe,&error)) goto done;
  for(page=0;page<=target.page;page++) {
    exr_layout_free(layout);layout=NULL;
    if(exr_pager_next(probe,&layout,&error)!=EXR_OK || !layout) goto done;
  }
  item->layout_ms=item->failed_cache_ms+now_ms()-at;
  if(exr_layout_memory_size(layout)<=8u*1024u*1024u) goto done;
  at=now_ms();if(exr_render_page_ex(layout,exr_layout_font(layout),0,4,NULL,&bitmap,&error)!=EXR_OK) goto done;
  item->render_ms=now_ms()-at;item->total_ms=item->layout_ms+item->render_ms;
  item->memory=exr_pager_chapter_statistics(probe);
  if(!bitmap_sample(&bitmap,item,NULL) || !text_sample(probe,layout,item,&error)) goto done;
  item->oversize_fallback=1;ok=1;
done:
  exr_bitmap_free(&bitmap);exr_layout_free(layout);exr_pager_free(probe);return ok;
}
static void diagnose_cache_failure(exr_publication *publication,exr_font *font,route target) {
  exr_pager *probe=NULL;exr_layout *layout=NULL;exr_error error={0};
  size_t page,glyphs=0,lines=0,boxes=0,i,images=0;const exr_box *items;
  if(!create_pager(publication,target.part,font,0,&probe,&error)) goto done;
  for(page=0;page<=target.page;page++) {
    exr_layout_free(layout);layout=NULL;
    if(exr_pager_next(probe,&layout,&error)!=EXR_OK || !layout) goto done;
  }
  (void)exr_layout_glyphs(layout,&glyphs);(void)exr_layout_lines(layout,&lines);
  items=exr_layout_boxes(layout,&boxes);
  fprintf(stderr,"{\"cache_failure_probe\":{\"part\":%zu,\"page\":%zu,\"layout_bytes\":%zu,"
          "\"glyphs\":%zu,\"lines\":%zu,\"boxes\":%zu,\"image_boxes\":[",target.part,target.page,
          exr_layout_memory_size(layout),glyphs,lines,boxes);
  for(i=0;i<boxes;i++) if(items[i].kind==EXR_BOX_IMAGE) {
    const exr_bitmap *image=exr_layout_image(layout,items[i].resource);
    fprintf(stderr,"%s{\"resource\":%zu,\"box_width\":%.6f,\"box_height\":%.6f,"
            "\"decoded_width\":%u,\"decoded_height\":%u,\"decoded_bytes\":%" PRIu64 "}",
            images++?",":"",items[i].resource,items[i].width,items[i].height,
            image?image->width:0,image?image->height:0,image?(uint64_t)image->stride*image->height:0);
  }
  fprintf(stderr,"]}}\n");
done:
  if(error.code!=EXR_OK) fprintf(stderr,"Cache failure secondary probe status=%d: %s\n",(int)error.code,error.message);
  exr_layout_free(layout);exr_pager_free(probe);
}
int main(int argc,char **argv) {
  exr_font *font=NULL;exr_fixed_document *fixed=NULL;exr_publication *publication=NULL;
  exr_pager *pager=NULL;exr_error error={0};exr_fixed_open_options options={0};
  const exr_part *parts=NULL;sample samples[MAX_SAMPLES]={{0}};route routes[SEQUENTIAL+1]={{0}};
  size_t count=0,part_count=0,page_count=0,part=0,page=0,i,route_count=0,current_part=SIZE_MAX,fallbacks=0;
  uint32_t random=20261023u;uint64_t baseline=rss(),peak,directory_bytes=0;
  double start=now_ms(),at,font_ms=0,open_ms=0,first_ms=0;int ok=0,is_pdf,result;
  const char *stage="arguments";char *selected=NULL,*token,*save=NULL;
  if(argc!=6) { fprintf(stderr,"Usage: reading-real-benchmark pdf|epub input font dumpdir selected-pages-csv\n");return 2; }
  is_pdf=!strcmp(argv[1],"pdf");
  if(!is_pdf && strcmp(argv[1],"epub")) goto finish;
  stage="font_open";at=now_ms();
  if(exr_font_open(argv[3],&font,&error)!=EXR_OK) goto finish;
  font_ms=now_ms()-at;stage="open";at=now_ms();
  if(is_pdf) {
    options.struct_size=sizeof(options);options.fallback_font=font;
    if(exr_fixed_open(argv[2],&options,&fixed,&error)!=EXR_OK) goto finish;
    if(!exr_fixed_pages(fixed,&page_count) || !page_count) goto finish;
    directory_bytes=exr_fixed_memory_size(fixed);
  } else {
    if(exr_publication_open(argv[2],&publication,&error)!=EXR_OK) goto finish;
    parts=exr_publication_parts(publication,&part_count);
    while(part<part_count && !parts[part].in_reading_order) part++;
    if(part==part_count || !create_pager(publication,part,font,0,&pager,&error)) goto finish;
    current_part=part;
  }
  open_ms=now_ms()-at;stage="first";
  result=is_pdf ? fixed_page(fixed,0,"first",&samples[count],NULL,&error) :
                 reflow_page(pager,part,0,"first",0,&samples[count],&error);
  if(result!=1) goto finish;
  count++;first_ms=font_ms+open_ms+samples[0].total_ms;routes[route_count++]=(route){part,0};
  stage="sequential";
  for(i=0;i<SEQUENTIAL;i++) {
    if(is_pdf) {
      page=(i+1)%page_count;
      if(!fixed_page(fixed,page,"sequential",&samples[count],NULL,&error)) goto finish;
    } else {
      double transition=0;
      page++;
      for(;;) {
        result=reflow_page(pager,part,page,"sequential",0,&samples[count],&error);
        if(result!=2) break;
        transition+=samples[count].layout_ms;
        do { part++; } while(part<part_count && !parts[part].in_reading_order);
        if(part==part_count) break;
        at=now_ms();if(!create_pager(publication,part,font,0,&pager,&error)) goto finish;
        transition+=now_ms()-at;current_part=part;page=0;
      }
      if(part==part_count) break;
      if(result!=1) goto finish;
      samples[count].layout_ms+=transition;samples[count].total_ms+=transition;
      routes[route_count++]=(route){part,page};
    }
    count++;
  }
  stage="random";
  /* next() has an explicit EOF contract; get() is a separate borrowed-page mode. */
  current_part=SIZE_MAX;
  for(i=0;i<RANDOM;i++) {
    random=random*1664525u+1013904223u;
    if(is_pdf) {
      if(!fixed_page(fixed,random%page_count,"random",&samples[count],NULL,&error)) goto finish;
    } else {
      route target=routes[random%route_count];double transition=0;
      if(target.part!=current_part) {
        at=now_ms();if(!create_pager(publication,target.part,font,1,&pager,&error)) goto finish;
        transition=now_ms()-at;current_part=target.part;
      }
      if(reflow_page(pager,target.part,target.page,"random",1,&samples[count],&error)!=1) {
        if(!oversize_owned_page(publication,font,target,&samples[count])) {
          diagnose_cache_failure(publication,font,target);goto finish;
        }
        error.code=EXR_OK;error.message[0]='\0';
      }
      samples[count].layout_ms+=transition;samples[count].total_ms+=transition;
    }
    count++;
  }
  stage="reference";
  if(is_pdf && strcmp(argv[5],"-")) {
    selected=strdup(argv[5]);if(!selected) goto finish;
    for(token=strtok_r(selected,",",&save);token;token=strtok_r(NULL,",",&save)) {
      char name[4096],*end;unsigned long value=strtoul(token,&end,10);
      if(*end || value>=page_count || count==MAX_SAMPLES ||
         snprintf(name,sizeof(name),"%s/page-%lu.ppm",argv[4],value)>=(int)sizeof(name)) goto finish;
      if(!fixed_page(fixed,(size_t)value,"reference",&samples[count],name,&error)) goto finish;
      count++;
    }
  }
  ok=1;stage="complete";
finish:
  peak=rss();if(!peak || start<0) ok=0;
  for(i=0;i<count;i++) if(samples[i].oversize_fallback) fallbacks++;
  printf("{\"schema\":1,\"success\":%s,\"stage\":\"%s\",\"status\":%d,\"engine_version\":\"%s\","
         "\"engine_abi\":%u,\"mode\":\"%s\",\"font_open_ms\":%.6f,\"open_ms\":%.6f,\"first_visible_ms\":%.6f,"
         "\"baseline_peak_rss_bytes\":%" PRIu64 ",\"peak_rss_bytes\":%" PRIu64 ","
         "\"fixed_directory_bytes\":%" PRIu64 ",\"page_count\":%zu,\"part_count\":%zu,\"oversize_fallbacks\":%zu,\"samples\":[",
         ok?"true":"false",stage,(int)error.code,exr_version(),exr_abi_version(),argv[1],font_ms,open_ms,first_ms,
         baseline,peak,directory_bytes,page_count,part_count,fallbacks);
  for(i=0;i<count;i++) {
    sample *s=&samples[i];exr_chapter_stats *m=&s->memory;
    printf("%s{\"phase\":\"%s\",\"part\":%zu,\"page\":%zu,\"layout_ms\":%.6f,\"render_ms\":%.6f,"
           "\"total_ms\":%.6f,\"width\":%u,\"height\":%u,\"bitmap_bytes\":%" PRIu64 ","
           "\"fixed_document_bytes\":%" PRIu64 ","
           "\"text_hash\":\"%016" PRIx64 "\",\"text_bytes\":%" PRIu64 ",\"text_start\":%zu,\"text_end\":%zu,"
           "\"layout_bytes\":%zu,\"oversize_fallback\":%d,\"cache_rejection_status\":%d,\"failed_cache_ms\":%.6f,"
           "\"pixel_hash\":\"%016" PRIx64 "\",\"workspace_bytes\":%zu,\"peak_workspace_bytes\":%zu,"
           "\"index_bytes\":%zu,\"cache_bytes\":%zu,\"checkpoint_bytes\":%zu,\"explicit_snapshot_bytes\":%zu}",
           i?",":"",s->phase,s->part,s->page,s->layout_ms,s->render_ms,s->total_ms,s->width,s->height,
           s->bitmap_bytes,s->fixed_document_bytes,s->text_hash,s->text_bytes,s->text_start,s->text_end,
           s->layout_bytes,s->oversize_fallback,s->cache_rejection_status,s->failed_cache_ms,
           s->hash,m->parse_workspace_bytes,m->peak_parse_workspace_bytes,m->index_bytes,
           m->page_cache_bytes,m->checkpoint_bytes,m->explicit_snapshot_bytes);
  }
  printf("]}\n");if(!ok) fprintf(stderr,"Native measurement failed at %s status=%d: %s\n",stage,(int)error.code,error.message);
  free(selected);exr_pager_free(pager);exr_publication_free(publication);exr_fixed_free(fixed);exr_font_free(font);
  return ok?0:1;
}
