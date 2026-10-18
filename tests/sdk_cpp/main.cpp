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
  exr_glyph_image image{};
  if(exr_font_glyph_image(nullptr,0,0,20,&image,nullptr,&error)!=EXR_ARGUMENT || image.bitmap.pixels || image.scale) return 6;
  const char patterns[]=u8".aaaa1aaaa./\u00df=\ufb03,4,2";
  exr_hyphen_pattern_input dictionary{sizeof(dictionary),"de",patterns,sizeof(patterns)-1,1,1};
  exr_hyphenator *hyphenator=nullptr;exr_hyphenation *result=nullptr;
  if(exr_hyphenator_create_patterns_ex(&dictionary,1,0,EXR_HYPHEN_CASE_WORD,nullptr,&hyphenator,&error)!=EXR_OK) return 7;
  std::unique_ptr<exr_hyphenator,decltype(&exr_hyphenator_free)> owned_hyphenator(hyphenator,exr_hyphenator_free);
  if(exr_hyphenator_query(hyphenator,"de-DE","AAAAAAAA",8,nullptr,&result,&error)!=EXR_OK) return 8;
  std::unique_ptr<exr_hyphenation,decltype(&exr_hyphenation_free)> owned_result(result,exr_hyphenation_free);
  const auto *breaks=exr_hyphenation_breaks(result,&count);
  if(count!=1 || std::strcmp(breaks[0].before,"SS") || std::strcmp(breaks[0].after,"FFI")) return 9;
  const char compound[]= "efg1hijk/gg=h,3,2\n.abcd1efgg.\nNEXTLEVEL\n.ab1cd.\n.hi1jk.";
  dictionary={sizeof(dictionary),"und",compound,sizeof(compound)-1,1,1};
  if(exr_hyphenator_create_patterns(&dictionary,1,0,nullptr,&hyphenator,&error)!=EXR_OK) return 10;
  owned_hyphenator.reset(hyphenator);
  if(exr_hyphenator_query(hyphenator,"und","abcdefghijk",11,nullptr,&result,&error)!=EXR_OK) return 11;
  owned_result.reset(result);breaks=exr_hyphenation_breaks(result,&count);
  if(count!=4 || breaks[1].point!=4 || std::strcmp(breaks[2].before,"gg") || breaks[2].start!=6 || breaks[2].end!=8) return 12;
  std::printf("C++ consumer: %s ABI %u\n",exr_version(),unsigned(exr_abi_version())); return 0;
}
