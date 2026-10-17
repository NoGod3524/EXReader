/* SPDX-License-Identifier: GPL-3.0-only */
#include "exreader.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static exr_error error; static unsigned checks;
#define CHECK(x) do { checks++; if(!(x)) { fprintf(stderr,"line %d: %s (%d: %s)\n",__LINE__,#x,error.code,error.message); exit(1); } } while(0)
#define OK(x) CHECK((x)==EXR_OK)
static exr_document *open(const char *source) { exr_document *d=NULL; OK(exr_document_open_memory(EXR_RTF,source,strlen(source),&d,&error)); return d; }
static void roundtrip(exr_document *doc,const char *dir,size_t minimum_pages) {
  exr_document *copy=NULL; void *zip=NULL; size_t size,count_a,count_b,i; exr_font *font=NULL; exr_layout *a=NULL,*b=NULL; exr_bitmap ba,bb; char path[4096];
  exr_layout_config config=exr_layout_config_defaults(); config.page=(exr_layout_options){200,100,4,14,1.2f,2};
  snprintf(path,sizeof(path),"%s/fonts/primary.ttf",dir); OK(exr_font_open(path,&font,&error));
  OK(exr_document_export_epub(doc,NULL,&zip,&size,&error)); OK(exr_document_open_memory(EXR_EPUB,zip,size,&copy,&error)); exr_free(zip);
  CHECK(!strcmp(exr_document_text(doc,NULL),exr_document_text(copy,NULL)));
  OK(exr_layout_create_ex(doc,font,&config,&a,&error)); OK(exr_layout_create_ex(copy,font,&config,&b,&error));
  exr_layout_pages(a,&count_a); exr_layout_pages(b,&count_b); CHECK(count_a==count_b && count_a>=minimum_pages);
  for(i=0;i<count_a;i++) { OK(exr_render_page(a,NULL,i,&ba,&error)); OK(exr_render_page(b,NULL,i,&bb,&error)); CHECK(ba.stride==bb.stride && ba.height==bb.height && !memcmp(ba.pixels,bb.pixels,(size_t)ba.stride*ba.height)); exr_bitmap_free(&ba); exr_bitmap_free(&bb); }
  exr_layout_free(a); exr_layout_free(b); exr_font_free(font); exr_document_free(copy);
}
int main(int argc,char **argv) {
  const char source[]="{\\rtf1 Before\\par\\trowd\\cellx1500\\cellx3000\\pard\\intbl A {\\b bold}\\par second\\cell\\pard\\intbl B\\cell\\row\\trowd\\cellx1500\\cellx3000\\intbl C\\cell\\qc\\cell\\row\\pard After\\par\\trowd\\intbl No width\\cell\\row\\pard End}";
  exr_document *d; const exr_node *nodes; const char *text; size_t count,i,tables=0,rows=0,cells=0,boundaries=0; char large[8192]; size_t at=0;
  const char *bad[]={"{\\rtf1\\cell}","{\\rtf1\\row}","{\\rtf1\\trowd A\\cell}","{\\rtf1\\trowd A\\row}","{\\rtf1\\trowd\\cellx1\\cellx2 A\\cell\\row}","{\\rtf1\\trowd\\trowd}","{\\rtf1\\itap2 A}","{\\rtf1\\trowd\\cellx2\\cellx1 A\\cell\\row}","{\\rtf1\\trowd\\clmrg\\cellx1 A\\cell\\row}","{\\rtf1\\trowd\\clvmrg\\cellx1 A\\cell\\row}"};
  CHECK(argc==2); d=open(source); text=exr_document_text(d,NULL); CHECK(strstr(text,"Before") && strstr(text,"A bold") && strstr(text,"second") && strstr(text,"No width") && strstr(text,"End"));
  nodes=exr_document_nodes(d,&count);
  for(i=0;i<count;i++) {
    if(nodes[i].kind==EXR_NODE_TABLE) tables++;
    if(nodes[i].kind==EXR_NODE_ROW) rows++;
    if(nodes[i].kind==EXR_NODE_CELL) { const char *value=exr_node_attribute(&nodes[i],"data-rtf-cellx"); cells++; if(value) { CHECK(!strcmp(value,"1500") || !strcmp(value,"3000")); boundaries++; } }
  }
  CHECK(tables==2 && rows==3 && cells==5 && boundaries==4); roundtrip(d,argv[1],2); exr_document_free(d);
  d=open("{\\rtf1\\trowd X\\cell Y\\cell\\cellx1000\\cellx2000\\row}"); nodes=exr_document_nodes(d,&count); cells=0;
  for(i=0;i<count;i++) if(nodes[i].kind==EXR_NODE_CELL) { CHECK(exr_node_attribute(&nodes[i],"data-rtf-cellx")); cells++; } CHECK(cells==2); exr_document_free(d);
  d=open("{\\rtf1\\uc1\\u65\\cell B}"); CHECK(!strcmp(exr_document_text(d,NULL),"AB")); exr_document_free(d);
  d=open("{\\rtf1{\\*\\unknown\\trowd ignored\\cell\\row}Visible}"); CHECK(!strcmp(exr_document_text(d,NULL),"Visible")); exr_document_free(d);
  for(i=0;i<sizeof(bad)/sizeof(*bad);i++) CHECK(exr_document_open_memory(EXR_RTF,bad[i],strlen(bad[i]),&d,&error)==EXR_FORMAT && !d);
  at+=(size_t)snprintf(large+at,sizeof(large)-at,"{\\rtf1\\trowd");
  for(i=0;i<257;i++) at+=(size_t)snprintf(large+at,sizeof(large)-at,"\\cellx%zu",i+1);
  CHECK(exr_document_open_memory(EXR_RTF,large,at,&d,&error)==EXR_LIMIT && !d);
  at=(size_t)snprintf(large,sizeof(large),"{\\rtf1");
  for(i=0;i<20;i++) at+=(size_t)snprintf(large+at,sizeof(large)-at,"\\trowd\\cellx1000\\cellx2000\\intbl R%zu left\\cell R%zu right\\cell\\row",i,i);
  large[at++]='}'; large[at]=0; d=open(large); roundtrip(d,argv[1],2); exr_document_free(d);
  {
    const char merged[]="{\\rtf1\\trowd\\clmgf\\clvmgf\\cellx1000\\clmrg\\clvmgf\\cellx2000\\cellx3000 A {\\b bold}\\cell\\cell X\\cell\\row\\trowd\\clmgf\\clvmrg\\cellx1000\\clmrg\\clvmrg\\cellx2000\\cellx3000 B {\\i more}\\cell\\cell Y\\cell\\row}";
    size_t colspan=0,rowspan=0,hidden=0; d=open(merged); nodes=exr_document_nodes(d,&count); cells=0;
    for(i=0;i<count;i++) {
      if(nodes[i].kind==EXR_NODE_CELL) {
        const char *cspan=exr_node_attribute(&nodes[i],"colspan"),*rspan=exr_node_attribute(&nodes[i],"rowspan"); cells++;
        if(cspan) { CHECK(!strcmp(cspan,"2")); colspan++; } if(rspan) { CHECK(!strcmp(rspan,"2")); rowspan++; }
      }
      if(nodes[i].kind==EXR_NODE_ELEMENT && exr_node_attribute(&nodes[i],"style") && !strcmp(exr_node_attribute(&nodes[i],"style"),"display:none;")) hidden++;
      if(nodes[i].parent!=SIZE_MAX) CHECK(nodes[i].parent<i);
    }
    CHECK(cells==3 && colspan==1 && rowspan==1 && hidden==2); CHECK(strstr(exr_document_text(d,NULL),"A bold") && strstr(exr_document_text(d,NULL),"B more")); roundtrip(d,argv[1],1); exr_document_free(d);
  }
  d=open("{\\rtf1\\trowd\\clmgf\\cellx1000\\clmrg\\cellx2000 H1\\cell H2\\cell\\row}"); nodes=exr_document_nodes(d,&count); cells=0;
  for(i=0;i<count;i++) if(nodes[i].kind==EXR_NODE_CELL) { CHECK(!strcmp(exr_node_attribute(&nodes[i],"colspan"),"2")); cells++; } CHECK(cells==1); CHECK(strstr(exr_document_text(d,NULL),"H1") && strstr(exr_document_text(d,NULL),"H2")); roundtrip(d,argv[1],1); exr_document_free(d);
  d=open("{\\rtf1\\trowd\\clvmgf\\cellx1000 A\\cell\\row\\trowd\\clvmrg\\cellx1000 B\\cell\\row}"); roundtrip(d,argv[1],1); exr_document_free(d); /* Empty continued row. */
  {
    const char *invalid[]={
      "{\\rtf1\\trowd\\clmgf A\\cell\\row}",
      "{\\rtf1\\trowd\\clmgf\\clvmgf\\cellx1\\clmrg\\clvmrg\\cellx2 A\\cell B\\cell\\row}",
      "{\\rtf1\\trowd\\clvmgf\\cellx1000 A\\cell\\row\\trowd\\clvmrg\\cellx1100 B\\cell\\row}",
      "{\\rtf1\\trowd\\clvmgf\\cellx1000 A\\cell\\row\\trowd\\cellx1000 B\\cell\\row\\trowd\\clvmrg\\cellx1000 C\\cell\\row}",
      "{\\rtf1\\trowd\\clvmgf\\cellx1000 A\\cell\\row\\pard Break\\par\\trowd\\clvmrg\\cellx1000 B\\cell\\row}"
    };
    for(i=0;i<sizeof(invalid)/sizeof(*invalid);i++) CHECK(exr_document_open_memory(EXR_RTF,invalid[i],strlen(invalid[i]),&d,&error)==EXR_FORMAT && !d);
  }
  printf("%u RTF table checks passed\n",checks); return 0;
}
