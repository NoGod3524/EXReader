/* SPDX-License-Identifier: MIT */
/* Installed C++ consumer of EXReaderLocalization: C linkage from C++, RAII
   buffer sizing through reader_localization_measure and concurrent rendering
   from several threads. Nothing here includes the package sources. */
#include "reader_localization.h"

#include <atomic>
#include <cstdio>
#include <cstring>
#include <string>
#include <thread>
#include <vector>

namespace {

std::atomic<int> failures{0};

void check(bool condition, const char* name) {
  if (!condition) {
    std::fprintf(stdout, "FAIL %s\n", name);
    ++failures;
  }
}

reader_localization_context make_context(const char* tag) {
  reader_localization_context context{};
  context.struct_size = static_cast<uint32_t>(sizeof(context));
  if (reader_localization_open(tag, &context) != READER_LOCALIZATION_OK) {
    context.locale = 0u;
  }
  return context;
}

reader_localization_param text_param(const std::string& text) {
  reader_localization_param param{};
  param.struct_size = static_cast<uint32_t>(sizeof(param));
  param.kind = static_cast<uint32_t>(READER_LOCALIZATION_PARAM_STRING);
  param.string = text.c_str();
  return param;
}

reader_localization_param int_param(int64_t value) {
  reader_localization_param param{};
  param.struct_size = static_cast<uint32_t>(sizeof(param));
  param.kind = static_cast<uint32_t>(READER_LOCALIZATION_PARAM_INT);
  param.integer = value;
  return param;
}

/* Renders through measure + format, exactly as a native host would: the first
   call learns the size, the second fills an exactly sized std::string. */
std::string render(const reader_localization_context& context, const char* message_id,
                   std::vector<reader_localization_param> params,
                   reader_localization_status* out_status = nullptr) {
  reader_localization_measurement measurement{};
  measurement.struct_size = static_cast<uint32_t>(sizeof(measurement));
  reader_localization_status status = reader_localization_measure(
      &context, message_id, params.empty() ? nullptr : params.data(), params.size(), &measurement);
  if (out_status != nullptr) *out_status = status;
  if (status != READER_LOCALIZATION_OK) return std::string();
  std::string text(measurement.bytes, '\0');
  status = reader_localization_format(&context, message_id,
                                      params.empty() ? nullptr : params.data(), params.size(),
                                      &text[0], text.size(), nullptr);
  if (out_status != nullptr) *out_status = status;
  if (status != READER_LOCALIZATION_OK) return std::string();
  text.resize(std::strlen(text.c_str()));
  return text;
}

}  // namespace

int main() {
  const reader_localization_context en = make_context("en-US");
  const reader_localization_context zh = make_context("zh-CN");
  check(en.locale == static_cast<uint32_t>(READER_LOCALIZATION_LOCALE_EN_US), "cpp-open-en");
  check(zh.locale == static_cast<uint32_t>(READER_LOCALIZATION_LOCALE_ZH_CN), "cpp-open-zh");
  check(reader_localization_abi_version() == READER_LOCALIZATION_ABI_VERSION, "cpp-abi");

  struct Sample {
    std::string title;
    std::string author;
    int64_t percent;
  };
  const std::vector<Sample> samples = {
      {"Ulysses", "James Joyce", 37},
      {"\xe6\xb4\xbb\xe7\x9d\x80", "\xe4\xbd\x99\xe5\x8d\x8e", 0},
      {"\xf0\x9f\x93\x9a Books", "Ana \xc3\x81lvarez", 100},
      {"\xd7\xa9\xd7\x9c\xd7\x95\xd7\x9d", "David", 5},
  };

  /* Single-threaded reference text for each sample and locale. */
  std::vector<std::vector<std::string>> reference(2);
  for (const Sample& sample : samples) {
    std::vector<reader_localization_param> params = {text_param(sample.title),
                                                     text_param(sample.author),
                                                     int_param(sample.percent)};
    reader_localization_status status = READER_LOCALIZATION_OK;
    std::string text = render(en, "reader.a11y.shelf.book", params, &status);
    check(status == READER_LOCALIZATION_OK, "cpp-render-en-status");
    check(!text.empty(), "cpp-render-en-text");
    reference[0].push_back(text);
    text = render(zh, "reader.a11y.shelf.book", params, &status);
    check(status == READER_LOCALIZATION_OK, "cpp-render-zh-status");
    reference[1].push_back(text);
  }
  check(reference[0][0] == "Ulysses by James Joyce, 37% read", "cpp-reference-en");
  check(reference[1][0] == "\xe3\x80\x8aUlysses\xe3\x80\x8b\xef\xbc\x8cJames Joyce\xef\xbc\x8c"
                           "\xe5\xb7\xb2\xe8\xaf\xbb 37%",
        "cpp-reference-zh");

  /* A refused render must leave the caller's string and the reported status
     consistent: measure() succeeds, format() with one byte less fails. */
  {
    std::vector<reader_localization_param> params = {text_param("T"), text_param("A"),
                                                     int_param(1)};
    reader_localization_measurement measurement{};
    measurement.struct_size = static_cast<uint32_t>(sizeof(measurement));
    check(reader_localization_measure(&en, "reader.a11y.shelf.book", params.data(), params.size(),
                                      &measurement) == READER_LOCALIZATION_OK,
          "cpp-measure-short");
    std::vector<char> tiny(measurement.bytes - 1u, static_cast<char>(0xa5));
    const std::vector<char> before = tiny;
    check(reader_localization_format(&en, "reader.a11y.shelf.book", params.data(), params.size(),
                                     tiny.data(), tiny.size(), nullptr) == READER_LOCALIZATION_CAPACITY,
          "cpp-capacity-status");
    check(tiny == before, "cpp-capacity-untouched");
  }

  char digest[65];
  reader_localization_catalog_digest(digest);
  const std::string reference_digest(digest);
  check(reference_digest.size() == 64u, "cpp-digest-length");

  /* Four threads render the same matrix repeatedly. Outputs must stay
     byte-identical to the single-threaded reference, and the catalog digest
     must not change: the library has no mutable global state. */
  std::atomic<int> mismatches{0};
  std::vector<std::thread> workers;
  for (int worker = 0; worker < 4; ++worker) {
    workers.emplace_back([&]() {
      for (int round = 0; round < 200; ++round) {
        for (size_t index = 0; index < samples.size(); ++index) {
          const Sample& sample = samples[index];
          std::vector<reader_localization_param> params = {text_param(sample.title),
                                                           text_param(sample.author),
                                                           int_param(sample.percent)};
          if (render(en, "reader.a11y.shelf.book", params) != reference[0][index]) ++mismatches;
          if (render(zh, "reader.a11y.shelf.book", params) != reference[1][index]) ++mismatches;
          if (render(en, "reader.reading.page",
                     {int_param(sample.percent), int_param(412)}).empty()) {
            ++mismatches;
          }
        }
        char local[65];
        reader_localization_catalog_digest(local);
        if (std::strcmp(local, digest) != 0) ++mismatches;
      }
    });
  }
  for (std::thread& worker : workers) worker.join();
  check(mismatches.load() == 0, "cpp-threads-stable");

  std::fprintf(stdout, "CONSUMER\tcpp\t%d\tfailures\n", failures.load());
  return failures.load() == 0 ? 0 : 1;
}
