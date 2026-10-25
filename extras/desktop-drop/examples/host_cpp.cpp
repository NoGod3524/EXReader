// SPDX-License-Identifier: MIT
// C++ host consumer: the installed package must be usable from C++ with the
// same ownership rules, including destroying a target from its own callback.
#include <exr_desktop_drop.h>
#include <cstdio>
#include <cstring>
#include <memory>
#include <string>
#include <vector>

namespace {

struct RequestDeleter {
  void operator()(exr_drop_request *request) const { exr_drop_request_release(request); }
};
using RequestPtr = std::unique_ptr<exr_drop_request, RequestDeleter>;

struct TargetHandle {
  exr_drop_target *target = nullptr;
  ~TargetHandle() {
    if (target) exr_drop_target_destroy(target);
  }
};

int cancel_always(void *) { return 1; }

}  // namespace

int main() {
  const std::string payload =
      "file:///tmp/exr%20drop%20%E4%B8%AD%E6%96%87.epub\n"
      "file:///tmp/exr-drop-directory/\n"
      "https://example.invalid/b.epub\n"
      "# comment\n"
      "\n";
  exr_drop_request *raw = nullptr;
  exr_drop_control control{};
  control.struct_size = sizeof(control);
  control.cancelled = cancel_always;
  if (exr_drop_request_from_uri_list(payload.data(), payload.size(), EXR_DROP_ORIGIN_TEXT,
                                     &control, &raw) != EXR_DROP_CANCELLED || raw != nullptr) {
    std::printf("cancellation contract broken\n");
    return 2;
  }
  if (exr_drop_request_from_uri_list(payload.data(), payload.size(), EXR_DROP_ORIGIN_CLIPBOARD,
                                     nullptr, &raw) != EXR_DROP_OK) {
    std::printf("parse failed\n");
    return 3;
  }
  RequestPtr request(raw);
  exr_drop_request_info info{};
  info.struct_size = sizeof(info);
  if (exr_drop_request_get_info(request.get(), &info) != EXR_DROP_OK) return 4;
  std::vector<std::string> statuses;
  for (std::size_t index = 0; index < info.item_count; ++index) {
    exr_drop_item item{};
    item.struct_size = sizeof(item);
    if (exr_drop_request_get_item(request.get(), index, &item) != EXR_DROP_OK) return 5;
    statuses.emplace_back(exr_drop_item_status_name(item.status));
  }
  std::printf("items=%zu files=%zu directories=%zu duplicates=%zu\n", info.item_count,
              info.file_count, info.directory_count, info.duplicate_count);
  for (const std::string &status : statuses) std::printf("item=%s\n", status.c_str());
  /* A target needs a native control, so this example only checks the part of
     the target contract that every platform head shares. */
  if (exr_drop_target_destroy(nullptr) != EXR_DROP_ARGUMENT) return 6;
  return 0;
}
