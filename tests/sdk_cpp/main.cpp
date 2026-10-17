/* SPDX-License-Identifier: GPL-3.0-only */
#include <exreader.h>
#include <cstring>
#include <memory>
#include <cstdio>
int main() {
  static_assert(EXR_ABI_VERSION==1,"Expected documented ABI epoch");
  if(exr_abi_version()!=EXR_ABI_VERSION || std::strcmp(exr_version(),EXR_VERSION)) return 1;
  exr_error error{}; exr_document *raw=nullptr;
  const char text[]=u8"C++ host";
  if(exr_document_open_memory(EXR_TXT,text,sizeof(text)-1,&raw,&error)!=EXR_OK) return 2;
  std::unique_ptr<exr_document,decltype(&exr_document_free)> document(raw,exr_document_free);
  std::size_t size=0; const char *view=exr_document_text(document.get(),&size);
  if(size!=sizeof(text)-1 || std::memcmp(view,text,size)) return 3;
  static_assert(sizeof(exr_font_color_layer)==8,"Stable C color-layer record");
  std::size_t palettes=1,entries=1,count=1; exr_font_color_layer *layers=nullptr;
  if(exr_font_color_palettes(nullptr,0,&palettes,&entries,&error)!=EXR_ARGUMENT || palettes || entries) return 4;
  if(exr_font_color_layers(nullptr,0,0,0,0,&layers,&count,nullptr,&error)!=EXR_ARGUMENT || layers || count) return 5;
  std::printf("C++ consumer: %s ABI %u\n",exr_version(),unsigned(exr_abi_version())); return 0;
}
