/* SPDX-License-Identifier: MIT */
#include "exr/textindex.h"
#include <stdio.h>
#include <string.h>
#if defined(EXR_DOCUMENT_H) || defined(EXR_LIBRARY_H) || defined(EXR_AUDIO_H)
#error Text indexing must be independent of documents, library and audio
#endif
#define CHECK(x) do { if(!(x)) { fprintf(stderr,"line %d: %s (%s)\n",__LINE__,#x,e.message);return 1; } } while(0)
int main(void) {
  exr_error e={0};exr_text_index *index=NULL;exr_text_query *query=NULL;exr_text_hit hit={0};int found=0;
  if(!exr_text_index_available()) {
    CHECK(exr_text_index_open(":memory:",&index,&e)==EXR_FORMAT && !index);return 0;
  }
  CHECK(exr_text_index_open(":memory:",&index,&e)==EXR_OK);
  CHECK(exr_text_index_put(index,"source","part","banana",6,NULL,&e)==EXR_OK);
  CHECK(exr_text_index_query(index,"source","ana",3,NULL,&query,&e)==EXR_OK);
  CHECK(exr_text_query_next(query,&hit,&found,&e)==EXR_OK && found && hit.start==1 && hit.end==4 && !strcmp(hit.part,"part"));
  CHECK(exr_text_query_next(query,&hit,&found,&e)==EXR_OK && found && hit.start==3 && hit.end==6);
  CHECK(exr_text_query_next(query,&hit,&found,&e)==EXR_OK && !found);exr_text_query_free(query);
  CHECK(exr_text_index_remove(index,"source",NULL,NULL,&e)==EXR_OK);exr_text_index_close(index);
  puts("Independent text index component passed");return 0;
}
