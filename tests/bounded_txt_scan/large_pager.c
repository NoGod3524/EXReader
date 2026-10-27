#include "exreader.h"
#include <windows.h>
#include <psapi.h>
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>

typedef struct { FILE *file; } file_source;
static size_t read_at(void *ctx,uint64_t offset,void *buffer,size_t size) {
  file_source *s=(file_source *)ctx;
  if(offset>INT64_MAX || _fseeki64(s->file,(__int64)offset,SEEK_SET)) return 0;
  return fread(buffer,1,size,s->file);
}
static void release_source(void *ctx) { file_source *s=(file_source *)ctx; fclose(s->file);free(s); }
static void die(const char *where,exr_error *e) { fprintf(stderr,"%s: %d %s\n",where,e->code,e->message);exit(1); }
int main(int argc,char **argv) {
  file_source *in;exr_source source={0};exr_font *font=NULL;exr_pager *pager=NULL;
  exr_layout *page=NULL;exr_error error={0};size_t count=0,last=0;LARGE_INTEGER frequency,begin,end;
  PROCESS_MEMORY_COUNTERS_EX memory={0};
  if(argc!=2) return 2;
  in=(file_source *)calloc(1,sizeof(*in));if(!in) return 2;
  in->file=fopen(argv[1],"rb");if(!in->file) return 2;
  if(_fseeki64(in->file,0,SEEK_END)) return 2;
  source.size=(uint64_t)_ftelli64(in->file);source.context=in;source.read_at=read_at;source.release=release_source;
  QueryPerformanceFrequency(&frequency);QueryPerformanceCounter(&begin);
  if(exr_font_open("C:/Windows/Fonts/arial.ttf",&font,&error)!=EXR_OK) die("font",&error);
  if(exr_txt_pager_create(&source,font,NULL,&pager,&error)!=EXR_OK) { release_source(in);die("open",&error); }
  for(;;) {
    size_t n;const exr_page *p;
    if(exr_pager_next(pager,&page,&error)!=EXR_OK) die("next",&error);
    if(!page) break;
    p=exr_layout_pages(page,&n);
    if(n!=1 || p[0].end<=p[0].start || (count && p[0].start<last)) die("page sequence",&error);
    last=p[0].end;count++;exr_layout_free(page);page=NULL;
    if(count%1000==0) { fprintf(stderr,"pages=%zu end=%zu\n",count,last);fflush(stderr); }
  }
  QueryPerformanceCounter(&end);memory.cb=sizeof(memory);
  if(!GetProcessMemoryInfo(GetCurrentProcess(),(PROCESS_MEMORY_COUNTERS *)&memory,sizeof(memory))) return 2;
  printf("pages=%zu final_end=%zu elapsed_ms=%.3f peak_working_set=%zu peak_private_bytes=%zu\n",count,last,
    1000.0*(double)(end.QuadPart-begin.QuadPart)/(double)frequency.QuadPart,
    (size_t)memory.PeakWorkingSetSize,(size_t)memory.PeakPagefileUsage);
  exr_pager_free(pager);exr_font_free(font);return count ? 0 : 1;
}
