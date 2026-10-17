/* SPDX-License-Identifier: GPL-3.0-only */
#include "exreader.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static exr_error error; static unsigned checks;
#define CHECK(x) do { checks++; if(!(x)) { fprintf(stderr,"line %d: %s (%d: %s)\n",__LINE__,#x,error.code,error.message); exit(1); } } while(0)
#define OK(x) CHECK((x)==EXR_OK)
static void fixture(const char *dir,const char *name,const char *text,exr_status expected) {
  char path[4096]; exr_document *doc=(exr_document *)(uintptr_t)1; exr_status status;
  snprintf(path,sizeof(path),"%s/%s",dir,name); status=exr_document_open(path,&doc,&error);
  if(status!=expected) fprintf(stderr,"fixture %s\n",name);
  CHECK(status==expected);
  if(expected==EXR_OK) { CHECK(doc && !strcmp(exr_document_text(doc,NULL),text)); exr_document_free(doc); }
  else { CHECK(!doc && error.code==expected && error.message[0]); }
}
int main(int argc,char **argv) {
  const char *valid[]={"mobi-huff.mobi","mobi-huff-trailers.mobi","mobi-huff-split.mobi","mobi-huff-many-trailers.mobi","mobi-raw-trailers.mobi","mobi-palmdoc-trailers.mobi"};
  const char *bad[]={"mobi-huff-cycle.mobi","mobi-huff-zero-length.mobi","mobi-huff-bad-offset.mobi","mobi-huff-truncated-phrase.mobi","mobi-huff-missing-dict.mobi","mobi-huff-bad-code.mobi","mobi-huff-bad-prefix.mobi","mobi-palmdoc-cross-record.mobi","mobi-palmdoc-truncated.mobi","mobi-bad-directory.mobi","mobi-bad-trailer.mobi"};
  size_t i; CHECK(argc==2);
  for(i=0;i<sizeof(valid)/sizeof(*valid);i++) fixture(argv[1],valid[i],"HUFF native reading.",EXR_OK);
  fixture(argv[1],"mobi-huff-cp1252.mobi","Café",EXR_OK);
  fixture(argv[1],"mobi-huff-recursive.mobi","Recursive",EXR_OK);
  fixture(argv[1],"mobi-huff-long-code.mobi","X",EXR_OK);
  fixture(argv[1],"mobi-huff-short-code.mobi","X",EXR_OK);
  fixture(argv[1],"mobi-huff-depth-64.mobi","X",EXR_OK);
  fixture(argv[1],"mobi-huff-depth-65.mobi",NULL,EXR_LIMIT);
  fixture(argv[1],"mobi-huff-expansion.mobi",NULL,EXR_LIMIT);
  fixture(argv[1],"mobi-palmdoc-overlap.mobi","AAAAAAAAAAA",EXR_OK);
  for(i=0;i<sizeof(bad)/sizeof(*bad);i++) fixture(argv[1],bad[i],NULL,EXR_FORMAT);
  printf("%u MOBI codec checks passed\n",checks); return 0;
}
