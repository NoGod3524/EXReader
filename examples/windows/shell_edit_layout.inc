/* SPDX-License-Identifier: MIT */
/* DirectWrite owns shaping, fallback, bidi and empty-line geometry. The host
   owns input/transactions and keeps the exact model byte stream separately. */
struct shell_edit_view { IDWriteTextLayout *layout; unsigned length; };

extern "C" HRESULT shell_edit_view_create(shell_d2d *s, const wchar_t *text, unsigned length,
  const wchar_t *family, float size, float width, shell_edit_view **out) {
  *out = nullptr;
  if (!s || !s->write || !text || size <= 0 || width <= 0) return E_INVALIDARG;
  IDWriteTextFormat *format = nullptr;
  HRESULT hr = s->write->CreateTextFormat(family && *family ? family : L"Microsoft YaHei",
    nullptr, DWRITE_FONT_WEIGHT_NORMAL, DWRITE_FONT_STYLE_NORMAL,
    DWRITE_FONT_STRETCH_NORMAL, size, L"zh-cn", &format);
  if (FAILED(hr)) return hr;
  format->SetWordWrapping(DWRITE_WORD_WRAPPING_WRAP);
  format->SetLineSpacing(DWRITE_LINE_SPACING_METHOD_UNIFORM, size*1.75f, size*1.3f);
  shell_edit_view *v = new(std::nothrow) shell_edit_view{};
  if (!v) { format->Release(); return E_OUTOFMEMORY; }
  hr = s->write->CreateTextLayout(text, length, format, width, 10000000.0f, &v->layout);
  format->Release();
  if (FAILED(hr)) { delete v; return hr; }
  v->length = length; *out = v; return S_OK;
}
extern "C" void shell_edit_view_free(shell_edit_view *v) {
  if (v) { v->layout->Release(); delete v; }
}
extern "C" unsigned shell_edit_view_hit(shell_edit_view *v, float x, float y) {
  BOOL trailing = FALSE, inside = FALSE; DWRITE_HIT_TEST_METRICS hit{};
  if (!v || FAILED(v->layout->HitTestPoint(x,y,&trailing,&inside,&hit))) return 0;
  return std::min(v->length,hit.textPosition+(trailing ? hit.length : 0));
}
extern "C" HRESULT shell_edit_view_caret(shell_edit_view *v, unsigned position, float box[4]) {
  DWRITE_HIT_TEST_METRICS hit{}; float x=0, y=0;
  if (!v) return E_INVALIDARG;
  HRESULT hr=v->layout->HitTestTextPosition(std::min(position,v->length),FALSE,&x,&y,&hit);
  box[0]=x; box[1]=y; box[2]=1; box[3]=hit.height;
  return hr;
}
extern "C" unsigned shell_edit_view_line_edge(shell_edit_view *v, unsigned position, int end) {
  if (!v) return 0;
  UINT32 count=0;
  v->layout->GetLineMetrics(nullptr,0,&count);
  std::vector<DWRITE_LINE_METRICS> lines(count);
  if (FAILED(v->layout->GetLineMetrics(lines.data(),count,&count))) return position;
  unsigned start=0;
  for (const auto &line:lines) {
    unsigned next=start+line.length;
    if (position<next || &line==&lines.back())
      return end ? next-line.newlineLength : start;
    start=next;
  }
  return position;
}
extern "C" float shell_edit_view_height(shell_edit_view *v) {
  DWRITE_TEXT_METRICS m{};
  return v && SUCCEEDED(v->layout->GetMetrics(&m)) ? m.height : 0;
}
extern "C" HRESULT shell_edit_view_paint(shell_d2d *s, shell_edit_view *v, HDC dc,
  const RECT *area, float left, float top, unsigned start, unsigned end,
  uint32_t paper, uint32_t ink, uint32_t accent) {
  if (!s || !v || !dc || !area) return E_INVALIDARG;
  /* Use the same unioned region highlight as reading selection; text is drawn
     over the fill so CJK and anti-aliased ink keep their original coverage. */
  if (start<end) {
    UINT32 count=0;
    v->layout->HitTestTextRange(start,end-start,left,top,nullptr,0,&count);
    std::vector<DWRITE_HIT_TEST_METRICS> hits(count);
    if (SUCCEEDED(v->layout->HitTestTextRange(start,end-start,left,top,hits.data(),count,&count))) {
      HRGN region=CreateRectRgn(0,0,0,0);
      for (const auto &hit:hits) shell_highlight_rect(region,hit.left,hit.top,hit.width,hit.height);
      HBRUSH brush=CreateSolidBrush(RGB((accent>>16)&255,(accent>>8)&255,accent&255));
      FillRgn(dc,region,brush); DeleteObject(brush); DeleteObject(region);
    }
  }
  /* A DC target is shared with owner-drawn controls; BindDC must be refreshed. */
  if (!s->dc_target) {
    D2D1_RENDER_TARGET_PROPERTIES props=D2D1::RenderTargetProperties(
      D2D1_RENDER_TARGET_TYPE_DEFAULT,D2D1::PixelFormat(DXGI_FORMAT_B8G8R8A8_UNORM,D2D1_ALPHA_MODE_IGNORE));
    props.dpiX=props.dpiY=96;
    HRESULT hr=s->factory->CreateDCRenderTarget(&props,&s->dc_target);
    if (FAILED(hr)) return hr;
  }
  HRESULT hr=s->dc_target->BindDC(dc,area);
  if (FAILED(hr)) return hr;
  if (!s->dc_brush) {
    hr=s->dc_target->CreateSolidColorBrush(D2D1::ColorF(ink),&s->dc_brush);
    if (FAILED(hr)) return hr;
  }
  (void)paper;
  s->dc_brush->SetColor(D2D1::ColorF(ink));
  s->dc_target->BeginDraw();
  s->dc_target->SetTransform(D2D1::Matrix3x2F::Identity());
  s->dc_target->DrawTextLayout(D2D1::Point2F(left-area->left,top-area->top),v->layout,s->dc_brush,D2D1_DRAW_TEXT_OPTIONS_CLIP);
  hr=s->dc_target->EndDraw();
  if (hr==D2DERR_RECREATE_TARGET) {
    s->dc_brush->Release(); s->dc_brush=nullptr;
    s->dc_target->Release(); s->dc_target=nullptr;
  }
  return hr;
}
