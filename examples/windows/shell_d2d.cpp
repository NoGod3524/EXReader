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
                                              (DWRITE_FONT_WEIGHT)(is_title ? SHELL_TITLE_WEIGHT : style == SHELL_TEXT_UI ? SHELL_CONTROL_WEIGHT : (int)DWRITE_FONT_WEIGHT_NORMAL),
                                              DWRITE_FONT_STYLE_NORMAL, DWRITE_FONT_STRETCH_NORMAL,
                                              (float)(is_title ? SHELL_TITLE_FONT : is_icon ? SHELL_ICON_FONT : style == SHELL_TEXT_UI ? SHELL_UI_FONT : SHELL_PAGE_FONT) * shell->dpi / 96.0f, L"zh-cn", &format);
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
  shell->target->DrawText(text, (UINT32)wcslen(text), shell->format[style], D2D1::RectF(x, y, x + width, y + height),
                          shell->brush);
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
  const wchar_t text[2] = {glyph, 0};
  shell->dc_target->BeginDraw();
  shell->dc_target->Clear(D2D1::ColorF(look->background));
  if (look->has_fill) {
    shell->dc_brush->SetColor(D2D1::ColorF(look->fill));
    shell->dc_target->FillEllipse(D2D1::Ellipse(centre, radius, radius), shell->dc_brush);
  }
  shell->dc_brush->SetColor(D2D1::ColorF(look->icon));
  shell->dc_target->DrawText(text, 1, shell->format[SHELL_TEXT_ICON],
                             D2D1::RectF(centre.x - radius, centre.y - radius, centre.x + radius, centre.y + radius),
                             shell->dc_brush);
  if (look->has_ring) {
    const float ring = radius + look->ring_width / 2;
    shell->dc_brush->SetColor(D2D1::ColorF(look->ring));
    shell->dc_target->DrawEllipse(D2D1::Ellipse(centre, ring, ring), shell->dc_brush, look->ring_width);
  }
  hr = shell->dc_target->EndDraw();
  if (hr == D2DERR_RECREATE_TARGET) { drop_dc_target(shell); shell->recreated++; return S_FALSE; }
  return hr;
}

extern "C" HRESULT shell_d2d_dc_text(shell_d2d *shell, HDC dc, const RECT *box, const wchar_t *text, uint32_t color) {
  if (!shell->dc_target) {
    const D2D1_RENDER_TARGET_PROPERTIES properties =
      pixel_properties(D2D1::PixelFormat(DXGI_FORMAT_B8G8R8A8_UNORM, D2D1_ALPHA_MODE_IGNORE));
    HRESULT hr = shell->factory->CreateDCRenderTarget(&properties, &shell->dc_target);
    if (SUCCEEDED(hr)) hr = shell->dc_target->CreateSolidColorBrush(D2D1::ColorF(color), &shell->dc_brush);
    if (FAILED(hr)) { drop_dc_target(shell); return hr; }
    shell->dc_target->SetTextAntialiasMode(D2D1_TEXT_ANTIALIAS_MODE_GRAYSCALE);
  }
  HRESULT hr = shell->dc_target->BindDC(dc, box);
  if (FAILED(hr)) return hr;
  shell->dc_target->BeginDraw();
  shell->dc_brush->SetColor(D2D1::ColorF(color));
  shell->dc_target->DrawText(text, (UINT32)wcslen(text), shell->format[SHELL_TEXT_PAGE_NUMBER],
    D2D1::RectF(0, 0, (float)(box->right - box->left), (float)(box->bottom - box->top)), shell->dc_brush);
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
  const float radius=(float)(kind ? SHELL_RADIUS : SHELL_RADIUS_SM)*scale;
  const auto *layers=kind ? SHELL_SHADOW_MD : SHELL_SHADOW_SM;
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
    for(int i=-reach;i<=reach;i++) { float v=std::exp(-i*i/(2*sigma*sigma));kernel[i+reach]=v;sum+=v; }
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

extern "C" HRESULT shell_d2d_panel(shell_d2d *s,HDC dc,const RECT *box,int dark,const wchar_t *font,const uint32_t *background) {
  HRESULT hr=bind_dc(s,dc,box); if(FAILED(hr)) return hr;
  const auto &c=dark ? shell_theme_dark : shell_theme_light;
  float k=s->dpi/96.f,pad=(float)SHELL_SHADOW_PAD*k,w=(float)(box->right-box->left),h=(float)(box->bottom-box->top);
  auto shadow=shadow_bitmap(s,(unsigned)w,(unsigned)h,1);
  ID2D1Bitmap *underlay=nullptr;
  if(background) {
    auto props=D2D1::BitmapProperties(D2D1::PixelFormat(DXGI_FORMAT_B8G8R8A8_UNORM,D2D1_ALPHA_MODE_IGNORE));
    s->dc_target->CreateBitmap(D2D1::SizeU((UINT32)w,(UINT32)h),background,(UINT32)w*4,props,&underlay);
  }
  s->dc_target->BeginDraw(); s->dc_target->Clear(D2D1::ColorF(c.layer_page));
  if(underlay) { s->dc_target->DrawBitmap(underlay);underlay->Release(); }
  if(shadow) s->dc_target->DrawBitmap(shadow);
  s->dc_brush->SetColor(D2D1::ColorF(c.layer_float));
  s->dc_target->FillRoundedRectangle(D2D1::RoundedRect(D2D1::RectF(pad,pad,w-pad,h-pad),(float)SHELL_RADIUS*k,(float)SHELL_RADIUS*k),s->dc_brush);
  s->dc_brush->SetColor(D2D1::ColorF(c.text));
  s->format[SHELL_TEXT_UI]->SetTextAlignment(DWRITE_TEXT_ALIGNMENT_LEADING);
  s->dc_target->DrawText(L"字号",2,s->format[SHELL_TEXT_UI],D2D1::RectF(pad+(float)SHELL_SPACE_3*k,pad+(float)SHELL_SPACE_2*k,w-pad,pad+(float)SHELL_SPACE_5*k),s->dc_brush);
  s->dc_target->DrawText(L"主题",2,s->format[SHELL_TEXT_UI],D2D1::RectF(pad+(float)SHELL_SPACE_3*k,pad+(float)SHELL_SPACE_5*k*2,w-pad,pad+(SHELL_SPACE_5*2+SHELL_SPACE_4)*k),s->dc_brush);
  s->format[SHELL_TEXT_UI]->SetTextAlignment(DWRITE_TEXT_ALIGNMENT_CENTER);
  s->dc_target->DrawText(font,(UINT32)wcslen(font),s->format[SHELL_TEXT_UI],D2D1::RectF(pad+(float)SHELL_SPACE_5*k*2,pad+(float)SHELL_SPACE_5*k,w-pad-(float)SHELL_SPACE_5*k*2,pad+(SHELL_SPACE_5+SHELL_CONTROL_H)*k),s->dc_brush);
  hr=s->dc_target->EndDraw(); if(hr==D2DERR_RECREATE_TARGET) drop_dc_target(s); return hr;
}

extern "C" HRESULT shell_d2d_control(shell_d2d *s,HDC dc,const RECT *box,const wchar_t *text,int dark,int variant,unsigned state) {
  HRESULT hr=bind_dc(s,dc,box); if(FAILED(hr)) return hr;
  const auto &c=dark ? shell_theme_dark : shell_theme_light;
  const float k=s->dpi/96.f,pad=(float)SHELL_CONTROL_FRAME*k;
  float w=(float)(box->right-box->left),h=(float)(box->bottom-box->top);
  bool disabled=(state&8)!=0,hover=(state&1)!=0 && !disabled;
  float opacity=disabled ? SHELL_DISABLED_ALPHA : 1.f;
  float dy=(state&2) && !disabled ? (float)SHELL_PRESSED_Y*k : 0;
  uint32_t fill=variant==1 ? (hover ? c.accent_hover : c.accent) : hover ? c.surface2 : c.layer_float;
  uint32_t ink=variant==1 ? c.on_accent : variant==2 ? c.text_secondary : c.text;
  auto rect=D2D1::RoundedRect(D2D1::RectF(pad,pad+dy,w-pad,h-pad+dy),(float)SHELL_RADIUS_SM*k,(float)SHELL_RADIUS_SM*k);
  auto shadow=variant!=2 ? shadow_bitmap(s,(unsigned)(w+2*(SHELL_SHADOW_PAD-SHELL_CONTROL_FRAME)*k),(unsigned)(h+2*(SHELL_SHADOW_PAD-SHELL_CONTROL_FRAME)*k),0) : nullptr;
  s->dc_target->BeginDraw();s->dc_target->Clear(D2D1::ColorF(c.layer_float));
  if(shadow) s->dc_target->DrawBitmap(shadow,D2D1::RectF(-(SHELL_SHADOW_PAD-SHELL_CONTROL_FRAME)*k,dy-(SHELL_SHADOW_PAD-SHELL_CONTROL_FRAME)*k,w+(SHELL_SHADOW_PAD-SHELL_CONTROL_FRAME)*k,h+dy+(SHELL_SHADOW_PAD-SHELL_CONTROL_FRAME)*k),opacity);
  s->dc_brush->SetColor(D2D1::ColorF(shell_blend(c.layer_float,fill,opacity)));
  s->dc_target->FillRoundedRectangle(rect,s->dc_brush);
  if(variant==0) {
    s->dc_brush->SetColor(D2D1::ColorF(shell_blend(fill,c.line_rgb,SHELL_LINE_STRONG_ALPHA*opacity)));
    auto border=rect;border.rect.left+=k/2;border.rect.top+=k/2;border.rect.right-=k/2;border.rect.bottom-=k/2;
    s->dc_target->DrawRoundedRectangle(border,s->dc_brush,k);
  }
  if(variant==1) {
    s->dc_brush->SetColor(D2D1::ColorF(c.on_accent,SHELL_PRIMARY_HIGHLIGHT_ALPHA*opacity));
    s->dc_target->DrawLine(D2D1::Point2F(pad+(float)SHELL_RADIUS_SM*k,pad+dy+k/2),D2D1::Point2F(w-pad-(float)SHELL_RADIUS_SM*k,pad+dy+k/2),s->dc_brush,k);
  }
  s->dc_brush->SetColor(D2D1::ColorF(shell_blend(c.layer_float,ink,opacity)));
  s->dc_target->DrawText(text,(UINT32)wcslen(text),s->format[SHELL_TEXT_UI],rect.rect,s->dc_brush);
  if((state&4) && !disabled) {
    auto ring=rect;ring.rect.left-=(float)SHELL_FOCUS_STROKE*k;ring.rect.top-=(float)SHELL_FOCUS_STROKE*k;
    ring.rect.right+=(float)SHELL_FOCUS_STROKE*k;ring.rect.bottom+=(float)SHELL_FOCUS_STROKE*k;
    s->dc_brush->SetColor(D2D1::ColorF(c.accent));s->dc_target->DrawRoundedRectangle(ring,s->dc_brush,(float)SHELL_FOCUS_STROKE*k);
  }
  hr=s->dc_target->EndDraw();if(hr==D2DERR_RECREATE_TARGET) drop_dc_target(s);return hr;
}
