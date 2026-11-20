/* SPDX-License-Identifier: MIT */
/* Render page 0 of a PDF at scale 1 through the public exr_fixed_render API and dump raw RGBA.
   argv[3]=="nocache" installs a never-cancelling control callback: the canvas then refuses to
   build path-cache keys (build_path_key returns 0 when control.cancelled is set), so the same
   DLL renders every path through the ordinary uncached pipeline. On DLLs without the cache
   (the 9c2443edf baseline) the callback is a no-op.
   Output line: status=<code> width=<w> height=<h> fnv64=<hash> message=<error> */
#include <exreader.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
static int never_cancel(void *context) { (void)context; return 0; }
int main(int argc,char **argv) {
  exr_fixed_document *doc=NULL; exr_fixed_open_options open={0}; exr_fixed_render_options options={0};
  exr_bitmap bitmap={0}; exr_error error={0}; exr_status status; uint64_t h=14695981039346656037ULL;
  if(argc!=4) { fprintf(stderr,"usage: render_abc in.pdf out.rgba cache|nocache\n"); return 2; }
  open.struct_size=sizeof(open);
  options.channels=4; options.background=0xffffffffu;
  if(!strcmp(argv[3],"nocache")) options.control.cancelled=never_cancel;
  else if(strcmp(argv[3],"cache")) return 2;
  status=exr_fixed_open(argv[1],&open,&doc,&error);
  if(status==EXR_OK) status=exr_fixed_render(doc,0,1.0,&options,&bitmap,&error);
  if(status==EXR_OK) {
    FILE *f=fopen(argv[2],"wb"); if(!f) return 3;
    for(uint32_t y=0;y<bitmap.height;y++) {
      const unsigned char *row=bitmap.pixels+(size_t)y*bitmap.stride;
      fwrite(row,1,(size_t)bitmap.width*4,f);
      for(size_t i=0;i<(size_t)bitmap.width*4;i++) h=(h^row[i])*1099511628211ULL;
    }
    fclose(f);
  }
  printf("status=%d width=%u height=%u fnv64=%016llx message=%s\n",(int)status,bitmap.width,bitmap.height,
         status==EXR_OK ? (unsigned long long)h : 0ULL,status==EXR_OK ? "" : error.message);
  exr_bitmap_free(&bitmap); exr_fixed_free(doc);
  return 0;
}
