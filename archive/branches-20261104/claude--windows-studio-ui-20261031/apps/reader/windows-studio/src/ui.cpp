// SPDX-License-Identifier: MIT
// EXReader Studio: a Direct2D/DirectWrite desktop client over the EXReader SDK.
// The window is immediate-mode: every paint rebuilds the hit regions it draws.
#include "engine.h"
#include <commctrl.h>
#include <commdlg.h>
#include <d2d1.h>
#include <dwmapi.h>
#include <dwrite.h>
#include <shellapi.h>
#include <shlobj.h>
#include <uiautomation.h>
#include <windowsx.h>
#include <algorithm>
#include <cmath>
#include <cstdio>
#include <ctime>

namespace {

// ------------------------------------------------------------------------
// Look

using Color = D2D1_COLOR_F;

Color Hex(uint32_t rgb, float alpha = 1.0f) {
  return D2D1::ColorF(((rgb >> 16) & 255) / 255.0f, ((rgb >> 8) & 255) / 255.0f, (rgb & 255) / 255.0f, alpha);
}
Color Alpha(Color c, float a) { c.a *= a; return c; }
Color Mix(Color a, Color b, float t) {
  return D2D1::ColorF(a.r + (b.r - a.r) * t, a.g + (b.g - a.g) * t, a.b + (b.b - a.b) * t, a.a + (b.a - a.a) * t);
}

struct Palette {
  Color window, sidebar, surface, hover, border, text, subtle, faint, accent, accentInk, accentSoft, shadow, field;
};

const Palette kLight = {
  Hex(0xF7F5F1), Hex(0xEFECE6), Hex(0xFFFFFF), Hex(0xE6E2DA), Hex(0xE2DED6), Hex(0x1D1B18), Hex(0x6E6A63),
  Hex(0xA29D94), Hex(0xC8582B), Hex(0xFFFFFF), Hex(0xC8582B, 0.12f), Hex(0x3A2A1A), Hex(0xE9E5DE),
};
const Palette kDark = {
  Hex(0x16171A), Hex(0x1D1E22), Hex(0x24252A), Hex(0x2C2D33), Hex(0x2F3036), Hex(0xEDEBE7), Hex(0x9C9993),
  Hex(0x6C6A66), Hex(0xEE8A55), Hex(0x1B1206), Hex(0xEE8A55, 0.16f), Hex(0x000000), Hex(0x2A2B30),
};

struct ReadingTheme {
  const wchar_t *name;
  uint32_t page, ink; // 0xRRGGBB
  uint32_t surround;
  bool dark;
};
const ReadingTheme kThemes[] = {
  {L"纸白", 0xFFFFFF, 0x1F1F1F, 0xECE9E3, false},
  {L"米黄", 0xF7EFDD, 0x4A3B2A, 0xE7DCC4, false},
  {L"护眼", 0xE4EDDA, 0x2D3A2A, 0xD0DCC3, false},
  {L"夜间", 0x1E1F22, 0xC9C6C0, 0x121315, true},
};
constexpr int kThemeCount = 4;
const float kSpacing[] = {1.4f, 1.65f, 1.95f};
const wchar_t *kSpacingName[] = {L"紧凑", L"适中", L"宽松"};

// Generated covers for books without one.
const uint32_t kCoverInks[][2] = {
  {0x2F4858, 0x33658A}, {0x6D2E46, 0xA26769}, {0x1F4E3D, 0x3E7C59}, {0x3D348B, 0x7678ED},
  {0x8C3B1B, 0xD17A22}, {0x264653, 0x2A9D8F}, {0x4A4E69, 0x9A8C98}, {0x5E2B7E, 0xB0548E},
};

// Segoe Fluent Icons / MDL2 code points.
constexpr wchar_t kIconLibrary = 0xE8F1, kIconRecent = 0xE81C, kIconHeart = 0xEB51, kIconHeartFill = 0xEB52,
                  kIconAdd = 0xE710, kIconBack = 0xE72B, kIconSearch = 0xE721, kIconMoon = 0xE708,
                  kIconSun = 0xE706, kIconLeft = 0xE76B, kIconRight = 0xE76C, kIconMinus = 0xE738,
                  kIconCheck = 0xE73E, kIconBook = 0xE736, kIconToc = 0xE8FD, kIconDelete = 0xE74D;

// Layout, in DIPs.
constexpr float kSidebar = 248, kHeader = 96, kPad = 40, kGap = 28, kTopBar = 56, kBottomBar = 52;

enum class View { Shelf, Reader };
enum class Filter { All, Recent, Favorites };

enum HotId {
  HotNone, HotNavAll, HotNavRecent, HotNavFavorites, HotImport, HotAppearance, HotBook, HotContinue,
  HotBack, HotStyle, HotFontDown, HotFontUp, HotSpacing, HotTheme, HotZoomDown, HotZoomUp, HotTrack,
  HotPrev, HotNext, HotPanel, HotSearch, HotToc, HotTocItem, HotTocPanel, HotConfirm, HotConfirmCancel,
  HotConfirmCard, HotConfirmShade, HotMenuItem, HotMenuCard,
  HotPageText, // not a hit region: the page's text as an accessible element
};

struct Hot {
  D2D1_RECT_F rect;
  HotId id;
  int64_t arg;
};

struct Book {
  BookItem item;
  double progress = -1; // 0..1 once opened here
  long long lastRead = 0;
};

struct Cover {
  Pixels pixels;
  ID2D1Bitmap *bitmap = nullptr;
  ID2D1BitmapBrush *brush = nullptr;
};

template <class T> void Release(T *&p) { if (p) { p->Release(); p = nullptr; } }

bool Inside(const D2D1_RECT_F &r, float x, float y) { return x >= r.left && x < r.right && y >= r.top && y < r.bottom; }
D2D1_RECT_F Rect(float x, float y, float w, float h) { return D2D1::RectF(x, y, x + w, y + h); }

class AccessRoot;
class AccessItem;

// One accessible element: a control the last paint drew, or the page text.
struct AccessNode {
  HotId id;
  int64_t arg;
  D2D1_RECT_F rect; // DIPs, client coordinates
  std::wstring name;
  CONTROLTYPEID type;
  bool invoke;
};

constexpr UINT WM_ACCESS_INVOKE = WM_APP + 41;
bool g_accessAlive = false;

class App {
  friend class AccessRoot;
  friend class AccessItem;

public:
  int run(HINSTANCE instance, int show);
  LRESULT handle(HWND hwnd, UINT message, WPARAM wparam, LPARAM lparam);

private:
  // Device and drawing primitives.
  bool ensureTarget();
  void discardDevice();
  IDWriteTextFormat *format(float size, DWRITE_FONT_WEIGHT weight, bool icon = false);
  void fill(const D2D1_RECT_F &r, Color c, float radius = 0);
  void stroke(const D2D1_RECT_F &r, Color c, float radius, float width = 1);
  void shadow(const D2D1_RECT_F &r, float radius, float strength);
  void text(const std::wstring &s, const D2D1_RECT_F &r, float size, DWRITE_FONT_WEIGHT weight, Color c,
            DWRITE_TEXT_ALIGNMENT align = DWRITE_TEXT_ALIGNMENT_LEADING,
            DWRITE_PARAGRAPH_ALIGNMENT valign = DWRITE_PARAGRAPH_ALIGNMENT_NEAR, bool wrap = false);
  void icon(wchar_t glyph, const D2D1_RECT_F &r, float size, Color c);
  float measure(const std::wstring &s, float size, DWRITE_FONT_WEIGHT weight);
  ID2D1Bitmap *bitmapFrom(const Pixels &pixels);
  void hot(const D2D1_RECT_F &r, HotId id, int64_t arg = 0) { hots_.push_back({r, id, arg}); }
  Hot hitTest(float x, float y) const {
    for (auto it = hots_.rbegin(); it != hots_.rend(); ++it)
      if (Inside(it->rect, x, y)) return *it;
    return {{}, HotNone, 0};
  }
  float hoverAmount(HotId id, int64_t arg = 0);

  // Painting.
  void paint();
  void paintSidebar(float height);
  void paintShelf(float width, float height);
  void paintHero(const Book &book, float x, float y, float w);
  void paintCard(const Book &book, float x, float y, float w, float coverH);
  void paintCover(const Book &book, const D2D1_RECT_F &r, float radius);
  void paintEmpty(float x, float y, float w, float h, bool library);
  void paintReader(float width, float height);
  void paintPanel(float width);
  void paintToc(float width, float height);
  void paintConfirm(float width, float height);
  void paintMenu(float width, float height);
  void menuAction(int item);
  void paintToast(float width, float height);
  void paintSpinner(float cx, float cy, Color c);
  void button(const D2D1_RECT_F &r, const std::wstring &label, HotId id, int64_t arg, bool primary, wchar_t glyph = 0);

  // Behavior.
  void click(float x, float y);
  void contextMenu(float x, float y);
  void key(WPARAM key);
  void wheel(int delta);
  void onEvent(std::unique_ptr<EngineEvent> event);
  void chooseFiles();
  void openBook(int64_t id);
  void closeBook();
  void askRemove(int64_t id);
  void endConfirm(bool remove);
  void turn(int delta);
  bool scrollPage(float dy);
  int currentToc() const;
  ReadStyle readStyle() const;
  void restyle();
  void setDark(bool dark);
  void applyChrome();
  void toast(const std::wstring &message, bool error = false);
  void animate();
  void startAnimation();
  void layoutSearch();
  void updateSearchFont();
  std::vector<const Book *> visibleBooks() const;
  const Book *continueBook() const;
  Book *findBook(int64_t id);
  void loadSettings();
  void saveSettings();
  void saveBookMeta(const Book &book);
  void trace();
  void publishAccess();
  std::wstring accessName(const Hot &h) const;
  const AccessNode *accessNode(HotId id, int64_t arg, size_t *index = nullptr) const;
  std::vector<std::pair<HotId, int64_t>> focusRing() const;
  void moveFocus(int direction);
  void paintFocus();
  float scale() const { return dpi_ / 96.0f; }

  HWND hwnd_ = nullptr, search_ = nullptr;
  HBRUSH searchBrush_ = nullptr;
  HFONT searchFont_ = nullptr;
  float dpi_ = 96;
  Engine engine_;
  std::wstring dataDir_, settingsPath_, tracePath_, traced_;

  ID2D1Factory *factory_ = nullptr;
  ID2D1HwndRenderTarget *target_ = nullptr;
  ID2D1SolidColorBrush *brush_ = nullptr;
  ID2D1LinearGradientBrush *gradients_[8] = {};
  IDWriteFactory *write_ = nullptr;
  std::map<std::pair<int, int>, IDWriteTextFormat *> formats_;
  std::wstring uiFamily_ = L"Segoe UI", iconFamily_ = L"Segoe Fluent Icons";

  bool dark_ = false;
  Palette pal_ = kLight;
  View view_ = View::Shelf;
  Filter filter_ = Filter::All;
  std::vector<Book> books_;
  std::map<int64_t, Cover> covers_;
  std::wstring query_;
  bool ready_ = false, loaded_ = false, importing_ = false;

  std::vector<Hot> hots_;
  Hot hover_ = {{}, HotNone, 0};
  std::map<std::pair<int, int64_t>, float> hoverAnim_;
  float mouseX_ = -1, mouseY_ = -1;
  float scroll_ = 0, scrollTarget_ = 0, scrollMax_ = 0;
  bool animating_ = false;

  // Reader.
  uint64_t ticket_ = 0;
  int64_t reading_ = 0;
  bool opening_ = false, panel_ = false;
  int turnsInFlight_ = 0, pendingTurn_ = 0;
  Frame frame_;
  Pixels framePixels_;
  ID2D1Bitmap *page_ = nullptr, *previous_ = nullptr;
  float fade_ = 1, wheelAccum_ = 0;
  std::wstring bookTitle_;
  int theme_ = 0, spacing_ = 1;
  float fontSize_ = 19, zoom_ = 1;
  bool relayoutPending_ = false;
  std::vector<TocEntry> toc_;
  // UI Automation: the elements of the last paint, the provider for the
  // window, and what was last announced and published.
  std::vector<AccessNode> access_;
  AccessRoot *accessRoot_ = nullptr;
  std::wstring accessShape_, accessAnnounced_;
  // Keyboard focus among the drawn controls (Tab / Shift+Tab, Enter invokes).
  HotId focusId_ = HotNone;
  int64_t focusArg_ = 0;
  int focusDirection_ = 1;
  std::pair<HotId, int64_t> focusRaised_ = {HotNone, 0};
  // Removal confirmation drawn in the window; focus starts on Cancel.
  int64_t confirm_ = 0;
  bool confirmOnRemove_ = false;
  // Book context menu drawn in the window at (menuX_, menuY_); menuIndex_ is the keyboard row.
  int64_t menuBook_ = 0;
  float menuX_ = 0, menuY_ = 0;
  int menuIndex_ = -1;
  bool tocOpen_ = false;
  float tocScroll_ = 0, tocScrollMax_ = 0;
  // A fixed page larger than the view is panned: by drag, wheel or Up/Down.
  D2D1_RECT_F pageRect_ = {};
  float panX_ = 0, panY_ = 0, overflowX_ = 0, overflowY_ = 0;
  bool dragging_ = false, dragMoved_ = false, enterAtEnd_ = false;
  float dragX_ = 0, dragY_ = 0, dragPanX_ = 0, dragPanY_ = 0;

  std::wstring toast_;
  bool toastError_ = false;
  ULONGLONG toastAt_ = 0;
  float spin_ = 0;
};

App *g_app = nullptr;
constexpr UINT_PTR kAnimTimer = 1, kRelayoutTimer = 2;
constexpr int kSearchId = 300;

// ------------------------------------------------------------------------
// Device

bool App::ensureTarget() {
  if (target_) return true;
  RECT rc;
  GetClientRect(hwnd_, &rc);
  D2D1_RENDER_TARGET_PROPERTIES props = D2D1::RenderTargetProperties();
  props.dpiX = props.dpiY = dpi_;
  if (FAILED(factory_->CreateHwndRenderTarget(props,
        D2D1::HwndRenderTargetProperties(hwnd_, D2D1::SizeU(rc.right, rc.bottom)), &target_)))
    return false;
  target_->CreateSolidColorBrush(D2D1::ColorF(0, 0, 0), &brush_);
  for (int i = 0; i < 8; ++i) {
    D2D1_GRADIENT_STOP stops[2] = {{0, Hex(kCoverInks[i][0])}, {1, Hex(kCoverInks[i][1])}};
    ID2D1GradientStopCollection *collection = nullptr;
    target_->CreateGradientStopCollection(stops, 2, &collection);
    target_->CreateLinearGradientBrush(D2D1::LinearGradientBrushProperties(D2D1::Point2F(), D2D1::Point2F(0, 1)),
                                       collection, &gradients_[i]);
    Release(collection);
  }
  for (auto &cover : covers_) cover.second.bitmap = bitmapFrom(cover.second.pixels);
  if (!framePixels_.empty()) page_ = bitmapFrom(framePixels_);
  return true;
}

void App::discardDevice() {
  for (auto &cover : covers_) { Release(cover.second.brush); Release(cover.second.bitmap); }
  for (auto &g : gradients_) Release(g);
  Release(page_);
  Release(previous_);
  Release(brush_);
  Release(target_);
}

ID2D1Bitmap *App::bitmapFrom(const Pixels &pixels) {
  if (!target_ || pixels.empty()) return nullptr;
  ID2D1Bitmap *bitmap = nullptr;
  D2D1_BITMAP_PROPERTIES props = D2D1::BitmapProperties(
    D2D1::PixelFormat(DXGI_FORMAT_B8G8R8A8_UNORM, D2D1_ALPHA_MODE_PREMULTIPLIED), dpi_, dpi_);
  target_->CreateBitmap(D2D1::SizeU(pixels.w, pixels.h), pixels.bgra.data(), pixels.w * 4, props, &bitmap);
  return bitmap;
}

IDWriteTextFormat *App::format(float size, DWRITE_FONT_WEIGHT weight, bool iconFont) {
  auto key = std::make_pair(int(size * 10) * (iconFont ? -1 : 1), int(weight));
  auto it = formats_.find(key);
  if (it != formats_.end()) return it->second;
  IDWriteTextFormat *f = nullptr;
  write_->CreateTextFormat(iconFont ? iconFamily_.c_str() : uiFamily_.c_str(), nullptr, weight,
                           DWRITE_FONT_STYLE_NORMAL, DWRITE_FONT_STRETCH_NORMAL, size, L"zh-cn", &f);
  if (!f) return nullptr;
  DWRITE_TRIMMING trimming = {DWRITE_TRIMMING_GRANULARITY_CHARACTER, 0, 0};
  IDWriteInlineObject *ellipsis = nullptr;
  write_->CreateEllipsisTrimmingSign(f, &ellipsis);
  f->SetTrimming(&trimming, ellipsis);
  Release(ellipsis);
  formats_[key] = f;
  return f;
}

void App::fill(const D2D1_RECT_F &r, Color c, float radius) {
  brush_->SetColor(c);
  if (radius > 0) target_->FillRoundedRectangle(D2D1::RoundedRect(r, radius, radius), brush_);
  else target_->FillRectangle(r, brush_);
}

void App::stroke(const D2D1_RECT_F &r, Color c, float radius, float width) {
  brush_->SetColor(c);
  D2D1_RECT_F inset = D2D1::RectF(r.left + width / 2, r.top + width / 2, r.right - width / 2, r.bottom - width / 2);
  target_->DrawRoundedRectangle(D2D1::RoundedRect(inset, radius, radius), brush_, width);
}

// Soft drop shadow from stacked translucent rounded rectangles.
void App::shadow(const D2D1_RECT_F &r, float radius, float strength) {
  const int steps = 8;
  for (int i = steps; i >= 1; --i) {
    float grow = i * 1.6f;
    float alpha = strength * (1.0f - float(i) / (steps + 1)) / steps * (dark_ ? 2.2f : 1.0f);
    D2D1_RECT_F s = D2D1::RectF(r.left - grow * 0.6f, r.top - grow * 0.2f + i * 0.9f, r.right + grow * 0.6f, r.bottom + grow);
    fill(s, Alpha(pal_.shadow, alpha), radius + grow);
  }
}

void App::text(const std::wstring &s, const D2D1_RECT_F &r, float size, DWRITE_FONT_WEIGHT weight, Color c,
               DWRITE_TEXT_ALIGNMENT align, DWRITE_PARAGRAPH_ALIGNMENT valign, bool wrap) {
  IDWriteTextFormat *f = format(size, weight);
  if (!f || s.empty()) return;
  f->SetTextAlignment(align);
  f->SetParagraphAlignment(valign);
  f->SetWordWrapping(wrap ? DWRITE_WORD_WRAPPING_WRAP : DWRITE_WORD_WRAPPING_NO_WRAP);
  // Text that does not fit ends in an ellipsis instead of a cut glyph.
  IDWriteInlineObject *ellipsis = nullptr;
  DWRITE_TRIMMING trimming = {DWRITE_TRIMMING_GRANULARITY_CHARACTER, 0, 0};
  if (SUCCEEDED(write_->CreateEllipsisTrimmingSign(f, &ellipsis))) f->SetTrimming(&trimming, ellipsis);
  brush_->SetColor(c);
  target_->DrawText(s.c_str(), UINT32(s.size()), f, r, brush_, D2D1_DRAW_TEXT_OPTIONS_CLIP);
  DWRITE_TRIMMING none = {DWRITE_TRIMMING_GRANULARITY_NONE, 0, 0};
  f->SetTrimming(&none, nullptr);
  Release(ellipsis);
}

void App::icon(wchar_t glyph, const D2D1_RECT_F &r, float size, Color c) {
  IDWriteTextFormat *f = format(size, DWRITE_FONT_WEIGHT_NORMAL, true);
  if (!f) return;
  f->SetTextAlignment(DWRITE_TEXT_ALIGNMENT_CENTER);
  f->SetParagraphAlignment(DWRITE_PARAGRAPH_ALIGNMENT_CENTER);
  brush_->SetColor(c);
  target_->DrawText(&glyph, 1, f, r, brush_);
}

float App::measure(const std::wstring &s, float size, DWRITE_FONT_WEIGHT weight) {
  IDWriteTextFormat *f = format(size, weight);
  IDWriteTextLayout *layout = nullptr;
  if (!f || FAILED(write_->CreateTextLayout(s.c_str(), UINT32(s.size()), f, 10000, 1000, &layout))) return 0;
  DWRITE_TEXT_METRICS m = {};
  layout->GetMetrics(&m);
  layout->Release();
  return m.widthIncludingTrailingWhitespace;
}

float App::hoverAmount(HotId id, int64_t arg) {
  auto it = hoverAnim_.find({int(id), arg});
  return it == hoverAnim_.end() ? 0.0f : it->second;
}

// ------------------------------------------------------------------------
// Painting

void App::paint() {
  if (!ensureTarget()) return;
  RECT rc;
  GetClientRect(hwnd_, &rc);
  float width = rc.right / scale(), height = rc.bottom / scale();
  hots_.clear();
  target_->BeginDraw();
  target_->SetTransform(D2D1::Matrix3x2F::Identity());
  if (view_ == View::Shelf) {
    target_->Clear(pal_.window);
    paintShelf(width, height);
    paintSidebar(height);
  } else {
    paintReader(width, height);
  }
  paintFocus();
  paintToast(width, height);
  if (menuBook_) paintMenu(width, height);
  if (confirm_) paintConfirm(width, height);
  if (target_->EndDraw() == D2DERR_RECREATE_TARGET) discardDevice();
  publishAccess();
  trace();
}

// --trace FILE: after each paint that changes what a test can observe, append
// the state and the client-pixel centers of the controls a driver clicks.
void App::trace() {
  if (tracePath_.empty()) return;
  auto rgb = [&](UINT x, UINT y) {
    wchar_t hex[8] = L"none";
    if (x < framePixels_.w && y < framePixels_.h) swprintf(hex, 8, L"%06X", framePixels_.bgra[size_t(y) * framePixels_.w + x] & 0xffffffu);
    return std::wstring(hex);
  };
  const Book *book = findBook(reading_);
  std::wstring line = L"state view=" + std::wstring(view_ == View::Shelf ? L"shelf" : L"reader") +
                      L" books=" + std::to_wstring(books_.size()) + L" opening=" + std::to_wstring(opening_) +
                      L" book=" + std::to_wstring(reading_) +
                      L" format=" + (book ? FormatName(book->item.format) : L"none") +
                      L" author=" + (book && !book->item.author.empty() ? L"set" : L"empty") +
                      L" page=" + std::to_wstring(page_ ? frame_.page : 0) + L" count=" + std::to_wstring(frame_.pageCount) +
                      L" theme=" + std::to_wstring(theme_) + L" panel=" + std::to_wstring(panel_) +
                      L" paper=" + rgb(2, 2);
  size_t ink = 0;
  if (page_ && framePixels_.w > 2 && framePixels_.h > 2)
    for (uint32_t p : framePixels_.bgra) ink += (p ^ framePixels_.bgra[2 * framePixels_.w + 2]) & 0xffffffu ? 1 : 0;
  line += L" ink=" + std::to_wstring(framePixels_.empty() ? 0 : ink * 1000 / framePixels_.bgra.size());
  uint32_t hash = 2166136261u; // FNV-1a over the shown page pixels
  if (page_)
    for (uint32_t p : framePixels_.bgra) hash = (hash ^ p) * 16777619u;
  wchar_t style[96];
  swprintf(style, 96, L" font=%d spacing=%d zoom=%d size=%ux%u frame=%08X", int(fontSize_), spacing_,
           int(zoom_ * 100 + 0.5f), framePixels_.w, framePixels_.h, page_ ? hash : 0u);
  line += style;
  swprintf(style, 96, L" toc=%zu tocopen=%d current=%d pan=%d,%d over=%d,%d", toc_.size(), int(tocOpen_), currentToc(),
           int(panX_), int(panY_), int(overflowX_), int(overflowY_));
  line += style;
  swprintf(style, 96, L" dark=%d filter=%d match=%zu confirm=%lld focus=%d search=%d", int(dark_), int(filter_),
           visibleBooks().size(), (long long)confirm_, int(confirmOnRemove_), int(IsWindowVisible(search_) != FALSE));
  line += style;
  swprintf(style, 96, L" menu=%lld row=%d hover=%d kfocus=%d:%lld", (long long)menuBook_, menuIndex_, int(hover_.id),
           int(focusId_), (long long)focusArg_);
  line += style;
  // Each picture: its center, then a point 3 px inside its top-left corner.
  line += L" pictures=";
  if (!page_ || frame_.pictures.empty()) line += L"none";
  for (size_t i = 0; page_ && i < frame_.pictures.size(); ++i) {
    const RECT &r = frame_.pictures[i];
    line += (i ? L"," : L"") + rgb(UINT(r.left + r.right) / 2, UINT(r.top + r.bottom) / 2) + L":" +
            rgb(UINT(r.left + 3), UINT(r.top + 3));
  }
  for (const Hot &h : hots_)
    if ((h.id >= HotNavAll && h.id <= HotBook) || (h.id >= HotBack && h.id <= HotTrack) || h.id == HotSearch ||
        h.id == HotToc || h.id == HotTocItem || h.id == HotConfirm || h.id == HotConfirmCancel ||
        h.id == HotMenuItem)
      line += L"\nhot " + std::to_wstring(int(h.id)) + L" " + std::to_wstring(h.arg) + L" " +
              std::to_wstring(int((h.rect.left + h.rect.right) / 2 * scale())) + L" " +
              std::to_wstring(int((h.rect.top + h.rect.bottom) / 2 * scale())) + L" " +
              std::to_wstring(int((h.rect.right - h.rect.left) * scale()));
  if (line == traced_) return;
  traced_ = line;
  if (FILE *f = _wfopen(tracePath_.c_str(), L"ab")) {
    int size = WideCharToMultiByte(CP_UTF8, 0, line.c_str(), -1, nullptr, 0, nullptr, nullptr);
    std::string utf8(size > 0 ? size : 1, '\0');
    WideCharToMultiByte(CP_UTF8, 0, line.c_str(), -1, utf8.data(), size, nullptr, nullptr);
    fprintf(f, "%s\nend\n", utf8.c_str());
    fclose(f);
  }
}

void App::button(const D2D1_RECT_F &r, const std::wstring &label, HotId id, int64_t arg, bool primary, wchar_t glyph) {
  float h = hoverAmount(id, arg);
  float radius = (r.bottom - r.top) / 2;
  if (primary) {
    fill(r, Mix(pal_.accent, dark_ ? Hex(0xFFFFFF) : Hex(0x000000), 0.10f * h), radius);
  } else {
    fill(r, Mix(pal_.field, pal_.hover, h), radius);
  }
  Color ink = primary ? pal_.accentInk : pal_.text;
  float tw = measure(label, 14, DWRITE_FONT_WEIGHT_SEMI_BOLD);
  float iw = glyph ? 22.0f : 0.0f;
  float x = (r.left + r.right - tw - iw) / 2;
  if (glyph) icon(glyph, Rect(x, r.top, 16, r.bottom - r.top), 14, ink);
  text(label, D2D1::RectF(x + iw, r.top, r.right, r.bottom), 14, DWRITE_FONT_WEIGHT_SEMI_BOLD, ink,
       DWRITE_TEXT_ALIGNMENT_LEADING, DWRITE_PARAGRAPH_ALIGNMENT_CENTER);
  hot(r, id, arg);
}

void App::paintSidebar(float height) {
  fill(Rect(0, 0, kSidebar, height), pal_.sidebar);
  fill(Rect(kSidebar - 1, 0, 1, height), pal_.border);

  // Brand.
  D2D1_RECT_F mark = Rect(24, 28, 36, 36);
  fill(mark, pal_.accent, 10);
  icon(kIconBook, mark, 18, pal_.accentInk);
  text(L"EXReader", Rect(70, 26, 160, 22), 18, DWRITE_FONT_WEIGHT_BOLD, pal_.text);
  text(L"本地书库", Rect(70, 48, 160, 18), 12, DWRITE_FONT_WEIGHT_NORMAL, pal_.subtle);

  struct Nav { HotId id; Filter filter; wchar_t glyph; const wchar_t *label; size_t count; };
  size_t recent = 0, favorites = 0;
  for (const Book &b : books_) { recent += b.lastRead > 0; favorites += b.item.favorite; }
  Nav navs[] = {
    {HotNavAll, Filter::All, kIconLibrary, L"全部书籍", books_.size()},
    {HotNavRecent, Filter::Recent, kIconRecent, L"最近阅读", recent},
    {HotNavFavorites, Filter::Favorites, kIconHeart, L"我的收藏", favorites},
  };
  text(L"书库", Rect(28, 96, 160, 18), 12, DWRITE_FONT_WEIGHT_SEMI_BOLD, pal_.faint);
  float y = 120;
  for (const Nav &nav : navs) {
    D2D1_RECT_F r = Rect(14, y, kSidebar - 28, 42);
    bool selected = filter_ == nav.filter;
    float h = hoverAmount(nav.id);
    if (selected) fill(r, pal_.accentSoft, 10);
    else if (h > 0) fill(r, Alpha(pal_.hover, h), 10);
    if (selected) fill(Rect(14, y + 12, 3, 18), pal_.accent, 1.5f);
    Color ink = selected ? pal_.accent : pal_.text;
    icon(nav.glyph, Rect(28, y, 22, 42), 16, ink);
    text(nav.label, Rect(60, y, 120, 42), 14, selected ? DWRITE_FONT_WEIGHT_SEMI_BOLD : DWRITE_FONT_WEIGHT_NORMAL, ink,
         DWRITE_TEXT_ALIGNMENT_LEADING, DWRITE_PARAGRAPH_ALIGNMENT_CENTER);
    if (nav.count)
      text(std::to_wstring(nav.count), Rect(kSidebar - 80, y, 52, 42), 12, DWRITE_FONT_WEIGHT_NORMAL,
           selected ? pal_.accent : pal_.faint, DWRITE_TEXT_ALIGNMENT_TRAILING, DWRITE_PARAGRAPH_ALIGNMENT_CENTER);
    hot(r, nav.id);
    y += 46;
  }

  // Import and appearance stay pinned to the bottom.
  float bottom = std::max(y + 40, height - 116);
  button(Rect(20, bottom, kSidebar - 40, 44), importing_ ? L"正在导入…" : L"导入书籍", HotImport, 0, true,
         importing_ ? 0 : kIconAdd);
  D2D1_RECT_F mode = Rect(14, bottom + 56, kSidebar - 28, 40);
  float h = hoverAmount(HotAppearance);
  if (h > 0) fill(mode, Alpha(pal_.hover, h), 10);
  icon(dark_ ? kIconMoon : kIconSun, Rect(28, mode.top, 22, 40), 15, pal_.subtle);
  text(L"深色模式", Rect(60, mode.top, 120, 40), 13, DWRITE_FONT_WEIGHT_NORMAL, pal_.subtle,
       DWRITE_TEXT_ALIGNMENT_LEADING, DWRITE_PARAGRAPH_ALIGNMENT_CENTER);
  D2D1_RECT_F track = Rect(kSidebar - 72, mode.top + 10, 40, 20);
  fill(track, dark_ ? pal_.accent : pal_.border, 10);
  float knob = dark_ ? track.right - 18 : track.left + 2;
  fill(Rect(knob, track.top + 2, 16, 16), dark_ ? pal_.accentInk : Hex(0xFFFFFF), 8);
  hot(mode, HotAppearance);
}

std::vector<const Book *> App::visibleBooks() const {
  std::vector<const Book *> out;
  std::wstring q = query_;
  CharLowerBuffW(q.data(), DWORD(q.size()));
  for (const Book &b : books_) {
    if (filter_ == Filter::Recent && !b.lastRead) continue;
    if (filter_ == Filter::Favorites && !b.item.favorite) continue;
    if (!q.empty()) {
      std::wstring hay = b.item.title + L"\n" + b.item.author;
      CharLowerBuffW(hay.data(), DWORD(hay.size()));
      if (hay.find(q) == std::wstring::npos) continue;
    }
    out.push_back(&b);
  }
  if (filter_ == Filter::Recent)
    std::stable_sort(out.begin(), out.end(), [](const Book *a, const Book *b) { return a->lastRead > b->lastRead; });
  else
    std::stable_sort(out.begin(), out.end(), [](const Book *a, const Book *b) { return a->item.id > b->item.id; });
  return out;
}

const Book *App::continueBook() const {
  const Book *best = nullptr;
  for (const Book &b : books_)
    if (b.lastRead && b.progress < 0.995 && (!best || b.lastRead > best->lastRead)) best = &b;
  return best;
}

Book *App::findBook(int64_t id) {
  for (Book &b : books_) if (b.item.id == id) return &b;
  return nullptr;
}

void App::paintShelf(float width, float height) {
  float left = kSidebar + kPad, contentW = width - left - kPad;
  std::vector<const Book *> list = visibleBooks();

  // Header: title, count and the search field (a native edit laid over the drawn pill).
  const wchar_t *title = filter_ == Filter::All ? L"全部书籍" : filter_ == Filter::Recent ? L"最近阅读" : L"我的收藏";
  text(title, Rect(left, 30, 400, 38), 28, DWRITE_FONT_WEIGHT_BOLD, pal_.text);
  std::wstring sub = !loaded_ ? L"正在载入书库…" : query_.empty() ? L"共 " + std::to_wstring(list.size()) + L" 本"
                                                     : L"找到 " + std::to_wstring(list.size()) + L" 本";
  text(sub, Rect(left, 68, 400, 20), 13, DWRITE_FONT_WEIGHT_NORMAL, pal_.subtle);
  float searchW = std::min(300.0f, contentW * 0.45f);
  D2D1_RECT_F field = Rect(width - kPad - searchW, 36, searchW, 40);
  bool focused = GetFocus() == search_;
  fill(field, focused ? pal_.surface : pal_.field, 20);
  if (focused) stroke(field, pal_.accent, 20, 1.5f);
  icon(kIconSearch, Rect(field.left + 12, field.top, 20, 40), 14, pal_.faint);
  hot(field, HotSearch);

  // Scrolling content, clipped under the header.
  float viewTop = kHeader + 8, viewH = height - viewTop;
  target_->PushAxisAlignedClip(D2D1::RectF(kSidebar, viewTop - 8, width, height), D2D1_ANTIALIAS_MODE_ALIASED);
  float y = viewTop + 8 - scroll_;
  const Book *resume = filter_ == Filter::All && query_.empty() ? continueBook() : nullptr;
  if (resume) {
    paintHero(*resume, left, y, contentW);
    y += 196;
    text(L"书架", Rect(left, y, 200, 24), 17, DWRITE_FONT_WEIGHT_SEMI_BOLD, pal_.text);
    y += 40;
  }
  if (list.empty()) {
    if (loaded_) paintEmpty(left, y, contentW, std::max(320.0f, height - y - 40), books_.empty());
    scrollMax_ = 0;
  } else {
    int columns = std::max(1, int((contentW + kGap) / (150 + kGap)));
    float cardW = std::min(190.0f, (contentW - kGap * (columns - 1)) / columns);
    float coverH = cardW * 1.5f, cardH = coverH + 82;
    for (size_t i = 0; i < list.size(); ++i) {
      float cx = left + (i % columns) * (cardW + kGap), cy = y + (i / columns) * (cardH + 12);
      if (cy + cardH < viewTop - 20 || cy > height + 20) continue;
      paintCard(*list[i], cx, cy, cardW, coverH);
    }
    float total = (y + scroll_) + ((list.size() + columns - 1) / columns) * (cardH + 12) + 24;
    scrollMax_ = std::max(0.0f, total - (viewTop + viewH));
  }
  target_->PopAxisAlignedClip();
  if (scrollMax_ > 0) {
    float trackH = viewH - 24, thumbH = std::max(40.0f, trackH * viewH / (viewH + scrollMax_));
    float thumbY = viewTop + 8 + (trackH - thumbH) * (scroll_ / scrollMax_);
    fill(Rect(width - 8, thumbY, 4, thumbH), Alpha(pal_.subtle, 0.35f), 2);
  }
  // Soft edge where content scrolls under the header.
  if (scroll_ > 1) {
    for (int i = 0; i < 12; ++i) fill(Rect(kSidebar, viewTop - 8 + i, width - kSidebar, 1), Alpha(pal_.window, 1 - i / 12.0f));
  }
}

void App::paintHero(const Book &book, float x, float y, float w) {
  D2D1_RECT_F card = Rect(x, y, w, 172);
  float h = hoverAmount(HotContinue, book.item.id);
  shadow(card, 18, 0.10f + 0.06f * h);
  fill(card, pal_.surface, 18);
  // Accent wash on the right.
  D2D1_RECT_F wash = Rect(x + w * 0.55f, y, w * 0.45f, 172);
  target_->PushAxisAlignedClip(wash, D2D1_ANTIALIAS_MODE_ALIASED);
  fill(Rect(x + w - 220, y - 80, 300, 300), Alpha(pal_.accent, dark_ ? 0.10f : 0.07f), 150);
  fill(Rect(x + w - 120, y + 60, 200, 200), Alpha(pal_.accent, dark_ ? 0.08f : 0.05f), 100);
  target_->PopAxisAlignedClip();

  paintCover(book, Rect(x + 24, y + 20, 88, 132), 6);
  float tx = x + 136, tw = w - 136 - 200;
  text(L"继续阅读", Rect(tx, y + 26, tw, 18), 12, DWRITE_FONT_WEIGHT_SEMI_BOLD, pal_.accent);
  text(book.item.title.empty() ? L"未命名" : book.item.title, Rect(tx, y + 46, tw, 32), 22, DWRITE_FONT_WEIGHT_BOLD, pal_.text);
  text(book.item.author.empty() ? L"佚名" : book.item.author, Rect(tx, y + 80, tw, 20), 13, DWRITE_FONT_WEIGHT_NORMAL, pal_.subtle);
  float barW = std::min(280.0f, tw);
  double p = std::max(0.0, book.progress);
  fill(Rect(tx, y + 124, barW, 6), pal_.field, 3);
  fill(Rect(tx, y + 124, std::max(6.0f, float(barW * p)), 6), pal_.accent, 3);
  wchar_t pct[32];
  swprintf(pct, 32, L"已读 %d%%", int(p * 100 + 0.5));
  text(pct, Rect(tx + barW + 12, y + 116, 100, 22), 12, DWRITE_FONT_WEIGHT_SEMI_BOLD, pal_.subtle,
       DWRITE_TEXT_ALIGNMENT_LEADING, DWRITE_PARAGRAPH_ALIGNMENT_CENTER);
  button(Rect(x + w - 176, y + 64, 148, 44), L"继续阅读", HotContinue, book.item.id, true, kIconRight);
  hot(card, HotContinue, book.item.id);
  std::swap(hots_[hots_.size() - 1], hots_[hots_.size() - 2]); // the button stays on top
}

void App::paintCover(const Book &book, const D2D1_RECT_F &r, float radius) {
  auto it = covers_.find(book.item.id);
  float w = r.right - r.left, h = r.bottom - r.top;
  if (it != covers_.end() && it->second.bitmap) {
    Cover &cover = it->second;
    if (!cover.brush) target_->CreateBitmapBrush(cover.bitmap, &cover.brush);
    if (cover.brush) {
      D2D1_SIZE_F size = cover.bitmap->GetSize();
      float s = std::max(w / size.width, h / size.height); // crop to fill
      float ox = r.left + (w - size.width * s) / 2, oy = r.top + (h - size.height * s) / 2;
      cover.brush->SetTransform(D2D1::Matrix3x2F::Scale(s, s) * D2D1::Matrix3x2F::Translation(ox, oy));
      cover.brush->SetInterpolationMode(D2D1_BITMAP_INTERPOLATION_MODE_LINEAR);
      target_->FillRoundedRectangle(D2D1::RoundedRect(r, radius, radius), cover.brush);
      // Spine shading.
      fill(Rect(r.left, r.top, 3, h), Hex(0x000000, 0.10f));
      stroke(r, Hex(0x000000, 0.08f), radius);
      return;
    }
  }
  size_t hash = std::hash<std::wstring>()(book.item.title + book.item.author);
  ID2D1LinearGradientBrush *g = gradients_[hash % 8];
  if (g) {
    g->SetStartPoint(D2D1::Point2F(r.left, r.top));
    g->SetEndPoint(D2D1::Point2F(r.right, r.bottom));
    target_->FillRoundedRectangle(D2D1::RoundedRect(r, radius, radius), g);
  }
  fill(Rect(r.left, r.top, 4, h), Hex(0x000000, 0.14f));
  fill(Rect(r.left + 4, r.top, 1, h), Hex(0xFFFFFF, 0.12f));
  if (w < 60) return;
  float s = w / 150;
  float pad = 14 * s;
  fill(Rect(r.left + pad, r.top + 22 * s, 24 * s, 2 * s), Hex(0xFFFFFF, 0.75f));
  text(book.item.title.empty() ? L"未命名" : book.item.title, Rect(r.left + pad, r.top + 34 * s, w - pad * 2, h * 0.5f),
       std::max(11.0f, 17 * s), DWRITE_FONT_WEIGHT_BOLD, Hex(0xFFFFFF, 0.96f), DWRITE_TEXT_ALIGNMENT_LEADING,
       DWRITE_PARAGRAPH_ALIGNMENT_NEAR, true);
  if (!book.item.author.empty())
    text(book.item.author, Rect(r.left + pad, r.bottom - 34 * s, w - pad * 2, 18 * s), std::max(9.0f, 11 * s),
         DWRITE_FONT_WEIGHT_NORMAL, Hex(0xFFFFFF, 0.78f));
}

void App::paintCard(const Book &book, float x, float y, float w, float coverH) {
  float h = hoverAmount(HotBook, book.item.id);
  float lift = 4 * h;
  D2D1_RECT_F cover = Rect(x, y - lift, w, coverH);
  shadow(cover, 8, 0.12f + 0.10f * h);
  paintCover(book, cover, 8);
  if (h > 0) fill(cover, Hex(0xFFFFFF, 0.05f * h), 8);

  // Format badge and favorite mark.
  std::wstring fmt = FormatName(book.item.format);
  float bw = measure(fmt, 10, DWRITE_FONT_WEIGHT_BOLD) + 14;
  D2D1_RECT_F badge = Rect(cover.left + 8, cover.bottom - 28, bw, 20);
  fill(badge, Hex(0x000000, 0.45f), 10);
  text(fmt, badge, 10, DWRITE_FONT_WEIGHT_BOLD, Hex(0xFFFFFF, 0.95f), DWRITE_TEXT_ALIGNMENT_CENTER,
       DWRITE_PARAGRAPH_ALIGNMENT_CENTER);
  if (book.item.favorite) {
    D2D1_RECT_F heart = Rect(cover.right - 34, cover.top + 8, 26, 26);
    fill(heart, Hex(0xFFFFFF, 0.92f), 13);
    icon(kIconHeartFill, heart, 12, Hex(0xE03E52));
  }
  if (h > 0.01f) {
    D2D1_RECT_F open = Rect(cover.left + w / 2 - 44, cover.top + coverH / 2 - 18, 88, 36);
    fill(open, Hex(0x000000, 0.55f * h), 18);
    text(L"打开", open, 13, DWRITE_FONT_WEIGHT_SEMI_BOLD, Hex(0xFFFFFF, h), DWRITE_TEXT_ALIGNMENT_CENTER,
         DWRITE_PARAGRAPH_ALIGNMENT_CENTER);
  }

  float ty = y + coverH + 12;
  const std::wstring &name = book.item.title.empty() ? std::wstring(L"未命名") : book.item.title;
  float titleH = measure(name, 14, DWRITE_FONT_WEIGHT_SEMI_BOLD) <= w ? 21.0f : 40.0f;
  text(name, Rect(x, ty, w, 40), 14, DWRITE_FONT_WEIGHT_SEMI_BOLD,
       pal_.text, DWRITE_TEXT_ALIGNMENT_LEADING, DWRITE_PARAGRAPH_ALIGNMENT_NEAR, true);
  text(book.item.author.empty() ? L"佚名" : book.item.author, Rect(x, ty + titleH, w, 18), 12, DWRITE_FONT_WEIGHT_NORMAL,
       pal_.subtle);
  float by = ty + titleH + 30;
  if (book.progress >= 0) {
    float pw = w - 44;
    fill(Rect(x, by, pw, 4), pal_.field, 2);
    fill(Rect(x, by, std::max(4.0f, float(pw * book.progress)), 4), pal_.accent, 2);
    wchar_t pct[16];
    if (book.progress >= 0.995) wcscpy(pct, L"读完");
    else swprintf(pct, 16, L"%d%%", int(book.progress * 100 + 0.5));
    text(pct, Rect(x + pw + 4, by - 8, 40, 20), 11, DWRITE_FONT_WEIGHT_SEMI_BOLD, pal_.subtle,
         DWRITE_TEXT_ALIGNMENT_TRAILING, DWRITE_PARAGRAPH_ALIGNMENT_CENTER);
  } else {
    text(L"未读", Rect(x, by - 8, w, 20), 11, DWRITE_FONT_WEIGHT_NORMAL, pal_.faint,
         DWRITE_TEXT_ALIGNMENT_LEADING, DWRITE_PARAGRAPH_ALIGNMENT_CENTER);
  }
  hot(Rect(x, y - lift, w, coverH + 82), HotBook, book.item.id);
}

void App::paintEmpty(float x, float y, float w, float h, bool library) {
  float cx = x + w / 2, cy = y + h * 0.36f;
  // Three leaning books.
  struct Spine { float dx, angle, w, h; int ink; };
  Spine spines[] = {{-46, -8, 34, 116, 3}, {-6, 0, 40, 132, 4}, {38, 6, 30, 108, 5}};
  for (const Spine &s : spines) {
    D2D1_RECT_F r = Rect(cx + s.dx - s.w / 2, cy - s.h / 2, s.w, s.h);
    target_->SetTransform(D2D1::Matrix3x2F::Rotation(s.angle, D2D1::Point2F(cx + s.dx, cy + s.h / 2)));
    ID2D1LinearGradientBrush *g = gradients_[s.ink];
    if (g) {
      g->SetStartPoint(D2D1::Point2F(r.left, r.top));
      g->SetEndPoint(D2D1::Point2F(r.right, r.bottom));
      target_->FillRoundedRectangle(D2D1::RoundedRect(r, 5, 5), g);
    }
    fill(Rect(r.left + 6, r.top + 18, s.w - 12, 3), Hex(0xFFFFFF, 0.6f));
    fill(Rect(r.left + 6, r.bottom - 24, s.w - 12, 3), Hex(0xFFFFFF, 0.6f));
    target_->SetTransform(D2D1::Matrix3x2F::Identity());
  }
  fill(Rect(cx - 110, cy + 70, 220, 4), pal_.border, 2);
  const wchar_t *title = library ? L"书架还空着" : !query_.empty() ? L"没有找到相关的书" : L"这里还没有书";
  const wchar_t *hint = library ? L"把 EPUB、PDF、TXT、MOBI 等电子书拖进窗口，或点击下方按钮导入"
                       : !query_.empty() ? L"换个关键词试试，书名和作者都能搜"
                       : filter_ == Filter::Recent ? L"打开一本书，它就会出现在这里" : L"在书本上右键即可加入收藏";
  text(title, Rect(x, cy + 96, w, 30), 20, DWRITE_FONT_WEIGHT_SEMI_BOLD, pal_.text, DWRITE_TEXT_ALIGNMENT_CENTER);
  text(hint, Rect(x, cy + 130, w, 22), 13, DWRITE_FONT_WEIGHT_NORMAL, pal_.subtle, DWRITE_TEXT_ALIGNMENT_CENTER);
  if (library) button(Rect(cx - 80, cy + 172, 160, 44), L"导入书籍", HotImport, 1, true, kIconAdd);
}

void App::paintSpinner(float cx, float cy, Color c) {
  for (int i = 0; i < 10; ++i) {
    float a = (spin_ + i * 36.0f) * 3.14159265f / 180.0f;
    float alpha = 0.15f + 0.85f * (i / 9.0f);
    float px = cx + std::cos(a) * 14, py = cy + std::sin(a) * 14;
    brush_->SetColor(Alpha(c, alpha));
    target_->FillEllipse(D2D1::Ellipse(D2D1::Point2F(px, py), 2.6f, 2.6f), brush_);
  }
}

void App::paintReader(float width, float height) {
  const ReadingTheme &theme = kThemes[theme_];
  Color surround = Hex(theme.surround), ink = Hex(theme.ink);
  Color soft = Alpha(ink, 0.55f);
  target_->Clear(surround);

  // Top bar.
  D2D1_RECT_F back = Rect(16, 10, 92, 36);
  float hb = hoverAmount(HotBack);
  if (hb > 0) fill(back, Alpha(ink, 0.08f * hb), 18);
  icon(kIconBack, Rect(back.left + 10, back.top, 20, 36), 14, ink);
  text(L"书架", Rect(back.left + 36, back.top, 50, 36), 14, DWRITE_FONT_WEIGHT_SEMI_BOLD, ink,
       DWRITE_TEXT_ALIGNMENT_LEADING, DWRITE_PARAGRAPH_ALIGNMENT_CENTER);
  hot(back, HotBack);
  text(bookTitle_, Rect(140, 10, width - 280, 36), 14, DWRITE_FONT_WEIGHT_SEMI_BOLD, soft, DWRITE_TEXT_ALIGNMENT_CENTER,
       DWRITE_PARAGRAPH_ALIGNMENT_CENTER);
  D2D1_RECT_F style = Rect(width - 64, 10, 44, 36);
  float hs = std::max(hoverAmount(HotStyle), panel_ ? 1.0f : 0.0f);
  if (hs > 0) fill(style, Alpha(ink, 0.08f * hs), 18);
  text(L"Aa", style, 16, DWRITE_FONT_WEIGHT_SEMI_BOLD, ink, DWRITE_TEXT_ALIGNMENT_CENTER, DWRITE_PARAGRAPH_ALIGNMENT_CENTER);
  hot(style, HotStyle);
  if (!toc_.empty()) {
    D2D1_RECT_F contents = Rect(width - 112, 10, 44, 36);
    float ht = std::max(hoverAmount(HotToc), tocOpen_ ? 1.0f : 0.0f);
    if (ht > 0) fill(contents, Alpha(ink, 0.08f * ht), 18);
    icon(kIconToc, contents, 16, ink);
    hot(contents, HotToc);
  }

  // Page, clipped to the space between the bars. A fixed page larger than
  // that space is panned instead of spilling under the bars.
  float availH = height - kTopBar - kBottomBar - 8, viewH = height - kTopBar - kBottomBar;
  float paperW = frame_.fixed ? 0 : std::min(width - 160, 760.0f);
  overflowX_ = overflowY_ = 0;
  if (page_) {
    D2D1_SIZE_F size = page_->GetSize();
    float pw = size.width, ph = size.height;
    float px = std::floor((width - pw) / 2), py = std::floor(kTopBar + (availH - ph) / 2);
    if (frame_.fixed) {
      overflowX_ = std::max(0.0f, pw - width);
      overflowY_ = std::max(0.0f, ph - viewH);
      panX_ = std::min(overflowX_, std::max(0.0f, panX_));
      panY_ = std::min(overflowY_, std::max(0.0f, panY_));
      if (overflowX_ > 0) px = -std::floor(panX_);
      py = overflowY_ > 0 ? kTopBar - std::floor(panY_) : std::max(kTopBar, py);
    }
    D2D1_RECT_F paper = Rect(px, py, pw, ph);
    pageRect_ = paper;
    target_->PushAxisAlignedClip(Rect(0, kTopBar, width, viewH), D2D1_ANTIALIAS_MODE_ALIASED);
    shadow(paper, 4, theme.dark ? 0.30f : 0.10f);
    if (previous_ && fade_ < 1) {
      D2D1_SIZE_F ps = previous_->GetSize();
      target_->DrawBitmap(previous_, Rect(std::floor((width - ps.width) / 2), py, ps.width, ps.height), 1.0f,
                          D2D1_BITMAP_INTERPOLATION_MODE_LINEAR);
    }
    target_->DrawBitmap(page_, paper, fade_, D2D1_BITMAP_INTERPOLATION_MODE_LINEAR);
    target_->PopAxisAlignedClip();
    paperW = std::min(pw, width);
  } else if (opening_) {
    paintSpinner(width / 2, kTopBar + availH / 2, ink);
    text(L"正在打开…", Rect(0, kTopBar + availH / 2 + 26, width, 22), 13, DWRITE_FONT_WEIGHT_NORMAL, soft,
         DWRITE_TEXT_ALIGNMENT_CENTER);
  }

  // Click zones and edge chevrons.
  D2D1_RECT_F prevZone = Rect(0, kTopBar, width * 0.3f, availH), nextZone = Rect(width * 0.7f, kTopBar, width * 0.3f, availH);
  hot(prevZone, HotPrev);
  hot(nextZone, HotNext);
  if (page_) {
    float hp = hoverAmount(HotPrev), hn = hoverAmount(HotNext);
    float cy = kTopBar + availH / 2;
    if (hp > 0 && !frame_.first) {
      D2D1_RECT_F c = Rect(24, cy - 24, 48, 48);
      fill(c, Alpha(ink, 0.08f * hp), 24);
      icon(kIconLeft, c, 16, Alpha(ink, hp));
    }
    if (hn > 0 && !frame_.last) {
      D2D1_RECT_F c = Rect(width - 72, cy - 24, 48, 48);
      fill(c, Alpha(ink, 0.08f * hn), 24);
      icon(kIconRight, c, 16, Alpha(ink, hn));
    }
  }

  // Bottom progress.
  if (page_) {
    float barW = std::max(200.0f, std::min(paperW, width - 320));
    float bx = (width - barW) / 2, by = height - kBottomBar / 2;
    float ht = hoverAmount(HotTrack);
    float thick = 4 + 2 * ht;
    fill(Rect(bx, by - thick / 2, barW, thick), Alpha(ink, 0.12f), thick / 2);
    fill(Rect(bx, by - thick / 2, std::max(thick, float(barW * frame_.progress)), thick), Hex(0xE07A45), thick / 2);
    hot(Rect(bx, by - 12, barW, 24), HotTrack);
    wchar_t left[64], right[32];
    if (frame_.fixed) swprintf(left, 64, L"%zu / %zu", frame_.page + 1, frame_.pageCount);
    else swprintf(left, 64, L"第 %zu 页", frame_.page + 1);
    swprintf(right, 32, L"%d%%", int(frame_.progress * 100 + 0.5));
    text(left, Rect(bx - 140, by - 11, 128, 22), 12, DWRITE_FONT_WEIGHT_NORMAL, soft, DWRITE_TEXT_ALIGNMENT_TRAILING,
         DWRITE_PARAGRAPH_ALIGNMENT_CENTER);
    text(right, Rect(bx + barW + 12, by - 11, 80, 22), 12, DWRITE_FONT_WEIGHT_NORMAL, soft, DWRITE_TEXT_ALIGNMENT_LEADING,
         DWRITE_PARAGRAPH_ALIGNMENT_CENTER);
  }
  if (panel_) paintPanel(width);
  if (tocOpen_) paintToc(width, height);
}

// The entry this page belongs to: the last one that begins before the page
// ends, so a heading partway down the page is already current.
void App::paintConfirm(float width, float height) {
  const Book *book = findBook(confirm_);
  if (!book) { confirm_ = 0; return; }
  fill(Rect(0, 0, width, height), Hex(0x000000, dark_ ? 0.45f : 0.28f));
  hot(Rect(0, 0, width, height), HotConfirmShade);
  D2D1_RECT_F card = Rect(std::floor((width - 440) / 2), std::floor((height - 214) / 2), 440, 214);
  shadow(card, 18, 0.30f);
  fill(card, pal_.surface, 18);
  stroke(card, pal_.border, 18);
  hot(card, HotConfirmCard);
  float x = card.left + 28, w = 440 - 56;
  text(L"移除这本书？", Rect(x, card.top + 26, w, 30), 18, DWRITE_FONT_WEIGHT_SEMI_BOLD, pal_.text);
  std::wstring title = book->item.title.empty() ? std::wstring(L"未命名") : book->item.title;
  text(L"《" + title + L"》", Rect(x, card.top + 62, w, 22), 14, DWRITE_FONT_WEIGHT_SEMI_BOLD, pal_.text);
  text(L"书库中保存的原文件、阅读进度和笔记都会一并删除，无法恢复。", Rect(x, card.top + 90, w, 40), 13,
       DWRITE_FONT_WEIGHT_NORMAL, pal_.subtle, DWRITE_TEXT_ALIGNMENT_LEADING, DWRITE_PARAGRAPH_ALIGNMENT_NEAR, true);
  D2D1_RECT_F cancel = Rect(card.right - 28 - 220, card.bottom - 64, 104, 40);
  D2D1_RECT_F remove = Rect(card.right - 28 - 104, card.bottom - 64, 104, 40);
  Color danger = Hex(0xC2412D);
  float hc = hoverAmount(HotConfirmCancel), hr = hoverAmount(HotConfirm);
  fill(cancel, Mix(pal_.field, pal_.hover, hc), 20);
  text(L"取消", cancel, 14, DWRITE_FONT_WEIGHT_SEMI_BOLD, pal_.text, DWRITE_TEXT_ALIGNMENT_CENTER,
       DWRITE_PARAGRAPH_ALIGNMENT_CENTER);
  fill(remove, Mix(danger, Hex(0x9E2F1F), hr), 20);
  text(L"移除", remove, 14, DWRITE_FONT_WEIGHT_SEMI_BOLD, Hex(0xFFFFFF), DWRITE_TEXT_ALIGNMENT_CENTER,
       DWRITE_PARAGRAPH_ALIGNMENT_CENTER);
  // Keyboard focus ring on the button Enter would press.
  D2D1_RECT_F focus = confirmOnRemove_ ? remove : cancel;
  stroke(D2D1::RectF(focus.left - 3, focus.top - 3, focus.right + 3, focus.bottom + 3), pal_.accent, 23, 2);
  hot(cancel, HotConfirmCancel);
  hot(remove, HotConfirm);
}

void App::paintMenu(float width, float height) {
  const Book *book = findBook(menuBook_);
  if (!book || view_ != View::Shelf) { menuBook_ = 0; return; }
  const float w = 208, rowH = 40, gap = 9;
  float h = 8 + rowH * 3 + gap + 8;
  float x = std::min(menuX_, width - w - 8), y = menuY_ + h > height - 8 ? std::max(8.0f, menuY_ - h) : menuY_;
  D2D1_RECT_F card = Rect(x, y, w, h);
  shadow(card, 12, 0.24f);
  fill(card, pal_.surface, 12);
  stroke(card, pal_.border, 12);
  hot(card, HotMenuCard);
  struct Item { wchar_t glyph; const wchar_t *label; Color ink; };
  Color danger = Hex(0xC2412D);
  Item items[3] = {{kIconBook, L"打开", pal_.text},
                   {book->item.favorite ? kIconHeartFill : kIconHeart, book->item.favorite ? L"取消收藏" : L"加入收藏",
                    pal_.text},
                   {kIconDelete, L"从书架移除…", danger}};
  float top = y + 8;
  for (int i = 0; i < 3; ++i) {
    if (i == 2) {
      fill(Rect(x + 12, top + gap / 2, w - 24, 1), pal_.border);
      top += gap;
    }
    D2D1_RECT_F row = Rect(x + 6, top, w - 12, rowH);
    float hv = std::max(hoverAmount(HotMenuItem, i), menuIndex_ == i ? 1.0f : 0.0f);
    if (hv > 0) fill(row, Alpha(pal_.hover, hv), 8);
    icon(items[i].glyph, Rect(row.left + 8, top, 24, rowH), 14, i == 1 && book->item.favorite ? Hex(0xE03E52) : items[i].ink);
    text(items[i].label, Rect(row.left + 40, top, w - 64, rowH), 14, DWRITE_FONT_WEIGHT_NORMAL, items[i].ink,
         DWRITE_TEXT_ALIGNMENT_LEADING, DWRITE_PARAGRAPH_ALIGNMENT_CENTER);
    hot(row, HotMenuItem, i);
    top += rowH;
  }
}

void App::menuAction(int item) {
  int64_t id = menuBook_;
  menuBook_ = 0;
  Book *book = findBook(id);
  if (book && item == 0) openBook(id);
  else if (book && item == 1) {
    book->item.favorite = !book->item.favorite;
    engine_.favorite(id, book->item.favorite);
    toast(book->item.favorite ? L"已加入收藏" : L"已取消收藏");
  } else if (book && item == 2) {
    askRemove(id);
  }
  InvalidateRect(hwnd_, nullptr, FALSE);
}

void App::askRemove(int64_t id) {
  confirm_ = id;
  confirmOnRemove_ = false;
  // The search box is a child window the dimmed overlay cannot cover.
  ShowWindow(search_, SW_HIDE);
  hover_ = {{}, HotNone, 0};
  startAnimation();
  SetFocus(hwnd_);
  InvalidateRect(hwnd_, nullptr, FALSE);
}

void App::endConfirm(bool remove) {
  int64_t id = confirm_;
  confirm_ = 0;
  if (view_ == View::Shelf) ShowWindow(search_, SW_SHOW);
  if (remove && findBook(id)) {
    engine_.remove(id);
    toast(L"已从书架移除");
  }
  InvalidateRect(hwnd_, nullptr, FALSE);
}

// Tab order: the controls a keyboard user would reach, in reading order. On
// the shelf every visible book is in the ring, painted or scrolled away.
std::vector<std::pair<HotId, int64_t>> App::focusRing() const {
  std::vector<std::pair<HotId, int64_t>> ring;
  if (view_ == View::Shelf) {
    for (HotId id : {HotNavAll, HotNavRecent, HotNavFavorites, HotImport, HotAppearance}) ring.push_back({id, 0});
    if (const Book *resume = filter_ == Filter::All && query_.empty() ? continueBook() : nullptr)
      ring.push_back({HotContinue, resume->item.id});
    for (const Book *b : visibleBooks()) ring.push_back({HotBook, b->item.id});
    return ring;
  }
  for (const Hot &h : hots_) {
    bool wanted = h.id == HotBack || h.id == HotToc || h.id == HotStyle || (h.id >= HotFontDown && h.id <= HotZoomUp) ||
                  h.id == HotTocItem;
    if (wanted && std::find(ring.begin(), ring.end(), std::make_pair(h.id, h.arg)) == ring.end()) ring.push_back({h.id, h.arg});
  }
  return ring;
}

void App::moveFocus(int direction) {
  std::vector<std::pair<HotId, int64_t>> ring = focusRing();
  if (ring.empty()) return;
  auto at = std::find(ring.begin(), ring.end(), std::make_pair(focusId_, focusArg_));
  size_t next = at == ring.end() ? (direction > 0 ? 0 : ring.size() - 1)
                                 : (size_t(at - ring.begin()) + ring.size() + direction) % ring.size();
  focusId_ = ring[next].first;
  focusArg_ = ring[next].second;
  focusDirection_ = direction;
  InvalidateRect(hwnd_, nullptr, FALSE);
}

// Ring around the focused control; a shelf card is scrolled fully into view,
// and one not painted yet is approached in the direction focus moved.
void App::paintFocus() {
  if (focusId_ == HotNone || confirm_ || menuBook_) return;
  const Hot *found = nullptr;
  for (const Hot &h : hots_) if (h.id == focusId_ && h.arg == focusArg_) found = &h;
  if (view_ == View::Shelf && (focusId_ == HotBook || focusId_ == HotContinue)) {
    RECT rc;
    GetClientRect(hwnd_, &rc);
    float top = kHeader + 8, bottom = rc.bottom / scale() - 12;
    float shift = !found ? focusDirection_ * 240.0f
                : found->rect.top < top ? found->rect.top - top
                : found->rect.bottom > bottom ? found->rect.bottom - bottom : 0;
    if (shift != 0) {
      scrollTarget_ = std::min(scrollMax_, std::max(0.0f, scrollTarget_ + shift));
      startAnimation();
    }
  }
  if (!found) return;
  D2D1_RECT_F r = found->rect;
  stroke(D2D1::RectF(r.left - 3, r.top - 3, r.right + 3, r.bottom + 3), pal_.accent, 12, 2);
}

int App::currentToc() const {
  int current = -1;
  for (size_t i = 0; i < toc_.size(); ++i)
    if (toc_[i].offset < std::max(frame_.end, frame_.start + 1) && (current < 0 || toc_[i].offset >= toc_[current].offset))
      current = int(i);
  return current;
}

// Contents drawer: the book's own table of contents, current chapter marked.
void App::paintToc(float width, float height) {
  const Palette &p = kThemes[theme_].dark ? kDark : kLight;
  D2D1_RECT_F r = Rect(16, kTopBar + 4, std::min(360.0f, width - 32), height - kTopBar - 20);
  shadow(r, 16, 0.22f);
  fill(r, p.surface, 16);
  stroke(r, p.border, 16);
  hot(r, HotTocPanel);
  text(L"目录", Rect(r.left + 20, r.top + 12, 120, 32), 16, DWRITE_FONT_WEIGHT_SEMI_BOLD, p.text,
       DWRITE_TEXT_ALIGNMENT_LEADING, DWRITE_PARAGRAPH_ALIGNMENT_CENTER);
  text(std::to_wstring(toc_.size()) + L" 项", Rect(r.right - 120, r.top + 12, 100, 32), 12, DWRITE_FONT_WEIGHT_NORMAL,
       p.subtle, DWRITE_TEXT_ALIGNMENT_TRAILING, DWRITE_PARAGRAPH_ALIGNMENT_CENTER);
  D2D1_RECT_F list = D2D1::RectF(r.left + 8, r.top + 54, r.right - 8, r.bottom - 10);
  const float rowH = 40;
  tocScrollMax_ = std::max(0.0f, toc_.size() * rowH - (list.bottom - list.top));
  tocScroll_ = std::min(tocScrollMax_, std::max(0.0f, tocScroll_));
  int current = currentToc();
  target_->PushAxisAlignedClip(list, D2D1_ANTIALIAS_MODE_ALIASED);
  for (size_t i = 0; i < toc_.size(); ++i) {
    float y = list.top + i * rowH - tocScroll_;
    if (y + rowH < list.top || y > list.bottom) continue;
    D2D1_RECT_F row = D2D1::RectF(list.left, y, list.right, y + rowH);
    float h = hoverAmount(HotTocItem, int64_t(i));
    bool here = int(i) == current;
    if (here) fill(row, p.accentSoft, 10);
    else if (h > 0) fill(row, Alpha(p.hover, h), 10);
    if (here) fill(Rect(row.left + 4, y + 10, 3, rowH - 20), p.accent, 1.5f);
    float indent = 16 + 16 * float(std::min(toc_[i].depth, 4));
    text(toc_[i].label, Rect(row.left + indent, y, row.right - row.left - indent - 12, rowH), 14,
         here ? DWRITE_FONT_WEIGHT_SEMI_BOLD : DWRITE_FONT_WEIGHT_NORMAL, here ? p.accent : p.text,
         DWRITE_TEXT_ALIGNMENT_LEADING, DWRITE_PARAGRAPH_ALIGNMENT_CENTER);
    hot(D2D1::RectF(row.left, std::max(row.top, list.top), row.right, std::min(row.bottom, list.bottom)), HotTocItem,
        int64_t(i));
  }
  target_->PopAxisAlignedClip();
  if (tocScrollMax_ > 0) {
    float trackH = list.bottom - list.top, thumbH = std::max(32.0f, trackH * trackH / (trackH + tocScrollMax_));
    float thumbY = list.top + (trackH - thumbH) * (tocScroll_ / tocScrollMax_);
    fill(Rect(r.right - 6, thumbY, 3, thumbH), Alpha(p.subtle, 0.5f), 1.5f);
  }
}

// Pans an oversized fixed page by dy; at its top or bottom edge the page
// turns instead, entering the previous page at its bottom. False when the
// page fits, so the caller turns as usual.
bool App::scrollPage(float dy) {
  if (!frame_.fixed || overflowY_ <= 0) return false;
  if (dy > 0 && panY_ >= overflowY_ - 0.5f) {
    if (!frame_.last) turn(1);
    return true;
  }
  if (dy < 0 && panY_ <= 0.5f) {
    if (!frame_.first) { enterAtEnd_ = true; turn(-1); }
    return true;
  }
  panY_ = std::min(overflowY_, std::max(0.0f, panY_ + dy));
  InvalidateRect(hwnd_, nullptr, FALSE);
  return true;
}

void App::paintPanel(float width) {
  const Palette &p = kThemes[theme_].dark ? kDark : kLight;
  bool fixed = frame_.fixed;
  float pw = 320, ph = fixed ? 196 : 248;
  D2D1_RECT_F r = Rect(width - pw - 16, kTopBar + 4, pw, ph);
  shadow(r, 16, 0.22f);
  fill(r, p.surface, 16);
  stroke(r, p.border, 16);
  hot(r, HotPanel);
  float x = r.left + 20, y = r.top + 18, inner = pw - 40;

  auto stepper = [&](const wchar_t *label, const std::wstring &value, HotId down, HotId up, bool letters) {
    text(label, Rect(x, y, 80, 36), 13, DWRITE_FONT_WEIGHT_NORMAL, p.subtle, DWRITE_TEXT_ALIGNMENT_LEADING,
         DWRITE_PARAGRAPH_ALIGNMENT_CENTER);
    D2D1_RECT_F box = Rect(x + 84, y, inner - 84, 36);
    fill(box, p.field, 18);
    D2D1_RECT_F minus = Rect(box.left, y, 52, 36), plus = Rect(box.right - 52, y, 52, 36);
    if (hoverAmount(down) > 0) fill(minus, Alpha(p.hover, hoverAmount(down)), 18);
    if (hoverAmount(up) > 0) fill(plus, Alpha(p.hover, hoverAmount(up)), 18);
    if (letters) {
      text(L"A", minus, 12, DWRITE_FONT_WEIGHT_SEMI_BOLD, p.text, DWRITE_TEXT_ALIGNMENT_CENTER, DWRITE_PARAGRAPH_ALIGNMENT_CENTER);
      text(L"A", plus, 18, DWRITE_FONT_WEIGHT_SEMI_BOLD, p.text, DWRITE_TEXT_ALIGNMENT_CENTER, DWRITE_PARAGRAPH_ALIGNMENT_CENTER);
    } else {
      icon(kIconMinus, minus, 12, p.text);
      icon(kIconAdd, plus, 12, p.text);
    }
    text(value, box, 14, DWRITE_FONT_WEIGHT_SEMI_BOLD, p.text, DWRITE_TEXT_ALIGNMENT_CENTER, DWRITE_PARAGRAPH_ALIGNMENT_CENTER);
    hot(minus, down);
    hot(plus, up);
    y += 52;
  };

  if (fixed) {
    stepper(L"缩放", std::to_wstring(int(zoom_ * 100 + 0.5f)) + L"%", HotZoomDown, HotZoomUp, false);
  } else {
    stepper(L"字号", std::to_wstring(int(fontSize_)), HotFontDown, HotFontUp, true);
    text(L"行距", Rect(x, y, 80, 36), 13, DWRITE_FONT_WEIGHT_NORMAL, p.subtle, DWRITE_TEXT_ALIGNMENT_LEADING,
         DWRITE_PARAGRAPH_ALIGNMENT_CENTER);
    D2D1_RECT_F seg = Rect(x + 84, y, inner - 84, 36);
    fill(seg, p.field, 18);
    float sw = (seg.right - seg.left) / 3;
    for (int i = 0; i < 3; ++i) {
      D2D1_RECT_F s = Rect(seg.left + i * sw, y, sw, 36);
      if (spacing_ == i) {
        D2D1_RECT_F pill = D2D1::RectF(s.left + 3, s.top + 3, s.right - 3, s.bottom - 3);
        fill(pill, p.surface, 15);
        stroke(pill, p.border, 15);
      } else if (hoverAmount(HotSpacing, i) > 0) {
        fill(D2D1::RectF(s.left + 3, s.top + 3, s.right - 3, s.bottom - 3), Alpha(p.hover, hoverAmount(HotSpacing, i)), 15);
      }
      text(kSpacingName[i], s, 13, spacing_ == i ? DWRITE_FONT_WEIGHT_SEMI_BOLD : DWRITE_FONT_WEIGHT_NORMAL,
           spacing_ == i ? p.text : p.subtle, DWRITE_TEXT_ALIGNMENT_CENTER, DWRITE_PARAGRAPH_ALIGNMENT_CENTER);
      hot(s, HotSpacing, i);
    }
    y += 52;
  }
  text(L"背景", Rect(x, y, 80, 20), 13, DWRITE_FONT_WEIGHT_NORMAL, p.subtle);
  y += 28;
  float slot = inner / kThemeCount;
  for (int i = 0; i < kThemeCount; ++i) {
    float cx = x + slot * i + slot / 2;
    D2D1_RECT_F dot = Rect(cx - 20, y, 40, 40);
    if (theme_ == i) stroke(Rect(cx - 24, y - 4, 48, 48), p.accent, 24, 2);
    fill(dot, Hex(kThemes[i].page), 20);
    stroke(dot, Hex(0x000000, 0.12f), 20);
    if (theme_ == i) icon(kIconCheck, dot, 14, Hex(kThemes[i].ink));
    else text(L"文", dot, 14, DWRITE_FONT_WEIGHT_SEMI_BOLD, Hex(kThemes[i].ink), DWRITE_TEXT_ALIGNMENT_CENTER,
              DWRITE_PARAGRAPH_ALIGNMENT_CENTER);
    text(kThemes[i].name, Rect(cx - 30, y + 48, 60, 18), 12, DWRITE_FONT_WEIGHT_NORMAL,
         theme_ == i ? p.text : p.subtle, DWRITE_TEXT_ALIGNMENT_CENTER);
    hot(Rect(cx - 26, y - 6, 52, 74), HotTheme, i);
  }
}

void App::paintToast(float width, float height) {
  if (toast_.empty()) return;
  ULONGLONG age = GetTickCount64() - toastAt_;
  float alpha = age < 180 ? age / 180.0f : age > 3200 ? std::max(0.0f, 1 - (age - 3200) / 300.0f) : 1.0f;
  if (alpha <= 0) return;
  float left = view_ == View::Shelf ? kSidebar : 0;
  float tw = std::min(measure(toast_, 13, DWRITE_FONT_WEIGHT_SEMI_BOLD) + 56, width - left - 48);
  float rise = (1 - std::min(1.0f, age / 180.0f)) * 10;
  D2D1_RECT_F r = Rect(left + (width - left - tw) / 2, height - 84 + rise, tw, 44);
  shadow(r, 22, 0.25f * alpha);
  Color bg = dark_ ? Hex(0xEDEBE7) : Hex(0x24221F);
  fill(r, Alpha(bg, alpha), 22);
  Color ink = dark_ ? Hex(0x1D1B18) : Hex(0xF7F5F1);
  fill(Rect(r.left + 18, r.top + 18, 8, 8), Alpha(toastError_ ? Hex(0xE5484D) : Hex(0x46A758), alpha), 4);
  text(toast_, D2D1::RectF(r.left + 36, r.top, r.right - 16, r.bottom), 13, DWRITE_FONT_WEIGHT_SEMI_BOLD,
       Alpha(ink, alpha), DWRITE_TEXT_ALIGNMENT_LEADING, DWRITE_PARAGRAPH_ALIGNMENT_CENTER);
}

// ------------------------------------------------------------------------
// Behavior

void App::toast(const std::wstring &message, bool error) {
  toast_ = message;
  toastError_ = error;
  toastAt_ = GetTickCount64();
  startAnimation();
}

void App::startAnimation() {
  if (animating_) return;
  animating_ = true;
  SetTimer(hwnd_, kAnimTimer, 15, nullptr);
}

void App::animate() {
  bool active = false;
  for (auto it = hoverAnim_.begin(); it != hoverAnim_.end();) {
    bool target = hover_.id == HotId(it->first.first) && hover_.arg == it->first.second;
    float goal = target ? 1.0f : 0.0f;
    it->second += (goal - it->second) * 0.28f;
    if (std::fabs(goal - it->second) < 0.01f) it->second = goal;
    else active = true;
    if (!target && it->second == 0) it = hoverAnim_.erase(it);
    else ++it;
  }
  if (std::fabs(scrollTarget_ - scroll_) > 0.5f) { scroll_ += (scrollTarget_ - scroll_) * 0.22f; active = true; }
  else scroll_ = scrollTarget_;
  if (fade_ < 1) { fade_ = std::min(1.0f, fade_ + 0.14f); active = true; if (fade_ >= 1) Release(previous_); }
  if (!toast_.empty()) {
    if (GetTickCount64() - toastAt_ > 3600) toast_.clear();
    else active = true;
  }
  if (opening_ || importing_) { spin_ = std::fmod(spin_ + 9, 360.0f); active = true; }
  InvalidateRect(hwnd_, nullptr, FALSE);
  if (!active) { KillTimer(hwnd_, kAnimTimer); animating_ = false; }
}

ReadStyle App::readStyle() const {
  RECT rc;
  GetClientRect(hwnd_, &rc);
  float s = scale();
  float width = rc.right / s, height = rc.bottom / s;
  float availH = height - kTopBar - kBottomBar - 8;
  ReadStyle style;
  const ReadingTheme &theme = kThemes[theme_];
  style.background = (theme.page << 8) | 0xffu;
  style.foreground = (theme.ink << 8) | 0xffu;
  if (frame_.fixed && reading_) {
    style.pageWidth = std::max(200.0f, width - 160) * s;
    style.pageHeight = std::max(200.0f, availH - 16) * s;
  } else {
    style.pageWidth = std::max(320.0f, std::min(width - 160, 760.0f)) * s;
    style.pageHeight = std::max(320.0f, availH - 16) * s;
  }
  style.fontSize = fontSize_ * s;
  style.lineHeight = kSpacing[spacing_];
  style.margin = std::min(64.0f, std::max(28.0f, (style.pageWidth / s) * 0.075f)) * s;
  style.paragraph = fontSize_ * 0.5f * s;
  style.zoom = zoom_;
  return style;
}

void App::openBook(int64_t id) {
  Book *book = findBook(id);
  if (!book) return;
  reading_ = id;
  bookTitle_ = book->item.title.empty() ? L"未命名" : book->item.title;
  frame_ = Frame();
  frame_.fixed = IsFixedFormat(book->item.format);
  framePixels_ = Pixels();
  Release(page_);
  Release(previous_);
  opening_ = true;
  focusId_ = HotNone;
  panel_ = tocOpen_ = false;
  toc_.clear();
  panX_ = panY_ = overflowX_ = overflowY_ = 0;
  turnsInFlight_ = pendingTurn_ = 0;
  view_ = View::Reader;
  ShowWindow(search_, SW_HIDE);
  SetFocus(hwnd_);
  applyChrome();
  engine_.open(id, readStyle(), ++ticket_);
  startAnimation();
}

void App::closeBook() {
  ++ticket_;
  reading_ = 0;
  opening_ = false;
  focusId_ = HotNone;
  panel_ = tocOpen_ = false;
  toc_.clear();
  overflowX_ = overflowY_ = 0;
  Release(page_);
  Release(previous_);
  framePixels_ = Pixels();
  view_ = View::Shelf;
  ShowWindow(search_, SW_SHOW);
  applyChrome();
  engine_.close();
  InvalidateRect(hwnd_, nullptr, FALSE);
}

void App::turn(int delta) {
  if (!reading_ || opening_) return;
  if (turnsInFlight_) { pendingTurn_ += delta; return; }
  turnsInFlight_++;
  engine_.turn(delta, ticket_);
}

void App::restyle() {
  if (!reading_) return;
  engine_.restyle(readStyle(), ticket_);
  saveSettings();
}

void App::chooseFiles() {
  std::vector<wchar_t> buffer(32768, 0);
  OPENFILENAMEW ofn = {sizeof(ofn)};
  ofn.hwndOwner = hwnd_;
  ofn.lpstrFilter = L"电子书\0*.epub;*.pdf;*.cbz;*.txt;*.mobi;*.azw3;*.fb2;*.docx;*.rtf;*.html;*.htm\0所有文件\0*.*\0";
  ofn.lpstrFile = buffer.data();
  ofn.nMaxFile = DWORD(buffer.size());
  ofn.lpstrTitle = L"导入书籍";
  // NOCHANGEDIR: the dialog must not move the process's current directory.
  ofn.Flags = OFN_ALLOWMULTISELECT | OFN_EXPLORER | OFN_FILEMUSTEXIST | OFN_PATHMUSTEXIST | OFN_NOCHANGEDIR;
  if (!GetOpenFileNameW(&ofn)) return;
  std::vector<std::wstring> paths;
  std::wstring first = buffer.data();
  const wchar_t *p = buffer.data() + first.size() + 1;
  if (!*p) paths.push_back(first);
  for (; *p; p += wcslen(p) + 1) paths.push_back(first + L"\\" + p);
  importing_ = true;
  engine_.import(paths);
  startAnimation();
}

void App::click(float x, float y) {
  const Hot hit = hitTest(x, y);
  focusId_ = HotNone;
  if (confirm_) {
    if (hit.id == HotConfirm) endConfirm(true);
    else if (hit.id != HotConfirmCard) endConfirm(false);
    return;
  }
  if (menuBook_) {
    if (hit.id == HotMenuItem) menuAction(int(hit.arg));
    else if (hit.id != HotMenuCard) { menuBook_ = 0; InvalidateRect(hwnd_, nullptr, FALSE); }
    return;
  }
  if (tocOpen_ && hit.id != HotToc && hit.id != HotTocItem && hit.id != HotTocPanel && hit.id != HotStyle) {
    tocOpen_ = false;
    InvalidateRect(hwnd_, nullptr, FALSE);
    return;
  }
  if (panel_ && hit.id != HotStyle && hit.id != HotToc && hit.id != HotPanel && !(hit.id >= HotFontDown && hit.id <= HotZoomUp)) {
    panel_ = false;
    InvalidateRect(hwnd_, nullptr, FALSE);
    return;
  }
  switch (hit.id) {
    case HotNavAll: filter_ = Filter::All; scroll_ = scrollTarget_ = 0; break;
    case HotNavRecent: filter_ = Filter::Recent; scroll_ = scrollTarget_ = 0; break;
    case HotNavFavorites: filter_ = Filter::Favorites; scroll_ = scrollTarget_ = 0; break;
    case HotImport: if (!importing_) chooseFiles(); break;
    case HotAppearance: setDark(!dark_); saveSettings(); break;
    case HotBook: case HotContinue: openBook(hit.arg); break;
    case HotSearch: SetFocus(search_); break;
    case HotBack: closeBook(); break;
    case HotStyle: panel_ = !panel_; tocOpen_ = false; break;
    case HotToc:
      tocOpen_ = !tocOpen_;
      panel_ = false;
      if (tocOpen_) tocScroll_ = std::max(0, currentToc() - 3) * 40.0f;
      break;
    case HotTocItem:
      if (reading_ && !opening_ && hit.arg >= 0 && size_t(hit.arg) < toc_.size()) engine_.jump(toc_[size_t(hit.arg)].offset, ticket_);
      tocOpen_ = false;
      break;
    case HotFontDown: if (fontSize_ > 12) { fontSize_ -= 1; restyle(); } break;
    case HotFontUp: if (fontSize_ < 40) { fontSize_ += 1; restyle(); } break;
    case HotSpacing: if (spacing_ != int(hit.arg)) { spacing_ = int(hit.arg); restyle(); } break;
    case HotTheme:
      if (theme_ != int(hit.arg)) { theme_ = int(hit.arg); applyChrome(); if (!frame_.fixed) restyle(); else saveSettings(); }
      break;
    case HotZoomDown: if (zoom_ > 0.5f) { zoom_ = std::max(0.5f, zoom_ - 0.1f); restyle(); } break;
    case HotZoomUp: if (zoom_ < 3.0f) { zoom_ = std::min(3.0f, zoom_ + 0.1f); restyle(); } break;
    case HotTrack:
      if (reading_ && !opening_) {
        double f = (x - hit.rect.left) / (hit.rect.right - hit.rect.left);
        engine_.seek(f, ticket_);
      }
      break;
    case HotPrev: turn(-1); break;
    case HotNext: turn(1); break;
    default: if (GetFocus() == search_) SetFocus(hwnd_); break;
  }
  InvalidateRect(hwnd_, nullptr, FALSE);
}

void App::contextMenu(float x, float y) {
  if (menuBook_) { menuBook_ = 0; InvalidateRect(hwnd_, nullptr, FALSE); }
  const Hot hit = hitTest(x, y);
  if (view_ != View::Shelf || (hit.id != HotBook && hit.id != HotContinue)) return;
  Book *book = findBook(hit.arg);
  if (!book) return;
  menuBook_ = book->item.id;
  menuX_ = x;
  menuY_ = y;
  menuIndex_ = -1;
  // What was under the pointer is covered now; its hover fades until the pointer moves.
  hover_ = {{}, HotNone, 0};
  startAnimation();
  SetFocus(hwnd_);
  InvalidateRect(hwnd_, nullptr, FALSE);
}

void App::key(WPARAM vk) {
  bool ctrl = GetKeyState(VK_CONTROL) < 0;
  if (!confirm_ && !menuBook_) {
    if (vk == VK_TAB) { moveFocus(GetKeyState(VK_SHIFT) < 0 ? -1 : 1); return; }
    if (vk == VK_RETURN && focusId_ != HotNone) {
      // Invoke as a click, keeping focus on the control unless the view changed.
      HotId id = focusId_;
      int64_t arg = focusArg_;
      View before = view_;
      for (const Hot &h : hots_)
        if (h.id == id && h.arg == arg) { click((h.rect.left + h.rect.right) / 2, (h.rect.top + h.rect.bottom) / 2); break; }
      if (view_ == before) { focusId_ = id; focusArg_ = arg; }
      return;
    }
  }
  if (confirm_) {
    if (vk == VK_ESCAPE) endConfirm(false);
    else if (vk == VK_RETURN || vk == VK_SPACE) endConfirm(confirmOnRemove_);
    else if (vk == VK_TAB || vk == VK_LEFT || vk == VK_RIGHT) {
      confirmOnRemove_ = !confirmOnRemove_;
      InvalidateRect(hwnd_, nullptr, FALSE);
    }
    return;
  }
  if (menuBook_) {
    if (vk == VK_ESCAPE) menuBook_ = 0;
    else if (vk == VK_DOWN) menuIndex_ = (menuIndex_ + 1) % 3;
    else if (vk == VK_UP) menuIndex_ = (menuIndex_ + 2) % 3;
    else if ((vk == VK_RETURN || vk == VK_SPACE) && menuIndex_ >= 0) { menuAction(menuIndex_); return; }
    InvalidateRect(hwnd_, nullptr, FALSE);
    return;
  }
  if (view_ == View::Reader) {
    switch (vk) {
      case VK_UP: if (!scrollPage(-80)) turn(-1); break;
      case VK_DOWN: if (!scrollPage(80)) turn(1); break;
      case VK_LEFT: case VK_PRIOR: turn(-1); break;
      case VK_RIGHT: case VK_NEXT: case VK_SPACE: turn(1); break;
      case VK_HOME: if (reading_ && !opening_) engine_.seek(0, ticket_); break;
      case VK_END: if (reading_ && !opening_) engine_.seek(1, ticket_); break;
      case VK_ESCAPE:
        if (panel_ || tocOpen_) { panel_ = tocOpen_ = false; InvalidateRect(hwnd_, nullptr, FALSE); }
        else closeBook();
        break;
      case VK_OEM_PLUS: case VK_ADD:
        if (ctrl) { if (frame_.fixed) { zoom_ = std::min(3.0f, zoom_ + 0.1f); } else if (fontSize_ < 40) fontSize_ += 1; restyle(); }
        break;
      case VK_OEM_MINUS: case VK_SUBTRACT:
        if (ctrl) { if (frame_.fixed) { zoom_ = std::max(0.5f, zoom_ - 0.1f); } else if (fontSize_ > 12) fontSize_ -= 1; restyle(); }
        break;
    }
    return;
  }
  if (ctrl && vk == 'O' && !importing_) chooseFiles();
  else if (ctrl && vk == 'F') SetFocus(search_);
}

void App::wheel(int delta) {
  if (confirm_) return;
  if (menuBook_) { menuBook_ = 0; InvalidateRect(hwnd_, nullptr, FALSE); return; }
  if (view_ == View::Reader) {
    if (panel_) return;
    if (tocOpen_) {
      tocScroll_ = std::min(tocScrollMax_, std::max(0.0f, tocScroll_ - delta * 0.6f));
      InvalidateRect(hwnd_, nullptr, FALSE);
      return;
    }
    if (scrollPage(-delta * 0.8f)) return;
    wheelAccum_ += delta;
    while (wheelAccum_ >= WHEEL_DELTA) { wheelAccum_ -= WHEEL_DELTA; turn(-1); }
    while (wheelAccum_ <= -WHEEL_DELTA) { wheelAccum_ += WHEEL_DELTA; turn(1); }
    return;
  }
  scrollTarget_ = std::min(scrollMax_, std::max(0.0f, scrollTarget_ - delta * 1.2f));
  startAnimation();
}

void App::onEvent(std::unique_ptr<EngineEvent> e) {
  switch (e->kind) {
    case EventKind::Ready: ready_ = true; break;
    case EventKind::Shelf: {
      std::map<int64_t, Book> old;
      for (Book &b : books_) old[b.item.id] = b;
      books_.clear();
      for (BookItem &item : e->books) {
        Book b;
        b.item = std::move(item);
        wchar_t key[32], value[64];
        swprintf(key, 32, L"%lld", (long long)b.item.id);
        GetPrivateProfileStringW(L"Progress", key, L"", value, 64, settingsPath_.c_str());
        if (*value) b.progress = std::min(1.0, _wtoi(value) / 10000.0);
        GetPrivateProfileStringW(L"Recent", key, L"", value, 64, settingsPath_.c_str());
        if (*value) b.lastRead = _wtoi64(value);
        books_.push_back(std::move(b));
      }
      for (auto it = covers_.begin(); it != covers_.end();) {
        if (!findBook(it->first)) { Release(it->second.brush); Release(it->second.bitmap); it = covers_.erase(it); }
        else ++it;
      }
      loaded_ = true;
      scrollTarget_ = std::min(scrollTarget_, scrollMax_);
      break;
    }
    case EventKind::Cover: {
      Cover &cover = covers_[e->book];
      Release(cover.brush);
      Release(cover.bitmap);
      cover.pixels = std::move(e->cover);
      cover.bitmap = bitmapFrom(cover.pixels);
      break;
    }
    case EventKind::Imported: {
      importing_ = false;
      std::wstring message;
      if (e->added) message = L"已导入 " + std::to_wstring(e->added) + L" 本书";
      if (e->existing) message += (message.empty() ? L"" : L"，") + std::to_wstring(e->existing) + L" 本已在书架上";
      if (e->failed) message += (message.empty() ? L"" : L"，") + std::to_wstring(e->failed) + L" 个文件失败";
      if (e->failed == 1 && !e->added && !e->existing) message = e->message;
      toast(message, e->failed && !e->added);
      filter_ = Filter::All;
      scroll_ = scrollTarget_ = 0;
      break;
    }
    case EventKind::Opened:
    case EventKind::Page: {
      if (e->ticket != ticket_ || !reading_) return;
      if (e->kind == EventKind::Page && turnsInFlight_) turnsInFlight_--;
      bool turned = page_ && frame_.page != e->frame.page;
      if (e->kind == EventKind::Opened) toc_ = std::move(e->toc);
      if (turned || e->kind == EventKind::Opened) {
        panY_ = enterAtEnd_ && e->frame.page < frame_.page ? 1e9f : 0;
        panX_ = 0;
      }
      enterAtEnd_ = false;
      Release(previous_);
      if (turned) { previous_ = page_; page_ = nullptr; fade_ = 0; }
      else Release(page_);
      framePixels_ = std::move(e->frame.image);
      frame_ = e->frame;
      page_ = bitmapFrom(framePixels_);
      if (!e->title.empty()) bookTitle_ = e->title;
      opening_ = false;
      if (Book *book = findBook(reading_)) {
        book->progress = frame_.progress;
        book->lastRead = (long long)time(nullptr);
        saveBookMeta(*book);
      }
      if (pendingTurn_ && !turnsInFlight_) { int d = pendingTurn_; pendingTurn_ = 0; turn(d); }
      startAnimation();
      break;
    }
    case EventKind::Edge:
      if (e->ticket != ticket_) return;
      if (turnsInFlight_) turnsInFlight_--;
      pendingTurn_ = 0;
      toast(e->message);
      break;
    case EventKind::Error:
      if (e->ticket && e->ticket != ticket_) return;
      if (e->ticket && turnsInFlight_) turnsInFlight_--;
      importing_ = false;
      toast(e->message, true);
      if (e->ticket && opening_) { opening_ = false; closeBook(); toast(e->message, true); }
      break;
  }
  InvalidateRect(hwnd_, nullptr, FALSE);
}

// ------------------------------------------------------------------------
// Window chrome, search field and settings

void App::setDark(bool dark) {
  dark_ = dark;
  pal_ = dark ? kDark : kLight;
  if (searchBrush_) DeleteObject(searchBrush_);
  Color f = pal_.field;
  searchBrush_ = CreateSolidBrush(RGB(int(f.r * 255), int(f.g * 255), int(f.b * 255)));
  applyChrome();
  InvalidateRect(search_, nullptr, TRUE);
  InvalidateRect(hwnd_, nullptr, FALSE);
}

void App::applyChrome() {
  // Title bar follows the visible surface (Windows 11; ignored on older builds).
  bool darkBar = view_ == View::Reader ? kThemes[theme_].dark : dark_;
  BOOL value = darkBar;
  DwmSetWindowAttribute(hwnd_, 20, &value, sizeof(value));
  Color c = view_ == View::Reader ? Hex(kThemes[theme_].surround) : pal_.sidebar;
  COLORREF caption = RGB(int(c.r * 255), int(c.g * 255), int(c.b * 255));
  DwmSetWindowAttribute(hwnd_, 35, &caption, sizeof(caption));
}

void App::updateSearchFont() {
  if (searchFont_) DeleteObject(searchFont_);
  searchFont_ = CreateFontW(-int(14 * scale() + 0.5f), 0, 0, 0, FW_NORMAL, 0, 0, 0, DEFAULT_CHARSET, 0, 0,
                            CLEARTYPE_QUALITY, 0, L"Segoe UI");
  SendMessageW(search_, WM_SETFONT, (WPARAM)searchFont_, TRUE);
  layoutSearch();
}

void App::layoutSearch() {
  RECT rc;
  GetClientRect(hwnd_, &rc);
  float s = scale(), width = rc.right / s;
  float contentW = width - kSidebar - kPad * 2;
  float searchW = std::min(300.0f, contentW * 0.45f);
  float left = width - kPad - searchW + 40, top = 36 + (40 - 20) / 2.0f;
  MoveWindow(search_, int(left * s), int(top * s), int((searchW - 56) * s), int(20 * s), TRUE);
}

void App::loadSettings() {
  wchar_t value[32];
  GetPrivateProfileStringW(L"Studio", L"Dark", L"", value, 32, settingsPath_.c_str());
  if (*value) dark_ = _wtoi(value) != 0;
  else {
    DWORD light = 1, size = sizeof(light);
    RegGetValueW(HKEY_CURRENT_USER, L"Software\\Microsoft\\Windows\\CurrentVersion\\Themes\\Personalize",
                 L"AppsUseLightTheme", RRF_RT_REG_DWORD, nullptr, &light, &size);
    dark_ = light == 0;
  }
  theme_ = std::min(kThemeCount - 1, std::max(0, (int)GetPrivateProfileIntW(L"Studio", L"Theme", dark_ ? 3 : 0, settingsPath_.c_str())));
  spacing_ = std::min(2, std::max(0, (int)GetPrivateProfileIntW(L"Studio", L"Spacing", 1, settingsPath_.c_str())));
  fontSize_ = (float)std::min(40, std::max(12, (int)GetPrivateProfileIntW(L"Studio", L"FontSize", 19, settingsPath_.c_str())));
  zoom_ = std::min(300, std::max(50, (int)GetPrivateProfileIntW(L"Studio", L"Zoom", 100, settingsPath_.c_str()))) / 100.0f;
}

void App::saveSettings() {
  auto put = [&](const wchar_t *key, int v) {
    WritePrivateProfileStringW(L"Studio", key, std::to_wstring(v).c_str(), settingsPath_.c_str());
  };
  put(L"Dark", dark_);
  put(L"Theme", theme_);
  put(L"Spacing", spacing_);
  put(L"FontSize", int(fontSize_));
  put(L"Zoom", int(zoom_ * 100 + 0.5f));
}

void App::saveBookMeta(const Book &book) {
  wchar_t key[32];
  swprintf(key, 32, L"%lld", (long long)book.item.id);
  WritePrivateProfileStringW(L"Progress", key, std::to_wstring(int(book.progress * 10000 + 0.5)).c_str(), settingsPath_.c_str());
  WritePrivateProfileStringW(L"Recent", key, std::to_wstring(book.lastRead).c_str(), settingsPath_.c_str());
}

// The search box's own UI Automation element: the system provides its value
// and text; this adds what it lacks, the name (its cue text is not one) and
// the edit control type.
class SearchAccess final : public IRawElementProviderSimple {
public:
  explicit SearchAccess(HWND hwnd) : hwnd_(hwnd) {}
  ULONG STDMETHODCALLTYPE AddRef() override { return InterlockedIncrement(&refs_); }
  ULONG STDMETHODCALLTYPE Release() override {
    ULONG left = InterlockedDecrement(&refs_);
    if (!left) delete this;
    return left;
  }
  HRESULT STDMETHODCALLTYPE QueryInterface(REFIID riid, void **out) override {
    if (riid != __uuidof(IUnknown) && riid != __uuidof(IRawElementProviderSimple)) { *out = nullptr; return E_NOINTERFACE; }
    *out = static_cast<IRawElementProviderSimple *>(this);
    AddRef();
    return S_OK;
  }
  HRESULT STDMETHODCALLTYPE get_ProviderOptions(ProviderOptions *out) override {
    *out = ProviderOptions(ProviderOptions_ServerSideProvider | ProviderOptions_UseComThreading);
    return S_OK;
  }
  HRESULT STDMETHODCALLTYPE GetPatternProvider(PATTERNID, IUnknown **out) override { *out = nullptr; return S_OK; }
  HRESULT STDMETHODCALLTYPE GetPropertyValue(PROPERTYID property, VARIANT *out) override {
    VariantInit(out);
    if (property == UIA_NamePropertyId) { out->vt = VT_BSTR; out->bstrVal = SysAllocString(L"搜索书名或作者"); }
    else if (property == UIA_ControlTypePropertyId) { out->vt = VT_I4; out->lVal = UIA_EditControlTypeId; }
    return S_OK;
  }
  HRESULT STDMETHODCALLTYPE get_HostRawElementProvider(IRawElementProviderSimple **out) override {
    return UiaHostProviderFromHwnd(hwnd_, out);
  }

private:
  HWND hwnd_;
  LONG refs_ = 1;
};

LRESULT CALLBACK SearchProc(HWND hwnd, UINT message, WPARAM wparam, LPARAM lparam, UINT_PTR, DWORD_PTR) {
  if (message == WM_GETOBJECT && static_cast<long>(lparam) == static_cast<long>(UiaRootObjectId)) {
    SearchAccess *provider = new SearchAccess(hwnd);
    LRESULT result = UiaReturnRawElementProvider(hwnd, wparam, lparam, provider);
    provider->Release();
    return result;
  }
  if (message == WM_DESTROY) UiaReturnRawElementProvider(hwnd, 0, 0, nullptr);
  if (message == WM_KEYDOWN && wparam == VK_TAB) {
    SetFocus(GetParent(hwnd));
    PostMessageW(GetParent(hwnd), WM_KEYDOWN, VK_TAB, 0);
    return 0;
  }
  if (message == WM_CHAR && wparam == VK_TAB) return 0;
  if (message == WM_KEYDOWN && wparam == VK_ESCAPE) {
    SetWindowTextW(hwnd, L"");
    SetFocus(GetParent(hwnd));
    return 0;
  }
  if (message == WM_CHAR && (wparam == VK_ESCAPE || wparam == VK_RETURN)) return 0;
  if (message == WM_SETFOCUS || message == WM_KILLFOCUS) InvalidateRect(GetParent(hwnd), nullptr, FALSE);
  return DefSubclassProc(hwnd, message, wparam, lparam);
}

// ------------------------------------------------------------------------
// UI Automation
//
// The window draws everything itself, so it publishes what it drew: each
// paint turns the hit regions into named elements (buttons, list items) and
// the page into a text element. Providers run on the UI thread (COM
// threading on this STA) and look their element up by (id, arg) on every
// call; one that no longer exists reports itself unavailable.

std::wstring App::accessName(const Hot &h) const {
  auto selected = [](bool on) { return on ? std::wstring(L"，已选中") : std::wstring(); };
  switch (h.id) {
    case HotNavAll: return L"全部书籍";
    case HotNavRecent: return L"最近阅读";
    case HotNavFavorites: return L"我的收藏";
    case HotImport: return L"导入书籍";
    case HotAppearance: return dark_ ? L"深色模式，已开启" : L"深色模式，已关闭";
    case HotBook:
    case HotContinue:
      for (const Book &b : books_) {
        if (b.item.id != h.arg) continue;
        std::wstring progress = b.progress < 0 ? L"未读" : b.progress >= 0.999 ? L"读完"
                                                         : L"已读 " + std::to_wstring(int(b.progress * 100 + 0.5)) + L"%";
        return std::wstring(h.id == HotContinue ? L"继续阅读 " : L"") + (b.item.title.empty() ? L"未命名" : b.item.title) +
               L"，" + (b.item.author.empty() ? L"佚名" : b.item.author) + L"，" + FormatName(b.item.format) + L"，" + progress +
               (b.item.favorite ? L"，已收藏" : L"");
      }
      return {};
    case HotBack: return L"返回书架";
    case HotStyle: return L"阅读设置";
    case HotFontDown: return L"减小字号，当前 " + std::to_wstring(int(fontSize_));
    case HotFontUp: return L"增大字号，当前 " + std::to_wstring(int(fontSize_));
    case HotSpacing: return std::wstring(kSpacingName[h.arg]) + L"行距" + selected(spacing_ == int(h.arg));
    case HotTheme: return std::wstring(kThemes[h.arg].name) + L"背景" + selected(theme_ == int(h.arg));
    case HotZoomDown: return L"缩小，当前 " + std::to_wstring(int(zoom_ * 100 + 0.5f)) + L"%";
    case HotZoomUp: return L"放大，当前 " + std::to_wstring(int(zoom_ * 100 + 0.5f)) + L"%";
    case HotTrack: return L"阅读进度 " + std::to_wstring(int(frame_.progress * 100 + 0.5)) + L"%";
    case HotPrev: return frame_.first ? std::wstring() : L"上一页";
    case HotNext: return frame_.last ? std::wstring() : L"下一页";
    case HotToc: return L"目录";
    case HotTocItem:
      return h.arg >= 0 && size_t(h.arg) < toc_.size() ? toc_[size_t(h.arg)].label + selected(currentToc() == int(h.arg))
                                                        : std::wstring();
    case HotConfirm: return L"移除";
    case HotConfirmCancel: return L"取消";
    case HotMenuItem: {
      const Book *b = nullptr;
      for (const Book &x : books_) if (x.item.id == menuBook_) b = &x;
      if (h.arg == 0) return L"打开";
      if (h.arg == 1) return b && b->item.favorite ? L"取消收藏" : L"加入收藏";
      return L"从书架移除";
    }
    default: return {};
  }
}

const AccessNode *App::accessNode(HotId id, int64_t arg, size_t *index) const {
  for (size_t i = 0; i < access_.size(); ++i)
    if (access_[i].id == id && access_[i].arg == arg) {
      if (index) *index = i;
      return &access_[i];
    }
  return nullptr;
}

class AccessItem final : public IRawElementProviderSimple, public IRawElementProviderFragment, public IInvokeProvider {
public:
  AccessItem(App *app, HotId id, int64_t arg) : app_(app), id_(id), arg_(arg) {}

  // IUnknown
  ULONG STDMETHODCALLTYPE AddRef() override { return InterlockedIncrement(&refs_); }
  ULONG STDMETHODCALLTYPE Release() override {
    ULONG left = InterlockedDecrement(&refs_);
    if (!left) delete this;
    return left;
  }
  HRESULT STDMETHODCALLTYPE QueryInterface(REFIID riid, void **out) override {
    if (riid == __uuidof(IUnknown) || riid == __uuidof(IRawElementProviderSimple)) *out = static_cast<IRawElementProviderSimple *>(this);
    else if (riid == __uuidof(IRawElementProviderFragment)) *out = static_cast<IRawElementProviderFragment *>(this);
    else if (riid == __uuidof(IInvokeProvider)) *out = static_cast<IInvokeProvider *>(this);
    else { *out = nullptr; return E_NOINTERFACE; }
    AddRef();
    return S_OK;
  }

  // IRawElementProviderSimple
  HRESULT STDMETHODCALLTYPE get_ProviderOptions(ProviderOptions *out) override {
    *out = ProviderOptions(ProviderOptions_ServerSideProvider | ProviderOptions_UseComThreading);
    return S_OK;
  }
  HRESULT STDMETHODCALLTYPE GetPatternProvider(PATTERNID pattern, IUnknown **out) override {
    *out = nullptr;
    const AccessNode *node = find();
    if (!node) return UIA_E_ELEMENTNOTAVAILABLE;
    if (pattern == UIA_InvokePatternId && node->invoke) { *out = static_cast<IInvokeProvider *>(this); AddRef(); }
    return S_OK;
  }
  HRESULT STDMETHODCALLTYPE GetPropertyValue(PROPERTYID property, VARIANT *out) override {
    VariantInit(out);
    const AccessNode *node = find();
    if (!node) return UIA_E_ELEMENTNOTAVAILABLE;
    switch (property) {
      case UIA_NamePropertyId: out->vt = VT_BSTR; out->bstrVal = SysAllocString(node->name.c_str()); break;
      case UIA_ControlTypePropertyId: out->vt = VT_I4; out->lVal = node->type; break;
      case UIA_AutomationIdPropertyId: {
        std::wstring id = L"hot-" + std::to_wstring(int(id_)) + L"-" + std::to_wstring(arg_);
        out->vt = VT_BSTR; out->bstrVal = SysAllocString(id.c_str());
        break;
      }
      case UIA_IsEnabledPropertyId: case UIA_IsContentElementPropertyId: case UIA_IsControlElementPropertyId:
        out->vt = VT_BOOL; out->boolVal = VARIANT_TRUE; break;
      case UIA_IsKeyboardFocusablePropertyId:
        out->vt = VT_BOOL; out->boolVal = node->invoke ? VARIANT_TRUE : VARIANT_FALSE; break;
      case UIA_HasKeyboardFocusPropertyId:
        out->vt = VT_BOOL;
        out->boolVal = app_->focusId_ == id_ && app_->focusArg_ == arg_ ? VARIANT_TRUE : VARIANT_FALSE;
        break;
      case UIA_IsInvokePatternAvailablePropertyId: out->vt = VT_BOOL; out->boolVal = node->invoke ? VARIANT_TRUE : VARIANT_FALSE; break;
      default: break;
    }
    return S_OK;
  }
  HRESULT STDMETHODCALLTYPE get_HostRawElementProvider(IRawElementProviderSimple **out) override { *out = nullptr; return S_OK; }

  // IRawElementProviderFragment
  HRESULT STDMETHODCALLTYPE Navigate(NavigateDirection direction, IRawElementProviderFragment **out) override;
  HRESULT STDMETHODCALLTYPE GetRuntimeId(SAFEARRAY **out) override {
    int ids[4] = {UiaAppendRuntimeId, int(id_), int(arg_ & 0x7fffffff), int((arg_ >> 31) & 0x7fffffff)};
    *out = SafeArrayCreateVector(VT_I4, 0, 4);
    if (!*out) return E_OUTOFMEMORY;
    for (LONG i = 0; i < 4; ++i) SafeArrayPutElement(*out, &i, &ids[i]);
    return S_OK;
  }
  HRESULT STDMETHODCALLTYPE get_BoundingRectangle(UiaRect *out) override {
    const AccessNode *node = find();
    if (!node) return UIA_E_ELEMENTNOTAVAILABLE;
    POINT origin = {0, 0};
    ClientToScreen(app_->hwnd_, &origin);
    float k = app_->scale();
    out->left = origin.x + node->rect.left * k;
    out->top = origin.y + node->rect.top * k;
    out->width = (node->rect.right - node->rect.left) * k;
    out->height = (node->rect.bottom - node->rect.top) * k;
    return S_OK;
  }
  HRESULT STDMETHODCALLTYPE GetEmbeddedFragmentRoots(SAFEARRAY **out) override { *out = nullptr; return S_OK; }
  HRESULT STDMETHODCALLTYPE SetFocus() override { return S_OK; }
  HRESULT STDMETHODCALLTYPE get_FragmentRoot(IRawElementProviderFragmentRoot **out) override;

  // IInvokeProvider: performed after this call returns, as a click on the element.
  HRESULT STDMETHODCALLTYPE Invoke() override {
    const AccessNode *node = find();
    if (!node) return UIA_E_ELEMENTNOTAVAILABLE;
    if (!node->invoke) return UIA_E_INVALIDOPERATION;
    PostMessageW(app_->hwnd_, WM_ACCESS_INVOKE, WPARAM(id_), LPARAM(arg_));
    return S_OK;
  }

private:
  const AccessNode *find() const { return g_accessAlive ? app_->accessNode(id_, arg_) : nullptr; }
  App *app_;
  HotId id_;
  int64_t arg_;
  LONG refs_ = 1;
};

class AccessRoot final : public IRawElementProviderSimple, public IRawElementProviderFragment, public IRawElementProviderFragmentRoot {
public:
  explicit AccessRoot(App *app) : app_(app) {}

  ULONG STDMETHODCALLTYPE AddRef() override { return InterlockedIncrement(&refs_); }
  ULONG STDMETHODCALLTYPE Release() override {
    ULONG left = InterlockedDecrement(&refs_);
    if (!left) delete this;
    return left;
  }
  HRESULT STDMETHODCALLTYPE QueryInterface(REFIID riid, void **out) override {
    if (riid == __uuidof(IUnknown) || riid == __uuidof(IRawElementProviderSimple)) *out = static_cast<IRawElementProviderSimple *>(this);
    else if (riid == __uuidof(IRawElementProviderFragment)) *out = static_cast<IRawElementProviderFragment *>(this);
    else if (riid == __uuidof(IRawElementProviderFragmentRoot)) *out = static_cast<IRawElementProviderFragmentRoot *>(this);
    else { *out = nullptr; return E_NOINTERFACE; }
    AddRef();
    return S_OK;
  }

  HRESULT STDMETHODCALLTYPE get_ProviderOptions(ProviderOptions *out) override {
    *out = ProviderOptions(ProviderOptions_ServerSideProvider | ProviderOptions_UseComThreading);
    return S_OK;
  }
  HRESULT STDMETHODCALLTYPE GetPatternProvider(PATTERNID, IUnknown **out) override { *out = nullptr; return S_OK; }
  HRESULT STDMETHODCALLTYPE GetPropertyValue(PROPERTYID property, VARIANT *out) override {
    VariantInit(out);
    if (!g_accessAlive) return UIA_E_ELEMENTNOTAVAILABLE;
    if (property == UIA_NamePropertyId) {
      std::wstring name = app_->view_ == View::Shelf ? L"EXReader 书架" : L"EXReader 阅读 " + app_->bookTitle_;
      out->vt = VT_BSTR;
      out->bstrVal = SysAllocString(name.c_str());
    }
    return S_OK;
  }
  HRESULT STDMETHODCALLTYPE get_HostRawElementProvider(IRawElementProviderSimple **out) override {
    return g_accessAlive ? UiaHostProviderFromHwnd(app_->hwnd_, out) : UIA_E_ELEMENTNOTAVAILABLE;
  }

  HRESULT STDMETHODCALLTYPE Navigate(NavigateDirection direction, IRawElementProviderFragment **out) override {
    *out = nullptr;
    if (!g_accessAlive || app_->access_.empty()) return S_OK;
    const AccessNode *node = direction == NavigateDirection_FirstChild ? &app_->access_.front()
                           : direction == NavigateDirection_LastChild ? &app_->access_.back() : nullptr;
    if (node) *out = new AccessItem(app_, node->id, node->arg);
    return S_OK;
  }
  HRESULT STDMETHODCALLTYPE GetRuntimeId(SAFEARRAY **out) override { *out = nullptr; return S_OK; }
  HRESULT STDMETHODCALLTYPE get_BoundingRectangle(UiaRect *out) override { *out = {}; return S_OK; }
  HRESULT STDMETHODCALLTYPE GetEmbeddedFragmentRoots(SAFEARRAY **out) override { *out = nullptr; return S_OK; }
  HRESULT STDMETHODCALLTYPE SetFocus() override { return S_OK; }
  HRESULT STDMETHODCALLTYPE get_FragmentRoot(IRawElementProviderFragmentRoot **out) override {
    *out = this;
    AddRef();
    return S_OK;
  }

  HRESULT STDMETHODCALLTYPE ElementProviderFromPoint(double x, double y, IRawElementProviderFragment **out) override {
    *out = nullptr;
    if (!g_accessAlive) return S_OK;
    POINT p = {LONG(x), LONG(y)};
    ScreenToClient(app_->hwnd_, &p);
    float k = app_->scale(), cx = p.x / k, cy = p.y / k;
    for (auto it = app_->access_.rbegin(); it != app_->access_.rend(); ++it)
      if (Inside(it->rect, cx, cy)) { *out = new AccessItem(app_, it->id, it->arg); break; }
    return S_OK;
  }
  HRESULT STDMETHODCALLTYPE GetFocus(IRawElementProviderFragment **out) override {
    *out = nullptr;
    if (g_accessAlive && app_->accessNode(app_->focusId_, app_->focusArg_))
      *out = new AccessItem(app_, app_->focusId_, app_->focusArg_);
    return S_OK;
  }

private:
  App *app_;
  LONG refs_ = 1;
};

HRESULT AccessItem::Navigate(NavigateDirection direction, IRawElementProviderFragment **out) {
  *out = nullptr;
  size_t index = 0;
  if (!g_accessAlive || !app_->accessNode(id_, arg_, &index)) return UIA_E_ELEMENTNOTAVAILABLE;
  const std::vector<AccessNode> &all = app_->access_;
  if (direction == NavigateDirection_Parent) {
    if (!app_->accessRoot_) return UIA_E_ELEMENTNOTAVAILABLE;
    *out = app_->accessRoot_;
    (*out)->AddRef();
    return S_OK;
  }
  const AccessNode *node = direction == NavigateDirection_NextSibling && index + 1 < all.size() ? &all[index + 1]
                         : direction == NavigateDirection_PreviousSibling && index > 0 ? &all[index - 1] : nullptr;
  if (node) *out = new AccessItem(app_, node->id, node->arg);
  return S_OK;
}

HRESULT AccessItem::get_FragmentRoot(IRawElementProviderFragmentRoot **out) {
  *out = g_accessAlive ? app_->accessRoot_ : nullptr;
  if (!*out) return UIA_E_ELEMENTNOTAVAILABLE;
  (*out)->AddRef();
  return S_OK;
}

// Rebuilds the elements from this paint's hit regions. Only the confirmation
// or the book menu is offered while one is open, as only it takes input then.
// Structure changes and page turns are raised to listening clients.
void App::publishAccess() {
  std::vector<AccessNode> nodes;
  bool modal = confirm_ || menuBook_;
  for (const Hot &h : hots_) {
    if (modal && !(confirm_ ? (h.id == HotConfirm || h.id == HotConfirmCancel) : h.id == HotMenuItem)) continue;
    // The page sits between the top bar and the page-turn regions in reading order.
    if (h.id == HotPrev && page_ && view_ == View::Reader && !modal) {
      std::wstring text = frame_.fixed || frame_.text.empty()
                            ? L"第 " + std::to_wstring(frame_.page + 1) + L" 页" +
                                (frame_.pageCount ? L"，共 " + std::to_wstring(frame_.pageCount) + L" 页" : L"")
                            : frame_.text;
      nodes.push_back({HotPageText, 0, pageRect_, text, UIA_TextControlTypeId, false});
    }
    std::wstring name = accessName(h);
    if (name.empty()) continue;
    if (std::any_of(nodes.begin(), nodes.end(), [&](const AccessNode &n) { return n.id == h.id && n.arg == h.arg; })) continue;
    CONTROLTYPEID type = h.id == HotBook || h.id == HotContinue || h.id == HotTocItem ? UIA_ListItemControlTypeId
                       : h.id == HotTrack ? UIA_ProgressBarControlTypeId : UIA_ButtonControlTypeId;
    nodes.push_back({h.id, h.arg, h.rect, name, type, h.id != HotTrack});
  }
  // On the shelf the sidebar is painted last but read first.
  std::stable_partition(nodes.begin(), nodes.end(), [](const AccessNode &n) { return n.id >= HotNavAll && n.id <= HotAppearance; });
  std::wstring shape;
  for (const AccessNode &n : nodes) shape += std::to_wstring(int(n.id)) + L":" + std::to_wstring(n.arg) + L":" + n.name + L"\n";
  access_ = std::move(nodes);
  if (!accessRoot_ || !UiaClientsAreListening()) { accessShape_ = shape; return; }
  if (shape != accessShape_) {
    accessShape_ = shape;
    UiaRaiseStructureChangedEvent(accessRoot_, StructureChangeType_ChildrenInvalidated, nullptr, 0);
  }
  std::pair<HotId, int64_t> focus = {focusId_, focusArg_};
  if (focus != focusRaised_ && accessNode(focusId_, focusArg_)) {
    focusRaised_ = focus;
    AccessItem *item = new AccessItem(this, focusId_, focusArg_);
    UiaRaiseAutomationEvent(item, UIA_AutomationFocusChangedEventId);
    item->Release();
  }
  // Announce the page a reader just arrived at.
  std::wstring announce;
  if (view_ == View::Reader && page_ && !opening_)
    announce = L"第 " + std::to_wstring(frame_.page + 1) + L" 页" +
               (frame_.pageCount ? L"，共 " + std::to_wstring(frame_.pageCount) + L" 页" : L"");
  if (!announce.empty() && announce != accessAnnounced_) {
    using Notify = HRESULT(WINAPI *)(IRawElementProviderSimple *, int, int, BSTR, BSTR);
    static Notify notify = (Notify)(void *)GetProcAddress(GetModuleHandleW(L"uiautomationcore.dll"), "UiaRaiseNotificationEvent");
    if (notify) {
      BSTR text = SysAllocString(announce.c_str()), activity = SysAllocString(L"exreader-page");
      notify(accessRoot_, 2 /* ActionCompleted */, 3 /* MostRecent */, text, activity);
      SysFreeString(text);
      SysFreeString(activity);
    }
  }
  accessAnnounced_ = announce;
}

LRESULT CALLBACK WindowProc(HWND hwnd, UINT message, WPARAM wparam, LPARAM lparam) {
  if (g_app) return g_app->handle(hwnd, message, wparam, lparam);
  return DefWindowProcW(hwnd, message, wparam, lparam);
}

LRESULT App::handle(HWND hwnd, UINT message, WPARAM wparam, LPARAM lparam) {
  switch (message) {
    case WM_GETOBJECT:
      if (static_cast<long>(lparam) == static_cast<long>(UiaRootObjectId) && g_accessAlive) {
        if (!accessRoot_) accessRoot_ = new AccessRoot(this);
        return UiaReturnRawElementProvider(hwnd, wparam, lparam, accessRoot_);
      }
      break;
    case WM_ACCESS_INVOKE:
      if (const AccessNode *node = accessNode(HotId(wparam), int64_t(lparam)))
        if (node->invoke) click((node->rect.left + node->rect.right) / 2, (node->rect.top + node->rect.bottom) / 2);
      return 0;
    case WM_ENGINE_EVENT:
      onEvent(std::unique_ptr<EngineEvent>((EngineEvent *)lparam));
      return 0;
    case WM_PAINT: {
      PAINTSTRUCT ps;
      BeginPaint(hwnd, &ps);
      paint();
      EndPaint(hwnd, &ps);
      return 0;
    }
    case WM_ERASEBKGND:
      return 1;
    case WM_SIZE:
      if (target_) target_->Resize(D2D1::SizeU(LOWORD(lparam), HIWORD(lparam)));
      layoutSearch();
      if (view_ == View::Reader && reading_ && wparam != SIZE_MINIMIZED) {
        relayoutPending_ = true;
        SetTimer(hwnd, kRelayoutTimer, 220, nullptr);
      }
      InvalidateRect(hwnd, nullptr, FALSE);
      return 0;
    case WM_DPICHANGED: {
      dpi_ = HIWORD(wparam);
      RECT *r = (RECT *)lparam;
      if (target_) target_->SetDpi(dpi_, dpi_);
      SetWindowPos(hwnd, nullptr, r->left, r->top, r->right - r->left, r->bottom - r->top, SWP_NOZORDER | SWP_NOACTIVATE);
      updateSearchFont();
      discardDevice();
      if (reading_) restyle();
      return 0;
    }
    case WM_GETMINMAXINFO: {
      MINMAXINFO *info = (MINMAXINFO *)lparam;
      // Never larger than the monitor's work area, or a scaled small screen
      // could not hold the window at all.
      MONITORINFO monitor = {sizeof(monitor)};
      LONG minW = LONG(900 * scale()), minH = LONG(620 * scale());
      if (GetMonitorInfoW(MonitorFromWindow(hwnd, MONITOR_DEFAULTTONEAREST), &monitor)) {
        minW = std::min(minW, monitor.rcWork.right - monitor.rcWork.left);
        minH = std::min(minH, monitor.rcWork.bottom - monitor.rcWork.top);
      }
      info->ptMinTrackSize.x = minW;
      info->ptMinTrackSize.y = minH;
      return 0;
    }
    case WM_TIMER:
      if (wparam == kAnimTimer) animate();
      else if (wparam == kRelayoutTimer) {
        KillTimer(hwnd, kRelayoutTimer);
        if (relayoutPending_ && reading_ && !opening_) { relayoutPending_ = false; restyle(); }
      }
      return 0;
    case WM_MOUSEMOVE: {
      mouseX_ = GET_X_LPARAM(lparam) / scale();
      mouseY_ = GET_Y_LPARAM(lparam) / scale();
      if (dragging_) {
        float dx = mouseX_ - dragX_, dy = mouseY_ - dragY_;
        if (std::fabs(dx) + std::fabs(dy) > 4) dragMoved_ = true;
        if (dragMoved_) {
          panX_ = dragPanX_ - dx;
          panY_ = dragPanY_ - dy;
          SetCursor(LoadCursorW(nullptr, IDC_SIZEALL));
          InvalidateRect(hwnd, nullptr, FALSE);
          return 0;
        }
      }
      Hot found = hitTest(mouseX_, mouseY_);
      if (found.id != hover_.id || found.arg != hover_.arg) {
        hover_ = found;
        if (found.id != HotNone && found.id != HotPanel) hoverAnim_.emplace(std::make_pair(int(found.id), found.arg), 0.0f);
        startAnimation();
      }
      bool hand = found.id != HotNone && found.id != HotPanel && found.id != HotPrev && found.id != HotNext &&
                  found.id != HotSearch && found.id != HotTocPanel;
      bool pan = view_ == View::Reader && (overflowX_ > 0 || overflowY_ > 0) && Inside(pageRect_, mouseX_, mouseY_) &&
                 (found.id == HotNone || found.id == HotPrev || found.id == HotNext);
      SetCursor(LoadCursorW(nullptr, found.id == HotSearch ? IDC_IBEAM : pan ? IDC_SIZEALL : hand ? IDC_HAND : IDC_ARROW));
      TRACKMOUSEEVENT tme = {sizeof(tme), TME_LEAVE, hwnd, 0};
      TrackMouseEvent(&tme);
      return 0;
    }
    case WM_MOUSELEAVE:
      hover_ = {{}, HotNone, 0};
      startAnimation();
      return 0;
    case WM_SETCURSOR:
      if (LOWORD(lparam) == HTCLIENT) return TRUE; // set in WM_MOUSEMOVE
      break;
    case WM_LBUTTONDOWN: {
      SetFocus(hwnd);
      float x = GET_X_LPARAM(lparam) / scale(), y = GET_Y_LPARAM(lparam) / scale();
      HotId id = hitTest(x, y).id;
      if (view_ == View::Reader && !panel_ && !tocOpen_ && (overflowX_ > 0 || overflowY_ > 0) && Inside(pageRect_, x, y) &&
          (id == HotNone || id == HotPrev || id == HotNext)) {
        dragging_ = true;
        dragMoved_ = false;
        dragX_ = x, dragY_ = y, dragPanX_ = panX_, dragPanY_ = panY_;
        SetCapture(hwnd);
      }
      return 0;
    }
    case WM_LBUTTONUP:
      if (dragging_) {
        dragging_ = false;
        ReleaseCapture();
        if (dragMoved_) return 0;
      }
      click(GET_X_LPARAM(lparam) / scale(), GET_Y_LPARAM(lparam) / scale());
      return 0;
    case WM_LBUTTONDBLCLK:
      if (view_ == View::Reader) {
        Hot hit = hitTest(GET_X_LPARAM(lparam) / scale(), GET_Y_LPARAM(lparam) / scale());
        if (hit.id == HotPrev || hit.id == HotNext) turn(hit.id == HotPrev ? -1 : 1);
      }
      return 0;
    case WM_RBUTTONUP:
      contextMenu(GET_X_LPARAM(lparam) / scale(), GET_Y_LPARAM(lparam) / scale());
      return 0;
    case WM_MOUSEWHEEL:
      wheel(GET_WHEEL_DELTA_WPARAM(wparam));
      return 0;
    case WM_KEYDOWN:
      key(wparam);
      return 0;
    case WM_COMMAND:
      if (LOWORD(wparam) == kSearchId && HIWORD(wparam) == EN_CHANGE) {
        int n = GetWindowTextLengthW(search_);
        std::wstring q(n, L'\0');
        GetWindowTextW(search_, q.data(), n + 1);
        query_ = q;
        scroll_ = scrollTarget_ = 0;
        InvalidateRect(hwnd, nullptr, FALSE);
      }
      return 0;
    case WM_CTLCOLOREDIT: {
      HDC dc = (HDC)wparam;
      Color f = GetFocus() == search_ ? pal_.surface : pal_.field, t = pal_.text;
      SetBkColor(dc, RGB(int(f.r * 255), int(f.g * 255), int(f.b * 255)));
      SetTextColor(dc, RGB(int(t.r * 255), int(t.g * 255), int(t.b * 255)));
      static HBRUSH focusBrush = nullptr;
      if (GetFocus() == search_) {
        if (focusBrush) DeleteObject(focusBrush);
        focusBrush = CreateSolidBrush(RGB(int(f.r * 255), int(f.g * 255), int(f.b * 255)));
        return (LRESULT)focusBrush;
      }
      return (LRESULT)searchBrush_;
    }
    case WM_DROPFILES: {
      HDROP drop = (HDROP)wparam;
      UINT count = DragQueryFileW(drop, 0xFFFFFFFF, nullptr, 0);
      std::vector<std::wstring> paths;
      for (UINT i = 0; i < count; ++i) {
        UINT n = DragQueryFileW(drop, i, nullptr, 0);
        std::wstring path(n, L'\0');
        DragQueryFileW(drop, i, path.data(), n + 1);
        paths.push_back(path);
      }
      DragFinish(drop);
      if (!paths.empty()) {
        if (view_ == View::Reader) closeBook();
        importing_ = true;
        engine_.import(paths);
        toast(L"正在导入 " + std::to_wstring(paths.size()) + L" 个文件…");
      }
      return 0;
    }
    case WM_SETTINGCHANGE:
      return 0;
    case WM_DESTROY:
      g_accessAlive = false;
      UiaReturnRawElementProvider(hwnd, 0, 0, nullptr);
      if (accessRoot_) { accessRoot_->Release(); accessRoot_ = nullptr; }
      if (!tracePath_.empty())
        if (FILE *f = _wfopen(tracePath_.c_str(), L"ab")) { fputs("exit\n", f); fclose(f); }
      KillTimer(hwnd, kAnimTimer);
      PostQuitMessage(0);
      return 0;
  }
  return DefWindowProcW(hwnd, message, wparam, lparam);
}

int App::run(HINSTANCE instance, int show) {
  wchar_t *local = nullptr;
  if (SUCCEEDED(SHGetKnownFolderPath(FOLDERID_LocalAppData, 0, nullptr, &local))) {
    dataDir_ = std::wstring(local) + L"\\EXReader Studio";
    CoTaskMemFree(local);
  } else {
    dataDir_ = L".\\EXReader Studio";
  }
  // exreader-studio [--data DIR] [--trace FILE] [book ...]: files given here are imported at start.
  std::vector<std::wstring> startup;
  int argc = 0;
  wchar_t **argv = CommandLineToArgvW(GetCommandLineW(), &argc);
  for (int i = 1; argv && i < argc; ++i) {
    if (!wcscmp(argv[i], L"--data") && i + 1 < argc) dataDir_ = argv[++i];
    else if (!wcscmp(argv[i], L"--trace") && i + 1 < argc) tracePath_ = argv[++i];
    else startup.push_back(argv[i]);
  }
  if (argv) LocalFree(argv);
  // Paths from the command line are fixed now, whatever the current directory becomes.
  auto absolute = [](std::wstring &path) {
    if (path.empty()) return;
    wchar_t full[MAX_PATH * 2];
    DWORD n = GetFullPathNameW(path.c_str(), DWORD(std::size(full)), full, nullptr);
    if (n && n < std::size(full)) path = full;
  };
  absolute(dataDir_);
  absolute(tracePath_);
  for (std::wstring &path : startup) absolute(path);
  CreateDirectoryW(dataDir_.c_str(), nullptr);
  settingsPath_ = dataDir_ + L"\\studio.ini";
  loadSettings();

  if (FAILED(D2D1CreateFactory(D2D1_FACTORY_TYPE_SINGLE_THREADED, &factory_)) ||
      FAILED(DWriteCreateFactory(DWRITE_FACTORY_TYPE_SHARED, __uuidof(IDWriteFactory), (IUnknown **)&write_))) {
    MessageBoxW(nullptr, L"无法初始化 Direct2D。", L"EXReader", MB_ICONERROR);
    return 1;
  }
  IDWriteFontCollection *fonts = nullptr;
  if (SUCCEEDED(write_->GetSystemFontCollection(&fonts, FALSE))) {
    UINT32 index;
    BOOL exists = FALSE;
    if (SUCCEEDED(fonts->FindFamilyName(L"Segoe UI Variable Text", &index, &exists)) && exists) uiFamily_ = L"Segoe UI Variable Text";
    exists = FALSE;
    if (FAILED(fonts->FindFamilyName(iconFamily_.c_str(), &index, &exists)) || !exists) iconFamily_ = L"Segoe MDL2 Assets";
    fonts->Release();
  }

  WNDCLASSEXW wc = {sizeof(wc)};
  wc.style = CS_HREDRAW | CS_VREDRAW | CS_DBLCLKS;
  wc.lpfnWndProc = WindowProc;
  wc.hInstance = instance;
  wc.hCursor = LoadCursorW(nullptr, IDC_ARROW);
  wc.hIcon = LoadIconW(instance, MAKEINTRESOURCEW(1));
  wc.lpszClassName = L"EXReaderStudio";
  RegisterClassExW(&wc);

  dpi_ = (float)GetDpiForSystem();
  RECT work = {0, 0, 1920, 1080};
  SystemParametersInfoW(SPI_GETWORKAREA, 0, &work, 0);
  int w = std::min(int(1280 * scale()), int((work.right - work.left) * 0.92f));
  int h = std::min(int(820 * scale()), int((work.bottom - work.top) * 0.92f));
  hwnd_ = CreateWindowExW(WS_EX_ACCEPTFILES, wc.lpszClassName, L"EXReader", WS_OVERLAPPEDWINDOW, work.left + (work.right - work.left - w) / 2,
                          work.top + (work.bottom - work.top - h) / 2, w, h, nullptr, nullptr, instance, nullptr);
  if (!hwnd_) return 1;
  dpi_ = (float)GetDpiForWindow(hwnd_);
  search_ = CreateWindowExW(0, L"EDIT", L"", WS_CHILD | WS_VISIBLE | ES_AUTOHSCROLL, 0, 0, 10, 10, hwnd_,
                            (HMENU)(INT_PTR)kSearchId, instance, nullptr);
  SendMessageW(search_, EM_SETCUEBANNER, TRUE, (LPARAM)L"搜索书名或作者");
  SetWindowSubclass(search_, SearchProc, 1, 0);
  setDark(dark_);
  updateSearchFont();
  ShowWindow(hwnd_, show);
  UpdateWindow(hwnd_);
  g_accessAlive = true;
  engine_.start(hwnd_, dataDir_);
  if (!startup.empty()) {
    importing_ = true;
    engine_.import(startup);
  }

  MSG msg;
  while (GetMessageW(&msg, nullptr, 0, 0)) {
    TranslateMessage(&msg);
    DispatchMessageW(&msg);
  }
  engine_.stop();
  // Drain events the worker posted while shutting down.
  while (PeekMessageW(&msg, nullptr, WM_ENGINE_EVENT, WM_ENGINE_EVENT, PM_REMOVE)) delete (EngineEvent *)msg.lParam;
  discardDevice();
  for (auto &f : formats_) f.second->Release();
  Release(write_);
  Release(factory_);
  if (searchBrush_) DeleteObject(searchBrush_);
  if (searchFont_) DeleteObject(searchFont_);
  return int(msg.wParam);
}

} // namespace

int WINAPI wWinMain(HINSTANCE instance, HINSTANCE, PWSTR, int show) {
  CoInitializeEx(nullptr, COINIT_APARTMENTTHREADED);
  App app;
  g_app = &app;
  int code = app.run(instance, show);
  g_app = nullptr;
  CoUninitialize();
  return code;
}
