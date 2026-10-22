/* SPDX-License-Identifier: MIT */
#include <exr_ocr.h>
#include <tesseract/baseapi.h>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <iostream>
#include <string>
#include <vector>
static int called=0,after=0;
static int cancelled(void*) { return ++called>=after; }
static bool empty(const exr_ocr_result &r) { return !r.text&&!r.items&&!r.text_bytes&&!r.count; }
int main(int argc,char **argv) {
  if(argc!=7) return 2;
  std::ifstream f(argv[3],std::ios::binary); std::string magic; unsigned w,h,max;
  f>>magic>>w>>h>>max; f.get();
  if(magic!="P5"||!w||!h||w>5000||h>5000||max!=255) return 3;
  std::vector<unsigned char> pixels(static_cast<size_t>(w)*h);
  f.read(reinterpret_cast<char*>(pixels.data()),pixels.size()); if(!f) return 4;
  exr_ocr *ctx=nullptr;exr_error error{};
  if(exr_ocr_open(argv[1],argv[2],&ctx,&error)!=EXR_OK||!ctx) return 5;
  exr_bitmap bitmap{w,h,w,pixels.data(),1};exr_ocr_options options{};exr_ocr_options_default(&options);
  options.clockwise=std::strtoul(argv[5],nullptr,10);
  /* Source page origin=(13,29), y up; 300 dpi pixels -> 72 dpi page units. */
  options.pixel_to_page[0]=0.24;options.pixel_to_page[3]=-0.24;
  options.pixel_to_page[4]=13;options.pixel_to_page[5]=29+h*0.24;
  exr_ocr_result result{};
  exr_status status=exr_ocr_recognize(ctx,&bitmap,&options,&result,&error);
  if(status!=EXR_OK) { exr_ocr_close(ctx); return 10+status; }
  std::ofstream out(argv[4]);out.precision(17);
  out<<"backend\t"<<tesseract::TessBaseAPI::Version()<<"\n";
  for(size_t i=0;i<result.count;i++) {
    const auto &r=result.items[i]; out<<r.level<<'\t'<<r.confidence;
    for(double n:r.pixel_quad) out<<'\t'<<n;
    for(double n:r.page_quad) out<<'\t'<<n;
    out<<'\t'; const char *hex="0123456789abcdef";
    for(size_t j=0;j<r.text_bytes;j++) { unsigned c=static_cast<unsigned char>(result.text[r.text_offset+j]);out<<hex[c>>4]<<hex[c&15]; }
    out<<'\n';
  }
  exr_ocr_result_free(&result);
  if(std::strcmp(argv[6],"contracts")==0) {
    auto verify=[&](exr_status expected) {
      exr_status got=exr_ocr_recognize(ctx,&bitmap,&options,&result,&error);
      bool ok=got==expected&&empty(result);exr_ocr_result_free(&result); return ok;
    };
    auto original=options;
    options.max_pixels=1; if(!verify(EXR_LIMIT)) return 30;options=original;
    options.max_output_bytes=1; if(!verify(EXR_LIMIT)) return 31;options=original;
    options.max_items=1; if(!verify(EXR_LIMIT)) return 32;options=original;
    options.clockwise=45;if(!verify(EXR_ARGUMENT)) return 33;options=original;
    options.pixel_to_page[0]=0;if(!verify(EXR_ARGUMENT)) return 34;options=original;
    called=0;after=1;options.control.cancelled=cancelled;if(!verify(EXR_CANCELLED)) return 35;options=original;
    called=0;after=h+2;options.control.cancelled=cancelled;if(!verify(EXR_CANCELLED)) return 36;options=original;
    options.timeout_ms=1;if(!verify(EXR_LIMIT)) return 37;options=original;
    bitmap.stride=w-1;if(!verify(EXR_ARGUMENT)) return 38;bitmap.stride=w;
    status=exr_ocr_recognize(ctx,&bitmap,&options,&result,&error);
    if(status!=EXR_OK||!result.count) return 39;
    exr_ocr_result_free(&result);
    /* Explicit RGBA alpha normalization, equivalent to the gray input. */
    std::vector<unsigned char> rgba(pixels.size()*4);
    for(size_t i=0;i<pixels.size();i++) { rgba[4*i]=rgba[4*i+1]=rgba[4*i+2]=pixels[i];rgba[4*i+3]=255; }
    bitmap.pixels=rgba.data();bitmap.stride=w*4;bitmap.channels=4;
    status=exr_ocr_recognize(ctx,&bitmap,&options,&result,&error);
    if(status!=EXR_OK||!result.count) return 40;
    exr_ocr_result_free(&result);
    out<<"contracts\t11\n";
  }
  exr_ocr_close(ctx);return out?0:50;
}
