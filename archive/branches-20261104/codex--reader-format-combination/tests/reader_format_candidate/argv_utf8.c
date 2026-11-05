/* SPDX-License-Identifier: MIT */
/* Thin entry adapter around the byte-identical F5 body. The Windows conversion
   follows C05 1659f834 probe.c: CommandLineToArgvW and strict CP_UTF8 conversion.
   Empty arguments are retained; the original F5 operations are never rewritten. */
#ifndef _WIN32
#define _GNU_SOURCE
#endif
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#ifdef _WIN32
#include <windows.h>
#include <shellapi.h>
#else
#include <dlfcn.h>
#endif

static void fmt_hex(const char *s) {
  const unsigned char *p=(const unsigned char *)s;
  putchar('"'); while(*p) printf("%02x",*p++); putchar('"');
}
#ifdef _WIN32
static int fmt_convert(const wchar_t *input,char **out) {
  int n=WideCharToMultiByte(CP_UTF8,WC_ERR_INVALID_CHARS,input,-1,NULL,0,NULL,NULL);
  char *text;
  if(n<1) return 0;
  text=(char *)malloc((size_t)n); if(!text) return 0;
  if(WideCharToMultiByte(CP_UTF8,WC_ERR_INVALID_CHARS,input,-1,text,n,NULL,NULL)!=n) { free(text); return 0; }
  *out=text; return 1;
}
#endif

#if defined(FORMAT_ARGV_PROBE)
static int fmt_body(int argc,char **argv) {
  int i; fputs("{\"argv_hex\":[",stdout);
  for(i=1;i<argc;i++) { if(i>1) putchar(','); fmt_hex(argv[i]); }
  fputs("]}\n",stdout); return 0;
}
#elif !defined(FORMAT_ARGV_SELF_TEST)
#define main fmt_original_f5_main
#include "f5-consumer-original.c"
#undef main
static int fmt_body(int argc,char **argv) {
  const char *query=""; int i;
  for(i=1;i+1<argc;i++) if(!strcmp(argv[i],"--query")) query=argv[i+1];
  /* ASCII diagnostic cannot be altered by console code pages. */
  fputs("FORMAT_QUERY_UTF8_HEX ",stderr);
  for(i=0;query[i];i++) fprintf(stderr,"%02x",(unsigned char)query[i]);
  fputc('\n',stderr);
#ifdef _WIN32
  {
    HMODULE module=GetModuleHandleW(L"exreader.dll"); wchar_t path[32768]; char *utf8=NULL; DWORD used;
    if(!module) return 93;
    used=GetModuleFileNameW(module,path,32768);
    if(!used || used>=32768 || !fmt_convert(path,&utf8)) return 93;
    fprintf(stderr,"FORMAT_LOADED_SDK %s\n",utf8); free(utf8);
  }
#else
  {
    Dl_info image;
    void *symbol=dlsym(RTLD_DEFAULT,"exr_version");
    if(!symbol || !dladdr(symbol,&image) || !image.dli_fname) return 93;
    fprintf(stderr,"FORMAT_LOADED_SDK %s\n",image.dli_fname);
  }
#endif
  return fmt_original_f5_main(argc,argv);
}
#endif

int main(int argc,char **argv) {
#ifdef FORMAT_ARGV_SELF_TEST
#ifdef _WIN32
  static const wchar_t high[]={0xd800,0},low[]={0xdc00,0},pair[]={0xd83d,0xde00,0};
  char *out=NULL; int count=0;
  if(fmt_convert(high,&out) || out) return 1; count++;
  if(fmt_convert(low,&out) || out) return 2; count++;
  if(!fmt_convert(pair,&out) || strcmp(out,"\xf0\x9f\x98\x80")) return 3; free(out); out=NULL; count++;
  if(!fmt_convert(L"",&out) || strcmp(out,"")) return 4; free(out); out=NULL; count++;
  if(!fmt_convert(L"ASCII",&out) || strcmp(out,"ASCII")) return 5; free(out); count++;
  printf("{\"windows_utf16_checks\":%d,\"invalid_rejected_without_fallback\":true}\n",count);
#else
  puts("{\"windows_utf16_checks\":0,\"scope\":\"POSIX argv passthrough\"}");
#endif
  return 0;
#else
#ifdef _WIN32
  int wide_count=0,i,status; wchar_t **wide=CommandLineToArgvW(GetCommandLineW(),&wide_count);
  char **converted;
  if(!wide || wide_count<1) return 90;
  converted=(char **)calloc((size_t)wide_count+1,sizeof(*converted));
  if(!converted) { LocalFree(wide); return 91; }
  for(i=0;i<wide_count;i++) if(!fmt_convert(wide[i],&converted[i])) {
    while(i) free(converted[--i]); free(converted); LocalFree(wide); return 92;
  }
  status=fmt_body(wide_count,converted);
  for(i=0;i<wide_count;i++) free(converted[i]); free(converted); LocalFree(wide); return status;
#else
  return fmt_body(argc,argv);
#endif
#endif
}
