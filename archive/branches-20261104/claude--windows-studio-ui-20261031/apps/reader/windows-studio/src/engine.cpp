// SPDX-License-Identifier: MIT
#include "engine.h"
#include <wincodec.h>
#include <algorithm>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>

namespace {

constexpr size_t kImportLimit = size_t(96) * 1024 * 1024;
constexpr UINT kCoverWidth = 240, kCoverHeight = 360;

std::string Utf8(const std::wstring &text) {
  if (text.empty()) return {};
  int size = WideCharToMultiByte(CP_UTF8, 0, text.data(), (int)text.size(), nullptr, 0, nullptr, nullptr);
  std::string out(size, '\0');
  WideCharToMultiByte(CP_UTF8, 0, text.data(), (int)text.size(), out.data(), size, nullptr, nullptr);
  return out;
}

std::wstring Wide(const char *text) {
  if (!text || !*text) return {};
  int size = MultiByteToWideChar(CP_UTF8, 0, text, -1, nullptr, 0);
  std::wstring out(size > 0 ? size - 1 : 0, L'\0');
  if (size > 1) MultiByteToWideChar(CP_UTF8, 0, text, -1, out.data(), size);
  return out;
}

std::wstring StatusText(exr_status status, const exr_error &error) {
  std::wstring detail = Wide(error.message);
  const wchar_t *name = L"未知错误";
  switch (status) {
    case EXR_MEMORY: name = L"内存不足"; break;
    case EXR_IO: name = L"读写失败"; break;
    case EXR_FORMAT: name = L"文件格式无法识别"; break;
    case EXR_UNSUPPORTED: name = L"暂不支持此内容"; break;
    case EXR_LIMIT: name = L"超出大小限制"; break;
    case EXR_DATABASE: name = L"书库访问失败"; break;
    case EXR_CANCELLED: name = L"已取消"; break;
    case EXR_PASSWORD: name = L"文档已加密，需要密码"; break;
    case EXR_FONT: name = L"字体不可用"; break;
    case EXR_ENCODING: name = L"文本编码无法识别"; break;
    default: break;
  }
  return detail.empty() ? name : std::wstring(name) + L"：" + detail;
}

// Straight RGBA (or gray) from the SDK to premultiplied BGRA.
Pixels FromBitmap(const exr_bitmap &bitmap) {
  Pixels out;
  out.w = bitmap.width;
  out.h = bitmap.height;
  out.bgra.resize(size_t(out.w) * out.h);
  for (UINT y = 0; y < out.h; ++y) {
    const unsigned char *row = bitmap.pixels + size_t(y) * bitmap.stride;
    uint32_t *dst = out.bgra.data() + size_t(y) * out.w;
    for (UINT x = 0; x < out.w; ++x) {
      unsigned r, g, b, a = 255;
      if (bitmap.channels == 4) {
        const unsigned char *p = row + x * 4;
        a = p[3];
        r = (p[0] * a + 127) / 255; g = (p[1] * a + 127) / 255; b = (p[2] * a + 127) / 255;
      } else {
        r = g = b = row[x];
      }
      dst[x] = (a << 24) | (r << 16) | (g << 8) | b;
    }
  }
  return out;
}

// A book picture on a reflow page: its pixel rectangle as the SDK fills it,
// the layout box and the decoded source (NULL when unavailable).
struct Picture {
  RECT rect;
  exr_box box;
  const exr_bitmap *source;
};

// Source alpha at page pixel (x, y), sampled exactly as the SDK rasterizer
// scales the picture into its box.
unsigned PictureAlpha(const Picture &picture, UINT x, UINT y) {
  const exr_bitmap *src = picture.source;
  if (!src || src->channels != 4 || !src->width || !src->height) return 255;
  const exr_box &box = picture.box;
  float sx = std::max(0.0f, std::min(float(src->width) - 1, (x + 0.5f - box.x) / box.width * src->width - 0.5f));
  float sy = std::max(0.0f, std::min(float(src->height) - 1, (y + 0.5f - box.y) / box.height * src->height - 0.5f));
  uint32_t x0 = uint32_t(sx), y0 = uint32_t(sy);
  uint32_t x1 = x0 + 1 < src->width ? x0 + 1 : x0, y1 = y0 + 1 < src->height ? y0 + 1 : y0;
  float fx = sx - x0, fy = sy - y0;
  auto a = [&](uint32_t px, uint32_t py) { return float(src->pixels[size_t(py) * src->stride + px * 4 + 3]); };
  float alpha = (1 - fx) * (1 - fy) * a(x0, y0) + fx * (1 - fy) * a(x1, y0) + (1 - fx) * fy * a(x0, y1) + fx * fy * a(x1, y1);
  return std::min(255u, unsigned(lroundf(alpha)));
}

// This SDK renders reflow pages on an opaque white canvas. Map white to the
// theme page color and black to its ink, channel by channel, everywhere but
// the book's own pictures, which keep their colors. Where a picture is
// translucent the canvas (or its box background) shows through; that part is
// moved to the themed color by the share the picture leaves uncovered.
void Recolor(Pixels &pixels, uint32_t background, uint32_t foreground, const std::vector<Picture> &pictures) {
  if (background == 0xffffffffu && foreground == 0x000000ffu) return;
  unsigned char table[3][256];
  for (int c = 0; c < 3; ++c) {
    int shift = 24 - 8 * c; // R, G, B of 0xRRGGBBAA
    int bg = (background >> shift) & 255, ink = (foreground >> shift) & 255;
    for (int v = 0; v < 256; ++v) table[c][v] = (unsigned char)(ink + ((bg - ink) * v + (bg >= ink ? 127 : -127)) / 255);
  }
  for (UINT y = 0; y < pixels.h; ++y)
    for (UINT x = 0; x < pixels.w; ++x) {
      POINT at = {LONG(x), LONG(y)};
      if (std::any_of(pictures.begin(), pictures.end(), [&](const Picture &p) { return PtInRect(&p.rect, at); })) continue;
      uint32_t &p = pixels.bgra[size_t(y) * pixels.w + x];
      uint32_t r = (p >> 16) & 255, g = (p >> 8) & 255, b = p & 255;
      p = (p & 0xff000000u) | (uint32_t(table[0][r]) << 16) | (uint32_t(table[1][g]) << 8) | table[2][b];
    }
  for (const Picture &picture : pictures) {
    int under[3], themed[3];
    unsigned boxAlpha = picture.box.background & 255;
    for (int c = 0; c < 3; ++c) {
      unsigned color = (picture.box.background >> (24 - 8 * c)) & 255;
      under[c] = int((255 * (255 - boxAlpha) + color * boxAlpha + 127) / 255);
      themed[c] = table[c][under[c]];
    }
    for (LONG y = std::max(0L, picture.rect.top); y < std::min(LONG(pixels.h), picture.rect.bottom); ++y)
      for (LONG x = std::max(0L, picture.rect.left); x < std::min(LONG(pixels.w), picture.rect.right); ++x) {
        int open = 255 - int(PictureAlpha(picture, UINT(x), UINT(y)));
        if (!open) continue;
        uint32_t &p = pixels.bgra[size_t(y) * pixels.w + x];
        uint32_t out = p & 0xff000000u;
        for (int c = 0; c < 3; ++c) {
          int shift = 16 - 8 * c; // R, G, B of 0xAARRGGBB
          int v = int((p >> shift) & 255) + ((themed[c] - under[c]) * open + (themed[c] >= under[c] ? 127 : -127)) / 255;
          out |= uint32_t(std::min(255, std::max(0, v))) << shift;
        }
        p = out;
      }
  }
}

// The book's own table of contents (the "toc" navigation), each entry resolved
// to the text offset of its chapter or fragment. Unresolvable entries are left out.
std::vector<TocEntry> ReadToc(const exr_document *doc) {
  std::vector<TocEntry> out;
  exr_navigation *nav = nullptr;
  size_t count = 0, chapterCount = 0, nodeCount = 0;
  exr_error error = {};
  if (exr_document_navigation(doc, &nav, &count, &error) != EXR_OK) return out;
  const exr_chapter *chapters = exr_document_chapters(doc, &chapterCount);
  const exr_node *nodes = exr_document_nodes(doc, &nodeCount);
  std::vector<int> depth(count, 0);
  for (size_t i = 0; i < count; ++i) {
    const exr_navigation &entry = nav[i];
    depth[i] = entry.parent < i ? depth[entry.parent] + 1 : 0;
    if (!entry.role || strcmp(entry.role, "toc") || !entry.label || !*entry.label || entry.part >= chapterCount) continue;
    size_t node = chapters[entry.part].root;
    const char *fragment = entry.href ? strchr(entry.href, '#') : nullptr;
    if (fragment && fragment[1] && chapters[entry.part].path) {
      // Resolve "<chapter file>#fragment" against the chapter itself.
      const char *path = chapters[entry.part].path, *slash = strrchr(path, '/');
      std::string uri = std::string(slash ? slash + 1 : path) + fragment;
      size_t resource = SIZE_MAX, target = SIZE_MAX;
      if (exr_document_resolve(doc, entry.part, uri.c_str(), &resource, &target, &error) == EXR_OK && target < nodeCount)
        node = target;
      error = {};
    }
    if (node < nodeCount) out.push_back({Wide(entry.label), depth[i], nodes[node].start});
  }
  exr_navigation_free(nav, count);
  return out;
}

// Decodes and downsizes an embedded cover with WIC; the worker owns its COM apartment.
bool DecodeCover(const void *data, size_t size, Pixels &out) {
  IWICImagingFactory *factory = nullptr;
  IWICStream *stream = nullptr;
  IWICBitmapDecoder *decoder = nullptr;
  IWICBitmapFrameDecode *frame = nullptr;
  IWICBitmapScaler *scaler = nullptr;
  IWICFormatConverter *converter = nullptr;
  bool ok = false;
  if (SUCCEEDED(CoCreateInstance(CLSID_WICImagingFactory, nullptr, CLSCTX_INPROC_SERVER, IID_PPV_ARGS(&factory))) &&
      SUCCEEDED(factory->CreateStream(&stream)) &&
      SUCCEEDED(stream->InitializeFromMemory((BYTE *)data, (DWORD)size)) &&
      SUCCEEDED(factory->CreateDecoderFromStream(stream, nullptr, WICDecodeMetadataCacheOnDemand, &decoder)) &&
      SUCCEEDED(decoder->GetFrame(0, &frame))) {
    UINT w = 0, h = 0;
    frame->GetSize(&w, &h);
    if (w && h) {
      double scale = std::min(1.0, std::max(double(kCoverWidth) / w, double(kCoverHeight) / h));
      UINT tw = std::max(1u, UINT(w * scale)), th = std::max(1u, UINT(h * scale));
      if (SUCCEEDED(factory->CreateBitmapScaler(&scaler)) &&
          SUCCEEDED(scaler->Initialize(frame, tw, th, WICBitmapInterpolationModeFant)) &&
          SUCCEEDED(factory->CreateFormatConverter(&converter)) &&
          SUCCEEDED(converter->Initialize(scaler, GUID_WICPixelFormat32bppPBGRA, WICBitmapDitherTypeNone,
                                          nullptr, 0, WICBitmapPaletteTypeCustom))) {
        out.w = tw; out.h = th;
        out.bgra.resize(size_t(tw) * th);
        ok = SUCCEEDED(converter->CopyPixels(nullptr, tw * 4, UINT(out.bgra.size() * 4), (BYTE *)out.bgra.data()));
        if (!ok) out = Pixels();
      }
    }
  }
  if (converter) converter->Release();
  if (scaler) scaler->Release();
  if (frame) frame->Release();
  if (decoder) decoder->Release();
  if (stream) stream->Release();
  if (factory) factory->Release();
  return ok;
}

std::wstring ModuleDirectory() {
  wchar_t path[MAX_PATH];
  DWORD n = GetModuleFileNameW(nullptr, path, MAX_PATH);
  std::wstring dir(path, n);
  size_t slash = dir.find_last_of(L"\\/");
  return slash == std::wstring::npos ? L"." : dir.substr(0, slash);
}

exr_font *OpenReadingFont() {
  wchar_t windows[MAX_PATH] = L"C:\\Windows";
  GetWindowsDirectoryW(windows, MAX_PATH);
  std::wstring fonts = std::wstring(windows) + L"\\Fonts\\";
  const std::wstring candidates[] = {
    ModuleDirectory() + L"\\Reader.otf", fonts + L"msyh.ttc", fonts + L"simsun.ttc", fonts + L"segoeui.ttf",
  };
  for (const std::wstring &path : candidates) {
    if (GetFileAttributesW(path.c_str()) == INVALID_FILE_ATTRIBUTES) continue;
    exr_font *font = nullptr;
    exr_error error = {};
    if (exr_font_open(Utf8(path).c_str(), &font, &error) == EXR_OK) return font;
  }
  return nullptr;
}

bool ReadWholeFile(const std::wstring &path, std::vector<unsigned char> &data, exr_status *status) {
  HANDLE file = CreateFileW(path.c_str(), GENERIC_READ, FILE_SHARE_READ, nullptr, OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, nullptr);
  if (file == INVALID_HANDLE_VALUE) { *status = EXR_IO; return false; }
  LARGE_INTEGER size;
  bool ok = GetFileSizeEx(file, &size) && size.QuadPart > 0;
  if (!ok) *status = EXR_FORMAT;
  else if (uint64_t(size.QuadPart) > kImportLimit) { *status = EXR_LIMIT; ok = false; }
  if (ok) {
    data.resize(size_t(size.QuadPart));
    size_t done = 0;
    while (ok && done < data.size()) {
      DWORD chunk = DWORD(std::min<size_t>(data.size() - done, 1u << 24)), got = 0;
      ok = ReadFile(file, data.data() + done, chunk, &got, nullptr) && got;
      done += got;
    }
    if (!ok) *status = EXR_IO;
  }
  CloseHandle(file);
  return ok;
}

std::wstring FileStem(const std::wstring &path) {
  size_t slash = path.find_last_of(L"\\/");
  std::wstring name = slash == std::wstring::npos ? path : path.substr(slash + 1);
  size_t dot = name.find_last_of(L'.');
  return dot == std::wstring::npos || dot == 0 ? name : name.substr(0, dot);
}

char *DupString(const char *text) {
  if (!text) return nullptr;
  size_t n = strlen(text) + 1;
  char *out = (char *)malloc(n);
  if (out) memcpy(out, text, n);
  return out;
}

} // namespace

std::wstring FormatName(exr_format format) {
  switch (format) {
    case EXR_TXT: return L"TXT";
    case EXR_HTML: return L"HTML";
    case EXR_FB2: return L"FB2";
    case EXR_EPUB: return L"EPUB";
    case EXR_DOCX: return L"DOCX";
    case EXR_RTF: return L"RTF";
    case EXR_MOBI: return L"MOBI";
    case EXR_PDF: return L"PDF";
    case EXR_CBZ: return L"CBZ";
    default: return L"BOOK";
  }
}

bool FormatForPath(const std::wstring &path, exr_format *format) {
  size_t dot = path.find_last_of(L'.');
  if (dot == std::wstring::npos) return false;
  const wchar_t *e = path.c_str() + dot;
  struct { const wchar_t *ext; exr_format format; } table[] = {
    {L".epub", EXR_EPUB}, {L".pdf", EXR_PDF}, {L".cbz", EXR_CBZ}, {L".txt", EXR_TXT},
    {L".html", EXR_HTML}, {L".htm", EXR_HTML}, {L".xhtml", EXR_HTML}, {L".fb2", EXR_FB2},
    {L".docx", EXR_DOCX}, {L".rtf", EXR_RTF}, {L".mobi", EXR_MOBI}, {L".azw3", EXR_MOBI},
  };
  for (auto &row : table)
    if (!_wcsicmp(e, row.ext)) { *format = row.format; return true; }
  return false;
}

// ------------------------------------------------------------------------
// Reading session

struct Engine::Session {
  exr_book book = {};
  bool fixed = false;
  exr_document *document = nullptr;
  exr_pager *pager = nullptr;
  exr_fixed_document *fixedDocument = nullptr;
  ReadStyle style;
  size_t page = 0, pageCount = 0, textSize = 0, pageStart = 0;
  size_t lastPage = SIZE_MAX; // first reflow page index known to be the end
  std::vector<TocEntry> toc;
  ~Session() {
    if (pager) exr_pager_free(pager);
    if (document) exr_document_free(document);
    if (fixedDocument) exr_fixed_free(fixedDocument);
    free(book.title); free(book.author); free(book.tags);
  }
};

Engine::Engine() = default;
Engine::~Engine() { stop(); }

void Engine::start(HWND window, const std::wstring &dataDir) {
  window_ = window;
  dataDir_ = dataDir;
  thread_ = std::thread([this] { run(); });
  post([this] {
    CreateDirectoryW(dataDir_.c_str(), nullptr);
    exr_error error = {};
    exr_status status = exr_library_open(Utf8(dataDir_ + L"\\library.sqlite").c_str(), &library_, &error);
    if (status != EXR_OK) { fail(EventKind::Error, 0, L"无法打开书库", status, error); return; }
    font_ = OpenReadingFont();
    if (!font_) {
      auto event = std::make_unique<EngineEvent>();
      event->kind = EventKind::Error;
      event->message = L"找不到可用的阅读字体，流式排版书籍将无法打开。";
      emit(std::move(event));
    }
    auto ready = std::make_unique<EngineEvent>();
    ready->kind = EventKind::Ready;
    emit(std::move(ready));
    doRefresh();
  });
}

void Engine::stop() {
  if (!thread_.joinable()) return;
  post([this] {
    doClose();
    if (library_) exr_library_close(library_);
    if (font_) exr_font_free(font_);
    library_ = nullptr; font_ = nullptr;
  });
  {
    std::lock_guard<std::mutex> lock(mutex_);
    quit_ = true;
  }
  wake_.notify_all();
  thread_.join();
}

void Engine::post(std::function<void()> task) {
  {
    std::lock_guard<std::mutex> lock(mutex_);
    queue_.push_back(std::move(task));
  }
  wake_.notify_one();
}

void Engine::emit(std::unique_ptr<EngineEvent> event) {
  if (!PostMessageW(window_, WM_ENGINE_EVENT, 0, (LPARAM)event.get())) return;
  event.release();
}

void Engine::fail(EventKind kind, uint64_t ticket, const wchar_t *what, exr_status status, const exr_error &error) {
  auto event = std::make_unique<EngineEvent>();
  event->kind = kind;
  event->ticket = ticket;
  event->message = std::wstring(what) + L"：" + StatusText(status, error);
  emit(std::move(event));
}

void Engine::run() {
  CoInitializeEx(nullptr, COINIT_MULTITHREADED);
  for (;;) {
    std::function<void()> task;
    {
      std::unique_lock<std::mutex> lock(mutex_);
      wake_.wait(lock, [this] { return quit_ || !queue_.empty(); });
      if (queue_.empty()) break;
      task = std::move(queue_.front());
      queue_.pop_front();
    }
    task();
  }
  CoUninitialize();
}

// ------------------------------------------------------------------------
// Bookshelf

void Engine::refresh() { post([this] { doRefresh(); }); }

void Engine::doRefresh() {
  if (!library_) return;
  exr_book *books = nullptr;
  size_t count = 0;
  exr_error error = {};
  exr_status status = exr_library_books(library_, "", &books, &count, &error);
  if (status != EXR_OK) { fail(EventKind::Error, 0, L"读取书架失败", status, error); return; }
  auto event = std::make_unique<EngineEvent>();
  event->kind = EventKind::Shelf;
  std::vector<std::pair<int64_t, exr_format>> covers;
  for (size_t i = 0; i < count; ++i) {
    BookItem item;
    item.id = books[i].id;
    item.title = Wide(books[i].title);
    item.author = Wide(books[i].author);
    item.format = books[i].format;
    item.position = books[i].position;
    item.favorite = books[i].favorite != 0;
    if (!coverTried_.count(item.id)) covers.emplace_back(item.id, item.format);
    event->books.push_back(std::move(item));
  }
  exr_books_free(books, count);
  emit(std::move(event));
  // One task per cover so user actions queued meanwhile are not held up.
  for (auto &cover : covers) {
    coverTried_.insert(cover.first);
    post([this, cover] { doCover(cover.first, cover.second); });
  }
}

void Engine::doCover(int64_t id, exr_format format) {
  if (!library_) return;
  auto event = std::make_unique<EngineEvent>();
  event->kind = EventKind::Cover;
  event->book = id;
  void *data = nullptr;
  size_t size = 0;
  exr_error error = {};
  if (exr_library_blob(library_, id, 1, &data, &size, &error) == EXR_OK && data && size)
    DecodeCover(data, size, event->cover);
  exr_free(data);
  if (event->cover.empty() && IsFixedFormat(format)) {
    // No stored cover: a fixed book's first page is its cover.
    exr_fixed_open_options options = {};
    options.struct_size = sizeof(options);
    options.fallback_font = font_;
    exr_fixed_document *document = nullptr;
    error = {};
    if (exr_library_fixed_source(library_, id, &options, &document, &error) == EXR_OK) {
      size_t count = 0;
      const exr_fixed_page *pages = exr_fixed_pages(document, &count);
      if (pages && count) {
        const exr_page_geometry &g = pages[0].geometry;
        double w = (g.bounds[2] - g.bounds[0]) * g.unit_scale, h = (g.bounds[3] - g.bounds[1]) * g.unit_scale;
        if (w > 0 && h > 0) {
          exr_fixed_render_options render = {};
          render.channels = 4;
          render.background = 0xffffffffu;
          exr_bitmap bitmap = {};
          if (exr_fixed_render(document, 0, std::min(kCoverWidth / w, kCoverHeight / h), &render, &bitmap, &error) == EXR_OK) {
            event->cover = FromBitmap(bitmap);
            exr_bitmap_free(&bitmap);
          }
        }
      }
      exr_fixed_free(document);
    }
  }
  if (!event->cover.empty()) emit(std::move(event));
}

void Engine::import(const std::vector<std::wstring> &paths) { post([this, paths] { doImport(paths); }); }

void Engine::doImport(const std::vector<std::wstring> &paths) {
  if (!library_) return;
  auto event = std::make_unique<EngineEvent>();
  event->kind = EventKind::Imported;
  std::map<int64_t, std::wstring> created;
  std::wstring lastError;
  for (const std::wstring &path : paths) {
    exr_format format;
    if (!FormatForPath(path, &format)) {
      event->failed++;
      lastError = FileStem(path) + L"：不支持的文件类型";
      continue;
    }
    exr_error error = {};
    exr_status status;
    int64_t id = 0;
    int isNew = 0;
    if (IsFixedFormat(format)) {
      // PDF/CBZ stream straight from disk; nothing is materialized on the heap.
      status = exr_library_import_file_unique(library_, format, Utf8(path).c_str(), nullptr, &id, &isNew, &error);
    } else {
      std::vector<unsigned char> data;
      if (ReadWholeFile(path, data, &status))
        status = exr_library_import_unique(library_, format, data.data(), data.size(), nullptr, &id, &isNew, &error);
    }
    if (status != EXR_OK) {
      event->failed++;
      lastError = FileStem(path) + L"：" + StatusText(status, error);
      continue;
    }
    if (isNew) { event->added++; created[id] = FileStem(path); }
    else event->existing++;
    event->book = id;
  }
  // Books without an embedded title are named after their file.
  if (!created.empty()) {
    exr_book *books = nullptr;
    size_t count = 0;
    exr_error error = {};
    if (exr_library_books(library_, "", &books, &count, &error) == EXR_OK) {
      for (size_t i = 0; i < count; ++i) {
        auto it = created.find(books[i].id);
        if (it == created.end() || (books[i].title && *books[i].title && strcmp(books[i].title, "Untitled"))) continue;
        std::string title = Utf8(it->second);
        exr_book copy = books[i];
        copy.title = title.data();
        exr_library_update(library_, &copy, &error);
      }
      exr_books_free(books, count);
    }
  }
  event->message = lastError;
  emit(std::move(event));
  doRefresh();
}

void Engine::remove(int64_t id) {
  post([this, id] {
    if (!library_) return;
    if (session_ && session_->book.id == id) doClose();
    exr_error error = {};
    exr_status status = exr_library_delete(library_, id, &error);
    if (status != EXR_OK) fail(EventKind::Error, 0, L"删除失败", status, error);
    coverTried_.erase(id);
    doRefresh();
  });
}

void Engine::favorite(int64_t id, bool value) {
  post([this, id, value] {
    if (!library_) return;
    exr_book *books = nullptr;
    size_t count = 0;
    exr_error error = {};
    exr_status status = exr_library_books(library_, "", &books, &count, &error);
    for (size_t i = 0; status == EXR_OK && i < count; ++i) {
      if (books[i].id != id) continue;
      books[i].favorite = value;
      status = exr_library_update(library_, &books[i], &error);
      if (session_ && session_->book.id == id) session_->book.favorite = value;
    }
    if (books) exr_books_free(books, count);
    if (status != EXR_OK) fail(EventKind::Error, 0, L"更新收藏失败", status, error);
    doRefresh();
  });
}

// ------------------------------------------------------------------------
// Reading

exr_status Engine::buildPager(exr_error *error) {
  Session &s = *session_;
  if (s.pager) { exr_pager_free(s.pager); s.pager = nullptr; }
  exr_layout_config config = exr_layout_config_defaults();
  config.page.width = s.style.pageWidth;
  config.page.height = s.style.pageHeight;
  config.page.margin = s.style.margin;
  config.page.font_size = s.style.fontSize;
  config.page.line_height = s.style.lineHeight;
  config.page.paragraph_spacing = s.style.paragraph;
  // Text is laid out black on the SDK's white canvas; render() maps it to the theme.
  config.user_css = "*{color:#000000FF}\n";
  exr_status status = exr_pager_create(s.document, font_, &config, &s.pager, error);
  if (status == EXR_OK) status = exr_pager_set_cache(s.pager, 3, 0, error);
  if (status == EXR_OK) status = exr_pager_set_checkpoints(s.pager, 8, 4 * 1024 * 1024, 8, error);
  s.lastPage = SIZE_MAX;
  return status;
}

// Last page whose start is at or before offset; a resident pager reports
// EXR_ARGUMENT past its final page.
exr_status Engine::pageForOffset(size_t offset, size_t *page, exr_error *error) {
  Session &s = *session_;
  const exr_layout *layout = nullptr;
  size_t count = 0;
  auto startOf = [&](size_t index, size_t *start) -> exr_status {
    exr_status status = exr_pager_get(s.pager, index, &layout, error);
    if (status != EXR_OK) return status;
    const exr_page *info = exr_layout_pages(layout, &count);
    if (!info || !count) return EXR_FORMAT;
    *start = info->start;
    return EXR_OK;
  };
  size_t start = 0, lo = 0, hi = 1;
  exr_status status = startOf(0, &start);
  if (status != EXR_OK) return status;
  for (int guard = 0; guard < 40; ++guard) {
    status = startOf(hi, &start);
    if (status == EXR_ARGUMENT) { *error = {}; s.lastPage = std::min(s.lastPage, hi); break; }
    if (status != EXR_OK) return status;
    if (start > offset) break;
    lo = hi;
    hi *= 2;
  }
  while (lo + 1 < hi) {
    size_t mid = lo + (hi - lo) / 2;
    status = startOf(mid, &start);
    if (status == EXR_OK && start <= offset) lo = mid;
    else if (status == EXR_OK || status == EXR_ARGUMENT) hi = mid;
    else return status;
    *error = {};
  }
  *page = lo;
  return EXR_OK;
}

exr_status Engine::render(size_t page, Frame &frame, exr_error *error) {
  Session &s = *session_;
  exr_bitmap bitmap = {};
  exr_status status;
  std::vector<Picture> pictures; // borrowed from the pager's layout, valid through Recolor
  frame = Frame();
  frame.book = s.book.id;
  frame.fixed = s.fixed;
  if (s.fixed) {
    size_t count = 0;
    const exr_fixed_page *pages = exr_fixed_pages(s.fixedDocument, &count);
    if (!pages || page >= count) return EXR_ARGUMENT;
    const exr_page_geometry &g = pages[page].geometry;
    double w = (g.bounds[2] - g.bounds[0]) * g.unit_scale, h = (g.bounds[3] - g.bounds[1]) * g.unit_scale;
    if (g.rotation == 90 || g.rotation == 270) std::swap(w, h);
    if (!(w > 0) || !(h > 0)) return EXR_FORMAT;
    double scale = std::min(s.style.pageWidth / w, s.style.pageHeight / h) * s.style.zoom;
    scale = std::min(scale, std::min(4096.0 / w, 4096.0 / h));
    exr_fixed_render_options options = {};
    options.channels = 4;
    options.background = 0xffffffffu;
    status = exr_fixed_render(s.fixedDocument, page, scale, &options, &bitmap, error);
    if (status != EXR_OK) return status;
    frame.pageCount = count;
    frame.last = page + 1 >= count;
    frame.progress = count > 1 ? double(page) / double(count - 1) : 1.0;
  } else {
    const exr_layout *layout = nullptr;
    size_t count = 0;
    status = exr_pager_get(s.pager, page, &layout, error);
    if (status == EXR_ARGUMENT) s.lastPage = std::min(s.lastPage, page);
    if (status != EXR_OK) return status;
    const exr_page *info = exr_layout_pages(layout, &count);
    if (!info || !count) return EXR_FORMAT;
    s.pageStart = info->start;
    frame.start = info->start;
    frame.end = info->end;
    size_t textSize = 0;
    const char *text = exr_document_text(s.document, &textSize);
    if (text && info->start < info->end && info->end <= textSize)
      frame.text = Wide(std::string(text + info->start, info->end - info->start).c_str());
    size_t boxCount = 0;
    const exr_box *boxes = exr_layout_boxes(layout, &boxCount);
    for (size_t i = info->box_start; boxes && i < info->box_start + info->box_count && i < boxCount; ++i)
      if (boxes[i].kind == EXR_BOX_IMAGE && !boxes[i].flags && boxes[i].width > 0 && boxes[i].height > 0) {
        const exr_box &b = boxes[i];
        RECT rect = {LONG(ceilf(b.x)), LONG(ceilf(b.y)), LONG(ceilf(b.x + b.width)), LONG(ceilf(b.y + b.height))};
        pictures.push_back({rect, b, exr_layout_image(layout, b.resource)});
        frame.pictures.push_back(rect);
      }
    status = exr_render_page_ex(layout, exr_layout_font(layout), 0, 4, nullptr, &bitmap, error);
    if (status != EXR_OK) return status;
    bool atEnd = info->end >= s.textSize;
    if (atEnd) s.lastPage = std::min(s.lastPage, page + 1);
    frame.last = atEnd || page + 1 >= s.lastPage;
    frame.pageCount = s.lastPage != SIZE_MAX ? s.lastPage : 0;
    frame.progress = s.textSize ? std::min(1.0, double(info->end) / double(s.textSize)) : 1.0;
  }
  frame.page = page;
  frame.first = page == 0;
  frame.image = FromBitmap(bitmap);
  exr_bitmap_free(&bitmap);
  if (!s.fixed) Recolor(frame.image, s.style.background, s.style.foreground, pictures);
  return EXR_OK;
}

void Engine::present(EventKind kind, uint64_t ticket, size_t page) {
  auto event = std::make_unique<EngineEvent>();
  event->kind = kind;
  event->ticket = ticket;
  exr_error error = {};
  exr_status status = render(page, event->frame, &error);
  if (status != EXR_OK) { fail(EventKind::Error, ticket, L"无法显示此页", status, error); return; }
  session_->page = page;
  event->title = Wide(session_->book.title);
  if (kind == EventKind::Opened) event->toc = session_->toc;
  emit(std::move(event));
  saveProgress();
}

void Engine::saveProgress() {
  if (!session_ || !library_) return;
  Session &s = *session_;
  exr_error error = {};
  if (s.fixed) {
    s.book.position = s.page;
    exr_library_update(library_, &s.book, &error);
  } else {
    exr_anchor anchor = {};
    if (exr_anchor_create(s.document, s.pageStart, s.pageStart, &anchor, &error) == EXR_OK) {
      exr_library_progress(library_, s.book.id, &anchor, &error);
      exr_anchor_free(&anchor);
    }
  }
}

void Engine::open(int64_t id, const ReadStyle &style, uint64_t ticket) {
  post([this, id, style, ticket] { doOpen(id, style, ticket); });
}

void Engine::doOpen(int64_t id, const ReadStyle &style, uint64_t ticket) {
  doClose();
  if (!library_) return;
  exr_error error = {};
  exr_book *books = nullptr;
  size_t count = 0;
  exr_status status = exr_library_books(library_, "", &books, &count, &error);
  if (status != EXR_OK) { fail(EventKind::Error, ticket, L"无法读取书籍信息", status, error); return; }
  auto session = std::make_unique<Session>();
  for (size_t i = 0; i < count; ++i) {
    if (books[i].id != id) continue;
    session->book = books[i];
    session->book.title = DupString(books[i].title);
    session->book.author = DupString(books[i].author);
    session->book.tags = DupString(books[i].tags);
  }
  exr_books_free(books, count);
  if (!session->book.id) { fail(EventKind::Error, ticket, L"无法打开", EXR_ARGUMENT, error); return; }
  session->fixed = IsFixedFormat(session->book.format);
  session->style = style;
  session_ = std::move(session);
  Session &s = *session_;
  size_t page = 0;
  if (s.fixed) {
    exr_fixed_open_options options = {};
    options.struct_size = sizeof(options);
    options.fallback_font = font_;
    status = exr_library_fixed_source(library_, id, &options, &s.fixedDocument, &error);
    if (status == EXR_OK) {
      exr_fixed_pages(s.fixedDocument, &s.pageCount);
      if (!s.pageCount) status = EXR_FORMAT;
      page = std::min(s.book.position, s.pageCount ? s.pageCount - 1 : 0);
    }
  } else {
    exr_library_epub_info info = {sizeof(info), 0, 0};
    if (!font_) status = EXR_UNSUPPORTED;
    else if (s.book.format == EXR_EPUB && exr_library_epub_info_get(library_, id, &info, &error) == EXR_OK && info.bounded_storage) {
      status = EXR_UNSUPPORTED;
      snprintf(error.message, sizeof(error.message), "this EPUB uses chapter-bounded storage");
    } else {
      error = {};
      status = exr_library_document(library_, id, &s.document, &error);
    }
    if (status == EXR_OK) {
      exr_document_text(s.document, &s.textSize);
      s.toc = ReadToc(s.document);
      status = buildPager(&error);
    }
    if (status == EXR_OK) {
      // Resume from the saved selector; a moved or legacy point falls back to its offset.
      exr_anchor anchor = {};
      exr_anchor_state state = EXR_ANCHOR_MISSING;
      size_t offset = s.book.position;
      if (exr_library_progress_get(library_, id, &anchor, &state, &error) == EXR_OK) {
        offset = anchor.start;
        exr_anchor_match match = {};
        if (state == EXR_ANCHOR_FOUND && exr_anchor_resolve_ex(s.document, &anchor, nullptr, &match, &error) == EXR_OK &&
            match.state == EXR_ANCHOR_FOUND)
          offset = match.start;
        if (state == EXR_ANCHOR_MISSING) offset = 0;
      }
      exr_anchor_free(&anchor);
      error = {};
      if (offset > s.textSize) offset = 0;
      status = pageForOffset(offset, &page, &error);
    }
  }
  if (status != EXR_OK) {
    session_.reset();
    fail(EventKind::Error, ticket, L"无法打开这本书", status, error);
    return;
  }
  present(EventKind::Opened, ticket, page);
}

void Engine::turn(int delta, uint64_t ticket) {
  post([this, delta, ticket] {
    if (!session_) return;
    Session &s = *session_;
    long long target = (long long)s.page + delta;
    bool before = target < 0;
    bool after = s.fixed ? target >= (long long)s.pageCount : (size_t)target >= s.lastPage;
    if (!before && !after) {
      auto event = std::make_unique<EngineEvent>();
      event->kind = EventKind::Page;
      event->ticket = ticket;
      exr_error error = {};
      exr_status status = render(size_t(target), event->frame, &error);
      if (status == EXR_OK) {
        s.page = size_t(target);
        emit(std::move(event));
        saveProgress();
        return;
      }
      if (status != EXR_ARGUMENT) { fail(EventKind::Error, ticket, L"无法显示此页", status, error); return; }
      after = true;
    }
    auto edge = std::make_unique<EngineEvent>();
    edge->kind = EventKind::Edge;
    edge->ticket = ticket;
    edge->message = before ? L"已经是第一页" : L"已经读到最后一页";
    emit(std::move(edge));
  });
}

void Engine::seek(double fraction, uint64_t ticket) {
  post([this, fraction, ticket] {
    if (!session_) return;
    Session &s = *session_;
    double f = std::min(1.0, std::max(0.0, fraction));
    size_t page = 0;
    if (s.fixed) page = size_t(std::lround(f * double(s.pageCount - 1)));
    else {
      exr_error error = {};
      exr_status status = pageForOffset(size_t(f * double(s.textSize)), &page, &error);
      if (status != EXR_OK) { fail(EventKind::Error, ticket, L"跳转失败", status, error); return; }
    }
    present(EventKind::Page, ticket, page);
  });
}

void Engine::jump(size_t offset, uint64_t ticket) {
  post([this, offset, ticket] {
    if (!session_ || session_->fixed) return;
    size_t page = 0;
    exr_error error = {};
    exr_status status = pageForOffset(std::min(offset, session_->textSize), &page, &error);
    if (status != EXR_OK) { fail(EventKind::Error, ticket, L"跳转失败", status, error); return; }
    present(EventKind::Page, ticket, page);
  });
}

void Engine::restyle(const ReadStyle &style, uint64_t ticket) {
  post([this, style, ticket] {
    if (!session_) return;
    Session &s = *session_;
    s.style = style;
    size_t page = s.page;
    if (!s.fixed) {
      size_t offset = s.pageStart;
      exr_error error = {};
      exr_status status = buildPager(&error);
      if (status == EXR_OK) status = pageForOffset(offset, &page, &error);
      if (status != EXR_OK) { fail(EventKind::Error, ticket, L"重新排版失败", status, error); return; }
    }
    present(EventKind::Page, ticket, page);
  });
}

void Engine::close() {
  post([this] {
    doClose();
    doRefresh();
  });
}

void Engine::doClose() {
  if (!session_) return;
  saveProgress();
  session_.reset();
}
