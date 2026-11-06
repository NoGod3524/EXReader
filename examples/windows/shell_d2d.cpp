/* SPDX-License-Identifier: MIT */
#include "shell_d2d.h"
#include <d2d1.h>
#include <dwrite.h>
#include <cwchar>
#include <new>

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
  static const wchar_t *const title[] = {L"Segoe UI Variable Text", L"Segoe UI"};
  static const wchar_t *const icon[] = {L"Segoe Fluent Icons", L"Segoe MDL2 Assets"};
  const bool is_title = style == SHELL_TEXT_TITLE;
  const bool is_icon = style == SHELL_TEXT_ICON;
  const wchar_t *name = is_icon ? icon[1] : title[1];
  IDWriteFontFamily *family = find_family(shell, is_icon ? icon : title, 2, &name);
  if (family) family->Release();
  IDWriteTextFormat *format = nullptr;
  HRESULT hr = shell->write->CreateTextFormat(name, nullptr,
                                              is_title ? DWRITE_FONT_WEIGHT_SEMI_BOLD : DWRITE_FONT_WEIGHT_NORMAL,
                                              DWRITE_FONT_STYLE_NORMAL, DWRITE_FONT_STRETCH_NORMAL,
                                              (is_title ? 17.0f : is_icon ? 20.0f : 13.0f) * shell->dpi / 96.0f, L"zh-cn", &format);
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
  const D2D1_POINT_2F centre = D2D1::Point2F(width / 2, height / 2);
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
