/* SPDX-License-Identifier: MIT */
#include <exr/dictionary.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#ifdef _WIN32
#include <windows.h>
static double milliseconds(void) {LARGE_INTEGER n,f;QueryPerformanceCounter(&n);QueryPerformanceFrequency(&f);return 1000.0*(double)n.QuadPart/(double)f.QuadPart;}
#else
#include <time.h>
static double milliseconds(void) {struct timespec t;timespec_get(&t,TIME_UTC);return (double)t.tv_sec*1000+t.tv_nsec/1e6;}
#endif
static void string(const char *s) {
  putchar('"');for(const unsigned char *p=(const unsigned char *)s;*p;p++) {
    if(*p=='"'||*p=='\\')printf("\\%c",*p);
    else if(*p<32)printf("\\u%04x",*p);
    else putchar(*p);
  }putchar('"');
}
int main(int argc,char **argv) {
  exr_dictionary *d[64]={0};exr_error e={0};int exit_code=0;
  if(argc<2||argc>65)return 2;
  for(int i=1;i<argc;i++) {
    exr_status status=exr_dictionary_open(argv[i],&d[i-1],&e);
    if(status!=EXR_OK){printf("{\"open_status\":%d,\"message\":",status);string(e.message);puts("}");exit_code=1;goto done;}
    const exr_dictionary_info *v=exr_dictionary_get_info(d[i-1]);
    printf("{\"bookname\":");string(v->bookname);printf(",\"version\":");string(v->version);
    printf(",\"sametypesequence\":");string(v->sametypesequence);
    printf(",\"wordcount\":%llu,\"synwordcount\":%llu,\"idxfilesize\":%llu,\"data_size\":%llu,\"idxoffsetbits\":%u,\"chunk_length\":%u,\"chunk_count\":%u}\n",
      (unsigned long long)v->wordcount,(unsigned long long)v->synwordcount,(unsigned long long)v->idxfilesize,
      (unsigned long long)v->data_size,v->idxoffsetbits,v->chunk_length,v->chunk_count);
  }
  char line[8192];
  while(fgets(line,sizeof(line),stdin)) {
    line[strcspn(line,"\r\n")]=0;exr_dictionary_result *r=NULL;size_t n=0;
    exr_dictionary_io before={0},after={0};
    for(int i=0;i<argc-1;i++){exr_dictionary_io v=exr_dictionary_get_io(d[i]);before.blocks_inflated+=v.blocks_inflated;before.compressed_bytes_read+=v.compressed_bytes_read;before.bytes_inflated+=v.bytes_inflated;}
    double start=milliseconds();exr_status status=exr_dictionary_query(d,(size_t)argc-1,line,32,&r,&n,&e);double elapsed=milliseconds()-start;
    for(int i=0;i<argc-1;i++){exr_dictionary_io v=exr_dictionary_get_io(d[i]);after.blocks_inflated+=v.blocks_inflated;after.compressed_bytes_read+=v.compressed_bytes_read;after.bytes_inflated+=v.bytes_inflated;}
    printf("{\"query\":");string(line);printf(",\"status\":%d,\"ms\":%.6f,\"blocks\":%llu,\"compressed_bytes\":%llu,\"inflated_bytes\":%llu,\"results\":[",
      status,elapsed,(unsigned long long)(after.blocks_inflated-before.blocks_inflated),
      (unsigned long long)(after.compressed_bytes_read-before.compressed_bytes_read),(unsigned long long)(after.bytes_inflated-before.bytes_inflated));
    for(size_t i=0;i<n;i++) {
      if(i)putchar(',');printf("{\"word\":");string(r[i].word);printf(",\"definition\":");string(r[i].definition);
      printf(",\"pos\":");string(r[i].part_of_speech);printf(",\"dictionary\":");string(r[i].dictionary);
      printf(",\"dictionary_index\":%zu,\"entry_index\":%zu,\"match\":%d}",r[i].dictionary_index,r[i].entry_index,r[i].match);
    }
    puts("]}");exr_dictionary_results_free(r,n);
  }
done:for(int i=0;i<64;i++)exr_dictionary_free(d[i]);return exit_code;
}
