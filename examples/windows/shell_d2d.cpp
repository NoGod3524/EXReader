/* SPDX-License-Identifier: MIT */
#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include "shell_d2d.h"
#include "shell_tokens.h"
#include <vector>
#include <cmath>
#include <algorithm>
#include <d2d1.h>
#include <dwrite.h>
#include <dwrite_1.h>
#include <cwchar>
#include <new>
#include <map>
#include <string>

struct shadow_cache { unsigned width,height,dpi; int kind; ID2D1Bitmap *bitmap; };
struct toc_row_cache {HBITMAP bitmap;unsigned used;};
struct shell_d2d {
  HWND window;
  ID2D1Factory *factory;
  ID2D1HwndRenderTarget *target;
  ID2D1SolidColorBrush *brush;
  ID2D1DCRenderTarget *dc_target; /* owner-drawn controls */
  ID2D1SolidColorBrush *dc_brush;
  IDWriteFactory *write;
  IDWriteTextFormat *format[SHELL_TEXT_STYLES];
  const wchar_t *family[SHELL_TEXT_STYLES];
  std::vector<shadow_cache> shadows;
  unsigned recreated;
  unsigned dpi;
  float title_x,title_spacing;
  std::map<unsigned,std::wstring> toc_labels;
  HFONT toc_fonts[2];
  int toc_width;
  float toc_metrics[4];
  std::map<unsigned,toc_row_cache> toc_rows;
  HDC toc_row_dc;
  unsigned toc_tick;

};

/* 96 dpi: one unit is one physical pixel, the host's own coordinate space. */
static D2D1_RENDER_TARGET_PROPERTIES pixel_properties(D2D1_PIXEL_FORMAT format) {
  D2D1_RENDER_TARGET_PROPERTIES properties = D2D1::RenderTargetProperties(D2D1_RENDER_TARGET_TYPE_DEFAULT, format);
  properties.dpiX = properties.dpiY = 96.0f;
  return properties;
}

static void drop_target(shell_d2d *shell) {
  if (shell->brush) { shell->brush->Release(); shell->brush = nullptr; }
  if (shell->target) { shell->target->Release(); shell->target = nullptr; }
}

static void drop_dc_target(shell_d2d *shell) {
  for (auto &entry : shell->shadows) entry.bitmap->Release();
  shell->shadows.clear();
  if (shell->dc_brush) { shell->dc_brush->Release(); shell->dc_brush = nullptr; }
  if (shell->dc_target) { shell->dc_target->Release(); shell->dc_target = nullptr; }
}

static IDWriteFontFamily *find_family(shell_d2d *shell, const wchar_t *const *names, size_t count,
                                      const wchar_t **chosen) {
  IDWriteFontCollection *fonts = nullptr;
  IDWriteFontFamily *family = nullptr;
  if (FAILED(shell->write->GetSystemFontCollection(&fonts, FALSE))) return nullptr;
  for (size_t i = 0; i < count && !family; i++) {
    UINT32 index = 0;
    BOOL exists = FALSE;
    if (SUCCEEDED(fonts->FindFamilyName(names[i], &index, &exists)) && exists &&
        SUCCEEDED(fonts->GetFontFamily(index, &family)) && chosen)
      *chosen = names[i];
  }
  fonts->Release();
  return family;
}

static HRESULT make_format(shell_d2d *shell, int style) {

  const bool is_title = style == SHELL_TEXT_TITLE || style == SHELL_TEXT_CENTER;
  const bool is_icon = style == SHELL_TEXT_ICON;
  const wchar_t *name = SHELL_UI_FONTS[2];
  IDWriteFontFamily *family = find_family(shell, is_icon ? SHELL_ICON_FONTS : SHELL_UI_FONTS,
    is_icon ? sizeof(SHELL_ICON_FONTS)/sizeof(*SHELL_ICON_FONTS) : sizeof(SHELL_UI_FONTS)/sizeof(*SHELL_UI_FONTS), &name);
  if (family) family->Release();
  IDWriteTextFormat *format = nullptr;
  HRESULT hr = shell->write->CreateTextFormat(name, nullptr,
                                              (DWRITE_FONT_WEIGHT)(is_title ? SHELL_TITLE_WEIGHT : style == SHELL_TEXT_PAGE_NUMBER ? SHELL_PAGE_WEIGHT : (style == SHELL_TEXT_UI || style == SHELL_TEXT_LABEL) ? SHELL_CONTROL_WEIGHT : (int)DWRITE_FONT_WEIGHT_NORMAL),
                                              DWRITE_FONT_STYLE_NORMAL, DWRITE_FONT_STRETCH_NORMAL,
                                              (float)(is_title ? SHELL_TITLE_FONT : is_icon ? SHELL_ICON_FONT : style == SHELL_TEXT_UI ? SHELL_VALUE_FONT : style == SHELL_TEXT_LABEL ? SHELL_LABEL_FONT : SHELL_PAGE_FONT) * shell->dpi / 96.0f, L"zh-cn", &format);
  if (FAILED(hr)) return hr;
  format->SetWordWrapping(DWRITE_WORD_WRAPPING_NO_WRAP);
  format->SetParagraphAlignment(DWRITE_PARAGRAPH_ALIGNMENT_CENTER);
  format->SetTextAlignment(is_title && style != SHELL_TEXT_CENTER ? DWRITE_TEXT_ALIGNMENT_LEADING : DWRITE_TEXT_ALIGNMENT_CENTER);
  if (is_title) {
    IDWriteInlineObject *ellipsis = nullptr;
    DWRITE_TRIMMING trimming = {DWRITE_TRIMMING_GRANULARITY_CHARACTER, 0, 0};
    if (SUCCEEDED(shell->write->CreateEllipsisTrimmingSign(format, &ellipsis))) {
      format->SetTrimming(&trimming, ellipsis);
      ellipsis->Release();
    }
  }
  if (shell->format[style]) shell->format[style]->Release();
  shell->format[style] = format;
  shell->family[style] = name;
  return S_OK;
}

extern "C" HRESULT shell_d2d_create(HWND window, shell_d2d **out) {
  *out = nullptr;
  shell_d2d *shell = new (std::nothrow) shell_d2d();
  if (!shell) return E_OUTOFMEMORY;
  shell->window = window;
  shell->dpi = 96;
  HRESULT hr = D2D1CreateFactory(D2D1_FACTORY_TYPE_SINGLE_THREADED, &shell->factory);
  if (SUCCEEDED(hr))
    hr = DWriteCreateFactory(DWRITE_FACTORY_TYPE_SHARED, __uuidof(IDWriteFactory),
                             reinterpret_cast<IUnknown **>(&shell->write));
  for (int style = 0; SUCCEEDED(hr) && style < SHELL_TEXT_STYLES; style++) hr = make_format(shell, style);
  if (FAILED(hr)) { shell_d2d_destroy(shell); return hr; }
  *out = shell;
  return S_OK;
}

extern "C" void shell_d2d_destroy(shell_d2d *shell) {
  if (!shell) return;
  shell_d2d_toc_clear(shell);
  if(shell->toc_row_dc) DeleteDC(shell->toc_row_dc);
  drop_target(shell);
  drop_dc_target(shell);
  for (int style = 0; style < SHELL_TEXT_STYLES; style++)
    if (shell->format[style]) shell->format[style]->Release();
  if (shell->write) shell->write->Release();
  if (shell->factory) shell->factory->Release();
  delete shell;
}

extern "C" void shell_d2d_target_dpi(const shell_d2d *shell, float values[4]) {
  for (int i = 0; i < 4; i++) values[i] = 0;
  if (shell->target) shell->target->GetDpi(&values[0], &values[1]);
  if (shell->dc_target) shell->dc_target->GetDpi(&values[2], &values[3]);
}

extern "C" HRESULT shell_d2d_set_dpi(shell_d2d *shell, unsigned dpi) {
  if (!shell || !dpi) return E_INVALIDARG;
  if (shell->dpi == dpi) return S_OK;
  shell->dpi = dpi;
  shell_d2d_toc_clear(shell);
  for (int style = 0; style < SHELL_TEXT_STYLES; style++) {
    HRESULT hr = make_format(shell, style);
    if (FAILED(hr)) return hr;
  }
  return S_OK;
}

extern "C" HRESULT shell_d2d_resize(shell_d2d *shell, UINT width, UINT height) {
  return shell->target ? shell->target->Resize(D2D1::SizeU(width, height)) : S_OK;
}

extern "C" HRESULT shell_d2d_begin(shell_d2d *shell, uint32_t background) {
  if (!shell->target) {
    RECT area;
    GetClientRect(shell->window, &area);
    D2D1_SIZE_U size = D2D1::SizeU((UINT32)(area.right - area.left), (UINT32)(area.bottom - area.top));
    HRESULT hr = shell->factory->CreateHwndRenderTarget(pixel_properties(D2D1::PixelFormat()),
                                                        D2D1::HwndRenderTargetProperties(shell->window, size),
                                                        &shell->target);
    if (SUCCEEDED(hr)) hr = shell->target->CreateSolidColorBrush(D2D1::ColorF(background), &shell->brush);
    if (FAILED(hr)) { drop_target(shell); return hr; }
    shell->target->SetTextAntialiasMode(D2D1_TEXT_ANTIALIAS_MODE_GRAYSCALE);
  }
  shell->target->BeginDraw();
  shell->target->Clear(D2D1::ColorF(background));
  return S_OK;
}

extern "C" void shell_d2d_fill(shell_d2d *shell, float x, float y, float width, float height, uint32_t color) {
  shell->brush->SetColor(D2D1::ColorF(color));
  shell->target->FillRectangle(D2D1::RectF(x, y, x + width, y + height), shell->brush);
}

extern "C" HRESULT shell_d2d_text(shell_d2d *shell, int style, const wchar_t *text, float x, float y, float width,
                                  float height, uint32_t color) {
  if (style < 0 || style >= SHELL_TEXT_STYLES) return E_INVALIDARG;
  shell->brush->SetColor(D2D1::ColorF(color));
  IDWriteTextLayout *layout=nullptr;
  HRESULT hr=shell->write->CreateTextLayout(text,(UINT32)wcslen(text),shell->format[style],width,height,&layout);
  if(FAILED(hr)) return hr;
  if(style==SHELL_TEXT_TITLE) {
    shell->title_x=x;
    IDWriteTextLayout1 *spacing=nullptr;
    if(SUCCEEDED(layout->QueryInterface(__uuidof(IDWriteTextLayout1),(void **)&spacing))) {
      float half=-.005f*(float)SHELL_TITLE_FONT*shell->dpi/96.f;
      if(SUCCEEDED(spacing->SetCharacterSpacing(half,half,0,{0,(UINT32)wcslen(text)}))) shell->title_spacing=2*half;
      spacing->Release();
    }
  }
  shell->target->DrawTextLayout(D2D1::Point2F(x,y),layout,shell->brush);
  layout->Release();
  return S_OK;
}

extern "C" HRESULT shell_d2d_end(shell_d2d *shell) {
  HRESULT hr = shell->target->EndDraw();
  if (hr != D2DERR_RECREATE_TARGET) return hr;
  drop_target(shell);
  shell->recreated++;
  return S_FALSE;
}

extern "C" unsigned shell_d2d_recreated(const shell_d2d *shell) {
  return shell->recreated;
}

extern "C" HRESULT shell_d2d_icon_button(shell_d2d *shell, HDC dc, const RECT *box, wchar_t glyph,
                                         const shell_d2d_button *look) {
  HRESULT hr;
  if (!shell->dc_target) {
    const D2D1_RENDER_TARGET_PROPERTIES properties =
        pixel_properties(D2D1::PixelFormat(DXGI_FORMAT_B8G8R8A8_UNORM, D2D1_ALPHA_MODE_IGNORE));
    hr = shell->factory->CreateDCRenderTarget(&properties, &shell->dc_target);
    if (SUCCEEDED(hr)) hr = shell->dc_target->CreateSolidColorBrush(D2D1::ColorF(look->background), &shell->dc_brush);
    if (FAILED(hr)) { drop_dc_target(shell); return hr; }
    shell->dc_target->SetTextAntialiasMode(D2D1_TEXT_ANTIALIAS_MODE_GRAYSCALE);
  }
  hr = shell->dc_target->BindDC(dc, box);
  if (FAILED(hr)) return hr;
  const float width = (float)(box->right - box->left), height = (float)(box->bottom - box->top);
  const D2D1_POINT_2F centre = D2D1::Point2F(width / 2, height / 2 + look->offset_y);
  const float radius = look->diameter / 2;
  const float k=shell->dpi/96.f;
  auto rect=D2D1::RectF(centre.x-radius,centre.y-radius,centre.x+radius,centre.y+radius);
  shell->dc_target->BeginDraw();
  shell->dc_target->Clear(D2D1::ColorF(look->background));
  if (look->has_fill) {
    shell->dc_brush->SetColor(D2D1::ColorF(look->fill));
    shell->dc_target->FillRoundedRectangle(D2D1::RoundedRect(rect,9*k,9*k),shell->dc_brush);
  }
  shell->dc_brush->SetColor(D2D1::ColorF(look->icon));
  const float stroke=1.5f*k;
  if(glyph==0xE8FD) {
    for(int row=-1;row<=1;row++) {
      float y=centre.y+(row*6+.5f)*k;
      shell->dc_target->DrawLine(D2D1::Point2F(centre.x-9*k,y),D2D1::Point2F(centre.x+9*k,y),shell->dc_brush,stroke);
    }
  } else if(glyph==0xE721) {
    auto lens=D2D1::Point2F(centre.x-2*k,centre.y-2*k);
    shell->dc_target->DrawEllipse(D2D1::Ellipse(lens,6*k,6*k),shell->dc_brush,stroke);
    shell->dc_target->DrawLine(D2D1::Point2F(centre.x+2.5f*k,centre.y+2.5f*k),
      D2D1::Point2F(centre.x+8*k,centre.y+8*k),shell->dc_brush,stroke);
  } else {
    ID2D1PathGeometry *path=nullptr; ID2D1GeometrySink *sink=nullptr;
    if(SUCCEEDED(shell->factory->CreatePathGeometry(&path)) && SUCCEEDED(path->Open(&sink))) {
      for(int i=0;i<48;i++) {
        float angle=(float)i*6.28318530718f/48.f;
        float r=(i%6==0 || i%6==5 ? 6.25f : 8.25f)*k;
        auto point=D2D1::Point2F(centre.x+std::cos(angle)*r,centre.y+std::sin(angle)*r);
        if(i==0) sink->BeginFigure(point,D2D1_FIGURE_BEGIN_HOLLOW); else sink->AddLine(point);
      }
      sink->EndFigure(D2D1_FIGURE_END_CLOSED);sink->Close();
      shell->dc_target->DrawGeometry(path,shell->dc_brush,stroke);
    }
    if(sink) sink->Release();
    if(path) path->Release();
    shell->dc_target->DrawEllipse(D2D1::Ellipse(centre,3*k,3*k),shell->dc_brush,stroke);
  }
  if (look->has_ring) {
    float expansion=3*k;
    rect.left-=expansion;rect.top-=expansion;rect.right+=expansion;rect.bottom+=expansion;
    shell->dc_brush->SetColor(D2D1::ColorF(look->ring));
    shell->dc_target->DrawRoundedRectangle(D2D1::RoundedRect(rect,11*k,11*k),shell->dc_brush,look->ring_width);
  }
  hr = shell->dc_target->EndDraw();
  if (hr == D2DERR_RECREATE_TARGET) { drop_dc_target(shell); shell->recreated++; return S_FALSE; }
  return hr;
}

static HRESULT page_layout(shell_d2d *shell,const wchar_t *text,float width,float height,IDWriteTextLayout **layout) {
  UINT32 length=(UINT32)wcslen(text);
  HRESULT hr=shell->write->CreateTextLayout(text,length,shell->format[SHELL_TEXT_PAGE_NUMBER],width,height,layout);
  if(FAILED(hr)) return hr;
  IDWriteTypography *typography=nullptr;
  hr=shell->write->CreateTypography(&typography);
  if(SUCCEEDED(hr)) hr=typography->AddFontFeature({DWRITE_FONT_FEATURE_TAG_TABULAR_FIGURES,1});
  if(SUCCEEDED(hr)) hr=(*layout)->SetTypography(typography,{0,length});
  /* Segoe UI Semibold's tnum leaves 7 narrower. Normalize digit advances even
     when a selected face implements only part of the OpenType feature. */
  IDWriteTextLayout *digits=nullptr;IDWriteTextLayout1 *spacing=nullptr;
  if(SUCCEEDED(hr)) hr=shell->write->CreateTextLayout(L"0123456789",10,shell->format[SHELL_TEXT_PAGE_NUMBER],1000,100,&digits);
  if(SUCCEEDED(hr)) hr=digits->SetTypography(typography,{0,10});
  DWRITE_CLUSTER_METRICS clusters[10]={};UINT32 count=0;
  if(SUCCEEDED(hr)) hr=digits->GetClusterMetrics(clusters,10,&count);
  if(SUCCEEDED(hr) && count!=10) hr=E_FAIL;
  if(SUCCEEDED(hr)) hr=(*layout)->QueryInterface(__uuidof(IDWriteTextLayout1),(void **)&spacing);
  if(SUCCEEDED(hr)) {
    float advance=0;for(const auto &q:clusters) advance=std::max(advance,q.width);
    for(UINT32 i=0;i<length && SUCCEEDED(hr);i++) if(text[i]>=L'0' && text[i]<=L'9') {
      float extra=(advance-clusters[text[i]-L'0'].width)/2;
      hr=spacing->SetCharacterSpacing(extra,extra,0,{i,1});
    }
  }
  if(spacing) spacing->Release();
  if(digits) digits->Release();
  if(typography) typography->Release();
  if(FAILED(hr)) {(*layout)->Release();*layout=nullptr;}
  return hr;
}

extern "C" void shell_d2d_page_metrics(shell_d2d *s,float values[12]) {
  values[0]=s->format[SHELL_TEXT_PAGE_NUMBER]->GetFontSize();
  values[1]=(float)s->format[SHELL_TEXT_PAGE_NUMBER]->GetFontWeight();
  IDWriteTextLayout *layout=nullptr;
  for(int i=2;i<12;i++) values[i]=0;
  if(SUCCEEDED(page_layout(s,L"0123456789",1000,100,&layout))) {
    DWRITE_CLUSTER_METRICS clusters[10]={};UINT32 count=0;
    if(SUCCEEDED(layout->GetClusterMetrics(clusters,10,&count)) && count==10)
      for(int i=0;i<10;i++) values[2+i]=clusters[i].width;
    layout->Release();
  }
}

extern "C" HRESULT shell_d2d_dc_text(shell_d2d *shell, HDC dc, const RECT *box, const wchar_t *text,
                                     unsigned strong_start, unsigned strong_length, uint32_t current, uint32_t rest) {
  if (!shell->dc_target) {
    const D2D1_RENDER_TARGET_PROPERTIES properties =
      pixel_properties(D2D1::PixelFormat(DXGI_FORMAT_B8G8R8A8_UNORM, D2D1_ALPHA_MODE_IGNORE));
    HRESULT hr = shell->factory->CreateDCRenderTarget(&properties, &shell->dc_target);
    if (SUCCEEDED(hr)) hr = shell->dc_target->CreateSolidColorBrush(D2D1::ColorF(current), &shell->dc_brush);
    if (FAILED(hr)) { drop_dc_target(shell); return hr; }
    shell->dc_target->SetTextAntialiasMode(D2D1_TEXT_ANTIALIAS_MODE_GRAYSCALE);
  }
  HRESULT hr = shell->dc_target->BindDC(dc, box);
  if (FAILED(hr)) return hr;
  IDWriteTextLayout *layout=nullptr;
  UINT32 length=(UINT32)wcslen(text);
  hr=page_layout(shell,text,(float)(box->right-box->left),(float)(box->bottom-box->top),&layout);
  if(FAILED(hr)) return hr;
  /* The strong run (the current page) takes `current`; everything else `rest`. */
  ID2D1SolidColorBrush *strong=nullptr;
  if(strong_start>length) strong_start=length;
  if(strong_length>length-strong_start) strong_length=length-strong_start;
  if(SUCCEEDED(hr)) hr=shell->dc_target->CreateSolidColorBrush(D2D1::ColorF(current),&strong);
  if(SUCCEEDED(hr) && strong_length) hr=layout->SetDrawingEffect(strong,{strong_start,strong_length});
  if(FAILED(hr)) { if(strong) strong->Release();layout->Release();return hr; }
  DWRITE_OVERHANG_METRICS ink={};
  hr=layout->GetOverhangMetrics(&ink);
  if(FAILED(hr)) {strong->Release();layout->Release();return hr;}
  shell->dc_target->BeginDraw();
  shell->dc_brush->SetColor(D2D1::ColorF(rest));
  shell->dc_target->DrawTextLayout(D2D1::Point2F(0,(ink.top-ink.bottom)/2),layout,shell->dc_brush);
  strong->Release();layout->Release();
  hr = shell->dc_target->EndDraw();
  if (hr == D2DERR_RECREATE_TARGET) { drop_dc_target(shell); shell->recreated++; return S_FALSE; }
  return hr;
}

static unsigned face_simulations(shell_d2d *shell, const wchar_t *name) {
  const wchar_t *const names[] = {name};
  IDWriteFontFamily *family = find_family(shell, names, 1, nullptr);
  IDWriteFont *font = nullptr;
  unsigned simulations = 0xFFFFFFFFu; /* family missing */
  if (family && SUCCEEDED(family->GetFirstMatchingFont(DWRITE_FONT_WEIGHT_SEMI_BOLD, DWRITE_FONT_STRETCH_NORMAL,
                                                       DWRITE_FONT_STYLE_NORMAL, &font))) {
    simulations = (unsigned)font->GetSimulations();
    font->Release();
  }
  if (family) family->Release();
  return simulations;
}

extern "C" HRESULT shell_d2d_title_faces(shell_d2d *shell, unsigned *latin, unsigned *cjk) {
  *latin = face_simulations(shell, shell->family[SHELL_TEXT_TITLE]);
  *cjk = face_simulations(shell, L"Microsoft YaHei UI");
  return S_OK;
}

extern "C" const wchar_t *shell_d2d_family(const shell_d2d *shell, int style) {
  return style >= 0 && style < SHELL_TEXT_STYLES ? shell->family[style] : L"";
}

extern "C" void shell_d2d_metrics(const shell_d2d *s,float values[8]) {
  const int styles[]={SHELL_TEXT_TITLE,SHELL_TEXT_UI,SHELL_TEXT_LABEL};
  for(int i=0;i<3;i++) {
    values[i*2]=s->format[styles[i]]->GetFontSize();
    values[i*2+1]=(float)s->format[styles[i]]->GetFontWeight();
  }
  values[6]=s->title_x;values[7]=s->title_spacing;
}

static HRESULT bind_dc(shell_d2d *s, HDC dc, const RECT *box) {
  if (!s->dc_target) {
    auto props = pixel_properties(D2D1::PixelFormat(DXGI_FORMAT_B8G8R8A8_UNORM, D2D1_ALPHA_MODE_IGNORE));
    HRESULT hr = s->factory->CreateDCRenderTarget(&props, &s->dc_target);
    if (SUCCEEDED(hr)) hr = s->dc_target->CreateSolidColorBrush(D2D1::ColorF(shell_theme_light.layer_float), &s->dc_brush);
    if (FAILED(hr)) { drop_dc_target(s); return hr; }
    s->dc_target->SetTextAntialiasMode(D2D1_TEXT_ANTIALIAS_MODE_GRAYSCALE);
  }
  return s->dc_target->BindDC(dc, box);
}

/* Rasterize the rounded mask, separable Gaussian blur, then cache its
   premultiplied BGRA bitmap. Both layers retain the CSS offset/spread/alpha.
   CSS blur radius is twice sigma. Nothing is sampled from the desktop. */
static ID2D1Bitmap *shadow_bitmap(shell_d2d *s, unsigned w, unsigned h, int kind) {
  for (const auto &e : s->shadows)
    if (e.width==w && e.height==h && e.dpi==s->dpi && e.kind==kind) return e.bitmap;
  const float scale=s->dpi/96.f, pad=(float)SHELL_SHADOW_PAD*scale;
  const float radius=(float)(kind==3 ? 0 : kind==1 ? SHELL_RADIUS : kind==2 ? 6 : SHELL_RADIUS_SM)*scale;
  const auto *layers=kind==3 ? SHELL_PAGE_SHADOW : kind==1 ? SHELL_SHADOW_LG : SHELL_SHADOW_SM;
  std::vector<float> alpha(w*h), mask(w*h), temp(w*h), blurred(w*h);
  for (int layer=0;layer<2;layer++) {
    const auto &q=layers[layer];
    float l=pad+(q.x-q.spread)*scale, t=pad+(q.y-q.spread)*scale;
    float r=w-pad+(q.x+q.spread)*scale, b=h-pad+(q.y+q.spread)*scale;
    float rad=std::max(0.f,radius+q.spread*scale);
    for(unsigned y=0;y<h;y++) for(unsigned x=0;x<w;x++) {
      float dx=std::max(std::max(l+rad-(x+.5f),(x+.5f)-(r-rad)),0.f);
      float dy=std::max(std::max(t+rad-(y+.5f),(y+.5f)-(b-rad)),0.f);
      mask[y*w+x]=std::clamp(rad+.5f-std::sqrt(dx*dx+dy*dy),0.f,1.f);
    }
    float sigma=q.blur*scale/2;
    int reach=(int)std::ceil(3*sigma);
    std::vector<float> kernel(2*reach+1); float sum=0;
    for(int i=-reach;i<=reach;i++) { float v=reach ? std::exp(-i*i/(2*sigma*sigma)) : 1.f;kernel[i+reach]=v;sum+=v; }
    for(auto &v:kernel) v/=sum;
    for(unsigned y=0;y<h;y++) for(unsigned x=0;x<w;x++) {
      float v=0; for(int i=-reach;i<=reach;i++) if((int)x+i>=0 && (int)x+i<(int)w) v+=mask[y*w+x+i]*kernel[i+reach];
      temp[y*w+x]=v;
    }
    for(unsigned y=0;y<h;y++) for(unsigned x=0;x<w;x++) {
      float v=0; for(int i=-reach;i<=reach;i++) if((int)y+i>=0 && (int)y+i<(int)h) v+=temp[(y+i)*w+x]*kernel[i+reach];
      blurred[y*w+x]=v;
    }
    for(size_t i=0;i<alpha.size();i++) alpha[i]=1-(1-alpha[i])*(1-blurred[i]*q.alpha);
  }
  std::vector<uint32_t> pixels(w*h);
  for(size_t i=0;i<pixels.size();i++) {
    auto a=(unsigned)(alpha[i]*255+.5f); uint32_t rgb=layers[0].rgb;
    pixels[i]=(a<<24)|((((rgb>>16)&255)*a/255)<<16)|((((rgb>>8)&255)*a/255)<<8)|((rgb&255)*a/255);
  }
  ID2D1Bitmap *bitmap=nullptr;
  auto props=D2D1::BitmapProperties(D2D1::PixelFormat(DXGI_FORMAT_B8G8R8A8_UNORM,D2D1_ALPHA_MODE_PREMULTIPLIED));
  if(FAILED(s->dc_target->CreateBitmap(D2D1::SizeU(w,h),pixels.data(),w*4,props,&bitmap))) return nullptr;
  s->shadows.push_back({w,h,s->dpi,kind,bitmap});
  return bitmap;
}

extern "C" HRESULT shell_d2d_page_image(shell_d2d *s,HDC dc,const RECT *area,const RECT *image,
                                        unsigned source_width,unsigned source_height,
                                        const uint32_t *pixels,unsigned pitch,uint32_t background) {
  HRESULT hr=bind_dc(s,dc,area);if(FAILED(hr)) return hr;
  unsigned w=(unsigned)(image->right-image->left),h=(unsigned)(image->bottom-image->top);
  float pad=(float)SHELL_SHADOW_PAD*s->dpi/96.f;
  auto shadow=shadow_bitmap(s,w+2*(unsigned)pad,h+2*(unsigned)pad,3);
  auto props=D2D1::BitmapProperties(D2D1::PixelFormat(DXGI_FORMAT_B8G8R8A8_UNORM,D2D1_ALPHA_MODE_IGNORE));
  ID2D1Bitmap *bitmap=nullptr;
  hr=s->dc_target->CreateBitmap(D2D1::SizeU(source_width,source_height),pixels,pitch,props,&bitmap);
  if(FAILED(hr)) return hr;
  auto rect=D2D1::RectF((float)image->left,(float)image->top,(float)image->right,(float)image->bottom);
  s->dc_target->BeginDraw();s->dc_target->Clear(D2D1::ColorF(background));
  if(shadow) s->dc_target->DrawBitmap(shadow,D2D1::RectF(rect.left-pad,rect.top-pad,rect.right+pad,rect.bottom+pad));
  s->dc_target->DrawBitmap(bitmap,rect);bitmap->Release();
  hr=s->dc_target->EndDraw();if(hr==D2DERR_RECREATE_TARGET) drop_dc_target(s);return hr;
}

/* dark: 0 light, 1 dark, 2 system high contrast (colours supplied by the host). */
shell_theme shell_theme_contrast = shell_theme_dark; /* declared extern "C" in shell_tokens.h */
static const shell_theme &theme_of(int dark) { return dark == 2 ? shell_theme_contrast : dark ? shell_theme_dark : shell_theme_light; }
static float line_alpha(int dark, float normal) { return dark == 2 ? 1.f : normal; }

struct edit_color { DWRITE_TEXT_RANGE range; uint32_t rgb; };
struct edit_layout {
  IDWriteTextLayout *text=nullptr;
  std::vector<edit_color> colors;
  ~edit_layout() {if(text)text->Release();}
};

extern "C" HRESULT shell_d2d_edit_layout(shell_d2d *s,const wchar_t *text,const wchar_t *family,
                                         float size,float width,void **out,float *height) {
  *out=nullptr;
  IDWriteTextFormat *format=nullptr;
  IDWriteTextLayout *layout=nullptr;
  HRESULT hr=s->write->CreateTextFormat(family,nullptr,DWRITE_FONT_WEIGHT_NORMAL,
    DWRITE_FONT_STYLE_NORMAL,DWRITE_FONT_STRETCH_NORMAL,size,L"zh-cn",&format);
  if(SUCCEEDED(hr)) hr=s->write->CreateTextLayout(text,(UINT32)wcslen(text),format,
    std::max(1.f,width),10000000.f,&layout);
  if(format) format->Release();
  DWRITE_TEXT_METRICS metrics={};
  if(SUCCEEDED(hr)) hr=layout->GetMetrics(&metrics);
  if(FAILED(hr)) {if(layout)layout->Release();return hr;}
  auto view=new(std::nothrow) edit_layout;
  if(!view) {layout->Release();return E_OUTOFMEMORY;}
  view->text=layout;*height=metrics.height;*out=view;return S_OK;
}

extern "C" HRESULT shell_d2d_edit_style(shell_d2d *s,void *p,unsigned start,unsigned length,
  const wchar_t *family,float size,unsigned bold,unsigned italic,int has_color,uint32_t rgb,int *missing) {
  auto view=static_cast<edit_layout *>(p);auto text=view->text;
  DWRITE_TEXT_RANGE range={start,length};*missing=0;
  HRESULT hr=S_OK;
  if(family && *family) {
    IDWriteFontCollection *fonts=nullptr;UINT32 index=0;BOOL exists=FALSE;
    hr=s->write->GetSystemFontCollection(&fonts,FALSE);
    if(SUCCEEDED(hr)) hr=fonts->FindFamilyName(family,&index,&exists);
    if(fonts)fonts->Release();
    if(FAILED(hr))return hr;
    if(exists)hr=text->SetFontFamilyName(family,range);else *missing=1;
  }
  if(SUCCEEDED(hr) && size>0)hr=text->SetFontSize(size,range);
  if(SUCCEEDED(hr))hr=text->SetFontWeight(bold ? DWRITE_FONT_WEIGHT_BOLD:DWRITE_FONT_WEIGHT_NORMAL,range);
  if(SUCCEEDED(hr))hr=text->SetFontStyle(italic ? DWRITE_FONT_STYLE_ITALIC:DWRITE_FONT_STYLE_NORMAL,range);
  if(SUCCEEDED(hr) && has_color) {
    try {view->colors.push_back({range,rgb});} catch(...) {return E_OUTOFMEMORY;}
  }
  return hr;
}
extern "C" HRESULT shell_d2d_edit_align(void *p,unsigned alignment,float *height) {
  auto text=static_cast<edit_layout *>(p)->text;
  const DWRITE_TEXT_ALIGNMENT values[]={DWRITE_TEXT_ALIGNMENT_LEADING,DWRITE_TEXT_ALIGNMENT_CENTER,
    DWRITE_TEXT_ALIGNMENT_TRAILING,DWRITE_TEXT_ALIGNMENT_JUSTIFIED};
  HRESULT hr=text->SetTextAlignment(values[alignment<4 ? alignment:0]);
  DWRITE_TEXT_METRICS metrics={};
  if(SUCCEEDED(hr))hr=text->GetMetrics(&metrics);
  if(SUCCEEDED(hr))*height=metrics.height;
  return hr;
}

extern "C" void shell_d2d_edit_release(void *layout) {
  delete static_cast<edit_layout *>(layout);
}

extern "C" unsigned shell_d2d_edit_hit(void *p,float x,float y) {
  BOOL trailing=FALSE,inside=FALSE;DWRITE_HIT_TEST_METRICS hit={};
  if(FAILED(static_cast<edit_layout *>(p)->text->HitTestPoint(x,y,&trailing,&inside,&hit))) return 0;
  return hit.textPosition+(trailing ? hit.length:0);
}

extern "C" void shell_d2d_edit_position(void *p,unsigned at,float box[4]) {
  DWRITE_HIT_TEST_METRICS hit={};float x=0,y=0;
  static_cast<edit_layout *>(p)->text->HitTestTextPosition(at,FALSE,&x,&y,&hit);
  box[0]=x;box[1]=y;box[2]=hit.width;box[3]=hit.height;
}

extern "C" HRESULT shell_d2d_edit_paint(shell_d2d *s,HDC dc,const RECT *area,int dark,
  const shell_d2d_edit_row *rows,size_t count,float inset,float scroll,float top) {
  HRESULT hr=bind_dc(s,dc,area);if(FAILED(hr)) return hr;
  const auto &c=theme_of(dark);
  s->dc_target->BeginDraw();s->dc_target->Clear(D2D1::ColorF(c.layer_page));
  s->dc_target->PushAxisAlignedClip(D2D1::RectF(0,top,(float)(area->right-area->left),
    (float)(area->bottom-area->top)),D2D1_ANTIALIAS_MODE_ALIASED);
  for(size_t i=0;i<count && SUCCEEDED(hr);i++) {
    const auto &row=rows[i];float y=row.y-scroll;
    const float origin=inset+row.x;
    if(row.cell_border) {
      s->dc_brush->SetColor(D2D1::ColorF(c.text,.65f));
      s->dc_target->DrawRectangle(D2D1::RectF(row.cell_box[0],row.cell_box[1]-scroll,
        row.cell_box[2],row.cell_box[3]-scroll),s->dc_brush,1.f);
    }
    if(!row.height || y+row.height<0 || y>area->bottom-area->top) continue;
    auto view=static_cast<edit_layout *>(row.layout);auto layout=view->text;
    UINT32 needed=0;
    layout->HitTestTextRange(row.start,row.length,origin,y,nullptr,0,&needed);
    std::vector<DWRITE_HIT_TEST_METRICS> boxes(needed);
    if(needed) layout->HitTestTextRange(row.start,row.length,origin,y,boxes.data(),needed,&needed);
    s->dc_brush->SetColor(D2D1::ColorF(dark ? 0x82B5FF:0x3178D4,.35f));
    for(const auto &b:boxes) s->dc_target->FillRectangle(
      D2D1::RectF(b.left,b.top,b.left+b.width,b.top+b.height),s->dc_brush);
    float caret[4];shell_d2d_edit_position(row.layout,row.caret,caret);
    if(row.selected_break) {
      float end[4]={};
      // A paragraph mark gets its own small selection cell at the visual end.
      UINT32 n=0;layout->GetLineMetrics(nullptr,0,&n);
      std::vector<DWRITE_LINE_METRICS> lines(n);
      if(n && SUCCEEDED(layout->GetLineMetrics(lines.data(),n,&n))) {
        UINT32 length=0;for(const auto &line:lines) length+=line.length;
        shell_d2d_edit_position(row.layout,length,end);
        s->dc_target->FillRectangle(D2D1::RectF(origin+end[0],y+end[1],
          origin+end[0]+6,y+end[1]+end[3]),s->dc_brush);
      }
    }
    s->dc_brush->SetColor(D2D1::ColorF(c.text));
    // Effects belong to this DC target only; clear them before device recreation.
    for(const auto &color:view->colors) {
      ID2D1SolidColorBrush *brush=nullptr;
      hr=s->dc_target->CreateSolidColorBrush(D2D1::ColorF(color.rgb),&brush);
      if(SUCCEEDED(hr)) {layout->SetDrawingEffect(brush,color.range);brush->Release();}
      else break;
    }
    if(SUCCEEDED(hr))s->dc_target->DrawTextLayout(D2D1::Point2F(origin,y),layout,s->dc_brush);
    for(const auto &color:view->colors)layout->SetDrawingEffect(nullptr,color.range);
    if(row.show_caret) s->dc_target->FillRectangle(D2D1::RectF(origin+caret[0],y+caret[1],
      origin+caret[0]+1,y+caret[1]+caret[3]),s->dc_brush);
  }
  s->dc_target->PopAxisAlignedClip();HRESULT end=s->dc_target->EndDraw();
  if(SUCCEEDED(hr))hr=end;
  if(hr==D2DERR_RECREATE_TARGET) {drop_dc_target(s);return S_FALSE;}
  return hr;
}


extern "C" HRESULT shell_d2d_edit_image(shell_d2d *s,HDC dc,const RECT *area,int dark,
  const unsigned char *rgba,unsigned width,unsigned height,unsigned stride,
  float x,float y,float display_width,float display_height,float top,int selected) {
  if(!s || !dc || !area || !rgba || !width || !height || width>UINT32_MAX/4 ||
      stride<width*4 || height>SIZE_MAX/stride || width>SIZE_MAX/4/height ||
      !std::isfinite(x) || !std::isfinite(y) || !std::isfinite(display_width) ||
      !std::isfinite(display_height) || !std::isfinite(top) || display_width<=0 || display_height<=0)
    return E_INVALIDARG;
  HRESULT hr=bind_dc(s,dc,area);if(FAILED(hr))return hr;
  std::vector<unsigned char> bgra;
  try {bgra.resize((size_t)width*height*4);} catch(...) {return E_OUTOFMEMORY;}
  for(unsigned row=0;row<height;row++)for(unsigned col=0;col<width;col++) {
    const auto *p=rgba+(size_t)row*stride+col*4;
    auto *q=bgra.data()+((size_t)row*width+col)*4;
    q[0]=(unsigned char)((p[2]*p[3]+127)/255);
    q[1]=(unsigned char)((p[1]*p[3]+127)/255);
    q[2]=(unsigned char)((p[0]*p[3]+127)/255);q[3]=p[3];
  }
  ID2D1Bitmap *bitmap=nullptr;
  auto properties=D2D1::BitmapProperties(D2D1::PixelFormat(
    DXGI_FORMAT_B8G8R8A8_UNORM,D2D1_ALPHA_MODE_PREMULTIPLIED));
  hr=s->dc_target->CreateBitmap(D2D1::SizeU(width,height),bgra.data(),width*4,properties,&bitmap);
  if(FAILED(hr))return hr;
  s->dc_target->BeginDraw();
  s->dc_target->PushAxisAlignedClip(D2D1::RectF(0,top,(float)(area->right-area->left),
    (float)(area->bottom-area->top)),D2D1_ANTIALIAS_MODE_ALIASED);
  s->dc_target->DrawBitmap(bitmap,D2D1::RectF(x,y,x+display_width,y+display_height));
  if(selected) {
    s->dc_brush->SetColor(D2D1::ColorF(theme_of(dark).accent));
    auto old=s->dc_target->GetAntialiasMode();
    s->dc_target->SetAntialiasMode(D2D1_ANTIALIAS_MODE_ALIASED);
    s->dc_target->DrawRectangle(D2D1::RectF(std::floor(x)+.5f,std::floor(y)+.5f,
      std::ceil(x+display_width)-.5f,std::ceil(y+display_height)-.5f),s->dc_brush,1.f);
    s->dc_target->SetAntialiasMode(old);
  }
  s->dc_target->PopAxisAlignedClip();hr=s->dc_target->EndDraw();bitmap->Release();
  if(hr==D2DERR_RECREATE_TARGET) {drop_dc_target(s);return S_FALSE;}
  return hr;
}

/* One floating surface for every popup (settings, notes, footnotes, dictionary):
   the caller's pixels beneath, shadow-lg, a radius-14 surface with a line
   border, then the caller's static text. Label boxes are DIPs from the visible
   surface's top-left corner; a width of 0 runs to the right padding. */
extern "C" HRESULT shell_d2d_surface(shell_d2d *s,HDC dc,const RECT *box,int dark,const uint32_t *background,
                                     const shell_d2d_label *labels,int count) {
  HRESULT hr=bind_dc(s,dc,box); if(FAILED(hr)) return hr;
  const auto &c=theme_of(dark);
  float k=s->dpi/96.f,pad=(float)SHELL_SHADOW_PAD*k,top=(float)SHELL_SHADOW_TOP*k,w=(float)(box->right-box->left),h=(float)(box->bottom-box->top);
  auto shadow=shadow_bitmap(s,(unsigned)w,(unsigned)(h+pad-top),1);
  ID2D1Bitmap *underlay=nullptr;
  if(background) {
    auto props=D2D1::BitmapProperties(D2D1::PixelFormat(DXGI_FORMAT_B8G8R8A8_UNORM,D2D1_ALPHA_MODE_IGNORE));
    s->dc_target->CreateBitmap(D2D1::SizeU((UINT32)w,(UINT32)h),background,(UINT32)w*4,props,&underlay);
  }
  s->dc_target->BeginDraw(); s->dc_target->Clear(D2D1::ColorF(c.layer_page));
  if(underlay) { s->dc_target->DrawBitmap(underlay);underlay->Release(); }
  if(shadow) s->dc_target->DrawBitmap(shadow,D2D1::RectF(0,top-pad,w,h));
  const float radius=(float)SHELL_RADIUS*k;
  s->dc_brush->SetColor(D2D1::ColorF(c.layer_float));
  s->dc_target->FillRoundedRectangle(D2D1::RoundedRect(D2D1::RectF(pad,top,w-pad,h-pad),radius,radius),s->dc_brush);
  s->dc_brush->SetColor(D2D1::ColorF(shell_blend(c.layer_float,c.line_rgb,line_alpha(dark,SHELL_LINE_ALPHA))));
  s->dc_target->DrawRoundedRectangle(D2D1::RoundedRect(D2D1::RectF(pad+k/2,top+k/2,w-pad-k/2,h-pad-k/2),radius,radius),s->dc_brush,k);
  for(int i=0;i<count;i++) {
    const shell_d2d_label &label=labels[i];
    IDWriteTextFormat *format=s->format[label.style==SHELL_TEXT_TITLE ? SHELL_TEXT_TITLE : SHELL_TEXT_LABEL];
    float left=pad+label.x*k,right=label.width>0 ? left+label.width*k : w-pad-(float)SHELL_PANEL_PAD*k;
    s->dc_brush->SetColor(D2D1::ColorF(label.style==SHELL_TEXT_TITLE ? c.text : c.text_secondary));
    format->SetTextAlignment(DWRITE_TEXT_ALIGNMENT_LEADING);
    s->dc_target->DrawText(label.text,(UINT32)wcslen(label.text),format,
      D2D1::RectF(left,top+label.y*k,right,top+(label.y+label.height)*k),s->dc_brush);
  }
  hr=s->dc_target->EndDraw(); if(hr==D2DERR_RECREATE_TARGET) drop_dc_target(s); return hr;
}

/* DECKMARK-TOKENS buttons and the segmented control of ART-DIRECTION e-4. The
   DC target has no alpha, so every control first clears its box to look->under. */
extern "C" HRESULT shell_d2d_control(shell_d2d *s,HDC dc,const RECT *box,const wchar_t *text,int dark,const shell_d2d_look *look) {
  HRESULT hr=bind_dc(s,dc,box); if(FAILED(hr)) return hr;
  const auto &c=theme_of(dark);
  const float k=s->dpi/96.f,shadow_pad=(float)SHELL_SHADOW_PAD*k;
  const float w=(float)(box->right-box->left),h=(float)(box->bottom-box->top);
  const unsigned state=look->state;
  const bool disabled=(state&SHELL_STATE_DISABLED)!=0,hover=(state&SHELL_STATE_HOVER)!=0 && !disabled;
  const bool pressed=(state&SHELL_STATE_PRESSED)!=0 && !disabled,selected=(state&SHELL_STATE_SELECTED)!=0;
  const bool focus=(state&SHELL_STATE_FOCUS)!=0 && !disabled,segment=look->kind==SHELL_CONTROL_SEGMENT;
  const float opacity=disabled ? SHELL_DISABLED_ALPHA : 1.f;
  uint32_t under=look->under,fill=under,ink=c.text;
  bool filled=false,raised=false;
  D2D1_ROUNDED_RECT rect;
  s->dc_target->BeginDraw();s->dc_target->Clear(D2D1::ColorF(under));
  if(segment) {
    /* Each box draws the whole track, shifted, and so shows only its own slice. */
    const float pad=(float)SHELL_SEGMENT_PAD*k,radius=(float)SHELL_RADIUS_SM*k,left=-w*look->index,right=w*(look->count-look->index);
    s->dc_brush->SetColor(D2D1::ColorF(c.surface2));
    s->dc_target->FillRoundedRectangle(D2D1::RoundedRect(D2D1::RectF(left,0,right,h),radius,radius),s->dc_brush);
    s->dc_brush->SetColor(D2D1::ColorF(shell_blend(c.surface2,c.line_rgb,line_alpha(dark,SHELL_LINE_ALPHA))));
    s->dc_target->DrawRoundedRectangle(D2D1::RoundedRect(D2D1::RectF(left+k/2,k/2,right-k/2,h-k/2),radius,radius),s->dc_brush,k);
    under=c.surface2;fill=c.layer_float;filled=raised=selected;
    ink=selected || hover ? c.text : c.text_secondary;
    rect=D2D1::RoundedRect(D2D1::RectF(pad,pad,w-pad,h-pad),6*k,6*k);
  } else {
    const float pad=(float)SHELL_CONTROL_FRAME*k,dy=pressed ? (float)SHELL_PRESSED_Y*k : 0,radius=(float)SHELL_RADIUS_SM*k;
    rect=D2D1::RoundedRect(D2D1::RectF(pad,pad+dy,w-pad,h-pad+dy),radius,radius);
    if(look->kind==SHELL_CONTROL_GHOST) {
      filled=hover || pressed;fill=pressed ? c.surface3 : c.surface2;
      ink=filled ? c.text : c.text_secondary;
      if(selected) {
        if(!filled) fill=shell_blend(under,SHELL_ACCENT_SOFT_RGB,SHELL_ACCENT_SOFT_ALPHA);
        filled=true;ink=c.accent;
      }
    } else if(look->kind==SHELL_CONTROL_FIELD) {
      filled=true;fill=c.layer_float;
    } else if(look->kind==SHELL_CONTROL_PRIMARY) {
      filled=raised=true;fill=hover || pressed ? c.accent_hover : c.accent;ink=c.on_accent;
    } else {
      filled=raised=true;fill=hover || pressed ? c.surface2 : c.layer_float;
    }
  }
  const float rw=rect.rect.right-rect.rect.left,rh=rect.rect.bottom-rect.rect.top;
  if(raised) {
    auto shadow=shadow_bitmap(s,(unsigned)(rw+2*shadow_pad),(unsigned)(rh+2*shadow_pad),segment ? 2 : 0);
    if(shadow) s->dc_target->DrawBitmap(shadow,D2D1::RectF(rect.rect.left-shadow_pad,rect.rect.top-shadow_pad,
      rect.rect.right+shadow_pad,rect.rect.bottom+shadow_pad),opacity);
  }
  if(filled) {
    fill=shell_blend(under,fill,opacity);
    s->dc_brush->SetColor(D2D1::ColorF(fill));
    s->dc_target->FillRoundedRectangle(rect,s->dc_brush);
  } else fill=under;
  if(look->kind==SHELL_CONTROL_STANDARD || look->kind==SHELL_CONTROL_FIELD) {
    s->dc_brush->SetColor(D2D1::ColorF(shell_blend(fill,c.line_rgb,line_alpha(dark,SHELL_LINE_STRONG_ALPHA)*opacity)));
    auto border=rect;border.rect.left+=k/2;border.rect.top+=k/2;border.rect.right-=k/2;border.rect.bottom-=k/2;
    s->dc_target->DrawRoundedRectangle(border,s->dc_brush,k);
  } else if(look->kind==SHELL_CONTROL_PRIMARY) {
    /* inset 0 1px 0 rgba(255,255,255,.16) */
    s->dc_brush->SetColor(D2D1::ColorF(shell_blend(fill,0xffffff,SHELL_PRIMARY_HIGHLIGHT_ALPHA*opacity)));
    s->dc_target->DrawLine(D2D1::Point2F(rect.rect.left+rect.radiusX,rect.rect.top+k/2),
      D2D1::Point2F(rect.rect.right-rect.radiusX,rect.rect.top+k/2),s->dc_brush,k);
  }
  s->dc_brush->SetColor(D2D1::ColorF(shell_blend(fill,ink,opacity)));
  s->format[SHELL_TEXT_UI]->SetTextAlignment(DWRITE_TEXT_ALIGNMENT_CENTER);
  s->dc_target->DrawText(text,(UINT32)wcslen(text),s->format[SHELL_TEXT_UI],rect.rect,s->dc_brush);
  if(focus) {
    /* A segment keeps its ring inside the track; a button's sits in its frame. */
    const float stroke=(float)SHELL_FOCUS_STROKE*k,grow=segment ? -stroke/2 : stroke;
    auto ring=rect;ring.rect.left-=grow;ring.rect.top-=grow;ring.rect.right+=grow;ring.rect.bottom+=grow;
    s->dc_brush->SetColor(D2D1::ColorF(c.accent));s->dc_target->DrawRoundedRectangle(ring,s->dc_brush,stroke);
  }
  hr=s->dc_target->EndDraw();if(hr==D2DERR_RECREATE_TARGET) drop_dc_target(s);return hr;
}


extern "C" void shell_d2d_toc_clear(shell_d2d *s) {
  s->toc_labels.clear();s->toc_width=0;
  for(auto &entry:s->toc_rows) DeleteObject(entry.second.bitmap);
  s->toc_rows.clear();
  for(auto &font:s->toc_fonts) {if(font) DeleteObject(font);font=nullptr;}
}
static COLORREF toc_rgb(uint32_t c) {return RGB((c>>16)&255,(c>>8)&255,c&255);}

extern "C" HRESULT shell_d2d_toc_row(shell_d2d *s,HDC dc,const RECT *box,const wchar_t *text,
    int dark,unsigned state,int row,float size,unsigned weight,int align) {
  const auto &c=theme_of(dark);
  float k=s->dpi/96.f;int w=box->right-box->left,h=box->bottom-box->top;
  bool selected=(state&8)!=0;
  if(row>=0) {
    if(s->toc_width!=w) {shell_d2d_toc_clear(s);s->toc_width=w;}
    if(!s->toc_row_dc) s->toc_row_dc=CreateCompatibleDC(dc);
    if(!s->toc_row_dc) return E_OUTOFMEMORY;
    HDC output=dc;RECT destination=*box,local={0,0,w,h};
    unsigned bitmap_key=(unsigned)row*32+(state&15)+(dark ? 16:0);
    auto cached=s->toc_rows.find(bitmap_key);
    if(cached!=s->toc_rows.end()) {
      cached->second.used=++s->toc_tick;HGDIOBJ previous=SelectObject(s->toc_row_dc,cached->second.bitmap);
      BitBlt(output,destination.left,destination.top,w,h,s->toc_row_dc,0,0,SRCCOPY);
      SelectObject(s->toc_row_dc,previous);return S_OK;
    }
    /* Bound the raster cache to 64 rows (about 2.2 MiB at 96 DPI).
       Labels keep their one-time ellipsis result; new rows use the native font. */
    if(s->toc_rows.size()>=64) {
      auto oldest=std::min_element(s->toc_rows.begin(),s->toc_rows.end(),[](const auto &a,const auto &b){return a.second.used<b.second.used;});
      DeleteObject(oldest->second.bitmap);s->toc_rows.erase(oldest);
    }
    BITMAPINFO info={};void *bits=nullptr;info.bmiHeader.biSize=sizeof(BITMAPINFOHEADER);
    info.bmiHeader.biWidth=w;info.bmiHeader.biHeight=-h;info.bmiHeader.biPlanes=1;info.bmiHeader.biBitCount=32;
    HBITMAP bitmap=CreateDIBSection(dc,&info,DIB_RGB_COLORS,&bits,nullptr,0);if(!bitmap) return E_OUTOFMEMORY;
    HGDIOBJ previous=SelectObject(s->toc_row_dc,bitmap);dc=s->toc_row_dc;box=&local;
    HBRUSH background=CreateSolidBrush(toc_rgb(c.layer_side));FillRect(dc,&local,background);DeleteObject(background);
    int variant=selected ? 1:0;
    if(!s->toc_fonts[variant]) s->toc_fonts[variant]=CreateFontW(-(int)std::round(14*k),0,0,0,selected ? 600:400,
      FALSE,FALSE,FALSE,DEFAULT_CHARSET,OUT_DEFAULT_PRECIS,CLIP_DEFAULT_PRECIS,ANTIALIASED_QUALITY,DEFAULT_PITCH,s->family[SHELL_TEXT_UI]);
    if(!s->toc_fonts[variant]) return E_OUTOFMEMORY;
    int saved=SaveDC(dc);IntersectClipRect(dc,box->left,box->top,box->right,box->bottom);
    SetViewportOrgEx(dc,box->left,box->top,nullptr);
    HGDIOBJ old=SelectObject(dc,s->toc_fonts[variant]);SetBkMode(dc,TRANSPARENT);SetTextColor(dc,toc_rgb(c.text));
    int pad=(int)(std::round(20*k)-std::round(10*k));
    unsigned key=(unsigned)row*2+(selected ? 1u:0u);
    auto it=s->toc_labels.find(key);
    if(it==s->toc_labels.end()) {
      std::wstring label=text;SIZE extent={};GetTextExtentPoint32W(dc,label.data(),(int)label.size(),&extent);
      int available=w-(int)std::round(20*k);
      if(extent.cx>available) {
        SIZE ellipsis={};GetTextExtentPoint32W(dc,L"…",1,&ellipsis);
        int fit=0;GetTextExtentExPointW(dc,label.data(),(int)label.size(),std::max(0,available-(int)ellipsis.cx),&fit,nullptr,&extent);
        if(fit>0 && label[(size_t)fit-1]>=0xd800 && label[(size_t)fit-1]<=0xdbff) fit--;
        label.resize((size_t)fit);label+=L"…";
      }
      it=s->toc_labels.emplace(key,std::move(label)).first;
    }
    uint32_t fill=selected ? (dark==2 ? c.surface3 : dark ? ((state&2) ? 0x2d2f45:0x262835):((state&2) ? 0xeceefc:0xf4f5fd)):
      (state&2) ? c.surface3:(state&1) ? c.surface2:c.layer_side;
    int radius=(int)std::round(9*k);HRGN rounded=CreateRoundRectRgn(0,0,w+1,h+1,2*radius,2*radius);
    HBRUSH brush=CreateSolidBrush(toc_rgb(fill));FillRgn(dc,rounded,brush);DeleteObject(brush);
    if(selected || (state&4)) {
      brush=CreateSolidBrush(toc_rgb(c.accent));
      if(selected) {int clip=SaveDC(dc);ExtSelectClipRgn(dc,rounded,RGN_AND);RECT stripe={0,0,(LONG)std::round(2*k),h};FillRect(dc,&stripe,brush);RestoreDC(dc,clip);}
      if(state&4) FrameRgn(dc,rounded,brush,(int)std::round(2*k),(int)std::round(2*k));
      DeleteObject(brush);
    }
    RECT labelbox={pad,0,w-(int)std::round(10*k),h};
    DrawTextW(dc,it->second.data(),(int)it->second.size(),&labelbox,DT_SINGLELINE|DT_VCENTER|DT_NOPREFIX);
    if(selected) {LOGFONTW actual={};GetObjectW(s->toc_fonts[variant],sizeof(actual),&actual);s->toc_metrics[2]=(float)-actual.lfHeight;s->toc_metrics[3]=(float)actual.lfWeight;}
    DeleteObject(rounded);SelectObject(dc,old);RestoreDC(dc,saved);
    BitBlt(output,destination.left,destination.top,w,h,dc,0,0,SRCCOPY);SelectObject(dc,previous);
    s->toc_rows.emplace(bitmap_key,toc_row_cache{bitmap,++s->toc_tick});return S_OK;
  }
  HRESULT hr=bind_dc(s,dc,box);if(FAILED(hr)) return hr;
  IDWriteTextFormat *format=nullptr;IDWriteTextLayout *layout=nullptr;
  hr=s->write->CreateTextFormat(s->family[SHELL_TEXT_UI],nullptr,(DWRITE_FONT_WEIGHT)weight,DWRITE_FONT_STYLE_NORMAL,
    DWRITE_FONT_STRETCH_NORMAL,size*k,L"zh-cn",&format);if(FAILED(hr)) return hr;
  format->SetWordWrapping(row==-4 ? DWRITE_WORD_WRAPPING_WRAP:DWRITE_WORD_WRAPPING_NO_WRAP);
  format->SetTextAlignment((DWRITE_TEXT_ALIGNMENT)align);
  format->SetParagraphAlignment(row==-4 ? DWRITE_PARAGRAPH_ALIGNMENT_NEAR:DWRITE_PARAGRAPH_ALIGNMENT_CENTER);
  if(row==-4) format->SetLineSpacing(DWRITE_LINE_SPACING_METHOD_UNIFORM,22.4f*k,15.4f*k);
  hr=s->write->CreateTextLayout(text,(UINT32)wcslen(text),format,(float)w,(float)h,&layout);
  if(SUCCEEDED(hr) && row==-3) {s->toc_metrics[0]=format->GetFontSize();s->toc_metrics[1]=(float)format->GetFontWeight();}
  format->Release();if(FAILED(hr)) return hr;
  IDWriteTypography *numbers=nullptr;
  if(SUCCEEDED(s->write->CreateTypography(&numbers))) {numbers->AddFontFeature({DWRITE_FONT_FEATURE_TAG_TABULAR_FIGURES,1});layout->SetTypography(numbers,{0,(UINT32)wcslen(text)});numbers->Release();}
  s->dc_target->BeginDraw();s->dc_target->Clear(D2D1::ColorF(c.layer_side));
  s->dc_brush->SetColor(D2D1::ColorF(row==-1 || row==-4 ? c.text_secondary:row==-2 ? c.text_disabled:c.text));
  s->dc_target->DrawTextLayout(D2D1::Point2F(0,0),layout,s->dc_brush,D2D1_DRAW_TEXT_OPTIONS_CLIP);layout->Release();
  hr=s->dc_target->EndDraw();if(hr==D2DERR_RECREATE_TARGET) drop_dc_target(s);return hr;
}
extern "C" HRESULT shell_d2d_toc_begin(shell_d2d *,HDC dc,const RECT *box,int dark) {
  HBRUSH brush=CreateSolidBrush(toc_rgb(theme_of(dark).layer_side));
  FillRect(dc,box,brush);DeleteObject(brush);return S_OK;
}
extern "C" HRESULT shell_d2d_toc_end(shell_d2d *) {return S_OK;}
extern "C" void shell_d2d_toc_metrics(shell_d2d *s,float values[4]) {for(int i=0;i<4;i++) values[i]=s->toc_metrics[i];}
