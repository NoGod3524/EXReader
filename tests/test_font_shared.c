/* SPDX-License-Identifier: MIT */
/* Shared document font files: each file is read and charged once, however
   many face combinations (fonts) a PPT/PPTX document builds from it. */
#include "font_manager_internal.h"
#include <stdio.h>
#include <string.h>

static exr_error error;
static unsigned checks;
#define CHECK(x) do { checks++; if (!(x)) { fprintf(stderr,"line %d: %s (%d: %s)\n", \
  __LINE__, #x, (int)error.code, error.message); return 1; } } while (0)

static long file_size(const char *path) {
  FILE *f=fopen(path,"rb"); long n;
  if(!f) return -1;
  n=fseek(f,0,SEEK_END) ? -1 : ftell(f); fclose(f); return n;
}
int main(int argc,char **argv) {
  exr_font_manager_options options={0}; exr_font_location location;
  exr_font_manager *m=NULL; exr_font_manager_summary summary={0};
  exr_font_blob_cache cache={0}; exr_font *fonts[64]={0};
  size_t faces[32],plain[32],n=0,count=0,i,j,collection=SIZE_MAX,total=0;
  CHECK(argc==2);
  location=(exr_font_location){argv[1],EXR_FONT_LOCATION_DIRECTORY,0};
  options.struct_size=sizeof(options); options.locations=&location; options.location_count=1;
  CHECK(exr_font_manager_create(&options,&m,&error)==EXR_OK);
  summary.struct_size=sizeof(summary);
  CHECK(exr_font_manager_summary_get(m,&summary,&error)==EXR_OK);
  /* One face per distinct file, plus one extra face of a collection file. */
  for(i=0;i<summary.faces && n<32;i++) {
    exr_font_face_info a={0}; int seen=0;
    a.struct_size=sizeof(a);
    CHECK(exr_font_manager_face(m,i,&a,&error)==EXR_OK);
    for(j=0;j<n;j++) {
      exr_font_face_info b={0}; b.struct_size=sizeof(b);
      CHECK(exr_font_manager_face(m,plain[j],&b,&error)==EXR_OK);
      if(!strcmp(a.path,b.path)) { seen=1; if(collection==SIZE_MAX && a.face_index) collection=i; }
    }
    if(!seen) { long size=file_size(a.path); CHECK(size>0); total+=(size_t)size; plain[n++]=i; }
  }
  CHECK(n>=3 && collection!=SIZE_MAX);
  /* Every prefix, in both orders, and the collection's second face: many
     distinct combinations over the same handful of files. */
  for(i=1;i<=n && count+2<=64;i++) {
    for(j=0;j<i;j++) faces[j]=plain[j];
    CHECK(exr_font_manager_shared_font(m,&cache,faces,i,&fonts[count],&error)==EXR_OK);
    CHECK(exr_font_count(fonts[count++])==i);
    for(j=0;j<i;j++) faces[j]=plain[i-1-j];
    CHECK(exr_font_manager_shared_font(m,&cache,faces,i,&fonts[count++],&error)==EXR_OK);
  }
  faces[0]=collection;
  CHECK(exr_font_manager_shared_font(m,&cache,faces,1,&fonts[count++],&error)==EXR_OK);
  CHECK(cache.bytes==total);
  {
    size_t blobs=0;
    for(i=0;i<cache.count;i++) {
      for(j=0;j<i && cache.items[j].blob!=cache.items[i].blob;j++) { }
      blobs+=j==i;
    }
    CHECK(blobs==n);
  }
  /* Fonts keep their borrowed bytes alive after the cache is released. */
  exr_font_blob_cache_free(&cache);
  CHECK(!cache.count && !cache.items && !cache.bytes);
  for(i=0;i<count;i++) {
    /* Touch the FreeType face, which reads the borrowed bytes (ASan). */
    for(j=0;j<exr_font_count(fonts[i]);j++) (void)exr_font_has_glyph(fonts[i],j,'A');
    exr_font_free(fonts[i]);
  }
  CHECK(exr_font_manager_shared_font(m,&cache,plain,0,&fonts[0],&error)==EXR_ARGUMENT);
  exr_font_manager_free(m);
  printf("font-shared: files=%zu combinations=%zu resident_bytes=%zu checks=%u\n",n,count,total,checks);
  return 0;
}
