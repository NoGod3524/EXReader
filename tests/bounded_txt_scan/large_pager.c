#include "exreader.h"
#include <windows.h>
#include <psapi.h>
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <string.h>

typedef struct { HANDLE file; } file_source;
static size_t read_at(void *ctx,uint64_t offset,void *buffer,size_t size) {
  file_source *s=(file_source *)ctx; LARGE_INTEGER at; DWORD got=0;
  if(offset>INT64_MAX || size>UINT32_MAX) return 0;
  at.QuadPart=(LONGLONG)offset;
  if(!SetFilePointerEx(s->file,at,NULL,FILE_BEGIN) || !ReadFile(s->file,buffer,(DWORD)size,&got,NULL)) return 0;
  return (size_t)got;
}
static void release_source(void *ctx) { file_source *s=(file_source *)ctx; CloseHandle(s->file);free(s); }
static void die(const char *where,exr_error *e) { fprintf(stderr,"%s: %d %s\n",where,e->code,e->message);exit(1); }
int main(int argc,char **argv) {
  file_source *in;exr_source source={0};exr_font *font=NULL;exr_pager *pager=NULL;
  const exr_layout *page=NULL;exr_error error={0};size_t count=0,last=0;LARGE_INTEGER frequency,begin,end;
  exr_layout_config config=exr_layout_config_defaults();
  PROCESS_MEMORY_COUNTERS_EX memory={0};
  int replay;size_t saved_page=0,saved_start=0,saved_end=0;FILE *position;
  if(argc!=4 && argc!=5) return 2;
  replay=strcmp(argv[2],"replay")==0;
  if(!replay && strcmp(argv[2],"record")!=0) return 2;
  if(replay) {
    position=fopen(argv[3],"r");if(!position) return 2;
    if(fscanf(position,"%zu %zu %zu",&saved_page,&saved_start,&saved_end)!=3) return 2;
    fclose(position);
  }
  in=(file_source *)calloc(1,sizeof(*in));if(!in) return 2;
  in->file=CreateFileA(argv[1],GENERIC_READ,FILE_SHARE_READ,NULL,OPEN_EXISTING,FILE_ATTRIBUTE_NORMAL,NULL);
  if(in->file==INVALID_HANDLE_VALUE) return 2;
  { LARGE_INTEGER length;if(!GetFileSizeEx(in->file,&length) || length.QuadPart<0) return 2;
    source.size=(uint64_t)length.QuadPart; }
  source.context=in;source.read_at=read_at;source.release=release_source;
  QueryPerformanceFrequency(&frequency);QueryPerformanceCounter(&begin);
  if(exr_font_open(argc==5?argv[4]:"C:/Windows/Fonts/arial.ttf",&font,&error)!=EXR_OK) die("font",&error);
  config.page.width=720;config.page.height=1040;config.page.margin=36;
  config.page.font_size=42.0f;config.page.line_height=1.5f;config.page.paragraph_spacing=10;
  if(exr_txt_pager_create(&source,font,&config,&pager,&error)!=EXR_OK) { release_source(in);die("open",&error); }
  if(exr_pager_set_cache(pager,2,8*1024*1024,&error)!=EXR_OK ||
     exr_pager_set_checkpoints(pager,8,4*1024*1024,8,&error)!=EXR_OK) die("cache",&error);
  for(;;) {
    size_t n;const exr_page *p;
    if(exr_pager_get(pager,count,&page,&error)!=EXR_OK) die("get",&error);
    if(!page) break;
    p=exr_layout_pages(page,&n);
    if(n!=1 || p[0].end<=p[0].start || (count && p[0].start<last)) die("page sequence",&error);
    if(count==100) {
      if(replay) {
        if(saved_page!=count || saved_start!=p[0].start || saved_end!=p[0].end) die("restart position mismatch",&error);
        printf("restart replay page=%zu start=%zu end=%zu\n",count,p[0].start,p[0].end);
      } else {
        position=fopen(argv[3],"w");if(!position) return 2;
        if(fprintf(position,"%zu %zu %zu\n",count,p[0].start,p[0].end)<0 || fclose(position)) return 2;
      }
    }
    printf("PAGE %zu %zu %zu\n",count,p[0].start,p[0].end);
    last=p[0].end;count++;page=NULL;
    if(count>=3000 || (replay && count>100)) break;
    if(count%1000==0) { fprintf(stderr,"pages=%zu end=%zu\n",count,last);fflush(stderr); }
  }
  QueryPerformanceCounter(&end);memory.cb=sizeof(memory);
  if(!GetProcessMemoryInfo(GetCurrentProcess(),(PROCESS_MEMORY_COUNTERS *)&memory,sizeof(memory))) return 2;
  printf("pages=%zu final_end=%zu elapsed_ms=%.3f peak_working_set=%zu peak_private_bytes=%zu\n",count,last,
    1000.0*(double)(end.QuadPart-begin.QuadPart)/(double)frequency.QuadPart,
    (size_t)memory.PeakWorkingSetSize,(size_t)memory.PeakPagefileUsage);
  exr_pager_free(pager);exr_font_free(font);return count ? 0 : 1;
}
