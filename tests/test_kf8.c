/* SPDX-License-Identifier: GPL-3.0-only */
#include "exreader.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static exr_error error; static unsigned checks;
#define CHECK(x) do { checks++; if(!(x)) { fprintf(stderr,"line %d: %s (%d: %s)\n",__LINE__,#x,error.code,error.message); exit(1); } } while(0)
#define OK(x) CHECK((x)==EXR_OK)
static void valid(const char *dir,const char *name,const char *expected,size_t chapters) {
  char path[4096]; exr_document *doc=NULL,*copy=NULL; size_t n,i,bold=0; void *data=NULL;
  const exr_chapter *parts; const exr_node *nodes;
  snprintf(path,sizeof(path),"%s/%s",dir,name); OK(exr_document_open(path,&doc,&error));
  CHECK(!strcmp(exr_document_text(doc,NULL),expected));
  parts=exr_document_chapters(doc,&n); CHECK(n==chapters);
  for(i=0;i<n;i++) {
    size_t size; OK(exr_document_resource(doc,parts[i].resource,&data,&size,&error));
    CHECK(size && !memcmp(data,"<html",5)); exr_free(data); data=NULL;
    CHECK(parts[i].in_spine && parts[i].linear);
  }
  nodes=exr_document_nodes(doc,&n);
  for(i=0;i<n;i++) if(nodes[i].name && strstr(nodes[i].name,"|b") && !strcmp(strrchr(nodes[i].name,'|'),"|b")) bold++;
  if(strstr(expected,"bold")) CHECK(bold==1);
  if(!strcmp(name,"kf8-flows.azw3")) {
    const exr_resource *r=exr_document_resources(doc,&n); CHECK(n==3 && !strcmp(r[0].path,"flow0001.bin"));
    OK(exr_document_resource(doc,0,&data,&n,&error)); CHECK(n==strlen("p { color: #123456; }") && !memcmp(data,"p {",3)); exr_free(data);
  }
  OK(exr_document_export_epub(doc,NULL,&data,&n,&error));
  OK(exr_document_open_memory(EXR_EPUB,data,n,&copy,&error)); exr_free(data);
  CHECK(!strcmp(exr_document_text(copy,NULL),expected)); exr_document_free(copy); exr_document_free(doc);
}
static void assets_case(const char *dir,const char *name) {
  char path[4096]; exr_document *doc=NULL,*copy=NULL; exr_font *font=NULL; exr_layout *a=NULL,*b=NULL;
  exr_layout_config config=exr_layout_config_defaults(); exr_bitmap ba={0},bb={0};
  const exr_resource *resources; const exr_node *nodes; const exr_glyph *glyphs;
  size_t n,i,images=0,embedded=0,pages,other; void *data=NULL,*original=NULL; size_t size;
  snprintf(path,sizeof(path),"%s/%s",dir,name); OK(exr_document_open(path,&doc,&error));
  CHECK(strstr(exr_document_text(doc,NULL),"Literal kindle:embed:ZZZZ"));
  resources=exr_document_resources(doc,&n); CHECK(n==6);
  for(i=0;i<n;i++) {
    if(!strcmp(resources[i].media_type,"text/css")) {
      char *text;
      OK(exr_document_resource(doc,i,&data,&size,&error));
      text=malloc(size+1); CHECK(text); memcpy(text,data,size); text[size]=0;
      CHECK(!strstr(text,"background:url(kindle:") && !strstr(text,"URL(\"kindle:"));
      if(strstr(text,"font-face")) {
        CHECK(strstr(text,"embed00003.bin") && strstr(text,"flow0002.bin"));
        CHECK(strstr(text,"content:\"kindle:embed:FFFF\"") && strstr(text,"/* url(kindle:embed:ZZZZ) */"));
      }
      free(text); exr_free(data);
    }
    if(!strcmp(resources[i].media_type,"font/ttf")) {
      FILE *f; long length;
      OK(exr_document_resource(doc,i,&data,&size,&error));
      snprintf(path,sizeof(path),"%s/fonts/fallback.ttf",dir); f=fopen(path,"rb"); CHECK(f);
      CHECK(!fseek(f,0,SEEK_END)); length=ftell(f); CHECK(length>0 && (size_t)length==size);
      rewind(f); original=malloc(size); CHECK(original); CHECK(fread(original,1,size,f)==size); fclose(f);
      CHECK(!memcmp(data,original,size)); free(original); exr_free(data);
    }
  }
  nodes=exr_document_nodes(doc,&n);
  for(i=0;i<n;i++) if(nodes[i].kind==EXR_NODE_IMAGE) {
    size_t resource,target; const char *src=exr_node_attribute(&nodes[i],"src");
    CHECK(src && !strncmp(src,"embed",5));
    OK(exr_document_resolve(doc,0,src,&resource,&target,&error)); CHECK(resource!=SIZE_MAX); images++;
  }
  CHECK(images==3);
  snprintf(path,sizeof(path),"%s/fonts/primary.ttf",dir); OK(exr_font_open(path,&font,&error));
  config.page=(exr_layout_options){240,160,8,20,1.2f,4};
  OK(exr_layout_create_ex(doc,font,&config,&a,&error));
  CHECK(exr_font_count(exr_layout_font(a))==2); glyphs=exr_layout_glyphs(a,&n);
  for(i=0;i<n;i++) if(glyphs[i].font_index==1) { embedded++; CHECK(glyphs[i].color==0x123456ff); }
  CHECK(embedded==1); resources=exr_document_resources(doc,&n);
  for(i=0;i<n;i++) if(!strncmp(resources[i].media_type,"image/",6)) CHECK(exr_layout_image(a,i));
  OK(exr_document_export_epub(doc,NULL,&data,&size,&error));
  OK(exr_document_open_memory(EXR_EPUB,data,size,&copy,&error)); exr_free(data);
  CHECK(!strcmp(exr_document_text(copy,NULL),exr_document_text(doc,NULL)));
  OK(exr_layout_create_ex(copy,font,&config,&b,&error)); exr_layout_pages(a,&pages); exr_layout_pages(b,&other); CHECK(pages==other);
  for(i=0;i<pages;i++) {
    OK(exr_render_page(a,NULL,i,&ba,&error)); OK(exr_render_page(b,NULL,i,&bb,&error));
    CHECK(ba.stride==bb.stride && ba.height==bb.height && !memcmp(ba.pixels,bb.pixels,(size_t)ba.stride*ba.height));
    exr_bitmap_free(&ba); exr_bitmap_free(&bb);
  }
  exr_layout_free(a); exr_layout_free(b); exr_font_free(font); exr_document_free(doc); exr_document_free(copy);
}
static void position_links(exr_document *doc) {
  size_t i,n,links=0,parts; const exr_node *nodes=exr_document_nodes(doc,&n);
  const exr_chapter *chapters=exr_document_chapters(doc,&parts); CHECK(parts>=2);
  for(i=0;i<n;i++) {
    const char *key=exr_node_attribute(&nodes[i],"data-test"),*href,*expected=NULL,*id;
    size_t resource,target;
    if(!key) continue;
    href=exr_node_attribute(&nodes[i],"href"); CHECK(href && !strstr(href,"kindle:"));
    OK(exr_document_resolve(doc,nodes[i].chapter,href,&resource,&target,&error)); CHECK(target<n && resource!=SIZE_MAX);
    CHECK(nodes[target].chapter==(!strcmp(key,"back") ? 0u : 1u));
    if(!strcmp(key,"top")) CHECK(target==chapters[1].root);
    else {
      if(!strcmp(key,"forward") || !strcmp(key,"inside")) {
        expected="target % # \xe7\x94\xb2";
        CHECK(strstr(href,"%25") && strstr(href,"%23") && strstr(href,"%E7%94%B2"));
      } else if(!strcmp(key,"legacy")) expected="legacy";
      else if(!strcmp(key,"xml")) expected="xml-target";
      else expected="shared";
      id=exr_node_attribute(&nodes[target],"id"); if(!id) id=exr_node_attribute(&nodes[target],"http://www.w3.org/XML/1998/namespace|id");
      CHECK(id && !strcmp(id,expected));
    }
    links++;
  }
  CHECK(links==7);
}
static void positions_case(const char *dir) {
  char path[4096]; exr_document *doc=NULL,*copy=NULL; void *data=NULL; size_t size;
  snprintf(path,sizeof(path),"%s/kf8-positions.azw3",dir); OK(exr_document_open(path,&doc,&error));
  position_links(doc); OK(exr_document_export_epub(doc,NULL,&data,&size,&error));
  OK(exr_document_open_memory(EXR_EPUB,data,size,&copy,&error)); exr_free(data);
  position_links(copy); CHECK(!strcmp(exr_document_text(doc,NULL),exr_document_text(copy,NULL)));
  exr_document_free(doc); exr_document_free(copy);
}
int main(int argc,char **argv) {
  const char *bad[]={"indx","pointer","idxt","total","tagx","controls","mask","ordt","version","insert-before","insert-after","length","file","missing-fragment","extra-fragment","overlap","label","fdst","xml","orphan","fdst-gap","vwi","short-header","decreasing-idxt","embed-zero","embed-range","embed-overflow","embed-bad-number","flow-zero","flow-range","flow-mime","flow-conflict","asset-signature","asset-pointer","font-flags","font-offset","font-key","font-size","font-key-start","font-trailing","font-compressed","pos-fid","pos-off","pos-overflow","pos-separator","pos-trailing","pos-empty","pos-prefix","pos-length","pos-duplicate","pos-body-duplicate"};
  const char *text="Chapter one\nA bold passage.\nChapter two\nSecond passage."; size_t i;
  CHECK(argc==2);
  valid(argv[1],"kf8-basic.azw3",text,2); valid(argv[1],"kf8-multirecord.azw3",text,2); valid(argv[1],"kf8-multicontrol.azw3",text,2);
  valid(argv[1],"kf8-flows.azw3",text,2);
  valid(argv[1],"kf8-unsplit.azw3","Chapter one\nA bold passage.",1);
  valid(argv[1],"kf8-two-inserts.azw3","One.\nTwo.",1);
  valid(argv[1],"kf8-zero-fragments.azw3","",1);
  for(i=0;i<sizeof(bad)/sizeof(*bad);i++) {
    char path[4096]; exr_document *doc=(exr_document *)(uintptr_t)1; exr_status status;
    snprintf(path,sizeof(path),"%s/kf8-bad-%s.azw3",argv[1],bad[i]); status=exr_document_open(path,&doc,&error);
    if(status!=EXR_FORMAT) fprintf(stderr,"fixture %s returned %d\n",bad[i],status);
    CHECK(status==EXR_FORMAT && !doc && error.code==EXR_FORMAT && error.message[0]);
  }
  positions_case(argv[1]);
  assets_case(argv[1],"kf8-assets.azw3");
  assets_case(argv[1],"kf8-assets-font0.azw3"); assets_case(argv[1],"kf8-assets-font1.azw3"); assets_case(argv[1],"kf8-assets-font2.azw3");
  { char path[4096]; exr_document *doc=NULL; snprintf(path,sizeof(path),"%s/kf8-limit-font.azw3",argv[1]); CHECK(exr_document_open(path,&doc,&error)==EXR_LIMIT && !doc); }
  printf("%u KF8 checks passed\n",checks); return 0;
}
