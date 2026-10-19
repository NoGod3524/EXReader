/* SPDX-License-Identifier: MIT */
#include "exreader.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static exr_error error; static unsigned checks;
#define CHECK(x) do { checks++; if(!(x)) { fprintf(stderr,"line %d: %s (%d: %s)\n",__LINE__,#x,error.code,error.message); exit(1); } } while(0)
#define OK(x) CHECK((x)==EXR_OK)
static exr_document *open(const char *s) { exr_document *d=NULL; OK(exr_document_open_memory(EXR_RTF,s,strlen(s),&d,&error)); return d; }
static void roundtrip(exr_document *doc,const char *dir) {
  exr_document *copy=NULL; void *zip=NULL; size_t size,pa,pb,i; exr_font *font=NULL; exr_layout *a=NULL,*b=NULL; exr_bitmap ba,bb; char path[4096];
  exr_layout_config config=exr_layout_config_defaults(); config.page=(exr_layout_options){220,160,4,14,1.2f,2};
  snprintf(path,sizeof(path),"%s/fonts/primary.ttf",dir); OK(exr_font_open(path,&font,&error));
  OK(exr_document_export_epub(doc,NULL,&zip,&size,&error)); OK(exr_document_open_memory(EXR_EPUB,zip,size,&copy,&error)); exr_free(zip);
  CHECK(!strcmp(exr_document_text(doc,NULL),exr_document_text(copy,NULL)));
  OK(exr_layout_create_ex(doc,font,&config,&a,&error)); OK(exr_layout_create_ex(copy,font,&config,&b,&error)); exr_layout_pages(a,&pa); exr_layout_pages(b,&pb); CHECK(pa==pb && pa);
  for(i=0;i<pa;i++) { OK(exr_render_page(a,NULL,i,&ba,&error)); OK(exr_render_page(b,NULL,i,&bb,&error)); CHECK(ba.stride==bb.stride && ba.height==bb.height && !memcmp(ba.pixels,bb.pixels,(size_t)ba.stride*ba.height)); exr_bitmap_free(&ba); exr_bitmap_free(&bb); }
  exr_layout_free(a); exr_layout_free(b); exr_font_free(font); exr_document_free(copy);
}
int main(int argc,char **argv) {
  const char source[]="{\\rtf1{\\*\\listtable Hidden}\\pard\\ls1\\ilvl0{\\listtext\\pard\\plain 1.\\tab}First{\\footnote\\chftn Note} item\\par\\pard\\ls1\\ilvl1{\\listtext a)\\tab}Nested\\par\\pard\\ls1\\ilvl0{\\listtext 2.\\tab}Second\\par\\pard Plain\\par\\pard\\ls2{\\listtext\\u8226?\\tab}Bullet\\par\\pard Before jump\\par\\pard\\ls3\\ilvl2{\\listtext i.\\tab}Jump\\par\\pard End jump\\par\\pard{\\pntext 1.\\tab}Legacy first\\par\\pard{\\pntext 2.\\tab}Legacy second}";
  const char *bad[]={"{\\rtf1\\ls-1 A}","{\\rtf1\\ilvl9 A}","{\\rtf1\\ilvl-1 A}","{\\rtf1\\ls A}"};
  exr_document *d; const exr_node *nodes; const char *text; size_t count,i,lists=0,items=0,placeholders=0,markers=0,root_one=0,bullets=0;
  CHECK(argc==2); d=open(source); text=exr_document_text(d,NULL);
  CHECK(strstr(text,"1. First1 item") && strstr(text,"a) Nested") && strstr(text,"2. Second") && strstr(text,"Legacy second") && !strstr(text,"Hidden"));
  nodes=exr_document_nodes(d,&count);
  for(i=0;i<count;i++) {
    const char *role=exr_node_attribute(&nodes[i],"role");
    if(nodes[i].kind==EXR_NODE_LIST) {
      const char *id=exr_node_attribute(&nodes[i],"data-rtf-list-id"),*level=exr_node_attribute(&nodes[i],"data-rtf-list-level"); CHECK(id && level); lists++;
      if(!strcmp(id,"1") && !strcmp(level,"0")) root_one++;
      if(strstr(nodes[i].name,"|ul")) bullets++;
    }
    if(nodes[i].kind==EXR_NODE_LIST_ITEM) { items++; if(role && !strcmp(role,"presentation")) placeholders++; }
    if(role && !strcmp(role,"presentation") && exr_node_attribute(&nodes[i],"aria-hidden")) markers++;
  }
  CHECK(root_one==1 && lists==7 && items==9 && placeholders==2 && markers==7 && bullets==1); roundtrip(d,argv[1]); exr_document_free(d);
  d=open("{\\rtf1\\trowd\\cellx1000\\cellx2000\\pard\\intbl\\ls1{\\listtext 1.\\tab}Cell one\\par{\\listtext 2.\\tab}Cell two\\cell\\pard\\intbl\\ls1{\\listtext 1.\\tab}Other cell\\cell\\row}"); roundtrip(d,argv[1]); exr_document_free(d);
  for(i=0;i<sizeof(bad)/sizeof(*bad);i++) CHECK(exr_document_open_memory(EXR_RTF,bad[i],strlen(bad[i]),&d,&error)==EXR_FORMAT && !d);
  printf("%u RTF list checks passed\n",checks); return 0;
}
