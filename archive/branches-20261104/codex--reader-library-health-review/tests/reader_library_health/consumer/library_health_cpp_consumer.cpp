/* SPDX-License-Identifier: MIT */
/* Installed C++17 consumer for the optional library-health package. It proves
   the public header, C ABI and installed CMake package are usable from C++,
   scans the same 2202-row catalog with different step sizes, compares two
   independent passes, and checks wrong-thread and reentry refusal. */
#include "reader_library_health.h"
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <thread>
#include <vector>

namespace {

struct PlanRow {
  std::string sort_title;
  std::string format;
  std::string sha256;
  unsigned long long bytes;
  std::string file;
  std::string action;
};

struct Row {
  std::string sort_title;
  std::string book_key;
  std::string format;
  long long sdk_book_id;
  int verdict;
  int sdk_status;
  unsigned long long expected_bytes;
  unsigned long long retained_bytes;
  unsigned long long bytes_read;
  int hashed;
  std::string expected_sha256;
  std::string observed_sha256;
};

struct Check {
  std::string id;
  bool passed;
  std::string detail;
};

std::vector<Check> g_checks;
int g_checks_failed = 0;

void check(const char *id, bool passed, const std::string &detail) {
  Check entry;
  entry.id = id;
  entry.passed = passed;
  entry.detail = detail;
  g_checks.push_back(entry);
  if (!passed) g_checks_failed++;
}

std::string yes_no(bool value) { return value ? "true" : "false"; }

bool read_plan(const char *path, std::vector<PlanRow> &out) {
  std::FILE *file = std::fopen(path, "rb");
  if (!file) return false;
  char line[1200];
  while (std::fgets(line, sizeof(line), file)) {
    std::string text(line);
    while (!text.empty() && (text.back() == '\n' || text.back() == '\r')) text.pop_back();
    if (text.empty() || text[0] == '#') continue;
    std::string fields[6];
    std::size_t start = 0;
    std::size_t index = 0;
    bool ok = true;
    for (; index < 6; index++) {
      if (index == 5) {
        fields[index] = text.substr(start);
        break;
      }
      std::size_t tab = text.find('\t', start);
      if (tab == std::string::npos) {
        ok = false;
        break;
      }
      fields[index] = text.substr(start, tab - start);
      start = tab + 1;
    }
    if (!ok) {
      std::fclose(file);
      return false;
    }
    PlanRow row;
    row.sort_title = fields[0];
    row.format = fields[1];
    row.sha256 = fields[2];
    row.bytes = std::strtoull(fields[3].c_str(), nullptr, 10);
    row.file = fields[4];
    row.action = fields[5];
    out.push_back(row);
  }
  std::fclose(file);
  return !out.empty();
}

reader_health_verdict expected_verdict(const std::string &action) {
  if (action == "map") return READER_HEALTH_VERIFIED;
  if (action == "cloud") return READER_HEALTH_CLOUD_ONLY;
  if (action == "missing") return READER_HEALTH_MAPPING_MISSING;
  if (action == "hash_bad") return READER_HEALTH_HASH_MISMATCH;
  if (action == "size_short") return READER_HEALTH_SIZE_MISMATCH;
  if (action == "size_long") return READER_HEALTH_SIZE_MISMATCH;
  if (action == "limit") return READER_HEALTH_LIMIT_SKIPPED;
  return READER_HEALTH_SOURCE_UNAVAILABLE;
}

std::string catalog_key(const PlanRow &row) {
  std::string sha = row.sha256;
  if (row.action == "hash_bad") sha[63] = sha[63] == '0' ? '1' : '0';
  return row.format + ":" + sha;
}

struct State {
  std::vector<Row> rows;
  const std::vector<PlanRow> *plan = nullptr;
  bool identity_ok = true;
  bool order_ok = true;
  bool verdicts_ok = true;
};

int visit(void *context, const reader_health_row *row) {
  State *state = static_cast<State *>(context);
  Row copy;
  copy.sort_title = row->sort_title ? row->sort_title : "";
  copy.book_key = row->book_key ? row->book_key : "";
  copy.format = row->format ? row->format : "";
  copy.sdk_book_id = row->sdk_book_id;
  copy.verdict = static_cast<int>(row->verdict);
  copy.sdk_status = static_cast<int>(row->sdk_status);
  copy.expected_bytes = row->expected_bytes;
  copy.retained_bytes = row->retained_bytes;
  copy.bytes_read = row->bytes_read;
  copy.hashed = row->hashed;
  copy.expected_sha256 = row->expected_sha256;
  copy.observed_sha256 = row->observed_sha256;
  if (!state->rows.empty() && !(state->rows.back().sort_title < copy.sort_title))
    state->order_ok = false;
  if (state->plan && state->rows.size() < state->plan->size()) {
    const PlanRow &expected = (*state->plan)[state->rows.size()];
    if (copy.book_key != catalog_key(expected)) state->identity_ok = false;
    if (copy.sort_title != expected.sort_title) state->identity_ok = false;
    if (copy.verdict != static_cast<int>(expected_verdict(expected.action)))
      state->verdicts_ok = false;
  }
  state->rows.push_back(copy);
  return 0;
}

int ignore_visit(void *context, const reader_health_row *row) {
  (void)context;
  (void)row;
  return 0;
}

struct ReentryProbe {
  reader_health_scanner *scanner;
  bool saw_reentry;
  bool unexpected;
};

int reentry_probe_visit(void *context, const reader_health_row *row) {
  ReentryProbe *probe = static_cast<ReentryProbe *>(context);
  reader_health_cursor cursor;
  reader_health_step_info info;
  reader_health_error error;
  reader_health_status status;
  (void)row;
  std::memset(&info, 0, sizeof(info));
  std::memset(&error, 0, sizeof(error));
  reader_health_cursor_init(&cursor);
  status = reader_health_step(probe->scanner, &cursor, ignore_visit, nullptr, &info, &error);
  if (status == READER_HEALTH_REENTRY) probe->saw_reentry = true;
  else probe->unexpected = true;
  return 0;
}

bool rows_equal(const std::vector<Row> &left, const std::vector<Row> &right) {
  if (left.size() != right.size()) return false;
  for (std::size_t i = 0; i < left.size(); i++) {
    const Row &a = left[i];
    const Row &b = right[i];
    if (a.sort_title != b.sort_title || a.book_key != b.book_key || a.format != b.format ||
        a.sdk_book_id != b.sdk_book_id || a.verdict != b.verdict ||
        a.sdk_status != b.sdk_status || a.expected_bytes != b.expected_bytes ||
        a.retained_bytes != b.retained_bytes || a.bytes_read != b.bytes_read ||
        a.hashed != b.hashed || a.expected_sha256 != b.expected_sha256 ||
        a.observed_sha256 != b.observed_sha256)
      return false;
  }
  return true;
}

std::string json(const std::string &text) {
  std::string out = "\"";
  for (std::size_t i = 0; i < text.size(); i++) {
    unsigned char c = static_cast<unsigned char>(text[i]);
    if (c == '"' || c == '\\') {
      out += '\\';
      out += static_cast<char>(c);
    } else if (c < 0x20) {
      char buffer[8];
      std::snprintf(buffer, sizeof(buffer), "\\u%04x", static_cast<unsigned>(c));
      out += buffer;
    } else {
      out += static_cast<char>(c);
    }
  }
  out += '"';
  return out;
}

void write_json(const char *path, const State &state, std::size_t steps,
                unsigned long long bytes_hashed, bool done) {
  std::FILE *out = std::fopen(path, "wb");
  if (!out) return;
  std::fprintf(out,
               "{\"probe\":\"library-health-cpp-consumer\",\"scenario\":\"cpp\","
               "\"platform\":\"cpp\",\"checks\":[");
  for (std::size_t i = 0; i < g_checks.size(); i++) {
    if (i) std::fputc(',', out);
    std::fprintf(out, "{\"id\":%s,\"passed\":%s,\"detail\":%s}",
                 json(g_checks[i].id).c_str(), yes_no(g_checks[i].passed).c_str(),
                 json(g_checks[i].detail).c_str());
  }
  std::fprintf(out, "],\"rows\":[");
  for (std::size_t i = 0; i < state.rows.size(); i++) {
    const Row &row = state.rows[i];
    const std::string verdict =
        reader_health_verdict_name(static_cast<reader_health_verdict>(row.verdict));
    if (i) std::fputc(',', out);
    std::fprintf(out,
                 "{\"sort_title\":%s,\"book_key\":%s,\"format\":%s,\"sdk_book_id\":%lld,"
                 "\"verdict\":%s,\"sdk_status\":%d,\"expected_bytes\":%llu,"
                 "\"retained_bytes\":%llu,\"bytes_read\":%llu,\"hashed\":%s,"
                 "\"expected_sha256\":%s,\"observed_sha256\":%s}",
                 json(row.sort_title).c_str(), json(row.book_key).c_str(),
                 json(row.format).c_str(), row.sdk_book_id, json(verdict).c_str(),
                 row.sdk_status, row.expected_bytes, row.retained_bytes, row.bytes_read,
                 yes_no(row.hashed != 0).c_str(), json(row.expected_sha256).c_str(),
                 json(row.observed_sha256).c_str());
  }
  std::fprintf(out,
               "],\"stats\":{\"steps\":%llu,\"bytes_hashed\":%llu,\"done\":%s,"
               "\"limit_reached\":false,\"stopped\":false,\"cpu_ms\":0}}",
               static_cast<unsigned long long>(steps), bytes_hashed, yes_no(done).c_str());
  std::fclose(out);
}

}  // namespace

int main(int argc, char **argv) {
  if (argc != 7) {
    std::fprintf(stderr,
                 "usage: %s <catalog.db> <library.db> <plan.tsv> <rows_per_step> <buffer> "
                 "<json>\n",
                 argv[0]);
    return 2;
  }
  std::vector<PlanRow> plan;
  if (!read_plan(argv[3], plan)) {
    std::fprintf(stderr, "cannot read plan\n");
    return 1;
  }
  reader_catalog *catalog = nullptr;
  exr_library *library = nullptr;
  reader_catalog_error catalog_error;
  exr_error error;
  std::memset(&catalog_error, 0, sizeof(catalog_error));
  std::memset(&error, 0, sizeof(error));
  if (reader_catalog_open(argv[1], &catalog, &catalog_error) != 0) {
    std::fprintf(stderr, "catalog open: %s\n", catalog_error.message);
    return 1;
  }
  if (exr_library_open(argv[2], &library, &error) != EXR_OK) {
    std::fprintf(stderr, "library open: %s\n", error.message);
    reader_catalog_close(&catalog, &catalog_error);
    return 1;
  }
  reader_health_options options;
  reader_health_options_init(&options);
  options.rows_per_step = static_cast<std::size_t>(std::strtoul(argv[4], nullptr, 10));
  options.buffer_bytes = static_cast<std::size_t>(std::strtoul(argv[5], nullptr, 10));
  options.max_book_bytes = 600ull * 1024ull;
  reader_health_error health_error;
  std::memset(&health_error, 0, sizeof(health_error));
  State state;
  state.plan = &plan;
  State repeat;
  repeat.plan = &plan;
  reader_health_scanner *scanner = nullptr;
  reader_health_status status =
      reader_health_create(catalog, library, &options, &scanner, &health_error);
  check("cpp_create", status == READER_HEALTH_OK, reader_health_status_name(status));
  std::size_t steps = 0;
  unsigned long long bytes_hashed = 0;
  bool done = false;
  if (status == READER_HEALTH_OK && scanner != nullptr) {
    reader_health_cursor cursor;
    reader_health_cursor_init(&cursor);
    for (;;) {
      reader_health_step_info info;
      reader_health_status now =
          reader_health_step(scanner, &cursor, visit, &state, &info, &health_error);
      if (now != READER_HEALTH_OK) {
        check("cpp_scan_status", false, reader_health_status_name(now));
        break;
      }
      steps++;
      bytes_hashed += info.bytes_hashed;
      if (info.done) {
        done = true;
        break;
      }
      if (info.limit_reached || info.stopped) break;
      if (steps > 100000) break;
    }
    check("cpp_rows_delivered", state.rows.size() == plan.size(),
          std::to_string(state.rows.size()) + " of " + std::to_string(plan.size()));
    check("cpp_identity_and_order", state.identity_ok && state.order_ok,
          std::string("identity=") + yes_no(state.identity_ok) +
              " order=" + yes_no(state.order_ok));
    check("cpp_verdicts", state.verdicts_ok, yes_no(state.verdicts_ok));
    check("cpp_done", done, yes_no(done));
    reader_health_scanner *second = nullptr;
    reader_health_options again = options;
    again.rows_per_step = 3;
    if (reader_health_create(catalog, library, &again, &second, &health_error) ==
        READER_HEALTH_OK) {
      reader_health_cursor restart;
      reader_health_cursor_init(&restart);
      std::size_t repeat_steps = 0;
      bool repeat_done = false;
      for (;;) {
        reader_health_step_info info;
        reader_health_status now =
            reader_health_step(second, &restart, visit, &repeat, &info, &health_error);
        if (now != READER_HEALTH_OK) break;
        repeat_steps++;
        if (info.done) {
          repeat_done = true;
          break;
        }
        if (info.limit_reached || info.stopped) break;
        if (repeat_steps > 100000) break;
      }
      check("cpp_repeat_identical", repeat_done && rows_equal(state.rows, repeat.rows),
            std::to_string(repeat.rows.size()) + " rows, steps " +
                std::to_string(repeat_steps));
      reader_health_destroy(&second, &health_error);
    } else {
      check("cpp_repeat_identical", false, "second scanner create failed");
    }
    ReentryProbe probe;
    probe.scanner = scanner;
    probe.saw_reentry = false;
    probe.unexpected = false;
    reader_health_options reentry_options = options;
    reentry_options.rows_per_step = 4;
    reader_health_scanner *reentrant = nullptr;
    if (reader_health_create(catalog, library, &reentry_options, &reentrant, &health_error) ==
        READER_HEALTH_OK) {
      reader_health_cursor cursor;
      reader_health_cursor_init(&cursor);
      probe.scanner = reentrant;
      for (;;) {
        reader_health_step_info info;
        reader_health_status now =
            reader_health_step(reentrant, &cursor, reentry_probe_visit, &probe, &info,
                               &health_error);
        if (now != READER_HEALTH_OK) break;
        if (info.done || info.limit_reached || info.stopped) break;
      }
      reader_health_destroy(&reentrant, &health_error);
    }
    check("cpp_reentry_refused", probe.saw_reentry && !probe.unexpected,
          std::string("reentry=") + yes_no(probe.saw_reentry) +
              " unexpected=" + yes_no(probe.unexpected));
    reader_health_status threaded = READER_HEALTH_OK;
    std::thread worker([&]() {
      reader_health_cursor cursor;
      reader_health_step_info info;
      reader_health_error inner_error;
      std::memset(&info, 0, sizeof(info));
      std::memset(&inner_error, 0, sizeof(inner_error));
      reader_health_cursor_init(&cursor);
      threaded = reader_health_step(scanner, &cursor, ignore_visit, nullptr, &info, &inner_error);
    });
    worker.join();
    check("cpp_wrong_thread_refused", threaded == READER_HEALTH_THREAD,
          reader_health_status_name(threaded));
    check("cpp_destroy", reader_health_destroy(&scanner, &health_error) == READER_HEALTH_OK,
          "owner thread destroy");
  } else {
    check("cpp_rows_delivered", false, "scanner create failed");
  }
  write_json(argv[6], state, steps, bytes_hashed, done);
  exr_library_close(library);
  reader_catalog_close(&catalog, &catalog_error);
  return g_checks_failed == 0 ? 0 : 1;
}
