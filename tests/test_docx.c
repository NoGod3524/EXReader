/* SPDX-License-Identifier: GPL-3.0-only */
#include "exreader.h"
#include <miniz.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define W "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
#define R "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
#define REL "http://schemas.openxmlformats.org/package/2006/relationships"
static exr_error error; static unsigned checks;
#define CHECK(x) do { checks++; if(!(x)) { fprintf(stderr,"line %d: %s (%d: %s)\n",__LINE__,#x,error.code,error.message); exit(1); } } while(0)
#define OK(x) CHECK((x)==EXR_OK)
static void rich(const char *dir) {
  char path[4096]; exr_document *doc=NULL,*copy=NULL; exr_font *font=NULL; exr_layout *a=NULL,*b=NULL;
  exr_layout_config config=exr_layout_config_defaults(); exr_bitmap ba={0},bb={0};
  const exr_node *nodes; const exr_resource *resources; const exr_glyph *glyphs;
  size_t count,i,resource,target,images=0,tables=0,rowspan=0,colspan=0,heads=0,bold=0,italic=0,pa,pb;
  void *zip=NULL,*image=NULL; size_t size,n; const char *text;
  snprintf(path,sizeof(path),"%s/rich.docx",dir); OK(exr_document_open(path,&doc,&error));
  text=exr_document_text(doc,NULL); CHECK(strstr(text,"Normal Bold Styled"));
  CHECK(strstr(text,"Inserted Result") && strstr(text,"Fallback"));
  CHECK(!strstr(text,"Deleted") && !strstr(text,"Instruction") && !strstr(text,"Should not appear"));
  resources=exr_document_resources(doc,&count); CHECK(count==1);
  CHECK(!strcmp(resources[0].media_type,"image/png"));
  CHECK(!strcmp(resources[0].path,"Content/images/图#%?.png"));
  OK(exr_document_resource(doc,0,&image,&n,&error)); CHECK(n>60 && !memcmp(image,"\x89PNG",4)); exr_free(image);
  nodes=exr_document_nodes(doc,&count);
  for(i=0;i<count;i++) {
    if(nodes[i].kind==EXR_NODE_IMAGE) {
      images++; CHECK(!strcmp(exr_node_attribute(&nodes[i],"width"),"24.0000")); CHECK(!strcmp(exr_node_attribute(&nodes[i],"height"),"12.0000"));
      OK(exr_document_resolve(doc,0,exr_node_attribute(&nodes[i],"src"),&resource,&target,&error)); CHECK(resource==0);
    }
    if(nodes[i].kind==EXR_NODE_TABLE) tables++;
    if(nodes[i].kind==EXR_NODE_CELL) {
      if(exr_node_attribute(&nodes[i],"rowspan")) { CHECK(!strcmp(exr_node_attribute(&nodes[i],"rowspan"),"2")); rowspan++; }
      if(exr_node_attribute(&nodes[i],"colspan")) { CHECK(!strcmp(exr_node_attribute(&nodes[i],"colspan"),"2")); colspan++; }
    }
    if(nodes[i].kind==EXR_NODE_HEADING) heads++;
    if(nodes[i].kind==EXR_NODE_LINK) {
      const char *href=exr_node_attribute(&nodes[i],"href"); CHECK(href);
      if(*href=='#') { OK(exr_document_resolve(doc,0,href,&resource,&target,&error)); CHECK(target<count); }
      else CHECK(!strcmp(href,"https://example.test/?a=1&b=2"));
    }
  }
  CHECK(images==1 && tables==1 && rowspan==1 && colspan==1 && heads==1);
  snprintf(path,sizeof(path),"%s/fonts/primary.ttf",dir); OK(exr_font_open(path,&font,&error));
  config.page=(exr_layout_options){300,240,8,16,1.2f,4};
  OK(exr_layout_create_ex(doc,font,&config,&a,&error));
  glyphs=exr_layout_glyphs(a,&count);
  for(i=0;i<count;i++) { if(glyphs[i].flags&EXR_GLYPH_BOLD) bold++; if(glyphs[i].flags&EXR_GLYPH_ITALIC) italic++; }
  CHECK(bold>=11 && italic>=6); CHECK(exr_layout_image(a,0));
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
static void package(const char *body,const char *rels,const char *styles,int valid) {
  mz_zip_archive writer={0}; void *bytes=NULL; size_t size; exr_document *doc=NULL; char xml[8192]; exr_status status;
  CHECK(mz_zip_writer_init_heap(&writer,0,0));
  snprintf(xml,sizeof(xml),"<w:document xmlns:w='" W "' xmlns:r='" R "'><w:body>%s</w:body></w:document>",body);
  CHECK(mz_zip_writer_add_mem(&writer,"word/document.xml",xml,strlen(xml),0));
  if(rels) CHECK(mz_zip_writer_add_mem(&writer,"word/_rels/document.xml.rels",rels,strlen(rels),0));
  if(styles) CHECK(mz_zip_writer_add_mem(&writer,"word/styles.xml",styles,strlen(styles),0));
  CHECK(mz_zip_writer_finalize_heap_archive(&writer,&bytes,&size)); mz_zip_writer_end(&writer);
  status=exr_document_open_memory(EXR_DOCX,bytes,size,&doc,&error); mz_free(bytes);
  if(valid) { CHECK(status==EXR_OK); exr_document_free(doc); }
  else CHECK(status==EXR_FORMAT && !doc);
}
int main(int argc,char **argv) {
  const char *image="<w:p><w:r><w:drawing xmlns:a='http://schemas.openxmlformats.org/drawingml/2006/main'><a:blip r:embed='x'/></w:drawing></w:r></w:p>";
  CHECK(argc==2); rich(argv[1]);
  package("<w:p><w:r><w:t>Simple</w:t></w:r></w:p>",NULL,NULL,1);
  package(image,NULL,NULL,0);
  package(image,"<Relationships xmlns='" REL "'><Relationship Id='x' Type='" R "/image' Target='../../../outside.png'/></Relationships>",NULL,0);
  package(image,"<Relationships xmlns='" REL "'><Relationship Id='x' Type='" R "/image' Target='missing.png'/></Relationships>",NULL,0);
  package(image,"<Relationships xmlns='" REL "'><Relationship Id='x' Type='" R "/image' Target='https://example.test/pic.png' TargetMode='External'/></Relationships>",NULL,1);
  package("<w:p/>","<Relationships xmlns='urn:wrong'/>",NULL,0);
  package("<w:p/>","<Relationships xmlns='" REL "'><Relationship Id='x' Type='" R "/image' Target='a.png'/><Relationship Id='x' Type='" R "/image' Target='b.png'/></Relationships>",NULL,0);
  package("<w:tbl><w:tr><w:tc><w:tcPr><w:vMerge/></w:tcPr><w:p/></w:tc></w:tr></w:tbl>",NULL,NULL,0);
  package("<w:p><w:pPr><w:pStyle w:val='Cycle'/></w:pPr><w:r><w:t>Style cycle</w:t></w:r></w:p>",
    "<Relationships xmlns='" REL "'><Relationship Id='s' Type='" R "/styles' Target='styles.xml'/></Relationships>",
    "<w:styles xmlns:w='" W "'><w:style w:styleId='Cycle'><w:basedOn w:val='Cycle'/></w:style></w:styles>",0);
  package("<w:tbl><w:tr><w:trPr><w:gridBefore w:val='1'/><w:gridAfter w:val='1'/></w:trPr><w:tc><w:p><w:r><w:t>Offset cell</w:t></w:r></w:p></w:tc></w:tr></w:tbl>",NULL,NULL,1);
  package("<w:tbl><w:tr><w:trPr><w:gridBefore w:val='257'/></w:trPr><w:tc><w:p/></w:tc></w:tr></w:tbl>",NULL,NULL,0);
  printf("%u rich DOCX checks passed\n",checks); return 0;
}
