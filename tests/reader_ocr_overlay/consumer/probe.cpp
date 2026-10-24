/* SPDX-License-Identifier: MIT */
/* Independent installed consumer and evidence probe for reader_ocr_overlay.

   Linked only against the installed EXReaderOCROverlay package (which brings the
   frozen SDK core and the separate OCR adapter). Every case is named; the probe
   prints one RESULT line per case and writes the same rows as TSV. A case that
   is never reached is emitted as PENDING by finalize(), so an early abort cannot
   hide behind a missing row. */
#include <reader_ocr_overlay.h>
#include <algorithm>
#include <cctype>
#include <cmath>
#include <cstdio>
#include <cstring>
#include <fstream>
#include <iterator>
#include <string>
#include <thread>
#include <vector>

namespace {

using Status = reader_ocr_overlay_status;

const char *status_name(Status s) {
  switch(s) {
    case READER_OCR_OVERLAY_OK: return "OK";
    case READER_OCR_OVERLAY_ARGUMENT: return "ARGUMENT";
    case READER_OCR_OVERLAY_MEMORY: return "MEMORY";
    case READER_OCR_OVERLAY_LIMIT: return "LIMIT";
    case READER_OCR_OVERLAY_CANCELLED: return "CANCELLED";
    case READER_OCR_OVERLAY_TIMEOUT: return "TIMEOUT";
    case READER_OCR_OVERLAY_MODEL_MISSING: return "MODEL_MISSING";
    case READER_OCR_OVERLAY_BACKEND: return "BACKEND";
    case READER_OCR_OVERLAY_RENDER: return "RENDER";
    case READER_OCR_OVERLAY_STALE: return "STALE";
    case READER_OCR_OVERLAY_BUSY: return "BUSY";
    case READER_OCR_OVERLAY_THREAD: return "THREAD";
  }
  return "UNKNOWN";
}

const char *const kChecks[] = {
  "fixture_document_created",
  "engine_open_eng",
  "recognize_page_ok",
  "recognize_page_source_labels",
  "recognize_page_items_wellformed",
  "recognize_page_locate_rows",
  "recognize_page_pixel_quad_consistent",
  "recognize_page_confidence_filter",
  "recognize_page_line_and_word_mix",
  "render_fixture_page",
  "recognize_bitmap_ok",
  "recognize_bitmap_matches_page",
  "snapshot_outlives_bitmap",
  "snapshot_outlives_document",
  "rotation_90_page",
  "rotation_180_page",
  "rotation_270_page",
  "rotation_quads_invariant",
  "content_rotation_90_upright",
  "scale_1_5_page",
  "scale_1_5_quads_agree",
  "blank_page_empty",
  "bars_page_no_letters",
  "cancel_before_render",
  "cancel_during_recognition",
  "timeout_deadline",
  "stale_still_current",
  "still_current_commits",
  "missing_model_directory",
  "missing_model_file",
  "empty_model_file",
  "argument_null_engine",
  "argument_options",
  "argument_scale_rotation_confidence",
  "argument_hard_caps",
  "argument_bitmap_mismatch",
  "argument_page_range",
  "argument_language",
  "limit_pixels_before_render",
  "limit_snapshot_budget",
  "render_failure_propagates",
  "busy_reentrant",
  "to_fixed_text_lines",
  "to_fixed_text_words",
  "to_fixed_text_rejects_level",
  "to_fixed_text_cancelled",
  "to_fixed_text_independent",
  "thread_foreign_call_rejected",
  "thread_foreign_close_rejected",
  "document_untouched",
  "engine_close_null",
  "windows_host_scope",
  "mobile_host_scope",
  "model_chi_sim",
  "engine_close_owner",
};

struct Result { std::string name, status, detail; };
std::vector<Result> g_results;

void report(const char *name, const char *status, const std::string &detail) {
  for(const Result &r : g_results) if(r.name == name) return; /* first verdict wins */
  g_results.push_back(Result{name, status, detail});
  std::printf("RESULT %s %s %s\n", name, status, detail.c_str());
  std::fflush(stdout);
}
void check(const char *name, bool ok, const std::string &detail) { report(name, ok ? "PASS" : "FAIL", detail); }
void skip(const char *name, const std::string &detail) { report(name, "SKIP", detail); }

std::string clean(const std::string &text) {
  std::string out;
  for(char c : text) out += (c == '\t' || c == '\n' || c == '\r') ? ' ' : c;
  return out;
}
std::string error_text(Status code, const reader_ocr_overlay_error &e) {
  return std::string("code=") + status_name(code) + " sdk=" + std::to_string(e.sdk_code) + " msg=" + clean(e.message);
}
std::string upper(std::string text) {
  for(char &c : text) c = static_cast<char>(std::toupper(static_cast<unsigned char>(c)));
  return text;
}

/* Fills unreached cases as PENDING and writes the verdict table. */
int write_results(const std::string &path) {
  for(const char *name : kChecks) report(name, "PENDING", "case not reached");
  std::ofstream out(path);
  if(!out) return 8;
  int failures = 0;
  for(const Result &r : g_results) {
    out << r.name << '\t' << r.status << '\t' << clean(r.detail) << '\n';
    if(r.status == "FAIL") failures++;
  }
  std::printf("PROBE checks=%zu failures=%d\n", g_results.size(), failures);
  return failures == 0 ? 0 : 1;
}

struct Box { double x0 = 0, y0 = 0, x1 = 0, y1 = 0; };
struct Line { std::string text, token; Box box, token_box; };
struct Located { bool found = false; double cx = 0, cy = 0; std::string text; };

enum { DRAW_NONE = 0, DRAW_IMAGE = 1, DRAW_IMAGE_ROT90 = 2, DRAW_FAIL = 3 };
struct Op { int kind = DRAW_NONE; const exr_bitmap *image = nullptr; };
std::vector<Op> g_ops;
long g_provider_calls = 0;

exr_status set_error(exr_error *e, exr_status code, const char *message) {
  if(e) { e->code = code; std::snprintf(e->message, sizeof(e->message), "%s", message); }
  return code;
}
/* out = a after b, for x' = a0*x + a2*y + a4, y' = a1*x + a3*y + a5. */
void compose(const double a[6], const double b[6], double out[6]) {
  out[0] = a[0]*b[0] + a[2]*b[1];
  out[1] = a[1]*b[0] + a[3]*b[1];
  out[2] = a[0]*b[2] + a[2]*b[3];
  out[3] = a[1]*b[2] + a[3]*b[3];
  out[4] = a[0]*b[4] + a[2]*b[5] + a[4];
  out[5] = a[1]*b[4] + a[3]*b[5] + a[5];
}

exr_status provider_draw(void *context, size_t page, const double matrix[6], const exr_draw_sink *sink,
                         const exr_control *control, exr_error *error) {
  (void)context; (void)control;
  g_provider_calls++;
  if(!sink || !sink->image) return set_error(error, EXR_ARGUMENT, "probe sink has no image callback");
  if(page >= g_ops.size()) return set_error(error, EXR_ARGUMENT, "probe page out of range");
  const Op &op = g_ops[page];
  if(op.kind == DRAW_FAIL) return set_error(error, EXR_IO, "probe page provider failure");
  if(op.kind == DRAW_NONE || !op.image) return EXR_OK;
  double page_matrix[6] = {1, 0, 0, 1, 0, 0};
  if(op.kind == DRAW_IMAGE_ROT90) {
    /* Clockwise quarter turn inside the page: (x,y) -> (height - y, x). */
    const double height = static_cast<double>(op.image->height);
    page_matrix[0] = 0; page_matrix[1] = 1; page_matrix[2] = -1; page_matrix[3] = 0;
    page_matrix[4] = height; page_matrix[5] = 0;
  }
  double image_matrix[6];
  compose(matrix, page_matrix, image_matrix);
  exr_image_layer layer{};
  layer.bitmap = *op.image;
  layer.interpolate = 1;
  return sink->image(sink->context, &layer, image_matrix, 1.0, error);
}

bool read_bytes(const std::string &path, std::vector<unsigned char> &bytes) {
  std::ifstream file(path, std::ios::binary);
  if(!file) return false;
  bytes.assign(std::istreambuf_iterator<char>(file), std::istreambuf_iterator<char>());
  return true;
}
bool parse_box(const std::string &text, Box &box) {
  double values[4] = {0, 0, 0, 0};
  if(std::sscanf(text.c_str(), "%lf %lf %lf %lf", &values[0], &values[1], &values[2], &values[3]) != 4) return false;
  box = Box{values[0], values[1], values[2], values[3]};
  return true;
}
std::vector<std::string> split_tab(const std::string &row) {
  std::vector<std::string> columns;
  size_t start = 0;
  for(;;) {
    const size_t tab = row.find('\t', start);
    columns.push_back(row.substr(start, tab == std::string::npos ? std::string::npos : tab - start));
    if(tab == std::string::npos) break;
    start = tab + 1;
  }
  return columns;
}

bool item_text(const char *text, size_t bytes, const reader_ocr_overlay_item &item, std::string &out) {
  if(item.text_offset > bytes || item.text_bytes > bytes - item.text_offset) return false;
  out.assign(text + item.text_offset, item.text_bytes);
  return true;
}
void quad_center(const double quad[8], double &x, double &y) {
  x = (quad[0] + quad[2] + quad[4] + quad[6]) / 4.0;
  y = (quad[1] + quad[3] + quad[5] + quad[7]) / 4.0;
}
bool inside(const Box &box, double x, double y, double grow) {
  return x >= box.x0 - grow && x <= box.x1 + grow && y >= box.y0 - grow && y <= box.y1 + grow;
}
/* Locates each expected line by a word record carrying the line's token. */
std::vector<Located> locate_rows(const reader_ocr_overlay *overlay, const std::vector<Line> &lines, double grow) {
  std::vector<Located> found(lines.size());
  size_t count = 0;
  const reader_ocr_overlay_item *items = reader_ocr_overlay_items(overlay, &count);
  size_t bytes = 0;
  const char *text = reader_ocr_overlay_text(overlay, &bytes);
  if(!items || !text) return found;
  for(size_t index = 0; index < lines.size(); index++) {
    const std::string token = upper(lines[index].token);
    for(size_t i = 0; i < count && !found[index].found; i++) {
      if(items[i].level != READER_OCR_WORD) continue;
      std::string value;
      if(!item_text(text, bytes, items[i], value)) continue;
      if(upper(value).find(token) == std::string::npos) continue;
      double x = 0, y = 0;
      quad_center(items[i].page_quad, x, y);
      if(!inside(lines[index].token_box, x, y, grow)) continue;
      found[index] = Located{true, x, y, value};
    }
  }
  return found;
}
int located_count(const std::vector<Located> &rows) {
  int count = 0;
  for(const Located &row : rows) if(row.found) count++;
  return count;
}

int g_cancel_polls = 0;
int g_cancel_after = 0;
int cancel_after_polls(void *) { g_cancel_polls++; return g_cancel_after > 0 && g_cancel_polls >= g_cancel_after; }
int cancel_always(void *) { return 1; }
int current_never(void *) { return 0; }
int current_always(void *) { return 1; }

struct Nested {
  reader_ocr_engine *engine = nullptr;
  const exr_page_geometry *geometry = nullptr;
  const exr_bitmap *bitmap = nullptr;
  const reader_ocr_overlay_options *options = nullptr;
  Status status = READER_OCR_OVERLAY_OK;
  bool called = false;
  reader_ocr_overlay *out = nullptr;
  reader_ocr_overlay_error error{};
};
Nested *g_nested = nullptr;
void nested_progress(void *, exr_stage, uint64_t, uint64_t) {
  if(!g_nested || g_nested->called) return;
  g_nested->called = true;
  g_nested->status = reader_ocr_overlay_recognize_bitmap(g_nested->engine, "page-scan", g_nested->geometry,
    g_nested->bitmap, g_nested->options, &g_nested->out, &g_nested->error);
  if(g_nested->out) { reader_ocr_overlay_free(g_nested->out); g_nested->out = nullptr; }
}

struct Overlay {
  reader_ocr_overlay *value = nullptr;
  ~Overlay() { reader_ocr_overlay_free(value); }
};

exr_fixed_document *build_document(const exr_fixed_page *pages, size_t count, std::string &detail) {
  exr_fixed_input input{};
  input.struct_size = sizeof(input);
  input.title = "reader ocr overlay fixture";
  input.pages = pages;
  input.page_count = count;
  input.draw = provider_draw;
  input.context = nullptr;
  input.release = nullptr;
  exr_fixed_document *document = nullptr;
  exr_error sdk{};
  const exr_status status = exr_fixed_create(&input, &document, &sdk);
  if(status != EXR_OK) detail = std::string("exr_fixed_create failed: ") + sdk.message;
  return status == EXR_OK ? document : nullptr;
}

}  // namespace

int main(int argc, char **argv) {
  if(argc != 5) {
    std::fprintf(stderr, "usage: %s <fixtures> <models> <results.tsv> <work-dir>\n", argv[0]);
    return 2;
  }
  const std::string fixtures = argv[1], models = argv[2], results = argv[3];
  /* 1. Fixture inputs. */
  std::vector<Line> lines;
  {
    std::ifstream table(fixtures + "/lines.tsv");
    std::string row;
    while(std::getline(table, row)) {
      if(row.empty() || row[0] == '#') continue;
      const std::vector<std::string> columns = split_tab(row);
      Line line;
      if(columns.size() != 5 || !parse_box(columns[2], line.box) || !parse_box(columns[4], line.token_box)) {
        std::fprintf(stderr, "bad lines.tsv row\n");
        return 3;
      }
      line.text = columns[1];
      line.token = columns[3];
      lines.push_back(line);
    }
    if(lines.size() < 4) { std::fprintf(stderr, "lines.tsv is incomplete\n"); return 3; }
  }
  exr_bitmap scan{}, bars{};
  std::vector<unsigned char> bytes;
  exr_error sdk{};
  auto load = [&](const char *name, exr_bitmap &bitmap) {
    if(!read_bytes(fixtures + "/" + name, bytes)) return false;
    return exr_image_decode(bytes.data(), bytes.size(), &bitmap, &sdk) == EXR_OK;
  };
  if(!load("scan.png", scan) || !load("bars.png", bars)) {
    std::fprintf(stderr, "cannot decode the page fixtures\n");
    return 4;
  }

  /* 2. Fixed document: eight pages, one behaviour each. */
  const exr_page_geometry page_geometry{{0, 0, 900, 1200}, 1.0, 0, 1};
  exr_page_geometry rotated = page_geometry;
  exr_page_geometry content = page_geometry;
  content.bounds[2] = 1200;
  content.bounds[3] = 900;
  exr_fixed_page pages[8] = {};
  g_ops.assign(8, Op{});
  const char *ids[8] = {"page-scan", "page-scan-rot90", "page-scan-rot180", "page-scan-rot270",
                        "page-scan-content90", "page-blank", "page-bars", "page-fail"};
  for(int i = 0; i < 8; i++) pages[i].id = ids[i];
  pages[0].geometry = page_geometry;
  rotated.rotation = 90;   pages[1].geometry = rotated;
  rotated.rotation = 180;  pages[2].geometry = rotated;
  rotated.rotation = 270;  pages[3].geometry = rotated;
  pages[4].geometry = content;
  pages[5].geometry = page_geometry;
  pages[6].geometry = page_geometry;
  pages[7].geometry = page_geometry;
  g_ops[0] = Op{DRAW_IMAGE, &scan};
  g_ops[1] = Op{DRAW_IMAGE, &scan};
  g_ops[2] = Op{DRAW_IMAGE, &scan};
  g_ops[3] = Op{DRAW_IMAGE, &scan};
  g_ops[4] = Op{DRAW_IMAGE_ROT90, &scan};
  g_ops[5] = Op{DRAW_NONE, nullptr};
  g_ops[6] = Op{DRAW_IMAGE, &bars};
  g_ops[7] = Op{DRAW_FAIL, nullptr};
  std::string detail;
  exr_fixed_document *document = build_document(pages, 8, detail);
  check("fixture_document_created", document != nullptr, detail.empty() ? "8 pages created" : detail);
  if(!document) return write_results(results);

  /* 3. Engine. */
  reader_ocr_engine *engine = nullptr;
  reader_ocr_overlay_error error{};
  Status status = reader_ocr_engine_open(models.c_str(), "eng", &engine, &error);
  check("engine_open_eng", status == READER_OCR_OVERLAY_OK && engine != nullptr, error_text(status, error));
  if(!engine) return write_results(results);
  const std::string version = reader_ocr_overlay_version();

  /* 4. Baseline recognition of the rendered page. */
  reader_ocr_overlay_options options;
  reader_ocr_overlay_options_default(&options);
  Overlay baseline;
  status = reader_ocr_overlay_recognize_page(engine, document, 0, &options, &baseline.value, &error);
  check("recognize_page_ok", status == READER_OCR_OVERLAY_OK && baseline.value != nullptr, error_text(status, error));
  if(!baseline.value) return write_results(results);
  const reader_ocr_overlay_info *info = reader_ocr_overlay_get_info(baseline.value);
  size_t baseline_items = 0, baseline_bytes = 0;
  const reader_ocr_overlay_item *baseline_records = reader_ocr_overlay_items(baseline.value, &baseline_items);
  const char *baseline_text = reader_ocr_overlay_text(baseline.value, &baseline_bytes);
  {
    const bool labels = info && info->source && std::strcmp(info->source, "tesseract-ocr") == 0 &&
      info->backend && info->backend[0] && info->languages && std::strcmp(info->languages, "eng") == 0 &&
      info->page_id && std::strcmp(info->page_id, "page-scan") == 0 && info->native_text == 0 &&
      info->permanent_anchor == 0 && info->dpi == 300 && info->clockwise == 0 && info->scale == 1.0 &&
      info->bitmap_width == 900 && info->bitmap_height == 1200 && info->count > 0 && info->text_bytes > 0 &&
      info->memory_bytes > 0 && info->pixel_fnv1a != 0 && info->geometry.rotation == 0;
    check("recognize_page_source_labels", labels,
      std::string("source=") + (info && info->source ? info->source : "(null)") + " backend=" + (info && info->backend ? info->backend : "?") +
      " dpi=" + std::to_string(info ? info->dpi : 0) + " clockwise=" + std::to_string(info ? info->clockwise : 0) +
      " count=" + std::to_string(info ? info->count : 0) + " version=" + version);
  }
  {
    bool ok = baseline_records && baseline_text && baseline_items > 0;
    int seen_words = 0;
    for(size_t i = 0; ok && i < baseline_items; i++) {
      const reader_ocr_overlay_item &item = baseline_records[i];
      std::string value;
      ok = (item.level == READER_OCR_LINE || item.level == READER_OCR_WORD) && item.confidence >= 0 && item.confidence <= 100 &&
        item_text(baseline_text, baseline_bytes, item, value) && !value.empty();
      for(int k = 0; ok && k < 8; k++)
        ok = std::isfinite(item.page_quad[k]) && std::isfinite(item.pixel_quad[k]);
      ok = ok && item.page_quad[0] >= -2 && item.page_quad[2] <= 902 && item.page_quad[1] >= -2 && item.page_quad[5] <= 1202 &&
        item.pixel_quad[0] >= -2 && item.pixel_quad[2] <= 902 && item.pixel_quad[1] >= -2 && item.pixel_quad[5] <= 1202;
      if(item.level == READER_OCR_WORD) seen_words++;
      if(item.level == READER_OCR_LINE) ok = ok && seen_words == 0;
    }
    check("recognize_page_items_wellformed", ok, "items=" + std::to_string(baseline_items));
  }
  const std::vector<Located> base_rows = locate_rows(baseline.value, lines, 12);
  check("recognize_page_locate_rows", located_count(base_rows) == static_cast<int>(lines.size()),
    "located " + std::to_string(located_count(base_rows)) + "/" + std::to_string(lines.size()));
  {
    bool ok = false;
    std::string note = "token row missing";
    exr_viewport view{};
    if(exr_viewport_create(&page_geometry, 1.0, &view, &sdk) == EXR_OK) {
      for(size_t i = 0; i < baseline_items; i++) {
        std::string value;
        if(baseline_records[i].level != READER_OCR_WORD || !item_text(baseline_text, baseline_bytes, baseline_records[i], value)) continue;
        if(upper(value).find("31415") == std::string::npos) continue;
        ok = true;
        double worst = 0;
        for(int k = 0; k < 4; k++) {
          const double px = view.matrix[0]*baseline_records[i].page_quad[2*k] + view.matrix[2]*baseline_records[i].page_quad[2*k+1] + view.matrix[4];
          const double py = view.matrix[1]*baseline_records[i].page_quad[2*k] + view.matrix[3]*baseline_records[i].page_quad[2*k+1] + view.matrix[5];
          worst = std::max(worst, std::max(std::fabs(px - baseline_records[i].pixel_quad[2*k]), std::fabs(py - baseline_records[i].pixel_quad[2*k+1])));
        }
        ok = worst <= 1.0;
        note = "max pixel/page mismatch " + std::to_string(worst);
        break;
      }
    }
    check("recognize_page_pixel_quad_consistent", ok, note);
  }
  {
    reader_ocr_overlay_options filtered = options;
    filtered.min_confidence = 90.0f;
    Overlay overlay;
    const Status result = reader_ocr_overlay_recognize_page(engine, document, 0, &filtered, &overlay.value, &error);
    bool ok = result == READER_OCR_OVERLAY_OK && overlay.value != nullptr;
    size_t count = 0;
    const reader_ocr_overlay_item *items = ok ? reader_ocr_overlay_items(overlay.value, &count) : nullptr;
    ok = ok && count <= baseline_items;
    for(size_t i = 0; ok && i < count; i++) ok = items[i].confidence >= 90.0f;
    check("recognize_page_confidence_filter", ok, "kept=" + std::to_string(count) + " of " + std::to_string(baseline_items));
  }
  {
    int line_count = 0, word_count = 0;
    for(size_t i = 0; i < baseline_items; i++) {
      if(baseline_records[i].level == READER_OCR_LINE) line_count++;
      else if(baseline_records[i].level == READER_OCR_WORD) word_count++;
    }
    check("recognize_page_line_and_word_mix", line_count >= 3 && word_count >= 6,
      "lines=" + std::to_string(line_count) + " words=" + std::to_string(word_count));
  }

  /* 5. Host-rendered bitmap path and snapshot lifetime. */
  exr_bitmap rendered{};
  {
    exr_fixed_render_options render{};
    render.channels = 0;
    render.background = 0xffffffffu;
    const exr_status status_render = exr_fixed_render(document, 0, 1.0, &render, &rendered, &sdk);
    check("render_fixture_page", status_render == EXR_OK && rendered.width == 900 && rendered.height == 1200 && rendered.channels == 4 && rendered.pixels,
      std::string("status=") + status_name(status_render == EXR_OK ? READER_OCR_OVERLAY_OK : READER_OCR_OVERLAY_RENDER) +
      " " + std::to_string(rendered.width) + "x" + std::to_string(rendered.height) + " ch=" + std::to_string(rendered.channels));
  }
  Overlay host;
  reader_ocr_overlay_options host_options = options;
  status = reader_ocr_overlay_recognize_bitmap(engine, "page-scan", &page_geometry, &rendered, &host_options, &host.value, &error);
  check("recognize_bitmap_ok", status == READER_OCR_OVERLAY_OK && host.value != nullptr, error_text(status, error));
  {
    size_t host_items = 0, host_bytes = 0;
    const reader_ocr_overlay_item *records = host.value ? reader_ocr_overlay_items(host.value, &host_items) : nullptr;
    const char *text = host.value ? reader_ocr_overlay_text(host.value, &host_bytes) : nullptr;
    const bool same = host.value && records && text && host_items == baseline_items && host_bytes == baseline_bytes &&
      std::string(text, host_bytes) == std::string(baseline_text, baseline_bytes);
    check("recognize_bitmap_matches_page", same,
      "host_items=" + std::to_string(host_items) + " page_items=" + std::to_string(baseline_items));
  }
  {
    const reader_ocr_overlay_info *host_info = host.value ? reader_ocr_overlay_get_info(host.value) : nullptr;
    exr_bitmap_free(&rendered);
    size_t host_bytes = 0;
    const char *text = host.value ? reader_ocr_overlay_text(host.value, &host_bytes) : nullptr;
    bool ok = host_info && text && host_bytes > 0 && std::string(text, host_bytes).find("31415") != std::string::npos &&
      std::strcmp(host_info->page_id, "page-scan") == 0 && host_info->count > 0;
    const Status current = host.value ? reader_ocr_overlay_check_current(host.value, "page-scan", &page_geometry, 1.0, nullptr, &error)
                                      : READER_OCR_OVERLAY_ARGUMENT;
    ok = ok && current == READER_OCR_OVERLAY_OK;
    check("snapshot_outlives_bitmap", ok, "check_current=" + std::string(status_name(current)) + " bytes=" + std::to_string(host_bytes));
  }
  {
    /* A second, short-lived document proves the snapshot keeps its own page id. */
    exr_fixed_page lifetime[1] = {};
    lifetime[0].id = "page-lifetime";
    lifetime[0].label = "lifetime";
    lifetime[0].geometry = page_geometry;
    std::string lifetime_detail;
    exr_fixed_document *temporary = build_document(lifetime, 1, lifetime_detail);
    Overlay overlay;
    Status result = temporary ? reader_ocr_overlay_recognize_page(engine, temporary, 0, &options, &overlay.value, &error)
                              : READER_OCR_OVERLAY_ARGUMENT;
    if(temporary) exr_fixed_free(temporary);
    size_t bytes_out = 0;
    const char *text = overlay.value ? reader_ocr_overlay_text(overlay.value, &bytes_out) : nullptr;
    const reader_ocr_overlay_info *snapshot = overlay.value ? reader_ocr_overlay_get_info(overlay.value) : nullptr;
    const bool ok = result == READER_OCR_OVERLAY_OK && text && bytes_out > 0 && snapshot &&
      std::strcmp(snapshot->page_id, "page-lifetime") == 0;
    check("snapshot_outlives_document", ok, error_text(result, error));
  }

  /* 6. Page rotation and content rotation. */
  std::vector<Located> rotation_rows[3];
  const unsigned rotation_degrees[3] = {90, 180, 270};
  const char *rotation_names[3] = {"rotation_90_page", "rotation_180_page", "rotation_270_page"};
  for(int i = 0; i < 3; i++) {
    Overlay overlay;
    reader_ocr_overlay_options rotated_options = options;
    const Status result = reader_ocr_overlay_recognize_page(engine, document, static_cast<size_t>(i + 1), &rotated_options, &overlay.value, &error);
    rotation_rows[i] = locate_rows(overlay.value, lines, 12);
    const reader_ocr_overlay_info *rotated_info = overlay.value ? reader_ocr_overlay_get_info(overlay.value) : nullptr;
    const bool ok = result == READER_OCR_OVERLAY_OK && rotated_info && rotated_info->clockwise == (720u - rotation_degrees[i]) % 360u &&
      located_count(rotation_rows[i]) == static_cast<int>(lines.size());
    check(rotation_names[i], ok, std::string("located=") + std::to_string(located_count(rotation_rows[i])) +
      " clockwise=" + std::to_string(rotated_info ? rotated_info->clockwise : 999u) + " " + error_text(result, error));
  }
  {
    double worst = 0;
    bool ok = true;
    for(int i = 0; i < 3; i++) {
      for(size_t row = 0; row < lines.size(); row++) {
        if(!base_rows[row].found || !rotation_rows[i][row].found) { ok = false; continue; }
        worst = std::max(worst, std::max(std::fabs(base_rows[row].cx - rotation_rows[i][row].cx),
                                         std::fabs(base_rows[row].cy - rotation_rows[i][row].cy)));
      }
    }
    check("rotation_quads_invariant", ok && worst <= 4.0, "worst page-unit deviation " + std::to_string(worst));
  }
  {
    Overlay overlay;
    reader_ocr_overlay_options content_options = options;
    content_options.content_rotation = 90;
    const Status result = reader_ocr_overlay_recognize_page(engine, document, 4, &content_options, &overlay.value, &error);
    const reader_ocr_overlay_info *content_info = overlay.value ? reader_ocr_overlay_get_info(overlay.value) : nullptr;
    /* Bitmap (x,y) -> page (1200 - y, x), so a box maps to a rotated box. */
    std::vector<Line> rotated_lines = lines;
    for(Line &line : rotated_lines) {
      const double height = 1200;
      Box box{height - line.token_box.y1, line.token_box.x0, height - line.token_box.y0, line.token_box.x1};
      line.token_box = box;
    }
    const std::vector<Located> rows = locate_rows(overlay.value, rotated_lines, 14);
    const bool ok = result == READER_OCR_OVERLAY_OK && content_info && content_info->clockwise == 270 &&
      located_count(rows) == static_cast<int>(lines.size());
    check("content_rotation_90_upright", ok, std::string("located=") + std::to_string(located_count(rows)) +
      " clockwise=" + std::to_string(content_info ? content_info->clockwise : 999u) + " " + error_text(result, error));
  }

  /* 7. Scale. */
  Overlay scaled;
  reader_ocr_overlay_options scaled_options = options;
  scaled_options.scale = 1.5;
  status = reader_ocr_overlay_recognize_page(engine, document, 0, &scaled_options, &scaled.value, &error);
  const std::vector<Located> scaled_rows = locate_rows(scaled.value, lines, 14);
  {
    const reader_ocr_overlay_info *scaled_info = scaled.value ? reader_ocr_overlay_get_info(scaled.value) : nullptr;
    const bool ok = status == READER_OCR_OVERLAY_OK && scaled_info && scaled_info->bitmap_width == 1350 &&
      scaled_info->bitmap_height == 1800 && scaled_info->dpi == 450 && located_count(scaled_rows) == static_cast<int>(lines.size());
    check("scale_1_5_page", ok, std::string("located=") + std::to_string(located_count(scaled_rows)) +
      " bitmap=" + std::to_string(scaled_info ? scaled_info->bitmap_width : 0) + "x" + std::to_string(scaled_info ? scaled_info->bitmap_height : 0) +
      " dpi=" + std::to_string(scaled_info ? scaled_info->dpi : 0) + " " + error_text(status, error));
  }
  {
    double worst = 0;
    bool ok = true;
    for(size_t row = 0; row < lines.size(); row++) {
      if(!base_rows[row].found || !scaled_rows[row].found) { ok = false; continue; }
      worst = std::max(worst, std::max(std::fabs(base_rows[row].cx - scaled_rows[row].cx),
                                       std::fabs(base_rows[row].cy - scaled_rows[row].cy)));
    }
    check("scale_1_5_quads_agree", ok && worst <= 8.0, "worst page-unit deviation " + std::to_string(worst));
  }

  /* 8. Blank page and image-only page. */
  {
    Overlay overlay;
    const Status result = reader_ocr_overlay_recognize_page(engine, document, 5, &options, &overlay.value, &error);
    size_t bytes_out = 1;
    const char *text = overlay.value ? reader_ocr_overlay_text(overlay.value, &bytes_out) : nullptr;
    const reader_ocr_overlay_info *blank_info = overlay.value ? reader_ocr_overlay_get_info(overlay.value) : nullptr;
    exr_fixed_text *fixed = nullptr;
    const Status text_status = overlay.value ? reader_ocr_overlay_to_fixed_text(overlay.value, READER_OCR_LINE, nullptr, &fixed, &error)
                                             : READER_OCR_OVERLAY_ARGUMENT;
    size_t fixed_size = 1, fixed_regions = 1;
    if(fixed) {
      exr_fixed_text_string(fixed, &fixed_size);
      exr_fixed_text_regions(fixed, &fixed_regions);
      exr_fixed_text_free(fixed);
    }
    const bool ok = result == READER_OCR_OVERLAY_OK && blank_info && blank_info->count == 0 && bytes_out == 0 &&
      text && text[0] == '\0' && std::strcmp(blank_info->page_id, "page-blank") == 0 &&
      text_status == READER_OCR_OVERLAY_OK && fixed_size == 0 && fixed_regions == 0;
    check("blank_page_empty", ok, "count=" + std::to_string(blank_info ? blank_info->count : 999u) +
      " text_bytes=" + std::to_string(bytes_out) + " fixed=" + std::to_string(fixed_size) + "/" + std::to_string(fixed_regions));
  }
  {
    Overlay overlay;
    const Status result = reader_ocr_overlay_recognize_page(engine, document, 6, &options, &overlay.value, &error);
    size_t count = 0, bytes_out = 0;
    const reader_ocr_overlay_item *items = overlay.value ? reader_ocr_overlay_items(overlay.value, &count) : nullptr;
    const char *text = overlay.value ? reader_ocr_overlay_text(overlay.value, &bytes_out) : nullptr;
    bool letters = false;
    for(size_t i = 0; items && i < count && text; i++) {
      std::string value;
      if(!item_text(text, bytes_out, items[i], value)) continue;
      for(char c : value) if(std::isalpha(static_cast<unsigned char>(c))) letters = true;
    }
    check("bars_page_no_letters", result == READER_OCR_OVERLAY_OK && !letters && count <= 2,
      "count=" + std::to_string(count) + " letters=" + (letters ? "yes" : "no"));
  }

  /* 9. Cancellation, deadline and the commit guard. */
  {
    Overlay overlay;
    reader_ocr_overlay_options cancel_options = options;
    cancel_options.control.cancelled = cancel_always;
    const Status result = reader_ocr_overlay_recognize_page(engine, document, 0, &cancel_options, &overlay.value, &error);
    check("cancel_before_render", result == READER_OCR_OVERLAY_CANCELLED && overlay.value == nullptr, error_text(result, error));
  }
  {
    Overlay overlay;
    reader_ocr_overlay_options cancel_options = options;
    g_cancel_polls = 0; g_cancel_after = 30;
    cancel_options.control.cancelled = cancel_after_polls;
    const Status result = reader_ocr_overlay_recognize_page(engine, document, 0, &cancel_options, &overlay.value, &error);
    check("cancel_during_recognition", result == READER_OCR_OVERLAY_CANCELLED && overlay.value == nullptr,
      error_text(result, error) + " polls=" + std::to_string(g_cancel_polls));
  }
  {
    Overlay overlay;
    reader_ocr_overlay_options timeout_options = options;
    timeout_options.timeout_ms = 1;
    timeout_options.scale = 2.0;
    const Status result = reader_ocr_overlay_recognize_page(engine, document, 0, &timeout_options, &overlay.value, &error);
    check("timeout_deadline", result == READER_OCR_OVERLAY_TIMEOUT && overlay.value == nullptr, error_text(result, error));
  }
  {
    Overlay overlay;
    reader_ocr_overlay_options stale_options = options;
    stale_options.still_current = current_never;
    const Status result = reader_ocr_overlay_recognize_page(engine, document, 0, &stale_options, &overlay.value, &error);
    check("stale_still_current", result == READER_OCR_OVERLAY_STALE && overlay.value == nullptr, error_text(result, error));
  }
  {
    Overlay overlay;
    reader_ocr_overlay_options current_options = options;
    current_options.still_current = current_always;
    const Status result = reader_ocr_overlay_recognize_page(engine, document, 0, &current_options, &overlay.value, &error);
    check("still_current_commits", result == READER_OCR_OVERLAY_OK && overlay.value != nullptr, error_text(result, error));
  }

  /* 10. Meaningful failure paths around the model directory. */
  {
    reader_ocr_engine *other = nullptr;
    const Status result = reader_ocr_engine_open((fixtures + "/absent-models").c_str(), "eng", &other, &error);
    check("missing_model_directory", result == READER_OCR_OVERLAY_MODEL_MISSING && other == nullptr, error_text(result, error));
    if(other) reader_ocr_engine_close(other, nullptr);
  }
  {
    reader_ocr_engine *other = nullptr;
    const Status result = reader_ocr_engine_open((fixtures + "/empty-models").c_str(), "eng", &other, &error);
    check("missing_model_file", result == READER_OCR_OVERLAY_MODEL_MISSING && other == nullptr, error_text(result, error));
    if(other) reader_ocr_engine_close(other, nullptr);
  }
  {
    reader_ocr_engine *other = nullptr;
    const Status result = reader_ocr_engine_open((fixtures + "/empty-model-file").c_str(), "eng", &other, &error);
    check("empty_model_file", result == READER_OCR_OVERLAY_MODEL_MISSING && other == nullptr, error_text(result, error));
    if(other) reader_ocr_engine_close(other, nullptr);
  }

  /* 11. Argument, cap and range boundaries. */
  {
    Overlay overlay;
    const Status result = reader_ocr_overlay_recognize_page(nullptr, document, 0, &options, &overlay.value, &error);
    const Status bitmap_result = reader_ocr_overlay_recognize_bitmap(nullptr, "page-scan", &page_geometry, nullptr, &options, &overlay.value, &error);
    check("argument_null_engine", result == READER_OCR_OVERLAY_ARGUMENT && bitmap_result == READER_OCR_OVERLAY_ARGUMENT && overlay.value == nullptr,
      error_text(result, error));
  }
  {
    Overlay overlay;
    reader_ocr_overlay_options bad = options;
    bad.struct_size = 0;
    const Status wrong_size = reader_ocr_overlay_recognize_page(engine, document, 0, &bad, &overlay.value, &error);
    const Status missing = reader_ocr_overlay_recognize_page(engine, document, 0, nullptr, &overlay.value, &error);
    check("argument_options", wrong_size == READER_OCR_OVERLAY_ARGUMENT && missing == READER_OCR_OVERLAY_ARGUMENT && overlay.value == nullptr,
      error_text(wrong_size, error));
  }
  {
    Overlay overlay;
    bool ok = true;
    for(int variant = 0; variant < 6; variant++) {
      reader_ocr_overlay_options bad = options;
      if(variant == 0) bad.scale = 0;
      else if(variant == 1) bad.scale = 17;
      else if(variant == 2) bad.content_rotation = 45;
      else if(variant == 3) bad.base_dpi = 0;
      else if(variant == 4) bad.min_confidence = 101;
      else bad.timeout_ms = 0;
      const Status result = reader_ocr_overlay_recognize_page(engine, document, 0, &bad, &overlay.value, &error);
      if(result != READER_OCR_OVERLAY_ARGUMENT || overlay.value != nullptr) { ok = false; break; }
    }
    check("argument_scale_rotation_confidence", ok, "six invalid option values refused");
  }
  {
    Overlay overlay;
    bool ok = true;
    for(int variant = 0; variant < 4; variant++) {
      reader_ocr_overlay_options bad = options;
      if(variant == 0) bad.max_pixels = 64000001;
      else if(variant == 1) bad.max_items = 20001;
      else if(variant == 2) bad.max_snapshot_bytes = (4u << 20) + 1;
      else bad.timeout_ms = 300001;
      const Status result = reader_ocr_overlay_recognize_page(engine, document, 0, &bad, &overlay.value, &error);
      if(result != READER_OCR_OVERLAY_ARGUMENT || overlay.value != nullptr) { ok = false; break; }
    }
    check("argument_hard_caps", ok, "four cap overruns refused");
  }
  {
    Overlay overlay;
    std::vector<unsigned char> small(32 * 32 * 4, 255);
    exr_bitmap bitmap{32, 32, 32 * 4, small.data(), 4};
    const Status result = reader_ocr_overlay_recognize_bitmap(engine, "page-scan", &page_geometry, &bitmap, &options, &overlay.value, &error);
    check("argument_bitmap_mismatch", result == READER_OCR_OVERLAY_ARGUMENT && overlay.value == nullptr, error_text(result, error));
  }
  {
    Overlay overlay;
    const Status far = reader_ocr_overlay_recognize_page(engine, document, 99, &options, &overlay.value, &error);
    const Status missing = reader_ocr_overlay_recognize_page(engine, nullptr, 0, &options, &overlay.value, &error);
    check("argument_page_range", far == READER_OCR_OVERLAY_ARGUMENT && missing == READER_OCR_OVERLAY_ARGUMENT && overlay.value == nullptr,
      error_text(far, error));
  }
  {
    reader_ocr_engine *other = nullptr;
    const Status space = reader_ocr_engine_open(models.c_str(), "en g", &other, &error);
    const Status empty = reader_ocr_engine_open(models.c_str(), "eng++eng", &other, &error);
    const Status many = reader_ocr_engine_open(models.c_str(), "e+e+e+e+e+e+e+e+e", &other, &error);
    const Status nodir = reader_ocr_engine_open("", "eng", &other, &error);
    if(other) reader_ocr_engine_close(other, nullptr);
    check("argument_language", space == READER_OCR_OVERLAY_ARGUMENT && empty == READER_OCR_OVERLAY_ARGUMENT &&
      many == READER_OCR_OVERLAY_ARGUMENT && nodir == READER_OCR_OVERLAY_ARGUMENT && other == nullptr, error_text(space, error));
  }
  {
    Overlay overlay;
    reader_ocr_overlay_options small = options;
    small.max_pixels = 1000;
    const long before = g_provider_calls;
    const Status result = reader_ocr_overlay_recognize_page(engine, document, 0, &small, &overlay.value, &error);
    const long after = g_provider_calls;
    check("limit_pixels_before_render", result == READER_OCR_OVERLAY_LIMIT && overlay.value == nullptr && after == before,
      error_text(result, error) + " provider_calls=" + std::to_string(after - before));
  }
  {
    Overlay overlay;
    reader_ocr_overlay_options tiny = options;
    tiny.max_snapshot_bytes = 512;
    const Status result = reader_ocr_overlay_recognize_page(engine, document, 0, &tiny, &overlay.value, &error);
    check("limit_snapshot_budget", result == READER_OCR_OVERLAY_LIMIT && overlay.value == nullptr, error_text(result, error));
  }
  {
    Overlay overlay;
    const Status result = reader_ocr_overlay_recognize_page(engine, document, 7, &options, &overlay.value, &error);
    check("render_failure_propagates", result == READER_OCR_OVERLAY_RENDER && error.sdk_code == EXR_IO && overlay.value == nullptr,
      error_text(result, error));
  }
  {
    Overlay overlay;
    exr_bitmap page_bitmap{};
    Nested nested;
    reader_ocr_overlay_options nested_options = options;
    nested_options.control.progress = nested_progress;
    nested_options.control.context = &nested;
    nested.engine = engine; nested.geometry = &page_geometry; nested.bitmap = &page_bitmap; nested.options = &options;
    g_nested = &nested;
    const Status result = reader_ocr_overlay_recognize_page(engine, document, 0, &nested_options, &overlay.value, &error);
    g_nested = nullptr;
    check("busy_reentrant", result == READER_OCR_OVERLAY_OK && nested.called && nested.status == READER_OCR_OVERLAY_BUSY && overlay.value != nullptr,
      "nested=" + std::string(status_name(nested.status)) + " outer=" + std::string(status_name(result)));
  }

  /* 12. Temporary fixed text for find/select/hit. */
  {
    exr_fixed_text *fixed = nullptr;
    Status result = reader_ocr_overlay_to_fixed_text(baseline.value, READER_OCR_LINE, nullptr, &fixed, &error);
    size_t size = 0, count = 0, found_start = SIZE_MAX, found_end = SIZE_MAX, region = SIZE_MAX, selected = 0;
    const char *text = fixed ? exr_fixed_text_string(fixed, &size) : nullptr;
    const exr_text_region *regions = fixed ? exr_fixed_text_regions(fixed, &count) : nullptr;
    int line_count = 0;
    for(size_t i = 0; i < baseline_items; i++) if(baseline_records[i].level == READER_OCR_LINE) line_count++;
    bool ok = result == READER_OCR_OVERLAY_OK && fixed && text && size > 0 && static_cast<int>(count) == line_count &&
      std::string(text, size).find("31415") != std::string::npos;
    if(ok) ok = exr_fixed_text_find(fixed, "Reading", 7, 0, nullptr, &found_start, &found_end, &sdk) == EXR_OK && found_start != SIZE_MAX;
    if(ok && regions && count > 0) {
      double x = 0, y = 0;
      quad_center(regions[0].quad, x, y);
      ok = exr_fixed_text_hit(fixed, x, y, 1.0, 0, nullptr, &region, &sdk) == EXR_OK && region != SIZE_MAX;
      exr_text_region *overlapping = nullptr;
      if(ok) {
        ok = exr_fixed_text_select(fixed, regions[0].start, regions[0].end, nullptr, &overlapping, &selected, &sdk) == EXR_OK && selected >= 1;
        exr_free(overlapping);
      }
    } else ok = false;
    check("to_fixed_text_lines", ok, "regions=" + std::to_string(count) + " lines=" + std::to_string(line_count) +
      " size=" + std::to_string(size) + " " + error_text(result, error));
    if(fixed) exr_fixed_text_free(fixed);
  }
  {
    exr_fixed_text *fixed = nullptr;
    const Status result = reader_ocr_overlay_to_fixed_text(baseline.value, READER_OCR_WORD, nullptr, &fixed, &error);
    size_t size = 0, count = 0;
    const char *text = fixed ? exr_fixed_text_string(fixed, &size) : nullptr;
    exr_fixed_text_regions(fixed, &count);
    int word_count = 0;
    for(size_t i = 0; i < baseline_items; i++) if(baseline_records[i].level == READER_OCR_WORD) word_count++;
    const bool ok = result == READER_OCR_OVERLAY_OK && fixed && text && size > 0 && static_cast<int>(count) == word_count &&
      std::string(text, size).find("27182") != std::string::npos;
    check("to_fixed_text_words", ok, "regions=" + std::to_string(count) + " words=" + std::to_string(word_count));
    if(fixed) exr_fixed_text_free(fixed);
  }
  {
    exr_fixed_text *fixed = nullptr;
    const Status three = reader_ocr_overlay_to_fixed_text(baseline.value, 3, nullptr, &fixed, &error);
    const Status zero = reader_ocr_overlay_to_fixed_text(baseline.value, 0, nullptr, &fixed, &error);
    const Status missing = reader_ocr_overlay_to_fixed_text(nullptr, READER_OCR_LINE, nullptr, &fixed, &error);
    check("to_fixed_text_rejects_level", three == READER_OCR_OVERLAY_ARGUMENT && zero == READER_OCR_OVERLAY_ARGUMENT &&
      missing == READER_OCR_OVERLAY_ARGUMENT && fixed == nullptr, error_text(three, error));
  }
  {
    exr_fixed_text *fixed = nullptr;
    exr_control control{};
    control.cancelled = cancel_always;
    const Status result = reader_ocr_overlay_to_fixed_text(baseline.value, READER_OCR_LINE, &control, &fixed, &error);
    check("to_fixed_text_cancelled", result == READER_OCR_OVERLAY_CANCELLED && fixed == nullptr, error_text(result, error));
  }
  {
    Overlay overlay;
    exr_fixed_text *fixed = nullptr;
    const Status result = reader_ocr_overlay_recognize_page(engine, document, 0, &options, &overlay.value, &error);
    bool ok = result == READER_OCR_OVERLAY_OK && overlay.value != nullptr;
    if(ok) ok = reader_ocr_overlay_to_fixed_text(overlay.value, READER_OCR_LINE, nullptr, &fixed, &error) == READER_OCR_OVERLAY_OK;
    reader_ocr_overlay_free(overlay.value);
    overlay.value = nullptr;
    size_t size = 0, found_start = SIZE_MAX, found_end = SIZE_MAX;
    const char *text = fixed ? exr_fixed_text_string(fixed, &size) : nullptr;
    ok = ok && fixed && text && size > 0 && std::string(text, size).find("Quiet") != std::string::npos &&
      exr_fixed_text_find(fixed, "27182", 5, 0, nullptr, &found_start, &found_end, &sdk) == EXR_OK && found_start != SIZE_MAX;
    check("to_fixed_text_independent", ok, "bytes=" + std::to_string(size));
    if(fixed) exr_fixed_text_free(fixed);
  }

  /* 13. Thread affinity. */
  {
    std::vector<unsigned char> pixels(900 * 1200, 255);
    exr_bitmap flat{900, 1200, 900, pixels.data(), 1};
    Status foreign = READER_OCR_OVERLAY_OK;
    reader_ocr_overlay *out = nullptr;
    reader_ocr_overlay_error foreign_error{};
    std::thread worker([&]() {
      foreign = reader_ocr_overlay_recognize_bitmap(engine, "page-scan", &page_geometry, &flat, &options, &out, &foreign_error);
    });
    worker.join();
    check("thread_foreign_call_rejected", foreign == READER_OCR_OVERLAY_THREAD && out == nullptr, error_text(foreign, foreign_error));
  }
  {
    Status foreign = READER_OCR_OVERLAY_OK;
    reader_ocr_overlay_error foreign_error{};
    std::thread worker([&]() { foreign = reader_ocr_engine_close(engine, &foreign_error); });
    worker.join();
    /* The refused close must leave the engine usable. */
    Overlay overlay;
    const Status usable = reader_ocr_overlay_recognize_page(engine, document, 0, &options, &overlay.value, &error);
    check("thread_foreign_close_rejected", foreign == READER_OCR_OVERLAY_THREAD && usable == READER_OCR_OVERLAY_OK && overlay.value != nullptr,
      "close=" + std::string(status_name(foreign)) + " reuse=" + std::string(status_name(usable)));
  }

  /* 14. Nothing in the original document changed. */
  {
    const size_t before = exr_fixed_memory_size(document);
    size_t page_count = 0;
    const exr_fixed_page *current = exr_fixed_pages(document, &page_count);
    exr_fixed_text *attached = nullptr;
    const exr_status load = exr_fixed_load_text(document, 0, nullptr, &attached, &sdk);
    Overlay overlay;
    const Status result = reader_ocr_overlay_recognize_page(engine, document, 0, &options, &overlay.value, &error);
    const size_t after = exr_fixed_memory_size(document);
    const exr_fixed_page *later = exr_fixed_pages(document, &page_count);
    const bool ok = load == EXR_FORMAT && attached == nullptr && before == after && result == READER_OCR_OVERLAY_OK &&
      current == later && std::strcmp(later[0].id, "page-scan") == 0 && overlay.value != nullptr;
    check("document_untouched", ok, "memory=" + std::to_string(before) + "->" + std::to_string(after) +
      " text_provider=" + status_name(load == EXR_FORMAT ? READER_OCR_OVERLAY_OK : READER_OCR_OVERLAY_ARGUMENT));
    if(attached) exr_fixed_text_free(attached);
  }
  {
    const Status result = reader_ocr_engine_close(nullptr, &error);
    check("engine_close_null", result == READER_OCR_OVERLAY_OK, error_text(result, error));
  }

  /* 15. Declared host scope and optional second language model. */
  skip("windows_host_scope", "Windows host is not exercised by this package; it stays unaccepted until it runs its own probe");
  skip("mobile_host_scope", "Android/iOS hosts are not exercised by this package; they stay unaccepted until they run their own probe");
  {
    std::ifstream model(models + "/chi_sim.traineddata", std::ios::binary | std::ios::ate);
    const std::streampos length = model.tellg();
    const bool present = model.good() && length > std::streampos(0);
    if(!present) {
      skip("model_chi_sim", "chi_sim.traineddata is absent from this run's model directory");
    } else {
      reader_ocr_engine *other = nullptr;
      const Status result = reader_ocr_engine_open(models.c_str(), "eng+chi_sim", &other, &error);
      check("model_chi_sim", result == READER_OCR_OVERLAY_OK && other != nullptr, error_text(result, error));
      if(other) reader_ocr_engine_close(other, nullptr);
    }
  }
  check("engine_close_owner", reader_ocr_engine_close(engine, &error) == READER_OCR_OVERLAY_OK, "engine closed on its owner thread");

  exr_fixed_free(document);
  exr_bitmap_free(&scan);
  exr_bitmap_free(&bars);

  std::printf("PROBE version=%s\n", version.c_str());
  return write_results(results);
}
