/* SPDX-License-Identifier: GPL-3.0-only */
#include "exreader.h"
#include <expat.h>
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
static void check_navigation(exr_document *doc,const exr_navigation *nav,size_t count) {
  const char *labels[]={"Alpha","Child","Deep","Sibling","Beta \xe4\xba\x8c & \"quotes\""};
  const char *ids[]={"chapter-a","child-a","deep-a","child-b","chapter-b"};
  size_t expected[]={SIZE_MAX,0,1,0,SIZE_MAX},i,n; const exr_node *nodes=exr_document_nodes(doc,&n);
  CHECK(count==5);
  for(i=0;i<count;i++) {
    size_t target,resource; const char *id;
    CHECK(!strcmp(nav[i].label,labels[i]) && nav[i].parent==expected[i]);
    CHECK(nav[i].part==(i==4 ? 1u : 0u) && !strcmp(nav[i].role,"toc"));
    OK(exr_document_resolve(doc,0,nav[i].href,&resource,&target,&error)); CHECK(target<n);
    id=exr_node_attribute(&nodes[target],"id"); CHECK(id && !strcmp(id,ids[i]));
  }
}
static void navigation_case(const char *dir,const char *name) {
  char path[4096]; exr_document *doc=NULL,*copy=NULL; exr_navigation *a=NULL,*b=NULL;
  exr_publication *publication=NULL; const exr_navigation *borrowed; size_t n,m,size; void *data=NULL;
  snprintf(path,sizeof(path),"%s/%s",dir,name); OK(exr_document_open(path,&doc,&error));
  OK(exr_document_navigation(doc,&a,&n,&error)); check_navigation(doc,a,n);
  CHECK(!strstr(exr_document_text(doc,NULL),"quotes"));
  OK(exr_document_export_epub(doc,NULL,&data,&size,&error));
  OK(exr_document_open_memory(EXR_EPUB,data,size,&copy,&error));
  OK(exr_document_navigation(copy,&b,&m,&error)); check_navigation(copy,b,m); exr_navigation_free(b,m);
  OK(exr_publication_open_memory(EXR_EPUB,data,size,&publication,&error)); exr_free(data);
  OK(exr_publication_navigation(publication,&borrowed,&m,&error)); CHECK(m==n);
  check_navigation(copy,borrowed,m);
  exr_publication_free(publication); exr_document_free(copy); exr_document_free(doc);
  CHECK(!strcmp(a[1].label,"Child") && a[2].parent==1); exr_navigation_free(a,n);
}
static void navigation_api(void) {
  exr_document *doc=NULL; exr_navigation *nav=(exr_navigation *)(uintptr_t)1; size_t n=99;
  CHECK(exr_document_navigation(NULL,&nav,&n,&error)==EXR_ARGUMENT && !nav && !n);
  OK(exr_document_open_memory(EXR_TXT,"Plain",5,&doc,&error));
  OK(exr_document_navigation(doc,&nav,&n,&error)); CHECK(!nav && !n);
  CHECK(exr_document_navigation(doc,NULL,&n,&error)==EXR_ARGUMENT && !n);
  CHECK(exr_document_navigation(doc,&nav,NULL,&error)==EXR_ARGUMENT && !nav);
  exr_navigation_free(NULL,0); exr_document_free(doc);
}
static void guide_check(exr_document *doc,int authored,int offset) {
  exr_navigation *nav=NULL; size_t n,i,count,landmarks=0,base=authored ? 5 : 2; const exr_node *nodes=exr_document_nodes(doc,&count);
  const char *labels[]={"Cover","Read from here","Other & custom"};
  OK(exr_document_navigation(doc,&nav,&n,&error)); CHECK(n==base+3);
  for(i=0;i<n;i++) {
    const exr_navigation *v=&nav[i]; size_t resource,target,index;
    if(strcmp(v->role,"landmarks")) { CHECK(!strcmp(v->role,"toc")); continue; }
    index=landmarks++; CHECK(index<3);
    CHECK(v->parent==SIZE_MAX && !strcmp(v->label,labels[index]));
    CHECK(v->part==(index==1 ? 1u : 0u));
    OK(exr_document_resolve(doc,0,v->href,&resource,&target,&error)); CHECK(target<count);
    if(authored) {
      const char *id=exr_node_attribute(&nodes[target],"id");
      CHECK(id && !strcmp(id,index==1 ? "chapter-b" : index==2 && offset ? "deep-a" : "chapter-a"));
    } else CHECK(nodes[target].kind==EXR_NODE_CHAPTER);
  }
  CHECK(landmarks==3);
  exr_navigation_free(nav,n);
}
static void guide_case(const char *dir,const char *name,int authored,int offset) {
  char path[4096]; exr_document *doc=NULL,*copy=NULL; const exr_resource *resources;
  void *data=NULL; size_t n,i,size; int found=0;
  snprintf(path,sizeof(path),"%s/%s",dir,name); OK(exr_document_open(path,&doc,&error)); guide_check(doc,authored,offset);
  resources=exr_document_resources(doc,&n);
  for(i=0;i<n;i++) if(!strcmp(resources[i].media_type,"application/x-dtbncx+xml")) {
    char *text; OK(exr_document_resource(doc,i,&data,&size,&error)); text=malloc(size+1); CHECK(text);
    memcpy(text,data,size); text[size]=0; exr_free(data);
    CHECK(strstr(text,"class=\"cover\"") && strstr(text,"class=\"text\"") && strstr(text,"class=\"other:preface\""));
    CHECK(!strstr(text,"thumbimagestandard")); free(text); found++;
  }
  CHECK(found==1); OK(exr_document_export_epub(doc,NULL,&data,&size,&error));
  OK(exr_document_open_memory(EXR_EPUB,data,size,&copy,&error)); exr_free(data); guide_check(copy,authored,offset);
  CHECK(!strcmp(exr_document_text(doc,NULL),exr_document_text(copy,NULL)));
  exr_document_free(doc); exr_document_free(copy);
}
typedef struct { char image[128],use[128],text[2048]; size_t size; unsigned roots,images,local,foreign,style; } svg_info;
static void XMLCALL svg_start(void *context,const char *name,const char **attributes) {
  svg_info *info=context; size_t i;
  if(!strcmp(name,"http://www.w3.org/2000/svg|svg")) info->roots++;
  if(!strcmp(name,"local")) info->local++;
  if(!strcmp(name,"urn:exreader:extension|style")) info->foreign++;
  if(!strcmp(name,"http://www.w3.org/2000/svg|image")) {
    info->images++;
    for(i=0;attributes[i];i+=2) {
      if(!strcmp(attributes[i],"http://www.w3.org/1999/xlink|href")) {
        CHECK(strlen(attributes[i+1])<sizeof(info->image)); strcpy(info->image,attributes[i+1]);
      }
      if(!strcmp(attributes[i],"style") && strstr(attributes[i+1],"embed00001.bin")) info->style++;
    }
  }
  if(!strcmp(name,"http://www.w3.org/2000/svg|use"))
    for(i=0;attributes[i];i+=2) if(!strcmp(attributes[i],"href")) {
      CHECK(strlen(attributes[i+1])<sizeof(info->use)); strcpy(info->use,attributes[i+1]);
    }
}
static void XMLCALL svg_text(void *context,const char *text,int size) {
  svg_info *info=context; CHECK(size>=0 && (size_t)size<sizeof(info->text)-info->size);
  memcpy(info->text+info->size,text,(size_t)size); info->size+=(size_t)size; info->text[info->size]=0;
}
static svg_info svg_parse(const void *data,size_t size) {
  svg_info info={0}; XML_Parser parser=XML_ParserCreateNS(NULL,'|'); CHECK(parser && size<INT32_MAX);
  XML_SetUserData(parser,&info); XML_SetStartElementHandler(parser,svg_start); XML_SetCharacterDataHandler(parser,svg_text);
  CHECK(XML_Parse(parser,data,(int)size,XML_TRUE)==XML_STATUS_OK); XML_ParserFree(parser); CHECK(info.roots==1); return info;
}
typedef struct { exr_document *doc; unsigned decoded,released; } svg_decoder;
static exr_status host_svg(void *context,const exr_resource *resource,const void *data,size_t size,exr_bitmap *out,exr_error *e) {
  svg_decoder *state=context; svg_info info; void *png=NULL; size_t n,index,node; exr_status status;
  if(strcmp(resource->media_type,"image/svg+xml")) return exr_image_decode(data,size,out,e);
  state->decoded++; info=svg_parse(data,size);
  CHECK(info.images==1 && info.local==1 && info.foreign==1 && info.style==1 && !strcmp(info.image,"embed00001.bin"));
  CHECK(!strcmp(info.use,"flow0003.bin#symbol%20%25") && strstr(info.text,"url(embed00002.bin)"));
  CHECK(strstr(info.text,"url(kindle:embed:FFFF)") && strstr(info.text,"Literal kindle:embed:ZZZZ"));
  status=exr_document_resolve(state->doc,0,info.image,&index,&node,e); if(status!=EXR_OK) return status;
  status=exr_document_resource(state->doc,index,&png,&n,e); if(status!=EXR_OK) return status;
  status=exr_image_decode(png,n,out,e); exr_free(png); return status;
}
static void host_svg_release(void *context,exr_bitmap *out) {
  svg_decoder *state=context; state->released++; exr_bitmap_free(out);
}
static void svg_case(const char *dir,const char *name) {
  char path[4096]; exr_document *doc=NULL,*copy=NULL; exr_font *font=NULL; exr_layout *a=NULL,*b=NULL;
  const exr_resource *resources; const exr_glyph *glyphs; exr_layout_config config=exr_layout_config_defaults();
  exr_bitmap ba={0},bb={0}; svg_decoder state={0}; void *data=NULL; size_t n,size,i,svgs=0,pages,other;
  snprintf(path,sizeof(path),"%s/%s",dir,name); OK(exr_document_open(path,&doc,&error));
  resources=exr_document_resources(doc,&n); CHECK(n==7);
  for(i=0;i<n;i++) if(!strcmp(resources[i].media_type,"image/svg+xml")) {
    svg_info info; OK(exr_document_resource(doc,i,&data,&size,&error)); info=svg_parse(data,size); exr_free(data); svgs++;
    if(!info.images) CHECK(!strcmp(info.use,"flow0002.bin"));
  }
  CHECK(svgs==2);
  snprintf(path,sizeof(path),"%s/fonts/primary.ttf",dir); OK(exr_font_open(path,&font,&error));
  config.page=(exr_layout_options){180,120,8,20,1.2f,0}; config.decode_image=host_svg; config.release_image=host_svg_release; config.image_context=&state;
  state.doc=doc; OK(exr_layout_create_ex(doc,font,&config,&a,&error));
  glyphs=exr_layout_glyphs(a,&n); CHECK(n==1 && glyphs[0].font_index==1 && glyphs[0].color==0x123456ff);
  OK(exr_document_export_epub(doc,NULL,&data,&size,&error)); OK(exr_document_open_memory(EXR_EPUB,data,size,&copy,&error)); exr_free(data);
  state.doc=copy; OK(exr_layout_create_ex(copy,font,&config,&b,&error));
  exr_layout_pages(a,&pages); exr_layout_pages(b,&other); CHECK(pages==other);
  for(i=0;i<pages;i++) {
    OK(exr_render_page(a,NULL,i,&ba,&error)); OK(exr_render_page(b,NULL,i,&bb,&error));
    CHECK(ba.stride==bb.stride && ba.height==bb.height && !memcmp(ba.pixels,bb.pixels,(size_t)ba.stride*ba.height));
    exr_bitmap_free(&ba); exr_bitmap_free(&bb);
  }
  exr_layout_free(a); exr_layout_free(b); CHECK(state.decoded==2 && state.released==2);
  exr_font_free(font); exr_document_free(doc); exr_document_free(copy);
}
int main(int argc,char **argv) {
  const char *bad[]={"indx","pointer","idxt","total","tagx","controls","mask","ordt","version","insert-before","insert-after","length","file","missing-fragment","extra-fragment","overlap","label","fdst","xml","orphan","fdst-gap","vwi","short-header","decreasing-idxt","embed-zero","embed-range","embed-overflow","embed-bad-number","flow-zero","flow-range","flow-mime","flow-conflict","asset-signature","asset-pointer","font-flags","font-offset","font-key","font-size","font-key-start","font-trailing","font-compressed","pos-fid","pos-off","pos-overflow","pos-separator","pos-trailing","pos-empty","pos-prefix","pos-length","pos-duplicate","pos-body-duplicate","nav-title","nav-level","nav-parent","nav-child","nav-last","nav-leaf","nav-target","cncx-truncated","cncx-padding","cncx-index","boundary-pointer","boundary-text","boundary-marker","boundary-version","boundary-encrypted","boundary-resource","exth-signature","exth-length","exth-count","exth-entry","exth-entry-size","exth-duplicate","exth-fallback-encoding","exth-fallback-compression","guide-label","guide-target","guide-kind","svg-xml","svg-root","svg-entity","svg-reference","svg-namespace","svg-fragment","ordt-count","ordt-entries","ordt-pointer","ordt-signature","ordt-value","ordt-overlap","ordt-label","ordt-missing","ordt-local-conflict","ordt-late-label","skel-repeats"};
  const char *text="Chapter one\nA bold passage.\nChapter two\nSecond passage."; size_t i;
  CHECK(argc==2);
  valid(argv[1],"kf8-skel-repeats.azw3",text,2); valid(argv[1],"kf8-ordt-basic.azw3",text,2); valid(argv[1],"kf8-hybrid.azw3",text,2); valid(argv[1],"kf8-basic.azw3",text,2); valid(argv[1],"kf8-multirecord.azw3",text,2); valid(argv[1],"kf8-multicontrol.azw3",text,2);
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
  guide_case(argv[1],"kf8-ordt-guide.azw3",1,0); guide_case(argv[1],"kf8-ordt-local.azw3",1,0);
  guide_case(argv[1],"kf8-ordt-utf8-header.azw3",1,0); guide_case(argv[1],"kf8-hybrid-ordt.azw3",1,0);
  navigation_case(argv[1],"kf8-ordt-navigation.azw3");
  svg_case(argv[1],"kf8-svg.azw3"); svg_case(argv[1],"kf8-hybrid-svg.azw3");
  guide_case(argv[1],"kf8-guide.azw3",1,0); guide_case(argv[1],"kf8-guide-only.azw3",0,0);
  guide_case(argv[1],"kf8-guide-offset.azw3",1,1); guide_case(argv[1],"kf8-hybrid-guide.azw3",1,0);
  navigation_api(); navigation_case(argv[1],"kf8-navigation.azw3"); navigation_case(argv[1],"kf8-navigation-derived.azw3");
  navigation_case(argv[1],"kf8-hybrid-navigation.azw3");
  positions_case(argv[1]);
  assets_case(argv[1],"kf8-hybrid-assets.azw3"); assets_case(argv[1],"kf8-hybrid-all-shared.azw3");
  assets_case(argv[1],"kf8-hybrid-local-assets.azw3"); assets_case(argv[1],"kf8-hybrid-huff.azw3");
  assets_case(argv[1],"kf8-assets.azw3");
  assets_case(argv[1],"kf8-assets-font0.azw3"); assets_case(argv[1],"kf8-assets-font1.azw3"); assets_case(argv[1],"kf8-assets-font2.azw3");
  { char path[4096]; exr_document *doc=NULL; snprintf(path,sizeof(path),"%s/kf8-limit-font.azw3",argv[1]); CHECK(exr_document_open(path,&doc,&error)==EXR_LIMIT && !doc); }
  { char path[4096]; exr_document *doc=NULL; snprintf(path,sizeof(path),"%s/kf8-legacy-exth.azw3",argv[1]); OK(exr_document_open(path,&doc,&error)); CHECK(!strcmp(exr_document_text(doc,NULL),"Legacy fallback.")); exr_document_free(doc); }
  { char path[4096]; exr_document *doc=NULL; snprintf(path,sizeof(path),"%s/kf8-encoding-guide.azw3",argv[1]); CHECK(exr_document_open(path,&doc,&error)==EXR_ENCODING && !doc); }
  { char path[4096]; exr_document *doc=NULL; exr_navigation *nav=NULL; size_t n;
    snprintf(path,sizeof(path),"%s/kf8-guide-budget.azw3",argv[1]); OK(exr_document_open(path,&doc,&error));
    OK(exr_document_navigation(doc,&nav,&n,&error)); CHECK(n==10000); exr_document_free(doc); exr_navigation_free(nav,n);
    snprintf(path,sizeof(path),"%s/kf8-limit-guide.azw3",argv[1]); CHECK(exr_document_open(path,&doc,&error)==EXR_LIMIT && !doc);
  }
  printf("%u KF8 checks passed\n",checks); return 0;
}
