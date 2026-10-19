/* SPDX-License-Identifier: MIT */
#include "exreader.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static exr_error error; static unsigned checks;
#define CHECK(x) do { checks++; if(!(x)) { fprintf(stderr,"line %d: %s (%d: %s)\n",__LINE__,#x,error.code,error.message); exit(1); } } while(0)
#define OK(x) CHECK((x)==EXR_OK)
static const char prefix[]="<FictionBook xmlns='http://www.gribuser.ru/xml/fictionbook/2.0' xmlns:l='http://www.w3.org/1999/xlink'><body><section><p>Body</p></section></body>";
static void binary_case(const char *encoded,const char *decoded,size_t size,int valid) {
  char xml[4096]; exr_document *doc=NULL; void *data=NULL; size_t n; exr_status status;
  snprintf(xml,sizeof(xml),"%s<binary id='x' content-type='application/octet-stream'>%s</binary></FictionBook>",prefix,encoded);
  status=exr_document_open_memory(EXR_FB2,xml,strlen(xml),&doc,&error);
  if(valid) {
    CHECK(status==EXR_OK); OK(exr_document_resource(doc,0,&data,&n,&error));
    CHECK(n==size && (!n || !memcmp(data,decoded,n))); exr_free(data); exr_document_free(doc);
  } else CHECK(status==EXR_FORMAT && !doc);
}
static void invalid(const char *xml) {
  exr_document *doc=(exr_document *)(uintptr_t)1;
  CHECK(exr_document_open_memory(EXR_FB2,xml,strlen(xml),&doc,&error)==EXR_FORMAT); CHECK(!doc);
}
static void rich(const char *dir) {
  char path[4096]; exr_document *doc=NULL,*copy=NULL; exr_font *font=NULL; exr_layout *a=NULL,*b=NULL;
  exr_layout_config config=exr_layout_config_defaults(); exr_bitmap ba={0},bb={0};
  const exr_node *nodes; const exr_resource *resources; const exr_glyph *glyphs;
  size_t count,i,resource,target,images=0,tables=0,notes=0,heads=0,bold=0,italic=0,pa,pb;
  void *zip=NULL,*image=NULL; size_t size,n; const char *text;
  snprintf(path,sizeof(path),"%s/rich.fb2",dir); OK(exr_document_open(path,&doc,&error));
  CHECK(!strcmp(exr_document_title(doc),"Book & 图")); text=exr_document_text(doc,NULL);
  CHECK(strstr(text,"Normal bold and italic, note.")); CHECK(strstr(text,"Footnote text."));
  CHECK(!strstr(text,"Metadata only") && !strstr(text,"image/png") && !strstr(text,"color:"));
  resources=exr_document_resources(doc,&count); CHECK(count==1);
  CHECK(!strcmp(resources[0].properties,"cover-image") && !strcmp(resources[0].media_type,"image/png"));
  OK(exr_document_resource(doc,0,&image,&n,&error)); CHECK(n>60 && !memcmp(image,"\x89PNG",4)); exr_free(image);
  nodes=exr_document_nodes(doc,&count);
  for(i=0;i<count;i++) {
    if(nodes[i].kind==EXR_NODE_IMAGE) {
      images++; OK(exr_document_resolve(doc,0,exr_node_attribute(&nodes[i],"src"),&resource,&target,&error)); CHECK(resource==0);
    }
    if(nodes[i].kind==EXR_NODE_TABLE) tables++;
    if(nodes[i].kind==EXR_NODE_NOTE) notes++;
    if(nodes[i].kind==EXR_NODE_HEADING) heads++;
    if(nodes[i].kind==EXR_NODE_LINK) {
      CHECK(!strcmp(exr_node_attribute(&nodes[i],"role"),"doc-noteref"));
      OK(exr_document_resolve(doc,0,exr_node_attribute(&nodes[i],"href"),&resource,&target,&error));
      CHECK(target<count && nodes[target].kind==EXR_NODE_NOTE);
    }
  }
  CHECK(images==1 && tables==1 && notes==1 && heads==1);
  snprintf(path,sizeof(path),"%s/fonts/primary.ttf",dir); OK(exr_font_open(path,&font,&error));
  config.page=(exr_layout_options){260,180,8,16,1.2f,4};
  OK(exr_layout_create_ex(doc,font,&config,&a,&error));
  glyphs=exr_layout_glyphs(a,&count);
  for(i=0;i<count;i++) { if(glyphs[i].flags&EXR_GLYPH_BOLD) bold++; if(glyphs[i].flags&EXR_GLYPH_ITALIC) italic++; }
  CHECK(bold>=4 && italic>=6); CHECK(exr_layout_image(a,0));
  OK(exr_document_export_epub(doc,NULL,&zip,&size,&error));
  OK(exr_document_open_memory(EXR_EPUB,zip,size,&copy,&error)); exr_free(zip);
  CHECK(!strcmp(text,exr_document_text(copy,NULL)));
  OK(exr_layout_create_ex(copy,font,&config,&b,&error)); exr_layout_pages(a,&pa); exr_layout_pages(b,&pb); CHECK(pa==pb);
  for(i=0;i<pa;i++) {
    OK(exr_render_page(a,NULL,i,&ba,&error)); OK(exr_render_page(b,NULL,i,&bb,&error));
    CHECK(ba.stride==bb.stride && ba.height==bb.height && !memcmp(ba.pixels,bb.pixels,(size_t)ba.stride*ba.height));
    exr_bitmap_free(&ba); exr_bitmap_free(&bb);
  }
  exr_layout_free(a); exr_layout_free(b); exr_document_free(doc); exr_document_free(copy); exr_font_free(font);
}
int main(int argc,char **argv) {
  const char *bad[]={"A","AA","AAA","A===","=AAA","AA=A","AAAA=","AA==A","AB==","AAB=","!!!!","AAA-","TQ==TQ=="}; size_t i;
  CHECK(argc==2); rich(argv[1]);
  binary_case("","",0,1); binary_case("TQ==","M",1,1); binary_case("TWE=","Ma",2,1);
  binary_case("TWFu","Man",3,1); binary_case(" T W\nF\tu\r ","Man",3,1);
  for(i=0;i<sizeof(bad)/sizeof(*bad);i++) binary_case(bad[i],NULL,0,0);
  invalid("<FictionBook xmlns='urn:wrong'><body><p>Bad namespace</p></body></FictionBook>");
  invalid("<html><body>Wrong root</body></html>"); invalid("<FictionBook><description/></FictionBook>");
  invalid("<!DOCTYPE FictionBook [<!ENTITY x 'blocked'>]><FictionBook><body><p>&x;</p></body></FictionBook>");
  invalid("<FictionBook><body><image href='#missing'/></body></FictionBook>");
  invalid("<FictionBook><body><p>Text</p></body><binary id='x'>TQ==</binary><binary id='x'>TQ==</binary></FictionBook>");
  printf("%u rich FB2 checks passed\n",checks); return 0;
}
