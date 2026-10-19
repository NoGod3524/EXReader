/* SPDX-License-Identifier: MIT */
#include <exreader.h>
#include <stdio.h>
#include <string.h>
typedef struct {
  exr_publication *publication; exr_document *current;
  const exr_part *parts; size_t count,at; char id[48];
} source;
/* Keep only one chapter snapshot, then let replace() commit the whole source. */
static exr_status next(void *context,size_t ordinal,exr_text_part *out,int *found,exr_error *error) {
  source *s=context; size_t part,size; exr_status status; (void)ordinal;
  exr_document_free(s->current); s->current=NULL;
  while(s->at<s->count && !s->parts[s->at].in_reading_order) s->at++;
  if(s->at==s->count) { *found=0; return EXR_OK; }
  part=s->at++; status=exr_publication_load(s->publication,part,&s->current,error); if(status!=EXR_OK) return status;
  snprintf(s->id,sizeof(s->id),"part-%zu",part);
  out->id=s->id; out->text=exr_document_text(s->current,&size); out->size=size; *found=1; return EXR_OK;
}
static int example_main(int argc,char **argv) {
  source s={0}; exr_text_index *index=NULL; exr_text_query *query=NULL; exr_text_hit hit;
  exr_error error={0}; exr_status status; size_t hits=0; int found;
  if(argc!=4) { fprintf(stderr,"usage: exreader-search-example input.epub index.sqlite literal-query\n"); return 2; }
  if(!exr_text_index_available()) { puts("This SDK build omits the optional text index"); return 0; }
  status=exr_publication_open(argv[1],&s.publication,&error); if(status!=EXR_OK) goto done;
  s.parts=exr_publication_parts(s.publication,&s.count);
  status=exr_text_index_open(argv[2],&index,&error); if(status!=EXR_OK) goto done;
  status=exr_text_index_replace(index,argv[1],next,&s,NULL,&error); if(status!=EXR_OK) goto done;
  status=exr_text_index_query(index,argv[1],argv[3],strlen(argv[3]),NULL,&query,&error); if(status!=EXR_OK) goto done;
  while(hits<20) {
    status=exr_text_query_next(query,&hit,&found,&error); if(status!=EXR_OK || !found) break;
    printf("%s:%zu..%zu\n",hit.part,hit.start,hit.end); hits++;
  }
  printf("hits_shown=%zu\n",hits);
done:
  if(status!=EXR_OK) fprintf(stderr,"%d: %s\n",status,error.message);
  exr_text_query_free(query); exr_text_index_close(index); exr_document_free(s.current); exr_publication_free(s.publication);
  return status==EXR_OK ? 0 : 1;
}
#include "entry.h"
