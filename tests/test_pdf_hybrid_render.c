/* SPDX-License-Identifier: MIT */
#include "exreader.h"
#include "../src/pdf_internal.h"
#include "../src/pdf_crypto.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static exr_error error;
#define CHECK(x) do { if(!(x)) { fprintf(stderr,"line %d: %s (%d: %s)\n",__LINE__,#x,error.code,error.message); return 1; } } while(0)
int main(int argc,char **argv) {
  FILE *f; long length; unsigned char *data; exr_pdf_file *parser=NULL;
  exr_pdf_xref_diagnostics report={0}; exr_fixed_document *doc=NULL;
  exr_fixed_open_options options={0}; exr_pdf_security_info security={0};
  size_t pages=0,i,total=0; int expected,conflict; exr_status status;
  CHECK(argc==5); expected=atoi(argv[2]); conflict=atoi(argv[3]);
  f=fopen(argv[1],"rb"); CHECK(f && !fseek(f,0,SEEK_END)); length=ftell(f); CHECK(length>0); rewind(f);
  data=malloc((size_t)length); CHECK(data && fread(data,1,(size_t)length,f)==(size_t)length); fclose(f);
  status=exr_pdf_open_password(data,(size_t)length,NULL,0,NULL,NULL,&parser,&error);
  if(expected<0) {
    CHECK(status==EXR_FORMAT && !parser && error.message[0]);
    printf("parser status=%d EXR_FORMAT message=%s\n",status,error.message);
  } else {
    CHECK(status==EXR_OK); exr_pdf_xref_report(parser,&report);
    CHECK(report.hybrid_sections>0 && report.encrypt_conflicts==(size_t)conflict);
    CHECK(report.last_xrefstm<(size_t)length);
    printf("parser discovered /XRefStm offset=%zu sections=%zu encrypt_conflicts=%zu\n",report.last_xrefstm,report.hybrid_sections,report.encrypt_conflicts);
    exr_pdf_close(parser);
  }
  free(data); options.struct_size=sizeof(options); security.struct_size=sizeof(security); options.pdf_security=&security;
  status=exr_fixed_open(argv[1],&options,&doc,&error);
  if(expected<0) {
    CHECK(status==EXR_FORMAT && !doc && error.message[0]);
    printf("public open status=%d EXR_FORMAT message=%s\n",status,error.message); return 0;
  }
  CHECK(status==EXR_OK && doc); CHECK(exr_fixed_pages(doc,&pages) && pages==(size_t)expected);
  CHECK(!strcmp(argv[4],"encrypted") ? security.encrypted && security.revision==2 : !security.encrypted);
  printf("public open status=0 pages=%zu expected=%d\n",pages,expected);
  for(i=0;i<pages;i++) {
    exr_bitmap b={0}; size_t x,y,ink=0;
    CHECK(exr_fixed_render(doc,i,0.5,NULL,&b,&error)==EXR_OK);
    CHECK(b.pixels && b.width && b.height && b.channels==4);
    for(y=0;y<b.height;y++) for(x=0;x<b.width;x++) {
      const unsigned char *p=b.pixels+y*b.stride+x*4;
      if(p[3] && (p[0]<250 || p[1]<250 || p[2]<250)) ink++;
    }
    printf("page=%zu status=0 width=%u height=%u nonwhite_pixels=%zu\n",i+1,b.width,b.height,ink);
    CHECK(ink>0); total+=ink; exr_bitmap_free(&b);
  }
  printf("rendered=%zu failures=0 nonwhite_pixels_total=%zu\n",pages,total);
  exr_fixed_free(doc); return 0;
}
