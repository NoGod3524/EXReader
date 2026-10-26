/* Minimal opt-in host exercising the frozen SDK with bounded TXT windows. */
#include "bounded_txt.h"
#include <windows.h>
#include <psapi.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
typedef struct { FILE *file; int cancelled; } input;
static size_t read_at(void *p,uint64_t offset,void *buffer,size_t n) {
  input *in=(input *)p;
  if (_fseeki64(in->file,(long long)offset,SEEK_SET)) return 0;
  return fread(buffer,1,n,in->file);
}
static int cancelled(void *p) { return ((input *)p)->cancelled; }
#define CHECK(x) do { if (!(x)) { fprintf(stderr,"line %d: %s (%d: %s)\n",__LINE__,#x,(int)error.code,error.message); return 1; } } while (0)
int main(int argc,char **argv) {
  input in={0}; exr_source source={0}; exr_error error={0}; exr_document *doc=NULL;
  exr_font *font=NULL; exr_pager *pager=NULL; exr_layout *page=NULL; exr_anchor anchor={0};
  exr_anchor_match match={0}; exr_layout_config config=exr_layout_config_defaults();
  uint64_t cursor=0, saved=0; size_t windows=0,blocks=0,n=0,start=0,end=0,max_nodes=0,max_doc=0;
  LARGE_INTEGER frequency,begin,finish; PROCESS_MEMORY_COUNTERS memory={0};
  CHECK(argc==3); in.file=fopen(argv[1],"rb"); CHECK(in.file);
  CHECK(!_fseeki64(in.file,0,SEEK_END)); source.size=(uint64_t)_ftelli64(in.file);
  source.read_at=read_at; source.context=&in; source.control.cancelled=cancelled; source.control.context=&in;
  CHECK(exr_font_open(argv[2],&font,&error)==EXR_OK);
  QueryPerformanceFrequency(&frequency); QueryPerformanceCounter(&begin);
  in.cancelled=1; CHECK(bounded_txt_next(&source,&cursor,&doc,&error)==EXR_CANCELLED && !doc && cursor==0); in.cancelled=0;
  while (cursor<source.size) {
    saved=cursor; CHECK(bounded_txt_next(&source,&cursor,&doc,&error)==EXR_OK && doc && cursor>saved);
    exr_document_blocks(doc,&n); blocks+=n;
    exr_document_nodes(doc,&n); if(n>max_nodes) max_nodes=n;
    n=exr_document_memory_size(doc); if(n>max_doc) max_doc=n;
    if (windows==0) {
      CHECK(exr_document_find(doc,"Perf Import 0000",0,&start,&end,&error)==EXR_OK && start!=SIZE_MAX);
      CHECK(exr_anchor_create(doc,start,end,&anchor,&error)==EXR_OK);
      CHECK(exr_pager_create(doc,font,&config,&pager,&error)==EXR_OK);
      CHECK(exr_pager_next(pager,&page,&error)==EXR_OK && page);
      CHECK(exr_layout_pages(page,&n) && n==1);
      exr_layout_free(page); page=NULL; exr_pager_free(pager); pager=NULL;
    }
    exr_document_free(doc); doc=NULL; windows++;
  }
  CHECK(bounded_txt_next(&source,&cursor,&doc,&error)==EXR_OK && !doc);
  saved=0; CHECK(bounded_txt_next(&source,&saved,&doc,&error)==EXR_OK && doc);
  CHECK(exr_anchor_resolve(doc,&anchor,&match,&error)==EXR_OK && match.state==EXR_ANCHOR_FOUND && match.start==start && match.end==end);
  exr_document_free(doc); exr_anchor_free(&anchor); exr_font_free(font); fclose(in.file);
  QueryPerformanceCounter(&finish); memory.cb=sizeof(memory); CHECK(GetProcessMemoryInfo(GetCurrentProcess(),&memory,sizeof(memory)));
  printf("{\"source_bytes\":%llu,\"windows\":%zu,\"blocks\":%zu,\"max_window_nodes\":%zu,\"max_document_bytes\":%zu,\"peak_working_set_bytes\":%llu,\"elapsed_ms\":%.3f,\"cancel_resume\":true,\"first_page\":true,\"window_anchor_reload\":true}\n",
    (unsigned long long)source.size,windows,blocks,max_nodes,max_doc,(unsigned long long)memory.PeakWorkingSetSize,
    (double)(finish.QuadPart-begin.QuadPart)*1000.0/(double)frequency.QuadPart);
  return blocks==212895 && source.size==16792975 && max_nodes<=262144 ? 0 : 1;
}
