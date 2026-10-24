/* SPDX-License-Identifier: MIT */
/* Cloud fixture generation through the installed public SDK, no guessed CFI. */
#include <exreader.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

int main(int argc,char **argv) {
  exr_document *document=NULL;exr_error error={0};char *cfi=NULL;size_t count=0;
  if(!getenv("GITHUB_ACTIONS") || strcmp(getenv("GITHUB_ACTIONS"),"true") || argc!=2) return 2;
  exr_status status=exr_document_open(argv[1],&document,&error);
  if(status!=EXR_OK) { fprintf(stderr,"CFI source: %s\n",error.message);return 1; }
  const exr_node *nodes=exr_document_nodes(document,&count);size_t chosen=SIZE_MAX;
  for(size_t i=0;i<count;i++) if(nodes[i].chapter==1 && nodes[i].kind==EXR_NODE_TEXT &&
      nodes[i].text && strstr(nodes[i].text,"A\xf0\x9f\x98\x80Z")) { chosen=i;break; }
  if(chosen!=SIZE_MAX) {
    exr_cfi_point point={chosen,3,0};
    status=exr_document_cfi_create(document,1,&point,NULL,&cfi,&error);
  } else status=EXR_FORMAT;
  if(status==EXR_OK && cfi) puts(cfi);
  else fprintf(stderr,"CFI target: %s\n",error.message);
  exr_free(cfi);exr_document_free(document);
  return status==EXR_OK && chosen!=SIZE_MAX ? 0:1;
}
