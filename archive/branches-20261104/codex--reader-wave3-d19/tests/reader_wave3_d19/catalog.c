/* Public SDK source and product catalog readback, only after the GUI owner exits. */
#include "catalog_sdk.h"
#include <inttypes.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
static exr_error problem;
static int matched;
static char wanted[72];
static uint64_t wanted_bytes;
#define CHECK(x) do { if (!(x)) { fprintf(stderr,"D19 readback line %d: %s; SDK %s\n",__LINE__,#x,problem.message); return 1; } } while (0)
static int visit(void *context,const reader_catalog_row *row) {
  const exr_book *book=context;
  matched=(row->sdk_book_id==book->id && row->source_bytes==wanted_bytes && !strcmp(row->book_key,wanted));
  return 0;
}
int main(int argc,char **argv) {
  CHECK(argc==2 && getenv("GITHUB_ACTIONS") && !strcmp(getenv("GITHUB_ACTIONS"),"true"));
  char sdk[4096],product[4096];
  CHECK(snprintf(sdk,sizeof(sdk),"%s/library.sqlite",argv[1])<(int)sizeof(sdk));
  CHECK(snprintf(product,sizeof(product),"%s/library.sqlite.product.sqlite",argv[1])<(int)sizeof(product));
  exr_library *library=NULL;reader_catalog *catalog=NULL;
  CHECK(exr_library_open(sdk,&library,&problem)==EXR_OK);
  CHECK(reader_catalog_open(product,&catalog,NULL)==0);
  exr_book *books=NULL;size_t count=0;
  CHECK(exr_library_books(library,"",&books,&count,&problem)==EXR_OK);
  printf("{\"pid\":%ld,\"sdk_status\":0,\"catalog_status\":0,\"books\":[",(long)getpid());
  for(size_t i=0;i<count;i++) {
    char sha[65];uint64_t bytes=0;int found=0;
    CHECK(reader_catalog_sdk_original_identity(library,books[i].id,NULL,sha,&bytes,&problem)==EXR_OK);
    const char *format=books[i].format==EXR_TXT?"txt":books[i].format==EXR_EPUB?"epub":books[i].format==EXR_PDF?"pdf":books[i].format==EXR_CBZ?"cbz":"unknown";
    CHECK(snprintf(wanted,sizeof(wanted),"%s:%s",format,sha)<(int)sizeof(wanted));
    wanted_bytes=bytes;matched=0;
    CHECK(reader_catalog_local_lookup(catalog,books[i].id,NULL,visit,&books[i],&found,NULL)==0 && found && matched);
    printf("%s{\"id\":%"PRId64",\"format\":\"%s\",\"bytes\":%"PRIu64",\"sha256\":\"%s\",\"position\":%zu,\"catalog_matched\":true}",i?",":"",books[i].id,format,bytes,sha,books[i].position);
  }
  printf("],\"count\":%zu}\n",count);
  exr_books_free(books,count);CHECK(reader_catalog_close(&catalog,NULL)==0);exr_library_close(library);return 0;
}
