/* SPDX-License-Identifier: MIT */
#include "shell_d2d.h"
#include <d2d1.h>
#include <new>

struct shell_d2d {
  HWND window;
  ID2D1Factory *factory;
  ID2D1HwndRenderTarget *target;
  ID2D1SolidColorBrush *brush;
  unsigned recreated;
};

static void drop_target(shell_d2d *shell) {
  if (shell->brush) { shell->brush->Release(); shell->brush = nullptr; }
  if (shell->target) { shell->target->Release(); shell->target = nullptr; }
}

extern "C" HRESULT shell_d2d_create(HWND window, shell_d2d **out) {
  *out = nullptr;
  shell_d2d *shell = new (std::nothrow) shell_d2d();
  if (!shell) return E_OUTOFMEMORY;
  shell->window = window;
  HRESULT hr = D2D1CreateFactory(D2D1_FACTORY_TYPE_SINGLE_THREADED, &shell->factory);
  if (FAILED(hr)) { delete shell; return hr; }
  *out = shell;
  return S_OK;
}

extern "C" void shell_d2d_destroy(shell_d2d *shell) {
  if (!shell) return;
  drop_target(shell);
  if (shell->factory) shell->factory->Release();
  delete shell;
}

extern "C" HRESULT shell_d2d_resize(shell_d2d *shell, UINT width, UINT height) {
  return shell->target ? shell->target->Resize(D2D1::SizeU(width, height)) : S_OK;
}

extern "C" HRESULT shell_d2d_begin(shell_d2d *shell, uint32_t background) {
  if (!shell->target) {
    RECT area;
    GetClientRect(shell->window, &area);
    D2D1_SIZE_U size = D2D1::SizeU((UINT32)(area.right - area.left), (UINT32)(area.bottom - area.top));
    HRESULT hr = shell->factory->CreateHwndRenderTarget(D2D1::RenderTargetProperties(),
                                                        D2D1::HwndRenderTargetProperties(shell->window, size),
                                                        &shell->target);
    if (SUCCEEDED(hr)) hr = shell->target->CreateSolidColorBrush(D2D1::ColorF(background), &shell->brush);
    if (FAILED(hr)) { drop_target(shell); return hr; }
  }
  shell->target->BeginDraw();
  shell->target->Clear(D2D1::ColorF(background));
  return S_OK;
}

extern "C" void shell_d2d_fill(shell_d2d *shell, float x, float y, float width, float height, uint32_t color) {
  shell->brush->SetColor(D2D1::ColorF(color));
  shell->target->FillRectangle(D2D1::RectF(x, y, x + width, y + height), shell->brush);
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
