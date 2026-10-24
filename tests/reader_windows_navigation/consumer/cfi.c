/* SPDX-License-Identifier: MIT */
#include <exr/core.h>
#include <exr/document.h>
#include <exr/formats.h>
#include <stdio.h>
#include <stdint.h>
int main(int argc,char **argv) {
  exr_publication *publication=NULL;exr_document *document=NULL;exr_error error={0};char *cfi=NULL;
  if(argc!=2 || exr_publication_open(argv[1],&publication,&error)!=EXR_OK ||
     exr_publication_load(publication,1,&document,&error)!=EXR_OK) return 1;
  size_t count;const exr_node *nodes=exr_document_nodes(document,&count);exr_cfi_point point={SIZE_MAX,1,0};
  for(size_t i=0;i<count;i++) if(nodes[i].kind==EXR_NODE_TEXT) { point.node=i;break; }
  int result=1;
  if(point.node!=SIZE_MAX && exr_publication_cfi_create(publication,1,document,&point,NULL,&cfi,&error)==EXR_OK) {
    puts(cfi);result=0;
  }
  exr_free(cfi);exr_document_free(document);exr_publication_free(publication);return result;
}
