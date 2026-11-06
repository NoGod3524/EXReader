/* External measurement wrapper; the repository CLI is included unchanged. */
#include "exreader.h"
#include <windows.h>
#include <wincrypt.h>
#include <stdlib.h>
#include <math.h>
#include <stdio.h>
static int first_render_seen;

static size_t probe_part, probe_last_part=(size_t)-1, probe_modes[3],probe_vertical_glyphs,probe_missing_glyphs,probe_glyphs;
static void probe_layout(const exr_layout *layout) {
  size_t n=0,vertical=0,missing=0; const exr_glyph *g=exr_layout_glyphs(layout,&n);
  int mode=(int)exr_layout_writing_mode(layout);
  if(mode>=0 && mode<3)probe_modes[mode]++;
  for(size_t i=0;i<n;i++){vertical+=!!(g[i].flags&EXR_GLYPH_VERTICAL);missing+=!!(g[i].flags&EXR_GLYPH_MISSING);}
  probe_vertical_glyphs+=vertical;probe_missing_glyphs+=missing;probe_glyphs+=n;
  if(probe_last_part!=probe_part){
    printf("PASS_A_LAYOUT {\"part_index\":%zu,\"writing_mode\":%d,\"glyphs\":%zu,\"vertical_glyphs\":%zu,\"missing_glyphs\":%zu}\n",probe_part,mode,n,vertical,missing);fflush(stdout);probe_last_part=probe_part;
  }
}
static exr_status probe_load(exr_publication *p,size_t part,exr_document **out,exr_error *error) {
  probe_part=part;return exr_publication_load(p,part,out,error);
}
static void probe_report(void) {
  printf("PASS_A_COVERAGE {\"horizontal_pages\":%zu,\"vertical_rl_pages\":%zu,\"vertical_lr_pages\":%zu,\"glyphs\":%zu,\"vertical_glyphs\":%zu,\"missing_glyphs\":%zu}\n",probe_modes[0],probe_modes[1],probe_modes[2],probe_glyphs,probe_vertical_glyphs,probe_missing_glyphs);
}

static double clock_ms(void) {
  LARGE_INTEGER n,f; QueryPerformanceCounter(&n); QueryPerformanceFrequency(&f);
  return 1000.0*(double)n.QuadPart/(double)f.QuadPart;
}
static void measured_open(exr_status status,double start) {
  printf("PASS_A_OPEN {\"status\":%d,\"ms\":%.6f}\n",(int)status,clock_ms()-start);fflush(stdout);
}
static exr_status publication_open(const char *path,exr_publication **out,exr_error *error) {
  double t=clock_ms();exr_status s=exr_publication_open(path,out,error);measured_open(s,t);return s;
}
static exr_status document_open(const char *path,exr_document **out,exr_error *error) {
  double t=clock_ms();exr_status s=exr_document_open(path,out,error);measured_open(s,t);return s;
}
static exr_status fixed_open(const char *path,const exr_fixed_open_options *options,exr_fixed_document **out,exr_error *error) {
  double t=clock_ms();exr_status s=exr_fixed_open(path,options,out,error);measured_open(s,t);return s;
}
static const exr_part *publication_parts(const exr_publication *publication,size_t *count) {
  const exr_part *p=exr_publication_parts(publication,count);
  printf("PASS_A_PARTS {\"parts\":%zu}\n",*count);fflush(stdout);return p;
}
static const exr_fixed_page *fixed_pages(const exr_fixed_document *document,size_t *count) {
  const exr_fixed_page *p=exr_fixed_pages(document,count);
  printf("PASS_A_FIXED_PAGES {\"parts\":1,\"pages\":%zu}\n",*count);fflush(stdout);return p;
}
static void measured_render(exr_status status,double elapsed,const exr_bitmap *out) {
  if(first_render_seen++)return;
  printf("PASS_A_RENDER {\"status\":%d,\"ms\":%.6f,\"valid_bitmap\":%s}\n",(int)status,elapsed,
    out->pixels && out->width && out->height && out->channels==4 && out->stride>=(size_t)out->width*4 ? "true":"false");fflush(stdout);
}

static size_t alias_global_page;
static void alias_bitmap(const exr_layout *layout,const exr_bitmap *bitmap) {
  HCRYPTPROV provider=0;HCRYPTHASH hash=0;BYTE digest[32];DWORD length=sizeof(digest);
  char hex[65];size_t lines=0,n=0,left=0,right=0;float first=0,last=0,min_size=1e9f,max_size=0;
  const exr_line *l=exr_layout_lines(layout,&lines);const exr_glyph *g=exr_layout_glyphs(layout,&n);
  if(!CryptAcquireContextW(&provider,NULL,NULL,PROV_RSA_AES,CRYPT_VERIFYCONTEXT) ||
     !CryptCreateHash(provider,CALG_SHA_256,0,0,&hash)) { fputs("ProbeHashError\n",stderr);exit(3); }
  DWORD header[3]={bitmap->width,bitmap->height,bitmap->channels};
  if(!CryptHashData(hash,(const BYTE*)header,sizeof(header),0)){fputs("ProbeHashError\n",stderr);exit(3);}
  for(size_t y=0;y<bitmap->height;y++)if(!CryptHashData(hash,bitmap->pixels+y*bitmap->stride,bitmap->width*4,0)){fputs("ProbeHashError\n",stderr);exit(3);}
  if(!CryptGetHashParam(hash,HP_HASHVAL,digest,&length,0)){fputs("ProbeHashError\n",stderr);exit(3);}
  CryptDestroyHash(hash);CryptReleaseContext(provider,0);
  for(size_t i=0;i<32;i++)snprintf(hex+2*i,3,"%02x",digest[i]);
  for(size_t i=0;i<n;i++){if(g[i].size<min_size)min_size=g[i].size;if(g[i].size>max_size)max_size=g[i].size;}
  if(!n)min_size=0;
  if(lines){first=l[0].x;last=l[lines-1].x;for(size_t i=1;i<lines;i++){left+=l[i].x<l[i-1].x-0.01f;right+=l[i].x>l[i-1].x+0.01f;}}
  alias_global_page++;
  printf("ALIAS_PAGE {\"page\":%zu,\"part_index\":%zu,\"sha256\":\"%s\",\"mode\":%d,\"glyphs\":%zu,\"lines\":%zu,\"first_x\":%.6f,\"last_x\":%.6f,\"left_steps\":%zu,\"right_steps\":%zu,\"font_min\":%.6f,\"font_max\":%.6f",alias_global_page,probe_part,hex,(int)exr_layout_writing_mode(layout),n,lines,first,last,left,right,min_size,max_size);
  if(alias_global_page==30 || alias_global_page==100 || alias_global_page==200){
    printf(",\"sample_x\":[");for(size_t i=0;i<lines;i++)printf("%s%.6f",i ? ",":"",l[i].x);putchar(']');
    
    printf(",\"body_x\":[");size_t body_count=0,body_right=0;float previous=0;
    for(size_t i=0;i<lines;i++) {
      int body=0;for(size_t j=l[i].glyph_start;j<l[i].glyph_start+l[i].glyph_count && j<n;j++)if(g[j].size>=max_size-0.01f)body=1;
      if(body && (!body_count || fabsf(l[i].x-previous)>0.01f)) {
        if(body_count && l[i].x>previous+0.01f)body_right++;
        printf("%s%.6f",body_count ? ",":"",l[i].x);body_count++;previous=l[i].x;
      }
    }
    printf("],\"body_right_steps\":%zu",body_right);

const char *capture=getenv("EXR_ALIAS_CAPTURE");
    if(capture && capture[0]){char path[2048];exr_error e={0};snprintf(path,sizeof(path),"%s/sample-page-%04zu.png",capture,alias_global_page);if(exr_bitmap_write_png(bitmap,path,&e)!=EXR_OK){fputs("ProbePNGError\n",stderr);exit(3);}}
  }
  puts("}");fflush(stdout);
}

static exr_status render_color(const exr_layout *layout,exr_font *font,size_t page,exr_bitmap *out,exr_error *error) {
  probe_layout(layout);double t=clock_ms();exr_status s=exr_render_page_color(layout,font,page,out,error);
  double elapsed=clock_ms()-t;if(s==EXR_OK)alias_bitmap(layout,out);measured_render(s,elapsed,out);return s;
}
static exr_status render_fixed(exr_fixed_document *document,size_t page,double scale,const exr_fixed_render_options *options,exr_bitmap *out,exr_error *error) {
  double t=clock_ms();exr_status s=exr_fixed_render(document,page,scale,options,out,error);
  measured_render(s,clock_ms()-t,out);return s;
}
#define main original_check_document_main
#define exr_publication_load probe_load
#define exr_publication_open publication_open
#define exr_document_open document_open
#define exr_fixed_open fixed_open
#define exr_publication_parts publication_parts
#define exr_fixed_pages fixed_pages
#define exr_render_page_color render_color
#define exr_fixed_render render_fixed
#include "C:/Users/Oscar/Documents/Codex/EXReader-real-books-20261105/tools/check_document.c"

#undef main
int main(void) { atexit(probe_report);return original_check_document_main(); }
