/* SPDX-License-Identifier: MIT */
#include "exreader.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static exr_error error; static unsigned checks;
#define CHECK(x) do { checks++; if(!(x)) { fprintf(stderr,"line %d: %s (%d: %s)\n",__LINE__,#x,error.code,error.message); exit(1); } } while(0)
#define OK(x) CHECK((x)==EXR_OK)
static exr_document *open(const char *source) { exr_document *d=NULL; OK(exr_document_open_memory(EXR_RTF,source,strlen(source),&d,&error)); return d; }
static void roundtrip(exr_document *doc,const char *dir) {
  exr_document *copy=NULL; void *zip=NULL; size_t size,pa,pb,i; exr_font *font=NULL; exr_layout *a=NULL,*b=NULL; exr_bitmap ba,bb; char path[4096];
  exr_layout_config config=exr_layout_config_defaults(); config.page=(exr_layout_options){220,140,4,14,1.2f,2};
  snprintf(path,sizeof(path),"%s/fonts/primary.ttf",dir); OK(exr_font_open(path,&font,&error));
  OK(exr_document_export_epub(doc,NULL,&zip,&size,&error)); OK(exr_document_open_memory(EXR_EPUB,zip,size,&copy,&error)); exr_free(zip);
  CHECK(!strcmp(exr_document_text(doc,NULL),exr_document_text(copy,NULL)));
  OK(exr_layout_create_ex(doc,font,&config,&a,&error)); OK(exr_layout_create_ex(copy,font,&config,&b,&error)); exr_layout_pages(a,&pa); exr_layout_pages(b,&pb); CHECK(pa==pb && pa);
  for(i=0;i<pa;i++) { OK(exr_render_page(a,NULL,i,&ba,&error)); OK(exr_render_page(b,NULL,i,&bb,&error)); CHECK(ba.stride==bb.stride && ba.height==bb.height && !memcmp(ba.pixels,bb.pixels,(size_t)ba.stride*ba.height)); exr_bitmap_free(&ba); exr_bitmap_free(&bb); }
  exr_layout_free(a); exr_layout_free(b); exr_font_free(font); exr_document_free(copy);
}
int main(int argc,char **argv) {
  const char source[]="{\\rtf1 Body{\\super\\chftn}{\\footnote\\pard\\plain\\chftn Foot {\\b bold}\\par More foot.} after.\\par Second{\\footnote\\ftnalt\\pard\\chftn Endnote.} done.\\par\\trowd\\cellx1500\\cellx3000\\intbl Cell{\\footnote\\pard\\chftn Cell note.} tail\\cell Other\\cell\\row\\pard Last body.}";
  const char *bad[]={"{\\rtf1 A{\\footnote Outer{\\footnote Inner}}}","{\\rtf1 A{\\footnote\\trowd X\\cell\\row}}","{\\rtf1 A\\chftn}","{\\rtf1 A\\chftn\\chftn{\\footnote Text}}"};
  exr_document *d; const exr_node *nodes; const char *text; size_t count,i,notes=0,ends=0,refs=0,backs=0,target,resource,cells=0;
  CHECK(argc==2); d=open(source); text=exr_document_text(d,NULL);
  CHECK(strstr(text,"Body1 after.") && strstr(text,"Second2 done.") && strstr(text,"Cell3 tail"));
  CHECK(strstr(text,"Last body.") && strstr(text,"Foot bold") && strstr(text,"Cell note."));
  CHECK(strstr(text,"Last body.")<strstr(text,"Foot bold") && strstr(text,"Last body.")<strstr(text,"Cell note."));
  nodes=exr_document_nodes(d,&count);
  for(i=0;i<count;i++) {
    const char *role=exr_node_attribute(&nodes[i],"role");
    if(nodes[i].kind==EXR_NODE_NOTE) { notes++; CHECK(role); if(!strcmp(role,"doc-endnote")) ends++; }
    if(nodes[i].kind==EXR_NODE_CELL) cells++;
    if(role && (!strcmp(role,"doc-noteref") || !strcmp(role,"doc-backlink"))) {
      if(!strcmp(role,"doc-noteref")) refs++; else backs++;
      OK(exr_document_resolve(d,0,exr_node_attribute(&nodes[i],"href"),&resource,&target,&error)); CHECK(target<count);
    }
    if(nodes[i].parent!=SIZE_MAX) CHECK(nodes[i].parent<i);
  }
  CHECK(notes==3 && ends==1 && refs==3 && backs==3 && cells==2); roundtrip(d,argv[1]); exr_document_free(d);
  for(i=0;i<sizeof(bad)/sizeof(*bad);i++) CHECK(exr_document_open_memory(EXR_RTF,bad[i],strlen(bad[i]),&d,&error)==EXR_FORMAT && !d);
  d=open("{\\rtf1{\\*\\unknown{\\footnote Hidden}}Visible}"); CHECK(!strcmp(exr_document_text(d,NULL),"Visible")); exr_document_free(d);
  /* Images inside a detached note must remain in the note, not its parent cell. */
  { char path[4096],*source_image; exr_document *fb2=NULL; void *png=NULL; size_t size,at,k,image_node=SIZE_MAX,note_node=SIZE_MAX;
    snprintf(path,sizeof(path),"%s/rich.fb2",argv[1]); OK(exr_document_open(path,&fb2,&error)); OK(exr_document_resource(fb2,0,&png,&size,&error)); exr_document_free(fb2);
    source_image=malloc(size*2+512); CHECK(source_image); at=(size_t)sprintf(source_image,"{\\rtf1\\trowd\\cellx2000 Cell{\\footnote\\chftn {\\pict\\pngblip\\picwgoal360\\pichgoal180 ");
    for(k=0;k<size;k++) at+=(size_t)sprintf(source_image+at,"%02x",((unsigned char *)png)[k]);
    sprintf(source_image+at,"}} tail\\cell\\row}"); exr_free(png); d=open(source_image); free(source_image);
    nodes=exr_document_nodes(d,&count); for(k=0;k<count;k++) { if(nodes[k].kind==EXR_NODE_IMAGE) image_node=k; if(nodes[k].kind==EXR_NODE_NOTE) note_node=k; }
    CHECK(image_node<count && note_node<count); for(k=image_node;k!=SIZE_MAX && k!=note_node;k=nodes[k].parent) { } CHECK(k==note_node);
    roundtrip(d,argv[1]); exr_document_free(d);
  }
  { const char group[]="{\\footnote X}"; size_t at=0,k; char *many=malloc(16*10001+32); CHECK(many);
    at=(size_t)sprintf(many,"{\\rtf1 "); for(k=0;k<10001;k++) { memcpy(many+at,group,sizeof(group)-1); at+=sizeof(group)-1; } many[at++]='}'; many[at]=0;
    CHECK(exr_document_open_memory(EXR_RTF,many,at,&d,&error)==EXR_LIMIT && !d); free(many);
  }
  printf("%u RTF note checks passed\n",checks); return 0;
}
