/* SPDX-License-Identifier: MIT */
#if !defined(_WIN32) && !defined(_POSIX_C_SOURCE)
#define _POSIX_C_SOURCE 200809L
#endif
/* WP12a large-media evidence probe. Not part of the installed SDK. */
#include "exreader.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#ifdef _WIN32
#include <windows.h>
#include <psapi.h>
#else
#include <sys/resource.h>
#include <sys/stat.h>
#include <time.h>
#include <unistd.h>
#include <pthread.h>
#endif
typedef struct { size_t working,private_bytes,peak_working,peak_private,sampled_working,sampled_private; } memory_snapshot;
static int memory_read(memory_snapshot *m) {
#ifdef _WIN32
  PROCESS_MEMORY_COUNTERS_EX counters;DWORD size=sizeof(counters);
  if(!GetProcessMemoryInfo(GetCurrentProcess(),(PROCESS_MEMORY_COUNTERS *)&counters,size)) return 0;
  m->working=counters.WorkingSetSize;m->private_bytes=counters.PrivateUsage;
  m->peak_working=counters.PeakWorkingSetSize;m->peak_private=counters.PeakPagefileUsage;
  return 1;
#else
  FILE *f=fopen("/proc/self/status","r");char line[256];m->working=m->private_bytes=m->peak_working=0;
  if(f) { while(fgets(line,sizeof(line),f)) { if(!strncmp(line,"VmRSS:",6)) m->working=(size_t)strtoull(line+6,NULL,10)*1024; if(!strncmp(line,"VmHWM:",6)) m->peak_working=(size_t)strtoull(line+6,NULL,10)*1024; if(!strncmp(line,"VmPeak:",7)) m->peak_private=(size_t)strtoull(line+7,NULL,10)*1024; } fclose(f); }
  m->private_bytes=m->working;if(!m->peak_private) m->peak_private=m->peak_working;return m->working!=0;
#endif
}
#ifdef _WIN32
static DWORD WINAPI sample_thread(LPVOID context) {
  memory_snapshot *m=context;
  while(1) { memory_snapshot now;if(!memory_read(&now)) break;if(now.working>m->sampled_working) m->sampled_working=now.working;if(now.private_bytes>m->sampled_private) m->sampled_private=now.private_bytes;Sleep(2); }
  return 0;
}
#else
static void *sample_thread(void *context) {
  memory_snapshot *m=context;
  for(;;) { memory_snapshot now;if(!memory_read(&now)) break;if(now.working>m->sampled_working) m->sampled_working=now.working;if(now.private_bytes>m->sampled_private) m->sampled_private=now.private_bytes;struct timespec ts={0,2000000};nanosleep(&ts,NULL); }
  return NULL;
}
#endif
static unsigned long long file_size(const char *path) {
#ifdef _WIN32
  FILE *f=fopen(path,"rb");__int64 n;if(!f) return 0;if(_fseeki64(f,0,SEEK_END)) { fclose(f);return 0; }n=_ftelli64(f);fclose(f);return n<0?0:(unsigned long long)n;
#else
  struct stat st;return stat(path,&st)==0 ? (unsigned long long)st.st_size : 0;
#endif
}
static double now_seconds(void) {
#ifdef _WIN32
  LARGE_INTEGER f,c;QueryPerformanceFrequency(&f);QueryPerformanceCounter(&c);return (double)c.QuadPart/(double)f.QuadPart;
#else
  struct timespec ts;clock_gettime(CLOCK_MONOTONIC,&ts);return ts.tv_sec+ts.tv_nsec/1e9;
#endif
}
static void json_size(const char *name,size_t value,int comma) { printf("    \"%s\": %llu%s\n",name,(unsigned long long)value,comma?",":""); }
static int audio(const char *path) {
  exr_wave *wave=NULL;exr_error error={0};const exr_wave_info *info;size_t frames=0,read=0;float *buffer=NULL;double start;memory_snapshot before,peak;
  size_t request=4096;uint64_t first[3];int i;
  if(exr_wave_open(path,NULL,&wave,&error)!=EXR_OK) { fprintf(stderr,"wave open: %s\n",error.message);return 1; }
  info=exr_wave_format(wave);buffer=malloc(request*info->channels*sizeof(*buffer));
  if(!buffer) return 1;
  memory_read(&before);peak=before;peak.sampled_working=before.working;peak.sampled_private=before.private_bytes;start=now_seconds();
  first[0]=0;first[1]=info->frames/2;first[2]=info->frames>request?info->frames-request:0;
  for(i=0;i<3;i++) {
    exr_status status=exr_wave_read(wave,first[i],request,buffer,&read,NULL,&error);
    if(status!=EXR_OK) { fprintf(stderr,"wave read: %s\n",error.message);free(buffer);exr_wave_free(wave);return 1; }
    frames+=read;
  }
  { double elapsed=now_seconds()-start;memory_snapshot after;memory_read(&after);
    printf("{\n  \"kind\": \"audio\",\n  \"source_bytes\": %llu,\n",file_size(path));
    printf("  \"sample_rate\": %u,\n  \"channels\": %u,\n  \"frames\": %llu,\n",info->sample_rate,info->channels,(unsigned long long)info->frames);
    printf("  \"reads\": 3,\n  \"frames_read\": %llu,\n  \"elapsed_seconds\": %.6f,\n",(unsigned long long)frames,elapsed);
    json_size("baseline_private",before.private_bytes,1);json_size("peak_private",peak.private_bytes,1);
    json_size("baseline_working",before.working,1);json_size("peak_working",peak.working,1);
    json_size("added_private_peak",peak.sampled_private>before.private_bytes?peak.sampled_private-before.private_bytes:0,1);
    json_size("added_working_peak",peak.sampled_working>before.working?peak.sampled_working-before.working:0,1);
    json_size("process_peak_private",peak.peak_private,1);
    json_size("process_peak_working",peak.peak_working,1);
    printf("  \"read_buffer_bytes\": %llu,\n  \"wave_stack_buffer_bytes\": 4096\n}\n",(unsigned long long)(request*info->channels*sizeof(*buffer)));
  }
  free(buffer);exr_wave_free(wave);return 0;
}
static int book(const char *path,const char *database) {
  exr_library *library=NULL;exr_error error={0};int64_t id=0,duplicate=0;int created=0,duplicate_created=0;exr_fixed_document *doc=NULL;exr_bitmap bitmap={0};double start,elapsed;memory_snapshot before,peak;size_t pages=0;
#ifdef _WIN32
  HANDLE thread;
#else
  pthread_t thread;
#endif
  remove(database);
  if(exr_library_open(database,&library,&error)!=EXR_OK) { fprintf(stderr,"library: %s\n",error.message);return 1; }
  memory_read(&before);peak=before;peak.sampled_working=before.working;peak.sampled_private=before.private_bytes;
#ifdef _WIN32
  thread=CreateThread(NULL,0,sample_thread,&peak,0,NULL);
#else
  pthread_create(&thread,NULL,sample_thread,&peak);
#endif
  start=now_seconds();
  if(exr_library_import_file_unique(library,EXR_CBZ,path,"Large book",&id,&created,&error)!=EXR_OK) { fprintf(stderr,"import: %s\n",error.message);return 1; }
  { double first_elapsed=now_seconds()-start;
    memory_snapshot after_import;memory_read(&after_import);
    start=now_seconds();
    if(exr_library_import_file_unique(library,EXR_CBZ,path,"Large book",&duplicate,&duplicate_created,&error)!=EXR_OK) { fprintf(stderr,"duplicate: %s\n",error.message);return 1; }
    elapsed=now_seconds()-start;
    if(exr_library_fixed_source(library,id,NULL,&doc,&error)!=EXR_OK) { fprintf(stderr,"fixed source: %s\n",error.message);return 1; }
    exr_fixed_pages(doc,&pages);if(exr_fixed_render(doc,0,1,NULL,&bitmap,&error)!=EXR_OK) { fprintf(stderr,"render: %s\n",error.message);return 1; }
    memory_snapshot after=peak;
    printf("{\n  \"kind\": \"book\",\n  \"source_bytes\": %llu,\n",file_size(path));
    printf("  \"book_id\": %lld,\n  \"duplicate_id\": %lld,\n  \"created\": %d,\n  \"duplicate_created\": %d,\n",(long long)id,(long long)duplicate,created,duplicate_created);
    printf("  \"pages\": %llu,\n  \"first_import_seconds\": %.6f,\n  \"duplicate_seconds\": %.6f,\n  \"page_pixels\": %u,\n",(unsigned long long)pages,first_elapsed,elapsed,bitmap.width*bitmap.height);
    json_size("baseline_private",before.private_bytes,1);json_size("peak_private",peak.private_bytes,1);
    json_size("baseline_working",before.working,1);json_size("peak_working",peak.working,1);
    json_size("added_private_peak",peak.sampled_private>before.private_bytes?peak.sampled_private-before.private_bytes:0,1);
    json_size("added_working_peak",peak.sampled_working>before.working?peak.sampled_working-before.working:0,1);
    json_size("process_peak_private",peak.peak_private,1);
    json_size("process_peak_working",peak.peak_working,1);
    json_size("post_import_private",after_import.private_bytes,1);
    printf("  \"chunk_bytes\": 65536,\n  \"sqlite_cache_bytes\": 2097152,\n  \"database_bytes\": %llu\n}\n",file_size(database));
    exr_bitmap_free(&bitmap);exr_fixed_free(doc);
  }
  exr_library_close(library);
  return 0;
}
static int book_memory(const char *path,const char *database) {
  FILE *f=fopen(path,"rb");long size;unsigned char *bytes;exr_library *library=NULL;exr_error error={0};int64_t id=0;memory_snapshot before,loaded,after;double start;size_t pages=0;
  memory_read(&before);
  remove(database);
  if(!f) { fprintf(stderr,"cannot open %s\n",path);return 1; }
  if(fseek(f,0,SEEK_END) || (size=ftell(f))<0) { fclose(f);return 1; } rewind(f);
  bytes=malloc((size_t)size);if(!bytes) { fclose(f);return 1; }if(fread(bytes,1,(size_t)size,f)!=(size_t)size) { fclose(f);free(bytes);return 1; }fclose(f);
  if(exr_library_open(database,&library,&error)!=EXR_OK) { fprintf(stderr,"library: %s\n",error.message);free(bytes);return 1; }
  memory_read(&loaded);
  start=now_seconds();
  if(exr_library_import(library,EXR_CBZ,bytes,(size_t)size,"Legacy book",&id,&error)!=EXR_OK) { fprintf(stderr,"import: %s\n",error.message);free(bytes);exr_library_close(library);return 1; }
  { double elapsed=now_seconds()-start;memory_read(&after);
    printf("{\n  \"kind\": \"book-memory\",\n  \"source_bytes\": %llu,\n  \"book_id\": %lld,\n  \"elapsed_seconds\": %.6f,\n",(unsigned long long)size,(long long)id,elapsed);
    json_size("baseline_private",before.private_bytes,1);json_size("loaded_private",loaded.private_bytes,1);json_size("after_private",after.private_bytes,1);
    printf("  \"file_buffer_bytes\": %llu,\n  \"database_bytes\": %llu\n}\n",(unsigned long long)size,file_size(database));
    (void)pages;
  }
  free(bytes);exr_library_close(library);return 0;
}
int main(int argc,char **argv) {
  if(argc<3) { fprintf(stderr,"usage: %s audio <wav> | book <cbz> <db>\n",argv[0]);return 2; }
  if(!strcmp(argv[1],"audio") && argc==3) return audio(argv[2]);
  if(!strcmp(argv[1],"book") && argc==4) return book(argv[2],argv[3]);
  if(!strcmp(argv[1],"book-memory") && argc==4) return book_memory(argv[2],argv[3]);
  fprintf(stderr,"invalid arguments\n");return 2;
}
