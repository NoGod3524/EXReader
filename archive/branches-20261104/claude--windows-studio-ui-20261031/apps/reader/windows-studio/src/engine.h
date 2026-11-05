// SPDX-License-Identifier: MIT
// EXReader Studio: the SDK side of the client. Every exr_* call runs on one
// worker thread; the UI thread only enqueues requests and receives events.
#pragma once
#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#ifndef UNICODE
#define UNICODE
#endif
#include <windows.h>
#include <exreader.h>
#include <condition_variable>
#include <cstdint>
#include <deque>
#include <functional>
#include <map>
#include <memory>
#include <mutex>
#include <set>
#include <string>
#include <thread>
#include <vector>

#define WM_ENGINE_EVENT (WM_APP + 40)

// Premultiplied BGRA, ready for a Direct2D bitmap.
struct Pixels {
  UINT w = 0, h = 0;
  std::vector<uint32_t> bgra;
  bool empty() const { return bgra.empty(); }
};

struct BookItem {
  int64_t id = 0;
  std::wstring title, author;
  exr_format format = EXR_CUSTOM;
  size_t position = 0;
  bool favorite = false;
};

// Reading style in device pixels; colors are 0xRRGGBBAA as the SDK expects.
struct ReadStyle {
  float pageWidth = 720, pageHeight = 1000;
  float fontSize = 28, lineHeight = 1.6f, margin = 56, paragraph = 10;
  uint32_t background = 0xffffffffu, foreground = 0x1f1f1fffu;
  float zoom = 1.0f; // fixed formats only, multiplies the fit-to-page scale
};

// One table-of-contents entry: nesting depth and whole-text offset of its target.
struct TocEntry {
  std::wstring label;
  int depth = 0;
  size_t offset = 0;
};

struct Frame {
  int64_t book = 0;
  size_t page = 0, pageCount = 0; // pageCount is 0 while a reflow book's end is unknown
  size_t start = 0, end = 0;      // whole-text range a reflow page shows
  bool fixed = false, first = false, last = false;
  double progress = 0;
  Pixels image;
  std::vector<RECT> pictures; // book images on a reflow page, in image pixels
  std::wstring text;          // the reflow page's text, for screen readers
};

enum class EventKind { Ready, Shelf, Cover, Imported, Opened, Page, Edge, Error };

struct EngineEvent {
  EventKind kind = EventKind::Error;
  uint64_t ticket = 0;
  std::vector<BookItem> books;
  int64_t book = 0;
  Pixels cover;
  Frame frame;
  std::vector<TocEntry> toc; // Opened only
  std::wstring title, message;
  int added = 0, existing = 0, failed = 0;
};

class Engine {
public:
  Engine();
  ~Engine();
  void start(HWND window, const std::wstring &dataDir);
  void stop();

  void refresh();
  void import(const std::vector<std::wstring> &paths);
  void remove(int64_t id);
  void favorite(int64_t id, bool value);
  void open(int64_t id, const ReadStyle &style, uint64_t ticket);
  void turn(int delta, uint64_t ticket);
  void seek(double fraction, uint64_t ticket);
  void jump(size_t offset, uint64_t ticket); // reflow books: the page holding a text offset
  void restyle(const ReadStyle &style, uint64_t ticket);
  void close();

private:
  struct Session;
  void post(std::function<void()> task);
  void emit(std::unique_ptr<EngineEvent> event);
  void fail(EventKind kind, uint64_t ticket, const wchar_t *what, exr_status status, const exr_error &error);
  void run();

  void doRefresh();
  void doCover(int64_t id, exr_format format);
  void doImport(const std::vector<std::wstring> &paths);
  void doOpen(int64_t id, const ReadStyle &style, uint64_t ticket);
  void doClose();
  exr_status buildPager(exr_error *error);
  exr_status render(size_t page, Frame &frame, exr_error *error);
  exr_status pageForOffset(size_t offset, size_t *page, exr_error *error);
  void present(EventKind kind, uint64_t ticket, size_t page);
  void saveProgress();

  HWND window_ = nullptr;
  std::wstring dataDir_;
  std::thread thread_;
  std::mutex mutex_;
  std::condition_variable wake_;
  std::deque<std::function<void()>> queue_;
  bool quit_ = false;

  // Worker-owned state.
  exr_library *library_ = nullptr;
  exr_font *font_ = nullptr;
  std::set<int64_t> coverTried_;
  std::unique_ptr<Session> session_;
};

std::wstring FormatName(exr_format format);
bool FormatForPath(const std::wstring &path, exr_format *format);
inline bool IsFixedFormat(exr_format format) { return format == EXR_PDF || format == EXR_CBZ; }
