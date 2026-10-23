/* SPDX-License-Identifier: MIT */
/* Installed public-API consumer. Run capture and resolve in separate processes. */
#include "exreader.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

static exr_error error;
static unsigned checks;
#define CHECK(x) do { checks++;if(!(x)) { fprintf(stderr,"resident CFI line %d (%d: %s)\n",__LINE__,error.code,error.message);exit(1); } } while(0)
#define OK(x) CHECK((x)==EXR_OK)
static void *read_file(const char *path,size_t *size) {
  FILE *f=fopen(path,"rb");long length;void *bytes;
  CHECK(f!=NULL);CHECK(!fseek(f,0,SEEK_END));length=ftell(f);CHECK(length>=0);
  CHECK(!fseek(f,0,SEEK_SET));*size=(size_t)length;bytes=malloc(*size+1);CHECK(bytes!=NULL);
  CHECK(fread(bytes,1,*size,f)==*size);CHECK(!fclose(f));((char *)bytes)[*size]=0;return bytes;
}
static void write_file(const char *path,const void *bytes,size_t size) {
  FILE *f=fopen(path,"wb");CHECK(f!=NULL);CHECK(fwrite(bytes,1,size,f)==size);CHECK(!fclose(f));
}
static exr_font *font_open(const char *path) {
  exr_font *font=NULL;size_t size;void *bytes=read_file(path,&size);exr_font_input input={0};
  input.data=bytes;input.size=size;OK(exr_font_create(&input,1,&font,&error));free(bytes);return font;
}
static exr_pager *pager_open(exr_publication *publication,exr_font *font) {
  exr_pager *pager=NULL;exr_layout_config config=exr_layout_config_defaults();
  exr_chapter_options options=exr_chapter_options_defaults();
  config.page=(exr_layout_options){600,860,32,24,1.6f,12};
  config.document_css=1;config.embedded_fonts=1;options.workspace_budget=8*1024*1024;options.window_bytes=64*1024;
  OK(exr_publication_pager_create(publication,0,font,&config,&options,&pager,&error));return pager;
}
static char *convert(exr_pager *pager,size_t offset) {
  char *cfi=NULL;exr_chapter_stats before=exr_pager_chapter_statistics(pager),after;
  OK(exr_pager_cfi_create_at(pager,offset,NULL,&cfi,&error));CHECK(cfi!=NULL);
  after=exr_pager_chapter_statistics(pager);
  CHECK(before.windows_loaded==after.windows_loaded && before.windows_evicted==after.windows_evicted);
  CHECK(!after.explicit_snapshot_bytes);return cfi;
}
static void full_resolve(exr_document *document,const char *cfi,size_t node,size_t offset) {
  exr_cfi_point point={0};size_t chapter=SIZE_MAX;
  OK(exr_document_cfi_resolve(document,cfi,NULL,&chapter,&point,&error));
  CHECK(chapter==0 && point.node==node && point.offset==offset && point.side==0);
}
static int cancelled(void *context) { (void)context;return 1; }
static void suite(const char *epub,exr_font *font) {
  static const char raw[]="  A \t&\n 😀 é  X ";
  static const size_t normalized[]={0,1,2,3,4,8,9,10,12,13,14};
  static const size_t utf16[]={2,3,5,6,8,10,11,12,13,15,16};
  exr_publication *publication=NULL;exr_document *document=NULL;exr_pager *pager;
  exr_layout *page=NULL;const exr_node *nodes;size_t count,node,i,base,old_offset,page_count=0;
  char *cfi=NULL;exr_control control={0};exr_chapter_stats before,after;
  OK(exr_publication_open(epub,&publication,&error));OK(exr_publication_load(publication,0,&document,&error));
  nodes=exr_document_nodes(document,&count);
  for(node=0;node<count;node++) if(nodes[node].kind==EXR_NODE_TEXT && nodes[node].text && !strcmp(nodes[node].text,raw)) break;
  CHECK(node<count);base=nodes[node].start;old_offset=base;
  pager=pager_open(publication,font);OK(exr_pager_next(pager,&page,&error));CHECK(page!=NULL);exr_layout_free(page);page=NULL;
  for(i=0;i<sizeof(normalized)/sizeof(*normalized);i++) {
    cfi=convert(pager,base+normalized[i]);full_resolve(document,cfi,node,utf16[i]);exr_free(cfi);cfi=NULL;
  }
  CHECK(exr_pager_cfi_create_at(pager,base+5,NULL,&cfi,&error)==EXR_ARGUMENT && !cfi);
  CHECK(exr_pager_cfi_create_at(pager,base+11,NULL,&cfi,&error)==EXR_ARGUMENT && !cfi);
  CHECK(exr_pager_cfi_create_at(pager,SIZE_MAX,NULL,&cfi,&error)==EXR_ARGUMENT && !cfi);
  control.cancelled=cancelled;
  CHECK(exr_pager_cfi_create_at(pager,base,&control,&cfi,&error)==EXR_CANCELLED && !cfi);
  /* Rejection must neither poison the pager nor replace its active window. */
  before=exr_pager_chapter_statistics(pager);
  for(i=count;i>0;i--) if(nodes[i-1].kind==EXR_NODE_TEXT && nodes[i-1].end>nodes[i-1].start) break;
  CHECK(i>0 && nodes[i-1].start>65536);
  CHECK(exr_pager_cfi_create_at(pager,nodes[i-1].start+1,NULL,&cfi,&error)==EXR_UNSUPPORTED && !cfi);
  after=exr_pager_chapter_statistics(pager);CHECK(before.windows_loaded==after.windows_loaded);
  cfi=convert(pager,base);exr_free(cfi);cfi=NULL;
  for(;;) {
    const exr_page *pages;size_t n;
    OK(exr_pager_next(pager,&page,&error));CHECK(page!=NULL);pages=exr_layout_pages(page,&n);CHECK(n==1);
    page_count++;
    if(exr_pager_chapter_statistics(pager).windows_loaded>=3) {
      /* The last real ASCII glyph is resident even if a page straddles windows. */
      const exr_glyph *glyphs=exr_layout_glyphs(page,&n);size_t at,j;
      CHECK(n>0);at=glyphs[n-1].start;
      for(j=0;j<count;j++) if(nodes[j].kind==EXR_NODE_TEXT && nodes[j].start<=at && nodes[j].end>at) break;
      CHECK(j<count && nodes[j].text && !strncmp(nodes[j].text,"Edge ",5));
      cfi=convert(pager,at);full_resolve(document,cfi,j,at-nodes[j].start);exr_free(cfi);cfi=NULL;
      exr_layout_free(page);page=NULL;break;
    }
    CHECK(pages[0].end>pages[0].start && page_count<1000);exr_layout_free(page);page=NULL;
  }
  before=exr_pager_chapter_statistics(pager);
  CHECK(exr_pager_cfi_create_at(pager,old_offset,NULL,&cfi,&error)==EXR_UNSUPPORTED && !cfi);
  after=exr_pager_chapter_statistics(pager);CHECK(before.windows_loaded==after.windows_loaded);
  OK(exr_pager_next(pager,&page,&error));CHECK(page!=NULL);exr_layout_free(page);
  printf("{\"suite\":\"resident-boundaries\",\"checks\":%u,\"windows_loaded\":%zu,\"cross_window_pages\":%zu,\"experimental_only\":true}\n",checks,after.windows_loaded,page_count);
  exr_pager_free(pager);exr_document_free(document);exr_publication_free(publication);
}
static void capture(const char *epub,exr_font *font,const char *prefix) {
  exr_publication *publication=NULL;exr_document *document=NULL;exr_pager *pager;
  exr_layout *page=NULL;const exr_page *pages;const exr_node *nodes;size_t n,offset,chapter=SIZE_MAX;
  exr_cfi_point full;char *cfi,path[4096],metadata[1024];clock_t began;double elapsed;
  OK(exr_publication_open(epub,&publication,&error));pager=pager_open(publication,font);
  OK(exr_pager_next(pager,&page,&error));CHECK(page!=NULL);exr_layout_free(page);page=NULL;
  OK(exr_pager_next(pager,&page,&error));CHECK(page!=NULL);pages=exr_layout_pages(page,&n);CHECK(n==1);offset=pages[0].start;
  CHECK(offset>0);began=clock();cfi=convert(pager,offset);elapsed=1000.0*(clock()-began)/CLOCKS_PER_SEC;
  /* Independent full-document parse is confined to this cloud reference consumer. */
  OK(exr_publication_load(publication,0,&document,&error));
  OK(exr_document_cfi_resolve(document,cfi,NULL,&chapter,&full,&error));CHECK(chapter==0);
  nodes=exr_document_nodes(document,&n);CHECK(full.node<n && nodes[full.node].text);
  CHECK(nodes[full.node].start<=offset && nodes[full.node].end>=offset);
  CHECK(snprintf(path,sizeof(path),"%s.cfi",prefix)>0);write_file(path,cfi,strlen(cfi));
  CHECK(snprintf(path,sizeof(path),"%s.raw",prefix)>0);write_file(path,nodes[full.node].text,strlen(nodes[full.node].text));
  CHECK(snprintf(metadata,sizeof(metadata),"{\"normalized_offset\":%zu,\"raw_node\":%zu,\"raw_utf16\":%zu,\"full_node_start\":%zu,\"full_node_end\":%zu,\"capture_cpu_ms\":%.3f,\"experimental_only\":true}\n",
        offset,full.node,full.offset,nodes[full.node].start,nodes[full.node].end,elapsed)>0);
  CHECK(snprintf(path,sizeof(path),"%s.json",prefix)>0);write_file(path,metadata,strlen(metadata));puts(metadata);
  exr_free(cfi);exr_layout_free(page);exr_pager_free(pager);exr_document_free(document);exr_publication_free(publication);
}
static void resolve(const char *epub,exr_font *font,const char *prefix) {
  exr_publication *publication=NULL;exr_pager *pager;exr_cfi_point point;char path[4096];size_t size;
  char *cfi;exr_chapter_stats before,after;clock_t began;double elapsed;
  CHECK(snprintf(path,sizeof(path),"%s.cfi",prefix)>0);cfi=read_file(path,&size);CHECK(size>0);
  OK(exr_publication_open(epub,&publication,&error));pager=pager_open(publication,font);
  before=exr_pager_chapter_statistics(pager);began=clock();
  OK(exr_pager_cfi_resolve(pager,cfi,NULL,&point,&error));elapsed=1000.0*(clock()-began)/CLOCKS_PER_SEC;
  after=exr_pager_chapter_statistics(pager);CHECK(after.windows_loaded<=before.windows_loaded+1);
  CHECK(after.explicit_snapshot_bytes==0);
  printf("{\"raw_node\":%zu,\"raw_utf16\":%zu,\"resolve_cpu_ms\":%.3f,\"windows_before\":%zu,\"windows_after\":%zu,\"experimental_only\":true}\n",point.node,point.offset,elapsed,before.windows_loaded,after.windows_loaded);
  free(cfi);exr_pager_free(pager);exr_publication_free(publication);
}
int main(int argc,char **argv) {
  exr_font *font;CHECK(argc==5);font=font_open(argv[2]);
  if(!strcmp(argv[1],"suite")) suite(argv[3],font);
  else if(!strcmp(argv[1],"capture")) capture(argv[3],font,argv[4]);
  else if(!strcmp(argv[1],"resolve")) resolve(argv[3],font,argv[4]);
  else CHECK(0);
  exr_font_free(font);return 0;
}
