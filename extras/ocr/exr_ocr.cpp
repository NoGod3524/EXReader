/* SPDX-License-Identifier: MIT */
#include "exr_ocr.h"
#include <tesseract/baseapi.h>
#include <tesseract/resultiterator.h>
#include <tesseract/ocrclass.h>
#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdlib>
#include <cstring>
#include <limits>
#include <memory>
#include <string>
#include <vector>
struct exr_ocr { tesseract::TessBaseAPI api; };
static exr_status fail(exr_error *e, exr_status s, const char *msg) {
  if(e) { e->code=s; std::strncpy(e->message,msg,255); e->message[255]=0; } return s;
}
extern "C" void exr_ocr_options_default(exr_ocr_options *o) {
  if(!o) return; *o={}; o->max_pixels=16000000; o->max_output_bytes=4*1024*1024;
  o->max_items=100000; o->timeout_ms=30000; o->dpi=300;
  o->pixel_to_page[0]=o->pixel_to_page[3]=1;
}
extern "C" exr_status exr_ocr_open(const char *path,const char *lang,exr_ocr **out,exr_error *e) {
  if(out) *out=nullptr;
  if(!out || !path || !*path || !lang || !*lang) return fail(e,EXR_ARGUMENT,"Missing OCR model path/language");
  try {
    auto p=std::make_unique<exr_ocr>();
    if(p->api.Init(path,lang,tesseract::OEM_LSTM_ONLY)) return fail(e,EXR_IO,"OCR model initialization failed");
    p->api.SetPageSegMode(tesseract::PSM_AUTO); *out=p.release(); return fail(e,EXR_OK,"");
  } catch(...) { return fail(e,EXR_MEMORY,"OCR model allocation failed"); }
}
extern "C" void exr_ocr_close(exr_ocr *p) { delete p; }
extern "C" void exr_ocr_result_free(exr_ocr_result *r) {
  if(r) { std::free(r->text); std::free(r->items); *r={}; }
}
struct Work {
  const exr_ocr_options &o;
  std::chrono::steady_clock::time_point end;
  bool cancelled=false, expired=false;
  bool stop() {
    if(o.control.cancelled && o.control.cancelled(o.control.context)) cancelled=true;
    if(std::chrono::steady_clock::now()>=end) expired=true;
    return cancelled || expired;
  }
};
static bool cancel(void *p,int) { return static_cast<Work*>(p)->stop(); }
static void map(double x,double y,unsigned rot,double w,double h,const double m[6],double *pixel,double *page) {
  double a=x,b=y;
  if(rot==90) { a=y; b=h-x; } else if(rot==180) { a=w-x; b=h-y; }
  else if(rot==270) { a=w-y; b=x; }
  pixel[0]=a; pixel[1]=b; page[0]=m[0]*a+m[2]*b+m[4]; page[1]=m[1]*a+m[3]*b+m[5];
}
extern "C" exr_status exr_ocr_recognize(exr_ocr *p,const exr_bitmap *b,const exr_ocr_options *o,
  exr_ocr_result *out,exr_error *e) {
  if(out) *out={};
  if(!p || !b || !o || !out || !b->pixels || !b->width || !b->height ||
     (b->channels!=1 && b->channels!=4) || b->width>INT32_MAX || b->height>INT32_MAX ||
     b->width>SIZE_MAX/b->channels || b->stride<static_cast<size_t>(b->width)*b->channels ||
     b->height>SIZE_MAX/b->stride || o->clockwise>270 || o->clockwise%90 || !o->timeout_ms || o->timeout_ms>INT32_MAX ||
     o->dpi<70 || o->dpi>2400 || !o->max_pixels || !o->max_items || !o->max_output_bytes)
    return fail(e,EXR_ARGUMENT,"Invalid OCR bitmap/options");
  for(double v:o->pixel_to_page) if(!std::isfinite(v) || std::fabs(v)>1e7) return fail(e,EXR_ARGUMENT,"Invalid OCR transform");
  double determinant=o->pixel_to_page[0]*o->pixel_to_page[3]-o->pixel_to_page[1]*o->pixel_to_page[2];
  if(!std::isfinite(determinant) || determinant==0) return fail(e,EXR_ARGUMENT,"Singular OCR transform");
  if(b->height>o->max_pixels/b->width) return fail(e,EXR_LIMIT,"OCR pixel budget exceeded");
  Work work{*o,std::chrono::steady_clock::now()+std::chrono::milliseconds(o->timeout_ms)};
  auto stopped=[&]() { return fail(e,work.cancelled?EXR_CANCELLED:EXR_LIMIT,"OCR cancelled or deadline exceeded"); };
  if(work.stop()) return stopped();
  /* ponytail: one gray copy supplies orientation and alpha normalization; no image library dependency. */
  try {
    unsigned w=o->clockwise%180?b->height:b->width,h=o->clockwise%180?b->width:b->height;
    std::vector<unsigned char> gray(static_cast<size_t>(w)*h);
    for(unsigned y=0;y<b->height;y++) {
      if(work.stop()) return stopped();
      for(unsigned x=0;x<b->width;x++) {
        auto q=b->pixels+static_cast<size_t>(y)*b->stride+static_cast<size_t>(x)*b->channels;
        unsigned value=q[0];
        if(b->channels==4) { value=(77u*q[0]+150u*q[1]+29u*q[2]+128)/256; value=(value*q[3]+255u*(255-q[3])+127)/255; }
        unsigned dx=x,dy=y;
        if(o->clockwise==90) { dx=b->height-1-y;dy=x; }
        else if(o->clockwise==180) { dx=b->width-1-x;dy=b->height-1-y; }
        else if(o->clockwise==270) { dx=y;dy=b->width-1-x; }
        gray[static_cast<size_t>(dy)*w+dx]=static_cast<unsigned char>(value);
      }
    }
    p->api.SetImage(gray.data(),w,h,1,w); p->api.SetSourceResolution(o->dpi);
    struct Clear { tesseract::TessBaseAPI &api; ~Clear(){api.Clear();} } clear{p->api};
    tesseract::ETEXT_DESC monitor; monitor.cancel=cancel; monitor.cancel_this=&work;
    monitor.set_deadline_msecs(o->timeout_ms);
    int rc=p->api.Recognize(&monitor);
    if(work.stop()) return stopped();
    if(rc) return fail(e,EXR_FORMAT,"OCR recognition failed");
    std::string text; std::vector<exr_ocr_item> items;
    const tesseract::PageIteratorLevel levels[]={tesseract::RIL_TEXTLINE,tesseract::RIL_WORD,tesseract::RIL_SYMBOL};
    for(unsigned level=0;level<3;level++) {
      std::unique_ptr<tesseract::ResultIterator> it(p->api.GetIterator());
      if(!it) continue;
      do {
        if(work.stop()) return stopped();
        std::unique_ptr<char[]> s(it->GetUTF8Text(levels[level]));
        if(!s || !*s) continue;
        size_t length=0;
        while(s[length] && length<o->max_output_bytes) length++;
        if(length==o->max_output_bytes || items.size()>=o->max_items ||
           items.size()>=SIZE_MAX/sizeof(exr_ocr_item)-1 ||
           (items.size()+1)*sizeof(exr_ocr_item)>o->max_output_bytes ||
           text.size()>=o->max_output_bytes-(items.size()+1)*sizeof(exr_ocr_item) ||
           length>=o->max_output_bytes-(items.size()+1)*sizeof(exr_ocr_item)-text.size())
          return fail(e,EXR_LIMIT,"OCR output budget exceeded");
        int l,t,r,bt; if(!it->BoundingBox(levels[level],&l,&t,&r,&bt)) continue;
        exr_ocr_item item{}; item.level=level+1; item.confidence=it->Confidence(levels[level]);
        item.text_offset=text.size(); item.text_bytes=length;
        const double corners[]={double(l),double(t),double(r),double(t),double(r),double(bt),double(l),double(bt)};
        for(unsigned j=0;j<4;j++) map(corners[2*j],corners[2*j+1],o->clockwise,b->width,b->height,
          o->pixel_to_page,item.pixel_quad+2*j,item.page_quad+2*j);
        text.append(s.get(),length); items.push_back(item);
      } while(it->Next(levels[level]));
    }
    if(work.stop()) return stopped();
    std::unique_ptr<char,decltype(&std::free)> bytes(static_cast<char*>(std::malloc(text.size()+1)),&std::free);
    std::unique_ptr<exr_ocr_item,decltype(&std::free)> records(nullptr,&std::free);
    if(!items.empty()) records.reset(static_cast<exr_ocr_item*>(std::malloc(items.size()*sizeof(exr_ocr_item))));
    if(!bytes || (!items.empty()&&!records)) return fail(e,EXR_MEMORY,"OCR result allocation failed");
    std::memcpy(bytes.get(),text.c_str(),text.size()+1);
    if(!items.empty()) std::memcpy(records.get(),items.data(),items.size()*sizeof(exr_ocr_item));
    out->text=bytes.release();out->text_bytes=text.size();out->items=records.release();out->count=items.size();
    return fail(e,EXR_OK,"");
  } catch(...) { return fail(e,EXR_MEMORY,"OCR allocation failed"); }
}
