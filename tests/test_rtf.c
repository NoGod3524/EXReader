/* SPDX-License-Identifier: GPL-3.0-only */
#include "exreader.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static exr_error error; static unsigned checks;
#define CHECK(x) do { checks++; if(!(x)) { fprintf(stderr,"line %d: %s (%d: %s)\n",__LINE__,#x,error.code,error.message); exit(1); } } while(0)
#define OK(x) CHECK((x)==EXR_OK)
static void rich(const char *dir) {
  const char *input="{\\rtf1\\ansi\\ansicpg1252\\uc1{\\colortbl;\\red18\\green52\\blue86;}{\\info ignored metadata}\\pard\\qc\\sb60 Normal {\\b bold} {\\i italic} {\\fs36\\cf1 color} normal {\\ul under}{\\strike strike}\\par\\pard\\li120\\fi60 Second\\line third}";
  exr_document *doc=NULL,*copy=NULL; exr_font *font=NULL; exr_layout *a=NULL,*b=NULL;
  exr_layout_config config=exr_layout_config_defaults(); exr_bitmap ba={0},bb={0};
  const exr_node *nodes; const exr_glyph *glyphs; char path[4096];
  size_t count,i,bold=0,italic=0,colored=0,under=0,strike=0,underlined=0,struck=0,pa,pb,paragraphs=0,breaks=0; void *zip=NULL; size_t size;
  OK(exr_document_open_memory(EXR_RTF,input,strlen(input),&doc,&error));
  CHECK(!strcmp(exr_document_text(doc,NULL),"Normal bold italic color normal understrike\nSecond\nthird"));
  nodes=exr_document_nodes(doc,&count);
  for(i=0;i<count;i++) {
    if(nodes[i].kind==EXR_NODE_PARAGRAPH) paragraphs++;
    if(nodes[i].kind==EXR_NODE_BREAK) breaks++;
    if(nodes[i].name && !strcmp(nodes[i].name,"http://www.w3.org/1999/xhtml|u")) under++;
    if(nodes[i].name && !strcmp(nodes[i].name,"http://www.w3.org/1999/xhtml|s")) strike++;
  }
  CHECK(paragraphs==2 && breaks==1 && under==1 && strike==1);
  snprintf(path,sizeof(path),"%s/fonts/primary.ttf",dir); OK(exr_font_open(path,&font,&error));
  config.page=(exr_layout_options){300,180,8,16,1.2f,4};
  OK(exr_layout_create_ex(doc,font,&config,&a,&error)); glyphs=exr_layout_glyphs(a,&count);
  for(i=0;i<count;i++) {
    if(glyphs[i].codepoint==' ') continue;
    if(glyphs[i].flags&EXR_GLYPH_UNDERLINE) underlined++;
    if(glyphs[i].flags&EXR_GLYPH_STRIKE) struck++;
    if(glyphs[i].flags&EXR_GLYPH_BOLD) bold++;
    if(glyphs[i].flags&EXR_GLYPH_ITALIC) italic++;
    if(glyphs[i].color==0x123456ff) { CHECK(glyphs[i].size==24); colored++; }
  }
  CHECK(bold==4 && italic==6 && colored==5 && underlined==5 && struck==6);
  OK(exr_document_export_epub(doc,NULL,&zip,&size,&error)); OK(exr_document_open_memory(EXR_EPUB,zip,size,&copy,&error)); exr_free(zip);
  CHECK(!strcmp(exr_document_text(doc,NULL),exr_document_text(copy,NULL)));
  OK(exr_layout_create_ex(copy,font,&config,&b,&error)); exr_layout_pages(a,&pa); exr_layout_pages(b,&pb); CHECK(pa==pb);
  for(i=0;i<pa;i++) {
    OK(exr_render_page(a,NULL,i,&ba,&error)); OK(exr_render_page(b,NULL,i,&bb,&error));
    CHECK(ba.stride==bb.stride && ba.height==bb.height && !memcmp(ba.pixels,bb.pixels,(size_t)ba.stride*ba.height));
    exr_bitmap_free(&ba); exr_bitmap_free(&bb);
  }
  exr_layout_free(a); exr_layout_free(b); exr_font_free(font); exr_document_free(doc); exr_document_free(copy);
}
static void picture_case(const char *dir,int binary,int jpeg) {
  char path[4096],prefix[256]; exr_document *source=NULL,*doc=NULL,*copy=NULL;
  void *png=NULL,*copied=NULL,*zip=NULL; size_t png_size,n,at=0,i,zip_size,count;
  unsigned char *rtf; const exr_resource *resources; const exr_node *nodes;
  exr_font *font=NULL; exr_layout *a=NULL,*b=NULL; exr_bitmap pa={0},pb={0};
  exr_layout_config config=exr_layout_config_defaults();
  snprintf(path,sizeof(path),"%s/%s",dir,jpeg ? "layout.epub" : "rich.fb2"); OK(exr_document_open(path,&source,&error));
  resources=exr_document_resources(source,&count); n=0;
  if(jpeg) { for(n=0;n<count;n++) if(!strcmp(resources[n].path,"sample.jpg")) break; CHECK(n<count); }
  OK(exr_document_resource(source,n,&png,&png_size,&error)); exr_document_free(source);
  rtf=malloc(png_size*4+1024); CHECK(rtf);
  if(binary) {
    int length=snprintf(prefix,sizeof(prefix),"{\\rtf1 A{\\pict\\%s\\picwgoal360\\pichgoal180\\bin%zu ",jpeg ? "jpegblip" : "pngblip",png_size);
    memcpy(rtf,prefix,(size_t)length); at=(size_t)length; memcpy(rtf+at,png,png_size); at+=png_size;
    memcpy(rtf+at,"}B}",3); at+=3;
  } else {
    char start[256],fallback[128];
    snprintf(start,sizeof(start),"{\\rtf1 A{\\*\\shppict{\\pict\\%s\\picwgoal360\\pichgoal180 ",jpeg ? "jpegblip" : "pngblip");
    snprintf(fallback,sizeof(fallback),"}}{\\nonshppict{\\pict\\%s ",jpeg ? "jpegblip" : "pngblip");
    memcpy(rtf,start,strlen(start)); at=strlen(start);
    for(i=0;i<png_size;i++) at+=(size_t)sprintf((char *)rtf+at,"%02x",((unsigned char *)png)[i]);
    memcpy(rtf+at,fallback,strlen(fallback)); at+=strlen(fallback);
    for(i=0;i<png_size;i++) at+=(size_t)sprintf((char *)rtf+at,"%02x",((unsigned char *)png)[i]);
    memcpy(rtf+at,"}}B}",4); at+=4;
  }
  OK(exr_document_open_memory(EXR_RTF,rtf,at,&doc,&error)); free(rtf);
  CHECK(!strcmp(exr_document_text(doc,NULL),"AB")); resources=exr_document_resources(doc,&count); CHECK(count==1);
  CHECK(!strcmp(resources[0].media_type,jpeg ? "image/jpeg" : "image/png"));
  OK(exr_document_resource(doc,0,&copied,&n,&error)); CHECK(n==png_size && !memcmp(png,copied,n)); exr_free(png); exr_free(copied);
  nodes=exr_document_nodes(doc,&count);
  for(i=0;i<count;i++) if(nodes[i].kind==EXR_NODE_IMAGE) break;
  CHECK(i<count && !strcmp(exr_node_attribute(&nodes[i],"width"),"24.0000") && !strcmp(exr_node_attribute(&nodes[i],"height"),"12.0000"));
  snprintf(path,sizeof(path),"%s/fonts/primary.ttf",dir); OK(exr_font_open(path,&font,&error));
  config.page=(exr_layout_options){200,160,8,16,1.2f,4}; OK(exr_layout_create_ex(doc,font,&config,&a,&error)); CHECK(exr_layout_image(a,0));
  OK(exr_document_export_epub(doc,NULL,&zip,&zip_size,&error)); OK(exr_document_open_memory(EXR_EPUB,zip,zip_size,&copy,&error)); exr_free(zip);
  OK(exr_layout_create_ex(copy,font,&config,&b,&error)); OK(exr_render_page(a,NULL,0,&pa,&error)); OK(exr_render_page(b,NULL,0,&pb,&error));
  CHECK(pa.stride==pb.stride && pa.height==pb.height && !memcmp(pa.pixels,pb.pixels,(size_t)pa.stride*pa.height));
  exr_bitmap_free(&pa); exr_bitmap_free(&pb); exr_layout_free(a); exr_layout_free(b); exr_font_free(font); exr_document_free(doc); exr_document_free(copy);
}
static void skipped(void) {
  const char *input="{\\rtf1 A{\\*\\unknown \\shppict Secret}B}";
  exr_document *doc=NULL;
  OK(exr_document_open_memory(EXR_RTF,input,strlen(input),&doc,&error));
  CHECK(!strcmp(exr_document_text(doc,NULL),"AB")); exr_document_free(doc);
}
static void links_fonts(const char *dir) {
  const char *input="{\\rtf1\\ansi\\ansicpg1252\\deff0{\\fonttbl{\\f0\\fnil SourceSerif;}{\\f1\\fswiss Alt\\u20013?;}}{\\info{\\title Test \\u20013? title}{\\author Hidden author}}A{\\*\\bkmkstart target}{\\*\\bkmkend target}{\\field{\\*\\fldinst HYPERLINK \"https://example.test/?a=1&b=2\"}{\\fldrslt \\f1 Web {\\b bold}}} {\\field{\\*\\fldinst HYPERLINK \\\\l \"target\"}{\\fldrslt Back}} {\\field{\\*\\fldinst DATE}{\\fldrslt Date result}}}";
  exr_document *doc=NULL,*copy=NULL; exr_font *font=NULL; exr_layout *a=NULL,*b=NULL;
  exr_bitmap pa={0},pb={0}; exr_layout_config config=exr_layout_config_defaults(); char path[4096];
  const exr_node *nodes; size_t count,i,links=0,internal=0,font0=0,font1=0,resource,target;
  void *zip=NULL; size_t size;
  OK(exr_document_open_memory(EXR_RTF,input,strlen(input),&doc,&error));
  CHECK(!strcmp(exr_document_title(doc),"Test 中 title"));
  CHECK(!strcmp(exr_document_text(doc,NULL),"AWeb bold Back Date result"));
  nodes=exr_document_nodes(doc,&count);
  for(i=0;i<count;i++) {
    const char *style=exr_node_attribute(&nodes[i],"style");
    if(style && strstr(style,"SourceSerif")) font0++;
    if(style && strstr(style,"Alt中")) font1++;
    if(nodes[i].kind==EXR_NODE_LINK) {
      const char *href=exr_node_attribute(&nodes[i],"href"); CHECK(href); links++;
      if(*href=='#') {
        internal++; OK(exr_document_resolve(doc,0,href,&resource,&target,&error));
        CHECK(target<count && !strcmp(exr_node_attribute(&nodes[target],"id"),"bookmark-target"));
      } else CHECK(!strcmp(href,"https://example.test/?a=1&b=2"));
    }
  }
  CHECK(links==3 && internal==1 && font0 && font1);
  snprintf(path,sizeof(path),"%s/fonts/primary.ttf",dir); OK(exr_font_open(path,&font,&error));
  config.page=(exr_layout_options){300,180,8,16,1.2f,4}; OK(exr_layout_create_ex(doc,font,&config,&a,&error));
  OK(exr_document_export_epub(doc,NULL,&zip,&size,&error)); OK(exr_document_open_memory(EXR_EPUB,zip,size,&copy,&error)); exr_free(zip);
  CHECK(!strcmp(exr_document_title(copy),exr_document_title(doc)));
  OK(exr_layout_create_ex(copy,font,&config,&b,&error)); OK(exr_render_page(a,NULL,0,&pa,&error)); OK(exr_render_page(b,NULL,0,&pb,&error));
  CHECK(pa.stride==pb.stride && pa.height==pb.height && !memcmp(pa.pixels,pb.pixels,(size_t)pa.stride*pa.height));
  exr_bitmap_free(&pa); exr_bitmap_free(&pb); exr_layout_free(a); exr_layout_free(b); exr_font_free(font); exr_document_free(doc); exr_document_free(copy);
}
static void metadata_edges(void) {
  const char *cases[]={
    "{\\rtf1 A{\\*\\unknown \\field\\fldinst HYPERLINK \"https://bad.test\"\\fldrslt Secret}B}",
    "{\\rtf1 A{\\*\\'41\\fonttbl Secret}B}",
    "{\\rtf1{\\fonttbl{\\f0;}}AB}"};
  size_t i;
  for(i=0;i<sizeof(cases)/sizeof(*cases);i++) {
    exr_document *doc=NULL;
    OK(exr_document_open_memory(EXR_RTF,cases[i],strlen(cases[i]),&doc,&error));
    CHECK(!strcmp(exr_document_text(doc,NULL),"AB")); exr_document_free(doc);
  }
}
static void invalid(const char *rtf) {
  exr_document *doc=NULL; CHECK(exr_document_open_memory(EXR_RTF,rtf,strlen(rtf),&doc,&error)==EXR_FORMAT); CHECK(!doc);
}
int main(int argc,char **argv) {
  CHECK(argc==2); rich(argv[1]); skipped(); metadata_edges(); links_fonts(argv[1]); picture_case(argv[1],0,0); picture_case(argv[1],1,0); picture_case(argv[1],0,1); picture_case(argv[1],1,1);
  invalid("{\\rtf1{\\colortbl;\\red256\\green0\\blue0;}\\cf1 bad}");
  invalid("{\\rtf1\\cf1 missing color}"); invalid("{\\rtf1\\fs0 invalid size}");
  invalid("{\\rtf1{\\pict\\pngblip 89504e4}}");
  invalid("{\\rtf1{\\pict\\pngblip 0001020304050607}}");
  invalid("{\\rtf1{\\pict\\pngblip ZZ}}");
  printf("%u rich RTF checks passed\n",checks); return 0;
}
