/* SPDX-License-Identifier: MIT */
#include "reader_ocr_overlay.h"
#include <exr_ocr.h>
#include <tesseract/baseapi.h>
#include <algorithm>
#include <cctype>
#include <chrono>
#include <cmath>
#include <cstdio>
#include <cstring>
#include <filesystem>
#include <memory>
#include <new>
#include <string>
#include <system_error>
#include <thread>
#include <vector>

namespace {
using Clock = std::chrono::steady_clock;
using Status = reader_ocr_overlay_status;
constexpr size_t kMaxPixels = 64000000, kMaxItems = 20000, kMaxSnapshot = 4u << 20;
constexpr unsigned kMaxTimeout = 300000;

Status fail(reader_ocr_overlay_error *e, Status code, int sdk, const char *message) {
  if(e) {
    e->code = code;
    e->sdk_code = sdk;
    /* Bounded copy: an SDK/backend message may be longer than this error field. */
    size_t length = message ? std::strlen(message) : 0;
    if(length > sizeof(e->message) - 1) length = sizeof(e->message) - 1;
    if(length) std::memcpy(e->message, message, length);
    e->message[length] = '\0';
  }
  return code;
}
Status ok(reader_ocr_overlay_error *e) { return fail(e, READER_OCR_OVERLAY_OK, 0, ""); }
}  // namespace

struct reader_ocr_engine {
  exr_ocr *ocr = nullptr;
  const std::thread::id owner = std::this_thread::get_id(); /* immutable after publication */
  bool busy = false;                                       /* only read on the owner thread */
  std::string languages, backend;
};

struct reader_ocr_overlay {
  reader_ocr_overlay_info info{};
  std::string page_id, backend, languages, text;
  std::vector<reader_ocr_overlay_item> items;
};

namespace {
struct Busy {
  reader_ocr_engine *engine;
  explicit Busy(reader_ocr_engine *e) : engine(e) { engine->busy = true; }
  ~Busy() { engine->busy = false; }
};
/* Thread then reentry gate shared by every engine call. The owner id never
   changes after publication, so a foreign thread reads only immutable state. */
Status enter(reader_ocr_engine *engine, reader_ocr_overlay_error *e) {
  if(!engine) return fail(e, READER_OCR_OVERLAY_ARGUMENT, 0, "NULL OCR engine");
  if(engine->owner != std::this_thread::get_id()) return fail(e, READER_OCR_OVERLAY_THREAD, 0, "OCR engine used from a non-owner thread");
  if(engine->busy) return fail(e, READER_OCR_OVERLAY_BUSY, 0, "Reentrant OCR engine use");
  return READER_OCR_OVERLAY_OK;
}

/* Wraps the host control so one deadline spans render and recognition. */
struct Guard {
  exr_control host{};
  Clock::time_point end{};
  bool timed_out = false, cancelled = false;
  static int stop(void *context) {
    Guard *g = static_cast<Guard *>(context);
    if(g->host.cancelled && g->host.cancelled(g->host.context)) { g->cancelled = true; return 1; }
    if(Clock::now() >= g->end) { g->timed_out = true; return 1; }
    return 0;
  }
  static void progress(void *context, exr_stage stage, uint64_t done, uint64_t total) {
    Guard *g = static_cast<Guard *>(context);
    if(g->host.progress) g->host.progress(g->host.context, stage, done, total);
  }
  exr_control control() { exr_control c{}; c.cancelled = stop; c.progress = progress; c.context = this; return c; }
  Status stopped(reader_ocr_overlay_error *e) const {
    return timed_out && !cancelled ? fail(e, READER_OCR_OVERLAY_TIMEOUT, 0, "OCR deadline exceeded")
                                   : fail(e, READER_OCR_OVERLAY_CANCELLED, 0, "OCR cancelled");
  }
};

bool valid_options(const reader_ocr_overlay_options *o) {
  return o && o->struct_size == sizeof(*o) && std::isfinite(o->scale) && o->scale > 0 && o->scale <= 16 &&
    o->base_dpi && o->content_rotation <= 270 && o->content_rotation % 90 == 0 &&
    o->timeout_ms && o->timeout_ms <= kMaxTimeout && o->max_pixels && o->max_pixels <= kMaxPixels &&
    o->max_items && o->max_items <= kMaxItems && o->max_snapshot_bytes && o->max_snapshot_bytes <= kMaxSnapshot &&
    std::isfinite(o->min_confidence) && o->min_confidence >= 0 && o->min_confidence <= 100;
}
uint64_t fnv1a(const exr_bitmap &b) {
  uint64_t h = 1469598103934665603ull;
  size_t row = static_cast<size_t>(b.width) * (b.channels ? b.channels : 1);
  for(uint32_t y = 0; y < b.height; y++) {
    const unsigned char *p = b.pixels + static_cast<size_t>(y) * b.stride;
    for(size_t i = 0; i < row; i++) { h ^= p[i]; h *= 1099511628211ull; }
  }
  return h;
}
bool same_geometry(const exr_page_geometry &a, const exr_page_geometry &b) {
  return std::equal(a.bounds, a.bounds + 4, b.bounds) && a.unit_scale == b.unit_scale && a.rotation == b.rotation && a.y_down == b.y_down;
}

Status recognize(reader_ocr_engine *engine, const char *page_id, const exr_page_geometry &geometry, const exr_bitmap &bitmap,
                 const reader_ocr_overlay_options &o, Guard &guard, reader_ocr_overlay **out, reader_ocr_overlay_error *e) {
  if(!page_id || !*page_id) return fail(e, READER_OCR_OVERLAY_ARGUMENT, 0, "Missing OCR page identity");
  exr_error sdk{}; exr_viewport view{};
  exr_status viewport = exr_viewport_create(&geometry, o.scale, &view, &sdk);
  if(viewport != EXR_OK)
    return fail(e, viewport == EXR_LIMIT ? READER_OCR_OVERLAY_LIMIT : READER_OCR_OVERLAY_ARGUMENT, sdk.code, "Invalid page geometry or scale");
  uint32_t cols = static_cast<uint32_t>(std::ceil(view.width)), rows = static_cast<uint32_t>(std::ceil(view.height));
  if(!bitmap.pixels || (bitmap.channels != 1 && bitmap.channels != 4) || bitmap.width != cols || bitmap.height != rows)
    return fail(e, READER_OCR_OVERLAY_ARGUMENT, 0, "Bitmap does not match the page viewport");
  double dpi = std::llround(static_cast<double>(o.base_dpi) * o.scale);
  if(dpi < 70 || dpi > 2400) return fail(e, READER_OCR_OVERLAY_ARGUMENT, 0, "Effective dpi outside 70..2400");
  if(guard.stop(&guard)) return guard.stopped(e);
  unsigned clockwise = (720u - geometry.rotation - o.content_rotation) % 360u;

  exr_ocr_options ocr{}; exr_ocr_options_default(&ocr);
  ocr.max_pixels = o.max_pixels;
  ocr.max_output_bytes = std::min<size_t>(o.max_snapshot_bytes * 4, 16u << 20);
  ocr.max_items = std::min<size_t>(o.max_items * 32, 500000);
  ocr.dpi = static_cast<unsigned>(dpi); ocr.clockwise = clockwise;
  auto remaining = std::chrono::duration_cast<std::chrono::milliseconds>(guard.end - Clock::now()).count();
  if(remaining < 1) { guard.timed_out = true; return guard.stopped(e); }
  ocr.timeout_ms = static_cast<unsigned>(std::min<long long>(remaining, static_cast<long long>(kMaxTimeout)));
  std::memcpy(ocr.pixel_to_page, view.inverse, sizeof(view.inverse));
  ocr.control = guard.control();
  exr_ocr_result raw{};
  exr_status status = exr_ocr_recognize(engine->ocr, &bitmap, &ocr, &raw, &sdk);
  if(status != EXR_OK) {
    exr_ocr_result_free(&raw);
    if(status == EXR_CANCELLED) return guard.stopped(e);
    if(status == EXR_LIMIT && std::strstr(sdk.message, "deadline")) { guard.timed_out = true; return guard.stopped(e); }
    if(status == EXR_LIMIT) return fail(e, READER_OCR_OVERLAY_LIMIT, status, sdk.message);
    if(status == EXR_ARGUMENT) return fail(e, READER_OCR_OVERLAY_ARGUMENT, status, sdk.message);
    if(status == EXR_MEMORY) return fail(e, READER_OCR_OVERLAY_MEMORY, status, sdk.message);
    return fail(e, READER_OCR_OVERLAY_BACKEND, status, sdk.message);
  }
  std::unique_ptr<reader_ocr_overlay> snapshot;
  try {
    snapshot.reset(new reader_ocr_overlay);
    for(size_t i = 0; i < raw.count; i++) {
      const exr_ocr_item &r = raw.items[i];
      if((r.level != READER_OCR_LINE && r.level != READER_OCR_WORD) || r.confidence < o.min_confidence) continue;
      reader_ocr_overlay_item item{};
      item.level = r.level; item.confidence = r.confidence;
      item.text_offset = snapshot->text.size(); item.text_bytes = r.text_bytes;
      std::copy(r.pixel_quad, r.pixel_quad + 8, item.pixel_quad); std::copy(r.page_quad, r.page_quad + 8, item.page_quad);
      if(snapshot->items.size() >= o.max_items ||
         (snapshot->items.size() + 1) * sizeof(item) + snapshot->text.size() + item.text_bytes + 1 > o.max_snapshot_bytes) {
        exr_ocr_result_free(&raw);
        return fail(e, READER_OCR_OVERLAY_LIMIT, 0, "OCR snapshot budget exceeded");
      }
      snapshot->text.append(raw.text + r.text_offset, r.text_bytes);
      snapshot->items.push_back(item);
    }
    exr_ocr_result_free(&raw);
    snapshot->page_id = page_id; snapshot->backend = engine->backend; snapshot->languages = engine->languages;
  } catch(...) { exr_ocr_result_free(&raw); return fail(e, READER_OCR_OVERLAY_MEMORY, 0, "OCR snapshot allocation failed"); }
  /* Commit boundary: last cancellation poll, then the host's currency check. */
  if(guard.stop(&guard)) return guard.stopped(e);
  if(o.still_current && !o.still_current(o.current_context)) return fail(e, READER_OCR_OVERLAY_STALE, 0, "Page changed before the OCR snapshot was committed");
  reader_ocr_overlay_info &i = snapshot->info;
  i.source = "tesseract-ocr"; i.backend = snapshot->backend.c_str(); i.languages = snapshot->languages.c_str(); i.page_id = snapshot->page_id.c_str();
  i.geometry = geometry; i.scale = o.scale; i.bitmap_width = bitmap.width; i.bitmap_height = bitmap.height;
  i.dpi = ocr.dpi; i.clockwise = clockwise; i.pixel_fnv1a = fnv1a(bitmap);
  i.count = snapshot->items.size(); i.text_bytes = snapshot->text.size();
  i.memory_bytes = sizeof(*snapshot) + snapshot->items.capacity() * sizeof(reader_ocr_overlay_item) + snapshot->text.capacity() +
    snapshot->page_id.capacity() + snapshot->backend.capacity() + snapshot->languages.capacity();
  *out = snapshot.release();
  return ok(e);
}
}  // namespace

extern "C" {
const char *reader_ocr_overlay_version(void) { return READER_OCR_OVERLAY_VERSION; }

void reader_ocr_overlay_options_default(reader_ocr_overlay_options *o) {
  if(!o) return;
  *o = {};
  o->struct_size = sizeof(*o); o->scale = 1; o->base_dpi = 300; o->timeout_ms = 30000;
  o->max_pixels = 16000000; o->max_items = 5000; o->max_snapshot_bytes = 1u << 20;
}

Status reader_ocr_engine_open(const char *dir, const char *languages, reader_ocr_engine **out, reader_ocr_overlay_error *e) {
  if(out) *out = nullptr;
  if(!out || !dir || !*dir || !languages || !*languages || std::strlen(languages) > 64)
    return fail(e, READER_OCR_OVERLAY_ARGUMENT, 0, "Missing OCR model directory or language");
  std::vector<std::string> names; std::string current;
  for(const char *p = languages;; p++) {
    if(*p == '+' || !*p) {
      if(current.empty()) return fail(e, READER_OCR_OVERLAY_ARGUMENT, 0, "Empty OCR language name");
      names.push_back(current); current.clear();
      if(!*p) break;
    } else if(std::isalnum(static_cast<unsigned char>(*p)) || *p == '_') current += *p;
    else return fail(e, READER_OCR_OVERLAY_ARGUMENT, 0, "Invalid OCR language name");
  }
  if(names.size() > 8) return fail(e, READER_OCR_OVERLAY_ARGUMENT, 0, "Too many OCR languages");
  for(const std::string &name : names) {
    std::error_code ec;
    std::filesystem::path model = std::filesystem::path(dir) / (name + ".traineddata");
    bool regular = std::filesystem::is_regular_file(model, ec) && !ec;
    uintmax_t bytes = regular ? std::filesystem::file_size(model, ec) : 0;
    if(!regular || ec || bytes == 0) {
      const std::string notice = "OCR model missing or empty: " + name;
      return fail(e, READER_OCR_OVERLAY_MODEL_MISSING, 0, notice.c_str());
    }
  }
  std::unique_ptr<reader_ocr_engine> engine;
  try { engine.reset(new reader_ocr_engine); } catch(...) { return fail(e, READER_OCR_OVERLAY_MEMORY, 0, "OCR engine allocation failed"); }
  exr_error sdk{};
  exr_status status = exr_ocr_open(dir, languages, &engine->ocr, &sdk);
  if(status != EXR_OK) return fail(e, status == EXR_MEMORY ? READER_OCR_OVERLAY_MEMORY : READER_OCR_OVERLAY_BACKEND, status, sdk.message);
  try {
    engine->languages = languages;
    engine->backend = tesseract::TessBaseAPI::Version();
  } catch(...) { exr_ocr_close(engine->ocr); return fail(e, READER_OCR_OVERLAY_MEMORY, 0, "OCR engine allocation failed"); }
  *out = engine.release();
  return ok(e);
}

Status reader_ocr_engine_close(reader_ocr_engine *engine, reader_ocr_overlay_error *e) {
  if(!engine) return ok(e);
  Status gate = enter(engine, e);
  if(gate != READER_OCR_OVERLAY_OK) return gate;
  exr_ocr_close(engine->ocr); delete engine;
  return ok(e);
}

Status reader_ocr_overlay_recognize_bitmap(reader_ocr_engine *engine, const char *page_id, const exr_page_geometry *geometry,
    const exr_bitmap *bitmap, const reader_ocr_overlay_options *options, reader_ocr_overlay **out, reader_ocr_overlay_error *e) {
  if(out) *out = nullptr;
  Status gate = enter(engine, e);
  if(gate != READER_OCR_OVERLAY_OK) return gate;
  if(!out || !page_id || !*page_id || !geometry || !bitmap || !valid_options(options))
    return fail(e, READER_OCR_OVERLAY_ARGUMENT, 0, "Invalid OCR overlay arguments");
  Busy busy(engine);
  Guard guard; guard.host = options->control; guard.end = Clock::now() + std::chrono::milliseconds(options->timeout_ms);
  return recognize(engine, page_id, *geometry, *bitmap, *options, guard, out, e);
}

Status reader_ocr_overlay_recognize_page(reader_ocr_engine *engine, exr_fixed_document *document, size_t page,
    const reader_ocr_overlay_options *options, reader_ocr_overlay **out, reader_ocr_overlay_error *e) {
  if(out) *out = nullptr;
  Status gate = enter(engine, e);
  if(gate != READER_OCR_OVERLAY_OK) return gate;
  size_t count = 0;
  const exr_fixed_page *pages = document ? exr_fixed_pages(document, &count) : nullptr;
  if(!out || !pages || page >= count || !pages[page].id || !valid_options(options))
    return fail(e, READER_OCR_OVERLAY_ARGUMENT, 0, "Invalid OCR overlay arguments");
  Busy busy(engine);
  Guard guard; guard.host = options->control; guard.end = Clock::now() + std::chrono::milliseconds(options->timeout_ms);
  /* Dimensions come from the same viewport the SDK renders, so the budget holds before any drawing. */
  exr_error sdk{}; exr_viewport view{};
  exr_status created = exr_viewport_create(&pages[page].geometry, options->scale, &view, &sdk);
  if(created != EXR_OK)
    return fail(e, created == EXR_LIMIT ? READER_OCR_OVERLAY_LIMIT : READER_OCR_OVERLAY_ARGUMENT, sdk.code, "Invalid page geometry or scale");
  double cols = std::ceil(view.width), rows = std::ceil(view.height);
  if(cols < 1 || rows < 1 || cols > 16384 || rows > 16384 || cols * rows > static_cast<double>(options->max_pixels))
    return fail(e, READER_OCR_OVERLAY_LIMIT, 0, "OCR pixel budget exceeded before render");
  exr_fixed_render_options render{}; render.control = guard.control();
  render.channels = 0; render.background = 0xffffffffu; /* opaque white page, as a printed scan */
  exr_bitmap bitmap{};
  exr_status status = exr_fixed_render(document, page, options->scale, &render, &bitmap, &sdk);
  if(status != EXR_OK) {
    exr_bitmap_free(&bitmap);
    if(status == EXR_CANCELLED) return guard.stopped(e);
    if(status == EXR_LIMIT) return fail(e, READER_OCR_OVERLAY_LIMIT, status, sdk.message);
    return fail(e, READER_OCR_OVERLAY_RENDER, status, sdk.message);
  }
  Status result = recognize(engine, pages[page].id, pages[page].geometry, bitmap, *options, guard, out, e);
  exr_bitmap_free(&bitmap);
  return result;
}

void reader_ocr_overlay_free(reader_ocr_overlay *overlay) { delete overlay; }
const reader_ocr_overlay_info *reader_ocr_overlay_get_info(const reader_ocr_overlay *o) { return o ? &o->info : nullptr; }
const reader_ocr_overlay_item *reader_ocr_overlay_items(const reader_ocr_overlay *o, size_t *count) {
  if(count) *count = o ? o->items.size() : 0;
  return o && !o->items.empty() ? o->items.data() : nullptr;
}
const char *reader_ocr_overlay_text(const reader_ocr_overlay *o, size_t *bytes) {
  if(bytes) *bytes = o ? o->text.size() : 0;
  return o ? o->text.c_str() : "";
}

Status reader_ocr_overlay_check_current(const reader_ocr_overlay *o, const char *page_id, const exr_page_geometry *geometry,
    double scale, const exr_bitmap *bitmap, reader_ocr_overlay_error *e) {
  if(!o || !page_id || !geometry || !std::isfinite(scale)) return fail(e, READER_OCR_OVERLAY_ARGUMENT, 0, "Invalid currency check arguments");
  if(o->page_id != page_id) return fail(e, READER_OCR_OVERLAY_STALE, 0, "Page identity changed");
  if(!same_geometry(o->info.geometry, *geometry)) return fail(e, READER_OCR_OVERLAY_STALE, 0, "Page geometry changed");
  if(o->info.scale != scale) return fail(e, READER_OCR_OVERLAY_STALE, 0, "Render scale changed");
  if(bitmap) {
    /* The hash walks height rows of stride bytes: refuse a stride that would read past a row. */
    if(!bitmap->pixels || (bitmap->channels != 1 && bitmap->channels != 4) ||
       bitmap->stride < static_cast<size_t>(bitmap->width) * bitmap->channels)
      return fail(e, READER_OCR_OVERLAY_ARGUMENT, 0, "Invalid currency bitmap");
    if(bitmap->width != o->info.bitmap_width || bitmap->height != o->info.bitmap_height || fnv1a(*bitmap) != o->info.pixel_fnv1a)
      return fail(e, READER_OCR_OVERLAY_STALE, 0, "Page pixels changed");
  }
  return ok(e);
}

Status reader_ocr_overlay_to_fixed_text(const reader_ocr_overlay *o, unsigned level, const exr_control *control,
    exr_fixed_text **out, reader_ocr_overlay_error *e) {
  if(out) *out = nullptr;
  if(!o || !out || (level != READER_OCR_LINE && level != READER_OCR_WORD)) return fail(e, READER_OCR_OVERLAY_ARGUMENT, 0, "Invalid OCR text level");
  std::string text; std::vector<exr_text_region> regions;
  try {
    for(const reader_ocr_overlay_item &item : o->items) {
      if(item.level != level) continue;
      if(!regions.empty()) text += '\n';
      exr_text_region r{}; r.start = text.size(); text.append(o->text, item.text_offset, item.text_bytes); r.end = text.size();
      std::copy(item.page_quad, item.page_quad + 8, r.quad); regions.push_back(r);
    }
  } catch(...) { return fail(e, READER_OCR_OVERLAY_MEMORY, 0, "OCR text allocation failed"); }
  exr_error sdk{};
  exr_status status = exr_fixed_text_create(text.data(), text.size(), regions.empty() ? nullptr : regions.data(), regions.size(), control, out, &sdk);
  if(status == EXR_CANCELLED) return fail(e, READER_OCR_OVERLAY_CANCELLED, status, sdk.message);
  if(status == EXR_MEMORY) return fail(e, READER_OCR_OVERLAY_MEMORY, status, sdk.message);
  if(status == EXR_LIMIT) return fail(e, READER_OCR_OVERLAY_LIMIT, status, sdk.message);
  if(status != EXR_OK) return fail(e, READER_OCR_OVERLAY_ARGUMENT, status, sdk.message);
  return ok(e);
}
}  // extern "C"
