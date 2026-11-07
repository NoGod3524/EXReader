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

struct shadow_cache { unsigned width,height,dpi; int kind; ID2D1Bitmap *bitmap; };
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

  const bool is_title = style == SHELL_TEXT_TITLE;
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
  format->SetTextAlignment(is_title ? DWRITE_TEXT_ALIGNMENT_LEADING : DWRITE_TEXT_ALIGNMENT_CENTER);
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

extern "C" HRESULT shell_d2d_dc_text(shell_d2d *shell, HDC dc, const RECT *box, const wchar_t *text, uint32_t current, uint32_t rest) {
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
  const wchar_t *separator=wcschr(text,L' ');
  ID2D1SolidColorBrush *muted=nullptr;
  if(SUCCEEDED(hr)) hr=shell->dc_target->CreateSolidColorBrush(D2D1::ColorF(rest),&muted);
  if(SUCCEEDED(hr) && separator) hr=layout->SetDrawingEffect(muted,{(UINT32)(separator-text),length-(UINT32)(separator-text)});
  if(FAILED(hr)) { if(muted) muted->Release();layout->Release();return hr; }
  DWRITE_OVERHANG_METRICS ink={};
  hr=layout->GetOverhangMetrics(&ink);
  if(FAILED(hr)) {muted->Release();layout->Release();return hr;}
  shell->dc_target->BeginDraw();
  shell->dc_brush->SetColor(D2D1::ColorF(current));
  shell->dc_target->DrawTextLayout(D2D1::Point2F(0,(ink.top-ink.bottom)/2),layout,shell->dc_brush);
  muted->Release();layout->Release();
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

extern "C" HRESULT shell_d2d_panel(shell_d2d *s,HDC dc,const RECT *box,int dark,const wchar_t *font,const uint32_t *background) {
  HRESULT hr=bind_dc(s,dc,box); if(FAILED(hr)) return hr;
  const auto &c=dark ? shell_theme_dark : shell_theme_light;
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
  s->dc_brush->SetColor(D2D1::ColorF(c.layer_float));
  s->dc_target->FillRoundedRectangle(D2D1::RoundedRect(D2D1::RectF(pad,top,w-pad,h-pad),(float)SHELL_RADIUS*k,(float)SHELL_RADIUS*k),s->dc_brush);
  auto border=D2D1::RoundedRect(D2D1::RectF(pad+k/2,top+k/2,w-pad-k/2,h-pad-k/2),14*k,14*k);
  s->dc_brush->SetColor(D2D1::ColorF(shell_blend(c.layer_float,c.line_rgb,SHELL_LINE_ALPHA)));
  s->dc_target->DrawRoundedRectangle(border,s->dc_brush,k);
  auto track=D2D1::RoundedRect(D2D1::RectF(pad+20*k,top+118*k,pad+204*k,top+152*k),9*k,9*k);
  s->dc_brush->SetColor(D2D1::ColorF(c.surface2));s->dc_target->FillRoundedRectangle(track,s->dc_brush);
  s->dc_brush->SetColor(D2D1::ColorF(shell_blend(c.surface2,c.line_rgb,SHELL_LINE_ALPHA)));
  track.rect.left+=k/2;track.rect.top+=k/2;track.rect.right-=k/2;track.rect.bottom-=k/2;
  s->dc_target->DrawRoundedRectangle(track,s->dc_brush,k);
  s->dc_brush->SetColor(D2D1::ColorF(c.text_secondary));
  s->format[SHELL_TEXT_LABEL]->SetTextAlignment(DWRITE_TEXT_ALIGNMENT_LEADING);
  s->dc_target->DrawText(L"字号",2,s->format[SHELL_TEXT_LABEL],D2D1::RectF(pad+20*k,top+20*k,w-pad-20*k,top+36*k),s->dc_brush);
  s->dc_target->DrawText(L"主题",2,s->format[SHELL_TEXT_LABEL],D2D1::RectF(pad+20*k,top+94*k,w-pad-20*k,top+110*k),s->dc_brush);
  s->dc_brush->SetColor(D2D1::ColorF(c.text));
  IDWriteTextLayout *value=nullptr; IDWriteTypography *typography=nullptr;
  if(SUCCEEDED(s->write->CreateTextLayout(font,(UINT32)wcslen(font),s->format[SHELL_TEXT_UI],54*k,34*k,&value))) {
    if(SUCCEEDED(s->write->CreateTypography(&typography))) {
      typography->AddFontFeature({DWRITE_FONT_FEATURE_TAG_TABULAR_FIGURES,1});
      value->SetTypography(typography,{0,(UINT32)wcslen(font)});typography->Release();
    }
    s->dc_target->DrawTextLayout(D2D1::Point2F(pad+153*k,top+44*k),value,s->dc_brush);value->Release();
  }
  hr=s->dc_target->EndDraw(); if(hr==D2DERR_RECREATE_TARGET) drop_dc_target(s); return hr;
}

extern "C" HRESULT shell_d2d_control(shell_d2d *s,HDC dc,const RECT *box,const wchar_t *text,int dark,int variant,unsigned state) {
  HRESULT hr=bind_dc(s,dc,box); if(FAILED(hr)) return hr;
  const auto &c=dark ? shell_theme_dark : shell_theme_light;
  const float k=s->dpi/96.f,pad=(float)(variant ? SHELL_SEGMENT_PAD : SHELL_CONTROL_FRAME)*k;
  const float px=variant ? 0 : pad,shadow_pad=(float)SHELL_SHADOW_PAD*k;
  float w=(float)(box->right-box->left),h=(float)(box->bottom-box->top);
  bool disabled=(state&8)!=0,hover=(state&1)!=0 && !disabled;
  float opacity=disabled ? SHELL_DISABLED_ALPHA : 1.f;
  float dy=variant ? 0 : (state&2) && !disabled ? (float)SHELL_PRESSED_Y*k : 0;
  uint32_t base=variant ? c.surface2 : c.layer_float;
  uint32_t fill=variant==1 ? c.layer_float : variant==2 ? c.surface2 : hover ? c.surface2 : c.layer_float;
  if((state&2) && !disabled) fill=c.surface3;
  uint32_t ink=variant==2 && !hover ? c.text_secondary : c.text;
  auto rect=D2D1::RoundedRect(D2D1::RectF(variant ? 0 : pad,pad+dy,variant ? w : w-pad,h-pad+dy),(variant ? 6.f : (float)SHELL_RADIUS_SM)*k,(variant ? 6.f : (float)SHELL_RADIUS_SM)*k);
  auto shadow=variant!=2 ? shadow_bitmap(s,(unsigned)(w-2*px+2*shadow_pad),(unsigned)(h-2*pad+2*shadow_pad),variant ? 2 : 0) : nullptr;
  s->dc_target->BeginDraw();s->dc_target->Clear(D2D1::ColorF(base));
  if(shadow) s->dc_target->DrawBitmap(shadow,D2D1::RectF(px-shadow_pad,pad+dy-shadow_pad,w-px+shadow_pad,h-pad+dy+shadow_pad),opacity);
  s->dc_brush->SetColor(D2D1::ColorF(shell_blend(base,fill,opacity)));
  s->dc_target->FillRoundedRectangle(rect,s->dc_brush);
  if(variant==0) {
    s->dc_brush->SetColor(D2D1::ColorF(shell_blend(fill,c.line_rgb,SHELL_LINE_STRONG_ALPHA*opacity)));
    auto border=rect;border.rect.left+=k/2;border.rect.top+=k/2;border.rect.right-=k/2;border.rect.bottom-=k/2;
    s->dc_target->DrawRoundedRectangle(border,s->dc_brush,k);
  }

  s->dc_brush->SetColor(D2D1::ColorF(shell_blend(base,ink,opacity)));
  s->dc_target->DrawText(text,(UINT32)wcslen(text),s->format[SHELL_TEXT_UI],rect.rect,s->dc_brush);
  if((state&4) && !disabled) {
    auto ring=rect;ring.rect.left-=(float)SHELL_FOCUS_STROKE*k;ring.rect.top-=(float)SHELL_FOCUS_STROKE*k;
    ring.rect.right+=(float)SHELL_FOCUS_STROKE*k;ring.rect.bottom+=(float)SHELL_FOCUS_STROKE*k;
    s->dc_brush->SetColor(D2D1::ColorF(c.accent));s->dc_target->DrawRoundedRectangle(ring,s->dc_brush,(float)SHELL_FOCUS_STROKE*k);
  }
  hr=s->dc_target->EndDraw();if(hr==D2DERR_RECREATE_TARGET) drop_dc_target(s);return hr;
}
