/* SPDX-License-Identifier: MIT */
/* No HWND: check the presentation ZIP and the SDK's bounded first page. */
#include "shell_epub.cpp"
#include <cstdio>
int main(int argc,char **argv) {
  if(argc!=4) return 2;
  FILE *f=std::fopen(argv[2],"rb");if(!f) return 2;
  std::fseek(f,0,SEEK_END);long n=std::ftell(f);std::rewind(f);
  auto *b=new std::vector<unsigned char>((size_t)n);
  if(std::fread(b->data(),1,b->size(),f)!=b->size()) return 2;
  std::fclose(f);
  exr_source source={b->size(),read_memory,release_memory,b,{}};
  if(!shell_epub_source(&source)) return 3;
  f=std::fopen(argv[3],"wb");if(!f) return 2;
  auto &bytes=*(std::vector<unsigned char> *)source.context;
  std::fwrite(bytes.data(),1,bytes.size(),f);std::fclose(f);
  exr_error e={};exr_publication *p=nullptr;
  exr_status s=exr_publication_open_source(&source,&p,&e);
  std::printf("open=%d %s\n",s,e.message);
  if(s!=EXR_OK) {source.release(source.context);return 4;}
  exr_font *font=nullptr;s=exr_font_open(argv[1],&font,&e);
  if(s!=EXR_OK) return 5;
  const exr_node_input nodes[]={
    {EXR_NODE_DOCUMENT,SIZE_MAX,nullptr,nullptr,nullptr,0},
    {EXR_NODE_CHAPTER,0,nullptr,nullptr,nullptr,0},
    {EXR_NODE_PARAGRAPH,1,"p",nullptr,nullptr,0},
    {EXR_NODE_TEXT,2,nullptr,"　　正文文字。",nullptr,0}};
  const exr_chapter_input chapter={"c","c.xhtml",1,1};
  const exr_document_input input={"Resident CJK",nodes,4,&chapter,1,nullptr,0};
  exr_document *resident=nullptr;
  if(exr_document_create(&input,&resident,&e)!=EXR_OK || !shell_style_document(&resident)) return 7;
  size_t length=0;const char *text=exr_document_text(resident,&length);
  if(std::strcmp(text,"　　正文文字。")) return 8;
  size_t nc=0;const auto *ns=exr_document_nodes(resident,&nc);
  const char *classes=exr_node_attribute(ns+2,"class");
  if(nc!=4 || !classes || !std::strstr(classes,"exr-shell-cjk") || !std::strstr(classes,"exr-shell-indent-2")) return 9;
  auto resident_config=exr_layout_config_defaults();resident_config.page.font_size=18;
  resident_config.user_css=".exr-shell-cjk{line-height:32px;text-indent:0;margin-top:0;margin-bottom:9px}";
  exr_layout *resident_layout=nullptr;
  if(exr_layout_create_ex(resident,font,&resident_config,&resident_layout,&e)!=EXR_OK) return 10;
  size_t lc=0;const auto *ls=exr_layout_lines(resident_layout,&lc);
  if(lc!=1 || ls[0].height!=32) return 11;
  std::printf("resident CJK: text/nodes retained, leading=32, authored-prefix class retained\n");
  exr_layout_free(resident_layout);exr_document_free(resident);
  size_t count=0;const exr_part *parts=exr_publication_parts(p,&count);
  for(size_t i=0;i<count && i<3;i++) if(parts[i].in_reading_order) {
    exr_pager *pager=nullptr;auto config=exr_layout_config_defaults();
    s=exr_publication_pager_create(p,i,font,&config,nullptr,&pager,&e);
    std::printf("part=%zu create=%d %s\n",i,s,e.message);
    const exr_layout *layout=nullptr;
    if(s==EXR_OK) s=exr_pager_get(pager,0,&layout,&e);
    std::printf("part=%zu get=%d %s\n",i,s,e.message);
    exr_pager_free(pager);if(s!=EXR_OK) return 6;
  }
  exr_publication_free(p);exr_font_free(font);return 0;
}
